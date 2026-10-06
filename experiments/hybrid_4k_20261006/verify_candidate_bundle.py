from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zlib

import numpy as np

from member_a.fixed_reference import FixedReference


def _digest(path: Path) -> dict[str, str | int]:
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _stage_metadata(values: np.ndarray) -> dict[str, object]:
    array = np.ascontiguousarray(values)
    raw = array.tobytes(order="C")
    return {
        "shape_hwc": list(array.shape),
        "dtype": array.dtype.name,
        "layout": "HWC_row_major",
        "minimum": int(array.min()),
        "maximum": int(array.max()),
        "bytes": len(raw),
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify candidate file digests and exact integer vectors/Golden")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.bundle_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        root.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Candidate bundle must remain under ignored .data/: {root}") from exc

    bundle_manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    checked_files = 0
    for relative, expected in bundle_manifest["files"].items():
        actual = _digest(root / relative)
        if actual != expected:
            raise AssertionError(f"Bundle digest mismatch: {relative}")
        checked_files += 1

    reference = FixedReference(root / "quant")
    vectors_root = root / "test_vectors"
    vector_count = 0
    for case_dir in sorted(path for path in vectors_root.iterdir() if path.is_dir()):
        input_bytes = (case_dir / "input_y_u8.bin").read_bytes()
        input_image = np.frombuffer(input_bytes, dtype=np.uint8).reshape(54, 96)
        for name, values in reference.iter_outputs(input_image):
            output_path = case_dir / f"{name}_hwc_{values.dtype.name}.bin"
            if output_path.read_bytes() != np.ascontiguousarray(values).tobytes(order="C"):
                raise AssertionError(f"Integer vector mismatch: {case_dir.name}/{output_path.name}")
            vector_count += 1

    golden_root = root / "full_integer_candidate_gold" / "full_integer_golden"
    golden_manifest = json.loads((golden_root / "manifest.json").read_text(encoding="utf-8"))
    full_input = np.fromfile(golden_root / "input_960x540_y_u8.bin", dtype=np.uint8).reshape(540, 960)
    stage_count = 0
    for name, values in reference.iter_outputs(full_input):
        if _stage_metadata(values) != golden_manifest["stage_digests"][name]:
            raise AssertionError(f"Full-frame stage mismatch: {name}")
        stage_count += 1

    print(json.dumps({
        "status": "PASS_EXPERIMENTAL_CANDIDATE_BUNDLE_INTEGRITY_AND_INTEGER_REFERENCE",
        "checked_package_files": checked_files,
        "checked_vector_stages": vector_count,
        "checked_full_frame_stages": stage_count,
        "limitations": "This validates A-side files and Python integer reference only; not B RTL, synthesis, FPGA, or board.",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
