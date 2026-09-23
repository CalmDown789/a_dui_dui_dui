# 成员B工作：对 C 分支 `4827f19` 的接口与证据回复

日期：2026-09-23。只读审查来源为 `origin/c-side-latest@4827f19619aa96a6601aebf53cf121a3063141f3`。本文是 B 对当前 RTL 的事实回填，不修改 C 原文件，也不替 C 签板级结果。

## B-IF-1/2/3：已由 B 当前 RTL 回答

1. **真实顶层模块名：`b_core_real`**，文件为 `rtl/stream/b_core_real.sv`，已在 `member-b-five-layer-stream@ae29515` 推送。内部调用 `fsrcnn_network_mem_top`，五层参数 ROM 包在 `rom/member_a_d16_s8_m1_c16/`。
2. **端口：** `clk_200,rst_n,start,busy,done,in_valid,in_ready,in_data,out_valid,out_data,out_ready,stripe_last,frame_last` 共 13 个，与 C-B v0.2 的信号名、方向及 8-bit 输入/输出宽度逐项一致。C 的 `b_core_if.v` 已用命名连接，端口声明顺序不影响连接；请以端口名和方向核对。
3. **几何参数化：** B 顶层有编译期参数 `IMG_W=960, IMG_H=540, STRIPE_H=64`，**没有运行时尺寸端口或握手**。生产尺寸可使用默认值；C 的小尺寸 TB 必须显式传 `.IMG_W(IMG_W),.IMG_H(IMG_H),.STRIPE_H(STRIPE_H)`，否则 C 的小图参数不会传进 B。B 已在 C 原始 `c_core` 的隔离副本中完成这种接法的连续两帧 6×5、240 字节位精确联调，未改 C 源码。

## 新交付与现有 C 报告的边界

- C 的 `rtl/b_real/PROVENANCE.md` 明确镜像源为旧 `acx750-rtl@658c82e`，仅有 17 个算术/窗口原语，**不包含**上述五层流式 top。`run_sim.tcl`/`synth_check.tcl`/`impl_check.tcl` 虽已把旧原语加入文件列表，但 `c_synth_top` 仍实例化最近邻 `b_core_stub`。正式接入请使用 B 新分支的 15 个五层相关 RTL 文件（详见 `member_b_c_real_core_handoff.md`），以 SystemVerilog 读入，并把 19 个 `*_packed.mem` 放到 `$readmemh` 的运行目录。
- C 的 `report/impl/impl_result.txt` 是 **stub 骨架 post-route**：192 RAMB36、0 DSP、WNS −2.749 ns；它不是完整 B+C 时序。`report/b_real_synth/synth_result.txt` 的 127 DSP、WNS −5.353 ns 是**旧 17 原语 benchmark 的仅综合**，不是五层网络。B 已完成 6×5、96×54 和 A 权威 960×540 整帧 XSim：全尺寸 2,073,600 Y 字节逐值 PASS，4,180,019 仿真周期；这些仍不证明 XC7A200T 上 200 MHz 或 30 fps。
- C 当前 `BRAM_BUDGET_MAP.md` 的 276 块外推使用 B v1.1 的旧 44 块。B 当前逐 bank RTL 的条件性预估为约 **46 块**（见 `member_b_backpressure_contract.md`），则同样口径是 `192+46+40=278`，低于 85% 线的 310 块，但 **278 也不是目标综合实测**。请用真实五层合并后的 `report_utilization` 替换两种外推。

## A Golden 的版本一致性与仍需 A 回答的问题

- C 分支留档的 manifest 与用户新提供的 A ZIP 均把输出 SHA256 写为 `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`，`quant_params.json` SHA256 均为 `f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a`。B 独立核对新 ZIP 的 8 个数据文件、56 个量化参数文件、524288 地址输入 ROM 和四相位重排，并以上述 Golden 对完整 RTL 输出逐字节通过。新 ZIP 的 `docs/成员A全尺寸整数Golden确认.md` 有 A 的明确确认文字和各文件哈希。
- C 指出 `main` 上的 A Golden 提交曾被 revert。**B 不能代 A 解释 revert 的原因，也不能决定正式重新发布位置。** 若 C8 门槛要求 `main` 上可取的权威提交，仍请 A 回答：撤回原因、最终权威 commit/路径、输入图和 checkpoint 等生成来源。B 的功能对拍结论与这个仓库发布治理问题要分开记录。

## C 下一步可执行验收

1. 更新 C 的 B 镜像/文件列表到 `member-b-five-layer-stream@ae29515`；保留原 stub 仿真作为 C 基础回归，并新增启用 `C_USE_B_REAL` 的真实网络回归。
2. 小图联调传入上述三个编译期参数；整图使用 A 的 `input_rom_2p19_u8.mem` 和 `output_1920x1080_y_u8.bin`，对比 8-bit Y、`stripe_last/frame_last`、`busy/done`、输入/输出 stall。C 现有最近邻 stub scoreboard 不能作为 FSRCNN 期望值。
3. 在 `xc7a200tfbg484-2` 上对 **真实 B+C 合并顶层**分别跑综合和 post-route，给分层 DSP/RAMB36/LUT/FF、关键路径、时钟/XDC 与失败端点；在这些报告到位前，370 DSP、271/278 RAMB36、200 MHz、30 fps 均不能称已实现。
