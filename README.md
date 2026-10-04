# ACX750-200T 成员 A FSRCNN 子像素模型交付

已完成成员 A 的算法与数据交付，用于小梅哥 ACX750-200T 上的 540p 到 1080p 超分项目。模型为 `d=16 / s=8 / m=1 / c=16` 的 FSRCNN 主干，输出层直接训练为稠密 `5×5 Conv 16→4 + PixelShuffle×2`。它不是 9×9 反卷积的逐权重等价变换。

## 冻结规格

- 输入：`960×540`，8-bit 灰度 Y，HWC 行优先；
- 输出：`1920×1080`，8-bit 灰度 Y；
- 权重：逐输出通道对称 INT8，OIHW；
- 激活：逐层对称 INT16；
- 偏置与累加：INT32，溢出饱和；
- PReLU：逐通道 Q1.15；
- 算力：`1.4681088 G MAC/帧`，30fps 为 `44.043264 GMAC/s`；
- 理论估计：任务书按特定 DSP 打包、频率和利用率假设给出 `133.2 GMAC/s`，对应约 `3.02×`；该数值不是板上实测吞吐，也不保证实际达到 30fps。

## 环境

```powershell
C:\Python314\python.exe -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 完整复现

下载 T91 与 Set5 原始图像并在本地生成 ×2 训练块，训练 FP32 模型、校准量化参数、必要时执行 5 epoch QAT，并生成全部交付物：

```powershell
.\.venv\Scripts\python.exe run_all.py
```

验证已经提交的模型、权重、格式、测试向量、全尺寸输出、指标和哈希：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\verify_delivery.py
```

## 全尺寸整数 Golden

成员 A 已补齐可供 B/C 最终逐字节验收的 `960×540 → 1920×1080` 整数网络 Golden。它由导出的 INT8 权重、INT16 激活、INT32 偏置/累加、Q1.15 PReLU 和 Q31 重量化参数直接计算，不是 FP32 输出，也不是 QDQ 软件仿真输出。

成员 A 的正式取数位置为冻结标签 `member-a-v1.0.1`，不是 `main`。`main` 上的历史回退只是成员分支隔离操作，不代表数据失效；完整原因、checkpoint 和输入生成来源见 `docs/成员A发布治理与来源确认.md`。

下游 B/C 对同一份权重、ROM 和整数 Golden 的复用情况，以及 36-bit 内部保护累加器为何不改变 A 的 INT32 对拍合同，见 `docs/成员A下游验证状态_2026-09-24.md`。该文件仅记录消费方验证事实，不把 RTL、Vivado 时序或板测结果纳入成员 A 的交付范围。

- 权威输出：`artifacts/full_integer_golden/output_1920x1080_y_u8.bin`；
- C 侧输入 ROM：`artifacts/full_integer_golden/input_rom_2p19_u8.mem`，共 `524288` 行，前 `518400` 字节为输入图像，末尾 `5888` 字节为 `00`；
- 四相位诊断输出：`artifacts/full_integer_golden/subpixel_phases_540x960x4_hwc_u8.bin`；
- 完整形状、值域、逐层摘要和 CRC32/SHA-256：`artifacts/full_integer_golden/manifest.json`。

重新生成并执行全层整数重算验收：

```powershell
.\.venv\Scripts\python.exe scripts\generate_full_integer_golden.py
.\.venv\Scripts\python.exe scripts\verify_full_integer_golden.py --recompute
```

最终输出固定为 `2073600` 字节，CRC32 为 `87d353f1`，SHA-256 为 `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`。

只交接小尺寸逐层整数实现时，可直接下载 `artifacts/member_a_integer_delivery_d16_s8_m1_c16.zip`。压缩包包含 `quant_params.json`、INT8/INT32/Q1.15 权重参数和四组 96×54 逐层向量；全尺寸最终 Golden 以仓库中的 `artifacts/full_integer_golden/` 为准。解压小尺寸包后运行：

