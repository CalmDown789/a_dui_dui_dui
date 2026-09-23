# B 真实五层 RTL —— 逐字节对拍不成立的取证与交接

> **复核更新（2026-09-23）**：上文记录的是 XSim 2022.2 默认 `xelab` 优化下的
> 失败。原 RTL `ae29515`、ROM 与 Golden 均不变，切换到 `xelab -O0` 后 6×5 全层探针、
> 96×54 四组和 960×540 全帧均为 0 失配。综合、实现和上板仍未验收。以下默认优化
> 失败矩阵保留为历史证据。配置、命令、日志和输入哈希见
> `docs/B_REAL_XSIM_REPRODUCIBILITY.md`。

生成时间：2026-09-23。本文件由 C 侧（WorkBuddy 工程集成）出具。

---

## 0 冻结前提

| 项 | 值 |
|---|---|
| 工具链 | **Vivado / XSim 2022.2**（本机唯一安装；`E:\Xilinx\Vivado\2022.2`） |
| B RTL | `rtl/b_real_ae29515/` —— 14 个 `stream/*.sv` + `postprocess/prelu_requantize.sv`（15 文件闭包），来源 `CalmDown789/a_dui_dui_dui` @ `ae29515` |
| B 参数 ROM | `rom/member_a_d16_s8_m1_c16/*_packed.mem`（19 个） |
| A 整数 Golden | `ref/a_test_vectors/<case>/`（SHA-256 经 `manifest.json` 对账）、`ref/a_full_integer_golden/` |
| C 参考实现 | 五层 + PixelShuffle 的 NumPy 整数参考，**直接复用 B 自己的** `acx750_rtl/scripts/audit_member_a_delivery.py` |

> ⚠️ B 记录中的 PASS 标记来自 **XSim 2025.2**（见
> `acx750_rtl/docs/verification_status.md` 与 `member_b_c_real_core_handoff.md`）。
> 本机**只装 2022.2**，无法在同版本下复跑。该版本差异是本文件唯一未排除的
> 干扰因素，见 §5。

---

## 1 复现步骤（B 自身流程，逐字未改）

```text
# 1) 用 B 自己的生成脚本产出「输入 + 五层 Golden + 19 个 packed ROM」
#    --delivery-root 指向 A 的冻结量化资产（artifacts/quant）
python acx750_rtl/scripts/generate_small_network_golden.py \
    --delivery-root <A artifacts root> \
    --output-dir <work> --width 96 --height 54 --seed 750

# 2) 抄 B 的 15 个 RTL + B 自己的 TB（仅把 `define TB_W/TB_H 改成目标尺寸）
# 3) 按 B 的 run_network_mem_top_xsim.ps1 逐条执行
xvlog -sv <17 sv>            # 需要时加 -d TB_ALWAYS_READY
xelab fsrcnn_network_mem_top_tb -s s1
xsim  s1 -runall
```

C 侧已把上述流程脚本化为 `_brepro_run/`（单尺寸）与 `_bgeo.ps1`（多尺寸扫描）。

---

## 2 失败矩阵（全部用 **B 自己的 TB + B 自己的 Golden**）

| 几何 | 背压 | 结果 |
|---|---|---|
| **6×5**（B 脚本默认值） | 有（TB 默认 3/17 停等） | `Fatal: output byte=2` |
| **6×5** | 无（`-d TB_ALWAYS_READY`） | `Fatal: output byte=2` |
| 96×54 | 有 | `Fatal: output byte=2` |
| 96×54 | 无 | `Fatal: output byte=2` |
| 96×96（IMG_H > STRIPE_ROWS） | 有 | `Fatal: output byte=2` |
| 96×128 | 有 | `Fatal: output byte=2` |

关键点：

1. **失败点恒为第 3 个输出字节（index 2）**，与图像尺寸无关。
   即：`out[0]`、`out[1]` 正确，`out[2]` 起错误。
   按 PixelShuffle 行主序，`out[0..3]` 对应输入像素 `x=0` 的四个相位，
   `out[2]` 是 **输入列 x=1、相位 0** 的第一个字节。
2. **与背压无关**：`ALWAYS_READY` 与带停等两种模式下失败点完全一致。
3. **与几何/条带数无关**：6×5（单条带）、96×96 与 96×128（多完整条带）同样失败，
   因此**不是** `IMG_H < STRIPE_ROWS` 的条带边界特例。
4. 失败与 B 记录中的尺寸（6×5 / 96×54）**均不能复现 PASS**。

---

## 3 C 侧集成路径下的同一结论

C 侧正式路径（`b_core_if.v` + `-d C_USE_B_REAL` + 显式传
`IMG_W/IMG_H/STRIPE_H`）跑 `tb/tb_b_real_bit_exact.v`（96×54，四组 A 用例）：

| 用例 | 逐字节匹配 |
|---|---|
| impulse | 4920 / 20736（23.7%） |
| ramp | 103 / 20736（0.5%） |
| random | 1581 / 20736（7.6%） |
| zero | 4911 / 20736（23.7%） |

协议层**完全正确**：`fed=5184`、`got=20736`、`stripe_last=2`、`frame_last=1`、
`done=1`、无 X、保持规则在停等期间成立、帧间无状态泄漏。

即：**握手/侧带/帧调度这块 C 侧接得没问题，出问题的是数据通路的数值。**

---

## 4 已排除的原因（每项都有独立证据）

### 4.1 不是参数 ROM 装载 / 端序问题 —— **已实测排除**

新增探针 `tb_rom_probe.sv` 直接读取 `fsrcnn_network_mem_top` 内部寄存器，
与同一份 packed 文件在 Python 侧的解码值、以及 A 的量化 `bin` 逐项比对：

```text
  ROM-PROBE ok        w1[0][7:0]        (elem0)  = 20 / 0x00000014
  ROM-PROBE ok        w1[0][15:8]       (elem1)  = 54 / 0x00000036
  ROM-PROBE ok        w1[0][3199:3192]  (elem399)  = 13 / 0x0000000d
  ROM-PROBE ok        b1[0][31:0]       (bias0)  = -1584 / 0xfffff9d0
  ROM-PROBE ok        q1[0][31:0]       (q31_0)  = 176813261 / 0x0a89f4cd
  ROM-PROBE ok        p1[0][15:0]       (prelu0)  = 32767 / 0x00007fff
  ROM-PROBE ok        w5[0][7:0]        (elem0)  = 254 / 0x000000fe
  ROM-PROBE ok        b5[0][31:0]       (bias0)  = 122888 / 0x0001e008
