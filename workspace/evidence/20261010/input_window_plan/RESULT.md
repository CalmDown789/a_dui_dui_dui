# 同 BIT 输入扩窗实板结果 · 2026-10-10

**结论：正常输入扩窗实板验收通过，建议将 input64 / batch1 / output128 作为后续运行候选。** input128 的典型帧中位数更低，但本次均值和实际协议循环吞吐与64相当，P95更长；四轮不足以证明128总体更优。冻结默认未升级。

收件身份、两种PowerShell实际预检、递增筛查、四轮平衡对照、逐case零重复Gate、整体Gate及B/C两套只读统计已完成。20个成功case共360个Natural帧、746,496,000个输出Golden字节零差；正常帧输入/ACK/输出/BEGIN/COMMIT/FINAL零重复。帧外HELLO重试共4次单列，没有放宽重试或正确性门槛。

## 身份与方法

- 主ZIP发行SHA（用户提供，与实际值一致）：`24352a4a4f1acbd6e538ecc37bdabd1ac6696a7954cb9dbb5e754bff53a61db8`。
- BIT：`cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5`；DCP：`47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da`。
- v5 main manifest / selection分别为 `df417110814124283d812b9434bfb853fdd779af71db0f0e53dc6650e6bc9931` / `3d0eb5784f12c32f32ec42dbbfa463d507266188edfd8beff49eaeb7685be2e9`。
- 120份RTL、约束、模型、输入/Golden及image文件与冻结基线逐字节相同；19份MEM；150MHz、pause0、16行条带。来源以 `intake_01/FROZEN_IDENTITY_RECHECK.json` 及最终复核为准。早期收件收据的冻结比较列表因Windows路径分隔符筛选为空，后续独立复核已覆盖全部120份文件，早期原收据保留。
- 所有Natural报告和profile核对：输入batch1、输出窗口128、输出接收batch32、nonblocking、sampled/16。正式实验16窗口也是batch1，不能直接把本表与旧冻结batch32成绩混算。
- 成功筛查4case/72帧独立保存；正式四轮16case/288帧，顺序为16/32/128/64、32/64/16/128、64/128/32/16、128/16/64/32。每窗口Natural2=8帧、Natural16=64帧，独立比较单位为4个round/case。
- C外部编排保存真实入口、参数、退出码、自身SHA与Gate引用，执行原Run→原Pack→原Gate；没有修改B原main、控制器、分析器或门槛工具，也没有冒称B原控制器执行。

## 正式Natural16结果

“中位数”为4个case各自帧中位数的再中位数；均值/P95/最大值为该窗口全部64帧的描述分布。协议fps为64帧除以4个实际LAB protocol_loop总时间，包含帧间主机记录开销，未用单帧中位数倒数代替。

| 输入窗口 | DATA中位数 ms | 整帧中位数 ms | 整帧均值 ms | 帧P95 ms | 最大 ms | 实际协议循环 fps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 42.627 | 76.266 | 76.974 | 78.519 | 87.071 | 12.849 |
| 32 | 22.250 | 55.936 | 56.616 | 57.597 | 67.580 | 17.409 |
| 64 | 12.463 | 46.274 | 46.281 | 47.552 | 56.038 | 21.224 |
| 128 | 11.479 | 45.251 | 46.346 | 54.688 | 57.656 | 21.186 |

相对同round窗口16，32/64/128的配对整帧中位改善幅度分别为26.47% / 39.91% / 40.51%，每个窗口均4/4轮改善，满足执行前建议的基准收益标准。输出验证阶段的中位数仍约29.13–29.15ms，收益主要来自输入等待下降。

64比128典型整帧约慢1.023ms（2.26%），略超计划中“2%接近”建议值；该差异与本次跨轮波动相近，第二轮排名反转，不能据4轮断言128全面胜出。64的实测均值、协议循环fps与128基本相当，P95低7.136ms，因此建议64作为兼顾长尾的操作候选；128保留为典型延迟较低的选项，进一步比较应另做平衡重复。

Natural2独立统计：16/32/64/128整帧中位数分别76.761/56.500/46.409/45.847ms；均值76.957/56.573/46.471/49.433ms；P95/最大值78.072/57.536/47.349/65.059ms。只有每窗口8帧，P95等于最大值，不据此作置信推断。首帧和后续帧分组、各轮配对及全部逐帧数据均在分析JSON/CSV保留。

## 正常门槛与失败记录

