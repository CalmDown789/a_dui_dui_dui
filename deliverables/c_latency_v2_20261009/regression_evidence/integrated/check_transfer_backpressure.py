"""End-to-end client checks on a synthetic peer with local write stalls."""
from pathlib import Path
import hashlib,json,os,socket,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'main/host'));sys.path.insert(0,str(ROOT/'main/streaming'))
from streaming_client import StreamingClient,decode_any
from nonblocking_io import TransportSendDeadlineError
from binary_journal import records
from host_regression_adapted import Peer,independent_audit
from transport_fixture import NonblockingPeer

class Stalled(NonblockingPeer):
    def __init__(self,peer,kind,permanent=False):
        super().__init__(peer);self.kind=kind;self.permanent=permanent;self.injected=False
        self.writable_at=0;self.stall_attempts=0
    def sendto(self,raw,address):
        _,p=decode_any(raw)
        if not self.injected and p.type==self.kind:
            self.injected=True;self.writable_at=time.perf_counter()+(1 if self.permanent else .002)
        if time.perf_counter()<self.writable_at:
            self.stall_attempts+=1;raise BlockingIOError(10035,'injected write stall')
        return super().sendto(raw,address)
    def wait_ready(self,read,write,timeout):
        assert timeout>0 and (read or write)
        self.wait_calls+=1
        remaining=max(0,self.writable_at-time.perf_counter())
        if read and self.peer.queue:return True,bool(write and remaining==0)
        time.sleep(min(timeout,remaining or .001))
        return bool(read and self.peer.queue),bool(write and time.perf_counter()>=self.writable_at)

run=ROOT/'validation/backpressure_runs'/str(time.time_ns());run.mkdir(parents=True)
ins=[bytes((q*23+f*17)&255 for q in range(4099))for f in range(2)]
gold=[bytes((q*31+f*11)&255 for q in range(4097))for f in range(2)]
sid=bytes(range(16));rows=[]
for name,kind,permanent in [('begin_once',2,False),('input_once',3,False),
                             ('proof_once',0x97,False),('final_once',9,False),('final_stalled',9,True)]:
    peer=Peer(ins,gold);transport=Stalled(peer,kind,permanent)
    out=run/name;c=StreamingClient(transport,peer.address,sid,out,len(ins[0]),len(gold[0]),
        timeout=.02,frame_timeout=.5,io_mode='nonblocking',readiness_waiter=transport.wait_ready,timing_mode=os.environ.get('STEP04_TIMING_MODE','full'))
    error=None;success=False
    try:
        c.hello()
        for f in range(2):assert c.transfer(ins[f],gold[f],f)==gold[f]
        c.finish();audit=independent_audit(out,ins,gold,sid);success=True
    except TransportSendDeadlineError as exc:error=repr(exc);c.abort()
    assert success is not permanent and transport.injected and transport.stall_attempts>=1
    if permanent:
        assert peer.frame_acks==0 and not c.frames and not(out/'JOURNAL.json').exists()
        assert (out/'ABORTED_CAPTURE.json').exists()
    else:
        assert peer.frame_acks==2 and c.retries==0
        raw=list(records(out/'datagrams.bin'))
        # A syscall that would-block does not add another TX journal record.
        assert sum(direction==0 for _,direction,_,_ in raw)==transport.send_calls
    assert c.io.max_pending_tx==1 and c.io.max_rx_buffer<=32
    rows.append(dict(case=name,status='PASS',transfer_success=success,releases=peer.frame_acks,
        error=error,write_stall_attempts=transport.stall_attempts,max_rx_buffer=c.io.max_rx_buffer,
        raw_directory=str(out),network_retries=c.retries))
    print('BACKPRESSURE_CASE='+name+' PASS',flush=True)
result=dict(status='PASS',timing_mode=os.environ.get('STEP04_TIMING_MODE','full'),cases=rows,scope='MEMORY_PEER_LOCAL_TX_STALL_NOT_OS_OR_BOARD',socket_created=False,
    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [Path(__file__),ROOT/'main/streaming/streaming_client.py',ROOT/'main/streaming/nonblocking_io.py',
         ROOT/'validation/transport_fixture.py',ROOT/'validation/host_regression_adapted.py',ROOT/'main/streaming/timing_diagnostics.py',ROOT/'main/streaming/binary_journal.py']})
(ROOT/'TRANSFER_BACKPRESSURE.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
