# 成员 A 模型优化阶段报告

日期：2026-10-06
阶段：540p Y → FSRCNN ×2 → Keys bicubic ×2 → 4K 软件筛选
范围：只新增独立实验；未修改正式冻结模型、整数权重、Golden、成员 B/C 工程或 GitHub 远端。

## 本阶段结论

冻结 R0 的 4K 混合软件链路已在 7 个 UVG 视频序列的 65 帧上完成初步对照。相对同输入的纯 bicubic ×4，平均 PSNR 增加 **1.425 dB**、平均 SSIM 增加 **0.00369**；但 Beauty 单序列 PSNR 低 **0.097 dB**，收益与内容有关，不能外推为任意视频的保证。

缩算量候选中，R1（仅将稠密输出头由 5×5 改为 3×3）最接近 R0T 重训基线：CNN 静态 MAC 减少 **36.2%**，本机 RTX 5060 单帧 CNN 延迟中位数约减少 **10.3%**；在 25 帧、3 个未参与训练的测试片段上，较 R0T 低 **0.267 dB** PSNR、低 **0.00092** SSIM。当前这是一个有算量收益、但存在画质代价的候选，尚不建议替换正式模型。

R2/R3/R4 的 MAC 降幅更大，但测试画质损失也更大；当前不推荐升格。R4 约减少 67.2% MAC，本次 25 帧留出集相对 R0T 的 PSNR 低约 0.786 dB。所有结果均为 FP32 软件对照，不是量化模型、FPGA 或板卡验收结论。

## 数据与评测约定

