# 成员 B：200 MHz 时序优化续轮

2026-10-03；本轮独立于 C 的 150 MHz 板级结果对话，用户授权继续本地优化及发布至 `member-b-2025-2-bc-trial`。

## 基线与目标

真实 B 五层、C 外壳与 A bank16 输入 ROM；Vivado 2025.2，`xc7a200tfbg484-2`，5.000 ns。
最低/中间/最高 WNS 目标 +0.100/+0.250/+0.400 ns；同时 TNS=0、WHS>=0、THS=0、脉宽通过、全路由/错误0。
自动抖动和有效约束保留；临时 setup 压力仅用于搜索，最终恢复 UU=0 验收。

本轮结束时的最好已测结果仍为WNS/TNS **-0.041/-0.217 ns**，三档裕量均未通过。新的直接FIFO队头B-only整帧Golden已通过2073600字节；该候选重新布局尚未运行，按用户要求留待以后。ROM3增量布局最终-0.517/-791.200 ns，未采用；当前按用户指示收尾暂停。

推荐续跑的原始 V1 nominal DCP SHA256：`abe0c41bfda7b06d5dd920094053b56eef17daa02a32d7ebb5c5bfd43e25b1d0`，86,334,752 字节。
源码/ROM 与功能证据对应上轮 `pipeline000`/`sim_pipeline200`，不能与 V1 setup030 的收尾结果混淆。

## 已测量的物理收尾

| 实验 | WNS ns | TNS ns | setup违例端点 | WHS/THS ns | WPWS ns | 路由 |
|---|---:|---:|---:|---:|---:|---|
| 原 V1 nominal | -0.164 | -7.523 | 226 | +0.036/0 | +1.370 | 完整/错误0 |
| nominal，无额外压力的 AggressiveExplore | -0.083 | -6.608 | 214 | +0.036/0 | +1.370 | 完整/错误0 |

第一个新结果比原基线改善0.081 ns，**仍未通过200 MHz setup，也未达到任何裕量目标**。
最终周期5.000 ns，UU/TSJ/DJ/PE=0/.071/.118/0 ns；未触发 route repair。
资源 LUT 27,994、FF 49,170、RAMB36/18 226/8、DSP394；物理优化增加一个 BUFG（总2个），属于实际时钟布线变化，不是约束修改。
证据：`member_b_evidence/timing_200_20261003/postroute_v1_nominal000`；输出 DCP 在 `_synth_bc/postroute200_v1_nominal000_20261003_try2/postroute.dcp`。

物理优化没有修改 RTL/接口/延迟，复用已验收 V1 RTL 功能结果；没有重复运行未改变源码的整帧回归，也未新增板级功能证据。
沿用实验 XDC 缺 UART LOC/IOSTANDARD、输出 delay 等边界及原 DRC 严重级别；不是完整板级签核。

## 全部违例端点诊断与下一候选

原基线全部226个 setup 违例端点已从 DCP 导出，和 timing summary 数量一致。
其中192个来自 L5 MAC 末级 `valid_q_reg[7]`，12个来自L5 pad y[7]，7个来自L3 pad x[3]，其余15个分散在pad、条带、层间FIFO、MAC、输入ROM。
这是全部负setup端点的来源统计，不是仅最差100条样本，也不代表192个端点贡献全部TNS。

收尾后最差路径是 L5 MAC 末级valid → ready/窗口FIFO pop → 写使能。
该路径逻辑0.748 ns、布线3.886 ns，写使能约1056个负载。
实际驱动审计发现九个既有LUT3写使能副本：八个各1056个负载、一个352个负载。RAM32M内部层次引脚/网段不能直接当作独立物理网络，必须解析到driver parent net。
针对高扇出驱动的布线后强制复制未执行成功：Vivado返回`Vivado_Tcl 4-265`，明确`-force_replication_on_nets`不支持post-route。此前四次均在查询保护检查处停止，未调用物理复制。所有失败入口/脚本/日志保留，不能当作已测量的候选。

