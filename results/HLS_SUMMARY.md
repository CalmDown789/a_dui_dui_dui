# HLS 阶段资源汇总

目标器件均为 PYNQ-Z2 对应的 `xc7z020-clg400-1`，综合时钟约束均为 10 ns。

| 阶段 | HLS 顶层 | 估算 Fmax (MHz) | BRAM_18K | DSP | FF | LUT |
|---|---|---:|---:|---:|---:|---:|
| core | `conv3x3_mac_top` | 150.22 | 0 | 6 | 556 | 576 |
| integration | `conv3x3_stream_top` | 140.88 | 16 | 6 | 853 | 1349 |
| layer | `conv3x3_layer_top` | 140.88 | 16 | 6 | 2753 | 2039 |
| pixel_shuffle | `pixel_shuffle2x_stream_top` | 182.08 | 2 | 0 | 304 | 704 |
| postprocess | `postprocess_stream_top` | 143.31 | 0 | 20 | 4543 | 5111 |
| stage3 | `stage3_pipeline_top` | 140.88 | 20 | 11 | 3899 | 4972 |
| window | `window3x3_stream_top` | 147.84 | 2 | 1 | 653 | 972 |

注意：各行是不同功能边界的独立综合，不可相加为完整网络资源。
`stage3` 是目前最接近可交付子系统的一行，包含末层卷积、后处理和 Pixel Shuffle；
所有数据仍是 HLS 估算，不等于 Vivado 实现后的资源、WNS 或板上帧率。
