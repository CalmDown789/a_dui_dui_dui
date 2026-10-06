from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
from statistics import fmean
from urllib.parse import quote


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_mp4(path: Path, expected_frames: int) -> dict[str, object]:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required to verify encoded clips") from exc
    completed = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "info", "-i", str(path), "-vf", "showinfo", "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(f"FFmpeg could not decode {path}: {completed.stderr[-1000:]}")
    frame_ids = [int(value) for value in re.findall(r"\bn:\s*(\d+)\s+pts:", completed.stderr)]
    sizes = re.findall(r"\bs:(\d+x\d+)\s+i:", completed.stderr)
    if len(frame_ids) != expected_frames or frame_ids != list(range(expected_frames)):
        raise ValueError(f"Decoded frame count/index mismatch in {path}: {len(frame_ids)} vs {expected_frames}")
    if not sizes or any(size != "3840x2160" for size in sizes):
        raise ValueError(f"Encoded output is not consistently 3840x2160: {path}")
    return {"status": "PASS_MP4_DECODE", "frames": len(frame_ids), "resolution": "3840x2160"}


def collect_video_matrix(root: Path, clip_names: list[str], *, verify_media: bool = True) -> dict[str, object]:
    if len(set(clip_names)) < 10:
        raise ValueError("At least 10 distinct 5–10 second clip directories are required")
    rows: list[dict[str, object]] = []
    used_source_frames: dict[str, set[int]] = {}
    verified_sources: dict[Path, tuple[str, int]] = {}
    for clip_name in clip_names:
        clip_dir = root / clip_name
        summary_path = clip_dir / "summary.json"
        if not summary_path.is_file():
            raise FileNotFoundError(f"Missing clip summary: {summary_path}")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("status") != "SOFTWARE_DEMO_ONLY_NOT_BOARD_PROTOCOL_OR_REALTIME_ACCEPTANCE":
            raise ValueError(f"Unexpected acceptance scope in {summary_path}")
        indices = [int(value) for value in summary["source_frame_indices"]]
        if len(indices) != int(summary["frames"]):
            raise ValueError(f"Frame count mismatch in {summary_path}")
        if len(set(indices)) != len(indices) or indices != sorted(indices):
            raise ValueError(f"Source frame indices must be unique and increasing in {summary_path}")
        source_hash = str(summary["source_video_sha256"])
        source_path = Path(str(summary["source_video"])).resolve()
        if source_path not in verified_sources:
            if not source_path.is_file() or _sha256(source_path) != source_hash:
                raise ValueError(f"Source file is missing or its SHA-256 changed: {source_path}")
            verified_sources[source_path] = (source_hash, source_path.stat().st_size)
        elif verified_sources[source_path][0] != source_hash:
            raise ValueError(f"A source hash differs between clip summaries for {source_path}")
        prior = used_source_frames.setdefault(source_hash, set())
        overlap = prior.intersection(indices)
        if overlap:
            raise ValueError(f"Source frames overlap for {clip_name}: {sorted(overlap)[:8]}")
        prior.update(indices)

        output_fps = float(summary["output_fps_for_selected_frames"])
        duration = len(indices) / output_fps
        if not 5.0 <= duration <= 10.0:
            raise ValueError(f"{clip_name} duration {duration:.3f}s is outside 5–10s")
        metrics = summary["metrics"]["per_frame"]
        if len(metrics) != len(indices):
            raise ValueError(f"Per-frame metric count mismatch in {summary_path}")
        if not (clip_dir / "hybrid_4k_color_demo.mp4").is_file():
            raise FileNotFoundError(f"Missing encoded output for {clip_name}")
        if not (clip_dir / "color_video_contact_sheet.png").is_file():
            raise FileNotFoundError(f"Missing visual preview for {clip_name}")
        mp4_path = clip_dir / "hybrid_4k_color_demo.mp4"
        sheet_path = clip_dir / "color_video_contact_sheet.png"
        media_check = _verify_mp4(mp4_path, len(indices)) if verify_media else None
        model_artifact = Path(str(summary.get("model_artifact", "")))
        bundle_manifest = model_artifact.parent / "bundle_manifest.json"
        rows.append(
            {
                "clip": clip_name,
                "sequence": summary["sequence"],
                "frames": len(indices),
                "fps": output_fps,
                "duration_s": duration,
                "source_sha256": source_hash,
                "source_bytes": verified_sources[source_path][1],
                "model_mode": summary.get("model_mode"),
                "model_bundle_manifest_sha256": _sha256(bundle_manifest) if bundle_manifest.is_file() else None,
                "summary_sha256": _sha256(summary_path),
                "bicubic_y_psnr_db": fmean(float(item["bicubic_y_psnr_db"]) for item in metrics),
                "hybrid_y_psnr_db": fmean(float(item["hybrid_y_psnr_db"]) for item in metrics),
                "delta_y_psnr_db": fmean(float(item["hybrid_y_delta_vs_bicubic_db"]) for item in metrics),
                "bicubic_y_ssim": fmean(float(item["bicubic_y_ssim"]) for item in metrics),
                "hybrid_y_ssim": fmean(float(item["hybrid_y_ssim"]) for item in metrics),
                "summary": str(summary_path),
                "mp4": str(mp4_path),
                "mp4_decode_check": media_check,
                "mp4_sha256": _sha256(mp4_path),
                "contact_sheet": str(sheet_path),
                "contact_sheet_sha256": _sha256(sheet_path),
            }
        )

    all_metrics = [
        row
        for clip_name in clip_names
        for row in json.loads((root / clip_name / "summary.json").read_text(encoding="utf-8"))["metrics"]["per_frame"]
    ]
    total_frames = sum(int(row["frames"]) for row in rows)
    overall = {
        key: fmean(float(frame[key]) for frame in all_metrics)
        for key in (
            "bicubic_y_psnr_db",
            "bicubic_y_ssim",
            "hybrid_y_psnr_db",
            "hybrid_y_ssim",
            "hybrid_y_delta_vs_bicubic_db",
        )
    }
    return {
        "schema": "member-a-video-matrix-v1",
        "scope": "PC software-only, A-side CPU integer reference; not RTL/FPGA/board or real-time acceptance",
        "dataset": "UVG 4K sequences; CC BY-NC non-commercial academic use; cite Mercat et al., ACM MMSys 2020",
        "clips": rows,
        "clip_count": len(rows),
        "total_evaluated_frames": total_frames,
        "overall_frame_weighted_metrics": overall,
    }


