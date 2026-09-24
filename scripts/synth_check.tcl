##############################################################################
# synth_check.tcl —— 仅综合（synthesis）资源 / 时序取证
#-----------------------------------------------------------------------------
# 用法：
#   vivado -mode batch -source scripts/synth_check.tcl
#
# ★★ 严格边界（用户指令 §十四，绝对不得越界）★★
#   · 只调用 `synth_design`；
#   · **不调用** opt_design / place_design / phys_opt_design / route_design；
#   · **不调用** write_bitstream；**不生成** .bit；
#   · **不调用** launch_runs impl_1；
#   · 不写 post_synth.dcp（避免大文件；如需可用 -save_dcp 显式打开）。
#
# 产出（全部为 Vivado **原始报告**，符合 §8.3 C17 硬约束 2）：
#   report/utilization_synth.rpt      ← C11 资源统计（BRAM_36K / BRAM_18K / DSP48E1）
#   report/timing_summary_synth.rpt   ← C12 时序（注意：synthesis 级）
#   report/synth_result.txt           ← 一句话结论 + C17 十项必录信息
#
# 综合目标：`c_synth_top`（见 rtl/c_synth_top.v 关于 ROM 初值的说明）
##############################################################################

set target_part   "xc7a200tfbg484-2"
set top_module    "c_synth_top"
set synth_strategy "Vivado Synthesis Defaults"
set target_clk_mhz 200

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set xdc_dir    "$root_dir/constr"
set out_dir    "$root_dir/report"
file mkdir $out_dir

#-----------------------------------------------------------------------------
# 0. 确保输入 ROM 的 .mem 存在
#    `$readmemh` 的路径相对 **运行 vivado 时的工作目录** 解析，这里统一 cd 到
#    仓库根，于是 c_synth_top 里的 "rtl/input_image_pattern.mem" 可稳定命中。
#    （报告路径全部用绝对路径，cd 不影响。）
#-----------------------------------------------------------------------------
cd $root_dir
set mem_rel "rtl/input_image_pattern.mem"
if {![file exists "$root_dir/$mem_rel"]} {
    puts "== 首次运行：生成 $mem_rel =="
    set gen 0
    foreach py {python py python3} {
        if {[catch {exec $py "$script_dir/gen_input_mem.py" pattern-full} e]} { continue }
        puts $e
        set gen 1
        break
    }
    if {!$gen || ![file exists "$root_dir/$mem_rel"]} {
        error "无法生成 $mem_rel —— 请手工执行: python scripts/gen_input_mem.py pattern-full"
    }
}
puts "ROM init file: $mem_rel ([file size "$root_dir/$mem_rel"] bytes)"

# C17 第 10 项：必须明确是否存在未提交本地修改
#   ⚠️ 只检查**源码路径**（rtl/tb/scripts/constr/docs/README/.gitignore）——
#      report/ 是本脚本的**输出目录**，运行后必然有改动，把它算进去会让
#      本字段永远显示 DIRTY，失去意义。
set local_mod "unknown"
set src_paths [list rtl tb scripts constr docs README.md .gitignore]
if {[catch {exec git -C "$script_dir/.." status --porcelain -- {*}$src_paths} gitout]} {
    set local_mod "git-unavailable"
} elseif {[string trim $gitout] eq ""} {
    set local_mod "clean (源文件与 HEAD 一致; report/ 为产物目录已排除)"
} else {
    set local_mod "DIRTY: [string map {\n { }} [string trim $gitout]]"
}
set git_sha "unknown"
catch {set git_sha [string trim [exec git -C "$script_dir/.." rev-parse HEAD]]}

puts "================================================================"
puts " C-side RTL skeleton - SYNTHESIS ONLY (no implementation, no bitstream)"
puts " part    : $target_part"
puts " top     : $top_module"
puts "================================================================"

