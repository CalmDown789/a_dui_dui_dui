"""Prepare separate actual-C and B-only tests for the direct-head sequencer."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def create(path,s):
    with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(s)
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)

c=(HERE/'run_sim_rom_pipeline.tcl').read_text(encoding='utf-8')
c=once(c,'"$b_real_dir/stream/eight_phase_issue.sv"','"$candidate_dir/issue_head/eight_phase_issue.sv"')
c=c.replace('_sim_l5_member_b_acc36_rom_pipeline_20261003','_sim_l5_member_b_acc36_issue_head_c_20261003')
c=once(c,'set pipeline_tag "rom_pipeline_20261003"','set pipeline_tag "issue_head_c_20261003"')
create(HERE/'run_sim_issue_head_c.tcl',c)
c=(HERE/'collect_rom_pipeline_sim.py').read_text(encoding='utf-8')
c=c.replace('v1-rom-pipeline','v1-rom3-head-c')
c=c.replace('run_sim_rom_pipeline.tcl','run_sim_issue_head_c.tcl')
c=c.replace('_sim_l5_member_b_acc36_rom_pipeline_20261003','_sim_l5_member_b_acc36_issue_head_c_20261003')
c=once(c,'f"{B_REAL}/eight_phase_issue.sv"','"experiments/timing_200_20261003/issue_head/eight_phase_issue.sv"')
create(HERE/'collect_issue_head_c_sim.py',c)

b=(HERE/'run_sim_pad_flags.tcl').read_text(encoding='utf-8')
b=once(b,'"$b_real_dir/stream/eight_phase_issue.sv"','"$candidate_dir/issue_head/eight_phase_issue.sv"')
b=once(b,'"$member_b_overlay_dir/rtl/c/input_rom.v"','"$candidate_dir/rom_pipeline/input_rom.v"')
b=once(b,'"$member_b_overlay_dir/rtl/c/input_stream.v"','"$candidate_dir/rom_pipeline/input_stream.v"')
b=b.replace('_sim_l5_member_b_acc36_pad_flags_20261003','_sim_l5_member_b_acc36_issue_head_b_20261003')
b=once(b,'set pipeline_tag "pad_flags_20261003"','set pipeline_tag "issue_head_b_20261003"')
create(HERE/'run_sim_issue_head_b.tcl',b)
b=(HERE/'collect_pad_flags_sim.py').read_text(encoding='utf-8')
b=b.replace('v1-pad-flags','v1-rom3-head-b')
b=b.replace('run_sim_pad_flags.tcl','run_sim_issue_head_b.tcl')
b=b.replace('_sim_l5_member_b_acc36_pad_flags_20261003','_sim_l5_member_b_acc36_issue_head_b_20261003')
b=once(b,'f"{B_REAL}/eight_phase_issue.sv"','"experiments/timing_200_20261003/issue_head/eight_phase_issue.sv"')
b=once(b,'f"{OVERLAY}/c/input_rom.v"','"experiments/timing_200_20261003/rom_pipeline/input_rom.v"')
b=once(b,'f"{OVERLAY}/c/input_stream.v"','"experiments/timing_200_20261003/rom_pipeline/input_stream.v"')
b=once(b,'Simulation evidence only. Real-network and C isolation scopes are separate;',
          'Direct FIFO-head B sequencer tested via b_core_if; C modules are compiled but unused by these B-only tests;')
create(HERE/'collect_issue_head_b_sim.py',b)
print('ISSUE_HEAD_SIM_RUNNERS_PREPARED')
