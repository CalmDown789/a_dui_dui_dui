"""Recheck EMA v2 on the eight BBB source frames and package 540p integer Golden.

The 720p source supplies a genuine 360p->720p paired quality test.  The
separately prepared 540p->1080p board inputs have no 1080p ground truth, so
their comparison records only R0-versus-candidate output differences.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
from PIL import Image, ImageDraw
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / ".data/model_optimization/site-packages"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_dynamic_crop_ab import make_video_samples
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y


CANDIDATE_ID = "R0_QAT_EMA_seed20261006_v2"
CANDIDATE = ROOT / "experiments/model_optimization_20261005/candidate_delivery" / CANDIDATE_ID
EXPECTED = {
    "video": "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28",
    "r0_checkpoint": "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5",
    "r0_quant": "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a",
    "candidate_checkpoint": "10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a",
    "candidate_quant": "12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_hash(path: Path, expected: str) -> None:
    actual = sha_file(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual} != {expected}")


def integer_output(engine: FixedReference, image: np.ndarray) -> np.ndarray:
    for stage, output in engine.iter_outputs(image):
        if stage == "output":
            return output[:, :, 0].copy()
    raise AssertionError("Integer reference did not produce output")


def score(reference: np.ndarray, output: np.ndarray) -> tuple[float, float]:
    target = torch.from_numpy(reference.astype(np.float32) / 255.0)[None, None]
    prediction = torch.from_numpy(output.astype(np.float32) / 255.0)[None, None]
    return psnr_y(target, prediction, border=2), ssim_y(target, prediction, border=2)


def strongest_crop(a: np.ndarray, b: np.ndarray, size: int = 192) -> tuple[int, int]:
    a_int = a.astype(np.int16)
    difference = np.abs(a_int - b.astype(np.int16)).astype(np.int64)
    texture = np.abs(np.diff(a_int, axis=1, prepend=a_int[:, :1]))
    texture += np.abs(np.diff(a_int, axis=0, prepend=a_int[:1, :]))
    # Favor details where a visual side-by-side is useful, while retaining
    # weight for places where the models actually disagree.
    interest = difference * 2 + texture.astype(np.int64)
    integral = np.pad(interest, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    stride = 64
    xs = list(range(0, a.shape[1] - size + 1, stride))
    ys = list(range(0, a.shape[0] - size + 1, stride))
    if xs[-1] != a.shape[1] - size:
        xs.append(a.shape[1] - size)
    if ys[-1] != a.shape[0] - size:
        ys.append(a.shape[0] - size)
    return max(
        ((x, y) for y in ys for x in xs),
        key=lambda xy: integral[xy[1] + size, xy[0] + size]
        - integral[xy[1], xy[0] + size]
        - integral[xy[1] + size, xy[0]]
        + integral[xy[1], xy[0]],
    )


def contact_sheet(rows: list[dict], raw_dir: Path, kind: str, target: Path) -> None:
    key = "quality_psnr_gain_db" if kind == "quality" else "board_mean_abs_delta_u8"
    ordered = sorted(rows, key=lambda row: row[key])
    chosen = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    size, gap, header, footer = 192, 12, 32, 36
    sheet = Image.new("RGB", (3 * size + 4 * gap, 3 * (size + header) + 4 * gap + footer), "white")
    draw = ImageDraw.Draw(sheet)
    for row_index, row in enumerate(chosen):
        frame = row["frame_id"]
        suffix = "quality" if kind == "quality" else "board"
        a = np.fromfile(raw_dir / f"frame_{frame:03d}_{suffix}_r0.bin", dtype=np.uint8)
        b = np.fromfile(raw_dir / f"frame_{frame:03d}_{suffix}_ema.bin", dtype=np.uint8)
        height, width = ((720, 1280) if kind == "quality" else (1080, 1920))
        a, b = a.reshape(height, width), b.reshape(height, width)
        x, y = strongest_crop(a, b, size)
        a_crop, b_crop = a[y:y + size, x:x + size], b[y:y + size, x:x + size]
        amplified = np.minimum(np.abs(a_crop.astype(np.int16) - b_crop.astype(np.int16)) * 32, 255).astype(np.uint8)
        ypos = gap + row_index * (size + header + gap)
        score_label = (f"gain {row[key]:+.3f} dB" if kind == "quality" else f"mean delta {row[key]:.3f} Y8")
        draw.text((gap, ypos), f"frame {frame}  crop ({x},{y})  {score_label}", fill="black")
        for col, image in enumerate((a_crop, b_crop, amplified)):
            sheet.paste(Image.fromarray(image, "L").convert("RGB"), (gap + col * (size + gap), ypos + header))
    draw.text((gap, sheet.height - footer + 6), "R0 | EMA v2 | abs difference x32; Big Buck Bunny (c) Blender Foundation, CC BY 3.0", fill="black")
    sheet.save(target, optimize=True)


def zip_entry(archive: ZipFile, name: str, data: bytes) -> None:
    entry = ZipInfo(name, date_time=(2026, 10, 14, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    archive.writestr(entry, data, compress_type=ZIP_DEFLATED, compresslevel=6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "experiments/model_optimization_20261005/evaluation/bbb_ema_v2_20261014")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".data/member_a_ema_v2_natural8_20261014")
    parser.add_argument("--package", type=Path, help="Destination for the candidate eight-frame Golden ZIP")
    args = parser.parse_args()
    output_dir, raw_dir = args.output_dir.resolve(), args.raw_dir.resolve()
    package = (args.package or output_dir / "A_EMA_V2_NATURAL8_GOLDEN_20261014.zip").resolve()
    for directory in (output_dir, raw_dir, package.parent):
        if not directory.is_relative_to(ROOT.parent):
            parser.error(f"Output must remain under the repository parent: {directory}")
        directory.mkdir(parents=True, exist_ok=True)

    source_video = ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg"
    paths = {
        "video": source_video,
        "r0_checkpoint": ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth",
        "r0_quant": ROOT / "artifacts/quant/quant_params.json",
        "candidate_checkpoint": CANDIDATE / "training/candidate_ema_qat_fp32.pth",
        "candidate_quant": CANDIDATE / "quant/quant_params.json",
    }
    for name, path in paths.items():
        check_hash(path, EXPECTED[name])
    frozen = FixedReference(ROOT / "artifacts/quant")
    candidate = FixedReference(CANDIDATE / "quant")
    board_manifest_path = ROOT / "artifacts/multiframe/manifest.json"
    board_manifest = json.loads(board_manifest_path.read_text(encoding="utf-8"))
    if len(board_manifest["frames"]) != 8:
        raise ValueError("Expected exactly eight frozen board-input frames")
    samples = make_video_samples(source_video)
    if len(samples) != 8:
        raise ValueError("Expected exactly eight decoded quality frames")
    previous_csv = ROOT / ".data/model_optimization/qat_ema_refine_20261006/evaluation_div2k_bbb/per_sample_metrics.csv"
    with previous_csv.open(newline="", encoding="utf-8") as stream:
        previous = {row["sample"]: row for row in csv.DictReader(stream) if row["group"] == "bbb_development_8"}
    if len(previous) != 8:
        raise ValueError("Existing BBB development-result table is incomplete")

    rows: list[dict] = []
    package_files: list[tuple[str, Path]] = []
    for frame, sample in enumerate(samples):
        board_info = board_manifest["frames"][frame]
        expected_index = 1440 + frame * 12
        if board_info["source_frame_index"] != expected_index or sample["name"] != f"bbb_{expected_index}":
            raise ValueError(f"Source frame identity differs at index {frame}")

        low, high = sample["lr_u8"], sample["hr_u8"]
        r0_quality = integer_output(frozen, low)
        ema_quality = integer_output(candidate, low)
        r0_psnr, r0_ssim = score(high, r0_quality)
        ema_psnr, ema_ssim = score(high, ema_quality)
        for prefix, actual_psnr, actual_ssim in (("frozen", r0_psnr, r0_ssim), ("candidate", ema_psnr, ema_ssim)):
            old = previous[sample["name"]]
            if abs(actual_psnr - float(old[f"{prefix}_integer_psnr_db"])) > 1e-5 or abs(actual_ssim - float(old[f"{prefix}_integer_ssim"])) > 1e-7:
                raise AssertionError(f"Existing exact-integer quality result did not reproduce: {sample['name']} {prefix}")
        (raw_dir / f"frame_{frame:03d}_quality_r0.bin").write_bytes(r0_quality.tobytes())
        (raw_dir / f"frame_{frame:03d}_quality_ema.bin").write_bytes(ema_quality.tobytes())

        input_path = ROOT / "artifacts/multiframe" / board_info["input"]["path"]
        r0_path = ROOT / "artifacts/multiframe" / board_info["golden"]["path"]
        check_hash(input_path, board_info["input"]["sha256"])
        check_hash(r0_path, board_info["golden"]["sha256"])
        board_input = np.fromfile(input_path, dtype=np.uint8).reshape(540, 960)
        board_r0 = np.fromfile(r0_path, dtype=np.uint8).reshape(1080, 1920)
        board_ema = integer_output(candidate, board_input)
        board_diff = np.abs(board_ema.astype(np.int16) - board_r0.astype(np.int16))
        candidate_path = raw_dir / f"frame_{frame:03d}_candidate_output_y_u8.bin"
        candidate_path.write_bytes(board_ema.tobytes())
        (raw_dir / f"frame_{frame:03d}_board_r0.bin").write_bytes(board_r0.tobytes())
        (raw_dir / f"frame_{frame:03d}_board_ema.bin").write_bytes(board_ema.tobytes())
        package_files.extend(((f"frames/frame_{frame:03d}_input_y_u8.bin", input_path),
                              (f"frames/frame_{frame:03d}_candidate_output_y_u8.bin", candidate_path)))
        row = {
            "frame_id": frame,
            "source_frame_index": expected_index,
            "source_timestamp_s": board_info["source_timestamp_seconds"],
            "quality_r0_psnr_db": r0_psnr,
            "quality_ema_psnr_db": ema_psnr,
            "quality_psnr_gain_db": ema_psnr - r0_psnr,
            "quality_r0_ssim": r0_ssim,
            "quality_ema_ssim": ema_ssim,
            "quality_ssim_gain": ema_ssim - r0_ssim,
            "board_input_sha256": board_info["input"]["sha256"],
            "board_r0_output_sha256": board_info["golden"]["sha256"],
            "board_ema_output_sha256": sha_bytes(board_ema.tobytes()),
            "board_mean_abs_delta_u8": float(board_diff.mean()),
            "board_max_abs_delta_u8": int(board_diff.max()),
            "board_changed_pixels": int(np.count_nonzero(board_diff)),
            "board_changed_fraction": float(np.count_nonzero(board_diff) / board_diff.size),
        }
        rows.append(row)
        print(f"{frame + 1}/8 source {expected_index}: quality gain {row['quality_psnr_gain_db']:+.4f} dB; board MAE {row['board_mean_abs_delta_u8']:.4f}", flush=True)

    csv_path = output_dir / "per_frame.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    contact_sheet(rows, raw_dir, "quality", output_dir / "quality_crops.png")
    contact_sheet(rows, raw_dir, "board", output_dir / "board_crops.png")

    package_manifest = {
        "schema": "member-a-ema-v2-natural8-integer-golden-v1",
        "candidate_status": "EXPERIMENTAL_NOT_RELEASED",
        "candidate_id": CANDIDATE_ID,
        "candidate_checkpoint_sha256": EXPECTED["candidate_checkpoint"],
        "candidate_quant_params_sha256": EXPECTED["candidate_quant"],
        "source_video_sha256": EXPECTED["video"],
        "frozen_board_input_manifest_sha256": sha_file(board_manifest_path),
        "input_shape_hwc": [540, 960, 1],
        "output_shape_hwc": [1080, 1920, 1],
        "dtype": "uint8",
        "layout": "HWC_row_major",
        "files": {name: {"bytes": path.stat().st_size, "sha256": sha_file(path)} for name, path in package_files},
        "limits": "PC exact-integer software Golden for eight independent frames; no candidate RTL, FPGA, board, timing or FPS result",
    }
    readme = (
        "# EMA v2 candidate natural eight-frame integer Golden\n\n"
        "Each input is the same 960x540 Y8 frame used by the frozen R0 natural-eight board test. "
        "Each output is generated by A's exact integer reference with the candidate quantization files. "
        "Validate all sizes and SHA-256 values against manifest.json before use. "
        "The candidate remains experimental; these files do not establish hardware timing or board output.\n\n"
        "Big Buck Bunny (2008), (c) Blender Foundation / www.bigbuckbunny.org, CC BY 3.0. "
        "https://creativecommons.org/licenses/by/3.0/\n"
    )
    with ZipFile(package, "w") as archive:
        for name, path in package_files:
            zip_entry(archive, name, path.read_bytes())
        zip_entry(archive, "manifest.json", (json.dumps(package_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        zip_entry(archive, "README.md", readme.encode("utf-8"))

    summary = {
        "schema": "member-a-ema-v2-natural8-quality-and-board-input-review-v1",
        "status": "PC_SOFTWARE_CANDIDATE_NOT_RELEASED",
        "identity": EXPECTED,
        "frozen_board_input_manifest_sha256": sha_file(board_manifest_path),
        "previous_bbb_development_csv_sha256": sha_file(previous_csv),
        "quality": {
            "protocol": "Same BBB source indices 1440..1524 step 12; RGB decode to YCbCr Y, Pillow bicubic 640x360 LR, 1280x720 HR; exact integer R0 and EMA v2; Y PSNR/SSIM shave 2",
            "samples": 8,
            "mean_r0_psnr_db": float(np.mean([r["quality_r0_psnr_db"] for r in rows])),
            "mean_ema_psnr_db": float(np.mean([r["quality_ema_psnr_db"] for r in rows])),
            "mean_psnr_gain_db": float(np.mean([r["quality_psnr_gain_db"] for r in rows])),
            "mean_r0_ssim": float(np.mean([r["quality_r0_ssim"] for r in rows])),
            "mean_ema_ssim": float(np.mean([r["quality_ema_ssim"] for r in rows])),
            "mean_ssim_gain": float(np.mean([r["quality_ssim_gain"] for r in rows])),
            "positive_psnr_frames": sum(r["quality_psnr_gain_db"] > 0 for r in rows),
            "scope": "Previously observed development animation frames; not independent final test, camera video, 1080p board-output ground truth, or subjective quality judgment",
        },
        "board_input_comparison": {
            "protocol": "Same frozen 960x540 input bytes; R0 frozen software Golden versus EMA v2 exact integer output at 1920x1080",
            "samples": 8,
            "mean_abs_delta_u8": float(np.mean([r["board_mean_abs_delta_u8"] for r in rows])),
            "scope": "Inter-model difference only; no 1080p ground truth, PSNR/SSIM quality claim, hardware output, or FPS claim",
        },
        "candidate_natural8_package": {"name": package.name, "bytes": package.stat().st_size, "sha256": sha_file(package)},
        "per_frame_csv": csv_path.name,
        "contact_sheets": ["quality_crops.png", "board_crops.png"],
        "attribution": "Big Buck Bunny (2008), (c) Blender Foundation / www.bigbuckbunny.org, CC BY 3.0",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"quality": summary["quality"], "package": summary["candidate_natural8_package"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
