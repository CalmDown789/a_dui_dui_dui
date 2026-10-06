"""Low-rate EMA QAT refinement, selected only on the predefined 20-image split."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset, TensorDataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from member_a.data import EvalDataset
from member_a.model import FSRCNNSubpixel
from member_a.quantization import calibrate_activation_scales
from member_a.training import evaluate_model, qat_forward, seed_everything
from train_div2k_qat import BASE_CHECKPOINT_SHA256, BASE_QUANT_SHA256, T91_SHA256, build_patch_tensors, file_sha, save_json


PARENT_CANDIDATE_SHA256 = "4eb3f144df4c1ab9cbd2f93c00f9456eede34ca4b3b67be1422a718bbef6b184"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--div2k-dir", type=Path, default=ROOT / ".data/model_optimization/datasets/div2k")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/qat_ema_refine_20261006")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=1.0e-6)
    parser.add_argument("--ema-decay", type=float, default=0.99)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args()

    parent_checkpoint = args.parent_run.resolve() / "candidate_qat_fp32.pth"
    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant = ROOT / "artifacts/quant/quant_params.json"
    div_manifest_path = args.div2k_dir.resolve() / "manifest.json"
    t91_manifest_path = args.data_dir.resolve() / "dataset_manifest.json"
    if file_sha(frozen_checkpoint) != BASE_CHECKPOINT_SHA256 or file_sha(frozen_quant) != BASE_QUANT_SHA256:
        parser.error("Frozen official assets changed")
    if file_sha(parent_checkpoint) != PARENT_CANDIDATE_SHA256:
        parser.error("Parent candidate checkpoint hash mismatch")
    t91_manifest = json.loads(t91_manifest_path.read_text(encoding="utf-8"))
    div_manifest = json.loads(div_manifest_path.read_text(encoding="utf-8"))
    if t91_manifest.get("T91", {}).get("sha256") != T91_SHA256:
        parser.error("T91 source hash mismatch")
    if div_manifest.get("image_count") != 800 or div_manifest.get("internal_split", {}).get("training_images") != 720:
        parser.error("Unexpected DIV2K split")
    if args.epochs <= 0 or args.learning_rate <= 0 or not 0.0 < args.ema_decay < 1.0:
        parser.error("Invalid refinement hyperparameters")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(args.seed)
    torch.set_num_threads(4)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    t91_files = sorted(path for path in (args.data_dir.resolve() / "t91").iterdir() if path.is_file())
    div_files = sorted((args.div2k_dir.resolve() / "split/train_hr").glob("*.png"))
    if len(t91_files) != 91 or len(div_files) != 720:
        parser.error(f"Training image count mismatch: T91={len(t91_files)}, DIV2K={len(div_files)}")

    saved = torch.load(parent_checkpoint, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    model.to(device).eval()
    ema_model = deepcopy(model).eval()

    calibration_t91, _ = build_patch_tensors(t91_files[:16], repeat=1, seed=20261005, epoch=0)
    calibration_div, _ = build_patch_tensors(div_files[:16], repeat=1, seed=20261006, epoch=0)
    calibration_samples = [sample.unsqueeze(0) for sample in torch.cat([calibration_t91, calibration_div], dim=0)]
    train_scales = calibrate_activation_scales(model, calibration_samples, device)
    selection_all = EvalDataset(args.div2k_dir.resolve() / "split/validation_hr")
    selection = Subset(selection_all, list(range(0, len(selection_all), 4)))
    if len(selection) != 20:
        parser.error(f"Expected 20 predeclared checkpoint-selection images; got {len(selection)}")

    _, baseline_metrics = evaluate_model(ema_model, selection, device,
                                         calibrate_activation_scales(ema_model, calibration_samples, device))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    criterion = torch.nn.MSELoss()
    best_metric = baseline_metrics["quant_psnr_db"]
    best_epoch = 0
    best_state = deepcopy(ema_model.state_dict())
    best_checkpoint = output_dir / "candidate_ema_qat_fp32.pth"
    torch.save({
        "state_dict": best_state,
        "config": ema_model.config.to_dict(),
        "parent_candidate_checkpoint_sha256": PARENT_CANDIDATE_SHA256,
        "experiment": "Parent candidate fallback for low-rate EMA QAT refinement",
        "epoch": 0,
        "selection_qdq_psnr_db": best_metric,
    }, best_checkpoint)
    rows: list[dict] = []
    manifest = {
        "schema": "member-a-ema-qat-refinement-v1",
        "status": "RUNNING",
        "frozen_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "frozen_quant_params_sha256": BASE_QUANT_SHA256,
        "parent_candidate_checkpoint_sha256": PARENT_CANDIDATE_SHA256,
        "T91_sha256": T91_SHA256,
        "DIV2K_train_archive_sha256": div_manifest["archive_sha256"],
        "device": str(device),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "seed": args.seed,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "ema_decay_per_batch": args.ema_decay,
        "batch_size": 16,
        "training_mix": "T91 repeat=32 plus DIV2K training IDs 0001-0720 repeat=4, fresh deterministic crops/dihedral each epoch",
        "calibration": "32 deterministic training-only patches; same source IDs and crop seed as parent experiment",
        "checkpoint_selection": "QDQ PSNR on DIV2K training-HR IDs 0721-0800, deterministic indices 0,4,...,76; selection data only, not final evidence",
        "selection_samples": len(selection),
        "parent_selection_qdq_psnr_db": baseline_metrics["quant_psnr_db"],
        "parent_selection_qdq_ssim": baseline_metrics["quant_ssim"],
    }
    save_json(output_dir / "run_manifest.json", manifest)

    for epoch in range(args.epochs):
        started = time.perf_counter()
        t91_lr, t91_hr = build_patch_tensors(t91_files, repeat=32, seed=args.seed, epoch=epoch)
        div_lr, div_hr = build_patch_tensors(div_files, repeat=4, seed=args.seed + 1, epoch=epoch)
        train_set = TensorDataset(torch.cat([t91_lr, div_lr]), torch.cat([t91_hr, div_hr]))
        loader = DataLoader(train_set, batch_size=16, shuffle=True, num_workers=0,
                            pin_memory=device.type == "cuda")
        model.train()
        loss_total = 0.0
        sample_count = 0
        for inputs, labels in loader:
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            qat_loss = criterion(qat_forward(model, inputs, train_scales), labels)
            fp32_loss = criterion(model(inputs).clamp(0.0, 1.0), labels)
            loss = qat_loss + 0.25 * fp32_loss
            loss.backward()
            optimizer.step()
            with torch.no_grad():
                for ema_param, current_param in zip(ema_model.parameters(), model.parameters()):
                    ema_param.lerp_(current_param, 1.0 - args.ema_decay)
            loss_total += float(qat_loss.detach().item()) * inputs.shape[0]
            sample_count += inputs.shape[0]

        model.eval()
        ema_model.eval()
        validation_scales = calibrate_activation_scales(ema_model, calibration_samples, device)
        _, metrics = evaluate_model(ema_model, selection, device, validation_scales)
        row = {
            "epoch": epoch + 1,
            "qat_train_mse": loss_total / sample_count,
            "selection_qdq_psnr_db": metrics["quant_psnr_db"],
            "selection_qdq_ssim": metrics["quant_ssim"],
            "selection_fp32_psnr_db": metrics["fp32_psnr_db"],
            "epoch_seconds": time.perf_counter() - started,
        }
        rows.append(row)
        if row["selection_qdq_psnr_db"] > best_metric:
            best_metric = row["selection_qdq_psnr_db"]
            best_epoch = epoch + 1
            best_state = deepcopy(ema_model.state_dict())
            torch.save({
                "state_dict": best_state,
                "config": ema_model.config.to_dict(),
                "parent_candidate_checkpoint_sha256": PARENT_CANDIDATE_SHA256,
                "experiment": "Low-rate EMA QAT refinement; selected on predeclared DIV2K 20-image selection split",
                "epoch": best_epoch,
                "selection_qdq_psnr_db": best_metric,
            }, best_checkpoint)
        with (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        manifest.update({
            "completed_epochs": epoch + 1,
            "best_epoch": best_epoch,
            "best_selection_qdq_psnr_db": best_metric,
            "candidate_checkpoint_sha256": file_sha(best_checkpoint),
        })
        save_json(output_dir / "run_manifest.json", manifest)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    model.load_state_dict(best_state, strict=True)
    final_scales = calibrate_activation_scales(model, calibration_samples, device)
    save_json(output_dir / "quant_calibration_scales.json", final_scales)
    manifest["status"] = "TRAINED"
    manifest["mean_epoch_seconds"] = float(np.mean([row["epoch_seconds"] for row in rows]))
    manifest["deployment_activation_scales"] = final_scales
    manifest["checkpoint_selected_from_parent_or_refinement"] = "parent" if best_epoch == 0 else f"EMA epoch {best_epoch}"
    save_json(output_dir / "run_manifest.json", manifest)
    print(json.dumps({"best_epoch": best_epoch, "best_selection_qdq_psnr_db": best_metric,
                      "parent_selection_qdq_psnr_db": baseline_metrics["quant_psnr_db"],
                      "checkpoint": str(best_checkpoint)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
