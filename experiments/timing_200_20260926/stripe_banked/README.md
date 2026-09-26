# 显式 4096 深度分片的 stripe 读取候选

状态（2026-09-26 19:44）：**Vivado/XSim 2025.2 单测 5/5 边界配置及 3 个既有 stripe/C 回归均 PASS。** V2 整网回归、综合与布线仍需独立验证，BRAM 输出寄存器是否吸收及实际时序收益尚未证明。

成功会话 PID `30704`，工作目录 `unit_work/run_20260926_194354_30704/`。生产深度 122880 的配置完成 123856 次写、124334 次读，30 个 bank 中切换 1027 次；其它深度为 8197、4096、32、1，均覆盖地址边界及非法地址。`tb_stripe_pipe`、`tb_stripe_buffer`、`tb_backpressure_rand` 同时通过，其中随机反压三个种子各输出/回读 192 字节、3 条带、1 帧、0 断言错误。原始日志与源文件哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units_next/summary.json)。

## 原因与结构

此前 `stripe_pipe` 在整条大 RAM 的读取输出后增加寄存器，但父任务提供的两组综合 `stripe_bram_registers.txt` 均显示 60 个 RAMB36 的 DOA_REG/DOB_REG 全部为 0。新增寄存器没有进入 BRAM 内部，不能据此认定分开了 BRAM 与深层选择 mux 的延迟。

本候选显式拆分内存：

- 生产容量 `1920×64=122880` 字节，每个 stripe 实例分成 **30 片 4096×8**，两个 pingpong stripe 共 60 片。
- 每片在独立 `stripe_buffer_bank4096` 层级中声明 `mem`、`read_q0`、`read_q1`，两个读级均无复位，q1 位于最终 bank mux **之前**。实例保留 `keep_hierarchy`，允许 q1 吸收到本片 BRAM 输出寄存器。
- 请求地址低 12 位通过赋值截断/补零获得，避免 `ADDR_W<12` 时出现越界 part-select。高位选择分片。
- 分片数量向上取整，最后一片按剩余字数声明，支持不足 4096 的尾片、小尺寸及单字容量。
- 读请求只有在 `rd_en && rd_addr<MEM_DEPTH` 时改变第一级数据和选择器；第二级每拍前进。越界写丢弃，越界/禁用读保持前次结果，不回绕。

## 延迟与接口

端口与 `stripe_pipe/stripe_buffer.v` 一致，总共两级同步读：E0 接受地址并更新各片 q0/一级选择器；E1 更新 q1/二级选择器并输出；E2 下游采样。bank 选择器与每片 q1 对齐，支持连续请求在不同分片间切换。

直接复用 `../stripe_pipe/pingpong_buffer.v`，不复制或修改它。原 bank 释放、防重复领取，以及 valid/first/last 的二级对齐保持一致。stripe 数据和选择器不复位；复位期间及流水清空时，由 pingpong 的有效标签屏蔽旧数据。

同沿相同地址读写的 RTL 语义仍是 read-first。生产 pingpong 的所有权规则应避免同一 stripe 的读写冲突；独立测试保留碰撞语义检查，综合后的存储模式仍须核对。

## 自检与运行入口

`tb_stripe_banked.sv` 有五个并行配置：

| ID | 深度 | 检查范围 |
|---|---:|---|
| 0 | 122880 | 生产容量、30 片，写满后逐地址连续读取 |
| 1 | 8197 | 三片、最后一片仅 5 字节 |
| 2 | 4096 | 恰好一整片，额外地址位用于测试越界 |
| 3 | 32 | ADDR_W=6，低于 12 位 |
| 4 | 1 | 单字容量、ADDR_W=1 |

每组同时对照原 `stripe_pipe` 两级读取实现和独立数组/响应模型；参考模块仅在运行工作目录中更名，不改原文件。期望模型先读后写，逐周期检查已知的输出，包含禁用和越界读周期。定向覆盖 4095→4096、4096→4095、末地址、连续跨片选择、相同/不同地址并行读写、越界写不回绕，以及内存内容已改变但禁用/越界读取仍应保持旧输出。另有 2000 拍固定种子随机读写、覆盖门槛和硬超时。

runner 默认顺序运行四项，全部编译本候选 `stripe_buffer.v`：

1. `tb_stripe_banked`：以上五配置；要求五条 `STRIPE_BANKED_CONFIG_PASS id=` 和总标志 `STRIPE_BANKED_ALL_CONFIGS_PASS`。
2. 复用 `stripe_pipe/tb_stripe_pipe.sv`：独立 pingpong FIFO/标签参考、满载反压、复用及在途复位。
3. 原 `tb_stripe_buffer`。
4. 原 `tb_backpressure_rand`。

每次使用新的工作目录，每个 TB 日志独立；xvlog/xelab 带 `--nolog`，XSim 引擎日志写 `xsim_engine.log`，控制台重定向到 `xsim.log`，两者分开并检查错误。不开波形，不执行综合或实现。

在父任务已确认的 ASCII 工作区映射中运行，例如 `V:` 指向该仓库时：

```tcl
set argv {tb_stripe_banked tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand}
source V:/experiments/timing_200_20260926/stripe_banked/run_unit.tcl
```

整体通过标志为 `STRIPE_BANKED_REGRESSION_PASS`。当前没有通过记录。之后仍需完整 C 两帧 UART 回归和最终组合的真实 B Golden/背压回归。

## 综合与实现判据

- 检查生产配置每个 `g_bank[*].memory` 中 q1 实际保留为 BRAM 输出寄存器（相关 DOA_REG/DOB_REG=1），或明确的独立局部 FF，并确认这些寄存器处于最终 bank 选择 mux 前。
- 若 q1 被移动/合并到整条 mux 后，不能把 RTL 中的分级当成优化成功；需要查看综合网表及实际起终点。
- 对照每 stripe 30 个 RAMB36、全双缓冲 60 个的旧资源基线，记录 BRAM/FF/LUT 变化；属性只是推断请求，不能保证原语和数量。
- 检查两级分片选择器的路径和扇出，确认没有把原数据瓶颈转移成新的控制瓶颈。
- 最终只按原 200 MHz/5.000 ns 及原自动 uncertainty 验收 setup、hold、TNS/THS、完整路由与 DRC。不得通过 multicycle、false path、降低时钟或降低 DRC 严重性替代结果。
