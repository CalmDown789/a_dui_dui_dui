set here [file normalize [file dirname [info script]]]
set work "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set snapshot tb_rom_pipeline
set_param general.maxThreads 2
set viv $::env(XILINX_VIVADO)
set bindir "$viv/bin"
file mkdir $work
cd $work
set root [file normalize "$here/../../.."]
foreach source [glob "$root/member_b_evidence/real_banks/rom_bank_*.mem"] {file copy $source "$work/[file tail $source]"}
file copy "$root/ref/a_full_integer_golden/input_rom_2p19_u8.mem" "$work/input_rom_2p19_u8.mem"
exec "$bindir/xvlog.bat" --nolog -sv --work worklib --include "$here/../../../rtl" -d C_SIM "$here/input_rom.v" \
    "$here/input_stream.v" "$here/tb_rom_pipeline.sv" > "$work/xvlog.log" 2>@1
exec "$bindir/xelab.bat" --nolog "worklib.$snapshot" -O0 -s $snapshot > "$work/xelab.log" 2>@1
set libdir "$viv/lib/win64.o"
set tpdir "$viv/tps/win64"
set snapdir "$work/xsim.dir/$snapshot"
foreach name {xv_simulator_kernel.dll librdi_simulator_kernel.dll librdizlib.dll tcl85t.dll tcl86t.dll} {
    if {[file exists "$libdir/$name"]} {file copy "$libdir/$name" "$snapdir/$name"}
}
foreach pattern [list "$libdir/*boost*.dll" "$tpdir/MSVCP140*.dll" "$tpdir/VCRUNTIME140*.dll"] {
    foreach source [glob -nocomplain -types f $pattern] {
        file copy -force $source "$snapdir/[file tail $source]"
    }
}
exec "$bindir/xsim.bat" $snapshot -runall -log "$work/xsim_engine.log" > "$work/xsim.log" 2>@1
set fh [open "$work/xsim.log" r]
set simlog [read $fh]
close $fh
if {[string first "ROM_PIPELINE_UNIT_PASS cases=4 frames_each=3 latency_edges=3" $simlog]<0 ||
    [regexp -nocase {fatal:|error:} $simlog]} {
    error "ROM pipeline test failed; inspect $work/xsim.log"
}
puts "ROM_PIPELINE_UNIT_COMPLETE log=$work/xsim.log"
