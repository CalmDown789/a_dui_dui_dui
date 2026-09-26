# Prepared-only PReLU signed-round candidate. No synthesis or implementation.
# Six scalar configurations + two arithmetic probes, then five shared cases.
set here [file normalize [file dirname [info script]]]
if {![info exists ::env(XILINX_VIVADO)]} {
    error "Run from the intended Vivado environment with XILINX_VIVADO set"
}
set viv [file normalize $::env(XILINX_VIVADO)]
set bindir "$viv/bin"
foreach name {xvlog.bat xelab.bat xsim.bat} {
    if {![file isfile "$bindir/$name"]} { error "Missing tool: $bindir/$name" }
}
set benches {tb_prelu_signed_round tb_prelu_signed_shared}
if {[info exists argv] && [llength $argv]} { set benches $argv }
foreach tb $benches {
    if {$tb ni {tb_prelu_signed_round tb_prelu_signed_shared}} {
        error "Unsupported PReLU signed-round testbench: $tb"
    }
}
set workroot "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set caller_dir [pwd]
file mkdir $workroot
puts "PRELU_SIGNED_SIM_TOOL_ROOT=$viv"
puts "PRELU_SIGNED_SIM_WORK=$workroot"

proc prelu_signed_stage_runtime {viv snapdir} {
    set libdir "$viv/lib/win64.o"
    set tpdir "$viv/tps/win64"
    set files [concat \
        [glob -nocomplain -types f "$libdir/xv_simulator_kernel.dll"] \
        [glob -nocomplain -types f "$libdir/librdi_simulator_kernel.dll"]]
    if {![llength $files]} { error "No supported XSim kernel DLL in $libdir" }
    foreach pattern [list "$libdir/tcl*t.dll" "$libdir/*boost*.dll" \
                          "$libdir/librdizlib.dll" "$libdir/zlib*.dll" \
                          "$tpdir/MSVCP140*.dll" "$tpdir/VCRUNTIME140*.dll"] {
        set files [concat $files [glob -nocomplain -types f $pattern]]
    }
    foreach source [lsort -unique $files] {
        file copy -force $source "$snapdir/[file tail $source]"
    }
}

set status [catch {
    foreach tb $benches {
        set work "$workroot/$tb"
        file mkdir $work
        cd $work
        exec "$bindir/xvlog.bat" --nolog -sv --work worklib \
            "$here/prelu_requantize.sv" "$here/prelu_requantize_reference.sv" \
            "$here/vector_postprocess_shared.sv" \
            "$here/vector_postprocess_shared_reference.sv" "$here/$tb.sv" \
            > "$work/xvlog.log" 2>@1
        exec "$bindir/xelab.bat" --nolog "worklib.$tb" -O0 -s $tb \
            > "$work/xelab.log" 2>@1
        prelu_signed_stage_runtime $viv "$work/xsim.dir/$tb"
        exec "$bindir/xsim.bat" $tb -runall -log "$work/xsim_engine.log" \
            > "$work/xsim.log" 2>@1
        set fh [open "$work/xsim.log" r]
        set simlog [read $fh]
        close $fh
        if {![file isfile "$work/xsim_engine.log"]} {
            error "Missing XSim engine log: $work/xsim_engine.log"
        }
        set fh [open "$work/xsim_engine.log" r]
        set engine_log [read $fh]
        close $fh
        if {$tb eq "tb_prelu_signed_round"} {
            set marker PRELU_SIGNED_SCALAR_ALL_CONFIGS_PASS
            set config_marker {PRELU_SIGNED_SCALAR_CONFIG_PASS id=}
            set config_count 6
            foreach probe {REQUANT_ROUND64_PROBE_PASS PRELU_SIGNED_ROUND48_PROBE_PASS} {
                if {[string first $probe $simlog] < 0} {
                    error "Missing arithmetic probe $probe in $work/xsim.log"
                }
            }
        } else {
            set marker PRELU_SIGNED_SHARED_ALL_CONFIGS_PASS
            set config_marker {PRELU_SIGNED_SHARED_CONFIG_PASS id=}
            set config_count 5
        }
        if {[string first $marker $simlog] < 0 ||
            [regexp -all $config_marker $simlog] != $config_count ||
            [regexp -nocase {\[FAIL\]|RESULT: FAIL|fatal:|error:} "$simlog\n$engine_log"]} {
            error "PReLU signed-round test failed: $tb; inspect $work/xsim.log and xsim_engine.log"
        }
        puts "PRELU_SIGNED_BENCH_PASS=$tb"
    }
} message options]
cd $caller_dir
if {$status} { return -options $options $message }
puts "PRELU_SIGNED_ROUND_ALL_UNIT_TESTS_PASS; work=$workroot"
