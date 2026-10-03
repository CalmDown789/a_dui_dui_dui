# Member B: read-only routed-checkpoint diagnosis; no constraints/netlist edits.
# -tclargs <DCP> <new-output-directory>
if {[llength $argv] != 2} {error "Expected DCP and NEW diagnostic directory"}
set input_dcp [file normalize [lindex $argv 0]]
set output_dir [file normalize [lindex $argv 1]]
if {[file exists $output_dir]} {error "Refuse to overwrite diagnostic evidence"}
file mkdir $output_dir
set_param general.maxThreads 2
open_checkpoint $input_dcp
if {[get_property PART [current_design]] ne "xc7a200tfbg484-2"} {error "Unexpected part"}
update_timing
set clk [get_clocks -of_objects [get_pins {u_top/g_mmcm.u_mmcm/CLKOUT0}]]
if {[llength $clk]!=1 || abs([get_property PERIOD $clk]-5.000)>0.000001} {error "Expected 200 MHz"}
report_timing_summary -delay_type min_max -max_paths 20 -file "$output_dir/timing_summary.rpt"
report_timing -delay_type max -max_paths 100 -nworst 1 -file "$output_dir/setup_paths.rpt"
report_route_status -file "$output_dir/route_status.rpt"
report_clocks -file "$output_dir/clocks.rpt"
write_xdc "$output_dir/constraints.xdc"
set failing [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 100000 -nworst 1]
set f [open "$output_dir/failing_endpoints.tsv" w]
puts $f "slack_ns\tstartpoint\tendpoint"
foreach path $failing {
    puts $f "[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
}
close $f
set critical [get_timing_paths -delay_type max -max_paths 500 -nworst 1]
set f [open "$output_dir/critical_500.tsv" w]
puts $f "slack_ns\tstartpoint\tendpoint"
foreach path $critical {
    puts $f "[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
}
close $f
puts "MEMBER_B_DIAGNOSIS_COMPLETE failing_endpoints=[llength $failing]"
