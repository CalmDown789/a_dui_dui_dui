from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "results" / "r0_color_quality_20261007"
CHECKPOINT_DIR = ROOT / ".data" / "r0_color_quality_20261007_checkpoint"
SEQUENCES = ("Beauty", "Jockey", "Bosphorus")
CONTACT_ORDINALS = (0, 15, 29)
PANEL_WIDTH, PANEL_HEIGHT = 384, 216
SOURCE_HEADER_HEIGHT = 30
HEADER_HEIGHT = 50
LABELS = (
    "Decoded 4K reference",
    "Bicubic Y + bicubic CbCr",
    "R0 integer Y + bicubic CbCr",
    "Bicubic Y + bilinear CbCr",
    "R0 integer Y + bilinear CbCr",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_row(source_path: Path, sequence: str, frame_index: int) -> Image.Image:
    expected_source_size = (PANEL_WIDTH * len(LABELS), PANEL_HEIGHT + SOURCE_HEADER_HEIGHT)
    with Image.open(source_path) as opened:
        source = opened.convert("RGB")
    if source.size != expected_source_size:
        raise ValueError(f"Unexpected checkpoint contact-row size at {source_path}: {source.size}")

    row = Image.new("RGB", (expected_source_size[0], PANEL_HEIGHT + HEADER_HEIGHT), "#111111")
    draw = ImageDraw.Draw(row)
    font = ImageFont.load_default(size=14)
    draw.text((4, 2), f"{sequence} - source frame {frame_index}", font=font, fill="white")
    for column, label in enumerate(LABELS):
        x = column * PANEL_WIDTH
        draw.text((x + 4, 27), label, font=font, fill="white")
        crop = source.crop((x, SOURCE_HEADER_HEIGHT, x + PANEL_WIDTH, SOURCE_HEADER_HEIGHT + PANEL_HEIGHT))
        row.paste(crop, (x, HEADER_HEIGHT))
    return row


def render_contact_sheets(output_dir: Path = OUTPUT_DIR, checkpoint_dir: Path = CHECKPOINT_DIR) -> dict:
    output_dir, checkpoint_dir = output_dir.resolve(), checkpoint_dir.resolve()
    metrics_path = output_dir / "per_frame_color_metrics.csv"
    manifest_path = output_dir / "evaluation_manifest.json"
    if not metrics_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("A completed color evaluation is required before rendering contact sheets")

    with metrics_path.open(newline="", encoding="utf-8") as stream:
        metric_rows = list(csv.DictReader(stream))
    if len(metric_rows) != len(SEQUENCES) * 30:
        raise ValueError(f"Expected 90 completed frame records, found {len(metric_rows)}")
    row_by_key = {
        (row["sequence"], int(row["sample_ordinal"])): row
        for row in metric_rows
    }
    if len(row_by_key) != len(metric_rows):
        raise ValueError("The completed frame CSV contains duplicate sequence/ordinal rows")

    visual_dir = output_dir / "visuals"
    visual_dir.mkdir(parents=True, exist_ok=True)
    contact_paths = []
    for sequence in SEQUENCES:
        rows = []
        for ordinal in CONTACT_ORDINALS:
            metric = row_by_key.get((sequence, ordinal))
            if metric is None:
                raise ValueError(f"Missing contact-sheet sample {sequence} ordinal {ordinal}")
            contact_row_path = checkpoint_dir / "contact_rows" / f"{sequence.lower()}_ordinal_{ordinal:02d}.jpg"
            if not contact_row_path.is_file():
                raise FileNotFoundError(f"Missing saved contact-row thumbnail: {contact_row_path}")
            rows.append(_render_row(contact_row_path, sequence, int(metric["decoded_frame_index"])))

        sheet = Image.new("RGB", (PANEL_WIDTH * len(LABELS), len(rows) * (PANEL_HEIGHT + HEADER_HEIGHT)), "#111111")
        row_height = PANEL_HEIGHT + HEADER_HEIGHT
        for index, row in enumerate(rows):
            sheet.paste(row, (0, index * row_height))
        path = visual_dir / f"{sequence.lower()}_color_contact.jpg"
        sheet.save(path, format="JPEG", quality=92, optimize=True)
        contact_paths.append(path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_records = {item["path"]: item for item in manifest["outputs"]["files"]}
    for path in contact_paths:
        relative = path.relative_to(output_dir).as_posix()
        output_records[relative] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    manifest["outputs"]["files"] = list(output_records.values())
    manifest["visualization"] = {
        "renderer": Path(__file__).relative_to(ROOT).as_posix(),
        "renderer_sha256": _sha256_file(Path(__file__)),
        "panel_order": list(LABELS),
        "contact_sample_ordinals": list(CONTACT_ORDINALS),
        "layout": {"panel_width": PANEL_WIDTH, "panel_height": PANEL_HEIGHT,
                   "header_height": HEADER_HEIGHT, "rows_per_sequence": len(CONTACT_ORDINALS)},
    }
    temporary_manifest = manifest_path.with_name(manifest_path.name + ".tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8", newline="\n")
    temporary_manifest.replace(manifest_path)
    return {"status": "PASS", "contact_sheets": [path.relative_to(output_dir).as_posix()
                                                   for path in contact_paths],
            "renderer_sha256": manifest["visualization"]["renderer_sha256"]}


def main() -> int:
    result = render_contact_sheets()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
