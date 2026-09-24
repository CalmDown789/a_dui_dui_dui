# 成员B：Vivado 2025.2 B+C 实验取证

完整结论与边界见 [`../docs/MEMBER_B_2025_2_TRIAL_STATUS_2026-09-24.md`](../docs/MEMBER_B_2025_2_TRIAL_STATUS_2026-09-24.md)。

- `raw_sim/`：XSim 原始日志，含 36/48 位全帧和 150 MHz 精确源码短回归。
- `sim_reports/`：对应的仿真汇总。
- `real_banks/`：从 A 冻结输入 ROM 拆出的 16 个真实图像 bank 和 SHA-256 清单；来源须由 `scripts/prepare_ref_data.py` 校验。
- `rom_tb/`：真实 bank16 ROM 同步读与边界地址测试。
- `route_reports/`：每个独立候选的 Vivado 原始资源、时钟、DRC、路由和时序报告。
- `route_realrom_*_console.log`：综合与实现原始控制台日志。首次中文路径崩溃和两次 BRAM 级联 DRC 失败也保留，不能计为成功实现。

AMD 登录认证令牌和安装器下载链接不属于工程证据，不随分支提交。
以上结果是独立实验 overlay，尚未替换 C 正式 RTL，也没有实体板验收。
