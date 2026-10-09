"""EVF1 continuous input/result client. Peer must run the new application image.

Factory ch52 only echoes bytes and is intentionally rejected by this client.
All outputs remain unaccepted until the physical run and evidence are reviewed.
"""
from datetime import datetime,timezone
import argparse,base64,hashlib,json,secrets,socket,struct,time,zlib
from pathlib import Path
from video_protocol import Packet,Type,Status,INPUT_BYTES,OUTPUT_BYTES,decode,InvalidPacket
from video_image_identity import verify_image_manifest
from startup_status_identity import verify_startup_permission
from video_sequence_identity import verify_sequence

def sha(data):return hashlib.sha256(data).hexdigest()

class LocalPrecheckError(RuntimeError):
    """Socket could not bind; no request was sent to the board."""

class VideoClient:
    def __init__(self,peer,local,out,timeout=1.0,attempts=3,frame_timeout=300.0,
                 input_bytes=INPUT_BYTES,output_bytes=OUTPUT_BYTES,label='UNACCEPTED_PEER_VIDEO_RUN'):
        self.peer=peer;self.timeout=timeout;self.attempts=attempts;self.frame_timeout=frame_timeout
        self.input_bytes=input_bytes;self.output_bytes=output_bytes;self.label=label
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:self.sock.bind(local)
        except OSError as exc:
            self.sock.close()
            result={'status':'LOCAL_SOCKET_PRECHECK_FAILED_NO_NETWORK_TRAFFIC','success':False,
                'error':f'{type(exc).__name__}: {exc}','label':label,'peer':list(peer),'local':list(local),
                'network_traffic_started':False,'frames':[],'unique_requests':0,'received':0,
                'board_and_image_identity_verified_by_this_script':False,'strict_FPS_requirement':None}
            summary=self.out/'SUMMARY.json';summary.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            (self.out/'SHA256SUMS.txt').write_text(sha(summary.read_bytes())+'  SUMMARY.json\n',encoding='ascii')
            raise LocalPrecheckError(result['error']) from exc
        self.events=(self.out/'events.jsonl').open('x',encoding='utf-8')
        self.session=secrets.token_bytes(16);self.serial=self.received=self.retries=self.ignored=0
        self.frames=[];self.deadline=None;self.closed=False
    def event(self,kind,**fields):
        self.events.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'event':kind,**fields})+'\n');self.events.flush()
    def save(self,name,data):
        with (self.out/name).open('xb') as f:f.write(data)
        return {'file':name,'bytes':len(data),'sha256':sha(data)}
    def exchange(self,p,accepted,result_payload=False):
        raw=p.encode();evidence=self.save(f'request_{self.serial:06d}.bin',raw);self.serial+=1
        for attempt in range(self.attempts):
            if self.deadline is not None and time.monotonic()>self.deadline:raise TimeoutError('frame deadline expired')
            if attempt:self.retries+=1
            self.sock.sendto(raw,self.peer);self.event('SEND',attempt=attempt,type=int(p.type),frame=p.frame_id,sequence=p.sequence,**evidence)
            until=time.monotonic()+self.timeout
            while time.monotonic()<until:
                self.sock.settimeout(max(.00001,until-time.monotonic()))
                try:raw_reply,source=self.sock.recvfrom(65535)
                except socket.timeout:break
                item=self.save(f'response_{self.received:06d}.bin',raw_reply);self.received+=1;self.event('RECEIVE',source=list(source),**item)
                try:r=decode(raw_reply)
                except InvalidPacket as exc:self.ignored+=1;self.event('IGNORE',reason=exc.reason);continue
                valid=(source==self.peer and r.type==int(p.type)|0x80 and r.session==p.session and r.frame_id==p.frame_id
                       and r.sequence==p.sequence and r.offset==p.offset and r.frame_bytes==p.frame_bytes and not r.reserved)
                if not result_payload:valid=valid and not r.payload and not r.flags and r.frame_crc==p.frame_crc
                else:
                    valid=valid and r.flags in (0,1)
                    if r.status!=Status.ACK:valid=valid and not r.payload and not r.flags and r.frame_crc==p.frame_crc
                if not valid:self.ignored+=1;self.event('IGNORE',reason='source_identity_envelope');continue
                if r.status==Status.PAYLOAD_CRC:break
                if r.status not in accepted:raise RuntimeError(f'peer rejection status={r.status} type={p.type} sequence={p.sequence}')
                self.event('ACK',type=int(p.type),frame=p.frame_id,sequence=p.sequence,status=r.status,next_offset=r.next_offset)
                return r
            self.event('RETRY_OR_TIMEOUT',attempt=attempt)
        raise TimeoutError(f'no valid reply after {self.attempts} attempts: type={p.type} seq={p.sequence}')
    def hello(self):
        self.exchange(Packet(Type.HELLO,self.session,frame_bytes=self.input_bytes),{Status.OK})
    def transfer_frame(self,pixels,golden,frame_id):
        if len(pixels)!=self.input_bytes or len(golden)!=self.output_bytes:raise ValueError('input/Golden byte count mismatch')
        began=time.perf_counter_ns();self.deadline=time.monotonic()+self.frame_timeout
        crc=zlib.crc32(pixels);input_meta=self.save(f'frame_{frame_id:04d}_input.bin',pixels)
        r=self.exchange(Packet(Type.BEGIN,self.session,frame_id,frame_bytes=self.input_bytes,frame_crc=crc),{Status.ACK})
        if r.next_offset!=0:raise RuntimeError('fresh frame unexpectedly has data; no implicit resume')
        for seq,off in enumerate(range(0,len(pixels),1024)):
            chunk=pixels[off:off+1024]
            r=self.exchange(Packet(Type.DATA,self.session,frame_id,seq,off,self.input_bytes,crc,chunk),{Status.ACK})
            if r.next_offset!=off+len(chunk):raise RuntimeError('input progress mismatch')
        sent=time.perf_counter_ns()
        r=self.exchange(Packet(Type.COMMIT,self.session,frame_id,(len(pixels)+1023)//1024,len(pixels),self.input_bytes,crc),{Status.STARTED})
        if r.next_offset!=len(pixels):raise RuntimeError('COMMIT progress mismatch')
        committed=time.perf_counter_ns();result=bytearray();declared_crc=None
        for seq,off in enumerate(range(0,self.output_bytes,1024)):
            while True:
                r=self.exchange(Packet(Type.READ_RESULT,self.session,frame_id,seq,off,self.output_bytes),{Status.ACK,Status.NOT_READY},True)
                if r.status==Status.ACK:break
                if time.monotonic()>self.deadline:raise TimeoutError('result never became ready')
                time.sleep(.001)
            length=min(1024,self.output_bytes-off);last=off+length==self.output_bytes
            if len(r.payload)!=length or bool(r.flags&1)!=last or r.next_offset!=off or (not last and r.frame_crc!=0):
                raise RuntimeError('result length/LAST/progress/CRC field mismatch')
            result.extend(r.payload)
            if last:declared_crc=r.frame_crc
            r=self.exchange(Packet(Type.ACK_RESULT,self.session,frame_id,seq,off,self.output_bytes,payload=struct.pack('!I',zlib.crc32(r.payload))),{Status.ACK})
            if r.next_offset!=off+length:raise RuntimeError('result ACK progress mismatch')
        got=time.perf_counter_ns();actual=bytes(result);output_meta=self.save(f'frame_{frame_id:04d}_result.bin',actual)
        if zlib.crc32(actual)!=declared_crc:raise RuntimeError('whole output CRC mismatch')
        if actual!=golden:raise RuntimeError('output differs from frozen Golden; frame ACK withheld')
        verified=time.perf_counter_ns()
        while True:
            r=self.exchange(Packet(Type.ACK_FRAME,self.session,frame_id,(self.output_bytes+1023)//1024,self.output_bytes,self.output_bytes,declared_crc),{Status.FRAME_DONE,Status.NOT_READY})
            if r.status==Status.FRAME_DONE:break
            if time.monotonic()>self.deadline:raise TimeoutError('core completion/frame release timeout')
            time.sleep(.001)
        if r.next_offset!=self.output_bytes:raise RuntimeError('final frame ACK progress mismatch')
        finished=time.perf_counter_ns();self.deadline=None
        record={'frame_id':frame_id,'input':input_meta,'result':output_meta,'golden_sha256':sha(golden),
            'input_crc32':f'{crc:08x}','result_crc32':f'{declared_crc:08x}','golden_match':True,
            'host_timing_ns':{'input_begin_to_last_data_ack':sent-began,'commit_exchange':committed-sent,
                              'commit_ack_to_full_result_and_packet_acks':got-committed,'verify':verified-got,
                              'final_frame_ack':finished-verified,'whole_frame':finished-began},
            'timing_scope':'HOST_WALL_CLOCK_INCLUDES_OS_NETWORK_PROTOCOL_AND_OVERLAP_NOT_ISOLATED_CORE_LATENCY'}
        self.frames.append(record);self.event('FRAME_COMPLETE',**record)
        (self.out/'FRAMES.json').write_text(json.dumps(self.frames,indent=2)+'\n',encoding='utf-8')
        return actual
    def close(self,success,error=None):
        if self.closed:return
        self.closed=True;self.event('FINISH',success=success,error=error);self.events.close();self.sock.close()
        result={'status':'PASS_BYTES_AGAINST_PROVIDED_GOLDEN_PENDING_INDEPENDENT_REVIEW' if success else 'FAIL',
            'success':success,'error':error,'label':self.label,'session':self.session.hex(),'peer':list(self.peer),
            'input_bytes':self.input_bytes,'output_bytes':self.output_bytes,'frames':self.frames,'unique_requests':self.serial,
            'received':self.received,'retries':self.retries,'ignored':self.ignored,
            'board_and_image_identity_verified_by_this_script':False,'strict_FPS_requirement':None}
        (self.out/'SUMMARY.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        (self.out/'SHA256SUMS.txt').write_text(''.join(sha(f.read_bytes())+'  '+f.name+'\n' for f in sorted(self.out.iterdir()) if f.is_file()),encoding='ascii')
        return result

def png_y(pixels,width=1920,height=1080):
    if len(pixels)!=width*height:raise ValueError('PNG dimensions mismatch')
    def block(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
    rows=b''.join(b'\0'+pixels[y*width:(y+1)*width] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+block(b'IHDR',struct.pack('!IIBBBBB',width,height,8,0,0,0,0))+block(b'IDAT',zlib.compress(rows))+block(b'IEND',b'')

def playback(out,frames):
    images=[base64.b64encode(png_y(f)).decode('ascii') for f in frames]
    html='''<!doctype html><meta charset="utf-8"><title>以太网回传顺序回放</title>
<style>body{font-family:system-ui;background:#171717;color:#ddd;margin:24px}img{width:min(100%,1920px);image-rendering:auto}button,input{margin:8px}</style>
<p>实际回传帧的离线顺序回放；播放速度可调，不代表 FPGA 处理帧率。Golden 对拍及实际耗时见 SUMMARY.json。</p>
<button id="play">播放/暂停</button><input id="rate" type="number" min="1" max="60" value="8">播放 fps
<input id="seek" type="range" min="0" value="0"><span id="label"></span><br><img id="image">
<script>const frames=IMAGES;let idx=0,running=false,last=0;const seek=document.getElementById('seek');seek.max=frames.length-1;
function show(){document.getElementById('image').src='data:image/png;base64,'+frames[idx];seek.value=idx;document.getElementById('label').textContent='frame_id '+idx+' / '+(frames.length-1);}
document.getElementById('play').onclick=()=>{running=!running;};seek.oninput=()=>{idx=+seek.value;show();};
function tick(t){if(running&&t-last>=1000/Math.max(1,+document.getElementById('rate').value)){idx=(idx+1)%frames.length;show();last=t;}requestAnimationFrame(tick);}show();requestAnimationFrame(tick);</script>'''.replace('IMAGES',json.dumps(images))
    with (Path(out)/'playback.html').open('x',encoding='utf-8') as f:f.write(html)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--image-manifest',required=True,type=Path,help='Separately issued, I/O-signed-off new video BIT manifest')
    p.add_argument('--startup-capture-report',type=Path,help='Required post-JTAG PHY0 raw capture report for managed images')
    p.add_argument('--peer-ip',required=True);p.add_argument('--peer-port',type=int,default=5000)
    p.add_argument('--local-ip',required=True);p.add_argument('--local-port',type=int,default=6102)
    p.add_argument('--out-dir',required=True,type=Path);p.add_argument('--timeout',type=float,default=1.)
    p.add_argument('--attempts',type=int,default=3);p.add_argument('--frame-timeout',type=float,default=300.)
    a=p.parse_args()
    if a.timeout<=0 or a.frame_timeout<=0 or not 1<=a.attempts<=10:p.error('positive deadlines and attempts1..10 required')
    try:
        image_identity=verify_image_manifest(a.image_manifest)
        image_identity['startup_permission']=verify_startup_permission(image_identity,a.startup_capture_report)
        prepared,sequence_identity=verify_sequence(a.manifest)
    except Exception as exc:
        a.out_dir.mkdir(parents=True,exist_ok=False)
        (a.out_dir/'SUMMARY.json').write_text(json.dumps({'status':'LOCAL_IDENTITY_PRECHECK_FAILED_NO_NETWORK_TRAFFIC',
            'success':False,'error':repr(exc),'unique_requests':0,'received':0,'frames':[],
            'network_traffic_started':False},indent=2)+'\n',encoding='utf-8')
        print('LOCAL_IDENTITY_PRECHECK_FAILED_NO_NETWORK_TRAFFIC');return 1
    try:client=VideoClient((a.peer_ip,a.peer_port),(a.local_ip,a.local_port),a.out_dir,a.timeout,a.attempts,a.frame_timeout)
    except LocalPrecheckError:
        print(json.dumps({'status':'LOCAL_SOCKET_PRECHECK_FAILED_NO_NETWORK_TRAFFIC','frames':0,'out_dir':str(a.out_dir)}))
        return 1
    actual=[]
    try:
        client.save('SOURCE_MANIFEST.json',a.manifest.read_bytes())
        client.save('IMAGE_MANIFEST.json',a.image_manifest.read_bytes())
        client.save('LOCAL_IDENTITY.json',(json.dumps({'image':image_identity,'sequence':sequence_identity},indent=2)+'\n').encode('utf-8'))
        client.hello()
        for i,(input_data,golden) in enumerate(prepared):actual.append(client.transfer_frame(input_data,golden,i))
        playback(a.out_dir,actual);r=client.close(True)
    except Exception as exc:r=client.close(False,f'{type(exc).__name__}: {exc}')
    print(json.dumps({'status':r['status'],'frames':len(r['frames']),'out_dir':str(a.out_dir)},ensure_ascii=True))
    return 0 if r['success'] else 1
if __name__=='__main__':raise SystemExit(main())
