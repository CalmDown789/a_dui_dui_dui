"""Bounded single-owner datagram service; accepts an existing transport only.

TX journal time is before the first syscall attempt (not wire completion).
RX journal time is immediately after recvfrom returns, before buffering.
One send stays pending until complete; a stalled send may buffer at most one
bounded receive batch. No sockets, threads, or background writers are created.
"""
from collections import deque
import errno
import select
import socket
import time


class TransportSendDeadlineError(RuntimeError):
    """Local TX stall is fatal, distinct from a lost-response socket.timeout."""


class TransportProgressError(RuntimeError):
    """Repeated false readiness or reentrant use must not cause busy polling."""


def would_block(exc):
    return (isinstance(exc, BlockingIOError) or
            getattr(exc, 'errno', None) in (errno.EAGAIN, errno.EWOULDBLOCK, 10035) or
            getattr(exc, 'winerror', None) == 10035)


class NonblockingDatagramIO:
    def __init__(self, transport, journal, timing, capture_rx, *, waiter=None,
                 batch_packets=32, batch_budget_ns=200_000, clock=None,
                 check_deadline=None):
        if not 1 <= batch_packets <= 128 or not 1 <= batch_budget_ns <= 10_000_000:
            raise ValueError('bounded receive batch')
        self.transport, self.journal, self.timing = transport, journal, timing
        self.capture_rx = capture_rx
        self.batch_packets, self.batch_budget_ns = batch_packets, batch_budget_ns
        self.clock = time.perf_counter if clock is None else clock
        self.check_deadline = check_deadline or (lambda: None)
        self.waiter = self._select if waiter is None else waiter
        self.ready = deque()
        self.pending = None
        self.failed = None
        self.max_rx_buffer = self.max_pending_tx = self.max_batch = 0
        self._false_ready = 0
        transport.setblocking(False)
        timing.increment('io_setblocking_calls')

    def _select(self, read, write, timeout):
        readable, writable, _ = select.select(
            [self.transport] if read else [], [self.transport] if write else [], [], timeout)
        return bool(readable), bool(writable)

    def _check(self):
        if self.failed is not None:
            raise RuntimeError('nonblocking transport poisoned') from self.failed
        self.check_deadline()

    def _wait(self, read, write, until):
        self._check()
        remaining = until - self.clock()
        if remaining <= 0:
            return False, False
        sample = self.timing.begin('readiness_wait', always=True)
        self.timing.increment('io_readiness_wait_calls')
        try:
            result = self.waiter(read, write, remaining)
        finally:
            self.timing.end('readiness_wait',sample,{'read':read,'write':write})
        self._check()
        return result

    def _false_wakeup(self, ready, progress):
        if progress:
            self._false_ready = 0
        elif any(ready):
            self._false_ready += 1
            self.timing.increment('io_false_readiness')
            if self._false_ready >= 8:
                raise TransportProgressError('eight readiness wakeups without transport progress')
        else:
            self._false_ready = 0

    def _drain_rx(self, until):
        self._check()
        began = self.clock()
        count = 0
        try:
            while len(self.ready) < self.batch_packets and count < self.batch_packets:
                self._check()
                now = self.clock()
                if now >= until or (count and (now-began)*1e9 >= self.batch_budget_ns):
                    break
                self.timing.increment('io_recvfrom_attempts')
                try:
                    raw, source = self.transport.recvfrom(65535)
                except OSError as exc:
                    if not would_block(exc):
                        raise
                    self.timing.increment('io_rx_would_block')
                    break
                stamp = time.perf_counter_ns()
                raw = bytes(raw)
                self.capture_rx(raw, source, stamp)
                self.ready.append((raw, source))
                count += 1
                self.timing.increment('io_rx_captured')
                self.max_rx_buffer = max(self.max_rx_buffer, len(self.ready))
            self.max_batch = max(self.max_batch, count)
            return count
        except BaseException as exc:
            self.failed = exc
            raise

    def _try_send(self, until):
        self._check()
        if self.clock() >= until:
            raise TransportSendDeadlineError('nonblocking send deadline; response retry forbidden')
        raw, address, logged = self.pending
        if not logged:
            self.journal.append(0, raw, address)
            self.pending = (raw, address, True)
        self._check()
        if self.clock() >= until:
            raise TransportSendDeadlineError('send deadline reached during journal append')
        self.timing.increment('io_sendto_attempts')
        try:
            sent = self.transport.sendto(raw, address)
        except OSError as exc:
            if not would_block(exc):
                raise
            self.timing.increment('io_tx_would_block')
            return False
        if sent != len(raw):
            raise OSError('partial datagram send; frame release forbidden')
        self.pending = None
        self.timing.increment('io_tx_completed')
        self._false_ready = 0
        return True

    def send(self, raw, address, until):
        self._check()
        if self.pending is not None:
            raise TransportProgressError('single pending TX slot occupied')
        if not isinstance(raw, bytes):
            raise TypeError('immutable datagram required')
        self.pending = (raw, address, False)
        self.max_pending_tx = 1
        self.timing.increment('io_tx_submitted')
        try:
            if self._try_send(until):
                return
            while True:
                # On write backpressure, retain returned datagrams in bounded
                # FIFO order. A full FIFO disables read interest, never drops RX.
                read_count = self._drain_rx(until)
                if self.clock() >= until:
                    raise TransportSendDeadlineError('nonblocking send deadline')
                ready = self._wait(len(self.ready) < self.batch_packets, True, until)
                if self.clock() >= until:
                    raise TransportSendDeadlineError('nonblocking send deadline')
                read_count += self._drain_rx(until) if ready[0] else 0
                sent = self._try_send(until) if ready[1] else False
                self._false_wakeup(ready, sent or read_count)
                if sent:
                    return
        except BaseException as exc:
            self.failed = exc
            raise

    def receive(self, until):
        self._check()
        if self.clock() >= until:
            raise socket.timeout('absolute receive deadline')
        if self.ready:
            return self.ready.popleft()
        try:
            if self._drain_rx(until):
                return self.ready.popleft()
            ready = self._wait(True, False, until)
            count = self._drain_rx(until) if ready[0] else 0
            self._false_wakeup(ready, count)
            if count:
                return self.ready.popleft()
            if self.clock() >= until:
                raise socket.timeout('absolute receive deadline')
            # Early/spurious wait completion is neither a lost response nor
            # an input retry. The owner services timers before calling again.
            return None
        except socket.timeout:
            raise
        except BaseException as exc:
            self.failed = exc
            raise
