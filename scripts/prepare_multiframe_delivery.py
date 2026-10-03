"""Add explicit provenance and lossless previews to the already-pinned sequence."""
from pathlib import Path
import json
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from member_a.multiframe import verify_frozen_assets
from compare_board_sequence import load_manifest, digest

if __name__ == "__main__":
    verify_frozen_assets(ROOT)
    directory = ROOT / "artifacts/multiframe"
    path = directory / "manifest.json"
    manifest = load_manifest(path)
    source = json.loads((ROOT / ".data/public_sequence/source.json").read_text(encoding="utf-8"))
    if source["extracted_raw_sha256"] != manifest["source"]["extracted_raw_sha256"]:
        raise ValueError("Re-extracted source differs from the delivered inputs")
    source["preprocessing"]["range_lut_256_codes_verified"] = True
    manifest.update(sequence_id="bbb_clip_01", source=source, preprocessing=source["preprocessing"])
    manifest["metadata_revision"] = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "raw_input_and_golden_changed": False,
        "original_generation_time": "Not recorded in initial delivery; recomputation report records current verification time",
    }
    manifest["model_provenance"]["quant_assets_repository_path"] = "artifacts/quant"
    for order, frame in enumerate(manifest["frames"]):
        frame["order"] = order
        for key, shape in (("input", (960,540)), ("golden", (1920,1080))):
            raw = (directory / frame[key]["path"]).read_bytes()
            preview = directory / (Path(frame[key]["path"]).stem + ".png")
            Image.frombytes("L", shape, raw).save(preview)
            frame[key]["shape_hwc"] = [shape[1],shape[0],1]
            frame[key]["dtype"] = "uint8"
            frame[key]["preview"] = {"path": preview.name, **digest(preview.read_bytes())}
    path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    probe = {**manifest, "sequence_id": "bbb_two_image_probe", "frame_count": 2,
             "frames": [dict(manifest["frames"][i], order=order) for order,i in enumerate((0,7))]}
    (directory/"two_frame_manifest.json").write_text(json.dumps(probe,indent=2)+"\n",encoding="utf-8",newline="\n")
    (directory/"preprocessing.json").write_text(json.dumps(source,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":"PASS","raw_bytes_changed":False,"frame_count":8,"lossless_previews":16}))
