#!/usr/bin/env python3
"""成员B工作: package and verify the exact C-facing five-layer source set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


RTL_FILES = (
    "rtl/stream/same_pad_raster.sv",
    "rtl/stream/elastic_fifo.sv",
    "rtl/stream/window_kminus1_bram.sv",
    "rtl/stream/window_stream_frontend.sv",
    "rtl/stream/eight_phase_issue.sv",
    "rtl/stream/phase_mac_pipeline.sv",
    "rtl/stream/phase_accumulator.sv",
    "rtl/stream/mac_issue_stage.sv",
    "rtl/stream/vector_postprocess_shared.sv",
    "rtl/stream/fsrcnn_stream_layer.sv",
    "rtl/stream/pixel_shuffle2x_row_banks.sv",
    "rtl/stream/fsrcnn_network_core.sv",
    "rtl/stream/fsrcnn_network_mem_top.sv",
    "rtl/stream/b_core_real.sv",
    "rtl/postprocess/prelu_requantize.sv",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task_root = Path(__file__).resolve().parents[1]
    repo_root = task_root.parent
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {args.output}")
    rom_dir = task_root / "rom/member_a_d16_s8_m1_c16"
    rom_manifest_bytes = (rom_dir / "manifest.json").read_bytes()
    rom_manifest = json.loads(rom_manifest_bytes)
    if len(RTL_FILES) != 15 or len(rom_manifest["files"]) != 19:
        raise ValueError("Expected exactly 15 RTL files and 19 parameter ROM files")
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
    ).strip()
    source_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=repo_root, text=True
    ).strip()
    if source_branch != "member-b-five-layer-stream":
        raise ValueError(f"Expected member B delivery branch, got {source_branch!r}")
    data_by_path: dict[str, bytes] = {}
    for relative in RTL_FILES:
        data_by_path[relative] = (task_root / relative).read_bytes()
    for item in rom_manifest["files"]:
        relative = "rom/member_a_d16_s8_m1_c16/" + item["name"]
        data = (task_root / relative).read_bytes()
        if sha256(data) != item["sha256"]:
            raise ValueError(f"Parameter ROM hash differs from B manifest: {relative}")
        data_by_path[relative] = data
    data_by_path["rom/member_a_d16_s8_m1_c16/manifest.json"] = rom_manifest_bytes
    tracked_paths = ["acx750_rtl/" + name for name in data_by_path]
    changed = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *tracked_paths],
        cwd=repo_root,
        text=True,
    ).strip()
    if changed:
        raise ValueError(f"Delivery files differ from source commit:\n{changed}")
    manifest = {
        "owner": "成员B工作 / Team member B",
        "source_branch": source_branch,
        "source_commit": source_commit,
        "top_module": "b_core_real",
        "rtl_count": len(RTL_FILES),
        "parameter_rom_count": len(rom_manifest["files"]),
        "quant_params_sha256": rom_manifest["quant_params_sha256"],
        "files": {
            name: {"bytes": len(data), "sha256": sha256(data)}
            for name, data in sorted(data_by_path.items())
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(data_by_path.items()):
            archive.writestr("acx750_rtl/" + name, data)
        archive.writestr("MEMBER_B_DELIVERY_MANIFEST.json", manifest_bytes)
    with zipfile.ZipFile(args.output) as archive:
        actual = set(archive.namelist())
        expected = {"acx750_rtl/" + path for path in data_by_path} | {
            "MEMBER_B_DELIVERY_MANIFEST.json"
        }
        if actual != expected:
            raise ValueError("Package entry set differs from manifest")
        checked = json.loads(archive.read("MEMBER_B_DELIVERY_MANIFEST.json"))
        for name, metadata in checked["files"].items():
            data = archive.read("acx750_rtl/" + name)
            if len(data) != metadata["bytes"] or sha256(data) != metadata["sha256"]:
                raise ValueError(f"Package hash mismatch: {name}")
    print(
        "MEMBER_B_C_DELIVERY_PASS",
        f"rtl={len(RTL_FILES)}",
        f"rom={len(rom_manifest['files'])}",
        f"source_commit={source_commit}",
        f"zip_sha256={sha256(args.output.read_bytes())}",
    )


if __name__ == "__main__":
    main()
