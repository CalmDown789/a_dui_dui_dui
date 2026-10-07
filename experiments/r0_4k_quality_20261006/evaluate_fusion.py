from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.r0_4k_quality_20261006.color_demo import read_selected_yuv420
from experiments.r0_4k_quality_20261006.evaluate import (
    CLIPS,
    HEIGHT,
    LR_HEIGHT,
    LR_WIDTH,
    WIDTH,
    bicubic_baseline,
    integer_hybrid,
    make_lr,
    quant_tree_sha256,
    sha256_file,
    sha_array,
)
from experiments.r0_4k_quality_20261006.evaluate_color_quality import (
    CHROMA_HEIGHT,
    CHROMA_WIDTH,
    FRAME_COUNT,
    LR_CHROMA_HEIGHT,
    LR_CHROMA_WIDTH,
    SEQUENCES,
    _available_memory_mib,
    _read_csv,
    _resize_plane,
    _ssim_y,
    _write_csv_atomic,
    psnr_rgb,
    rgb_metrics,
    sampled_ordinals,
    ycbcr709_full_to_rgb,
)

QUALITY_DIR = ROOT / "results" / "r0_4k_quality_20261006"
COLOR_DIR = ROOT / "results" / "r0_color_quality_20261007"
OUTPUT_DIR = ROOT / "results" / "r0_fusion_diagnostic_20261007"
CHECKPOINT_DIR = ROOT / ".data" / "r0_fusion_diagnostic_20261007_checkpoint"
GLOBAL_ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)
TILE_QUANTILES = (50.0, 75.0)
TILE_ALPHA_PAIRS = ((0.0, 0.5), (0.0, 0.75), (0.25, 0.5), (0.25, 0.75))
TILE_GRID = (16, 9)  # 960x540 LR is divided into 60x60-pixel tiles.
MIN_AVAILABLE_MEMORY_MIB = 1024
PREVIEW_SIZE = (160, 90)
RESUME_COMPATIBILITY_NOTE = (
    "CPU thread limit changed to one; validation reuses previously hash-verified baseline metrics and "
    "resumes only missing sequence/frame records; selected preview tiles are checkpointed. "
    "Candidate math, inputs, candidate grid, and reported metrics are unchanged."
)


def candidate_specs() -> list[dict]:
    result = [{"candidate_id": f"global_a{alpha:.2f}", "kind": "global", "alpha": alpha}
              for alpha in GLOBAL_ALPHAS]
    for quantile in TILE_QUANTILES:
        for low, high in TILE_ALPHA_PAIRS:
            result.append({
                "candidate_id": f"tile_q{int(quantile)}_a{low:.2f}_{high:.2f}",
                "kind": "edge_tile",
                "quantile": quantile,
                "alpha_low": low,
                "alpha_high": high,
            })
    return result


def blend_y(bicubic_y: np.ndarray, r0_y: np.ndarray, alpha: float | np.ndarray) -> np.ndarray:
    if bicubic_y.shape != r0_y.shape or bicubic_y.dtype != np.uint8 or r0_y.dtype != np.uint8:
        raise ValueError("Fusion inputs must be equally shaped uint8 luma frames")
    weights = np.asarray(alpha, dtype=np.float32)
    if np.any(~np.isfinite(weights)) or np.any((weights < 0) | (weights > 1)):
        raise ValueError("Fusion weights must be finite and in [0, 1]")
    if weights.ndim and weights.shape != bicubic_y.shape:
        raise ValueError("Per-pixel fusion weights must match the luma frame")
    mixed = bicubic_y.astype(np.float32) * (1.0 - weights) + r0_y.astype(np.float32) * weights
    # Round half-up to make the software candidate's uint8 conversion explicit.
    return np.floor(mixed + 0.5).clip(0, 255).astype(np.uint8)


def tile_activity(lr_y: np.ndarray) -> np.ndarray:
    if lr_y.shape != (LR_HEIGHT, LR_WIDTH) or lr_y.dtype != np.uint8:
        raise ValueError("Expected the frozen 960x540 uint8 luma input")
    columns, rows = TILE_GRID
    tile_w, tile_h = LR_WIDTH // columns, LR_HEIGHT // rows
    values = lr_y.astype(np.float32)
    gx = np.zeros_like(values)
    gy = np.zeros_like(values)
    gx[:, 1:] = np.abs(values[:, 1:] - values[:, :-1])
    gy[1:, :] = np.abs(values[1:, :] - values[:-1, :])
    strength = gaussian_filter(np.hypot(gx, gy), sigma=1.0, mode="reflect")
    return strength.reshape(rows, tile_h, columns, tile_w).mean(axis=(1, 3), dtype=np.float64).astype(np.float32)


def edge_tile_mask_map(lr_y: np.ndarray, quantile: float) -> np.ndarray:
    if not 0 <= quantile <= 100:
        raise ValueError("Invalid tile quantile")
    activity = tile_activity(lr_y)
    threshold = float(np.percentile(activity, quantile))
    encoded = np.where(activity >= threshold, 255, 0).astype(np.uint8)
    mask = Image.fromarray(encoded, mode="L").resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    return np.asarray(mask, dtype=np.float32).copy() / 255.0


