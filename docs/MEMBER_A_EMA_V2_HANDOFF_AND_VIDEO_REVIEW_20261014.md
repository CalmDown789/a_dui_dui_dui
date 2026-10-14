# EMA v2 候选交接与自然视频对照（2026-10-14）

## 当前结论

冻结部署版仍为 R0 `member-a-v1.0.1`。`R0_QAT_EMA_seed20261006_v2` 是同结构、同算力的实验权重候选。B 的候选 RTL 数值回归和 C 的独立 XSim 2025.2 复现均已通过；C 复现包记录 96 项小图逐层检查、两帧全尺寸检查共 98 项，失配为零。候选尚无独立综合、布局布线、bitstream 或实体板对拍。

C 的另一份证据是**冻结 R0** 的自然 8 帧板测：板端回传的 16,588,800 个 Y8 字节与 R0 Golden 逐字节一致。该次短序列协议循环为 609.541 ms/8 帧，约 13.1 fps；它不能代表候选、连续视频或 4K30。

## 候选身份与交接文件

| 对象 | SHA-256 / 标识 | 位置 |
| --- | --- | --- |
| EMA v2 checkpoint | `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a` | `experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/training/candidate_ema_qat_fp32.pth` |
| EMA v2 `quant_params.json` | `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809` | 同一候选目录下的 `quant/quant_params.json` |
| A 可移植候选资产 | `bundle_manifest.json` 登记 177 个文件 | 同一候选目录；含权重、偏置、PReLU、Q31、六组 96×54 向量及原有全尺寸 Golden |
| B 打包的 19 份候选 ROM | 集合 SHA-256 `8ef151f70646dfa6f0aa38a6b07d9381aee65e4bb64ef57b47e82a08707912bd` | 下述 B 复现包内 `package_identity/CANDIDATE_ROM_SHA256.txt`；每个文件哈希见下表 |
| B 候选 RTL 快照 | `B_RTL_SNAPSHOT_20261008_EMA_V2_NUMERIC_20261009`；14 文件清单 SHA-256 `1fd06ce205064d4f74da46c947b4779b9b5e90bb33aaf16a9209e820288a824b` | B 复现包；其回执的 `RTL_commit=None`，交接时应保留快照包与哈希 |
| B 原始复现包 | `34e25d96b81325f19333b2521b96f4bfa4bb50409ff9e2824b37bbbfb8f8e25a` | D 盘交接目录 `B_A_EMA_V2_REPRO_20261013_v2.zip` |
| C 独立 XSim 恢复复现证据 | `7033cfd3ef9221aa5770e9e51c5d860678c11f62a1a37e9a1908c33139621209` | D 盘交接目录 `C_EMA_V2_REPRO_RECOVERY_20261014.zip`；原始报告 `RESULT(4).md` |
| C 冻结 R0 自然 8 帧板测证据 | `6e33cd4e583bade0cf591da0ad52d98dcbdfdf0656cac54d12885317d1f36b4c` | D 盘交接目录 `C_R0_NATURAL8_BOARD_EVIDENCE_20261014.zip`；原始报告 `RESULT(5).md` |
| A 新增候选自然 8 帧整数 Golden | `1b8266493fec4c0df85da053ed5612d884a2c68f9ad6794017f1a2e8915209b7` | 本 A 分支 `experiments/model_optimization_20261005/evaluation/bbb_ema_v2_20261014/A_EMA_V2_NATURAL8_GOLDEN_20261014.zip`；D 盘交接目录另存同哈希副本 |

19 份 B 打包 ROM 的逐文件 SHA-256 来自 C 复现包中封存的清单；综合和板测必须按这份清单检查实际加载的 ROM：

| ROM | SHA-256 | ROM | SHA-256 |
| --- | --- | --- | --- |
| `expand_bias_packed.mem` | `8649d5da4aabb96fb11b5f93c609a7be8b9c0cafa1dfc6960b10361fcb6bb20a` | `expand_prelu_packed.mem` | `057d9f787961e9791d687ac1e13a8c915f20dc8092dc457b89e30baf516927e1` |
| `expand_q31_packed.mem` | `e38801924e81683b959545ef945a8dcfdf48d8f3d360b0b6b12b25ab4bca13c1` | `expand_weights_packed.mem` | `da7e3a0e7b510b736d6923f6dbb478de1c6b8a729f9b10601eb4e4ec403dd7f3` |
| `feature_bias_packed.mem` | `b84c5b6b2a66cc54612108d931d637e8dc4a4f4c3ae77662ba3aa0e5133cd502` | `feature_prelu_packed.mem` | `f43b7823bbe42f633a382136344129e6305b694ed2f43fcaa0244dc5a319a52b` |
| `feature_q31_packed.mem` | `9b1a1a1bf7687a1236773776a635047b79a34b2e0dfe69a1bc205cba8a018658` | `feature_weights_packed.mem` | `5592d27e9f7d78d202f461fdeca69e248e1453b7a1b2670c30b4993f694aa58a` |
| `mapping0_bias_packed.mem` | `d9cc6075a5579ba919d283e6b2d35222dcb8810eb499f8a1c247738a8a608da3` | `mapping0_prelu_packed.mem` | `d0fbf365da450639f4471205b4b554bb1d563b8b049c6c9ba86c4f9ee97065b3` |
| `mapping0_q31_packed.mem` | `61039f2a3ccd2c019f617041475271672b4137010d4e5f8fe018c7aeff6b5cdd` | `mapping0_weights_packed.mem` | `d0c2c81234730e1d8c51d9b26cc445b17d653c5b3cfdc7eb56a027829293373a` |
| `shrink_bias_packed.mem` | `5a8ad9762027383efa8ceb4202adcba482de0e9a3a99aa2c2ed1364d5de983d7` | `shrink_prelu_packed.mem` | `53f4e6014514bbfc91b7acffd7446819218cf1cc7f2f0f4db2498ff7f44143d0` |
| `shrink_q31_packed.mem` | `606f90036ae5cacf6168638dcce80b4b545d91f482b37d309d37b18bce42eaf7` | `shrink_weights_packed.mem` | `becf22961409ba68aed39387a1e2989e29077a84fbed27dca988b1ec516aee1f` |
| `subpixel_bias_packed.mem` | `7eba760bc8b871051f1db9f1cbef05b5e074a32e6c1460a6ead625135566ca29` | `subpixel_q31_packed.mem` | `fdad0bc768cbe7f3cd2320a47b648be9e3b69d7746bfdd709fbb1f988f16029f` |
| `subpixel_weights_packed.mem` | `62bead1d17c7333fda6abdbff0ba53aca99e10e72f11c8339817b6ccef63ceaa` | — | — |

