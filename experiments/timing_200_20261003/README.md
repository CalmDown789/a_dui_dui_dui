# 成员 B：200 MHz 时序优化续轮（2026-10-03）

真实 B 五层 + C 外壳 + A bank16 输入 ROM，目标器件 `xc7a200tfbg484-2`。
时钟保持 5.000 ns，最终额外 setup UU=0，自动 TSJ/DJ/PE 保留。
目标 WNS +0.100 / +0.250 / +0.400 ns，同时 TNS=0、WHS>=0、THS=0、脉宽通过、全路由且错误0。

首个实验从 V1 nominal / pipeline000 的冻结 post-route DCP 开始。
输入 SHA256 `abe0c41bfda7b06d5dd920094053b56eef17daa02a32d7ebb5c5bfd43e25b1d0`。
输入完整实现、RTL/ROM 哈希与功能证据沿用 `member_b_evidence/timing_200_20260926/pipeline000` 和 `sim_pipeline200`。
物理收尾复用已核对的 `experiments/timing_200_20260926/postroute_finish/finish.tcl`，不修改旧脚本。

- `_synth_bc/postroute200_v1_nominal000_20261003_try1`：受限会话 Vivado 初始化用户组件失败，未读 DCP；原日志保留。
- `_synth_bc/postroute200_v1_nominal000_20261003_try2`：正常用户会话，AggressiveExplore，额外 setup 压力0；最终 WNS/TNS -0.083/-6.608 ns，214个setup违例端点，WHS/THS +0.036/0 ns，全路由/错误0，尚未达标。
- `postroute_focus/`：驱动审计表明L5写使能有9个LUT3副本，其中8个各1056个负载。try1–4停于保护查询，try5确认post-route不支持`-force_replication_on_nets`（Vivado_Tcl 4-265），没有新的物理结果。此脚本保留为失败尝试证据，**不能直接作为post-route可用入口**。
- 每进程 `maxThreads=2`，外部 Python 使用 `-I`。
- 当前工具会话的 V: 映射需在同一次启动命令中验证；受限会话映射不跨工具调用共享。

150 MHz 发布候选 `6cc8ea4` 和 C 板级工作保持独立。物理结果不能视作上板验证；助手验证不代表用户已掌握。

## 已否决的容量ready候选

V1基础上仅将6400位、深4的L5窗口FIFO ready改为已登记容量，不使用满队列同拍pop的look-ahead；算术和存储保持。
`fifo_capacity/elastic_fifo.sv`为独立覆盖文件，6400位单测与三帧背压/四组短图Golden已通过。
单测第一次因非空reset覆盖不足失败，增强定向激励后通过，未放宽判据；日志均保存。

精确选源入口为`run_sim_fifo_capacity.tcl`和`synth_fifo_capacity.tcl`，生成器保留可追溯变更。
66项综合启动输入哈希在新stage保存，完整实现已完成：
`_synth_bc/acc36_realrom_200_member_b_fifo_capacity_20261003_nominal_ascii_ramdecomp`。
默认/已运行参数为`impl acc36 ascii ramdecomp nominal`，额外setup压力0。
最终WNS/TNS -0.640/-786.978 ns，6212个负setup端点，明显退步，未采用且未跑整帧。

## 局部LUT ECO与物理收尾

`postroute_eco/`只在经审计的9个L5窗口RAM写使能LUT3上改INIT 8A→0A。
`prove_fifo_credit.py`和`fifo_credit_proof.json`记录16状态/256转移的抽象容量穷举；不是自动提取RTL或网表形式等价。
实际FIFO ready/count/pointer不改；原frontend容量预留下，改变的full+raw_valid输入组合不可达。
局部ECO收尾WNS/TNS -0.043/-0.260 ns，随后`postroute_route/`收尾为-0.041/-0.217 ns，仍未达标。
后者在完整已布线DCP上被工具选择为TNS cleanup，AggressiveExplore路由directive被忽略；日志保留，不宣称已重布线。
`credit_eco_model/`是仅内存写条件改变的RTL模型，保留原握手和指针，并断言真实frontend容量条件；没有单独运行该模型的整帧，不能声称纯ECO网表已仿真。

## 当前候选：padding边界标志寄存器

