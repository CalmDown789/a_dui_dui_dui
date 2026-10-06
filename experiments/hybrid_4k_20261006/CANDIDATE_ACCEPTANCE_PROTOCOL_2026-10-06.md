# 成员 A 候选模型验收口径

日期：2026-10-06
范围：仅限 PC 侧模型与整数参考评测；不修改正式冻结资产或 B/C 文件。

## 验收问题

判断 R0F、R0T、R0-QAT 是否值得进入后续硬件联调。评测链路固定为：
`960×540 Y8 → FSRCNN×2 → 1920×1080 Y8 → Keys bicubic×2 → 3840×2160 Y8`。
本报告中的结果只代表软件参考，不代表 RTL、FPGA 实现、板级画面或实时性能。

## 比较对象

- 双三次基线：直接将 960×540 输入放大到 3840×2160。
- R0F：正式冻结的 FP32 d16/s8/m1/c16 checkpoint。
- R0T：同结构、seed 123 的训练候选，使用独立 checkpoint。
- R0-QAT：同结构、seed 456 的 5 epoch QAT 候选，使用独立 checkpoint。
- 对 R0F、R0T、R0-QAT 分别按同一校准数据生成实验性整数包，再跑整数 Python 参考。

## 数据边界

- 训练侧：UVG Beauty、HoneyBee、YachtRide；每条序列的已有 FFmpeg 配对集用于模型训练。
- 校准侧：YachtRide 训练侧配对集；仅用于候选激活量化校准，不参与最终测试指标。
- 验证侧：UVG Jockey。
- 留出测试侧：Bosphorus（10 帧）、ReadySetGo（10 帧）、ShakeNDry（5 帧）。
- 两种 LR 生成口径分别报告：FFmpeg bicubic 与 Pillow bicubic。它们来自同一批 25 个原始帧，因此总计 50 组“图像-退化口径”样本，但不是 50 个独立场景或独立源帧。
- 原始视频为有损 HEVC 解码内容，测试对是合成退化，不等同相机原生 540p/4K ground truth。
- 连续视频扩展采用 UVG Bosphorus、ReadySetGo 各一段 5 s 留出片段，以及 CityAlley、FlowerFocus、FlowerKids、FlowerPan 四条新 12 s、50 fps 序列各两个互不重叠的 5 s 区间；总计十段、约 50 s、约 1,240 帧。12 s 原始序列由 4K YUV420 逐帧读入，FFmpeg 以 bicubic 合成 540p，整数模型输出视频按 25 fps；Bosphorus/ReadySetGo HEVC 5 s 序列按 24 fps 取样。实际帧号、源哈希和输出帧率写入各片段摘要。
- 新增 UVG 序列按官方 CC BY-NC 及压缩包版权说明中的 CC BY-NC 3.0 Unported 条款用于非商业评测；素材及其中说明 Digiturk 保留知识产权。保留每个压缩包内的版权说明；原始数据与派生视频不纳入 Git。

## 指标与规则

- 只评估亮度 Y，像素范围 0–255，PSNR 峰值固定为 255。
- PSNR/SSIM 同时报全图（border=0）和中心裁边 8 像素（border=8）；逐图 CSV 与集合算术平均一并保存。
- SSIM 使用 11×11 高斯窗口、sigma=1.5；不将裁边结果简称为“全图质量”。
- 逐候选记录 checkpoint、校准清单、测试清单及整数包哈希；校准/测试原始数据不纳入代码提交。

## 计划书筛选门槛

- 4K 平均 PSNR 相对双三次提升至少 0.20 dB，且 SSIM 不降低。
- 候选平均 PSNR 相对 R0T 的损失不超过 0.30 dB。
- 整数量化相对同候选 FP32 的平均 PSNR 损失不超过 0.10 dB。
- 门槛仅作为候选筛选，不替代视觉检查；文本/边缘、振铃、细节与时域闪烁须结合样图判断。

## 交付边界

本阶段可交付逐图指标、统计摘要、候选整数参数/权重/测试向量哈希、代表性图像裁剪和复现说明。若未完成连续视频或实物测试，会明确列为未完成，不以静态帧或模拟播放器替代。真实 B 位精确对拍、资源/时序、bitstream 和板测结论均由 B/C 后续验证。
