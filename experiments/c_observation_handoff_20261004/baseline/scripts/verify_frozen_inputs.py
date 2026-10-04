from pathlib import Path
import hashlib,json,subprocess

ROOT=Path(__file__).resolve().parents[1]
receipt=json.loads((ROOT/'audit/preparation_receipt.json').read_text(encoding='utf-8'))
errors=[]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
for r in receipt['files']:
    p=ROOT/r['path']
    if not p.is_file() or sha(p)!=r['sha256']:errors.append(r['path'])
for r in receipt['B_tracked_source_hashes']+receipt['auxiliary_A_input_assets']:
    p=ROOT/'b_reference'/r['path']
    if not p.is_file() or sha(p)!=r['sha256']:errors.append('b_reference/'+r['path'])
head=subprocess.check_output(['git','-C',str(ROOT/'b_reference'),'rev-parse','HEAD'],text=True).strip()
if head!=receipt['B_commit']:errors.append('B_commit')
print(json.dumps({'status':'PASS_FROZEN_INPUTS' if not errors else 'FAIL_FROZEN_INPUTS','B_commit':head,'errors':errors}))
raise SystemExit(bool(errors))
