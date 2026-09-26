# 条带 RAM 回读增加一拍：独立候选

状态（2026-09-26 19:20）：**Vivado/XSim 2025.2 的三个条带单元/既有回归 TB 全部 PASS**；完整 C 通路回归、综合及实现仍需独立验证。此目录不改变 C 正式 RTL，也不改变时钟及验收约束。

成功会话 PID `33224`，工作目录 `unit_work/run_20260926_191951_33224/`。新增 TB 实际覆盖单字节 51 次、短条带 98 次、满 bank 52 次、连续请求 1953 次、并行读写 647 次、反压 3395 次，两类在途复位各 1 次；原 `tb_stripe_buffer` 与三种子的 `tb_backpressure_rand` 也 PASS。三个 TB 的原始日志、coverage 和源文件哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units/summary.json)。

## 修改范围

- `stripe_buffer.v` 从 `experiments/l5_splitmem_20260924/rtl/c_ramdecomp_member_b/stripe_buffer.v` 复制：保留 RAM_DECOMP=power、写端口和越界保护，在同步 RAM 读出后增加一级无复位数据寄存器。第二级每拍更新，不能用当前 `rd_en` 门控前一请求的响应；停止请求后，两级数据自然保持。
- `pingpong_buffer.v` 从 `rtl/pingpong_buffer.v` 复制：`valid/first/last` 增加一级，随请求保存并延迟 bank 选择；响应 mux 使用响应 bank 标签。写指针、满状态、释放握手和防止重复领取 bank 的判断均保留。
- `readback_ctrl.v` 保持原版；`pend_q` 等待 `rd_valid`，因此能够承受新增响应延迟。它的旧注释“1 拍”不再描述本候选，但其控制逻辑无需变化。

以 E0 为 `rd_req && rd_busy` 被采样的上升沿：

| 时钟沿 | 数据与标签 | 条带最后请求的所有权处理 |
|---|---|---|
| E0 | RAM 原始输出和一级标签更新 | `rd_busy` 清零，`rd_done` 置一 |
| E1 | 新数据寄存器和二级标签更新，`rd_valid` 有效 | 原写侧块清 `bank_full`；末字节已经进入独立寄存器 |
| E2 | 下游 `byte_q` 采样数据和 `last` | 可以选择下一 bank；响应不使用这个新的 live bank 选择 |

新增的是一个完整时钟周期延迟；接口总计两级同步读。连续请求仍可每拍接受一次。复位清所有响应 valid/标签，RAM 和数据流水不复位，未写入或无效数据不参与验收。

不能只延迟 `rd_done`：`!rd_busy && !rd_done` 会在旧 bank 尚未释放时重新领取它。本候选保持原释放逻辑，E1 数据已经脱离存储阵列，不依赖随后 RAM 内容。`rd_len` 保持“当前读条带长度”的原接口语义；C core 未连接此输出。若未来把它作为逐响应元数据使用，须一起延迟。

## 自检与运行入口

`tb_stripe_pipe.sv` 使用写握手及读请求建立独立期望队列，检查每拍响应延迟，以及每个有效字节的 data/first/last；中间字节也必须 first=last=0。覆盖一字节、短条带、整 bank、连续请求、多次 bank 复用、双 bank 满反压、随机停顿、并行读写与在途复位。TB 具有硬超时并在失败时 `$fatal`。

`run_unit.tcl` 默认依次运行：

1. 新增 `tb_stripe_pipe`，通过标志 `STRIPE_PIPE_UNIT_TEST_PASS`。
2. 项目原 `tb_stripe_buffer`，定向边界回归。
3. 项目原 `tb_backpressure_rand`，三个确定性种子的随机背压回归。

三个 TB 均编译本目录的两份候选 RTL。脚本分开编译 Verilog RTL 与 SystemVerilog TB，每次使用独立工作目录，没有综合、实现或波形导出。Windows 运行库从当前 `XILINX_VIVADO` 取用，兼顾 2025.2 的 `xv_simulator_kernel.dll`、`tcl86t.dll` 和 `boost_*.dll` 名称；不回退到其它工具版本。本次已通过 2025.2 实际启动及运行验证。

在已使用本工程 ASCII 路径映射的 Vivado Tcl 环境中，执行以下命令；其中 `V:` 必须已经指向本工作区，不能覆盖其它映射：

```tcl
set argv {tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand}
source V:/experiments/timing_200_20260926/stripe_pipe/run_unit.tcl
```

批处理可指定三个 TB；可执行文件路径使用本机已经确认的 Vivado 2025.2 安装：

```powershell
& 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat' -mode batch -nojournal -nolog `
  -source 'V:/experiments/timing_200_20260926/stripe_pipe/run_unit.tcl' `
  -tclargs tb_stripe_pipe tb_stripe_buffer tb_backpressure_rand
```

通过后还需将完整 C 回归 runner 中的 stripe/pingpong 两项替换为本目录副本，运行 `tb_ready_valid`（两帧 UART 解码）及 `tb_c_top`（全尺寸、17 条带、连续逐拍读）。原 runner 直接运行会继续编译旧 RTL，不能作为本候选证据。`tb_b_real_bit_exact/full` 只验证 B 数据通路，不能替代 C 回读回归。

## 综合后必须确认的结构和验收

本候选的目的，是使用 BRAM 内部输出寄存器，将原 BRAM clock-to-out 与深层 mux 路径分开。仅在 RTL 中写两个寄存器，不保证得到该结构。

- 检查实际读口 `DOA_REG/DOB_REG`；旧关键路径使用 `DOBDO`。要求该读口输出寄存启用，或等价的局部寄存确实位于深层 RAM 选择 mux 前。
- 若寄存器仍只位于整条 30:1 mux 后，不能宣称已分开原瓶颈。必要时另建显式 30×4096×8 分片候选，各片寄存后再选择；本目录尚未实现该后备方案。
- 对比 RAM 数、FF、LUT 和新控制/选择路径，确认 RAM 未变成寄存器阵列。原两个 stripe bank 合计 60 个 RAMB36，仅是比较基线。
- 200 MHz 最终结果必须按原 5.000 ns 时钟与原 uncertainty 报告 setup/hold、TNS/THS、完整路由和 DRC；不增加 multicycle/false path，不降低 DRC 严重性。
- 本模块仿真通过不代表 200 MHz 时序通过，也不替代整板 UART/Golden 与连续多帧验证。
