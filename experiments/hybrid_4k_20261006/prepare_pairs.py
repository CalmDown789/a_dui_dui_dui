from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


IMAGE_SUFFIXES = {".png", ".tif", ".tiff", ".bmp", ".jpg", ".jpeg"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_pair(path: Path, output_path: Path) -> dict[str, object]:
    with Image.open(path) as source:
        width, height = source.size
        if width < 3840 or height < 2160:
            raise ValueError(f"{path.name}: source is {width}x{height}; requires at least 3840x2160")
        left = (width - 3840) // 2
        top = (height - 2160) // 2
        crop = source.crop((left, top, left + 3840, top + 2160))
        if source.mode == "L":
            y_image = crop
            channel_conversion = "source already grayscale Y8; no additional color conversion"
        else:
            y_image = crop.convert("RGB").convert("YCbCr").getchannel("Y")
            channel_conversion = "Pillow RGB to YCbCr Y, 8-bit"
        hr_y = np.asarray(y_image, dtype=np.uint8).copy()
        lr_image = y_image.resize((960, 540), resample=Image.Resampling.BICUBIC, reducing_gap=None)
        lr_y = np.asarray(lr_image, dtype=np.uint8).copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output_path, hr_y=hr_y, lr_y=lr_y)
    return {
        "source_file": path.name,
        "source_sha256": sha256_file(path),
        "source_width": width,
        "source_height": height,
        "center_crop_xywh": [left, top, 3840, 2160],
        "channel_conversion": channel_conversion,
        "hr_y_shape": list(hr_y.shape),
        "hr_y_sha256": hashlib.sha256(hr_y.tobytes()).hexdigest(),
        "lr_y_shape": list(lr_y.shape),
        "lr_y_sha256": hashlib.sha256(lr_y.tobytes()).hexdigest(),
        "pair_file": output_path.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare reproducible 4K-HR/540p-LR Y-channel pairs")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--max-images", type=int, default=0, help="0 means all images")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Prepared image pairs must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    sources = sorted(path for path in args.source_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if args.max_images > 0:
        sources = sources[: args.max_images]
    if not sources:
        raise FileNotFoundError(f"No supported images found under {args.source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    records = [make_pair(path, output_dir / f"{path.stem}.npz") for path in sources]
    manifest = {
        "schema": "member-a-hybrid-4k-pair-manifest-v1",
        "status": "PREPARED_SYNTHETIC_SCALE4_EVALUATION_PAIRS",
        "source": {"name": args.source_name, "url": args.source_url, "license": args.license},
        "protocol": {
            "target_hr": "3840x2160",
            "input_lr": "960x540",
            "channel": "Pillow RGB-to-Y (YCbCr Y)",
            "crop": "center crop to 3840x2160; no upscaling",
            "lr_generation": "Pillow Image.Resampling.BICUBIC; reducing_gap=None; resize x4",
            "metrics": "Y PSNR/SSIM at final 4K; crop border 8 pixels",
        },
        "count": len(records),
        "pairs": records,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "count": len(records), "manifest": str(output_dir / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
