from __future__ import annotations

import math

import numpy as np
import pytest

from experiments.hybrid_4k_20261006.compare_r0_qat456_video import (
    _bootstrap_ci,
    _delta_distribution,
    _select_sample_ordinals,
)
from experiments.hybrid_4k_20261006.audit_r0_qat456_output_delta import _pixel_delta_metrics


@pytest.mark.parametrize("frame_count", [120, 125])
def test_stratified_sample_is_unique_even_and_includes_endpoints(frame_count: int) -> None:
    selected = _select_sample_ordinals(frame_count, 24)

    assert len(selected) == 24
    assert len(set(selected)) == 24
    assert selected == sorted(selected)
    assert selected[0] == 0
    assert selected[-1] == frame_count - 1
    gaps = [right - left for left, right in zip(selected, selected[1:])]
    assert max(gaps) - min(gaps) <= 1


def test_sequence_bootstrap_is_deterministic_and_bounded() -> None:
    means = {"a": 0.01, "b": 0.05, "c": 0.08, "d": 0.12, "e": 0.15, "f": 0.3}

    first = _bootstrap_ci(means)
    second = _bootstrap_ci(means)

    assert first == second
    assert first is not None
    assert math.isfinite(first[0]) and math.isfinite(first[1])
    assert first[0] <= first[1]
    assert first[0] >= min(means.values())
    assert first[1] <= max(means.values())


def test_delta_distribution_reports_min_quantiles_and_max() -> None:
    result = _delta_distribution([-0.2, -0.1, 0.0, 0.1, 0.2])

    assert result["min"] == -0.2
    assert result["median"] == 0.0
    assert result["max"] == 0.2
    assert result["p05"] <= result["median"] <= result["p95"]


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")]])
def test_delta_distribution_rejects_empty_or_nonfinite_values(values: list[float]) -> None:
    with pytest.raises(ValueError):
        _delta_distribution(values)


def test_output_delta_metrics_are_zero_for_identical_frames() -> None:
    frame = np.full((4, 4), 128, dtype=np.uint8)

    result = _pixel_delta_metrics(frame, frame.copy())

    assert result["changed_pixel_fraction"] == 0.0
    assert result["mean_absolute_difference"] == 0.0
    assert result["max_absolute_difference"] == 0


def test_output_delta_metrics_capture_sparse_pixel_change() -> None:
    qat = np.zeros((4, 4), dtype=np.uint8)
    r0 = qat.copy()
    qat[2, 1] = 255

    result = _pixel_delta_metrics(qat, r0)

    assert result["changed_pixel_fraction"] == 1 / 16
    assert result["mean_absolute_difference"] == 255 / 16
    assert result["max_absolute_difference"] == 255


def test_output_delta_metrics_reject_incompatible_arrays() -> None:
    with pytest.raises(ValueError):
        _pixel_delta_metrics(np.zeros((2, 2), dtype=np.uint8), np.zeros((2, 3), dtype=np.uint8))
