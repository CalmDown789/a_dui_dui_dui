from pathlib import Path
import argparse
import json
import sys
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from member_a.multiframe import verify_sequence

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check all sequence assets; optionally recompute every integer layer")
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/multiframe/manifest.json")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(4)
    report = verify_sequence(ROOT, args.manifest, recompute=args.recompute)
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    print(text)
