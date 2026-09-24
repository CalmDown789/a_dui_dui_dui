# 成员B工作：150 MHz fallback，使用真实 A 输入 ROM，与 200 MHz 实验分开取证。
# 成员B工作：冻结的 A 输入 ROM bank16 实现取证
##############################################################################
# synth_bc_realrom_150_member_b.tcl —— 150 MHz 候选，真实 B+C+A 输入 ROM
#-----------------------------------------------------------------------------
# 与 scripts/synth_check.tcl 的区别（**这是本脚本存在的唯一理由**）：
#   synth_check.tcl 只把 B 的**旧原语**读进内存**而不实例化**，因此资源数字
#   完全来自 C 侧 + `b_core_stub`，**不反映 B 的五层网络**。
#   本脚本用 `synth_design -verilog_define C_USE_B_REAL` 让 b_core_if 真正
#   实例化 `b_core_real`，并综合 ae29515 + C 局部补丁的 15 文件闭包，从而得到
#   「B 五层 + C 外壳」在目标器件上的**实测**资源。
#
# 用法（从仓库根目录）：
#   vivado -mode batch -source experiments/l5_splitmem_20260924/synth_bc_realrom_150_member_b.tcl -tclargs impl
#   vivado -mode batch -source experiments/l5_splitmem_20260924/synth_bc_realrom_150_member_b.tcl -tclargs impl acc36
#
# 前置条件（脚本自动完成）：
#   · B 的 19 个 `*_packed.mem` 必须位于 **运行 vivado 时的工作目录**
#     —— `fsrcnn_network_mem_top.sv` 用裸文件名调用 $readmemh。
#     本脚本把它 stage 到 `_synth_bc/`，并在其中 cd。
#   · `c_synth_top` 的 ROM_INIT_FILE("rtl/input_image_pattern.mem") 同样是
#     CWD 相对路径，故 `_synth_bc/rtl/input_image_pattern.mem` 也被 stage。
#
# 自校验：综合后必须能在层次中找到 `b_core_real`；若找到的是 `b_core_stub`，
#         说明 -verilog_define 未生效，脚本以 FAIL 结束，数字一律作废。
##############################################################################

set target_part    "xc7a200tfbg484-2"
set top_module     "c_synth_top"
set target_clk_mhz 150
set do_impl 0
set variant "l5splitmem_realrom_150_member_b_fanout"
if {[info exists argv] && [lsearch -exact $argv "acc36"] >= 0} { set variant "acc36_realrom_150_member_b_fanout" }
if {[info exists argv] && [lsearch -exact $argv "ascii"] >= 0} { append variant "_ascii" }
set use_ramdecomp [expr {[info exists argv] && [lsearch -exact $argv "ramdecomp"] >= 0}]
if {$use_ramdecomp} { append variant "_ramdecomp" }
if {[info exists argv]} { foreach a $argv { if {$a eq "impl"} { set do_impl 1 } } }

set script_dir [file normalize [file dirname [info script]]]
set root_dir   [file normalize "$script_dir/../.."]
set experiment_dir "$root_dir/experiments/l5_splitmem_20260924"
set rtl_dir    "$root_dir/rtl"
set input_rom_file "$experiment_dir/rtl/c/input_rom.v"
set xdc_dir    "$root_dir/constr"
set b_real_dir "$rtl_dir/b_real_ae29515"
set fifo_file "$experiment_dir/rtl/b/elastic_fifo.sv"
set mac_issue_file "$experiment_dir/rtl/b/mac_issue_stage.sv"
set stream_layer_file "$experiment_dir/rtl/b/fsrcnn_stream_layer.sv"
set network_core_file "$experiment_dir/rtl/b/fsrcnn_network_core.sv"
set phase_acc_file "$experiment_dir/rtl/b/phase_accumulator.sv"
if {[info exists argv] && [lsearch -exact $argv "acc36"] >= 0} { set phase_acc_file "$experiment_dir/rtl/b/phase_accumulator_36.sv" }
set input_stream_file "$experiment_dir/rtl/c/input_stream.v"
set c_core_file "$experiment_dir/rtl/c/c_core.v"
set stripe_file "$rtl_dir/stripe_buffer.v"
if {$use_ramdecomp} { set stripe_file "$experiment_dir/rtl/c_ramdecomp_member_b/stripe_buffer.v" }
set b_patch_dir "$experiment_dir/rtl/b"
set rom_dir    "$root_dir/rom/member_a_d16_s8_m1_c16"
set stage      "$root_dir/_synth_bc/$variant"
set out_dir    "$stage/reports"
file mkdir $out_dir