```powershell
python scripts\verify_integer_delivery.py
```

审核模型质量证据时，可直接下载 `artifacts/member_a_weights_and_logs.zip`，其中集中提供 FP32 checkpoint、模型契约、50轮训练日志、Set5逐图指标、汇总指标及量化参数。

训练数据保存到 `.data/` 且不会提交。任务书原件保存在 `docs/source/`，接口约定、算力核算和成员 A 报告位于 `docs/`。

本次固定种子训练的 Set5 平均结果为：双三次 32.6398 dB、FP32 34.1202 dB、量化 34.0190 dB；量化损失 0.1012 dB，因此未触发 QAT。完整逐图 PSNR/SSIM 见 `artifacts/evaluation/set5_metrics.csv`。

## 预录视频多帧检查（2026-10-03）

新增公开授权视频的固定 8 帧 `960×540` 输入及逐帧 `1920×1080` 整数 Golden。模型、权重、量化参数和原冻结标签保持不变。先用 frame 000/007 做两幅不同画面的检查，再按清单顺序跑完整 8 帧。

按 10 月 3 日详细任务说明补充 A1 成对包：`artifacts/member_a_authority_plus_second_frame.zip`，包含旧权威帧 0000 和不同自然画面 0001，来源见 `artifacts/authority_pair/manifest.json`。它与视频的 frame ID 使用不同序列 ID，避免混淆。每帧无损灰度预览与原始字节同时交付。

- 取数：`artifacts/multiframe/manifest.json`；两帧子集：`two_frame_manifest.json`；
- 便携包：`artifacts/member_a_two_frame_check.zip` 和 `artifacts/member_a_video_8frames.zip`；
- 回传工具：`python scripts/compare_board_sequence.py --capture-dir <回传目录>`，支持单帧与无头连续数据；
- PC 播放器：`python scripts/export_pc_player.py --output <D盘HTML路径>`，可选加载回传文件并并排对照；
- 接收清单：`python scripts/compare_received_frames.py --manifest artifacts/multiframe/manifest.json --received-manifest <D盘接收清单> --report <D盘报告>`；播放器支持同一个 `--received-manifest`，保留接收顺序，不用 Golden 补缺帧；
- 新序列生成：`python scripts/generate_multiframe_golden.py --inputs artifacts/authority_pair_inputs.json --output-dir <D盘新目录>`，拒绝覆盖已有目录；
- [验收命令、退出码和日志](results/multiframe/task_execution.json)，[完整任务核验](docs/成员A任务核验_2026-10-03.md)；
- [交接说明与命令](docs/成员A多帧交接_2026-10-03.md)。

清单包含帧编号、顺序、源视频时间、哈希和冻结模型来源。抽样序列是 2 fps 展示素材，不是持续帧率指标；软件 Golden 已完成整数重算，C 的该组多帧板测仍需回传数据验证。

## 彩色演示与实际整数画质评测（2026-10-04）

新增 PC 彩色视频示范：冻结整数 Golden 的 Y 与源视频放大的 Cb/Cr 合成，4 秒 1080p、2 fps。视频、逐帧输入/输出哈希和颜色转换假设见 `artifacts/color_demo/`；Big Buck Bunny 按 [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) 署名。

新增 20 个样本的双三次、FP32 和实际整数对比，详见[画质方法与解释](docs/成员A彩色演示与整数画质评测_2026-10-04.md)、[HTML 报告](artifacts/evaluation/actual_integer_quality_report.html)、[JSON](artifacts/evaluation/actual_integer_quality_report.json)及[逐图 CSV](artifacts/evaluation/actual_integer_quality_per_image.csv)。Set5 曾用于权重选择，不属于独立留出集；BBB 的 8 张 640×360→1280×720 配对是软件评测；文字/建筑/人物/运动为合成压力图。BBB 样本整数平均 46.366 dB，低于双三次 46.604 dB；这提示当前模型对该类内容未能稳定胜过插值。

