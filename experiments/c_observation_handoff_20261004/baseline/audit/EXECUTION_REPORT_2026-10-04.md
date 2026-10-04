# C 侧 Vivado 2025.2 执行结果（2026-10-04）

工作区：`C:\Users\Administrator\WorkBuddy\srtp\_c2025_2_validation_20261004_02`。工具为 Vivado/XSim 2025.2（SW Build 6299465），B 来源固定为 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`。冻结输入校验通过。原 C checkout 与其既有暂存/未提交改动未被本次操作触碰；所有新文件均在隔离验证工作区。

## 已完成

| 阶段 | 结果 | 关键值与证据 |
|---|---|---|
| 2025.2 bank16 探测 | PASS | `sim/bank16_v2025_2_probe01/result.json` |
| 真实 B 短多帧回归 | PASS，54.324 s | `sim/multiframe_attempt01/result.json` |
| 完整双帧回归 | PASS，3398.97 s | `sim/fullframe_attempt02/result.json`；两帧各 518,400 输入字节、2,073,600 输出字节，Golden 全字节一致 |
| 完整双帧 attempt01 | 主机 900 s 超时，保留 | `sim/fullframe_attempt01/result.json`、完整日志和部分帧输出；不是功能断言失败 |
| 100 MHz 综合/实现 | 命令完成 | B 真五层自检：`b_core_real=1`、stub=0、layer=5；布线 WNS +0.517 ns、WHS +0.014 ns、TNS/THS=0、route errors=0。详见 `audit/build100_execution.json` 与 `runs/multiframe_board100_attempt01/reports/` |
| 150 MHz 综合/实现 | 命令完成 | 真五层自检通过；此实现 WNS +0.139 ns、WHS +0.036 ns、TNS/THS=0、route errors=0。详见 `audit/build150_execution.json` 与 `runs/multiframe_board150_attempt01/reports/` |
| 150 MHz +0.300 ns 路由压力 | PASS | 压力约束报告 WNS +0.100 ns；恢复正式约束后的 WNS +0.400 ns、WHS +0.036 ns，76,800/76,800 可布线网络完整、route errors=0。详见 `audit/route150_execution.json` 和 `runs/multiframe_board150_route_pressure01/reports/` |
| 100 MHz bitgen 门控 | PASS | WNS +0.517 ns、WHS +0.014 ns、WPWS +3.870 ns，TNS/THS/TPWS=0，76,738/76,738 完整布线，DRC 0 Error；bit SHA `524f72bc8ca01388f7305dbb02c48d5f1c68e1abe51900ce6c3738e667b80c3c`。详见 `audit/gate100_execution.json` |
| 150 MHz bitgen 门控 | PASS | 正式约束 WNS +0.400 ns、WHS +0.036 ns、WPWS +2.203 ns，TNS/THS/TPWS=0，76,800/76,800 完整布线，DRC 0 Error；bit SHA `93dd60cffbefa43f6ab9f49697ff1d3f1ab6657445d01552c88842b6bc0760f6`。详见 `audit/gate150_execution.json` |
| 100 MHz 板测 | 四帧 PASS_BIT_EXACT | frame_id 0–3 连续，每帧 2,073,600 输出字节，全部匹配 Golden；主机总耗时 113.742 s。`board/100_attempt01/programming.json`、`board/100_attempt01/capture/session.json` |
| 150 MHz 板测 | 四帧 PASS_BIT_EXACT | frame_id 0–3 连续，每帧 2,073,600 输出字节，全部匹配 Golden；主机总耗时 113.684 s。`board/150_attempt01/programming.json`、`board/150_attempt01/capture/session.json` |
| 150 MHz 连续帧 | 16 帧 PASS_BIT_EXACT | 单次配置后 frame_id 0–15 连续、每帧 Golden 精确匹配、无中途复位；总主机耗时 453.929 s。`board/150_attempt02/input_sequence.json`、`board/150_attempt02/capture/session.json` |

板测计时是主机写入/串口回读耗时，不作为 CNN 计算周期或 FPS。

## 保留的异常与解释

`invoke_vivado_stage.ps1` 是冻结文件，build 阶段把整帧 PASS 固定写死为 `fullframe_attempt01`。attempt01 因主机等待上限超时，而有效的 2025.2 PASS 在 attempt02；脚本因此在 Vivado 启动前拒绝。拒绝证据见 `audit/build100_wrapper_preflight_rejection.json`。没有改门控脚本、RTL、TB、Golden、XDC 或门槛；build100/build150 使用原封不动的冻结 Tcl 与同一参数，在独立审计记录中手动核实 attempt02 PASS 后执行。

两个后布线 DRC 报告各有 1,141 项 Warning：CHECK-3 1、DPIP-1 708、DPOP-1 20、DPOP-2 384、REQP-1839 20、REQP-1840 8；门控要求 DRC Error 为 0，实际两档 bitgen 都为 0 Error。REQP-1839/1840 提示异步复位相关 BRAM 控制信号未由默认静态时序分析覆盖、复位期间可能影响存储器读写。它们没有被改级别或隐藏；四帧和 16 帧会话证明当前配置后一段连续运行正确，但冷启动与按钮复位还需单独取证。

JTAG 只读探测及两档镜像烧录均记录在各自日志。审计脚本两次后处理曾误读 Tcl 回显/路径斜杠而将成功动作临时标为失败；原记录保存在 `audit/board_identity_probe01_parser_error.json` 和 `board/100_attempt01/programming_parser_error.json`，修正后的最终状态与成功日志、bit SHA 一致。没有因此重复烧录或丢弃证据。

## 尚待完成

冷上电和物理按钮复位需要真实物理操作，当前没有这两项的独立证据；200 MHz 按既定范围不阻塞当前交付，本轮未运行。最终汇总数据见 `audit/FINAL_STATUS_2026-10-04.json`。

## 冷上电恢复补充（2026-10-04）

用户报告“我已重新上电”。物理断电区间未由软件独立观测；记录见 `board/150_coldpower_attempt01/physical_event.json`。板卡 cable、part、IDCODE 和 CH9102 COM3 与既有记录一致；150 MHz bit SHA 与 gate150 完全一致。在重新上电后通过 JTAG 重新配置同一已门控镜像，四帧 frame_id 0–3 均为 2,073,600 输出字节、0 mismatch，与固定 Golden/参考逐字节一致。

本次结果是 `PASS_POWER_CYCLE_JTAG_RECOVERY_FOUR_FRAME_BIT_EXACT`，证据见 `board/150_coldpower_attempt01/result.json`、`programming.json`、`program_console.txt`、`capture/session.json` 和四帧原始输出。覆盖范围为用户报告的冷上电后 JTAG 配置恢复，不是 Flash 自主启动；REQP-1839/1840 警告不因这次运行通过而被清除。

四帧采集已退出，串口在采集脚本 finally 中关闭并释放。当前镜像保持配置，下一步仅按 S0 做按钮复位后开新会话；不能重新配置镜像来代替按钮复位。以上替代先前“冷上电没有独立会话”的状态，按钮复位仍待完成。

## S0 按钮复位恢复补充（2026-10-04）

用户报告“已经按下并松开”。在前一冷上电恢复四帧完成后，保持同一 150 MHz 配置，仅进行 S0 空闲按钮复位；本次 runner 不含任何重新烧录操作。新会话 frame_id 0–3 全部通过固定 Golden/参考逐字节对比，每帧输入 518,400 字节、输出 2,073,600 字节、mismatch=0，主机会话总耗时 113.806587 s。结果 `PASS_IDLE_S0_RESET_RECOVERY_FOUR_FRAME_BIT_EXACT`，详见 `board/150_buttonreset_attempt01/result.json`、`physical_event.json`、`capture_console.txt`、`capture/session.json` 与四帧原始输出。采集正常退出并释放串口。

截至此补充，两项计划内物理操作均有独立证据，不再处于“等待用户按键/上电”的状态。复位警告评估见 `audit/RESET_WARNING_REVIEW_2026-10-04.md`：操作恢复通过不等于 BRAM 异步复位结构风险关闭。另发现现有 DRC 报告的 REQP-1839 达到 20 条报告上限，因此不能把打印数量视为完整违规清单；警告分类还涉及 C 条带缓存和 C→B 输入握手驱动的 B 第一层窗口 RAM，不能直接归责于 B 内部。

按固定 B 云端交接文档，还需明确板上握手、stripe/frame sideband 和 proto/overflow 错误计数的真实观测来源；当前 UART 会话记录不含这些内部计数，不能以输出逐字节一致替代计数取证。没有修改 RTL、XDC 或验收口径来填充该缺口。200 MHz 不阻塞；忙时复位、Flash 自动启动等更广范围未测试。当前剩余状态以本补充和更新后的 FINAL_STATUS 为准。
