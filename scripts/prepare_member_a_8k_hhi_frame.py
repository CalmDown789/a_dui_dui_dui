"""Prepare one local 8K 10-bit HHI luma frame and a synthetic 540p Y8 input.

The licensed source is kept out of the repository. The output directory must
be below .data/ so neither source-derived frames nor inputs are accidentally
published with the code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WIDTH_8K = 7680
HEIGHT_8K = 4320
WIDTH_LR = 960
HEIGHT_LR = 540
Y10_BYTES = WIDTH_8K * HEIGHT_8K * 2
SOURCE_FRAME_BYTES = WIDTH_8K * HEIGHT_8K * 3
SOURCE_URL = "https://dash-large-files.akamaized.net/WAVE/3GPP/5GVideo/ReferenceSequences/BodeMuseum/BodeMuseum.yuv"
SOURCE_PAGE = "https://www.hhi.fraunhofer.de/en/departments/vca/research-groups/video-coding-systems/8k-sequences.html"
SOURCE_TOTAL_BYTES = 59_719_680_000
DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_y_plane(frame_index: int, output_path: Path) -> tuple[bytes, list[list[int]]]:
    frame_offset = frame_index * SOURCE_FRAME_BYTES
    ranges: list[list[int]] = []
    with output_path.open("wb") as stream:
        for offset in range(0, Y10_BYTES, DOWNLOAD_CHUNK_BYTES):
            count = min(DOWNLOAD_CHUNK_BYTES, Y10_BYTES - offset)
            range_start = frame_offset + offset
            range_end = range_start + count - 1
            request = Request(
                SOURCE_URL,
                headers={"Range": f"bytes={range_start}-{range_end}", "User-Agent": "member-a-8k-evaluation/1.0"},
            )
            last_error: Exception | None = None
            for attempt in range(4):
                try:
                    with urlopen(request, timeout=60) as response:
                        content_range = response.headers.get("Content-Range", "")
                        expected_range = f"bytes {range_start}-{range_end}/{SOURCE_TOTAL_BYTES}"
                        if response.status != 206 or content_range != expected_range:
                            raise RuntimeError(
                                f"Expected HTTP 206 {expected_range}, got {response.status} {content_range!r}"
                            )
                        payload = response.read(count + 1)
                        if len(payload) != count:
                            raise RuntimeError(f"Range returned {len(payload)} bytes; expected {count}")
                    stream.write(payload)
                    ranges.append([range_start, range_end])
                    last_error = None
                    break
                except (OSError, URLError, RuntimeError) as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(attempt + 1)
            if last_error is not None:
                raise RuntimeError(f"Failed downloading source bytes {range_start}-{range_end}") from last_error
    raw = output_path.read_bytes()
    if len(raw) != Y10_BYTES:
        raise RuntimeError(f"Downloaded Y plane has {len(raw)} bytes; expected {Y10_BYTES}")
    return raw, ranges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-y10le", type=Path, help="One 7680x4320 10-bit LE luma plane")
    source_group.add_argument(
        "--download-official",
        action="store_true",
        help="Download only the selected Y-plane byte range from the official HHI raw sequence",
    )
    parser.add_argument("--frame-index", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory under the repository .data/")
    args = parser.parse_args()

    if args.frame_index < 0 or args.frame_index >= 600:
        raise ValueError("Frame index must be in the source sequence range 0..599")
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"Source-derived images must stay under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_ranges: list[list[int]] = []
    if args.download_official:
        source_temp = output_dir / f"BodeMuseum_frame_{args.frame_index:03d}_source_y10le.tmp"
        try:
            raw, downloaded_ranges = download_y_plane(args.frame_index, source_temp)
        finally:
            source_temp.unlink(missing_ok=True)
    else:
        raw = args.source_y10le.read_bytes()
    if len(raw) != Y10_BYTES:
        raise ValueError(f"Expected exactly {Y10_BYTES} bytes, got {len(raw)}")
    y10 = np.frombuffer(raw, dtype="<u2")
    if np.any(y10 > 1023):
        raise ValueError("Source contains values outside the 10-bit range")

    # HHI's SDR sequence is 10-bit limited-range YCbCr. Convert nominal Y=64..940
    # to full-range 8-bit Y using nearest integer; clip legal-footroom/headroom.
    y10_f64 = np.clip(y10.astype(np.float64), 64.0, 940.0)
    y8 = np.floor((y10_f64 - 64.0) * (255.0 / 876.0) + 0.5).astype(np.uint8)
    y8 = y8.reshape(HEIGHT_8K, WIDTH_8K)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-video_size",
        f"{WIDTH_8K}x{HEIGHT_8K}",
        "-i",
        "pipe:0",
        "-frames:v",
        "1",
        "-vf",
        f"scale={WIDTH_LR}:{HEIGHT_LR}:flags=bicubic",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    result = subprocess.run(command, input=y8.tobytes(), capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg downsampling failed: {result.stderr.decode(errors='replace')[-2000:]}")
    expected_lr_bytes = WIDTH_LR * HEIGHT_LR
    if len(result.stdout) != expected_lr_bytes:
        raise RuntimeError(f"Expected {expected_lr_bytes} LR bytes, got {len(result.stdout)}")

    hr_path = output_dir / f"BodeMuseum_frame_{args.frame_index:03d}_7680x4320_y8.bin"
    lr_path = output_dir / f"BodeMuseum_frame_{args.frame_index:03d}_960x540_y8.bin"
    hr_bytes = y8.tobytes(order="C")
    hr_path.write_bytes(hr_bytes)
    lr_path.write_bytes(result.stdout)
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]

    frame_offset = args.frame_index * SOURCE_FRAME_BYTES
    manifest = {
        "schema": "member-a-hhi-8k-sample-preparation-v1",
        "status": "LOCAL_NONCOMMERCIAL_EVALUATION_INPUTS_ONLY",
        "source": {
            "title": "8K Berlin Test Sequences - BodeMuseum SDR",
            "creator": "Björn Kowalewsky; Fraunhofer HHI",
            "copyright": "Copyright (C) 2019 Fraunhofer HHI",
            "source_page": SOURCE_PAGE,
            "raw_sequence_url": SOURCE_URL,
            "license": "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International",
            "sequence_format": "7680x4320 YCbCr 4:2:0, BT.2020 SDR, 10-bit, limited range, 60 fps, 600 frames",
            "frame_index": args.frame_index,
            "raw_file_etag_md5": "fba9f8c929d8496ecf80d83645e61706",
            "requested_byte_range_inclusive": [frame_offset, frame_offset + Y10_BYTES - 1],
            "downloaded_byte_ranges_inclusive": downloaded_ranges,
            "requested_bytes": Y10_BYTES,
            "source_y_plane_sha256": sha256(raw),
        },
        "conversion": {
            "y10_to_y8": "little-endian unsigned 16-bit; clip nominal 10-bit limited Y to [64,940]; map linearly to full-range [0,255]; nearest integer with half-up rounding",
            "downsample": "FFmpeg scale bicubic, 7680x4320 Y8 to 960x540 Y8",
            "ffmpeg_version": version,
            "hr_y8": {"file": hr_path.name, "bytes": len(hr_bytes), "sha256": sha256(hr_bytes)},
            "lr_y8": {"file": lr_path.name, "bytes": len(result.stdout), "sha256": sha256(result.stdout)},
            "no_source_or_derived_images_in_repository": True,
        },
    }
    manifest_path = output_dir / "preparation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
