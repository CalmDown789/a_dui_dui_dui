"""Add this candidate to the previously validated simulation collector."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
text = (ROOT / 'experiments/timing_200_20260926/collect_sim_evidence.py').read_text(encoding='utf-8')
text = text.replace('("v1", "v1-srl")', '("v1", "v1-srl", "v1-fifo-capacity")')
old = 'f"{EXP}/fifo_srl/elastic_fifo.sv" if use_srl else f"{OVERLAY}/b/elastic_fifo.sv",'
new = ('"experiments/timing_200_20261003/fifo_capacity/elastic_fifo.sv" if variant == "v1-fifo-capacity" '
       'else f"{EXP}/fifo_srl/elastic_fifo.sv" if use_srl else f"{OVERLAY}/b/elastic_fifo.sv",')
assert text.count(old)==1
text = text.replace(old, new)
old = '    require(sim_dir.name == expected_dir, f"Variant {variant} requires sim directory named {expected_dir}")'
assert text.count(old)==1
text = text.replace(old, '    if variant == "v1-fifo-capacity":\n'
                    '        expected_dir = "_sim_l5_member_b_acc36_fifo_capacity_20261003"\n'+old)
old = '    runner = resolve_repo_path(args.runner or f"{EXP}/run_sim_pipeline200{family_suffix}.tcl")'
assert text.count(old)==1
text = text.replace(old, '    default_runner = ("experiments/timing_200_20261003/run_sim_fifo_capacity.tcl" '
                    'if variant == "v1-fifo-capacity" else f"{EXP}/run_sim_pipeline200{family_suffix}.tcl")\n'
                    '    runner = resolve_repo_path(args.runner or default_runner)')
old = 'choices=("v1", "v1-srl", "v2",'
assert text.count(old)==1
text = text.replace(old, 'choices=("v1", "v1-srl", "v1-fifo-capacity", "v2",')
with (HERE / 'collect_sim_evidence.py').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write('# Member B: V1-derived FIFO capacity candidate, exact source/ROM/log verification.\n'+text)
print('FIFO_CAPACITY_SIM_COLLECTOR_PREPARED')
