#!/usr/bin/env python3
"""成员B工作: losslessly serialize A's fixed uint8 input for C's ROM.

No image selection or quantization is performed here. The input bytes and
SHA256 are checked against member A's full-reference manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    reference = args.delivery_root / "artifacts" / "full_reference"
    source = reference / "input_960x540_y_u8.bin"
    manifest = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    raw = source.read_bytes()
    assert len(raw) == 960 * 540, "unexpected input length"
    assert digest(raw) == manifest[source.name]["sha256"], "member A input SHA256 mismatch"
    padded = raw + bytes((1 << 19) - len(raw))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "member_a_input_960x540_y_u8.mem"
    output.write_text(
        "// 成员B工作 / Team member B: member A input bytes, zero padded for C ROM.\n"
        + "".join(f"{pixel:02X}\n" for pixel in padded),
        encoding="utf-8",
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps({
            "owner": "成员B工作 / Team member B",
            "source": str(source),
            "source_sha256": digest(raw),
            "width": 960,
            "height": 540,
            "rom_depth": 1 << 19,
            "zero_padding_bytes": len(padded) - len(raw),
            "mem_sha256": digest(output.read_bytes()),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"ACX750_MEMBER_B_C_INPUT_MEM_EXPORTED pixels={len(raw)} padded={len(padded)-len(raw)}")


if __name__ == "__main__":
    main()
