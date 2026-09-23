from __future__ import annotations

import argparse
from pathlib import Path
import hashlib
import json
import sys
import zlib

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference


def _digest_bytes(data: bytes) -> tuple[str, str]:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", hashlib.sha256(data).hexdigest()


def _array_digest(values: np.ndarray) -> tuple[str, str]:
    return _digest_bytes(np.ascontiguousarray(values).tobytes(order="C"))


def verify(recompute: bool = False) -> dict[str, object]:
    golden_dir = ROOT / "artifacts" / "full_integer_golden"
    manifest = json.loads((golden_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "A_CONFIRMED_INTEGER_GOLDEN":
        raise AssertionError("Full integer Golden is not marked A-confirmed")
    if manifest["golden_class"] != "full_frame_integer_bit_exact":
        raise AssertionError("Unexpected Golden class")

    for filename, metadata in manifest["files"].items():
        path = golden_dir / filename
        data = path.read_bytes()
        crc32, sha256 = _digest_bytes(data)
        if len(data) != metadata["bytes"] or crc32 != metadata["crc32"] or sha256 != metadata["sha256"]:
            raise AssertionError(f"Digest mismatch: {filename}")

    raw_input = (golden_dir / "input_960x540_y_u8.bin").read_bytes()
    rom = (golden_dir / "input_rom_2p19_u8.bin").read_bytes()
    if len(raw_input) != 960 * 540:
        raise AssertionError("Input byte count is not 960x540")
    if len(rom) != 1 << 19:
        raise AssertionError("Padded ROM byte count is not 2^19")
    if rom[: len(raw_input)] != raw_input or any(rom[len(raw_input) :]):
        raise AssertionError("ROM prefix/padding does not match the A-confirmed input")

    output_path = golden_dir / manifest["authoritative_output"]
    if output_path.stat().st_size != 1920 * 1080:
        raise AssertionError("Authoritative output byte count is not 1920x1080")

    recomputed = False
    if recompute:
        input_u8 = np.frombuffer(raw_input, dtype=np.uint8).reshape(540, 960)
        reference = FixedReference(ROOT / "artifacts" / "quant")
        for name, values in reference.iter_outputs(input_u8):
            crc32, sha256 = _array_digest(values)
            expected = manifest["stage_digests"][name]
            if list(values.shape) != expected["shape_hwc"] or values.dtype.name != expected["dtype"]:
                raise AssertionError(f"Stage metadata mismatch: {name}")
            if crc32 != expected["crc32"] or sha256 != expected["sha256"]:
                raise AssertionError(f"Stage byte mismatch: {name}")
            if name == "output" and values.tobytes(order="C") != output_path.read_bytes():
                raise AssertionError("Authoritative output is not byte-identical to recomputation")
        recomputed = True

    output_meta = manifest["stage_digests"]["output"]
    return {
        "status": "PASS",
        "golden_status": manifest["status"],
        "recomputed_all_integer_stages": recomputed,
        "input_bytes": len(raw_input),
        "rom_bytes": len(rom),
        "output_bytes": output_path.stat().st_size,
        "output_crc32": output_meta["crc32"],
        "output_sha256": output_meta["sha256"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify the A-confirmed full-frame integer Golden")
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="rerun all integer layers and compare every stage digest and final byte stream",
    )
    args = parser.parse_args()
    print(json.dumps(verify(recompute=args.recompute), indent=2, ensure_ascii=False))
