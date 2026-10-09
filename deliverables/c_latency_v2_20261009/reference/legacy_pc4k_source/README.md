# 新通信BIT：连续4K生成和内屏缩放测量补充包

> **C 修复实测状态：主包 Natural2 两帧和 Natural16 十六帧板测及独立原始审计通过；PC4K RuntimePreflight 通过。** 2026-10-08 的 PC4K 五秒短测未通过：33/150 帧在 30.34 秒内完成，已完成帧的 4K Golden 对比均零差异，端到端速率约 1.09 帧/秒。板端回传验证耗时中位数约 0.85 秒/帧，交付中位迟到 13.63 秒；有限运行截止后其余输入槽未尝试，未完成帧的最终 ACK 被扣留。独立审计器要求完整测量，故未审计此失败前缀。4K30、内屏/面板刷新和电气验收仍未通过或声明。包内 B 原始检查记录仍绑定 B 的原始文件哈希，不作为 C 修复验证结果；正式 video 许可仍为 false。

配合本候选中的 `main` 主包目录使用。此补充包从 B 的 PC4K v3 补充包派生，不含BIT。主包和补充包必须作为同一候选配对；不能使用旧 B 三槽 BIT 的捕获。

解压例如 `E:\COMM_PC4K_20261007`。Python环境需已有numpy、opencv-python、Pillow、Tk；CUDA入口另需已有可用CUDA版PyTorch。C电脑配置尚未核实，CPU入口必须显式选择，不自动代替CUDA。

文件预检不导入GPU依赖，不开UART/JTAG/socket：

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -B 'E:\COMM_PC4K_20261007\live4k.py' --package 'E:\COMM_150_20261007' --files-only --out-dir 'E:\COMM_PC4K_20261007\preflight_新attempt'
```

正式执行前确认主包保存的网卡/IP/永久邻居未变化，UDP6102空闲。以下命令使用主包实际打印的Natural16启动捕获路径；目录必须是新的attempt。程序不修改网卡、不执行JTAG、不写Flash，按真实身份/启动/PHY检查后才创建socket。保留主包网络快照并记录是否变更。

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -B -u -X faulthandler 'E:\COMM_PC4K_20261007\live4k.py' --package 'E:\COMM_150_20261007' --startup-capture-report 'E:\COMM_150_20261007\attempts\实际Run目录\startup_for_16\REPORT.json' --backend torch-cuda-f64 --seconds 300 --fps 30 --out-dir 'E:\COMM_PC4K_20261007\live_新attempt'
```

这是9000个目标输入槽，16份冻结预录输入/Golden循环、唯一frame_id。迟到的槽继续用自己的ID记录，不降低实际提供速率或重复显示掩盖失败；队列暂满最多等待500ms，此前不发最终释放ACK；超时拒绝该帧，等待/迟到照实记录，不扩大队列。最多约610秒执行窗口，再受单帧10秒截止约束。启动时逐源建立独立整数4K参考并校验实际后端；每个新输出仍完整重新计算和逐像素核对。1280×720是默认缩放画布，可指定预览尺寸；记录实际缩放提交尺寸，不宣称面板全画面原生4K显示。

原始UDP报文全部保留，9000帧的正常流量约几十GB。准备阶段检查约83GB空闲余量（3倍正常流量和2GiB）；日志SHA和审计使用流式读取。关闭预览会停止后续输入并排空已接收任务，失败证据保留。CPU后端参数为 `--backend opencv-f64`，性能单独记录。

中途失败、队列拒绝或关闭预览后，未获最终确认的帧会留在板端；先保留并打包原attempt。下一次测量通过主包 `-Mode Run` 重新临时JTAG、启动捕获及Natural2/Natural16，使用该次真实Natural16 REPORT；不要用旧捕获绕过仍活动的帧/会话。

