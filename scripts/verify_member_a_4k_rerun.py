"""Compare a fresh 25-frame A evaluation against the frozen PC quality package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "artifacts/member_a_4k_postprocess_golden"
EXACT_METRICS = (
    "bicubic_y_psnr_db",
    "bicubic_y_ssim",
    "r0_int_y_psnr_db",
    "r0_int_y_ssim",
    "bicubic_psnr_full_db",
    "bicubic_ssim_full",
    "r0_int_psnr_full_db",
    "r0_int_ssim_full",
)
FP32_TOLERANCES = {
    "r0_fp32_y_psnr_db": 0.02,
    "r0_fp32_y_ssim": 0.00005,
    "r0_fp32_psnr_full_db": 0.02,
    "r0_fp32_ssim_full": 0.00005,
}
SEQUENCE_COUNTS = {
    "ffmpeg_Bosphorus_test_pairs": 10,
    "ffmpeg_ReadySetGo_test_pairs": 10,
    "ffmpeg_ShakeNDry_test_pairs": 5,
}


def _read_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    indexed = {row["frame_id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate frame IDs in {path}")
    return indexed


def verify_rerun(evaluation_dir: Path, baseline_dir: Path, *, require_goldens: bool) -> dict[str, object]:
    evaluation_dir = evaluation_dir.resolve()
    baseline_dir = baseline_dir.resolve()
    run_summary = json.loads((evaluation_dir / "summary.json").read_text(encoding="utf-8"))
    baseline_summary = json.loads((baseline_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((baseline_dir / "manifest.json").read_text(encoding="utf-8"))

    if run_summary.get("schema") != "member-a-4k-frozen-r0-software-evaluation-v1":
        raise ValueError("Fresh evaluation has an unexpected schema")
    for run_key, baseline_key in (
        ("frozen_checkpoint_sha256", "checkpoint_sha256"),
        ("frozen_quant_params_sha256", "formal_quant_params_sha256"),
    ):
        if run_summary.get(run_key) != manifest.get(baseline_key):
            raise ValueError(f"Frozen model asset differs: {run_key}")
    if run_summary.get("pair_manifest_sha256") != baseline_summary.get("pair_manifest_sha256"):
        raise ValueError("Fresh evaluation used a different paired-data manifest")

    expected = _read_rows(baseline_dir / manifest["per_frame_metrics_csv"])
    actual = _read_rows(evaluation_dir / "per_frame.csv")
    if set(expected) != set(actual) or len(actual) != 25:
        raise ValueError("Fresh evaluation must contain the same 25 frame IDs")
    counts = {name: sum(row["sequence"] == name for row in actual.values()) for name in SEQUENCE_COUNTS}
    if counts != SEQUENCE_COUNTS:
        raise ValueError(f"Unexpected sequence/frame coverage: {counts}")

    max_delta = {key: 0.0 for key in (*EXACT_METRICS, *FP32_TOLERANCES)}
    for frame_id, reference in expected.items():
        row = actual[frame_id]
        for key in ("sequence", "source_file", "lr_sha256", "hr_sha256"):
            if row.get(key) != reference.get(key):
                raise ValueError(f"Frame provenance differs at {frame_id}: {key}")
        for metric in EXACT_METRICS:
            delta = abs(float(row[metric]) - float(reference[metric]))
            max_delta[metric] = max(max_delta[metric], delta)
            if not math.isfinite(delta) or delta > 1e-9:
                raise ValueError(f"Exact metric mismatch at {frame_id}: {metric} delta={delta}")
        for metric, tolerance in FP32_TOLERANCES.items():
            delta = abs(float(row[metric]) - float(reference[metric]))
            max_delta[metric] = max(max_delta[metric], delta)
            if not math.isfinite(delta) or delta > tolerance:
                raise ValueError(
                    f"FP32 metric exceeds cross-device tolerance at {frame_id}: "
                    f"{metric} delta={delta} tolerance={tolerance}"
                )

    expected_goldens = {row["frame_id"]: row for row in manifest["frames"]}
    checked_goldens = 0
    for frame_id, row in actual.items():
        relative = row.get("golden_4k_path")
        if not relative:
            continue
        golden = (evaluation_dir / relative).resolve()
        try:
            golden.relative_to(evaluation_dir)
        except ValueError as error:
            raise ValueError(f"4K Golden escaped the evaluation directory: {relative}") from error
        record = expected_goldens.get(frame_id)
        if record is None:
            raise ValueError(f"Unexpected exported 4K Golden frame: {frame_id}")
        if golden.stat().st_size != record["output_bytes"]:
            raise ValueError(f"4K Golden size mismatch: {frame_id}")
        digest = hashlib.sha256(golden.read_bytes()).hexdigest()
        if digest != record["output_sha256"] or digest != row.get("golden_4k_sha256"):
            raise ValueError(f"4K Golden SHA-256 mismatch: {frame_id}")
        checked_goldens += 1

    if require_goldens and checked_goldens != len(expected_goldens):
        raise ValueError(
            f"Expected {len(expected_goldens)} 4K Golden exports, checked {checked_goldens}"
        )
    return {
        "status": "PASS_MEMBER_A_4K_RERUN",
        "frames": len(actual),
        "sequence_counts": counts,
        "float_device": run_summary.get("float_device"),
        "exact_metrics": list(EXACT_METRICS),
        "fp32_cross_device_tolerances": FP32_TOLERANCES,
        "max_abs_metric_delta": max_delta,
        "verified_4k_golden_files": checked_goldens,
        "model_checkpoint_sha256": manifest["checkpoint_sha256"],
        "quant_params_sha256": manifest["formal_quant_params_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--require-goldens", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify_rerun(args.evaluation_dir, args.baseline_dir, require_goldens=args.require_goldens)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        report = args.report.resolve()
        try:
            report.relative_to(ROOT / ".data")
        except ValueError as error:
            raise ValueError("Rerun report must be written under ignored .data/") from error
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
