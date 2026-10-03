"""Publication guard: exact new-round Git blobs and no unrelated/private paths."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ('experiments/timing_200_20261003/', 'member_b_evidence/timing_200_20261003/')
EXACT = {'.gitignore', '.gitattributes', 'docs/MEMBER_B_200MHZ_TIMING_2026-10-03.md'}

def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+ROOT.as_posix(), *args], cwd=ROOT)

assert git('branch', '--show-current').decode().strip() == 'member-b-2025-2-bc-trial'
assert not git('diff','--cached','--name-only','--diff-filter=D','-z'), 'Unexpected staged deletion'
paths = [p.decode('utf-8') for p in git('diff','--cached','--name-only','-z').split(b'\0') if p]
assert paths, 'Nothing staged; cannot report publication verification'
exact_blobs = 0
for rel in paths:
    assert rel in EXACT or rel.startswith(PREFIXES), f'Unrelated/private staged path: {rel}'
    if rel.startswith(PREFIXES[0]):
        assert '/unit_work/' not in rel, f'Compiled cache staged: {rel}'
    elif '/unit_work/' in rel:
        assert Path(rel).suffix in {'.log','.jou'}, f'Non-log unit cache staged: {rel}'
    raw = (ROOT / rel).read_bytes()
    blob = git('cat-file','blob',':'+rel)
    if rel.startswith(PREFIXES):
        assert blob == raw, f'Frozen raw bytes changed by Git filters: {rel}'
        exact_blobs += 1
    else:
        assert blob in (raw, raw.replace(b'\r\n',b'\n')), f'Unexpected content filter: {rel}'
print(f'STAGED_SCOPE_AND_BYTES_PASS files={len(paths)} exact_frozen_blobs={exact_blobs}')
archive_files = sorted(p for p in (ROOT / PREFIXES[1]).rglob('*') if p.is_file())
tracked = {p.decode('utf-8') for p in git('ls-files','--cached','-z').split(b'\0') if p}
missing = [p.relative_to(ROOT).as_posix() for p in archive_files
           if p.relative_to(ROOT).as_posix() not in tracked]
assert not missing, 'Archive files missing from Git index: '+repr(missing[:20])
for path in archive_files:
    rel = path.relative_to(ROOT).as_posix()
    assert path.suffix.lower() not in {'.dcp','.exe','.dll','.pyc'}, 'Compiled artifact in public archive: '+rel
    assert path.stat().st_size < 50_000_000, 'Unexpected large archive file: '+rel
    assert git('cat-file','blob',':'+rel) == path.read_bytes(), 'Stale/mixed archive index: '+rel
print(f'STAGED_ARCHIVE_COMPLETENESS_PASS files={len(archive_files)} no_ignored_evidence=True')
print('Only this round engineering paths, public report and limited Git attributes/ignore changes are staged.')
