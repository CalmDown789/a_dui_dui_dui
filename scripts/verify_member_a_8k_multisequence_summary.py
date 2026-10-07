"""Audit a source-safe aggregate report for the A-side 8K software study."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SEQUENCES = ("BodeMuseum", "NeptuneFountain2", "QuadrigaTree", "SubwayTree")
EXPECTED_FRAMES = (120, 240, 360, 480)
METHODS = ("direct_bicubic_x8", "r0_fp32", "r0_integer")
METRICS = ("psnr_db", "ssim")
EXPECTED_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
EXPECTED_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"


def _close(actual: float, expected: float, where: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12):
        raise AssertionError(f"Aggregate statistic mismatch at {where}: {actual} != {expected}")


def _require_sha256(value: str, where: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise AssertionError(f"Invalid SHA-256 at {where}")


def verify_summary(summary_path: Path, frame_report_paths: tuple[Path, ...] = ()) -> dict[str, object]:
    summary_path = summary_path.resolve()
    try:
        summary_path.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"The HHI-derived aggregate must remain under ignored .data/: {summary_path}") from exc
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    if data.get("schema") != "member-a-8k-multisequence-aggregate-v1":
        raise AssertionError("Unexpected 8K aggregate schema")
    if data.get("status") != "A_SIDE_MULTI_SEQUENCE_SOFTWARE_STUDY_NOT_BOARD_OR_VIDEO_ACCEPTANCE":
        raise AssertionError("Aggregate status must not imply board acceptance")
    if data["model"]["checkpoint_sha256"] != EXPECTED_CHECKPOINT_SHA256:
        raise AssertionError("8K report does not use the frozen R0 checkpoint")
    if data["model"]["quant_params_sha256"] != EXPECTED_QUANT_SHA256:
        raise AssertionError("8K report does not use the frozen R0 quantization package")

    counts = data.get("sequence_counts", {})
    expected_counts = {name: len(EXPECTED_FRAMES) for name in EXPECTED_SEQUENCES}
    if counts != expected_counts or int(data.get("frames", -1)) != sum(expected_counts.values()):
        raise AssertionError(f"Unexpected sequence/frame counts: {counts}")
    expected_sequence_list = sorted(EXPECTED_SEQUENCES)
    if data["source_attribution"].get("sequences") != expected_sequence_list:
        raise AssertionError("Source sequence names do not match the audited sequence set")

    rows = data.get("per_frame", [])
    expected_pairs = {(sequence, frame) for sequence in EXPECTED_SEQUENCES for frame in EXPECTED_FRAMES}
    observed_pairs: set[tuple[str, int]] = set()
    for row in rows:
        pair = (str(row["sequence_name"]), int(row["frame_index"]))
        if pair in observed_pairs:
            raise AssertionError(f"Duplicate sequence/frame entry: {pair}")
        observed_pairs.add(pair)
        for key in ("source_y_plane_sha256", "preparation_manifest_sha256", "lr_sha256", "hr_sha256"):
            _require_sha256(str(row[key]), f"{pair}/{key}")
        if set(row["scores"]) != set(METHODS) or set(row["output_sha256"]) != set(METHODS):
            raise AssertionError(f"Missing comparison method for {pair}")
        for method in METHODS:
            _require_sha256(str(row["output_sha256"][method]), f"{pair}/{method}/output")
            for border in ("full", "shave16"):
                for metric in METRICS:
                    value = float(row["scores"][method][border][metric])
                    if not math.isfinite(value):
                        raise AssertionError(f"Non-finite score for {pair}/{method}/{border}/{metric}")
    if observed_pairs != expected_pairs:
        missing = sorted(expected_pairs - observed_pairs)
        extra = sorted(observed_pairs - expected_pairs)
        raise AssertionError(f"Wrong frame set; missing={missing}, extra={extra}")

    verified_frame_files = 0
    if frame_report_paths:
        if len(frame_report_paths) != len(expected_pairs):
            raise AssertionError(f"Expected {len(expected_pairs)} frame reports, got {len(frame_report_paths)}")
        rows_by_pair = {(str(row["sequence_name"]), int(row["frame_index"])): row for row in rows}
        checked_reports: set[tuple[str, int]] = set()
        for report_path in frame_report_paths:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            source = report["source_attribution"]
            sequence = source.get("sequence_name")
            if not sequence:
                title = source.get("title", "")
                sequence = title.removeprefix("8K Berlin Test Sequences - ").removesuffix(" SDR")
            frame_index = int(source["frame_index"])
            pair_key = (str(sequence), frame_index)
            if pair_key in checked_reports or pair_key not in rows_by_pair:
                raise AssertionError(f"Unexpected or duplicate frame report: {pair_key}")
            checked_reports.add(pair_key)
            row = rows_by_pair[pair_key]
            pair = report["pair"]
            if pair["hr_sha256"] != row["hr_sha256"] or pair["lr_sha256"] != row["lr_sha256"]:
                raise AssertionError(f"Frame report hashes differ from aggregate for {pair_key}")
            if pair["preparation_manifest_sha256"] != row["preparation_manifest_sha256"]:
                raise AssertionError(f"Preparation manifest hash differs from aggregate for {pair_key}")
            hr_path = Path(pair["hr_path_local"]).resolve()
            lr_path = Path(pair["lr_path_local"]).resolve()
            for data_path in (hr_path, lr_path):
                try:
                    data_path.relative_to(ROOT / ".data")
                except ValueError as exc:
                    raise ValueError(f"Source-derived file must stay under ignored .data/: {data_path}") from exc
            manifest_path = hr_path.parent / "preparation_manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            if hashlib.sha256(manifest_bytes).hexdigest() != pair["preparation_manifest_sha256"]:
                raise AssertionError(f"Preparation manifest content mismatch for {pair_key}")
            preparation = json.loads(manifest_bytes.decode("utf-8"))
            preparation_source = preparation["source"]
            if preparation_source.get("sequence_name", sequence) != sequence or int(preparation_source["frame_index"]) != frame_index:
                raise AssertionError(f"Preparation source identity mismatch for {pair_key}")
            expected_files = (
                (hr_path, pair["hr_sha256"], 7680 * 4320, preparation["conversion"]["hr_y8"]),
                (lr_path, pair["lr_sha256"], 960 * 540, preparation["conversion"]["lr_y8"]),
            )
            for data_path, expected_sha, expected_size, metadata in expected_files:
                content = data_path.read_bytes()
                actual_sha = hashlib.sha256(content).hexdigest()
                if len(content) != expected_size or actual_sha != expected_sha:
                    raise AssertionError(f"Prepared image hash/size mismatch for {pair_key}: {data_path.name}")
                if metadata["file"] != data_path.name or metadata["bytes"] != expected_size or metadata["sha256"] != actual_sha:
                    raise AssertionError(f"Preparation file manifest mismatch for {pair_key}: {data_path.name}")
            verified_frame_files += 1
        if checked_reports != expected_pairs:
            raise AssertionError("The supplied per-frame reports do not cover the full sequence/frame set")

    for border in ("full", "shave16"):
        for method in METHODS:
            for metric in METRICS:
                values = [float(row["scores"][method][border][metric]) for row in rows]
                _close(data["mean_scores"][border][method][metric], statistics.fmean(values),
                       f"mean_scores/{border}/{method}/{metric}")
        for method in ("r0_fp32", "r0_integer"):
            for metric in METRICS:
                expected_gain = (
                    float(data["mean_scores"][border][method][metric])
                    - float(data["mean_scores"][border]["direct_bicubic_x8"][metric])
                )
                _close(data["mean_gains_vs_direct_bicubic_x8"][border][method][metric], expected_gain,
                       f"mean_gains/{border}/{method}/{metric}")

    for sequence in EXPECTED_SEQUENCES:
        subset = [row for row in rows if row["sequence_name"] == sequence]
        if data["frame_indices_by_sequence"][sequence] != list(EXPECTED_FRAMES):
            raise AssertionError(f"Unexpected frame indices for {sequence}")
        for border in ("full", "shave16"):
            for method in METHODS:
                for metric in METRICS:
                    values = [float(row["scores"][method][border][metric]) for row in subset]
                    _close(data["per_sequence_mean_scores"][sequence][border][method][metric],
                           statistics.fmean(values), f"per_sequence/{sequence}/{border}/{method}/{metric}")
            for method in ("r0_fp32", "r0_integer"):
                for metric in METRICS:
                    expected_gain = (
                        float(data["per_sequence_mean_scores"][sequence][border][method][metric])
                        - float(data["per_sequence_mean_scores"][sequence][border]["direct_bicubic_x8"][metric])
                    )
                    _close(data["per_sequence_gains_vs_direct_bicubic_x8"][sequence][border][method][metric],
                           expected_gain, f"per_sequence_gain/{sequence}/{border}/{method}/{metric}")

    frame_gains = [
        float(row["scores"]["r0_integer"]["shave16"]["psnr_db"])
        - float(row["scores"]["direct_bicubic_x8"]["shave16"]["psnr_db"])
        for row in rows
    ]
    if not all(gain > 0.0 for gain in frame_gains):
        raise AssertionError("At least one sampled frame does not show an integer PSNR gain over direct bicubic")

    return {
        "status": "PASS_A_SIDE_8K_MULTISEQUENCE_SOFTWARE_SUMMARY",
        "board_acceptance": False,
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "frames": len(rows),
        "frame_reports_and_local_files_verified": verified_frame_files,
        "sequence_counts": counts,
        "integer_psnr_gain_frames": len(frame_gains),
        "integer_psnr_gain_range_shave16_db": [min(frame_gains), max(frame_gains)],
        "integer_mean_gain_shave16_db": data["mean_gains_vs_direct_bicubic_x8"]["shave16"]["r0_integer"]["psnr_db"],
        "integer_mean_gain_shave16_ssim": data["mean_gains_vs_direct_bicubic_x8"]["shave16"]["r0_integer"]["ssim"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / ".data/member_a_task_20261008/hhi_8k_multisequence/aggregate_8k_16frames_verified.json",
    )
    parser.add_argument(
        "--frame-report",
        type=Path,
        action="append",
        default=[],
        help="Optional per-frame JSON report; pass all 16 to also recheck local source-derived file hashes",
    )
    args = parser.parse_args()
    print(json.dumps(verify_summary(args.summary, tuple(args.frame_report)), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
