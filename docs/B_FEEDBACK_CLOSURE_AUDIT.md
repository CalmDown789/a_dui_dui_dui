# B 反馈闭环修订 —— 审计表

> **后续状态（2026-09-23）**：本文的 7 项闭环和 `5/5 PASS` 是当时 C+stub /
> B 原语基线的历史记录。真实 B 五层 RTL `ae29515` 已进入正式路径，
> 但在 XSim 2022.2 下逐字节验收 FAIL。最新证据与判定见
> `B_REAL_BITEXXACT_MISMATCH_HANDOFF.md` 和 `B_C_REAL_ACCEPTANCE_REPORT.md`。

> **本轮范围**：针对「B 反馈闭环修订」的 7 项要求，逐条核对现有 C 侧实现并补齐**可复现证据**。
> **明确不做**：不重新设计架构；不改冻结口径；不生成 bitstream；不宣任何 Fmax / FPS。
>
> **基线**：`任务书 v3.2.2 修订执行版` + `成员B对C架构接口与资源预算确认_v1.1`（现行）
> **仓库 / 分支**：`srtp/c_side` @ `main`
> **审计日期**：2026-09-23
> **工具 / 器件**：Vivado 2022.2 (win64) / `xc7a200tfbg484-2`
>
> 状态图例：`[已解决]` 本轮闭合 ｜ `[未解决]` 本轮明确不做或做不完 ｜
> `[依赖B确认]` 卡在 B 的书面答复 ｜ `[依赖A提供]` 卡在 A 的书面确认

---

## 一、7 项逐条审计

### ① 澄清 `b_core_if` ↔ 真实 B 的契约（IMGW / IMGH / STRIPEH）

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`**（就「C 侧能把话说清楚」而言）；**`[依赖B确认]`**（就「端口逐字一致」而言） |
| 结论 | **B v1.1 的 C-B 接口里不存在 IMGW/IMGH/STRIPEH，也不存在任何尺寸总线。** §九「C-B v0.2 冻结矩阵」把 960×540 / 1920×1080 / 64 行条带列为**已冻结常量**；尺寸量在 **elaboration 期**生效，**无运行时尺寸握手** |
| C 侧定位 | `b_core_if.v` 的 5 个 parameter（`IMG_W/IMG_H/OUT_W/OUT_H/STRIPE_H`）是 **C 的内部便利**（供 TB 小规模例化），**不是双方契约的一部分**，不得假设真实 B 会读 |
| 证据 | `docs/B_INTERFACE_CONTRACT.md` §一 / §二（13 个端口逐条照抄 §六 表 8）/ §三 |
| 仍开放 | 🔴 **B-IF-1** 真实 B 顶层**模块名**；**B-IF-2** 端口名与顺序是否与表 8 逐字一致；**B-IF-3** B 是否要求几何参数化 |

---

### ② 确认真实 B 已在 C 的仿真 + 综合文件列表内

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`** |
| 做法 | 三个入口脚本**都显式 `read_verilog` 了 B 的 17 个真实 RTL 文件**（含 2 个 `.sv`，故用 `-sv`），文件缺失即 `error` 中止 |
| 脚本 | `scripts/run_sim.tcl`（仿真）、`scripts/synth_check.tcl`（仅综合）、`scripts/impl_check.tcl`（实现） |
| **诚实边界** | `c_synth_top` **只读入、不实例化** B 的原语 ⇒ **不改变**资源数字。目的仅是让「B 真实 RTL 已在工程文件列表内」成为**可复现事实**，而非文档声明 |
| 更强的证据 | `tb/tb_b_real_primitives.v` 把 17 个原语**真实例化**并做 **30 项逐值断言**（含独立重算 LCG 校验参数 ROM），**已 PASS** — 见 `report`/`_sim` 日志；`scripts/synth_b_real.tcl` 把 17 个原语在**目标器件**上真正综合一次（顶层 `b_real_bench_top`） |
| 为什么必须这样做 | B 本机 Vivado 2025.2 **缺 `xc7a200tfbg484-2` 器件数据**（B 的 `synthesis_status.md` 记录 `No parts matched`），只在 xc7z020 上跑过 fallback ⇒ 目标器件上的结构/资源/时序证据由 **C 侧补齐** |

---

