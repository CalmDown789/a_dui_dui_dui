# C 侧 RTL 实现状态（C_IMPLEMENTATION_STATUS）

> 仓库：`srtp/c_side`（C 侧独立 Git 仓库，2026-09-23 新建）
> 基线文档：
> 1. `output/任务书v3.2.2_修订执行版.md`（= `FSRCNN_ACX750-200T部署任务书_v3.2.2修订执行版.docx`）
> 2. `成员B对C架构接口与资源预算确认_v1.0.docx`
>
> 本轮性质：**C 侧可编译、可仿真的工程骨架**。**不是**完整 FSRCNN CNN。
> 所有未由 A/B 确认的量一律 **parameter 化 + TODO**，未做任何猜测。

---

## 1. 本轮完成度（诚实清单）

| # | 用户指令要求（§三 1~16） | 状态 | 证据 |
|---|---|---|---|
| 1 | 200 MHz 单时钟域与复位 | ✅ | `c_top.v`：MMCME2_BASE 24.0/1/6.0（§五.4）；`sys_rst_n = rst_n & mmcm_locked` |
| 2 | start/busy/done 控制框架 | ✅ | `c_ctrl.v`；语义严格按 §六（N 接受 / N+1 进输入 / F+1 出 done） |
| 3 | 输入 ROM / 输入像素流接口 | ✅ | `input_rom.v`（19 bit 地址、2^19 深、同步读 1 拍）+ `input_stream.v` |
| 4 | C→B 输入 ready/valid | ✅ | `in_valid`/`in_ready`/`in_data[7:0]`；stall 时 addr/x/y/data 全部保持（TB 逐拍断言） |
| 5 | B→C 输出 ready/valid | ✅ | `out_valid`/`out_data`/`out_ready`/`stripe_last`/`frame_last`（§五.8 冻结 8 条件） |
| 6 | 64-row ping-pong buffer | ✅ | `pingpong_buffer.v` + `stripe_buffer.v`（**单条带**，绝不整帧缓冲） |
| 7 | stripe_last / frame_last | ✅ | 由 C 侧**独立复算**并与 B 的 sideband 比对，不一致即 `proto_err` |
| 8 | 输出流与 buffer 状态机 | ✅ | `output_stream.v`；`buf_state` = IDLE/WRITING/SWAPPING/DRAINING（§五.10 规则 3） |
| 9 | UART 回读骨架 | ✅ | `uart_tx.v`（8N1 参数化，默认 921600）+ `readback_ctrl.v`（有条带回读，有界流水不丢字节） |
| 10 | 参数集中管理 | ✅ | `c_config.vh`（单一真源，逐条标注出处） |
| 11 | B interface stub | ✅ | `b_core_if.v`（冻结端口唯一落点）+ `b_core_stub.v`（**SIMULATION STUB ONLY**） |
| 12 | testbench | ✅ | `tb/tb_stripe_buffer.v`（模块级 T1~T6）、`tb/tb_ready_valid.v`（小规模 A~K）、`tb/tb_c_top.v`（全尺寸边界 + c_top 冒烟）——**三者全 PASS** |
| 13 | 基本自检 | ✅ | TB 内 scoreboard：逐字节比对 + 边界复算 + UART 解码复算 |
| 14 | 必要的 assertion | 🟡 **部分** | ✅ TB 内逐拍断言（stall 保持 / 计数 / 边界）＋ RTL 内 `proto_err`/`overflow_err` 黏滞标志；⬜ 未写 SVA `assert property` |
| 15 | Vivado 工程兼容代码 | ✅ | `constr/c_top.xdc`（复用已上板实测基线）、`scripts/run_sim.tcl`、`scripts/synth_check.tcl`、`rtl/c_synth_top.v`（综合专用顶层） |
| 16 | C 侧开发说明 | ✅ | 本文件 + 各文件头注释（含 TODO 与依据条款） |

### 已通过的验证（实测，非推断）

