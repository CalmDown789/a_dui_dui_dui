from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from .model import FSRCNNSubpixel


INT16_MIN = -32768
INT16_MAX = 32767
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
Q15 = 1 << 15
Q31 = 1 << 31


def round_away_from_zero(values: np.ndarray | float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return np.copysign(np.floor(np.abs(array) + 0.5), array)


def round_divide_signed(numerator: np.ndarray, denominator: int) -> np.ndarray:
    values = np.asarray(numerator, dtype=np.int64)
    signs = np.where(values < 0, -1, 1)
    rounded = (np.abs(values) + denominator // 2) // denominator
    return rounded * signs


def symmetric_scale(values: torch.Tensor, qmax: int) -> float:
    maximum = float(values.detach().abs().max().item())
    return max(maximum / float(qmax), 1.0e-12)


def named_layers(model: FSRCNNSubpixel) -> list[tuple[str, nn.Conv2d, nn.PReLU | None]]:
    layers: list[tuple[str, nn.Conv2d, nn.PReLU | None]] = [
        ("feature", model.feature, model.feature_act),
        ("shrink", model.shrink, model.shrink_act),
    ]
    layers.extend(
        (f"mapping{index}", conv, model.mapping_act[index])
        for index, conv in enumerate(model.mapping)
    )
    layers.extend(
        [
            ("expand", model.expand, model.expand_act),
            ("subpixel", model.subpixel, None),
        ]
    )
    return layers


@torch.no_grad()
def calibrate_activation_scales(
    model: FSRCNNSubpixel,
    samples: list[torch.Tensor],
    device: torch.device,
) -> dict[str, float]:
    maxima: dict[str, float] = {}
    model.eval()
    for sample in samples:
        stages = model.forward_with_intermediates(sample.to(device))
        for name in ["feature", "shrink", *[f"mapping{i}" for i in range(model.config.m)], "expand"]:
            maxima[name] = max(maxima.get(name, 0.0), float(stages[name].abs().max().item()))
    return {name: max(value / INT16_MAX, 1.0e-12) for name, value in maxima.items()}


def _write_mem(path: Path, values: np.ndarray, bits: int) -> None:
    mask = (1 << bits) - 1
    flat = values.reshape(-1)
    width = bits // 4
    path.write_text("\n".join(f"{int(value) & mask:0{width}X}" for value in flat) + "\n", encoding="ascii")


def _write_coe(path: Path, values: np.ndarray, bits: int) -> None:
    mask = (1 << bits) - 1
    width = bits // 4
    encoded = [f"{int(value) & mask:0{width}X}" for value in values.reshape(-1)]
    body = ",\n".join(encoded[:-1]) + (",\n" if len(encoded) > 1 else "") + encoded[-1] + ";\n"
    path.write_text("memory_initialization_radix=16;\nmemory_initialization_vector=\n" + body, encoding="ascii")


def _export_array(base: Path, stem: str, values: np.ndarray, bits: int) -> dict[str, str]:
    base.mkdir(parents=True, exist_ok=True)
    values = np.ascontiguousarray(values)
    np.save(base / f"{stem}.npy", values)
    values.tofile(base / f"{stem}.bin")
    _write_mem(base / f"{stem}.mem", values, bits)
    _write_coe(base / f"{stem}.coe", values, bits)
    return {
        "npy": f"{stem}.npy",
        "bin": f"{stem}.bin",
        "mem": f"{stem}.mem",
        "coe": f"{stem}.coe",
    }


def export_quantized_bundle(
    model: FSRCNNSubpixel,
    activation_scales: dict[str, float],
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_scale = 1.0 / 255.0
    layer_specs: list[dict] = []
    previous_scale = input_scale
    for name, conv, prelu in named_layers(model):
        weight = conv.weight.detach().cpu().numpy().astype(np.float64)
        bias = conv.bias.detach().cpu().numpy().astype(np.float64)
        weight_scale = np.maximum(np.max(np.abs(weight), axis=(1, 2, 3)) / 127.0, 1.0e-12)
        weight_q = np.clip(
            round_away_from_zero(weight / weight_scale[:, None, None, None]), -127, 127
        ).astype(np.int8)
        bias_q = np.clip(
            round_away_from_zero(bias / (previous_scale * weight_scale)), INT32_MIN, INT32_MAX
        ).astype("<i4")
        is_output = name == "subpixel"
        output_scale = input_scale if is_output else activation_scales[name]
        multiplier = previous_scale * weight_scale / output_scale
        multiplier_q31 = round_away_from_zero(multiplier * Q31).astype("<i8")
        files = {}
        files.update({f"weight_{key}": value for key, value in _export_array(output_dir, f"{name}_weight_oihw_int8", weight_q, 8).items()})
        files.update({f"bias_{key}": value for key, value in _export_array(output_dir, f"{name}_bias_int32", bias_q, 32).items()})
        alpha_q15: np.ndarray | None = None
        if prelu is not None:
            alpha = prelu.weight.detach().cpu().numpy().astype(np.float64)
            alpha_q15 = np.clip(round_away_from_zero(alpha * Q15), INT16_MIN, INT16_MAX).astype("<i2")
            files.update({f"prelu_{key}": value for key, value in _export_array(output_dir, f"{name}_prelu_q15", alpha_q15, 16).items()})
        layer_specs.append(
            {
                "name": name,
                "type": "conv2d",
                "kernel": list(conv.kernel_size),
                "padding": list(conv.padding),
                "weight_shape_oihw": list(weight_q.shape),
                "weight_scale_per_output": weight_scale.tolist(),
                "input_scale": previous_scale,
                "output_scale": output_scale,
                "bias_scale_per_output": (previous_scale * weight_scale).tolist(),
                "requant_multiplier_real": multiplier.tolist(),
                "requant_multiplier_q31": multiplier_q31.tolist(),
                "prelu_q15": alpha_q15.tolist() if alpha_q15 is not None else None,
                "output_dtype": "uint8" if is_output else "int16",
                "files": files,
            }
        )
        previous_scale = output_scale
    bundle = {
        "schema_version": 1,
        "model": "FSRCNNSubpixel-d16-s8-m1-c16-x2",
        "input": {
            "dtype": "uint8",
            "shape_hwc": [540, 960, 1],
            "scale": input_scale,
            "zero_point": 0,
            "layout": "HWC_row_major",
        },
        "hidden_activation": {
            "dtype": "int16",
            "quantization": "symmetric_per_tensor",
            "zero_point": 0,
        },
        "weight": {
            "dtype": "int8",
            "layout": "OIHW",
            "quantization": "symmetric_per_output_channel",
            "zero_point": 0,
        },
        "bias_accumulator": {"dtype": "int32", "overflow": "saturate"},
        "rounding": "nearest_ties_away_from_zero",
        "prelu": "per_channel_Q1.15_before_requantization",
        "pixel_shuffle": {
            "scale": 2,
            "channel_order": ["top_left", "top_right", "bottom_left", "bottom_right"],
        },
        "output": {"dtype": "uint8", "shape_hwc": [1080, 1920, 1], "scale": input_scale, "zero_point": 0},
        "layers": layer_specs,
    }
    (output_dir / "quant_params.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return bundle


def _fake_quant(values: torch.Tensor, scale: torch.Tensor | float, qmin: int, qmax: int) -> torch.Tensor:
    scale_tensor = torch.as_tensor(scale, dtype=values.dtype, device=values.device)
    while scale_tensor.ndim < values.ndim:
        scale_tensor = scale_tensor.unsqueeze(-1)
    codes = torch.clamp(torch.round(values / scale_tensor), qmin, qmax)
    return codes * scale_tensor


@torch.no_grad()
def quantized_forward_float(
    model: FSRCNNSubpixel,
    x: torch.Tensor,
    activation_scales: dict[str, float],
) -> torch.Tensor:
    current = _fake_quant(x, 1.0 / 255.0, 0, 255)
    for name, conv, prelu in named_layers(model):
        weight_scales = torch.clamp(conv.weight.detach().abs().amax(dim=(1, 2, 3)) / 127.0, min=1.0e-12)
        weight_qdq = _fake_quant(conv.weight, weight_scales, -127, 127)
        current = F.conv2d(current, weight_qdq, conv.bias, padding=conv.padding)
        if prelu is not None:
            alpha_qdq = _fake_quant(prelu.weight, 1.0 / Q15, INT16_MIN, INT16_MAX)
            current = F.prelu(current, alpha_qdq)
            current = _fake_quant(current, activation_scales[name], INT16_MIN, INT16_MAX)
    output = F.pixel_shuffle(current, 2)
    return _fake_quant(output, 1.0 / 255.0, 0, 255).clamp(0.0, 1.0)
