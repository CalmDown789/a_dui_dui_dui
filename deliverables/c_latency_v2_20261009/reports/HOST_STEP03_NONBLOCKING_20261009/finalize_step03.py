"""Source-bound offline review receipt; never accesses network transports."""
from pathlib import Path
import ast,difflib,hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[1]
STEP2=WORK/'output/HOST_STEP02_CODEC_TIMING_20261009'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
base=load(ROOT/'STEP02_BASELINE.json');step2=load(STEP2/'SOURCE_MANIFEST.json')
assert sha(STEP2/'FINAL_RECEIPT.json')==sha(ROOT/'STEP02_RECEIPT.json')
files=[];changed=[]
for row in base['files']:
    rel=row['file'];before=ROOT/'baseline'/rel;after=ROOT/'main'/rel
    assert sha(before)==sha(STEP2/'main'/rel)==row['step02_sha256'],rel
    digest=sha(after)
    files.append(dict(file=rel,step02_sha256=row['step02_sha256'],candidate_sha256=digest))
    if digest!=row['step02_sha256']:changed.append(rel)
assert changed==['streaming/streaming_client.py']
new='streaming/nonblocking_io.py';files.append(dict(file=new,step02_sha256=None,candidate_sha256=sha(ROOT/'main'/new)))
patch=''
for rel in changed+[new]:
    before=(ROOT/'baseline'/rel).read_text(encoding='utf-8')if (ROOT/'baseline'/rel).exists()else ''
    after=(ROOT/'main'/rel).read_text(encoding='utf-8')
    patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='baseline/'+rel,tofile='main/'+rel))
(ROOT/'nonblocking_changes.patch').write_text(patch,encoding='utf-8')
for p in (ROOT/'main').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
for p in (ROOT/'validation').glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
old_ast=ast.parse((ROOT/'baseline/streaming/streaming_client.py').read_text())
new_ast=ast.parse((ROOT/'main/streaming/streaming_client.py').read_text())
def decode_ast(tree):return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='decode_any'))
assert decode_ast(old_ast)==decode_ast(new_ast)
for row in step2['files']:assert sha(Path(row['source']))==row['baseline_sha256']
for row in step2['test_assets']:
    assert sha(ROOT/'main/data'/row['file'])==sha(Path(row['source']))==row['sha256']
for rel,digest in step2['unchanged_release_identities'].items():assert sha(Path(r'C:\t6dup09\main')/rel)==digest
assert sha(Path(r'C:\t6dup09\pc4k\SUPPLEMENT_MANIFEST.json'))=='6c8edf91e8599e13b574443558225c8edbf8399dbe4ab110cfa128f502098cd4'
assert sha(WORK/'output/RTL_STEP01_RETRY_20261009/rtl/evf2_result_window.sv')==step2['step01_candidate_sha256']
source=dict(status='ISOLATED_STEP03_NONBLOCKING_HOST_NOT_RELEASE',files=files,
    changed_functional_files=changed+[new],step02_decode_and_other_copied_files_unchanged=True,
    default_io_mode='timeout',nonblocking_activation='explicit io_mode=nonblocking',
    unchanged_release_identities=step2['unchanged_release_identities'],
    test_asset_sha256={row['file']:row['sha256']for row in step2['test_assets']},all_manifest_frames_included=False,
    board_io=False,RTL_changed=False,BIT_generated=False)
