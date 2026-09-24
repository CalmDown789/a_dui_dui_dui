##############################################################################
# impl_check.tcl —— C 侧骨架的**实现（implementation）**资源/时序取证
#-----------------------------------------------------------------------------
# 用法：
#   cd <repo_root> && vivado -mode batch -source scripts/impl_check.tcl
#
# ★★ 与 synth_check.tcl 的关系（用户指令 §十四「必须明确区分」）★★
#   synth_check.tcl  = **synthesis only**：只跑 synth_design，不 place/route。
#   impl_check.tcl   = **implementation**：synth_design → opt_design →
#                      place_design → phys_opt_design → route_design。
#   两张报告**不可互相引用**。
#
# ★ 本脚本仍**不生成 bitstream**。
#
#-----------------------------------------------------------------------------
# ★★ 2026-09-23 修复（第 1 次运行的三个真实缺陷，逐条留档）★★
#   1. `puts " [IMPL] ..."` → Tcl 把 `[IMPL]` 当**命令替换**去执行名为 IMPL 的
#      命令，报 `invalid command name "IMPL"`。方括号必须转义（与历史
#      `[FAIL]` 同一个坑）。⇒ 控制台输出全部改成无方括号的纯文本。
#   2. 时序正则写错：`{WNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)}` 抓到的不是
#      Design Timing Summary 的数字行，结果 WNS/TNS/WHS 打印出同一个 -3.0。
#      ⇒ 改为显式匹配「表头行 + 分隔行 + 第一个数字行」。
#   3. 结果文件中文变**双重编码乱码**：Windows 系统码页为 GBK，Vivado 按
#      系统编码读取本 .tcl，中文在内存里就已经是乱码，再以 UTF-8 写出即成
#      `C 渚§ RTL 楠ㄦ灦`。`fconfigure -encoding utf-8` **修不了这一层**。
#      ⇒ 生成的证据文件改为**纯 ASCII 标签**（机器可读、可 diff、跨平台）；
#        中文解释放在 docs/C_IMPLEMENTATION_STATUS.md（UTF-8 由 Python/编辑器写）。
#
#-----------------------------------------------------------------------------
# ★★ 第 2 次运行（2026-09-23）暴露并修复的 4 个缺陷，逐条留档 ★★
#   4. **方括号陷阱的第 2 个落点**：第 1 次修复只改了**控制台** puts，漏了
#      **写结果文件**的 `puts $rf " [Flow A] ..."`。双引号内的 `[Flow A]`
#      同样触发命令替换 → `invalid command name "Flow"` → 脚本在第 236 行中断。
#      后果：`impl_result.txt` 被截断（1460 B），但**所有 .rpt 报告已经在
#      第 168~174 行写完了**，故 post-route 证据未丢。
#      ⇒ 现在全文**不含任何方括号字面量**：一律写成 `Flow-A` / `Flow-B`。
#      **规则：Tcl 双引号字符串里绝不出现裸方括号。**
#   5. WNS 正则截断：旧式 `{WNS\(ns\).*?\n\s*-+...}` 在 **Tcl ARE** 下把
#      `-0.153` 截成 `-0.1`（Python 同模式却给 -0.153）。四组对照实验定位：
#        `.*?`+`\d` → -0.1 ❌   `.*?`+`[0-9]` → -0.1 ❌
#        `[^\n]*`+`\d` → -0.153 ✅`[^\n]*`+`[0-9]` → -0.153 ✅
#      ⇒ 元凶是 **`.*?`**：**Tcl ARE 默认 `.` 匹配换行**（与 Python 相反），
#        懒惰量词因此走到另一条回溯路径、给出更短的匹配。
#      **规则：Tcl 正则跨行一律用显式 `[^\n]*`，不用 `.*?`。**（ts6 已符合）
#   6. 纠正上一版注释的错误归因：先前写「`flatten_hierarchy none` 会显著恶化
#      时序，none = -3.098 ns」——**错**。复跑实测两条流程的**综合级 WNS 完全相同
#      (-0.153 ns)**；-3.098 是一次**实现后**数值，被误记成了 flatten 的代价。
#-----------------------------------------------------------------------------
# ★★ 两条流程分离：逐模块资源 vs 代表性实现时序 ★★
#   流程 A（flatten_hierarchy none）：保留层级 → 可出**逐模块**资源报告。
#   流程 B（flatten_hierarchy 默认 rebuilt）：允许跨层优化 → **代表性**实现时序。
#   ⇒ 引用逐模块资源时须声明「该次综合用了 flatten none」；
#     引用实现后时序一律用流程 B 的 utilization_postroute / timing_summary_postroute。
#
# 产出（report/impl/）：
#   util_synth_A_hier_none.rpt     流程 A：仅综合 + 保留层级 → **逐模块**资源 ★
#   timing_synth_A_none.rpt        流程 A：仅综合时序（用于归因 flatten 影响）
#   util_synth_B_default.rpt       流程 B：仅综合（默认层级）总量
#   timing_synth_B_default.rpt     流程 B：仅综合时序
#   utilization_postroute.rpt      流程 B：实现后总量 ★
#   timing_summary_postroute.rpt   流程 B：实现后时序 ★
#   worst_path_postroute.rpt       流程 B：实现后最差路径
#   ram_utilization_postroute.rpt  流程 B：实现后 BRAM 细化（含 RAMB36/RAMB18）
#   route_status.rpt / drc_postroute.rpt / clocks_postroute.rpt
#   impl_result.txt                纯 ASCII 一句话结论 + 必录字段
##############################################################################

