# C → B：PC4K 延迟与吞吐优化交付

交付日期：2026-10-09。当前工作已经停止，本次只整理既有证据和离线分析，没有再次上板或修改通信/RTL 功能。B 接手的起点是**已消除正常路径重复输出、PC4K 150 帧正确完成、实际 12.381 fps 的新候选**。下一任务是定位并降低剩余时延，推动整机实际吞吐达到 30 fps，同时保留数据正确性、证明 ACK 和最终帧释放机制。

## 1. 先读与接手版本

建议阅读顺序：本文件 → `analysis/PC4K_LATENCY.json` → `evidence/duplicate_fix/PC4K_SHORT_TEST.md` → 最新 PC4K `RESULTS.json`、`AUDIT.json`、`TIMING_DIAGNOSTICS.json` → 源码。ZIP 内相对路径以解压根目录为基准。

| 内容 | 交付位置 |
|---|---|
| 当前配对主包，含 RTL、BIT、DCP、约束、模型、16 组输入/Golden、主机与 LAB 入口 | `runtime/main/` |
| 当前配对 PC4K 补包，含后处理和监督入口 | `runtime/pc4k/` |
| 最新 150 帧完整 PC4K 原始记录、启动、审计、事件和末帧实际 4K | `evidence/20261009/pc4k/attempts/Run_short_once_20261009/` |
| 同日旧版 PC4K 失败基线及完整保存的原始前缀 | `evidence/20261009/baseline_pc4k/attempts/` |
| 同日新旧主包 Smoke/Probe/Natural2/Natural16 与各自真实启动 | `evidence/20261009/main/attempts/`、`evidence/20261009/baseline_main/attempts/` |
| 包龄修复源、原版源、定向/完整报文仿真、修复脚本与验证说明 | `evidence/duplicate_fix/` |
| 新候选构建过程，包括失败尝试日志、最终时序及 Tcl | `evidence/builds/` |
| 历史失败分析、ACK/服务间隔分析、此前修复背景 | `history/` |
| 新增可复算的离线时延分析与逐帧结果 | `analysis/` |
| 交付中每个文件的原始来源、大小与 SHA-256 | `DELIVERY_MANIFEST.json` |
| 未收入 ZIP 的历史大抓包/重复构建中间件清单与原位置 | `EXTERNAL_ARCHIVE_INDEX.json` |

仅 `runtime/main` 与 `runtime/pc4k` 是本次接手配对。历史目录中的旧交接消息、任务指令与路径用于追溯，不能作为重新执行旧任务的指令。

| 身份 | SHA-256 |
|---|---|
| 新 BIT，`runtime/main/image/COMM_window128_150_lab_candidate.bit` | `81377cedf56706a2de904344a8684bdaffcd1e46f3ffa8e65da6a5e1ff584c0e` |
| 新 routed DCP，`runtime/main/implementation/physical_routed.dcp` | `18444d98ed1538ea9dbc1d316e29805c4f9943ad14bd3a31eca7da09604752ee` |
| 修复后 `rtl/evf2_result_window.sv` | `86932586c1f71f0e0713643a8b58bf42a2f6f62e25acfbfb43ed95ec7118c8cc` |
| 修复前同文件 | `60ace8d2a0a33265a6ad07aabd60388ab0fe4e03c9cd5a8569959545dcde2b28` |
| 当前主包 PACKAGE_MANIFEST | `4870f3ea9aca185fcdeebb9bf0074a715559a3b488dfad1152d3fbc4e1393de8` |
| 当前 STREAMING_SELECTION | `0a4bdeab96fefb2512fa20d34d1caf6817b8f1f4bac4f5b064a34b8c1158a645` |
| 当前 PC4K SUPPLEMENT_MANIFEST | `6c8edf91e8599e13b574443558225c8edbf8399dbe4ab110cfa128f502098cd4` |

源码身份：`C_DUPLICATE_AGE20MS_WINDOW128_20261009_86932586c1f71f0e`。150 MHz、pause=0、输出窗口 128、输入窗口 16、证明 ACK 合批 32、ACK 最长等待配置 1 ms。最新测试为 `opencv-f64`，不能写成 CUDA 测试。

