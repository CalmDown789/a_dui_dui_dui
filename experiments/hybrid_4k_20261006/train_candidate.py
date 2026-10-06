from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Iterator

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, Sampler

from .bicubic_reference import _axis_plan
from .candidate_models import HybridFSRCNN, PRESETS


def _load_manifest_pairs(directories: list[Path], limit_per_dir: int = 0) -> list[tuple[Path, str]]:
    records: list[tuple[Path, str]] = []
    for directory in directories:
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pairs = manifest["pairs"]
        if limit_per_dir > 0:
            pairs = pairs[:limit_per_dir]
        records.extend((directory / str(item["pair_file"]), str(item["source_file"])) for item in pairs)
    if not records:
        raise ValueError("No training/validation pairs were found")
    return records


class FramePatchDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(
        self,
        records: list[tuple[Path, str]],
        *,
        patches_per_frame: int,
        patch_size: int,
        seed: int,
        training: bool,
    ) -> None:
        self.records = records
        self.patches_per_frame = patches_per_frame
        self.patch_size = patch_size
        self.seed = seed
        self.training = training
        self.epoch = 0
        self._cached_path: Path | None = None
        self._cached_lr: np.ndarray | None = None
        self._cached_hr: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.records) * self.patches_per_frame

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        frame_index = index // self.patches_per_frame
        patch_index = index % self.patches_per_frame
        pair_path, _ = self.records[frame_index]
        if pair_path != self._cached_path:
            with np.load(pair_path, allow_pickle=False) as pair:
                self._cached_lr = pair["lr_y"].copy()
                self._cached_hr = pair["hr_y"].copy()
            self._cached_path = pair_path
        assert self._cached_lr is not None and self._cached_hr is not None
        lr, hr = self._cached_lr, self._cached_hr
        patch = self.patch_size
        if patch > min(lr.shape):
            raise ValueError(f"Patch {patch} exceeds LR image shape {lr.shape}")
        if self.training:
            rng = np.random.default_rng(self.seed + self.epoch * 1_000_003 + index * 9176)
            top = int(rng.integers(0, lr.shape[0] - patch + 1))
            left = int(rng.integers(0, lr.shape[1] - patch + 1))
        else:
            top = (lr.shape[0] - patch) // 2
            left = (lr.shape[1] - patch) // 2
        lr_patch = lr[top : top + patch, left : left + patch]
        hr_patch = hr[top * 4 : (top + patch) * 4, left * 4 : (left + patch) * 4]
        if self.training:
            turns = int(rng.integers(0, 4))
            if turns:
                lr_patch = np.rot90(lr_patch, turns)
                hr_patch = np.rot90(hr_patch, turns)
            if bool(rng.integers(0, 2)):
                lr_patch = np.flip(lr_patch, axis=1)
                hr_patch = np.flip(hr_patch, axis=1)
            if bool(rng.integers(0, 2)):
                lr_patch = np.flip(lr_patch, axis=0)
                hr_patch = np.flip(hr_patch, axis=0)
        lr_tensor = torch.from_numpy(lr_patch.copy()).float().unsqueeze(0) / 255.0
        hr_tensor = torch.from_numpy(hr_patch.copy()).float().unsqueeze(0) / 255.0
        return lr_tensor, hr_tensor


class FrameBlockSampler(Sampler[int]):
    """Shuffle frames while keeping their patches adjacent for efficient pair IO."""

    def __init__(self, dataset: FramePatchDataset, seed: int) -> None:
        self.dataset = dataset
        self.seed = seed
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __len__(self) -> int:
        return len(self.dataset)

    def __iter__(self) -> Iterator[int]:
        frame_ids = list(range(len(self.dataset.records)))
        random.Random(self.seed + self.epoch).shuffle(frame_ids)
        for frame_id in frame_ids:
            start = frame_id * self.dataset.patches_per_frame
            yield from range(start, start + self.dataset.patches_per_frame)