导师审阅包：`artifacts/member_a_color_quality_evaluation.zip`，包括彩色视频、画质报告、图表、逐图数据和复现脚本；不包含原始视频或 Set5 图片。

复现命令：

```powershell
python scripts/evaluate_integer_quality.py
python scripts/create_color_video_demo.py
python scripts/package_color_quality_report.py
```

生成指标时，脚本核对 checkpoint、量化参数、Set5 和源视频摘要，并确认 960×540 权威整数 Golden 重算一致。报告只记录软件结果；尚无相应板卡视频采集证据。

实时 PC 上传与回传适配尚未完成，等待 A/C 确认接口、帧头/编号、流控、CRC 和超时恢复，见[协议确认清单](docs/成员A_PC收发协议确认清单_2026-10-03.md)。离线播放器和对拍工具不等于实时收发链路。

已补充已知 UART TX 的[PC 接收保存工具](docs/成员A_UART接收工具_2026-10-03.md)：`capture_raw_uart.py` 支持短读、超时、断连和尾部额外数据，输出同一套接收清单与原始字节。不上传输入、不发送未知命令；打开实际端口前必须核验完整帧起点与 RTS/DTR 接线安全。软件读取器的验证记录位于 `artifacts/uart_capture_selftest.json`，不等于实体串口或 A4 双向通路已通过。

另按用户提供的 C 隔离原型说明，增加[双向 UART 实验客户端](experiments/member_a_uart_prototype_20261003/README.md)。实验输入采用 `SRTP`、小端字段和 IEEE CRC-32，按 stop-and-wait 收齐裸 Y 输出后才发下一帧；失败不自动重发。协议状态固定为 `PROTOTYPE_UNCONFIRMED`，没有 C 原型来源提交或板测证据，不对正式 TX-only 工程发送输入。两帧、8 帧及错字节的软件联测见 `artifacts/uart_prototype_selftest.json`。当前链路的输入加输出理论串行时间约 28.125 秒/帧，不是实时视频；UDP 未实现。

## PC 通信故障模拟、链路预算与板卡接口资料（2026-10-05）

成员 A 新增纯软件 UART 故障模拟器，复用实验 PC 客户端，覆盖正常/延迟、截断、错误帧内容、帧号不同步、断线以及帧前残留数据需要复位等场景。模拟端返回冻结 Golden，不连接串口、不执行 RTL、不证明 C/板卡兼容。[逐场景结果](artifacts/pc_transport_simulator_selftest.json)和复现边界见[PC 通信与性能预算报告](docs/成员A_PC通信故障模拟与带宽预算_2026-10-05.md)。

同一报告包含可参数化的 `scripts/pc_performance_budget.py`，可调整分辨率、倍率、FPS、Y8/YUV420P/RGB24、UART 波特率和以太网线速；能读取保存的接收会话并拆分 PC 发送、首字节等待、回传读返回跨度和本机对拍时间。当前预算表可看 [CSV](artifacts/pc_performance/pc_bandwidth_budget.csv)、[JSON](artifacts/pc_performance/pc_performance_budget.json) 和 [Markdown](artifacts/pc_performance/pc_performance_budget.md)。无实测输入时不会填造实测值。

厂商公开资料已核对 ACX750-200T 的器件标注、DVP/HDMI 接口列表、DDR3 配置提示及摄像头→DDR3→HDMI 参考工程入口。实际板卡 revision、摄像头模块、电平/时钟、HDMI XDC 和 MIG 配置仍需 C 用实物及工程确认；当前 C 顶层不包含相机、DDR MIG 或 HDMI 视频通路。A 侧只整理来源与缺项，不修改 C 工程。

## 职责边界

本交付不包含 RTL、板级约束、Vivado 工程或 bitstream。成员 B 可直接读取 `artifacts/quant/quant_params.json`、各层 `.mem/.coe` 权重以及 `artifacts/test_vectors/` 完成 RTL 对拍；成员 C 负责板卡工程、ILA、时序收敛和上板结果导出。
