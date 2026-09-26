# L5 6400×4 SRL FIFO 备用候选

状态（2026-09-26 19:20）：**Vivado/XSim 2025.2 单元仿真 7/7 配置 PASS**；本 SRL 候选的整网回归、综合及布局布线仍待验证。当前主 `pipeline` 候选未引用本目录。后续是否试用由 200 MHz 实际关键路径决定。

成功会话 PID `33224`，工作目录 `unit_work/run_20260926_192015_33224/`。目标 6400×4 配置实际接受 964 项、弹出 941 项、复位丢弃 23 项；满时交换 534 次，最长无泡交换 40 拍，保持检查 1294 次，2000 拍随机流量及满/半满复位均通过。全部七组均出现唯一配置 PASS 和最终 `FIFO_SRL_ALL_SEVEN_CONFIGS_PASS`。原始日志及源文件哈希见[单元证据](../../../member_b_evidence/timing_200_20260926/units/summary.json)。

## 修改与来源

`elastic_fifo.sv` 原样复制自此前未验证草稿：

```text
experiments/timing_margin_20260926/srl_candidate/elastic_fifo.sv
SHA-256 b907fe31d0de9d92e648920e987bc760f4b29d7a082a6d4f2cbecd846bb87d6c
```

只在 `DATA_W==6400 && DEPTH==4` 的 L5 窗口 FIFO 中启用移位存储。其它参数保留原窄字和分片宽字 LUTRAM 分支。没有修改 baseline、150 MHz 发布件、主候选或运行脚本。

对照 `elastic_fifo_reference.sv` 来自：

```text
experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv
原文件 SHA-256 354116f189917f9f818a9ac990ddb84cc2f1f712398a9e12ba3309a08379f49d
```

对照只将模块名 `elastic_fifo` 改为 `elastic_fifo_reference`；可还原模块名后核对原件。保留对照并不替代独立队列模型。

## 存储和时钟行为

每个输入 bit 使用四级、无复位的 `data_shift[3:0]`。每次接受输入时把新 bit 放入 stage 0，旧数据向 stage 3 移动；最旧有效数据位于 `count-1`。只有 push 改变存储，单独 pop 只改变读取位置与有效数量。

6400 位分成 100 组，每组 64 位，共用一个两位 `read_index_local`。该索引满足 `(count-1) mod 4`：空队列复位为 3，只有 push 时加 1，只有 pop 时减 1，同时 push/pop 时保持。因此：

| 操作 | 存储变化 | 最旧有效数据 |
|---|---|---|
| 空队列 push | 新数据进入 stage 0 | count=1、索引=0，读到新数据 |
| 有效头部停顿时追加 | 原头部向高一级移动，索引也加 1 | 输出仍是原头部 |
| 仅 pop | 存储不动，索引减 1 | 转到下一旧数据 |
| 满队列同时 pop/push | 最旧项移出，新数据插入，索引仍为 3 | 新的最旧项正确成为输出 |
| reset | count 和索引复位，存储内容保留 | out_valid=0；随后新 push 才重新有效 |

这消除了 L5 存储的二进制写地址需求。顶层遗留的 `wr_ptr` 在该特化分支中未被存储使用，应由综合移除；其它分支仍使用它。

**本候选没有切断 ready 组合通路。** 它保留 `in_ready=(count<DEPTH)||pop`，满时允许 pop/push 同拍。`mac_buffer` 的两槽缓冲是另一处独立修改，不能混淆两者。SRL 推断后，push 仍可能成为高扇出时钟使能，新的读地址、使能或上游控制也可能成为瓶颈。

## 新单元自检

`tb_elastic_fifo_srl.sv` 同时实例化七组参数：

