"""Build isolated integer vectors and a full-size Golden for the QAT candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.artifacts import (
    MEMBER_A_ACCEPTANCE_VECTOR_CASES,
    generate_fixed_vectors,
    generate_full_integer_golden,
    generate_full_reference,
)
from member_a.fixed_reference import FixedReference
from member_a.model import FSRCNNSubpixel


BASE_CHECKPOINT_SHA256 = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"
BASE_QUANT_SHA256 = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=root / ".data/model_optimization/div2k_qat_mix_20261005")
    parser.add_argument("--checkpoint-name", default="candidate_qat_fp32.pth")
    parser.add_argument("--quant-dir", type=Path, default=root / ".data/model_optimization/div2k_qat_mix_20261005/evaluation_calibration_ab/candidate_quantized")
    parser.add_argument("--output-dir", type=Path, default=root / ".data/model_optimization/div2k_qat_mix_20261005/candidate_delivery")
    args = parser.parse_args()

    frozen_checkpoint = root / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    frozen_quant_json = root / "artifacts/quant/quant_params.json"
    candidate_checkpoint = args.run_dir.resolve() / args.checkpoint_name
    quant_dir = args.quant_dir.resolve()
    output_dir = args.output_dir.resolve()
    if file_sha(frozen_checkpoint) != BASE_CHECKPOINT_SHA256 or file_sha(frozen_quant_json) != BASE_QUANT_SHA256:
        parser.error("Frozen assets changed; refusing to generate a candidate bundle")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite candidate delivery: {output_dir}")
    if not (quant_dir / "quant_params.json").is_file() or not candidate_checkpoint.is_file():
        parser.error("Candidate checkpoint or quantization bundle is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    vectors_dir = output_dir / "test_vectors_96x54"
    full_ref_dir = output_dir / "full_reference"
    full_integer_dir = output_dir / "full_integer_golden"
    for path in (vectors_dir, full_ref_dir, full_integer_dir):
        path.mkdir(parents=True, exist_ok=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)
    saved = torch.load(candidate_checkpoint, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    model.to(device).eval()
    quant_spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    scales = {layer["name"]: float(layer["output_scale"])
              for layer in quant_spec["layers"] if layer["name"] != "subpixel"}

    generate_fixed_vectors(
        quant_dir,
        vectors_dir,
        case_names=MEMBER_A_ACCEPTANCE_VECTOR_CASES,
    )
    generate_full_reference(model, scales, full_ref_dir, device)
    official_input = root / "artifacts/full_reference/input_960x540_y_u8.bin"
    if file_sha(official_input) != file_sha(full_ref_dir / "input_960x540_y_u8.bin"):
        raise RuntimeError("Candidate and frozen full-frame references do not use the same input bytes")
    golden_summary = generate_full_integer_golden(
        quant_dir, full_ref_dir / "input_960x540_y_u8.bin", full_integer_dir,
    )
    manifest_path = full_integer_dir / "manifest.json"
    golden_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    golden_manifest["status"] = "EXPERIMENTAL_MEMBER_A_CANDIDATE"
    golden_manifest["golden_class"] = "experimental_candidate_full_frame_integer_golden"
    golden_manifest["candidate_checkpoint_sha256"] = file_sha(candidate_checkpoint)
    golden_manifest["quant_params_sha256"] = file_sha(quant_dir / "quant_params.json")
    golden_manifest["quant_params"]["path"] = str(
        (quant_dir / "quant_params.json").relative_to(root)
    ).replace("\\", "/")
    golden_manifest["acceptance_boundary"] = "PC integer reference only; not yet substituted for frozen A assets, B RTL revalidated, or board accepted"
    manifest_path.write_text(json.dumps(golden_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    golden_summary["status"] = "EXPERIMENTAL_MEMBER_A_CANDIDATE"
    golden_summary["golden_class"] = "experimental_candidate_full_frame_integer_golden"
    golden_summary["quant_params"]["path"] = golden_manifest["quant_params"]["path"]

    exact = np.fromfile(full_integer_dir / "output_1920x1080_y_u8.bin", dtype=np.uint8)
    qdq = np.fromfile(full_ref_dir / "output_quant_1920x1080_y_u8.bin", dtype=np.uint8)
    if exact.size != 1920 * 1080 or qdq.size != exact.size:
        raise RuntimeError("Full-size candidate outputs have unexpected byte counts")
    delta = exact.astype(np.int16) - qdq.astype(np.int16)
    report = {
        "schema": "member-a-experimental-candidate-delivery-v1",
        "status": "EXPERIMENTAL_NOT_RELEASED",
        "candidate_checkpoint_sha256": file_sha(candidate_checkpoint),
        "candidate_quant_params_sha256": file_sha(quant_dir / "quant_params.json"),
        "frozen_checkpoint_sha256": file_sha(frozen_checkpoint),
        "frozen_quant_params_sha256": file_sha(frozen_quant_json),
        "full_input_sha256": file_sha(full_ref_dir / "input_960x540_y_u8.bin"),
        "full_integer_output_sha256": file_sha(full_integer_dir / "output_1920x1080_y_u8.bin"),
        "full_integer_output_bytes": int(exact.size),
        "qdq_vs_integer": {
            "byte_exact_matches": int(np.count_nonzero(delta == 0)),
            "bytes": int(delta.size),
            "max_absolute_difference": int(np.max(np.abs(delta))),
            "mean_absolute_difference": float(np.mean(np.abs(delta))),
            "mae_crc32_integer": f"{zlib.crc32(exact.tobytes()) & 0xFFFFFFFF:08x}",
            "mae_crc32_qdq": f"{zlib.crc32(qdq.tobytes()) & 0xFFFFFFFF:08x}",
        },
        "integer_golden_summary": golden_summary,
        "artifacts": {
            "test_vectors": str(vectors_dir.relative_to(root)),
            "full_reference": str(full_ref_dir.relative_to(root)),
            "full_integer_golden": str(full_integer_dir.relative_to(root)),
        },
        "limitations": [
            "All files in this directory are experimental and ignored by Git; official frozen A artifacts are unchanged.",
            "B/RTL bit-exact regression, B+C synthesis, FPGA timing, and board image capture remain required before adoption.",
        ],
    }
    (output_dir / "candidate_delivery_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
