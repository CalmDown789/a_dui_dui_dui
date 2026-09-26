# 真实 B+C 五层：150 MHz 布线裕量补试

日期：2026-09-26。**最终推荐 `route_setup030`：原约束下 WNS/TNS 为 +0.492/0 ns，WHS/THS 为 +0.018/0 ns，路由错误为 0。** 相比旧 NetDelay 的 +0.132 ns 提升 0.360 ns，达到本轮约 +0.4 ns 的目标。用于实现的 RTL、XDC 和 ROM 均未修改。

## 条件与证据

- 工作树：`10h冲刺_c_trial`，分支 `member-b-2025-2-bc-trial`，HEAD `7a891e7321e5e5d971d1d9b7a29a9992668322df`。
- Vivado 2025.2，器件 `xc7a200tfbg484-2`，顶层 `c_synth_top`，真实五层 B 核与 C 外壳，真实 A ROM bank16，36 位累加，条带 RAM `ram_decomp="power"`。
- 50 MHz 经 MMCM 产生 150 MHz；最终报告周期为 6.667 ns。使用现有实验 `constr/c_top.xdc`。
- 继承原 NetDelay 的 `ExtraNetDelay_high`、`AggressiveExplore`、`NoTimingRelaxation`，以及综合后 L5 相位网络 `MAX_FANOUT 48`。
- 原 NetDelay 日志的相位集合共 49 条网络，46 条超过阈值并实际设置属性。旧文档“仅改三个实现指令”已补正；不能省略该段复现。
- 本轮四组均完成布线。65 个共有 RTL/XDC/ROM 源文件哈希一致；最终清单另含两份运行脚本和父布局检查点。已有未提交文件的哈希检查通过，未提交、推送或合并 Git。

原始报告和 SHA-256：[`member_b_evidence/timing_margin_20260926/`](../member_b_evidence/timing_margin_20260926/)。每组有 `summary.json`、`source_manifest.json`、时序、资源、时钟、路由与 DRC 原件。

## 同条件结果

| 方案 | WNS / TNS (ns) | WHS / THS (ns) | LUT | FF | RAMB36/18 | DSP | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| 旧 NetDelay | +0.132 / 0 | +0.019 / 0 | 28,078 | 48,498 | 226/8 | 394 | 本轮比较基准 |
| `forcefifo`：L5 写指针定向物理复制 | +0.124 / 0 | +0.018 / 0 | 28,078 | 48,654 | 226/8 | 394 | 总裕量未改善 |
| `setup030`：布局加压，布线前恢复 | +0.183 / 0 | +0.019 / 0 | 28,100 | 48,498 | 226/8 | 394 | 提升 51 ps |
| `multi_target`：四组网络定向复制 | +0.230 / 0 | +0.019 / 0 | 28,078 | 50,773 | 226/8 | 394 | 提升 98 ps，增加 2,275 FF |
| **`route_setup030`：同一布局，布线继续加压，结束后恢复** | **+0.492 / 0** | **+0.018 / 0** | **28,100** | **48,498** | **226/8** | **394** | **本轮推荐** |

所有四组新结果 route errors 均为 0。最终推荐比旧 NetDelay 增加 22 LUT，FF、BRAM 与 DSP 数量相同。本轮达到目标后停止继续扫参。

## 为什么这是有效改善

`setup030` 在综合后仅对 150 MHz 同时钟域增加 0.300 ns **setup** user uncertainty，迫使工具用更紧的时间预算布局、物理优化。它在布线前恢复原值，得到 +0.183 ns。

最终 `route_setup030` 从完全相同的 `placed_setup030.dcp` 开始，保留这 0.300 ns 额外要求完成布线，然后恢复原约束评价。两份时序报告之间只更新时序并保存报告，未再做布局、物理优化或布线。

| 同一布线结果的评价条件 | WNS/TNS | WHS/THS | setup user uncertainty |
|---|---:|---:|---:|
| 加压条件 | +0.192/0 ns | +0.018/0 ns | 0.300 ns |
| 原条件 | +0.492/0 ns | +0.018/0 ns | 0.000 ns |

WNS 恰好相差 0.300 ns，hold 完全一致。自动计算的抖动等 clock uncertainty **0.071 ns 仍保留**；没有通过删除时钟抖动或放宽原约束制造正裕量。导出 XDC 的有效命令与原始版本相比，仅新增先设 0.300、后覆盖为 0.000 的两条 setup uncertainty 命令。

最终原件：[`timing_summary_postroute.rpt`](../member_b_evidence/timing_margin_20260926/route_setup030/timing_summary_postroute.rpt)；加压对照：[`timing_summary_route_setup030.rpt`](../member_b_evidence/timing_margin_20260926/route_setup030/timing_summary_route_setup030.rpt)。

## 瓶颈变化

