# c_side —— FSRCNN 超分加速器 C 侧 RTL 工程（ACX750-200T）

C 侧（系统集成 / 综合实现 / 板级验证）RTL 骨架。目标：**真实 B RTL 到位后，
只需替换 `rtl/b_core_if.v` 里的 stub 实例，C 侧其余模块不需要重新设计。**

## 设计基线（唯一依据）

| 文档 | 位置 |
|---|---|
| `FSRCNN_ACX750-200T部署任务书_v3.2.2修订执行版` | 上级目录（md 源在 `../output/任务书v3.2.2_修订执行版.md`） |
| `成员B对C架构接口与资源预算确认_v1.1` | 上级目录（**现行版本**，取代 v1.0） |

冻结口径（不得自行改动）：d16/s8/m1/c16、L5 = 单稠密 Conv(16→4,5×5)、
中间激活对称 INT16、权重 INT8、INT32 累加、Q31 requant；C-B 接口 v0.2；
200 MHz 单时钟域；64 行条带双缓冲（**当前基线，非冻结项**）；
**反压合同级保证 N=0**（B v1.1 §八，见 `docs/B_INTERFACE_CONTRACT.md` §3.4）。

## 目录

```
rtl/      c_config.vh    参数单一真源（逐条标注 v3.2.2 出处）
          c_top.v        板级顶层：MMCM 50→200MHz + 复位汇聚 + LED
          c_synth_top.v  综合专用顶层（ROM 用 pattern 初值以保证 BRAM 被真实推断）
          c_core.v       单时钟域集成壳
          c_ctrl.v       start/busy/done 控制框架
          input_rom.v    输入 ROM（19 bit 地址 / 2^19 深 / 同步读 1 拍）
          input_stream.v 输入像素流（in_valid/in_ready/in_data）
          stripe_buffer.v 单个条带 bank
          pingpong_buffer.v 条带 ping-pong 双缓冲 + 交换 + 回读口径
          output_stream.v B→C 输出消费 + 条带/帧边界复算 + out_ready
          uart_tx.v      UART 8N1 发送（波特率参数化）
          readback_ctrl.v UART 静态回读控制
          b_core_if.v    ★ C-B v0.2 冻结端口的唯一落点（stub / 真实 B 切换）
          b_core_stub.v  ★★★ SIMULATION STUB ONLY ★★★（2×2 最近邻，不是 FSRCNN）
          c_protocol_assertions.v  协议断言层 A1~A6（ifdef C_SIM，不进综合）
b_real/   ★ B 真实 RTL 只读镜像（17 个原语，来源 acx750-rtl @ 658c82e2）
          见 rtl/b_real/PROVENANCE.md（含逐文件 SHA-256）
          ※ 只含原语；B 的五层集成 top 尚未交付 ⇒ C_USE_B_REAL 仍为占位
tb/       tb_stripe_buffer.v     条带缓冲模块级定向测试 T1~T6（已 PASS）
          tb_backpressure_rand.v 随机化背压压力测试，3 种子 + 断言层（已 PASS）
          tb_ready_valid.v       小规模定向全链路 A~K 场景（已 PASS）
          tb_c_top.v             全尺寸 1920×1080/STRIPE_H=64 边界测试 + c_top 冒烟（已 PASS）
          tb_b_real_primitives.v ★ 证明接入的是**真 B 原语**而非 C 的 stub
                                 （30 项逐值断言 + 17/17 实例化，已 PASS）
constr/   c_top.xdc             引脚/时钟/复位约束（复用已上板实测基线；UART 引脚待确认）
scripts/  run_sim.tcl           一键跑全部 TB（每个 TB 独立工作目录，无波形 dump）
          synth_check.tcl       **仅综合**取证（不实现/不布局布线/不生成位流）
          synth_b_real.tcl      **B 原语**在目标器件上的仅综合取证（b_real_bench_top）
          impl_check.tcl        **implementation**取证（synth+opt+place+route，仍不生成位流）
          gen_input_mem.py      生成综合/仿真用的 ROM 初始化 .mem
          export_dep_txt.py     由依赖清单 .md 生成纯文本 .txt（CJK 宽字符对齐 + 折行）
report/   综合报告输出目录（utilization_synth.rpt / timing_summary_synth.rpt /
          synth_result.txt 含 C17 十项必录信息）；impl/ 为实现后报告，**口径不同**
docs/     C_IMPLEMENTATION_STATUS.md   ← 实现状态、覆盖度、TODO、下一步
          B_INTERFACE_CONTRACT.md      ← ★ C-B 接口条款（依据 B v1.1，含 N=0 结论）
          BRAM_BUDGET_MAP.md           ← ★ 「192 块」的构成 + 与 B v1.1 分项对齐
          ACCEPTANCE_DATA_DEPENDENCY.md ← ★ 验收数据依赖（960×540 整数 Golden 现状）
          DEPENDENCIES_A_B.md          ← ★ 依赖 A/B 的事项清单（Markdown 源，排期/交接用）
          DEPENDENCIES_A_B.txt         ← 同上**纯文本版**（自动生成，分发给 A/B 用）
```

