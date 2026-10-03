"""Preserve strict simulation closure checks for actual C ROM + real B test."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=(HERE/'collect_pad_flags_sim.py').read_text(encoding='utf-8')
s=s.replace('v1-pad-flags','v1-rom-pipeline')
s=s.replace('tb_b_real_bit_exact','tb_c_rom_pipeline_bit_exact')
s=s.replace('_sim_l5_member_b_acc36_pad_flags_20261003','_sim_l5_member_b_acc36_rom_pipeline_20261003')
s=s.replace('run_sim_pad_flags.tcl','run_sim_rom_pipeline.tcl')
s=s.replace('f"{OVERLAY}/c/input_rom.v"','"experiments/timing_200_20261003/rom_pipeline/input_rom.v"')
s=s.replace('f"{OVERLAY}/c/input_stream.v"','"experiments/timing_200_20261003/rom_pipeline/input_stream.v"')
s=s.replace('f"tb/{tb}.v"','f"experiments/timing_200_20261003/rom_pipeline/{tb}.v"')
s=s.replace('"real five-layer B network" if tb in REAL_TBS','"actual C shell ROM/stream plus real five-layer B network" if tb in REAL_TBS')
s=s.replace('Simulation evidence only. Real-network and C isolation scopes are separate;',
            'Actual C shell/new ROM+stream and real B on four 96x54 cases; B output Golden/data/coordinate handshakes checked. UART decoded bytes are not checked; this is not the full 960x540 system test;')
target=HERE/'collect_rom_pipeline_sim.py'
with target.open('x',encoding='utf-8',newline='\n') as stream: stream.write(s)
print('ROM_PIPELINE_COLLECTOR_PREPARED')