- 旧 NetDelay：L5 FIFO 写指针到分布式 RAM 写地址，数据路径 6.386 ns，其中布线 6.007 ns。
- 仅复制写指针：最差路径转到 C 条带 RAM 写数据；继续复制 ROM 地址、条带数据和窗口使能后，最差路径转为 L5 控制信号到新增指针寄存器。增加副本会使驱动副本的上游控制网变重，因此复制数量不能直接等同于时序收益。
- 最终推荐：最差仍为 L5 `fifo/wr_ptr_reg[0]` 到 `g_read_slice[95]` 的 `RAMD32/WADR0`，数据路径 **6.033 ns**，其中布线 **5.654 ns（93.718%）**，无 LUT 逻辑级。当前改善主要来自物理实现，不是网络算法或流水级变化。
- 最终 **75,842/75,842** 条可布线网络全部完成；无无时钟寄存器，也无未约束内部端点。

## 本机复现

脚本入口：[`experiments/timing_margin_20260926/`](../experiments/timing_margin_20260926/)。干净克隆先运行 `python experiments/timing_margin_20260926/prepare_input_rom.py`，从已入库的 16 个真实 bank 重建脚本仍需 staging 的大输入 ROM，工具会核对冻结哈希并拒绝覆盖不同内容。Vivado 启动目录须为 ASCII 路径。本机用 `V:` 映射该工作树；运行前确认 `V:` 空闲，或已经指向这里。

```powershell
# 若 V: 尚未映射，创建本机目录别名。
subst V: 'F:\FPGA预选\10h冲刺_c_trial'
Push-Location 'V:/'
try {
    # 完整综合/布局并保存加压布局检查点；也产生布线前恢复的对照组。
    & 'F:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -source 'experiments/timing_margin_20260926/synth_setup030.tcl' -log 'experiments/timing_margin_20260926/setup030.log' -journal 'experiments/timing_margin_20260926/setup030.jou' -tclargs impl acc36 ascii ramdecomp
    if ($LASTEXITCODE -ne 0) { throw 'setup030 failed' }

    # 从上一步保存的同一布局继续加压布线，再恢复原约束报告。
    & 'F:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -source 'experiments/timing_margin_20260926/route_setup030.tcl' -log 'experiments/timing_margin_20260926/route_setup030.log' -journal 'experiments/timing_margin_20260926/route_setup030.jou'
    if ($LASTEXITCODE -ne 0) { throw 'route_setup030 failed' }
}
finally {
    Pop-Location
}
```

第二步需要第一步生成的 `_synth_bc/acc36_realrom_150_member_b_setup0300926_ascii_ramdecomp/placed_setup030.dcp`，不可用其它布局替代。此次检查点 SHA-256 为 `172ef002cb7319f4fbc3da526d1847a7419b866883269800ac97973592c70cf0`。最终检查点为 `_synth_bc/margin0926_route_setup030/postroute.dcp`，已保存恢复后的约束。日志末尾有 `MARGIN0926_ROUTE_SETUP030_COMPLETE`，Vivado 正常退出。

## 适用边界与理解状态

本结论为当前器件、工具、叠层和实验 XDC 的 post-route 静态时序结果。现有 9 个输出端口无 output delay；`uart_tx` 仍有 NSTD-1/UCIO-1，实验报告不等于完整板级 XDC 签核或可直接上板的 bitstream。本次未生成 bitstream、未做板测，也未声称连续多帧或 30 fps 已验收。当前阶段的多帧通路任务不变。

本轮用于实现的功能 RTL 未变，沿用此前原 RTL 的 Golden 仿真证据；未新增门级仿真或物理网表等价证明。`srl_candidate/` 只保留为未验证草稿，未仿真、未综合实现、未纳入推荐。

后续发布：用户已授权提交本次完成结果及 C 上板交接到 `member-b-2025-2-bc-trial`，仅推送该实验分支。未验证 SRL 草稿留在本地。C 的步骤见 [`MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md`](MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md)；200 MHz 优化在独立目录继续，不阻塞 C 使用本次结果。

工程实验由助手执行，证据已核对。用户对 setup/hold、加压实现与原约束验收的解释仍待复述和亲自复现，不能据此标为“已掌握”。需要理解：0.300 ns 是工具优化时额外的时间要求；最终 +0.492 ns 来自恢复原条件后的同一布线。导师追问时应能说明为何恢复后恰差 0.300 ns、为何 hold 不变，以及为何正 WNS 不能证明实际视频帧率。

方法依据：[AMD UG835 set_clock_uncertainty](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/set_clock_uncertainty)、[AMD UG949 设计过约束](https://docs.amd.com/r/zh-CN/ug949-vivado-design-methodology/设计过约束)、[AMD UG835 phys_opt_design](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/phys_opt_design)。`setup030` 采用 UG949 推荐的布线前恢复；最终方案是另做的“保持加压至布线结束”对照，不能称为该推荐流程。
