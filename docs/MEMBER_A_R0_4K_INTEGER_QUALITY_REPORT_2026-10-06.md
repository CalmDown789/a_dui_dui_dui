# 成员 A：冻结整数链路 4K 画质评测

日期：2026-10-06

状态：PC 软件评测完成；不代表 FPGA 板级验收。

## 结论

在本轮固定的合成 ×4 评测中，冻结 R0 整数混合链路的总体指标高于直接双三次 ×4。20 张静态图的 shave-8 平均 PSNR 提升 **1.268 dB**、SSIM 提升 **0.006122**；10 段视频、500 个采样帧的 shave-8 平均 PSNR 提升 **1.105 dB**、SSIM 提升 **0.004133**。但视频并非所有帧都改善：17 帧的 PSNR 增益为负，64 帧的 SSIM 差值为负，主要集中在 Beauty 与 Jockey。总体均值不能替代这些退化样本。

## 比较对象与口径

- 基线：输入 Y8 由 Pillow BICUBIC 直接放大 ×4 至 3840×2160。
- R0：冻结的 FSRCNN d16/s8/m1/c16 整数模型 ×2（INT8 权重、INT16 激活、INT32 偏置/累加、Q1.15 PReLU），再以冻结 Q14×Q14 Keys bicubic ×2 放大至 3840×2160。
- 参考：UVG 4K 序列经 FFmpeg 解码并扩展有限范围后的 Y 平面。评测输入由同一参考图像 Pillow BICUBIC 缩至 960×540；因此测量的是合成退化复原，不是相机原生 540p。
- 样本：20 张静态图；10 条序列各取开头 5 秒，按 10 fps 抽取 50 帧，共 500 帧。指标为 Y-PSNR（peak 255）和固定高斯窗 SSIM；同时报告全图及四周 shave 8 像素。汇总采用逐帧算术平均。
- 来源许可：[UVG 数据集](https://ultravideo.fi/dataset.html)为 CC BY-NC，仅限非商业使用；引用 A. Mercat、M. Viitanen、J. Vanne，ACM MMSys 2020。原始视频未放入仓库。

## 汇总结果

| 样本 | 指标 | 双三次 ×4 | R0 整数混合 ×4 | 差值 |
| --- | --- | ---: | ---: | ---: |
| 静态 20 图，全图 | Y-PSNR (dB) | 37.418 | 38.680 | +1.262 |
| 静态 20 图，全图 | Y-SSIM | 0.912065 | 0.918159 | +0.006095 |
| 静态 20 图，shave-8 | Y-PSNR (dB) | 37.429 | 38.697 | +1.268 |
| 静态 20 图，shave-8 | Y-SSIM | 0.912052 | 0.918174 | +0.006122 |
| 视频 500 帧，全图 | Y-PSNR (dB) | 39.547 | 40.640 | +1.093 |
| 视频 500 帧，全图 | Y-SSIM | 0.937942 | 0.942026 | +0.004084 |
| 视频 500 帧，shave-8 | Y-PSNR (dB) | 39.542 | 40.648 | +1.105 |
| 视频 500 帧，shave-8 | Y-SSIM | 0.937949 | 0.942082 | +0.004133 |

各片段的 shave-8 均值：

| 片段 | PSNR 差值 (dB) | SSIM 差值 | 负 PSNR 增益帧 | 负 SSIM 差值帧 |
| --- | ---: | ---: | ---: | ---: |
| Beauty | +0.154 | +0.001107 | 8 | 24 |
| Bosphorus | +1.814 | +0.002564 | 0 | 0 |
| CityAlley | +0.774 | +0.005651 | 0 | 0 |
| FlowerFocus | +0.085 | +0.001406 | 0 | 0 |
| FlowerKids | +1.492 | +0.005892 | 0 | 0 |
| FlowerPan | +1.185 | +0.012590 | 0 | 0 |
| HoneyBee | +0.878 | +0.001079 | 0 | 0 |
| Jockey | +0.518 | −0.000663 | 9 | 40 |
| ReadySetGo | +2.458 | +0.005890 | 0 | 0 |
| YachtRide | +1.695 | +0.005815 | 0 | 0 |

视频片段 PSNR 增益的等权平均为 +1.105 dB；每段片段平均 PSNR 增益均为正。帧间亮度差 MAE（shave-8、非运动补偿）平均由双三次的 2.573 降至 R0 的 2.333 个 Y 灰度级。该值只作辅助连续性统计，不是感知闪烁指标。

## 退化样本

视频失败清单按“任一 shave-8 PSNR 增益或 SSIM 差值为负”定义，共 64 帧：17 帧 PSNR 增益为负，64 帧 SSIM 差值为负；按失败清单计数，Beauty 24 帧、Jockey 40 帧。最差 PSNR 样本来自 Jockey：`Jockey_first5s_f35` −0.980 dB、`f33` −0.916 dB、`f37` −0.915 dB。Jockey 的平均 PSNR 仍提升 +0.518 dB，但片段平均 SSIM 略降 0.000663。另一个值得留意的例子是 `Jockey_first5s_f17`：PSNR 提升 +0.429 dB，而 SSIM 下降 0.002098。

20 张静态图没有出现负 PSNR 增益或负 SSIM 差值。逐图、逐帧数据和失败项均保留在结果 CSV，未从汇总中剔除异常帧。

## 文件与复现

- [机器可读汇总](../results/r0_4k_quality_20261006/summary.json)
- [数据与模型哈希、抽样索引及限制](../results/r0_4k_quality_20261006/evaluation_manifest.json)
- [20 张静态图逐图指标](../results/r0_4k_quality_20261006/per_image_metrics.csv)
- [500 个视频帧逐帧指标](../results/r0_4k_quality_20261006/per_clip_frame_metrics.csv)
- [10 段逐片段汇总](../results/r0_4k_quality_20261006/per_clip_summary.csv)
- [失败帧清单](../results/r0_4k_quality_20261006/failure_cases.csv)
- [低增益静态样本对照图](../results/r0_4k_quality_20261006/visuals/lowest_gain_examples.jpg)
- [Beauty 5 秒软件演示](../results/r0_4k_quality_20261006/demo_beauty_5s_10fps.mp4)

在仓库根目录安装 `quality` 与 `test` 可选依赖后，使用以下命令复现；原始数据只下载至被忽略的 `.data/` 目录：

```powershell
python -m pip install -e ".[quality,test]"
python scripts\download_r0_quality_data.py
python -m experiments.r0_4k_quality_20261006.evaluate `
  --source-dir .data\r0_4k_quality_20261006\sources `
  --output-dir results\r0_4k_quality_20261006
```

若完整结果表已保存，只需重建汇总或对照图：

```powershell
python -m experiments.r0_4k_quality_20261006.evaluate --finalize-existing `
  --output-dir results\r0_4k_quality_20261006
python -m experiments.r0_4k_quality_20261006.evaluate --contact-sheet-only `
  --source-dir .data\r0_4k_quality_20261006\sources `
  --output-dir results\r0_4k_quality_20261006
```

方法细节、采样规则和许可说明见[评测协议](MEMBER_A_R0_4K_INTEGER_QUALITY_PROTOCOL_2026-10-06.md)。

## 限制

UVG HEVC 是有损解码素材，不是无损传感器真值；合成缩小输入不能代表相机原生 540p。这里只测灰度/Y 通道和离线 10 fps 抽样；既不验证彩色重建、实时 30 fps，也不验证 FPGA RTL、bitstream、HDMI 或板上画面。该评测用于描述冻结 R0 软件链路在指定数据与处理口径下的效果，不构成模型对所有场景均优于双三次的保证。
