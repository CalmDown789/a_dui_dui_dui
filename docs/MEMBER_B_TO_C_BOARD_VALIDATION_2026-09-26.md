# 成员 B 交给 C 的 150 MHz 上板验证说明

日期：2026-09-26。交付分支：`member-b-2025-2-bc-trial`。请 C 以本次分支实际提交、源文件清单和完整板级 XDC 建立可复现构建，完成 150 MHz 单帧板测，并继续推进预录连续多帧输入 → FPGA 超分 → PC 回传播放。**这些工作可以立即推进，不等待 200 MHz 优化。**

当前工程依据为 `10h冲刺_a_assets/docs/source/FSRCNN_ACX750-200T_540p到1080p_30fps部署任务书.docx`，阶段验收同时遵守用户 2026-09-26 的澄清：帧率暂不设严格门槛；ROM 单图对拍是检查点；摄像头和 HDMI 属于之后的竞赛工作。

## 1 本次结果及适用范围

| 构建 | 工具和约束 | 后布线 WNS/TNS | WHS/THS | 状态 |
|---|---|---:|---:|---|
| B 本次推荐 `route_setup030` | Vivado 2025.2，B 实验 XDC | **+0.492/0 ns** | **+0.018/0 ns** | 75,842 条可布线网络全部完成，route errors 0 |
| C 已报告的 100 MHz | Vivado 2022.2，C 板测 XDC | +0.464/0 ns | +0.036/0 ns | C 报告整帧 UART 与 Golden 一致；应补齐原始证据 |
| C 已报告的 150 MHz | Vivado 2022.2，C 板测 XDC，AggressiveFanoutOpt/Explore | −0.210/−36.940 ns | +0.026/0 ns | 时序失败；该 bitstream 尚未上板 |

B 本次采用 `xc7a200tfbg484-2`、真实 A 输入 ROM bank16、B 真实五层、36 位累加和 C 条带 RAM `ram_decomp="power"`。资源为 28,100 LUT、48,498 FF、226 RAMB36、8 RAMB18、394 DSP。相对旧 NetDelay +0.132 ns，增加 0.360 ns 裕量，功能 RTL 未改。

**+0.492 ns 属于 B 的实验构建，C 补齐板级 XDC 后必须重新综合、布局、布线。** B 原 XDC 的 UART 引脚未填写，9 个输出没有 output delay，NSTD-1/UCIO-1 被原实验文件降为 Warning。本次未生成可交付的板级 bitstream，不能把该结果直接登记成 C 板测通过。

详细结果：[150 MHz 裕量补试](MEMBER_B_150MHZ_MARGIN_2026-09-26.md)。旧源文件说明：[B → C 原交接](MEMBER_B_TO_C_HANDOFF_2026-09-24.md)。C 两份历史报告位于 `origin/c-side-latest@2e18a28` 的 `report/c_board_100mhz/`、`report/c_board_150mhz/`；其中引用的实际构建 overlay、完整 XDC、采集脚本和原始板测文件尚需 C 一并归档。

## 2 获取本分支并核对数据

在新的 ASCII 路径下取用，保留 C 正在使用的正式工程。以下 PowerShell 示例使用新目录；不要对已有工作目录执行覆盖、reset 或强制切换。

```powershell
$bCheckout = 'C:\fpga\b150_review_20260926'
if (Test-Path -LiteralPath $bCheckout) { throw '目标目录已存在，请另选新目录' }
git -c core.autocrlf=false clone --single-branch --branch member-b-2025-2-bc-trial https://github.com/CalmDown789/a_dui_dui_dui.git $bCheckout
if ($LASTEXITCODE -ne 0) { throw 'clone failed' }
Set-Location -LiteralPath $bCheckout
git config core.autocrlf false
git rev-parse HEAD
git status --short

# 从本分支已跟踪的 16 个真实 bank 重构原输入 .mem，并校验权威 SHA。
python experiments/timing_margin_20260926/prepare_input_rom.py
if ($LASTEXITCODE -ne 0) { throw 'input ROM preparation failed' }
python experiments/timing_margin_20260926/verify_sources.py
if ($LASTEXITCODE -ne 0) { throw 'release source verification failed' }
```

