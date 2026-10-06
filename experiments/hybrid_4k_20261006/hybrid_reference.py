from __future__ import annotations

import numpy as np
import torch

from .bicubic_reference import resize_keys, round_ties_away_from_zero


def _to_u8(values: np.ndarray) -> np.ndarray:
    return np.clip(round_ties_away_from_zero(values), 0, 255).astype(np.uint8)


@torch.no_grad()
def run_hybrid_float_u8(
    model: torch.nn.Module,
    lr_y_u8: np.ndarray,
    *,
    keys_a: float,
    device: torch.device | str = "cpu",
) -> tuple[np.ndarray, np.ndarray]:
    """Run 540p Y8 -> FP32 CNN x2 -> intermediate Y8 -> Keys bicubic x2 -> final Y8.

    Returns (1080p intermediate, 4K output). This is a float software reference,
    not the final quantized FPGA interpolation contract.
    """
    lr = np.asarray(lr_y_u8)
    if lr.dtype != np.uint8 or lr.ndim != 2:
        raise ValueError("LR input must be a 2D uint8 Y plane")
    tensor = torch.from_numpy(lr.copy()).to(device=device, dtype=torch.float32)[None, None] / 255.0
    model = model.to(device).eval()
    prediction = model(tensor).squeeze(0).squeeze(0).detach().cpu().numpy() * 255.0
    if prediction.shape != (lr.shape[0] * 2, lr.shape[1] * 2):
        raise ValueError(f"CNN output shape mismatch: got {prediction.shape}")
    intermediate = _to_u8(prediction)
    final = resize_keys(intermediate, scale=2, a=keys_a)
    return intermediate, _to_u8(final)


def run_bicubic4x_u8(lr_y_u8: np.ndarray, *, keys_a: float) -> np.ndarray:
    lr = np.asarray(lr_y_u8)
    if lr.dtype != np.uint8 or lr.ndim != 2:
        raise ValueError("LR input must be a 2D uint8 Y plane")
    return _to_u8(resize_keys(lr, scale=4, a=keys_a))
