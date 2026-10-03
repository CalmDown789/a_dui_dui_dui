"""Unconfirmed SRTP input prototype; bare output has no wire ID, CRC or ACK."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import json
import math
import shutil
import struct
import sys
import time
import zlib

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
from capture_raw_uart import capture
from compare_board_sequence import digest,load_manifest,safe_path
from received_frames import compare_received

INPUT_BYTES=518400


def crc32(data): return zlib.crc32(data)&0xffffffff


def encode_frame(frame_id,payload):
    if type(frame_id) is not int or not 0<=frame_id<=0xffffffff:
        raise ValueError("Frame ID must be uint32")
    if len(payload)!=INPUT_BYTES: raise ValueError("Prototype input must be exactly 960x540 Y bytes")
    fields=struct.pack("<III",frame_id,len(payload),crc32(payload))
    return b"SRTP"+fields+struct.pack("<I",crc32(fields))+payload


def decode_input(packet):
    if len(packet)<20 or packet[:4]!=b"SRTP": raise ValueError("Invalid SRTP header")
    frame_id,length,payload_crc,header_crc=struct.unpack("<IIII",packet[4:20])
    if crc32(packet[4:16])!=header_crc: raise ValueError("Header CRC mismatch")
    if length!=INPUT_BYTES or len(packet)!=20+length: raise ValueError("Input length mismatch")
    if crc32(packet[20:])!=payload_crc: raise ValueError("Payload CRC mismatch")
    return frame_id,packet[20:]


def send_packet(port,packet,directory,*,timeout,clock=time.monotonic):
    start=clock();offset=0;calls=0
    with (directory/"tx_submitted.bin").open("xb") as submitted,(directory/"tx_accepted.bin").open("xb") as accepted:
        while offset<len(packet):
            if clock()-start>=timeout: raise TimeoutError("Input write deadline exceeded; do not retry without external reset")
            chunk=packet[offset:offset+4096];submitted.write(chunk);submitted.flush();calls+=1
            # On a write exception the device may have seen bytes even if the
            # host cannot count them. Never retry the entire packet blindly.
            count=port.write(chunk)
            if type(count) is not int or not 0<=count<=len(chunk): raise OSError("Invalid write result; transmission outcome unknown")
            accepted.write(chunk[:count]);accepted.flush();offset+=count
    return {"accepted_bytes":offset,"write_calls":calls,"elapsed_seconds":clock()-start,
            "ack_received":False,"input_accepted_by_fpga_verified":False}


def run_sequence(port,manifest_path,output_dir,*,send_timeout=30,receive_timeout=300,idle_timeout=30,
                 tail_watch=1,clock=time.monotonic,utc=lambda:datetime.now(timezone.utc).isoformat(),
                 evidence_source="operator_supplied_capture",transport=None):
    if output_dir.exists(): raise ValueError("Refusing to overwrite an existing prototype session")
    for timeout in (send_timeout,receive_timeout,idle_timeout,tail_watch):
        if not math.isfinite(timeout) or timeout<=0: raise ValueError("Timeouts must be positive and finite")
    if evidence_source not in ("software_fixture","operator_supplied_capture"):
        raise ValueError("Capture provenance must be explicit before transmitting")
    expected=load_manifest(manifest_path)
    if expected["input"]["bytes_per_frame"]!=INPUT_BYTES or expected["output"]["bytes_per_frame"]!=2073600:
        raise ValueError("Prototype uses fixed 540p to 1080p lengths")
    if [f["frame_id"] for f in expected["frames"]]!=list(range(expected["frame_count"])):
        raise ValueError("After external reset, prototype frame IDs must start at zero and be contiguous")
    output_dir.mkdir(parents=True,exist_ok=False)
    reference=output_dir/"reference";reference.mkdir()
    snapshot=json.loads(json.dumps(expected))
    for frame in snapshot["frames"]:
        for key in ("input","golden"):
            frame[key].pop("preview",None)
            relative=frame[key]["path"];target=safe_path(reference,relative);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(safe_path(manifest_path.parent,relative),target)
    (reference/"manifest.json").write_text(json.dumps(snapshot,indent=2)+"\n",encoding="utf-8",newline="\n")
    records=[];transmissions=[];reason=None;started=utc();timer=clock();tail_bytes=0
    with (output_dir/"wire_rx.bin").open("xb") as aggregate:
        try:
            stale=port.read(4096)
            if stale:
                aggregate.write(stale);(output_dir/"preexisting_rx.bin").write_bytes(stale)
                raise OSError("Preexisting output: no known frame boundary; external reset required")
            for order,frame in enumerate(snapshot["frames"]):
                directory=output_dir/f"frame_{order:04d}";directory.mkdir()
                payload=safe_path(reference,frame["input"]["path"]).read_bytes()
                packet=encode_frame(frame["frame_id"],payload)
                (directory/"input_packet.bin").write_bytes(packet)
                transmission={"frame_id":frame["frame_id"],"started_utc":utc(),"packet_sha256":digest(packet)["sha256"]}
                transmissions.append(transmission)
                transmission.update(send_packet(port,packet,directory,timeout=send_timeout,clock=clock))
                transmission["ended_utc"]=utc()
                selected={**snapshot,"frame_count":1,"frames":[dict(frame,order=0)]}
                selected_path=reference/f"frame_{order:04d}_manifest.json"
                selected_path.write_text(json.dumps(selected,indent=2)+"\n",encoding="utf-8",newline="\n")
                received=capture(port.read,selected_path,directory/"rx",total_timeout=receive_timeout,
                                 idle_timeout=idle_timeout,tail_watch=tail_watch,clock=clock,utc=utc,
                                 evidence_source=evidence_source,transport={"kind":"unconfirmed_SRTP_input_bare_output"})
                aggregate.write((directory/"rx/wire_rx.bin").read_bytes());aggregate.flush()
                tail_bytes+=received["unexpected_tail_bytes"]
                for arrival in received["frames"]:
                    records.append({**arrival,"order":order,"path":f"{directory.name}/rx/{arrival['path']}",
                                    "input_frame_id_sent":frame["frame_id"],"output_frame_id_from_wire":None})
                transmission["receive_status"]=received["capture_status"]
                if received["capture_status"]!="COMPLETE":
                    raise OSError("Receive failed: "+str(received["failure_reason"]))
                # Stop-and-wait: the NEXT input is never sent until this entire
                # output and its bounded tail check have completed successfully.
        except KeyboardInterrupt:
            reason="cancelled_external_reset_required"
        except (OSError,ValueError) as error:
            reason=str(error)+"; session stopped, external reset required; no retry performed"
    received_manifest={"schema":"member-a-received-frames-v1","sequence_id":snapshot["sequence_id"],
        "frame_count":len(records),"frames":records,"evidence_source":evidence_source,
        "capture_status":"COMPLETE" if reason is None else "FAIL","failure_reason":reason,
        "unexpected_tail_bytes":tail_bytes,"raw_stream":{"path":"wire_rx.bin",**digest((output_dir/"wire_rx.bin").read_bytes())},
        "protocol_status":"PROTOTYPE_UNCONFIRMED","transport":transport or {},"transmissions":transmissions,
        "started_utc":started,"ended_utc":utc(),"session_elapsed_seconds":clock()-timer,
        "timestamp_semantics":"PC read-return timestamps, not UART pin timestamps",
        "wire_output_crc_supported":False,"wire_output_id_supported":False,"automatic_retry_supported":False}
    received_path=output_dir/"received_manifest.json"
    received_path.write_text(json.dumps(received_manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    report=compare_received(reference/"manifest.json",received_path)
    (output_dir/"comparison.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
    return received_manifest,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--port",required=True)
    parser.add_argument("--baud",type=int,default=921600)
    parser.add_argument("--experimental-prototype",action="store_true")
    parser.add_argument("--external-reset-confirmed",action="store_true")
    parser.add_argument("--control-lines-safe",action="store_true")
    parser.add_argument("--send-timeout",type=float,default=30)
    parser.add_argument("--receive-timeout",type=float,default=300)
    args=parser.parse_args()
    if not all((args.experimental_prototype,args.external_reset_confirmed,args.control_lines_safe)):
        parser.error("Explicitly acknowledge unconfirmed prototype, external reset and RTS/DTR safety")
    if args.output_dir.exists(): parser.error("Session directory already exists")
    if not args.output_dir.resolve().is_relative_to(Path("D:/Codex File/dialogue file").resolve()): parser.error("All session files must be under D:/Codex File/dialogue file")
    if args.baud<=0 or "://" in args.port: parser.error("Native serial device and positive baud required")
    if any(not math.isfinite(v) or v<=0 for v in (args.send_timeout,args.receive_timeout)): parser.error("Invalid timeout")
    expected=load_manifest(args.manifest)
    if (expected["input"]["bytes_per_frame"]!=INPUT_BYTES or expected["output"]["bytes_per_frame"]!=2073600
        or [f["frame_id"] for f in expected["frames"]]!=list(range(expected["frame_count"]))):
        parser.error("Prototype requires 540p/1080p lengths and contiguous IDs from zero")
    try:
        import serial
        port=serial.Serial(port=None,baudrate=args.baud,bytesize=8,parity="N",stopbits=1,timeout=.1,write_timeout=.1,
                           xonxoff=False,rtscts=False,dsrdtr=False)
        port.rts=False;port.dtr=False;port.port=args.port
        try:
            port.open()
            result,comparison=run_sequence(port,args.manifest,args.output_dir,send_timeout=args.send_timeout,
                receive_timeout=args.receive_timeout,transport={"kind":"prototype_uart","port":args.port,"baud":args.baud,
                "protocol_status":"PROTOTYPE_UNCONFIRMED","spec_source":"User supplied prototype description; C source commit not supplied"})
        finally: port.close()
        print(json.dumps({"protocol_status":"PROTOTYPE_UNCONFIRMED","capture_status":result["capture_status"],"comparison":comparison["status"],"frames":result["frame_count"]}))
        return 0 if comparison["status"]=="PASS" else 1
    except (ImportError,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({"status":"FAIL","error":str(error)}));return 1


if __name__=="__main__": sys.exit(main())
