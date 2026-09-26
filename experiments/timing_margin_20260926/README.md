# 2026-09-26：B+C 150 MHz 裕量补试

本目录是在 `member-b-2025-2-bc-trial@7a891e7` 上完成的独立实验。没有更改 C 正式 RTL。用户随后授权把已完成实验与交接文档提交到该实验分支；未合并 C 正式分支。

## 已完成

最终推荐 `route_setup030`：原约束下 WNS/TNS **+0.492/0 ns**，WHS/THS **+0.018/0 ns**，route errors **0**。相比旧 NetDelay 提升 0.360 ns，达到约 +0.4 ns 目标。完整结论与复现命令见下方正式报告。

| 候选 | 脚本 | 说明 |
|---|---|---|
| forcefifo | `synth_forcefifo.tcl` | 原 NetDelay 设置，布局后仅定向复制 L5 FIFO 写指针 |
| setup030 | `synth_setup030.tcl` | 原 NetDelay RTL；布局阶段增加0.300 ns setup要求，布线前恢复0 |
| multi_target | `route_physical_branch.tcl -tclargs multi_target` | 从 forcefifo 的复制前布局检查点分支，同时处理 FIFO、ROM地址、stripe数据和 L5 pending1 |
| route_setup030 | `route_setup030.tcl` | 从 setup030 的同一布局检查点分支，将0.300 ns要求保持到布线结束，保存收紧报告后恢复0再验收 |

本轮所有用于实现的 RTL、XDC 和 ROM 相同。原 NetDelay 脚本本身包含综合后 L5 phase MAX_FANOUT 48，本轮保留；旧日志确认49条网络中46条实际设置该属性。

`collect_evidence.py route_setup030` 收集报告、源文件SHA-256、检查点SHA-256和摘要。原工作站可附加 `--verify-preserved` 核对原有未提交文件未被改变；其它克隆无需该选项。正式本轮结论以 `../../docs/MEMBER_B_150MHZ_MARGIN_2026-09-26.md` 和 `../../member_b_evidence/timing_margin_20260926/` 为准。C 上板验证交接见 `../../docs/MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md`。

## 备用草稿，未纳入实现

原工作站另有 `srl_candidate/`、`run_sim_srl.tcl` 和 `synth_srl.tcl` 本地草稿，**不在本次提交中**。它们尚未运行单模块仿真、Golden/反压或实现，不可集成。本轮已证明FIFO地址被改善后仍受其它控制长线限制，因此未启动这项存储结构改造。

## 运行条件

Vivado 2025.2，xc7a200tfbg484-2，真实A输入ROM bank16，36位累加，C stripe RAM ram_decomp=power，现有实验XDC。Vivado启动目录必须是ASCII路径；本机使用临时V盘映射。先运行生成所需检查点的完整脚本，再运行其分支脚本；所有结果按原150MHz约束评价。

干净克隆先运行 `python experiments/timing_margin_20260926/prepare_input_rom.py`。它从已跟踪的真实 bank 无损重建大输入 ROM，核对冻结 SHA-256，已有内容不符时拒绝覆盖。需要精确比较文本文件原始哈希时，克隆使用 `-c core.autocrlf=false` 保留 LF 换行。

参考：[AMD UG835 phys_opt_design](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/phys_opt_design)、[AMD UG949 设计过约束](https://docs.amd.com/r/zh-CN/ug949-vivado-design-methodology/设计过约束)。第二组采用UG949建议的布线前恢复；第四组是单独的布线压力对照，不称为该建议流程。
