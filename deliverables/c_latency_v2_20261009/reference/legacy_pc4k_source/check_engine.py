"""Injected transport with real CUDA/finite queues; no socket or board operation."""
from pathlib import Path
from time import perf_counter_ns, sleep
import hashlib, importlib.util, json, sys, tempfile
HERE = Path(__file__).resolve().parent; STREAM = HERE.parent; ROOT = STREAM.parents[2]
sys.path.insert(0, str(STREAM))
from host_regression import Peer, independent_audit
from streaming_client import StreamingClient, PreparedGolden
from pc4k_bridge import load_pipeline
from engine import measure
sys.path.insert(0, str(ROOT/'experiments/pc_4k_20261007'))
from reference import integer_reference


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    saved = HERE/'checks'/Path(tempfile.mkdtemp(prefix='pld_live4k_engine_')).name
    saved.mkdir(parents=True); print('SAVED_DIRECTORY='+str(saved),flush=True)
    base = ROOT/'host/baseline_ethernet/data'
    manifest = json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    inputs, goldens = [], []
    for row in manifest['frames'][:2]:
        for kind, dest in [('input',inputs),('golden',goldens)]:
            p = base/row[kind+'_file']; assert sha(p)==row[kind+'_sha256']; dest.append(p.read_bytes())
    pairs = [(p,PreparedGolden(g)) for p,g in zip(inputs,goldens)]
    module = load_pipeline(); backend = module.CudaBicubic()
    expected = [integer_reference(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920)) for g in goldens]
    for g in goldens: backend.resize(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920))
    rows = []
    for name in ('normal','drop_final_reply','slow_finalize','slow_preview','bounded_wait_expired','preview_closed','wrong_golden'):
        frames = 12 if name in ('slow_preview','bounded_wait_expired') else 6
        fault = name if name in ('drop_final_reply','wrong_golden') else None
        peer = Peer([inputs[i%2] for i in range(frames)],[goldens[i%2] for i in range(frames)],fault)
        session = bytes(range(16)); case = saved/name; case.mkdir()
        client = StreamingClient(peer,peer.address,session,case/'raw',output_window=128,frame_log_mode='jsonl')
        if name=='slow_finalize':
            original_finish=client.finish
            def delayed_finish():sleep(.15);return original_finish()
            client.finish=delayed_finish
        shown = []
        def preview(completed):
            if completed is None: return
            if name=='preview_closed': raise RuntimeError('injected preview close')
            if name=='slow_preview': sleep(.2)
            if name=='bounded_wait_expired':sleep(2)
            shown.append(completed.frame_id)
            return dict(submitted_ns=perf_counter_ns(),size=[1280,720])
        result = measure(client,pairs,module,backend,session.hex(),'FROZEN_MEMORY_PEER_NO_BOARD',
                         case/'measurement',frames,60 if name=='slow_preview' else 30,
                         preview=preview,source_kind='INJECTED_MEMORY_PEER_PREVIEW_CALLBACK_NO_BOARD',expected_4k=expected,
                         queue_accept_timeout=.5 if name=='bounded_wait_expired' else 0)
        if name in ('normal','drop_final_reply','slow_finalize'):
            assert result['status']=='COMPLETE_MEASUREMENT',result
            assert peer.frame_acks==frames and result['generated_4k']==result['preview_submitted']==frames
            assert shown==list(range(frames)) and result['duplicate_output_ids']==0
            assert not result['missing_generated_ids'] and not result['accepted_but_no_frame_done']
            assert result['generated_4k_reference_zero_difference_frames']==frames
            if name=='slow_finalize':assert result['post_measurement_evidence_finalize_ms']>=150
            audit = independent_audit(case/'raw',[inputs[i%2] for i in range(frames)],[goldens[i%2] for i in range(frames)],session)
            assert len((case/'raw/FRAMES.jsonl').read_text().splitlines())==frames
            assert json.loads((case/'raw/FRAMES.json').read_text())==client.frames
        else:
            assert result['status']=='FAIL_PRESERVE_EVIDENCE',result
            assert peer.frame_acks < frames and result['unattempted_slots']>0
            assert result['pipeline_stats']['accepted']==result['pipeline_stats']['completed']
            assert not result['missing_generated_ids'] and result['duplicate_output_ids']==0
            if name in ('slow_preview','bounded_wait_expired'): assert result['pipeline_stats']['rejected_full']==1,result
            if name=='wrong_golden': assert peer.frame_acks==0 and result['generated_4k']==0
            if name=='preview_closed': assert result['preview_error'] and result['preview_submitted']==0
            audit = None
        assert result['whole_system_4K30_achieved'] is False
        rows.append(dict(name=name,status='PASS_EXPECTED_BEHAVIOR',measurement=result,frame_releases=peer.frame_acks,raw_audit=audit))
        print(name+' PASS',flush=True)
    result = dict(status='PASS_INJECTED_TRANSPORT_REAL_CUDA_CONTINUOUS_ENGINE',cases=rows,
                  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (HERE/'engine.py',Path(__file__),STREAM/'streaming_client.py',STREAM/'binary_journal.py',ROOT/'experiments/pc_4k_20261007/pipeline.py',ROOT/'experiments/pc_4k_20261007/reference.py')},
                  socket_created=False,board_run=False,actual_Tk_preview=False,
                  scope='FINITE_SCHEDULE_QUEUE_DRAIN_4K_NUMERIC_FAULT_VALIDATION_NO_REALTIME_BOARD_CLAIM')
    (saved/'RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (HERE/'LATEST_engine.json').write_text(json.dumps(dict(saved_directory=str(saved)),ensure_ascii=False),encoding='utf-8')


if __name__=='__main__': main()
