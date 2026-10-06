from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

from .bicubic_reference import resize_keys_u8
from .candidate_models import HybridFSRCNN, PRESETS
from .evaluate_hybrid import _metrics
from .extract_uvg_hevc_frames import selected_source_indices, sha256_file
from .hybrid_reference import run_bicubic4x_u8, run_hybrid_float_u8
from member_a.fixed_reference import FixedReference


WIDTH, HEIGHT = 960, 540
OUTPUT_WIDTH, OUTPUT_HEIGHT = 3840, 2160
DATASET_URL = "https://tie-ultravideo.rd.tuni.fi/dataset.html"
LICENSE = "CC BY-NC; non-commercial academic use; cite Mercat et al., ACM MMSys 2020"


def yuv420_frame_bytes(width: int, height: int) -> int:
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("YUV420 dimensions must be positive even numbers")
    return width * height * 3 // 2


def selected_raw_source_indices(frame_start: int, frame_stride: int, count: int) -> list[int]:
    """Return absolute source indices for a raw-YUV segment and its sampling stride."""
    if frame_start < 0 or frame_stride <= 0 or count <= 0:
        raise ValueError("frame-start must be non-negative; frame-stride and count must be positive")
    return [frame_start + ordinal * frame_stride for ordinal in range(count)]


def unpack_yuv420_frame(data: bytes, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    expected = yuv420_frame_bytes(width, height)
    if len(data) != expected:
        raise ValueError(f"Expected {expected} bytes for {width}x{height} YUV420, got {len(data)}")
    y_bytes = width * height
    chroma_bytes = (width // 2) * (height // 2)
    y = np.frombuffer(data[:y_bytes], dtype=np.uint8).reshape(height, width).copy()
    cb = np.frombuffer(data[y_bytes : y_bytes + chroma_bytes], dtype=np.uint8).reshape(height // 2, width // 2).copy()
    cr = np.frombuffer(data[y_bytes + chroma_bytes :], dtype=np.uint8).reshape(height // 2, width // 2).copy()
    return y, cb, cr


def pack_yuv420_frame(y: np.ndarray, cb: np.ndarray, cr: np.ndarray) -> bytes:
    if y.ndim != 2 or y.dtype != np.uint8 or y.shape[0] % 2 or y.shape[1] % 2:
        raise ValueError("Y must be an even-sized 2D uint8 plane")
    expected_chroma_shape = (y.shape[0] // 2, y.shape[1] // 2)
    if cb.shape != expected_chroma_shape or cr.shape != expected_chroma_shape:
        raise ValueError(f"Cb/Cr planes must have shape {expected_chroma_shape}")
    if cb.dtype != np.uint8 or cr.dtype != np.uint8:
        raise ValueError("Cb/Cr must be uint8")
    return y.tobytes(order="C") + cb.tobytes(order="C") + cr.tobytes(order="C")


def run_hybrid_integer_u8(fixed: FixedReference, lr_y_u8: np.ndarray, *, keys_a: float) -> tuple[np.ndarray, np.ndarray]:
    """Run quantized FSRCNN x2 followed by Keys bicubic x2 in the exact A integer reference."""
    lr = np.asarray(lr_y_u8)
    if lr.dtype != np.uint8 or lr.ndim != 2:
        raise ValueError("LR input must be a 2D uint8 Y plane")
    stages = fixed.run(lr)
    intermediate = stages["output"][:, :, 0]
    expected_shape = (lr.shape[0] * 2, lr.shape[1] * 2)
    if intermediate.shape != expected_shape or intermediate.dtype != np.uint8:
        raise ValueError(f"Integer CNN output must be uint8 {expected_shape}, got {intermediate.shape} {intermediate.dtype}")
    final = resize_keys_u8(intermediate, scale=2, a=keys_a)
    return intermediate, final


def _decode_selected_yuv420(
    ffmpeg: str,
    video: Path,
    output: Path,
    *,
    width: int,
    height: int,
    count: int,
    stride: int,
    offset: int,
    scale: bool,
) -> None:
    expression = f"gte(n,{offset})*not(mod(n-{offset},{stride}))"
    if scale:
        scale_filter = f"scale={width}:{height}:flags=bicubic:in_range=tv:out_range=pc,"
    else:
        scale_filter = f"scale={width}:{height}:flags=bicubic:in_range=tv:out_range=pc,"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video.resolve()),
        "-vf",
        f"select='{expression}',{scale_filter}format=yuv420p",
        "-fps_mode",
        "vfr",
        "-frames:v",
        str(count),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "rawvideo",
        str(output),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(f"FFmpeg decode failed: {completed.stderr.strip()}")
    expected_size = count * yuv420_frame_bytes(width, height)
    actual_size = output.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(f"Expected {count} decoded frames ({expected_size} bytes), got {actual_size} bytes")


def _decode_selected_raw_yuv420(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    width: int,
    height: int,
    source_fps: float,
    count: int,
    stride: int,
    offset: int,
    scale: bool,
) -> None:
    expression = f"gte(n,{offset})*not(mod(n-{offset},{stride}))"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "yuv420p",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        f"{source_fps:.8g}",
        "-i",
        str(source.resolve()),
        "-vf",
        f"select='{expression}',scale={WIDTH if scale else OUTPUT_WIDTH}:{HEIGHT if scale else OUTPUT_HEIGHT}:flags=bicubic:in_range=tv:out_range=pc,format=yuv420p",
        "-fps_mode",
        "vfr",
        "-frames:v",
        str(count),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "rawvideo",
        str(output),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(f"FFmpeg raw YUV decode failed: {completed.stderr.strip()}")
    expected_size = count * yuv420_frame_bytes(WIDTH if scale else OUTPUT_WIDTH, HEIGHT if scale else OUTPUT_HEIGHT)
    actual_size = output.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(f"Expected {count} decoded raw frames ({expected_size} bytes), got {actual_size} bytes")


def _rgb_from_yuv420(y: np.ndarray, cb420: np.ndarray, cr420: np.ndarray) -> Image.Image:
    cb = resize_keys_u8(cb420, scale=2, a=-0.5)
    cr = resize_keys_u8(cr420, scale=2, a=-0.5)
    ycbcr = np.stack((y, cb, cr), axis=-1)
    return Image.fromarray(ycbcr, mode="YCbCr").convert("RGB")


def _write_contact_sheet(frames: list[dict[str, object]], output: Path) -> None:
    thumb = (640, 360)
    label_height = 25
    columns = [("Decoded 4K reference", "reference"), ("Bicubic x4", "bicubic"), ("FSRCNN x2 + bicubic x2", "hybrid")]
    canvas = Image.new("RGB", (thumb[0] * len(columns), (thumb[1] + label_height) * len(frames)), color=(28, 28, 28))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for row, record in enumerate(frames):
        for col, (label, key) in enumerate(columns):
            x = col * thumb[0]
            y = row * (thumb[1] + label_height)
            draw.text((x + 6, y + 5), f"Frame {record['frame_index']}: {label}", fill=(245, 245, 245), font=font)
            image = record[key]
            assert isinstance(image, Image.Image)
            canvas.paste(image.resize(thumb, Image.Resampling.LANCZOS), (x, y + label_height))
    canvas.save(output, optimize=True)


def _encode_mp4(ffmpeg: str, raw_path: Path, output_path: Path, fps: float) -> str | None:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "yuv420p",
        "-video_size",
        f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
        "-framerate",
        f"{fps:.6g}",
        "-i",
        str(raw_path),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return None if completed.returncode == 0 else completed.stderr.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small software-only color video upscale prototype")
    parser.add_argument("--video", type=Path, help="Local UVG HEVC sequence")
    parser.add_argument("--raw-yuv420", type=Path, help="Local UVG raw YUV420 source (3840x2160)")
    parser.add_argument("--sequence", required=True, help="UVG sequence name for the manifest")
    parser.add_argument("--checkpoint", type=Path, default=Path("artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"))
    parser.add_argument("--quant-dir", type=Path, help="Optional A integer candidate quant directory (quant_params.json + integer weights)")
    parser.add_argument("--candidate-label", help="Short model identifier recorded in the output summary")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory under ignored .data/")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--preview-count", type=int, default=8, help="Number of representative frames to render into PNG previews/contact sheet")
    parser.add_argument("--frame-stride", type=int, default=10)
    parser.add_argument("--frame-offset", type=int, default=0)
    parser.add_argument("--source-fps", type=float, default=120.0)
    args = parser.parse_args()
    if (args.video is None) == (args.raw_yuv420 is None):
        raise ValueError("Specify exactly one of --video or --raw-yuv420")
    if args.frames <= 0 or args.preview_count <= 0 or args.frame_stride <= 0 or args.source_fps <= 0:
        raise ValueError("frames, preview-count, frame-stride and source-fps must be positive")
    indices = (
        selected_source_indices(args.frame_stride, args.frame_offset, args.frames)
        if args.raw_yuv420 is None
        else selected_raw_source_indices(args.frame_offset, args.frame_stride, args.frames)
    )
    source_path = args.video if args.video is not None else args.raw_yuv420
    assert source_path is not None
    if not source_path.is_file():
        raise FileNotFoundError("Input video source was not found")
    if args.raw_yuv420 is not None:
        source_frame_bytes = yuv420_frame_bytes(OUTPUT_WIDTH, OUTPUT_HEIGHT)
        if args.raw_yuv420.stat().st_size % source_frame_bytes:
            raise ValueError("Raw YUV420 source size is not a whole number of 3840x2160 frames")
        available_frames = args.raw_yuv420.stat().st_size // source_frame_bytes
        if max(indices) >= available_frames:
            raise ValueError(f"Requested source frame is outside the {available_frames}-frame raw sequence")
    if args.quant_dir is None and not args.checkpoint.is_file():
        raise FileNotFoundError("FP32 checkpoint was not found")
    if args.quant_dir is not None and not (args.quant_dir / "quant_params.json").is_file():
        raise FileNotFoundError(f"Integer quantization parameters not found under {args.quant_dir}")

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Prototype outputs must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    preview_count = min(args.preview_count, args.frames)
    preview_ordinals = (
        {args.frames // 2}
        if preview_count == 1
        else {round(i * (args.frames - 1) / (preview_count - 1)) for i in range(preview_count)}
    )
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required in the experiment runtime") from exc
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    low_path = output_dir / "input_540p_yuv420p.raw"
    reference_path = output_dir / "reference_4k_yuv420p.raw"
    if args.raw_yuv420 is None:
        assert args.video is not None
        _decode_selected_yuv420(
            ffmpeg,
            args.video,
            low_path,
            width=WIDTH,
            height=HEIGHT,
            count=args.frames,
            stride=args.frame_stride,
            offset=args.frame_offset,
            scale=True,
        )
        _decode_selected_yuv420(
            ffmpeg,
            args.video,
            reference_path,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            count=args.frames,
            stride=args.frame_stride,
            offset=args.frame_offset,
            scale=False,
        )
    else:
        _decode_selected_raw_yuv420(
            ffmpeg,
            args.raw_yuv420,
            low_path,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            source_fps=args.source_fps,
            count=args.frames,
            stride=args.frame_stride,
            offset=args.frame_offset,
            scale=True,
        )
        _decode_selected_raw_yuv420(
            ffmpeg,
            args.raw_yuv420,
            reference_path,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            source_fps=args.source_fps,
            count=args.frames,
            stride=args.frame_stride,
            offset=args.frame_offset,
            scale=False,
        )

    if args.quant_dir is None:
        checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
        model = HybridFSRCNN(PRESETS["R0"])
        model.load_state_dict(checkpoint.get("state_dict", checkpoint), strict=True)
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        model.to(device).eval()
        fixed = None
        model_mode = "frozen_FP32_R0"
        model_sha256 = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
        quant_params_sha256 = None
        model_path = str(args.checkpoint.resolve())
    else:
        model = None
        device = "CPU exact integer reference"
        fixed = FixedReference(args.quant_dir)
        candidate_label = args.candidate_label or args.quant_dir.parent.name
        model_mode = f"experimental_integer_candidate:{candidate_label}"
        model_sha256 = None
        quant_params_sha256 = sha256_file(args.quant_dir / "quant_params.json")
        model_path = str(args.quant_dir.resolve())

    input_frame_bytes = yuv420_frame_bytes(WIDTH, HEIGHT)
    ref_frame_bytes = yuv420_frame_bytes(OUTPUT_WIDTH, OUTPUT_HEIGHT)
    hybrid_raw_path = output_dir / "hybrid_4k_yuv420p.raw"
    frame_previews: list[dict[str, object]] = []
    metric_rows: list[dict[str, float | int]] = []
    with low_path.open("rb") as low_stream, reference_path.open("rb") as reference_stream, hybrid_raw_path.open("wb") as hybrid_stream:
        for ordinal, source_index in enumerate(indices):
            low_y, low_cb, low_cr = unpack_yuv420_frame(low_stream.read(input_frame_bytes), WIDTH, HEIGHT)
            ref_y, ref_cb, ref_cr = unpack_yuv420_frame(reference_stream.read(ref_frame_bytes), OUTPUT_WIDTH, OUTPUT_HEIGHT)
            if fixed is None:
                assert model is not None
                _, hybrid_y = run_hybrid_float_u8(model, low_y, keys_a=-0.5, device=device)
            else:
                _, hybrid_y = run_hybrid_integer_u8(fixed, low_y, keys_a=-0.5)
            bicubic_y = run_bicubic4x_u8(low_y, keys_a=-0.5)
            hybrid_cb = resize_keys_u8(low_cb, scale=4, a=-0.5)
            hybrid_cr = resize_keys_u8(low_cr, scale=4, a=-0.5)
            bicubic_cb = hybrid_cb
            bicubic_cr = hybrid_cr
            hybrid_stream.write(pack_yuv420_frame(hybrid_y, hybrid_cb, hybrid_cr))

            if ordinal in preview_ordinals:
                reference_rgb = _rgb_from_yuv420(ref_y, ref_cb, ref_cr)
                bicubic_rgb = _rgb_from_yuv420(bicubic_y, bicubic_cb, bicubic_cr)
                hybrid_rgb = _rgb_from_yuv420(hybrid_y, hybrid_cb, hybrid_cr)
                reference_rgb.save(output_dir / f"frame_{ordinal:03d}_reference.png", optimize=True)
                bicubic_rgb.save(output_dir / f"frame_{ordinal:03d}_bicubic.png", optimize=True)
                hybrid_rgb.save(output_dir / f"frame_{ordinal:03d}_hybrid.png", optimize=True)
                frame_previews.append(
                    {
                        "frame_index": source_index,
                        "reference": reference_rgb,
                        "bicubic": bicubic_rgb,
                        "hybrid": hybrid_rgb,
                    }
                )
            bicubic_psnr, bicubic_ssim = _metrics(ref_y, bicubic_y)
            hybrid_psnr, hybrid_ssim = _metrics(ref_y, hybrid_y)
            metric_rows.append(
                {
                    "frame_index": source_index,
                    "bicubic_y_psnr_db": bicubic_psnr,
                    "bicubic_y_ssim": bicubic_ssim,
                    "hybrid_y_psnr_db": hybrid_psnr,
                    "hybrid_y_ssim": hybrid_ssim,
                    "hybrid_y_delta_vs_bicubic_db": hybrid_psnr - bicubic_psnr,
                }
            )
            if (ordinal + 1) % 25 == 0 or ordinal + 1 == args.frames:
                print(f"Processed {ordinal + 1}/{args.frames} frames for {args.sequence}", flush=True)

    contact_sheet = output_dir / "color_video_contact_sheet.png"
    _write_contact_sheet(frame_previews, contact_sheet)
    output_fps = args.source_fps / args.frame_stride
    mp4_path = output_dir / "hybrid_4k_color_demo.mp4"
    encode_error = _encode_mp4(ffmpeg, hybrid_raw_path, mp4_path, output_fps)
    if encode_error is not None:
        mp4_path = None

    summary = {
        "schema": "member-a-color-video-software-prototype-v1",
        "status": "SOFTWARE_DEMO_ONLY_NOT_BOARD_PROTOCOL_OR_REALTIME_ACCEPTANCE",
        "dataset_url": DATASET_URL,
        "license": LICENSE,
        "sequence": args.sequence,
        "source_video": str(source_path.resolve()),
        "source_video_sha256": sha256_file(source_path),
        "source_frame_indices": indices,
        "source_fps_metadata": args.source_fps,
        "output_fps_for_selected_frames": output_fps,
        "input_format": "960x540 YUV420p; FFmpeg bicubic downscale; range mapped TV to PC for this demo",
        "metric_reference": "3840x2160 source Y plane, FFmpeg TV-to-PC range mapping; PSNR/SSIM use an 8-pixel shave on each edge",
        "output_format": f"3840x2160 YUV420p; Y uses {'integer QAT candidate' if fixed is not None else 'frozen FP32 R0'} FSRCNN x2 + Keys bicubic x2; Cb/Cr use Keys bicubic x4",
        "preview_rule": "Cb/Cr are Keys bicubic x2 upsampled for RGB preview only; raw output remains YUV420p",
        "keys_a": -0.5,
        "model_mode": model_mode,
        "model_artifact": model_path,
        "model_artifact_sha256": model_sha256,
        "quant_params_sha256": quant_params_sha256,
        "checkpoint": str(args.checkpoint.resolve()) if fixed is None else None,
        "checkpoint_sha256": model_sha256,
        "device": str(device),
        "frames": args.frames,
        "preview_source_frame_indices": [indices[i] for i in sorted(preview_ordinals)],
        "metrics": {
            "scope": "Y-plane PSNR/SSIM versus source 4K reference after range mapping; synthetic FFmpeg bicubic downscale input; 8-pixel border shaved",
            "mean": {
                key: float(np.mean([row[key] for row in metric_rows]))
                for key in ["bicubic_y_psnr_db", "bicubic_y_ssim", "hybrid_y_psnr_db", "hybrid_y_ssim", "hybrid_y_delta_vs_bicubic_db"]
            },
            "per_frame": metric_rows,
        },
        "outputs": {
            "contact_sheet": str(contact_sheet),
            "hybrid_yuv420p_raw": str(hybrid_raw_path),
            "mp4": str(mp4_path) if mp4_path is not None else None,
            "mp4_encode_error": encode_error,
        },
        "limitations": [
            "The 540p input is synthesized by software from a 4K HEVC sequence, not captured by a 540p camera.",
            f"The CNN is {model_mode}; integer mode uses the A-side exact integer reference only. RGB preview is software-only and does not establish a hardware chroma path.",
            "No UART/UDP, HDMI, DDR, FPGA timing, sustained frame rate, or board behavior is measured.",
            "UVG source is CC BY-NC and must not be redistributed commercially; generated frames stay in ignored .data/.",
        ],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "contact_sheet": str(contact_sheet), "mp4": summary["outputs"]["mp4"], "metrics": summary["metrics"]["mean"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
