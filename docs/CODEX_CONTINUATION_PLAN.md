# 接续任务清单：GitHub 协作与本机执行（2026-09-23）

> **2026-09-24 交接更新：**用户要求把目前成果同步到 GitHub，由其他成员/机器续跑；此后不要在 C 的本机运行 Vivado、XSim 或实现流程。最新的 L5 split-memory / 36-bit 候选、测量边界和可复跑 Tcl 见 [`docs/FPGA_TIMING_HANDOFF_2026-09-24.md`](FPGA_TIMING_HANDOFF_2026-09-24.md)。下文 2026-09-23 的“当前本机可直接运行”步骤是历史说明，执行前按本段交接要求选择其他有 Vivado 2022.2 与器件 license 的 runner。

本仓库分支 `c-side-latest`。用户已要求将必要提交推送到 GitHub；本轮验证记录
需随当前分支提交发布，便于其他账号续跑和审查。工作树中 `_bself/` 与
`tb/tb_const_probe.v` 是已有的未跟踪文件，交接时应保留，不要自动纳入提交。

## 当前证据与限制

- B 真五层 RTL `ae29515` 的 15 文件闭包已接入 `C_USE_B_REAL`；19 个参数 ROM
  和来源哈希清单已提交。
- XSim 2022.2 默认 `xelab` 优化的旧失败已由同一 RTL 的 `-O0` 复核为模拟器
  优化问题；不要将默认优化结果当作当前 RTL 功能结论。详情见
  `docs/B_REAL_XSIM_OPTIMIZATION_FINDING.md`。
- `-O0` 下 6×5 逐层探针、96×54 impulse/ramp/random/zero 正式验收及 960×540
  全帧均 0 失配。全帧摘要和 raw log 在 `report/xsim_repro/o0/960x540/`；同 runner
  的 96×54 default/`-O0` 对照日志在 `report/xsim_repro/{default,o0}/96x54/`。
- B 反馈要求把默认优化与 `-O0` 对照证据固定下来，不改 B RTL，也不混淆其测试台
  竞态修正与 C 侧的 XSim 优化结果。复现配置、命令及数据哈希见
  `docs/B_REAL_XSIM_REPRODUCIBILITY.md`；`run_sim.tcl` 可用
  `C_REAL_B_XELAB_OPT=default|o0` 选择真实 B 仿真选项。
- 本机真实 B smoke 与背压回归 `-O0` PASS；三种背压场景均逐字节匹配，T-B 实测
  连续有效拍停顿 300、保持违例 0。期间修正的是 C 侧背压 TB 的重复触发/启动计数，
  未修改 B 或 C RTL。
- 真实 B+C 综合和实现尚未完成；仿真数值/协议结果已通过 `-O0` 全尺寸对拍。
  2026-09-23 两轮 synth-only 均未生成综合资源/时序报告：首轮在可用物理内存低时
  过早停止；第二轮进入并完成 RTL Optimization Phase 2 后，系统提交余量降至 1.12 GB，
  页面文件仍为 32 GB、提交上限未扩展，故安全中断。详见
  `docs/B_C_REAL_SYNTH_CHECKPOINT.md` 及 `report/bc_real_synth/synth_only_*_stop.txt`。
- 仓库没有 `.github` workflow，也没有配置好的 GitHub Actions / Vivado runner。
  GitHub 协作可承载代码分析、修改和 PR；Vivado 仿真、综合、布局布线需要
  装有相应版本和许可的机器或专用 self-hosted runner。
- A 的全尺寸参考数据和 96×54 原始向量由 `.gitignore` 排除；本机有已校验副本，
  A 的来源提交 `98c82f3` 可供能访问该 GitHub 仓库的协作者重新取得。
  探针原始台架在本机 `_bgeo` 临时目录，提交入库的是哈希、计数和结论。

## 可由其他用户通过 GitHub 协作完成

这些工作不依赖本机绝对路径。**当前提交发布到共享 GitHub 分支后**，协作者可
在自己的 clone/分支上完成并提交 PR。

### G1：审查并定位第一层后处理分歧

从 `report/b_real_layer_probe.txt` 和跟踪证据开始，审查
`rtl/b_real_ae29515/stream/vector_postprocess_shared.sv`、
`rtl/b_real_ae29515/postprocess/prelu_requantize.sv` 与 ROM 参数打包顺序。
重点检查槽位/通道元数据延迟、lane 与 Q15/Q31 参数的配对，以及有符号乘法、
舍入和截位。提交根因说明与最小修正 PR；保留原始 B 快照及来源提交，
不要把尚未通过的修正标成已验收。

### G2：准备可审查的定向验证代码

