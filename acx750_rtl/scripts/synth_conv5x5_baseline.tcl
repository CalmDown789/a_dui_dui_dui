set work_dir [file normalize [lindex $argv 0]]
set out_dir [file normalize [lindex $argv 1]]
set target_part [lindex $argv 2]
file mkdir $out_dir

read_verilog [file join $work_dir dsp_signed_mult.v]
read_verilog [file join $work_dir dot25_pipeline.v]
read_verilog [file join $work_dir channel_accumulator.v]
read_verilog [file join $work_dir conv5x5_backend.v]
read_xdc [file join $work_dir clock_200mhz_benchmark.xdc]

synth_design -top conv5x5_backend -part $target_part \
    -generic ACT_W=8 -generic WGT_W=8 -generic ACC_W=32 \
    -generic CHANNELS=1 -mode out_of_context -flatten_hierarchy rebuilt

report_utilization -hierarchical \
    -file [file join $out_dir conv5x5_utilization.rpt]
report_timing_summary -delay_type max -report_unconstrained \
    -file [file join $out_dir conv5x5_timing_synth.rpt]

set dsp_cells [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
puts "ACX750_CONV5X5_DSP48E1=[llength $dsp_cells]"
puts "ACX750_CONV5X5_PART=$target_part"
puts "ACX750_CONV5X5_SYNTH_DONE"
