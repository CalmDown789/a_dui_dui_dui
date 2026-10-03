"""Prepare one V1-derived L5 window FIFO control candidate; never run tools."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OLD = ROOT / 'experiments/timing_200_20260926'

def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def create(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

fifo = (ROOT / 'experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv').read_text(encoding='utf-8')
fifo = replace_once(fifo, '    assign in_ready = (count < DEPTH) || pop;',
    '''    // Member B 2026-10-03: only the frozen L5 25*16*16-bit window FIFO.
    // Full+pop rejects a new input for this configuration, removing the
    // downstream MAC-ready -> issue -> pop -> wide RAM write-enable cone.
    // The frontend's two outstanding reservations protect raw_window input;
    // overflow and frame/Golden tests must still pass with this exact source.
    // Other layer FIFOs retain their original look-ahead behavior.
    localparam integer L5_WINDOW_CAPACITY_ONLY = (DATA_W == 6400 && DEPTH == 4);
    assign in_ready = (count < DEPTH) || (!L5_WINDOW_CAPACITY_ONLY && pop);''')
create(HERE / 'fifo_capacity/elastic_fifo.sv', fifo)

anchor = 'set root_dir   [file normalize "$script_dir/../.."]'
alias = anchor + '\nset candidate_dir $script_dir\nset script_dir "$root_dir/experiments/timing_200_20260926"'
synth = (OLD / 'synth_200_pipeline030.tcl').read_text(encoding='utf-8')
synth = replace_once(synth, anchor, alias)
synth = replace_once(synth, 'set fifo_file "$experiment_dir/rtl/b/elastic_fifo.sv"',
                     'set fifo_file "$candidate_dir/fifo_capacity/elastic_fifo.sv"')
synth = synth.replace('l5splitmem_realrom_200_member_b_pipeline0300926',
                      'l5splitmem_realrom_200_member_b_fifo_capacity_20261003_nominal')
synth = synth.replace('acc36_realrom_200_member_b_pipeline0300926',
                      'acc36_realrom_200_member_b_fifo_capacity_20261003_nominal')
synth = replace_once(synth, 'set setup_tag "setup030"\nset setup_extra_ns 0.300',
                     'set setup_tag "setup000"\nset setup_extra_ns 0.000')
synth = replace_once(synth, 'file mkdir $out_dir',
                     'if {[file exists $stage]} {error "Refuse to overwrite candidate stage"}\nfile mkdir $out_dir')
manifest_anchor = 'foreach f [concat $c_files $b_files [list "$xdc_dir/c_top.xdc"]] {puts $mf $f}\nclose $mf'
synth = replace_once(synth, manifest_anchor, manifest_anchor + '''
puts [exec "C:/Users/24889/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" -I \
    "$root_dir/experiments/timing_200_20260926/freeze_launch_inputs.py" $variant \
    "experiments/timing_200_20261003/synth_fifo_capacity.tcl"]''')
create(HERE / 'synth_fifo_capacity.tcl', '# Member B: V1 + L5 FIFO capacity-only ready, nominal 200 MHz.\n'+synth)

sim = (OLD / 'run_sim_pipeline200.tcl').read_text(encoding='utf-8')
sim = replace_once(sim, anchor, alias)
sim = replace_once(sim, 'set pipeline_fifo_file "$member_b_overlay_dir/rtl/b/elastic_fifo.sv"',
                   'set pipeline_fifo_file "$candidate_dir/fifo_capacity/elastic_fifo.sv"')
sim = replace_once(sim, 'set sim_root   "$root_dir/_sim_l5_member_b_acc36_pipeline200"',
                   'set sim_root   "$root_dir/_sim_l5_member_b_acc36_fifo_capacity_20261003"')
sim = replace_once(sim, 'set pipeline_tag "pipeline200"', 'set pipeline_tag "fifo_capacity_20261003"')
create(HERE / 'run_sim_fifo_capacity.tcl', '# Member B: exact V1-derived capacity-only FIFO source closure.\n'+sim)
paths = [HERE / 'fifo_capacity/elastic_fifo.sv', HERE / 'synth_fifo_capacity.tcl',
         HERE / 'run_sim_fifo_capacity.tcl', Path(__file__).resolve()]
data = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size,
             sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
create(HERE / 'fifo_capacity/prepared_manifest.json', json.dumps(dict(
    status='PREPARED_NOT_RUN', baseline='V1 nominal', inputs=data), indent=2)+'\n')
print('L5_FIFO_CAPACITY_CANDIDATE_PREPARED_NOT_RUN')
