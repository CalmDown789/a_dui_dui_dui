"""Receive the existing headerless UART TX path. No FPGA upload/command protocol."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import math
import sys
import time
from compare_board_sequence import digest, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def capture(read, manifest_path, output_dir, *, total_timeout=300.0, idle_timeout=30.0,
            tail_watch=1.0, max_tail_bytes=65536, clock=time.monotonic,
            utc=lambda: datetime.now(timezone.utc).isoformat(), evidence_source="operator_supplied_capture",
            transport=None):
    manifest = load_manifest(manifest_path)
    if output_dir.exists():
        raise ValueError("Refusing to overwrite an existing capture directory")
    for value in (total_timeout, idle_timeout, tail_watch):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Timeouts must be finite and positive")
    if type(max_tail_bytes) is not int or max_tail_bytes <= 0:
        raise ValueError("Invalid tail byte limit")
    if evidence_source not in ("software_fixture", "operator_supplied_capture"):
        raise ValueError("Capture provenance must be explicit")
    output_dir.mkdir(parents=True, exist_ok=False)
    start = clock(); started_utc = utc(); last_data = start
    frame_bytes = manifest["output"]["bytes_per_frame"]
    records = []; pending = bytearray(); first_utc = None; last_utc = None
    first_offset = None; last_offset = None; total_bytes = 0; read_calls = 0
    reason = None; extra = bytearray(); tail_started = None

    def save_frame(status):
        order = len(records); expected = manifest["frames"][order]
        name = f"arrival_{order:04d}_frame_{expected['frame_id']:04d}.bin"
        raw = bytes(pending); (output_dir/name).write_bytes(raw)
        records.append({"frame_id": expected["frame_id"], "order": order, "path": name, **digest(raw),
                        "receive_status":status,"crc_result":"NOT_CHECKED","protocol_frame_id_observed":False,
                        "first_byte_utc":first_utc,"last_byte_utc":last_utc,
                        "first_payload_read_offset_seconds":first_offset,"last_payload_read_offset_seconds":last_offset})

    with (output_dir/"wire_rx.bin").open("xb") as wire:
        try:
            while True:
                now = clock()
                if len(records) == manifest["frame_count"]:
                    if tail_started is None: tail_started = now
                    if now-tail_started >= tail_watch: break
                    capacity = max_tail_bytes-len(extra)
                    if capacity <= 0:
                        reason = "extra_data_limit"; break
                    requested = min(4096, capacity)
                else:
                    if now-start >= total_timeout:
                        reason = "total_timeout"; break
                    if now-last_data >= idle_timeout:
                        reason = "idle_timeout"; break
                    requested = min(4096, frame_bytes-len(pending))
                chunk = read(requested); read_calls += 1; now = clock()
                if not isinstance(chunk, bytes):
                    reason = "invalid_reader_type"; break
                if not chunk: continue
                stamp = utc()
                wire.write(chunk); wire.flush(); total_bytes += len(chunk); last_data = now
                if len(records) == manifest["frame_count"]:
                    extra.extend(chunk); reason = "unexpected_trailing_data"
                    continue
                if first_utc is None:
                    first_utc = stamp; first_offset = now-start
                last_utc = stamp; last_offset = now-start
                pending.extend(chunk)
                if len(pending) > frame_bytes:
                    reason = "reader_overrun"; break
                if len(pending) == frame_bytes:
                    save_frame("complete"); pending.clear()
                    first_utc = last_utc = first_offset = last_offset = None
        except KeyboardInterrupt:
            reason = "cancelled"
        except OSError as error:
            reason = "read_error: "+str(error)
        finally:
            if pending:
                save_frame("timeout" if reason in ("idle_timeout","total_timeout") else "error")
            if extra: (output_dir/"unexpected_tail.bin").write_bytes(extra)
    ended = utc(); elapsed = clock()-start
    received = {"schema":"member-a-received-frames-v1","sequence_id":manifest["sequence_id"],
                "frame_count":len(records),"frames":records,"evidence_source":evidence_source,
                "timestamp_semantics":"PC timestamps immediately after first/last payload-bearing read() returns, not UART pin timestamps",
                "transport":transport or {},"id_assignment":"Host expected-order assignment; no on-wire frame ID exists",
                "raw_stream":{"path":"wire_rx.bin",**digest((output_dir/"wire_rx.bin").read_bytes())},
                "capture_status":"COMPLETE" if reason is None and len(records)==manifest["frame_count"] else "FAIL",
                "failure_reason":reason,"unexpected_tail_bytes":len(extra),"started_utc":started_utc,"ended_utc":ended,
                "session_elapsed_seconds":elapsed,"read_calls":read_calls,"bytes_received":total_bytes,
                "input_upload_supported":False,"wire_crc_supported":False,"line_frame_boundary_verified":False}
    (output_dir/"received_manifest.json").write_text(json.dumps(received,indent=2)+"\n",encoding="utf-8",newline="\n")
    return received


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-ports",action="store_true",help="Read port inventory only; no device open")
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--port",help="Explicit local device, e.g. COM7. Never copy another machine's COM3")
    parser.add_argument("--baud",type=int,default=921600)
    parser.add_argument("--boundary-confirmed",action="store_true",help="Operator arranged capture BEFORE a known frame starts")
    parser.add_argument("--control-lines-safe",action="store_true",help="Operator checked RTS/DTR cannot reset or miscontrol this board")
    parser.add_argument("--total-timeout",type=float,default=300)
    parser.add_argument("--idle-timeout",type=float,default=30)
    parser.add_argument("--tail-watch",type=float,default=1)
    args = parser.parse_args()
    if not args.list_ports:
        if not args.manifest or not args.output_dir or not args.port:
            parser.error("--manifest, --output-dir and --port are required")
        if not args.boundary_confirmed or not args.control_lines_safe:
            parser.error("Confirm known frame start and RTS/DTR safety; unframed streams cannot self-synchronize")
        if not args.output_dir.resolve().is_relative_to(Path("D:/Codex File/dialogue file").resolve()):
            parser.error("Capture data and documents must remain under D:/Codex File/dialogue file")
        if args.output_dir.exists(): parser.error("Output directory already exists")
        if args.baud <= 0: parser.error("Baud must be positive")
        load_manifest(args.manifest)
        if any(not math.isfinite(value) or value<=0 for value in (args.total_timeout,args.idle_timeout,args.tail_watch)):
            parser.error("Timeouts must be finite and positive")
        if "://" in args.port: parser.error("Only a native serial device is accepted; no network URLs")
    try:
        import serial
        if args.list_ports:
            from serial.tools import list_ports
            print(json.dumps({"ports":[{"port":p.device,"description":p.description} for p in list_ports.comports()],"device_opened":False},ensure_ascii=False));return 0
        port = serial.Serial(port=None,baudrate=args.baud,bytesize=8,parity="N",stopbits=1,timeout=.1,
                             xonxoff=False,rtscts=False,dsrdtr=False)
        port.dtr = False; port.rts = False; port.port = args.port
        try:
            port.open()
            print("Receiver open. Arrange the agreed external frame start; no bytes are sent to the FPGA.",flush=True)
            result = capture(port.read,args.manifest,args.output_dir,total_timeout=args.total_timeout,
                             idle_timeout=args.idle_timeout,tail_watch=args.tail_watch,
                             transport={"kind":"legacy_uart_raw_receive_only","port":args.port,"baud":args.baud,"format":"8N1",
                                        "rts":False,"dtr":False,"xonxoff":False,"rtscts":False,
                                        "source_c_commit":"910e60e85fca5c869c311289cc8586b8cfb8fdb3",
                                        "start_boundary":"Operator assertion; not verified by on-wire framing"})
        finally:
            port.close()
        print(json.dumps({"capture_status":result["capture_status"],"failure_reason":result["failure_reason"],
                          "frames":result["frame_count"],"bytes_received":result["bytes_received"]},indent=2))
        return 130 if result["failure_reason"]=="cancelled" else 0 if result["capture_status"]=="COMPLETE" else 1
    except (ImportError,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({"status":"FAIL","error":str(error)}));return 1


if __name__ == "__main__":
    sys.exit(main())
