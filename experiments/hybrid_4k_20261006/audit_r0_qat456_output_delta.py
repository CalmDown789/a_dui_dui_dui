from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean

import imageio_ffmpeg
import numpy as np

from member_a.fixed_reference import FixedReference

from .color_video_prototype import run_hybrid_integer_u8
from .compare_r0_qat456_video import (
    CHROMA_OUTPUT_BYTES,
    DEFAULT_CLIPS,
    OUTPUT_FRAME_BYTES,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    WIDTH,
    HEIGHT,
    Y_OUTPUT_BYTES,
    _finish_process,
    _load_run_inputs,
    _next_y,
    _read_exact,
    _start_y_stream,
    sha256_file,
)


def _pixel_delta_metrics(qat_y: np.ndarray, r0_y: np.ndarray) -> dict[str, float | int]:
    if qat_y.shape != r0_y.shape or qat_y.dtype != np.uint8 or r0_y.dtype != np.uint8:
        raise ValueError("Both outputs must be same-shape uint8 luma frames")
    diff = qat_y.astype(np.int16) - r0_y.astype(np.int16)
    abs_diff = np.abs(diff)
    p50, p95, p99 = np.quantile(abs_diff, [0.5, 0.95, 0.99])
    return {
        "changed_pixel_fraction": float(np.count_nonzero(diff) / diff.size),
        "mean_absolute_difference": float(abs_diff.mean()),
        "median_absolute_difference": float(p50),
        "p95_absolute_difference": float(p95),
        "p99_absolute_difference": float(p99),
        "max_absolute_difference": int(abs_diff.max()),
    }


