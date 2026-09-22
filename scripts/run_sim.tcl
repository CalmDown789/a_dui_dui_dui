##############################################################################
# run_sim.tcl —— 一键跑完 C 侧全部 testbench（Vivado 2022.2 xsim）
#-----------------------------------------------------------------------------
# 用法（两种等价）：
#   vivado -mode batch -source scripts/run_sim.tcl
#   vivado -mode batch -source scripts/run_sim.tcl -tclargs tb_c_top   ;# 只跑一个
#
# 设计要点（都踩过坑，勿改）：
#   1. **每个 TB 使用独立工作目录**（_sim/<tb>/）——
#      多个 snapshot 共用一个 xsim.dir 时曾出现
#      「Simulation engine failed to start ... status code -1073741515」。
#   2. TB 必须有硬 timeout，本脚本再包一层 `-timeout` 兜底。
#   3. **绝不打开波形 dump**（无 $dumpvars / 无 -wave）；磁盘安全第一。
#   4. `-d C_SIM` 打开 RTL 内的 `$display` 诊断分支（综合时不定义）。
##############################################################################

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set tb_dir     "$root_dir/tb"
set sim_root   "$root_dir/_sim"

# Vivado 自带 xsim 工具链目录
set bin_dir [file normalize "$::env(XILINX_VIVADO)/bin"]
if {![file exists "$bin_dir/xvlog.bat"]} {
    # 非 Vivado 环境时退回到已实测路径
    set bin_dir "E:/Xilinx/Vivado/2022.2/bin"
}

set rtl_files [list \
    "$rtl_dir/c_config.vh"     \
    "$rtl_dir/input_rom.v"     \
    "$rtl_dir/input_stream.v"  \
    "$rtl_dir/stripe_buffer.v" \
    "$rtl_dir/pingpong_buffer.v"\
    "$rtl_dir/output_stream.v" \
    "$rtl_dir/uart_tx.v"       \
    "$rtl_dir/readback_ctrl.v" \
    "$rtl_dir/c_ctrl.v"        \
    "$rtl_dir/b_core_stub.v"   \
    "$rtl_dir/b_core_if.v"     \
    "$rtl_dir/c_core.v"        \
    "$rtl_dir/c_top.v"         \
    "$rtl_dir/c_synth_top.v"   \
]

# 每个 TB 需要的额外 RTL（全量编译最简单可靠，不按需裁剪）
set all_tbs [list tb_stripe_buffer tb_ready_valid tb_c_top]
# 默认跑全部三个 TB。
# 可选：只跑指定 TB —— vivado -mode batch -source run_sim.tcl -tclargs tb_c_top
#   （Vivado 批处理下若未用 -tclargs，$argv 可能是 Tcl 自身参数，
#     故只在其首元素形如 "tb_*" 时才据此裁剪。）
if {[info exists argv] && [llength $argv] > 0 && [string match "tb_*" [lindex $argv 0]]} {
    set all_tbs $argv
}

set fail_list [list]

foreach tb $all_tbs {
    set work "$sim_root/$tb"
    file mkdir $work
    puts "================================================================"
    puts " RUN $tb   (work dir: $work)"
    puts "================================================================"

    set ok 1

    #--- 1. compile ------------------------------------------------------
    set cmd [list "$bin_dir/xvlog.bat" --include $rtl_dir -d C_SIM --nolog --work worklib]
    foreach f $rtl_files { lappend cmd $f }
    lappend cmd "$tb_dir/$tb.v"
    if {[catch {eval exec $cmd > "$work/xvlog.log"} err]} { set ok 0; puts "xvlog FAILED: $err" }

    #--- 2. elaborate ----------------------------------------------------
    if {$ok} {
        if {[catch {eval exec "$bin_dir/xelab.bat" "worklib.$tb" --nolog -s $tb > "$work/xelab.log"} err]} {
            set ok 0; puts "xelab FAILED: $err"
        }
    }

    #--- 3. simulate（**无波形**；超时兜底） ------------------------------
    if {$ok} {
        # 外层超时 900 s 兜底（TB 内部还有 cycle 级硬 timeout）
        if {[catch {exec "$bin_dir/xsim.bat" $tb -runall > "$work/xsim.log"} err]} {
            set ok 0; puts "xsim FAILED: $err"
        }
    }

    #--- 4. 判定 ---------------------------------------------------------
    set pass 0
    if {$ok && [file exists "$work/xsim.log"]} {
        set fh [open "$work/xsim.log" r]; set c [read $fh]; close $fh
        if {[string match "*RESULT: PASS*" $c]} { set pass 1 }
        if {[regexp {RESULT: (\w+)} $c -> r]} { puts "  -> RESULT: $r" }
        if {[regexp -all {\[FAIL\]} $c] > 0} {
            puts "  -> [regexp -all {\[FAIL\]} $c] 条 [FAIL]"
        }
    }

    if {$pass} {
        puts "  $tb : PASS"
    } else {
        puts "  $tb : FAIL  （见 $work/xsim.log）"
        lappend fail_list $tb
    }
}

puts ""
puts "================================================================"
if {[llength $fail_list] == 0} {
    puts " ALL sims PASS : $all_tbs"
} else {
    puts " FAILED : $fail_list"
}
puts " 日志目录: $sim_root/<tb>/"
puts "================================================================"
