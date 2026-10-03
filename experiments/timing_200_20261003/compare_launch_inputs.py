"""Audit exact shared inputs against the original completed V1 nominal."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / '_synth_bc/acc36_realrom_200_member_b_pipeline0000926_ascii_ramdecomp/reports/launch_source_manifest.json'
NEW = ROOT / '_synth_bc/acc36_realrom_200_member_b_pad_flags_20261003_setup030_ascii_ramdecomp/reports/launch_source_manifest.json'
before = {row['path']: row for row in json.loads(OLD.read_text(encoding='utf-8'))}
after = {row['path']: row for row in json.loads(NEW.read_text(encoding='utf-8'))}
common = sorted(before.keys() & after.keys())
changed = [p for p in common if before[p]['sha256'] != after[p]['sha256']]
assert not changed, f'Existing inputs changed: {changed}'
report = dict(status='SHARED_LAUNCH_INPUT_HASHES_MATCH', original_inputs=len(before),
              candidate_inputs=len(after), shared_unchanged=len(common),
              removed=sorted(before.keys()-after.keys()), added=sorted(after.keys()-before.keys()),
              original_manifest_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),
              candidate_manifest_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest(),
              note='Candidate has new FIFO write-enable model, cached pad boundary RTL and runner; arithmetic/ROM/constraints shared bytes unchanged. Does not imply physical timing or functional equivalence.')
target = Path(__file__).resolve().parent / 'pad_flags/launch_input_comparison.json'
with target.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps(report, indent=2))
