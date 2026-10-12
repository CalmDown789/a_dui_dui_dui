"""Audit a historical C 150 MHz raw board capture through A's PC 4K step.

This is a characterization audit, not current-BIT, natural-video, display, or
end-to-end real-time acceptance. It binds every output to the saved board
capture and verifies the A integer reference before checking the PC result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True,
                        help="C board run directory containing input_sequence.json, programming.json, capture/")
    parser.add_argument("--fixture-dir", type=Path, required=True,
                        help="Directory with the four input and expected Y8 fixture binaries")
    parser.add_argument("--crosscheck-json", type=Path, required=True,
                        help="A-side historical board-vs-integer-reference audit JSON")
    parser.add_argument("--pc-results-dir", type=Path, required=True,
                        help="Directory containing frame_NNNN_4k_y.bin and frame_NNNN_timing.json")
    parser.add_argument("--quant-dir", type=Path, default=ROOT / "artifacts/quant")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    session_dir = args.session_dir.resolve()
    fixture_dir = args.fixture_dir.resolve()
    crosscheck_path = args.crosscheck_json.resolve()
    pc_dir = args.pc_results_dir.resolve()
    output_path = args.output.resolve()
    need(not output_path.exists(), f"Refusing to overwrite existing audit: {output_path}")

    sequence_path = session_dir / "input_sequence.json"
    programming_path = session_dir / "programming.json"
    capture_session_path = session_dir / "capture/session.json"
    sequence = load_json(sequence_path)
    programming = load_json(programming_path)
    capture_session = load_json(capture_session_path)
    crosscheck = load_json(crosscheck_path)

    need(sequence.get("status") == "PASS_FIXED_16_FRAME_SEQUENCE", "Unexpected input-sequence status")
    need(sequence.get("frame_count") == 16 and len(sequence.get("input_sequence", [])) == 16,
         "Expected exactly 16 input-sequence frames")
    need(programming.get("status") == "BOARD_CAPTURE_PASS_16_FRAME_BIT_EXACT", "Unexpected C programming status")
    need(programming.get("board_signoff") == "PASS_16_FRAME_CONTINUOUS_BIT_EXACT", "Unexpected C board signoff")
    need(programming.get("frequency_mhz") == 150 and programming.get("vivado_version") == "2025.2",
         "Unexpected historical run tool/frequency")
    need(capture_session.get("status") == "PASS_BIT_EXACT" and capture_session.get("frame_count") == 16,
         "Unexpected capture-session status")
    need(capture_session.get("geometry_in") == "960x540 uint8 Y row-major" and
         capture_session.get("geometry_out") == "1920x1080 uint8 Y row-major",
         "Unexpected C capture geometry")
    need(crosscheck.get("status") == "PASS_HISTORICAL_C_BOARD_RETURNS_MATCH_A_INTEGER_REFERENCE",
         "A-side board crosscheck is not PASS")
    need(any("150_attempt02" in name for name in crosscheck.get("sessions", [])),
         "Crosscheck does not cover the selected 150 MHz session")

    quant_path = args.quant_dir.resolve() / "quant_params.json"
    need(quant_path.is_file(), f"Missing R0 quantization parameters: {quant_path}")
    reference = FixedReference(args.quant_dir.resolve())
    capture_rows = capture_session.get("frames", [])
    need(len(capture_rows) == 16, "Capture session does not contain 16 frame records")

    reference_cache: dict[int, bytes] = {}
    rows: list[dict] = []
    for expected_id, (input_meta, capture_meta) in enumerate(zip(sequence["input_sequence"], capture_rows)):
        need(input_meta.get("frame_id") == expected_id and capture_meta.get("frame_id") == expected_id,
             f"Frame order/ID mismatch at {expected_id}")
        input_path = fixture_dir / Path(input_meta["input_path"]).name
        expected_path = fixture_dir / Path(input_meta["expected_path"]).name
        board_path = session_dir / "capture" / f"frame_{expected_id:04d}_y.bin"
        pc_output_path = pc_dir / f"frame_{expected_id:04d}_4k_y.bin"
        pc_report_path = pc_dir / f"frame_{expected_id:04d}_timing.json"
        for path in (input_path, expected_path, board_path, pc_output_path, pc_report_path):
            need(path.is_file(), f"Missing required frame artifact: {path}")

        input_sha = sha256_file(input_path)
        expected_sha = sha256_file(expected_path)
        board_sha = sha256_file(board_path)
        need(input_path.stat().st_size == 960 * 540 and expected_path.stat().st_size == 1920 * 1080,
             f"Unexpected fixture size for frame {expected_id}")
        need(input_sha == input_meta.get("input_sha256") == capture_meta.get("input_sha256"),
             f"Input SHA mismatch for frame {expected_id}")
        need(expected_sha == input_meta.get("expected_sha256") == capture_meta.get("expected_sha256"),
             f"Expected-output SHA mismatch for frame {expected_id}")
        need(board_path.stat().st_size == 1920 * 1080 and board_sha == capture_meta.get("output_sha256"),
             f"Board-output identity mismatch for frame {expected_id}")
        need(board_path.read_bytes() == expected_path.read_bytes(),
             f"Board output differs from C/A expected output at frame {expected_id}")

        fixture_id = int(input_meta["fixture_frame_id"])
        if fixture_id not in reference_cache:
            image = np.fromfile(input_path, dtype=np.uint8).reshape(540, 960)
            reference_cache[fixture_id] = reference.run(image)["output"].tobytes(order="C")
        need(reference_cache[fixture_id] == expected_path.read_bytes(),
             f"Saved C expected output differs from recomputed A R0 reference for fixture {fixture_id}")

        pc_record = load_json(pc_report_path)
        pc_sha = sha256_file(pc_output_path)
        need(str(pc_record.get("frame_id")) == str(expected_id), f"PC record frame ID mismatch at {expected_id}")
        need(pc_record.get("input_sha256") == board_sha and pc_record.get("input_bytes") == 1920 * 1080,
             f"PC record is not bound to this board output at frame {expected_id}")
        need(pc_output_path.stat().st_size == 3840 * 2160 and
             pc_record.get("output_bytes") == 3840 * 2160 and pc_record.get("output_sha256") == pc_sha,
             f"PC output size/hash mismatch at frame {expected_id}")

        rows.append({
            "frame_id": expected_id,
            "fixture_frame_id": fixture_id,
            "input_sha256": input_sha,
            "expected_1080p_sha256": expected_sha,
            "board_1080p_sha256": board_sha,
            "board_vs_a_reference_mismatch_bytes": 0,
            "pc_4k_sha256": pc_sha,
            "pc_4k_bytes": pc_output_path.stat().st_size,
            "pc_postprocess_ms": float(pc_record["duration_ms"]),
            "c_host_frame_elapsed_s": capture_meta.get("host_frame_elapsed_seconds"),
            "c_output_receive_s": capture_meta.get("output_receive_seconds"),
        })

    times = np.asarray([row["pc_postprocess_ms"] for row in rows], dtype=np.float64)
    unique_pc_outputs = len({row["pc_4k_sha256"] for row in rows})
    need(unique_pc_outputs == 4, f"Expected four distinct PC outputs from four repeated fixture inputs, got {unique_pc_outputs}")
    need(all(rows[i]["pc_4k_sha256"] == rows[i % 4]["pc_4k_sha256"] for i in range(16)),
         "Repeated fixture frames did not produce repeatable 4K outputs")

    result = {
        "schema": "member-a-historical-board150-to-pc4k-audit-v1",
        "status": "PASS_HISTORICAL_R0_BOARD_TO_A_PC_POSTPROCESS",
        "scope": {
            "run_date": "2026-10-04 historical C capture",
            "board_frequency_mhz": programming["frequency_mhz"],
            "vivado_version": programming["vivado_version"],
            "part": programming.get("part"),
            "bit_sha256": programming.get("bit_sha256"),
            "protocol": capture_session.get("protocol"),
            "unique_test_inputs": 4,
            "sequence_frames": 16,
            "sequence_pattern": "four fixed distinct inputs repeated four times",
            "natural_video": False,
            "actual_4k_board_capture": False,
            "pc_4k_outputs_are_software_derived_from_saved_board_1080p": True,
            "current_c_bit_or_ema_candidate": False,
        },
        "identity": {
            "a_r0_quant_params_sha256": sha256_file(quant_path),
            "c_programming_json_sha256": sha256_file(programming_path),
            "c_input_sequence_sha256": sha256_file(sequence_path),
            "c_capture_session_sha256": sha256_file(capture_session_path),
            "a_board_crosscheck_sha256": sha256_file(crosscheck_path),
            "a_board_crosscheck_status": crosscheck["status"],
        },
        "counts": {
            "frames_checked": len(rows),
            "unique_inputs_recomputed_with_a_fixed_reference": len(reference_cache),
            "board_1080p_mismatches": sum(row["board_vs_a_reference_mismatch_bytes"] > 0 for row in rows),
            "pc_4k_outputs": len(rows),
            "distinct_pc_4k_outputs": unique_pc_outputs,
            "pc_4k_bytes_total": sum(row["pc_4k_bytes"] for row in rows),
        },
        "pc_postprocess_timing_ms": {
            "mean": float(times.mean()),
            "median": float(np.median(times)),
            "p95": float(np.percentile(times, 95)),
            "min": float(times.min()),
            "max": float(times.max()),
            "scope": "local PC monotonic time around 1080p-to-4K Keys resize only; excludes serial transfer, FPGA compute, rendering, and display refresh",
        },
        "acceptance_boundary": "This confirms a historical 150 MHz R0 board capture against recomputed A integer 1080p outputs and applies A's PC software Keys x2 step to those exact captures. It is not the current C BIT, EMA candidate, natural-video quality evaluation, captured/displayed 4K output, or sustained real-time system acceptance.",
        "frames": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "frames": len(rows), "unique_a_references": len(reference_cache),
                      "mean_pc_postprocess_ms": result["pc_postprocess_timing_ms"]["mean"],
                      "p95_pc_postprocess_ms": result["pc_postprocess_timing_ms"]["p95"],
                      "report": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
