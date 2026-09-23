# 真实 B 五层 RTL 接入 C 侧：验收报告（A～Q）

> **最新状态（2026-09-24，本机）**：XSim 2022.2 下，当前冻结 RTL/ROM/Golden 的
> `xelab -O0` 回归 9/9 通过；96×54 四组及 960×540→1920×1080 全帧均逐字节匹配。
> 真实 B+C 综合和 route 已完成：394 DSP、32,243 综合 LUT、41,673 综合 FF，综合/route
> 峰值约 3.13/4.13 GB。post-route WNS=-2.208 ns，200 MHz 未闭合；尚无 bitstream 或板测，
> 因此**功能仿真已通过，器件总验收仍待完成**。下文旧失配与“未运行”条目保留作历史诊断，
> 不代表当前 RTL。全套当前日志摘要见 `report/sim_result_full_20260924.txt`；
> 复现命令及仿真工具版本边界见 `docs/B_REAL_XSIM_REPRODUCIBILITY.md`。

## A. 验收对象与版本

仓库 `CalmDown789/a_dui_dui_dui` 的 C 侧分支 `c-side-latest`，接管基点
`4827f19619aa96a6601aebf53cf121a3063141f3`。真实 B RTL 来自
`member-b-five-layer-stream` @ `ae29515945fbb6e9566626d7f2d28660ac94d5c4`。
本轮工作树的未提交状态以最终 Git 记录为准，不能把基点 SHA 当成新增文件的提交。
接管时远端 B 分支位于 `4c80d1e8`；相对 `ae29515` 的两个新提交只改文档和
交付脚本，未修改本报告使用的 RTL。

## B. 正式编译路径

`rtl/b_core_if.v` 的 `C_USE_B_REAL` 分支实例化 `b_core_real`，并显式传入
`IMG_W/IMG_H/STRIPE_H`。`scripts/run_sim.tcl` 的真实 B 组使用 11 个冻结的
`ae29515` 上游文件及 4 个本地补丁覆盖；旧 `rtl/b_real/rtl` 是原语回归组。
综合脚本 `scripts/synth_bc_real.tcl` 使用同一闭包并通过
`synth_design -verilog_define C_USE_B_REAL` 选择正式路径。

## C. 来源与文件完整性

`rtl/b_real_ae29515/PROVENANCE.md` 和 `_b_vendor_manifest.json` 记录每个 RTL
文件的 SHA-256。依赖图从 `b_core_real` 出发有 15 个可达模块、15 个必需文件，
未解析模块为 0。19 个 `*_packed.mem` 由 A 量化资产生成，位于
`rom/member_a_d16_s8_m1_c16/`。接管后按 `_b_vendor_manifest.json` 重新计算，
RTL **15/15**、ROM 目录条目 **21/21** 哈希一致（后者含 19 个 `.mem` 与
2 个说明/清单文件）。

## D. A 侧基准

96×54 的 `impulse/ramp/random/zero` 四组数据来自 `ref/a_test_vectors/`；
文件哈希与各组 `manifest.json` 对账。全尺寸 960×540 输入、1920×1080 输出
来自 `ref/a_full_integer_golden/`，输出应有 2,073,600 字节。
这份全尺寸资产来自 A 的 `98c82f3`，后来从 `main` 撤回；
该提交的 `docs/成员A全尺寸整数Golden确认.md` **已有 A 的书面确认**，
其列出的输出哈希与本地资产一致。正式重新发布的提交/路径仍待 A 明确。
详见
`docs/ACCEPTANCE_DATA_DEPENDENCY.md`。浮点/QDQ 产物不是本报告的逐字节基准。

## E. 工具链与适用边界

本机冻结工具链为 Vivado/XSim 2022.2。B 的既有 PASS 记录来自 XSim 2025.2。
本报告的当前仿真判定适用于 **2022.2 + `xelab -O0`**；需 B 在 2025.2 上按同一
输入、ROM、TB 复跑以确定版本边界。
另有测试台调度风险：B 原始 TB 在 `posedge` 用阻塞赋值递增 `sent`，
而 DUT 同沿采样 `input_mem[sent]`。这可能形成仿真事件排序竞争；
故 B 原始 TB 的 FAIL 作为交叉佐证，判定主要依据是 C 侧在 `negedge`
稳定驱动输入的四组测试。逐层探针将再用非阻塞索引推进隔离该风险。

