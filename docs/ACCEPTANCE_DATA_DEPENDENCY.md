# 验收数据依赖（ACCEPTANCE_DATA_DEPENDENCY）

> **2026-09-23 接管核对更正**：`member-a@98c82f3` 的
> `docs/成员A全尺寸整数Golden确认.md` 已明确确认全尺寸整数 Golden，
> 且列出的最终输出 SHA-256 与本地 9 文件清单一致。因此下文把
> “缺 A 书面确认”列为唯一障碍的旧结论已失效。仍待 A 澄清的是：
> 为何该提交从 `main` 撤回，以及最终重新发布的权威 commit/路径。
> 当前真实 B RTL 的逐字节 FAIL 是独立的功能阻塞。

> **用途**：把 C 侧**验收链路所依赖的外部数据**（谁提供、在哪、什么哈希、当前什么状态、
> 卡住哪一条验收）一次性钉死。核心是 **A 侧全尺寸 960×540 整数 Golden**。
>
> **上级依据**：`任务书 v3.2.2 修订执行版` §三.2 / §三.3 / §四.4 / §五.9（2） / §8.3 **C8** / §九 门槛 3；
> `DEPENDENCIES_A_B.md` §2（A-1 ~ A-5）。
> **建立时间**：2026-09-23　｜　**被引用于**：`rtl/c_config.vh`（`TODO(A_CONFIRM)`）、`ref/README.md`
> **本文档纪律**：所有哈希/字节数**均为本机实测**（命令输出，非记忆）；
> A 的书面确认已在 `98c82f3` 的 `docs/成员A全尺寸整数Golden确认.md` 找到；
> 正式重新发布位置仍未确认，不推测、不补全。

---

## 一、结论先行

| # | 数据 | 现状 | 卡住什么 |
|---|---|---|---|
| **1** | **全尺寸整数 Golden**（`output_1920x1080_y_u8.bin` 等 9 文件） | ✅ **实物已取得**（`member-a` @ `98c82f3`），**9/9 哈希复核通过**，同提交含 A 书面确认；<br>🔴 该提交已被 revert，**不在 `main` 上** | **C8** 的可取得性与正式重新发布位置 |
| **2** | 真实 960×540 输入 ROM（`input_rom_2p19_u8.mem` / `.bin`） | ✅ 同上，已取得并校验 | A-2 / C-3（上板实现） |
| **3** | 量化参数 `quant_params.json` | ✅ 已取得；口径争议**已证伪**（见 §三.2） | 门槛 1 |

**一句话**：数据、哈希和 A 的书面确认均已找到；仍需 A 明确撤回原因与正式重新发布
位置。当前真实 B RTL 在 XSim 2022.2 下已逐字节失配，因此 C8 **尚未通过**。

---

## 二、实物清单（逐文件 + 实测哈希）

来源：`https://github.com/CalmDown789/a_dui_dui_dui` ／ 分支 `member-a` ／ 提交
`98c82f394bdfba85bc2959bede9760edc4d6862f` ／ 路径 `artifacts/full_integer_golden/`。
本机副本：`c_side/ref/a_full_integer_golden/`（实物被 `.gitignore` 排除，只提交摘要）。

复核结果：**OK = 9 / BAD = 0**，且与 A 自己的 `manifest.json` → `files{}` 段**逐条一致**。

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `input_960x540_y_u8.bin` | 518400 | `aca4fb6f89accc388cede8f5fddaea79026a1fd507cdad6a844236941807e0f4` |
| `input_960x540_y_u8.png` | 279707 | `d949c79887beda7db85f6778c12917a3664da8ca628a41e0892a6d43152313c1` |
| `input_rom_2p19_u8.bin` | 524288 | `a754715b08e88fa9734069e6090ccceae13594bba248b09a4c154addb21efefc` |
| `input_rom_2p19_u8.mem` | 1572864 | `f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9` |
| `manifest.json` | 6774 | `ea54aa814efb4a71223e691c01780808df72c363b6cc0382c7b5d29e567a6c2a` |
| **`output_1920x1080_y_u8.bin`** | 2073600 | **`be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`** |
| `output_1920x1080_y_u8.npy` | 2073728 | `7fdb252fb749640d6e08da3856d4e9573b74f09650aece454498079706b19e37` |
| `output_1920x1080_y_u8.png` | 1003876 | `5aa6a86c7749b43101dfd6274e926884d1194888e83ff06693c580b9f1d64106` |
| `subpixel_phases_540x960x4_hwc_u8.bin` | 2073600 | `95da497cfcc9002afa0fda59de8e146edb0fd07f2890d8e9a9a9c77753f3be4b` |

