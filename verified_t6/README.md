# 独立验收后的交付入口

当前源码修订：`303b51d21b3004ddf5780c502ae5c1f3b81cefb6`。此提交将 C 的缓存暂停修复与对应测试台纳入独立 Git 历史，固定 B 与原板级 XDC 保持。

收到的 C 原始包 SHA256：`54a00085a31d641e5aadecd22b97742ab2119ee9baf806cfe05752cb73c19949`。892 个 ZIP 成员 CRC、890 个索引文件长度/SHA、Git 内索引绑定通过；80 个实际 UART 帧均与对应 Golden 逐字节相同。

| 组合 | UART | 原始板测证据独立验收 |
|---|---|---|
| 100MHz_pause0 | 20/20 一致 | 通过，使用历史原交付 BIT |
| 100MHz_pause1 | 20/20 一致 | 通过，使用 C 修复后重建 BIT |
| 150MHz_pause0 | 20/20 一致 | 通过，使用 C 修复后重建 BIT |
| 150MHz_pause1 | 20/20 一致 | C 报告通过；仍缺 46 个原始附件，独立证据验收未闭合 |

核验详细结果：[RAW_ACCEPTANCE_VERIFICATION.json](RAW_ACCEPTANCE_VERIFICATION.json)。96 个原始 VIO 槽已重新解码；13 份 ILA CSV 已按原始数据检查；100MHz 暂停四帧的 request/forced-block 均大于零。150MHz 暂停版相关缺项不使用报告中的摘要替代原件。

## 当前交付

- [accepted_board_images.zip](accepted_board_images.zip)：四组实际镜像及各自验收状态。自然视频联调固定选 `150MHz_pause0`，其 BIT SHA256 为 `a907a50af0528d2149b369a404eb0eade3b282a14e1e9b1e7419acf66b43c0cd`。
- [accepted_sourcekit.zip](accepted_sourcekit.zip)：包含完整旧依赖闭包与 C 修复后的源码、当前源码修订、完整 Git bundle 和新的成员清单。旧 T0–T5 资料保留历史身份，当前入口为包内 `README_CURRENT.md`。
- [DELIVERY_MANIFEST.json](DELIVERY_MANIFEST.json)：新包长度与 SHA；[SOURCE_IDENTITY.json](SOURCE_IDENTITY.json)：实际源码与镜像对应关系。

新机器重建结果要重新通过实现门控及实体测试；仅已有、精确哈希相同的实际镜像使用本次独立板测证据。C 冷上电和实体按键动作仍为操作者确认，数字空闲基线已核验。DCP 是独立可选材料，不在原始包内，本轮未在 Vivado 中重开网表。

## C 补交现有原件

[C_SUPPLEMENT_REQUIRED.json](C_SUPPLEMENT_REQUIRED.json) 列出 46 个原始路径。包缺失的是文件收集范围，不表示 UART 测试失败；不要求重跑已经取得的 80 帧。

在 C 机器的新目录中放本清单与 `pack_c_supplement.py`，用已安装 Python 执行：

```powershell
& 'C:\实际Python\python.exe' .\pack_c_supplement.py --output .\T6_150pause1_supplement.zip
```

脚本只读取清单中的文件并创建新包；已有输出不覆盖。若原路径不存在，保留报错，交付实际存在的正确原件及路径勘误，不补造日志或操作时间。

## 当前阶段边界

此处完成的是测试图案多帧与暂停观测验收；自然视频连续多帧输入→FPGA 超分→PC 回传播放另按自然视频包执行。200MHz 继续暂停，当前模型保持 d16/s8/m1/c16、INT8 权重/INT16 隐藏激活，不把成员 A 的长期候选替换进本次验收。
