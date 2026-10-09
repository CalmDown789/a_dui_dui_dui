"""Bind all step04 checks to the isolated candidate and unchanged baselines."""
from pathlib import Path
import ast,difflib,hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[1]
STEP3=WORK/'output/HOST_STEP03_NONBLOCKING_20261009'
STEP2=WORK/'output/HOST_STEP02_CODEC_TIMING_20261009'
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
base=load(ROOT/'STEP03_BASELINE.json');step2=load(STEP2/'SOURCE_MANIFEST.json')
assert sha(STEP3/'FINAL_RECEIPT.json')==sha(ROOT/'STEP03_RECEIPT.json')
files=[];changed=[];patch=''
for r in base['files']:
    rel=r['file'];before=ROOT/'baseline'/rel;after=ROOT/'main'/rel
    assert sha(before)==sha(STEP3/'main'/rel)==r['step03_sha256'],rel
    digest=sha(after);files.append(dict(file=rel,step03_sha256=r['step03_sha256'],candidate_sha256=digest))
    if digest!=r['step03_sha256']:
        changed.append(rel)
        patch+=''.join(difflib.unified_diff(before.read_text().splitlines(True),after.read_text().splitlines(True),fromfile='baseline/'+rel,tofile='main/'+rel))
expected={'streaming/streaming_client.py','streaming/timing_diagnostics.py','streaming/binary_journal.py','streaming/nonblocking_io.py'}
assert set(changed)==expected
(ROOT/'sampled_timing_changes.patch').write_text(patch,encoding='utf-8')
for prefix in ('main','baseline'):
    for p in (ROOT/prefix).rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
def method(prefix,file,name,cls=None):
    tree=ast.parse((ROOT/prefix/'streaming'/file).read_text())
    body=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls).body if cls else tree.body
    return next(n for n in body if isinstance(n,ast.FunctionDef)and n.name==name)
protected={'streaming_client.py':['decode_any'], 'client_methods':['matching','exchange','hello','input_packets','transfer'],
           'io_methods':['_check','_false_wakeup','_drain_rx','_try_send','send','receive'],
           'journal_methods':['check','finalize','abort']}
for key,names in protected.items():
    file,cls=(key,None)if key=='streaming_client.py'else ('streaming_client.py','StreamingClient')if key=='client_methods'else ('nonblocking_io.py','NonblockingDatagramIO')if key=='io_methods'else ('binary_journal.py','BinaryJournal')
    for name in names:assert ast.dump(method('main',file,name,cls))==ast.dump(method('baseline',file,name,cls)),name
for name in ('append','checkpoint'):
    old=method('baseline','binary_journal.py',name,'BinaryJournal');new=method('main','binary_journal.py',name,'BinaryJournal')
    old_try=next(n for n in old.body if isinstance(n,ast.Try));new_try=next(n for n in new.body if isinstance(n,ast.Try))
    assert [ast.dump(n)for n in old_try.body]==[ast.dump(n)for n in new_try.body],name
for r in step2['files']:
    assert sha(Path(r['source']))==r['baseline_sha256']
    assert sha(STEP2/'main'/r['file'])==r['candidate_sha256']
for rel,digest in step2['unchanged_release_identities'].items():assert sha(Path(r'C:\t6dup09\main')/rel)==digest
assert sha(Path(r'C:\t6dup09\pc4k\SUPPLEMENT_MANIFEST.json'))=='6c8edf91e8599e13b574443558225c8edbf8399dbe4ab110cfa128f502098cd4'
assert sha(WORK/'output/RTL_STEP01_RETRY_20261009/rtl/evf2_result_window.sv')==step2['step01_candidate_sha256']
for r in step2['test_assets']:assert sha(ROOT/'main/data'/r['file'])==sha(Path(r['source']))==r['sha256']
source=dict(status='ISOLATED_STEP04_SAMPLED_TIMING_NOT_RELEASE',files=files,changed_functional_files=changed,
    default_timing_mode='full',sampled_activation='explicit timing_mode=sampled',sample_every_default=16,
    protected_ast_checks=protected,raw_journal_not_sampled=True,frame_timing_not_sampled=True,
    unchanged_release_identities=step2['unchanged_release_identities'],all_manifest_frames_included=False,
    board_io=False,RTL_changed=False,BIT_generated=False)
