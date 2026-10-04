if {[llength $argv]!=3} {error "usage: gated_bitgen.tcl <routed_dcp> <MHz> <new_output_directory>"}
set dcp [file normalize [lindex $argv 0]]
set mhz [lindex $argv 1]
set out [file normalize [lindex $argv 2]]
if {$mhz ni {100 150}} {error "unsupported frequency"}
if {![file isfile $dcp] || [file exists $out]} {error "missing DCP or output already exists"}
file mkdir $out
open_checkpoint $dcp
set_property SEVERITY Error [get_drc_checks {NSTD-1 UCIO-1}]
set pins [get_pins -quiet -hier -filter {REF_PIN_NAME == CLKOUT0}]
set clock [get_clocks -quiet -of_objects $pins]
if {[llength $clock]!=1 || abs([get_property PERIOD $clock]-1000.0/$mhz)>0.001} {error "wrong MMCM clock"}
report_clocks -file "$out/clocks.rpt"
report_io -file "$out/io.rpt"
report_exceptions -coverage -file "$out/exceptions.rpt"
check_timing -verbose -file "$out/check_timing.rpt"
set ts [report_timing_summary -delay_type min_max -report_unconstrained -max_paths 100 -return_string]
set f [open "$out/timing_summary.rpt" w];puts $f $ts;close $f
set route [report_route_status -return_string]
set f [open "$out/route_status.rpt" w];puts $f $route;close $f
set drc [report_drc -return_string]
set f [open "$out/drc.rpt" w];puts $f $drc;close $f
write_xdc -force "$out/constraints.xdc"
if {![regexp {WNS\(ns\)[^\n]*\n[^\n]*\n\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)\s+(\d+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)\s+(\d+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)} $ts -> wns tns sfe ste whs ths hfe hte wpws tpws pfe]} {error "timing metrics missing"}
if {$wns<0 || $tns!=0 || $sfe!=0 || $whs<0 || $ths!=0 || $hfe!=0 || $wpws<0 || $tpws!=0 || $pfe!=0} {error "timing gate failed"}
foreach check {no_clock unconstrained_internal_endpoints} {
    if {![regexp "checking $check \\(0\\)" $ts]} {error "internal timing coverage failed: $check"}
}
if {![regexp {nets with routing errors\.+\s*:\s*0\s*:} $route]} {error "route status gate failed"}
if {![regexp {routable nets\.+\s*:\s*(\d+)\s*:} $route -> routable] || ![regexp {fully routed nets\.+\s*:\s*(\d+)\s*:} $route -> routed] || $routable!=$routed} {error "not fully routed"}
if {[regexp {\|\s*[^|]+\|\s*Error\s*\|} $drc] || [regexp {\|\s*(NSTD-1|UCIO-1)\s*\|} $drc]} {error "DRC gate failed"}
puts "BITGEN_GATES_PASS WNS=$wns TNS=$tns WHS=$whs THS=$ths WPWS=$wpws routable=$routable"
write_bitstream "$out/c_board_${mhz}mhz.bit"
puts "GATED_BITSTREAM_COMPLETE=$out/c_board_${mhz}mhz.bit"
exit
