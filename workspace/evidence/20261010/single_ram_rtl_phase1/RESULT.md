# 单 RAM 跨帧 RTL 候选第一阶段 · 2026-10-10

**结果：两个隔离 RTL 构件已实现并分别综合；输入读流的小尺寸回绕/背压仿真干净通过，信用守卫的测试输出通过但 XSim elaboration 持续报告访问异常，因此信用模块仿真不作干净签核。尚未接入完整系统。** 本候选不产生 BIT，也不改变冻结基线。

## 变更与身份

- `rtl/input_stream.v` 从冻结源 `input_stream.v` SHA256 `15cb1062caa76ebad5826f1b4b0eaf1aecd0763fcc81c326803846372215d3b8` 复制后修改；最终候选 SHA256 `2eb888e594ad062bbb74ea2ac7b297d3e27be3b3290650571ca2f105837523a4`。新增 `frame_base` 在 `start_load` 时采样；物理 `req_addr_q` 自然回绕；以独立逻辑 `req_count_q` 判定最后请求和整帧交付，不再拿物理地址与 N 比较。
- `rtl/ring_credit_guard.sv` 为新的隔离模块，SHA256 `5838a93080e75223171116cbdbacebbe7607cd532f06ee47f0476674e33c57fd`。旧帧累计 C 只由 `c2b_pop` 推进；用上一拍 C 形成 `L=min(N,C+D)`，无旧输入 owner 时 L=N。整包校验长度及 `R+packet_bytes<=L` 才预约 R；W 和物理写指针只由实际 `write_fire` 推进。对同拍新消费授予、最后短包和包长不符采用保守拒绝。调用方仍负责 SID/frame/epoch、包 CRC/指纹、bank、ABORT drain、owner 与启动 join。
- 冻结 BIT/DCP 本轮重算 SHA256 仍分别为 `cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5`、`47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da`。

## 验证

| 层级 | 结果 | 边界 |
|---|---|---|
| `tb_input_stream_ring.sv` | XSim `-O0 -mt off -debug typical` 编译/仿真退出码 0，最终日志无 ERROR/FATAL，`PASS_INPUT_STREAM_RING frames=4 accepted=48`。 | 4×3 像素、16 地址物理环；4 个基址 0/4/8/12，背压、保持、坐标、逻辑终点与无额外请求。 |
| `tb_ring_credit_guard.sv` | XSim 退出码 0，`PASS_RING_CREDIT_GUARD checks=16 C=12 W=12 R=12`；但 `xelab.log` 报 `ERROR: [XSIM 43-3294] Signal EXCEPTION_ACCESS_VIOLATION`，重试仍出现。**状态：条件通过，非干净签核。** | N=12、M=16、包 5/5/2；同拍 pop 不授予信用、整包拒绝、物理回绕、旧未消费地址保护和最后短包。 |
| 单模块综合 | Vivado 2025.2、xc7a200tfbg484-2，两个 `synth_design` 均退出码 0。信用守卫 187 LUT/82 FF、0 warning；读流 87 LUT/82 FF、24 个常量高位 debug 端口 warning。 | 单模块、无约束综合；这些数字不是完整设计增量，也未做实现、CDC 或 150 MHz 时序。 |

早期 XSim 0 ps 内核 FATAL、elaboration 访问异常和首次综合脚本选项错误的原始日志留在 `build/`。不能因最终测试打印 PASS 而抹去这些失败；尚未定位 XSim 异常来源。选定最终日志与资源报告复制到 `results/evidence/`。

## 下一步

先用一个不报 XSim elaboration ERROR 的仿真环境重测信用守卫；随后把 `frame_base`、C/R/W/L 和写地址正式接入独立的 `c_ethernet_core`/RX 候选，增加 packet bank/CRC/ACK 身份与 ABORT issue/drain，再实现三方 ready/accepted 及早期控制保留通路。达到这些 RTL 门槛后才能进行完整三帧 CNN/网络 Golden、综合实现/时序、新 BIT 和板测。当前模块不得直接替换现有 RUNNING 禁写逻辑。
