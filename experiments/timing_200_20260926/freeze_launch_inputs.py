"""Record the inputs of a just-started isolated implementation for later verification."""
from pathlib import Path
import hashlib
import json
import sys

root = Path(__file__).resolve().parents[2]
reports = root / '_synth_bc' / sys.argv[1] / 'reports'
paths = [root / line.removeprefix('V:').lstrip('/')
         for line in (reports / 'source_files.txt').read_text().splitlines()]
paths += list((root / 'rom/member_a_d16_s8_m1_c16').glob('*_packed.mem'))
paths += list((root / 'member_b_evidence/real_banks').glob('rom_bank_*.mem'))
paths += [root / sys.argv[2]]
manifest = []
for path in paths:
    data = path.read_bytes()
    manifest.append(dict(path=path.relative_to(root).as_posix(), bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(),
                         canonical_sha256=hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()))
target = reports / 'launch_source_manifest.json'
if target.exists():
    assert json.loads(target.read_text()) == manifest, 'Existing launch manifest differs'
else:
    target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(f'{sys.argv[1]}: frozen {len(manifest)} input hashes')
