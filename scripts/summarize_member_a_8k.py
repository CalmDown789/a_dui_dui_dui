"""Aggregate per-frame A-side 8K reports without storing image outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("direct_bicubic_x8", "r0_fp32", "r0_integer")
METRIC_KEYS = ("psnr_db", "ssim")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    try:
        output.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"Aggregated source-derived report must stay under ignored .data/: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    if len(reports) < 2:
        raise ValueError("Provide at least two distinct per-frame reports")
    first = reports[0]
    identity = (
        first["source_attribution"]["title"],
        first["source_attribution"]["source_page"],
        first["source_attribution"]["license"],
        first["model"]["checkpoint_sha256"],
        first["model"]["quant_params_sha256"],
        first["protocol"],
    )
    seen_frames: set[int] = set()
    rows: list[dict[str, object]] = []
    for report in reports:
        if report.get("schema") != "member-a-8k-single-frame-software-study-v1":
            raise ValueError("Unexpected per-frame report schema")
        current_identity = (
            report["source_attribution"]["title"],
            report["source_attribution"]["source_page"],
            report["source_attribution"]["license"],
            report["model"]["checkpoint_sha256"],
            report["model"]["quant_params_sha256"],
            report["protocol"],
        )
        if current_identity != identity:
            raise ValueError("Reports mix different sources, models, quantization, or evaluation protocols")
        frame_index = int(report["source_attribution"]["frame_index"])
        if frame_index in seen_frames:
            raise ValueError(f"Duplicate 8K source frame index: {frame_index}")
        seen_frames.add(frame_index)
        if set(report["scores"]) != set(METHODS):
            raise ValueError("A report is missing an expected comparison method")
        rows.append({
            "frame_index": frame_index,
            "source_y_plane_sha256": report["source_attribution"]["source_y_plane_sha256"],
            "preparation_manifest_sha256": report["pair"]["preparation_manifest_sha256"],
            "lr_sha256": report["pair"]["lr_sha256"],
            "hr_sha256": report["pair"]["hr_sha256"],
            "scores": report["scores"],
            "output_sha256": report["output_sha256"],
            "stage_times_ms": report["stage_times_ms"],
        })
    rows.sort(key=lambda row: int(row["frame_index"]))

    means: dict[str, dict[str, dict[str, float]]] = {}
    gains: dict[str, dict[str, dict[str, float]]] = {}
    timing_medians: dict[str, dict[str, float]] = {}
    for border in ("full", "shave16"):
        means[border] = {
            method: {
                key: statistics.fmean(float(row["scores"][method][border][key]) for row in rows)
                for key in METRIC_KEYS
            }
            for method in METHODS
        }
        gains[border] = {
            method: {
                key: means[border][method][key] - means[border]["direct_bicubic_x8"][key]
                for key in METRIC_KEYS
            }
            for method in ("r0_fp32", "r0_integer")
        }
    timing_keys = sorted({key for row in rows for method in row["stage_times_ms"].values() for key in method})
    for method in METHODS:
        timing_medians[method] = {
            key: statistics.median(
                float(row["stage_times_ms"].get(method, {}).get(key, float("nan")))
                for row in rows
                if key in row["stage_times_ms"].get(method, {})
            )
            for key in timing_keys
            if any(key in row["stage_times_ms"].get(method, {}) for row in rows)
        }

    source_attribution = dict(first["source_attribution"])
    source_attribution.pop("frame_index", None)
    source_attribution.pop("source_y_plane_sha256", None)
    result = {
        "schema": "member-a-8k-multiframe-aggregate-v1",
        "status": "A_SIDE_FOUR_FRAME_SOFTWARE_STUDY_NOT_BOARD_OR_VIDEO_ACCEPTANCE",
        "source_attribution": source_attribution,
        "model": first["model"],
        "protocol": first["protocol"],
        "frames": len(rows),
        "frame_indices": [row["frame_index"] for row in rows],
        "mean_scores": means,
        "mean_gains_vs_direct_bicubic_x8": gains,
        "median_stage_times_ms": timing_medians,
        "per_frame": rows,
        "limitations": [
            "Four frames from one 8K sequence are a small spatial sample, not a broad content or temporal-stability evaluation.",
            "The 540p input is synthetically downsampled; scores apply only to the documented FFmpeg bicubic degradation.",
            "The HHI source is CC BY-NC-ND. The repository publishes no source or derived images, only metrics and hashes.",
            "Software reference results do not establish FPGA resources, timing, bitstream, board output, or 8K real-time capability.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
