from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from member_a.artifacts import generate_full_integer_golden


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a separate full-frame integer Golden for an experimental candidate")
    parser.add_argument("--quant-dir", type=Path, required=True)
    parser.add_argument("--input-bin", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Experimental Golden must remain under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    if not (args.quant_dir / "quant_params.json").is_file() or not args.input_bin.is_file():
        raise FileNotFoundError("Quantization parameters or deterministic input file is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    golden_dir = output_dir / "full_integer_golden"
    manifest = generate_full_integer_golden(args.quant_dir, args.input_bin, golden_dir)
    summary = {
        "schema": "member-a-experimental-full-integer-candidate-golden-v1",
        "status": "EXPERIMENTAL_CANDIDATE_NOT_FROZEN_A_GOLDEN",
        "model": manifest["model"],
        "quant_params_sha256": _sha256(args.quant_dir / "quant_params.json"),
        "input": {
            "path": str(args.input_bin.resolve()),
            "bytes": args.input_bin.stat().st_size,
            "sha256": _sha256(args.input_bin),
        },
        "golden_manifest": str(golden_dir / "manifest.json"),
        "golden_manifest_sha256": _sha256(golden_dir / "manifest.json"),
        "output_sha256": manifest["stage_digests"]["output"]["sha256"],
        "limitations": [
            "The Golden belongs to this experimental candidate quantization package only.",
            "It must not replace the frozen A integer Golden without team approval and complete regression.",
            "B RTL bit-exact comparison, C synthesis/implementation, and board validation remain outstanding.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
