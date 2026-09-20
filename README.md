# 轻量视频超分 FPGA 10 小时冲刺

本仓库用于三人团队在 PYNQ-Z2 上完成 640×360 到 1280×720 的轻量超分演示。

项目冻结网络为三层 3×3 卷积 `1→8→16→4` 加 2 倍子像素重排，权重与激活为 INT8，卷积累加为 INT32。十小时内不实现原生 FSRCNN。

本仓库当前由成员 C 维护。成员 C 的任务是：

- 使用 Vitis HLS 编写加速器；
- 完成 C 仿真和位精确比对；
- 提供综合脚本、约束与 HLS IP；
- 编写 PYNQ Python 驱动；
- 支持成员 A 板上集成并整理汇报材料。

本机已确认安装 Vitis 2025.2，`vitis-run.bat` 支持 HLS、C 仿真、综合和实现流程。

详细安排见 [SPRINT_PLAN.md](SPRINT_PLAN.md)。现有 Verilog 代码说明见 [docs/RTL_BASELINE.md](docs/RTL_BASELINE.md)，这些代码只作为结构参考，不是本轮 HLS 最终交付。

## 目录规划

- `hls/`：Vitis HLS 加速器、C/C++ testbench 与配置
- `python/`：定点参考实现、测试向量工具
- `driver/`：PYNQ Python 驱动与调用示例
- `spec/`：冻结网络、数据布局、量化和寄存器规格
- `scripts/`：一键 C 仿真、综合和报告脚本
- `results/`：筛选后的仿真、综合、截图和指标
- `rtl/`、`tb/`：此前验证过的 Verilog 参考模块

Vivado、Vitis HLS 自动生成目录、缓存和临时日志不提交到 Git。
