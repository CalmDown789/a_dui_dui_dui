##############################################################################
# run_sim.tcl —— 一键跑完 C 侧全部 testbench（Vivado 2022.2 xsim）
#-----------------------------------------------------------------------------
# 用法（两种等价）：
#   vivado -mode batch -source scripts/run_sim.tcl
#   vivado -mode batch -source scripts/run_sim.tcl -tclargs tb_c_top   ;# 只跑一个
#
# 设计要点（都踩过坑，勿改）：
#   1. **每个 TB 使用独立工作目录**（_sim/<tb>/）——让各 TB 的 xsim.log
#      不互相覆盖。
#      ★ 但请注意：**这并不能**修掉「Simulation engine failed to start ...
#      status code -1073741515」——该错误的真因是 xsim 运行库闭包缺失，
#      见下方 `patch_xsim_dlls` 与要点 5（实测：每 TB 独立目录**并未**阻止它）。
#   2. TB 必须有硬 timeout，本脚本再包一层 `-timeout` 兜底。
#   3. **绝不打开波形 dump**（无 $dumpvars / 无 -wave）；磁盘安全第一。
#   4. `-d C_SIM` 打开 RTL 内的 `$display` 诊断分支（综合时不定义）。
#   5. ★ 2026-09-23 定位并实测：`-1073741515`（0xC0000135 =
#      STATUS_DLL_NOT_FOUND）的**真因是 xsim 运行库闭包缺失**
#      （xsimk.exe 缺 `<XILINX_VIVADO>/lib/win64.o/librdi_simulator_kernel.dll`
#      及其 12 个依赖）。修法 = elaborate 之后把这 13 个 DLL **按位置**放到
#      xsimk.exe 旁；补齐后 **5/5 全 PASS**。完整证据在下方 patch_xsim_dlls 头注释。
#      · **历史归因作废**：脚本此前记的「与 synth/impl 并发才失败」「环境级抖动、
#        重试无效」都是被同一个 DLL 缺失现象误导的结论。加固后**未复测**并发场景，
#        故仍建议不要与 synth/impl 并发（资源与日志干扰），
#        但**不得**再据此断言并发会导致本错误。
#      · 脚本内另加 5/15/30 s 递增退避重试（共 4 次）作兜底。
#
# ★ 2026-09-23 变更（B 反馈闭环 #2「真实 B 模块接入」）：
#   · 新增 **B 真实 RTL** 编译步骤（rtl/b_real/**，来源见 rtl/b_real/PROVENANCE.md）；
#   · 该步骤单独用 `-sv` 调用 xvlog —— B 交付中含 .sv 文件
#     （sync_parameter_rom.sv / prelu_requantize.sv），
#     **不得**因此把 C 侧自己的 .v 也一起丢进 `-sv` 模式；
#   · 新增 TB：tb_b_real_primitives（断言「接入的是真 B，不是 C 的 stub」）。
##############################################################################

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set tb_dir     "$root_dir/tb"
set sim_root   "$root_dir/_sim"