#-----------------------------------------------------------------------------
# 0. staging（ROM 裸文件名 + 输入图案 ROM 的相对路径都要靠 CWD）
#-----------------------------------------------------------------------------
file mkdir "$stage/rtl"
set real_input_rom "$root_dir/ref/a_full_integer_golden/input_rom_2p19_u8.mem"
if {![file exists $real_input_rom]} { error "missing frozen A full input ROM: $real_input_rom" }
file copy -force $real_input_rom "$stage/rtl/input_image_pattern.mem"
set roms [glob -nocomplain -types f -directory $rom_dir *_packed.mem]
if {[llength $roms] != 19} { error "期望 19 个 *_packed.mem，实得 [llength $roms]（$rom_dir）" }
foreach f $roms { file copy -force $f "$stage/[file tail $f]" }
puts "== staged [llength $roms] packed ROMs + frozen A input ROM to $stage =="
set real_bank_dir "$root_dir/member_b_evidence/real_banks"
set real_bank_files [glob -nocomplain -types f -directory $real_bank_dir rom_bank_*.mem]
if {[llength $real_bank_files] != 16} { error "expected 16 real A image banks under $real_bank_dir" }
foreach f $real_bank_files { file copy -force $f "$stage/[file tail $f]" }
puts "== staged 16 real A image ROM banks from $real_bank_dir =="
cd $stage

set git_sha "unknown"
catch {set git_sha [string trim [exec git -C $root_dir rev-parse HEAD]]}
set local_mod "unknown"
if {[catch {exec git -C $root_dir status --porcelain -- {*}[list rtl tb scripts constr docs rom] } g]} {
    set local_mod "(git status unavailable)"
} else {
    set local_mod [string map {\n { }} [string trim $g]]
    if {$local_mod eq ""} { set local_mod "clean" }
}

puts "================================================================"
puts " REAL B five-layer + C shell -- SYNTHESIS (part $target_part)"
puts " top=$top_module  C_USE_B_REAL=1  do_impl=$do_impl"
puts "================================================================"

#-----------------------------------------------------------------------------
# 1. 读入 C 侧（与 synth_check.tcl 同列表，保证可比）
#-----------------------------------------------------------------------------
set c_files [list \
    "$rtl_dir/c_config.vh"     \
    $input_rom_file     \
    $input_stream_file  \
    $stripe_file \
    "$rtl_dir/pingpong_buffer.v"\
    "$rtl_dir/output_stream.v" \
    "$rtl_dir/uart_tx.v"       \
    "$rtl_dir/readback_ctrl.v" \
    "$rtl_dir/c_ctrl.v"        \
    "$rtl_dir/b_core_stub.v"   \
    "$rtl_dir/b_core_if.v"     \
    $c_core_file        \
    "$experiment_dir/rtl/c_150_member_b/c_top.v"         \
    "$experiment_dir/rtl/c_150_member_b/c_synth_top.v"   \
]
foreach f $c_files { if {![file exists $f]} { error "缺少 C 侧 RTL: $f" } }
read_verilog -verbose $c_files

