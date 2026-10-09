"""Preencoded memory wire fixtures isolate actual host codec/log/PC4K/Tk.

There is no board, OS socket, SR computation or wire timing. Heavy Python board
model work is preparation; actual StreamingClient CRC/Golden/proofs still run.
"""
from pathlib import Path
from collections import deque
import hashlib,json,os,socket,struct,sys,tempfile,zlib
HERE=Path(__file__).resolve().parent;STREAM=HERE.parent;ROOT=STREAM.parents[2]
sys.path.insert(0,str(STREAM));sys.path.insert(0,str(ROOT/'experiments/pc_4k_20261007'))
from streaming_client import StreamingClient,PreparedGolden,Packet,encode2,decode_any
from pc4k_bridge import load_pipeline
import reference
from engine import measure
from live4k import TkPreview
from audit_live4k import audit_payloads
def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
class PreencodedPeer:
    address=('192.168.0.2',5000)
    def __init__(self,pairs,session,frames):
        self.queue=deque();self.frames=[];self.current=-1;self.base=self.next=0;self.proved=set();self.released=0
        self.hello=Packet(0x81,session,status=0).encode()
        cap=struct.pack('!HHB3x',1024,128,0x17)
        self.offer=encode2(Packet(0x81,session,frame_bytes=2073600,payload=cap,status=0))
        for f in range(frames):
            pixels,golden=pairs[f%len(pairs)];icrc=zlib.crc32(pixels);ocrc=zlib.crc32(golden)
            n=(len(pixels)+1023)//1024
            inputs=[Packet(0x83,session,f,q,q*1024,len(pixels),icrc,status=1,next_offset=min((q+1)*1024,len(pixels))).encode()for q in range(n)]
            packets=[];crc=[]
            for q,at in enumerate(range(0,len(golden),1024)):
                payload=golden[at:at+1024];last=at+len(payload)==len(golden);crc.append(zlib.crc32(payload))
                packets.append(encode2(Packet(0x17,session,f,q,at,len(golden),ocrc if last else 0,payload,status=1,flags=int(last))))
            self.frames.append(dict(input=inputs,output=packets,crc=crc,
                begin=Packet(0x82,session,f,frame_bytes=len(pixels),frame_crc=icrc,status=1).encode(),
                commit=Packet(0x84,session,f,n,len(pixels),len(pixels),icrc,status=2,next_offset=len(pixels)).encode(),
                final=encode2(Packet(0x89,session,f,len(packets),len(golden),len(golden),ocrc,status=4,next_offset=len(golden)))))
    def settimeout(self,value):assert value>0
    def burst(self):
        row=self.frames[self.current]
        while self.next<len(row['output'])and self.next<self.base+128:
            self.queue.append((row['output'][self.next],self.address));self.next+=1
    def sendto(self,raw,peer):
        assert peer==self.address
        kind=raw[5];f,q=struct.unpack('!II',raw[24:32])
        if kind==1:self.queue.append((self.hello if raw[4]==1 else self.offer,self.address))
        elif kind==2:
            assert f==self.released;self.current=f;self.base=self.next=0;self.proved.clear()
            self.queue.append((self.frames[f]['begin'],self.address))
        elif kind==3:self.queue.append((self.frames[f]['input'][q],self.address))
        elif kind==4:self.queue.append((self.frames[f]['commit'],self.address));self.burst()
        elif kind==0x97:
            _,p=decode_any(raw);assert p.frame_id==self.current
            for seq,crc in struct.iter_unpack('!II',p.payload):
                assert seq<self.next and self.frames[f]['crc'][seq]==crc;self.proved.add(seq)
            while self.base in self.proved:self.proved.remove(self.base);self.base+=1
            self.burst()
        elif kind==9:
            assert self.base==len(self.frames[f]['output']);self.released+=1
            self.queue.append((self.frames[f]['final'],self.address))
        else:raise AssertionError(kind)
        return len(raw)
    def recvfrom(self,n):
        if not self.queue:raise socket.timeout('preencoded fixture has no pending response')
        return self.queue.popleft()
def main():
    saved=HERE/'checks'/Path(tempfile.mkdtemp(prefix='pld_fast_wire_150_')).name;saved.mkdir(parents=True)
    print('SAVED_DIRECTORY='+str(saved),flush=True)
    runtime=ROOT/'experiments/pc_4k_20261007/runtime'
    os.environ['TCL_LIBRARY']=(runtime/'tcl8.6').as_posix();os.environ['TK_LIBRARY']=(runtime/'tk8.6').as_posix()
    base=ROOT/'host/baseline_ethernet/data';cfg=json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    pairs=[]
    for row in cfg['frames'][:2]:
        p,g=base/row['input_file'],base/row['golden_file'];assert sha(p)==row['input_sha256']and sha(g)==row['golden_sha256']
        pairs.append((p.read_bytes(),g.read_bytes()))
    session=bytes(range(16));peer=PreencodedPeer(pairs,session,150)
    module=load_pipeline();backend=module.CudaBicubic()
    expected=[reference.integer_reference(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920))for p,g in pairs]
    for p,g in pairs:priming,_=backend.resize(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920))
    preview=TkPreview(1280,720);preview.root.title('PLD PC协议150帧检查 · 预编码内存报文，无板卡/网络')
    preparation=preview.warmup(priming)
    client=StreamingClient(peer,peer.address,session,saved/'traffic',output_window=128,frame_log_mode='jsonl')
    try:
        result=measure(client,[(p,PreparedGolden(g))for p,g in pairs],module,backend,session.hex(),'PREENCODED_MEMORY_WIRE_NO_BOARD',
            saved/'measurement',150,30,preview=preview,source_kind='PREENCODED_MEMORY_WIRE_HOST_COST_NO_BOARD_OR_OS_SOCKET',expected_4k=expected,queue_accept_timeout=.5)
        assert result['status']=='COMPLETE_MEASUREMENT',result
        assert result['generated_4k_reference_zero_difference_frames']==result['preview_submitted']==peer.released==150
        report=dict(offered_slots=150,session=session.hex(),peer=list(peer.address),local=['192.168.0.3',6102],
                    measurement_result_sha256=sha(saved/'measurement/RESULTS.json'))
        audit=audit_payloads(saved,report,pairs,peer.address,('192.168.0.3',6102),module,reference)
        assert audit['frames']==150 and audit['actual_startup_reaudited']is False
    finally:preview.finish(saved)
    report=dict(status='PASS_PREENCODED_150_FRAME_HOST_CUDA_TK_STREAM_AUDIT_NOT_BOARD_RATE',measurement=result,audit=audit,
        preview_preparation=preparation,socket_created=False,board_run=False,whole_system_4K30_achieved=False,
        source_sha256={str(p.relative_to(ROOT)):sha(p)for p in (Path(__file__),HERE/'engine.py',HERE/'live4k.py',HERE/'audit_live4k.py',STREAM/'streaming_client.py',STREAM/'binary_journal.py')})
    (saved/'RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (HERE/'LATEST_fast_wire.json').write_text(json.dumps(dict(saved_directory=str(saved)),ensure_ascii=False),encoding='utf-8')
    print(report['status'])
if __name__=='__main__':main()
