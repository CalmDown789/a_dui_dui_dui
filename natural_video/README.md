# C：连续自然视频 16 帧联调包（待实体执行）

本包完成 PC 准备及工具检查，尚未执行自然视频上板验收。使用 C 的实际通过镜像 **150MHz、pause=0**，不重新综合，不恢复 200MHz。模型保持 d16/s8/m1/c16、原生 5×5 子像素输出头、INT8 权重/INT16 隐藏激活、Y 通道。源版本冻结为 `303b51d21b3004ddf5780c502ae5c1f3b81cefb6`，B 为 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`。

输入是 OpenCV `vtest.avi` 的连续源帧 100–115（768×576、10fps）；中间裁切为 768×432，双三次缩放到 960×540，再提取 full-range Y。16 帧各不相同，输入/整数 Golden/预处理/权重身份逐项见 `SEQUENCE_MANIFEST.json`。Golden 使用已有 A 整数参考；已核对一个原已验收完整帧与自然首帧 CPU/GPU 逐字节一致。

## 要验证的行为

一次 S0 复位后，连续发送 frame_id=0–15，中途不复位。每帧回传 2,073,600 字节并逐字节等于对应 Golden；16 个 VIO 槽的 31 字段检查通过，错误计数/hold 违规/暂停计数为 0，17 个 stripe_last、1 个 frame_last；ILA 的 snapshot_overflow 为 0。接收后打开实际回传数据生成的 `playback.html`，确认运动和帧序，再返回原始证据。

当前串口是 921600、8N1、原 SRTP stop-and-wait v1。一轮预计至少约 7.5 分钟，加上主机 CRC/对拍开销会更长；逐帧等接收完成再发送下一帧。回放 10fps 是源片段播放速率，不能作为 FPGA 实时吞吐结论。没有 HR 真值，不报告 PSNR/画质优越性。彩色通路尚未实现，本次只显示灰度 Y。

## 执行环境

C 已有 Windows/Vivado 2025.2、正常板卡/JTAG/USB-UART环境。Python **3.10 或更高**仅使用标准库，不需要安装 torch、OpenCV、numpy。PowerShell 使用原 T6 已通过的环境。不要选择蓝牙 COM 端口；确认 USB-UART 当前实际端口。若 JTAG 序列号已变，先记录设备身份后调整两份 Tcl 的明确目标，不用“第一个设备”替代选择。

解压到新 ASCII 路径 `C:\t6video`。以下在 PowerShell 执行；先把 `$python`、`$vivado`、`$port` 替换成当前真实值。`$run` 必须是新的目录，已有目录或失败原件都保留。

```powershell
$kit = 'C:\t6video'
$run = 'C:\t6video_runs\natural16_attempt01'
$python = 'python'
$vivado = 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat'
$port = 'COM实际编号'
& $python -X utf8 "$kit\scripts\verify_kit.py"
& "$kit\scripts\capture_uart_frames.ps1" -SelfTest
```

用途：检查包内所有文件 SHA/长度及 BIT/LTX、输入/Golden 身份，并检查串口 CRC、字节序和协议头；任一报错先停止。

### 1. 烧录及空闲记录

先关闭占用同一目标的其他 Hardware Manager 会话，确保本机 hw_server 的 3121 端口已就绪。创建新目录，然后烧录内置配套镜像：

```powershell
if (Test-Path -LiteralPath $run) { throw '运行目录已存在，换一个新名称，保留旧证据。' }
New-Item -ItemType Directory -Path $run | Out-Null
& $vivado -mode batch -source "$kit\scripts\program_board.tcl" -log "$run\program.log" -journal "$run\program.jou" -tclargs $kit
if ($LASTEXITCODE -ne 0) { throw '烧录失败，保留日志。' }
```

**亲自按 S0 一次**，等待板卡恢复空闲，再导出复位后的 VIO（此导出不会复位）：

```powershell
& $vivado -mode batch -source "$kit\scripts\export_session.tcl" -log "$run\idle_export.log" -journal "$run\idle_export.jou" -tclargs $kit $run idle
if ($LASTEXITCODE -ne 0) { throw '空闲导出失败，保留日志。' }
```

### 2. 一次连续发送/接收 16 帧

```powershell
& "$kit\scripts\run_natural_capture.ps1" -PortName $port -RunDirectory $run -Python $python -ResetConfirmed
```

用途：再次查包、确认原始 idle VIO 为 16 槽 valid=0/count=0，按清单顺序发送全部输入，对实际串口输出逐帧对拍，保存原始二进制、session.json、控制台和命令身份。不在两帧之间复位。捕获失败时保留部分输出与日志，下一次用新 attempt 目录重新完成一次完整序列。

### 3. 完成观察、实际回放与回传

接收结束后**不要按 S0**，直接导出 16 槽和 overflow ILA：

```powershell
& $vivado -mode batch -source "$kit\scripts\export_session.tcl" -log "$run\observation.log" -journal "$run\observation.jou" -tclargs $kit $run post
if ($LASTEXITCODE -ne 0) { throw '观察导出失败，保留日志。' }
Copy-Item -LiteralPath "$kit\OPERATOR_CONFIRMATION.template.json" -Destination "$run\OPERATOR_CONFIRMATION.json"
```

用文本编辑器填写 `OPERATOR_CONFIRMATION.json` 的实际执行人、时间、COM，并且仅在实际完成后把对应 false 改 true。然后：

```powershell
& $python -X utf8 "$kit\scripts\complete_capture.py" --run $run
if ($LASTEXITCODE -ne 0) { throw '自然视频检查失败，保留原始文件并返回报错。' }
Start-Process "$run\playback.html"
Copy-Item -LiteralPath "$kit\PLAYBACK_CONFIRMATION.template.json" -Destination "$run\PLAYBACK_CONFIRMATION.json"
```

用途：重新读取实际二进制逐字节对拍，独立解码原始 VIO/检查 ILA，然后生成内嵌无损 PNG 的离线播放器。亲自观察 `run/playback.html` 的 16 帧循环和单帧切换，填写 `PLAYBACK_CONFIRMATION.json`。可补一张播放器截图，但不能替代原始回传文件。

```powershell
& $python -X utf8 "$kit\scripts\pack_video_evidence.py" --run $run --output 'C:\t6video_runs\NATURAL_VIDEO16_EVIDENCE_20261005.zip'
```

请返回最后的 ZIP 和 `.receipt.json`；打包前会再查原始 UART/VIO/ILA 与播放器哈希。该包包含实际 16 帧、烧录/导出日志、原始 VIO/ILA、命令记录、程序检查、实际播放器和本人确认。收到后协调端再独立验收，C 的报告 PASS 不自动等同于协调端已复核 PASS。

## 文件与结论边界

- `board/` 是已独立复核的 150MHz pause0 实际镜像；BIT SHA256 `a907a50af0528d2149b369a404eb0eade3b282a14e1e9b1e7419acf66b43c0cd`，LTX `1aa99107dbfbf3ee5ef7edebe88d7f581427ff38c15410fe132c96a67445bb66`。
- `software_reference_preview.html` 只用于提前看素材，明确标注软件 Golden，不能替代 FPGA 回传播放。
- 原任务书当前阶段是预录连续多帧→FPGA→PC 回传播放，无严格帧率门槛；UART 离线回放只是该链路的当前验证方式。摄像头、HDMI、4K60、200MHz均不在本次验收中。
- `source_credit/` 记录上游视频文件及冻结来源和 OpenCV 许可信息；本包不另行宣称该视频资产许可，不把其作为商用交付授权依据。
- `contracts/signal_map.json` 的位段沿用已验收契约，末尾 sources 是原 T0 映射来源锚点；当前 C 核修复版本身份以冻结 Git 与 `board/ACCEPTANCE.json` 为准。
