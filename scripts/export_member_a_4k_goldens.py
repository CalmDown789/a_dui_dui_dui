"""Publish selected reproducible PC 4K integer Golden frames as A artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import zlib

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".data/member_a_4k_postprocess_golden"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--benchmark-report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    evaluation = args.evaluation_dir.resolve()
    output = args.output_dir.resolve()
    summary_path = evaluation / "summary.json"
    csv_path = evaluation / "per_frame.csv"
    if not summary_path.is_file() or not csv_path.is_file():
        raise FileNotFoundError("Evaluation summary.json and per_frame.csv are required")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema") != "member-a-4k-frozen-r0-software-evaluation-v1":
        raise ValueError("Unrecognized A evaluation schema")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty delivery directory: {output}")

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    selected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("golden_4k_path"):
            selected[row["sequence"]] = row
    if not selected:
        raise ValueError("No exported 4K integer Golden is listed in the evaluation")

    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    delivered_metrics: list[dict[str, str]] = []
    for sequence, row in sorted(selected.items()):
        source = evaluation / row["golden_4k_path"]
        if source.stat().st_size != 8_294_400 or sha256(source) != row["golden_4k_sha256"]:
            raise ValueError(f"Evaluation Golden is corrupt: {source}")
        name = sequence.removeprefix("ffmpeg_").removesuffix("_test_pairs")
        target = output / f"{name}_{Path(row['source_file']).stem}_3840x2160_y_u8.bin"
        shutil.copyfile(source, target)
        pixels = np.fromfile(target, dtype=np.uint8).reshape(2160, 3840)
        preview = output / f"{target.stem}.png"
        Image.fromarray(pixels, mode="L").save(preview, format="PNG", optimize=True)
        entries.append({
            "sequence": name,
            "frame_id": row["frame_id"],
            "source_file": row["source_file"],
            "input_lr_sha256": row["lr_sha256"],
            "hr_reference_sha256": row["hr_sha256"],
            "output_bin": target.name,
            "output_bytes": target.stat().st_size,
            "output_crc32": f"{zlib.crc32(target.read_bytes()) & 0xffffffff:08x}",
            "output_sha256": sha256(target),
            "preview_png": preview.name,
            "preview_sha256": sha256(preview),
        })

    output_by_id = {entry["frame_id"]: entry for entry in entries}
    metric_columns = [
        "frame_id", "sequence", "source_file", "lr_sha256", "hr_sha256",
        "bicubic_y_psnr_db", "bicubic_y_ssim", "r0_fp32_y_psnr_db", "r0_fp32_y_ssim",
        "r0_int_y_psnr_db", "r0_int_y_ssim", "bicubic_psnr_full_db", "bicubic_ssim_full",
        "r0_fp32_psnr_full_db", "r0_fp32_ssim_full", "r0_int_psnr_full_db", "r0_int_ssim_full",
        "bicubic_4x_ms", "r0_fp32_cnn_ms", "r0_int_cpu_cnn_ms",
        "r0_fp32_postprocess_ms", "r0_int_postprocess_ms",
    ]
    for row in rows:
        clean = {column: row[column] for column in metric_columns}
        golden = output_by_id.get(row["frame_id"])
        if golden:
            clean["derived_4k_integer_golden"] = str(golden["output_bin"])
            clean["derived_4k_integer_golden_sha256"] = str(golden["output_sha256"])
        delivered_metrics.append(clean)
    metrics_path = output / "per_frame_metrics.csv"
    metric_columns.extend(["derived_4k_integer_golden", "derived_4k_integer_golden_sha256"])
    with metrics_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=metric_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(delivered_metrics)

    summary_target = output / "evaluation_summary.json"
    shutil.copyfile(summary_path, summary_target)
    benchmark_entry = None
    if args.benchmark_report:
        bench_src = args.benchmark_report.resolve()
        bench = json.loads(bench_src.read_text(encoding="utf-8"))
        if bench.get("schema") != "member-a-pc-path-benchmark-v1":
            raise ValueError("Unrecognized PC benchmark report")
        bench_target = output / "pc_path_benchmark.json"
        shutil.copyfile(bench_src, bench_target)
        benchmark_entry = {"path": bench_target.name, "sha256": sha256(bench_target)}

    manifest = {
        "schema": "member-a-pc-postprocess-4k-golden-v1",
        "status": "FROZEN_R0_INTEGER_REFERENCE_PLUS_PC_BICUBIC_SOFTWARE",
        "source_evaluation_summary_sha256": sha256(summary_path),
        "checkpoint_sha256": summary["frozen_checkpoint_sha256"],
        "formal_quant_params_sha256": summary["frozen_quant_params_sha256"],
        "input_contract": "960x540 Y8 synthetic FFmpeg bicubic downsample of the listed lossy decoded 4K UVG source frame; integer R0 produces 1920x1080 Y8",
        "output_contract": "1920x1080 integer R0 Y8; then Keys bicubic a=-0.5 to 3840x2160 Y8, row-major",
        "interpolation": "half-pixel coordinates, edge replication, separable float64 accumulation, nearest ties away from zero, uint8 saturation",
        "output_bytes_each": 8_294_400,
        "evaluated_pairs": len(rows),
        "per_frame_metrics_csv": metrics_path.name,
        "per_frame_metrics_csv_sha256": sha256(metrics_path),
        "evaluation_summary": summary_target.name,
        "evaluation_summary_sha256": sha256(summary_target),
        "pc_benchmark": benchmark_entry,
        "license_note": "Derived Y-only outputs for non-commercial academic work from UVG CC BY-NC source sequences; cite the source dataset and do not redistribute the original source video.",
        "frames": entries,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "frames": len(entries), "manifest_sha256": sha256(manifest_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
