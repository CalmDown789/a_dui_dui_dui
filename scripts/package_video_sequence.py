"""Build two-frame and eight-frame portable packages with fixed ZIP metadata."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = ROOT / "artifacts/multiframe"


def package(name, manifest_name):
    manifest = json.loads((SEQUENCE / manifest_name).read_text(encoding="utf-8"))
    entries = {
        "artifacts/multiframe/manifest.json": (SEQUENCE / manifest_name).read_bytes(),
        "artifacts/multiframe/ATTRIBUTION.md": (SEQUENCE / "ATTRIBUTION.md").read_bytes(),
        "scripts/compare_board_sequence.py": (ROOT / "scripts/compare_board_sequence.py").read_bytes(),
        "scripts/input_bin_to_mem.py": (ROOT / "scripts/input_bin_to_mem.py").read_bytes(),
        "docs/成员A多帧交接_2026-10-03.md": (ROOT / "docs/成员A多帧交接_2026-10-03.md").read_bytes(),
    }
    # Portable packages are capture-comparison kits, not standalone training or
    # inference environments. The manifest pins all frozen quantization assets.
    for frame in manifest["frames"]:
        for key in ("input", "golden"):
            relative = frame[key]["path"]
            entries[f"artifacts/multiframe/{relative}"] = (SEQUENCE / relative).read_bytes()
    if manifest["frame_count"] == 8:
        for filename in ("input_contact_sheet.png", "software_golden_preview.gif", "verification.json", "two_frame_manifest.json"):
            entries[f"artifacts/multiframe/{filename}"] = (SEQUENCE / filename).read_bytes()
    else:
        entries["artifacts/multiframe/two_frame_manifest.json"] = (SEQUENCE / manifest_name).read_bytes()
    target = ROOT / "artifacts" / name
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for relative, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 3, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zipped.writestr(info, raw)
    with zipfile.ZipFile(target) as zipped:
        if zipped.testzip() is not None:
            raise AssertionError("Package CRC verification failed")
    return {"path": target.name, "frame_ids": [frame["frame_id"] for frame in manifest["frames"]],
            "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == "__main__":
    results = [package("member_a_two_frame_check.zip", "two_frame_manifest.json"),
               package("member_a_video_8frames.zip", "manifest.json")]
    text = json.dumps({"schema": "member-a-video-packages-v1", "packages": results}, indent=2) + "\n"
    (ROOT / "artifacts/video_packages.json").write_text(text, encoding="utf-8", newline="\n")
    print(text)
