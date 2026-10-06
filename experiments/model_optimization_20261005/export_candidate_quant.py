"""Export an isolated candidate checkpoint and its recorded activation scales."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from member_a.model import FSRCNNSubpixel
from member_a.quantization import export_quantized_bundle


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--scales", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty quantized bundle: {output_dir}")
    checkpoint = args.checkpoint.resolve()
    scales = json.loads(args.scales.resolve().read_text(encoding="utf-8"))
    saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = FSRCNNSubpixel()
    model.load_state_dict(saved["state_dict"], strict=True)
    model.eval()
    output_dir.mkdir(parents=True, exist_ok=True)
    export_quantized_bundle(model, scales, output_dir)
    manifest = {
        "status": "EXPERIMENTAL_MEMBER_A_CANDIDATE_NOT_RELEASED",
        "checkpoint_sha256": sha256(checkpoint),
        "activation_scales_sha256": sha256(args.scales.resolve()),
        "quant_params_sha256": sha256(output_dir / "quant_params.json"),
        "quant_params": "quant_params.json",
    }
    (output_dir / "candidate_quant_export_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
