# Vitis HLS 环境验证记录

## 结论

- 工具：Vitis HLS 2025.2，Build 6295257。
- 目标器件：`xc7z020-clg400-1`，对应 PYNQ-Z2。
- 目标时钟：10 ns，仅用于工具链自检，不代表成员 A 已确认系统时钟。
- C 仿真：通过，日志标志为 `HLS_SMOKE_TEST_PASS`。
- C 综合：通过，已生成 Verilog RTL。
- 最小例程估算：3.915 ns，约 255.43 MHz；64 FF、87 LUT、0 DSP、0 BRAM。

以上数字只证明本机 HLS 流程可用，不代表超分加速器的最终性能或资源占用。

## 复现命令

在仓库根目录执行：

```powershell
.\scripts\run_hls_smoke.ps1
```

由于 Vitis HLS 对当前中文仓库路径兼容不稳定，脚本会把最小示例复制到
`F:\Xilinx_Installers\pld10h_hls_smoke` 后运行。该目录是生成物，不提交 Git。

## 已处理问题

第一次运行时，HLS 工程位于中文路径，工具在创建 solution 时失败。改用纯英文临时目录后解决。

第二次运行时，Tcl 工作目录没有切换到源码目录，导致设计源码未参与 C 仿真链接。脚本增加
`cd $script_dir` 后，设计源码与 testbench 均正确编译。

## 后续验收

正式加速器仍需分别通过：

1. 小尺寸定向 C 仿真；
2. 与成员 B 黄金结果的逐层位精确比对；
3. 完整 HLS C 综合与 IP 导出；
4. 成员 A overlay 中的接口联调。
