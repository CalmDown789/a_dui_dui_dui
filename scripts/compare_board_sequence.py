"""Compare headerless uint8 Y captures against an A sequence manifest (stdlib only)."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "crc32": f"{zlib.crc32(data) & 0xffffffff:08x}"}


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Manifest path escapes package: {relative}")
    return path


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    if manifest["schema"] != "member-a-prerecorded-integer-sequence-v1":
        raise ValueError("Unsupported manifest schema")
    if not frames or len(frames) != manifest["frame_count"]:
        raise ValueError("Invalid frame_count")
    ids = [frame["frame_id"] for frame in frames]
    if any("order" in frame for frame in frames) and [frame.get("order") for frame in frames] != list(range(len(frames))):
        raise ValueError("Manifest order must match the listed frame order")
    if any(type(value) is not int or value < 0 for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("frame_id must be unique nonnegative integers")
    for name in ("input", "output"):
        spec = manifest[name]
        h, w, c = spec["shape_hwc"]
        if spec["dtype"] != "uint8" or spec["layout"] != "HWC_row_major" or c != 1 or h <= 0 or w <= 0:
            raise ValueError(f"Invalid {name} layout")
        if spec["bytes_per_frame"] != h * w:
            raise ValueError(f"Invalid {name} bytes_per_frame")
    for frame in frames:
        for name in ("input", "golden"):
            metadata = frame[name]
            data = safe_path(path.parent, metadata["path"]).read_bytes()
            actual = digest(data)
            if any(actual[key] != metadata[key] for key in actual):
                raise ValueError(f"Package integrity mismatch: {metadata['path']}")
            spec = manifest["input" if name == "input" else "output"]
            if len(data) != spec["bytes_per_frame"]:
                raise ValueError(f"Invalid frame length: {metadata['path']}")
            if "preview" in metadata:
                preview = metadata["preview"]
                actual = digest(safe_path(path.parent,preview["path"]).read_bytes())
                if any(actual[key] != preview[key] for key in actual):
                    raise ValueError("Lossless preview integrity mismatch")
    names = [safe_path(path.parent,frame["golden"]["path"]) for frame in frames]
    if len(set(names)) != len(names):
        raise ValueError("Golden file paths must be unique")
    return manifest


def compare_bytes(expected, received, width):
    equal_length = len(expected) == len(received)
    differing = [i for i, (a, b) in enumerate(zip(expected, received)) if a != b] if equal_length else None
    first = differing[0] if differing else min(len(expected),len(received)) if not equal_length else None
    return {
        "status": "PASS" if expected == received else "FAIL",
        "expected": digest(expected), "received": digest(received),
        "length_status": "PASS" if equal_length else "FAIL",
        "content_comparison": "DONE" if equal_length else "NOT_RUN_LENGTH_ERROR",
        "byte_mismatch": len(differing) if differing is not None else None, "missing_bytes": max(0, len(expected) - len(received)),
        "extra_bytes": max(0, len(received) - len(expected)),
        "first_error": None if first is None else {
            "byte_offset": first, "row": first // width if first < len(expected) else None,
            "column": first % width if first < len(expected) else None,
            "expected_u8": expected[first] if first < len(expected) else None,
            "received_u8": received[first] if first < len(received) else None,
        },
    }


def compare_capture(manifest_path, *, capture_dir=None, stream=None, capture_file=None, frame_id=None):
    manifest = load_manifest(manifest_path)
    frames = manifest["frames"]
    if capture_file is not None:
        frames = [frame for frame in frames if frame["frame_id"] == frame_id]
        if len(frames) != 1:
            raise ValueError("--capture-file requires a frame ID in the manifest")
    width = manifest["output"]["shape_hwc"][1]
    frame_bytes = manifest["output"]["bytes_per_frame"]
    payload = stream.read_bytes() if stream is not None else None
    results = []
    for index, frame in enumerate(frames):
        expected = safe_path(manifest_path.parent, frame["golden"]["path"]).read_bytes()
        missing_file = False
        if payload is not None:
            received = payload[index * frame_bytes:(index + 1) * frame_bytes]
        elif capture_file is not None:
            received = capture_file.read_bytes()
        else:
            path = safe_path(capture_dir,frame["golden"]["path"])
            missing_file = not path.is_file()
            received = b"" if missing_file else path.read_bytes()
        result = {"frame_id": frame["frame_id"], "missing_file": missing_file,
                  **compare_bytes(expected, received, width)}
        # Helpful diagnostic, not a claim to have observed on-wire frame IDs.
        result["matches_other_expected_frame_ids"] = [
            other["frame_id"] for other in manifest["frames"]
            if other["frame_id"] != frame["frame_id"] and other["golden"]["sha256"] == result["received"]["sha256"]
        ]
        results.append(result)
    expected_names = {safe_path(capture_dir,frame["golden"]["path"]) for frame in frames} if capture_dir else set()
    unexpected_files = sorted(path.relative_to(capture_dir).as_posix() for path in capture_dir.rglob("*.bin") if path.resolve() not in expected_names) if capture_dir else []
    extra_stream_bytes = max(0, len(payload) - frame_bytes * len(frames)) if payload is not None else 0
    return {
        "schema": "member-a-board-sequence-comparison-v1",
        "status": "PASS" if all(result["status"] == "PASS" for result in results) and not extra_stream_bytes and not unexpected_files else "FAIL",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "frame_count": len(frames), "frames": results,
        "extra_stream_bytes": extra_stream_bytes, "unexpected_files": unexpected_files,
        "capture_mode": "headerless_stream" if stream else "single_frame" if capture_file else "named_frame_files",
        "scope": "Byte comparison only. Filenames/order are assigned by the host; no on-wire frame ID, CRC, timing or sustained-FPS claim.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/multiframe/manifest.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture-dir", type=Path)
    group.add_argument("--stream", type=Path)
    group.add_argument("--capture-file", type=Path)
    parser.add_argument("--frame-id", type=int)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--preview-dir", type=Path, help="After PASS, save full-size PNGs and a downscaled GIF (requires Pillow)")
    args = parser.parse_args()
    if args.capture_file is not None and args.frame_id is None:
        parser.error("--capture-file requires --frame-id")
    if args.frame_id is not None and args.capture_file is None:
        parser.error("--frame-id is only valid with --capture-file")
    try:
        report = compare_capture(args.manifest, capture_dir=args.capture_dir, stream=args.stream,
                                 capture_file=args.capture_file, frame_id=args.frame_id)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"status": "FAIL", "error": str(error)}
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    if args.preview_dir and report["status"] == "PASS":
        from PIL import Image
        manifest = load_manifest(args.manifest)
        payload = args.stream.read_bytes() if args.stream else None
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        previews = []
        height, width, _ = manifest["output"]["shape_hwc"]
        for index, frame_result in enumerate(report["frames"]):
            frame = next(frame for frame in manifest["frames"] if frame["frame_id"] == frame_result["frame_id"])
            data = payload[index * height * width:(index + 1) * height * width] if payload is not None else (
                args.capture_file.read_bytes() if args.capture_file else safe_path(args.capture_dir,frame["golden"]["path"]).read_bytes())
            image = Image.frombytes("L", (width, height), data)
            image.save(args.preview_dir / f"frame_{frame['frame_id']:03d}_capture.png")
            previews.append(image.resize((480, 270)))
        previews[0].save(args.preview_dir / "capture_preview.gif", save_all=True,
                         append_images=previews[1:], duration=500, loop=0, optimize=False)
    print(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
