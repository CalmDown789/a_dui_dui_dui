"""Configurable three-layer integer network reference for member C."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sr_reference import (
    PaddingMode,
    RequantConfig,
    conv2d_int32,
    pixel_shuffle2x,
    postprocess_channels_int8,
)


@dataclass(frozen=True)
class LayerParameters:
    weights: np.ndarray
    bias: np.ndarray
    requant: tuple[RequantConfig, ...]
    prelu: tuple[RequantConfig, ...] | None = None
    prelu_before_requant: bool = True


def run_layer_int8(
    activations: np.ndarray,
    parameters: LayerParameters,
    *,
    padding: PaddingMode,
) -> np.ndarray:
    accumulators = conv2d_int32(
        activations,
        parameters.weights,
        parameters.bias,
        padding=padding,
    )
    return postprocess_channels_int8(
        accumulators,
        parameters.requant,
        prelu_configs=parameters.prelu,
        prelu_before_requant=parameters.prelu_before_requant,
    )


def run_three_layer_network(
    input_activation: np.ndarray,
    layers: tuple[LayerParameters, LayerParameters, LayerParameters],
    *,
    padding: PaddingMode,
) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Run 1→8→16→4 convolutions and 2× pixel shuffle."""

    expected_channels = ((1, 8), (8, 16), (16, 4))
    current = np.asarray(input_activation, dtype=np.int8)
    if current.ndim != 3 or current.shape[2] != 1:
        raise ValueError("network input must have shape [H, W, 1]")

    intermediates: list[np.ndarray] = []
    for index, (layer, (expected_in, expected_out)) in enumerate(
        zip(layers, expected_channels, strict=True), start=1
    ):
        weights = np.asarray(layer.weights)
        if weights.shape != (expected_out, expected_in, 3, 3):
            raise ValueError(
                f"layer {index} weights must have shape "
                f"{(expected_out, expected_in, 3, 3)}, got {weights.shape}"
            )
        if index < 3 and layer.prelu is None:
            raise ValueError(f"layer {index} requires PReLU parameters")
        if index == 3 and layer.prelu is not None:
            raise ValueError("layer 3 must not apply PReLU before Pixel Shuffle")

        current = run_layer_int8(current, layer, padding=padding)
        intermediates.append(current)

    output = pixel_shuffle2x(intermediates[2])
    return output, (intermediates[0], intermediates[1], intermediates[2])

