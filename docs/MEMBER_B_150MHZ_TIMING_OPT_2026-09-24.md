# 成员 B：150 MHz 时序优化试验记录

日期：2026-09-24。目标为 Vivado 2025.2、`xc7a200tfbg484-2`、真实 A 输入
ROM bank16、B 五层网络、C 外壳、36 位跨通道累加和 C 条带 RAM
`ram_decomp="power"` 的同条件实现。时钟由 50 MHz 板载输入经 MMCM 产生
150 MHz。表中数据均为**完成布线后的静态时序**，不是板级测试、bitstream
签核或持续帧率。

## 同条件对照

| 方案 | 150 MHz WNS/TNS | LUT | FF | RAMB36/18 | DSP48E1 | 判断 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 原基线 RTL + 默认实现 | +0.039/0 ns | 28,041 | 48,510 | 226/8 | 394 | 功能已验证，裕量小 |
| FIFO 写指针按位片局部复制 + 默认实现 | +0.027/0 ns | 28,384 | 48,702 | 226/8 | 394 | 时序退化 |
| FIFO 2 的幂深度简化指针回绕 + 默认实现 | +0.038/0 ns | 27,947 | 48,594 | 226/8 | 394 | 时序无实质收益 |
| **原基线 RTL + NetDelay 实现策略** | **+0.132/0 ns** | **28,078** | **48,498** | **226/8** | **394** | 当前推荐候选，较基线增加 93 ps |
| 局部复制写指针 + NetDelay 实现策略 | +0.138/0 ns | 28,340 | 48,674 | 226/8 | 394 | 仅多 6 ps，资源增加，不推荐集成 |
| 原基线 RTL + L5 相位网络 fanout 约束 + WLDrivenBlockPlacement/AggressiveFanoutOpt/Explore | +0.128/0 ns | 28,021 | 48,498 | 226/8 | 394 | 比 NetDelay 少 4 ps，不推荐替换 |

针对综合后 `out_window` 网络设置 `MAX_FANOUT` 的一组试验在综合阶段停止：
其直接 fanout 最高仅 2，没有命中受限对象，因此**没有布线结果**，不能计入
改善。上表的 FIFO RTL 试验均通过三种背压场景与四组 96×54 A Golden 短
回归；NetDelay 使用已通过完整 960×540 位精确仿真的**原基线 RTL**，
只改变实现指令。最后一组 WL/fanout 试验也使用原基线 RTL，综合后将
48 条 L5 相位寄存器输出网络的 `MAX_FANOUT` 设为 48，并调整三个实现指令；
路由错误为 0，但最差路径仍落在 L5 FIFO 写指针到分布式 RAM 写地址，
没有改善目标瓶颈。

## NetDelay 候选的复现与限制

- 运行脚本：`experiments/l5_timing_opt_20260924/synth_bc_realrom_150_netdelay_member_b.tcl`，
  参数 `-tclargs impl acc36 ascii ramdecomp`。Vivado 工作目录必须为纯 ASCII；
  本机以临时 `V:` 映射运行。
- 与原基线实现的差别仅是 `place_design -directive ExtraNetDelay_high`、
  `phys_opt_design -directive AggressiveExplore` 和
  `route_design -directive NoTimingRelaxation`。完整结果与时序、资源、时钟、
  路由状态原件在 `member_b_evidence/timing_opt_netdelay150/`；路由错误为 0。
- 当前最差路径是 L5 宽 FIFO 写指针寄存器到分布式 RAM 写地址：直连
  fanout 1,056，数据路径 6.386 ns，其中布线 6.007 ns（约 94%）。这说明
  下一步主要是**地址分发的物理局部性**，而不是再减少一个组合逻辑级。
- 150 MHz WNS +0.132 ns 仍低于约 +0.4 ns 的目标。布局布线结果会随
  XDC、种子、层次、工具设置变化；C 必须使用实际板卡完整 XDC 重新实现。
  板级验证应先按交接文件从 100 MHz 开始，再验证 150 MHz。
- 其余完成布线的方案保留精简原始证据：
  `member_b_evidence/timing_opt_wrptrlocal150/`、
  `timing_opt_pow2ptr150/`、`timing_opt_wrptrlocal_netdelay150/` 和
  `timing_opt_wlfanout150/`。每组均包含结果摘要、时序、资源、时钟与
  路由状态报告。对应 Tcl 和 RTL 在 `experiments/l5_timing_opt_20260924/`。

## 结果边界

静态 WNS 是该实验叠层和该约束下的实现结果；它不能证明上板 IO、真实
UART/视频通路或持续 30 fps。单帧 4,699,406 周期只提供计算段估算。
不应把失败的写指针 RTL 候选混入 C 的正式分支。各试验所用源文件和 Tcl
单独保留，C 可依据脚本检查具体覆盖关系。
