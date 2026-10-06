from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image


WIDTH = 3840
HEIGHT = 2160
DATASET_PAGE = "https://ultravideo.fi/dataset.html"
SEQUENCE_URLS = {
    "Beauty": "https://ultravideo.fi/video/Beauty_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "Bosphorus": "https://ultravideo.fi/video/Bosphorus_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "HoneyBee": "https://ultravideo.fi/video/HoneyBee_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "Jockey": "https://ultravideo.fi/video/Jockey_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "ReadySetGo": "https://ultravideo.fi/video/ReadySetGo_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "ShakeNDry": "https://ultravideo.fi/video/ShakeNDry_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
    "YachtRide": "https://ultravideo.fi/video/YachtRide_3840x2160_120fps_420_8bit_HEVC_RAW.hevc",
}


def selected_source_indices(frame_stride: int, frame_offset: int, count: int) -> list[int]:
    if frame_stride <= 0 or count < 0:
        raise ValueError("frame-stride must be positive and count must be non-negative")
    if frame_offset < 0 or frame_offset >= frame_stride:
        raise ValueError("frame-offset must be in [0, frame-stride)")
    return [frame_offset + index * frame_stride for index in range(count)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract selected 4K luma frames from UVG HEVC sequence files")
    parser.add_argument("--sequence", choices=SEQUENCE_URLS, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frame-stride", type=int, default=60, help="decoded frame index stride; not a PTS interval")
    parser.add_argument("--frame-offset", type=int, default=0, help="decoded frame index offset within each stride")
    parser.add_argument("--max-frames", type=int, default=10)
    args = parser.parse_args()
    if args.frame_stride <= 0 or args.max_frames <= 0:
        raise ValueError("frame-stride and max-frames must be positive")
    if args.frame_offset < 0 or args.frame_offset >= args.frame_stride:
        raise ValueError("frame-offset must be in [0, frame-stride)")

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Extracted source frames must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    if not args.video.is_file():
        raise FileNotFoundError(args.video)

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Install imageio-ffmpeg into the ignored experiment runtime before decoding") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pattern = output_dir / "frame_%03d.png"
    select_expr = (
        f"select='gte(n,{args.frame_offset})*not(mod(n-{args.frame_offset},{args.frame_stride}))',"
        "scale=out_range=pc,format=gray"
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(args.video.resolve()),
        "-vf",
        select_expr,
        "-fps_mode",
        "vfr",
        "-frames:v",
        str(args.max_frames),
        "-start_number",
        "0",
        str(pattern),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(f"FFmpeg failed ({completed.returncode}): {completed.stderr.strip()}")

    files = sorted(output_dir.glob("frame_*.png"))
    if not files:
        raise RuntimeError("Decoder produced no frames")
    records: list[dict[str, object]] = []
    source_indices = selected_source_indices(args.frame_stride, args.frame_offset, len(files))
    for index, path in enumerate(files):
        with Image.open(path) as image:
            if image.size != (WIDTH, HEIGHT):
                raise ValueError(f"Unexpected image size {image.size} in {path.name}")
            if image.mode != "L":
                raise ValueError(f"Expected extracted 8-bit luma, got {image.mode}")
            luma_hash = hashlib.sha256(image.tobytes()).hexdigest()
        source_index = source_indices[index]
        records.append(
            {
                "frame_file": path.name,
                "decoded_frame_index": source_index,
                "assumed_interval_seconds_from_uvg_120fps_metadata": source_index / 120.0,
                "shape": [HEIGHT, WIDTH],
                "luma_sha256": luma_hash,
            }
        )

    manifest = {
        "schema": "member-a-uvg-4k-hevc-frame-source-v1",
        "status": "LICENSED_DECODED_HEVC_REFERENCE_FRAMES_NOT_CAMERA_RAW",
        "dataset": f"UVG {args.sequence} 4K 3840x2160 8-bit 4:2:0 HEVC sequence",
        "dataset_url": DATASET_PAGE,
        "sequence_url": SEQUENCE_URLS[args.sequence],
        "license": "Creative Commons BY-NC; non-commercial academic use only; cite Mercat et al., ACM MMSys 2020",
        "local_video": str(args.video.resolve()),
        "video_bytes": args.video.stat().st_size,
        "video_sha256": sha256_file(args.video),
        "decoder": {"ffmpeg": Path(ffmpeg).name, "version": imageio_ffmpeg.get_ffmpeg_version()},
        "pixel_handling": "HEVC decoded; scale filter expands limited-range Y to full range; grayscale PNG is Y only",
        "selection": {
            "method": "decoded frame index stride; elementary stream has no reliable timestamps",
            "frame_stride": args.frame_stride,
            "frame_offset": args.frame_offset,
            "uvg_source_metadata_fps": 120,
            "max_frames_requested": args.max_frames,
        },
        "frames": records,
        "limitations": [
            "The HEVC source is lossy; use for an initial paired 4K software benchmark only, not pristine sensor-ground-truth claims.",
            "All decoded frames are from one sequence and must not be split across train/validation/test groups.",
            "These 8-bit luma frames are not proof of a color or FPGA output path.",
        ],
    }
    (output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"frames": len(files), "output_dir": str(output_dir), "manifest": str(output_dir / "source_manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
