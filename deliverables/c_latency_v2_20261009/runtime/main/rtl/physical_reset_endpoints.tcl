# Scope: only PRE inputs of three identified two-stage reset synchronizers.
# Do not cut clock domains, D paths, synchronized reset consumers, or Gray guards.
proc reset_one_pin {name} {
 set pins [get_pins -quiet $name]
 if {[llength $pins]!=1} {error "Missing/ambiguous exact reset pin $name"}
 return [lindex $pins 0]
}
proc reset_net_driver {pin} {
 set drivers [lsort -unique [get_pins -leaf -of_objects [get_nets -segments -of_objects $pin] -filter {DIRECTION == OUT}]]
 if {[llength $drivers]!=1} {error "Expected one leaf reset driver for $pin: $drivers"}
 return [lindex $drivers 0]
}
set reset_proof [open reset_endpoint_structure.txt w]
set reset_PRE_endpoints {}
set reset_chain_D_endpoints {}
foreach {base driver_pattern} {
 {rr_reg} {u_clocks/startup_reset_reg*}
 {tr_reg} {u_clocks/startup_reset_reg*}
 {u_video/u_rx_bridge/rd_reset_q_reg} {rr_reg[1]}
} {
 set a [get_cells -quiet "${base}\[0\]"]
 set b [get_cells -quiet "${base}\[1\]"]
 foreach c [list $a $b] {
  if {[llength $c]!=1 || [get_property REF_NAME $c] ne "FDPE" || ![get_property ASYNC_REG $c]} {error "Not an ASYNC_REG FDPE reset pair: $base"}
 }
 set p0 [reset_one_pin "${base}\[0\]/PRE"]
 set p1 [reset_one_pin "${base}\[1\]/PRE"]
 set dr0 [reset_net_driver $p0]
 set dr1 [reset_net_driver $p1]
 if {$dr0 ne $dr1} {error "Pair PRE pins have different reset sources: $base"}
 set driver_cell [get_cells -of_objects $dr0]
 if {$driver_pattern eq {rr_reg[1]}} {
  if {$driver_cell ne $driver_pattern} {error "Unexpected RX reset source $driver_cell"}
 } elseif {![string match $driver_pattern $driver_cell]} {error "Unexpected startup reset source $driver_cell"}
 if {[get_property REF_NAME $driver_cell] ne "FDPE"} {error "Reset source is not a register"}
 set da [reset_net_driver [reset_one_pin "${base}\[0\]/D"]]
 set db [reset_net_driver [reset_one_pin "${base}\[1\]/D"]]
 if {[get_property REF_NAME [get_cells -of_objects $da]] ne "GND" || $db ne "${base}\[0\]/Q"} {error "Not a zero-shifting two-stage reset synchronizer: $base"}
 set ca [reset_net_driver [reset_one_pin "${base}\[0\]/C"]]
 set cb [reset_net_driver [reset_one_pin "${base}\[1\]/C"]]
 if {$ca ne $cb} {error "Reset pair clocks differ: $base"}
 foreach c [list $a $b] {
  set ce [reset_net_driver [reset_one_pin "$c/CE"]]
  if {[get_property REF_NAME [get_cells -of_objects $ce]] ne "VCC"} {error "Reset synchronizer has a gated CE: $c"}
 }
 puts $reset_proof "$base ASYNC_REG=TRUE REF_NAME=FDPE CE=VCC PRE_SOURCE=$dr0 D0=$da D1=$db CLOCK=$ca"
 lappend reset_PRE_endpoints $p0 $p1
 lappend reset_chain_D_endpoints [reset_one_pin "${base}\[1\]/D"]
}
close $reset_proof
if {[llength $reset_PRE_endpoints]!=6} {error "Reset exception endpoint count changed"}
set_false_path -to $reset_PRE_endpoints
