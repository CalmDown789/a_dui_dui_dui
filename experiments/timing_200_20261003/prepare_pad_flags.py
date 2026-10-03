"""Prepare a cached-padding-boundary candidate, without starting simulation/impl."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'experiments/timing_200_20260926'

def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def create(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

pad = (ROOT / 'rtl/b_real_ae29515/stream/same_pad_raster.sv').read_text(encoding='utf-8')
create(HERE / 'pad_flags/same_pad_raster_reference.sv', once(pad, 'module same_pad_raster #(', 'module same_pad_raster_reference #('))
pad = once(pad, '''    wire interior = (x >= PAD) && (x < PAD+IMG_W) &&
                    (y >= PAD) && (y < PAD+IMG_H);''', '''    // Cache the CURRENT coordinate's interior flags. Boundary updates occur
    // on the same handshake edge as x/y, so there is no stream latency change.
    // KEEP preserves the flag registers but allows physical replication.
    (* KEEP = "TRUE" *) reg interior_x, interior_y;
    wire interior = interior_x && interior_y;
    localparam integer INITIAL_INTERIOR = (PAD == 0);
`ifndef SYNTHESIS
    always @(posedge clk) if (!rst) begin
        if (interior_x !== ((x >= PAD) && (x < PAD+IMG_W)) ||
            interior_y !== ((y >= PAD) && (y < PAD+IMG_H)))
            $fatal(1, "same_pad_raster: cached boundary differs from coordinate decode");
    end
`endif''')
anchor = '    always @(posedge clk) begin\n        if (rst) begin'
pad = once(pad, anchor, '''    always @(posedge clk) begin
        if (rst) begin
            interior_x <= INITIAL_INTERIOR;
            interior_y <= INITIAL_INTERIOR;
        end else if (!busy) begin
            if (start) begin
                interior_x <= INITIAL_INTERIOR;
                interior_y <= INITIAL_INTERIOR;
            end
        end else if (fire) begin
            if (out_last) begin
                interior_x <= INITIAL_INTERIOR;
                interior_y <= INITIAL_INTERIOR;
            end else if (x == PAD_W-1) begin
                interior_x <= INITIAL_INTERIOR;
                if (PAD > 0) begin
                    if (y == PAD-1) interior_y <= 1'b1;
                    else if (y == PAD+IMG_H-1) interior_y <= 1'b0;
                end
            end else if (PAD > 0) begin
                if (x == PAD-1) interior_x <= 1'b1;
                else if (x == PAD+IMG_W-1) interior_x <= 1'b0;
            end
        end
    end

''' + anchor)
create(HERE / 'pad_flags/same_pad_raster.sv', pad)
create(HERE / 'pad_flags/elastic_fifo.sv', (HERE / 'credit_eco_model/elastic_fifo.sv').read_text(encoding='utf-8'))

sim = (HERE / 'run_sim_credit_eco_model.tcl').read_text(encoding='utf-8')
sim = once(sim, '"$candidate_dir/credit_eco_model/elastic_fifo.sv"', '"$candidate_dir/pad_flags/elastic_fifo.sv"')
sim = once(sim, '"$b_real_dir/stream/same_pad_raster.sv"', '"$candidate_dir/pad_flags/same_pad_raster.sv"')
sim = sim.replace('credit_eco_20261003', 'pad_flags_20261003')
create(HERE / 'run_sim_pad_flags.tcl', sim)

collector = (HERE / 'collect_credit_eco_sim.py').read_text(encoding='utf-8')
collector = collector.replace('v1-credit-eco', 'v1-pad-flags').replace('credit_eco_model/elastic_fifo.sv', 'pad_flags/elastic_fifo.sv')
collector = collector.replace('_sim_l5_member_b_acc36_credit_eco_20261003', '_sim_l5_member_b_acc36_pad_flags_20261003')
collector = collector.replace('run_sim_credit_eco_model.tcl', 'run_sim_pad_flags.tcl')
collector = once(collector, 'f"{B_REAL}/same_pad_raster.sv",', '"experiments/timing_200_20261003/pad_flags/same_pad_raster.sv",')
create(HERE / 'collect_pad_flags_sim.py', collector)

synth = (OLD / 'synth_200_pipeline030.tcl').read_text(encoding='utf-8')
anchor = 'set root_dir   [file normalize "$script_dir/../.."]'
synth = once(synth, anchor, anchor + '\nset candidate_dir $script_dir\nset script_dir "$root_dir/experiments/timing_200_20260926"')
synth = once(synth, 'set fifo_file "$experiment_dir/rtl/b/elastic_fifo.sv"', 'set fifo_file "$candidate_dir/pad_flags/elastic_fifo.sv"')
synth = once(synth, '"$b_real_dir/stream/same_pad_raster.sv"', '"$candidate_dir/pad_flags/same_pad_raster.sv"')
synth = synth.replace('l5splitmem_realrom_200_member_b_pipeline0300926', 'l5splitmem_realrom_200_member_b_pad_flags_20261003_setup030')
synth = synth.replace('acc36_realrom_200_member_b_pipeline0300926', 'acc36_realrom_200_member_b_pad_flags_20261003_setup030')
synth = once(synth, 'file mkdir $out_dir', 'if {[file exists $stage]} {error "Refuse to overwrite candidate stage"}\nfile mkdir $out_dir')
anchor = 'foreach f [concat $c_files $b_files [list "$xdc_dir/c_top.xdc"]] {puts $mf $f}\nclose $mf'
synth = once(synth, anchor, anchor + '''
puts [exec "C:/Users/24889/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" -I \
    "$root_dir/experiments/timing_200_20260926/freeze_launch_inputs.py" $variant \
    "experiments/timing_200_20261003/synth_pad_flags.tcl"]''')
create(HERE / 'synth_pad_flags.tcl', '# V1 arithmetic + cached pad boundaries + credit memory write, setup030 search.\n' + synth)
paths = list((HERE / 'pad_flags').glob('*.sv')) + [HERE / 'run_sim_pad_flags.tcl', HERE / 'synth_pad_flags.tcl',
        HERE / 'collect_pad_flags_sim.py', Path(__file__).resolve()]
records = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
create(HERE / 'pad_flags/prepared_manifest.json', json.dumps(records, indent=2)+'\n')
print('PAD_FLAG_CANDIDATE_PREPARED_NOT_RUN')