**历史状态字段说明：**源码清单中的 NOT_BOARD_TESTED、构建回执中的 NOT_BOARD_TESTED、包清单中的 BOARD_COMPARISON_PENDING 是形成文件时的状态，保持原字节以保留配对哈希。最新实板结论以本文件和后续实测/独立审计为准。`runtime/main/implementation/RECEIPT.json`、`SAVED_DIGITAL_AUDIT.json` 等沿用父包的回执不能单独证明新候选；新构建依据是 `evidence/20261009/BUILD_RECEIPT.json`、`evidence/builds/build_20261009T110342/` 和 `runtime/main/image/DIGITAL_CHARACTERIZATION_REVIEW.json`。

## 2. 已完成的修复与结果

此前先后修复主机跨帧陈旧 ACK 定时器、合批反馈及 venv worker 监督身份/CPU 采样，仍有约 1 fps 的 PC4K 失败。最近旧候选 30 秒期限内完成 30 帧，其 60,750 个唯一分块对应 1,803,557 个输出报文，其中重复 1,742,807；ACK 合批已达到平均 31.90 条证明/包。这证明仅调整主机批量已不能解决主要问题。

原板端 1 ms 重传配置是全局扫描周期，不是“该包发送后至少等待 1 ms”。定向仿真复现发送结束后仅 2,853 拍（约 19 us）就再次发送。当前只改 `evf2_result_window.sv`：每槽记录完整发送结束时间，包龄满足门限才可重传；优先首次发送；年龄查询寄存；保留 CRC、严格证明批次原子应用、槽位所有权和最终释放。门限 3,000,000 拍，即 20 ms。全局扫描仍存在，恢复可能再多等一个扫描周期；20 ms 是已验证候选值，没有做最优 RTO 选择。定向测试中仅增加包龄和首次发送优先、保持 1 ms 也消除了健康 ACK 场景重复，不能把全部收益归因于把 1 ms 放宽到 20 ms。

7 组定向回归通过，涵盖证明丢失恢复、32 位计时回绕、槽复用/旧证明、整批拒绝。完整输出窗口/控制解析/条带 RAM/序列化仿真两帧通过：4,050 唯一分块、0 重复、4,147,200 Golden 字节零差。这不是重新执行全 B 核 PHY 仿真；未改 B 核的完整仿真沿用父候选记录。

实现阶段增量布局失败，改全量布局；随后接收复位恢复路径 -0.067 ns，仅将 `rr_reg[0:1]` 放回已知位置 `SLICE_X1Y113` 并重布线。逻辑、时钟与时序例外不变。最终 WNS +0.009 ns、WHS +0.050 ns，DRC Error/Critical Warning 为 0。裕量较小，B 改 RTL 后必须重新实现检查，不能继承当前 BIT 的时序结论。

| 同日受控结果 | 旧版 | 当前修复版 |
|---|---:|---:|
| Natural16 重复输出包 | 849,676 | 0 |
| Natural16 Golden 通过帧 | 16/16 | 16/16 |
| Natural16 协议时间 | 14.456 s | 1.244 s |
| Natural16 协议吞吐 | 1.107 fps | 12.861 fps |
| PC4K 实际完成帧 | 31（30 秒期限失败） | 150（完整测量） |
| PC4K 全程实际吞吐 | 1.014 fps | 12.381 fps |

Natural16 约提升 11.62 倍；PC4K 比此前失败基线约快 12.21 倍，但旧版是失败前缀、新版是完整运行，不能写成两轮都完成 150 帧的严格等长对比。

最新 PC4K 仅运行一次实际测量。计划 5 秒×30 fps=150 槽，含排空实际 12.1150851 秒；协议完成、4K 生成和预览提交均 150。独立审计重复包 0、无无效/错误来源、150 帧 Golden 零差、全部最终释放。运行每帧 4K 参考比较零差，离线独立审计复算全部事件哈希及实际保存的末帧 4K raw；其余 149 帧没有保存全部 4K raw。物理面板刷新率未测。`COMPLETE_MEASUREMENT` 和审计 PASS 表示测量完整及数据正确，**整机 30 fps 仍未实现**。

