# 真实 B 五层网络：XSim 2022.2 优化选项复核

更新时间：2026-09-23 19:47（本机）

## 已确认

之前的逐字节失配来自 XSim 2022.2 `xelab` 默认优化运行：同一份 B RTL、参数 ROM、输入和整数 Golden，在默认优化下输出错误；使用 `xelab -O0` 后逐项匹配。RTL `ae29515` 本身没有修改。一个混合正负值的四拍标量 PReLU/Q31 探针在默认优化下错 2/4，`-O0` 下错 0/4；`-debug all` 也能复现正确值。

已完成的验证：

- 6×5 逐层探针，`xelab -O0`：L1 INT32 MAC、L1 后处理、L2、L3、L4、L5 phase 输出全部 0 失配。
- C 正式路径 `tb_b_real_bit_exact`，XSim 2022.2 + `xelab -O0`：96×54 的 impulse、ramp、random、zero 四组全部逐字节匹配，`report/sim_result_tb_b_real_bit_exact.txt` 为 PASS；单次仿真耗时约 80 秒。
- `scripts/run_sim.tcl` 已对真实 B 验收组加 `-O0`，只影响 XSim elaboration，不改 RTL，也不改变综合选项。

## 已完成复核

- 同一 `scripts/run_sim.tcl`、RTL/ROM/Golden 的 96×54 四组对照复跑：默认优化 0/4
  通过，四组均出现输出失配；`C_REAL_B_XELAB_OPT=o0` 为 4/4 PASS、0 失配。
- `xelab -O0` 的 960×540 → 1920×1080 全帧复跑 PASS：输入 518,400/518,400，输出
  2,073,600/2,073,600 字节匹配，X=0，17 个条带尾、1 个帧尾、0 个保持规则违例，
  仿真 4,180,016 周期、32 分 38 秒。摘要在 `report/b_real_full_summary.json`，原始
  elaboration/XSim 日志与结果在 `report/xsim_repro/o0/960x540/`。

default 与 `-O0` 的逐项数据哈希及存档路径见 `docs/B_REAL_XSIM_REPRODUCIBILITY.md`。

## 后续本机工作

1. 运行本机真实 B+C synth-only，并记录资源/时序报告和峰值内存；先不直接启动完整实现。
2. 结合 synth-only 数据评估是否运行 place/route。旧记录显示一次真实综合约 30 GB 内存后被人工停止；本机约 33.7 GB 总内存。
3. 上板和 HDMI 图像仍需板卡实测；仿真 PASS 不等于 bitstream/板级验收。

当前没有提交 B RTL 修复；已定位并绕开的是本机 XSim 默认优化导致的仿真错误。
