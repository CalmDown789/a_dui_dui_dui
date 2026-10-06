from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HEVC_SEQUENCES = ("Beauty", "Bosphorus", "HoneyBee", "Jockey", "ReadySetGo", "YachtRide", "ShakeNDry")
YUV_SEQUENCES = ("CityAlley", "FlowerFocus", "FlowerKids", "FlowerPan")
USER_AGENT = "member-a-r0-quality-evaluation/1.0"
SEVENZIP_SIGNATURE = b"7z\xbc\xaf\x27\x1c"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sevenzip_signature_offset(path: Path) -> int | None:
    overlap = b""
    consumed = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            block = overlap + chunk
            offset = block.find(SEVENZIP_SIGNATURE)
            if offset >= 0:
                return consumed - len(overlap) + offset
            consumed += len(chunk)
            overlap = block[-(len(SEVENZIP_SIGNATURE) - 1):]
    return None


def _openable_7z_path(archive: Path, scratch_dir: Path) -> tuple[Path, Path | None]:
    with archive.open("rb") as stream:
        signature = stream.read(len(SEVENZIP_SIGNATURE))
    if signature == SEVENZIP_SIGNATURE:
        return archive, None
    if signature[:2] != b"MZ":
        raise ValueError(f"Unrecognized archive header in {archive.name}: {signature.hex()}")
    offset = _sevenzip_signature_offset(archive)
    if offset is None:
        raise ValueError(f"No embedded 7z archive signature found in self-extracting source {archive.name}")
    embedded = scratch_dir / f"{archive.stem}.embedded.7z"
    expected_size = archive.stat().st_size - offset
    if embedded.exists():
        if embedded.stat().st_size != expected_size:
            raise ValueError(f"Incomplete embedded archive remains; inspect before retrying: {embedded}")
        return embedded, embedded
    with archive.open("rb") as source, embedded.open("xb") as target:
        source.seek(offset)
        shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    if embedded.stat().st_size != expected_size:
        raise IOError(f"Embedded archive copy size mismatch: {embedded}")
    return embedded, embedded


def _remote_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        size = response.headers.get("Content-Length")
    if size is None or not size.isdigit():
        raise IOError(f"No Content-Length returned for {url}")
    return int(size)


def _download_resumable(url: str, target: Path, partial_source: Path | None = None) -> Path:
    expected = _remote_size(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size != expected:
            raise ValueError(f"Existing source has unexpected size ({target.stat().st_size}/{expected}); preserve and inspect: {target}")
        return target

    partial = target.with_suffix(target.suffix + ".part")
    if not partial.exists():
        if partial_source and partial_source.is_file():
            if partial_source.stat().st_size > expected:
                raise ValueError(f"Seed file is larger than official source: {partial_source}")
            shutil.copyfile(partial_source, partial)
            print(f"Resuming from local partial {partial.name}: {partial.stat().st_size:,}/{expected:,} bytes", flush=True)
        else:
            partial.touch(exist_ok=False)
    offset = partial.stat().st_size
    if offset > expected:
        raise ValueError(f"Partial source is larger than official file: {partial}")
    if offset < expected:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Range": f"bytes={offset}-{expected - 1}"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if offset and response.status != 206:
                raise IOError(f"Server did not honor byte-range resume for {url} (status {response.status})")
            if offset:
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                if not match or tuple(map(int, match.groups())) != (offset, expected - 1, expected):
                    raise IOError(f"Unexpected Content-Range for {url}: {content_range!r}")
            mode = "ab" if offset else "wb"
            with partial.open(mode) as output:
                downloaded = offset
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded == expected or downloaded % (256 * 1024 * 1024) < len(chunk):
                        print(f"{target.name}: {downloaded:,}/{expected:,} bytes", flush=True)
    if partial.stat().st_size != expected:
        raise IOError(f"Incomplete download retained for safe resume: {partial} ({partial.stat().st_size}/{expected})")
    partial.replace(target)
    print(f"Verified size {target.name}: {expected:,} bytes; SHA-256 {_sha256(target)}", flush=True)
    return target


def _extract_yuv(archive: Path, target: Path, extract_root: Path) -> Path:
    expected_bytes = 3840 * 2160 * 3 // 2 * 50 * 12
    if target.exists():
        if target.stat().st_size != expected_bytes:
            raise ValueError(f"Existing raw source has unexpected size: {target}")
        return target
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError("Install project quality extra to extract licensed YUV sources: pip install -e .[quality]") from exc

    if extract_root.exists():
        if any(extract_root.iterdir()):
            raise FileExistsError(f"Prior extraction directory is non-empty; inspect it before retrying: {extract_root}")
        extract_root.rmdir()
    extract_root.mkdir(parents=True)
    archive_for_reader, temporary_embedded = _openable_7z_path(archive, archive.parent)
    with py7zr.SevenZipFile(archive_for_reader, mode="r") as container:
        names = container.getnames()
        yuv_members = [name for name in names if PurePosixPath(name).suffix.lower() == ".yuv"]
        if len(yuv_members) != 1:
            raise ValueError(f"Expected one .yuv member in {archive.name}; got {yuv_members}")
        print(f"Extracting {archive.name} to ignored local data (about 7.5 GB uncompressed)", flush=True)
        container.extract(path=extract_root, targets=yuv_members)
    extracted = list(extract_root.rglob("*.yuv"))
    if len(extracted) != 1 or extracted[0].stat().st_size != expected_bytes:
        raise ValueError(f"Extracted YUV size mismatch in {extract_root}; expected {expected_bytes} bytes")
    target.parent.mkdir(parents=True, exist_ok=True)
    extracted[0].replace(target)
    if temporary_embedded is not None:
        temporary_embedded.unlink()
    print(f"Verified raw source {target.name}: {target.stat().st_size:,} bytes; SHA-256 {_sha256(target)}", flush=True)
    return target


def prepare(destination: Path, partial_source_dir: Path | None = None) -> list[Path]:
    destination = destination.resolve()
    data_root = (ROOT / ".data").resolve()
    try:
        destination.relative_to(data_root)
    except ValueError as exc:
        raise ValueError(f"Downloaded and extracted data must stay under ignored .data/: {destination}") from exc
    destination.mkdir(parents=True, exist_ok=True)
    partial_source_dir = partial_source_dir.resolve() if partial_source_dir else None
    outputs = []

    for name in HEVC_SEQUENCES:
        filename = f"{name}_3840x2160_120fps_420_8bit_HEVC_RAW.hevc"
        url = f"https://ultravideo.fi/video/{filename}"
        seed = partial_source_dir / filename if partial_source_dir else None
        outputs.append(_download_resumable(url, destination / filename, seed))

    archive_dir = destination / "archives"
    for name in YUV_SEQUENCES:
        stem = f"{name}_3840x2160_50fps_420_8bit_YUV_RAW"
        archive = archive_dir / f"{stem}.7z"
        url = f"https://ultravideo.fi/video/{stem}.7z"
        seed = partial_source_dir / f"{stem}.7z" if partial_source_dir else None
        _download_resumable(url, archive, seed)
        outputs.append(_extract_yuv(archive, destination / f"{stem}.yuv", archive_dir / f"extract_{name}"))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and prepare the non-commercial UVG sources for 4K R0 quality evaluation"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".data" / "r0_4k_quality_20261006" / "sources")
    parser.add_argument("--partial-source-dir", type=Path,
                        help="Optional existing cache; incomplete files are copied and HTTP-range resumed, never modified")
    args = parser.parse_args()
    paths = prepare(args.output_dir, args.partial_source_dir)
    print(f"Ready: {len(paths)} source sequences in {args.output_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