## 3. 剩余时延：最新 150 帧实测

下表中通信阶段是 `StreamingClient.transfer` 的主机调用边界，输入包含 BEGIN 和准备；输出包括接收、协议验证及 Golden 比较；释放包含接收回调/日志检查点/最终确认。

| 阶段 | 中位数 | P95 | 最大值 |
|---|---:|---:|---:|
| 输入 | 47.380 ms | 48.974 ms | 53.691 ms |
| COMMIT 交换 | 1.418 ms | 1.552 ms | 1.779 ms |
| 输出直到验证完成 | 29.466 ms | 30.879 ms | 35.802 ms |
| 最终释放 | 1.676 ms | 1.821 ms | 2.391 ms |
| 单帧整个 transfer | 79.992 ms | 82.396 ms | 91.253 ms |
| 已验证 1080p → 4K 生成 | 28.220 ms | 31.394 ms | 35.672 ms |
| 已验证 1080p → 预览提交 | 38.777 ms | 42.705 ms | 47.036 ms |
| 本帧 BEGIN → 预览提交 | 117.477 ms | 122.936 ms | 136.426 ms |

阶段中位数不可保证相加等于 whole 中位数。PC4K 后处理由 worker 执行、预览由 consumer 提交，与下一帧通信可以重叠，不能将 38.777 ms 直接加到通信周期去预测吞吐。最新输入/输出队列峰值均 1、拒绝与丢弃 0，目前仍首先受通信供帧限制。实际迟到输入槽 149，交付迟到中位 3.488 秒，最大 7.024 秒；这些是相对 30 fps 计划槽的累计落后，不是单帧处理延迟。

### 已经看到的输入 ACK 反馈特征

离线重新读取最新完整 raw：76,050 个输入 DATA 与 76,050 个 DATA ACK，输入重发 0；每帧 507 包。记录级 DATA→ACK 中位 1.326 ms，P95 1.626 ms。输入 ACK 间隔超过 0.5 ms 共 4,684 次，其中 4,537 次（96.9%）观察时主机保留窗口已满 16；每帧长间隔累计中位 30.525 ms。未接 PC4K 的 Natural16 同样出现此形态（495 次中 479 次窗口满，长间隔累计中位 28.628 ms），因此现象不依赖 4K/Tk 才发生。

这些数值来自 `analysis/analyze_latency.py` 与两个结果 JSON，已校验原始 journal 的 SHA-256/记录数及报文 CRC。**TX 记录先于 sendto，RX 记录在 recvfrom 返回后**，故它们不是线端 RTT，不能确定延迟发生在 FPGA ACK 处理、网卡/USB 批量交付、Windows socket 还是主机服务。窗口满是主机累计 ACK 退役模型的推断，不是 FPGA ILA 采样。长间隔累计也不能全部等价为可消除等待。

### 输出还有优化空间，但不能忽视帧间串行

最新首个至最后一个唯一输出的主机观察间隔中位 28.671 ms。按 2,025 包×每包约 1,154 个线端字节（1024 payload、64 应用头、UDP/IP/Ethernet/FCS/前导码/IFG），1 Gbps 单向理想发送时间约 18.69 ms；这不包含 ACK、核心供数、CDC、队列、服务开销和控制，不能当作实测带宽或 B 核计算时间。输入 518,400 字节的净荷理论时间约 4.15 ms，含类似报文开销约 4.67 ms；当前 47 ms 明显不只是净荷线速。

当前 `runtime/main/rtl/ethernet_frame_rx.sv` 保持帧 RUNNING 所有权，下一 BEGIN 在运行/释放前被拒绝；`streaming_client.py:231` 的 transfer 完成输入→COMMIT→输出验证→最终释放后返回；`runtime/pc4k/engine.py:82` 才调用下一帧。**输入与本帧输出在协议流程中相加**。即使把输入降至 5 ms，保留输出 29.466 ms、COMMIT/释放约 3.094 ms，仍约 37.56 ms（约 26.6 fps）。这是预算估算，不是已实现结果。输入优化后必须继续降低输出/控制开销，或设计具备明确存储所有权的跨帧重叠。

