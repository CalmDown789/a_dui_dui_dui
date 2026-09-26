# Member B: standalone partial FIFO test. No synthesis or implementation.
set here [file normalize [file dirname [info script]]]
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set snapshot "tb_mac_partial_fifo2"
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run this script using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
file mkdir $work
cd $work
exec "$bindir/xvlog.bat" --nolog -sv --work worklib "$here/mac_issue_stage.sv" \
    "$here/tb_mac_partial_fifo2.sv" > "$work/xvlog.log" 2>@1
# Only elaborate the FIFO unit test. The uninstantiated mac_issue_stage
# wrapper is exercised later through the complete network source closure.
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
exec "$bindir/xsim.bat" $snapshot -runall -log "$work/xsim_engine.log" > "$work/xsim.log" 2>@1
set fh [open "$work/xsim.log" r]
set simlog [read $fh]
close $fh
if {[string first "MAC_PARTIAL_FIFO2_131BIT_TEST_PASS" $simlog] < 0 ||
    [regexp -nocase {fatal:|error:} $simlog]} {
    error "Partial FIFO test failed; inspect $work/xsim.log"
}
puts "MAC_PARTIAL_FIFO2_131BIT_TEST_PASS; log=$work/xsim.log"