set target_part    "xc7a200tfbg484-2"
set top_module     "c_synth_top"
set target_clk_mhz 200

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set xdc_dir    "$root_dir/constr"
set out_dir    "$root_dir/report/impl"
file mkdir $out_dir
cd $root_dir

#-----------------------------------------------------------------------------
# 0. ROM 初值文件
#-----------------------------------------------------------------------------
set mem_rel "rtl/input_image_pattern.mem"
if {![file exists "$root_dir/$mem_rel"]} {
    error "missing $mem_rel -- run: python scripts/gen_input_mem.py pattern-full"
}
puts "ROM init file: $mem_rel ([file size "$root_dir/$mem_rel"] bytes)"

#-----------------------------------------------------------------------------
# 1. 读入设计（C 骨架 + B 真实 RTL 一并读入：证明 B 已在工程文件列表内）
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
read_verilog $rtl_files

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
# 只读入（解析/展开），c_synth_top 未实例化它们 → 不占资源；目的是证明
# 「B 的真实 RTL 已在 C 侧工程文件列表内」，而不是只存在于 C 自己的 stub。
read_verilog -sv $b_real_files

read_xdc "$xdc_dir/c_top.xdc"

# --- C17 第 10 项：可追溯性（commit SHA + 未提交修改） ----------------------
set local_mod "unknown"
set src_paths [list rtl tb scripts constr docs README.md .gitignore]
if {[catch {exec git -C "$script_dir/.." status --porcelain -- {*}$src_paths} gitout]} {
    set local_mod "git-unavailable"
} elseif {[string trim $gitout] eq ""} {
    set local_mod "clean (source tree matches HEAD; report/ is an artifact dir, excluded)"
} else {
    set local_mod "DIRTY: [string map {\n { }} [string trim $gitout]]"
}
set git_sha "unknown"
catch {set git_sha [string trim [exec git -C "$script_dir/.." rev-parse HEAD]]}

puts "================================================================"
puts " C-side RTL  --  IMPLEMENTATION (synth + opt + place + route)"
puts " part : $target_part"
puts " top  : $top_module"
puts "================================================================"

#-----------------------------------------------------------------------------
# 2. 流程 A —— 保留层级（flatten none）：为出**逐模块**资源报告
#-----------------------------------------------------------------------------
puts "-- Flow A: synth_design -flatten_hierarchy none (per-module resources)"
synth_design -top $top_module -part $target_part -flatten_hierarchy none
report_utilization -hierarchical -file "$out_dir/util_synth_A_hier_none.rpt"
report_utilization              -file "$out_dir/util_synth_A_total_none.rpt"
report_timing_summary -file "$out_dir/timing_synth_A_none.rpt" -max_paths 5

