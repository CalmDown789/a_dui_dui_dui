# 必要历史

| 阶段 | 保留结论 | 原始来源 |
| --- | --- | --- |
| 9 月模型与任务书 | d16/s8/m1/c16、稠密 L5 Conv16→4 + PixelShuffle×2、整数 Golden 与模型交付；任务书 v3.2.2 属于当时修订执行版 | A 仓库、`output/任务书v3.2.2_修订执行版.md`、对应 DOCX |
| 9 月 23 日失败调查 | 旧 2022.2 复现曾失败，排除过程和工具链问题有追溯价值；该失败不能代表后续源树 | 外部清理备份中的旧 `HANDOFF_CODEX.md`、`c_side/docs/` |
| 9 月 24 日 | 100 MHz 单帧 UART / Golden 通过；UART 约 22.43 秒是回传时间 | C 板测专项报告 |
| 9 月 26 日 | B 的 150/200 MHz 实验与 C 的板测不是同一验证层级 | `PROJECT_STATUS_SYNC_2026-10-03.md`，属于历史快照 |
| 10 月 8 日 | 流式通信、ACK 服务间隔与 PC4K 截止失败调查，原始失败证据保持 | `comm_c_20261008_operator/` 与相应 attempts |
| 10 月 9 日 | 四步整合新 BIT 及 512 帧实验成为当前延迟优化交接基线 | `output/C_TO_B_LATENCY_HANDOFF_V2_20261009/` |
| 10 月 10 日 | 同BIT输入扩窗360帧正常零重复/Golden通过；四轮对照64窗口约21.224fps，建议64/batch1/output128候选，128典型帧更快但长尾较大；首次JTAG失败与服务恢复保留，冻结默认未变 | `candidates/20261010_input_window_plan/results/RESULT.md`、`FINAL_STATUS.json` |
| 10 月 10 日后续中间快照 | 当时长测为320 Natural16 + 40 Natural2；两次主机启动/Smoke审计停滞均保留，后一次捕获SyncDisk注入与挂起线程的临界区阻塞。该行记录中间状态，后续完成情况见下一行 | `candidates/20261010_input64_followup/results/partial_review_01/RESULTS.json`、`recovery_stall_01/` |
| 10 月 10 日后续完成 | 32个完整Run共512 Natural16 + 64 Natural2零Golden差；当前BIT的150帧PC4K配对约20.536fps；轻量GC样本未复现12.3267ms长尾且未见间隔内GC，长尾根因仍未定。保留2次主机失败、1次用户中断；跨帧正式评审待B设计原文 | `candidates/20261010_input64_followup/results/RESULT.md`、`FINAL_STATUS.json`、`GC_LIGHT_REVIEW.json`、证据包SHA收据 |
| 10 月 10 日跨帧设计评审 | B单RAM设计原文到达；C核对12个RTL源与当前BIT/DCP，并独立验证消费信用地址不变量。结构可行性有条件通过；信用线格式、待启动COMMIT、启动握手和原B模型附件未闭合，未实现/上板 | `candidates/20261010_single_ram_cross_frame_review/results/RESULT.md`、`REVIEW_STATUS.json`、`C_RING_GEOMETRY_MODEL.json` |
| 10 月 10 日跨帧合同补交复核 | B补齐原三份附件、EVF3信用协议、上下文与启动/进展合同、离线模型；C复跑原脚本、21项控制模型、62项线协议、7项交叉检查并核对16份冻结RTL快照。草案可供同版评审，未实施RTL/新BIT/板测 | `candidates/20261010_single_ram_contract_review/results/RESULT.md`、原包SHA256 `260871da8610e8a75fced9fd95b3f82a6509307fb07fec61c77c9adbc5dcbc66` |
| 10 月 10 日跨帧 RTL 第一阶段 | 在隔离候选实现 ROM 物理基址/逻辑计数与真实 B 消费信用/整包预约/实际写指针；分别综合成功，读流小尺寸 XSim 干净通过；信用测试有 PASS 输出但 XSim elaboration 访问异常，未作干净签核。未集成、未出新 BIT 或上板 | `candidates/20261010_single_ram_rtl_phase1/results/RESULT.md`、`PHASE1_STATUS.json`、证据 ZIP SHA256 `d7e404ad92054f196a7d85725944b2bd2cfc0dce52e2888348ea450ec735d1b5` |

10 月 10 日跨帧系统候选及 B 实施补充：C 候选已有 GMII/三上下文/TX 接入和定向仿真；最新版综合包装器因目录错误失败、post-place WNS −2.898 ns，P&R 被用户停止，未出新 BIT。拟由 B 完成实现/时序，C 提供已有四窗口板测、条件性 I/O 和候选差异。冻结交接版/B main逐文件一致；物理 I/O仍UNVERIFIED。本轮仅整理材料，未运行硬件/Vivado。入口为 `candidates/20261010_b_implementation_support/results/RESULT.md`；补充 ZIP SHA256 `dcfabce1b7a3cc28387fe56e43c2b27e7e4d5d2e6ca69680117340cbec3a7fc6`；原始 RTL/日志在 `20261010_single_ram_rtl_integration/`。

10 月 11 日用户澄清与状态同步：跨帧方案尚未正式交付；10 月 10 日单 RAM 设计/合同草案、离线模型与已停止 C RTL 实验作为历史评审证据保留，不能冒充正式方案完成。当前主线等待正式方案，已有约 20–21 fps 正确链路与 150 槽 PC4K 结果保留；更新计划入口和维护分支，不合并 main 或 C/B 分支。本轮无新硬件/Vivado运行。

长期保留的口径：软件量化指标、仿真逐字节正确、数字时序通过、板上协议正确、PC4K 输出、真实显示和整机吞吐分别验收。理论 MAC/DSP、BRAM KiB 核算与综合/实现报告分别引用。输出整帧装不进板上 BRAM，条带/握手的容量边界按当前候选合同判断，不能沿用旧接口假设。

旧记录中的“不支持 UDP”“只有 Vivado 2022.2”“GitHub 不可访问”“全帧未通过”“没有板测”均有时间与源树边界，不能作为当前事实。
