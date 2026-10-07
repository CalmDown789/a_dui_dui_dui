from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time
from collections import defaultdict
from statistics import fmean

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .color_video_prototype import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    WIDTH,
    HEIGHT,
    run_hybrid_integer_u8,
    unpack_yuv420_frame,
    yuv420_frame_bytes,
)
from .evaluate_hybrid import _metrics
from member_a.fixed_reference import FixedReference


DEFAULT_CLIPS = [
    "Bosphorus_5s",
    "ReadySetGo_5s",
    "CityAlley_0_5s",
    "CityAlley_6_11s",
    "FlowerFocus_0_5s",
    "FlowerFocus_6_11s",
    "FlowerKids_0_5s",
    "FlowerKids_6_11s",
    "FlowerPan_0_5s",
    "FlowerPan_6_11s",
]
Y_INPUT_BYTES = WIDTH * HEIGHT
Y_OUTPUT_BYTES = OUTPUT_WIDTH * OUTPUT_HEIGHT
CHROMA_INPUT_BYTES = Y_INPUT_BYTES // 2
CHROMA_OUTPUT_BYTES = Y_OUTPUT_BYTES // 2
INPUT_FRAME_BYTES = yuv420_frame_bytes(WIDTH, HEIGHT)
OUTPUT_FRAME_BYTES = yuv420_frame_bytes(OUTPUT_WIDTH, OUTPUT_HEIGHT)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError(f"FFmpeg stream ended with {remaining} bytes still expected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _decoder_command(
    ffmpeg: str,
    source: Path,
    source_indices: list[int],
    *,
    source_fps: float,
    output_width: int,
    output_height: int,
    raw_yuv420: bool,
) -> list[str]:
    if not source_indices:
        raise ValueError("Cannot start a decoder with no selected source frames")
    if source_indices != sorted(set(source_indices)):
        raise ValueError("Selected source frame indices must be strictly increasing")
    expression = "+".join(f"eq(n,{index})" for index in source_indices)
    video_filter = (
        f"select='{expression}',"
        f"scale={output_width}:{output_height}:flags=bicubic:in_range=tv:out_range=pc,"
        "format=yuv420p"
    )
    command = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if raw_yuv420:
        command.extend(
            [
                "-f",
                "rawvideo",
                "-pixel_format",
                "yuv420p",
                "-video_size",
                f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
                "-framerate",
                f"{source_fps:.8g}",
            ]
        )
    command.extend(["-i", str(source.resolve()), "-vf", video_filter, "-fps_mode", "vfr"])
    command.extend(
        [
            "-frames:v",
            str(len(source_indices)),
            "-pix_fmt",
            "yuv420p",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    )
    return command


def _start_y_stream(ffmpeg: str, source: Path, source_indices: list[int], *, source_fps: float, width: int, height: int):
    process = subprocess.Popen(
        _decoder_command(
            ffmpeg,
            source,
            source_indices,
            source_fps=source_fps,
            output_width=width,
            output_height=height,
            raw_yuv420=source.suffix.lower() in {".yuv", ".raw"},
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Failed to create FFmpeg pipe")
    return process


def _next_y(stream, width: int, height: int) -> np.ndarray:
    y_size = width * height
    chroma_size = y_size // 2
    y = np.frombuffer(_read_exact(stream, y_size), dtype=np.uint8).reshape(height, width).copy()
    _read_exact(stream, chroma_size)
    return y


def _finish_process(process, *, terminate: bool = False) -> None:
    if terminate and process.poll() is None:
        process.terminate()
    if process.stdout is not None:
        process.stdout.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr is not None else ""
    status = process.wait()
    if not terminate and status:
        raise RuntimeError(f"FFmpeg returned {status}: {stderr[-2000:]}")


def _select_sample_ordinals(frame_count: int, sample_count: int) -> list[int]:
    count = min(frame_count, sample_count)
    if count == 1:
        return [frame_count // 2]
    return sorted({round(index * (frame_count - 1) / (count - 1)) for index in range(count)})


def _crop_for_contact(image: np.ndarray, *, crop_width: int = 768, crop_height: int = 432) -> np.ndarray:
    height, width = image.shape
    crop_width = min(crop_width, width)
    crop_height = min(crop_height, height)
    x0 = (width - crop_width) // 2
    y0 = (height - crop_height) // 2
    crop = image[y0 : y0 + crop_height, x0 : x0 + crop_width]
    return np.asarray(Image.fromarray(crop).resize((480, 270), Image.Resampling.LANCZOS).convert("RGB"))


def _make_contact_sheets(worst: list[dict[str, object]], output_dir: Path) -> list[str]:
    if not worst:
        return []
    columns = ["4K reference Y", "Bicubic ×4", "Frozen R0 integer", "QAT seed456 integer"]
    cell_width, cell_height, label_height = 480, 270, 36
    full_sheet = Image.new("RGB", (cell_width * len(columns), (cell_height + label_height) * len(worst)), (24, 24, 24))
    crop_sheet = Image.new("RGB", full_sheet.size, (24, 24, 24))
    draw_full = ImageDraw.Draw(full_sheet)
    draw_crop = ImageDraw.Draw(crop_sheet)
    font = ImageFont.load_default()
    for row_index, record in enumerate(worst):
        title = f"{record['clip']} frame {record['frame_index']} | QAT−R0 {record['delta_psnr_db']:+.3f} dB"
        for col_index, label in enumerate(columns):
            x = col_index * cell_width
            y = row_index * (cell_height + label_height)
            draw_full.text((x + 6, y + 4), f"{title} | {label}", fill=(245, 245, 245), font=font)
            draw_crop.text((x + 6, y + 4), f"{title} | {label} (center crop)", fill=(245, 245, 245), font=font)
            full_sheet.paste(record["full"][label], (x, y + label_height))
            crop_sheet.paste(record["crop"][label], (x, y + label_height))
    paths = [
        output_dir / "worst_full_frame_contact_sheet.png",
        output_dir / "worst_center_crop_contact_sheet.png",
    ]
    full_sheet.save(paths[0], optimize=True)
    crop_sheet.save(paths[1], optimize=True)
    return [str(path) for path in paths]


def _load_run_inputs(matrix_root: Path, clip_names: list[str], candidate_quant_dir: Path):
    candidate_params = candidate_quant_dir / "quant_params.json"
    candidate_param_hash = sha256_file(candidate_params)
    candidate_bundle_manifest = candidate_quant_dir.parent / "bundle_manifest.json"
    candidate_bundle_hash = sha256_file(candidate_bundle_manifest) if candidate_bundle_manifest.is_file() else None
    inputs: list[dict[str, object]] = []
    source_hashes: dict[Path, str] = {}
    for clip_name in clip_names:
        summary_path = matrix_root / clip_name / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("model_mode") not in {"experimental_integer_QAT_candidate", "experimental_integer_candidate:R0QAT_seed456"}:
            raise ValueError(f"Unexpected candidate mode in {summary_path}: {summary.get('model_mode')}")
        if Path(summary["model_artifact"]).resolve() != candidate_quant_dir.resolve():
            raise ValueError(f"Candidate quant directory mismatch in {summary_path}")
        if summary.get("quant_params_sha256") != candidate_param_hash:
            raise ValueError(f"Candidate quantization hash mismatch in {summary_path}")
        source = Path(summary["source_video"])
        source_hash = summary["source_video_sha256"]
        if not source.is_file():
            raise FileNotFoundError(source)
        source_hashes.setdefault(source.resolve(), source_hash)
        raw_output = Path(summary["outputs"]["hybrid_yuv420p_raw"])
        if not raw_output.is_file() or raw_output.stat().st_size != int(summary["frames"]) * OUTPUT_FRAME_BYTES:
            raise ValueError(f"Candidate raw output is missing or has the wrong size: {raw_output}")
        indices = [int(value) for value in summary["source_frame_indices"]]
        metric_rows = summary["metrics"]["per_frame"]
        if len(indices) != int(summary["frames"]) or len(metric_rows) != len(indices):
            raise ValueError(f"Candidate per-frame metadata is inconsistent in {summary_path}")
        if [int(row["frame_index"]) for row in metric_rows] != indices:
            raise ValueError(f"Candidate frame indices do not match metric rows in {summary_path}")
        inputs.append(
            {
                "clip": clip_name,
                "sequence": summary["sequence"],
                "summary_path": summary_path,
                "summary_sha256": sha256_file(summary_path),
                "summary": summary,
                "source": source,
                "source_sha256": source_hash,
                "source_fps": float(summary["source_fps_metadata"]),
                "source_indices": indices,
                "raw_output": raw_output,
                "metric_rows": metric_rows,
            }
        )
    for source_path, expected_hash in source_hashes.items():
        if sha256_file(source_path) != expected_hash:
            raise ValueError(f"Source video hash changed: {source_path}")
    return inputs, candidate_param_hash, candidate_bundle_hash


def _append_record(progress_path: Path, record: dict[str, object]) -> None:
    with progress_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def _read_records(progress_path: Path) -> list[dict[str, object]]:
    if not progress_path.is_file():
        return []
    records = []
    with progress_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Corrupt progress file at line {line_number}") from exc
    return records


def _process_indices(
    ffmpeg: str,
    entry: dict[str, object],
    ordinals: list[int],
    frozen: FixedReference,
    progress_path: Path,
    completed: set[tuple[str, int]],
    *,
    deadline: float | None,
    allow_timeout: bool,
    worst_cases: list[dict[str, object]],
    worst_count: int,
) -> tuple[int, bool]:
    clip = str(entry["clip"])
    summary = entry["summary"]
    source_indices = entry["source_indices"]
    pending = [ordinal for ordinal in ordinals if (clip, source_indices[ordinal]) not in completed]
    if not pending:
        return 0, False
    requested = [source_indices[ordinal] for ordinal in pending]
    source = entry["source"]
    source_fps = float(entry["source_fps"])
    low_proc = _start_y_stream(ffmpeg, source, requested, source_fps=source_fps, width=WIDTH, height=HEIGHT)
    ref_proc = _start_y_stream(ffmpeg, source, requested, source_fps=source_fps, width=OUTPUT_WIDTH, height=OUTPUT_HEIGHT)
    raw_output = entry["raw_output"]
    candidate_metrics = entry["metric_rows"]
    output_stream = raw_output.open("rb")
    processed = 0
    timed_out = False
    try:
        for ordinal, frame_index in zip(pending, requested, strict=True):
            if allow_timeout and deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            low_y = _next_y(low_proc.stdout, WIDTH, HEIGHT)
            ref_y = _next_y(ref_proc.stdout, OUTPUT_WIDTH, OUTPUT_HEIGHT)
            output_stream.seek(ordinal * OUTPUT_FRAME_BYTES)
            qat_y = np.frombuffer(_read_exact(output_stream, Y_OUTPUT_BYTES), dtype=np.uint8).reshape(OUTPUT_HEIGHT, OUTPUT_WIDTH).copy()
            bicubic_psnr = float(candidate_metrics[ordinal]["bicubic_y_psnr_db"])
            bicubic_ssim = float(candidate_metrics[ordinal]["bicubic_y_ssim"])
            qat_psnr, qat_ssim = _metrics(ref_y, qat_y)
            recorded = candidate_metrics[ordinal]
            if abs(qat_psnr - float(recorded["hybrid_y_psnr_db"])) > 1e-7 or abs(qat_ssim - float(recorded["hybrid_y_ssim"])) > 1e-7:
                raise ValueError(f"Stored QAT output does not reproduce its recorded metrics: {clip} frame {frame_index}")
            _, r0_y = run_hybrid_integer_u8(frozen, low_y, keys_a=-0.5)
            r0_psnr, r0_ssim = _metrics(ref_y, r0_y)
            record = {
                "clip": clip,
                "sequence": str(entry["sequence"]),
                "frame_index": int(frame_index),
                "clip_ordinal": int(ordinal),
                "sampled": bool(ordinal in entry["sample_ordinals"]),
                "bicubic_y_psnr_db": bicubic_psnr,
                "bicubic_y_ssim": bicubic_ssim,
                "r0_y_psnr_db": r0_psnr,
                "r0_y_ssim": r0_ssim,
                "qat456_y_psnr_db": qat_psnr,
                "qat456_y_ssim": qat_ssim,
                "qat_minus_r0_psnr_db": qat_psnr - r0_psnr,
                "qat_minus_r0_ssim": qat_ssim - r0_ssim,
                "r0_minus_bicubic_psnr_db": r0_psnr - bicubic_psnr,
                "qat_minus_bicubic_psnr_db": qat_psnr - bicubic_psnr,
            }
            _append_record(progress_path, record)
            completed.add((clip, int(frame_index)))
            processed += 1
            delta = float(record["qat_minus_r0_psnr_db"])
            if len(worst_cases) < worst_count or delta < max(float(case["delta_psnr_db"]) for case in worst_cases):
                from .color_video_prototype import run_bicubic4x_u8

                bicubic_y = run_bicubic4x_u8(low_y, keys_a=-0.5)
                labels = ["4K reference Y", "Bicubic ×4", "Frozen R0 integer", "QAT seed456 integer"]
                images = [ref_y, bicubic_y, r0_y, qat_y]
                full = {
                    label: Image.fromarray(image).resize((480, 270), Image.Resampling.LANCZOS).convert("RGB")
                    for label, image in zip(labels, images, strict=True)
                }
                crops = {
                    label: Image.fromarray(_crop_for_contact(image))
                    for label, image in zip(labels, images, strict=True)
                }
                case = {
                    "clip": clip,
                    "frame_index": int(frame_index),
                    "delta_psnr_db": delta,
                    "full": full,
                    "crop": crops,
                }
                worst_cases.append(case)
                worst_cases.sort(key=lambda item: float(item["delta_psnr_db"]))
                del worst_cases[worst_count:]
            if processed % 25 == 0:
                print(f"{clip}: {processed}/{len(pending)} new paired frames in this pass", flush=True)
    finally:
        output_stream.close()
        _finish_process(low_proc, terminate=timed_out)
        _finish_process(ref_proc, terminate=timed_out)
    return processed, timed_out


def _bootstrap_ci(sequence_means: dict[str, float], *, seed: int = 20261006) -> tuple[float, float] | None:
    values = np.asarray(list(sequence_means.values()), dtype=np.float64)
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(20000, len(values)), replace=True).mean(axis=1)
    low, high = np.quantile(samples, [0.025, 0.975])
    return float(low), float(high)


def _delta_distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("Delta distribution requires at least one finite value")
    p05, median, p95 = np.quantile(array, [0.05, 0.5, 0.95])
    return {
        "min": float(array.min()),
        "p05": float(p05),
        "median": float(median),
        "p95": float(p95),
        "max": float(array.max()),
    }


def _write_results(
    output_dir: Path,
    report_path: Path,
    records: list[dict[str, object]],
    *,
    run_manifest: dict[str, object],
    full_complete: bool,
    timeout_reached: bool,
    contact_paths: list[str],
) -> None:
    by_clip_all: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        by_clip_all[str(row["clip"])].append(row)
    primary = records if full_complete else [row for row in records if row["sampled"]]
    if not primary:
        return
    fieldnames = list(primary[0].keys())
    with (output_dir / "per_frame_paired_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda row: (str(row["clip"]), int(row["clip_ordinal"]))))
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in primary:
        grouped[str(row["clip"])].append(row)
    clip_rows = []
    for clip, rows in grouped.items():
        clip_rows.append(
            {
                "clip": clip,
                "sequence": str(rows[0]["sequence"]),
                "frames_used": len(rows),
                "r0_mean_psnr_db": fmean(float(row["r0_y_psnr_db"]) for row in rows),
                "qat456_mean_psnr_db": fmean(float(row["qat456_y_psnr_db"]) for row in rows),
                "qat_minus_r0_mean_psnr_db": fmean(float(row["qat_minus_r0_psnr_db"]) for row in rows),
                "r0_mean_ssim": fmean(float(row["r0_y_ssim"]) for row in rows),
                "qat456_mean_ssim": fmean(float(row["qat456_y_ssim"]) for row in rows),
                "qat_minus_r0_mean_ssim": fmean(float(row["qat_minus_r0_ssim"]) for row in rows),
                "qat_psnr_regression_frames": sum(float(row["qat_minus_r0_psnr_db"]) < 0.0 for row in rows),
            }
        )
    clip_rows.sort(key=lambda row: str(row["clip"]))
    with (output_dir / "per_clip_paired_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(clip_rows[0].keys()))
        writer.writeheader()
        writer.writerows(clip_rows)

    seq_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in primary:
        seq_groups[str(row["sequence"])].append(row)
    sequence_means = {
        sequence: fmean(float(row["qat_minus_r0_psnr_db"]) for row in rows)
        for sequence, rows in seq_groups.items()
    }
    sequence_ssim_means = {
        sequence: fmean(float(row["qat_minus_r0_ssim"]) for row in rows)
        for sequence, rows in seq_groups.items()
    }
    ci = _bootstrap_ci(sequence_means)
    ssim_ci = _bootstrap_ci(sequence_ssim_means)
    leave_one_sequence_out = {
        sequence: fmean(
            float(row["qat_minus_r0_psnr_db"])
            for row in primary
            if str(row["sequence"]) != sequence
        )
        for sequence in seq_groups
        if len(seq_groups) > 1
    }
    psnr_delta_distribution = _delta_distribution(
        [float(row["qat_minus_r0_psnr_db"]) for row in primary]
    )
    ssim_delta_distribution = _delta_distribution(
        [float(row["qat_minus_r0_ssim"]) for row in primary]
    )
    overall = {
        "frames_in_primary_analysis": len(primary),
        "clips_in_primary_analysis": len(grouped),
        "sequences_in_primary_analysis": len(seq_groups),
        "r0_mean_psnr_db": fmean(float(row["r0_y_psnr_db"]) for row in primary),
        "qat456_mean_psnr_db": fmean(float(row["qat456_y_psnr_db"]) for row in primary),
        "qat_minus_r0_mean_psnr_db": fmean(float(row["qat_minus_r0_psnr_db"]) for row in primary),
        "r0_mean_ssim": fmean(float(row["r0_y_ssim"]) for row in primary),
        "qat456_mean_ssim": fmean(float(row["qat456_y_ssim"]) for row in primary),
        "qat_minus_r0_mean_ssim": fmean(float(row["qat_minus_r0_ssim"]) for row in primary),
        "qat_psnr_regression_frames": sum(float(row["qat_minus_r0_psnr_db"]) < 0.0 for row in primary),
        "qat_ssim_regression_frames": sum(float(row["qat_minus_r0_ssim"]) < 0.0 for row in primary),
        "mean_psnr_delta_bootstrap_95pct_ci_by_sequence": list(ci) if ci else None,
        "sequence_weighted_mean_psnr_delta_db": fmean(sequence_means.values()),
        "mean_ssim_delta_bootstrap_95pct_ci_by_sequence": list(ssim_ci) if ssim_ci else None,
        "sequence_weighted_mean_ssim_delta": fmean(sequence_ssim_means.values()),
        "per_sequence_mean_psnr_delta_db": sequence_means,
        "per_sequence_mean_ssim_delta": sequence_ssim_means,
        "per_frame_psnr_delta_db_distribution": psnr_delta_distribution,
        "per_frame_ssim_delta_distribution": ssim_delta_distribution,
        "leave_one_sequence_out_frame_weighted_mean_psnr_delta_db": leave_one_sequence_out,
    }
    full_frame_counts = {clip: len(rows) for clip, rows in by_clip_all.items()}
    summary = {
        "schema": "member-a-r0-vs-qat456-video-v1",
        "status": "FULL_10_CLIP_PAIRED_EVALUATION" if full_complete else "STRATIFIED_SAMPLE_WITH_PARTIAL_EXTENSION" if timeout_reached else "STRATIFIED_SAMPLE_EVALUATION",
        "scope": "仅 A 侧 PC 整数参考对照；不是 B RTL、FPGA、板卡或实时性能验收",
        "primary_analysis_rule": "Use all frames only when all 10 clips are complete; otherwise use the predeclared evenly spaced sample only.",
        "full_frame_counts_completed": full_frame_counts,
        "overall": overall,
        "clips": clip_rows,
        "source_manifest": run_manifest,
    }
    output_delta_path = output_dir.parent / "r0_qat456_output_delta_20261007" / "summary.json"
    output_delta_summary = None
    if output_delta_path.is_file():
        output_delta_summary = json.loads(output_delta_path.read_text(encoding="utf-8"))
        expected_manifest_hash = sha256_file(output_dir / "run_manifest.json")
        if output_delta_summary.get("source_comparison_manifest_sha256") != expected_manifest_hash:
            raise ValueError("R0/QAT output-delta audit refers to a different comparison run")
        if output_delta_summary.get("status") != "FULL_10_CLIP_OUTPUT_DELTA_AUDIT":
            raise ValueError("R0/QAT output-delta audit is not complete")
        summary["output_delta_audit"] = {
            "summary_sha256": sha256_file(output_delta_path),
            "overall": output_delta_summary["overall"],
            "clips": output_delta_summary["clips"],
        }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    worst = sorted(primary, key=lambda row: float(row["qat_minus_r0_psnr_db"]))[:20]
    contact_files = [Path(path).name for path in contact_paths]
    lines = [
        "# 冻结 R0 与 QAT seed456：10 段视频整数参考配对评测",
        "",
        f"状态：`{summary['status']}`。范围：{summary['scope']}。",
        "",
        f"主分析样本：{overall['frames_in_primary_analysis']} 帧、{overall['clips_in_primary_analysis']} 段、{overall['sequences_in_primary_analysis']} 个序列。",
        "",
        "同一公开 3840×2160 源帧经同一 FFmpeg bicubic/range 流程生成 960×540 Y 输入，分别送入冻结 R0 与实验性 QAT seed456 整数模型，再经共同的 ×2 bicubic 输出到 3840×2160；仅对 Y 平面计算 PSNR/SSIM，边界裁剪 8 像素。",
        "",
        "| 指标 | 冻结 R0 | QAT seed456 | QAT − R0 |",
        "| --- | ---: | ---: | ---: |",
        f"| Y-PSNR (dB) | {overall['r0_mean_psnr_db']:.4f} | {overall['qat456_mean_psnr_db']:.4f} | {overall['qat_minus_r0_mean_psnr_db']:+.4f} |",
        f"| SSIM | {overall['r0_mean_ssim']:.6f} | {overall['qat456_mean_ssim']:.6f} | {overall['qat_minus_r0_mean_ssim']:+.6f} |",
        f"| 逐帧回归数 | — | — | PSNR {overall['qat_psnr_regression_frames']} 帧；SSIM {overall['qat_ssim_regression_frames']} 帧 |",
        "",
        "## 分片结果",
        "",
        "| 片段 | 帧数 | R0 PSNR | QAT PSNR | ΔPSNR | R0 SSIM | QAT SSIM | ΔSSIM | QAT PSNR 回归帧 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in clip_rows:
        lines.append(
            f"| {row['clip']} | {row['frames_used']} | {row['r0_mean_psnr_db']:.4f} | {row['qat456_mean_psnr_db']:.4f} | {row['qat_minus_r0_mean_psnr_db']:+.4f} | {row['r0_mean_ssim']:.6f} | {row['qat456_mean_ssim']:.6f} | {row['qat_minus_r0_mean_ssim']:+.6f} | {row['qat_psnr_regression_frames']} |"
        )
    if output_delta_summary is not None:
        delta = output_delta_summary["overall"]
        lines.extend(
            [
                "",
                "## 两个整数版本的输出差异（全 1,240 帧）",
                "",
                f"QAT 相对 R0 的输出中，平均 {delta['mean_changed_pixel_fraction']:.1%} 的 Y 像素发生变化；逐帧平均绝对差 {delta['mean_absolute_difference']:.4f} 灰度级，逐帧 P95 差值均值 {delta['mean_p95_absolute_difference']:.4f}，最大绝对差 {delta['max_absolute_difference']}。这刻画的是两个模型输出之间的差异，不是相对原始真值的误差。",
                "",
                "| 片段 | 改变像素比例 | 平均绝对差 | 平均 P95 差值 | 最大差值 |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for delta_clip in output_delta_summary["clips"]:
            lines.append(
                f"| {delta_clip['clip']} | {delta_clip['mean_changed_pixel_fraction']:.1%} | {delta_clip['mean_absolute_difference']:.4f} | {delta_clip['mean_p95_absolute_difference']:.4f} | {delta_clip['max_absolute_difference']} |"
            )
    lines.extend(
        [
            "",
            "## 数据与模型",
            "",
            "测试素材来自 UVG 公开 4K 序列，许可为 CC BY-NC（非商业学术用途）；原始视频未加入仓库。正式冻结模型读取 `artifacts/quant`；QAT seed456 是实验候选，权重与参数文件哈希记录在 `run_manifest.json`，不会覆盖 R0。",
            "",
            "## 统计解释与边界",
            "",
            f"按 6 个 UVG 序列为抽样簇的描述性 bootstrap 95% 区间：[{ci[0]:.4f}, {ci[1]:.4f}] dB。视频帧存在时间相关，区间仅作不确定性提示；不把每帧当作独立视频样本。" if ci else "序列数不足，未计算 bootstrap 区间。",
            f"序列等权 ΔPSNR 均值为 {overall['sequence_weighted_mean_psnr_delta_db']:+.4f} dB；帧级 ΔPSNR 的 5/50/95 分位为 {psnr_delta_distribution['p05']:+.4f}/{psnr_delta_distribution['median']:+.4f}/{psnr_delta_distribution['p95']:+.4f} dB。逐一去掉任一序列后，帧加权均值范围为 {min(leave_one_sequence_out.values()):+.4f} 至 {max(leave_one_sequence_out.values()):+.4f} dB。",
            f"按序列聚类的 ΔSSIM 描述性 bootstrap 95% 区间：[{ssim_ci[0]:+.6f}, {ssim_ci[1]:+.6f}]；帧级 ΔSSIM 的 5/50/95 分位为 {ssim_delta_distribution['p05']:+.6f}/{ssim_delta_distribution['median']:+.6f}/{ssim_delta_distribution['p95']:+.6f}。" if ssim_ci else "序列数不足，未计算 SSIM bootstrap 区间。",
            "",
            "本次 QAT 相对 R0 的平均增益较小，应视为质量评估信号，不足以据此替换正式 R0。后续如采用该候选，仍需成员 B 独立 RTL 黄金对拍；本报告不证明 RTL/FPGA、板卡图像、真实摄像头、时域稳定或实时性能。",
            "",
            "复核文件：`per_frame_paired_metrics.csv`、`per_clip_paired_metrics.csv`、`summary.json`。最差帧接触表：",
        ]
    )
    if not contact_files:
        contact_files = [
            name
            for name in (
                "worst_full_frame_contact_sheet.png",
                "worst_center_crop_contact_sheet.png",
            )
            if (output_dir / name).is_file()
        ]
    lines.extend(f"- `{Path(path).name}`" for path in sorted(set(contact_files)))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired full-frame integer quality comparison for frozen R0 and QAT seed456")
    parser.add_argument("--matrix-root", type=Path, default=Path(".data/hybrid_4k_20261006/video_acceptance_20261006"))
    parser.add_argument("--clips", nargs="+", default=DEFAULT_CLIPS)
    parser.add_argument("--candidate-quant-dir", type=Path, default=Path(".data/hybrid_4k_20261006/quant_candidate_acceptance_20261006_samecal_r0f_r0t_r0qat/R0QAT/quant"))
    parser.add_argument("--frozen-quant-dir", type=Path, default=Path("artifacts/quant"))
    parser.add_argument("--output-dir", type=Path, default=Path(".data/hybrid_4k_20261006/r0_vs_qat456_video_20261006"))
    parser.add_argument("--report", type=Path, default=Path("experiments/hybrid_4k_20261006/R0_VS_QAT456_VIDEO_REPORT_2026-10-06.md"))
    parser.add_argument("--sample-per-clip", type=int, default=24)
    parser.add_argument("--max-runtime-seconds", type=int, default=5400, help="Time cap for full extension after stratified samples")
    parser.add_argument("--sample-only", action="store_true", help="Evaluate only the predeclared evenly spaced sample")
    parser.add_argument("--worst-count", type=int, default=20)
    args = parser.parse_args()
    if args.sample_per_clip <= 0 or args.max_runtime_seconds <= 0 or args.worst_count <= 0:
        raise ValueError("sample-per-clip, max-runtime-seconds and worst-count must be positive")
    matrix_root = args.matrix_root.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError("Generated metrics and visual artifacts must stay inside ignored .data/") from exc
    candidate_quant_dir = args.candidate_quant_dir.resolve()
    frozen_quant_dir = args.frozen_quant_dir.resolve()
    inputs, candidate_param_hash, candidate_bundle_hash = _load_run_inputs(matrix_root, args.clips, candidate_quant_dir)
    frozen_param_hash = sha256_file(frozen_quant_dir / "quant_params.json")
    frozen_spec = json.loads((frozen_quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    frozen_file_hashes = {"quant_params.json": frozen_param_hash}
    for layer in frozen_spec["layers"]:
        for file_name in layer["files"].values():
            path = frozen_quant_dir / file_name
            frozen_file_hashes[str(file_name)] = sha256_file(path)
    matrix_manifest_path = matrix_root / "video_matrix_manifest.json"
    matrix_manifest_hash = sha256_file(matrix_manifest_path) if matrix_manifest_path.is_file() else None
    run_manifest = {
        "schema": "member-a-r0-vs-qat456-run-v1",
        "matrix_manifest_sha256": matrix_manifest_hash,
        "candidate_quant_params_sha256": candidate_param_hash,
        "candidate_bundle_manifest_sha256": candidate_bundle_hash,
        "frozen_quant_file_sha256": frozen_file_hashes,
        "clips": [
            {
                "clip": entry["clip"],
                "source_sha256": entry["source_sha256"],
                "candidate_summary_sha256": entry["summary_sha256"],
                "candidate_raw_output_bytes": entry["raw_output"].stat().st_size,
                "source_indices": entry["source_indices"],
            }
            for entry in inputs
        ],
        "protocol": "same FFmpeg-selected source frames; FFmpeg bicubic 4K→540p TV-to-PC range conversion; final 4K Y; PSNR peak 255; SSIM 11x11 Gaussian; border=8; Keys a=-0.5",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = output_dir / "run_manifest.json"
    progress_path = output_dir / "per_frame_progress.jsonl"
    if run_manifest_path.exists():
        existing = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if existing != run_manifest:
            raise ValueError("Existing output directory is tied to different data/model hashes; choose a fresh output directory")
    else:
        if progress_path.exists() and progress_path.stat().st_size:
            raise ValueError("Progress rows exist without a run manifest; refusing to guess their provenance")
        run_manifest_path.write_text(json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    entries_by_clip = {str(entry["clip"]): entry for entry in inputs}
    for entry in inputs:
        entry["sample_ordinals"] = _select_sample_ordinals(len(entry["source_indices"]), args.sample_per_clip)
    records = _read_records(progress_path)
    completed = {(str(row["clip"]), int(row["frame_index"])) for row in records}
    worst_cases: list[dict[str, object]] = []
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("The project's ignored Python dependencies must be on PYTHONPATH (imageio-ffmpeg missing)") from exc
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    frozen = FixedReference(frozen_quant_dir)
    start = time.monotonic()
    sample_frames = 0
    for entry in inputs:
        processed, _ = _process_indices(
            ffmpeg,
            entry,
            entry["sample_ordinals"],
            frozen,
            progress_path,
            completed,
            deadline=None,
            allow_timeout=False,
            worst_cases=worst_cases,
            worst_count=args.worst_count,
        )
        sample_frames += processed
        print(f"Stratified sample ready: {entry['clip']} ({len(entry['sample_ordinals'])} frames)", flush=True)
    expected_sample_frames = sum(len(entry["sample_ordinals"]) for entry in inputs)
    sampled_completed = sum(1 for row in _read_records(progress_path) if row["sampled"])
    if sampled_completed != expected_sample_frames:
        raise RuntimeError(f"Stratified sample incomplete: {sampled_completed}/{expected_sample_frames}")
    timeout_reached = False
    if not args.sample_only:
        deadline = time.monotonic() + args.max_runtime_seconds
        for entry in inputs:
            remaining = [ordinal for ordinal in range(len(entry["source_indices"])) if (str(entry["clip"]), entry["source_indices"][ordinal]) not in completed]
            processed, timed_out = _process_indices(
                ffmpeg,
                entry,
                remaining,
                frozen,
                progress_path,
                completed,
                deadline=deadline,
                allow_timeout=True,
                worst_cases=worst_cases,
                worst_count=args.worst_count,
            )
            print(f"Extension pass: {entry['clip']} added {processed} frames", flush=True)
            if timed_out or time.monotonic() >= deadline:
                timeout_reached = True
                break
    records = _read_records(progress_path)
    full_complete = all(len([row for row in records if row["clip"] == clip]) == len(entries_by_clip[clip]["source_indices"]) for clip in entries_by_clip)
    contact_paths = _make_contact_sheets(worst_cases, output_dir)
    _write_results(
        output_dir,
        report_path,
        records,
        run_manifest=run_manifest,
        full_complete=full_complete,
        timeout_reached=timeout_reached,
        contact_paths=contact_paths,
    )
    print(
        json.dumps(
            {
                "status": "FULL_10_CLIP_PAIRED_EVALUATION" if full_complete else "STRATIFIED_SAMPLE_WITH_PARTIAL_EXTENSION" if timeout_reached else "STRATIFIED_SAMPLE_EVALUATION",
                "sample_frames_new_this_run": sample_frames,
                "total_completed_rows": len(records),
                "full_complete": full_complete,
                "timeout_reached": timeout_reached,
                "runtime_seconds": round(time.monotonic() - start, 1),
                "output_dir": str(output_dir),
                "report": str(report_path),
            },
            indent=2,
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
