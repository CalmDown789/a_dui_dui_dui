from pathlib import Path
from datetime import datetime,timedelta,timezone
import importlib.util
import json
import struct
import sys
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"experiments/member_a_uart_prototype_20261003/host/stop_wait_client.py"
spec=importlib.util.spec_from_file_location("uart_proto",FILE)
proto=importlib.util.module_from_spec(spec);spec.loader.exec_module(proto)


def test_ieee_crc_standard_check_and_wire_layout():
    assert proto.crc32(b"123456789")==0xcbf43926
    raw=bytes(range(256))*2025
    packet=proto.encode_frame(0x12345678,raw)
    assert packet[:8]==b"SRTP\x78\x56\x34\x12"
    assert struct.unpack("<I",packet[8:12])[0]==518400
    assert struct.unpack("<I",packet[12:16])[0]==proto.crc32(raw)
    assert struct.unpack("<I",packet[16:20])[0]==proto.crc32(packet[4:16])
    assert proto.decode_input(packet)==(0x12345678,raw)


@pytest.mark.parametrize("offset",[0,4,8,12,16,20,518419])
def test_corrupted_packet_detected(offset):
    packet=bytearray(proto.encode_frame(0,bytes(518400)));packet[offset]^=1
    with pytest.raises(ValueError): proto.decode_input(bytes(packet))


@pytest.mark.parametrize("value",[-1,2**32,True])
def test_invalid_id_rejected(value):
    with pytest.raises(ValueError): proto.encode_frame(value,bytes(518400))


def test_inexact_packet_length_rejected():
    packet=proto.encode_frame(0,bytes(518400))
    for raw in (packet[:-1],packet+b"\0",b"SRTP"):
        with pytest.raises(ValueError): proto.decode_input(raw)


class Device:
    """A software endpoint that validates input CRC then supplies frozen outputs."""
    def __init__(self,expected,root,*,write_chunk=113,short=False,extra=False,wrong=False,zero=False,throw=False):
        self.expected=expected;self.root=root;self.input=bytearray();self.output=bytearray()
        self.ids=[];self.t=0;self.chunk=write_chunk;self.short=short;self.extra=extra;self.wrong=wrong
        self.zero=zero;self.throw=throw;self.new_input_before_output_drained=False
    def clock(self): return self.t
    def utc(self): return (datetime(2026,10,3,tzinfo=timezone.utc)+timedelta(seconds=self.t)).isoformat()
    def write(self,data):
        self.t+=.001
        if self.output: self.new_input_before_output_drained=True;raise AssertionError("Stop-and-wait violation")
        if self.throw: raise OSError("simulated uncertain partial write")
        if self.zero: return 0
        count=min(len(data),self.chunk);self.input.extend(data[:count])
        if len(self.input)==518420:
            frame_id,payload=proto.decode_input(bytes(self.input))
            frame=self.expected["frames"][len(self.ids)]
            assert payload==(self.root/frame["input"]["path"]).read_bytes()
            assert frame_id==frame["frame_id"]
            self.ids.append(frame_id);self.input.clear()
            raw=(self.root/frame["golden"]["path"]).read_bytes()
            if self.short: raw=raw[:-1]
            if self.extra: raw+=b"!"
            if self.wrong: raw=bytes([raw[0]^1])+raw[1:]
            self.output.extend(raw)
        return count
    def read(self,n):
        self.t+=.001
        raw=bytes(self.output[:min(n,347)]);del self.output[:len(raw)];return raw


def test_full_size_pair_stop_wait_short_reads_and_writes(tmp_path):
    path=ROOT/"artifacts/authority_pair/manifest.json"
    expected=proto.load_manifest(path);device=Device(expected,path.parent)
    result,report=proto.run_sequence(device,path,tmp_path/"session",clock=device.clock,utc=device.utc,
                                    tail_watch=.01,idle_timeout=.1,evidence_source="software_fixture")
    assert report["status"]=="PASS" and device.ids==[0,1]
    assert not device.new_input_before_output_drained
    assert all(not f["protocol_frame_id_observed"] and f["crc_result"]=="NOT_CHECKED" for f in result["frames"])
    assert result["protocol_status"]=="PROTOTYPE_UNCONFIRMED"


