"""Low-overhead bounded timing summaries for the live EVF2 host path."""
import heapq
import math
import threading
import time


class BoundedTiming:
    def __init__(self, slow_threshold_ns=2_000_000, max_slow_events=64,
                 mode='full', sample_every=16):
        if slow_threshold_ns < 1 or max_slow_events < 0:
            raise ValueError('bounded timing configuration')
        if mode not in ('full', 'sampled') or not isinstance(sample_every,int) or not 1 <= sample_every <= 1024:
            raise ValueError('explicit timing mode and bounded sample interval')
        self.mode, self.sample_every = mode, sample_every
        self.observations = {}
        self.selected = {}
        self.slow_threshold_ns = slow_threshold_ns
        self.max_slow_events = max_slow_events
        self.stages = {}
        self.counters = {}
        self._slow = []
        self._sequence = 0

    def increment(self, name, amount=1):
        self.counters[name] = self.counters.get(name, 0) + amount

    def begin(self, stage, *, always=False):
        count = self.observations.get(stage, 0) + 1
        self.observations[stage] = count
        if self.mode == 'full' or always or (count-1) % self.sample_every == 0:
            self.selected[stage] = self.selected.get(stage, 0) + 1
            return time.perf_counter_ns(), time.thread_time_ns()
        return None

    def end(self, stage, token, detail=None, *, end_ns=None):
        if token is None:
            return
        wall_end = time.perf_counter_ns() if end_ns is None else end_ns
        self.record(stage, wall_end-token[0], time.thread_time_ns()-token[1], detail)

    def record(self, stage, wall_ns, cpu_ns=None, detail=None):
        wall_ns = max(0, int(wall_ns))
        row = self.stages.get(stage)
        if row is None:
            # count, wall sum, wall max, cpu sum, cpu max, log2 histogram
            row = [0, 0, 0, 0, 0, [0] * 32]
            self.stages[stage] = row
        row[0] += 1
        row[1] += wall_ns
        row[2] = max(row[2], wall_ns)
        bucket = min(31, max(0, wall_ns.bit_length() - 1))
        row[5][bucket] += 1
        if cpu_ns is not None:
            cpu_ns = max(0, int(cpu_ns))
            row[3] += cpu_ns
            row[4] = max(row[4], cpu_ns)
        if wall_ns < self.slow_threshold_ns or self.max_slow_events == 0:
            return
        event = {'stage': stage, 'wall_ns': wall_ns, 'cpu_ns': cpu_ns,
                 'at_perf_counter_ns': time.perf_counter_ns(),
                 'thread_name': threading.current_thread().name,
                 'thread_ident': threading.get_ident()}
        if detail:
            event['detail'] = dict(detail)
        item = (wall_ns, self._sequence, event)
        self._sequence += 1
        if len(self._slow) < self.max_slow_events:
            heapq.heappush(self._slow, item)
        elif wall_ns > self._slow[0][0]:
            heapq.heapreplace(self._slow, item)

    @staticmethod
    def _quantile(histogram, count, fraction):
        if not count:
            return None
        target = max(1, math.ceil(count * fraction))
        seen = 0
        for index, value in enumerate(histogram):
            seen += value
            if seen >= target:
                return 1 << (index + 1)
        return 1 << 32

    def snapshot(self, scope, **metadata):
        stages = {}
        for name, row in sorted(self.stages.items()):
            count, total, maximum, cpu_total, cpu_maximum, histogram = row
            stages[name] = {
                'count': count,
                'wall_total_ns': total,
                'wall_mean_ns': total / count if count else None,
                'wall_p50_upper_bound_ns': self._quantile(histogram, count, .50),
                'wall_p95_upper_bound_ns': self._quantile(histogram, count, .95),
                'wall_max_ns': maximum,
                'thread_cpu_total_ns': cpu_total,
                'thread_cpu_mean_ns': cpu_total / count if count else None,
                'thread_cpu_max_ns': cpu_maximum,
                'log2_histogram': [{'upper_bound_ns': 1 << (i + 1), 'count': n}
                                   for i, n in enumerate(histogram) if n],
                'observed_calls': self.observations.get(name, count),
                'recorded_samples': count,
                'population_scope': ('ALL_OBSERVED_CALLS' if count == self.observations.get(name,count)
                                     else 'RECORDED_SAMPLES_ONLY'),
            }
        return {
            'scope': scope,
            'clock': 'time.perf_counter_ns / QPC on Windows',
            'thread_cpu_clock': 'time.thread_time_ns; current calling thread only',
            'slow_event_threshold_ns': self.slow_threshold_ns,
            'slow_event_limit': self.max_slow_events,
            'counters': dict(sorted(self.counters.items())),
            'stages': stages,
            'slowest_events': [row[2] for row in sorted(self._slow, reverse=True)],
            'metadata': metadata,
            'hardware_timestamp_claim': False,
            'profiling': {
                'mode': self.mode, 'sample_every': self.sample_every if self.mode == 'sampled' else 1,
                'selection': 'FIRST_AND_EVERY_NTH_CALL_PER_STAGE_NO_EXTRAPOLATION',
                'observed_calls': dict(sorted(self.observations.items())),
                'selected_calls': dict(sorted(self.selected.items())),
                'fine_stage_totals_and_quantiles_scope': 'RECORDED_CALLS_ONLY',
                'slowest_events_scope': 'RECORDED_CALLS_ONLY_UNSAMPLED_SLOW_EVENTS_MAY_BE_MISSED',
            },
        }
