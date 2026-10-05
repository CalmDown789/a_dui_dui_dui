# C 观测修复后 T6 实体板阶段验收报告

验收日期：2026-10-05（Asia/Shanghai）。交付起点：`b828e7a8f2aab47fee8b07ce3b446377c14c2997`；固定 B：`6cc8ea4173d2a720f741e80b7cbd9279558ee93a`。

## 结论与完成范围

交接指南要求的 100/150MHz × 普通/暂停四组合 T6 板测已完成，四组合分别为 **PASS / BOARD_PASS**。80 帧实际 UART 原始文件在本次报告复核中逐字节比较 Golden，全部一致；8 帧受控暂停都实际产生 request 和 forced-block，释放后正常完成。

当前完整任务书尚未全部验收：预录自然视频连续多帧输入 → FPGA 超分 → PC 回传播放仍为 **NOT_RUN**。200MHz 按用户要求继续 **PAUSED**。本报告为 T6 阶段验收，不升级自然视频、摄像头/HDMI、30fps、Flash 自主启动、忙时复位或用户掌握状态；REQP/BRAM 异步复位结构风险继续 OPEN。

| MHz | pause | 实际通过 attempt | T6 / 状态 | Golden 逐帧一致 | VIO 快照数 |
|---:|---:|---|---|---|---|
| 100 | 0 | `100_p0_delivery01` | PASS / BOARD_PASS | 4/4 + 16/16 | 4 + 16 |
| 100 | 1 | `100_p1_cfix01` | PASS / BOARD_PASS | 4/4 + 16/16 | 4 + 16 |
| 150 | 0 | `150_p0_physfix01` | PASS / BOARD_PASS | 4/4 + 16/16 | 4 + 16 |
| 150 | 1 | `150_p1_physfix01` | PASS / BOARD_PASS | 4/4 + 16/16 | 4 + 16 |

普通版为 S04/S16；暂停版为 P04/P16。四帧输入为四种不同 960×540 uint8 Y，16 帧按四图案重复四轮；独立会话从 S0 空闲复位开始，会话内连续帧之间不复位。UART 921600 baud、8N1；每帧返回 2,073,600 字节，输出为 1920×1080 uint8 Y。

## 实测镜像身份与源码边界

BOARD_PASS 严格绑定下面的实际烧录 BIT/LTX。100MHz 普通版使用原交付镜像；另外三组合使用 sourcekit 中的本地 C 覆盖修复重建。原 T5 ZIP 的相应旧 BIT 不能继承新 BIT 的板测结论，原 ZIP、离线清单和失败记录保持历史身份。

本地覆盖修复属于 C 的 `candidate/multiframe/rtl/c_core.v`：暂停时已缓存的一拍仍可能被下游接收，接收后应清除 valid，避免重复发送；B RTL 和原板级 XDC 保持原身份。本地覆盖未作为 B/main 的源码修改提交；以 [SOURCE_PROVENANCE.json](SOURCE_PROVENANCE.json)、[C 修复差异](c_core.v.patch) 和测试台差异标识。C core SHA256 为 `8f708588ae719c85abcfa5b392444e644a015b40eefb003b1e9ad165694125e3`，不能仅用继承的 `659a861...` 元数据表示这些重建镜像。

### 100MHz_pause0

- c_board_100mhz.bit: 9,730,787 字节，SHA256 `d9b97465ce259d23fd4879c927feaa11366605dfa9dd008e09cfdcf6d3adb5d5`。
- c_board_100mhz.ltx: 358,912 字节，SHA256 `e8bb272f5d498fc2418cabc0ad18dfa795552aa933b1c90a4c735591e7cefbe5`。

### 100MHz_pause1

- c_board_100mhz.bit: 9,730,787 字节，SHA256 `0a7064123ae699ea2182fb1f783e8f0ca632d95c8a35bf3a898e206291147c32`。
- c_board_100mhz.ltx: 358,912 字节，SHA256 `e8bb272f5d498fc2418cabc0ad18dfa795552aa933b1c90a4c735591e7cefbe5`。

