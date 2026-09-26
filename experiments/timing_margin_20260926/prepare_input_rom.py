#!/usr/bin/env python3
"""Rebuild the frozen A input ROM from the 16 tracked banks, without Vivado.

The measured Tcl still stages the monolithic ROM although its bank16 RTL reads
the bank files. This helper fills that clean-clone dependency without changing
the measured Tcl or silently replacing an existing input.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "ref/a_full_integer_golden"
BANK_DIR = ROOT / "member_b_evidence/real_banks"
ROM_NAME = "input_rom_2p19_u8.mem"
BANK_COUNT = 16
BANK_DEPTH = 32768


def digest(data):
    return hashlib.sha256(data).hexdigest()


def expected_rom():
    manifest = json.loads((REFERENCE / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["files"][ROM_NAME]
    sums = (REFERENCE / "SHA256SUMS.txt").read_text(encoding="utf-8")
    rows = [line.split() for line in sums.splitlines() if line.strip().endswith(ROM_NAME)]
    if len(rows) != 1 or len(rows[0]) != 3:
        raise ValueError("Expected one frozen ROM entry in SHA256SUMS.txt")
    sha, size, name = rows[0]
    if name != ROM_NAME or sha != entry["sha256"] or int(size) != entry["bytes"]:
        raise ValueError("Frozen manifest and SHA256SUMS.txt disagree")
    return entry["sha256"], entry["bytes"]


def verify_rom(data, expected_sha, expected_size):
    actual = digest(data)
    if len(data) != expected_size or actual != expected_sha:
        raise ValueError(
            f"ROM mismatch: bytes={len(data)}, sha256={actual}; "
            f"expected bytes={expected_size}, sha256={expected_sha}"
        )


def reconstruct(expected_sha, expected_size):
    bank_sums = (BANK_DIR / "SOURCE_AND_BANK_SHA256.txt").read_text(encoding="ascii")
    sources = [line.split("=", 1)[1] for line in bank_sums.splitlines()
               if line.startswith("source_sha256=")]
    if sources != [expected_sha]:
        raise ValueError("Bank provenance does not match the frozen A input ROM")
    hashes = {}
    for line in bank_sums.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+(rom_bank_\d{3}\.mem)", line)
        if match:
            if match[2] in hashes:
                raise ValueError(f"Duplicate bank hash: {match[2]}")
            hashes[match[2]] = match[1]
    names = [f"rom_bank_{index:03d}.mem" for index in range(BANK_COUNT)]
    if set(hashes) != set(names):
        raise ValueError("Expected exactly 16 frozen bank hashes")
    pieces = []
    normalized = 0
    for name in names:
        raw = (BANK_DIR / name).read_bytes()
        # Git's Windows checkout may use CRLF. Only normalize that separator;
        # verify the full canonical bytes against the frozen bank digest.
        data = raw.replace(b"\r\n", b"\n")
        normalized += raw != data
        lines = data.splitlines()
        if (len(lines) != BANK_DEPTH or not data.endswith(b"\n")
                or any(re.fullmatch(rb"[0-9a-fA-F]{2}", line) is None for line in lines)):
            raise ValueError(f"Invalid bank shape or hex data: {name}")
        if digest(data) != hashes[name]:
            raise ValueError(f"Frozen bank SHA256 mismatch: {name}")
        pieces.append(data)
    data = b"".join(pieces)
    verify_rom(data, expected_sha, expected_size)
    return data, normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REFERENCE / ROM_NAME,
                        help="Output path; an existing file must match and is never overwritten")
    output = parser.parse_args().output.resolve()
    expected_sha, expected_size = expected_rom()
    data, normalized = reconstruct(expected_sha, expected_size)
    if output.exists():
        verify_rom(output.read_bytes(), expected_sha, expected_size)
        action = "VERIFIED_EXISTING"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also refuses to overwrite a file created after
        # the existence check by another process.
        with output.open("xb") as stream:
            stream.write(data)
        verify_rom(output.read_bytes(), expected_sha, expected_size)
        action = "CREATED"
    print(f"INPUT_ROM_{action} banks=16 bytes={expected_size} sha256={expected_sha}")
    print(f"output={output}")
    print(f"bank_files_with_crlf_normalized={normalized}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"INPUT_ROM_ERROR: {error}") from error
