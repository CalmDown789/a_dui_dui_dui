from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from .model import TinySR, model_contract


Q31 = 1 << 31
Q15 = 1 << 15


def round_away_from_zero(x: np.ndarray | float) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    return np.where(a >= 0.0, np.floor(a + 0.5), np.ceil(a - 0.5))


def symmetric_scale(tensor: torch.Tensor) -> float:
    peak = float(tensor.detach().abs().max().cpu())
    return max(peak / 127.0, 1.0e-12)


def q31_multiplier(real_multiplier: float) -> int:
    value = int(round_away_from_zero(real_multiplier * Q31).item())
    if not (0 <= value <= 0x7FFFFFFF):
        raise ValueError(f"Q31 multiplier out of range: {real_multiplier}")
    return value


def calibrate_activation_scales(model: TinySR, lr_tensors: list[torch.Tensor], device: torch.device) -> tuple[float, float]:
    model.eval()
    max1 = 0.0
    max2 = 0.0
    with torch.inference_mode():
        for lr in lr_tensors:
            l1, l2, _ = model.forward_features(lr.unsqueeze(0).to(device))
            max1 = max(max1, float(l1.abs().max().cpu()))
            max2 = max(max2, float(l2.abs().max().cpu()))
    return max(max1 / 127.0, 1.0e-12), max(max2 / 127.0, 1.0e-12)


def _export_layer(
    name: str,
    layer: torch.nn.Conv2d,
    input_scale: float,
    input_zero_point: int,
    output_scale: float,
    output_zero_point: int,
    output_dir: Path,
    prelu_alpha: float | None,
) -> dict:
    weight = layer.weight.detach().cpu().numpy().astype(np.float64)
    bias = layer.bias.detach().cpu().numpy().astype(np.float64)
    weight_scale = np.maximum(np.max(np.abs(weight), axis=(1, 2, 3)) / 127.0, 1.0e-12)
    weight_q = np.clip(round_away_from_zero(weight / weight_scale[:, None, None, None]), -127, 127).astype(np.int8)
    bias_q = round_away_from_zero(bias / (input_scale * weight_scale)).astype(np.int32)
    multiplier = input_scale * weight_scale / output_scale
    multiplier_q31 = [q31_multiplier(float(value)) for value in multiplier]

    weight_file = f"{name}_weight_oihw_int8.bin"
    bias_file = f"{name}_bias_int32.bin"
    weight_q.tofile(output_dir / weight_file)
    bias_q.tofile(output_dir / bias_file)
    np.save(output_dir / f"{name}_weight_oihw_int8.npy", weight_q)
    np.save(output_dir / f"{name}_bias_int32.npy", bias_q)

    spec = {
        "name": name,
        "weight_shape_oihw": list(weight_q.shape),
        "weight_scale": weight_scale.tolist(),
        "weight_quantization": "symmetric_per_output_channel",
        "weight_zero_point": 0,
        "input_scale": input_scale,
        "input_zero_point": input_zero_point,
        "output_scale": output_scale,
        "output_zero_point": output_zero_point,
        "bias_scale": (input_scale * weight_scale).tolist(),
        "requant_multiplier_real": multiplier.tolist(),
        "requant_multiplier_q31": multiplier_q31,
        "weight_file": weight_file,
        "bias_file": bias_file,
        "rounding": "nearest_ties_away_from_zero",
        "saturation": "int8_-128_to_127",
    }
    if prelu_alpha is not None:
        alpha_q15 = int(np.clip(round_away_from_zero(prelu_alpha * Q15), -32768, 32767).item())
        alpha_file = f"{name}_prelu_alpha_q15.bin"
        np.asarray([alpha_q15], dtype=np.int16).tofile(output_dir / alpha_file)
        spec.update({"prelu_alpha_float": prelu_alpha, "prelu_alpha_q15": alpha_q15, "prelu_alpha_file": alpha_file})
    return spec