def edge_tile_weight_map(lr_y: np.ndarray, quantile: float, alpha_low: float,
                         alpha_high: float, mask_map: np.ndarray | None = None) -> np.ndarray:
    if not 0 <= alpha_low <= alpha_high <= 1:
        raise ValueError("Invalid tile fusion parameters")
    binary_map = mask_map if mask_map is not None else edge_tile_mask_map(lr_y, quantile)
    if binary_map.shape != (HEIGHT, WIDTH):
        raise ValueError("Cached tile mask must match the 4K output shape")
    return alpha_low + (alpha_high - alpha_low) * binary_map


def candidate_y(spec: dict, bicubic_y: np.ndarray, r0_y: np.ndarray,
                lr_y: np.ndarray, mask_maps: dict[float, np.ndarray] | None = None) -> np.ndarray:
    if spec["kind"] == "global":
        weight: float | np.ndarray = float(spec["alpha"])
    elif spec["kind"] == "edge_tile":
        weight = edge_tile_weight_map(lr_y, float(spec["quantile"]),
                                      float(spec["alpha_low"]), float(spec["alpha_high"]),
                                      None if mask_maps is None else mask_maps[float(spec["quantile"])])
    else:
        raise ValueError(f"Unknown candidate kind: {spec['kind']}")
    return blend_y(bicubic_y, r0_y, weight)


def _write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")
    temporary.replace(path)


