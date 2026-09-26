# 200 MHz 优化实验：本轮已收尾

最终记录与下次入口：`docs/MEMBER_B_200MHZ_TIMING_2026-09-26.md`。证据和机器可读总表：`member_b_evidence/timing_200_20260926/results_index.json`。

目标+0.100/+0.250/+0.400ns均未达到。最高WNS为−0.162ns；建议下次从V1 nominal继续（−0.164ns，TNS −7.523ns，hold +0.036ns），其总违例和hold优于最高WNS记录。V6完整测试已经完成，WNS −0.638ns，功能正确但本轮不采用。

## 入口

- V1：`synth_200_pipeline030.tcl` / `run_sim_pipeline200.tcl`。实现参数`impl acc36 ascii ramdecomp nominal`为推荐继续基线；去掉`nominal`为额外0.300ns搜索压力组。
- V2：`synth_200_pipeline2_030.tcl` / `run_sim_pipeline200_v2.tcl`。
- V6：`synth_200_pipeline6_030.tcl` / `run_sim_pipeline200_v6.tcl`。
- V3/V5只完成单元、小图和综合探针，不等于完整实现；`prelu_signed_round`仅是未执行草稿。
- `postroute_finish/`从独立DCP副本做物理收尾；V1/V2原约束收尾已运行完成。
- `freeze_launch_inputs.py`记录66项启动输入；`collect_evidence.py`核验完整实现；`collect_sim_evidence.py`核验仿真及实际源码/ROM；`collect_postroute_evidence.py`核验收尾DCP/报告/工具哈希后归档。
- `monitor_runs.py`只读检查本轮作业日志；本轮作业均已结束。

## 保存规则

每个版本独立stage和输入哈希，已有检查点保持不覆盖。完整实现的最终时序使用200MHz/5ns、UU=0，自动抖动保留，需setup/hold/路由共同通过。综合WNS不能作为达标结果。

V1/V2/V6完整帧均2073600字节逐字节通过，周期分别4959092、4959093、5218778；功能通过不代表200MHz可用。SRL备选整帧主动中止，不能引用其他版本PASS。

子目录README中准备时的说明保留为过程记录；执行状态以最终报告、源码哈希和原始日志为准。`unit_work/`及工具二进制忽略，证据目录的`*.log.txt`明确保留。没有变更C正式工程或150MHz发布版本RTL。
