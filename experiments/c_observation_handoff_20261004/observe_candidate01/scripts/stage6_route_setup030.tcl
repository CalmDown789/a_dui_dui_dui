if {[llength $argv] != 1} { error "usage: stage6_route_setup030.tcl <fresh_stage_directory>" }
# Preserve a short SUBST drive path so Vivado's debug-hub temporary paths stay
# below the host OS path-length limit.
set stage [lindex $argv 0]
set placed "$stage/placed_setup030.dcp"
if {![file isfile $placed]} { error "fresh candidate placed DCP missing: $placed" }
if {[file exists "$stage/postroute.dcp"]} { error "refusing to overwrite candidate postroute DCP" }
set out "$stage/reports"
open_checkpoint $placed
if {[get_property PART [current_design]] ne "xc7a200tfbg484-2"} { error "candidate DCP part mismatch" }
set_property SEVERITY Error [get_drc_checks {NSTD-1 UCIO-1}]
set cp [get_pins -quiet {u_multiframe/g_mmcm.u_mmcm/CLKOUT0}]
set cc [get_clocks -quiet -of_objects $cp]
if {[llength $cp] != 1 || [llength $cc] != 1 || abs([get_property PERIOD $cc] - 1000.0/150.0) > 0.001} {
    error "fresh candidate placed DCP is not constrained at 150 MHz"
}
report_clocks -file "$out/clocks_route_setup030.rpt"
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_before_route_setup030.rpt"
route_design -directive NoTimingRelaxation
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_summary_route_setup030.rpt"

# Keep the same routed physical solution. Restore only the added user setup
# uncertainty to the original XDC value (0.000 ns), retaining device jitter.
set_clock_uncertainty -setup -from $cc -to $cc 0.000
update_timing
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 100 -file "$out/timing_summary_postroute.rpt"
report_timing -delay_type max -max_paths 100 -nworst 1 -file "$out/setup_paths_postroute.rpt"
report_timing -delay_type min -max_paths 100 -nworst 1 -file "$out/hold_paths_postroute.rpt"
report_utilization -file "$out/utilization_postroute.rpt"
report_utilization -hierarchical -file "$out/utilization_postroute_hier.rpt"
report_route_status -file "$out/route_status_postroute.rpt"
report_clocks -file "$out/clocks_postroute.rpt"
report_io -file "$out/io_postroute.rpt"
report_exceptions -coverage -file "$out/exceptions_postroute.rpt"
check_timing -verbose -file "$out/check_timing_postroute.rpt"
report_drc -file "$out/drc_postroute.rpt"
catch {report_ram_utilization -file "$out/ram_utilization_postroute.rpt"}
write_xdc -force "$out/constraints_restored.xdc"
write_checkpoint -force "$stage/postroute.dcp"
puts "STAGE6_ROUTE_COMPLETE=$stage/postroute.dcp"
puts "STAGE6_BITSTREAM_NOT_GENERATED=1"
