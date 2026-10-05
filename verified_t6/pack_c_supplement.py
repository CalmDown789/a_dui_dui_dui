"""Package only the already-existing original files named by the missing-file list."""
from pathlib import Path, PureWindowsPath
import argparse, hashlib, json, zipfile

p=argparse.ArgumentParser();p.add_argument('--list',default=str(Path(__file__).with_name('C_SUPPLEMENT_REQUIRED.json')));p.add_argument('--output',required=True)
a=p.parse_args();out=Path(a.output)
if out.exists():raise SystemExit('Preserving existing output: '+str(out))
spec=json.loads(Path(a.list).read_text(encoding='utf-8-sig'))
paths=[Path(s) for s in spec['files']]
missing=[str(p) for p in paths if not p.is_file()]
if missing:raise SystemExit('Missing originals; provide correct evidence/path errata, do not fabricate:\n'+'\n'.join(missing))
rows=[]
with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
 for src in paths:
  wp=PureWindowsPath(src);name='/'.join(wp.parts[1:]);data=src.read_bytes()
  rows.append(dict(original_path=str(src),member=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
  z.writestr(name,data)
 z.writestr('SUPPLEMENT_MANIFEST.json',json.dumps(dict(original_archive_sha256=spec['original_archive_sha256'],files=rows),indent=2)+'\n')
receipt=dict(path=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),files=len(rows))
Path(str(out)+'.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
