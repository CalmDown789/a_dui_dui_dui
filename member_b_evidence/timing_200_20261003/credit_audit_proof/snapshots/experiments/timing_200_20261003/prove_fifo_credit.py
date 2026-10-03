"""Exhaust an over-approximation of the actual frontend's credit states.

This is an abstract reachable-state proof with checked RTL input hashes,
not machine-extracted formal RTL/netlist equivalence or a board test.
window_kminus1_bram.read_valid_d and frontend.pending1 receive pad_fire with
the same synchronous reset. raw_valid therefore implies pending2. Allow an
arbitrary crop bit per cycle, arbitrary downstream ready, arbitrary pad_valid,
and arbitrary resets: this contains every actual frame geometry/stall pattern.
"""
from collections import deque
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '_synth_bc/postroute200_v1_nominal000_20261003_try2'
source_manifest = json.loads((BASE / 'input/baseline_reports/launch_source_manifest.json').read_text())
paths = ['rtl/b_real_ae29515/stream/window_stream_frontend.sv',
         'rtl/b_real_ae29515/stream/window_kminus1_bram.sv',
         'experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv']
inputs=[]
for name in paths:
    data=(ROOT / name).read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    original=next(item for item in source_manifest if item['path']==name)
    assert sha==original['sha256'], ('RTL differs from retained DCP', name)
    inputs.append(dict(path=name, sha256=sha))

initial=(0,0,0)  # count, pending1, pending2
visited={initial}
work=deque([initial])
checked=0
transitions=[]
while work:
    count,p1,p2=state=work.popleft()
    assert 0<=count<=4 and count+p1+p2<=4
    for pad_valid,crop,out_ready,reset in itertools.product((0,1), repeat=4):
        raw_valid=p2 and crop
        pad_fire=pad_valid and count+p1+p2<4
        pop=count>0 and out_ready
        original_push=raw_valid and (count<4 or pop)
        guarded_push=raw_valid and count<4
        # FIFO RAM truth-table change differs only at raw_valid=full=ready=1.
        assert not (raw_valid and count==4)
        assert original_push==guarded_push
        after=initial if reset else (count+int(original_push)-int(pop), int(pad_fire), p1)
        assert 0<=after[0]<=4 and sum(after)<=4
        checked+=1
        transitions.append(dict(before=state, inputs=[pad_valid,crop,out_ready,reset], after=after,
                                original_write=int(original_push), guarded_write=int(guarded_push)))
        if after not in visited:
            visited.add(after);work.append(after)

# Verify the independently audited LUT3 input order and the one-bit change.
truth=[]
for full,ready,valid in itertools.product((0,1), repeat=3):
    address=valid+2*ready+4*full
    original=(0x8A>>address)&1
    guarded=(0x0A>>address)&1
    assert original==int(valid and (not full or ready))
    assert guarded==int(valid and not full)
    assert original==guarded or (full and ready and valid)
    truth.append(dict(I0_raw_valid=valid,I1_window_ready=ready,I2_full=full,
                      original=original,guarded=guarded))
result=dict(status='ABSTRACT_REACHABLE_CREDIT_PROOF_PASS',
            depth=4, reachable_states=sorted(visited), checked_transitions=checked,
            impossible_branch='raw_valid && count==4',
            RTL_inputs=inputs, LUT_truth_table=truth, transitions=transitions,
            scope='Frontend over-approximation, all stalls/crops/resets; checked source hashes. Not extracted formal equivalence, gate simulation, or board validation.',
            observable_reason='RAM writes remain identical; old FIFO ready/count/pointers are retained by ECO. Only an unreachable RAM-write minterm changes.')
target=ROOT / 'experiments/timing_200_20261003/fifo_credit_proof.json'
with target.open('x',encoding='utf-8') as stream:
    json.dump(result,stream,indent=2);stream.write('\n')
print(f'ABSTRACT_REACHABLE_CREDIT_PROOF_PASS states={len(visited)} transitions={checked}')
