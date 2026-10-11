# 当前状态 · 2026-10-11

依据截至 10 月 10 日的绑定实验及 10 月 11 日用户澄清更新。本轮仅维护文档和 GitHub 同步，没有新增板测或 Vivado 运行。原始测量以候选目录的最终报告、数据和身份清单为准。

## 当前基线与主线

- ACX750-200T / xc7a200tfbg484-2；Vivado 2025.2，core 150 MHz，pause=0，输出条带 16 行。
- FSRCNN d16/s8/m1/c16：960×540 Y8 输入 → 1920×1080 Y8 输出 → PC 双三次生成 3840×2160 Y8 → 缩放预览。
- 已验收延迟优化基线仍为 2026-10-09 四步整合 V2。本地 `output/C_TO_B_LATENCY_HANDOFF_V2_20261009/`，GitHub `deliverables/c_latency_v2_20261009/`。
- BIT SHA256：`cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5`；DCP SHA256：`47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da`。
- input64 / batch1 / output128 是已测运行候选，未提升为冻结默认；当前 BIT 不支持 EVF3。
- **跨帧方案尚未正式交付。** 10 月 10 日已有单 RAM 设计/合同草案评审和隔离 RTL 实验，但不能据此宣布跨帧方案已完成、已实施或可验收。当前原分工 C03 主线等待正式方案；执行计划 C05/C06 为待方案/待新实现验收，整机 4K30 尚未达标。

## 已证实结果

- 同 BIT 输入扩窗：20 个成功 case 共 360 帧 Golden 零差；四轮平衡对照中，input64 的实际 Natural16 协议循环约 21.224 fps，input128 约 21.186 fps 且长尾较大。首次 JTAG 失败保留。见 `candidates/20261010_input_window_plan/results/RESULT.md`。
- input64 长期复核：32 个完整原 Run，共 512 个 Natural16、64 个 Natural2，1,194,393,600 个 Golden 字节零差；逐 case 正常零重复门槛通过。Natural16 按实际协议循环累计约 20.479 fps；保留 2 次主机失败和 1 次用户中断，不是连续无失败启动。见 `candidates/20261010_input64_followup/results/RESULT.md`。
- 当前 BIT 的 PC4K：150 个输入槽全部协议完成，4K 逐像素参考零差，实际约 7.304 秒，生成/预览提交约 20.536 fps。完成 150 槽不代表达到 30 fps；应用提交和 Tk 像素检查不代表真实面板刷新。
- 逐调用/轻量 GC 诊断均有 16 帧审计通过。轻量样本最大末输出 RX 至 FINAL TX 间隔 2.7602 ms，间隔内无 GC，未复现原 12.3267 ms 长尾；根因仍未确定，不能从 PC 日志归因 NIC、USB 或物理链路。
- 冻结 V2 数字实现最终 setup/hold 余量 +0.018/+0.050 ns，DRC 无 error/critical；物理 I/O 仍 UNVERIFIED。数字时序、配置读回、协议/Golden、PC4K 与真实显示分别验收。

## 草案与已停止实验的边界

- 单 RAM 设计草案已做条件性环地址安全评审；合同 v1 (`0.1.0-draft`) 原包 SHA256 `260871da8610e8a75fced9fd95b3f82a6509307fb07fec61c77c9adbc5dcbc66`，离线控制模型 21/21、线协议 62 项、交叉检查 7 项通过。这些是实施评审输入，尚无正式方案交付/冻结或实板收益。
- C 隔离 RTL 第一阶段与系统接入实验保留：小尺寸读流及部分 contexts/TX/GMII 定向仿真通过；信用模块有 XSim elaboration 访问异常，完整 HELLO/STATE/CREDIT/主动信用通路未接齐。最新版综合包装器因目录错误判失败，post-synth WNS −1.629 ns、post-place WNS −2.898 ns；P&R 按用户要求停止，无最终 route、新 BIT 或板测。
- 原报告不改写，入口为 `20261010_single_ram_cross_frame_review`、`20261010_single_ram_contract_review`、`20261010_single_ram_rtl_phase1`、`20261010_single_ram_rtl_integration` 候选。既有实验不替代 B 的正式方案。

## 未完成项与下一步

1. 等待跨帧正式方案/实施交付，确认同版合同、资源、真实握手/信用、帧所有权与恢复边界；方案未到前，不恢复已停止实现，不向当前 BIT 发送 EVF3。
2. 新实现先完成真实 CNN 三帧/网络 Golden、完整物理顶层布局布线、150 MHz 时序及 CDC/DRC 审查，绑定新 BIT/DCP 后 C 再独立复核和板测；模型或 GMII OOC 不替代这些门槛。
3. 可独立继续准备 A 正式后处理同帧对拍、独立后处理预算、播放器/有界队列与恢复验收材料；当前约 20–21 fps 不关闭持续整机 4K30 门槛。
4. 两类主机停滞尚未全部查明：一次 Smoke 审计原生栈指向 SyncDisk 注入锁等待，另一次板卡 I/O 前 bootstrap 超时根因未证实。10 月 10 日按用户要求停止 AnyShare Family7 服务且未改 Automatic 配置；本轮未重新检查服务或建立性能因果关系。
5. 最终恢复矩阵、真实显示刷新、持续整机 4K30、公平软件比较、最终机器彩排和提交版冻结仍待验收。

给 B 的既有实施前材料见 `candidates/20261010_b_implementation_support/results/RESULT.md`：四窗口证据、条件性 I/O 来源和独立 C 差异已整理，原 ZIP/收据保留；先前没有发送材料，GitHub 文档同步不代表 B 已签收。

任务矩阵见 `C_TASK_STATUS.json`；计划入口在 `C:/Users/Administrator/Desktop/srtp/计划/PLD竞赛2026_C侧执行任务规划_20261007.md`，GitHub 镜像在 `workspace/plans/`；同步范围及本地原报告映射见 GitHub `workspace/evidence/20261010/INDEX.json`。冻结交付字节不变，旧 BOARD_PENDING 由最终收据补充。
