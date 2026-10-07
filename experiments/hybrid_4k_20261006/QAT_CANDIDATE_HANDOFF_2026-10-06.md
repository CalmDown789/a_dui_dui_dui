# 成员 A：R0-QAT 整数候选交接说明

日期：2026-10-06

版本提示：本文描述较早的 `quant_cross_eval_adapt456qat5/R0adapt456_QAT5` seed456 包，`quant_params.json` SHA-256 以 `13f912c9` 开头。它不是 1,240 帧 R0/QAT seed456 视频报告使用的候选；后者的量化参数 SHA-256 以 `f2d6c486` 开头，独立发布目录见 `candidate_delivery/R0_QAT456_seed456_20261007/README.md`。

## 交付状态

此包是成员 A 的**实验候选**，不是正式 R0 更新，也未经过成员 B RTL、Vivado 综合、实现或 FPGA 板卡验收。它保留冻结 R0 的网络形状和整数接口，目的是供团队评审是否安排独立的 B 侧候选分支验证。

候选位置：

```text
.data/hybrid_4k_20261006/quant_cross_eval_adapt456qat5/R0adapt456_QAT5/
```

其中 `quant/` 为整数参数和权重包；`test_vectors/` 为 96×54 四类输入的逐层整数参考；`full_integer_candidate_gold/` 为确定性 960×540 输入及全尺寸逐层整数 Golden；`bundle_manifest.json` 记录包内文件摘要。该目录受 `.gitignore` 排除，**没有提交或推送到 GitHub**。UVG 原视频和衍生演示遵循 CC BY-NC，不随仓库分发。

## 模型与定点定义

结构维持 `FSRCNNSubpixel d16/s8/m1/c16`：输入单通道 960×540 uint8，依次经过 feature 5×5、shrink 1×1、一个 mapping 3×3、expand 1×1、dense subpixel 输出头 5×5 与 PixelShuffle×2；输出单通道 1920×1080 uint8。整数格式为权重 INT8、隐藏激活 INT16、偏置和累加 INT32、PReLU Q1.15、重定量 Q31；卷积权重布局 OIHW，特征 HWC 行优先，PixelShuffle 顺序 top-left、top-right、bottom-left、bottom-right。

候选由冻结 R0 FP32 权重初始化，以 Beauty/HoneyBee/YachtRide 180 个 FFmpeg 降质帧适配，Jockey 10 帧校准/验证，seed 456 再做 5 轮 STE QAT。候选未替换正式 R0 的模型、量化包、ROM 或 Golden。

## 与冻结 R0 的关系

自动对比结果：

```text
.data/hybrid_4k_20261006/quant_candidate_compatibility_vs_frozen.json
```

两包的 schema、I/O 形状、层次顺序、卷积核、padding、OIHW 形状、dtype、舍入、PixelShuffle 顺序一致，因此属于**格式和形状兼容**；但数值参数不同，不能混用：

| 层 | INT8 权重变化 | INT32 偏置变化 | Q1.15 PReLU 变化 |
| --- | ---: | ---: | ---: |
| feature | 21 / 400 | 16 / 16 | 11 / 16 |
| shrink | 0 / 128 | 8 / 8 | 5 / 8 |
| mapping0 | 26 / 576 | 8 / 8 | 3 / 8 |
| expand | 8 / 128 | 16 / 16 | 9 / 16 |
| subpixel | 279 / 1600 | 4 / 4 | — |

所有层的逐输出通道权重 scale 与 Q31 multiplier 都变化；四个中间激活边界的 scale 改变，输入及最终 uint8 输出 scale 相同。`shrink` 的 INT8 权重字节虽完全相同，但其逐通道 scale 全变了。因此不得只覆盖权重 ROM；如开展 B 侧验证，必须把候选 `quant/`、全部 ROM、测试向量及 Golden 作为同一版本配套使用。

## 软件整数结果

CPU `FixedReference` 候选包完整性复核结果：134 个包内文件哈希通过、48 组 96×54 逐层输出逐字节一致、12 个全尺寸逐层摘要一致。实现和指标详情见本目录的 [`MODEL_OPTIMIZATION_REPORT_2026-10-06.md`](MODEL_OPTIMIZATION_REPORT_2026-10-06.md) 与 [`README.md`](README.md)。

两套互相独立的 25 帧留出协议中，seed 456 整数候选相对同协议冻结 R0 整数基线平均增加：FFmpeg 合成降质 `+0.3227 dB`，Pillow 合成降质 `+0.3037 dB`。按 Bosphorus / ReadySetGo / ShakeNDry 分组，seed 456 的配对 PSNR 增益分别为：

