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
                                    'capacity-implementation-log'))
args = parser.parse_args()
inputs = []
if args.kind == 'capacity-implementation-log':
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
(out / 'manifest.json').write_text(json.dumps(dict(kind=args.kind, note=note, files=records), indent=2)+'\n', encoding='utf-8')
(out / 'README.md').write_text('# Supplemental evidence\n\n'+note+'\n', encoding='utf-8')
print(f'SUPPLEMENTAL_ARCHIVED {args.kind} files={len(records)}')
