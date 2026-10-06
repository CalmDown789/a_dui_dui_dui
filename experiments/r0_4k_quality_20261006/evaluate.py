from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

import numpy as np
import torch
import PIL
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import convolve1d

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from member_a.fixed_reference import FixedReference
from experiments.integer_bicubic_20261006.integer_bicubic import resize_chunked

WIDTH, HEIGHT = 3840, 2160
LR_WIDTH, LR_HEIGHT = 960, 540
SAMPLE_FPS = 10
CLIP_DURATION_SECONDS = 5
CLIP_FRAMES = SAMPLE_FPS * CLIP_DURATION_SECONDS
CLIP_SEQUENCES = ("Beauty", "Bosphorus", "HoneyBee", "Jockey", "ReadySetGo", "YachtRide",
                  "CityAlley", "FlowerFocus", "FlowerKids", "FlowerPan")
STILL_INDICES = {
    "CityAlley": (350, 360, 370, 380),
    "FlowerFocus": (350, 360, 370, 380),
    "FlowerKids": (350, 360, 370, 380),
    "FlowerPan": (350, 360, 370, 380),
    "ShakeNDry": (60, 70, 80, 90),
}
SEQUENCES = tuple(dict.fromkeys((*CLIP_SEQUENCES, "ShakeNDry")))
HEVC_SEQUENCES = ("Beauty", "Bosphorus", "HoneyBee", "Jockey", "ReadySetGo", "YachtRide", "ShakeNDry")
YUV_SEQUENCES = ("CityAlley", "FlowerFocus", "FlowerKids", "FlowerPan")
SEQUENCE_FPS = {**{name: 120 for name in HEVC_SEQUENCES}, **{name: 50 for name in YUV_SEQUENCES}}
DATASET_URL = "https://ultravideo.fi/dataset.html"
DATASET_LICENSE = "CC BY-NC; non-commercial use only; cite Mercat et al., ACM MMSys 2020"
SEQUENCE_FILES = {
    **{name: f"{name}_3840x2160_120fps_420_8bit_HEVC_RAW.hevc" for name in HEVC_SEQUENCES},
    **{name: f"{name}_3840x2160_50fps_420_8bit_YUV_RAW.yuv" for name in YUV_SEQUENCES},
}


@dataclass(frozen=True)
class Clip:
    clip_id: str
    sequence: str
    start_frame: int
    source_fps: int

    @property
    def indices(self) -> tuple[int, ...]:
        stride = self.source_fps // SAMPLE_FPS
        return tuple(self.start_frame + i * stride for i in range(CLIP_FRAMES))

    @property
    def start_seconds(self) -> float:
        return self.start_frame / self.source_fps

    @property
    def sampled_span_seconds(self) -> float:
        return (self.indices[-1] - self.indices[0]) / self.source_fps


CLIPS = tuple(Clip(f"{sequence}_first5s", sequence, 0, SEQUENCE_FPS[sequence]) for sequence in CLIP_SEQUENCES)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quant_tree_sha256(quant_dir: Path) -> str:
    entries = []
    for path in sorted(p for p in quant_dir.rglob("*") if p.is_file()):
        entries.append({"path": path.relative_to(quant_dir).as_posix(), "sha256": sha256_file(path)})
    return sha256_bytes(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())


def frame_plan() -> dict[str, dict[int, list[tuple[str, str, int]]]]:
    """Map sequence/frame index to image IDs or (clip ID, frame ordinal) tasks."""
    plan: dict[str, dict[int, list[tuple[str, str, int]]]] = {name: {} for name in SEQUENCES}
    for sequence, frame_indices in STILL_INDICES.items():
        for image_ordinal, frame_index in enumerate(frame_indices):
            plan[sequence].setdefault(frame_index, []).append(("image", f"{sequence}_still_{image_ordinal:02d}", frame_index))
    for clip in CLIPS:
        for ordinal, frame_index in enumerate(clip.indices):
            plan[clip.sequence].setdefault(frame_index, []).append(("clip", clip.clip_id, ordinal))
    return plan


def validate_frame_plan() -> None:
    plan = frame_plan()
    expected_frames = sum(len(v) for v in STILL_INDICES.values()) + sum(len(clip.indices) for clip in CLIPS)
    if sum(len(indices) for indices in plan.values()) != expected_frames:
        raise AssertionError("Frame plan contains duplicate source indices")
    for sequence, records in plan.items():
        image_indices = {index for index, actions in records.items() if any(a[0] == "image" for a in actions)}
        clip_indices = {index for index, actions in records.items() if any(a[0] == "clip" for a in actions)}
        if image_indices & clip_indices:
            raise AssertionError(f"Static and clip frames overlap in {sequence}")
    if len(CLIPS) != 10 or sum(len(v) for v in STILL_INDICES.values()) < 20:
        raise AssertionError("The frozen evaluation set must contain >=20 images and >=10 clips")


