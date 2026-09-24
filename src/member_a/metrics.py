from __future__ import annotations

import math

import torch
import torch.nn.functional as F


def _crop(tensor: torch.Tensor, border: int) -> torch.Tensor:
    if border <= 0:
        return tensor
    if tensor.shape[-2] <= 2 * border or tensor.shape[-1] <= 2 * border:
        raise ValueError("Crop border is too large for the image")
    return tensor[..., border:-border, border:-border]


def psnr_y(reference: torch.Tensor, candidate: torch.Tensor, border: int = 2) -> float:
    reference = _crop(reference.to(torch.float64), border)
    candidate = _crop(candidate.to(torch.float64), border)
    mse = torch.mean((reference - candidate) ** 2).item()
    if mse == 0.0:
        return math.inf
    return 10.0 * math.log10(1.0 / mse)


def ssim_y(reference: torch.Tensor, candidate: torch.Tensor, border: int = 2) -> float:
    reference = _crop(reference.to(torch.float64), border)
    candidate = _crop(candidate.to(torch.float64), border)
    coords = torch.arange(11, dtype=torch.float64, device=reference.device) - 5
    kernel_1d = torch.exp(-(coords**2) / (2 * 1.5**2))
    kernel_1d /= kernel_1d.sum()
    kernel = (kernel_1d[:, None] * kernel_1d[None, :]).view(1, 1, 11, 11)
    mu_x = F.conv2d(reference, kernel, padding=5)
    mu_y = F.conv2d(candidate, kernel, padding=5)
    sigma_x = F.conv2d(reference * reference, kernel, padding=5) - mu_x * mu_x
    sigma_y = F.conv2d(candidate * candidate, kernel, padding=5) - mu_y * mu_y
    sigma_xy = F.conv2d(reference * candidate, kernel, padding=5) - mu_x * mu_y
    c1 = 0.01**2
    c2 = 0.03**2
    numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
    denominator = (mu_x * mu_x + mu_y * mu_y + c1) * (sigma_x + sigma_y + c2)
    return torch.mean(numerator / denominator.clamp_min(1.0e-15)).item()
