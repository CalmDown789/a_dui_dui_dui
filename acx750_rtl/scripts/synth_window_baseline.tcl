set work_dir [file normalize [lindex $argv 0]]
set out_dir [file normalize [lindex $argv 1]]
set target_part [lindex $argv 2]
set top_name [lindex $argv 3]
set source_name [lindex $argv 4]
file mkdir $out_dir

read_verilog [file join $work_dir $source_name]
read_xdc [file join $work_dir clock_200mhz_benchmark.xdc]
synth_design -top $top_name -part $target_part \
    -generic DATA_W=16 -generic IMG_W=960 \
    -mode out_of_context -flatten_hierarchy rebuilt

report_utilization -hierarchical \
    -file [file join $out_dir window_utilization.rpt]
report_timing_summary -delay_type max -report_unconstrained \
    -file [file join $out_dir window_timing_synth.rpt]
puts "ACX750_WINDOW_SYNTH_TOP=$top_name"
puts "ACX750_WINDOW_SYNTH_PART=$target_part"
puts "ACX750_WINDOW_SYNTH_DONE"
