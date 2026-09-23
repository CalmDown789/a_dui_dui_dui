from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import zlib

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference


def _digest(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", hashlib.sha256(data).hexdigest()


def verify() -> dict:
    quant_dir = ROOT / "artifacts" / "quant"
    vectors_dir = ROOT / "artifacts" / "test_vectors"
    spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    if spec["model"] != "FSRCNNSubpixel-d16-s8-m1-c16-x2":
        raise AssertionError("Unexpected model in quant_params.json")

    missing_formats: list[str] = []
    for layer in spec["layers"]:
        for stem in ("weight", "bias"):
            for extension in ("npy", "bin", "mem", "coe"):
                key = f"{stem}_{extension}"
                if key not in layer["files"] or not (quant_dir / layer["files"][key]).is_file():
                    missing_formats.append(f"{layer['name']}:{key}")
        if layer["prelu_q15"] is not None:
            for extension in ("npy", "bin", "mem", "coe"):
                key = f"prelu_{extension}"
                if key not in layer["files"] or not (quant_dir / layer["files"][key]).is_file():
                    missing_formats.append(f"{layer['name']}:{key}")
    if missing_formats:
        raise FileNotFoundError(f"Missing integer export formats: {missing_formats}")

    reference = FixedReference(quant_dir)
    cases: dict[str, str] = {}
    for case in ("zero", "impulse", "ramp", "random"):
        case_dir = vectors_dir / case
        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        for filename, metadata in manifest["files"].items():
            crc32, sha256 = _digest(case_dir / filename)
            if crc32 != metadata["crc32"] or sha256 != metadata["sha256"]:
                raise AssertionError(f"Digest mismatch: {case}/{filename}")

        image = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(54, 96)
        outputs = reference.run(image)
        for name, actual in outputs.items():
            filename = f"{name}_hwc_{actual.dtype.name}.bin"
            metadata = manifest["files"][filename]
            expected = np.fromfile(case_dir / filename, dtype=np.dtype(metadata["dtype"]))
            expected = expected.reshape(metadata["shape"])
            if not np.array_equal(actual, expected):
                raise AssertionError(f"Golden-reference mismatch: {case}/{filename}")
        cases[case] = manifest["files"]["output_hwc_uint8.bin"]["sha256"]

    full_dir = ROOT / "artifacts" / "full_integer_golden"
    full_manifest = json.loads((full_dir / "manifest.json").read_text(encoding="utf-8"))
    if full_manifest["status"] != "A_CONFIRMED_INTEGER_GOLDEN":
        raise AssertionError("Full-frame integer Golden is not A-confirmed")
    for filename, metadata in full_manifest["files"].items():
        crc32, sha256 = _digest(full_dir / filename)
        if crc32 != metadata["crc32"] or sha256 != metadata["sha256"]:
            raise AssertionError(f"Full-frame digest mismatch: {filename}")

    full_input = (full_dir / "input_960x540_y_u8.bin").read_bytes()
    full_rom = (full_dir / "input_rom_2p19_u8.bin").read_bytes()
    if len(full_input) != 960 * 540 or len(full_rom) != 1 << 19:
        raise AssertionError("Unexpected full-frame input or ROM size")
    if full_rom[: len(full_input)] != full_input or any(full_rom[len(full_input) :]):
        raise AssertionError("Full-frame ROM prefix/padding mismatch")
    full_output = full_dir / full_manifest["authoritative_output"]
    if full_output.stat().st_size != 1920 * 1080:
        raise AssertionError("Unexpected full-frame integer output size")

    return {
        "status": "PASS",
        "model": spec["model"],
        "layers": [layer["name"] for layer in spec["layers"]],
        "cases": cases,
        "full_integer_golden": {
            "status": full_manifest["status"],
            "output": full_manifest["authoritative_output"],
            "sha256": full_manifest["stage_digests"]["output"]["sha256"],
        },
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, ensure_ascii=False))
