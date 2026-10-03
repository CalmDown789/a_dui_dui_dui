"""Verify raw-byte hashes of completed archives before staging/publishing."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'member_b_evidence/timing_200_20261003'
checked = {}

def verify(folder, relative, expected, size=None):
    path = (folder / relative).resolve()
    path.relative_to(folder.resolve())
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected, f'Hash mismatch: {path}'
    if size is not None:
        assert len(data) == size, f'Size mismatch: {path}'
    checked[str(path.relative_to(BASE))] = expected

def walk_sim(value, folder):
    if isinstance(value, dict):
        if 'archive_path' in value and 'sha256' in value:
            verify(folder, value['archive_path'], value['sha256'], value.get('bytes'))
        for item in value.values():
            walk_sim(item, folder)
    elif isinstance(value, list):
        for item in value:
            walk_sim(item, folder)

archives = 0
for folder in sorted(p for p in BASE.iterdir() if p.is_dir()):
    manifest = folder / 'archive_manifest.json'
    if manifest.is_file():
        for row in json.loads(manifest.read_text(encoding='utf-8')):
            verify(folder, row['path'], row['sha256'], row['bytes'])
        archives += 1
    manifest = folder / 'manifest.json'
    if manifest.is_file():
        content = json.loads(manifest.read_text(encoding='utf-8'))
        if isinstance(content, dict) and isinstance(content.get('files'), list):
            for row in content['files']:
                verify(folder, row['archive'], row['sha256'], row['bytes'])
            archives += 1
    summary = folder / 'summary.json'
    if summary.is_file():
        content = json.loads(summary.read_text(encoding='utf-8'))
        if 'selected_testbenches' in content:
            walk_sim(content, folder)
            archives += 1
assert archives > 0 and checked
print(f'ARCHIVE_RAW_BYTES_PASS archives={archives} unique_files={len(checked)}')
print('Scope: stored archive hashes only; not a new timing/functional/board acceptance.')
