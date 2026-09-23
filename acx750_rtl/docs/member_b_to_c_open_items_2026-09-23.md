# 成员B工作：交成员C确认与签核的事项（2026-09-23）

成员B现有 `fsrcnn_network_mem_top.sv` 通过 `96×54` 整链 XSim bit-exact，共享后处理、MAC 平衡树流水与同步 PixelShuffle 读口替换后已复测。另已用 C ZIP 的 `c_core` 副本完成 6×5 真实 B 接入对拍。以下事项归 C 的板级工程或必须使用 C 的目标器件环境完成；B 的参数 ROM bank 优化仍由 B 负责，MAC 与后处理的实际 DSP 用量也待综合确认。

1. 请提供能识别 `xc7a200tfbg484-2` 的 Vivado 工程/器件支持，或该板实际准确 part 与 ACX750 参考工程。B 当前本机不能签目标资源和时序；2026-09-23 另遇 Vivado batch 在读 RTL 前 `Failed to install all user apps / load_features failed`，XSim 正常。
2. 请提供板级 200 MHz 时钟来源、`rst_n` 与 MMCM locked 的连接方式及 XDC；若实现后只能稳定在其他频率，请给 `report_timing_summary` 和目标频率，不把 200 MHz 当作已实现值。
3. 请用 v1.1 ready/valid 接口接入 `fsrcnn_network_mem_top`：输入 stall 时 ROM 地址、Y 数据和输入坐标保持；输出按 `out_valid&&out_ready` 写 C 的 64-row ping-pong，`stripe_last/frame_last` 随 token 保持。请确认综合后 C 侧 ROM 与 64-row 双 bank 的 RAMB36 实际用量，尤其 60 RAMB36 预算。
4. 请提供按模块拆分的 `report_utilization` 和关键路径，使 B 能针对 MAC 加法树、后处理乘法、参数 bank、PixelShuffle 读口优化。当前 370 DSP/271 RAMB36 仍为理论预算。

当前没有新的成员A模型或量化语义待确认；本轮对拍直接使用其已审计整数交付。

5. C ZIP 的 `b_core_if.v` 对真实 `b_core_real` 未传 `IMG_W/IMG_H/STRIPE_H`，而 B 顶层默认 960×540；请 C 在正式接入时给该实例传入三项参数。本地小尺寸联调仅在隔离副本中补了这项连接，C 原件未改。
6. C 现有四个 TB 的数据 scoreboard 以最近邻 stub 为期望值；启用真实 B 后必须改为 FSRCNN 整数黄金，不应期待原样全 PASS。B 可提供 6×5 与 96×54 的独立整数参考及一键 XSim。
7. C 报告中 C 侧骨架已用 192 RAMB36，原 v1.1 预估 C 侧 187 块；请据合并后的真实 B 综合重新核算总量，并对齐物理块与 KiB 两种口径。背压七项及逻辑缓冲明细见 `member_b_backpressure_contract.md`。
