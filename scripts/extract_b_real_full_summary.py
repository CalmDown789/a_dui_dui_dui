#!/usr/bin/env python3
"""Turn a completed full-frame XSim log into a compact, auditable summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "_sim" / "tb_b_real_full" / "xsim.log"
DEFAULT_OUT = ROOT / "report" / "b_real_full_summary.json"


def require_int(log: str, label: str) -> int:
    match = re.search(r"^\s*" + re.escape(label) + r"\s*:\s*(\d+)", log, re.M)
    if not match:
        raise ValueError(f"completed log lacks '{label}'")
    return int(match.group(1))


def require_pair(log: str, label: str) -> tuple[int, int]:
    match = re.search(
        r"^\s*" + re.escape(label) + r"\s*:\s*(\d+)\s*/\s*(\d+)",
        log,
        re.M,
    )
    if not match:
        raise ValueError(f"completed log lacks '{label}'")
    return int(match.group(1)), int(match.group(2))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    raw = args.log.read_bytes()
    log = raw.decode("utf-8", errors="replace")
    if "FULL FRAME 960x540 -> 1920x1080" not in log:
        raise ValueError("log does not contain the completed full-frame table")
    results = re.findall(r"^RESULT:\s*(PASS|FAIL)\b", log, re.M)
    # Vivado echoes the XSim tail into the same capture after `exit`, so the
    # final RESULT line can appear twice. Require a consistent verdict.
    if not results or len(set(results)) != 1:
        raise ValueError("log must have a consistent final RESULT line")

    fed, n_input = require_pair(log, "input beats fed")
    got, n_output = require_pair(log, "output bytes received")
    matched, match_total = require_pair(log, "byte match")
    mismatched = require_int(log, "mismatched bytes")
    x_bytes = require_int(log, "X bytes")
    stripes = require_int(log, "stripe_last pulses")
    frames = require_int(log, "frame_last pulses")
    done = require_int(log, "done pulses")
    hold_violations = require_int(log, "hold-rule violations")
    cycles = require_int(log, "sim cycles")
    if not (n_input == 518400 and n_output == match_total == 2073600):
        raise ValueError("unexpected geometry/count in full-frame log")
    if matched + mismatched != n_output or got != n_output:
        raise ValueError("byte totals in full-frame log disagree")
    if results[0] == "PASS" and mismatched:
        raise ValueError("PASS marker conflicts with mismatch count")

    vendor = json.loads((ROOT / "_b_vendor_manifest.json").read_text(encoding="utf-8"))
    golden = ROOT / "ref" / "a_full_integer_golden" / "output_1920x1080_y_u8.bin"
    golden_sha = sha256(golden)
    if golden_sha != "be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e":
        raise ValueError("A integer Golden SHA-256 does not match frozen reference")
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    summary = {
        "schema": "b-real-full-xsim-summary-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tool": "Vivado/XSim 2022.2",
        "c_base_commit": git_sha,
        "b_source_commit": vendor["commit"],
        "log_path": str(args.log.resolve().relative_to(ROOT)),
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "a_integer_golden_sha256": golden_sha,
        "verdict": results[0],
        "input_beats": {"fed": fed, "expected": n_input},
        "output_bytes": {"received": got, "expected": n_output},
        "byte_match": matched,
        "byte_mismatch": mismatched,
        "x_bytes": x_bytes,
        "stripe_last_pulses": stripes,
        "frame_last_pulses": frames,
        "done_pulses": done,
        "hold_rule_violations": hold_violations,
        "sim_cycles": cycles,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out} verdict={results[0]} mismatched={mismatched}/{n_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
