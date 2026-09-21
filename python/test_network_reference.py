from __future__ import annotations

import numpy as np

from network_reference import LayerParameters, run_three_layer_network
from sr_reference import RequantConfig, postprocess_channels_int8


IDENTITY = RequantConfig(multiplier=1, shift=0, rounding="toward_zero")
PRELU_IDENTITY = RequantConfig(multiplier=1, shift=0, rounding="toward_zero")


def make_routing_layer(input_channels: int, output_channels: int,
                       *, with_prelu: bool) -> LayerParameters:
    weights = np.zeros((output_channels, input_channels, 3, 3), dtype=np.int8)
    weights[:, 0, 1, 1] = 1
    return LayerParameters(
        weights=weights,
        bias=np.zeros(output_channels, dtype=np.int32),
        requant=(IDENTITY,) * output_channels,
        prelu=(PRELU_IDENTITY,) * output_channels if with_prelu else None,
    )


def test_three_layer_same_and_valid_geometry() -> None:
    source = np.arange(1, 50, dtype=np.int8).reshape(7, 7, 1)
    layers = (
        make_routing_layer(1, 8, with_prelu=True),
        make_routing_layer(8, 16, with_prelu=True),
        make_routing_layer(16, 4, with_prelu=False),
    )

    same_output, same_intermediates = run_three_layer_network(
        source, layers, padding="same"
    )
    assert [value.shape for value in same_intermediates] == [
        (7, 7, 8),
        (7, 7, 16),
        (7, 7, 4),
    ]
    assert same_output.shape == (14, 14)
    np.testing.assert_array_equal(same_output[0::2, 0::2], source[:, :, 0])
    np.testing.assert_array_equal(same_output[0::2, 1::2], source[:, :, 0])
    np.testing.assert_array_equal(same_output[1::2, 0::2], source[:, :, 0])
    np.testing.assert_array_equal(same_output[1::2, 1::2], source[:, :, 0])

    valid_output, valid_intermediates = run_three_layer_network(
        source, layers, padding="valid"
    )
    assert [value.shape for value in valid_intermediates] == [
        (5, 5, 8),
        (3, 3, 16),
        (1, 1, 4),
    ]
    np.testing.assert_array_equal(valid_output, np.full((2, 2), 25, dtype=np.int8))


def test_channel_postprocess_order() -> None:
    accumulators = np.array([[[-9, -9], [9, 9]]], dtype=np.int32)
    requant = (
        RequantConfig(multiplier=1, shift=1, rounding="toward_zero"),
        RequantConfig(multiplier=1, shift=1, rounding="toward_zero"),
    )
    prelu = (
        RequantConfig(multiplier=1, shift=1, rounding="toward_zero"),
        RequantConfig(multiplier=1, shift=1, rounding="toward_zero"),
    )
    before = postprocess_channels_int8(
        accumulators, requant, prelu_configs=prelu, prelu_before_requant=True
    )
    after = postprocess_channels_int8(
        accumulators, requant, prelu_configs=prelu, prelu_before_requant=False
    )
    np.testing.assert_array_equal(before, [[[-2, -2], [4, 4]]])
    np.testing.assert_array_equal(after, [[[-2, -2], [4, 4]]])


def main() -> None:
    test_three_layer_same_and_valid_geometry()
    test_channel_postprocess_order()
    print("NETWORK_REFERENCE_TEST_PASS tests=2")


if __name__ == "__main__":
    main()

