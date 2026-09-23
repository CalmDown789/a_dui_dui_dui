from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import torch
import torch.nn.functional as F

from .quantization import INT16_MAX, INT16_MIN, INT32_MAX, INT32_MIN, Q15, Q31, round_divide_signed


def pixel_shuffle_hwc_x2(phases: np.ndarray) -> np.ndarray:
    if phases.ndim != 3 or phases.shape[2] != 4:
        raise ValueError("PixelShuffle x2 expects HWC with exactly four phase channels")
    height, width, _ = phases.shape
    output = np.empty((height * 2, width * 2, 1), dtype=phases.dtype)
    output[0::2, 0::2, 0] = phases[:, :, 0]
    output[0::2, 1::2, 0] = phases[:, :, 1]
    output[1::2, 0::2, 0] = phases[:, :, 2]
    output[1::2, 1::2, 0] = phases[:, :, 3]
    return output


def _conv_integer_hwc(x: np.ndarray, weight: np.ndarray, bias: np.ndarray, padding: int) -> np.ndarray:
    x_nchw = torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1)[None])).to(torch.float64)
    w_oihw = torch.from_numpy(np.ascontiguousarray(weight)).to(torch.float64)
    accum = F.conv2d(x_nchw, w_oihw, bias=None, padding=padding)
    accum_np = np.rint(accum.numpy()).astype(np.int64)[0].transpose(1, 2, 0)
    accum_np += bias.astype(np.int64)[None, None, :]
    return np.clip(accum_np, INT32_MIN, INT32_MAX).astype(np.int64)


def _apply_prelu_q15(accum: np.ndarray, alpha_q15: np.ndarray | None) -> np.ndarray:
    if alpha_q15 is None:
        return accum
    alpha = alpha_q15.astype(np.int64)[None, None, :]
    negative = round_divide_signed(accum * alpha, Q15)
    return np.where(accum < 0, negative, accum)


def _requantize(accum: np.ndarray, multipliers: np.ndarray, qmin: int, qmax: int) -> np.ndarray:
    multiplier = multipliers.astype(np.int64)[None, None, :]
    result = round_divide_signed(accum.astype(np.int64) * multiplier, Q31)
    return np.clip(result, qmin, qmax)


class FixedReference:
    def __init__(self, quant_dir: Path) -> None:
        self.quant_dir = Path(quant_dir)
        self.spec = json.loads((self.quant_dir / "quant_params.json").read_text(encoding="utf-8"))

    def run(self, input_u8: np.ndarray) -> dict[str, np.ndarray]:
        if input_u8.ndim == 2:
            input_u8 = input_u8[:, :, None]
        if input_u8.ndim != 3 or input_u8.shape[2] != 1 or input_u8.dtype != np.uint8:
            raise ValueError("Input must be uint8 HWC with one channel")
        current = input_u8.astype(np.int16)
        outputs: dict[str, np.ndarray] = {"input": current}
        for layer in self.spec["layers"]:
            name = layer["name"]
            shape = tuple(layer["weight_shape_oihw"])
            weight = np.fromfile(self.quant_dir / layer["files"]["weight_bin"], dtype=np.int8).reshape(shape)
            bias = np.fromfile(self.quant_dir / layer["files"]["bias_bin"], dtype="<i4")
            padding = int(layer["padding"][0])
            accum = _conv_integer_hwc(current, weight, bias, padding)
            alpha_values = layer.get("prelu_q15")
            alpha = np.asarray(alpha_values, dtype=np.int16) if alpha_values is not None else None
            accum = np.clip(_apply_prelu_q15(accum, alpha), INT32_MIN, INT32_MAX).astype(np.int32)
            outputs[f"{name}_accum"] = accum
            multipliers = np.asarray(layer["requant_multiplier_q31"], dtype=np.int64)
            if name == "subpixel":
                phases = _requantize(accum, multipliers, 0, 255).astype(np.uint8)
                outputs["subpixel_phases"] = phases
                current = phases
            else:
                current = _requantize(accum, multipliers, INT16_MIN, INT16_MAX).astype(np.int16)
                outputs[name] = current
        outputs["output"] = pixel_shuffle_hwc_x2(outputs["subpixel_phases"])
        return outputs
