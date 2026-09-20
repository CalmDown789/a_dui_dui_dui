# 可配置定点后处理阶段记录

## 已实现能力

- 逐输出通道 requant multiplier、shift、zero point；
- 最近值远离零、向零截断、向下取整三种舍入；
- 可选 INT8 饱和或直接低位收窄；
- 逐输出通道 PReLU multiplier、shift；
- 可选择 PReLU 位于 requant 前或后；
- 输入 INT32 流，输出 INT8 流；数据顺序均为 `spatial_position → channel`。

这些是可配置能力，不代表成员 B 已选择任何具体组合。

## C 仿真

覆盖两个用例：

1. PReLU 位于 requant 前、向零截断、正负数及饱和边界；
2. 不启用 PReLU、最近值远离零及饱和边界。

结果：`POSTPROCESS_TEST_PASS tests=2`。

## HLS 综合结果

目标器件：`xc7z020-clg400-1`。自测时钟约束：10 ns。

| 指标 | 结果 |
|---|---:|
| 位置/通道扁平循环 II | 1 |
| 估算 Fmax | 143.31 MHz |
| BRAM_18K | 0 / 280 |
| DSP | 20 / 220 |
| FF | 4543 / 106400 |
| LUT | 5111 / 53200 |

## 风险与后续裁剪

当前为覆盖多种可能规则，内部使用 64×32 位乘法并保留两个可能的缩放位置，因此资源明显高于单一冻结量化公式。收到成员 B 的实际 multiplier 位宽、shift 范围和 PReLU 顺序后，应：

1. 删除未采用的分支；
2. 将 multiplier 缩到实际有效位宽；
3. 判断 requant 与 PReLU 能否合并为一次乘移；
4. 重新综合比较 DSP/LUT 和关键路径。

当前 20 DSP 是“通用正确性底座”的估算，不能作为最终后处理资源结论。

## 复现

```powershell
.\scripts\run_hls_postprocess.ps1
```

权威报告位于 `results/hls_postprocess/`。
