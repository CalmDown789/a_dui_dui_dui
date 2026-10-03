from pathlib import Path
import json
import sys
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import received_frames as received
from compare_board_sequence import digest
from export_pc_player import player_payload
from test_multiframe import bundle


@pytest.fixture
def arrivals(bundle):
    path, capture = bundle
    expected = json.loads(path.read_text())
    expected.update(sequence_id="test_clip", model="FSRCNN")
    path.write_text(json.dumps(expected))
    records = []
    for order, frame in enumerate(expected["frames"]):
        name = frame["golden"]["path"]
        records.append({"frame_id":frame["frame_id"], "order":order, "path":name,
                        **digest((capture/name).read_bytes()), "receive_status":"complete",
                        "crc_result":"NOT_CHECKED", "protocol_frame_id_observed":False,
                        "first_byte_utc":f"2026-10-03T00:00:0{order*2}+00:00",
                        "last_byte_utc":f"2026-10-03T00:00:0{order*2+1}+00:00"})
    data = {"schema":"member-a-received-frames-v1", "sequence_id":"test_clip",
            "frame_count":3, "evidence_source":"software_fixture", "frames":records}
    target = capture / "received_manifest.json"
    target.write_text(json.dumps(data))
    return path, target, data


def test_received_exact_and_timing(arrivals):
    path, target, data = arrivals
    result = received.compare_received(path,target)
    assert result["status"] == "PASS" and result["receive_first_to_last_seconds"] == 5
    assert result["first_byte_intervals_seconds"] == [2,2]
    assert not result["all_protocol_frame_ids_observed"]
    assert result["evidence_source"] == "software_fixture"


@pytest.mark.parametrize("fault",["missing", "repeat", "reorder", "unknown", "bad_order", "crc", "incomplete", "hash", "length", "wrong_sequence", "negative_time"])
def test_received_record_errors(arrivals, fault):
    path, target, data = arrivals
    if fault == "missing": data["frames"].pop(1)
    elif fault == "repeat": data["frames"][1] = dict(data["frames"][0],order=1)
    elif fault == "reorder": data["frames"][0],data["frames"][1] = data["frames"][1],data["frames"][0]
    elif fault == "unknown": data["frames"][1]["frame_id"] = 99
    elif fault == "bad_order": data["frames"][1]["order"] = 0
    elif fault == "crc": data["frames"][1]["crc_result"] = "FAIL"
    elif fault == "incomplete": data["frames"][1]["receive_status"] = "timeout"
    elif fault == "hash": data["frames"][1]["sha256"] = "0"*64
    elif fault == "length": data["frames"][1]["bytes"] = 15
    elif fault == "wrong_sequence": data["sequence_id"] = "other"
    else: data["frames"][1]["last_byte_utc"] = "2026-10-03T00:00:01Z"
    data["frame_count"] = len(data["frames"])
    target.write_text(json.dumps(data))
    assert received.compare_received(path,target)["status"] == "FAIL"


@pytest.mark.parametrize("fault",["byte","short","long","missing_file"])
def test_received_data_errors(arrivals,fault):
    path,target,data = arrivals
    file = target.parent/data["frames"][1]["path"]
    raw = file.read_bytes()
    if fault == "byte": file.write_bytes(raw[:5]+bytes([raw[5]^1])+raw[6:])
    elif fault == "short": file.write_bytes(raw[:-1])
    elif fault == "long": file.write_bytes(raw+b"\0")
    else: file.unlink()
    report = received.compare_received(path,target)
    assert report["status"] == "FAIL"
    if fault == "byte":
        assert report["frames"][1]["byte_mismatch"] == 1
        assert report["frames"][1]["first_error"] == {"byte_offset":5,"row":1,"column":1,"expected_u8":31,"received_u8":30}


@pytest.mark.parametrize("fault",["path", "timezone", "count", "bool_id", "bad_status"])
def test_invalid_received_schema(arrivals,fault):
    path,target,data = arrivals
    if fault == "path": data["frames"][0]["path"] = "../outside.bin"
    elif fault == "timezone": data["frames"][0]["first_byte_utc"] = "2026-10-03T00:00:00"
    elif fault == "count": data["frame_count"] = 4
    elif fault == "bool_id": data["frames"][0]["frame_id"] = True
    else: data["frames"][0]["receive_status"] = "unknown"
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError): received.compare_received(path,target)


def test_player_preserves_received_order_no_missing_golden_fallback(arrivals):
    path,target,data = arrivals
    data["frames"] = [dict(data["frames"][2],order=0),dict(data["frames"][0],order=1)]
    data["frame_count"] = 2; target.write_text(json.dumps(data))
    payload = player_payload(path,received_manifest=target)
    assert [frame["frame_id"] for frame in payload["frames"]] == [2,0]
    assert payload["capture_report"]["missing_frame_ids"] == [1]
    assert payload["capture_report"]["status"] == "FAIL"
    assert all(frame["capture_source"] for frame in payload["frames"])


def test_received_cli_exit_codes(arrivals):
    path,target,data = arrivals
    command = [sys.executable,str(ROOT/"scripts/compare_received_frames.py"),"--manifest",str(path),
               "--received-manifest",str(target),"--report",str(target.parent/"report.json")]
    assert subprocess.run(command,capture_output=True).returncode == 0
    data["frames"].pop();data["frame_count"] = 2;target.write_text(json.dumps(data))
    assert subprocess.run(command,capture_output=True).returncode == 1


def test_existing_sequence_generation_refuses_overwrite(tmp_path):
    from member_a.multiframe import generate_sequence
    with pytest.raises(ValueError,match="overwrite"):
        generate_sequence(ROOT,tmp_path/"absent.bin",tmp_path/"absent.json",tmp_path)


def test_quant_asset_tampering_is_rejected(tmp_path):
    import shutil
    from member_a.multiframe import verify_frozen_assets
    (tmp_path/"artifacts").mkdir()
    shutil.copytree(ROOT/"artifacts/quant",tmp_path/"artifacts/quant")
    shutil.copyfile(ROOT/"artifacts/frozen_quant_assets.json",tmp_path/"artifacts/frozen_quant_assets.json")
    file = tmp_path/"artifacts/quant/feature_weight_oihw_int8.bin"
    raw = file.read_bytes();file.write_bytes(bytes([raw[0]^1])+raw[1:])
    with pytest.raises(ValueError,match="asset hash mismatch"): verify_frozen_assets(tmp_path)
