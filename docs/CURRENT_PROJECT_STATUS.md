# FSRCNN FPGA 项目当前状态

**快照时间：2026-09-24（北京时间）**  
**仓库：`CalmDown789/a_dui_dui_dui`，分支：`c-side-latest`**  
本文记录本机 Vivado/XSim 2022.2 的可复现证据，不代表 bitstream 或板上验收。

## C 端与真实 B 集成状态

### 当前 RTL 和回归

- 正式综合/仿真启用 `C_USE_B_REAL`，真实 B 来自 `ae29515` 的五层依赖闭包；11 个上游文件保持锁定，另有 4 个本地兼容/时序覆盖：`phase_mac_pipeline`、`phase_accumulator`、`vector_postprocess_shared`、`prelu_requantize`。
- C 侧在输入 ROM 到 B 前增加两项局部改动：请求地址寄存并与同步 ROM 响应握手；C→B 加 2-entry FIFO，`ready` 由寄存占用量产生，断开 B 反压到 ROM 地址/使能组合路径。
- 完整仿真组 **9/9 PASS**：C 条带缓存、随机背压、C ready/valid、C 顶层、B 原语、B 真实核 smoke、真实核长背压、96×54 bit-exact、960×540 全帧。
- 全帧证据：输入 518,400/518,400；输出 2,073,600/2,073,600；逐字节匹配 A 整数 Golden；mismatch=0、X=0；stripe_last=17/17、frame_last=1/1、done=1、hold-rule violation=0。全帧仿真耗时约 36 分 28 秒。
- 小图 ready/valid 两帧：输入 1,024/1,024；输出/UART 4,096/4,096；UART error、proto_err、overflow_err 均为 0。
- B bit-exact 使用 `xelab -O0`。此设置是 XSim 2022.2 的仿真配置，不改变 RTL 和综合；默认优化异常保留为工具对照记录。

### 综合与布局布线

使用 `scripts/synth_bc_real.tcl -tclargs impl`，器件 `xc7a200tfbg484-2`，真实 B 路径自检通过：`b_core_real=1`、`b_core_stub=0`、5 层、7 个 FIFO、1 个 PixelShuffle。

| 指标 | 综合 | 布线后 |
|---|---:|---:|
| RAMB36 / RAMB18 | 230 / 8 | 230 / 8 |
| DSP48E1 | 394 | 394 |
| LUT | 32,243 | 32,152 |
| FF | 41,673 | 41,932 |
| WNS / TNS | -1.169 ns / -8,153.583 ns | -2.208 ns / -50,037.625 ns |
| WHS / THS | +0.029 ns / 0 ns | +0.036 ns / 0 ns |
| Vivado 报告峰值内存 | 3.13 GB | 4.13 GB |

route 完成且 DRC 为 0 errors；有 29 warnings，主要涉及未分配 UART 引脚及 BRAM/DSP pipeline advice。200 MHz 时序**没有闭合**。布线后最差路径来自 L5 的 phase 选择寄存器到 DSP48E1 输入：数据路径 3.669 ns，其中 route 2.979 ns（81.2%），逻辑两级（LUT6、MUXF7）。C ROM 地址路径不再是当前报告的最差路径，但仍需关注物理布局对其高扇出 bank enable 的影响。

这次将 MAC phase 选择操作数额外寄存一拍的实验虽通过 smoke、背压及 4 组 bit-exact，但综合吸收了该级寄存器，未打断预期的 phase→DSP 物理路径；最终 WNS 为 -2.370 ns，比保留版本 -2.208 ns 更差，已撤销，不进入当前 RTL。

随后仅改实现策略、未改 RTL，使用 `phys_opt_design -directive AggressiveFanoutOpt` 与
`route_design -directive Explore` 做了一次真实 B+C 对照 route：WNS/TNS 为
-1.949 ns / -48,730.961 ns，最差路径从 L5 转移到 L3 phase→DSP，布线延迟仍占约 81%。
WNS 比默认实现改善 0.259 ns，但 route 时间从 4:16 增至 13:18，200 MHz 仍未闭合；
故保留默认脚本，并将该策略作为已测量的慢速备选，不继续盲扫实现指令。数据见
`report/bc_real_synth/physopt_aggressive_fanout_trial_20260924.txt`。

