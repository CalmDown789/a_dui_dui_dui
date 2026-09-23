from __future__ import annotations

from pathlib import Path
import hashlib
import json

import numpy as np
import torch

from .fixed_reference import FixedReference
from .model import FSRCNNSubpixel, mac_breakdown


REQUIRED = [
    "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth",
    "artifacts/model/model_contract.json",
    "artifacts/quant/quant_params.json",
    "artifacts/evaluation/set5_metrics.csv",
    "artifacts/evaluation/summary.json",
    "artifacts/full_reference/ref_out_fp32.npy",
    "artifacts/full_reference/ref_out_quant.npy",
    "artifacts/test_vectors/zero/manifest.json",
    "artifacts/test_vectors/impulse/manifest.json",
    "artifacts/test_vectors/ramp/manifest.json",
    "artifacts/test_vectors/random/manifest.json",
    "delivery_manifest.json",
]


def _sha256(path: Path, normalize_lf: bool = False) -> str:
    data = path.read_bytes()
    if normalize_lf:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def verify_delivery(root: Path) -> dict:
    root = root.resolve()
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing required delivery files: {missing}")
    checkpoint = torch.load(root / REQUIRED[0], map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(checkpoint["state_dict"])
    with torch.no_grad():
        output = model(torch.zeros(1, 1, 54, 96))
    if tuple(output.shape) != (1, 1, 108, 192):
        raise AssertionError(f"Unexpected model output shape: {tuple(output.shape)}")
    macs = mac_breakdown()
    if macs["total"] != 1_468_108_800:
        raise AssertionError(f"MAC count drifted: {macs['total']}")
    quant_dir = root / "artifacts" / "quant"
    reference = FixedReference(quant_dir)
    vector_checks: dict[str, str] = {}
    for case in ["zero", "impulse", "ramp", "random"]:
        case_dir = root / "artifacts" / "test_vectors" / case
        image = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(54, 96)
        outputs = reference.run(image)
        expected_path = case_dir / "output_hwc_uint8.bin"
        expected = np.fromfile(expected_path, dtype=np.uint8).reshape(108, 192, 1)
        if not np.array_equal(outputs["output"], expected):
            raise AssertionError(f"Fixed reference mismatch for {case}")
        vector_checks[case] = _sha256(expected_path)
    full = np.load(root / "artifacts/full_reference/ref_out_fp32.npy")
    full_quant = np.load(root / "artifacts/full_reference/ref_out_quant.npy")
    if full.shape != (1080, 1920):
        raise AssertionError(f"Unexpected full reference shape: {full.shape}")
    if full_quant.shape != (1080, 1920):
        raise AssertionError(f"Unexpected quantized full reference shape: {full_quant.shape}")
    metrics = json.loads((root / "artifacts/evaluation/summary.json").read_text(encoding="utf-8"))
    if metrics["set5"]["quant_psnr_loss_db"] > 1.0:
        raise AssertionError("Quantized PSNR loss exceeds 1 dB")
    manifest = json.loads((root / "delivery_manifest.json").read_text(encoding="utf-8"))
    bad_hashes = []
    for relative, metadata in manifest["files"].items():
        path = root / relative
        normalize_lf = metadata.get("normalization") == "lf"
        if not path.is_file() or _sha256(path, normalize_lf=normalize_lf) != metadata["sha256"]:
            bad_hashes.append(relative)
    if bad_hashes:
        raise AssertionError(f"Delivery manifest mismatch: {bad_hashes[:5]}")
    return {
        "status": "PASS",
        "model_output": list(output.shape),
        "full_reference": list(full.shape),
        "quant_full_reference": list(full_quant.shape),
        "gmac_per_frame": macs["gmac_per_frame"],
        "gmac_per_second_30fps": macs["gmac_per_second_30fps"],
        "vector_sha256": vector_checks,
        "quant_psnr_loss_db": metrics["set5"]["quant_psnr_loss_db"],
    }