def decode_selected_frames(video: Path, frame_indices: list[int], ffmpeg: str,
                           source_fps: int, raw_yuv420: bool) -> Iterator[tuple[int, np.ndarray]]:
    """Stream selected full-range Y8 frames from an HEVC stream or planar YUV420 file."""
    if not frame_indices or frame_indices != sorted(set(frame_indices)):
        raise ValueError("frame_indices must be a non-empty, sorted unique list")
    selector = "+".join(f"eq(n,{index})" for index in frame_indices)
    video_filter = f"select='{selector}',scale=in_range=limited:out_range=pc,format=gray"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if raw_yuv420:
        command.extend(["-f", "rawvideo", "-pixel_format", "yuv420p", "-video_size", f"{WIDTH}x{HEIGHT}",
                        "-framerate", str(source_fps)])
    command.extend([
        "-i", str(video),
        "-vf", video_filter, "-fps_mode", "passthrough", "-frames:v", str(len(frame_indices)),
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    frame_bytes = WIDTH * HEIGHT
    try:
        for index in frame_indices:
            raw = process.stdout.read(frame_bytes)
            if len(raw) != frame_bytes:
                raise RuntimeError(f"FFmpeg produced {len(raw)} bytes for frame {index}; expected {frame_bytes}")
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH).copy()
            yield index, frame
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else b""
        code = process.wait(timeout=120)
        if code:
            raise RuntimeError(f"FFmpeg failed ({code}) for {video.name}: {stderr.decode(errors='replace')[-2000:]}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stderr:
            process.stderr.close()


def make_lr(hr_y: np.ndarray) -> np.ndarray:
    if hr_y.dtype != np.uint8 or hr_y.shape != (HEIGHT, WIDTH):
        raise ValueError("Expected 3840x2160 uint8 Y source frame")
    return np.asarray(
        Image.fromarray(hr_y, mode="L").resize((LR_WIDTH, LR_HEIGHT), Image.Resampling.BICUBIC, reducing_gap=None),
        dtype=np.uint8,
    ).copy()


def bicubic_baseline(lr_y: np.ndarray) -> np.ndarray:
    if lr_y.dtype != np.uint8 or lr_y.shape != (LR_HEIGHT, LR_WIDTH):
        raise ValueError("Expected 960x540 uint8 Y input")
    return np.asarray(
        Image.fromarray(lr_y, mode="L").resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC), dtype=np.uint8
    ).copy()


def integer_hybrid(lr_y: np.ndarray, fixed: FixedReference) -> np.ndarray:
    sr_1080 = None
    for name, values in fixed.iter_outputs(lr_y):
        if name == "output":
            sr_1080 = values[:, :, 0].copy()
    if sr_1080 is None or sr_1080.shape != (1080, 1920) or sr_1080.dtype != np.uint8:
        raise AssertionError("Frozen integer FSRCNN did not produce 1920x1080 Y8")
    sr_4k, _, _ = resize_chunked(sr_1080, include_stages=False)
    if sr_4k.shape != (HEIGHT, WIDTH) or sr_4k.dtype != np.uint8:
        raise AssertionError("Q14 bicubic x2 did not produce 3840x2160 Y8")
    return sr_4k


def psnr_y(reference: np.ndarray, candidate: np.ndarray, border: int) -> float:
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("PSNR inputs must be equal-sized single-channel images")
    if border:
        reference = reference[border:-border, border:-border]
        candidate = candidate[border:-border, border:-border]
    difference = reference.astype(np.float64) - candidate.astype(np.float64)
    mse = float(np.mean(difference * difference, dtype=np.float64)) / (255.0 * 255.0)
    return math.inf if mse == 0 else -10.0 * math.log10(mse)


def _ssim_y(reference: np.ndarray, candidate: np.ndarray, border: int) -> float:
    if border:
        reference = reference[border:-border, border:-border]
        candidate = candidate[border:-border, border:-border]
    coord = np.arange(11, dtype=np.float64) - 5
    kernel = np.exp(-(coord**2) / (2 * 1.5**2))
    kernel /= kernel.sum()

    def blur(values: np.ndarray) -> np.ndarray:
        values = convolve1d(values, kernel, axis=0, mode="constant", cval=0.0)
        return convolve1d(values, kernel, axis=1, mode="constant", cval=0.0)

    # The 4K SSIM window is evaluated a strip at a time. Five source rows of
    # halo on either side reproduce the full-frame 11x11 zero-padded filter
    # while keeping peak scratch memory independent of image height.
    height, width = reference.shape
    halo = 5
    strip_rows = 96
    c1, c2 = 0.01**2, 0.03**2
    total = 0.0
    count = 0
    for start in range(0, height, strip_rows):
        end = min(start + strip_rows, height)
        source_start = max(start - halo, 0)
        source_end = min(end + halo, height)
        x = reference[source_start:source_end].astype(np.float64) / 255.0
        y = candidate[source_start:source_end].astype(np.float64) / 255.0
        mux, muy = blur(x), blur(y)
        sigma_x = blur(x * x) - mux * mux
        sigma_y = blur(y * y) - muy * muy
        sigma_xy = blur(x * y) - mux * muy
        numerator = (2 * mux * muy + c1) * (2 * sigma_xy + c2)
        denominator = (mux * mux + muy * muy + c1) * (sigma_x + sigma_y + c2)
        local_start = start - source_start
        local_end = local_start + (end - start)
        scores = numerator[local_start:local_end] / np.maximum(denominator[local_start:local_end], 1.0e-15)
        total += float(np.sum(scores, dtype=np.float64))
        count += scores.size
    return total / count


def quality_metrics(reference: np.ndarray, candidate: np.ndarray, prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_psnr_db_full": psnr_y(reference, candidate, 0),
        f"{prefix}_ssim_full": _ssim_y(reference, candidate, 0),
        f"{prefix}_psnr_db_shave8": psnr_y(reference, candidate, 8),
        f"{prefix}_ssim_shave8": _ssim_y(reference, candidate, 8),
    }


def temporal_difference_mae(reference_now: np.ndarray, reference_prev: np.ndarray,
                            candidate_now: np.ndarray, candidate_prev: np.ndarray, border: int = 8) -> float:
    ref_delta = reference_now[border:-border, border:-border].astype(np.int16) - reference_prev[border:-border, border:-border].astype(np.int16)
    out_delta = candidate_now[border:-border, border:-border].astype(np.int16) - candidate_prev[border:-border, border:-border].astype(np.int16)
    return float(np.mean(np.abs(ref_delta.astype(np.int32) - out_delta.astype(np.int32)), dtype=np.float64))


def thumb(pixels: np.ndarray, size: tuple[int, int] = (640, 360)) -> np.ndarray:
    return np.asarray(Image.fromarray(pixels, mode="L").resize(size, Image.Resampling.LANCZOS), dtype=np.uint8)


def sha_array(pixels: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(pixels).tobytes())


def _mean(rows: list[dict], key: str) -> float:
    values = [float(row[key]) for row in rows]
    return float(np.mean(values, dtype=np.float64))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_demo_frame(writer: BinaryIO, reference: np.ndarray, bicubic: np.ndarray, hybrid: np.ndarray) -> None:
    panel_w, panel_h, header_h = 640, 360, 36
    canvas = Image.new("RGB", (panel_w * 3, panel_h + header_h), "black")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=24)
    for index, (name, image) in enumerate((("Decoded 4K Y", reference), ("Bicubic x4", bicubic), ("R0 INT hybrid", hybrid))):
        x = index * panel_w
        draw.text((x + 8, 8), name, font=font, fill="white")
        canvas.paste(Image.fromarray(thumb(image, (panel_w, panel_h)), mode="L").convert("RGB"), (x, header_h))
    writer.write(canvas.tobytes())


