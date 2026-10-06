"""Controlled 20-epoch fine-tuning: fixed crops vs epoch-resampled crops.

The official checkpoint is read-only. All candidate files go to .data/.
"""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import sys

import torch
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from epoch_resampled_dataset import EpochResampledTrainDataset
from member_a.data import EvalDataset, TrainDataset
from member_a.model import FSRCNNSubpixel
from member_a.training import evaluate_model, seed_everything


BASE_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
BASE_T91_SHA256 = "d903f5e8e3c43c92fc5009d33378de41a3a651d05cd86f79339843ebaf7af65c"
BASE_SET5_SHA256 = "b9cbe9ec0e9b09f440d75f73870598005439f54d4b9dc8a33e801fd2ecb3d79e"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def train_arm(
    name: str,
    resample: bool,
    root: Path,
    data_dir: Path,
    base_checkpoint: Path,
    output_dir: Path,
    epochs: int,
    seed: int,
    device: torch.device,
) -> dict:
    seed_everything(seed)
    output_dir.mkdir(parents=True, exist_ok=False)
    saved = torch.load(base_checkpoint, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    model.to(device)

    train_class = EpochResampledTrainDataset if resample else TrainDataset
    train_set = train_class(data_dir / "t91", seed=seed)
    eval_set = EvalDataset(data_dir / "set5")
    loader = DataLoader(
        train_set,
        batch_size=16,
        shuffle=True,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    optimizer = torch.optim.Adam(
        [
            {"params": [p for key, p in model.named_parameters() if not key.startswith("subpixel.")], "lr": 1.0e-4},
            {"params": model.subpixel.parameters(), "lr": 1.0e-5},
        ]
    )
    criterion = torch.nn.MSELoss()
    _, initial = evaluate_model(model, eval_set, device)
    best_psnr = initial["fp32_psnr_db"]
    best_state = deepcopy(model.state_dict())
    best_epoch = 0
    log: list[dict] = []

    for epoch in range(epochs):
        if resample:
            train_set.set_epoch(epoch)
        started = time.perf_counter()
        model.train()
        total_loss = 0.0
        samples = 0
        for inputs, labels in loader:
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * inputs.shape[0]
            samples += inputs.shape[0]

        _, metrics = evaluate_model(model, eval_set, device)
        elapsed = time.perf_counter() - started
        row = {
            "epoch": epoch + 1,
            "mse_loss": total_loss / max(samples, 1),
            "set5_psnr_db": metrics["fp32_psnr_db"],
            "set5_ssim": metrics["fp32_ssim"],
            "epoch_seconds": elapsed,
        }
        log.append(row)
        if metrics["fp32_psnr_db"] > best_psnr:
            best_psnr = metrics["fp32_psnr_db"]
            best_state = deepcopy(model.state_dict())
            best_epoch = epoch + 1
        print(
            f"{name} epoch={epoch + 1}/{epochs} mse={row['mse_loss']:.7f} "
            f"Set5={row['set5_psnr_db']:.4f}dB elapsed={elapsed:.1f}s",
            flush=True,
        )

    model.load_state_dict(best_state)
    checkpoint_out = output_dir / "candidate_fp32.pth"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": model.config.to_dict(),
            "seed": seed,
            "fine_tune_epochs": epochs,
            "best_set5_psnr_db": best_psnr,
            "best_epoch": best_epoch,
            "parent_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
            "experiment": name,
            "crop_policy": "epoch_resampled" if resample else "fixed_per_index",
            "optimizer": "Adam; lr=1e-4 backbone, 1e-5 subpixel; MSE",
        },
        checkpoint_out,
    )
    with (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(log[0]))
        writer.writeheader()
        writer.writerows(log)
    summary = {
        "name": name,
        "crop_policy": "epoch_resampled" if resample else "fixed_per_index",
        "initial_set5_psnr_db": initial["fp32_psnr_db"],
        "best_set5_psnr_db": best_psnr,
        "best_epoch": best_epoch,
        "checkpoint": str(checkpoint_out.relative_to(root)),
        "checkpoint_sha256": file_sha(checkpoint_out),
        "mean_epoch_seconds": sum(row["epoch_seconds"] for row in log) / len(log),
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/dynamic_crop_ab_20e")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    base_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    if file_sha(base_checkpoint) != BASE_CHECKPOINT_SHA256:
        parser.error("Frozen baseline checkpoint hash mismatch; refusing to train against changed assets")
    if not (data_dir / "dataset_manifest.json").is_file():
        parser.error("Dataset manifest missing; prepare verified T91 and Set5 first")
    manifest = json.loads((data_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("T91", {}).get("sha256") != BASE_T91_SHA256:
        parser.error("T91 files do not match the frozen training source collection")
    if manifest.get("Set5", {}).get("sha256") != BASE_SET5_SHA256:
        parser.error("Set5 files do not match the frozen validation source collection")
    if args.epochs <= 0:
        parser.error("--epochs must be positive")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty experiment directory: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    run_manifest = {
        "schema": "member-a-dynamic-crop-ab-experiment-v1",
        "status": "RUNNING",
        "source_commit": __import__("subprocess").check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "baseline_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "model_config": "FSRCNNSubpixel d16/s8/m1/c16 x2",
        "dataset_manifest": manifest,
        "device": str(device),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "seed": args.seed,
        "epochs": args.epochs,
        "controlled_change": "crop and dihedral transform resampled deterministically each epoch",
        "shared_settings": "same frozen initialization, T91, MSE, Adam, batch 16, fixed LR 1e-4/1e-5",
        "independent_evaluation": "BBB frames 1440..1524; do not use these scores for per-epoch selection",
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    try:
        results = [
            train_arm("fixed_crop_control", False, ROOT, data_dir, base_checkpoint,
                      output_dir / "fixed_crop_control", args.epochs, args.seed, device),
            train_arm("epoch_resampled_crop", True, ROOT, data_dir, base_checkpoint,
                      output_dir / "epoch_resampled_crop", args.epochs, args.seed, device),
        ]
        run_manifest["status"] = "TRAINED"
        run_manifest["arms"] = results
    except BaseException as error:
        run_manifest["status"] = "TRAINING_FAILED"
        run_manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output_dir / "run_manifest.json").write_text(
            json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
