"""QAT fine-tune frozen and crop-resampled candidates into isolated run folders."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import EvalDataset
from member_a.model import FSRCNNSubpixel
from member_a.quantization import calibrate_activation_scales
from member_a.training import qat_finetune, seed_everything


BASE_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
RESAMPLED_CHECKPOINT_SHA256 = "784aab20d7ebfe35b34ec59638c457515b9aae7bf7ff49335c78a5529c35bb74"
BASE_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data/model_optimization/datasets")
    parser.add_argument("--source-run", type=Path, default=ROOT / ".data/model_optimization/dynamic_crop_ab_20e")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data/model_optimization/qat_ab_20261005")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()

    base_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant = ROOT / "artifacts/quant/quant_params.json"
    candidate_checkpoint = args.source_run / "epoch_resampled_crop/candidate_fp32.pth"
    if file_sha(base_checkpoint) != BASE_CHECKPOINT_SHA256:
        parser.error("Frozen checkpoint hash mismatch; refusing to continue")
    if file_sha(frozen_quant) != BASE_QUANT_SHA256:
        parser.error("Frozen quantization hash mismatch; refusing to continue")
    if file_sha(candidate_checkpoint) != RESAMPLED_CHECKPOINT_SHA256:
        parser.error("Resampled candidate checkpoint hash mismatch; refusing to continue")
    manifest_path = args.data_dir.resolve() / "dataset_manifest.json"
    if not manifest_path.is_file():
        parser.error("Verified T91/Set5 dataset manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("T91", {}).get("sha256") != "d903f5e8e3c43c92fc5009d33378de41a3a651d05cd86f79339843ebaf7af65c":
        parser.error("T91 source hash mismatch")
    if manifest.get("Set5", {}).get("sha256") != "b9cbe9ec0e9b09f440d75f73870598005439f54d4b9dc8a33e801fd2ecb3d79e":
        parser.error("Set5 source hash mismatch")
    if args.epochs <= 0:
        parser.error("--epochs must be positive")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    calibration_set = EvalDataset(args.data_dir.resolve() / "set5")
    calibration_samples = [calibration_set[i][1].unsqueeze(0) for i in range(len(calibration_set))]
    sources = {
        "frozen_start_qat": base_checkpoint,
        "resampled_start_qat": candidate_checkpoint,
    }
    arms = []
    try:
        for name, checkpoint_path in sources.items():
            arm_dir = output_dir / name
            arm_dir.mkdir()
            seed_everything(args.seed)
            saved = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            model = FSRCNNSubpixel()
            model.load_state_dict(saved["state_dict"], strict=True)
            model.to(device).eval()
            scales = calibrate_activation_scales(model, calibration_samples, device)
            qat_log = qat_finetune(
                model, args.data_dir.resolve() / "t91", scales, arm_dir, device,
                epochs=args.epochs, batch_size=16,
            )
            qat_path = arm_dir / "fsrcnn_d16_s8_m1_c16_x2_qat.pth"
            arm = {
                "name": name,
                "source_checkpoint_sha256": file_sha(checkpoint_path),
                "qat_checkpoint": str(qat_path.relative_to(ROOT)),
                "qat_checkpoint_sha256": file_sha(qat_path),
                "epochs": args.epochs,
                "seed": args.seed,
                "learning_rate": 1.0e-5,
                "training_samples_per_epoch": 91 * 64,
                "qat_log": qat_log,
            }
            (arm_dir / "training_summary.json").write_text(
                json.dumps(arm, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            arms.append(arm)
            print(json.dumps(arm, ensure_ascii=False), flush=True)
        summary = {
            "schema": "member-a-qat-ab-v1",
            "status": "TRAINED",
            "base_checkpoint_sha256": BASE_CHECKPOINT_SHA256,
            "base_quant_params_sha256": BASE_QUANT_SHA256,
            "dataset_manifest": manifest,
            "device": str(device),
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            "controlled_change": "5-epoch QAT fine-tuning, comparing a frozen baseline and the previous dynamic-crop candidate",
            "calibration_images": "all five Set5 images; selection/diagnostic only, not final independent evidence",
            "training_images": "verified T91; raw data remains ignored local .data",
            "arms": arms,
        }
        (output_dir / "run_manifest.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except BaseException as error:
        failure = {"status": "TRAINING_FAILED", "error": f"{type(error).__name__}: {error}", "arms": arms}
        (output_dir / "run_manifest.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
