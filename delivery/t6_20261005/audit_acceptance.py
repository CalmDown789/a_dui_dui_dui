import csv
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path(__file__).parent
REPORT = Path('C:/t6fix/runs/20261005_100quick01/T6_RESULTS_FINAL.json')
report = json.loads(REPORT.read_text(encoding='utf-8-sig'))
errata=[]
for c in report['combinations']:
    if c['combination']=='150MHz_pause1' and c['cold_power_jtag_idle_reset']['status']=='P04_PASS; AWAITING_P16':
        errata.append({'field':'150MHz_pause1/cold_power_jtag_idle_reset/status','original':'P04_PASS; AWAITING_P16',
                       'corrected':'PASS','reason':'Idle check PASS and independent P16 reset/session PASS are present; this nested label was not finalized.'})
        c['cold_power_jtag_idle_reset']['status']='PASS'
    for s in c['sessions']:
        if c['combination']=='150MHz_pause1' and s['case']=='P04':
            old=str(Path(s['vio_raw_csv']).parent/'post_session_command.json')
            new=str(Path(s['vio_raw_csv']).parent/'controller_command.json')
            if old in s['complete_logs']:
                s['complete_logs']=[new if p==old else p for p in s['complete_logs']]
                errata.append({'field':'150MHz_pause1/P04/complete_logs','original':old,'corrected':new,
                               'reason':'VIO/ILA exports were performed by the coordinated controller; its receipt is controller_command.json.'})
        if c['combination']=='100MHz_pause1' and s['case']=='P04':
            old=str(Path(s['vio_raw_csv']).parent/'observation_retry01.log')
            new=str(Path(s['vio_raw_csv']).parent/'controller.log')
            if old in s['complete_logs']:
                s['complete_logs']=[new if p==old else p for p in s['complete_logs']]
                errata.append({'field':'100MHz_pause1/P04/complete_logs','original':old,'corrected':new,
                               'reason':'The coordinated controller performed VIO/ILA export; the combined report carried a nonexistent retry log name.'})
report['acceptance_index_errata']=errata
now = datetime.now(timezone(timedelta(hours=8))).isoformat()
def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(p):
    p = Path(p)
    assert p.is_file(), f'Missing evidence: {p}'
    return {'path':str(p), 'bytes':p.stat().st_size, 'sha256':sha(p)}
def ila_check(item):
    native = item.get('native') or item.get('native_ila')
    assert native, item
    check(native)
    path = item['csv']
    check(path)
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))[1:]
    assert len(rows) == 1024, (path,len(rows))
    assert all(int(r['dbg_obs_snapshot_overflow'],16)==0 for r in rows), path
    signal = item.get('expected_signal')
    if not signal and 'forced' in item.get('type',''): signal='dbg_obs_pause_forced_block'
    if not signal and 'done' in item.get('type',''): signal='dbg_frame_done'
    high = sum(int(r[signal],16)>0 for r in rows) if signal else None
    if signal: assert high > 0, (path,signal)
    return {'csv':path,'native':native,'samples':len(rows),'overflow_high_samples':0,'trigger_signal':signal,'signal_high_samples':high}

audit = {'created_at':now,'status':'PASS','delivery_commit':report['delivery_commit'],
         'scope':'T6 four-combination board acceptance only', 'natural_video_acceptance':'NOT_RUN',
         '200MHz':'PAUSED','raw_artifact_location':'LOCAL_ONLY_NOT_UPLOADED_TO_GITHUB','combinations':[]}
