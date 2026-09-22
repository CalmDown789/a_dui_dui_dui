#!/usr/bin/env python3
"""Generate real member-A vectors for the first and final 5x5 RTL paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from audit_member_a_delivery import apply_prelu_q15, conv_integer_hwc, requantize


def masked(value: int, bits: int) -> int:
    return int(value) & ((1 << bits) - 1)


def pack_fields(values: np.ndarray, bits: int) -> int:
    word = 0
    for index, value in enumerate(values.reshape(-1)):
        word |= masked(value, bits) << (index * bits)
    return word


def positions(height: int, width: int) -> tuple[tuple[int, int], ...]:
    return ((0, 0), (0, width-1), (height-1, 0), (height-1, width-1), (height//2, width//2))


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
    layers = {layer["name"]: layer for layer in spec["layers"]}
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))

    # Feature: uint8 input, one input channel, sixteen output channels.
    feature = layers["feature"]
    height, width, _ = manifest["files"]["input_hwc_int16.bin"]["shape"]
    input_u8 = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(height, width, 1)
    feature_weight = np.fromfile(
        quant_dir / feature["files"]["weight_bin"], dtype=np.int8
    ).reshape(feature["weight_shape_oihw"])
    feature_bias = np.fromfile(quant_dir / feature["files"]["bias_bin"], dtype="<i4")
    feature_raw = conv_integer_hwc(input_u8.astype(np.int16), feature_weight, feature_bias, 2).astype(np.int32)
    feature_expected = requantize(
        apply_prelu_q15(feature_raw, feature["prelu_q15"]),
        feature["requant_multiplier_q31"], -(1 << 15), (1 << 15)-1,
    ).astype(np.int16)
    feature_golden = np.fromfile(case_dir / "feature_hwc_int16.bin", dtype=np.int16).reshape(feature_expected.shape)
    if not np.array_equal(feature_expected, feature_golden):
        raise AssertionError("Feature result mismatch before vector export")
    padded_u8 = np.pad(input_u8, ((2, 2), (2, 2), (0, 0)))
    feature_contributions: list[str] = []
    feature_groups: list[str] = []
    for y, x in positions(height, width):
        window = padded_u8[y:y+5, x:x+5, 0]
        for out_channel in range(feature_weight.shape[0]):
            record = (pack_fields(window, 8) << 200) | pack_fields(feature_weight[out_channel, 0], 8)
            feature_contributions.append(f"{record:0100X}")
            group = (
                (masked(feature_bias[out_channel], 32) << 96)
                | (masked(feature["prelu_q15"][out_channel], 16) << 80)
                | (masked(feature["requant_multiplier_q31"][out_channel], 32) << 48)
                | (masked(feature_raw[y, x, out_channel], 32) << 16)
                | masked(feature_expected[y, x, out_channel], 16)
            )
            feature_groups.append(f"{group:032X}")

    # Subpixel: sixteen signed INT16 input channels and four uint8 phases.
    subpixel = layers["subpixel"]
    expand_shape = manifest["files"]["expand_hwc_int16.bin"]["shape"]
    expand = np.fromfile(case_dir / "expand_hwc_int16.bin", dtype=np.int16).reshape(expand_shape)
    sub_weight = np.fromfile(
        quant_dir / subpixel["files"]["weight_bin"], dtype=np.int8
    ).reshape(subpixel["weight_shape_oihw"])
    sub_bias = np.fromfile(quant_dir / subpixel["files"]["bias_bin"], dtype="<i4")
    sub_raw = conv_integer_hwc(expand, sub_weight, sub_bias, 2).astype(np.int32)
    sub_expected = requantize(sub_raw, subpixel["requant_multiplier_q31"], 0, 255).astype(np.uint8)
    sub_golden = np.fromfile(case_dir / "subpixel_phases_hwc_uint8.bin", dtype=np.uint8).reshape(sub_expected.shape)
    if not np.array_equal(sub_expected, sub_golden):
        raise AssertionError("Subpixel result mismatch before vector export")
    padded_expand = np.pad(expand, ((2, 2), (2, 2), (0, 0)))
    sub_contributions: list[str] = []
    sub_groups: list[str] = []
    for y, x in positions(height, width):
        for out_channel in range(sub_weight.shape[0]):
            for in_channel in range(expand.shape[2]):
                window = padded_expand[y:y+5, x:x+5, in_channel]
                record = (pack_fields(window, 16) << 200) | pack_fields(sub_weight[out_channel, in_channel], 8)
                sub_contributions.append(f"{record:0150X}")
            group = (
                (masked(sub_bias[out_channel], 32) << 72)
                | (masked(subpixel["requant_multiplier_q31"][out_channel], 32) << 40)
                | (masked(sub_raw[y, x, out_channel], 32) << 8)
                | masked(sub_expected[y, x, out_channel], 8)
            )
            sub_groups.append(f"{group:026X}")

    files = {
        "feature_contributions.mem": feature_contributions,
        "feature_groups.mem": feature_groups,
        "subpixel_contributions.mem": sub_contributions,
        "subpixel_groups.mem": sub_groups,
    }
    for filename, lines in files.items():
        (output_dir / filename).write_text("\n".join(lines) + "\n", encoding="ascii")
    (output_dir / "feature_subpixel_counts.vh").write_text(
        f"`define FEATURE_GROUP_COUNT {len(feature_groups)}\n"
        f"`define SUBPIXEL_GROUP_COUNT {len(sub_groups)}\n"
        f"`define SUBPIXEL_CHANNELS {expand.shape[2]}\n",
        encoding="ascii",
    )
    print(json.dumps({
        "feature_groups": len(feature_groups),
        "subpixel_groups": len(sub_groups),
        "subpixel_contributions": len(sub_contributions),
    }, indent=2))


if __name__ == "__main__":
    main()
