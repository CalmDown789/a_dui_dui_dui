"""Software-only fault simulator for the unconfirmed Member A UART prototype.

This exercises the real PC stop-and-wait client against a deterministic fake
endpoint. It does not open a serial port, execute RTL, or establish C/board
compatibility. The simulated endpoint returns frozen Golden bytes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sys
import time

from stop_wait_client import ROOT, decode_input, digest, load_manifest, run_sequence
from capture_raw_uart import capture as capture_raw_uart
from received_frames import compare_received


SCENARIOS = {
    "normal": {"expected_capture": "COMPLETE", "expected_comparison": "PASS"},
    "delayed": {"expected_capture": "COMPLETE", "expected_comparison": "PASS"},
    "truncated": {"expected_capture": "FAIL", "expected_comparison": "FAIL"},
    "wrong_frame": {"expected_capture": "COMPLETE", "expected_comparison": "FAIL"},
    "wrong_frame_id": {"expected_capture": "FAIL", "expected_comparison": "FAIL"},
    "disconnect": {"expected_capture": "FAIL", "expected_comparison": "FAIL"},
    "reset_required": {"expected_capture": "FAIL", "expected_comparison": "FAIL"},
}


class VirtualClock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def advance(self, seconds: float) -> float:
        self.seconds += seconds
        return self.seconds

    def utc(self) -> str:
        base = datetime(2026, 10, 5, tzinfo=timezone.utc)
        return (base + timedelta(seconds=self.seconds)).isoformat()


class SimulatedEndpoint:
    """A fake UART peer with explicit, reproducible transport faults."""

    def __init__(self, manifest_path: Path, scenario: str, clock: VirtualClock,
                 *, read_chunk: int = 3071, write_chunk: int = 1021,
                 delay_seconds: float = 0.25) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        self.manifest_path = manifest_path
        self.manifest = load_manifest(manifest_path)
        self.reference_root = manifest_path.parent
        self.scenario = scenario
        self.clock = clock
        self.read_chunk = read_chunk
        self.write_chunk = write_chunk
        self.delay_seconds = delay_seconds
        self.input = bytearray()
        self.output = bytearray()
        self.accepted_frame_ids: list[int] = []
        self.read_bytes = 0
        self.output_ready_at = 0.0
        self.stale_rx_pending = scenario == "reset_required"
        self.disconnected = False
        self.events: list[str] = []

    def write(self, data: bytes) -> int:
        self.clock.advance(0.00001)
        if self.output:
            self.events.append("client_sent_next_frame_before_output_drain")
            raise OSError("stop-and-wait violation: previous output still pending")
        count = min(len(data), self.write_chunk)
        self.input.extend(data[:count])
        expected_input = self.manifest["input"]["bytes_per_frame"] + 20
        if len(self.input) == expected_input:
            frame_id, payload = decode_input(bytes(self.input))
            order = len(self.accepted_frame_ids)
            expected_frame = self.manifest["frames"][order]
            expected_input_bytes = (self.reference_root / expected_frame["input"]["path"]).read_bytes()
            expected_id = expected_frame["frame_id"] + (1 if self.scenario == "wrong_frame_id" and order == 0 else 0)
            if frame_id != expected_id:
                self.events.append(f"reject_unexpected_frame_id:got_{frame_id}_expected_{expected_id}")
                self.input.clear()
                return count
            if payload != expected_input_bytes:
                self.events.append("reject_input_payload_mismatch")
                raise OSError("endpoint rejected input payload mismatch")
            self.accepted_frame_ids.append(frame_id)
            self.input.clear()
            output_order = order
            if self.scenario == "wrong_frame" and len(self.manifest["frames"]) > 1:
                output_order = (order + 1) % len(self.manifest["frames"])
                self.events.append(f"returned_frame_{output_order}_for_input_{frame_id}")
            output_frame = self.manifest["frames"][output_order]
            raw = (self.reference_root / output_frame["golden"]["path"]).read_bytes()
            if self.scenario == "truncated" and order == 0:
                raw = raw[:-1]
                self.events.append("truncated_output_by_one_byte")
            if self.scenario == "disconnect" and order == 0:
                self.events.append("disconnect_after_32768_output_bytes")
            self.output.extend(raw)
            self.output_ready_at = self.clock.seconds + (
                self.delay_seconds if self.scenario == "delayed" else 0.0
            )
        return count

    def read(self, requested: int) -> bytes:
        self.clock.advance(0.001)
        if self.stale_rx_pending:
            self.stale_rx_pending = False
            self.events.append("stale_rx_before_first_input_reset_required")
            return b"\xA5"
        if self.scenario == "disconnect" and self.read_bytes >= 32768 and not self.disconnected:
            self.disconnected = True
            self.events.append("serial_disconnect")
            raise OSError("simulated cable/device disconnect")
        if self.clock.seconds < self.output_ready_at:
            return b""
        if not self.output:
            return b""
        count = min(requested, self.read_chunk, len(self.output))
        raw = bytes(self.output[:count])
        del self.output[:count]
        self.read_bytes += count
        return raw


class RawTxEndpoint:
    """Read-only fake peer for the current C headerless UART TX path."""

    def __init__(self, payload: bytes, scenario: str, clock: VirtualClock,
                 *, delay_seconds: float = 0.25, chunk_size: int = 4093) -> None:
        self.payload = payload
        self.scenario = scenario
        self.clock = clock
        self.delay_seconds = delay_seconds
        self.chunk_size = chunk_size
        self.offset = 0
        self.ready_at = delay_seconds if scenario == "delayed" else 0.0
        self.events: list[str] = []

    def read(self, requested: int) -> bytes:
        self.clock.advance(0.001)
        if self.clock.seconds < self.ready_at:
            return b""
        if self.scenario == "disconnect" and self.offset >= 32768:
            self.events.append("simulated_uart_disconnect")
            raise OSError("simulated cable/device disconnect")
        count = min(requested, self.chunk_size, len(self.payload) - self.offset)
        raw = self.payload[self.offset:self.offset + count]
        self.offset += len(raw)
        return raw


def run_c_tx_suite(output_root: Path, *, delay_seconds: float = 0.25) -> dict:
    single_path = ROOT / "artifacts/authority_pair/single_authority_manifest.json"
    pair_path = ROOT / "artifacts/authority_pair/manifest.json"
    single = load_manifest(single_path)
    single_golden = (single_path.parent / single["frames"][0]["golden"]["path"]).read_bytes()
    pair = load_manifest(pair_path)
    pair_golden = [(pair_path.parent / frame["golden"]["path"]).read_bytes()
                   for frame in pair["frames"]]
    cases = [
        ("normal", single_path, single_golden, "COMPLETE", "PASS", 0),
        ("delayed", single_path, single_golden, "COMPLETE", "PASS", 0),
        ("truncated", single_path, single_golden[:-1], "FAIL", "FAIL", 0),
        ("wrong_frame_order", pair_path, b"".join(reversed(pair_golden)), "COMPLETE", "FAIL", 0),
        ("disconnect", single_path, single_golden, "FAIL", "FAIL", 0),
        ("stale_byte_requires_reset", single_path, b"\xA5" + single_golden,
         "FAIL", "FAIL", 1),
        # A new reader/session models operator action after a real external reset;
        # it is not an automatic retry of the failed unframed stream.
        ("recovery_after_external_reset", single_path, single_golden,
         "COMPLETE", "PASS", 0),
    ]
    results = []
    for name, manifest_path, payload, expected_capture, expected_compare, expected_tail in cases:
        clock = VirtualClock()
        endpoint = RawTxEndpoint(payload, name, clock, delay_seconds=delay_seconds)
        session_dir = output_root / f"c_tx_{name}"
        received = capture_raw_uart(
            endpoint.read, manifest_path, session_dir,
            total_timeout=5, idle_timeout=1, tail_watch=0.01,
            clock=lambda: clock.seconds, utc=clock.utc,
            evidence_source="software_fixture",
            transport={"kind": "fake_current_c_uart_tx", "scenario": name,
                       "physical_port_opened": False, "input_bytes_sent": 0},
        )
        comparison = compare_received(manifest_path, session_dir / "received_manifest.json")
        status_ok = (received["capture_status"] == expected_capture
                     and comparison["status"] == expected_compare
                     and received["unexpected_tail_bytes"] == expected_tail)
        results.append({
            "scenario": name,
            "expected_capture": expected_capture,
            "expected_comparison": expected_compare,
            "capture_status": received["capture_status"],
            "comparison_status": comparison["status"],
            "test_verdict": "PASS" if status_ok else "FAIL",
            "received_frames": received["frame_count"],
            "received_bytes": received["bytes_received"],
            "unexpected_tail_bytes": received["unexpected_tail_bytes"],
            "failure_reason": received["failure_reason"],
            "wire_rx_sha256": received["raw_stream"]["sha256"],
            "virtual_elapsed_seconds": round(clock.seconds, 6),
            "input_bytes_sent": 0,
            "events": endpoint.events,
            "raw_session_files_committed": False,
        })
    suite_ok = all(case["test_verdict"] == "PASS" for case in results)
    return {
        "suite_verdict": "PASS" if suite_ok else "FAIL",
        "mode": "current_C_headerless_UART_TX_receive_only",
        "protocol_basis": "C top streams raw Y output without frame header, wire frame ID, CRC or ACK; no PC bytes are sent.",
        "physical_port_opened": False,
        "rtl_executed": False,
        "board_tested": False,
        "input_bytes_sent": 0,
        "wire_frame_id_available": False,
        "wrong_frame_test_limit": "Frame order/content errors are found by Golden comparison; the raw output has no wire frame ID to decode.",
        "automatic_recovery_claimed": False,
        "recovery_rule": "Stop and preserve the failed capture; begin a new receive session only after an operator-arranged external reset and known frame boundary.",
        "raw_session_files_committed": False,
        "scenarios": results,
    }


def run_suite(manifest_path: Path, output_root: Path, *, delay_seconds: float = 0.25) -> dict:
    manifest_path = manifest_path.resolve()
    if output_root.exists():
        raise ValueError(f"Refusing to overwrite simulator output directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    results = []
    for name, expected in SCENARIOS.items():
        clock = VirtualClock()
        device = SimulatedEndpoint(manifest_path, name, clock, delay_seconds=delay_seconds)
        session_dir = output_root / name
        received, comparison = run_sequence(
            device,
            manifest_path,
            session_dir,
            send_timeout=30,
            receive_timeout=5,
            idle_timeout=1,
            tail_watch=0.01,
            clock=lambda: clock.seconds,
            utc=clock.utc,
            evidence_source="software_fixture",
            transport={"kind": "deterministic_fake_uart", "scenario": name,
                       "physical_port_opened": False},
        )
        compare_started = time.perf_counter()
        compared_again = compare_received(session_dir / "reference/manifest.json",
                                          session_dir / "received_manifest.json")
        comparison_seconds = time.perf_counter() - compare_started
        send_values = [t.get("elapsed_seconds") for t in received.get("transmissions", [])
                       if isinstance(t.get("elapsed_seconds"), (int, float))]
        wait_values, return_values = [], []
        for frame in received.get("frames", []):
            first = frame.get("first_payload_read_offset_seconds")
            last = frame.get("last_payload_read_offset_seconds")
            if isinstance(first, (int, float)) and isinstance(last, (int, float)) and last >= first:
                wait_values.append(float(first))
                return_values.append(float(last - first))
        actual = {
            "capture": received["capture_status"],
            "comparison": comparison["status"],
        }
        result_ok = (actual["capture"] == expected["expected_capture"]
                     and actual["comparison"] == expected["expected_comparison"]
                     and "client_sent_next_frame_before_output_drain" not in device.events)
        results.append({
            "scenario": name,
            "expected": expected,
            "actual": actual,
            "test_verdict": "PASS" if result_ok else "FAIL",
            "input_frame_ids_accepted": device.accepted_frame_ids,
            "received_frame_count": received["frame_count"],
            "received_bytes": received.get("bytes_received", received.get("raw_stream", {}).get("bytes", 0)),
            "wire_rx_sha256": received.get("raw_stream", {}).get("sha256"),
            "unexpected_tail_bytes": received["unexpected_tail_bytes"],
            "failure_reason": received["failure_reason"],
            "virtual_elapsed_seconds": round(clock.seconds, 6),
            "stage_timings": {
                "host_send_virtual_seconds": round(sum(send_values), 6) if send_values else None,
                "host_wait_to_first_payload_virtual_seconds": round(sum(wait_values), 6) if wait_values else None,
                "host_return_read_span_virtual_seconds": round(sum(return_values), 6) if return_values else None,
                "host_session_virtual_seconds": received.get("session_elapsed_seconds"),
                "local_byte_compare_seconds": round(comparison_seconds, 6),
                "local_byte_compare_status": compared_again.get("status"),
                "player_nominal_seconds_at_2fps": received.get("frame_count", 0) / 2,
                "player_observed_seconds": None,
                "timing_basis": "software_fixture; virtual transport clock; host compare timer; playback is nominal only",
            },
            "events": device.events,
            "comparison_mismatch_bytes": sum(
                value for value in (f.get("byte_mismatch") for f in comparison["frames"])
                if isinstance(value, int)
            ),
            "raw_session_files_committed": False,
        })
    c_tx_results = run_c_tx_suite(output_root, delay_seconds=delay_seconds)
    suite_ok = (all(item["test_verdict"] == "PASS" for item in results)
                and c_tx_results["suite_verdict"] == "PASS")
    manifest_label = (manifest_path.relative_to(ROOT).as_posix()
                      if manifest_path.is_relative_to(ROOT) else manifest_path.name)
    return {
        "schema": "member-a-pc-transport-fault-simulation-v1",
        "suite_verdict": "PASS" if suite_ok else "FAIL",
        "protocol_status": "PROTOTYPE_UNCONFIRMED",
        "manifest": manifest_label,
        "manifest_is_repository_relative": manifest_path.is_relative_to(ROOT),
        "manifest_sha256": digest(manifest_path.read_bytes())["sha256"],
        "sequence_id": load_manifest(manifest_path)["sequence_id"],
        "physical_port_opened": False,
        "rtl_executed": False,
        "board_tested": False,
        "c_compatibility_verified": False,
        "raw_session_files_committed": False,
        "endpoint_behavior": "Validates the prototype input and returns frozen A Golden output bytes; fault cases deliberately alter delivery.",
        "output_frame_id_on_wire": False,
        "wrong_frame_case_limit": "Output has no wire frame ID; a shifted Golden is detected by byte comparison, not diagnosed as an observed ID field.",
        "wrong_input_id_case_limit": "The fake receiver starts with an out-of-sync expected ID and sends no output; with no ACK/status response, the PC observes timeout rather than a decoded ID error.",
        "scenarios": results,
        "current_c_uart_tx_simulation": c_tx_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "artifacts/authority_pair/manifest.json")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory for raw simulator sessions; never overwritten")
    parser.add_argument("--summary", type=Path,
                        default=ROOT / "artifacts/pc_transport_simulator_selftest.json")
    parser.add_argument("--delay-ms", type=float, default=250)
    args = parser.parse_args()
    if args.delay_ms < 0:
        parser.error("--delay-ms must be nonnegative")
    safe_root = Path("D:/Codex File/dialogue file").resolve()
    output = args.output_dir.resolve()
    summary = args.summary.resolve()
    if not output.is_relative_to(safe_root) or not summary.is_relative_to(safe_root):
        parser.error("Simulator session files and reports must remain under D:/Codex File/dialogue file")
    try:
        result = run_suite(args.manifest, output, delay_seconds=args.delay_ms / 1000.0)
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"suite_verdict": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"suite_verdict": result["suite_verdict"],
                      "prototype_scenarios": len(result["scenarios"]),
                      "current_c_uart_tx_scenarios": len(result["current_c_uart_tx_simulation"]["scenarios"]),
                      "summary": str(summary)}, ensure_ascii=False))
    return 0 if result["suite_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
