# Isolated explicitly banked stripe simulation; no synthesis or implementation.
# Run under the intended Vivado environment. No fallback to another version.
# Optional -tclargs: tb_stripe_banked tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand
set here [file normalize [file dirname [info script]]]
set root [file normalize "$here/../../.."]
set previous "$here/../stripe_pipe"
if {![info exists ::env(XILINX_VIVADO)]} {
    error "XILINX_VIVADO is missing; run from the intended Vivado environment"
}
set viv [file normalize $::env(XILINX_VIVADO)]
set bindir "$viv/bin"
foreach exe {xvlog.bat xelab.bat xsim.bat} {
    if {![file isfile "$bindir/$exe"]} { error "Missing tool: $bindir/$exe" }
}
set benches {tb_stripe_banked tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand}
if {[info exists argv] && [llength $argv]} { set benches $argv }
foreach tb $benches {
    if {$tb ni {tb_stripe_banked tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand}} {
        error "Unsupported testbench: $tb"
    }
}

# Each invocation uses a new directory, so stale PASS logs cannot be reused.
set workroot "$here/unit_work/run_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
file mkdir $workroot
set libdir "$viv/lib/win64.o"
set tpdir "$viv/tps/win64"
set saved_cwd [pwd]
puts "STRIPE_BANKED_SIM_TOOL_ROOT=$viv"
puts "STRIPE_BANKED_SIM_WORK=$workroot"

# Support both known kernel filename generations. In 2025.2 the kernel is
# xv_simulator_kernel.dll, the Tcl library is tcl86t.dll, and Boost names have
# no 'lib' prefix. Stage only these runtime families after xelab, which may
# recreate the snapshot directory. Windows system DLLs remain system-owned.
proc stripe_banked_stage_runtime {libdir tpdir snapdir} {
    set kernels [concat \
        [glob -nocomplain -types f "$libdir/xv_simulator_kernel.dll"] \
        [glob -nocomplain -types f "$libdir/librdi_simulator_kernel.dll"]]
    if {![llength $kernels]} { error "No supported XSim kernel DLL in $libdir" }
    set files $kernels
    foreach pattern [list "$libdir/tcl*t.dll" "$libdir/*boost*.dll" \
                          "$libdir/librdizlib.dll" "$libdir/zlib*.dll" \
                          "$tpdir/msvcp140*.dll" "$tpdir/vcruntime140*.dll"] {
        set files [concat $files [glob -nocomplain -types f $pattern]]
    }
    foreach source [lsort -unique $files] {
        file copy -force $source "$snapdir/[file tail $source]"
    }
}

set failure [catch {
    foreach tb $benches {
        set work "$workroot/$tb"
        file mkdir $work
        cd $work
        set rtl [list "$here/stripe_buffer.v" "$previous/pingpong_buffer.v"]
        if {$tb ni {tb_stripe_banked tb_stripe_pipe}} {
            lappend rtl "$root/rtl/output_stream.v" "$root/rtl/c_protocol_assertions.v"
        }
        if {$tb eq "tb_stripe_banked"} {
            # Make a renamed, otherwise unchanged copy in this new run's work
            # directory. The source/reference experiment is never overwritten.
            set fh [open "$previous/stripe_buffer.v" r]
            fconfigure $fh -encoding utf-8
            set reference_text [read $fh]
            close $fh
            set replacements [regsub -all {module[ \t]+stripe_buffer[ \t]*#} \
                $reference_text {module stripe_buffer_reference #} reference_text]
            if {$replacements != 1} { error "Expected one reference module declaration" }
            set reference_file "$work/stripe_buffer_reference.v"
            set fh [open $reference_file w]
            fconfigure $fh -encoding utf-8 -translation lf
            puts -nonewline $fh $reference_text
            close $fh
            lappend rtl $reference_file
        }
        # Preserve Verilog-2001 semantics for C RTL. Compile the new TB as SV.
        exec "$bindir/xvlog.bat" --nolog --include "$root/rtl" -d C_SIM --work worklib \
            {*}$rtl > "$work/xvlog_rtl.log" 2>@1
        if {$tb eq "tb_stripe_banked"} {
            exec "$bindir/xvlog.bat" --nolog -sv --work worklib "$here/$tb.sv" \
                > "$work/xvlog_tb.log" 2>@1
        } elseif {$tb eq "tb_stripe_pipe"} {
            exec "$bindir/xvlog.bat" --nolog -sv --work worklib "$previous/$tb.sv" \
                > "$work/xvlog_tb.log" 2>@1
        } else {
            exec "$bindir/xvlog.bat" --nolog --include "$root/rtl" -d C_SIM --work worklib \
                "$root/tb/$tb.v" > "$work/xvlog_tb.log" 2>@1
        }
        exec "$bindir/xelab.bat" --nolog "worklib.$tb" -O0 -s $tb \
            > "$work/xelab.log" 2>@1
        stripe_banked_stage_runtime $libdir $tpdir "$work/xsim.dir/$tb"
        exec "$bindir/xsim.bat" $tb -runall -log "$work/xsim_engine.log" > "$work/xsim.log" 2>@1
        set fh [open "$work/xsim.log" r]
        set simlog [read $fh]
        close $fh
        set engine_log ""
        if {[file isfile "$work/xsim_engine.log"]} {
            set fh [open "$work/xsim_engine.log" r]
            set engine_log [read $fh]
            close $fh
        }
        set marker "RESULT: PASS"
        if {$tb eq "tb_stripe_pipe"} { set marker "STRIPE_PIPE_UNIT_TEST_PASS" }
        if {$tb eq "tb_stripe_banked"} { set marker "STRIPE_BANKED_ALL_CONFIGS_PASS" }
        if {[string first $marker $simlog] < 0 ||
            [regexp -nocase {\[FAIL\]|RESULT: FAIL|fatal:|error:} "$simlog\n$engine_log"]} {
            error "Test failed: $tb; inspect $work/xsim.log"
        }
        if {$tb eq "tb_stripe_banked" &&
            [regexp -all {STRIPE_BANKED_CONFIG_PASS id=} $simlog] != 5} {
            error "Boundary test did not pass all five configurations"
        }
        puts "STRIPE_BANKED_BENCH_PASS=$tb"
    }
} failure_message failure_options]
cd $saved_cwd
if {$failure} { return -options $failure_options $failure_message }
puts "STRIPE_BANKED_REGRESSION_PASS; work=$workroot"
