# 当前状态 · 2026-10-09

依据本地冻结交付、最终构建收据、原始实验汇总及移机复审结果整理。此文是工作入口；测量证据仍以原报告和绑定源码/BIT 的清单为准。

## 当前基线

- ACX750-200T / xc7a200tfbg484-2；本轮 Vivado 2025.2，core 150 MHz，pause=0，输出条带 16 行。
- FSRCNN d16/s8/m1/c16：960×540 灰度输入 → 1920×1080 输出；每帧输入 518,400 B、输出 2,073,600 B。
- 四步整合：RTL retry 同拍到期修复、EVF2 直接解码、nonblocking 有界批读、sampled/16 细粒度计时。LAB 显式使用输入窗口 16、输出窗口 128；通用 API 的 timeout/full 默认不能与 LAB 默认混淆。
- BIT SHA256：`cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5`。
- DCP SHA256：`47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da`。

## 已有证据

- 四步整合方案 24 帧、原方案对照 6 帧，共 30 帧原始 Golden 审计通过。新方案 Natural16 协议循环约 12.61 fps。
- 后续同一新 BIT 的 32 次独立启动共 512 帧全部 Golden 一致。移机离线复审为 32 cases / 512 frames，通过；离线复审没有新增上板动作。
- 四步前后整帧中位数 79.584 → 79.241 ms，均值未改善，波动重叠；不能宣称健康帧耗时有明确收益。
- 输入 batch1 相对 batch32：整帧中位数下降 1.539 ms（1.96%），仅 4 轮独立重复，尚未并入冻结默认。
- 最终原生 setup/hold 余量 +0.018/+0.050 ns；DRC 无 error/critical。物理 I/O 状态仍 UNVERIFIED，整机 4K30 未实现。
- 新 BIT 尚未完成 PC4K 配对验证。旧 BIT 的 150 帧 PC4K 结果约 12.38 fps，仅属于历史配对；preview 提交时间不等于屏幕刷新。

## 下一步

1. B 先测输入 ACK 反馈的分段等待、窗口占满、队列水位及背压；当前输入约 45 ms、输出及验证约 29 ms。
2. 在完整板端缓存/commit/跨域 FIFO 容量核算后评估输入扩窗和 ACK 队列，保留正确性与所有失败记录。
3. 评估计算/发送与跨帧重叠，分别报告吞吐和单帧延迟。
4. 新候选重新绑定源码、约束、BIT/DCP，做平衡上板对照；新 BIT 与 PC4K 单独配对验收。

详见 `output/C_TO_B_LATENCY_HANDOFF_V2_20261009/交接文件_给B.md`、`文件地图与复现.md`、`reports/INTEGRATED_STEPS01_04_20261009/REVIEW.md`、`reports/HOST_IO_BATCH_BOARD_AB_20261009/` 与根目录外部 `.receipt.json`。
