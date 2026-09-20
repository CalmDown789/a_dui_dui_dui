from __future__ import annotations

import numpy as np

from sr_reference import (
    RequantConfig,
    conv2d_int32,
    pixel_shuffle2x,
    prelu_int8,
    requantize_int8,
)


def test_multichannel_valid_convolution() -> None:
    activations = np.empty((4, 5, 2), dtype=np.int8)
    activations[:, :, 0] = np.arange(1, 21, dtype=np.int8).reshape(4, 5)
    activations[:, :, 1] = 2

    weights = np.empty((1, 2, 3, 3), dtype=np.int8)
    weights[0, 0, :, :] = 1
    weights[0, 1, :, :] = -1

    result = conv2d_int32(activations, weights, np.array([7], dtype=np.int32))
    assert result.shape == (2, 3, 1)

    expected = np.empty((2, 3), dtype=np.int32)
    for row in range(2):
        for col in range(3):
            channel0 = activations[row : row + 3, col : col + 3, 0]
            expected[row, col] = 7 + int(channel0.sum()) - 18

    np.testing.assert_array_equal(result[:, :, 0], expected)


def test_same_padding_shape_and_corner() -> None:
    activations = np.arange(1, 10, dtype=np.int8).reshape(3, 3, 1)
    weights = np.ones((1, 1, 3, 3), dtype=np.int8)
    result = conv2d_int32(activations, weights, padding="same")
    assert result.shape == (3, 3, 1)
    assert int(result[0, 0, 0]) == 1 + 2 + 4 + 5
    assert int(result[1, 1, 0]) == 45


def test_requantization_modes() -> None:
    source = np.array([-3, -2, 2, 3, 300], dtype=np.int32)
    nearest = requantize_int8(
        source, RequantConfig(multiplier=1, shift=1, rounding="nearest_away")
    )
    toward_zero = requantize_int8(
        source, RequantConfig(multiplier=1, shift=1, rounding="toward_zero")
    )
    np.testing.assert_array_equal(nearest, [-2, -1, 1, 2, 127])
    np.testing.assert_array_equal(toward_zero, [-1, -1, 1, 1, 127])


def test_prelu_candidate() -> None:
    source = np.array([-8, -3, 0, 7], dtype=np.int32)
    result = prelu_int8(
        source,
        RequantConfig(multiplier=1, shift=2, rounding="toward_zero"),
    )
    np.testing.assert_array_equal(result, [-2, 0, 0, 7])


def test_pixel_shuffle_order() -> None:
    source = np.array([[[10, 20, 30, 40], [11, 21, 31, 41]]], dtype=np.int8)
    result = pixel_shuffle2x(source)
    expected = np.array([[10, 20, 11, 21], [30, 40, 31, 41]], dtype=np.int8)
    np.testing.assert_array_equal(result, expected)


def main() -> None:
    test_multichannel_valid_convolution()
    test_same_padding_shape_and_corner()
    test_requantization_modes()
    test_prelu_candidate()
    test_pixel_shuffle_order()
    print("PYTHON_REFERENCE_TEST_PASS tests=5")


if __name__ == "__main__":
    main()
