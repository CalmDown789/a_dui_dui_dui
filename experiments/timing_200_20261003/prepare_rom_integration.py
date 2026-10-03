"""Prepare actual C-shell + new ROM/stream + unchanged real-B short regression.

Retain the original four-case Golden checker. Observe B input/output actual
handshakes inside c_core, whose real ping-pong/UART path supplies backpressure.
No force, fabricated ready, alternate arithmetic or stub is used.
"""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
name='tb_c_rom_pipeline_bit_exact'

def replace_once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)

def create(path,text):
    with path.open('x',encoding='utf-8',newline='\n') as stream: stream.write(text)

tb=(ROOT/'tb/tb_b_real_bit_exact.v').read_text(encoding='utf-8')
tb=replace_once(tb,'module tb_b_real_bit_exact;','module '+name+';')
tb=replace_once(tb,'    reg  in_valid = 0;\n    reg  [7:0] in_data = 0;',
                   '    wire in_valid;\n    wire [7:0] in_data;')
tb=replace_once(tb,'    reg  out_ready = 0;','    wire out_ready;')
begin=tb.index('    b_core_if #(')
end=tb.index('    always #2.5 clk',begin)
tb=tb[:begin]+'''    wire c_busy,c_done;
    wire [15:0] input_x,input_y;
    c_core #(.IMG_W(IMG_W),.IMG_H(IMG_H),.OUT_W(OUT_W),.OUT_H(OUT_H),
        .STRIPE_H(STRIPE),.PIXEL_W(8),.ROM_ADDR_W(13),.ROM_DEPTH(8192),
        .ROM_INIT_MODE(0),.ROM_INIT_EN(0),.CLK_HZ(200000000),.UART_DIV(1)) core(
        .clk(clk),.rst_n(rst_n),.start(start),.busy(c_busy),.done(c_done),
        .rb_enable(1'b1),.dbg_in_x(input_x),.dbg_in_y(input_y));
    assign busy=core.b_busy;
    assign done=core.b_done;
    assign in_valid=core.in_valid;
    assign in_ready=core.in_ready;
    assign in_data=core.in_data;
    assign out_valid=core.b_out_valid;
    assign out_ready=core.out_ready;
    assign out_data=core.b_out_data;
    assign stripe_last=core.b_stripe_last;
    assign frame_last=core.b_frame_last;

'''+tb[end:]
tb=replace_once(tb,'            @(negedge clk);\n            if (busy',
                   '            @(negedge clk);\n            while (c_busy) @(negedge clk);\n            if (busy')
begin=tb.index('                if (fed < N_IN) begin')
end=tb.index('                if (held) begin',begin)
tb=tb[:begin]+'''                if (in_valid && in_ready) begin
                    if (fed>=N_IN || in_data!==in_mem[fed] ||
                        input_x!==(fed%IMG_W) || input_y!==(fed/IMG_W))
                        fail("C ROM/input stream data or coordinate mismatch");
                    fed=fed+1;
                end

'''+tb[end:]
tb=replace_once(tb,'            load_case(c);','''            load_case(c);
            // Load the same frozen short-case bytes into the actual bank RAM.
            // ROM_INIT_EN=0 avoids claiming these are the full-image banks.
            for (k=0;k<N_IN;k=k+1)
                core.u_rom.g_single_bank.u_bank.mem[k]=in_mem[k];''')
# Natural C backpressure may be absent for the first frame (two free banks).
# Keep per-case counts and require stall coverage across the whole sequence.
tb=replace_once(tb,'    integer tot_pass, tot_fail;',
                   '    integer tot_pass, tot_fail, total_held;')
tb=replace_once(tb,'        tot_pass = 0; tot_fail = 0;',
                   '        tot_pass = 0; tot_fail = 0; total_held=0;')
tb=replace_once(tb,'(x_cnt == 0) && (held_events > 0);','(x_cnt == 0);')
tb=replace_once(tb,'            if (held_events == 0)   fail("no stall cycles -- backpressure not exercised");',
                   '            total_held=total_held+held_events;')
tb=replace_once(tb,'        $display("  total cycles = %0d", cyc);',
                   '''        if (total_held==0) fail("C path supplied no output backpressure");
        $display("C_ROM_PIPELINE_INTEGRATION cycles=%0d output_stalls=%0d",cyc,total_held);
        $display("  total cycles = %0d", cyc);''')
tb='// Actual c_core integration; observe real B handshakes, Golden and C coordinates.\n'+tb
create(HERE/'rom_pipeline'/f'{name}.v',tb)

runner=(HERE/'run_sim_pad_flags.tcl').read_text(encoding='utf-8')
runner=replace_once(runner,'set tb_dir     "$root_dir/tb"','set tb_dir "$candidate_dir/rom_pipeline"')
runner=runner.replace('_sim_l5_member_b_acc36_pad_flags_20261003',
                      '_sim_l5_member_b_acc36_rom_pipeline_20261003')
runner=replace_once(runner,'set pipeline_tag "pad_flags_20261003"',
                   'set pipeline_tag "rom_pipeline_20261003"')
runner=replace_once(runner,'"$member_b_overlay_dir/rtl/c/input_rom.v"',
                   '"$candidate_dir/rom_pipeline/input_rom.v"')
runner=replace_once(runner,'"$member_b_overlay_dir/rtl/c/input_stream.v"',
                   '"$candidate_dir/rom_pipeline/input_stream.v"')
runner=runner.replace('tb_b_real_bit_exact',name)
runner=replace_once(runner,'set all_tbs [list tb_stripe_buffer tb_backpressure_rand tb_ready_valid tb_c_top \\\n                  tb_b_real_primitives \\\n                  tb_b_real_smoke tb_b_real_backpressure '+name+' tb_b_real_full]',
                   'set all_tbs [list '+name+']')
runner='//placeholder\n'.replace('//placeholder','# Actual C-shell ROM pipeline + real five-layer B integration only.\n')+runner
create(HERE/'run_sim_rom_pipeline.tcl',runner)
files=[Path(__file__),ROOT/'tb/tb_b_real_bit_exact.v',HERE/'rom_pipeline'/f'{name}.v',
       HERE/'run_sim_rom_pipeline.tcl',HERE/'rom_pipeline/input_rom.v',HERE/'rom_pipeline/input_stream.v']
manifest=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,
               sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
create(HERE/'rom_pipeline/integration_prepared_manifest.json',json.dumps(manifest,indent=2)+'\n')
print('C_ROM_REAL_B_INTEGRATION_PREPARED_NOT_RUN')
