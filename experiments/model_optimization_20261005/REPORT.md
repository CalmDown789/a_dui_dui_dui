# Member A 量化模型优化实验报告

实验记录日期：2026-10-05
状态：PC 软件侧实验候选，已作为独立实验包发布；未替换冻结 A 交付

## 结论

保持网络结构 `d16/s8/m1/c16`、输入输出格式和 MAC 数不变，对冻结权重做混合数据 QAT 和低学习率 EMA-QAT 微调后，得到一个整数推理候选。独立的 DIV2K 官方验证集 100 张图上，精确整数路径平均 PSNR 从 32.4043 dB 提升到 32.4707 dB，增益 **+0.0664 dB**；按图配对 bootstrap 95% 区间为 **[+0.0445, +0.0987] dB**。这是小幅、统计区间未跨零的软件评测增益，不代表所有内容都会有同样改善。

模型计算量没有变化：仍为 `1.4681088 GMAC/帧`，按 30 fps 估算 `44.043 GMAC/s`。本次是量化画质优化，不是吞吐、延迟或帧率优化。候选仍须经过 B 的候选 ROM/Golden 回归、C 的综合实现和板卡验证后，才可讨论是否升级正式版本。

## 训练工作量与方法

- 网络：FSRCNN 主干 `d16/s8/m1/c16`，单通道 Y，x2 原生子像素输出头；层数、通道数和 MAC 统计均未改变。
- 起点：正式冻结 checkpoint。冻结 checkpoint 与量化参数按 SHA-256 核对，且始终保持只读。
- 第一阶段：T91 加 DIV2K 官方训练 HR 的 0001–0720，15 epoch QAT；20 张预先留出的内部图像用于选 checkpoint，选择 epoch 8。
- 第二阶段：从第一阶段候选继续训练 10 epoch，学习率 `1e-6`、逐 batch EMA decay `0.99`；在同一预先定义的 20 张选模图上选择 epoch 7。
- 数据隔离：DIV2K 0721–0800 未进入训练；其中 20 张用于 checkpoint 选择，另外 60 张未参与选择。官方验证 HR 0801–0900 未用于训练或选模，仅作一次最终配对评测。
- 激活校准：32 个来自训练数据的确定性 patch。
- 训练设备：NVIDIA GeForce RTX 5060 Laptop GPU。第一阶段 15 epoch 平均约 43.52 秒/epoch，即约 10 分 53 秒；第二阶段 10 epoch 平均约 44.38 秒/epoch，即约 7 分 24 秒。两阶段训练计算时间合计约 **18 分 17 秒**，不包括下载/准备数据、完整评测和交付校验。
- 在数据已准备好的情况下，复现训练约 18 分钟；官方 100 张验证集的精确整数评测在本机 CPU 上约 25–30 分钟，另需导出和交付校验时间。首次运行还需下载多 GB 的训练数据，时间取决于网络。

## 精确整数质量对照

同一数据、同一预处理下对比冻结整数模型与候选整数模型；指标为 Y 通道 PSNR/SSIM，统一裁掉 2 像素边界。增益为候选减冻结。

| 数据集/子集 | 样本数 | 冻结 PSNR / SSIM | 候选 PSNR / SSIM | PSNR 增益 |
| --- | ---: | ---: | ---: | ---: |
| 官方 DIV2K validation-HR | 100 张 | 32.4043 / 0.91402 | 32.4707 / 0.91750 | **+0.0664 dB** |
| Set5 | 5 张 | 34.0184 / 0.93784 | 34.0823 / 0.93983 | +0.0638 dB |
| Sintel 授权动画抽帧 | 8 帧 | 43.9158 / 0.97640 | 45.0340 / 0.97983 | +1.1182 dB |
| Big Buck Bunny 开发帧 | 8 帧 | 46.3658 / 0.98862 | 48.1319 / 0.99409 | +1.7661 dB |
| DIV2K 内部未参与选模子集 | 20 张 | 31.6508 / 0.91693 | 31.6947 / 0.91911 | +0.0438 dB |

证据边界：

