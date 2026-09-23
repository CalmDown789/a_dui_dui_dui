# FSRCNN RTL 综合内存审计

日期：2026-09-24  
Vivado：2022.2  
目标器件：`xc7a200tfbg484-2`（Artix-7 200T）

## 结论

原始五层 FSRCNN 不是按图像像素生成硬件，存储也没有被展开成整帧 feature map。让 Vivado 优化阶段从约 3.4 GB 涨到约 30.4 GB 的主要原因，是乘法 lane 内按运行时相位计算的宽打包向量动态 bit-select。Vivado 必须在每个 lane 上处理相位驱动的宽选择网，RTL Optimization Phase 2 因此发生异常膨胀。

根因修复仍是小范围的 MAC 相位静态索引。后续另加入 B/C 局部流水和 C 输入弹性缓冲，现有 4 个 B 覆盖均只在 `rtl/b_real_c_patch/`，冻结 B 源没有改：

1. 将 MAC lane 中两个运行时宽向量切片换为相位 `case`，每个 case arm 的索引在 elaboration 时为常量。这是解决综合内存异常的根因修复。
2. 针对 postprocess 路径拆分 Q15 舍入/饱和和 Q31 运算，并将 48-bit phase sum 与 bias/saturation 分段；这些更改增加弹性延迟，不改变算术结果和每拍吞吐。
3. C 侧在 B 前添加 2-entry FIFO，并将 ROM 请求地址寄存；FIFO ready 只由寄存占用量决定，切开 B 反压到 ROM 地址/使能的组合反馈。

上游 B 冻结副本未改，仿真和综合/实现均使用相同的闭包。2026-09-24 最新完整 B+C 运行综合峰值约 3,132 MB，route 峰值约 4,132 MB；此前同阶段达到 30,381 MB 后没有 netlist/report。当前实现完成，route status 显示 0 routing error。

200 MHz 时序仍未收敛：当前 post-route WNS=-2.208 ns、TNS=-50,037.625 ns。最差路径已从 C ROM 地址/BRAM enable 转移到 L5 phase 控制到 DSP48E1 输入：3.669 ns data delay，其中 2.979 ns（81.2%）为 route delay；组合逻辑为 LUT6+MUXF7 两级。时序未通过，不能据此生成并宣称板级 200 MHz 已验收。

## A. 最可能造成综合内存异常的代码

根因位于冻结版本 `rtl/b_real_ae29515/stream/phase_mac_pipeline.sv:37-38,59-69`：`group_out`、`group_in` 由运行时 `in_phase` 算出，再用于每个乘法 lane 的 `window_flat[...]` 和 `weight_flat[...]` 可变 part-select。L5 的打包输入总线分别为 6,400 bit 和 12,800 bit；这种选择在 200 个 lane 上重复出现。其它四层也使用相同代码模式。

隔离对照固定了 L5 的实际参数（K=5、CIN=16、COUT=4、IN_PAR=2、OUT_PAR=4、ACT_W=16）：

- 原始动态索引版本在进入综合优化后持续增长，约 3.5 分钟时系统 commit 余量从约 41 GB 降至约 25 GB；为避免影响整机而停止，没有产生 utilization report。
- 只把 `sums_q` 改为一维数组、继续保留动态索引，仍增长到约 18 GB 私有内存；说明数组维度警告不是主因。
- 保留原 `sums_q` 和 200 个乘法 lane，只将相位选择写为常量切片的 `case` 后，OOC 综合 26 秒完成，Vivado 峰值约 2.05 GB，得到 10,308 LUT、5,900 FF、200 DSP、0 BRAM。

完整工程的前后日志也吻合：旧 `_bc_real_synth_retry.log:590,623,650` 在 elaboration 峰值 2,929.938 MB、约束检查峰值 3,422.426 MB 后，RTL Optimization Phase 2 用时 8 分 42 秒并达到 30,381.059 MB；旧运行没有完成综合结果。新运行日志中 RTL Optimization Phase 2 在 51 秒完成，峰值 3,135.031 MB；全程 `synth_design` 用时 2 分 44 秒，峰值 3,175.988 MB。

`phase_mac_pipeline` 仍会产生 `Synth 8-11357`，提示 `sums_q_reg` 三维寄存器阵列有 13,056 bit。这个提示在原版和修复版均存在；修复版仍保留它并完成综合，所以它是值得留意的次要写法提示，不是本次 30 GB 膨胀的根因。

## B. 属于正常高内存，还是 RTL/netlist 异常膨胀

结论是 **RTL/netlist 优化异常膨胀**，不是这个小模型的正常综合内存需求。

证据是同一个完整设计、器件、Vivado 版本、参数和约束，在消除动态宽切片后，从 RTL Optimization Phase 2 的 30.38 GB 降至全流程 3.18 GB，并成功生成资源报告。旧运行时总系统 commit 曾到约 62.31/63.43 GB、余量约 1.12 GB；新运行期间周期采样最高约 30.44/63.43 GB，最小观测余量约 32.99 GB。系统 commit 数值是 Windows 全系统采样，Vivado 日志的 3.18 GB 是 Vivado 自身报告峰值，两者口径不同。

