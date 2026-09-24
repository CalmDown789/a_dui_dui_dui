# 成员B工作：Vivado 2025.2 本机实验 overlay 取证

日期：2026-09-24。此文件只记录独立工作树 `c-side-latest@6b87af3` 加
`experiments/l5_splitmem_20260924/` 的实验路径；正式 RTL 尚未替换。

## 已完成的本机功能证据

- 工具：Vivado/XSim 2025.2，`xelab -O0`，五层真实 `b_core_real`，C 顶层接口启用
  `C_USE_B_REAL`。48 位与 36 位都使用同一 C+B overlay，唯一位宽差别是
  `phase_accumulator.sv` 与 `phase_accumulator_36.sv`。
- A 冻结数据来自 `member-a@98c82f3`。`scripts/prepare_ref_data.py` 的 SHA-256
  校验与 staging 为 `RESULT: PASS`，原始输出见
  `member_b_evidence/prepare_ref_data.log`。首次缺少 Golden 的仿真出现 `X`
  并失败，那轮不计入验收。
- 实验包 12 个覆盖源码对 `SOURCE_SHA256SUMS.txt` 的 LF 规范化 SHA-256
  全部吻合。Windows 工作树的 CRLF 原始文件哈希不同，属 Git 行尾转换。
- 48 位：`tb_b_real_smoke` PASS；`tb_b_real_backpressure` 三帧 PASS（随机
  out_ready、连续 300 周期输出停顿、连续 120 周期输入留空）；
  `tb_b_real_bit_exact` 四组 96×54 PASS，每组 20,736 输出字节零 mismatch。
- 36 位：上述同一组 smoke、背压、四组 96×54 对拍全部 PASS；四组各
  20,736 字节零 mismatch，背压保持违例为 0。其 36 位数学上覆盖 8 个
  signed32 部分和与一个 signed32 bias 的极值范围；现有局部边界/随机探针
  也保留在 C 的实验包中；目标器件实现结果见下文。

36 位审查依据：对任一通道，最保守的九个有符号 32 位项之和落在
`[-9·2^31, 9·(2^31-1)]`，而 signed36 可表示
`[-2^35, 2^35-1]`；35 位不足。累加器只在 `phase_valid && phase_ready`
时推进 `accum/expected_phase`，`sum_valid` 被占用且输出停顿时
`phase_ready` 拉低；`out_valid && !out_ready` 时输出寄存器保持。
`bias_flat` 在当前模型中是每层静态 ROM 参数，故输出级在下一拍取 bias
与 48 位版本同义；若将来改成逐像素动态 bias，须一并寄存 bias 元数据。
- 原始 XSim 日志分别在 `_sim_l5_member_b/` 与
  `_sim_l5_member_b_acc36/`，启动控制台日志在 `member_b_evidence/`。
  实验脚本在 `scripts/run_sim_l5_trial_member_b.tcl` 与
  `scripts/run_sim_l5_trial_acc36_member_b.tcl`，现已加入缺失 Golden 拒绝逻辑
  与真实 bank16 staging；最初的对拍发生在加 bank staging 之前。
  48 位背压与四组 96×54 对拍已于 15:14 按更新脚本复跑，均 PASS；
  此次运行日志明确显示真实 A 输入 bank16 已 staging。测试台仍从端口喂图，
  bank ROM 的读值正确性另由专门 ROM 测试覆盖。
  36 位背压与四组 96×54 对拍也已于 15:48 按更新脚本复跑，均 PASS；
  真实 A 输入 bank16 staging 见 `member_b_evidence/overlay36_recheck_console.log`。

## 真实输入 ROM

`scripts/gen_real_banks_member_b.py` 验证 A 的 524,288 行输入 ROM SHA-256
`f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9`，
按每 bank 32,768 字节拆成 16 个文件并重组核对。每个 bank 的 SHA-256 在
`member_b_evidence/real_banks/SOURCE_AND_BANK_SHA256.txt`。C 原实验包的
`fixtures/rom_bank_*.mem` 是合成 marker，不能用于真实图像的最终工程。

