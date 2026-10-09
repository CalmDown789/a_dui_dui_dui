"""Socket-free readiness adapter for the existing independent peer fixture."""
import errno
import os
import socket
import time
from streaming_client import StreamingClient as Client

MODE = os.environ.get('STEP03_IO_MODE', 'nonblocking')
TIMING_MODE = os.environ.get('STEP04_TIMING_MODE', 'full')


class NonblockingPeer:
    def __init__(self, peer):
        self.peer = peer
        self.setblocking_calls = self.recv_calls = self.send_calls = self.wait_calls = 0
        self.retry_after = time.perf_counter() + .002

    def retry_due(self):
        active = (self.peer.sender is not None and not self.peer.sender.complete and
                  self.peer.fault != 'no_output')
        if not self.peer.queue and active and time.perf_counter() >= self.retry_after:
            self.peer.queue.extend((raw, self.peer.address) for raw in self.peer.sender.retry())
            self.peer.max_queue = max(self.peer.max_queue, len(self.peer.queue))
            self.retry_after = time.perf_counter() + .002
        return active

    def setblocking(self, enabled):
        assert enabled is False
        self.setblocking_calls += 1
        assert self.setblocking_calls == 1

    def settimeout(self, _):
        raise AssertionError('nonblocking path must never settimeout')

    def sendto(self, raw, address):
        self.send_calls += 1
        return self.peer.sendto(raw, address)

    def recvfrom(self, maximum):
        self.recv_calls += 1
        # Eager buffering may exhaust the peer queue before buffered proofs
        # reach it. Queue exhaustion alone is not a retransmission timer.
        self.retry_due()
        if not self.peer.queue:
            raise BlockingIOError(errno.EWOULDBLOCK, 'in-memory would-block')
        try:
            value = self.peer.recvfrom(maximum)
            self.retry_after = time.perf_counter() + .002
            return value
        except socket.timeout as exc:
            raise BlockingIOError(errno.EWOULDBLOCK, 'in-memory would-block') from exc

    def wait_ready(self, read, write, timeout):
        assert timeout > 0 and (read or write)
        self.wait_calls += 1
        if write:
            return bool(read and self.peer.queue), True
        if read and self.peer.queue:
            return True, False
        active = self.retry_due()
        wait = min(timeout, .001)
        if read and active:wait = min(wait,max(0,self.retry_after-time.perf_counter()))
        if wait > 0:time.sleep(wait)
        self.retry_due()
        return bool(read and self.peer.queue), False


def tested_client(peer, *args, **kwargs):
    if MODE == 'nonblocking':
        transport = NonblockingPeer(peer)
        kwargs.update(io_mode='nonblocking', readiness_waiter=transport.wait_ready)
    elif MODE == 'timeout':
        transport = peer
        kwargs.update(io_mode='timeout')
    else:
        raise ValueError('explicit fixture IO mode')
    kwargs.setdefault('timing_mode',TIMING_MODE)
    return Client(transport, *args, **kwargs)
