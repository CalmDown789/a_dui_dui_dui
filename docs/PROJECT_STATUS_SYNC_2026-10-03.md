# 项目进度同步快照（2026-10-03，补入 9 月 26 日成果）

本快照汇总 GitHub 上截至 2026-09-26 的最新可核验结果。B 时序实验分支当前提交为 `4b90246`，比 9 月 24 日记录新增 3 个提交；主线、C 集成分支和 B 实验分支的测量结果分别标明，不能互相替代。

## 已完成的功能验证

- **A：模型与量化已冻结。** 配置为 d16/s8/m1/c16。Set5 平均 PSNR：双三次 32.6398 dB、FP32 34.1202 dB、INT8/INT16 34.0190 dB。见[主线项目说明](../README.md)。
- **B+C：全尺寸整数仿真通过。** 960×540 输入产生 2,073,600 字节输出，与 A 整数 Golden 逐字节一致，失配为 0。C 集成基线的仿真记录使用 XSim 2022.2 `-O0`，详见[全帧与 C 端状态记录](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/docs/CURRENT_PROJECT_STATUS.md)。
- **C：100 MHz 单帧上板验证通过。** UART 收到完整的 2,073,600 字节并与 Golden 逐字节一致，失配为 0；后布线 WNS 为 +0.464 ns。约 22.43 秒/帧是 UART 回传时间，不代表 CNN 计算帧率。见[100 MHz 板测报告](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/report/c_board_100mhz/BOARD_TEST_REPORT_2026-09-24.md)。

## B 的 150 MHz 最新候选

9 月 26 日 B 实验分支推荐 `route_setup030` 候选，恢复原评价条件后的 WNS/TNS 为 **+0.492/0 ns**，WHS/THS 为 **+0.018/0 ns**。相比此前 NetDelay 候选的 +0.132 ns，WNS 提升 0.360 ns。使用的实验实现流程包含 L5 phase 网络 `MAX_FANOUT 48`、布局/物理优化/布线指令和额外 setup 加压布局；报告保留加压与恢复后时序数据。

该候选仍是 Vivado 2025.2 的实验实现结果：没有生成候选 bitstream，也没有上板测试；报告指出当前 XDC 缺少 9 个输出端口的 output delay，UART 引脚约束也未达到完整板级签核口径。因此 **+0.492 ns 不能写成 C 的板级时序通过**。详见[B 端 150 MHz 裕量补试报告](https://github.com/CalmDown789/a_dui_dui_dui/blob/member-b-2025-2-bc-trial/docs/MEMBER_B_150MHZ_MARGIN_2026-09-26.md)。

## B 的 200 MHz 优化收尾

200 MHz 仍未达到时序目标。V1 nominal 是建议继续的主基线，WNS/TNS 为 **−0.164/−7.523 ns**，有 226 个 setup 违例端点；同轮最高 WNS 记录为 −0.162 ns，但 TNS 为 −45.955 ns、813 个违例端点。V6 完整功能验证通过，布线 WNS 为 −0.638 ns，较 V2 更差，因此不采用。

V1、V2、V6 都完成真实五层网络全帧整数 Golden 对拍：输出均为 2,073,600 字节、失配 0，X=0；仿真周期分别为 4,959,092、4,959,093、5,218,778。这些是实验 RTL/叠层的仿真证据，不是板上连续帧帧率。详见[B 端 200 MHz 收尾报告](https://github.com/CalmDown789/a_dui_dui_dui/blob/member-b-2025-2-bc-trial/docs/MEMBER_B_200MHZ_TIMING_2026-09-26.md)。

## C 端实现状态与结果边界

- C 自己的 150 MHz 实现记录来自 Vivado 2022.2，布线后 WNS/TNS 为 −0.210/−36.940 ns；bitstream 虽已生成，但未下载上板，也没有 150 MHz UART/Golden 对拍。该结果不是 B 的 +0.492 ns 候选。
- C 真实 B+C 的 200 MHz 基线布线记录 WNS/TNS 为 −2.208/−50,037.625 ns，时序未闭合。
- 因此当前最强的板级证据仍是 100 MHz 单帧通过。尚无 150 MHz 板测、连续帧系统吞吐或 HDMI 图像验收证据。

## 下一阶段

B 在 9 月 26 日的交接建议 C 以 150 MHz 候选和完整板级约束建立独立构建，完成上板单帧检查，再推进“不同的预录连续帧输入 → FPGA 超分 → PC 回传播放”。当前帧率暂不设严格门槛；摄像头和 HDMI 属于后续竞赛工作。200 MHz 优化可以继续，但不阻塞 C 验证 150 MHz 和连续帧通路。详见[B→C 板测交接](https://github.com/CalmDown789/a_dui_dui_dui/blob/member-b-2025-2-bc-trial/docs/MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md)。

## 旧状态文档

C 分支的旧版 [CURRENT_PROJECT_STATUS.md](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/docs/CURRENT_PROJECT_STATUS.md) 记录早于 9 月 26 日交接，其中“没有 bitstream、没有板测”也与同分支后续 100 MHz 板测报告冲突。应按各专项报告及其源树/工具/约束边界引用数据；本快照补充统一摘要，旧实验记录保留供追溯。
