#!/usr/bin/env python3
"""Export member-A Q31 multipliers into RTL-friendly member-B derived files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quant-params", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.quant_params.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "owner": "member B derived RTL initialization files",
        "source_model": spec["model"],
        "source_quant_params_sha256": hashlib.sha256(args.quant_params.read_bytes()).hexdigest(),
        "format": "signed Q31, 32-bit two's complement, one channel per line",
        "layers": {},
    }
    for layer in spec["layers"]:
        values = [int(value) for value in layer["requant_multiplier_q31"]]
        if any(value < -(1 << 31) or value > (1 << 31)-1 for value in values):
            raise OverflowError(f"Q31 multiplier does not fit signed INT32: {layer['name']}")
        stem = f"{layer['name']}_requant_q31"
        binary = b"".join(struct.pack("<i", value) for value in values)
        (args.output_dir / f"{stem}.bin").write_bytes(binary)
        encoded = [f"{value & 0xFFFFFFFF:08X}" for value in values]
        (args.output_dir / f"{stem}.mem").write_text("\n".join(encoded) + "\n", encoding="ascii")
        (args.output_dir / f"{stem}.coe").write_text(
            "memory_initialization_radix=16;\n"
            "memory_initialization_vector=\n"
            + ",\n".join(encoded)
            + ";\n",
            encoding="ascii",
        )
        manifest["layers"][layer["name"]] = {
            "channels": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "files": [f"{stem}.bin", f"{stem}.mem", f"{stem}.coe"],
        }
    (args.output_dir / "requant_q31_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
