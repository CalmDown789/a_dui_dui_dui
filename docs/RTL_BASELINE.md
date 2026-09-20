# 成员 C RTL 基线

## 已导入模块

- `rtl/window3x3_stream.v`：无 padding 的单通道 3×3 流式窗口生成器。
- `rtl/dot9_pipelined_dsp.v`：九个有符号乘法及流水加法树，乘法定向映射 DSP48E1。
- `rtl/channel12_accumulator.v`：顺序接收 12 个输入通道贡献并完成偏置累加。
- `rtl/mapping_backend_core_dsp.v`：连接 DSP 点积与 12 通道累加器的算术后端。

对应 testbench 位于 `tb/`，100 MHz 时钟约束位于 `constraints/clock_100mhz.xdc`。

## 已有验证记录

这些源码来自此前已经由成员 C 在 Vivado/XSim 中亲自运行通过的版本：

- `window3x3_stream_tb`：`WINDOW3X3_TEST_PASS`；
- `dot9_pipelined_dsp_tb`：`DOT9_PIPELINED_DSP_TEST_PASS`；
- `channel12_accumulator_tb`：`CHANNEL12_ACCUMULATOR_TEST_PASS`；
- `mapping_backend_core_dsp_tb`：`MAPPING_BACKEND_DSP_TEST_PASS`。

## 当前边界

- 窗口生成器与算术后端尚未连接成完整 mapping 层数据调度系统。
- 算术后端 testbench 从已经准备好的 3×3 窗口开始。
- 尚未加入真实 FSRCNN 权重和特征张量的位精确比对。
- 尚未加入 AXI4-Stream、DMA、PYNQ Python 控制和板上实测。
- 当前资源和时序结论只应在明确的器件、时钟约束和实现流程下引用。