def _torch_resize_keys2(image: torch.Tensor, *, a: float = -0.5) -> torch.Tensor:
    """Differentiable NCHW Keys bicubic x2, half-pixel coordinates, edge replication."""
    if image.ndim != 4:
        raise ValueError("Expected NCHW tensor")
    height, width = image.shape[-2:]
    y_index, y_weight = _axis_plan(height, 2, a)
    x_index, x_weight = _axis_plan(width, 2, a)
    y_index_t = torch.as_tensor(y_index, device=image.device, dtype=torch.long)
    x_index_t = torch.as_tensor(x_index, device=image.device, dtype=torch.long)
    y_weight_t = torch.as_tensor(y_weight, device=image.device, dtype=image.dtype)
    x_weight_t = torch.as_tensor(x_weight, device=image.device, dtype=image.dtype)
    horizontal = torch.zeros((*image.shape[:-1], width * 2), device=image.device, dtype=image.dtype)
    for tap in range(4):
        selected = image.index_select(-1, x_index_t[:, tap])
        horizontal = horizontal + selected * x_weight_t[:, tap].view(1, 1, 1, -1)
    output = torch.zeros((*image.shape[:-2], height * 2, width * 2), device=image.device, dtype=image.dtype)
    for tap in range(4):
        selected = horizontal.index_select(-2, y_index_t[:, tap])
        output = output + selected * y_weight_t[:, tap].view(1, 1, -1, 1)
    return output


def _fake_u8(values: torch.Tensor) -> torch.Tensor:
    clipped = values.clamp(0.0, 1.0)
    rounded = torch.floor(clipped * 255.0 + 0.5) / 255.0
    return clipped + (rounded - clipped).detach()


def _hybrid_fake_u8(model: nn.Module, lr: torch.Tensor, *, a: float = -0.5) -> torch.Tensor:
    middle = _fake_u8(model(lr))
    return _fake_u8(_torch_resize_keys2(middle, a=a))


