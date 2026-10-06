from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

from .candidate_models import HybridFSRCNN, PRESETS
from .hybrid_reference import run_bicubic4x_u8, run_hybrid_float_u8


def _panel(image: np.ndarray, size: tuple[int, int], *, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    rendered = Image.fromarray(image, mode="L")
    if crop is not None:
        rendered = rendered.crop(crop)
    return rendered.resize(size, Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a full-frame and detail contact sheet for one 4K hybrid sample")
    parser.add_argument("--pair", type=Path, required=True, help="One prepared .npz pair containing hr_y and lr_y")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--variant", choices=tuple(PRESETS), required=True)
    parser.add_argument("--keys-a", type=float, choices=(-0.5, -0.75), default=-0.5)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crop-x", type=int, default=-1)
    parser.add_argument("--crop-y", type=int, default=-1)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Rendered image outputs must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")

    with np.load(args.pair, allow_pickle=False) as pair:
        hr_y = pair["hr_y"]
        lr_y = pair["lr_y"]
    model = HybridFSRCNN(PRESETS[args.variant])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint.get("state_dict", checkpoint), strict=True)
    model.eval()
    middle, hybrid = run_hybrid_float_u8(model, lr_y, keys_a=args.keys_a, device="cuda:0" if torch.cuda.is_available() else "cpu")
    del middle
    bicubic = run_bicubic4x_u8(lr_y, keys_a=args.keys_a)
    difference = np.minimum(np.abs(hybrid.astype(np.int16) - hr_y.astype(np.int16)) * 4, 255).astype(np.uint8)

    width, height = hr_y.shape[1], hr_y.shape[0]
    crop_w, crop_h = min(960, width), min(540, height)
    crop_x = args.crop_x if args.crop_x >= 0 else (width - crop_w) // 2
    crop_y = args.crop_y if args.crop_y >= 0 else (height - crop_h) // 2
    if crop_x + crop_w > width or crop_y + crop_h > height:
        raise ValueError("Detail crop lies outside the reference frame")
    crop_box = (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)

    overview_size = (960, 540)
    detail_size = (960, 540)
    items = [
        ("Reference (decoded HEVC Y)", hr_y),
        ("Bicubic x4", bicubic),
        (f"{args.variant} + bicubic x2", hybrid),
        ("4x amplified abs error", difference),
    ]
    label_h = 34
    row_h = overview_size[1] + label_h
    canvas = Image.new("L", (overview_size[0] * len(items), row_h * 2), color=24)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    for column, (label, image) in enumerate(items):
        x = column * overview_size[0]
        draw.text((x + 8, 6), label, fill=255, font=font)
        canvas.paste(_panel(image, overview_size), (x, label_h))
        draw.text((x + 8, row_h + 6), f"Detail crop x={crop_x}, y={crop_y}", fill=255, font=font)
        canvas.paste(_panel(image, detail_size, crop=crop_box), (x, row_h + label_h))
    output_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(output_dir / "comparison.png", optimize=True)
    Image.fromarray(hr_y, mode="L").save(output_dir / "reference_4k.png", optimize=True)
    Image.fromarray(bicubic, mode="L").save(output_dir / "bicubic4x_4k.png", optimize=True)
    Image.fromarray(hybrid, mode="L").save(output_dir / "hybrid_4k.png", optimize=True)
    print(f"Rendered comparison into {output_dir}")


if __name__ == "__main__":
    main()
