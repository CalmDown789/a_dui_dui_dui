"""Convert one raw 960x540 Y frame to a C input-ROM file without changing its bytes."""
from pathlib import Path
import argparse
import hashlib

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--depth", type=int, default=1 << 19)
    args = parser.parse_args()
    data = args.input.read_bytes()
    if len(data) != 518400 or args.depth < len(data):
        parser.error("Requires 518400 input bytes and ROM depth >= 518400")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    padded = data + bytes(args.depth - len(data))
    with args.output.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("".join(f"{value:02x}\n" for value in padded))
    print(f"input_sha256={hashlib.sha256(data).hexdigest()}; words={len(padded)}; zero_pad={len(padded)-len(data)}")
