"""Verify extracted handoff files or ZIP entries offline; never invokes hardware."""
from pathlib import Path
import argparse, hashlib, json, zipfile

def sha_stream(stream):
    h=hashlib.sha256()
    while block:=stream.read(4*1024*1024): h.update(block)
    return h.hexdigest()

def verify_zip(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); assert len(names)==len(set(names)), 'duplicate entries'
        manifest_name=next(n for n in names if n.endswith('/DELIVERY_MANIFEST.json'))
        prefix=manifest_name[:-len('DELIVERY_MANIFEST.json')]
        m=json.loads(z.read(manifest_name))
        assert set(names)=={prefix+r['file'] for r in m['files']}|{manifest_name}, 'inventory differs'
        for row in m['files']:
            info=z.getinfo(prefix+row['file']); assert info.file_size==row['bytes'],row['file']
            with z.open(info) as stream: assert sha_stream(stream)==row['sha256'],row['file']
        return dict(status='PASS_ALL_ARCHIVE_ENTRIES_SHA256_AND_CRC',files=len(m['files']),bytes=sum(r['bytes'] for r in m['files']))

def verify_folder(root):
    m=json.loads((root/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    for row in m['files']:
        path=(root/row['file']).resolve(); assert path.is_relative_to(root.resolve())
        assert path.stat().st_size==row['bytes'],row['file']
        with path.open('rb') as stream: assert sha_stream(stream)==row['sha256'],row['file']
    return dict(status='PASS_ALL_DELIVERY_FILES_SHA256',files=len(m['files']))

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('path',type=Path); arg=a.parse_args()
    print(json.dumps(verify_zip(arg.path) if arg.path.is_file() else verify_folder(arg.path)))