```
工具   : Vivado 2022.2  xvlog / xelab / xsim / synth_design（E:\Xilinx\Vivado\2022.2\bin）
RTL    : 14 个文件 xvlog 语法分析 0 ERROR（含 c_core / b_core_if / c_top / c_synth_top）
仿真   : 3 个 testbench 全部 PASS
           tb_stripe_buffer : RESULT: PASS  (T1~T6, 0 error)
           tb_ready_valid   : RESULT: PASS  (all A~K scenarios, 0 error)
           tb_c_top         : RESULT: PASS  (Part A 全尺寸边界 + Part B c_top 冒烟)
综合   : synthesis only —— 0 ERROR / 0 CRITICAL WARNING
           RAMB36 = 192 / 365 (52.60%)   RAMB18 = 0   DSP48E1 = 0
           LUT 3723   FF 8190   WNS(synthesis, 200MHz) = -0.153 ns（3/20911 失败端点，
           且剩余违例路径位于 **stub 内部**）
```

### tb_ready_valid 实测汇总（小规模 IMG 32×16 → OUT 64×32，STRIPE_H=5 ⇒ 7 条带、末条 2 行）

| 指标 | 实测 | 期望 |
|---|---|---|
| 输入像素握手数 | 1024 | 1024（2 帧 × 512） |
| 输出像素握手数 | 4096 | 4096（2 帧 × 2048） |
| UART 解出字节数 / 错误 | 4096 / **0** | 4096 / 0 |
| 输出字节逐字节比对 | **全部一致** | — |
| `stripe_last` 脉冲数 | 14 | 14（2 × 7） |
| `frame_last` 脉冲数 | 2 | 2 |
| 最长输出背压 | **33610 拍** | ≥50 拍（场景 C/I） |
| 最长输入背压 | 33738 拍 | — |
| `proto_err` / `overflow_err` | **0 / 0** | 0 / 0 |
| `rom_addr` 最大值 | 512（= 填充区起点） | 不回绕、不无界增长 |

### tb_stripe_buffer 实测汇总（模块级 WIDTH=8 / ROWS=4 ⇒ 32 B/条带）

| 用例 | 内容 | 结果 |
|---|---|---|
| T1 | 单条带写满 + 立即回读 | ✅ 逐字节一致，`rd_start`/`rd_last` 位置正确 |
| T2 | 两条带连写（触发一次 exchange）+ 顺序回读 | ✅ |
| T3 | 两条带连写后不释放 → **wr_ready 必须掉 0**；持续 200 拍不得放行；`buf_state=SWAPPING` | ✅ 反压生效，`overflow_err=0`（未覆盖） |
| T4 | 部分条带（len=12 < 32）收尾 + 回读 | ✅ |
| T5 | `overflow_err` 恒 0；wr_total == rd_total | ✅ 204 == 204 |
| T6 | `buf_state` 观察到 WRITING / SWAPPING / DRAINING | ✅ 三态全见 |

### tb_c_top 实测汇总（**全尺寸** 1920×1080 / STRIPE_H=64）

| 用例 | 内容 | 实测 | 期望 |
|---|---|---|---|
| A1 | 输出像素握手总数 | **2,073,600** | 2,073,600 |
| A2 | `stripe_last` 脉冲数 | **17** | 17（16 条整 + 末条） |
| A3 | **末条带长度** | **107,520 B** | 56 × 1920 = 107,520 |
| A4 | `frame_last` 脉冲数 / `frame_last ⇒ stripe_last` | 1 / 成立 | 1 / 成立 |
| A5 | `proto_err`（C 侧独立复算 vs B 侧 sideband） | 0 | 0 |
| A6 | `overflow_err`（245,760 B 双 bank 内不覆盖） | 0 | 0 |
| A7 | 回读 2,073,600 B 逐字节一致 + 条带顺序 FIFO | **全部一致** | — |
| A8 | 最长输出背压 | 5 拍（1 B/cycle 回读基本追得上） | 记录值 |
| B | `c_top` 板级冒烟（`USE_MMCM=0`，`busy` 于 47 拍后拉起，无 X 传播） | PASS | — |

> 仿真总时长 21,965,800 ns ≈ 2.1966 M 拍（全尺寸单帧），**未生成任何波形文件**。

---

## 2. 场景覆盖对照（用户指令 §十三 A~K）