(ROOT/'SOURCE_MANIFEST.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
matrix=load(ROOT/'TIMING_MODE_MATRIX.json');sampler=load(ROOT/'SAMPLER_CHECKS.json');bench=load(ROOT/'TIMING_BENCHMARK.json')
edge=load(ROOT/'validation/protocol_edge_regression.json')
for result in (matrix,sampler,bench,edge):assert result['status']=='PASS'
partitions=('rx_decode_rejected','rx_identity_rejected','rx_output_wrong_frame','rx_output_rejected','rx_output_accepted','rx_control_delivered')
def verify_named_sources(mapping):
    for name,digest in mapping.items():
        if name in ('host_regression.py','check_host_window128.py'):p=ROOT/'main/proof'/name
        elif name=='video_protocol.py':p=ROOT/'main/host'/name
        elif (ROOT/'main/streaming'/name).exists():p=ROOT/'main/streaming'/name
        else:p=ROOT/'validation'/name
        assert sha(p)==digest,name
for row in matrix['rows']:
    for key in ('host_results','window128_results'):
        p=Path(row[key]);assert sha(p)==row[key+'_sha256'];r=load(p)
        assert r['status']=='PASS'and r['timing_mode']==row['timing_mode']and r['io_mode']==row['io_mode']
        verify_named_sources(r['source_sha256'])
        if key=='host_results':
            assert len(r['fault_cases'])==26 and r['full_frozen_audit']['golden_bytes']==4147200
            dirs=[p.parent/'full_frozen']+[p.parent/c['fault']for c in r['fault_cases']]
            for c in r['fault_cases']:
                assert c['status']=='PASS'
                if not c['expected_transfer_success']:assert c['frame_releases']==0 and not(p.parent/c['fault']/'JOURNAL.json').exists()
        else:
            assert len(r['rows'])==7
            dirs=[p.parent/c['fault']for c in r['rows']]
            for c in r['rows']:assert c['releases']==2 and c['raw_audit']['golden_bytes']==4147200
        for d in dirs:
            timing=load(d/'TIMING_DIAGNOSTICS.json');meta=timing['metadata'];counters=timing['counters']
            assert timing['profiling']['mode']==row['timing_mode']
            assert sum(counters.get(n,0)for n in partitions)+meta['rx_prefetched_unprocessed']==meta['received_datagrams']
            if row['io_mode']=='nonblocking':assert meta['max_rx_buffer']<=32 and meta['max_pending_tx']<=1 and 'settimeout'not in timing['stages']
            if row['timing_mode']=='sampled':assert 'receive_service_interval'not in timing['stages']
            if (d/'FRAMES.json').exists():
                frames=load(d/'FRAMES.json');assert timing['stages']['frame_transfer']['count']==len(frames)
for row in matrix['supplement']:
    p=ROOT/row['report'];assert sha(p)==row['sha256'];r=load(p);assert r['status']=='PASS'
    verify_named_sources(r['source_sha256'])
assert len(matrix['rows'])==4 and len(matrix['supplement'])==4 and len(sampler['checks'])==10
verify_named_sources(sampler['source_sha256']);verify_named_sources(edge['source_sha256'])
assert len(bench['rows'])==18
for r in bench['rows']:
    assert r['output_duplicate_packets']==0 and r['golden_bytes']==4147200 and r['frame_timing_samples']==2
    for rel,digest in r['source_sha256'].items():assert sha(ROOT/rel)==digest,rel
artifacts=['SOURCE_MANIFEST.json','STEP03_BASELINE.json','STEP03_RECEIPT.json','TIMING_MODE_MATRIX.json',
    'SAMPLER_CHECKS.json','TIMING_BENCHMARK.json','FAILED_VALIDATION.json','sampled_timing_changes.patch',
    '第4步检查说明.md','finalize_step04.py','validation/protocol_edge_regression.json']
artifacts+=[r['report']for r in matrix['supplement']]
artifacts+=[str(p.relative_to(ROOT))for p in sorted((ROOT/'validation').glob('*.py'))]
receipt=dict(status='STEP04_COMPLETE_FOR_USER_REVIEW_NOT_RELEASE',changed_functional_files=changed,
    source_and_protected_ast_verified=True,previous_candidates_and_paired_release_unchanged=True,
    io_timing_configurations=4,host_fault_cases_per_configuration=26,full_window128_cases_per_configuration=7,
    scheduler_checks_per_timing_mode=21,backpressure_checks_per_timing_mode=5,sampler_checks=10,protocol_edge_checks=6,
    raw_journal_full=True,frame_timing_full=True,exact_rx_classification_reconciled=True,
    benchmark_two_frame_wall_median_ns=bench['median_two_frame_wall_ns'],
    sampled_wall_reduction_vs_step04_full_percent=bench['sampled_wall_reduction_vs_step04_full_percent'],
    sampled_wall_reduction_vs_step03_full_percent=bench['sampled_wall_reduction_vs_step03_full_percent'],
    actual_30fps_or_real_host_cpu_budget_proven=False,socket_created=False,board_io=False,RTL_changed=False,BIT_generated=False,
    asynchronous_journal_implemented=False,input_window_or_credit_changed=False,cross_frame_prefetch_implemented=False,
    default_timing_mode='full',sampled_mode_opt_in=True,next_step_started=False,
    artifact_sha256={rel:sha(ROOT/rel)for rel in artifacts})
(ROOT/'FINAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print('STEP04_COMPLETE_FOR_USER_REVIEW; full/raw integrity and offline suites PASS; original identities unchanged')
