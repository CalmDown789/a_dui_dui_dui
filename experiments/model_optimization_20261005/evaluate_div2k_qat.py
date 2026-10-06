"""Evaluate a DIV2K/T91 QAT candidate on held-out images and BBB dev frames."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from member_a.data import EvalDataset
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y
from member_a.model import FSRCNNSubpixel
from member_a.quantization import calibrate_activation_scales, export_quantized_bundle, quantized_forward_float
from evaluate_dynamic_crop_ab import BASE_CHECKPOINT_SHA256, BASE_QUANT_SHA256, file_sha, make_video_samples
from train_div2k_qat import build_patch_tensors


def load_model(path: Path, device: torch.device) -> FSRCNNSubpixel:
    saved = torch.load(path, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    return model.to(device).eval()


def as_u8(tensor: torch.Tensor) -> np.ndarray:
    return np.floor(tensor.detach().cpu().numpy().squeeze().clip(0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def metrics(ref: torch.Tensor, out: torch.Tensor) -> tuple[float, float]:
    return psnr_y(ref, out, border=2), ssim_y(ref, out, border=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--div2k-dir", type=Path, default=ROOT / ".data/model_optimization/datasets/div2k")
    parser.add_argument("--run-dir", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--checkpoint-name", default="candidate_qat_fp32.pth")
    parser.add_argument("--video", type=Path, default=ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_20261005/evaluation")
    args = parser.parse_args()

    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant_json = ROOT / "artifacts/quant/quant_params.json"
    candidate_checkpoint = args.run_dir.resolve() / args.checkpoint_name
    if file_sha(frozen_checkpoint) != BASE_CHECKPOINT_SHA256 or file_sha(frozen_quant_json) != BASE_QUANT_SHA256:
        parser.error("Frozen model/quantization hashes changed")
    if not candidate_checkpoint.is_file():
        parser.error("Candidate checkpoint is missing")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    frozen = load_model(frozen_checkpoint, device)
    candidate = load_model(candidate_checkpoint, device)
    scales = json.loads((args.run_dir.resolve() / "quant_calibration_scales.json").read_text(encoding="utf-8"))
    candidate_quant_dir = output_dir / "candidate_quantized"
    candidate_quant_dir.mkdir()
    export_quantized_bundle(candidate, scales, candidate_quant_dir)
    t91_files = sorted(path for path in (args.data_dir.resolve() / "t91").iterdir() if path.is_file())
    div2k_files = sorted((args.div2k_dir.resolve() / "split/train_hr").glob("*.png"))
    calibration_lr_t91, _ = build_patch_tensors(t91_files[:16], repeat=1, seed=20261005, epoch=0)
    calibration_lr_div2k, _ = build_patch_tensors(div2k_files[:16], repeat=1, seed=20261006, epoch=0)
    calibration_samples = [item.unsqueeze(0) for item in torch.cat([calibration_lr_t91, calibration_lr_div2k], dim=0)]
    frozen_train_scales = calibrate_activation_scales(frozen, calibration_samples, device)
    frozen_train_quant_dir = output_dir / "frozen_train_calibrated_quantized"
    frozen_train_quant_dir.mkdir()
    export_quantized_bundle(frozen, frozen_train_scales, frozen_train_quant_dir)
    frozen_engine = FixedReference(ROOT / "artifacts/quant")
    frozen_train_engine = FixedReference(frozen_train_quant_dir)
    candidate_engine = FixedReference(candidate_quant_dir)

    heldout = EvalDataset(args.div2k_dir.resolve() / "split/validation_hr")
    records: list[dict] = []
    selection_indices = set(range(0, len(heldout), 4))
    exact_indices = set(range(1, len(heldout), 4))
    for index in range(len(heldout)):
        name, lr, hr = heldout[index]
        lr_batch = lr[None].to(device)
        target = hr[None].to(device)
        with torch.inference_mode():
            frozen_fp = frozen(lr_batch).clamp(0.0, 1.0)
            candidate_fp = candidate(lr_batch).clamp(0.0, 1.0)
            candidate_qdq = quantized_forward_float(candidate, lr_batch, scales).clamp(0.0, 1.0)
            frozen_train_qdq = quantized_forward_float(frozen, lr_batch, frozen_train_scales).clamp(0.0, 1.0)
        row: dict = {
            "sample": name,
            "group": "div2k_internal_heldout_80",
            "validation_index": index,
            "checkpoint_selection_sample": index in selection_indices,
            "integer_exact": index in exact_indices,
        }
        for key, output in (("frozen_fp32", frozen_fp), ("candidate_fp32", candidate_fp), ("candidate_qdq", candidate_qdq)):
            row[f"{key}_psnr_db"], row[f"{key}_ssim"] = metrics(target, output)
        row["frozen_train_calibrated_qdq_psnr_db"], row["frozen_train_calibrated_qdq_ssim"] = metrics(target, frozen_train_qdq)
        if index in exact_indices:
            lr_u8 = as_u8(lr)
            frozen_out = frozen_engine.run(lr_u8)["output"][:, :, 0]
            frozen_train_out = frozen_train_engine.run(lr_u8)["output"][:, :, 0]
            candidate_out = candidate_engine.run(lr_u8)["output"][:, :, 0]
            for key, output_u8 in (("frozen_integer", frozen_out),
                                   ("frozen_train_calibrated_integer", frozen_train_out),
                                   ("candidate_integer", candidate_out)):
                output = torch.from_numpy(output_u8.astype(np.float32) / 255.0)[None, None]
                row[f"{key}_psnr_db"], row[f"{key}_ssim"] = metrics(target.cpu(), output)
        records.append(row)
        print(f"DIV2K {index + 1}/{len(heldout)} {name} done", flush=True)

    video_samples = make_video_samples(args.video.resolve())
    for sample in video_samples:
        input_tensor = sample["lr_tensor"].to(device)
        target = torch.from_numpy(sample["hr_u8"].astype(np.float32) / 255.0)[None, None]
        with torch.inference_mode():
            frozen_fp = frozen(input_tensor).clamp(0.0, 1.0).cpu()
            candidate_fp = candidate(input_tensor).clamp(0.0, 1.0).cpu()
            candidate_qdq = quantized_forward_float(candidate, input_tensor, scales).clamp(0.0, 1.0).cpu()
            frozen_train_qdq = quantized_forward_float(frozen, input_tensor, frozen_train_scales).clamp(0.0, 1.0).cpu()
        row = {"sample": sample["name"], "group": "bbb_development_8", "integer_exact": True}
        for key, output in (("frozen_fp32", frozen_fp), ("candidate_fp32", candidate_fp), ("candidate_qdq", candidate_qdq)):
            row[f"{key}_psnr_db"], row[f"{key}_ssim"] = metrics(target, output)
        row["frozen_train_calibrated_qdq_psnr_db"], row["frozen_train_calibrated_qdq_ssim"] = metrics(target, frozen_train_qdq)
        lr_u8 = sample["lr_u8"]
        for key, output_u8 in (("frozen_integer", frozen_engine.run(lr_u8)["output"][:, :, 0]),
                               ("frozen_train_calibrated_integer", frozen_train_engine.run(lr_u8)["output"][:, :, 0]),
                               ("candidate_integer", candidate_engine.run(lr_u8)["output"][:, :, 0])):
            output = torch.from_numpy(output_u8.astype(np.float32) / 255.0)[None, None]
            row[f"{key}_psnr_db"], row[f"{key}_ssim"] = metrics(target, output)
        records.append(row)
        print(f"BBB {sample['name']} done", flush=True)

    groups: dict[str, dict] = {}
    for group in sorted({row["group"] for row in records}):
        subset = [row for row in records if row["group"] == group]
        metrics_keys = sorted({key for row in subset for key in row if key.endswith(("_psnr_db", "_ssim"))})
        groups[group] = {"samples": len(subset), **{
            key: float(np.mean([row[key] for row in subset if key in row]))
            for key in metrics_keys if any(key in row for row in subset)
        }}
        if group == "div2k_internal_heldout_80":
            exact = [row for row in subset if row["integer_exact"]]
            selection = [row for row in subset if row["checkpoint_selection_sample"]]
            untouched = [row for row in subset if not row["checkpoint_selection_sample"]]
            evaluation_keys = (
                "frozen_fp32_psnr_db", "candidate_fp32_psnr_db", "candidate_qdq_psnr_db",
                "frozen_train_calibrated_qdq_psnr_db", "frozen_integer_psnr_db",
                "frozen_train_calibrated_integer_psnr_db", "candidate_integer_psnr_db",
                "frozen_fp32_ssim", "candidate_fp32_ssim", "candidate_qdq_ssim",
                "frozen_train_calibrated_qdq_ssim", "frozen_integer_ssim",
                "frozen_train_calibrated_integer_ssim", "candidate_integer_ssim",
            )
            for subset_name, subset_rows in (("exact20", exact), ("selected20", selection),
                                               ("untouched60", untouched)):
                for key in evaluation_keys:
                    observed = [row[key] for row in subset_rows if key in row]
                    if observed:
                        groups[group][f"{subset_name}_mean_{key}"] = float(np.mean(observed))
            groups[group]["exact20_candidate_quant_loss_db"] = (
                groups[group]["exact20_mean_candidate_fp32_psnr_db"]
                - groups[group]["exact20_mean_candidate_integer_psnr_db"]
            )
            groups[group]["exact20_frozen_original_quant_loss_db"] = (
                groups[group]["exact20_mean_frozen_fp32_psnr_db"]
                - groups[group]["exact20_mean_frozen_integer_psnr_db"]
            )
            groups[group]["exact20_frozen_train_calibrated_quant_loss_db"] = (
                groups[group]["exact20_mean_frozen_fp32_psnr_db"]
                - groups[group]["exact20_mean_frozen_train_calibrated_integer_psnr_db"]
            )
    for group_result in groups.values():
        if "frozen_integer_psnr_db" in group_result and "candidate_integer_psnr_db" in group_result:
            group_result["candidate_integer_delta_vs_frozen_db"] = group_result["candidate_integer_psnr_db"] - group_result["frozen_integer_psnr_db"]
        if "frozen_train_calibrated_integer_psnr_db" in group_result and "candidate_integer_psnr_db" in group_result:
            group_result["candidate_integer_delta_vs_train_calibrated_frozen_db"] = (
                group_result["candidate_integer_psnr_db"] - group_result["frozen_train_calibrated_integer_psnr_db"]
            )
        if "candidate_fp32_psnr_db" in group_result and "candidate_integer_psnr_db" in group_result:
            if "exact20_candidate_quant_loss_db" in group_result:
                group_result["candidate_quant_loss_db"] = group_result["exact20_candidate_quant_loss_db"]
            else:
                group_result["candidate_quant_loss_db"] = group_result["candidate_fp32_psnr_db"] - group_result["candidate_integer_psnr_db"]

    csv_path = output_dir / "per_sample_metrics.csv"
    fieldnames = sorted({key for row in records for key in row})
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    summary = {
        "schema": "member-a-div2k-qat-evaluation-v1",
        "status": "EXPLORATORY_SOFTWARE_ONLY",
        "candidate_checkpoint_sha256": file_sha(candidate_checkpoint),
        "frozen_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "frozen_quant_params_sha256": BASE_QUANT_SHA256,
        "div2k_archive_sha256": json.loads((args.div2k_dir.resolve() / "manifest.json").read_text(encoding="utf-8"))["archive_sha256"],
        "video_source_sha256": "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28",
        "candidate_activation_scales": scales,
        "exact_integer_coverage": "All 8 BBB development frames plus every fourth DIV2K held-out image (20/80); QDQ measured on all 80 DIV2K images.",
        "groups": groups,
        "scope_limits": [
            "DIV2K validation images are an internal image-level split of the 800 official training-HR images, not the official DIV2K test set.",
            "BBB frames are a previously observed development set and are not final untouched evidence.",
            "The official DIV2K page restricts use to academic research; raw images and candidate model are not redistributed.",
            "PC software metrics only; not FPGA, board, or real-time acceptance.",
        ],
        "per_sample_csv": csv_path.name,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(groups, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
