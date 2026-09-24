#!/usr/bin/env python3
"""成员B工作：把冻结的 A 输入 ROM 原样拆为实验 bank16 的 16 个 ROM。"""

from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ref/a_full_integer_golden/input_rom_2p19_u8.mem"
SUMS = ROOT / "ref/a_full_integer_golden/SHA256SUMS.txt"
OUT = ROOT / "member_b_evidence/real_banks"
BANK_DEPTH = 32768
BANKS = 16


def main() -> None:
    expected = next(
        line.split()[0]
        for line in SUMS.read_text(encoding="utf-8").splitlines()
        if line.strip().endswith("input_rom_2p19_u8.mem")
    )
    raw = SOURCE.read_bytes()
    actual = sha256(raw).hexdigest()
    if actual != expected:
        raise SystemExit(f"source SHA256 mismatch: {actual} != {expected}")
    lines = raw.decode("ascii").splitlines()
    if len(lines) != BANK_DEPTH * BANKS or any(
        len(s) != 2 or any(c not in "0123456789abcdefABCDEF" for c in s)
        for s in lines
    ):
        raise SystemExit("source is not exactly 524288 one-byte hex values")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = [f"source_sha256={actual}", "source=ref/a_full_integer_golden/input_rom_2p19_u8.mem"]
    for bank in range(BANKS):
        name = f"rom_bank_{bank:03d}.mem"
        part = lines[bank * BANK_DEPTH : (bank + 1) * BANK_DEPTH]
        data = ("\n".join(part) + "\n").encode("ascii")
        (OUT / name).write_bytes(data)
        manifest.append(f"{sha256(data).hexdigest()}  {name}")
    reassembled = [
        s
        for bank in range(BANKS)
        for s in (OUT / f"rom_bank_{bank:03d}.mem").read_text(
            encoding="ascii"
        ).splitlines()
    ]
    if reassembled != lines:
        raise SystemExit("bank round-trip mismatch")
    (OUT / "SOURCE_AND_BANK_SHA256.txt").write_text(
        "\n".join(manifest) + "\n", encoding="ascii"
    )
    print(f"REAL_BANKS_PASS banks={BANKS} depth={BANK_DEPTH} source_sha256={actual}")


if __name__ == "__main__":
    main()
