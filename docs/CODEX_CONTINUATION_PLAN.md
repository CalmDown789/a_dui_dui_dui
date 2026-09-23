# 接续任务清单（2026-09-23）

本仓库分支 `c-side-latest`。用户要求暂不上云；先读取本地最新提交、
`docs/B_C_REAL_ACCEPTANCE_REPORT.md` 和本文件，不要把未通过的功能写成通过。
冻结工具链 `E:\Xilinx\Vivado\2022.2`，器件 `xc7a200tfbg484-2`。

## 已取得的硬证据

- B 真五层 RTL `ae29515` 的 15 文件闭包已接入 `C_USE_B_REAL`；19 个 A 参数 ROM
  已入库，来源见 `_b_vendor_manifest.json`。
- 96×54 的四组整数 Golden 均 FAIL，见 `report/sim_result.txt`。
- 960×540 整帧输出 2,073,600/2,073,600，失配 2,049,726，X=0；
  帧/条带尾标记与保持规则通过，见 `report/b_real_full_summary.json`。
- 6×5 的逐层探针：L1 INT32 MAC 0/480 失配，L1 后处理 INT16 186/480
  失配，首次为 token 0/channel 1，DUT `fa6b`、参考 `0f7b`；
  见 `report/b_real_layer_probe.txt`。B 原 TB 有同沿索引竞争风险，
  因此逐层探针用非阻塞索引推进。
- A 整帧数据在 `member-a@98c82f3` 有书面确认和匹配哈希，但该提交后来
  从 `main` 撤回；需 A 明确正式重新发布位置。

## 可分别交给其他账号的任务

### 任务 1：定位并修正 B 第一层后处理

从 `report/b_real_layer_probe.txt` 出发，比较
`rtl/b_real_ae29515/stream/vector_postprocess_shared.sv` 与
`rtl/b_real_ae29515/postprocess/prelu_requantize.sv` 的每拍输入、
共享槽位元数据、Q15/Q31 参数及输出。先在**副本或新分支**验证修正，
保留 `ae29515` 原始 vendor 基线。用 6×5 逐层值、96×54 四组和整帧 A
整数 Golden 复测。C 侧仿真命令：

```powershell
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/run_sim.tcl' -tclargs tb_b_real_bit_exact
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/run_sim.tcl' -tclargs tb_b_real_full
```

整帧约 23 分钟，完成后运行 `scripts/extract_b_real_full_summary.py`；
其结果要与 A Golden SHA-256 一起留档。若 B 在 XSim 2025.2 的 PASS
仍成立，应按相同 RTL/ROM/TB 做版本对照。

### 任务 2：真实 B+C 综合与实现取证

独立于功能修正，可先用当前 vendor 基线测结构与资源；但不能把综合
成功当成功能验收。仿真结束后单独运行：

```powershell
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/synth_bc_real.tcl' -tclargs impl *> '_bc_real_impl.log'
```

该脚本在 `report/bc_real_synth/` 写综合与实现报告，并自检真实
`b_core_real`/五层实例存在、`b_core_stub` 为 0。记录准确的 LUT/FF、
RAMB36/RAMB18、DSP48E1、层次拆解、WNS、路由状态及失败点。
此前一次综合在 RTL Optimization Phase 2 后被人工停止，约 10 分钟，
内存峰值约 30 GB；本机物理内存约 32 GB，注意避免与 XSim 并行。
若内存不足，可先不带 `impl` 参数只做综合并如实报告限制。

### 任务 3：正式验收与文档闭环

汇总任务 1/2 的原始数据，更新 `docs/B_C_REAL_ACCEPTANCE_REPORT.md`
的 A～Q 小节，明确功能、协议、资源、时序分别 PASS/FAIL/未完成；
同步 `README.md`、`docs/DEPENDENCIES_A_B.md` 后运行
`scripts/export_dep_txt.py`。不能用旧 C+stub 的 192 RAMB36 或 B 的预算
271/276/278 当真实 B+C 实测，也不能从仿真周期推断 200 MHz/30 fps。
UART 管脚及板级触发仍需单独完成。

## 本机依赖与提交边界

裸 `python` 是 Windows Store alias；使用
`C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe`。
A 的大文件参考数据在本机 `ref/a_full_integer_golden/` 与
`ref/a_test_vectors/`，由 `.gitignore` 排除；入库的是来源/哈希清单。
上游 A 量化资产位于 `C:\Users\Administrator\a_dui_dui_dui\artifacts\quant`。
临时 `_sim/`、`_synth_bc/` 可再生，当前原始日志在本机，不随 Git 提交。
