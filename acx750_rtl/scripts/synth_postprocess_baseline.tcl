set work_dir [file normalize [lindex $argv 0]]
set out_dir [file normalize [lindex $argv 1]]
set target_part [lindex $argv 2]
set out_width [lindex $argv 3]
set out_signed [lindex $argv 4]
set apply_prelu [lindex $argv 5]
set label [lindex $argv 6]
file mkdir $out_dir

read_verilog -sv [file join $work_dir prelu_requantize.sv]
read_xdc [file join $work_dir clock_200mhz_benchmark.xdc]

synth_design -top prelu_requantize -part $target_part \
    -generic OUT_W=$out_width -generic OUT_SIGNED=$out_signed \
    -generic APPLY_PRELU=$apply_prelu -mode out_of_context \
    -flatten_hierarchy rebuilt

report_utilization -hierarchical \
    -file [file join $out_dir ${label}_utilization.rpt]
report_timing_summary -delay_type max -report_unconstrained \
    -file [file join $out_dir ${label}_timing_synth.rpt]
write_checkpoint -force [file join $out_dir ${label}_synth.dcp]

set dsp_cells [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
puts "ACX750_POSTPROCESS_LABEL=$label"
puts "ACX750_POSTPROCESS_DSP48E1=[llength $dsp_cells]"
puts "ACX750_POSTPROCESS_PART=$target_part"
puts "ACX750_POSTPROCESS_SYNTH_DONE"
