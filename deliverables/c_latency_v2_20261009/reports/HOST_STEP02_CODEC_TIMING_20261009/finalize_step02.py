"""Verify source identities and gather the offline-only step 2 review receipt."""
from pathlib import Path
import ast, hashlib, json, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
LIVE = Path(r'C:\t6dup09\main')
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):
    return json.loads(p.read_text(encoding='utf-8'))
manifest = load(ROOT/'SOURCE_MANIFEST.json')
for row in manifest['files']:
    assert sha(Path(row['source'])) == row['baseline_sha256'], row['file']
    assert sha(ROOT/'baseline'/row['file']) == row['baseline_sha256'], row['file']
    assert sha(ROOT/'main'/row['file']) == row['candidate_sha256'], row['file']
    for prefix in ('baseline','main'):
        ast.parse((ROOT/prefix/row['file']).read_text(encoding='utf-8'))
for row in manifest['test_assets']:
    assert sha(Path(row['source'])) == row['sha256']
    assert sha(ROOT/'main/data'/row['file']) == row['sha256']
assert sha(ROOT/'main/data/ETHERNET_SEQUENCE_MANIFEST.json') == sha(LIVE/'data/ETHERNET_SEQUENCE_MANIFEST.json')
for rel, digest in manifest['unchanged_release_identities'].items():
    assert sha(LIVE/rel) == digest, rel
step1=WORK/'output/RTL_STEP01_RETRY_20261009/rtl/evf2_result_window.sv'
assert sha(step1) == manifest['step01_candidate_sha256']
supplement=Path(r'C:\t6dup09\pc4k\SUPPLEMENT_MANIFEST.json')
assert sha(supplement)=='6c8edf91e8599e13b574443558225c8edbf8399dbe4ab110cfa128f502098cd4'
changed=[r['file'] for r in manifest['files'] if r['baseline_sha256']!=r['candidate_sha256']]
assert changed==manifest['changed_functional_files']
codec=load(ROOT/'CODEC_CHECKS.json');timing=load(ROOT/'TIMING_CHECKS.json')
fixture=load(ROOT/'FIXTURE_CHECKS.json');edge=load(ROOT/'validation/protocol_edge_regression.json')
host_dir=Path(load(ROOT/'validation/LATEST_host.json')['saved_directory'])
host=load(host_dir/'RESULTS.json')
window_run=load(ROOT/'WINDOW128_RUN.json');window_dir=Path(window_run['saved_directory'])
window=load(window_dir/'RESULTS.json')
for result in (codec,timing,fixture,edge,host,window_run,window):
    assert result['status']=='PASS'
assert len(host['fault_cases'])==26 and len(window['rows'])==7
assert all(r['status']=='PASS' for r in host['fault_cases']+window['rows'])
for result in (host,window,edge):
    for name,digest in result['source_sha256'].items():
        p=(ROOT/'main/host'/name if name=='video_protocol.py' else
           ROOT/'main/proof'/name if name in ('host_regression.py','check_host_window128.py') else
           ROOT/'main/streaming'/name)
        assert sha(p)==digest, name
assert sha(ROOT/'validation/window128_adapted.py')==window_run['executed_harness_sha256']
assert sha(ROOT/'validation/host_regression_adapted.py')==window_run['injected_peer_harness_sha256']
for r in host['fault_cases']:
    if not r['expected_transfer_success']:
        assert r['frame_releases']==0 and not (host_dir/r['fault']/'JOURNAL.json').exists()
assert host['full_frozen_audit']['golden_bytes']==4147200
for r in window['rows']:
    assert r['releases']==2 and r['max_input_retained']<=16 and r['max_inbox']<=128
    assert r['raw_audit']['golden_bytes']==4147200
    assert (window_dir/r['fault']/'JOURNAL.json').is_file()
reports=['SOURCE_MANIFEST.json','CODEC_CHECKS.json','TIMING_CHECKS.json','FIXTURE_CHECKS.json',
         'FAILED_ATTEMPTS.json','WINDOW128_RUN.json','host_changes.patch','check_step02.py',
         'prepare_step02.py','finalize_step02.py','第2步检查说明.md']
reports += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'validation').glob('*.py'))]
reports += ['validation/protocol_edge_regression.json']
receipt=dict(status='STEP02_COMPLETE_FOR_USER_REVIEW_NOT_RELEASE',
    changed_functional_files=changed,source_and_baseline_identities_verified=True,
    live_package_identity_unchanged=True,step01_candidate_unchanged=True,
    original_journal_records_compared=codec['original_valid_records_equal'],
    mutation_boundary_cases=codec['mutated_and_boundary_cases'],timing_matrix_cases=len(timing['topk_matrix']),
    host_fault_cases=26,host_results=str(host_dir/'RESULTS.json'),
    window128_full_two_frame_cases=7,window128_results=str(window_dir/'RESULTS.json'),
    protocol_edge_checks=len(edge['checks']),golden_bytes_per_two_frame_case=4147200,
    decode_microbenchmark_time_reduction_percent=codec['decode_time_reduction_percent'],
    performance_scope='LOCAL_DECODE_MICROBENCHMARK_NOT_END_TO_END_FPS',
    failed_fixture_attempt_preserved=True,paired_release_modified=False,
    board_io=False,socket_created=False,RTL_changed=False,BIT_generated=False,
    nonblocking_receive_loop_implemented=False,low_perturbation_timing_mode_implemented=False,
    input_window_or_credit_changed=False,cross_frame_prefetch_implemented=False,
    next_step_started=False,artifact_sha256={rel:sha(ROOT/rel) for rel in reports},
    executed_host_results_sha256=sha(host_dir/'RESULTS.json'),
    executed_window128_results_sha256=sha(window_dir/'RESULTS.json'))
(ROOT/'FINAL_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('STEP02_COMPLETE_FOR_USER_REVIEW; two host files changed; offline checks PASS; live identities unchanged')
