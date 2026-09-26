# Member B: scalar original+1/mathematics and shared-slot unit regressions.
# This script runs simulation only, after an explicit launch by the caller.
set here [file normalize [file dirname [info script]]]
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
set caller_dir [pwd]

proc run_requant_case {here viv bindir snapshot pass_marker config_marker config_count} {
    set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]/$snapshot"
    file mkdir $work
    cd $work
    exec "$bindir/xvlog.bat" --nolog -sv --work worklib \
        "$here/prelu_requantize.sv" "$here/prelu_requantize_reference.sv" \
        "$here/vector_postprocess_shared.sv" "$here/$snapshot.sv" \
        > "$work/xvlog.log" 2>@1
    exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot \
        > "$work/xelab.log" 2>@1

    # xelab recreates its snapshot. Stage Windows compatibility libraries
    # afterwards, using the working XSim loader method from the other units.
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
    exec "$bindir/xsim.bat" $snapshot -runall -log "$work/xsim_engine.log" > "$work/xsim.log" 2>@1
    set fh [open "$work/xsim.log" r]
    set simlog [read $fh]
    close $fh
    if {[string first $pass_marker $simlog] < 0 ||
        [regexp -nocase {fatal:|error:} $simlog] ||
        [regexp -all $config_marker $simlog] != $config_count} {
        error "$snapshot failed; inspect $work/xsim.log"
    }
    if {$snapshot eq "tb_requant_scalar" &&
        [string first "REQUANT_ROUND64_PROBE_PASS" $simlog] < 0} {
        error "Missing full-INT64 arithmetic probe PASS in $work/xsim.log"
    }
    puts "$pass_marker; log=$work/xsim.log"
}

set status [catch {
    run_requant_case $here $viv $bindir tb_requant_scalar \
        REQUANT_SCALAR_ALL_CONFIGS_PASS {REQUANT_SCALAR_CONFIG_PASS id=} 6
    run_requant_case $here $viv $bindir tb_requant_shared \
        REQUANT_SHARED_ALL_CONFIGS_PASS {REQUANT_SHARED_CONFIG_PASS id=} 3
} message options]
cd $caller_dir
if {$status} { return -options $options $message }
puts "REQUANT_PIPE_ALL_UNIT_TESTS_PASS"
