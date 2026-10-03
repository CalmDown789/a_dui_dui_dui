# Member B: generic routed diagnosis plus the targeted combinational-cone check.
# Same arguments as diagnose.tcl: DCP, new output directory.
set here [file normalize [file dirname [info script]]]
source "$here/diagnose.tcl"
set mac_valid_regs [get_cells -hierarchical -filter {NAME =~ *l5/mac/mac/*valid_q_reg* && IS_PRIMITIVE}]
set window_we_pins [get_pins -hierarchical -filter {NAME =~ *l5/gk.frontend/fifo*/WE}]
if {[llength $mac_valid_regs]==0 || [llength $window_we_pins]==0} {
    error "Cannot identify the actual L5 MAC-valid and window-FIFO write-enable objects"
}
set crossing [get_timing_paths -from $mac_valid_regs -to $window_we_pins -delay_type max -max_paths 1]
set f [open "$output_dir/targeted_cone_check.txt" w]
puts $f "mac_valid_registers=[llength $mac_valid_regs]"
puts $f "fifo_we_pins=[llength $window_we_pins]"
puts $f "combinational_timed_paths=[llength $crossing]"
puts $f "boundary=Only direct timed combinational paths; this is not formal functional equivalence."
close $f
if {[llength $crossing]!=0} {
    report_timing -from $mac_valid_regs -to $window_we_pins -delay_type max -max_paths 20 \
        -file "$output_dir/unexpected_ready_cone.rpt"
    error "Targeted MAC-valid to FIFO-WE combinational cone remains"
}
puts "L5_MAC_VALID_TO_WINDOW_FIFO_WE_TIMED_CONE_REMOVED"