def _error_maxpool_thumbnail(reference: np.ndarray, candidate: np.ndarray, size: tuple[int, int] = (640, 360),
                            gain: int = 8) -> np.ndarray:
    if reference.shape != candidate.shape or reference.shape[0] % size[1] or reference.shape[1] % size[0]:
        raise ValueError("Error thumbnail requires equal image shapes divisible by the target dimensions")
    height, width = reference.shape
    block_y, block_x = height // size[1], width // size[0]
    difference = np.abs(reference.astype(np.int16) - candidate.astype(np.int16)).astype(np.uint8)
    pooled = difference.reshape(size[1], block_y, size[0], block_x).max(axis=(1, 3))
    return np.clip(pooled.astype(np.uint16) * gain, 0, 255).astype(np.uint8)


def _contact_sheet(rows: list[dict], thumbs: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]], target: Path) -> None:
    chosen = sorted(rows, key=lambda row: (float(row["hybrid_gain_vs_bicubic_db_shave8"]), float(row["hybrid_psnr_db_shave8"])))[:4]
    panel_w, panel_h, gap, label_h = 640, 360, 12, 34
    canvas = Image.new("RGB", (panel_w * 4 + gap * 5, len(chosen) * (panel_h + label_h + gap) + gap), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=22)
    columns = ("Decoded reference", "Bicubic x4", "R0 integer hybrid", "max |hybrid-ref| x8 (6x6)")
    for row_index, row in enumerate(chosen):
        y = gap + row_index * (panel_h + label_h + gap)
        key = row["sample_id"]
        ref, cubic, hybrid, error = thumbs[key]
        for col, image in enumerate((ref, cubic, hybrid, error)):
            x = gap + col * (panel_w + gap)
            if row_index == 0:
                draw.text((x + 4, y + 2), columns[col], fill="black", font=font)
            canvas.paste(Image.fromarray(image, mode="L").convert("RGB"), (x, y + label_h))
        draw.text((gap, y + panel_h + label_h + 1),
                  f"{key} | gain {float(row['hybrid_gain_vs_bicubic_db_shave8']):+.3f} dB | "
                  f"R0 {float(row['hybrid_psnr_db_shave8']):.3f} dB",
                  fill="black", font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="JPEG", quality=88, optimize=True)


def _summary_rows(rows: list[dict], group_key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row[group_key]), []).append(row)
    output = []
    for group, values in sorted(groups.items()):
        record = {group_key: group, "frames": len(values)}
        metric_keys = []
        for key, value in values[0].items():
            if not key.startswith(("bicubic_", "hybrid_")):
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            metric_keys.append(key)
        for key in metric_keys:
            numeric = [float(row[key]) for row in values]
            record[f"mean_{key}"] = float(np.mean(numeric, dtype=np.float64))
            if key.endswith("psnr_db_full") or key.endswith("psnr_db_shave8"):
                record[f"min_{key}"] = float(np.min(numeric))
        gain_key = "hybrid_gain_vs_bicubic_db_shave8"
        record["negative_gain_frames"] = sum(float(row[gain_key]) < 0 for row in values)
        if group_key == "clip_id":
            for model in ("bicubic", "hybrid"):
                temporal = [float(row[f"{model}_temporal_difference_mae_u8"]) for row in values if row.get(f"{model}_temporal_difference_mae_u8") is not None]
                record[f"mean_{model}_temporal_difference_mae_u8"] = float(np.mean(temporal)) if temporal else None
        output.append(record)
    return output


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key, value in list(row.items()):
            if value == "":
                row[key] = None
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                if value.lower() in ("true", "false"):
                    row[key] = value.lower() == "true"
                continue
            if key == "frames" or key.startswith("negative_"):
                row[key] = int(number)
            else:
                row[key] = number
    return rows