A 的 `manifest.json` 自声明：

```json
"status":       "A_CONFIRMED_INTEGER_GOLDEN",
"golden_class": "full_frame_integer_bit_exact",
"authoritative_output": "output_1920x1080_y_u8.bin"
```

> `manifest.json` 的 `A_CONFIRMED_*` 字段自身不足以当书面确认；
> 同提交的 `docs/成员A全尺寸整数Golden确认.md` 才是已找到的确认文本。

---

## 三、三个必须澄清的口径（本文件存在的首要理由）

### 3.1 这份 Golden **现在不在远端 `main` 上** —— 它被 revert 了

远端 `main` 的近两条提交（实测）：

```
2dbb8c7  Revert "feat(member-a): add full-frame integer golden"   ← main 的 tip
98c82f3  feat(member-a): add full-frame integer golden            ← Golden 在这里
```

- `main` 树中 `artifacts/full_integer_golden` 文件数 = **0**（`ls-tree` 实测）
- `98c82f3` 树中同名路径文件数 = **9**
- `98c82f3..main` 之间的提交集合 = `{2dbb8c7}`，即 **加上又立刻撤掉**

**推论（对 C 的直接影响）**：

1. 任何按「clone main 然后找 `artifacts/full_integer_golden/`」的人都会**找不到** —— 不是权限问题，是被撤了；
2. 本机 `ref/a_full_integer_golden/` 的副本**只是证据留档**，**不代表权威定版**；
3. 同提交已有 A 的书面确认；**A-G-1 仍需回答撤回原因与正式重新发布口径**。

> 治理背景见 `DEPENDENCIES_A_B.md` §8 与长期记忆条目 **T6**。
> **本机最新实测（2026-09-23）**：用 GitHub 连接器（账号身份 `CalmDown789`）
> 调 `list_branches` 访问 `CalmDown789/a_dui_dui_dui`，返回
> **HTTP 404 Not Found** ⇒ 该仓库**当前不可访问**。
> 至于是「已删除 / 已改名」还是「token 对该私有库权限不足」，**本机无法进一步区分**，
> 故本文件**不下断言**，只记录「不可访问 + 具体命令 + 返回码」。
> ⇒ **取件前必须先校验 SHA-256，通过后才可当输入使用。**

### 3.2 「13029 还是 13557」之争 —— **已证伪，是同一份文件**

曾观察到两个字节数：`quant_params.json` 在 git 里 13029 B、在 Windows 工作区/交付 ZIP 里 13557 B，
一度怀疑是「两个版本」。**实测结论：是同一份文件，差异全部来自行尾。**

| 形态 | 字节 | SHA-256 | 说明 |
|---|---:|---|---|
| A 仓库工作区（**CRLF**） | **13557** | `9a53d2e3059b36fd68d066935e3d949fb3a418fcc8114d0dcee680ba4d06c34b` | Windows 检出形态；**两个交付 ZIP 内也是这一形态** |
| **LF 归一后**（= git blob） | **13029** | `f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a` | **A 的 `manifest.json` 声明的正是这一口径** |
| 差值 | **528** | | 文件恰有 **528 行**，`13029 + 528 = 13557` ✅ |

- A 的 `manifest.json` 声明：`quant_params.bytes = 13029`、`sha256 = f2a9f20c…b77a`、
  `crc32 = 0a1303ff`；本机对 CRLF 版本做 LF 归一后**三项全部命中** ⇒ **MATCH**。
