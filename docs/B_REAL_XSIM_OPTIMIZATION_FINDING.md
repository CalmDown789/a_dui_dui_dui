# 真实 B 五层网络：XSim 2022.2 优化选项复核

更新时间：2026-09-23 19:11（本机）

## 已确认

之前的逐字节失配来自 XSim 2022.2 `xelab` 默认优化运行：同一份 B RTL、参数 ROM、输入和整数 Golden，在默认优化下输出错误；使用 `xelab -O0` 后逐项匹配。RTL `ae29515` 本身没有修改。一个混合正负值的四拍标量 PReLU/Q31 探针在默认优化下错 2/4，`-O0` 下错 0/4；`-debug all` 也能复现正确值。

已完成的验证：

- 6×5 逐层探针，`xelab -O0`：L1 INT32 MAC、L1 后处理、L2、L3、L4、L5 phase 输出全部 0 失配。
- C 正式路径 `tb_b_real_bit_exact`，XSim 2022.2 + `xelab -O0`：96×54 的 impulse、ramp、random、zero 四组全部逐字节匹配，`report/sim_result_tb_b_real_bit_exact.txt` 为 PASS；单次仿真耗时约 80 秒。
- `scripts/run_sim.tcl` 已对真实 B 验收组加 `-O0`，只影响 XSim elaboration，不改 RTL，也不改变综合选项。

## 正在进行

`tb_b_real_full` 正用同一正式脚本重跑 960×540 → 1920×1080 全帧 A 整数 Golden，对拍结束前不能将全尺寸验收标为通过。查看 `_sim/tb_b_real_full/xsim.log` 和 `report/b_real_full_summary.json` 获取结果；脚本会在完成后更新 `report/sim_result_tb_b_real_full.txt`。

## 后续本机工作

1. 等全帧逐字节对拍结束；若失败，按首个失配阶段继续查，不沿用默认优化运行的旧结论。
2. 运行 smoke/backpressure 本机回归。
3. 评估本机真实 B+C 综合/实现。旧记录显示一次真实综合约 30 GB 内存后被人工停止；当前机器可用内存约 33.7 GB，需谨慎区分 synth-only 与完整实现。
4. 上板和 HDMI 图像仍需板卡实测；仿真 PASS 不等于 bitstream/板级验收。

当前没有提交 B RTL 修复；已定位并绕开的是本机 XSim 默认优化导致的仿真错误。
