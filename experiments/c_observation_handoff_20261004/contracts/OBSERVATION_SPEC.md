C-B 观察与暂停边界说明（阶段 4）

范围与固定来源
本阶段只描述隔离候选 observe_candidate01。C 源来自冻结快照 _c2025_2_validation_20261004_02，B 侧计算 RTL 来自固定提交 6cc8ea4173d2a720f741e80b7cbd9279558ee93a，A 输入 ROM 来自固定提交 98c82f394bdfba85bc2959bede9760edc4d6862f。候选目录之外不写入 RTL。ILA/VIO 由本地 Vivado 2025.2 生成，配置与输出哈希单独留档。

观察边界
C 输入计数点是 C→B 的 in_valid/in_ready/data；B 输出计数点是 B→C 的 out_valid/out_ready/data/stripe_last/frame_last。握手只在 valid && ready 的采样沿计数。B 输出停顿是 valid && !ready；C 输入停顿是 valid && !ready；C 供数等待定义为 core_busy、已接受输入尚未达到 EXPECTED_INPUTS 且 c2b_valid 为 0。联合停顿是同一周期同时满足 B 输出阻塞和 C 供数等待，两者不相加也不重复扣除。

本实现只观测现有边界信号，不改数值流、几何、Golden 或验收门槛。功能仿真和普通构建将 OBS_TEST_PAUSE_ENABLE 保持 0；只有明确启用该参数的受控暂停试验构建才让 dbg_obs_control[4] 门控 B 的 out_ready。VIO 的 5 位输出 INIT 值为 0，启动时快照选择 0 且暂停关闭。用户改变控制位前，仍需确认当前硬件及串口状态。

帧边界与计数语义
frame_start 采样沿开始一帧并锁存 expected_frame_id、UART 字节起点及首拍握手。session_done 只在 frame_active_q 有效时保存记录；顶层把它接到既有 loader frame_done。该采样记录最终 UART 空闲、core_busy、core_done_seen、帧错误和串口错误计数。core_span_cycles 从 frame_start 到首次采样 core_done，含等待、停顿周期。session_done_cycle 从 frame_start 采样沿计为 1，并包括保存快照的 session_done 沿。last_input_cycle 与 last_output_cycle 是对应预期数量的最后一次握手距 frame_start 的周期编号；若计数未到预期，则为 0。

core proto/overflow、loader protocol error、loader frame error count、UART framing error count 按其源寄存器语义取样：错误位自复位后粘滞，错误计数为自复位后的累计值，不等同于本帧独占错误计数。UART byte delta 是 session_done 时的累计 UART 字节计数减 frame_start 锁存值。output_blocked、b_input_wait、c2b_stall、joint_stall、pause_request、pause_forced_block 均为 frame_active_q 周期级计数。hold violation 在上一周期已经 valid&&!ready 后，下一周期 valid 撤销或 payload/sideband 改变时加一；C→B 检查 data，B→C 检查 data/stripe_last/frame_last。

934 位快照布局
snapshot_selected_data 的低位到高位布局见 signal_map.json。总宽度由 31 个字段组成，合计 934 位；位 0 是 valid，位 933 是 session_done 时 pause_active。16 个帧槽按索引 0 至 15 保存，snapshot_count 达到 16 后饱和并置 snapshot_overflow；本设计不环回覆盖旧帧。snapshot_select 为 VIO 输出的低 4 位。ILA 记录 valid、完整快照、slot select、frame_start、core_busy、core_done、frame_done、暂停有效、暂停强制阻塞和槽溢出；2025.2 的 ILA 最小采样深度为 1024，时钟周期元数据设置为 6.666667 ns。VIO 单个输入宽度限制为 256 位，故 934 位快照分成 [255:0]、[511:256]、[767:512]、[933:768] 四个只读探针，另有 valid、count，并提供安全初始化为零的控制输出。

阶段 4 产物与通过条件
阶段 4 的可审查产物包括信号契约、位映射、候选与冻结基线差异清单、IP 配置与生成证据、观察模块自检源和仿真日志。阶段 4 通过条件为：快照总宽度和字段映射校验一致；Vivado 2025.2 生成的 ILA/VIO 端口宽度与包装器相符且 VIO 初值全零；自检覆盖首末握手、frame_id、stripe/frame sideband、停顿与联合停顿、hold violation、错误快照、core_done/session_done、UART 空闲时快照、双槽保留和溢出；原始 C 工作树与冻结基线字节级未变化。该自检仅验证计量逻辑，不构成真实 B 的端到端功能或板上通过证据。

未覆盖项
该模块不判定是否恰好收到 EXPECTED_INPUTS/EXPECTED_OUTPUTS，也不将 sticky 错误计数归属到单帧；自检负责核验示例计数，阶段 5/6 的真实 B 仿真和新建板级时序工程负责后续验收。复位结构与 UART 物理 bit-time 仍保持 OPEN。200 MHz 不在当前交付阻塞范围。
