"""Generate a new sequence from already-preprocessed uint8 Y files; never overwrite."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import platform
import subprocess
import sys
import time
import numpy as np
from PIL import Image
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from member_a.multiframe import verify_frozen_assets, quant_provenance, FROZEN_CHECKPOINT_SHA
from member_a.fixed_reference import FixedReference
from member_a.artifacts import _digest, _array_metadata


def generate(inputs_path, output_dir):
    if output_dir.exists():
        raise ValueError("Refusing to overwrite an existing output directory")
    verify_frozen_assets(ROOT)
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    entries = inputs["frames"]
    if not entries or len({item["frame_id"] for item in entries}) != len(entries):
        raise ValueError("Input frames must have unique IDs")
    for item in entries:
        if type(item["frame_id"]) is not int or item["frame_id"] < 0:
            raise ValueError("Invalid frame_id")
        path = inputs_path.parent / item["path"]
        if path.stat().st_size != 518400 or _digest(path)["sha256"] != item["sha256"]:
            raise ValueError("Input length/hash mismatch")
    started = datetime.now(timezone.utc).isoformat(); timer = time.perf_counter()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    reference = FixedReference(ROOT / "artifacts/quant")
    output_dir.mkdir(parents=True, exist_ok=False)
    frames = []
    for order, item in enumerate(entries):
        directory = output_dir / f"frame_{item['frame_id']:04d}"; directory.mkdir()
        raw = (inputs_path.parent / item["path"]).read_bytes()
        (directory / "input_y_u8.bin").write_bytes(raw)
        image = np.frombuffer(raw, dtype=np.uint8).reshape(540, 960)
        Image.fromarray(image).save(directory / "input.png")
        stages = {}
        for name, values in reference.iter_outputs(image):
            stages[name] = _array_metadata(values)
            if name == "output":
                (directory / "output_y_u8.bin").write_bytes(values.tobytes())
                Image.fromarray(values[:, :, 0]).save(directory / "output.png")
        frame = {"frame_id": item["frame_id"], "order": order,
                 "source": item.get("source", inputs.get("source")),
                 "source_frame_index": item.get("source_frame_index"),
                 "source_timestamp_seconds": item.get("source_timestamp_seconds"), "stage_digests": stages}
        for key, name in (("input", "input_y_u8.bin"), ("golden", "output_y_u8.bin")):
            frame[key] = {"path": f"{directory.name}/{name}", **_digest(directory/name)}
        frames.append(frame)
        print(f"generated frame {item['frame_id']}", flush=True)
    manifest = {"schema": "member-a-prerecorded-integer-sequence-v1", "sequence_id": inputs["sequence_id"],
                "frame_count": len(frames), "frames": frames, "model": reference.spec["model"],
                "input": {"shape_hwc": [540,960,1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 518400},
                "output": {"shape_hwc": [1080,1920,1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 2073600},
                "source": inputs.get("source", {}), "preprocessing": inputs["preprocessing"],
                "generation": {"source_commit": revision, "worktree_dirty": dirty, "started_utc": started,
                               "elapsed_seconds": time.perf_counter()-timer,
                               "environment": {"python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__},
                               "generator_sha256_lf": _digest(Path(__file__), normalize_text=True)["sha256"]},
                "model_provenance": {"frozen_a_source_commit": "98c82f394bdfba85bc2959bede9760edc4d6862f",
                                     "checkpoint_sha256": FROZEN_CHECKPOINT_SHA, "quant_assets": quant_provenance(ROOT/"artifacts/quant"),
                                     "quant_assets_repository_path": "artifacts/quant", "reference": "src/member_a/fixed_reference.py",
                                     "reference_sha256_lf": _digest(ROOT/"src/member_a/fixed_reference.py", normalize_text=True)["sha256"]},
                "boundary": "Software integer Golden only; no hardware capture or quality/FPS claim."}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(4)
    try:
        result = generate(args.inputs, args.output_dir)
        print(json.dumps({"status": "PASS", "frames": result["frame_count"]}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)})); sys.exit(1)
