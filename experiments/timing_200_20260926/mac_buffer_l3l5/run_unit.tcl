# Isolated L3/L5 partial FIFO test; no synthesis or implementation.
set here [file normalize [file dirname [info script]]]
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
set snapshot tb_mac_partial_fifo2
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set caller_dir [pwd]
file mkdir $work
set status [catch {
    cd $work
    exec "$bindir/xvlog.bat" --nolog -sv --work worklib \
        "$here/mac_issue_stage.sv" "$here/tb_mac_partial_fifo2.sv" \
        > "$work/xvlog.log" 2>@1
    # Elaborate only the two FIFO configurations. Full wrapper dependencies
    # remain part of the later network source-closure regression.
    exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot \
        > "$work/xelab.log" 2>@1
    set libdir "$viv/lib/win64.o"
    set tpdir "$viv/tps/win64"
    set snapdir "$work/xsim.dir/$snapshot"
    foreach name {xv_simulator_kernel.dll librdi_simulator_kernel.dll librdizlib.dll tcl85t.dll tcl86t.dll} {
        if {[file exists "$libdir/$name"]} {
            file copy -force "$libdir/$name" "$snapdir/$name"
        }
    }
    foreach pattern [list "$libdir/*boost*.dll" "$tpdir/MSVCP140*.dll" \
                         "$tpdir/VCRUNTIME140*.dll"] {
        foreach source [glob -nocomplain -types f $pattern] {
            file copy -force $source "$snapdir/[file tail $source]"
        }
    }
    exec "$bindir/xsim.bat" $snapshot -runall -log "$work/xsim_engine.log" \
        > "$work/xsim.log" 2>@1
    set fh [open "$work/xsim.log" r]
    set simlog [read $fh]
    close $fh
    if {[regexp -all {MAC_L3L5_ALL_CONFIGS_PASS configs=2} $simlog] != 1 ||
        [regexp -all {MAC_L3L5_CONFIG_PASS id=} $simlog] != 2 ||
        [regexp -all {MAC_L3L5_CONFIG_PASS id=3 width=259 } $simlog] != 1 ||
        [regexp -all {MAC_L3L5_CONFIG_PASS id=5 width=131 } $simlog] != 1 ||
        [regexp -nocase {fatal:|error:} $simlog]} {
        error "L3/L5 FIFO unit test failed; inspect $work/xsim.log"
    }
    if {[file exists "$work/xsim_engine.log"]} {
        set fh [open "$work/xsim_engine.log" r]
        set engine_log [read $fh]
        close $fh
        if {[regexp -nocase {fatal:|error:} $engine_log]} {
            error "L3/L5 FIFO engine reported an error; inspect $work/xsim_engine.log"
        }
    }
} message options]
cd $caller_dir
if {$status} { return -options $options $message }
puts "MAC_L3L5_UNIT_TEST_PASS; log=$work/xsim.log"