## 未采用的局部RTL候选：L5窗口FIFO容量控制

基于V1，只改变`DATA_W=6400 && DEPTH=4`的L5窗口FIFO：`in_ready=(count<DEPTH)`，满队列同时pop时不接受新输入。其他FIFO保留`(count<DEPTH)||pop`。
目的为切断MAC末级valid/ready→八相位issue→FIFO pop→宽FIFO写使能的组合路径，不改变算术、数据宽度或存储结构。原frontend的两项在途预留继续保护raw window输入；功能及实际吞吐必须以该候选的验证为准。

- 6400位独立FIFO单测通过：664次push、656次pop、50次满队列pop覆盖、312次同时读写、2次非空reset、985拍输出stall；所有数据位和输出保持核对。push-pop差值是两次reset丢弃的未输出项，不是漏数。
- 首次单测因非空reset只覆盖一次而失败，强化为在强制输出stall期间reset后重跑通过，未放宽判据；旧失败日志/源码保留。
- 三帧背压及zero/impulse/ramp/random四组短图全部Golden一致；三帧每帧20736字节、错字节0、hold违例0。短图不代表整帧或板级验收。
- 源码/ROM/日志已通过精确选源和编译路径校验归档：`sim_fifo_capacity_short`；FIFO单测为`fifo_capacity_unit`。
- 17:50–18:47完成真实B+C实现，原5ns/额外UU0，66项启动输入哈希冻结；与V1共同的64项输入原始哈希全部相同，只替换FIFO和runner。
- 最终WNS -0.640 ns、TNS -786.978 ns、6212个违例端点、WHS/THS +0.047/0 ns、WPWS +1.370 ns，74279个可路由网全部完成/错误0。LUT28207、FF49362、RAMB36/18 226/8、DSP394。证据`fifo_capacity_nominal`。
- DCP诊断确认MAC-valid到L5 FIFO写使能的组合定时路径已消除（0条），但重新布局布线后全局时序恶化；新最差是C输入ROM bank10 BRAM→16:1读数据mux→`c2b_data_q_reg[0][2]`，数据路径5.317 ns（逻辑2.487、布线2.830）。不能把局部切断等同全局收敛。
- 候选不采用，因此未运行昂贵整帧，也不借用V1整帧PASS。短图/单测PASS仅证明其已运行的功能范围。

## 已测量的局部LUT ECO：保留原FIFO握手与布局

在nominal物理收尾DCP上，只改9个既有L5窗口RAM写使能LUT3的INIT：`8'h8A`→`8'h0A`。实际引脚逐个审计为I0=`raw_valid`、I1=`window_ready`、I2=`count[2]`；不修改ready、计数器、指针或算术。旧函数为`raw_valid && (!count[2] || window_ready)`，新函数为`raw_valid && !count[2]`。

这是一项实际逻辑修改，不是false-path或关闭定时分析。两函数只在`count=4 && raw_valid && window_ready`时不同。原frontend预留两拍在途容量，满足`occupancy+pending1+pending2<=4`及`raw_valid<=pending2`，所以满队列时没有raw_valid。

`prove_fifo_credit.py`对任意pad输入、crop、输出ready及reset做抽象可达状态穷举：16状态/256转移通过；9个原LUT的真值表和驱动审计已冻结。该证据是**抽象容量模型证明，未自动提取RTL/网表做形式等价**。不能声称新FIFO对任意独立输入等价。

