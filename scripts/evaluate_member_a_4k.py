"""Evaluate frozen A integer R0, FP32 R0 and bicubic on paired 4K references."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference
from member_a.metrics import psnr_y
from member_a.model import FSRCNNSubpixel, ModelConfig
from member_a.pc_postprocess_4k import process_1080_frame, resize_keys_u8
from experiments.hybrid_4k_20261006.evaluate_hybrid import _ssim_y_tiled


DEFAULT_CHECKPOINT = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
DEFAULT_QUANT = ROOT / "artifacts/quant"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_u8_prediction(tensor: torch.Tensor) -> np.ndarray:
    values = tensor.detach().to(device="cpu", dtype=torch.float64).numpy().squeeze() * 255.0
    rounded = np.copysign(np.floor(np.abs(values) + 0.5), values)
    return np.clip(rounded, 0, 255).astype(np.uint8)


def metrics(reference: np.ndarray, output: np.ndarray, border: int) -> tuple[float, float]:
    ref = torch.from_numpy(reference.copy()).to(torch.float64)[None, None] / 255.0
    pred = torch.from_numpy(output.copy()).to(torch.float64)[None, None] / 255.0
    return float(psnr_y(ref, pred, border=border)), float(_ssim_y_tiled(reference, output, border=border))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--quant-dir", type=Path, default=DEFAULT_QUANT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--sample-goldens-per-sequence", type=int, default=1)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"Outputs must be saved under ignored .data/: {output_dir}") from exc
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing output: {output_dir}")
    if args.sample_goldens_per_sequence < 0:
        raise ValueError("sample-goldens-per-sequence cannot be negative")

    device_name = args.device
    if args.device == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    device = torch.device(device_name)
    torch.set_num_threads(4)

    model = FSRCNNSubpixel(ModelConfig())
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    fixed = FixedReference(args.quant_dir)

    output_dir.mkdir(parents=True)
    golden_dir = output_dir / "derived_4k_integer_golden"
    golden_dir.mkdir()
    rows: list[dict[str, str | int | float]] = []
    source_manifests: dict[str, str] = {}
    saved_per_sequence: dict[str, int] = {}

    for pairs_dir in args.pairs_dir:
        pairs_dir = pairs_dir.resolve()
        manifest_path = pairs_dir / "manifest.json"
        source_manifests[pairs_dir.name] = sha256(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest["pairs"]:
            frame_id = f"{pairs_dir.name}:{record['source_file']}"
            with np.load(pairs_dir / record["pair_file"], allow_pickle=False) as pair:
                lr_y = pair["lr_y"].copy()
                hr_y = pair["hr_y"].copy()
            if lr_y.dtype != np.uint8 or lr_y.shape != (540, 960):
                raise ValueError(f"Unexpected LR contract for {frame_id}: {lr_y.shape} {lr_y.dtype}")
            if hr_y.dtype != np.uint8 or hr_y.shape != (2160, 3840):
                raise ValueError(f"Unexpected HR contract for {frame_id}: {hr_y.shape} {hr_y.dtype}")

            tensor = torch.from_numpy(lr_y.copy()).to(device=device, dtype=torch.float32)[None, None] / 255.0
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            float_started = time.perf_counter_ns()
            with torch.inference_mode():
                float_mid = read_u8_prediction(model(tensor))
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            float_cnn_ms = (time.perf_counter_ns() - float_started) / 1e6

            int_started = time.perf_counter_ns()
            integer_mid = None
            for layer_name, values in fixed.iter_outputs(lr_y):
                if layer_name == "output":
                    integer_mid = values[:, :, 0].copy()
            integer_cnn_ms = (time.perf_counter_ns() - int_started) / 1e6
            if integer_mid is None:
                raise RuntimeError(f"Integer reference omitted output for {frame_id}")

            bicubic_started = time.perf_counter_ns()
            bicubic = resize_keys_u8(lr_y, scale=4, a=-0.5)
            bicubic_ms = (time.perf_counter_ns() - bicubic_started) / 1e6

            float_post = process_1080_frame(frame_id, float_mid)
            integer_post = process_1080_frame(frame_id, integer_mid)
            expected_shape = (2160, 3840)
            if any(value.shape != expected_shape for value in (float_post.y_u8, integer_post.y_u8, bicubic)):
                raise RuntimeError(f"4K shape mismatch for {frame_id}")

            outputs = {"bicubic": bicubic, "r0_fp32": float_post.y_u8, "r0_int": integer_post.y_u8}
            scores: dict[str, dict[str, tuple[float, float]]] = {"shave8": {}, "full": {}}
            for border_name, border in (("shave8", 8), ("full", 0)):
                for output_name, pixels in outputs.items():
                    scores[border_name][output_name] = metrics(hr_y, pixels, border)

            row: dict[str, str | int | float] = {
                "frame_id": frame_id,
                "sequence": pairs_dir.name,
                "source_file": str(record["source_file"]),
                "lr_sha256": hashlib.sha256(lr_y.tobytes()).hexdigest(),
                "hr_sha256": hashlib.sha256(hr_y.tobytes()).hexdigest(),
                "bicubic_4x_ms": bicubic_ms,
                "r0_fp32_cnn_ms": float_cnn_ms,
                "r0_int_cpu_cnn_ms": integer_cnn_ms,
                "r0_fp32_postprocess_ms": float_post.duration_ms,
                "r0_fp32_postprocess_started_monotonic_ns": float_post.started_monotonic_ns,
                "r0_fp32_postprocess_finished_monotonic_ns": float_post.finished_monotonic_ns,
                "r0_int_postprocess_ms": integer_post.duration_ms,
                "r0_int_postprocess_started_monotonic_ns": integer_post.started_monotonic_ns,
                "r0_int_postprocess_finished_monotonic_ns": integer_post.finished_monotonic_ns,
                "bicubic_y_psnr_db": scores["shave8"]["bicubic"][0],
                "r0_fp32_y_psnr_db": scores["shave8"]["r0_fp32"][0],
                "r0_int_y_psnr_db": scores["shave8"]["r0_int"][0],
                "bicubic_y_ssim": scores["shave8"]["bicubic"][1],
                "r0_fp32_y_ssim": scores["shave8"]["r0_fp32"][1],
                "r0_int_y_ssim": scores["shave8"]["r0_int"][1],
                "bicubic_psnr_full_db": scores["full"]["bicubic"][0],
                "r0_fp32_psnr_full_db": scores["full"]["r0_fp32"][0],
                "r0_int_psnr_full_db": scores["full"]["r0_int"][0],
                "bicubic_ssim_full": scores["full"]["bicubic"][1],
                "r0_fp32_ssim_full": scores["full"]["r0_fp32"][1],
                "r0_int_ssim_full": scores["full"]["r0_int"][1],
            }
            rows.append(row)

            used = saved_per_sequence.get(pairs_dir.name, 0)
            if used < args.sample_goldens_per_sequence:
                safe_sequence = "".join(c if c.isalnum() or c in "-_." else "_" for c in pairs_dir.name)
                golden_path = golden_dir / f"{safe_sequence}_{used:02d}_1920x1080_to_3840x2160_y_u8.bin"
                golden_path.write_bytes(integer_post.y_u8.tobytes())
                row["golden_4k_path"] = str(golden_path.relative_to(output_dir))
                row["golden_4k_sha256"] = sha256(golden_path)
                saved_per_sequence[pairs_dir.name] = used + 1

    csv_path = output_dir / "per_frame.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)

    metrics_keys = [key for key in rows[0] if "psnr" in key or "ssim" in key]
    timing_keys = [key for key in rows[0] if key.endswith("_ms")]
    summary = {
        "schema": "member-a-4k-frozen-r0-software-evaluation-v1",
        "status": "A_SIDE_PC_SOFTWARE_EVALUATION_NOT_BOARD_ACCEPTANCE",
        "dataset_scope": "paired decoded public 4K Y references with synthetic 4x bicubic LR degradation",
        "pairs": len(rows),
        "sequences": sorted(source_manifests),
        "pair_manifest_sha256": source_manifests,
        "frozen_checkpoint_sha256": sha256(args.checkpoint),
        "frozen_quant_params_sha256": sha256(args.quant_dir / "quant_params.json"),
        "integer_reference": "formal artifacts/quant; no recalibration or weight changes",
        "float_device": str(device),
        "postprocess": {
            "contract": "Keys cubic a=-0.5; half-pixel centers; edge replication; float64 separable accumulation; nearest ties away from zero; saturate to uint8",
            "input": "1920x1080 Y8, row-major",
            "output": "3840x2160 Y8, row-major, 8294400 bytes",
            "sample_integer_goldens_saved_per_sequence": args.sample_goldens_per_sequence,
        },
        "metric": "Y PSNR/SSIM against decoded 4K Y reference; center shave 8 reported separately from full frame; arithmetic mean by frame",
        "means": {key: statistics.fmean(float(row[key]) for row in rows) for key in metrics_keys},
        "mean_stage_ms": {key: statistics.fmean(float(row[key]) for row in rows) for key in timing_keys},
        "per_frame_csv": csv_path.name,
        "derived_golden_directory": golden_dir.name,
        "limitations": [
            "UVG source videos are lossy decoded references; LR was synthetically downsampled, so this is not camera-native ground truth.",
            "CPU/GPU reference results do not establish FPGA resources, timing, complete host-to-board latency, live preview, or sustained frame rate.",
            "PC bicubic details are specified by this software module; C must confirm the display/integration contract.",
        ],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