RESULT: PASS
```

⇒ 权重/偏置/requant/PReLU 的**装载顺序与打包方式一致**，装载端序**不是**原因。

同时 19 个 ROM 的末行（B 自己的判定口径）在「B 生成脚本产物」「B 仓库打包件」
「C 侧 `rom/` 副本」三处**逐字符一致**（19/19）。

### 4.2 不是 A 的基准有问题 —— **已实测排除**

用 B 自己的 `audit_member_a_delivery.py` 参考重算 A 的四组 `test_vectors`，
逐层、逐用例 **0 处不一致**；A 各文件 SHA-256 与其 `manifest.json` 一致；
`impulse` 与 `zero` 两组长向量的差异恰为冲激响应区域（265 字节），自洽。

### 4.3 不是「输出顺序 / 相位置换」 —— **已实测排除**

若是纯排列问题，则**常数输入**下输出必须仍为常数（排列不改变值集合）。
实测（`tb_const_probe.sv`，96×54，直接常数注入）：

| 输入常数 V | 参考深内部值 | DUT 逐字节匹配 | DUT 首行样值 |
|---|---|---|---|
| 0 | {0,1,2,3,4} | 4911 / 20736 | `02 03 02 04 02 03 ...` |
| 64 | {63,64,65} | **0 / 20736** | `0c 02 05 00 0a ...` |
| 128 | {127,128,129} | **0 / 20736** | `13 00 02 00 0e ...` |
| 192 | {189..194} | **0 / 20736** | `19 00 00 00 0f ...` |
| 255 | {251..255} | **0 / 20736** | `1e 02 05 00 0f ...` |

两条硬结论：

* **DUT 在常数输入下输出非常数**（V=0 时 20058/20736 字节 ≠ 首字节），
  而正确实现在深内部必须是常数 ⇒ **不是**排列/寻址顺序问题。
* V ≥ 64 时**逐字节匹配恰为 0**，值集合与参考**完全不相交**；
  DUT 输出约为参考的 **1/13～1/14 增益**（V=64→3、128→10、192→13、255→17），
  且在 x 方向呈**周期 2 的调制**（如 `0d 02 0d 02 ...`）。

### 4.4 不是 C 侧喂数/握手/背压

* `tb_b_real_smoke.v`（6×5 两帧、含停等与保持规则）**PASS**。
* `ALWAYS_READY` 与带停等下失败点一致（§2）。
* 常数注入路径不经过任何 C 侧模块，仍失败。

### 4.5 不是「本机集成方式」的问题

B 自己的 TB 直接实例化 `fsrcnn_network_mem_top`（不经 C 的 `b_core_if`），
同样失败；C 侧走 `b_core_if` 也失败。**两条独立路径、两个独立测试台、
两套独立 Golden，共同指向同一 DUT。**

---

## 5 唯一未排除的干扰：Vivado 版本

> **接管补充**：B 原始 TB 的 `always @(posedge clk)` 用阻塞赋值推进
> `sent`，DUT 同沿采样 `input_mem[sent]`，存在事件排序竞争的可能。
> 因此下述“唯一”应理解为此前排查范围，不应据 B 原始 TB 的结果
> 单独归因于 RTL。C 侧 TB 在下降沿稳定驱动后仍逐字节失败；
> 另用非阻塞索引的逐层探针排除原始 TB 竞争。

* B 的 PASS 记录在 **XSim 2025.2**；
* 本机只有 **Vivado 2022.2**（`E:\Xilinx\Vivado` 下仅此一个版本）。

因此严格表述应为：**「在项目冻结的 2022.2 上，B 的五层真实 RTL 不成立」**，
而不能单方面断言「RTL 在任何工具上都不成立」。

不过：整数定点 RTL 的正确性**不应**依赖仿真器版本；且本设计无 X 传播、
无未初始化存储（探针已验 ROM 装载正确），常规的版本敏感点（`$readmemh`
长行/宽字、initial 次序、X-乐观）都已逐项排查。因此**大概率是真缺陷**，
但仍需 B 在自己的 2025.2 上按 §1 原样复跑一次以定分界。

---

## 6 请 B 执行的动作（最小集）

1. **在 2025.2 与本机 2022.2 上，用 §1 的原始流程各跑一次 6×5**。
   若 2025.2 过、2022.2 不过 ⇒ 定位为版本敏感构造，请给出敏感点；
   若两边都不过 ⇒ B 的 PASS 记录本身需要撤回并重查。
2. 给出 `out[0..1]` 正确、`out[2]` 起错误的**根因**。
   **接管后新增的逐层证据**：6×5 输入下 L1 INT32 MAC 原始值全部匹配
   A 参考（0/480 失配），而同一层 INT16 后处理有 186/480 失配，
   首个分歧为 token 0/channel 1：DUT `fa6b`、参考 `0f7b`。
   因此优先排查第一层 `vector_postprocess_shared` 的槽位/通道调度、
   `prelu_requantize` 的逐值算术及 Q15/Q31 参数对齐；
   PixelShuffle 症状仍可在上述分歧修复后再独立复核。
   详见 `report/b_real_layer_probe.txt`。
3. 提供一个**常数输入的定向用例**（例如全 0 与全 128 的 96×54），
   B 侧自证输出为深内部常数。
4. 若 B 认为问题出在 C 侧集成，请指出**具体文件与行**；本文件 §4.5 已说明
   B 自身 TB 独立失败。

---

## 7 C 侧已完成的动作（不受本阻塞影响）

* §一：B 的 15 文件闭包 + 19 个 ROM **已纳入正式编译路径**（非 stub），
  `run_sim.tcl` 增加 `real_b_tbs` / `stage_b_roms` / `stage_ref_data` 与
  `-d C_USE_B_REAL`；`lint_tcl.py` LINT CLEAN。
* §二：真实 B 可详细化并跑完整帧协议（smoke PASS）。
* §三：**判据成立但结论为 FAIL**（本文件）。
  后续整帧复跑 2,073,600 字节中有 2,049,726 字节失配；
  `report/b_real_full_summary.json` 固定日志与 Golden 哈希。
* §四/§五/§六：目标器件 `xc7a200tfbg484-2` 的真实 B+C 合并综合脚本
  `scripts/synth_bc_real.tcl` 已准备，带层次**自校验**（必须出现
  `b_core_real` 且 `b_core_stub` 为 0）；综合/实现结果应以
  `report/bc_real_synth/` 的实际输出为准，不能把脚本就绪写成综合完成。

---

## 8 措辞纪律（写入交付材料时必须遵守）

* **不得**把 B 的 XSim PASS 标记当作 C 侧验收结论；
* **不得**由仿真周期数推 200 MHz / 30 fps；
* 在 B 提供根因与修正前，**不得**在任何状态文档中写
  「B 侧功能已验证 / 五层已通过逐字节验收」；
* 综合成功 **不等于** 功能正确，两者必须分开陈述。
