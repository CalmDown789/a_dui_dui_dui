from pathlib import Path
from datetime import datetime,timedelta,timezone
import json
import sys
import subprocess
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from capture_raw_uart import capture
from received_frames import compare_received
from test_multiframe import bundle


class Reader:
    def __init__(self,payload,chunk=3,fail_at=None):
        self.payload=payload;self.chunk=chunk;self.offset=0;self.now=0;self.calls=0;self.fail_at=fail_at
    def clock(self): return self.now
    def utc(self): return (datetime(2026,10,3,tzinfo=timezone.utc)+timedelta(seconds=self.now)).isoformat()
    def read(self,size):
        self.now+=.05;self.calls+=1
        if self.calls==self.fail_at: raise OSError("simulated disconnect")
        raw=self.payload[self.offset:self.offset+min(size,self.chunk)];self.offset+=len(raw);return raw


@pytest.fixture
def source(bundle):
    path,capture_dir=bundle
    data=json.loads(path.read_text());data["sequence_id"]="uart_fixture";path.write_text(json.dumps(data))
    raw=b"".join((capture_dir/f["golden"]["path"]).read_bytes() for f in data["frames"])
    return path,raw,capture_dir.parent/"new_capture"


def run(reader,path,out,**options):
    return capture(reader.read,path,out,clock=reader.clock,utc=reader.utc,evidence_source="software_fixture",
                   total_timeout=options.get("total_timeout",5),idle_timeout=options.get("idle_timeout",1),tail_watch=.15)


@pytest.mark.parametrize("chunk",[1,3,16,4096])
def test_short_reads_and_exact_frame_boundaries(source,chunk):
    path,raw,out=source;reader=Reader(raw,chunk)
    result=run(reader,path,out)
    assert result["capture_status"]=="COMPLETE" and result["bytes_received"]==48
    assert (out/"wire_rx.bin").read_bytes()==raw
    assert result["read_calls"]>=3
    assert all(not r["protocol_frame_id_observed"] and r["crc_result"]=="NOT_CHECKED" for r in result["frames"])
    assert not result["input_upload_supported"] and not result["line_frame_boundary_verified"]
    assert compare_received(path,out/"received_manifest.json")["status"]=="PASS"


@pytest.mark.parametrize("size",[0,1,15,16,17,47])
def test_partial_receive_and_idle_timeout_preserve_every_byte(source,size):
    path,raw,out=source;reader=Reader(raw[:size])
    result=run(reader,path,out)
    assert result["capture_status"]=="FAIL" and result["failure_reason"]=="idle_timeout"
    assert (out/"wire_rx.bin").read_bytes()==raw[:size]
    assert compare_received(path,out/"received_manifest.json")["status"]=="FAIL"
    assert sum(r["bytes"] for r in result["frames"])==size


def test_total_timeout_despite_continued_data(source):
    path,raw,out=source;reader=Reader(raw,1)
    result=run(reader,path,out,total_timeout=.21)
    assert result["failure_reason"]=="total_timeout"
    assert result["bytes_received"]<48


def test_long_but_bounded_idle_gap_recovers_without_retry(source):
    path,raw,out=source;reader=Reader(raw,16)
    original=reader.read;pauses=0
    def paused(size):
        nonlocal pauses
        if reader.calls==1 and pauses<12:
            pauses+=1;reader.now+=.05;return b""
        return original(size)
    reader.read=paused
    result=run(reader,path,out)
    assert result["capture_status"]=="COMPLETE" and result["bytes_received"]==48
    assert (out/"wire_rx.bin").read_bytes()==raw
    assert compare_received(path,out/"received_manifest.json")["status"]=="PASS"


def test_extra_byte_cannot_pass_by_truncation(source):
    path,raw,out=source;reader=Reader(raw+b"!")
    result=run(reader,path,out)
    assert result["capture_status"]=="FAIL" and result["unexpected_tail_bytes"]==1
    assert (out/"wire_rx.bin").read_bytes()==raw+b"!"
    assert (out/"unexpected_tail.bin").read_bytes()==b"!"
    assert compare_received(path,out/"received_manifest.json")["status"]=="FAIL"


def test_disconnect_and_cancel_preserve_partial_frame(source):
    path,raw,out=source;reader=Reader(raw,3,fail_at=3)
    result=run(reader,path,out)
    assert result["failure_reason"].startswith("read_error") and result["bytes_received"]==6
    assert (out/"wire_rx.bin").read_bytes()==raw[:6]
    assert result["frames"][0]["receive_status"]=="error"


