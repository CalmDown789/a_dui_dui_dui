"""Verify exported handoff files; does not run or modify FPGA tools or RTL."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parent
manifest = json.loads((root / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
errors = []
for row in manifest["files"]:
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        errors.append(row["path"])
        continue
    data = path.read_bytes()
    if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
        errors.append(row["path"])
for name in manifest["archives"]:
    with zipfile.ZipFile(root / name) as archive:
        bad = archive.testzip()
        if bad:
            errors.append(f"{name}:{bad}")
print(json.dumps({"status": "FAIL" if errors else "PASS", "files_checked": len(manifest["files"]), "errors": errors}, indent=2))
raise SystemExit(bool(errors))
