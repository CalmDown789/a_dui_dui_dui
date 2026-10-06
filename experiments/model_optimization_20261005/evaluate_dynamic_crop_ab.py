"""Compare frozen, fixed-crop and epoch-resampled fine-tuning candidates."""
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
from member_a.quantization import calibrate_activation_scales, export_quantized_bundle


BASE_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
BASE_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"
VIDEO_SHA256 = "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_u8(tensor: torch.Tensor) -> np.ndarray:
    return np.floor(tensor.detach().cpu().numpy().squeeze().clip(0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def load_models(run_dir: Path, device: torch.device) -> dict[str, FSRCNNSubpixel]:
    entries = {
        "frozen": ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth",
        "fixed_crop_control": run_dir / "fixed_crop_control/candidate_fp32.pth",
        "epoch_resampled_crop": run_dir / "epoch_resampled_crop/candidate_fp32.pth",
    }
    models: dict[str, FSRCNNSubpixel] = {}
    for name, path in entries.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing checkpoint for {name}: {path}")
        saved = torch.load(path, map_location="cpu", weights_only=False)
        model = FSRCNNSubpixel()
        model.load_state_dict(saved["state_dict"], strict=True)
        models[name] = model.to(device).eval()
    return models


def make_set5_samples(set5_dir: Path) -> list[dict]:
    dataset = EvalDataset(set5_dir)
    samples = []
    for index in range(len(dataset)):
        name, lr, hr = dataset[index]
        samples.append({"name": name, "group": "set5_selection_validation",
                        "lr_u8": as_u8(lr), "hr_u8": as_u8(hr), "lr_tensor": lr[None]})
    return samples


def make_video_samples(video: Path) -> list[dict]:
    if file_sha(video) != VIDEO_SHA256:
        raise ValueError("Big Buck Bunny source hash differs from the pinned evaluation source")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    select = r"select=gte(n\,1440)*not(mod(n-1440\,12)),format=rgb24"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", select,
               "-frames:v", "8", "-fps_mode", "passthrough", "-an", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, check=True, timeout=300)
    frame_bytes = 1280 * 720 * 3
    if len(decoded.stdout) != 8 * frame_bytes:
        raise RuntimeError(f"Expected 8 decoded RGB frames, received {len(decoded.stdout) // frame_bytes}")
    samples = []
    for index, source_frame in enumerate(range(1440, 1536, 12)):
        raw = decoded.stdout[index * frame_bytes : (index + 1) * frame_bytes]
        y_image = Image.frombytes("RGB", (1280, 720), raw).convert("YCbCr").getchannel("Y")
        lr_image = y_image.resize((640, 360), Image.Resampling.BICUBIC)
        lr_u8 = np.asarray(lr_image, dtype=np.uint8)
        hr_u8 = np.asarray(y_image, dtype=np.uint8)
        samples.append({"name": f"bbb_{source_frame}", "group": "bbb_temporal_holdout",
                        "lr_u8": lr_u8, "hr_u8": hr_u8,
                        "lr_tensor": torch.from_numpy(lr_u8.astype(np.float32) / 255.0)[None, None]})
    return samples


def score(reference: np.ndarray, prediction: torch.Tensor) -> tuple[float, float]:
    target = torch.from_numpy(reference.astype(np.float32) / 255.0)[None, None]
    return psnr_y(target, prediction.detach().cpu().to(torch.float32), border=2), \
        ssim_y(target, prediction.detach().cpu().to(torch.float32), border=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / ".data/model_optimization/dynamic_crop_ab_20e")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--video", type=Path, default=ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    output_dir = (args.output_dir or run_dir / "evaluation").resolve()
    if file_sha(ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth") != BASE_CHECKPOINT_SHA256:
        parser.error("Frozen baseline checkpoint changed")
    if file_sha(ROOT / "artifacts/quant/quant_params.json") != BASE_QUANT_SHA256:
        parser.error("Frozen baseline quantization parameters changed")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty evaluation directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    set5_dir = args.data_dir.resolve() / "set5"
    samples = make_set5_samples(set5_dir) + make_video_samples(args.video.resolve())
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    models = load_models(run_dir, device)
    quant_dirs = {"frozen": ROOT / "artifacts/quant"}
    calibration_dataset = EvalDataset(set5_dir)
    calibration_samples = [calibration_dataset[i][1].unsqueeze(0) for i in range(len(calibration_dataset))]
    for name in ("fixed_crop_control", "epoch_resampled_crop"):
        quant_dir = run_dir / name / "quantized_candidate"
        if quant_dir.exists() and any(quant_dir.iterdir()):
            parser.error(f"Refusing to overwrite quantized candidate: {quant_dir}")
        quant_dir.mkdir(parents=True, exist_ok=True)
        scales = calibrate_activation_scales(models[name], calibration_samples, device)
        export_quantized_bundle(models[name], scales, quant_dir)
        quant_dirs[name] = quant_dir

    integer_engines = {name: FixedReference(path) for name, path in quant_dirs.items()}
    rows: list[dict] = []
    for sample_index, sample in enumerate(samples, start=1):
        reference = sample["hr_u8"]
        lr = sample["lr_u8"]
        x = sample["lr_tensor"].to(device)
        with torch.inference_mode():
            bicubic = F.interpolate(x, size=reference.shape, mode="bicubic", align_corners=False).clamp(0.0, 1.0).cpu()
            fp_outputs = {name: model(x).clamp(0.0, 1.0).cpu() for name, model in models.items()}
        integer_outputs = {
            name: torch.from_numpy(engine.run(lr)["output"][:, :, 0].astype(np.float32) / 255.0)[None, None]
            for name, engine in integer_engines.items()
        }
        predictions = {"bicubic": bicubic, **{f"{name}_fp32": output for name, output in fp_outputs.items()},
                       **{f"{name}_integer": output for name, output in integer_outputs.items()}}
        row: dict = {"sample": sample["name"], "group": sample["group"]}
        for name, output in predictions.items():
            psnr, ssim = score(reference, output)
            row[f"{name}_psnr_db"] = psnr
            row[f"{name}_ssim"] = ssim
        rows.append(row)
        print(f"{sample_index:02d}/{len(samples)} {sample['name']} done", flush=True)

    metric_names = [key for key in rows[0] if key.endswith(("_psnr_db", "_ssim"))]
    grouped: dict[str, dict] = {}
    for group in sorted({row["group"] for row in rows}):
        subset = [row for row in rows if row["group"] == group]
        grouped[group] = {
            "samples": len(subset),
            **{metric: float(np.mean([row[metric] for row in subset])) for metric in metric_names},
        }
    for group, metrics in grouped.items():
        for prefix in ("frozen", "fixed_crop_control", "epoch_resampled_crop"):
            metrics[f"{prefix}_integer_quant_loss_db"] = (
                metrics[f"{prefix}_fp32_psnr_db"] - metrics[f"{prefix}_integer_psnr_db"]
            )
            metrics[f"{prefix}_integer_gain_vs_bicubic_db"] = (
                metrics[f"{prefix}_integer_psnr_db"] - metrics["bicubic_psnr_db"]
            )
            metrics[f"{prefix}_integer_delta_vs_frozen_db"] = (
                metrics[f"{prefix}_integer_psnr_db"] - metrics["frozen_integer_psnr_db"]
            )

    csv_path = output_dir / "per_sample_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-dynamic-crop-ab-evaluation-v1",
        "status": "EXPLORATORY_SOFTWARE_ONLY",
        "device": str(device),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "baseline_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
        "baseline_quant_params_sha256": BASE_QUANT_SHA256,
        "video_sha256": VIDEO_SHA256,
        "groups": grouped,
        "scope_limits": [
            "Set5 is the fine-tuning checkpoint-selection validation set, not independent evidence.",
            "BBB samples are a small temporal holdout from one animation and may guide this experiment; use a new source for final acceptance.",
            "All values are PC software metrics; no FPGA, RTL, board timing, or real-time claim is made.",
            "Candidate integer outputs use exported INT8/INT16 parameters and the exact integer reference engine.",
        ],
        "per_sample_csv": csv_path.name,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(grouped, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
