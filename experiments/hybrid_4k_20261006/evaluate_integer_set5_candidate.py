from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y, ssim_y


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Secondary exact-integer 2x Set5 compatibility check")
    parser.add_argument("--set5-dir", type=Path, required=True)
    parser.add_argument("--baseline-quant-dir", type=Path, required=True)
    parser.add_argument("--candidate-quant-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Evaluation results must remain under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty evaluation directory: {output_dir}")
    images = sorted(args.set5_dir.glob("*.png"))
    if len(images) != 5:
        raise ValueError(f"Expected exactly five Set5 PNG images, got {len(images)}")
    baseline = FixedReference(args.baseline_quant_dir)
    candidate = FixedReference(args.candidate_quant_dir)
    rows: list[dict[str, float | str]] = []
    for path in images:
        with Image.open(path) as source:
            hr_image = source.convert("YCbCr").getchannel("Y")
            width = hr_image.width - hr_image.width % 2
            height = hr_image.height - hr_image.height % 2
            hr_image = hr_image.crop((0, 0, width, height))
            lr_image = hr_image.resize((width // 2, height // 2), Image.Resampling.BICUBIC)
            hr = np.asarray(hr_image, dtype=np.uint8).copy()
            lr = np.asarray(lr_image, dtype=np.uint8).copy()
        base_out = baseline.run(lr)["output"][:, :, 0]
        cand_out = candidate.run(lr)["output"][:, :, 0]
        hr_t = torch.from_numpy(hr.astype(np.float64) / 255.0)[None, None]
        base_t = torch.from_numpy(base_out.astype(np.float64) / 255.0)[None, None]
        cand_t = torch.from_numpy(cand_out.astype(np.float64) / 255.0)[None, None]
        base_psnr, cand_psnr = psnr_y(hr_t, base_t, border=2), psnr_y(hr_t, cand_t, border=2)
        base_ssim, cand_ssim = ssim_y(hr_t, base_t, border=2), ssim_y(hr_t, cand_t, border=2)
        rows.append(
            {
                "image": path.name,
                "source_sha256": _digest(path),
                "baseline_integer_psnr_db": base_psnr,
                "candidate_integer_psnr_db": cand_psnr,
                "candidate_delta_psnr_db": cand_psnr - base_psnr,
                "baseline_integer_ssim": base_ssim,
                "candidate_integer_ssim": cand_ssim,
                "candidate_delta_ssim": cand_ssim - base_ssim,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "per_image_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metrics = {
        key: float(np.mean([float(row[key]) for row in rows]))
        for key in [
            "baseline_integer_psnr_db",
            "candidate_integer_psnr_db",
            "candidate_delta_psnr_db",
            "baseline_integer_ssim",
            "candidate_integer_ssim",
            "candidate_delta_ssim",
        ]
    }
    summary = {
        "schema": "member-a-candidate-set5-integer-sidecheck-v1",
        "status": "SECONDARY_EXACT_INTEGER_2X_CHECK_NOT_FORMAL_RELEASE",
        "source_split": "Set5 standard 2x Pillow bicubic input; not used in FFmpeg candidate training/QAT",
        "metrics": "Y PSNR/SSIM; shave=2; integer FSRCNN x2 output before Keys x2 stage",
        "samples": len(rows),
        "baseline_quant_params_sha256": _digest(args.baseline_quant_dir / "quant_params.json"),
        "candidate_quant_params_sha256": _digest(args.candidate_quant_dir / "quant_params.json"),
        "means": metrics,
        "per_image_csv": str(csv_path),
        "limitations": [
            "Only five Set5 images; this is a secondary compatibility check, not the primary 4K hybrid video metric.",
            "Candidate was trained for a 4x hybrid pipeline, while this check observes the 2x FSRCNN stage only.",
            "No FPGA/RTL bit-exact test or board validation is included.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