def _adapt_state_dict(model: HybridFSRCNN, source: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    target = model.state_dict()
    adapted: dict[str, torch.Tensor] = {}
    for name, target_tensor in target.items():
        if name not in source:
            raise KeyError(f"Initialization checkpoint is missing {name}")
        tensor = source[name]
        if tensor.ndim != target_tensor.ndim or any(src < dst for src, dst in zip(tensor.shape, target_tensor.shape, strict=True)):
            raise ValueError(f"Cannot transfer {name} from {tuple(tensor.shape)} to {tuple(target_tensor.shape)}")
        slices: list[slice] = []
        for axis, (src, dst) in enumerate(zip(tensor.shape, target_tensor.shape, strict=True)):
            if tensor.ndim >= 3 and axis >= tensor.ndim - 2 and src != dst:
                start = (src - dst) // 2
                slices.append(slice(start, start + dst))
            else:
                slices.append(slice(0, dst))
        adapted[name] = tensor[tuple(slices)].clone()
    return adapted


def _select_shrink_channels_by_l1(source: dict[str, torch.Tensor], count: int) -> list[int]:
    shrink = source["shrink.weight"].abs().sum(dim=(1, 2, 3))
    expand_gain = source["expand.weight"].abs().sum(dim=(0, 2, 3))
    mapping_key = "mapping.0.weight"
    mapping_count = len([key for key in source if key.startswith("mapping.") and key.endswith(".weight")])
    if mapping_key not in source or mapping_count != 1:
        raise ValueError("Importance ranking currently requires exactly one mapping layer")
    mapping = source[mapping_key].abs().sum(dim=(2, 3))
    if mapping.shape[0] != mapping.shape[1] or mapping.shape[0] != shrink.numel() or expand_gain.numel() != shrink.numel():
        raise ValueError("Importance pruning expects equal shrink, mapping and expand widths")
    input_contribution = mapping.transpose(0, 1) @ expand_gain
    output_contribution = mapping @ shrink
    scores = shrink * input_contribution + expand_gain * output_contribution
    if count <= 0 or count > scores.numel():
        raise ValueError("Requested channel count is outside the source width")
    return sorted(range(scores.numel()), key=lambda index: (-float(scores[index]), index))[:count]


def _adapt_selected_shrink_channels(
    model: HybridFSRCNN,
    source: dict[str, torch.Tensor],
    channel_indices: list[int],
) -> dict[str, torch.Tensor]:
    if len(channel_indices) != model.config.s or len(set(channel_indices)) != model.config.s:
        raise ValueError(f"Expected {model.config.s} unique shrink-channel indices")
    if any(index < 0 or index >= source["shrink.weight"].shape[0] for index in channel_indices):
        raise ValueError("Shrink-channel index is outside the source width")
    source_mapping_count = len([key for key in source if key.startswith("mapping.") and key.endswith(".weight")])
    if source_mapping_count != model.config.m:
        raise ValueError("Source and target mapping depths must match for structured channel pruning")

    indices = torch.tensor(channel_indices, dtype=torch.long)
    adapted = _adapt_state_dict(model, source)
    adapted["shrink.weight"] = source["shrink.weight"].index_select(0, indices)[:, : model.config.d].clone()
    adapted["shrink.bias"] = source["shrink.bias"].index_select(0, indices).clone()
    adapted["shrink_act.weight"] = source["shrink_act.weight"].index_select(0, indices).clone()
    for layer_index in range(model.config.m):
        prefix = f"mapping.{layer_index}"
        weight = source[f"{prefix}.weight"]
        adapted[f"{prefix}.weight"] = weight.index_select(0, indices).index_select(1, indices).clone()
        adapted[f"{prefix}.bias"] = source[f"{prefix}.bias"].index_select(0, indices).clone()
        adapted[f"mapping_act.{layer_index}.weight"] = source[f"mapping_act.{layer_index}.weight"].index_select(0, indices).clone()
    adapted["expand.weight"] = source["expand.weight"].index_select(1, indices).clone()
    return adapted


def _set_trainable_scope(model: HybridFSRCNN, output_head_only: bool) -> None:
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(not output_head_only or name.startswith("subpixel."))
    if not any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("Training scope selected no trainable parameters")


def _mean_mse(model: nn.Module, loader: DataLoader, device: torch.device, border: int) -> float:
    model.eval()
    loss_sum = 0.0
    image_count = 0
    with torch.no_grad():
        for lr, hr in loader:
            lr = lr.to(device, non_blocking=True)
            hr = hr.to(device, non_blocking=True)
            prediction = _hybrid_fake_u8(model, lr)
            margin = border * 4
            prediction = prediction[..., margin:-margin, margin:-margin]
            hr = hr[..., margin:-margin, margin:-margin]
            loss_sum += float(torch.mean((prediction - hr) ** 2).item()) * lr.shape[0]
            image_count += int(lr.shape[0])
    return loss_sum / image_count


def _inside_data(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Training artifacts must be written under ignored .data/: {resolved}") from exc
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a separate FSRCNN candidate against the full 4K hybrid output")
    parser.add_argument("--train-pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--validation-pairs-dir", type=Path, required=True)
    parser.add_argument("--initial-checkpoint", type=Path, required=True)
    parser.add_argument("--distill-checkpoint", type=Path)
    parser.add_argument("--distill-weight", type=float, default=0.0)
    parser.add_argument("--variant", choices=tuple(PRESETS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patches-per-frame", type=int, default=2)
    parser.add_argument("--patch-size", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument(
        "--train-output-head-only",
        action="store_true",
        help="Freeze the shared FSRCNN trunk and fine-tune only the subpixel output convolution",
    )
    parser.add_argument(
        "--importance-prune-shrink-channels",
        action="store_true",
        help="When narrowing s, rank source channels by shrink/mapping/expand L1 contribution before weight transfer",
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--border", type=int, default=8, help="Exclude this many LR pixels from patch-edge loss")
    parser.add_argument("--limit-train-per-dir", type=int, default=0)
    parser.add_argument("--limit-validation", type=int, default=0)
    args = parser.parse_args()
    if min(args.epochs, args.patches_per_frame, args.patch_size, args.batch_size) <= 0:
        raise ValueError("epochs, patches-per-frame, patch-size and batch-size must be positive")
    if args.patch_size <= args.border * 2:
        raise ValueError("patch-size must be larger than twice the loss border")
    if args.distill_weight < 0 or (args.distill_weight > 0 and args.distill_checkpoint is None):
        raise ValueError("A positive distill weight requires --distill-checkpoint")

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = _inside_data(args.output_dir, repo_root)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    train_records = _load_manifest_pairs(args.train_pairs_dir, args.limit_train_per_dir)
    val_records = _load_manifest_pairs([args.validation_pairs_dir], args.limit_validation)
    train_dataset = FramePatchDataset(
        train_records,
        patches_per_frame=args.patches_per_frame,
        patch_size=args.patch_size,
        seed=args.seed,
        training=True,
    )
    val_dataset = FramePatchDataset(
        val_records,
        patches_per_frame=1,
        patch_size=args.patch_size,
        seed=args.seed,
        training=False,
    )
    sampler = FrameBlockSampler(train_dataset, args.seed)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, sampler=sampler, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = HybridFSRCNN(PRESETS[args.variant])
    initial = torch.load(args.initial_checkpoint, map_location="cpu", weights_only=False)
    initial_state = initial.get("state_dict", initial.get("model_state_dict", initial))
    if args.importance_prune_shrink_channels:
        selected_channels = _select_shrink_channels_by_l1(initial_state, model.config.s)
        initial_state = _adapt_selected_shrink_channels(model, initial_state, selected_channels)
    else:
        selected_channels = None
        initial_state = _adapt_state_dict(model, initial_state)
    model.load_state_dict(initial_state, strict=True)
    _set_trainable_scope(model, args.train_output_head_only)
    model.to(device)
    teacher: HybridFSRCNN | None = None
    if args.distill_checkpoint is not None:
        teacher_checkpoint = torch.load(args.distill_checkpoint, map_location="cpu", weights_only=False)
        teacher_state = teacher_checkpoint.get("state_dict", teacher_checkpoint.get("model_state_dict", teacher_checkpoint))
        teacher = HybridFSRCNN(PRESETS["R0"])
        teacher.load_state_dict(teacher_state, strict=True)
        teacher.to(device).eval()
        for parameter in teacher.parameters():
            parameter.requires_grad_(False)
    optimizer = torch.optim.Adam((parameter for parameter in model.parameters() if parameter.requires_grad), lr=args.learning_rate)
    scheduler = torch.optim.lr_scheduler.MultiStepLR(
        optimizer,
        milestones=sorted(set([max(1, args.epochs // 2), max(1, (args.epochs * 3) // 4)])),
        gamma=0.5,
    )
    history: list[dict[str, float | int]] = []
    best_val = math.inf
    best_path = output_dir / f"{args.variant.lower()}_best.pth"
    history_path = output_dir / "training_log.csv"
    hyperparameters = {
        "epochs_requested": args.epochs,
        "patches_per_frame": args.patches_per_frame,
        "patch_size_lr": args.patch_size,
        "batch_size": args.batch_size,
        "initial_learning_rate": args.learning_rate,
        "loss_border_lr_pixels": args.border,
        "seed": args.seed,
        "trainable_scope": "subpixel_output_head_only" if args.train_output_head_only else "all_parameters",
        "importance_prune_shrink_channels": selected_channels,
        "augmentation": "random 90-degree rotation and independent horizontal/vertical flips, paired across LR/HR",
    }

    for epoch in range(args.epochs):
        train_dataset.set_epoch(epoch)
        sampler.set_epoch(epoch)
        model.train()
        batch_losses: list[float] = []
        for lr, hr in train_loader:
            lr = lr.to(device, non_blocking=True)
            hr = hr.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            prediction = _hybrid_fake_u8(model, lr)
            margin = args.border * 4
            prediction = prediction[..., margin:-margin, margin:-margin]
            target = hr[..., margin:-margin, margin:-margin]
            target_loss = torch.mean((prediction - target) ** 2)
            loss = target_loss
            if teacher is not None and args.distill_weight > 0:
                with torch.no_grad():
                    teacher_output = _hybrid_fake_u8(teacher, lr)[..., margin:-margin, margin:-margin]
                loss = loss + args.distill_weight * torch.mean((prediction - teacher_output) ** 2)
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach().item()))
        scheduler.step()
        val_mse = _mean_mse(model, val_loader, device, args.border)
        row: dict[str, float | int] = {
            "epoch": epoch + 1,
            "train_mse": float(np.mean(batch_losses)),
            "validation_mse": val_mse,
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if val_mse < best_val:
            best_val = val_mse
            torch.save(
                {
                    "state_dict": model.cpu().state_dict(),
                    "variant": args.variant,
                    "config": PRESETS[args.variant].to_dict(),
                    "epoch": epoch + 1,
                    "validation_mse": val_mse,
                    "seed": args.seed,
                    "hyperparameters": hyperparameters,
                    "distill_checkpoint": str(args.distill_checkpoint.resolve()) if args.distill_checkpoint else None,
                    "distill_weight": args.distill_weight,
                    "training_protocol": "FP32 network + straight-through uint8 middle/final rounding + differentiable Keys bicubic x2 a=-0.5; full hybrid 4K MSE; UVG decoded HEVC pairs",
                },
                best_path,
            )
            model.to(device)
        with history_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(history[0]))
            writer.writeheader()
            writer.writerows(history)

    summary = {
        "schema": "member-a-hybrid-4k-training-run-v1",
        "status": "EXPERIMENTAL_NOT_FROZEN_OR_INTEGER_DEPLOYMENT",
        "variant": args.variant,
        "config": PRESETS[args.variant].to_dict(),
        "initial_checkpoint": str(args.initial_checkpoint.resolve()),
        "initial_checkpoint_sha256": hashlib.sha256(args.initial_checkpoint.read_bytes()).hexdigest(),
        "distill_checkpoint": str(args.distill_checkpoint.resolve()) if args.distill_checkpoint else None,
        "distill_weight": args.distill_weight,
        "hyperparameters": hyperparameters,
        "train_manifests": [
            {
                "path": str((path / "manifest.json").resolve()),
                "sha256": hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest(),
            }
            for path in args.train_pairs_dir
        ],
        "validation_manifest": {
            "path": str((args.validation_pairs_dir / "manifest.json").resolve()),
            "sha256": hashlib.sha256((args.validation_pairs_dir / "manifest.json").read_bytes()).hexdigest(),
        },
        "train_sources": [str(path.resolve()) for path in args.train_pairs_dir],
        "validation_source": str(args.validation_pairs_dir.resolve()),
        "train_frames": len(train_records),
        "validation_frames": len(val_records),
        "epochs_completed": len(history),
        "best_validation_mse": best_val,
        "best_epoch": int(min(history, key=lambda item: float(item["validation_mse"]))["epoch"]),
        "best_checkpoint": str(best_path),
        "best_checkpoint_sha256": hashlib.sha256(best_path.read_bytes()).hexdigest(),
        "training_log": str(history_path),
        "device": str(device),
        "seed": args.seed,
        "limitations": [
            "Training and validation are separated by UVG sequence; all source video is lossy HEVC-decoded Y8.",
            "The experiment uses synthetic x4 bicubic degradation, not a native 540p camera reference.",
            "This is a floating-point software candidate only; it does not establish quantized quality or FPGA timing/resources.",
        ],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
