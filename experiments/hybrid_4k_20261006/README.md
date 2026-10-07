# 成员 A 540p 到 4K 混合放大独立实验

状态：R0 多序列基线、R0T/R1/R2/R3/R4/R5 训练试验、留出测试、FFmpeg 降质交叉评测、FP32 与 QAT 整数彩色视频软件原型、QAT 候选复核，以及 10 段连续视频整数评测（1,240 帧）已完成。10 段逐段平均 PSNR 均高于同输入双三次，帧加权平均提高 1.113 dB；FlowerFocus 增益较小，显示结果依赖内容。完整指标见 `CANDIDATE_ACCEPTANCE_REPORT_2026-10-06.md`，逐段结果与本地播放器在 `.data/hybrid_4k_20261006/video_acceptance_20261006/`。所有候选仍是实验方案，未冻结或替换正式模型；没有据此宣称时域稳定、RTL/FPGA 或实时性能。实验不修改正式 A 模型、量化包、Golden 或 B/C 文件。

10 段 R0/QAT seed456 对比所用的精确候选（`quant_params.json` SHA-256 `f2d6c4865b295f6a02c67a43ab2fb00cd36ede723ee8743575f6746f52d924ac`）单独发布在 `candidate_delivery/R0_QAT456_seed456_20261007/`。不要与较早 `quant_cross_eval_adapt456qat5/R0adapt456_QAT5` 候选混淆；后者的量化参数 SHA-256 为 `13f912c9…`，并非 1,240 帧报告使用的数值包。发布候选仍标记为实验状态，不覆盖正式 R0。

## 目标和边界

实验链路固定为 `960×540 Y8 → FSRCNN×2 → 1920×1080 → 双三次×2 → 3840×2160`。R0–R5 只在本目录定义，不改 `src/member_a/model.py` 的冻结模型。结构 MAC 仅作候选初筛；帧率、DSP、存储和时序必须由 B/C 的硬件结果证明。

核心候选为 R0（基线）、R1（输出头 3×3）、R2（扩展通道 c=8）和 R3（两项组合）；后续也筛选了更激进的 R4/R5，只有重要性裁剪版 R4 进入留出集评测，R5 未通过验证门槛。

## 当前可复现实现

- `candidate_models.py`：独立候选模型和 R0–R5 逐层 MAC 计算。
- `bicubic_reference.py`：Keys bicubic 软件参考，支持 `a=-0.5/-0.75`，半像素坐标、边缘复制；浮点中间值不提前裁剪或取整。
- `hybrid_reference.py`：FP32 模型输出转中间 Y8，再经 bicubic ×2 转为最终 Y8；同时提供纯 bicubic ×4 基线。
- `prepare_pairs.py`：把授权 4K 图像中心裁成 3840×2160，Pillow YCbCr-Y 转换，并用 Pillow bicubic ×4 生成 960×540 LR；写入文件哈希和协议清单。
- `prepare_ffmpeg_pairs.py`：将已解码 4K Y8 图像用 FFmpeg bicubic 缩为 540p，生成独立训练/验证/交叉评测配对及来源哈希。
- `evaluate_hybrid.py`：对同一 LR 输入比较纯 bicubic ×4 与 FSRCNN ×2 + bicubic ×2，报告最终 4K Y-PSNR/SSIM，裁边 8 像素。
- `train_candidate.py`：按视频序列隔离训练和验证，对整条 4K 混合链路做 patch MSE 训练；中间和最终 Y8 舍入使用 straight-through estimator。
- `benchmark_cuda.py`：可选的本机 CUDA CNN 单帧延迟比较；排除视频 I/O、插值后级和 FPGA。
- `render_comparison.py`：输出解码参考、bicubic、混合输出和放大误差的 4K 对照图。
- `extract_uvg_hevc_frames.py` 支持显式帧偏移；新增测试确认错开抽帧与原训练帧无重叠。
- `performance_budget.py`：计算 Y8、YUV420、RGB24 端点流量及 1080p 中间帧落 DDR 的理想带宽上下界。
- `qat_candidate.py`、`quantize_candidate_eval.py`、`generate_candidate_golden.py`、`manifest_candidate_bundle.py`、`verify_candidate_bundle.py`：在 `.data/` 下训练、导出、整数评估和校验独立候选，不覆盖正式资产。
- `evaluate_integer_set5_candidate.py`：对独立整数候选做 Set5 2×兼容性抽查。
- `color_video_prototype.py`：生成软件级 YUV420 多帧彩色视频演示；支持 UVG HEVC 与 3840×2160 原始 YUV420 输入，可用 `--quant-dir` 选择整数权重包，默认仍运行冻结 FP32 R0；长片段可用 `--preview-count` 限制代表帧预览数量。
- `compare_color_video_runs.py`：只有在视频源哈希、帧号、退化设置和双三次基线相同的前提下，才生成两次演示的逐帧模型指标对照。
- `compare_integer_evaluations.py`：按同一序列/图像名与双三次基线校验，对两个整数评测 CSV 做配对对比。
- `compare_quant_bundles.py`：逐项对比冻结量化包和实验候选的结构契约、数值参数及整数张量。
- `manifest_color_video_output.py`：生成并验证演示输出目录的 SHA-256/字节数清单。
- `summarize_video_matrix.py`：校验至少十个 5–10 秒片段的帧号不重叠、结果文件齐全，并汇总逐帧加权画质指标。
- `render_video_pair_comparison.py`：仅在同一源哈希、相同源帧和双三次基线完全对齐时，输出 R0F 与 QAT 整数候选的视觉对照图。
- 所有准备数据、指标与图片应放在项目 `.data/`（Git 忽略目录）；原始视频/图片不提交仓库。

