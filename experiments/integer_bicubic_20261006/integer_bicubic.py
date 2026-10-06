from __future__ import annotations

from fractions import Fraction

import numpy as np


Q14 = 1 << 14
Q28 = 1 << 28
SCALE = 2
TAPS = 4
KEYS_A = Fraction(-1, 2)

# Coefficient order is the four source taps in increasing source-index order.
# Rows correspond to even and odd output coordinates, respectively.
COEFFICIENTS_Q14 = np.asarray(
    [
        [-384, 3712, 14208, -1152],
        [-1152, 14208, 3712, -384],
    ],
    dtype=np.int16,
)


def _validate_image(image: np.ndarray) -> np.ndarray:
    values = np.asarray(image)
    if values.ndim != 2 or values.dtype != np.uint8:
        raise ValueError("Expected a two-dimensional uint8 luma image")
    if values.shape[0] <= 0 or values.shape[1] <= 0:
        raise ValueError("Image dimensions must be positive")
    return np.ascontiguousarray(values)


def _keys_fraction(distance: Fraction) -> Fraction:
    x = abs(distance)
    a = KEYS_A
    if x <= 1:
        return (a + 2) * x**3 - (a + 3) * x**2 + 1
    if x < 2:
        return a * x**3 - 5 * a * x**2 + 8 * a * x - 4 * a
    return Fraction(0)


def _scalar_phase_coefficients(phase: int) -> tuple[int, int, int, int]:
    """Derive a phase independently with exact rational coordinates and Keys weights."""
    if phase == 0:
        coordinate = Fraction(-1, 4)
        first_source_index = -2
    elif phase == 1:
        coordinate = Fraction(1, 4)
        first_source_index = -1
    else:
        raise ValueError("phase must be 0 (even) or 1 (odd)")
    weights = tuple(_keys_fraction(coordinate - (first_source_index + tap)) for tap in range(TAPS))
    total = sum(weights, Fraction(0))
    scaled = tuple(weight * Q14 / total for weight in weights)
    if any(value.denominator != 1 for value in scaled):
        raise ArithmeticError("The selected Keys phase is not exactly representable in Q14")
    result = tuple(int(value) for value in scaled)
    if sum(result) != Q14:
        raise ArithmeticError("Q14 phase does not have unity gain")
    return result  # type: ignore[return-value]


def _scalar_tap_indices(position: int, source_size: int) -> tuple[int, int, int, int]:
    """Use the literal half-pixel coordinate formula, not the vectorized phase map."""
    coordinate = Fraction(2 * position - 1, 4)
    floor_coordinate = coordinate.numerator // coordinate.denominator
    first = floor_coordinate - 1
    return tuple(min(source_size - 1, max(0, first + tap)) for tap in range(TAPS))  # type: ignore[return-value]