def _records(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    return {(row["sequence"], int(row["decoded_frame_index"])): row for row in _read_csv(path)}


def _frame_indices() -> dict[str, list[int]]:
    ordinals = sampled_ordinals(FRAME_COUNT)
    clips = {clip.sequence: clip for clip in CLIPS}
    return {sequence: [clips[sequence].indices[ordinal] for ordinal in ordinals] for sequence in SEQUENCES}


def _reference_and_chroma(hr_y: np.ndarray, source_cb: np.ndarray, source_cr: np.ndarray,
                          lr_y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Keep exactly the established BT.709/full-range reference and bicubic chroma pipeline.
    ref_cb_full = _resize_plane(source_cb, WIDTH, HEIGHT, "bicubic")
    ref_cr_full = _resize_plane(source_cr, WIDTH, HEIGHT, "bicubic")
    reference_rgb = ycbcr709_full_to_rgb(hr_y, ref_cb_full, ref_cr_full)
    cb_lr = _resize_plane(source_cb, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT, "bicubic")
    cr_lr = _resize_plane(source_cr, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT, "bicubic")
    cb_out = _resize_plane(cb_lr, CHROMA_WIDTH, CHROMA_HEIGHT, "bicubic")
    cr_out = _resize_plane(cr_lr, CHROMA_WIDTH, CHROMA_HEIGHT, "bicubic")
    cb_full = _resize_plane(cb_out, WIDTH, HEIGHT, "bicubic")
    cr_full = _resize_plane(cr_out, WIDTH, HEIGHT, "bicubic")
    return reference_rgb, cb_full, cr_full, hashlib.sha256(cb_lr.tobytes() + cr_lr.tobytes()).hexdigest()


def _error_panel(reference: np.ndarray, candidate: np.ndarray) -> Image.Image:
    width, height = PREVIEW_SIZE
    error = np.abs(reference.astype(np.int16) - candidate.astype(np.int16)).max(axis=2).astype(np.uint8)
    pooled = error.reshape(height, HEIGHT // height, width, WIDTH // width).max(axis=(1, 3))
    pooled = np.clip(pooled.astype(np.uint16) * 5, 0, 255).astype(np.uint8)
    return ImageOps.colorize(Image.fromarray(pooled, mode="L"), black="#111827", white="#ff382b")


def _thumb(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(rgb, mode="RGB").resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)


def _save_regression_sheet(rows: list[dict], panels: dict[tuple[str, int], tuple[Image.Image, ...]],
                           path: Path) -> None:
    if not rows:
        return
    labels = ("Reference", "Bicubic", "R0", "|Reference−Bicubic| ×5", "|Reference−R0| ×5")
    title_h, gap = 22, 4
    panel_w, panel_h = PREVIEW_SIZE
    canvas = Image.new("RGB", (panel_w * len(labels), (panel_h + title_h + gap) * len(rows)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=12)
    for index, row in enumerate(rows):
        key = (row["sequence"], int(row["decoded_frame_index"]))
        y = index * (panel_h + title_h + gap)
        title = (f"{row['sequence']} frame {key[1]} | dPSNR {row['r0_delta_psnr_db_shave8']:+.3f} dB"
                 f" | dSSIM {row['r0_delta_ssim_shave8']:+.6f}")
        draw.text((2, y + 2), title, fill="black", font=font)
        for column, (label, panel) in enumerate(zip(labels, panels[key], strict=True)):
            x = column * panel_w
            if index == 0:
                draw.text((x + 2, y + title_h), label, fill="black", font=font)
            canvas.paste(panel, (x, y + title_h + gap))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="JPEG", quality=90, optimize=True)


def _spec_map() -> dict[str, dict]:
    return {spec["candidate_id"]: spec for spec in candidate_specs()}


def _choose_best(train_rows: list[dict], specs: dict[str, dict], kind: str) -> dict:
    eligible = [spec for spec in specs.values() if spec["kind"] == kind]
    scores = []
    for spec in eligible:
        values = [float(row["psnr_db_shave8"]) for row in train_rows
                  if row["candidate_id"] == spec["candidate_id"]]
        scores.append((float(np.mean(values, dtype=np.float64)), spec["candidate_id"], spec))
    if not scores or any(not math.isfinite(item[0]) for item in scores):
        raise ValueError("Cannot select a fusion candidate from empty/non-finite training scores")
    scores.sort(key=lambda item: (-item[0], item[1]))
    return {"candidate_id": scores[0][1], "spec": scores[0][2], "mean_train_psnr_db_shave8": scores[0][0]}


def _aggregate(rows: list[dict]) -> dict:
    keys = ("delta_psnr_db_full", "delta_psnr_db_shave8", "delta_ssim_full", "delta_ssim_shave8")
    return {
        "frames": len(rows),
        **{f"mean_{key}": float(np.mean([float(row[key]) for row in rows], dtype=np.float64)) for key in keys},
        "negative_psnr_gain_frames_shave8": sum(float(row["delta_psnr_db_shave8"]) < 0 for row in rows),
        "negative_ssim_delta_frames_shave8": sum(float(row["delta_ssim_shave8"]) < 0 for row in rows),
    }


def _contracts() -> tuple[dict, dict, dict]:
    quality_manifest_path = QUALITY_DIR / "evaluation_manifest.json"
    color_manifest_path = COLOR_DIR / "evaluation_manifest.json"
    quality_manifest = json.loads(quality_manifest_path.read_text(encoding="utf-8"))
    color_manifest = json.loads(color_manifest_path.read_text(encoding="utf-8"))
    quality_rows = _records(QUALITY_DIR / "per_clip_frame_metrics.csv")
    color_rows = _records(COLOR_DIR / "per_frame_color_metrics.csv")
    if len(color_rows) != len(SEQUENCES) * FRAME_COUNT:
        raise ValueError(f"Expected {len(SEQUENCES) * FRAME_COUNT} frozen color rows, found {len(color_rows)}")
    if len(quality_rows) < len(color_rows):
        raise ValueError("The frozen luma evaluation is missing frame records")
    if quality_manifest.get("model") != color_manifest.get("model"):
        raise ValueError("Luma and RGB evaluations do not use the same frozen model contract")
    if color_manifest.get("quant_assets_sha256") != quant_tree_sha256(ROOT / "artifacts" / "quant"):
        raise ValueError("Frozen integer model files differ from the color evaluation's quantized assets")
    if set(SEQUENCES) - {row["sequence"] for row in color_rows.values()}:
        raise ValueError("Color evaluation is missing one of the three frozen sequences")
    return quality_manifest, color_manifest, {"quality": quality_rows, "color": color_rows}


def _verify_baselines(sequence: str, frame_index: int, lr_y: np.ndarray, bicubic_y: np.ndarray,
                      r0_y: np.ndarray, reference_rgb: np.ndarray, cb_full: np.ndarray, cr_full: np.ndarray,
                      expected: dict[str, str], *, verify_metrics: bool = True,
                      create_rgb_candidates: bool = True) -> tuple[np.ndarray | None, np.ndarray | None, dict]:
    if sha_array(lr_y) != expected["lr_y_sha256"] or sha_array(r0_y) != expected["r0_y_sha256"]:
        raise ValueError(f"Frozen LR/R0 output hash differs for {sequence} frame {frame_index}")
    reference_hash = hashlib.sha256(reference_rgb.tobytes()).hexdigest()
    if reference_hash != expected["reference_rgb_sha256"]:
        raise ValueError(f"Decoded RGB reference hash differs for {sequence} frame {frame_index}")
    deltas = {
        "r0_delta_psnr_db_shave8": float(expected["r0_gain_psnr_db_bicubic_cbcr_shave8"]),
        "r0_delta_ssim_shave8": float(expected["r0_delta_ssim_bicubic_cbcr_shave8"]),
    }
    if not create_rgb_candidates:
        return None, None, deltas
    baseline_rgb = ycbcr709_full_to_rgb(bicubic_y, cb_full, cr_full)
    r0_rgb = ycbcr709_full_to_rgb(r0_y, cb_full, cr_full)
    baseline_hash = hashlib.sha256(baseline_rgb.tobytes()).hexdigest()
    r0_hash = hashlib.sha256(r0_rgb.tobytes()).hexdigest()
    if baseline_hash != expected["bicubic_y_bicubic_cbcr_rgb_sha256"]:
        raise ValueError(f"Recreated bicubic RGB baseline hash differs for {sequence} frame {frame_index}")
    if r0_hash != expected["r0_y_bicubic_cbcr_rgb_sha256"]:
        raise ValueError(f"Recreated R0 RGB output hash differs for {sequence} frame {frame_index}")
    if verify_metrics:
        base_metrics = rgb_metrics(reference_rgb, baseline_rgb, "baseline")
        r0_metrics = rgb_metrics(reference_rgb, r0_rgb, "r0")
        for metric_name, expected_key in (
            ("baseline_psnr_db_full", "bicubic_y_bicubic_cbcr_rgb_psnr_db_full"),
            ("baseline_psnr_db_shave8", "bicubic_y_bicubic_cbcr_rgb_psnr_db_shave8"),
            ("baseline_ssim_full", "bicubic_y_bicubic_cbcr_rgb_ssim_full"),
            ("baseline_ssim_shave8", "bicubic_y_bicubic_cbcr_rgb_ssim_shave8"),
            ("r0_psnr_db_full", "r0_y_bicubic_cbcr_rgb_psnr_db_full"),
            ("r0_psnr_db_shave8", "r0_y_bicubic_cbcr_rgb_psnr_db_shave8"),
            ("r0_ssim_full", "r0_y_bicubic_cbcr_rgb_ssim_full"),
            ("r0_ssim_shave8", "r0_y_bicubic_cbcr_rgb_ssim_shave8"),
        ):
            actual = base_metrics.get(metric_name, r0_metrics.get(metric_name))
            if abs(actual - float(expected[expected_key])) > 1e-9:
                raise ValueError(f"Frozen metric mismatch for {sequence} frame {frame_index}: {metric_name}")
    return baseline_rgb, r0_rgb, deltas


def _check_memory(min_available_memory_mib: int) -> None:
    available = _available_memory_mib()
    if available is not None and available < min_available_memory_mib:
        raise MemoryError(f"Only {available} MiB physical memory remains; pause threshold is {min_available_memory_mib} MiB")


def run(output_dir: Path = OUTPUT_DIR, checkpoint_dir: Path = CHECKPOINT_DIR,
        source_dir: Path | None = None, resume: bool = False,
        min_available_memory_mib: int = MIN_AVAILABLE_MEMORY_MIB) -> dict:
    quality_manifest, color_manifest, existing = _contracts()
    source_metric_rows = existing["color"]
    negative_psnr_rows = sorted(
        (row for row in source_metric_rows.values() if float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]) < 0),
        key=lambda row: float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]),
    )[:6]
    negative_ssim_rows = sorted(
        (row for row in source_metric_rows.values() if float(row["r0_delta_ssim_bicubic_cbcr_shave8"]) < 0),
        key=lambda row: float(row["r0_delta_ssim_bicubic_cbcr_shave8"]),
    )[:6]
    regression_preview_keys = {
        (row["sequence"], int(row["decoded_frame_index"]))
        for row in negative_psnr_rows + negative_ssim_rows
    }
    source_dir = source_dir or ROOT / ".data" / "r0_4k_quality_20261006" / "sources"
    source_dir, output_dir, checkpoint_dir = source_dir.resolve(), output_dir.resolve(), checkpoint_dir.resolve()
    if (output_dir / "fusion_manifest.json").exists():
        raise FileExistsError(f"Fusion diagnostic is already complete: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not resume:
        raise FileExistsError(f"Refusing to overwrite existing output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    panel_checkpoint_dir = checkpoint_dir / "preview_panels"
    panel_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    specs = _spec_map()
    tuning_path = checkpoint_dir / "tuning_frame_metrics.csv"
    validation_path = checkpoint_dir / "holdout_frame_metrics.csv"
    contract_path = checkpoint_dir / "fusion_checkpoint_manifest.json"
    contract = {
        "schema": "member-a-r0-fusion-checkpoint-v1",
        "script_sha256": sha256_file(Path(__file__)),
        "quality_manifest_sha256": sha256_file(QUALITY_DIR / "evaluation_manifest.json"),
        "color_manifest_sha256": sha256_file(COLOR_DIR / "evaluation_manifest.json"),
        "quant_assets_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
        "sequences": list(SEQUENCES),
        "frames_per_sequence": FRAME_COUNT,
        "candidate_ids": list(specs),
        "tile_grid_lr": list(TILE_GRID),
    }
    if contract_path.exists():
        saved_contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if saved_contract != contract:
            ignored = {"script_sha256", "compatible_resume_script_sha256", "resume_compatibility_note"}
            saved_core = {key: value for key, value in saved_contract.items() if key not in ignored}
            current_core = {key: value for key, value in contract.items() if key not in ignored}
            if not resume or saved_core != current_core:
                raise ValueError("Checkpoint contract changed after data was written; refusing unsafe resume")
            compatible_hashes = set(saved_contract.get("compatible_resume_script_sha256", []))
            compatible_hashes.add(saved_contract["script_sha256"])
            compatible_hashes.add(contract["script_sha256"])
            contract["compatible_resume_script_sha256"] = sorted(compatible_hashes)
            contract["resume_compatibility_note"] = RESUME_COMPATIBILITY_NOTE
            _write_json_atomic(contract_path, contract)
    elif tuning_path.exists() or validation_path.exists():
        raise ValueError("Checkpoint CSV exists without its contract manifest")
    else:
        _write_json_atomic(contract_path, contract)

    tuning_rows = _read_csv(tuning_path) if tuning_path.exists() else []
    tuning_done = {(row["sequence"], int(row["decoded_frame_index"])) for row in tuning_rows}
    color_records = {record["sequence"]: record for record in color_manifest["source_records"]}
    indices_by_sequence = _frame_indices()
    # Match the established evaluator: one CPU thread avoids large temporary
    # workspaces and contention on the constrained workstation.
    torch.set_num_threads(1)
    fixed = None
    from member_a.fixed_reference import FixedReference
    fixed = FixedReference(ROOT / "artifacts" / "quant")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    regression_panels: dict[tuple[str, int], tuple[Image.Image, ...]] = {}
    panel_suffixes = ("reference", "baseline", "r0", "error_baseline", "error_r0")
    for key in regression_preview_keys:
        panel_paths = [panel_checkpoint_dir / f"{key[0]}_{key[1]:04d}_{suffix}.png"
                       for suffix in panel_suffixes]
        if all(path.is_file() for path in panel_paths):
            regression_panels[key] = tuple(Image.open(path).convert("RGB") for path in panel_paths)

    for sequence in SEQUENCES:
        source_record = color_records[sequence]
        source_path = source_dir / source_record["source_file"]
        if not source_path.is_file() or sha256_file(source_path) != source_record["sha256"]:
            raise ValueError(f"Source is missing or differs from its frozen hash: {source_path}")
        wanted = indices_by_sequence[sequence]
        for frame_index, hr_y, source_cb, source_cr in read_selected_yuv420(source_path, wanted, ffmpeg):
            key = (sequence, frame_index)
            if key in tuning_done:
                continue
            _check_memory(min_available_memory_mib)
            expected = existing["color"].get(key)
            if expected is None:
                raise ValueError(f"No frozen RGB evaluation record for {key}")
            lr_y = make_lr(hr_y)
            bicubic_y = bicubic_baseline(lr_y)
            r0_y = integer_hybrid(lr_y, fixed)
            reference_rgb, cb_full, cr_full, lr_cbcr_hash = _reference_and_chroma(
                hr_y, source_cb, source_cr, lr_y
            )
            if lr_cbcr_hash != expected["lr_cbcr_sha256"]:
                raise ValueError(f"Frozen chroma downsample hash differs for {sequence} frame {frame_index}")
            base_rgb, r0_rgb, r0_delta = _verify_baselines(
                sequence, frame_index, lr_y, bicubic_y, r0_y, reference_rgb, cb_full, cr_full, expected
            )
            color_row = {
                "sequence": sequence,
                "decoded_frame_index": frame_index,
                "r0_delta_psnr_db_shave8": r0_delta["r0_delta_psnr_db_shave8"],
                "r0_delta_ssim_shave8": r0_delta["r0_delta_ssim_shave8"],
            }
            candidate_rows = []
            mask_maps = {quantile: edge_tile_mask_map(lr_y, quantile) for quantile in TILE_QUANTILES}
            for spec in specs.values():
                mixed_y = candidate_y(spec, bicubic_y, r0_y, lr_y, mask_maps)
                mixed_rgb = ycbcr709_full_to_rgb(mixed_y, cb_full, cr_full)
                candidate_rows.append({
                    **color_row,
                    "candidate_id": spec["candidate_id"],
                    "psnr_db_full": psnr_rgb(reference_rgb, mixed_rgb, 0),
                    "psnr_db_shave8": psnr_rgb(reference_rgb, mixed_rgb, 8),
                })
                del mixed_y, mixed_rgb
            tuning_rows.extend(candidate_rows)
            _write_csv_atomic(tuning_path, tuning_rows)
            tuning_done.add(key)
            sequence_done = sum(done_sequence == sequence for done_sequence, _ in tuning_done)
            if sequence_done % 5 == 0:
                print(f"[tune {sequence}] {sequence_done}/{FRAME_COUNT} frames", flush=True)

            del hr_y, source_cb, source_cr, lr_y, bicubic_y, r0_y, reference_rgb, cb_full, cr_full, base_rgb, r0_rgb

    expected_frame_count = len(SEQUENCES) * FRAME_COUNT
    unique_tuning = {(row["sequence"], int(row["decoded_frame_index"])) for row in tuning_rows}
    if len(unique_tuning) != expected_frame_count:
        raise AssertionError(f"Incomplete tuning pass: {len(unique_tuning)} / {expected_frame_count} frames")
    tuning_csv = output_dir / "candidate_frame_psnr.csv"
    _write_csv_atomic(tuning_csv, tuning_rows)

    folds = {}
    for heldout in SEQUENCES:
        train_sequences = [sequence for sequence in SEQUENCES if sequence != heldout]
        train_rows = [row for row in tuning_rows if row["sequence"] in train_sequences]
        folds[heldout] = {
            "train_sequences": train_sequences,
            "selected_global": _choose_best(train_rows, specs, "global"),
            "selected_edge_tile": _choose_best(train_rows, specs, "edge_tile"),
        }
        print(f"[select holdout={heldout}] global={folds[heldout]['selected_global']['candidate_id']}; "
              f"edge_tile={folds[heldout]['selected_edge_tile']['candidate_id']}", flush=True)

    validation_rows = _read_csv(validation_path) if validation_path.exists() else []
    validation_done = {(row["strategy"], row["sequence"], int(row["decoded_frame_index"]))
                       for row in validation_rows}
    for sequence in SEQUENCES:
        selected_specs = [
            ("global", folds[sequence]["selected_global"]["spec"]),
            ("edge_tile", folds[sequence]["selected_edge_tile"]["spec"]),
        ]
        source_record = color_records[sequence]
        source_path = source_dir / source_record["source_file"]
        missing_validation_frames = {
            frame_index for frame_index in indices_by_sequence[sequence]
            if any((strategy, sequence, frame_index) not in validation_done for strategy, _ in selected_specs)
        }
        missing_preview_frames = {
            frame_index for seq, frame_index in regression_preview_keys
            if seq == sequence and (seq, frame_index) not in regression_panels
        }
        wanted = sorted(missing_validation_frames | missing_preview_frames)
        if not wanted:
            continue
        for frame_index, hr_y, source_cb, source_cr in read_selected_yuv420(source_path, wanted, ffmpeg):
            _check_memory(min_available_memory_mib)
            key = (sequence, frame_index)
            expected = existing["color"].get(key)
            if expected is None:
                raise ValueError(f"No frozen RGB evaluation record for {key}")
            lr_y = make_lr(hr_y)
            bicubic_y = bicubic_baseline(lr_y)
            r0_y = integer_hybrid(lr_y, fixed)
            reference_rgb, cb_full, cr_full, lr_cbcr_hash = _reference_and_chroma(
                hr_y, source_cb, source_cr, lr_y
            )
            if lr_cbcr_hash != expected["lr_cbcr_sha256"]:
                raise ValueError(f"Frozen chroma downsample hash differs for {sequence} frame {frame_index}")
            baseline_rgb, r0_rgb, r0_delta = _verify_baselines(
                sequence, frame_index, lr_y, bicubic_y, r0_y,
                reference_rgb, cb_full, cr_full, expected,
                verify_metrics=False, create_rgb_candidates=key in regression_preview_keys,
            )
            if key in regression_preview_keys:
                regression_panels[key] = (
                    _thumb(reference_rgb), _thumb(baseline_rgb), _thumb(r0_rgb),
                    _error_panel(reference_rgb, baseline_rgb), _error_panel(reference_rgb, r0_rgb),
                )
                for suffix, panel in zip(panel_suffixes, regression_panels[key], strict=True):
                    panel.save(panel_checkpoint_dir / f"{sequence}_{frame_index:04d}_{suffix}.png")
            baseline_metrics = {
                "baseline_psnr_db_full": float(expected["bicubic_y_bicubic_cbcr_rgb_psnr_db_full"]),
                "baseline_psnr_db_shave8": float(expected["bicubic_y_bicubic_cbcr_rgb_psnr_db_shave8"]),
                "baseline_ssim_full": float(expected["bicubic_y_bicubic_cbcr_rgb_ssim_full"]),
                "baseline_ssim_shave8": float(expected["bicubic_y_bicubic_cbcr_rgb_ssim_shave8"]),
            }
            for strategy, spec in selected_specs:
                validation_key = (strategy, sequence, frame_index)
                if validation_key in validation_done:
                    continue
                mixed_y = candidate_y(spec, bicubic_y, r0_y, lr_y)
                mixed_rgb = ycbcr709_full_to_rgb(mixed_y, cb_full, cr_full)
                metrics = rgb_metrics(reference_rgb, mixed_rgb, "candidate")
                validation_rows.append({
                    "strategy": strategy,
                    "candidate_id": spec["candidate_id"],
                    "sequence": sequence,
                    "decoded_frame_index": frame_index,
                    "candidate_psnr_db_full": metrics["candidate_psnr_db_full"],
                    "candidate_psnr_db_shave8": metrics["candidate_psnr_db_shave8"],
                    "candidate_ssim_full": metrics["candidate_ssim_full"],
                    "candidate_ssim_shave8": metrics["candidate_ssim_shave8"],
                    "baseline_psnr_db_full": baseline_metrics["baseline_psnr_db_full"],
                    "baseline_psnr_db_shave8": baseline_metrics["baseline_psnr_db_shave8"],
                    "baseline_ssim_full": baseline_metrics["baseline_ssim_full"],
                    "baseline_ssim_shave8": baseline_metrics["baseline_ssim_shave8"],
                    "delta_psnr_db_full": metrics["candidate_psnr_db_full"] - baseline_metrics["baseline_psnr_db_full"],
                    "delta_psnr_db_shave8": metrics["candidate_psnr_db_shave8"] - baseline_metrics["baseline_psnr_db_shave8"],
                    "delta_ssim_full": metrics["candidate_ssim_full"] - baseline_metrics["baseline_ssim_full"],
                    "delta_ssim_shave8": metrics["candidate_ssim_shave8"] - baseline_metrics["baseline_ssim_shave8"],
                })
                validation_done.add(validation_key)
                _write_csv_atomic(validation_path, validation_rows)
                sequence_done = sum(row["sequence"] == sequence for row in validation_rows)
                if sequence_done % 10 == 0:
                    print(f"[holdout {sequence}] {sequence_done // 2}/{FRAME_COUNT} frames", flush=True)
                del mixed_y, mixed_rgb
            del hr_y, source_cb, source_cr, lr_y, bicubic_y, r0_y, reference_rgb, cb_full, cr_full

    expected_validation_rows = expected_frame_count * 2
    if len(validation_rows) != expected_validation_rows:
        raise AssertionError(f"Incomplete holdout evaluation: {len(validation_rows)} / {expected_validation_rows} records")
    validation_csv = output_dir / "leave_one_sequence_out_metrics.csv"
    _write_csv_atomic(validation_csv, validation_rows)

    by_strategy = {}
    for strategy in ("global", "edge_tile"):
        rows = [row for row in validation_rows if row["strategy"] == strategy]
        by_sequence = {
            sequence: _aggregate([row for row in rows if row["sequence"] == sequence])
            for sequence in SEQUENCES
        }
        by_strategy[strategy] = {"cross_validated": _aggregate(rows), "by_heldout_sequence": by_sequence}

    original_r0_regressions = [
        row for row in source_metric_rows.values()
        if float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]) < 0
        or float(row["r0_delta_ssim_bicubic_cbcr_shave8"]) < 0
    ]
    original_r0_regressions.sort(key=lambda row: (
        min(float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]), 0),
        float(row["r0_delta_ssim_bicubic_cbcr_shave8"]),
    ))
    # Keep the contact sheet readable while ensuring both negative-PSNR and negative-SSIM tails are represented.
    map_rows = []
    seen_map_keys = set()
    for row in negative_psnr_rows + negative_ssim_rows:
        key = (row["sequence"], int(row["decoded_frame_index"]))
        if key in regression_panels and key not in seen_map_keys:
            map_rows.append({
                "sequence": key[0], "decoded_frame_index": key[1],
                "r0_delta_psnr_db_shave8": float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]),
                "r0_delta_ssim_shave8": float(row["r0_delta_ssim_bicubic_cbcr_shave8"]),
            })
            seen_map_keys.add(key)
    map_path = output_dir / "visuals" / "worst_regression_error_maps.jpg"
    _save_regression_sheet(map_rows, regression_panels, map_path)

    all_r0 = [row for row in source_metric_rows.values()]
    overall = json.loads((COLOR_DIR / "summary.json").read_text(encoding="utf-8"))["overall"]
    summary = {
        "schema": "member-a-r0-fusion-diagnostic-v1",
        "status": "COMPLETED_SOFTWARE_CROSS_VALIDATION_NOT_HARDWARE_VALIDATION",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_baseline": {
            "color_evaluation_manifest_sha256": sha256_file(COLOR_DIR / "evaluation_manifest.json"),
            "quality_evaluation_manifest_sha256": sha256_file(QUALITY_DIR / "evaluation_manifest.json"),
            "quant_assets_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
            "sequence_count": len(SEQUENCES), "frames_per_sequence": FRAME_COUNT,
            "total_frames": len(source_metric_rows), "regression_frames_any": len(original_r0_regressions),
            "negative_r0_psnr_gain_shave8_frames": sum(
                float(row["r0_gain_psnr_db_bicubic_cbcr_shave8"]) < 0 for row in all_r0),
            "negative_r0_ssim_delta_shave8_frames": sum(
                float(row["r0_delta_ssim_bicubic_cbcr_shave8"]) < 0 for row in all_r0),
            "mean_r0_gain_psnr_db_shave8": overall["mean_r0_gain_psnr_db_bicubic_cbcr_shave8"],
            "mean_r0_delta_ssim_shave8": overall["mean_r0_delta_ssim_bicubic_cbcr_shave8"],
        },
        "selection_protocol": {
            "split": "Leave one complete video sequence out; select on the other two; evaluate once on the held-out sequence.",
            "selection_metric": "Mean per-frame RGB PSNR, shave-8, on training sequences only; deterministic ties prefer lexical candidate id.",
            "candidate_grid": list(specs.values()),
            "tile_grid_lr": {"columns": TILE_GRID[0], "rows": TILE_GRID[1], "tile_size_pixels": [60, 60]},
            "tile_policy": "Compute Gaussian-smoothed LR gradient magnitude; threshold tile means at each frame's 50th or 75th percentile; bilinearly upsample tile weights to 4K; mix Y with half-up uint8 rounding.",
            "no_reference_at_inference": True,
            "weights_changed": False,
        },
        "folds": folds,
        "cross_validated": by_strategy,
        "limitations": [
            "Software post-processing candidates only; no R0 weights, quantization assets, or B/C files were modified.",
            "The 90 source frames are three UVG sequences and are not independent samples; this is a small cross-sequence check, not a broad generalization claim.",
            "Inputs are synthetically downsampled from decoded 4K references. Results depend on the frozen FFmpeg range handling, BT.709 RGB conversion, chroma path, and shave-8 metric contract.",
            "Edge-tile fusion is a PC feasibility experiment. Its mask generation, storage, quality, and resource cost have not been implemented or validated in FPGA hardware.",
            "This evaluation does not establish board output quality, timing, throughput, or real-time frame rate. UVG source content is CC BY-NC and must remain non-commercial.",
        ],
        "outputs": {
            "candidate_frame_psnr_csv": {"path": tuning_csv.name, "sha256": sha256_file(tuning_csv)},
            "leave_one_sequence_out_csv": {"path": validation_csv.name, "sha256": sha256_file(validation_csv)},
            "worst_regression_error_maps": {"path": map_path.relative_to(output_dir).as_posix(), "sha256": sha256_file(map_path)},
        },
    }
    summary_path = output_dir / "summary.json"
    _write_json_atomic(summary_path, summary)
    report_path = output_dir / "R0_FUSION_DIAGNOSTIC_REPORT_2026-10-07.md"
    _write_report(output_dir, summary)
    manifest = {
        "schema": "member-a-r0-fusion-manifest-v1",
        "status": summary["status"],
        "generated_utc": summary["generated_utc"],
        "script_sha256": sha256_file(Path(__file__)),
        "source_evaluation_manifest_sha256": sha256_file(COLOR_DIR / "evaluation_manifest.json"),
        "quant_assets_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
        "software": {"python": sys.version.split()[0], "numpy": np.__version__, "pytorch": torch.__version__},
        "summary_sha256": sha256_file(summary_path),
        "outputs": [
            {"path": path.relative_to(output_dir).as_posix(), "bytes": path.stat().st_size,
             "sha256": sha256_file(path)}
            for path in (tuning_csv, validation_csv, summary_path, map_path, report_path)
        ],
    }
    _write_json_atomic(output_dir / "fusion_manifest.json", manifest)
    return summary