- 18:54–19:02完成局部ECO及额外setup 0.300 ns物理收尾；最终恢复UU0，WNS -0.043 ns、TNS -0.260 ns、WHS/THS +0.036/0 ns、WPWS +1.370 ns、全路由/错误0。
- LUT27995、FF49170、RAMB36/18 226/8、DSP394、BUFG2；较原V1 WNS改善0.121 ns，仍未通过setup或任何裕量档位。证据`postroute_v1_credit_eco030`。
- DCP SHA256 `821625c0674db1517f8e79b20e461ec53017c66de09174de17232d758b70a4e0`，34,652,782字节。
- 最差转为L3 pad边界判断→窗口BRAM数据，数据路径4.391 ns（逻辑0.926、布线3.465）。19:05–19:14路由收尾后最终WNS -0.041/TNS -0.217 ns，WHS/THS +0.036/0、WPWS +1.370，全路由/错误0；仍未达标。调用`route_design -directive AggressiveExplore -tns_cleanup`，但工具明确在完整已布线设计上仅执行TNS cleanup、忽略其他选项（Route35-558），随后真实执行物理优化。不能把此调用宣称为已执行AggressiveExplore重布线。
- 已准备与LUT修改对应的RTL内存写条件模型及每拍容量断言；尚未运行。模型保留原ready/count/pointer，只改内存写条件。若保留此逻辑候选，需要短图/背压和整帧功能证据；这仍不等于网表仿真或板级验证。

## 当前候选：padding边界标志寄存器 + 容量写模型

padding在每次输出握手推进x/y的同一边沿更新`interior_x`/`interior_y`，跨入/跨出图像范围时切换标志，stall时保持。原start/busy/reset/坐标/接口不变，无额外stream延迟。两标志寄存器使用KEEP（允许物理复制），组合数据路径不再重新解码x/y。

L5 FIFO使用与九LUT ECO相同的内存写条件，原ready/count/pointer保留；RTL每拍断言检查满队列不能raw_valid，以及实际内存写条件与原push相同。padding每拍断言检查缓存标志与原坐标解码相同。此候选重新综合，不能直接沿用局部ECO DCP时序。

- 独立原模块对照PASS：W/H/PAD=7/5/2、1/1/1、9/7/0、960/540/2，各三帧。完整尺寸组2,838,548拍，693,812拍stall，2次reset；逐拍比较busy/ready/valid/last/所有16位数据及内嵌标志断言。不是形式或网表等价。证据`pad_flag_unit`。
- 真实五层三帧背压和四组短图Golden全部PASS，背压161955拍，四组短图211980拍，与原V1相同；L5容量和各层padding断言未触发。精确选源/ROM/日志证据`sim_pad_flags_short`。
- 19:19–20:30完成单个真实B+C完整200 MHz实现，stage=`acc36_realrom_200_member_b_pad_flags_20261003_setup030_ascii_ramdecomp`。66项启动输入哈希冻结且前后核验未变，35项staged ROM与源文件一致，临时setup压力0.300 ns，最终恢复UU0。
- 20:09完成该候选唯一的960×540整帧Golden回归：输入518400/518400，输出2073600/2073600全部字节一致，错字节/X字节/hold违例均0，17次stripe_last、1次frame_last、1次done，**4,959,092拍，与原V1完全相同**。当前TB条件下未损失吞吐或增加整帧周期；不是C外壳/真实ROM驱动的整帧系统仿真、网表仿真或板级帧率证据。证据`sim_pad_flags_full`，31项精确源码/TB快照、实际参数ROM和Golden校验通过。
- 默认已验收的XSim `-O0`，仿真47分24秒，独立TB目录和日志，未改冻结源码。旧runner注释建议避免并发以减少CPU/磁盘竞争；本轮为节省约47分钟串行等待，仅并行这一个实现和一个仿真，综合maxThreads2。整帧已完成，当前只剩一个实现作业；此决策不改变功能或时序判据。
- 与原V1的66项启动输入相比，63项共同输入原始哈希全部相同，只替换FIFO内存写模型、padding RTL及runner，记录`pad_flags/launch_input_comparison.json`。
- 完整实现最终WNS/TNS **-0.179/-6.939 ns**，164个setup违例端点，WHS/THS +0.027/0 ns，WPWS +1.370 ns；74035个可路由网全部完成/错误0。LUT27923、FF49168、RAMB36/18 226/8、DSP394。证据`pad_flags_setup030`、外层日志及DCP哈希`pad_implementation_log`；DCP 86,393,418字节，SHA256 `7cb3701a14e2c58c968a1b1b8ec537befbeba831a503a7cfac2d4d6d0d78cead`。
- 冻结脚本只执行布线前物理优化。因此另开`postroute_pad/`在该已布线DCP上做额外setup 0.300 ns的AggressiveExplore物理收尾，20:31–20:37完成，最终恢复UU0：WNS/TNS **-0.158/-5.057 ns**，WHS/THS +0.027/0 ns，WPWS +1.370 ns，全路由/错误0。证据`postroute_pad_flags030`，独立目录保留首次完整实现。
- 收尾后只读诊断确认MAC-valid到L5窗口FIFO WE的直接组合定时路径为0，但最差转为L5 partial FIFO count→窗口读指针reset，仍有控制扇出/布线问题。首次完整实现另有C请求控制→ROM银行EN违例；不能认为仅寄存padding即可完成全局收敛。诊断证据`pad_diagnostic`。
- 本轮最好已测量结果仍为`postroute_v1_credit_route030`：WNS -0.041 ns、TNS -0.217 ns；**所有200 MHz裕量目标仍未达到**，不替代150 MHz发布候选。

