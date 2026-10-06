from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from experiments.r0_4k_quality_20261006.color_demo import ycbcr709_full_to_rgb as demo_conversion
from experiments.r0_4k_quality_20261006.evaluate_color_quality import (
    contact_ordinals,
    _available_memory_mib,
    _read_checkpoint_rows,
    _resize_plane,
    _write_contact_row,
    _write_contact_sheet,
    _write_csv_atomic,
    psnr_rgb,
    sampled_ordinals,
    ssim_rgb,
    ycbcr709_full_to_rgb,
)


def test_bt709_full_range_neutral_chroma_preserves_gray() -> None:
    y = np.array([[0, 1, 127], [128, 254, 255]], dtype=np.uint8)
    neutral = np.full_like(y, 128)
    rgb = ycbcr709_full_to_rgb(y, neutral, neutral)
    assert np.array_equal(rgb[:, :, 0], y)
    assert np.array_equal(rgb[:, :, 1], y)
    assert np.array_equal(rgb[:, :, 2], y)


def test_color_conversion_matches_existing_software_demo_contract() -> None:
    rng = np.random.default_rng(20261007)
    y = rng.integers(0, 256, size=(32, 48), dtype=np.uint8)
    cb = rng.integers(0, 256, size=(32, 48), dtype=np.uint8)
    cr = rng.integers(0, 256, size=(32, 48), dtype=np.uint8)
    assert np.array_equal(ycbcr709_full_to_rgb(y, cb, cr), demo_conversion(y, cb, cr))


@pytest.mark.parametrize("method", ["bicubic", "bilinear"])
def test_chroma_resizing_preserves_constant_and_shape(method: str) -> None:
    plane = np.full((9, 11), 137, dtype=np.uint8)
    result = _resize_plane(plane, 22, 18, method)
    assert result.shape == (18, 22)
    assert result.dtype == np.uint8
    assert np.all(result == 137)


def test_rgb_metrics_are_exact_for_identical_frame() -> None:
    rng = np.random.default_rng(123)
    image = rng.integers(0, 256, size=(40, 48, 3), dtype=np.uint8)
    assert np.isinf(psnr_rgb(image, image))
    assert np.isinf(psnr_rgb(image, image, border=8))
    assert ssim_rgb(image, image) == pytest.approx(1.0, abs=1e-14)
    assert ssim_rgb(image, image, border=8) == pytest.approx(1.0, abs=1e-14)


def test_rgb_psnr_uses_joint_three_channel_mse() -> None:
    reference = np.zeros((16, 20, 3), dtype=np.uint8)
    candidate = reference.copy()
    candidate[:, :, 0] = 255
    assert psnr_rgb(reference, candidate) == pytest.approx(10.0 * np.log10(3.0), abs=1e-12)


def test_deterministic_sample_schedule_spans_clip_and_includes_regression_ordinals() -> None:
    ordinals = sampled_ordinals(30)
    assert len(ordinals) == len(set(ordinals)) == 30
    assert ordinals[0] == 0
    assert ordinals[-1] == 49
    assert 17 in ordinals
    assert 35 in ordinals


def test_sample_schedule_rejects_out_of_range_count() -> None:
    with pytest.raises(ValueError):
        sampled_ordinals(0)
    with pytest.raises(ValueError):
        sampled_ordinals(51)


def test_contact_sheet_samples_adapt_to_smoke_and_full_runs() -> None:
    assert contact_ordinals(1) == (0,)
    assert contact_ordinals(2) == (0, 1)
    assert contact_ordinals(30) == (0, 15, 29)


def test_color_metrics_reject_non_rgb_or_non_uint8_inputs() -> None:
    gray = np.zeros((16, 20), dtype=np.uint8)
    rgb = np.zeros((16, 20, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        psnr_rgb(gray, gray)
    with pytest.raises(ValueError):
        ssim_rgb(gray, gray)
    with pytest.raises(ValueError):
        psnr_rgb(rgb.astype(np.float32), rgb.astype(np.float32))


def test_checkpoint_csv_roundtrips_typed_rows_atomically(tmp_path) -> None:
    path = tmp_path / "partial_metrics.csv"
    row = {
        "sequence": "Beauty",
        "sample_ordinal": 15,
        "decoded_frame_index": 252,
        "timestamp_seconds": 2.1,
        "source_y_sha256": "a" * 64,
        "rgb_psnr_db_full": 38.25,
        "rgb_ssim_full": 0.95,
    }
    _write_csv_atomic(path, [row])
    loaded = _read_checkpoint_rows(path)
    assert loaded == [row]
    assert isinstance(loaded[0]["sample_ordinal"], int)
    assert isinstance(loaded[0]["timestamp_seconds"], float)
    assert not path.with_name(path.name + ".tmp").exists()


def test_contact_rows_are_independently_persistable(tmp_path) -> None:
    panels = [Image.new("RGB", (384, 216), color) for color in ("gray", "red", "green", "blue", "white")]
    row_path = tmp_path / "contact_rows" / "beauty_ordinal_00.jpg"
    _write_contact_row(row_path, "Beauty", 0, panels)
    assert row_path.is_file()
    with Image.open(row_path) as saved:
        assert saved.size == (384 * 5, 216 + 30)
    sheet_path = tmp_path / "beauty_contact.jpg"
    _write_contact_sheet(sheet_path, [row_path])
    with Image.open(sheet_path) as saved:
        assert saved.size == (384 * 5, 216 + 30)


def test_available_memory_probe_returns_none_or_nonnegative_integer() -> None:
    available = _available_memory_mib()
    assert available is None or (isinstance(available, int) and available >= 0)
