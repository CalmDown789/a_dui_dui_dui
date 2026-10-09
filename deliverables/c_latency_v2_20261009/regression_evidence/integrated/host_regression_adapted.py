"""No sockets: fault-injected peer plus independent binary raw evidence audit."""
from collections import deque
from dataclasses import replace
from pathlib import Path
import hashlib,json,socket,struct,sys,tempfile,time,zlib
HERE=Path(r'C:\t6int09\main\proof');ROOT=Path(r'C:\t6int09')
sys.path.insert(0,str(HERE.parent/'streaming'));sys.path.insert(0,str(HERE.parent/'host'))
from video_protocol import Packet,FrameReceiver,decode,InvalidPacket
from streaming_client import StreamingClient,encode2,decode_any
from injected_sender import Sender
from transport_fixture import tested_client as StreamingClient
from binary_journal import records
from audit_protocol import parse as audit_parse

class Peer:
    address=('192.168.0.2',5000)
    def __init__(self,inputs,goldens,fault=None):
        self.inputs,self.goldens,self.fault=inputs,goldens,fault;self.receiver=FrameReceiver(len(inputs[0]))
        self.queue=deque();self.window=16;self.sender=None;self.injected=False;self.frame_acks=0;self.last_done=None
        self.started=set();self.core_done=True;self.max_queue=0
    def settimeout(self,t):assert t>0
    def offer_output(self):
        for raw in self.sender.burst():self.queue.append((raw,self.address))
        self.max_queue=max(self.max_queue,len(self.queue))
    def sendto(self,raw,peer):
        assert peer==self.address
        version,p=decode_any(raw)
        if version==1:
            if p.type==3 and not self.injected and p.sequence==0 and self.fault=='drop_input_request':self.injected=True;return len(raw)
            reply=self.receiver.process(raw)
            if reply is not None:
                r=decode(reply)
                if p.type==3 and not self.injected and p.sequence==0:
                    if self.fault=='drop_input_ack':self.injected=True;return len(raw)
                    if self.fault=='bad_input_progress':reply=replace(r,next_offset=len(self.inputs[0])).encode();self.injected=True
                    if self.fault=='bad_input_source':self.queue.append((reply,('192.168.0.9',5000)));self.injected=True;return len(raw)
                if p.type==4 and p.frame_id not in self.started and r.status==2:
                    assert bytes(self.receiver.memory)==self.inputs[p.frame_id]
                    self.started.add(p.frame_id)
                    data=self.goldens[p.frame_id]
                    if self.fault=='wrong_golden':data=bytes([data[0]^1])+data[1:]
                    self.sender=Sender(data,p.session,p.frame_id,self.window,self.address,negotiated=True,output=True)
                    self.queue.append((reply,self.address))
                    if self.fault!='no_output':self.offer_output()
                    return len(raw)
                self.queue.append((reply,self.address))
        elif p.type==1:
            if self.fault=='no_negotiation':return len(raw)
            chunk,self.window,flow=struct.unpack('!HHB3x',p.payload);assert chunk==1024 and flow==0x17
            self.queue.append((encode2(replace(p,type=0x81,status=0)),self.address))
        elif p.type==0x97:
            if self.fault=='drop_output_ack' and not self.injected:self.injected=True;return len(raw)
            assert self.sender.acknowledge(raw,self.address);self.offer_output()
        elif p.type==9:
            identity=(p.session,p.frame_id,p.frame_crc)
            if self.last_done==identity:status=4
            elif self.sender is None or not self.sender.complete:status=24
            elif p.frame_crc!=self.sender.crc:status=21
            elif self.fault=='core_done_late' and not self.injected:self.injected=True;status=24
            else:
                self.receiver.release();self.frame_acks+=1;self.last_done=identity;status=4
            r=replace(p,type=0x89,status=status,next_offset=len(self.goldens[0]),payload=b'')
            if self.fault=='drop_final_reply' and not self.injected:self.injected=True;return len(raw)
            self.queue.append((encode2(r),self.address))
        else:raise AssertionError((version,p.type))
        self.max_queue=max(self.max_queue,len(self.queue));return len(raw)
    def recvfrom(self,n):
        if not self.queue and self.sender is not None and not self.sender.complete and self.fault!='no_output':
            for raw in self.sender.retry():self.queue.append((raw,self.address))
        if not self.queue:raise socket.timeout('in-memory timeout')
        raw,source=self.queue.popleft();version,p=decode_any(raw)
        # The RTL DATA descriptor uses ACK status=1. The older proposal model
        # used default status=0; normalize ONLY this injected peer's wire data.
        if version==2 and p.type==0x17:p=replace(p,status=1);raw=encode2(p)
        if version==2 and p.type==0x17 and self.fault=='zero_output_status':raw=encode2(replace(p,status=0))
        if version==2 and p.type==0x17 and not self.injected:
            fault=self.fault
            if fault=='drop_output_packet':self.injected=True;return self.recvfrom(n)
            if fault=='bad_output_source':source=('192.168.0.9',5000);self.injected=True
            if fault=='bad_output_session':raw=encode2(replace(p,session=b'X'*16));self.injected=True
            if fault=='bad_output_frame':raw=encode2(replace(p,frame_id=10));self.injected=True
            if fault=='bad_output_header_crc':raw=raw[:60]+bytes([raw[60]^1])+raw[61:];self.injected=True
            if fault=='bad_output_payload_crc':raw=raw[:-1]+bytes([raw[-1]^1]);self.injected=True
            if fault=='early_output_crc':raw=encode2(replace(p,frame_crc=123));self.injected=True
            if fault=='bad_output_last':raw=encode2(replace(p,flags=1));self.injected=True
            if fault=='duplicate_output':self.queue.appendleft((raw,source));self.injected=True
            if fault=='changed_duplicate':
                altered=replace(p,payload=bytes([p.payload[0]^1])+p.payload[1:]);self.queue.appendleft((encode2(altered),source));self.injected=True
            if fault=='reorder_output' and self.queue:
                other=self.queue.popleft();self.queue.appendleft((raw,source));raw,source=other;self.injected=True
                # The newly selected wire packet needs the same RTL status
                # normalization; this fault changes order, not packet status.
                other_version,other_packet=decode_any(raw)
                if other_version==2 and other_packet.type==0x17:raw=encode2(replace(other_packet,status=1))
        if version==2 and p.type==0x17 and self.fault=='bad_whole_crc' and p.flags&1:
            raw=encode2(replace(p,frame_crc=p.frame_crc^1));self.injected=True
        return raw,source