## C输入ROM三拍流水（专项与短图联合功能PASS）

`rom_pipeline/`只在隔离候选中新增银行内地址/使能入口寄存器、BRAM输出寄存器；ROM读延迟由一拍改为三拍。匹配的`input_stream`用四项响应队列，把三项在途请求计入容量预留，保持输出像素与坐标顺序、背压保持和done条件。外部端口不改，但启动延迟增加；未据此宣称性能提升。

最初两拍草稿未运行；`prepared_manifest.json`仅保留这一历史草稿记录。**当前运行源码依据`frozen_manifest.json`，明确三拍**，源文件/测试/runner哈希前后核验一致。

20:38完成专项RTL测试，四配置1×1、7×5、9×7、960×540各三帧；每配置另有两次在途/非空队列中断复位。完整配置实际A输入ROM每帧518400字节，三个已完成帧的请求地址、像素、坐标全部核对，连续输出和随机/长背压通过；完整配置1726162拍、170890拍输出stall、3次reset。16项真实bank文件及原始ROM副本原始字节一致，证据`rom_pipeline_unit`。

上述专项结果不代表整帧C系统或上板证据。恢复后短图联合验证和实际综合映射结果见下文；B源码未变时，不重复已通过的B-only整帧。

## 20:45用户要求重启前暂停（历史）

用户要求当前进程完成后停止，待重启后继续。本轮完整实现、物理收尾、ROM专项仿真、只读诊断均已正常退出，正常用户进程查询确认无Vivado/xsimk/xelab/xvlog残留。不再启动新综合或仿真；代码、DCP、日志与交接均保存在磁盘。尚未Git add/commit/push，原授权分支发布留待恢复后继续。

## 20:53后用户要求恢复，ROM联合验证完成

重启恢复核对：Git分支和HEAD仍为`member-b-2025-2-bc-trial`/`4b90246`，三拍ROM冻结清单和六个已完成DCP的字节/SHA256全部一致。V:映射通过实际目录文件身份核对；不采用控制台乱码路径作身份判断。

20:58–21:00完成`tb_c_rom_pipeline_bit_exact`：使用**真实`c_core`外壳、三拍ROM/input_stream、C→B FIFO、真实B五层、C ping-pong/UART**。在实际B输入/输出握手处核对像素、坐标和四组96×54整数Golden；96×54使用真实单银行模块内存装载冻结短图，不能说成完整图bank16联合验证。

