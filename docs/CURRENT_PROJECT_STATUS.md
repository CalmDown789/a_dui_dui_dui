# C 端与项目总体状态交接

**快照时间：2026-09-23（北京时间）**

**代码/证据基线：2026-09-23 当前 C 侧状态同步快照**
**用途：为另一位项目成员撰写阶段性总结提供事实材料；本文不是最终验收签署。**

## C 端当前状态

### 已完成并有证据

- C 的 `C_USE_B_REAL` 路径使用 B 五层 RTL 快照 `ae29515` 和两个 C 侧局部覆盖；19 个参数 ROM 已入库并有来源/哈希清单。冻结的上游 B 文件没有修改。
- 针对综合内存异常，`phase_mac_pipeline` 将运行时相位宽切片改成常量索引 case。针对路由关键路径，`vector_postprocess_shared` 在 PReLU DSP 前寄存已选择操作数并同步延长元数据一拍。
- 本机 Vivado/XSim 2022.2 用 `xelab -O0` 跑最新 RTL：`tb_b_real_backpressure` 3/3 帧逐字节匹配、hold violation 为 0；`tb_b_real_bit_exact` 的 96×54 四个 Golden 用例 4/4 通过。此前 960×540 全帧在上一版 RTL 下通过，加入 postprocess 隔离拍后尚未复跑。
- 最新完整 B+C 综合和 place/route 已完成：综合资源为 32,339 LUT、37,061 FF、394 DSP、230 RAMB36 + 8 RAMB18；综合峰值 3,165.832 MB，实现峰值 4,239.918 MB。
- 200 MHz 时序尚未收敛：布线 WNS=-3.348 ns、TNS=-89,415.367 ns。当前最差路径为 PReLU Q15 舍入/饱和组合逻辑到 Q31 DSP；0 个 routing error。
- B 提供的 XSim 2025.2 PASS 是 B 侧记录；本机只有 2022.2，尚未在本机复跑 2025.2。

### 当前结论边界

- 早前 XSim 2022.2 默认优化对拍异常仍应作为工具对照记录；最新回归只证明所列小图/背压场景，不证明 960×540 最新 RTL 全帧或板上图像。
- 综合与 route 已完成，但 WNS 为负；没有生成本轮 bitstream，尚未证明板级图像或 200 MHz 实时性能。
- 早期默认优化日志中的 L1 后处理差异属于该默认配置下的观测；`-O0` 分层探针全通过后，不能再据此单独断言 B 的数值 RTL 有缺陷。

## 项目总体状态

| 验收项 | 当前状态 | 可引用证据/限制 |
|---|---|---|
| C-B 接口与仿真协议 | `-O0` smoke、背压回归通过 | `docs/B_REAL_XSIM_REPRODUCIBILITY.md` |
| 真实 B 数值对拍 | 当前 96×54 回归与三帧背压测试通过 | 最新 postprocess 隔离拍版本的全尺寸回归待本机复跑 |
| B+C 综合资源 | 已完成真实五层综合 | 32,339 LUT、37,061 FF、394 DSP、230 RAMB36 + 8 RAMB18 |
| 布局布线/实现时序 | 已布线，时序未收敛 | WNS=-3.348 ns；route error=0；200 MHz 不能签收 |
| bitstream/上板/HDMI 图像 | 未完成 | 没有本轮 bitstream、板上运行记录或验收图像 |
| 系统级最终验收 | 未完成 | 不能声称已达 200 MHz、30 fps 或板级图像正确 |

### 综合内存根因与结果

最初异常来自 `phase_mac_pipeline` 中运行时相位驱动的宽 packed-bus part-select：旧版本完整工程在 RTL Optimization Phase 2 达到 30,381 MB 后没有生成 netlist。常量 case 局部补丁后，同一目标器件和 Vivado 版本在 53 秒完成该阶段；综合峰值约 3.17 GB，实现峰值约 4.24 GB。本机提交内存复验过程最高采样约 31.28/63.43 GB，没有再逼近上限。

## 仍开放的项目事项

- **C 本机**：将 PReLU Q15 rounding/saturation 拆分为更短组合级，重新跑 bit-exact/backpressure、综合和 place/route；时序达标后再生成 bitstream。
- **C 本机**：postprocess 隔离拍版本重跑 960×540 全帧 Golden；之后在板卡上实测启动、HDMI 图像、吞吐和画质。
- 请 B 在同一输入、ROM、Golden 和无竞态 testbench 条件下确认 XSim 2025.2 结果；B 侧测试台竞态作为独立事项维护，不要与 C 侧默认优化现象混为一谈。
- 确认 A 全尺寸整数 Golden 的正式发布位置；另需确认 UART 管脚与真实 start 触发方案。
- 当前仓库没有已配置的 GitHub Actions Vivado runner。代码/文档审查可通过 GitHub 协作；综合、实现和板测依赖本机或具备相同工具与授权的硬件环境。

## 阶段总结交接给另一位成员

请另一位项目成员基于本文及下列证据，独立撰写 `docs/STAGE_SUMMARY_2026-09-23.md`：

- `docs/B_C_REAL_ACCEPTANCE_REPORT.md`
- `docs/B_REAL_XSIM_OPTIMIZATION_FINDING.md`
- `docs/B_REAL_XSIM_REPRODUCIBILITY.md`
- `docs/B_C_REAL_SYNTH_CHECKPOINT.md`
- `docs/CODEX_CONTINUATION_PLAN.md`

阶段总结应分清最新小图回归、未复跑的全尺寸图像、已经完成但时序未收敛的综合/实现、未完成的 bitstream/板级验收，以及本机执行和 GitHub 协作任务。不要声称板测通过、200 MHz 收敛或全尺寸最新 RTL 已回归。若发现本文与原始报告冲突，应指出冲突并引用具体证据，不自行补猜结论。
