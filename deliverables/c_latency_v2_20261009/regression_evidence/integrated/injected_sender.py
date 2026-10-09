"""Bounded synthetic peer for host tests only; does not model RTL timing."""
import struct
import zlib
from streaming_client import encode2, decode_any
from video_protocol import Packet, InvalidPacket


class Sender:
    def __init__(self, data, session, frame, window, address, negotiated=False, output=False):
        assert negotiated and output
        self.data, self.session, self.frame = data, session, frame
        self.window, self.address = window, address
        self.crc = zlib.crc32(data)
        self.total = (len(data) + 1023) // 1024
        self.base = self.next_q = 0
        self.acked = set()
        self.complete = False

    def packet(self, q):
        at = q * 1024
        last = q == self.total - 1
        return encode2(Packet(0x17, self.session, self.frame, q, at,
                              len(self.data), self.crc if last else 0,
                              self.data[at:at+1024], status=1, flags=int(last)))

    def burst(self):
        # An ACK admits new packets. It does not retransmit packets already
        # queued in the transport; explicit retry() handles missing proofs.
        end = min(self.total, self.base + self.window)
        out = [self.packet(q) for q in range(self.next_q, end)]
        self.next_q = end
        return out

    def retry(self):
        return [self.packet(q) for q in range(self.base, self.next_q)
                if q not in self.acked]

    def acknowledge(self, raw, source):
        if source != self.address:
            return False
        try:
            version, p = decode_any(raw)
            proofs = list(struct.iter_unpack('!II', p.payload))
        except (ValueError, InvalidPacket, struct.error):
            return False
        if version != 2 or p.type != 0x97 or p.session != self.session or p.frame_id != self.frame:
            return False
        # Validate the whole batch before changing state, including CRCs for
        # older duplicates. There is no retirement on a partially valid batch.
        if not proofs or any(q >= self.next_q or
                             zlib.crc32(self.data[q*1024:(q+1)*1024]) != crc
                             for q, crc in proofs):
            return False
        self.acked.update(q for q, _ in proofs if q >= self.base)
        while self.base in self.acked:
            self.acked.remove(self.base)
            self.base += 1
        self.complete = self.base == self.total
        return True