- A 仓库 `core.autocrlf = true`，`.gitattributes` 存在（`quant_params.json` 属性 `text: set`、`eol: lf`）。

**⇒ 校验纪律（新增，务必遵守）**：核对 A 的**文本类**产物时，**必须先做行尾归一（CRLF→LF）再算哈希**，
否则必然误判为「不一致」。二进制类（`.bin` / `.npy` / `.png` / `.pth`）不受影响。

### 3.3 两个交付 ZIP 里**都没有** Golden

实测 `artifacts/member_a_integer_delivery_d16_s8_m1_c16.zip`（1,701,467 B / 135 条目）与
`artifacts/member_a_weights_and_logs.zip`（20,184 B / 6 条目）：

- `full_integer_golden` 条目数 = **0 / 0**
- 两者内含的 `artifacts/quant/quant_params.json` 均为 **13557 B / `9a53d2e3…34b`**（即 §3.2 的 CRLF 形态）

**⇒ Golden 是「独立于交付 ZIP 的一次性追加」，没有随 zip 分发过。** 这进一步说明：
只拿 ZIP 的人**根本不会知道有这份 Golden**，印证 §3.1 的可见性问题。

---

## 四、行动项

> 图例：🔴 未确认 / 🟨 部分 / 🟩 已闭合

### A 侧

| 编号 | 面向 | 内容 | 卡住什么 | 状态 |
|---|---|---|---|---|
| **A-G-1** | **A** | 同提交的确认文件已找到；请**说明为何在 `main` 上被 revert**，并指定当前应使用的发布位置 | 取件和版本治理 | 🟨 **确认文本已找到，撤回原因未答** |
| **A-G-2** | A | 给出该 Golden 的**生成条件**：输入图来源、模型 checkpoint 哈希、量化参数版本（`quant_params.json` 的 13029/LF 口径）、后处理步骤 | C8 结果的可复现性 | 🔴 未提供 |
| **A-G-3** | A | 确认 §3.2 的**行尾口径**（13029/LF 为准），避免后续再按 13557 比对 | 取件校验流程 | 🟨 本机已定，待 A 认可 |
| **A-G-4** | A | 若 Golden 会被重新发布，给出**新的权威 commit / 路径** | 留档有效性 | 🔴 未提供 |

> A 的书面确认与本地哈希支持把 `98c82f3` 的数据用于本轮对拍；
> `main` 上的重新发布状态仍未闭合。参见 `ref/README.md` 首段。

### B 侧

| 编号 | 面向 | 内容 | 状态 |
|---|---|---|---|
| **B-G-1** | B | 96×54 整数向量**全层逐值对拍**（`DEPENDENCIES_A_B.md` 的 B-9） | 🔴 真实 B RTL 已到；C 在 XSim 2022.2 的最终输出对拍 FAIL，逐层定位进行中 |

### C 侧（自决，不依赖 A/B）

| 编号 | 内容 | 状态 |
|---|---|---|
| **C-G-1** | Golden 实物抽取 + 9/9 哈希复核 + 摘要入库（本文件 §二） | 🟩 完成 |
| **C-G-2** | 把「LF 归一后才比对」写进校验 SOP（§五） | 🟩 完成 |
| **C-G-3** | 在 `c_config.vh` / `README.md` / `ref/README.md` 三处埋指针指向本文件 | 🟩 完成 |
| **C-G-4** | 编写 C8 逐字节比对脚本（PC 端，对 `output_1920x1080_y_u8.bin`） | ⬜ **待做**（依赖 B-1 才有 FPGA 输出可比） |

---

## 五、校验 SOP（任何人、任何机器可复现）

### 5.1 取件（不要用 `checkout`，避免行尾/转码影响）

