"""Prepare a bounded cleanup plan and verified backup; deletion is PowerShell-only.

Usage: py -3.12 scripts/workspace_maintenance.py --prepare
       py -3.12 scripts/workspace_maintenance.py --verify
The plan uses explicit local roots. Frozen deliveries and Git metadata are excluded.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BACKUP = Path('C:/Users/Administrator/srtp_backup/2026-10-09-workspace-cleanup')
PLAN = ROOT / 'docs/CLEANUP_PLAN.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare():
    assert ROOT == Path('C:/Users/Administrator/WorkBuddy/srtp').resolve()
    assert not PLAN.exists(), 'Existing plan: use --verify, do not overwrite backup'
    BACKUP.mkdir(parents=True, exist_ok=True)
    files = {p for p in ROOT.iterdir() if p.is_file() and p.name.startswith('_')}
    files |= {p for p in (ROOT / 'output').iterdir() if p.is_file() and p.name.startswith('_')}
    files.add(ROOT / 'HANDOFF_CODEX.md')
    memory = ROOT / '.workbuddy/memory'
    # Archive the original workspace records. This does not touch Codex's memory folder.
    files |= {p for p in memory.iterdir() if p.is_file() and p.name != 'MEMORY.md'}
    output = ROOT / 'output'
    for p in output.iterdir():
        if not p.is_file() or p.suffix not in {'.md', '.docx'}:
            continue
        if ('任务书' in p.name) and re.search(r'v[23]', p.name) and 'v3.2.2' not in p.name:
            files.add(p)
    logs = re.compile(r'^(vivado|xsim|xelab|xvlog)(?:_.*)?\.(?:log|jou|pb)$')
    for base in (ROOT, ROOT / 'c_side'):
        for p in base.iterdir():
            if p.is_file() and (logs.match(p.name) or p.name == 'dfx_runtime.txt'):
                if base.name == 'c_side':
                    tracked = subprocess.check_output(['git', '-C', str(base), 'ls-files', '--', p.name])
                    if tracked:
                        continue
                files.add(p)
    archived = sorted(files | {memory / 'MEMORY.md'}, key=str)
    archive = BACKUP / 'legacy_records_and_scratch.zip'
    assert not archive.exists(), 'Backup already exists'
    entries = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in archived:
            rel = p.relative_to(ROOT).as_posix()
            sha = digest(p)
            z.write(p, rel)
            entries.append({'path': rel, 'bytes': p.stat().st_size, 'sha256': sha})
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in entries:
            assert hashlib.sha256(z.read(row['path'])).hexdigest() == row['sha256']
    directories = []
    roots = [ROOT / '.Xil', ROOT / 'xsim.dir']
    # Only old engineering work trees; never inspect or change frozen handoff packages.
    scan_roots = [ROOT / 'c_side'] + [p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith('_')]
    for base in scan_roots:
        for folder, dirs, _ in os.walk(base):
            dirs[:] = [n for n in dirs if n not in {'.git', '.venv', 'venv'}
                       and not (Path(folder) / n / 'pyvenv.cfg').exists()]
            for n in list(dirs):
                if n in {'.Xil', 'xsim.dir', '__pycache__'}:
                    roots.append(Path(folder) / n)
                    dirs.remove(n)
    roots.append(ROOT / 'comm_c_20261008_pc4k_tmp')
    for p in roots:
        if not p.exists():
            continue
        assert p.resolve().is_relative_to(ROOT) and p.resolve() != ROOT
        sizes = [(x, x.stat().st_size) for x in p.rglob('*') if x.is_file()]
        directories.append({'path': str(p.resolve()), 'bytes': sum(s for _, s in sizes),
                            'files': len(sizes), 'reason': 'installed_dependency_download' if p.name.endswith('_tmp') else 'generated_simulation_cache'})
    rows = [{'path': str(p.resolve()), 'bytes': p.stat().st_size, 'sha256': digest(p),
             'reason': 'verified_external_archive'} for p in sorted(files, key=str)]
    plan = {'workspace': str(ROOT), 'backup': str(archive), 'backup_sha256': digest(archive),
            'backup_entries': entries, 'files': rows, 'directories': directories,
            'delete_file_count': len(rows) + sum(d['files'] for d in directories),
            'delete_bytes': sum(r['bytes'] for r in rows) + sum(d['bytes'] for d in directories)}
    write_json(PLAN, plan)
    write_json(BACKUP / 'manifest.json', plan)
    print(json.dumps({k: plan[k] for k in ('delete_file_count', 'delete_bytes', 'backup')}))
    for d in sorted(directories, key=lambda row: row['bytes'], reverse=True)[:12]:
        print(f"{d['bytes']/1024**2:.2f} MiB {d['files']} {d['path']}")


def verify():
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    assert digest(Path(plan['backup'])) == plan['backup_sha256']
    remaining = [r['path'] for r in plan['files'] + plan['directories'] if Path(r['path']).exists()]
    assert not remaining, remaining
    print(json.dumps({'status': 'PASS_CLEANUP_AND_BACKUP', 'files_removed': plan['delete_file_count'],
                      'bytes_removed': plan['delete_bytes']}))


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--prepare', action='store_true')
    args.add_argument('--verify', action='store_true')
    a = args.parse_args()
    if a.prepare:
        prepare()
    elif a.verify:
        verify()
    else:
        args.print_help()
