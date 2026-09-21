from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from member_b.golden import GoldenModel, file_digest
from member_b.model import TinySR


def verify(delivery: Path) -> dict:
    delivery = Path(delivery)
    manifest = json.loads((delivery / "delivery_manifest.json").read_text(encoding="utf-8"))
    artifacts = delivery / "artifacts"
    required = [
        artifacts / "model" / "model_fp32.pt",
        artifacts / "model" / "training_log.csv",
        artifacts / "quant" / "quant_params.json",
        artifacts / "evaluation" / "metrics.csv",
        artifacts / "evaluation" / "comparison.png",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise AssertionError(f"Missing required files: {missing}")

    checkpoint = torch.load(artifacts / "model" / "model_fp32.pt", map_location="cpu", weights_only=False)
    model = TinySR()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    with torch.inference_mode():
        output = model(torch.zeros(1, 1, 360, 640))
    if tuple(output.shape) != (1, 1, 720, 1280):
        raise AssertionError(f"Unexpected model output shape: {tuple(output.shape)}")

    golden = GoldenModel(artifacts / "quant")
    vector_results = {}
    for case_dir in sorted((artifacts / "test_vectors").iterdir()):
        if not case_dir.is_dir():
            continue
        case_manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        for filename, expected in case_manifest["files"].items():
            actual = file_digest(case_dir / filename)
            if actual != {k: expected[k] for k in ("bytes", "crc32", "sha256")}:
                raise AssertionError(f"Checksum mismatch: {case_dir.name}/{filename}")
        input_shape = case_manifest["files"]["input_y_u8.bin"]["shape"]
        input_u8 = np.fromfile(case_dir / "input_y_u8.bin", dtype=np.uint8).reshape(input_shape)
        regenerated = golden.run(input_u8)
        expected_output = np.fromfile(case_dir / "output_y_u8.bin", dtype=np.uint8).reshape(regenerated.shape)
        exact = bool(np.array_equal(regenerated, expected_output))
        if not exact:
            raise AssertionError(f"Golden regeneration mismatch: {case_dir.name}")
        vector_results[case_dir.name] = {"exact": True, "output_shape": list(regenerated.shape)}

    with (artifacts / "evaluation" / "metrics.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or rows[-1]["case"] != "AVERAGE":
        raise AssertionError("Metrics file has no AVERAGE row")
    if set(manifest["member_b_tasks"].values()) != {"complete"}:
        raise AssertionError("Manifest does not mark all B tasks complete")
    return {"status": "PASS", "model_output_shape": list(output.shape), "vectors": vector_results, "metrics_rows": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.delivery), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

