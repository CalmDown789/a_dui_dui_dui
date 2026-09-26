# 成员 B：200 MHz 优化收尾与下次交接

日期：2026-09-26；本轮按用户要求收尾，不再新增优化。所有已启动的主候选实现、物理收尾和所选功能回归均已结束。

## 结论

**200 MHz 尚未达标。** 原5.000 ns约束下最高WNS为−0.162 ns，最低+0.100 ns目标仍差0.262 ns；+0.250/+0.400 ns同样未达成。

下次建议从 **V1 nominal / `pipeline000`** 继续：WNS −0.164 ns、TNS −7.523 ns、226个setup违例端点、WHS +0.036 ns。最高WNS记录只比它好0.002 ns，但TNS为−45.955 ns、813个setup违例端点、WHS +0.013 ns，因此保留nominal为主要继续基线，同时保存最高WNS检查点。

**V6完整测试已做完，功能正确，最终时序比V2差，本轮不采用。** 它解决了算术DSP级联，但最差路径转到C输入ROM和L5控制布线；不能用局部结构改善推断整网时序改善。

150 MHz的WNS +0.492 ns结果和C上板交接已发布于`6cc8ea4173d2a720f741e80b7cbd9279558ee93a`。C继续按[150 MHz上板交接](MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md)验证，200 MHz实验不替代该版本。

## 完整布线结果

Vivado 2025.2，`xc7a200tfbg484-2`，真实五层B+C外壳+A bank16输入ROM。下表均为恢复原5ns约束后的结果；全部THS=0、hold非负、脉宽检查通过、可布线网络完整连接、route errors=0。

| 版本 / 证据目录 | WNS ns | TNS ns | setup违例端点 | WHS ns | 决策 |
|---|---:|---:|---:|---:|---|
| 原RTL，NetDelay / `setup030` | −0.613 | −939.145 | 7,800 | +0.036 | 对照 |
| **V1 nominal / `pipeline000`** | **−0.164** | **−7.523** | **226** | **+0.036** | **下次主要基线** |
| V1，加0.300ns搜索压力 / `pipeline030` | −0.312 | −68.680 | 1,153 | +0.013 | 保存 |
| 上行再做无额外压力的物理收尾 / `postroute_v1_000` | −0.162 | −45.955 | 813 | +0.013 | 最高WNS记录，保存 |
| V2 / `pipeline2_030` | −0.481 | −350.776 | 3,104 | +0.050 | 未采用 |
| V2物理收尾 / `postroute_v2_000` | −0.403 | −220.478 | 2,126 | +0.050 | 未采用 |
| V6 / `pipeline6_030` | −0.638 | −394.339 | 3,742 | +0.023 | 未采用 |

所有证据目录位于`member_b_evidence/timing_200_20260926/`，机器可读汇总为`results_index.json`。历史默认200MHz结果−0.719/−2842.755 ns仅作旧对照，未作为本轮新跑结果。

### 资源与路由

| 实现 | LUT | FF | RAMB36/18 | DSP | 完整可布线网络 |
|---|---:|---:|---:|---:|---:|
| 原RTL setup030 | 29,196 | 48,911 | 226/8 | 394 | 76,670 |
| V1 nominal | 27,994 | 49,170 | 226/8 | 394 | 73,987 |
| V1 setup030 | 28,012 | 49,275 | 226/8 | 394 | 74,134 |
| V2 | 29,477 | 49,343 | 226/8 | 394 | 73,235 |
| V6 | 29,952 | 49,729 | 226/8 | 396 | 73,171 |

物理收尾资源详见各目录`reports/after_restored/utilization.rpt`，不把基线资源直接当作收尾后资源。

### 约束与证据口径

- `setup030`仅在布局布线时额外增加0.300ns setup uncertainty；最终恢复UU=0再验收。同一个物理结果恢复前后WNS恰好相差0.300ns，hold不变。
- nominal全过程额外压力为0。最终周期5.000ns，自动uncertainty约0.069ns，TSJ 0.071ns、DJ 0.118ns、PE 0保留。没有降低频率、删除抖动、增加false path或multicycle来取得数字。
- 每个完整实现核对66项启动输入哈希、35份staged ROM与来源一致，保存真实B层次、XDC、路由、时序和资源报告。
- post-route收尾从精确DCP副本开始，输入/输出DCP、脚本和每份报告都有哈希；保持周期、自动抖动、hold约束和DRC级别，额外setup压力为0。V1/V2两次均未触发route repair。
- 原始文本日志以`*.log.txt`入Git；实验中的`unit_work/`、DLL、WDB、EXE和DCP不入Git。二进制DCP保留在本机`_synth_bc/`，其哈希在证据中。

## RTL组合与功能验证

| 版本 | 内容 | 实际验证 |
|---|---|---|
| V1 | 固定bias提前进入36位累加；L5两槽partial缓冲；条带两拍读；完整Q31乘积寄存并同步metadata | 单元、三帧背压、四组小图Golden、完整帧、C外壳全部通过 |
| V2 | V1基础上增加L3 partial缓冲、条带显式4096×8分片并使用BRAM输出寄存、post固定低位读出后移位 | 单元、小图、完整帧、C外壳全部通过 |
| V3 | 增加PReLU结果流水级 | 单元/小图通过；DSP MREG仍0、级联未改善，仅短综合探针，无长实现 |
| V5 | 显式PReLU高/低部分积 | 单元/小图通过；L1–L4的12个相关DSP均MREG=1/PREG=1，最差转为Q31级联；无长实现 |
| V6 | V5基础上将Q31拆成四个独立部分积，再用两级CSA和一次64位加法重建 | 单元、小图、完整帧、C外壳和完整实现全部完成 |
| SRL备选 | 仅改变L5宽FIFO存储结构 | 单元及七帧短图/背压通过；整帧20:41主动停止以优先主候选，不算整帧PASS |
| `prelu_signed_round`草稿 | PReLU signed-floor/guard/sticky备选 | 仅准备，未执行、不采用 |