| 协议 | Bosphorus | ReadySetGo | ShakeNDry |
| --- | ---: | ---: | ---: |
| FFmpeg | +0.4711 dB | +0.2378 dB | +0.1960 dB |
| Pillow | +0.4993 dB | +0.2243 dB | +0.1229 dB |

这些是三个 UVG 序列、合成 540p 输入、有损 HEVC 解码参考上的软件 Y 平面结果，不外推为任意视频表现。Set5 2×兼容性抽查为 34.0165 dB，对照冻结 R0 整数包 34.0183 dB（−0.0018 dB）；这不是 4×视频主指标。

同一 Bosphorus 8 帧（源帧 0、10、…、70）的视频软件测试中，QAT 整数候选相对冻结 R0 整数包平均高 `+0.3861 dB`，8 帧均为正，范围 `+0.2935` 至 `+0.4263 dB`。逐帧表：

```text
.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_integer_baseline_vs_qat456_8frames.json
```

冻结整数、QAT 整数两段输出均为 3840×2160 YUV420，8 帧 MP4 已成功解码；原始 YUV 字节数、逐帧图及摘要的 30 项文件 SHA-256 清单均已核验。仍只是 PC 端软件参考，不表示实时帧率或硬件画质。

## 低算量备选：R1-QAT（不是 R0 的直接替换包）

另完成两个 R1-QAT seed 的同条件试验。R1 将 R0 的 subpixel 输出头从 5×5 改为 3×3，静态 MAC 从 `1.4681088` 降至 `0.9372672 GMAC/帧`（−36.2%）。两个 seed 各做 5 轮 QAT；相对 R1 PTQ 的 50 帧均值分别改善 `+0.2423 dB`（seed123）和 `+0.2385 dB`（seed456）。但与冻结 R0 整数基线配对时，差值仍如下：

| 协议 / seed | 25 帧均值 delta | Bosphorus | ReadySetGo | ShakeNDry |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg / 123 | −0.2972 dB | −0.0881 dB | −0.3963 dB | −0.5174 dB |
| FFmpeg / 456 | −0.2921 dB | −0.0629 dB | −0.4108 dB | −0.5133 dB |
| Pillow / 123 | −0.2370 dB | +0.0038 dB | −0.3562 dB | −0.4802 dB |
| Pillow / 456 | −0.2495 dB | −0.0084 dB | −0.3711 dB | −0.4887 dB |

QAT 找回了 R1 的量化误差，但没有消除 3×3 head 的场景依赖画质损失。seed456 包在 `.data/hybrid_4k_20261006/quant_r1_ptq_vs_qat_seed456/R1_QAT/`，内含 R1 专属 `quant_params.json`、权重、四组 96×54 向量、全尺寸整数 Golden 和 `bundle_manifest.json`；134 项文件、48 组逐层输出和 12 个全尺寸阶段均已通过 Python 整数参考复核。README 也在该包内。

该 R1 包的 `subpixel` 是 3×3、padding=1，与正式 R0 的 5×5、padding=2 不同。它只能在 B 支持该结构的独立候选路径上试验；不能把它当作冻结 R0 的 ROM-only 更新，也不能和 R0 Golden/ROM 混搭。没有对 R1 完成 B RTL 对拍、综合/时序或上板验证。

两个 R1 seed 的 15 轮、30 轮 QAT 留出对照显示：15→30 轮仍有约 `+0.019…+0.047 dB` 小幅增益，但相对冻结 R0 仍落后约 `0.19 dB`；ReadySetGo、ShakeNDry 分别仍落后约 `0.31 dB`、`0.41–0.44 dB`。两 seed 间 30 轮结果一致到 `0.007 dB` 以内，说明趋势可复现且收益递减。这不足以支持 R1 替换正式模型；没有生成新的候选交付包。逐图报告见忽略目录 `.data/hybrid_4k_20261006/r1_qat_paired_metrics/seed{123,456}_{15ep,30ep}_vs_*.json`。

## 推荐的 B 侧接入门槛

若团队决定评估，建议另建实验分支，不覆盖冻结基线：

1. 复制候选整数包为一个独立、有版本标识的 ROM/Golden 组；先检查所有 `.mem/.coe` 是从同一候选包重新生成。
2. 用候选 96×54 四类向量逐层对拍，逐层核对 MAC、PReLU、requant、饱和和 PixelShuffle。
3. 小图全部逐字节通过后再跑候选全尺寸 Golden；失败时保留原始日志，不覆盖正式结果。
4. 由 B 侧在其确认的 XSim/Vivado 流程验证，由 C 侧另行评估资源、时序和板上行为。

候选没有获得团队采纳前，正式 R0、B/C 文件和共享 GitHub 分支均保持不变。
