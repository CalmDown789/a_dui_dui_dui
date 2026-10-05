"""Independently check received raw evidence; never execute archive-supplied code."""
from pathlib import Path, PureWindowsPath
from datetime import datetime, timezone, timedelta
import csv, hashlib, importlib.util, io, json, zipfile

ROOT = Path(__file__).resolve().parent
WORK = Path('F:/FPGA预选')
ARCHIVE = ROOT / 'T6_EVIDENCE_20261005.zip'
REPORTS = ROOT / 'reports/delivery/t6_20261005'
EXPECTED = '54a00085a31d641e5aadecd22b97742ab2119ee9baf806cfe05752cb73c19949'
def sha(b): return hashlib.sha256(b).hexdigest()
def local(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def member(p):
    p = PureWindowsPath(p)
    assert p.drive.lower() == 'c:', p
    return '/'.join(p.parts[1:])

spec = importlib.util.spec_from_file_location('our_decoder', WORK/'c_obs_fix_20261005/scripts/decode_snapshots.py')
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
mapping = local(WORK/'c_obs_fix_20261005/contracts/signal_map.json')
execution = local(REPORTS/'T6_EXECUTION_REPORT.json')
status = local(REPORTS/'T6_STATUS.json')
provenance = local(REPORTS/'SOURCE_PROVENANCE.json')
assert ARCHIVE.stat().st_size == 206066607 and sha(ARCHIVE.read_bytes()) == EXPECTED
result = {'status':'PASS', 'scope':'Independent raw-evidence audit, not a new board run',
    'checked_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'C_commit':'2e185be7308190a7c83dfee787bc7fca25a9ff0e',
    'archive':{'path':str(ARCHIVE),'bytes':ARCHIVE.stat().st_size,'sha256':EXPECTED},
    'combinations':[], 'natural_video':'NOT_RUN', '200MHz':'PAUSED',
    'physical_event_limit':'Cold-power and button actions remain operator-confirmed; raw idle state is verified'}

with zipfile.ZipFile(ARCHIVE) as z:
    names=z.namelist()
    assert len(names)==len(set(names))==892
    assert all(not n.startswith(('/', '\\')) and '..' not in n.split('/') for n in names)
    def raw(p): return z.read(member(p))
    def jread(p): return json.loads(raw(p).decode('utf-8-sig'))
    def text(p): return raw(p).decode('utf-8-sig').replace('\r\r\n','\n').replace('\r\n','\n')
    def rows(p): return list(csv.DictReader(io.StringIO(text(p),newline=None)))
    def vio(p): return [decoder.decode(r,mapping) for r in rows(p)]
    mb=z.read('acceptance/T6_EVIDENCE_MANIFEST.json')
    ab=z.read('acceptance/T6_ACCEPTANCE_AUDIT.json')
    assert mb==(REPORTS/'T6_EVIDENCE_MANIFEST.json').read_bytes()
    assert ab==(REPORTS/'T6_ACCEPTANCE_AUDIT.json').read_bytes()
    manifest=json.loads(mb.decode('utf-8-sig'));accepted_audit=json.loads(ab.decode('utf-8-sig'))
    files={f['path']:f for f in manifest['files']}
    assert len(files)==manifest['file_count']==890
    assert set(names)=={member(p) for p in files}|{'acceptance/T6_EVIDENCE_MANIFEST.json','acceptance/T6_ACCEPTANCE_AUDIT.json'}
    checked_bytes=0
    for f in manifest['files']:
        b=raw(f['path']) # read also verifies ZIP CRC
        assert len(b)==f['bytes'] and sha(b)==f['sha256'],f['path']
        checked_bytes+=len(b)
    assert checked_bytes==manifest['bytes']
    result['archive_verification']={'CRC_members':892,'SHA_length_data_files':890,'data_bytes':checked_bytes,'Git_manifest_binding':True}
    print('Archive CRC, 890 file SHA/length and Git binding: PASS',flush=True)
    expected_fields={'valid':1,'frame_start_seen':1,'core_busy_at_session_done':0,'core_done_seen':1,
        'session_done':1,'uart_final_idle':1,'input_accept_count':518400,'output_accept_count':2073600,
        'stripe_last_accept_count':17,'frame_last_accept_count':1,'uart_bytes_delta':2073600,
        'core_proto_error':0,'core_overflow_error':0,'loader_protocol_error':0,'loader_frame_error_count':0,
        'uart_framing_error_count':0,'c2b_hold_violation_count':0,'b_output_hold_violation_count':0,'pause_active_at_done':0}
    nf=np=ni=nv=0
    for c in sorted(execution['combinations'],key=lambda x:(x['freq_MHz'],x['pause'])):
        assert c['T6']=='PASS' and c['delivery_status']=='BOARD_PASS'
        sc=next(s for s in status['combinations'] if s['combination']==c['combination'])
        ca={'combination':c['combination'],'status':'BOARD_PASS','sessions':[],'images':[],'missing_required_raw':[]}
        def available(p):
            if member(p) in names: return True
            if p not in ca['missing_required_raw']: ca['missing_required_raw'].append(p)
            return False
        ac=next(a for a in accepted_audit['combinations'] if a['combination']==c['combination'])
        for im in c['expected_images']:
            b=raw(im['path'])
            assert len(b)==im['expected_bytes']
            assert sha(b)==im['expected_sha256']==im['actual_sha256_at_programming']
            assert sha(b) in [s['sha256'] for s in sc['images']]
            ca['images'].append({'name':PureWindowsPath(im['path']).name,'bytes':len(b),'sha256':sha(b),'archive_member':member(im['path'])})
        for p in c['actual_program_records']:
            for key in ['program_tcl','vivado_log','vivado_journal','command_receipt']:
                available(p[key])
            if available(p['program_tcl']) and available(p['vivado_log']):
                program,log=text(p['program_tcl']),text(p['vivado_log'])
                assert all(PureWindowsPath(im['path']).name in program for im in c['expected_images'])
                assert 'program_hw_devices' in log and 'xc7a200t' in log.lower()
                assert 'u_obs_ila' in log and 'u_obs_vio' in log
            ca['JTAG_device']=p['device_name'];ca['JTAG_IDCODE']=p['idcode_hex']
        cold=c['cold_power_jtag_idle_reset']
        idle_check_path=cold.get('idle_check') or cold['P04_idle_check']
        ca['idle_raw_verified']=False
        if available(idle_check_path):
            idle_check=jread(idle_check_path)
            idle_csv=cold.get('idle_csv') or idle_check['vio']['csv']
            if available(idle_csv):
                idle=vio(idle_csv)
                assert len(idle)==16 and all(r['selected_valid']==0 and r['snapshot_count']==0 for r in idle)
                assert idle_check['status'].startswith('PASS')
                ca['idle_raw_verified']=True
        elif cold.get('idle_csv'): available(cold['idle_csv'])
        for s in c['sessions']:
            n=s['required_frame_count']
            if available(s['capture_session_json']):
                capture=jread(s['capture_session_json'])
                assert capture['frame_count']==n and capture['status']=='PASS_BIT_EXACT'
                assert capture['nominal_baud']==921600 and '8N1' in capture['uart_format']
            else:
                audit_session=next(x for x in ac['sessions'] if x['case']==s['case'])
                capture={'frames':[dict(frame_id=f['frame_id'],input_path=f['input']['path'],output_path=f['UART']['path'],
                    expected_path=f['golden']['path'],input_sha256=f['input']['sha256'],output_sha256=f['UART']['sha256'],
                    expected_sha256=f['golden']['sha256']) for f in audit_session['frames']]}
            fc=[]
            for i,f in enumerate(capture['frames']):
                inp,act,gold=map(raw,(f['input_path'],f['output_path'],f['expected_path']))
                assert f['frame_id']==i and len(inp)==518400 and len(act)==len(gold)==2073600
                assert act==gold,(c['combination'],s['case'],i)
                assert sha(inp)==f['input_sha256'] and sha(act)==f['output_sha256']==f['expected_sha256']==sha(gold)
                fc.append({'frame_id':i,'input_sha256':sha(inp),'UART_sha256':sha(act),'mismatch_bytes':0})
            assert len(fc)==n and len({f['input_sha256'] for f in fc})==4
            observed=[]
            has_vio=available(s['vio_raw_csv']);has_decoded=available(s['decoded_31_fields_json'])
            if has_vio and has_decoded:
                observed=vio(s['vio_raw_csv']);claimed=jread(s['decoded_31_fields_json'])['records']
                assert observed==claimed,(c['combination'],s['case'],'raw VIO decode mismatch')
                assert len(observed)==16 and all(r['snapshot_count']==n for r in observed)
            valid=[r for r in observed if r['selected_valid']==1]
            if observed: assert len(valid)==n
            pauses=[]
            for i,r in enumerate(valid):
                f=r['fields'];assert r['slot']==f['slot_index']==f['frame_id']==i and len(f)==31
                for k,v in expected_fields.items(): assert f[k]==v,(c['combination'],s['case'],i,k)
                if c['pause']==1 and n==4:
                    assert f['pause_request_cycles']>0 and f['pause_forced_block_cycles']>0
                    pauses.append({k:f[k] for k in ['frame_id','pause_request_cycles','pause_forced_block_cycles']})
                if c['pause']==0: assert f['pause_request_cycles']==f['pause_forced_block_cycles']==0
            if available(s['field_checks_json']): assert jread(s['field_checks_json'])['status'].startswith('PASS')
            assert s['reset_event']['S0_user_confirmed']
            if available(s['reset_event']['baseline_check']): assert jread(s['reset_event']['baseline_check'])['status'].startswith('PASS')
            for p in s['complete_logs']: available(p)
            available(s['complete_command_record'])
            ila=[]
            for item in s['ila_exports']:
                has_native=available(item.get('native') or item.get('native_ila'));has_csv=available(item['csv'])
                if not has_native or not has_csv: continue
                assert raw(item.get('native') or item.get('native_ila'))
                rr=rows(item['csv'])[1:] # Vivado first data row states radices
                assert len(rr)==1024 and all(int(r['dbg_obs_snapshot_overflow'],16)==0 for r in rr)
                signal=item.get('expected_signal')
                if not signal and 'forced' in item.get('type',''): signal='dbg_obs_pause_forced_block'
                if not signal and 'done' in item.get('type',''): signal='dbg_frame_done'
                high=sum(int(r[signal],16)!=0 for r in rr) if signal else None
                if signal: assert high>0
                ila.append({'csv':item['csv'],'samples':1024,'signal':signal,'high_samples':high})
            if pauses: assert len(ila)>=8
            ni+=len(ila);nv+=len(observed);nf+=n;np+=len(pauses)
            ca['sessions'].append({'case':s['case'],'frames':n,'UART_bit_exact':True,'VIO_raw_redecoded':bool(observed),
                'snapshot_count':n,'frame_checks':fc,'pause_checks':pauses,'ILA':ila})
        assert sorted(s['frames'] for s in ca['sessions'])==[4,16]
        build=c.get('build_attempt')
        if build:
            prefix=f'C:/t6fix/sourcekit/impl/{build}'
            frozen=jread(prefix+'/frozen_inputs.json');sm=jread(prefix+'/stage6_build_manifest.json')
            hashes={f['path']:f['sha256'] for f in sm['inputs']};bc=0;optional_dcp=[]
            assert sm['fixed_B']==provenance['fixed_B_commit']
            for f in frozen:
                if f['copy'].lower().endswith('.dcp'):
                    optional_dcp.append({'path':f['copy'],'sha256':f['sha256'],'verification':'Recorded only; optional DCP excluded by C archive contract'})
                    continue
                assert sha(raw(f['copy']))==f['sha256']==hashes[f['source']]
                rel=member(f['source']).split('/sourcekit/',1)[1]
                if rel.startswith('b_fixed/'):
                    assert sha((WORK/'c_obs_fix_20261005'/rel).read_bytes())==f['sha256'];bc+=1
                if rel=='candidate/multiframe/rtl/c_core.v': assert f['sha256']==provenance['local_c_core_sha256']
                if rel=='candidate/multiframe/constr/c_top.xdc': assert sha((WORK/'c_obs_fix_20261005'/rel).read_bytes())==f['sha256']
            impl=jread(prefix+'/implementation_result.json')
            assert impl['status']=='IMPLEMENTATION_PASS' and all(impl['gates'].values())
            assert impl['nominal']['WNS']==c['nominal_WNS_ns_offline']
            assert impl['nominal']['TNS']==impl['nominal']['THS']==impl['nominal']['TPWS']==0
            assert min(impl['nominal'][k] for k in ['WNS','WHS','WPWS'])>=0
            assert impl['route']['fully_routed']==impl['route']['routable'] and impl['route']['errors']==0
            for rpt in impl['reports']: assert sha(raw(prefix+'/reports/'+rpt['name']))==rpt['sha256']
            ready=jread(prefix+'/board_ready.json')
            assert ready['source_postroute_sha256']==impl['dcp']['sha256']
            assert {im['sha256'] for im in ready['artifacts']}=={im['sha256'] for im in ca['images']}
            ca['build']={'name':build,'frozen_non_DCP_inputs_verified':len(frozen)-len(optional_dcp),'optional_DCP_inputs':optional_dcp,
                'fixed_B_inputs':bc,'nominal':impl['nominal'],'pressure':impl['pressure'],'DCP_not_in_archive':True}
        else: ca['build']={'name':'original T5 100MHz_pause0','previous_offline_gates_reused':True}
        if ca['missing_required_raw']: ca['status']='BOARD_PASS_REPORTED_RAW_AUDIT_INCOMPLETE'
        result['combinations'].append(ca)
        print(c['combination'],ca['status'],f"20 UART frames, missing {len(ca['missing_required_raw'])} required raw files",flush=True)
    assert nf==80
    result.update({'UART_frames_compared':nf,'effective_pause_frames':np,'VIO_slots_redecoded':nv,'ILA_exports_checked':ni})
    for overlay in provenance['local_overlay_changes']:
        assert sha(raw('C:/t6fix/sourcekit/'+overlay['path']))==overlay['candidate_sha256']

if any(c['missing_required_raw'] for c in result['combinations']): result['status']='PARTIAL_PASS_MISSING_C_ARCHIVE_MEMBERS'
(ROOT/'RAW_ACCEPTANCE_VERIFICATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('T6 independent raw acceptance:',result['status'],'Natural-video playback: NOT_RUN.',flush=True)
