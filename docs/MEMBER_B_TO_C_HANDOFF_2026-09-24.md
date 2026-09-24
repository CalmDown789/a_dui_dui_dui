# 成员 B → 成员 C：真实五层 B+C 实验与板级交接

日期：2026-09-24。请从 `member-b-2025-2-bc-trial` 分支阅读本文件。这是基于
`c-side-latest@6b87af3` 的**独立实验叠层**，不是对 C 正式 RTL 的直接替换。
成员 B 负责网络 RTL、位精确验证和 150 MHz 时序优化；成员 C 负责板级工程、
引脚和实际输入输出通路。任何实验补丁进入 C 正式工程前，请按下文逐项审查。

## 已交付并通过的部分

1. **真实网络与数据。** `C_USE_B_REAL` 下，自检为 `b_core_real=1`、
   `b_core_stub=0`、五个 `fsrcnn_stream_layer`、七个 `elastic_fifo` 和一个
   PixelShuffle。A 的冻结整数 Golden 为 `member-a@98c82f3`；输入图 ROM
   已拆为 16 个真实 bank，跟踪于 `member_b_evidence/real_banks/`，并经过
   SHA-256/重组校验及 137 次同步读检查。`experiments/l5_splitmem_20260924/fixtures/`
   中的同名 bank 是**合成 marker**，不能用于上板图像验证。
2. **位精确仿真。** 36 位与 48 位都通过三种背压场景和四组 96×54 A Golden
   对拍。36 位完整 960×540 单帧仿真得到 518,400 输入、2,073,600 输出，
   mismatch/X/保持违例均为 0，`stripe_last=17`、`frame_last=1`、`done=1`，
   共 4,699,406 周期。36 位是数学上足够的累加宽度，减少资源，不改变
   输出量化精度。完整原始证据见
   [`MEMBER_B_2025_2_TRIAL_STATUS_2026-09-24.md`](MEMBER_B_2025_2_TRIAL_STATUS_2026-09-24.md)。
3. **目标器件布线。** 本机 Vivado 2025.2、`xc7a200tfbg484-2`、真实 A ROM、
   36 位累加器、C 条带 RAM 的 `ram_decomp="power"` 属性，布线后结果如下。

   | MMCM 输出 | WNS/TNS | 资源 | 结论 |
   | --- | --- | --- | --- |
   | 200 MHz | −0.719/−2842.755 ns | RAMB36/18 226/8，DSP 394 | 时序失败 |
   | 150 MHz | +0.039/0 ns | RAMB36/18 226/8，DSP 394 | 通过，但仅 39 ps 裕量 |
   | 120 MHz | +0.127/0 ns | RAMB36/18 226/8，DSP 394 | 通过，裕量仍小 |
   | 100 MHz | +0.403/0 ns | RAMB36/18 226/8，DSP 394 | 建议先用于板级联调 |

   这些是**完整布线后的静态时序**，不是 bitstream 或板上频率。150 MHz
   的最差路径在 C 输入 ROM 地址到 BRAM，另有第五层宽 FIFO 控制/地址长线。
   100 MHz 是排除板级问题的联调起点，150 MHz 是后续性能目标。

## C 可以直接查看的源码与复现入口

- `experiments/l5_splitmem_20260924/rtl/c/input_rom.v`：真实 bank16 同步读。
- `experiments/l5_splitmem_20260924/rtl/c/input_stream.v`：请求地址寄存器与
  ready/valid 保持；`in_valid && !in_ready` 时地址、坐标和数据不得前进。
- `experiments/l5_splitmem_20260924/rtl/c_ramdecomp_member_b/stripe_buffer.v`：
  相比 C 原件仅为 `mem` 添加 BRAM 分解综合属性。原映射在本机触发
  `REQP-1962`，该属性使设计能完成布线。
- `experiments/l5_splitmem_20260924/rtl/b/phase_accumulator_36.sv`：36 位候选。
  对应的 `elastic_fifo.sv`、`mac_issue_stage.sv` 和其它补丁由实现 Tcl 精确选取；
  **不要只复制累加器一个文件就声称复现了本报告。**
- `experiments/l5_splitmem_20260924/rtl/c_100_member_b/` 与
  `rtl/c_150_member_b/`：对应时钟的 `c_top`/`c_synth_top`。`c_synth_top`
  明确设 `ROM_INIT_EN=1`，`rtl/c_top.v` 的默认值为 0；上板前必须核对
  bitstream 使用的顶层、真实 bank 和初始化参数。
- `experiments/l5_splitmem_20260924/synth_bc_realrom_100_member_b.tcl`
  与 `synth_bc_realrom_150_member_b.tcl`：同条件实现脚本，使用参数
  `-tclargs impl acc36 ascii ramdecomp`。Vivado 工作路径请用纯 ASCII；
  本机通过临时 `V:` 映射运行。报告原件在 `member_b_evidence/route_reports/`。
