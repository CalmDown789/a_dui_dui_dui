from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.artifacts import generate_full_integer_golden


def main() -> None:
    output_dir = ROOT / "artifacts" / "full_integer_golden"
    manifest = generate_full_integer_golden(
        ROOT / "artifacts" / "quant",
        ROOT / "artifacts" / "full_reference" / "input_960x540_y_u8.bin",
        output_dir,
    )
    output_meta = manifest["stage_digests"]["output"]
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "output": manifest["authoritative_output"],
                "shape_hwc": output_meta["shape_hwc"],
                "crc32": output_meta["crc32"],
                "sha256": output_meta["sha256"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
