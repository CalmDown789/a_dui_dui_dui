"""Archive a completed physical-only experiment without copying binary DCPs."""
from pathlib import Path
import argparse
import json
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'postroute_finish'))
from prepare import checked_stage, verify, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage', help='Directory name directly below _synth_bc')
parser.add_argument('name', help='New evidence directory name')
args = parser.parse_args()
stage = checked_stage(ROOT / '_synth_bc' / args.stage)
inputs = verify(stage)
assert not (stage / 'failed.txt').exists(), 'Failed run is not a completed result'
result = json.loads((stage / 'result_manifest.json').read_text())
assert result['status'] == 'COMPLETED_MEASURED'
assert result['baseline_hash'] == inputs['baseline_hash']
assert digest(stage / 'postroute.dcp') == result['postroute_hash']
assert result['values']['route_fully_complete'] == '1'
assert result['values']['route_errors_present'] == '0'
log = (stage / 'vivado.log').read_text(encoding='utf-8', errors='replace')
assert '\nPOSTROUTE_FINISH_COMPLETE stage=' in log
assert 'INFO: [Common 17-206] Exiting Vivado' in log
for item in result['reports']:
    assert digest(stage / item['path']) == {k: item[k] for k in ('bytes', 'sha256')}
out = ROOT / 'member_b_evidence/timing_200_20260926' / args.name
assert out.parent == ROOT / 'member_b_evidence/timing_200_20260926'
out.mkdir(exist_ok=False)
shutil.copytree(stage / 'reports', out / 'reports')
for name in ('input_manifest.json', 'result_manifest.json', 'settings.tcl', 'run_started.txt'):
    shutil.copy2(stage / name, out / name)
shutil.copy2(stage / 'vivado.log', out / 'vivado.log.txt')
(out / 'runners').mkdir()
for item in inputs['tools']:
    shutil.copy2(ROOT / item['path'], out / 'runners' / Path(item['path']).name)
shutil.copy2(__file__, out / 'runners' / Path(__file__).name)
(out / 'README.md').write_text(
    '# Post-route physical optimization evidence\n\n'
    f'Local stage: `_synth_bc/{args.stage}`. Both binary DCPs remain there; '
    'Git contains their hashes, exact runners and text reports. '
    'The baseline implementation evidence identifies RTL, constraints and ROM inputs. '
    'Reproduction: rebuild that baseline, prepare a NEW stage with the recorded pressure, '
    'then run `postroute_finish/finish.tcl`. Record the new DCP hash instead of assuming '
    'binary-identical ZIP timestamps. Completion does not imply timing acceptance.\n',
    encoding='utf-8')
print(json.dumps({'archive': args.name, 'status': result['status'],
                  'final': result['global_timing']['after_restored'],
                  'targets': result['timing_targets_ns']}, indent=2))