> 依赖清单的纯文本版由 `.md` 自动生成，**不要手改 .txt**：
> `python scripts/export_dep_txt.py`

## 复现

### 仿真（**五个 testbench** 全部 PASS）

```powershell
# 方式一：一键（推荐）
& vivado.bat -mode batch -source scripts/run_sim.tcl

# 方式二：只跑一个（排查用）
& vivado.bat -mode batch -source scripts/run_sim.tcl -tclargs tb_b_real_primitives

# 方式三：手工（注意每个 TB 用**独立工作目录**）
$bin = "E:\Xilinx\Vivado\2022.2\bin"
$rtl = (Get-ChildItem rtl\*.v | ForEach-Object { $_.FullName })
New-Item -ItemType Directory -Force _sim\myrun | Out-Null; Set-Location _sim\myrun
& "$bin\xvlog.bat" --include ..\..\rtl -d C_SIM --nolog --work worklib @rtl ..\..\tb\tb_ready_valid.v
& "$bin\xelab.bat" worklib.tb_ready_valid --nolog -s tb_sim
& "$bin\xsim.bat" tb_sim -runall      # 期望 "RESULT: PASS  (all A~K scenarios, 0 error)"
```

> ⚠️ **两条硬约束（都踩过坑）**
> 1. **每个 TB 必须用独立工作目录**：多个 snapshot 共用一个 `xsim.dir` 会报
>    `Simulation engine failed to start ... status code -1073741515`。
> 2. **仿真不得与综合/实现并发跑**。实测同一批 5 个 TB 与 `synth_design` 并发时
>    **5/5 全部**在 `Simulation engine failed to start ... -1073741515`
>    （0xC0000135 = STATUS_DLL_NOT_FOUND，环境级抖动，与 RTL/TB 无关）；
>    单独跑则 **5/5 全 PASS**。`run_sim.tcl` 已内建 5/15/30 s 递增退避重试兜底。
> 3. `tb_b_real_primitives.v` 里的 `sync_parameter_rom` 需要
>    `MEM_FILE = "../../rtl/b_real_bench_param.mem"`（**相对 xsim 工作目录**），
>    故必须经由 `run_sim.tcl` 或 `cd` 到 `_sim/<tb>` 后运行。

### 仅综合取证 / 实现取证

```powershell
& vivado.bat -mode batch -source scripts/synth_check.tcl -nojournal -log _syn\vivado_synth.log   # synthesis only
& vivado.bat -mode batch -source scripts/synth_b_real.tcl -nojournal -log _syn\vivado_breal.log  # B 原语（synthesis only）
& vivado.bat -mode batch -source scripts/impl_check.tcl   -nojournal -log _syn\vivado_impl.log    # implementation（无位流）
```

**磁盘安全约定**：不 dump 波形（无 `$dumpvars`）；TB 只用小规模/内存数组；
所有 testbench 均有硬 timeout；构建产物（`_sim/`、`_syn/`、`report/*.rpt` 之外、
`*.log`、`*.jou`、`*.dcp`、`*.bit` 等）已被 `.gitignore` 忽略。

## 表述纪律（重要）

- 完整设计**尚未综合完成实现**，本仓库**不得**出现 Fmax / FPS 的实测数字。
- **synthesis-only** 口径（`report/synth_result.txt`）：RAMB36 192/365 = 52.60%、
  DSP48E1 0、WNS −0.1 ns、0 ERROR / 0 CRITICAL WARNING。含 stub，**不是完整 FSRCNN**，
  未做 place/route，**不得**据此宣称「200 MHz 已收敛」或任何 Fmax。
- **implementation** 口径（`report/impl/impl_result.txt`）：与上面**是两个不同口径，
  不得互相引用**；两套数字必须各自带「synthesis / post-route」标签 + commit SHA。
- BRAM 现状（§五.13 两级，不可混谈）：
  - **一级 理论预算**：口径分歧已澄清 —— 任务书 v3.2.2 口径② ≈1406.6 KiB **未闭合**；
    但 **B v1.1 §五 的物理 RAMB36 口径**理论 1219.5 KiB、用 C 实测值替换后 1242.0 KiB，
    **在 85% 线（1395.0 KiB）内**。两口径差异 = 「按字节」vs「按物理块向上取整」+ 是否计 40 块预留。
    详见 `docs/BRAM_BUDGET_MAP.md` §3.1。
  - **二级 实际资源**：C 侧骨架实测 192/365，但**不含 B 侧 42+2 块**与 40 块预留；
    故**只能**写「按 v1.1 物理块口径**外推**在 85% 线内（余量 ≈34 块）」，
    **不得**写「BRAM 已闭合」。
- `b_core_stub.v` 的输出是**测试 pattern**，**不是算法结果**，不得用于 PSNR/效果结论。
- UART 属**离线静态回读**，**不得**用其传输时间推断实时 FPS。
