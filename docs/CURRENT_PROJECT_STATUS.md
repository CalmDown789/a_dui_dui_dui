# C 端与项目总体状态交接

**快照时间：2026-09-23（北京时间）**

**代码/证据基线：`c-side-latest`，提交 `51443d3`**
**用途：为另一位项目成员撰写阶段性总结提供事实材料；本文不是最终验收签署。**

## C 端当前状态

### 已完成并有证据

- C 的 `C_USE_B_REAL` 路径接入 B 五层 RTL 快照 `ae29515`，闭包为 15 个 RTL 文件；19 个参数 ROM 已入库并有来源/哈希清单。
- 本机 Vivado/XSim 2022.2 使用默认 `xelab` 优化时，96×54 四组逐字节对拍失败；同一 RTL、ROM、输入、Golden 和 runner 改用 `xelab -O0` 后，6×5 分层探针、96×54 四组以及 960×540 全帧均通过。
- 全帧结果：输入 518,400/518,400；输出 2,073,600/2,073,600 字节匹配；X=0；17 个条带尾、1 个帧尾、保持规则违例 0；4,180,016 周期。
- `-O0` 下真实 B smoke 和背压测试通过。三种背压场景逐字节匹配；T-B 连续有效输出停顿 300 拍、保持违例 0。期间改动是 C 侧背压测试台的重复触发/停顿计数，不是 B 或 C 硬件 RTL。
- B 提供的 XSim 2025.2 PASS 是 B 侧记录；本机只有 2022.2，尚未在本机复跑 2025.2。

### 当前结论边界

- 已复现的数值差异受 XSim 2022.2 默认优化配置影响；`-O0` 下仿真与整数 Golden 一致。不要把旧默认优化失败矩阵写成当前 `-O0` 功能结论，也不要把 `-O0` 当成硬件修复。
- 仿真通过只证明指定工具、输入、ROM、Golden 和 testbench 配置下的结果。尚未证明综合后的硬件行为，也没有生成可供板测的本轮 bitstream。
- 早期默认优化日志中的 L1 后处理差异属于该默认配置下的观测；`-O0` 分层探针全通过后，不能再据此单独断言 B 的数值 RTL 有缺陷。

## 项目总体状态

| 验收项 | 当前状态 | 可引用证据/限制 |
|---|---|---|
| C-B 接口与仿真协议 | `-O0` smoke、背压回归通过 | `docs/B_REAL_XSIM_REPRODUCIBILITY.md` |
| 真实 B 数值对拍 | XSim 2022.2 `-O0` 下小图和全帧通过；默认优化失败 | 同一 runner 的对照材料见 `report/xsim_repro/` |
| B+C 综合资源/综合时序 | 未取得有效报告 | 两次 synth-only 均未产出资源/时序报告，不能引用 C+stub 或预算数字 |
| 布局布线/实现时序 | 未运行 | 没有 WNS、路由状态或实现后资源数据 |
| bitstream/上板/HDMI 图像 | 未完成 | 没有本轮 bitstream、板上运行记录或验收图像 |
| 系统级最终验收 | 未完成 | 不能声称已达 200 MHz、30 fps 或板级图像正确 |

### 本机综合停止记录

2026-09-23 两次 B+C synth-only 均未获得报告。首轮在可用物理内存降至约 0.61 GB 时被过早中断；第二轮改为监控提交内存和页面文件，运行约 40 分钟并完成 RTL Optimization Phase 2，之后没有新的综合日志或报告。

第二轮最高观察到系统提交量约 62.31/63.43 GB，余量约 1.12 GB。系统管理页面文件分配 32 GB，停止前页面文件占用约 4.71 GB；提交上限在运行期间未扩大。Vivado 被安全中断时没有报告资源分配错误。详情与原始日志见 `docs/B_C_REAL_SYNTH_CHECKPOINT.md`、`report/bc_real_synth/synth_only_memory_stop.txt` 和 `report/bc_real_synth/synth_only_commit_limit_stop.txt`。

## 仍开放的项目事项

- 先确认并提供足够的 Windows 提交内存/页面文件容量，再重跑 B+C synth-only；必须拿到真实 `b_core_real`、五层实例自检和资源/时序报告后，才评估是否进行完整实现。
- 取得实现报告、生成 bitstream 后，再由 C 端在板卡上运行并记录 HDMI 输出图像、启动流程和必要的吞吐/画质指标。
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

阶段总结应分清已通过的仿真、尚未取得的综合/实现结果、未完成的板级图像验收，以及本机执行和 GitHub 协作任务。请把默认优化失败作为历史对照、把 `-O0` 结果作为当前本机仿真证据；不要声称板测通过、200 MHz 收敛或已有真实 B+C 资源数据。若发现本文与原始报告冲突，应指出冲突并引用具体证据，不自行补猜结论。
