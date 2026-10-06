# R0 整数混合链路：4K 画质与短片评测协议

## 目的与边界

本轮只评价冻结 R0 整数软件链路，不训练或替换模型，不修改 B/C 文件。评测的输入是 4K HEVC 解码 Y 平面经双三次合成退化得到的 960×540 Y8；它不能代表相机原生 540p 输入，也不能证明 RTL、板卡、颜色通路或实时帧率。

## 留出样本

- 静态画质组：CityAlley、FlowerFocus、FlowerKids、FlowerPan 四条 50 fps 序列各取第 350、360、370、380 帧，另从 ShakeNDry 取第 60、70、80、90 帧，共 20 张 4K 图。
- 连续片段组：Beauty、Bosphorus、HoneyBee、Jockey、ReadySetGo、YachtRide 六条 120 fps HEVC 序列，加 CityAlley、FlowerFocus、FlowerKids、FlowerPan 四条 50 fps 原始 YUV 序列；每条取起始 5 秒片段，每段抽取 50 帧，以 10 fps 评测，共 10 段、500 帧。
- 四条 50 fps 序列的静态图位于 5 秒视频段之后；静态图索引与连续片段样本帧不重叠。ShakeNDry 只用于静态图。
- 帧号根据各序列官方 50/120 fps 元数据；HEVC elementary stream 不依赖逐帧时间戳。
- UVG 官方数据集为 4K 50/120 fps 序列，采用 CC BY-NC 非商业许可；报告须保留官方出处和论文引用。下载视频、原始视频帧不入库。

## 比较链路

1. 双三次基线：960×540 Y8 由 Pillow BICUBIC 直接放大至 3840×2160。
2. 冻结 R0 整数混合：960×540 Y8 → 正式量化资产中的 FSRCNN d16/s8/m1/c16 INT8/INT16/INT32 ×2 → 1920×1080 Y8 → 已冻结的 Q14×Q14 Keys bicubic ×2 → 3840×2160 Y8。

目标参考为 FFmpeg 解码的 3840×2160 8-bit 4:2:0 HEVC Y；有限范围 Y 由 FFmpeg `in_range=limited:out_range=pc` 扩展到 0–255。输入由同一参考 Y 图经 Pillow BICUBIC 降到 960×540，`reducing_gap=None`。因此这是合成 scale-4 复原评测，不是无损原始画面比较。

## 指标

- 逐图/逐帧报告 Y-PSNR（peak=255）和 Y-SSIM；同时报告全图以及 shave=8 中心裁边结果。
- SSIM 使用 11×11 高斯窗、sigma=1.5、C1=0.01²、C2=0.03²；边界使用零填充。
- 汇总值是逐帧算术平均；视频片段另给逐帧 PSNR 增益、最差帧和负增益帧数。
- 连续性使用 shave=8 后的帧间亮度差 MAE：比较预测输出相邻帧差与 4K 参考相邻帧差，单位为 8-bit Y 级。该指标未做运动补偿，不应单独称作感知闪烁分数。
- 视觉材料只作检查辅助；放大图、压缩演示视频不能替代原始逐像素指标。

## 重现

在仓库根目录准备隔离环境并下载公开数据：

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -e ".[quality,test]"
.\.venv\Scripts\python.exe scripts\download_r0_quality_data.py
```

运行完整评测（结果目录必须为空或不存在，避免覆盖旧证据）：

```powershell
.\.venv\Scripts\python.exe -m experiments.r0_4k_quality_20261006.evaluate `
  --source-dir .data\r0_4k_quality_20261006\sources `
  --output-dir results\r0_4k_quality_20261006
```

若已有相同公开素材的部分下载缓存，可传入 `--partial-source-dir`；程序会复制缓存并通过 HTTP Range 续传，不会修改原缓存。50 fps 原始 YUV 每段解压后约 7.5 GB；它们及 HEVC 原始文件均留在 `.data/`。

结果包含 `evaluation_manifest.json`（原始源、抽样帧、哈希、版本及限制）、20 张 `per_image_metrics.csv`、500 行 `per_clip_frame_metrics.csv`、10 行 `per_clip_summary.csv`、失败/最差案例 CSV、低增益案例接触表和一段 10 fps 软件演示。复跑时使用同一 source file 哈希、模型量化目录哈希和脚本版本。

公开来源： [UVG Dataset](https://ultravideo.fi/dataset.html)。论文：A. Mercat, M. Viitanen, J. Vanne, “UVG dataset: 50/120fps 4K sequences for video codec analysis and development,” ACM MMSys, 2020。