`core.autocrlf=false` 避免检出时额外换行转换，但原工作站源文件混用 LF/CRLF，不能据此承诺所有 raw SHA 相同。`verify_sources.py` 用 Python 3.9+ 标准库只读核对 67 项（65 个 RTL/XDC/ROM 与两个实跑 Tcl），分别报告 raw 与仅 CRLF→LF 归一后的 canonical 哈希；canonical 必须 67/67，缺文件或其他内容变化即失败。保留 raw 一致数量。此检查不验证 DCP、bitstream 或板测。记录 `git rev-parse HEAD` 的实际结果，不以旧实验开始时的 `7a891e7` 代替本次交付提交。

- 真实图像 bank：`member_b_evidence/real_banks/rom_bank_000.mem` 至 `rom_bank_015.mem`；哈希清单为 `SOURCE_AND_BANK_SHA256.txt`。
- `experiments/l5_splitmem_20260924/fixtures/` 是 marker 数据，不能用于真实图像验收。
- 原完整输入 `.mem` 的 SHA-256：`f15e360bd0d5c3fb1ebd5e85cec32cafaf125c723890c39cf514301c064634c9`。上述准备工具仅重构输入，不提供输出 Golden。
- 输出 Golden 由 A 冻结交付或 C 已校验留档取得：`output_1920x1080_y_u8.bin`，长度 **2,073,600** 字节，SHA-256 **`be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`**。它是最终 1920×1080 Y 图，不是末层四相输出。
- B 参数 ROM 为 `rom/member_a_d16_s8_m1_c16/` 的 19 个 `*_packed.mem`；实现脚本会复制到运行目录。真实模型为 `FSRCNNSubpixel(d16,s8,m1,c16,x2)`，不要用旧任务书中的估算配置替换。

如需重跑 Golden/反压回归，先把 A 的完整 Golden 文件放入 `ref/a_full_integer_golden/`，并取得含 `artifacts/test_vectors/` 的 A 工作副本，再执行：

```powershell
# 将此值改为 C 机器上已经核验的 A 工作副本。
$aCheckout = 'C:\fpga\member_a'
python scripts/verify_golden.py
if ($LASTEXITCODE -ne 0) { throw 'Golden archive verification failed' }
python scripts/prepare_ref_data.py --a-repo $aCheckout
if ($LASTEXITCODE -ne 0) { throw 'Golden staging failed' }
```

已读代码确认：`verify_golden.py` 校验参考数据留档，**不接收 UART dump 参数，也不比较板上文件**；`prepare_ref_data.py` 的 `--a-repo` 用于取得四组小图用例，全尺寸 Golden 仍从本分支 `ref/a_full_integer_golden/` 读取。

## 3 原实验的两步复现

先保持实验 XDC 原样，复现 B 的数值。此步骤只产生实现报告和 DCP，不用于烧板。下面 `$vivado` 改为 C 本机 Vivado 2025.2 的实际路径；若继续用 2022.2，单独标记工具版本差异，不能期望获得相同 WNS。

```powershell
$vivado = 'F:\Xilinx\2025.2\Vivado\bin\vivado.bat'
if (-not (Test-Path -LiteralPath $vivado)) { throw '请填写本机 Vivado 2025.2 路径' }
& $vivado -mode batch -source experiments/timing_margin_20260926/synth_setup030.tcl -log setup030.log -journal setup030.jou -tclargs impl acc36 ascii ramdecomp
if ($LASTEXITCODE -ne 0) { throw 'setup030 failed' }
& $vivado -mode batch -source experiments/timing_margin_20260926/route_setup030.tcl -log route_setup030.log -journal route_setup030.jou
if ($LASTEXITCODE -ne 0) { throw 'route_setup030 failed' }
```

第一步保存 `_synth_bc/acc36_realrom_150_member_b_setup0300926_ascii_ramdecomp/placed_setup030.dcp`。第二步直接读取该布局，以额外 **0.300 ns setup uncertainty** 完成布线，再恢复原 user uncertainty＝0。最终文件在 `_synth_bc/margin0926_route_setup030/`，日志末尾应有 `MARGIN0926_ROUTE_SETUP030_COMPLETE`。