- impulse/ramp/random/zero四组各输入5184、输出20736，全部字节一致，错字节/X/hold违例0，各2次stripe_last、1次frame_last、1次B done。
- 不在帧间reset，真实C缓冲与UART生成591024拍B输出stall；798286拍完成四组。周期包括真实C通路停等，不能与此前直接TB驱动的211980拍短图比较为计算核吞吐退步。
- 实际编译为C_USE_B_REAL、XSim -O0；31项源码/TB精确闭包、参数ROM、8项Golden和时间戳核对，证据`sim_rom_pipeline_integration`。新ROM源码沿用此前冻结字节。
- 核对的是B输出Golden和C输入像素/坐标，**未对UART串行解码字节做Golden，也未做完整960×540联合系统、网表或板级验收**。

21:08启动单个真实B+C 200 MHz候选：`synth_rom_pipeline_inc.tcl`，stage=`acc36_realrom_200_member_b_rom_pipeline_inc_20261003_setup030_ascii_ramdecomp_try2`。新网表从已验证RTL综合；最好已布线DCP只作为增量位置/路由参考，不导入其RTL替代新源码。69项启动输入含精确参考DCP/辅助脚本/清单冻结，额外setup压力0.300 ns最终恢复UU0。按照安装的2025.2帮助，`read_checkpoint -incremental -directive TimingClosure`、默认place和兼容的Explore route；复用率以实际报告为准，尚无最终结果。

首次启动在参考快照复制的路径保护处失败，原因是Python已把ROOT解析到F:，而目标仍未解析的V:。未进入综合、未产出物理结果；证据`rom_reference_alias_guard_failure`保留旧runner/helper/日志。修正为目标路径先resolve，使用新try2目录，不覆盖首次目录。当前未Git提交/推送。

## 21:52进展：ROM综合映射与直接FIFO队头候选

ROM增量候选实际综合映射为128个输入RAMB36，有效A端口全部DOA_REG=1；B端口未使用，不要求DOB_REG=1。位置复用96.03%、网复用89.00%、引脚复用74.87%（after_place）。工具把请求的Default place自动改为Explore（Place46-84/44），目标WNS=0。最终结果见下文；中间带0.300 ns搜索压力的估计不当作验收结果。

最紧setup/hold引脚包含大量L5 `mac/issue/out_window_reg`。隔离准备`issue_head/eight_phase_issue.sv`：八个MAC相位直接读取FIFO队头，只在第7相位完成握手后消费窗口，去掉单独6400位L5窗口复制。标准源必须在valid期间保持数据直到in_ready；现有窗口FIFO满足这一条件。输入窗口消费时刻及启动延迟改变，不能称逐周期等价，实际面积和时序收益待测。

- 专项参考比较PASS：位宽1/256/6400，各三个完成回合，每回合64窗口/512相位样本，检查旧/新accepted数据、相位和last顺序、随机/长背压与窗口中途复位。证据`issue_head_unit`；不是形式或网表等价。
- 21:41–21:44实际C外壳联合四组96×54 Golden PASS，各输入5184/输出20736全部一致，各2stripe_last/1frame_last/1B done，错字节/X/hold0。总798291拍、590989拍真实C输出stall，证据`sim_issue_head_c`。尚无UART串行解码Golden或完整C系统验证。
- B-only三帧强背压Golden PASS，161940拍/hold0，证据`sim_issue_head_b_backpressure`；四组短图Golden PASS，211962拍，证据`sim_issue_head_b_short`。采集时重复`--tb`只选择了最后一个TB，因此保留首次不可覆盖的短图归档，另存背压归档，两个都严格核对编译闭包和完成日志。
- 21:52–22:37完成新的960×540→1920×1080完整Golden：输入518400、输出2073600全字节一致，错字节/X/hold违例0，17stripe_last/1frame_last/1done，**4,959,087拍**。比相同B-only TB的V1少5拍，仅启动时刻变化，不据此宣称吞吐或帧率提升。44分03秒XSim -O0，精确31项闭包和实际ROM/Golden/日志核对，证据`sim_issue_head_b_full`；不是C外壳/ROM驱动的完整系统、网表或板级验证。
- 已准备`synth_issue_head_fresh.tcl`和精确collector，重新布局、不导入旧DCP；维持原5ns/抖动/XDC，ExtraNetDelay_high place、NoTimingRelaxation route、前后AggressiveExplore physopt，临时压力0.300 ns最终恢复0。用户随后要求今日收尾暂停，该实现**尚未启动，留待用户恢复后运行**。