### 150MHz_pause0

- c_board_150mhz.bit: 9,730,787 字节，SHA256 `a907a50af0528d2149b369a404eb0eade3b282a14e1e9b1e7419acf66b43c0cd`。
- c_board_150mhz.ltx: 358,912 字节，SHA256 `1aa99107dbfbf3ee5ef7edebe88d7f581427ff38c15410fe132c96a67445bb66`。

### 150MHz_pause1

- c_board_150mhz.bit: 9,730,787 字节，SHA256 `667988e18f3b466f9caecf71a3be5e1321bd8fb4f38693205e4f96ebf544fa96`。
- c_board_150mhz.ltx: 358,912 字节，SHA256 `1aa99107dbfbf3ee5ef7edebe88d7f581427ff38c15410fe132c96a67445bb66`。

## 板卡、烧录与复位

Vivado 2025.2；构建设备为 xc7a200tfbg484-2。板卡实物标识检查由用户确认完成；原始文字/照片未另行采集。JTAG 实读为 `xc7a200t_0` / PART `xc7a200t` / IDCODE `13636093`，Digilent JTAG-SMT2 序列号 `250520092545`。JTAG 读值不能单独证明封装和速度档。

各组合保留 program Tcl、实际命令回执、Vivado log/jou、BIT/LTX 哈希以及一个 u_obs_ila、一个 u_obs_vio 的识别记录。冷上电、配置后 S0 按下/释放为用户确认的物理操作；空闲基线由 VIO/ILA 导出复核，各独立四帧/16帧会话前另有复位基线。精确按键按下/释放时刻未由操作者提供，不补造时间。

| 组合 | 会话 | 原始会话身份 | 快照数量 |
|---|---|---|---:|
| 100MHz_pause0 | S04 | `100_p0_delivery01-S04-2026-10-05T19:27:25.7324709+08:00` | 4 |
| 100MHz_pause0 | S16 | `100_p0_delivery01-S16-2026-10-05T19:32:36.729047+08:00` | 16 |
| 100MHz_pause1 | P04 | `100_p1_cfix01-P04-2026-10-05T19:48:50.9955539+08:00` | 4 |
| 100MHz_pause1 | P16 | `100_p1_cfix01-P16-2026-10-05T19:53:18.9053472+08:00` | 16 |
| 150MHz_pause0 | S04 | `150_p0_physfix01-S04-2026-10-05T17:01:35.0571722+08:00` | 4 |
| 150MHz_pause0 | S16 | `150_p0_physfix01-S16-2026-10-05T17:09:05.5772756+08:00` | 16 |
| 150MHz_pause1 | P04 | `150_p1_physfix01-P04_retry04-2026-10-05T18:16:19.7997564+08:00` | 4 |
| 150MHz_pause1 | P16 | `150_p1_physfix01-P16_attempt01-2026-10-05T18:27:37.399726+08:00` | 16 |

## VIO、ILA 与暂停验收

全部 16 槽原始 VIO CSV 和 31 字段解码 JSON 已保存。有效槽的 frame_id/slot_index 顺序正确；四帧 count=4，16帧 count=16，未使用槽有效位为0；每帧 input_accept_count=518400、output_accept_count/uart_bytes_delta=2073600、stripe_last_accept_count=17、frame_last_accept_count=1，frame_start_seen/core_done_seen/session_done/uart_final_idle=1，core_busy_at_session_done=0。

协议、溢出、loader/frame/UART framing 错误和两种保持违例均为0，暂停在完成时已释放；64位周期/停顿字段完整保留。错误字段仍按复位以来累计或 sticky 语义理解。ILA 每份1024样本，所验溢出探针全0；暂停版逐帧 forced 触发和 done 触发的原始 ILA/CSV 均存在且信号实际出现。