本次原始结果：加压条件 WNS +0.192 ns，恢复条件 +0.492 ns；两份报告恰差 0.300 ns，WHS 都是 +0.018 ns。自动计算的 0.071 ns uncertainty 仍保留。恢复后只有时序更新与报告，没有物理修改。

实现设置必须完整保留：综合后 L5 phase 网络的 `MAX_FANOUT 48`、`place_design -directive ExtraNetDelay_high`、`phys_opt_design -directive AggressiveExplore`、`route_design -directive NoTimingRelaxation`。不要只复制最后一个命令，也不要混入 `forcefifo`、`multi_target` 或 SRL 草稿。使用精确源文件闭包；本分支普通 `rtl/` 目录并非这组实验的完整选源清单。

短回归的已核对入口为：

```powershell
& $vivado -mode batch -source scripts/run_sim_l5_trial_acc36_ramdecomp150_member_b.tcl -tclargs tb_b_real_backpressure tb_b_real_bit_exact
if ($LASTEXITCODE -ne 0) { throw 'backpressure / Golden regression failed' }
```

上述为三种反压和四组 96×54 对拍入口；RTL、复位、帧控制或存储组织发生变化时，除该短回归外还应重跑 `tb_b_real_full`，并为变化的功能补充相应用例。未变的 B RTL 可引用已有完整帧 Golden 证据，不以重复仿真阻塞板级约束工作。

## 4 在 C 的独立板测工程中应用

### 顶层与时钟

以 `synth_setup030.tcl` 的 `c_files`、`b_files` 和 `source_files.txt` 为准导入。推荐沿用实验顶层 **`c_synth_top`** 及其实际参数；它的物理端口是 `sys_clk/rst_n/led[7:0]/uart_tx`。若改用 `c_top`，必须显式覆盖真实 ROM 初始化等参数，不能依赖其 `ROM_INIT_EN=0` 默认值。

| 项目 | 100 MHz | 150 MHz |
|---|---:|---:|
| 外部输入 / MMCM 反馈倍频 / 前置分频 | 50 MHz / 24.0 / 1 | 50 MHz / 24.0 / 1 |
| `CLKOUT0_DIVIDE_F` | 12.0 | 8.0 |
| 传给 `c_core` / `uart_tx` 的 `CLK_HZ` | 100000000 | 150000000 |
| 实验顶层目录 | `rtl/c_100_member_b/` | `rtl/c_150_member_b/` |

表中目录均位于 `experiments/l5_splitmem_20260924/` 下。`rtl/c_config.vh` 仍保留 200 MHz 默认宏，实验 wrapper 已覆盖相关值；核对实际参数传播，不能只改 MMCM 而忘改 UART 使用的 `CLK_HZ`。

初始化必须为 `ROM_INIT_MODE=0`、`ROM_INIT_EN=1`、`USE_MMCM=1`、`RB_ENABLE=1`，综合定义 `C_USE_B_REAL`。输入 bank 实际按裸文件名 `$readmemh("rom_bank_000.mem", ...)` 等读取。wrapper 的 `input_image_pattern.mem` 文件名和部分历史注释不足以判断数据来源，须检查 staging 内容与哈希。

综合后确认 `b_core_real=1`、`b_core_stub=0`、五层网络、PixelShuffle 和预期 FIFO 均存在；漏 ROM、初始化警告、错误顶层或常量折叠都应先解决。

### 完整板级 XDC

1. 将 C **实际成功板测的完整 XDC 和构建 overlay** 纳入可复现板测目录，记录来源提交。B 提供的 `constr/c_top.xdc` 不能直接用于板级交付。
2. 逐项核对实体板版本、原理图、器件 `xc7a200tfbg484-2`、晶振频率、引脚、VCCO 与 IOSTANDARD。现有 XDC 记录时钟 W19、低有效复位 D21 和 LED 引脚；也须与实际板核对。
3. C 历史板测报告称 UART TX 为 **M21**，这是 C 报告提供的线索；请以当前板原理图及实际成功构建确认信号方向、电平标准后填写。本文不替 C 重新确认引脚或假定 IOSTANDARD。
4. 删除实验 XDC 中把 `NSTD-1`、`UCIO-1` 降为 Warning 的两行。在新 Vivado 会话构建；如加载的 DCP 曾带降级设置，在最终检查时恢复为 Error：

   ```tcl
   set_property SEVERITY Error [get_drc_checks {NSTD-1 UCIO-1}]
   report_drc -file board_drc_postroute.rpt
   ```