```powershell
# 在 A 仓库的工作副本里
git fetch origin "+refs/heads/*:refs/remotes/upstream-*"
git rev-parse 98c82f394bdfba85bc2959bede9760edc4d6862f      # 必须回显同一 SHA
git show 98c82f394bdfba85bc2959bede9760edc4d6862f:artifacts/full_integer_golden/output_1920x1080_y_u8.bin > out.bin
```

### 5.2 校验（**二进制**）

```powershell
(Get-FileHash out.bin -Algorithm SHA256).Hash.ToLower()
# 期望 be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e
```

### 5.3 校验（**文本类，如 `quant_params.json`**）—— 必须先归一

```python
import hashlib
data = open("quant_params.json", "rb").read()
lf = data.replace(b"\r\n", b"\n")          # ★ 关键一步
print(len(lf), hashlib.sha256(lf).hexdigest())
# 期望 13029  f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a
```

### 5.4 一键复核（推荐，已入库）

```powershell
# 只校验留档目录（§二 的 9 个文件 + manifest 交叉核对）
& <managed-python> c_side\scripts\verify_golden.py

# 连 quant_params.json 行尾口径一起校验（指向 A 仓库副本）
& <managed-python> c_side\scripts\verify_golden.py --quant <A_repo>\artifacts\quant\quant_params.json
```

实测输出（本机，2026-09-23）：

```
 1) SHA256SUMS.txt 逐文件复核   -> OK=9  BAD=0
 2) manifest.json files{}       -> 8/8 项 manifest==sums : YES
 3) quant_params.json 行尾口径  -> LF 归一三项 bytes=True sha256=True crc32=True
 结果: PASS
```

退出码：`0` = 通过；`1` = 有不一致；`2` = 前置条件缺失。

### 5.5 判定

- 全部命中原期望值 ⇒ **可以**作为输入使用；仍须记录 `98c82f3` 来源与 `main` 的撤回状态；
- 任一不符 ⇒ **立即停用**，按 §六 治理流程上报，**不得**「大概是同一份」放行。

---

## 六、风险与治理

| 风险 | 现象（已实测） | 缓解 |
|---|---|---|
| **仓库可见性波动** | 此前连接器曾返回 404；接管时 `git ls-remote` 已可访问，不应断言仓库删除 | 本机归档保留；取件前校验 SHA-256 |
| **Golden 被 revert** | `main` 上 `full_integer_golden` = 0 文件 | 本机 `ref/a_full_integer_golden/` 留档；并已升级为 A-G-1 行动项 |
| **行尾误判** | 13029 vs 13557 一度被当成两版本 | §3.2 + §5.3 归一 SOP |
| **表述越界** | 容易顺手写「已通过全尺寸整数验收」 | §七 红线 |

---

## 七、表述红线（不得越界）

- 🚫 **不得**写「C8 已通过 / 已验收」—— 真实 B RTL 的输出与整数 Golden 尚不一致；
- 🚫 **不得**把 A 的 `full_reference/ref_out_quant.npy`（A 类浮点/QDQ 参考）当 bit-exact 黄金
  （`任务书` §十.1 第 7 条）；
- 🚫 不得省略 `main` 撤回事实及最终重新发布位置未明确的状态；
- ✅ 可以写：「A 在 `member-a` @ `98c82f3` 提供全尺寸整数 Golden 与书面确认，
  本机已抽取并 **9/9** 通过 SHA-256 复核；该提交随后从 `main` 撤回，
  正式重新发布位置待 A 指定」。

---

## 八、与其它文档的关系

| 文档 | 关系 |
|---|---|
| `DEPENDENCIES_A_B.md` §2 | **上级清单**：本文件是其 A-1/A-2/A-4 项的**证据与状态细化** |
| `ref/README.md` | 留档目录说明；指向本文件 §四 A-G-1 |
| `rtl/c_config.vh` `TODO(A_CONFIRM)` | 指回本文件 |
| `docs/C_IMPLEMENTATION_STATUS.md` §6 | 「还等谁」的 C 侧实现视角 |
| `docs/B_INTERFACE_CONTRACT.md` | B 侧接口契约（与本文件互不覆盖） |