结束后独立审计：

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -B 'E:\COMM_PC4K_20261007\audit_live4k.py' --package 'E:\COMM_150_20261007' --run 'E:\COMM_PC4K_20261007\live_实际attempt' --out-dir 'E:\COMM_PC4K_20261007\audit_新attempt'
```

`measurement/RESULTS.json`分别记录协议完成、4K生成、应用缩放提交在目标窗口中的帧率、实际输入到输出排空跨度、每秒计数、帧间隔、延迟、迟到/未尝试/队列拒绝/重复与缺失ID。全程原始1080p回传可独立重审Golden/CRC/证明/释放；每帧4K运行时全像素核对，事件SHA可对独立参考复核，只保存末帧完整4K和应用画布PNG，不保存所有4K raw。应用提交不等于面板刷新，数值正确和实测速率分别验收。收尾fsync/整日志SHA在输出排空后执行，另记耗时与失败，未通过不能作为完整证据；它不计入运行跨度。Tk/Pillow实际首张准备画面在网络/计时前预热，明确不计帧。完成测量不自动将整机4K30标为已达成。

将完整attempt、独立audit、主包原始身份/网络快照和本补充包SHA一起回传。较短试跑可用 `--seconds 5`；这些是测量入口默认值，未将5分钟阈值登记为新的生效任务书要求。本机工程检查使用内存传输，不证明实板帧率；电气UNVERIFIED、正式video许可false保持。

推荐通过补充包PowerShell入口执行，它沿用主包完全相同的网卡检查，并使用原诊断helper保留30秒调用栈及首sendto前120秒监督：

```powershell
& 'E:\COMM_PC4K_20261007\run_live4k.ps1' -Mode Run -CommPackage 'E:\COMM_150_20261007' -Python 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -StartupCaptureReport 'E:\COMM_150_20261007\attempts\实际Run目录\startup_for_16\REPORT.json' -Backend torch-cuda-f64 -Seconds 300 -Fps 30
```

随后用相同入口的 `-Mode Audit -RunRoot '实际打印的attempt路径'` 复核，`-Mode Pack -RunRoot '同一attempt路径'` 打包全部证据，失败也Pack。Preflight可用 `-Mode Preflight`，不执行硬件/网络操作。每次入口均填上同一 `-CommPackage` 和实际 `-Python`；Run前后保存真实网卡快照，不改配置。只把真实启动捕获及完整审计通过后的测量解释为本BIT实测。


本补包v2精确绑定2026-10-08通信v3，不能配之前通信v2；请整包换新目录。
文件预检也通过外部120秒准备期限及30秒定时栈，Python尚未进入入口时仍留进程记录。
诊断工具哈希用.NET核对，不再依赖Get-FileHash模块自动加载。
默认期限/采样参数保留；缩短参数仅用于助手离线故障注入。
BIT、计算、PC4K算法和参考保持，主包或补包报错后先Pack，按上文恢复新启动/会话。


## 2026-10-08 主机修复通信v4（精确配对PC4K补包v3）

本轮接入经过离线复核的C主机候选：ACK等待按1ms实际截止限制recv超时，重复包不再无条件触发单项ACK，已退出保留窗口的旧proof不混入新批次。数据CRC、身份、整帧Golden和队列接纳后才释放整帧的约束保留。
Python启动器在执行前即归入本次Windows Job；真实bootstrap工作进程通过归属核对确认。CPU/I/O和首sendto标记采用工作PID，超时及退出清理本次Job所有后代。Pack要求启动器、工作进程及Job均已停止；日志未闭合时拒绝打包。默认120秒准备/首sendto期限和30秒栈保持。sendto返回只代表OS接受数据报。
本次BIT、RTL重发器、模型、150MHz、pause=0、MEM、Golden和PC4K插值算法未改。RTL仍是全局1ms重发计时；是否需要每包年龄抑制由本轮实板原始输出决定。本机测试不替代实板验证，不保证4K30。
本轮先Preflight，再全新Run，默认OutputWindow128；成功或失败都保留并Pack实际attempt。Natural16稳定和原始审计通过后才接PC4K五秒短试，再Audit/Pack；短试不通过不做300秒长测。失败后重试先重新JTAG及取得对应启动捕获。

本轮新增上板前环境自检：在同一实际Python环境执行`run_live4k.ps1 -Mode RuntimePreflight -CommPackage 主包目录 -Python 实际Python路径 -Backend torch-cuda-f64`。它只用冻结Golden验证全部16帧独立4K参考、CUDA/依赖和Tk准备，记录解释器/库版本和GPU；不JTAG、不打开串口或网络socket，不需要启动捕获。CPU后端须显式选择opencv-f64。CUDA失败不自动换CPU。准备图属于Golden自检，不算板端测量帧。RuntimePreflight成功后才上板；失败可Pack其实际attempt并先定位环境。

## 2026-10-08 C 修复实板测量结果

已用与主包配对的当前BIT、Natural16 本次JTAG后的启动捕获和 `opencv-f64` 后端执行 `-Seconds 5 -Fps 30`。入口启动并收到了板端数据，但受有限运行截止保护而失败：33/150 槽完成，实际跨度30.340秒，116槽未尝试；完成帧4K参考逐像素零差异，`receive_to_4k_ms` 中位数29.414、`receive_to_preview_ms` 中位数43.869、交付迟到中位数13.634秒。失败时consumer停止并扣留最终帧ACK，以避免释放未完成的帧。此记录不能证明PC4K阶段通过，也不能证明整机4K30。

这次独立审计返回 `FAIL_PRESERVE_RAW_AUDIT`，因为正式审计入口的首个条件要求 `REPORT.status == COMPLETE_MEASUREMENT`；本次状态为 `FAIL_PRESERVE_EVIDENCE`，所以没有执行失败前缀的原始协议审计。不得把运行中已生成的4K参考匹配当作完整的独立审计通过。完整原始证据归档：`attempts/Run_20261008T1545126667018Z_evidence_20261008T1547505657561Z.zip`，SHA-256 `4bf20a05e510b845fe14485c2416ba3ea6499fff2359c75801f1c8277e88b30c`。重试前须照上文重新运行主包完整 `Run`，取得新的 Natural16 启动捕获；不要复用这次会话。


协议截止改用Windows高精度perf_counter/QPC；原monotonic在本机Python3.11的GetTickCount64精度为15.625ms，不能判断1ms ACK目标。提前接收超时只继续服务ACK，不计作输入/控制失败。RuntimePreflight记录本机实际时钟实现和精度。1ms是软件目标；Windows调度与recv实际唤醒仍可能晚于它，不能保证实板每次1ms送达。Natural2原始报文显示有输出重复包；本次修复只处理主机跨帧 ACK 定时器，没有修改 RTL 重传算法。后续是否需要按包年龄抑制需结合 Natural16/PC4K 实测继续判断。
包内原有proof保留为历史来源；本次修复验证以随交接单标注的B新验证收据为准。旧proof不作为新主机代码或新实板通过证据。
