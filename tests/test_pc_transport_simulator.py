from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "experiments/member_a_uart_prototype_20261003/host/transport_simulator.py"
sys.path.insert(0, str(FILE.parent))
spec = importlib.util.spec_from_file_location("pc_transport_simulator", FILE)
simulator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simulator)


def test_fault_simulation_detects_transport_failures_and_keeps_provenance(tmp_path):
    manifest = ROOT / "artifacts/authority_pair/manifest.json"
    report = simulator.run_suite(manifest, tmp_path / "sessions", delay_seconds=0.025)
    assert report["suite_verdict"] == "PASS"
    assert report["physical_port_opened"] is False
    assert report["rtl_executed"] is False
    assert report["board_tested"] is False
    assert report["c_compatibility_verified"] is False
    assert report["raw_session_files_committed"] is False
    by_name = {case["scenario"]: case for case in report["scenarios"]}
    assert set(by_name) == set(simulator.SCENARIOS)
    assert by_name["normal"]["actual"] == {"capture": "COMPLETE", "comparison": "PASS"}
    assert len(by_name["normal"]["wire_rx_sha256"]) == 64
    assert "session_dir" not in by_name["normal"]
    assert by_name["delayed"]["actual"] == {"capture": "COMPLETE", "comparison": "PASS"}
    assert by_name["truncated"]["received_bytes"] == 2_073_599
    assert by_name["wrong_frame"]["comparison_mismatch_bytes"] > 0
    assert by_name["wrong_frame_id"]["input_frame_ids_accepted"] == []
    assert "idle_timeout" in by_name["wrong_frame_id"]["failure_reason"]
    assert "disconnect" in by_name["disconnect"]["failure_reason"].lower()
    assert by_name["reset_required"]["input_frame_ids_accepted"] == []


def test_simulator_refuses_to_overwrite_sessions(tmp_path):
    manifest = ROOT / "artifacts/authority_pair/manifest.json"
    output = tmp_path / "sessions"
    output.mkdir()
    try:
        simulator.run_suite(manifest, output)
    except ValueError as error:
        assert "overwrite" in str(error)
    else:
        raise AssertionError("existing simulator data must not be overwritten")
