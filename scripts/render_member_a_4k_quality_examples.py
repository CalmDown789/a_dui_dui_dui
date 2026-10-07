"""Render least-gain paired examples for visual review of the A software results."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference
from member_a.model import FSRCNNSubpixel, ModelConfig
from member_a.pc_postprocess_4k import resize_keys_u8


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uint8_prediction(tensor: torch.Tensor) -> np.ndarray:
    values = tensor.detach().to(device="cpu", dtype=torch.float64).numpy().squeeze() * 255.0
    rounded = np.copysign(np.floor(np.abs(values) + 0.5), values)
    return np.clip(rounded, 0, 255).astype(np.uint8)


def max_error_crop(reference: np.ndarray, candidate: np.ndarray, size: int = 256) -> tuple[int, int, int]:
    error = np.abs(reference.astype(np.int16) - candidate.astype(np.int16)).astype(np.int64)
    integral = np.pad(error, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    height, width = reference.shape
    step = 64
    ys = sorted(set(range(0, height - size + 1, step)) | {height - size})
    xs = sorted(set(range(0, width - size + 1, step)) | {width - size})
    best: tuple[int, int, int] = (-1, 0, 0)
    for y in ys:
        y2 = y + size
        for x in xs:
            x2 = x + size
            score = int(integral[y2, x2] - integral[y, x2] - integral[y2, x] + integral[y, x])
            if score > best[0]:
                best = (score, x, y)
    return best[1], best[2], size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth")
    parser.add_argument("--quant-dir", type=Path, default=ROOT / "artifacts/quant")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    evaluation = args.evaluation_dir.resolve()
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Refusing to overwrite {out}")
    device_name = args.device
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but not available")
    device = torch.device(device_name)
    torch.set_num_threads(4)

    per_frame = list(csv.DictReader((evaluation / "per_frame.csv").open(encoding="utf-8", newline="")))
    selected: list[dict[str, str]] = []
    for sequence in sorted({row["sequence"] for row in per_frame}):
        rows = [row for row in per_frame if row["sequence"] == sequence]
        least_gain = min(rows, key=lambda row: float(row["r0_int_y_psnr_db"]) - float(row["bicubic_y_psnr_db"]))
        selected.append(least_gain)
    pair_manifests = {path.resolve().name: json.loads((path.resolve() / "manifest.json").read_text(encoding="utf-8"))
                      for path in args.pairs_dir}
    pair_dirs = {path.resolve().name: path.resolve() for path in args.pairs_dir}

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model = FSRCNNSubpixel(ModelConfig())
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    fixed = FixedReference(args.quant_dir)

    labels = ("Decoded 4K reference", "Direct bicubic x4", "Frozen R0 FP32", "Frozen R0 integer")
    tile_w, tile_h, scale, margin, title_h = 256, 256, 2, 16, 48
    canvas = Image.new("RGB", (margin + 4 * (tile_w * scale + margin),
                                margin + len(selected) * (tile_h * scale + title_h + margin)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=20)
    report_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(selected):
        sequence = row["sequence"]
        record = next(item for item in pair_manifests[sequence]["pairs"]
                      if item["source_file"] == row["source_file"])
        with np.load(pair_dirs[sequence] / record["pair_file"], allow_pickle=False) as pair:
            lr, hr = pair["lr_y"].copy(), pair["hr_y"].copy()
        cubic = resize_keys_u8(lr, scale=4)
        input_tensor = torch.from_numpy(lr.copy()).to(device=device, dtype=torch.float32)[None, None] / 255.0
        with torch.inference_mode():
            float_mid = uint8_prediction(model(input_tensor))
        int_mid = None
        for layer_name, values in fixed.iter_outputs(lr):
            if layer_name == "output":
                int_mid = values[:, :, 0].copy()
        if int_mid is None:
            raise RuntimeError(f"Integer reference omitted {row['frame_id']}")
        outputs = [hr, cubic, resize_keys_u8(float_mid), resize_keys_u8(int_mid)]
        x, y, size = max_error_crop(hr, outputs[-1])
        top = margin + row_index * (tile_h * scale + title_h + margin)
        draw.text((margin, top), f"{row['frame_id']}  least integer gain vs bicubic", fill="black", font=font)
        for col, (pixels, label) in enumerate(zip(outputs, labels, strict=True)):
            left = margin + col * (tile_w * scale + margin)
            draw.text((left, top + 25), label, fill="black", font=font)
            tile = Image.fromarray(pixels[y:y + size, x:x + size], mode="L").resize(
                (tile_w * scale, tile_h * scale), Image.Resampling.NEAREST
            ).convert("RGB")
            canvas.paste(tile, (left, top + title_h))
        report_rows.append({
            "frame_id": row["frame_id"],
            "source_file": row["source_file"],
            "crop_xywh": [x, y, size, size],
            "selection": "least integer PSNR gain over bicubic among this sequence's evaluated frames",
            "r0_int_psnr_db": float(row["r0_int_y_psnr_db"]),
            "bicubic_psnr_db": float(row["bicubic_y_psnr_db"]),
            "integer_gain_db": float(row["r0_int_y_psnr_db"]) - float(row["bicubic_y_psnr_db"]),
            "r0_fp32_psnr_db": float(row["r0_fp32_y_psnr_db"]),
            "int_vs_fp32_delta_db": float(row["r0_int_y_psnr_db"]) - float(row["r0_fp32_y_psnr_db"]),
        })

    out.mkdir(parents=True, exist_ok=True)
    image_path = out / "quality_examples.png"
    canvas.save(image_path, format="PNG", optimize=True)
    report = {
        "schema": "member-a-4k-quality-visual-examples-v1",
        "status": "PC_SOFTWARE_VISUAL_COMPARISON_NOT_BOARD_CAPTURE",
        "evaluation_summary_sha256": sha256(evaluation / "summary.json"),
        "checkpoint_sha256": sha256(args.checkpoint),
        "quant_params_sha256": sha256(args.quant_dir / "quant_params.json"),
        "metric_scope": "The shown image is a crop selected around the maximum local absolute error of the integer output against the decoded 4K reference. Rows are chosen for the smallest integer PSNR gain over bicubic per sequence.",
        "columns": list(labels),
        "frames": report_rows,
        "image": image_path.name,
        "image_sha256": sha256(image_path),
    }
    report_path = out / "quality_examples.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"image": str(image_path), "report": str(report_path), "frames": len(report_rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
