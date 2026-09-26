# Separate second-candidate unit entry point. Does not alter first-run evidence.
set next_units_root [file normalize [file dirname [info script]]]
set next_units_selected $argv
set next_units_saved_argv $argv
if {[llength $next_units_selected] == 0} {
    set next_units_selected {post_shift stripe_banked mac_buffer_l3l5}
}
foreach next_units_pkg $next_units_selected {
    if {$next_units_pkg ni {post_shift stripe_banked mac_buffer_l3l5}} {
        error "Unknown second-candidate unit $next_units_pkg"
    }
    set argv {}
    source "$next_units_root/$next_units_pkg/run_unit.tcl"
}
set argv $next_units_saved_argv
puts "MARGIN200_NEXT_UNITS_COMPLETE"
