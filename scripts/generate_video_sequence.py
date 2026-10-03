from pathlib import Path
import argparse
import sys
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from member_a.multiframe import generate_sequence

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate eight exact-integer video frame Golden outputs")
    parser.add_argument("--input-stream", type=Path, default=ROOT / ".data/public_sequence/sequence_960x540_y_u8.bin")
    parser.add_argument("--source", type=Path, default=ROOT / ".data/public_sequence/source.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/multiframe")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    generate_sequence(ROOT, args.input_stream, args.source, args.output_dir)