| 场景 | 覆盖方式 | 结果 |
|---|---|---|
| A ready 恒为 1 | 复位后至缓冲区写满前的窗口（实测 out_accept 到 640 时仍恒 1） | ✅ |
| B ready 周期性拉低 | UART 每字节忙 10 拍 ⇒ 条带间周期性反压 | ✅ |
| C ready 连续拉低几十拍 | `rb_enable=0` 2000 拍 ⇒ 缓冲区写满（`buf_state=SWAPPING`），最长 33610 拍 | ✅ |
| D out stall 时 data/sideband 保持 | TB 逐拍比对 `out_data`/`stripe_last`/`frame_last` | ✅ 零漂移 |
| E in_ready=0 时 data/addr/x/y 保持 | TB 逐拍比对 `in_data`/`rom_addr`/`x`/`y` | ✅ 零漂移 |
| F stripe 边界 | TB 独立复算 `stripe_last` 位置 | ✅ |
| G 末条带（部分条带） | OUT_H=32 / STRIPE_H=5 ⇒ 末条 **2 行** | ✅ |
| H frame_last | TB 复算 + `frame_last ⇒ stripe_last` 检查 | ✅ |
| I buffer 满 | 见 C；`overflow_err=0` 证明无覆盖 | ✅ |
| J start/busy/done | 复位后 start 单拍 → N+1 检查 `busy=1`；`done` 脉冲计数 | ✅ |
| K 连续启动第二帧 | 第 1 帧 done 后 5 拍再起第 2 帧，全程字节级一致 | ✅ |

---

## 3. 接口现状（C 侧实现，严格对齐冻结契约）

### C-B v0.2（`b_core_if.v` 端口 = 唯一落点）

| 信号 | 方向 | 位宽 | 实现要点 |
|---|---|---|---|
| `clk_200` | C→B | 1 | 唯一时钟域（§五.4，不做多域） |
| `rst_n` | C→B | 1 | 低有效，`rst_n & mmcm_locked` |
| `start` | C→B | 1 | 1 拍脉冲，**cycle N+1** 发出（§六） |
| `busy` / `done` | B→C | 1 | C 侧自产 `busy`；同拍记录 B 的 `done`（`b_done_seen`） |
| `in_valid` / `in_data[7:0]` | C→B | 1/8 | 行主序，每帧 518400 像素 |
| `in_ready` | B→C | 1 | 反压时输入侧**零跳像素**（TB 验证） |
| `out_valid` / `out_data[7:0]` | B→C | 1/8 | `out_data` 固定 8 bit uint8 |
| `out_ready` | C→B | 1 | **寄存输出**，寄存的是「下一拍可用性」（§五.10 规则 1/2） |
| `stripe_last` / `frame_last` | B→C | 1/1 | 与最后一个有效数据拍同拍；`frame_last ⇒ stripe_last` |

### 输入 ROM 读接口（§五.9（2）语义冻结）

- 端口 `rom_en` / `rom_addr[18:0]` / `rom_dout[7:0]`；同步读延迟 **1 拍**。
- 地址语义 `rom_addr = y*960 + x`；填充区 `518400..524287` 内容 `0x00`。

> **★ 地址写法（§五.9（4）第 7 项要求二者择一写清）**：
> **本实现采用「写法 A（请求地址）」** —— `rom_addr` 是本拍**请求**的地址，
> 其数据在**下一拍**出现在 `pixel_valid`/`in_data` 上，即 `pixel_valid` 相对
> `rom_addr` **延后 1 拍**。
> 形式化（`pres_q` = 当前呈现像素索引，`in_fire = in_valid & in_ready`）：
> ```
> rom_addr(t) = pres_q(t) + in_fire(t) = pres_q(t+1)
> in_data(t)  = rom_dout(t) = mem[rom_addr(t-1)] = mem[pres_q(t)]
> ```
> TB 已按「`in_data(t) == pattern(y(t)*IMG_W + x(t))`」逐拍验证，故 **不存在整体平移 1 像素的 off-by-one**。
> 端点证据：`(0,0)` 与 `(959,539)` 等价端点（小规模为 `(0,0)`/`(31,15)`）均单独断言通过。

---

## 4. 哪些参数来自 v3.2.2（可追溯）

