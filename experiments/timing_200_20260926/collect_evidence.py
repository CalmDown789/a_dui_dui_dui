"""Archive one completed 200 MHz run and its exact input hashes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('name')
parser.add_argument('stage', help='Directory name below _synth_bc')
parser.add_argument('script', help='Repository-relative runner')
parser.add_argument('--check-only', action='store_true', help='Validate and print without writing evidence')
args = parser.parse_args()
source = ROOT / '_synth_bc' / args.stage / 'reports'
dest = ROOT / 'member_b_evidence/timing_200_20260926' / args.name

def read(name):
    return (source / name).read_text(encoding='utf-8')

def timing(text):
    row = re.search(r'WNS\(ns\)[^\n]*\n[^\n]*\n\s*([^\n]+)', text).group(1).split()
    return dict(WNS=float(row[0]), TNS=float(row[1]), failing_setup_endpoints=int(row[2]),
                WHS=float(row[4]), THS=float(row[5]), WPWS=float(row[8]))

def repo_path(value):
    """Resolve both the V: ASCII alias used by Vivado and native paths."""
    value = value.strip().replace('\\', '/')
    if value[:3].lower() == 'v:/':
        value = value[3:].lstrip('/')
    result = (ROOT / value).resolve()
    result.relative_to(ROOT.resolve())
    return result

runner = repo_path(args.script)
result_text = read('bc_real_synth_result.txt')
status = re.search(r'^\s*12\s+implementation\s*:\s*(\S+)', result_text, re.M)
assert status and status[1] == 'COMPLETED', 'Implementation has not completed'
assert re.search(r'^\s*VERDICT\s*:\s*OK\s*$', result_text, re.M), 'Real B hierarchy check missing'
assert re.search(r'^\s*8\s+clock\s*:.*->\s*200\s*MHz', result_text, re.M), 'Result is not for 200 MHz'
config = {}
if (source / 'run_config.txt').exists():
    config = dict(line.split('=', 1) for line in read('run_config.txt').splitlines() if '=' in line)
    assert repo_path(config['script']) == runner, 'Runner argument does not match measured run_config'
    assert float(config['target_MHz']) == 200, 'run_config is not for 200 MHz'
    if 'variant' in config:
        assert config['variant'] == args.stage, 'run_config variant does not match stage'
    start_ns = (source / 'run_config.txt').stat().st_mtime_ns
    for name in ('bc_real_synth_result.txt', 'timing_summary_postroute.rpt',
                 'route_status.rpt', 'utilization_postroute.rpt', 'source_files.txt'):
        assert (source / name).stat().st_mtime_ns >= start_ns, f'Stale report from an earlier invocation: {name}'
pipeline_runners = {
    'synth_200_pipeline030.tcl': ('V1', 'pipeline'),
    'synth_200_pipeline2_030.tcl': ('V2', 'pipeline2_'),
    'synth_200_pipeline3_030.tcl': ('V3', 'pipeline3_'),
    'synth_200_pipeline5_030.tcl': ('V5', 'pipeline5_'),
    'synth_200_pipeline6_030.tcl': ('V6', 'pipeline6_'),
}
version, pipeline_prefix = pipeline_runners.get(runner.name, ('baseline_or_single_candidate', None))
if pipeline_prefix is not None:
    assert config, 'Pipeline run is missing its run_config.txt'
    assert re.search(re.escape(pipeline_prefix) + r'\d{3}0926(?:_|$)', args.stage), 'Stage does not identify the requested pipeline version'
    if 'candidate_version' in config:
        assert config['candidate_version'] == version, 'run_config candidate version does not match runner'

summary = dict(candidate=args.name, pipeline_version=version, stage=args.stage,
               runner=runner.relative_to(ROOT).as_posix(), implementation='COMPLETED',
               frequency_MHz=200, run_config=config, **timing(read('timing_summary_postroute.rpt')))
# The existing V1 result format already contains the post-route numbers; no
# new completion file or marker is required for an in-flight V1 implementation.
post_result = result_text.split('(B) POST-ROUTE (MEASURED)', 1)[1]
post_wns_tns = re.search(r'WNS / TNS\s*:\s*([\d.+-]+)\s*/\s*([\d.+-]+)', post_result)
assert post_wns_tns and (float(post_wns_tns[1]), float(post_wns_tns[2])) == (summary['WNS'], summary['TNS']), 'Result/report timing mismatch'
route = read('route_status.rpt')
for key, label in [('route_errors','nets with routing errors'), ('routed_nets','fully routed nets'), ('routable_nets','routable nets')]:
    summary[key] = int(re.search(label + r'\.+\s*:\s*(\d+)', route).group(1))
util = read('utilization_postroute.rpt')
summary['resources'] = {}
for key, label in [('LUT','Slice LUTs'), ('FF','Slice Registers'), ('RAMB36','RAMB36/FIFO'), ('RAMB18','RAMB18'), ('DSP','DSPs')]:
    summary['resources'][key] = int(re.search(r'\|\s*'+label+r'\*?\s*\|\s*(\d+)',util).group(1))
ok = summary['TNS'] == 0 and summary['THS'] == 0 and summary['WHS'] >= 0 and summary['WPWS'] >= 0 and summary['route_errors'] == 0 and summary['routed_nets'] == summary['routable_nets']
summary['targets_ns'] = {str(target): ok and summary['WNS'] >= target for target in [0.1, 0.25, 0.4]}
tight_reports = list(source.glob('timing_summary_route_setup*.rpt'))
assert len(tight_reports) == 1, tight_reports
tight = tight_reports[0]
extra_ns = int(tight.stem.rsplit('setup', 1)[1]) / 100
summary['setup_tag'] = tight.stem.rsplit('route_', 1)[1]
if config:
    assert float(config['extra_setup_ns']) == extra_ns, 'Setup pressure mismatch between run_config and report'
    if 'setup_tag' in config:
        assert config['setup_tag'] == summary['setup_tag'], 'Setup tag mismatch'
if pipeline_prefix is not None:
    assert pipeline_prefix + summary['setup_tag'].removeprefix('setup') in args.stage, 'Stage setup suffix does not match measured report'
summary['extra_setup_ns'] = extra_ns
summary['timing_with_extra_setup'] = timing(tight.read_text(encoding='utf-8'))
summary['restored_minus_tight_WNS'] = round(summary['WNS'] - summary['timing_with_extra_setup']['WNS'], 3)
assert summary['restored_minus_tight_WNS'] == extra_ns
assert summary['WHS'] == summary['timing_with_extra_setup']['WHS']
summary['worst_path'] = re.search(r'Slack \((?:MET|VIOLATED)\)\s*:[\s\S]*?(?=Location\s+Delay type)', read('timing_summary_postroute.rpt')).group(0).strip()
run_commit = re.search(r'^\s*9\s+Git commit SHA\s*:\s*(\S+)', result_text, re.M)
summary['source_commit'] = run_commit[1] if run_commit else 'unknown'
summary['archive_commit'] = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()

paths = [repo_path(line) for line in read('source_files.txt').splitlines() if line.strip()]
source_names = {path.relative_to(ROOT).as_posix() for path in paths}
if pipeline_prefix is not None:
    folders = {
        'V1': ('mac_buffer', 'requant_pipe', 'stripe_pipe'),
        'V2': ('mac_buffer_l3l5', 'post_shift', 'stripe_banked'),
        'V3': ('mac_buffer_l3l5', 'prelu_pipeline', 'stripe_banked'),
        'V5': ('mac_buffer_l3l5', 'prelu_partial', 'stripe_banked'),
        'V6': ('mac_buffer_l3l5', 'post_partial32', 'stripe_banked'),
    }[version]
    expected = [f'experiments/timing_200_20260926/{folder}/{name}' for folder, name in
                zip(folders, ('mac_issue_stage.sv', 'vector_postprocess_shared.sv', 'stripe_buffer.v'))]
    scalar_folder = {'V3': 'prelu_pipeline', 'V5': 'prelu_partial', 'V6': 'post_partial32'}.get(version, 'requant_pipe')
    expected.append(f'experiments/timing_200_20260926/{scalar_folder}/prelu_requantize.sv')
    assert set(expected) <= source_names, f'{version} candidate replacements missing from measured source list'
    for expected_path in expected:
        basename = Path(expected_path).name
        assert sum(path.name == basename for path in paths) == 1, f'Duplicate {basename} definitions'
packed_roms = list((ROOT/'rom/member_a_d16_s8_m1_c16').glob('*_packed.mem'))
input_banks = list((ROOT/'member_b_evidence/real_banks').glob('rom_bank_*.mem'))
assert len(packed_roms) == 19 and len(input_banks) == 16, 'Frozen ROM closure is incomplete'
for path in packed_roms + input_banks:
    assert (source.parent / path.name).read_bytes() == path.read_bytes(), f'Staged ROM differs from source: {path.name}'
summary['staged_roms_equal_sources'] = 35
paths += packed_roms + input_banks + [runner]
manifest = []
for path in paths:
    data = path.read_bytes()
    manifest.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(),
                         canonical_sha256=hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()))
launch_manifest = source / 'launch_source_manifest.json'
if pipeline_prefix is not None:
    assert launch_manifest.exists(), 'Pipeline launch manifest is missing; exact run inputs cannot be established'
if launch_manifest.exists():
    before = {item['path']: item['sha256'] for item in json.loads(launch_manifest.read_text())}
    after = {item['path']: item['sha256'] for item in manifest}
    assert before == after, 'Inputs changed after launch; do not publish mixed evidence'
    summary['launch_input_hashes_unchanged'] = True
else:
    summary['launch_input_hashes_unchanged'] = None
if not args.check_only:
    dest.mkdir(parents=True,exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path,dest/path.name)
    (dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (dest/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'worst_path'},indent=2))
