# C 新观测版本操作指南（实体操作尚未执行）

只对`T5_delivery.json`列为BOARD_READY的频率/暂停组合操作。它们的BIT、LTX、源码和后布线报告各自绑定。该指南和读取脚本已离线检查；JTAG/VIO/ILA实读及实体UART验收仍是C的T6，不把离线实现记为BOARD_PASS。

## 1. 镜像身份和可回退准备

1. 对照交付索引核对所选目录的BIT/LTX SHA256。PowerShell命令：`Get-FileHash -LiteralPath '实际完整文件路径' -Algorithm SHA256`。不要用另一个频率或暂停版本的LTX。
2. 先保留已通过的原多帧基线：100MHz BIT SHA `524f72bc8ca01388f7305dbb02c48d5f1c68e1abe51900ce6c3738e667b80c3c`；150MHz SHA `93dd60cffbefa43f6ab9f49697ff1d3f1ab6657445d01552c88842b6bc0760f6`，各9,730,787字节。本工作区原件在`.artifacts/c_handoff_audit_20261004/supplement_d6b13e6/baseline_raw_board.zip`；C自己冻结基线目录也保有原件。回退时重新JTAG配置对应基线BIT，清除新LTX关联并复位，复用原PC采集流程。本任务不改Flash。
3. 板卡仍为ACX750/xc7a200tfbg484-2；引脚/电压依据原完整C XDC，未改。保持原921600 baud、8N1输入/回传协议。先关闭其他占用串口程序。

## 2. 配置正确BIT与LTX

在Vivado Hardware Manager中连接实际板卡，并确认目标。选择交付索引中的BIT和同目录LTX后Program Device。可以在已连接且已选择正确device的Tcl控制台执行：

```tcl
set dev [current_hw_device]
set_property PROGRAM.FILE {C:/实际交付目录/该组合/c_board_150mhz.bit} $dev
set_property PROBES.FILE {C:/实际交付目录/该组合/c_board_150mhz.ltx} $dev
program_hw_devices $dev
refresh_hw_device $dev
get_hw_vios
get_hw_ilas
```

以上路径由C替换为实际所选组合（100MHz文件名对应100）。保存JTAG器件身份、配置日志、两个文件SHA。核对一个`u_obs_vio`、一个`u_obs_ila`；VIO输出初值应为00，即槽0、暂停0。硬件不匹配时先停止并核对镜像身份，不能用旧探针继续读取。

四个组合复用相同ILA/VIO IP，因此UUID相同；同频率普通/暂停版本的LTX也可能逐字节相同。UUID或LTX单独不能辨认暂停参数，必须记录实际烧录BIT的SHA和所选组合，再关联该组合验证过的LTX。

## 3. 普通观测（pause=0）

先按原已验证流程执行四种不同输入，再执行连续16帧（4种输入各重复4次），帧号0–15，帧间不复位。用原C `capture_uart_frames.ps1`或已验证主机流程，而不是重新定义协议。实际COM口可由`[IO.Ports.SerialPort]::GetPortNames()`枚举，不盲用原COM3。

每个独立采集会话开始前，在空闲时复位一次，使loader期望ID与快照计数归零；四帧会话和16帧会话之间也需这一次空闲复位。**单个连续会话的帧间不复位**。原PC脚本从frame_id=0发起，不能在上一会话后直接以0开始而不复位。

PowerShell直接调用原脚本的完整参数形式：

```powershell
$captureScript = 'C:\实际冻结基线\scripts\capture_uart_frames.ps1'
$inputs = @('C:\实际素材\frame0_y_u8.bin', 'C:\实际素材\frame1_y_u8.bin')
$goldens = @('C:\实际素材\frame0_golden_y_u8.bin', 'C:\实际素材\frame1_golden_y_u8.bin')
& $captureScript -PortName 'COM实际编号' -InputFrame $inputs -ExpectedFrame $goldens -OutputDirectory 'C:\新的采集目录' -BaudRate 921600 -Width 960 -Height 540 -ReadTimeoutMilliseconds 120000
if ($LASTEXITCODE -ne 0) { throw '保存原始结果并查看对拍报告' }
```

正式验收将数组改为已冻结四种/16帧清单，保持输入Golden来源A98c82f3及逐帧身份哈希。源码包不替代C已有自然视频序列；pattern连续帧仍不自动成为自然视频验收。

