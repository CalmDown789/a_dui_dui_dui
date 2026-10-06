from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from member_a.metrics import psnr_y
from .candidate_models import HybridFSRCNN, PRESETS
from .hybrid_reference import run_bicubic4x_u8, run_hybrid_float_u8


def _ssim_y_tiled(reference: np.ndarray, candidate: np.ndarray, border: int = 8, tile_rows: int = 128) -> float:
    """Compute the project's Gaussian-window SSIM in row tiles to cap memory."""
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("SSIM inputs must be equal-shaped grayscale arrays")
    if border < 0 or reference.shape[0] <= border * 2 or reference.shape[1] <= border * 2:
        raise ValueError("Invalid SSIM border")
    reference = reference[border:-border, border:-border] if border else reference
    candidate = candidate[border:-border, border:-border] if border else candidate
    coords = torch.arange(11, dtype=torch.float64) - 5
    kernel_1d = torch.exp(-(coords**2) / (2 * 1.5**2))
    kernel_1d /= kernel_1d.sum()
    vertical_kernel = kernel_1d.view(1, 1, 11, 1).expand(5, 1, 11, 1).contiguous()
    horizontal_kernel = kernel_1d.view(1, 1, 1, 11).expand(5, 1, 1, 11).contiguous()
    height = reference.shape[0]
    score_sum = 0.0
    for core_start in range(0, height, tile_rows):
        core_end = min(core_start + tile_rows, height)
        halo_start = max(0, core_start - 5)
        halo_end = min(height, core_end + 5)
        ref = torch.from_numpy(np.ascontiguousarray(reference[halo_start:halo_end])).to(torch.float64)[None, None] / 255.0
        pred = torch.from_numpy(np.ascontiguousarray(candidate[halo_start:halo_end])).to(torch.float64)[None, None] / 255.0
        moments = torch.cat((ref, pred, ref * ref, pred * pred, ref * pred), dim=1)
        filtered = F.conv2d(moments, vertical_kernel, groups=5, padding=(5, 0))
        filtered = F.conv2d(filtered, horizontal_kernel, groups=5, padding=(0, 5))
        mu_x, mu_y = filtered[:, 0:1], filtered[:, 1:2]
        sigma_x = filtered[:, 2:3] - mu_x * mu_x
        sigma_y = filtered[:, 3:4] - mu_y * mu_y
        sigma_xy = filtered[:, 4:5] - mu_x * mu_y
        c1 = 0.01**2
        c2 = 0.03**2
        numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
        denominator = (mu_x * mu_x + mu_y * mu_y + c1) * (sigma_x + sigma_y + c2)
        tile = numerator / denominator.clamp_min(1.0e-15)
        core_offset = core_start - halo_start
        core = tile[..., core_offset : core_offset + (core_end - core_start), :]
        score_sum += float(core.sum().item())
    return score_sum / (reference.shape[0] * reference.shape[1])


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float]:
    ref = torch.from_numpy(reference.copy()).to(torch.float64)[None, None] / 255.0
    pred = torch.from_numpy(candidate.copy()).to(torch.float64)[None, None] / 255.0
    return psnr_y(ref, pred, border=8), _ssim_y_tiled(reference, candidate, border=8)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the 540p-to-hybrid-4K software reference")
    parser.add_argument("--pairs-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--variant", choices=PRESETS, default="R0")
    parser.add_argument("--keys-a", type=float, choices=(-0.5, -0.75), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    manifest_path = args.pairs_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["pairs"][: args.limit] if args.limit > 0 else manifest["pairs"]
    if not records:
        raise ValueError("No evaluation pairs found")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = HybridFSRCNN(PRESETS[args.variant])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint)
    model.load_state_dict(state, strict=True)
    model.to(device).eval()

    rows: list[dict[str, float | str]] = []
    for record in records:
        pair_path = args.pairs_dir / str(record["pair_file"])
        with np.load(pair_path, allow_pickle=False) as pair:
            hr_y = pair["hr_y"]
            lr_y = pair["lr_y"]
        hybrid_mid, hybrid_final = run_hybrid_float_u8(model, lr_y, keys_a=args.keys_a, device=device)
        bicubic_final = run_bicubic4x_u8(lr_y, keys_a=args.keys_a)
        if hybrid_final.shape != (2160, 3840) or bicubic_final.shape != hr_y.shape:
            raise ValueError(f"Unexpected final image shape for {record['source_file']}")
        hybrid_psnr, hybrid_ssim = _metrics(hr_y, hybrid_final)
        cubic_psnr, cubic_ssim = _metrics(hr_y, bicubic_final)
        rows.append(
            {
                "image": str(record["source_file"]),
                "bicubic4x_psnr_db": cubic_psnr,
                "bicubic4x_ssim": cubic_ssim,
                "hybrid_psnr_db": hybrid_psnr,
                "hybrid_ssim": hybrid_ssim,
                "hybrid_delta_vs_bicubic_db": hybrid_psnr - cubic_psnr,
                "intermediate_1080p_min": int(hybrid_mid.min()),
                "intermediate_1080p_max": int(hybrid_mid.max()),
            }
        )

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Evaluation outputs must stay under ignored .data/: {output_dir}") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "per_image_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-hybrid-4k-software-evaluation-v1",
        "status": "FLOAT_SOFTWARE_REFERENCE_NOT_INTEGER_OR_BOARD_ACCEPTANCE",
        "pair_manifest": str(manifest_path),
        "pair_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "model_variant": args.variant,
        "model_config": PRESETS[args.variant].to_dict(),
        "checkpoint": str(args.checkpoint.resolve()),
        "device": str(device),
        "keys_a": args.keys_a,
        "coordinate_rule": "half-pixel",
        "edge_rule": "edge replication",
        "intermediate_rule": "FSRCNN FP32 output rounded ties-away to uint8 before bicubic x2",
        "final_rule": "bicubic float64; final round ties-away from zero; saturate to uint8",
        "metric_rule": "Y PSNR/SSIM, border=8 pixels, arithmetic mean over images",
        "samples": len(rows),
        "means": {
            key: float(np.mean([float(row[key]) for row in rows]))
            for key in ["bicubic4x_psnr_db", "bicubic4x_ssim", "hybrid_psnr_db", "hybrid_ssim", "hybrid_delta_vs_bicubic_db"]
        },
        "per_image_csv": str(csv_path),
        "limitations": [
            "FP32 software reference only; not the integer interpolation path or FPGA evidence.",
            "The synthetic x4 LR degradation and Keys upsampling kernels are experimental contracts and must be frozen by A/B before final comparison.",
            "No claim about 540p60, 4K60, resources, or timing follows from these PSNR results.",
        ],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["means"], indent=2))


if __name__ == "__main__":
    main()
