# 成员 A：EMA v2 候选算法侧放行单

日期：2026-10-17

适用分支：`codex/member-a-r0qat456-bundle-20261007`

候选编号：`R0_QAT_EMA_seed20261006_v2`

身份清单勘误（2026-10-18）：首次放行提交 `f82bbc7` 把两组评测中的 6 个 JSON/CSV 文件按 Git 文本规则转换为 LF，致使提交字节与原始哈希不符。复查还发现 DIV2K 的 `SHA256SUMS.txt` 中 `README.md` 条目滞后。当前分支的修订提交将评测文件按生成时的原始字节保存、更新该 README 哈希，并增加 Git 提交内容核验；模型、Golden 和画质数值没有改变。**不要用 `f82bbc7` 的评测文件作哈希验收，取本分支最新提交。**

## 放行结论

**A 侧数据与算法合同核验通过，同意 B、C 以本单固定的 EMA v2 身份继续候选验证。**这是一张候选交接单，不是正式版本替换令。冻结版仍为 `member-a-v1.0.1`（R0）；不得用候选权重、ROM 或 Golden 覆盖 R0，也不得将本单解释为整机 4K30 已达标。

本次仅整理、核验并发布已有的 A 资产及收到的 B/C 证据副本，没有改动模型、量化参数、B/C RTL 或板卡工程。A 候选数据的来源提交为 `cb0ad8549967c5306cc25f88023658918d0fe03d`。下游如改变任一权重、量化参数、打包 ROM、网络结构或 PC 后处理合同，须另立候选并重新生成对应 Golden。

## 固定模型与数据合同

- 网络：FSRCNN 主干 `d16/s8/m1/c16`，原生稠密 `5×5 Conv 16→4 + PixelShuffle×2`；输入 `960×540` Y8，输出 `1920×1080` Y8，HWC 行优先。理论计算量 `1.4681088 G MAC/帧`，不是实测帧率。
- 整数语义：逐输出通道对称 INT8 权重、逐层 INT16 激活、INT32 偏置与饱和累加、逐通道 Q1.15 PReLU、Q31 重定量化、最近舍入且中点远离零、最终 uint8 饱和。具体逐层参数以候选目录内 `quant/quant_params.json` 和逐层向量为准。
- PC 4K 合同：对板端 `1920×1080` Y8 做 Keys 三次插值 `a=-0.5`、half-pixel 坐标、边界复制、float64 分离计算、中点远离零舍入、Y8 饱和，得到 `3840×2160` Y8。参考源码 SHA-256 为 `8ffa8363b6bbf0fcb2066f77ca0151ff4a31a43ea4dc2ed7e0cf97c207d011f6`。

## B、C 取数位置

以下路径均相对于本分支仓库根目录。先运行 `python scripts/verify_member_a_ema_v2_clearance.py`；该命令只核验文件身份，不代替仿真、综合或板测。完整机器可读清单见 [`ema_v2_clearance_manifest_20261017.json`](../artifacts/member_a_handoff/ema_v2_clearance_manifest_20261017.json)。

| 用途 | 文件或目录 | 身份 |
| --- | --- | --- |
| FP32 checkpoint | [`candidate_ema_qat_fp32.pth`](../experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/training/candidate_ema_qat_fp32.pth) | SHA-256 `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a` |
| 量化参数 | [`quant_params.json`](../experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/quant/quant_params.json) | SHA-256 `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809` |
| 整数权重、逐层向量、单帧 Golden | [候选交付目录](../experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/) | `bundle_manifest.json` 登记 177 个载荷文件；保留目录结构 |
| 同输入 Natural8 整数 Golden | [`A_EMA_V2_NATURAL8_GOLDEN_20261014.zip`](../experiments/model_optimization_20261005/evaluation/bbb_ema_v2_20261014/A_EMA_V2_NATURAL8_GOLDEN_20261014.zip) | SHA-256 `1b8266493fec4c0df85da053ed5612d884a2c68f9ad6794017f1a2e8915209b7`；8 输入、8 输出与逐文件清单 |
| 独立画质评测 | [DIV2K validation 100 张结果](../experiments/model_optimization_20261005/evaluation/official_div2k_valid_ema_v2_20261013/) | `summary.json`、`per_image_metrics.csv`、`audit_summary.json` |
| 4K 软件参考 | [`pc_postprocess_4k.py`](../src/member_a/pc_postprocess_4k.py) | 上述固定 SHA-256 |
| B 打包 ROM／数值复现（原包原样转存） | [`B_A_EMA_V2_REPRO_20261013_v2.zip`](../artifacts/member_a_handoff/received/B_A_EMA_V2_REPRO_20261013_v2.zip) | SHA-256 `34e25d96b81325f19333b2521b96f4bfa4bb50409ff9e2824b37bbbfb8f8e25a`；B 为生产者，A 不修改其内容 |
| C 阶段性验收材料（原包原样转存） | [`A_TASK_CLOSURE_20261016.zip`](../artifacts/member_a_handoff/received/A_TASK_CLOSURE_20261016.zip) 与 [收据](../artifacts/member_a_handoff/received/A_TASK_CLOSURE_20261016.zip.receipt.json) | ZIP SHA-256 `c0affddeb03977a5a4c117d9c1e18975549840ef0fe8836c98674a9c58fdf5fc`；原始大型档案未包含在该包内 |

