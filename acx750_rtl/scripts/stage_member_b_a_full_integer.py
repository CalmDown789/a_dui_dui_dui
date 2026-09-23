#!/usr/bin/env python3
"""成员B工作: stage verified A full-frame bytes for the RTL scoreboard."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zlib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a-delivery-root", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    golden = args.a_delivery_root / "artifacts/full_integer_golden"
    manifest = json.loads((golden / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "A_CONFIRMED_INTEGER_GOLDEN":
        raise ValueError("A full integer Golden is not confirmed")
    quant_bytes = (args.a_delivery_root / "artifacts/quant/quant_params.json").read_bytes()
    if hashlib.sha256(quant_bytes).hexdigest() != manifest["quant_params"]["sha256"]:
        raise ValueError("A quantization version does not match Golden")
    for name, metadata in manifest["files"].items():
        data = (golden / name).read_bytes()
        if (len(data) != metadata["bytes"] or
                f"{zlib.crc32(data):08x}" != metadata["crc32"] or
                hashlib.sha256(data).hexdigest() != metadata["sha256"]):
            raise ValueError(f"A Golden digest mismatch: {name}")
    input_bytes = (golden / "input_960x540_y_u8.bin").read_bytes()
    output_bytes = (golden / "output_1920x1080_y_u8.bin").read_bytes()
    rom_bytes = (golden / "input_rom_2p19_u8.bin").read_bytes()
    if len(input_bytes) != 960 * 540 or len(output_bytes) != 1920 * 1080:
        raise ValueError("Unexpected full-frame dimensions")
    if len(rom_bytes) != 1 << 19 or rom_bytes[:len(input_bytes)] != input_bytes or any(rom_bytes[len(input_bytes):]):
        raise ValueError("A input ROM does not match raw input")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("input_u8.mem", input_bytes), ("output_u8.mem", output_bytes)):
        (args.output_dir / name).write_text("".join(f"{byte:02X}\n" for byte in data), encoding="ascii")
    rom_manifest = json.loads((args.rom_dir / "manifest.json").read_text(encoding="utf-8"))
    if rom_manifest["quant_params_sha256"] != manifest["quant_params"]["sha256"]:
        raise ValueError("B parameter ROMs originate from a different A quantization version")
    if len(rom_manifest["files"]) != 19:
        raise ValueError("Expected 19 B parameter ROM files")
    for metadata in rom_manifest["files"]:
        path = args.rom_dir / metadata["name"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError(f"B parameter ROM digest mismatch: {path.name}")
        shutil.copy2(path, args.output_dir / path.name)
    print("A_FULL_INTEGER_STAGE_PASS", "input_bytes=518400", "output_bytes=2073600",
          f"output_sha256={hashlib.sha256(output_bytes).hexdigest()}")


if __name__ == "__main__":
    main()
