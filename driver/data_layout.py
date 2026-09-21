"""Transport-neutral frame and tensor layout helpers.

This module intentionally does not select DMA, VDMA, TLAST semantics, or a
quantization zero point.  Those values belong to the interfaces owned by
members A and B and must be passed explicitly after they are frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


PaddingMode = Literal["valid", "same"]


@dataclass(frozen=True)
class FrameGeometry:
    rows: int
    cols: int
    channels: int = 1

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.cols <= 0 or self.channels <= 0:
            raise ValueError("rows, cols, and channels must all be positive")

    @property
    def element_count(self) -> int:
        return self.rows * self.cols * self.channels


def network_output_geometry(
    input_geometry: FrameGeometry,
    *,
    convolution_layers: int = 3,
    padding: PaddingMode,
    upscale: int = 2,
) -> FrameGeometry:
    """Return the raster geometry after convolution layers and pixel shuffle."""

    if input_geometry.channels != 1:
        raise ValueError("the frozen external input must be single-channel Y")
    if convolution_layers <= 0:
        raise ValueError("convolution_layers must be positive")
    if upscale <= 0:
        raise ValueError("upscale must be positive")
    if padding not in ("valid", "same"):
        raise ValueError("padding must be 'valid' or 'same'")

    shrink = 2 * convolution_layers if padding == "valid" else 0
    low_rows = input_geometry.rows - shrink
    low_cols = input_geometry.cols - shrink
    if low_rows <= 0 or low_cols <= 0:
        raise ValueError("input is too small for the requested valid convolutions")

    return FrameGeometry(low_rows * upscale, low_cols * upscale, 1)


def pack_hwc_int8(tensor: np.ndarray, geometry: FrameGeometry) -> np.ndarray:
    """Pack signed HWC activations into contiguous transport bytes."""

    source = np.asarray(tensor)
    expected_shape = (geometry.rows, geometry.cols, geometry.channels)
    if source.shape != expected_shape:
        raise ValueError(f"expected HWC shape {expected_shape}, got {source.shape}")
    if source.dtype != np.int8:
        raise TypeError("activation tensor must have dtype int8")

    contiguous = np.ascontiguousarray(source)
    return contiguous.reshape(-1).view(np.uint8).copy()


def unpack_hwc_int8(payload: bytes | bytearray | memoryview | np.ndarray,
                    geometry: FrameGeometry) -> np.ndarray:
    """Unpack transport bytes into a signed contiguous HWC tensor."""

    if isinstance(payload, np.ndarray):
        raw = np.asarray(payload)
        if raw.dtype != np.uint8:
            raise TypeError("array payload must have dtype uint8")
        flat = np.ascontiguousarray(raw).reshape(-1)
    else:
        flat = np.frombuffer(payload, dtype=np.uint8)

    if flat.size != geometry.element_count:
        raise ValueError(
            f"expected {geometry.element_count} bytes, got {flat.size}"
        )

    return flat.view(np.int8).reshape(
        geometry.rows, geometry.cols, geometry.channels
    ).copy()


def encode_y8_to_int8(frame: np.ndarray, *, zero_point: int) -> np.ndarray:
    """Convert unsigned Y8 pixels to signed INT8 activations explicitly."""

    source = np.asarray(frame)
    if source.dtype != np.uint8:
        raise TypeError("Y frame must have dtype uint8")
    if not 0 <= zero_point <= 255:
        raise ValueError("zero_point must be in the unsigned Y8 range")

    shifted = source.astype(np.int16) - zero_point
    if np.any((shifted < -128) | (shifted > 127)):
        raise ValueError(
            "zero_point does not map every supplied pixel into signed INT8"
        )
    return shifted.astype(np.int8)


def decode_int8_to_y8(activations: np.ndarray, *, zero_point: int) -> np.ndarray:
    """Convert signed output activations back to displayable unsigned Y8."""

    source = np.asarray(activations)
    if source.dtype != np.int8:
        raise TypeError("output activations must have dtype int8")
    if not 0 <= zero_point <= 255:
        raise ValueError("zero_point must be in the unsigned Y8 range")

    restored = source.astype(np.int16) + zero_point
    return np.clip(restored, 0, 255).astype(np.uint8)