当前插值实现是 A 侧浮点实验参考，并非已与 B 冻结的整数实现契约。输入 4K 数据退化、Y 转换、插值核、舍入、饱和都要先形成一致协议；整数 Golden 与 RTL 结果另行验收。

## 候选 MAC 数

按 960×540 输入像素、每个位置的乘加数核算：

| 候选 | d/s/c，输出头 | MAC/输入像素 | GMAC/帧 | GMAC/s @ 60 fps |
| --- | --- | ---: | ---: | ---: |
| R0 | 16/8/16，5×5 | 2832 | 1.468109 | 88.086528 |
| R1 | 16/8/16，3×3 | 1808 | 0.937267 | 56.236032 |
| R2 | 16/8/8，5×5 | 1968 | 1.020211 | 61.212672 |
| R3 | 16/8/8，3×3 | 1456 | 0.754790 | 45.287424 |
| R4 | 16/4/8，3×3 | 928 | 0.481075 | 28.864512 |
| R5 | 8/4/8，3×3 | 696 | 0.360806 | 21.648384 |

R3 的 CNN 算量约为 R0 的 51.4%，这是算术推导，不是帧率提升比例。通道缩减或改核需重新训练/蒸馏；不能只裁权重后把结果称为候选验收。

## FFmpeg 降质交叉评测

为检查候选对降采样实现的敏感度，另用 FFmpeg bicubic 从 UVG 解码的 4K 灰度帧生成 540p 输入，训练集仍为 Beauty/HoneyBee/YachtRide，Jockey 验证，Bosphorus/ReadySetGo/ShakeNDry 留出测试 25 帧；候选仍是原来用 Pillow 合成对训练的 checkpoint。此项是跨降质协议测试，不用于训练或选模，也不与上面的 Pillow 主评测混表。

| 模型 | 25 帧平均 Y-PSNR | 平均 SSIM | PSNR 增益 vs 同输入双三次 | GMAC/帧 |
| --- | ---: | ---: | ---: | ---: |
| R0 冻结基线 | 43.4420 dB | 0.979642 | +2.1654 dB | 1.4681 |
| R1 | 43.1686 dB | 0.978702 | +1.8920 dB | 0.9373 |
| R4 seed123/456 平均 | 42.6766 dB | 0.977748 | +1.4000 dB | 0.4811 |

该测试下 R1 相对 R0 低约 0.2734 dB；R4 两种子平均低约 0.7654 dB，和 Pillow 主评测排序、差距相近。逐序列增益：R0 在 Bosphorus/ReadySetGo/ShakeNDry 分别为 +2.003/+2.431/+1.959 dB；R1 为 +1.785/+2.124/+1.643 dB；R4 两种子平均为 +1.399/+1.538/+1.125 dB。所有序列相对双三次均为正，但 Beauty 彩色演示 8 帧中 R0 的 PSNR 略低于双三次，说明内容依赖仍存在。FFmpeg 交叉评测数据和摘要均在忽略目录 `.data/hybrid_4k_20261006/ffmpeg_*`；仍是 HEVC 解码参考与软件推理，不代表原生相机输入或 FPGA 质量。

