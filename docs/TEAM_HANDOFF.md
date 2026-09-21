# 成员 C 当前交接包（2026-09-21）

## 可立即交给成员 A

- 预览 HLS IP：`results/hls_stage3/stage3_pipeline_preview.zip`；
- 顶层接口与边界：`docs/HLS_STAGE3_STATUS.md`；
- 全部 HLS 资源估算：`results/HLS_SUMMARY.md`；
- 接口草案：`spec/INTERFACE_DRAFT.md`。

预览 IP 已由 Vitis HLS 2025.2 针对 `xc7z020-clg400-1` 导出，可用于 Vivado IP Repository 和 Block Design 占位。它不是最终 IP：当前只有 8 bit TDATA/TVALID/TREADY，尚未冻结 TLAST/TUSER，参数为外部 memory ports，卷积边界为 valid。

成员 A 仍需回复 `spec/TEAM_CONFIRMATION.md` 中的 overlay、DMA/VDMA、sideband、时钟和地址问题；在这些信息到达前，成员 C 不替成员 A 固定系统连接。

## 可立即交给成员 B

- 三层整数黄金模型：`python/network_reference.py`；
- 数值原语：`python/sr_reference.py`；
- 共享二进制向量格式示例：`spec/TEST_VECTOR_FORMAT.md` 与 `vectors/layer_smoke/`；
- padding/量化确认项：`spec/TEAM_CONFIRMATION.md`。

成员 B 最少需要提供：

1. padding 规则；
2. 三层 OIHW INT8 权重与 INT32 bias；
3. 每层/每输出通道 requant multiplier、shift、zero point；
4. 舍入、饱和和 PReLU 顺序/参数；
5. Pixel Shuffle 四通道排列；
6. 一组输入、三层中间结果和最终输出。

未收到这些数据前，当前测试向量只能证明实现逻辑正确，不能代表真实模型精度。

## 成员 C 已完成

- HLS 工具链、C 仿真和 PYNQ-Z2 综合闭环；
- 3×3 窗口、9 路空间乘加、跨输入/输出通道卷积；
- 可配置 requant/PReLU 和 Pixel Shuffle；
- 末层整链路 dataflow，两个独立算术测试通过；
- 预览 IP 导出；
- 完整三层 Python 位精确参考入口；
- 与 DMA/VDMA 无关的数据布局、Y8/INT8 转换和尺寸校验；
- 快速回归：`.\scripts\run_quick_regression.ps1`。

## 当前真正阻塞

- 没有成员 B 的真实权重与位精确规则，无法完成真实三层 HLS 对拍；
- padding 未冻结，无法把 HLS 尺寸从当前 valid 验证链定版为 640×360→1280×720；
- 没有成员 A 的 overlay/搬运/sideband/地址方案，无法完成最终 AXI 顶层和可运行 PYNQ 驱动；
- 没有可用板上工程和 bitstream，无法声称 Vivado 实现时序或板上性能。

因此下一次有效推进应从 A/B 的回答或成员 A 的板级工程开始，而不是继续扩展占位实现。
