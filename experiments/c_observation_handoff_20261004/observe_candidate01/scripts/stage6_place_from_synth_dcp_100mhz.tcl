if {[llength $argv] != 2} {
    error "usage: stage6_place_from_synth_dcp.tcl <fresh_candidate_synth_dcp> <short_output_stage_directory>"
}

# Keep the caller's short SUBST path intact. Normalizing this path can expand it
# back to the long physical workspace path and recreate the Vivado debug-hub
# path-length failure.
set source_dcp [lindex $argv 0]
set stage [lindex $argv 1]
if {![file isfile $source_dcp]} { error "candidate synthesis DCP missing: $source_dcp" }
if {![file isdirectory $stage]} { error "fresh output attempt directory missing: $stage" }
if {[file exists "$stage/placed_setup030.dcp"]} { error "refusing to overwrite placed candidate DCP" }
set out "$stage/reports"
file mkdir $out
cd $stage
open_checkpoint $source_dcp

if {[get_property PART [current_design]] ne "xc7a200tfbg484-2"} {
    error "candidate synthesis checkpoint part mismatch"
}
set_property SEVERITY Error [get_drc_checks {NSTD-1 UCIO-1}]
set cp [get_pins -quiet {u_multiframe/g_mmcm.u_mmcm/CLKOUT0}]
set cc [get_clocks -quiet -of_objects $cp]
if {[llength $cp] != 1 || [llength $cc] != 1 || abs([get_property PERIOD $cc] - 1000.0/100.0) > 0.001} {
    error "fresh candidate synthesis DCP is not constrained at 100 MHz"
}

puts "STAGE6_CONTINUATION_SOURCE=$source_dcp"
puts "STAGE6_CONTINUATION_CWD=[pwd]"
report_clocks -file "$out/clocks_loaded_setup030.rpt"
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_loaded_setup030.rpt"
report_drc -file "$out/drc_loaded_setup030.rpt"

opt_design
place_design -directive ExtraNetDelay_high
phys_opt_design -directive AggressiveExplore
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_placed_setup030.rpt"
report_clocks -file "$out/clocks_placed_setup030.rpt"
write_checkpoint -force "$stage/placed_setup030.dcp"
puts "STAGE6_PLACEMENT_SETUP030_COMPLETE=$stage/placed_setup030.dcp"