def independent_audit(out,inputs,goldens,session):
    coverage=[set() for _ in goldens];raw_input=[set() for _ in inputs];cum=[0 for _ in inputs]
    invalid=wrong_source=finals=0;proofs={};sent_inputs={}
    for stamp,direction,raw,source in records(out/'datagrams.bin'):
        if direction==1 and source!=Peer.address:wrong_source+=1;continue
        try:version,p=audit_parse(raw)
        except (ValueError,InvalidPacket):invalid+=1;continue
        if p.session!=session:invalid+=1;continue
        if direction==0 and version==1 and p.type==3:
            data=inputs[p.frame_id];assert p.offset==p.sequence*1024 and p.payload==data[p.offset:p.offset+1024]
            assert p.frame_crc==zlib.crc32(data);raw_input[p.frame_id].add(p.sequence);sent_inputs[(p.frame_id,p.sequence)]=p
        if direction==1 and version==1 and p.type==0x83 and p.status==1:
            original=sent_inputs[(p.frame_id,p.sequence)]
            assert p.offset==original.offset and p.frame_crc==original.frame_crc and p.next_offset==p.offset+len(original.payload)
            cum[p.frame_id]=max(cum[p.frame_id],p.sequence+1)
        if direction==0 and version==1 and p.type==4:
            assert cum[p.frame_id]==(len(inputs[p.frame_id])+1023)//1024 and p.frame_crc==zlib.crc32(inputs[p.frame_id])
        if direction==1 and version==2 and p.type==0x17:
            if not 0<=p.frame_id<len(goldens):invalid+=1;continue
            data=goldens[p.frame_id];at=p.sequence*1024;last=at+len(p.payload)==len(data)
            if p.offset!=at or p.payload!=data[at:at+1024] or p.flags!=int(last) or p.frame_crc!=(zlib.crc32(data) if last else 0):invalid+=1;continue
            coverage[p.frame_id].add(p.sequence);proofs[(p.frame_id,p.sequence)]=zlib.crc32(p.payload)
        if direction==0 and version==2 and p.type==0x97:
            for q,crc in struct.iter_unpack('!II',p.payload):assert proofs[(p.frame_id,q)]==crc
        if direction==0 and version==2 and p.type==9:
            assert coverage[p.frame_id]==set(range((len(goldens[p.frame_id])+1023)//1024))
            assert p.frame_crc==zlib.crc32(goldens[p.frame_id]);finals+=1
    for f,data in enumerate(inputs):assert raw_input[f]==set(range((len(data)+1023)//1024))
    result={'status':'PASS','frames':len(inputs),'golden_bytes':sum(map(len,goldens)),'invalid_records_retained':invalid,
        'wrong_source_records_retained':wrong_source,'final_ack_requests_checked':finals,'audit_uses_client_state':False}
    (out/'RAW_AUDIT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def main():
    saved=Path(r'C:\t6int09\validation\host_regression_runs')/Path(tempfile.mkdtemp(prefix='pld_stream_host_')).name;saved.mkdir(parents=True)
    print('SAVED_DIRECTORY='+str(saved),flush=True);session=bytes(range(16))
    inputs=[bytes((q*23+f*17)&255 for q in range(4099)) for f in range(2)]
    goldens=[bytes((q*31+f*11)&255 for q in range(4097)) for f in range(2)]
    success=[None,'drop_input_request','drop_input_ack','bad_input_source','drop_output_packet','drop_output_ack',
        'bad_output_source','bad_output_session','bad_output_frame','bad_output_header_crc','bad_output_payload_crc',
        'early_output_crc','bad_output_last','duplicate_output','changed_duplicate','reorder_output','core_done_late','drop_final_reply']
    failures=['bad_input_progress','wrong_golden','bad_whole_crc','no_negotiation','writer_failure','callback_failure','no_output','zero_output_status']
    rows=[]
    for fault in success+failures:
        peer=Peer(inputs,goldens,fault);out=saved/(fault or 'normal');client=StreamingClient(peer,peer.address,session,out,
            len(inputs[0]),len(goldens[0]),timeout=.001,frame_timeout=.3)
        passed=False;error=None;t=time.perf_counter_ns()
        try:
            client.hello()
            def callback(data,identity):
                assert data==goldens[identity['frame_id']] and identity['session']==session.hex()
                if fault=='writer_failure':client.journal.file.close()
                if fault=='callback_failure':raise RuntimeError('injected PC queue failure')
            for f in range(2):assert client.transfer(inputs[f],goldens[f],f,callback)==goldens[f]
            if fault=='changed_duplicate':assert client.frames[0]['output_rejected_packets']>0
            journal=client.finish();audit=independent_audit(out,inputs,goldens,session);passed=True
            assert peer.frame_acks==2 and peer.max_queue<=32
        except Exception as exc:error=repr(exc);client.abort()
        expect=fault in success
        assert passed==expect,(fault,error)
        if not expect:
            assert peer.frame_acks==0 and not (out/'JOURNAL.json').exists(),(fault,peer.frame_acks)
            assert not client.frames
        rows.append({'fault':fault or 'normal','status':'PASS','expected_transfer_success':expect,'observed_transfer_success':passed,
            'frame_releases':peer.frame_acks,'error':error,'offline_wall_ns':time.perf_counter_ns()-t,
            'max_input_retained':client.max_retained,'ignored':client.ignored,'retries':client.retries,'max_peer_queue':peer.max_queue})
        print('CASE='+str(fault or 'normal')+' PASS',flush=True)
    # Full frozen geometry on injected memory transport, not board/FSRCNN fps.
    base=ROOT/'main/data';m=json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    ins=[];outs=[]
    for row in m['frames'][:2]:
        for kind,dest in [('input',ins),('golden',outs)]:
            p=base/row[f'{kind}_file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row[f'{kind}_sha256'];dest.append(p.read_bytes())
    peer=Peer(ins,outs);out=saved/'full_frozen';client=StreamingClient(peer,peer.address,session,out)
    t=time.perf_counter_ns();client.hello()
    for f in range(2):assert client.transfer(ins[f],outs[f],f)==outs[f]
    client.finish();audit=independent_audit(out,ins,outs,session)
    result={'status':'PASS','fault_cases':rows,'full_frozen_audit':audit,'full_frozen_frames':client.frames,
        'offline_full_wall_ns':time.perf_counter_ns()-t,'socket_created':False,'board_run':False,
        'scope':'INJECTED_MEMORY_PEER_NO_SR_NETWORK_OS_PC4K_FRAME_RATE','io_mode':__import__('transport_fixture').MODE,'timing_mode':__import__('transport_fixture').TIMING_MODE,
        'source_sha256':{n:hashlib.sha256((HERE/n).read_bytes() if n=='host_regression.py' else (HERE.parent/'streaming'/n).read_bytes()).hexdigest() for n in ('host_regression.py','streaming_client.py','stream_receiver.py','binary_journal.py','audit_protocol.py','timing_diagnostics.py','nonblocking_io.py')}}
    (saved/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (Path(r'C:\t6int09\validation\LATEST_host.json')).write_text(json.dumps({'saved_directory':str(saved)},ensure_ascii=False),encoding='utf-8')
    print('STREAMING_HOST_PASS cases='+str(len(rows)),flush=True)
if __name__=='__main__':main()
