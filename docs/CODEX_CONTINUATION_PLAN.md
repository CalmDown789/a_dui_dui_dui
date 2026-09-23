# 接续任务清单：GitHub 协作与本机执行（2026-09-23）

本仓库分支 `c-side-latest`，本地接管提交为 `146fd2ed72f4d320c0483a35a9e0119e2c6d6ff6`。
用户此前要求暂不上云，因此该提交目前只在本机。其他人要从 GitHub 取用，
需要先由用户决定何时发布这个提交；本文不代替发布授权。

## 当前证据与限制

- B 真五层 RTL `ae29515` 的 15 文件闭包已接入 `C_USE_B_REAL`；19 个参数 ROM
  和来源哈希清单已提交。
- 96×54 四组整数 Golden 均 FAIL，见 `report/sim_result_tb_b_real_bit_exact.txt`。
- 960×540 整帧收到 2,073,600/2,073,600 字节，2,049,726 字节失配，X=0；
  帧/条带尾标记与保持规则通过，见 `report/b_real_full_summary.json`。
- 6×5 逐层记录显示 L1 INT32 MAC 为 0/480 失配，L1 后处理为 186/480 失配；
  首错 token 0/channel 1，DUT `fa6b`、参考 `0f7b`，见
  `report/b_real_layer_probe.txt`。
- 真实 B+C 综合和实现尚未完成。验收总判定仍是 **FAIL（功能阻塞）**。
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

全尺寸运行约 23 分钟。每次先核对参考数据 SHA-256；若 A 文件缺失，应从
已记录的 A commit `98c82f3` 复取并验证，不能退回到浮点/QDQ 参考。
修正 PR 合并后由本机复跑，产出最终小图/整帧数值证据。

### L2：本机真实 B+C 综合及实现

本机安装 Vivado/XSim 2022.2，器件为 `xc7a200tfbg484-2`。不与仿真并行运行：

```powershell
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/synth_bc_real.tcl' -tclargs impl *> '_bc_real_impl.log'
```

读取 `report/bc_real_synth/` 中的原始报告，自检真实 `b_core_real` / 五层实例
存在且 `b_core_stub=0`，记录 LUT/FF、RAMB36/RAMB18、DSP48E1、层次拆解、WNS
和路由状态。上次本机综合在 RTL 优化阶段被人工停止，约 10 分钟、内存峰值
约 30 GB；若再次遇到内存限制，可先运行 synth-only 并明确记录实现未完成。

### L3：用本机结果完成最终 A～Q 验收

报告的编辑可经 GitHub PR 协作完成，但最终数字必须来自 L1/L2 的实际结果。
更新 `docs/B_C_REAL_ACCEPTANCE_REPORT.md`、`README.md`、
`docs/DEPENDENCIES_A_B.md`，再运行 `scripts/export_dep_txt.py`。分别判定功能、
协议、资源和时序；不能把旧 C+stub 的 192 RAMB36 或 B 的预算 271/276/278
当成真实 B+C 实测，也不能从仿真周期推断 200 MHz 或 30 fps。UART 管脚和板级
触发仍是单独开放项。

## 建议接续顺序

1. 把 G1/G2 交给 GitHub 协作者，取得可审查的根因、修正 PR 和定向验证代码。
2. 在本机检查/合入修正，完成 L1 的小图与整帧复测。
3. 在本机单独完成 L2 综合/实现。
4. 依据两类本机结果完成 L3，保留失败项和开放项。

裸 `python` 是 Windows Store alias；当前机器请使用上面的托管 Python 路径。
`_sim/`、`_synth_bc/` 可再生，日志及 A 的大文件参考数据不随 Git 提交。