#-----------------------------------------------------------------------------
# 1b. 读入 **B 真实五层依赖闭包**（11 个冻结 ae29515 文件 + 4 个 C 局部补丁）
#-----------------------------------------------------------------------------
# 注：15-file 依赖闭包由 11 个锁定 B 源文件和 4 个 C 侧局部补丁组成，
#     与 run_sim.tcl 的正式仿真路径**完全一致**；B 原仓库 stream/ 下另有
#     phase_mac_array.sv / vector_postprocess_elastic.sv / mac_lane_map.sv 等
#     未被 mem_top 层次引用的文件，故意不纳入，以保证「仿真路径 == 综合路径」。
set b_files [list \
    "$b_real_dir/stream/same_pad_raster.sv"            \
    $fifo_file               \
    "$b_real_dir/stream/window_kminus1_bram.sv"        \
    "$b_real_dir/stream/window_stream_frontend.sv"     \
    "$b_real_dir/stream/eight_phase_issue.sv"          \
    "$b_patch_dir/phase_mac_pipeline.sv"               \
    $phase_acc_file                \
    $mac_issue_file            \
    "$b_patch_dir/vector_postprocess_shared.sv"        \
    $stream_layer_file        \
    "$b_real_dir/stream/pixel_shuffle2x_row_banks.sv"  \
    $network_core_file        \
    "$b_real_dir/stream/fsrcnn_network_mem_top.sv"     \
    "$b_real_dir/stream/b_core_real.sv"                \
    "$b_patch_dir/prelu_requantize.sv"                 \
]
foreach f $b_files { if {![file exists $f]} { error "缺少 B 真实 RTL: $f" } }
read_verilog -sv -verbose $b_files

read_xdc "$xdc_dir/c_top.xdc"

#-----------------------------------------------------------------------------
# 2. 综合（★ -verilog_define 让 b_core_if 真正例化 b_core_real）
#-----------------------------------------------------------------------------
synth_design -top $top_module -part $target_part \
    -flatten_hierarchy rebuilt \
    -verilog_define C_USE_B_REAL

# Bound fanout only on the actual L5 phase-register Q nets. The measured
# post-route baseline had replicated phase nets above 120 direct loads.
set l5_phase_regs [get_cells -quiet -hier -filter {NAME =~ *l5/mac/issue/out_phase_reg*}]
set l5_phase_q [get_pins -quiet -of_objects $l5_phase_regs -filter {REF_PIN_NAME == Q}]
set l5_phase_nets [get_nets -quiet -of_objects $l5_phase_q]
puts "L5 phase fanout cap: regs=[llength $l5_phase_regs], Q pins=[llength $l5_phase_q], direct nets=[llength $l5_phase_nets]"
if {[llength $l5_phase_regs] == 0 || [llength $l5_phase_regs] > 64 || [llength $l5_phase_nets] == 0} {
    error "Unexpected L5 phase register collection; refusing broad fanout constraint"
}
foreach n $l5_phase_nets {
    set loads [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}]
    if {[llength $loads] > 48} {
        puts "L5 phase MAX_FANOUT 48: [get_property NAME $n] loads=[llength $loads]"
        set_property MAX_FANOUT 48 $n
    }
}

#-----------------------------------------------------------------------------
# 2b. 自校验：必须真的用上 b_core_real
#-----------------------------------------------------------------------------
set n_real  [llength [get_cells -quiet -hier -filter {REF_NAME =~ b_core_real*}]]
set n_stub  [llength [get_cells -quiet -hier -filter {REF_NAME =~ b_core_stub*}]]
set n_top   [llength [get_cells -quiet -hier -filter {REF_NAME =~ fsrcnn_network_mem_top*}]]
set n_layer [llength [get_cells -quiet -hier -filter {REF_NAME =~ fsrcnn_stream_layer*}]]
set n_pshuf [llength [get_cells -quiet -hier -filter {REF_NAME =~ pixel_shuffle2x_row_banks*}]]
set n_fifo  [llength [get_cells -quiet -hier -filter {REF_NAME =~ elastic_fifo*}]]
puts "SELF-CHECK: b_core_real cells=$n_real  b_core_stub cells=$n_stub"
puts "SELF-CHECK: fsrcnn_network_mem_top=$n_top  fsrcnn_stream_layer=$n_layer"
puts "SELF-CHECK: pixel_shuffle2x_row_banks=$n_pshuf  elastic_fifo=$n_fifo"
set use_real "OK"
if {$n_real != 1 || $n_stub != 0 || $n_top != 1 || $n_layer != 5 || $n_pshuf != 1 || $n_fifo < 4} {
    error "Member B hierarchy check failed: real=$n_real stub=$n_stub top=$n_top layers=$n_layer pixelshuffle=$n_pshuf fifo=$n_fifo"
}

