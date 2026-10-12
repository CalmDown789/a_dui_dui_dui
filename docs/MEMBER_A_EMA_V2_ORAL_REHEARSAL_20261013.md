# 成员 A 答辩补充：EMA v2 候选

日期：2026-10-13
用途：补充既有《成员 A 答辩速记》和自测核对表；这是练习材料，不是成员 A 本人的讲解或签字记录。

## 约一分钟说明

“正式部署版本仍是冻结 R0，EMA v2 只是保持网络结构和 MAC 数不变的实验权重候选。我在 DIV2K 官方 validation-HR 0801–0900 共 100 张图上，用同一 Pillow bicubic×2 生成 Y 通道输入、相同整数参考和 shave-2 指标做配对比较。EMA v2 整数 PSNR 平均 32.4707 dB，R0 为 32.4043 dB，提升约 0.0664 dB；按图 bootstrap 的 95% 区间是 +0.0445 到 +0.0987 dB。逐图表中 100 张 PSNR 均略升，但可视化差异并不显著到能声称普遍肉眼可见。B 随后报告了候选 ROM、逐层向量和两帧全尺寸整数 Golden 的 XSim 数值对拍通过。该结果不等于 C 侧综合、布局布线或上板通过，所以正式 R0 继续冻结，EMA v2 不能直接替换。”

## 必须说清楚的证据边界

| 证据 | 能说明什么 | 不能说明什么 |
|---|---|---|
| A 的 DIV2K 100 张软件整数评测 | 这套图像集合、Y 通道、Pillow bicubic×2、shave-2 口径下，EMA v2 的平均 PSNR/SSIM 高于 R0 | 不是 MATLAB-bicubic track；不是主观普遍可见的画质结论；不是自然视频时序或 FPGA 板端画质 |
| B 的 EMA v2 XSim 回执 | B 报告候选 ROM/逐层/两帧全尺寸数值与 A 候选 Golden 一致，候选数值检查通过 | 不证明综合、布局布线、时序、bitstream、实体板图像、帧率或 4K30 |
| C 侧现行基线报告 | 截至 2026-10-11，C 报告跨帧正式交付仍待完成；Natural16 约 20.479 fps、PC 4K 路径约 20.536 fps | 不是 EMA v2 候选数据，也不能外推为最新一次运行；需以新同条件日志复测 |

候选 checkpoint SHA-256：`10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`。候选 `quant_params.json` SHA-256：`12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`。B 回传压缩包 SHA-256：`1262ba502d60be51fcf56eb61790e5233c70cb1b19f334dd9fbe958e33759f93`。指标复现细节见同目录 `evaluation/official_div2k_valid_ema_v2_20261013/README.md`；B/C 当前需要协作的事项见 `MEMBER_A_TASK_AUDIT_20261013.md`。

## 评委可能会问

**为什么 +0.066 dB 仍说是“小幅提升”？**
因为绝对增益不到 0.1 dB。统计区间在该评测集上高于零，说明结果不是仅由均值的一个偶然方向支撑；但这不等于人眼稳定可辨，也不代表其他分布、真实视频或板端都会获得同样增益。

**100 张是不是拿来训练或挑 checkpoint 的？**
报告绑定的 DIV2K validation-HR ID 是 0801–0900；训练和选模使用其他数据/划分，这 100 张只用于一次最终配对评估。输入 LR 按项目的 Pillow bicubic×2 Y 通道流程生成，而不是官方 MATLAB LR。

**B 通过之后为什么不直接换 EMA ROM？**
B 的回执是候选数值仿真证据。升级还需要 C 用相同 checkpoint/量化/ROM 身份完成综合和实现，并证明目标时钟、资源和板卡行为满足要求；之后团队再批准版本变更。在这些门槛前保留 R0，避免把实验候选当作已部署版本。

**它提升了速度或减少了计算量吗？**
没有。d16/s8/m1/c16 结构和 MAC 数未变；该实验优化的是整数路径画质指标，不是吞吐、延迟或资源。

**现在还缺哪几项？**
C 对 EMA v2 的资源/时序/板卡验收；当前 C BIT 的同帧自然视频原始回传及 A 侧端到端对拍；A/C 冻结真实通信协议并完成双向板测；成员 A 本人完成讲解、亲自复跑并填写自测表。整机 4K30 及跨帧方案也仍是团队级未关闭事项。

## 建议的本人复跑顺序

以下命令从仓库根目录执行；先确认候选目录未被覆盖，pytest 输出留在 D 盘忽略目录。评测指标包和独立审计可先查阅上方路径；若现场重新跑 100 张评测，需确认本机已有授权数据及相同候选文件。

```powershell
$py = "D:\Codex File\dialogue file\github\a_dui_dui_dui\.venv\Scripts\python.exe"
$candidate = "experiments\model_optimization_20261005\candidate_delivery\R0_QAT_EMA_seed20261006_v2"

& $py experiments\model_optimization_20261005\verify_candidate_delivery.py `
  --delivery-dir $candidate `
  --quant-dir "$candidate\quant" `
  --checkpoint "$candidate\training\candidate_ema_qat_fp32.pth" `
  --recompute-full

$testTemp = ".data\member_a_task_20261013\pytest_member_a_replay"
& $py -m pytest -q --basetemp $testTemp
```

自测表中的日期、实际执行人、命令与 PASS 报告路径、未理解问题均由成员 A 本人填写。自动复跑 PASS 只能证明当前机器和文件的复现性，不能替代成员本人的讲解能力或板卡验收。

补充：2026-10-13 本机代理已按此顺序重跑正式 R0 整数包、全尺寸 Golden、EMA v2 候选完整整数参考及 PC 后处理测试，均 PASS；详见 `MEMBER_A_TASK_AUDIT_20261013.md`。这次运行者不是成员 A，因此仍不在本人自测表上打勾。
