"""Run the existing injected-host regression against this candidate's source."""
from pathlib import Path
import runpy,sys
sys.dont_write_bytecode=True

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'main' / 'proof' / 'host_regression.py'
VALIDATION = ROOT / 'validation'
PROOF = ROOT / 'main' / 'proof'
STREAMING = ROOT / 'main' / 'streaming'
HOST_DATA = ROOT / 'main' / 'host' / 'baseline_ethernet' / 'data'
SCRIPT = VALIDATION / 'host_regression_adapted.py'

sys.path.insert(0,str(VALIDATION))

source = SOURCE.read_text(encoding='utf-8')
replacements = [
    ("'scope':'INJECTED_MEMORY_PEER_NO_SR_NETWORK_OS_PC4K_FRAME_RATE',",
     "'scope':'INJECTED_MEMORY_PEER_NO_SR_NETWORK_OS_PC4K_FRAME_RATE','io_mode':__import__('transport_fixture').MODE,'timing_mode':__import__('transport_fixture').TIMING_MODE,"),
    ("HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]\n"
     "sys.path.insert(0,str(HERE.parent/'sources/host'));sys.path.insert(0,str(HERE.parent/'optimization_20261007'))",
     f"HERE=Path(r'{PROOF}');ROOT=Path(r'{ROOT}')\n"
     "sys.path.insert(0,str(HERE.parent/'streaming'));sys.path.insert(0,str(HERE.parent/'host'))"),
    ("from window_model import Sender\n", ""),
    ("from streaming_client import StreamingClient,encode2,decode_any\n",
     "from streaming_client import StreamingClient,encode2,decode_any\n" + "from injected_sender import Sender\nfrom transport_fixture import tested_client as StreamingClient\n"),
    ("if fault=='duplicate_output':self.queue.appendleft((raw,source));self.injected=True\n",
     "if fault=='duplicate_output':self.queue.appendleft((raw,source));self.injected=True\n"
     "            if fault=='changed_duplicate':\n"
     "                altered=replace(p,payload=bytes([p.payload[0]^1])+p.payload[1:]);self.queue.appendleft((encode2(altered),source));self.injected=True\n"),
    ("'early_output_crc','bad_output_last','duplicate_output','reorder_output','core_done_late','drop_final_reply']",
     "'early_output_crc','bad_output_last','duplicate_output','changed_duplicate','reorder_output','core_done_late','drop_final_reply']"),
    ("for f in range(2):assert client.transfer(inputs[f],goldens[f],f,callback)==goldens[f]\n",
     "for f in range(2):assert client.transfer(inputs[f],goldens[f],f,callback)==goldens[f]\n"
     "            if fault=='changed_duplicate':assert client.frames[0]['output_rejected_packets']>0\n"),
    ("saved=HERE/'host_runs'/Path(tempfile.mkdtemp(prefix='pld_stream_host_')).name;saved.mkdir(parents=True)",
     f"saved=Path(r'{VALIDATION/'host_regression_runs'}')/Path(tempfile.mkdtemp(prefix='pld_stream_host_')).name;saved.mkdir(parents=True)"),
    ("base=ROOT/'host/baseline_ethernet/data'", "base=ROOT/'main/data'"),
    ("(HERE/'LATEST_host.json').write_text(json.dumps({'saved_directory':str(saved)},ensure_ascii=False),encoding='utf-8')",
     f"(Path(r'{VALIDATION/'LATEST_host.json'}')).write_text(json.dumps({{'saved_directory':str(saved)}},ensure_ascii=False),encoding='utf-8')"),
    ("'source_sha256':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('host_regression.py','streaming_client.py','stream_receiver.py','binary_journal.py','audit_protocol.py')}",
     "'source_sha256':{n:hashlib.sha256((HERE/n).read_bytes() if n=='host_regression.py' else (HERE.parent/'streaming'/n).read_bytes()).hexdigest() for n in ('host_regression.py','streaming_client.py','stream_receiver.py','binary_journal.py','audit_protocol.py','timing_diagnostics.py','nonblocking_io.py')}")
]
for old, new in replacements:
    if source.count(old) != 1:
        raise RuntimeError(f'expected one regression-harness anchor, found {source.count(old)}: {old[:80]}')
    source = source.replace(old, new)
SCRIPT.write_text(source, encoding='utf-8', newline='\n')
runpy.run_path(str(SCRIPT), run_name='__main__')
