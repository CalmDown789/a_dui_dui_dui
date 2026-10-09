"""Bounded retained-window regression with full frozen frames; no sockets."""
from pathlib import Path
import hashlib,json,tempfile,time
from host_regression_adapted import Peer,independent_audit
from streaming_client import PreparedGolden
from transport_fixture import tested_client as StreamingClient
HERE=Path(r'C:\t6int09\main\proof');ROOT=Path(r'C:\t6int09')
def main():
    out=HERE/'host_runs'/Path(tempfile.mkdtemp(prefix='pld_host_window128_')).name;out.mkdir(parents=True)
    base=ROOT/'main/data';manifest=json.loads((base/'ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
    ins=[];gold=[]
    for r in manifest['frames'][:2]:
        for k,d in [('input',ins),('golden',gold)]:
            b=(base/r[k+'_file']).read_bytes();assert hashlib.sha256(b).hexdigest()==r[k+'_sha256'];d.append(b)
    prepared=[PreparedGolden(b)for b in gold];sid=bytes(range(16));rows=[]
    for fault in (None,'drop_output_packet','drop_output_ack','reorder_output','duplicate_output','bad_output_payload_crc','drop_final_reply'):
        peer=Peer(ins,gold,fault);d=out/(fault or 'normal');client=StreamingClient(peer,peer.address,sid,d,output_window=128,frame_timeout=30)
        t=time.perf_counter_ns();client.hello()
        try:
            for f in range(2):assert client.transfer(ins[f],prepared[f],f)==gold[f]
        except BaseException:
            client.abort();raise
        client.finish();audit=independent_audit(d,ins,gold,sid)
        assert peer.frame_acks==2 and peer.max_queue<=256 and client.max_retained<=16 and client.max_inbox<=128
        rows.append(dict(fault=fault or 'normal',status='PASS',raw_audit=audit,releases=peer.frame_acks,max_peer_queue=peer.max_queue,max_input_retained=client.max_retained,max_inbox=client.max_inbox,offline_wall_ns=time.perf_counter_ns()-t))
        print(f'WINDOW128_CASE={fault or "normal"} PASS',flush=True)
    result=dict(status='PASS',rows=rows,output_window=128,scope='INJECTED_MEMORY_PEER_FULL_GOLDEN_NO_BOARD_OR_REALTIME_FPS',io_mode=__import__('transport_fixture').MODE,timing_mode=__import__('transport_fixture').TIMING_MODE,socket_created=False,
        source_sha256={n:hashlib.sha256((HERE/n).read_bytes() if n in ('check_host_window128.py','host_regression.py') else (HERE.parent/'streaming'/n).read_bytes()).hexdigest() for n in ('check_host_window128.py','host_regression.py','streaming_client.py','stream_receiver.py','binary_journal.py','audit_protocol.py','timing_diagnostics.py','nonblocking_io.py')})
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (HERE/'LATEST_host_window128.json').write_text(json.dumps(dict(saved_directory=str(out)),ensure_ascii=False),encoding='utf-8')
    print('HOST_WINDOW128_PASS '+str(out),flush=True)
if __name__=='__main__':main()
