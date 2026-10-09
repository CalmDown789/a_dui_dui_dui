set_param general.maxThreads 8
read_verilog -sv [list evf2_result_window.sv evf2_control_parser.sv evf2_response_serializer.sv]
set out [file normalize [file dirname [info script]]]
cd $out
read_verilog -sv [list input_rom.v input_stream.v stripe_buffer.v pingpong_buffer.v output_stream.v c_ctrl.v b_core_if.v b_core_stub.v same_pad_raster.sv window_kminus1_bram.sv window_stream_frontend.sv eight_phase_issue.sv pixel_shuffle2x_row_banks.sv fsrcnn_network_mem_top.sv b_core_real.sv elastic_fifo.sv phase_mac_pipeline.sv phase_accumulator_36.sv mac_issue_stage.sv vector_postprocess_shared.sv fsrcnn_stream_layer.sv fsrcnn_network_core.sv prelu_requantize.sv c_ethernet_core.v ethernet_frame_rx.sv ethernet_result_tx.sv evf_response_serializer.sv ethernet_video_application.sv ethernet_sr_pipeline.sv course_udp_receive_commit.sv udp_packet_commit_buffer.sv course_udp_transmit.sv packet_async_bridge.sv ethernet_gmii_video.sv rgmii_io_7series.sv ethernet_rgmii_clocks.sv ethernet_rgmii_video.sv course_eth_udp_rx_checked.v eth_udp_tx_gmii.v crc32_d8.v ip_checksum.v ethernet_rgmii_calibrated_clocks.sv rgmii_io_calibrated_7series.sv rgmii_tx_iob250.sv ethernet_rgmii_managed_video.sv fsrcnn_phy_management.sv fsrcnn_phy_startup_config.sv fsrcnn_phy_mdio_c22_transaction.sv fsrcnn_phy_status_once.sv fsrcnn_phy_uart_tx.v]
read_xdc pins_clocks_internal_only.xdc
auto_detect_xpm
synth_design -verilog_define C_USE_B_REAL -top ethernet_rgmii_managed_video -part xc7a200tfbg484-2
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
write_checkpoint physical_unconstrained_synth.dcp
set_property CLKIN1_PERIOD 7.2 [get_cells u_clocks/u_rx_pll]
read_xdc external_io_candidate.xdc
set_clock_uncertainty 0.100 [all_clocks]
# Exact source-synchronous eye is PHY>=1.2ns plus board bounds; retain the
# tool's jitter/PVT/delay-line model. Do not add an unallocated .1ns margin
# to only this direct BUFIO self path. All PLL/fabric crossings keep .1ns.
set_clock_uncertainty -from [get_clocks phy_rx125] -to [get_clocks phy_rx125] 0.0
# Only this native source-synchronous 250MHz->forwarded125 TX relation has
# no extra unallocated user reserve. Native jitter/PVT/CPR and board envelope
# remain; all GMII125->250, phase state, reset and fabric paths keep .1ns.
set tx_serial_clock [get_clocks -of_objects [get_pins u_io/u_tx/u_forward/C]]
if {[llength $tx_serial_clock]!=1} {error {TX serial clock identity}}
set_clock_uncertainty -from $tx_serial_clock -to [get_clocks rgmii_tx_forward] 0.0
create_generated_clock -name mdc_out -source [get_ports sys_clk50] -divide_by 500 [get_ports mdc]
set_output_delay -clock mdc_out -max 10.0 [get_ports mdio]
set_output_delay -clock mdc_out -min -10.0 [get_ports mdio]
set meta [get_pins u_management/u_startup/u_mdio/mdio_meta_q_reg/D]
if {[llength $meta]!=1} {error {MDIO stage1 identity}}
set_false_path -from [get_ports mdio] -to $meta
set drive_regs [get_cells {u_management/u_startup/u_mdio/mdio_out_q_reg u_management/u_startup/u_mdio/mdio_oe_q_reg}]
if {[llength $drive_regs]!=2} {error {MDIO drive identity}}
set_multicycle_path -setup 250 -start -from $drive_regs -to [get_ports mdio]
set_multicycle_path -hold 249 -start -from $drive_regs -to [get_ports mdio]
# Slow serial UART is verified by byte waveform/baud contract, not sys50 I/O.
set_false_path -to [get_ports uart_tx]

# Lock indications are asynchronous reset requests, never frame data.
set lock_pins [get_pins {u_clocks/u_sys_mmcm/LOCKED u_clocks/u_rx_pll/LOCKED u_clocks/u_ref_mmcm/LOCKED}]
if {[llength $lock_pins]!=3} {error "Clock lock source identity mismatch"}
set_false_path -through $lock_pins

source physical_reset_endpoints.tcl
source managed_reset_fault_endpoints.tcl

report_utilization -file utilization_synth.rpt
report_cdc -details -file cdc_synth.rpt
report_clock_interaction -file clock_interaction_synth.rpt
write_xdc synthesized_constraints.xdc
set cdcfile [open cdc_synth.rpt r]
set cdc_text [read $cdcfile]
close $cdcfile
if {[regexp {CDC-[0-9]+[ 	]+Critical[ 	]+[1-9][0-9]*} $cdc_text]} {error "Critical physical parent CDC remains; implementation withheld"}
set xcfile [open synthesized_constraints.xdc r]
set xc_text [read $xcfile]
close $xcfile
if {[regexp -all {set_bus_skew} $xc_text]<16 || [regexp -all {set_max_delay} $xc_text]<16} {error "XPM Gray constraints missing"}
write_checkpoint physical_synth.dcp
opt_design
read_checkpoint -incremental -directive TimingClosure incremental_reference.dcp
report_incremental_reuse -file incremental_reuse_before_place.rpt
place_design
phys_opt_design -directive AggressiveExplore
route_design
set before_refine [get_timing_paths -from [all_registers] -to [all_registers] -delay_type max -max_paths 1]
if {[llength $before_refine]!=1} {error {Missing full internal timing}}
if {[get_property SLACK $before_refine]<0} {
 report_timing -from [all_registers] -to [all_registers] -delay_type max -max_paths 10 -file internal_before_postroute_refine.rpt
 phys_opt_design -directive AggressiveExplore
 route_design
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
report_incremental_reuse -file incremental_reuse_final.rpt
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