`scripts/run_input_rom_real_member_b.ps1` 与
`tb/tb_input_rom_real_member_b.sv` 已运行，通过 137 次同步读边界/随机
地址及 `en=0` 保持检查，XSim 标记为
`MEMBER_B_REAL_BANKED_ROM_PASS reads=137 banks=16 depth=32768`。原始日志在
`member_b_evidence/rom_tb/`。`synth_bc_realrom_member_b.tcl` 为 A 真实 ROM
另设输出目录，不能把 marker 布线报告直接当成真实 ROM 的时序。

## 960×540 全帧与折算边界

48 位 overlay 的 `tb_b_real_full` 在 XSim 2025.2 `-O0` PASS：
518,400/518,400 输入、2,073,600/2,073,600 输出，mismatch=0、X=0、
`stripe_last=17`、`frame_last=1`、`done=1`、保持违例=0，耗时
4,699,406 个仿真周期。原始日志在
`_sim_l5_member_b/tb_b_real_full/xsim.log`。若只做算术折算，该周期数对应
200/150/120 MHz 下分别约 42.56/31.92/25.54 帧每秒；这些数字要求
目标时钟实际收敛，并假定外部无额外吞吐限制，仅是单帧仿真时长换算，
不是连续吞吐或板测帧率。36 位同一全帧测试也已 PASS：输入与输出
数量、逐字节零差异、`stripe_last=17`、`frame_last=1`、`done=1`、
保持违例=0 与 4,699,406 周期均与 48 位一致。原始日志在
`member_b_evidence/raw_sim/l5_member_b_acc36_tb_b_real_full_xsim.log`。

## 实验过程与边界

- 36 位 960×540 全帧 XSim 与真实 bank16 staging 后的短回归均已 PASS。
- 目标器件 200 MHz 的 36 位真实 ROM 首次综合在 Vivado 2025.2 内
  异常退出（Windows 退出码 `0xC0000374`），停在综合 warning 后，
  没有自检或时序报告；原始日志为
  `member_b_evidence/route_realrom_acc36_200_console.log`，不计入实现结果。
  AMD UG973 的 Vivado 命名规则说明未明确列出的路径字符不受支持；
  工作树 `F:\FPGA预选\...` 包含中文。已验证临时 `V:` 映射下 Vivado
  `file normalize` 得到 `V:/`，并用此 ASCII 路径及独立 stage
  `acc36_realrom_member_b_ascii` 重跑；路径风险是合理怀疑，未单独证明崩溃根因。
  规则来源：<https://docs.amd.com/r/2023.2-English/ug973-vivado-release-notes-install-license/Vivado-Naming-Conventions>。
  ASCII 路径重跑完成综合及层次自检，真实核=1、stub=0、stream layer=5、
  pixel shuffle=1、elastic FIFO=7；综合资源 RAMB36/18=230/8、DSP=394、
  LUT=29,149、FF=48,359，综合 WNS/TNS=-0.844/-402.596 ns。
  `place_design` 被两条 `REQP-1962` 阻止：C 的 ping-pong 条带 BRAM
  级联两端 `ADDRARDADDR[15]` 不一致；没有布局或布线结果。
  原始日志与报告在 `member_b_evidence/route_realrom_acc36_200_ascii_console.log`
  和 `_synth_bc/acc36_realrom_member_b_ascii/reports/`。另独立试验了
  `synth_design -max_bram_cascade_height 1`；该选项见 AMD UG835：
  <https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/synth_design>。
  该选项复跑后两条 `REQP-1962` 仍存在。随后只在实验副本的
  `stripe_buffer.v` 内给 `mem` 增加 `ram_decomp="power"`，保留行为 RTL；
  200 MHz 36 位真实 ROM 方案在 ASCII 路径下已完整实现，层次自检通过，
  RAMB36/18=226/8、DSP=394，所有 76,150 条网络已布线、路由错误 0，
  但 post-route WNS/TNS=-0.719/-2842.755 ns，未达到 200 MHz。
  最差路径从 L5 `sum_valid_reg/C` 到宽 FIFO 某读指针复位端，
  数据路径 5.367 ns，其中布线 4.463 ns。原始结果见
  `_synth_bc/acc36_realrom_member_b_ascii_ramdecomp/reports/`。
  150 MHz 同一候选已完整实现：post-route WNS/TNS=+0.039/0 ns，
  RAMB36/18=226/8、DSP=394、75,832 条网络全部路由、路由错误 0；
  `report_clocks` 的实际生成时钟周期为 6.667 ns。该余量仅 39 ps，
  最差路径为 C 输入 ROM 地址寄存器至 bank10 BRAM 地址端，
  数据路径 6.247 ns，其中布线 5.868 ns。原始报告在
  `_synth_bc/acc36_realrom_150_member_b_ascii_ramdecomp/reports/`。
  120 MHz 同源候选也已完整布线：post-route WNS/TNS=+0.127/0 ns，
  RAMB36/18=226/8、DSP=394、75,759 条网络全部路由、错误 0，
  实际生成时钟周期 8.333 ns。最差路径为 L5 frontend 状态到窗口移位
  寄存器使能，数据路径 7.865 ns，其中布线 7.486 ns。报告在
  `_synth_bc/acc36_realrom_120_member_b_ascii_ramdecomp/reports/`。
  120 MHz 较 150 MHz 多约 88 ps 余量，但降低帧率；两者余量都较小。
  100 MHz 同源候选也已完整布线：post-route WNS/TNS=+0.403/0 ns，
  RAMB36/18=226/8、DSP=394、75,781 条网络全部路由、错误 0，
  实际生成时钟周期 10.000 ns。报告在
  `_synth_bc/acc36_realrom_100_member_b_ascii_ramdecomp/reports/`。
  以 4,699,406 周期做单帧算术折算，
  150/120/100 MHz 分别约 31.92/25.54/21.28 fps，
  不是持续吞吐或板测帧率。

