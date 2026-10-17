"""Read-only identity check for the Member A EMA v2 candidate handoff.

This checks files, embedded manifests and summary consistency. It does not
perform model inference, RTL simulation, FPGA implementation or board testing.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "artifacts/member_a_handoff/ema_v2_clearance_manifest_20261017.json"
CANDIDATE_DIR = ROOT / "experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2"
GOLDEN_ZIP = ROOT / "experiments/model_optimization_20261005/evaluation/bbb_ema_v2_20261014/A_EMA_V2_NATURAL8_GOLDEN_20261014.zip"
QUALITY_SUMMARY = ROOT / "experiments/model_optimization_20261005/evaluation/official_div2k_valid_ema_v2_20261013/summary.json"
C_CLOSURE_ZIP = ROOT / "artifacts/member_a_handoff/received/A_TASK_CLOSURE_20261016.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_file(path: Path, expected: dict) -> None:
    if not path.is_file():
        raise ValueError(f"Missing: {path}")
    if path.stat().st_size != expected["bytes"]:
        raise ValueError(f"Size mismatch: {path}")
    if sha256_file(path) != expected["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path}")


def check_candidate_bundle(manifest: dict) -> None:
    bundle = json.loads((CANDIDATE_DIR / "bundle_manifest.json").read_text(encoding="utf-8"))
    if bundle["file_count"] != manifest["candidate_bundle_file_count"]:
        raise ValueError("Candidate bundle file count changed")
    if len(bundle["files"]) != bundle["file_count"]:
        raise ValueError("Candidate bundle manifest count is inconsistent")
    if bundle["candidate_checkpoint_sha256"] != manifest["files"][0]["sha256"]:
        raise ValueError("Candidate checkpoint identity changed")
    if bundle["candidate_quant_params_sha256"] != manifest["files"][1]["sha256"]:
        raise ValueError("Candidate quantization identity changed")
    for relative, expected in bundle["files"].items():
        check_file(CANDIDATE_DIR / relative, expected)
    print(f"PASS candidate bundle: {bundle['file_count']} files")


def check_natural8() -> None:
    with ZipFile(GOLDEN_ZIP) as archive:
        if archive.testzip() is not None:
            raise ValueError("Natural8 ZIP CRC failure")
        golden = json.loads(archive.read("manifest.json"))
        expected_names = set(golden["files"]) | {"manifest.json", "README.md"}
        if set(archive.namelist()) != expected_names or len(golden["files"]) != 16:
            raise ValueError("Natural8 ZIP member set changed")
        for name, expected in golden["files"].items():
            data = archive.read(name)
            if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError(f"Natural8 ZIP member mismatch: {name}")
    print("PASS Natural8 ZIP: 8 inputs + 8 integer outputs")


def check_quality(manifest: dict) -> None:
    quality = json.loads(QUALITY_SUMMARY.read_text(encoding="utf-8"))
    metrics = quality["groups"]["DIV2K_official_valid_100"]
    if quality["candidate_checkpoint_sha256"] != manifest["files"][0]["sha256"]:
        raise ValueError("Quality report uses a different checkpoint")
    if quality["candidate_quant_params_sha256"] != manifest["files"][1]["sha256"]:
        raise ValueError("Quality report uses different quantization parameters")
    difference = metrics["candidate_integer_psnr_db"] - metrics["frozen_integer_psnr_db"]
    if metrics["samples"] != 100 or not math.isclose(
        difference, metrics["candidate_integer_delta_vs_frozen_db"], abs_tol=1e-12
    ):
        raise ValueError("Quality summary is internally inconsistent")
    print(f"PASS DIV2K 100-image summary identity: paired mean {difference:+.4f} dB")


def check_quality_hash_list() -> None:
    directory = QUALITY_SUMMARY.parent
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        if sha256_file(directory / relative) != expected:
            raise ValueError(f"Published DIV2K SHA256SUMS mismatch: {relative}")
    print("PASS DIV2K published SHA256SUMS")


def check_git_tree(manifest: dict) -> None:
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if probe.returncode != 0:
        print("SKIP Git tree check: no Git checkout")
        return
    for item in manifest["files"]:
        relative = item["path"]
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"], cwd=ROOT, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise ValueError(f"Missing from HEAD: {relative}")
        if len(result.stdout) != item["bytes"] or hashlib.sha256(result.stdout).hexdigest() != item["sha256"]:
            raise ValueError(f"Git HEAD blob differs from release manifest: {relative}")
    print(f"PASS Git HEAD blobs: {len(manifest['files'])} pinned files")


def check_received_archives() -> None:
    b_path = ROOT / "artifacts/member_a_handoff/received/B_A_EMA_V2_REPRO_20261013_v2.zip"
    with ZipFile(b_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Received B ZIP CRC failure")
    receipt_path = C_CLOSURE_ZIP.with_name(C_CLOSURE_ZIP.name + ".receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["sha256"] != sha256_file(C_CLOSURE_ZIP) or receipt["bytes"] != C_CLOSURE_ZIP.stat().st_size:
        raise ValueError("Received C ZIP does not match its receipt")
    with ZipFile(C_CLOSURE_ZIP) as archive:
        if archive.testzip() is not None:
            raise ValueError("Received C ZIP CRC failure")
        delivery = json.loads(archive.read("results/DELIVERY_MANIFEST.json"))
        names = {entry.filename for entry in archive.infolist()}
        if names != {item["file"] for item in delivery["files"]} | {"results/DELIVERY_MANIFEST.json"}:
            raise ValueError("Received C ZIP member set changed")
        for item in delivery["files"]:
            data = archive.read(item["file"])
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Received C ZIP member mismatch: {item['file']}")
        status = json.loads(archive.read("results/FINAL_STATUS.json"))
        if status["formal_R0_replaced"] or status["whole_system_4K30_achieved"]:
            raise ValueError("Received C conclusion changed; review handoff wording")
    print("PASS received B/C archive integrity; this does not re-audit original hardware")


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["status"] != "A_ASSETS_VERIFIED_CANDIDATE_ONLY_NOT_R0_REPLACEMENT":
        raise ValueError("Unexpected handoff status")
    for item in manifest["files"]:
        check_file(ROOT / item["path"], item)
    print(f"PASS release manifest: {len(manifest['files'])} pinned files")
    check_candidate_bundle(manifest)
    check_natural8()
    check_quality(manifest)
    check_quality_hash_list()
    check_received_archives()
    check_git_tree(manifest)
    print("PASS A-side candidate handoff identity only; R0 remains frozen")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