# Member B timing experiment: retain the proven RTL and ask the placer to
# replicate only measured long, high-fanout paths. 2025.2 UG949 describes
# FORCE_MAX_FANOUT as a placement-time property; MAX_FANOUT above is a
# separate existing constraint retained for apples-to-apples comparison.
set issue_candidates [get_nets -quiet -hier -filter {NAME =~ *l5/mac/issue/out_window*}]
set issue_forced 0
puts "TIMING_OPT issue_candidates=[llength $issue_candidates]"
set issue_max 0
set issue_max_name "none"
foreach n $issue_candidates {
    set loads [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}]
    if {[llength $loads] > $issue_max} {
        set issue_max [llength $loads]
        set issue_max_name [get_property NAME $n]
    }
    if {[llength $loads] > 1000} {
        puts "TIMING_OPT issue net=[get_property NAME $n] direct_loads=[llength $loads] FORCE_MAX_FANOUT=256"
        set_property FORCE_MAX_FANOUT 256 $n
        incr issue_forced
    }
}
puts "TIMING_OPT issue_max=$issue_max name=$issue_max_name"
if {$issue_forced == 0} { puts "TIMING_OPT no issue net was forced in this synthesis" }

set fifo_candidates [get_nets -quiet -hier -filter {NAME =~ *l5/gk.frontend/fifo/wr_ptr*}]
set fifo_forced 0
foreach n $fifo_candidates {
    set loads [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}]
    if {[llength $loads] > 500} {
        puts "TIMING_OPT fifo net=[get_property NAME $n] direct_loads=[llength $loads] FORCE_MAX_FANOUT=256"
        set_property FORCE_MAX_FANOUT 256 $n
        incr fifo_forced
    }
}
puts "TIMING_OPT targeted issue_nets=$issue_forced fifo_nets=$fifo_forced"

#-----------------------------------------------------------------------------
# 3. 综合级报告（先落盘，保证即使后面实现失败也有数据）
#-----------------------------------------------------------------------------
report_utilization      -file "$out_dir/utilization_synth.rpt"
report_utilization      -hierarchical -file "$out_dir/utilization_synth_hier.rpt"
report_timing_summary   -file "$out_dir/timing_summary_synth.rpt" -max_paths 20
report_clocks           -file "$out_dir/clocks_synth.rpt"
report_drc              -file "$out_dir/drc_synth.rpt"
catch {report_ram_utilization -file "$out_dir/ram_utilization_synth.rpt"}

#-----------------------------------------------------------------------------
# 4. 可选实现
#-----------------------------------------------------------------------------
set impl_status "NOT RUN"
set r_wns "n/a"; set r_tns "n/a"; set r_whs "n/a"; set r_ths "n/a"
set r_wns_s "n/a"; set r_tns_s "n/a"; set r_whs_s "n/a"; set r_ths_s "n/a"
if {$do_impl} {
    puts "== implementation: opt_design / place_design / phys_opt_design / route_design =="
    set ok 1
    if {[catch {opt_design} e]}                 { set ok 0; puts "opt_design FAILED: $e" }
    if {$ok && [catch {place_design} e]}        { set ok 0; puts "place_design FAILED: $e" }
    if {$ok && [catch {phys_opt_design} e]}     { set ok 0; puts "phys_opt_design FAILED: $e" }
    if {$ok && [catch {route_design} e]}        { set ok 0; puts "route_design FAILED: $e" }
    if {$ok} { set impl_status "COMPLETED" } else { set impl_status "FAILED" }
    catch {report_utilization      -file "$out_dir/utilization_postroute.rpt"}
    catch {report_utilization      -hierarchical -file "$out_dir/utilization_postroute_hier.rpt"}
    catch {report_timing_summary   -file "$out_dir/timing_summary_postroute.rpt" -max_paths 20}
    catch {report_clocks           -file "$out_dir/clocks_postroute.rpt"}
    catch {report_drc              -file "$out_dir/drc_postroute.rpt"}
    catch {report_route_status     -file "$out_dir/route_status.rpt"}
    catch {report_ram_utilization  -file "$out_dir/ram_utilization_postroute.rpt"}
}

