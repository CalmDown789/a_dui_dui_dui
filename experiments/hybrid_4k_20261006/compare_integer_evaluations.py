from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_rows(path: Path, sequence_prefix: str) -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    with Path(path).open("r", newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            sequence = row.get("sequence", "")
            image = row.get("image", "")
            if not sequence.startswith(sequence_prefix):
                continue
            key = (sequence, image)
            if key in rows:
                raise ValueError(f"Duplicate evaluation row: {key}")
            rows[key] = row
    if not rows:
        raise ValueError(f"No evaluation rows start with sequence prefix {sequence_prefix!r} in {path}")
    return rows


def compare_integer_evaluations(
    baseline_csv: Path,
    candidate_csv: Path,
    *,
    sequence_prefix: str,
    baseline_name: str,
    candidate_name: str,
) -> dict[str, Any]:
    baseline = _read_rows(baseline_csv, sequence_prefix)
    candidate = _read_rows(candidate_csv, sequence_prefix)
    if baseline.keys() != candidate.keys():
        missing = sorted(set(baseline) - set(candidate))
        extra = sorted(set(candidate) - set(baseline))
        raise ValueError(f"Evaluation samples differ; missing={missing[:3]}, extra={extra[:3]}")

    per_frame = []
    per_sequence: dict[str, list[dict[str, float]]] = defaultdict(list)
    for sequence, image in sorted(baseline):
        base = baseline[(sequence, image)]
        cand = candidate[(sequence, image)]
        for metric in ("bicubic_psnr_db", "bicubic_ssim"):
            if metric in base and metric in cand and float(base[metric]) != float(cand[metric]):
                raise ValueError(f"Shared {metric} differs for {sequence}/{image}")
        delta_psnr = float(cand["integer_psnr_db"]) - float(base["integer_psnr_db"])
        delta_ssim = float(cand["integer_ssim"]) - float(base["integer_ssim"])
        record = {
            "sequence": sequence,
            "image": image,
            "baseline_integer_psnr_db": float(base["integer_psnr_db"]),
            "candidate_integer_psnr_db": float(cand["integer_psnr_db"]),
            "candidate_minus_baseline_psnr_db": delta_psnr,
            "baseline_integer_ssim": float(base["integer_ssim"]),
            "candidate_integer_ssim": float(cand["integer_ssim"]),
            "candidate_minus_baseline_ssim": delta_ssim,
        }
        per_frame.append(record)
        per_sequence[sequence].append({"psnr_delta": delta_psnr, "ssim_delta": delta_ssim})

    sequence_summary = {}
    for sequence, records in sorted(per_sequence.items()):
        psnr = [record["psnr_delta"] for record in records]
        ssim = [record["ssim_delta"] for record in records]
        sequence_summary[sequence] = {
            "frames": len(records),
            "mean_candidate_minus_baseline_psnr_db": sum(psnr) / len(psnr),
            "min_candidate_minus_baseline_psnr_db": min(psnr),
            "max_candidate_minus_baseline_psnr_db": max(psnr),
            "mean_candidate_minus_baseline_ssim": sum(ssim) / len(ssim),
        }
    psnr_deltas = [record["candidate_minus_baseline_psnr_db"] for record in per_frame]
    ssim_deltas = [record["candidate_minus_baseline_ssim"] for record in per_frame]
    return {
        "schema": "member-a-integer-evaluation-comparison-v1",
        "status": "PAIRED_SOFTWARE_INTEGER_METRICS_ONLY_NOT_RTL_OR_BOARD_ACCEPTANCE",
        "protocol_sequence_prefix": sequence_prefix,
        "baseline_name": baseline_name,
        "baseline_csv": str(Path(baseline_csv).resolve()),
        "candidate_name": candidate_name,
        "candidate_csv": str(Path(candidate_csv).resolve()),
        "frames": len(per_frame),
        "mean_candidate_minus_baseline_psnr_db": sum(psnr_deltas) / len(psnr_deltas),
        "min_candidate_minus_baseline_psnr_db": min(psnr_deltas),
        "max_candidate_minus_baseline_psnr_db": max(psnr_deltas),
        "mean_candidate_minus_baseline_ssim": sum(ssim_deltas) / len(ssim_deltas),
        "per_sequence": sequence_summary,
        "per_frame": per_frame,
        "limitations": [
            "This is a paired comparison of software integer-reference CSV results on synthetic downscales of lossy UVG HEVC.",
            "The sequence count is small and frames within one sequence are temporally correlated.",
            "No RTL, synthesis, timing, bitstream, or board evidence is provided.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paired per-frame comparisons of integer-reference evaluation CSVs")
    parser.add_argument("--baseline-csv", type=Path, required=True)
    parser.add_argument("--candidate-csv", type=Path, required=True)
    parser.add_argument("--sequence-prefix", required=True, help="Use ffmpeg_ or uvg_ to select one protocol")
    parser.add_argument("--baseline-name", required=True)
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--output", type=Path, required=True, help="JSON output under ignored .data/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Comparison output must stay under ignored .data/: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing comparison: {output}")
    report = compare_integer_evaluations(
        args.baseline_csv,
        args.candidate_csv,
        sequence_prefix=args.sequence_prefix,
        baseline_name=args.baseline_name,
        candidate_name=args.candidate_name,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "frames": report["frames"], "mean_delta_psnr_db": report["mean_candidate_minus_baseline_psnr_db"], "per_sequence": report["per_sequence"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
