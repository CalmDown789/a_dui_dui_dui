"""Offline player verification with explicit separation from browser/board checks."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

from compare_board_sequence import load_manifest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", type=Path, required=True, help="Node runtime for simulated DOM controller tests")
    args = parser.parse_args()
    manifest_path = ROOT / "artifacts/multiframe/manifest.json"
    manifest = load_manifest(manifest_path)
    scratch = ROOT / ".data/pc_player_verification"
    scratch.mkdir(parents=True, exist_ok=True)
    golden_bytes = b"".join((manifest_path.parent / frame["golden"]["path"]).read_bytes() for frame in manifest["frames"])
    exact = scratch / "software_fixture.bin"
    wrong = scratch / "software_fixture_wrong_byte.bin"
    short = scratch / "software_fixture_truncated.bin"
    exact.write_bytes(golden_bytes)
    wrong.write_bytes(bytes([golden_bytes[0] ^ 1]) + golden_bytes[1:])
    short.write_bytes(golden_bytes[:-1])
    outputs = [scratch / name for name in ("reference.html", "software_fixture_pass.html", "mismatch.html", "truncated.html")]
    for output, stream, expected_code in zip(outputs, [None, exact, wrong, short], [0, 0, 1, 1]):
        command = [sys.executable, str(ROOT / "scripts/export_pc_player.py"), "--output", str(output)]
        if stream:
            command.extend(["--stream", str(stream)])
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != expected_code:
            raise AssertionError(result.stdout + result.stderr)
    # Actual-arrival ordering is tested independently of named-file/stream mode.
    from datetime import datetime, timezone, timedelta
    from compare_board_sequence import digest
    arrivals = []
    for order,index in enumerate((7,0)):
        frame = manifest["frames"][index]
        raw = (manifest_path.parent/frame["golden"]["path"]).read_bytes()
        filename = f"arrival_{order}.bin";(scratch/filename).write_bytes(raw)
        start = datetime(2026,10,3,tzinfo=timezone.utc)+timedelta(seconds=order*2)
        arrivals.append({"frame_id":index,"order":order,"path":filename,**digest(raw),
                         "receive_status":"complete","crc_result":"NOT_CHECKED","protocol_frame_id_observed":False,
                         "first_byte_utc":start.isoformat(),"last_byte_utc":(start+timedelta(seconds=1)).isoformat()})
    received = scratch/"received_manifest.json"
    received.write_text(json.dumps({"schema":"member-a-received-frames-v1","sequence_id":manifest["sequence_id"],
        "evidence_source":"software_fixture","frame_count":2,"frames":arrivals}),encoding="utf-8",newline="\n")
    received_player = scratch/"received_order.html"
    result = subprocess.run([sys.executable,str(ROOT/"scripts/export_pc_player.py"),"--received-manifest",str(received),
                             "--output",str(received_player)],capture_output=True,text=True,encoding="utf-8")
    assert result.returncode == 1, result.stdout+result.stderr
    report_path = ROOT / "artifacts/pc_player_logic_test.json"
    command = [str(args.node), str(ROOT / "tests/check_pc_player_logic.cjs"),
               *map(str, outputs), str(report_path), str(received_player)]
    subprocess.run(command, check=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checks"]["export_cli_pass_fail_exit_codes"] = "PASS"
    report["protocol_state"] = "UNCONFIRMED"
    report["live_io_enabled"] = False
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
