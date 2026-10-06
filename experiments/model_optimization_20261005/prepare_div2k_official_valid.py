"""Verify and extract the official DIV2K validation-HR images locally."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from PIL import Image


URL = "https://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_valid_HR.zip"
EXPECTED_BYTES = 448_993_893
EXPECTED_IMAGES = 100


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    data_root = root / ".data/model_optimization/datasets/div2k_official_valid"
    archive = data_root / "archives/DIV2K_valid_HR.zip"
    images_dir = data_root / "HR"
    if not archive.is_file() or archive.stat().st_size != EXPECTED_BYTES:
        raise FileNotFoundError(f"Download complete official archive first: {archive} ({EXPECTED_BYTES} bytes expected)")
    with zipfile.ZipFile(archive) as zip_file:
        corrupt = zip_file.testzip()
        if corrupt:
            raise RuntimeError(f"ZIP CRC failure: {corrupt}")
        selected = []
        for name in zip_file.namelist():
            path = PurePosixPath(name)
            if len(path.parts) != 2 or path.parts[0] != "DIV2K_valid_HR" or path.suffix.lower() != ".png":
                continue
            stem = path.stem
            if stem.isdigit() and 801 <= int(stem) <= 900:
                selected.append(name)
        selected.sort()
        if len(selected) != EXPECTED_IMAGES:
            raise RuntimeError(f"Expected 100 official validation HR images, got {len(selected)}")
        if images_dir.exists():
            existing = sorted(images_dir.glob("*.png"))
            if len(existing) != EXPECTED_IMAGES:
                raise RuntimeError(f"Refusing to mix with incomplete extracted folder: {images_dir}")
        else:
            images_dir.mkdir(parents=True)
            try:
                for name in selected:
                    target = images_dir / PurePosixPath(name).name
                    with zip_file.open(name) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                existing = sorted(images_dir.glob("*.png"))
                if len(existing) != EXPECTED_IMAGES:
                    raise RuntimeError(f"Extraction produced {len(existing)} images")
            except Exception:
                # Preserve partial extraction for inspection; never silently delete source data.
                raise
    images = sorted(images_dir.glob("*.png"))
    if [path.name for path in images] != [f"{index:04d}.png" for index in range(801, 901)]:
        raise RuntimeError("Extracted validation image ID range is not 0801-0900")
    for path in images:
        with Image.open(path) as image:
            image.verify()
    image_collection_sha = hashlib.sha256("".join(sha256(path) for path in images).encode()).hexdigest()
    manifest = {
        "dataset": "DIV2K_official_validation_HR",
        "url": URL,
        "source_page": "https://data.vision.ee.ethz.ch/cvl/DIV2K/",
        "usage_notice": "Official DIV2K page limits use to academic research; source images retain original owners' copyrights.",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256(archive),
        "images": len(images),
        "image_ids": [801, 900],
        "image_collection_sha256": image_collection_sha,
        "images_committed": False,
    }
    (data_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
