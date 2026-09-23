# B 真实 RTL：XSim 优化选项复现记录

本记录用于保存成员 B 转来的技术反馈，并让其他账号能复查 C 侧的仿真对照。
B 报告其 XSim 2025.2 运行通过，并指出其修正过的测试台竞态是独立问题，应继续保留。
C 侧据此把 XSim 2022.2 默认优化列为待复现的仿真器嫌疑；这不是对 B RTL 的定罪。
本轮没有修改真实 B RTL、参数 ROM 或 Golden，也没有做猜测性 RTL 修补。

## 固定输入身份

| 输入 | 身份/摘要 |
|---|---|
| B 真实 RTL | 上游提交 `ae29515945fbb6e9566626d7f2d28660ac94d5c4`；15 文件逐文件 SHA-256 在 `_b_vendor_manifest.json`，该清单 SHA-256 `4d3c568ec6205816ddf821973ad72f11706b9afe67bbb356be23928c6256761c` |
| B 参数 ROM | `rom/member_a_d16_s8_m1_c16/manifest.json` SHA-256 `9c8206b6ac2dcbac0f5826b9ad6fb10183611de8abb39ccaeb9395c9c073abba`；清单包含 19 个 ROM 文件哈希 |
| 96×54 用例 | A 四组 manifest：impulse `5b2c57e5aef920f50fdd925ef319e20c6953f9f5786a9f45ca509574819e83fb`；ramp `220f0be44e1ba620da861f6924c933f19e45cbb45fe4d93d1a3688791ea6d9a5`；random `25e09ab491961179f78e5a0e952a86ae1150d3900ed2820ee41098aff1b06765`；zero `8343a457d2a7afa497bf84a4014fa560bfa891b1a46875d425498510d41216bf`。每份 manifest 都固定输入、逐层 Golden 和最终输出哈希 |
| 960×540 全帧 Golden | A 来源提交 `98c82f394bdfba85bc2959bede9760edc4d6862f`；输出 `output_1920x1080_y_u8.bin` SHA-256 `be8e576beea1632e6ee8257ba39a92c9c7950e9ae90b202bd240677e2d85504e`；完整清单为 `ref/a_full_integer_golden/SHA256SUMS.txt` |
| 验收台 | `tb_b_real_bit_exact.v` SHA-256 `372d2805927f683f37b2da8c366baa060649ccfb627aa0da02facd45a91ac960`；`tb_b_real_full.v` SHA-256 `1bbde2e7ec936c392c0813f86387dc57c7e3714b57fa7345c43045628b1e85ff` |

## 同一 runner 的对照命令

`scripts/run_sim.tcl` 默认对正式真实 B 仿真使用 `xelab -O0`。要复现 XSim 默认优化，
启动 Vivado 前将环境变量设为 `default`；要复现当前建议配置，设为 `o0`。只对真实 B
验收 TB 生效，stub 回归和综合不受影响。

```powershell
$env:C_REAL_B_XELAB_OPT = 'default'
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog `
  -source 'scripts/run_sim.tcl' -tclargs tb_b_real_bit_exact

$env:C_REAL_B_XELAB_OPT = 'o0'
& 'E:\Xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -nojournal -nolog `
  -source 'scripts/run_sim.tcl' -tclargs tb_b_real_bit_exact
```

`run_sim.tcl` 会打印所选模式。每次运行的 `xelab.log`、`xsim.log` 和结果报告应分别
存到 `report/xsim_repro/default/` 与 `report/xsim_repro/o0/`，避免下一次运行覆盖证据。
目前这两个 96×54 配置还需在模式开关加入后各重跑一次，以保存同 runner 的原始日志。

## 已有结果

| 配置 | 用例 | 结果 | 证据 |
|---|---|---|---|
| XSim 2022.2 默认优化 | 96×54 四组 | 历史记录 FAIL；同一数据此前默认优化下失配 | 原始简表在提交 `23d913c` 的 `report/sim_result_tb_b_real_bit_exact.txt`；本机 Vivado transcript `_bit_exact_codex.log` |
| XSim 2022.2 `-O0` | 96×54 四组 | 4/4 PASS，0 失配 | `report/sim_result_tb_b_real_bit_exact.txt`；本机 `_sim/tb_b_real_bit_exact/xsim.log` |
| XSim 2022.2 默认优化 | 960×540 全帧 | 23,874 匹配、2,049,726 失配、0 个 X；帧尾/条带尾/保持规则通过 | 历史结构化摘要 `report/b_real_full_summary.json`；旧 Vivado transcript `_full_sim_codex_resume.log` |
| XSim 2022.2 `-O0` | 960×540 全帧 | 运行中；截至 2026-09-23 19:30 本机已比较 1,250,000/2,073,600 字节（60%），0 失配 | `_sim/tb_b_real_full/xsim.log` |

旧全帧摘要记录的默认优化原始 `xsim.log` SHA-256 为
`a9b816e184190e23b2a1a99f31720efa5c5f56e6e306f120b5a194f4d46b8f5f`。XSim 使用同一
`_sim/tb_b_real_full/xsim.log` 路径；当前 `-O0` 全帧正在运行，因此旧原始 log 已被
覆盖。旧的 Vivado transcript 与结构化摘要仍保留旧运行计数。新全帧结束后，应立即把
`-O0` 的 log、elaboration log、summary 和结果文本归档到 `report/xsim_repro/o0/`。

## 验收边界

`-O0` 的仿真结果只证明对应输入和仿真配置下的数值/协议结果。真实 B+C 综合、实现、
器件资源及时序、bitstream 和板级图像仍须 C 侧分别验证。B 侧修正过的测试台竞态也
继续作为独立问题维护，不能因 C 侧优化选项对照通过而删掉。
