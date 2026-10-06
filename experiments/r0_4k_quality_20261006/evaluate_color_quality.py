from __future__ import annotations

import argparse
import csv
import ctypes
import gc
import hashlib
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import PIL
import torch
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from member_a.fixed_reference import FixedReference
from experiments.r0_4k_quality_20261006.color_demo import read_selected_yuv420
from experiments.r0_4k_quality_20261006.evaluate import (
    CLIPS,
    CLIP_FRAMES,
    HEIGHT,
    LR_HEIGHT,
    LR_WIDTH,
    SAMPLE_FPS,
    WIDTH,
    _ssim_y,
    bicubic_baseline,
    integer_hybrid,
    make_lr,
    psnr_y,
    quant_tree_sha256,
    sha256_file,
    sha_array,
)

SOURCE_DIR = ROOT / ".data" / "r0_4k_quality_20261006" / "sources"
QUALITY_DIR = ROOT / "results" / "r0_4k_quality_20261006"
OUTPUT_DIR = ROOT / "results" / "r0_color_quality_20261007"
CHECKPOINT_DIR = ROOT / ".data" / "r0_color_quality_20261007_checkpoint"
SEQUENCES = ("Beauty", "Jockey", "Bosphorus")
FRAME_COUNT = 30
MIN_START_MEMORY_MIB = 2304
MIN_AVAILABLE_MEMORY_MIB = 768
CHROMA_WIDTH, CHROMA_HEIGHT = WIDTH // 2, HEIGHT // 2
LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT = LR_WIDTH // 2, LR_HEIGHT // 2
THUMB_SIZE = (384, 216)


