"""Download and validate the official DIV2K training-HR archive locally."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
import urllib.request
import zipfile

from PIL import Image


URL = "https://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_train_HR.zip"
EXPECTED_BYTES = 3_530_603_713
EXPECTED_IMAGES = 800


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_part(index: int, start: int, end: int, parts: Path, retries: int = 4) -> Path:
    target = parts / f"part-{index:05d}.bin"
    expected = end - start + 1
    if target.is_file() and target.stat().st_size == expected:
        return target
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            URL,
            headers={"Range": f"bytes={start}-{end}", "User-Agent": "FSRCNN-academic-research/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                content_range = response.headers.get("Content-Range", "")
                if response.status != 206 or not content_range.startswith(f"bytes {start}-{end}/"):
                    raise RuntimeError(f"Unexpected range response: status={response.status}, range={content_range!r}")
                payload = response.read()
            if len(payload) != expected:
                raise RuntimeError(f"Part {index} has {len(payload)} bytes; expected {expected}")
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(target)
            return target
        except Exception as error:
            last_error = error
            time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"Could not download byte range {start}-{end}: {last_error}")


def download_archive(archive: Path, parts: Path, workers: int = 12, chunk_mib: int = 32) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if archive.stat().st_size != EXPECTED_BYTES:
            raise RuntimeError(f"Existing archive has wrong size: {archive.stat().st_size}")
        return
    parts.mkdir(parents=True, exist_ok=True)
    chunk_size = chunk_mib * 1024 * 1024
    ranges = []
    for start in range(0, EXPECTED_BYTES, chunk_size):
        end = min(start + chunk_size, EXPECTED_BYTES) - 1
        ranges.append((len(ranges), start, end))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_part, i, start, end, parts) for i, start, end in ranges]
        complete = 0
        for future in as_completed(futures):
            future.result()
            complete += 1
            if complete % 4 == 0 or complete == len(futures):
                print(f"downloaded {complete}/{len(futures)} ranges", flush=True)
    building = archive.with_name(archive.name + ".building")
    if building.exists():
        raise RuntimeError(f"Refusing to overwrite partial assembly: {building}")
    total = 0
    with building.open("xb") as output:
        for index, _, _ in ranges:
            part = parts / f"part-{index:05d}.bin"
            with part.open("rb") as source:
                shutil.copyfileobj(source, output, length=4 * 1024 * 1024)
            total += part.stat().st_size
    if total != EXPECTED_BYTES or building.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError(f"Assembled archive size mismatch: {total}")
    with zipfile.ZipFile(building) as archive_file:
        corrupt = archive_file.testzip()
        if corrupt is not None:
            raise RuntimeError(f"Archive CRC failure at {corrupt}")
    building.replace(archive)


def extract_train_images(archive: Path, image_dir: Path) -> list[Path]:
    if image_dir.exists():
        existing = sorted(image_dir.glob("*.png"))
        if len(existing) == EXPECTED_IMAGES:
            for path in existing:
                with Image.open(path) as image:
                    image.verify()
            return existing
        if any(image_dir.iterdir()):
            raise RuntimeError(f"Refusing to mix with partial/non-DIV2K files: {image_dir}")
    else:
        image_dir.mkdir(parents=True)
    with zipfile.ZipFile(archive) as archive_file:
        selected = []
        for name in archive_file.namelist():
            path = PurePosixPath(name)
            if len(path.parts) != 2 or path.parts[0] != "DIV2K_train_HR" or path.suffix.lower() != ".png":
                continue
            stem = path.stem
            if not (stem.isdigit() and 1 <= int(stem) <= EXPECTED_IMAGES):
                continue
            selected.append(name)
        if len(selected) != EXPECTED_IMAGES:
            raise RuntimeError(f"Expected {EXPECTED_IMAGES} training images, found {len(selected)}")
        for name in selected:
            target = image_dir / PurePosixPath(name).name
            with archive_file.open(name) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    images = sorted(image_dir.glob("*.png"))
    if len(images) != EXPECTED_IMAGES:
        raise RuntimeError(f"Extraction produced {len(images)} PNGs")
    for path in images:
        with Image.open(path) as image:
            image.verify()
    return images


def materialize_split(images: list[Path], split_dir: Path) -> tuple[list[Path], list[Path]]:
    train_dir = split_dir / "train_hr"
    validation_dir = split_dir / "validation_hr"
    train_sources = [path for path in images if int(path.stem) <= 720]
    validation_sources = [path for path in images if int(path.stem) > 720]
    for target_dir, sources, expected in (
        (train_dir, train_sources, 720),
        (validation_dir, validation_sources, 80),
    ):
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(target_dir.glob("*.png"))
        if existing:
            if len(existing) != expected or [p.name for p in existing] != [p.name for p in sources]:
                raise RuntimeError(f"Existing DIV2K split does not match expected IDs: {target_dir}")
            continue
        for source in sources:
            os.link(source, target_dir / source.name)
    return sorted(train_dir.glob("*.png")), sorted(validation_dir.glob("*.png"))


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    data_root = root / ".data/model_optimization/datasets/div2k"
    archive = data_root / "archives/DIV2K_train_HR.parallel.zip"
    parts = data_root / "archives/.parts"
    images_dir = data_root / "DIV2K_train_HR"
    download_archive(archive, parts)
    images = extract_train_images(archive, images_dir)
    train_images, validation_images = materialize_split(images, data_root / "split")
    manifest = {
        "dataset": "DIV2K_train_HR",
        "source_url": URL,
        "usage_notice": "Official page limits the dataset to academic research; images retain their original owners' copyrights.",
        "source_page": "https://data.vision.ee.ethz.ch/cvl/DIV2K/",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256(archive),
        "image_count": len(images),
        "image_filename_range": [images[0].name, images[-1].name],
        "internal_split": {"training_images": len(train_images), "validation_images": len(validation_images),
                           "rule": "IDs 0001-0720 for training; 0721-0800 reserved for validation; hardlinks to source images"},
        "image_collection_sha256": hashlib.sha256("".join(sha256(path) for path in images).encode()).hexdigest(),
        "raw_images_committed": False,
    }
    (data_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
