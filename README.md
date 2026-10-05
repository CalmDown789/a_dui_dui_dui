# C 观测修复：T6 板测交接

**最新入口：[独立验收与冻结版本](verified_t6/README.md)。** 80 帧实际 UART 全部独立对拍一致；100MHz 两版及150MHz 普通版的原始板测证据完整验收通过，150MHz 暂停版尚缺46个原始附件。以下原 T5 与 C T6 报告保持历史身份，不能据它们把所有四组合标为已独立验收。当前自然视频基线为新150MHz 普通镜像，暂停修复源码已纳入 `303b51d`。

**C 当前先做：[16 帧连续自然视频联调](natural_video/README.md)，[下载完整联调包](natural_video/natural_video_16frames.zip)。** 包内含已通过的150MHz普通版BIT/LTX、16帧连续自然输入、整数Golden、串口采集、VIO/ILA检查及无损离线播放器。PC准备与软件工具检查通过；实体自然视频尚未执行，需要 C 实际采集并返回证据。46个旧附件补交降为低优先级，不阻塞这一主线。

## 2026-10-05 T6 实体板验收更新

100/150MHz × 普通/暂停四个**实际烧录镜像**的 T6 均为 **PASS / BOARD_PASS**。80帧逐字节Golden一致，8帧受控暂停实际forced-block>0。100MHz普通版使用原交付BIT，其余三组合为本地C覆盖修复重建；通过状态只绑定验收报告中的BIT/LTX哈希，旧交付ZIP镜像不继承该状态。

详见 [T6阶段验收报告](delivery/t6_20261005/T6_ACCEPTANCE_REPORT.md) 和 [当前机器状态](delivery/t6_20261005/T6_STATUS.json)。自然视频连续输入→FPGA超分→PC回传播放仍 **NOT_RUN**，200MHz继续 **PAUSED**。原T5离线清单、原150MHz暂停版额外压力失败与下文交接记录保留为历史记录。完整原始二进制证据包已在本机冻结，尚未上传GitHub；远程同步报告、复核和哈希索引。

## 原始 T5 交接记录（固定提交 b828e7a）

本分支 `c-obsfix-delivery-20261005` 是独立交付分支。T0–T5 离线完成，100/150 MHz、pause=0/1 四组合均为 **BOARD_READY**；本次实体 T6 **NOT_RUN**。原 C/main/B 分支及 200 MHz 暂停任务不在本次修改范围内。

## C 从这里开始

1. 下载本分支 ZIP，或在独立目录检出本分支，保留原已通过镜像、失败证据和已有工作区修改。
2. 先读 [板测指南](delivery/C_BOARD_GUIDE.md) 和 [T5 交付索引](delivery/T5_delivery.md)。
3. 按 [交付校验清单](delivery/DELIVERY_MANIFEST.json) 核对下面三个 ZIP 的长度与 SHA256。它们合计约 15 MB。
4. 将 `obsfix_board_images.zip` 解压到新的短 ASCII 路径，核对每组合 BIT/LTX，再使用 Vivado 2025.2 / xc7a200tfbg484-2 按指南进行 T6。
5. 需要审查或重建时，将 `obsfix_sourcekit.zip` 解压到另一个新的短 ASCII 根目录，并阅读 [重建指南](delivery/REBUILD_GUIDE.md)。不要直接把本分支顶层的审查源码当成完整重建工程；完整依赖闭包在 sourcekit 中。

## 下载内容

- [obsfix_board_images.zip](delivery/obsfix_board_images.zip)：四组配套 BIT/LTX、板测指南、VIO 导出和解码脚本。
- [obsfix_sourcekit.zip](delivery/obsfix_sourcekit.zip)：固定 B 依赖、C 修复源码、参数 ROM、IP 配方、重建与回归入口、Git bundle/patch。
- [obsfix_evidence.zip](delivery/obsfix_evidence.zip)：离线仿真返回、时序/路由/DRC 报告、失败及恢复的原始日志。
- [FINAL_RECEIPT.json](delivery/FINAL_RECEIPT.json)：离线完成范围与交付校验收据。
- [MORNING_REVIEW.md](delivery/MORNING_REVIEW.md)：结果概览。

`DELIVERY_MANIFEST.json` 与收据还记录了约 907 MB 的 `obsfix_checkpoints.zip`。该可选 DCP 包已在本地核验，但**未上传本分支**；开始 T6 不需要它。若需要网表检查，再通过单独附件或 Release 交付。此处保留原始清单字节，不删除该记录。

## 验收与回传

- 普通版两频率：按指南分别测试四种不同 960×540 输入，以及 16 帧连续输入。独立会话从空闲复位开始，连续帧之间不复位。UART 为原协议 921600 baud、8N1，每帧返回 2,073,600 字节并逐字节匹配对应 Golden。
- 暂停版两频率：按指南施加并释放 VIO 受控暂停，必须实际出现 `pause_request_cycles > 0` 和 `pause_forced_block_cycles > 0`，释放后正常完成、Golden 一致、保持/协议错误为 0。
- 每组合独立记录 PASS/FAIL/NOT_RUN。回传 BIT/LTX 哈希和烧录日志、输入/Golden/实际 UART 原始文件、逐帧比较结果、VIO 原始 CSV 与 31 字段解码、暂停 ILA 导出、复位/帧号/快照数量记录、冷上电后重新 JTAG 配置与空闲复位检查。失败保留准确命令和完整日志。
- T6 实际通过的组合才可以改为 BOARD_PASS。板测四种图案重复 16 帧，不直接等于当前任务书的自然视频回传播放验收。

## 结果与边界

| MHz | pause | 原正式约束 WNS (ns) | 额外 +0.300 ns 压力 WNS (ns) |
|---:|---:|---:|---:|
| 100 | 0 | +0.717 | +0.417 |
| 100 | 1 | +1.088 | +0.788 |
| 150 | 0 | +0.404 | +0.104 |
| 150 | 1 | +0.252 | -0.048 |

四组合正式原约束门控通过；150 MHz pause=1 额外压力项未通过，不能宣称所有压力项通过。八帧短图实际 UART 解码全部匹配 Golden，不替代实体板测试或本轮新全尺寸系统回归。

最小源码修复提交：`659a86183aa84174d4aad0a5aae99ee482e0a6e4`，仅 `multiframe/rtl/c_observation.v` 与 `scripts/configure_observation_debug_ip.tcl` 两处逻辑变化。固定 B 为 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`；原 C 基线为 `86df150d45ff8f98b976053ce293688133bc12e9`，补交证据为 `d6b13e625a15d952b6d3b657428472c1f51b1242`。原板级 XDC 与 B RTL 未改。
