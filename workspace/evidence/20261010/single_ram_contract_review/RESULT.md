# B 单输入 RAM 跨帧合同 v1 复核 · 2026-10-10

**判定：本次要求 B 补交的七类材料已在包内对应齐备，包身份和离线复现通过；`0.1.0-draft` 可作为 B/C 联合评审及独立 RTL 候选的输入，尚未成为已实施或板测通过的合同。** 冻结 RTL、BIT/DCP、主机和旧证据没有修改。

收到的 `B_TO_C_SINGLE_RAM_CONTRACT_20261010_v1.zip` SHA256 为 `260871da8610e8a75fced9fd95b3f82a6509307fb07fec61c77c9adbc5dcbc66`，与用户给定值一致。ZIP 53 个成员 CRC 均通过；`MANIFEST.json` 所列 51 个负载文件的长度/SHA256、`SHA256SUMS.txt` 的 52 条记录均通过。单独收到的 `README(1).md` 与 ZIP 内 `README.md` 逐字节相同。原 `SINGLE_RAM_CROSS_FRAME_DESIGN.md` 与上次收到的版本也逐字节相同。

原缺失的 `SOURCE_MAP.json`、`check_ring_invariant.py`、`RING_INVARIANT_MODEL.json` 均已补齐。原环地址脚本在临时目录独立复跑，生成结果 SHA256 与原结果同为 `de3e6fbcdb2344bbdf65641a54f23b4a2d85aa619383367600eac0defd03b4ff`；其 19178 次旧未消费地址检查、1224 个超授予负例现可复核。包内 16 份不同 RTL 快照均与本地冻结 `runtime/main/rtl/` 同名源文件逐字节一致；原 12 份/53 行及补充 7 份/150 行、协议来源映射 5 份/12 行由包内校验器通过。

新增 `CREDIT_PROTOCOL_V0_1.md`、`CONTEXT_TRANSITIONS_V0_1.md`、`START_PROGRESS_V0_1.md` 和 `CONTRACT.json` 明确了 EVF3 信用线格式、HELLO 能力协商与旧版回退、R/W/L 整包预约、attempt/epoch 身份、`PENDING=256` 与真实 `STARTED=2`、ABORT drain、三上下文、FINAL 墓碑、三方同拍 start join、早期控制保留通路及公平仲裁。离线重跑 `model/run_validation.py` 为 **21/21 PASS**，各例实际值与 B 包内 `results/model_v3/RESULTS.json` 逐项一致；字节协议固定向量/回复绑定为 **62 项通过**，模型与线格式交叉检查为 **7 项通过**。复跑产物保存在本候选 `build/`，原包保存在 `results/incoming/`。

**仍需真实实现证明：** 两个独立控制 bank、回复槽及 507 包持久指纹历史的资源容量；共享 RX/CDC 之前的控制分类；已预约 RAM writer 与 ACK/TX 解耦；ABORT 已 issue 写入和跨 CDC token 的排空；B/C/输出窗口真实 ready/accepted 同沿一致；旧 FINAL 退休与新启动优先级；整包公平仲裁和 8192 core-cycle 服务目标。B 文档明确把 8192 拍作为待实现目标，Python 调度步不能证明它。随后还需完整三帧 CNN/网络 Golden、综合实现/CDC/150 MHz 时序、新 BIT 身份及板测。当前 BIT 不支持 EVF3，不能发送新协议作兼容测试，也不能据模型宣称整机 4K30。

下一步先由 B/C 确认同一 `0.1.0-draft` 文本/哈希并冻结实施版；在隔离 RTL 候选中按 `START_PROGRESS_V0_1.md` 的门槛逐层验证。包内的“实施顺序”只作为 B 的提案，本报告未把它当成用户要求执行的操作。
