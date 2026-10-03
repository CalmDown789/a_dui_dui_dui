"""Download an attributed Blender movie and extract a fixed, silent Y sequence."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import urllib.request
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_720p_stereo.ogg.zip"
ARCHIVE_SHA256 = "dc24016805203e5ae750f19cbd616e20561664d5bf5755ae484e3ed5487824b2"
MOVIE_SHA256 = "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    if args.ffmpeg:
        ffmpeg = str(args.ffmpeg)
    else:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cache = ROOT / ".data" / "public_sequence"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / URL.rsplit("/", 1)[1]
    if not archive.exists():
        print("Downloading licensed source movie", flush=True)
        temporary = archive.with_suffix(".partial")
        try:
            urllib.request.urlretrieve(URL, temporary)
        except urllib.error.HTTPError:
            # Some download mirrors reject Python's default HTTP client.
            subprocess.run(["curl", "-L", "--fail", "--retry", "3", URL,
                            "-o", str(temporary)], check=True)
        with zipfile.ZipFile(temporary) as zipped:
            if zipped.testzip() is not None:
                raise ValueError("Source archive CRC verification failed")
        temporary.replace(archive)
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError("Source archive differs from the pinned release")
    with zipfile.ZipFile(archive) as zipped:
        movies = [name for name in zipped.namelist() if name.lower().endswith((".ogg", ".ogv"))]
        if len(movies) != 1:
            raise ValueError(f"Expected one movie, found {movies}")
        movie = cache / Path(movies[0]).name
        if not movie.exists():
            with zipped.open(movies[0]) as source, movie.open("wb") as target:
                import shutil
                shutil.copyfileobj(source, target)
    if sha(movie) != MOVIE_SHA256:
        raise ValueError("Source movie differs from the pinned release")
    # Select source frames, not synthesized/interpolated frames. Seek/filter are
    # after input decoding so frame numbers stay tied to the complete movie.
    extraction = "select=gte(n\\,1440)*not(mod(n-1440\\,12)),scale=960:540:flags=lanczos:in_range=tv:out_range=pc,format=gray"
    output = cache / "sequence_960x540_y_u8.bin"
    temporary_output = cache / "sequence_960x540_y_u8.tmp"
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-i", str(movie),
               "-vf", extraction, "-frames:v", "8", "-fps_mode", "passthrough",
               "-an", "-f", "rawvideo", "-pix_fmt", "gray", str(temporary_output)]
    subprocess.run(command, check=True)
    if temporary_output.stat().st_size != 8 * 960 * 540:
        raise ValueError("Unexpected extracted byte count")
    if output.exists() and sha(output) != sha(temporary_output):
        raise ValueError("Decoded bytes changed; refusing to overwrite prior input stream")
    temporary_output.replace(output)
    lut = subprocess.check_output([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
        "nullsrc=size=256x16,format=yuv420p,geq=lum=X:cb=128:cr=128,format=gray",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    if list(lut[:256]) != [max(0,min(255,int((value-16)*255/219+.5))) for value in range(256)]:
        raise ValueError("Pinned FFmpeg limited/full range conversion check failed")
    source = {
        "title": "Big Buck Bunny (2008)", "creator": "Blender Foundation",
        "attribution": "(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org",
        "license": "CC-BY-3.0", "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "license_statement_url": "https://peach.blender.org/about/",
        "download_url": URL, "archive_sha256": sha(archive),
        "archive_bytes": archive.stat().st_size, "movie_sha256": sha(movie),
        "movie_bytes": movie.stat().st_size,
        "source_frame_rate": "24/1", "source_frame_indices": list(range(1440, 1536, 12)),
        "source_shape_wh": [1280, 720], "source_pixel_format": "yuv420p",
        "preprocessing": {
            "crop": "none", "resize": "1280x720 to 960x540, Lanczos via pinned FFmpeg/libswscale",
            "color_input": "Decoded Theora planar YUV420P; consume luma, no RGB/BGR conversion",
            "range": "Interpret source Y as limited [16,235], output full [0,255]; explicit tv to pc",
            "range_formula": "clip(floor((Y-16)*255/219 + 0.5),0,255); scale/range conversion fused by libswscale",
            "rounding": "Pinned FFmpeg/libswscale integer filtering and quantization; no Python/OpenCV gray conversion",
            "authority": "Exact exported .bin SHA-256 is authoritative; same bytes for Golden and PC input",
            "range_lut_256_codes_verified": True,
        },
        "sequence_sampling_fps": 2, "source_timestamps_seconds": [60 + i * .5 for i in range(8)],
        "transform": "Select frames; Lanczos resize to 960x540; FFmpeg gray uint8 full-range luma; no audio",
        "decode_note": "The original OGG reports a keyframe-flag warning. Frames are decoded sequentially from the beginning (no keyframe seek); archive CRC and source/input hashes are verified.",
        "ffmpeg_version": subprocess.check_output([ffmpeg, "-version"], text=True).splitlines()[0],
        "ffmpeg_filter": extraction,
        "extracted_raw_sha256": sha(output), "frame_count": 8,
        "notice": "These frames are a sampled prerecorded sequence, not a 30fps throughput test.",
    }
    (cache / "source.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(source, indent=2), flush=True)


if __name__ == "__main__":
    main()