def summarize_clip_rows(frame_rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in frame_rows:
        clip_id = str(row["sample_id"]).rsplit("_f", 1)[0]
        groups.setdefault(clip_id, []).append(row)
    clip_by_id = {clip.clip_id: clip for clip in CLIPS}
    summaries = []
    for clip_id, rows in sorted(groups.items()):
        clip = clip_by_id[clip_id]
        rows.sort(key=lambda row: int(row["decoded_frame_index"]))
        record = {
            "clip_id": clip_id,
            "sequence": clip.sequence,
            "source_start_frame": clip.indices[0],
            "source_end_frame": clip.indices[-1],
            "source_start_seconds": clip.start_seconds,
            "nominal_duration_seconds": CLIP_DURATION_SECONDS,
            "sampled_span_seconds": clip.sampled_span_seconds,
            "frames": len(rows),
            "sample_fps": SAMPLE_FPS,
        }
        for model in ("bicubic", "hybrid"):
            for metric in ("psnr_db_full", "ssim_full", "psnr_db_shave8", "ssim_shave8"):
                key = f"{model}_{metric}"
                record[f"mean_{key}"] = _mean(rows, key)
                record[f"{model}_mean_{metric}"] = record[f"mean_{key}"]
                if metric.startswith("psnr"):
                    record[f"min_{key}"] = min(float(row[key]) for row in rows)
            temporal_key = f"{model}_temporal_difference_mae_u8"
            temporal = [float(row[temporal_key]) for row in rows if row.get(temporal_key) is not None]
            record[temporal_key] = float(np.mean(temporal, dtype=np.float64)) if temporal else None
        for border in ("full", "shave8"):
            psnr_gain = f"hybrid_gain_vs_bicubic_db_{border}"
            ssim_delta = f"hybrid_ssim_delta_vs_bicubic_{border}"
            record[f"mean_{psnr_gain}"] = _mean(rows, psnr_gain)
            record[f"mean_{ssim_delta}"] = _mean(rows, ssim_delta)
            if border == "full":
                record["hybrid_gain_mean_psnr_db_full"] = record[f"mean_{psnr_gain}"]
            else:
                record["hybrid_gain_mean_psnr_db_shave8"] = record[f"mean_{psnr_gain}"]
            record[f"negative_psnr_gain_frames_{border}"] = sum(float(row[psnr_gain]) < 0 for row in rows)
            record[f"negative_ssim_delta_frames_{border}"] = sum(float(row[ssim_delta]) < 0 for row in rows)
        record["negative_gain_frames"] = record["negative_psnr_gain_frames_shave8"]
        summaries.append(record)
    if len(summaries) != len(CLIPS) or any(row["frames"] != CLIP_FRAMES for row in summaries):
        raise ValueError(f"Persisted clip frame table has unexpected grouping: {len(summaries)} clips")
    return summaries


def finalize_output(output_dir: Path) -> dict:
    """Build the final JSON summary from the already persisted result tables."""
    output_dir = output_dir.resolve()
    image_rows = _read_csv(output_dir / "per_image_metrics.csv")
    frame_rows = _read_csv(output_dir / "per_clip_frame_metrics.csv")
    clip_summary = summarize_clip_rows(frame_rows)
    _write_csv(output_dir / "per_clip_summary.csv", clip_summary)
    failure_rows = _read_csv(output_dir / "failure_cases.csv")
    if len(image_rows) != 20 or len(frame_rows) != 500 or len(clip_summary) != 10:
        raise ValueError(
            f"Unexpected persisted counts: {len(image_rows)} images, {len(frame_rows)} clip frames, "
            f"{len(clip_summary)} clips; expected 20/500/10"
        )

    overall = {}
    for key in ("bicubic_psnr_db_full", "bicubic_ssim_full", "bicubic_psnr_db_shave8", "bicubic_ssim_shave8",
                "hybrid_psnr_db_full", "hybrid_ssim_full", "hybrid_psnr_db_shave8", "hybrid_ssim_shave8",
                "hybrid_gain_vs_bicubic_db_full", "hybrid_gain_vs_bicubic_db_shave8",
                "hybrid_ssim_delta_vs_bicubic_full", "hybrid_ssim_delta_vs_bicubic_shave8"):
        overall[key] = _mean(image_rows, key)
    overall["static_images_with_negative_psnr_gain"] = sum(
        float(row["hybrid_gain_vs_bicubic_db_shave8"]) < 0 for row in image_rows
    )
    overall["static_images_with_negative_ssim_delta"] = sum(
        float(row["hybrid_ssim_delta_vs_bicubic_shave8"]) < 0 for row in image_rows
    )
    overall["clip_frames"] = len(frame_rows)
    overall["clips_with_negative_mean_psnr_gain"] = sum(
        float(row["hybrid_gain_mean_psnr_db_shave8"]) < 0 for row in clip_summary
    )
    clip_overall = {}
    for key in ("bicubic_psnr_db_full", "bicubic_ssim_full", "bicubic_psnr_db_shave8", "bicubic_ssim_shave8",
                "hybrid_psnr_db_full", "hybrid_ssim_full", "hybrid_psnr_db_shave8", "hybrid_ssim_shave8",
                "hybrid_gain_vs_bicubic_db_full", "hybrid_gain_vs_bicubic_db_shave8",
                "hybrid_ssim_delta_vs_bicubic_full", "hybrid_ssim_delta_vs_bicubic_shave8"):
        clip_overall[key] = _mean(frame_rows, key)
    for border in ("full", "shave8"):
        clip_overall[f"negative_psnr_gain_frames_{border}"] = sum(
            float(row[f"hybrid_gain_vs_bicubic_db_{border}"]) < 0 for row in frame_rows
        )
        clip_overall[f"negative_ssim_delta_frames_{border}"] = sum(
            float(row[f"hybrid_ssim_delta_vs_bicubic_{border}"]) < 0 for row in frame_rows
        )

    summary = {
        "schema": "member-a-r0-integer-quality-summary-v1",
        "status": "COMPLETED_SOFTWARE_EVALUATION",
        "images": {"count": len(image_rows), "overall_frame_mean": overall,
                   "by_sequence": _summary_rows(image_rows, "sequence")},
        "clips": {"count": len(clip_summary), "nominal_duration_seconds_each": CLIP_DURATION_SECONDS,
                  "sample_fps": SAMPLE_FPS, "sampled_frames": len(frame_rows),
                  "overall_frame_mean": clip_overall,
                  "by_clip": clip_summary,
                  "mean_clip_gain_psnr_db_shave8": float(np.mean([r["hybrid_gain_mean_psnr_db_shave8"] for r in clip_summary])),
                  "mean_bicubic_temporal_difference_mae_u8": float(np.mean([r["bicubic_temporal_difference_mae_u8"] for r in clip_summary])),
                  "mean_hybrid_temporal_difference_mae_u8": float(np.mean([r["hybrid_temporal_difference_mae_u8"] for r in clip_summary]))},
        "failure_cases": {"triggered_count": sum(bool(row["failure_triggered"]) for row in failure_rows),
                           "negative_psnr_gain_frames_shave8": clip_overall["negative_psnr_gain_frames_shave8"] + overall["static_images_with_negative_psnr_gain"],
                           "negative_ssim_delta_frames_shave8": clip_overall["negative_ssim_delta_frames_shave8"] + overall["static_images_with_negative_ssim_delta"],
                           "by_sequence": {sequence: sum(row["sequence"] == sequence for row in failure_rows)
                                           for sequence in sorted({str(row["sequence"]) for row in failure_rows})},
                           "definition": "negative PSNR gain or SSIM delta on any still/clip frame at shave=8",
                           "csv": "failure_cases.csv",
                           "when_none": "CSV contains the five lowest-PSNR-gain cases for transparent review."},
        "artifacts": {"per_image_metrics": "per_image_metrics.csv", "per_clip_frame_metrics": "per_clip_frame_metrics.csv",
                      "per_clip_summary": "per_clip_summary.csv", "contact_sheet": "visuals/lowest_gain_examples.jpg",
                      "demo_video": "demo_beauty_5s_10fps.mp4", "evaluation_manifest": "evaluation_manifest.json"},
    }
    manifest_path = output_dir / "evaluation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["aggregation"] = (
        "frame arithmetic mean; each five-second clip averages 50 frames sampled at 10 fps"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def regenerate_contact_sheet(source_dir: Path, output_dir: Path) -> Path:
    """Rebuild low-gain visuals from source frames, checking saved output hashes."""
    import imageio_ffmpeg

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    image_rows = _read_csv(output_dir / "per_image_metrics.csv")
    chosen = sorted(image_rows, key=lambda row: (float(row["hybrid_gain_vs_bicubic_db_shave8"]),
                                                 float(row["hybrid_psnr_db_shave8"])))[:4]
    manifest = json.loads((output_dir / "evaluation_manifest.json").read_text(encoding="utf-8"))
    manifest_sources = {item["sequence"]: item for item in manifest["sources"]}
    quant_dir = ROOT / "artifacts" / "quant"
    if quant_tree_sha256(quant_dir) != manifest["model"]["quant_asset_tree_sha256"]:
        raise ValueError("Frozen quantized model assets differ from the evaluation manifest")
    fixed = FixedReference(quant_dir)
    torch.set_num_threads(1)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    thumbs: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    by_sequence: dict[str, list[dict]] = {}
    for row in chosen:
        by_sequence.setdefault(str(row["sequence"]), []).append(row)
    for sequence, rows in by_sequence.items():
        source = source_dir / SEQUENCE_FILES[sequence]
        if sha256_file(source) != manifest_sources[sequence]["sha256"]:
            raise ValueError(f"Source hash changed since evaluation: {sequence}")
        wanted = sorted({int(row["decoded_frame_index"]) for row in rows})
        rows_by_index = {int(row["decoded_frame_index"]): row for row in rows}
        for index, hr_y in decode_selected_frames(source, wanted, ffmpeg, SEQUENCE_FPS[sequence], sequence in YUV_SEQUENCES):
            row = rows_by_index[index]
            if sha_array(hr_y) != row["hr_y_sha256"]:
                raise ValueError(f"Decoded reference hash changed for {row['sample_id']}")
            lr_y = make_lr(hr_y)
            bicubic = bicubic_baseline(lr_y)
            hybrid = integer_hybrid(lr_y, fixed)
            hashes = (sha_array(lr_y), sha_array(bicubic), sha_array(hybrid))
            expected = (row["lr_y_sha256"], row["bicubic_y_sha256"], row["hybrid_y_sha256"])
            if hashes != expected:
                raise ValueError(f"Recomputed candidate hash changed for {row['sample_id']}")
            thumbs[str(row["sample_id"])] = (
                thumb(hr_y), thumb(bicubic), thumb(hybrid), _error_maxpool_thumbnail(hr_y, hybrid)
            )
    target = output_dir / "visuals" / "lowest_gain_examples.jpg"
    _contact_sheet(chosen, thumbs, target)
    return target


def run(source_dir: Path, output_dir: Path, ffmpeg: str | None, device_name: str) -> dict:
    validate_frame_plan()
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(ROOT / "results")
    except ValueError as exc:
        raise ValueError(f"Results must be written under {ROOT / 'results'}; got {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty result directory: {output_dir}")
    if device_name != "cpu":
        raise ValueError("FixedReference is the CPU integer oracle; device must be cpu")
    if ffmpeg is None:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_version = imageio_ffmpeg.get_ffmpeg_version()
    else:
        version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=True)
        ffmpeg_version = version.stdout.splitlines()[0]

    sources = {}
    for sequence, filename in SEQUENCE_FILES.items():
        source = source_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Missing UVG source file: {source}")
        if sequence in YUV_SEQUENCES:
            expected_bytes = WIDTH * HEIGHT * 3 // 2 * 50 * 12
            if source.stat().st_size != expected_bytes:
                raise ValueError(f"{source.name} has {source.stat().st_size} bytes; expected {expected_bytes} for 12 s YUV420p")
        sources[sequence] = {"path": source, "bytes": source.stat().st_size, "sha256": sha256_file(source)}

    quant_dir = ROOT / "artifacts" / "quant"
    quant_params = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    quant_digest = quant_tree_sha256(quant_dir)
    fixed = FixedReference(quant_dir)
    # Avoid large oneDNN scratch allocations on shared/student machines.
    torch.set_num_threads(1)
    output_dir.mkdir(parents=True, exist_ok=False)
    visual_dir = output_dir / "visuals"
    visual_dir.mkdir()
    static_rows: list[dict] = []
    clip_rows: list[dict] = []
    static_thumbs: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    clip_accumulators: dict[str, dict] = {
        clip.clip_id: {"rows": [], "previous": None, "temporal_bicubic": [], "temporal_hybrid": []} for clip in CLIPS
    }
    demo_path = output_dir / "demo_beauty_5s_10fps.mp4"
    demo_writer = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "1920x396", "-r", str(SAMPLE_FPS), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(demo_path)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    assert demo_writer.stdin is not None
    plan = frame_plan()
    source_manifest = []
    try:
        for sequence in SEQUENCES:
            selected = sorted(plan[sequence])
            source_path = sources[sequence]["path"]
            frame_hashes = []
            for source_index, hr_y in decode_selected_frames(
                source_path, selected, ffmpeg, SEQUENCE_FPS[sequence], sequence in YUV_SEQUENCES
            ):
                frame_hash = sha_array(hr_y)
                frame_hashes.append({"decoded_frame_index": source_index, "timestamp_s_from_dataset_fps": source_index / SEQUENCE_FPS[sequence],
                                     "hr_y_sha256": frame_hash})
                lr_y = make_lr(hr_y)
                bicubic = bicubic_baseline(lr_y)
                hybrid = integer_hybrid(lr_y, fixed)
                if bicubic.shape != hr_y.shape or hybrid.shape != hr_y.shape:
                    raise AssertionError("Upscaled candidate dimensions do not match 4K reference")
                lr_hash = sha_array(lr_y)
                for kind, record_id, ordinal in plan[sequence][source_index]:
                    row = {
                        "sample_id": record_id if kind == "image" else f"{record_id}_f{ordinal:02d}",
                        "sequence": sequence,
                        "decoded_frame_index": source_index,
                        "timestamp_s_from_dataset_fps": source_index / SEQUENCE_FPS[sequence],
                        "hr_y_sha256": frame_hash,
                        "lr_y_sha256": lr_hash,
                        "bicubic_y_sha256": sha_array(bicubic),
                        "hybrid_y_sha256": sha_array(hybrid),
                    }
                    row.update(quality_metrics(hr_y, bicubic, "bicubic"))
                    row.update(quality_metrics(hr_y, hybrid, "hybrid"))
                    row["hybrid_gain_vs_bicubic_db_full"] = row["hybrid_psnr_db_full"] - row["bicubic_psnr_db_full"]
                    row["hybrid_gain_vs_bicubic_db_shave8"] = row["hybrid_psnr_db_shave8"] - row["bicubic_psnr_db_shave8"]
                    row["hybrid_ssim_delta_vs_bicubic_full"] = row["hybrid_ssim_full"] - row["bicubic_ssim_full"]
                    row["hybrid_ssim_delta_vs_bicubic_shave8"] = row["hybrid_ssim_shave8"] - row["bicubic_ssim_shave8"]
                    if kind == "image":
                        static_rows.append(row)
                        static_thumbs[record_id] = (
                            thumb(hr_y), thumb(bicubic), thumb(hybrid), _error_maxpool_thumbnail(hr_y, hybrid)
                        )
                    else:
                        state = clip_accumulators[record_id]
                        previous = state["previous"]
                        if previous is None:
                            row["bicubic_temporal_difference_mae_u8"] = None
                            row["hybrid_temporal_difference_mae_u8"] = None
                        else:
                            prev_ref, prev_bicubic, prev_hybrid = previous
                            b_mae = temporal_difference_mae(hr_y, prev_ref, bicubic, prev_bicubic)
                            h_mae = temporal_difference_mae(hr_y, prev_ref, hybrid, prev_hybrid)
                            row["bicubic_temporal_difference_mae_u8"] = b_mae
                            row["hybrid_temporal_difference_mae_u8"] = h_mae
                            state["temporal_bicubic"].append(b_mae)
                            state["temporal_hybrid"].append(h_mae)
                        state["previous"] = (hr_y.copy(), bicubic.copy(), hybrid.copy())
                        state["rows"].append(row)
                        clip_rows.append(row)
                        if record_id == "Beauty_first5s":
                            _write_demo_frame(demo_writer.stdin, hr_y, bicubic, hybrid)
            source_manifest.append({
                "sequence": sequence,
                "source_file": source_path.name,
                "source_url": f"https://ultravideo.fi/video/{source_path.name.removesuffix('.yuv') + '.7z' if sequence in YUV_SEQUENCES else source_path.name}",
                "source_format": "raw YUV420p 8-bit" if sequence in YUV_SEQUENCES else "8-bit 4:2:0 HEVC",
                "dataset_fps": SEQUENCE_FPS[sequence],
                "bytes": sources[sequence]["bytes"],
                "sha256": sources[sequence]["sha256"],
                "decoded_frame_count": len(frame_hashes),
                "selected_frames": frame_hashes,
            })
    finally:
        demo_writer.stdin.close()
        stderr = demo_writer.stderr.read() if demo_writer.stderr else b""
        code = demo_writer.wait()
        if code:
            raise RuntimeError(f"FFmpeg demo encoding failed ({code}): {stderr.decode(errors='replace')[-2000:]}")
        if demo_writer.stderr:
            demo_writer.stderr.close()

    if len(static_rows) != 20 or len(clip_rows) != 500:
        raise AssertionError(f"Unexpected evaluation counts: {len(static_rows)} images, {len(clip_rows)} clip frames")

    static_rows.sort(key=lambda row: row["sample_id"])
    clip_rows.sort(key=lambda row: (row["sample_id"].split("_f")[0], row["decoded_frame_index"]))
    _write_csv(output_dir / "per_image_metrics.csv", static_rows)
    _write_csv(output_dir / "per_clip_frame_metrics.csv", clip_rows)
    clip_summary = []
    for clip in CLIPS:
        state = clip_accumulators[clip.clip_id]
        rows = state["rows"]
        summary = {
            "clip_id": clip.clip_id,
            "sequence": clip.sequence,
            "source_start_frame": clip.indices[0],
            "source_end_frame": clip.indices[-1],
            "source_start_seconds": clip.start_seconds,
            "nominal_duration_seconds": CLIP_DURATION_SECONDS,
            "sampled_span_seconds": clip.sampled_span_seconds,
            "frames": len(rows),
            "sample_fps": SAMPLE_FPS,
            "bicubic_mean_psnr_db_shave8": _mean(rows, "bicubic_psnr_db_shave8"),
            "hybrid_mean_psnr_db_shave8": _mean(rows, "hybrid_psnr_db_shave8"),
            "hybrid_gain_mean_psnr_db_shave8": _mean(rows, "hybrid_gain_vs_bicubic_db_shave8"),
            "bicubic_mean_ssim_shave8": _mean(rows, "bicubic_ssim_shave8"),
            "hybrid_mean_ssim_shave8": _mean(rows, "hybrid_ssim_shave8"),
            "negative_gain_frames": sum(float(row["hybrid_gain_vs_bicubic_db_shave8"]) < 0 for row in rows),
            "bicubic_temporal_difference_mae_u8": float(np.mean(state["temporal_bicubic"])),
            "hybrid_temporal_difference_mae_u8": float(np.mean(state["temporal_hybrid"])),
        }
        clip_summary.append(summary)
    _write_csv(output_dir / "per_clip_summary.csv", clip_summary)

    _contact_sheet(static_rows, static_thumbs, visual_dir / "lowest_gain_examples.jpg")
    all_quality_rows = static_rows + clip_rows
    failures = [row for row in all_quality_rows if float(row["hybrid_gain_vs_bicubic_db_shave8"]) < 0 or
                float(row["hybrid_ssim_delta_vs_bicubic_shave8"]) < 0]
    if failures:
        failure_rows = [{**row, "failure_triggered": True} for row in failures]
    else:
        failure_rows = [{**row, "failure_triggered": False} for row in sorted(
            all_quality_rows, key=lambda row: float(row["hybrid_gain_vs_bicubic_db_shave8"])
        )[:5]]
    _write_csv(output_dir / "failure_cases.csv", failure_rows)

    dataset_manifest = {
        "schema": "member-a-r0-integer-4k-temporal-quality-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SOFTWARE_ONLY_SYNTHETIC_SCALE4_QUALITY_EVALUATION",
        "dataset": {"name": "UVG 4K test sequences", "url": DATASET_URL, "license": DATASET_LICENSE,
                    "citation": "A. Mercat, M. Viitanen, J. Vanne, UVG dataset: 50/120fps 4K sequences for video codec analysis and development, ACM MMSys, 2020."},
        "sources": source_manifest,
        "static_images": {"count": len(static_rows), "sequences": list(STILL_INDICES), "source_indices_per_sequence": STILL_INDICES,
                          "disjoint_from_clip_samples": True},
        "clips": [{"clip_id": clip.clip_id, "sequence": clip.sequence, "source_start_frame": clip.indices[0],
                   "source_end_frame": clip.indices[-1], "source_fps": clip.source_fps,
                   "sample_stride_frames": clip.source_fps // SAMPLE_FPS, "sampled_frames": list(clip.indices),
                   "nominal_duration_seconds": CLIP_DURATION_SECONDS, "sample_fps": SAMPLE_FPS, "frame_count": CLIP_FRAMES,
                   "sampled_span_seconds": clip.sampled_span_seconds} for clip in CLIPS],
        "preprocessing": {"source": "UVG 4K 3840x2160 8-bit 4:2:0 HEVC and planar YUV420p sequences, FFmpeg decoded Y plane",
                          "range": "limited-range Y expanded to full-range 0..255 using FFmpeg scale in_range=limited:out_range=pc",
                          "synthetic_lr": "Pillow BICUBIC downsample 3840x2160 to 960x540, reducing_gap=None",
                          "baseline": "Pillow BICUBIC direct enlargement 960x540 to 3840x2160",
                          "hybrid": "frozen R0 INT8/INT16/INT32 FSRCNN x2 to 1920x1080 Y8, then frozen Q14xQ14 Keys bicubic x2 to 3840x2160 Y8",
                          "colorspace": "Y only; no color reconstruction was evaluated"},
        "model": {"name": quant_params["model"], "quant_params_sha256": sha256_file(quant_dir / "quant_params.json"),
                  "quant_asset_tree_sha256": quant_digest, "rounding": quant_params["rounding"],
                  "quantization": "per-output-channel symmetric INT8 weights; symmetric per-layer INT16 activations; INT32 bias/accumulator; Q1.15 PReLU"},
        "metrics": {"y_psnr": "peak=255, MSE in normalized [0,1], arithmetic mean over frames",
                    "y_ssim": "11x11 Gaussian window, sigma=1.5, C1=0.01^2, C2=0.03^2, zero padding",
                    "borders": [0, 8], "aggregation": "frame arithmetic mean; each five-second clip averages 50 frames sampled at 10 fps",
                    "temporal_difference_mae": "mean absolute error of frame-to-frame Y differences in 8-bit levels after 8-pixel shave; not motion-compensated"},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__,
                        "pillow": PIL.__version__, "ffmpeg": ffmpeg_version, "fixed_reference_device": "CPU"},
        "limitations": ["UVG HEVC is lossy decoded reference content, not pristine sensor ground truth.",
                        "540p inputs are synthetic bicubic degradations of 4K decoded Y; native-camera 540p quality is not measured.",
                        "50 frames per five-second clip are sampled at 10 fps from 50/120 fps sources; this does not establish 30 fps or real-time throughput.",
                        "The evaluation measures grayscale/Y software output only; it does not validate FPGA RTL, bitstream, HDMI, or color reconstruction."],
    }
    (output_dir / "evaluation_manifest.json").write_text(json.dumps(dataset_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return finalize_output(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate frozen R0 integer hybrid reconstruction on UVG 4K Y sequences")
    parser.add_argument("--source-dir", type=Path,
                        help="Directory containing seven UVG HEVC and four extracted 4K YUV source files")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "r0_4k_quality_20261006")
    parser.add_argument("--ffmpeg", help="Optional ffmpeg executable; default uses imageio-ffmpeg")
    parser.add_argument("--device", choices=("cpu",), default="cpu", help="The frozen integer oracle currently runs on CPU")
    parser.add_argument("--finalize-existing", action="store_true",
                        help="Build summary.json from complete persisted CSV tables without rerunning inference")
    parser.add_argument("--contact-sheet-only", action="store_true",
                        help="Regenerate the low-gain contact sheet from saved evaluation rows and verify hashes")
    args = parser.parse_args()
    if args.contact_sheet_only:
        if args.source_dir is None:
            parser.error("--source-dir is required with --contact-sheet-only")
        target = regenerate_contact_sheet(args.source_dir, args.output_dir)
        print(f"Regenerated and verified: {target}")
        return 0
    if args.finalize_existing:
        result = finalize_output(args.output_dir)
        print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir.resolve()),
                          "images": result["images"]["count"], "clips": result["clips"]["count"],
                          "clip_frames": result["clips"]["sampled_frames"]}, indent=2, ensure_ascii=False))
        return 0
    if args.source_dir is None:
        parser.error("--source-dir is required unless --finalize-existing is used")
    result = run(args.source_dir, args.output_dir, args.ffmpeg, args.device)
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir.resolve()),
                      "images": result["images"]["count"], "clips": result["clips"]["count"],
                      "clip_frames": result["clips"]["sampled_frames"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
