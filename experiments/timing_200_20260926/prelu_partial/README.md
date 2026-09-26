# PReLU 显式部分积候选

2026-09-26 20:14:57 单元仿真通过：Vivado/XSim 2025.2，PID 20920，scalar 6/6、shared 5/5 配置 PASS。共核对 23092 个 scalar 输出、23207 次完整 48 位拼合和 1094 项 INT64 舍入探针；原始日志与源码哈希见 [units_prelu_partial](../../../member_b_evidence/timing_200_20260926/units_prelu_partial/README.md)。整网与实现另行验证。本目录基于 V3 `prelu_pipeline`，保持 scalar 九级和 shared 十拍标签，只替换前两级乘法结构。

## 改动依据与结构

V3 增加完整结果寄存后，父任务报告 PReLU DSP 的 MREG 仍为0，源 PREG=0/目标 PREG=1，综合最差路径仍是原 CLK→PCOUT→PCIN；因此这一候选显式寄存两个部分积，再用普通逻辑重建完整结果。

对于 signed32 输入 x 和 signed16 参数 a：

```text
H = signed(x[31:16])
L = unsigned(x[15:0])
x = H × 65536 + L
x × a = (H × a) × 65536 + L × a
```

- 第一拍：`prelu_product_hi_s1` 是 signed16×signed16→signed32；`prelu_product_lo_s1` 是补零后的 signed17×signed16→signed33。两个乘法都请求 `use_dsp="yes"`。
- 第二拍：两个部分积分别**先符号扩展到48位**，高项左移16位后相加，写入 signed48 的 `prelu_product_s1b`。求和请求 `use_dsp="no"`；完整结果寄存还带 KEEP/DONT_TOUCH，保留逻辑加法后的边界。
- accumulator、Q31 multiplier和valid按V3原s1→s1b延迟。后续PReLU绝对值、Q1.15舍入、INT32饱和、Q31乘法/舍入、输出饱和逐行保留。
- shared与V3副本一致，dispatch后仍用10拍valid/slot/group标签，不改变两槽调度。

例如 x=-1：H=-1，L=65535，组合为 `(-1×a)×65536+65535×a=-a`。L直接当signed16会得到-1，造成错误；本实现显式补零形成正的signed17。移位前扩成48位避免32位中间结果被截断。

H×a的幅度不超过2^30，L×a的幅度小于2^31；最终signed32×signed16的幅度不超过2^46，完整signed48足够容纳。此分解保持全INT32/INT16输入域，含负alpha和INT32最小值，不减少精度或改变半值远离零规则。

## 单测与入口

reference由当前V2 `requant_pipe` scalar只更名而来。单测检查候选等于reference延迟一拍，独立数学队列保持九级；shared使用外部握手FIFO及数学参考。

```tcl
set argv {tb_prelu_partial tb_prelu_partial_shared}
source V:/experiments/timing_200_20260926/prelu_partial/run_unit.tcl
```

此示例要求父任务已确认V:映射到本仓库。runner仅仿真，每次新建目录，编译使用`--nolog`，XSim控制台和引擎日志分开。要求6个scalar配置、INT64 Q31探针和5个shared配置全部通过，总标志为 `PRELU_PARTIAL_ALL_UNIT_TESTS_PASS`。

scalar覆盖INT32极值、正负alpha、低16位全1、高16位负值、半值两侧、饱和、连续输入、invalid保持和在途复位；额外直接核对完整48位拼合寄存，防止最终输出饱和掩盖拼合错误。shared覆盖真实16/2、8/1、4/1组态，以及GROUPS=1/2边界、双槽背压、复用、输入停顿和复位。

## 必须实证的映射与时序

属性是推断请求。后续综合必须确认：

1. 两个部分积分别保留独立DSP乘法及寄存；记录每个完整instance的AREG/BREG/MREG/PREG。
2. `prelu_product_s1b`前的重建加法由LUT/CARRY实现，完整结果寄存保留；不存在将两个部分积重新合并成原PReLU PCOUT→PCIN级联的情况。
3. 根据实际关键路径判断目标是否达成。本方案允许单个部分积DSP用PREG保存结果；MREG=0本身不等于本方案失败，关键是旧跨DSP乘法级联已经分开，且新的单DSP/逻辑加法路径可满足时序。
4. 记录DSP、FF、LUT及BRAM变化。逻辑声明中，65位部分积加48位完整结果，比V3两个48位完整结果级多17个数据寄存位；实际普通FF与DSP内部寄存数量不能由声明数直接推定。
5. 原200 MHz/5.000 ns及原自动uncertainty下检查布线后setup、hold、路由和DRC，再完成整网Golden/背压及C UART回归。综合结果只用于决定是否值得进入实现。

`prelu_signed_round`为另一独立候选；此处仍保留V3的绝对值算法和九级延迟，没有提前合并两项变更。