def _markdown(report: dict[str, object]) -> str:
    lines = [
        "# 成员 A 多片段整数模型 PC 验证汇总",
        "",
        f"范围：{report['scope']}。数据集许可：{report['dataset']}。",
        "",
        f"样本数：{report['clip_count']} 段，累计 {report['total_evaluated_frames']} 帧。",
        "",
        "| 片段 | UVG 序列 | 帧数 | 输出 fps | 时长 (s) | 双三次 Y-PSNR | 整数混合 Y-PSNR | 增益 (dB) | 双三次 SSIM | 整数混合 SSIM |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["clips"]:
        lines.append(
            "| {clip} | {sequence} | {frames} | {fps:.2f} | {duration_s:.2f} | {bicubic_y_psnr_db:.3f} | {hybrid_y_psnr_db:.3f} | {delta_y_psnr_db:+.3f} | {bicubic_y_ssim:.6f} | {hybrid_y_ssim:.6f} |".format(**row)
        )
    overall = report["overall_frame_weighted_metrics"]
    lines.extend(
        [
            "",
            "逐帧加权总平均：",
            "",
            f"- 双三次：{overall['bicubic_y_psnr_db']:.3f} dB / SSIM {overall['bicubic_y_ssim']:.6f}",
            f"- 整数混合：{overall['hybrid_y_psnr_db']:.3f} dB / SSIM {overall['hybrid_y_ssim']:.6f}",
            f"- PSNR 平均变化：{overall['hybrid_y_delta_vs_bicubic_db']:+.3f} dB",
            "",
            "所有片段均由公开 4K 素材合成 540p 输入，再以 A 侧整数 Python 参考做亮度超分；Cb/Cr 采用 Keys bicubic ×4。结果不证明 FPGA 上板或实时性能，也不等同原生 540p 摄像头输入的泛化表现。",
            "",
        ]
    )
    return "\n".join(lines)


def _player(root: Path, report: dict[str, object]) -> str:
    options = []
    for row in report["clips"]:
        relative_video = Path(str(row["mp4"])).relative_to(root).as_posix()
        options.append(
            f'<option value="{html.escape(quote(relative_video), quote=True)}">'
            f'{html.escape(str(row["clip"]))} — {html.escape(str(row["sequence"]))}</option>'
        )
    return """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>成员 A 多片段整数参考播放器</title>
<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}select{font:inherit;padding:.5rem;max-width:100%;margin:0 0 1rem}video{width:100%;background:#000}p{color:#bbb}</style>
<h1>成员 A 多片段整数参考播放器</h1>
<select id="clip">""" + "\n".join(options) + """</select>
<video id="video" controls preload="metadata"></video>
<p>PC 软件参考结果：Y 通道整数超分，Cb/Cr 软件插值。不是 FPGA 板卡或实时性能验收。素材来自 UVG 4K Dataset，序列版权归 Digiturk；依 CC BY-NC 3.0 署名、非商业条款使用。请引 Mercat et al., ACM MMSys 2020。</p>
<script>const s=document.getElementById('clip'),v=document.getElementById('video');function load(){v.src=s.value;v.load()}s.addEventListener('change',load);load();</script>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and summarize a set of 5–10 second integer video evaluations")
    parser.add_argument("--root", type=Path, required=True, help="Video matrix root under ignored .data/")
    parser.add_argument("--clips", nargs="+", required=True, help="Clip output directory names")
    args = parser.parse_args()
    root = args.root.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        root.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Video matrix reports must be written under ignored .data/: {root}") from exc
    generated_paths = [root / "video_matrix_manifest.json", root / "VIDEO_MATRIX_REPORT.md", root / "VIDEO_MATRIX_PLAYER.html"]
    existing = [path for path in generated_paths if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing matrix deliverables: {existing}")
    report = collect_video_matrix(root, args.clips)
    (root / "video_matrix_manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "VIDEO_MATRIX_REPORT.md").write_text(_markdown(report), encoding="utf-8")
    (root / "VIDEO_MATRIX_PLAYER.html").write_text(_player(root, report), encoding="utf-8")
    print(json.dumps({"clip_count": report["clip_count"], "frames": report["total_evaluated_frames"], "metrics": report["overall_frame_weighted_metrics"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
