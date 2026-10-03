"""Create a simulation model of the nine-LUT ECO, not a resynthesis candidate.

Original FIFO handshake, pointers and count are unchanged. Only L5 memory
write-enable loses the full+pop term. Runtime assertion checks the frontend
credit premise, including every valid input in the full-frame test.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'experiments/timing_200_20260926'

def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def create(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

fifo = (ROOT / 'experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv').read_text(encoding='utf-8')
fifo = replace_once(fifo, '    wire push = in_valid && in_ready;', '''    wire push = in_valid && in_ready;
    // RTL behavioral model of post-route LUT3 INIT 8'h8A -> 8'h0A.
    // The original ready/count/pointer logic below remains unchanged.
    // This is equivalent ONLY in this frontend's reachable credit states;
    // it is not an unconstrained replacement for a standalone FIFO.
    localparam integer L5_CREDIT_ECO = (DATA_W == 6400 && DEPTH == 4);
    wire memory_push = L5_CREDIT_ECO ? (in_valid && count < DEPTH) : push;
`ifndef SYNTHESIS
    initial if (L5_CREDIT_ECO)
        $display("L5_CREDIT_ECO_MEMORY_MODEL_ASSERTION_ENABLED");
    always @(posedge clk) begin
        if (!rst && L5_CREDIT_ECO) begin
            if (in_valid && count >= DEPTH)
                $fatal(1, "L5_CREDIT_ECO: unreachable full+valid premise violated");
            if (memory_push !== push)
                $fatal(1, "L5_CREDIT_ECO: memory write differs from original push");
        end
    end
`endif''')
assert fifo.count('if (push)') == 3
# Only the two memory write conditions, not the pointer control.
fifo = replace_once(fifo, 'if (push)\n                        mem_slice', 'if (memory_push)\n                        mem_slice')
fifo = replace_once(fifo, 'if (push)\n                    mem[', 'if (memory_push)\n                    mem[')
create(HERE / 'credit_eco_model/elastic_fifo.sv', fifo)

sim = (OLD / 'run_sim_pipeline200.tcl').read_text(encoding='utf-8')
anchor = 'set root_dir   [file normalize "$script_dir/../.."]'
sim = replace_once(sim, anchor, anchor + '\nset candidate_dir $script_dir\nset script_dir "$root_dir/experiments/timing_200_20260926"')
sim = replace_once(sim, 'set pipeline_fifo_file "$member_b_overlay_dir/rtl/b/elastic_fifo.sv"',
                   'set pipeline_fifo_file "$candidate_dir/credit_eco_model/elastic_fifo.sv"')
sim = replace_once(sim, 'set sim_root   "$root_dir/_sim_l5_member_b_acc36_pipeline200"',
                   'set sim_root   "$root_dir/_sim_l5_member_b_acc36_credit_eco_20261003"')
sim = replace_once(sim, 'set pipeline_tag "pipeline200"', 'set pipeline_tag "credit_eco_20261003"')
create(HERE / 'run_sim_credit_eco_model.tcl', '# Behavioral memory-write model of LUT ECO; not gate-level simulation.\n' + sim)

collector = (OLD / 'collect_sim_evidence.py').read_text(encoding='utf-8')
collector = collector.replace('("v1", "v1-srl")', '("v1", "v1-srl", "v1-credit-eco")')
collector = replace_once(collector, 'f"{EXP}/fifo_srl/elastic_fifo.sv" if use_srl else f"{OVERLAY}/b/elastic_fifo.sv",',
    '"experiments/timing_200_20261003/credit_eco_model/elastic_fifo.sv" if variant == "v1-credit-eco" else f"{EXP}/fifo_srl/elastic_fifo.sv" if use_srl else f"{OVERLAY}/b/elastic_fifo.sv",')
anchor = '    require(sim_dir.name == expected_dir, f"Variant {variant} requires sim directory named {expected_dir}")'
collector = replace_once(collector, anchor,
    '    if variant == "v1-credit-eco":\n        expected_dir = "_sim_l5_member_b_acc36_credit_eco_20261003"\n' + anchor)
collector = replace_once(collector, '    runner = resolve_repo_path(args.runner or f"{EXP}/run_sim_pipeline200{family_suffix}.tcl")',
    '    default_runner = ("experiments/timing_200_20261003/run_sim_credit_eco_model.tcl" if variant == "v1-credit-eco" else f"{EXP}/run_sim_pipeline200{family_suffix}.tcl")\n    runner = resolve_repo_path(args.runner or default_runner)')
collector = replace_once(collector, 'choices=("v1", "v1-srl", "v2",', 'choices=("v1", "v1-srl", "v1-credit-eco", "v2",')
create(HERE / 'collect_credit_eco_sim.py', '# Exact source/ROM evidence for behavioral ECO model, not gate-level equivalence.\n' + collector)
paths = [HERE / 'credit_eco_model/elastic_fifo.sv', HERE / 'run_sim_credit_eco_model.tcl',
         HERE / 'collect_credit_eco_sim.py', Path(__file__).resolve()]
records = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
create(HERE / 'credit_eco_model/prepared_manifest.json', json.dumps(records, indent=2)+'\n')
print('CREDIT_ECO_BEHAVIORAL_SIM_PREPARED')