### 同结构 R0 适配与整数 QAT 候选

R0 从冻结 FP32 checkpoint 初始化，以 FFmpeg bicubic 配对（Beauty/HoneyBee/YachtRide 共 180 帧）精调 20 轮，Jockey 10 帧验证。两个 seed 的 FP32 留出集变化很小：FFmpeg 协议相对冻结 R0 分别 +0.0675/+0.0667 dB，Pillow 协议分别 +0.0185/+0.0132 dB。seed123 未做 QAT 的 PTQ 整数输出比同校准 R0 低约 0.402 dB，因此没有采用该 PTQ 包。

两个微调种子随后各做 5 轮 STE QAT，以相同 Jockey 校准集重新导出 INT8/INT16/INT32/Q15/Q31 包；CPU 整数参考分别在 FFmpeg 与 Pillow 两套独立 25 帧留出集上逐图评测：

| 测试协议 | 冻结 R0 整数基线 | QAT seed123 | QAT seed456 | 两种子平均增益 |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg 合成降质 | 43.1528 dB | 43.4168（+0.2640） | 43.4756（+0.3227） | +0.2934 dB |
| Pillow 合成降质 | 43.1848 dB | 43.4135（+0.2286） | 43.4886（+0.3037） | +0.2662 dB |

按留出序列配对计算的整数 PSNR 增益（相对同协议的冻结 R0 整数基线）：

| 退化协议 | QAT seed | Bosphorus（10 帧） | ReadySetGo（10 帧） | ShakeNDry（5 帧） |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg | 123 | +0.3786 dB | +0.1926 dB | +0.1778 dB |
| FFmpeg | 456 | +0.4711 dB | +0.2378 dB | +0.1960 dB |
| Pillow | 123 | +0.3694 dB | +0.1473 dB | +0.1097 dB |
| Pillow | 456 | +0.4993 dB | +0.2243 dB | +0.1229 dB |

两种子、两种退化下，各留出序列的平均配对增益均为正；但序列数只有 3，且视频帧有时间相关性，不能把逐帧当成独立随机样本来夸大统计把握。

seed456 QAT 候选另做 Set5 2×整数兼容性抽查：34.0165 dB，对照同校准冻结 R0 整数模型 34.0183 dB，差 −0.0018 dB；这不是 4×视频主指标。该结果可供团队/B 侧审查，但仍属小样本软件整数参考，不能作为 RTL 或板卡验收。候选包位于 `.data/hybrid_4k_20261006/quant_cross_eval_adapt456qat5/R0adapt456_QAT5/`，含量化参数/整数权重、96×54 逐层测试向量及程序生成的全尺寸整数 Golden；134 个文件摘要、48 组小向量阶段输出及 12 个全尺寸阶段摘要已通过 A 侧整数参考一致性校验。不要与正式 R0 ROM/Golden 混用，也不随 Git 提交。

与正式冻结 R0 量化包作参数结构比较：schema、网络/量化契约、五层顺序、所有 OIHW 形状与 padding 完全一致，但数值包不可混用。seed456 候选的 INT8 权重实际变化量如下；所有层的权重 scale、偏置、Q31 重定量参数均不同，四个中间激活边界 scale 也改变。特别是 `shrink` 的 128 个 INT8 权重字节虽相同，其逐输出通道 weight scale 仍全部变化，因此该层实数语义也已变化。

| 层 | INT8 权重变化 / 总数 | INT32 偏置变化 / 通道 | Q1.15 PReLU 变化 / 通道 |
| --- | ---: | ---: | ---: |
| feature | 21 / 400 | 16 / 16 | 11 / 16 |
| shrink | 0 / 128 | 8 / 8 | 5 / 8 |
| mapping0 | 26 / 576 | 8 / 8 | 3 / 8 |
| expand | 8 / 128 | 16 / 16 | 9 / 16 |
| subpixel | 279 / 1600 | 4 / 4 | — |

完整机器可读差异在忽略文件 `.data/hybrid_4k_20261006/quant_candidate_compatibility_vs_frozen.json`，由 `compare_quant_bundles.py` 生成。B 侧若评估候选，必须把其参数、ROM、逐层向量与整数 Golden作为同一版本；不能只替换 INT8 权重。

给 B/队友的候选接入边界、参数差异和验证步骤单独整理在 [`QAT_CANDIDATE_HANDOFF_2026-10-06.md`](QAT_CANDIDATE_HANDOFF_2026-10-06.md)。