5. 保留真实 50 MHz 输入时钟及 MMCM 自动派生关系。解释每一个无 input/output delay 端口：LED、异步串口没有同步采样时钟时，应记录接口语义与检查方法；同步外部接口按接收端真实时序预算约束。不要虚填零延迟，或把计算路径统一设为 false path 来消除告警。
6. 检查复位释放、MMCM `locked`、RAM 控制等原有告警，记录处理或评估依据。C 旧报告的 REQP-1840 等警告不能因单帧对拍成功就自动忽略。

**改变完整板级 XDC、顶层或 RTL 后，从综合重新开始两步实现，不能拿 B 的旧 routed DCP 补几个引脚就沿用 +0.492 ns。** 使用独立输出目录，保留 C 的 100 MHz 可恢复基线。若修改了脚本 stage 名，第二步 `open_checkpoint` 必须同步指向该板级构建自身的加压布局 DCP。

### 板级实现与 bitstream

先记录原 `report_clocks`、XDC、工具版本和源文件哈希。B 原条件 user uncertainty 为 0，才适用脚本的“加 0.300、恢复 0”。若 C 原约束已有必须保留的 uncertainty，额外施压后应恢复 C 的原值及原作用范围，不能直接清零。clock collection 必须实际命中 150 MHz 核时钟；顶层层次变化时不能硬套旧 pin 名。

最终在**恢复原板级约束后的同一布线**上保存：`report_timing_summary`、`report_clocks`、`report_route_status`、`report_utilization`、`report_drc`、`write_xdc`、DCP。确认 setup/hold/pulse-width 全部通过、route errors＝0、没有新增未约束内部端点、阻止 bitstream 的 DRC 已真正解决，再在该设计上运行：

```tcl
# 仅在上述板级验收通过的当前设计中执行；不要载入 B 实验 DCP 代替。
write_bitstream -force c_board_150MHz.bit
```

记录 `.bit` SHA-256。Vivado Hardware Manager 核对 JTAG 实际识别器件，选择此 bitstream 配置，记录配置结果与启动状态。生成 `.bit` 成功本身不代表时序通过。

## 5 100 MHz 至 150 MHz 的单帧检查点

C 已报告 100 MHz 对拍通过。若保留了当时的 bitstream、完整源文件/XDC 与 UART 原件，先补齐归档即可；若本次改动了输入 ROM、C 壳或板级构建，则在新构建先跑 100 MHz，排除数据和接口问题，再切 150 MHz。两个频点使用同一 A 输入/Golden。

### 已核对的串口行为

- `rtl/c_config.vh`、`uart_tx.v`：名义 **921600 baud，8N1，LSB first**，`BAUD_DIV=CLK_HZ/BAUD` 为整数除法。100/150 MHz 分频值分别为 108/162；串口工具仍设名义 921600，记录实际测得波特率/误差。
- `readback_ctrl.v`：依条带读出像素，直接发送裸 uint8 Y 字节，**没有帧头、帧号、长度字段或 CRC，也没有 UART RX 命令输入**。不能虚构一个串口“发送 start”命令。
- 输出按 1920×1080 行优先，共 **2,073,600 字节**；17 条带为 16×64 行和最后 56 行。`done` 是最后像素进入输出通路后的控制事件，不表示最后 UART 停止位已经发完。
- 实验 wrapper 在复位释放后约 100 ms 自动发起计算，之后 start 保持有效、空闲时可再次接收。重复同一 ROM 图不能算预录多帧输入；对连续帧的缓冲尾部和边界还要单独验证。
- C 历史采集使用 COM3，但端口号由当前设备枚举决定。当前分支没有已提交的串口采集程序，C 历史报告中的采集脚本也应补交。

### 采集操作

优先复用 C 已通过 100 MHz 的采集脚本并一并提交。关闭占用串口的软件；先按住并保持板上低有效复位，打开串口并清理旧接收缓冲，开始采集后再松开复位。由于流内没有帧头，运行到一半才打开串口会截到半帧；不要尝试从任意字节猜帧边界。

