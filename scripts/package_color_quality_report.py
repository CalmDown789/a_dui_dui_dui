"""Build a compact, self-contained review ZIP for the Member A color and quality work."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "docs/成员A彩色演示与整数画质评测_2026-10-04.md",
    "scripts/evaluate_integer_quality.py",
    "scripts/create_color_video_demo.py",
    "artifacts/color_demo/ATTRIBUTION.md",
    "artifacts/color_demo/manifest.json",
    "artifacts/color_demo/bbb_fsrcnn_integer_960x540_to_1920x1080.mp4",
    "artifacts/evaluation/actual_integer_quality_report.html",
    "artifacts/evaluation/actual_integer_quality_report.json",
    "artifacts/evaluation/actual_integer_quality_per_image.csv",
    "artifacts/evaluation/actual_integer_visual_review.png",
    "artifacts/evaluation/actual_integer_worst_case_detail.png",
)


def main() -> int:
    entries: dict[str, bytes] = {}
    for relative in FILES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Review package is missing {relative}")
        entries[relative] = path.read_bytes()
    # The HTML viewer uses relative references to the packaged clip and data files.
    required_links = {"artifacts/color_demo/bbb_fsrcnn_integer_960x540_to_1920x1080.mp4",
                      "artifacts/evaluation/actual_integer_quality_report.json",
                      "artifacts/evaluation/actual_integer_quality_per_image.csv"}
    if not required_links.issubset(entries):
        raise AssertionError("The review package is missing a linked artifact")
    target = ROOT / "artifacts/member_a_color_quality_evaluation.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, raw)
    with zipfile.ZipFile(target) as archive:
        bad_entry = archive.testzip()
        if bad_entry:
            raise AssertionError(f"ZIP entry failed CRC verification: {bad_entry}")
        if not required_links.issubset(set(archive.namelist())):
            raise AssertionError("A linked HTML artifact is absent from the ZIP")
    result = {"schema": "member-a-color-quality-package-v1", "status": "PASS",
              "path": target.name, "bytes": target.stat().st_size,
              "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "entries": [{"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                          for name, raw in sorted(entries.items())],
              "source_video_included": False, "set5_original_images_included": False}
    (ROOT / "artifacts/color_quality_package.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