#-----------------------------------------------------------------------------
# 5. 提取数字
#-----------------------------------------------------------------------------
proc grab {file pattern {dflt n/a}} {
    if {![file exists $file]} { return $dflt }
    set fh [open $file r]; set c [read $fh]; close $fh
    if {[regexp $pattern $c -> v]} { return $v }
    return $dflt
}
proc bram_of {util} {
    set b36 [grab $util {\|\s*RAMB36/FIFO\*?\s*\|\s*(\d+)\s*\|}]
    set b18 [grab $util {\|\s*RAMB18\s*\|\s*(\d+)\s*\|}]
    return [list $b36 $b18]
}
proc timing_of {tsum} {
    # 跨行正则必须显式 [^\n]*（Tcl ARE 的 . 匹配换行，见 impl_check.tcl「缺陷 5」）
    set res [list n/a n/a n/a n/a]
    if {![file exists $tsum]} { return $res }
    set fh [open $tsum r]; set tc [read $fh]; close $fh
    if {[regexp {WNS\(ns\)[^\n]*\n[^\n]*\n\s*(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+([0-9]+)\s+([0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)} \
            $tc -> w t fe te wh th]} {
        set res [list $w $t $wh $th]
    }
    return $res
}

set us "$out_dir/utilization_synth.rpt"
lassign [bram_of $us] bram36 bram18
set dsp [grab $us {\|\s*DSPs\*?\s*\|\s*(\d+)\s*\|}]
if {$dsp eq "n/a"} { set dsp [grab $us {\|\s*DSP48E1\s*\|\s*(\d+)\s*\|}] }
set lut    [grab $us {\|\s*Slice LUTs\*?\s*\|\s*(\d+)\s*\|}]
set ff     [grab $us {\|\s*Slice Registers\s*\|\s*(\d+)\s*\|}]
set bram_lut [grab $us {\|\s*LUT as Memory\s*\|\s*(\d+)\s*\|}]
set mmcm   [grab $us {\|\s*MMCME2_ADV\s*\|\s*(\d+)\s*\|}]
set pll    [grab $us {\|\s*PLLE2_ADV\s*\|\s*(\d+)\s*\|}]
set bufg   [grab $us {\|\s*BUFGCTRL\*?\s*\|\s*(\d+)\s*\|}]
lassign [timing_of "$out_dir/timing_summary_synth.rpt"] r_wns_s r_tns_s r_whs_s r_ths_s

set up "$out_dir/utilization_postroute.rpt"
set has_impl 0
if {[file exists $up]} { set has_impl 1 }
if {$has_impl} {
    lassign [bram_of $up] pb36 pb18
    set pdsp    [grab $up {\|\s*DSPs\*?\s*\|\s*(\d+)\s*\|}]
    if {$pdsp eq "n/a"} { set pdsp [grab $up {\|\s*DSP48E1\s*\|\s*(\d+)\s*\|}] }
    set plut    [grab $up {\|\s*Slice LUTs\*?\s*\|\s*(\d+)\s*\|}]
    set pff     [grab $up {\|\s*Slice Registers\s*\|\s*(\d+)\s*\|}]
    set pmmcm   [grab $up {\|\s*MMCME2_ADV\s*\|\s*(\d+)\s*\|}]
    set ppll    [grab $up {\|\s*PLLE2_ADV\s*\|\s*(\d+)\s*\|}]
    set pbufg   [grab $up {\|\s*BUFGCTRL\*?\s*\|\s*(\d+)\s*\|}]
    lassign [timing_of "$out_dir/timing_summary_postroute.rpt"] r_wns r_tns r_whs r_ths
} else {
    set pb36 "n/a"; set pb18 "n/a"; set pdsp "n/a"; set plut "n/a"; set pff "n/a"
    set pmmcm "n/a"; set ppll "n/a"; set pbufg "n/a"
}

#-----------------------------------------------------------------------------
# 6. 结果文件（纯 ASCII 标签 —— 理由见 synth_check.tcl 的编码陷阱注释）
#-----------------------------------------------------------------------------
set rf [open "$out_dir/bc_real_synth_result.txt" w]
fconfigure $rf -encoding utf-8
puts $rf "=========================================================="
puts $rf " REAL B five-layer + C shell : resource / timing evidence"
puts $rf "=========================================================="
puts $rf " 1  Vivado version     : [version -short]"
puts $rf " 2  FPGA part          : $target_part"
puts $rf " 3  top module         : $top_module"
puts $rf " 4  B RTL              : ae29515 closure + rtl/b_real_c_patch local RTL overrides"
puts $rf " 5  B param ROMs       : rom/member_a_d16_s8_m1_c16 (19 x *_packed.mem, \$readmemh, CWD)"
puts $rf " 6  C_USE_B_REAL       : via 'synth_design -verilog_define C_USE_B_REAL'"
puts $rf " 7  flatten_hierarchy  : rebuilt"
puts $rf " 8  clock              : sys_clk 50MHz (W19) -> MMCME2_BASE -> [expr {$target_clk_mhz}] MHz"
puts $rf " 9  Git commit SHA     : $git_sha"
puts $rf "10  uncommitted change : $local_mod"
puts $rf "11  generated at       : [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] (local)"
puts $rf "12  implementation     : $impl_status"
puts $rf "----------------------------------------------------------"
puts $rf " SELF-CHECK (must be OK, else everything below is void):"
puts $rf "   b_core_real cells            : $n_real"
puts $rf "   b_core_stub cells            : $n_stub   (must be 0)"
puts $rf "   fsrcnn_network_mem_top cells : $n_top"
puts $rf "   fsrcnn_stream_layer cells    : $n_layer  (must be 5)"
puts $rf "   pixel_shuffle2x_row_banks    : $n_pshuf"
puts $rf "   elastic_fifo cells           : $n_fifo"
puts $rf "   VERDICT                      : $use_real"
puts $rf "----------------------------------------------------------"
puts $rf " (A) SYNTHESIS-level (MEASURED)"
puts $rf "   RAMB36/FIFO   : $bram36 / 365"
puts $rf "   RAMB18        : $bram18 / 730"
puts $rf "   DSP48E1       : $dsp / 740"
puts $rf "   Slice LUTs    : $lut"
puts $rf "   Slice Regs    : $ff"
puts $rf "   LUT as Memory : $bram_lut"
puts $rf "   MMCME2_ADV    : $mmcm"
puts $rf "   PLLE2_ADV     : $pll"
puts $rf "   BUFGCTRL      : $bufg"
puts $rf "   WNS / TNS     : $r_wns_s / $r_tns_s ns"
puts $rf "   WHS / THS     : $r_whs_s / $r_ths_s ns"
puts $rf "----------------------------------------------------------"
puts $rf " (B) POST-ROUTE (MEASURED)"
puts $rf "   RAMB36/FIFO   : $pb36 / 365"
puts $rf "   RAMB18        : $pb18 / 730"
puts $rf "   DSP48E1       : $pdsp / 740"
puts $rf "   Slice LUTs    : $plut"
puts $rf "   Slice Regs    : $pff"
puts $rf "   MMCME2_ADV    : $pmmcm"
puts $rf "   PLLE2_ADV     : $ppll"
puts $rf "   BUFGCTRL      : $pbufg"
puts $rf "   WNS / TNS     : $r_wns / $r_tns ns"
puts $rf "   WHS / THS     : $r_whs / $r_ths ns"
puts $rf "----------------------------------------------------------"
puts $rf " reports : _synth_bc/$variant/reports/"
puts $rf "=========================================================="
puts $rf " NOTE 1: this DOES instantiate b_core_real (see SELF-CHECK)."
puts $rf "         Do NOT quote synth_check.tcl numbers as 'B network cost'."
puts $rf " NOTE 2: functional correctness of B is NOT implied by this file."
puts $rf "         Synthesis success != the five-layer net reproduces A Golden."
puts $rf " NOTE 3: Fmax / 30fps MUST NOT be claimed from synthesis-only data."
puts $rf "=========================================================="
close $rf

puts ""
puts " SELF-CHECK use_real = $use_real (real=$n_real stub=$n_stub top=$n_top layer=$n_layer)"
puts " synth: RAMB36=$bram36 RAMB18=$bram18 DSP=$dsp LUT=$lut FF=$ff MMCM=$mmcm BUFG=$bufg"
puts " synth: WNS=$r_wns_s TNS=$r_tns_s WHS=$r_whs_s THS=$r_ths_s"
puts " impl : $impl_status  WNS=$r_wns TNS=$r_tns WHS=$r_whs THS=$r_ths"
puts " -> $out_dir/bc_real_synth_result.txt"
puts ""
if {$do_impl && $impl_status ne "COMPLETED"} { error "Member B implementation did not complete" }
