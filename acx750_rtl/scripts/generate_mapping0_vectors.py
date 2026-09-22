#!/usr/bin/env python3
"""Generate compact mapping0 convolution-to-postprocess RTL vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from audit_member_a_delivery import apply_prelu_q15, conv_integer_hwc, requantize


def masked(value: int, bits: int) -> int:
    return int(value) & ((1 << bits) - 1)


def pack_little_fields(values: np.ndarray, bits: int) -> int:
    word = 0
    for index, value in enumerate(values.reshape(-1)):
        word |= masked(int(value), bits) << (index * bits)
    return word


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
    layer = next(item for item in spec["layers"] if item["name"] == "mapping0")

    input_metadata = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))["files"]["shrink_hwc_int16.bin"]
    x = np.fromfile(case_dir / "shrink_hwc_int16.bin", dtype=np.int16).reshape(input_metadata["shape"])
    weight = np.fromfile(
        quant_dir / layer["files"]["weight_bin"], dtype=np.int8
    ).reshape(layer["weight_shape_oihw"])
    bias = np.fromfile(quant_dir / layer["files"]["bias_bin"], dtype="<i4")
    raw = conv_integer_hwc(x, weight, bias, padding=1).astype(np.int32)
    post_prelu = apply_prelu_q15(raw, layer["prelu_q15"])
    expected = requantize(
        post_prelu, layer["requant_multiplier_q31"], -(1 << 15), (1 << 15) - 1
    ).astype(np.int16)
    golden = np.fromfile(case_dir / "mapping0_hwc_int16.bin", dtype=np.int16).reshape(expected.shape)
    if not np.array_equal(expected, golden):
        raise AssertionError("Generated mapping0 result does not match member A golden data")

    height, width, channels = x.shape
    positions = ((0, 0), (0, width-1), (height-1, 0), (height-1, width-1), (height//2, width//2))
    padded = np.pad(x, ((1, 1), (1, 1), (0, 0)))
    contributions: list[str] = []
    groups: list[str] = []
    for y, x_pos in positions:
        for out_channel in range(weight.shape[0]):
            for in_channel in range(channels):
                window = padded[y:y+3, x_pos:x_pos+3, in_channel]
                kernel = weight[out_channel, in_channel]
                word = (pack_little_fields(window, 16) << 72) | pack_little_fields(kernel, 8)
                contributions.append(f"{word:054X}")
            group = (
                (masked(bias[out_channel], 32) << 96)
                | (masked(layer["prelu_q15"][out_channel], 16) << 80)
                | (masked(layer["requant_multiplier_q31"][out_channel], 32) << 48)
                | (masked(raw[y, x_pos, out_channel], 32) << 16)
                | masked(expected[y, x_pos, out_channel], 16)
            )
            groups.append(f"{group:032X}")

    (output_dir / "mapping0_contributions.mem").write_text("\n".join(contributions) + "\n", encoding="ascii")
    (output_dir / "mapping0_groups.mem").write_text("\n".join(groups) + "\n", encoding="ascii")
    (output_dir / "mapping0_vector_counts.vh").write_text(
        f"`define MAPPING0_GROUP_COUNT {len(groups)}\n"
        f"`define MAPPING0_CHANNELS {channels}\n",
        encoding="ascii",
    )
    print(json.dumps({"groups": len(groups), "contributions": len(contributions), "positions": positions}, indent=2))


if __name__ == "__main__":
    main()
