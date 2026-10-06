from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import zlib

import numpy as np
import torch

from member_a.artifacts import generate_fixed_vectors
from member_a.fixed_reference import FixedReference
from member_a.quantization import calibrate_activation_scales, export_quantized_bundle
from member_a.metrics import psnr_y
from .candidate_models import HybridFSRCNN, PRESETS
from .bicubic_reference import resize_keys_u8
from .evaluate_hybrid import _ssim_y_tiled
from .hybrid_reference import run_bicubic4x_u8, run_hybrid_float_u8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_pairs(directory: Path) -> list[tuple[dict[str, str], Path]]:
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [(record, directory / str(record["pair_file"])) for record in manifest["pairs"]]


def _tensor_from_lr(pair_path: Path) -> torch.Tensor:
    with np.load(pair_path, allow_pickle=False) as pair:
        values = pair["lr_y"].copy()
    return torch.from_numpy(values.astype(np.float32) / 255.0)[None, None]


def _metrics_border(reference: np.ndarray, candidate: np.ndarray, border: int) -> tuple[float, float]:
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("Metric inputs must be equal-shaped Y images")
    ref = torch.from_numpy(reference.copy()).to(torch.float64)[None, None] / 255.0
    pred = torch.from_numpy(candidate.copy()).to(torch.float64)[None, None] / 255.0
    return psnr_y(ref, pred, border=border), _ssim_y_tiled(reference, candidate, border=border)


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float]:
    """Plan-compatible center-crop metrics (8-pixel shave)."""
    return _metrics_border(reference, candidate, border=8)


