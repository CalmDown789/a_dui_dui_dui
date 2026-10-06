"""Measure hidden INT16 range coverage on the development video frames."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import EvalDataset
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y
from member_a.model import FSRCNNSubpixel
from member_a.quantization import INT16_MAX, quantized_forward_float
from evaluate_dynamic_crop_ab import make_video_samples, load_models


def load_scales(path: Path) -> dict[str, float]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    return {layer["name"]: float(layer["output_scale"])
            for layer in spec["layers"] if layer["name"] != "subpixel"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / ".data/model_optimization/dynamic_crop_ab_20e")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--video", type=Path, default=ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    models = load_models(args.run_dir.resolve(), device)
    candidates = {
        "frozen": (models["frozen"], ROOT / "artifacts/quant/quant_params.json"),
        "fixed_crop_control": (models["fixed_crop_control"], args.run_dir / "fixed_crop_control/quantized_candidate/quant_params.json"),
        "epoch_resampled_crop": (models["epoch_resampled_crop"], args.run_dir / "epoch_resampled_crop/quantized_candidate/quant_params.json"),
    }
    video = make_video_samples(args.video.resolve())
    result: dict[str, dict] = {}
    for name, (model, spec_path) in candidates.items():
        scales = load_scales(spec_path)
        per_layer: dict[str, list[float]] = {layer: [] for layer in scales}
        bundle_dir = spec_path.parent
        integer = FixedReference(bundle_dir)
        qdq_psnr: list[float] = []
        integer_psnr: list[float] = []
        for sample in video:
            tensor = sample["lr_tensor"].to(device)
            with torch.inference_mode():
                stages = model.forward_with_intermediates(tensor)
                qdq = quantized_forward_float(model, tensor, scales).clamp(0.0, 1.0).cpu()
            for layer, scale in scales.items():
                values = stages[layer].abs()
                per_layer[layer].append(float(values.max().item() / (scale * INT16_MAX)))
            ref = torch.from_numpy(sample["hr_u8"].astype(np.float32) / 255.0)[None, None]
            qdq_psnr.append(psnr_y(ref, qdq, border=2))
            int_image = integer.run(sample["lr_u8"])["output"][:, :, 0]
            int_tensor = torch.from_numpy(int_image.astype(np.float32) / 255.0)[None, None]
            integer_psnr.append(psnr_y(ref, int_tensor, border=2))
        result[name] = {
            "scales": scales,
            "bbb_mean_qdq_psnr_db": float(np.mean(qdq_psnr)),
            "bbb_mean_integer_psnr_db": float(np.mean(integer_psnr)),
            "integer_minus_qdq_db": float(np.mean(integer_psnr) - np.mean(qdq_psnr)),
            "video_max_abs_over_int16_fullscale_by_layer": {
                layer: {"max": max(ratios), "mean_frame_max": float(np.mean(ratios))}
                for layer, ratios in per_layer.items()
            },
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