| ID | 宽度×深度 | 用途 |
|---|---:|---|
| 1 | 6400×4 | 目标 L5 SRL 特化 |
| 2 | 256×32 | 实际网络窄字 FIFO |
| 3 | 200×4 | L1 窗口窄字分支 |
| 4 | 1152×4 | L3 窗口其它宽字分支 |
| 5 | 1025×3 | 宽字尾部分片、非 2 次幂深度 |
| 6 | 6400×3 | 同目标宽度但不同深度，必须保留原分支 |
| 7 | 37×1 | 单项队列和非整 32 位宽度 |

独立模型把旧数据保存在数组前端：pop 时前移，push 时追加到尾端。它既不使用 DUT 的“新数据放前端 + count−1 选头”实现，也不使用原件的环形指针。每个有效输出检查所有数据 bit，同时与原件逐拍比较 ready/valid/occupancy 和有效数据；空队列的未初始化存储输出不参与比较。

每组定向检查及强制覆盖计数包括：

- 空队列、重复完整填满/排空、非 2 次幂地址回绕；
- 满队列连续 40 拍 pop/push，要求无插入空拍；count=1 时也连续 40 拍交换；
- 输出停顿时继续追加而头部保持，满时上游阻塞并保持未接受的输入；
- 每组 2000 拍固定种子随机流量，周期性至少 51 拍输出停顿；
- 满队列、有未接受上游数据时复位，并刻意让 reset 期间输入 valid 为 1；
- 深度大于 1 时额外检查半满复位；复位后的旧存储不得重新泄漏；
- 最终排空，检查 `已接受输入 = 已弹出输出 + 复位丢弃项`；
- 每个上述覆盖不足均 `$fatal`，整个测试 200 us 硬超时，不生成波形文件。

本次 runner 已实际完成，七个配置均通过覆盖检查并输出最终 PASS。该结论限于单元行为，不包含 SRL 物理推断、完整网络或时序验收。

## 复现入口

需要复跑时在 Vivado 空闲时执行。启动工作路径须为 ASCII；以下假定 `V:` 已正确映射到此仓库：

```powershell
Push-Location 'V:/'
try {
    & 'F:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -source 'experiments/timing_200_20260926/fifo_srl/run_unit.tcl' -log 'experiments/timing_200_20260926/fifo_srl/unit_vivado.log' -journal 'experiments/timing_200_20260926/fifo_srl/unit_vivado.jou'
    if ($LASTEXITCODE -ne 0) { throw 'FIFO SRL unit failed' }
}
finally { Pop-Location }
```

或从同一 Vivado 2025.2 会话中：

```tcl
source V:/experiments/timing_200_20260926/fifo_srl/run_unit.tcl
```

runner 在本目录 `unit_work/` 调用 xvlog、`xelab -O0`、xsim，elaboration 后复制可用的 2025.2 Windows DLL。它要求恰好七条 `FIFO_SRL_CONFIG_PASS id=`、最终 `FIFO_SRL_ALL_SEVEN_CONFIGS_PASS`，并拒绝 fatal/error。未加入主 `run_units200.tcl`。

## 采用前仍须证明

1. 单元测试通过，再在独立 source closure 中仅替换该 FIFO 文件，执行真实 B Golden 和三种反压回归；若其它候选叠加使用，应验证最终实际组合。
2. 综合层次和网表确认目标分支确实启用、四级移位被推断为预期 SRL 原语，写地址逻辑被消除；`shreg_extract`/`srl_style` 只是请求，不能代替原语检查。
3. 记录 SRL、LUT、FF、分布式 RAM、BRAM 与 DSP 数量。SRL 可降低写地址压力，但可能增加 LUT 或改变局部布线需求；若退化为 FF 链，不能仍按 SRL 方案报告。
4. 检查本地读取索引和 push 使能的实际扇出、关键路径是否转移，再按原 200 MHz 约束取 post-route setup/hold/路由错误与资源结果。

本轮单元仿真原始证据已归档；本目录仍没有本 SRL 候选的整网回归、综合报告或 bitstream，不能将单元 PASS 扩大为当前主候选包含 SRL 或 SRL 已实现通过。
