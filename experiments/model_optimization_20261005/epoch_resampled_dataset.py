"""Deterministic, epoch-varying crops for the frozen FSRCNN training set."""
from __future__ import annotations

import numpy as np
from PIL import Image

from member_a.data import TrainDataset


class EpochResampledTrainDataset(TrainDataset):
    """Reuse the same T91 images, but draw a new crop/dihedral transform per epoch.

    Epoch zero exactly matches the existing TrainDataset samples. Later epochs
    are deterministic for a given (seed, epoch, index), so runs remain replayable.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.images:
            raise ValueError("Epoch-resampled mode currently requires an image directory")
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        if epoch < 0:
            raise ValueError("epoch must be nonnegative")
        self.epoch = int(epoch)

    def __getitem__(self, index: int):
        if self.epoch == 0:
            return super().__getitem__(index)

        source = Image.open(self.images[index % len(self.images)]).convert("YCbCr").getchannel("Y")
        array = np.asarray(source, dtype=np.uint8)
        rng = np.random.default_rng(self.seed + self.epoch * len(self) + index)
        patch = min(self.hr_patch, array.shape[0] // 2 * 2, array.shape[1] // 2 * 2)
        patch -= patch % 2
        top = int(rng.integers(0, array.shape[0] - patch + 1))
        left = int(rng.integers(0, array.shape[1] - patch + 1))
        hr = array[top : top + patch, left : left + patch]
        transform = int(rng.integers(0, 8))
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
        import torch

        return torch.from_numpy(lr[None]), torch.from_numpy(hr[None])
