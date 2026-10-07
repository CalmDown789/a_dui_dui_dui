"""PC reference post-processing from 1080p Y8 to 4K Y8.

The contract is separable Keys cubic convolution (a=-0.5), half-pixel
coordinates, edge replication, float64 accumulation, ties-away-from-zero
rounding, then uint8 saturation. This is a PC software contract; C must confirm
the display-side contract before integrating it into the board host.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np


INPUT_HEIGHT = 1080
INPUT_WIDTH = 1920
OUTPUT_HEIGHT = 2160
OUTPUT_WIDTH = 3840
OUTPUT_BYTES = OUTPUT_HEIGHT * OUTPUT_WIDTH
KEYS_A = -0.5
ROW_CHUNK = 64


@dataclass(frozen=True)
class PostprocessResult:
    frame_id: str | int
    y_u8: np.ndarray
    started_monotonic_ns: int
    finished_monotonic_ns: int
    duration_ms: float


def _kernel(distance: np.ndarray, a: float) -> np.ndarray:
    x = np.abs(np.asarray(distance, dtype=np.float64))
    near = ((a + 2.0) * x - (a + 3.0)) * x * x + 1.0
    far = (((a * x - 5.0 * a) * x + 8.0 * a) * x) - 4.0 * a
    return np.where(x <= 1.0, near, np.where(x < 2.0, far, 0.0))


def _axis_plan(source_size: int, target_size: int, a: float) -> tuple[np.ndarray, np.ndarray]:
    scale = target_size / source_size
    coordinates = (np.arange(target_size, dtype=np.float64) + 0.5) / scale - 0.5
    left = np.floor(coordinates).astype(np.int64) - 1
    taps = left[:, None] + np.arange(4, dtype=np.int64)[None, :]
    weights = _kernel(coordinates[:, None] - taps, a)
    taps = np.clip(taps, 0, source_size - 1)
    weights /= weights.sum(axis=1, keepdims=True)
    return taps, weights


def resize_keys_u8(
    image: np.ndarray,
    *,
    scale: int = 2,
    a: float = KEYS_A,
    row_chunk: int = ROW_CHUNK,
) -> np.ndarray:
    """Resize a uint8 gray image by an integer factor with bounded memory."""
    source = np.asarray(image)
    if source.dtype != np.uint8 or source.ndim != 2 or min(source.shape) <= 0:
        raise ValueError("Input must be a non-empty 2D uint8 Y image")
    if not np.isfinite(a) or row_chunk <= 0 or scale <= 0:
        raise ValueError("a must be finite; scale and row_chunk must be positive")

    height, width = source.shape
    x_indices, x_weights = _axis_plan(width, width * scale, a)
    y_indices, y_weights = _axis_plan(height, height * scale, a)

    source_f64 = source.astype(np.float64, copy=False)
    horizontal = np.zeros((height, width * scale), dtype=np.float64)
    for tap in range(4):
        horizontal += source_f64[:, x_indices[:, tap]] * x_weights[None, :, tap]

    output = np.empty((height * scale, width * scale), dtype=np.uint8)
    for start in range(0, height * scale, row_chunk):
        stop = min(start + row_chunk, height * scale)
        selected = horizontal[y_indices[start:stop]].transpose(0, 2, 1)
        values = np.einsum("hwk,hk->hw", selected, y_weights[start:stop], optimize=True)
        rounded = np.copysign(np.floor(np.abs(values) + 0.5), values)
        output[start:stop] = np.clip(rounded, 0, 255).astype(np.uint8)
    return output


def resize_1080_y8_to_4k(image: np.ndarray, *, a: float = KEYS_A, row_chunk: int = ROW_CHUNK) -> np.ndarray:
    """Convert a 1920x1080 Y8 plane to a 3840x2160 Y8 plane."""
    source = np.asarray(image)
    if source.shape != (INPUT_HEIGHT, INPUT_WIDTH) or source.dtype != np.uint8:
        raise ValueError(f"Input must be uint8 with shape {(INPUT_HEIGHT, INPUT_WIDTH)}")
    output = resize_keys_u8(source, a=a, row_chunk=row_chunk)
    if output.shape != (OUTPUT_HEIGHT, OUTPUT_WIDTH) or output.nbytes != OUTPUT_BYTES:
        raise RuntimeError("4K output contract violation")
    return output


def process_1080_frame(frame_id: str | int, image: np.ndarray, *, a: float = KEYS_A) -> PostprocessResult:
    """Run one frame and return PC monotonic timestamps around the operation."""
    started = time.perf_counter_ns()
    output = resize_1080_y8_to_4k(image, a=a)
    finished = time.perf_counter_ns()
    return PostprocessResult(frame_id, output, started, finished, (finished - started) / 1_000_000.0)
