# bias 提前累加候选（成员 B，2026-09-26）

状态（2026-09-26 19:20）：**Vivado/XSim 2025.2 单元仿真 5/5 配置 PASS**；整网回归、综合及布线仍需独立验证。本目录仅供 200 MHz 实验，不修改 C 正式工程。

成功会话 PID `33224`，工作目录 `unit_work/run_20260926_191941_33224/`。五组均出现唯一配置 PASS 和最终 `BIAS_EARLY_ALL_FIVE_CONFIGS_PASS`；各组实际消费 163–169 个窗口，正负饱和、精确上下界、输入/输出停顿和两类复位覆盖均通过。原始日志、逐项 coverage 及 RTL/TB/runner 的 raw/canonical 哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units/summary.json)。

## 原理与等价边界

原模块在 `sum_stage` 后同一周期完成 36 位加 bias 和 INT32 饱和。旧 200 MHz 报告中，该类路径经过 10 个 CARRY4，总计 12 级逻辑。

候选在 phase 0 把所有通道的累加初值置为符号扩展后的 bias，按原分组依次加 partial；phase 7 捕获总和，原输出级仅做饱和。因此端口、寄存器级数、ready/valid 方程、输出延迟和握手顺序保持原结构。

**前提：bias 从一组 phase 0 开始到其输出接受期间保持稳定。**当前 `fsrcnn_network_mem_top.sv` 中 bias 仅由 `$readmemh` 初始化且没有运行时写入，满足该前提；本候选不承诺与动态修改 bias 的通用用法等价。

- 输入 partial 和 bias 均为 signed32；`sx32()` 显式拼接 4 个符号位并返回 signed36，避免无符号 packed slice 或表达式宽度造成歧义。
- 任一输出通道最多有 8 项 signed32 partial 和 1 项 signed32 bias。绝对值上界不超过 `9 × 2^31 = 19,327,352,832`，小于 signed36 的负向量程 `2^35`；中间步骤也不会发生 36 位回绕。
- signed36 能直接表示为 signed32，当且仅当 `value[35:31] == {5{value[31]}}`；不满足时用 **bit 35** 决定正/负饱和，不能用可能已翻转的 bit 31。
- 不在中间 partial 处饱和，保留“先越过 INT32 范围、后又加回合法范围”的结果。

## 文件

- `phase_accumulator_36.sv`：候选，模块名仍为 `phase_accumulator`。
- `phase_accumulator_reference36.sv`：原文件逐字复制，仅将模块名改为 `phase_accumulator_reference36`。
- `tb_bias_early.sv`：五组配置并行对拍；另以独立 signed64 加法与数值比较作数学 scoreboard。
- `run_unit.tcl`：XSim 编译、elaborate、运行和 PASS 检查；复用现有 Windows DLL staging 与 `-O0`。

原始对照文件：`experiments/l5_splitmem_20260924/rtl/b/phase_accumulator_36.sv`，SHA-256：

```text
213D73BB6A0B49747D5C57521F93A72CDFC99434FB66EA514411154C4D7A3342
```

已做静态文本核对：把对照模块名还原后，文件内容与原件完全一致。该检查不是仿真通过记录。

## 自检内容

配置完全对应冻结网络的 L1–L5：`(CIN,COUT,IN_PAR,OUT_PAR)` 分别为 `(1,16,1,2)`、`(16,8,2,8)`、`(8,8,1,8)`、`(8,16,1,16)`、`(16,4,2,4)`。

每配置覆盖：INT32 正/负饱和、精确上下界、零 partial、正负交替与宽中间值恢复、固定种子的随机 signed32 partial、valid 空拍、长期输出阻塞、输入保持、输出保持、阻塞解除后的连续输出、非空复位、未完成相位组复位。每拍比较候选与原模块的 ready、valid、有效输出，故数据相同但延迟变化也会失败。数学模型使用 64 位计算，与候选的 36 位加法和位模式饱和独立。

任意不一致或覆盖不足 `$fatal`；硬超时 100 us，无波形 dump。

## 复现验证

需要复跑时，先确认 Vivado 空闲；在正确映射到本实验仓库的 Vivado 2025.2 Tcl Console 执行：

```tcl
source V:/experiments/timing_200_20260926/bias_early/run_unit.tcl
```

或在已配置 Vivado 2025.2 的命令环境执行：

```powershell
vivado -mode batch -source V:/experiments/timing_200_20260926/bias_early/run_unit.tcl -log V:/experiments/timing_200_20260926/bias_early/unit_vivado.log -journal V:/experiments/timing_200_20260926/bias_early/unit_vivado.jou
```

需恰好五条 `BIAS_EARLY_CONFIG_PASS` 和最终 `BIAS_EARLY_ALL_FIVE_CONFIGS_PASS`，且无 fatal/error。输出只写本目录 `unit_work/`。

单模块通过后仍须既有五层三种反压场景、四组 96×54 真实 A Golden 回归。然后同器件、真实 ROM、相同 XDC、36 位累加与选定实现策略执行完整 200 MHz 布线；记录新关键路径是否转入累加输入或其它模块。不得仅根据消除输出加法宣称时序改善。
