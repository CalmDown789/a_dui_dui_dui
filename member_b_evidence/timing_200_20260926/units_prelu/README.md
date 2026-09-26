# V3 PReLU 流水线单元仿真证据

Vivado/XSim **2025.2**，PID `21792`，2026-09-26 **20:04:18–20:04:32（Asia/Shanghai）**。入口 `prelu_pipeline/run_unit.tcl`；两个 testbench 均正常 `$finish` 并退出，最终 `PRELU_PIPELINE_ALL_UNIT_TESTS_PASS`。

- Scalar：**6/6 配置 PASS**，共核对 18868 个输出；同时对照前一版延迟一拍的输出、独立 9 级 valid/data 模型和 signed64 数学模型。每配置至少 2500 个输出、30 拍 bubble、3 次有数据在途的 reset，结束时流水为空。
- INT64 注入探针：**1094 项 PASS**，包括舍入边界及极值；它验证算术表达式，不证明 DSP 寄存器映射。
- Shared：**5/5 配置 PASS**，覆盖实际 16×2、8×1、4×1，以及 GROUPS=1/2 边界。每配置接受 422、输出 418 个向量，4 个在定向 reset 作废；反压、同时输入/输出、计算中 reset 和输出阻塞时 reset 均满足覆盖门槛。

`summary.json` 保存实际 PASS/计数、9 份原始文本日志哈希及 6 个冻结 RTL/TB/runner 的 raw/canonical SHA-256。源文件修改时间早于本次编译日志；哈希是在归档时采集，不冒称启动时哈希。reference 与 `requant_pipe/prelu_requantize.sv` 经换行规范化后仅模块名不同。

日志按原字节复制，无 warning/fatal/error。未归档 DLL、WDB、快照可执行文件。此证据只覆盖独立单元行为；V3 整网 Golden、DSP MREG 吸收、200 MHz 布线裕量及上板另行验收。
