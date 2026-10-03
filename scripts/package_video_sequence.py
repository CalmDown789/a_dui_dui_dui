"""Build two-frame and eight-frame portable packages with fixed ZIP metadata."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = ROOT / "artifacts/multiframe"


def package(name, manifest_name, sequence=SEQUENCE):
    manifest = json.loads((sequence / manifest_name).read_text(encoding="utf-8"))
    entries = {
        "artifacts/multiframe/manifest.json": (sequence / manifest_name).read_bytes(),
        "artifacts/multiframe/ATTRIBUTION.md": (SEQUENCE / "ATTRIBUTION.md").read_bytes(),
        "scripts/compare_board_sequence.py": (ROOT / "scripts/compare_board_sequence.py").read_bytes(),
        "scripts/input_bin_to_mem.py": (ROOT / "scripts/input_bin_to_mem.py").read_bytes(),
        "scripts/export_pc_player.py": (ROOT / "scripts/export_pc_player.py").read_bytes(),
        "scripts/received_frames.py": (ROOT / "scripts/received_frames.py").read_bytes(),
        "scripts/compare_received_frames.py": (ROOT / "scripts/compare_received_frames.py").read_bytes(),
        "scripts/capture_raw_uart.py": (ROOT / "scripts/capture_raw_uart.py").read_bytes(),
        "src/member_a/pc_player.html": (ROOT / "src/member_a/pc_player.html").read_bytes(),
        "artifacts/pc_player_manual_acceptance.json": (ROOT / "artifacts/pc_player_manual_acceptance.json").read_bytes(),
        "docs/成员A多帧交接_2026-10-03.md": (ROOT / "docs/成员A多帧交接_2026-10-03.md").read_bytes(),
        "docs/成员A_PC收发协议确认清单_2026-10-03.md": (ROOT / "docs/成员A_PC收发协议确认清单_2026-10-03.md").read_bytes(),
        "docs/成员A任务核验_2026-10-03.md": (ROOT / "docs/成员A任务核验_2026-10-03.md").read_bytes(),
        "docs/成员A_UART接收工具_2026-10-03.md": (ROOT / "docs/成员A_UART接收工具_2026-10-03.md").read_bytes(),
    }
    for relative in ("experiments/member_a_uart_prototype_20261003/README.md",
                     "experiments/member_a_uart_prototype_20261003/host/stop_wait_client.py",
                     "artifacts/uart_prototype_selftest.json"):
        entries[relative] = (ROOT / relative).read_bytes()
    # Portable packages are capture-comparison kits, not standalone training or
    # inference environments. The manifest pins all frozen quantization assets.
    for frame in manifest["frames"]:
        for key in ("input", "golden"):
            relative = frame[key]["path"]
            entries[f"artifacts/multiframe/{relative}"] = (sequence / relative).read_bytes()
            if "preview" in frame[key]:
                preview = frame[key]["preview"]["path"]
                entries[f"artifacts/multiframe/{preview}"] = (sequence / preview).read_bytes()
        # Generic two-frame generator saves lossless PNGs beside raw frames.
        if sequence != SEQUENCE:
            for png in (sequence / Path(frame["input"]["path"]).parent).glob("*.png"):
                entries[f"artifacts/multiframe/{png.relative_to(sequence).as_posix()}"] = png.read_bytes()
    if manifest["frame_count"] == 8:
        for filename in ("input_contact_sheet.png", "software_golden_preview.gif", "verification.json", "two_frame_manifest.json", "preprocessing.json", "generation_summary.json"):
            entries[f"artifacts/multiframe/{filename}"] = (SEQUENCE / filename).read_bytes()
        entries["artifacts/pc_player_logic_test.json"] = (ROOT / "artifacts/pc_player_logic_test.json").read_bytes()
    else:
        entries["artifacts/multiframe/two_frame_manifest.json"] = (sequence / manifest_name).read_bytes()
    if (sequence / "verification.json").is_file():
        entries["artifacts/multiframe/verification.json"] = (sequence / "verification.json").read_bytes()
    if (sequence / "single_authority_manifest.json").is_file():
        entries["artifacts/multiframe/single_authority_manifest.json"] = (sequence / "single_authority_manifest.json").read_bytes()
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
               package("member_a_video_8frames.zip", "manifest.json"),
               package("member_a_authority_plus_second_frame.zip", "manifest.json", ROOT / "artifacts/authority_pair")]
    text = json.dumps({"schema": "member-a-video-packages-v1", "packages": results}, indent=2) + "\n"
    (ROOT / "artifacts/video_packages.json").write_text(text, encoding="utf-8", newline="\n")
    print(text)
