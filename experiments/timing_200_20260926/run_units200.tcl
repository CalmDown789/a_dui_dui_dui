# Run only the selected isolated unit tests, sequentially in one Vivado session.
set units_root [file normalize [file dirname [info script]]]
set units_selected $argv
set units_saved_argv $argv
if {[llength $units_selected] == 0} {set units_selected {bias_early mac_buffer stripe_pipe requant_pipe}}
foreach units_pkg $units_selected {
    if {$units_pkg ni {bias_early mac_buffer stripe_pipe requant_pipe fifo_srl}} {error "Unknown unit $units_pkg"}
    # A child may interpret argv as testbench selectors, not package names.
    set argv {}
    source "$units_root/$units_pkg/run_unit.tcl"
}
set argv $units_saved_argv
puts "MARGIN200_SELECTED_UNITS_COMPLETE"
