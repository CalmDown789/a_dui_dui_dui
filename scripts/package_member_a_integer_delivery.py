"""Regenerate the six-case A integer-vector delivery package deterministically."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PACKAGE = ROOT / "artifacts" / "member_a_integer_delivery_d16_s8_m1_c16_v2.zip"


def build_package() -> dict[str, object]:
    members = [
        path
        for source in (ROOT / "artifacts/quant", ROOT / "artifacts/test_vectors")
        for path in sorted(source.rglob("*"))
        if path.is_file()
    ]
    if not members:
        raise FileNotFoundError("No quantization assets or integer test vectors found")

    PACKAGE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PACKAGE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in members:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    with zipfile.ZipFile(PACKAGE) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Corrupt ZIP member: {bad_member}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate member names in generated package")
        for path in members:
            name = path.relative_to(ROOT).as_posix()
            if archive.read(name) != path.read_bytes():
                raise ValueError(f"Packaged bytes differ from source: {name}")

    digest = hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    return {
        "status": "PASS_MEMBER_A_INTEGER_PACKAGE_V2",
        "path": PACKAGE.relative_to(ROOT).as_posix(),
        "files": len(members),
        "cases": [path.name for path in sorted((ROOT / "artifacts/test_vectors").iterdir()) if path.is_dir()],
        "bytes": PACKAGE.stat().st_size,
        "sha256": digest,
    }


def main() -> int:
    from member_a.artifacts import MEMBER_A_ACCEPTANCE_VECTOR_CASES, generate_fixed_vectors, write_delivery_manifest

    generate_fixed_vectors(
        ROOT / "artifacts/quant",
        ROOT / "artifacts/test_vectors",
        case_names=MEMBER_A_ACCEPTANCE_VECTOR_CASES,
    )
    result = build_package()
    write_delivery_manifest(ROOT)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
