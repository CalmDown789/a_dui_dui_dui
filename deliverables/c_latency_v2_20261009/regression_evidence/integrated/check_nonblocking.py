"""Deterministic socket-free scheduler and client deadline fault checks."""
from collections import deque
from pathlib import Path
import errno, hashlib, json, os, socket, sys, time as real_time, zlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'main/host'));sys.path.insert(0,str(ROOT/'main/streaming'))
import streaming_client as client_module
import nonblocking_io as io_module
import binary_journal as journal_module
import timing_diagnostics as timing_module
TIMING_MODE=os.environ.get('STEP04_TIMING_MODE','full')
from video_protocol import Packet
from stream_receiver import OutputReceiver
from timing_diagnostics import BoundedTiming
from binary_journal import BinaryJournal,records
from streaming_client import StreamingClient,encode2,decode_any,FrameDeadlineError
from nonblocking_io import NonblockingDatagramIO,TransportSendDeadlineError,TransportProgressError

PEER=('192.168.0.2',5000);SID=bytes(range(16));rows=[]
RUN=ROOT/'validation/scheduler_runs'/str(real_time.time_ns())
RUN.mkdir(parents=True)

class Clock:
    def __init__(self):self.now=100.0
    def perf_counter(self):return self.now
    def perf_counter_ns(self):return round(self.now*1e9)
    def thread_time_ns(self):return real_time.thread_time_ns()
    def advance(self,amount):self.now+=amount

class Endpoint:
    def __init__(self,clock,packets=(),read_cost=0,write_after=0,early=False,spurious=False):
        self.clock=clock;self.queue=deque((clock.now+t,raw,source) for t,raw,source in packets)
        self.read_cost=read_cost;self.write_at=clock.now+write_after
        self.early=early;self.spurious=spurious;self.waits=[];self.sent=[]
        self.blocking_calls=[];self.send_calls=0;self.recv_calls=0
        self.partial=False;self.hard_error=False;self.on_send=None
    def setblocking(self,value):self.blocking_calls.append(value);assert value is False
    def settimeout(self,_):raise AssertionError('settimeout forbidden')
    def recvfrom(self,_):
        self.recv_calls+=1
        if not self.queue or self.queue[0][0]>self.clock.now:
            raise BlockingIOError(errno.EWOULDBLOCK,'RX unavailable')
        _,raw,source=self.queue.popleft();self.clock.advance(self.read_cost);return raw,source
    def sendto(self,raw,address):
        self.send_calls+=1
        if self.hard_error:raise OSError(errno.EACCES,'injected socket error')
        if self.clock.now<self.write_at:raise BlockingIOError(errno.EWOULDBLOCK,'TX unavailable')
        if self.partial:return len(raw)-1
        self.sent.append((self.clock.now,raw,address))
        if self.on_send:self.on_send(raw)
        return len(raw)
    def wait(self,read,write,timeout):
        assert timeout>0 and (read or write)
        self.waits.append((read,write,timeout))
        if self.spurious:return read,write
        if self.early:self.clock.advance(min(timeout,.00001));return False,False
        events=[self.clock.now+timeout]
        if read and self.queue:events.append(max(self.clock.now,self.queue[0][0]))
        if write:events.append(max(self.clock.now,self.write_at))
        self.clock.now=min(events)
        return bool(read and self.queue and self.queue[0][0]<=self.clock.now),bool(write and self.clock.now>=self.write_at)

clock=Clock()
original_times={m:m.time for m in (client_module,io_module,journal_module,timing_module)}
for m in original_times:m.time=clock

def reset():
    global clock
    clock=Clock()
    for m in original_times:m.time=clock
def service(name,ep,batch=32,budget=200_000,check=None):
    d=RUN/name
    journal=BinaryJournal(d);timing=BoundedTiming(mode=TIMING_MODE)
    def capture(raw,source,stamp):journal.append(1,raw,source,stamp=stamp)
    io=NonblockingDatagramIO(ep,journal,timing,capture,waiter=ep.wait,
        batch_packets=batch,batch_budget_ns=budget,clock=clock.perf_counter,check_deadline=check)
    return io,journal,timing
