# 当前工作入口

先读 [当前状态](CURRENT_STATUS.md)，再读 [工作约定](WORKFLOW.md) 和 [必要历史](HISTORY.md)。

当前可运行交付是 [C→B 延迟优化 V2](../deliverables/c_latency_v2_20261009/README.md)，包含源代码、RTL、约束、模型 MEM、输入/Golden、BIT/DCP、构建/回归证据和离线核验工具。冻结文件保持原始字节；其中原状态可能早于最终板测，应按当前状态摘要和最终收据引用。

完整 512 帧原始证据包及历史候选保留本地，SHA256、大小、索引见 V2 的 EVIDENCE_ARCHIVE_INDEX.json 与本目录交付收据。GitHub 文件清单见 SYNC_MANIFEST.json，整理数量与备份位置见 CLEANUP_REPORT.md。

新任务采用 candidates/<日期>_<任务>/，结果写 results/，缓存写 build/；任务结束只维护一份简短结果和当前状态，避免重复流水账。