- `scripts/run_sim_l5_trial_acc36_ramdecomp150_member_b.tcl`：150 MHz
  精确叠层的反压与四组 Golden 短回归。A 的完整 Golden `.bin/.mem`
  因体积/归属未跟踪在本分支；可从 A 冻结交付 `member-a@98c82f3`
  取得，使用 `scripts/prepare_ref_data.py` 校验后 staging。

## 请 C 按此顺序推进

1. **先做 100 MHz 板级冒烟。** 在 C 自己的工程中逐项审查上述实验补丁，
   确认目标板实际器件、50 MHz 时钟、MMCM 输出、复位、真实 ROM bank 和
   顶层参数；先用 LED/ILA 验证 `start`、`busy`、`done`、错误标志和像素握手。
   本实验分支没有 bitstream，也没有替 C 确认实体板。
2. **补齐 XDC 与回读。** `constr/c_top.xdc` 的 UART TX 管脚尚未确认，
   当前实现报告也有未指定 I/O 标准警告。请根据板卡原理图/IO Planner
   核对引脚与电平后再生成板级 bitstream；记录实际上板频率、工具版本、
   XDC、bitstream 对应 commit、输出字节数、`frame_last/done`、协议错误和
   连续两帧的行为。不要用 marker ROM 或零初始化 ROM 做真实图像签核。
3. **将板上输出与 A Golden 对比。** A 权威输出为
   `output_1920x1080_y_u8.bin`，2,073,600 字节，SHA-256
   `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`。
   如不能一次回读整帧，可先对固定坐标/条带做逐字节对照，并明确记录
   采样范围；不能把少量采样称作整帧 bit-exact。
4. **测实际吞吐，再切 150 MHz。** 921,600 baud 的 8N1 UART 回读
   理论上发送完整 2,073,600 字节至少约 22.5 秒，还未计协议开销；
   因此 UART 适合功能取证，不能据此声称 30 fps。请分别记录计算段
   周期、输入/输出等待和连续帧间隔。100 MHz 跑通后再上 150 MHz
   候选，并用 C 完整板级 XDC 重新实现、复测。B 推荐的 150 MHz
   实现脚本见下节；该脚本不改变网络 RTL。

## 150 MHz 优化实验状态

- B 单独试过第五层宽 FIFO 的分片写指针：三种反压、四组 96×54 Golden
  全部通过，但同条件布线后 WNS 为 **+0.027 ns**，低于基线的 +0.039 ns；
  LUT/FF 从 28,041/48,510 增至 28,384/48,702。该候选**不推荐 C 集成**。
  源码与复现脚本在 `experiments/l5_timing_opt_20260924/`，关键仿真及
  布线报告在 `member_b_evidence/timing_opt_wrptrlocal150/`。
- 针对高扇出网络的第二组实验在综合网络选择阶段停止，**没有布线结果**；
  不把它当作时序改善。
- **当前推荐：原基线 RTL + NetDelay 实现策略。** 同一真实 ROM、目标器件、
  150 MHz 时钟和 XDC 下，布线后 WNS/TNS 从 +0.039/0 提升到
  **+0.132/0 ns**（增加 93 ps），LUT/FF 为 28,078/48,498，
  RAMB36/18 为 226/8，DSP 为 394，路由错误 0。运行
  `experiments/l5_timing_opt_20260924/synth_bc_realrom_150_netdelay_member_b.tcl`
  并传入 `-tclargs impl acc36 ascii ramdecomp`；原始报告在
  `member_b_evidence/timing_opt_netdelay150/`。该脚本只调整布局、物理优化
  和布线指令，沿用本文件上文的已位精确验证 RTL。C 可在 100 MHz 板级
  联调成功后，以实际板级 XDC 复现、评估 150 MHz；不能直接把这里的
  +0.132 ns 视为板级最终裕量。
- 其它完成布线对照：FIFO 2 的幂深度简化指针 +0.038 ns；局部写指针
  配合 NetDelay +0.138 ns，但增加 262 LUT、176 FF，较推荐方案只多
  6 ps；定向 L5 相位 fanout 与 WL 策略 +0.128 ns。完整对照与原始报告
  索引见 [`MEMBER_B_150MHZ_TIMING_OPT_2026-09-24.md`](MEMBER_B_150MHZ_TIMING_OPT_2026-09-24.md)。

## 交付边界与沟通点

- 150 MHz 原基线只有 39 ps 余量；推荐实现策略在本实验条件下达到
  132 ps，仍未达到约 400 ps 的期望裕量。当前最差路径是 L5 宽 FIFO
  写指针到分布式 RAM 写地址，直连 fanout 1,056，数据路径布线占约 94%。
  **未验证或退化的 RTL 候选不得合入 C 板级基线**。
- 单帧 4,699,406 周期按 150/100 MHz 分别折算约 31.92/21.28 fps，
  只用于计算段预算；不等于实际连续视频帧率。
- 请 C 回传板卡型号/原理图依据、UART 管脚、完整 XDC、首个 100 MHz
  bitstream 的自检与板测日志，以及真实输出采集方式。B 收到后可针对
  同一接口和约束继续处理 150 MHz 时序，不会改 C 正在联调的正式分支。