def _read_progress(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _append_progress(path: Path, record: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def _write_summary(output_dir: Path, rows: list[dict[str, object]], manifest: dict[str, object]) -> None:
    by_clip: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_clip[str(row["clip"])].append(row)
    clips = []
    for clip in sorted(by_clip):
        group = by_clip[clip]
        clips.append(
            {
                "clip": clip,
                "frames": len(group),
                "mean_changed_pixel_fraction": fmean(float(row["changed_pixel_fraction"]) for row in group),
                "mean_absolute_difference": fmean(float(row["mean_absolute_difference"]) for row in group),
                "mean_p95_absolute_difference": fmean(float(row["p95_absolute_difference"]) for row in group),
                "mean_p99_absolute_difference": fmean(float(row["p99_absolute_difference"]) for row in group),
                "max_absolute_difference": max(int(row["max_absolute_difference"]) for row in group),
            }
        )
    expected = {str(item["clip"]): len(item["source_indices"]) for item in manifest["clips"]}
    actual = {clip: len(group) for clip, group in by_clip.items()}
    full_complete = actual == expected
    if not full_complete:
        return
    overall = {
        "frames": len(rows),
        "clips": len(by_clip),
        "mean_changed_pixel_fraction": fmean(float(row["changed_pixel_fraction"]) for row in rows),
        "mean_absolute_difference": fmean(float(row["mean_absolute_difference"]) for row in rows),
        "mean_p95_absolute_difference": fmean(float(row["p95_absolute_difference"]) for row in rows),
        "mean_p99_absolute_difference": fmean(float(row["p99_absolute_difference"]) for row in rows),
        "max_absolute_difference": max(int(row["max_absolute_difference"]) for row in rows),
    }
    summary = {
        "schema": "member-a-r0-qat456-output-delta-v1",
        "status": "FULL_10_CLIP_OUTPUT_DELTA_AUDIT",
        "scope": "A-side PC integer-reference output difference only; not FPGA or board acceptance",
        "comparison": "Per-pixel absolute difference between the final uint8 Y frames from frozen R0 integer and experimental QAT seed456 integer, same input frame and same Keys x2 post-resize.",
        "source_comparison_manifest_sha256": manifest["source_comparison_manifest_sha256"],
        "candidate_quant_params_sha256": manifest["candidate_quant_params_sha256"],
        "frozen_quant_params_sha256": manifest["frozen_quant_params_sha256"],
        "full_frame_counts": actual,
        "overall": overall,
        "clips": clips,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (output_dir / "per_clip_output_delta.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(clips[0].keys()))
        writer.writeheader()
        writer.writerows(clips)


def main() -> None:
    matrix_root = Path(".data/hybrid_4k_20261006/video_acceptance_20261006")
    candidate_quant_dir = Path(
        ".data/hybrid_4k_20261006/quant_candidate_acceptance_20261006_samecal_r0f_r0t_r0qat/R0QAT/quant"
    )
    frozen_quant_dir = Path("artifacts/quant")
    comparison_dir = Path(".data/hybrid_4k_20261006/r0_vs_qat456_video_20261006")
    output_dir = Path(".data/hybrid_4k_20261006/r0_qat456_output_delta_20261007").resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError("Output-delta artifacts must remain under ignored .data/") from exc
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison_manifest_path = comparison_dir / "run_manifest.json"
    if not comparison_manifest_path.is_file():
        raise FileNotFoundError(comparison_manifest_path)
    comparison_manifest_hash = sha256_file(comparison_manifest_path)
    inputs, candidate_params_hash, _ = _load_run_inputs(matrix_root, DEFAULT_CLIPS, candidate_quant_dir)
    frozen_params_hash = sha256_file(frozen_quant_dir / "quant_params.json")
    manifest = {
        "schema": "member-a-r0-qat456-output-delta-run-v1",
        "source_comparison_manifest_sha256": comparison_manifest_hash,
        "candidate_quant_params_sha256": candidate_params_hash,
        "frozen_quant_params_sha256": frozen_params_hash,
        "clips": [
            {
                "clip": str(entry["clip"]),
                "source_sha256": str(entry["source_sha256"]),
                "source_indices": entry["source_indices"],
                "candidate_summary_sha256": str(entry["summary_sha256"]),
                "candidate_raw_output_bytes": int(entry["raw_output"].stat().st_size),
            }
            for entry in inputs
        ],
    }
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise ValueError("Output-delta directory belongs to different source/model data")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    progress_path = output_dir / "per_frame_output_delta.jsonl"
    rows = _read_progress(progress_path)
    key_rows = [(str(row["clip"]), int(row["frame_index"])) for row in rows]
    if len(set(key_rows)) != len(key_rows):
        raise ValueError("Output-delta progress contains duplicate clip/frame keys")
    completed = set(key_rows)
    expected_counts = {str(entry["clip"]): len(entry["source_indices"]) for entry in inputs}
    existing_counts = {clip: sum(key[0] == clip for key in completed) for clip in expected_counts}
    if any(existing_counts[clip] > expected_counts[clip] for clip in expected_counts):
        raise ValueError("Output-delta progress has more rows than the manifest permits")

    frozen = FixedReference(frozen_quant_dir)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    for entry in inputs:
        clip = str(entry["clip"])
        indices = entry["source_indices"]
        pending_ordinals = [ordinal for ordinal, frame_index in enumerate(indices) if (clip, frame_index) not in completed]
        if not pending_ordinals:
            continue
        requested = [indices[ordinal] for ordinal in pending_ordinals]
        source = entry["source"]
        low_process = _start_y_stream(
            ffmpeg,
            source,
            requested,
            source_fps=float(entry["source_fps"]),
            width=WIDTH,
            height=HEIGHT,
        )
        raw_output = entry["raw_output"]
        output_stream = raw_output.open("rb")
        processed = 0
        failed = False
        try:
            for ordinal, frame_index in zip(pending_ordinals, requested, strict=True):
                if low_process.stdout is None:
                    raise RuntimeError("FFmpeg luma pipe was not created")
                low_y = _next_y(low_process.stdout, WIDTH, HEIGHT)
                output_stream.seek(ordinal * OUTPUT_FRAME_BYTES)
                qat_y = np.frombuffer(_read_exact(output_stream, Y_OUTPUT_BYTES), dtype=np.uint8).reshape(OUTPUT_HEIGHT, OUTPUT_WIDTH).copy()
                output_stream.seek(ordinal * OUTPUT_FRAME_BYTES + Y_OUTPUT_BYTES + CHROMA_OUTPUT_BYTES)
                _, r0_y = run_hybrid_integer_u8(frozen, low_y, keys_a=-0.5)
                row = {
                    "clip": clip,
                    "sequence": str(entry["sequence"]),
                    "frame_index": int(frame_index),
                    "clip_ordinal": int(ordinal),
                    **_pixel_delta_metrics(qat_y, r0_y),
                }
                _append_progress(progress_path, row)
                rows.append(row)
                completed.add((clip, int(frame_index)))
                processed += 1
                if processed % 25 == 0:
                    print(f"{clip}: {processed}/{len(pending_ordinals)} frames audited", flush=True)
        except BaseException:
            failed = True
            raise
        finally:
            output_stream.close()
            _finish_process(low_process, terminate=failed)
        print(f"Completed {clip}: added {processed} frame-delta rows", flush=True)

    rows = _read_progress(progress_path)
    if len(rows) != sum(expected_counts.values()):
        print(f"Partial audit: {len(rows)}/{sum(expected_counts.values())} frame records; progress is resumable", flush=True)
        return
    _write_summary(output_dir, rows, manifest)
    print(json.dumps({"status": "FULL_10_CLIP_OUTPUT_DELTA_AUDIT", "frames": len(rows), "output_dir": str(output_dir)}, indent=2))


if __name__ == "__main__":
    main()
