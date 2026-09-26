# 冻结 FSRCNN 模型的累加范围核查

日期：2026-09-26。源提交：`6cc8ea4173d2a720f741e80b7cbd9279558ee93a`。

**结论：这套冻结 ROM 模型在合法输入范围内，所有乘积、加法树节点、8 相位累加前缀和最终加 bias 的结果均可安全容纳于 signed32；signed33 也安全。最宽的是 L5，覆盖全过程只需 29 个有符号位。** 这是整数区间计算，未修改 RTL、未运行仿真，也没有从测试图像的实际最大值外推。

机器可读结果见 [`acc_range_analysis.json`](acc_range_analysis.json)：含全部 52 个输出通道的权重正负和、bias、各相位部分和、各级加法树范围、8 个全局相位后的累加范围及原始文件哈希。

## 1 输入和 ROM 排列依据

- `rtl/b_real_ae29515/stream/fsrcnn_network_mem_top.sv:25` 声明完整 packed 向量，`:36` 起用 `$readmemh` 将每个参数文件的一整个十六进制字读入。十六进制字符串最右端是总线最低位。
- `experiments/l5_splitmem_20260924/rtl/b/phase_mac_pipeline.sv:58` 定义 `I=n/TAPS`、`TAP=n%TAPS`；`:71` 起的 8 个静态分支给出权重索引 `(oc*CIN+ic)*TAPS+tap`，每项 8 位，按二补码解释为 signed int8。
- bias 使用 `bias_flat[c*32+:32]`，即最低 32 位对应输出通道 0。见 `phase_accumulator_36.sv:68`。
- `fsrcnn_network_core.sv:53` 指定 L1 为 `ACT_W=8, ACT_UNSIGNED=1`，范围 `[0,255]`；L2–L5 指定 `ACT_W=16, ACT_UNSIGNED=0`，范围 `[-32768,32767]`。`phase_mac_pipeline.sv:108`–`:113` 实际分别做零扩展和符号扩展后乘 signed int8 权重。
- 实际相位映射为 `IN_GROUPS=CIN/IN_PAR`、`oc=(phase/IN_GROUPS)*OUT_PAR+lane`、`ic=(phase%IN_GROUPS)*IN_PAR+input_lane`。L1 每个通道只在 8 个全局相位之一贡献；其它四层每通道分 8 次累计。

另已阅读原导出器 `F:/FPGA预选/10h冲刺/acx750_rtl/scripts/export_member_b_parameter_rom.py:22`：它按 `values.flat` 顺序将第 i 个元素放在 `i*bits`，权重原数组为 OIHW。**不仅依赖该本机脚本说明：将 5 份权重和 5 份 bias 反解为原 int8 / little-endian int32 字节后，10/10 个 SHA-256 均等于已提交 ROM manifest 的 A 原始二进制哈希。** 19/19 个 packed 参数文件的规范化哈希也与 150 MHz 发布清单一致。解码次序与符号不存在未解决歧义。

| 层 | K / CIN / COUT | IN_PAR / OUT_PAR | 激活输入范围 |
|---|---|---|---|
| L1 feature | 5 / 1 / 16 | 1 / 2 | 0…255 |
| L2 shrink | 1 / 16 / 8 | 2 / 8 | −32768…32767 |
| L3 mapping0 | 3 / 8 / 8 | 1 / 8 | −32768…32767 |
| L4 expand | 1 / 8 / 16 | 1 / 16 | −32768…32767 |
| L5 subpixel | 5 / 16 / 4 | 2 / 4 | −32768…32767 |

## 2 计算方式

对一个输出通道，令 `P` 为全部正权重之和，`N` 为全部负权重之和，激活范围为 `[a,b]`，真实 bias 为 `B`：

```text
卷积最小值 = a*P + b*N
卷积最大值 = b*P + a*N
最终区间   = [a*P+b*N+B, b*P+a*N+B]
```

逐相位只对该相位选中的输入通道和 taps 应用同一公式，再按 RTL 相位顺序相加。乘积节点及每一级二叉加法树也逐项求区间，确认不存在上游 signed32 环绕后才得到表内结果的情况。L1–L5 的最大单相位部分和所需位数分别为 19、24、26、23、26。

输入元素按其完整合法范围独立取值。对某层独立的卷积窗口，这是给定权重的上下界；对实际前层生成的相关激活，它仍是保守上界。边界补零只会缩小可达范围。没有以已有测试张量替代全域分析。

## 3 各层最坏范围

“未加 bias”覆盖该层所有输出通道、所有合法 8 相位前缀和复位零值。不同列的极值可能来自不同通道，不能把两个极值当作同一输出样本。

| 层 | 未加 bias 的最小值 | 未加 bias 的最大值 | 加 bias 后最小值 | 加 bias 后最大值 | 覆盖全过程的 signed 位数 |
|---|---:|---:|---:|---:|---:|
| L1 | −175,185 | 254,745 | −176,169 | 266,439 | 20 |
| L2 | −30,080,574 | 30,080,556 | −30,036,571 | 30,124,559 | 26 |
| L3 | −97,581,967 | 97,581,263 | −97,565,526 | 97,597,704 | 28 |
| L4 | −19,267,272 | 19,267,308 | −19,028,546 | 19,506,034 | 26 |
| L5 | −139,294,756 | 139,294,529 | −139,171,868 | 139,417,417 | 29 |

