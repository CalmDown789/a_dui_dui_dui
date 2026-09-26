# Prepared only. No RTL read/synthesis; start from an exact routed checkpoint.
# Invocation: -tclargs <prepared-new-stage> <Python-executable>
if {![info exists argv] || [llength $argv] != 2} {
    error "Expected prepared stage and Python executable"
}
set finish_here [file normalize [file dirname [info script]]]
set finish_stage [file normalize [lindex $argv 0]]
set finish_python [lindex $argv 1]
if {![string match "2025.2*" [version -short]]} {error "This experiment was reviewed for Vivado 2025.2"}
puts [exec $finish_python -I "$finish_here/prepare.py" verify $finish_stage]
source "$finish_stage/settings.tcl"
if {$finish_extra_setup_ns ni {0.000 0.300 0.500}} {error "Unsupported setup pressure"}
if {[file exists "$finish_stage/reports"] || [file exists "$finish_stage/run_started.txt"]} {
    error "This stage has already been used; prepare a new stage"
}
set finish_lock [open "$finish_stage/run_started.txt" {WRONLY CREAT EXCL}]
puts $finish_lock "started=[clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"
close $finish_lock
file mkdir "$finish_stage/reports"
set finish_old_dir [pwd]
cd $finish_stage
set_param general.maxThreads 2

proc finish_slack {clock delay} {
    set paths [get_timing_paths -from $clock -to $clock -delay_type $delay -max_paths 1 -nworst 1]
    if {[llength $paths] != 1} {error "Expected a timed path within the 200 MHz clock"}
    return [get_property SLACK [lindex $paths 0]]
}

proc finish_uncertainty {clock} {
    set text [report_timing -from $clock -to $clock -delay_type max -max_paths 1 -return_string]
    set values [dict create]
    foreach {key pattern} {
        UU {User Uncertainty\s+\(UU\):\s+(-?[0-9.]+)ns}
        TSJ {Total System Jitter\s+\(TSJ\):\s+([0-9.]+)ns}
        DJ {Discrete Jitter\s+\(DJ\):\s+([0-9.]+)ns}
        PE {Phase Error\s+\(PE\):\s+([0-9.]+)ns}
    } {
        if {![regexp $pattern $text -> number]} {error "Cannot audit timing uncertainty field $key"}
        dict set values $key $number
    }
    return $values
}

proc finish_snapshot {folder clock} {
    file mkdir $folder
    report_timing_summary -delay_type min_max -max_paths 20 -file "$folder/timing_summary.rpt"
    report_timing -delay_type max -max_paths 100 -nworst 1 -file "$folder/setup_paths.rpt"
    report_timing -delay_type min -max_paths 100 -nworst 1 -file "$folder/hold_paths.rpt"
    report_timing -from $clock -to $clock -delay_type max -max_paths 20 -file "$folder/same_clock_setup.rpt"
    report_timing -from $clock -to $clock -delay_type min -max_paths 20 -file "$folder/same_clock_hold.rpt"
    report_route_status -file "$folder/route_status.rpt"
    report_drc -file "$folder/drc.rpt"
    report_utilization -file "$folder/utilization.rpt"
    report_utilization -hierarchical -file "$folder/utilization_hier.rpt"
    report_clocks -file "$folder/clocks.rpt"
    write_xdc "$folder/constraints.xdc"
}