### R1 3×3 输出头整数感知微调（低算量备选）

为测试能否通过 QAT 缩回 R1 画质差距，对 R1 的 3×3 输出头候选做了两个独立 seed、各 5 轮 QAT（学习率 1e-6），之后用同一 FFmpeg Jockey 校准集重导整数包，在完全相同的 FFmpeg/Pillow 25 帧留出集上评估。两个 seed 相对 R1 自身 PTQ 的整数 PSNR 都改善约 +0.24 dB；相对冻结 R0 整数基线仍有画质差距：

| 协议 / seed | 相对冻结 R0 整数 PSNR | Bosphorus | ReadySetGo | ShakeNDry |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg / 123 | −0.2972 dB | −0.0881 dB | −0.3963 dB | −0.5174 dB |
| FFmpeg / 456 | −0.2921 dB | −0.0629 dB | −0.4108 dB | −0.5133 dB |
| Pillow / 123 | −0.2370 dB | +0.0038 dB | −0.3562 dB | −0.4802 dB |
| Pillow / 456 | −0.2495 dB | −0.0084 dB | −0.3711 dB | −0.4887 dB |

R1 的静态 MAC 为 0.9372672 G/帧，较 R0 减少 36.2%；差距主要集中在 ReadySetGo、ShakeNDry，体现内容依赖。seed456 独立包及全尺寸整数 Golden 在 `.data/hybrid_4k_20261006/quant_r1_ptq_vs_qat_seed456/R1_QAT/`，134 个文件哈希、48 组逐层向量、12 个全尺寸阶段摘要均通过 A 侧校验。逐帧配对比较 JSON 在 `.data/hybrid_4k_20261006/r1_qat_paired_metrics/`。该包输出头确实为 3×3，不是 R0 ROM 的可替换权重包；B 侧需开独立支持 3×3 的实验路径，不能混用冻结 R0 Golden/ROM。没有综合、板测或实时吞吐证据。

两个 R1 seed 延长到 15 轮 QAT 后，相对各自 5 轮版的 FFmpeg/Pillow 留出 PSNR 分别提升 `+0.059/+0.030 dB` 和 `+0.061/+0.040 dB`。但相对冻结 R0 仍低约 `0.21–0.24 dB`，ShakeNDry 仍低约 `0.46 dB`；两种子间结果差异不到 `0.01 dB`。这是可复现的小幅收益，不足以改变 R1 候选状态；未生成新的候选交付包。逐图对照位于忽略目录 `r1_qat_paired_metrics/seed{123,456}_15ep_vs_*.json`。

再延长至 30 轮后，两个 seed 的最佳验证轮次均为 27；各自相对 15 轮版的 FFmpeg/Pillow 留出 PSNR 增益为 `+0.047/+0.019 dB` 和 `+0.034/+0.020 dB`。相对冻结 R0 仍低约 `0.19 dB`，ReadySetGo 低约 `0.31 dB`、ShakeNDry 低约 `0.41–0.44 dB`。两 seed 间结果相差不足 `0.007 dB`。提升稳定但递减，不建议单纯增加 QAT 轮数；30 轮实验仍只在忽略 `.data/`，未生成候选交付包。逐图报告见 `r1_qat_paired_metrics/seed{123,456}_30ep_vs_*.json`。

## 数据来源与门槛

DIV2K 当前本机副本是 2K 训练图，不能作为原生 4K 真值。可以评测 2K×2 人工放大管线，但只能标成调试用合成数据，不得用于声称真实 4K 画质增益。

