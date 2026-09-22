#!/usr/bin/env python3
"""Generate compact RTL postprocess vectors from member A's golden bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from audit_member_a_delivery import (
    INT32_MAX,
    INT32_MIN,
    apply_prelu_q15,
    conv_integer_hwc,
)


def masked(value: int, bits: int) -> int:
    return int(value) & ((1 << bits) - 1)


def extreme_indices(values: np.ndarray) -> list[tuple[int, int, int]]:
    indices: list[tuple[int, int, int]] = []
    for channel in range(values.shape[2]):
        plane = values[:, :, channel]
        for flat_index in (int(np.argmin(plane)), int(np.argmax(plane))):
            y, x = np.unravel_index(flat_index, plane.shape)
            indices.append((int(y), int(x), channel))
    return indices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    root = args.delivery_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    quant_dir = root / "artifacts" / "quant"
    case_dir = root / "artifacts" / "test_vectors" / "random"
    spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    height, width, _ = manifest["files"]["input_hwc_int16.bin"]["shape"]
    current = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(height, width, 1).astype(np.int16)

    signed_lines: list[str] = []
    unsigned_lines: list[str] = []
    sample_summary: dict[str, int] = {}

    for layer in spec["layers"]:
        name = layer["name"]
        weight = np.fromfile(
            quant_dir / layer["files"]["weight_bin"], dtype=np.int8
        ).reshape(layer["weight_shape_oihw"])
        bias = np.fromfile(quant_dir / layer["files"]["bias_bin"], dtype="<i4")
        raw = conv_integer_hwc(current, weight, bias, int(layer["padding"][0])).astype(np.int32)
        post_prelu = np.clip(
            apply_prelu_q15(raw, layer["prelu_q15"]), INT32_MIN, INT32_MAX
        ).astype(np.int32)
        expected_accum = np.fromfile(
            case_dir / f"{name}_accum_hwc_int32.bin", dtype=np.int32
        ).reshape(raw.shape)
        if not np.array_equal(post_prelu, expected_accum):
            raise AssertionError(f"Pre-vector accumulator mismatch: {name}")

        selected = extreme_indices(raw)
        sample_summary[name] = len(selected)
        multipliers = layer["requant_multiplier_q31"]
        if name == "subpixel":
            expected = np.fromfile(
                case_dir / "subpixel_phases_hwc_uint8.bin", dtype=np.uint8
            ).reshape(raw.shape)
            for y, x, channel in selected:
                word = (
                    (masked(raw[y, x, channel], 32) << 40)
                    | (masked(multipliers[channel], 32) << 8)
                    | masked(expected[y, x, channel], 8)
                )
                unsigned_lines.append(f"{word:018X}")
        else:
            expected = np.fromfile(
                case_dir / f"{name}_hwc_int16.bin", dtype=np.int16
            ).reshape(raw.shape)
            alphas = layer["prelu_q15"]
            for y, x, channel in selected:
                word = (
                    (masked(raw[y, x, channel], 32) << 64)
                    | (masked(alphas[channel], 16) << 48)
                    | (masked(multipliers[channel], 32) << 16)
                    | masked(expected[y, x, channel], 16)
                )
                signed_lines.append(f"{word:024X}")
            current = expected

    (output_dir / "postprocess_i16.mem").write_text("\n".join(signed_lines) + "\n", encoding="ascii")
    (output_dir / "postprocess_u8.mem").write_text("\n".join(unsigned_lines) + "\n", encoding="ascii")
    (output_dir / "postprocess_vector_counts.vh").write_text(
        f"`define POST_I16_COUNT {len(signed_lines)}\n"
        f"`define POST_U8_COUNT {len(unsigned_lines)}\n",
        encoding="ascii",
    )
    print(json.dumps({"signed_count": len(signed_lines), "unsigned_count": len(unsigned_lines), "layers": sample_summary}, indent=2))


if __name__ == "__main__":
    main()
