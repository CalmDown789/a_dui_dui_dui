"""Create an attributed software color clip from frozen integer Y Goldens."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MOVIE = ROOT / ".data/public_sequence/big_buck_bunny_720p_stereo.ogg"
MOVIE_SHA256 = "785b09a585be55f81326a3fcef2cdeeb7ebbc33932b6305fd84209928df67f28"
ATTRIBUTION = "(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org"
LICENSE = "CC BY 3.0"
SCALE_FILTER = ("select=gte(n\\,1440)*not(mod(n-1440\\,12)),"
                "scale=1920:1080:flags=lanczos:in_color_matrix=bt709:out_color_matrix=bt709:"
                "in_range=tv:out_range=pc,format=yuv444p")


def digest(path: Path) -> dict[str, int | str]:
    size = 0
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block); sha.update(block)
    return {"bytes": size, "sha256": sha.hexdigest()}


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=MOVIE)
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/multiframe/manifest.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/color_demo")
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"Refusing to overwrite nonempty color demo directory: {args.output_dir}")
    if not args.video.is_file() or digest(args.video)["sha256"] != MOVIE_SHA256:
        parser.error("Pinned CC BY Big Buck Bunny source is missing or changed")
    if args.ffmpeg:
        ffmpeg = str(args.ffmpeg)
    else:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    sys.path.insert(0, str(ROOT / "scripts"))
    from compare_board_sequence import load_manifest, safe_path
    manifest = load_manifest(args.manifest)
    indices = [frame.get("source_frame_index") for frame in manifest["frames"]]
    if len(indices) != 8 or indices != list(range(1440, 1536, 12)):
        parser.error("Color demo expects the frozen Big Buck Bunny frames 1440, 1452, ..., 1524")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / ".data/color_video_demo"
    scratch.mkdir(parents=True, exist_ok=True)
    combined = scratch / "integer_y_fullrange_chroma_yuv444p_8frames.tmp"
    mp4 = output_dir / "bbb_fsrcnn_integer_960x540_to_1920x1080.mp4"
    width, height, count = 1920, 1080, len(indices)
    plane = width * height
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(args.video),
        "-vf", SCALE_FILTER, "-frames:v", str(count), "-fps_mode", "passthrough", "-an",
        "-f", "rawvideo", "-pix_fmt", "yuv444p", "pipe:1"]
    source = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processed_frames = []
    try:
        assert source.stdout is not None
        with combined.open("xb") as target:
            for manifest_frame in manifest["frames"]:
                source_planes = source.stdout.read(plane * 3)
                if len(source_planes) != plane * 3:
                    raise RuntimeError(f"FFmpeg supplied a short chroma frame; got {len(source_planes)} bytes")
                y_path = safe_path(args.manifest.parent, manifest_frame["golden"]["path"])
                y = y_path.read_bytes()
                if len(y) != plane:
                    raise RuntimeError(f"Frozen integer Golden has an invalid frame length: {y_path}")
                # Source Y is deliberately discarded. Cb/Cr are software-upsampled
                # from the original 1280x720 video; the frozen integer Y replaces it.
                u = source_planes[plane:2 * plane]
                v = source_planes[2 * plane:]
                target.write(y); target.write(u); target.write(v)
                processed_frames.append({"frame_id": manifest_frame["frame_id"],
                    "source_frame_index": manifest_frame["source_frame_index"],
                    "source_timestamp_seconds": manifest_frame["source_timestamp_seconds"],
                    "input_y_sha256": manifest_frame["input"]["sha256"],
                    "integer_y_sha256": manifest_frame["golden"]["sha256"],
                    "upsampled_cb_sha256": hashlib.sha256(u).hexdigest(),
                    "upsampled_cr_sha256": hashlib.sha256(v).hexdigest()})
        source.stdout.close()
        error = source.stderr.read() if source.stderr else b""
        if source.wait() != 0:
            raise RuntimeError("FFmpeg chroma extraction failed: " + error.decode("utf-8", "replace")[-3000:])
    finally:
        if source.poll() is None:
            source.kill(); source.wait()
    if combined.stat().st_size != count * plane * 3:
        raise RuntimeError("Composed YUV444 frame stream length is incorrect")

    encode = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "rawvideo", "-pix_fmt", "yuv444p", "-video_size", f"{width}x{height}",
        "-framerate", "2", "-color_range", "pc", "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-i", str(combined), "-frames:v", str(count), "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-color_range", "pc", "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-movflags", "+faststart", "-metadata", "title=FSRCNN integer Y + software-upsampled chroma",
        "-metadata", "artist=Blender Foundation (Big Buck Bunny); ACX750 Member A software demonstration",
        "-metadata", "comment=Y from frozen integer FSRCNN; CbCr Lanczos upsampled. BT.709 assumed because source tags are unspecified. No audio.",
        str(mp4)]
    run(encode)
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp4), "-f", "null", "-"])
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(mp4)], capture_output=True, text=True, encoding="utf-8")
    stream_lines = [line.strip() for line in probe.stderr.splitlines() if "Stream #0:0" in line]
    output_manifest = {
        "schema": "member-a-color-video-software-demo-v1", "status": "PASS",
        "source": {"title": "Big Buck Bunny (2008)", "credit": ATTRIBUTION, "license": LICENSE,
                   "license_url": "https://creativecommons.org/licenses/by/3.0/",
                   "official_source": "https://peach.blender.org/about/", **digest(args.video)},
        "model": {"config": "FSRCNNSubpixel d16/s8/m1/c16 x2", "quant_params_sha256":
                  "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a",
                  "integer_output_source": "artifacts/multiframe/*.bin frozen integer Golden"},
        "conversion": {"input_y": "Existing frozen 960x540 full-range uint8 Y; unchanged model inputs",
            "output_y": "Frozen integer Golden 1920x1080 uint8 Y replaces decoded source luma",
            "cb_cr": "Original source Cb/Cr software-upsampled 1280x720 to 1920x1080 using FFmpeg/libswscale Lanczos",
            "source_range_conversion": "FFmpeg scale in_range=tv, out_range=pc for all planar YUV channels",
            "source_color_tags": "Original Theora tags report unknown; BT.709 matrix is explicitly assumed for this demonstration",
            "composition": "full-range YUV444; encode H.264 yuv420p full-range, BT.709, CRF18",
            "audio": "omitted", "frame_rate_fps": 2,
            "scope": "Software visual demonstration only; not FPGA capture or performance measurement"},
        "frames": processed_frames,
        "output": {"path": mp4.name, **digest(mp4), "codec_probe": stream_lines,
                   "decode_exit_code": 0, "video_frame_count": count, "duration_seconds": count / 2},
        "tool": {"ffmpeg_version": subprocess.check_output([ffmpeg, "-version"], text=True).splitlines()[0]},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(output_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (output_dir / "ATTRIBUTION.md").write_text(
        "# 素材署名\n\n" + ATTRIBUTION + "\n\n"
        + "授权： [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)；"
        + "[官方说明](https://peach.blender.org/about/)。\n\n"
        + "本短片从 Big Buck Bunny 抽取第 1440 至 1524 帧（每 12 帧一帧），无音频。"
        + "将冻结整数 FSRCNN 的 1080p Y 与软件 Lanczos 放大的色度 Cb/Cr 合成，"
        + "并编码为 2 fps H.264。源视频颜色标签未指定，演示按 BT.709 解释。\n",
        encoding="utf-8", newline="\n")
    combined.unlink()
    print(json.dumps({"status": "PASS", "frames": count, "duration_seconds": count / 2,
        "output": str(mp4), "bytes": mp4.stat().st_size, "sha256": digest(mp4)["sha256"],
        "source_color_tags": "unknown; assumed BT.709", "board_capture_tested": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
