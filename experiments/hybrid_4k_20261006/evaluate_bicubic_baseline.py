from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .hybrid_reference import run_bicubic4x_u8
from .quantize_candidate_eval import _load_pairs, _metrics_border


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the paired bicubic x4 baseline with full/cropped Y metrics")
    parser.add_argument("--pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Baseline metrics must remain under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")

    rows: list[dict[str, str | float]] = []
    manifest_digests: dict[str, str] = {}
    for pairs_dir in args.pairs_dir:
        pairs_dir = pairs_dir.resolve()
        manifest_path = pairs_dir / "manifest.json"
        manifest_digests[pairs_dir.name] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        for record, pair_path in _load_pairs(pairs_dir):
            with np.load(pair_path, allow_pickle=False) as pair:
                hr_y = pair["hr_y"].copy()
                lr_y = pair["lr_y"].copy()
            bicubic = run_bicubic4x_u8(lr_y, keys_a=-0.5)
            if bicubic.shape != hr_y.shape:
                raise ValueError(f"Bicubic output shape {bicubic.shape} does not match reference {hr_y.shape}")
            psnr_crop, ssim_crop = _metrics_border(hr_y, bicubic, border=8)
            psnr_full, ssim_full = _metrics_border(hr_y, bicubic, border=0)
            rows.append(
                {
                    "sequence": pairs_dir.name,
                    "image": str(record["source_file"]),
                    "bicubic_psnr_db": psnr_crop,
                    "bicubic_ssim": ssim_crop,
                    "bicubic_psnr_db_full": psnr_full,
                    "bicubic_ssim_full": ssim_full,
                }
            )

    if not rows:
        raise ValueError("No evaluation pairs were found")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "per_image_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-bicubic-baseline-metrics-v1",
        "status": "SOFTWARE_REFERENCE_ONLY_NOT_BOARD_ACCEPTANCE",
        "keys_a": -0.5,
        "metric_rule": "Y PSNR/SSIM, peak=255; report full frame and center shave=8; arithmetic mean over images",
        "samples": len(rows),
        "test_manifest_sha256": manifest_digests,
        "means": {
            key: float(np.mean([float(row[key]) for row in rows]))
            for key in ["bicubic_psnr_db", "bicubic_ssim", "bicubic_psnr_db_full", "bicubic_ssim_full"]
        },
        "per_image_csv": str(csv_path),
        "limitations": [
            "The test consists of 25 unique lossy UVG HEVC-derived source frames, each evaluated under two synthetic downsampling protocols (50 paired conditions).",
            "This is a software bicubic reference only; not a camera-original 540p/4K measurement or FPGA result.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["means"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
