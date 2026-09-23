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

## 综合内存问题结论

原异常根因是 `phase_mac_pipeline` 的运行时 `in_phase` 驱动宽 packed-bus part-select；Vivado 在 RTL Optimization Phase 2 将综合网表规模异常膨胀，旧运行达到约 30.4 GB 后无法完成。静态 `case` 相位索引修复后，真实 B+C 完整综合峰值约 3.13 GB、实现峰值约 4.13 GB，资源规模符合小型流式 CNN accelerator 的范围。详细前后证据、层级资源及 RAM 映射见 `docs/RTL_SYNTHESIS_MEMORY_AUDIT.md`。

## 板测状态与边界

- 尚未生成 bitstream，也没有板上 HDMI/输出图像、画质或吞吐验收记录。全尺寸 Golden PASS 是本机 XSim 数据，不能称为板测通过。
- 200 MHz 时序失败，因此现在还不能按目标频率签收上板性能。下一个门槛是缩短 L5 phase→DSP 的物理路径并重新完整 route；是否降低目标频率需按项目验收要求另行决定。
- UART TX 引脚约束仍待确认，真实 `start` 触发方案也需最终确定。板卡本机操作、器件编程、HDMI/串口采集属于必须在接有 ACX750 的本机完成的工作。

## 后续工作拆分

### 必须在带 Vivado 的本机完成

1. 分析 L3/L5 phase 控制到 DSP 的高扇出和跨区域布线；已测的 FanoutOpt+Explore 仅改善 0.259 ns 且明显加长 route 时间。下一个试验应让 phase 状态按 output-lane group 本地化，跑真实 B bit-exact/backpressure、综合和完整 route；若不能显著缩短相位控制网，停止该结构并重新评估并行度/时钟目标。
2. 只有时序与启动/引脚约束达到板测门槛后再生成 bitstream；在 C 手上的板卡采集 HDMI 图像、UART 输出和吞吐数据，与同一版 A Golden 对拍。
3. 保存 Vivado/XSim 版本、ROM/Golden 哈希、完整资源/时序/DRC 报告及原始仿真摘要。

### 可由其他 GitHub 成员协作完成

1. 独立复核 RTL 修改、闭包来源和这份阶段状态；检查是否有遗漏的代码/文档证据。
2. 查阅项目约束和 B 侧实现，对 L5 phase 控制扇出/布局给出设计评审意见；建议必须附依据，不能以猜测替换板级要求。
3. 确认 UART 引脚、上板 start 方案及可接受的最低时钟/帧率目标；提供书面验收门槛。
4. GitHub 可做代码审查和文档校验；当前仓库没有已配置的 Vivado GitHub Actions runner，综合/布局布线不能假定会在 GitHub 自动执行。

## 给阶段性总结作者的事实边界

总结时可引用：全尺寸 **本机仿真**通过、真实 B+C 综合和 route 已完成、峰值内存约 3.13/4.13 GB、post-route WNS=-2.208 ns。必须同时写明：200 MHz 未收敛、没有 bitstream、没有板上图像或性能验收。不要把本机 Golden 对拍写成板测，也不要把 C+stub 的资源结果替代真实 B+C 数据。