### ③ 重跑 仿真 + 综合 + 实现 取证，且 synthesis 与 implementation 必须分开

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`** |
| 仿真 | **5 / 5 TB 全部 PASS**（`tb_stripe_buffer`、`tb_backpressure_rand`、`tb_ready_valid`、`tb_c_top`、`tb_b_real_primitives`）；结果文件 `report/sim_result.txt`（**入库**） |
| synthesis | 单独脚本 `scripts/synth_check.tcl`，**只调 `synth_design`**，不 opt/place/route |
| implementation | 单独脚本 `scripts/impl_check.tcl`，`synth_design → opt_design → place_design → phys_opt_design → route_design`，**仍不生成 bitstream** |
| 两口径纪律 | 两个脚本**互不引用**，各自结果文件都带口径标签 + commit SHA；实现脚本内再分 **Flow-A**（`flatten_hierarchy none` → **逐模块资源**）与 **Flow-B**（默认 flatten → **代表性实现时序**）。仅综合脚本则显式用 **`rebuilt`**（并已在结果文件第 3b 项写明，见 §2.2 脚注） |
| 实测数据 | 见 §二 |

---

### ④ 把「192 块」与 B 的 271 预算对齐

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`**（并**纠正了一个口径错误**） |
| 先纠正 | 原稿把 B v1.1 的「**127**」误标为「**B 侧参数 ROM**」，据此外推出 403 块 —— **错**。127 是 **C 输入 ROM**（B 自己的数），而 **B 参数 ROM = 0 块**（v1.1 §五 表 7，走 LUTROM） |
| 正确外推 | **192（C）+ 42（B 行缓存）+ 2（相位 bank）+ 0（B 参数 ROM）+ 40（系统预留）= 276 RAMB36** = 1242 KiB = **75.62%** < 85% 线（310 块 / 1395 KiB），**余量 ≈ 34 块** |
| 为什么 C 实测 64 而 B 估 60 | 两个口径**都正确**：B 按 30+30 假设，C 实测 32+32（`120K×8` BRAM 映射的向上取整维度不同） |
| 证据 | `docs/BRAM_BUDGET_MAP.md` §2 / §2.1（含负面证据留档）/ §3 / §3.1 / §3.2 |
| 表述红线 | 只能写「**C 侧骨架部分在 85% 预算线内**」+「按 v1.1 物理块口径**外推**在预算线内」；**不得**写「BRAM 已闭合」 |

---

### ⑤ 审计并更新 C 侧 v1.0 → v1.1 引用

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`** |
| 做法 | 全仓 `grep -rn "v1\.0"` 逐条判定，**8 处**由 `确认_v1.0` 升级为 `确认_v1.1`（引用条款号在 v1.1 中均存在，故只换版本不换条款） |
| 涉及文件 | `rtl/c_config.vh`、`rtl/b_core_if.v`、`docs/DEPENDENCIES_A_B.md`（5 处）、`docs/C_IMPLEMENTATION_STATUS.md`（2 处） |
| 保留 v1.0 字样的地方 | 仅**显式说明版本沿革**的句子（如 `c_config.vh` 第 8~9 行「v1.1 = 现行版本，取代 v1.0」），**故意保留** |
| 顺带闭合 | `c_config.vh` 的 `TODO(B_CONFIRM)` 由「B-ARCH-10 七项待给」改为 **「最大连续 back-pressure 周期 N = 0（合同级保证）」**（B v1.1 §八）；其余 9 个 RTL/TB 文件的 v1.0 引用同步更新 |

---

### ⑥ 记录 960×540 整数 Golden 的依赖（A 提供 vs 被 revert）

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`**（留档 + 校验）；**`[依赖A提供]`**（权威性确认） |
| 已取得 | A 在 `member-a` @ `98c82f394bdfba85bc2959bede9760edc4d6862f` 的 `artifacts/full_integer_golden/` 提供 **9 个文件**，本机已抽取到 `ref/a_full_integer_golden/` 并 **9/9 通过 SHA-256 复核**，与 A 的 `manifest.json` 逐条一致 |
| ⚠️ 关键事实 | 该提交**已被 revert**：远端 `main` tip = `2dbb8c7 Revert "feat(member-a): add full-frame integer golden"`，`main` 树中该路径 = **0 文件** ⇒ 留档**不是权威定版** |
| 顺带纠正 | `quant_params.json` 的 **13029 B（LF）/ `f2a9f20c…b77a`** 与 **13557 B（CRLF）/ `9a53d2e3…34b`** 是**同一份文件**（差 528 行行尾），**不是两个版本**；A 的 manifest 声明的正是 LF 口径 |
| 另发现 | 两个交付 ZIP 内**都没有** Golden（`full_integer_golden` 条目 = 0/0），说明它是**独立于 ZIP 的一次性追加** |
| 证据 | `docs/ACCEPTANCE_DATA_DEPENDENCY.md`（§二 清单 / §3.1 revert / §3.2 行尾 / §3.3 ZIP / §四 行动项 / §五 校验 SOP）；`scripts/verify_golden.py`（可执行复核，退出码 0/1/2） |
| 仍开放 | 🔴 **A-G-1** 澄清既有书面确认的正式发布位置并说明为何被 revert；**A-G-2** 生成条件；**A-G-4** 是否重新发布 |

