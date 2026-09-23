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
puts " C 侧 RTL 骨架  —  仅综合（不做实现/不作位流）"
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
    if {![file exists $f]} { error "缺少 RTL 文件: $f" }
}
read_verilog -verbose $rtl_files
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
set wns "n/a"
if {[file exists $tsum]} {
    set fh [open $tsum r]; set tc [read $fh]; close $fh
    if {[regexp {WNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)} $tc -> w]} { set wns $w }
}

#-----------------------------------------------------------------------------
# 5. C17 十项必录信息
#-----------------------------------------------------------------------------
set rf [open "$out_dir/synth_result.txt" w]
puts $rf "=============================================="
puts $rf " C 侧 RTL 骨架  —  仅综合（synthesis only）结果"
puts $rf "=============================================="
puts $rf " 1  Vivado 版本        : [version -short]"
puts $rf " 2  FPGA part           : $target_part"
puts $rf " 3  synthesis strategy  : $synth_strategy (synth_design 默认)"
puts $rf " 4  implementation      : **未执行**（本轮明确不做）"
puts $rf " 5  top module          : $top_module"
puts $rf " 6  constraint 文件     : constr/c_top.xdc"
puts $rf " 7  clock configuration : MMCME2_BASE CLKFBOUT_MULT_F=24.0 / DIVCLK_DIVIDE=1 / CLKOUT0_DIVIDE_F=6.0 / CLKIN1_PERIOD=20.0 -> clk_200 = ${target_clk_mhz} MHz"
puts $rf " 8  Git commit SHA      : $git_sha"
puts $rf " 9  生成时间            : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf "10  未提交本地修改      : $local_mod"
puts $rf "----------------------------------------------"
puts $rf " RAMB36  : $bram36 / 365"
puts $rf " RAMB18  : $bram18 / 730"
puts $rf " DSP48E1 : $dsp / 740"
puts $rf " Slice LUTs    : $lut"
puts $rf " Slice Regs    : $ff"
puts $rf " LUT as Memory : $bram_lut"
puts $rf " WNS @200MHz (synthesis 级) : $wns ns"
puts $rf "----------------------------------------------"
puts $rf " 报告: report/utilization_synth.rpt"
puts $rf "       report/timing_summary_synth.rpt"
puts $rf "=============================================="
puts $rf " 注意：本结果为 **synthesis 级**，不是实现后结果；"
puts $rf "       未做 place/route，未生成 bitstream，**不得**据此宣称 Fmax。"
puts $rf "       BRAM 判据须按 §五.13（2）二级条件：BRAM_36K/BRAM_18K utilization。"
puts $rf "=============================================="
close $rf

puts ""
puts " RAMB36=$bram36  RAMB18=$bram18  DSP48E1=$dsp  LUT=$lut  FF=$ff"
puts " WNS(synth) = $wns ns @200MHz"
puts " -> $out_dir/synth_result.txt"
puts ""
