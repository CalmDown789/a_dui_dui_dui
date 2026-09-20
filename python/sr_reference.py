"""Configurable integer reference operations for the 10-hour SR sprint.

Tensor layout:
  activations: [height, width, input_channel]
  weights:     [output_channel, input_channel, kernel_row, kernel_col]

The module intentionally exposes padding and requantization choices instead
of freezing member B's model decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


PaddingMode = Literal["valid", "same"]
RoundingMode = Literal["nearest_away", "toward_zero", "floor"]


@dataclass(frozen=True)
class RequantConfig:
    multiplier: int
    shift: int
    zero_point: int = 0
    rounding: RoundingMode = "nearest_away"
    saturate: bool = True


def conv2d_int32(
    activations: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray | None = None,
    *,
    padding: PaddingMode = "valid",
) -> np.ndarray:
    """Compute a 3x3 INT8 convolution with INT32 outputs."""

    x = np.asarray(activations, dtype=np.int8)
    w = np.asarray(weights, dtype=np.int8)

    if x.ndim != 3:
        raise ValueError("activations must have shape [H, W, Cin]")
    if w.ndim != 4 or w.shape[2:] != (3, 3):
        raise ValueError("weights must have shape [Cout, Cin, 3, 3]")
    if x.shape[2] != w.shape[1]:
        raise ValueError("activation and weight input-channel counts differ")
    if padding not in ("valid", "same"):
        raise ValueError("padding must be 'valid' or 'same'")

    cout = w.shape[0]
    if bias is None:
        b = np.zeros(cout, dtype=np.int32)
    else:
        b = np.asarray(bias, dtype=np.int32)
        if b.shape != (cout,):
            raise ValueError("bias must have shape [Cout]")

    if padding == "same":
        x_work = np.pad(x, ((1, 1), (1, 1), (0, 0)), mode="constant")
    else:
        x_work = x

    out_h = x_work.shape[0] - 2
    out_w = x_work.shape[1] - 2
    if out_h <= 0 or out_w <= 0:
        raise ValueError("input is too small for a 3x3 convolution")

    result = np.empty((out_h, out_w, cout), dtype=np.int32)
    w64 = w.astype(np.int64)

    for row in range(out_h):
        for col in range(out_w):
            window = x_work[row : row + 3, col : col + 3, :]
            window_c_first = np.transpose(window, (2, 0, 1)).astype(np.int64)
            for out_channel in range(cout):
                accumulator = int(b[out_channel]) + int(
                    np.sum(window_c_first * w64[out_channel], dtype=np.int64)
                )
                if accumulator < np.iinfo(np.int32).min or accumulator > np.iinfo(
                    np.int32
                ).max:
                    raise OverflowError("INT32 accumulator overflow")
                result[row, col, out_channel] = accumulator

    return result


def _round_shift(values: np.ndarray, shift: int, mode: RoundingMode) -> np.ndarray:
    if shift < 0:
        return values << (-shift)
    if shift == 0:
        return values

    divisor = 1 << shift
    if mode == "floor":
        return values // divisor

    magnitude = np.abs(values)
    if mode == "nearest_away":
        magnitude = magnitude + (divisor >> 1)
    elif mode != "toward_zero":
        raise ValueError(f"unsupported rounding mode: {mode}")

    shifted = magnitude // divisor
    return np.where(values < 0, -shifted, shifted)


def requantize_int8(values: np.ndarray, config: RequantConfig) -> np.ndarray:
    """Apply configurable integer rescaling and optional INT8 saturation."""

    source = np.asarray(values, dtype=np.int64)
    scaled = _round_shift(source * config.multiplier, config.shift, config.rounding)
    shifted = scaled + config.zero_point

    if config.saturate:
        shifted = np.clip(shifted, -128, 127)
    elif np.any((shifted < -128) | (shifted > 127)):
        raise OverflowError("requantized value is outside INT8 without saturation")

    return shifted.astype(np.int8)


def prelu_int8(
    values: np.ndarray,
    negative_config: RequantConfig,
) -> np.ndarray:
    """Apply identity on non-negative values and configurable slope on negatives."""

    source = np.asarray(values, dtype=np.int32)
    negative = requantize_int8(source, negative_config)
    positive = np.clip(source, -128, 127).astype(np.int8)
    return np.where(source < 0, negative, positive).astype(np.int8)


def pixel_shuffle2x(channels: np.ndarray) -> np.ndarray:
    """Map [H, W, 4] to [2H, 2W] using channel=dy*2+dx."""

    source = np.asarray(channels, dtype=np.int8)
    if source.ndim != 3 or source.shape[2] != 4:
        raise ValueError("pixel shuffle input must have shape [H, W, 4]")

    height, width, _ = source.shape
    output = np.empty((height * 2, width * 2), dtype=np.int8)
    output[0::2, 0::2] = source[:, :, 0]
    output[0::2, 1::2] = source[:, :, 1]
    output[1::2, 0::2] = source[:, :, 2]
    output[1::2, 1::2] = source[:, :, 3]
    return output
