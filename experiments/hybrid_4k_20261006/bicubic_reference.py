from __future__ import annotations

import numpy as np


def keys_kernel(x: np.ndarray, a: float) -> np.ndarray:
    """Keys cubic-convolution kernel with explicit parameter a."""
    x = np.abs(np.asarray(x, dtype=np.float64))
    near = ((a + 2.0) * x - (a + 3.0)) * x * x + 1.0
    far = (((a * x - 5.0 * a) * x + 8.0 * a) * x) - 4.0 * a
    return np.where(x <= 1.0, near, np.where(x < 2.0, far, 0.0))


def _axis_plan(source_size: int, scale: int, a: float) -> tuple[np.ndarray, np.ndarray]:
    target_size = source_size * scale
    coordinates = (np.arange(target_size, dtype=np.float64) + 0.5) / scale - 0.5
    left = np.floor(coordinates).astype(np.int64) - 1
    taps = left[:, None] + np.arange(4, dtype=np.int64)[None, :]
    weights = keys_kernel(coordinates[:, None] - taps, a)
    # Edge replication combines taps landing outside the source extent.
    taps = np.clip(taps, 0, source_size - 1)
    weights /= weights.sum(axis=1, keepdims=True)
    return taps, weights


def resize_keys(image: np.ndarray, scale: int = 2, a: float = -0.5) -> np.ndarray:
    """Separable Keys bicubic upsample with half-pixel coordinates and edge replication.

    Returns float64 values and deliberately does not clamp or round intermediate
    samples. Input is HxW or HxWxC, with scale an integer enlargement factor.
    """
    source = np.asarray(image)
    if source.ndim not in (2, 3):
        raise ValueError("Expected a grayscale HxW or HWC image")
    if source.shape[0] <= 0 or source.shape[1] <= 0 or scale < 1:
        raise ValueError("Image dimensions and scale must be positive")
    if not np.isfinite(a):
        raise ValueError("Keys parameter a must be finite")

    values = source.astype(np.float64, copy=False)
    y_indices, y_weights = _axis_plan(source.shape[0], scale, a)
    x_indices, x_weights = _axis_plan(source.shape[1], scale, a)

    horizontal = np.zeros((source.shape[0], source.shape[1] * scale) + source.shape[2:], dtype=np.float64)
    for tap in range(4):
        selected = np.take(values, x_indices[:, tap], axis=1)
        weight_shape = (1, x_weights.shape[0]) + ((1,) if source.ndim == 3 else ())
        horizontal += selected * x_weights[:, tap].reshape(weight_shape)

    output = np.zeros((source.shape[0] * scale, source.shape[1] * scale) + source.shape[2:], dtype=np.float64)
    for tap in range(4):
        selected = np.take(horizontal, y_indices[:, tap], axis=0)
        weight_shape = (y_weights.shape[0], 1) + ((1,) if source.ndim == 3 else ())
        output += selected * y_weights[:, tap].reshape(weight_shape)
    return output


def round_ties_away_from_zero(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.copysign(np.floor(np.abs(values) + 0.5), values)


def resize_keys_u8(image: np.ndarray, scale: int = 2, a: float = -0.5) -> np.ndarray:
    values = resize_keys(image, scale=scale, a=a)
    rounded = round_ties_away_from_zero(values)
    return np.clip(rounded, 0, 255).astype(np.uint8)
