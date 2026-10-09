"""Sampling semantics, exact raw evidence and unsampled writer failure checks."""
from pathlib import Path
import hashlib,json,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'main/streaming'))
import timing_diagnostics as td
from timing_diagnostics import BoundedTiming
from binary_journal import BinaryJournal,records
RUN=ROOT/'validation/sampler_runs'/str(time.time_ns());RUN.mkdir(parents=True)
rows=[]
class SpyClock:
    def __init__(self):self.ns=0;self.wall_calls=self.cpu_calls=0
    def perf_counter_ns(self):self.wall_calls+=1;self.ns+=10;return self.ns
    def thread_time_ns(self):self.cpu_calls+=1;return self.ns//2

original=td.time
try:
    for mode in ('full','sampled'):
        spy=SpyClock();td.time=spy;t=BoundedTiming(mode=mode,sample_every=16);built=0
        for _ in range(64):
            token=t.begin('hot')
            if token is not None:
                built+=1;t.end('hot',token,{'built':built})
            t.increment('datagrams')
        expected=64 if mode=='full'else 4
        assert spy.wall_calls==spy.cpu_calls==2*expected and built==expected
        snap=t.snapshot('spy_clock')
        assert t.observations['hot']==64 and t.stages['hot'][0]==expected and t.counters['datagrams']==64
        assert snap['stages']['hot']['wall_total_ns']==10*expected
        assert snap['stages']['hot']['recorded_samples']==expected
        assert snap['stages']['hot']['population_scope']==('ALL_OBSERVED_CALLS'if mode=='full'else 'RECORDED_SAMPLES_ONLY')
        rows.append(dict(case='clock_and_detail_gating_'+mode,status='PASS',observed_calls=64,
            measured_calls=expected,diagnostic_wall_clock_calls=spy.wall_calls,diagnostic_cpu_clock_calls=spy.cpu_calls,detail_builds=built))
    for interval in (1,2,16,1024):
        spy=SpyClock();td.time=spy;t=BoundedTiming(mode='sampled',sample_every=interval)
        for q in range(123):
            for stage in ('a','b'):
                token=t.begin(stage)
                if token is not None:t.end(stage,token)
            token=t.begin('checkpoint',always=True);t.end('checkpoint',token)
        expected=(122//interval)+1
        assert t.stages['a'][0]==t.stages['b'][0]==expected and t.stages['checkpoint'][0]==123
        assert t.observations=={'a':123,'b':123,'checkpoint':123}
        rows.append(dict(case='independent_stage_sampling_'+str(interval),status='PASS',samples_per_stage=expected,checkpoints=123))
    td.time=original
    for mode,interval in [('off',16),('sampled',0),('sampled',1025),('sampled',1.5)]:
        try:BoundedTiming(mode=mode,sample_every=interval)
        except ValueError:pass
        else:raise AssertionError('invalid timing config accepted')
    t=BoundedTiming(1,2)
    for v in (10,20,30):t.record('top',v)
    assert [r['wall_ns']for r in t.snapshot('top')['slowest_events']]==[30,20]
    t.record('zero',0);assert t.stages['zero'][5][0]==1
    rows.append(dict(case='invalid_config_topk_zero_histogram',status='PASS'))
    t=BoundedTiming(mode='sampled');t.record('frame_transfer',33_000_000,7_000_000)
    assert t.snapshot('frame')['stages']['frame_transfer']['wall_total_ns']==33_000_000
    assert t.snapshot('frame')['stages']['frame_transfer']['thread_cpu_total_ns']==7_000_000
    rows.append(dict(case='frame_totals_not_sampled_or_scaled',status='PASS'))
finally:td.time=original

paths={};details={}
for mode in ('full','sampled'):
    t=BoundedTiming(mode=mode);j=BinaryJournal(RUN/mode,threshold=2048,timing=t)
    for q in range(200):j.append(q%2,bytes([q%256])*1088,('192.168.0.2',5000),stamp=1_000_000+q)
    manifest=j.finalize();p=j.out/'datagrams.bin';paths[mode]=p
    detail=t.snapshot('journal')
    assert len(list(records(p)))==200 and j.records==200
    expected=200 if mode=='full'else 13
    assert detail['stages']['journal_append']['count']==expected
    for stage in ('journal_file_write','journal_flush_block','journal_checkpoint'):
        assert detail['stages'][stage]['count']==detail['profiling']['observed_calls'][stage]
    details[mode]=dict(raw_sha256=manifest['sha256'],records=200,append_timing_samples=expected,
        file_write_timing_samples=detail['stages']['journal_file_write']['count'],max_buffer=manifest['max_buffer_bytes'])
assert paths['full'].read_bytes()==paths['sampled'].read_bytes()
rows.append(dict(case='full_raw_journal_byte_identical_under_sampling',status='PASS',details=details))

t=BoundedTiming(mode='sampled');j=BinaryJournal(RUN/'unsampled_failure',threshold=1088,timing=t)
j.append(0,b'A'*1088,('192.168.0.2',5000),stamp=10)
real=j.file
class ShortWriter:
    def __getattr__(self,name):return getattr(real,name)
    def write(self,body):real.write(body[:len(body)//2]);return len(body)//2
j.file=ShortWriter()
try:j.append(1,b'B'*1088,('192.168.0.2',5000),stamp=20)
except OSError:pass
else:raise AssertionError('unsampled append writer failure swallowed')
assert j.failed is not None and t.observations['journal_append']==2 and t.stages['journal_append'][0]==1
try:j.checkpoint()
except RuntimeError:pass
else:raise AssertionError('poisoned journal checkpoint allowed')
j.abort();assert not(j.out/'JOURNAL.json').exists()and(j.out/'ABORTED_CAPTURE.json').exists()
rows.append(dict(case='unsampled_write_failure_still_poisoned_and_withholds_success',status='PASS'))
result=dict(status='PASS',checks=rows,run_directory=str(RUN),scope='LOCAL_SAMPLER_AND_JOURNAL_NO_BOARD_OR_NETWORK',
    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in
        [Path(__file__),ROOT/'main/streaming/timing_diagnostics.py',ROOT/'main/streaming/binary_journal.py']})
(ROOT/'SAMPLER_CHECKS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('SAMPLER_PASS checks='+str(len(rows)))