#-----------------------------------------------------------------------------
# 3. 流程 B —— 默认层级（rebuilt）：为出**代表性**实现时序
#-----------------------------------------------------------------------------
puts "-- Flow B: synth_design (default flatten) -> opt/place/phys_opt/route"
synth_design -top $top_module -part $target_part
report_utilization   -file "$out_dir/util_synth_B_default.rpt"
report_timing_summary -file "$out_dir/timing_synth_B_default.rpt" -max_paths 5

opt_design
place_design
phys_opt_design
route_design

#-----------------------------------------------------------------------------
# 4. 实现后报告（流程 B）
#-----------------------------------------------------------------------------
report_utilization      -file "$out_dir/utilization_postroute.rpt"
report_ram_utilization  -file "$out_dir/ram_utilization_postroute.rpt"
report_timing_summary   -file "$out_dir/timing_summary_postroute.rpt" -max_paths 20
report_timing -max_paths 1 -file "$out_dir/worst_path_postroute.rpt"
report_route_status     -file "$out_dir/route_status.rpt"
report_drc              -file "$out_dir/drc_postroute.rpt"
report_clocks           -file "$out_dir/clocks_postroute.rpt"

#-----------------------------------------------------------------------------
# 5. 提取关键数字（★ 修正后的正则：显式匹配 表头行 + 分隔行 + 数字行）
#-----------------------------------------------------------------------------
proc grab {file pattern} {
    if {![file exists $file]} { return "n/a" }
    set fh [open $file r]; set c [read $fh]; close $fh
    if {[regexp $pattern $c -> v]} { return $v }
    return "n/a"
}

