"""Verify the published A 4K PC software handoff and its frozen asset linkage."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "artifacts/member_a_4k_postprocess_golden"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    package = args.package_dir.resolve()
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "member-a-pc-postprocess-4k-golden-v1":
        raise ValueError("Unexpected 4K Golden package schema")
    if manifest.get("evaluated_pairs") != 25 or len(manifest.get("frames", [])) != 3:
        raise ValueError("Expected 25 paired eval rows and 3 full-frame Golden hash entries")
    if manifest.get("pixel_assets_published") is not False:
        raise ValueError("The repository policy requires 4K pixel assets to remain local-only")
    expected_hashes = {
        "checkpoint": (ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth", manifest["checkpoint_sha256"]),
        "quant_params": (ROOT / "artifacts/quant/quant_params.json", manifest["formal_quant_params_sha256"]),
        "metrics_csv": (package / manifest["per_frame_metrics_csv"], manifest["per_frame_metrics_csv_sha256"]),
        "evaluation_summary": (package / manifest["evaluation_summary"], manifest["evaluation_summary_sha256"]),
    }
    for name, (path, expected) in expected_hashes.items():
        if sha256(path) != expected:
            raise ValueError(f"{name} hash mismatch: {path}")

    rows = list(csv.DictReader((package / manifest["per_frame_metrics_csv"]).open(encoding="utf-8", newline="")))
    if len(rows) != 25 or len({row["frame_id"] for row in rows}) != 25:
        raise ValueError("Per-frame metric table must contain 25 unique frame IDs")
    expected_counts = {"ffmpeg_Bosphorus_test_pairs": 10,
                       "ffmpeg_ReadySetGo_test_pairs": 10,
                       "ffmpeg_ShakeNDry_test_pairs": 5}
    actual_counts = {name: sum(row["sequence"] == name for row in rows) for name in expected_counts}
    if actual_counts != expected_counts:
        raise ValueError(f"Unexpected sequence coverage: {actual_counts}")
    metrics_fields = [
        "bicubic_y_psnr_db", "bicubic_y_ssim", "r0_fp32_y_psnr_db", "r0_fp32_y_ssim",
        "r0_int_y_psnr_db", "r0_int_y_ssim", "bicubic_psnr_full_db", "bicubic_ssim_full",
        "r0_fp32_psnr_full_db", "r0_fp32_ssim_full", "r0_int_psnr_full_db", "r0_int_ssim_full",
    ]
    if any(not math.isfinite(float(row[field])) for row in rows for field in metrics_fields):
        raise ValueError("Non-finite PSNR/SSIM in per-frame metrics")
    if any(float(row["r0_int_y_psnr_db"]) <= float(row["bicubic_y_psnr_db"]) for row in rows):
        raise ValueError("At least one integer R0 frame does not exceed the bicubic PSNR baseline")

    local_pixel_goldens_verified = 0
    for record in manifest["frames"]:
        golden = package / record["output_bin"]
        preview = package / record["preview_png"]
        if record.get("output_bytes") != 8_294_400:
            raise ValueError(f"Unexpected Golden byte count in manifest: {record['frame_id']}")
        if len(record.get("output_sha256", "")) != 64 or len(record.get("output_crc32", "")) != 8:
            raise ValueError(f"Missing Golden hashes in manifest: {record['frame_id']}")
        if golden.exists() != preview.exists():
            raise ValueError(f"Only one local pixel asset exists for {record['frame_id']}")
        if golden.exists():
            if golden.stat().st_size != 8_294_400 or sha256(golden) != record["output_sha256"]:
                raise ValueError(f"Golden bytes/hash mismatch: {golden.name}")
            if sha256(preview) != record["preview_sha256"]:
                raise ValueError(f"Golden preview hash mismatch: {preview.name}")
            with Image.open(preview) as image:
                if image.mode != "L" or image.size != (3840, 2160):
                    raise ValueError(f"Unexpected Golden preview dimensions/mode: {preview.name}")
                preview_bytes = np.asarray(image, dtype=np.uint8)
            golden_bytes = np.fromfile(golden, dtype=np.uint8).reshape(2160, 3840)
            if not np.array_equal(preview_bytes, golden_bytes):
                raise ValueError(f"Golden PNG preview pixels differ from raw Y8: {preview.name}")
            local_pixel_goldens_verified += 1

    benchmark_ref = manifest.get("pc_benchmark")
    if not benchmark_ref:
        raise ValueError("PC benchmark is not attached to the handoff package")
    benchmark_path = package / benchmark_ref["path"]
    if sha256(benchmark_path) != benchmark_ref["sha256"]:
        raise ValueError("PC benchmark report hash mismatch")
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if benchmark.get("schema") != "member-a-pc-path-benchmark-v1":
        raise ValueError("Unexpected PC benchmark report schema")

    visual = manifest.get("quality_examples")
    if not visual:
        raise ValueError("Visual comparison sheet is missing")
    image_path, report_path = package / visual["image"], package / visual["report"]
    if not image_path.exists() and manifest.get("pixel_assets_published") is not False:
        raise FileNotFoundError("Quality comparison image is missing")
    if image_path.exists() and sha256(image_path) != visual["image_sha256"]:
        raise ValueError("Quality visual image hash mismatch")
    if sha256(report_path) != visual["report_sha256"]:
        raise ValueError("Quality visual report hash mismatch")
    visual_report = json.loads(report_path.read_text(encoding="utf-8"))
    if len(visual_report.get("frames", [])) != 3:
        raise ValueError("Expected one least-gain visual example per sequence")
    if not (ROOT / "docs/成员A竞赛分工执行与阶段结果_20261008.md").is_file():
        raise FileNotFoundError("Member A competition report is missing")

    print(json.dumps({"status": "PASS_MEMBER_A_COMPETITION_HANDOFF_INTEGRITY",
                      "paired_evaluation_frames": len(rows), "golden_hashes_listed": len(manifest["frames"]),
                      "local_pixel_goldens_verified": local_pixel_goldens_verified,
                      "sequence_counts": actual_counts, "checkpoint_sha256": manifest["checkpoint_sha256"],
                      "quant_params_sha256": manifest["formal_quant_params_sha256"],
                      "package_files": sum(path.is_file() for path in package.rglob("*"))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