- **最有代表性的独立质量结果是 DIV2K 100 张，增益约 0.066 dB。** 该集合仅做一次最终评估，未用于训练或选模。LR 图像由 HR 依据本项目预处理生成：Pillow bicubic ×2 的 Y 通道流程；不是 DIV2K 官方 MATLAB-bicubic LR track。
- Set5 只有 5 张；且仓库中的早期其他探索曾使用 Set5，不能单独视为完全独立证据。
- Sintel 为 CC BY 3.0 动画抽帧，Big Buck Bunny 为开发集；它们的较大增益是内容相关的探索结果，不能外推为一般场景增益。BBB 样本不是最终未触碰留出集。
- DIV2K 内部 80 张的汇总含 20 张选模图，不称为独立测试；表中只列 20 张未参与选模且做过精确整数复测的子集。
- 候选 FP32 并未在所有来源上优于冻结模型。本实验结论针对**候选整数推理路径**，不是浮点模型全面提升。
- DIV2K 原图保留各自版权，官方页面仅允许学术研究用途；原始数据未放入 Git，也不随候选分发。

## 候选身份与整数交付核验

- 冻结 checkpoint SHA-256：`bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5`
- 冻结量化参数 SHA-256：`f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a`
- 最终候选 checkpoint SHA-256：`10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`
- 候选量化参数 SHA-256：`12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`
- 全尺寸合成输入的候选整数输出：`1920×1080`、2,073,600 字节，SHA-256 `d1d9a6fb09d3fe84a6538df2a68107a216d79586ae3c296fa5d8706c616dbef1`。
- 候选 QDQ 与整数全尺寸输出逐字节匹配 2,032,785 / 2,073,600；其余字节最大差异 1，MAE 为 0.01968。
- `verify_candidate_delivery.py --recompute-full` 已通过：六组小尺寸逐层测试向量和全尺寸逐层输出/哈希均复算一致；正式冻结资产未变。
- 2026-10-08 已将 checkpoint、训练日志、完整量化权重包、六组 96×54 向量、全尺寸 Golden 和逐文件哈希整理至 [`candidate_delivery/R0_QAT_EMA_seed20261006_v2/`](candidate_delivery/R0_QAT_EMA_seed20261006_v2/)。该包状态为 `EXPERIMENTAL_NOT_RELEASED`，是给 B 做候选验证的交接材料，不替换旧包或正式 R0。
- 候选包自身哈希清单为 `bundle_manifest.json`。该文件不包含自身哈希；验证时先校验清单中的文件，再运行 `verify_candidate_delivery.py --recompute-full` 复算整数向量和全帧阶段输出。

## 下一步验收门槛

1. 由 B 使用候选权重 ROM 和候选整数 Golden，运行小图、逐层及整帧逐字节回归；基线模型通过不能替代候选回归。
2. B 的候选数值回归通过后，由 C 基于候选 ROM 做综合、实现和时序检查；权重更新仍需验证初始化映射与资源/时序。
3. 再进行板上图像与接口验证。PC 软件参考结果不等同于 RTL、bitstream 或板卡验收。
4. 团队确认上述证据后，才能决定是否升版。当前冻结标签和正式 A 资产均未替换，B/C 文件也未修改。

## 复现与证据位置

代码和命令见同目录 [README.md](README.md)。本机运行数据位于：

- 最终训练日志、参数和 hash 清单：`.data/model_optimization/qat_ema_refine_20261006/`
- 官方 DIV2K 100 张最终评测：`.data/model_optimization/qat_ema_refine_20261006/official_valid_eval/`
- Set5、Sintel：`.data/model_optimization/qat_ema_refine_20261006/independent_eval_final/`
- DIV2K 内部集、BBB：`.data/model_optimization/qat_ema_refine_20261006/evaluation_div2k_bbb/`
- 可供 B 取用的实验候选包（权重、checkpoint、训练日志、向量和全尺寸 Golden）：[`candidate_delivery/R0_QAT_EMA_seed20261006_v2/`](candidate_delivery/R0_QAT_EMA_seed20261006_v2/)

数据来源：[DIV2K 官方数据页](https://data.vision.ee.ethz.ch/cvl/DIV2K/)；[Sintel 下载页](https://durian.blender.org/download/)；[Sintel 授权与署名](https://durian.blender.org/sharing/)。如对外使用 Sintel 派生评测材料，应保留 Blender Foundation 署名。
