# SRTP 工作入口

- 本地工作区先读 `docs/CURRENT_STATUS.md`、`docs/WORKFLOW.md`、`docs/HISTORY.md`；GitHub 同步仓库对应文件在 `workspace/`。
- 当前基线是 2026-10-09 四步整合及延迟优化 V2。本地在 `output/C_TO_B_LATENCY_HANDOFF_V2_20261009/`，GitHub 在 `deliverables/c_latency_v2_20261009/`。
- 冻结交付保持字节不变；最终状态以外部最终收据和当前摘要补充。旧 `BOARD_PENDING` 原文不得用作最新结论。
- 新任务放 `candidates/<日期>_<任务>/`，产物 `results/`，缓存 `build/`；根目录不放一次性探测文件。
- 一次任务一份简短结果，长期状态只留基线、证实结果、限制和下一步；不积累命令流水账。
- 修改源码先确认源树、工具、约束、BIT/DCP 和数据身份；软件指标、仿真、数字时序、板测、PC4K 与整机吞吐分别引用。
- 原始失败/恢复证据、Git 历史和未提交源码保留。生成缓存可清理；删除前核实路径边界并保留必要日志与清单。
- 清理备份在 `C:/Users/Administrator/srtp_backup/2026-10-09-workspace-cleanup/`；不将旧日记重新展开到工作区。
- GitHub 当前维护分支 `workspace-maintenance-20261009`；不要把整理自动视为合并到 main 或 C/B 分支。