#-----------------------------------------------------------------------------
# 1. 读入设计（显式文件列表 ⇒ 可复现；不用通配符以免顺序歧义）
#-----------------------------------------------------------------------------
set rtl_files [list \
    "$rtl_dir/c_config.vh"    \
    "$rtl_dir/input_rom.v"    \
    "$rtl_dir/input_stream.v" \
    "$rtl_dir/stripe_buffer.v"\
    "$rtl_dir/pingpong_buffer.v"\
    "$rtl_dir/output_stream.v"\
    "$rtl_dir/uart_tx.v"      \
    "$rtl_dir/readback_ctrl.v"\
    "$rtl_dir/c_ctrl.v"       \
    "$rtl_dir/b_core_stub.v"  \
    "$rtl_dir/b_core_if.v"    \
    "$rtl_dir/c_core.v"       \
    "$rtl_dir/c_top.v"        \
    "$rtl_dir/c_synth_top.v"  \
]
foreach f $rtl_files {
    if {![file exists $f]} { error "missing RTL file: $f" }
}
read_verilog -verbose $rtl_files

#-----------------------------------------------------------------------------
# 1b. 读入 **B 的真实 RTL**（用户指令 §二：不得用 C 自己的 stub 顶替）
#     来源：CalmDown789/a_dui_dui_dui @ acx750-rtl @ 658c82e2
#          见 rtl/b_real/PROVENANCE.md
#     ⚠️ 只「读入」不「实例化」：c_synth_top 里没有实例化它们，
#        所以**不改变**下面的资源数字。这样做的目的是让
#        「B 的真实 RTL 已在 C 侧综合文件列表内」成为可复现的事实，
#        而不是停留在文档声明。
#     ⚠️ 必须用 -sv：B 交付含 SystemVerilog 文件（.sv）。
#     B 原语在**目标器件**上的独立综合见 scripts/synth_b_real.tcl。
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
foreach f $b_real_files {
    if {![file exists $f]} { error "缺少 B 真实 RTL 文件: $f（见 rtl/b_real/PROVENANCE.md）" }
}
read_verilog -sv $b_real_files

read_xdc "$xdc_dir/c_top.xdc"

#-----------------------------------------------------------------------------
# 2. 综合（**仅此一步**）
#-----------------------------------------------------------------------------
synth_design -top $top_module -part $target_part -flatten_hierarchy rebuilt

#-----------------------------------------------------------------------------
# 3. 报告
#-----------------------------------------------------------------------------
report_utilization    -file "$out_dir/utilization_synth.rpt"
report_timing_summary -file "$out_dir/timing_summary_synth.rpt" -max_paths 20
report_clocks         -file "$out_dir/clocks_synth.rpt"
report_drc            -file "$out_dir/drc_synth.rpt"

#-----------------------------------------------------------------------------
# 4. 提取关键数字
#-----------------------------------------------------------------------------
proc grab {file pattern} {
    if {![file exists $file]} { return "n/a" }
    set fh [open $file r]; set c [read $fh]; close $fh
    if {[regexp $pattern $c -> v]} { return $v }
    return "n/a"
}

set util "$out_dir/utilization_synth.rpt"
set bram36 [grab $util {\|\s*RAMB36/FIFO\*?\s*\|\s*(\d+)\s*\|}]
set bram18 [grab $util {\|\s*RAMB18\s*\|\s*(\d+)\s*\|}]
# DSP：为 0 时 Vivado 不输出 "DSP48E1" 行，只输出 "DSPs" 汇总行，故两级匹配
set dsp    [grab $util {\|\s*DSPs\*?\s*\|\s*(\d+)\s*\|}]
if {$dsp eq "n/a"} {
    set dsp [grab $util {\|\s*DSP48E1\s*\|\s*(\d+)\s*\|}]
}
set lut    [grab $util {\|\s*Slice LUTs\*?\s*\|\s*(\d+)\s*\|}]
set ff     [grab $util {\|\s*Slice Registers\s*\|\s*(\d+)\s*\|}]
set bram_lut [grab $util {\|\s*LUT as Memory\s*\|\s*(\d+)\s*\|}]

