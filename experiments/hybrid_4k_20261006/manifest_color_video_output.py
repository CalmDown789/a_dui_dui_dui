from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


MANIFEST_NAME = "delivery_manifest.json"


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(output_dir: Path) -> dict[str, Any]:
    root = Path(output_dir)
    files = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != MANIFEST_NAME):
        relative = path.relative_to(root).as_posix()
        files[relative] = {"bytes": path.stat().st_size, "sha256": _digest(path)}
    if not files:
        raise ValueError("Output directory contains no delivery files")
    return {
        "schema": "member-a-color-video-output-manifest-v1",
        "files_checked_excluding_manifest": len(files),
        "files": files,
    }


def verify_manifest(output_dir: Path) -> dict[str, Any]:
    root = Path(output_dir)
    manifest_path = root / MANIFEST_NAME
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = build_manifest(root)
    if actual != expected:
        expected_files = expected.get("files", {})
        actual_files = actual["files"]
        mismatches = [
            name
            for name in sorted(set(expected_files) | set(actual_files))
            if expected_files.get(name) != actual_files.get(name)
        ]
        raise AssertionError(f"Output manifest mismatch: {mismatches}")
    return {
        "status": "PASS_COLOR_VIDEO_OUTPUT_INTEGRITY",
        "files_checked": actual["files_checked_excluding_manifest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or verify hashes for a software color-video demo folder")
    parser.add_argument("--output-dir", type=Path, required=True, help="Demo output folder under ignored .data/")
    parser.add_argument("--verify", action="store_true", help="Verify an existing delivery_manifest.json")
    args = parser.parse_args()

    root = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        root.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Video output directory must stay under ignored .data/: {root}") from exc
    manifest_path = root / MANIFEST_NAME
    if args.verify:
        result = verify_manifest(root)
    else:
        if manifest_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing manifest: {manifest_path}")
        manifest = build_manifest(root)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = {"status": "CREATED_COLOR_VIDEO_OUTPUT_MANIFEST", "files_checked": manifest["files_checked_excluding_manifest"]}
    print(json.dumps({"directory": str(root), **result}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