def _write_report(output_dir: Path, summary: dict) -> None:
    frozen = summary["frozen_baseline"]
    strategy_rows = []
    for strategy, result in summary["cross_validated"].items():
        aggregate = result["cross_validated"]
        strategy_rows.append(
            f"| {strategy} | {aggregate['mean_delta_psnr_db_shave8']:+.4f} dB | "
            f"{aggregate['mean_delta_ssim_shave8']:+.6f} | "
            f"{aggregate['negative_psnr_gain_frames_shave8']}/{aggregate['frames']} | "
            f"{aggregate['negative_ssim_delta_frames_shave8']}/{aggregate['frames']} |"
        )
    lines = [
        "# R0 融合候选与退化帧诊断",
        "",
        f"生成时间：{summary['generated_utc']}",
        "",
        "## 结果",
        "",
        f"本次固定并复核了 {frozen['total_frames']} 帧 RGB 评测基线：R0 相对同口径双三次平均 PSNR "
        f"提升 {frozen['mean_r0_gain_psnr_db_shave8']:+.4f} dB，平均 SSIM 变化 {frozen['mean_r0_delta_ssim_shave8']:+.6f}；"
        f"其中 {frozen['negative_r0_psnr_gain_shave8_frames']} 帧 PSNR 下降，"
        f"{frozen['negative_r0_ssim_delta_shave8_frames']} 帧 SSIM 下降。",
        "",
        "融合权重只用另外两条视频的平均 RGB PSNR（裁边 8 像素）选出，再在整条留出视频上评测。权重图只读取 960×540 输入，不读取参考图像；正式 R0 模型与量化资产保持不变。",
        "",
        "| 留出视频策略 | PSNR 平均变化 | SSIM 平均变化 | PSNR 下降帧 | SSIM 下降帧 |",
        "| --- | ---: | ---: | ---: | ---: |",
        *strategy_rows,
        "",
        "完整跨视频结果见 `leave_one_sequence_out_metrics.csv`；每个留出折实际选择的参数见 `summary.json`。PSNR/SSIM 以同一帧双三次输出为参照，分别报告每帧指标差的算术平均。",
        "",
        "## 退化帧检查",
        "",
        "`visuals/worst_regression_error_maps.jpg` 对最差 PSNR/SSIM 帧并列展示参考、双三次、R0，以及参考残差热图。残差热图对 4K 区域做最大值池化并放大显示，只用于定位，不代表新增质量指标。",
        "",
        "## 结论边界",
        "",
        "本结果是 90 帧、三条 UVG 序列上的 PC 软件验证。它不改变已冻结的 R0，不证明 FPGA 资源、时序、帧率或板上图像质量；边缘分块融合仅为软件可行性候选，若有收益仍需另行评估硬件成本和视觉伪影。UVG 数据仅限 CC BY-NC 非商业使用。",
        "",
        "## 可复现入口",
        "",
        "```powershell",
        "& '.venv\\Scripts\\python.exe' -m experiments.r0_4k_quality_20261006.evaluate_fusion",
        "```",
        "",
        "运行会先核验冻结源数据、R0 输出、RGB Golden 与量化资产哈希；中断后使用 `--resume` 从忽略目录中的帧级检查点续跑。",
    ]
    (output_dir / "R0_FUSION_DIAGNOSTIC_REPORT_2026-10-07.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-validate global and edge-tile fusion for frozen R0 RGB output")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINT_DIR)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--min-available-memory-mib", type=int, default=MIN_AVAILABLE_MEMORY_MIB)
    args = parser.parse_args()
    summary = run(args.output_dir, args.checkpoint_dir, args.source_dir, args.resume,
                  args.min_available_memory_mib)
    print(json.dumps({
        "status": summary["status"],
        "output_dir": str(args.output_dir.resolve()),
        "baseline": summary["frozen_baseline"],
        "cross_validated": summary["cross_validated"],
    }, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