(ROOT/'SOURCE_MANIFEST.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
mode=load(ROOT/'MODE_COMPARISON.json');checks=load(ROOT/'NONBLOCKING_CHECKS.json')
back=load(ROOT/'TRANSFER_BACKPRESSURE.json');replay=load(ROOT/'REPLAY_COMPARISON.json')
edge=load(ROOT/'validation/protocol_edge_regression.json')
for r in (mode,checks,back,replay,edge):assert r['status']=='PASS'
for row in mode['rows']:
    for key in ('host_results','window128_results'):
        p=Path(row[key]);assert sha(p)==row[key+'_sha256'];result=load(p)
        assert result['status']=='PASS'and result['io_mode']==row['io_mode']
        for name,digest in result['source_sha256'].items():
            prefix='proof'if name in ('host_regression.py','check_host_window128.py')else 'streaming'
            assert sha(ROOT/'main'/prefix/name)==digest,name
        if key=='host_results':
            assert len(result['fault_cases'])==26
            for r in result['fault_cases']:
                assert r['status']=='PASS'
                if not r['expected_transfer_success']:
                    assert r['frame_releases']==0 and not(p.parent/r['fault']/'JOURNAL.json').exists()
            directories=[p.parent/'full_frozen']+[p.parent/(r['fault']) for r in result['fault_cases']]
        else:
            assert len(result['rows'])==7
            for r in result['rows']:assert r['releases']==2 and r['raw_audit']['golden_bytes']==4147200
            directories=[p.parent/r['fault']for r in result['rows']]
        if row['io_mode']=='nonblocking':
            for directory in directories:
                timing=load(directory/'TIMING_DIAGNOSTICS.json')
                assert timing['metadata']['io_mode']=='nonblocking'
                assert timing['counters']['io_setblocking_calls']==1 and 'settimeout'not in timing['stages']
                assert timing['metadata']['max_rx_buffer']<=32 and timing['metadata']['max_pending_tx']<=1
            normal=load(p.parent/('full_frozen'if key=='host_results'else 'normal')/'FRAMES.json')
            assert all(r['output_duplicate_packets']==0 for r in normal)
for result in (checks,back):
    for name,digest in result['source_sha256'].items():
        prefix='main/streaming'if name in ('streaming_client.py','nonblocking_io.py')else 'validation'
        assert sha(ROOT/prefix/name)==digest,name
assert len(checks['checks'])==21 and len(back['cases'])==5
assert all(r['status']=='PASS'for r in checks['checks']+back['cases'])
for r in back['cases']:
    if not r['transfer_success']:assert r['releases']==0 and not(Path(r['raw_directory'])/'JOURNAL.json').exists()
assert len(replay['rows'])==12 and all(r['output_duplicate_packets']==0 for r in replay['rows'])
for r in replay['rows']:
    if r['implementation']=='step03_nonblocking':assert r['settimeout_stage_count']==0 and r['max_rx_buffer']<=32
artifacts=['SOURCE_MANIFEST.json','STEP02_BASELINE.json','STEP02_RECEIPT.json','MODE_COMPARISON.json',
    'NONBLOCKING_CHECKS.json','TRANSFER_BACKPRESSURE.json','REPLAY_COMPARISON.json','EARLY_FIXTURE_ATTEMPT.json',
    'nonblocking_changes.patch','第3步检查说明.md','finalize_step03.py','validation/protocol_edge_regression.json']
artifacts += [str(p.relative_to(ROOT))for p in sorted((ROOT/'validation').glob('*.py'))]
receipt=dict(status='STEP03_COMPLETE_FOR_USER_REVIEW_NOT_RELEASE',changed_functional_files=changed+[new],
    source_identities_verified=True,step01_and_step02_candidates_unchanged=True,paired_release_modified=False,
    mode_results=mode['rows'],scheduler_checks=21,transfer_write_backpressure_checks=5,protocol_edge_checks=6,
    nonblocking_receive_cache_capacity=32,nonblocking_pending_tx_capacity=1,batch_budget_ns=200_000,
    performance_comparison=replay['median_offline_two_frame_wall_ns'],
    relative_offline_wall_change_percent=replay['relative_wall_change_percent'],overall_performance_gain_proven=False,
    scope='INJECTED_MEMORY_TRANSPORT_AND_MODEL_CLOCK_NO_BOARD_OR_REAL_SOCKET',
    real_windows_select_exercised=False,low_perturbation_timing_mode_implemented=False,
    input_window_or_credit_changed=False,cross_frame_prefetch_implemented=False,
    board_io=False,socket_created=False,RTL_changed=False,BIT_generated=False,next_step_started=False,
    early_prefetch_fixture_attempt_preserved=True,artifact_sha256={rel:sha(ROOT/rel)for rel in artifacts})
(ROOT/'FINAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print('STEP03_COMPLETE_FOR_USER_REVIEW; offline suites PASS; no performance gain claimed; live identities unchanged')