## ROM3增量实现最终结果（未采用）

21:08–22:56完成真实B+C，工具在原route_design内自动进行增量位置调整和第二轮路由，随后执行原脚本中的AggressiveExplore post-route physopt。后者报告0.000 ns收益；没有再启动额外实现。

- 最终5.000 ns、UU/TSJ/DJ/PE=0/.071/.118/0 ns，WNS/TNS **-0.517/-791.200 ns**，5698个负setup端点；WHS/THS +0.013/0 ns，WPWS +1.370 ns；74042个可路由网全部完成，路由错误0。原0.300 ns压力下为-0.817/-4304.814，恢复差值严格0.300 ns，hold不变。
- LUT27896、FF49365、RAMB36/18 226/8、DSP394。最终位置/网复用95.94%/85.42%；高复用没有带来更好的时序，此次布局不采用，也不替换150MHz发布候选。
- 69项启动输入原始哈希前后完全相同，35项参数/输入bank staging字节一致。证据`rom_pipeline_inc_setup030`和`rom_inc_implementation_log`；本地DCP 86,877,840字节，SHA256 `3c02435158a80a6c68363fa3fa4595a2e309f1f00e9a4e7490418a09a06b9e61`，不上传二进制。
- 正常用户Git归属检查使旧runner中的source_commit为unknown；不以此证明源码身份，实际身份由69项启动/结束原始哈希确定。新准备的head runner和采集器使用本命令精确safe.directory，不改全局设置。
- Vivado 12-8060提示改变用户uncertainty可能影响增量QoR；没有启用忽略用户uncertainty的选项，没有改变验收时钟或抖动，也没有新增例外。最终报告核对原始约束。32-745提示较大负裕量不适合post-route收尾，实际0收益已保留。
- 只读DCP诊断22:59正常退出，全部5698个负setup端点与最终summary数量一致；最差L5 MAC末级valid→窗口FIFO count[2]/D（-0.517），其次同源→本地读指针R（-0.511）。负端点中1896个为L5窗口存储、1422为L5 MAC、1329为L5窗口复制issue、749为L5 FIFO；这些是端点分布，不是TNS贡献比例。MAC-valid→窗口FIFO WE直接定时路径仍为0，不能由该局部消除推断全局时序通过。证据`rom_inc_diagnostic`。

## 用户要求今日收尾暂停

用户要求现有工作完成后停止，之后再继续。直接队头B-only整帧Golden、ROM3增量实现和必要只读诊断均正常退出并归档；正常用户进程查询确认没有Vivado/XSim/xelab/xvlog残留。本轮公开工程记录按原授权保存到试验分支；暂停不代表200MHz目标完成。已准备的直接队头重新布局实现尚未启动，等待用户以后明确恢复。用户理解仍待讲解/待本人复现。

发布检查增加“所有归档文件必须存在于Git index且原始字节一致”，限定本轮evidence目录解除旧日志/工具目录忽略规则，确保选定日志和journal副本能够随提交恢复。实际执行缓存、大型DCP、EXE/DLL和私人记录不在该证据目录，仍不上传。

## 工具与保存

- try1在受限用户会话初始化Vivado用户组件失败，未读DCP；日志保留。try2使用正常用户会话后成功运行。
- V:先核对无未知映射再建立；受限会话映射不跨调用共享，正常用户会话可复用已核对映射。
- `maxThreads=2`，外部Python使用`-I`；新实验目录拒绝覆盖，输入/脚本/报告/DCP均保存哈希。
- 原有未提交改动、旧证据、150 MHz发布候选`6cc8ea4`保持；本轮不处理C正式分支或主分支。
- 当前阶段仍为预录连续多帧→FPGA超分→PC播放；助手工程结果不等于用户已理解或亲自复现。