#------------------------------------------------------------------------------
# xsim runtime DLL stager
#
#   Symptom when the runtime DLLs are not staged:
#     ERROR [Simtcl 6-50] Simulation engine failed to start:
#     Simulation exited with status code -1073741515 (= STATUS_DLL_NOT_FOUND)
#
#   Root cause, MEASURED 2026-09-23 on this machine (Vivado 2022.2):
#     xsimk.exe imports ONLY KERNEL32.dll / librdi_simulator_kernel.dll /
#     msvcrt.dll.  The one that is missing is a Vivado library:
#         <XILINX_VIVADO>/lib/win64.o/librdi_simulator_kernel.dll
#   Walking its own imports gives a minimal non-system closure of 13 DLLs / 7.9 MB:
#         lib/win64.o : librdi_simulator_kernel.dll, librdizlib.dll, tcl85t.dll,
#                       libboost_{context,coroutine,date_time,filesystem,
#                                 math_c99,thread}.dll
#         tps/win64   : MSVCP140.dll, VCRUNTIME140.dll, VCRUNTIME140_1.dll
#
#   * Staging them NEXT TO xsimk.exe is what fixes it: the exe's own directory is
#     searched before PATH. Verified: one TB went -1073741515 -> RESULT: PASS.
#   * Adding lib/win64.o (or the MinGW dir) to PATH does NOT fix it -- measured.
#   * The 8 MinGW runtimes from tps/mingw/<ver>/win64.o/nt/bin are NOT part of this
#     closure (measured). The earlier note blaming them was wrong; do not "fix"
#     this by copying only those.
#   * xsim.bat does not stage any of this, and PATH is not dependable, so the
#     failure looks intermittent -- it is not.
#
#   * Timing matters: MUST run AFTER xelab. xelab rebuilds $work/xsim.dir/<tb>/
#     every time, wiping DLLs staged on a previous run, so one staged copy kept
#     in the project is not enough.
#   * No hard-coded version: everything resolves under $::env(XILINX_VIVADO).
#------------------------------------------------------------------------------
proc patch_xsim_dlls {work} {
    set viv ""
    if {[info exists ::env(XILINX_VIVADO)]} { set viv $::env(XILINX_VIVADO) }
    if {$viv eq "" || ![file isdirectory $viv]} { set viv "E:/Xilinx/Vivado/2022.2" }

    set libdir "$viv/lib/win64.o"
    set tpdir  "$viv/tps/win64"
    if {![file isdirectory $libdir]} {
        puts "  !! $libdir not found -- cannot stage the xsim runtime"
        return 0
    }

    # named: the direct import of xsimk.exe + the Xilinx libs it pulls in
    set named {librdi_simulator_kernel.dll librdizlib.dll tcl85t.dll}
    # families: boost + the MSVC runtime (globbed so a minor version bump survives)
    set pats [list "$libdir/libboost*.dll" \
                   "$tpdir/MSVCP140*.dll" \
                   "$tpdir/VCRUNTIME140*.dll"]

    set n 0
    foreach exe [glob -nocomplain -types f -directory "$work/xsim.dir" */xsimk.exe] {
        set c [file dirname $exe]
        set nf 0
        foreach d $named {
            if {[file exists "$libdir/$d"]} {
                catch {file copy -force "$libdir/$d" "$c/$d"}
                incr nf
            } else {
                puts "  !! expected runtime missing: $libdir/$d"
            }
        }
        foreach p $pats {
            foreach s [glob -nocomplain -types f $p] {
                catch {file copy -force $s "$c/[file tail $s]"}
                incr nf
            }
        }
        puts "  staged xsim runtime: [file tail $c]  ($nf dlls)"
        incr n
    }
    if {$n == 0} { puts "  !! no xsimk.exe under $work/xsim.dir -- nothing staged" }
    return $n
}

# Vivado 自带 xsim 工具链目录
set bin_dir [file normalize "$::env(XILINX_VIVADO)/bin"]
if {![file exists "$bin_dir/xvlog.bat"]} {
    # 非 Vivado 环境时退回到已实测路径
    set bin_dir "E:/Xilinx/Vivado/2022.2/bin"
}

#-----------------------------------------------------------------------------
# C 侧自己的 RTL（Verilog-2001；不要用 -sv 编译，以免改变既有语义）
#-----------------------------------------------------------------------------
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
    "$rtl_dir/c_protocol_assertions.v" \
]

#-----------------------------------------------------------------------------
# B 侧真实 RTL（只读镜像；含 .sv，需 `-sv` 编译）
#   来源：CalmDown789/a_dui_dui_dui @ acx750-rtl @ 658c82e2
#   ⚠️ 只包含 B 已交付的**原语**；B 的五层集成 top 尚未交付
#      （依据 B v1.1 §十.5），故 b_core_if 的 C_USE_B_REAL 分支仍为占位。
#-----------------------------------------------------------------------------
set b_rtl_dir "$rtl_dir/b_real/rtl"
set b_real_files [list \
    "$b_rtl_dir/compute/dsp_signed_mult.v"        \
    "$b_rtl_dir/compute/dsp_u8s8_mult.v"          \
    "$b_rtl_dir/compute/dot9_pipeline.v"          \
    "$b_rtl_dir/compute/dot25_pipeline.v"         \
    "$b_rtl_dir/compute/dot25_u8s8_pipeline.v"    \
    "$b_rtl_dir/compute/channel_accumulator.v"    \
    "$b_rtl_dir/compute/conv1x1_backend.v"        \
    "$b_rtl_dir/compute/conv3x3_backend.v"        \
    "$b_rtl_dir/compute/conv5x5_backend.v"        \
    "$b_rtl_dir/compute/conv5x5_u8s8_backend.v"   \
    "$b_rtl_dir/window/window3x3_stream.v"        \
    "$b_rtl_dir/window/window3x3_bram.v"          \
    "$b_rtl_dir/window/window5x5_stream.v"        \
    "$b_rtl_dir/window/window5x5_bram.v"          \
    "$b_rtl_dir/memory/sync_parameter_rom.sv"     \
    "$b_rtl_dir/postprocess/pixel_shuffle2x_coord_map.v" \
    "$b_rtl_dir/postprocess/prelu_requantize.sv"  \
]

