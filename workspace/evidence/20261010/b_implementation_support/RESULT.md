# C 给 B 的实施前补充材料 · 2026-10-10

本次只整理既有证据与真实变更；没有新增板测、Vivado运行、PHY配置、网卡配置或外部发送。代码和时序实施由 B 继续推进，输入扩窗材料用于收益核算，不作为本地实现的前置阻塞。

## 1. 输入扩窗已测，完整证据可提供

同一 BIT cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5；输入 batch1、输出窗口128、nonblocking/sample16。正式四轮平衡对照，每窗口64个Natural16帧加8个Natural2帧；筛查另计，不混入正式分布。20个成功case共360帧，746,496,000个输出Golden字节零差，逐case正常零重复门槛通过。首次窗口16的JTAG连接失败在进入Natural/网口测试前发生，原失败Pack保留。预检与fixture不计板测。

| 输入窗口 | 正式Natural16 + Natural2帧 | 整帧中位 ms | Natural16 P95 ms | 实际协议循环 fps |
| --- | ---: | ---: | ---: | ---: |
| 16 | 64 + 8 | 76.266 | 78.519 | 12.849 |
| 32 | 64 + 8 | 55.936 | 57.597 | 17.409 |
| 64 | 64 + 8 | 46.274 | 47.552 | 21.224 |
| 128 | 64 + 8 | 45.251 | 54.688 | 21.186 |

中位数是四个case各自帧中位数的再中位数；fps按实际protocol_loop累计时间计算，不能用中位数倒数替代。整帧指标沿原LAB定义，不能称为纯FPGA计算时间。推荐input64候选，尚未改变冻结默认。

完整大包：C_TO_B_INPUT_WINDOW_RESULTS_20261010.zip；字节数 1014080074；SHA256 08a733d466cf99cb3d8f4ecda9fefd6675f6221aba156910c322bccbb933f1ed。其中 results/balanced_ab_01/INDEX.json、results/screening_01/INDEX.json、results/screening_02/INDEX.json 给出原case；evidence/ 存放23个原Pack，包括失败及预检。补包的 evidence/CASE_ARCHIVE_INDEX.json 提供每case到原ZIP成员、SHA、Golden审计及正常零重复Gate的可携带索引；本轮重新核对23个Pack SHA，仅复制历史审计，不冒称重新做板测或重新运行Golden算法。零重复范围为捕获PC UDP记录，不证明物理报文/RAM写次数。参考Golden B已有；完整原始输出、参考身份及Golden检查在原Pack。

64长期/PC4K单独保存：C_INPUT64_LONG_PC4K_FOLLOWUP_20261010.zip，2168021406 B，SHA256 c9860483b54ae235153656742ec16d09679e609a68f14459a748bb90db9dbe53。512个Natural16和64个Natural2、两次主机失败及一次用户中断均保留；这是可选追加包，不并入四窗口对照，也不是32次连续无失败启动。

## 2. I/O 数值依据为条件性范围，物理电气未验证

现有外部XDC注释给出RX偏斜范围[-0.30,+0.45]ns、TX[-0.34,+0.40]ns，PHY RX setup/hold>=1.2ns、TX0 pin window[1.0,2.6]ns；这是冻结约束采用的条件性假设，当前没有补充的板上偏斜/眼图/PVT实测资料或独立确认的完整PHY模拟延迟包络。数值与来源逐项记录在 io/CONSTRAINT_BASIS.json；原XDC、时钟/IDELAY/PHY源码和原build Tcl附在 io/frozen_sources/。

保存的UART启动状态确认逻辑RX1/TX0：page0x0d08，RX reg0x15 bit3=1，TX reg0x11 bit8=0；例中rx_actual=0x0019、tx_actual=0x0009，详见 io/observed/。这证明配置读回，不证明模拟延迟数值、时钟—数据偏斜或板级电气通过。RX数据IDELAY为10 taps（rxd1=11），参考200MHz；原约束phy_rx125采用7.2ns条件周期，rise/fall input max分别2.49/3.21ns、min0.90ns；TX output max1.40ns、min-1.74ns。物理I/O保持UNVERIFIED。数字时序、UART配置、协议/Golden及屏幕刷新分别引用；原冻结BOARD_PENDING文本不改，由后续证据补充。

## 3. 变更边界与差异

当前冻结V2交接版：无变更，本轮逐文件核对166份runtime负载与发行清单一致。收到的B输入扩窗main：无变更，167份发行负载与原ZIP逐文件一致。RTL/XDC/PHY配置/MEM/Golden/B主机程序没有在这些发行树内修改。核对记录在 changes/FROZEN_V2_RECHECK.json、B_MAIN_RECHECK.json。

C另建了两个独立跨帧RTL候选，因此不能对整个C工作区笼统回复“无变更”。候选有物理基址/逻辑计数、信用/三上下文、收包/控制/回复/TX仲裁及定向时序拆分；有修改文件和新增模块。已把各候选相对冻结RTL的差异、精确文件字节和SHA放入 changes/，入口CHANGES_INDEX.json。候选未合并、未上板，HELLO/STATE/CREDIT/主动更新尚未全部接通；最新综合包装器因目录错误判失败，P&R按用户要求停在Global Iteration0，无最终route签核、新BIT或实测延迟收益。不能将此候选结果当作B已交付实现，也不能用它替换当前基线。

C主机侧新增外部编排/选择性诊断包装器，另有独立PC4K派生补包（绑定64/batch1/output128）；对应新增源码/差异/SHA单列，B原main保持不变。PC4K算法及参考保持原版。资料不包含重复整工程、模型MEM、完整Golden或工具安装环境。

## 后续交付与验收口径

B的新BIT交C前，需完成真实CNN三帧/网络Golden和完整物理顶层布局布线审查；GMII OOC诊断不能替代RGMII完整顶层。150MHz原生setup/hold、CDC/DRC、外部条件性约束和未验证项分别说明。单帧延迟与连续帧周期分别报告，实测与估算分别标明。C收到后独立复核身份与证据，再进行有授权的板测对照。
