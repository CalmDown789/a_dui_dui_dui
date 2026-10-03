# Member B: read-only audit of the retained nominal implementation.
# No netlist, INIT, routing, or constraint changes. DCP, NEW audit directory.
if {[llength $argv]!=2} {error "Expected DCP and new audit directory"}
set audit_input [file normalize [lindex $argv 0]]
set audit_dir [file normalize [lindex $argv 1]]
if {[file exists $audit_dir]} {error "Refuse to overwrite LUT audit"}
file mkdir $audit_dir
set_param general.maxThreads 2
open_checkpoint $audit_input
if {[get_property PART [current_design]] ne "xc7a200tfbg484-2"} {error "Unexpected part"}
set pins [get_pins -hier -filter {NAME =~ *l5/gk.frontend/fifo*/WE}]
set nets [lsort -unique [get_nets -parent_net -segments -of_objects $pins]]
set f [open "$audit_dir/lut_audit.tsv" w]
puts $f "net\tcell\tinit\tI0_net\tI0_driver\tI1_net\tI1_driver\tI2_net\tI2_driver"
foreach net $nets {
    set outputs [get_pins -leaf -of_objects $net -filter {DIRECTION == OUT}]
    set cells [get_cells -of_objects $outputs]
    if {[llength $cells]!=1 || [get_property REF_NAME $cells] ne "LUT3"} {error "Expected LUT3 driver"}
    set row [list $net $cells [get_property INIT $cells]]
    for {set i 0} {$i<3} {incr i} {
        set pin [get_pins "$cells/I$i"]
        set n [lsort -unique [get_nets -parent_net -segments -of_objects $pin]]
        set d [get_pins -leaf -of_objects $n -filter {DIRECTION == OUT}]
        lappend row $n $d
    }
    puts $f [join $row "\t"]
}
close $f
update_timing
report_timing_summary -delay_type min_max -max_paths 5 -file "$audit_dir/timing_summary.rpt"
report_route_status -file "$audit_dir/route_status.rpt"
write_xdc "$audit_dir/constraints.xdc"
puts "L5_FIFO_LUT_READ_ONLY_AUDIT_COMPLETE nets=[llength $nets]"
