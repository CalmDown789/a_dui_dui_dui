"""Real Tk PhotoImage ownership/pixels with memory peer and real CUDA; no board."""
from pathlib import Path
import hashlib,json,os,sys,tempfile
HERE=Path(__file__).resolve().parent;STREAM=HERE.parent;ROOT=STREAM.parents[2]
sys.path.insert(0,str(STREAM));sys.path.insert(0,str(ROOT/'experiments/pc_4k_20261007'))
from streaming_client import StreamingClient,PreparedGolden
from host_regression import Peer,independent_audit
from pc4k_bridge import load_pipeline
from reference import integer_reference
from engine import measure
from live4k import TkPreview
def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    saved=HERE/'checks'/Path(tempfile.mkdtemp(prefix='pld_live4k_tk_')).name;saved.mkdir(parents=True)
    print('SAVED_DIRECTORY='+str(saved),flush=True)
    # Use previously verified existing Tcl scripts read-only; no shared writes.
    runtime=ROOT/'experiments/pc_4k_20261007/runtime'
    os.environ['TCL_LIBRARY']=(runtime/'tcl8.6').as_posix();os.environ['TK_LIBRARY']=(runtime/'tk8.6').as_posix()
    data=ROOT/'host/baseline_ethernet/data';m=json.loads((data/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    ins=[];gold=[]
    for row in m['frames'][:2]:
        for kind,dest in [('input',ins),('golden',gold)]:
            p=data/row[kind+'_file'];assert sha(p)==row[kind+'_sha256'];dest.append(p.read_bytes())
    module=load_pipeline();backend=module.CudaBicubic()
    expected=[integer_reference(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920))for g in gold]
    priming,_=backend.resize(module.np.frombuffer(gold[0],dtype=module.np.uint8).reshape(1080,1920))
    assert module.np.array_equal(priming,expected[0])
    peer=Peer(ins,gold);session=bytes(range(16));client=StreamingClient(peer,peer.address,session,saved/'raw',output_window=128,frame_log_mode='jsonl')
    preview=TkPreview(320,180);preview.root.title('PLD 本机Tk接入检查 · 内存传输，无实板')
    preparation=preview.warmup(priming);assert preparation['counted_as_measured_frame']is False
    import cv2
    from PIL import ImageTk
    compared=[]
    def shown(completed):
        result=preview(completed)
        if completed is not None:
            actual=module.np.asarray(ImageTk.getimage(preview.photo))
            wanted=cv2.resize(expected[completed.source_frame_id],tuple(result['size']),interpolation=cv2.INTER_AREA)
            # Tk returns RGB/RGBA storage even for an original L image.
            # Check every channel and alpha, retaining exact grayscale values.
            if actual.ndim==3:
                assert actual.shape[:2]==wanted.shape and actual.shape[2] in (3,4)
                assert module.np.array_equal(actual[:,:,:3],module.np.repeat(wanted[:,:,None],3,axis=2))
                if actual.shape[2]==4: assert module.np.all(actual[:,:,3]==255)
            else: assert module.np.array_equal(actual,wanted)
            compared.append(dict(frame_id=completed.frame_id,source_frame_id=completed.source_frame_id,
                                 pixels_checked=int(actual.size),mismatches=0))
        return result
    try:
        result=measure(client,[(x,PreparedGolden(g))for x,g in zip(ins,gold)],module,backend,session.hex(),
                       'FROZEN_MEMORY_PEER_NO_BOARD',saved/'measurement',2,30,preview=shown,
                       source_kind='INJECTED_MEMORY_PEER_REAL_TK_NO_BOARD',expected_4k=expected)
        assert result['status']=='COMPLETE_MEASUREMENT' and result['preview_submitted']==2,result
        assert [r['frame_id']for r in compared]==[0,1]
        audit=independent_audit(saved/'raw',ins,gold,session)
    finally:preview.finish(saved)
    report=dict(status='PASS_REAL_TK_APP_PIXELS_ID_AND_QUEUE_HANDOFF',pixel_checks=compared,raw_audit=audit,preview_preparation=preparation,
        source_sha256={str(p.relative_to(ROOT)):sha(p)for p in (HERE/'engine.py',HERE/'live4k.py',Path(__file__),STREAM/'streaming_client.py',STREAM/'binary_journal.py',ROOT/'experiments/pc_4k_20261007/pipeline.py')},
        socket_created=False,board_run=False,physical_panel_refresh_measured=False,
        scope='ACTUAL_TK_PHOTOIMAGE_PIXELS_WITH_INJECTED_TRANSPORT_NOT_BOARD_FPS_OR_PANEL_REFRESH')
    (saved/'RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (HERE/'LATEST_app.json').write_text(json.dumps(dict(saved_directory=str(saved)),ensure_ascii=False),encoding='utf-8')
    print(report['status'])
if __name__=='__main__':main()
