"""Adapt the frozen 128-window host regression to the isolated host candidate."""
from pathlib import Path
import hashlib,json,runpy,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'main/proof'
sys.path.insert(0,str(ROOT/'validation'))
sys.path.insert(0,str(ROOT/'main/host'));sys.path.insert(0,str(ROOT/'main/streaming'))
src=(HERE/'check_host_window128.py').read_text()
replacements=[
    ("'binary_journal.py','audit_protocol.py')}","'binary_journal.py','audit_protocol.py','timing_diagnostics.py','nonblocking_io.py')}"),
    ("scope='INJECTED_MEMORY_PEER_FULL_GOLDEN_NO_BOARD_OR_REALTIME_FPS',", "scope='INJECTED_MEMORY_PEER_FULL_GOLDEN_NO_BOARD_OR_REALTIME_FPS',io_mode=__import__('transport_fixture').MODE,timing_mode=__import__('transport_fixture').TIMING_MODE,"),
    ('from streaming_client import StreamingClient,PreparedGolden','from streaming_client import PreparedGolden\nfrom transport_fixture import tested_client as StreamingClient'),
    ('from host_regression import Peer,independent_audit','from host_regression_adapted import Peer,independent_audit'),
    ('HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]',f"HERE=Path(r'{HERE}');ROOT=Path(r'{ROOT}')"),
    ("        for f in range(2):assert client.transfer(ins[f],prepared[f],f)==gold[f]",
     "        try:\n            for f in range(2):assert client.transfer(ins[f],prepared[f],f)==gold[f]\n        except BaseException:\n            client.abort();raise"),
    ("base=ROOT/'host/baseline_ethernet/data'","base=ROOT/'main/data'"),
    ("hashlib.sha256((HERE/n).read_bytes()).hexdigest()",
     "hashlib.sha256((HERE/n).read_bytes() if n in ('check_host_window128.py','host_regression.py') else (HERE.parent/'streaming'/n).read_bytes()).hexdigest()")
]
for old,new in replacements:
    assert src.count(old)==1,old;src=src.replace(old,new)
adapted=ROOT/'validation/window128_adapted.py';adapted.write_text(src,encoding='utf-8')
runpy.run_path(str(adapted),run_name='__main__')
latest=json.loads((HERE/'LATEST_host_window128.json').read_text())
receipt=dict(status='PASS',saved_directory=latest['saved_directory'],
    executed_harness_sha256=hashlib.sha256(adapted.read_bytes()).hexdigest(),
    injected_peer_harness_sha256=hashlib.sha256((ROOT/'validation/host_regression_adapted.py').read_bytes()).hexdigest(),
    socket_created=False,board_io=False,io_mode=__import__('transport_fixture').MODE)
(ROOT/'WINDOW128_RUN.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