`pad_flags/`缓存当前x/y的interior标志，与坐标同边沿更新，不加stream延迟；合并上述容量内存写模型。
原padding对照测试四配置各三帧全部PASS，包括完整960×540扫描、随机stall和reset。
真实五层背压三帧和四组短图Golden、标志及容量每拍断言全部通过，证据`sim_pad_flags_short`。
入口`run_sim_pad_flags.tcl`、`synth_pad_flags.tcl`，生成器`prepare_pad_flags.py`拒绝覆盖已有文件。
完整实现已完成：`_synth_bc/acc36_realrom_200_member_b_pad_flags_20261003_setup030_ascii_ramdecomp`，参数`impl acc36 ascii ramdecomp`，66项输入哈希冻结，临时setup压力0.300 ns最终恢复0。最终WNS/TNS -0.179/-6.939 ns，164个setup违例端点，hold/脉宽通过，全路由/错误0。
该候选唯一整帧Golden回归通过：2073600个输出字节全部一致，4959092拍，与V1相同；不是C外壳/真实ROM驱动的系统仿真。独立日志/TB目录和默认XSim -O0；有限并行用于减少约47分钟串行等待。
`postroute_pad/`在冻结的新DCP上另做布线后物理优化，最终恢复UU0，WNS/TNS -0.158/-5.057 ns，hold/脉宽通过，全路由/错误0。两次结果独立保存，仍未达标。

## 重启暂停（历史）与恢复

用户要求当前进程完成后暂停。本轮全部实现、仿真及诊断已正常退出，无Vivado/XSim进程残留；尚未Git add/commit/push。恢复前不启动任何作业。
`rom_pipeline/`三拍ROM+匹配的容量响应队列专项测试通过：四配置各三帧，真实960×540每帧518400像素、请求地址/数据/坐标/背压/复位核对。证据`rom_pipeline_unit`。
当前冻结源码看`rom_pipeline/frozen_manifest.json`；最初两拍`prepared_manifest.json`是未运行且已被替代的草稿记录。新C输入路径尚未接入真实B做联合Golden，也未综合/实现；恢复后先完成联合短图验证。
最好已测量结果仍为纯ECO收尾WNS/TNS -0.041/-0.217 ns，没有200 MHz裕量档位通过。保留150 MHz发布候选。

用户已要求恢复。`run_sim_rom_pipeline.tcl`完成实际C外壳+新ROM/stream+真实B联合四组短图，Golden、输入坐标和背压保持均PASS，798286拍/591024拍输出stall；证据`sim_rom_pipeline_integration`。未验证UART串行解码Golden或整帧系统。
`synth_rom_pipeline_inc.tcl`已完成真实B+C 200 MHz增量候选，69项输入冻结，参考DCP只提供物理位置/路由。stage后缀`_try2`；首次V:/F:路径保护失败在综合前退出，已归档并修正，目录不覆盖。最终原约束UU0 WNS/TNS -0.517/-791.200 ns，5698个setup端点，WHS/THS +0.013/0、WPWS +1.370，全74042网路由/错误0；LUT27896/FF49365/BRAM226+8/DSP394。未采用该布局，证据`rom_pipeline_inc_setup030`/`rom_inc_implementation_log`。

实际综合输入ROM为128个RAMB36，有效A端口DOA_REG全部1。增量after_place位置复用96.03%、网89.00%、引脚74.87%；最终位置/网95.94%/85.42%；工具把Default place改为Explore。高复用未带来时序改善，当前最佳仍纯ECO收尾-0.041/-0.217 ns，200MHz目标未达成。

`issue_head/`新增直接FIFO队头八相位候选，只在phase7消费窗口，输入握手时刻改变；不能称逐周期等价。位宽1/256/6400的旧/新accepted相位序列单测PASS（`issue_head_unit`）；实际C外壳四组Golden PASS（`sim_issue_head_c`，798291拍/590989真实输出stall）。B-only短图/背压全部PASS，211962/161940拍，分别独立归档`sim_issue_head_b_short`/`sim_issue_head_b_backpressure`。22:37新B源码全帧Golden PASS：2073600字节一致、4959087拍、17stripe_last/1frame_last/1done、错字节/X/hold0（`sim_issue_head_b_full`）。少于V1的5拍来自启动时刻，不能据此宣称吞吐或帧率改善；不是完整C系统或上板证据。
`prepare_issue_head_impl.py`准备重新布局的`synth_issue_head_fresh.tcl`，不使用增量DCP，原5ns/抖动/XDC与恢复UU0规则不变；用户要求现有工作结束后今日暂停，**尚未启动，留待恢复后运行**。ROM3增量实现、直接队头B-only全帧Golden和只读诊断均正常退出并归档，无Vivado/XSim残留；原200MHz目标未达成，按用户要求暂停，交接入口为工作区根HANDOFF.md。

证据及新实验目录通过本轮限定的`.gitattributes -text`保留原始字节，避免跨平台换行转换破坏SHA256。大型DCP/仿真缓存只在本地`_synth_bc`/`_sim*`，未上传Git；迁移工作区时若需要精确复用DCP，应另行保留这些本地目录。

最新结论和证据边界见`docs/MEMBER_B_200MHZ_TIMING_2026-10-03.md`。
