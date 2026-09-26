# 200 MHz 备用候选：shared post 按组移动输入槽

## 状态

**2026-09-26 19:44：Vivado/XSim 2025.2 独立单元仿真 5/5 配置 PASS。** V2 整网回归及综合、布线仍需另行验证；单测不能证明时序收益。

成功会话 PID `30704`，工作目录 `unit_work/run_20260926_194349_30704/`。五配置覆盖 GROUPS=1/2/4/8；每配置接受 422、输出 418 个向量，差值 4 为定向复位丢弃。两个槽反复复用，同拍接收/issue、反压保持与逐拍 reference 对照均通过。原始日志及源文件 raw/canonical 哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units_next/summary.json)。

本候选以 `requant_pipe/vector_postprocess_shared.sv` 为基线，保留 9 拍 metadata 和带完整乘积寄存级的 scalar。它只替换 shared 的 accumulator 选组方式，没有增加流水拍数或槽数量。是否改善频率须由后续实现确认。

后续与四项主候选组合时，只将 shared 的源文件路径替换成本目录版本；scalar 副本用于本目录独立单元闭包，与主候选 scalar 内容相同，不要把两个同名 scalar 文件同时加入编译。reference 与 TB 不加入综合。

## 本地报告依据

原 200 MHz routed 报告：`_synth_bc/acc36_realrom_200_member_b_setup0300926_ascii_ramdecomp/reports/setup_paths.rpt`。

两条路径均从 L1 `post/issue_slot_reg` 到 `units[0].post/prelu_product_s10/A[14]` 或 `A[13]`，slack 分别为 **−0.416/−0.413 ns**。最差路径数据延迟 5.090 ns，其中 route 4.342 ns、logic 0.748 ns，3 级 LUT。路径先选择两个 slot 的 issued 组号（该网络 fanout 100），再穿过 `dispatch_accum` 的通道选择 LUT。

因此 accumulator 变量 part-select 有直接路径依据。该报告没有证明本候选的物理收益；路径中大部分延迟来自布线。

## 修改与不变项

原读取：

```systemverilog
input_slot[issue_slot][(issue_group*LANES+lane)*32+:32]
```

候选读取：

```systemverilog
input_slot[issue_slot][lane*32+:32]
```

每次 `issue_valid` 成立的上升沿，同时执行固定右移：

```systemverilog
input_slot[issue_slot] <= input_slot[issue_slot] >> (LANES*32);
```

非阻塞赋值保证 dispatch 先取得原低组，而右移后的下一组从下个周期开始可读。移位量是参数常数，填充零。最后一组 issue 后 issued 到达 GROUPS，该槽停止 issue，直到完成并回收。

`issued`、`completed`、三个 slot 指针、occupied/ready、dispatch valid、9 拍 slot/group/valid 标签和所有输出更新条件保持基线逻辑。PReLU 与 Q31 系数仍按 `issue_group` 选取；系数必须保持原接口要求的静态配置。相比当前 requant_pipe，外部 ready/valid/输出数据及拍数应逐拍一致。

## 同拍行为审查

| 事件 | 安全条件 |
|---|---|
| 同拍 input_fire 与 issue_valid | 接收要求 write_slot 未占用，issue 要求 issue_slot 已占用，因此两者必为不同槽。可一槽装入新向量、另一槽右移。 |
| 同拍 output_fire 与 issue_valid | 可回收槽已经完成全部分组，不能仍在 issue。若两事件同时发生，issue 必属另一槽。 |
| 释放后复用 | ready 仍只看当前 occupied；释放边沿后下一拍才允许重装。新向量完整覆盖该槽，issued/completed 归零。 |
| reset | 两个输入槽及全部控制/metadata 仍同步清零，未完成向量作废。 |
| GROUPS=1 | 唯一组在右移前被 dispatch 采样；全宽右移得到零，不引入空 part-select。 |

候选增加了仅仿真使用的同槽 input/issue、output/issue 冲突断言。

## 验证闭包

- `vector_postprocess_shared.sv`：候选。
- `vector_postprocess_shared_reference.sv`：当前 requant_pipe shared，仅重命名模块；对应原文件 SHA256 `550FD731D935FE561756E6E3489220EFA1948AF0C316FFC22BD6221F5FE602DD`。
- `prelu_requantize.sv`：当前 requant_pipe scalar 原样副本；SHA256 `46F448B9067507ACC5CF2B6EC93D4A2A3EEF8BF6084E8AEF702E1EFBCF2A489A`。候选与 reference 均使用这一模块。
- `tb_post_shift.sv`：复用独立整数数学 shared scoreboard，增加候选与当前 reference 的逐拍 ready/valid/数据对照、原始 dispatch accumulator 对照及右移/槽冲突覆盖。覆盖本网络三种组态和 GROUPS=1/2 边界、长背压、同时接收与 issue、槽复用、随机输入/反压、在途 reset。比较 dispatch 原始值可避免输出饱和掩盖通道错序。
- `run_unit.tcl`：仅运行独立组合单元 TB；每次新建 run 目录。编译/展开使用 `--nolog`，XSim 控制台和 engine 日志分别为 `xsim.log`、`xsim_engine.log`，在 xelab 之后补齐已知 DLL 依赖。

确认 `V:` 映射到本试验仓库后，由父任务择机在 Vivado Tcl Console 执行：

```tcl
source V:/experiments/timing_200_20260926/post_shift/run_unit.tcl
```

应出现 5 个 `POST_SHIFT_CONFIG_PASS`、`POST_SHIFT_ALL_CONFIGS_PASS`，runner 最后输出 `POST_SHIFT_UNIT_TEST_PASS`。所有输出只写本目录 `unit_work/`；当前没有运行结果。

## 后续需要确认

1. 单元等价通过后，再把候选放入独立的完整 Golden 和反压回归；不要覆盖正在运行的主候选目录。
2. 网表应显示 accumulator 选组变量 mux 消失，只剩 slot 选择和固定低位读取。
3. 每次 issue 都写宽输入槽，会增加槽数据 mux、写使能扇出及切换活动。须检查是否把瓶颈转移到 input_slot 的 D/CE 或 issue 控制，比较 LUT/FF、控制集合与最终 setup/hold。
4. 系数的分组选择仍保留。若新的关键路径转为 PReLU/Q31 系数选择，应按新路径证据处理，不能据本候选自动延长流水。
5. 完整 Golden 与最终实现均通过，才能计入交付结果。