## 同条件实现对照与验收边界

以下数字均来自 Vivado 2025.2、`xc7a200tfbg484-2`、真实 A 输入 ROM、
相同 C+B 实验 overlay 及 C `stripe_buffer` 的 `ram_decomp="power"` 映射。
该属性副本与原 C RTL 的功能差别仅为综合属性；文本差异已核对。
报告原件复制在 `member_b_evidence/route_reports/`。WNS 为完整布线后值。

| 累加器 | 时钟 | 实际周期 | WNS / TNS (ns) | RAMB36/18 | DSP | LUT / FF (post-route) | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| 48 位 | 200 MHz | 5.000 ns | -0.759 / -3642.598 | 226/8 | 394 | 31,125 / 50,024 | 失败 |
| 36 位 | 200 MHz | 5.000 ns | -0.719 / -2842.755 | 226/8 | 394 | 29,162 / 48,785 | 失败 |
| 36 位 | 150 MHz | 6.667 ns | +0.039 / 0 | 226/8 | 394 | 28,041 / 48,510 | 通过，余量 39 ps |
| 36 位 | 120 MHz | 8.333 ns | +0.127 / 0 | 226/8 | 394 | 28,010 / 48,445 | 通过，余量 127 ps |
| 36 位 | 100 MHz | 10.000 ns | +0.403 / 0 | 226/8 | 394 | 28,009 / 48,447 | 通过，余量 403 ps |

48→36 位同条件 200 MHz：post-route LUT 减少 1,963，FF 减少 1,239，
WNS 改善 0.040 ns，TNS 改善 799.843 ns；仍未达到 200 MHz。
48 位 200 MHz 对照也完成全部 79,157 条网络布线，路由错误 0。
36 位 150 MHz 的精确源码短回归（含 RAM 分解属性和 150 MHz C 顶层）
背压与四组 96×54 A 整数 Golden 对拍均 PASS，日志在
`member_b_evidence/overlay36_ramdecomp150_exact_console.log`。
36 位 960×540 全帧 PASS 发生在加入 RAM 分解属性前；该属性不改变
RTL 逻辑，但并未另跑属性版整帧，不能把两者混作同一次仿真。