采集完成、主机不再发送新帧后，从Tcl控制台加载和调用：

```tcl
source {C:/实际交付目录/scripts/export_vio.tcl}
obs_export {C:/新的采集目录/observation_raw.csv}
```

脚本按VIO输入端口编号及位宽选择四个数据分块（256/256/256/166）、valid、count，保持暂停0，逐槽选择并两次刷新核对稳定，原始CSV即使失败也保留，结束恢复原选槽。所有16个槽导出，valid=0槽可保留但不能当完成记录。这个硬件调用尚待C实跑；若工具对象属性/探针名称不符，先`report_property -all`查看并保存信息，不能猜测另一探针的值。

使用Python标准库恢复31字段：

```powershell
python 'C:\实际交付目录\scripts\decode_snapshots.py' 'C:\新的采集目录\observation_raw.csv' --map 'C:\实际交付目录\contracts\signal_map.json' --output 'C:\新的采集目录\observation_decoded.json'
```

核对每帧frame_id及槽对应关系、input_accept_count=518400、output_accept_count=2073600、stripe_last_accept_count=17、frame_last_accept_count=1、session_done=1、uart_final_idle=1、core_done_seen=1、core_busy_at_session_done=0；正常sticky错误/保持违例为0，16槽不覆盖，count=16，无第17帧时overflow应为0。64位周期/停顿字段完整保留。停止主机串口读取并不会自动制造B输出内部背压。

另外核对`uart_bytes_delta=2073600`、`frame_start_seen=1`。四帧独立会话结束时count=4，连续16帧会话结束时count=16；未使用槽的valid=0应保留原始导出。错误字段按源语义是复位以来的sticky/累计状态，不能写成本帧独占错误数。

周期数换算秒用`cycles/(实际MHz×1000000)`。`core_span_cycles`从frame_start到首次core_done，包含串口供数、等待与背压；`session_done_cycle`还包含最终UART回传完成。这些不是排除I/O等待后的纯CNN计算时间，也不能直接当实时视频帧率。各停顿字段有重叠，`joint_stall_cycles`是同拍交集，不把几个字段简单相加。快照保留原同拍取样语义，详见contracts/OBSERVATION_SPEC.md与T2_design.md。

## 4. 受控暂停（独立pause=1镜像）

必须重新配置交付索引中的pause=1 BIT及同一组合LTX，不能用普通版的时序或BIT代替。VIO仍默认00。沿普通步骤提交一帧，在B已开始工作、帧尚未结束时运行：

```tcl
source {C:/实际交付目录/scripts/export_vio.tcl}
obs_pause_once 200
```

该脚本将控制bit4置1，最多保持指定1–1000ms，finally释放bit4，保留低4位选槽；不是精确200ms周期计量，实际脉宽含JTAG操作延迟，以快照pause_request_cycles/forced_block_cycles为准。先用短暂停、人在现场；若未覆盖有效输出窗口而forced_block_cycles=0，此轮不能算受控暂停通过，应记录并重新选择有输出的时段。

ILA可在原小探针probe8（forced）=1或probe6（frame_done）=1触发，probe1仍采集完整934位，但**不支持对整个宽probe1设置匹配触发**。暂停释放后帧必须完成且UART Golden失配0；实际pause_request_cycles>0、pause_forced_block_cycles>0，两个hold violation为0，协议/溢出错误0。保存ILA原始导出、快照CSV/解码、实际UART返回和逐帧比较JSON。对若干不同输入做短暂停后再跑连续帧。

## 5. C T6回传记录

- 精确镜像组合、BIT/LTX SHA、源码提交/清单、JTAG配置日志和实际设备身份。
- 四帧、连续16帧、受控暂停各自输入/Golden/实际返回、会话ID、原始CSV、31字段解码、ILA导出与错误状态；是否完整逐帧对拍必须明确。
- 新镜像复核冷上电后JTAG恢复及S0空闲复位；不扩大到Flash自主启动或忙时复位。本补丁没有修改复位体系，既有REQP/BRAM异步复位结构风险仍OPEN。
- 板通过后才能标BOARD_PASS；摄像头/HDMI、30fps、200MHz及用户掌握状态均不由此升级。
