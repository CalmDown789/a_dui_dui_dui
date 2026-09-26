# PReLU 有符号直接舍入备选

2026-09-26：仅准备并静态审查，未编译、仿真或综合；父任务决定是否启用。本目录不属于已冻结的 V1/V2/V3 输入。

## 改动与动机

基于 V2 `requant_pipe/prelu_requantize.sv`，将 PReLU 原来的绝对值和恢复符号改成有符号直接舍入。s2 用于寄存完整 signed48 乘积，s3 完成 Q15 舍入，s4 完成 INT32 饱和或 accumulator 旁路。PReLU 的 s1/s2 无 KEEP、DONT_TOUCH 或新的 DSP 指定属性，允许综合器重新分配寄存器。

外部延迟保持 V2：scalar 8 级，shared 仍为 dispatch 加 scalar 共 9 级 metadata。`vector_postprocess_shared.sv` 原样复制 V2 的 `post_shift` 版本；slot/group/valid、ready、输入槽移位和回收规则均未修改。现有 Q31 完整乘积寄存级的 KEEP/DONT_TOUCH 保留。

已有 V2 综合最差路径为 PReLU DSP 的 PCOUT→PCIN，源 MREG/PREG=0/0、目标 MREG/PREG=0/1。V3 在完整结果后增加一级后，父任务核验 MREG 仍为 0，原 PCIN 路径综合 slack 仍为 +0.016 ns。因此本候选复用 s2 **不保证**改变 DSP 级联结构或改善时序。目前保留为备选，不增加本轮长实验。显式拆乘法的候选由父任务另行准备。

## 位宽与等值推导

对任意 signed48 整数 x，写成 `x = q * 32768 + r`，其中 `q = floor(x/32768)`，`0 <= r < 32768`。

- 非负 x：r 大于等于 16384 时加 1。
- 负 x：r 严格大于 16384 时加 1；恰好半值时保持更负的 q，实现半值远离零。
- 因此 `round_up = x[14] & (~x[47] | (|x[13:0]))`。

`$signed(x[47:15])` 是 signed33 的 q。先将 q 符号扩展到 signed34，再加 signed34 的 0/1；两项显式 `$signed`，防止拼接默认 unsigned 导致比较或加法扩展错误。完整 signed48 的最大正数可舍入成 +2^32，最小数可成为 -2^32，因此不能将结果缩回 signed33。

实际 signed32×signed16 的乘积位于 `[-(2^31-1)*2^15, 2^46]`，signed48 完全容纳。乘法两个操作数和结果声明均为 signed。上述公式对这个区间和更大的完整 signed48 区间都成立；有限测试不等于穷举全部 INT32×INT16 组合。

舍入取乘积的符号；是否执行 PReLU 仍由原 accumulator 为负且 APPLY_PRELU 非零决定。负 alpha 使乘积变正时也按正值舍入。s4 用 signed34 的 INT32 上下限比较后再截取低 32 位，顺序与原版“Q15 舍入→INT32 饱和→Q31 乘法”一致。accumulator 非负或 APPLY_PRELU=0 仍旁路原 accumulator。

关键边界：

| 输入乘积 x | Q15 舍入结果 |
|---|---:|
| -16383 / -16384 / -16385 | 0 / -1 / -1 |
| +16383 / +16384 / +16385 | 0 / +1 / +1 |
| INT32_MIN × INT16_MIN | +2^31，随后饱和为 INT32_MAX |
| signed48 最小 / 最大值 | -2^32 / +2^32 |

完整 Q31 舍入实现未变，TB 继续覆盖 INT64_MIN；其无符号绝对值参考模型能容纳 2^63，不会发生有符号取反溢出。

## 时序与控制静态核对

以一次有效输入的采样沿为 E1：E1 乘积 s1，E2 完整乘积 s2，E3 舍入 s3，E4 INT32 饱和或旁路，E5 Q31 乘积，E6 完整 Q31 乘积，E7 Q31 舍入，E8 输出饱和。与 V2 同拍。

