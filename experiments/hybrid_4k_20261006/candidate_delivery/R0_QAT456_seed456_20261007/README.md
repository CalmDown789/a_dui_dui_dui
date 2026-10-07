# R0-QAT seed456 独立整数候选包

状态：`EXPERIMENTAL_NOT_FORMAL_A_DELIVERY`。这是供审查和后续独立对拍使用的 A 侧候选；不替换正式冻结 R0，也不代表 B RTL、Vivado 综合、FPGA 或板卡验收通过。

## 固定规格

- 网络：`FSRCNNSubpixel-d16-s8-m1-c16-x2`；输入为 960×540 单通道 Y8，CNN 输出为 1920×1080 Y8。
- 权重为逐输出通道对称 signed INT8；隐藏激活 INT16；偏置与累加 INT32；PReLU 为 Q1.15，requant 为 Q31；最近舍入、中点远离零并饱和。
- 权重布局 OIHW，特征布局 HWC 行优先；PixelShuffle 顺序为左上、右上、左下、右下。
- seed456 候选由同结构的冻结 R0 权重初始化，并经独立训练/校准流程生成。候选与 R0 的量化参数不可混用。

## 包内内容

- `quant/`：`quant_params.json` 及各层 INT8 权重、INT32 bias、PReLU 参数，提供 `.npy`、小端 `.bin`、Verilog `.mem` 和 Vivado `.coe` 格式。
- `test_vectors/`：96×54 的 zero、impulse、ramp、random 四组输入与逐层 INT32/INT16、PixelShuffle phase 和 uint8 输出参考。
- `full_integer_candidate_gold/`：确定性 960×540 输入、输入 ROM 与 1920×1080 输出及逐层摘要；测试输入为程序生成，不是公开视频帧。
- `evaluation/`：既有 FFmpeg/Pillow 留出图像的逐图指标和评测汇总。
- `training/`：seed456 的 QAT `r0_qat_best.pth`、逐 epoch MSE CSV 与路径无关的训练摘要。checkpoint SHA-256 为 `123ba381d852a3eb5821a41ee417697bcbc50ece764506d3836b49567a267d02`；底层训练数据及初始 checkpoint 未打包。
- `bundle_manifest.json`：本次发布包内文件的大小、CRC32 和 SHA-256。`source_provenance/` 保留原始候选 manifest 与训练摘要；其中旧 manifest 的 `bundle` 字段是历史本机暂存路径，当前发布目录以本文件和根目录的新 manifest 为准。

## 哈希关联

- 候选 `quant/quant_params.json`：SHA-256 `f2d6c4865b295f6a02c67a43ab2fb00cd36ede723ee8743575f6746f52d924ac`。
- 冻结 R0 `quant_params.json`：SHA-256 `f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a`。
- 原始来源候选 bundle manifest：SHA-256 `13cdb3b35cf6bf11f44afa9a7bafb390e63e7b4e6609ff75cd6a08a52e096984`；其哈希也记录在 [10 段视频评测运行清单](../../results/full_10_clips/run_manifest.json) 中。
- QAT 训练使用 seed 456、180 个训练帧、10 个验证帧、5 个 epoch；最佳轮次为第 2 轮。逐 epoch 指标见 `training/qat_training_log.csv`，源运行摘要的 SHA-256 记录在 `source_provenance.json` 中。
- 1,240 帧对比结果及统计边界见[完整评测报告](../../R0_VS_QAT456_VIDEO_REPORT_2026-10-06.md)。结果显示候选相对冻结 R0 的平均 Y-PSNR 增益约 0.1034 dB；这是小幅 PC 整数参考结果，不足以晋级替换正式 R0。

## 验证

从仓库根目录运行（需 Python 环境中已安装项目所需依赖）：

```powershell
$env:PYTHONPATH = '.;src'
python -m experiments.hybrid_4k_20261006.verify_candidate_bundle `
  --bundle-dir experiments/hybrid_4k_20261006/candidate_delivery/R0_QAT456_seed456_20261007 `
  --allow-published
```

验证器检查发布 manifest 对目录的完整覆盖、所有文件摘要、QAT checkpoint/日志与评测摘要的哈希关联，并用 A 侧整数参考重新计算四组 96×54 向量及 960×540 全尺寸 Golden。即使全部通过，也只证明这份候选包与 A 侧 Python 整数参考一致；B 侧必须使用整套候选量化参数、权重、向量和 Golden 独立对拍，不能只替换 R0 权重 ROM。

原始 UVG 视频及衍生视频没有打包或提交；测试向量和全尺寸 Golden 输入均为合成数据。
