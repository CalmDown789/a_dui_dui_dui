# B+C synth-only 续跑检查点（2026-09-23）

## 状态

- 目标：Vivado 2022.2、`xc7a200tfbg484-2`、真实 B 五层 RTL 加 C 外壳，运行
  `scripts/synth_bc_real.tcl` 的 synth-only 模式（没有传 `impl` 参数）。
- 首轮约在本机 20:07 启动；看到可用物理内存约 0.61 GB 后提前中断。后来发现该判断
  没有同时检查 Windows 提交内存与页面文件，不能证明页面文件不可用。
- 第二轮于 20:22:53 启动，监控提交内存和页面文件。Vivado 完成 RTL Optimization
  Phase 2，日志峰值内存约 30.4 GB；随后一直没有新日志或资源报告。
- 第二轮提交量升至约 62.31 GB / 63.43 GB，余量仅约 1.12 GB。页面文件已分配 32 GB、
  当前使用约 4.71 GB，但本次运行期间分配容量和提交上限都没有扩展。为避免触及提交
  上限导致系统分配失败，于本机约 21:02 安全中断 Vivado。
- 中断时仍未完成 `synth_design`、真实 B 层级自检或报告生成。第二轮结束后进程已退出，
  可用物理内存恢复到约 22.9 GB，系统提交余量恢复到约 42.5 GB。
- `report/bc_real_synth/` 没有本次运行生成的综合报告或结果文件。不要引用旧 C+stub
  综合数字作为真实 B+C 结果。本次也未运行 `opt_design`、布局、布线或实现。
- 两轮原始 stdout/stderr 记录分别在
  `report/bc_real_synth/synth_only_memory_stop.txt` 和
  `report/bc_real_synth/synth_only_commit_limit_stop.txt`。
- 当前配置：系统管理页面文件为 32 GB；物理内存约 31.4 GB，总提交上限约 63.4 GB。
  第二轮 E 盘尚有约 377 GB 可用，但提交余量很低时上限没有随运行增加。下次运行前应
  先确认/预留足够页面文件提交容量，并实时监控 `CommitLimit - CommittedBytes`；不要只看
  可用物理 RAM，也不要假设系统会及时扩展页面文件。

## 续跑

1. 先确认 `report/bc_real_synth/` 中没有另一轮正在写入的 Vivado 报告。
2. 先确认页面文件容量/提交上限足以覆盖该综合峰值；关闭本机占用大量内存的程序，
   不要和 XSim/其他 Vivado 仿真并行运行。
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
