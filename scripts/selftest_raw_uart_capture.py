"""Full-size software UART read simulation; never opens a physical serial port."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json
import subprocess
import sys
from capture_raw_uart import capture
from compare_board_sequence import load_manifest
from received_frames import compare_received

ROOT = Path(__file__).resolve().parents[1]

class Fixture:
    def __init__(self,raw): self.raw=raw;self.offset=0;self.t=0;self.reads=0
    def read(self,n):
        self.t+=.001;self.reads+=1
        size=min(n,(17,4096,73,1024)[self.reads%4])
        block=self.raw[self.offset:self.offset+size];self.offset+=len(block);return block
    def clock(self): return self.t
    def utc(self): return (datetime(2026,10,3,tzinfo=timezone.utc)+timedelta(seconds=self.t)).isoformat()

if __name__ == "__main__":
    root=ROOT/".data/uart_capture_selftest"
    root.mkdir(parents=True,exist_ok=True)
    # A new uniquely named directory for each run preserves every prior capture.
    from tempfile import mkdtemp
    run=Path(mkdtemp(prefix="run_",dir=root))
    evidence=[]
    plans=[("single",ROOT/"artifacts/authority_pair/single_authority_manifest.json"),
           ("eight",ROOT/"artifacts/multiframe/manifest.json")]
    for name,path in plans:
        manifest=load_manifest(path)
        raw=b"".join((path.parent/f["golden"]["path"]).read_bytes() for f in manifest["frames"])
        for mutation in ("exact","short","extra","wrong_byte"):
            data=raw if mutation=="exact" else raw[:-1] if mutation=="short" else raw+b"!" if mutation=="extra" else bytes([raw[0]^1])+raw[1:]
            fixture=Fixture(data);directory=run/f"{name}_{mutation}"
            record=capture(fixture.read,path,directory,total_timeout=200,idle_timeout=.1,tail_watch=.01,
                           clock=fixture.clock,utc=fixture.utc,evidence_source="software_fixture",
                           transport={"kind":"software_reader_fixture","timestamp_source":"synthetic_schedule"})
            assert (directory/"wire_rx.bin").read_bytes()==data
            report=compare_received(path,directory/"received_manifest.json")
            assert report["status"]==("PASS" if mutation=="exact" else "FAIL")
            player=directory/"player.html"
            command=[sys.executable,str(ROOT/"scripts/export_pc_player.py"),"--manifest",str(path),
                     "--received-manifest",str(directory/"received_manifest.json"),"--output",str(player)]
            result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8")
            assert result.returncode==(0 if mutation=="exact" else 1),result.stdout+result.stderr
            assert player.is_file()
            evidence.append({"case":f"{name}_{mutation}","input_bytes":len(data),"saved_raw_identical":True,
                             "capture_status":record["capture_status"],"comparison":report["status"],
                             "player_command":command,"player_exit_code":result.returncode,
                             "received_manifest":str((directory/"received_manifest.json").relative_to(ROOT).as_posix())})
    output={"status":"PASS","cases":evidence,"physical_port_opened":False,"board_capture_tested":False,
            "input_upload_tested":False,"fixture_source":"Copied integer Golden with deliberately corrupted bytes and synthetic timestamps"}
    (ROOT/"artifacts/uart_capture_selftest.json").write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":"PASS","full_size_cases":len(evidence),"physical_port_opened":False}))
