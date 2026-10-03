"""Prepare/verify an isolated routed-DCP experiment; never launch Vivado."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return dict(bytes=path.stat().st_size, sha256=h.hexdigest())


def checked_stage(value):
    stage = Path(value).resolve()
    if stage.parent != (ROOT / '_synth_bc').resolve():
        raise ValueError('Stage must be a direct child of this repository _synth_bc')
    return stage


def verify(stage):
    manifest = json.loads((stage / 'input_manifest.json').read_text(encoding='utf-8'))
    for item in manifest['frozen_inputs']:
        path = stage / item['path']
        if digest(path) != {k: item[k] for k in ('bytes', 'sha256')}:
            raise ValueError(f'Prepared input changed: {item["path"]}')
    for item in manifest['tools']:
        if digest(ROOT / item['path']) != {k: item[k] for k in ('bytes', 'sha256')}:
            raise ValueError(f'Runner changed after preparation: {item["path"]}')
    return manifest


def prepare(args):
    baseline = Path(args.baseline).resolve()
    baseline.relative_to((ROOT / '_synth_bc').resolve())
    if baseline.name != 'postroute.dcp' or not baseline.is_file():
        raise ValueError('Select an existing completed postroute.dcp under _synth_bc')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]+', args.stage):
        raise ValueError('--stage must be a new directory name, without path separators')
    stage = checked_stage(ROOT / '_synth_bc' / args.stage)
    # No cleanup or replacement: an existing stage always refuses preparation.
    stage.mkdir(exist_ok=False)
    input_dir = stage / 'input'
    input_dir.mkdir()
    before = digest(baseline)
    snapshot = input_dir / 'source_postroute.dcp'
    shutil.copyfile(baseline, snapshot)
    if digest(snapshot) != before or digest(baseline) != before:
        raise ValueError('Baseline DCP changed while copying; this stage is incomplete')
    frozen = [dict(path='input/source_postroute.dcp', **before)]
    report_dir = baseline.parent / 'reports'
    required = ['timing_summary_postroute.rpt', 'route_status.rpt',
                'constraints_restored.xdc', 'clocks_postroute.rpt',
                'utilization_postroute.rpt', 'drc_postroute.rpt']
    for name in required:
        if not (report_dir / name).is_file():
            raise ValueError(f'Baseline report missing: {name}')
    original = input_dir / 'baseline_reports'
    original.mkdir()
    for path in sorted(report_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {'.rpt', '.xdc', '.json', '.txt'}:
            target = original / path.name
            shutil.copyfile(path, target)
            frozen.append(dict(path=target.relative_to(stage).as_posix(), **digest(target)))
    settings = stage / 'settings.tcl'
    settings.write_text(f'set finish_extra_setup_ns {float(args.extra_setup):.3f}\n', encoding='ascii')
    frozen.append(dict(path='settings.tcl', **digest(settings)))
    tools = [dict(path=p.relative_to(ROOT).as_posix(), **digest(p))
             for p in (HERE / 'finish.tcl', Path(__file__).resolve())]
    manifest = dict(schema_version=1, state='PREPARED_NOT_RUN',
                    baseline=str(baseline), baseline_hash=before,
                    extra_setup_ns=float(args.extra_setup),
                    frozen_inputs=frozen, tools=tools)
    (stage / 'input_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    verify(stage)
    print(json.dumps(dict(stage=str(stage), status='PREPARED_NOT_RUN',
          vivado_tclargs=[str(stage), sys.executable], baseline_hash=before), indent=2))


def finalize(stage):
    manifest = verify(stage)
    if (stage / 'failed.txt').exists():
        raise ValueError('Failed experiment cannot be finalized')
    result = stage / 'reports/result.txt'
    values = dict(line.split('=', 1) for line in result.read_text(encoding='utf-8').splitlines() if '=' in line)
    if values.get('status') != 'COMPLETED_MEASURED':
        raise ValueError('No completed physical-result marker; cannot finalize')
    if values.get('route_fully_complete') != '1' or values.get('route_errors_present') != '0':
        raise ValueError('Final route is incomplete or erroneous')
    checkpoint = stage / 'postroute.dcp'
    timing = {}
    for label in ('before', 'before_pressure', 'after_physopt_pressure', 'after_pressure', 'after_restored'):
        text = (stage / 'reports' / label / 'timing_summary.rpt').read_text(encoding='utf-8')
        row = re.search(r'WNS\(ns\)[^\n]*\n[^\n]*\n\s*([^\n]+)', text)
        if row is None:
            raise ValueError(f'Cannot parse global timing summary: {label}')
        fields = row[1].split()
        timing[label] = dict(WNS=float(fields[0]), TNS=float(fields[1]),
                             WHS=float(fields[4]), THS=float(fields[5]), WPWS=float(fields[8]))
    final = timing['after_restored']
    timing_ok = final['TNS'] == 0 and final['THS'] == 0 and final['WHS'] >= 0 and final['WPWS'] >= 0
    result_files = []
    for path in sorted((stage / 'reports').rglob('*')):
        if path.is_file():
            result_files.append(dict(path=path.relative_to(stage).as_posix(), **digest(path)))
    summary = dict(status='COMPLETED_MEASURED', baseline_hash=manifest['baseline_hash'],
                   postroute_hash=digest(checkpoint), values=values, reports=result_files,
                   global_timing=timing,
                   timing_targets_ns={str(target): timing_ok and final['WNS'] >= target for target in (0.1, 0.25, 0.4)},
                   note='Completion records an experiment, not timing acceptance or board validation.')
    target = stage / 'result_manifest.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
        stream.write('\n')
    print('POSTROUTE_FINISH_HASHES_VERIFIED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--baseline', required=True)
    prep.add_argument('--stage', required=True)
    prep.add_argument('--extra-setup', choices=('0', '0.000', '0.300', '0.500'), default='0')
    for command in ('verify', 'finalize'):
        sub.add_parser(command).add_argument('stage')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
    elif args.command == 'verify':
        verify(checked_stage(args.stage))
        print('POSTROUTE_FINISH_INPUTS_VERIFIED')
    else:
        finalize(checked_stage(args.stage))


if __name__ == '__main__':
    main()
