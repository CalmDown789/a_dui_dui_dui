# 独立重建入口

交付包需解压到新的短ASCII路径，例如`C:\fpga\obsfix`，不要覆盖C的原工程、冻结基线或任何已有attempt。本机实跑根目录是`F:\FPGA预选\c_obs_fix_20261005`，正常用户会话Q:映射该目录；本机安装`F:\Xilinx\2025.2\Vivado`，不是C历史R:路径。受限用户会话首次无法访问Q:及Vivado用户启动目录，改在经工具自动审批的正常用户会话运行后恢复；这是环境问题，无工具重装。

源码审查入口为`source_review`的独立本地Git提交与`results/repair.patch`，两处逻辑变化；真实构建C来自`candidate/multiframe`。固定B目录`b_fixed`保留42份原字节依赖（23份RTL含实际选源15份、19份参数ROM），身份见`B_VERIFIED_BLOBS.json`；综合真实选源以build.tcl为准。源码包里的固定依赖副本按6cc8ea4 Git blob验证，不可从新的B HEAD覆盖。如果需要自己的Git依赖checkout，应在另一新目录从原remote检出准确6cc8ea4173d2a720f741e80b7cbd9279558ee93a，并对清单逐文件原字节核对。

既有attempt的`build.tcl`是原实跑命令来源，`stage6_build_manifest.json`和`frozen_inputs.json`分别记录使用源和字节副本。独立重建新attempt由`scripts/prepare_impl.py`生成，使用同一C XDC、原物理策略、150/100对应MMCM参数和对应pause generic。完整综合与布局布线从源码开始；不导入旧原候选/基线DCP。自动派生时钟及器件jitter保持。先使用+0.300ns setup压力，最终只恢复原用户uncertainty=0.000ns。

在自己的PowerShell中填写已安装Vivado2025.2和Python3.10+实际位置，执行：

```powershell
$python = 'C:\实际Python\python.exe'
$vivado = 'C:\实际Xilinx\2025.2\Vivado\bin\vivado.bat'
& 'C:\fpga\obsfix\scripts\portable_bootstrap.ps1' -Python $python -Vivado $vivado -MHz 150 -Pause 0 -Attempt review01
```

另三个组合分别改`-MHz 100 -Pause 0`、`-MHz 150 -Pause 1`、`-MHz 100 -Pause 1`，各用新的Attempt。最多两份大型Vivado作业并行，每份maxThreads2；依据自己的内存再减少并发。脚本依次冻结输入、完整实现、门控、独立bitgen门控、BIT/LTX一致性检查；任一失败停止，不会为失败实现生成BIT。

`source_review/scripts/configure_observation_debug_ip.tcl`是可审查的生成配方，完整934位probe1=DATA，其他九探针维持DATA_AND_TRIGGER、深度1024、输入流水0。新实现使用包内对应XCI重新生成IP；不得替换为原TYPE0的失败配置。ILA的配置时钟元数据沿原配方150MHz保持可比，实际采样与计时来自顶层MMCM100/150MHz，最终clocks及LTX debug-hub频率须与实际组合一致。

回归入口：`candidate/run_alignment_sim.py controlled 新名称 --optimization 2 --clock-mhz 100 --wall-timeout 1800`与`multiframe 新名称`，150MHz改`--clock-mhz 150`，先在`candidate/toolchain.json`填写本机Vivado根目录。它们保留真实B、UART串行解码、Golden逐字节对拍和原始actual_frame*.mem。观察器自检也读取此toolchain：`scripts/run_observer_tests.py --attempt 自检新名称`；不要覆盖原结果目录。原测试命令、退出码、源哈希和返回已经附在对应原件中。sourcekit只含可迁移重建/读取入口；evidence/scripts还保留本机Q:路径的原执行、诊断和整理脚本供取证，不直接在C机器照抄这些本机启动路径。

各机器物理实现可能不同；新产物按新实测时序/DRC/路由门控签核，不能期待重新生成的BIT字节SHA必然与本包完全一致，也不能拿本机BOARD_READY代替新机器或实体板测试。

## 工具内部opt错误的已尝试恢复

本机100MHz pause=1首轮完整综合成功并保存`synth_setup030.dcp`后，`opt_design`仅输出空的`Synth 20-411`而退出。对应阶段没有布局或时序失败结论，原attempt保留。同源码综合DCP在新会话继续，必须记录其相同SHA与原综合日志来源；不要改RTL、覆盖原日志或盲目重跑长综合。

恢复命令示例（把两个attempt名替换为自己的）：

```powershell
& $python 'C:\fpga\obsfix\scripts\prepare_continue.py' f100_p1_review01 f100_p1_review02
if ($LASTEXITCODE -ne 0) { throw 'Continuation preparation failed' }
& $python 'C:\fpga\obsfix\scripts\freeze_attempt.py' f100_p1_review02
if ($LASTEXITCODE -ne 0) { throw 'Continuation freeze failed' }
& 'C:\fpga\obsfix\scripts\portable_run_prepared.ps1' -Python $python -Vivado $vivado -StageName f100_p1_review02
```

portable_run_prepared会记录真实命令与退出码，并在全部实现门控通过后才进入独立bitgen和BIT/LTX核对。接续的综合报告是原件复制，`continuation_input.json`明确来源和同SHA；不宣称重新实跑了综合。

## 150MHz余量不足时的本轮物理修复配方

本轮150MHz pause0首次完整源码流名义WNS-0.141ns、26端点，集中于帧头解析至错误计数器CE。接续其本轮新源码postroute DCP，增加一次布线后AggressiveExplore，在+0.300ns压力下再用原NoTimingRelaxation布线；最后恢复原0.000ns用户uncertainty，保留jitter。实际名义WNS+0.404ns，压力+0.104ns，hold+0.022ns，pulse+2.203ns。没有RTL修改、新例外或时序门槛放宽。

若自己的完整实现同类失败，先保留原setup/hold/DRC/route报告和collect_impl写出的失败结果，然后使用新attempt名：

```powershell
& $python 'C:\fpga\obsfix\scripts\prepare_postroute.py' f150_p0_review01 f150_p0_review02
if ($LASTEXITCODE -ne 0) { throw 'Postroute preparation failed' }
& $python 'C:\fpga\obsfix\scripts\freeze_attempt.py' f150_p0_review02
if ($LASTEXITCODE -ne 0) { throw 'Input freeze failed' }
& 'C:\fpga\obsfix\scripts\portable_run_prepared.ps1' -Python $python -Vivado $vivado -StageName f150_p0_review02
```

该配方源DCP必须由自己的修正源码完整实现得来，脚本检查源身份与器件/时钟/层级；不能导入原失败宽触发候选或旧基线DCP冒充修正源码实现。每台机器仍以自己的实际门控结果为准。
