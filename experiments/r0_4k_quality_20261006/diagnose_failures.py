from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy.ndimage import gaussian_filter

from experiments.r0_4k_quality_20261006.evaluate import (
    HEIGHT,
    WIDTH,
    FixedReference,
    _error_maxpool_thumbnail,
    decode_selected_frames,
    integer_hybrid,
    make_lr,
    sha256_file,
    sha_array,
    thumb,
)

ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT / "results" / "r0_4k_quality_20261006"
SOURCE_DIR = ROOT / ".data" / "r0_4k_quality_20261006" / "sources"
TARGET_SEQUENCES = ("Beauty", "Jockey")
ZOOM_COUNT_PER_CLASS = 6
PANEL_SIZE = (320, 180)
ERROR_GAIN = 8


def classify(gain_db: float, ssim_delta: float) -> str:
    psnr_down = gain_db < 0
    ssim_down = ssim_delta < 0
    if psnr_down and ssim_down:
        return "psnr_and_ssim_down"
    if psnr_down:
        return "psnr_only_down"
    if ssim_down:
        return "ssim_only_down"
    return "no_regression"


def spatial_features(hr_y: np.ndarray, previous_y: np.ndarray | None) -> dict[str, float | None]:
    if hr_y.shape != (HEIGHT, WIDTH) or hr_y.dtype != np.uint8:
        raise ValueError("Expected a 3840x2160 uint8 reference Y frame")
    lr = make_lr(hr_y).astype(np.float32)
    gx = np.abs(np.diff(lr, axis=1))
    gy = np.abs(np.diff(lr, axis=0))
    detail = np.abs(lr - gaussian_filter(lr, sigma=1.0, mode="nearest"))
    motion = None
    if previous_y is not None:
        previous_lr = make_lr(previous_y).astype(np.int16)
        motion = float(np.mean(np.abs(lr.astype(np.int16) - previous_lr), dtype=np.float64))
    return {
        "reference_gradient_l1_960x540": float((gx.mean(dtype=np.float64) + gy.mean(dtype=np.float64)) / 2.0),
        "reference_high_frequency_l1_960x540": float(detail.mean(dtype=np.float64)),
        "reference_motion_mae_960x540": motion,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No records to write: {path}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _group_summary(rows: list[dict]) -> dict:
    output = {"count": len(rows)}
    numeric = (
        "hybrid_gain_vs_bicubic_db_shave8",
        "hybrid_ssim_delta_vs_bicubic_shave8",
        "reference_gradient_l1_960x540",
        "reference_high_frequency_l1_960x540",
        "reference_motion_mae_960x540",
    )
    for key in numeric:
        values = [float(row[key]) for row in rows if row.get(key) not in (None, "")]
        output[f"mean_{key}"] = float(np.mean(values, dtype=np.float64)) if values else None
        output[f"median_{key}"] = float(np.median(values)) if values else None
    return output


def _tile_with_largest_regression(reference: np.ndarray, bicubic: np.ndarray, hybrid: np.ndarray,
                                  tile_width: int = 480, tile_height: int = 270) -> tuple[int, int, float]:
    if any(frame.shape != (HEIGHT, WIDTH) for frame in (reference, bicubic, hybrid)):
        raise ValueError("Expected aligned 3840x2160 planes")
    if WIDTH % tile_width or HEIGHT % tile_height:
        raise ValueError("Tile size must divide the 4K frame dimensions")
    best = (-1, -1, -float("inf"))
    ref16 = reference.astype(np.int16)
    bic16 = bicubic.astype(np.int16)
    hyb16 = hybrid.astype(np.int16)
    for y in range(0, HEIGHT, tile_height):
        for x in range(0, WIDTH, tile_width):
            region = np.s_[y:y + tile_height, x:x + tile_width]
            bic_err = ref16[region].astype(np.int32) - bic16[region].astype(np.int32)
            hyb_err = ref16[region].astype(np.int32) - hyb16[region].astype(np.int32)
            excess_mse = float(np.mean(hyb_err * hyb_err - bic_err * bic_err, dtype=np.float64))
            if excess_mse > best[2]:
                best = (x, y, excess_mse)
    return best


def _error_rgb(reference: np.ndarray, hybrid: np.ndarray, size: tuple[int, int] = PANEL_SIZE) -> Image.Image:
    if reference.shape[0] % size[1] == 0 and reference.shape[1] % size[0] == 0:
        pooled = _error_maxpool_thumbnail(reference, hybrid, size=size, gain=ERROR_GAIN)
    else:
        if reference.shape != hybrid.shape or reference.ndim != 2:
            raise ValueError("Residual preview requires aligned 2D planes")
        height, width = reference.shape
        out_width, out_height = size
        difference = np.abs(reference.astype(np.int16) - hybrid.astype(np.int16)).astype(np.uint8)
        pooled = np.zeros((out_height, out_width), dtype=np.uint8)
        y_edges = np.linspace(0, height, out_height + 1, dtype=np.int32)
        x_edges = np.linspace(0, width, out_width + 1, dtype=np.int32)
        for out_y in range(out_height):
            band = difference[y_edges[out_y]:max(y_edges[out_y] + 1, y_edges[out_y + 1])]
            for out_x in range(out_width):
                patch = band[:, x_edges[out_x]:max(x_edges[out_x] + 1, x_edges[out_x + 1])]
                pooled[out_y, out_x] = patch.max(initial=0)
        pooled = np.clip(pooled.astype(np.uint16) * ERROR_GAIN, 0, 255).astype(np.uint8)
    return ImageOps.colorize(Image.fromarray(pooled, mode="L"), black="#111827", white="#ff382b")


def _save_contact_sheet(rows: list[dict], panels: dict[str, tuple[Image.Image, ...]], target: Path,
                        labels: tuple[str, ...], zoom: bool = False) -> None:
    gap, label_h = 8, 28
    panel_w, panel_h = PANEL_SIZE
    columns = len(labels)
    canvas = Image.new("RGB", (gap * (columns + 1) + columns * panel_w,
                               gap + len(rows) * (panel_h + label_h + gap)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    for row_index, row in enumerate(rows):
        y = gap + row_index * (panel_h + label_h + gap)
        key = row["sample_id"]
        current = panels[key]
        for col, panel in enumerate(current):
            x = gap + col * (panel_w + gap)
            if row_index == 0:
                draw.text((x + 2, y + 2), labels[col], fill="black", font=font)
            canvas.paste(panel, (x, y + label_h))
        title = (f"{key} | {row['regression_class']} | PSNR {float(row['hybrid_gain_vs_bicubic_db_shave8']):+.3f} dB"
                 f" | SSIM {float(row['hybrid_ssim_delta_vs_bicubic_shave8']):+.6f}")
        if zoom and row.get("diagnostic_roi"):
            title += f" | ROI {row['diagnostic_roi']}"
        draw.text((gap, y + panel_h + label_h + 1), title[:150], fill="black", font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="JPEG", quality=88, optimize=True)


def _source_map(manifest_path: Path) -> dict[str, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {record["sequence"]: record for record in manifest["sources"]}


def _feature_correlations(rows: list[dict]) -> dict[str, float | None]:
    result = {}
    for feature_key in ("reference_gradient_l1_960x540", "reference_high_frequency_l1_960x540",
                        "reference_motion_mae_960x540"):
        valid = [row for row in rows if row.get(feature_key) not in (None, "")]
        if len(valid) < 3:
            result[feature_key] = None
            continue
        x = np.asarray([float(row[feature_key]) for row in valid], dtype=np.float64)
        y = np.asarray([float(row["hybrid_gain_vs_bicubic_db_shave8"]) for row in valid], dtype=np.float64)
        result[feature_key] = float(np.corrcoef(x, y)[0, 1]) if np.std(x) and np.std(y) else None
    return result


def finalize_existing(output_dir: Path) -> dict:
    """Add within-sequence correlations to a completed feature report without rerunning inference."""
    output_dir = output_dir.resolve()
    rows = _read_csv(output_dir / "per_frame_features.csv")
    summary_path = output_dir / "diagnostics_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["content_feature_gain_correlations_by_sequence"] = {
        sequence: _feature_correlations([row for row in rows if row["sequence"] == sequence])
        for sequence in TARGET_SEQUENCES
    }
    summary["interpretation"] = (
        "Correlations are descriptive, not causal. The pooled value combines two different sequences and may be confounded by sequence identity; "
        "use the within-sequence correlations and category means for interpretation."
    )
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                            encoding="utf-8", newline="\n")
    return summary


def run(source_dir: Path = SOURCE_DIR, evaluation_dir: Path = EVALUATION_DIR,
        output_dir: Path | None = None, refresh_visuals: bool = False) -> dict:
    source_dir = source_dir.resolve()
    evaluation_dir = evaluation_dir.resolve()
    output_dir = (output_dir or ROOT / "results" / "r0_failure_diagnosis_20261006").resolve()
    if output_dir.exists():
        existing_files = [path for path in output_dir.rglob("*") if path.is_file()]
        if refresh_visuals:
            allowed = {output_dir / "per_frame_features.csv", output_dir / "diagnostics_summary.json",
                       output_dir / "visuals" / "all_regression_frames.jpg",
                       output_dir / "visuals" / "worst_case_rois.jpg"}
            if set(existing_files) != allowed:
                raise FileExistsError(f"Visual refresh requires the exact previously generated output set: {existing_files}")
        elif existing_files:
            raise FileExistsError(f"Refusing to overwrite prior diagnostic files: {existing_files[:3]}")
    clip_rows = [row for row in _read_csv(evaluation_dir / "per_clip_frame_metrics.csv")
                 if row["sequence"] in TARGET_SEQUENCES]
    if len(clip_rows) != len(TARGET_SEQUENCES) * 50:
        raise ValueError(f"Expected 100 Beauty/Jockey rows, found {len(clip_rows)}")
    by_sequence: dict[str, list[dict]] = {name: [] for name in TARGET_SEQUENCES}
    for row in clip_rows:
        row["decoded_frame_index"] = int(row["decoded_frame_index"])
        row["hybrid_gain_vs_bicubic_db_shave8"] = float(row["hybrid_gain_vs_bicubic_db_shave8"])
        row["hybrid_ssim_delta_vs_bicubic_shave8"] = float(row["hybrid_ssim_delta_vs_bicubic_shave8"])
        row["regression_class"] = classify(row["hybrid_gain_vs_bicubic_db_shave8"],
                                           row["hybrid_ssim_delta_vs_bicubic_shave8"])
        by_sequence[row["sequence"]].append(row)

    manifest_sources = _source_map(evaluation_dir / "evaluation_manifest.json")
    for sequence in TARGET_SEQUENCES:
        source_path = source_dir / manifest_sources[sequence]["source_file"]
        if not source_path.is_file() or sha256_file(source_path) != manifest_sources[sequence]["sha256"]:
            raise ValueError(f"Source hash does not match the original evaluation manifest: {source_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    visual_dir = output_dir / "visuals"
    visual_dir.mkdir(exist_ok=True)
    feature_rows: list[dict] = []
    full_panels: dict[str, tuple[Image.Image, ...]] = {}
    negative_psnr = sorted((row for row in clip_rows if row["hybrid_gain_vs_bicubic_db_shave8"] < 0),
                          key=lambda row: row["hybrid_gain_vs_bicubic_db_shave8"])
    ssim_only = sorted((row for row in clip_rows if row["regression_class"] == "ssim_only_down"),
                       key=lambda row: row["hybrid_ssim_delta_vs_bicubic_shave8"])
    zoom_rows = negative_psnr[:ZOOM_COUNT_PER_CLASS] + ssim_only[:ZOOM_COUNT_PER_CLASS]
    zoom_ids = {row["sample_id"] for row in zoom_rows}
    zoom_panels: dict[str, tuple[Image.Image, ...]] = {}

    quant_dir = ROOT / "artifacts" / "quant"
    torch.set_num_threads(1)
    fixed = FixedReference(quant_dir)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    for sequence in TARGET_SEQUENCES:
        source_path = source_dir / manifest_sources[sequence]["source_file"]
        sequence_rows = sorted(by_sequence[sequence], key=lambda row: row["decoded_frame_index"])
        indices = [row["decoded_frame_index"] for row in sequence_rows]
        row_by_index = {row["decoded_frame_index"]: row for row in sequence_rows}
        previous_y = None
        for frame_index, hr_y in decode_selected_frames(
            source_path, indices, ffmpeg, 120,
            raw_yuv420=False,
        ):
            # Beauty and Jockey are both 120 fps HEVC sequences.
            row = row_by_index[frame_index]
            if sha_array(hr_y) != row["hr_y_sha256"]:
                raise ValueError(f"Decoded Y hash mismatch: {row['sample_id']}")
            metrics = spatial_features(hr_y, previous_y)
            previous_y = hr_y
            feature_record = {**row, **metrics}
            feature_rows.append(feature_record)

            if row["regression_class"] == "no_regression":
                continue
            lr_y = make_lr(hr_y)
            if sha_array(lr_y) != row["lr_y_sha256"]:
                raise ValueError(f"Decoded LR hash mismatch: {row['sample_id']}")
            bicubic = np.asarray(Image.fromarray(lr_y, mode="L").resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC),
                                 dtype=np.uint8)
            if sha_array(bicubic) != row["bicubic_y_sha256"]:
                raise ValueError(f"Bicubic output hash mismatch: {row['sample_id']}")
            hybrid = integer_hybrid(lr_y, fixed)
            if sha_array(hybrid) != row["hybrid_y_sha256"]:
                raise ValueError(f"R0 integer output hash mismatch: {row['sample_id']}")
            size = PANEL_SIZE
            full_panels[row["sample_id"]] = (
                Image.fromarray(thumb(hr_y, size), mode="L").convert("RGB"),
                Image.fromarray(thumb(bicubic, size), mode="L").convert("RGB"),
                Image.fromarray(thumb(hybrid, size), mode="L").convert("RGB"),
                _error_rgb(hr_y, hybrid, size),
            )
            if row["sample_id"] in zoom_ids:
                x, y, excess = _tile_with_largest_regression(hr_y, bicubic, hybrid)
                roi = f"x{x}:x{x+480},y{y}:y{y+270}; ΔMSE={excess:.2f}"
                row["diagnostic_roi"] = roi
                region = np.s_[y:y + 270, x:x + 480]
                zoom_panels[row["sample_id"]] = (
                    Image.fromarray(thumb(hr_y[region], size), mode="L").convert("RGB"),
                    Image.fromarray(thumb(bicubic[region], size), mode="L").convert("RGB"),
                    Image.fromarray(thumb(hybrid[region], size), mode="L").convert("RGB"),
                    _error_rgb(hr_y[region], hybrid[region], size),
                )

    feature_rows.sort(key=lambda row: row["sample_id"])
    _write_csv(output_dir / "per_frame_features.csv", feature_rows)
    all_categories = sorted({row["regression_class"] for row in feature_rows})
    by_category = {category: _group_summary([row for row in feature_rows if row["regression_class"] == category])
                   for category in all_categories}
    by_sequence = {sequence: {
        "frame_count": len(by_sequence[sequence]),
        "regression_categories": {
            category: sum(row["regression_class"] == category for row in by_sequence[sequence])
            for category in ("psnr_and_ssim_down", "psnr_only_down", "ssim_only_down", "no_regression")
        },
        "mean_shave8_psnr_gain_db": float(np.mean([row["hybrid_gain_vs_bicubic_db_shave8"] for row in by_sequence[sequence]])),
        "mean_shave8_ssim_delta": float(np.mean([row["hybrid_ssim_delta_vs_bicubic_shave8"] for row in by_sequence[sequence]])),
    } for sequence in TARGET_SEQUENCES}
    correlations = _feature_correlations(feature_rows)
    correlations_by_sequence = {
        sequence: _feature_correlations([row for row in feature_rows if row["sequence"] == sequence])
        for sequence in TARGET_SEQUENCES
    }

    _save_contact_sheet(
        [row for row in clip_rows if row["regression_class"] != "no_regression"], full_panels,
        visual_dir / "all_regression_frames.jpg",
        ("Decoded reference", "Bicubic x4", "R0 integer hybrid", f"max |R0-reference| x{ERROR_GAIN} clipped"),
    )
    ordered_zoom = [row for row in zoom_rows if row["sample_id"] in zoom_panels]
    _save_contact_sheet(
        ordered_zoom, zoom_panels, visual_dir / "worst_case_rois.jpg",
        ("Reference ROI", "Bicubic ROI", "R0 ROI", f"max |R0-reference| x{ERROR_GAIN} clipped"), zoom=True,
    )
    source_record = {sequence: {"source_file": manifest_sources[sequence]["source_file"],
                                "sha256": manifest_sources[sequence]["sha256"]}
                     for sequence in TARGET_SEQUENCES}
    summary = {
        "schema": "member-a-r0-4k-failure-diagnosis-v1",
        "status": "SOFTWARE_DIAGNOSTIC_ONLY",
        "scope": "All 100 sampled frames from Beauty and Jockey; all 64 frames with a negative shave-8 PSNR gain or SSIM delta are visually regenerated and hash-checked.",
        "sequences": by_sequence,
        "regression_categories": by_category,
        "content_feature_gain_correlations": correlations,
        "content_feature_gain_correlations_by_sequence": correlations_by_sequence,
        "interpretation": "Correlations are descriptive, not causal. The pooled value combines two different sequences and may be confounded by sequence identity; use the within-sequence correlations and category means for interpretation.",
        "sources": source_record,
        "model_quant_params_sha256": sha256_file(quant_dir / "quant_params.json"),
        "artifacts": {
            "per_frame_features": "per_frame_features.csv",
            "all_regression_frames": "visuals/all_regression_frames.jpg",
            "worst_case_rois": "visuals/worst_case_rois.jpg",
        },
    }
    (output_dir / "diagnostics_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce and characterize all Beauty/Jockey regression frames")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--evaluation-dir", type=Path, default=EVALUATION_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "r0_failure_diagnosis_20261006")
    parser.add_argument("--finalize-existing", action="store_true",
                        help="Refresh descriptive correlations from saved per-frame features without rerunning inference")
    parser.add_argument("--refresh-visuals", action="store_true",
                        help="Re-render the diagnostic sheets from verified source/model hashes")
    args = parser.parse_args()
    if args.finalize_existing:
        result = finalize_existing(args.output_dir)
        print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir.resolve()),
                          "targeted_frames": sum(record["frame_count"] for record in result["sequences"].values()),
                          "regression_frames": sum(item["count"] for key, item in result["regression_categories"].items()
                                                    if key != "no_regression")}, indent=2, ensure_ascii=False))
        return 0
    result = run(args.source_dir, args.evaluation_dir, args.output_dir, refresh_visuals=args.refresh_visuals)
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir.resolve()),
                      "targeted_frames": sum(record["frame_count"] for record in result["sequences"].values()),
                      "regression_frames": sum(summary["count"] for category, summary in result["regression_categories"].items()
                                                if category != "no_regression")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
