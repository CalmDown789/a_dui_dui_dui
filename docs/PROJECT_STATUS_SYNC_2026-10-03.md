# 项目进度同步快照（2026-10-03）

本快照根据 GitHub 上截至 2026-09-25 可见的项目记录整理。数据证据主要形成于 2026-09-24；未发现更晚的验收报告。主线、C 集成分支和 B 时序试验分支的结果按各自来源记录。

## 已完成

- **A：模型与量化已冻结。** 配置为 d16/s8/m1/c16。Set5 平均 PSNR：双三次 32.6398 dB、FP32 34.1202 dB、INT8/INT16 34.0190 dB。见 [主线项目说明](../README.md)。
- **B+C：全尺寸整数仿真通过。** 960×540 输入产生 2,073,600 字节输出，与 A 整数 Golden 逐字节一致，失配为 0。仿真记录采用 XSim 2022.2 `-O0`，见 [C 端状态记录](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/docs/CURRENT_PROJECT_STATUS.md)。
- **C：100 MHz 单帧上板验证通过。** ACX750 已配置 bitstream，UART 收到完整的 2,073,600 字节，和 Golden 逐字节相同；后布线 WNS 为 +0.464 ns。UART 回传约 22.43 秒/帧是传输时间，不代表 CNN 计算帧率。见 [100 MHz 板测报告](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/report/c_board_100mhz/BOARD_TEST_REPORT_2026-09-24.md)。

## 时序状态与边界

- **C 的 150 MHz 实现没有通过时序。** Vivado 2022.2 已完成布线并生成 bitstream，但后布线 WNS/TNS 为 -0.210/-36.940 ns；bitstream 未下载到板卡，也没有 150 MHz UART/Golden 对拍。见 [C 端 150 MHz 实现记录](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/report/c_board_150mhz/IMPLEMENTATION_STATUS_2026-09-24.md)。
- **B 的 +0.132 ns 是另一项实验结果。** 它来自 B 的 150 MHz 时序优化候选和实验叠层，不代表 C 的 150 MHz 实现通过，更不代表上板验证。见 [B 端时序试验报告](https://github.com/CalmDown789/a_dui_dui_dui/blob/main/docs/MEMBER_B_150MHZ_TIMING_OPT_2026-09-24.md)。
- **C 的 200 MHz 真实 B+C 路径尚未闭合。** 已记录的一次布线结果 WNS/TNS 为 -2.208/-50,037.625 ns；这些资源和时序数据属于对应实现基线，不能和 100 MHz 板测、B 的 150 MHz 实验混成一组验收结果。
- **1080p30、连续帧稳定性和 HDMI 图像验收尚无通过证据。** UART 单帧回读速度不是核心吞吐率。

## 下一步

1. 选定唯一的 C RTL/约束基线，针对真实后布线路径继续优化并复核完整约束。
2. 在明确时序门槛后，重新生成并下载对应 bitstream；验证连续帧运行和图像输出。
3. 将通过的源树、约束、资源/时序报告、bitstream 哈希及板测数据归档到同一验收版本。

## 状态文档说明

C 分支的旧版 [CURRENT_PROJECT_STATUS.md](https://github.com/CalmDown789/a_dui_dui_dui/blob/c-side-latest/docs/CURRENT_PROJECT_STATUS.md) 仍保留了 2026-09-24 较早的“没有 bitstream、没有板测”描述，与同分支后续发布的 100 MHz 板测报告冲突。上述板测报告和 150 MHz 实现报告是对应事项的直接证据；本快照用于给出统一摘要，旧文档中的实验记录仍保留供追溯。
