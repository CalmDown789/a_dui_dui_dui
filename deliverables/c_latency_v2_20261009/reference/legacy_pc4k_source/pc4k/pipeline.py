"""Candidate PC-only Y8 bicubic x2 interface. No board/network side effects."""
from dataclasses import dataclass, field
from queue import Queue, Full, Empty
from threading import Thread, Lock
from time import perf_counter_ns, thread_time_ns
import numpy as np
import cv2

INPUT_SHAPE = (1080, 1920)
OUTPUT_SHAPE = (2160, 3840)
SEMANTICS = 'candidate-cubic-a075-halfpixel-replicate-rne-y8-v1'

def validate_y8(a, shape=None):
    if not isinstance(a, np.ndarray) or a.dtype != np.uint8 or a.ndim != 2:
        raise ValueError('Y8 must be a 2D NumPy uint8 array')
    if shape is not None and a.shape != shape:
        raise ValueError(f'expected {shape}, got {a.shape}')
    if min(a.shape) < 1 or not a.flags.c_contiguous:
        raise ValueError('Y8 must be nonempty, C-contiguous row-major without stride padding')

@dataclass(frozen=True)
class ReceivedFrame:
    frame_id: int
    y8: np.ndarray
    model_source: str
    received_complete_ns: int
    source_kind: str
    verified: bool = True
    integrity_sha256: str = ''
    source_frame_id: int | None = None

    def validate(self):
        validate_y8(self.y8, INPUT_SHAPE)
        if type(self.frame_id) is not int or not 0 <= self.frame_id <= 0xffffffff:
            raise ValueError('frame_id must be uint32; wrap requires a new Pipeline/session')
        if self.verified is not True or not isinstance(self.model_source,str) or not self.model_source.strip() or not isinstance(self.source_kind,str) or not self.source_kind.strip():
            raise ValueError('complete, integrity-verified frame and explicit model/source required')
        if type(self.received_complete_ns) is not int or not 0 < self.received_complete_ns <= perf_counter_ns():
            raise ValueError('receive timestamp must use local perf_counter_ns, not board/UTC clock')

@dataclass
class CompletedFrame:
    frame_id: int
    y8: np.ndarray
    model_source: str
    source_kind: str
    received_complete_ns: int
    processing_start_ns: int
    processing_complete_ns: int
    backend: str
    stages_ms: dict
    preview_submitted_ns: int | None = None
    preview_size: tuple | None = None
    semantics: str = SEMANTICS
    source_frame_id: int | None = None
    processing_thread_cpu_ns: int = 0

class CpuBicubic:
    """float64 is intentional: x2 dyadic coefficients are exact before final RNE."""
    name = 'opencv-f64'
    def __init__(self, threads=4):
        cv2.setNumThreads(threads)
        cv2.ocl.setUseOpenCL(False)
        # Stable native path; do not silently substitute optional IPP interpolation.
        if hasattr(cv2, 'ipp'):
            cv2.ipp.setUseIPP(False)

    def resize(self, a):
        validate_y8(a)
        t0 = perf_counter_ns()
        f = a.astype(np.float64)
        t1 = perf_counter_ns()
        v = cv2.resize(f, (a.shape[1]*2, a.shape[0]*2), interpolation=cv2.INTER_CUBIC)
        t2 = perf_counter_ns()
        np.rint(v, out=v)
        np.clip(v, 0, 255, out=v)
        result = v.astype(np.uint8)
        t3 = perf_counter_ns()
        return result, {'cpu_input_cast_ms': (t1-t0)/1e6, 'interpolation_ms': (t2-t1)/1e6,
                        'round_clip_output_ms': (t3-t2)/1e6, 'host_ready_ms': (t3-t0)/1e6}

class CudaBicubic:
    """Optional GPU path, with synchronized H2D, kernel and D2H event timings."""
    name = 'torch-cuda-f64'
    def __init__(self, dtype='float64'):
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; choose opencv-f64 explicitly')
        self.torch = torch
        self.dtype = getattr(torch, dtype)
        self.name = 'torch-cuda-f64' if dtype == 'float64' else 'torch-cuda-f32-exploratory'
        self.stream = torch.cuda.Stream()
        self.shape = None

    def resize(self, a):
        validate_y8(a)
        t = self.torch
        import torch.nn.functional as F
        t0 = perf_counter_ns()
        if self.shape != a.shape:
            self.host_in = t.empty(a.shape, dtype=t.uint8, pin_memory=True)
            self.host_out = t.empty((a.shape[0]*2,a.shape[1]*2), dtype=t.uint8, pin_memory=True)
            self.shape = a.shape
        np.copyto(self.host_in.numpy(), a)
        t1 = perf_counter_ns()
        events = [t.cuda.Event(enable_timing=True) for _ in range(6)]
        with t.inference_mode(), t.cuda.stream(self.stream):
            events[0].record()
            gpu = self.host_in.to('cuda', non_blocking=True)
            events[1].record()
            f = gpu.to(self.dtype)[None,None]
            events[2].record()
            v = F.interpolate(f, scale_factor=2, mode='bicubic', align_corners=False, antialias=False)
            events[3].record()
            result = v.round_().clamp_(0,255).to(t.uint8)[0,0]
            events[4].record()
            self.host_out.copy_(result, non_blocking=True)
            events[5].record()
        events[5].synchronize()  # host output is now real; never time only the enqueue.
        t2 = perf_counter_ns()
        result = self.host_out.numpy().copy()  # owned output survives next frame
        t3 = perf_counter_ns()
        return result, {'host_to_pinned_ms': (t1-t0)/1e6,
            'h2d_event_ms': events[0].elapsed_time(events[1]),
            'gpu_cast_event_ms': events[1].elapsed_time(events[2]),
            'gpu_interpolation_event_ms': events[2].elapsed_time(events[3]),
            'gpu_round_clip_y8_event_ms': events[3].elapsed_time(events[4]),
            'd2h_event_ms': events[4].elapsed_time(events[5]),
            'gpu_pipeline_event_ms': events[0].elapsed_time(events[5]),
            'enqueue_wait_ms': (t2-t1)/1e6, 'owned_output_copy_ms': (t3-t2)/1e6,
            'host_ready_ms': (t3-t0)/1e6}

