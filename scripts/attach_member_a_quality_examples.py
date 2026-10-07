"""Attach a verified software comparison contact sheet to the A Golden bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / ".data/member_a_4k_postprocess_golden"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()
    visual = args.visual_dir.resolve()
    artifact = args.artifact_dir.resolve()
    source_image = visual / "quality_examples.png"
    source_report = visual / "quality_examples.json"
    manifest_path = artifact / "manifest.json"
    if not all(path.is_file() for path in (source_image, source_report, manifest_path)):
        raise FileNotFoundError("Visual examples and A Golden manifest are required")
    report = json.loads(source_report.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report.get("schema") != "member-a-4k-quality-visual-examples-v1":
        raise ValueError("Unrecognized visual report")
    if report.get("evaluation_summary_sha256") != manifest.get("evaluation_summary_sha256"):
        raise ValueError("Visuals and Golden package refer to different evaluation runs")
    if sha256(source_image) != report.get("image_sha256"):
        raise ValueError("Visual contact sheet hash mismatch")
    image_target = artifact / "quality_examples.png"
    report_target = artifact / "quality_examples.json"
    if image_target.exists() or report_target.exists():
        raise FileExistsError("Quality examples already exist in the artifact package")
    shutil.copyfile(source_image, image_target)
    shutil.copyfile(source_report, report_target)
    manifest["quality_examples"] = {
        "image": image_target.name,
        "image_sha256": sha256(image_target),
        "report": report_target.name,
        "report_sha256": sha256(report_target),
        "status": report["status"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"image_sha256": sha256(image_target), "report_sha256": sha256(report_target),
                      "manifest_sha256": sha256(manifest_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
