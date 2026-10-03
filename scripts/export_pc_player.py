"""Export a self-contained offline Y-frame player, optionally with capture comparison."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import sys

from compare_board_sequence import compare_capture, load_manifest, safe_path

ROOT = Path(__file__).resolve().parents[1]


def player_payload(manifest_path, *, capture_dir=None, stream=None, received_manifest=None):
    manifest = load_manifest(manifest_path)
    if received_manifest:
        from received_frames import compare_received, load_received
        report = compare_received(manifest_path, received_manifest)
        arrivals = load_received(received_manifest)
        lookup = {frame["frame_id"]: frame for frame in manifest["frames"]}
        if not arrivals["frames"] or report["unexpected_frame_ids"]:
            raise ValueError("No playable known received frames; see comparison report")
        frames = []
        aligned = []
        for arrival in arrivals["frames"]:
            frame = lookup[arrival["frame_id"]]
            received_path = safe_path(received_manifest.parent, arrival["path"])
            raw = received_path.read_bytes() if received_path.is_file() else b""
            frames.append({"frame_id": frame["frame_id"], "source_timestamp_seconds": frame.get("source_timestamp_seconds"),
                           "capture_source": arrival["path"], "receive_order": arrival["order"],
                           "input_b64": base64.b64encode(safe_path(manifest_path.parent, frame["input"]["path"]).read_bytes()).decode("ascii"),
                           "golden_b64": base64.b64encode(safe_path(manifest_path.parent, frame["golden"]["path"]).read_bytes()).decode("ascii"),
                           "capture_b64": base64.b64encode(raw).decode("ascii")})
            aligned.append(frame)
        return {"schema": "member-a-offline-pc-player-v1", "manifest": {**manifest, "frames": aligned},
                "manifest_sha256": report["manifest_sha256"], "frames": frames, "mode": "received_manifest",
                "capture_report": report, "protocol_state": "UNCONFIRMED", "live_io_enabled": False}
    report = compare_capture(manifest_path, capture_dir=capture_dir, stream=stream) if capture_dir or stream else None
    raw_stream = stream.read_bytes() if stream else None
    frame_bytes = manifest["output"]["bytes_per_frame"]
    frames = []
    for index, frame in enumerate(manifest["frames"]):
        record = {"frame_id": frame["frame_id"], "source_timestamp_seconds": frame.get("source_timestamp_seconds"),
                  "capture_source": str(stream) if stream else str(capture_dir / frame["golden"]["path"]) if capture_dir else None,
                  "input_b64": base64.b64encode(safe_path(manifest_path.parent, frame["input"]["path"]).read_bytes()).decode("ascii"),
                  "golden_b64": base64.b64encode(safe_path(manifest_path.parent, frame["golden"]["path"]).read_bytes()).decode("ascii")}
        if report:
            if raw_stream is not None:
                received = raw_stream[index * frame_bytes:(index + 1) * frame_bytes]
            else:
                file = safe_path(capture_dir,frame["golden"]["path"])
                received = file.read_bytes() if file.is_file() else b""
            record["capture_b64"] = base64.b64encode(received).decode("ascii")
        frames.append(record)
    return {"schema": "member-a-offline-pc-player-v1", "manifest": manifest, "frames": frames,
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "mode": "capture_comparison" if report else "software_reference", "capture_report": report,
            "protocol_state": "UNCONFIRMED", "live_io_enabled": False,
            "notice": "Offline display only. Software Golden is not hardware output. Display FPS is not FPGA throughput."}


def export_player(manifest_path, output, *, capture_dir=None, stream=None, received_manifest=None):
    payload = player_payload(manifest_path, capture_dir=capture_dir, stream=stream, received_manifest=received_manifest)
    template = (ROOT / "src/member_a/pc_player.html").read_text(encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__PLAYER_DATA_JSON__", encoded), encoding="utf-8", newline="\n")
    return {"status": "EXPORTED", "mode": payload["mode"], "frame_count": len(payload["frames"]),
            "capture_status": payload["capture_report"]["status"] if payload["capture_report"] else "NOT_TESTED",
            "output": str(output.resolve()), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "live_io_enabled": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/multiframe/manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--capture-dir", type=Path)
    group.add_argument("--stream", type=Path)
    group.add_argument("--received-manifest", type=Path)
    args = parser.parse_args()
    try:
        result = export_player(args.manifest, args.output, capture_dir=args.capture_dir, stream=args.stream, received_manifest=args.received_manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # A FAIL capture still gets a diagnostic player, but must not exit as PASS.
    sys.exit(1 if result["capture_status"] == "FAIL" else 0)
