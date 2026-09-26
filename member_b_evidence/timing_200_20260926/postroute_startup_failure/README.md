# 物理收尾入口环境失败

首次调用在读取DCP前，因Vivado设置的Python标准库环境与外部Python解释器不兼容，出现`SRE module mismatch`。没有执行物理优化，也没有修改原DCP。`finish.tcl`的两处外部Python调用均加入`-I`隔离环境；在新stage `postroute200_v2_pressure000_try2`完整重跑。原失败stage和日志保留，此记录不算实现失败或时序结果。
