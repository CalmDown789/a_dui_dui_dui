from pathlib import Path
import base64
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("pc_player", ROOT / "scripts/export_pc_player.py")
player = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(player)


def embedded_payload(path):
    text = path.read_text(encoding="utf-8")
    start = text.index('<script id="playerData" type="application/json">') + len('<script id="playerData" type="application/json">')
    return json.loads(text[start:text.index("</script>", start)])


def test_reference_player_is_self_contained(tmp_path):
    manifest_path = ROOT / "artifacts/multiframe/two_frame_manifest.json"
    output = tmp_path / "player.html"
    result = player.export_player(manifest_path, output)
    assert result["status"] == "EXPORTED" and result["capture_status"] == "NOT_TESTED"
    payload = embedded_payload(output)
    assert payload["mode"] == "software_reference" and not payload["live_io_enabled"]
    assert [frame["frame_id"] for frame in payload["frames"]] == [0, 7]
    for frame in payload["frames"]:
        assert len(base64.b64decode(frame["input_b64"])) == 518400
        assert len(base64.b64decode(frame["golden_b64"])) == 2073600
    assert "__PLAYER_DATA_JSON__" not in output.read_text(encoding="utf-8")
    assert "connect-src 'none'" in output.read_text(encoding="utf-8")


def test_exact_capture_player(tmp_path):
    manifest_path = ROOT / "artifacts/multiframe/two_frame_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = tmp_path / "capture.bin"
    stream.write_bytes(b"".join((manifest_path.parent / frame["golden"]["path"]).read_bytes() for frame in manifest["frames"]))
    output = tmp_path / "player.html"
    assert player.export_player(manifest_path, output, stream=stream)["capture_status"] == "PASS"
    payload = embedded_payload(output)
    assert payload["capture_report"]["status"] == "PASS"
    assert all(frame["golden_b64"] == frame["capture_b64"] for frame in payload["frames"])


def test_failed_capture_keeps_failure_evidence(tmp_path):
    manifest_path = ROOT / "artifacts/multiframe/two_frame_manifest.json"
    stream = tmp_path / "short.bin"
    stream.write_bytes(b"\0" * 10)
    output = tmp_path / "failure.html"
    assert player.export_player(manifest_path, output, stream=stream)["capture_status"] == "FAIL"
    payload = embedded_payload(output)
    assert payload["capture_report"]["status"] == "FAIL"
    assert payload["capture_report"]["frames"][0]["missing_bytes"] == 2073590
    assert payload["frames"][1]["capture_b64"] == ""


def test_embedded_manifest_cannot_close_script_tag(tmp_path):
    manifest_path = ROOT / "artifacts/multiframe/two_frame_manifest.json"
    altered = json.loads(manifest_path.read_text(encoding="utf-8"))
    altered["model"] = "</script><script>alert(1)</script>"
    # Reference frame paths stay in a valid temporary package.
    for frame in altered["frames"]:
        for key in ("input", "golden"):
            name = frame[key]["path"]
            (tmp_path / name).write_bytes((manifest_path.parent / name).read_bytes())
            if "preview" in frame[key]:
                preview = frame[key]["preview"]["path"]
                (tmp_path / preview).write_bytes((manifest_path.parent / preview).read_bytes())
    temporary_manifest = tmp_path / "manifest.json"
    temporary_manifest.write_text(json.dumps(altered), encoding="utf-8")
    output = tmp_path / "escaped.html"
    player.export_player(temporary_manifest, output)
    text = output.read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in text
    assert embedded_payload(output)["manifest"]["model"] == altered["model"]


def test_controller_evidence_does_not_claim_browser_or_board_validation():
    report = json.loads((ROOT / "artifacts/pc_player_logic_test.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert not report["browser_visual_verified"] and not report["board_capture_tested"]
    assert not report["live_io_enabled"] and report["protocol_state"] == "UNCONFIRMED"
    assert all(value == "PASS" for value in report["checks"].values())
