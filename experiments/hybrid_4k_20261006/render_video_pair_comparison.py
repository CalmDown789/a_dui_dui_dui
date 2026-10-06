from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .compare_color_video_runs import compare_summaries


def render_pair_comparison(baseline_dir: Path, candidate_dir: Path, output: Path) -> dict[str, object]:
    base_summary = json.loads((baseline_dir / "summary.json").read_text(encoding="utf-8"))
    cand_summary = json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8"))
    compare_summaries(base_summary, cand_summary)
    for field in ("source_video_sha256", "source_frame_indices", "output_fps_for_selected_frames", "input_format"):
        if base_summary.get(field) != cand_summary.get(field):
            raise ValueError(f"Paired video runs differ in {field}")
    if base_summary.get("preview_source_frame_indices") != cand_summary.get("preview_source_frame_indices"):
        raise ValueError("Paired runs do not preview the same source frames")

    preview_indices = base_summary["preview_source_frame_indices"]
    preview_ordinals = []
    source_indices = base_summary["source_frame_indices"]
    for source_index in preview_indices:
        try:
            preview_ordinals.append(source_indices.index(source_index))
        except ValueError as exc:
            raise ValueError(f"Preview frame {source_index} is absent from the source index list") from exc

    labels = ["4K reference", "bicubic ×4", "R0F integer", "R0-QAT integer"]
    thumb = (640, 360)
    label_height = 30
    canvas = Image.new("RGB", (thumb[0] * len(labels), (thumb[1] + label_height) * len(preview_ordinals)), (25, 25, 25))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for row, (ordinal, source_index) in enumerate(zip(preview_ordinals, preview_indices, strict=True)):
        filenames = [
            baseline_dir / f"frame_{ordinal:03d}_reference.png",
            baseline_dir / f"frame_{ordinal:03d}_bicubic.png",
            baseline_dir / f"frame_{ordinal:03d}_hybrid.png",
            candidate_dir / f"frame_{ordinal:03d}_hybrid.png",
        ]
        for column, (label, path) in enumerate(zip(labels, filenames, strict=True)):
            if not path.is_file():
                raise FileNotFoundError(f"Missing paired preview frame: {path}")
            x = column * thumb[0]
            y = row * (thumb[1] + label_height)
            draw.text((x + 6, y + 6), f"Source frame {source_index}: {label}", fill=(245, 245, 245), font=font)
            with Image.open(path) as image:
                canvas.paste(image.convert("RGB").resize(thumb, Image.Resampling.LANCZOS), (x, y + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    canvas.save(output, optimize=True)
    return {
        "status": "SOFTWARE_VISUAL_COMPARISON_ONLY",
        "sequence": base_summary.get("sequence"),
        "source_video_sha256": base_summary["source_video_sha256"],
        "source_frame_indices": preview_indices,
        "baseline_model_mode": base_summary.get("model_mode"),
        "candidate_model_mode": cand_summary.get("model_mode"),
        "output": str(output.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render same-frame visual comparisons for two integer video runs")
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output PNG under ignored .data/")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Pair comparisons must be written under ignored .data/: {output}") from exc
    result = render_pair_comparison(args.baseline_dir, args.candidate_dir, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
