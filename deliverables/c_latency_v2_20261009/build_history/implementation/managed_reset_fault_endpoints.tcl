# Additional managed-image boundaries. Source after physical_reset_endpoints.tcl.
# Preserve every Q->D stage and all synchronized reset consumers.
proc managed_zero_shift_pair {base expected_clock_ref expected_source} {
 set a [get_cells -quiet "${base}\[0\]"]
 set b [get_cells -quiet "${base}\[1\]"]
 foreach c [list $a $b] {
  if {[llength $c]!=1 || [get_property REF_NAME $c] ne {FDPE} || ![get_property ASYNC_REG $c]} {error "Managed reset identity: $base"}
  set ce [reset_net_driver [reset_one_pin "$c/CE"]]
  if {[get_property REF_NAME [get_cells -of_objects $ce]] ne {VCC}} {error "Gated managed reset CE: $base"}
 }
 set p0 [reset_one_pin "${base}\[0\]/PRE"]
 set p1 [reset_one_pin "${base}\[1\]/PRE"]
 set dr0 [reset_net_driver $p0];set dr1 [reset_net_driver $p1]
 if {$dr0 ne $dr1} {error "Managed reset PRE source differs: $base"}
 if {$expected_source ne {} && $dr0 ne $expected_source} {error "Managed reset unexpected source: $base $dr0"}
 set da [reset_net_driver [reset_one_pin "${base}\[0\]/D"]]
 set db [reset_net_driver [reset_one_pin "${base}\[1\]/D"]]
 if {[get_property REF_NAME [get_cells -of_objects $da]] ne {GND} || $db ne "${base}\[0\]/Q"} {error "Not zero shifting: $base"}
 set ca [reset_net_driver [reset_one_pin "${base}\[0\]/C"]]
 set cb [reset_net_driver [reset_one_pin "${base}\[1\]/C"]]
 if {$ca ne $cb || $ca ne $expected_clock_ref} {error "Managed reset clock identity: $base $ca"}
 puts $::managed_proof "$base REF=FDPE ASYNC_REG=TRUE CE=VCC PRE=$dr0 D0=$da D1=$db CLOCK=$ca"
 lappend ::managed_chain_D [reset_one_pin "${base}\[1\]/D"]
 return [list $p0 $p1]
}
set managed_proof [open managed_reset_structure.txt w]
set managed_chain_D {}
set core_clock_pin [reset_one_pin u_clocks/u_core_clock/O]
set tx_clock_pin [reset_one_pin u_clocks/u_serialize_clock/O]
set ref_clock_pin [reset_one_pin u_clocks/u_ref_clock/O]
set fault_pre [managed_zero_shift_pair {u_clocks/bad_sync_reg} $core_clock_pin {}]
set tx_pre [managed_zero_shift_pair {u_io/u_tx/release_sync_reg} $tx_clock_pin {u_clocks/startup_reset_reg/Q}]
set ref_pre [managed_zero_shift_pair {u_clocks/reference_bad_reg} $ref_clock_pin {}]
if {[llength $fault_pre]!=2 || [llength $tx_pre]!=2 || [llength $ref_pre]!=2} {error {Managed reset exact PRE counts}}
# The reference lock's raw source already has a precise LOCKED exception.
# Do not cut reference_bad[1] to calibration counter/RST recovery/removal.
set_false_path -to $fault_pre
set_false_path -to $tx_pre

# Raw IDELAYCTRL RDY enters only one data synchronizer stage.
set ready_pin [reset_one_pin u_clocks/u_delay_control/RDY]
foreach n {0 1} {
 set c [get_cells "u_clocks/delay_ready_sync_reg\[$n\]"]
 if {[llength $c]!=1 || [get_property REF_NAME $c] ne {FDRE} || ![get_property ASYNC_REG $c]} {error {RDY synchronizer identity}}
 set ce [reset_net_driver [reset_one_pin "$c/CE"]]
 if {[get_property REF_NAME [get_cells -of_objects $ce]] ne {VCC}} {error {RDY CE is gated}}
}
set rd0 [reset_net_driver [reset_one_pin {u_clocks/delay_ready_sync_reg[0]/D}]]
set rd1 [reset_net_driver [reset_one_pin {u_clocks/delay_ready_sync_reg[1]/D}]]
if {$rd0 ne $ready_pin || $rd1 ne {u_clocks/delay_ready_sync_reg[0]/Q}} {error {RDY D chain changed}}
# RDY is an asynchronous primitive output, not a valid STA launch startpoint.
# Use a scoped through-pin exception to only its first synchronizer D.
set_false_path -through $ready_pin -to [get_pins {u_clocks/delay_ready_sync_reg[0]/D}]
lappend managed_chain_D [reset_one_pin {u_clocks/delay_ready_sync_reg[1]/D}]
puts $managed_proof "RDY ASYNC_REG=TRUE CE=VCC D0=$rd0 D1=$rd1"
close $managed_proof

