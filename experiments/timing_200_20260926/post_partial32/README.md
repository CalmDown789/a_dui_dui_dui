# V6：Q31 四部分积

基于 V5 `prelu_partial`，仅替换 Q31 乘法；PReLU、scalar九级、shared十拍标签不变。准备者未运行工具链。

令 `a=65536×a_hi+a_lo`，`b=65536×b_hi+b_lo`，其中高半字为signed16，低半字补零为signed17。s5分别寄存LL(signed34)、LH/HL(signed33)、HH(signed32)，均请求DSP乘法。各项先符号扩展到64位，再移位0/16/16/32。

两级CSA使用恒等式 `A+B+C=(A xor B xor C)+2×majority(A,B,C)`，所有向量均64位，因此逐级在模2^64下成立；最后一次64位加法得到原signed32×signed32的完整位模式。真实乘积幅度不超过2^62，解释为signed64时也与整数乘法一致。CSA及最终加法均请求`use_dsp="no"`；原`requant_product_full_s6`的KEEP/DONT_TOUCH保留。Q31舍入和饱和部分保持原样。

## 验证入口

父任务已确认V:映射到仓库时：

```tcl
set argv {tb_post_partial32 tb_post_partial32_shared}
source V:/experiments/timing_200_20260926/post_partial32/run_unit.tcl
```

要求6个scalar、5个shared配置及INT64舍入探针通过；reference仍为V2 scalar延迟一拍。新增完整64位乘积检查应覆盖符号、半字边界、invalid保持及复位，避免输出饱和掩盖错误。总标志为`POST_PARTIAL32_ALL_UNIT_TESTS_PASS`。

后续仅按实证决定是否实现：确认四个独立DSP的寄存属性、无Q31 PCIN级联算术、CSA/最终加法位于普通逻辑、完整64位FF保留，并查看实际最差路径和资源。最终仍以原5.000 ns约束下布线后setup/hold及完整功能回归验收。
