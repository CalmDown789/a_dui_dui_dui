# C 内部观测候选交接包（2026-10-04）

> B 请求的失败 DCP、完整 Vivado 日志和原始基线板测附件现已在 [`supplement_20261004/`](supplement_20261004/) 补齐。下载和长度/SHA 见[补交说明](../../docs/C_TO_B_EVIDENCE_SUPPLEMENT_2026-10-04.md)。下文原件省略范围描述对应初次交接包，补交文件使用独立 manifest。

请先读仓库根目录 [`docs/C_TO_B_OBSERVATION_HANDOFF_2026-10-04.md`](../../docs/C_TO_B_OBSERVATION_HANDOFF_2026-10-04.md)，再用本目录中的文件分析和复跑。可把该文档第 8 节原样发送给负责的 B 模型。

## 包内内容

- `observe_candidate01/overlay/multiframe/`：新增观察器候选的完整 C 多帧 RTL、完整 C 板级 XDC、测试台。
- `observe_candidate01/scripts/`：已用 Vivado/XSim 2025.2 运行的生成、仿真、综合和实现脚本。
- `observe_candidate01/b_reference/`：候选测试/脚本所需的固定 B RTL 依赖和 19 个模型参数 ROM 副本。它们受下文所列固定 B 提交约束。
- `observe_candidate01/generated_ip/`：实际生成的 ILA/VIO `.xci` 配置。最终物理产物可在有 Vivado 的机器上重新生成。
- `observe_candidate01/fixtures/simulation/` 与 `sim/controlled_observe03/`：小型固定向量、阶段 5 双帧受控暂停 PASS 记录和仿真日志。
- `baseline/`：先前已通过的 2025.2 C overlay、建置脚本、工具信息与基线收据。
- `baseline_board_evidence.zip`：100/150 MHz 原板测会话摘要、已通过连续 16 帧会话与冷上电/S0 恢复收据；该证据保持基线来源。
- `baseline_vivado_reports.zip`：基线 C route 报告及对照用 B 报告。
- `candidate_failure_reports.zip`：100/150 MHz 新候选完整 post-route、时序、DRC、布线、clock、utilization 报告与建置清单。
- `audit/`、`contracts/`、`reference/`：阶段状态、诊断结果、934 位映射及 B 的 2026-09-26 C 端验收要求。
- `PACKAGE_MANIFEST.json`：逐文件以及三个 ZIP 的字节数和 SHA-256。

在本目录执行 `python verify_package.py` 核对导出内容。文本报告需要先解压，之后交接书中的证据相对路径即可定位：

```text
python -m zipfile -e baseline_board_evidence.zip baseline
python -m zipfile -e baseline_vivado_reports.zip .
python -m zipfile -e candidate_failure_reports.zip observe_candidate01
```

原审计 JSON 保留历史运行机器的绝对路径，交接包采用上面的相对目录映射；未导出的原 DCP、原图像和部分历史审计文件仍在 C 本机，导出范围以 manifest 为准。

为避免仓库保存大量图像像素，板测 ZIP 中保留运行收据及逐帧字节长度、Golden 对拍状态和 SHA-256，不包含 UART 原始图像文件或 bitstream。C 本地基线目录保有原始采集。完整失败时序文本报告都在候选报告 ZIP 中，不只保留摘录。综合/布线检查点 DCP 不打包，摘要交接书登记了其哈希。

## 固定来源检查

固定 B 提交必须为 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`；固定 A 输入来源为 `98c82f394bdfba85bc2959bede9760edc4d6862f`。不得从已更新的 `member-b-five-layer-stream` HEAD 取代它。为可重复执行现有阶段 6 Tcl，模型应在包之外克隆/检出此准确 B commit，并按脚本所列 15 个 B RTL 文件与 19 个模型参数 ROM 做 Git blob 核验。仓库中的 B 子目录副本便于直接阅读和小型仿真，不替代 `.git` blob 来源校验。

候选尝试使用 Vivado/XSim 2025.2 SW Build 6299465、`xc7a200tfbg484-2`、顶层 `c_multiframe_synth_top`、完整 C XDC。交接包里的脚本保留本地试验痕迹和 Windows 工具路径：B 在自己的 runner 上应先核验输入，再将工作/输出目录改到 runner 的临时路径，保留完整哈希和报告。不要让脚本在 C 的原 dirty 工作树或冻结基线上运行。

阶段 6 准备脚本从 `H/b_repro_reference` 核验精确 B Git blob。B 可将该固定提交的 checkout 建在此目录；避免使用当前仓库自身的 HEAD 冒充 B 的来源。准备脚本原 IP 输入位置为 `observe_candidate01/ipgen_attempt06/ip/`，请将包内 `generated_ip/` 对应两层目录复制到该位置，或者使用 `scripts/configure_observation_debug_ip.tcl` 在新会话中生成并记录新 XCI 哈希。`run_alignment_sim.py` 原版调用 Windows `.bat` 和 `toolchain.json`，跨平台 runner 需要适配启动器并单独留下验证记录，不能声称原命令在 Linux 已实跑。

板上无需参与 B 的 T0–T5 根因定位、代码变更、XSim 回归、完整实现或 BIT/LTX 生成。T6 新版本烧录、VIO/ILA 读取、实际强制背压和逐帧 UART 板测由 C 执行。

## 当前结果索引

已通过基线：100 MHz 四帧板测；150 MHz 四帧及连续 16 帧板测，帧间不复位且逐帧 bit-exact。新 `observe_candidate01`：受控两帧功能回归 PASS；150 MHz setup WNS `−6.984 ns`、100 MHz `−3.790 ns`，均有 setup endpoints 失败，**未生成新 bitstream，未上板**。准确范围、禁止事项、逐阶段交付物和验收条件见仓库根目录交接书。

运行本包已有阶段 5 模拟证据只能核对历史结果。B 对 RTL 或调试 IP 所作的任何更改都必须产生新的源码清单、回归收据和从新源开始的 post-route 实现报告，不能借用本包失败版本或已通过基线的 timing/BIT 结果。
