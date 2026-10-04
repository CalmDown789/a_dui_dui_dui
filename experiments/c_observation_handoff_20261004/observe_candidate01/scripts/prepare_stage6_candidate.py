from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


CANDIDATE = Path(__file__).resolve().parents[1]
JOB = CANDIDATE.parent
B_ROOT = JOB / "b_repro_reference"
attempt = sys.argv[1] if len(sys.argv) > 1 else "attempt01"
if len(sys.argv) > 2 or not attempt.replace("_", "").isalnum():
    raise SystemExit("usage: prepare_stage6_candidate.py [attempt_name]")
STAGE = CANDIDATE / "impl" / f"board150_candidate_{attempt}"
B_COMMIT = "6cc8ea4173d2a720f741e80b7cbd9279558ee93a"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(rel: str) -> str:
    data = subprocess.check_output(
        ["git", "-C", str(B_ROOT), "show", f"{B_COMMIT}:{rel}"],
        stderr=subprocess.STDOUT,
    )
    return hashlib.sha256(data).hexdigest()


if STAGE.exists():
    raise SystemExit(f"preserving existing stage directory: {STAGE}")

head = subprocess.check_output(
    ["git", "-C", str(B_ROOT), "rev-parse", "HEAD"], text=True
).strip()
if head != B_COMMIT:
    raise SystemExit(f"fixed B checkout mismatch: expected {B_COMMIT}, got {head}")

rtl = CANDIDATE / "overlay" / "multiframe" / "rtl"
candidate_files = [
    "c_config.vh",
    "input_rom.v",
    "input_stream.v",
    "stripe_buffer.v",
    "pingpong_buffer.v",
    "output_stream.v",
    "uart_tx.v",
    "readback_ctrl.v",
    "c_ctrl.v",
    "b_core_stub.v",
    "b_core_if.v",
    "c_core.v",
    "c_observation.v",
    "c_protocol_assertions.v",
    "uart_rx.v",
    "uart_frame_loader.v",
    "c_multiframe_top.v",
    "c_multiframe_synth_top.v",
]
candidate_sources = [rtl / name for name in candidate_files]

exp = B_ROOT / "experiments" / "l5_splitmem_20260924"
b_real = B_ROOT / "rtl" / "b_real_ae29515" / "stream"
b_sources_by_rel = [
    "rtl/b_real_ae29515/stream/same_pad_raster.sv",
    "experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv",
    "rtl/b_real_ae29515/stream/window_kminus1_bram.sv",
    "rtl/b_real_ae29515/stream/window_stream_frontend.sv",
    "rtl/b_real_ae29515/stream/eight_phase_issue.sv",
    "experiments/l5_splitmem_20260924/rtl/b/phase_mac_pipeline.sv",
    "experiments/l5_splitmem_20260924/rtl/b/phase_accumulator_36.sv",
    "experiments/l5_splitmem_20260924/rtl/b/mac_issue_stage.sv",
    "experiments/l5_splitmem_20260924/rtl/b/vector_postprocess_shared.sv",
    "experiments/l5_splitmem_20260924/rtl/b/fsrcnn_stream_layer.sv",
    "rtl/b_real_ae29515/stream/pixel_shuffle2x_row_banks.sv",
    "experiments/l5_splitmem_20260924/rtl/b/fsrcnn_network_core.sv",
    "rtl/b_real_ae29515/stream/fsrcnn_network_mem_top.sv",
    "rtl/b_real_ae29515/stream/b_core_real.sv",
    "experiments/l5_splitmem_20260924/rtl/b/prelu_requantize.sv",
]
b_sources = [B_ROOT / rel for rel in b_sources_by_rel]
for rel, path in zip(b_sources_by_rel, b_sources, strict=True):
    if sha(path) != git_blob_sha(rel):
        raise SystemExit(f"B source differs from pinned commit blob: {rel}")

xdc = CANDIDATE / "overlay" / "multiframe" / "constr" / "c_top.xdc"
ip_source = CANDIDATE / "ipgen_attempt06" / "ip"
ip_files = {
    "ila_obs_snapshot/ila_obs_snapshot.xci": ip_source / "ila_obs_snapshot" / "ila_obs_snapshot" / "ila_obs_snapshot.xci",
    "vio_obs_snapshot_ctrl/vio_obs_snapshot_ctrl.xci": ip_source / "vio_obs_snapshot_ctrl" / "vio_obs_snapshot_ctrl" / "vio_obs_snapshot_ctrl.xci",
}
rom_dir = B_ROOT / "rom" / "member_a_d16_s8_m1_c16"
roms = sorted(rom_dir.glob("*_packed.mem"))
if len(roms) != 19:
    raise SystemExit(f"expected 19 fixed-B parameter ROMs, found {len(roms)}")

for path in candidate_sources + b_sources + [xdc, *ip_files.values(), *roms]:
    if not path.is_file():
        raise SystemExit(f"required build input missing: {path}")

STAGE.mkdir(parents=True)
(STAGE / "ip").mkdir()
(STAGE / "reports").mkdir()
for name, path in ip_files.items():
    target = STAGE / "ip" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
for path in roms:
    shutil.copyfile(path, STAGE / path.name)

rows = []
for group, paths in (
    ("candidate_c_rtl", candidate_sources),
    ("fixed_b_rtl", b_sources),
    ("complete_c_board_xdc", [xdc]),
    ("debug_ip_xci", list(ip_files.values())),
    ("fixed_b_parameter_rom", roms),
):
    for path in paths:
        rows.append({"group": group, "path": str(path), "sha256": sha(path)})
for name in ip_files:
    path = STAGE / "ip" / name
    rows.append({"group": "stage6_copied_ip_xci", "path": str(path), "sha256": sha(path)})
for path in sorted(STAGE.glob("*_packed.mem")):
    rows.append({"group": "stage6_staged_parameter_rom", "path": str(path), "sha256": sha(path)})

manifest = {
    "status": "PREPARED",
    "stage": "6 fresh 150 MHz candidate implementation",
    "vivado_expected_version": "2025.2",
    "part": "xc7a200tfbg484-2",
    "top": "c_multiframe_synth_top",
    "candidate_root": str(CANDIDATE),
    "fixed_b_root": str(B_ROOT),
    "fixed_b_commit": B_COMMIT,
    "rom_init": "C multiframe input arrives through uart_rx; candidate top keeps test pause disabled; 19 fixed-B model parameter ROMs are staged.",
    "clock": {"board_input_MHz": 50, "core_MHz": 150, "mmcm_clkout0_divide_f": 8.0},
    "implementation_method": {
        "source": "fresh source synthesis; no prior full-design DCP reused",
        "placement_setup_uncertainty_ns": 0.3,
        "route_setup_uncertainty_ns": 0.3,
        "final_report_uncertainty_restored_ns": 0.0,
        "place_directive": "ExtraNetDelay_high",
        "phys_opt_directive": "AggressiveExplore",
        "route_directive": "NoTimingRelaxation",
        "write_bitstream": False,
    },
    "stage_directory": str(STAGE),
    "inputs": rows,
}
(STAGE / "stage6_build_manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
(STAGE / "source_files.txt").write_text(
    "\n".join(row["path"] for row in rows) + "\n", encoding="utf-8"
)
print(json.dumps({"status": "PREPARED", "stage": str(STAGE), "B_sources": len(b_sources), "C_sources": len(candidate_sources), "parameter_roms": len(roms), "xci": list(ip_files)}, ensure_ascii=False))
