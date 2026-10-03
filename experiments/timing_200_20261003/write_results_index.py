"""Summarize completed evidence without promoting negative timing to acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import argparse

parser = argparse.ArgumentParser(description=__doc__)
state = parser.add_mutually_exclusive_group()
state.add_argument('--paused-for-restart', action='store_true')
state.add_argument('--draining-for-pause', action='store_true')
state.add_argument('--paused-for-user', action='store_true')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'member_b_evidence/timing_200_20261003'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def resources(text):
    result = {}
    for key, label in (('LUT', 'Slice LUTs'), ('FF', 'Slice Registers'),
                       ('RAMB36', 'RAMB36/FIFO'), ('RAMB18', 'RAMB18'),
                       ('DSP', 'DSPs'), ('BUFG', 'BUFGCTRL')):
        match = re.search(r'^\|\s*'+re.escape(label)+r'[^|]*\|\s*(\d+)\s*\|', text, re.M)
        if match:
            result[key] = int(match[1])
    return result

def targets(timing, routed=True):
    ok = (routed and timing['TNS'] == 0 and timing['THS'] == 0 and
          timing['WHS'] >= 0 and timing['WPWS'] >= 0)
    return {str(value): ok and timing['WNS'] >= value for value in (0.1,0.25,0.4)}

completed = []
for name, stage, function_scope in (
    ('postroute_v1_nominal000', 'postroute200_v1_nominal000_20261003_try2',
     'Unchanged V1 RTL; prior V1 full/short simulation reused, no new board evidence.'),
    ('postroute_v1_credit_eco030', 'postroute200_v1_credit_eco030_20261003_try1',
     'Nine audited LUT truth tables plus abstract credit proof; no standalone gate/full-frame simulation of this DCP.'),
    ('postroute_v1_credit_route030', 'postroute200_v1_credit_route030_20261003_try2',
     'Same nine-LUT ECO; only physical continuation. Related behavioral credit model is tested with cached-padding candidate; not gate-level equivalence.'),
    ('postroute_pad_flags030', 'postroute200_v1_pad_flags030_20261003_try1',
     'Same cached-padding/credit-write RTL as the full Golden PASS; physical continuation only, no gate-level or board validation.'),
):
    folder = BASE / name
    manifest = folder / 'result_manifest.json'
    if not manifest.is_file():
        continue
    result = read(manifest)
    final = result['global_timing']['after_restored']
    timing_report = (folder / 'reports/after_restored/timing_summary.rpt').read_text(encoding='utf-8')
    row = re.search(r'WNS\(ns\)[^\n]*\n[^\n]*\n\s*([^\n]+)', timing_report)[1].split()
    routed = result['values']['route_fully_complete']=='1' and result['values']['route_errors_present']=='0'
    completed.append(dict(name=name, stage=stage, evidence=folder.relative_to(ROOT).as_posix(),
        timing=final, failing_setup_endpoints=int(row[2]), resources=resources(
            (folder / 'reports/after_restored/utilization.rpt').read_text(encoding='utf-8')),
        fully_routed=routed, route_errors=int(result['values']['route_errors_present']),
        targets_ns=targets(final,routed), postroute_dcp=result['postroute_hash'],
        baseline_dcp=result['baseline_hash'], function_scope=function_scope))

for name in ('fifo_capacity_nominal', 'pad_flags_setup030', 'rom_pipeline_inc_setup030', 'issue_head_fresh_setup030'):
    folder = BASE / name
    if not (folder / 'summary.json').is_file():
        continue
    result = read(folder / 'summary.json')
    final = {key: result[key] for key in ('WNS','TNS','WHS','THS','WPWS')}
    routed = result['route_errors']==0 and result['routed_nets']==result['routable_nets']
    stage = ROOT / '_synth_bc' / result['stage']
    dcp = stage / 'postroute.dcp'
    import hashlib
    data = dcp.read_bytes()
    completed.append(dict(name=name, stage=result['stage'], evidence=folder.relative_to(ROOT).as_posix(),
        timing=final, failing_setup_endpoints=result['failing_setup_endpoints'],
        resources=result['resources'], fully_routed=routed, route_errors=result['route_errors'],
        targets_ns=targets(final,routed), postroute_dcp=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()),
        function_scope=('Unadopted; independent FIFO and real B short/backpressure pass; no full-frame.' if name=='fifo_capacity_nominal'
                        else 'Three-edge C ROM/stream; actual C shell + real B four-case Golden pass and full-ROM source unit pass. B RTL unchanged from separate B-only full-frame PASS. No full-system/board signoff.' if name=='rom_pipeline_inc_setup030'
                        else 'Direct FIFO-head B sequencer with ROM3; see separately collected unit/C-shell/B-only/full-frame status. No board evidence.' if name=='issue_head_fresh_setup030'
                        else 'Cached-padding/credit-write RTL; see separately collected short and full simulation status. No board evidence.'),
        launch_input_hashes_unchanged=result['launch_input_hashes_unchanged']))

simulations = {}
for name in ('sim_fifo_capacity_short','sim_pad_flags_short','sim_pad_flags_full','sim_rom_pipeline_integration',
             'sim_issue_head_c','sim_issue_head_b_short','sim_issue_head_b_backpressure','sim_issue_head_b_full'):
    path = BASE / name / 'summary.json'
    if path.is_file():
        result = read(path)
        simulations[name] = dict(status=result['status'], variant=result['variant'],
            testbenches={tb:dict(pass_line=data['pass_line'], metrics=data['metrics'])
                         for tb,data in result['testbenches'].items()},
            evidence=path.parent.relative_to(ROOT).as_posix(), boundary=result['validation_boundary'])

unit_manifest = BASE / 'issue_head_unit/manifest.json'
if unit_manifest.is_file():
    unit = read(unit_manifest)
    logfile = next(row['archive'] for row in unit['files'] if row['source'].endswith('/xsim.log'))
    content = (unit_manifest.parent / logfile).read_text(encoding='utf-8')
    pattern = r'ISSUE_HEAD_CASE_PASS id=(\d+) width=(\d+) rounds=(\d+) windows_each=(\d+) samples_each=(\d+) cycles=(\d+) old_stalls=(\d+) new_stalls=(\d+)'
    cases = [dict(zip(('id','width','rounds','windows_each','samples_each','cycles','old_stalls','new_stalls'), map(int,row)))
             for row in re.findall(pattern,content)]
    assert len(cases)==3 and all(row['rounds']==3 for row in cases)
    simulations['issue_head_unit'] = dict(status='PASS', cases=cases,
        evidence=unit_manifest.parent.relative_to(ROOT).as_posix(), boundary=unit['note'],
        cycle_equivalence=False, synthesized_or_routed=False)

unit_manifest = BASE / 'rom_pipeline_unit/manifest.json'
if unit_manifest.is_file():
    unit = read(unit_manifest)
    logfile = next(row['archive'] for row in unit['files'] if row['source'].endswith('/xsim.log'))
    content = (unit_manifest.parent / logfile).read_text(encoding='utf-8')
    pattern = r'ROM_PIPELINE_CASE_PASS id=(\d+) W=(\d+) H=(\d+) frames=(\d+) pixels_each=(\d+) cycles=(\d+) stalls=(\d+) resets=(\d+)'
    cases = [dict(zip(('id','W','H','frames','pixels_each','cycles','stalls','resets'), map(int,row)))
             for row in re.findall(pattern,content)]
    assert len(cases)==4 and all(row['frames']==3 for row in cases)
    simulations['rom_pipeline_unit'] = dict(status='PASS', latency_edges=3, cases=cases,
        evidence=unit_manifest.parent.relative_to(ROOT).as_posix(), boundary=unit['note'],
        connected_real_B_tested=False, synthesized_or_routed=False)

index = dict(schema_version=1, updated_at_utc=datetime.now(timezone.utc).isoformat(),
    task_status=('PAUSED_FOR_USER_RESTART' if args.paused_for_restart else
                 'PAUSED_AT_USER_REQUEST' if args.paused_for_user else
                 'DRAINING_ACTIVE_JOBS_AT_USER_REQUEST' if args.draining_for_pause else 'IN_PROGRESS'),
    branch='member-b-2025-2-bc-trial', target_device='xc7a200tfbg484-2', frequency_MHz=200,
    final_clock=dict(period_ns=5.0,UU_ns=0.0,TSJ_ns=0.071,DJ_ns=0.118,PE_ns=0.0),
    original_V1_nominal=dict(WNS=-0.164,TNS=-7.523,WHS=0.036,THS=0.0,WPWS=1.370,
        failing_setup_endpoints=226,evidence='member_b_evidence/timing_200_20260926/pipeline000',
        dcp_sha256='abe0c41bfda7b06d5dd920094053b56eef17daa02a32d7ebb5c5bfd43e25b1d0'),
    completed_implementations=completed, simulations=simulations,
    best_measured=(max(completed,key=lambda row:row['timing']['WNS'])['name'] if completed else None),
    any_minimum_target_pass=any(row['targets_ns']['0.1'] for row in completed),
    adopted_200MHz_board_release=False,
    board_boundary='Original experimental XDC/DRC severity retained; UART LOC/IOSTANDARD and output delays incomplete. No bitstream/board signoff and no multi-frame PC-video deployment claim.',
    preserved_150MHz_release='6cc8ea4173d2a720f741e80b7cbd9279558ee93a',
    failure_boundary='Query guard failures, unsupported post-route replication, user-app initialization and argv-start failure archived separately; no physical acceptance inferred.',
    evidence_note='Raw-byte SHA256 preserved via new-round-only .gitattributes. Large DCP/simulation caches local only; retain _synth_bc separately for exact reruns. User understanding not established by assistant evidence.')
(BASE / 'results_index.json').write_text(json.dumps(index,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(dict(completed=len(completed),best=index['best_measured'],minimum_pass=index['any_minimum_target_pass']),indent=2))
