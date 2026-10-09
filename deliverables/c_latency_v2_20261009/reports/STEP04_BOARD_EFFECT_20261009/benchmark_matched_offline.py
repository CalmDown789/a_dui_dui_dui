"""Same data, PreparedGolden, callback, socket parameters and timing boundary as board."""
from pathlib import Path
import argparse, hashlib, json, sys, time
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]/'output/HOST_STEP04_SAMPLED_TIMING_20261009'
ap = argparse.ArgumentParser()
ap.add_argument('variant', choices=['step03_full','step04_sampled'])
ap.add_argument('out', type=Path)
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
prefix = 'baseline' if a.variant == 'step03_full' else 'main'
sys.path[:0] = [str(ROOT/prefix/'streaming'), str(ROOT/prefix/'host'), str(ROOT/'validation')]
from streaming_client import StreamingClient, PreparedGolden
from transport_fixture import NonblockingPeer
from host_regression_adapted import Peer, independent_audit
manifest = json.loads((ROOT/'main/data/ETHERNET_SEQUENCE_MANIFEST.json').read_text(encoding='utf-8'))
inputs, goldens = [], []
for row in manifest['frames'][:2]:
    for name, target in [('input', inputs), ('golden', goldens)]:
        raw = (ROOT/'main/data'/row[name+'_file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row[name+'_sha256']
        target.append(raw)
prepared = [PreparedGolden(raw) for raw in goldens]
peer = Peer(inputs, goldens)
transport = NonblockingPeer(peer)
session = bytes(range(16))
kw = dict(output_window=128, timeout=.02, attempts=4, frame_timeout=10.,
          io_mode='nonblocking', readiness_waiter=transport.wait_ready)
if prefix == 'main': kw.update(timing_mode='sampled', timing_sample_every=16)
c = StreamingClient(transport, peer.address, session, a.out/'traffic', **kw)
actual = []
with (a.out/'frame_events.jsonl').open('x', encoding='utf-8') as event_file:
    def accept(data, identity):
        f = len(actual)
        assert identity['frame_id'] == f and identity['golden_match'] is True
        assert identity['integrity_sha256'] == prepared[f].sha256 and data == goldens[f]
        actual.append(data)
        event_file.write(json.dumps(dict(event='VALIDATED_FRAME_ACCEPTED', monotonic_ns=time.perf_counter_ns(),
                                        frame_id=f, identity=identity))+'\n')
        event_file.flush()
    began = time.perf_counter_ns(); cpu_began = time.thread_time_ns()
    c.hello(); negotiated = time.perf_counter_ns()
    for f in range(2):
        assert c.transfer(inputs[f], prepared[f], f, accept) is actual[f]
        print(json.dumps(dict(event='FRAME_COMPLETE', frame=f, metrics=c.frames[-1])), flush=True)
    end = time.perf_counter_ns(); cpu_end = time.thread_time_ns()
c.finish()
audit = independent_audit(a.out/'traffic', inputs, goldens, session)
report = dict(status='PASS', variant=a.variant, frames=c.frames, audit=audit,
              hello_and_two_frames_wall_ns=end-began, protocol_loop_wall_ns=end-negotiated,
              hello_wall_ns=negotiated-began, calling_thread_cpu_ns=cpu_end-cpu_began,
              retries=c.retries, ignored=c.ignored, callback_and_prepared_golden_match_board=True,
              peer_simulation_executes_in_calling_thread=True,
              input_and_golden_sha256=[{k:row[k] for k in ('input_sha256','golden_sha256')} for row in manifest['frames'][:2]])
(a.out/'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(dict(status=report['status'], variant=a.variant,
                     frame_ms=[r['timing_ns']['whole']/1e6 for r in c.frames])), flush=True)