上述 150/120/100 MHz 为目标器件静态时序通过，不是板上验证。
当前 XDC 有 1 条未指定 I/O 标准警告，UART 物理引脚与板级数据输出
仍待 C/实体板确认；仿真周期换算也未包括真实外部 I/O 带宽和连续帧间隔。
- 本机 Vivado 2025.2 最初查不到 `xc7a200tfbg484-2`；AMD 管理员补装
  `Artix-7 FPGAs` 在约 2.95/7.20 GB 时因归档
  `data_0169_2025.2_1114_2157_encrypt.xz` 损坏而返回
  `DownloadFailed`，安装器自动回滚，当时目标器件仍不可用。
  安装配置只勾选 Artix-7，控制台与配置记录在
  `F:\Xilinx\member_b_artix_trial\`；
  已核对路径和文件大小，仅移除上述损坏归档，并于 15:07 重试。
  重试期间另有多份归档出现校验失败，安装器自动重取后最终报告
  `Install completed successfully`。新启动的 Vivado 2025.2 在
  `get_parts -quiet xc7a200tfbg484-2` 返回 `PART_COUNT=1`，
  原始只读探针记录在 `member_b_evidence/probe_part_after_install_console.log`。
  该探针本身只证明目标器件数据可用；后续独立实现已取得许可并完成布线。
  安装器日志给出的该归档期望 MD5 为
  `b2b810738f5421eea4cbd51b7cf474f7`，本机实际 MD5 为
  `3df95b502ae6fc0f1b6dd0da4a834df7`；因此这是具体下载校验失败，
  不是缺少器件许可。认证令牌内容不记录在工程里。
- 200/150/120/100 MHz 的资源、WNS/TNS、DRC 和最差路径均已在本机
  实测，见上表与原始报告。仿真通过不能推导板上通过；UART 管脚与
  实体板测试仍归 C。
- 降频候选的 C 顶层分别只改 MMCM 分频、`CLK_HZ` 和维持 100 ms
  的自动启动计数；各自脚本和源文件独立保存，没有覆盖正式 RTL。
- 当前 96×54 B+C 测试台从端口喂输入像素，未走 C 的板上输入 ROM；
  bank16 ROM 的专门测试已 PASS，真实 bank 也已纳入综合/布线。
- `rtl/c_top.v` 单独作为 top 时默认 `ROM_INIT_EN=0`；当前实现取证 top
  `c_synth_top` 显式设为 1。给 C 的板级工程必须明确以启用真实 bank
  初始化的 top 构建，不能把单独的默认 `c_top` bitstream 当成相同图像路径。

## 本机复现命令

从此工作树根目录运行（Python 路径可替换为已有 Python）：

```powershell
& 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/prepare_ref_data.py --a-repo 'F:\FPGA预选\10h冲刺_a_assets'
& 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/gen_real_banks_member_b.py
$env:XILINX_VIVADO = 'F:\Xilinx\2025.2\Vivado'
& 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat' -mode batch -source scripts/run_sim_l5_trial_member_b.tcl -tclargs tb_b_real_backpressure tb_b_real_bit_exact
& 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat' -mode batch -source scripts/run_sim_l5_trial_acc36_member_b.tcl -tclargs tb_b_real_backpressure tb_b_real_bit_exact
& 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat' -mode batch -source scripts/run_sim_l5_trial_acc36_ramdecomp150_member_b.tcl -tclargs tb_b_real_backpressure tb_b_real_bit_exact
```

上述 `prepare_ref_data.py` 以已校验的 A 源码树为输入，复制二进制与生成
仿真读取的 `.mem`；无须重训模型。原始 C 实验报告仍是 2022.2 的对照，
本机 2025.2 的数值必须单独标注版本，不能要求两个版本的 WNS 相等。

此 Windows 工程目录含中文；以下为本轮 150 MHz 实现的实际运行方法。
`V:` 仅是临时映射，同一 PowerShell 进程退出前会清理。执行前先确认
`V:` 未被占用；目标器件数据、A Golden 和真实 bank16 均已就绪。

```powershell
if (Get-PSDrive -Name V -ErrorAction SilentlyContinue) { throw 'V: is occupied' }
subst V: 'F:\FPGA预选\10h冲刺_c_trial'
try {
    Push-Location 'V:\'
    & 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat' -mode batch -source 'V:\experiments\l5_splitmem_20260924\synth_bc_realrom_150_member_b.tcl' -tclargs impl acc36 ascii ramdecomp
    if ($LASTEXITCODE -ne 0) { throw 'Vivado implementation failed' }
} finally {
    Pop-Location
    subst V: /D
}
```
