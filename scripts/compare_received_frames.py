"""Compare received frames in their recorded arrival order; exit 0 PASS, 1 FAIL."""
from pathlib import Path
import argparse
import json
import sys
from received_frames import compare_received

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--received-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare_received(args.manifest, args.received_manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"status": "FAIL", "error": str(error)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] == "PASS" else 1)