这些是**打包后供 B RTL 读取的 ROM**，与 A 侧 `quant/*.bin` 的文件数量及字节排列不同；不能把 14 份 A `.bin` 直接替代 19 份 B `.mem`。R0 的 ROM 也不得与候选混用。

## 8 帧画质与同输入输出对照

复用 Big Buck Bunny 源片第 1440、1452、…、1524 帧。质量评测把原始 1280×720 图像作为 HR，按此前开发评测相同的 RGB→YCbCr-Y、Pillow 双三次生成 640×360 LR；R0 与候选均走精确整数参考，Y PSNR/SSIM 四周裁 2 像素。复算逐帧结果与旧 BBB 开发集 CSV 一致。

| 源帧 | R0 PSNR | EMA v2 PSNR | 增益 |
| ---: | ---: | ---: | ---: |
| 1440 | 43.055 | 43.726 | +0.671 dB |
| 1452 | 43.056 | 43.726 | +0.670 dB |
| 1464 | 47.665 | 49.920 | +2.255 dB |
| 1476 | 47.314 | 49.321 | +2.008 dB |
| 1488 | 47.527 | 49.689 | +2.162 dB |
| 1500 | 47.350 | 49.398 | +2.048 dB |
| 1512 | 47.603 | 49.859 | +2.257 dB |
| 1524 | 47.357 | 49.415 | +2.058 dB |
| **逐帧均值** | **46.366** | **48.132** | **+1.766 dB** |

SSIM 逐帧均值从 `0.988617` 到 `0.994086`，差值 `+0.005470`；8 帧 PSNR 均高于 R0。这个集合在模型开发时已经被观察过，且只有同一段动画的 8 帧，不能当作未触碰的独立质量测试。独立 DIV2K validation-HR 100 张的整数评测增益为 **+0.0664 dB**，更适合用于概括候选的泛化证据。局部图显示两版视觉差异细微，未完成主观评分。

另用 C 已板测的**同一份 960×540 输入字节**生成了 EMA v2 的 8 帧 1920×1080 Y8 Golden，输入逐帧哈希与 R0 自然 8 帧清单一致。候选输出与 R0 软件 Golden 的平均绝对差为 `0.4475` 个 Y8 码值；这是**两模型输出差异**，没有 1080p 真值，不能称为 PSNR 增益。新 ZIP 含 8 个输入和 8 个候选输出，`manifest.json` 逐文件记录字节数与 SHA-256，可供候选 bitstream 上板后逐字节对拍。

复算数据、逐帧哈希和局部图：`experiments/model_optimization_20261005/evaluation/bbb_ema_v2_20261014/`。图中第三列绝对差放大 32 倍，只用于定位差异，不能作为真实输出画面。

## 复现与下一道验收

在本 D 盘 A 仓库运行：

```powershell
& 'C:\Python314\python.exe' 'experiments\model_optimization_20261005\evaluate_ema_v2_natural8.py'
```

脚本核对视频、R0/候选 checkpoint、量化参数、现有 8 帧输入与 R0 Golden 的 SHA-256；重新计算两模型的 8 帧整数画质与候选 8 帧全尺寸输出，生成逐帧 CSV、摘要、局部图及候选 Golden ZIP。候选 ZIP 内文件以 `manifest.json` 的 SHA-256 为准。

交给 B/C 的下一步是使用上表确切候选权重和 ROM 做 150 MHz 独立综合、布局布线，记录完整约束下的资源、WNS/TNS、hold、DRC、DCP/BIT 哈希。若实现可下载，再用新 ZIP 的 8 帧输入和候选 Golden 在板上对拍，并单独记录发送、计算、回传和 PC 后处理耗时。正式 R0 的功能与速率证据继续单独记录；候选升版须在这些证据齐备后由团队决定。

视频素材：Big Buck Bunny (2008)，© Blender Foundation，CC BY 3.0；[许可](https://creativecommons.org/licenses/by/3.0/)、[来源](https://peach.blender.org/about/)。