| 参数（`c_config.vh`） | 值 | 出处 |
|---|---|---|
| `C_IMG_W` / `C_IMG_H` | 960 / 540 | §五.9（1）行主序、每帧 518400 拍 |
| `C_PIXEL_W` | 8（uint8 Y） | §五.8（1）`out_data` 固定 8 bit |
| `C_OUT_W` / `C_OUT_H` | 1920 / 1080 | §五.8（3）每帧输出 2,073,600 像素 |
| `C_STRIPE_H` | **64（当前基线，非冻结项）** | §五.3 / §五.11；变更须走 §五.3 五项重算规程 |
| `C_STRIPE_CNT` / `C_LAST_STRIPE_H` | 17 / 56 | §五.8（3）；仅在 H=64 时成立 |
| `C_ROM_ADDR_W` / `C_ROM_DEPTH_POW2` | 19 / 524288 | §五.9（2）；差额 5888 B ≈ 5.75 KiB 须计入预算 |
| MMCM 24.0 / 1 / 6.0，CLKIN 20.0 ns | — | §五.4（已上板实测） |
| `C_UART_BAUD` | 921600（8N1 = 10 bit/Byte ⇒ ≈22.5 s/帧） | §五.7 |
| `C_CLK_HZ` | 200 MHz | §五.4 |

---

## 5. 使用 B stub 的位置（★ 替换点）

