"""Read a raw 1080p Y8 board capture and generate a timed 4K Y8 PC result."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.pc_postprocess_4k import INPUT_HEIGHT, INPUT_WIDTH, OUTPUT_BYTES, process_1080_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Raw row-major 1920x1080 Y8 input, exactly 2073600 bytes")
    parser.add_argument("--frame-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New raw row-major 3840x2160 Y8 output path")
    parser.add_argument("--report", type=Path, required=True, help="New JSON record path")
    args = parser.parse_args()
    if args.output.resolve() == args.report.resolve():
        raise ValueError("Output bytes and JSON timing report must use separate paths")
    for path in (args.output, args.report):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    input_bytes = args.input.read_bytes()
    expected = INPUT_HEIGHT * INPUT_WIDTH
    if len(input_bytes) != expected:
        raise ValueError(f"Input must contain exactly {expected} bytes, got {len(input_bytes)}")
    source = np.frombuffer(input_bytes, dtype=np.uint8).reshape(INPUT_HEIGHT, INPUT_WIDTH)
    result = process_1080_frame(args.frame_id, source)
    if result.y_u8.nbytes != OUTPUT_BYTES:
        raise RuntimeError("Unexpected 4K Y8 output length")
    output_bytes = result.y_u8.tobytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_bytes)
    record = {
        "schema": "member-a-pc-postprocess-frame-record-v1",
        "frame_id": str(args.frame_id),
        "input_path": str(args.input.resolve()),
        "input_bytes": len(input_bytes),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "output_path": str(args.output.resolve()),
        "output_bytes": len(output_bytes),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "started_monotonic_ns": result.started_monotonic_ns,
        "finished_monotonic_ns": result.finished_monotonic_ns,
        "duration_ms": result.duration_ms,
        "clock_semantics": "PC monotonic clock around local 1080p-to-4K processing only; not comparable to FPGA cycles or host/network timestamps from another process.",
    }
    args.report.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
