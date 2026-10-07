from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import imageio_ffmpeg

from member_a.fixed_reference import FixedReference

from .compare_r0_qat456_video import (
    DEFAULT_CLIPS,
    _load_run_inputs,
    _make_contact_sheets,
    _process_indices,
    _read_records,
)


def main() -> None:
    output_dir = Path(".data/hybrid_4k_20261006/r0_vs_qat456_video_20261006").resolve()
    progress_path = output_dir / "per_frame_progress.jsonl"
    scratch_dir = output_dir / "contact_rebuild"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    validation_path = scratch_dir / "rebuild_validation.jsonl"
    manifest_path = scratch_dir / "worst_cases_manifest.json"
    if validation_path.exists() or manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite contact rebuild evidence in {scratch_dir}")

    records = _read_records(progress_path)
    keys = [(str(row["clip"]), int(row["frame_index"])) for row in records]
    if len(records) != 1240 or len(set(keys)) != 1240:
        raise ValueError(f"Expected 1,240 unique paired frame records, got {len(records)} rows / {len(set(keys))} unique")

    matrix_root = Path(".data/hybrid_4k_20261006/video_acceptance_20261006")
    candidate_quant_dir = Path(
        ".data/hybrid_4k_20261006/quant_candidate_acceptance_20261006_samecal_r0f_r0t_r0qat/R0QAT/quant"
    )
    inputs, _, _ = _load_run_inputs(matrix_root, DEFAULT_CLIPS, candidate_quant_dir)
    by_clip = {str(entry["clip"]): entry for entry in inputs}
    per_clip_counts = {clip: sum(row["clip"] == clip for row in records) for clip in DEFAULT_CLIPS}
    expected_counts = {str(entry["clip"]): len(entry["source_indices"]) for entry in inputs}
    if per_clip_counts != expected_counts:
        raise ValueError(f"Per-clip frame counts mismatch: found {per_clip_counts}; expected {expected_counts}")

    selected = sorted(records, key=lambda row: float(row["qat_minus_r0_psnr_db"]))[:20]
    ordinals_by_clip: dict[str, list[int]] = defaultdict(list)
    for row in selected:
        ordinals_by_clip[str(row["clip"])].append(int(row["clip_ordinal"]))
    for clip, entry in by_clip.items():
        entry["sample_ordinals"] = sorted(ordinals_by_clip.get(clip, []))

    frozen = FixedReference(Path("artifacts/quant"))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    completed: set[tuple[str, int]] = set()
    worst_cases: list[dict[str, object]] = []
    checked = 0
    for clip in DEFAULT_CLIPS:
        entry = by_clip[clip]
        ordinals = entry["sample_ordinals"]
        if not ordinals:
            continue
        processed, timed_out = _process_indices(
            ffmpeg,
            entry,
            ordinals,
            frozen,
            validation_path,
            completed,
            deadline=None,
            allow_timeout=False,
            worst_cases=worst_cases,
            worst_count=20,
        )
        if timed_out or processed != len(ordinals):
            raise RuntimeError(f"Failed to regenerate all selected frames for {clip}: {processed}/{len(ordinals)}")
        checked += processed

    if checked != len(selected):
        raise RuntimeError(f"Rebuilt {checked} contact frames; expected {len(selected)}")
    validated = _read_records(validation_path)
    expected = {(str(row["clip"]), int(row["frame_index"])): row for row in selected}
    actual = {(str(row["clip"]), int(row["frame_index"])): row for row in validated}
    if actual.keys() != expected.keys():
        raise RuntimeError("Rebuilt contact frame set differs from the recorded worst-frame set")
    for key, row in expected.items():
        rebuilt = actual[key]
        for metric in ("r0_y_psnr_db", "r0_y_ssim", "qat456_y_psnr_db", "qat456_y_ssim"):
            if abs(float(row[metric]) - float(rebuilt[metric])) > 1e-7:
                raise RuntimeError(f"Rebuilt metric changed for {key} / {metric}")

    paths = _make_contact_sheets(worst_cases, output_dir)
    if len(paths) != 2 or any(not Path(path).is_file() for path in paths):
        raise RuntimeError(f"Contact sheet generation incomplete: {paths}")
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "member-a-r0-qat456-worst-contact-frames-v1",
                "verified_frame_count": checked,
                "source_record_count": len(records),
                "per_clip_frame_counts": per_clip_counts,
                "metric_reproduction_tolerance": 1e-7,
                "selected_frames": [
                    {
                        "clip": str(row["clip"]),
                        "frame_index": int(row["frame_index"]),
                        "clip_ordinal": int(row["clip_ordinal"]),
                        "qat_minus_r0_psnr_db": float(row["qat_minus_r0_psnr_db"]),
                    }
                    for row in selected
                ],
                "contact_sheets": [str(Path(path).name) for path in paths],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"verified_worst_frames": checked, "contact_sheets": paths, "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