---

### ⑦ 产出审计表 + 提交

| 项 | 结论 |
|---|---|
| 状态 | **`[已解决]`** |
| 本文件 | 即审计表 |
| 提交 | 见 §五「提交记录」 |

---

## 二、本轮实测数据（三个口径，**不得互相引用**）

### 2.1 仿真（`scripts/run_sim.tcl`）

| TB | 结果 |
|---|---|
| `tb_stripe_buffer` | PASS |
| `tb_backpressure_rand` | PASS |
| `tb_ready_valid` | PASS |
| `tb_c_top` | PASS |
| `tb_b_real_primitives` | PASS（17/17 原语例化 + 30 项断言） |
| **合计** | **5 / 5 PASS** |

> 📄 **证据文件**：`report/sim_result.txt`（**本轮新增**，由 `run_sim.tcl` 第 5 节写出）。
> 纯 ASCII 标签，含 commit SHA / 生成时间 / 未提交改动 / 逐 TB 判定。
> 原始日志 `_sim/<tb>/xsim.log` **已 gitignore**（体积大、可再生）。
> ∴ 在本轮之前，**仿真证据并不在仓库内**（见缺陷 #10）。

> ⚠️ **`-1073741515` 的真因（本轮定位并实测，**替换**旧归因）**：
> 该错误码是 `0xC0000135 = STATUS_DLL_NOT_FOUND`，根因是 **xsimk.exe 的运行库闭包缺失** ——
> 它只导入 `KERNEL32.dll / msvcrt.dll / librdi_simulator_kernel.dll`，而最后这个 Vivado 库
> （`<XILINX_VIVADO>/lib/win64.o/`）没有被放到快照目录旁；`xelab` **每次重建**该目录，
> 故上一轮放进去的会被清掉。解析 PE 导入表得到的**最小非系统闭包 = 13 个 DLL / 7.9 MB**
> （`librdi_simulator_kernel` / `librdizlib` / `tcl85t` / 6 个 `libboost*` + `MSVCP140` /
> `VCRUNTIME140` / `VCRUNTIME140_1`）。`run_sim.tcl` 的 `patch_xsim_dlls` 已按**位置**补齐，
> 实测 **5/5 全 PASS**。两条反直觉实测：**只把 `lib/win64.o` 加进 `PATH` 无效**；
> **MinGW 的 8 个运行库不在闭包内**（旧说法有误）；「每 TB 独立工作目录」**也不能**阻止该错误。
>
> ❌ **旧归因作废**：本节此前写「并发时 5/5 全部崩溃、单独跑则全 PASS」并据此断言
> 「**并发**导致 0xC0000135」。该因果链**已被上述测量否证**（是缺 DLL，不是并发）。
> 加固后**未复测**并发场景，故：并发仍**不建议**（CPU/磁盘/日志干扰，属**工程纪律**），
> 但**不得**再把它写成该错误的原因。`scripts/run_sim.tcl` 的头部注释、重试注释与此处已同步更正。

### 2.2 仅综合（`scripts/synth_check.tcl`，顶层 `c_synth_top`，`-flatten_hierarchy rebuilt`）

| 资源 | 值 | 上限 | 占比 |
|---|---|---|---|
| RAMB36/FIFO | **192** | 365 | **52.60%** |
| RAMB18 | 0 | 730 | 0% |
| DSP48E1 | **0** | 740 | 0% |
| Slice LUTs | 3,723 | 134,600 | 2.77% |
| Slice Registers | 8,190 | 269,200 | 3.04% |
| WNS @200 MHz | **−0.153 ns** | — | 失败端点 **3 / 20,786** |
| WHS | +0.127 ns | — | 失败 0 |
| ERROR / CRITICAL WARNING | **0 / 0** | — | — |

> ⚠️ **三种 flatten 口径，不得混用**：本表来自 `synth_check.tcl`，用的是
> **`-flatten_hierarchy rebuilt`**。另两种在 `impl_check.tcl` 里：
> **Flow-A = `none`**（唯一能给出**逐模块**资源的口径，见下表）与
> **Flow-B = 默认（`full`）**（唯一带布局布线延迟的口径）。
> `none` 会阻止跨模块优化，逻辑资源因此偏高；`rebuilt` / `full` 把层次打平后
> **无法逐模块拆账**。三者的数字**不得互相引用**。

