# 成员B工作：真实五层核接入 C 工程的交接单

日期：2026-09-23。核对来源为用户提供的 `a_dui_dui_dui-c-side-latest.zip`（SHA256 `16ECF3E13E0CE8C1E044D6EE55AD76DBE410E4491C558AA20D36C2CDBA1BE0AA`）。B 没有修改 C 原仓库文件；本地联调复制 C 文件到临时目录后才做参数适配。

## B 已交付的可复测部分

- `rtl/stream/b_core_real.sv` 与 C-B v0.2 端口同名，`IMG_W/IMG_H/STRIPE_H` 默认分别为 960/540/64，内部例化五层 `fsrcnn_network_mem_top`。
- 五层分别有自己的行窗口、八相 MAC 流水、跨相累加、共享后处理；四处层间 FIFO；PixelShuffle 同步读双 row-bank。所有计算只在 ready/valid 握手时推进。
- `rom/member_a_d16_s8_m1_c16/` 有 19 个由 A 已审计整数资产逐位重排的参数 `.mem`，`manifest.json` 给 SHA256。权重数值和量化语义未由 B 重新决定。
- `scripts/convert_member_a_input_to_c_mem.py` 已把 A 的 `input_960x540_y_u8.bin`（先按 A manifest 校验 SHA256）无损转成 C 的 2^19 深、逐行十六进制输入 ROM 文件，末尾 5,888 byte 补 0。产物在本地 `.artifacts/member_b_c_input_mem/`，由 C 决定是否接入其输入 ROM。
- `scripts/run_member_b_c_input_rom_xsim.ps1` 用 C 的原始 `input_rom.v` 验证转换文件：地址 0、959、518399 与 A 原始字节相符，518400、524287 为零，标记 `ACX750_MEMBER_B_C_INPUT_ROM_PASS`。
- `scripts/run_network_mem_top_xsim.ps1 -Width 96 -Height 54 -ParameterRomDir .\acx750_rtl\rom\member_a_d16_s8_m1_c16`：20,736 个最终 Y 字节逐值通过，测试中最长 `out_valid=0` 间隔 117 拍；这是本测试输入和背压激励下的观测值，不是 960×540 节拍上界。
- 同一脚本加 `-AlwaysReady` 时，96×54 全帧对拍通过，测试从复位释放到完成共 44,915 拍（包含 start、填充和流水起落），最长帧内 `out_valid=0` 间隔 193 拍。该仿真周期数不能乘以尚未实现的 200 MHz 当作板上帧率。
- `scripts/run_member_b_c_core_real_xsim.ps1 -ParameterRomDir .\acx750_rtl\rom\member_a_d16_s8_m1_c16`：C 原始 `c_core`/ROM/条带双缓冲/UART 与真实 B 核连续跑两帧 6×5；240 字节、每帧三条带及 C 错误标志通过，最长连续输出背压 16,111 拍。
- `b_core_real` 默认 960×540 参数已在 XSim 2025.2 完成编译展开；同一五层 `fsrcnn_network_mem_top` 已用 A 新整数 Golden 跑完整帧行为仿真，2,073,600 个输出 Y 字节逐值 PASS，4,180,019 拍。仍不能据此声称目标器件达到 200 MHz 或 30 fps；C 的正式整机接入尚待完成。

## C 正式接入时必须做的最小适配

1. 在 C 的 `b_core_if.v` 中给真实核实例传尺寸，保持端口不变：

   ```systemverilog
   b_core_real #(
       .IMG_W(IMG_W), .IMG_H(IMG_H), .STRIPE_H(STRIPE_H)
   ) u_b_core (...);
   ```

   原 ZIP 的实例没有参数传递，小尺寸 TB 会误用 B 的 960×540 默认值。本地 B 联调只在隔离副本应用了上述改动。

2. 在 C 的仿真与综合脚本加入 B 的 15 个文件：`same_pad_raster.sv`、`elastic_fifo.sv`、`window_kminus1_bram.sv`、`window_stream_frontend.sv`、`eight_phase_issue.sv`、`phase_mac_pipeline.sv`、`phase_accumulator.sv`、`mac_issue_stage.sv`、`vector_postprocess_shared.sv`、`fsrcnn_stream_layer.sv`、`pixel_shuffle2x_row_banks.sv`、`fsrcnn_network_core.sv`、`fsrcnn_network_mem_top.sv`、`b_core_real.sv`、`rtl/postprocess/prelu_requantize.sv`。以 SystemVerilog 模式读入并对真实核启用 `C_USE_B_REAL`。C 当前 `synth_check.tcl` 仅用 `read_verilog` 读取 `.v` 与 stub，不能原样综合 B 核。
3. 把 B 参数 ROM 包中的 19 个 `*_packed.mem` 放进仿真/综合**运行工作目录**，因为 `fsrcnn_network_mem_top.sv` 当前按相对文件名调用 `$readmemh`。C 输入图 ROM 仍是 C 自己的文件与职责。
4. C 现有 TB 的最近邻 stub 期望值不能用来验收 FSRCNN。启用真实 B 后以 A/B 整数参考逐字节比较，并保留 sideband、长背压和第二帧检查。
5. 对 `xc7a200tfbg484-2` 重跑**合并后的**综合，再按模块报告 DSP、RAMB36、LUT、FF、关键路径。C ZIP 的 192 RAMB36/0 DSP/−0.153 ns 是 stub 工程的仅综合结果。C 的 192 块也已高于 v1.1 原估 C 侧 187 块；系统 271 块预算要重新核算。

## 仍需 A/C 给出的信息

- **A 已解决**：用户新提供的 `a_dui_dui_dui-member-a.zip` 中，`artifacts/full_integer_golden/` 是 A 确认的 960×540→1920×1080 整数 Golden。B 核对 8 个文件的长度、CRC32、SHA256，56 个量化参数文件与旧审计包逐字节一致，四相位到最终输出的 PixelShuffle 逐字节一致。最终输出 SHA256 为 `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`。A 的 `input_rom_2p19_u8.mem` 与 B 此前转换版的 524288 个地址数值相同，C 可直接采用 A 权威 ROM 文本。A 的逐层重算脚本需要 PyTorch，B 当前通用 Python 缺少该依赖；这里的独立核对不等同于重新运行 A 的全部整数层。
- **C**：上述最小接口/脚本适配、正式合并综合的原始报告与对应提交、时钟/XDC 实现报告；若继续以 UART 静态回读验功能，另需确定满足 30 fps 的实时输出通路，不能拿 UART 回读时间推帧率。

## 结论边界

功能仿真已从 B 单独整链推进到 C+B 两帧小尺寸联调；真实 B+C 的 XC7A200T 资源、200 MHz 时序和 30 fps **均未签核**。`B-ARCH-10` 背压七项与容量详见 `member_b_backpressure_contract.md`。