之后测试了按 output lane 复制 3-bit phase 状态的 RTL 候选。smoke、长背压、96×54
bit-exact 和真实 B 层级自检均通过，但完整 route 出现拥塞迭代；布线后 WNS/TNS
退化为 -2.975 ns / -75,872.156 ns，较默认实现差 0.767 ns，LUT 增加 8,568（26.7%），
route 耗时约 8:05。最差路径仍是 phase 控制到 DSP 输入，route 占数据延迟 84.9%，
局部 phase 副本驱动网扇出仍有 347。该候选已撤销，正式 RTL 未改变；报告见
`report/bc_real_synth/phase_local_phase_state_trial_20260924.txt`。结论是不要再按整个
output lane 复制二进制 phase 状态，也不能用综合 WNS 代替 post-route 判断。

之后基于实际路径测试了一个仅作用于实现阶段的约束：综合后识别 L5 `out_phase_reg` 的 Q 网，
只对直接负载超过 48 的网设置 `MAX_FANOUT=48`。本次找到 38 条相位 Q 网，其中 18 条超过阈值；
真实 B 层级自检通过。完整 route 的 WNS/TNS 从基线 `-2.208/-50,037.625 ns` 改为
`-2.057/-47,234.746 ns`，改善 `0.151 ns/2,802.879 ns`。LUT `32,152→32,166`、FF
`41,932→42,149`，BRAM/DSP 不变，route 时间 `4:16→4:11`，峰值内存约 `4.13 GB`。
最差路径转到 L5 窗口数据寄存器经 LUT6+MUXF7 到 DSP48E1，data delay `3.521 ns`
（route `2.805 ns`，79.7%）；第二差路径仍是 phase→DSP，slack `-2.040 ns`。此约束已加入
`scripts/synth_bc_real.tcl` 作为当前本机实现候选；200 MHz 仍未闭合，不能上板签收。原始试验报告
保存在本机忽略目录 `_synth_bc/fanout48_narrow/`；汇总见
`report/bc_real_synth/fanout48_phase_limit_trial_20260924.txt`。下一轮应针对 L5 窗口数据寄存器到
选择器/DSP 的长布线进行局部化试验，并检查是否只是把路径在数据与控制间来回搬移。

另以相同 RTL 检验了降频预案：150 MHz post-route WNS/TNS 为 -0.585/-751.208 ns，
仍被 L5 phase→DSP 限制；120 MHz 时 WNS/TNS 为 +0.012/0 ns，但只有 12 ps 正 slack。
在 120 MHz 下最差路径转为 C 输入请求地址寄存器到 ROM BRAM 地址端，数据延迟 7.370 ns，
其中 6.991 ns 是布线延迟，地址网扇出 22。120 MHz 只能算工具报告边缘通过，不能视为有
足够裕量的板测配置；同时 DRC 仍有大量 DSP pipeline advice，uart_tx 管脚未约束。两个
降频结果均未生成 bitstream，也未改变正式 200 MHz 配置；完整报告见
`report/bc_real_synth/clock_fallback_trial_20260924.txt`。

## 综合内存问题结论

原异常根因是 `phase_mac_pipeline` 的运行时 `in_phase` 驱动宽 packed-bus part-select；Vivado 在 RTL Optimization Phase 2 将综合网表规模异常膨胀，旧运行达到约 30.4 GB 后无法完成。静态 `case` 相位索引修复后，真实 B+C 完整综合峰值约 3.13 GB、实现峰值约 4.13 GB，资源规模符合小型流式 CNN accelerator 的范围。详细前后证据、层级资源及 RAM 映射见 `docs/RTL_SYNTHESIS_MEMORY_AUDIT.md`。

## 2026-09-24 后续实现候选与接手状态

