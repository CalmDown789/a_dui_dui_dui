"""Fine-tune the frozen integer model with diverse DIV2K/T91 patches and QAT."""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Subset, TensorDataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from member_a.data import EvalDataset
from member_a.model import FSRCNNSubpixel
from member_a.quantization import calibrate_activation_scales
from member_a.training import evaluate_model, qat_forward, seed_everything


BASE_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
BASE_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"
T91_SHA256 = "d903f5e8e3c43c92fc5009d33378de41a3a651d05cd86f79339843ebaf7af65c"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--div2k-dir", type=Path, default=ROOT / ".data/model_optimization/datasets/div2k")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--learning-rate", type=float, default=3.0e-6)
    parser.add_argument("--fp32-loss-weight", type=float, default=0.25)
    args = parser.parse_args()

    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant_json = ROOT / "artifacts/quant/quant_params.json"
    div_manifest_path = args.div2k_dir.resolve() / "manifest.json"
    if file_sha(frozen_checkpoint) != BASE_CHECKPOINT_SHA256 or file_sha(frozen_quant_json) != BASE_QUANT_SHA256:
        parser.error("Frozen model or quantization asset hash mismatch")
    t91_manifest = json.loads((args.data_dir.resolve() / "dataset_manifest.json").read_text(encoding="utf-8"))
    if t91_manifest.get("T91", {}).get("sha256") != T91_SHA256:
        parser.error("T91 dataset hash mismatch")
    if not div_manifest_path.is_file():
        parser.error("DIV2K manifest missing; run prepare_div2k_hr.py first")
    div_manifest = json.loads(div_manifest_path.read_text(encoding="utf-8"))
    if div_manifest.get("image_count") != 800 or div_manifest.get("internal_split", {}).get("training_images") != 720:
        parser.error("DIV2K images/split do not match the expected 720/80 verified split")
    if args.epochs <= 0 or args.learning_rate <= 0 or args.fp32_loss_weight < 0:
        parser.error("Invalid training hyperparameters")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty experiment folder: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(args.seed)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    t91_files = sorted(path for path in (args.data_dir.resolve() / "t91").iterdir() if path.is_file())
    div2k_files = sorted((args.div2k_dir.resolve() / "split/train_hr").glob("*.png"))
    if len(t91_files) != 91 or len(div2k_files) != 720:
        parser.error(f"Unexpected training image counts: T91={len(t91_files)}, DIV2K={len(div2k_files)}")
    validation_all = EvalDataset(args.div2k_dir.resolve() / "split/validation_hr")
    validation = Subset(validation_all, list(range(0, len(validation_all), 4)))
    model = FSRCNNSubpixel()
    baseline_saved = torch.load(frozen_checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(baseline_saved["state_dict"], strict=True)
    model.to(device).eval()
    calibration_lr, _ = build_patch_tensors(t91_files[:16], repeat=1, seed=args.seed, epoch=0)
    calibration_lr_div2k, _ = build_patch_tensors(div2k_files[:16], repeat=1, seed=args.seed + 1, epoch=0)
    calibration_samples = [item.unsqueeze(0) for item in torch.cat([calibration_lr, calibration_lr_div2k], dim=0)]
    qat_training_scales = calibrate_activation_scales(model, calibration_samples, device)

    rows: list[dict] = []
    best_metric = -float("inf")
    best_state = deepcopy(model.state_dict())
    best_epoch = 0
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    criterion = torch.nn.MSELoss()
    manifest = {
        "schema": "member-a-div2k-qat-experiment-v1",
        "status": "RUNNING",
        "parent_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "frozen_quant_params_sha256": BASE_QUANT_SHA256,
        "T91_collection_sha256": T91_SHA256,
        "DIV2K_manifest": div_manifest,
        "device": str(device),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "seed": args.seed,
        "epochs": args.epochs,
        "batch_size": 16,
        "lr": args.learning_rate,
        "fp32_loss_weight": args.fp32_loss_weight,
        "samples_per_epoch": 91 * 32 + 720 * 4,
        "training_mix": "T91 repeat=32 plus DIV2K train IDs 0001-0720 repeat=4; new deterministic crop/dihedral each epoch",
        "quant_calibration": "32 deterministic HR patches sampled only from training set",
        "checkpoint_selection": "QDQ quantized PSNR on 20 internal DIV2K IDs 0721-0800; held out from training/calibration",
        "validation_scope": "selection split, not final independent acceptance",
    }
    save_json(output_dir / "run_manifest.json", manifest)
    for epoch in range(args.epochs):
        started = time.perf_counter()
        prepare_started = time.perf_counter()
        train_lr_t91, train_hr_t91 = build_patch_tensors(t91_files, repeat=32, seed=args.seed, epoch=epoch)
        train_lr_div2k, train_hr_div2k = build_patch_tensors(
            div2k_files, repeat=4, seed=args.seed + 1, epoch=epoch
        )
        train_dataset = TensorDataset(
            torch.cat([train_lr_t91, train_lr_div2k]),
            torch.cat([train_hr_t91, train_hr_div2k]),
        )
        loader = DataLoader(train_dataset, batch_size=16, shuffle=True, num_workers=0,
                            pin_memory=device.type == "cuda")
        print(f"epoch {epoch + 1}: prepared {len(train_dataset)} patches in {time.perf_counter() - prepare_started:.1f}s", flush=True)
        model.train()
        total_qat = 0.0
        total_fp = 0.0
        count = 0
        for inputs, labels in loader:
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            qat_prediction = qat_forward(model, inputs, qat_training_scales)
            fp_prediction = model(inputs).clamp(0.0, 1.0)
            qat_loss = criterion(qat_prediction, labels)
            fp_loss = criterion(fp_prediction, labels)
            loss = qat_loss + args.fp32_loss_weight * fp_loss
            loss.backward()
            optimizer.step()
            batch_count = inputs.shape[0]
            total_qat += float(qat_loss.detach().item()) * batch_count
            total_fp += float(fp_loss.detach().item()) * batch_count
            count += batch_count
        model.eval()
        validation_scales = calibrate_activation_scales(model, calibration_samples, device)
        _, val = evaluate_model(model, validation, device, validation_scales)
        row = {
            "epoch": epoch + 1,
            "training_qat_mse": total_qat / count,
            "training_fp32_mse": total_fp / count,
            "validation_qdq_psnr_db": val["quant_psnr_db"],
            "validation_qdq_ssim": val["quant_ssim"],
            "validation_fp32_psnr_db": val["fp32_psnr_db"],
            "validation_fp32_ssim": val["fp32_ssim"],
            "epoch_seconds": time.perf_counter() - started,
        }
        rows.append(row)
        if val["quant_psnr_db"] > best_metric:
            best_metric = val["quant_psnr_db"]
            best_state = deepcopy(model.state_dict())
            best_epoch = epoch + 1
            checkpoint = output_dir / "candidate_qat_fp32.pth"
            torch.save({
                "state_dict": best_state,
                "config": model.config.to_dict(),
                "seed": args.seed,
                "epoch": best_epoch,
                "best_internal_validation_qdq_psnr_db": best_metric,
                "parent_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
                "experiment": "DIV2K+T91 mixed QAT with FP32 auxiliary loss",
            }, checkpoint)
        with (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        manifest["completed_epochs"] = epoch + 1
        manifest["best_epoch"] = best_epoch
        manifest["best_internal_validation_qdq_psnr_db"] = best_metric
        manifest["candidate_checkpoint_sha256"] = file_sha(output_dir / "candidate_qat_fp32.pth")
        save_json(output_dir / "run_manifest.json", manifest)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    manifest["status"] = "TRAINED"
    manifest["mean_epoch_seconds"] = float(np.mean([row["epoch_seconds"] for row in rows]))
    model.load_state_dict(best_state, strict=True)
    deployment_scales = calibrate_activation_scales(model, calibration_samples, device)
    save_json(output_dir / "quant_calibration_scales.json", deployment_scales)
    manifest["deployment_calibration"] = "recalibrated on the same 32 train-only patches using the selected checkpoint"
    manifest["deployment_activation_scales"] = deployment_scales
    save_json(output_dir / "run_manifest.json", manifest)
    print(json.dumps({"best_epoch": best_epoch, "best_qdq_psnr_db": best_metric,
                      "checkpoint": str(output_dir / "candidate_qat_fp32.pth")}, ensure_ascii=False), flush=True)
    return 0


def build_patch_tensors(
    image_paths: list[Path], repeat: int, seed: int, epoch: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    lr_patches: list[np.ndarray] = []
    hr_patches: list[np.ndarray] = []
    patch_size = 64
    for image_index, path in enumerate(image_paths):
        with Image.open(path) as opened:
            source = opened.convert("YCbCr").getchannel("Y")
            array = np.asarray(source, dtype=np.uint8)
        patch = min(patch_size, array.shape[0] // 2 * 2, array.shape[1] // 2 * 2)
        patch -= patch % 2
        if patch < 2:
            raise ValueError(f"Image too small for x2 training: {path}")
        for repeat_index in range(repeat):
            sample_index = image_index * repeat + repeat_index
            rng = np.random.default_rng(seed + epoch * len(image_paths) * repeat + sample_index)
            top = int(rng.integers(0, array.shape[0] - patch + 1))
            left = int(rng.integers(0, array.shape[1] - patch + 1))
            hr = array[top:top + patch, left:left + patch]
            transform = int(rng.integers(0, 8))
            if transform & 1:
                hr = np.fliplr(hr)
            if transform & 2:
                hr = np.flipud(hr)
            if transform & 4:
                hr = np.rot90(hr)
            hr_image = Image.fromarray(np.ascontiguousarray(hr), mode="L")
            lr_image = hr_image.resize((patch // 2, patch // 2), Image.Resampling.BICUBIC)
            lr_patches.append(np.asarray(lr_image, dtype=np.float32) / 255.0)
            hr_patches.append(np.asarray(hr_image, dtype=np.float32) / 255.0)
    lr_tensor = torch.from_numpy(np.stack(lr_patches)[:, None])
    hr_tensor = torch.from_numpy(np.stack(hr_patches)[:, None])
    return lr_tensor, hr_tensor


if __name__ == "__main__":
    raise SystemExit(main())