signed32 的范围为 `[−2,147,483,648, 2,147,483,647]`。上述界限与它相距充分，故本模型不存在需要 ACC36 才能保住数值的卷积或 bias 加法。

## 4 相位前缀是否可能比最终结果更大

必须区分两个含义：

1. **相对同一通道未加 bias 的完整卷积区间，前缀不会越界。** 两种激活区间均包含 0，因此每个乘积的最小值不大于 0、最大值不小于 0；加入更多项只会扩大可取区间。逐项核查的全部 8 相位前缀均在完整无 bias 区间内。
2. **相对已加 bias 的最终区间，前缀可以越界。** bias 会平移最终区间。52 个通道均有非零 bias，各自至少一侧的无 bias 前缀范围超出其最终有 bias 区间。因此位宽核查使用两者的并集，没有只检查最终输出。例如 L5 的无 bias 最小值为 −139,294,756，比所有通道最终最小值 −139,171,868 更低，但仍只需 signed29。

对固定输入样本，后续正负贡献可能抵消，某个前缀的绝对值也可能大于那个样本的最终和。上面的区间证明已覆盖这种情况。

## 5 可应用的 RTL 优化边界

- 对这套 ROM、这里的网络参数和合法相位事务，`accum`、`sum_stage` 使用 signed32 有数学依据；signed33 也有充分余量。
- 若收窄累加寄存器，建议 bias 加法仍把两个 32 位操作数**显式符号扩展到 33 位**后再执行 `sat_i32`，保留原输出饱和、时延和握手。不要机械把所有 `36` 替换为 `32`，否则一般化输入下可能先环绕再判断饱和。
- 该证明没有覆盖给 `phase_accumulator` 任意灌入 8 个 signed32 部分和的独立模块契约；那比真实 MAC 可生成的数据范围更大。通用单元测试若故意输入超出 MAC 可达范围的值，不能用本证明宣布其原功能等价。
- ROM、K/CIN、激活位宽或 unsigned 设置改变后必须重算。此计算也不证明收窄一定改善 200 MHz 时序；实现后仍需 Golden/反压回归和 post-route 报告。
- 本文件是工程推导证据，不表示用户已经掌握；用户理解状态仍待解释与复述。

## 6 完整计算入口与独立复核

完整脚本为 [`analyze_acc_ranges.py`](analyze_acc_ranges.py)，只依赖 Python 标准库。从仓库根目录运行：

```powershell
python experiments/timing_200_20260926/analyze_acc_ranges.py
```

该命令重新生成同目录 `acc_range_analysis.json`；可用 `--output-json <路径>` 将复算结果写到别处。它先核对 19 份 ROM 与冻结发布清单、参考 RTL 的排列契约，再反解并核对 10 份权重/bias 的 A 源 SHA，最后重算 52 通道、416 个相位前缀和全部 MAC 加法树节点。任何源哈希、解码、范围或计数检查失败都会返回非零退出码。脚本不会修改 RTL，也不调用 Vivado 或仿真工具。

成功末尾应为：

```text
ROM_19_RELEASE_CANONICAL_PASS; WEIGHT_BIAS_10_DECODED_A_BINARY_SHA_PASS
ACC_FROZEN_MODEL_RANGE_PASS: output_channels=52 phase_prefixes=416 maximum_signed_bits=29
```

下面仅用 Python 标准库，从仓库根目录可复核各通道最终区间；完整相位和加法树的结果保存在 JSON 中。`unpack` 从最低位开始解码，因而按通道、输入通道、tap 的顺序返回。

```python
from pathlib import Path
import json, re

root = Path.cwd()
report = json.loads((root / 'experiments/timing_200_20260926/acc_range_analysis.json').read_text())
rom = root / 'rom/member_a_d16_s8_m1_c16'

def unpack(filename, bits, count):
    words = re.sub(r'//[^\n]*', '', (rom / filename).read_text(encoding='utf-8')).split()
    assert len(words) == 1 and len(words[0]) == count * bits // 4
    packed = int(words[0], 16)
    values = [(packed >> (i * bits)) & ((1 << bits) - 1) for i in range(count)]
    return [v - (1 << bits) if v & (1 << (bits - 1)) else v for v in values]

for layer in report['layers']:
    name, cin, cout, k = (layer[key] for key in ('name', 'CIN', 'COUT', 'K'))
    terms = cin * k * k
    weights = unpack(name + '_weights_packed.mem', 8, cout * terms)
    biases = unpack(name + '_bias_packed.mem', 32, cout)
    a, b = layer['input_range']
    for c, channel in enumerate(layer['channels']):
        part = weights[c * terms:(c + 1) * terms]
        p, n = sum(v for v in part if v > 0), sum(v for v in part if v < 0)
        lo, hi = a*p + b*n + biases[c], b*p + a*n + biases[c]
        assert (lo, hi) == (channel['final_with_bias']['minimum'], channel['final_with_bias']['maximum'])
        assert -(1 << 31) <= lo <= hi < (1 << 31)
print('ALL_52_CHANNEL_FINAL_RANGES_PASS')
```
