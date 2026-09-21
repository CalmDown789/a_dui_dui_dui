# 三层网络位精确参考模型阶段记录

## 已实现

- 固定拓扑检查：`1→8→16→4` 三层 3×3 卷积；
- 前两层必须提供 PReLU 参数，第三层禁止在 Pixel Shuffle 前额外启用 PReLU；
- 每层逐输出通道 requant multiplier、shift、zero point、舍入和饱和；
- PReLU 可配置在 requant 前或后，用于等待成员 B 的最终规则；
- same/valid padding 均可运行；
- 返回三层中间 INT8 张量和最终 2× Pixel Shuffle 输出，便于逐层定位首个不一致点。

## 自动测试

1. 用中心抽头路由权重贯通完整 `1→8→16→4→Pixel Shuffle` 网络，同时检查 same/valid 的逐层尺寸与最终像素；
2. 检查逐通道后处理和 PReLU 顺序入口。

结果：

- `PYTHON_REFERENCE_TEST_PASS tests=5`
- `NETWORK_REFERENCE_TEST_PASS tests=2`

## 使用边界

当前测试参数是人为构造的确定性向量，不是成员 B 的真实模型。代码已经具备装载实际数组后逐层产生黄金结果的入口；在真实权重、量化 scale、zero point、padding 和 PReLU 顺序提供前，不生成或声称真实模型精度。

## 复现

```powershell
.\scripts\run_python_reference.ps1
.\scripts\run_python_network.ps1
```
