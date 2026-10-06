# A→B 定点双三次接口交接

日期：2026-10-06
状态：A 侧软件参考和数值向量已生成；请 B 审核中间精度、时序组织和 RTL 接口后再冻结。

## 处理链

输入为冻结 R0 的 `1920×1080` 单通道 Y8 整数输出，按行优先排列；输出为 `3840×2160` 单通道 Y8。该阶段采用分离式 Keys cubic convolution，倍率 2，参数 `a=-0.5`，源坐标为：

```text
source_coordinate = (output_index + 0.5) / 2 - 0.5
```

水平方向先处理，再处理垂直方向。每个方向四个 tap，tap 索引越界时分别夹到最近边缘像素。相位行顺序为偶数输出位置、奇数输出位置；每行四个系数按源索引递增排列。

## 系数与运算

```text
even: [-384, 3712, 14208, -1152]   # Q2.14
odd:  [-1152, 14208, 3712, -384]   # Q2.14
sum per phase: 16384
```

这些有理数系数可被 Q14 精确表示。水平卷积保留无舍入的 Q14 有符号和；垂直卷积输入水平 Q14 值，保留 Q28 有符号累加；最终只舍入一次，再饱和到 `[0,255]`。舍入采用最近值，中点远离零。

范围证明使用系数绝对值和 `19456`：水平最大绝对值不超过 `255×19456 = 4,961,280`，因此有符号 24 位足够；垂直最大绝对值不超过 `255×19456² = 96,526,663,680`，因此有符号 38 位足够。边界夹取会合并 tap，不会增大系数绝对值和。参考模型使用 INT64 累加，水平中间以 INT32 容器保存。

## 可复现资料

- 协议：`artifacts/integer_bicubic_20261006/interp_contract.json`
- 系数：`artifacts/integer_bicubic_20261006/coefficients/`，含 JSON、NPY、小端 BIN、Verilog MEM 和 Vivado COE。
- 两套参考：`experiments/integer_bicubic_20261006/integer_bicubic.py`。`resize_scalar` 使用 Python 精确有理坐标与逐像素整数运算；`resize_chunked` 使用 NumPy 分块实现。
- 小型逐层向量：`artifacts/integer_bicubic_20261006/vectors/`，含输入、水平 Q14、垂直 Q28 累加和最终 Y8。
- 完整整数混合 Golden：`artifacts/integer_bicubic_20261006/mixed_golden/`。清单引用原冻结 A 的 540p 输入与 1080p 整数 CNN 输出，并附 4K Y8 输出。
- 连续软件帧：清单引用原 `artifacts/multiframe/` 的前三帧，独立生成并哈希 4K 输出。
- 哈希和范围：`source_manifest.json`、`golden_manifest.json`、`interpolation_error_report.json`。

在仓库根目录生成全部资产：

```powershell
$env:PYTHONPATH = '.;src'
python -m experiments.integer_bicubic_20261006.generate_assets
```

单独运行 raw Y8 参考：

```powershell
$env:PYTHONPATH = '.;src'
python -m experiments.integer_bicubic_20261006.cli `
  artifacts/full_integer_golden/output_1920x1080_y_u8.bin `
  artifacts/integer_bicubic_20261006/replayed_3840x2160_y_u8.bin `
  --width 1920 --height 1080
```

## 请 B 确认

1. `1920×1080` Y8 行优先输入、`3840×2160` Y8 行优先输出及偶/奇相位、tap 次序是否与 B 侧数据通路一致。
2. B 的 RAM/乘加调度能否保留水平 Q14 中间值，并用至少 38 位垂直累加；若需中途重定量化，请给出精确位宽、舍入、饱和位置和新协议版本。
3. 四 tap 的边缘复制是否适合首尾行列；如果 B 的行缓存接口使用其他边界行为，应先用向量确认。
4. 系数 ROM 的 signed INT16 解释、相位地址和 MEM/COE 字节/字顺序是否正确。

修改任何阶段的舍入、截位、饱和或边界规则后，B 应提交协议版本变更请求；A 会按新版本重生成全尺寸和边界 Golden。当前文件只提供软件数值契约，不声称已完成 RTL、综合、时序或板卡验证。
