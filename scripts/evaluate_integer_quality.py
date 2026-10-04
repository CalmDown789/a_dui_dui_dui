"""Evaluate the frozen integer network against paired Set5, video and synthetic references."""
from __future__ import annotations

from pathlib import Path
import base64
import csv
import hashlib
import html
import json
import platform
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".data" / "integer_quality"
SET5 = ROOT / ".data" / "set5"
VIDEO = ROOT / ".data" / "public_sequence" / "big_buck_bunny_720p_stereo.ogg"
SET5_COLLECTION_SHA256 = "b9cbe9ec0e9b09f440d75f73870598005439f54d4b9dc8a33e801fd2ecb3d79e"
VIDEO_SHA256 = "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28"
CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
QUANT_JSON_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"

import sys
sys.path.insert(0, str(ROOT / "src"))
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y
from member_a.model import FSRCNNSubpixel


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _gradient(width: int, height: int, top: int, bottom: int) -> Image.Image:
    values = np.linspace(top, bottom, height, dtype=np.uint8)[:, None]
    pixels = np.broadcast_to(values, (height, width)).copy()
    return Image.fromarray(pixels, mode="L")


def make_stress_scenes() -> list[tuple[str, str, Image.Image]]:
    """Create deterministic paired 1920x1080 grayscale diagnostics in memory."""
    width, height = 1920, 1080
    font_small = ImageFont.load_default(size=28)
    font_large = ImageFont.load_default(size=68)

    text = _gradient(width, height, 224, 176)
    draw = ImageDraw.Draw(text)
    draw.rounded_rectangle((120, 100, 1800, 980), radius=20, fill=238, outline=16, width=8)
    draw.text((180, 170), "FSRCNN  x2   FPGA", font=font_large, fill=8, stroke_width=1, stroke_fill=8)
    draw.text((180, 280), "A2  960 x 540  ->  1920 x 1080", font=font_small, fill=18)
    draw.text((180, 350), "0123456789  ABCDEFG  abcdefg", font=font_small, fill=24)
    draw.line((180, 455, 1740, 455), fill=28, width=3)
    for index, gap in enumerate((4, 7, 11, 15, 21, 29)):
        x = 240 + index * 240
        draw.rectangle((x, 535, x + gap, 890), fill=20 + index * 20)
    draw.text((190, 925), "SMALL STROKES  |  HIGH CONTRAST  |  EDGE DETAIL", font=font_small, fill=24)

    building = _gradient(width, height, 204, 126)
    draw = ImageDraw.Draw(building)
    draw.rectangle((0, 760, width, height), fill=105)
    draw.polygon(((240, 365), (960, 130), (1680, 365)), fill=78, outline=12)
    draw.rectangle((300, 350, 1620, 990), fill=178, outline=16, width=9)
    for row in range(4):
        y = 415 + row * 138
        for col in range(7):
            x = 352 + col * 182
            draw.rectangle((x, y, x + 112, y + 82), fill=48 + ((row + col) % 3) * 22, outline=22, width=5)
            draw.line((x + 56, y, x + 56, y + 82), fill=210, width=4)
            draw.line((x, y + 41, x + 112, y + 41), fill=210, width=4)
    draw.rectangle((870, 780, 1050, 990), fill=45, outline=18, width=6)
    for y in (560, 700, 840):
        for x in range(332, 1600, 48):
            draw.line((x, y, x + 24, y), fill=115, width=2)

    person = _gradient(width, height, 192, 120)
    draw = ImageDraw.Draw(person)
    draw.ellipse((650, 170, 1270, 790), fill=202, outline=26, width=9)
    draw.ellipse((790, 365, 860, 430), fill=18)
    draw.ellipse((1060, 365, 1130, 430), fill=18)
    draw.arc((825, 390, 1100, 650), start=18, end=155, fill=26, width=15)
    draw.line((960, 480, 935, 565, 995, 565), fill=30, width=11)
    draw.pieslice((610, 125, 1310, 615), start=180, end=360, fill=37, outline=16, width=8)
    draw.rounded_rectangle((735, 755, 1185, 835), radius=20, fill=166, outline=32, width=9)
    draw.polygon(((480, 1050), (580, 815), (730, 775), (960, 910), (1190, 775), (1340, 815), (1440, 1050)),
                 fill=94, outline=20)
    draw.line((960, 920, 960, 1070), fill=220, width=8)
    draw.line((800, 840, 760, 1040), fill=205, width=7)
    draw.line((1120, 840, 1160, 1040), fill=205, width=7)

    motion_scenes: list[tuple[str, str, Image.Image]] = []
    for frame_index, center_x in enumerate((470, 770, 1070, 1370)):
        image = _gradient(width, height, 185, 118)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 770, width, height), fill=92)
        draw.line((0, 798, width, 798), fill=34, width=8)
        for x in range(100, width, 240):
            draw.rectangle((x, 300, x + 18, 770), fill=72)
            draw.ellipse((x - 65, 220, x + 90, 385), fill=126)
        # Faint prior positions make direction and motion blur a repeatable stress case.
        for trail in (3, 2, 1):
            ghost_x = center_x - trail * 54
            shade = 164 + trail * 18
            draw.ellipse((ghost_x - 58, 475, ghost_x + 58, 592), fill=shade)
            draw.rounded_rectangle((ghost_x - 70, 580, ghost_x + 70, 825), radius=52, fill=shade)
        draw.ellipse((center_x - 66, 445, center_x + 66, 577), fill=24, outline=8, width=4)
        draw.ellipse((center_x - 45, 470, center_x - 25, 490), fill=245)
        draw.ellipse((center_x + 25, 470, center_x + 45, 490), fill=245)
        draw.rounded_rectangle((center_x - 78, 565, center_x + 78, 835), radius=58, fill=48, outline=14, width=7)
        leg = 38 + (frame_index % 2) * 24
        draw.line((center_x - 34, 810, center_x - 75 - leg, 1040), fill=35, width=33)
        draw.line((center_x + 34, 810, center_x + 78 + leg, 1035), fill=35, width=33)
        draw.line((center_x - 72, 620, center_x - 175, 730 + frame_index * 7), fill=35, width=25)
        draw.line((center_x + 72, 620, center_x + 165, 690 - frame_index * 4), fill=35, width=25)
        motion_scenes.append((f"motion_{frame_index:02d}", "synthetic_motion", image))
    return [("text_small_strokes", "synthetic_text", text),
            ("building_facade", "synthetic_architecture", building),
            ("portrait_face", "synthetic_person", person), *motion_scenes]


