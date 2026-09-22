from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import csv
import random

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from .data import EvalDataset, TrainDataset
from .metrics import psnr_y, ssim_y
from .model import FSRCNNSubpixel
from .quantization import INT16_MAX, INT16_MIN, Q15, named_layers, quantized_forward_float


def seed_everything(seed: int = 123) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


@torch.no_grad()
def evaluate_model(
    model: FSRCNNSubpixel,
    dataset: EvalDataset,
    device: torch.device,
    activation_scales: dict[str, float] | None = None,
) -> tuple[list[dict[str, float | str]], dict[str, float]]:
    model.eval()
    rows: list[dict[str, float | str]] = []
    for index in range(len(dataset)):
        name, lr, hr = dataset[index]
        lr = lr.unsqueeze(0).to(device)
        hr = hr.unsqueeze(0).to(device)
        fp32 = model(lr).clamp(0.0, 1.0)
        quant = (
            quantized_forward_float(model, lr, activation_scales)
            if activation_scales is not None
            else fp32
        )
        bicubic = F.interpolate(lr, size=hr.shape[-2:], mode="bicubic", align_corners=False).clamp(0.0, 1.0)
        rows.append(
            {
                "image": name,
                "bicubic_psnr_db": psnr_y(hr, bicubic),
                "bicubic_ssim": ssim_y(hr, bicubic),
                "fp32_psnr_db": psnr_y(hr, fp32),
                "fp32_ssim": ssim_y(hr, fp32),
                "quant_psnr_db": psnr_y(hr, quant),
                "quant_ssim": ssim_y(hr, quant),
            }
        )
    summary = {
        key: float(np.mean([float(row[key]) for row in rows]))
        for key in [
            "bicubic_psnr_db",
            "bicubic_ssim",
            "fp32_psnr_db",
            "fp32_ssim",
            "quant_psnr_db",
            "quant_ssim",
        ]
    }
    summary["quant_psnr_loss_db"] = summary["fp32_psnr_db"] - summary["quant_psnr_db"]
    return rows, summary


def train_fp32(
    model: FSRCNNSubpixel,
    train_file: Path,
    eval_file: Path,
    output_dir: Path,
    device: torch.device,
    max_epochs: int = 50,
    min_epochs: int = 20,
    patience: int = 10,
    batch_size: int = 16,
    seed: int = 123,
) -> list[dict[str, float | int]]:
    seed_everything(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.to(device)
    train_set = TrainDataset(train_file)
    eval_set = EvalDataset(eval_file)
    loader = DataLoader(train_set, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=device.type == "cuda")
    optimizer = torch.optim.Adam(
        [
            {"params": [p for name, p in model.named_parameters() if not name.startswith("subpixel.")]},
            {"params": model.subpixel.parameters(), "lr": 1.0e-4},
        ],
        lr=1.0e-3,
    )
    criterion = nn.MSELoss()
    best_psnr = -float("inf")
    best_state = deepcopy(model.state_dict())
    stale = 0
    log: list[dict[str, float | int]] = []
    for epoch in range(max_epochs):
        if epoch == 30:
            for group in optimizer.param_groups:
                group["lr"] *= 0.1
        model.train()
        loss_total = 0.0
        sample_total = 0
        for inputs, labels in tqdm(loader, desc=f"train {epoch + 1}/{max_epochs}", leave=False):
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), labels)
            loss.backward()
            optimizer.step()
            loss_total += float(loss.item()) * inputs.shape[0]
            sample_total += inputs.shape[0]
        _, metrics = evaluate_model(model, eval_set, device)
        row = {
            "epoch": epoch + 1,
            "mse_loss": loss_total / max(sample_total, 1),
            "set5_psnr_db": metrics["fp32_psnr_db"],
            "set5_ssim": metrics["fp32_ssim"],
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
        }
        log.append(row)
        if metrics["fp32_psnr_db"] > best_psnr:
            best_psnr = metrics["fp32_psnr_db"]
            best_state = deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
        if epoch + 1 >= min_epochs and stale >= patience:
            break
    model.load_state_dict(best_state)
    torch.save(
        {"state_dict": model.state_dict(), "config": model.config.to_dict(), "seed": seed, "best_set5_psnr_db": best_psnr},
        output_dir / "fsrcnn_d16_s8_m1_c16_x2_fp32.pth",
    )
    with (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(log[0]))
        writer.writeheader()
        writer.writerows(log)
    return log


def _ste_fake_quant(values: torch.Tensor, scale: torch.Tensor | float, qmin: int, qmax: int) -> torch.Tensor:
    scale_tensor = torch.as_tensor(scale, dtype=values.dtype, device=values.device)
    while scale_tensor.ndim < values.ndim:
        scale_tensor = scale_tensor.unsqueeze(-1)
    quantized = torch.clamp(torch.round(values / scale_tensor), qmin, qmax) * scale_tensor
    return values + (quantized - values).detach()


def qat_forward(model: FSRCNNSubpixel, x: torch.Tensor, scales: dict[str, float]) -> torch.Tensor:
    current = _ste_fake_quant(x, 1.0 / 255.0, 0, 255)
    for name, conv, prelu in named_layers(model):
        weight_scale = torch.clamp(conv.weight.detach().abs().amax(dim=(1, 2, 3)) / 127.0, min=1.0e-12)
        weight = _ste_fake_quant(conv.weight, weight_scale, -127, 127)
        current = F.conv2d(current, weight, conv.bias, padding=conv.padding)
        if prelu is not None:
            alpha = _ste_fake_quant(prelu.weight, 1.0 / Q15, INT16_MIN, INT16_MAX)
            current = F.prelu(current, alpha)
            current = _ste_fake_quant(current, scales[name], INT16_MIN, INT16_MAX)
    current = F.pixel_shuffle(current, 2)
    return _ste_fake_quant(current, 1.0 / 255.0, 0, 255).clamp(0.0, 1.0)


def qat_finetune(
    model: FSRCNNSubpixel,
    train_file: Path,
    scales: dict[str, float],
    output_dir: Path,
    device: torch.device,
    epochs: int = 5,
    batch_size: int = 16,
) -> list[dict[str, float | int]]:
    train_set = TrainDataset(train_file)
    loader = DataLoader(train_set, batch_size=batch_size, shuffle=True, num_workers=0)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-5)
    criterion = nn.MSELoss()
    log: list[dict[str, float | int]] = []
    model.train()
    for epoch in range(epochs):
        total = 0.0
        count = 0
        for inputs, labels in tqdm(loader, desc=f"qat {epoch + 1}/{epochs}", leave=False):
            inputs = inputs.to(device)
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(qat_forward(model, inputs, scales), labels)
            loss.backward()
            optimizer.step()
            total += float(loss.item()) * inputs.shape[0]
            count += inputs.shape[0]
        log.append({"epoch": epoch + 1, "mse_loss": total / max(count, 1)})
    torch.save(
        {"state_dict": model.state_dict(), "config": model.config.to_dict(), "qat_epochs": epochs},
        output_dir / "fsrcnn_d16_s8_m1_c16_x2_qat.pth",
    )
    with (output_dir / "qat_log.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(log[0]))
        writer.writeheader()
        writer.writerows(log)
    return log