## 4. 给 B 的下一步任务与顺序

1. **先加可关联的 ACK 时间证据，定位输入 16 包窗口停顿。** 在板端记录或 ILA 观察：完整有效 DATA 接收、RAM 应用结束、ACK 描述符入队、等待 TX 的时间、ACK 发射结束、RX 队列溢出/丢弃、背压、输入序号与帧 ID。主机对应记录 sendto 开始/返回、recvfrom、验证/处理耗时；若可行对网卡中断合并/USB 批量交付作单因素对比。FPGA 与主机时钟不可直接相减，用同一端的间隔和序号关联。先判定主因，再决定修改位置。
2. **依据证据改输入反馈，优先做小而可验证的改动。** 若板端 ACK 等待/回复串行占主因，考虑缓冲 ACK 描述符、降低控制通道等待、兼容严格序号/CRC的累计 ACK。若主机/网卡交付主导，比较现有网卡参数或原生以太网路径。输入窗口当前软件硬限制 16，不能只把 Python 参数改为 128；扩大需要核对板端 FIFO/背压、累计进度校验、乱序与重试语义。不要删除 CRC 或减弱 Golden 校验换取表面 fps。
3. **定位输出 28.7 ms 与约 18.7 ms 线端预算间的差距。** 区分 B 核产出节奏/条带就绪、条带 RAM 读取、描述符/序列器、包间空隙、证明 ACK 处理/窗口推进、主机单包 CRC/Golden/journal 服务。测串行器空闲周期与窗口缺料/缺 ACK 停顿，再考虑预取或流水；保留包龄门限与首次发送优先，不能重新引入重复洪泛。
4. **若预算仍超过 33.33 ms，评估跨帧输入/输出重叠。** 明确输入双缓冲容量与选择、B 核读写所有权、输出保存窗口、帧 ID/session/CRC、乱序/错误/abort、最终释放归属。先做资源/时序预算与状态机设计；不能只允许 RUNNING 时接受 BEGIN 而覆盖上一帧数据。若继续单帧串行，则必须共同优化输入、输出及控制使总周期满足目标。
5. **通信接近目标后再验证 PC4K 持续吞吐和尾部延迟。** 当前 opencv-f64 4K 生成 P95 31.39 ms、最大 35.67 ms，目标供帧时可能成为下一瓶颈；现有 12 fps 下队列不积压不能证明 30 fps 下也成立。必要时受控比较 CUDA 后端，分别注明实际环境、参考一致性、输入供帧和预览吞吐。不要只换后端就认定解决通信问题。

本任务不预设已经证实 Windows 丢包、GIL 是唯一主因或 FPGA 忽略 ACK。COMMIT 响应/首包间隔包含协议调度，不能当作完整 CNN 时间。必要恢复重传与正常路径重复包分别统计。

## 5. B 回交时需给出的证据

- 独立新候选目录、来源链、代码差异、BIT/RTL/DCP/主包/补包哈希；绑定文件同步更新。保留当前已通过版本作为对照。
- 问题定位证据及优化前后同条件指标：输入/COMMIT/输出/释放、整帧周期、实际 protocol/4K/preview fps、P50/P95/max、迟到槽/队列峰值/丢弃、实际重复包/输入重试/证明恢复。
- 相关仿真与数字实现通过；覆盖丢证明、旧证明/槽复用、计时回绕、整批原子验证、重复最终请求无重复释放，多帧 Golden 零差。
- 新 BIT 的真实临时 JTAG 启动记录、完整原始双向抓包、运行日志、全部事件/manifest、官方独立 raw/Golden/最终释放/4K 参考审计。失败也保留完整原始 attempt，不覆盖、不用失败前缀冒充完整测量。
- 达到 30 fps 的主张必须来自实际完成率；计划 Fps=30、150 offered_slots、COMPLETE 或 150 帧最终完成均不足以单独证明 30 fps。30 fps 稳态应对应约 33.33 ms 帧间周期且无持续累计迟到/丢帧，测量时长与容差另行明确。此前 300 秒只是长测建议，没有新增本任务硬验收阈值。

