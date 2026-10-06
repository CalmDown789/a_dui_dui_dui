"""One-time paired evaluation on official DIV2K validation IDs 0801-0900."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import EvalDataset
from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y
from member_a.model import FSRCNNSubpixel
from member_a.quantization import quantized_forward_float


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_model(path: Path, device: torch.device) -> FSRCNNSubpixel:
    saved = torch.load(path, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    return model.to(device).eval()


def scales_from_bundle(quant_dir: Path) -> dict[str, float]:
    spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    return {layer["name"]: float(layer["output_scale"])
            for layer in spec["layers"] if layer["name"] != "subpixel"}


def metrics(target: torch.Tensor, output: torch.Tensor) -> tuple[float, float]:
    return psnr_y(target, output, border=2), ssim_y(target, output, border=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hr-dir", type=Path,
                        default=ROOT / ".data/model_optimization/datasets/div2k_official_valid/HR")
    parser.add_argument("--dataset-manifest", type=Path,
                        default=ROOT / ".data/model_optimization/datasets/div2k_official_valid/manifest.json")
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint-name", default="candidate_qat_fp32.pth")
    parser.add_argument("--candidate-quant", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    dataset_manifest = json.loads(args.dataset_manifest.resolve().read_text(encoding="utf-8"))
    if dataset_manifest.get("dataset") != "DIV2K_official_validation_HR" or dataset_manifest.get("images") != 100:
        parser.error("Official validation manifest is missing or invalid")
    dataset = EvalDataset(args.hr_dir.resolve())
    if len(dataset) != 100:
        parser.error(f"Expected 100 official DIV2K validation images, got {len(dataset)}")
    checkpoint = args.candidate_run.resolve() / args.candidate_checkpoint_name
    if not checkpoint.is_file():
        parser.error(f"Candidate checkpoint missing: {checkpoint}")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty result directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    frozen_model = load_model(ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth", device)
    candidate_model = load_model(checkpoint, device)
    candidate_quant = args.candidate_quant.resolve()
    candidate_scales = scales_from_bundle(candidate_quant)
    frozen_integer = FixedReference(ROOT / "artifacts/quant")
    candidate_integer = FixedReference(candidate_quant)
    rows: list[dict] = []

    for index in range(len(dataset)):
        name, lr, hr = dataset[index]
        lr_batch = lr.unsqueeze(0).to(device)
        hr_batch = hr.unsqueeze(0).to(device)
        with torch.inference_mode():
            frozen_fp = frozen_model(lr_batch).clamp(0.0, 1.0).cpu()
            candidate_fp = candidate_model(lr_batch).clamp(0.0, 1.0).cpu()
            candidate_qdq = quantized_forward_float(candidate_model, lr_batch, candidate_scales).clamp(0.0, 1.0).cpu()
            bicubic = F.interpolate(lr_batch, size=hr_batch.shape[-2:], mode="bicubic",
                                    align_corners=False).clamp(0.0, 1.0).cpu()
        lr_u8 = np.floor(lr.squeeze(0).numpy() * 255.0 + 0.5).astype(np.uint8)
        frozen_u8 = frozen_integer.run(lr_u8)["output"][:, :, 0]
        candidate_u8 = candidate_integer.run(lr_u8)["output"][:, :, 0]
        frozen_int = torch.from_numpy(frozen_u8.astype(np.float32) / 255.0)[None, None]
        candidate_int = torch.from_numpy(candidate_u8.astype(np.float32) / 255.0)[None, None]
        row = {"image": name}
        outputs = {
            "bicubic": bicubic,
            "frozen_fp32": frozen_fp,
            "frozen_integer": frozen_int,
            "candidate_fp32": candidate_fp,
            "candidate_qdq": candidate_qdq,
            "candidate_integer": candidate_int,
        }
        for key, output in outputs.items():
            row[f"{key}_psnr_db"], row[f"{key}_ssim"] = metrics(hr_batch.cpu(), output)
        row["candidate_integer_delta_vs_frozen_db"] = row["candidate_integer_psnr_db"] - row["frozen_integer_psnr_db"]
        row["candidate_quant_loss_db"] = row["candidate_fp32_psnr_db"] - row["candidate_integer_psnr_db"]
        rows.append(row)
        print(f"DIV2K valid {index + 1}/100 {name} done", flush=True)

    metric_keys = [key for key in rows[0] if key.endswith(("_psnr_db", "_ssim"))]
    summary_group = {"samples": len(rows), **{key: float(np.mean([row[key] for row in rows])) for key in metric_keys}}
    deltas = np.asarray([row["candidate_integer_delta_vs_frozen_db"] for row in rows], dtype=np.float64)
    rng = np.random.default_rng(20261007)
    bootstrap = rng.choice(deltas, size=(20_000, deltas.size), replace=True).mean(axis=1)
    summary_group["candidate_integer_delta_vs_frozen_db"] = float(deltas.mean())
    summary_group["candidate_integer_delta_bootstrap_95pct_ci_db"] = [
        float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))
    ]
    csv_path = output_dir / "per_image_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "member-a-official-div2k-validation-eval-v1",
        "status": "ONE_TIME_INDEPENDENT_SOFTWARE_EVALUATION_NOT_BOARD_ACCEPTANCE",
        "dataset_source": "Official DIV2K validation HR, IDs 0801-0900; not used for training or checkpoint selection.",
        "dataset_archive_sha256": dataset_manifest["archive_sha256"],
        "image_collection_sha256": dataset_manifest["image_collection_sha256"],
        "downsampling": "Y channel from official validation HR; even crop; Pillow bicubic x2, matching the Member A training/evaluation preprocessing. This is not the official MATLAB LR track.",
        "metrics": "Per-image Y PSNR/SSIM, border=2; report arithmetic mean over 100 images.",
        "frozen_checkpoint_sha256": sha256(ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"),
        "frozen_quant_params_sha256": sha256(ROOT / "artifacts/quant/quant_params.json"),
        "candidate_checkpoint_sha256": sha256(checkpoint),
        "candidate_quant_params_sha256": sha256(candidate_quant / "quant_params.json"),
        "groups": {"DIV2K_official_valid_100": summary_group},
        "scope_limits": [
            "A one-time independent image-quality check; no hyperparameters or checkpoint will be selected based on these scores.",
            "Pillow bicubic degradation differs from the official MATLAB-bicubic LR track and is stated explicitly.",
            "Software reference only; not RTL, FPGA timing, or board-image evidence.",
            "DIV2K is made available for academic research only; do not redistribute source images or derived model artifacts without confirming applicable rights.",
        ],
        "per_image_csv": csv_path.name,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["groups"], indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