V6综合确认42个后处理DSP的PCIN全部接地，完整Q31保留448个FDRE。六scalar和五shared单测包括完整48/64位乘积、正负极值、invalid保持、流水线复位和1,094项INT64舍入探针。其综合WNS +0.072ns只属于综合估算，最终布线为−0.638ns。

### 完整帧结果与吞吐代价

| 路径 | 输出匹配 | 仿真周期 | 相对原版 |
|---|---:|---:|---:|
| 原版历史基线 | 2,073,600字节 | 4,699,406 | 基准 |
| V1 | 2,073,600/2,073,600 | 4,959,092 | +5.53% |
| V2 | 2,073,600/2,073,600 | 4,959,093 | +5.53% |
| V6 | 2,073,600/2,073,600 | 5,218,778 | +11.05% |

三版完整帧均为960×540→1920×1080：X=0、17次stripe_last、1次frame_last/完成、握手违例0。V6比V2多259,685周期（约5.24%）。这是`out_ready=1`下B数据通路的仿真周期，不是板上UART或多帧系统帧率。

完整功能证据：`sim_pipeline200/`、`sim_pipeline200_v2_short/`、`sim_pipeline200_v2_full/`、`sim_pipeline200_v6_short/`、`sim_pipeline200_v6_full/`。C外壳TB用stub生成数据，验证UART/条带控制；B完整帧TB不覆盖C输入ROM读通路。两类证据不能互相替代。

## 下次从哪里继续

### 推荐保留的实现

- 主要基线：`_synth_bc/acc36_realrom_200_member_b_pipeline0000926_ascii_ramdecomp/postroute.dcp`。
- 最高WNS记录：`_synth_bc/postroute200_v1_pressure000_try1/postroute.dcp`。其基线是V1 setup030，目录名中的000仅表示收尾阶段无额外压力。
- V6保留：`_synth_bc/acc36_realrom_200_member_b_pipeline6_0300926_ascii_ramdecomp/postroute.dcp`。不从V6直接覆盖主要基线。
- 启动输入见相应`reports/launch_source_manifest.json`；Git中的对应证据目录保存相同输入清单。读取已有DCP即可分析，不必重复跑已验收的整帧或重装环境。

V1 nominal原入口：

```powershell
# 已确认V:映射到本仓库时；重跑会耗时较长，下次优先读取现有DCP。
& 'F:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -nojournal -source 'V:/experiments/timing_200_20260926/synth_200_pipeline030.tcl' -tclargs impl acc36 ascii ramdecomp nominal
```

后续若要重新实现，应先建立新stage以保留本轮检查点，不直接覆盖这些已归档结果。物理收尾入口`postroute_finish/prepare.py`会拒绝覆盖stage；`finish.tcl`保持原5ns并自动核验前后setup/hold/路由。

### 实际剩余瓶颈

V1 nominal最差路径：L5 pad的y寄存器→窗口BRAM EN，slack −0.164ns，逻辑0.799ns、布线3.926ns（83.1%）。其后有L3 pad→窗口BRAM数据−0.144ns、条带BRAM→读寄存器−0.139ns。最差100条样本中82条从L5乘加树valid寄存器出发，后续应按这些真实控制/窗口路径逐项判断。

V2最差路径为L5 active→宽FIFO写使能，布线占87.9%；V6最差为C输入ROM BRAM→bank选择→c2b_data_q，slack −0.638ns，其后是L5控制路径。V6的局部算术改善没有改善最终整网结果。最差100条只是样本，不能据其数量推断全部TNS的类别比例。

下次先检查主要基线的post-route报告，再决定局部复制、控制寄存或读流水方案。任何接口延迟/ready改变都需要重新做握手、复位、小图和完整帧Golden验证。当前不继续启动这些工作。

## 运行问题和保存边界

- 首次单元runner把XSim默认日志与stdout写到同一文件，造成PASS重复计数；分离日志后完整重跑通过，未放宽RTL判据。
- post-route首次入口在读取DCP之前遇到Vivado Python环境导致的`SRE module mismatch`；外部Python调用加入`-I`后，在新stage重跑完成。失败入口日志保留于`postroute_startup_failure/`。
- 所有预存用户修改及旧150草稿保持原样，保存核验为`PRESERVED_EXISTING_FILES_PASS`。本次只提交明确的200实验/证据/报告及交接更新。
- 实验XDC仍缺UART LOC/IOSTANDARD，9个输出没有output delay，原NSTD/UCIO级别被降低；因此这里不是板级签核。C必须补齐板级约束并恢复正常DRC级别后重新实现。
- 当前阶段仍要求预录连续多帧→FPGA超分→PC回传播放；ROM单帧Golden仅是检查点。摄像头/HDMI不属于本轮范围。
- 这些是助手工程验证，用户尚未亲自复现和解释新改动，理解状态保持待讲解/待用户复现。
