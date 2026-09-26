# 200 MHz routed DCP 收尾备选

状态：**本轮已执行V1/V2两组无额外压力的物理收尾，均未达200MHz目标。** V1 setup030从−0.312改善到−0.162ns；V2从−0.481改善到−0.403ns。完整报告见`member_b_evidence/timing_200_20260926/postroute_v1_000/`和`postroute_v2_000/`。外部Python调用用`-I`隔离Vivado环境。以下为复现流程说明。 输入为已完成布线、已恢复 5.000 ns / setup UU=0 的 `postroute.dcp`；不读取或修改 RTL。旧 stage 始终保留，准备与运行都拒绝覆盖已有结果。

## 已核实的命令与边界

本机 Vivado 2025.2 帮助：

- `F:/Xilinx/2025.2/Vivado/doc/eng/man/phys_opt_design`：支持 post-route，列出 `AggressiveExplore`。帮助同时明确没有负 slack 的设计不会优化。因此无额外压力时，此入口适合轻微负 WNS 收尾；已有正裕量时默认记录跳过，不能假定还能提高裕量。
- `.../doc/eng/man/route_design`：`NoTimingRelaxation` 可与 `-preserve` 配合。`-preserve` 保留已完整的路由，允许修复未完整连接；这属于对当前 routed design 的继续处理。
- 不使用 `read_checkpoint -incremental`：该高复用流程只兼容 Explore/Quick/Default。也不组合 `-eco` 与 NoTimingRelaxation。
- `.../doc/eng/man/report_route_status`：支持 `-boolean_check ROUTED_FULLY` 与 `ERRORS_IN_ROUTES`，用来检查优化前后是否需要修复路由。

AMD [UG904 2025.2 Physical Optimization](https://docs.amd.com/r/2025.2-English/ug904-vivado-implementation/Physical-Optimization) 说明 post-place/post-route 两种阶段；[实现策略表](https://docs.amd.com/r/2025.2-English/ug904-vivado-implementation/Directives-Used-by-phys_opt_design-and-route_design-in-Implementation-Strategies)列出 post-route 策略。项目目标 Artix-7 的正常实现流程支持这一步；实际运行若工具返回错误，脚本停止并保留失败信息，不把准备状态当作已实测。

本机帮助 SHA-256：

| 文件 | SHA-256 |
|---|---|
| phys_opt_design | `62a1392c78cc2bb4acee9189424722a20238f79ea5a26d61bea5ac52e4ef792e` |
| route_design | `4ecc43d1175acf43fc9fc6dc8604bd045443cd4ccdc374dd40b992b9beb982ee` |
| report_route_status | `098549f1ab006f727fa7b5d341929b7f99ac7647e20be8f83351b999b5fc2f04` |

## 实验流程

1. `prepare.py prepare` 将指定基线 DCP 复制进新的 `_synth_bc/<名称>/input/`，验证源/副本 SHA-256 一致，复制原 reports 下的报告、XDC 和 manifest；固定 Tcl/Python 脚本哈希。此步骤不会启动 Vivado。
2. `finish.tcl` 首先验证这些哈希，检查器件、5 ns 时钟、UU=0、全布线且无路由错误，保存 before 完整报告。输入 DCP 副本就是 before checkpoint。
3. 可选临时 setup 压力为 **0、0.300、0.500 ns**，只作用于同一 200 MHz 时钟的 setup 检查。时钟频率、hold 约束、自动 TSJ/DJ/PE、false path、multicycle 和 DRC 严重级别不变。
4. 存在负 setup slack 时执行 `phys_opt_design -directive AggressiveExplore`。每次都保存其后的 setup/hold/route/DRC/资源报告；即使 route 完整也不省略这些检查。
5. 仅在路线未完整或有错误时执行 `route_design -directive NoTimingRelaxation -preserve`，然后再次报告。
6. 同一个物理结果先在压力条件下报告，再恢复 UU=0 报告。检查同钟最差 setup slack 差额等于所加压力、hold 不变、TSJ/DJ/PE 和原时钟波形相同，保存最终 DCP。
7. Python 再次核验输入、记录最终 DCP 和所有报告哈希。`COMPLETED_MEASURED` 仅表示测量完成；是否接受必须依据全局 restored WNS/TNS、WHS/THS、脉宽、路由和 DRC。

同钟差额核验不用全局 WNS：恢复约束可能改变全局最差路径所属时钟，不能把这误判为压力未恢复。优化后的 hold 可能与原基线不同，必须看完整 after_restored 报告，不能只看临时压力恢复前后 hold 相等。

## 复现命令示例（此处pressure030示例未执行）

以下例子选择 V2 的 030 基线；必须等其生成最终 DCP 后再准备。`V:` 为当前实验仓库映射，新 stage 名称不得存在。

```powershell
& 'C:/Users/24889/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' V:/experiments/timing_200_20260926/postroute_finish/prepare.py prepare --baseline V:/_synth_bc/acc36_realrom_200_member_b_pipeline2_0300926_ascii_ramdecomp/postroute.dcp --stage postroute200_v2_pressure030_try1 --extra-setup 0.300
```

准备完成并由主任务安排运行时：

```powershell
& 'F:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -nojournal -log V:/_synth_bc/postroute200_v2_pressure030_try1/vivado.log -source V:/experiments/timing_200_20260926/postroute_finish/finish.tcl -tclargs V:/_synth_bc/postroute200_v2_pressure030_try1 'C:/Users/24889/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
```

入口每进程最多 2 线程。任何准备/执行失败保留现场；下一次使用新 stage 名，不覆盖。该流程不使用普通 `collect_evidence.py` 的 RTL 输入格式，证据由本目录 helper 生成 `input_manifest.json` 和 `result_manifest.json`。