set finish_status [catch {
    open_checkpoint "$finish_stage/input/source_postroute.dcp"
    if {[get_property PART [current_design]] ne "xc7a200tfbg484-2"} {error "Unexpected FPGA part"}
    update_timing
    set finish_pin [get_pins -quiet {u_top/g_mmcm.u_mmcm/CLKOUT0}]
    set finish_clock [get_clocks -quiet -of_objects $finish_pin]
    if {[llength $finish_clock] != 1} {error "Expected exactly one MMCM output clock"}
    if {abs([get_property PERIOD $finish_clock]-5.000) > 0.000001} {error "Baseline period is not 5 ns"}
    set finish_waveform [get_property WAVEFORM $finish_clock]
    if {![report_route_status -boolean_check ROUTED_FULLY] ||
        [report_route_status -boolean_check ERRORS_IN_ROUTES]} {error "Baseline DCP is not fully and legally routed"}
    set finish_original_uncertainty [finish_uncertainty $finish_clock]
    if {abs([dict get $finish_original_uncertainty UU]) > 0.000001} {error "Baseline must already have restored UU=0"}
    finish_snapshot "$finish_stage/reports/before" $finish_clock
    set finish_before_setup [finish_slack $finish_clock max]
    set finish_before_hold [finish_slack $finish_clock min]

    # Only a temporary same-clock setup pressure; frequency, automatic jitter,
    # hold uncertainty, exceptions and DRC severity are not modified.
    if {$finish_extra_setup_ns > 0} {
        set_clock_uncertainty -setup -from $finish_clock -to $finish_clock $finish_extra_setup_ns
    }
    update_timing
    finish_snapshot "$finish_stage/reports/before_pressure" $finish_clock
    set finish_pressure_before [finish_slack $finish_clock max]
    if {abs(($finish_before_setup-$finish_pressure_before)-$finish_extra_setup_ns) > 0.002} {
        error "Initial same-clock setup pressure does not match requested value"
    }
    # Local 2025.2 help states that positive-slack designs are not optimized.
    # Preserve a measured no-op result if no negative setup path exists.
    set finish_global_paths [get_timing_paths -delay_type max -max_paths 1 -nworst 1]
    if {[llength $finish_global_paths] != 1} {error "Cannot determine global setup slack"}
    set finish_opt_applied 0
    if {[get_property SLACK [lindex $finish_global_paths 0]] < 0} {
        phys_opt_design -directive AggressiveExplore
        set finish_opt_applied 1
    } else {
        puts "POSTROUTE_FINISH_NO_NEGATIVE_SETUP_PATH; physical optimization skipped"
    }
    update_timing
    finish_snapshot "$finish_stage/reports/after_physopt_pressure" $finish_clock
    set finish_route_repair 0
    if {![report_route_status -boolean_check ROUTED_FULLY] ||
        [report_route_status -boolean_check ERRORS_IN_ROUTES]} {
        # Normal routed-design continuation, not read_checkpoint -incremental
        # or route_design -eco (different directive compatibility rules).
        route_design -directive NoTimingRelaxation -preserve
        set finish_route_repair 1
    }
    update_timing
    finish_snapshot "$finish_stage/reports/after_pressure" $finish_clock
    set finish_tight_setup [finish_slack $finish_clock max]
    set finish_tight_hold [finish_slack $finish_clock min]
    # No physical command may occur between this measurement and restored one.
    set_clock_uncertainty -setup -from $finish_clock -to $finish_clock 0.000
    update_timing
    finish_snapshot "$finish_stage/reports/after_restored" $finish_clock
    set finish_restored_setup [finish_slack $finish_clock max]
    set finish_restored_hold [finish_slack $finish_clock min]
    set finish_final_uncertainty [finish_uncertainty $finish_clock]
    if {abs(($finish_restored_setup-$finish_tight_setup)-$finish_extra_setup_ns) > 0.002} {
        error "Final same-physical-design setup difference does not match pressure"
    }
    if {abs($finish_restored_hold-$finish_tight_hold) > 0.002} {error "Setup restore changed hold slack"}
    if {abs([get_property PERIOD $finish_clock]-5.000) > 0.000001 ||
        [get_property WAVEFORM $finish_clock] ne $finish_waveform} {error "Clock period or waveform changed"}
    foreach finish_key {UU TSJ DJ PE} {
        if {[dict get $finish_final_uncertainty $finish_key] != [dict get $finish_original_uncertainty $finish_key]} {
            error "Restored clock uncertainty component changed: $finish_key"
        }
    }
    set finish_routed [report_route_status -boolean_check ROUTED_FULLY]
    set finish_route_error [report_route_status -boolean_check ERRORS_IN_ROUTES]
    write_checkpoint "$finish_stage/postroute.dcp"
    set finish_result [open "$finish_stage/reports/result.txt" w]
    set finish_measured_status "COMPLETED_MEASURED"
    if {!$finish_routed || $finish_route_error} {set finish_measured_status "FAILED_ROUTE"}
    puts $finish_result "status=$finish_measured_status"
    puts $finish_result "extra_setup_ns=$finish_extra_setup_ns"
    puts $finish_result "phys_opt_applied=$finish_opt_applied"
    puts $finish_result "route_repair_applied=$finish_route_repair"
    puts $finish_result "same_clock_before_setup_ns=$finish_before_setup"
    puts $finish_result "same_clock_before_hold_ns=$finish_before_hold"
    puts $finish_result "same_clock_after_tight_setup_ns=$finish_tight_setup"
    puts $finish_result "same_clock_after_restored_setup_ns=$finish_restored_setup"
    puts $finish_result "same_clock_after_restored_hold_ns=$finish_restored_hold"
    puts $finish_result "restored_minus_tight_ns=[expr {$finish_restored_setup-$finish_tight_setup}]"
    puts $finish_result "route_fully_complete=$finish_routed"
    puts $finish_result "route_errors_present=$finish_route_error"
    puts $finish_result "uncertainty_components=$finish_final_uncertainty"
    puts $finish_result "acceptance=Inspect global restored setup/hold/pulse-width, DRC and route reports; completion is not timing acceptance"
    close $finish_result
    if {!$finish_routed || $finish_route_error} {error "Final routing is incomplete or has errors; result is not accepted"}
    puts [exec $finish_python -I "$finish_here/prepare.py" finalize $finish_stage]
} finish_message finish_options]
cd $finish_old_dir
if {$finish_status} {
    set finish_failure [open "$finish_stage/failed.txt" w]
    puts $finish_failure $finish_message
    close $finish_failure
    return -options $finish_options $finish_message
}
puts "POSTROUTE_FINISH_COMPLETE stage=$finish_stage"