audit['execution_report_errata']=errata
all_paths = {REPORT}
for c in sorted(report['combinations'],key=lambda c:(c['freq_MHz'],c['pause'])):
    assert c['T6']=='PASS' and c['delivery_status']=='BOARD_PASS'
    ca={'combination':c['combination'],'T6':'PASS','status':'BOARD_PASS','attempt':c['selected_pass_attempt'],
        'images':[],'sessions':[],'nominal_WNS_ns':c['nominal_WNS_ns_offline'],
        'pressure_WNS_ns':c.get('pressure_WNS_ns_offline'),'source_build':c.get('build_attempt')}
    for im in c['expected_images']:
        actual=check(im['path'])
        assert actual['sha256']==im['expected_sha256']==im['actual_sha256_at_programming'], im
        assert actual['bytes']==im['expected_bytes']
        ca['images'].append(actual);all_paths.add(Path(im['path']))
    program=c['actual_program_records'][0]
    ca['program_log']=check(program['vivado_log'])
    ca['JTAG_identity']=c['actual_device_identity']
    assert c['cold_power_jtag_idle_reset']['status']=='PASS'
    ca['cold_power_jtag_idle_reset']=c['cold_power_jtag_idle_reset']
    for s in c['sessions']:
        assert s['status']=='PASS' and not s.get('missing_evidence')
        n=s['required_frame_count']
        capture=load(s['capture_session_json'])
        assert capture['status']=='PASS_BIT_EXACT' and capture['frame_count']==n
        assert capture['nominal_baud']==921600 and '8N1' in capture['uart_format']
        frames=[]
        for i,f in enumerate(capture['frames']):
            assert f['frame_id']==i and f['bit_exact'] and f['mismatch_bytes']==0
            inp,out,gold=map(Path,(f['input_path'],f['output_path'],f['expected_path']))
            assert inp.stat().st_size==518400 and out.stat().st_size==gold.stat().st_size==2073600
            assert out.read_bytes()==gold.read_bytes(), out
            assert sha(inp)==f['input_sha256'] and sha(out)==f['output_sha256']==f['expected_sha256']==sha(gold)
            frames.append({'frame_id':i,'input':check(inp),'golden':check(gold),'UART':check(out),'mismatch_bytes':0})
            all_paths.update((inp,out,gold))
        assert len({f['input']['sha256'] for f in frames})==4
        decoded=load(s['decoded_31_fields_json'])
        records=decoded['records'];assert len(records)==16
        valid=[r for r in records if r['selected_valid']==1]
        assert len(valid)==n and s['actual_snapshot_count']==n and not s['actual_snapshot_overflow']
        pauses=[]
        expected={'valid':1,'frame_start_seen':1,'core_busy_at_session_done':0,'core_done_seen':1,
                  'session_done':1,'uart_final_idle':1,'input_accept_count':518400,'output_accept_count':2073600,
                  'stripe_last_accept_count':17,'frame_last_accept_count':1,'uart_bytes_delta':2073600,
                  'core_proto_error':0,'core_overflow_error':0,'loader_protocol_error':0,'loader_frame_error_count':0,
                  'uart_framing_error_count':0,'c2b_hold_violation_count':0,'b_output_hold_violation_count':0,
                  'pause_active_at_done':0}
        for i,r in enumerate(valid):
            f=r['fields'];assert len(f)==31 and r['snapshot_count']==n
            assert r['slot']==f['slot_index']==f['frame_id']==i
            for k,v in expected.items():assert f[k]==v,(c['combination'],s['case'],i,k,f[k],v)
            if c['pause']==1 and n==4:
                assert f['pause_request_cycles']>0 and f['pause_forced_block_cycles']>0
                pauses.append({k:f[k] for k in ('frame_id','pause_request_cycles','pause_forced_block_cycles')})
        check(s['vio_raw_csv']);check(s['decoded_31_fields_json'])
        assert load(s['field_checks_json'])['status'].startswith('PASS')
        reset=s['reset_event'];assert reset['S0_user_confirmed']
        check(reset['baseline_check']);check(reset['physical_events'])
        assert load(reset['baseline_check'])['status'].startswith('PASS')
        check(s['complete_command_record'])
        for p in s['complete_logs']:check(p)
        ilas=[ila_check(i) for i in s['ila_exports']]
        if pauses: assert len(ilas)>=8
        ca['sessions'].append({'case':s['case'],'status':'PASS','session_id':s['actual_session_id'],
            'frames':frames,'snapshot_count':n,'decoded_fields_per_record':31,'overflow':0,
            'reset':reset,'vio_raw_csv':s['vio_raw_csv'],'decoded_json':s['decoded_31_fields_json'],
            'field_checks_json':s['field_checks_json'],'ILA':ilas,'pause_counts':pauses})
    attempt=Path(c['sessions'][0]['reset_event']['physical_events']).parent
    all_paths.update(p for p in attempt.rglob('*') if p.is_file())
    ca['evidence_root']=str(attempt)
    audit['combinations'].append(ca)

audit['total_byte_exact_frames']=sum(len(s['frames']) for c in audit['combinations'] for s in c['sessions'])
audit['controlled_pause_frames']=sum(len(s['pause_counts']) for c in audit['combinations'] for s in c['sessions'])
audit['record_limitations']=['Physical label check was operator-confirmed; exact printed label and button press/release times were not transcribed.',
    'The old 150MHz pause0 manifest predates a physical_events.json update; 150MHz pause1 lacks a standalone old file manifest. A fresh acceptance-wide file index is supplied, with old records preserved.',
    'Three accepted BIT images are local C-overlay rebuilds, not the corresponding original T5 ZIP BIT images.']
provenance=Path('C:/t6fix/analysis/integrated01/SOURCE_PROVENANCE.json')
audit['source_provenance']=load(provenance)
for p in Path('C:/t6fix/analysis/integrated01').glob('*'):
    if p.is_file():all_paths.add(p)
for c in audit['combinations']:
    build=c['source_build']
    if build:
        root=Path('C:/t6fix/sourcekit/impl')/build
        all_paths.update(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() not in ('.dcp','.bit','.ltx'))
for p in [Path('C:/t6fix/sourcekit/candidate/multiframe/rtl/c_core.v'),Path('C:/t6fix/sourcekit/candidate/multiframe/tb/tb_c_controlled_pause.v')]:
    all_paths.add(p)
for p in Path('C:/t6c/data').glob('*manifest*'):all_paths.add(p)
manifest={'created_at':now,'status':'CURRENT_FILES_HASHED','files':[check(p) for p in sorted(all_paths)]}
manifest['file_count']=len(manifest['files'])
manifest['bytes']=sum(f['bytes'] for f in manifest['files'])
def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
write('T6_ACCEPTANCE_AUDIT.json',audit)
write('T6_EVIDENCE_MANIFEST.json',manifest)
write('T6_EXECUTION_REPORT.json',report)
for p in [provenance,Path('C:/t6fix/analysis/integrated01/c_core.v.patch'),Path('C:/t6fix/analysis/integrated01/tb_c_controlled_pause.v.patch')]:shutil.copy2(p,OUT/p.name)
with zipfile.ZipFile(OUT/'T6_EVIDENCE_20261005.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(all_paths):z.write(p,str(p.relative_to(Path('C:/'))).replace('\\','/'))
    for name in ('T6_ACCEPTANCE_AUDIT.json','T6_EVIDENCE_MANIFEST.json'):
        z.write(OUT/name,'acceptance/'+name)
write('T6_EVIDENCE_ARCHIVE.json',check(OUT/'T6_EVIDENCE_20261005.zip'))
print(json.dumps({'status':audit['status'],'frames':audit['total_byte_exact_frames'],'pause_frames':audit['controlled_pause_frames'],'files':manifest['file_count'],'archive':check(OUT/'T6_EVIDENCE_20261005.zip')},ensure_ascii=False))
