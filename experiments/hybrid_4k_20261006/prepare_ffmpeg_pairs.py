from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from .extract_uvg_hevc_frames import sha256_file


def _scale_gray_frame(ffmpeg: str, source: Path) -> np.ndarray:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source.resolve()),
        "-vf",
        "scale=960:540:flags=bicubic:in_range=pc:out_range=pc,format=gray",
        "-frames:v",
        "1",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "-",
    ]
    completed = subprocess.run(command, check=False, capture_output=True)
    if completed.returncode:
        raise RuntimeError(f"FFmpeg failed for {source.name}: {completed.stderr.decode(errors='replace').strip()}")
    expected = 960 * 540
    if len(completed.stdout) != expected:
        raise RuntimeError(f"Expected {expected} downscaled bytes, received {len(completed.stdout)} for {source.name}")
    return np.frombuffer(completed.stdout, dtype=np.uint8).reshape(540, 960).copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare full-range luma pairs with FFmpeg bicubic x4 degradation")
    parser.add_argument("--source-dir", type=Path, required=True, help="Directory of decoded 3840x2160 grayscale PNG frames")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory under ignored .data/")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--max-images", type=int, default=0)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Prepared pairs must remain under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    sources = sorted(args.source_dir.glob("*.png"))
    if args.max_images > 0:
        sources = sources[: args.max_images]
    if not sources:
        raise FileNotFoundError(f"No PNG frames found in {args.source_dir}")

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required in the experiment runtime") from exc
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for source in sources:
        with Image.open(source) as image:
            if image.size != (3840, 2160):
                raise ValueError(f"Expected 3840x2160 source, got {image.size} in {source.name}")
            hr_y = np.asarray(image.convert("L"), dtype=np.uint8).copy()
        lr_y = _scale_gray_frame(ffmpeg, source)
        pair_path = output_dir / f"{source.stem}.npz"
        np.savez_compressed(pair_path, hr_y=hr_y, lr_y=lr_y)
        records.append(
            {
                "source_file": source.name,
                "source_sha256": sha256_file(source),
                "hr_y_shape": list(hr_y.shape),
                "hr_y_sha256": hashlib.sha256(hr_y.tobytes()).hexdigest(),
                "lr_y_shape": list(lr_y.shape),
                "lr_y_sha256": hashlib.sha256(lr_y.tobytes()).hexdigest(),
                "pair_file": pair_path.name,
            }
        )
        print(json.dumps({"frame": source.name, "pairs_done": len(records), "total": len(sources)}), flush=True)

    manifest = {
        "schema": "member-a-hybrid-4k-ffmpeg-pair-manifest-v1",
        "status": "EXPERIMENTAL_FFMPEG_BICUBIC_SYNTHETIC_PAIRS",
        "source": {"name": args.source_name, "url": args.source_url, "license": args.license},
        "decoder": {"ffmpeg": Path(ffmpeg).name, "version": imageio_ffmpeg.get_ffmpeg_version()},
        "protocol": {
            "target_hr": "3840x2160 Y8",
            "input_lr": "960x540 Y8",
            "crop": "none; decoded full-resolution frame is the reference",
            "lr_generation": "FFmpeg scale bicubic flags; full-range PNG Y8 to full-range Y8; x4",
            "metrics": "Hybrid 4K Y PSNR/SSIM; border 8 pixels",
        },
        "count": len(records),
        "pairs": records,
        "limitations": [
            "The source is lossy UVG HEVC decoded luma, not camera-original ground truth.",
            "The synthetic degradation is FFmpeg scale from full-resolution Y8, not native 540p capture or a YUV420 camera pipeline.",
            "Software candidate evaluation only; no integer deployment or FPGA evidence.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "count": len(records), "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
