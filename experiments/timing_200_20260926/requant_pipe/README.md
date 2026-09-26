# 200 MHz 备用候选：完整 Q31 乘积寄存边界

## 状态与范围

**2026-09-26 19:20：Vivado/XSim 2025.2 单元仿真 PASS：scalar 6/6、完整 INT64 probe、shared 3/3。** 整网回归、综合及实现仍需独立验证。

成功会话 PID `33224`，scalar/shared 分别位于 `unit_work/run_20260926_192006_33224/tb_requant_scalar/` 和 `unit_work/run_20260926_192010_33224/tb_requant_shared/`。scalar 每配置实际检查 3122–3168 个输入结果，INT64 probe 检查 1094 项；shared 每配置接受 358 个向量、输出 354 个，其余按在途复位丢弃，独立队列、停顿和保持检查均通过。最终 `REQUANT_PIPE_ALL_UNIT_TESTS_PASS`。原始日志及源文件哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units/summary.json)。

所有文件均在本隔离目录。正式 B/C 工程未改。集成时同时替换本目录的 `prelu_requantize.sv` 和 `vector_postprocess_shared.sv`，不能只换其中一个，也不能与原模块同时加载。reference 和 TB 只用于仿真。

对应证据是 `_synth_bc/acc36_realrom_200_member_b_setup0300926_ascii_ramdecomp/reports/timing_placed_setup030.rpt`：L2 scalar 的 DSP `requant_product_s5_reg__0/CLK` 到 `rounded_q31_s6_reg[33]/D`，数据延迟 5.395 ns，23 级逻辑，21 个 CARRY4。路径先经过部分积重建进位链，再经过 Q31 舍入进位链。现有 RTL 已经采用 guard/sticky 舍入；本候选不再改写舍入公式。

## 修改

- 原 `requant_product_s5` 乘法级保留。
- 新增 signed 64 位 `requant_product_full_s6`，用 `DONT_TOUCH` 和 `KEEP` 请求保留完整乘积寄存边界；同步增加 `valid_full_s6`。
- 舍入只读取完整乘积寄存器，结果写 `rounded_q31_s7`，再进入原输出饱和寄存器。数据与 valid 同时增加一拍，scalar 共 8 个寄存级。
- shared 的 metadata valid/slot 从 8 位扩展到 9 位，group 从 8 项扩展到 9 项。移位、复位、结果写槽、完成计数及断言全部读取末项 `[8]`。
- shared 的两槽占用、顺序和 ready 协议保持原逻辑。**增加一拍会延长槽占用，不能继续承诺原注释的每 8 拍接收一个向量。** 须以完整网络仿真重新测吞吐。

若输入在第 n 个上升沿被 scalar 采样，原版在第 n+6 个上升沿后置 out_valid，候选在第 n+7 个上升沿后置 out_valid。shared 的分组标签必须同步增加一拍。

## 数学边界

令 signed64 输入 `x=q*2^31+r`，`q=floor(x/2^31)`，`0<=r<2^31`。原公式保留：

```text
q = signed(x[63:31])
increment = x[30] & (~x[63] | OR(x[29:0]))
rounded = sign_extend_34(q) + increment
```

正数在半 LSB 及以上向上加 1；负数只在严格超过半 LSB 时加 1，因此负数恰好一半时仍向远离零的方向取整。`INT64_MIN` 得到 `-2^32`，不计算 signed64 绝对值。`INT64_MAX` 得到 `+2^32`，所以舍入结果仍须 signed34，不能缩为 signed33 或 signed32。输出继续先作 signed34/35 比较，再截取 OUT_W，避免饱和前截断。

## 验证文件

- `prelu_requantize_reference.sv`：原 scalar 仅改模块名。原源 SHA256：`572F01FF911B822DD4BE4089CB01341BDCE81B6C840AB01A41A1AAF133137FAF`。
- 原 shared 源 SHA256：`C136BE73A1283BF990DC8C48770F46F19C00F7AFB4AB30EFD138FF0ADEC816B0`。
- `tb_requant_scalar.sv`：6 个参数组合，覆盖 signed16 PReLU 开/关、unsigned8 PReLU 关、signed31、unsigned31、signed1。逐拍比较原版延迟一拍，以及独立 64 位数学模型；检查 valid 空洞、无效期输出保持、在途复位、正负 Q15/Q31、饱和边界、半 LSB 及两侧、确定性随机输入。额外直接探测实际舍入表达式，覆盖完整 INT64 边界和 signed31 输出饱和；直接探测不是可达输入等价证明的替代。
- `tb_requant_shared.sv`：覆盖本网络去重后的 3 种参数组合（16/2、8/1、4/1），独立数学队列检查多组拼接、顺序、两槽满、长反压、槽复用及复位。PReLU/Q31 配置按通道保持静态，符合 shared 仅缓存 accumulator 的接口前提。
- `run_unit.tcl`：顺序运行两个独立 top；检查 6 个 scalar 配置、INT64 probe、3 个 shared 配置的 PASS，任何 fatal/error 或缺失标志均失败。日志和快照只写 `unit_work/`。

## 复现运行

需要复跑时，先确认 Vivado 空闲及 `V:` 已映射到 `F:\FPGA预选\10h冲刺_c_trial`，在 Vivado Tcl Console 中执行：

```tcl
source V:/experiments/timing_200_20260926/requant_pipe/run_unit.tcl
```

最终应出现 `REQUANT_PIPE_ALL_UNIT_TESTS_PASS`。脚本复用本机既有 XSim 的 `-O0` 和快照目录 DLL 装载办法，不运行综合或实现。若 V: 未映射，应先由父任务按当前环境配置 ASCII 路径。

## 综合与实现验收

1. 单元测试通过后，再做完整 B+C Golden/反压回归；尤其记录两槽吞吐变化。
2. 从网表确认每个 scalar 的完整乘积边界实际为独立 FF，检查相应单元的 `DONT_TOUCH` 属性及 fanin/fanout；不要只依赖 RTL 属性或 FF 总数。
3. 分别报告 DSP 部分积输出 → 完整乘积 FF，以及完整乘积 FF → 舍入 FF 的路径。应看到先前串联的重建/舍入 carry 链被时钟边界分开。若仍串联，候选目的未达成。
4. 比较 DSP、LUT、FF、控制集合、route errors、setup/hold、WNS/TNS；新增 FF 和其 valid/reset 扇出也可能改变布局。该候选不预先保证频率或裕量收益。

这里没有更改舍入算法或增加共享槽数量。上述单元测试范围内的数值、延迟及共享槽控制已通过核对；仍不能据此宣布整网吞吐不变、200 MHz 实现成功或上板通过。
