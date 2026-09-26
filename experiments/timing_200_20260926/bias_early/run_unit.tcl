# Member B: independent bias-early equivalence and mathematical unit test.
# No synthesis/implementation. Use an ASCII-mapped repository path.
set here [file normalize [file dirname [info script]]]
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set snapshot "tb_bias_early"
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run this script using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
file mkdir $work
cd $work
exec "$bindir/xvlog.bat" --nolog -sv --work worklib "$here/phase_accumulator_36.sv" \
    "$here/phase_accumulator_reference36.sv" "$here/tb_bias_early.sv" \
    > "$work/xvlog.log" 2>@1
exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot \
    > "$work/xelab.log" 2>@1

# Stage available Windows XSim compatibility libraries after xelab, which
# recreates the snapshot directory. Kernel DLL names differ by version;
# successful execution and the final PASS marker verify this environment.
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
if {[string first "BIAS_EARLY_ALL_FIVE_CONFIGS_PASS" $simlog] < 0 ||
    [regexp -nocase {fatal:|error:} $simlog] ||
    [regexp -all {BIAS_EARLY_CONFIG_PASS id=} $simlog] != 5} {
    error "Bias-early unit test failed; inspect $work/xsim.log"
}
puts "BIAS_EARLY_ALL_FIVE_CONFIGS_PASS; log=$work/xsim.log"