## F. 时钟与目标器件

`constr/c_top.xdc` 对板载 `sys_clk`（W19）约束 20.000 ns，即 50 MHz。
`c_top`/`c_synth_top` 使用 `MMCME2_BASE` 的 24/1/6 参数生成 200 MHz
设计时钟。目标器件是 `xc7a200tfbg484-2`。这是约束与 RTL 配置；
是否达到 200 MHz 应以后续实现时序报告判定。

## G. 基础协议冒烟

`tb_b_real_smoke.v` 的 6×5 两帧测试 PASS：真实 B 能详细化、输出协议结束，
并覆盖有限停等与保持规则。该测试不验证 FSRCNN 的逐字节数值。

## H. 背压与握手

> 本节失配/超时数字是修复前诊断记录；当前长背压正式回归已通过，见完整回归摘要。

B 原始 TB 在带停等和 `TB_ALWAYS_READY` 两种模式下都从输出 index 2 失配。
由此可排除背压是该最早失配的必要条件。C 侧独立的
`tb_b_real_backpressure.v` 的独立重跑中，随机背压场景 T-A 输出
20,736/20,736 字节、保持违规 0，但失配 19,157 字节；
300 拍连续停等场景 T-B 在 4,000,000 拍硬超时，故 T-C 未执行。
原始记录为 `report/sim_result_tb_b_real_backpressure.txt` 和本机
`_sim/tb_b_real_backpressure/xsim.log`。首次运行曾因测试脚本漏 stage
`tv_random_*.mem` 出现 X，此次修正后重跑无此类加载警告。
T-B 超出 B v1.1 的合同级保证 `N=0`，只能作为诊断压力测试；
正式数值 FAIL 也在无背压情况下成立。

## I. 四组小尺寸逐字节验收

修复前的 FAIL 数字已被当前 `xelab -O0` 结果取代：

正式 C 路径 `tb_b_real_bit_exact.v`，每组期望 20,736 字节：

| 用例 | 匹配字节 | 判定 |
|---|---:|---|
| impulse | 20,736 / 20,736 | PASS |
| ramp | 20,736 / 20,736 | PASS |
| random | 20,736 / 20,736 | PASS |
| zero | 20,736 / 20,736 | PASS |

当前四组每组 fed=5,184、输出 20,736 字节、mismatch=0、stripe_last=2、
frame_last=1、done=1；4/4 PASS，无 X。修复前失配详情保留在
`docs/B_REAL_BITEXXACT_MISMATCH_HANDOFF.md`。

## J. B 原始流程独立复现

> 本节记录的是修复前的原始 B 流程诊断结果；不能据此描述当前 C 接入路径的判定。

不经过 `b_core_if`，用 B 未改动的 TB、B 的 Golden 生成脚本和 B 的 RTL，
6×5、96×54、96×96、96×128 的已跑组合均在输出 index 2 首次失败；
6×5 与 96×54 的有背压/无背压模式结果一致。复现矩阵与命令见
`docs/B_REAL_BITEXXACT_MISMATCH_HANDOFF.md`。该原始 TB 的同沿索引竞争
风险见 §E，因此不把这组复现单独作为 RTL 缺陷的充分证明。

## K. 整帧逐字节验收

`tb_b_real_full.v` 使用 A 整数 Golden，目标 2,073,600 输出字节。
2026-09-24 当前 RTL 完整复跑：输入 518,400/518,400；输出 2,073,600/2,073,600；
**匹配 2,073,600 字节，失配 0，PASS**。X 字节 0；`stripe_last=17/17`、
`frame_last=1/1`、`done=1`，保持规则违反 0，共 4,699,401 个仿真周期，XSim elapsed
36:28。原始日志为 `_sim/tb_b_real_full/xsim.log`；摘要及 Golden 哈希索引见
`report/sim_result_full_20260924.txt` 与 `report/b_real_full_summary.json`。

## L. 常数输入定位实验

> 本节的数值失配与首分歧定位属于修复前诊断快照；当前正式路径结果见 §I、§K。

