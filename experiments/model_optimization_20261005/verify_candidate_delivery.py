"""Verify an isolated experimental candidate's hashes, vectors, and full Golden."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zlib

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.artifacts import MEMBER_A_ACCEPTANCE_VECTOR_CASES
from member_a.fixed_reference import FixedReference


FROZEN_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
FROZEN_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"


def digest(path: Path) -> tuple[int, str, str]:
    data = path.read_bytes()
    return len(data), f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", hashlib.sha256(data).hexdigest()


def check_files(directory: Path, files: dict) -> None:
    for name, expected in files.items():
        size, crc32, sha256 = digest(directory / name)
        if size != expected["bytes"] or crc32 != expected["crc32"] or sha256 != expected["sha256"]:
            raise AssertionError(f"Artifact digest mismatch: {directory / name}")


def check_outputs(reference: FixedReference, input_u8: np.ndarray, manifest: dict, directory: Path) -> None:
    outputs = reference.run(input_u8)
    expected_names = set(manifest["files"])
    for name, actual in outputs.items():
        filename = f"{name}_hwc_{actual.dtype.name}.bin"
        if filename not in expected_names:
            raise AssertionError(f"Missing stage output in manifest: {filename}")
        metadata = manifest["files"][filename]
        expected = np.fromfile(directory / filename, dtype=np.dtype(metadata["dtype"]))
        expected = expected.reshape(metadata["shape"])
        if not np.array_equal(actual, expected):
            raise AssertionError(f"Integer stage mismatch: {directory.name}/{filename}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-dir", type=Path,
                        default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/candidate_delivery")
    parser.add_argument("--quant-dir", type=Path,
                        default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/evaluation_calibration_ab/candidate_quantized")
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / ".data/model_optimization/div2k_qat_mix_20261005/candidate_qat_fp32.pth")
    parser.add_argument("--recompute-full", action="store_true",
                        help="recompute all full-frame stages, not only verify their stored hashes")
    args = parser.parse_args()

    delivery = args.delivery_dir.resolve()
    quant_dir = args.quant_dir.resolve()
    checkpoint = args.checkpoint.resolve()
    summary = json.loads((delivery / "candidate_delivery_manifest.json").read_text(encoding="utf-8"))
    if summary.get("status") != "EXPERIMENTAL_NOT_RELEASED":
        raise AssertionError("Candidate delivery must remain explicitly unreleased")
    bundle_manifest_path = delivery / "bundle_manifest.json"
    bundle_verified = False
    if bundle_manifest_path.is_file():
        bundle = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
        if bundle.get("schema") != "member-a-experimental-candidate-bundle-v1":
            raise AssertionError("Unexpected candidate bundle manifest schema")
        if bundle.get("status") != "EXPERIMENTAL_NOT_RELEASED":
            raise AssertionError("Candidate bundle must remain explicitly experimental")
        expected_files = bundle.get("files", {})
        actual_files = {
            path.relative_to(delivery).as_posix()
            for path in delivery.rglob("*")
            if path.is_file() and path.name != "bundle_manifest.json"
        }
        if actual_files != set(expected_files):
            raise AssertionError("Candidate bundle file inventory mismatch")
        for name, metadata in expected_files.items():
            size, _, sha256 = digest(delivery / name)
            if size != metadata["bytes"] or sha256 != metadata["sha256"]:
                raise AssertionError(f"Candidate bundle file digest mismatch: {name}")
        if bundle.get("file_count") != len(expected_files):
            raise AssertionError("Candidate bundle file count mismatch")
        bundle_verified = True
    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant = ROOT / "artifacts/quant/quant_params.json"
    if hashlib.sha256(frozen_checkpoint.read_bytes()).hexdigest() != FROZEN_CHECKPOINT_SHA256:
        raise AssertionError("Official frozen checkpoint changed")
    if hashlib.sha256(frozen_quant.read_bytes()).hexdigest() != FROZEN_QUANT_SHA256:
        raise AssertionError("Official frozen quantization package changed")
    if hashlib.sha256((quant_dir / "quant_params.json").read_bytes()).hexdigest() != summary["candidate_quant_params_sha256"]:
        raise AssertionError("Candidate quantization parameter hash mismatch")
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != summary["candidate_checkpoint_sha256"]:
        raise AssertionError("Candidate checkpoint hash mismatch")

    reference = FixedReference(quant_dir)
    vector_root = delivery / "test_vectors_96x54"
    vector_cases = {}
    for case in MEMBER_A_ACCEPTANCE_VECTOR_CASES:
        case_dir = vector_root / case
        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        check_files(case_dir, manifest["files"])
        input_u8 = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(54, 96)
        check_outputs(reference, input_u8, manifest, case_dir)
        vector_cases[case] = "PASS"

    golden_dir = delivery / "full_integer_golden"
    manifest = json.loads((golden_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "EXPERIMENTAL_MEMBER_A_CANDIDATE":
        raise AssertionError("Candidate Golden was mislabeled as an A-confirmed release")
    check_files(golden_dir, manifest["files"])
    input_u8 = np.fromfile(golden_dir / "input_960x540_y_u8.bin", dtype=np.uint8).reshape(540, 960)
    rom = (golden_dir / "input_rom_2p19_u8.bin").read_bytes()
    if len(rom) != (1 << 19) or rom[: 960 * 540] != input_u8.tobytes() or any(rom[960 * 540:]):
        raise AssertionError("Full-frame input ROM content/padding mismatch")
    output = golden_dir / manifest["authoritative_output"]
    if digest(output)[2] != summary["full_integer_output_sha256"]:
        raise AssertionError("Full-frame output SHA-256 differs from candidate summary")

    recomputed = False
    if args.recompute_full:
        stage_manifest = manifest["stage_digests"]
        for name, values in reference.iter_outputs(input_u8):
            values = np.ascontiguousarray(values)
            metadata = stage_manifest[name]
            crc32 = f"{zlib.crc32(values.tobytes()) & 0xFFFFFFFF:08x}"
            sha256 = hashlib.sha256(values.tobytes()).hexdigest()
            if list(values.shape) != metadata["shape_hwc"] or values.dtype.name != metadata["dtype"]:
                raise AssertionError(f"Full-frame stage shape/dtype mismatch: {name}")
            if crc32 != metadata["crc32"] or sha256 != metadata["sha256"]:
                raise AssertionError(f"Full-frame stage output mismatch: {name}")
        recomputed = True

    print(json.dumps({
        "status": "PASS",
        "release_status": summary["status"],
        "portable_bundle_verified": bundle_verified,
        "frozen_assets_unchanged": True,
        "candidate_quant_sha256": summary["candidate_quant_params_sha256"],
        "candidate_checkpoint_sha256": summary["candidate_checkpoint_sha256"],
        "vector_cases": vector_cases,
        "full_frame_output_bytes": summary["full_integer_output_bytes"],
        "full_frame_output_sha256": summary["full_integer_output_sha256"],
        "recomputed_full_stages": recomputed,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
