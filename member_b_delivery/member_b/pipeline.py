from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader

from .dataset import PairedPatchDataset, generate_paired_dataset, load_validation_pairs
from .golden import GoldenModel, export_test_vector, file_digest
from .metrics import psnr_u8, ssim_u8
from .model import TinySR, model_contract
from .quantization import calibrate_activation_scales, export_quant_bundle, qat_forward


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def tensor_to_u8(tensor: torch.Tensor) -> np.ndarray:
    return np.clip(np.rint(tensor.detach().cpu().squeeze().numpy() * 255.0), 0, 255).astype(np.uint8)


def train(model: TinySR, dataset_root: Path, artifacts: Path, device: torch.device, steps: int, batch_size: int) -> list[dict]:
    dataset = PairedPatchDataset(dataset_root, patch_lr=48, samples_per_epoch=max(steps * batch_size, batch_size))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=device.type == "cuda")
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    loss_fn = nn.MSELoss()
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps, eta_min=1.0e-5)
    model.train()
    log: list[dict] = []
    start = time.perf_counter()
    iterator = iter(loader)
    for step in range(1, steps + 1):
        try:
            lr, hr = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            lr, hr = next(iterator)
        lr = lr.to(device, non_blocking=True)
        hr = hr.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        pred = model.forward_raw(lr)
        loss = loss_fn(pred, hr)
        loss.backward()
        optimizer.step()
        scheduler.step()
        report_interval = 25 if steps <= 3000 else 100
        if step == 1 or step % report_interval == 0 or step == steps:
            log.append({"step": step, "mse_loss": float(loss.detach().cpu()), "learning_rate": scheduler.get_last_lr()[0], "elapsed_seconds": time.perf_counter() - start})
            print(f"train step {step:04d}/{steps}: MSE={log[-1]['mse_loss']:.6f}")
    with (artifacts / "training_log.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["step", "mse_loss", "learning_rate", "elapsed_seconds"])
        writer.writeheader()
        writer.writerows(log)
    return log


def qat_finetune(
    model: TinySR,
    dataset_root: Path,
    artifacts: Path,
    device: torch.device,
    activation_scales: tuple[float, float],
    steps: int,
    batch_size: int,
) -> list[dict]:
    dataset = PairedPatchDataset(dataset_root, patch_lr=48, samples_per_epoch=max(steps * batch_size, batch_size), seed=20261920)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=device.type == "cuda")
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps, eta_min=5.0e-6)
    loss_fn = nn.MSELoss()
    model.train()
    iterator = iter(loader)
    log: list[dict] = []
    start = time.perf_counter()
    for step in range(1, steps + 1):
        try:
            lr, hr = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            lr, hr = next(iterator)
        lr = lr.to(device, non_blocking=True)
        hr = hr.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        pred = qat_forward(model, lr, activation_scales)
        float_pred = model.forward_raw(lr)
        loss = 0.8 * loss_fn(pred, hr) + 0.2 * loss_fn(float_pred, hr)
        loss.backward()
        optimizer.step()
        scheduler.step()
        report_interval = 25 if steps <= 1000 else 100
        if step == 1 or step % report_interval == 0 or step == steps:
            log.append({"step": step, "mse_loss": float(loss.detach().cpu()), "learning_rate": scheduler.get_last_lr()[0], "elapsed_seconds": time.perf_counter() - start})
            print(f"QAT step {step:04d}/{steps}: MSE={log[-1]['mse_loss']:.6f}")
    with (artifacts / "qat_log.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["step", "mse_loss", "learning_rate", "elapsed_seconds"])
        writer.writeheader()
        writer.writerows(log)
    return log


def _make_vectors(dataset_root: Path, vectors_dir: Path, golden: GoldenModel) -> None:
    zero = np.zeros((360, 640, 1), dtype=np.uint8)
    ramp = np.tile(np.arange(640, dtype=np.uint16) * 255 // 639, (360, 1)).astype(np.uint8)[:, :, None]
    natural = np.asarray(Image.open(sorted((dataset_root / "val" / "lr").glob("*.png"))[0]).convert("L"), dtype=np.uint8)[:, :, None]
    for name, array in (("zero", zero), ("ramp", ramp), ("natural", natural)):
        export_test_vector(vectors_dir / name, array, golden)
        Image.fromarray(array[:, :, 0], mode="L").save(vectors_dir / name / "input_preview.png")
        output = golden.run(array)
        Image.fromarray(output[:, :, 0], mode="L").save(vectors_dir / name / "output_preview.png")


def evaluate(model: TinySR, dataset_root: Path, golden: GoldenModel, output_dir: Path, device: torch.device) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    comparison_payload = None
    model.eval()
    with torch.inference_mode():
        for name, lr, hr in load_validation_pairs(dataset_root):
            fp = model(lr.unsqueeze(0).to(device))
            fp_u8 = tensor_to_u8(fp)
            hr_u8 = tensor_to_u8(hr)
            lr_u8 = tensor_to_u8(lr)
            bicubic = np.asarray(Image.fromarray(lr_u8).resize((1280, 720), Image.Resampling.BICUBIC), dtype=np.uint8)
            int8_u8 = golden.run(lr_u8[:, :, None])[:, :, 0]
            row = {
                "case": name,
                "bicubic_psnr_db": psnr_u8(hr_u8, bicubic),
                "bicubic_ssim": ssim_u8(hr_u8, bicubic),
                "fp32_psnr_db": psnr_u8(hr_u8, fp_u8),
                "fp32_ssim": ssim_u8(hr_u8, fp_u8),
                "int8_psnr_db": psnr_u8(hr_u8, int8_u8),
                "int8_ssim": ssim_u8(hr_u8, int8_u8),
            }
            records.append(row)
            if comparison_payload is None:
                comparison_payload = (name, bicubic, fp_u8, int8_u8, hr_u8)
    numeric_keys = [k for k in records[0] if k != "case"]
    average = {"case": "AVERAGE"}
    average.update({k: float(np.mean([row[k] for row in records])) for k in numeric_keys})
    records.append(average)
    with (output_dir / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    name, bicubic, fp_u8, int8_u8, hr_u8 = comparison_payload
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    for ax, image, title in zip(axes.ravel(), (bicubic, fp_u8, int8_u8, hr_u8), ("Bicubic", "TinySR FP32", "TinySR INT8 golden", "Ground truth")):
        ax.imshow(image, cmap="gray", vmin=0, vmax=255)
        ax.set_title(title)
        ax.axis("off")
    fig.suptitle(f"Validation comparison: {name}")
    fig.savefig(output_dir / "comparison.png", dpi=150)
    plt.close(fig)
    return records


def write_documents(docs_dir: Path, output_root: Path, device: torch.device, log: list[dict], metrics: list[dict]) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    avg = metrics[-1]
    readme = f"""# 成员 B 交付包\n\n本目录对应桌面 `{output_root}` 中的可执行交付。成员 B 已完成模型、配对数据、快速训练、INT8 量化、纯 NumPy 黄金模型、逐层测试向量和画质评估。\n\n## 运行环境\n\n- Python: {os.sys.version.split()[0]}\n- PyTorch: {torch.__version__}\n- 训练设备: {device}\n\n## 复现命令\n\n```powershell\npython run_all.py --output \"{output_root}\" --docs-dir \"{docs_dir}\"\npython verify_delivery.py --delivery \"{output_root}\"\n```\n\n## 当前结果\n\n- 最后记录的训练 MSE: {log[-1]['mse_loss']:.6f}\n- INT8 平均 PSNR: {avg['int8_psnr_db']:.3f} dB\n- INT8 平均 SSIM: {avg['int8_ssim']:.5f}\n- 双三次平均 PSNR: {avg['bicubic_psnr_db']:.3f} dB\n- 双三次平均 SSIM: {avg['bicubic_ssim']:.5f}\n\n详细量化和接口定义见 `接口与量化约定.md`。\n"""
    interface = """# 接口与量化约定\n\n## 网络\n\n输入为 640×360 单通道 Y，依次经过 3×3 Conv 1→8、标量 PReLU、3×3 Conv 8→16、标量 PReLU、3×3 Conv 16→4，最后 PixelShuffle×2 输出 1280×720。卷积采用 PyTorch 交叉相关语义和一圈零填充。\n\n## 排列\n\n权重文件为 OIHW；特征和测试向量为 HWC 行优先。PixelShuffle 通道 0、1、2、3 分别对应 2×2 输出块的左上、右上、左下、右下。\n\n## 数值\n\n外部输入输出为 uint8 Y。模型输入以同一原始字节解释为 int8，zero-point=-128，scale=1/255。隐藏激活为逐层对称 int8，zero-point=0。权重为按输出通道对称 int8，每个输出通道具有独立 scale 与 Q31 重量化乘数；偏置为 int32。PReLU 斜率使用 Q1.15。所有除法使用最近舍入且恰好一半时远离零，最终饱和至 [-128,127]。\n\n## 文件\n\n所有精确尺寸、scale、zero-point、Q31 乘数和文件名均以 `artifacts/quant/quant_params.json` 为准。逐层测试向量位于 `artifacts/test_vectors`，每个用例都有 CRC32 与 SHA-256。\n"""
    report = f"""# 成员 B 交付报告\n\n## 已完成任务\n\n- B1：实现三层 PyTorch 超分模型。\n- B2：生成 640×360 至 1280×720 的配对 Y 通道小样本数据。\n- B3：完成快速训练并保存 FP32 权重和训练日志。\n- B4：导出 INT8 权重、INT32 偏置、Q1.15 PReLU 与 Q31 重量化参数。\n- B5：实现不依赖 PyTorch 运算子的纯 NumPy 整数黄金模型。\n- B6：生成零图、梯度图、自然图三组全尺寸逐层测试向量。\n- B7：计算双三次、FP32 与 INT8 的 PSNR/SSIM。\n- B8：输出联调用对比图和逐层二进制结果。\n\n## 结果摘要\n\nINT8 平均 PSNR 为 {avg['int8_psnr_db']:.3f} dB，SSIM 为 {avg['int8_ssim']:.5f}；双三次平均 PSNR 为 {avg['bicubic_psnr_db']:.3f} dB，SSIM 为 {avg['bicubic_ssim']:.5f}。这些数字来自程序生成的合成验证集，仅用于打通工程和联调；后续替换为项目真实数据后应重新训练与评估。\n\n## 联调判据\n\n成员 C 应先用零图和梯度图定位偏置、行列顺序、边界填充与 PixelShuffle，再使用自然图。各层输出应与测试向量逐字节一致；若硬件乘数实现不同，需在接口文档中记录允许误差。\n"""
    (docs_dir / "README.md").write_text(readme, encoding="utf-8")
    (docs_dir / "接口与量化约定.md").write_text(interface, encoding="utf-8")
    (docs_dir / "成员B交付报告.md").write_text(report, encoding="utf-8")


def run_pipeline(output_root: Path, docs_dir: Path, steps: int = 20000, qat_steps: int = 5000, batch_size: int = 8, seed: int = 20260920) -> dict:
    output_root = Path(output_root)
    docs_dir = Path(docs_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts = output_root / "artifacts"
    for child in ("dataset", "model", "quant", "test_vectors", "evaluation"):
        (artifacts / child).mkdir(parents=True, exist_ok=True)
    seed_everything(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")
    dataset_info = generate_paired_dataset(artifacts / "dataset")
    model = TinySR().to(device)
    log = train(model, artifacts / "dataset", artifacts / "model", device, steps, batch_size)
    validation = load_validation_pairs(artifacts / "dataset")
    calibrated = calibrate_activation_scales(model, [item[1] for item in validation], device)
    scales = (calibrated[0] * 0.95, calibrated[1] * 0.85)
    qat_log = qat_finetune(model, artifacts / "dataset", artifacts / "model", device, scales, qat_steps, batch_size)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "contract": model_contract(),
        "seed": seed,
        "fp32_steps": steps,
        "qat_steps": qat_steps,
        "activation_scales": scales,
    }
    torch.save(checkpoint, artifacts / "model" / "model_fp32.pt")
    (artifacts / "model" / "model_contract.json").write_text(json.dumps(model_contract(), ensure_ascii=False, indent=2), encoding="utf-8")
    quant_spec = export_quant_bundle(model, scales, artifacts / "quant")
    golden = GoldenModel(artifacts / "quant")
    _make_vectors(artifacts / "dataset", artifacts / "test_vectors", golden)
    metrics = evaluate(model, artifacts / "dataset", golden, artifacts / "evaluation", device)
    write_documents(docs_dir, output_root, device, qat_log, metrics)

    delivery_manifest = {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "python": os.sys.version,
        "torch": torch.__version__,
        "device": str(device),
        "seed": seed,
        "training_steps": steps,
        "qat_steps": qat_steps,
        "activation_scales": list(scales),
        "dataset": dataset_info,
        "documents_location": str(docs_dir),
        "member_b_tasks": {f"B{i}": "complete" for i in range(1, 9)},
    }
    (output_root / "delivery_manifest.json").write_text(json.dumps(delivery_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return delivery_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the complete Member B delivery")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--qat-steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    result = run_pipeline(args.output, args.docs_dir, steps=args.steps, qat_steps=args.qat_steps, batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
