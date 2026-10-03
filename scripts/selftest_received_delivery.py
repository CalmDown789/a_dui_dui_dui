"""Full-size receive-manifest error tests with explicitly synthetic software logs."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import shutil
import subprocess
import sys
from compare_board_sequence import load_manifest, digest

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    expected = ROOT/"artifacts/multiframe/manifest.json"
    manifest = load_manifest(expected)
    scratch = ROOT/".data/received_manifest_selftest";scratch.mkdir(parents=True,exist_ok=True)
    records = []
    start = datetime(2026,10,3,tzinfo=timezone.utc)
    for order,frame in enumerate(manifest["frames"]):
        filename = f"arrival_{order:03d}.bin"
        shutil.copyfile(expected.parent/frame["golden"]["path"],scratch/filename)
        records.append({"frame_id":frame["frame_id"],"order":order,"path":filename,
                        **digest((scratch/filename).read_bytes()),"receive_status":"complete",
                        "crc_result":"NOT_CHECKED","protocol_frame_id_observed":False,
                        "first_byte_utc":(start+timedelta(seconds=order*2)).isoformat(),
                        "last_byte_utc":(start+timedelta(seconds=order*2+1)).isoformat()})
    base = {"schema":"member-a-received-frames-v1","sequence_id":manifest["sequence_id"],
            "frame_count":8,"evidence_source":"software_fixture","timestamp_source":"synthetic_test_schedule",
            "frames":records}
    checks = []
    for name in ("exact","missing","repeat","reorder","crc_failed","one_byte","short","long"):
        data = json.loads(json.dumps(base))
        if name == "missing": data["frames"].pop(3)
        elif name == "repeat": data["frames"][3] = dict(data["frames"][2],order=3)
        elif name == "reorder": data["frames"][2],data["frames"][3] = data["frames"][3],data["frames"][2]
        elif name == "crc_failed": data["frames"][3]["crc_result"] = "FAIL"
        elif name in ("one_byte","short","long"):
            raw = (scratch/records[3]["path"]).read_bytes()
            changed = raw[:123]+bytes([raw[123]^1])+raw[124:] if name == "one_byte" else raw[:-1] if name == "short" else raw+b"\0"
            modified = scratch/f"{name}.bin";modified.write_bytes(changed)
            data["frames"][3].update(path=modified.name,**digest(changed))
        data["frame_count"] = len(data["frames"])
        received = scratch/f"{name}_received_manifest.json"
        received.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8",newline="\n")
        report_path = scratch/f"{name}_comparison.json"
        command = [sys.executable,str(ROOT/"scripts/compare_received_frames.py"),"--manifest",str(expected),
                   "--received-manifest",str(received),"--report",str(report_path)]
        result = subprocess.run(command,capture_output=True,text=True,encoding="utf-8")
        expected_exit = 0 if name == "exact" else 1
        assert result.returncode == expected_exit,result.stdout+result.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if name == "one_byte":
            assert report["frames"][3]["byte_mismatch"] == 1
            assert report["frames"][3]["first_error"]["byte_offset"] == 123
        checks.append({"case":name,"command":command,"exit_code":result.returncode,"expected_exit_code":expected_exit,
                       "report":str(report_path.relative_to(ROOT)),"observed_status":report["status"],"test_status":"PASS"})
    target = ROOT/"artifacts/received_manifest_selftest.json"
    target.write_text(json.dumps({"status":"PASS","checks":checks,"board_capture_tested":False,
        "fixture_source":"Copied Golden and deliberately corrupted files; synthetic timestamps; no UART/network input"},indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":"PASS","full_size_cases":len(checks),"board_capture_tested":False}))