本交付不要求立即重跑已通过的所有旧步骤；先离线读证据并给出定位计划。上板验证使用 fresh attempt、fresh JTAG/启动记录。不要复用活动会话中旧 startup：主包 Natural16 结束后 DUT 期待下一个 frame_id，新的 PC4K 从 0 开始，必须用新的会话/正确启动过程。

## 6. 本机环境、入口与停止状态

当前原目录：`C:\t6dup09\main`、`C:\t6dup09\pc4k`。建议 B 将 ZIP 解压到短 ASCII 路径，例如 `C:\B_latency09`，其中 `runtime\main` 与 `runtime\pc4k` 保持同一交付配对。复制的历史日志内绝对路径只是采集时记录，不能要求 B 的机器存在原路径。

- Windows / PowerShell；Vivado/XSim 2025.2：`E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat`；器件 `xc7a200tfbg484-2`。
- 系统 Python 3.12：`C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`（有 pyserial）。PC4K venv：`C:\Users\Administrator\WorkBuddy\srtp\comm_c_20261008_pc4k_env\Scripts\python.exe`（numpy/OpenCV/Pillow/Tk；不包含串口库）。依赖规格和原机器硬件/环境快照在 `history/operator/`。
- 网卡：以太网 3，index 10，MAC `00-E0-4C-19-4B-88`，Up/1 Gbps；主机 `192.168.0.3/24:6102`；FPGA `192.168.0.2:5000`；永久邻居 MAC `00-0A-35-01-FE-C0`；串口 COM3 CH9102。
- JTAG：Digilent `250520092545`，目标 `xc7a200t_0`，ID `13636093`。B 应核对自己的实际设备映射。

已有入口（B 后续执行；本次交付没有执行）：

```powershell
# 文件预检：实际 Python/Vivado 按 B 的安装替换。
& 'C:\B_latency09\runtime\main\lab\run_c_streaming.ps1' -Mode Preflight -Python 'C:\Python312\python.exe' -Vivado 'E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat' -OutputWindow 128
& 'C:\B_latency09\runtime\pc4k\run_live4k.ps1' -Mode Preflight -CommPackage 'C:\B_latency09\runtime\main' -Python 'C:\PC4K_env\Scripts\python.exe'

# 离线复算最新 journal 时延；不打开网络或串口。
& 'C:\Python312\python.exe' 'C:\B_latency09\analysis\analyze_latency.py' --journal 'C:\B_latency09\evidence\20261009\pc4k\attempts\Run_short_once_20261009\live\traffic\datagrams.bin' --frames 'C:\B_latency09\evidence\20261009\pc4k\attempts\Run_short_once_20261009\live\traffic\FRAMES.jsonl' --out 'C:\B_latency09\analysis\PC4K_RECHECK.json'
```

新候选的上板入口为主包 `lab/run_c_streaming.ps1 -Mode Run`，PC4K 为补包 `run_live4k.ps1 -Mode RuntimePreflight/Run/Audit/Pack`，用法见包内 README 与 C_QUICKSTART。PC4K 显式配置 `-Seconds 5 -Fps 30 -Backend opencv-f64` 才与最新短测条件一致。正式生产入口的保护/版本认证不应被绕过；修改源码后应重新生成并配对候选身份。

构建与仿真脚本中保留了原机绝对路径/父工程引用；它们是实际执行记录，不承诺在 B 的目录中原样可运行。包内当前 RTL/MEM/约束、最终 routed DCP、新 BIT 及构建 Tcl 已交付，B 应结合自己的工程接入；全量重建要包含前级综合/布局，最后的 `build_20261009T110342/build_duplicate.tcl` 单独只是恢复 routed checkpoint、复位位置修复、重布线和出 BIT。

停止状态：最新测试后的 UDP 6102 无本次监听，Vivado 未运行，本次拥有的 hw_server 已停止；只临时 JTAG、未写 Flash。无正在继续的优化或测试。本文件与 ZIP 是供用户交给 B 的离线交付，不代表已向 B 发送消息。
