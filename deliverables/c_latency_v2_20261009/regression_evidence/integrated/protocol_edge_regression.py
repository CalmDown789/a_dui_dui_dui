"""Bounded no-socket protocol edge checks against the current candidate."""
from pathlib import Path
import hashlib, json, socket, sys, time, zlib

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'main'
sys.path.insert(0, str(MAIN / 'streaming'))
sys.path.insert(0, str(MAIN / 'host'))
from streaming_client import StreamingClient
from stream_receiver import OutputReceiver
from timing_diagnostics import BoundedTiming
from video_protocol import FrameReceiver, Packet, decode

PEER = ('127.0.0.1', 6102)
SESSION = bytes(range(16))
FRAME = 9
DATA = bytes((i * 29 + 7) & 0xff for i in range(130 * 1024))
WHOLE_CRC = zlib.crc32(DATA)

def packet(q, payload=None):
    at = q * 1024
    part = DATA[at:at + 1024] if payload is None else payload
    last = q == 129
    return Packet(0x17, SESSION, FRAME, q, at, len(DATA),
                  WHOLE_CRC if last else 0, part, status=1, flags=int(last))

receiver = OutputReceiver(len(DATA), SESSION, FRAME, 128, PEER)
assert receiver.receive_packet(packet(128), PEER, zlib.crc32(DATA[128*1024:129*1024])) is False
assert receiver.receive_packet(packet(129), PEER, zlib.crc32(DATA[129*1024:])) is False
assert receiver.receive_packet(packet(127), PEER, zlib.crc32(DATA[127*1024:128*1024])) is True
assert receiver.receive_packet(packet(0), PEER, zlib.crc32(DATA[:1024])) is True
assert receiver.contiguous == 1
assert receiver.receive_packet(packet(128), PEER, zlib.crc32(DATA[128*1024:129*1024])) is True
assert receiver.retired_proofs_pruned == 1
assert 0 not in receiver.ack_pending
assert receiver.receive_packet(packet(0), PEER, zlib.crc32(DATA[:1024])) is True
assert receiver.duplicates == 1
changed = bytearray(DATA[127*1024:128*1024]); changed[0] ^= 1
assert receiver.receive_packet(packet(127, bytes(changed)), PEER,
                               zlib.crc32(changed)) is False
for q in range(1, 127):
    assert receiver.receive_packet(packet(q), PEER,
                                   zlib.crc32(DATA[q*1024:(q+1)*1024])) is True
assert receiver.contiguous == 129
assert receiver.receive_packet(packet(129), PEER,
                               zlib.crc32(DATA[129*1024:])) is True
assert receiver.complete and receiver.commit() == DATA

input_receiver = FrameReceiver(1024)
assert decode(input_receiver.process(Packet(1, SESSION, frame_bytes=1024).encode())).status == 0
one_chunk = bytes(range(256)) * 4
early_data = Packet(3, SESSION, 0, 0, 0, 1024, zlib.crc32(one_chunk), one_chunk)
assert decode(input_receiver.process(early_data.encode())).status == 24

class TimeoutTransport:
    def __init__(self):
        self.waits = []
        self.calls = 0
    def settimeout(self, value):
        self.waits.append(value)
    def recvfrom(self, _):
        self.calls += 1
        raise socket.timeout('injected timeout')

def client_with_timeout(ack_started, ack_delay, timeout, receiver):
    client = StreamingClient.__new__(StreamingClient)
    client.timeout = timeout
    client.deadline = None
    client.ack_started = ack_started
    client.ack_delay = ack_delay
    client.receiver = receiver
    client.transport = TimeoutTransport()
    client.timing = BoundedTiming()
    client._last_recv_return_ns = None
    return client

pending = type('Pending', (), {'ack_pending': {0: 123}})()
early_client = client_with_timeout(time.perf_counter(), 0.5, 1.0, pending)
assert early_client.receive() is None
assert early_client.transport.waits[0] > 0
assert early_client.ack_started is not None and pending.ack_pending == {0: 123}

stale_client = client_with_timeout(time.perf_counter() - 1.0, 0.01, 0.02, None)
try:
    stale_client.receive()
except socket.timeout:
    pass
else:
    raise AssertionError('stale cross-frame timer must still wait for socket timeout')
assert stale_client.ack_started is None
assert stale_client.transport.calls == 1
assert stale_client.transport.waits[0] >= 0.019

report = {
    'status': 'PASS',
    'scope': 'NO_SOCKET_OUTPUT_RECEIVER_WINDOW_TIMER_AND_INPUT_NOT_READY_EDGE_CHECKS',
    'checks': {
        'window_128_upper_boundary_and_retired_proofs': True,
        'byte_changed_duplicate_rejected': True,
        'completed_output_commit': True,
        'input_before_begin_returns_not_ready_24': True,
        'early_ack_timer_wait_does_not_retry_or_flush': True,
        'stale_cross_frame_timer_clears_then_waits': True,
    },
    'source_sha256': {
        name: hashlib.sha256((MAIN / folder / name).read_bytes()).hexdigest()
        for folder, names in (
            ('streaming', ('streaming_client.py', 'stream_receiver.py', 'timing_diagnostics.py')),
            ('host', ('video_protocol.py',)),
        )
        for name in names
    },
}
out = ROOT / 'validation' / 'protocol_edge_regression.json'
out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
