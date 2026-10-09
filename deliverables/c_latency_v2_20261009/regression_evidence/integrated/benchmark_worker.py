"""Fresh interpreter separates step03 baseline imports from step04 imports."""
from pathlib import Path
import argparse,hashlib,json,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('variant',choices=['step03_full','step04_full','step04_sampled'])
parser.add_argument('out');args=parser.parse_args()
prefix='baseline'if args.variant=='step03_full'else 'main'
sys.path.insert(0,str(ROOT/prefix/'host'));sys.path.insert(0,str(ROOT/prefix/'streaming'))
from streaming_client import StreamingClient
from transport_fixture import NonblockingPeer
from host_regression_adapted import Peer,independent_audit
data=ROOT/'main/data';manifest=json.loads((data/'ETHERNET_SEQUENCE_MANIFEST.json').read_text())
inputs=[];goldens=[]
for row in manifest['frames'][:2]:
    for kind,dest in [('input',inputs),('golden',goldens)]:
        raw=(data/row[kind+'_file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row[kind+'_sha256'];dest.append(raw)
peer=Peer(inputs,goldens);transport=NonblockingPeer(peer);out=Path(args.out)
kw=dict(output_window=128,io_mode='nonblocking',readiness_waiter=transport.wait_ready)
if prefix=='main':kw['timing_mode']='sampled'if args.variant=='step04_sampled'else 'full'
c=StreamingClient(transport,peer.address,bytes(range(16)),out,**kw)
began=time.perf_counter_ns();cpu_began=time.thread_time_ns();c.hello()
for f in range(2):assert c.transfer(inputs[f],goldens[f],f)==goldens[f]
cpu_ns=time.thread_time_ns()-cpu_began;wall_ns=time.perf_counter_ns()-began
c.finish();audit=independent_audit(out,inputs,goldens,bytes(range(16)))
assert peer.frame_acks==2 and all(row['output_duplicate_packets']==0 for row in c.frames)
timing=json.loads((out/'TIMING_DIAGNOSTICS.json').read_text())
assert timing['stages']['frame_transfer']['count']==2
hot=('scheduled_send','scheduled_receive','decode_header_payload_crc','output_receiver_validate_store_deduplicate','journal_append','proof_batch_take','proof_packet_build')
result=dict(status='PASS',variant=args.variant,wall_ns=wall_ns,calling_thread_cpu_ns=cpu_ns,
    fine_timing_samples=sum(timing['stages'].get(name,{}).get('count',0)for name in hot),
    stage_samples={name:timing['stages'].get(name,{}).get('count',0)for name in hot},
    frame_timing_samples=timing['stages']['frame_transfer']['count'],
    journal_records=c.journal.records,raw_directory=str(out),golden_bytes=4147200,
    output_duplicate_packets=0,proof_ack_datagrams=sum(row['proof_ack_datagrams']for row in c.frames),
    profiling=timing.get('profiling'),audit_status=audit['status'],
    source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
        [Path(__file__),ROOT/'validation/transport_fixture.py',ROOT/'validation/host_regression_adapted.py']+
        [ROOT/prefix/'streaming'/name for name in ('streaming_client.py','nonblocking_io.py','binary_journal.py','timing_diagnostics.py','stream_receiver.py','audit_protocol.py')]})
(out/'BENCHMARK.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(status='PASS',variant=args.variant,wall_ns=wall_ns,calling_thread_cpu_ns=cpu_ns)))
