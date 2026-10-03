"""Software-only SRTP endpoint fixtures; not C RTL, UART hardware or board proof."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from tempfile import mkdtemp
import json
import subprocess
import sys
import time
from stop_wait_client import ROOT,crc32,decode_input,digest,encode_frame,load_manifest,run_sequence


class SoftwareEndpoint:
    def __init__(self,manifest,path,*,wrong=False):
        self.manifest=manifest;self.path=path;self.wrong=wrong
        self.input=bytearray();self.output=bytearray();self.ids=[];self.t=0
    def clock(self): return self.t
    def utc(self): return (datetime(2026,10,3,tzinfo=timezone.utc)+timedelta(seconds=self.t)).isoformat()
    def write(self,data):
        self.t+=.001
        if self.output: raise AssertionError("New input sent before all output drained")
        count=min(len(data),1021);self.input.extend(data[:count])
        if len(self.input)==518420:
            frame_id,payload=decode_input(bytes(self.input))
            frame=self.manifest["frames"][len(self.ids)]
            assert frame_id==frame["frame_id"]
            assert payload==(self.path/frame["input"]["path"]).read_bytes()
            self.ids.append(frame_id);self.input.clear()
            raw=(self.path/frame["golden"]["path"]).read_bytes()
            if self.wrong: raw=bytes([raw[0]^1])+raw[1:]
            self.output.extend(raw)
        return count
    def read(self,n):
        self.t+=.001
        raw=bytes(self.output[:min(n,2053)]);del self.output[:len(raw)];return raw


def main():
    root=ROOT/".data/uart_prototype_selftest";root.mkdir(parents=True,exist_ok=True)
    run=Path(mkdtemp(prefix="run_",dir=root));cases=[];vectors=[]
    for name,relative,wrong in (
        ("authority_pair_exact","artifacts/authority_pair/manifest.json",False),
        ("video_eight_exact","artifacts/multiframe/manifest.json",False),
        ("video_eight_wrong_byte","artifacts/multiframe/manifest.json",True),
    ):
        path=ROOT/relative;manifest=load_manifest(path);endpoint=SoftwareEndpoint(manifest,path.parent,wrong=wrong)
        started=time.perf_counter();directory=run/name
        record,comparison=run_sequence(endpoint,path,directory,clock=endpoint.clock,utc=endpoint.utc,
            tail_watch=.01,idle_timeout=.1,evidence_source="software_fixture",
            transport={"kind":"software_endpoint_fixture","physical_port_opened":False})
        assert comparison["status"]==("FAIL" if wrong else "PASS")
        assert endpoint.ids==list(range(manifest["frame_count"]))
        for order,frame in enumerate(manifest["frames"]):
            target=directory/f"frame_{order:04d}"
            packet=(target/"input_packet.bin").read_bytes()
            assert (target/"tx_accepted.bin").read_bytes()==packet
            assert decode_input(packet)[0]==frame["frame_id"]
            if name=="authority_pair_exact":
                vectors.append({"sequence_id":manifest["sequence_id"],"frame_id":frame["frame_id"],
                    "packet_bytes":len(packet),"header_hex":packet[:20].hex(),"packet_sha256":digest(packet)["sha256"],
                    "payload_sha256":frame["input"]["sha256"],"header_crc32":f"{crc32(packet[4:16]):08x}",
                    "payload_crc32":f"{crc32(packet[20:]):08x}"})
        command=[sys.executable,str(ROOT/"scripts/export_pc_player.py"),"--manifest",str(directory/"reference/manifest.json"),
                 "--received-manifest",str(directory/"received_manifest.json"),"--output",str(directory/"player.html")]
        result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8")
        assert result.returncode==(1 if wrong else 0),result.stdout+result.stderr
        assert (directory/"player.html").is_file()
        cases.append({"case":name,"frame_ids_sent":endpoint.ids,"capture_status":record["capture_status"],
            "comparison":comparison["status"],"player_command":command,"player_exit_code":result.returncode,
            "elapsed_host_seconds":time.perf_counter()-started,
            "received_manifest":str((directory/"received_manifest.json").relative_to(ROOT).as_posix()),
            "short_reads_and_writes_tested":True,"next_input_before_output_drained":False})
    report={"status":"PASS","protocol_status":"PROTOTYPE_UNCONFIRMED","cases":cases,
            "fixture_source":"Software endpoint validates input packets and copies frozen integer Golden as output; not C RTL",
            "physical_port_opened":False,"board_capture_tested":False,"C_compatibility_verified":False,
            "packet_examples":vectors,"CRC_check_123456789":"cbf43926"}
    (ROOT/"artifacts/uart_prototype_selftest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":"PASS","cases":len(cases),"physical_port_opened":False,"protocol_status":"PROTOTYPE_UNCONFIRMED"}))
    return 0


if __name__=="__main__": sys.exit(main())
