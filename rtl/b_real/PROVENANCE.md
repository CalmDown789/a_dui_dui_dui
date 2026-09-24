# B 侧真实 RTL 只读镜像（vendored mirror）

> ⚠️ **本目录为只读镜像，不得手工编辑。** 更新必须由 B 重新交付后整目录替换，
> 并同步更新本文件与 `SHA256SUMS.txt`。

## 来源（provenance）

| 项 | 值 |
|---|---|
| 源仓库 | `https://github.com/CalmDown789/a_dui_dui_dui.git` |
| 源分支 | `acx750-rtl` |
| 源提交 | `658c82e266439a1e749cee403beeb4ff8ad61fa3` |
| 提交标题 | `feat: add member B bit-exact FSRCNN RTL pipeline` |
| 导出方式 | `git archive --format=tar <commit> acx750_rtl` |
| 归属 | 成员B |

## 纳入范围

- `rtl/b_real/rtl/**` —— B 已交付的真实可综合 RTL 原语（compute / window / memory / postprocess）
- `rtl/b_real/docs/**` —— B 自述的接口冻结、验证状态、综合状态等
- `rtl/b_real/constraints/` —— B 的 200MHz 基准约束（仅参考）
- `tb/b_real/**` —— B 自己的 testbench（在 C 侧 xsim 环境下复现用）

## ⚠️ 明确未纳入 / 不存在

**B 尚未交付五层集成 top。** 本镜像只包含「原语 + B 自己的 TB」，
**不存在** `b_core_real` 的完整五层实现。依据：

- B v1.1 §十.5：96×54 全层 bit-exact 需在 B 交付**完整调度器 RTL**之后；
- B 仓库中 `acx750_rtl/rtl/` 下没有任何五层串联 top 文件。

因此 C 侧 `rtl/b_core_if.v` 的 `C_USE_B_REAL` 分支仍指向**占位**实现，
在 B 交付集成 top 之前**不得**声称「已接入真实 B 五层」。

## 文件清单（B 交付的可综合 RTL，17 个）

| # | 文件 | 字节 | SHA-256（前 16） |
|---:|---|---:|---|
| 1 | `rtl/b_real/rtl/compute/channel_accumulator.v` | 3271 | `0fe41f021898bb3d` |
| 2 | `rtl/b_real/rtl/compute/conv1x1_backend.v` | 1334 | `ce620623b174f97e` |
| 3 | `rtl/b_real/rtl/compute/conv3x3_backend.v` | 2314 | `4aa980d87b16b327` |
| 4 | `rtl/b_real/rtl/compute/conv5x5_backend.v` | 1826 | `8b42b7793e3680ac` |
| 5 | `rtl/b_real/rtl/compute/conv5x5_u8s8_backend.v` | 2040 | `3adf62dd591029b3` |
| 6 | `rtl/b_real/rtl/compute/dot25_pipeline.v` | 4123 | `00e73d36607d9b45` |
| 7 | `rtl/b_real/rtl/compute/dot25_u8s8_pipeline.v` | 4289 | `414232e1ae276e0b` |
| 8 | `rtl/b_real/rtl/compute/dot9_pipeline.v` | 4516 | `d9d04c34c04c7df1` |
| 9 | `rtl/b_real/rtl/compute/dsp_signed_mult.v` | 579 | `110e485573e0a8a7` |
| 10 | `rtl/b_real/rtl/compute/dsp_u8s8_mult.v` | 1102 | `b67f6416449572b3` |
| 11 | `rtl/b_real/rtl/memory/sync_parameter_rom.sv` | 918 | `97edeb75916a6fca` |
| 12 | `rtl/b_real/rtl/postprocess/pixel_shuffle2x_coord_map.v` | 922 | `92fa5436b09ef5fa` |
| 13 | `rtl/b_real/rtl/postprocess/prelu_requantize.sv` | 4978 | `0c914c8cd6e97278` |
| 14 | `rtl/b_real/rtl/window/window3x3_bram.v` | 3919 | `66e33355c3b05282` |
| 15 | `rtl/b_real/rtl/window/window3x3_stream.v` | 3281 | `81c04ada7aea57b1` |
| 16 | `rtl/b_real/rtl/window/window5x5_bram.v` | 4043 | `70be8c4df300f2cd` |
| 17 | `rtl/b_real/rtl/window/window5x5_stream.v` | 3597 | `2dabccc36786baee` |
