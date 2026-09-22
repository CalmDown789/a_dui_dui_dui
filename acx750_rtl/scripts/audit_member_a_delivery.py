#!/usr/bin/env python3
"""Independent NumPy audit for member A's integer delivery bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zlib

import numpy as np


INT16_MIN = -(1 << 15)
INT16_MAX = (1 << 15) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
Q15 = 1 << 15
Q31 = 1 << 31


def digest(path: Path) -> tuple[int, str, str]:
    data = path.read_bytes()
    return len(data), f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", hashlib.sha256(data).hexdigest()


def round_divide_signed(values: np.ndarray, denominator: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.int64)
    magnitude = (np.abs(values) + denominator // 2) // denominator
    return np.where(values < 0, -magnitude, magnitude)


def conv_integer_hwc(
    x: np.ndarray,
    weight_oihw: np.ndarray,
    bias: np.ndarray,
    padding: int,
) -> np.ndarray:
    kh, kw = weight_oihw.shape[2:]
    padded = np.pad(x.astype(np.int64), ((padding, padding), (padding, padding), (0, 0)))
    height, width, _ = x.shape
    accum = np.zeros((height, width, weight_oihw.shape[0]), dtype=np.int64)
    weights = weight_oihw.astype(np.int64)
    for ky in range(kh):
        for kx in range(kw):
            pixels = padded[ky : ky + height, kx : kx + width, :]
            accum += np.tensordot(pixels, weights[:, :, ky, kx], axes=([2], [1]))
    accum += bias.astype(np.int64)[None, None, :]
    return np.clip(accum, INT32_MIN, INT32_MAX)


def apply_prelu_q15(accum: np.ndarray, alpha_values: list[int] | None) -> np.ndarray:
    if alpha_values is None:
        return accum
    alpha = np.asarray(alpha_values, dtype=np.int64)[None, None, :]
    negative = round_divide_signed(accum * alpha, Q15)
    return np.where(accum < 0, negative, accum)


def requantize(accum: np.ndarray, multipliers: list[int], qmin: int, qmax: int) -> np.ndarray:
    multiplier = np.asarray(multipliers, dtype=np.int64)[None, None, :]
    result = round_divide_signed(accum.astype(np.int64) * multiplier, Q31)
    return np.clip(result, qmin, qmax)


def pixel_shuffle_x2(phases: np.ndarray) -> np.ndarray:
    height, width, channels = phases.shape
    if channels != 4:
        raise AssertionError(f"Expected four PixelShuffle phases, got {channels}")
    output = np.empty((height * 2, width * 2, 1), dtype=np.uint8)
    output[0::2, 0::2, 0] = phases[:, :, 0]
    output[0::2, 1::2, 0] = phases[:, :, 1]
    output[1::2, 0::2, 0] = phases[:, :, 2]
    output[1::2, 1::2, 0] = phases[:, :, 3]
    return output


def verify_delivery_manifest(root: Path) -> int:
    manifest = json.loads((root / "delivery_manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for relative, expected in manifest["files"].items():
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        size, crc32, sha256 = digest(path)
        if size != expected["bytes"] or crc32 != expected["crc32"] or sha256 != expected["sha256"]:
            raise AssertionError(f"Delivery digest mismatch: {relative}")
        checked += 1
    return checked


def decode_twos_complement(values: list[int], bits: int) -> np.ndarray:
    unsigned = np.asarray(values, dtype=np.int64)
    sign = 1 << (bits - 1)
    return np.where(unsigned & sign, unsigned - (1 << bits), unsigned)


def parse_mem(path: Path, bits: int) -> np.ndarray:
    values = [int(line.strip(), 16) for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    return decode_twos_complement(values, bits)


def parse_coe(path: Path, bits: int) -> np.ndarray:
    text = path.read_text(encoding="ascii")
    body = text.split("memory_initialization_vector=", 1)[1]
    values = [int(token, 16) for token in re.findall(r"[0-9A-Fa-f]+", body)]
    return decode_twos_complement(values, bits)


def verify_parameter_formats(root: Path, spec: dict) -> int:
    quant_dir = root / "artifacts" / "quant"
    checked = 0
    for layer in spec["layers"]:
        fields = [("weight", np.int8, 8), ("bias", np.dtype("<i4"), 32)]
        if layer["prelu_q15"] is not None:
            fields.append(("prelu", np.dtype("<i2"), 16))
        for stem, dtype, bits in fields:
            files = layer["files"]
            npy = np.load(quant_dir / files[f"{stem}_npy"]).reshape(-1).astype(np.int64)
            raw = np.fromfile(quant_dir / files[f"{stem}_bin"], dtype=dtype).astype(np.int64)
            mem = parse_mem(quant_dir / files[f"{stem}_mem"], bits)
            coe = parse_coe(quant_dir / files[f"{stem}_coe"], bits)
            if not (np.array_equal(npy, raw) and np.array_equal(raw, mem) and np.array_equal(mem, coe)):
                raise AssertionError(f"Parameter format mismatch: {layer['name']}:{stem}")
            checked += 1
    return checked


def load_expected(case_dir: Path, manifest: dict, name: str) -> np.ndarray:
    metadata = manifest["files"][name]
    return np.fromfile(case_dir / name, dtype=np.dtype(metadata["dtype"])).reshape(metadata["shape"])


def verify_case(root: Path, spec: dict, case: str) -> dict[str, object]:
    quant_dir = root / "artifacts" / "quant"
    case_dir = root / "artifacts" / "test_vectors" / case
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    height, width, _ = manifest["files"]["input_hwc_int16.bin"]["shape"]
    input_u8 = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(height, width, 1)
    current = input_u8.astype(np.int16)
    if not np.array_equal(current, load_expected(case_dir, manifest, "input_hwc_int16.bin")):
        raise AssertionError(f"Input conversion mismatch: {case}")

    ranges: dict[str, list[int]] = {}
    phases: np.ndarray | None = None
    for layer in spec["layers"]:
        name = layer["name"]
        weight = np.fromfile(
            quant_dir / layer["files"]["weight_bin"], dtype=np.int8
        ).reshape(layer["weight_shape_oihw"])
        bias = np.fromfile(quant_dir / layer["files"]["bias_bin"], dtype="<i4")
        accum = conv_integer_hwc(current, weight, bias, int(layer["padding"][0]))
        accum = np.clip(apply_prelu_q15(accum, layer["prelu_q15"]), INT32_MIN, INT32_MAX).astype(np.int32)
        expected_accum = load_expected(case_dir, manifest, f"{name}_accum_hwc_int32.bin")
        if not np.array_equal(accum, expected_accum):
            mismatch = int(np.count_nonzero(accum != expected_accum))
            raise AssertionError(f"Accumulator mismatch: {case}/{name}, count={mismatch}")
        ranges[f"{name}_accum"] = [int(accum.min()), int(accum.max())]

        if name == "subpixel":
            phases = requantize(accum, layer["requant_multiplier_q31"], 0, 255).astype(np.uint8)
            expected = load_expected(case_dir, manifest, "subpixel_phases_hwc_uint8.bin")
        else:
            current = requantize(
                accum, layer["requant_multiplier_q31"], INT16_MIN, INT16_MAX
            ).astype(np.int16)
            expected = load_expected(case_dir, manifest, f"{name}_hwc_int16.bin")
            if not np.array_equal(current, expected):
                mismatch = int(np.count_nonzero(current != expected))
                raise AssertionError(f"Activation mismatch: {case}/{name}, count={mismatch}")
            continue
        if not np.array_equal(phases, expected):
            mismatch = int(np.count_nonzero(phases != expected))
            raise AssertionError(f"Subpixel mismatch: {case}, count={mismatch}")

    if phases is None:
        raise AssertionError("Subpixel layer was not found")
    output = pixel_shuffle_x2(phases)
    expected_output = load_expected(case_dir, manifest, "output_hwc_uint8.bin")
    if not np.array_equal(output, expected_output):
        raise AssertionError(f"PixelShuffle output mismatch: {case}")
    return {"output_sha256": digest(case_dir / "output_hwc_uint8.bin")[2], "ranges": ranges}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.delivery_root.resolve()
    spec = json.loads((root / "artifacts" / "quant" / "quant_params.json").read_text(encoding="utf-8"))
    if spec["model"] != "FSRCNNSubpixel-d16-s8-m1-c16-x2":
        raise AssertionError(f"Unexpected model: {spec['model']}")

    report = {
        "status": "PASS",
        "delivery_files_verified": verify_delivery_manifest(root),
        "parameter_groups_cross_checked": verify_parameter_formats(root, spec),
        "model": spec["model"],
        "rounding": spec["rounding"],
        "cases": {
            case: verify_case(root, spec, case)
            for case in ("zero", "impulse", "ramp", "random")
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
