# PYNQ 驱动数据布局阶段记录

## 已完成

- `FrameGeometry`：统一检查帧高、宽、通道数和元素总数；
- `pack_hwc_int8` / `unpack_hwc_int8`：按 `row → col → channel` 顺序在 INT8 张量与连续传输字节间转换；
- `encode_y8_to_int8` / `decode_int8_to_y8`：要求显式传入 zero point，避免把无符号 Y8 像素直接误解释为有符号 INT8；
- `network_output_geometry`：分别计算 same/valid padding 下三层卷积和 2× 上采样后的尺寸。

## 自动测试

覆盖 HWC 字节顺序与负数补码、长度错误、Y8/INT8 zero point 往返，以及 padding 对最终尺寸的影响。

结果：`DRIVER_LAYOUT_TEST_PASS tests=4`。

## 已暴露的关键接口事实

三层 3×3 卷积后：

| padding | 640×360 输入对应输出 |
|---|---:|
| same | 1280×720 |
| valid | 1268×708 |

因此最终演示要满足任务书的 1280×720，成员 B 的模型必须给出保持尺寸的边界处理，或团队明确采用其他补边/裁切恢复方案。这里仅做尺寸推导，没有替成员 B 决定 padding。

## 尚未冻结

- DMA、VDMA 或视频流直连；
- TLAST/TUSER 语义；
- PYNQ overlay 名称和寄存器地址；
- 输入与输出 zero point；
- 板端 buffer 分配与 cache flush/invalidate 方式。

这些分别等待成员 A、B 的接口结果。当前代码不依赖具体传输后端，可被后续驱动直接调用。

## 复现

```powershell
.\scripts\run_driver_layout.ps1
```
