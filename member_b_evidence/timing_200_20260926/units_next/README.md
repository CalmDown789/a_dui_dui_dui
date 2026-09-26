# 第二组备选单元仿真证据

Vivado/XSim **2025.2**，PID `30704`，会话时间 **2026-09-26 19:43:47–19:44:20（Asia/Shanghai）**。入口 `experiments/timing_200_20260926/run_units200_next.tcl`，最终打印 `MARGIN200_NEXT_UNITS_COMPLETE`，Vivado 正常退出。

| 包 | 实际通过范围 |
|---|---|
| post_shift | 5 配置，GROUPS=1/2/4/8，独立数学模型、逐拍旧版等价、槽复用及复位/反压 |
| stripe_banked | 5 深度配置（122880/8197/4096/32/1），加 tb_stripe_pipe、tb_stripe_buffer、tb_backpressure_rand |
| mac_buffer_l3l5 | 实际 259/131 位，两槽独立队列模型、反压断链行为、复位与数据守恒 |

共 **3 包、6 个 testbench、29 份原始文本日志**。`summary.json` 保存实际 PASS/覆盖行、20 个源文件的 raw/canonical SHA-256，以及日志 SHA-256。日志按原始字节复制，扩展名 `.log.txt` 用于 Git 归档；不含 DLL、WDB、仿真快照或二进制临时文件。

三项主要配置计数分别为 5、5、2，PASS 行均在标准输出日志中恰出现一次。编译/展开/仿真日志没有 warning/fatal/error；合法成功文本 `0 error` 不算失败。XSim 引擎日志与标准输出已分别归档。

post_shift 每配置接受 422、输出 418 个向量，4 个由定向复位作废。MAC L3 的 691=683+8，L5 的 683=673+10；两个宽度最长持续吞吐均 23 拍。具体 stall/reset 及 bank 边界命中数见 summary。

这些是独立单测和列出的 stripe/C 回归证据。V2 真实五层 Golden 回归、200 MHz 完整布局布线及上板结果另行记录，不能由本次 PASS 推定。
