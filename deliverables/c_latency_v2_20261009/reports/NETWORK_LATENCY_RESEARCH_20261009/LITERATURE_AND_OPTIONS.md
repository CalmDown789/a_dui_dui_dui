# UDP反馈、批处理与离线上板差距：资料与解决方案

检索日期：2026-10-09。资料来自RFC、Microsoft官方文档、Linux官方源码、USENIX论文及其作者项目。本文提出待验证方案；未运行新的上板实验、修改产品代码或网卡设置。

## 判断与证据边界

目前最符合数据的解释是：16包输入窗口受到真实反馈延迟限制，主机收包批处理改变补发节奏；解码及诊断优化减少的CPU工作有部分被等待吸收。不能把1.2 ms主机观察间隔直接认定为网卡RTT或USB聚合定时器，也不能把离线上板差值认定为CNN耗时。

本项目三轮交错对照的阶段均值：输入44.403→46.740 ms，输出及验证31.368→29.129 ms，整帧79.163→79.418 ms。第4步同口径离线与上板整帧中位数分别50.775和78.931 ms；输入分别13.385和46.207 ms。原始日志中整合方案输入ACK观察间隔中位数约1.202 ms，每帧约31次超过0.25 ms的ACK间隔。日志时间在发送调用前、接收调用返回后，包含主机队列和调度。

证据：[整合结果](C:/Users/Administrator/WorkBuddy/srtp/output/INTEGRATED_STEPS01_04_20261009/SUMMARY.json)、[离线上板对照](C:/Users/Administrator/WorkBuddy/srtp/output/STEP04_BOARD_EFFECT_20261009/SUMMARY.json)。离线Peer在调用线程内生成ACK，COMMIT后直接发送预先准备的Golden，没有真实CNN、USB或Windows网络等待。

## 直接相关的资料

### 窗口与反馈延迟