B 侧 19 份**已打包**候选 ROM 的集合 SHA-256 为 `8ef151f70646dfa6f0aa38a6b07d9381aee65e4bb64ef57b47e82a08707912bd`，14 文件 RTL 快照标识为 `B_RTL_SNAPSHOT_20261008_EMA_V2_NUMERIC_20261009`。这 19 份 `.mem` 与 A 目录内的原始量化导出文件不是同一种排列，不能互换；逐文件 ROM 哈希见 [`MEMBER_A_EMA_V2_HANDOFF_AND_VIDEO_REVIEW_20261014.md`](MEMBER_A_EMA_V2_HANDOFF_AND_VIDEO_REVIEW_20261014.md)。

## 画质与当前硬件证据

独立的软件画质检查使用 DIV2K validation-HR 的 100 张图，Y 通道、Pillow 双三次生成 LR、边缘裁 2 像素；不是官方 MATLAB-LR 赛道。R0 整数均值为 **32.4043 dB / 0.914017 SSIM**，EMA v2 整数均值为 **32.4707 dB / 0.917499 SSIM**，平均提升 **0.0664 dB / 0.003482 SSIM**。配对 PSNR 增益的 bootstrap 95% 区间为 **+0.0445 至 +0.0987 dB**。这证明本测试口径下有小幅软件画质收益，不证明所有视频内容都会改善。

Big Buck Bunny 同片段 8 帧开发样本的平均 PSNR 提升为 **+1.766 dB**，但这些帧已用于开发观察，不能代替上述独立结果；候选与 R0 的板端同输入对照没有 1080p 真值，不能用两版输出差值冒充画质增益。Big Buck Bunny © Blender Foundation，CC BY 3.0；[素材与许可说明](https://peach.blender.org/about/)。仓库不提交 DIV2K 原始图像。

收到的 C 材料报告：EMA v2 的 8 帧板测共 `16,588,800` 个输出字节与 A 候选 Golden 一致；确切 DCP 复查的 150 MHz 静态 WNS 为 **+0.015 ns**，裕量很小。该材料还报告保存板帧的离线 4K 软件对拍为 0 差异。**本仓库转存的 C 汇总包没有包含其原始大型板测档案及 BIT/DCP；这些数字是 C 的报告，不是 A 在本次重新上板或重新实现所得。**R0 既有 758 帧在线 CSV 可复查，但原始 journal/事件档案在 C 的迁移副本中缺失，不能宣称原始协议已完整复审。

## 下游签收与正式升版门槛

1. **B：**核对 19 ROM、RTL 快照、完整 XDC、候选 BIT/DCP 的来源与哈希；保留正式实现的资源、时序、路由和告警原件。WNS +15 ps 仅说明该次约束下静态时序勉强通过，不代表温压角或板级可靠性。
2. **C：**以确切 EMA BIT 做连续多帧整机测试，保存可重审的原始收发记录和逐帧输入／输出哈希；完成真实启动与回退、物理 I/O 电气、真实显示刷新、持续帧率验收。报告必须分开列出纯核周期、传输、PC 后处理和显示环节；当前纯核周期未测。
3. **团队共同决定：**R0 保持冻结直至上述门槛按项目目标签收。当前 R0 连续测试约 10 fps，EMA 8 帧协议环节约 12.9 fps，均不能标为持续整机 4K30。若只发布功能试验版，应另立版本号并明确性能未达标，不覆盖 R0。

签收记录（由实际负责人填写，不预填签名）：

| 角色 | 应确认的内容 | 签收/日期 |
| --- | --- | --- |
| A | 本单身份、画质口径、Golden 与模型参数冻结 | 待确认 |
| B | ROM/RTL/实现身份与复现资料 | 待确认 |
| C | 板测、整机、显示及回退证据 | 待确认 |

若任何身份不符、Golden 出现首个非零差异或质量结论被新数据推翻，暂停候选升版并回报 A；不得悄悄替换文件或修改既有哈希。
