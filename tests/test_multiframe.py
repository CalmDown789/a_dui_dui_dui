from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("compare", ROOT / "scripts/compare_board_sequence.py")
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


@pytest.fixture
def bundle(tmp_path):
    frames = []
    for index in range(3):
        inp = bytes([index + 10] * 4)
        out = bytes([index + 30] * 16)
        inp_path, out_path = f"frame_{index:03d}_input_y_u8.bin", f"frame_{index:03d}_output_y_u8.bin"
        (tmp_path / inp_path).write_bytes(inp)
        (tmp_path / out_path).write_bytes(out)
        frames.append({"frame_id": index, "input": {"path": inp_path, **compare.digest(inp)},
                       "golden": {"path": out_path, **compare.digest(out)}})
    manifest = {"schema": "member-a-prerecorded-integer-sequence-v1", "frame_count": 3,
                "input": {"shape_hwc": [2, 2, 1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 4},
                "output": {"shape_hwc": [4, 4, 1], "dtype": "uint8", "layout": "HWC_row_major", "bytes_per_frame": 16},
                "frames": frames}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    capture = tmp_path / "capture"
    capture.mkdir()
    for frame in frames:
        name = frame["golden"]["path"]
        (capture / name).write_bytes((tmp_path / name).read_bytes())
    return path, capture


def test_exact_directory(bundle):
    path, capture = bundle
    report = compare.compare_capture(path, capture_dir=capture)
    assert report["status"] == "PASS"
    assert all(frame["byte_mismatch"] == 0 and frame["first_error"] is None for frame in report["frames"])


def test_c_natural_video_manifest_and_capture(tmp_path):
    frames = []
    capture = tmp_path / "capture"
    capture.mkdir()
    (tmp_path / "input").mkdir()
    (tmp_path / "golden").mkdir()
    for frame_id in range(2):
        input_bytes = bytes([10 + frame_id] * 4)
        golden_bytes = bytes([30 + frame_id] * 16)
        input_name = f"input/frame_{frame_id:04d}_y.bin"
        golden_name = f"golden/frame_{frame_id:04d}_y.bin"
        (tmp_path / input_name).write_bytes(input_bytes)
        (tmp_path / golden_name).write_bytes(golden_bytes)
        (capture / f"frame_{frame_id:04d}_y.bin").write_bytes(golden_bytes)
        frames.append({
            "frame_id": frame_id,
            "input": input_name,
            "input_bytes": len(input_bytes),
            "input_sha256": compare.digest(input_bytes)["sha256"],
            "golden": golden_name,
            "golden_bytes": len(golden_bytes),
            "golden_sha256": compare.digest(golden_bytes)["sha256"],
        })
    manifest = {
        "schema": 1,
        "kind": "NATURAL_VIDEO_KIT_NOT_BOARD_TESTED",
        "frame_count": 2,
        "input_geometry": [2, 2],
        "output_geometry": [4, 4],
        "frames": frames,
    }
    path = tmp_path / "SEQUENCE_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    report = compare.compare_capture(path, capture_dir=capture)
    assert report["status"] == "PASS"
    assert [frame["frame_id"] for frame in report["frames"]] == [0, 1]
    assert report["capture_mode"] == "named_frame_files"
    assert report["source_manifest"] == {"schema": 1, "kind": "NATURAL_VIDEO_KIT_NOT_BOARD_TESTED"}
    command = [sys.executable, str(ROOT / "scripts/compare_board_sequence.py"), "--manifest", str(path), "--capture-dir", str(capture)]
    cli = subprocess.run(command, capture_output=True, text=True)
    assert cli.returncode == 0 and json.loads(cli.stdout)["status"] == "PASS"

    changed = bytearray((capture / "frame_0001_y.bin").read_bytes())
    changed[7] ^= 1
    (capture / "frame_0001_y.bin").write_bytes(changed)
    failed = compare.compare_capture(path, capture_dir=capture)
    assert failed["status"] == "FAIL"
    assert failed["frames"][1]["byte_mismatch"] == 1
    assert failed["frames"][1]["first_error"]["byte_offset"] == 7


@pytest.mark.parametrize("mutation", ["byte", "short", "long", "missing", "wrong_order", "repeat", "extra_file"])
def test_capture_errors(bundle, mutation):
    path, capture = bundle
    first, second = capture / "frame_000_output_y_u8.bin", capture / "frame_001_output_y_u8.bin"
    data = first.read_bytes()
    if mutation == "byte":
        first.write_bytes(data[:5] + bytes([data[5] ^ 1]) + data[6:])
    elif mutation == "short":
        first.write_bytes(data[:-1])
    elif mutation == "long":
        first.write_bytes(data + b"\0")
    elif mutation == "missing":
        first.unlink()
    elif mutation == "wrong_order":
        first.write_bytes(second.read_bytes())
        second.write_bytes(data)
    elif mutation == "repeat":
        second.write_bytes(data)
    else:
        (capture / "unexpected.bin").write_bytes(data)
    report = compare.compare_capture(path, capture_dir=capture)
    assert report["status"] == "FAIL"
    if mutation == "byte":
        assert report["frames"][0]["byte_mismatch"] == 1
        assert report["frames"][0]["first_error"]["byte_offset"] == 5
        assert report["frames"][0]["first_error"]["row"] == 1
        assert report["frames"][0]["first_error"]["column"] == 1
    if mutation == "wrong_order":
        assert report["frames"][0]["matches_other_expected_frame_ids"] == [1]


@pytest.mark.parametrize("extra", [-1, 0, 1, 16])
def test_stream_boundaries(bundle, extra):
    path, capture = bundle
    payload = b"".join((capture / f"frame_{i:03d}_output_y_u8.bin").read_bytes() for i in range(3))
    payload = payload[:extra] if extra < 0 else payload + b"\0" * extra
    stream = capture.parent / "capture.bin"
    stream.write_bytes(payload)
    report = compare.compare_capture(path, stream=stream)
    assert report["status"] == ("PASS" if extra == 0 else "FAIL")


def test_single_frame_and_invalid_id(bundle):
    path, capture = bundle
    assert compare.compare_capture(path, capture_file=capture / "frame_001_output_y_u8.bin", frame_id=1)["status"] == "PASS"
    with pytest.raises(ValueError):
        compare.compare_capture(path, capture_file=capture / "frame_001_output_y_u8.bin", frame_id=9)


@pytest.mark.parametrize("mutation", ["hash", "duplicate_id", "frame_count", "shape", "escape"])
def test_invalid_package(bundle, mutation):
    path, capture = bundle
    manifest = json.loads(path.read_text())
    if mutation == "hash":
        manifest["frames"][0]["golden"]["sha256"] = "0" * 64
    elif mutation == "duplicate_id":
        manifest["frames"][1]["frame_id"] = 0
    elif mutation == "frame_count":
        manifest["frame_count"] = 5
    elif mutation == "shape":
        manifest["output"]["bytes_per_frame"] = 17
    else:
        manifest["frames"][0]["golden"]["path"] = "../outside.bin"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        compare.load_manifest(path)


def test_cli_exit_codes(bundle):
    path, capture = bundle
    command = [sys.executable, str(ROOT / "scripts/compare_board_sequence.py"), "--manifest", str(path), "--capture-dir", str(capture)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "PASS"
    (capture / "frame_000_output_y_u8.bin").write_bytes(b"")
    assert subprocess.run(command, capture_output=True).returncode == 1


def test_delivered_eight_frame_contract():
    path = ROOT / "artifacts/multiframe/manifest.json"
    manifest = compare.load_manifest(path)
    assert manifest["frame_count"] == 8
    assert [frame["frame_id"] for frame in manifest["frames"]] == list(range(8))
    assert manifest["input"]["bytes_per_frame"] == 518400
    assert manifest["output"]["bytes_per_frame"] == 2073600
    assert len({frame["input"]["sha256"] for frame in manifest["frames"]}) == 8
    assert len({frame["golden"]["sha256"] for frame in manifest["frames"]}) == 8
    probe = compare.load_manifest(path.with_name("two_frame_manifest.json"))
    assert [frame["frame_id"] for frame in probe["frames"]] == [0, 7]
    assert probe["model_provenance"] == manifest["model_provenance"]


@pytest.mark.parametrize("name", ["member_a_two_frame_check.zip", "member_a_video_8frames.zip", "member_a_authority_plus_second_frame.zip"])
def test_portable_package_integrity(name):
    index = json.loads((ROOT / "artifacts/video_packages.json").read_text())
    metadata = next(package for package in index["packages"] if package["path"] == name)
    archive = ROOT / "artifacts" / name
    assert compare.digest(archive.read_bytes())["sha256"] == metadata["sha256"]
    assert archive.stat().st_size == metadata["bytes"]
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        manifest = json.loads(zipped.read("artifacts/multiframe/manifest.json"))
        assert [frame["frame_id"] for frame in manifest["frames"]] == metadata["frame_ids"]
        for frame in manifest["frames"]:
            for key in ("input", "golden"):
                expected = frame[key]
                actual = compare.digest(zipped.read("artifacts/multiframe/" + expected["path"]))
                assert all(actual[field] == expected[field] for field in actual)


def test_verification_evidence_does_not_claim_board_pass():
    verification = json.loads((ROOT / "artifacts/multiframe/verification.json").read_text())
    tool = json.loads((ROOT / "artifacts/video_tool_selftest.json").read_text())
    assert verification["status"] == "PASS" and verification["recomputed_all_integer_stages"]
    assert verification["source_stream_hash_verified"]
    assert not verification["board_capture_tested"] and not tool["board_capture_tested"]
    assert tool["status"] == "PASS" and all(value == "PASS" for value in tool["checks"].values())
