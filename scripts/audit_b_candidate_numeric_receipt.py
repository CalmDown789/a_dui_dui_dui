"""Verify B's delivered EMA-v2 numeric receipt against A's exact assets.

This audit checks archive integrity, the inner file manifest, A/B candidate
identity, B's reported stage results, and the two saved XSim outputs against
A's candidate Goldens. It does not rerun XSim or imply synthesis/board signoff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_stage_records(value, result: list[dict]) -> None:
    if isinstance(value, dict):
        if "case" in value and "stage" in value and "B_reference_sha256" in value:
            result.append(value)
        for child in value.values():
            find_stage_records(child, result)
    elif isinstance(value, list):
        for child in value:
            find_stage_records(child, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True,
                        help="Extracted B_A_CANDIDATE_NUMERIC package root")
    parser.add_argument("--b-zip", type=Path, required=True)
    parser.add_argument("--b-sha256-file", type=Path, required=True)
    parser.add_argument("--a-return-dir", type=Path, required=True,
                        help="A-to-B candidate return containing the exact two full-frame Goldens")
    parser.add_argument("--a-return-zip", type=Path, required=True)
    parser.add_argument("--a-return-sha256-file", type=Path, required=True)
    parser.add_argument("--a-candidate-dir", type=Path, required=True,
                        help="A branch candidate_delivery/R0_QAT_EMA_seed20261006_v2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    b_zip = args.b_zip.resolve()
    a_return_dir = args.a_return_dir.resolve()
    a_return_zip = args.a_return_zip.resolve()
    a_candidate_dir = args.a_candidate_dir.resolve()
    output = args.output.resolve()
    require(not output.exists(), f"Refusing to overwrite existing output: {output}")

    b_zip_sha = sha256_file(b_zip)
    b_sidecar = args.b_sha256_file.read_text(encoding="utf-8-sig").split()[0].lower()
    require(b_zip_sha == b_sidecar, "B ZIP SHA-256 differs from supplied sidecar")
    a_return_sha = sha256_file(a_return_zip)
    a_return_sidecar = args.a_return_sha256_file.read_text(encoding="utf-8-sig").split()[0].lower()
    require(a_return_sha == a_return_sidecar, "A-to-B ZIP SHA-256 differs from supplied sidecar")

    with zipfile.ZipFile(b_zip) as archive:
        bad_member = archive.testzip()
        require(bad_member is None, f"B ZIP CRC failed at {bad_member}")

    manifest_path = package_dir / "PACKAGE_MANIFEST.json"
    manifest = load_json(manifest_path)
    require(manifest.get("package_id") == "B_A_CANDIDATE_NUMERIC_20261009_v1", "Unexpected package ID")
    require(manifest.get("candidate_id") == "R0_QAT_EMA_seed20261006_v2", "Unexpected candidate ID")
    require(manifest.get("status") == "PASS_CANDIDATE_NUMERIC_ONLY_NOT_IMPLEMENTED_OR_BOARD_ACCEPTED",
            "Package status overstates or changes its acceptance boundary")
    expected_files = {entry["file"]: entry for entry in manifest.get("files", [])}
    actual_files = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file() and path.name != "PACKAGE_MANIFEST.json"
    }
    require(actual_files == set(expected_files), "Extracted inventory differs from B package manifest")
    for relative, metadata in expected_files.items():
        path = package_dir / relative
        require(path.stat().st_size == metadata["bytes"], f"Byte count differs: {relative}")
        require(sha256_file(path) == metadata["sha256"], f"SHA-256 differs: {relative}")

    candidate_checkpoint = a_candidate_dir / "training/candidate_ema_qat_fp32.pth"
    candidate_quant = a_candidate_dir / "quant/quant_params.json"
    b_quant = package_dir / "candidate_identity/quant_params.json"
    require(candidate_checkpoint.is_file() and candidate_quant.is_file() and b_quant.is_file(),
            "Missing A/B candidate identity files")
    checkpoint_sha = sha256_file(candidate_checkpoint)
    quant_sha = sha256_file(candidate_quant)
    require(sha256_file(b_quant) == quant_sha, "B quantization parameters differ from A candidate")
    require(checkpoint_sha == manifest.get("checkpoint_sha256") ==
            "10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a",
            "Candidate checkpoint identity differs from A's frozen candidate hash")
    require(quant_sha == manifest.get("quant_params_sha256") ==
            "12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809",
            "Candidate quantization identity differs from A's frozen candidate hash")

    results = load_json(package_dir / "reports/RESULTS.json")
    require(results.get("status") == manifest["status"], "B results status differs from package status")
    require(results.get("candidate_zip_sha256") == a_return_sha,
            "B did not verify the exact A-to-B return ZIP")
    require(results.get("checkpoint_sha256") == checkpoint_sha and results.get("quant_params_sha256") == quant_sha,
            "B results identity differs from A candidate")
    roms = results.get("packed_candidate_ROMs", [])
    require(len(roms) == 19, "Expected exactly 19 packed candidate ROMs")
    for rom in roms:
        path = package_dir / "candidate_rom" / rom["file"]
        require(path.is_file() and path.stat().st_size == rom["bytes"] and
                sha256_file(path) == rom["sha256"], f"Candidate ROM differs: {rom['file']}")
        require(rom.get("independent_checkpoint_and_unpack_match") is True,
                f"ROM not marked as independently reconstructed: {rom['file']}")

    small = results.get("small_layer_summary", [])
    require(len(small) == 12 and all(stage.get("mismatch_elements") == 0 for stage in small),
            "One or more small-vector stages reports mismatches")
    require(results.get("small_stage_checks") == 96, "Expected 96 normal/backpressure/reset stage checks")
    require(results.get("post_extremes", {}).get("mismatch_elements", 0) == 0,
            "Postprocess extremes report contains mismatches")

    golden = load_json(package_dir / "reports/INDEPENDENT_GOLDEN_REPORT.json")
    stage_records: list[dict] = []
    find_stage_records(golden, stage_records)
    require(stage_records, "Independent Golden report contains no stage identity records")
    bad_stages = [entry for entry in stage_records
                  if entry.get("hash_matches") is not True or entry.get("mismatch_elements", 0) != 0]
    require(not bad_stages, f"Independent Golden report has {len(bad_stages)} failed stage records")

    full_outputs = [entry for entry in results.get("full_frames", []) if entry.get("stage") == "output"]
    require(len(full_outputs) == 2 and all(entry.get("mismatch_elements") == 0 for entry in full_outputs),
            "Expected two passing full-frame output records")
    output_paths = [package_dir / "runs/full/actual_0.bin", package_dir / "runs/full/actual_1.bin"]
    frame_rows = []
    for frame_id, actual_path in enumerate(output_paths):
        a_frame_dir = a_return_dir / f"vectors/full_frames/frame_{frame_id:04d}"
        a_manifest = load_json(a_frame_dir / "manifest.json")
        golden_path = a_frame_dir / a_manifest["candidate_output_file"]
        actual_sha = sha256_file(actual_path)
        golden_sha = sha256_file(golden_path)
        result_record = next(item for item in full_outputs if item.get("case") == f"frame_{frame_id:04d}")
        require(actual_path.stat().st_size == 1920 * 1080 and
                actual_sha == result_record.get("actual_sha256") == result_record.get("candidate_golden_sha256") == golden_sha,
                f"Full-frame output {frame_id} differs from A candidate Golden")
        input_path = a_frame_dir / a_manifest["input_file"]
        input_sha = sha256_file(input_path)
        frame_rows.append({
            "frame_id": frame_id,
            "input_sha256": input_sha,
            "input_bytes": input_path.stat().st_size,
            "rtl_output_bytes": actual_path.stat().st_size,
            "rtl_output_sha256": actual_sha,
            "candidate_golden_sha256": golden_sha,
            "mismatch_bytes": 0,
        })
    require(sum(row["rtl_output_bytes"] for row in frame_rows) == 4_147_200,
            "Two full-frame outputs do not total 4,147,200 bytes")

    simulator = results.get("simulator_versions", {})
    require(results.get("candidate_synthesis_implementation_or_BIT_performed") is False,
            "Receipt unexpectedly claims candidate implementation")
    require(results.get("candidate_board_IO_performed") is False,
            "Receipt unexpectedly claims candidate board I/O")
    require(results.get("formal_R0_replaced") is False, "Receipt unexpectedly replaces formal R0")
    require(results.get("whole_system_4K30_achieved") is False, "Receipt overstates 4K30 acceptance")

    audit = {
        "schema": "member-a-b-ema-v2-numeric-receipt-audit-v1",
        "status": "PASS_B_CANDIDATE_NUMERIC_RECEIPT_AND_A_IDENTITIES",
        "acceptance_scope": "B's supplied XSim numerical result and two full-frame outputs were identity-checked against A's exact candidate ZIP/Goldens. This audit did not rerun XSim, synthesize, place/route, generate a candidate BIT, or perform board I/O.",
        "package": {
            "package_id": manifest["package_id"],
            "status": manifest["status"],
            "b_receipt_zip_sha256": b_zip_sha,
            "a_return_zip_sha256": a_return_sha,
            "manifest_file_count": len(expected_files),
            "all_manifest_files_verified": True,
            "zip_crc_test": "PASS",
        },
        "candidate_identity": {
            "candidate_id": manifest["candidate_id"],
            "checkpoint_sha256": checkpoint_sha,
            "quant_params_sha256": quant_sha,
            "candidate_ROM_count": len(roms),
            "candidate_ROMs_verified_against_B_report": True,
        },
        "B_numerical_results": {
            "simulator_versions": simulator,
            "small_stage_checks": results["small_stage_checks"],
            "small_summary_stage_count": len(small),
            "small_stage_mismatches": 0,
            "independent_Golden_stage_records": len(stage_records),
            "independent_Golden_stage_failures": 0,
            "full_frames": frame_rows,
            "full_output_bytes_total": sum(row["rtl_output_bytes"] for row in frame_rows),
            "synthesis_or_implementation": False,
            "candidate_BIT_generated": False,
            "board_IO": False,
            "formal_R0_replaced": False,
            "whole_system_4K30": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "verified_manifest_files": len(expected_files),
                      "verified_ROMs": len(roms), "small_stage_checks": results["small_stage_checks"],
                      "full_output_bytes": audit["B_numerical_results"]["full_output_bytes_total"],
                      "audit": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
