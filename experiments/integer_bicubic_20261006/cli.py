from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .integer_bicubic import resize_chunked


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the A-side fixed-point Keys bicubic x2 reference")
    parser.add_argument("input", type=Path, help="raw row-major Y8 input file")
    parser.add_argument("output", type=Path, help="raw row-major Y8 output file")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--row-chunk", type=int, default=16)
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0:
        parser.error("width and height must be positive")
    expected_bytes = args.width * args.height
    raw = args.input.read_bytes()
    if len(raw) != expected_bytes:
        parser.error(f"input has {len(raw)} bytes; expected {expected_bytes}")
    image = np.frombuffer(raw, dtype=np.uint8).reshape(args.height, args.width)
    output, _, _ = resize_chunked(image, row_chunk=args.row_chunk, include_stages=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output.tobytes(order="C"))
    print(f"PASS {args.width}x{args.height} -> {args.width * 2}x{args.height * 2}: {args.output}")


if __name__ == "__main__":
    main()
