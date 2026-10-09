"""EVF1 v1 codec and input-frame reference model; not an FPGA replacement.

The envelope assumes an upstream validated IPv4/UDP datagram. Runtime physical
acceptance still requires the new FPGA image, frozen FSRCNN and actual result.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import IntEnum
import struct
import zlib

INPUT_BYTES = 960 * 540
OUTPUT_BYTES = 1920 * 1080
CHUNK_BYTES = 1024
HEADER = struct.Struct('!4sBBH16sIIIIIHHIIII')
assert HEADER.size == 64


class Type(IntEnum):
    HELLO = 1
    BEGIN = 2
    DATA = 3
    COMMIT = 4
    STATUS = 5
    ABORT = 6
    READ_RESULT = 7
    ACK_RESULT = 8
    ACK_FRAME = 9


class Status(IntEnum):
    OK = 0
    ACK = 1
    STARTED = 2
    PROCESSING = 3
    FRAME_DONE = 4
    BUSY = 5
    SESSION = 16
    FRAME_ID = 17
    PAYLOAD_CRC = 18
    LENGTH = 19
    OFFSET = 20
    FRAME_CRC = 21
    FLAGS = 22
    TYPE = 23
    NOT_READY = 24


class State(IntEnum):
    NO_SESSION = 0
    IDLE = 1
    RECEIVING = 2
    RUNNING = 3
    FAILED = 4


@dataclass(frozen=True)
class Packet:
    type: int
    session: bytes
    frame_id: int = 0
    sequence: int = 0
    offset: int = 0
    frame_bytes: int = INPUT_BYTES
    frame_crc: int = 0
    payload: bytes = b''
    status: int = 0
    next_offset: int = 0
    flags: int = 0
    reserved: int = 0

    def encode(self) -> bytes:
        if len(self.session) != 16 or len(self.payload) > CHUNK_BYTES:
            raise ValueError('EVF1 session must be 16 bytes; payload <=1024 bytes')
        head = HEADER.pack(b'EVF1', 1, self.type, self.flags, self.session,
                           self.frame_id, self.sequence, self.offset, self.frame_bytes, self.frame_crc,
                           len(self.payload), self.status, self.next_offset, self.reserved,
                           zlib.crc32(self.payload), 0)
        return head[:60] + struct.pack('!I', zlib.crc32(head[:60])) + self.payload


class InvalidPacket(ValueError):
    def __init__(self, reason, packet=None):
        super().__init__(reason)
        self.reason, self.packet = reason, packet


def decode(raw: bytes) -> Packet:
    if len(raw) < 64 or len(raw) > 64 + CHUNK_BYTES:
        raise InvalidPacket('LENGTH')
    fields = HEADER.unpack(raw[:64])
    magic, version, kind, flags, session, frame_id, sequence, offset, frame_bytes, frame_crc, count, status, next_offset, reserved, payload_crc, header_crc = fields
    if magic != b'EVF1' or version != 1 or zlib.crc32(raw[:60]) != header_crc:
        raise InvalidPacket('HEADER')
    packet = Packet(kind, session, frame_id, sequence, offset, frame_bytes, frame_crc,
                    raw[64:], status, next_offset, flags, reserved)
    if count != len(raw) - 64:
        raise InvalidPacket('LENGTH', packet)
    if zlib.crc32(packet.payload) != payload_crc:
        raise InvalidPacket('PAYLOAD_CRC', packet)
    return packet


class FrameReceiver:
    """Serial input-only behavioral reference. release() models full result ACK.

    It does not calculate SR or send an output image. Memory writes occur only
    after both CRCs/length/session/offset checks; processing owns the whole input.
    """
    def __init__(self, frame_bytes=INPUT_BYTES, chunk_bytes=CHUNK_BYTES):
        self.frame_bytes, self.chunk_bytes = frame_bytes, chunk_bytes
        self.memory = bytearray(frame_bytes)
        self.state = State.NO_SESSION
        self.session = None
        self.expected_id = 0
        self.declared_crc = self.rolling_crc = 0
        self.offset = self.sequence = 0
        self.last_packet = None
        self.last_done = None
        self.start_count = self.write_bytes = self.rejected = self.timeout_count = 0

    def response(self, request, status):
        return replace(request, type=request.type | 0x80, payload=b'', status=int(status),
                       frame_bytes=self.frame_bytes, next_offset=self.offset,
                       flags=0, reserved=0).encode()

    def timeout_receiving(self):
        if self.state in (State.RECEIVING, State.FAILED):
            self.state, self.session = State.NO_SESSION, None
            self.offset = self.sequence = 0
            self.last_packet = None
            self.last_done = None
            self.timeout_count += 1

    def release(self):
        if self.state != State.RUNNING:
            raise ValueError('release only after a started frame and complete output acknowledgement')
        self.last_done = (self.expected_id, self.declared_crc)
        self.expected_id = (self.expected_id + 1) & 0xffffffff
        self.state = State.IDLE

    def process(self, raw):
        try:
            h = decode(raw)
        except InvalidPacket as exc:
            self.rejected += 1
            if exc.packet is None:
                return None  # Header identity is not trusted: discard, sender timeout/retry.
            return self.response(exc.packet, Status.PAYLOAD_CRC if exc.reason == 'PAYLOAD_CRC' else Status.LENGTH)
        def fail(status):
            self.rejected += 1
            return self.response(h, status)
        if h.flags or h.reserved or h.status or h.next_offset:
            return fail(Status.FLAGS)
        if h.type not in {int(t) for t in Type}:
            return fail(Status.TYPE)
        if h.frame_bytes != self.frame_bytes:
            return fail(Status.LENGTH)
        if h.type > Type.ABORT:
            return fail(Status.TYPE)  # Output ownership layer is implemented separately.
        if h.type == Type.HELLO:
            if h.payload or h.frame_id or h.sequence or h.offset or h.frame_crc:
                return fail(Status.LENGTH)
            if self.session == h.session:
                return self.response(h, Status.OK)
            if self.state not in (State.NO_SESSION, State.IDLE):
                return fail(Status.BUSY)
            self.session, self.state = h.session, State.IDLE
            self.expected_id = self.offset = self.sequence = 0
            self.declared_crc = self.rolling_crc = 0
            self.last_packet = self.last_done = None
            return self.response(h, Status.OK)
        if self.session != h.session:
            return fail(Status.SESSION)
        if self.last_done and (h.frame_id, h.frame_crc) == self.last_done and h.type in (Type.BEGIN, Type.DATA, Type.COMMIT):
            return self.response(h, Status.FRAME_DONE)
        if h.frame_id != self.expected_id:
            return fail(Status.FRAME_ID)
        if h.type == Type.STATUS:
            if h.payload or h.sequence or h.offset or h.frame_crc:
                return fail(Status.LENGTH)
            status = {State.IDLE: Status.OK, State.RECEIVING: Status.ACK,
                      State.RUNNING: Status.PROCESSING, State.FAILED: Status.FRAME_CRC}[self.state]
            return self.response(h, status)
        if h.type == Type.ABORT:
            if h.payload or h.sequence or h.offset or h.frame_crc:
                return fail(Status.LENGTH)
            if self.state == State.RUNNING:
                return fail(Status.BUSY)
            self.state = State.IDLE
            self.offset = self.sequence = self.rolling_crc = self.declared_crc = 0
            self.last_packet = None
            return self.response(h, Status.OK)
        if h.type == Type.BEGIN:
            if h.payload or h.sequence or h.offset:
                return fail(Status.LENGTH)
            if self.state == State.RUNNING:
                return fail(Status.BUSY)
            if self.state in (State.RECEIVING, State.FAILED):
                return self.response(h, Status.ACK if self.state == State.RECEIVING and self.declared_crc == h.frame_crc else Status.FRAME_CRC)
            self.state, self.declared_crc = State.RECEIVING, h.frame_crc
            self.offset = self.sequence = self.rolling_crc = 0
            self.last_packet = None
            return self.response(h, Status.ACK)
        if self.state == State.RUNNING:
            if h.type == Type.COMMIT and not h.payload and h.frame_crc == self.declared_crc and h.offset == self.frame_bytes and h.sequence == self.sequence:
                return self.response(h, Status.STARTED)  # Lost start ACK is idempotent.
            return fail(Status.BUSY)
        if self.state != State.RECEIVING:
            return fail(Status.FRAME_CRC if self.state == State.FAILED else Status.NOT_READY)
        if h.frame_crc != self.declared_crc:
            return fail(Status.FRAME_CRC)
        if h.type == Type.DATA:
            identity = (h.sequence, h.offset, len(h.payload), zlib.crc32(h.payload))
            if self.last_packet == identity:
                return self.response(h, Status.ACK)
            if h.offset != self.offset or h.sequence != self.sequence:
                return fail(Status.OFFSET)
            if not h.payload or len(h.payload) != min(self.chunk_bytes, self.frame_bytes - self.offset):
                return fail(Status.LENGTH)
            self.memory[self.offset:self.offset + len(h.payload)] = h.payload
            self.write_bytes += len(h.payload)
            self.rolling_crc = zlib.crc32(h.payload, self.rolling_crc)
            self.offset += len(h.payload)
            self.sequence += 1
            self.last_packet = identity
            return self.response(h, Status.ACK)
        if h.type == Type.COMMIT:
            if h.payload or h.offset != self.frame_bytes or h.sequence != self.sequence or self.offset != self.frame_bytes:
                return fail(Status.OFFSET)
            if self.rolling_crc != self.declared_crc:
                self.state = State.FAILED
                return fail(Status.FRAME_CRC)
            self.state = State.RUNNING
            self.start_count += 1
            return self.response(h, Status.STARTED)
        return fail(Status.TYPE)
