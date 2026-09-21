from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter
from torch.utils.data import Dataset


def _procedural_hr(index: int, width: int = 1280, height: int = 720) -> Image.Image:
    """Create a deterministic naturalistic grayscale frame without external downloads."""
    rng = np.random.default_rng(1000 + index)
    yy, xx = np.mgrid[0:height, 0:width]
    base = 0.42 + 0.20 * np.sin((xx + 31 * index) / (35.0 + index))
    base += 0.15 * np.cos((yy + 17 * index) / (27.0 + 0.5 * index))
    base += 0.08 * np.sin((xx + yy) / (11.0 + index % 5))
    radial = np.sqrt((xx - width * (0.25 + 0.04 * (index % 5))) ** 2 + (yy - height * 0.55) ** 2)
    base += 0.12 * np.cos(radial / (8.0 + index % 7))
    # Keep a small sensor-like perturbation, but avoid making the held-out HR
    # target dominated by information that no 2x model can reconstruct.
    noise = rng.normal(0.0, 0.003, size=(height, width))
    arr = np.clip(base + noise, 0.0, 1.0)
    img = Image.fromarray(np.uint8(np.rint(arr * 255.0)), mode="L")
    draw = ImageDraw.Draw(img)
    for j in range(18):
        x0 = int(rng.integers(0, width - 120))
        y0 = int(rng.integers(0, height - 80))
        x1 = min(width - 1, x0 + int(rng.integers(30, 260)))
        y1 = min(height - 1, y0 + int(rng.integers(20, 180)))
        shade = int(rng.integers(20, 236))
        if j % 3 == 0:
            draw.rectangle((x0, y0, x1, y1), outline=shade, width=int(rng.integers(1, 6)))
        elif j % 3 == 1:
            draw.ellipse((x0, y0, x1, y1), outline=shade, width=int(rng.integers(1, 6)))
        else:
            draw.line((x0, y0, x1, y1), fill=shade, width=int(rng.integers(1, 5)))
    if index % 2:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.35 + 0.1 * (index % 3)))
    return img


def generate_paired_dataset(root: Path, train_count: int = 8, val_count: int = 3) -> dict:
    root = Path(root)
    counts = {"train": train_count, "val": val_count}
    for split, count in counts.items():
        (root / split / "lr").mkdir(parents=True, exist_ok=True)
        (root / split / "hr").mkdir(parents=True, exist_ok=True)
        offset = 0 if split == "train" else train_count
        for i in range(count):
            hr = _procedural_hr(offset + i)
            lr = hr.resize((640, 360), Image.Resampling.BICUBIC)
            stem = f"{split}_{i:02d}"
            hr.save(root / split / "hr" / f"{stem}_hr.png", optimize=True)
            lr.save(root / split / "lr" / f"{stem}_lr.png", optimize=True)
    return {"train_pairs": train_count, "val_pairs": val_count, "lr_size": [640, 360], "hr_size": [1280, 720]}


def _load_gray(path: Path) -> torch.Tensor:
    arr = np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


class PairedPatchDataset(Dataset):
    def __init__(self, root: Path, patch_lr: int = 48, samples_per_epoch: int = 512, seed: int = 20260920):
        self.root = Path(root)
        self.patch_lr = int(patch_lr)
        self.samples_per_epoch = int(samples_per_epoch)
        self.seed = int(seed)
        self.lr_paths = sorted((self.root / "train" / "lr").glob("*.png"))
        self.hr_paths = sorted((self.root / "train" / "hr").glob("*.png"))
        if len(self.lr_paths) != len(self.hr_paths) or not self.lr_paths:
            raise RuntimeError("Paired dataset is missing or mismatched")
        self._lr = [_load_gray(p) for p in self.lr_paths]
        self._hr = [_load_gray(p) for p in self.hr_paths]

    def __len__(self) -> int:
        return self.samples_per_epoch

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        rng = random.Random(self.seed + index * 7919)
        k = rng.randrange(len(self._lr))
        lr, hr = self._lr[k], self._hr[k]
        _, h, w = lr.shape
        y = rng.randrange(0, h - self.patch_lr + 1)
        x = rng.randrange(0, w - self.patch_lr + 1)
        lr_patch = lr[:, y : y + self.patch_lr, x : x + self.patch_lr].clone()
        hr_patch = hr[:, 2 * y : 2 * (y + self.patch_lr), 2 * x : 2 * (x + self.patch_lr)].clone()
        if rng.random() < 0.5:
            lr_patch = torch.flip(lr_patch, dims=(-1,))
            hr_patch = torch.flip(hr_patch, dims=(-1,))
        if rng.random() < 0.5:
            lr_patch = torch.flip(lr_patch, dims=(-2,))
            hr_patch = torch.flip(hr_patch, dims=(-2,))
        rotations = rng.randrange(4)
        if rotations:
            lr_patch = torch.rot90(lr_patch, rotations, dims=(-2, -1))
            hr_patch = torch.rot90(hr_patch, rotations, dims=(-2, -1))
        return lr_patch.contiguous(), hr_patch.contiguous()


def load_validation_pairs(root: Path) -> list[tuple[str, torch.Tensor, torch.Tensor]]:
    root = Path(root)
    lr_paths = sorted((root / "val" / "lr").glob("*.png"))
    hr_paths = sorted((root / "val" / "hr").glob("*.png"))
    if len(lr_paths) != len(hr_paths):
        raise RuntimeError("Validation dataset is mismatched")
    return [(lr.stem.replace("_lr", ""), _load_gray(lr), _load_gray(hr)) for lr, hr in zip(lr_paths, hr_paths)]
