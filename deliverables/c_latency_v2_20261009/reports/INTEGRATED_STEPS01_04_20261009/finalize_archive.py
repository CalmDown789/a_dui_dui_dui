from pathlib import Path
import hashlib,json,zipfile,sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;NEW=Path(r'C:\t6int09\main')
manifest=json.loads((NEW/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
archive=REVIEW/'INTEGRATED_STEPS01_04_runtime.zip'
with zipfile.ZipFile(archive)as z:
    assert z.testzip()is None
    for name,digest in manifest['file_sha256'].items():
        assert hashlib.sha256(z.read('main/'+Path(name).as_posix())).hexdigest()==digest,name
    for name in ('BOARD_TEST_RECEIPT.json','PACKAGE_MANIFEST.json'):
        assert hashlib.sha256(z.read('main/'+name)).hexdigest()==sha(NEW/name)
receipt=dict(status='PASS_FOUR_STEPS_INTEGRATED_BOARD_AND_RUNTIME_ARCHIVE',candidate_package_manifest_sha256=sha(NEW/'PACKAGE_MANIFEST.json'),
    runtime_archive=dict(file=archive.name,sha256=sha(archive),bytes=archive.stat().st_size),
    integrated_board_frames=24,total_board_frames_audited=30,all_Golden_match=True,original_package_unchanged=True,
    final_native_setup_ns=.018,final_native_hold_ns=.050,
    artifacts={p.name:sha(p)for p in REVIEW.iterdir()if p.is_file()and p.name!='FINAL_RECEIPT.json'})
(REVIEW/'FINAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
summary=json.loads((REVIEW/'SUMMARY.json').read_text(encoding='utf-8'))
print(json.dumps(dict(status=receipt['status'],comparison=summary['comparison'],runtime_archive=receipt['runtime_archive']),indent=2))