> ✅ **交叉验证（本轮得到的一条有力证据）**：`report/impl/impl_result.txt` 里
> **Flow-B 的综合级**数字与本节**逐项完全一致** —— WNS `−0.153 ns`、TNS `−0.377 ns`、
> 失败端点 `3 / 20,786`、WHS `+0.127 ns`。即 **`rebuilt`（本脚本）与默认 `full`（Flow-B）
> 在本设计上给出同一张网表**，两条互不引用的入口互相印证。
> 由此也可判定：§2.3 的 **3 / 20,502**（Flow-A，`none`）与本节的 **3 / 20,786** 之差
> **只来自 flatten 口径**，不是运行间随机波动。

> ℹ️ 上表 **TNS = −0.377 ns**、失败端点 **3 / 20,786**、WHS 失败 **0**，
> 均与 `report/timing_summary_synth.rpt` 的 Design Timing Summary 数据行**同源**
> （结果文件第 3b 项同时自证 `flatten_hierarchy = rebuilt`）。

**RAMB36 = 192 的逐模块构成**（`report/impl/util_synth_A_hier_none.rpt`，Flow-A `flatten none`）：

| 实例 | 模块 | RAMB36 | LUT | FF |
|---|---|---:|---:|---:|
| `u_rom` | `input_rom` | **128** | 24 | 3 |
| `u_pp` | `pingpong_buffer` | **64** | 171 | 56 |
| ⠀└ `u_bank0` | `stripe_buffer` | 32 | 44 | 1 |
| ⠀└ `u_bank1` | `stripe_buffer` | 32 | 44 | 1 |
| `u_b` | `b_core_if` → **`b_core_stub`** | **0** | **3,290** | **7,794** |
| `u_core` 其余（ctrl/in/out/rb/uart） | — | 0 | 126 | 140 |
| **合计** | | **192** | 3,626 | 8,048 |

> 🔎 **重要观察**：**stub 吃掉 3,290 LUT / 7,794 FF（≈ 90% 的逻辑资源）但 0 块 BRAM**。
> 即当前 LUT/FF 数字**几乎全是 stub 的**，与 C 侧基础设施无关；真实 B 替换后应大幅变化。
> **BRAM 部分与 B 无关**（128 + 64 全部是 C 侧 ROM 与条带双缓冲）。

### 2.3 实现（`scripts/impl_check.tcl`，**post-route**，不生成位流）

| 项 | Flow-A（`flatten none`，仅综合） | Flow-B（默认 flatten，**实现后**） |
|---|---|---|
| WNS | −0.153 ns | **−2.749 ns** |
| TNS | −0.377 ns | **−25,008.076 ns** |
| 失败端点 | 3 / 20,502 | **17,766 / 20,906** |
| WHS | +0.127 ns | +0.067 ns（失败 0） |
| RAMB36 | 192 / 365 | **192 / 365（52.60%）** |
| RAMB18 | 0 | 0 |
| DSP48E1 | 0 | **0 / 740** |
| Slice LUTs | 3,626 | 3,762（2.81%） |
| Slice Registers | 8,048 | 8,252（3.07%） |
| 布线 | — | **全布线成功，routing errors = 0**（10,619 / 10,619 可布线网络） |

**最差路径（post-route）**：

```
Slack (VIOLATED) : -2.749 ns
  Source      : u_top/u_core/u_b/u_b_core/out_x_reg[4]/C          ← stub 内部
  Destination : u_top/u_core/u_pp/u_bank1/mem_reg_1_3/DIADI[0]    ← 条带 bank1 的 BRAM 数据输入
  Requirement : 5.000 ns
  Data Path Delay : 7.104 ns  (logic 1.479 ns = 20.8% ; route 5.625 ns = 79.2%)
  Logic Levels : 5  (LUT6×2, MUXF7×2, MUXF8×1)
  Clock Path Skew : -0.216 ns  (DCD 5.335 / SCD 5.763 ns)
```

> 🔎 **如何正确解读（关键，别读成设计缺陷）**：
> 1. **违例是布线主导，不是逻辑深度主导** —— 逻辑只占 **1.479 ns / 5 级**，布线占 **79.2%**。
>    在只用了 **12.83% slice** 的空器件上出现 5.6 ns 的走线延迟，属**布局/约束质量**问题
>    （无 floorplan、无 I/O 时序约束、MMCM 位置未约束 ⇒ 时钟插入延迟高达 ~5.5 ns），
>    **不是** RTL 组合逻辑过深。
> 2. **失败路径的起点在 stub 内部**（`u_b_core/out_x_reg[4]`），终点是 C 侧条带 BRAM。
>    真实 B 替换 stub 后该路径拓扑改变，必须**重测**。
> 3. **synthesis 与 post-route 的数字差距巨大（−0.153 → −2.749）**，这正说明
>    **两个口径绝不能互相引用**：综合级不含布局布线延迟与时钟树效应。
> 4. 🚫 **不得**由本结果推 Fmax，**不得**写「200 MHz 未收敛/已收敛」之外的任何量化结论；
>    本轮**未做任何时序收敛努力**（未调 opt/place 策略、未加 floorplan、未做时序驱动综合），
>    时序闭合**不在本轮范围内**。

