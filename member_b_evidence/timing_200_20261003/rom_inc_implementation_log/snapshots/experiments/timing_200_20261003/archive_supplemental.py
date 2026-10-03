"""Archive completed diagnostic/proof or launch-failure evidence, without DCPs."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('kind', choices=('capacity-diagnostic', 'credit-audit-proof',
                                    'route-launch-failure', 'nominal-launch-failure', 'pad-flag-unit',
                                    'capacity-implementation-log', 'pad-implementation-log',
                                    'pad-diagnostic', 'rom-pipeline-unit', 'issue-head-unit',
                                    'rom-inc-implementation-log', 'issue-head-implementation-log',
                                    'rom-inc-diagnostic', 'issue-head-diagnostic'))
args = parser.parse_args()
inputs = []
checkpoints = []
if args.kind in ('rom-inc-implementation-log', 'issue-head-implementation-log',
                 'rom-inc-diagnostic', 'issue-head-diagnostic'):
    import re
    rom = args.kind.startswith('rom-inc-')
    stage_name = ('acc36_realrom_200_member_b_rom_pipeline_inc_20261003_setup030_ascii_ramdecomp_try2'
                  if rom else 'acc36_realrom_200_member_b_issue_head_fresh_20261003_setup030_ascii_ramdecomp_try1')
    stage = ROOT / '_synth_bc' / stage_name
    if args.kind.endswith('-diagnostic'):
        log = stage / 'diagnose_final.log'
        content = log.read_text(encoding='utf-8', errors='replace')
        assert '\nL5_MAC_VALID_TO_WINDOW_FIFO_WE_TIMED_CONE_REMOVED\n' in content
        assert 'INFO: [Common 17-206] Exiting Vivado' in content
        inputs = [stage / 'diagnose_final', log, HERE / 'diagnose.tcl', HERE / 'diagnose_fifo_capacity.tcl']
        note = 'Read-only diagnosis of final restored-UU0 ROM3 ' + ('incremental' if rom else 'direct-head fresh-placement') + ' DCP. No new functional, gate-level or board evidence.'
    else:
        log = ROOT / ('_synth_bc/rom_pipeline_inc_impl_20261003_try2.log' if rom
                      else '_synth_bc/issue_head_fresh_impl_20261003_try1.log')
        content = log.read_text(encoding='utf-8', errors='replace')
        assert '\nMARGIN200_PIPELINE030_COMPLETE\n' in content
        assert 'INFO: [Common 17-206] Exiting Vivado' in content
        assert not re.search(r'^ERROR:', content, re.M)
        runner = HERE / ('synth_rom_pipeline_inc.tcl' if rom else 'synth_issue_head_fresh.tcl')
        inputs = [log, runner, stage / 'reports/launch_source_manifest.json']
        dcp = stage / 'postroute.dcp'
        checkpoints = [dict(path=dcp.relative_to(ROOT).as_posix(), bytes=dcp.stat().st_size,
                            sha256=hashlib.sha256(dcp.read_bytes()).hexdigest())]
        note = 'Completed implementation outer log, launch hashes and local DCP identity. Complements separately collected final timing/resource/routing evidence; completion is not timing acceptance.'
elif args.kind == 'issue-head-unit':
    import re
    log = ROOT / '_synth_bc/issue_head_unit_20261003_try1.log'
    content = log.read_text(encoding='utf-8', errors='replace')
    match = re.search(r'^ISSUE_HEAD_UNIT_COMPLETE log=(.+)$', content, re.M)
    assert match and 'INFO: [Common 17-206] Exiting Vivado' in content
    work = HERE / 'issue_head/unit_work' / Path(match[1].strip()).parent.name
    sim = (work / 'xsim.log').read_text(encoding='utf-8', errors='replace')
    assert sim.count('ISSUE_HEAD_CASE_PASS id=') == 3
    assert 'ISSUE_HEAD_UNIT_PASS cases=3 rounds_each=3' in sim
    assert not re.search(r'fatal:|error:', sim, re.I)
    prepared = HERE / 'issue_head/prepared_manifest.json'
    inputs = [log, prepared]
    for row in json.loads(prepared.read_text(encoding='utf-8')):
        path = ROOT / row['path']
        data = path.read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        inputs.append(path)
    inputs.extend(p for p in work.iterdir() if p.is_file() and p.suffix in ('.log', '.jou'))
    note = 'Direct FIFO-head eight-phase RTL sequencer: widths 1/256/6400, three completed 64-window rounds each, stalls and mid-window reset, old/new accepted output word/phase/last ordering checked. Requires valid/data held until input handshake; input-consumption timing and startup latency differ. Not cycle equivalence, extracted formal proof, gate-level or board acceptance.'
elif args.kind == 'pad-implementation-log':
    stage = ROOT / '_synth_bc/acc36_realrom_200_member_b_pad_flags_20261003_setup030_ascii_ramdecomp'
    log = ROOT / '_synth_bc/pad_flags_impl_20261003_vivado.log'
    content = log.read_text(encoding='utf-8', errors='replace')
    assert '\nMARGIN200_PIPELINE030_COMPLETE\n' in content
    assert 'Exiting Vivado at Sat Oct  3 20:30:32 2026' in content
    inputs = [log, HERE / 'synth_pad_flags.tcl', stage / 'reports/launch_source_manifest.json']
    dcp = stage / 'postroute.dcp'
    checkpoints = [dict(path=dcp.relative_to(ROOT).as_posix(), bytes=dcp.stat().st_size,
                        sha256=hashlib.sha256(dcp.read_bytes()).hexdigest())]
    note = 'Completed padding/credit-memory implementation outer log and DCP hash; complements pad_flags_setup030 reports. Final UU=0 WNS -0.179 ns, TNS -6.939 ns; not timing acceptance.'
elif args.kind == 'pad-diagnostic':
    stage = ROOT / '_synth_bc/postroute200_v1_pad_flags030_20261003_try1'
    log = stage / 'diagnose_final.log'
    content = log.read_text(encoding='utf-8', errors='replace')
    assert '\nL5_MAC_VALID_TO_WINDOW_FIFO_WE_TIMED_CONE_REMOVED\n' in content
    assert 'INFO: [Common 17-206] Exiting Vivado' in content
    inputs = [stage / 'diagnose_final', log, HERE / 'diagnose.tcl', HERE / 'diagnose_fifo_capacity.tcl']
    note = 'Read-only diagnosis of the completed padding post-route finish. Timed MAC-valid to L5 window-FIFO WE cone absent; not functional or formal equivalence.'
elif args.kind == 'rom-pipeline-unit':
    import re
    log = ROOT / '_synth_bc/rom_pipeline_unit_20261003_try1.log'
    content = log.read_text(encoding='utf-8', errors='replace')
    match = re.search(r'^ROM_PIPELINE_UNIT_COMPLETE log=(.+)$', content, re.M)
    assert match and 'INFO: [Common 17-206] Exiting Vivado' in content
    work = HERE / 'rom_pipeline/unit_work' / Path(match[1].strip()).parent.name
    sim = (work / 'xsim.log').read_text(encoding='utf-8', errors='replace')
    assert sim.count('ROM_PIPELINE_CASE_PASS id=') == 4
    assert 'ROM_PIPELINE_UNIT_PASS cases=4 frames_each=3 latency_edges=3' in sim
    assert not re.search(r'fatal:|error:', sim, re.I)
    prepared = HERE / 'rom_pipeline/frozen_manifest.json'
    inputs = [log, prepared]
    for row in json.loads(prepared.read_text(encoding='utf-8'))['inputs']:
        path = ROOT / row['path']
        data = path.read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        inputs.append(path)
    sources = list((ROOT / 'member_b_evidence/real_banks').glob('rom_bank_*.mem'))
    assert len(sources) == 16
    sources.append(ROOT / 'ref/a_full_integer_golden/input_rom_2p19_u8.mem')
    for path in sources:
        assert (work / path.name).read_bytes() == path.read_bytes()
        inputs.append(path)
    inputs.extend(p for p in work.iterdir() if p.is_file() and p.suffix in ('.log', '.jou'))
    note = 'Latency-three C ROM/input-stream RTL unit: four geometries, three completed frames each, two aborted runs/reset, stalls, request/data/coordinate order. Actual 960x540 ROM checked against original A bytes. Not connected real-B, full C system, gate-level or board acceptance.'
elif args.kind == 'capacity-implementation-log':
    log = HERE / 'fifo_capacity/implementation_vivado.log'
    content = log.read_text(encoding='utf-8', errors='replace')
    assert '\nMARGIN200_PIPELINE030_COMPLETE\n' in content
    assert 'Exiting Vivado at Sat Oct  3 18:47:48 2026' in content
    inputs = [log, HERE / 'synth_fifo_capacity.tcl']
    journal = HERE / 'fifo_capacity/implementation_vivado.jou'
    if journal.is_file():
        inputs.append(journal)
    note = 'Completed outer Vivado implementation log of the unadopted capacity-ready candidate; supplements its existing reports and launch-input hashes.'
elif args.kind == 'pad-flag-unit':
    import re
    log = ROOT / '_synth_bc/pad_flags_unit_20261003_try1.log'
    content = log.read_text(errors='replace')
    match = re.search(r'^PAD_FLAG_UNIT_COMPLETE log=(.+)$', content, re.M)
    assert match and 'INFO: [Common 17-206] Exiting Vivado' in content
    work = ROOT / 'experiments/timing_200_20261003/pad_flags/unit_work' / Path(match[1].strip()).parent.name
    sim = (work / 'xsim.log').read_text(errors='replace')
    assert sim.count('PAD_FLAG_CASE_PASS id=') == 4
    assert 'PAD_FLAG_REFERENCE_EQUIVALENCE_PASS cases=4 frames_each=3' in sim
    assert not re.search(r'fatal:|error:', sim, re.I)
    prepared = HERE / 'pad_flags/prepared_manifest.json'
    for row in json.loads(prepared.read_text()):
        path = ROOT / row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
    inputs = [log, prepared, HERE / 'pad_flags/same_pad_raster.sv',
              HERE / 'pad_flags/same_pad_raster_reference.sv', HERE / 'pad_flags/tb_pad_flags.sv',
              HERE / 'pad_flags/run_unit.tcl']
    inputs.extend(p for p in work.iterdir() if p.is_file() and p.suffix in ('.log', '.jou'))
    note = 'Cycle-by-cycle RTL comparison to the unchanged original padding algorithm: four configurations, three frames each, full 960x540 scan plus stalls/resets. Not formal or gate-level equivalence.'
elif args.kind == 'capacity-diagnostic':
    stage = ROOT / '_synth_bc/acc36_realrom_200_member_b_fifo_capacity_20261003_nominal_ascii_ramdecomp'
    inputs = [stage / 'diagnose_final', stage / 'diagnose_final.log',
              HERE / 'diagnose.tcl', HERE / 'diagnose_fifo_capacity.tcl']
    note = 'Read-only DCP diagnosis of the unadopted capacity-ready candidate; not new functional evidence.'
elif args.kind == 'credit-audit-proof':
    inputs = [ROOT / '_synth_bc/eco_capacity_audit_20261003',
              ROOT / '_synth_bc/eco_capacity_audit_20261003_vivado.log',
              HERE / 'fifo_credit_proof.json', HERE / 'prove_fifo_credit.py',
              HERE / 'audit_fifo_luts.tcl']
    note = 'Original LUT/driver audit plus abstract reachable-credit proof; not extracted RTL/netlist formal equivalence.'
else:
    stage_name = ('postroute200_v1_credit_route030_20261003_try1' if args.kind == 'route-launch-failure'
                  else 'postroute200_v1_nominal000_20261003_try1')
    stage = ROOT / '_synth_bc' / stage_name
    log_path = stage / 'vivado.log'
    if args.kind == 'route-launch-failure':
        # The misplaced -log option became a Tcl argument; default root log.
        log_path = ROOT / 'vivado.log'
        assert 'Expected prepared stage and Python executable' in log_path.read_text(errors='replace')
    inputs = [log_path, stage / 'input_manifest.json', stage / 'settings.tcl']
    manifest = json.loads((stage / 'input_manifest.json').read_text(encoding='utf-8'))
    inputs.extend(ROOT / row['path'] for row in manifest['tools'])
    for row in manifest['tools']:
        data = (ROOT / row['path']).read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
    note = ('Vivado argv validation failed before opening DCP; no optimization executed.'
            if args.kind == 'route-launch-failure' else
            'Restricted user-app initialization failed before opening DCP; no optimization executed.')
archive_name = args.kind.replace('-', '_')
if args.kind == 'route-launch-failure':
    archive_name += '_recovered'
out = ROOT / 'member_b_evidence/timing_200_20261003' / archive_name
out.mkdir(parents=True, exist_ok=False)
records = []
for item in inputs + [Path(__file__).resolve()]:
    paths = sorted(p for p in item.rglob('*') if p.is_file()) if item.is_dir() else [item]
    for path in paths:
        assert path.is_file()
        rel = path.relative_to(ROOT).as_posix()
        target = out / 'snapshots' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        target.write_bytes(data)
        assert target.read_bytes() == data and path.read_bytes() == data
        records.append(dict(source=rel, archive=target.relative_to(out).as_posix(),
                            bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
(out / 'manifest.json').write_text(json.dumps(dict(kind=args.kind, note=note, files=records,
                                                  checkpoints=checkpoints), indent=2)+'\n', encoding='utf-8')
(out / 'README.md').write_text('# Supplemental evidence\n\n'+note+'\n', encoding='utf-8')
print(f'SUPPLEMENTAL_ARCHIVED {args.kind} files={len(records)}')