| MHz | 暂停帧号 | pause_request_cycles | pause_forced_block_cycles |
|---:|---:|---:|---:|
| 100 | 0 | 51719265 | 27554737 |
| 100 | 1 | 50548841 | 27685680 |
| 100 | 2 | 51477526 | 28067649 |
| 100 | 3 | 52012544 | 28936980 |
| 150 | 0 | 77768391 | 43593482 |
| 150 | 1 | 76161905 | 42588200 |
| 150 | 2 | 77615599 | 44040710 |
| 150 | 3 | 77812827 | 43433314 |

P04 在内部 VIO bit4 施加并释放受控暂停；P16 是随后独立复位的16帧连续输入会话，不要求每帧继续暂停。停止 PC 串口读取未被用作内部背压证明。周期值包含供数、等待和背压，不能作为纯 CNN 计算时间或30fps证据。

## 时序边界与历史失败

| 实际验收镜像 | 正式约束 WNS(ns) | +0.300ns压力 WNS(ns) |
|---|---:|---:|
| 100 pause0 原交付 | +0.717 | +0.417（原 T5 报告） |
| 100 pause1 f100_p1_quick02 | +0.551 | +0.251 |
| 150 pause0 f150_p0_physfix01 | +0.455 | +0.155 |
| 150 pause1 f150_p1_physfix01 | +0.314 | +0.014 |

原交付150MHz暂停镜像的额外压力项仍是 -0.048ns / FAIL，历史结论保持；上表后三项属于不同的本地重建实现。正式约束、压力项与实体板测试分开记录。不能把新镜像的结果追溯改写为原交付所有压力项都通过。

各失败/无效尝试和完整命令日志保留在原 run 目录。暂停窗口未覆盖有效输出而 forced=0 的尝试未用于通过判定。PowerShell 包装回执错误发生在 UART 对拍通过之后，按主机记录问题保留；100MHz暂停版P16在电脑重启后重连同一 FPGA 并导出快照，保留首次中断和重试记录，以最终16帧UART、16快照和ILA复核通过，不重造采集证据。

## 交付索引与复核

- [当前状态](T6_STATUS.json)：四组合实际镜像身份、T6结果与未验收范围。
- [独立复核结果](T6_ACCEPTANCE_AUDIT.json)：80帧原始返回逐字节比较、31字段与暂停/ILA核验。
- [执行报告验收副本](T6_EXECUTION_REPORT.json)：烧录、输入/Golden、UART、CSV/JSON、复位、ILA、失败与准确命令索引。原结果文件保留；副本记录两处错误日志路径与一处未更新阶段标签的勘误。
- [当前文件哈希索引](T6_EVIDENCE_MANIFEST.json)：890份文件的长度与SHA256；旧150普通版索引早于physical_events更新，150暂停版缺少独立旧索引，本次重新冻结当前证据，旧索引不覆盖。
- [证据包身份](T6_EVIDENCE_ARCHIVE.json)：完整本地原始证据包，包含选定run下通过及失败重试、原始UART、四组输入/Golden、BIT/LTX、VIO、ILA、日志、C修复和重建报告。DCP仍为独立可选材料。

GitHub 本次同步报告、机器状态、复核结果、文件索引及C修复身份。完整二进制证据包留在本机，**尚未上传GitHub**，没有把本地路径写成远程下载承诺。路径如下：

`C:\t6fix\acceptance_20261005\T6_EVIDENCE_20261005.zip`

长度：206,066,607 字节；SHA256 `54a00085a31d641e5aadecd22b97742ab2119ee9baf806cfe05752cb73c19949`。

原始文件仍分别保存在 `C:\t6fix\runs\20261005_100quick01`、`C:\t6fix\runs\20261005_150fix01`，输入/Golden在 `C:\t6c\data`。主工作区既有修改、原可用镜像和失败证据均保留。
