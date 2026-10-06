from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
import torch
from torch.utils.data import DataLoader

from member_a.quantization import calibrate_activation_scales
from member_a.training import qat_forward
from .candidate_models import HybridFSRCNN, PRESETS
from .train_candidate import (
    FrameBlockSampler,
    FramePatchDataset,
    _fake_u8,
    _load_manifest_pairs,
    _torch_resize_keys2,
)


def _inside_data(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"QAT outputs must remain under ignored .data/: {resolved}") from exc
    return resolved


@torch.no_grad()
def _validate(model, loader, scales, device, border: int) -> float:
    model.eval()
    total = 0.0
    count = 0
    for lr, hr in loader:
        lr = lr.to(device)
        hr = hr.to(device)
        mid = qat_forward(model, lr, scales)
        pred = _fake_u8(_torch_resize_keys2(mid, a=-0.5))
        margin = border * 4
        loss = torch.mean((pred[..., margin:-margin, margin:-margin] - hr[..., margin:-margin, margin:-margin]) ** 2)
        total += float(loss.item()) * int(lr.shape[0])
        count += int(lr.shape[0])
    return total / max(count, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QAT on a separate experimental candidate")
    parser.add_argument("--variant", choices=sorted(PRESETS), default="R0")
    parser.add_argument("--initial-checkpoint", type=Path, required=True)
    parser.add_argument("--train-pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--validation-pairs-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--patches-per-frame", type=int, default=2)
    parser.add_argument("--patch-size", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1.0e-5)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--border", type=int, default=8)
    args = parser.parse_args()
    if min(args.epochs, args.patches_per_frame, args.patch_size, args.batch_size) <= 0:
        raise ValueError("epochs, patches-per-frame, patch-size and batch-size must be positive")
    if args.patch_size <= args.border * 2:
        raise ValueError("patch-size must exceed twice the loss border")

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = _inside_data(args.output_dir, repo_root)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    if not args.initial_checkpoint.is_file():
        raise FileNotFoundError(args.initial_checkpoint)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.set_num_threads(4)

    train_records = _load_manifest_pairs([path.resolve() for path in args.train_pairs_dir])
    val_records = _load_manifest_pairs([args.validation_pairs_dir.resolve()])
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
    checkpoint = torch.load(args.initial_checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model = HybridFSRCNN(PRESETS[args.variant])
    model.load_state_dict(state, strict=True)
    model.to(device)
    calibration_samples = []
    for pair_path, _source_file in val_records:
        with np.load(pair_path, allow_pickle=False) as pair:
            lr_y = pair["lr_y"].copy().astype(np.float32) / 255.0
        calibration_samples.append(torch.from_numpy(lr_y)[None, None])
    scales = calibrate_activation_scales(model, calibration_samples, device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    model.train()
    history: list[dict[str, float | int]] = []
    best_val = math.inf
    best_path = output_dir / ("r0_qat_best.pth" if args.variant == "R0" else f"{args.variant.lower()}_qat_best.pth")
    for epoch in range(args.epochs):
        train_dataset.set_epoch(epoch)
        sampler.set_epoch(epoch)
        model.train()
        losses: list[float] = []
        for lr, hr in train_loader:
            lr = lr.to(device)
            hr = hr.to(device)
            optimizer.zero_grad(set_to_none=True)
            mid = qat_forward(model, lr, scales)
            pred = _fake_u8(_torch_resize_keys2(mid, a=-0.5))
            margin = args.border * 4
            loss = torch.mean((pred[..., margin:-margin, margin:-margin] - hr[..., margin:-margin, margin:-margin]) ** 2)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().item()))
        val_mse = _validate(model, val_loader, scales, device, args.border)
        row = {
            "epoch": epoch + 1,
            "train_mse": float(np.mean(losses)),
            "validation_fake_quant_mse": val_mse,
            "learning_rate": args.learning_rate,
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if val_mse < best_val:
            best_val = val_mse
            torch.save(
                {
                    "state_dict": model.cpu().state_dict(),
                    "variant": args.variant,
                    "config": model.config.to_dict(),
                    "seed": args.seed,
                    "qat_epochs_requested": args.epochs,
                    "best_validation_fake_quant_mse": best_val,
                    "activation_scales": scales,
                    "initial_checkpoint": str(args.initial_checkpoint.resolve()),
                    "initial_checkpoint_sha256": hashlib.sha256(args.initial_checkpoint.read_bytes()).hexdigest(),
                    "train_manifests": [
                        {
                            "path": str((path.resolve() / "manifest.json")),
                            "sha256": hashlib.sha256((path.resolve() / "manifest.json").read_bytes()).hexdigest(),
                        }
                        for path in args.train_pairs_dir
                    ],
                    "validation_manifest_sha256": hashlib.sha256(
                        (args.validation_pairs_dir.resolve() / "manifest.json").read_bytes()
                    ).hexdigest(),
                    "training_protocol": "STE fake quant INT8 weights, calibrated INT16 hidden activations, Q15 PReLU, UINT8 output; full 4K hybrid MSE",
                },
                best_path,
            )
            model.to(device)
        with (output_dir / "qat_training_log.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(history[0]))
            writer.writeheader()
            writer.writerows(history)

    summary = {
        "schema": "member-a-candidate-qat-run-v1",
        "status": "EXPERIMENTAL_NOT_FORMAL_A_DELIVERY",
        "variant": f"{args.variant} candidate {PRESETS[args.variant].d}/{PRESETS[args.variant].s}/m{PRESETS[args.variant].m}/c{PRESETS[args.variant].c} head{PRESETS[args.variant].head_kernel}x{PRESETS[args.variant].head_kernel}",
        "initial_checkpoint": str(args.initial_checkpoint.resolve()),
        "initial_checkpoint_sha256": hashlib.sha256(args.initial_checkpoint.read_bytes()).hexdigest(),
        "train_frames": len(train_records),
        "validation_frames": len(val_records),
        "epochs_completed": len(history),
        "seed": args.seed,
        "learning_rate": args.learning_rate,
        "patch_size_lr": args.patch_size,
        "patches_per_frame": args.patches_per_frame,
        "batch_size": args.batch_size,
        "best_epoch": int(min(history, key=lambda row: float(row["validation_fake_quant_mse"]))["epoch"]),
        "best_validation_fake_quant_mse": best_val,
        "checkpoint": str(best_path),
        "checkpoint_sha256": hashlib.sha256(best_path.read_bytes()).hexdigest(),
        "training_log": str(output_dir / "qat_training_log.csv"),
        "device": str(device),
        "limitations": [
            "QAT candidate is a separate experimental model and does not alter frozen A assets.",
            "Validation and training use synthetic FFmpeg bicubic pairs derived from lossy UVG HEVC.",
            "QAT validation MSE is not a substitute for exact integer-reference full-frame PSNR/SSIM evaluation.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
