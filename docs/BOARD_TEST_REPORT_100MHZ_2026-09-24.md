# C 侧 100 MHz 板级验证报告

日期：2026-09-24  
结论：**板级功能及单帧 Golden 比对通过**

## 测试基线

- FPGA：ACX750，器件 `xc7a200tfbg484-2`
- 工具：Vivado 2022.2
- 正式 RTL 源树：`6218c5eb09a09e7a7d63c12ae163f7dd29baf0f8`，tree `618a532ab842e9a7b33b1f695689e446f37cebf6`
- 该 tree 与远端 `c-side-latest` 的父提交 `47e8f164c7be50470d1ac87ba07db445e83cd7be` 相同；远端当时 HEAD 为 `6b87af30a63ba3988f971cf8e787f0bd92fd46be`
- 板测 overlay：50 MHz 输入下 MMCM `CLKOUT0_DIVIDE_F=12.0`，`C_CLK_HZ=100000000`；功能 RTL 未修改
- UART：`921600 baud, 8N1`；ACX750 手册对应 TX 管脚 M21
- 输入 ROM SHA-256：`f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9`

## 实现结果

| 指标 | 综合 | 布局布线后 |
|---|---:|---:|
| WNS | +3.825 ns | +0.464 ns |
| TNS | 0 ns | 0 ns |
| WHS | +0.029 ns | +0.036 ns |
| THS | 0 ns | 0 ns |

后布线报告显示所有用户时序约束满足。71,461 条可布线网络全部完成布线，路由错误为 0。

后布线资源：RAMB36/FIFO 230，RAMB18 8，DSP48E1 394，LUT 30,039，FF 41,936，MMCM 1，BUFG 1。

后布线 DRC：0 个错误、1,091 条警告。主要警告为 DSP 输入/输出流水线建议及 RAMB18 异步控制检查；其中 REQP-1840 有 8 条，提示异步复位可能影响 RAMB 控制脚。警告保留待后续评估，本次板上输出比对通过。

## 板上结果

- JTAG 将 bitstream 配置到 `xc7a200t_0`，Vivado 报告 End of Startup 为 HIGH。
- COM3（CH9102）收到完整灰度帧：2,073,600 字节。
- 输出文件 SHA-256：`be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`
- 参考 Golden：`output_1920x1080_y_u8.bin`，长度及 SHA-256 完全相同；逐字节差异数：**0**。
- 本次 bitstream SHA-256：`2296eee5cd550f890e1c6f51fa4c24ee21b1879bb10bdadef7c701ebfb7a8244`

## 吞吐记录

采集脚本读取 2,073,600 字节的主机读循环时间为 22.426 秒，约 92465 B/s（90.30 KiB/s），约 0.04459 帧/秒。计时从第一批串口数据读回后开始，Windows 接收缓冲会使该读循环时间略短于线上的完整传输时间。

UART 配置为 921,600 baud、8N1，理论有效载荷速率为 92,160 B/s；单帧串行传输时间约 22.500 秒，即约 0.04444 帧/秒。该结果反映当前 UART 回传速度，不代表 CNN 核心的纯计算吞吐。

## 判定范围

100 MHz 单帧板测与 Golden 逐字节一致，满足进入下一档测试的功能门槛。此结果不代表 150 MHz 时序闭合，也不等价于 30 fps 视频吞吐。数码管显示的“7”不是此 C 顶层的验收信号；验收数据来自 UART 帧。
