# B+C synth-only 续跑检查点（2026-09-23）

## 状态

- 目标：Vivado 2022.2、`xc7a200tfbg484-2`、真实 B 五层 RTL 加 C 外壳，运行
  `scripts/synth_bc_real.tcl` 的 synth-only 模式（没有传 `impl` 参数）。
- 运行约在本机 20:07 启动。到 20:10 左右，可用内存降至约 0.61 GB，按安全阈值
  中断 Vivado；进程退出后可用内存恢复到约 21.5 GB。
- 日志显示 RTL 读入、约束处理及早期 FSM 提取已进行。中断前停在 `synth_design`
  早期，尚未完成网表优化、自检或报告生成。
- `report/bc_real_synth/` 没有本次运行生成的综合报告或结果文件。不要引用旧 C+stub
  综合数字作为真实 B+C 结果。本次也未运行 `opt_design`、布局、布线或实现。
- 原始完整 stdout/stderr 记录：
  `report/bc_real_synth/synth_only_memory_stop.txt`。根目录原始 `.log` 文件仍在本机，
  但按 `.gitignore` 规则不入库。

## 续跑

1. 先确认 `report/bc_real_synth/` 中没有另一轮正在写入的 Vivado 报告。
2. 关闭本机占用大量内存的程序；不要和 XSim/其他 Vivado 仿真并行运行。
3. 从仓库根目录重新执行 synth-only：

   ```powershell
   & 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog -source 'scripts/synth_bc_real.tcl' *> '_bc_real_synth_only.log'; exit $LASTEXITCODE
   ```

4. 等脚本完成后，先核对 `report/bc_real_synth/bc_real_synth_result.txt` 的
   `b_core_real`/五层自检，再查看 utilization 与 timing reports。只有这些真实综合报告
   完整后，才评估是否运行实现；综合成功不代表已通过布局布线或上板验证。

## 中断时的观察

中断前 Vivado 主进程工作集约 14.1 GB，另有两个工具子进程各约 1.8 GB；系统可用内存
仅约 0.61 GB。按既定 3 GB 可用内存安全线中断。未修改 RTL、综合脚本、ROM 或输入数据。
