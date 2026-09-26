# Isolated shared-post shift candidate: equivalence and mathematical tests.
# No synthesis/implementation. All generated files stay in this directory.
set here [file normalize [file dirname [info script]]]
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
set snapshot tb_post_shift
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set caller_dir [pwd]
file mkdir $work
set status [catch {
    cd $work
    exec "$bindir/xvlog.bat" --nolog -sv --work worklib \
        "$here/prelu_requantize.sv" "$here/vector_postprocess_shared.sv" \
        "$here/vector_postprocess_shared_reference.sv" "$here/tb_post_shift.sv" \
        > "$work/xvlog.log" 2>@1
    exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot \
        > "$work/xelab.log" 2>@1

    # xelab recreates the snapshot, so stage the known Windows XSim loader
    # closure afterwards. Compiler console logs use --nolog to avoid sharing
    # a file with an engine log opened by the tools themselves.
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
    if {[string first "POST_SHIFT_ALL_CONFIGS_PASS" $simlog] < 0 ||
        [regexp -nocase {fatal:|error:} $simlog] ||
        [regexp -all {POST_SHIFT_CONFIG_PASS id=} $simlog] != 5} {
        error "Post-shift unit test failed; inspect $work/xsim.log"
    }
    if {[file exists "$work/xsim_engine.log"]} {
        set fh [open "$work/xsim_engine.log" r]
        set engine_log [read $fh]
        close $fh
        if {[regexp -nocase {fatal:|error:} $engine_log]} {
            error "Post-shift engine reported an error; inspect $work/xsim_engine.log"
        }
    }
} message options]
cd $caller_dir
if {$status} { return -options $options $message }
puts "POST_SHIFT_UNIT_TEST_PASS; log=$work/xsim.log"
