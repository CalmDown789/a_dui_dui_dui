from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path

import numpy as np

from .quantization import Q15, Q31, load_quant_bundle


def _round_divide_signed(numerator: np.ndarray, denominator: int) -> np.ndarray:
    n = numerator.astype(np.int64, copy=False)
    absolute = np.abs(n)
    rounded = (absolute + denominator // 2) // denominator
    return np.where(n < 0, -rounded, rounded)


def conv2d_int_hwc(x_q: np.ndarray, input_zero_point: int, weight_q: np.ndarray, bias_q: np.ndarray) -> np.ndarray:
    """OIHW cross-correlation with same zero padding, returning int32 HWC."""
    if x_q.ndim != 3 or weight_q.ndim != 4:
        raise ValueError("Expected HWC input and OIHW weights")
    h, w, cin = x_q.shape
    cout, win, kh, kw = weight_q.shape
    if cin != win or kh != 3 or kw != 3:
        raise ValueError(f"Shape mismatch: input {x_q.shape}, weights {weight_q.shape}")
    centered = x_q.astype(np.int32) - int(input_zero_point)
    padded = np.pad(centered, ((1, 1), (1, 1), (0, 0)), mode="constant")
    out = np.broadcast_to(bias_q.astype(np.int32), (h, w, cout)).copy()
    for ky in range(3):
        for kx in range(3):
            patch = padded[ky : ky + h, kx : kx + w, :]
            kernel = weight_q[:, :, ky, kx].astype(np.int32)
            out += np.tensordot(patch, kernel, axes=([2], [1])).astype(np.int32)
    return out


def apply_prelu_q15(acc: np.ndarray, alpha_q15: int) -> np.ndarray:
    result = acc.astype(np.int64)
    negative = result < 0
    if np.any(negative):
        result[negative] = _round_divide_signed(result[negative] * int(alpha_q15), Q15)
    return result.astype(np.int32)


def requantize_int8(acc: np.ndarray, multiplier_q31: int | list[int], output_zero_point: int) -> np.ndarray:
    multiplier = np.asarray(multiplier_q31, dtype=np.int64)
    if multiplier.ndim == 1:
        multiplier = multiplier.reshape(1, 1, -1)
    scaled = _round_divide_signed(acc.astype(np.int64) * multiplier, Q31)
    shifted = scaled + int(output_zero_point)
    return np.clip(shifted, -128, 127).astype(np.int8)


def pixel_shuffle_hwc_x2(x: np.ndarray) -> np.ndarray:
    if x.ndim != 3 or x.shape[2] != 4:
        raise ValueError("PixelShuffle x2 expects HWC with 4 channels")
    h, w, _ = x.shape
    out = np.empty((h * 2, w * 2, 1), dtype=x.dtype)
    out[0::2, 0::2, 0] = x[:, :, 0]
    out[0::2, 1::2, 0] = x[:, :, 1]
    out[1::2, 0::2, 0] = x[:, :, 2]
    out[1::2, 1::2, 0] = x[:, :, 3]
    return out


class GoldenModel:
    def __init__(self, quant_dir: Path):
        self.quant_dir = Path(quant_dir)
        self.spec = load_quant_bundle(self.quant_dir / "quant_params.json")
        self.layers = []
        for layer_spec in self.spec["layers"]:
            weight = np.fromfile(self.quant_dir / layer_spec["weight_file"], dtype=np.int8).reshape(layer_spec["weight_shape_oihw"])
            bias = np.fromfile(self.quant_dir / layer_spec["bias_file"], dtype=np.int32)
            self.layers.append((layer_spec, weight, bias))

    def run(self, input_u8: np.ndarray, return_layers: bool = False):
        if input_u8.ndim == 2:
            input_u8 = input_u8[:, :, None]
        if input_u8.dtype != np.uint8 or input_u8.shape[2] != 1:
            raise ValueError("Input must be uint8 HWC luminance")
        current = (input_u8.astype(np.int16) - 128).astype(np.int8)
        dumps: dict[str, np.ndarray] = {"input_int8": current.copy()}
        for index, (spec, weight, bias) in enumerate(self.layers, start=1):
            acc = conv2d_int_hwc(current, spec["input_zero_point"], weight, bias)
            if "prelu_alpha_q15" in spec:
                acc = apply_prelu_q15(acc, spec["prelu_alpha_q15"])
            current = requantize_int8(acc, spec["requant_multiplier_q31"], spec["output_zero_point"])
            dumps[f"conv{index}_out_int8"] = current.copy()
        shuffled = pixel_shuffle_hwc_x2(current)
        output_u8 = np.clip(shuffled.astype(np.int16) + 128, 0, 255).astype(np.uint8)
        dumps["output_int8"] = shuffled
        dumps["output_u8"] = output_u8
        return (output_u8, dumps) if return_layers else output_u8


def file_digest(path: Path) -> dict:
    data = Path(path).read_bytes()
    return {"bytes": len(data), "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "sha256": hashlib.sha256(data).hexdigest()}


def export_test_vector(case_dir: Path, input_u8: np.ndarray, golden: GoldenModel) -> dict:
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    output_u8, dumps = golden.run(input_u8, return_layers=True)
    arrays = {
        "input_y_u8.bin": input_u8.astype(np.uint8),
        "input_model_int8.bin": dumps["input_int8"],
        "conv1_out_hwc_int8.bin": dumps["conv1_out_int8"],
        "conv2_out_hwc_int8.bin": dumps["conv2_out_int8"],
        "conv3_out_hwc_int8.bin": dumps["conv3_out_int8"],
        "output_model_int8.bin": dumps["output_int8"],
        "output_y_u8.bin": output_u8,
    }
    manifest = {"layout": "HWC_row_major", "files": {}}
    for filename, array in arrays.items():
        path = case_dir / filename
        np.ascontiguousarray(array).tofile(path)
        manifest["files"][filename] = {"shape": list(array.shape), "dtype": str(array.dtype), **file_digest(path)}
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