之后完成了一个 L5 FIFO 宽字分片候选的完整 route：post-route WNS/TNS `-0.738 ns / -3,137.469 ns`，器件资源 RAMB36/RAMB18 `174/8`、DSP48E1 `394`、LUT `31,313`、FF `50,025`，route status 为 78,989/78,989 nets fully routed、0 routing errors，Vivado 报告峰值内存约 4.20 GB。该结果与匹配的 bank16 临时基线相比 WNS 改善 359 ps，但它使用一组 C 输入 ROM/边界实验 overlay，不能当成当前正式 RTL 的单改动结果；200 MHz 仍未闭合。

另有 36-bit phase accumulator overlay 通过边界/随机定向探针、C+B smoke 和综合（LUT `29,644`、FF `48,358`、综合 WNS `-0.855 ns`），尚未 place-and-route。新成员接续要求、overlay 与原始报告见 [`docs/FPGA_TIMING_HANDOFF_2026-09-24.md`](FPGA_TIMING_HANDOFF_2026-09-24.md)。用户已要求后续 Vivado/XSim 在其他具备 Vivado 2022.2 与器件 license 的 runner 上运行；本机不再续跑。此时没有 bitstream，也没有板上图像验收。

## 板测状态与边界

- 尚未生成 bitstream，也没有板上 HDMI/输出图像、画质或吞吐验收记录。全尺寸 Golden PASS 是本机 XSim 数据，不能称为板测通过。
- 200 MHz 时序失败，因此现在还不能按目标频率签收上板性能。L5 phase-fanout 限制让 WNS 改善 0.151 ns，但最差路径已转到 L5 窗口数据→DSP，仍差 2.057 ns。150 MHz 仍失败；120 MHz 只有 12 ps slack 且暴露出输入 ROM 地址布线瓶颈，不能作为有裕量的交付配置。后续要继续改善 L5 选择器/DSP 输入路径，并确认 UART 管脚约束。
- UART TX 引脚约束仍待确认，真实 `start` 触发方案也需最终确定。板卡本机操作、器件编程、HDMI/串口采集属于必须在接有 ACX750 的本机完成的工作。

## 后续工作拆分

### 必须在带 Vivado 的本机完成

1. 继续做有界的物理路径优化：200 MHz 的 L5 phase→DSP 是主瓶颈；降到 120 MHz 后又暴露 C 请求地址→ROM BRAM 的长布线。现有 phase 复制试验已证明整 output lane 复制不划算；FanoutOpt+Explore 仅小幅改善且 route 时间很长。下一项 RTL 试验应先从静态时序路径、扇出与 RAM bank 物理位置提出单一假设；最多综合筛选一次、route 一次，有明确 post-route 改善才保留。不可把 120 MHz 的 12 ps 裕量作为签收依据。
2. 只有时序与启动/引脚约束达到板测门槛后再生成 bitstream；在 C 手上的板卡采集 HDMI 图像、UART 输出和吞吐数据，与同一版 A Golden 对拍。
3. 保存 Vivado/XSim 版本、ROM/Golden 哈希、完整资源/时序/DRC 报告及原始仿真摘要。

### 可由其他 GitHub 成员协作完成

1. 独立复核 RTL 修改、闭包来源和这份阶段状态；检查是否有遗漏的代码/文档证据。
2. 查阅项目约束和 B 侧实现，对 L5 phase 控制扇出/布局给出设计评审意见；建议必须附依据，不能以猜测替换板级要求。
3. 确认 UART 引脚、上板 start 方案及可接受的最低时钟/帧率目标；提供书面验收门槛。
4. GitHub 可做代码审查和文档校验；当前仓库没有已配置的 Vivado GitHub Actions runner，综合/布局布线不能假定会在 GitHub 自动执行。

## 给阶段性总结作者的事实边界

总结时可引用：全尺寸 **本机仿真**通过、真实 B+C 综合和 route 已完成、峰值内存约 3.13/4.13 GB、post-route WNS=-2.208 ns。必须同时写明：200 MHz 未收敛、没有 bitstream、没有板上图像或性能验收。不要把本机 Golden 对拍写成板测，也不要把 C+stub 的资源结果替代真实 B+C 数据。