每Natural帧原始记录均满足：507个唯一输入DATA TX、507个唯一DATA ACK RX、2025个唯一输出包，BEGIN/COMMIT/FINAL各方向各一次；完整覆盖、CRC/会话/来源/启动身份、完整Golden、已存与fresh独立auditor均通过。所有正常帧重试/duplicate/rejected/raw invalid/wrong source为0；HELLO重试和合法proof覆盖重叠分别描述。

首次 `screening_01` 在窗口16的首个JTAG连接阶段失败，尚未进入Natural或网口测试。Vivado报告cs_server连接失败；外层的自有hw_server记录中executable为null，导致原清理守卫拒绝清理。原Run exit1、Pack exit0，后续case没有执行，失败ZIP、UART/JTAG原始日志及launcher保留。

连接专项probe随后成功，只连接服务、未打开目标或编程；初次cs_server失败具体原因仍未证实。用PID、实际程序路径和启动ticks重新确认第一次启动的hw_server后，新建 `screening_02` 全组重跑，通过后再开始独立正式A/B；没有原地续跑或拼补失败组。成功组复用身份已确认的服务，最终按相同三项身份停止，3121监听已关闭，独立诊断cs_server已退出。

## 控制尾部与诊断边界

四轮128的frame1（第2帧）均出现控制尾部：末输出RX日志至FINAL TX日志约11.573/12.312/10.989/11.165ms；FINAL TX至ACK约1.270/1.336/1.411/1.265ms。这些帧全部Golden和正常零重复通过，长尾没有删除。

受绑定客户端源码确认，输出完整校验后、FINAL发送前包括 `accept_frame` 的frame_events写入/flush和非durable journal checkpoint；现有数据定位的是PC请求前的处理区间，未逐调用测定阻塞原因。不能归因为FPGA计算、USB、NIC或某个驱动。profile中的最终durable checkpoint发生于protocol_loop之后，其长耗时不能分配给某个帧release。

已保存原NIC工具的只读Snapshot、实际网卡/属性与协议统计。Pktmon状态/组件查询记录“无法与PktMon驱动程序通信，拒绝访问”；未启动ETL抓包，未改网卡或驱动，不能给NIC/USB分层归因。若后续需要抓包，应使用可访问驱动的管理员会话、真实component ID和全新的独立诊断attempt，并与无抓包基准分开。

## 证据与交付

- `FINAL_STATUS.json`：独立最终复核，包含身份、计数、参数、失败、尾部和证据SHA。
- `intake_01/`：四份原收件、CRC/SHA、发行SHA补充、冻结身份复核与文档差异。
- `preflight_01/ab/INDEX.json`、`preflight_ps7_01/ab/INDEX.json`：两种实际入口预检/Pack；`preflight_gate_rejection_01/`证明预检不能冒充板测PASS。
- `orchestrator_fixtures_02/RESULTS.json`：当前编排13项显式无硬件停止/来源/参数/完整流程fixture。
- `screening_01/`、`service_diagnosis_01/`：原始失败、连接probe和精确自有服务清理。
- `screening_02/INDEX.json`、`balanced_ab_01/INDEX.json`、逐case Gate和 `full_ab_gate_01/RESULTS.json`：成功筛查与完整正式验收。
- `analysis_B_01/` 与 `analysis_C_02/`：原B分析器与C只读原始时序/实际loop统计；最终复核已逐项对齐共同指标。旧分析版本保留，最新结论以C_02为准。
- 原始attempt及Pack位于 `C:/cwin26_20261010_e1/main/attempts/`；结果交付ZIP收录所有本次成功、失败及两种预检的Pack原件、完整Gate/索引/分析。门槛工具在 `C:/zerogate_20261010_e1/`。

## 限制与下一步

本次确认960×540灰度输入至1920×1080协议/Golden链路，正常零重复范围为PC捕获UDP；不能证明未捕获物理报文或RAM写入次数。物理I/O仍UNVERIFIED。当前同BIT串行协议循环约21.22fps，未达到整机4K30，PC4K、屏幕刷新和长期扩窗512帧均未验收。

下一步：以64/batch1/output128另设长期重复；B复核frame sink/日志控制尾部及原服务启动路径为空问题；新主机修复需独立身份/故障验证后发行。需要30fps时先取得缺失的 `SINGLE_RAM_CROSS_FRAME_DESIGN.md`，评审信用、消费地址和帧所有权后另立RTL候选，不直接删除RUNNING保护。本次不修改冻结默认、不提交或同步GitHub、不发送材料给B。
