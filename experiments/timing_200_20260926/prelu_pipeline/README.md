# PReLU 乘法增加一级的独立候选

准备日期：2026-09-26。本目录从 V2 的 `requant_pipe/prelu_requantize.sv` 和 `post_shift/vector_postprocess_shared.sv` 复制；仅本目录内增加一级。准备者未运行工具链，父任务负责实跑。

2026-09-26 20:04 单测已完成并独立核对：`unit_work/run_20260926_200420_21792/` 下 scalar 六配置全部通过，每配置比较 3119–3165 个有效输出；INT64 探针通过1094项；shared五配置各比较418个完整输出。编译日志明确读取本目录的新 scalar/reference/shared。RTL、TB及runner已冻结，后续仅读报告；完整网络及物理验收单独记录。

## 已有证据与目的

V2 原 5.000 ns 条件下的综合 WNS 为 +0.016 ns；前 20 条 setup 均属于 L1 PReLU DSP 级联，属于未布局估算。最差路径位于 `l1/post/units[0].post`：

| 项目 | 已核对值 |
|---|---:|
| 源 `prelu_product_s10` AREG/BREG/MREG/PREG | 1 / 1 / 0 / 0 |
| 目标 `prelu_product_s1_reg` AREG/BREG/MREG/PREG | 1 / 1 / 0 / 1 |
| 源 CLK→PCOUT[0] | 3.541 ns |
| PCOUT→PCIN[0] 连线 | 0.055 ns |
| 总数据延迟 | 3.596 ns |
| 目标 PCIN 建立时间 | 1.174 ns |
| 时钟偏移 / 自动 uncertainty | -0.145 ns / 0.069 ns |

证据入口为 `_synth_bc/acc36_realrom_200_member_b_pipeline2_0300926_ascii_ramdecomp/reports/timing_summary_synth.rpt`、`drc_synth.rpt` 及同级 `synth_setup030.dcp` 内的 EDIF。后者通过只读内存解压核对了精确属性和层级：`l1` → `fsrcnn_stream_layer` → `post/vector_postprocess_shared_8` → `units[0].post/prelu_requantize_9`。

原 shared 的 dispatch 寄存器已进入 DSP A/B 输入级；原 scalar 的乘法结果 s1 进入目标 DSP PREG。s2 会计算绝对值，没有可直接挪用的空流水级。3.541 ns 加 1.174 ns 的内部成本已达 4.715 ns，继续增加路由优化次数不能消除这部分算术延迟。

## 本候选改动与验收边界

- 保留完整 signed INT32×INT16→signed48 乘法。s1 后新增 `prelu_product_s1b`，并同拍延迟 accumulator、Q31 multiplier 和 valid。
- PReLU 绝对值、符号提取改读 s1b；原 s2 接收 s1b 的两个旁路值。之后的 Q1.15 取最近、半值远离零、INT32 饱和、Q31 舍入和输出饱和算法保持一致。
- scalar 由 8 级变为 9 级；shared 保留 dispatch 一拍，metadata 的 valid/slot/group 全部由 9 拍改为 10 拍。两个槽的占用、发射、输出握手保持原规则。
- 对乘法使用 `use_dsp="yes"`；PReLU 两个乘法结果级没有 KEEP/DONT_TOUCH，让综合器有机会将流水分布到两个 DSP 的 MREG 和最终 PREG。已有 Q31 完整乘积级的属性保持原样。

**本候选提供额外时序级供推断，尚未证明该级进入 MREG。** 若工具只在既有结果后增加普通 FF，原 A/B→乘法→PCOUT→PCIN→PREG 瓶颈仍可能保留。不得据“多了一拍”认定已经切开。

后续综合至少检查：

1. `post_dsp_pipeline.txt` 中目标 PReLU DSP 的 AREG/BREG/MREG/PREG，按完整 instance 区分乘法与 Q31 DSP。
2. 目标是使两路部分乘积经过 MREG，再进入级联加法/PREG。源 PREG 不一定需要启用；关键是原 3.541 ns 的源 CLK→PCOUT 算术段是否被 MREG 分开。
3. 再看实际 setup 路径和逐项延迟，确认瓶颈没有转移到绝对值、旁路控制、标签或其他层。
4. 记录资源变化、原 5.000 ns/原自动 uncertainty 下的布线后 setup、hold、路由及 DRC。综合正 slack 不能代表 200 MHz 已完成布线验收。

