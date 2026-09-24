# ACX750 FSRCNN 超分系统

项目目标是使用 ACX750-200T（`xc7a200tfbg484-2`）将 960×540 单通道 Y 图像放大到 1920×1080。本文汇总截至 2026-09-24 的可复核结果；不同阶段的仿真、实现和板测数据分别标明，不将计划或估算写成实测结论。

## 当前结论

| 阶段 | 结果 | 证据与边界 |
|---|---|---|
| A：模型、量化与数据 | 已冻结 `d16/s8/m1/c16`；Set5 平均 PSNR：双三次 32.6398 dB、FP32 34.1202 dB、INT8/INT16 34.0190 dB | [A交付报告](docs/成员A交付报告.md)、[量化指标](artifacts/evaluation/summary.json) |
| B+C：整数仿真 | 五层真实网络全尺寸输出 2,073,600 字节与整数 Golden 一致，失配 0 | A Golden SHA-256：`be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`；仿真采用 XSim 2022.2 `-O0`，详见 [下游验证记录](docs/成员A下游验证状态_2026-09-24.md) |
| C：100 MHz 板测 | 已下载 bitstream；板上 UART 回读完整单帧，2,073,600 字节与 Golden 逐字节一致，失配 0 | [板测报告](docs/BOARD_TEST_REPORT_100MHZ_2026-09-24.md)。UART 回传约 22.43 秒/帧是传输时间，不是 CNN 计算帧率 |
| B：150 MHz 时序试验 | 推荐实现策略候选完成布线，WNS/TNS `+0.132/0 ns`；资源 LUT 28,078、FF 48,498、RAMB36/18 `226/8`、DSP48E1 `394` | [时序试验记录](docs/MEMBER_B_150MHZ_TIMING_OPT_2026-09-24.md)。这是 B 的实验候选，不等于 C 的 150 MHz 板测或正式 RTL 集成 |

因此，项目已有模型、整数全帧对拍、100 MHz 单帧上板一致性和 150 MHz 完成布线的时序数据，形成了可展示、可复核的阶段成果。当前不能据此宣称 1080p30 已实现：150 MHz 结果裕量较小，且没有 150 MHz 板测或持续视频吞吐记录。

## 冻结模型与接口

FSRCNN 主干为 `Conv 1→16, 5×5`、`Conv 16→8, 1×1`、一个 `Conv 8→8, 3×3` mapping 层、`Conv 8→16, 1×1`；输出头为原生稠密 `Conv 16→4, 5×5 + PixelShuffle×2`。该输出头是直接训练的子像素卷积，不宣称与 9×9 反卷积逐权重等价。

权重为逐输出通道对称 INT8，激活为逐层对称 INT16，偏置及累加为 INT32，PReLU 参数为 Q1.15。全尺寸整数 Golden、输入和清单位于 [`artifacts/full_integer_golden/`](artifacts/full_integer_golden/)；RTL 使用的打包参数位于 [`rom/member_a_d16_s8_m1_c16/`](rom/member_a_d16_s8_m1_c16/)。完整整数交付和权重/训练记录分别见 [`artifacts/member_a_integer_delivery_d16_s8_m1_c16.zip`](artifacts/member_a_integer_delivery_d16_s8_m1_c16.zip) 与 [`artifacts/member_a_weights_and_logs.zip`](artifacts/member_a_weights_and_logs.zip)。

模型计算量为 1.4681088 GMAC/帧，30 fps 对应 44.043264 GMAC/s；任务书中的 133.2 GMAC/s 和约 3.02× 余量是建立在 DSP 打包、频率和利用率假设上的理论估计，不是板测吞吐。

## 分工与下一阶段

- A：模型、量化参数、逐层向量与整数 Golden 已冻结；下游使用状态见 [A验证记录](docs/成员A下游验证状态_2026-09-24.md)。
- B：五层流式 RTL 与时序优化试验；150 MHz 推荐候选及对照数据见 [B试验记录](docs/MEMBER_B_150MHZ_TIMING_OPT_2026-09-24.md)。
- C：板级集成、约束、bitstream 和实体板验证；已完成 100 MHz 单帧对拍，后续按板卡完整约束验证更高频率及连续帧运行。

下一阶段是基于同一已验证功能基线开展 150 MHz 板级验证，并记录连续帧完成时间和系统接口行为；目标是增加时序裕量、确认可重复运行。该工作正在按计划推进，当前记录未将其描述为已完成或已遇到阻塞。

## 代码与复核

- `rtl/`、`rom/`、`constr/`、`tb/`：当前 B+C 集成所需 RTL、参数 ROM、约束与仿真测试文件。
- `scripts/`：仿真、数据准备、综合与报告校验脚本。
- `experiments/l5_timing_opt_20260924/`、`member_b_evidence/timing_opt_netdelay150/`：150 MHz 推荐策略的复现脚本和精简原始报告。
- `docs/BOARD_TEST_REPORT_100MHZ_2026-09-24.md`：C 板测数据与判定边界。

来源版本：A 冻结交付 `member-a-v1.0.1`（全尺寸 Golden 来源提交 `98c82f3`）；B 150 MHz 时序试验分支提交 `4f93a87`；C 板测报告随 `c-side-latest` 最新提交 `4f1f73e` 同步。板测报告中的 RTL 源树哈希为 `618a532ab842e9a7b33b1f695689e446f37cebf6`。这些来源信息用于追溯，不代表各分支试验均已合并为同一正式版本。
