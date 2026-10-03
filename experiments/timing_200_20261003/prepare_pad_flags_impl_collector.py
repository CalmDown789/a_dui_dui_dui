"""Keep previous acceptance checks, adding a named pad-boundary candidate."""
from pathlib import Path
HERE = Path(__file__).resolve().parent
text = (HERE / 'collect_evidence.py').read_text(encoding='utf-8')
anchor = "pipeline_runners['synth_fifo_capacity.tcl'] = ('V1-fifo-capacity', None)"
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + "\npipeline_runners['synth_pad_flags.tcl'] = ('V1-pad-flags-credit-memory', None)")
with (HERE / 'collect_pad_flags_impl.py').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
print('PAD_FLAGS_IMPLEMENTATION_COLLECTOR_PREPARED')