- 来源：UVG 的 Beauty、HoneyBee、Jockey、YachtRide、Bosphorus、ReadySetGo、ShakeNDry。UVG 官方页面注明 4K 序列为 CC BY-NC，要求引用 Mercat、Viitanen、Vanne 的 2020 年论文：[UVG 数据集与许可](https://tie-ultravideo.rd.tuni.fi/dataset.html)，[论文 DOI 10.1145/3339825.3394937](https://doi.org/10.1145/3339825.3394937)。
- 下载的是 8-bit 4:2:0 HEVC 码流，本文使用 FFmpeg 解码出的 Y 平面；HEVC 有损，因此是“解码参考帧”，不是无损相机原始真值。原视频和解码帧保存在本机忽略目录 `.data/`，没有复制到 GitHub。
- 数据按视频序列分组，避免同片段相邻帧泄漏：Beauty/HoneyBee/YachtRide 各 60 帧用于训练；Jockey 10 帧用于验证；Bosphorus、ReadySetGo 各 10 帧和 ShakeNDry 5 帧作为留出测试。测试共 25 帧。
- 对每一张 4K 解码 Y 帧，用 Pillow bicubic ×4 合成 960×540 输入；同一 LR 分别输入纯 Keys bicubic ×4 与 FSRCNN ×2 + Keys bicubic ×2。输入、Y 平面、中心裁边 8 像素、最终 uint8 舍入/饱和规则均固定。
- 这是受控的合成降采样画质对照，不等同于真实 540p 摄像机采集、彩色视频、整数部署或 FPGA 输出。

源文件字节数、SHA-256、抽帧索引、逐帧哈希与解码器信息见 `.data/hybrid_4k_20261006/uvg_*_frames/source_manifest.json`；每张配对图的源帧哈希与 LR/HR 哈希见相应 `uvg_*_pairs/manifest.json`。所有大文件均在 `.gitignore` 的 `.data/` 内。

## R0 插值参数与画质结果

下表为每序列相对纯 bicubic ×4 的 PSNR 增量，均值为该序列逐帧结果的算术平均。

| UVG 序列 | 帧数 | R0，Keys a=−0.5 | R0，Keys a=−0.75 |
| --- | ---: | ---: | ---: |
| Beauty | 10 | −0.097 dB | −0.272 dB |
| HoneyBee | 10 | +0.885 dB | +0.579 dB |
| Jockey | 10 | +0.773 dB | +0.487 dB |
| YachtRide | 10 | +1.737 dB | +1.342 dB |
| Bosphorus | 10 | +2.213 dB | +1.536 dB |
| ReadySetGo | 10 | +2.628 dB | +2.022 dB |
| ShakeNDry | 5 | +2.242 dB | +1.412 dB |
| **逐帧总平均** | **65** | **+1.425 dB** | **+0.984 dB** |

在 65 帧上，`a=−0.5` 的双三次基线平均 PSNR 为 41.951 dB，R0 混合链路为 43.376 dB；平均 SSIM 从 0.96828 增至 0.97196。`a=−0.75` 的逐帧平均增益低约 0.440 dB，因此本轮统一使用 `a=−0.5`。这只是当前 UVG 片段和退化协议下的选择。

## 候选结构筛选

R0T 与 R1/R2/R3 均从冻结 R0 权重迁移初始化，并以 180 训练帧、Jockey 验证片段做端到端 4K MSE 精调；候选使用 64×64 LR 随机块、batch 4、Adam、固定 seed 123、中间和最终 uint8 量化的 straight-through 训练近似。R1 采用 R0T 教师蒸馏权重 1.0；0.5 与 2.0 的 25 帧留出集结果与 1.0 基本重合（差异小于 0.01 dB）。R4 的蒸馏权重对照也完成：相同 seed123 的独立模型分别使用 0.5/1.0/2.0，验证最佳 MSE 在 2.84264e-5 至 2.83865e-5 间，留出平均 PSNR 增益在 +1.61849 至 +1.62996 dB 间，未显示有实际意义的权重敏感性；候选表与双种子基准仍采用 R4 权重 1.0，不进一步扩大搜索。

| 候选 | 结构差异 | GMAC/帧 | MAC 相对 R0 | 本机 CNN p50 | 留出 25 帧 PSNR 相对双三次 | 相对 R0T | SSIM 相对 R0T |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R0T | 原 5×5 输出头，重训基线 | 1.4681 | — | 2.378 ms | +2.411 dB | — | — |
| R1，加密帧微调 | 输出头 3×3 | 0.9373 | −36.2% | 2.125 ms | +2.144 dB | −0.267 dB | −0.00092 |
| R2，修正版 | 扩展通道 c=8 | 1.0202 | −30.5% | 1.757 ms | +1.685 dB | −0.726 dB | −0.00222 |
| R3，修正版 | c=8 + 输出头 3×3 | 0.7548 | −48.6% | 1.614 ms | +1.637 dB | −0.774 dB | −0.00230 |
| R4，重要性裁剪 + R0T 蒸馏（2 seeds） | s=4 + 输出头 3×3 | 0.4811 | −67.2% | 1.454 ms | +1.625 dB | −0.786 dB | −0.00191 |

**迁移实现复核记录：**首次 R2/R3 小批次试验曾把一维 PReLU 向量按空间维度中心裁剪，通道索引不匹配。该缺陷已修正并新增回归测试；本表 R2/R3 只采用修正后的重新训练 checkpoint。旧训练结果不再引用。R1 加密训练帧后的独立留出结果略优于最初 R1（见下节），表中的 CUDA 时延取相同 R1 结构、加密帧 checkpoint 的复测值；候选损失统计也使用该 checkpoint。

CUDA 延迟测量为 RTX 5060 Laptop GPU、PyTorch/cuDNN、输入 1×1×540×960、30 次预热、100 次迭代；只包含 CNN 前向，不包含数据传输、CPU 双三次、视频 I/O。它只能说明本机软件内核的相对时延，不能推导 ACX750 的 DSP、时钟、帧率或板卡性能。

## FFmpeg 降质交叉评测

为核对候选是否只适用于训练时的 Pillow bicubic 输入，另以 FFmpeg bicubic 从 UVG 解码 4K Y8 帧生成 540p 输入，使用训练序列 Beauty/HoneyBee/YachtRide、Jockey 验证、Bosphorus/ReadySetGo/ShakeNDry 留出 25 帧；此交叉测试没有用于训练或选模，三个候选均使用既有 checkpoint。退化规则与彩色视频软件原型的 Y 平面相近，但这里从全分辨率灰度 PNG 缩小，不等同于相机采集或完整 YUV420 输入。

| 模型 | 留出集平均 Y-PSNR | 平均 SSIM | PSNR 增益 vs 同输入双三次 | GMAC/帧 |
| --- | ---: | ---: | ---: | ---: |
| R0 冻结基线 | 43.4420 dB | 0.979642 | +2.1654 dB | 1.4681 |
| R1 | 43.1686 dB | 0.978702 | +1.8920 dB | 0.9373 |
| R4 seed123/456 平均 | 42.6766 dB | 0.977748 | +1.4000 dB | 0.4811 |

逐序列 PSNR 增益（Bosphorus / ReadySetGo / ShakeNDry）分别为：R0 `+2.003 / +2.431 / +1.959 dB`，R1 `+1.785 / +2.124 / +1.643 dB`，R4 双种子均值 `+1.399 / +1.538 / +1.125 dB`。R1 相对 R0 低约 0.2734 dB，R4 平均低约 0.7654 dB；这与 Pillow 主评测中的候选排序相符，表明更换下采样实现没有消除缩算量的质量差距。Beauty 8 帧软件样例反而比双三次低 0.1116 dB，说明场景间仍有波动。逐图 CSV、配对清单与摘要仅在忽略目录 `.data/hybrid_4k_20261006/ffmpeg_*`。

## R0 同结构 FFmpeg 适配与 QAT 整数候选

为检验微调和定点化能否改善原模型，R0 从冻结 FP32 权重初始化，以 FFmpeg bicubic 的 Y8 配对（Beauty/HoneyBee/YachtRide 180 帧）训练 20 轮，Jockey 10 帧验证；两个 seed 均为独立实验。微调后 FP32 留出集变化很小：相对冻结 R0，FFmpeg 协议分别 +0.0675/+0.0667 dB，Pillow 协议分别 +0.0185/+0.0132 dB。seed123 直接 PTQ 后，FFmpeg 留出整数 PSNR 为 42.7513 dB，较同校准冻结 R0 的 43.1528 dB 低 0.4016 dB，表明 FP32 微调本身不构成量化收益证据。

随后对两个适配 seed 分别做 5 轮 STE QAT；用同一 FFmpeg Jockey 校准集重新导出 INT8 权重、INT16 激活、INT32 偏置/累加、Q1.15 PReLU、Q31 重定量化包。CPU `FixedReference` 逐层执行整数计算，分别测试了未参与训练的 FFmpeg 与 Pillow 25 帧留出集：

| 测试协议 | 冻结 R0 整数 PSNR | QAT seed123 | QAT seed456 | 两种子平均增益 |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg 合成降质 | 43.1528 dB | 43.4168（+0.2640） | 43.4756（+0.3227） | +0.2934 dB |
| Pillow 合成降质 | 43.1848 dB | 43.4135（+0.2286） | 43.4886（+0.3037） | +0.2662 dB |

按留出序列汇总的配对 PSNR 增益（相对各协议冻结 R0 整数基线）：

| 退化协议 | QAT seed | Bosphorus（10 帧） | ReadySetGo（10 帧） | ShakeNDry（5 帧） |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg | 123 | +0.3786 dB | +0.1926 dB | +0.1778 dB |
| FFmpeg | 456 | +0.4711 dB | +0.2378 dB | +0.1960 dB |
| Pillow | 123 | +0.3694 dB | +0.1473 dB | +0.1097 dB |
| Pillow | 456 | +0.4993 dB | +0.2243 dB | +0.1229 dB |

两种 seed、两种退化协议的各留出序列均有正平均配对增益。不过测试仅覆盖三个序列，且同一视频内帧存在时间相关性；这些帧不应被当成彼此独立的随机样本来夸大统计把握。

两个 seed 在两种退化协议下均优于冻结 R0 整数基线。seed456 QAT 候选另做 Set5 2×整数兼容性抽查：34.0165 dB，对照冻结 R0 同校准整数模型 34.0183 dB，差 −0.0018 dB；这不是 4×视频主指标。数据仍是小样本、有损 HEVC 合成对，所有指标来自软件整数参考，不能据此声称 RTL 或 FPGA 通过。

seed456 QAT 候选资产在 `.data/hybrid_4k_20261006/quant_cross_eval_adapt456qat5/R0adapt456_QAT5/`，包含量化参数和整数权重、四类 96×54 逐层向量，以及确定性输入下的全尺寸整数 Golden。包内 134 个文件摘要、48 组小向量阶段输出和 12 个全尺寸阶段摘要已全部通过 A 侧整数参考一致性校验。正式 `artifacts/quant` 和 `artifacts/full_integer_golden` 未更改。若交给 B 侧试跑，必须作为独立候选完整接入，逐字节对拍；不可混用正式 R0 ROM/Golden。

## 冻结 R0 与 QAT 候选的量化包兼容性

专门对比正式冻结 R0 与 seed456 QAT 的 `quant_params.json` 及二进制权重/偏置/PReLU 数组。两者 schema、模型名、I/O 和量化定义完全相同，五层名称/次序、卷积核、padding、OIHW 形状及输出 dtype 均一致，故满足当前冻结接口的**形状与格式兼容**。但这不等同于 ROM 可互换：

| 层 | INT8 权重变化 / 总数 | INT32 偏置变化 / 通道 | Q1.15 PReLU 变化 / 通道 |
| --- | ---: | ---: | ---: |
| feature | 21 / 400 | 16 / 16 | 11 / 16 |
| shrink | 0 / 128 | 8 / 8 | 5 / 8 |
| mapping0 | 26 / 576 | 8 / 8 | 3 / 8 |
| expand | 8 / 128 | 16 / 16 | 9 / 16 |
| subpixel | 279 / 1600 | 4 / 4 | — |

五层所有 per-output-channel weight scales 和 Q31 requant multiplier 都有变化；四个中间激活边界 scale 变化，而输入和最终 uint8 输出标度保持不变。`shrink` 虽然 128 个 INT8 权重字节完全相同，但 8 个 weight scale 全部变化，整数层语义仍不同。机器可读逐字段差异和 SHA-256 位于忽略文件 `.data/hybrid_4k_20261006/quant_candidate_compatibility_vs_frozen.json`，入口脚本为 `compare_quant_bundles.py`。因此若 B 侧验证候选，必须整体更换并版本绑定权重、scale、偏置、PReLU、Q31 参数、ROM、逐层向量和 Golden；不得只替换权重文件，也不能把候选 Golden 与正式 ROM 混搭。

## R1 3×3 输出头 QAT：低 MAC 候选复验

为评估能否在降低计算量同时弥补 R1 的整数画质损失，对 R1 3×3 输出头 checkpoint 使用同一 FFmpeg 训练组进行 5 轮 STE QAT；分别运行 seed123、seed456，学习率均为 `1e-6`。两个 checkpoint 均通过相同 Jockey 校准集导出 INT8/INT16/INT32/Q15/Q31 参数包，并在完全相同的 25 帧 FFmpeg 与 25 帧 Pillow 留出集上逐图评测。两个 QAT seed 相对同模型 R1 PTQ 分别提高 `+0.2423/+0.2385 dB`（合并 50 帧），说明它主要修复量化误差。

但相对冻结 R0 整数基线的配对结果仍然是：

| 协议 / seed | 25 帧均值 delta | Bosphorus（10） | ReadySetGo（10） | ShakeNDry（5） |
| --- | ---: | ---: | ---: | ---: |
| FFmpeg / 123 | −0.2972 dB | −0.0881 dB | −0.3963 dB | −0.5174 dB |
| FFmpeg / 456 | −0.2921 dB | −0.0629 dB | −0.4108 dB | −0.5133 dB |
| Pillow / 123 | −0.2370 dB | +0.0038 dB | −0.3562 dB | −0.4802 dB |
| Pillow / 456 | −0.2495 dB | −0.0084 dB | −0.3711 dB | −0.4887 dB |

R1 的计算量为 `0.9372672 GMAC/帧`，比冻结 R0 `1.4681088 GMAC/帧` 少约 `36.2%`。结果表明它在 Bosphorus 上接近基线，但 ReadySetGo/ShakeNDry 上存在约 `0.36–0.52 dB` 的差距；不能只报告总均值来掩盖场景差异。逐帧配对比较由 `compare_integer_evaluations.py` 生成，机器可读明细位于忽略目录 `.data/hybrid_4k_20261006/r1_qat_paired_metrics/`。seed456 独立整数包在 `.data/hybrid_4k_20261006/quant_r1_ptq_vs_qat_seed456/R1_QAT/`，包含 96×54 向量、全尺寸整数 Golden 和逐文件 SHA-256 清单；134 项文件、48 组逐层向量、12 个全尺寸阶段摘要已验证。因为末层是 3×3，R1 不是现有 R0 硬件配置的直接 ROM 替换项；若项目决定评估，B 需另开结构支持的实验路径。当前没有 RTL/综合、器件时序或板测证据。

### R1 两个 seed 延长至 15 轮 QAT 的探索

为确认增加 QAT 轮数能否进一步弥补 R1 差距，seed123、seed456 分别从同一 R1 适配 checkpoint 独立训练至 15 轮；训练数据、优化器设置和评测样本与各自 5 轮实验一致。两个 seed 的最佳验证 checkpoint 分别在第 12、14 轮。相对各自 5 轮 QAT，15 轮版本的整数留出 PSNR 在 FFmpeg 协议提高 `+0.0593/+0.0608 dB`，Pillow 协议提高 `+0.0301/+0.0395 dB`（seed123/456）。两个 15 轮 seed 之间的 50 帧配对差异仅 `+0.0066 dB`（FFmpeg）和 `−0.0032 dB`（Pillow）。

但相对冻结 R0 整数基线，15 轮 seed123/456 仍分别低 `0.2379/0.2313 dB`（FFmpeg）和 `0.2068/0.2100 dB`（Pillow）。按序列汇总，两种协议的 Bosphorus 差值为 `−0.013…+0.045 dB`，ReadySetGo 为 `−0.352…−0.332 dB`，ShakeNDry 为 `−0.463…−0.456 dB`。更长 QAT 的小幅收益在两个 seed 上可复现，但没有消除场景相关损失，尤其 ShakeNDry 仍低约 `0.46 dB`；因此 R1 不升格，15 轮产物也不是候选交付包。逐图机器可读对照保存在忽略目录 `.data/hybrid_4k_20261006/r1_qat_paired_metrics/seed{123,456}_15ep_vs_*.json`。

两个 seed 再延长至 30 轮后，最佳验证轮次均为 27；相对各自 15 轮整数版，留出 PSNR 提高 `+0.0468/+0.0186 dB`（seed123，FFmpeg/Pillow）和 `+0.0337/+0.0202 dB`（seed456）。30 轮两 seed 间差异仅 `0.0065/0.0016 dB`。但相对冻结 R0，30 轮版仍低约 `0.188–0.198 dB`；Bosphorus 略高 `0.027–0.065 dB`，ReadySetGo 仍低 `0.308–0.317 dB`，ShakeNDry 仍低 `0.408–0.442 dB`。增益可复现但递减，不建议只增加 QAT 轮数；需考虑结构/蒸馏目标或接受画质取舍。30 轮模型与配对结果仅在忽略 `.data/`，未生成正式包。

逐图机器可读对照保存在 `.data/hybrid_4k_20261006/r1_qat_paired_metrics/seed{123,456}_30ep_vs_*.json`。

## R1 加密训练帧复验

为检验 R1 约 0.28 dB 损失是否源自训练覆盖不足，在 Beauty、HoneyBee、YachtRide 三个训练序列各补取 60 帧，使用 stride=10、offset=5，与原训练帧索引错开；训练总量由 180 增至 360 帧，Jockey 验证与 25 帧留出测试未改变。由既有 R1 checkpoint 以 2.5e-6 学习率训练 30 轮，固定 seed 456。

| 指标 | R1 原候选 | 加密训练帧 R1 | R0T 参考 |
| --- | ---: | ---: | ---: |
| Jockey 最佳验证 MSE | 2.75951e-5 | 2.76145e-5 | — |
| 25 帧 PSNR 增益（相对 bicubic） | +2.13168 dB | +2.14389 dB | +2.41127 dB |
| 25 帧 PSNR（相对 R0T） | −0.27959 dB | −0.26738 dB | 0 dB |
| 25 帧 SSIM（相对 R0T） | −0.00100 | −0.00092 | 0 |

相较原 R1，增益只有 +0.01221 dB，且验证 MSE未改善；样本加密没有实质恢复候选画质损失。当前应继续保留 R0T/R0 为正式质量基准，R1 仍只是需团队确认损失门槛的算量候选。新增 HEVC 解码帧、配对数据、训练记录和 checkpoint 位于忽略目录 `.data/hybrid_4k_20261006/`，未发布或纳入正式 A 资产。

## R1 仅训练输出头试验

另做一项假设检验：从 R0T checkpoint 将 5×5 输出卷积中心裁为 3×3，冻结 FSRCNN 共享主干，只训练输出头 40 轮（180 帧训练组、4 patch/帧、Adam 初始学习率 1e-4）。Jockey 最佳验证 MSE 为 2.96913e-5，比完整微调 R1 的 2.75951e-5 高约 7.6%。该结果未达到继续评测门槛，因此没有运行 25 帧留出测试，也不计入候选表；验证清单与 checkpoint 保留在忽略数据目录。

## R4/R5 极限缩宽试验

R4/R5 以 16/8/16 冻结 R0 参数直接截取通道初始化后，各训练 30 轮；Jockey 最佳 MSE 分别为 1.37238e-4 和 3.06933e-4，因此都未以该版本进入留出评测。随后 R4 从已训练 R3 checkpoint 按 shrink、mapping、expand 的权重 L1 贡献选择 4 个 shrink 通道（索引 5、2、0、4），完整交叉裁剪连接后训练 40 轮，Jockey 验证 MSE 为 2.98648e-5；以 R0T 为教师蒸馏 40 轮后，最佳验证 MSE 降至 2.84079e-5。

蒸馏版 R4 使用两个独立随机种子复训。seed123/456 的 Jockey 最佳验证 MSE 分别为 2.84079e-5、2.83903e-5；25 帧留出 PSNR 增益分别为 +1.61849、+1.63204 dB，较 R0T 分别低 0.79278、0.77923 dB。两种子平均 PSNR 为 42.72580 dB（相对 bicubic +1.62526 dB），SSIM 平均为 0.97790（相对 R0T 低约 0.00191）。相较 R3，R4 减少约 36.3% MAC，平均 PSNR 低约 0.01153 dB，SSIM 高约 0.00038，构成一个值得团队比较的更低算量候选；但其相对 R0T 的画质差仍约 0.79 dB，不能直接升格为正式模型。R5 未以重要性初始化重训，也没有留出结果，不作质量结论。

## 视频流量估算（供 C 核查）

按每帧一次 540p Y8 输入读取、一次输出写入计算；中间帧场景额外计算 1080p Y8 整帧写/读。单位为十进制 MB/s，不含协议、DDR 效率、刷新、权重流量或显示消隐。

| 输出格式 | 30 fps 端点 | 30 fps + 1080p 中间帧落 DDR | 60 fps 端点 | 60 fps + 1080p 中间帧落 DDR |
| --- | ---: | ---: | ---: | ---: |
| 4K Y8 | 264.384 | 388.800 | 528.768 | 777.600 |
| 4K YUV420 8-bit | 388.800 | 513.216 | 777.600 | 1,026.432 |
| 4K RGB24 | 762.048 | 886.464 | 1,524.096 | 1,772.928 |

YUV420/RGB24 是输出格式的算术容量估算；本次实验只验证 Y8 软件链路，不代表 C 侧彩色视频、DDR 或吞吐实现。`performance_budget.py` 可生成完整帧缓存大小和 JSON 计算表至忽略目录 `.data/hybrid_4k_20261006/`。

## 8 帧彩色视频软件原型

另完成两段独立 8 帧软件展示链（帧索引 0、10、…、70，输出 12 fps）：从 UVG Beauty、Bosphorus 4K HEVC 解码并双三次缩小为 960×540 YUV420；Y 经 FSRCNN ×2 + Keys bicubic ×2，Cb/Cr 经 Keys bicubic ×4，输出 3840×2160 YUV420 MP4 和原始平面数据。FP32 结果使用冻结 R0，原产物位于忽略目录 `.data/hybrid_4k_20261006/color_demo_uvg_beauty_8frames/` 与 `color_demo_uvg_bosphorus_8frames/`。新增两份整数版分别使用正式冻结 R0 包和独立 R0-QAT seed456 候选，经 A 侧 CPU `FixedReference` 运行相同 Bosphorus 8 帧，输出目录是 `.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_frozen_r0_integer_8frames/` 和 `color_demo_uvg_bosphorus_qat_integer_8frames_v2/`。入口 `color_video_prototype.py`；各目录 `summary.json` 保存逐帧指标与来源哈希，30 个输出文件的 SHA-256 清单已创建并复核；整数模式通过 `--quant-dir` 选择参数/权重包。

Beauty 8 帧平均 Y-PSNR 为：纯双三次 45.7005 dB、混合 45.5890 dB（−0.1116 dB）；Bosphorus 8 帧为 42.6647 dB、44.6883 dB（+2.0235 dB）。对应 SSIM 分别为 Beauty `0.965454 / 0.965751`、Bosphorus `0.978507 / 0.983187`。片段差异说明存在内容依赖，不能只依据一个正向或负向小样本概括普遍效果。该演示验证的是软件解码、Y 超分、色度插值和视频封装流程；采用 FFmpeg 合成输入，与前文 Pillow 配对评测协议不同，也不证明真实摄像机输入、整数精度、FPGA/HDMI、通信协议或实时帧率。

同片段整数 QAT 版 Bosphorus 的 8 帧平均 Y-PSNR 为双三次 `42.6647 dB`、整数候选 `44.7280 dB`（`+2.0633 dB`），SSIM 为 `0.978507 / 0.983280`。与冻结 FP32 R0 逐帧配对后候选均值高约 `0.0398 dB`；与冻结 R0 整数版比较高 `0.3861 dB`。两份逐帧比较 JSON 分别为 `.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_fp32_vs_qat_integer_8frames.json` 和 `.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_integer_baseline_vs_qat456_8frames.json`。这仍是单片段小样本，整数版执行的是 A 侧 CPU 精确整数参考，不是 B RTL 仿真或板卡输出；此演示也不证明 FPGA 实时能力。

为直接比较模型而非只与插值基线比较，另用正式冻结 R0 整数量化包在完全相同的 Bosphorus 8 帧上生成对照。输入源 SHA-256、帧索引、退化设置及逐帧 bicubic 指标均相同；逐帧 QAT−冻结 R0 INT PSNR 增益范围 `+0.2935` 至 `+0.4263 dB`，均值 `+0.3861 dB`；SSIM 平均增益 `+0.002461`。逐帧记录位于忽略文件 `.data/hybrid_4k_20261006/color_demo_uvg_bosphorus_integer_baseline_vs_qat456_8frames.json`，比较入口为 `compare_color_video_runs.py`。结果仍仅代表此 8 帧片段和软件整数参考，不能替代独立多序列留出评测、RTL、板卡或实时验收。

## 当前交付与验证

- 可复现代码：`candidate_models.py`、`bicubic_reference.py`、`hybrid_reference.py`、`prepare_pairs.py`、`prepare_ffmpeg_pairs.py`、`extract_uvg_hevc_frames.py`、`evaluate_hybrid.py`、`train_candidate.py`、`qat_candidate.py`、`quantize_candidate_eval.py`、`generate_candidate_golden.py`、`manifest_candidate_bundle.py`、`verify_candidate_bundle.py`、`evaluate_integer_set5_candidate.py`、`color_video_prototype.py`、`compare_color_video_runs.py`、`compare_integer_evaluations.py`、`compare_quant_bundles.py`、`manifest_color_video_output.py`、`benchmark_cuda.py`、`render_comparison.py`。
- 给 B/队友的候选接入边界、数值包差异和验证步骤见 `QAT_CANDIDATE_HANDOFF_2026-10-06.md`；候选未进入正式 A/B/C。
- 训练 checkpoint、每轮 CSV 日志、完整逐帧 PSNR/SSIM、源文件清单和视觉对照图位于 `.data/hybrid_4k_20261006/`；这些文件未纳入 Git 跟踪。
- 单元测试覆盖模型形状/MAC、冻结 R0 权重兼容、候选初始化和裁剪、Keys 插值、uint8 量化、训练块对齐、抽帧索引、带宽预算、SSIM、整数视频尺寸、同源结果比较、视频产物哈希清单、量化包结构差异；运行通过 **32 项**。`compileall` 与 `git diff --check` 通过。
- 可视化示例：`.data/hybrid_4k_20261006/visual_Bosphorus_r0t/comparison.png`、`.data/hybrid_4k_20261006/visual_Bosphorus_r1d05/comparison.png`。图中依次对比解码参考、纯 bicubic、混合输出和放大 4 倍的绝对误差。

## 后续决策

1. 由项目组先明确可接受的 4K 画质损失阈值。若 `≤0.3 dB PSNR` 且 `≤0.001 SSIM` 可接受，R1 可作为低 MAC 候选继续；否则保留 R0。
2. 任何候选进入 B 前，必须单独生成匹配架构的新量化参数、整数权重、整数 Golden 与逐层向量，再由 B 做逐字节仿真；不能复用 R0 的 ROM/Golden。
3. B/C 仍需独立验证整数精度、资源、目标时钟、实现和实体板。当前结果没有完成上述任一项，也没有替换正式验收分支。
