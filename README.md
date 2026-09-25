> **本分支入口（2026-09-25）**：`member-b-five-layer-stream` 是成员 B 的
> ACX750 五层流式 RTL 开发分支，当前代码、仿真和接口状态从
> [`acx750_rtl/README.md`](acx750_rtl/README.md) 进入。下面的 PYNQ-Z2/HLS
> 十小时冲刺说明是分支建立前继承的历史文档，原文和队友文件均保留。

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

## 当前可交付基线

- 可配置三层 INT8/INT32 Python 黄金模型，可输出逐层中间结果；
- 3×3 流窗口、9 路乘加、多输入/输出通道卷积、定点后处理和 2× Pixel Shuffle 的独立 HLS 验证；
- 末层 `卷积→后处理→Pixel Shuffle` dataflow 整链路，已完成 C 仿真和 PYNQ-Z2 HLS 综合；
- 预览版 Vivado IP：`results/hls_stage3/stage3_pipeline_preview.zip`；
- 不绑定 DMA/VDMA 的 PYNQ 数据布局、Y8/INT8 显式转换和尺寸校验；
- 汇总资源表：`results/HLS_SUMMARY.md`。

末层整链路当前 HLS 估算为 20 BRAM、11 DSP、3899 FF、4972 LUT，估算 Fmax 140.87 MHz。该数值不是完整三层网络资源，也不是 Vivado 实现或板上帧率结果。

## 快速复现

不重新综合即可运行 Python 黄金模型、驱动布局测试和报告汇总：

```powershell
.\scripts\run_quick_regression.ps1
```

重新运行末层 HLS C 仿真、综合并导出预览 IP：

```powershell
.\scripts\run_hls_stage3.ps1
```

完整尺寸、padding、量化数学、Pixel Shuffle 通道顺序和 AXI sideband 仍需成员 A/B 确认；未确认项记录在 `spec/TEAM_CONFIRMATION.md`。

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
