from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve1d

from experiments.r0_4k_quality_20261006.evaluate import (
    CLIPS,
    CLIP_DURATION_SECONDS,
    CLIP_FRAMES,
    HEIGHT,
    LR_HEIGHT,
    LR_WIDTH,
    SEQUENCES,
    SAMPLE_FPS,
    STILL_INDICES,
    WIDTH,
    _error_maxpool_thumbnail,
    _summary_rows,
    _ssim_y,
    summarize_clip_rows,
    bicubic_baseline,
    frame_plan,
    make_lr,
    psnr_y,
    quality_metrics,
    temporal_difference_mae,
    validate_frame_plan,
)


def test_frame_plan_has_twenty_stills_and_ten_disjoint_clips() -> None:
    validate_frame_plan()
    plan = frame_plan()
    assert len(CLIPS) == 10
    assert CLIP_DURATION_SECONDS == 5
    assert SAMPLE_FPS == 10
    assert CLIP_FRAMES == 50
    assert all(len(clip.indices) == 50 for clip in CLIPS)
    assert sum(len(indices) for indices in STILL_INDICES.values()) == 20
    assert sum(len(indices) for indices in plan.values()) == 520
    for sequence, actions in plan.items():
        stills = {i for i, jobs in actions.items() if any(job[0] == "image" for job in jobs)}
        clips = {i for i, jobs in actions.items() if any(job[0] == "clip" for job in jobs)}
        assert stills.isdisjoint(clips), sequence


def test_synthetic_pair_and_bicubic_shapes() -> None:
    hr = np.full((HEIGHT, WIDTH), 123, dtype=np.uint8)
    lr = make_lr(hr)
    assert lr.shape == (LR_HEIGHT, LR_WIDTH)
    assert lr.dtype == np.uint8
    upscaled = bicubic_baseline(lr)
    assert upscaled.shape == hr.shape
    assert upscaled.dtype == np.uint8


def test_metrics_identity_and_border_contract() -> None:
    image = np.random.default_rng(123).integers(0, 256, size=(128, 160), dtype=np.uint8)
    assert psnr_y(image, image, 0) == float("inf")
    metrics = quality_metrics(image, image, "same")
    assert metrics["same_ssim_full"] > 0.999999
    assert metrics["same_psnr_db_shave8"] == float("inf")
    assert metrics["same_ssim_shave8"] > 0.999999


def test_striped_ssim_matches_full_frame_reference() -> None:
    rng = np.random.default_rng(655)
    reference = rng.integers(0, 256, size=(241, 193), dtype=np.uint8)
    candidate = np.clip(reference.astype(np.int16) + rng.integers(-8, 9, reference.shape), 0, 255).astype(np.uint8)
    coord = np.arange(11, dtype=np.float64) - 5
    kernel = np.exp(-(coord**2) / (2 * 1.5**2))
    kernel /= kernel.sum()

    def blur(values: np.ndarray) -> np.ndarray:
        return convolve1d(convolve1d(values, kernel, axis=0, mode="constant", cval=0.0),
                          kernel, axis=1, mode="constant", cval=0.0)

    x, y = reference.astype(np.float64) / 255.0, candidate.astype(np.float64) / 255.0
    mux, muy = blur(x), blur(y)
    sigma_x, sigma_y = blur(x * x) - mux * mux, blur(y * y) - muy * muy
    sigma_xy = blur(x * y) - mux * muy
    c1, c2 = 0.01**2, 0.03**2
    expected = float(np.mean(((2 * mux * muy + c1) * (2 * sigma_xy + c2)) /
                             np.maximum((mux * mux + muy * muy + c1) * (sigma_x + sigma_y + c2), 1.0e-15)))
    assert np.isclose(_ssim_y(reference, candidate, 0), expected, atol=2e-15, rtol=0)
    assert np.isclose(_ssim_y(reference, candidate, 8), _ssim_full(reference[8:-8, 8:-8], candidate[8:-8, 8:-8]),
                      atol=2e-15, rtol=0)


