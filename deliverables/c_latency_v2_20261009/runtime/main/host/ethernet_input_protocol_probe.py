"""New-image EVF1 smoke/input recovery probe. Never sends a complete frame."""
from datetime import datetime,timezone
from pathlib import Path
from dataclasses import replace
import argparse,hashlib,json,math,secrets,socket,time,zlib
from video_protocol import Packet,Type,Status,INPUT_BYTES,decode,InvalidPacket
from video_image_identity import verify_image_manifest
from startup_status_identity import verify_startup_permission

def sha(b):return hashlib.sha256(b).hexdigest()
class InputProbe:
    def __init__(self,peer,local,out,timeout=1.,attempts=3,label='UNACCEPTED_NEW_IMAGE_INPUT_PROTOCOL_RUN',image_identity=None):
        if not math.isfinite(timeout) or timeout<=0 or type(attempts) is not int or not 1<=attempts<=10:
            raise ValueError('finite positive timeout and attempts1..10 required')
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.peer=peer;self.local=local;self.timeout=timeout;self.attempts=attempts;self.label=label;self.image_identity=image_identity
        self.session=secrets.token_bytes(16);self.serial=0;self.received=0;self.retries=0;self.cases=[];self.closed=False
        self.network_sends=0;self.ignored=0;self.report=None
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        self.events=(self.out/'events.jsonl').open('x',encoding='utf-8')
        try:self.sock.bind(local)
        except OSError as exc:
            self.finish(False,f'LOCAL_BIND_FAILED_NO_NETWORK_TRAFFIC: {exc}');raise
    def event(self,kind,**fields):
        self.events.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'event':kind,**fields})+'\n');self.events.flush()
    def save(self,name,data):
        with (self.out/name).open('xb')as f:f.write(data)
        return {'file':name,'bytes':len(data),'sha256':sha(data)}
    def request(self,name,p,status,progress,raw=None,no_reply=False):
        wire=p.encode() if raw is None else raw
        evidence=self.save(f'request_{self.serial:04d}.bin',wire);self.serial+=1
        count=1 if no_reply else self.attempts
        for attempt in range(count):
            if attempt:self.retries+=1
            self.sock.sendto(wire,self.peer);self.network_sends+=1;self.event('SEND',case=name,attempt=attempt,**evidence)
            until=time.monotonic()+self.timeout
            while time.monotonic()<until:
                self.sock.settimeout(max(.001,until-time.monotonic()))
                try:received,source=self.sock.recvfrom(65535)
                except socket.timeout:break
                reply_evidence=self.save(f'reply_{self.received:04d}.bin',received);self.received+=1
                self.event('RECEIVE',case=name,source=list(source),**reply_evidence)
                if source!=self.peer:
                    self.ignored+=1;self.event('IGNORE',reason='source',case=name);continue
                try:r=decode(received)
                except InvalidPacket as exc:
                    self.ignored+=1;self.event('IGNORE',reason=exc.reason,case=name);continue
                envelope=(r.type==(int(p.type)|0x80) and r.session==p.session and r.frame_id==p.frame_id and r.sequence==p.sequence
                          and r.offset==p.offset and r.frame_bytes==INPUT_BYTES and r.frame_crc==p.frame_crc
                          and not r.payload and not r.flags and not r.reserved)
                if not envelope:
                    self.ignored+=1;self.event('IGNORE',reason='response_envelope',case=name);continue
                if no_reply:raise AssertionError(name+': corrupt header unexpectedly received trusted reply')
                if r.status!=status or r.next_offset!=progress:raise AssertionError(f'{name}: status/progress {r.status}/{r.next_offset}, expected {status}/{progress}')
                item={'case':name,'status':'PASS','reply_status':int(r.status),'next_offset':r.next_offset}
                self.cases.append(item);self.event('CASE_PASS',**item);return r
            if no_reply:
                item={'case':name,'status':'PASS','observation':'NO_TRUSTED_REPLY_WITHIN_PROBE_TIMEOUT','timeout_seconds':self.timeout}
                self.cases.append(item);self.event('CASE_PASS',**item);return None
        raise TimeoutError(name+': no valid new-image reply; factory echo is not EVF1 acknowledgement')
    def run(self,smoke_only=False):
        self.request('HELLO',Packet(Type.HELLO,self.session),Status.OK,0)
        self.request('STATUS_IDLE',Packet(Type.STATUS,self.session),Status.OK,0)
        if smoke_only:return self.finish(True)
        self.request('OLD_SESSION_REJECTED',Packet(Type.STATUS,b'old-invalid-sid!'),Status.SESSION,0)
        self.request('FUTURE_FRAME_REJECTED',Packet(Type.STATUS,self.session,frame_id=1),Status.FRAME_ID,0)
        # There are never enough DATA bytes to permit COMMIT or start the core.
        data=hashlib.shake_256(b'EVF1 INPUT RECOVERY PROBE, NOT VIDEO').digest(2048)
        frame_crc=zlib.crc32(data)
        begin=Packet(Type.BEGIN,self.session,frame_crc=frame_crc)
        self.request('BEGIN',begin,Status.ACK,0)
        self.request('OTHER_SESSION_CANNOT_TAKE_OVER',Packet(Type.HELLO,b'old-invalid-sid!'),Status.BUSY,0)
        packet0=Packet(Type.DATA,self.session,sequence=0,offset=0,frame_crc=frame_crc,payload=data[:1024])
        bad=packet0.encode();bad=bad[:-1]+bytes([bad[-1]^1])
        self.request('BAD_PAYLOAD_CRC_REJECTED',packet0,Status.PAYLOAD_CRC,0,raw=bad)
        packet1=replace(packet0,sequence=1,offset=1024,payload=data[1024:])
        self.request('FUTURE_CHUNK_REJECTED',packet1,Status.OFFSET,0)
        self.request('BAD_FLAGS_REJECTED',replace(packet0,flags=1),Status.FLAGS,0)
        self.request('SHORT_CHUNK_REJECTED',replace(packet0,payload=packet0.payload[:-1]),Status.LENGTH,0)
        self.request('WRONG_FRAME_CRC_REJECTED',replace(packet0,frame_crc=frame_crc^1),Status.FRAME_CRC,0)
        self.request('DATA0',packet0,Status.ACK,1024)
        # Save the first ACK but deliberately retry as if the application lost it.
        self.event('INTENTIONALLY_RETRY_AFTER_ONE_VALID_ACK',request_sequence=0)
        self.request('LOST_ACK_RETRY_SAME_PROGRESS',packet0,Status.ACK,1024)
        changed=replace(packet0,payload=bytes([packet0.payload[0]^1])+packet0.payload[1:])
        self.request('CHANGED_DUPLICATE_REJECTED',changed,Status.OFFSET,1024)
        self.request('DUPLICATE_BEGIN_RETAINS_PROGRESS',begin,Status.ACK,1024)
        self.request('INCOMPLETE_COMMIT_REJECTED',Packet(Type.COMMIT,self.session,sequence=507,offset=INPUT_BYTES,frame_crc=frame_crc),Status.OFFSET,1024)
        bad_header=bytearray(packet1.encode());bad_header[63]^=1
        self.request('BAD_HEADER_DISCARDED',packet1,None,None,raw=bytes(bad_header),no_reply=True)
        self.request('STATUS_STILL_RECEIVING',Packet(Type.STATUS,self.session),Status.ACK,1024)
        self.request('MISSING_CHUNK_RETRY',packet1,Status.ACK,2048)
        self.request('TOO_OLD_DUPLICATE_REJECTED',packet0,Status.OFFSET,2048)
        self.request('ABORT_HALF_FRAME',Packet(Type.ABORT,self.session),Status.OK,0)
        self.request('STATUS_RECOVERED_IDLE',Packet(Type.STATUS,self.session),Status.OK,0)
        self.session=secrets.token_bytes(16)
        self.request('FRESH_SESSION_AFTER_ABORT',Packet(Type.HELLO,self.session),Status.OK,0)
        self.request('OLD_SESSION_AFTER_RESTART_REJECTED',replace(packet1,session=packet0.session),Status.SESSION,0)
        return self.finish(True)
    def finish(self,success,error=None):
        if self.closed:return self.report
        self.closed=True;self.event('FINISH',success=success,error=error);self.sock.close();self.events.close()
        report={'status':'PASS_INPUT_PROTOCOL_ONLY_PENDING_INDEPENDENT_REVIEW' if success else 'FAIL',
                'success':success,'error':error,'scope':self.label,'cases':self.cases,'unique_requests':self.serial,'received':self.received,
                'retries':self.retries,'peer':list(self.peer),'local':list(self.local),'image_identity':self.image_identity,
                'network_sends':self.network_sends,'network_traffic_started':bool(self.network_sends),'ignored':self.ignored,
                'timeout_seconds':self.timeout,'maximum_attempts':self.attempts,
                'complete_frame_sent':False,'valid_COMMIT_sent':False,'Golden_or_video_acceptance':False,
                'physical_start_count_observed':None,'board_image_hardware_readback_verified':False}
        if not success and not self.network_sends:report['status']='LOCAL_PRECHECK_FAILED_NO_NETWORK_TRAFFIC'
        self.report=report
        (self.out/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (self.out/'SHA256SUMS.txt').write_text(''.join(sha(f.read_bytes())+'  '+f.name+'\n' for f in sorted(self.out.iterdir())if f.is_file()),encoding='ascii')
        return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image-manifest',required=True,type=Path)
    p.add_argument('--startup-capture-report',type=Path,help='Required post-JTAG PHY0 raw capture report for managed images')
    p.add_argument('--peer-ip',required=True);p.add_argument('--peer-port',type=int,default=5000)
    p.add_argument('--local-ip',required=True);p.add_argument('--local-port',type=int,default=6102)
    p.add_argument('--out-dir',required=True,type=Path);p.add_argument('--timeout',type=float,default=1.)
    p.add_argument('--attempts',type=int,default=3);p.add_argument('--smoke-only',action='store_true');a=p.parse_args()
    if not math.isfinite(a.timeout) or a.timeout<=0 or not 1<=a.attempts<=10:p.error('finite positive timeout and attempts1..10 required')
    try:
        identity=verify_image_manifest(a.image_manifest)
        identity['startup_permission']=verify_startup_permission(identity,a.startup_capture_report)
    except Exception as exc:
        a.out_dir.mkdir(parents=True,exist_ok=False)
        (a.out_dir/'REPORT.json').write_text(json.dumps({'status':'LOCAL_IMAGE_PRECHECK_FAILED_NO_NETWORK_TRAFFIC','error':repr(exc),'unique_requests':0},indent=2)+'\n',encoding='utf-8')
        print('LOCAL_IMAGE_PRECHECK_FAILED_NO_NETWORK_TRAFFIC');return 1
    try:probe=InputProbe((a.peer_ip,a.peer_port),(a.local_ip,a.local_port),a.out_dir,a.timeout,a.attempts,image_identity=identity)
    except OSError:
        print('LOCAL_PRECHECK_FAILED_NO_NETWORK_TRAFFIC');return 1
    try:
        probe.save('IMAGE_MANIFEST.json',a.image_manifest.read_bytes())
        r=probe.run(a.smoke_only)
    except Exception as exc:r=probe.finish(False,repr(exc))
    print(json.dumps({'status':r['status'],'cases':len(r['cases']),'out_dir':str(a.out_dir)}));return 0 if r['success'] else 1
if __name__=='__main__':raise SystemExit(main())