**时钟（`report/impl/clocks_postroute.rpt`）**：`sys_clk` 20 ns → MMCM 生成 `u_top_n_0` **5.000 ns（200 MHz）**，
`g_mmcm.clkfb` 20 ns；**User Uncertainty / User Jitter 均为空**（仅用工具默认抖动）。

### 2.4 B 原语在目标器件上的仅综合（`scripts/synth_b_real.tcl`）

顶层 `b_real_bench_top`（17 个原语全部实例化），报告在 `report/b_real_synth/`。

| 资源 | 值 | 上限 | 占比 |
|---|---|---|---|
| **DSP48E1** | **127** | 740 | 17.16% |
| Slice LUTs | 4,083 | 134,600 | 3.03% |
| Slice Registers | 3,980 | 269,200 | 1.48% |
| LUT as Memory | 576 | 46,200 | 1.25% |
| Block RAM Tile | 6 | 365 | 1.64% |
| ⠀└ RAMB36 / RAMB18 | 1 / 10 | 365 / 730 | — |
| WNS @200 MHz（综合级） | **−5.353 ns** | — | — |

**DSP 的逐原语归属**（`utilization_hier.rpt`，**本表信息量最大**）：

| 实例 | 原语 | DSP |
|---|---|---:|
| `u_c5` / `u_c5u` | `conv5x5_backend` / `conv5x5_u8s8_backend` | 25 / 25 |
| `u_d25` / `u_d25u` | `dot25_pipeline` / `dot25_u8s8_pipeline` | 25 / 25 |
| `u_c3` | `conv3x3_backend` | 9 |
| `u_d9` | `dot9_pipeline` | 9 |
| `u_pr` | **`prelu_requantize`** | **6** |
| `u_c1` | `conv1x1_backend` | 1 |
| `u_sm` / `u_u8` | `dsp_signed_mult` / `dsp_u8s8_mult` | 1 / 1 |
| `u_w3s`/`u_w3b`/`u_w5s`/`u_w5b` | 窗口原语 | 0（RAMB18 = 1/3/1/5） |
| **合计** | | **127** |

> 🔎 **对 B 的 370 DSP 预算最有价值的一条**：`dot25_*_pipeline` 在 **`ACT_W=8 / WGT_W=8`** 的参数
> （即 C 侧基准的例化方式）下 **固定吃 25 个 DSP**，也就是 **1 抽头 = 1 DSP，未做双 INT8 打包**。
> 这正好落在本项目的 DSP 打包口径问题上（乘法器端口为 25×18 位，`a1` 只有 4 位，
> 「两个完整 INT8 MAC/DSP」不成立）。**这是给 B 的一手证据，也是必须提前对齐的点。**

> ⚠️ **边界声明（必须随数据一起给 B）**：
> 1. 这是**原语集合**的 synthesis 级数据，**不是**五层网络、**不是**系统级结论，
>    **不得**据此宣称或推翻 B v1.1 的 **271 RAMB36** 系统预算；
> 2. `b_real_bench_top` 的输入**直接来自器件端口**（只 `create_clock`，无 `set_input_delay`），
>    所以 −5.353 ns **反映的是原语组合深度**，**不是**系统 Fmax；
> 3. 未做 place/route，未生成位流；
> 4. 本数据补上了 B 侧的一个缺口：B 本机 Vivado 2025.2 **无 `xc7a200tfbg484-2` 器件数据**
>    （B 的 `docs/synthesis_status.md` 记录 `No parts matched`），只在 xc7z020 上跑过 fallback
>    ⇒ **目标器件上的首份综合数据由 C 侧提供**。

---

