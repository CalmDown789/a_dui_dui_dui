"""Injected-transport candidate. This module never constructs a socket.

EVF1 input packets are pipelined with bounded retained requests and per-sequence
ACK checks. EVF2 output is explicitly negotiated and proof-ACKed in batches.
The existing model/numeric bytes are unchanged. No production image gate is
bypassed: a live caller must provide its independently authorized transport.
"""
from collections import deque
from dataclasses import dataclass,field
from pathlib import Path
import hashlib,json,socket,struct,sys,time,zlib
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'sources/host'))
sys.path.insert(0,str(HERE.parent/'optimization_20261007'))
from video_protocol import Packet,decode,InvalidPacket,HEADER,CHUNK_BYTES
from stream_receiver import OutputReceiver
from binary_journal import BinaryJournal
from timing_diagnostics import BoundedTiming
from nonblocking_io import NonblockingDatagramIO

def encode2(p):
    raw=p.encode();head=b'EVF2\x02'+raw[5:60];return head+struct.pack('!I',zlib.crc32(head))+raw[64:]
def decode_any(raw):
    if raw[:5]==b'EVF1\x01':return 1,decode(raw)
    if raw[:5]!=b'EVF2\x02' or len(raw)<64:
        raise InvalidPacket('version/header CRC')
    (magic,version,kind,flags,session,frame_id,sequence,offset,frame_bytes,frame_crc,
     count,status,next_offset,reserved,payload_crc,header_crc)=HEADER.unpack_from(raw)
    if zlib.crc32(raw[:60])!=header_crc:
        raise InvalidPacket('version/header CRC')
    if len(raw)>64+CHUNK_BYTES:raise InvalidPacket('LENGTH')
    # Validate the original EVF2 bytes once; avoid constructing an EVF1 surrogate.
    packet=Packet(kind,session,frame_id,sequence,offset,frame_bytes,frame_crc,
                  raw[64:],status,next_offset,flags,reserved)
    if count!=len(raw)-64:raise InvalidPacket('LENGTH',packet)
    if zlib.crc32(packet.payload)!=payload_crc:raise InvalidPacket('PAYLOAD_CRC',packet)
    return version,packet

class FrameDeadlineError(RuntimeError):
    """Distinct from socket.timeout (which aliases TimeoutError in Python)."""

@dataclass(frozen=True)
class PreparedGolden:
    """Hash immutable lab Golden once during startup/preparation, not per frame."""
    data: bytes
    sha256: str=field(init=False)
    def __post_init__(self):
        if not isinstance(self.data,bytes):raise TypeError('Golden must be immutable bytes')
        object.__setattr__(self,'sha256',hashlib.sha256(self.data).hexdigest())

