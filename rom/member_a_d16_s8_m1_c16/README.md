# 成员B工作：FSRCNN 参数 ROM 打包件

此目录的 19 个 `.mem` 来自成员 A 已审计的 `d16/s8/m1/c16` 整数交付，成员 B 只按 RTL 的 packed bus 位序重排，没有修改权重、bias、PReLU 或 Q31 值。`manifest.json` 记录 A 量化参数与每个源文件、输出文件的 SHA256。

生成方式（在 `F:\FPGA预选\10h冲刺` 执行）：

```powershell
& 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\acx750_rtl\scripts\export_member_b_parameter_rom.py --delivery-root .\.artifacts\member_a_review_83a9fcd --output-dir .\acx750_rtl\rom\member_a_d16_s8_m1_c16
```

复测时在 `run_network_mem_top_xsim.ps1` 或 `run_member_b_c_core_real_xsim.ps1` 指定 `-ParameterRomDir .\acx750_rtl\rom\member_a_d16_s8_m1_c16`。脚本先与独立黄金生成器的 packed 值逐文件比较，再在临时仿真目录使用此处的 `.mem`。6×5、96×54 B 顶层，以及连续两帧 6×5 C+B 联调均已通过。

`fsrcnn_network_mem_top.sv` 当前用相对文件名 `$readmemh`；C 的仿真/综合脚本需把这 19 个 `.mem` 复制到该运行目录，或在正式集成时给 ROM 文件名增加目录参数。这里的逻辑容量仅 3,344 字节原始参数，实际 ROM bank 复制与物理资源映射仍须目标综合核实。
