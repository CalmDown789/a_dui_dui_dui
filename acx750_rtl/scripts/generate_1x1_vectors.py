#!/usr/bin/env python3
"""Generate real member-A vectors for shrink and expand 1x1 RTL paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from audit_member_a_delivery import apply_prelu_q15, conv_integer_hwc, requantize


def masked(value: int, bits: int) -> int:
    return int(value) & ((1 << bits) - 1)


def export_layer(root: Path, layer: dict, input_name: str, expected_name: str) -> tuple[list[str], list[str], int]:
    quant_dir = root / "artifacts" / "quant"
    case_dir = root / "artifacts" / "test_vectors" / "random"
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    input_shape = manifest["files"][input_name]["shape"]
    x = np.fromfile(case_dir / input_name, dtype=np.int16).reshape(input_shape)
    weight = np.fromfile(
        quant_dir / layer["files"]["weight_bin"], dtype=np.int8
    ).reshape(layer["weight_shape_oihw"])
    bias = np.fromfile(quant_dir / layer["files"]["bias_bin"], dtype="<i4")
    raw = conv_integer_hwc(x, weight, bias, 0).astype(np.int32)
    expected = requantize(
        apply_prelu_q15(raw, layer["prelu_q15"]),
        layer["requant_multiplier_q31"], -(1 << 15), (1 << 15)-1,
    ).astype(np.int16)
    golden = np.fromfile(case_dir / expected_name, dtype=np.int16).reshape(expected.shape)
    if not np.array_equal(expected, golden):
        raise AssertionError(f"{layer['name']} result mismatch before vector export")

    height, width, channels = x.shape
    positions = ((0, 0), (0, width-1), (height-1, 0), (height-1, width-1), (height//2, width//2))
    contributions: list[str] = []
    groups: list[str] = []
    for y, x_pos in positions:
        for out_channel in range(weight.shape[0]):
            for in_channel in range(channels):
                record = (masked(x[y, x_pos, in_channel], 16) << 8) | masked(weight[out_channel, in_channel, 0, 0], 8)
                contributions.append(f"{record:06X}")
            group = (
                (masked(bias[out_channel], 32) << 96)
                | (masked(layer["prelu_q15"][out_channel], 16) << 80)
                | (masked(layer["requant_multiplier_q31"][out_channel], 32) << 48)
                | (masked(raw[y, x_pos, out_channel], 32) << 16)
                | masked(expected[y, x_pos, out_channel], 16)
            )
            groups.append(f"{group:032X}")
    return contributions, groups, channels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.delivery_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = json.loads((root / "artifacts" / "quant" / "quant_params.json").read_text(encoding="utf-8"))
    layers = {layer["name"]: layer for layer in spec["layers"]}
    shrink_c, shrink_g, shrink_channels = export_layer(
        root, layers["shrink"], "feature_hwc_int16.bin", "shrink_hwc_int16.bin"
    )
    expand_c, expand_g, expand_channels = export_layer(
        root, layers["expand"], "mapping0_hwc_int16.bin", "expand_hwc_int16.bin"
    )
    for filename, lines in {
        "shrink_contributions.mem": shrink_c,
        "shrink_groups.mem": shrink_g,
        "expand_contributions.mem": expand_c,
        "expand_groups.mem": expand_g,
    }.items():
        (output_dir / filename).write_text("\n".join(lines) + "\n", encoding="ascii")
    (output_dir / "conv1x1_counts.vh").write_text(
        f"`define SHRINK_GROUP_COUNT {len(shrink_g)}\n"
        f"`define SHRINK_CHANNELS {shrink_channels}\n"
        f"`define EXPAND_GROUP_COUNT {len(expand_g)}\n"
        f"`define EXPAND_CHANNELS {expand_channels}\n",
        encoding="ascii",
    )
    print(json.dumps({
        "shrink_groups": len(shrink_g), "shrink_contributions": len(shrink_c),
        "expand_groups": len(expand_g), "expand_contributions": len(expand_c),
    }, indent=2))


if __name__ == "__main__":
    main()
