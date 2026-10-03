"""Exercise comparison and standalone packages with software fixtures, not board data."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("compare", ROOT / "scripts/compare_board_sequence.py")
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def main():
    manifest_path = ROOT / "artifacts/multiframe/manifest.json"
    manifest = compare.load_manifest(manifest_path)
    scratch = ROOT / ".data/video_delivery_selftest"
    scratch.mkdir(parents=True, exist_ok=True)
    payload = b"".join((manifest_path.parent / frame["golden"]["path"]).read_bytes() for frame in manifest["frames"])
    stream = scratch / "software_fixture_8frames.bin"
    stream.write_bytes(payload)
    results = {}
    report = compare.compare_capture(manifest_path, stream=stream)
    assert report["status"] == "PASS"
    results["eight_frame_exact"] = "PASS"
    probe_path = manifest_path.with_name("two_frame_manifest.json")
    probe = compare.load_manifest(probe_path)
    two = scratch / "software_fixture_twoframes.bin"
    two.write_bytes(b"".join((manifest_path.parent / frame["golden"]["path"]).read_bytes() for frame in probe["frames"]))
    assert compare.compare_capture(probe_path, stream=two)["status"] == "PASS"
    results["two_frame_exact"] = "PASS"
    for name, mutated in {
        "one_wrong_byte": payload[:123] + bytes([payload[123] ^ 1]) + payload[124:],
        "truncated_stream": payload[:-1], "extra_byte": payload + b"\0",
        "wrong_frame_order": payload[2073600:4147200] + payload[:2073600] + payload[4147200:],
        "repeated_frame": payload[:2073600] * 2 + payload[4147200:],
    }.items():
        damaged = scratch / (name + ".bin")
        damaged.write_bytes(mutated)
        failure = compare.compare_capture(manifest_path, stream=damaged)
        assert failure["status"] == "FAIL"
        if name == "one_wrong_byte":
            assert failure["frames"][0]["byte_mismatch"] == 1
            assert failure["frames"][0]["first_error"]["byte_offset"] == 123
        results[name + "_detected"] = "PASS"
    for package in ("member_a_two_frame_check.zip", "member_a_video_8frames.zip"):
        destination = scratch / package.removesuffix(".zip")
        destination.mkdir(exist_ok=True)
        with zipfile.ZipFile(ROOT / "artifacts" / package) as zipped:
            assert zipped.testzip() is None
            zipped.extractall(destination)
        packaged_manifest = destination / "artifacts/multiframe/manifest.json"
        packaged = compare.load_manifest(packaged_manifest)
        capture = destination / "software_fixture"
        capture.mkdir(exist_ok=True)
        for frame in packaged["frames"]:
            name = frame["golden"]["path"]
            shutil.copyfile(packaged_manifest.parent / name, capture / Path(name).name)
        # -S excludes installed packages: core comparison really is stdlib-only.
        completed = subprocess.run([sys.executable, "-S", str(destination / "scripts/compare_board_sequence.py"),
                                    "--capture-dir", str(capture)], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        assert json.loads(completed.stdout)["status"] == "PASS"
        results[package + "_standalone"] = "PASS"
    # Test ROM conversion prefix and padding without publishing duplicate .mem.
    mem = scratch / "frame000.mem"
    subprocess.run([sys.executable, str(ROOT / "scripts/input_bin_to_mem.py"),
                    str(manifest_path.parent / manifest["frames"][0]["input"]["path"]), str(mem)], check=True)
    decoded = bytes.fromhex(mem.read_text(encoding="ascii"))
    assert len(decoded) == 524288
    assert decoded[:518400] == (manifest_path.parent / manifest["frames"][0]["input"]["path"]).read_bytes()
    assert decoded[518400:] == bytes(5888)
    results["rom_prefix_and_zero_padding"] = "PASS"
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/compare_board_sequence.py"),
                                "--stream", str(stream), "--preview-dir", str(scratch / "software_preview")],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert len(list((scratch / "software_preview").glob("*.png"))) == 8
    results["preview_export"] = "PASS"
    result = {"schema": "member-a-video-delivery-selftest-v1", "status": "PASS",
              "fixture_source": "Software Golden bytes and deliberate mutations; no hardware capture supplied",
              "board_capture_tested": False, "checks": results}
    (ROOT / "artifacts/video_tool_selftest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
