# Member B: repeatable physical-only branch from the saved baseline placed checkpoint.
# Usage: -tclargs <baseline|multi_target>
set script_dir [file normalize [file dirname [info script]]]
set root_dir [file normalize "$script_dir/../.."]
set mode [lindex $argv 0]
if {$mode ni {baseline multi_target}} {error "Expected baseline or multi_target"}
set base "$root_dir/_synth_bc/acc36_realrom_150_member_b_forcefifo0926_ascii_ramdecomp/base_postphys.dcp"
set stage "$root_dir/_synth_bc/margin0926_$mode"
set out_dir "$stage/reports"
file mkdir $out_dir
cd $stage
open_checkpoint $base
if {$mode eq "multi_target"} {
    set regs [get_cells -quiet -hier -filter {REF_NAME =~ FD* && (NAME =~ *l5/gk.frontend/fifo/wr_ptr_reg* || NAME =~ *u_in/req_addr_q_reg* || NAME =~ *out_pipe_data_q_reg* || NAME =~ *l5/gk.frontend/pending1_reg*)}]
    set qs [get_pins -quiet -of_objects $regs -filter {REF_PIN_NAME == Q}]
    set ns [get_nets -quiet -of_objects $qs]
    set force_nets {}
    set af [open "$out_dir/replication_targets.txt" w]
    foreach n $ns {
        set loads [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == IN}]
        puts $af "[get_property NAME $n] loads=[llength $loads]"
        set name [get_property NAME $n]
        # Reuse the proven FIFO target density. Include short-fanout BRAM
        # address/data nets because they span distant memory columns.
        set driver [get_cells -quiet -of_objects [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == OUT}]]
        set dn [get_property NAME $driver]
        set threshold 1
        if {[string match *fifo/wr_ptr_reg* $dn]} {set threshold 128}
        if {[string match *frontend/pending1_reg* $dn]} {set threshold 96}
        if {[llength $loads] > $threshold} {lappend force_nets $n}
    }
    close $af
    if {[llength $force_nets] == 0 || [llength $force_nets] > 300} {error "Unexpected targets"}
    phys_opt_design -force_replication_on_nets $force_nets
    report_phys_opt -file "$out_dir/phys_opt_forced.rpt"
}
set af [open "$out_dir/postphys_target_loads.txt" w]
set regs [get_cells -quiet -hier -filter {REF_NAME =~ FD* && (NAME =~ *l5/gk.frontend/fifo/wr_ptr_reg* || NAME =~ *u_in/req_addr_q_reg* || NAME =~ *out_pipe_data_q_reg* || NAME =~ *l5/gk.frontend/pending1_reg*)}]
foreach q [get_pins -quiet -of_objects $regs -filter {REF_PIN_NAME == Q}] {
    foreach n [get_nets -quiet -of_objects $q] {
        set loads [get_pins -quiet -leaf -of_objects $n -filter {DIRECTION == IN}]
        puts $af "[get_property NAME $n] input_pins=[llength $loads]"
    }
}
close $af
route_design -directive NoTimingRelaxation
write_checkpoint -force "$stage/postroute.dcp"
report_timing_summary -file "$out_dir/timing_summary_postroute.rpt" -max_paths 30
report_timing -max_paths 100 -nworst 1 -file "$out_dir/setup_paths.rpt"
report_utilization -file "$out_dir/utilization_postroute.rpt"
report_utilization -hierarchical -file "$out_dir/utilization_postroute_hier.rpt"
report_route_status -file "$out_dir/route_status.rpt"
report_clocks -file "$out_dir/clocks_postroute.rpt"
report_drc -file "$out_dir/drc_postroute.rpt"
puts "MARGIN0926_PHYSICAL_BRANCH_COMPLETE $mode"
