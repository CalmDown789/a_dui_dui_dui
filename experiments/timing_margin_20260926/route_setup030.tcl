# Independent route experiment: keep the same placement-pressure checkpoint,
# retain +0.300 ns setup uncertainty during route, then evaluate original timing.
# This differs from UG949's preferred pre-route restore; both reports are saved.
set here [file normalize [file dirname [info script]]]
set root_dir [file normalize "$here/../.."]
set stage "$root_dir/_synth_bc/margin0926_route_setup030"
set out_dir "$stage/reports"
file mkdir $out_dir
cd $stage
open_checkpoint "$root_dir/_synth_bc/acc36_realrom_150_member_b_setup0300926_ascii_ramdecomp/placed_setup030.dcp"
set cc [get_clocks -of_objects [get_pins {u_top/g_mmcm.u_mmcm/CLKOUT0}]]
if {[llength $cc] != 1 || abs([get_property PERIOD $cc] - 1000.0/150.0)>0.001} {error "Expected 150 MHz clock"}
report_clocks -file "$out_dir/clocks_route_setup030.rpt"
route_design -directive NoTimingRelaxation
report_timing_summary -max_paths 20 -file "$out_dir/timing_summary_route_setup030.rpt"
# No physical modification or reroute after this constraint restoration.
set_clock_uncertainty -setup -from $cc -to $cc 0.000
update_timing
report_timing_summary -max_paths 30 -file "$out_dir/timing_summary_postroute.rpt"
report_timing -max_paths 100 -nworst 1 -file "$out_dir/setup_paths.rpt"
report_utilization -file "$out_dir/utilization_postroute.rpt"
report_utilization -hierarchical -file "$out_dir/utilization_postroute_hier.rpt"
report_route_status -file "$out_dir/route_status.rpt"
report_clocks -file "$out_dir/clocks_postroute.rpt"
report_drc -file "$out_dir/drc_postroute.rpt"
write_xdc -force "$out_dir/constraints_restored.xdc"
write_checkpoint -force "$stage/postroute.dcp"
puts "MARGIN0926_ROUTE_SETUP030_COMPLETE"
