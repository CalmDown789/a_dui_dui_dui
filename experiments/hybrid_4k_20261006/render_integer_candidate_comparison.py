from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .bicubic_reference import resize_keys_u8
from .hybrid_reference import run_bicubic4x_u8
from .quantize_candidate_eval import _metrics_border
from member_a.fixed_reference import FixedReference


def _panel(image: np.ndarray, size: tuple[int, int], crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    rendered = Image.fromarray(image, mode="L")
    if crop is not None:
        rendered = rendered.crop(crop)
    if rendered.size != size:
        rendered = rendered.resize(size, Image.Resampling.LANCZOS)
    return rendered


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render paired full-frame/detail comparison for one integer candidate")
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--quant-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crop-x", type=int, default=-1)
    parser.add_argument("--crop-y", type=int, default=-1)
    parser.add_argument("--crop-width", type=int, default=960)
    parser.add_argument("--crop-height", type=int, default=540)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Rendered image outputs must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    if not (args.quant_dir / "quant_params.json").is_file():
        raise FileNotFoundError(f"Candidate quantization package not found: {args.quant_dir}")

    with np.load(args.pair, allow_pickle=False) as pair:
        hr_y = pair["hr_y"].copy()
        lr_y = pair["lr_y"].copy()
    if hr_y.shape != (2160, 3840) or lr_y.shape != (540, 960):
        raise ValueError(f"Expected 4K/540p pair, got {hr_y.shape}/{lr_y.shape}")

    stages = FixedReference(args.quant_dir).run(lr_y)
    integer_mid = stages["output"][:, :, 0]
    integer = resize_keys_u8(integer_mid, scale=2, a=-0.5)
    bicubic = run_bicubic4x_u8(lr_y, keys_a=-0.5)
    if integer.shape != hr_y.shape or bicubic.shape != hr_y.shape:
        raise ValueError("Output shape does not match the 4K reference")

    crop_w = min(args.crop_width, hr_y.shape[1])
    crop_h = min(args.crop_height, hr_y.shape[0])
    crop_x = args.crop_x if args.crop_x >= 0 else (hr_y.shape[1] - crop_w) // 2
    crop_y = args.crop_y if args.crop_y >= 0 else (hr_y.shape[0] - crop_h) // 2
    if crop_x + crop_w > hr_y.shape[1] or crop_y + crop_h > hr_y.shape[0]:
        raise ValueError("Detail crop lies outside the reference frame")
    crop_box = (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)
    diff = np.minimum(np.abs(integer.astype(np.int16) - hr_y.astype(np.int16)) * 4, 255).astype(np.uint8)

    labels = [
        ("Decoded 4K reference Y", hr_y),
        ("Bicubic x4", bicubic),
        ("Integer FSRCNN x2 + bicubic x2", integer),
        ("4x amplified absolute error", diff),
    ]
    overview_size = (960, 540)
    label_h = 34
    row_h = overview_size[1] + label_h
    canvas = Image.new("L", (overview_size[0] * 4, row_h * 2), color=24)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    for index, (label, values) in enumerate(labels):
        x = index * overview_size[0]
        draw.text((x + 8, 6), label, fill=255, font=font)
        canvas.paste(_panel(values, overview_size), (x, label_h))
        draw.text((x + 8, row_h + 6), f"Detail x={crop_x}, y={crop_y}, {crop_w}x{crop_h}", fill=255, font=font)
        canvas.paste(_panel(values, overview_size, crop=crop_box), (x, row_h + label_h))

    output_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = output_dir / "integer_comparison.png"
    canvas.save(sheet_path, optimize=True)
    reference_path = output_dir / "reference_4k_y.png"
    bicubic_path = output_dir / "bicubic4x_4k_y.png"
    integer_path = output_dir / "integer_hybrid_4k_y.png"
    Image.fromarray(hr_y, mode="L").save(reference_path, optimize=True)
    Image.fromarray(bicubic, mode="L").save(bicubic_path, optimize=True)
    Image.fromarray(integer, mode="L").save(integer_path, optimize=True)

    summary = {
        "schema": "member-a-integer-candidate-visual-comparison-v1",
        "status": "SOFTWARE_INTEGER_REFERENCE_ONLY_NOT_RTL_OR_BOARD",
        "pair": str(args.pair.resolve()),
        "pair_sha256": _sha256(args.pair.read_bytes()),
        "quant_params_sha256": _sha256((args.quant_dir / "quant_params.json").read_bytes()),
        "crop_xywh": [crop_x, crop_y, crop_w, crop_h],
        "metrics": {
            "integer_shave8": dict(zip(("psnr_db", "ssim"), _metrics_border(hr_y, integer, border=8), strict=True)),
            "bicubic_shave8": dict(zip(("psnr_db", "ssim"), _metrics_border(hr_y, bicubic, border=8), strict=True)),
            "integer_full": dict(zip(("psnr_db", "ssim"), _metrics_border(hr_y, integer, border=0), strict=True)),
            "bicubic_full": dict(zip(("psnr_db", "ssim"), _metrics_border(hr_y, bicubic, border=0), strict=True)),
        },
        "outputs": {
            "contact_sheet": str(sheet_path),
            "reference": str(reference_path),
            "bicubic": str(bicubic_path),
            "integer_hybrid": str(integer_path),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["metrics"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
