#!/usr/bin/env python3
"""成员B工作: pack member A's audited integer assets for the B RTL ROM.

This script only changes serialization. It does not choose or alter weights,
quantization, or the network topology owned by member A.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_packed(path: Path, values: np.ndarray) -> None:
    bits = values.dtype.itemsize * 8
    packed = 0
    for index, value in enumerate(values.flat):
        packed |= (int(value) & ((1 << bits) - 1)) << (index * bits)
    path.write_text(
        "// 成员B工作 / Team member B: packed from audited member A integers.\n"
        + f"{packed:0{values.size * bits // 4}X}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    quant = args.delivery_root / "artifacts" / "quant"
    spec_path = quant / "quant_params.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    expected = ["feature", "shrink", "mapping0", "expand", "subpixel"]
    if [item["name"] for item in spec["layers"]] != expected:
        raise AssertionError("member A layer order changed")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "owner": "成员B工作 / Team member B",
        "source": "member A audited integer delivery",
        "quant_params_sha256": sha256(spec_path),
        "files": [],
    }
    for layer in spec["layers"]:
        name = layer["name"]
        weight_path = quant / layer["files"]["weight_bin"]
        bias_path = quant / layer["files"]["bias_bin"]
        weight = np.fromfile(weight_path, dtype=np.int8).reshape(layer["weight_shape_oihw"])
        bias = np.fromfile(bias_path, dtype="<i4")
        entries = [
            (f"{name}_weights_packed.mem", weight, weight_path),
            (f"{name}_bias_packed.mem", bias, bias_path),
            (f"{name}_q31_packed.mem", np.asarray(layer["requant_multiplier_q31"], dtype=np.int32), spec_path),
        ]
        if layer["prelu_q15"] is not None:
            entries.append((
                f"{name}_prelu_packed.mem",
                np.asarray(layer["prelu_q15"], dtype=np.int16),
                spec_path,
            ))
        for filename, values, source in entries:
            destination = args.output_dir / filename
            write_packed(destination, values)
            manifest["files"].append({
                "name": filename,
                "elements": int(values.size),
                "bits_per_element": int(values.dtype.itemsize * 8),
                "source_sha256": sha256(source),
                "sha256": sha256(destination),
            })
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"ACX750_MEMBER_B_PARAMETER_ROM_EXPORTED files={len(manifest['files'])}")


if __name__ == "__main__":
    main()