协作者可以在 GitHub 分支中把本机临时逐层探针改造成仓库内可复现的 6×5
测试台/脚本，用已提交 RTL、参数 ROM 和小型固定测试向量检查 L1 INT32
以及后处理输出。PR 应包含生成/校验方式，并标明使用的仿真器。当前仓库
没有自动仿真 workflow；若验证必须用 XSim，应由装有许可工具的 runner 执行。

### G3：GitHub 文档与来源审查

协作者可检查 B 交付提交、A Golden 来源及当前验收文档之间的版本/措辞，
并提交文档修订 PR。A 的正式重新发布位置和撤回原因仍需 A 提供，不能靠
代码审查推定。

## 依赖特定工具或本机数据的任务

以下任务当前可在本机直接运行，因为相应工具和数据已配置好。其他用户也能
代跑，但需要自行取得 A 参考数据、安装并许可相同版本 Vivado/XSim，或使用
具备这些条件的 self-hosted runner；当前仓库没有配置这样的 GitHub runner/workflow。

### L1：本机 A 数据准备与正式逐字节复测

当前 A 量化仓库在 `C:\Users\Administrator\a_dui_dui_dui`，完整整数 Golden
和 test vector 的已校验副本在本机忽略目录。协作者可从 A 来源提交 `98c82f3`
重新取得；当前准备脚本则使用一个本地 A 仓库路径。准备与运行：

```powershell
& 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe' scripts\prepare_ref_data.py --a-repo 'C:\Users\Administrator\a_dui_dui_dui'
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/run_sim.tcl' -tclargs tb_b_real_bit_exact
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/run_sim.tcl' -tclargs tb_b_real_full
& 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe' scripts\extract_b_real_full_summary.py
```

默认优化下的旧全尺寸运行约 23 分钟；当前 `-O0` 速度更慢，按日志进度判断剩余
时间，不要沿用旧耗时估计。每次先核对参考数据 SHA-256；若 A 文件缺失，应从
已记录的 A commit `98c82f3` 复取并验证，不能退回到浮点/QDQ 参考。
修正 PR 合并后由本机复跑，产出最终小图/整帧数值证据。

### L2：本机真实 B+C 综合及实现

本机安装 Vivado/XSim 2022.2，器件为 `xc7a200tfbg484-2`。不与仿真并行运行：

```powershell
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/synth_bc_real.tcl' -tclargs impl *> '_bc_real_impl.log'
```

读取 `report/bc_real_synth/` 中的原始报告，自检真实 `b_core_real` / 五层实例
存在且 `b_core_stub=0`，记录 LUT/FF、RAMB36/RAMB18、DSP48E1、层次拆解、WNS
和路由状态。2026-09-23 两次 synth-only 均未生成报告；第二次因系统提交余量降至
1.12 GB 中断。在报告完成前不启动实现。具体续跑状态见
`docs/B_C_REAL_SYNTH_CHECKPOINT.md`。

### L3：用本机结果完成最终 A～Q 验收

报告的编辑可经 GitHub PR 协作完成，但最终数字必须来自 L1/L2 的实际结果。
更新 `docs/B_C_REAL_ACCEPTANCE_REPORT.md`、`README.md`、
`docs/DEPENDENCIES_A_B.md`，再运行 `scripts/export_dep_txt.py`。分别判定功能、
协议、资源和时序；不能把旧 C+stub 的 192 RAMB36 或 B 的预算 271/276/278
当成真实 B+C 实测，也不能从仿真周期推断 200 MHz 或 30 fps。UART 管脚和板级
触发仍是单独开放项。

## 建议接续顺序

1. 运行本机旧 C 壳层 smoke/ready-valid/backpressure 回归。
2. 评估本机真实 B+C synth-only；读取资源/时序报告和峰值内存，再决定是否运行完整实现。
3. 依据真实 B 验证和 B+C 综合/实现结果更新验收文档，明确板级事项仍需接板实测。
4. GitHub 协作者可独立审查仿真优化发现与重现流程；如提出 RTL 修改，需回本机复测。

## 本次本机运行检查点

`tb_b_real_full` 于 2026-09-23 19:10（本机）启动，Vivado 2022.2/XSim 完成于
19:42:40；完整日志和摘要已归档。随后 B+C synth-only 于约 20:07 启动，因系统
可用物理内存低而于约 20:10 提前中断；约 20:22:53 重跑并监控系统提交/页面文件，
Vivado 完成 RTL Optimization Phase 2 后，提交余量最低降到约 1.12 GB，于约 21:02
中断。两轮都没有综合报告，未启动实现。详见
`docs/B_C_REAL_SYNTH_CHECKPOINT.md`。A 输入/Golden `.mem` 文件位于 Git 忽略目录，
不能由 GitHub clone 恢复；本机完整数据源路径和 SHA-256 见 `ref/README.md`。

裸 `python` 是 Windows Store alias；当前机器请使用上面的托管 Python 路径。
`_sim/`、`_synth_bc/` 可再生，日志及 A 的大文件参考数据不随 Git 提交。
