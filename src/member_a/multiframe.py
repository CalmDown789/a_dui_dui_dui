"""Prerecorded frame delivery using the unchanged frozen integer reference."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw
from .artifacts import _array_metadata, _digest
from .fixed_reference import FixedReference

FROZEN_QUANT_SHA = "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a"
FROZEN_CHECKPOINT_SHA = "bb2ee7a2766185bb24e6fc16119db0ad7a69c8f1c4293a1ed0ceae0a142997c5"


def quant_provenance(quant_dir):
    spec = json.loads((quant_dir / "quant_params.json").read_text(encoding="utf-8"))
    paths = {"quant_params.json"}
    for layer in spec["layers"]:
        paths.update(value for key, value in layer["files"].items() if key.endswith("_bin"))
    return {name: _digest(quant_dir / name) for name in sorted(paths)}


def generate_sequence(root, input_stream, source_path, output_dir):
    source = json.loads(source_path.read_text(encoding="utf-8"))
    payload = input_stream.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source["extracted_raw_sha256"]:
        raise ValueError("Prepared video sequence hash mismatch")
    count = source["frame_count"]
    if count != 8 or len(payload) != count * 960 * 540:
        raise ValueError("Expected exactly eight 960x540 input frames")
    quant_dir = root / "artifacts/quant"
    quant_hash = _digest(quant_dir / "quant_params.json", normalize_text=True)["sha256"]
    checkpoint = root / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
    if quant_hash != FROZEN_QUANT_SHA or _digest(checkpoint)["sha256"] != FROZEN_CHECKPOINT_SHA:
        raise ValueError("Frozen model/quantization contract changed")
    reference = FixedReference(quant_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    thumbnails = []
    previews = []
    for index in range(count):
        input_bytes = payload[index * 960 * 540:(index + 1) * 960 * 540]
        image = np.frombuffer(input_bytes, dtype=np.uint8).reshape(540, 960)
        input_path = output_dir / f"frame_{index:03d}_input_y_u8.bin"
        output_path = output_dir / f"frame_{index:03d}_output_y_u8.bin"
        input_path.write_bytes(input_bytes)
        stages = {}
        output = None
        for name, values in reference.iter_outputs(image):
            stages[name] = _array_metadata(values)
            if name == "output":
                output = values[:, :, 0].copy()
        if output is None or output.shape != (1080, 1920) or output.dtype != np.uint8:
            raise AssertionError("Invalid integer reference output")
        output.tofile(output_path)
        frames.append({
            "frame_id": index, "sequence_index": index,
            "source_frame_index": source["source_frame_indices"][index],
            "source_timestamp_seconds": source["source_timestamps_seconds"][index],
            "input": {"path": input_path.name, **_digest(input_path)},
            "golden": {"path": output_path.name, **_digest(output_path)},
            "stage_digests": stages,
        })
        thumbnail = Image.fromarray(image).resize((320, 180))
        thumbnails.append(thumbnail)
        previews.append(Image.fromarray(output).resize((480, 270)))
        print(f"frame {index}: {frames[-1]['golden']['sha256']}", flush=True)
    if len({frame["input"]["sha256"] for frame in frames}) != count:
        raise ValueError("Duplicate input video frames")
    if len({frame["golden"]["sha256"] for frame in frames}) != count:
        raise ValueError("Duplicate integer output video frames")
    contact = Image.new("L", (4 * 320, 2 * 204), 255)
    draw = ImageDraw.Draw(contact)
    for index, thumbnail in enumerate(thumbnails):
        x, y = index % 4 * 320, index // 4 * 204
        contact.paste(thumbnail, (x, y + 24))
        draw.text((x + 6, y + 4), f"frame {index:03d} / t={60 + .5 * index:.1f}s", fill=0)
    contact.save(output_dir / "input_contact_sheet.png")
    previews[0].save(output_dir / "software_golden_preview.gif", save_all=True,
                     append_images=previews[1:], duration=500, loop=0, optimize=False)
    manifest = {
        "schema": "member-a-prerecorded-integer-sequence-v1",
        "status": "A_CONFIRMED_INTEGER_GOLDEN", "frame_count": count,
        "input": {"shape_hwc": [540, 960, 1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 518400},
        "output": {"shape_hwc": [1080, 1920, 1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 2073600},
        "model": reference.spec["model"],
        "model_provenance": {
            "frozen_a_source_commit": "98c82f394bdfba85bc2959bede9760edc4d6862f",
            "frozen_a_tag": "member-a-v1.0.1", "checkpoint_sha256": FROZEN_CHECKPOINT_SHA,
            "quant_assets": quant_provenance(quant_dir),
            "reference": "src/member_a/fixed_reference.py",
            "reference_sha256_lf": _digest(root / "src/member_a/fixed_reference.py", normalize_text=True)["sha256"],
        },
        "source": source, "two_frame_probe_ids": [0, 7],
        "frames": frames,
        "boundary": "Independent network frames in listed order. No FPGA interface, clock, bitstream, board-pass or sustained-FPS claim.",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    probe = {**manifest, "frame_count": 2, "frames": [frames[0], frames[7]],
             "purpose": "Initial two-image check using distinct source timestamps, then proceed to all eight frames."}
    (output_dir / "two_frame_manifest.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify_sequence(root, manifest_path, *, recompute=False):
    # Import the stdlib capture validator without requiring package installation.
    import importlib.util
    module_spec = importlib.util.spec_from_file_location("board_compare", root / "scripts/compare_board_sequence.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    manifest = module.load_manifest(manifest_path)
    provenance = manifest["model_provenance"]
    if provenance["checkpoint_sha256"] != _digest(root / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth")["sha256"]:
        raise ValueError("Checkpoint provenance mismatch")
    if provenance["quant_assets"] != quant_provenance(root / "artifacts/quant"):
        raise ValueError("Quantization provenance mismatch")
    if provenance["reference_sha256_lf"] != _digest(root / provenance["reference"], normalize_text=True)["sha256"]:
        raise ValueError("Integer reference provenance mismatch")
    reference = FixedReference(root / "artifacts/quant") if recompute else None
    if len({frame["input"]["sha256"] for frame in manifest["frames"]}) != len(manifest["frames"]):
        raise ValueError("Duplicate sequence inputs")
    if len({frame["golden"]["sha256"] for frame in manifest["frames"]}) != len(manifest["frames"]):
        raise ValueError("Duplicate sequence outputs")
    input_digest = hashlib.sha256()
    for frame in manifest["frames"]:
        input_digest.update((manifest_path.parent / frame["input"]["path"]).read_bytes())
    is_complete_source = [frame["frame_id"] for frame in manifest["frames"]] == list(range(8))
    if is_complete_source and input_digest.hexdigest() != manifest["source"]["extracted_raw_sha256"]:
        raise ValueError("Extracted input-stream provenance mismatch")
    checked = []
    for frame in manifest["frames"]:
        if reference is not None:
            image = np.fromfile(manifest_path.parent / frame["input"]["path"], dtype=np.uint8).reshape(540, 960)
            for name, values in reference.iter_outputs(image):
                if _array_metadata(values) != frame["stage_digests"][name]:
                    raise AssertionError(f"Integer recomputation mismatch frame={frame['frame_id']} stage={name}")
                if name == "output" and values.tobytes() != (manifest_path.parent / frame["golden"]["path"]).read_bytes():
                    raise AssertionError("Output bytes differ")
        checked.append({"frame_id": frame["frame_id"], "input_sha256": frame["input"]["sha256"],
                        "golden_sha256": frame["golden"]["sha256"]})
        print(f"verified frame {frame['frame_id']} recompute={recompute}", flush=True)
    return {"status": "PASS", "recomputed_all_integer_stages": recompute,
            "frame_count": len(checked), "frames": checked, "board_capture_tested": False,
            "selected_input_stream_sha256": input_digest.hexdigest(),
            "source_stream_hash_verified": is_complete_source,
            "frozen_quant_assets_verified": True, "frozen_checkpoint_verified": True}
