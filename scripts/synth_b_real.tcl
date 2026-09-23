##############################################################################
# synth_b_real.tcl —— 在**目标器件**上综合 B 的真实 RTL 原语集合
#-----------------------------------------------------------------------------
# 用法：
#   cd <repo_root> && vivado -mode batch -source scripts/synth_b_real.tcl
#
# 存在理由：
#   成员 B 的 Vivado 2025.2 **没有 xc7a200tfbg484-2 的器件数据**
#   （B 的 docs/synthesis_status.md 记录 `No parts matched 'xc7a200tfbg484-2'`），
#   所以 B 只能给 xc7z020 fallback 数据，**从未在目标器件上综合过**。
#   C 侧本机 Vivado 2022.2 **有**该器件数据（c_synth_top 已实测综合通过）。
#   本脚本因此为 B 补齐「目标器件上的结构推断 / 资源 / 综合级时序」证据。
#
# ★★ 严格边界（不得越界解读）★★
#   1. 综合对象是 **B 已交付的 17 个原语**（顶层 b_real_bench_top），
#      **不是**五层网络，**不是**系统级结论。
#      不得据此宣称或推翻 B v1.1 的 271 RAMB36 系统预算。
#   2. 只调用 `synth_design`；**不** opt/place/route，**不**生成 bitstream。
#   3. 结果为 **synthesis 级**：不得据此宣称 Fmax 或 30fps。
#
# 产出（report/b_real_synth/）：
#   utilization_synth.rpt            总量
#   utilization_hier.rpt             层级化（逐原语）★ per-module 证据
#   ram_utilization_synth.rpt        RAMB36/RAMB18 映射明细
#   timing_summary_synth.rpt         综合级时序
#   clocks_synth.rpt / drc_synth.rpt
#   synth_result.txt                 一句话结论 + 可比对字段
##############################################################################

set target_part   "xc7a200tfbg484-2"
set top_module    "b_real_bench_top"
set target_clk_mhz 200
set target_clk_ns 5.000

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set out_dir    "$root_dir/report/b_real_synth"
file mkdir $out_dir

# `$readmemh` 路径相对运行 vivado 时的工作目录解析 → 统一 cd 到仓库根
cd $root_dir

#-----------------------------------------------------------------------------
# 1. 读入设计
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
    if {![file exists $f]} { error "missing B real RTL file: $f" }
}
# ★ 必须用 -sv：B 交付含 SystemVerilog 文件；C 侧自己的 .v 不在此列表内
read_verilog -sv $b_real_files
set bench_top "$rtl_dir/b_real_bench_top.v"
if {![file exists $bench_top]} { error "missing $bench_top" }
read_verilog $bench_top

# 约束：只建一个 200MHz 时钟。
# ★★ 必须放在 synth_design **之后**（2026-09-23 实测踩坑）★★
#   `create_clock -period 5.000 [get_ports clk]` 是**立即执行**的命令，
#   在 synth_design 之前运行时设计尚未 elaborate，`get_ports clk` 找不到对象，
#   Vivado 直接报 `ERROR: [Common 17-53] User Exception: No open design`，
#   脚本随即中断（实测 synth_breal 只跑了 12 s 就退出、报告全缺）。
#   `read_xdc` 之所以可以在前（见 synth_check.tcl），是因为它只把约束**挂起**
#   交给下一次 synth_design；`create_clock` 没有这个语义。
#   ⇒ 时序分析只需要在 report_timing_summary **之前**有时钟即可，故置于综合之后。

#-----------------------------------------------------------------------------
# 2. 综合（仅此一步）
#-----------------------------------------------------------------------------
synth_design -top $top_module -part $target_part -flatten_hierarchy none

create_clock -name clk -period $target_clk_ns [get_ports clk]

#-----------------------------------------------------------------------------
# 3. 报告（含**层级化**资源 —— per-module 证据）
#-----------------------------------------------------------------------------
report_utilization     -file "$out_dir/utilization_synth.rpt"
report_utilization     -hierarchical -file "$out_dir/utilization_hier.rpt"
report_ram_utilization -file "$out_dir/ram_utilization_synth.rpt"
report_timing_summary  -file "$out_dir/timing_summary_synth.rpt" -max_paths 20
report_clocks          -file "$out_dir/clocks_synth.rpt"
report_drc             -file "$out_dir/drc_synth.rpt"

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
set bram_tile [grab $util {\|\s*Block RAM Tile\s*\|\s*(\d+)\s*\|}]
set uram   [grab $util {\|\s*URAM\s*\|\s*(\d+)\s*\|}]
set dsp    [grab $util {\|\s*DSPs\*?\s*\|\s*(\d+)\s*\|}]
if {$dsp eq "n/a"} { set dsp [grab $util {\|\s*DSP48E1\s*\|\s*(\d+)\s*\|}] }
set lut    [grab $util {\|\s*Slice LUTs\*?\s*\|\s*(\d+)\s*\|}]
set ff     [grab $util {\|\s*Slice Registers\s*\|\s*(\d+)\s*\|}]
set lutram [grab $util {\|\s*LUT as Memory\s*\|\s*(\d+)\s*\|}]

