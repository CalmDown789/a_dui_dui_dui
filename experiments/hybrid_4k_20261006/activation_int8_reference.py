from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from member_a.fixed_reference import (
    _apply_prelu_q15,
    _conv_integer_hwc,
    _requantize,
    pixel_shuffle_hwc_x2,
)
from member_a.quantization import (
    INT16_MAX,
    INT16_MIN,
    INT32_MAX,
    INT32_MIN,
    Q15,
    export_quantized_bundle,
    named_layers,
    round_away_from_zero,
)


HIDDEN_LAYERS = ("feature", "shrink", "mapping0", "expand")
ACTIVATION_LIMITS = {
    8: (-127, 127, np.int8),
    16: (INT16_MIN, INT16_MAX, np.int16),
}


def validate_activation_bits(bits: dict[str, int]) -> None:
    if set(bits) != set(HIDDEN_LAYERS):
        raise ValueError(f"activation bit map must contain exactly {HIDDEN_LAYERS}")
    if any(width not in ACTIVATION_LIMITS for width in bits.values()):
        raise ValueError("hidden activation width must be 8 or 16 bits")


def activation_scales_from_training(
    model: nn.Module,
    samples: list[torch.Tensor],
    bits: dict[str, int],
    device: torch.device,
) -> dict[str, float]:
    """Calibrate symmetric per-layer ranges using only supplied training samples."""
    validate_activation_bits(bits)
    maxima: dict[str, float] = {name: 0.0 for name in HIDDEN_LAYERS}
    model.eval()
    with torch.no_grad():
        for sample in samples:
            stages = model.forward_with_intermediates(sample.to(device))
            for name in HIDDEN_LAYERS:
                maxima[name] = max(maxima[name], float(stages[name].abs().max().item()))
    return {
        name: max(maxima[name] / float(ACTIVATION_LIMITS[bits[name]][1]), 1.0e-12)
        for name in HIDDEN_LAYERS
    }


def export_mixed_activation_bundle(
    model: nn.Module,
    activation_scales: dict[str, float],
    activation_bits: dict[str, int],
    output_dir: Path,
) -> dict:
    """Export normal INT8 weights and mark per-layer INT8/INT16 activation widths."""
    validate_activation_bits(activation_bits)
    bundle = export_quantized_bundle(model, activation_scales, output_dir)
    for layer in bundle["layers"]:
        name = layer["name"]
        if name == "subpixel":
            layer["output_dtype"] = "uint8"
            continue
        width = activation_bits[name]
        layer["output_dtype"] = f"int{width}"
        layer["activation_bits"] = width
        layer["activation_qmin"], layer["activation_qmax"] = ACTIVATION_LIMITS[width][:2]
    widths = set(activation_bits.values())
    bundle["hidden_activation"] = {
        "dtype": f"int{next(iter(widths))}" if len(widths) == 1 else "per_layer_mixed",
        "quantization": "symmetric_per_tensor",
        "zero_point": 0,
        "bits_by_layer": activation_bits,
        "calibration": "training-side max-absolute scale divided by signed qmax",
    }
    (output_dir / "quant_params.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return bundle


class MixedActivationFixedReference:
    """Exact integer inference for the experiment's per-layer activation widths."""

    def __init__(self, quant_dir: Path) -> None:
        self.quant_dir = Path(quant_dir)
        self.spec = json.loads((self.quant_dir / "quant_params.json").read_text(encoding="utf-8"))

    def iter_outputs(self, input_u8: np.ndarray):
        if input_u8.ndim == 2:
            input_u8 = input_u8[:, :, None]
        if input_u8.ndim != 3 or input_u8.shape[2] != 1 or input_u8.dtype != np.uint8:
            raise ValueError("input must be uint8 HWC with one channel")
        current = input_u8.astype(np.int16)
        yield "input", current
        for layer in self.spec["layers"]:
            name = layer["name"]
            shape = tuple(layer["weight_shape_oihw"])
            weight = np.fromfile(self.quant_dir / layer["files"]["weight_bin"], dtype=np.int8).reshape(shape)
            bias = np.fromfile(self.quant_dir / layer["files"]["bias_bin"], dtype="<i4")
            accum = _conv_integer_hwc(current, weight, bias, int(layer["padding"][0]))
            alpha_q15 = layer.get("prelu_q15")
            alpha = np.asarray(alpha_q15, dtype=np.int16) if alpha_q15 is not None else None
            accum = np.clip(_apply_prelu_q15(accum, alpha), INT32_MIN, INT32_MAX).astype(np.int32)
            yield f"{name}_accum", accum
            multipliers = np.asarray(layer["requant_multiplier_q31"], dtype=np.int64)
            if name == "subpixel":
                phases = _requantize(accum, multipliers, 0, 255).astype(np.uint8)
                yield "subpixel_phases", phases
                yield "output", pixel_shuffle_hwc_x2(phases)
                continue
            width = int(layer["activation_bits"])
            qmin, qmax, dtype = ACTIVATION_LIMITS[width]
            current = _requantize(accum, multipliers, qmin, qmax).astype(dtype)
            yield name, current

    def run(self, input_u8: np.ndarray) -> dict[str, np.ndarray]:
        return dict(self.iter_outputs(input_u8))


def _round_away_torch(values: torch.Tensor) -> torch.Tensor:
    return torch.sign(values) * torch.floor(torch.abs(values) + 0.5)


def _ste_fake_quant(
    values: torch.Tensor,
    scale: torch.Tensor | float,
    qmin: int,
    qmax: int,
) -> torch.Tensor:
    scale_tensor = torch.as_tensor(scale, dtype=values.dtype, device=values.device)
    while scale_tensor.ndim < values.ndim:
        scale_tensor = scale_tensor.unsqueeze(-1)
    normalized = values / scale_tensor
    quantized = torch.clamp(_round_away_torch(normalized), qmin, qmax) * scale_tensor
    return values + (quantized - values).detach()


def qat_forward_mixed(
    model: nn.Module,
    x: torch.Tensor,
    activation_scales: dict[str, float],
    activation_bits: dict[str, int],
) -> torch.Tensor:
    """STE fake quantization for INT8 weights and selected INT8 hidden outputs."""
    validate_activation_bits(activation_bits)
    current = _ste_fake_quant(x, 1.0 / 255.0, 0, 255)
    for name, conv, prelu in named_layers(model):
        weight_scale = torch.clamp(conv.weight.detach().abs().amax(dim=(1, 2, 3)) / 127.0, min=1.0e-12)
        weight = _ste_fake_quant(conv.weight, weight_scale, -127, 127)
        current = F.conv2d(current, weight, conv.bias, padding=conv.padding)
        if prelu is not None:
            alpha = _ste_fake_quant(prelu.weight, 1.0 / Q15, INT16_MIN, INT16_MAX)
            current = F.prelu(current, alpha)
            width = activation_bits[name]
            qmin, qmax, _dtype = ACTIVATION_LIMITS[width]
            current = _ste_fake_quant(current, activation_scales[name], qmin, qmax)
    current = F.pixel_shuffle(current, 2)
    return _ste_fake_quant(current, 1.0 / 255.0, 0, 255).clamp(0.0, 1.0)


__all__ = [
    "ACTIVATION_LIMITS",
    "HIDDEN_LAYERS",
    "MixedActivationFixedReference",
    "activation_scales_from_training",
    "export_mixed_activation_bundle",
    "qat_forward_mixed",
    "round_away_from_zero",
    "validate_activation_bits",
]
