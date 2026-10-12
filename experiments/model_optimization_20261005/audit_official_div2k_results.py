from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_IDS = [f"{value:04d}" for value in range(801, 901)]
PSNR_BOOTSTRAP_SEED = 20261007
SSIM_BOOTSTRAP_SEED = 20261008
BOOTSTRAP_SAMPLES = 20_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collection_sha256(paths: list[Path]) -> str:
    pieces = "".join(sha256_file(path) for path in sorted(paths, key=lambda item: item.name))
    return hashlib.sha256(pieces.encode("ascii")).hexdigest()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    names = [row["image"] for row in rows]
    if names != EXPECTED_IDS:
        raise ValueError("Per-image CSV must contain DIV2K validation IDs 0801-0900 exactly once, in order")
    required = {
        "frozen_integer_psnr_db",
        "frozen_integer_ssim",
        "candidate_integer_psnr_db",
        "candidate_integer_ssim",
        "candidate_integer_delta_vs_frozen_db",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"CSV is missing required fields: {sorted(required - set(rows[0] if rows else []))}")
    for row in rows:
        values = [float(row[key]) for key in required]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Non-finite metric in row {row['image']}")
        expected_delta = float(row["candidate_integer_psnr_db"]) - float(row["frozen_integer_psnr_db"])
        if not math.isclose(expected_delta, float(row["candidate_integer_delta_vs_frozen_db"]), abs_tol=1e-10):
            raise ValueError(f"Stored paired delta disagrees with columns for {row['image']}")
    return rows


def paired_bootstrap(values: np.ndarray, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(BOOTSTRAP_SAMPLES, len(values)), replace=True).mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    psnr = np.asarray([float(row["candidate_integer_delta_vs_frozen_db"]) for row in rows], dtype=np.float64)
    ssim = np.asarray([
        float(row["candidate_integer_ssim"]) - float(row["frozen_integer_ssim"])
        for row in rows
    ], dtype=np.float64)
    order = np.argsort(psnr)
    counts = {
        "psnr_improved": int(np.count_nonzero(psnr > 1e-12)),
        "psnr_regressed": int(np.count_nonzero(psnr < -1e-12)),
        "psnr_equal_within_1e-12_db": int(np.count_nonzero(np.abs(psnr) <= 1e-12)),
        "ssim_improved": int(np.count_nonzero(ssim > 1e-12)),
        "ssim_regressed": int(np.count_nonzero(ssim < -1e-12)),
        "ssim_equal_within_1e-12": int(np.count_nonzero(np.abs(ssim) <= 1e-12)),
    }
    return {
        "samples": len(rows),
        "candidate_integer_mean_psnr_db": float(np.mean([float(row["candidate_integer_psnr_db"]) for row in rows])),
        "frozen_integer_mean_psnr_db": float(np.mean([float(row["frozen_integer_psnr_db"]) for row in rows])),
        "candidate_integer_mean_ssim": float(np.mean([float(row["candidate_integer_ssim"]) for row in rows])),
        "frozen_integer_mean_ssim": float(np.mean([float(row["frozen_integer_ssim"]) for row in rows])),
        "paired_delta_psnr_db": {
            "mean": float(np.mean(psnr)),
            "median": float(np.median(psnr)),
            "minimum": float(np.min(psnr)),
            "maximum": float(np.max(psnr)),
            "bootstrap_95pct_ci": paired_bootstrap(psnr, PSNR_BOOTSTRAP_SEED),
            "bootstrap_seed": PSNR_BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_SAMPLES,
        },
        "paired_delta_ssim": {
            "mean": float(np.mean(ssim)),
            "median": float(np.median(ssim)),
            "minimum": float(np.min(ssim)),
            "maximum": float(np.max(ssim)),
            "bootstrap_95pct_ci_exploratory": paired_bootstrap(ssim, SSIM_BOOTSTRAP_SEED),
            "bootstrap_seed": SSIM_BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_SAMPLES,
        },
        "per_image_direction_counts": counts,
        "best_psnr_image": rows[int(order[-1])]["image"],
        "worst_psnr_image": rows[int(order[0])]["image"],
        "median_delta_image": rows[int(np.argmin(np.abs(psnr - np.median(psnr))))]["image"],
    }