def _ssim_full(reference: np.ndarray, candidate: np.ndarray) -> float:
    coord = np.arange(11, dtype=np.float64) - 5
    kernel = np.exp(-(coord**2) / (2 * 1.5**2))
    kernel /= kernel.sum()

    def blur(values: np.ndarray) -> np.ndarray:
        return convolve1d(convolve1d(values, kernel, axis=0, mode="constant", cval=0.0),
                          kernel, axis=1, mode="constant", cval=0.0)

    x, y = reference.astype(np.float64) / 255.0, candidate.astype(np.float64) / 255.0
    mux, muy = blur(x), blur(y)
    sigma_x, sigma_y = blur(x * x) - mux * mux, blur(y * y) - muy * muy
    sigma_xy = blur(x * y) - mux * muy
    c1, c2 = 0.01**2, 0.03**2
    score = (((2 * mux * muy + c1) * (2 * sigma_xy + c2)) /
             np.maximum((mux * mux + muy * muy + c1) * (sigma_x + sigma_y + c2), 1.0e-15))
    return float(np.mean(score, dtype=np.float64))


def test_temporal_difference_metric_is_zero_for_matching_differences() -> None:
    rng = np.random.default_rng(321)
    previous = rng.integers(0, 256, size=(64, 72), dtype=np.uint8)
    current = rng.integers(0, 256, size=(64, 72), dtype=np.uint8)
    assert temporal_difference_mae(current, previous, current, previous, border=4) == 0.0


def test_summary_ignores_hash_strings_and_keeps_numeric_means() -> None:
    rows = [
        {"sequence": "A", "bicubic_psnr_db_full": 30.0, "hybrid_psnr_db_full": 31.0,
         "bicubic_y_sha256": "a" * 64, "hybrid_y_sha256": "b" * 64,
         "hybrid_gain_vs_bicubic_db_shave8": 1.0},
        {"sequence": "A", "bicubic_psnr_db_full": 32.0, "hybrid_psnr_db_full": 31.0,
         "bicubic_y_sha256": "c" * 64, "hybrid_y_sha256": "d" * 64,
         "hybrid_gain_vs_bicubic_db_shave8": -1.0},
    ]
    result = _summary_rows(rows, "sequence")[0]
    assert result["frames"] == 2
    assert result["mean_bicubic_psnr_db_full"] == 31.0
    assert result["mean_hybrid_psnr_db_full"] == 31.0
    assert result["negative_gain_frames"] == 1


def test_clip_summary_contains_full_and_shave8_metrics() -> None:
    rows = []
    for ordinal, shift in ((0, 0.0), (1, 1.0)):
        row = {"sample_id": f"Beauty_first5s_f{ordinal:02d}", "decoded_frame_index": ordinal * 12}
        for model, base in (("bicubic", 30.0), ("hybrid", 31.0)):
            row.update({
                f"{model}_psnr_db_full": base + shift,
                f"{model}_ssim_full": 0.8 + shift / 100,
                f"{model}_psnr_db_shave8": base + shift + 0.1,
                f"{model}_ssim_shave8": 0.81 + shift / 100,
                f"{model}_temporal_difference_mae_u8": None if ordinal == 0 else 2.0,
            })
        row.update({
            "hybrid_gain_vs_bicubic_db_full": 1.0,
            "hybrid_gain_vs_bicubic_db_shave8": 1.0,
            "hybrid_ssim_delta_vs_bicubic_full": 0.01,
            "hybrid_ssim_delta_vs_bicubic_shave8": 0.01,
        })
        rows.append(row)
    # The summarizer expects the frozen 10 x 50 clip set; duplicate valid rows
    # to cover the complete grouping contract without invoking 4K inference.
    expanded = []
    for clip in CLIPS:
        for ordinal in range(CLIP_FRAMES):
            source = rows[ordinal % 2].copy()
            source["sample_id"] = f"{clip.clip_id}_f{ordinal:02d}"
            source["decoded_frame_index"] = clip.indices[ordinal]
            expanded.append(source)
    summaries = summarize_clip_rows(expanded)
    beauty = next(row for row in summaries if row["clip_id"] == "Beauty_first5s")
    assert beauty["frames"] == 50
    assert beauty["mean_hybrid_psnr_db_full"] == 31.5
    assert np.isclose(beauty["mean_bicubic_ssim_shave8"], 0.815)
    assert beauty["mean_hybrid_gain_vs_bicubic_db_shave8"] == 1.0
    assert beauty["bicubic_temporal_difference_mae_u8"] == 2.0


def test_error_contact_thumb_maxpools_local_pixel_differences() -> None:
    reference = np.zeros((12, 12), dtype=np.uint8)
    candidate = reference.copy()
    candidate[5, 5] = 1
    result = _error_maxpool_thumbnail(reference, candidate, size=(2, 2), gain=8)
    expected = np.array([[8, 0], [0, 0]], dtype=np.uint8)
    np.testing.assert_array_equal(result, expected)
