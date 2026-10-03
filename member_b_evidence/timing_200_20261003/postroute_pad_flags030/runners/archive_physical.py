"""Member B: verify and archive this round's physical-only experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/timing_200_20260926/postroute_finish'))
from prepare import verify, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage')
parser.add_argument('name')
args = parser.parse_args()
stage = (ROOT / '_synth_bc' / args.stage).resolve()
assert stage.parent == (ROOT / '_synth_bc').resolve()
inputs = verify(stage)
assert not (stage / 'failed.txt').exists()
result = json.loads((stage / 'result_manifest.json').read_text())
assert result['status'] == 'COMPLETED_MEASURED'
assert inputs['baseline_hash'] == result['baseline_hash']
assert digest(stage / 'postroute.dcp') == result['postroute_hash']
assert result['values']['route_fully_complete'] == '1'
assert result['values']['route_errors_present'] == '0'
log = (stage / 'vivado.log').read_text(encoding='utf-8', errors='replace')
assert '\nPOSTROUTE_FINISH_COMPLETE stage=' in log
assert 'INFO: [Common 17-206] Exiting Vivado' in log
for item in result['reports']:
    assert digest(stage / item['path']) == {key: item[key] for key in ('bytes', 'sha256')}
parent = ROOT / 'member_b_evidence/timing_200_20261003'
out = (parent / args.name).resolve()
assert out.parent == parent.resolve()
out.mkdir(parents=True, exist_ok=False)
shutil.copytree(stage / 'reports', out / 'reports')
for name in ('input_manifest.json', 'result_manifest.json', 'settings.tcl', 'run_started.txt'):
    shutil.copy2(stage / name, out / name)
shutil.copy2(stage / 'vivado.log', out / 'vivado.log.txt')
(out / 'runners').mkdir()
for item in inputs['tools']:
    shutil.copy2(ROOT / item['path'], out / 'runners' / Path(item['path']).name)
shutil.copy2(__file__, out / 'runners/archive_physical.py')
for folder in stage.glob('diagnose_*'):
    if folder.is_dir():
        shutil.copytree(folder, out / folder.name)
for path in stage.glob('diagnose_*.log'):
    shutil.copy2(path, out / (path.name + '.txt'))
manifest = []
for path in sorted(out.rglob('*')):
    if path.is_file():
        manifest.append(dict(path=path.relative_to(out).as_posix(), **digest(path)))
(out / 'archive_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(archive=args.name, final=result['global_timing']['after_restored'],
                     targets=result['timing_targets_ns']), indent=2))