def verify_identity(
    *,
    rows: list[dict[str, str]],
    source_summary: dict[str, Any],
    dataset_manifest_path: Path,
    hr_dir: Path,
    frozen_checkpoint: Path,
    frozen_quant_params: Path,
    candidate_checkpoint: Path,
    candidate_quant_params: Path,
) -> dict[str, Any]:
    dataset = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    images = sorted(path for path in hr_dir.iterdir() if path.is_file())
    image_ids = [path.stem for path in images]
    if dataset.get("dataset") != "DIV2K_official_validation_HR" or len(images) != 100:
        raise ValueError("Expected the 100-image official DIV2K validation HR set")
    if image_ids != EXPECTED_IDS:
        raise ValueError("HR directory does not contain exactly IDs 0801-0900")
    actual_collection_sha = collection_sha256(images)
    if actual_collection_sha != dataset.get("image_collection_sha256"):
        raise ValueError("DIV2K HR collection hash differs from the committed dataset manifest")

    group = source_summary["groups"]["DIV2K_official_valid_100"]
    file_hashes = {
        "frozen_checkpoint_sha256": sha256_file(frozen_checkpoint),
        "frozen_quant_params_sha256": sha256_file(frozen_quant_params),
        "candidate_checkpoint_sha256": sha256_file(candidate_checkpoint),
        "candidate_quant_params_sha256": sha256_file(candidate_quant_params),
    }
    for key, actual in file_hashes.items():
        if source_summary.get(key) != actual:
            raise ValueError(f"Evaluation summary {key} does not match current file")
    if int(group.get("samples", -1)) != len(rows):
        raise ValueError("Summary sample count differs from per-image CSV")
    return {
        "dataset_archive_sha256": dataset["archive_sha256"],
        "image_collection_sha256": actual_collection_sha,
        "evaluation_scope": source_summary.get("dataset_source"),
        "downsampling": source_summary.get("downsampling"),
        "metric_protocol": source_summary.get("metrics"),
        "model_and_data_hashes": file_hashes,
        "source_summary_matches_current_assets": True,
    }


