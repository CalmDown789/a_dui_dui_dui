"""Benchmark complete A software paths on one fixed paired 4K sample."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.fixed_reference import FixedReference
from member_a.model import FSRCNNSubpixel, ModelConfig
from member_a.pc_postprocess_4k import process_1080_frame, resize_keys_u8


CHECKPOINT = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
QUANT = ROOT / "artifacts/quant"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def float_path(lr: np.ndarray, model: torch.nn.Module, device: torch.device) -> tuple[np.ndarray, float, float]:
    tensor = torch.from_numpy(lr.copy()).to(device=device, dtype=torch.float32)[None, None] / 255.0
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    cnn_start = time.perf_counter_ns()
    with torch.inference_mode():
        prediction = model(tensor)
        values = prediction.detach().to(device="cpu", dtype=torch.float64).numpy().squeeze() * 255.0
        middle = np.clip(np.copysign(np.floor(np.abs(values) + 0.5), values), 0, 255).astype(np.uint8)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    cnn_ms = (time.perf_counter_ns() - cnn_start) / 1e6
    post = process_1080_frame("benchmark", middle)
    return post.y_u8, cnn_ms, post.duration_ms


def percentile(values: list[float], fraction: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), fraction))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir", type=Path, required=True)
    parser.add_argument("--pair-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0 or args.pair_index < 0:
        raise ValueError("iterations must be positive; warmup/index cannot be negative")
    output = args.output.resolve()
    try:
        output.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError("Benchmark report must stay under ignored .data/") from exc
    if output.exists():
        raise FileExistsError(output)

    manifest_path = args.pairs_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["pairs"][args.pair_index]
    with np.load(args.pairs_dir / record["pair_file"], allow_pickle=False) as pair:
        lr = pair["lr_y"].copy()
    if lr.dtype != np.uint8 or lr.shape != (540, 960):
        raise ValueError("Benchmark input must be 960x540 uint8 Y")

    torch.set_num_threads(4)
    model = FSRCNNSubpixel(ModelConfig())
    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model.load_state_dict(state, strict=True)
    model.eval()

    paths: dict[str, dict[str, object]] = {}
    fp32_outputs: dict[str, np.ndarray] = {}
    devices = [torch.device("cpu")]
    if torch.cuda.is_available():
        devices.append(torch.device("cuda:0"))
    for device in devices:
        model.to(device)
        for _ in range(args.warmup):
            float_path(lr, model, device)
        elapsed_values: list[float] = []
        cnn_values: list[float] = []
        post_values: list[float] = []
        digest = ""
        for _ in range(args.iterations):
            started = time.perf_counter_ns()
            pixels, cnn_ms, post_ms = float_path(lr, model, device)
            elapsed_ms = (time.perf_counter_ns() - started) / 1e6
            elapsed_values.append(elapsed_ms)
            cnn_values.append(cnn_ms)
            post_values.append(post_ms)
            digest = hashlib.sha256(pixels.tobytes()).hexdigest()
        paths[f"fp32_{device.type}"] = {
            "model": "frozen R0 FSRCNN d16/s8/m1/c16 FP32",
            "full_540p_to_4k_ms_p50": statistics.median(elapsed_values),
            "full_540p_to_4k_ms_p90": percentile(elapsed_values, 90),
            "full_540p_to_4k_ms_mean": statistics.fmean(elapsed_values),
            "cnn_and_cpu_copy_ms_mean": statistics.fmean(cnn_values),
            "1080p_to_4k_postprocess_ms_mean": statistics.fmean(post_values),
            "output_sha256_last_iteration": digest,
            "fps_from_median_single_frame_only": 1000.0 / statistics.median(elapsed_values),
        }
        fp32_outputs[device.type] = pixels.copy()

    if "cpu" in fp32_outputs and "cuda" in fp32_outputs:
        delta = np.abs(fp32_outputs["cpu"].astype(np.int16) - fp32_outputs["cuda"].astype(np.int16))
        paths["fp32_cpu_vs_cuda_output_delta"] = {
            "changed_pixels": int(np.count_nonzero(delta)),
            "total_pixels": int(delta.size),
            "mean_absolute_difference_y": float(delta.mean()),
            "max_absolute_difference_y": int(delta.max()),
            "note": "Same FP32 checkpoint and input; small differences can arise from CPU/GPU floating-point accumulation order.",
        }

    fixed = FixedReference(QUANT)
    int_elapsed: list[float] = []
    int_cnn: list[float] = []
    int_post: list[float] = []
    int_digest = ""
    for _ in range(args.warmup + args.iterations):
        started = time.perf_counter_ns()
        mid = None
        cnn_started = time.perf_counter_ns()
        for layer, values in fixed.iter_outputs(lr):
            if layer == "output":
                mid = values[:, :, 0].copy()
        cnn_ms = (time.perf_counter_ns() - cnn_started) / 1e6
        if mid is None:
            raise RuntimeError("Frozen integer path omitted output")
        result = process_1080_frame("benchmark", mid)
        full_ms = (time.perf_counter_ns() - started) / 1e6
        if _ >= args.warmup:
            int_elapsed.append(full_ms)
            int_cnn.append(cnn_ms)
            int_post.append(result.duration_ms)
            int_digest = hashlib.sha256(result.y_u8.tobytes()).hexdigest()
    paths["integer_cpu"] = {
        "model": "frozen formal INT8/INT16/INT32 R0 FixedReference",
        "full_540p_to_4k_ms_p50": statistics.median(int_elapsed),
        "full_540p_to_4k_ms_p90": percentile(int_elapsed, 90),
        "full_540p_to_4k_ms_mean": statistics.fmean(int_elapsed),
        "integer_cnn_ms_mean": statistics.fmean(int_cnn),
        "1080p_to_4k_postprocess_ms_mean": statistics.fmean(int_post),
        "output_sha256_last_iteration": int_digest,
        "fps_from_median_single_frame_only": 1000.0 / statistics.median(int_elapsed),
    }

    cubic_elapsed: list[float] = []
    cubic_digest = ""
    for _ in range(args.warmup + args.iterations):
        started = time.perf_counter_ns()
        pixels = resize_keys_u8(lr, scale=4)
        elapsed_ms = (time.perf_counter_ns() - started) / 1e6
        if _ >= args.warmup:
            cubic_elapsed.append(elapsed_ms)
            cubic_digest = hashlib.sha256(pixels.tobytes()).hexdigest()
    paths["bicubic4x_cpu"] = {
        "model": "direct Keys bicubic x4 from 540p to 4K",
        "full_540p_to_4k_ms_p50": statistics.median(cubic_elapsed),
        "full_540p_to_4k_ms_p90": percentile(cubic_elapsed, 90),
        "full_540p_to_4k_ms_mean": statistics.fmean(cubic_elapsed),
        "output_sha256_last_iteration": cubic_digest,
        "fps_from_median_single_frame_only": 1000.0 / statistics.median(cubic_elapsed),
    }

    report = {
        "schema": "member-a-pc-path-benchmark-v1",
        "status": "LOCAL_SOFTWARE_ONLY_NOT_FPGA_OR_LIVE_PIPELINE",
        "sample": f"{args.pairs_dir.name}:{record['source_file']}",
        "input": "960x540 Y8 518400 bytes",
        "output": "3840x2160 Y8 8294400 bytes",
        "warmup": args.warmup,
        "iterations": args.iterations,
        "host": {"platform": __import__("platform").platform(), "torch": torch.__version__,
                 "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        "checkpoint_sha256": sha256(CHECKPOINT),
        "formal_quant_params_sha256": sha256(QUANT / "quant_params.json"),
        "pair_manifest_sha256": sha256(manifest_path),
        "measurement_boundary": "One complete in-memory 540p input to 4K Y8 output; includes model input tensor creation and host/device copies for FP32, plus CPU bicubic post-processing; excludes file/video/network I/O and display queue.",
        "paths": paths,
        "limits": ["Single-frame measurements are not sustained throughput or frame-pacing measurements.",
                   "CPU integer reference is algorithmically exact for A contract, but not optimized host software.",
                   "The synthetic FFmpeg LR sample comes from a lossy decoded UVG 4K reference."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