96×54 常数输入 `0/64/128/192/255` 的探针显示：输入 ≥64 时，DUT
与参考的匹配均为 `0/20,736`，输出值集合与参考不相交；x 方向有周期 2
调制。ROM 内部寄存器 8 个抽样值与 Python 解码及 A 量化 bin 一致。
这把排查重点指向 B 的数值通路、PixelShuffle/row-bank 相位与中间缩位；
6×5 的独立逐层探针进一步证实：第一层 **INT32 MAC 对 A 原始值
0/480 失配**，但该层 PReLU/重定量化后的 INT16 输出 **186/480 失配**；
第一处是 token 0 / channel 1（DUT `fa6b`，A `0f7b`）。后续 L2/L3/L4/L5
也均失配。故最早已证实的分歧位于第一层 MAC 之后的后处理路径；
尚不能据此单独判定是标量计算、共享调度还是参数对齐问题。

## M. 真实 B+C 综合

`scripts/synth_bc_real.tcl` 已备好目标器件取证。报告必须核对
`b_core_real >= 1`、`b_core_stub = 0`、`fsrcnn_network_mem_top >= 1`、
`fsrcnn_stream_layer >= 5` 的自校验，否则资源数字作废。
2026-09-24 真实 B+C 综合已完成，脚本自检确认 `b_core_real=1`、`b_core_stub=0`、
`fsrcnn_network_mem_top=1`、`fsrcnn_stream_layer=5`、7 个 FIFO。实测综合资源：
230 RAMB36、8 RAMB18、394 DSP48E1、32,243 LUT、41,673 FF、5,717 LUTRAM；
峰值内存约 3.13 GB。完整数据在 `report/bc_real_synth/`。此前约 30.4 GB 的异常综合
记录属于修复前 RTL，根因分析见 `docs/RTL_SYNTHESIS_MEMORY_AUDIT.md`。

## N. 实现与时序

完整 implementation/route 已完成，峰值内存约 4.13 GB，DRC 0 errors。post-route
WNS=-2.208 ns、TNS=-50,037.625 ns、WHS=+0.036 ns；200 MHz 时序**未收敛**，不能宣称
达到 200 MHz 或 30 fps。最差路径是 L5 phase 选择寄存器至 DSP48E1 输入，路径延迟
3.669 ns，其中 2.979 ns 为布线延迟。见 `report/bc_real_synth/timing_summary_postroute.rpt`。

## O. 分层资源与预算

旧的 `192 RAMB36` 属于 C+stub；B v1.1 的 `271` 与 C 侧的 `276/278`
属于预算/外推，均不能充当真实 B+C 资源实测。本轮以
`utilization_synth_hier.rpt` 和 `utilization_postroute_hier.rpt`（若 route 完成）
核对层级资源，并分别报告 RAMB36、RAMB18、DSP48E1、LUT、FF。

## P. 交付范围与开放项

UART 管脚、真实 start 触发、A 对全尺寸 Golden 的正式重新发布位置、B 在 2025.2
的同条件复跑仍开放。本文没有板级
图像质量、PSNR、真实吞吐或 bitstream 验收数据。

## Q. 最终判定与下一步

**功能仿真 PASS；器件验收未完成。** 当前小尺寸与全尺寸 Golden 对拍均逐字节通过，
真实 B+C 综合和 route 已运行。剩余阻塞项是 post-route 200 MHz 时序负裕量、未生成 bitstream、
未在 ACX750 上采集 HDMI/UART 图像与吞吐数据，以及 UART 管脚和真实 start 触发方案待确认。
因此当前结果足以进入时序优化与受控上板准备，但不能作为目标时钟性能或板级图像验收通过。
状态快照及本机/GitHub 后续任务划分见 `docs/CURRENT_PROJECT_STATUS.md`。

---

复现脚本：`scripts/run_sim.tcl`、`scripts/synth_bc_real.tcl`；
直接证据：`report/sim_result.txt`、`report/b_real_full_summary.json`、
`report/b_real_layer_probe.txt`、
`docs/B_REAL_BITEXXACT_MISMATCH_HANDOFF.md`。日志目录 `_sim/` 可再生，
不作为已提交的不可变证据。
上游对照：[A 的确认提交](https://github.com/CalmDown789/a_dui_dui_dui/commit/98c82f394bdfba85bc2959bede9760edc4d6862f)、
[B 的 2025.2 验证记录](https://github.com/CalmDown789/a_dui_dui_dui/blob/4c80d1e8dcde6e0c693206aed361ca01badc774e/acx750_rtl/docs/verification_status.md)。