下面是 Windows PowerShell/.NET 的**辅助采集示例，尚未经过本机板测**，无需 Python 串口依赖。执行前保持复位，看到提示后再释放；按实际设备选择 COM 口。它只取复位后的第一帧，不能作为多帧协议工具。

```powershell
[IO.Ports.SerialPort]::GetPortNames()
$portName = Read-Host '输入本次实际 COM 口（不要直接沿用历史 COM3）'
$captureDir = Join-Path (Get-Location) ('board_capture_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $captureDir -ErrorAction Stop | Out-Null
$framePath = Join-Path $captureDir 'frame_y_u8.bin'
$serial = [IO.Ports.SerialPort]::new($portName, 921600, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 1000
$serial.ReadBufferSize = 4194304
$frame = [byte[]]::new(2073600)
$received = 0
$timer = [Diagnostics.Stopwatch]::new()
try {
    $serial.Open()
    $serial.DiscardInBuffer() # 此时 FPGA 必须仍处于复位。
    Write-Host '串口已准备好，现在松开 FPGA 复位；不要在采集中重新复位。'
    $timer.Start()
    while ($received -lt $frame.Length -and $timer.Elapsed.TotalSeconds -lt 120) {
        try {
            $count = $serial.Read($frame, $received, [Math]::Min(65536, $frame.Length - $received))
            $received += $count
        } catch [TimeoutException] { }
    }
} finally {
    $timer.Stop()
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $partial = [byte[]]::new($received)
    [Array]::Copy($frame, $partial, $received)
    [IO.File]::WriteAllBytes($framePath, $partial)
    [pscustomobject]@{port=$portName; baud=921600; format='8N1'; bytes=$received; host_elapsed_s=$timer.Elapsed.TotalSeconds} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $captureDir 'capture.json') -Encoding utf8
}
Get-FileHash -LiteralPath $framePath -Algorithm SHA256
if ($received -ne 2073600) { throw '帧长度不符；已保留部分数据和日志，请排查后从复位重新采集' }
```

采集计时包含人工释放复位和串口等待，不是核心计算时间。921600 baud 8N1 的完整帧线上理论下限约 22.5 s；150 MHz 也不能改变此带宽事实。

### 对拍和记录

长度与 SHA 均匹配上述权威 Golden 后，再记录逐字节差异数。以下命令用 Python 标准库比较实际文件；`$framePath` 沿用上面的采集结果，也可明确赋为 C 已有采集文件路径。

```powershell
$goldenPath = Join-Path (Get-Location) 'ref\a_full_integer_golden\output_1920x1080_y_u8.bin'
@'
from pathlib import Path
import hashlib, json, sys
got, ref = (Path(p).read_bytes() for p in sys.argv[1:3])
expected = 'be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e'
if len(ref) != 2073600 or hashlib.sha256(ref).hexdigest() != expected:
    raise SystemExit('Golden identity failed')
diff = sum(a != b for a, b in zip(got, ref)) + abs(len(got) - len(ref))
first = next((i for i, (a, b) in enumerate(zip(got, ref)) if a != b), None)
if first is None and len(got) != len(ref):
    first = min(len(got), len(ref))
result = dict(bytes=len(got), sha256=hashlib.sha256(got).hexdigest(),
              mismatch=diff, first_difference=first, pass_bit_exact=(got == ref))
text = json.dumps(result, indent=2)
print(text)
Path(sys.argv[1] + '.compare.json').write_text(text + '\n', encoding='utf-8')
raise SystemExit(0 if got == ref else 1)
'@ | python - $framePath $goldenPath
if ($LASTEXITCODE -ne 0) { throw '板上帧与 Golden 不一致，查看 compare.json' }
```

同时记录 `start/busy/done`、最后输入/输出握手、`stripe_last=17 次`、`frame_last=1 次`、`proto_err=0`、`overflow_err=0`；sideband 按有效握手计数，可从计数器、ILA 或已验证观测通路取得，明确数据来源。UART `bytes_sent` 在发起发送时计数，最终完成仍需确认发送器空闲。分别记录可恢复的冷启动/复位测试和不复位的连续两帧测试，避免把首帧成功误当成帧间状态无误。

