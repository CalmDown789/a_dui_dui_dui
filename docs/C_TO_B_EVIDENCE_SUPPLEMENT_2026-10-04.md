# C → B：DCP、完整日志和原始板测附件补交

日期：2026-10-04。对应初次交接提交 `86df150d45ff8f98b976053ce293688133bc12e9`，发布分支 `c-side-latest`。原候选、固定 B commit `6cc8ea4173d2a720f741e80b7cbd9279558ee93a` 和通过条件不变。

B 已收到初次交接的源码、完整 C XDC、IP 配置、观测契约和失败时序报告，本次补齐另外三类原件。没有重新跑 Vivado、修改 RTL 或重新上板。所有附件来自既有保存的运行。

## 1. 优先使用的失败 post-route DCP

| 候选 | 原运行目录 | 文件长度（字节） | SHA-256 |
|---|---|---:|---|
| 100 MHz | `board100_candidate_attempt01` | 43,124,050 | `74c10a5cdd625eb59aefb47074fed2146503823e7a2dc8b4e83b59017a827541` |
| 150 MHz | `board150_candidate_attempt06` | 44,478,826 | `f0b6873f946fd4305e55a4950b53f96c281c66e7bca7a7e573a531e917bedafc` |

可下载位置：

- [100 MHz post-route DCP 下载](https://github.com/CalmDown789/a_dui_dui_dui/raw/refs/heads/c-side-latest/experiments/c_observation_handoff_20261004/supplement_20261004/failed_dcp/candidate100_postroute.dcp)
- [150 MHz post-route DCP 下载](https://github.com/CalmDown789/a_dui_dui_dui/raw/refs/heads/c-side-latest/experiments/c_observation_handoff_20261004/supplement_20261004/failed_dcp/candidate150_postroute.dcp)

这两份均是失败的 `c_multiframe_synth_top` 完整物理设计：Vivado 2025.2 build 6299465，`xc7a200tfbg484-2`，保留完整 C 板级约束和原约束恢复结果；100/150 MHz WNS 分别 `−3.790/−6.984 ns`。DCP 原件哈希与先前报告一致，不能当作通过实现或上板镜像。

B 在有 Vivado 2025.2 的 runner 下载并校验长度/SHA 后，使用独立工作/报告目录 `open_checkpoint`，先核对 part、top、generated clocks 和当前约束，再查询 ILA、计数器、L5 pending1 控制网扇出/复制及路径。任何新物理优化应保存为新诊断 attempt，不能覆盖此 DCP，也不能修改时序例外来取得 PASS。

## 2. 完整 Vivado 日志

[完整日志 ZIP 下载](https://github.com/CalmDown789/a_dui_dui_dui/raw/refs/heads/c-side-latest/experiments/c_observation_handoff_20261004/supplement_20261004/full_vivado_logs.zip)

- ZIP 长度 **291,568 字节**，SHA-256 `826113ac922451ac4f27e5e0760ddc322fe67ac74317a95d9eceeb97169b9f70`。
- 包含 **38 个成员**：全部保存的实施 attempt 的 `.log/.jou` 与控制台输出、必要的阶段清单/接续收据、最终 IP 生成日志和阶段 6 Tcl。每个成员的长度/SHA 在补交 manifest 中登记。
- 100 MHz 主链是 `board100_candidate_attempt01/reports/vivado_synth_setup030.log`（含综合、布局、物理优化）及 `vivado_route_setup030.log`，对应 `.jou` 一并保留。
- 150 MHz 主链是 attempt05 的 `reports/vivado_synth.log`，再接 attempt06 的 `reports/vivado_place_setup030.log` 和 `vivado_route_setup030.log`，对应 `.jou` 和 `continuation_input.json` 均在包内。

150 MHz 的 attempt05 在保存综合 DCP 后因 Windows debug-hub 临时路径长度失败；attempt06 使用同 SHA 的综合 DCP，改用短路径后继续布局/物理优化和布线。日志和接续收据共同支持这条主链，不应把 attempt06 看成没有综合来源，也不能把此前 attempt01–04 的非通过记录当最终结果。

日志保存原机器的 Windows 与 `R:` 路径。这些是历史运行路径，不是 B runner 要照搬的目录；重跑时用自己的目录，并记录新命令与输出。

## 3. 2025.2 成功基线的原始板测附件

原始 ZIP 共 **69,648,541 字节**，SHA-256 `c0dd6ae92874b71dca9ff513be0455f2679d312a25e3147441b22e14756e9782`。为控制单个仓库附件大小，按顺序交付两个分片：

| 分片 | 字节数 | SHA-256 |
|---|---:|---|
| [part01 下载](https://github.com/CalmDown789/a_dui_dui_dui/raw/refs/heads/c-side-latest/experiments/c_observation_handoff_20261004/supplement_20261004/baseline_raw_board.zip.part01) | 40,000,000 | `7963e72f5663b0a3e96a45dfcbd23e26d9b5275f3e914735cfe53980ed46669f` |
| [part02 下载](https://github.com/CalmDown789/a_dui_dui_dui/raw/refs/heads/c-side-latest/experiments/c_observation_handoff_20261004/supplement_20261004/baseline_raw_board.zip.part02) | 29,648,541 | `6c60360a8e5108ab5ab63e51388cc2963694d2630cbb5134fc2ab8476f8ee7bc` |

将两片放在同一目录，先核对各片 SHA，按顺序合并，核对完整 ZIP SHA 再解压：

```python
from pathlib import Path
import hashlib
import shutil
import zipfile

parts = [Path('baseline_raw_board.zip.part01'), Path('baseline_raw_board.zip.part02')]
target = Path('baseline_raw_board.zip')
if target.exists():
    raise RuntimeError('保留已存在的 ZIP，请另选目录')
with target.open('wb') as output:
    for path in parts:
        with path.open('rb') as source:
            shutil.copyfileobj(source, output)
expected = 'c0dd6ae92874b71dca9ff513be0455f2679d312a25e3147441b22e14756e9782'
assert target.stat().st_size == 69648541
assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    destination = Path('baseline_raw_board')
    if destination.exists():
        raise RuntimeError('保留已存在的解压目录，请另选目录')
    archive.extractall(destination)
```

ZIP 中包括：

- 原 100/150 MHz 两档成功 bitstream。二者长度均为 9,730,787 字节；SHA 分别为 `524f72bc8ca01388f7305dbb02c48d5f1c68e1abe51900ce6c3738e667b80c3c` 与 `93dd60cffbefa43f6ab9f49697ff1d3f1ab6657445d01552c88842b6bc0760f6`。
- 100 MHz 四帧、150 MHz 四帧、150 MHz 连续 16 帧，以及冷上电后 JTAG 恢复四帧、S0 空闲按钮复位四帧，共 **32 帧原始 UART `.bin`**，连同各会话 JSON、烧录/采集日志和物理操作记录。
- 对应固定输入和期望输出文件，使下载方可以重新做逐帧长度/SHA/逐字节比较。
- `board_sessions_portable.json` 将原 Windows 绝对路径映射为 ZIP 内相对路径；也可在补交目录直接读取该 JSON。

打包前重新核对了全部 32 帧：输入、期望输出及原返回 SHA 符合记录，输出长度准确且逐字节失配为 0。此为历史原件复核，不是新板测；冷上电项仍限于 JTAG 恢复，S0 项仍限于空闲复位。成功基线不能代替新增内部观测版本的验证，也不关闭 BRAM 异步复位结构风险。

## 4. 完整附件清单与执行入口

- [补交目录](../experiments/c_observation_handoff_20261004/supplement_20261004/)
- [逐附件及 ZIP 成员长度/SHA 清单](../experiments/c_observation_handoff_20261004/supplement_20261004/SUPPLEMENT_MANIFEST.json)
- [原任务交接书与 B 模型启动指令](C_TO_B_OBSERVATION_HANDOFF_2026-10-04.md)

B 可立即从失败 DCP 和完整日志推进原交接书 T0–T2；原始基线板测 ZIP 是背景核验材料，无需等待开发板才能分析。C 暂不重新烧录或重跑已通过的基线。后续修复版仍须独立通过回归、完整 C XDC 的 post-route 门控，并交给 C 做新版本板测。
