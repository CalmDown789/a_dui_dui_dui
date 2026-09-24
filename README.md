# ACX750-200T 成员 A FSRCNN 子像素模型交付

> **小组 PPT 统一口径与项目全阶段记录：**[《技术路径与阶段总结（2026-09-24）》](docs/技术路径与阶段总结_2026-09-24.md)。报告按调研、板卡基线、任务书修订、A/B/C 实现、仿真与布线、1080p→4K 路线排列；所有结果标明证据层级。当前完整五层网络尚未完成板上验收。

已完成成员 A 的算法与数据交付，用于小梅哥 ACX750-200T 上的 540p 到 1080p 超分项目。模型为 `d=16 / s=8 / m=1 / c=16` 的 FSRCNN 主干，输出层直接训练为稠密 `5×5 Conv 16→4 + PixelShuffle×2`。它不是 9×9 反卷积的逐权重等价变换。

## 冻结规格

- 输入：`960×540`，8-bit 灰度 Y，HWC 行优先；
- 输出：`1920×1080`，8-bit 灰度 Y；
- 权重：逐输出通道对称 INT8，OIHW；
- 激活：逐层对称 INT16；
- 偏置与累加：INT32，溢出饱和；
- PReLU：逐通道 Q1.15；
- 算力：`1.4681088 G MAC/帧`，30fps 为 `44.043264 GMAC/s`；
- 理论余量：相对 `133.2 GMAC/s` 为约 `3.02×`。

## 环境

```powershell
C:\Python314\python.exe -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 完整复现

下载 T91 与 Set5 原始图像并在本地生成 ×2 训练块，训练 FP32 模型、校准量化参数、必要时执行 5 epoch QAT，并生成全部交付物：

```powershell
.\.venv\Scripts\python.exe run_all.py
```

验证已经提交的模型、权重、格式、测试向量、全尺寸输出、指标和哈希：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\verify_delivery.py
```

只交接整数实现时，可直接下载 `artifacts/member_a_integer_delivery_d16_s8_m1_c16.zip`。压缩包包含 `quant_params.json`、INT8/INT32/Q1.15 权重参数、整数黄金参考和四组逐层向量；解压后运行：

```powershell
python scripts\verify_integer_delivery.py
```

审核模型质量证据时，可直接下载 `artifacts/member_a_weights_and_logs.zip`，其中集中提供 FP32 checkpoint、模型契约、50轮训练日志、Set5逐图指标、汇总指标及量化参数。

训练数据保存到 `.data/` 且不会提交。任务书原件保存在 `docs/source/`，接口约定、算力核算和成员 A 报告位于 `docs/`。

本次固定种子训练的 Set5 平均结果为：双三次 32.6398 dB、FP32 34.1202 dB、量化 34.0190 dB；量化损失 0.1012 dB，因此未触发 QAT。完整逐图 PSNR/SSIM 见 `artifacts/evaluation/set5_metrics.csv`。

## 职责边界

本交付不包含 RTL、板级约束、Vivado 工程或 bitstream。成员 B 可直接读取 `artifacts/quant/quant_params.json`、各层 `.mem/.coe` 权重以及 `artifacts/test_vectors/` 完成 RTL 对拍；成员 C 负责板卡工程、ILA、时序收敛和上板结果导出。
