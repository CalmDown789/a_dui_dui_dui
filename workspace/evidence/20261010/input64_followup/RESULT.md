# 64窗口长期、当前BIT PC4K及长尾诊断结果

2026-10-10。已完成现有材料可执行的长期、PC4K配对及主机长尾诊断。跨帧正式设计评审仍缺B的 `SINGLE_RAM_CROSS_FRAME_DESIGN.md` 原文；接口事实预审见 CROSS_FRAME_PRE_REVIEW.md。整机4K30未实现，物理I/O仍UNVERIFIED，真实屏幕刷新未测量。

固定当前BIT `cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5`，input64 / batch1 / output128。B主包及冻结RTL/MEM/BIT/DCP字节保持；前序A/B交付、阶段包和全部失败/中断原index不覆盖。

## 长期验收

32个完整原Run来自20个原成功case加12个新补测case，共512个Natural16、64个Natural2、1,194,393,600个Golden字节零差。全部逐case正常零重复门槛通过，正常帧重试/重复/invalid/wrong source为零。每个完整Run包含2次JTAG/启动，64次成功启动属于这些已完成case；失败和用户中断另外保留。帧外HELLO重试6次单列。

512个Natural16描述统计：整帧中位47.485ms、均值47.913ms、P95 52.521ms、最大60.896ms；按实际协议循环累计时间为20.479fps。仅新12个case为20.163fps。前20个case在SyncDisk运行时完成，后12个在服务停止及无注入的新父进程下完成；本统计环境混合且无同期基准，不能据此量化停SyncDisk的性能收益。

原批次第21个case在无板卡I/O前bootstrap超时；第二批首case在Smoke离线审计停滞，保存原生栈/转储后失败及原Pack保留；隔离后的另一个启动被用户明确中断，没有Natural帧，不计为失败或成功验收。停止收据及C前缀快照见 USER_STOP_RECEIPT.json、interrupted_prefix_01/。不是32次连续无失败启动。

后一次主机停滞的实证见 recovery_stall_01/DIAGNOSIS.md；前一次根因尚未证实。本轮依用户最新要求保持SyncDisk停止；不修改其自动启动配置。程序无注入、8次新启动检查、32次隔离无I/O检查、13项编排夹具及3次原入口Preflight/Pack证据均保留。没有将环境隔离写作B原程序修复。

## 当前BIT的PC4K配对

正式配对状态：PASS_CURRENT_BIT_PC4K_AND_DIAGNOSTIC_REVIEW。C派生补包显式绑定64/batch1/output128，原算法和独立参考字节保持；从新的完整原Run启动捕获接入，Run/Audit/Pack分别保存，不能复用旧BIT历史数据。

150个输入槽全部协议完成、4K逐像素参考零差、应用预览提交完成。实际测量跨度7.304秒，生成4K/预览提交按实际跨度为20.536/20.536fps；名义5秒窗口内分别为20.600/20.400fps。150个槽以30fps目标提供，完成150帧不等于实际达到30fps。最后Tk预览图像像素与对应4K缩放结果零差，仍不认证面板刷新。PC4K原始审计duplicate/invalid/wrong source：[(0, 0, 0)]，单独引用。

## FINAL前逐调用诊断

128及64各16帧附加诊断Golden/原始协议审计通过，另有3个新完整Run的54个Natural帧正常门槛通过。选择性运行包装器记录调用、文本write/flush、非durable checkpoint及GC的精确时间；保留原CRC/Golden/FINAL约束。包装器会扰动时间，不与正式A/B混算，不把嵌套GC和外层调用耗时相加。

各诊断中最长末输出RX日志至FINAL TX日志间隔：

- window128 frame1：请求前间隔2.538ms，FINAL请求至ACK 1.377ms；其中完整落在间隔内的GC事件0个。调用wall/CPU明细见 FINAL_STATUS.json 和 FOLLOWUP_REVIEW.json。

- window64 frame1：请求前间隔2.044ms，FINAL请求至ACK 1.217ms；其中完整落在间隔内的GC事件0个。调用wall/CPU明细见 FINAL_STATUS.json 和 FOLLOWUP_REVIEW.json。

随后增加一组仅装GC callback的轻量采样：16帧原始Golden审计通过，记录到1次GC，墙钟耗时0.1326ms；输出末包RX至FINAL TX最大2.7602ms，区间内GC重叠0次。它没有复现原长期样本12.3267ms的最长间隔；因此当前采样未支持GC与该长尾同时发生，也不足以排除其他批次的GC影响，根因仍未确定。

轻量采样首个包装器试次因本地输出目录重复创建在网络I/O前退出，原日志保留；修正后在独立结果目录完成以上采样，不计入板测成功/失败case。

以上GC仅为相关性观察，不能直接作因果归因。既有长尾仍不能从PC日志归因为NIC/USB/物理链路；最终durable fsync位于protocol_loop之后，不分配给帧release。

## 证据与下一步

入口 FINAL_STATUS.json、long_review_01/RESULTS.json、FOLLOWUP_REVIEW.json、GC_LIGHT_REVIEW.json；原成功/失败/中断索引分别在 long64_01、recovery12_01、recovery12_isolated_01、recovery12_resumed_01。原Run/Pack、正常门槛、原始报文、逐帧Golden及诊断trace均保留。最终证据包收录原Pack及明确标注的C中断前缀，校验收据绑定CRC、逐文件SHA和ZIP SHA；转储只保留本地并以SHA引用。

下一步先取得B跨帧设计原文，评审单RAM信用、消费/回收水位、地址回绕和帧所有权；不直接删除RUNNING保护。RTL候选需重新仿真、资源/时序审查、BIT/DCP绑定及板测/PC4K。冻结默认不自动提升，未同步/合并GitHub或发送材料给B。
