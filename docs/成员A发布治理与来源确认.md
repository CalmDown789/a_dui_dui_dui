# 成员 A 发布治理与生成来源确认

## 确认结论

本文件是成员 A 对 C 分支 `4827f19` 所提发布治理问题的正式答复。成员 A 确认：`main` 上的回退只用于把不同成员的工作隔离到各自分支，不代表模型、权重、量化参数或整数 Golden 被技术撤回。

成员 A 的正式发布位置是 GitHub `member-a` 分支及其版本标签。核心数据交付固定在提交 `98c82f394bdfba85bc2959bede9760edc4d6862f`；`member-a-v1.0` 指向该提交。后续 `member-a-v1.0.1` 只补充本份来源和治理说明，核心数据文件与 `v1.0` 逐字节相同。

因此，C8 不应从 `main` 取 A 的验收数据，而应从冻结标签取数。B 已完成的 960×540 整帧逐字节对拍结论继续有效。

## 权威文件和哈希

| 内容 | 仓库路径 | SHA-256 |
|---|---|---|
| FP32 checkpoint | `artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth` | `bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5` |
| 训练日志 | `artifacts/model/training_log.csv` | `554de0b4364ef1af0fc7bd3cb9f20146362c2e9ead298d5d0dbb96d722f7f373` |
| 量化参数 | `artifacts/quant/quant_params.json` | `f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a` |
| 960×540 原始 Y 输入 | `artifacts/full_integer_golden/input_960x540_y_u8.bin` | `aca4fb6f89accc388cede8f5fddaea79026a1fd507cdad6a844236941807e0f4` |
| 2^19 深输入 ROM | `artifacts/full_integer_golden/input_rom_2p19_u8.mem` | `f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9` |
| 1920×1080 整数 Golden | `artifacts/full_integer_golden/output_1920x1080_y_u8.bin` | `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e` |
| 权重与日志 ZIP | `artifacts/member_a_weights_and_logs.zip` | `c80cf1342014cf84382ff9bd09f6705db19d43fa7cdb292ba634dbde94a32f8a` |

最终整数输出长度固定为 `2073600` 字节，CRC32 固定为 `87d353f1`。

## `main` 回退原因

提交 `98c82f3` 曾短暂快进到 `main`。随后项目明确要求每位成员使用独立分支，且不得修改其他成员文件，因此在 `main` 上使用普通 revert 恢复原文件树，同时保留 Git 历史；没有强推或重写其他成员提交。

该回退属于仓库治理操作，不是以下任何原因：

- 不是模型指标不合格；
- 不是权重或量化参数作废；
- 不是整数 Golden 计算错误；
- 不是 B 的整帧 XSim 对拍失败。

正式 A 交付从此只在 `member-a` 分支和 `member-a-v*` 标签发布。

## Checkpoint 生成来源

checkpoint 由本仓库 `run_all.py` 调用 `src/member_a/pipeline.py` 和 `src/member_a/training.py` 训练生成，不是从论文或第三方仓库下载的预训练权重。

- 模型：`FSRCNNSubpixel-d16-s8-m1-c16-x2`；
- 数据来源：`https://github.com/suxrobGM/fsrcnn/archive/refs/heads/main.zip`；
- 训练集：T91，共 91 张图，文件集合摘要 `d903f5e8e3c43c92fc5009d33378de41a3a651d05cd86f79339843ebaf7af65c`；
- 验证集：Set5，共 5 张图，文件集合摘要 `b9cbe9ec0e9b09f440d75f73870598005439f54d4b9dc8a33e801fd2ecb3d79e`；
- 颜色与范围：YCbCr 的 Y 通道，归一化到 `[0,1]`；
- 随机种子：123；
- 优化器：Adam；损失：MSE；batch：16；
- 训练：最多 50 epoch，第 31 epoch 起学习率下降 10 倍；
- checkpoint 保存规则：保存 Set5 PSNR 最优权重；本次最优点为第 50 epoch，Set5 平均 PSNR `34.1201813371 dB`；
- checkpoint 内部元数据包含相同的网络配置、`seed=123` 和上述最佳 PSNR。

训练集只用于训练，Set5 只用于验证和最终指标；没有用训练集指标冒充验收结果。量化相对 FP32 的 Set5 PSNR 损失为 `0.101153 dB`，未触发 QAT。

## 960×540 输入图生成来源

全尺寸输入不是 Set5 图片，也不是受版权约束的自然图像。它由 `src/member_a/data.py` 中的 `procedural_u8(width, height, seed)` 确定性生成，调用参数固定为：

```python
procedural_u8(960, 540, seed=123)
```

生成内容由水平/垂直正弦项、环形纹理、棋盘纹理和固定种子高斯噪声组合，最后执行最近取整并饱和到 uint8。相同 NumPy 实现和种子会生成相同的 `518400` 个 Y 字节。

`input_rom_2p19_u8.mem` 的地址 `0..518399` 按 HWC 行优先保存上述输入；地址 `518400..524287` 共 `5888` 个位置填零。卷积越界 padding 同样为整数零。

## Golden 生成链

1. 从冻结 checkpoint 导出逐输出通道对称 INT8 权重、INT32 偏置、Q1.15 PReLU 和 Q31 重量化参数；
2. 使用上述确定性 960×540 uint8 输入；
3. 由 `src/member_a/fixed_reference.py` 逐层执行整数卷积、PReLU、重量化、显式饱和和 PixelShuffle×2；
4. 生成 `output_1920x1080_y_u8.bin`；
5. `scripts/verify_full_integer_golden.py --recompute` 重新计算所有整数层并比对每层 CRC32/SHA-256；
6. 仓库单元测试、整数交付检查和整体验收检查全部通过。

FP32/QDQ 文件只用于算法效果分析，C8 的 bit-exact 验收必须使用本文件列出的整数 Golden。

## 给 C 的取数规则

- 取数来源：冻结标签 `member-a-v1.0.1`；
- 输入：`artifacts/full_integer_golden/input_rom_2p19_u8.mem`；
- 期望输出：`artifacts/full_integer_golden/output_1920x1080_y_u8.bin`；
- 量化唯一事实来源：`artifacts/quant/quant_params.json`；
- 校验时先核对本文件中的 SHA-256，再运行全尺寸逐字节比较；
- 不得从 `main`、FP32 输出或 QDQ 输出替代上述文件。
