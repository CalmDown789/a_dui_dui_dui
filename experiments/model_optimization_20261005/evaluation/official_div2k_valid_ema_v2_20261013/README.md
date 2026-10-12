# EMA v2 DIV2K 整数评测证据

评测日期：2026-10-13
状态：一次性软件整数评测复跑与来源审计通过；非 FPGA/板卡验收。

## 评测范围

- 图像：DIV2K 官方 validation HR ID 0801–0900，共 100 张；没有用于训练或 checkpoint 选择。
- 输入退化：取 Y 通道、偶数边界裁切、Pillow bicubic ×2；这不是 DIV2K 官方 MATLAB-bicubic LR track。
- 指标：逐图 Y PSNR/SSIM，边界裁 2 像素后计算，再对 100 张作算术平均。
- 结果：冻结 R0 整数平均 PSNR 32.4043169 dB / SSIM 0.9140168；EMA v2 整数平均 PSNR 32.4707118 dB / SSIM 0.9174987。配对 PSNR 差值 +0.0663949 dB，bootstrap 95% 区间 `[+0.0444671, +0.0986952] dB`。100 张逐图 PSNR 与 SSIM 均有微小提升。
- 该结果仅支持这组数据与处理约定下的指标比较；可视化抽查差异不明显到足以声称普遍可见的主观改善。不能据此推断所有自然场景、视频时序、RTL 或板端画质。

## 文件

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `per_image_metrics.csv` | 100 张逐图指标与模型间差值 | `29dd6139d9e1023e0a48cfd220668dd7324b657f6f13aa9c53876cf71761b979` |
| `summary.json` | 评测器原始汇总结果 | `5fda98c0b4063dcedc8204dc733bee4a7ace568d5a07e3a26ef6e57258e33b3e` |
| `audit_summary.json` | 独立重算均值/配对 bootstrap、图像集合身份和候选/冻结模型哈希；状态 `PASS_SOURCE_IDENTITY_AND_PER_IMAGE_SUMMARY_REPRODUCED` | `093f8eace7b20b71244de5a2c13f38b197e7d67db004b85b43dbf002522aacad` |
| `visual_selection.json` | 视觉抽查所选图像、增益排序和裁切坐标 | `a95035491b14799d88c9f3f458e7ad9ca1f75d4bb6a7b18de4efdbf042447e77` |

审计绑定的候选 checkpoint SHA-256 为 `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`，候选 `quant_params.json` SHA-256 为 `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`。冻结 R0 checkpoint 与量化参数的 SHA-256 分别为 `bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5` 和 `f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a`。

原始 DIV2K 图像及由其生成的可视化裁切不放进仓库。视觉审查接触表与审计工作文件保存在本机忽略目录 `.data/member_a_task_20261013/ema_visual_review/`，不随本证据包分发。

## 复现

在已安装项目依赖且官方 HR 数据位于忽略目录 `.data/model_optimization/datasets/div2k_official_valid/` 的仓库根目录执行：

```powershell
$out = ".data\model_optimization\div2k_official_valid_ema_v2_rerun_20261013"
$audit = ".data\member_a_task_20261013\ema_audit"
$visual = ".data\member_a_task_20261013\ema_visual_review"

python experiments\model_optimization_20261005\evaluate_official_div2k_valid.py `
  --hr-dir .data\model_optimization\datasets\div2k_official_valid\HR `
  --dataset-manifest .data\model_optimization\datasets\div2k_official_valid\manifest.json `
  --candidate-run experiments\model_optimization_20261005\candidate_delivery\R0_QAT_EMA_seed20261006_v2\training `
  --candidate-checkpoint-name candidate_ema_qat_fp32.pth `
  --candidate-quant experiments\model_optimization_20261005\candidate_delivery\R0_QAT_EMA_seed20261006_v2\quant `
  --output-dir $out

python experiments\model_optimization_20261005\audit_official_div2k_results.py `
  --evaluation-dir $out `
  --hr-dir .data\model_optimization\datasets\div2k_official_valid\HR `
  --dataset-manifest .data\model_optimization\datasets\div2k_official_valid\manifest.json `
  --candidate-dir experiments\model_optimization_20261005\candidate_delivery\R0_QAT_EMA_seed20261006_v2 `
  --r0-quant artifacts\quant `
  --output-dir $audit `
  --visual-dir $visual
```

评测复跑的逐图 CSV 与汇总 SHA-256 分别为本表前两项哈希；审计还确认 100 个图像 ID、当前图像集合和四个模型资产身份与此前一次性评测一致。复现时间取决于 CPU/GPU 和本地数据准备情况。
