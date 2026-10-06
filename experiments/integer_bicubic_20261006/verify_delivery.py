from __future__ import annotations

import json
from pathlib import Path

from .assets import file_record, sha256_file


def _verify_record(repo_root: Path, relative_path: str, expected: dict) -> None:
    path = repo_root / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_record(path)
    for key in ("bytes", "crc32", "sha256"):
        if actual[key] != expected[key]:
            raise ValueError(f"{relative_path}: {key} mismatch, expected {expected[key]}, got {actual[key]}")


def verify_delivery(repo_root: Path) -> dict:
    output_dir = repo_root / "artifacts" / "integer_bicubic_20261006"
    package = json.loads((output_dir / "golden_manifest.json").read_text(encoding="utf-8"))
    sources = json.loads((output_dir / "source_manifest.json").read_text(encoding="utf-8"))
    vectors = json.loads((output_dir / "vectors" / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "interpolation_error_report.json").read_text(encoding="utf-8"))

    if sha256_file(output_dir / "source_manifest.json") != package["source_manifest_sha256"]:
        raise ValueError("source_manifest.json hash differs from Golden manifest")
    if sha256_file(output_dir / "interp_contract.json") != package["interpolation_contract_sha256"]:
        raise ValueError("interp_contract.json hash differs from Golden manifest")
    if sha256_file(output_dir / "vectors" / "manifest.json") != package["test_vectors_manifest_sha256"]:
        raise ValueError("vector manifest hash differs from Golden manifest")
    if sha256_file(output_dir / "interpolation_error_report.json") != package["error_report_sha256"]:
        raise ValueError("error report hash differs from Golden manifest")

    def verify_nested_records(value: object) -> None:
        if isinstance(value, dict):
            if {"path", "bytes", "crc32", "sha256"}.issubset(value):
                _verify_record(repo_root, value["path"], value)
                return
            for child in value.values():
                verify_nested_records(child)
        elif isinstance(value, list):
            for child in value:
                verify_nested_records(child)

    verify_nested_records(sources)
    for filename, expected in package["coefficient_files"].items():
        _verify_record(repo_root, f"artifacts/integer_bicubic_20261006/coefficients/{filename}", expected)

    frame_records = [package["single_full_frame"], *package["contiguous_three_frame_software_sequence"]["frames"]]
    for frame in frame_records:
        for stage in ("pipeline_stage_input", "original_540p_input", "output_4k"):
            record = frame[stage]
            _verify_record(repo_root, record["path_from_repository_root"], record)
    if len(package["contiguous_three_frame_software_sequence"]["frames"]) != 3:
        raise ValueError("Expected three sequential software frames")

    vector_count = 0
    for vector in vectors["vectors"]:
        vector_count += 1
        if tuple(vector["output_shape_hw"]) != (vector["input_shape_hw"][0] * 2, vector["input_shape_hw"][1] * 2):
            raise ValueError(f"Invalid x2 vector shape: {vector['name']}")
        for filename, expected in vector["files"].items():
            _verify_record(repo_root, f"artifacts/integer_bicubic_20261006/vectors/{vector['name']}/{filename}", expected)
    if vector_count != 7:
        raise ValueError(f"Expected seven deterministic vectors, found {vector_count}")
    if report["status"] != "PASS":
        raise ValueError("Float/integer parity report is not PASS")
    for result in [report["single_full_frame"], *report["three_contiguous_frames"]]:
        if result["float64_vs_integer_final_y8"]["full_frame"]["mismatch_pixels"] != 0:
            raise ValueError(f"Float/integer mismatch in {result['id']}")
    if package["single_full_frame"]["output_4k"]["bytes"] != 3840 * 2160:
        raise ValueError("Full-size Golden has an unexpected byte count")
    return {
        "status": "PASS",
        "full_golden_bytes": package["single_full_frame"]["output_4k"]["bytes"],
        "sequence_frames": len(package["contiguous_three_frame_software_sequence"]["frames"]),
        "vectors": vector_count,
        "report_status": report["status"],
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    print(json.dumps(verify_delivery(repo_root), indent=2))


if __name__ == "__main__":
    main()
