from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from member_a.quantization import named_layers
from member_a.metrics import psnr_y
from .activation_int8_reference import (
    ACTIVATION_LIMITS,
    HIDDEN_LAYERS,
    MixedActivationFixedReference,
    activation_scales_from_training,
    export_mixed_activation_bundle,
    qat_forward_mixed,
)
from .candidate_models import HybridFSRCNN, PRESETS
from .hybrid_reference import run_bicubic4x_u8, run_hybrid_float_u8
from .bicubic_reference import resize_keys_u8
from .evaluate_hybrid import _ssim_y_tiled
from .train_candidate import (
    FrameBlockSampler,
    FramePatchDataset,
    _fake_u8,
    _load_manifest_pairs,
    _torch_resize_keys2,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / ".data" / "hybrid_4k_20261006"
DEFAULT_R0 = DATA_ROOT / "train_ffmpeg_R0_adapt_seed456" / "r0_best.pth"
DEFAULT_QAT456 = (
    ROOT
    / "experiments"
    / "hybrid_4k_20261006"
    / "candidate_delivery"
    / "R0_QAT456_seed456_20261007"
    / "training"
    / "r0_qat_best.pth"
)
DEFAULT_TRAIN_DIRS = [
    DATA_ROOT / "ffmpeg_YachtRide_train_pairs",
    DATA_ROOT / "ffmpeg_Beauty_train_pairs",
    DATA_ROOT / "ffmpeg_HoneyBee_train_pairs",
]
DEFAULT_VALIDATION_DIR = DATA_ROOT / "ffmpeg_Jockey_val_pairs"
DEFAULT_TEST_DIRS = [
    DATA_ROOT / "ffmpeg_Bosphorus_test_pairs",
    DATA_ROOT / "ffmpeg_ReadySetGo_test_pairs",
    DATA_ROOT / "ffmpeg_ShakeNDry_test_pairs",
    DATA_ROOT / "uvg_Bosphorus_pairs",
    DATA_ROOT / "uvg_ReadySetGo_pairs",
    DATA_ROOT / "uvg_ShakeNDry_pairs",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_hash(path: Path) -> str:
    return _sha256(path)


def _inside_data(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"Experiment outputs must stay under ignored .data/: {resolved}") from exc
    return resolved


def _load_records(directory: Path) -> list[tuple[dict[str, Any], Path]]:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return [
        ({**record, "sequence": directory.name}, directory / str(record["pair_file"]))
        for record in manifest["pairs"]
    ]


def _tensor_from_pair(path: Path) -> torch.Tensor:
    with np.load(path, allow_pickle=False) as pair:
        values = pair["lr_y"].copy().astype(np.float32) / 255.0
    return torch.from_numpy(values)[None, None]


def _metrics_border(reference: np.ndarray, candidate: np.ndarray, border: int) -> tuple[float, float]:
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("metric inputs must be equal-shaped grayscale images")
    ref = torch.from_numpy(reference.copy()).to(torch.float64)[None, None] / 255.0
    pred = torch.from_numpy(candidate.copy()).to(torch.float64)[None, None] / 255.0
    return psnr_y(ref, pred, border=border), _ssim_y_tiled(reference, candidate, border=border)


def _load_model(checkpoint_path: Path, device: torch.device) -> tuple[HybridFSRCNN, dict, str]:
    checkpoint_path = checkpoint_path.resolve()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(checkpoint_path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model = HybridFSRCNN(PRESETS["R0"])
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    return model, checkpoint, _sha256(checkpoint_path)


def _calibration_subsets(
    train_dirs: list[Path], per_sequence: int = 20
) -> tuple[list[tuple[str, list[Path]]], list[Path]]:
    subsets: list[tuple[str, list[Path]]] = []
    for directory in train_dirs:
        records = _load_records(directory)
        if not records:
            raise ValueError(f"empty training calibration manifest: {directory}")
        count = min(per_sequence, len(records))
        indices = np.linspace(0, len(records) - 1, count, dtype=np.int64).tolist()
        paths = [records[index][1] for index in indices]
        subsets.append((directory.name, paths))
    combined = [path for _name, paths in subsets for path in paths]
    return subsets, combined


def _calibrate(
    model: HybridFSRCNN,
    pair_paths: list[Path],
    bits: dict[str, int],
    device: torch.device,
) -> dict[str, float]:
    samples = [_tensor_from_pair(path) for path in pair_paths]
    model.to(device).eval()
    return activation_scales_from_training(model, samples, bits, device)


def _bit_configs() -> list[tuple[str, dict[str, int]]]:
    configs: list[tuple[str, dict[str, int]]] = [("int16", {name: 16 for name in HIDDEN_LAYERS})]
    for layer in HIDDEN_LAYERS:
        configs.append((f"{layer}_int8", {name: (8 if name == layer else 16) for name in HIDDEN_LAYERS}))
    configs.append(("all_int8", {name: 8 for name in HIDDEN_LAYERS}))
    return configs


def _export_candidate(
    model: HybridFSRCNN,
    bits: dict[str, int],
    calibration_paths: list[Path],
    quant_dir: Path,
    device: torch.device,
) -> tuple[dict[str, float], dict]:
    scales = _calibrate(model, calibration_paths, bits, device)
    quant_dir.mkdir(parents=True, exist_ok=False)
    bundle = export_mixed_activation_bundle(model, scales, bits, quant_dir)
    return scales, bundle


def _integer_image(
    fixed: MixedActivationFixedReference,
    input_u8: np.ndarray,
) -> tuple[np.ndarray, dict[str, dict[str, int | float]]]:
    output = None
    saturation: dict[str, dict[str, int | float]] = {}
    for name, values in fixed.iter_outputs(input_u8):
        if name in HIDDEN_LAYERS:
            layer_spec = next(layer for layer in fixed.spec["layers"] if layer["name"] == name)
            qmin = int(layer_spec["activation_qmin"])
            qmax = int(layer_spec["activation_qmax"])
            count = int(values.size)
            clipped = int(np.count_nonzero((values == qmin) | (values == qmax)))
            saturation[name] = {
                "count": clipped,
                "total": count,
                "ratio": clipped / max(count, 1),
            }
        elif name == "output":
            output = values[:, :, 0].copy()
    if output is None:
        raise RuntimeError("integer reference produced no output image")
    return output, saturation


def _evaluate(
    model: HybridFSRCNN,
    quant_dir: Path,
    records: list[tuple[dict[str, Any], Path]],
    device: torch.device,
    *,
    include_float: bool,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model.to(device).eval()
    fixed = MixedActivationFixedReference(quant_dir)
    rows: list[dict[str, Any]] = []
    sat_totals = {name: {"count": 0, "total": 0} for name in HIDDEN_LAYERS}
    for index, (record, pair_path) in enumerate(records, start=1):
        with np.load(pair_path, allow_pickle=False) as pair:
            lr_y = pair["lr_y"].copy()
            hr_y = pair["hr_y"].copy()
        integer_2x, saturation = _integer_image(fixed, lr_y)
        integer_4x = resize_keys_u8(integer_2x, scale=2, a=-0.5)
        bicubic = run_bicubic4x_u8(lr_y, keys_a=-0.5)
        integer_psnr, integer_ssim = _metrics_border(hr_y, integer_4x, border=8)
        integer_psnr_full, integer_ssim_full = _metrics_border(hr_y, integer_4x, border=0)
        bicubic_psnr, bicubic_ssim = _metrics_border(hr_y, bicubic, border=8)
        bicubic_psnr_full, bicubic_ssim_full = _metrics_border(hr_y, bicubic, border=0)
        row: dict[str, Any] = {
            "variant": label,
            "sequence": record.get("sequence", ""),
            "source_file": str(record["source_file"]),
            "source_sha256": str(record.get("source_sha256", "")),
            "pair_file": pair_path.name,
            "integer_psnr_db_shave8": integer_psnr,
            "integer_ssim_shave8": integer_ssim,
            "integer_psnr_db_full": integer_psnr_full,
            "integer_ssim_full": integer_ssim_full,
            "bicubic_psnr_db_shave8": bicubic_psnr,
            "bicubic_ssim_shave8": bicubic_ssim,
            "bicubic_psnr_db_full": bicubic_psnr_full,
            "bicubic_ssim_full": bicubic_ssim_full,
            "integer_gain_vs_bicubic_db": integer_psnr - bicubic_psnr,
            "integer_gain_vs_bicubic_db_full": integer_psnr_full - bicubic_psnr_full,
        }
        if include_float:
            lr_tensor = torch.from_numpy(lr_y.astype(np.float32) / 255.0)[None, None]
            _middle, float_4x = run_hybrid_float_u8(model, lr_y, keys_a=-0.5, device=device)
            float_psnr, float_ssim = _metrics_border(hr_y, float_4x, border=8)
            float_psnr_full, float_ssim_full = _metrics_border(hr_y, float_4x, border=0)
            row.update(
                {
                    "float_psnr_db_shave8": float_psnr,
                    "float_ssim_shave8": float_ssim,
                    "float_psnr_db_full": float_psnr_full,
                    "float_ssim_full": float_ssim_full,
                    "float_gain_vs_bicubic_db": float_psnr - bicubic_psnr,
                    "float_gain_vs_bicubic_db_full": float_psnr_full - bicubic_psnr_full,
                }
            )
            del lr_tensor
        rows.append(row)
        for name, values in saturation.items():
            sat_totals[name]["count"] += int(values["count"])
            sat_totals[name]["total"] += int(values["total"])
        if index % 5 == 0 or index == len(records):
            print(f"  {label}: {index}/{len(records)}", flush=True)
    for name in HIDDEN_LAYERS:
        sat_totals[name]["ratio"] = sat_totals[name]["count"] / max(sat_totals[name]["total"], 1)
    summary: dict[str, Any] = {"samples": len(rows), "saturation": sat_totals}
    metric_keys = [
        "integer_psnr_db_shave8",
        "integer_ssim_shave8",
        "integer_psnr_db_full",
        "integer_ssim_full",
        "bicubic_psnr_db_shave8",
        "bicubic_ssim_shave8",
        "bicubic_psnr_db_full",
        "bicubic_ssim_full",
        "integer_gain_vs_bicubic_db",
        "integer_gain_vs_bicubic_db_full",
        "float_psnr_db_shave8",
        "float_ssim_shave8",
        "float_psnr_db_full",
        "float_ssim_full",
        "float_gain_vs_bicubic_db",
        "float_gain_vs_bicubic_db_full",
    ]
    summary["means"] = {
        key: float(np.mean([float(row[key]) for row in rows]))
        for key in metric_keys
        if key in rows[0]
    }
    return rows, summary


def _append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_state(path: Path) -> dict[str, torch.Tensor]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    return checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))


def _validate_qat(
    model: HybridFSRCNN,
    loader: DataLoader,
    scales: dict[str, float],
    bits: dict[str, int],
    device: torch.device,
) -> float:
    model.eval()
    total = 0.0
    count = 0
    with torch.no_grad():
        for lr, hr in loader:
            lr = lr.to(device)
            hr = hr.to(device)
            mid = qat_forward_mixed(model, lr, scales, bits)
            pred = _fake_u8(_torch_resize_keys2(mid, a=-0.5))
            margin = 32
            loss = torch.mean((pred[..., margin:-margin, margin:-margin] - hr[..., margin:-margin, margin:-margin]) ** 2)
            total += float(loss.item()) * int(lr.shape[0])
            count += int(lr.shape[0])
    return total / max(count, 1)


def _train_qat(
    initial_model: HybridFSRCNN,
    initial_checkpoint: Path,
    train_dirs: list[Path],
    val_dir: Path,
    calibration_paths: list[Path],
    bits: dict[str, int],
    output_dir: Path,
    device: torch.device,
    *,
    seed: int = 456,
    epochs: int = 5,
) -> tuple[HybridFSRCNN, dict[str, float], Path, list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=False)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.set_num_threads(4)

    train_records = [
        record
        for directory in train_dirs
        for record in _load_manifest_pairs([directory.resolve()])
    ]
    val_records = _load_manifest_pairs([val_dir.resolve()])
    train_dataset = FramePatchDataset(
        train_records, patches_per_frame=2, patch_size=64, seed=seed, training=True
    )
    val_dataset = FramePatchDataset(
        val_records, patches_per_frame=1, patch_size=64, seed=seed, training=False
    )
    sampler = FrameBlockSampler(train_dataset, seed)
    train_loader = DataLoader(train_dataset, batch_size=4, sampler=sampler, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False, num_workers=0)

    initial_state = {
        name: tensor.detach().cpu().clone()
        for name, tensor in initial_model.state_dict().items()
    }
    model = HybridFSRCNN(PRESETS["R0"])
    model.load_state_dict(initial_state, strict=True)
    scales = _calibrate(model, calibration_paths, bits, device)
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-5)
    best_val = math.inf
    best_state = {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}
    history: list[dict[str, Any]] = []
    for epoch in range(epochs):
        train_dataset.set_epoch(epoch)
        sampler.set_epoch(epoch)
        model.train()
        losses: list[float] = []
        for step, (lr, hr) in enumerate(train_loader, start=1):
            lr = lr.to(device, non_blocking=True)
            hr = hr.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            middle = qat_forward_mixed(model, lr, scales, bits)
            predicted = _fake_u8(_torch_resize_keys2(middle, a=-0.5))
            margin = 32
            loss = torch.mean((predicted[..., margin:-margin, margin:-margin] - hr[..., margin:-margin, margin:-margin]) ** 2)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().item()))
            if step % 25 == 0 or step == len(train_loader):
                print(f"  QAT {output_dir.name} epoch {epoch + 1}/{epochs} step {step}/{len(train_loader)}", flush=True)
        val_mse = _validate_qat(model, val_loader, scales, bits, device)
        row = {
            "epoch": epoch + 1,
            "train_mse": float(np.mean(losses)),
            "validation_fake_quant_mse": val_mse,
            "learning_rate": 1.0e-5,
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if val_mse < best_val:
            best_val = val_mse
            best_state = {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}
    model.load_state_dict(best_state, strict=True)
    model.cpu().eval()
    checkpoint_out = output_dir / "activation_qat_best.pth"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "variant": "R0 activation INT8 experimental QAT",
            "config": PRESETS["R0"].to_dict(),
            "seed": seed,
            "epochs_requested": epochs,
            "best_validation_fake_quant_mse": best_val,
            "activation_bits": bits,
            "initial_checkpoint_sha256": _sha256(initial_checkpoint),
            "calibration_manifest_sha256": [
                _json_hash(directory / "manifest.json") for directory in train_dirs
            ],
            "validation_manifest_sha256": _json_hash(val_dir / "manifest.json"),
            "calibration_policy": "training-side only; deterministic 20 frames per training sequence",
        },
        checkpoint_out,
    )
    with (output_dir / "qat_training_log.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(history[0]))
        writer.writeheader()
        writer.writerows(history)
    return model, scales, checkpoint_out, history


def _source_split_audit(train_dirs: list[Path], val_dir: Path, test_dirs: list[Path]) -> dict[str, Any]:
    groups = {
        "train": [record for directory in train_dirs for record, _path in _load_records(directory)],
        "validation": [record for record, _path in _load_records(val_dir)],
        "test": [record for directory in test_dirs for record, _path in _load_records(directory)],
    }
    hashes = {
        name: {str(record.get("source_sha256", "")) for record in records if record.get("source_sha256")}
        for name, records in groups.items()
    }
    intersections = {
        "train_validation": sorted(hashes["train"] & hashes["validation"]),
        "train_test": sorted(hashes["train"] & hashes["test"]),
        "validation_test": sorted(hashes["validation"] & hashes["test"]),
    }
    if any(intersections.values()):
        raise ValueError(f"source-level leakage detected: {intersections}")
    return {
        "pair_rows": {name: len(records) for name, records in groups.items()},
        "unique_source_hashes": {name: len(value) for name, value in hashes.items()},
        "intersections": intersections,
        "test_pair_note": "Different degradation pipelines can contain distinct pairs derived from the same held-out source frame.",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = _inside_data(args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    train_dirs = [path.resolve() for path in args.train_pairs_dir]
    val_dir = args.validation_pairs_dir.resolve()
    test_dirs = [path.resolve() for path in args.test_pairs_dir]
    for directory in [*train_dirs, val_dir, *test_dirs]:
        if not (directory / "manifest.json").is_file():
            raise FileNotFoundError(directory / "manifest.json")
    split_audit = _source_split_audit(train_dirs, val_dir, test_dirs)
    calibration_sets, calibration_paths = _calibration_subsets(train_dirs, per_sequence=20)
    validation_records = _load_records(val_dir)
    test_records = [record for directory in test_dirs for record in _load_records(directory)]
    if args.limit_validation:
        validation_records = validation_records[: args.limit_validation]
    if args.limit_test:
        test_records = test_records[: args.limit_test]

    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"device={device}; output={output_dir}", flush=True)
    print(f"split_audit={json.dumps(split_audit, ensure_ascii=False)}", flush=True)

    model_specs = [
        ("R0", args.r0_checkpoint.resolve()),
        ("QAT456", args.qat456_checkpoint.resolve()),
    ]
    run_manifest: dict[str, Any] = {
        "schema": "member-a-hidden-activation-int8-sweep-v1",
        "status": "EXPERIMENTAL_NOT_FORMAL_A_DELIVERY",
        "device": str(device),
        "activation_format": "signed symmetric per-tensor; INT8 range [-127,127], INT16 range [-32768,32767]",
        "quantization_contract": "INT8 per-output-channel weights; INT32 bias/accumulator; Q1.15 PReLU before requantization; Q31 requantization; nearest ties away from zero",
        "calibration_policy": "training-side only; 20 evenly spaced frames from each of three disjoint training clips",
        "qat_policy": "up to five epochs, only for at most two floating-quality-qualified PTQ variants whose mean PSNR loss versus matched INT16 exceeds 0.10 dB",
        "metric_rule": "Y PSNR/SSIM; both full frame and 8-pixel shave; mean over paired images",
        "models": {},
        "data_split_audit": split_audit,
        "train_manifests": {str(path.name): _json_hash(path / "manifest.json") for path in train_dirs},
        "validation_manifest": {str(val_dir.name): _json_hash(val_dir / "manifest.json")},
        "test_manifests": {str(path.name): _json_hash(path / "manifest.json") for path in test_dirs},
        "limitations": [
            "Software integer reference only; no claim of DSP packing, throughput, RTL, FPGA, or board behavior.",
            "The published QAT456 checkpoint's historical training used validation-derived INT16 activation scales; this run uses training-only calibration for new PTQ/QAT exports, and preserves the provenance caveat for the checkpoint weights.",
            "Test rows from two degradation pipelines may share the same held-out source frame and are not independent source-frame counts.",
        ],
    }
    results_csv = output_dir / "validation_per_image.csv"
    model_objects: dict[str, HybridFSRCNN] = {}
    variants_by_model: dict[str, list[dict[str, Any]]] = {}

    for label, checkpoint_path in model_specs:
        model, checkpoint_meta, checkpoint_hash = _load_model(checkpoint_path, device)
        model_objects[label] = model
        variants_by_model[label] = []
        model_dir = output_dir / label
        model_dir.mkdir()
        print(f"\n[{label}] checkpoint={checkpoint_path.name} sha256={checkpoint_hash}", flush=True)
        model_record: dict[str, Any] = {
            "checkpoint_sha256": checkpoint_hash,
            "checkpoint_source": checkpoint_path.relative_to(ROOT).as_posix() if checkpoint_path.is_relative_to(ROOT) else checkpoint_path.name,
            "checkpoint_epoch": checkpoint_meta.get("epoch", checkpoint_meta.get("best_epoch")),
            "variants": {},
        }
        for variant_name, bits in _bit_configs():
            tag = f"{label}__{variant_name}"
            print(f"[{tag}] calibrating/exporting", flush=True)
            quant_dir = model_dir / variant_name / "quant"
            scales, bundle = _export_candidate(model, bits, calibration_paths, quant_dir, device)
            print(f"[{tag}] evaluating validation", flush=True)
            rows, summary = _evaluate(
                model,
                quant_dir,
                validation_records,
                device,
                include_float=True,
                label=tag,
            )
            variant = {
                "name": variant_name,
                "label": tag,
                "bits": bits,
                "scales": scales,
                "quant_params_sha256": _sha256(quant_dir / "quant_params.json"),
                "summary": summary,
                "rows": rows,
                "qat": False,
                "checkpoint": str(checkpoint_path),
                "checkpoint_sha256": checkpoint_hash,
                "int16_reference_psnr_db": None,
                "psnr_delta_vs_matched_int16_db": None,
            }
            variants_by_model[label].append(variant)
            model_record["variants"][variant_name] = {
                "bits": bits,
                "scales": scales,
                "quant_params_sha256": variant["quant_params_sha256"],
                "summary": summary,
            }
            _append_rows(results_csv, rows)
            del bundle
        int16 = next(item for item in variants_by_model[label] if item["name"] == "int16")
        int16_psnr = int16["summary"]["means"]["integer_psnr_db_shave8"]
        int16_ssim = int16["summary"]["means"]["integer_ssim_shave8"]
        for variant in variants_by_model[label]:
            means = variant["summary"]["means"]
            variant["int16_reference_psnr_db"] = int16_psnr
            variant["psnr_delta_vs_matched_int16_db"] = means["integer_psnr_db_shave8"] - int16_psnr
            variant["ssim_delta_vs_matched_int16"] = means["integer_ssim_shave8"] - int16_ssim
            model_record["variants"][variant["name"]]["psnr_delta_vs_matched_int16_db"] = variant["psnr_delta_vs_matched_int16_db"]
            model_record["variants"][variant["name"]]["ssim_delta_vs_matched_int16"] = variant["ssim_delta_vs_matched_int16"]
        float_means = int16["summary"]["means"]
        model_record["floating_quality_gate"] = {
            "float_gain_vs_bicubic_db": float_means["float_gain_vs_bicubic_db"],
            "float_ssim_delta_vs_bicubic": float_means["float_ssim_shave8"] - float_means["bicubic_ssim_shave8"],
            "passes": (
                float_means["float_gain_vs_bicubic_db"] >= 0.20
                and float_means["float_ssim_shave8"] >= float_means["bicubic_ssim_shave8"]
            ),
        }
        run_manifest["models"][label] = model_record

    # QAT only the two best floating-quality candidates whose PTQ loss exceeds budget.
    qat_candidates: list[tuple[float, float, str, dict[str, Any]]] = []
    for label in model_objects:
        fp_pass = bool(run_manifest["models"][label]["floating_quality_gate"]["passes"])
        if not fp_pass:
            continue
        for variant in variants_by_model[label]:
            if variant["name"] == "int16":
                continue
            if variant["psnr_delta_vs_matched_int16_db"] < -0.10:
                fp_psnr = variant["summary"]["means"]["float_psnr_db_shave8"]
                qat_candidates.append((fp_psnr, variant["psnr_delta_vs_matched_int16_db"], label, variant))
    qat_candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]["name"]))
    selected_qat = qat_candidates[: args.qat_max_candidates]
    run_manifest["qat_candidates"] = []
    for _fp_psnr, _ptq_delta, label, source_variant in selected_qat:
        print(f"\n[QAT] {label}/{source_variant['name']} triggered by {source_variant['psnr_delta_vs_matched_int16_db']:.4f} dB", flush=True)
        initial_checkpoint = Path(source_variant["checkpoint"])
        qat_dir = output_dir / label / f"qat_{source_variant['name']}"
        qat_model, _initial_scales, qat_checkpoint, qat_history = _train_qat(
            model_objects[label],
            initial_checkpoint,
            train_dirs,
            val_dir,
            calibration_paths,
            source_variant["bits"],
            qat_dir,
            device,
            epochs=args.qat_epochs,
        )
        model_objects[f"{label}_{source_variant['name']}_QAT"] = qat_model
        qat_scales = _calibrate(qat_model, calibration_paths, source_variant["bits"], device)
        candidate_record: dict[str, Any] = {
            "name": f"{source_variant['name']}_qat5",
            "label": f"{label}__{source_variant['name']}_qat5",
            "bits": source_variant["bits"],
            "checkpoint": str(qat_checkpoint),
            "checkpoint_sha256": _sha256(qat_checkpoint),
            "qat": True,
            "qat_history": qat_history,
            "scales": qat_scales,
        }
        # Re-evaluate matched INT16 and the requested mixed-width configuration for the post-QAT weights.
        for eval_name, eval_bits in (
            ("int16", {name: 16 for name in HIDDEN_LAYERS}),
            ("mixed", source_variant["bits"]),
        ):
            eval_scales = _calibrate(qat_model, calibration_paths, eval_bits, device)
            qdir = qat_dir / f"postqat_{eval_name}_quant"
            qdir.mkdir(exist_ok=False)
            export_mixed_activation_bundle(qat_model, eval_scales, eval_bits, qdir)
            qrows, qsummary = _evaluate(
                qat_model,
                qdir,
                validation_records,
                device,
                include_float=True,
                label=f"{candidate_record['label']}__{eval_name}",
            )
            _append_rows(results_csv, qrows)
            candidate_record[f"{eval_name}_summary"] = qsummary
            candidate_record[f"{eval_name}_rows"] = qrows
            candidate_record[f"{eval_name}_quant_params_sha256"] = _sha256(qdir / "quant_params.json")
        candidate_record["psnr_delta_vs_matched_int16_db"] = (
            candidate_record["mixed_summary"]["means"]["integer_psnr_db_shave8"]
            - candidate_record["int16_summary"]["means"]["integer_psnr_db_shave8"]
        )
        candidate_record["ssim_delta_vs_matched_int16"] = (
            candidate_record["mixed_summary"]["means"]["integer_ssim_shave8"]
            - candidate_record["int16_summary"]["means"]["integer_ssim_shave8"]
        )
        run_manifest["qat_candidates"].append(candidate_record)

    # Freeze one choice per model using validation only; test is run once after this point.
    selections: dict[str, dict[str, Any]] = {}
    for label in model_objects:
        if label not in variants_by_model:
            continue
        options: list[dict[str, Any]] = []
        for variant in variants_by_model[label]:
            if variant["name"] == "int16":
                continue
            variant["postqat"] = False
            options.append(variant)
        for candidate in run_manifest["qat_candidates"]:
            if candidate["label"].startswith(f"{label}__"):
                candidate["postqat"] = True
                options.append(candidate)
        qualified = [item for item in options if item["psnr_delta_vs_matched_int16_db"] >= -0.10]
        pool = qualified or options
        if not pool:
            selected = next(item for item in variants_by_model[label] if item["name"] == "int16")
            selected["postqat"] = False
            selected["qualified"] = False
            selected["name"] = "int16_no_int8_candidate"
        else:
            def _rank(item: dict[str, Any]) -> tuple[int, float, float, str]:
                bit_count = sum(1 for width in item["bits"].values() if width == 8)
                if item.get("postqat"):
                    means = item["mixed_summary"]["means"]
                else:
                    means = item["summary"]["means"]
                return (
                    bit_count,
                    float(means["integer_psnr_db_shave8"]),
                    float(item["psnr_delta_vs_matched_int16_db"]),
                    str(item["name"]),
                )
            if qualified:
                selected = max(pool, key=_rank)
            else:
                selected = max(
                    pool,
                    key=lambda item: (
                        float(item["psnr_delta_vs_matched_int16_db"]),
                        float(
                            item["mixed_summary"]["means"]["integer_psnr_db_shave8"]
                            if item.get("postqat")
                            else item["summary"]["means"]["integer_psnr_db_shave8"]
                        ),
                        str(item["name"]),
                    ),
                )
            selected["qualified"] = selected in qualified
        selections[label] = selected
        run_manifest["models"][label]["selected_by_validation"] = {
            "name": selected["name"],
            "bits": selected["bits"],
            "qualified": selected["qualified"],
            "psnr_delta_vs_matched_int16_db": selected["psnr_delta_vs_matched_int16_db"],
        }
        print(f"\n[{label}] selected by validation: {selected['name']} qualified={selected['qualified']}", flush=True)

    # Calibration-source sensitivity is diagnostic only; it cannot change the frozen validation choice.
    run_manifest["calibration_sensitivity"] = {}
    for label, selected in selections.items():
        if selected["name"] == "int16_no_int8_candidate":
            continue
        if selected.get("postqat"):
            selected_model = model_objects[f"{label}_{selected['name'].removesuffix('_qat5')}_QAT"]
        else:
            selected_model = model_objects[label]
        sensitivity: dict[str, Any] = {}
        for sequence_name, paths in calibration_sets:
            bit_config = selected["bits"]
            group_dir = output_dir / label / "calibration_sensitivity" / f"{sequence_name}_{selected['name']}"
            group_dir.mkdir(parents=True, exist_ok=False)
            group_result: dict[str, Any] = {}
            for eval_name, eval_bits in (
                ("matched_int16", {name: 16 for name in HIDDEN_LAYERS}),
                ("selected_activation_width", bit_config),
            ):
                qdir = group_dir / eval_name
                qdir.mkdir()
                scales = _calibrate(selected_model, paths, eval_bits, device)
                export_mixed_activation_bundle(selected_model, scales, eval_bits, qdir)
                rows, summary = _evaluate(
                    selected_model,
                    qdir,
                    validation_records,
                    device,
                    include_float=False,
                    label=f"{label}__calib_{sequence_name}__{eval_name}",
                )
                _append_rows(results_csv, rows)
                group_result[eval_name] = {
                    "scales": scales,
                    "summary": summary,
                    "quant_params_sha256": _sha256(qdir / "quant_params.json"),
                }
            group_result["psnr_delta_vs_matched_int16_db"] = (
                group_result["selected_activation_width"]["summary"]["means"]["integer_psnr_db_shave8"]
                - group_result["matched_int16"]["summary"]["means"]["integer_psnr_db_shave8"]
            )
            group_result["ssim_delta_vs_matched_int16"] = (
                group_result["selected_activation_width"]["summary"]["means"]["integer_ssim_shave8"]
                - group_result["matched_int16"]["summary"]["means"]["integer_ssim_shave8"]
            )
            sensitivity[sequence_name] = group_result
        run_manifest["calibration_sensitivity"][label] = sensitivity

    # Blind holdout evaluation after model/config choices are frozen.
    run_manifest["holdout_test"] = {}
    test_csv = output_dir / "holdout_test_per_image.csv"
    for label, selected in selections.items():
        if selected["name"] == "int16_no_int8_candidate":
            continue
        if selected.get("postqat"):
            selected_model = model_objects[f"{label}_{selected['name'].removesuffix('_qat5')}_QAT"]
            bits = selected["bits"]
            chosen_scales = _calibrate(selected_model, calibration_paths, bits, device)
            baseline_bits = {name: 16 for name in HIDDEN_LAYERS}
            baseline_scales = _calibrate(selected_model, calibration_paths, baseline_bits, device)
        else:
            selected_model = model_objects[label]
            bits = selected["bits"]
            chosen_scales = selected["scales"]
            baseline_bits = {name: 16 for name in HIDDEN_LAYERS}
            baseline_variant = next(item for item in variants_by_model[label] if item["name"] == "int16")
            baseline_scales = baseline_variant["scales"]
        holdout_result: dict[str, Any] = {
            "selected_candidate": selected["name"],
            "qualified_on_validation": bool(selected["qualified"]),
            "bitwidths": bits,
            "samples": len(test_records),
        }
        for test_name, eval_bits, eval_scales in (
            ("matched_int16", baseline_bits, baseline_scales),
            ("selected_activation_width", bits, chosen_scales),
        ):
            qdir = output_dir / label / "holdout" / test_name / "quant"
            qdir.parent.mkdir(parents=True, exist_ok=True)
            qdir.mkdir(exist_ok=False)
            export_mixed_activation_bundle(selected_model, eval_scales, eval_bits, qdir)
            rows, summary = _evaluate(
                selected_model,
                qdir,
                test_records,
                device,
                include_float=False,
                label=f"{label}__{selected['name']}__{test_name}",
            )
            _append_rows(test_csv, rows)
            holdout_result[test_name] = {
                "summary": summary,
                "quant_params_sha256": _sha256(qdir / "quant_params.json"),
            }
        holdout_result["psnr_delta_vs_matched_int16_db"] = (
            holdout_result["selected_activation_width"]["summary"]["means"]["integer_psnr_db_shave8"]
            - holdout_result["matched_int16"]["summary"]["means"]["integer_psnr_db_shave8"]
        )
        holdout_result["ssim_delta_vs_matched_int16"] = (
            holdout_result["selected_activation_width"]["summary"]["means"]["integer_ssim_shave8"]
            - holdout_result["matched_int16"]["summary"]["means"]["integer_ssim_shave8"]
        )
        run_manifest["holdout_test"][label] = holdout_result

    _save_json(output_dir / "run_manifest.json", run_manifest)
    print(json.dumps({"output_dir": str(output_dir), "holdout_test": run_manifest["holdout_test"]}, indent=2, ensure_ascii=False), flush=True)
    return run_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="A-side INT8 hidden-activation PTQ/QAT sensitivity experiment")
    parser.add_argument("--r0-checkpoint", type=Path, default=DEFAULT_R0)
    parser.add_argument("--qat456-checkpoint", type=Path, default=DEFAULT_QAT456)
    parser.add_argument("--train-pairs-dir", type=Path, action="append", default=None)
    parser.add_argument("--validation-pairs-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--test-pairs-dir", type=Path, action="append", default=None)
    parser.add_argument("--output-dir", type=Path, default=DATA_ROOT / "activation_int8_20261007")
    parser.add_argument("--limit-validation", type=int, default=0, help="nonzero is for smoke/debug only")
    parser.add_argument("--limit-test", type=int, default=0, help="nonzero is for smoke/debug only")
    parser.add_argument("--qat-max-candidates", type=int, default=2, help="normally 2; set 0 only for smoke/debug")
    parser.add_argument("--qat-epochs", type=int, default=5, help="plan requires 5; smaller values are for smoke/debug only")
    args = parser.parse_args()
    if args.limit_validation < 0 or args.limit_test < 0 or args.qat_max_candidates < 0 or args.qat_epochs <= 0:
        raise ValueError("limits and QAT candidate count must be nonnegative; QAT epochs must be positive")
    args.train_pairs_dir = args.train_pairs_dir or DEFAULT_TRAIN_DIRS
    args.test_pairs_dir = args.test_pairs_dir or DEFAULT_TEST_DIRS
    run(args)


if __name__ == "__main__":
    main()