| 项 | 内容 |
|---|---|
| 替换点 | `rtl/b_core_if.v`：默认例化 `b_core_stub`；打开编译宏 `` `C_USE_B_REAL `` 即切到 `b_core_real` |
| stub 文件 | `rtl/b_core_stub.v`（文件头已写 **★★★ SIMULATION STUB ONLY ★★★**） |
| stub 行为 | **仅** 2×2 最近邻复制上采样（IMG→OUT：OUT_W=2·IMG_W，OUT_H=2·IMG_H），严格光栅序 |
| 明确不做 | 不做卷积 / 不做 PixelShuffle 相位语义 / 不做量化·PReLU·Q31；**没有实现任何「猜测版 FSRCNN」** |
| 不得用于 | 任何 PSNR、算法效果、资源占用、FPS 结论 |

---

## 6. 还等谁（TODO 清单，实现处已同步标注）

| TODO | 等谁 | 影响 | 现状 |
|---|---|---|---|
| `TODO(B_CONFIRM)` B-ARCH-10 七项背压参数（含**最大连续 back-pressure 周期 N**） | B | C18 的 N 相关用例无法构造 | stub 取「可无限期背压」的下限模型；真实 B 到位后**无需改 C** |
| `TODO(B_CONFIRM)` 真实五层 RTL | B | 计算路径非真实 | 已隔离在 `b_core_if.v` |
| `TODO(B_CONFIRM)` 条带高度若改 32 行（M1 缓解方案） | B/C 双向 | 须重算 stripe 数 / 末条高 / 双缓冲 / UART 分段 / 接口周期 | 已参数化，改 `C_STRIPE_H` 即可 |
| `TODO(A_CONFIRM)` 全尺寸 960×540 真实图像 `.mem` | A | 输入 ROM 内容 | 现仅公式 pattern / 小 `tiny` 数据 |
| `TODO(A_CONFIRM)` padding 约定书面确认（附录 G G16） | A | B 侧责任，C 不索要越界像素 | — |
| `TODO(UART_PIN_CONFIRM)` CH9102 侧 FPGA 管脚 | 首连串口时用 IO Planner | XDC 约束 | 待写 XDC，已注释保留 |
| `TODO(C_DECIDE)` 真实 `start` 触发源（UART RX 命令 / 按键 / 上位机） | C | 顶层触发 | 暂用 `AUTO_START_EN` 参数作板级冒烟 |

---

## 7. 下一步（按优先级）

1. **补 `tb_stripe_buffer.v`**（模块级：写入/读出/ping-pong 切换/满时反压/不覆盖的定向用例）。
2. **补 `tb_c_top.v`**（全尺寸 960×540 → 1920×1080、STRIPE_H=64：只验控制/边界——17 条带、末条 56 行；
   严格 timeout、**不 dump 波形**、不落盘）。
3. **补 `scripts/run_sim.tcl` / `scripts/synth_check.tcl` / `constr/c_top.xdc`**（XDC 可直接复用
   `bench/onboard_dual_int8/constr/top_onboard.xdc` 的引脚与 CFGBVS/CONFIG_VOLTAGE）。
4. **一次 `synth_design`（仅综合，不做 implementation / 不生成 bitstream）**，产出 `report_utilization`
   以回填 §8.3 C11。注意：综合时须让 ROM 带非零初值（`ROM_INIT_MODE=1` 或真实 `.mem`），
   否则全零 ROM 可能被优化掉导致 BRAM 数偏低。
5. 真实 B RTL 到位后：按 `b_core_if.v` 的 `C_USE_B_REAL` 切换，并补 C18 的 N 相关用例。

---

## 8. 表述纪律（本轮严格遵守）

- 本文件**不含**任何 Fmax / FPS / DSP / BRAM 实测数字 —— 完整设计**尚未综合**。
- 唯一实测性能类数据是「本次 xsim 仿真的 cycle 数与背压拍数」，且明确标注为**仿真**结果。
- BRAM 预算口径仍为：「**一级 理论预算未闭合**（口径② ≈1406.6 > 1396.1 KiB）；**二级 实际资源未验证**」
  （§五.13（2）），C 侧本轮**未做**任何 BRAM 结论。
- stub 的输出**纯粹是测试 pattern**，不得当作算法结果。

---

## 9. 仅综合（synthesis）取证结果 —— **实测，但仍非最终结论**

> 命令：`vivado -mode batch -source scripts/synth_check.tcl`
> 顶层：`c_synth_top`（含 stub，**不是完整 FSRCNN**）
> 器件 / 工具：`xc7a200tfbg484-2` / Vivado 2022.2
> 原始报告：`report/utilization_synth.rpt`、`report/timing_summary_synth.rpt`、`report/synth_result.txt`
> **未执行** opt_design / place_design / route_design / write_bitstream。

### 9.1 资源

| 资源 | 本次实测 | 器件上限 | 占比 |
|---|---|---|---|
| **RAMB36/FIFO** | **192** | 365 | **52.60%** |
| RAMB18 | 0 | 730 | 0% |
| **DSP48E1** | **0** | 740 | 0% |
| Slice LUTs | 3,723 | 134,600 | 2.77% |
| Slice Registers | 8,190 | 269,200 | 3.04% |
| LUT as Memory | 0 | 46,200 | 0% |
| CRITICAL WARNING | **0** | — | — |
| ERROR | **0** | — | — |

**RAMB36 = 192 的构成（逐项可复算，来自综合日志的 Block RAM Final Mapping Report）**：

| 项 | 实测 RAMB36 | 复算 |
|---|---|---|
| 输入 ROM（`u_rom`，524288×8，`$readmemh`） | ~128 | 524288 / 4096 = 128（4096×9 模式） |
| 条带 bank0（`u_pp/u_bank0/mem_reg`，120K×8） | **32** | 日志明确列出 |
| 条带 bank1（`u_pp/u_bank1/mem_reg`，120K×8） | **32** | 日志明确列出 |
| **合计** | **192** | 128 + 32 + 32 |

> 与 B 侧预算对照（成员B确认_v1.0 §五，B 侧口径）：B 估算「C 输入 ROM **127** + C 侧 64 行双缓冲 **60**」= **187**。
> 本次实测 **128 + 64 = 192**，比 B 的估算 **多 5 块**（ROM 深度向上取整差 1 块；条带降为 32+32 而非 B 假设的 30+30）。
> **按 §五.13（2）二级判据，C 侧骨架的实际 BRAM utilization（52.60%）在 85% 工程预算线内。**
> ⚠️ 但这**不是**「BRAM 已闭合」：① 本设计含 stub，**不含 B 侧 44 块 RAMB36 行缓存与相位 bank**；
> ② 未做 implementation；③ 二级闭合的责任与判据在 §五.13（2）/ §九 门槛 7，需 B 侧方案选定后合并复核。

### 9.2 时序（**synthesis 级，不是最终 Fmax**）

| 项 | 值 |
|---|---|
| 目标时钟 | 200 MHz（MMCM 24.0 / 1 / 6.0） |
| **WNS** | **−0.153 ns** |
| TNS | −0.377 ns |
| 失败端点 | **3 / 20,911** |
| WHS（保持） | +0.127 ns，失败 0 |
| 关键路径位置 | **`u_b/u_b_core/stripe_base_reg[8]` → `stripe_h_reg[14]/D`**（即 **stub 内部**的条带几何，4.968 ns，CARRY4×4 + LUT3 + LUT6） |

> ⚠️ **表述纪律**：这是 **synthesis 级**结果，**未做 place/route**，
> **不得**据此宣称 Fmax、更不得宣称「200 MHz 已收敛」。
> 参考：任务书 §五.4 已说明「完整 FSRCNN 的 Fmax 待实测」。
> ✅ 值得记录的正向信号：**剩余唯一违例路径位于 stub 内部**，C 侧基础设施本身已无违例端点；
> 真实 B 替换 stub 后该路径消失，应重新综合复核。

### 9.3 本轮由综合暴露并已修复的 3 个真实缺陷

综合（而非仿真）是发现下列问题的手段——**这三条都是仿真"侥幸通过"、综合才报出来的**：

| # | 现象 | 根因 | 修复 | 效果 |
|---|---|---|---|---|
| 1 | **`CRITICAL WARNING [Synth 8-6859] multi-driven net` on `bank_full_q[0]/[1]`** | `bank_full_q` 被**写侧与读侧两个 always 块同时驱动**（仿真靠"后写胜出"侥幸通过，综合结果不确定） | 读侧改为只产生释放脉冲 `rd_done_q`/`rd_done_bank_q`，由写侧块**统一施加**；并在读侧起始条件加 `&& !rd_done_q` 防止重复读同一 bank | **0 CRITICAL WARNING** |
| 2 | **WNS −4.470 ns**，关键路径 `stripe_base_q → CARRY4 → LUT1 → CARRY4 → LUT6×2 → DSP48E1(A×0x780) → LUT2 → wr_stripe_len_q/D` | `next_rem = OUT_H−next_base; next_h = min(...); wr_stripe_len = next_h×OUT_W` 被串成一条「减法→取小→乘法」链，且乘法被映射成 **DSP48E1** | 末条带行数在**展开期**即为常量（`LAST_H = OUT_H − (N_STRIPES−1)×STRIPE_H`），改用**常量 mux**；并把 `stripe_last_row` 也寄存 | WNS **−4.470 → −0.153 ns**；失败端点 **150 → 3**；**DSP48E1 2 → 0** |
| 3 | **`WARNING [Synth 8-6896] loop limit (65536) exceeded inside initial block, initial block items will be ignored`**（`input_rom.v` / `stripe_buffer.v`） | 用无界 `for` 循环给整片 ROM/RAM 写初值；综合器**忽略**超限的 initial 块 ⇒ ROM 无初值、BRAM 统计失真（实测只报 16 块 RAMB36） | ① ROM 改走 `$readmemh`（Vivado 原生支持，不受循环上限影响），公式 pattern **仅包在 `` `ifdef C_SIM `` 内**；② `stripe_buffer`/`b_core_stub` 删除无效果的初值（BRAM 上电默认 0，且本设计保证先写后读） | BRAM 统计回到可信值（**16 → 192**）；新增 `scripts/gen_input_mem.py` 生成 1.5 MB 的 `rtl/input_image_pattern.mem`（已 gitignore） |