set tsum "$out_dir/timing_summary_synth.rpt"
set wns "n/a"
if {[file exists $tsum]} {
    set fh [open $tsum r]; set tc [read $fh]; close $fh
    # ★ 跨行正则必须用显式 [^\n]*，**不得用 `.*?`** ★
    #   Tcl ARE 的 `.` 默认**匹配换行**，`.*?` 会把 `-0.153` 截成 `-0.1`。
    #   四组对照实验与完整分析见 scripts/impl_check.tcl 头部「缺陷 5」。
    if {[regexp {WNS\(ns\)[^\n]*\n[^\n]*\n\s*(-?[0-9]+\.[0-9]+)} $tc -> w]} { set wns $w }
}

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

#-----------------------------------------------------------------------------
# 5. 结果文件
# ★★ 编码陷阱（与 synth_check.tcl 同根因）★★
#   `fconfigure -encoding utf-8` **不能**修复乱码：Tcl 按**系统码页**（本机 GBK）
#   解码本 .tcl 源码，中文字面量在内存里已被解错，再按 utf-8 写出即双重编码。
#   ⇒ 结果文件一律只用 **纯 ASCII 标签**；中文叙述进 docs/ 下的 .md。
#-----------------------------------------------------------------------------
set rf [open "$out_dir/synth_result.txt" w]
fconfigure $rf -encoding utf-8
puts $rf "=============================================="
puts $rf " Member-B real RTL primitive set - SYNTHESIS ONLY"
puts $rf " top = b_real_bench_top (17 B primitives, NOT the 5-layer net)"
puts $rf "=============================================="
puts $rf " 1  Vivado version      : [version -short]"
puts $rf " 2  FPGA part           : $target_part"
puts $rf " 3  synthesis strategy  : Vivado Synthesis Defaults (synth_design default)"
puts $rf " 4  implementation      : NOT RUN (this script does synthesis only)"
puts $rf " 5  top module          : $top_module"
puts $rf " 6  constraint          : create_clock -name clk -period ${target_clk_ns} \[get_ports clk\]"
puts $rf " 7  clock configuration : clk = ${target_clk_mhz} MHz (single self-created clock, not the board MMCM chain)"
puts $rf " 8  Git commit SHA      : $git_sha"
puts $rf " 9  generated at        : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf "10  uncommitted change  : $local_mod"
puts $rf "----------------------------------------------"
puts $rf " B primitive source   : acx750-rtl @ 658c82e2 (see rtl/b_real/PROVENANCE.md)"
puts $rf " Block RAM Tile  : $bram_tile / 365"
puts $rf "   RAMB36/FIFO   : $bram36 / 365"
puts $rf "   RAMB18        : $bram18 / 730"
puts $rf " URAM            : 0 (Artix-7 has no URAM; report has no URAM row, grab=$uram)"
puts $rf " DSP48E1         : $dsp / 740"
puts $rf " Slice LUTs      : $lut"
puts $rf " Slice Regs      : $ff"
puts $rf " LUT as Memory   : $lutram"
puts $rf " WNS @${target_clk_mhz}MHz (synthesis level) : $wns ns"
puts $rf "----------------------------------------------"
puts $rf " reports: report/b_real_synth/utilization_synth.rpt"
puts $rf "          report/b_real_synth/utilization_hier.rpt   <- per-primitive"
puts $rf "          report/b_real_synth/ram_utilization_synth.rpt"
puts $rf "          report/b_real_synth/timing_summary_synth.rpt"
puts $rf "=============================================="
puts $rf " NOTE 1: this is a SYNTHESIS-level result for the B PRIMITIVE SET,"
puts $rf "         NOT the 5-layer net, NOT a system-level conclusion;"
puts $rf "         it MUST NOT be used to claim or refute the 271 RAMB36 budget."
puts $rf " NOTE 2: place/route not run, no bitstream; Fmax MUST NOT be claimed."
puts $rf "=============================================="
close $rf

puts ""
puts " B real primitives: RAMB36=$bram36 RAMB18=$bram18 DSP=$dsp LUT=$lut FF=$ff"
puts " WNS(synth) = $wns ns @${target_clk_mhz}MHz"
puts " -> $out_dir/synth_result.txt"
puts ""
