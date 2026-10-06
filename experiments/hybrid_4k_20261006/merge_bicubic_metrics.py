from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser(description="Join paired bicubic SSIM into experimental candidate evaluations")
    parser.add_argument("--bicubic-csv", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, action="append", required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    bicubic_path = args.bicubic_csv.resolve()
    try:
        bicubic_path.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Bicubic metrics must remain under ignored .data/: {bicubic_path}") from exc
    baseline_rows = _read_csv(bicubic_path)
    baseline_by_key = {(row["sequence"], row["image"]): row for row in baseline_rows}
    if len(baseline_by_key) != len(baseline_rows):
        raise ValueError("Bicubic baseline contains duplicate sequence/image keys")
    baseline_sha = hashlib.sha256(bicubic_path.read_bytes()).hexdigest()

    updated: list[dict[str, object]] = []
    for candidate_dir in args.candidate_dir:
        root = candidate_dir.resolve()
        try:
            root.relative_to(repo_root / ".data")
        except ValueError as exc:
            raise ValueError(f"Candidate package must remain under ignored .data/: {root}") from exc
        evaluation_dir = root / "evaluation"
        csv_path = evaluation_dir / "per_image_metrics.csv"
        summary_path = evaluation_dir / "summary.json"
        rows = _read_csv(csv_path)
        if len(rows) != len(baseline_rows):
            raise ValueError(f"Sample-count mismatch in {root.name}: {len(rows)} vs {len(baseline_rows)}")
        for row in rows:
            key = (row["sequence"], row["image"])
            base = baseline_by_key.get(key)
            if base is None:
                raise ValueError(f"No paired bicubic baseline for {key}")
            for name in ("bicubic_psnr_db", "bicubic_psnr_db_full"):
                if abs(float(row[name]) - float(base[name])) > 1.0e-8:
                    raise ValueError(f"Bicubic PSNR mismatch for {key}: {name}")
            row["bicubic_ssim"] = base["bicubic_ssim"]
            row["bicubic_ssim_full"] = base["bicubic_ssim_full"]

        fieldnames = list(rows[0])
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["means"]["bicubic_ssim"] = float(np.mean([float(row["bicubic_ssim"]) for row in rows]))
        summary["means"]["bicubic_ssim_full"] = float(np.mean([float(row["bicubic_ssim_full"]) for row in rows]))
        summary["bicubic_metrics_source"] = str(bicubic_path)
        summary["bicubic_metrics_sha256"] = baseline_sha
        summary["metric_rule"] = "Y PSNR/SSIM; report full frame (border=0) and center crop (8-pixel shave); arithmetic mean over paired images"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        updated.append({"candidate": root.name, "samples": len(rows), "bicubic_ssim_mean": summary["means"]["bicubic_ssim"]})

    print(json.dumps({"bicubic_metrics_sha256": baseline_sha, "updated": updated}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
