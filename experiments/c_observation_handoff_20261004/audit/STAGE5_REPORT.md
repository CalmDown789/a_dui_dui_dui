阶段 5 报告：真实 B 端到端受控背压与两帧 UART 回归

状态：PASS。仿真只在隔离候选目录运行，输入固定 B RTL、冻结 C 派生候选和两组既有 Golden 向量。原始 C 工程和冻结基线未改动。

通过条件和结果

- 使用固定 B 提交 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a` 的真实计算 RTL 编译；Vivado 2025.2 `xvlog_b`、`xvlog_c`、`xelab`、`xsim` 均退出码 0。
- 连续发送两帧 96×54 输入，不复位；每帧均输出 20,736 字节并逐字节匹配 Golden，mismatch=0。
- 每帧只在 B 输出有效且原始 ready 可接收时注入 16 周期暂停；快照各记录 request=16、forced-block=16。两帧累计强制阻塞 32 周期。
- 两帧快照分别为 slot/frame_id 0/0 与 1/1；输入/输出握手计数 5,184/20,736，stripe_last/frame_last 计数与用例几何一致；UART 字节增量 20,736；错误和 C→B、B→C hold violation 均为 0；两帧槽保留且无溢出。
- 原始 C 非忽略文件 333 项、Git index 哈希和冻结 overlay 22 项只读重哈希全部通过。

主证据

- 受控暂停测试台：`observe_candidate01/overlay/multiframe/tb/tb_c_controlled_pause.v`
- 测试台生成器与仿真启动器：`observe_candidate01/scripts/create_controlled_pause_tb.py`、`observe_candidate01/scripts/run_alignment_sim.py`
- PASS 收据及源哈希清单：`observe_candidate01/sim/controlled_observe03/result.json`、`source_manifest.json`
- 编译和仿真日志：`observe_candidate01/sim/controlled_observe03/xvlog_b_stdout.txt`、`xvlog_c_stdout.txt`、`xelab_stdout.txt`、`xsim_stdout.txt`
- 原始 C 和冻结基线保护复核：`audit/stage5_preservation_postcheck.json`

保留的失败尝试

- `observe_candidate01/sim/controlled_observe01_prelaunch_failure/`：启动器缩进错误，Python 在调用 HDL 工具前退出。
- `observe_candidate01/sim/controlled_observe02/`：真实 B 编译通过，C 测试台编译因一个暂停信号名拼写错误退出；修正后由 observe03 重跑。两次失败均未进入硬件或实现流程。
