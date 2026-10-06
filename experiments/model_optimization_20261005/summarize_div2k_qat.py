"""Rebuild fair, same-sample metric summaries from the saved per-image CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean_metric(rows: list[dict[str, str]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key, "") != ""]
    return float(np.mean(values)) if values else None


def summarize(rows: list[dict[str, str]]) -> dict:
    groups: dict[str, dict] = {}
    for group_name in sorted({row["group"] for row in rows}):
        members = [row for row in rows if row["group"] == group_name]
        available_metrics = sorted({
            key for row in members for key, value in row.items()
            if key.endswith(("_psnr_db", "_ssim")) and value != ""
        })
        result = {"samples": len(members)}
        for key in available_metrics:
            value = mean_metric(members, key)
            if value is not None:
                result[key] = value
        if group_name == "div2k_internal_heldout_80":
            exact = [row for row in members if row["integer_exact"].lower() == "true"]
            selected = [row for row in members if row["checkpoint_selection_sample"].lower() == "true"]
            untouched = [row for row in members if row["checkpoint_selection_sample"].lower() != "true"]
            for subset_name, subset_rows in (("exact20", exact), ("selected20", selected), ("untouched60", untouched)):
                result[f"{subset_name}_samples"] = len(subset_rows)
                for key in available_metrics:
                    value = mean_metric(subset_rows, key)
                    if value is not None:
                        result[f"{subset_name}_mean_{key}"] = value
            result["exact20_candidate_quant_loss_db"] = (
                result["exact20_mean_candidate_fp32_psnr_db"]
                - result["exact20_mean_candidate_integer_psnr_db"]
            )
            result["exact20_frozen_original_quant_loss_db"] = (
                result["exact20_mean_frozen_fp32_psnr_db"]
                - result["exact20_mean_frozen_integer_psnr_db"]
            )
            result["exact20_frozen_train_calibrated_quant_loss_db"] = (
                result["exact20_mean_frozen_fp32_psnr_db"]
                - result["exact20_mean_frozen_train_calibrated_integer_psnr_db"]
            )
            result["exact20_candidate_integer_delta_vs_frozen_db"] = (
                result["exact20_mean_candidate_integer_psnr_db"]
                - result["exact20_mean_frozen_integer_psnr_db"]
            )
            result["exact20_candidate_integer_delta_vs_train_calibrated_frozen_db"] = (
                result["exact20_mean_candidate_integer_psnr_db"]
                - result["exact20_mean_frozen_train_calibrated_integer_psnr_db"]
            )
            result["exact20_candidate_integer_minus_qdq_psnr_db"] = (
                result["exact20_mean_candidate_integer_psnr_db"]
                - result["exact20_mean_candidate_qdq_psnr_db"]
            )
            result["untouched60_candidate_qdq_delta_vs_frozen_train_calibrated_db"] = (
                result["untouched60_mean_candidate_qdq_psnr_db"]
                - result["untouched60_mean_frozen_train_calibrated_qdq_psnr_db"]
            )
        groups[group_name] = result
    return groups


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=root / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--evaluation-dir", type=Path)
    parser.add_argument("--checkpoint-name", default="candidate_qat_fp32.pth")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    evaluation_dir = (args.evaluation_dir or run_dir / "evaluation_calibration_ab").resolve()
    csv_path = evaluation_dir / "per_sample_metrics.csv"
    if not csv_path.is_file():
        parser.error(f"Per-sample evaluation CSV missing: {csv_path}")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    div_manifest = json.loads((root / ".data/model_optimization/datasets/div2k/manifest.json").read_text(encoding="utf-8"))
    summary = {
        "schema": "member-a-div2k-qat-evaluation-v1",
        "status": "EXPLORATORY_SOFTWARE_ONLY",
        "candidate_checkpoint_sha256": sha256(run_dir / args.checkpoint_name),
        "frozen_checkpoint_sha256": run_manifest.get(
            "parent_checkpoint_sha256", run_manifest.get("frozen_checkpoint_sha256")
        ),
        "frozen_quant_params_sha256": run_manifest["frozen_quant_params_sha256"],
        "div2k_archive_sha256": div_manifest["archive_sha256"],
        "video_source_sha256": "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28",
        "candidate_activation_scales": json.loads((run_dir / "quant_calibration_scales.json").read_text(encoding="utf-8")),
        "metric_comparison_rule": "FP32, QDQ, and exact integer metrics are compared on the same images when reporting quantization loss; the 80-image aggregate and 20-image exact-integer subset are shown separately.",
        "exact_integer_coverage": "All 8 BBB development frames plus 20 DIV2K internal holdout images not used for checkpoint selection.",
        "groups": summarize(rows),
        "scope_limits": [
            "DIV2K 80-image holdout is an internal split of the official 800 training-HR images; first 20 by deterministic stride were used for checkpoint selection, and the remaining 60 were not used for selection.",
            "Exact integer runs were performed on 20 of the untouched 60 DIV2K images; report those separately from all-80 QDQ metrics.",
            "BBB frames are a previously observed development set, not untouched final evidence.",
            "Official DIV2K terms limit use to academic research; raw data and candidate model are not redistributed.",
            "All measurements are PC software evidence, not FPGA, board, or real-time acceptance.",
        ],
        "per_sample_csv": csv_path.name,
    }
    (evaluation_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["groups"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