def passed(name,**detail):rows.append(dict(case=name,status='PASS',**detail));print('IO_CASE='+name+' PASS',flush=True)
def expect(error,fn):
    try:fn()
    except error as exc:return exc
    raise AssertionError('expected '+error.__name__)
def client(name,ep,**kw):
    return StreamingClient(ep,PEER,SID,RUN/name,io_mode='nonblocking',readiness_waiter=ep.wait,timing_mode=TIMING_MODE,**kw)

try:
    reset();ep=Endpoint(clock,[(0,bytes([q+1]),PEER) for q in range(10)])
    io,j,t=service('ready_rx',ep,batch=4)
    assert [io.receive(clock.now+.01)[0] for _ in range(10)]==[bytes([q+1]) for q in range(10)]
    assert not ep.waits and ep.blocking_calls==[False] and io.max_rx_buffer==4
    j.finalize();assert len(list(records(j.out/'datagrams.bin')))==10
    passed('ready_rx_no_select_or_settimeout',max_rx=io.max_rx_buffer)

    reset();ep=Endpoint(clock,[(0,b'a',PEER)]*10,read_cost=.00005)
    io,j,t=service('budget_rx',ep,batch=32,budget=100_000)
    io.receive(clock.now+.01)
    assert io.max_batch<=3 and io.max_batch>=2  # binary float boundary permits one extra syscall
    assert len(ep.queue)>=7;j.abort()
    passed('batch_time_budget_cooperative',max_batch=io.max_batch,read_syscall_model_ns=50_000)

    reset();ep=Endpoint(clock,[(.005,b'later',PEER)])
    io,j,t=service('delayed_rx',ep)
    assert io.receive(clock.now+.01)==(b'later',PEER) and len(ep.waits)==1
    assert abs(clock.now-100.005)<1e-9;j.finalize()
    passed('would_block_waits_for_readable')

    reset();ep=Endpoint(clock)
    io,j,t=service('receive_timeout',ep)
    expect(socket.timeout,lambda:io.receive(clock.now+.01))
    assert io.failed is None and len(ep.waits)==1;j.abort()
    passed('absolute_receive_timeout_not_transport_poison')

    reset();ep=Endpoint(clock,early=True)
    io,j,t=service('early_wake',ep)
    assert io.receive(clock.now+.01) is None and len(ep.waits)==1;j.abort()
    passed('early_readiness_return_not_response_loss')

    reset();ep=Endpoint(clock,[(.001,b'first',PEER),(.002,b'second',PEER)],write_after=.005)
    io,j,t=service('tx_backpressure',ep,batch=2)
    io.send(b'tx',PEER,clock.now+.01)
    assert len(ep.sent)==1 and ep.send_calls==2 and io.max_pending_tx==1 and io.max_rx_buffer==2
    assert any(not read and write for read,write,_ in ep.waits)
    assert [io.receive(clock.now+.01)[0] for _ in range(2)]==[b'first',b'second']
    j.finalize();r=list(records(j.out/'datagrams.bin'))
    assert [x[1] for x in r]==[0,1,1] and [x[2] for x in r]==[b'tx',b'first',b'second']
    assert [x[0] for x in r]==sorted(x[0] for x in r)
    passed('tx_would_block_bounded_rx_fifo_and_single_journal_tx',send_calls=ep.send_calls)

    reset();ep=Endpoint(clock,write_after=.05)
    io,j,t=service('tx_deadline',ep)
    expect(TransportSendDeadlineError,lambda:io.send(b'pending',PEER,clock.now+.01))
    assert not ep.sent and ep.send_calls==1 and io.pending is not None and io.failed is not None
    expect(RuntimeError,lambda:io.receive(clock.now+.01));j.abort()
    assert not (j.out/'JOURNAL.json').exists()
    passed('tx_stall_fatal_not_network_retry')

    for name,field in [('partial_send','partial'),('hard_socket_error','hard_error')]:
        reset();ep=Endpoint(clock);setattr(ep,field,True)
        io,j,t=service(name,ep)
        expect(OSError,lambda:io.send(b'x',PEER,clock.now+.01))
        assert io.failed is not None and not ep.sent;j.abort();passed(name)

    reset();ep=Endpoint(clock)
    io,j,t=service('journal_tx_failure',ep)
    def poison(*args,**kw):raise OSError('injected journal failure')
    j.append=poison
    expect(OSError,lambda:io.send(b'x',PEER,clock.now+.01))
    assert ep.send_calls==0 and io.failed is not None;j.abort()
    passed('journal_failure_prevents_send')

    reset();ep=Endpoint(clock,[(0,b'x',PEER)])
    io,j,t=service('journal_rx_failure',ep);j.append=poison
    expect(OSError,lambda:io.receive(clock.now+.01))
    assert not io.ready and io.failed is not None;j.abort()
    passed('rx_journal_failure_prevents_validation')

    reset();ep=Endpoint(clock,spurious=True)
    io,j,t=service('spurious_rx',ep)
    for _ in range(7):assert io.receive(clock.now+.01) is None
    expect(TransportProgressError,lambda:io.receive(clock.now+.01));j.abort()
    assert len(ep.waits)==8;passed('spurious_readiness_bounded_no_busy_loop')

    reset();ep=Endpoint(clock,write_after=.1,spurious=True)
    io,j,t=service('spurious_tx',ep)
    expect(TransportProgressError,lambda:io.send(b'x',PEER,clock.now+.01));j.abort()
    assert len(ep.waits)==8;passed('spurious_writable_bounded_no_busy_loop')

    reset();ep=Endpoint(clock,[(0,b'a',PEER),(0,b'b',PEER)])
    limit=clock.now+.005
    def guard():
        if clock.now>=limit:raise FrameDeadlineError('model frame deadline')
    io,j,t=service('buffered_frame_deadline',ep,check=guard)
    assert io.receive(clock.now+.01)[0]==b'a';clock.advance(.005)
    expect(FrameDeadlineError,lambda:io.receive(clock.now+.01));assert len(io.ready)==1;j.abort()
    passed('frame_deadline_checked_before_buffered_packet')

    reset();ep=Endpoint(clock)
    io,j,t=service('occupied_tx_slot',ep);io.pending=(b'older',PEER,False)
    expect(TransportProgressError,lambda:io.send(b'new',PEER,clock.now+.01))
    assert ep.send_calls==0 and io.pending[0]==b'older';j.abort()
    passed('occupied_tx_slot_rejects_reentrant_submission')

    # Timer fairness under continuous valid-CRC but wrong-session datagrams.
    junk=encode2(Packet(0x17,b'X'*16,payload=b'x',status=1))
    reset();ep=Endpoint(clock,[(0,junk,PEER)]*200,read_cost=.00005)
    c=client('proof_timer_flood',ep,input_bytes=1024,output_bytes=2048,output_window=16,output_ack_delay=.001)
    data=b'A'*2048;c.receiver=OutputReceiver(2048,SID,0,16,PEER)
    p=Packet(0x17,SID,0,0,0,2048,0,data[:1024],status=1)
    assert c.receiver.receive_packet(p,PEER,zlib.crc32(p.payload))
    c.ack_started=clock.now;start=clock.now
    while not ep.sent:c.receive()
    ack_at,raw,_=ep.sent[0];assert decode_any(raw)[1].type==0x97
    assert ack_at-start<=.001201 and c.retries==0;c.abort()
    passed('proof_timer_serviced_during_rx_flood',model_ack_delay_ns=round((ack_at-start)*1e9))

    reset();ep=Endpoint(clock,[(0,junk,PEER)]*1000,read_cost=.00005)
    c=client('input_retry_flood',ep,input_bytes=4096,output_bytes=1024,timeout=.001,attempts=2)
    start=clock.now
    expect(TimeoutError,lambda:c.input_packets(b'I'*4096,0,zlib.crc32(b'I'*4096)))
    data_sent=[decode_any(raw)[1] for _,raw,_ in ep.sent]
    assert len(data_sent)==8 and all(sum(p.sequence==q for p in data_sent)==2 for q in range(4))
    assert clock.now-start<=.002101 and c.retries==4;c.abort()
    passed('absolute_input_retry_under_unrelated_flood',model_elapsed_ns=round((clock.now-start)*1e9))

    reset();ep=Endpoint(clock,read_cost=.00005)
    c=client('negotiation_flood',ep,input_bytes=1024,output_bytes=1024,timeout=.001,attempts=3)
    def reply_initial_hello(raw):
        version,p=decode_any(raw)
        if version==1 and p.type==1:
            ep.queue.append((clock.now,Packet(0x81,SID,frame_bytes=1024).encode(),PEER))
        elif version==2:
            ep.queue.extend((clock.now,junk,PEER) for _ in range(200))
    ep.on_send=reply_initial_hello;start=clock.now
    expect(TimeoutError,c.hello)
    sent=[decode_any(raw) for _,raw,_ in ep.sent]
    assert sum(v==2 and p.type==1 for v,p in sent)==3
    assert not any(p.type in (2,3,4,9) for _,p in sent) and clock.now-start<=.003201
    assert not c.negotiated;c.abort()
    passed('absolute_negotiation_deadline_no_begin_on_failure',model_elapsed_ns=round((clock.now-start)*1e9))

    reset();ep=Endpoint(clock,early=True)
    c=client('early_ack_wake_client',ep,timeout=.02,output_ack_delay=.001)
    c.receiver=OutputReceiver(2048,SID,0,16,PEER)
    p=Packet(0x17,SID,0,0,0,2048,0,b'A'*1024,status=1)
    assert c.receiver.receive_packet(p,PEER,zlib.crc32(p.payload))
    c.ack_started=clock.now
    assert c.receive() is None and c.ack_started is not None and not ep.sent and c.retries==0;c.abort()
    passed('early_ack_wakeup_not_flush_or_retry')

    reset();ep=Endpoint(clock)
    c=client('stale_frame_timer',ep,timeout=.02,output_ack_delay=.001)
    c.ack_started=clock.now-1;start=clock.now
    expect(socket.timeout,c.receive)
    assert c.ack_started is None and clock.now-start>=.0199 and len(ep.waits)==1;c.abort()
    passed('stale_cross_frame_timer_cleared_before_wait')

    reset();ep=Endpoint(clock,write_after=.01)
    c=client('control_reply_before_send',ep,input_bytes=1024,output_bytes=1024,timeout=.002)
    request=Packet(2,SID,frame_bytes=1024)
    ep.queue.append((clock.now,Packet(0x82,SID,frame_bytes=1024,status=1).encode(),PEER))
    expect(TransportSendDeadlineError,lambda:c.exchange(request,{1},progress=0))
    assert not ep.sent and c.retries==0 and not c.frames;c.abort()
    passed('buffered_reply_cannot_complete_unsent_control')
finally:
    for m,original in original_times.items():m.time=original

result=dict(status='PASS',timing_mode=TIMING_MODE,checks=rows,scope='DETERMINISTIC_MODEL_CLOCK_INJECTED_TRANSPORT_NOT_OS_OR_BOARD_TIMING',
            board_io=False,socket_created=False,batch_packets_default=32,batch_budget_ns_default=200_000,max_pending_tx=1,
            run_directory=str(RUN),source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__),ROOT/'main/streaming/streaming_client.py',ROOT/'main/streaming/nonblocking_io.py',ROOT/'main/streaming/timing_diagnostics.py',ROOT/'main/streaming/binary_journal.py']})
(ROOT/'NONBLOCKING_CHECKS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('NONBLOCKING_PASS cases='+str(len(rows)))