def export_quant_bundle(model: TinySR, activation_scales: tuple[float, float], output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    s1, s2 = activation_scales
    input_scale = 1.0 / 255.0
    output_scale = 1.0 / 255.0
    layers = [
        _export_layer("conv1", model.conv1, input_scale, -128, s1, 0, output_dir, float(model.prelu1.weight.detach().cpu().item())),
        _export_layer("conv2", model.conv2, s1, 0, s2, 0, output_dir, float(model.prelu2.weight.detach().cpu().item())),
        _export_layer("conv3", model.conv3, s2, 0, output_scale, -128, output_dir, None),
    ]
    bundle = {
        "schema_version": 1,
        "model_contract": model_contract(),
        "external_pixel_format": "uint8_Y_0_to_255",
        "internal_input_format": "int8_with_zero_point_-128_same_raw_bytes_as_uint8",
        "hidden_activation_format": "signed_int8_symmetric",
        "final_conv_format": "int8_scale_1_over_255_zero_point_-128",
        "accumulator": "signed_int32",
        "prelu": "scalar_Q1.15_applied_to_int32_accumulator_before_requantization",
        "requantization": "signed_int64_product_with_Q31_multiplier_then_round_nearest_ties_away_from_zero",
        "layers": layers,
    }
    (output_dir / "quant_params.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def load_quant_bundle(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _round_ste(x: torch.Tensor) -> torch.Tensor:
    return x + (torch.round(x) - x).detach()


def _fake_quant_symmetric(x: torch.Tensor, scale: float) -> torch.Tensor:
    q = torch.clamp(_round_ste(x / scale), -128.0, 127.0)
    return q * scale


def _fake_quant_weight(weight: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    scale = torch.clamp(weight.detach().abs().amax(dim=(1, 2, 3)) / 127.0, min=1.0e-12)
    shaped = scale.view(-1, 1, 1, 1)
    q = torch.clamp(_round_ste(weight / shaped), -127.0, 127.0)
    return q * shaped, scale


def _fake_quant_bias(bias: torch.Tensor, scale: torch.Tensor) -> torch.Tensor:
    return _round_ste(bias / scale) * scale


def _fake_quant_prelu(alpha: torch.Tensor) -> torch.Tensor:
    return torch.clamp(_round_ste(alpha * Q15), -32768.0, 32767.0) / Q15


def qat_forward(model: TinySR, x: torch.Tensor, activation_scales: tuple[float, float]) -> torch.Tensor:
    """Straight-through fake-quantized forward matching the exported integer contract."""
    s1, s2 = activation_scales
    input_scale = 1.0 / 255.0

    w1, sw1 = _fake_quant_weight(model.conv1.weight)
    b1 = _fake_quant_bias(model.conv1.bias, input_scale * sw1)
    y = F.conv2d(x, w1, b1, stride=1, padding=1)
    a1 = _fake_quant_prelu(model.prelu1.weight)
    y = torch.where(y >= 0.0, y, y * a1.view(1, 1, 1, 1))
    y = _fake_quant_symmetric(y, s1)

    w2, sw2 = _fake_quant_weight(model.conv2.weight)
    b2 = _fake_quant_bias(model.conv2.bias, s1 * sw2)
    y = F.conv2d(y, w2, b2, stride=1, padding=1)
    a2 = _fake_quant_prelu(model.prelu2.weight)
    y = torch.where(y >= 0.0, y, y * a2.view(1, 1, 1, 1))
    y = _fake_quant_symmetric(y, s2)

    w3, sw3 = _fake_quant_weight(model.conv3.weight)
    b3 = _fake_quant_bias(model.conv3.bias, s2 * sw3)
    y = F.conv2d(y, w3, b3, stride=1, padding=1)
    output_q = torch.clamp(_round_ste(y * 255.0 - 128.0), -128.0, 127.0)
    y = (output_q + 128.0) / 255.0
    return F.pixel_shuffle(y, upscale_factor=2)