def make_backend(name='opencv-f64', threads=4):
    if name == 'opencv-f64':
        return CpuBicubic(threads)
    if name == 'torch-cuda-f64':
        return CudaBicubic()
    if name == 'torch-cuda-f32-exploratory':
        return CudaBicubic('float32')
    raise ValueError(f'unknown backend {name}')

def postprocess(frame, backend):
    frame.validate()
    cpu_start = thread_time_ns()
    start = perf_counter_ns()
    y, timings = backend.resize(frame.y8)
    validate_y8(y, OUTPUT_SHAPE)
    return CompletedFrame(frame.frame_id, y, frame.model_source, frame.source_kind,
        frame.received_complete_ns, start, perf_counter_ns(), backend.name, timings,
        source_frame_id=frame.source_frame_id, processing_thread_cpu_ns=thread_time_ns()-cpu_start)

@dataclass
class Stats:
    attempted: int = 0
    accepted: int = 0
    rejected_full: int = 0
    rejected_invalid: int = 0
    rejected_id: int = 0
    completed: int = 0
    errors: int = 0
    output_discarded: int = 0
    input_peak: int = 0
    output_peak: int = 0
    worker_thread_cpu_ns: int = 0

class MeasuredQueue(Queue):
    def __init__(self, capacity):
        super().__init__(capacity)
        self.peak=0

    def _put(self,item):
        super()._put(item)
        # _put runs under Queue.mutex, before any consumer can pop the item.
        if item is not None:self.peak=max(self.peak,len(self.queue))

class Pipeline:
    """One worker, finite input/output queues. Full rejects explicitly, never hides loss.

    Caller must not mutate an accepted input until its output/error is returned.
    Worker blocks on full output; use get()/drain before close(). Frame IDs increase.
    """
    def __init__(self, backend, capacity=2):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('capacity must be positive')
        self.backend, self.input, self.output = backend, MeasuredQueue(capacity), MeasuredQueue(capacity)
        self.stats, self.lock, self.last_id = Stats(), Lock(), -1
        self.closed = False
        self.worker = Thread(target=self._run, name='pc4k-worker', daemon=False)
        self.worker.start()

    def submit(self, frame, timeout=0):
        with self.lock:
            if self.closed:
                raise RuntimeError('Pipeline is closed')
            self.stats.attempted += 1
            try:
                frame.validate()
            except (ValueError, AttributeError):
                self.stats.rejected_invalid += 1
                raise
            if frame.frame_id <= self.last_id:
                self.stats.rejected_id += 1
                raise ValueError('duplicate/out-of-order frame_id')
            try:
                # Keep metadata mutation ordered with concurrent producers.
                self.input.put(frame, block=timeout != 0, timeout=timeout if timeout else None)
            except Full:
                self.stats.rejected_full += 1
                return False
            self.last_id = frame.frame_id
            self.stats.accepted += 1
            self.stats.input_peak = self.input.peak
            return True

    def _run(self):
        while True:
            frame = self.input.get()
            if frame is None:
                self.input.task_done()
                return
            try:
                item = postprocess(frame, self.backend)
                self.stats.completed += 1
                self.stats.worker_thread_cpu_ns += item.processing_thread_cpu_ns
            except Exception as error:
                item = {'frame_id': frame.frame_id, 'error': repr(error)}
                self.stats.errors += 1
            self.output.put(item)  # bounded backpressure; no silent overwrite
            self.stats.output_peak = self.output.peak
            self.input.task_done()

    def get(self, timeout=10):
        return self.output.get(timeout=timeout)

    def close(self, timeout=10):
        # Preserve outputs: callers drain all accepted frames before close.
        with self.lock:
            send_sentinel=not self.closed
            self.closed = True
        if send_sentinel:
            try:
                self.input.put(None, timeout=timeout)
            except Full:
                with self.lock:self.closed=False
                raise TimeoutError('input blocked: drain accepted output frames, then retry close')
        self.worker.join(timeout)
        if self.worker.is_alive():
            raise TimeoutError('drain output queue before close; worker still active')