#-----------------------------------------------------------------------------
# 默认跑全部 TB（全量编译 RTL，最简单可靠，不按需裁剪）
#-----------------------------------------------------------------------------
set all_tbs [list tb_stripe_buffer tb_backpressure_rand tb_ready_valid tb_c_top tb_b_real_primitives]
# 可选：只跑指定 TB —— vivado -mode batch -source run_sim.tcl -tclargs tb_c_top
#   （Vivado 批处理下若未用 -tclargs，$argv 可能是 Tcl 自身参数，
#     故只在其首元素形如 "tb_*" 时才据此裁剪。）
if {[info exists argv] && [llength $argv] > 0 && [string match "tb_*" [lindex $argv 0]]} {
    set all_tbs $argv
}

# 预检：B 真实 RTL 必须全部存在，否则本轮证据不成立
foreach f $b_real_files {
    if {![file exists $f]} { error "missing B real RTL file: $f (see rtl/b_real/PROVENANCE.md)" }
}

set fail_list [list]

foreach tb $all_tbs {
    set work "$sim_root/$tb"
    file mkdir $work
    # ★ 必须 cd 到本 TB 的工作目录再跑 xelab/xsim：
    #   xelab 的 `-s <snapshot>` 与 xsim 的 `xsim.dir/<snapshot>/` 都是**相对 CWD** 解析的。
    #   若从仓库外启动 vivado（例如 cwd = 上级目录），xsim 找不到快照目录，
    #   会报 `Simulation engine failed to start: status code -1073741515`
    #   （0xC0000135 = STATUS_DLL_NOT_FOUND）——看着像缺 DLL，其实是找错目录。
    #   本脚本其余路径全部是绝对路径，故 cd 不影响它们。
    cd $work
    puts "================================================================"
    puts " RUN $tb   (work dir: $work)"
    puts "================================================================"

    set ok 1

    #--- 1a. compile B 真实 RTL（SystemVerilog 能力开启） -----------------
    set cmd0 [list "$bin_dir/xvlog.bat" --include $rtl_dir -d C_SIM --nolog --work worklib -sv]
    foreach f $b_real_files { lappend cmd0 $f }
    if {[catch {eval exec $cmd0 > "$work/xvlog_b_real.log"} err]} {
        set ok 0; puts "xvlog(B real) FAILED: $err"
    }

    #--- 1b. compile C 侧 RTL + TB（Verilog-2001） ------------------------
    if {$ok} {
        set cmd [list "$bin_dir/xvlog.bat" --include $rtl_dir -d C_SIM --nolog --work worklib]
        foreach f $rtl_files { lappend cmd $f }
        lappend cmd "$tb_dir/$tb.v"
        if {[catch {eval exec $cmd > "$work/xvlog.log"} err]} { set ok 0; puts "xvlog FAILED: $err" }
    }

    #--- 2. elaborate ----------------------------------------------------
    if {$ok} {
        if {[catch {eval exec "$bin_dir/xelab.bat" "worklib.$tb" --nolog -s $tb > "$work/xelab.log"} err]} {
            set ok 0; puts "xelab FAILED: $err"
        }
    }

    #--- 2b. patch xsim runtime DLLs (MUST be after xelab) ----------------
    #   xelab rebuilds $work/xsim.dir/<tb>/ and wipes DLLs copied in on a
    #   previous run, so re-patch every time. Without this the engine fails
    #   to start with -1073741515 (STATUS_DLL_NOT_FOUND).
    if {$ok} { patch_xsim_dlls $work }

    #--- 3. simulate（**无波形**；超时兜底） ------------------------------
    if {$ok} {
        # 外层超时 900 s 兜底（TB 内部还有 cycle 级硬 timeout）
        #
        # ★ 重试：xsim 偶发 `Simulation engine failed to start: status code
        #   -1073741515`（0xC0000135 = STATUS_DLL_NOT_FOUND）。
        #   ★ 2026-09-23 已定位**真因**（此前误记为「杀软扫描 / 上一轮残留」）：
        #     xsimk.exe 只导入 KERNEL32 / msvcrt / **librdi_simulator_kernel.dll**；
        #     缺的正是最后这个 Vivado 库（<XILINX_VIVADO>/lib/win64.o/），
        #     它的最小闭包共 **13 个 DLL / 7.9 MB**（含 libboost* 与 MSVC 运行库）。
        #     这些 DLL **既不在 PATH、也不会被 xsim.bat 放到快照目录旁**；
        #     **且 xelab 每次都重建快照目录**，故上一轮放进去的会被一并清掉。
        #     ⇒ 已在 elaborate 之后调用 `patch_xsim_dlls`（见上方 proc）逐次补齐。
        #       实测：补前 -1073741515，补后 RESULT: PASS；只往 PATH 里加目录**无效**；
        #       而 MinGW 的 8 个运行库**不在**该闭包内（此前说法有误）。
        #     本重试链保留作兜底（外部扫描窗口等仍可能抖动）。退避 5/15/30 s，共 4 次。
        #     注意：它**不是** -1073741515 的解 —— 那个错误靠上面的 DLL 补位解决；
        #     缺 DLL 时重试 4 次同样全败（实测）。
        set simok 0
        set backoff {5 15 30}
        for {set attempt 1} {$attempt <= 4} {incr attempt} {
            if {[catch {exec "$bin_dir/xsim.bat" $tb -runall > "$work/xsim.log"} err]} {
                puts "  xsim attempt $attempt FAILED: $err"
                if {$attempt <= 3} {
                    set d [lindex $backoff [expr {$attempt - 1}]]
                    puts "    (退避 ${d}s 后重试)"
                    catch {after [expr {$d * 1000}]}
                }
            } else {
                set simok 1
                break
            }
        }
        if {!$simok} { set ok 0; puts "xsim FAILED after 4 attempts" }
    }

    #--- 4. 判定 ---------------------------------------------------------
    set pass 0
    if {$ok && [file exists "$work/xsim.log"]} {
        set fh [open "$work/xsim.log" r]; set c [read $fh]; close $fh
        if {[string match "*RESULT: PASS*" $c]} { set pass 1 }
        if {[regexp {RESULT: (\w+)} $c -> r]} { puts "  -> RESULT: $r" }
        # ⚠️ 方括号必须转义：Tcl 会在双引号串内做命令替换，
        #    裸写 [FAIL] 会去执行名为 FAIL 的命令 → invalid command name "FAIL"
        set nfail [regexp -all {\[FAIL\]} $c]
        if {$nfail > 0} { puts "  -> $nfail 条 FAIL" }
    }

    if {$pass} {
        puts "  $tb : PASS"
    } else {
        puts "  $tb : FAIL  (see $work/xsim.log)"
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

#-----------------------------------------------------------------------------
# 5. Result file -> report/sim_result.txt
#    * ASCII-ONLY labels (same discipline as synth_check.tcl / impl_check.tcl):
#      Tcl decodes this .tcl source using the SYSTEM CODEPAGE (GBK here), so a
#      Chinese literal is already corrupt in memory and `fconfigure -encoding
#      utf-8` cannot fix that layer. Chinese prose belongs in docs/*.md.
#    * Bracket safety: every [..] below is an INTENDED command substitution
#      (version / llength / clock / format) -- all on the lint whitelist.
#-----------------------------------------------------------------------------
set git_sha "n/a"
if {![catch {exec git rev-parse HEAD} gs]} { set git_sha [string trim $gs] }
set local_mod "n/a"
if {![catch {exec git status --porcelain} lm]} {
    set lm [string trim $lm]
    if {$lm eq ""} {
        set local_mod "CLEAN"
    } else {
        set local_mod "DIRTY: [string map [list "\n" " "] $lm]"
    }
}
set npass [expr {[llength $all_tbs] - [llength $fail_list]}]

set rf [open "$root_dir/report/sim_result.txt" w]
puts $rf "=============================================="
puts $rf " C-side RTL skeleton - SIMULATION result (xsim)"
puts $rf "=============================================="
puts $rf " 1  Vivado version     : [version -short]"
puts $rf " 2  testbenches run    : [llength $all_tbs]"
puts $rf " 3  pass / fail        : $npass / [llength $fail_list]"
puts $rf " 4  git commit SHA     : $git_sha"
puts $rf " 5  generated at       : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf " 6  uncommitted change : $local_mod"
puts $rf "----------------------------------------------"
foreach tb $all_tbs {
    if {[lsearch -exact $fail_list $tb] >= 0} {
        puts $rf "   [format %-22s $tb] : FAIL"
    } else {
        puts $rf "   [format %-22s $tb] : PASS"
    }
}
puts $rf "----------------------------------------------"
puts $rf " raw logs : _sim/<tb>/xsim.log  (gitignored, regenerable)"
puts $rf "=============================================="
puts $rf " NOTE 1: simulation only -- NOT synthesis, NOT implementation."
puts $rf " NOTE 2: do NOT run run_sim.tcl concurrently with synthesis/impl --"
puts $rf "         POLICY ONLY (CPU/disk/log contention).  RETRACTED: the earlier"
puts $rf "         'concurrency causes the -1073741515 failure' reading was wrong;"
puts $rf "         see NOTE 3.  Not re-tested since the DLL staging was added."
puts $rf " NOTE 3: the 0xC0000135 / -1073741515 engine-start failure is NOT"
puts $rf "         concurrency: it is the xsim runtime DLL closure being absent."
puts $rf "         This script stages it next to xsimk.exe after each xelab;"
puts $rf "         the set and the evidence are in the header of run_sim.tcl."
puts $rf "=============================================="
close $rf

puts ""
puts " -> $root_dir/report/sim_result.txt"
