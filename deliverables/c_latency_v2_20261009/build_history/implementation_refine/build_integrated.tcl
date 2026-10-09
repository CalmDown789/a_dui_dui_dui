set_param general.maxThreads 8
open_checkpoint input_routed.dcp
set tx_serial_clock [get_clocks -of_objects [get_pins u_io/u_tx/u_forward/C]]
source physical_reset_endpoints.tcl
source managed_reset_fault_endpoints.tcl
phys_opt_design -directive AggressiveExplore
route_design -directive MoreGlobalIterations
set before_refine [get_timing_paths -from [all_registers] -to [all_registers] -delay_type max -max_paths 1]
if {[llength $before_refine]!=1} {error {Missing full internal timing}}
if {[get_property SLACK $before_refine]<0} {
 report_timing -from [all_registers] -to [all_registers] -delay_type max -max_paths 10 -file internal_before_postroute_refine.rpt
 phys_opt_design -directive AggressiveExplore
 route_design -directive MoreGlobalIterations
}
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -file timing_route.rpt
report_utilization -file utilization_route.rpt
report_clock_utilization -file clock_utilization_route.rpt
report_io -file actual_io_route.rpt
report_cdc -details -file cdc_route.rpt
report_bus_skew -file bus_skew_route.rpt
report_exceptions -coverage -file exceptions_route.rpt
check_timing -verbose -file check_timing_route.rpt
report_drc -file drc_route.rpt
set registers [all_registers]
report_timing -from $registers -to $registers -delay_type max -max_paths 10 -file internal_setup_route.rpt
report_timing -from $registers -to $registers -delay_type min -max_paths 10 -file internal_hold_route.rpt
report_timing -to $reset_chain_D_endpoints -delay_type max -max_paths 10 -file reset_chain_data_setup.rpt
report_timing -to $reset_chain_D_endpoints -delay_type min -max_paths 10 -file reset_chain_data_hold.rpt
foreach pin $reset_chain_D_endpoints {
 foreach kind {max min} {
  set paths [get_timing_paths -to $pin -delay_type $kind -max_paths 1]
  if {[llength $paths]!=1 || [get_property SLACK [lindex $paths 0]]<0} {error "Reset chain D timing missing/negative: $pin $kind"}
 }
}
set internal_file [open internal_slack.txt w]
foreach kind {max min} {
 set paths [get_timing_paths -from $registers -to $registers -delay_type $kind -max_paths 1]
 if {[llength $paths]!=1} {error "Unexpected internal path count"}
 puts $internal_file "$kind [get_property SLACK [lindex $paths 0]]"
}
close $internal_file
write_checkpoint -force physical_routed.dcp

set f [open external_io_slack.txt w]
foreach port [get_ports {rgmii_rxd[*] rgmii_rxctl rgmii_txd[*] rgmii_txctl}] {
 foreach kind {max min} {
  if {[get_property DIRECTION $port] eq {IN}} {set paths [get_timing_paths -from $port -delay_type $kind -max_paths 1]} else {set paths [get_timing_paths -to $port -delay_type $kind -max_paths 1]}
  if {[llength $paths]!=1} {error "Missing IO path $port $kind"}
  puts $f "$port $kind [get_property SLACK $paths]"
 }
}
close $f
report_timing -to [get_pins -of_objects [get_cells -hier -filter {REF_NAME == IDDR}] -filter {REF_PIN_NAME == R}] -delay_type max -max_paths 10 -file iddr_recovery.rpt
report_timing -to [get_pins -of_objects [get_cells -hier -filter {REF_NAME == IDDR}] -filter {REF_PIN_NAME == R}] -delay_type min -max_paths 10 -file iddr_removal.rpt
report_timing -to [get_pins u_io/u_tx/u_forward/R] -delay_type max -max_paths 4 -file tx_clock_recovery.rpt
report_timing -to [get_pins u_io/u_tx/u_forward/R] -delay_type min -max_paths 4 -file tx_clock_removal.rpt
set tx_resets [get_pins -of_objects [get_cells -hier -filter {NAME =~ u_io/u_tx/g_iob* && REF_NAME == FDCE}] -filter {REF_PIN_NAME == CLR}]
if {[llength $tx_resets]!=5} {error {Exactly five IOB TX FDCE CLR expected}}
report_timing -to $tx_resets -delay_type max -max_paths 10 -file tx_data_recovery.rpt
report_timing -to $tx_resets -delay_type min -max_paths 10 -file tx_data_removal.rpt
report_timing -to $managed_chain_D -delay_type max -max_paths 10 -file managed_chain_setup.rpt
report_timing -to $managed_chain_D -delay_type min -max_paths 10 -file managed_chain_hold.rpt
set ref_consumers [get_pins -of_objects [get_cells -hier -filter {NAME =~ u_clocks/delay_reset_count_reg* || NAME =~ u_clocks/calibration_was_ready_reg || NAME =~ u_clocks/delay_control_reset_reg}] -filter {REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}]
if {[llength $ref_consumers]!=8} {error {Calibration downstream async endpoint count}}
report_timing -to $ref_consumers -delay_type max -max_paths 10 -file calibration_recovery.rpt
report_timing -to $ref_consumers -delay_type min -max_paths 10 -file calibration_removal.rpt
report_clocks -file clocks_route.rpt
foreach p [get_ports {rgmii_txd[*] rgmii_txctl}] {
 set label [string map {[ _ ] {}} $p]
 foreach kind {max min} {
  report_timing -rise_to $p -delay_type $kind -max_paths 4 -nworst 4 -path_type full_clock_expanded -file "tx_${label}_${kind}_rise.rpt"
  report_timing -fall_to $p -delay_type $kind -max_paths 4 -nworst 4 -path_type full_clock_expanded -file "tx_${label}_${kind}_fall.rpt"
 }
}
report_timing -from [get_clocks tx_raw] -to $tx_serial_clock -delay_type max -max_paths 20 -file gmii125_to_250_setup.rpt
report_timing -from [get_clocks tx_raw] -to $tx_serial_clock -delay_type min -max_paths 20 -file gmii125_to_250_hold.rpt
report_timing -from [get_pins u_management/u_startup/u_mdio/mdio_meta_q_reg/Q] -to [get_pins u_management/u_startup/u_mdio/mdio_sync_q_reg/D] -delay_type max -file mdio_stage_setup.rpt
report_timing -from [get_pins u_management/u_startup/u_mdio/mdio_meta_q_reg/Q] -to [get_pins u_management/u_startup/u_mdio/mdio_sync_q_reg/D] -delay_type min -file mdio_stage_hold.rpt
report_methodology -file methodology_route.rpt

# Keep the inherited electrical envelope and exceptions. No BIT is issued.
set bb [get_cells -hier -filter {IS_BLACKBOX == 1}]
if {[llength $bb]} {error "Unresolved black boxes: $bb"}
foreach kind {max min} {
 set bad [get_timing_paths -delay_type $kind -max_paths 1 -slack_lesser_than 0]
 if {[llength $bad]} {error "Candidate timing negative: $kind [get_property SLACK [lindex $bad 0]]"}
}
set dv [get_drc_violations -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
if {[llength $dv]} {error "DRC error/critical violations: $dv"}
write_bitstream COMM_steps01_04_150_lab_candidate.bit
puts {INTEGRATED_STEPS01_04_DIGITAL_PASS_BIT_CREATED}
exit


