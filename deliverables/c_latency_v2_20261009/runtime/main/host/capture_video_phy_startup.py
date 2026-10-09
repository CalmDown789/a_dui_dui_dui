"""Capture UART BEFORE temporary JTAG; require two successful cached PHY0 records."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess,time
from video_image_identity import verify_image_manifest
from startup_status_identity import complete_packets,verify_startup_permission

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--image-manifest',required=True,type=Path);p.add_argument('--port',default='COM3')
 p.add_argument('--vivado-bat',required=True,type=Path);p.add_argument('--program-tcl',required=True,type=Path)
 p.add_argument('--out-dir',required=True,type=Path);p.add_argument('--seconds',type=float,default=15)
 a=p.parse_args()
 if not 5<=a.seconds<=600:p.error('seconds must be 5..600')
 identity=verify_image_manifest(a.image_manifest)
 if not identity['manifest'].get('startup_configuration'):p.error('Managed PHY0 image required')
 if not a.vivado_bat.is_file() or not a.program_tcl.is_file():p.error('Vivado/program TCL missing')
 if sha(a.program_tcl.read_bytes())!=identity['manifest']['startup_configuration'].get('program_tcl_sha256'):
  p.error('JTAG programmer does not match issued image contract')
 # Pyserial was already used successfully by C's accepted PHY capture.
 import serial
 from serial.tools import list_ports
 a.out_dir.mkdir(parents=True,exist_ok=False)
 raw=bytearray();events=[];error=None;process=None;exit_code=None;offset=None;ports=[]
 def event(name,**fields):
  item=dict(utc=datetime.now(timezone.utc).isoformat(),monotonic_seconds=time.monotonic(),event=name,**fields)
  events.append(item)
  with (a.out_dir/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(item)+'\n')
 bit=next(x['file'] for x in identity['files'] if x['kind']=='BIT')
 try:
  ports=[dict(device=x.device,description=x.description,hwid=x.hwid,serial_number=x.serial_number,location=x.location) for x in list_ports.comports()]
  with serial.Serial(a.port,115200,timeout=.02) as port,(a.out_dir/'uart_raw.bin').open('xb') as f,(a.out_dir/'program_console.log').open('xb') as log:
   event('UART_OPENED_BEFORE_JTAG',port=a.port,baud=115200)
   print('UART opened BEFORE JTAG. Keep S0 released.',flush=True)
   cmd=[str(a.vivado_bat.resolve()),'-mode','batch','-source',str(a.program_tcl.resolve()),'-log','program.log','-journal','program.jou','-tclargs',bit]
   event('JTAG_PROCESS_START',argv=cmd)
   process=subprocess.Popen(cmd,cwd=a.out_dir,stdout=log,stderr=subprocess.STDOUT)
   program_deadline=time.monotonic()+480;deadline=None
   while True:
    data=port.read(4096)
    if data:raw.extend(data);f.write(data);f.flush()
    exit_code=process.poll()
    if exit_code is not None and deadline is None:
     offset=len(raw);event('JTAG_PROCESS_EXIT',exit_code=exit_code,raw_offset=offset)
     if exit_code:raise RuntimeError('JTAG failed; preserve logs')
     deadline=time.monotonic()+a.seconds
    if deadline is not None:
     packets,decoded,locations=complete_packets(bytes(raw[offset:]))
     if decoded and not all(x['actual_success_rx1_tx0'] for x in decoded):raise RuntimeError('PHY startup failed closed')
     if len(packets)>=2:event('TWO_COMPLETE_IDENTICAL_PHY0_RECORDS',count=len(packets));break
     if time.monotonic()>=deadline:raise TimeoutError('Two successful post-JTAG cached status records missing')
    elif time.monotonic()>=program_deadline:raise TimeoutError('JTAG still running; do not launch a second programmer')
 except Exception as exc:error=f'{type(exc).__name__}: {exc}'
 if not (a.out_dir/'uart_raw.bin').exists():(a.out_dir/'uart_raw.bin').write_bytes(raw)
 if not (a.out_dir/'program_console.log').exists():(a.out_dir/'program_console.log').write_bytes(b'')
 def item(name):
  data=(a.out_dir/name).read_bytes();return dict(file=name,bytes=len(data),sha256=sha(data))
 result=dict(scope='ACX750_VIDEO_PHY_STARTUP_CAPTURE_V1',error=error,port=a.port,baud=115200,ports=ports,
  BIT_sha256=identity['manifest']['BIT']['sha256'],image_manifest_sha256=identity['manifest_sha256'],
  programmer_sha256=sha(a.program_tcl.read_bytes()),JTAG_exit_code=exit_code,post_JTAG_raw_offset=offset,
  raw=item('uart_raw.bin'),program_console=item('program_console.log'),events=events)
 report=a.out_dir/'REPORT.json';report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 if error is None:
  try:
   proof=verify_startup_permission(identity,report)
   (a.out_dir/'PARSED_STARTUP_PERMISSION.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
  except Exception as exc:
   error=f'{type(exc).__name__}: {exc}';result['error']=error;report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(status='PASS_STARTUP_PERMISSION_ONLY' if error is None else 'FAIL_STARTUP_CAPTURE',error=error,out_dir=str(a.out_dir))))
 return 0 if error is None else 1
if __name__=='__main__':raise SystemExit(main())
