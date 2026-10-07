from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zlib

from .candidate_bundle_paths import resolve_candidate_bundle_root


def _file_digest(path: Path) -> dict[str, str | int]:
    digest = hashlib.sha256()
    crc = 0
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
            crc = zlib.crc32(block, crc)
    return {"bytes": size, "crc32": f"{crc & 0xFFFFFFFF:08x}", "sha256": digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an integrity manifest for an experimental integer candidate bundle")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-published",
        action="store_true",
        help="allow bundles under experiments/hybrid_4k_20261006/candidate_delivery",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    root = resolve_candidate_bundle_root(
        args.bundle_dir, repo_root, allow_published=args.allow_published
    )
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = {
        path.relative_to(root).as_posix(): _file_digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "bundle_manifest.json"
    }
    manifest = {
        "schema": "member-a-experimental-candidate-bundle-manifest-v1",
        "status": "EXPERIMENTAL_NOT_FORMAL_A_DELIVERY",
        "bundle": root.relative_to(repo_root).as_posix() if args.allow_published else str(root),
        "file_count": len(files),
        "files": files,
    }
    output = root / "bundle_manifest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\r\n")
    print(json.dumps({"manifest": str(output), "file_count": len(files), "manifest_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