[RFC 6349，Framework for TCP Throughput Testing，2011，§3.3.1](https://www.rfc-editor.org/rfc/rfc6349.html#section-3.3.1)给出带宽时延积和接收窗口关系。本文讨论TCP；将其应用到EVF1是基于两者都通过ACK释放在途窗口的工程类比，不能把TCP拥塞控制结论直接搬入EVF1。

近似关系：有效吞吐上限≈在途字节数/有效反馈周期。当前16×1024字节、1.2 ms约对应109 Mbps，传518400字节约38 ms，尚未计入控制和处理成本。这与输入约46 ms处于相同量级。若要在1.2 ms反馈下维持1 Gbps，在途容量约150000字节，即约147个1024字节包；这只是容量量级，不能据此承诺满速。

### ACK集中到达和突发发送

[RFC 3449，TCP Performance Implications of Network Path Asymmetry，2002，§3.3、§4.6](https://www.rfc-editor.org/rfc/rfc3449.html)讨论ACK在时间上集中后引发发送突发，以及发送节奏控制。当前日志中16个ACK成批被读入，与反馈集中这一机制相似；日志不足以证明RFC所描述的网络排队原因发生在这里，因为应用批读本身也会改变记录节奏。

启示：保留连续进度校验，及时释放窗口；扩窗时应同时控制突发大小并检查板端吸收能力。不能盲目减少ACK频率，它可能延长小窗口停顿。

### 网卡中断合并与USB聚合

[Microsoft：Network Adapter Performance Tuning](https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics)明确指出，低延迟场景可以测试关闭中断合并，但代价是更多CPU工作。适配器是否提供配置项取决于驱动，指南不是所有设备都可执行的配置清单。

[Linux官方r8152驱动源码](https://github.com/torvalds/linux/blob/master/drivers/net/usb/r8152.c)包含`r8153_set_rx_early_timeout`、`USB_RX_EARLY_TIMEOUT`、`USB_RX_EXTRA_AGGR_TMR`以及`rtl8152_get_coalesce/set_coalesce`。这是RTL8153家族存在USB接收聚合计时机制的直接代码证据；不是当前Windows驱动采用同样参数或产生1.2 ms延迟的证据。Linux与Windows也不能使用同一套调参命令。

可行对照：同一BIT、同一主机程序，借用板载/PCIe网口；或使用Linux环境读取驱动支持的coalescing参数并做单因素试验。没有必要先购买新设备或移植完整网络栈。

### 自适应批处理

[IX，OSDI 2014论文，§3与§6](https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-belay.pdf)采用有界、自适应批处理，并把接收、协议和发送阶段衔接起来；其设计不为了凑满批次等待新请求，并限制批次大小以避免发送队列饥饿。[作者GitHub项目](https://github.com/ix-project/ix)公开了实现。

对本项目的借鉴是“缩短反馈处理路径、按阶段调整批量”，不是把IX部署到Windows/USB网卡上。当前200 µs参数是处理批次的预算上限，不是固定等待200 µs，也不会等到凑满32包才返回。它仍先捕获和记录一批报文，再把控制报文交给协议处理，因此可能推迟第一份ACK触发补发。

建议独立测试输入批量1/4/8/32，输出维持32；再测试25/50/200 µs预算。这些是实验点，不是论文推荐的通用最优值。应用完整校验、原始日志和超时保障均保留。

### 在Windows上定位

[Microsoft Pktmon文档](https://learn.microsoft.com/en-us/windows-server/networking/technologies/pktmon/pktmon-syntax)提供网络栈多个组件处的包捕获和丢包诊断；[Microsoft MsQuic GitHub性能排查文档](https://github.com/microsoft/msquic/blob/main/docs/TroubleshootingGuide.md)介绍WPR/WPA CPU分析，以及通过TCPIP事件确认URO实际工作的方法。

将应用日志与Pktmon/ETW按帧号、序号关联，可以区分驱动向栈交付后到应用读取的等待。NDIS/Pktmon时间戳不是PHY线缆时间，无法独立分解USB内部等待；必要时增加外部抓包或FPGA收到DATA、完成写入、提交ACK的周期计数。各端时钟不能未经校准直接相减，板内周期差可以独立计算。

## 当前机器的只读核对

- Windows 11，build 26300；Realtek USB GbE Family Controller，VID_0BDA/PID_8153，链路1 Gbps。
- 驱动报告版本11.19.20.602、日期2018-03-30；日期是驱动元数据，本文未核实该版本的新旧或可用更新。
- EEE、Advanced EEE、Green Ethernet、Idle Power Saving、Adaptive Link Speed均已关闭。
- 此驱动高级属性没有暴露Interrupt Moderation配置项。
- Receive URBs=6、Transmit URBs=3，接收缓冲区显示16、发送缓冲区显示18；这些驱动数值不等于EVF1的16包应用窗口，也不能未经文档确认解释为字节或包数。
- TCP相关RSC属性开启。传统RSC主要处理TCP，不能直接据此判断UDP被合并：[Microsoft RSC文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/overview-of-receive-segment-coalescing)。
- `netsh int udp show global`报告Receive Offload State和Send Offload State均enabled。这只是全局允许，不证明这条流实际卸载。Windows 11 24H2开始支持硬件URO：[Microsoft URO文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/udp-rsc-offload)。实际路径需跟踪确认。

因此，优先再关节能、盲目关全部卸载、套用TCP_NODELAY/Nagle或TCP自动窗口调整都缺少针对性。UDP校验和卸载不宜仅因怀疑延迟而一并关闭；修改后是否更快必须通过对照判断。

## 建议的验证顺序

| 顺序 | 试验 | 固定项 | 需要回答的问题 |
| --- | --- | --- | --- |
| 1 | timeout/nonblocking × full/sampled四组 | 同一新BIT、输入16、输出128、同数据与日志 | 输入增加来自IO调度还是计时策略？ |
| 2 | 输入接收批量1/4/8/32；再改变处理预算 | 输出批量、BIT、协议不变 | 提前处理ACK是否恢复补发流水？ |
| 3 | Pktmon/ETW与应用日志对照；有条件时借用板载网口 | 主机程序与BIT不变 | 约1 ms反馈等待主要在哪一段？ |
| 4 | 评估输入窗口32/64/128、累计确认和发送节奏 | 先证明板端容量与吞吐 | 在途量能否覆盖反馈周期，而不引发溢出和重传？ |
| 5 | 帧缓冲与跨帧流水 | 以已定位的瓶颈为依据 | 能否让输入、计算、输出重叠，以提高持续帧率？ |

前两组主机参数试验无需新BIT。当前LAB命令行已有io/timing参数；批次参数目前在StreamingClient API中，需要独立实验驱动或新的候选入口，不能假装已有CLI选项。每种模式分多轮交错运行，累计至少64帧，报告均值、中位数、p95、输入ACK分布、重传、重复包及Golden审计；首次帧和后续帧分别呈现。捕获工具也会增加开销，应同时保留不捕获的性能对照。

第4组不能只修改主机窗口限制。板端输入控制有两块包RAM和有界队列，下游还有提交缓冲与响应串行器；在扩大窗口前应核实全链路可用容量、处理速度、接收背压及突发行为。必要时配套更深FIFO、累计ACK、窗口/信用协商和节奏控制，并复测丢包、乱序、重复与进度伪造。累计ACK只代表已完成CRC和连续写入的真实进度。

## 预期收益边界

下面仅是输入窗口反馈模型的敏感性，不是上板预测。计算式为518400/(窗口包数×1024)×反馈周期，忽略线速、处理、控制、重传和不同包反馈差异。

| 在途窗口 | 假设反馈周期 | 反馈约束下的输入时间量级 |
| --- | --- | --- |
| 16包 | 1.2 ms | 38.0 ms |
| 16包 | 0.6 ms | 19.0 ms |
| 16包 | 0.3 ms | 9.5 ms |
| 32包 | 1.2 ms | 19.0 ms |
| 64包 | 1.2 ms | 9.5 ms |

如果反馈链路确实是主因，降低反馈延迟或增加有效在途量具有十几毫秒级收益空间；输入批次微调通常应先作为恢复流水和确认原因的手段，不能承诺十几毫秒收益。

当前输出及验证约29 ms，COMMIT与释放合计约3.5 ms。即使把输入降到10 ms，逐帧流程仍约42.5 ms。达到30 fps还需要降低输出耗时或跨帧重叠；跨帧重叠提高吞吐，并不自动降低单帧完成延迟。不能把优化输入等同于已实现30 fps。

下一步最合理的是同一新BIT上的四组IO/计时对照，再做输入批次对照；同时用驱动/应用跟踪确定反馈位置，然后决定是否值得扩窗或更换收发接口。
