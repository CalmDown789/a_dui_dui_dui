from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def compare_summaries(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare two color-video runs only when their decoded source and frame protocol match."""
    identity_fields = (
        "source_video_sha256",
        "source_frame_indices",
        "source_fps_metadata",
        "output_fps_for_selected_frames",
        "input_format",
        "keys_a",
    )
    for key in identity_fields:
        if baseline.get(key) != candidate.get(key):
            raise ValueError(f"Runs are not directly comparable: {key} differs")
    baseline_rows = baseline.get("metrics", {}).get("per_frame", [])
    candidate_rows = candidate.get("metrics", {}).get("per_frame", [])
    if not baseline_rows or len(baseline_rows) != len(candidate_rows):
        raise ValueError("Runs must contain the same non-empty set of per-frame metrics")

    rows = []
    for base, cand in zip(baseline_rows, candidate_rows, strict=True):
        if base.get("frame_index") != cand.get("frame_index"):
            raise ValueError("Runs have different frame indices or ordering")
        if base.get("bicubic_y_psnr_db") != cand.get("bicubic_y_psnr_db"):
            raise ValueError(f"Bicubic PSNR differs at source frame {base.get('frame_index')}")
        if base.get("bicubic_y_ssim") != cand.get("bicubic_y_ssim"):
            raise ValueError(f"Bicubic SSIM differs at source frame {base.get('frame_index')}")
        rows.append(
            {
                "frame_index": base["frame_index"],
                "baseline_model_y_psnr_db": base["hybrid_y_psnr_db"],
                "candidate_model_y_psnr_db": cand["hybrid_y_psnr_db"],
                "candidate_minus_baseline_y_psnr_db": cand["hybrid_y_psnr_db"] - base["hybrid_y_psnr_db"],
                "baseline_model_y_ssim": base["hybrid_y_ssim"],
                "candidate_model_y_ssim": cand["hybrid_y_ssim"],
                "candidate_minus_baseline_y_ssim": cand["hybrid_y_ssim"] - base["hybrid_y_ssim"],
            }
        )
    psnr_deltas = [row["candidate_minus_baseline_y_psnr_db"] for row in rows]
    ssim_deltas = [row["candidate_minus_baseline_y_ssim"] for row in rows]
    return {
        "schema": "member-a-color-video-run-comparison-v1",
        "status": "SOFTWARE_METRIC_COMPARISON_ONLY_NOT_BOARD_OR_REALTIME_ACCEPTANCE",
        "sequence": baseline.get("sequence"),
        "source_video_sha256": baseline["source_video_sha256"],
        "source_frame_indices": baseline["source_frame_indices"],
        "baseline_model_mode": baseline.get("model_mode", "frozen_FP32_R0" if baseline.get("checkpoint_sha256") else None),
        "baseline_model_artifact": baseline.get("model_artifact", baseline.get("checkpoint")),
        "candidate_model_mode": candidate.get("model_mode", "frozen_FP32_R0" if candidate.get("checkpoint_sha256") else None),
        "candidate_model_artifact": candidate.get("model_artifact", candidate.get("checkpoint")),
        "comparison": {
            "frames": len(rows),
            "mean_candidate_minus_baseline_y_psnr_db": sum(psnr_deltas) / len(psnr_deltas),
            "min_candidate_minus_baseline_y_psnr_db": min(psnr_deltas),
            "max_candidate_minus_baseline_y_psnr_db": max(psnr_deltas),
            "mean_candidate_minus_baseline_y_ssim": sum(ssim_deltas) / len(ssim_deltas),
            "per_frame": rows,
        },
        "limitations": [
            "Only the listed decoded UVG frames and this FFmpeg synthetic 540p degradation are compared.",
            "The reported values are software Y-plane metrics; they do not establish general visual quality, FPGA correctness, or real-time throughput.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare color-video demo summaries with exact input/frame identity checks")
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="JSON output path under ignored .data/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Comparison output must stay under ignored .data/: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing comparison: {output}")
    baseline = json.loads(args.baseline_summary.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_summary.read_text(encoding="utf-8"))
    comparison = compare_summaries(baseline, candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "comparison": comparison["comparison"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
