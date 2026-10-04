# C 侧复位与 BRAM 告警处置（阶段 3）

日期：2026-10-04。范围固定为 B 提交 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`、冻结 baseline `C:\Users\Administrator\WorkBuddy\srtp\_c2025_2_validation_20261004_02`、Vivado 2025.2。此处完成的是风险调查，不是复位结构签核；当前结论为 `OPEN_RESET_STRUCTURE_DISPOSITION_REQUIRED`。

## DRC 结论与报告上限

使用正式 150 MHz 门控所用 post-route DCP，以及同一 baseline 的 100 MHz post-route DCP，均只读打开；未 route、opt、改写 DCP、生成 bitstream、改变 DRC 严重级别或验收条件。

| 输入网表 | DCP SHA-256 | RAMB18E1 / RAMB36E1 | `REQP-1839` | `REQP-1840` | `CHECK-3` |
|---|---|---|---:|---:|---:|
| 100 MHz | `3d7c623d99e5687d8391b0b93ae374dee8d8f9e8f0f62560c505985fc89ee789` | 8 / 226 | 20 | 8 | 1 |
| 150 MHz | `9b3fe554fc18c33be3cfb9e91bdb5a71765e031aa7d32d47c780716994417fe5` | 8 / 226 | 20 | 8 | 1 |

两份 DRC 都明确包含 `REQP-1839 rule limit reached: 20 violations have been found.`。Vivado 返回的对象为 `CHECK-3=1`、`REQP-1839=20`、`REQP-1840=8`；这不是完整的 `REQP-1839` 违规总数，状态必须保留为 `DRC_REPORT_LIMIT_REMAINS`。检查对象属性为 `MAX_NAMES=0`、`MAX_MESSAGES=-1`。AMD 2025.2 文档说明 `MAX_NAMES` 只影响在单条 DRC 消息中列出的对象名，不代表违规对象数量上限，也不能据此清掉 `CHECK-3`。[AMD Vivado 2025.2 `MAX_NAMES`](https://docs.amd.com/r/2025.2-English/ug912-vivado-properties/MAX_NAMES?contentId=TcV_e7hOWP8YuZwTTEGFGw)

## BRAM 控制扇入调查

在 100 MHz、150 MHz 两个固定 DCP 中，`get_cells -hier` 均找到 234 个 BRAM。逐个查询输入方向的 `ADDR*`、`EN*`、`WE*`、`RST*`、`REGCE*` 控制脚，原始全扇入表分别记录 12,088 个控制脚和 10,806 个 timing-startpoint 行（含无起点记录时单独写 `NONE`）。另外从每个异步控制寄存器的 Q 输出以 Vivado `all_fanout -flat -endpoints_only -trace_arcs timing` 枚举至 BRAM 控制脚的候选路径：两档各 8,596 对寄存器 Q→BRAM 脚路径、5,720 个不同 BRAM 脚、192 个不同 BRAM 实例。候选分布为：

- `u_multiframe/u_core/u_pp/`（C ping-pong）：2,700 对；
- `u_multiframe/u_core/u_b/`（B 核第一层窗口 RAM，控制来源跨 C→B 边界）：8 对；
- `u_multiframe/u_core/u_rom/`：5,888 对。

100 MHz 的网表含 1,179 个 `FDCE/FDPE` 异步清零/置位单元（1,139/40）；150 MHz 含 1,198 个（1,158/40）。候选表只是时序弧扇出调查，不把 8,596 写成官方 DRC 违规数。Vivado 原 DRC 已报告的 28 条 REQP 描述均逐项匹配到相同的异步寄存器与 BRAM 输入脚；未发现无法匹配的已报告项。另一个 `all_fanin -startpoints_only` 表是原始时序图起点导出；单点对照显示它会返回驱动寄存器的 `C` 时钟脚，因此不能单独把该表里的 `FDCE` 单元写成 DRC 数据驱动起点。

当前已打印的 20 条 `REQP-1839` 全部落在 C ping-pong bank0：12 个 `ADDRARDADDR` 输入脚和 8 个 `ADDRBWRADDR` 输入脚，由异步复位的 `wr_cnt_q_reg` / `rd_ptr_q_reg` 驱动。报告上限遮住的其他 bank 或其他候选仍未被完整官方枚举。8 条 `REQP-1840` 则是 B 第一层 `bank_gen[0..3].mem_reg/ENARDEN`，由 C 侧 `c2b_count_q_reg[0/1]` 经 `pad_fire` 控制；责任边界是 C→B 接口，不应全部归到 B 内部。

机器可读计数、每个违反对象、完整 BRAM 控制脚/起点表、异步寄存器时钟/CLR/PRE 网络，以及 8,596 条 Q 扇出候选，分别保存在：

- `audit/reset_ram_inventory.json`；
- `audit/reset100_inventory_attempt01/` 与 `audit/reset150_inventory_attempt01/`；
- `audit/reset100_ram_fanin_timing_attempt01/` 与 `audit/reset150_ram_fanin_timing_attempt02/`。

原始 2025.2 命令、stdout、Vivado log、journal、exit code 与 DCP hash 也保留在这些目录旁。第一次 API 探针、第一次 fanin arc 探针和第一次全 arc 扇出尝试均保留在独立 `attempt01` 文件；它们分别暴露输出路径保护检查、层级 pin lookup 和跨 sequential arc 的探索性过宽问题，没有被当作设计失败或 PASS。修正尝试使用新目录完成。

## RTL 复位关系、帧重写与证据边界

冻结源码中的板级链路为：ACX750 `rst_n`（低有效 S0，D21）送入 `MMCME2_BASE.RST = ~rst_n`；`core_rst_n = rst_n & mmcm_locked`；该信号作为多个 C 子模块的低有效异步复位。当前顶层没有看到独立的同步释放级，因此 `mmcm_locked` 相对核心时钟释放时的时序安全性不能由现有 WNS/WHS 或零 mismatch 推导出来。XDC 对外部 `rst_n` 的 false path 只说明约束范围，不构成复位释放签核。

`uart_frame_loader` 在状态为 `S_PAYLOAD`、header 有效且 UART 收到有效字节时才拉高 `frame_wr_en`；只有输入 payload 长度及 CRC 检查通过，最后一个输入字节收到后才脉冲 `frame_start`。因而新帧开始计算前会完整写入 518,400 字节输入帧。这个事实没有证明 ping-pong RAM 或 B 窗口 RAM 在中断/复位后每个位置均已初始化，也没有证明异步复位期间 RAM 地址/使能的行为安全。

可复用的基线功能证据是：

- 150 MHz 冷上电后由用户操作、再经 JTAG 配置门控镜像，四帧 0–3 逐字节一致；它不等于 Flash 自动启动验证。
- S0 是在先前会话空闲结束后按下并松开，重新收到帧 0–3 且逐字节一致；它不是忙时复位测试，也没有重新烧录。
- 单次配置下连续 16 帧 0–15 逐字节一致；该项没有在帧间复位。

这些功能 PASS 与结构告警 OPEN 是两种不同结论。当前没有 busy-reset、任意复位释放相位、长按/抖动穷举或 Flash 自动加载的板级证据；不能把复位风险写成已消除。

## 当前处置与后续依赖

1. 保留两档的 `REQP-1839/1840` Warning 与 `CHECK-3`；不调整 DRC level、不忽略规则、不借 100 MHz 结果替代 150 MHz。
2. C ping-pong 的读写指针、异步复位时 RAM 地址/EN/WE 和复位期间 write-enable 屏蔽方式仍需结构处置；候选扇入范围已保存。
3. C 的 `c2b_count_q` 到 B 窗口 RAM `ENARDEN` 路径需要 B 确认 `pad_fire` 与 valid/ready、RAM 时钟/EN 的复位语义及可接受的 reset release 时序。执行方未向队友发送消息；需请求的具体问题已列于固定执行指南，后续可由用户转交。
4. `rst_n`、MMCM `LOCKED` 到全部异步 CLR/PRE 的组合释放关系仍是 OPEN。若之后建议改 RTL，应另建候选、明确验收影响并重跑受影响的仿真、实现和板测；本阶段没有改 RTL，也没有主动优化。

**阶段 3 状态：评估产物通过；结构处置仍 OPEN。**
