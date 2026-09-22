from __future__ import annotations

from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

import h5py
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset


DATASET_ARCHIVE = "https://github.com/suxrobGM/fsrcnn/archive/refs/heads/main.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_datasets(data_dir: Path) -> dict[str, dict[str, str | int]]:
    """Fetch compact raw T91 and Set5 images and verify image counts."""
    data_dir.mkdir(parents=True, exist_ok=True)
    t91_dir = data_dir / "t91"
    set5_dir = data_dir / "set5"
    if len(list(t91_dir.glob("*"))) != 91 or len(list(set5_dir.glob("*"))) != 5:
        archive_path = data_dir / "fsrcnn_dataset_source.zip"
        if not archive_path.exists():
            request = urllib.request.Request(DATASET_ARCHIVE, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=180) as response, archive_path.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
        t91_dir.mkdir(parents=True, exist_ok=True)
        set5_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                lowered = member.lower()
                target_dir = t91_dir if "/data/t91/" in lowered else set5_dir if "/data/set5/" in lowered else None
                if target_dir is None or member.endswith("/"):
                    continue
                (target_dir / Path(member).name).write_bytes(archive.read(member))
    t91_files = sorted(path for path in t91_dir.iterdir() if path.is_file())
    set5_files = sorted(path for path in set5_dir.iterdir() if path.is_file())
    if len(t91_files) != 91 or len(set5_files) != 5:
        raise RuntimeError(f"Dataset extraction failed: T91={len(t91_files)}, Set5={len(set5_files)}")
    manifest: dict[str, dict[str, str | int]] = {
        "T91": {
            "source": DATASET_ARCHIVE,
            "images": len(t91_files),
            "sha256": hashlib.sha256("".join(sha256_file(path) for path in t91_files).encode()).hexdigest(),
        },
        "Set5": {
            "source": DATASET_ARCHIVE,
            "images": len(set5_files),
            "sha256": hashlib.sha256("".join(sha256_file(path) for path in set5_files).encode()).hexdigest(),
        },
    }
    (data_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


class TrainDataset(Dataset):
    def __init__(self, path: Path, repeat: int = 64, hr_patch: int = 64, seed: int = 123) -> None:
        self.path = Path(path)
        self.repeat = repeat
        self.hr_patch = hr_patch
        self.seed = seed
        if self.path.is_dir():
            self.images = sorted(path for path in self.path.iterdir() if path.is_file())
            self.length = len(self.images) * repeat
        else:
            self.images = []
            with h5py.File(self.path, "r") as handle:
                self.length = len(handle["lr"])

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        if self.images:
            source = Image.open(self.images[index % len(self.images)]).convert("YCbCr").getchannel("Y")
            array = np.asarray(source, dtype=np.uint8)
            rng = np.random.default_rng(self.seed + index)
            patch = min(self.hr_patch, array.shape[0] // 2 * 2, array.shape[1] // 2 * 2)
            patch -= patch % 2
            top = int(rng.integers(0, array.shape[0] - patch + 1))
            left = int(rng.integers(0, array.shape[1] - patch + 1))
            hr = array[top : top + patch, left : left + patch]
            transform = index % 8
            if transform & 1:
                hr = np.fliplr(hr)
            if transform & 2:
                hr = np.flipud(hr)
            if transform & 4:
                hr = np.rot90(hr)
            hr_image = Image.fromarray(np.ascontiguousarray(hr), mode="L")
            lr_image = hr_image.resize((patch // 2, patch // 2), Image.Resampling.BICUBIC)
            lr = np.asarray(lr_image, dtype=np.float32) / 255.0
            hr = np.asarray(hr_image, dtype=np.float32) / 255.0
            return torch.from_numpy(lr[None]), torch.from_numpy(hr[None])
        with h5py.File(self.path, "r") as handle:
            lr = np.asarray(handle["lr"][index], dtype=np.float32) / 255.0
            hr = np.asarray(handle["hr"][index], dtype=np.float32) / 255.0
        return torch.from_numpy(lr[None]), torch.from_numpy(hr[None])


class EvalDataset(Dataset):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if self.path.is_dir():
            self.images = sorted(path for path in self.path.iterdir() if path.is_file())
            self.length = len(self.images)
        else:
            self.images = []
            with h5py.File(self.path, "r") as handle:
                self.length = len(handle["lr"])

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> tuple[str, torch.Tensor, torch.Tensor]:
        if self.images:
            source = Image.open(self.images[index]).convert("YCbCr").getchannel("Y")
            width = source.width - source.width % 2
            height = source.height - source.height % 2
            hr_image = source.crop((0, 0, width, height))
            lr_image = hr_image.resize((width // 2, height // 2), Image.Resampling.BICUBIC)
            lr = np.asarray(lr_image, dtype=np.float32) / 255.0
            hr = np.asarray(hr_image, dtype=np.float32) / 255.0
            return self.images[index].stem, torch.from_numpy(lr[None]), torch.from_numpy(hr[None])
        key = str(index)
        with h5py.File(self.path, "r") as handle:
            lr = np.asarray(handle["lr"][key], dtype=np.float32) / 255.0
            hr = np.asarray(handle["hr"][key], dtype=np.float32) / 255.0
        return key, torch.from_numpy(lr[None]), torch.from_numpy(hr[None])


def procedural_u8(width: int, height: int, seed: int = 123) -> np.ndarray:
    y, x = np.mgrid[0:height, 0:width]
    rng = np.random.default_rng(seed)
    base = 92 + 46 * np.sin(x / 31.0) + 38 * np.cos(y / 23.0)
    rings = 55 * np.sin(np.sqrt((x - width * 0.37) ** 2 + (y - height * 0.61) ** 2) / 8.0)
    checker = (((x // 24 + y // 20) & 1) * 28).astype(np.float64)
    noise = rng.normal(0.0, 2.0, size=(height, width))
    return np.clip(np.rint(base + rings + checker + noise), 0, 255).astype(np.uint8)
