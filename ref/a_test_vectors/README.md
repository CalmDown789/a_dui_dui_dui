# A 的 96×54 整数测试向量

`impulse`、`ramp`、`random`、`zero` 四组输入及 PixelShuffle 后输出
来自团队仓库 A 分支的 `artifacts/test_vectors/<case>/`。二进制实物不入库；
本目录提交 `SHA256SUMS.txt`，供复制后逐文件校验。

从本机 A 仓库复现：

```powershell
& <managed-python> scripts/prepare_ref_data.py --a-repo C:\Users\Administrator\a_dui_dui_dui
```

脚本校验各组 `manifest.json` 的 SHA-256 和文件长度，生成
`ref/_staged_mem/tv_<case>_{in,out}.mem`，供 `scripts/run_sim.tcl`
复制到各 testbench 工作目录。`report/sim_result.txt` 的真实 B
逐字节结论仅对校验通过的这组整数向量成立。