## C. Elaboration 实例与资源统计

### 运算并行度和综合资源

每层 MAC lane 数按 `OUT_PAR × IN_PAR × K²` 计算。DSP 列为综合后该层所有 DSP（含该层 PReLU/Q31 后处理），LUT/FF/BRAM 来自 `report/bc_real_synth/utilization_synth_hier.rpt`。

| 层 | 参数 K/Cin/Cout | IN_PAR/OUT_PAR | MAC lane | DSP48E1 | LUT | FF | BRAM36/BRAM18 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Feature L1 | 5/1/16 | 1/2 | 50 | 62 | 5,297 | 6,035 | 0/4 |
| Shrink L2 | 1/16/8 | 2/8 | 16 | 22 | 2,212 | 2,686 | 0/0 |
| Mapping L3 | 3/8/8 | 1/8 | 72 | 78 | 5,104 | 6,982 | 8/0 |
| Expand L4 | 1/8/16 | 1/16 | 16 | 28 | 3,816 | 4,525 | 0/0 |
| Deconvolution L5 | 5/16/4 | 2/4 | 200 | 204 | 13,966 | 20,264 | 28/4 |
| **整机 B+C** |  |  | **354 卷积乘法 lane** | **394** | **32,243** | **41,673** | **230/8** |

额外 40 个 DSP 是各层后处理中的 PReLU/Q31 运算。器件总容量为 740 DSP、134,600 LUT、269,200 FF、365 个 RAMB36 tile；当前综合占用分别为 53.24%、23.95%、15.48%、64.11%（BRAM18 按半个 tile 折算）。资源没有超出 ACX750 200T 器件容量。

综合原语表共有 21 类，按当前报告的 `Used` 列求和为 84,893 个映射原语实例。旧的完整 B+C 综合在生成 netlist 前被中断，所以不存在可比较的“修复前完整 cell count”或 LUT/FF/DSP/BRAM 报告。历史 C+stub 报告的 3,626–3,723 LUT、8,048–8,190 FF、192 RAMB36、0 DSP 不是完整 B 网络，不能充当修复前完整值。

### 实际层次数量

修复后的 netlist 自检结果：`b_core_real=1`、`b_core_stub=0`、`fsrcnn_network_mem_top=1`、`fsrcnn_stream_layer=5`、`pixel_shuffle2x_row_banks=1`、`elastic_fifo=7`。层次报告中 7 个 FIFO 是 4 个层间 FIFO 加 3 个 K>1 窗口前端 FIFO。每层各有一个 `mac_issue_stage`、`phase_mac_pipeline`、`phase_accumulator` 和 `vector_postprocess_shared`；只有 L1/L3/L5 建立窗口前端/line buffer。

### RAM、line buffer 和 ROM

- 输入 ROM 是 524,288×8 bit，综合映射为 128 RAMB36；它使用 `$readmemh` 和同步读。
- C 侧 ping-pong 条带 buffer 合计映射 64 RAMB36，条带存储使用同步读写和 `ram_style="block"`。
- B 网络实际使用 38 RAMB36 + 8 RAMB18：L1 窗口为 4 RAMB18，L3 为 8 RAMB36，L5 为 28 RAMB36 + 4 RAMB18，pixel shuffle 两个 bank 共 2 RAMB36。
- B 的窗口存储深度按图像宽度配置：L1 约 4×960×8 bit，L3 约 2×960×128 bit，L5 约 4×960×256 bit；没有按 960×540 保存中间 feature map。大窗口 RAM 映射到了 BRAM；32 深度的浅 FIFO 使用 LUTRAM/SRL 是小型队列的合理映射，当前综合 LUTRAM 为 5,717。
- B 权重/偏置/量化参数是 19 个 depth=1 的打包 `$readmemh` 数组，不是按像素展开的存储器。

## D. 当前是否是流式、资源有界的 CNN accelerator

是流式数据通路，不是按图像面积实例化硬件。`fsrcnn_network_core.sv:52-103` 明确例化 5 个卷积层、4 个层间 FIFO 和 1 个 pixel-shuffle row-bank；`IMG_W/IMG_H` 用于行列计数和 line buffer 地址/深度。generate 循环边界是通道、核尺寸、固定并行 lane 和加法树节点，不是图像宽/高/像素个数。

并行化是固定且可统计的：总计 354 个卷积乘法 lane，DSP 后处理后实际 394 DSP。phase scheduler 在通道组之间分时；卷积核项和配置的输入/输出并行 lane 则空间并行。因此它不是“单个 MAC 复用所有运算”，但也不是把所有层、所有输入通道和整帧像素完全展开。该并行度在 ACX750 200T 的 740 DSP 容量内。

最后的转置卷积被拆为四个输出子像素相位，每相位以 5×5 核表示，并由 200 个固定 MAC lane 处理；随后 `pixel_shuffle2x_row_banks` 用两个按行宽度深度的 BRAM bank 交错输出。没有每个输出像素一份计算硬件或整帧输出相位数组。

