#!/usr/bin/env python3
"""Read-only validation of the 67 sources used by the 150 MHz release.

Canonical comparison replaces CRLF with LF and changes no other bytes. A raw
hash difference alone is permitted when canonical bytes match the frozen run.
"""

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HASHES = HERE / "release_source_hashes.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Checkout root to inspect; defaults to this script's repository")
    root = parser.parse_args().root.resolve()
    manifest = json.loads(HASHES.read_text(encoding="utf-8"))
    entries = manifest["files"]
    if (manifest["schema_version"] != 1 or len(entries) != 67
            or len({entry["path"] for entry in entries}) != 67):
        raise ValueError("Expected exactly 67 unique source entries in the release manifest")
    raw_matches = 0
    canonical_matches = 0
    newline_only = []
    failures = []
    for entry in entries:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Source path escapes checkout: {entry['path']}")
        try:
            data = path.read_bytes()
        except OSError as error:
            failures.append(f"UNREADABLE {entry['path']}: {error}")
            continue
        raw_ok = (len(data) == entry["raw_bytes"]
                  and digest(data) == entry["raw_sha256"])
        canonical = data.replace(b"\r\n", b"\n")
        canonical_ok = (len(canonical) == entry["canonical_bytes"]
                        and digest(canonical) == entry["canonical_sha256"])
        raw_matches += raw_ok
        canonical_matches += canonical_ok
        if canonical_ok and not raw_ok:
            newline_only.append(entry["path"])
        elif not canonical_ok:
            failures.append(f"CONTENT_MISMATCH {entry['path']}")
    print(f"RAW_SHA256_MATCH {raw_matches}/67")
    print(f"CANONICAL_SHA256_MATCH {canonical_matches}/67")
    print(f"CRLF_LF_ONLY_DIFFERENCES {len(newline_only)}")
    for path in newline_only:
        print(f"  CRLF_LF_ONLY {path}")
    for failure in failures:
        print(f"  {failure}")
    if failures:
        print("RELEASE_SOURCES_FAIL")
        return 1
    print("RELEASE_SOURCES_PASS")
    print("No source files changed. DCP, bitstream, and board validation are outside this check.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"RELEASE_SOURCES_ERROR: {error}") from error
