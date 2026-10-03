"""Reuse implementation acceptance checks with this round's output directory."""
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
text = (ROOT / 'experiments/timing_200_20260926/collect_evidence.py').read_text(encoding='utf-8')
old = "dest = ROOT / 'member_b_evidence/timing_200_20260926' / args.name"
assert text.count(old)==1
text = text.replace(old, "dest = ROOT / 'member_b_evidence/timing_200_20261003' / args.name")
old = "version, pipeline_prefix = pipeline_runners.get(runner.name, ('baseline_or_single_candidate', None))"
assert text.count(old)==1
text = text.replace(old, "pipeline_runners['synth_fifo_capacity.tcl'] = ('V1-fifo-capacity', None)\n"+old)
with (HERE / 'collect_evidence.py').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write('# Member B: preserve original acceptance/hash checks; archive the capacity-only candidate.\n'+text)
print('FIFO_CAPACITY_IMPLEMENTATION_COLLECTOR_PREPARED')
