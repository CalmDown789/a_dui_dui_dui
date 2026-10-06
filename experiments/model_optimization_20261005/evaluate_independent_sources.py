"""Measure Set5 and licensed Sintel frames with exact integer references."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import imageio_ffmpeg
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import EvalDataset
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y
from member_a.model import FSRCNNSubpixel
from member_a.quantization import quantized_forward_float


SINTEL_FRAMES = (1440, 2880, 4320, 5760, 7200, 8640, 10080, 11520)
SINTEL_LICENSE = "Creative Commons Attribution 3.0; credit © copyright Blender Foundation | durian.blender.org"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_model(path: Path, device: torch.device) -> FSRCNNSubpixel:
    saved = torch.load(path, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    return model.to(device).eval()


def to_u8(tensor: torch.Tensor) -> np.ndarray:
    return np.floor(tensor.detach().cpu().numpy().squeeze().clip(0, 1) * 255.0 + 0.5).astype(np.uint8)


def measure(target: torch.Tensor, output: torch.Tensor) -> tuple[float, float]:
    target = target.detach().cpu().to(torch.float32)
    output = output.detach().cpu().to(torch.float32)
    return psnr_y(target, output, border=2), ssim_y(target, output, border=2)


def scales_from_bundle(quant_dir: Path) -> dict[str, float]:
    spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    return {layer["name"]: float(layer["output_scale"])
            for layer in spec["layers"] if layer["name"] != "subpixel"}


def make_sintel_samples(video: Path) -> tuple[list[dict], str]:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    selector = "select=" + "+".join(f"eq(n\\,{frame})" for frame in SINTEL_FRAMES) + ",format=rgb24"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
               "-vf", selector, "-frames:v", str(len(SINTEL_FRAMES)), "-fps_mode", "passthrough",
               "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, check=True, timeout=300)
    width, height = 1280, 544
    frame_bytes = width * height * 3
    if len(decoded.stdout) != len(SINTEL_FRAMES) * frame_bytes:
        raise RuntimeError(f"Decoded {len(decoded.stdout) // frame_bytes} Sintel frames; expected {len(SINTEL_FRAMES)}")
    samples = []
    for index, frame_index in enumerate(SINTEL_FRAMES):
        raw = decoded.stdout[index * frame_bytes:(index + 1) * frame_bytes]
        y_image = Image.frombytes("RGB", (width, height), raw).convert("YCbCr").getchannel("Y")
        lr_image = y_image.resize((width // 2, height // 2), Image.Resampling.BICUBIC)
        lr = np.asarray(lr_image, dtype=np.uint8)
        hr = np.asarray(y_image, dtype=np.uint8)
        samples.append({
            "name": f"sintel_frame_{frame_index}", "group": "sintel_cc_by_video_8",
            "lr_u8": lr, "hr_u8": hr,
            "lr_tensor": torch.from_numpy(lr.astype(np.float32) / 255.0)[None, None],
        })
    return samples, file_sha(video)


def sample_from_set5(dataset: EvalDataset, index: int) -> dict:
    name, lr, hr = dataset[index]
    lr_u8 = to_u8(lr)
    hr_u8 = to_u8(hr)
    return {"name": name, "group": "set5", "lr_u8": lr_u8, "hr_u8": hr_u8,
            "lr_tensor": torch.from_numpy(lr_u8.astype(np.float32) / 255.0)[None, None]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=ROOT / ".data/public_sequence/sintel-1280-surround.mp4")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--candidate-run", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--candidate-checkpoint-name", default="candidate_qat_fp32.pth")
    parser.add_argument("--candidate-quant", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/evaluation_calibration_ab/candidate_quantized")
    parser.add_argument("--frozen-train-quant", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/evaluation_calibration_ab/frozen_train_calibrated_quantized")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/independent_eval")
    args = parser.parse_args()

    if not args.video.is_file() or args.video.stat().st_size != 228_945_052:
        parser.error("Sintel video is missing or incomplete; expected the official 1280x544 MP4 download")
    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    candidate_checkpoint = args.candidate_run.resolve() / args.candidate_checkpoint_name
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty result directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    frozen_model = load_model(frozen_checkpoint, device)
    candidate_model = load_model(candidate_checkpoint, device)
    candidate_scales = scales_from_bundle(args.candidate_quant.resolve())
    train_scales = scales_from_bundle(args.frozen_train_quant.resolve())
    engines = {
        "frozen_original": FixedReference(ROOT / "artifacts/quant"),
        "frozen_train_calibrated": FixedReference(args.frozen_train_quant.resolve()),
        "candidate": FixedReference(args.candidate_quant.resolve()),
    }
    set5 = EvalDataset(args.data_dir.resolve() / "set5")
    samples = [sample_from_set5(set5, index) for index in range(len(set5))]
    sintel_samples, video_sha = make_sintel_samples(args.video.resolve())
    samples.extend(sintel_samples)

    rows = []
    for sample in samples:
        x = sample["lr_tensor"].to(device)
        target = torch.from_numpy(sample["hr_u8"].astype(np.float32) / 255.0)[None, None]
        with torch.inference_mode():
            frozen_fp = frozen_model(x).clamp(0, 1).cpu()
            candidate_fp = candidate_model(x).clamp(0, 1).cpu()
            candidate_qdq = quantized_forward_float(candidate_model, x, candidate_scales).clamp(0, 1).cpu()
            frozen_train_qdq = quantized_forward_float(frozen_model, x, train_scales).clamp(0, 1).cpu()
            bicubic = F.interpolate(x, size=target.shape[-2:], mode="bicubic", align_corners=False).clamp(0, 1).cpu()
        row = {"sample": sample["name"], "group": sample["group"]}
        for name, output in (("bicubic", bicubic), ("frozen_fp32", frozen_fp),
                             ("candidate_fp32", candidate_fp), ("candidate_qdq", candidate_qdq),
                             ("frozen_train_calibrated_qdq", frozen_train_qdq)):
            row[f"{name}_psnr_db"], row[f"{name}_ssim"] = measure(target, output)
        for name, engine in engines.items():
            out_u8 = engine.run(sample["lr_u8"])["output"][:, :, 0]
            output = torch.from_numpy(out_u8.astype(np.float32) / 255.0)[None, None]
            row[f"{name}_integer_psnr_db"], row[f"{name}_integer_ssim"] = measure(target, output)
        row["candidate_integer_delta_vs_frozen_db"] = row["candidate_integer_psnr_db"] - row["frozen_original_integer_psnr_db"]
        row["candidate_integer_delta_vs_train_calibrated_frozen_db"] = row["candidate_integer_psnr_db"] - row["frozen_train_calibrated_integer_psnr_db"]
        row["candidate_quant_loss_db"] = row["candidate_fp32_psnr_db"] - row["candidate_integer_psnr_db"]
        rows.append(row)
        print(f"{sample['group']} {sample['name']} done", flush=True)

    groups = {}
    metric_names = [key for key in rows[0] if key.endswith(("_psnr_db", "_ssim"))]
    for group in sorted({row["group"] for row in rows}):
        subset = [row for row in rows if row["group"] == group]
        groups[group] = {"samples": len(subset), **{
            key: float(np.mean([row[key] for row in subset])) for key in metric_names
        }}
        groups[group]["candidate_integer_delta_vs_frozen_db"] = float(np.mean([row["candidate_integer_delta_vs_frozen_db"] for row in subset]))
        groups[group]["candidate_integer_delta_vs_train_calibrated_frozen_db"] = float(np.mean([row["candidate_integer_delta_vs_train_calibrated_frozen_db"] for row in subset]))
        groups[group]["candidate_quant_loss_db"] = float(np.mean([row["candidate_quant_loss_db"] for row in subset]))

    csv_path = output_dir / "per_sample_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-independent-source-evaluation-v1",
        "status": "EXPLORATORY_SOFTWARE_ONLY",
        "frozen_checkpoint_sha256": file_sha(frozen_checkpoint),
        "candidate_checkpoint_sha256": file_sha(candidate_checkpoint),
        "candidate_quant_params_sha256": file_sha(args.candidate_quant.resolve() / "quant_params.json"),
        "sintel_video_sha256": video_sha,
        "sintel_source_page": "https://durian.blender.org/download/",
        "sintel_license_and_attribution": SINTEL_LICENSE,
        "sintel_frame_indices": list(SINTEL_FRAMES),
        "set5_source_sha256": json.loads((args.data_dir.resolve() / "dataset_manifest.json").read_text(encoding="utf-8"))["Set5"]["sha256"],
        "groups": groups,
        "scope_limits": [
            "Sintel is an additional public animation video, not a real camera capture; its frames were not used in training, calibration, or checkpoint selection.",
            "Set5 was not used to choose this candidate; earlier unrelated experiments in the repository did use Set5.",
            "DIV2K/Set5 metrics are software reference results. No FPGA or board acceptance is implied.",
            "Sintel content is CC BY 3.0; preserve the stated Blender Foundation attribution when redistributing derived evaluation material.",
        ],
        "per_sample_csv": csv_path.name,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(groups, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