# A single terminal, sticky startup permission feeds the asynchronous fault OR.
# Exact CDC-10 waiver only; a future other Critical source remains a build error.
set cfg_clock [reset_one_pin u_management/u_startup/cfg_ok_reg/C]
set cfg_pre [reset_one_pin {u_clocks/bad_sync_reg[0]/PRE}]
create_waiver -type CDC -id {CDC-10} -from $cfg_clock -to $cfg_pre -user {ACX750_root} -desc {Terminal sticky single-bit PHY permission enters an async-assert two-stage reset synchronizer, then 1024 core cycles. The fault OR is not a data crossing. Stage D and all reset consumers remain timed.} -tags {ACX750_PHY_TERMINAL_PERMISSION_FAULT}

# Separately reviewed registered calibration RST fault; never inherit the
# permission waiver for arbitrary future sources of the fault OR.
set cal_rst [get_cells -quiet u_clocks/delay_control_reset_reg]
if {[llength $cal_rst]!=1 || [get_property REF_NAME $cal_rst] ne {FDPE}} {error {Registered calibration reset identity}}
set cal_init [get_property INIT $cal_rst]
if {$cal_init ne {1} && $cal_init ne {1'b1}} {error {Calibration RST must initialize asserted}}
if {[reset_net_driver [reset_one_pin "$cal_rst/C"]] ne $ref_clock_pin || [reset_net_driver [reset_one_pin "$cal_rst/PRE"]] ne {u_clocks/reference_bad_reg[1]/Q}} {error {Calibration RST C/PRE source identity}}
set allowed_cal_sources [list {u_clocks/calibration_was_ready_reg/Q} {u_clocks/delay_ready_sync_reg[1]/Q} {u_clocks/delay_control_reset_reg/Q} {u_clocks/reference_bad_reg[1]/Q}]
for {set n 0} {$n<6} {incr n} {lappend allowed_cal_sources [format {u_clocks/delay_reset_count_reg[%d]/Q} $n]}
# Vivado all_fanin -startpoints_only uses a sequential launch C pin, not
# necessarily Q. Accept only C of the same explicitly approved registers.
set allowed_cal_launches {}
foreach q $allowed_cal_sources {lappend allowed_cal_launches "[string range $q 0 end-1]C"}
set cal_fanin [all_fanin -flat -startpoints_only -to [get_pins "$cal_rst/D $cal_rst/CE"]]
if {![llength $cal_fanin]} {error {Calibration RST has no identifiable D/CE cone}}
set cal_proof [open calibration_reset_source_structure.txt w]
puts $cal_proof "SOURCE=$cal_rst REF=FDPE INIT=$cal_init C=$ref_clock_pin PRE=u_clocks/reference_bad_reg\[1\]/Q"
foreach sp $cal_fanin {
 set source_cell [get_cells -quiet -of_objects $sp]
 if {[llength $source_cell]==1 && [get_property REF_NAME $source_cell] in {VCC GND}} {
  puts $cal_proof "CONSTANT=$sp"
 } elseif {$sp in $allowed_cal_sources || $sp in $allowed_cal_launches} {
  if {[reset_net_driver [reset_one_pin "$source_cell/C"]] ne $ref_clock_pin} {error "Calibration RST source clock differs: $sp"}
  puts $cal_proof "REF_DOMAIN_D_CE_SOURCE=$sp"
 } else {error "Unreviewed calibration RST D/CE source: $sp"}
}
close $cal_proof
create_waiver -type CDC -id {CDC-10} -from [reset_one_pin "$cal_rst/C"] -to $cfg_pre -user {ACX750_root} -desc {Source-bound registered IDELAYCTRL reset is an intentional asynchronous fault request, asserted for at least 64 stable ref200 edges. Release passes the verified zero-shift core reset synchronizer and 1024 cycles. Source D/CE, reference reset recovery/removal and all consumers remain timed.} -tags {ACX750_REGISTERED_CALIBRATION_FAULT}
