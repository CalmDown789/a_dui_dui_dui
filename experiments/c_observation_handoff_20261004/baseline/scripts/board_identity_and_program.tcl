# Read-only identity probe with no args; guarded programming with <bit> <idcode>.
if {[llength $argv] ni {0 2}} {error "usage: board_identity_and_program.tcl ?bitfile expected_idcode?"}
if {[llength $argv]==2} {
    set bit [file normalize [lindex $argv 0]]
    set expected [string tolower [lindex $argv 1]]
    if {![file isfile $bit]} {error "bitstream missing"}
}
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet *250520092545*]
if {[llength $targets]!=1} {error "expected observed Digilent cable 250520092545; found: [get_hw_targets]"}
set target [lindex $targets 0]
current_hw_target $target
open_hw_target $target
set devices [get_hw_devices]
if {[llength $devices]!=1} {error "expected one JTAG device"}
set device [lindex $devices 0]
set part [get_property PART $device]
set id [string tolower [get_property IDCODE $device]]
puts "BOARD_IDENTITY TARGET=$target DEVICE=$device PART=$part IDCODE=$id"
if {$part ne "xc7a200t"} {error "wrong FPGA part"}
if {[llength $argv]==2} {
    if {$id ne $expected} {error "IDCODE differs from read-only probe"}
    puts "PROGRAM_BEGIN BIT=$bit"
    set_property PROGRAM.FILE $bit $device
    program_hw_devices $device
    refresh_hw_device $device
    foreach property {REGISTER.CONFIG_STATUS PROGRAM.IS_PROGRAMMED} {
        if {[lsearch -exact [list_property $device] $property]>=0} {puts "$property=[get_property $property $device]"}
    }
    puts "PROGRAM_COMPLETE BIT=$bit"
} else {puts "READ_ONLY_BOARD_PROBE_COMPLETE"}
close_hw_target
close_hw_manager
exit
