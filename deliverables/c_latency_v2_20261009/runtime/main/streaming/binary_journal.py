"""Bounded binary raw datagram journal, with fail-closed checkpoints."""
from pathlib import Path
import hashlib,ipaddress,json,os,struct,time
HEADER=struct.Struct('!QIB4sH')
MAGIC=b'EVFJ\x02\x00\x00\x00'
def file_sha256(path):
    # Sustained raw captures can exceed RAM; hash without loading the capture.
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
class BinaryJournal:
    def __init__(self,out,threshold=524288,timing=None):
        if not 1088<=threshold<=4194304:raise ValueError('bounded journal block')
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.file=(self.out/'datagrams.bin').open('xb',buffering=1048576);self.file.write(MAGIC)
        self.threshold=threshold;self.buffer=bytearray();self.failed=None;self.closed=False
        self.records=self.bytes=self.max_buffer=0
        self.timing=timing
        self.address_cache={}
    def check(self):
        if self.failed is not None:raise RuntimeError('journal poisoned; final ACK forbidden') from self.failed
        if self.closed:raise RuntimeError('journal closed')
    def append(self,direction,raw,source,stamp=None):
        sample=self.timing.begin('journal_append') if self.timing is not None else None
        self.check()
        try:
            if direction not in (0,1) or not 0<len(raw)<=65535 or not 1<=source[1]<=65535:raise ValueError('journal record')
            address=self.address_cache.get(source)
            if address is None:
                address=ipaddress.IPv4Address(source[0]).packed
                if len(self.address_cache)<16:self.address_cache[source]=address
            record=HEADER.pack(time.perf_counter_ns() if stamp is None else stamp,len(raw),direction,address,source[1])+raw
            if self.buffer and len(self.buffer)+len(record)>self.threshold:self.flush_block()
            self.buffer.extend(record);self.records+=1;self.bytes+=len(record)
            self.max_buffer=max(self.max_buffer,len(self.buffer))
            if len(self.buffer)>=self.threshold:self.flush_block()
        except Exception as e:self.failed=e;raise
        finally:
            if sample is not None:self.timing.end('journal_append',sample,{'direction':direction,'raw_bytes':len(raw)})
    def flush_block(self):
        sample=self.timing.begin('journal_flush_block',always=True) if self.timing is not None else None
        pending_bytes=len(self.buffer)
        self.check()
        try:
            if self.buffer:
                write_sample=self.timing.begin('journal_file_write',always=True) if self.timing is not None else None
                write_bytes=len(self.buffer)
                try:
                    if self.file.write(self.buffer)!=write_bytes:raise OSError('short journal write')
                finally:
                    if write_sample is not None:self.timing.end('journal_file_write',write_sample,{'bytes':write_bytes})
                self.buffer.clear()
        except Exception as e:self.failed=e;raise
        finally:
            if sample is not None:self.timing.end('journal_flush_block',sample,{'buffer_bytes':pending_bytes})
    def checkpoint(self,durable=False):
        sample=self.timing.begin('journal_checkpoint',always=True) if self.timing is not None else None
        self.check()
        try:
            self.flush_block();self.file.flush()
            if durable:os.fsync(self.file.fileno())
        except Exception as e:self.failed=e;raise
        finally:
            if sample is not None:self.timing.end('journal_checkpoint',sample,{'durable':bool(durable)})
    def finalize(self):
        self.checkpoint(True);self.file.close();self.closed=True
        p=self.out/'datagrams.bin';result={'format':'EVFJ_V2','status':'CAPTURE_ONLY_PENDING_PROTOCOL_AUDIT',
            'header_struct':HEADER.format,'records':self.records,'bytes':p.stat().st_size,
            'sha256':file_sha256(p),'max_buffer_bytes':self.max_buffer,
            'threshold_bytes':self.threshold,'socket_created':False}
        (self.out/'JOURNAL.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
    def abort(self):
        if self.closed:return
        errors=[];tail=None
        # Preserve valid buffered records on a transfer/queue error. A poisoned
        # or externally closed writer must not authorize a normal JOURNAL.
        if self.failed is None and not self.file.closed:
            try:self.checkpoint()
            except BaseException as exc:errors.append(repr(exc))
        if self.buffer:
            try:
                p=self.out/'datagrams_tail_uncommitted.bin'
                with p.open('xb')as f:f.write(MAGIC);f.write(self.buffer)
                tail=dict(file=p.name,bytes=p.stat().st_size,sha256=file_sha256(p),
                          scope='UNCOMMITTED_RAW_TAIL_MAY_OVERLAP_PARTIAL_FAILED_PREFIX_WRITE')
            except BaseException as exc:errors.append(repr(exc))
        try:self.file.close()
        except BaseException as exc:errors.append(repr(exc))
        finally:self.closed=True
        try:
            p=self.out/'datagrams.bin'
            result=dict(status='ABORTED_CAPTURE_NOT_COMPLETE_OR_PROTOCOL_PASS',prefix_file=p.name,prefix_bytes=p.stat().st_size,
                        prefix_sha256_pending_independent_pack=True,in_memory_record_count=self.records,
                        uncommitted_tail=tail,writer_error=repr(self.failed)if self.failed else None,preservation_errors=errors)
            with (self.out/'ABORTED_CAPTURE.json').open('x',encoding='utf-8')as f:json.dump(result,f,indent=2)
        except BaseException as exc:errors.append(repr(exc))
        self.abort_preservation_errors=errors
def records(path):
    p=Path(path);manifest=json.loads((p.parent/'JOURNAL.json').read_text(encoding='utf-8'))
    assert p.stat().st_size==manifest['bytes'] and file_sha256(p)==manifest['sha256']
    with p.open('rb') as f:
        assert f.read(len(MAGIC))==MAGIC;n=0
        while h:=f.read(HEADER.size):
            if len(h)!=HEADER.size:raise ValueError('truncated journal header')
            stamp,length,direction,ip,port=HEADER.unpack(h)
            if not 0<length<=65535 or direction not in (0,1):raise ValueError('journal geometry')
            raw=f.read(length)
            if len(raw)!=length:raise ValueError('truncated journal payload')
            n+=1;yield stamp,direction,raw,(str(ipaddress.IPv4Address(ip)),port)
        assert n==manifest['records']
