"""Audit real engine evidence from injected transport; no fabricated startup."""
from pathlib import Path
from unittest.mock import patch
import hashlib,json,shutil,sys,tempfile
HERE=Path(__file__).resolve().parent;STREAM=HERE.parent;ROOT=STREAM.parents[2]
sys.path.insert(0,str(STREAM));sys.path.insert(0,str(ROOT/'experiments/pc_4k_20261007'))
from pc4k_bridge import load_pipeline
import reference
from audit_live4k import audit_payloads
def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    source=Path(json.loads((HERE/'LATEST_engine.json').read_text(encoding='utf-8'))['saved_directory'])/'normal'
    saved=HERE/'checks'/Path(tempfile.mkdtemp(prefix='pld_live4k_audit_')).name;saved.mkdir(parents=True)
    print('SAVED_DIRECTORY='+str(saved),flush=True)
    base=ROOT/'host/baseline_ethernet/data';manifest=json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    pairs=[]
    for row in manifest['frames'][:2]:
        p,g=base/row['input_file'],base/row['golden_file']
        assert sha(p)==row['input_sha256'] and sha(g)==row['golden_sha256'];pairs.append((p.read_bytes(),g.read_bytes()))
    module=load_pipeline();rows=[]
    for case in ('valid','tampered_raw','late_queue_acceptance','wrong_4k_hash','missing_output_event'):
        out=saved/case;out.mkdir();shutil.copytree(source/'raw',out/'traffic');shutil.copytree(source/'measurement',out/'measurement')
        result_path=out/'measurement/RESULTS.json';measurement=json.loads(result_path.read_text(encoding='utf-8'))
        report=dict(offered_slots=measurement['offered_slots'],session=bytes(range(16)).hex(),peer=['192.168.0.2',5000],local=['192.168.0.3',6102],
                    measurement_result_sha256=sha(result_path))
        if case=='tampered_raw':
            p=out/'traffic/datagrams.bin'
            with p.open('r+b')as f:f.seek(1000);v=f.read(1);f.seek(1000);f.write(bytes([v[0]^1]))
        if case=='late_queue_acceptance':
            p=out/'measurement/accepted.jsonl';events=[json.loads(s)for s in p.read_text(encoding='utf-8').splitlines()]
            events[0]['accepted_ns']=2**63;p.write_text(''.join(json.dumps(r)+'\n'for r in events))
        if case in ('wrong_4k_hash','missing_output_event'):
            p=out/'measurement/outputs.jsonl';events=[json.loads(s)for s in p.read_text(encoding='utf-8').splitlines()]
            if case=='wrong_4k_hash':events[0]['generated_4k_sha256']='0'*64
            else:events.pop(0)
            p.write_text(''.join(json.dumps(r)+'\n'for r in events))
        error=None;audited=None
        try:
            # A long capture must not call Path.read_bytes anywhere in this
            # evidence core. Real file_digest and record streaming still run.
            with patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file raw loading forbidden')):
                audited=audit_payloads(out,report,pairs,('192.168.0.2',5000),('192.168.0.3',6102),module,reference)
            assert case=='valid' and audited['frames']==measurement['offered_slots']
            assert audited['actual_startup_reaudited']is False
        except BaseException as exc:error=repr(exc)
        assert (error is None)==(case=='valid'),(case,error)
        rows.append(dict(case=case,status='PASS_EXPECTED_AUDIT_BEHAVIOR',error=error,audit=audited))
        print(case+' PASS',flush=True)
    report=dict(status='PASS_INDEPENDENT_STREAMING_AUDITOR_FAULT_CHECKS',cases=rows,real_startup_supplied=False,
                socket_created=False,board_run=False,whole_capture_read_bytes_forbidden_during_checks=True,
                source_sha256={str(p.relative_to(ROOT)):sha(p)for p in (Path(__file__),HERE/'audit_live4k.py',HERE/'live4k.py',STREAM/'binary_journal.py')})
    (saved/'RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (HERE/'LATEST_audit.json').write_text(json.dumps(dict(saved_directory=str(saved)),ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':main()
