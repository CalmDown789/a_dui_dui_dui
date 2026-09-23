from __future__ import annotations

from pathlib import Path
import json

import torch

from .artifacts import (
    generate_fixed_vectors,
    generate_full_integer_golden,
    generate_full_reference,
    write_delivery_manifest,
    write_metrics,
    write_model_contract,
)
from .data import EvalDataset, download_datasets
from .model import FSRCNNSubpixel
from .quantization import calibrate_activation_scales, export_quantized_bundle
from .training import evaluate_model, qat_finetune, train_fp32


def _calibration_samples(dataset: EvalDataset, limit: int = 5) -> list[torch.Tensor]:
    return [dataset[index][1].unsqueeze(0) for index in range(min(len(dataset), limit))]


def run_pipeline(
    root: Path,
    data_dir: Path,
    max_epochs: int = 50,
    min_epochs: int = 20,
    patience: int = 10,
    force_train: bool = False,
) -> dict:
    root = root.resolve()
    artifacts = root / "artifacts"
    model_dir = artifacts / "model"
    quant_dir = artifacts / "quant"
    evaluation_dir = artifacts / "evaluation"
    vectors_dir = artifacts / "test_vectors"
    full_reference_dir = artifacts / "full_reference"
    full_integer_dir = artifacts / "full_integer_golden"
    download_datasets(data_dir)
    train_file = data_dir / "t91"
    eval_file = data_dir / "set5"
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = FSRCNNSubpixel().to(device)
    checkpoint = model_dir / "fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    if checkpoint.exists() and not force_train:
        saved = torch.load(checkpoint, map_location=device, weights_only=False)
        model.load_state_dict(saved["state_dict"])
    else:
        train_fp32(
            model,
            train_file,
            eval_file,
            model_dir,
            device,
            max_epochs=max_epochs,
            min_epochs=min_epochs,
            patience=patience,
        )
    eval_set = EvalDataset(eval_file)
    scales = calibrate_activation_scales(model, _calibration_samples(eval_set), device)
    rows, summary = evaluate_model(model, eval_set, device, scales)
    qat_used = False
    if summary["quant_psnr_loss_db"] > 1.0:
        qat_finetune(model, train_file, scales, model_dir, device, epochs=5)
        scales = calibrate_activation_scales(model, _calibration_samples(eval_set), device)
        rows, summary = evaluate_model(model, eval_set, device, scales)
        qat_used = True
    if summary["quant_psnr_loss_db"] > 1.0:
        raise RuntimeError(
            f"Quantized PSNR loss {summary['quant_psnr_loss_db']:.4f} dB exceeds the 1 dB limit"
        )
    model.eval()
    write_model_contract(model, model_dir)
    export_quantized_bundle(model, scales, quant_dir)
    generate_fixed_vectors(quant_dir, vectors_dir)
    generate_full_reference(model, scales, full_reference_dir, device)
    generate_full_integer_golden(
        quant_dir,
        full_reference_dir / "input_960x540_y_u8.bin",
        full_integer_dir,
    )
    write_metrics(evaluation_dir / "set5_metrics.csv", rows, summary)
    result = {
        "device": str(device),
        "qat_used": qat_used,
        "activation_scales": scales,
        "set5": summary,
    }
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (evaluation_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_delivery_manifest(root)
    return result