### 9.4 已知遗留项（已定性，优先级低）

| 项 | 说明 | 影响 |
|---|---|---|
| `WARNING [Synth 8-4767]` + `[Synth 8-7137]`：`rowbuf_reg` 未能推断为 LUTRAM，被拆成寄存器 | 位于 **stub** 内（`b_core_stub.v` 的 960 B 行缓存）。真实 B 替换后消失 | 约 7.7K FF 的**临时**开销（当前 FF 8190 主要来自这里）。**不修**：属 stub 内部实现细节，修它没有交付价值 |
| `WARNING [Synth 8-7129]` ×3：`rd_avail`/`rd_start`/`b_busy` 端口无负载 | 这些端口是**为可观测性与真实 B 对接保留**的，当前 stub 未使用 | 无功能影响；保留 |
| `WARNING [Synth 8-589]` ×2：`!==` 被替换为 `!=` | `output_stream` 的 `proto_err` 检查刻意用 `!==` 以便在**仿真**中捕获 X | 无功能影响；仿真语义保留 |
| `WARNING [Synth 8-7080]` ×1 | Parallel synthesis criteria not met（回退单线程） | 无功能影响 |

**本轮结论（严格）**：C 侧骨架 **可编译、可仿真、可综合**，
三条 TB 全 PASS，综合 **0 ERROR / 0 CRITICAL WARNING**；
synthesis 级 WNS **−0.153 ns** 且**剩余违例路径在 stub 内部**；
RAMB36 **192/365 = 52.60%**，DSP **0**。
**这不构成「完整 FSRCNN 已收敛」的结论**——完整设计尚未综合、未实现、未上板。
