# 200 MHz 候选单元仿真证据

2026-09-26，Vivado/XSim **2025.2**，SW Build **6299465**，成功会话 PID **33224**，19:19:40–19:20:28（北京时间），`xelab -O0`。本轮五组候选的八个仿真 top 全部通过；本证据不代表整网回归、200 MHz 静态时序或板测通过。

完整记录见 [`summary.json`](summary.json)：真实配置/coverage、8 个工作目录、27 份 RTL/参考模块/TB/runner/头文件的 raw 与 CRLF→LF canonical SHA-256，以及逐份日志的原路径和字节哈希。

| 候选/测试 | 实际结果 |
|---|---|
| bias_early | 5/5 配置 PASS；逐拍原件对照和独立数学检查均通过 |
| mac_buffer | 131 位 FIFO PASS；full+pop 禁止输入 265 次，连续同时 push/pop 最长 23 拍 |
| stripe_pipe | 新增 TB 及原 `tb_stripe_buffer`、`tb_backpressure_rand` 共 3 个 TB PASS |
| requant scalar | 6/6 配置 PASS，每组检查 3122–3168 项；完整 INT64 probe 1094 项 PASS |
| requant shared | 3/3 配置 PASS，每组输出 354 个向量；在途复位与反压检查通过 |
| fifo_srl | 7/7 配置 PASS；6400×4 目标组满时交换 534 次，最长无泡运行 40 拍 |

每个子目录保存原始 xvlog、xelab、XSim stdout 和 `xsim_engine.log` 文本，共 35 份成功工具日志；顶层另有本轮 Vivado 完整日志。为便于 Git 跟踪，归档名追加 `.txt`，**内容逐字节复制，未清洗或截取**。没有复制 DLL、仿真快照、波形或临时二进制。成功日志未发现 fatal/error/warning；配置 PASS 的实际行数为 5、6、3、7，各最终标志仅出现一次。

## 首次运行的日志路径冲突

`runner_log_collision/` 保留首次 PID `19484` 的 Vivado 总日志和 bias 单元的原始 XSim 日志。首次命令未显式指定 XSim 内部日志路径，却把 stdout 也重定向到默认 `xsim.log`。两个写入源交错，使已完成仿真的 PASS 行重复：配置 PASS 实际出现 **7 行而非 5 行**，最终 PASS 出现 **2 行**，runner 因精确计数拒绝该次结果。

这是 **runner 日志输出冲突，不是 RTL 对拍失败**。首次 XSim 日志没有 RTL fatal/error，且已有最终 PASS。修复后 xvlog/xelab 使用 `--nolog`；XSim 用 `-log xsim_engine.log`，stdout 独立写 `xsim.log`。PID `33224` 重跑全部五组后，每组标志计数唯一且总入口出现 `MARGIN200_SELECTED_UNITS_COMPLETE`。本归档的正式 PASS 结论只引用后一次成功运行。

后续完整网络与物理实现应另存对应证据，不覆盖这些单元原始日志。哈希采集针对本轮成功运行后已固定的源文件；文档更新不改变这些 RTL/TB/runner 哈希。
