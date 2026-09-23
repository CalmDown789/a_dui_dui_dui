# 成员B工作：五层流式调度集成状态

日期：2026-09-23。这个文件记录成员B已完成的整链功能验证和剩余实现风险。

## 已实现并通过 XSim

- `same_pad_raster.sv` 按 ready/valid 在栅格流中插入零边界。测试覆盖 PAD=0/1/2、输入计数、最后一拍和输出停顿保持。
- `elastic_fifo.sv` 支持任意深度的有序 token 缓冲，满态同拍出入；深度 3 测试覆盖 40 个 token。
- `window_kminus1_bram.sv` 使用 K−1 个轮转存储数组并带 block RAM 推断提示；当前行覆写的数组同拍读出最老一行。实际 BRAM 映射仍待综合。`window_stream_frontend.sv` 将插零、该窗口、FIFO 连起来。窗口输出慢至每 8 拍一次并停顿 30 拍时，3×3/5×5 的 6×5 图像逐 tap 正确；连续两帧不串行缓存旧值。原有 K-bank 窗口原语保留原状。
- `eight_phase_issue.sv` 每个窗口保持 8 次成功握手，相位 0～7 遇下游停顿保持；13 个窗口、104 次传输通过。
- `mac_lane_map.sv` 用参数 `(K,CIN,COUT,IN_PAR,OUT_PAR,LANE)` 生成 OIHW 地址。五层每个 LR 像素的 400/128/576/128/1600 个 MAC 均恰好覆盖一次，共 2832 个；并行 lanes 为 50/16/72/16/200，共 354。
- `phase_accumulator.sv` 将八相的每通道部分和归并为完整 HWC INT32 像素，在末相只加一次 bias 并最终饱和。五层参数分别通过两帧正负部分和、边界 bias 和输出 stall 测试。
- `generate_small_network_golden.py` 使用 A 已审计的 INT8/INT32/Q15/Q31 资产和 B 独立整数参考，生成 `6×5` 与 `96×54` 五层原始累加及量化输出、最终 PixelShuffle 期望值。生成文件在仓库内 `.artifacts/`，属于本地测试产物；下述 XSim 对拍是另外取得的 RTL 证据。
- `phase_mac_array.sv`、`mac_issue_stage.sv`、`fsrcnn_stream_layer.sv`、`fsrcnn_network_core.sv`、`fsrcnn_network_mem_top.sv` 已形成五层独立、同时运行的 RTL 网络；四处 32-token FIFO 串接真实 RTL 激活。`pixel_shuffle2x_row_banks.sv` 将末层四相转换为行优先 uint8 Y，并生成 `stripe_last/frame_last`。
- `6×5` 与 `96×54` 完整网络 XSim 已逐值通过。`96×54` 每层出口共核对 269,568 个值；最终 `192×108` 核对 20,736 个字节。ROM 顶层 `start/busy/done`、ready/valid、输出停顿保持与 sideband 也通过。
- `vector_postprocess_shared.sv` 已替换整链中逐通道并行后处理：16 通道层使用 2 lane，8/4 通道层使用 1 lane，每个像素分 8 组发射。替换后 ROM 顶层的 `6×5`、`96×54` bit-exact XSim 均再次通过。RTL 结构共有 13 个后处理 lane 乘法单元，实际 DSP 推断数量仍待目标综合。
- `b_core_real.sv` 提供 C-B v0.2 实名适配；使用 C ZIP 的 `c_core`/ROM/输出条带/UART 原始模块连续联调两帧 6×5，总计 240 个 Y 字节逐值一致，C 的 `proto_err/overflow_err` 为 0，连续输出背压 16,111 拍。联调只在临时副本给 C `b_core_if.v` 增加三个尺寸参数，未改 C 原件。背压容量见 `member_b_backpressure_contract.md`。
- `phase_mac_pipeline.sv` 将乘法和平衡加法树逐级寄存并保持相位标签，`pixel_shuffle2x_row_banks.sv` 改为同步读相位 word；改动后 6×5、96×54 整链与 C+B 联调再次逐值通过。

## 尚未完成

- MAC 已改平衡树流水、共享后处理为 13 个结构 lane，但不能由此认定满足 200 MHz、354+16 DSP 预算。仍需参数 bank、BRAM 与 DSP 映射的目标综合证据。
- ROM 顶层使用单行 packed `.mem` 初始化真实 A 参数；当前 XSim 通过，但 LUTROM/寄存器/BRAM 实际映射、并行取权端口数和资源量未签核。
- PixelShuffle 双 row-bank 已改同步读并通过功能验证；是否推断成 v1.1 预计的 2 个 RAMB36 尚未签核。
- `96×54` 完整功能通过；`960×540` 尚未仿真。XC7A200T 综合、布局布线、200 MHz 时序和 30 fps 由 C 板级工程与器件支持到位后签核。
- K−1 bank 新窗口尚未取得 RAMB36 综合报告。2026-09-23 本机启动 Vivado batch 两次均在读取 RTL 前出现 `Failed to install all user apps / load_features failed`；XSim 能正常运行。不能仅凭行为仿真把 v1.1 的 42 块行缓存 BRAM 预算标为已验证。

## 复现本轮新增回归

在 `F:\FPGA预选\10h冲刺` 执行：

```powershell
.\acx750_rtl\scripts\run_stream_control_xsim.ps1
.\acx750_rtl\scripts\run_padded_window_member_b_xsim.ps1
.\acx750_rtl\scripts\run_eight_phase_issue_xsim.ps1
.\acx750_rtl\scripts\run_window_stream_frontend_xsim.ps1
.\acx750_rtl\scripts\run_mac_lane_map_xsim.ps1
.\acx750_rtl\scripts\run_phase_accumulator_xsim.ps1
.\acx750_rtl\scripts\run_phase_mac_array_xsim.ps1
.\acx750_rtl\scripts\run_network_mem_top_xsim.ps1 -Width 96 -Height 54
```

生成小尺寸黄金数据时，`--delivery-root` 指向 A 交付根目录，`--output-dir` 指向测试产物目录，`--width/--height` 为低分辨率输入尺寸。`6×5` 和 `96×54` 两组已实际生成成功；文件本身只给后续 RTL testbench 作期望值。
