# L3/L5 partial 两槽缓冲备选（2026-09-26）

状态（2026-09-26 19:44）：**Vivado/XSim 2025.2 双宽度 FIFO 单元仿真 PASS**。V2 整网回归、综合与布线仍需独立验证；不能据此认定时序改善或 200 MHz 达标。

成功会话 PID `30704`，工作目录 `unit_work/run_20260926_194416_30704/`。L3 259 位：691 次 push、683 次 pop、复位丢弃 8 项；L5 131 位：683/673/10，均满足数据守恒。两者最长连续同时 push/pop 均为 23 拍，满时 pop 禁止 push 分别命中 256/251 次，各完成 1595 拍随机流量和定向复位。原始日志及源文件 raw/canonical 哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units_next/summary.json)。

## 修改与成本

以 `../mac_buffer/mac_issue_stage.sv` 为起点；原件 raw SHA-256 为 `505e871bae49bb554fcdb5e83eceff623d4009bbfa5094f8ea5e83ad627f2f0a`。除注释外，只把启用缓冲的 generate 条件扩为：

```verilog
((K==3)&&(CIN==8)&&(COUT==8)) || ((K==5)&&(CIN==16)&&(COUT==4))
```

两槽 FIFO 的逻辑完全沿用现有 L5 版本，其余层仍走 direct 分支。保留原 `g_l5_partial_buffer` 标签以保持现有 L5 层次名，标签在新增 L3 分支中也使用；判断依据是参数条件。

| 冻结网络层 | OUT_PAR | 每槽内容 | 两槽数据位 | 控制位 |
|---|---:|---|---:|---:|
| L3，K3/CIN8/COUT8 | 8 | 3 位 phase + 8 个 signed32 partial，259 位 | 518 | 4 |
| L5，K5/CIN16/COUT4 | 4 | 3 位 phase + 4 个 signed32 partial，131 位 | 262 | 4 |

位宽始终使用 `3+OUT_PAR*32`，避免截断 phase 或最高输出通道。L3 新增 518 位数据存储与 4 位控制状态，按全部映射为 FF 估计约 **522 个额外 FF**；实际 FF/LUTRAM/LUT 数量以综合为准。L5 的 266 位状态已有，当前双层总计 788 位状态。

无反压时，L3 的每个 partial 相对原直接连接额外延迟 **1 拍**；L5 保留已有 1 拍。累加器按 phase 顺序接收同一数据。不能用原网络的绝对周期号对拍；必须按 ready/valid 接受顺序比较结果和控制标记。停顿条件下，延迟与接受节奏随队列占用变化。

## 反压行为

`in_ready = (count < 2)` 仅依赖寄存器 count，不含 `|| pop`，因此断开 accumulator ready 向 MAC 传播的组合路径。

- 空队列接收一项后，下一拍可输出；没有组合穿透。
- count 为 1 时，可持续每拍同时 push/pop。
- count 为 2 时，即使下游该拍 pop，仍禁止 push。下一拍恢复接受。
- 下游停顿时输出数据与 phase 保持；同步 reset 清空占用和指针，数据存储无需清零，空时输出无效。

本备选针对当前 L3 反向 ready 路径的潜在瓶颈。新增 FIFO 的计数、读数据选择和存储路径也可能成为关键路径，必须重新布线测量。

## 独立队列单测

`tb_mac_partial_fifo2.sv` 并行实例化实际 L3 **259 位**和 L5 **131 位** FIFO。scoreboard 使用前端出队、数组移动、尾部追加的模型，独立于 RTL 的环形指针，逐拍核对全部数据和 phase。

每个配置要求覆盖：空队列、反复满空/指针回绕、满时 pop 且禁止 push、至少 20 拍连续同时 push/pop、40 拍定向反压、阻塞时输入/输出保持、停顿追加、固定种子随机流量（至少 1500 拍）、满/半满/待接收输入及 valid 为高时 reset。最终检查 accepted = emitted + reset-discarded，覆盖不足直接失败，100 us 硬超时。

这里只单测 FIFO；包装模块的 L3/L5 启用条件及其它层直连仍需完整源闭包 elaboration 与整网回归证明。

## 后续运行入口

需复跑时，由主任务安排执行；`V:` 必须已映射到本实验仓库。

```tcl
source V:/experiments/timing_200_20260926/mac_buffer_l3l5/run_unit.tcl
```

或在已配置 Vivado 2025.2 的命令环境中运行：

```powershell
vivado -mode batch -source V:/experiments/timing_200_20260926/mac_buffer_l3l5/run_unit.tcl -log V:/experiments/timing_200_20260926/mac_buffer_l3l5/unit_vivado.log -journal V:/experiments/timing_200_20260926/mac_buffer_l3l5/unit_vivado.jou
```

runner 使用唯一 `unit_work/run_<时间>_<PID>/`、`xelab -O0`、Vivado 2025.2 DLL staging；`xvlog/xelab --nolog`，XSim 引擎写 `xsim_engine.log`，标准输出单独写 `xsim.log`。成功必须恰有两个配置 PASS（id=3 width=259、id=5 width=131），一次 `MAC_L3L5_ALL_CONFIGS_PASS configs=2`，runner 输出 `MAC_L3L5_UNIT_TEST_PASS`，且无 fatal/error。

单测通过后，下一轮仅选择本目录的 `mac_issue_stage.sv` 替换原 L5-only 版本，不能同时编入两份同名模块。固定候选源文件哈希，先跑既有反压与真实 Golden 整网回归，再完成 200 MHz 同条件综合、布局布线、资源与路由错误核查。只有最终路由报告可判断是否达到 +0.1 / +0.25 / +0.4 ns 目标。