## 三、本轮新发现并修复的缺陷

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | `synth_b_real.tcl` 只跑 13 s 就退出，报告全缺 | `create_clock -period 5.000 [get_ports clk]` 放在 `synth_design` **之前** —— 此时设计未 elaborate，`get_ports` 找不到对象 ⇒ `ERROR [Common 17-53] No open design`。（`read_xdc` 可以在前，因为它只**挂起**约束给下一次 `synth_design`；`create_clock` 是**立即执行**命令） | 把 `create_clock` 移到 `synth_design` **之后**；脚本内加注释说明这一区别 |
| 2 | `impl_check.tcl` 跑完 8.5 分钟后中途 `invalid command name "Flow"`，`impl_result.txt` 被截断 | **方括号陷阱的第 2 个落点**：上一次只改了**控制台** `puts`，漏了**写结果文件**的 `puts $rf " [Flow A] ..."`（双引号内 `[...]` 触发命令替换）。**修完仍是 4 处只生效 1 处**（见 #7），需再修 3 处 | 去掉 `[Flow A]`/`[Flow B]` 方括号，改写成 `Flow-A` / `Flow-B`；**并写了一个只扫双引号字符串内部的 lint 脚本作为硬门禁**（165 条 puts 行 → 违规 0）；把规则**精确表述**为「**双引号串内的 `[...]` 一定会被当命令执行**，所以其中内容必须是**你真想在此刻执行的命令**」——**不是**「不许出现方括号」（`[version -short]`、`[clock format …]` 就是合法的**故意**替换）；lint 用**白名单**认定合法替换，其余一律报错（**宁可误报也不漏报**，方向安全）。**该门禁已入库为 `scripts/lint_tcl.py`**：`--selftest` 自检 13 例（含一条逼真的坏脚本），对 `run_sim.tcl` / `synth_check.tcl` / `impl_check.tcl` / `synth_b_real.tcl` 四者 **LINT CLEAN** |
| 2b | `report/b_real_synth/synth_result.txt` 里 `constraint` 字段写成 `create_clock -period 5.000 clk`（丢了 `[get_ports clk]`） | **同一陷阱的第 3 个落点**：`puts $rf "... [get_ports clk]"` 里 `[get_ports clk]` 被**真的执行**了；因为当时已有 open design 所以**没报错**，只是把结果文本 `clk` 写了进去 —— **静默写错**，比报错更危险 | 转义为 `\[get_ports clk\]`；并把「描述命令的文本」也纳入 lint 范围 |
| 3 | 报告里 WNS 被写成 **`-0.1`**（真值 `-0.153`） | **Tcl ARE 的 `.` 默认匹配换行**（与 Python 相反），使 `.*?` 走到另一条回溯路径、给出更短匹配。四组对照实验定位：`.*?`+`\d`→`-0.1` ❌｜`.*?`+`[0-9]`→`-0.1` ❌｜`[^\n]*`+`\d`→`-0.153` ✅｜`[^\n]*`+`[0-9]`→`-0.153` ✅ ⇒ **元凶是 `.*?`** | 三个脚本的跨行正则统一改为显式 `[^\n]*`；数值改用 `[0-9]+\.[0-9]+`（拒绝 `1.2.3` 畸形串） |
| 4 | 生成的 `*_result.txt` 中文变**双重编码乱码** | Tcl 按**系统码页（GBK）**解码脚本源码，中文字面量在内存里已损坏，`fconfigure -encoding utf-8` **修不了这一层** | 结果文件一律**纯 ASCII 标签**；中文叙述移到 `docs/` 的 `.md`。顺带把脚本里中文的 `error`/`puts` 消息也改 ASCII |
| 5 | 脚本注释里的错误归因 | 曾写「`flatten_hierarchy none` 会显著恶化时序，none = −3.098 ns」—— **错**：−3.098 是一次**实现后**数值，被误记成 flatten 的代价 | 复跑实测两条流程的**综合级 WNS 完全相同（−0.153 ns）**；注释已改正 |
| 6 | 文档里 5 处 `v1.0 → v1.1` 修改**被静默回滚**（第一次改完 grep 复查时发现仍是 v1.0） | **工具层坑**：在同一条消息里对**同一个文件**并发发起多个 `Edit`，发生「读快照 → 改 → 写」交错，**后写覆盖先写**，先写的修改丢失。实测两批共丢 8 处中的 7 处 | 改为**一次性 Python 脚本原子替换**，并对每条替换断言「**恰好命中 1 次**」（既防止覆盖，也防止误伤那些**故意**保留 `v1.0` 的版本沿革句）。**规则：同一文件的多次编辑必须串行，或合并为一次原子写入** |
| 7 | `synth_check.tcl` / `impl_check.tcl` 生成的 `*_result.txt` 曾全部是乱码 | Tcl 以**系统码页 GBK** 读取 `.tcl` 源码 ⇒ 中文字面量**在内存里就已损坏**，`fconfigure -encoding utf-8` **修不了这一层**（这是最容易走的错误修法） | 结果文件**纯 ASCII**；中文叙述移到 `docs/*.md`（由编辑器/Python 写）；脚本内中文 `error` 消息一并 ASCII 化 |
| 8 | 入库的 `report/synth_result.txt` 里 WNS 仍是**被截断的 `-0.1`**（真值 `-0.153`），而脚本里的正则**早已改成 `[^
]*`** | **「修脚本」≠「修产物」**：改完正则**没有重跑**，于是报告里留着一个「修好之前」的数 —— 这类**陈旧产物**比错误本身更隐蔽，因为它看起来「有据可查」 | 重跑 `synth_check.tcl` 刷新该文件；并给结果文件**新增 TNS / 失败端点**字段，使其与 §2.2 表格**同源自证**，不再依赖从 `timing_summary_synth.rpt` 另行摘抄 |
| 9 | `synth_result.txt` 第 3 项把策略写成 `$synth_strategy (synth_design default)`，而脚本实际调用的是 `synth_design ... -flatten_hierarchy rebuilt` | **标签与代码不符**：`rebuilt` 并非 `synth_design` 的默认值（默认 `full`）；该括号措辞会让人误以为走的是默认流，进而**误判**资源数字的可比性 | 删去误导性的 `(synth_design default)`，**新增第 3b 项显式写明 `flatten_hierarchy = rebuilt`**，并在 §2.2 加「三种 flatten 口径不得混用」脚注 |
| 10 | 仿真证据**从未入库**：`run_sim.tcl` 只把 PASS/FAIL 打到 stdout，而原始日志又落在已 gitignore 的 `_sim/` | **取证链路不完整**：三项取证里综合与实现都有 `report/*_result.txt` 入库，**只有仿真无任何仓库内凭证**，等于「5/5 PASS」只能靠转述 | 给 `run_sim.tcl` 增加第 5 节，写出 `report/sim_result.txt`（纯 ASCII，含 commit SHA / 生成时间 / 未提交改动 / 逐 TB 判定），并重跑一次；原始日志仍不入库（可再生） |
| 11 | xsim 引擎反复以 **`-1073741515`**（STATUS_DLL_NOT_FOUND）起不来，脚本注释把它归因为「杀软扫描快照 DLL / 上一轮残留」，并靠 5/15/30 s 退避重试兜底 | **归因错误**：真因是 xsimk.exe 的导入库 **`librdi_simulator_kernel.dll`**（`<XILINX_VIVADO>/lib/win64.o/`）**没有被放到快照目录旁**，而 `xelab` **每次都重建该目录** ⇒ 上一轮放进去的会被清掉。解析 PE 导入表得到的**最小闭包只是 13 个 DLL / 7.9 MB**（含 `libboost*` 与 MSVC 运行库）；**MinGW 的 8 个运行库并不在其中**（此前说法有误） | `run_sim.tcl` 的 `patch_xsim_dlls` 改为按**位置**把这 13 个放到 `xsimk.exe` 旁，并在 elaborate 之后调用 —— 实测 **5/5 全 PASS**。另实测两条反直觉结论：**只把 `lib/win64.o` 加进 PATH 无效**；「每 TB 独立工作目录」**也不能**阻止该错误 |
| 12 | **同一个文件里存在两套互相矛盾的归因**：`run_sim.tcl` 头部「设计要点」1 / 5 与它自己生成报告里的 `NOTE 2`，仍在说 `-1073741515` 是「并发才失败」「环境级抖动、重试无效」；而同一文件下方的 `patch_xsim_dlls` 头注释已按实测建立**正确**归因（缺 DLL 闭包）。读者会**先看到错的那一套** | **修 A 处漏 B 处**（与缺陷 #2 / #8 同族）：只改了新增章节，没回头清理**同一事实的旧副本**。同一事实在文件里有多份副本时，**必须一次性全部对齐**，否则文档自相矛盾，且**旧副本的位置往往更显眼** | 三处一并对齐：头部「设计要点 1 / 5」（点 1 明确「独立工作目录**不能**修此错误」；点 5 改为 DLL 闭包真因 + 显式写「并发归因**作废**、加固后未复测」）、报告 `NOTE 2`（降级为 **POLICY ONLY** 并标 **RETRACTED**）、重试链注释（注明「退避**不是**该错误的解，缺 DLL 时重试 4 次同样全败」）；启动脚本 `_run_sim_final.ps1` 的注释同步更正 |

