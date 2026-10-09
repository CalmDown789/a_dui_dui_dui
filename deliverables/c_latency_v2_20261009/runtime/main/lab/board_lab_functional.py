"""Explicit lab-only networking entry; formal video image/permission guards stay intact.

Reuse frozen transport classes only after an independent root lab selection and
real characterization startup evidence are checked. No monkeypatch of a formal
image identity or permission function is used. Raw Golden checks prove bytes;
they do not close electrical or formal project acceptance gates.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, math, sys

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE/'host'))
sys.path.insert(0, str(PACKAGE/'scripts'))
sys.path.insert(0, str(PACKAGE/'diagnostics'))
import lab_diagnostics as diag
diag.stage('LAB_ENTRY_READY')
from board_characterization_identity import verify_candidate, verify_capture
from video_sequence_identity import verify_sequence
from ethernet_video_client import VideoClient, LocalPrecheckError, playback
from ethernet_input_protocol_probe import InputProbe

SCOPE = 'ACX750_ROOT_BOARD_LAB_FUNCTIONAL_SELECTION_V1'
MODES = {'Smoke','Probe','Natural2','Natural16'}
LABEL = 'BOARD_LAB_FUNCTIONAL_OBSERVATIONS_ONLY_NO_ELECTRICAL_OR_FORMAL_ACCEPTANCE'
DCP_SHA = '47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da'
EXPECTED_HOST = {'startup_status_identity.py','capture_video_phy_startup.py','parse_phy_startup_status.py',
    'video_image_identity.py','video_sequence_identity.py','video_protocol.py','ethernet_video_client.py',
    'ethernet_input_protocol_probe.py','audit_input_protocol_probe.py','audit_ethernet_video_run.py'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def bound_file(item):
    if not isinstance(item,dict) or not isinstance(item.get('file'),str) or not item['file']:
        raise ValueError('Missing lab selection file identity')
    rel=Path(item['file']);p=(PACKAGE/rel).resolve()
    if rel.is_absolute() or rel.drive or '..' in rel.parts or not p.is_relative_to(PACKAGE):
        raise ValueError('Lab selection path escapes package')
    expected=item.get('sha256')
    if not isinstance(expected,str) or len(expected)!=64 or any(x not in '0123456789abcdef' for x in expected):
        raise ValueError('Root has not bound a real lowercase SHA256')
    if not p.is_file() or sha(p)!=expected:raise ValueError('Lab selection file changed: '+str(p))
    return p

def selection(mode, capture_report, files_only=False):
    release=PACKAGE/'LAB_FUNCTIONAL_SELECTION.json'
    r=json.loads(release.read_text(encoding='utf-8'))
    if r.get('scope')!=SCOPE or r.get('root_issued_lab_observation_tests') is not True:
        raise ValueError('Independent root lab-only selection required')
    for key in ['physical_IO_signoff','formal_video_permission','complete_stage_acceptance']:
        if r.get(key) is not False:raise ValueError('Lab-only selection must explicitly deny '+key)
    if r.get('electrical_status')!='UNVERIFIED' or set(r.get('allowed_operations',[]))!=MODES:
        raise ValueError('Lab electrical boundary or operation set differs')
    if r.get('source_routed_DCP_sha256')!=DCP_SHA:
        raise ValueError('Different routed candidate selected')
    if r.get('peer')!=['192.168.0.2',5000] or r.get('local')!=['192.168.0.3',6102]:
        raise ValueError('Only the documented isolated PC/FPGA endpoint pair is allowed')
    hosts=r.get('formal_host_sha256')
    if not isinstance(hosts,dict) or set(hosts)!=EXPECTED_HOST:
        raise ValueError('All ten original host/dependency/auditor identities required')
    for n,digest in hosts.items():bound_file({'file':'host/'+n,'sha256':digest})
    labs=r.get('lab_tools_sha256')
    if not isinstance(labs,dict) or set(labs)!={'board_lab_functional.py','run_c_lab_functional.ps1'}:
        raise ValueError('Both independent lab entries must be bound')
    for n,digest in labs.items():bound_file({'file':'lab/'+n,'sha256':digest})
    candidate=bound_file(r.get('characterization_manifest'))
    identity=verify_candidate(candidate,r['characterization_manifest']['sha256'])
    if identity['BIT_sha256']!=r.get('candidate_BIT_sha256'):
        raise ValueError('Root lab selection differs from actual candidate bytes')
    # This proof observes startup identity only and supplies NO formal permission.
    if files_only:
        observed=None
    else:
        if capture_report is None:raise ValueError('Real post-JTAG capture required before every lab network operation')
        observed=verify_capture(identity,capture_report)
    prepared=None;sequence=None;sequence_path=None
    if mode.startswith('Natural'):
        item=r.get('sequence_manifests',{}).get(mode)
        sequence_path=bound_file(item)
        prepared,sequence=verify_sequence(sequence_path)
        if len(prepared)!={'Natural2':2,'Natural16':16}[mode]:
            raise ValueError('Root-selected frame count differs')
    if files_only:
        for name,count in [('Natural2',2),('Natural16',16)]:
            p=bound_file(r.get('sequence_manifests',{}).get(name))
            frames,_=verify_sequence(p)
            if len(frames)!=count:raise ValueError('Root-selected preflight frame count differs')
    return dict(release=r,release_sha256=sha(release),candidate_identity=identity,
        observed_startup=observed,sequence_identity=sequence,sequence_path=sequence_path,
        prepared=prepared,candidate_path=candidate)

def save_scope(out,mode,binding):
    result={'scope':LABEL,'mode':mode,'created_UTC':datetime.now(timezone.utc).isoformat(),
        'physical_IO_signoff':False,'formal_video_permission':False,'complete_stage_acceptance':False,
        'electrical_status':'UNVERIFIED','operator_playback_status':'PENDING',
        'AMD_Artix7_HR_3V3_RGMII_support':'NOT_SUPPORTED_PER_PG160',
        'unconditional_RGMII_compliance':False,'root_lab_selection_sha256':binding['release_sha256'],
        'candidate_identity':binding['candidate_identity'],'observed_startup':binding['observed_startup'],
        'sequence_identity':binding['sequence_identity'],
        'interpretation':'Raw response/Golden checks are local functional observations. This file cannot grant formal or electrical acceptance.'}
    (out/'LAB_OPERATION_SCOPE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=sorted(MODES),required=True)
    p.add_argument('--startup-capture-report',type=Path)
    p.add_argument('--files-only',action='store_true',help='Validate local files only; never UART/JTAG/network')
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=1.)
    p.add_argument('--attempts',type=int,default=3)
    p.add_argument('--frame-timeout',type=float,default=300.)
    a=p.parse_args()
    if not all(math.isfinite(t) and t>0 for t in (a.timeout,a.frame_timeout)) or not 1<=a.attempts<=10:
        p.error('Finite positive deadlines and attempts1..10 required')
    diag.stage('FILE_AND_STARTUP_PRECHECK_BEGIN', mode=a.mode, files_only=a.files_only)
    try:binding=selection(a.mode,a.startup_capture_report,files_only=a.files_only)
    except Exception as exc:
        a.out_dir.mkdir(parents=True,exist_ok=False)
        result={'scope':LABEL,'status':'LAB_SELECTION_FAILED_NO_NETWORK_TRAFFIC','error':repr(exc),
            'success':False,'unique_requests':0,'network_traffic_started':False,
            'physical_IO_signoff':False,'formal_video_permission':False,'complete_stage_acceptance':False}
        (a.out_dir/'LAB_PRECHECK_FAILURE.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'error':result['error']}));return 1
    diag.stage('FILE_AND_STARTUP_PRECHECK_COMPLETE', mode=a.mode, files_only=a.files_only)
    if a.files_only:
        a.out_dir.mkdir(parents=True,exist_ok=False)
        save_scope(a.out_dir,a.mode,binding)
        result={'scope':LABEL,'status':'PASS_LAB_FILES_ONLY_NO_NETWORK_JTAG_UART',
            'network_traffic_started':False,'JTAG_started':False,'UART_opened':False,
            'physical_IO_signoff':False,'complete_stage_acceptance':False}
        (a.out_dir/'LAB_FILE_PRECHECK.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));return 0
    peer=tuple(binding['release']['peer']);local=tuple(binding['release']['local'])
    if a.mode in ('Smoke','Probe'):
        try:client=InputProbe(peer,local,a.out_dir,a.timeout,a.attempts,label=LABEL,image_identity=binding['candidate_identity'])
        except OSError:return 1
        diag.observe_client(client)
        try:
            save_scope(a.out_dir,a.mode,binding)
            client.save('IMAGE_MANIFEST.json',binding['candidate_path'].read_bytes())
            result=client.run(smoke_only=a.mode=='Smoke')
        except Exception as exc:result=client.finish(False,repr(exc))
    else:
        try:client=VideoClient(peer,local,a.out_dir,a.timeout,a.attempts,a.frame_timeout,label=LABEL)
        except LocalPrecheckError:return 1
        diag.observe_client(client)
        actual=[]
        try:
            save_scope(a.out_dir,a.mode,binding)
            client.save('SOURCE_MANIFEST.json',binding['sequence_path'].read_bytes())
            client.save('IMAGE_MANIFEST.json',binding['candidate_path'].read_bytes())
            client.hello()
            for i,(input_data,golden) in enumerate(binding['prepared']):
                actual.append(client.transfer_frame(input_data,golden,i))
            playback(a.out_dir,actual)
            html=a.out_dir/'playback.html'
            html.write_text(html.read_text(encoding='utf-8').replace('</style>',
                '</style>\n<p>工程候选板测观察：电气条件仍待核实。本回放及Golden一致不构成正式阶段验收。</p>',1),encoding='utf-8')
            result=client.close(True)
        except Exception as exc:result=client.close(False,f'{type(exc).__name__}: {exc}')
    print(json.dumps({'scope':LABEL,'mode':a.mode,'raw_operation_status':result['status'],
        'physical_IO_signoff':False,'complete_stage_acceptance':False,'out_dir':str(a.out_dir)}))
    return 0 if result['success'] else 1

if __name__=='__main__':raise SystemExit(main())
