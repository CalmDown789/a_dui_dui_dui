"""Evidence replay, compatible error checks and bounded timing regression; no IO transport."""
from pathlib import Path
import gc,hashlib,importlib.util,json,random,statistics,sys,time,zlib
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'main/host'));sys.path.insert(0,str(HERE/'main/streaming'))
from streaming_client import decode_any as candidate, encode2
from timing_diagnostics import BoundedTiming
from video_protocol import Packet,InvalidPacket
from binary_journal import records

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
original=module('baseline_client',HERE/'baseline/streaming/streaming_client.py').decode_any
old_timing=module('baseline_timing',HERE/'baseline/streaming/timing_diagnostics.py').BoundedTiming

def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def outcome(fn,raw):
    try:return ('accepted',fn(raw))
    except InvalidPacket as exc:return ('rejected',type(exc).__name__,exc.reason,exc.packet)
def fix_crc(raw,payload=False):
    raw=bytearray(raw)
    if payload:raw[56:60]=zlib.crc32(raw[64:]).to_bytes(4,'big')
    raw[60:64]=zlib.crc32(raw[:60]).to_bytes(4,'big');return bytes(raw)

def codec_checks():
    journal=Path(r'C:\t6dup09\pc4k\attempts\Run_short_once_20261009\live\traffic\datagrams.bin')
    samples=[];count=0
    for _,_,raw,_ in records(journal):
        assert original(raw)==candidate(raw)
        count+=1
        if raw[:5]==b'EVF2\x02' and raw[5]==0x17 and len(samples)<2025:samples.append(raw)
    rng=random.Random(20261009);cases=[]
    cases.extend([b'',b'EVF1',b'EVF2',bytes(63),bytes(64),bytes(1089)])
    for size in [0,1,1023,1024]:
        p=Packet(3,bytes(range(16)),payload=bytes([0x5a])*size)
        for raw in [p.encode(),encode2(p)]:
            cases.append(raw)
            for at in [0,1,4,5,6,8,24,28,32,36,40,44,46,48,52,56,60,63]:
                bad=bytearray(raw);bad[at]^=1;cases.append(bytes(bad));cases.append(fix_crc(bad))
            for n in [0,4,5,59,60,63,64,len(raw)-1]:cases.append(raw[:n])
            cases.extend([raw+b'\0',fix_crc(raw+b'\0'),fix_crc(raw+b'\0'*1100)])
    for i in range(10000):
        raw=bytearray(rng.choice(samples));raw[rng.randrange(len(raw))]^=1<<rng.randrange(8)
        cases.append(fix_crc(raw,payload=(i%5==0)) if i%3==0 else bytes(raw))
    rejected=accepted=0
    for raw in cases:
        before=outcome(original,raw);after=outcome(candidate,raw);assert before==after,(len(raw),before,after)
        rejected+=after[0]=='rejected';accepted+=after[0]=='accepted'
    # Interleave order across rounds to reduce warmup/order bias; no socket/timeouts/journal in this benchmark.
    measurements={'baseline':[],'candidate':[]};functions={'baseline':original,'candidate':candidate}
    gc.disable()
    try:
        for round_id in range(8):
            order=['baseline','candidate'] if round_id%2==0 else ['candidate','baseline']
            for name in order:
                fn=functions[name];began=time.perf_counter_ns()
                for _ in range(20):
                    for raw in samples:fn(raw)
                measurements[name].append((time.perf_counter_ns()-began)/(20*len(samples)))
    finally:gc.enable()
    med={k:statistics.median(v) for k,v in measurements.items()}
    with journal.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    result=dict(status='PASS',scope='OFFLINE_ORIGINAL_JOURNAL_AND_LOCAL_DECODE_BENCHMARK_NOT_BOARD_OR_SOCKET_FPS',
        original_valid_records_equal=count,mutated_and_boundary_cases=len(cases),
        acceptance_fields_error_reason_and_error_packet_equal=True,rejected_cases=rejected,accepted_cases=accepted,
        journal_sha256=digest,median_ns_per_packet=med,laps_ns_per_packet=measurements,
        speedup=med['baseline']/med['candidate'],decode_time_reduction_percent=100*(1-med['candidate']/med['baseline']))
    save('CODEC_CHECKS.json',result);print('CODEC_PASS records='+str(count)+' boundary_mutations='+str(len(cases)),flush=True)

def timing_checks():
    old=old_timing(1,2)
    for value in [10,20,30]:old.record('test',value)
    observed=sorted(x['wall_ns'] for x in old.snapshot('baseline')['slowest_events'])
    assert observed==[10,30]
    t=BoundedTiming(1,2)
    for value in [10,20,30]:t.record('test',value)
    assert [x['wall_ns'] for x in t.snapshot('candidate')['slowest_events']]==[30,20]
    old_zero=old_timing();old_zero.record('zero',0)
    assert old_zero.stages['zero'][5][-1]==1
    zero=BoundedTiming();zero.record('zero',0)
    assert zero.stages['zero'][5][0]==1 and zero.stages['zero'][5][-1]==0
    rng=random.Random(20261009)
    orders=[('ascending',list(range(1,201))),('descending',list(range(200,0,-1))),
            ('random',[rng.randrange(0,10000) for _ in range(500)]),('equal',[20]*200),
            ('threshold',[0,1,9,10,11,20,100]),('negative_and_zero',[-1,0,0,1,10,100])]
    rows=[]
    for name,values in orders:
        for cap in [0,1,2,64,600]:
            t=BoundedTiming(slow_threshold_ns=10,max_slow_events=cap)
            for n,value in enumerate(values):t.record('test',value,cpu_ns=n,detail={'input_index':n})
            normalized=[max(0,int(v)) for v in values];snap=t.snapshot('offline')
            assert [x['wall_ns'] for x in snap['slowest_events']]==sorted([v for v in normalized if v>=10],reverse=True)[:cap]
            s=snap['stages']['test']
            assert s['count']==len(values) and s['wall_total_ns']==sum(normalized) and s['wall_max_ns']==max(normalized)
            assert s['thread_cpu_total_ns']==sum(range(len(values)))
            assert sum(x['count'] for x in s['log2_histogram'])==len(values)
            assert len(t._slow)<=cap
            # Repeated snapshot is read-only and exports deterministic details, including tied durations.
            assert snap==t.snapshot('offline')
            rows.append(dict(order=name,max_slow_events=cap,status='PASS'))
    no_events=BoundedTiming();assert no_events.snapshot('empty')['stages']=={}
    for threshold,cap in [(0,64),(-1,1),(1,-1)]:
        try:BoundedTiming(threshold,cap)
        except ValueError:pass
        else:raise AssertionError('invalid timing configuration accepted')
    result=dict(status='PASS',baseline_top2_wrong=[10,30],candidate_top2=[30,20],
        baseline_zero_bucket=31,candidate_zero_bucket=0,topk_matrix=rows,
        totals_maximum_cpu_histogram_counts_and_bounds_checked=True,empty_and_invalid_configurations_checked=True,
        legacy_slowest_events_recovered=False)
    save('TIMING_CHECKS.json',result);print('TIMING_PASS combinations='+str(len(rows)),flush=True)

if __name__=='__main__':
    timing_checks();codec_checks()