@pytest.mark.parametrize("fault",["short","extra","wrong","zero","throw"])
def test_prototype_failure_never_retries_or_claims_crc_verified(tmp_path,fault):
    path=ROOT/"artifacts/authority_pair/manifest.json";expected=proto.load_manifest(path)
    device=Device(expected,path.parent,write_chunk=4096,**{fault:True})
    result,report=proto.run_sequence(device,path,tmp_path/"bad",clock=device.clock,utc=device.utc,
        send_timeout=.1 if fault in ("zero","throw") else 30,idle_timeout=.1,tail_watch=.01,evidence_source="software_fixture")
    assert report["status"]=="FAIL" and not result["automatic_retry_supported"]
    assert not result["wire_output_crc_supported"] and not result["wire_output_id_supported"]
    if fault!="wrong": assert len(device.ids)<=1 and result["capture_status"]=="FAIL"
    else: assert result["capture_status"]=="COMPLETE" and report["frames"][0]["byte_mismatch"]==1


def test_preexisting_output_aborts_before_input_write(tmp_path):
    path=ROOT/"artifacts/authority_pair/manifest.json";device=Device(proto.load_manifest(path),path.parent)
    device.output.extend(b"stale")
    result,report=proto.run_sequence(device,path,tmp_path/"stale",clock=device.clock,utc=device.utc,evidence_source="software_fixture")
    assert not device.ids and not device.input and report["status"]=="FAIL"
    assert (tmp_path/"stale/preexisting_rx.bin").read_bytes()==b"stale"


def test_noncontiguous_ids_rejected_before_session(tmp_path):
    path=ROOT/"artifacts/multiframe/two_frame_manifest.json"
    with pytest.raises(ValueError,match="contiguous"):
        proto.run_sequence(None,path,tmp_path/"bad")
    assert not (tmp_path/"bad").exists()


def test_invalid_provenance_rejected_before_transmission(tmp_path):
    with pytest.raises(ValueError,match="provenance"):
        proto.run_sequence(None,ROOT/"artifacts/authority_pair/manifest.json",tmp_path/"bad",evidence_source="board_verified")
    assert not (tmp_path/"bad").exists()


def test_cli_requires_explicit_experimental_flags_before_device_access(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,"argv",[str(FILE),"--manifest",str(ROOT/"artifacts/authority_pair/manifest.json"),
        "--output-dir",str(tmp_path/"capture"),"--port","COM_TEST_ONLY"])
    with pytest.raises(SystemExit) as error: proto.main()
    assert error.value.code==2
    assert not (tmp_path/"capture").exists()


@pytest.mark.parametrize("open_fails",[False,True])
def test_cli_serial_adapter_configures_lines_before_open_and_always_closes(tmp_path,monkeypatch,open_fails):
    events=[];options={}
    class Serial:
        def __init__(self,**kwargs): options.update(kwargs);events.append("construct")
        def __setattr__(self,key,value): events.append((key,value));object.__setattr__(self,key,value)
        def open(self):
            assert self.rts is False and self.dtr is False
            events.append("open")
            if open_fails: raise OSError("simulated open error")
        def close(self): events.append("close")
    def run(port,manifest,output,**kwargs):
        events.append("run")
        return {"capture_status":"COMPLETE","frame_count":2},{"status":"PASS"}
    monkeypatch.setitem(sys.modules,"serial",SimpleNamespace(Serial=Serial))
    monkeypatch.setattr(proto,"run_sequence",run)
    monkeypatch.setattr(sys,"argv",[str(FILE),"--manifest",str(ROOT/"artifacts/authority_pair/manifest.json"),
        "--output-dir",str(tmp_path/"capture"),"--port","COM_TEST_ONLY","--experimental-prototype",
        "--external-reset-confirmed","--control-lines-safe"])
    assert proto.main()==(1 if open_fails else 0)
    assert events[-1]=="close"
    assert options==dict(port=None,baudrate=921600,bytesize=8,parity="N",stopbits=1,timeout=.1,
                        write_timeout=.1,xonxoff=False,rtscts=False,dsrdtr=False)
    assert ("run" in events)==(not open_fails)
