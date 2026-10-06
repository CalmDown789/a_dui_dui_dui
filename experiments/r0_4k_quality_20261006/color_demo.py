from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterator

import imageio_ffmpeg
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from experiments.r0_4k_quality_20261006.evaluate import (
    CLIPS,
    HEIGHT,
    SAMPLE_FPS,
    WIDTH,
    FixedReference,
    bicubic_baseline,
    integer_hybrid,
    make_lr,
    quant_tree_sha256,
    sha256_file,
    sha_array,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / ".data" / "r0_4k_quality_20261006" / "sources"
EVALUATION_DIR = ROOT / "results" / "r0_4k_quality_20261006"
OUTPUT_DIR = ROOT / "results" / "r0_color_demo_20261006"
CHROMA_WIDTH, CHROMA_HEIGHT = WIDTH // 2, HEIGHT // 2
LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT = 480, 270
PANEL_SIZE = (640, 360)
HEADER_HEIGHT = 36
OUTPUT_NAME = "demo_beauty_color_5s_10fps.mp4"


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_selected_yuv420(source: Path, indices: list[int], ffmpeg: str) -> Iterator[tuple[int, np.ndarray, np.ndarray, np.ndarray]]:
    if not indices or indices != sorted(set(indices)):
        raise ValueError("Frame indices must be non-empty, sorted, and unique")
    selector = "+".join(f"eq(n,{index})" for index in indices)
    video_filter = f"select='{selector}',scale=in_range=limited:out_range=pc,format=yuv420p"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", video_filter,
               "-fps_mode", "passthrough", "-frames:v", str(len(indices)), "-f", "rawvideo",
               "-pix_fmt", "yuv420p", "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None:
        raise RuntimeError("FFmpeg did not create a raw-video output stream")
    y_bytes = WIDTH * HEIGHT
    chroma_bytes = CHROMA_WIDTH * CHROMA_HEIGHT
    frame_bytes = y_bytes + 2 * chroma_bytes
    try:
        for index in indices:
            raw = process.stdout.read(frame_bytes)
            if len(raw) != frame_bytes:
                raise RuntimeError(f"FFmpeg emitted {len(raw)} bytes for frame {index}; expected {frame_bytes}")
            planes = np.frombuffer(raw, dtype=np.uint8)
            y = planes[:y_bytes].reshape(HEIGHT, WIDTH).copy()
            cb = planes[y_bytes:y_bytes + chroma_bytes].reshape(CHROMA_HEIGHT, CHROMA_WIDTH).copy()
            cr = planes[y_bytes + chroma_bytes:].reshape(CHROMA_HEIGHT, CHROMA_WIDTH).copy()
            yield index, y, cb, cr
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else b""
        status = process.wait(timeout=120)
        if status:
            raise RuntimeError(f"FFmpeg decode failed ({status}): {stderr.decode(errors='replace')[-2000:]}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stderr:
            process.stderr.close()


def resize_plane(plane: np.ndarray, width: int, height: int) -> np.ndarray:
    if plane.ndim != 2 or plane.dtype != np.uint8:
        raise ValueError("Expected a two-dimensional uint8 plane")
    return np.asarray(Image.fromarray(plane, mode="L").resize((width, height), Image.Resampling.BICUBIC),
                      dtype=np.uint8).copy()


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


def _rgb_thumb(y: np.ndarray, cb_native: np.ndarray, cr_native: np.ndarray) -> Image.Image:
    cb_full = resize_plane(cb_native, WIDTH, HEIGHT)
    cr_full = resize_plane(cr_native, WIDTH, HEIGHT)
    rgb = ycbcr709_full_to_rgb(y, cb_full, cr_full)
    return Image.fromarray(rgb, mode="RGB").resize(PANEL_SIZE, Image.Resampling.LANCZOS)


def _video_panel(reference: Image.Image, bicubic: Image.Image, hybrid: Image.Image) -> bytes:
    canvas = Image.new("RGB", (PANEL_SIZE[0] * 3, PANEL_SIZE[1] + HEADER_HEIGHT), "black")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=22)
    labels = ("Decoded 4K reference", "Bicubic x4 Y + CbCr", "R0 integer x4 Y + bicubic CbCr")
    for index, panel in enumerate((reference, bicubic, hybrid)):
        x = index * PANEL_SIZE[0]
        draw.text((x + 8, 7), labels[index], font=font, fill="white")
        canvas.paste(panel, (x, HEADER_HEIGHT))
    return canvas.tobytes()


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("The color demo contains no frames")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(source_dir: Path = SOURCE_DIR, evaluation_dir: Path = EVALUATION_DIR,
        output_dir: Path = OUTPUT_DIR, frame_count: int = 50) -> dict:
    if not 1 <= frame_count <= 50:
        raise ValueError("The color preview accepts 1..50 frames from the frozen Beauty sample")
    source_dir, evaluation_dir, output_dir = source_dir.resolve(), evaluation_dir.resolve(), output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite prior color-demo output: {output_dir}")
    eval_manifest = json.loads((evaluation_dir / "evaluation_manifest.json").read_text(encoding="utf-8"))
    source_record = next(record for record in eval_manifest["sources"] if record["sequence"] == "Beauty")
    source_path = source_dir / source_record["source_file"]
    if not source_path.is_file() or sha256_file(source_path) != source_record["sha256"]:
        raise ValueError(f"Beauty source is absent or differs from the evaluated source hash: {source_path}")
    clip = next(item for item in CLIPS if item.sequence == "Beauty")
    indices = list(clip.indices[:frame_count])
    metric_rows = {}
    with (evaluation_dir / "per_clip_frame_metrics.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["sequence"] == "Beauty" and int(row["decoded_frame_index"]) in indices:
                metric_rows[int(row["decoded_frame_index"])] = row
    if len(metric_rows) != frame_count:
        raise ValueError(f"Could not find {frame_count} matching luma records in the frozen evaluation")

    output_dir.mkdir(parents=True, exist_ok=False)
    video_path = output_dir / OUTPUT_NAME
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{PANEL_SIZE[0] * 3}x{PANEL_SIZE[1] + HEADER_HEIGHT}", "-r", str(SAMPLE_FPS), "-i", "pipe:0",
               "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
               "-movflags", "+faststart", str(video_path)]
    writer = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if writer.stdin is None:
        raise RuntimeError("FFmpeg did not create a video input stream")
    torch.set_num_threads(1)
    fixed = FixedReference(ROOT / "artifacts" / "quant")
    per_frame = []
    try:
        for frame_index, hr_y, source_cb, source_cr in read_selected_yuv420(source_path, indices, ffmpeg):
            expected = metric_rows[frame_index]
            if sha_array(hr_y) != expected["hr_y_sha256"]:
                raise ValueError(f"Y decode differs from evaluated reference at frame {frame_index}")
            lr_y = make_lr(hr_y)
            bicubic_y = bicubic_baseline(lr_y)
            hybrid_y = integer_hybrid(lr_y, fixed)
            if sha_array(lr_y) != expected["lr_y_sha256"]:
                raise ValueError(f"Synthetic low-resolution Y differs at frame {frame_index}")
            if sha_array(bicubic_y) != expected["bicubic_y_sha256"]:
                raise ValueError(f"Bicubic Y differs from evaluated output at frame {frame_index}")
            if sha_array(hybrid_y) != expected["hybrid_y_sha256"]:
                raise ValueError(f"Frozen integer Y differs from evaluated output at frame {frame_index}")

            # Simulate a 540p 4:2:0 input: reduce 4K chroma to 480x270, then
            # interpolate it to the 4K 4:2:0 output grid (1920x1080).
            cb_lr = resize_plane(source_cb, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT)
            cr_lr = resize_plane(source_cr, LR_CHROMA_WIDTH, LR_CHROMA_HEIGHT)
            cb_out = resize_plane(cb_lr, CHROMA_WIDTH, CHROMA_HEIGHT)
            cr_out = resize_plane(cr_lr, CHROMA_WIDTH, CHROMA_HEIGHT)
            reference_panel = _rgb_thumb(hr_y, source_cb, source_cr)
            bicubic_panel = _rgb_thumb(bicubic_y, cb_out, cr_out)
            hybrid_panel = _rgb_thumb(hybrid_y, cb_out, cr_out)
            writer.stdin.write(_video_panel(reference_panel, bicubic_panel, hybrid_panel))
            per_frame.append({
                "decoded_frame_index": frame_index,
                "timestamp_seconds": frame_index / 120,
                "source_y_sha256": sha_array(hr_y),
                "source_cb_sha256": sha_array(source_cb),
                "source_cr_sha256": sha_array(source_cr),
                "lr_y_sha256": sha_array(lr_y),
                "bicubic_y_sha256": sha_array(bicubic_y),
                "hybrid_y_sha256": sha_array(hybrid_y),
                "lr_cbcr_sha256": _sha256_bytes(cb_lr.tobytes() + cr_lr.tobytes()),
                "output_cbcr_sha256": _sha256_bytes(cb_out.tobytes() + cr_out.tobytes()),
                "y_matches_frozen_quality_evaluation": True,
            })
        writer.stdin.close()
        stderr = writer.stderr.read() if writer.stderr else b""
        status = writer.wait()
        if status:
            raise RuntimeError(f"FFmpeg color-demo encoding failed ({status}): {stderr.decode(errors='replace')[-2000:]}")
    finally:
        if writer.poll() is None:
            writer.kill()
            writer.wait()
        if writer.stderr:
            writer.stderr.close()

    _write_csv(output_dir / "per_frame_color_hashes.csv", per_frame)
    manifest = {
        "schema": "member-a-r0-color-video-demo-v1",
        "status": "SOFTWARE_COLOR_DEMO_NOT_BOARD_VALIDATION",
        "dataset": eval_manifest["dataset"],
        "source": {"sequence": "Beauty", "source_file": source_path.name,
                   "source_url": source_record["source_url"], "sha256": source_record["sha256"],
                   "license": eval_manifest["dataset"]["license"]},
        "model": eval_manifest["model"],
        "color_path": {
            "input": "synthetic 960x540 Y with 480x270 Cb/Cr, software-only",
            "y": "frozen R0 INT8/INT16/INT32 FSRCNN x2 followed by frozen Q14 Keys bicubic x2; per-frame hashes equal the prior 4K quality evaluation",
            "cbcr": "source 4K 4:2:0 Cb/Cr downsampled to 480x270 with Pillow BICUBIC and enlarged to the 4K 4:2:0 chroma grid 1920x1080 with Pillow BICUBIC; same chroma path for baseline and R0",
            "display_conversion": "full-range YCbCr to RGB using fixed-point BT.709 coefficients; panels resized to 640x360",
            "baseline": "direct Pillow BICUBIC x4 for Y and the same interpolated Cb/Cr path",
            "reference_panel": "decoded 4K Y with decoded 4K Cb/Cr for visual context; not a quality score",
        },
        "video": {"file": video_path.name, "bytes": video_path.stat().st_size,
                  "sha256": sha256_file(video_path), "width": PANEL_SIZE[0] * 3,
                  "height": PANEL_SIZE[1] + HEADER_HEIGHT, "fps": SAMPLE_FPS,
                  "frame_count": len(per_frame), "duration_seconds": len(per_frame) / SAMPLE_FPS,
                  "codec": "H.264, yuv420p, BT.709 tags, no audio"},
        "per_frame_hashes": "per_frame_color_hashes.csv",
        "quant_asset_tree_sha256": quant_tree_sha256(ROOT / "artifacts" / "quant"),
        "limitations": [
            "The side-by-side video is a software preview, not a full-resolution color-quality measurement.",
            "The current FPGA model enhances Y only; Cb/Cr interpolation is a software placeholder and is not verified on board.",
            "UVG source is CC BY-NC and may only be used non-commercially; the raw source is not included in this repository.",
        ],
    }
    (output_dir / "color_demo_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a color preview using frozen R0 luma and interpolated chroma")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--evaluation-dir", type=Path, default=EVALUATION_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--frame-count", type=int, default=50, help="Use 1..50 frames from the frozen Beauty clip")
    args = parser.parse_args()
    manifest = run(args.source_dir, args.evaluation_dir, args.output_dir, args.frame_count)
    print(json.dumps({"status": manifest["status"], "video": str((args.output_dir / OUTPUT_NAME).resolve()),
                      "frames": manifest["video"]["frame_count"], "duration_seconds": manifest["video"]["duration_seconds"],
                      "sha256": manifest["video"]["sha256"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