本轮使用 UVG 的 Beauty、HoneyBee、Jockey、YachtRide、Bosphorus、ReadySetGo、ShakeNDry 七个 3840×2160 8-bit 4:2:0 HEVC 序列；依官方页面 CC BY-NC 条款用于非商业学术实验并记录来源哈希。下载内容是有损 HEVC 码流；解码帧只是本次配对实验的 4K 参考，不是无损摄像机原始真值。官方数据与许可：[UVG Dataset](https://tie-ultravideo.rd.tuni.fi/dataset.html)，论文 DOI：[10.1145/3339825.3394937](https://doi.org/10.1145/3339825.3394937)。

数据按序列隔离：Beauty/HoneyBee/YachtRide（每段 60 帧，训练）；Jockey（10 帧，验证）；Bosphorus/ReadySetGo（各 10 帧）和 ShakeNDry（5 帧，留出测试）。训练抽帧索引间隔为 10，验证/测试为 60（按 UVG 标注 120 fps 分别约 0.083 秒、0.5 秒）。LR 由同一解码 4K Y 帧经 Pillow bicubic ×4 合成，因此评估的是“合成 540p 输入到该 4K 参考”的软件链路，不等同于真实相机 540p 采集。

## R0 多序列结果

冻结 R0 + Keys `a=-0.5` 在五个序列各 10 帧的同输入比较如下。数值为每段 PSNR/SSIM 的算术平均；逐帧明细在对应输出目录 `per_image_metrics.csv`。混合链路与纯双三次共用同一 LR。

| UVG 序列 | 帧数 | R0−bicubic，a=−0.5 | R0−bicubic，a=−0.75 |
| --- | ---: | ---: | ---: |
| Beauty | 10 | −0.097 dB | −0.272 dB |
| HoneyBee | 10 | +0.885 dB | +0.579 dB |
| Jockey | 10 | +0.773 dB | +0.487 dB |
| YachtRide | 10 | +1.737 dB | +1.342 dB |
| Bosphorus | 10 | +2.213 dB | +1.536 dB |
| ReadySetGo | 10 | +2.628 dB | +2.022 dB |
| ShakeNDry | 5 | +2.242 dB | +1.412 dB |
| **逐帧总平均** | **65** | **+1.425 dB** | **+0.984 dB** |

65 帧的双三次基线平均 PSNR 为 41.951 dB，R0 混合为 43.376 dB；平均 SSIM 从 0.96828 增至 0.97196。Beauty 上增益为负；七段平均不能外推到任意真实视频。`a=−0.5` 在七段都优于 `a=−0.75`，本轮据此继续用 `a=−0.5`。

候选训练数据按序列隔离：180 帧训练、Jockey 10 帧验证；Bosphorus、ReadySetGo、ShakeNDry 共 25 帧留出测试。下表为留出测试集逐帧平均；候选都与同一纯 bicubic 输入基线比较。

| 候选 | GMAC/帧 | MAC 相对 R0 | 本机 CNN p50 | 留出集增益 vs bicubic | PSNR 相对 R0T | SSIM 相对 R0T |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R0T 重训基线 | 1.4681 | — | 2.378 ms | +2.411 dB | — | — |
| R1 输出头 3×3，加密帧微调 | 0.9373 | −36.2% | 2.125 ms | +2.144 dB | −0.267 dB | −0.00092 |
| R2 c=8，修正初始化 | 1.0202 | −30.5% | 1.757 ms | +1.685 dB | −0.726 dB | −0.00222 |
| R3 c=8 + 输出头 3×3，修正初始化 | 0.7548 | −48.6% | 1.614 ms | +1.637 dB | −0.774 dB | −0.00230 |
| R4 s=4，重要性裁剪 + R0T 蒸馏（2 seeds） | 0.4811 | −67.2% | 1.454 ms | +1.625 dB | −0.786 dB | −0.00191 |

其中测试集为 25 帧，R1 相对 R0T 低约 0.267 dB、SSIM 低约 0.00092；R2/R3/R4 的基线画质损失更大。R4 相较 R3 少约 36.3% MAC，两个种子的平均 PSNR 仅低约 0.012 dB、SSIM 高约 0.00038；但两者相较 R0T 都低约 0.79 dB。R4 的 s=8→4 使用基于 shrink/mapping/expand 权重 L1 贡献的通道选择，并经 40 轮微调及 R0T 蒸馏；按数组顺序简单裁通道的 R4/R5 未达到同等验证质量。MAC 是静态算术，本机 CUDA p50 是 RTX 5060 Laptop GPU 上的 CNN-only 时延；两者都不是 FPGA DSP、时钟或吞吐结果。目前不更改正式模型，需团队先确认可接受的画质损失阈值。

### R1 加密训练帧复验

为检查 R1 画质损失是否来自训练帧覆盖不足，在 Beauty/HoneyBee/YachtRide 三个训练序列额外抽取与原样本错开的帧（stride=10、offset=5），新增 180 帧；原 180 帧、Jockey 验证片段及 25 帧留出测试均保持不变。R1 以 2.5e-6 学习率训练 30 轮。验证最佳 MSE 为 2.76145e-5，未优于前一 R1 最佳 2.75951e-5；留出集相对 R0T 为 −0.267 dB、SSIM −0.00092，相比此前 R1 仅增加约 0.012 dB。此轮没有实质性恢复画质，新增帧不构成正式候选升格理由。训练清单、哈希、日志与 checkpoint 仅存于忽略目录 `.data/hybrid_4k_20261006/`。

另测了从 R0T 初始化、冻结共享主干、仅微调 3×3 输出头 40 轮的方案。最佳 Jockey 验证 MSE 为 2.96913e-5，比完整微调 R1 的 2.75951e-5 高约 7.6%，未进入留出测试；因此不纳入候选结果表。

R4/R5 极限缩宽方案的直接裁剪初始化 30 轮后，Jockey 验证 MSE 分别为 1.37238e-4 和 3.06933e-4，未达继续测试门槛。R4 改从已训练 R3 选取权重贡献最高的 4 个 shrink/mapping 通道（索引 5、2、0、4）并微调 40 轮，再以 R0T 为教师蒸馏 40 轮。两个独立种子的验证 MSE 分别为 2.84079e-5、2.83903e-5；留出集增益为 +1.618、+1.632 dB，较 R0T 低 0.793、0.779 dB，结果接近。两种子平均 R4 相对 R0T 低 0.786 dB / 0.00191 SSIM；相比 R3 少 36.3% MAC，平均 PSNR 低 0.012 dB。R5 未做留出测试，当前不推荐。

## 视频流量预算（算术估算）

以下按 30/60 fps、8-bit 平面格式计算十进制 MB/s，不含协议开销、DDR 效率损耗或显示消隐。端点模型为每帧读一次 540p Y 输入并写一次指定输出；第二列额外假设 1080p Y 中间结果完整写入再读出 DDR。30 fps 结果：

| 输出格式 | 端点流量 | 若 1080p Y 中间帧落 DDR |
| --- | ---: | ---: |
| 4K Y8 | 264.384 MB/s | 388.800 MB/s |
| 4K YUV420 8-bit | 388.800 MB/s | 513.216 MB/s |
| 4K RGB24 | 762.048 MB/s | 886.464 MB/s |

60 fps 数值为表中两倍。当前已验证的是 Y8 软件参考链路；YUV420/RGB24 仅用于说明颜色输出数据量，不表示成员 B/C 已实现彩色链路。完整帧缓存尺寸及可复算 JSON 由 `performance_budget.py` 生成到忽略目录，供 C 根据实际缓存/DDR 结构核对；这些数字不能替代板上 DDR 实测。

## 8 帧彩色视频软件原型

已用 UVG Beauty 与 Bosphorus 公开片段各生成 8 帧软件演示：输入由 FFmpeg 从 4K HEVC 解码后双三次缩小为 960×540 YUV420；Y 平面经 FSRCNN ×2 + Keys bicubic ×2 放大，Cb/Cr 用 Keys bicubic ×4 放大，最后打包成 3840×2160 YUV420。两段均选帧索引 0、10、…、70，按 12 fps 写出。FP32 版本使用冻结 R0，产物位于 `.data/hybrid_4k_20261006/color_demo_uvg_beauty_8frames/` 和 `color_demo_uvg_bosphorus_8frames/`；整数版本包含冻结 R0 和独立 R0-QAT seed456 候选，目录分别为 `color_demo_uvg_bosphorus_frozen_r0_integer_8frames/` 与 `color_demo_uvg_bosphorus_qat_integer_8frames_v2/`。每个目录包含 MP4、YUV420 原始帧、逐帧 PNG、对照图、`summary.json` 与 30 文件 SHA-256 清单，清单均已验证。

Beauty 8 帧的 Y-PSNR 为双三次 45.701 dB、混合 45.589 dB（−0.112 dB），SSIM 分别为 0.965454、0.965751；Bosphorus 8 帧为双三次 42.665 dB、混合 44.688 dB（+2.024 dB），SSIM 分别为 0.978507、0.983187。两段结果差异体现内容依赖，不能只挑正向片段宣称普遍提升。该演示证明 A 侧软件能完成多帧 YUV420 解码、亮度超分、色度插值与视频封装；它采用 FFmpeg 生成的合成 540p 输入，和前述 Pillow bicubic 配对评测协议不同，不可混表；每段只有 8 帧，也不代表一般视频。没有 FPGA、板卡通信、HDMI、实时吞吐或实时帧率结论；UVG 源为 CC BY-NC，产物保持在本地忽略目录，不随仓库分发。

整数 QAT 版的 Bosphorus 8 帧 Y-PSNR 为双三次 42.665 dB、混合 44.728 dB（+2.063 dB），SSIM 分别为 0.978507、0.983280。对同 8 帧、同源、同双三次基线的冻结 R0 整数版（44.342 dB）进行逐帧对照后，QAT 整数候选平均高 0.386 dB；8 帧逐帧增益均为正，范围 +0.294 至 +0.426 dB，平均 SSIM 高 0.00246。与同片段 FP32 冻结 R0 逐帧比较则平均高 0.0398 dB。以上只是单段 8 帧小样本，不能据此断言泛化增益。可复核的逐帧差值分别在 `.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_integer_baseline_vs_qat456_8frames.json` 和 `color_demo_uvg_bosphorus_fp32_vs_qat_integer_8frames.json`。整数路径运行 A 侧 CPU `FixedReference`，逐帧载入量化参数/权重并计算；它不是 B RTL、综合、时序、板卡或实时处理验证。复现时给脚本传入候选 `quant` 目录的 `--quant-dir`；此实验包仅供审查，不能替换正式 R0 参数、ROM 或 Golden。

整数彩色视频演示复现命令（素材需先位于 `.data/hybrid_4k_20261006/sources/`）：

```powershell
python -m experiments.hybrid_4k_20261006.color_video_prototype `
  --video .data/hybrid_4k_20261006/sources/Bosphorus_3840x2160_120fps_420_8bit_HEVC_RAW.hevc `
  --sequence Bosphorus `
  --quant-dir .data/hybrid_4k_20261006/quant_cross_eval_adapt456qat5/R0adapt456_QAT5/quant `
  --output-dir .data/hybrid_4k_20261006/color_demo_uvg_bosphorus_qat_integer_8frames_v2 `
  --frames 8 --frame-stride 10 --frame-offset 0 --source-fps 120
```

## 验收步骤

1. 本轮 7 段 UVG HEVC 片段只作为非商业学术软件实验；若改用其他素材，先记录许可、源文件哈希与数据分组。
2. 由项目组审阅 R1/R4 的算量—画质取舍，以及 R0-QAT 的整数收益和数据边界；当前正式 R0 保持不变。
3. 如决定让 B 试跑 R0-QAT，先审阅候选目录中的量化参数、整数权重、向量与全尺寸 Golden，再独立接入仿真；不可复用正式 R0 ROM/Golden。
4. B 侧逐字节 RTL 对拍、C 侧资源/时序实现和板测仍须单独完成；本机整数参考结果不等同于 RTL PASS。

参考运行（在项目根目录，所有产物均在 `.data/`）：

```powershell
$env:PYTHONPATH = '.;src'
python -m pytest experiments/hybrid_4k_20261006/tests
python -m experiments.hybrid_4k_20261006.prepare_pairs --source-dir <4K帧目录> --output-dir .data/hybrid_4k_20261006/pairs --source-name <数据集名> --source-url <官方页面> --license <许可>
python -m experiments.hybrid_4k_20261006.evaluate_hybrid --pairs-dir .data/hybrid_4k_20261006/pairs --checkpoint artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth --variant R0 --keys-a -0.5 --output-dir .data/hybrid_4k_20261006/r0_a_m05
python -m experiments.hybrid_4k_20261006.train_candidate --train-pairs-dir .data/hybrid_4k_20261006/uvg_Beauty_trainpairs --train-pairs-dir .data/hybrid_4k_20261006/uvg_HoneyBee_trainpairs --train-pairs-dir .data/hybrid_4k_20261006/uvg_YachtRide_trainpairs --validation-pairs-dir .data/hybrid_4k_20261006/uvg_Jockey_pairs --initial-checkpoint artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth --distill-checkpoint .data/hybrid_4k_20261006/train_r0t/r0_best.pth --distill-weight 1 --variant R1 --output-dir .data/hybrid_4k_20261006/train_r1
python -m experiments.hybrid_4k_20261006.benchmark_cuda --candidate R0=artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth --candidate R1=.data/hybrid_4k_20261006/train_r1/r1_best.pth --output .data/hybrid_4k_20261006/cuda_latency.json
```

评测报告声明 FP32 软件参考，不是整数部署、FPGA、200/150 MHz 时序或持续 60 fps 的证据。
