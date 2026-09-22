# c_side —— FSRCNN 超分加速器 C 侧 RTL 工程（ACX750-200T）

C 侧（系统集成 / 综合实现 / 板级验证）RTL 骨架。目标：**真实 B RTL 到位后，
只需替换 `rtl/b_core_if.v` 里的 stub 实例，C 侧其余模块不需要重新设计。**

## 设计基线（唯一依据）

| 文档 | 位置 |
|---|---|
| `FSRCNN_ACX750-200T部署任务书_v3.2.2修订执行版` | 上级目录（md 源在 `../output/任务书v3.2.2_修订执行版.md`） |
| `成员B对C架构接口与资源预算确认_v1.0` | 上级目录 |

冻结口径（不得自行改动）：d16/s8/m1/c16、L5 = 单稠密 Conv(16→4,5×5)、
中间激活对称 INT16、权重 INT8、INT32 累加、Q31 requant；C-B 接口 v0.2；
200 MHz 单时钟域；64 行条带双缓冲（**当前基线，非冻结项**）。

## 目录

```
rtl/      c_config.vh    参数单一真源（逐条标注 v3.2.2 出处）
          c_top.v        板级顶层：MMCM 50→200MHz + 复位汇聚 + LED
          c_core.v       单时钟域集成壳
          c_ctrl.v       start/busy/done 控制框架
          input_rom.v    输入 ROM（19 bit 地址 / 2^19 深 / 同步读 1 拍）
          input_stream.v 输入像素流（in_valid/in_ready/in_data）
          stripe_buffer.v 单个条带 bank
          pingpong_buffer.v 条带 ping-pong 双缓冲 + 交换 + 回读口径
          output_stream.v B→C 输出消费 + 条带/帧边界复算 + out_ready
          uart_tx.v      UART 8N1 发送（波特率参数化）
          readback_ctrl.v UART 静态回读控制
          b_core_if.v    ★ C-B v0.2 冻结端口的唯一落点（stub / 真实 B 切换）
          b_core_stub.v  ★★★ SIMULATION STUB ONLY ★★★（2×2 最近邻，不是 FSRCNN）
tb/       tb_ready_valid.v  小规模全链路 + A~K 背压/边界场景（已 PASS）
constr/   （待补 c_top.xdc，可复用 ../bench/onboard_dual_int8/constr/top_onboard.xdc）
scripts/  （待补 run_sim.tcl / synth_check.tcl）
docs/     C_IMPLEMENTATION_STATUS.md  ← 实现状态、覆盖度、TODO、下一步
```

## 复现仿真（Vivado 2022.2）

```powershell
$bin = "E:\Xilinx\Vivado\2022.2\bin"
$rtl = Get-ChildItem rtl\*.v | ForEach-Object { $_.FullName }
& "$bin\xvlog.bat" --include rtl -d C_SIM --nolog --work worklib @rtl tb\tb_ready_valid.v
& "$bin\xelab.bat" worklib.tb_ready_valid --nolog -s tb_sim
& "$bin\xsim.bat" tb_sim -runall      # 期望 "RESULT: PASS  (all A~K scenarios, 0 error)"
```

**磁盘安全约定**：不 dump 波形（无 `$dumpvars`）；TB 只用小规模参数与内存数组；
所有 testbench 均有硬 timeout；构建产物（`_sim/`、`_syn/`、`*.log`、`*.jou` 等）已被 `.gitignore` 忽略。

## 表述纪律（重要）

- 完整设计**尚未综合**，本仓库**不得**出现 Fmax / FPS / DSP / BRAM 的实测数字。
- BRAM 现状：「**一级 理论预算未闭合**（口径② ≈1406.6 KiB > 预算线 1396.1 KiB）；
  **二级 实际资源未验证**」（任务书 §五.13（2））。
- `b_core_stub.v` 的输出是**测试 pattern**，**不是算法结果**，不得用于 PSNR/效果结论。
- UART 属**离线静态回读**，**不得**用其传输时间推断实时 FPS。