def render_visual_review(
    *,
    rows: list[dict[str, str]],
    hr_dir: Path,
    r0_quant: Path,
    candidate_quant: Path,
    output_png: Path,
    output_json: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    import sys

    import torch
    import torch.nn.functional as F
    from PIL import Image, ImageDraw, ImageFont

    sys.path.insert(0, str(project_root / "src"))
    from member_a.data import EvalDataset
    from member_a.fixed_reference import FixedReference

    row_by_id = {row["image"]: row for row in rows}
    deltas = np.asarray([float(row["candidate_integer_delta_vs_frozen_db"]) for row in rows])
    dataset = EvalDataset(hr_dir)
    r0_engine, candidate_engine = FixedReference(r0_quant), FixedReference(candidate_quant)
    torch.set_num_threads(4)

    crop_size = 192
    scale = 2
    tile_size = crop_size * scale
    col_labels = ["HR reference", "bicubic x2", "R0 integer", "EMA v2 integer", "R0 abs error x4", "EMA abs error x4"]
    title_height, header_height, row_label_height, margin = 46, 32, 30, 12
    col_width = tile_size + margin
    width = len(col_labels) * col_width + margin
    id_to_idx = {name: index for index, name in enumerate([path.stem for path in sorted(hr_dir.iterdir()) if path.is_file()])}

    def texture_score(image_id: str) -> float:
        _, _, hr_tensor = dataset[id_to_idx[image_id]]
        image = np.floor(hr_tensor.squeeze(0).numpy() * 255.0 + 0.5).astype(np.int16)
        gx = np.abs(np.diff(image, axis=1)).mean()
        gy = np.abs(np.diff(image, axis=0)).mean()
        return float(gx + gy)

    top_gain_ids = [rows[index]["image"] for index in np.argsort(deltas)[-10:][::-1]]
    textured_gain_id = max(top_gain_ids, key=texture_score)
    median_index = int(np.argmin(np.abs(deltas - np.median(deltas))))
    ids = [textured_gain_id, rows[int(np.argmin(deltas))]["image"], rows[median_index]["image"]]
    labels = ["high-gain textured sample", "lowest-gain sample", "median PSNR delta"]
    height = title_height + header_height + len(ids) * (row_label_height + tile_size + margin) + margin
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((margin, 10), "DIV2K validation visual audit - local review crops only", fill="black", font=font)
    for col, label in enumerate(col_labels):
        draw.text((margin + col * col_width, title_height), label, fill="black", font=font)

    selections: list[dict[str, Any]] = []
    for row_index, (image_id, reason) in enumerate(zip(ids, labels, strict=True)):
        name, lr_tensor, hr_tensor = dataset[id_to_idx[image_id]]
        if name != image_id:
            raise ValueError("Dataset order changed while selecting visual cases")
        lr_u8 = np.floor(lr_tensor.squeeze(0).numpy() * 255.0 + 0.5).astype(np.uint8)
        hr_u8 = np.floor(hr_tensor.squeeze(0).numpy() * 255.0 + 0.5).astype(np.uint8)
        r0_u8 = r0_engine.run(lr_u8)["output"][:, :, 0]
        candidate_u8 = candidate_engine.run(lr_u8)["output"][:, :, 0]
        bicubic = F.interpolate(
            lr_tensor.unsqueeze(0), size=hr_tensor.shape[-2:], mode="bicubic", align_corners=False
        ).clamp(0.0, 1.0).squeeze().numpy()
        bicubic_u8 = np.floor(bicubic * 255.0 + 0.5).astype(np.uint8)

        hr_i16 = hr_u8.astype(np.int16)
        gradient = np.zeros_like(hr_i16, dtype=np.int64)
        gradient[:, 1:] += np.abs(hr_i16[:, 1:] - hr_i16[:, :-1])
        gradient[1:, :] += np.abs(hr_i16[1:, :] - hr_i16[:-1, :])
        integral = np.pad(gradient, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        sums = integral[crop_size:, crop_size:] - integral[:-crop_size, crop_size:] - integral[crop_size:, :-crop_size] + integral[:-crop_size, :-crop_size]
        cy, cx = np.unravel_index(int(np.argmax(sums)), sums.shape)
        y0 = max(0, min(int(cy), hr_u8.shape[0] - crop_size))
        x0 = max(0, min(int(cx), hr_u8.shape[1] - crop_size))
        arrays = [
            hr_u8,
            bicubic_u8,
            r0_u8,
            candidate_u8,
            np.minimum(np.abs(r0_u8.astype(np.int16) - hr_u8.astype(np.int16)) * 4, 255).astype(np.uint8),
            np.minimum(np.abs(candidate_u8.astype(np.int16) - hr_u8.astype(np.int16)) * 4, 255).astype(np.uint8),
        ]
        y_base = title_height + header_height + row_index * (row_label_height + tile_size + margin)
        score = row_by_id[image_id]
        caption = (
            f"{image_id} - {reason}; delta PSNR {float(score['candidate_integer_delta_vs_frozen_db']):+.4f} dB; "
            f"delta SSIM {float(score['candidate_integer_ssim']) - float(score['frozen_integer_ssim']):+.6f}"
        )
        draw.text((margin, y_base), caption, fill="black", font=font)
        for col, array in enumerate(arrays):
            crop = Image.fromarray(array[y0:y0 + crop_size, x0:x0 + crop_size], mode="L")
            crop = crop.resize((tile_size, tile_size), resample=Image.Resampling.NEAREST).convert("RGB")
            x = margin + col * col_width
            sheet.paste(crop, (x, y_base + row_label_height))
        selections.append({
            "image_id": image_id,
            "selection_reason": reason,
            "candidate_integer_delta_psnr_db": float(score["candidate_integer_delta_vs_frozen_db"]),
            "candidate_integer_delta_ssim": float(score["candidate_integer_ssim"]) - float(score["frozen_integer_ssim"]),
            "crop_xy": [x0, y0],
            "crop_wh": [crop_size, crop_size],
            "crop_selection": "highest local 192x192 HR gradient energy, to keep the comparison focused on visible structure",
        })
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_png, format="PNG", optimize=True)
    output_json.write_text(json.dumps({"selections": selections, "copyright_scope": "local ignored review artifact; do not redistribute DIV2K-derived image crops without confirming rights"}, indent=2), encoding="utf-8")
    return selections


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit official DIV2K EMA-v2 paired evaluation artifacts")
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--hr-dir", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--r0-quant", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--visual-dir", type=Path, default=None, help="Ignored local folder for DIV2K-derived review crops")
    args = parser.parse_args()

    evaluation_dir = args.evaluation_dir.resolve()
    project_root = args.project_root.resolve()
    candidate_dir = args.candidate_dir.resolve()
    r0_quant = (args.r0_quant or project_root / "artifacts/quant").resolve()
    rows = load_rows(evaluation_dir / "per_image_metrics.csv")
    source_summary = json.loads((evaluation_dir / "summary.json").read_text(encoding="utf-8"))
    candidate_checkpoint = candidate_dir / "training/candidate_ema_qat_fp32.pth"
    candidate_quant = candidate_dir / "quant"
    source_identity = verify_identity(
        rows=rows,
        source_summary=source_summary,
        dataset_manifest_path=args.dataset_manifest.resolve(),
        hr_dir=args.hr_dir.resolve(),
        frozen_checkpoint=project_root / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth",
        frozen_quant_params=r0_quant / "quant_params.json",
        candidate_checkpoint=candidate_checkpoint,
        candidate_quant_params=candidate_quant / "quant_params.json",
    )
    computed = summarize(rows)
    source_group = source_summary["groups"]["DIV2K_official_valid_100"]
    comparisons = {
        "candidate_integer_psnr_db": computed["candidate_integer_mean_psnr_db"],
        "frozen_integer_psnr_db": computed["frozen_integer_mean_psnr_db"],
        "candidate_integer_ssim": computed["candidate_integer_mean_ssim"],
        "frozen_integer_ssim": computed["frozen_integer_mean_ssim"],
        "candidate_integer_delta_vs_frozen_db": computed["paired_delta_psnr_db"]["mean"],
        "candidate_integer_delta_bootstrap_95pct_ci_db": computed["paired_delta_psnr_db"]["bootstrap_95pct_ci"],
    }
    for key, value in comparisons.items():
        original = source_group.get(key)
        if original is None or not np.allclose(np.asarray(value), np.asarray(original), rtol=0.0, atol=1e-10):
            raise ValueError(f"Per-image CSV does not reproduce source summary field {key}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "schema": "member-a-official-div2k-result-audit-v1",
        "status": "PASS_SOURCE_IDENTITY_AND_PER_IMAGE_SUMMARY_REPRODUCED",
        "source_summary_status": source_summary.get("status"),
        "source_csv_sha256": sha256_file(evaluation_dir / "per_image_metrics.csv"),
        "source_summary_sha256": sha256_file(evaluation_dir / "summary.json"),
        "identity": source_identity,
        "recomputed_metrics": computed,
        "interpretation": [
            "Paired software integer-reference result on DIV2K validation HR IDs 0801-0900 only.",
            "The bootstrap resamples images, not video sequences; the confidence interval is conditional on this image set and preprocessing.",
            "Pillow bicubic x2 degradation is not the official MATLAB-bicubic LR track.",
            "This audit is not subjective image-quality acceptance, RTL/FPGA evidence, or board-image evidence.",
        ],
    }
    (output_dir / "audit_summary.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.visual_dir:
        visual_dir = args.visual_dir.resolve()
        render_visual_review(
            rows=rows,
            hr_dir=args.hr_dir.resolve(),
            r0_quant=r0_quant,
            candidate_quant=candidate_quant,
            output_png=visual_dir / "ema_v2_r0_div2k_contact_sheet.png",
            output_json=visual_dir / "visual_selection.json",
            project_root=project_root,
        )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
