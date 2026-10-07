from __future__ import annotations

import numpy as np
import pytest

from experiments.hybrid_4k_20261006.bicubic_reference import resize_keys_u8 as resize_keys_reference
from member_a.pc_postprocess_4k import (
    OUTPUT_BYTES,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    resize_1080_y8_to_4k,
    resize_keys_u8,
)


@pytest.mark.parametrize("shape", [(1, 1), (2, 3), (23, 37)])
@pytest.mark.parametrize("scale", [2, 4, 8])
def test_pc_resizer_matches_frozen_keys_reference(shape: tuple[int, int], scale: int) -> None:
    rng = np.random.default_rng(20261008)
    source = rng.integers(0, 256, size=shape, dtype=np.uint8)

    actual = resize_keys_u8(source, scale=scale, row_chunk=7)
    expected = resize_keys_reference(source, scale=scale, a=-0.5)

    np.testing.assert_array_equal(actual, expected)


def test_pc_resizer_preserves_constant_at_replicated_edges() -> None:
    source = np.full((3, 5), 73, dtype=np.uint8)

    result = resize_keys_u8(source, scale=2, row_chunk=3)

    assert result.shape == (6, 10)
    assert np.all(result == 73)


@pytest.mark.parametrize(
    "source",
    [
        np.zeros((2, 3), dtype=np.float32),
        np.zeros((2, 3, 1), dtype=np.uint8),
        np.zeros((0, 3), dtype=np.uint8),
    ],
)
def test_pc_resizer_rejects_invalid_images(source: np.ndarray) -> None:
    with pytest.raises(ValueError):
        resize_keys_u8(source)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scale": 0},
        {"row_chunk": 0},
        {"a": float("nan")},
    ],
)
def test_pc_resizer_rejects_invalid_options(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        resize_keys_u8(np.zeros((2, 3), dtype=np.uint8), **kwargs)  # type: ignore[arg-type]


def test_fixed_1080p_entrypoint_checks_geometry_before_processing() -> None:
    with pytest.raises(ValueError, match="Input must be uint8 with shape"):
        resize_1080_y8_to_4k(np.zeros((2, 3), dtype=np.uint8))


def test_full_1080p_to_4k_contract_and_constant_frame() -> None:
    source = np.full((1080, 1920), 73, dtype=np.uint8)

    result = resize_1080_y8_to_4k(source, row_chunk=64)

    assert result.shape == (OUTPUT_HEIGHT, OUTPUT_WIDTH) == (2160, 3840)
    assert result.dtype == np.uint8
    assert result.nbytes == OUTPUT_BYTES == 8_294_400
    assert np.all(result == 73)
