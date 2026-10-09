"""Archive every retained evidence file; packaging is never video acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, zipfile

def enumerate_files(root):
    files = sorted(p for p in root.rglob('*') if p.is_file())
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Evidence contains a link/path outside evidence root')
    return files

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--out-zip', type=Path, required=True)
    args = parser.parse_args()
    root, target = args.evidence_root.resolve(), args.out_zip.resolve()
    if not root.is_dir() or target.is_relative_to(root):
        raise ValueError('Evidence must exist; ZIP must be outside evidence tree')
    if target.exists() or not target.parent.is_dir():
        raise ValueError('Use a new ZIP name in an existing output directory')
    files = enumerate_files(root)
    if not files or any(p.relative_to(root).as_posix() == 'ZIP_CONTENTS_SHA256.json' for p in files):
        raise ValueError('Empty evidence or reserved manifest name')
    entries = []
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in files:
            before = path.stat()
            sha = hashlib.sha256()
            length = 0
            name = path.relative_to(root).as_posix()
            with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    sha.update(chunk)
                    length += len(chunk)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or length != before.st_size:
                raise ValueError('Evidence changed during packing: ' + name)
            entries.append(dict(file=name, bytes=length, sha256=sha.hexdigest()))
        if enumerate_files(root) != files:
            raise ValueError('Evidence file set changed during packing')
        archive.writestr('ZIP_CONTENTS_SHA256.json', json.dumps(dict(
            status='PACKED_RAW_EVIDENCE_NOT_STAGE_ACCEPTANCE',
            created_at_UTC=datetime.now(timezone.utc).isoformat(),
            evidence_root=str(root), board_acceptance=False,
            files=entries), ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(target, 'r') as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError('ZIP CRC failure: ' + bad)
    sha = hashlib.sha256()
    with target.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    result = dict(status='PACKED_RAW_EVIDENCE_NOT_STAGE_ACCEPTANCE',
                  ZIP=str(target), ZIP_sha256=sha.hexdigest(), ZIP_bytes=target.stat().st_size,
                  files=len(entries), original_evidence_deleted=False)
    receipt = target.with_suffix(target.suffix + '.receipt.json')
    with receipt.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(result))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
