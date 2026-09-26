# Member B: isolated SRL/fallback FIFO tests, no synthesis or implementation.
# Run using an ASCII-mapped repository path in Vivado 2025.2.
set here [file normalize [file dirname [info script]]]
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set snapshot "tb_elastic_fifo_srl"
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run this script using Vivado so XILINX_VIVADO is available"
}
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
file mkdir $work
cd $work
exec "$bindir/xvlog.bat" --nolog -sv --work worklib "$here/elastic_fifo.sv" \
    "$here/elastic_fifo_reference.sv" "$here/tb_elastic_fifo_srl.sv" \
    > "$work/xvlog.log" 2>@1
exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot \
    > "$work/xelab.log" 2>@1

# xelab recreates its snapshot directory. Stage the local Vivado Windows
# runtime after elaboration, retaining support for 2025.2 DLL names.
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
if {[string first "FIFO_SRL_ALL_SEVEN_CONFIGS_PASS" $simlog] < 0 ||
    [regexp -all {FIFO_SRL_CONFIG_PASS id=} $simlog] != 7 ||
    [regexp -nocase {fatal:|error:} $simlog]} {
    error "FIFO SRL unit test failed; inspect $work/xsim.log"
}
puts "FIFO_SRL_ALL_SEVEN_CONFIGS_PASS; log=$work/xsim.log"
