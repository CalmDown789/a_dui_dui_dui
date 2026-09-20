# Python 位精确参考原语

## 已完成

`python/sr_reference.py` 当前提供：

- HWC 激活、OIHW 权重排列的 3×3 INT8 卷积；
- INT32 偏置与累加；
- `valid`、`same` 两种可选 padding；
- 可配置整数 multiplier、shift、zero point；
- `nearest_away`、`toward_zero`、`floor` 三种舍入；
- 可选 INT8 饱和；
- 可配置负半轴定点 PReLU 候选；
- `channel=dy*2+dx` 候选顺序的 2× Pixel Shuffle。

## 自动测试

```powershell
.\scripts\run_python_reference.ps1
```

当前结果：

`PYTHON_REFERENCE_TEST_PASS tests=5`

测试包含：

1. 与 HLS 联合测试同口径的 4×5×2 有符号卷积；
2. same padding 的尺寸与边角补零；
3. 最近舍入与向零截断的正负数差异；
4. PReLU 候选定点斜率；
5. 2× Pixel Shuffle 通道顺序。

## 尚未冻结

- 三层网络究竟使用 same 还是 valid；
- 每层 scale/multiplier/shift/zero point；
- 舍入与溢出规则；
- PReLU 与 requantize 的先后顺序及斜率格式；
- 成员 B 的正式权重排列与 Pixel Shuffle 通道排列。

因此当前文件是可配置验证底座，不把任何候选配置冒充成员 B 的最终模型规则。收到成员 B 的参数后，再增加三层网络封装和逐层黄金向量导出。