def round_ties_away_from_zero(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    magnitude = abs(int(numerator))
    rounded = (magnitude + denominator // 2) // denominator
    return rounded if numerator >= 0 else -rounded


def _round_array_ties_away(values: np.ndarray, denominator: int) -> np.ndarray:
    # Values in this filter are proven to remain far inside signed INT64.
    values = np.asarray(values, dtype=np.int64)
    half = denominator // 2
    return np.where(values >= 0, (values + half) // denominator, -((-values + half) // denominator))


def resize_scalar(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slow exact-integer reference. Returns output, horizontal Q14, and vertical Q28."""
    source = _validate_image(image)
    source_height, source_width = source.shape
    output_height, output_width = source_height * 2, source_width * 2
    horizontal = [[0] * output_width for _ in range(source_height)]
    phase_coefficients = (_scalar_phase_coefficients(0), _scalar_phase_coefficients(1))

    for y in range(source_height):
        for output_x in range(output_width):
            indices = _scalar_tap_indices(output_x, source_width)
            coefficients = phase_coefficients[output_x & 1]
            horizontal[y][output_x] = sum(
                int(source[y, source_x]) * coefficient
                for source_x, coefficient in zip(indices, coefficients, strict=True)
            )

    vertical_accum = [[0] * output_width for _ in range(output_height)]
    output = np.empty((output_height, output_width), dtype=np.uint8)
    for output_y in range(output_height):
        indices = _scalar_tap_indices(output_y, source_height)
        coefficients = phase_coefficients[output_y & 1]
        for x in range(output_width):
            value = sum(
                horizontal[source_y][x] * coefficient
                for source_y, coefficient in zip(indices, coefficients, strict=True)
            )
            vertical_accum[output_y][x] = value
            pixel = round_ties_away_from_zero(value, Q28)
            output[output_y, x] = min(255, max(0, pixel))

    return (
        output,
        np.asarray(horizontal, dtype=np.int32),
        np.asarray(vertical_accum, dtype=np.int64),
    )


def _vector_tap_indices(output_positions: np.ndarray, source_size: int) -> np.ndarray:
    positions = np.asarray(output_positions, dtype=np.int64)
    # For j=2k the source coordinate is k-1/4 and the leftmost tap is k-2.
    # For j=2k+1 it is k+1/4 and the leftmost tap is k-1.
    first = positions // 2 - np.where((positions & 1) == 0, 2, 1)
    taps = first[:, None] + np.arange(TAPS, dtype=np.int64)[None, :]
    return np.clip(taps, 0, source_size - 1)


def resize_chunked(
    image: np.ndarray,
    *,
    row_chunk: int = 16,
    include_stages: bool = True,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Vectorized/chunked Q14 × Q14 filter with one Q28 final rounding step."""
    source = _validate_image(image)
    if row_chunk <= 0:
        raise ValueError("row_chunk must be positive")
    source_height, source_width = source.shape
    output_height, output_width = source_height * 2, source_width * 2
    coeffs = COEFFICIENTS_Q14.astype(np.int64)
    horizontal_indices = _vector_tap_indices(np.arange(output_width), source_width)
    horizontal_coeffs = coeffs[np.arange(output_width) & 1]
    horizontal = np.empty((source_height, output_width), dtype=np.int32)

    for first_row in range(0, source_height, row_chunk):
        last_row = min(source_height, first_row + row_chunk)
        source_rows = source[first_row:last_row]
        gathered = source_rows[:, horizontal_indices].astype(np.int64)
        sums = np.sum(gathered * horizontal_coeffs[None, :, :], axis=2, dtype=np.int64)
        horizontal[first_row:last_row] = sums.astype(np.int32)

    vertical_indices = _vector_tap_indices(np.arange(output_height), source_height)
    vertical_coeffs = coeffs[np.arange(output_height) & 1]
    vertical_accum = np.empty((output_height, output_width), dtype=np.int64)
    output = np.empty((output_height, output_width), dtype=np.uint8)
    for first_row in range(0, output_height, row_chunk):
        last_row = min(output_height, first_row + row_chunk)
        gathered = horizontal[vertical_indices[first_row:last_row]].transpose(0, 2, 1).astype(np.int64)
        sums = np.sum(
            gathered * vertical_coeffs[first_row:last_row, None, :], axis=2, dtype=np.int64
        )
        vertical_accum[first_row:last_row] = sums
        rounded = _round_array_ties_away(sums, Q28)
        output[first_row:last_row] = np.clip(rounded, 0, 255).astype(np.uint8)

    if include_stages:
        return output, horizontal, vertical_accum
    return output, None, None


def _keys_float64(distance: np.ndarray) -> np.ndarray:
    x = np.abs(np.asarray(distance, dtype=np.float64))
    a = -0.5
    near = ((a + 2.0) * x - (a + 3.0)) * x * x + 1.0
    far = (((a * x - 5.0 * a) * x + 8.0 * a) * x) - 4.0 * a
    return np.where(x <= 1.0, near, np.where(x < 2.0, far, 0.0))


def _float_axis_plan(source_size: int) -> tuple[np.ndarray, np.ndarray]:
    output_positions = np.arange(source_size * 2, dtype=np.float64)
    coordinates = (output_positions + 0.5) / 2.0 - 0.5
    floor_coordinates = np.floor(coordinates).astype(np.int64)
    raw_indices = floor_coordinates[:, None] - 1 + np.arange(TAPS, dtype=np.int64)[None, :]
    weights = _keys_float64(coordinates[:, None] - raw_indices)
    weights /= weights.sum(axis=1, keepdims=True)
    return np.clip(raw_indices, 0, source_size - 1), weights


def resize_float64(image: np.ndarray, *, row_chunk: int = 16) -> np.ndarray:
    """Independent float64 Keys reference; final conversion uses ties-away and clamp."""
    source = _validate_image(image)
    source_height, source_width = source.shape
    output_height, output_width = source_height * 2, source_width * 2
    x_indices, x_weights = _float_axis_plan(source_width)
    y_indices, y_weights = _float_axis_plan(source_height)
    horizontal = np.empty((source_height, output_width), dtype=np.float64)
    values = source.astype(np.float64)
    for first_row in range(0, source_height, row_chunk):
        last_row = min(source_height, first_row + row_chunk)
        gathered = values[first_row:last_row, x_indices]
        horizontal[first_row:last_row] = np.sum(gathered * x_weights[None, :, :], axis=2)

    result = np.empty((output_height, output_width), dtype=np.uint8)
    for first_row in range(0, output_height, row_chunk):
        last_row = min(output_height, first_row + row_chunk)
        gathered = horizontal[y_indices[first_row:last_row]].transpose(0, 2, 1)
        values_y = np.sum(gathered * y_weights[first_row:last_row, None, :], axis=2)
        magnitude = np.floor(np.abs(values_y) + 0.5)
        rounded = np.copysign(magnitude, values_y)
        result[first_row:last_row] = np.clip(rounded, 0, 255).astype(np.uint8)
    return result
