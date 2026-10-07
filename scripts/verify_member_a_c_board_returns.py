"""Independently compare archived C board captures against A's integer reference.

Board archives and generated reports belong below ignored .data/. Nothing from
the C branch is copied into this repository's tracked A artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contained_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Board manifest path escapes its data root: {relative}") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def a_integer_output(reference: FixedReference, input_bytes: bytes) -> bytes:
    image = np.frombuffer(input_bytes, dtype=np.uint8).reshape(540, 960)
    result: np.ndarray | None = None
    for name, values in reference.iter_outputs(image):
        if name == "output":
            result = values[:, :, 0].copy()
    if result is None or result.shape != (1080, 1920):
        raise RuntimeError("A integer reference failed to produce 1080p Y8")
    return result.tobytes(order="C")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-root", type=Path, required=True, help="Extracted baseline/ directory")
    parser.add_argument("--sessions", type=Path, required=True, help="C-provided board_sessions_portable.json")
    parser.add_argument("--quant-dir", type=Path, default=ROOT / "artifacts/quant")
    parser.add_argument("--c-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file under ignored .data/")
    args = parser.parse_args()

    output_path = args.output.resolve()
    try:
        output_path.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"C-derived verification report must stay under ignored .data/: {output_path}") from exc
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite {output_path}")

    board_root = args.board_root.resolve()
    session_manifest_bytes = args.sessions.read_bytes()
    session_manifest = json.loads(session_manifest_bytes)
    if int(session_manifest.get("raw_frame_count", -1)) <= 0:
        raise ValueError("C manifest has no raw frame count")

    reference = FixedReference(args.quant_dir)
    expected_by_input: dict[str, bytes] = {}
    checked: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for session in session_manifest["sessions"]:
        for frame in session["frames"]:
            input_path = contained_file(board_root, str(frame["input"]))
            output_capture_path = contained_file(board_root, str(frame["output"]))
            expected_path = contained_file(board_root, str(frame["expected"]))
            input_bytes = input_path.read_bytes()
            output_bytes = output_capture_path.read_bytes()
            expected_bytes = expected_path.read_bytes()
            input_hash = sha256(input_bytes)
            if len(input_bytes) != 960 * 540 or len(output_bytes) != 1920 * 1080:
                failures.append({"session": session["session"], "frame_id": frame["frame_id"], "error": "size mismatch"})
                continue
            if input_hash != frame["input_sha256"]:
                failures.append({"session": session["session"], "frame_id": frame["frame_id"], "error": "input SHA mismatch"})
                continue
            if len(expected_bytes) != 1920 * 1080 or sha256(expected_bytes) != frame["expected_sha256"]:
                failures.append({"session": session["session"], "frame_id": frame["frame_id"], "error": "expected file mismatch"})
                continue
            if input_hash not in expected_by_input:
                expected_by_input[input_hash] = a_integer_output(reference, input_bytes)
            a_bytes = expected_by_input[input_hash]
            board_mismatch = sum(left != right for left, right in zip(output_bytes, a_bytes, strict=True))
            expected_mismatch = sum(left != right for left, right in zip(expected_bytes, a_bytes, strict=True))
            record = {
                "session": session["session"],
                "frame_id": frame["frame_id"],
                "input_sha256": input_hash,
                "board_output_sha256": sha256(output_bytes),
                "c_expected_sha256": sha256(expected_bytes),
                "a_integer_reference_sha256": sha256(a_bytes),
                "board_vs_a_mismatch_bytes": board_mismatch,
                "c_expected_vs_a_mismatch_bytes": expected_mismatch,
            }
            checked.append(record)
            if (
                board_mismatch != 0
                or expected_mismatch != 0
                or sha256(output_bytes) != frame["output_sha256"]
                or int(frame.get("mismatch_bytes", -1)) != 0
                or frame.get("bit_exact") is not True
            ):
                failures.append({"session": session["session"], "frame_id": frame["frame_id"], "error": "byte mismatch or manifest claim mismatch"})

    expected_count = int(session_manifest["raw_frame_count"])
    status = "PASS_HISTORICAL_C_BOARD_RETURNS_MATCH_A_INTEGER_REFERENCE" if len(checked) == expected_count and not failures else "FAIL"
    report = {
        "schema": "member-a-c-board-return-crosscheck-v1",
        "status": status,
        "c_source_commit": args.c_source_commit,
        "c_session_manifest_sha256": sha256(session_manifest_bytes),
        "a_quant_params_sha256": sha256((args.quant_dir / "quant_params.json").read_bytes()),
        "frames_checked": len(checked),
        "unique_inputs_recomputed": len(expected_by_input),
        "frames_expected": expected_count,
        "sessions": [session["session"] for session in session_manifest["sessions"]],
        "checks": checked,
        "failures": failures,
        "limitations": [
            "This rechecks archived historical 100/150 MHz C baseline returns, not a new board run or the later observation-candidate bitstream.",
            "The four board fixtures are fixed pattern/reference inputs, not the 25 natural-video quality set; this does not add board PSNR/SSIM against HR.",
            "C's archived board files and bitstreams remain local ignored data and are not copied into the A branch.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "frames_checked": len(checked),
        "unique_inputs_recomputed": len(expected_by_input),
        "failures": len(failures),
        "c_source_commit": args.c_source_commit,
    }, indent=2, ensure_ascii=True))
    return 0 if status.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
