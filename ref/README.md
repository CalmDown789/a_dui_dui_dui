# ref/ —— 只读参考数据（**实物不入库，摘要入库**）

本目录存放**来自其他成员、体积较大、非 C 侧产出**的只读参考数据。
入库策略：**实物被本目录 `.gitignore` 排除，只提交可校验的摘要**，
使任何人在任何机器上都能「取到原件后校验是否同一份」。

---

## a_full_integer_golden/ —— 成员 A 的全尺寸整数 Golden

| 项 | 值 |
|---|---|
| 来源仓库 | `https://github.com/CalmDown789/a_dui_dui_dui` |
| 来源分支/提交 | `member-a` @ **`98c82f394bdfba85bc2959bede9760edc4d6862f`** |
| 来源路径 | `artifacts/full_integer_golden/` |
| A 的声明状态 | `manifest.json` → `status = "A_CONFIRMED_INTEGER_GOLDEN"`、`golden_class = "full_frame_integer_bit_exact"` |
| 本机抽取时间 | 2026-09-23（`git show <rev>:<path>` 逐文件取 blob，**未经任何转码**） |
| 校验清单 | 同目录 `SHA256SUMS.txt`（9 项，含字节数） |

⚠️ **该提交不在远端 `main` 上**：远端 `main` 的 tip 是
`2dbb8c7 Revert "feat(member-a): add full-frame integer golden"`，
即这份 Golden **被 revert 掉了**。因此：

- 本目录的副本**只是证据留档**，**不代表权威定版**；
- 权威性须由 A 书面确认（见 `docs/ACCEPTANCE_DATA_DEPENDENCY.md` §4 A-G-1）；
- 取用前**必须**按 `SHA256SUMS.txt` 校验。

关键的三个文件（C 侧会用到）：

| 文件 | 字节 | 用途 |
|---|---:|---|
| `output_1920x1080_y_u8.bin` | 2073600 | **C 类全尺寸整数 Golden 权威输出**（C8 逐字节比对目标） |
| `input_rom_2p19_u8.mem` | 1572864 | 真实 960×540 输入图填零到 2^19 的 ROM 文本（`$readmemh` 格式） |
| `input_rom_2p19_u8.bin` | 524288 | 同一 ROM 的裸二进制形式 |

### 复现抽取（任何人都能重做）

```powershell
# 在 A 仓库的工作副本里
git fetch origin "+refs/heads/*:refs/remotes/upstream-*"
git rev-parse 98c82f394bdfba85bc2959bede9760edc4d6862f     # 必须一致
# 逐文件取 blob（不要用 checkout，避免行尾/转码影响）
git show 98c82f394bdfba85bc2959bede9760edc4d6862f:artifacts/full_integer_golden/output_1920x1080_y_u8.bin > out.bin
# 校验
(Get-FileHash out.bin -Algorithm SHA256).Hash.ToLower()
# 期望 be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e
```