## 6 当前阶段必须继续完成的多帧通路

**单帧 Golden 通过后，继续完成预录的不同连续帧输入 → FPGA 计算 → PC 接收并按序播放；不能停在重复 ROM 单图。** 当前 UART TX 骨架缺少多帧输入接口和帧标识，此部分由 C 实现，B 配合帧控制与反压，A 提供对应多帧整数参考。

1. **冻结有限测试序列。** A/C 约定帧数、顺序、960×540 uint8 Y 输入与逐帧 1920×1080 uint8 Y Golden，保存每帧 ID、文件名、长度和 SHA。先用两张明显不同的帧排查边界，再扩展至一段预录序列；帧数与时长写入实际测试记录，不新增严格帧率门槛。
2. **选择并实现可持续输入和回传。** C 根据现有板卡例程/资源确定传输接口、时钟域和缓冲。任务书的 UDP 路线可作为候选；本次没有验证或交付 UDP 工程。若用 UART，须补接收接口/协议并接受其低速；不能把只含 TX 的本分支当作已有输入通路。
3. **明确帧边界和流量控制。** 在传输协议或可靠会话中可判定帧号、有效负载长度、起止和完整性；输入仅在 `in_valid&&in_ready` 推进，输出及 sideband 在反压时保持。缓冲满时停止接收或按协议请求发送方等待。`busy=0` 只说明核心可接受新 start；还要处理上一帧未回传的尾部数据及缓冲所有权，不能提前覆盖。
4. **无逐帧手动复位地处理整段序列。** 故意放慢接收/暂停消费来检查反压；逐帧核对输入计数 518,400、输出计数 2,073,600、帧号顺序、完整性、错误计数和对应 Golden。记录实际测得的丢帧、重复帧、乱序和缺字节；完整测试序列应全部为零。若只抽样 Golden，必须标明抽样范围，不能写“全部逐帧 bit-exact”。
5. **PC 从回传结果播放。** 播放器应读取 FPGA 实际回传帧，显示按序变化的内容；当前核心输出为 Y，可先以灰度显示。保存接收日志、逐帧比对结果、播放文件/演示录屏，区分采集完成后播放与边接收边播放，并记录实际运行方式。播放速度不作为 FPGA 实际处理帧率。
6. **记录端到端时间。** 分开测输入传输、计算含 stall/不含 stall、输出传输、连续帧间隔和总帧数/总时长。150 MHz 若在 C 完整约束下暂未通过，多帧功能仍可沿已通过的 100 MHz 构建推进；不等待 200 MHz，也不自行换模型或删除当前必做项。

阶段完成的证据是整段输入、FPGA 输出、PC 播放可关联，帧顺序/边界/完整性通过验证，并有实际吞吐记录。摄像头/HDMI 后续按用户另行启动的竞赛工作处理。

## 7 C 回传证据清单

建议按 `report/c_board_100mhz/`、`report/c_board_150mhz/`、`report/c_multiframe/` 分目录归档，实际提交路径可以不同，但交接报告须逐项链接：

- 板卡/器件、工具精确版本、Git commit、未提交 overlay 清单、RTL/ROM/XDC SHA，真实顶层、参数和完整构建 Tcl。
- 原约束和加压/恢复 clock report、后布线 setup/hold/pulse-width、最差路径、资源、route status、DRC 及接口约束覆盖说明。若用了额外 uncertainty，同时给出收紧和恢复两份报告。
- 可恢复的 100 MHz 和 150 MHz `.bit`、各自 SHA、配置日志；体积较大可放团队可访问的附件位置，报告仍需记录准确路径和哈希。
- UART 真实引脚/电平依据、实际 COM/波特率、采集工具源码与完整命令、原始 `.bin`、长度/SHA/逐字节对拍 JSON、复位与连续帧观察记录。
- 多帧输入/Golden manifest、输入和回传协议、逐帧比对/错误计数、缓冲与反压证据、PC 播放材料、实测时序/吞吐分项。

B 本次只交付实现方法与实验取证。C 的完整板级实现、单帧板测及多帧验收分别登记，不因某一项通过而提前标记其他项完成。