---

## 四、仍开放的事项（诚实清单）

| 编号 | 事项 | 归属 | 阻塞什么 |
|---|---|---|---|
| **B-1** | 真实五层 RTL（`b_core_real`） | 🔴 B | **整链验收主路径**；也是替换 stub、重测时序的前提 |
| **B-IF-1/2/3** | 真实 B 顶层模块名 / 端口逐字一致 / 是否参数化 | 🔴 B | `C_USE_B_REAL` 分支能否启用 |
| **A-G-1** | 书面确认全尺寸整数 Golden 权威性 + 说明为何被 revert | 🔴 A | **C8** 的验收效力 |
| **A-G-2** | Golden 生成条件（输入来源 / checkpoint 哈希 / 量化参数版本 / 后处理） | 🔴 A | C8 的可复现性 |
| **时序闭合** | 本轮**未做任何收敛努力**（无 floorplan、无 impl 策略调优、无时序驱动综合） | 🟨 C（下一轮） | 只能在 B-1 到位后一起做才有意义 |
| **C8 比对脚本** | PC 端逐字节比对 `output_1920x1080_y_u8.bin` | 🟨 C | 需 B-1 提供 FPGA 输出才有得比 |
| **ILA / 上板** | 静态回读链路的上板验证 | 🟨 C | 本轮明确不做 |