def _inside_data(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Candidate quantization outputs must remain under ignored .data/: {resolved}") from exc
    return resolved


def export_candidate_quantized_bundle(model: HybridFSRCNN, variant: str, activation_scales: dict[str, float], output_dir: Path) -> dict:
    """Export an experimental architecture without mislabeling non-R0 candidates as the frozen model."""
    if variant not in PRESETS:
        raise ValueError(f"Unknown candidate variant: {variant}")
    bundle = export_quantized_bundle(model, activation_scales, output_dir)
    if variant != "R0":
        config = PRESETS[variant]
        bundle["model"] = (
            f"HybridFSRCNN-{variant}-d{config.d}-s{config.s}-m{config.m}-c{config.c}-head{config.head_kernel}x{config.head_kernel}"
        )
        bundle["candidate_config"] = config.to_dict()
        (output_dir / "quant_params.json").write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantize experimental candidate models and evaluate with the integer reference")
    parser.add_argument("--variant", choices=sorted(PRESETS), default="R0")
    parser.add_argument("--candidate", action="append", required=True, help="Candidate name=checkpoint path; repeatable")
    parser.add_argument("--calibration-pairs-dir", type=Path, required=True)
    parser.add_argument("--test-pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--keys-a", type=float, choices=(-0.5, -0.75), default=-0.5)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = _inside_data(args.output_dir, repo_root)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    calibration_dir = args.calibration_pairs_dir.resolve()
    calibration_records = _load_pairs(calibration_dir)
    test_sets = [(directory.resolve(), _load_pairs(directory.resolve())) for directory in args.test_pairs_dir]
    if not calibration_records or not test_sets:
        raise ValueError("Calibration and test sets must not be empty")

    candidates: list[tuple[str, Path]] = []
    for item in args.candidate:
        name, separator, checkpoint = item.partition("=")
        if not separator or not name or not checkpoint:
            raise ValueError(f"Candidate must be NAME=CHECKPOINT, got: {item}")
        checkpoint_path = Path(checkpoint).resolve()
        if not checkpoint_path.is_file():
            raise FileNotFoundError(checkpoint_path)
        candidates.append((name, checkpoint_path))
    names = [name for name, _ in candidates]
    if len(set(names)) != len(names) or any(not name.replace("_", "").isalnum() for name in names):
        raise ValueError("Candidate names must be unique and contain only letters, digits and underscores")

    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results: dict[str, object] = {}
    calibration_manifest = calibration_dir / "manifest.json"
    test_manifest_digests = {str(directory): _sha256(directory / "manifest.json") for directory, _ in test_sets}

    for name, checkpoint_path in candidates:
        candidate_dir = output_dir / name
        quant_dir = candidate_dir / "quant"
        vectors_dir = candidate_dir / "test_vectors"
        candidate_dir.mkdir(parents=True)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
        model = HybridFSRCNN(PRESETS[args.variant])
        model.load_state_dict(state, strict=True)
        model.to(device).eval()

        calibration_samples = [_tensor_from_lr(path) for _, path in calibration_records]
        scales = calibrate_activation_scales(model, calibration_samples, device)
        export_candidate_quantized_bundle(model, args.variant, scales, quant_dir)
        generate_fixed_vectors(quant_dir, vectors_dir)
        fixed = FixedReference(quant_dir)

        rows: list[dict[str, float | int | str]] = []
        for source_dir, records in test_sets:
            for record, pair_path in records:
                with np.load(pair_path, allow_pickle=False) as pair:
                    lr_y = pair["lr_y"].copy()
                    hr_y = pair["hr_y"].copy()
                _, float_final = run_hybrid_float_u8(model, lr_y, keys_a=args.keys_a, device=device)
                bicubic_final = run_bicubic4x_u8(lr_y, keys_a=args.keys_a)
                integer_output = None
                for layer_name, values in fixed.iter_outputs(lr_y):
                    if layer_name == "output":
                        integer_output = values[:, :, 0].copy()
                if integer_output is None:
                    raise RuntimeError("Integer reference did not emit the output layer")
                integer_final = resize_keys_u8(integer_output, scale=2, a=args.keys_a)
                if integer_final.shape != hr_y.shape:
                    raise ValueError(f"Integer output {integer_final.shape} does not match HR {hr_y.shape}")
                float_psnr, float_ssim = _metrics(hr_y, float_final)
                integer_psnr, integer_ssim = _metrics(hr_y, integer_final)
                cubic_psnr, cubic_ssim = _metrics(hr_y, bicubic_final)
                float_psnr_full, float_ssim_full = _metrics_border(hr_y, float_final, border=0)
                integer_psnr_full, integer_ssim_full = _metrics_border(hr_y, integer_final, border=0)
                cubic_psnr_full, cubic_ssim_full = _metrics_border(hr_y, bicubic_final, border=0)
                rows.append(
                    {
                        "sequence": source_dir.name,
                        "image": str(record["source_file"]),
                        "float_psnr_db": float_psnr,
                        "integer_psnr_db": integer_psnr,
                        "integer_psnr_loss_vs_float_db": float_psnr - integer_psnr,
                        "float_ssim": float_ssim,
                        "integer_ssim": integer_ssim,
                        "bicubic_psnr_db": cubic_psnr,
                        "bicubic_ssim": cubic_ssim,
                        "integer_gain_vs_bicubic_db": integer_psnr - cubic_psnr,
                        "float_psnr_db_full": float_psnr_full,
                        "integer_psnr_db_full": integer_psnr_full,
                        "integer_psnr_loss_vs_float_db_full": float_psnr_full - integer_psnr_full,
                        "float_ssim_full": float_ssim_full,
                        "integer_ssim_full": integer_ssim_full,
                        "bicubic_psnr_db_full": cubic_psnr_full,
                        "bicubic_ssim_full": cubic_ssim_full,
                        "integer_gain_vs_bicubic_db_full": integer_psnr_full - cubic_psnr_full,
                    }
                )

        candidate_eval_dir = candidate_dir / "evaluation"
        candidate_eval_dir.mkdir()
        csv_path = candidate_eval_dir / "per_image_metrics.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

        quant_files = {
            path.relative_to(quant_dir).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "crc32": f"{zlib.crc32(path.read_bytes()) & 0xFFFFFFFF:08x}",
            }
            for path in sorted(quant_dir.rglob("*"))
            if path.is_file()
        }
        candidate_summary = {
            "status": "EXPERIMENTAL_INTEGER_REFERENCE_NOT_FORMAL_DELIVERY",
            "variant": f"{args.variant} d{PRESETS[args.variant].d}/s{PRESETS[args.variant].s}/m{PRESETS[args.variant].m}/c{PRESETS[args.variant].c} head{PRESETS[args.variant].head_kernel}x{PRESETS[args.variant].head_kernel}",
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": _sha256(checkpoint_path),
            "quantization": "INT8 per-output-channel weights; INT16 calibrated per-layer activations; INT32 bias/accumulator; Q1.15 PReLU; Q31 requantization",
            "rounding": "nearest ties away from zero; explicit saturation in FixedReference",
            "calibration_manifest": str(calibration_manifest),
            "calibration_manifest_sha256": _sha256(calibration_manifest),
            "calibration_samples": len(calibration_samples),
            "activation_scales": scales,
            "test_manifest_sha256": test_manifest_digests,
            "samples": len(rows),
            "means": {
                key: float(np.mean([float(row[key]) for row in rows]))
                for key in [
                    "float_psnr_db",
                    "integer_psnr_db",
                    "integer_psnr_loss_vs_float_db",
                    "float_ssim",
                    "integer_ssim",
                    "bicubic_psnr_db",
                    "bicubic_ssim",
                    "integer_gain_vs_bicubic_db",
                    "float_psnr_db_full",
                    "integer_psnr_db_full",
                    "integer_psnr_loss_vs_float_db_full",
                    "float_ssim_full",
                    "integer_ssim_full",
                    "bicubic_psnr_db_full",
                    "bicubic_ssim_full",
                    "integer_gain_vs_bicubic_db_full",
                ]
            },
            "metric_rule": "Y PSNR/SSIM; report both full frame (border=0) and center crop (8-pixel shave); arithmetic mean over paired images",
            "quant_files": quant_files,
            "per_image_metrics": str(csv_path),
            "test_vectors": str(vectors_dir),
            "limitations": [
                "This candidate-specific calibration and test set are experimental and do not replace the frozen A integer assets or Golden.",
                "Metrics use 25 lossy UVG HEVC-derived Y frames with synthetic FFmpeg degradation; not camera-original truth.",
                "No B RTL bit-exact test, FPGA implementation, board test, or real-time claim is included.",
            ],
        }
        summary_path = candidate_eval_dir / "summary.json"
        summary_path.write_text(json.dumps(candidate_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        all_results[name] = candidate_summary
        del model, fixed
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    top_summary = {
        "schema": "member-a-candidate-integer-cross-evaluation-v1",
        "status": "EXPERIMENTAL_NOT_FORMAL_A_DELIVERY",
        "device": str(device),
        "keys_a": args.keys_a,
        "results": all_results,
    }
    (output_dir / "summary.json").write_text(json.dumps(top_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({name: result["means"] for name, result in all_results.items()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