def contact_ordinals(frame_count: int) -> tuple[int, ...]:
    if frame_count < 1:
        raise ValueError("frame_count must be positive")
    return tuple(sorted({0, frame_count // 2, frame_count - 1}))


def _resize_plane(plane: np.ndarray, width: int, height: int, method: str) -> np.ndarray:
    if plane.ndim != 2 or plane.dtype != np.uint8:
        raise ValueError("Expected a two-dimensional uint8 plane")
    resampling = {"bicubic": Image.Resampling.BICUBIC, "bilinear": Image.Resampling.BILINEAR}
    if method not in resampling:
        raise ValueError(f"Unsupported chroma resampling method: {method}")
    return np.asarray(
        Image.fromarray(plane, mode="L").resize((width, height), resampling[method]), dtype=np.uint8
    ).copy()


def ycbcr709_full_to_rgb(y: np.ndarray, cb: np.ndarray, cr: np.ndarray) -> np.ndarray:
    if y.ndim != 2 or y.dtype != np.uint8 or cb.shape != y.shape or cr.shape != y.shape:
        raise ValueError("Y, Cb, and Cr must be equally shaped 2D uint8 planes")
    y32 = y.astype(np.int32)
    cb_delta = cb.astype(np.int32) - 128
    cr_delta = cr.astype(np.int32) - 128
    red = y32 + ((103206 * cr_delta + 32768) // 65536)
    green = y32 - ((12276 * cb_delta + 30679 * cr_delta + 32768) // 65536)
    blue = y32 + ((121609 * cb_delta + 32768) // 65536)
    rgb = np.empty((*y.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = np.clip(red, 0, 255).astype(np.uint8)
    rgb[:, :, 1] = np.clip(green, 0, 255).astype(np.uint8)
    rgb[:, :, 2] = np.clip(blue, 0, 255).astype(np.uint8)
    return rgb


def psnr_rgb(reference: np.ndarray, candidate: np.ndarray, border: int = 0) -> float:
    if reference.shape != candidate.shape or reference.ndim != 3 or reference.shape[2] != 3:
        raise ValueError("RGB PSNR inputs must be equally shaped HxWx3 arrays")
    if reference.dtype != np.uint8 or candidate.dtype != np.uint8:
        raise ValueError("RGB PSNR inputs must use uint8 values")
    if border < 0 or 2 * border >= min(reference.shape[:2]):
        raise ValueError("Invalid RGB PSNR border")
    if border:
        reference, candidate = reference[border:-border, border:-border], candidate[border:-border, border:-border]
    height = reference.shape[0]
    squared_error = 0
    sample_count = 0
    for start in range(0, height, 128):
        ref_strip = reference[start:start + 128].astype(np.int16)
        out_strip = candidate[start:start + 128].astype(np.int16)
        difference = ref_strip.astype(np.int32) - out_strip.astype(np.int32)
        squared_error += int(np.sum(difference * difference, dtype=np.int64))
        sample_count += difference.size
    mse = (squared_error / sample_count) / (255.0 * 255.0)
    return math.inf if mse == 0 else -10.0 * math.log10(mse)


def ssim_rgb(reference: np.ndarray, candidate: np.ndarray, border: int = 0) -> float:
    if reference.shape != candidate.shape or reference.ndim != 3 or reference.shape[2] != 3:
        raise ValueError("RGB SSIM inputs must be equally shaped HxWx3 arrays")
    if reference.dtype != np.uint8 or candidate.dtype != np.uint8:
        raise ValueError("RGB SSIM inputs must use uint8 values")
    if min(reference.shape[:2]) <= 2 * border + 10:
        raise ValueError("RGB SSIM input is too small for the selected crop and 11x11 window")
    scores = [
        _ssim_y(reference[:, :, channel], candidate[:, :, channel], border)
        for channel in range(3)
    ]
    return float(np.mean(scores, dtype=np.float64))


def rgb_metrics(reference: np.ndarray, candidate: np.ndarray, prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_psnr_db_full": psnr_rgb(reference, candidate, 0),
        f"{prefix}_psnr_db_shave8": psnr_rgb(reference, candidate, 8),
        f"{prefix}_ssim_full": ssim_rgb(reference, candidate, 0),
        f"{prefix}_ssim_shave8": ssim_rgb(reference, candidate, 8),
    }


def sampled_ordinals(frame_count: int = FRAME_COUNT) -> tuple[int, ...]:
    if not 1 <= frame_count <= CLIP_FRAMES:
        raise ValueError(f"frame_count must be in 1..{CLIP_FRAMES}")
    values = np.rint(np.linspace(0, CLIP_FRAMES - 1, frame_count)).astype(np.int64)
    result = tuple(int(value) for value in values)
    if len(set(result)) != frame_count:
        raise AssertionError("The deterministic frame schedule contains duplicates")
    return result


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _metric_rows(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    rows = _read_csv(path)
    return {(row["sequence"], int(row["decoded_frame_index"])): row for row in rows}


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty color evaluation")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_csv_atomic(path: Path, rows: list[dict]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    _write_csv(temporary, rows)
    temporary.replace(path)


def _read_checkpoint_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = _read_csv(path)
    integer_keys = {"sample_ordinal", "decoded_frame_index"}
    text_keys = {"sequence"}
    parsed = []
    for row in rows:
        converted = {}
        for key, value in row.items():
            if key in text_keys or key.endswith("_sha256"):
                converted[key] = value
            elif key in integer_keys:
                converted[key] = int(value)
            else:
                converted[key] = float(value)
        parsed.append(converted)
    return parsed


def _available_memory_mib() -> int | None:
    if sys.platform != "win32":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys // (1024 * 1024))


def _metric_keys(row: dict) -> list[str]:
    return [key for key, value in row.items() if isinstance(value, (int, float)) and key not in {
        "decoded_frame_index", "sample_ordinal", "timestamp_seconds"
    }]


def summarize(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("No evaluated frames are available")
    numeric_keys = _metric_keys(rows[0])

    def group_summary(group: list[dict], label: str) -> dict:
        result = {"group": label, "frames": len(group)}
        for key in numeric_keys:
            result[f"mean_{key}"] = float(np.mean([float(row[key]) for row in group], dtype=np.float64))
        for key in ("r0_gain_psnr_db_bicubic_cbcr_shave8", "r0_gain_psnr_db_bilinear_cbcr_shave8"):
            result[f"negative_{key}_frames"] = sum(float(row[key]) < 0 for row in group)
        for key in ("r0_delta_ssim_bicubic_cbcr_shave8", "r0_delta_ssim_bilinear_cbcr_shave8"):
            result[f"negative_{key}_frames"] = sum(float(row[key]) < 0 for row in group)
        return result

    return {
        "overall": group_summary(rows, "all"),
        "by_sequence": [group_summary([row for row in rows if row["sequence"] == sequence], sequence)
                        for sequence in SEQUENCES],
    }


def _float_for_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity" if value < 0 else "NaN"
    if isinstance(value, dict):
        return {key: _float_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_float_for_json(item) for item in value]
    return value


def _thumbnail(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(rgb, mode="RGB").resize(THUMB_SIZE, Image.Resampling.LANCZOS)


def _write_contact_row(path: Path, sequence: str, frame_index: int, panels: list[Image.Image]) -> None:
    labels = ("Decoded 4K reference", "Bicubic Y + bicubic CbCr", "R0 integer Y + bicubic CbCr",
              "Bicubic Y + bilinear CbCr", "R0 integer Y + bilinear CbCr")
    if len(panels) != len(labels):
        raise ValueError("A contact row must contain the reference and all four output variants")
    header = 30
    canvas = Image.new("RGB", (THUMB_SIZE[0] * len(labels), THUMB_SIZE[1] + header), "black")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    draw.text((4, 2), f"{sequence} · source frame {frame_index}", font=font, fill="white")
    for column, (label, image) in enumerate(zip(labels, panels, strict=True)):
        x = column * THUMB_SIZE[0]
        draw.text((x + 4, header - 2), label, font=font, fill="white")
        canvas.paste(image, (x, header))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="JPEG", quality=92, optimize=True)


def _write_contact_sheet(path: Path, row_paths: list[Path]) -> None:
    if not row_paths:
        raise ValueError("Cannot write an empty contact sheet")
    row_height = THUMB_SIZE[1] + 30
    canvas = Image.new("RGB", (THUMB_SIZE[0] * 5, row_height * len(row_paths)), "black")
    for index, row_path in enumerate(row_paths):
        with Image.open(row_path) as row_image:
            canvas.paste(row_image.convert("RGB"), (0, index * row_height))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="JPEG", quality=92, optimize=True)


def run(
    source_dir: Path = SOURCE_DIR,
    quality_dir: Path = QUALITY_DIR,
    output_dir: Path = OUTPUT_DIR,
    frame_count: int = FRAME_COUNT,
    resume: bool = False,
    checkpoint_dir: Path = CHECKPOINT_DIR,
    min_start_memory_mib: int = MIN_START_MEMORY_MIB,
    min_available_memory_mib: int = MIN_AVAILABLE_MEMORY_MIB,
) -> dict:
    source_dir, quality_dir, output_dir = source_dir.resolve(), quality_dir.resolve(), output_dir.resolve()
    checkpoint_dir = checkpoint_dir.resolve()
    if (output_dir / "evaluation_manifest.json").is_file():
        raise FileExistsError(f"Color evaluation is already finalized: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not resume:
        raise FileExistsError(f"Refusing to overwrite non-empty color-evaluation output: {output_dir}")
    eval_manifest = json.loads((quality_dir / "evaluation_manifest.json").read_text(encoding="utf-8"))
    source_records = {record["sequence"]: record for record in eval_manifest["sources"]}
    quality_metrics_path = quality_dir / "per_clip_frame_metrics.csv"
    source_metric_rows = _metric_rows(quality_metrics_path)
    frame_ordinals = sampled_ordinals(frame_count)
    selected_contact_rows = contact_ordinals(frame_count)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    torch.set_num_threads(1)
    fixed = FixedReference(ROOT / "artifacts" / "quant")
    checkpoint_csv = checkpoint_dir / "partial_metrics.csv"
    checkpoint_manifest_path = checkpoint_dir / "checkpoint_manifest.json"
    checkpoint_contact_dir = checkpoint_dir / "contact_rows"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema": "member-a-r0-color-quality-checkpoint-v1",
        "script_sha256": sha256_file(Path(__file__)),
        "quality_metrics_sha256": sha256_file(quality_metrics_path),
        "quant_assets_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
        "sources": {sequence: source_records[sequence]["sha256"] for sequence in SEQUENCES},
        "sequences": list(SEQUENCES),
        "frame_count_per_sequence": frame_count,
        "frame_ordinals": list(frame_ordinals),
    }
    if checkpoint_manifest_path.is_file():
        if not resume:
            raise FileExistsError(f"Checkpoint already exists; use --resume or choose another directory: {checkpoint_dir}")
        saved_contract = json.loads(checkpoint_manifest_path.read_text(encoding="utf-8"))
        if saved_contract != contract:
            raise ValueError("Checkpoint contract differs from the current source, model, sampling, or script")
    elif checkpoint_csv.exists():
        raise ValueError("Checkpoint metrics exist without their contract manifest")
    else:
        checkpoint_manifest_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8", newline="\n")

    all_rows = _read_checkpoint_rows(checkpoint_csv)
    rows_by_key: dict[tuple[str, int], dict] = {}
    for row in all_rows:
        sequence, ordinal = row["sequence"], int(row["sample_ordinal"])
        if sequence not in SEQUENCES or ordinal not in frame_ordinals:
            raise ValueError("Checkpoint contains a sample outside the frozen schedule")
        clip = next(item for item in CLIPS if item.sequence == sequence)
        expected_index = clip.indices[ordinal]
        if int(row["decoded_frame_index"]) != expected_index:
            raise ValueError("Checkpoint frame index does not match its sample ordinal")
        expected_metric = source_metric_rows.get((sequence, expected_index))
        if (expected_metric is None or row["source_y_sha256"] != expected_metric["hr_y_sha256"]
                or row["lr_y_sha256"] != expected_metric["lr_y_sha256"]
                or row["r0_y_sha256"] != expected_metric["hybrid_y_sha256"]):
            raise ValueError("Checkpoint source frame does not match the frozen quality evaluation")
        key = (sequence, ordinal)
        if key in rows_by_key:
            raise ValueError("Checkpoint contains duplicate samples")
        rows_by_key[key] = row
    all_rows = [rows_by_key[key] for key in sorted(rows_by_key, key=lambda item: (SEQUENCES.index(item[0]), item[1]))]
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_dir = output_dir / "visuals"
    source_audit: list[dict] = []

    available_mib = _available_memory_mib()
    if min_start_memory_mib > 0 and available_mib is not None and available_mib < min_start_memory_mib:
        print(f"PAUSED_LOW_MEMORY: {available_mib} MiB available; need {min_start_memory_mib} MiB to start safely",
              flush=True)
        return {"status": "PAUSED_LOW_MEMORY", "completed_frames": len(all_rows),
                "checkpoint_dir": str(checkpoint_dir), "available_memory_mib": available_mib}

    for sequence in SEQUENCES:
        clip = next(item for item in CLIPS if item.sequence == sequence)
        record = source_records[sequence]
        source_path = source_dir / record["source_file"]
        if not source_path.is_file() or sha256_file(source_path) != record["sha256"]:
            raise ValueError(f"Source file is absent or differs from frozen manifest: {source_path}")
        frame_indices = [clip.indices[ordinal] for ordinal in frame_ordinals]
        expected_y_hashes = {int(item["decoded_frame_index"]): item["hr_y_sha256"]
                             for item in record["selected_frames"]}

        for sample_ordinal, (frame_index, hr_y, ref_cb, ref_cr) in enumerate(
            read_selected_yuv420(source_path, frame_indices, ffmpeg)
        ):
            ordinal = frame_ordinals[sample_ordinal]
            key = (sequence, ordinal)
            contact_row_path = checkpoint_contact_dir / f"{sequence.lower()}_ordinal_{ordinal:02d}.jpg"
            if key in rows_by_key and (ordinal not in selected_contact_rows or contact_row_path.is_file()):
                continue
            available_mib = _available_memory_mib()
            if min_available_memory_mib > 0 and available_mib is not None and available_mib < min_available_memory_mib:
                print(f"PAUSED_LOW_MEMORY: {available_mib} MiB available before {sequence} frame {frame_index}; "
                      f"checkpoint has {len(rows_by_key)} frames", flush=True)
                return {"status": "PAUSED_LOW_MEMORY", "completed_frames": len(rows_by_key),
                        "checkpoint_dir": str(checkpoint_dir), "available_memory_mib": available_mib}
            reference_row = source_metric_rows.get((sequence, frame_index))
            if reference_row is None:
                raise ValueError(f"No prior frozen Y evaluation row for {sequence} frame {frame_index}")
            hr_hash = sha_array(hr_y)
            if hr_hash != expected_y_hashes.get(frame_index) or hr_hash != reference_row["hr_y_sha256"]:
                raise ValueError(f"Decoded Y reference differs from frozen quality run at {sequence} frame {frame_index}")

            lr_y = make_lr(hr_y)
            if sha_array(lr_y) != reference_row["lr_y_sha256"]:
                raise ValueError(f"Synthetic LR Y differs from frozen quality run at {sequence} frame {frame_index}")
            bicubic_y = bicubic_baseline(lr_y)
            if sha_array(bicubic_y) != reference_row["bicubic_y_sha256"]:
                raise ValueError(f"Bicubic Y differs from frozen quality run at {sequence} frame {frame_index}")
            r0_y = integer_hybrid(lr_y, fixed)
            if sha_array(r0_y) != reference_row["hybrid_y_sha256"]:
                raise ValueError(f"R0 integer Y differs from frozen quality run at {sequence} frame {frame_index}")

            ref_cb_full = _resize_plane(ref_cb, WIDTH, HEIGHT, "bicubic")
            ref_cr_full = _resize_plane(ref_cr, WIDTH, HEIGHT, "bicubic")
            reference_rgb = ycbcr709_full_to_rgb(hr_y, ref_cb_full, ref_cr_full)
            cb_lr = _resize_plane(ref_cb, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT, "bicubic")
            cr_lr = _resize_plane(ref_cr, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT, "bicubic")

            row = {
                "sequence": sequence,
                "sample_ordinal": ordinal,
                "decoded_frame_index": frame_index,
                "timestamp_seconds": frame_index / int(record["dataset_fps"]),
                "source_y_sha256": hr_hash,
                "source_cbcr_sha256": hashlib.sha256(ref_cb.tobytes() + ref_cr.tobytes()).hexdigest(),
                "lr_y_sha256": sha_array(lr_y),
                "r0_y_sha256": sha_array(r0_y),
                "lr_cbcr_sha256": hashlib.sha256(cb_lr.tobytes() + cr_lr.tobytes()).hexdigest(),
                "reference_rgb_sha256": hashlib.sha256(reference_rgb.tobytes()).hexdigest(),
            }
            capture_thumbs: dict[str, Image.Image] = {}
            if ordinal in selected_contact_rows:
                capture_thumbs["reference"] = _thumbnail(reference_rgb)
            for method in ("bicubic", "bilinear"):
                cb_out = _resize_plane(cb_lr, CHROMA_WIDTH, CHROMA_HEIGHT, method)
                cr_out = _resize_plane(cr_lr, CHROMA_WIDTH, CHROMA_HEIGHT, method)
                for plane_name, source_plane, output_plane in (("cb", ref_cb, cb_out), ("cr", ref_cr, cr_out)):
                    prefix = f"{method}_{plane_name}_chroma"
                    row[f"{prefix}_psnr_db_full"] = psnr_y(source_plane, output_plane, 0)
                    row[f"{prefix}_psnr_db_shave4"] = psnr_y(source_plane, output_plane, 4)
                    row[f"{prefix}_ssim_full"] = _ssim_y(source_plane, output_plane, 0)
                    row[f"{prefix}_ssim_shave4"] = _ssim_y(source_plane, output_plane, 4)
                row[f"{method}_cbcr_output_sha256"] = hashlib.sha256(cb_out.tobytes() + cr_out.tobytes()).hexdigest()
                cb_full = _resize_plane(cb_out, WIDTH, HEIGHT, "bicubic")
                cr_full = _resize_plane(cr_out, WIDTH, HEIGHT, "bicubic")
                for y_name, out_y in (("bicubic_y", bicubic_y), ("r0_y", r0_y)):
                    variant = f"{y_name}_{method}_cbcr"
                    candidate_rgb = ycbcr709_full_to_rgb(out_y, cb_full, cr_full)
                    row.update(rgb_metrics(reference_rgb, candidate_rgb, variant + "_rgb"))
                    row[variant + "_rgb_sha256"] = hashlib.sha256(candidate_rgb.tobytes()).hexdigest()
                    if ordinal in selected_contact_rows:
                        capture_thumbs[variant] = _thumbnail(candidate_rgb)
                    del candidate_rgb
                del cb_full, cr_full, cb_out, cr_out
                gc.collect()

            for method in ("bicubic", "bilinear"):
                base_prefix = f"bicubic_y_{method}_cbcr_rgb"
                r0_prefix = f"r0_y_{method}_cbcr_rgb"
                for crop in ("full", "shave8"):
                    row[f"r0_gain_psnr_db_{method}_cbcr_{crop}"] = (
                        row[f"{r0_prefix}_psnr_db_{crop}"] - row[f"{base_prefix}_psnr_db_{crop}"]
                    )
                    row[f"r0_delta_ssim_{method}_cbcr_{crop}"] = (
                        row[f"{r0_prefix}_ssim_{crop}"] - row[f"{base_prefix}_ssim_{crop}"]
                    )

            if ordinal in selected_contact_rows:
                panels = [capture_thumbs[name] for name in (
                    "reference", "bicubic_y_bicubic_cbcr", "r0_y_bicubic_cbcr",
                    "bicubic_y_bilinear_cbcr", "r0_y_bilinear_cbcr",
                )]
                _write_contact_row(contact_row_path, sequence, frame_index, panels)
            del reference_rgb, capture_thumbs, r0_y, bicubic_y, lr_y
            gc.collect()
            rows_by_key[key] = row
            all_rows = [rows_by_key[saved_key] for saved_key in sorted(
                rows_by_key, key=lambda item: (SEQUENCES.index(item[0]), item[1]))]
            _write_csv_atomic(checkpoint_csv, all_rows)
            sequence_done = sum(saved_key[0] == sequence for saved_key in rows_by_key)
            if sequence_done % 5 == 0 or sequence_done == frame_count:
                print(f"[{sequence}] {sequence_done}/{frame_count} frames checkpointed", flush=True)
            available_mib = _available_memory_mib()
            if min_available_memory_mib > 0 and available_mib is not None and available_mib < min_available_memory_mib:
                print(f"PAUSED_LOW_MEMORY: checkpoint saved after {sequence} frame {frame_index}; "
                      f"{available_mib} MiB available", flush=True)
                return {"status": "PAUSED_LOW_MEMORY", "completed_frames": len(rows_by_key),
                        "checkpoint_dir": str(checkpoint_dir), "available_memory_mib": available_mib}

        sequence_done = sum(saved_key[0] == sequence for saved_key in rows_by_key)
        if sequence_done != frame_count:
            raise AssertionError(f"Incomplete frame set for {sequence}: {sequence_done}/{frame_count}")
        contact_paths = [checkpoint_contact_dir / f"{sequence.lower()}_ordinal_{ordinal:02d}.jpg"
                         for ordinal in selected_contact_rows]
        if any(not path.is_file() for path in contact_paths):
            raise AssertionError(f"Missing resumable contact-row images for {sequence}")
        _write_contact_sheet(visual_dir / f"{sequence.lower()}_color_contact.jpg", contact_paths)
        print(f"[{sequence}] completed {sequence_done}/{frame_count} frames", flush=True)
        source_audit.append({
            "sequence": sequence,
            "source_file": record["source_file"],
            "source_url": record["source_url"],
            "sha256": record["sha256"],
            "source_format": record["source_format"],
            "source_fps": record["dataset_fps"],
            "sampled_decoded_frame_indices": frame_indices,
            "sampled_ordinals": list(frame_ordinals),
        })

    if len(all_rows) != frame_count * len(SEQUENCES):
        raise AssertionError(f"Incomplete evaluation: {len(all_rows)} of {frame_count * len(SEQUENCES)} frames")

    metrics_path = output_dir / "per_frame_color_metrics.csv"
    _write_csv(metrics_path, all_rows)
    summary = summarize(all_rows)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(_float_for_json(summary), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                            encoding="utf-8", newline="\n")
    contact_sheets = [visual_dir / f"{sequence.lower()}_color_contact.jpg" for sequence in SEQUENCES]
    manifest = {
        "schema": "member-a-r0-color-quality-v1",
        "status": "SOFTWARE_COLOR_QUALITY_EVALUATION_NOT_BOARD_VALIDATION",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "script_sha256": sha256_file(Path(__file__)),
        "dataset": eval_manifest["dataset"],
        "source_records": source_audit,
        "model": eval_manifest["model"],
        "quant_assets_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pillow": PIL.__version__,
                     "pytorch": torch.__version__, "ffmpeg": Path(ffmpeg).name},
        "sampling": {"sequence_count": len(SEQUENCES), "frames_per_sequence": frame_count,
                     "fps": SAMPLE_FPS, "frame_ordinals": list(frame_ordinals),
                     "sequences": list(SEQUENCES)},
        "memory_guard": {"start_minimum_mib": min_start_memory_mib,
                         "frame_boundary_minimum_mib": min_available_memory_mib},
        "signal_contract": {
            "source_decode": "FFmpeg scale in_range=limited:out_range=pc, format=yuv420p; source 4K 4:2:0 planes are used as references",
            "synthetic_input": "Y 3840x2160 to 960x540 with Pillow BICUBIC; Cb/Cr 1920x1080 to 480x270 with Pillow BICUBIC",
            "luma_baseline": "Pillow BICUBIC x4 from 960x540 Y to 3840x2160 Y",
            "luma_r0": "frozen integer R0 FSRCNN d16/s8/m1/c16 x2 to 1920x1080 Y, then frozen Q14 Keys bicubic x2 to 3840x2160 Y",
            "chroma_candidates": "same 480x270 Cb/Cr inputs enlarged to 1920x1080 using Pillow BICUBIC or BILINEAR; both enlarged to 3840x2160 for RGB using the same Pillow BICUBIC 4:2:0-to-4:4:4 conversion",
            "rgb_conversion": "full-range BT.709 fixed-point YCbCr to RGB; signed chroma centered at 128; output clips to uint8. Source HEVC stream tags indicate limited range but do not explicitly identify a matrix, so BT.709 is the fixed evaluation assumption.",
            "metrics": "RGB PSNR uses joint three-channel MSE with peak 255; RGB SSIM is the arithmetic mean of per-channel SSIM using an 11x11 Gaussian (sigma 1.5), zero padding; full and shave-8 reported. Cb/Cr metrics are measured on the 1920x1080 4:2:0 output plane against decoded source chroma; full and shave-4 reported.",
            "aggregation": "arithmetic mean of per-frame metrics; regression counts are frame-level and do not imply statistical independence",
        },
        "outputs": {
            "files": [
                {"path": metrics_path.name, "bytes": metrics_path.stat().st_size, "sha256": sha256_file(metrics_path)},
                {"path": summary_path.name, "bytes": summary_path.stat().st_size, "sha256": sha256_file(summary_path)},
                *[{"path": path.relative_to(output_dir).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256_file(path)} for path in contact_sheets],
            ]
        },
        "checkpoint": {"schema": contract["schema"], "per_frame_resume_supported": True,
                       "checkpoint_contents_are_local_ignored_data": True},
        "limitations": [
            "UVG sources are lossy HEVC references and are licensed CC BY-NC for non-commercial use.",
            "Low-resolution input is synthetically downsampled from the decoded 4K reference; this is not native camera input.",
            "Cb/Cr interpolation is software-only and has not been accepted by B/C or verified on FPGA.",
            "RGB metrics depend on the stated FFmpeg range expansion, BT.709 full-range conversion, and chroma upsampling conventions; results are not directly comparable to a different color contract.",
            "This report does not establish board image quality, HDMI correctness, throughput, or real-time frame rate.",
        ],
    }
    manifest_path = output_dir / "evaluation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")
    return {"status": "PASS", "manifest": manifest, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the frozen R0 Y-plus-chroma software color pipeline")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--quality-dir", type=Path, default=QUALITY_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--frames-per-sequence", type=int, default=FRAME_COUNT)
    parser.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINT_DIR)
    parser.add_argument("--resume", action="store_true", help="Resume a validated per-frame checkpoint")
    parser.add_argument("--min-start-memory-mib", type=int, default=MIN_START_MEMORY_MIB,
                        help="Require this much free physical memory after imports before evaluation starts")
    parser.add_argument("--min-available-memory-mib", type=int, default=MIN_AVAILABLE_MEMORY_MIB,
                        help="Pause at a frame boundary below this free-memory threshold; 0 disables the continuation guard")
    args = parser.parse_args()
    result = run(args.source_dir, args.quality_dir, args.output_dir, args.frames_per_sequence,
                 args.resume, args.checkpoint_dir, args.min_start_memory_mib, args.min_available_memory_mib)
    if result["status"] != "PASS":
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 75
    overall = result["summary"]["overall"]
    print(json.dumps({
        "status": "PASS",
        "output_dir": str(args.output_dir.resolve()),
        "frames": overall["frames"],
        "mean_shave8_rgb_psnr_gain_db_bicubic_cbcr": overall["mean_r0_gain_psnr_db_bicubic_cbcr_shave8"],
        "mean_shave8_rgb_ssim_delta_bicubic_cbcr": overall["mean_r0_delta_ssim_bicubic_cbcr_shave8"],
        "mean_shave8_rgb_psnr_gain_db_bilinear_cbcr": overall["mean_r0_gain_psnr_db_bilinear_cbcr_shave8"],
        "mean_shave8_rgb_ssim_delta_bilinear_cbcr": overall["mean_r0_delta_ssim_bilinear_cbcr_shave8"],
        "negative_gain_frames_bicubic_cbcr": overall["negative_r0_gain_psnr_db_bicubic_cbcr_shave8_frames"],
        "negative_gain_frames_bilinear_cbcr": overall["negative_r0_gain_psnr_db_bilinear_cbcr_shave8_frames"],
    }, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
