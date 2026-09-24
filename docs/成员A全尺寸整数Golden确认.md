# 成员 A 全尺寸整数 Golden 确认

## 确认结论

成员 A 确认 `artifacts/full_integer_golden/` 为 d16/s8/m1/c16 模型的 `960×540 → 1920×1080` 全尺寸整数网络 Golden。该目录用于成员 B 的 RTL 输出和成员 C 的板级输出逐字节验收。

本 Golden 由 `artifacts/quant/quant_params.json` 中冻结的整数参数直接计算，全程执行 INT8 权重、INT16 中间激活、INT32 偏置与饱和累加、Q1.15 PReLU、Q31 重量化、最近舍入且中点远离零以及显式饱和。它不是 FP32 输出，也不是 QDQ 软件仿真输出。

## 冻结文件

| 用途 | 文件 | 字节数 | SHA-256 |
|---|---|---:|---|
| 原始输入 Y | `input_960x540_y_u8.bin` | 518400 | `aca4fb6f89accc388cede8f5fddaea79026a1fd507cdad6a844236941807e0f4` |
| C 侧 ROM 二进制 | `input_rom_2p19_u8.bin` | 524288 | `a754715b08e88fa9734069e6090ccceae13594bba248b09a4c154addb21efefc` |
| C 侧 ROM 文本 | `input_rom_2p19_u8.mem` | 1572864 | `f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9` |
| 四相位诊断输出 | `subpixel_phases_540x960x4_hwc_u8.bin` | 2073600 | `95da497cfcc9002afa0fda59de8e146edb0fd07f2890d8e9a9a9c77753f3be4b` |
| 最终权威输出 | `output_1920x1080_y_u8.bin` | 2073600 | `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e` |

最终权威输出 CRC32 为 `87d353f1`。四相位文件采用 HWC 行优先，通道顺序固定为左上、右上、左下、右下。最终输出是 PixelShuffle×2 后的 1920×1080 单通道 uint8 行优先字节流。

## Padding 和 ROM 约定

- Feature 5×5：pad 2；
- Shrinking 1×1：pad 0；
- Mapping 3×3：pad 1；
- Expanding 1×1：pad 0；
- Subpixel 5×5：pad 2；
- 所有卷积越界值均为整数零；
- 输入 ROM 地址 `0..518399` 为图像数据，`518400..524287` 共 5888 字节固定为零。

## 验收方法

```powershell
.\.venv\Scripts\python.exe scripts\verify_full_integer_golden.py --recompute
```

验收脚本会重新执行全部整数层，对每层的 shape、dtype、CRC32 和 SHA-256 进行比对，并确认最终输出与权威 `.bin` 逐字节相等。通过时必须返回 `status: PASS` 和 `recomputed_all_integer_stages: true`。

成员 B/C 不得用 `artifacts/full_reference/ref_out_fp32.npy` 或 `ref_out_quant.npy` 替代本 Golden；这两个文件只用于算法和量化效果分析。