set tsum "$out_dir/timing_summary_synth.rpt"
set wns "n/a"; set tns "n/a"; set fail_ep "n/a"; set tot_ep "n/a"
if {[file exists $tsum]} {
    set fh [open $tsum r]; set tc [read $fh]; close $fh
    # ★ 跨行正则必须用显式 [^\n]*，**不得用 `.*?`** ★
    #   Tcl ARE 的 `.` 默认**匹配换行**（与 Python 相反），`.*?` 会把
    #   `-0.153` 截成 `-0.1`。四组对照实验与完整分析见
    #   scripts/impl_check.tcl 头部「缺陷 5」。
    #   Data row layout (report_timing_summary, "Design Timing Summary"):
    #     WNS(ns)  TNS(ns)  TNS Failing EP  TNS Total EP  WHS(ns) ...
    #     -0.153   -0.377   3               20786         0.127  ...
    if {[regexp {WNS\(ns\)[^\n]*\n[^\n]*\n\s*(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+([0-9]+)\s+([0-9]+)} $tc -> w t fe te]} {
        set wns $w; set tns $t; set fail_ep $fe; set tot_ep $te
    }
}

#-----------------------------------------------------------------------------
# 5. C17 十项必录信息
#-----------------------------------------------------------------------------
# ★★ 编码陷阱（已踩过，务必保留此注释）★★
#   `fconfigure $rf -encoding utf-8` **不能**修复乱码：Tcl 解析本 .tcl 源码时
#   是按**系统码页**（本机 GBK）解码的，脚本里的中文字面量在内存中已被解成
#   错误字符，再按 utf-8 写出即为「双重编码」（例如 C 渚§ RTL 楠ㄦ灦）。
#   本文件已实测该现象。⇒ 结果文件一律只用 **纯 ASCII 标签**，
#   中文叙述放到 docs/C_IMPLEMENTATION_STATUS.md（由人维护、不经 Tcl 写出）。
#   若将来需要中文报告，正确做法是：Tcl 只写 ASCII → 由本机 Python 读 ASCII
#   结果再生成中文 md，绝不在 Tcl 里直接写中文。
set rf [open "$out_dir/synth_result.txt" w]
fconfigure $rf -encoding utf-8
puts $rf "=============================================="
puts $rf " C-side RTL skeleton - SYNTHESIS ONLY result"
puts $rf "=============================================="
puts $rf " 1  Vivado version      : [version -short]"
puts $rf " 2  FPGA part           : $target_part"
puts $rf " 3  synthesis strategy  : $synth_strategy"
puts $rf " 3b flatten_hierarchy   : rebuilt (EXPLICIT, see synth_design call below);"
puts $rf "                          synth_design's own default would be full"
puts $rf " 4  implementation      : NOT RUN (explicitly out of scope this round)"
puts $rf " 5  top module          : $top_module"
puts $rf " 6  constraint file     : constr/c_top.xdc"
puts $rf " 7  clock configuration : MMCME2_BASE CLKFBOUT_MULT_F=24.0 / DIVCLK_DIVIDE=1 / CLKOUT0_DIVIDE_F=6.0 / CLKIN1_PERIOD=20.0 -> clk_200 = ${target_clk_mhz} MHz"
puts $rf " 8  Git commit SHA      : $git_sha"
puts $rf " 9  generated at        : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf "10  uncommitted change  : $local_mod"
puts $rf "----------------------------------------------"
puts $rf " RAMB36  : $bram36 / 365"
puts $rf " RAMB18  : $bram18 / 730"
puts $rf " DSP48E1 : $dsp / 740"
puts $rf " Slice LUTs    : $lut"
puts $rf " Slice Regs    : $ff"
puts $rf " LUT as Memory : $bram_lut"
puts $rf " WNS @200MHz (synthesis level) : $wns ns"
puts $rf " TNS @200MHz                   : $tns ns"
puts $rf " failing endpoints             : $fail_ep / $tot_ep"
puts $rf "   NOTE: synthesis-level endpoints, NOT post-route"
puts $rf "----------------------------------------------"
puts $rf " reports: report/utilization_synth.rpt"
puts $rf "          report/timing_summary_synth.rpt"
puts $rf "=============================================="
puts $rf " NOTE 1: this is a SYNTHESIS-level result, NOT post-implementation."
puts $rf " NOTE 2: place/route not run, bitstream not generated;"
puts $rf "         Fmax MUST NOT be claimed from this file."
puts $rf " NOTE 3: BRAM acceptance follows the two-level rule (BUDGET doc);"
puts $rf "         judge by BRAM_36K / BRAM_18K utilization."
puts $rf "=============================================="
close $rf

puts ""
puts " RAMB36=$bram36  RAMB18=$bram18  DSP48E1=$dsp  LUT=$lut  FF=$ff"
puts " WNS(synth) = $wns ns   TNS = $tns ns   failing = $fail_ep / $tot_ep"
puts " -> $out_dir/synth_result.txt"
puts ""