# Design Timing Summary 的第一个数字行：WNS TNS TNS_FE TNS_TE WHS THS
# ★ 正则纪律（见头部缺陷 5）：
#   · 跨行一律用显式 [^\n]*，**不用 .*?**（Tcl ARE 的 `.` 默认吃换行）；
#   · 数值用 [0-9]+\.[0-9]+，不用 [0-9.]+（后者会容忍 "1.2.3" 这种畸形串）。
proc ts6 {file} {
    if {![file exists $file]} { return [list n/a n/a n/a n/a n/a n/a] }
    set fh [open $file r]; set c [read $fh]; close $fh
    if {[regexp {WNS\(ns\)[^\n]*\n[^\n]*\n\s*(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+([0-9]+)\s+([0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)} $c -> a b cc d e f]} {
        return [list $a $b $cc $d $e $f]
    }
    return [list n/a n/a n/a n/a n/a n/a]
}

set tA "$out_dir/timing_synth_A_none.rpt"
set tB "$out_dir/timing_synth_B_default.rpt"
set tP "$out_dir/timing_summary_postroute.rpt"

lassign [ts6 $tA] a_wns a_tns a_fail a_tot a_whs a_ths
lassign [ts6 $tB] b_wns b_tns b_fail b_tot b_whs b_ths
lassign [ts6 $tP] p_wns p_tns p_fail p_tot p_whs p_ths

set util "$out_dir/utilization_postroute.rpt"
set bram_tile [grab $util {\|\s*Block RAM Tile\s*\|\s*([0-9.]+)\s*\|}]
set bram36 [grab $util {\|\s*RAMB36/FIFO\*?\s*\|\s*([0-9]+)\s*\|}]
set bram18 [grab $util {\|\s*RAMB18\s*\|\s*([0-9]+)\s*\|}]
set uram   [grab $util {\|\s*URAM\s*\|\s*([0-9]+)\s*\|}]
set dsp    [grab $util {\|\s*DSPs\*?\s*\|\s*([0-9]+)\s*\|}]
if {$dsp eq "n/a"} { set dsp [grab $util {\|\s*DSP48E1\s*\|\s*([0-9]+)\s*\|}] }
set lut    [grab $util {\|\s*Slice LUTs\*?\s*\|\s*([0-9]+)\s*\|}]
set ff     [grab $util {\|\s*Slice Registers\s*\|\s*([0-9]+)\s*\|}]

#-----------------------------------------------------------------------------
# 6. 结果文件（★ 纯 ASCII 标签：避免 Windows GBK 码页下的双重编码乱码）
#-----------------------------------------------------------------------------
set rf [open "$out_dir/impl_result.txt" w]
fconfigure $rf -encoding utf-8
puts $rf "=============================================================="
puts $rf " C-side RTL skeleton  --  IMPLEMENTATION (post-route) RESULT"
puts $rf " NOTE: ASCII-only labels on purpose. Chinese narrative lives in"
puts $rf "       docs/C_IMPLEMENTATION_STATUS.md (section: impl evidence)."
puts $rf "=============================================================="
puts $rf " 1  Vivado version        : [version -short]"
puts $rf " 2  FPGA part             : $target_part"
puts $rf " 3  synthesis strategy    : Vivado Synthesis Defaults"
puts $rf " 4  implementation         : EXECUTED  opt_design + place_design + phys_opt_design + route_design"
puts $rf " 5  bitstream              : NOT generated"
puts $rf " 6  top module             : $top_module"
puts $rf " 7  constraints            : constr/c_top.xdc"
puts $rf " 8  clock                  : MMCME2_BASE 24.0/1/6.0 -> clk_200 = ${target_clk_mhz} MHz"
puts $rf " 9  Git commit SHA         : $git_sha"
puts $rf "10  generation time        : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf "11  uncommitted changes    : $local_mod"
puts $rf "--------------------------------------------------------------"
puts $rf " Flow-A : synth, flatten_hierarchy=none  -> per-module resources"
puts $rf "   WNS = $a_wns ns   TNS = $a_tns ns   WHS = $a_whs ns"
puts $rf "   failing endpoints = $a_fail / $a_tot"
puts $rf "   (WARNING: timings from this flow are NOT representative;"
puts $rf "    flatten none blocks cross-module optimization. Use Flow B.)"
puts $rf " Flow-B : synth, default flatten  -> representative"
puts $rf "   WNS = $b_wns ns   TNS = $b_tns ns   WHS = $b_whs ns"
puts $rf "   failing endpoints = $b_fail / $b_tot"
puts $rf " Flow-B : post-route (representative)"
puts $rf "   WNS = $p_wns ns   TNS = $p_tns ns   WHS = $p_whs ns"
puts $rf "   failing endpoints = $p_fail / $p_tot"
puts $rf "--------------------------------------------------------------"
puts $rf " post-route resources"
puts $rf "   Block RAM Tile  : $bram_tile / 365"
puts $rf "   RAMB36/FIFO     : $bram36 / 365"
puts $rf "   RAMB18          : $bram18 / 730"
puts $rf "   URAM            : $uram / 0   (Artix-7 has no URAM)"
puts $rf "   DSP48E1         : $dsp / 740"
puts $rf "   Slice LUTs      : $lut"
puts $rf "   Slice Registers : $ff"
puts $rf "--------------------------------------------------------------"
puts $rf " DISCIPLINE"
puts $rf "  * This file is POST-ROUTE (implementation). It must NOT be quoted"
puts $rf "    interchangeably with report/synth_result.txt (synthesis only)."
puts $rf "  * No bitstream was generated. WNS>0 is not a frame-rate claim."
puts $rf "  * Per-module resources come from Flow A (flatten none, synthesis"
puts $rf "    only) -> report/impl/util_synth_A_hier_none.rpt"
puts $rf "  * Reports: report/impl/"
puts $rf "=============================================================="
close $rf

puts ""
puts " Flow-A synth(flatten none) WNS=$a_wns  fail=$a_fail/$a_tot"
puts " Flow-B synth(default)      WNS=$b_wns  fail=$b_fail/$b_tot"
puts " Flow-B post-route          WNS=$p_wns  TNS=$p_tns  fail=$p_fail/$p_tot"
puts " post-route RAMB36=$bram36 RAMB18=$bram18 Tile=$bram_tile URAM=$uram DSP=$dsp LUT=$lut FF=$ff"
puts " -> $out_dir/impl_result.txt"
puts ""
