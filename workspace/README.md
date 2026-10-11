# 当前工作入口

先读 [当前状态](CURRENT_STATUS.md)、[任务矩阵](C_TASK_STATUS.json)，再读 [工作约定](WORKFLOW.md) 和 [必要历史](HISTORY.md)。状态更新于2026-10-11；现有测量截至2026-10-10。

**跨帧方案尚未正式交付。** 单RAM草案评审及停止的C RTL实验作为历史输入保留；当前约20–21fps正确链路、150槽PC4K已测，持续整机4K30未通过。

[C侧执行计划](plans/PLD竞赛2026_C侧执行任务规划_20261007.md) 与本地计划原件同步，含最新进度和历史入口。原计划中的本地绝对路径用于本机复现；GitHub证据对应关系见 [10月10日简洁报告及身份索引](evidence/20261010/INDEX.json)，完整原始数据和大ZIP留本地。

当前冻结交付是 [C→B 延迟优化 V2](../deliverables/c_latency_v2_20261009/README.md)。源码、RTL、约束、MEM、BIT/DCP与原清单字节保持，旧BOARD_PENDING由最终收据及当前状态补充。当前文档同步不升级冻结默认，不代表A/B签收。

本分支 `workspace-maintenance-20261009` 用于工作区同步，未合并到main或C/B分支。当前完整同步清单见 [SYNC_MANIFEST.json](SYNC_MANIFEST.json)，原整理备份见 [CLEANUP_REPORT.md](CLEANUP_REPORT.md)。新任务结果放各自results/，缓存放build/。
