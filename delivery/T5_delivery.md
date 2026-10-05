# T5 C板测交付索引

> 2026-10-05 补充：本文件保存原 T5 离线交付身份。当前四个实测镜像的 T6 已通过，详见 [阶段验收报告](t6_20261005/T6_ACCEPTANCE_REPORT.md) 与 [T6状态](t6_20261005/T6_STATUS.json)。其中三组合为 C 覆盖修复重建，不能把这里的旧 BIT 哈希直接升级为 BOARD_PASS。自然视频验收未运行，200MHz继续暂停。

T0–T5离线完成，四组合仅 **BOARD_READY**；实体T6 **NOT_RUN**。先读C_BOARD_GUIDE.md，按每组合独立BIT/LTX及哈希配置；不能继承历史基线板测PASS。

| MHz | pause | 本轮最终attempt | WNS/WHS/WPWS(ns) | 压力WNS(ns) |
|---:|---:|---|---|---:|
| 100 | 0 | f100_p0_a01 | +0.717/+0.036/+3.870 | +0.417 |
| 100 | 1 | f100_p1_a03 | +1.088/+0.036/+3.870 | +0.788 |
| 150 | 0 | f150_p0_a02 | +0.404/+0.022/+2.203 | +0.104 |
| 150 | 1 | f150_p1_a01 | +0.252/+0.014/+2.203 | -0.048 |

签核按原约束：TNS/THS/TPWS=0、setup/hold/pulse非负、route全通且errors0、DRC Error0、NSTD/UCIO Error、no_clock/internal_unconstrained0、真实固定B层级通过。额外+0.300ns压力另报，不能与名义裕量混用。原板级XDC未改，器件jitter保留。

150MHz pause=1：额外压力setup未通过，WNS-0.048ns/TNS-0.397ns/10端点；正式原约束全部门控通过。压力原始失败与route critical warning保留，不宣称四档都通过额外压力。

## 镜像身份

### 100MHz pause=0

板测ZIP相对目录：`100mhz_pause0`；后布线DCP SHA：`05ed951d999c0aa2974394620675a190cefa23b214a07d049ddfe142aae8e493`。

- `c_board_100mhz.bit`，9730787字节，SHA256 `d9b97465ce259d23fd4879c927feaa11366605dfa9dd008e09cfdcf6d3adb5d5`。
- `c_board_100mhz.ltx`，358912字节，SHA256 `e8bb272f5d498fc2418cabc0ad18dfa795552aa933b1c90a4c735591e7cefbe5`。

ILA UUID `F965FFB8C14853F9928969F0B32C7F39`；VIO UUID `36E787058A5D5F8DA3A996B8F9D5F3E4`。934位probe1 DATA；其余9探针DATA_TRIGGER；VIO256/256/256/166/1/5，输出5位初值0。

### 100MHz pause=1

板测ZIP相对目录：`100mhz_pause1`；后布线DCP SHA：`ad2ba9afd150f3a133146de358eda3271b8c67024420f46a393220180caf5e71`。

- `c_board_100mhz.bit`，9730787字节，SHA256 `6718bcc859d76c8b33b00227e8d9f96839dc6abf10c4f69bc07c7f1f7df425af`。
- `c_board_100mhz.ltx`，358912字节，SHA256 `e8bb272f5d498fc2418cabc0ad18dfa795552aa933b1c90a4c735591e7cefbe5`。

ILA UUID `F965FFB8C14853F9928969F0B32C7F39`；VIO UUID `36E787058A5D5F8DA3A996B8F9D5F3E4`。934位probe1 DATA；其余9探针DATA_TRIGGER；VIO256/256/256/166/1/5，输出5位初值0。

### 150MHz pause=0

板测ZIP相对目录：`150mhz_pause0`；后布线DCP SHA：`5c8284e200ff2aea6cc7b47b4634ae35d1cf6429cc976927f3d93de0e52a012d`。

- `c_board_150mhz.bit`，9730787字节，SHA256 `fb53260d6ece72c35f33d81e9602b911b180b09ca4bc7810f1890552cb8b44a7`。
- `c_board_150mhz.ltx`，358912字节，SHA256 `1aa99107dbfbf3ee5ef7edebe88d7f581427ff38c15410fe132c96a67445bb66`。

ILA UUID `F965FFB8C14853F9928969F0B32C7F39`；VIO UUID `36E787058A5D5F8DA3A996B8F9D5F3E4`。934位probe1 DATA；其余9探针DATA_TRIGGER；VIO256/256/256/166/1/5，输出5位初值0。

### 150MHz pause=1

板测ZIP相对目录：`150mhz_pause1`；后布线DCP SHA：`f6caed31eb364a5010db50063dccfa4530df8f4746fa32286f74791f5b43b1e3`。

- `c_board_150mhz.bit`，9730787字节，SHA256 `87b0a97ce25d10acd8683311f20f5b4a4817ca238404dbdcd3fbeac91b3184f4`。
- `c_board_150mhz.ltx`，358912字节，SHA256 `1aa99107dbfbf3ee5ef7edebe88d7f581427ff38c15410fe132c96a67445bb66`。

ILA UUID `F965FFB8C14853F9928969F0B32C7F39`；VIO UUID `36E787058A5D5F8DA3A996B8F9D5F3E4`。934位probe1 DATA；其余9探针DATA_TRIGGER；VIO256/256/256/166/1/5，输出5位初值0。

## 源与复现

最小补丁提交 `659a86183aa84174d4aad0a5aae99ee482e0a6e4`（独立本地repo，未推送）；原C `86df150d45ff8f98b976053ce293688133bc12e9`，固定B `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`，A98c82f3。补丁SHA `e884b6165d6c0993e1e185b641bc555f94591086c83c507635bcea039263144a`。`source_review.bundle`可在新目录clone审查，源码包的candidate才是完整重建入口。

四份ZIP：board_images直接供C上板；sourcekit含固定源/ROM/IP/原始模板/脚本/契约/测试向量；evidence含全部通过和失败尝试报告、日志、命令、UART实际返回和测试台；checkpoints按SHA去重保存本轮DCP和冻结输入原字节，object_index映射每个原路径。ZIP及每成员长度/SHA/CRC由DELIVERY_MANIFEST.json与各PACKAGE_MANIFEST.json签核。

首两个直接Vivado作业的命令/起止来自原jou/log，退出码来自实际tool session完成回执，后补command_reconstructed.json明确是回顾索引；后续作业command.json在启动/完成时记录。工具错误和检查脚本错误不计作硬件失败；150MHz a01实际setup失败完整保留。

## 尚待C与回退

按指南进行四帧、连续16帧、31字段实读、ILA实际导出、受控暂停forced>0且释放后Golden一致。现有通路停止PC读串口不自动形成B内部背压。原100/150基线BIT可直接JTAG回退，准确SHA见C_BOARD_GUIDE.md。REQP-1839/1840/BRAM异步复位结构仍OPEN；报告20条上限不代表总违规数。Flash自主启动、忙时复位、自然视频播放、HDMI、30fps及200MHz不由此次离线通过升级；用户掌握状态未升级。
