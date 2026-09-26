# L5 partial 两槽缓冲备用候选（成员 B，2026-09-26）

状态（2026-09-26 19:20）：**Vivado/XSim 2025.2 的 131 位 FIFO 单元仿真 PASS**；完整 MAC/网络集成回归、综合及布线仍需独立验证。本目录不修改 C 正式工程，也不包含 bias 提前候选；两项实验可独立选择。

成功会话 PID `33224`，工作目录 `unit_work/run_20260926_191946_33224/`。实际 1786 拍、683 次 push、673 次 pop；满时 pop 禁止同时接收命中 265 次，同时 push/pop 275 次，最长连续运行 23 拍，保持检查 984 次，非空复位 6 次。最终标志 `MAC_PARTIAL_FIFO2_131BIT_TEST_PASS`。原始日志及源文件哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units/summary.json)。

## 修改范围

`mac_issue_stage.sv` 是 `experiments/l5_splitmem_20260924/rtl/b/mac_issue_stage.sv` 的实验副本。

原件 SHA-256：`B0641CC9A53E51E2867A00DA4B51DCBB2F0CCDF8EFDB6595412AC80E1ABD5B2A`。

- 仅当 `K==5 && CIN==16 && COUT==4` 时，在 `phase_mac_pipeline` 输出和 `phase_accumulator` 输入之间放置两槽 FIFO。
- 冻结 L5 的 `OUT_PAR=4`，每项为 `{phase[2:0], partial_sums[127:0]}`，共 **131 位**；phase 与四个 signed32 partial 同进同出，不改变数值。
- 其它层通过 generate 的 direct 分支保持原来的数据、phase、valid、ready 连接。
- 小 FIFO `mac_partial_fifo2` 定义在同一文件，替换该文件时无需新增 RTL 源文件项。
- 新缓冲会增加 L5 partial 的传输延迟；不能按原模块周期号对齐对拍，应按 ready/valid 接受顺序核对结果。

## ready 与容量

`in_ready = (count < 2)`，其中 count 是两位寄存器。没有 `|| pop`，因此 downstream `out_ready` 不会组合传回 MAC 的 `out_ready`。

| 时钟沿前 count | push / pop 行为 | 时钟沿后 count |
|---|---|---|
| 0 | 可接收，不能弹出 | 接收后为 1 |
| 1 | 可同时接收、弹出 | 同时发生仍为 1 |
| 2 | 禁止接收，可以弹出 | 弹出后为 1 |

满后恢复时，上游暂停接收一拍；之后在 count 为 1 时可持续每拍传递一个 token。下游停顿时，当前输出 word 与 phase 保持，最多再接收一个 token。同步 reset 清空 count 与读写指针；数据存储不复位，空时输出无效。

该缓冲切断 accumulator ready 对 MAC 的直接组合依赖。MAC 内部剩余的 ready 链、该缓冲自己的存储/计数路径仍需目标综合与布线验证，不能只凭插入 FIFO 宣称 200 MHz 通过。

## 独立自检

`tb_mac_partial_fifo2.sv` 只实例化实际 131 位 FIFO。独立 scoreboard 用前端出队后移动数组的队列模型，不复制 RTL 的环形指针结构。

覆盖：空队列、填满、满时弹出但仍禁止输入、count 为 1 时连续同时 push/pop、长反压输出保持、停顿追加、完整 131 位数据与 phase 顺序、反复满空/指针回绕、固定种子随机流量和非空 reset。每拍核对 `ready==(count<2)`，可直接检出误写的 `||pop`。驱动端阻塞时保持未接受数据。失败或覆盖不足 `$fatal`，100 us 硬超时，无波形 dump。

## 复现命令

需要复跑时，先确认 Vivado 空闲；在正确映射到实验仓库的 Vivado 2025.2 Tcl Console 中执行：

```tcl
source V:/experiments/timing_200_20260926/mac_buffer/run_unit.tcl
```

或在已配置 Vivado 2025.2 的命令环境中运行：

```powershell
vivado -mode batch -source V:/experiments/timing_200_20260926/mac_buffer/run_unit.tcl -log V:/experiments/timing_200_20260926/mac_buffer/unit_vivado.log -journal V:/experiments/timing_200_20260926/mac_buffer/unit_vivado.jou
```

输出写本目录 `unit_work/`。必须出现 `MAC_PARTIAL_FIFO2_131BIT_TEST_PASS` 且无 fatal/error。runner 复用现有 DLL staging 与 `xelab -O0`。

单模块通过只说明 FIFO 行为；还需在完整源码闭包中 elaboration，运行既有三种反压与四组真实 Golden 回归，确认八相位顺序、输出字节及控制标记。随后才进行同条件 200 MHz 完整布线、资源与路由错误核对。
