# H0.5 三方确认清单

本文件用于成员 A、B、C 在正式编码前确认跨角色接口。任务书已经明确的项目目标直接沿用；属于某位成员职责范围的决定，由该成员确认，其他成员只提出建议和风险。

## 任务书已经明确

- 平台：PYNQ-Z2，XC7Z020-1CLG400C。
- 输入：640×360，单通道 Y，8 bit。
- 输出：1280×720，单通道 Y，8 bit。
- 网络：3×3 卷积 `1→8→16→4`，前两层带 PReLU，末端 2 倍子像素重排。
- 权重与激活：INT8；卷积累加：INT32。
- 成员 A：板卡、overlay、Block Design、位流和板上运行。
- 成员 B：模型、训练、量化、黄金模型和测试向量。
- 成员 C：HLS 加速器、C 仿真、综合脚本和 PYNQ 驱动。

## 请成员 A 确认

1. PYNQ-Z2 是否已经能访问 Jupyter，PYNQ 镜像版本是什么？
2. base overlay 硬件工程源码是否已经取得，能否在当前 Vivado 版本打开？
3. 加速器计划连接 AXI DMA、AXI VDMA，还是直接接 AXI4-Stream Video 通路？
4. 输入流的 `TLAST` 表示一行结束还是一帧结束？是否使用 `TUSER[0]` 表示帧首？
5. 给 HLS IP 的目标时钟是多少？建议候选为 100 MHz，但由成员 A 根据 overlay 时钟规划确认。
6. AXI4-Lite 地址由谁分配、何时提供？
7. 若 H6 前 overlay 未跑通，是否按任务书切换到 Jupyter 或 C 仿真降级演示？

## 成员 B 已确认

1. 三层卷积均采用一圈零填充、stride 1 的 PyTorch 交叉相关语义，保持 640×360；末端 Pixel Shuffle 输出 1280×720。
2. 外部输入输出为 `uint8 Y`。输入原始字节在模型中按 `int8`、`zero_point=-128`、`scale=1/255` 解释；隐藏激活为逐层对称 `int8`，`zero_point=0`；末层输出重新映射到 `uint8 Y`。
3. 权重采用按输出通道对称 INT8 量化；每个输出通道有独立 scale 和 Q31 requant 乘数。隐藏激活采用逐层 scale。
4. requantize 使用最近舍入，恰好一半时远离零；Q31 乘法在 `int64` 中完成后右移 31 位。
5. 所有 INT8 输出采用饱和到 `[-128, 127]`，不允许回绕。
6. 前两层 PReLU 各使用一个标量斜率，保存为 Q1.15，在 INT32 累加结果上、requantize 之前应用。
7. 权重排列为 `[out_channel][in_channel][kernel_row][kernel_col]`（OIHW）；特征和测试向量为 HWC 行优先；Pixel Shuffle 通道 0、1、2、3 分别映射到左上、右上、左下、右下。
8. 完整量化参数和三组 640×360 测试向量已经位于 `member_b_delivery/artifacts/quant/` 与 `member_b_delivery/artifacts/test_vectors/`。每组包含输入、三层中间结果、最终输出、CRC32 和 SHA-256。

权威机器可读规格为 `member_b_delivery/artifacts/quant/quant_params.json`；人工说明见 `member_b_delivery/docs/接口与量化约定.md`。

## 成员 C 待确认后执行

- 根据成员 A 的回答确定 AXI sideband 语义、时钟和驱动访问方式。
- 根据成员 B 的回答确定 padding、requantize、PReLU 和权重解释方式。
- 将确认结果写入正式接口规格；确认前的 HLS 代码只保持可参数化，不视为冻结版。

## 等待期间可以独立推进

- 验证 Vitis HLS 命令行环境。
- 建立 HLS 顶层函数、类型定义和目录结构。
- 建立不绑定具体量化规则的小尺寸卷积参考测试。
- 编写接口与数值规则的可配置占位结构。
