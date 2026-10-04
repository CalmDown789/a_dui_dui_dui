# C 侧复位告警与操作恢复证据评估（2026-10-04）

范围：固定 B 提交 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`、当前冻结 C 多帧工程、Vivado 2025.2。此次只读取现有源码与报告、补充实际板测证据；未改 RTL、TB、XDC、Golden、DRC 严重级别或验收条件。

## 对照固定云端交接标准

`b_reference/docs/MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md:123` 要求检查复位释放、MMCM locked 和 RAM 控制告警，不能因对拍成功忽略 REQP-1840。该文档第 227 行还要求把冷启动/复位恢复与不复位连续帧分开，并记录板上握手和 sideband 的实际来源。

当前分类为：功能恢复测试通过；复位结构风险尚未闭环。这两个状态独立登记。

## 已有操作证据

| 会话 | 物理动作与配置关系 | 结果 | 证据 |
|---|---|---|---|
| 150 MHz 冷上电恢复 | 用户报告重新上电，随后 JTAG 配置已门控镜像 | 四帧 0–3 全部逐字节一致 | `board/150_coldpower_attempt01/result.json`、`physical_event.json`、`programming.json`、`capture/session.json` |
| 150 MHz S0 空闲复位恢复 | 用户报告按下并松开 S0；沿用上一会话的配置，采集 runner 不含烧录命令 | 四帧重新从 0–3 正常运行，全部逐字节一致 | `board/150_buttonreset_attempt01/result.json`、`physical_event.json`、`capture/session.json` |
| 150 MHz 无复位连续运行 | 先前独立的单次配置连续 16 帧会话 | 0–15 全部逐字节一致 | `board/150_attempt02/capture/session.json` |

物理按钮保持时间与断电区间来自用户操作报告，软件没有独立测量。配置来源通过先前烧录记录和本地 bit SHA 关联，没有对 FPGA 配置做读回哈希。冷上电恢复测试不覆盖 Flash 自动装载；S0 测试只覆盖会话结束后的空闲复位，不覆盖忙时中断、接点抖动穷举、多次/长时间复位或复位时序结构签核。

## 告警定位与影响范围

依据 `runs/multiframe_board150_bitgen01/drc.rpt`，原始报告显示 DRC Error=0 的门控已通过，但仍保留异步 BRAM 控制警告：

| 项目 | 报告定位 | 依赖与影响 |
|---|---|---|
| REQP-1839 | 报告列出 20 条；`u_multiframe/u_core/u_pp/u_bank0/mem_reg_bram_0/ADDRARDADDR` 由异步复位的 `wr_cnt_q_reg` 驱动 | C 条带 ping-pong 输出缓存；相关源码 `overlay/multiframe/rtl/pingpong_buffer.v:95`、`:143`、`:146` |
| REQP-1840 | 报告列出 8 条；B 第一层窗口 RAM 的 ENARDEN 等控制由 `u_multiframe/u_core/c2b_count_q_reg` 的组合逻辑驱动 | C→B 接口有效握手与 B 第一层窗口存储边界；相关 C 源码 `overlay/multiframe/rtl/c_core.v:110`、`:115`、`:120`、`:122`。不能把这些告警全部归为 B 内部问题 |
| CHECK-3 | REQP-1839 达到单规则报告上限 20 条 | 现有 20 条不是完整风险清单的证明；进一步结构签核需完整枚举，不能假定只涉及当前已打印的 bank0 |

报告明确指出：驱动 RAM 控制引脚的异步复位寄存器可能在复位断言时导致存储内容/读值异常，默认静态时序分析不覆盖该行为。因此，正 WNS 和零 DRC Error 均不能独立证明此类风险已消失。

板级顶层启用 MMCM（`overlay/multiframe/rtl/c_multiframe_synth_top.v:36`），S0 同时进入 MMCM RST（`c_multiframe_top.v:67`）；核心复位为 `rst_n & mmcm_locked`（`:77`）。在这条顶层逻辑中没有看到单独的同步释放级。结合 `overlay/multiframe/constr/c_top.xdc:17` 对外部异步复位的 false-path，仅能确认当前约束处理方式，不能由此推导复位/locked 相对于核心时钟释放的安全性。

## 当前结论与剩余证据

1. 两项实体操作已有独立会话，均通过固定数据逐字节比较；连续 16 帧证据保持独立，原失败/超时记录保留。
2. 复位告警评估已经记录，结构闭环状态仍为 `OPEN_RESET_STRUCTURE_DISPOSITION_REQUIRED`。当前未确认板上复位导致的错误，也没有依据将告警登记为已解决。
3. 若要完成更广的云端板级验收，还需明确板上 `start/busy/done`、最后握手、stripe/frame sideband、proto/overflow 错误计数的实际观测来源。UART 输出长度、主机帧号和 Golden 一致不能充当这些内部计数的测量值；当前 capture JSON 没有这些板内计数。
4. 下一步先由负责 C 控制与 C→B 接口的工程负责人依据完整 RAM 控制/复位网络作书面处置，并确定能否用现有已验证观测通路补齐 sideband。若最终需要改 RTL 或增加调试观测，必须另立候选与来源 manifest，按固定标准重走受影响的功能、时序和板测门控；不得直接修改当前已验证 baseline。
5. 本次不主动优化代码，不扩大为 200 MHz 工作，不进行 Flash 写入，也不隐藏或改级别任何告警。