## 独立验证入口

在父任务已确认的 ASCII 仓库映射中，例如 V: 指向本仓库：

```tcl
set argv {tb_prelu_pipeline tb_prelu_pipeline_shared}
source V:/experiments/timing_200_20260926/prelu_pipeline/run_unit.tcl
```

runner 只运行仿真，不运行综合或实现。每次新建工作目录；xvlog/xelab 使用 `--nolog`，XSim 引擎日志与控制台日志分开。要求全部配置通过且两类日志无错误，最终标志为 `PRELU_PIPELINE_ALL_UNIT_TESTS_PASS`。

### scalar：6 个配置

`tb_prelu_pipeline.sv` 同时检查：

- 当前 V2 scalar 只更名所得 `prelu_requantize_reference` 的完整输出与 valid，再延迟一拍，与候选逐拍比较。
- 独立 signed64 数学参考及 9 级 valid/data 队列。
- 六配置为 signed16 开启/关闭 PReLU、unsigned8 关闭 PReLU、signed31 开启 PReLU、unsigned31 关闭 PReLU、signed1 开启 PReLU。覆盖全 INT32/INT16/Q31 边界、半值两侧、饱和、连续输入、invalid 空洞、在途复位和输出保持。
- 原 full-INT64 Q31 舍入探针继续检查 `requant_product_full_s6`、`requant_rounded_s6` 及最终饱和函数。

通过标志：6 条 `PRELU_PIPELINE_SCALAR_CONFIG_PASS id=`、`PRELU_PIPELINE_SCALAR_ALL_CONFIGS_PASS` 和 `REQUANT_ROUND64_PROBE_PASS`。

### shared：5 个配置

`tb_prelu_pipeline_shared.sv` 使用独立外部握手 FIFO 与数学参考。三个真实网络组态为 16/2 signed16+PReLU、8/1 signed16+PReLU、4/1 unsigned8；另加 GROUPS=1 的 1/1 和 GROUPS=2 的 4/2。PReLU/Q31 参数在测试中保持静态，匹配模块只锁存 accum 的接口约定。

覆盖双槽填满及 96 拍背压、第三输入稳定保持、输出阻塞保持、槽复用、同时输入/输出、随机输入间隔和随机输出背压、计算在途复位、输出持有时复位。另加 64 组小幅度且各通道不同的数据，避免饱和值掩盖标签错位。

通过标志：5 条 `PRELU_PIPELINE_SHARED_CONFIG_PASS id=` 和 `PRELU_PIPELINE_SHARED_ALL_CONFIGS_PASS`。最终组合还需要真实 B Golden/背压及 C UART 回归。

## 若推断未启用 MREG：下一步备选，尚未实现

不要继续盲目在完整结果后加 FF。可独立尝试显式 16+16 分解，先寄存两项部分积，再重建完整 48 位结果：

```text
H = signed(x[31:16])
L = unsigned(x[15:0])
x = H * 65536 + L
p_hi = H * signed(alpha)                  // signed32
p_lo = signed({1'b0, L}) * signed(alpha)   // signed33
product48 = (sign_extend_48(p_hi) << 16) + sign_extend_48(p_lo)
```

两个乘法均可用单个 DSP 的乘法器容纳，期望仍是每个启用 PReLU 的 lane 两个 DSP；实际数量和 MREG/PREG仍须综合核验。增加的 65 位部分积寄存和一组重建加法会改变布局与资源。与本候选两个完整 48 位结果级相比，部分积65位加完整结果48位在 RTL 中多17个数据寄存位；这些位是否进入 DSP 原语或普通 FF，不能直接由声明数判断。

正确性成本在于：L 必须补零后按 signed17 乘法处理；H 必须保持 signed16；两个部分积必须先扩展到48位再移位/相加；accumulator、multiplier、valid仍需同步；APPLY_PRELU=0 也保持对外延迟一致。此方案必须重新通过全边界、原版延一拍、shared及整网验证，再决定是否进入实现。
