#!/usr/bin/env python3
"""成员B工作: generate a size-parameterized five-layer integer golden set.

Uses member A's frozen exported integers and member B's independent NumPy
arithmetic. Outputs row-major HWC hex files for future RTL stream scoreboards.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from audit_member_a_delivery import (
    INT32_MAX,
    INT32_MIN,
    apply_prelu_q15,
    conv_integer_hwc,
    pixel_shuffle_x2,
    requantize,
)


def write_mem(path: Path, array: np.ndarray) -> None:
    bits = array.dtype.itemsize * 8
    mask = (1 << bits) - 1
    width = bits // 4
    path.write_text(
        "".join(f"{int(value) & mask:0{width}X}\n" for value in array.flat),
        encoding="ascii",
    )


def write_packed_mem(path: Path, array: np.ndarray) -> None:
    bits = array.dtype.itemsize * 8
    packed = 0
    for index, value in enumerate(array.flat):
        packed |= (int(value) & ((1 << bits) - 1)) << (index * bits)
    path.write_text(f"{packed:0{array.size * bits // 4}X}\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=6)
    parser.add_argument("--height", type=int, default=5)
    parser.add_argument("--seed", type=int, default=750)
    args = parser.parse_args()
    if args.width < 5 or args.height < 5:
        parser.error("width and height must be at least 5 for both window types")

    quant_dir = args.delivery_root / "artifacts" / "quant"
    spec_path = quant_dir / "quant_params.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    names = [layer["name"] for layer in spec["layers"]]
    if names != ["feature", "shrink", "mapping0", "expand", "subpixel"]:
        raise AssertionError(f"Unexpected member A layer order: {names}")

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    x = rng.integers(0, 256, size=(args.height, args.width, 1), dtype=np.uint8)
    x[0, 0, 0] = 0
    x[0, -1, 0] = 255
    x[-1, 0, 0] = 128
    x[-1, -1, 0] = 127
    write_mem(out / "input_u8.mem", x)
    current = x
    metadata: dict[str, object] = {
        "owner": "team member B",
        "width": args.width,
        "height": args.height,
        "seed": args.seed,
        "quant_params_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        "layers": [],
    }

    for layer in spec["layers"]:
        name = layer["name"]
        weight = np.fromfile(quant_dir / layer["files"]["weight_bin"], dtype=np.int8).reshape(
            layer["weight_shape_oihw"]
        )
        bias = np.fromfile(quant_dir / layer["files"]["bias_bin"], dtype="<i4")
        write_packed_mem(out / f"{name}_weights_packed.mem", weight)
        write_packed_mem(out / f"{name}_bias_packed.mem", bias)
        write_packed_mem(
            out / f"{name}_q31_packed.mem",
            np.asarray(layer["requant_multiplier_q31"], dtype=np.int32),
        )
        if layer["prelu_q15"] is not None:
            write_packed_mem(
                out / f"{name}_prelu_packed.mem",
                np.asarray(layer["prelu_q15"], dtype=np.int16),
            )
        if current.shape[2] != weight.shape[1]:
            raise AssertionError(f"Input channel mismatch: {name}")
        raw = conv_integer_hwc(current, weight, bias, int(layer["padding"][0]))
        raw = raw.astype(np.int32)
        write_mem(out / f"{name}_raw_int32.mem", raw)
        post = np.clip(apply_prelu_q15(raw, layer["prelu_q15"]), INT32_MIN, INT32_MAX)
        qmin, qmax = (0, 255) if name == "subpixel" else (-(1 << 15), (1 << 15) - 1)
        current = requantize(post, layer["requant_multiplier_q31"], qmin, qmax).astype(
            np.uint8 if name == "subpixel" else np.int16
        )
        write_mem(out / f"{name}_out.mem", current)
        metadata["layers"].append(
            {"name": name, "shape_hwc": list(current.shape), "dtype": str(current.dtype),
             "min": int(current.min()), "max": int(current.max())}
        )

    output = pixel_shuffle_x2(current)
    write_mem(out / "output_u8.mem", output)
    metadata["output_shape_hwc"] = list(output.shape)
    (out / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "size": [args.width, args.height],
                      "output_shape_hwc": list(output.shape), "layers": names}))


if __name__ == "__main__":
    main()