## E. 最小修改

4 个局部 B 覆盖文件，冻结上游文件及 SHA-256 不变：

- `rtl/b_real_c_patch/phase_mac_pipeline.sv`：只将两个相位动态 part-select 换为 8 个静态索引 case arm。仍按原来的 `in_phase/IN_GROUPS` 和 `in_phase%IN_GROUPS` 语义选通道组，乘法宽度、valid/ready、累加树、pipeline、DSP 属性、数组形状和并行度不变。
- `rtl/b_real_c_patch/vector_postprocess_shared.sv`：把已选 slot/channel 的 accumulator、PReLU 系数和 Q31 系数寄存一拍后再送入 PReLU DSP，并把 slot/group/valid 标签也延迟一拍。算术不变，整向量发射间隔不变；新增流水寄存器使综合 FF 比 MAC-only 补丁版增加 389。
- `rtl/b_real_c_patch/prelu_requantize.sv`：将 Q15 和 Q31 运算的加法/舍入/饱和分成弹性级。
- `rtl/b_real_c_patch/phase_accumulator.sv`：寄存完成的 48-bit phase sum，再加 bias 并饱和到 INT32。

C 侧另外在 `rtl/c_core.v` 和 `rtl/input_stream.v` 实现两拍 FIFO 与 ROM 请求地址寄存，仿真、综合同用这两份 RTL。

`scripts/synth_bc_real.tcl` 和 `scripts/run_sim.tcl` 都将闭包内相应文件替换为这两个 C 侧补丁，保证仿真、综合和实现使用同一 RTL。没有减少模型参数，没有通过增加虚拟内存绕过问题，也没有进行全网重构。

## F. 修改后综合/仿真验证及前后比较

| 指标 | 修改前完整 B+C | 修改后完整 B+C |
|---|---:|---:|
| Vivado 峰值内存 | RTL Optimization Phase 2 达到约 30,381 MB，之后未完成 | 综合峰值约 3,132 MB；place/route 峰值约 4,132 MB |
| RTL Optimization Phase 2 | 8 分 42 秒后仍未完成，峰值约 30,381 MB | 约 1 分钟内完成，峰值约 3,132 MB |
| 系统 commit | 旧运行约 62.31/63.43 GB，余量约 1.12 GB | 整个复验过程采样峰值约 31.28/63.43 GB，观测余量至少约 32.15 GB |
| 综合时间 | 未完成；Phase 2 已耗时 8 分 42 秒 | `synth_design` 约 3 分 08 秒；`route_design` CPU 约 4 分 29 秒 |
| LUT/FF/DSP/BRAM | 无完整 netlist，无法测量 | 综合 32,243 / 41,673 / 394 / 230 RAMB36 + 8 RAMB18；布线后 32,152 / 41,932 / 394 / 230 + 8 |
| cell count | 无完整 netlist，无法测量 | 综合原语表 84,893 个实例（按 `Used` 列求和） |
| 真实网络实例自检 | 未到报告阶段 | real=1、stub=0、五层=5、FIFO=7、shuffle=1 |

修改后的仿真使用 `xelab -O0`：

- `tb_b_real_backpressure`：随机回压 20,736/20,736 字节匹配，长停顿和输入空闲场景通过，`hold_viol=0`。
- `tb_b_real_bit_exact`：96×54 输入、192×108 输出的 4 个 Golden 用例全部逐字节匹配，4/4 PASS。

综合有 0 critical warning、0 error；`sums_q` 的 3D-array warning 保留。最新 post-route WNS=-2.208 ns、TNS=-50,037.625 ns；仍未满足 200 MHz。当前最差路径从 L5 `out_phase` 寄存器到 DSP 输入，data delay 3.669 ns、route 2.979 ns、2 级逻辑。曾测试 MAC 前增加相位选择操作数寄存；Vivado 将其吸收进 DSP，route WNS=-2.370 ns，反而比 -2.208 ns 差，已回退。接下来应分析 L5 phase 控制的高扇出/布局；不要盲目继续堆流水或声称达到 200 MHz。

本机 XSim 2022.2 的完整回归组 9/9 通过。全帧为 518,400 输入、2,073,600 输出，逐字节匹配 A 整数 Golden，X=0、边界计数正确、保持规则违例 0；仿真约 36 分 28 秒。报告保存在 `report/sim_result_full_20260924.txt` 与 `report/bc_real_synth/`。

随本次状态同步保留的报告包括：`report/bc_real_synth/bc_real_synth_result.txt`、综合与布线 utilization（含层级）报告、时钟和 route status 报告，以及 L5 OOC 对照 CSV/利用率报告。完整的原始 timing、RAM mapping 和 DRC 文本报告保留在 C 本机的 `report/bc_real_synth/` 中；关键 WNS、关键路径和 RAM 估算已摘录在本文，可用 `scripts/synth_bc_real.tcl -tclargs impl` 重新生成。修复前完整运行快照保存在 `report/bc_real_synth/synth_only_commit_limit_stop.txt`。
