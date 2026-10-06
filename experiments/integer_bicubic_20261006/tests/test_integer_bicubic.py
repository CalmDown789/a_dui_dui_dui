from __future__ import annotations

import numpy as np
import pytest

from experiments.integer_bicubic_20261006.integer_bicubic import (
    COEFFICIENTS_Q14,
    Q14,
    Q28,
    _vector_tap_indices,
    resize_chunked,
    resize_float64,
    resize_scalar,
    round_ties_away_from_zero,
)


def test_coefficients_are_exact_q14_and_phase_sums_are_unity() -> None:
    assert COEFFICIENTS_Q14.dtype == np.int16
    assert COEFFICIENTS_Q14.tolist() == [[-384, 3712, 14208, -1152], [-1152, 14208, 3712, -384]]
    assert np.all(COEFFICIENTS_Q14.astype(np.int64).sum(axis=1) == Q14)


@pytest.mark.parametrize("shape", [(1, 1), (1, 9), (8, 1), (2, 2), (5, 7), (8, 6), (11, 13)])
def test_scalar_and_chunked_are_identical_for_odd_even_and_degenerate_shapes(shape: tuple[int, int]) -> None:
    generator = np.random.default_rng(shape[0] * 100 + shape[1])
    source = generator.integers(0, 256, size=shape, dtype=np.uint8)
    expected, expected_horizontal, expected_accumulator = resize_scalar(source)
    actual, actual_horizontal, actual_accumulator = resize_chunked(source, row_chunk=3)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual_horizontal, expected_horizontal)
    np.testing.assert_array_equal(actual_accumulator, expected_accumulator)


@pytest.mark.parametrize("value", [0, 1, 127, 255])
def test_constant_image_is_preserved_including_all_edges(value: int) -> None:
    source = np.full((7, 9), value, dtype=np.uint8)
    output, _, _ = resize_chunked(source)
    assert np.all(output == value)


def test_boundary_indices_use_edge_replication() -> None:
    indices = _vector_tap_indices(np.asarray([0, 1, 8, 9]), source_size=5)
    assert indices.tolist() == [[0, 0, 0, 1], [0, 0, 1, 2], [2, 3, 4, 4], [3, 4, 4, 4]]


def test_rounding_is_nearest_with_midpoints_away_from_zero() -> None:
    assert round_ties_away_from_zero(Q28 // 2, Q28) == 1
    assert round_ties_away_from_zero(-Q28 // 2, Q28) == -1
    assert round_ties_away_from_zero(Q28 // 2 - 1, Q28) == 0
    assert round_ties_away_from_zero(-(Q28 // 2 - 1), Q28) == 0
    assert round_ties_away_from_zero(3 * Q28 // 2, Q28) == 2
    assert round_ties_away_from_zero(-3 * Q28 // 2, Q28) == -2


def test_negative_lobes_remain_in_horizontal_stage_and_final_output_saturates() -> None:
    source = np.zeros((7, 9), dtype=np.uint8)
    source[3, 4] = 255
    output, horizontal, accumulator = resize_chunked(source)
    assert horizontal is not None and int(horizontal.min()) < 0
    assert accumulator is not None and int(accumulator.min()) < 0
    assert output.dtype == np.uint8
    assert int(output.min()) == 0 and int(output.max()) <= 255


@pytest.mark.parametrize("shape", [(3, 5), (8, 6), (1, 7)])
def test_float64_and_integer_outputs_match_on_exact_q14_phases(shape: tuple[int, int]) -> None:
    source = np.random.default_rng(23).integers(0, 256, size=shape, dtype=np.uint8)
    integer, _, _ = resize_chunked(source)
    floating = resize_float64(source, row_chunk=2)
    np.testing.assert_array_equal(integer, floating)


def test_high_contrast_corners_and_ramp_match_independent_scalar_reference() -> None:
    source = np.zeros((9, 11), dtype=np.uint8)
    source[0, 0] = 255
    source[0, -1] = 17
    source[-1, 0] = 93
    source[-1, -1] = 255
    source[1:-1, 1:-1] = np.arange(7 * 9, dtype=np.uint8).reshape(7, 9)
    expected = resize_scalar(source)[0]
    actual = resize_chunked(source, row_chunk=4)[0]
    np.testing.assert_array_equal(actual, expected)


def test_invalid_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="two-dimensional uint8"):
        resize_chunked(np.zeros((2, 3, 1), dtype=np.uint8))
    with pytest.raises(ValueError, match="row_chunk"):
        resize_chunked(np.zeros((2, 3), dtype=np.uint8), row_chunk=0)
