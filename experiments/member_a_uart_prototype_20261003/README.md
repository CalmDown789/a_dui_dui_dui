# A 侧双向 UART 原型客户端

此目录与正式 A 工具分开。依据用户提供的 C 侧隔离原型约定实现，协议状态固定为 **PROTOTYPE_UNCONFIRMED**。不是已冻结协议，不表示正式 C 代码已有 RX，也不表示实体板多帧已经通过。

提供的 C 原型说明位于另一台机器的 `C:/Users/Administrator/WorkBuddy/srtp/_c150_multiframe_uart_20261003/experiments/c_multiframe_uart_20261003/host/README.md`。当前机器无法读取该文件，原型没有可绑定的 Git 提交。这里仅使用用户在本对话给出的字段说明；进一步联调前还需取得原文、源码版本及板测配置。

## 实现的实验格式

921600 baud、8N1。输入固定 518400 字节 uint8 Y，从冻结输入 `.bin` 读取，不重新做颜色转换。每个输入包为 20 字节头部加负载：

| 字节偏移 | 字段 | 编码 |
| --- | --- | --- |
| 0～3 | magic | ASCII `SRTP` |
| 4～7 | frame_id | 小端 uint32 |
| 8～11 | payload_length | 小端 uint32，固定 518400 |
| 12～15 | payload_crc | 小端 uint32，负载的 IEEE CRC-32 |
| 16～19 | header_crc | 小端 uint32，仅覆盖偏移 4～15 的 12 字节 |
| 20 起 | 输入 Y | 960×540，行优先，无额外填充 |

本客户端使用 CRC-32/ISO-HDLC：poly 0x04C11DB7（反射实现 0xEDB88320），init 0xFFFFFFFF，refin/refout=true，xorout 0xFFFFFFFF；`123456789` 的 check 为 0xCBF43926。Python `zlib.crc32` 给出相同结果。该解释有软件测试，但仍需 C 确认并用同一字节向量对齐硬件实现。

输出按原型描述仅收 2073600 个裸 Y 字节，无输出帧头、线上帧号、CRC、ACK 或状态查询。保存的输出帧号只是主机绑定的已发送帧号，`protocol_frame_id_observed=false`、CRC 为 NOT_CHECKED。先收齐一帧并检查有限尾部窗口，才发送下一帧；超时或尾部异常立即停止，不自动重发，不发送未定义的软件复位命令。

## 实验入口

在 A 仓库根目录运行。不要对正式 TX-only bitstream 运行发送端；先确认下载的是相匹配的隔离 RX 原型。外部复位后帧号从 0 开始并连续递增。`--experimental-prototype` 只承认实验风险，不代表协议已被团队确认。

```powershell
python -m pip install pyserial==3.5
python experiments/member_a_uart_prototype_20261003/host/stop_wait_client.py --manifest artifacts/authority_pair/manifest.json --port COM7 --output-dir 'D:\Codex File\dialogue file\board_capture\prototype_pair_01' --experimental-prototype --external-reset-confirmed --control-lines-safe
```

端口、原型部署和复位由现场确认。原始输入长度/哈希先检查；已有输出目录拒绝覆盖。RTS/DTR 在打开前设置 false，但驱动仍可能有短暂跳变，必须事先核验接线安全。不开软/硬流控；该原型没有可供主机使用的 credit/ACK，不能因此推广到未确认的缓冲方案。

数据保存后：

```powershell
python scripts/export_pc_player.py --manifest 'D:\Codex File\dialogue file\board_capture\prototype_pair_01\reference\manifest.json' --received-manifest 'D:\Codex File\dialogue file\board_capture\prototype_pair_01\received_manifest.json' --output 'D:\Codex File\dialogue file\board_capture\prototype_pair_01\player.html'
```

目录中 `reference/` 是输入和 Golden 的只读来源副本，`frame_NNNN/rx/` 才是接收文件，不能把两者混为板卡输出。`comparison.json` 为全序列对拍；异常会话必须 FAIL，即使已有几帧匹配。`input_packet.bin` 是计划发送包；`tx_submitted.bin` 记录每次写请求，短写时可能重复提交未接受的尾部；`tx_accepted.bin` 仅记录成功返回的接受字节，不证明 FPGA 已接受。当串口写操作抛错时，实际发出了多少字节可能未知，不能凭该文件推断电气层数据完整。

## 验证和后续门槛

软件测试覆盖头部及负载 CRC、字节序、精确长度、短写/短读、stop-and-wait、不完整输出、尾部额外字节、错字节、零进展写超时及不确定写错误。它不等于板测。正式启用前须由 A/C 冻结字段和 CRC 全参数，取得源码及 bitstream 版本，并用不同的两帧、随后 8 帧实收文件完成对拍和播放验收。UDP 尚未定义或实现，本目录不补造 UDP 格式。

软件完整联测入口：`python experiments/member_a_uart_prototype_20261003/host/selftest.py`。报告 `artifacts/uart_prototype_selftest.json` 包含两帧和 8 帧端点样例、故意错字节案例、播放器退出码、两帧输入包的 20 字节头部与完整 SHA-256。软件端点检查输入 CRC 后直接复制 Golden 作为返回值，不执行 C RTL、不打开物理端口，不能推定硬件兼容。完整回归还包括 `tests/test_uart_prototype.py` 的异常处理测试。

8 帧实验入口将 `--manifest` 改为 `artifacts/multiframe/manifest.json`，并选择一个未存在的新输出目录。视频两帧子集 `[0,7]` 不符合复位后连续编号，客户端会拒绝；不要修改冻结数据编号来强行通过。

若仅解压便携交接包，使用包内的 `artifacts/multiframe/manifest.json`：旧权威帧成对包是 `[0,1]`，完整视频包是 `[0..7]`，视频两帧检查包 `[0,7]` 不能用于本原型。上述 `selftest.py` 与 pytest 入口要求完整 A 源码 checkout，不在便携取数包内运行。

在当前 921600、8N1 条件下，裸 1080p Y 回传理论时间为 `2073600×10/921600=22.5 s`；输入至少 `518400×10/921600=5.625 s`。逐帧 stop-and-wait 的输入和输出共约 28.125 s，加上头部、计算和软件等待；这是链路算术估算，不是核心吞吐或实测持续帧率，不能宣称实时视频。