accumulator、Q31 multiplier 在 s1→s2→s3 同步延迟。所有 valid 每拍移位，数据寄存器只在对应 valid 时更新；同步 reset 清空数据与 valid，invalid 输出保持规则不变。shared 的 9 拍标签无需更改。

## 文件与独立验证

- `prelu_requantize.sv`：候选 scalar。
- `prelu_requantize_reference.sv`：V2 scalar 仅更名，供同拍对照。
- `vector_postprocess_shared.sv`：V2 post_shift 原样副本。
- `vector_postprocess_shared_reference.sv`：post_shift 原有索引选组参考，原样副本。
- `tb_prelu_signed_round.sv`：6 个配置同拍对照、8 级独立数学队列、Q31 INT64 探针和新 PReLU signed48 探针。
- `tb_prelu_signed_shared.sv`：复用 V2 五组 shared 测试，仅改顶层名和 PASS 标志。
- `run_unit.tcl`：隔离编译和运行入口。

scalar 配置为 signed16 开/关 PReLU、unsigned8 关 PReLU、signed31 开 PReLU、unsigned31 关 PReLU、signed1 开 PReLU。每配置包含 1408 组边界组合、2000 次固定种子随机驱动、连续输入、invalid 空洞、3 次在途 reset、全周期输出保持检查；参考输出与候选同拍比较，不额外延迟。数学模型使用 signed64 乘法与绝对值加半值舍入，不复制 RTL 的切片公式。

signed48 探针直接驱动 `prelu_product_full_s2`，核对实际 `prelu_rounded_s2`，共 2189 项：13 个极值/半值边界、112 个正负商余数组合、64 个真实乘法边界和 2000 个完整 48 位随机值。Q31 探针保留 1094 项，包含 INT64_MIN 及最终 signed31 饱和。两项探针是补充，不能替代完整流水对照。

shared 五配置为 16/2、8/1 的 signed16 PReLU，4/1 的 unsigned8 旁路，以及 1/1、4/2 的 signed16 PReLU。测试保留独立数学 scoreboard、全周期 ready/valid/out_flat 与 dispatch 比较、双槽填满、96 拍背压、槽复用、同时收发、固定种子随机背压、在途和持有输出时 reset、64 组不饱和小值。两份 shared 都编译本候选 scalar；V2 scalar 的等价性由 scalar TB 单独核对。PReLU/Q31 每通道参数全程静态，与现有 shared 接口要求一致。

未来在已建立 V: 仓库映射及正确 Vivado 环境中运行：

```tcl
set argv {tb_prelu_signed_round tb_prelu_signed_shared}
source V:/experiments/timing_200_20260926/prelu_signed_round/run_unit.tcl
```

runner 每次创建新的 `unit_work/run_<time>_<pid>/`，xvlog/xelab 使用 `--nolog`，DLL 在 elaboration 后放入对应 snapshot，XSim 控制台输出与 `xsim_engine.log` 分开。要求 scalar 6 个配置、两个算术探针、shared 5 个配置全部通过，且 stdout/engine 无 error/fatal。最终标志为 `PRELU_SIGNED_ROUND_ALL_UNIT_TESTS_PASS`。本次没有执行上述命令。

## 如后续启用，仍需核验

1. 单元仿真全部通过，且实际编译源路径指向本目录。
2. 综合按完整 instance 读取每个 PReLU DSP 的 AREG/BREG/MREG/PREG 和级联连接；新增完整结果寄存器不能当作 MREG 已启用的证据。
3. 对比最差路径、资源，以及原 5.000 ns 时钟和原自动 uncertainty 下的最终 setup/hold/route/DRC。
4. 用精确源哈希重新执行整网 Golden、真实背压与 C UART 回归；未通过前不能替换已验证版本。
