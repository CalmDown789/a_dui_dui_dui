# 成员 B/C 共享测试向量格式 v0.1

## 目标

同一份输入、权重、偏置和期望输出同时供 Python 参考模型、HLS C 仿真及后续板上驱动使用，避免各端独立手写测试数据。

## 当前格式

每组向量放在独立目录，必须包含 `manifest.json`：

| 文件 | 类型 | 排列 |
|---|---|---|
| `input_hwc_i8.bin` | 原始补码 INT8 | `[H][W][Cin]` |
| `weights_oihw_i8.bin` | 原始补码 INT8 | `[Cout][Cin][3][3]` |
| `bias_i32_le.bin` | 小端有符号 INT32 | `[Cout]` |
| `expected_hwc_i32_le.bin` | 小端有符号 INT32 | `[Hout][Wout][Cout]` |
| `layer_vector.hpp` | C++ 常量 | 与上述文件相同 |

流顺序固定描述为：

- 输入：`row → column → input_channel`；
- 输出：`row → column → output_channel`。

这里冻结的是成员 C 的测试基础设施格式，不代表成员 B 的模型导出脚本必须直接生成该格式；后续可提供转换脚本。

## 当前 smoke 向量

入口：`vectors/layer_smoke/manifest.json`。

- 输入形状：4×5×2；
- 权重形状：3×2×3×3；
- padding：valid；
- 期望累加输出：2×3×3，INT32；
- 用途：验证卷积层的数据排列、符号、偏置和跨通道累加。

## 生成与验证

`scripts/run_hls_layer.ps1` 会先调用 Python 参考模型重新生成全部向量，再把生成的 C++ 头文件交给 HLS testbench。C 仿真通过即表示 HLS 输出与本次 Python 生成结果逐元素一致。

正式向量还需成员 B 提供每层 requantize/PReLU 后的 INT8 中间结果及最终 Pixel Shuffle 输出。
