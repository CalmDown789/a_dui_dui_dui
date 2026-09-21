from __future__ import annotations

import math

import numpy as np
import torch
from torch.nn import functional as F


def psnr_u8(reference: np.ndarray, candidate: np.ndarray, crop: int = 2) -> float:
    ref = reference.astype(np.float64)
    got = candidate.astype(np.float64)
    if crop:
        ref = ref[crop:-crop, crop:-crop]
        got = got[crop:-crop, crop:-crop]
    mse = float(np.mean((ref - got) ** 2))
    return 99.0 if mse == 0.0 else 10.0 * math.log10((255.0 * 255.0) / mse)


def ssim_u8(reference: np.ndarray, candidate: np.ndarray, crop: int = 2) -> float:
    ref = reference.astype(np.float32)
    got = candidate.astype(np.float32)
    if crop:
        ref = ref[crop:-crop, crop:-crop]
        got = got[crop:-crop, crop:-crop]
    x = torch.from_numpy(ref).view(1, 1, *ref.shape)
    y = torch.from_numpy(got).view(1, 1, *got.shape)
    coords = torch.arange(11, dtype=torch.float32) - 5.0
    kernel1d = torch.exp(-(coords**2) / (2.0 * 1.5**2))
    kernel1d /= kernel1d.sum()
    kernel = torch.outer(kernel1d, kernel1d).view(1, 1, 11, 11)
    mu_x = F.conv2d(x, kernel, padding=5)
    mu_y = F.conv2d(y, kernel, padding=5)
    sigma_x = F.conv2d(x * x, kernel, padding=5) - mu_x * mu_x
    sigma_y = F.conv2d(y * y, kernel, padding=5) - mu_y * mu_y
    sigma_xy = F.conv2d(x * y, kernel, padding=5) - mu_x * mu_y
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    score = ((2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)) / ((mu_x * mu_x + mu_y * mu_y + c1) * (sigma_x + sigma_y + c2))
    return float(score.mean().item())