def _save_gray(path: Path, pixels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(pixels, dtype=np.uint8), mode="L").save(path, format="PNG", optimize=True)


def _uint8_from_float(tensor: torch.Tensor) -> np.ndarray:
    values = tensor.detach().to("cpu").numpy().squeeze().clip(0.0, 1.0)
    return np.floor(values * 255.0 + 0.5).astype(np.uint8)


def _crop_origin(reference: np.ndarray, error: np.ndarray, crop: int = 160) -> tuple[int, int, float]:
    height, width = reference.shape
    crop = min(crop, height, width)
    energy = np.pad(np.abs(error).astype(np.float64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    step = max(8, crop // 8)
    ys = list(range(0, max(1, height - crop + 1), step)) + [max(0, height - crop)]
    xs = list(range(0, max(1, width - crop + 1), step)) + [max(0, width - crop)]
    best = (-1.0, 0, 0)
    for y in set(ys):
        y2 = y + crop
        for x in set(xs):
            x2 = x + crop
            total = energy[y2, x2] - energy[y, x2] - energy[y2, x] + energy[y, x]
            value = float(total / (crop * crop))
            if value > best[0]:
                best = (value, y, x)
    return best[1], best[2], best[0]


def _score(reference: np.ndarray, candidate: torch.Tensor, device: torch.device) -> tuple[float, float]:
    target = torch.from_numpy(reference.astype(np.float32) / 255.0)[None, None].to(device)
    estimate = candidate.detach().to(device=device, dtype=torch.float32).reshape(1, 1, *reference.shape)
    return psnr_y(target, estimate, border=2), ssim_y(target, estimate, border=2)


def _score_tensors(reference: torch.Tensor, candidate: torch.Tensor) -> tuple[float, float]:
    """Compare model tensors before display rounding, with the report's fixed shave."""
    reference = reference.detach().to(dtype=torch.float32, device="cpu")
    candidate = candidate.detach().to(dtype=torch.float32, device="cpu")
    return psnr_y(reference, candidate, border=2), ssim_y(reference, candidate, border=2)


def _render_contact(rows: list[dict], sample_root: Path, target: Path) -> None:
    chosen = [row for row in rows if row["group"] == "synthetic_stress" and row["frame_id"] in
              ("text_small_strokes", "building_facade", "portrait_face", "motion_00", "motion_03")]
    labels = ("Reference", "Bicubic", "FP32", "INT8/INT16 integer")
    thumb_w, thumb_h, margin, title_h = 480, 270, 16, 44
    canvas = Image.new("RGB", (thumb_w * 4 + margin * 5, len(chosen) * (thumb_h + title_h) + margin * (len(chosen) + 1)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=22)
    for row_index, row in enumerate(chosen):
        y = margin + row_index * (thumb_h + title_h + margin)
        draw.text((margin, y + 6), f"{row['frame_id']}  ·  {row['group']}", fill="black", font=font)
        for col, (key, label) in enumerate(zip(("reference", "bicubic", "fp32", "integer"), labels, strict=True)):
            path = sample_root / row["local_artifacts"][key]
            image = Image.open(path).convert("L").resize((thumb_w, thumb_h), Image.Resampling.BICUBIC)
            x = margin + col * (thumb_w + margin)
            draw.text((x, y + title_h - 3), label, fill="black", font=font)
            canvas.paste(image.convert("RGB"), (x, y + title_h + margin))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set5-dir", type=Path, default=SET5)
    parser.add_argument("--video", type=Path, default=VIDEO)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty evaluation directory: {output_dir}")
    if not args.set5_dir.is_dir() or len(list(args.set5_dir.glob("*.png"))) != 5:
        parser.error("Set5 is missing: run scripts/download_data.py first")
    set5_paths = sorted(args.set5_dir.glob("*.png"))
    set5_sha = sha256("".join(file_sha(path) for path in set5_paths).encode())
    if set5_sha != SET5_COLLECTION_SHA256:
        parser.error("Set5 images do not match the frozen source file collection")
    checkpoint_path = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    quant_path = ROOT / "artifacts/quant/quant_params.json"
    if file_sha(checkpoint_path) != CHECKPOINT_SHA256 or file_sha(quant_path) != QUANT_JSON_SHA256:
        parser.error("Frozen model or quantization parameter hash changed")
    if not args.video.is_file() or file_sha(args.video) != VIDEO_SHA256:
        parser.error("Pinned, licensed Big Buck Bunny source movie is missing or changed")
    if args.ffmpeg:
        ffmpeg = str(args.ffmpeg)
    else:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    from datetime import datetime, timezone
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = output_dir / "samples"
    samples_dir.mkdir()
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(123)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.to(device).eval()
    fixed = FixedReference(ROOT / "artifacts/quant")

    inputs: list[tuple[str, str, np.ndarray, np.ndarray, dict]] = []
    # Set5 uses the exact Y conversion and bicubic x2 degradation in EvalDataset.
    for path in set5_paths:
        hr_image = Image.open(path).convert("YCbCr").getchannel("Y")
        hr_image = hr_image.crop((0, 0, hr_image.width - hr_image.width % 2, hr_image.height - hr_image.height % 2))
        lr_image = hr_image.resize((hr_image.width // 2, hr_image.height // 2), Image.Resampling.BICUBIC)
        inputs.append((path.stem, "set5_validation", np.asarray(hr_image, dtype=np.uint8),
                       np.asarray(lr_image, dtype=np.uint8), {"source_path": path.name, "source_sha256": file_sha(path)}))

    # Decode eight licensed movie frames as RGB. Convert RGB to Y with Pillow,
    # then form paired half-resolution inputs with the training BICUBIC rule.
    frame_indices = list(range(1440, 1536, 12))
    select = "select=gte(n\\,1440)*not(mod(n-1440\\,12)),format=rgb24"
    decode = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(args.video),
        "-vf", select, "-frames:v", "8", "-fps_mode", "passthrough", "-an", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert decode.stdout is not None
        frame_bytes = 1280 * 720 * 3
        for frame_id, source_index in enumerate(frame_indices):
            rgb = decode.stdout.read(frame_bytes)
            if len(rgb) != frame_bytes:
                raise RuntimeError(f"FFmpeg returned a truncated source frame {source_index}")
            y_image = Image.frombytes("RGB", (1280, 720), rgb).convert("YCbCr").getchannel("Y")
            lr_image = y_image.resize((640, 360), Image.Resampling.BICUBIC)
            hr = np.asarray(y_image, dtype=np.uint8)
            inputs.append((f"bbb_{source_index}", "licensed_video_2x_pair", hr,
                           np.asarray(lr_image, dtype=np.uint8), {"source_frame_index": source_index,
                            "source_timestamp_seconds": source_index / 24,
                            "decoded_rgb_sha256": sha256(rgb), "source_video_sha256": VIDEO_SHA256}))
        decode.stdout.close()
        stderr = decode.stderr.read() if decode.stderr else b""
        if decode.wait() != 0:
            raise RuntimeError("FFmpeg source frame decode failed: " + stderr.decode("utf-8", "replace")[-2000:])
    finally:
        if decode.poll() is None:
            decode.kill(); decode.wait()

    for name, group, hr_image in make_stress_scenes():
        lr_image = hr_image.resize((960, 540), Image.Resampling.BICUBIC)
        inputs.append((name, group, np.asarray(hr_image, dtype=np.uint8), np.asarray(lr_image, dtype=np.uint8),
                       {"reference": "Deterministic synthetic 1920x1080 scene; downsampled with Pillow BICUBIC"}))

    rows: list[dict] = []
    for index, (name, group, reference, lr, source) in enumerate(inputs):
        x = torch.from_numpy(lr.astype(np.float32) / 255.0)[None, None].to(device)
        with torch.inference_mode():
            fp32 = model(x).clamp(0.0, 1.0)
            bicubic = F.interpolate(x, size=reference.shape, mode="bicubic", align_corners=False).clamp(0.0, 1.0)
        integer = fixed.run(lr)["output"][:, :, 0]
        if tuple(integer.shape) != tuple(reference.shape):
            raise AssertionError(f"Integer output shape mismatch for {name}")
        expected = torch.from_numpy(reference.astype(np.float32) / 255.0)[None, None]
        model_outputs = {"bicubic": bicubic.cpu(), "fp32": fp32.cpu(),
                         "integer": torch.from_numpy(integer.astype(np.float32) / 255.0)[None, None]}
        scores: dict[str, tuple[float, float]] = {key: _score(reference, value, torch.device("cpu"))
                                                   for key, value in model_outputs.items()}
        int_ref_scores = _score_tensors(fp32.cpu(), model_outputs["integer"])
        directory = samples_dir / name
        directory.mkdir()
        images = {"reference": reference, "bicubic": _uint8_from_float(bicubic.cpu()),
                  "fp32": _uint8_from_float(fp32.cpu()), "integer": integer}
        for key, pixels in images.items():
            _save_gray(directory / f"{key}.png", pixels)
        error = np.abs(reference.astype(np.int16) - integer.astype(np.int16))
        y0, x0, worst_mae = _crop_origin(reference, error)
        crop_size = min(160, *reference.shape)
        for key, pixels in images.items():
            _save_gray(directory / f"{key}_detail.png", pixels[y0:y0 + crop_size, x0:x0 + crop_size])
        fp_u8 = _uint8_from_float(fp32.cpu())
        difference = np.abs(fp_u8.astype(np.int16) - integer.astype(np.int16))
        record = {
            "frame_id": name, "group": "synthetic_stress" if group.startswith("synthetic_") else group,
            "scenario": group, "input_shape_hw": list(lr.shape), "output_shape_hw": list(reference.shape),
            "input_sha256": sha256(lr.tobytes()), "reference_sha256": sha256(reference.tobytes()),
            "reference_kind": "paired_hr" if group != "set5_validation" else "Set5 validation HR",
            "source": source,
            "bicubic_psnr_db": scores["bicubic"][0], "bicubic_ssim": scores["bicubic"][1],
            "fp32_psnr_db": scores["fp32"][0], "fp32_ssim": scores["fp32"][1],
            "integer_psnr_db": scores["integer"][0], "integer_ssim": scores["integer"][1],
            "integer_vs_fp32_psnr_db": int_ref_scores[0], "integer_vs_fp32_ssim": int_ref_scores[1],
            "integer_vs_fp32_max_abs_u8": int(difference.max()),
            "integer_vs_fp32_mismatched_u8": int(np.count_nonzero(difference)),
            "worst_integer_detail_crop_xy": [x0, y0], "worst_integer_detail_crop_mae_u8": worst_mae,
            "metric_border_crop_px": 2,
            "local_artifacts": {key: f"{name}/{key}.png" for key in images},
        }
        rows.append(record)
        print(f"{index+1:02d}/{len(inputs)} {name}: int {scores['integer'][0]:.3f} dB", flush=True)

    # The full reference below is generated by the frozen integer golden engine.
    known = np.fromfile(ROOT / "artifacts/full_integer_golden/input_960x540_y_u8.bin", dtype=np.uint8).reshape(540, 960)
    known_out = fixed.run(known)["output"][:, :, 0]
    golden_path = ROOT / "artifacts/full_integer_golden/output_1920x1080_y_u8.bin"
    if known_out.tobytes() != golden_path.read_bytes():
        raise AssertionError("Integer quality evaluation did not reproduce the frozen full-size Golden")

    groups = sorted({row["group"] for row in rows})
    summary = {group: {key: float(np.mean([row[key] for row in rows if row["group"] == group]))
                       for key in ("bicubic_psnr_db", "bicubic_ssim", "fp32_psnr_db", "fp32_ssim",
                                   "integer_psnr_db", "integer_ssim", "integer_vs_fp32_psnr_db",
                                   "integer_vs_fp32_ssim")}
               for group in groups}
    by_int = sorted((row for row in rows if row["group"] == "synthetic_stress"), key=lambda row: row["integer_psnr_db"])
    worst = by_int[0]
    artifacts = output_dir / "samples"
    _render_contact(rows, artifacts, ROOT / "artifacts/evaluation/actual_integer_visual_review.png")
    # Detail panel for the most difficult paired stress sample.
    details = [Image.open(artifacts / worst["frame_id"] / f"{key}_detail.png").convert("L")
               for key in ("reference", "bicubic", "fp32", "integer")]
    magnified = Image.new("RGB", (len(details) * 480 + 80, 520), "white")
    draw = ImageDraw.Draw(magnified); font = ImageFont.load_default(size=24)
    for col, (image, label) in enumerate(zip(details, ("Reference", "Bicubic", "FP32", "Integer"), strict=True)):
        magnified.paste(image.resize((480, 480), Image.Resampling.NEAREST).convert("RGB"), (col * 500, 36))
        draw.text((col * 500, 5), label, fill="black", font=font)
    detail_path = ROOT / "artifacts/evaluation/actual_integer_worst_case_detail.png"
    magnified.save(detail_path, format="PNG", optimize=True)

    evaluation = {
        "schema": "member-a-actual-integer-quality-v1", "status": "PASS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": {"config": "FSRCNNSubpixel d16/s8/m1/c16 x2", "checkpoint_sha256": CHECKPOINT_SHA256,
                  "quant_params_sha256": QUANT_JSON_SHA256, "integer_engine": "src/member_a/fixed_reference.py",
                  "full_960x540_golden_sha256": sha256(golden_path.read_bytes()),
                  "full_golden_reproduced": True},
        "execution": {"python": platform.python_version(), "torch": torch.__version__,
                      "numpy": np.__version__, "pillow": Image.__version__, "device": str(device),
                      "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else platform.processor(),
                      "script_sha256": file_sha(Path(__file__).resolve()),
                      "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                      "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())},
        "metrics": {"range": "uint8 Y / normalized [0,1], PSNR peak=1", "border_crop_px": 2,
                    "ssim": "src/member_a/metrics.py Gaussian 11x11, sigma=1.5, constants 0.01^2/0.03^2",
                    "bicubic": "PyTorch F.interpolate(mode=bicubic, align_corners=False), clipped [0,1]",
                    "rounding_for_png": "floor(value*255+0.5); metrics use unrounded FP32 and exact integer u8/255",
                    "Set5_limit": "Set5 was used for checkpoint selection during training; these scores are not a held-out test.",
                    "synthetic_limit": "Text, facade, portrait and motion charts are generated stress tests, not natural-scene evidence.",
                    "video_limit": "Big Buck Bunny samples are licensed animation; paired half-size bicubic input and original decoded 720p Y are used. This is a 2x software metric, not 960x540 board evidence."},
        "dataset": {"set5_collection_sha256": SET5_COLLECTION_SHA256, "source_video_sha256": VIDEO_SHA256,
                    "video_source_frames": frame_indices, "video_source_timestamps_s": [i / 24 for i in frame_indices],
                    "video_source_frame_size": [1280, 720], "video_input_frame_size": [640, 360]},
        "summary_by_group": summary, "sample_count": len(rows), "samples": rows,
        "worst_synthetic_integer_case": {"frame_id": worst["frame_id"],
            "integer_psnr_db": worst["integer_psnr_db"], "integer_ssim": worst["integer_ssim"],
            "detail_crop_xy": worst["worst_integer_detail_crop_xy"],
            "detail_crop_mae_u8": worst["worst_integer_detail_crop_mae_u8"],
            "image": "actual_integer_worst_case_detail.png"},
        "visual_review": "actual_integer_visual_review.png",
        "physical_board_tested": False,
    }
    json_path = ROOT / "artifacts/evaluation/actual_integer_quality_report.json"
    json_path.write_text(json.dumps(evaluation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    csv_path = ROOT / "artifacts/evaluation/actual_integer_quality_per_image.csv"
    columns = ["frame_id", "group", "scenario", "input_shape_hw", "output_shape_hw", "bicubic_psnr_db", "bicubic_ssim",
               "fp32_psnr_db", "fp32_ssim", "integer_psnr_db", "integer_ssim", "integer_vs_fp32_psnr_db",
               "integer_vs_fp32_ssim", "integer_vs_fp32_max_abs_u8", "integer_vs_fp32_mismatched_u8",
               "worst_integer_detail_crop_xy", "worst_integer_detail_crop_mae_u8", "input_sha256", "reference_sha256"]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if isinstance(row[key], (list, dict)) else row[key]
                             for key in columns})

    contact = (ROOT / "artifacts/evaluation/actual_integer_visual_review.png").read_bytes()
    detail = detail_path.read_bytes()
    set_rows = [row for row in rows if row["group"] == "set5_validation"]
    bbb_rows = [row for row in rows if row["group"] == "licensed_video_2x_pair"]
    synthetic_rows = [row for row in rows if row["group"] == "synthetic_stress"]
    def table(items: list[dict]) -> str:
        result = ["<table><thead><tr><th>样本</th><th>双三次 PSNR/SSIM</th><th>FP32 PSNR/SSIM</th><th>实际整数 PSNR/SSIM</th><th>整数与 FP32</th></tr></thead><tbody>"]
        for row in items:
            result.append(f"<tr><td>{html.escape(row['frame_id'])}</td><td>{row['bicubic_psnr_db']:.3f} dB / {row['bicubic_ssim']:.5f}</td>"
                f"<td>{row['fp32_psnr_db']:.3f} dB / {row['fp32_ssim']:.5f}</td><td>{row['integer_psnr_db']:.3f} dB / {row['integer_ssim']:.5f}</td>"
                f"<td>{row['integer_vs_fp32_psnr_db']:.2f} dB; {row['integer_vs_fp32_mismatched_u8']} differing pixels</td></tr>")
        result.append("</tbody></table>")
        return "".join(result)
    html_report = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FSRCNN 实际整数模型画质评测</title><style>body{{font:16px/1.6 system-ui,'Microsoft YaHei',sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#17202a}}h1,h2{{line-height:1.25}}.note{{background:#fff5d6;padding:14px;border-left:4px solid #d19a00}}table{{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}}th,td{{border:1px solid #ccd1d1;padding:8px;text-align:left}}th{{background:#edf2f7}}img{{max-width:100%;height:auto}}figure{{margin:20px 0}}.muted{{color:#566573}}</style>
<h1>FSRCNN d16/s8/m1/c16 实际整数模型画质评测</h1><p>冻结权重与量化参数未改。整数输出由逐层 INT8 权重、INT16 激活参考实现重新计算；FP32 与双三次使用相同 LR 亮度输入。</p>
<div class="note"><b>读数范围：</b>Set5 曾参与 checkpoint 选择，不能当成独立测试集。8 个 Big Buck Bunny 样本是动画视频的 720p 真值及配对 360p bicubic 输入，评的是 2×软件泛化。文字、建筑、人物、运动图为程序生成压力样例，不能代替真实照片。板卡和 bitstream 未参与。</div>
<h2>Set5（复用验证集，非 held-out）</h2>{table(set_rows)}
<h2>授权视频配对 2×样本（1280×720 → 640×360 输入）</h2><p>源视频帧逐一解码为 RGB，再以 Pillow YCbCr-Y 作为 HR；LR 使用与训练一致的 Pillow BICUBIC 缩至一半。输出尺寸为 1280×720。</p>{table(bbb_rows)}
<h2>合成场景压力样例（1920×1080 真值）</h2><p>每张合成 HR 图使用同一 BICUBIC 规则生成 960×540 LR。内容覆盖小字笔画、立面窗格、人脸轮廓和带拖影的运动序列。</p>{table(synthetic_rows)}
<h2>视觉并排</h2><p>每行依次为生成真值、双三次、FP32、实际整数输出。图为灰度 Y。彩色视频合成如下；Big Buck Bunny © copyright 2008, Blender Foundation / www.bigbuckbunny.org，<a href="https://creativecommons.org/licenses/by/3.0/">CC BY 3.0</a>，<a href="https://peach.blender.org/about/">官方授权说明</a>。</p><video controls preload="metadata" width="960" src="../color_demo/bbb_fsrcnn_integer_960x540_to_1920x1080.mp4"></video><figure><img alt="合成场景参考、双三次、FP32和整数结果" src="data:image/png;base64,{base64.b64encode(contact).decode('ascii')}"></figure>
<h2>整数模型误差最大的合成细节块</h2><p>按整数结果对合成真值的局部平均绝对误差选择窗口，Nearest 放大显示；用于定位压力样例中的短板，不代表自然画面失败概率。</p><figure><img alt="最差合成局部细节" src="data:image/png;base64,{base64.b64encode(detail).decode('ascii')}"></figure>
<h2>口径与文件</h2><ul><li>PSNR 峰值 1.0，亮度归一化 [0,1]，四周裁 2 像素；SSIM 使用项目中的 11×11 Gaussian、sigma 1.5。</li><li>PNG 显示时 FP32 以 floor(v×255+0.5) 转 uint8；PSNR/SSIM 对 FP32 使用未舍入张量，对整数直接使用 uint8/255。</li><li>逐图数据：<a href="actual_integer_quality_per_image.csv">CSV</a>；来源哈希与完整说明：<a href="actual_integer_quality_report.json">JSON</a>。</li><li>视频素材 Big Buck Bunny © copyright 2008, Blender Foundation / www.bigbuckbunny.org，CC BY 3.0。视频处理步骤和数据边界见随附说明。</li></ul><p class="muted">报告由冻结 A 侧 checkpoint 和量化资产生成；具体哈希见 JSON。集合均值按图像等权平均。</p></html>"""
    html_path = ROOT / "artifacts/evaluation/actual_integer_quality_report.html"
    html_path.write_text(html_report, encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS", "samples": len(rows), "device": str(device),
        "set5_mean_integer_psnr_db": summary["set5_validation"]["integer_psnr_db"],
        "video_mean_integer_psnr_db": summary["licensed_video_2x_pair"]["integer_psnr_db"],
        "synthetic_mean_integer_psnr_db": summary["synthetic_stress"]["integer_psnr_db"],
        "worst_synthetic": worst["frame_id"], "report": str(html_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
