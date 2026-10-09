"""EVF2 output receiver for already CRC-validated decoded packets.

Only one wire decoder runs per packet. Semantic checks and bounded proof queues
remain independent of that decoder. Data is immutable only after commit().
"""
import struct,zlib
class OutputReceiver:
    def __init__(self,size,session,frame,window,peer):
        if not 0<size<=2073600 or not 1<=window<=128:raise ValueError('bounded output geometry')
        self.size,self.session,self.frame,self.window,self.peer=size,session,frame,window,peer
        self.memory=bytearray(size);self.view=memoryview(self.memory);self.total=(size+1023)//1024
        self.coverage=bytearray(self.total);self.contiguous=0;self.pending=set();self.ack_pending={}
        self.rolling_crc=0;self.declared_crc=None;self.written_bytes=self.duplicates=self.rejected=self.max_pending=0
        self.highest_seen=-1;self.retired_proofs_pruned=0
    def receive_packet(self,p,source,payload_crc):
        q=p.sequence;at=q*1024
        if source!=self.peer or p.type!=0x17 or p.session!=self.session or p.frame_id!=self.frame or p.frame_bytes!=self.size:
            self.rejected+=1;return False
        if q>=self.total or p.offset!=at or len(p.payload)!=min(1024,self.size-at) or p.flags!=int(q==self.total-1) or p.status!=1 or p.reserved or p.next_offset:
            self.rejected+=1;return False
        if q!=self.total-1 and p.frame_crc!=0:
            self.rejected+=1;return False
        if q==self.total-1 and self.declared_crc is not None and p.frame_crc!=self.declared_crc:
            self.rejected+=1;return False
        if self.coverage[q]:
            if self.view[at:at+len(p.payload)]!=p.payload:self.rejected+=1;return False
        else:
            if not self.contiguous<=q<self.contiguous+self.window:self.rejected+=1;return False
        # A CRC/identity/byte-validated q proves board_base >= q-window+1
        # for the negotiated bounded sender (CRC is not authentication):
        # a bounded sender cannot emit q while retaining an older slot outside
        # that range. Those old proofs are already applied, even if duplicate
        # datagrams remain queued on the host; do not mix them into a new batch.
        highest=max(self.highest_seen,q);retired_before=max(0,highest-self.window+1)
        for old in tuple(self.ack_pending):
            if old<retired_before:del self.ack_pending[old];self.retired_proofs_pruned+=1
        if q>=retired_before and q not in self.ack_pending and len(self.ack_pending)>=self.window:
            self.rejected+=1;return False
        self.highest_seen=highest
        if self.coverage[q]:self.duplicates+=1
        else:
            self.view[at:at+len(p.payload)]=p.payload;self.coverage[q]=1;self.pending.add(q)
            self.written_bytes+=len(p.payload);self.max_pending=max(self.max_pending,len(self.pending))
            while self.contiguous in self.pending:
                pos=self.contiguous*1024
                self.rolling_crc=zlib.crc32(self.view[pos:pos+min(1024,self.size-pos)],self.rolling_crc)
                self.pending.remove(self.contiguous);self.contiguous+=1
        if q>=retired_before:self.ack_pending[q]=payload_crc
        if q==self.total-1:self.declared_crc=p.frame_crc
        return True
    @property
    def complete(self):return self.contiguous==self.total and not self.pending and self.declared_crc is not None and self.rolling_crc==self.declared_crc
    def commit(self):
        if not self.complete or self.written_bytes!=self.size:raise RuntimeError('incomplete/CRC output; no release')
        return bytes(self.memory)
    def take_proofs(self):
        body=b''.join(struct.pack('!II',q,crc) for q,crc in sorted(self.ack_pending.items()));self.ack_pending.clear();return body
