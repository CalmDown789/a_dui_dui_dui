"""Package the QAT/EMA integer candidate as a portable, explicitly experimental handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = ROOT / ".data/model_optimization/qat_ema_refine_20261006"
DEFAULT_SOURCE = DEFAULT_RUN / "candidate_delivery_v2"
DEFAULT_QUANT = DEFAULT_RUN / "candidate_quantized"
DEFAULT_OUTPUT = ROOT / "experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2"

EXPECTED_FROZEN_CHECKPOINT = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
EXPECTED_FROZEN_QUANT = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"
EXPECTED_CANDIDATE_CHECKPOINT = "10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a"
EXPECTED_CANDIDATE_QUANT = "12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_json(path: Path, updates: dict) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(updates)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--quant-dir", type=Path, default=DEFAULT_QUANT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    source_dir = args.source_dir.resolve()
    quant_dir = args.quant_dir.resolve()
    output_dir = args.output_dir.resolve()
    checkpoint = run_dir / "candidate_ema_qat_fp32.pth"
    frozen_checkpoint = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant = ROOT / "artifacts/quant/quant_params.json"
    candidate_manifest_path = source_dir / "candidate_delivery_manifest.json"
    for required in (checkpoint, frozen_checkpoint, frozen_quant,
                     run_dir / "training_log.csv", run_dir / "run_manifest.json",
                     quant_dir / "quant_params.json", candidate_manifest_path):
        if not required.is_file():
            parser.error(f"Required source file is missing: {required}")
    if sha256(frozen_checkpoint) != EXPECTED_FROZEN_CHECKPOINT:
        parser.error("Frozen A checkpoint hash changed; refusing to package candidate")
    if sha256(frozen_quant) != EXPECTED_FROZEN_QUANT:
        parser.error("Frozen A quantization hash changed; refusing to package candidate")

    candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    checks = {
        "candidate_checkpoint_sha256": (checkpoint, EXPECTED_CANDIDATE_CHECKPOINT),
        "candidate_quant_params_sha256": (quant_dir / "quant_params.json", EXPECTED_CANDIDATE_QUANT),
    }
    for key, (path, expected) in checks.items():
        if sha256(path) != expected or candidate_manifest.get(key) != expected:
            parser.error(f"{key} does not match the recorded candidate identity")
    if candidate_manifest.get("status") != "EXPERIMENTAL_NOT_RELEASED":
        parser.error("Candidate must remain explicitly unreleased")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite non-empty delivery directory: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, output_dir, dirs_exist_ok=True)
    shutil.copytree(quant_dir, output_dir / "quant")
    training_dir = output_dir / "training"
    training_dir.mkdir()
    for name in ("candidate_ema_qat_fp32.pth", "training_log.csv", "run_manifest.json"):
        shutil.copy2(run_dir / name, training_dir / name)

    candidate_delivery = portable_json(output_dir / "candidate_delivery_manifest.json", {
        "artifacts": {
            "test_vectors": "test_vectors_96x54",
            "full_reference": "full_reference",
            "full_integer_golden": "full_integer_golden",
        },
        "limitations": [
            "This checked-in bundle is an experimental candidate and does not replace frozen A R0.",
            "Candidate-specific B RTL regression, B/C synthesis, timing, and board validation remain required before adoption.",
        ],
    })
    candidate_delivery["integer_golden_summary"]["quant_params"]["path"] = "quant/quant_params.json"
    (output_dir / "candidate_delivery_manifest.json").write_text(
        json.dumps(candidate_delivery, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    portable_json(output_dir / "full_integer_golden/manifest.json", {
        "quant_params": {
            **json.loads((output_dir / "full_integer_golden/manifest.json").read_text(encoding="utf-8"))["quant_params"],
            "path": "../quant/quant_params.json",
        },
        "acceptance_boundary": "Experimental PC integer reference only; not the frozen A release, not B RTL revalidated, and not board accepted",
    })

    readme = """# R0 QAT/EMA v2 — experimental candidate only

This is a portable Member A handoff for a quantization-aware fine-tuning experiment. It is **not** the formal A R0 release and must not replace the frozen production weights or ROMs.

## Contents

- `quant/`: candidate INT8 weights, INT32 biases, Q1.15 PReLU values, quantization parameters, and `.bin`/`.mem`/`.coe` exports.
- `test_vectors_96x54/`: six small inputs with per-layer accumulators and activations.
- `full_integer_golden/`: full 960×540 to 1920×1080 input/output and per-stage hashes.
- `full_reference/`: QDQ/FP32 software references used to audit the candidate conversion.
- `training/`: selected checkpoint, training log, and run manifest.
- `bundle_manifest.json`: SHA-256 and byte count for every packaged file except the manifest itself.

## Identity and measured scope

- Candidate checkpoint SHA-256: `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`.
- Candidate `quant_params.json` SHA-256: `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`.
- On the one-time held-out DIV2K official validation-HR set (100 images), the integer candidate measured +0.0664 dB mean PSNR over frozen R0; the paired bootstrap 95% interval was [+0.0445, +0.0987] dB.
- This is a modest PC software quality result. MAC count is unchanged, and it does not establish FPGA resource, timing, throughput, or image quality.

## Verify

From the repository root, using the project Python environment:

```powershell
$env:PYTHONPATH = 'src'
python experiments/model_optimization_20261005/verify_candidate_delivery.py `
  --delivery-dir experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2 `
  --quant-dir experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/quant `
  --checkpoint experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/training/candidate_ema_qat_fp32.pth `
  --recompute-full
```

The report is only an A-side integer-reference verification. B must run candidate-specific RTL vector and full-frame comparison; C/team must separately evaluate candidate resources/timing and the physical board before discussing promotion. The official R0 assets remain unchanged.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    files = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "bundle_manifest.json":
            continue
        files[path.relative_to(output_dir).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    bundle = {
        "schema": "member-a-experimental-candidate-bundle-v1",
        "status": "EXPERIMENTAL_NOT_RELEASED",
        "candidate_checkpoint_sha256": EXPECTED_CANDIDATE_CHECKPOINT,
        "candidate_quant_params_sha256": EXPECTED_CANDIDATE_QUANT,
        "frozen_checkpoint_sha256": EXPECTED_FROZEN_CHECKPOINT,
        "frozen_quant_params_sha256": EXPECTED_FROZEN_QUANT,
        "file_count": len(files),
        "files": files,
        "promotion_gate": [
            "B candidate-specific bit-exact RTL regression",
            "C/team candidate ROM synthesis and implementation evaluation",
            "Physical board image and interface validation",
            "Explicit team decision; do not replace frozen R0 before all gates pass",
        ],
    }
    (output_dir / "bundle_manifest.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({
        "status": "PACKAGED_EXPERIMENTAL_ONLY",
        "path": str(output_dir),
        "files": len(files),
        "candidate_checkpoint_sha256": EXPECTED_CANDIDATE_CHECKPOINT,
        "candidate_quant_params_sha256": EXPECTED_CANDIDATE_QUANT,
        "frozen_assets_unchanged": True,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
