"""Paced complete-Golden ownership -> actual CUDA -> actual Tk, no protocol.

This isolates PC4K and preview capacity from Python board emulation/GIL cost.
No board, socket, protocol timing or physical refresh is measured here.
"""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,os,sys,tempfile
HERE=Path(__file__).resolve().parent;STREAM=HERE.parent;ROOT=STREAM.parents[2]
sys.path.insert(0,str(STREAM));sys.path.insert(0,str(ROOT/'experiments/pc_4k_20261007'))
from streaming_client import PreparedGolden
from pc4k_bridge import load_pipeline
from reference import integer_reference
from engine import measure
from live4k import TkPreview
def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
class CompleteGoldenSource:
    frame_timeout=1;timeout=.02;attempts=4;retries=ignored=0
    def __init__(self,session):self.session=session
    def hello(self):pass
    def finish(self):pass
    def abort(self):pass
    def transfer(self,pixels,golden,frame_id,on_frame):
        on_frame(golden.data,dict(session=self.session.hex(),frame_id=frame_id,golden_match=True,
                 integrity_sha256=golden.sha256,received_perf_counter_ns=perf_counter_ns()))
def main():
    saved=HERE/'checks'/Path(tempfile.mkdtemp(prefix='pld_pc_path_150_')).name;saved.mkdir(parents=True)
    print('SAVED_DIRECTORY='+str(saved),flush=True)
    runtime=ROOT/'experiments/pc_4k_20261007/runtime'
    os.environ['TCL_LIBRARY']=(runtime/'tcl8.6').as_posix();os.environ['TK_LIBRARY']=(runtime/'tk8.6').as_posix()
    base=ROOT/'host/baseline_ethernet/data';cfg=json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    pairs=[]
    for row in cfg['frames'][:2]:
        p,g=base/row['input_file'],base/row['golden_file']
        assert sha(p)==row['input_sha256']and sha(g)==row['golden_sha256'];pairs.append((p.read_bytes(),PreparedGolden(g.read_bytes())))
    module=load_pipeline();backend=module.CudaBicubic()
    expected=[integer_reference(module.np.frombuffer(g.data,dtype=module.np.uint8).reshape(1080,1920))for _,g in pairs]
    for _,g in pairs:priming,_=backend.resize(module.np.frombuffer(g.data,dtype=module.np.uint8).reshape(1080,1920))
    preview=TkPreview(1280,720);preview.root.title('PLD PC子系统150帧检查 · 已有Golden输入，无网口/板卡')
    preparation=preview.warmup(priming);session=bytes(range(16))
    try:
        result=measure(CompleteGoldenSource(session),pairs,module,backend,session.hex(),'FROZEN_COMPLETE_GOLDEN_NO_BOARD',
                       saved/'measurement',150,30,preview=preview,source_kind='COMPLETE_GOLDEN_TO_PC4K_ONLY_NO_PROTOCOL',expected_4k=expected,queue_accept_timeout=.5)
        assert result['status']=='COMPLETE_MEASUREMENT',result
        assert result['generated_4k']==result['preview_submitted']==result['generated_4k_reference_zero_difference_frames']==150
        assert not result['missing_generated_ids']and not result['duplicate_output_ids']
        rows=[json.loads(s)for s in (saved/'measurement/outputs.jsonl').read_text(encoding='utf-8').splitlines()]
        assert [r['frame_id']for r in rows]==list(range(150))
        wanted_sha=[hashlib.sha256(a).hexdigest()for a in expected]
        assert all(r['generated_4k_sha256']==wanted_sha[r['frame_id']%2]for r in rows)
        last=module.np.fromfile(saved/'measurement/last_generated_4k.bin',dtype=module.np.uint8)
        assert module.np.array_equal(last.reshape(2160,3840),expected[1])
    finally:preview.finish(saved)
    report=dict(status='PASS_PC_ONLY_150_PACED_CUDA_4K_TK_FRAMES_NOT_BOARD_RATE',measurement=result,
                preview_preparation=preparation,protocol_metrics_valid=False,socket_created=False,board_test=False,
                whole_system_4K30_achieved=False,physical_panel_refresh_measured=False,
                all_150_outputs_submitted_in_offer_window=(result['generated_4k_fps_in_nominal_window']==result['preview_submit_fps_in_nominal_window']==30),
                source_sha256={str(p.relative_to(ROOT)):sha(p)for p in (Path(__file__),HERE/'engine.py',HERE/'live4k.py',ROOT/'experiments/pc_4k_20261007/pipeline.py',ROOT/'experiments/pc_4k_20261007/reference.py')})
    (saved/'RESULTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (HERE/'LATEST_pc_path.json').write_text(json.dumps(dict(saved_directory=str(saved)),ensure_ascii=False),encoding='utf-8')
    print(report['status'])
if __name__=='__main__':main()
