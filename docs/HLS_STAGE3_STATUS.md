# 末层卷积到 Pixel Shuffle 整链路阶段记录

## 当前数据通路

`多通道 INT8 特征流 → 3×3 卷积（4 个输出通道）→ INT32/INT8 定点后处理 → 2× Pixel Shuffle → 单通道高分辨率 raster 流`

顶层采用 8 bit AXI4-Stream 输入/输出和 AXI4-Lite 控制参数。卷积权重、偏置和 requant 参数当前保留为存储器接口，便于在成员 A 冻结 overlay 后选择连接方式。

HLS 已将内部结构识别为三个独立 dataflow 进程：

1. `conv3x3_layer_top`；
2. `postprocess_stream_top`；
3. `pixel_shuffle2x_stream_top`。

两个中间 FIFO 深度均为 64。该结构证明三个模块能够并行握手，不是只在 C 代码中顺序调用。

## C 仿真

4×5×2 输入、4 个末层输出通道，验证两个用例：

1. 零权重、不同通道偏置，检查后处理与 Pixel Shuffle 映射；
2. 非零中心权重同时使用两个输入通道，逐像素检查卷积算术经过后处理和重排后的最终输出。

结果：`STAGE3_PIPELINE_TEST_PASS cases=2 pixels_per_case=24`。

## HLS 综合结果

目标器件：PYNQ-Z2 对应 `xc7z020-clg400-1`；时钟约束：10 ns。

| 指标 | 结果 |
|---|---:|
| 估算时钟周期 | 7.098 ns |
| 估算 Fmax | 140.87 MHz |
| BRAM_18K | 20 / 280（7%） |
| DSP | 11 / 220（5%） |
| FF | 3899 / 106400（3%） |
| LUT | 4972 / 53200（9%） |

以上是 HLS 估算值，不等于 Vivado 实现后的资源、WNS 或板上帧率。

## 结论边界

- 当前卷积仍是 `valid` 输出，因此只形成 `(H-2)×(W-2)×4 → 2(H-2)×2(W-2)` 的验证链；成员 B 未确认 padding 前，不能声称已满足 640×360 到 1280×720 的最终尺寸。
- requant 舍入、饱和、乘移参数和 Pixel Shuffle 通道顺序均可配置，但最终值必须由成员 B 的位精确导出确认。
- 8 bit AXI stream、参数存储接口以及 DMA/VDMA 连接尚未由成员 A 冻结；本模块是可综合的接口候选，不替代成员 A 的系统决定。
- 通用后处理仍保留多种规则。实际规则冻结后应裁剪无用分支并重新综合。

## 复现

```powershell
.\scripts\run_hls_stage3.ps1
```

权威日志和报告位于 `results/hls_stage3/`。

同目录的 `stage3_pipeline_preview.zip` 是供成员 A 提前检查端口、加入 Vivado IP Repository 和搭建占位 Block Design 的预览 IP。其流 sideband、参数装载和边界处理尚未冻结，不作为最终板上版本。
