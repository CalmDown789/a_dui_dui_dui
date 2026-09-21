# 成员 B 交付包

本目录是成员 B 的完整可执行交付，包含模型、配对数据、快速训练、INT8 量化、纯 NumPy 黄金模型、逐层测试向量和画质评估。

## 运行环境

- Python: 3.14.6
- PyTorch: 2.11.0+cu128
- 训练设备: cuda

## 复现命令

快速验证仓库中已经提交的交付：

```powershell
python self_test.py
python verify_delivery.py --delivery .
```

从头重新生成数据、训练、量化和评估；输出进入根目录已忽略的 `.artifacts`：

```powershell
python run_all.py --output "..\.artifacts\member_b_rebuild" --docs-dir "..\.artifacts\member_b_docs"
```

## 当前结果

- 最后记录的训练 MSE: 0.000379
- INT8 平均 PSNR: 36.059 dB
- INT8 平均 SSIM: 0.95646
- 双三次平均 PSNR: 35.712 dB
- 双三次平均 SSIM: 0.97920

详细量化和接口定义见 [`docs/接口与量化约定.md`](docs/接口与量化约定.md)，交付摘要见 [`docs/成员B交付报告.md`](docs/成员B交付报告.md)。当前数据是工程打通用合成数据；接入项目真实数据后应重新训练并重新生成指标。
