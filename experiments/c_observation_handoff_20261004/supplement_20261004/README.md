# B 请求材料的补交附件

使用方法、下载位置和对应运行说明见仓库 [`docs/C_TO_B_EVIDENCE_SUPPLEMENT_2026-10-04.md`](../../../docs/C_TO_B_EVIDENCE_SUPPLEMENT_2026-10-04.md)。

本目录包含两份原失败 post-route DCP、完整 Vivado `.log/.jou` 包，以及 2025.2 成功基线的原始板测 ZIP 分片。`SUPPLEMENT_MANIFEST.json` 登记文件长度、SHA-256、完整运行日志链、32 帧原始返回核验结果，以及 ZIP 每一个成员的长度/SHA。

`baseline_raw_board.zip.part01` 与 `part02` 须按顺序拼成 ZIP 后核对整体 SHA，再解压。两份 DCP 是时序失败候选，只用于诊断；原成功 bitstream 在重组后的基线 ZIP 内。
