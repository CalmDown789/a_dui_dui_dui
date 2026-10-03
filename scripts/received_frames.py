"""Offline received-manifest validation. No transport or on-wire format is assumed."""
from pathlib import Path
from collections import Counter
from datetime import datetime
import hashlib
import json
from compare_board_sequence import compare_bytes, digest, load_manifest, safe_path


def utc_time(value):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("Receive timestamps must include a timezone")
    return instant


def load_received(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["schema"] != "member-a-received-frames-v1":
        raise ValueError("Unsupported received manifest schema")
    if not isinstance(manifest["sequence_id"], str) or not manifest["sequence_id"]:
        raise ValueError("Missing received sequence ID")
    if manifest["evidence_source"] not in ("software_fixture", "operator_supplied_capture"):
        raise ValueError("Capture provenance must be explicit")
    if manifest["frame_count"] != len(manifest["frames"]):
        raise ValueError("Received frame_count does not match the records")
    for record in manifest["frames"]:
        if type(record["frame_id"]) is not int or record["frame_id"] < 0:
            raise ValueError("Invalid received frame ID")
        if type(record["order"]) is not int or record["order"] < 0:
            raise ValueError("Invalid received order")
        if type(record["bytes"]) is not int or record["bytes"] < 0:
            raise ValueError("Invalid received byte count")
        safe_path(path.parent, record["path"])
        if record["receive_status"] not in ("complete", "incomplete", "timeout", "error"):
            raise ValueError("Invalid receive_status")
        if record["crc_result"] not in ("PASS", "FAIL", "NOT_CHECKED"):
            raise ValueError("Invalid CRC result")
        if type(record["protocol_frame_id_observed"]) is not bool:
            raise ValueError("Frame ID evidence must be explicit")
        utc_time(record["first_byte_utc"])
        utc_time(record["last_byte_utc"])
    return manifest


def compare_received(expected_path, received_path):
    expected = load_manifest(expected_path)
    received = load_received(received_path)
    lookup = {frame["frame_id"]: frame for frame in expected["frames"]}
    ids = [record["frame_id"] for record in received["frames"]]
    orders = [record["order"] for record in received["frames"]]
    expected_ids = list(lookup)
    errors = []
    missing = sorted(set(expected_ids) - set(ids))
    unknown = sorted(set(ids) - set(expected_ids))
    duplicates = sorted(frame_id for frame_id, count in Counter(ids).items() if count > 1)
    if received["sequence_id"] != expected.get("sequence_id"):
        errors.append("sequence_id_mismatch")
    if missing: errors.append("missing_frames")
    if unknown: errors.append("unexpected_frame_ids")
    if duplicates: errors.append("duplicate_frame_ids")
    if ids != expected_ids: errors.append("frame_order_or_count_mismatch")
    if orders != list(range(len(orders))): errors.append("receive_order_mismatch")
    results = []
    starts, ends = [], []
    for record in received["frames"]:
        path = safe_path(received_path.parent, record["path"])
        raw = path.read_bytes() if path.is_file() else b""
        actual = digest(raw)
        faults = []
        if not path.is_file(): faults.append("missing_file")
        if actual["bytes"] != record["bytes"]: faults.append("recorded_length_mismatch")
        if actual["sha256"] != record["sha256"]: faults.append("recorded_hash_mismatch")
        if record["receive_status"] != "complete": faults.append("receive_not_complete")
        if record["crc_result"] == "FAIL": faults.append("transport_crc_failed")
        start, end = utc_time(record["first_byte_utc"]), utc_time(record["last_byte_utc"])
        starts.append(start); ends.append(end)
        if end < start: faults.append("negative_receive_duration")
        frame = lookup.get(record["frame_id"])
        if frame is None:
            faults.append("no_golden_for_frame")
            match = {"status": "NOT_COMPARED", "received": actual, "byte_mismatch": None,
                     "missing_bytes": None, "extra_bytes": None, "first_error": None}
        else:
            golden = safe_path(expected_path.parent, frame["golden"]["path"]).read_bytes()
            match = compare_bytes(golden, raw, expected["output"]["shape_hwc"][1])
        results.append({**match, "status": "FAIL" if faults else match["status"],
                        "frame_id": record["frame_id"], "order": record["order"],
                        "received_path": record["path"], "input_source": frame["input"]["path"] if frame else None,
                        "crc_result": record["crc_result"], "receive_status": record["receive_status"],
                        "protocol_frame_id_observed": record["protocol_frame_id_observed"],
                        "first_byte_utc": record["first_byte_utc"], "last_byte_utc": record["last_byte_utc"],
                        "receive_seconds": (end-start).total_seconds(), "metadata_errors": faults})
    if any(starts[i] < starts[i-1] or starts[i] < ends[i-1] for i in range(1, len(starts))):
        errors.append("nonsequential_or_overlapping_receive_times")
    return {"schema": "member-a-received-comparison-v1", "sequence_id": received["sequence_id"],
            "status": "PASS" if not errors and all(item["status"] == "PASS" for item in results) else "FAIL",
            "manifest_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
            "received_manifest_sha256": hashlib.sha256(received_path.read_bytes()).hexdigest(),
            "evidence_source": received["evidence_source"], "frame_count": len(results), "frames": results,
            "missing_frame_ids": missing, "duplicate_frame_ids": duplicates, "unexpected_frame_ids": unknown,
            "sequence_errors": errors, "extra_stream_bytes": 0,
            "receive_first_to_last_seconds": (ends[-1]-starts[0]).total_seconds() if starts else None,
            "first_byte_intervals_seconds": [(starts[i]-starts[i-1]).total_seconds() for i in range(1,len(starts))],
            "all_protocol_frame_ids_observed": bool(results) and all(r["protocol_frame_id_observed"] for r in results),
            "scope": "All listed Golden frames compared. Receive times are operator logs, not core throughput. "
                     "Software fixtures are not board evidence; protocol IDs/CRC require a confirmed capture implementation."}