class StreamingClient:
    def __init__(self,transport,peer,session,out,input_bytes=518400,output_bytes=2073600,
                 input_window=16,output_window=16,timeout=.02,attempts=4,frame_timeout=10,output_ack_batch=None,output_ack_delay=.001,frame_log_mode='snapshot',
                 io_mode='timeout',readiness_waiter=None,receive_batch_packets=32,receive_batch_budget_ns=200_000,timing_mode='full',timing_sample_every=16):
        if io_mode not in ('timeout','nonblocking'):raise ValueError('explicit IO mode')
        if not 1<=receive_batch_packets<=128 or not 1<=receive_batch_budget_ns<=10_000_000:raise ValueError('bounded receive batch')
        if io_mode=='nonblocking' and not callable(getattr(transport,'setblocking',None)):raise TypeError('nonblocking transport required')
        if len(session)!=16 or not 1<=input_window<=16 or not 1<=output_window<=128:raise ValueError('bounded explicit configuration')
        if timeout<=0 or frame_timeout<=0 or not 1<=attempts<=10:raise ValueError('deadlines')
        self.transport,self.peer,self.session=transport,peer,session
        self.input_bytes,self.output_bytes=input_bytes,output_bytes
        self.iw,self.ow,self.timeout,self.attempts,self.frame_timeout=input_window,output_window,timeout,attempts,frame_timeout
        self.ack_batch=min(output_window,32) if output_ack_batch is None else output_ack_batch
        if not 1<=self.ack_batch<=output_window:raise ValueError('ACK batch exceeds retained window')
        if output_ack_delay<=0:raise ValueError('positive ACK flush deadline required')
        if frame_log_mode not in ('snapshot','jsonl'):raise ValueError('frame log mode')
        self.ack_delay=output_ack_delay;self.ack_started=None
        self.timing=BoundedTiming(mode=timing_mode,sample_every=timing_sample_every)
        self.journal=BinaryJournal(out,timing=self.timing);self.out=Path(out);self.receiver=None;self.golden=None
        self.frame_log_mode=frame_log_mode
        self.frame_event_file=(self.out/'FRAMES.jsonl').open('x',encoding='utf-8') if frame_log_mode=='jsonl' else None
        self.inbox=deque();self.frames=[];self.serial=self.received=self.ignored=self.retries=self.max_retained=0
        self.deadline=None;self.negotiated=False;self.max_inbox=0;self._last_recv_return_ns=None;self._timing_saved=False
        self.io_mode=io_mode;self.io=None
        if io_mode=='nonblocking':
            try:
                self.io=NonblockingDatagramIO(transport,self.journal,self.timing,self._capture_rx,
                    waiter=readiness_waiter,batch_packets=receive_batch_packets,
                    batch_budget_ns=receive_batch_budget_ns,check_deadline=self.check_deadline)
            except BaseException:
                self.abort();raise
    def _capture_rx(self,raw,source,stamp):
        self.journal.append(1,raw,source,stamp=stamp);self.received+=1
    def send(self,raw):
        self.check_deadline()
        if self.io is None:self.journal.append(0,raw,self.peer)
        send_stage='scheduled_send' if self.io is not None else 'sendto'
        sample=self.timing.begin(send_stage)
        try:
            if self.io is None:
                if self.transport.sendto(raw,self.peer)!=len(raw):raise OSError('partial datagram send')
            else:
                until=time.perf_counter()+self.timeout
                if self.deadline is not None:until=min(until,self.deadline)
                self.io.send(raw,self.peer,until)
        finally:
            if sample is not None:
                self.timing.end(send_stage,sample,{'wire_version':raw[4] if len(raw)>4 else None,
                    'packet_type':raw[5] if len(raw)>5 else None,'raw_bytes':len(raw)})
        self.serial+=1;self.timing.increment('sendto_datagrams')
        if len(raw)>5 and raw[:4]==b'EVF2' and raw[5]==0x97:
            self.timing.increment('proof_ack_datagrams')
            self.timing.increment('proof_ack_entries',max(0,(len(raw)-64)//8))
    def check_deadline(self):
        if self.deadline is not None and time.perf_counter()>=self.deadline:raise FrameDeadlineError('frame deadline')
    def output_acks(self):
        if self.receiver is None or not self.receiver.ack_pending:
            # A frame may finish while a delayed ACK timer is still armed. Once
            # DONE retires that receiver, no proof remains to flush; retaining
            # the expired deadline would make the next control exchange spin
            # through its retries without waiting on the socket.
            self.ack_started=None
            return
        sample=self.timing.begin('proof_batch_take')
        body=self.receiver.take_proofs()
        if sample is not None:self.timing.end('proof_batch_take',sample,{'entries':len(body)//8})
        self.ack_started=None
        sample=self.timing.begin('proof_packet_build')
        raw=encode2(Packet(0x97,self.session,self.receiver.frame,frame_bytes=self.output_bytes,
            payload=body,status=1,next_offset=min(self.receiver.contiguous*1024,self.output_bytes)))
        if sample is not None:self.timing.end('proof_packet_build',sample,{'entries':len(body)//8,'raw_bytes':len(raw)})
        self.send(raw)
    # QPC/perf_counter is monotonic and high resolution on Windows; Python
    # 3.11/3.12 monotonic may use a 15.625ms GetTickCount64 clock.
    def receive(self,control_deadline=None):
        self.check_deadline()
        now=time.perf_counter()
        if self.ack_started is not None and now-self.ack_started>=self.ack_delay:
            self.output_acks();now=time.perf_counter()
        wait=self.timeout
        if self.deadline is not None:wait=min(wait,max(0,self.deadline-now))
        if control_deadline is not None:
            if now>=control_deadline:raise socket.timeout('control deadline')
            wait=min(wait,control_deadline-now)
        ack_wakeup=False
        if self.ack_started is not None:
            ack_wait=max(0,self.ack_started+self.ack_delay-now)
            ack_wakeup=ack_wait<=wait
            wait=min(wait,ack_wait)
        if wait<=0:self.check_deadline();raise socket.timeout('receive deadline')
        if getattr(self,'io',None) is None:
            sample=self.timing.begin('settimeout')
            try:self.transport.settimeout(wait)
            finally:
                if sample is not None:self.timing.end('settimeout',sample,{'requested_timeout_ns':int(wait*1e9)})
        recv_stage='scheduled_receive' if getattr(self,'io',None) is not None else 'recvfrom'
        sample=self.timing.begin(recv_stage)
        if self.timing.mode=='full' and self._last_recv_return_ns is not None:
            self.timing.record('receive_service_interval',sample[0]-self._last_recv_return_ns)
        try:
            if getattr(self,'io',None) is None:raw,source=self.transport.recvfrom(65535)
            else:
                item=self.io.receive(now+wait)
                if item is None:
                    if sample is not None:self.timing.end(recv_stage,sample,{'result':'early_wakeup'})
                    if self.timing.mode=='full':self._last_recv_return_ns=time.perf_counter_ns()
                    return None
                raw,source=item
        except socket.timeout:
            recv_end=time.perf_counter_ns() if sample is not None else None
            if sample is not None:self.timing.end(recv_stage,sample,{'result':'timeout'},end_ns=recv_end)
            if self.timing.mode=='full':self._last_recv_return_ns=recv_end
            self.check_deadline()
            if self.ack_started is not None and time.perf_counter()-self.ack_started>=self.ack_delay:
                self.output_acks()
                return None
            if ack_wakeup:return None
            raise
        except BaseException as exc:
            recv_end=time.perf_counter_ns() if sample is not None else None
            if sample is not None:self.timing.end(recv_stage,sample,{'result':'error','error_type':type(exc).__name__},end_ns=recv_end)
            if self.timing.mode=='full':self._last_recv_return_ns=recv_end
            raise
        else:
            # Legacy recvfrom needs its raw journal timestamp on every packet;
            # nonblocking RX already captured that timestamp before buffering.
            recv_end=time.perf_counter_ns() if sample is not None or getattr(self,'io',None) is None else None
            if sample is not None:self.timing.end(recv_stage,sample,{'result':'packet','raw_bytes':len(raw)},end_ns=recv_end)
            if self.timing.mode=='full':self._last_recv_return_ns=recv_end
        if getattr(self,'io',None) is None:self._capture_rx(raw,source,recv_end)
        sample=self.timing.begin('decode_header_payload_crc')
        try:version,p=decode_any(raw)
        except (ValueError,InvalidPacket):
            if sample is not None:self.timing.end('decode_header_payload_crc',sample,{'raw_bytes':len(raw),'result':'invalid'})
            self.timing.increment('rx_decode_rejected');self.ignored+=1;return None
        if sample is not None:self.timing.end('decode_header_payload_crc',sample,{'raw_bytes':len(raw),'result':'decoded'})
        if source!=self.peer or p.session!=self.session or p.reserved:
            self.timing.increment('rx_identity_rejected');self.ignored+=1;return None
        if version==2 and p.type==0x17:
            if self.receiver is None or p.frame_id!=self.receiver.frame:
                self.timing.increment('rx_output_wrong_frame');self.ignored+=1;return None
            duplicates_before=self.receiver.duplicates
            sample=self.timing.begin('output_receiver_validate_store_deduplicate')
            accepted=self.receiver.receive_packet(p,source,int.from_bytes(raw[56:60],'big'))
            if sample is not None:self.timing.end('output_receiver_validate_store_deduplicate',sample,{'result':'accepted' if accepted else 'rejected'})
            if not accepted:
                self.timing.increment('rx_output_rejected');self.ignored+=1;return None
            duplicate=self.receiver.duplicates>duplicates_before
            self.timing.increment('rx_output_accepted')
            if duplicate:self.timing.increment('rx_output_duplicates')
            if self.receiver.ack_pending and self.ack_started is None:self.ack_started=time.perf_counter()
            if not self.receiver.ack_pending:self.ack_started=None
            if len(self.receiver.ack_pending)>=self.ack_batch or (p.flags&1 and not duplicate):self.output_acks()
            return None
        self.timing.increment('rx_control_delivered')
        return version,p
    @staticmethod
    def matching(p,r):
        return (r.type==p.type|0x80 and r.frame_id==p.frame_id and r.sequence==p.sequence and
            r.offset==p.offset and r.frame_bytes==p.frame_bytes and r.frame_crc==p.frame_crc and
            not r.payload and not r.flags and not r.reserved)
    def exchange(self,p,accepted,version=1,progress=None):
        raw=p.encode() if version==1 else encode2(p)
        for attempt in range(self.attempts):
            self.check_deadline();self.send(raw);self.retries+=attempt!=0
            until=time.perf_counter()+self.timeout
            while time.perf_counter()<until:
                try:item=self.inbox.popleft() if self.inbox else self.receive(until)
                except socket.timeout:self.output_acks();break
                if item is None:continue
                v,r=item
                if v!=version or not self.matching(p,r):self.ignored+=1;continue
                if r.status not in accepted:raise RuntimeError(f'control rejection {r.status}')
                if progress is not None and r.next_offset!=progress:raise RuntimeError('control progress mismatch')
                return r
        raise TimeoutError(f'no control response {p.type}')
    def hello(self):
        self.exchange(Packet(1,self.session,frame_bytes=self.input_bytes),{0},progress=0)
        cap=struct.pack('!HHB3x',1024,self.ow,0x17)
        p=Packet(1,self.session,frame_bytes=self.output_bytes,payload=cap);raw=encode2(p)
        for attempt in range(self.attempts):
            self.send(raw);self.retries+=attempt!=0
            try:
                until=time.perf_counter()+self.timeout
                while time.perf_counter()<until:
                    item=self.receive(until)
                    if item is None:continue
                    version,r=item
                    if version==2 and r.type==0x81 and r.session==self.session and r.frame_id==0 and r.sequence==0 and r.offset==0 and r.frame_bytes==self.output_bytes and r.frame_crc==0 and r.status==0 and r.next_offset==0 and not r.flags and not r.reserved and r.payload==cap:
                        self.negotiated=True;return
                    self.ignored+=1
            except socket.timeout:pass
        raise TimeoutError('explicit EVF2 negotiation failed; no BEGIN/core start sent')
    def input_packets(self,pixels,frame,crc):
        total=(len(pixels)+1023)//1024;base=next_q=0;retained={};tries={};retry_at=None
        while base<total:
            self.check_deadline()
            while next_q<total and next_q<base+self.iw:
                at=next_q*1024;p=Packet(3,self.session,frame,next_q,at,len(pixels),crc,pixels[at:at+1024])
                retained[next_q]=p;tries[next_q]=1;self.send(p.encode());next_q+=1
            self.max_retained=max(self.max_retained,len(retained));assert len(retained)<=self.iw
            if retry_at is None:retry_at=time.perf_counter()+self.timeout
            try:item=self.receive(retry_at)
            except socket.timeout:
                for q,p in retained.items():
                    if tries[q]>=self.attempts:raise TimeoutError('bounded input retries exhausted')
                    tries[q]+=1;self.retries+=1;self.send(p.encode())
                retry_at=time.perf_counter()+self.timeout
                continue
            if item is None:continue
            version,r=item;p=retained.get(r.sequence)
            if version!=1 or p is None or not self.matching(p,r):self.ignored+=1;continue
            if r.status in (18,20):continue # CRC/offset holes await ordered retry.
            if r.status!=1:raise RuntimeError(f'input rejected {r.status}')
            if r.next_offset!=p.offset+len(p.payload):
                raise RuntimeError('input ACK forged progress')
            # EVF1 input accepts ONLY contiguous offsets. A correctly matched
            # DATA ACK therefore confirms earlier bytes too. Its progress must
            # equal this exact request's end; an arbitrary large hint is invalid.
            # COMMIT still checks the independently declared whole input CRC.
            for q in list(retained):
                if q<=r.sequence:del retained[q]
            base=max(base,r.sequence+1)
            retry_at=time.perf_counter()+self.timeout
    def transfer(self,pixels,golden,frame,on_frame=None):
        began=time.perf_counter_ns();thread_cpu_began=time.thread_time_ns()
        packets_began=self.received
        proof_datagrams_began=self.timing.counters.get('proof_ack_datagrams',0)
        proof_entries_began=self.timing.counters.get('proof_ack_entries',0)
        if isinstance(golden,PreparedGolden):golden_hash=golden.sha256;golden=golden.data
        else:golden_hash=hashlib.sha256(golden).hexdigest()
        if not self.negotiated:raise RuntimeError('explicit output negotiation required')
        if len(pixels)!=self.input_bytes or len(golden)!=self.output_bytes:raise ValueError('frozen byte geometry')
        self.deadline=time.perf_counter()+self.frame_timeout;crc=zlib.crc32(pixels)
        self.exchange(Packet(2,self.session,frame,frame_bytes=len(pixels),frame_crc=crc),{1},progress=0)
        self.input_packets(pixels,frame,crc);sent=time.perf_counter_ns()
        self.receiver=OutputReceiver(len(golden),self.session,frame,self.ow,self.peer)
        self.golden=golden
        self.exchange(Packet(4,self.session,frame,(len(pixels)+1023)//1024,len(pixels),len(pixels),crc),{2},progress=len(pixels))
        committed=time.perf_counter_ns()
        while not self.receiver.complete:
            try:item=self.receive()
            except socket.timeout:self.output_acks();continue
            if item is not None:self.ignored+=1
            if self.receiver.contiguous==self.receiver.total and self.receiver.declared_crc is not None and self.receiver.rolling_crc!=self.receiver.declared_crc:
                raise RuntimeError('whole output CRC mismatch; final ACK withheld')
        self.output_acks();actual=self.receiver.commit()
        if actual!=golden:raise RuntimeError('Golden mismatch; final ACK withheld')
        verified=time.perf_counter_ns()
        # Caller receives immutable, fully validated bytes; it can submit to the
        # bounded PC4K queue. Failure propagates before the board frame release.
        if on_frame is not None:on_frame(actual,{'session':self.session.hex(),'frame_id':frame,'received_perf_counter_ns':verified,
            'golden_match':True,'integrity_sha256':golden_hash,'verified_crc32':self.receiver.declared_crc})
        self.journal.checkpoint()
        final=Packet(9,self.session,frame,(len(actual)+1023)//1024,len(actual),len(actual),self.receiver.declared_crc)
        while self.exchange(final,{4,24},version=2,progress=len(actual)).status==24:
            self.check_deadline()
            # A final-window proof ACK may itself have been lost. Re-prove the
            # last bounded window, including already-ACKed slots; do not depend
            # on the final control reply to advance the data window.
            total=(len(actual)+1023)//1024
            body=b''.join(struct.pack('!II',q,zlib.crc32(actual[q*1024:(q+1)*1024]))
                for q in range(max(0,total-self.ow),total))
            self.send(encode2(Packet(0x97,self.session,frame,frame_bytes=len(actual),payload=body,status=1,next_offset=len(actual))))
        # FRAME_DONE closes the output window. Any late duplicate data and its
        # deferred proofs belong to the completed frame and must not wake the
        # next frame's BEGIN exchange as an already-expired ACK timer.
        self.ack_started=None
        done=time.perf_counter_ns();self.deadline=None
        row={'frame':frame,'input_bytes':len(pixels),'output_bytes':len(actual),'Golden_match':True,
            'timing_ns':{'input':sent-began,'commit':committed-sent,'output_until_verified':verified-committed,'release':done-verified,'whole':done-began},
            'thread_cpu_ns':time.thread_time_ns()-thread_cpu_began,
            'output_unique_chunks':self.receiver.total,'output_duplicate_packets':self.receiver.duplicates,
            'output_rejected_packets':self.receiver.rejected,'received_datagrams_during_frame':self.received-packets_began,
            'proof_ack_datagrams':self.timing.counters.get('proof_ack_datagrams',0)-proof_datagrams_began,
            'proof_ack_entries':self.timing.counters.get('proof_ack_entries',0)-proof_entries_began,
            'scope':'CALLER_TRANSPORT_WALL_TIME_AND_CALLING_THREAD_CPU_NOT_WIRE_TIME_OR_DISPLAY','max_input_retained':self.max_retained}
        self.timing.record('frame_transfer',done-began,row['thread_cpu_ns'],
                           {'frame':frame,'unique_output_chunks':self.receiver.total,
                            'duplicate_output_packets':self.receiver.duplicates})
        self.timing.increment('completed_frames')
        self.frames.append(row)
        if self.frame_event_file is None:(self.out/'FRAMES.json').write_text(json.dumps(self.frames,indent=2),encoding='utf-8')
        else:
            self.frame_event_file.write(json.dumps(row)+'\n');self.frame_event_file.flush()
        self.receiver=None;self.golden=None;return actual
    def _save_timing(self,status):
        if self._timing_saved:return
        path=self.out/'TIMING_DIAGNOSTICS.json'
        report=self.timing.snapshot('LIVE_STREAMING_CLIENT_CALL_BOUNDARIES_NOT_NIC_OR_WIRE_TIMESTAMPS',
            status=status,io_mode=self.io_mode,timing_mode=self.timing.mode,
            sampled_disabled_stages=['receive_service_interval'] if self.timing.mode=='sampled' else [],
            received_datagrams=self.received,ignored_protocol_items=self.ignored,network_retries=self.retries,
            rx_prefetched_unprocessed=len(self.io.ready) if self.io is not None else 0,
            active_output_unique_chunks=sum(self.receiver.coverage) if self.receiver is not None else None,
            active_output_rejected_packets=self.receiver.rejected if self.receiver is not None else None,
            active_output_duplicate_packets=self.receiver.duplicates if self.receiver is not None else None,

            max_rx_buffer=self.io.max_rx_buffer if self.io is not None else 0,
            max_pending_tx=self.io.max_pending_tx if self.io is not None else 0,
            receive_batch_packets=self.io.batch_packets if self.io is not None else 1,
            receive_batch_budget_ns=self.io.batch_budget_ns if self.io is not None else None,
            tx_journal_scope="BEFORE_FIRST_SEND_ATTEMPT_NOT_WIRE_COMPLETION",
            rx_journal_scope="RECVFROM_RETURN_BEFORE_BUFFERING_AND_VALIDATION",session_sha256=hashlib.sha256(self.session).hexdigest(),
            output_window=self.ow,ack_batch=self.ack_batch,ack_delay_seconds=self.ack_delay,
            raw_journal_records=self.journal.records,raw_journal_record_bytes=self.journal.bytes)
        with path.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
        self._timing_saved=True
    def finish(self):
        try:
            if self.frame_event_file is not None:
                self.frame_event_file.close()
                (self.out/'FRAMES.json').write_text(json.dumps(self.frames,indent=2),encoding='utf-8')
            result=self.journal.finalize();self._save_timing('FINALIZED_CAPTURE')
            return result
        except BaseException:
            try:self.journal.abort()
            except BaseException:pass
            self._save_timing('FAILED_FINISH_PRESERVE_CAPTURE')
            raise
    def abort(self):
        if self.frame_event_file is not None:self.frame_event_file.close()
        try:self.journal.abort()
        finally:self._save_timing('ABORTED_CAPTURE_PREFIX')
