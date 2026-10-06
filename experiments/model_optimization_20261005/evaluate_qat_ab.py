"""Evaluate QAT arms against frozen and pre-QAT development baselines."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import EvalDataset
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y
from member_a.model import FSRCNNSubpixel
from member_a.quantization import calibrate_activation_scales, export_quantized_bundle
from evaluate_dynamic_crop_ab import BASE_CHECKPOINT_SHA256, BASE_QUANT_SHA256, file_sha, make_video_samples


def load_checkpoint(path: Path, device: torch.device) -> FSRCNNSubpixel:
    saved = torch.load(path, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    return model.to(device).eval()


def as_sample(name: str, group: str, lr: torch.Tensor, hr: torch.Tensor) -> dict:
    lr_u8 = np.floor(lr.squeeze().numpy().clip(0, 1) * 255 + 0.5).astype(np.uint8)
    hr_u8 = np.floor(hr.squeeze().numpy().clip(0, 1) * 255 + 0.5).astype(np.uint8)
    return {"name": name, "group": group, "lr_u8": lr_u8, "hr_u8": hr_u8,
            "lr_tensor": lr[None]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--source-run", type=Path, default=ROOT / ".data/model_optimization/dynamic_crop_ab_20e")
    parser.add_argument("--qat-run", type=Path, default=ROOT / ".data/model_optimization/qat_ab_20261005")
    parser.add_argument("--video", type=Path, default=ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/qat_ab_20261005/evaluation")
    args = parser.parse_args()

    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant_json = ROOT / "artifacts/quant/quant_params.json"
    if file_sha(frozen_checkpoint) != BASE_CHECKPOINT_SHA256 or file_sha(frozen_quant_json) != BASE_QUANT_SHA256:
        parser.error("Frozen model/quantization hashes changed; refusing comparison")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty evaluation directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    models = {
        "frozen": load_checkpoint(frozen_checkpoint, device),
        "resampled_pre_qat": load_checkpoint(args.source_run / "epoch_resampled_crop/candidate_fp32.pth", device),
        "frozen_start_qat": load_checkpoint(args.qat_run / "frozen_start_qat/fsrcnn_d16_s8_m1_c16_x2_qat.pth", device),
        "resampled_start_qat": load_checkpoint(args.qat_run / "resampled_start_qat/fsrcnn_d16_s8_m1_c16_x2_qat.pth", device),
    }
    set5_dir = args.data_dir.resolve() / "set5"
    set5_eval = EvalDataset(set5_dir)
    samples = []
    for index in range(len(set5_eval)):
        name, lr, hr = set5_eval[index]
        samples.append(as_sample(name, "set5_selection_validation", lr, hr))
    samples.extend(make_video_samples(args.video.resolve()))

    quant_dirs: dict[str, Path] = {"frozen": ROOT / "artifacts/quant"}
    calibration = [set5_eval[index][1].unsqueeze(0) for index in range(len(set5_eval))]
    for name in ("resampled_pre_qat", "frozen_start_qat", "resampled_start_qat"):
        quant_dir = output_dir / f"{name}_quantized"
        quant_dir.mkdir()
        scales = calibrate_activation_scales(models[name], calibration, device)
        export_quantized_bundle(models[name], scales, quant_dir)
        quant_dirs[name] = quant_dir
    engines = {name: FixedReference(path) for name, path in quant_dirs.items()}

    rows = []
    for sample in samples:
        x = sample["lr_tensor"].to(device)
        ref = torch.from_numpy(sample["hr_u8"].astype(np.float32) / 255.0)[None, None]
        row = {"sample": sample["name"], "group": sample["group"]}
        with torch.inference_mode():
            for name, model in models.items():
                output = model(x).clamp(0, 1).cpu()
                row[f"{name}_fp32_psnr_db"] = psnr_y(ref, output, border=2)
                row[f"{name}_fp32_ssim"] = ssim_y(ref, output, border=2)
        for name, engine in engines.items():
            output_u8 = engine.run(sample["lr_u8"])["output"][:, :, 0]
            output = torch.from_numpy(output_u8.astype(np.float32) / 255)[None, None]
            row[f"{name}_integer_psnr_db"] = psnr_y(ref, output, border=2)
            row[f"{name}_integer_ssim"] = ssim_y(ref, output, border=2)
        rows.append(row)
        print(f"{sample['name']} done", flush=True)

    metric_columns = [key for key in rows[0] if key.endswith(("_psnr_db", "_ssim"))]
    grouped = {}
    for group in sorted({row["group"] for row in rows}):
        subset = [row for row in rows if row["group"] == group]
        grouped[group] = {
            "samples": len(subset),
            **{
                metric: float(np.mean([row[metric] for row in subset]))
                for metric in metric_columns
            },
        }
    for values in grouped.values():
        for name in models:
            values[f"{name}_quant_loss_db"] = values[f"{name}_fp32_psnr_db"] - values[f"{name}_integer_psnr_db"]
            values[f"{name}_integer_delta_vs_frozen_db"] = values[f"{name}_integer_psnr_db"] - values["frozen_integer_psnr_db"]

    csv_path = output_dir / "per_sample_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-qat-ab-evaluation-v1",
        "status": "EXPLORATORY_SOFTWARE_ONLY",
        "device": str(device),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "baseline_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "baseline_quant_params_sha256": BASE_QUANT_SHA256,
        "bbb_video_sha256": "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28",
        "groups": grouped,
        "scope_limits": [
            "Set5 is a selection/calibration set and is not independent evidence.",
            "BBB frames are development diagnostics previously observed; use a new video source for final acceptance.",
            "All results are PC software measurements, not FPGA/RTL or real-time evidence.",
        ],
        "per_sample_csv": csv_path.name,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(grouped, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
