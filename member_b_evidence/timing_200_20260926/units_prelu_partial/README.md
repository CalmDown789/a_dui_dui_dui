# PReLU 部分积单元仿真证据

Vivado/XSim **2025.2**，PID `20920`，2026-09-26 **20:14:43–20:14:57（Asia/Shanghai）**。入口 `prelu_partial/run_unit.tcl`；两个 testbench 正常 `$finish` 并退出，总标志 `PRELU_PARTIAL_ALL_UNIT_TESTS_PASS`。

- Scalar：**6/6 配置 PASS**，共核对 **23092** 个输出，同时对照 V2 原版延迟一拍和独立数学/九级 valid 模型。每配置至少 3200 个输出、30 拍 bubble、3 次在途 reset。
- 完整 48 位部分积拼合：共 **23207** 次独立乘法核对，包含两拍延迟、reset、invalid 保持；直接检查饱和前寄存器，含低 16 位全 1、负高 16 位、负 alpha 和 INT32 极值。
- INT64 Q31 注入探针：**1094 项 PASS**；它验证算术表达式，不证明 DSP 映射。
- Shared：**5/5 配置 PASS**，覆盖 16×2、8×1、4×1、1×1、4×2。每配置接受 422、输出 418，4 个向量在定向 reset 中作废。双槽背压、同时输入/输出、stall 保持、slot 复用和两种在途 reset 均满足覆盖门槛。

`summary.json` 保存实际 PASS/计数、9 份原始文本日志及 6 个 RTL/TB/runner 的 raw/canonical SHA-256。源码修改时间早于本次最早编译日志；哈希采集于归档时。reference 与 V2 `requant_pipe/prelu_requantize.sv` 规范化后仅模块名不同。

日志逐字节复制并复核，无 warning/error/fatal；未归档 DLL、WDB 或快照可执行文件。此证据只证明单元行为。V5 整网 Golden、DSP 实际映射、200 MHz 布线裕量和上板分别验收。
