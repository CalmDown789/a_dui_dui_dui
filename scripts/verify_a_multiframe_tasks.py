"""Record execution, exit codes, timing and logs of Member A software acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import platform
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node",type=Path,required=True)
    args = parser.parse_args()
    logs = ROOT/"results/multiframe/logs";logs.mkdir(parents=True,exist_ok=True)
    commands = [
        ("original_authority_recompute",[sys.executable,"-c","import sys,json,torch; sys.path.insert(0,'scripts'); import verify_full_integer_golden as v; torch.set_num_threads(4); print(json.dumps(v.verify(True),indent=2))"]),
        ("eight_frames_recompute",[sys.executable,"scripts/verify_video_sequence.py","--recompute","--report","artifacts/multiframe/verification.json"]),
        ("authority_pair_recompute",[sys.executable,"scripts/verify_video_sequence.py","--manifest","artifacts/authority_pair/manifest.json","--recompute","--report","artifacts/authority_pair/verification.json"]),
        ("safe_directory_reproduction",[sys.executable,"scripts/check_sequence_reproduction.py","--regenerated",".data/repro_sequence_20261003_final/manifest.json"]),
        ("player_controller",[sys.executable,"scripts/verify_pc_player.py","--node",str(args.node)]),
        ("receive_manifest_faults",[sys.executable,"scripts/selftest_received_delivery.py"]),
        ("package_build",[sys.executable,"scripts/package_video_sequence.py"]),
        ("portable_software_tests",[sys.executable,"scripts/selftest_video_delivery.py"]),
        ("python_test_suite",[sys.executable,"-m","pytest","--basetemp",str(ROOT/".data/pytest_task_temp")]),
    ]
    ledger = []
    for name,command in commands:
        print(f"running {name}",flush=True)
        started = datetime.now(timezone.utc).isoformat();timer = time.perf_counter()
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",env=environment)
        elapsed = time.perf_counter()-timer
        log = logs/f"{name}.txt"
        log.write_text(result.stdout+result.stderr,encoding="utf-8",newline="\n")
        ledger.append({"name":name,"command":command,"exit_code":result.returncode,"started_utc":started,
                       "elapsed_seconds":elapsed,"log":str(log.relative_to(ROOT).as_posix())})
        print(f"{name}: exit={result.returncode} elapsed={elapsed:.2f}s",flush=True)
        if result.returncode:
            print(result.stdout+result.stderr);break
    report = {"schema":"member-a-task-execution-ledger-v1","status":"PASS" if len(ledger)==len(commands) and all(r["exit_code"]==0 for r in ledger) else "FAIL",
              "python":platform.python_version(),"executions":ledger,"board_capture_tested":False,
              "live_io_tested":False,"browser_visual_verified":False}
    (ROOT/"results/multiframe/task_execution.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
    sys.exit(0 if report["status"]=="PASS" else 1)