def test_cancel_preserves_stream(source):
    path,raw,out=source;reader=Reader(raw)
    original=reader.read
    def cancelled(size):
        if reader.calls==2: raise KeyboardInterrupt
        return original(size)
    reader.read=cancelled
    result=run(reader,path,out)
    assert result["failure_reason"]=="cancelled" and result["bytes_received"]==6
    assert (out/"wire_rx.bin").read_bytes()==raw[:6]


def test_reader_overrun_is_not_trimmed(source):
    path,raw,out=source;reader=Reader(raw)
    def bad(size): reader.now+=.1; return raw[:size+1]
    reader.read=bad
    result=run(reader,path,out)
    assert result["failure_reason"]=="reader_overrun"
    assert (out/"wire_rx.bin").read_bytes()==raw[:17]
    assert result["frames"][0]["bytes"]==17


def test_existing_capture_is_not_overwritten(source):
    path,raw,out=source;out.mkdir();(out/"keep.txt").write_text("keep")
    with pytest.raises(ValueError,match="overwrite"): run(Reader(raw),path,out)
    assert (out/"keep.txt").read_text()=="keep"


@pytest.mark.parametrize("option",[float("nan"),0,-1,float("inf")])
def test_invalid_timeout_rejected_before_capture(source,option):
    path,raw,out=source
    with pytest.raises(ValueError): run(Reader(raw),path,out,total_timeout=option)
    assert not out.exists()


def test_raw_stream_corruption_detected(source):
    path,raw,out=source;run(Reader(raw),path,out)
    (out/"wire_rx.bin").write_bytes(raw+b"\0")
    assert "raw_stream_integrity_mismatch" in compare_received(path,out/"received_manifest.json")["sequence_errors"]


def test_receiver_cli_requires_boundary_and_control_line_checks(source):
    path,raw,out=source
    result=subprocess.run([sys.executable,str(ROOT/"scripts/capture_raw_uart.py"),"--manifest",str(path),
                           "--port","COM_NOT_OPENED","--output-dir",str(out)],capture_output=True)
    assert result.returncode==2 and not out.exists()


def test_serial_adapter_uses_bounded_reads_and_never_sends(monkeypatch,source):
    import types
    import capture_raw_uart as module
    path,raw,out=source
    reader=Reader(raw,16);events=[]
    class Serial:
        def __init__(self,**kwargs):
            assert kwargs["port"] is None and kwargs["timeout"]==.1
            assert kwargs["bytesize"]==8 and kwargs["parity"]=="N" and kwargs["stopbits"]==1
            assert not kwargs["rtscts"] and not kwargs["xonxoff"] and not kwargs["dsrdtr"]
            events.append("configured")
        def open(self):
            assert self.dtr is False and self.rts is False and self.port=="COM_TEST"
            events.append("opened")
        def read(self,n): return reader.read(n)
        def close(self): events.append("closed")
        def write(self,*args): raise AssertionError("No bytes may be sent to FPGA")
        def reset_input_buffer(self): raise AssertionError("Capture bytes must not be discarded")
    monkeypatch.setitem(sys.modules,"serial",types.SimpleNamespace(Serial=Serial))
    original=module.capture
    def fake_timing(read,path,out,**kwargs):
        kwargs.update(clock=reader.clock,utc=reader.utc,evidence_source="software_fixture",tail_watch=.15)
        return original(read,path,out,**kwargs)
    monkeypatch.setattr(module,"capture",fake_timing)
    monkeypatch.setattr(sys,"argv",["capture","--manifest",str(path),"--port","COM_TEST",
        "--output-dir",str(out),"--boundary-confirmed","--control-lines-safe"])
    assert module.main()==0
    assert events==["configured","opened","closed"]
    assert (out/"wire_rx.bin").read_bytes()==raw


def test_serial_adapter_safely_closes_after_open_error(monkeypatch,source):
    import types
    import capture_raw_uart as module
    path,raw,out=source;events=[]
    class Serial:
        def __init__(self,**kwargs): pass
        def open(self): raise OSError("mock open failure")
        def close(self): events.append("closed")
    monkeypatch.setitem(sys.modules,"serial",types.SimpleNamespace(Serial=Serial))
    monkeypatch.setattr(sys,"argv",["capture","--manifest",str(path),"--port","COM_TEST",
        "--output-dir",str(out),"--boundary-confirmed","--control-lines-safe"])
    assert module.main()==1 and events==["closed"] and not out.exists()