**不得越界的表述（重申）**：
- 🚫 不得写「完整 FSRCNN 已收敛 / 已实现 / 已上板」；
- 🚫 不得由 §2.3 推 Fmax 或 30 fps；
- 🚫 不得写「BRAM 已闭合」（只能写「C 侧骨架在预算线内」+「外推在预算线内」）；
- 🚫 不得写「C8 已通过」（需 A-G-1 + B-1）；
- 🚫 `b_core_stub` 的输出是**测试 pattern**，不得用于 PSNR / 效果结论。

---

## 五、证据索引与提交记录

### 5.1 证据索引

| 类别 | 文件 |
|---|---|
| 仿真结果 | `report/sim_result.txt`（**入库**，由 `run_sim.tcl` 写出） |
| 仿真原始日志 | `_sim/<tb>/xsim.log`（由 `run_sim.tcl` 生成，**已 gitignore**，可再生） |
| 仅综合报告 | `report/utilization_synth.rpt`、`report/timing_summary_synth.rpt`、`report/synth_result.txt` |
| 实现报告 | `report/impl/utilization_postroute.rpt`、`timing_summary_postroute.rpt`、`worst_path_postroute.rpt`、`ram_utilization_postroute.rpt`、`route_status.rpt`、`clocks_postroute.rpt`、`drc_postroute.rpt`、`impl_result.txt` |
| 逐模块资源 | `report/impl/util_synth_A_hier_none.rpt`（Flow-A） |
| B 原语仅综合 | `report/b_real_synth/*` |
| 报告文本 | `docs/C_IMPLEMENTATION_STATUS.md`、`docs/BRAM_BUDGET_MAP.md`、`docs/B_INTERFACE_CONTRACT.md`、`docs/ACCEPTANCE_DATA_DEPENDENCY.md`、`docs/DEPENDENCIES_A_B.md` |
| 复核脚本 | `scripts/verify_golden.py` |
| 门禁脚本 | `scripts/lint_tcl.py`（Tcl 方括号硬门禁；`--selftest` 13 例自检） |

### 5.2 提交记录

| 项 | 值 |
|---|---|
| 本轮提交 | **三个**提交（见 `git log -3`）：<br>① `b268ff9` = B 反馈闭环 7 项主体（RTL / 脚本 / 文档）；**`synth_result.txt` 的陈旧值刷新、flatten 标签修正（缺陷 #8 / #9）与 `.gitignore` 也在这一提交里**<br>② = **仅证据**：`report/sim_result.txt` 首次入库、审计表缺陷 #10 / #11 / #12、`run_sim.tcl` 的归因对齐与 DLL 补位<br>③ = 入库方括号硬门禁 `scripts/lint_tcl.py`（缺陷 #2 的预防）<br>②③ 均**不动任何 RTL、不动冻结参数** |
| 报告的生成基点 | 每个证据文件都**自证**了生成时的 HEAD 与未提交改动清单，三者基点**不同**，不得混引：<br>· `impl_result.txt` 第 9 / 11 项 → HEAD `0632b33`（**早于** `b268ff9`）<br>· `synth_result.txt` 第 8 / 10 项 → HEAD `0632b33`（同上；本轮**重跑刷新**，剔除了陈旧 `-0.1`）<br>· `sim_result.txt` 第 4 / 6 项 → HEAD `b268ff9`（即①提交之后、②提交之前） |
| 对应关系 | ① `b268ff9` 的内容 = `0632b33` + 该次提交的改动 ⇒ 综合/实现两份报告的基点落在 ① 上；仿真报告晚一次提交，基点落在 ①。②③ 只增删 evidence / 文档 / 工具，不改变任何被综合或仿真的对象 ⇒ 三份证据对**同一份 RTL** 成立（RTL 在 ①②③ 之间**零改动**；由 `git diff --stat b268ff9..HEAD -- rtl/ tb/` 为空自证，已实测为空） |

提交纪律：
- 证据文件（`report/`）**入库**（§五.13（2）二级判据要求「综合/实现报告入库 + commit 可追溯」）；
- 源文件与 HEAD 一致性由 `synth_result.txt` 的第 8 / 10 项、`impl_result.txt` 的第 10 / 11 项字段自证；
- ⚠️ `tight_setup_hold_pins.txt` 是 `route_design` **自动落在启动目录**的工具副产物，
  每次布线重生，**已加入 `.gitignore`**，不作为证据入库。
