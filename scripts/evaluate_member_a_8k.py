"""Evaluate frozen A R0 software paths against one paired 8K Y8 frame.

No rendered outputs are written: only hashes, metrics, and stage timings are
recorded. Use --output below .data/ because the HHI sample is NC-ND licensed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.hybrid_4k_20261006.evaluate_hybrid import _ssim_y_tiled
from member_a.fixed_reference import FixedReference
from member_a.model import FSRCNNSubpixel, ModelConfig
from member_a.pc_postprocess_4k import resize_keys_u8


WIDTH_LR = 960
HEIGHT_LR = 540
WIDTH_8K = 7680
HEIGHT_8K = 4320
DEFAULT_CHECKPOINT = ROOT / "artifacts/model/fsrcnn_d16_s8_m1_c16_x2_fp32.pth"
DEFAULT_QUANT = ROOT / "artifacts/quant"


def sha256_bytes(data: bytes | bytearray | memoryview | np.ndarray) -> str:
    return hashlib.sha256(memoryview(data)).hexdigest()


def read_u8_prediction(tensor: torch.Tensor) -> np.ndarray:
    values = tensor.detach().to(device="cpu", dtype=torch.float64).numpy().squeeze() * 255.0
    rounded = np.copysign(np.floor(np.abs(values) + 0.5), values)
    return np.clip(rounded, 0, 255).astype(np.uint8)


def psnr_y8_tiled(reference: np.ndarray, candidate: np.ndarray, border: int) -> float:
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("PSNR inputs must be equal-shaped grayscale arrays")
    height, width = reference.shape
    if border < 0 or height <= 2 * border or width <= 2 * border:
        raise ValueError("Invalid PSNR crop border")
    squared_error = 0
    pixels = 0
    for start in range(border, height - border, 128):
        stop = min(start + 128, height - border)
        left = reference[start:stop, border : width - border].astype(np.int16)
        right = candidate[start:stop, border : width - border].astype(np.int16)
        difference = left.astype(np.int32) - right.astype(np.int32)
        squared_error += int(np.sum(difference * difference, dtype=np.int64))
        pixels += difference.size
    mse = squared_error / pixels
    return math.inf if mse == 0 else 10.0 * math.log10((255.0 * 255.0) / mse)


def score(reference: np.ndarray, candidate: np.ndarray, border: int) -> dict[str, float]:
    return {
        "psnr_db": psnr_y8_tiled(reference, candidate, border),
        "ssim": float(_ssim_y_tiled(reference, candidate, border=border, tile_rows=64)),
    }


def load_model(checkpoint_path: Path, device: torch.device) -> tuple[FSRCNNSubpixel, str]:
    model = FSRCNNSubpixel(ModelConfig())
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    return model, hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hr-y8", type=Path, required=True, help="Raw 7680x4320 Y8 target from local .data/")
    parser.add_argument("--lr-y8", type=Path, required=True, help="Raw 960x540 Y8 synthetic input from local .data/")
    parser.add_argument("--preparation-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--quant-dir", type=Path, default=DEFAULT_QUANT)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file under ignored .data/")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()

    output_path = args.output.resolve()
    try:
        output_path.relative_to(ROOT / ".data")
    except ValueError as exc:
        raise ValueError(f"The HHI-derived evaluation report must stay under ignored .data/: {output_path}") from exc
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite {output_path}")
    if args.device == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device_name = args.device
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    device = torch.device(device_name)
    torch.set_num_threads(4)

    lr_bytes = args.lr_y8.read_bytes()
    hr_bytes = args.hr_y8.read_bytes()
    if len(lr_bytes) != WIDTH_LR * HEIGHT_LR or len(hr_bytes) != WIDTH_8K * HEIGHT_8K:
        raise ValueError("Raw input sizes do not match the 960x540 and 7680x4320 Y8 contracts")
    lr_y = np.frombuffer(lr_bytes, dtype=np.uint8).reshape(HEIGHT_LR, WIDTH_LR)
    hr_y = np.frombuffer(hr_bytes, dtype=np.uint8).reshape(HEIGHT_8K, WIDTH_8K).copy()

    checkpoint_path = args.checkpoint.resolve()
    model, checkpoint_sha = load_model(checkpoint_path, device)
    quant_path = args.quant_dir.resolve()
    fixed = FixedReference(quant_path)

    tensor = torch.from_numpy(lr_y.copy()).to(device=device, dtype=torch.float32)[None, None] / 255.0
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    started = time.perf_counter_ns()
    with torch.inference_mode():
        fp32_mid = read_u8_prediction(model(tensor))
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    fp32_cnn_ms = (time.perf_counter_ns() - started) / 1e6
    if fp32_mid.shape != (1080, 1920):
        raise RuntimeError(f"Unexpected FP32 1080p shape: {fp32_mid.shape}")

    started = time.perf_counter_ns()
    integer_mid = None
    for layer_name, values in fixed.iter_outputs(lr_y):
        if layer_name == "output":
            integer_mid = values[:, :, 0].copy()
    integer_cnn_ms = (time.perf_counter_ns() - started) / 1e6
    if integer_mid is None or integer_mid.shape != (1080, 1920):
        raise RuntimeError("Integer reference did not produce a 1920x1080 Y8 output")

    timings: dict[str, dict[str, float]] = {}
    candidates: dict[str, np.ndarray] = {}
    for name, middle in (("r0_fp32", fp32_mid), ("r0_integer", integer_mid)):
        stage_start = time.perf_counter_ns()
        at_4k = resize_keys_u8(middle, scale=2, row_chunk=64)
        stage4k_ms = (time.perf_counter_ns() - stage_start) / 1e6
        if at_4k.shape != (2160, 3840):
            raise RuntimeError(f"Unexpected 4K intermediate shape for {name}: {at_4k.shape}")
        stage_start = time.perf_counter_ns()
        at_8k = resize_keys_u8(at_4k, scale=2, row_chunk=32)
        stage8k_ms = (time.perf_counter_ns() - stage_start) / 1e6
        candidates[name] = at_8k
        timings[name] = {"cnn_ms": fp32_cnn_ms if name == "r0_fp32" else integer_cnn_ms,
                         "1080p_to_4k_keys_x2_ms": stage4k_ms,
                         "4k_to_8k_keys_x2_ms": stage8k_ms}

    direct_started = time.perf_counter_ns()
    candidates["direct_bicubic_x8"] = resize_keys_u8(lr_y, scale=8, row_chunk=32)
    direct_ms = (time.perf_counter_ns() - direct_started) / 1e6
    timings["direct_bicubic_x8"] = {"total_ms": direct_ms}
    for name, image in candidates.items():
        if image.shape != (HEIGHT_8K, WIDTH_8K) or image.dtype != np.uint8 or image.nbytes != WIDTH_8K * HEIGHT_8K:
            raise RuntimeError(f"8K Y8 output contract failed for {name}")

    scores = {
        name: {"full": score(hr_y, image, border=0), "shave16": score(hr_y, image, border=16)}
        for name, image in candidates.items()
    }
    prep_manifest = json.loads(args.preparation_manifest.read_text(encoding="utf-8"))
    source = prep_manifest.get("source", {})
    report = {
        "schema": "member-a-8k-single-frame-software-study-v1",
        "status": "A_SIDE_SINGLE_FRAME_SOFTWARE_STUDY_NOT_BOARD_OR_VIDEO_ACCEPTANCE",
        "source_attribution": {
            "title": source.get("title"),
            "sequence_name": source.get("sequence_name"),
            "creator": source.get("creator"),
            "copyright": source.get("copyright"),
            "source_page": source.get("source_page"),
            "license": source.get("license"),
            "frame_index": source.get("frame_index"),
            "source_y_plane_sha256": source.get("source_y_plane_sha256"),
            "restriction": "No source or derived image is exported; this report contains metrics and hashes only.",
        },
        "pair": {
            "lr_path_local": str(args.lr_y8.resolve()),
            "lr_bytes": len(lr_bytes),
            "lr_sha256": sha256_bytes(lr_bytes),
            "hr_path_local": str(args.hr_y8.resolve()),
            "hr_bytes": len(hr_bytes),
            "hr_sha256": sha256_bytes(hr_bytes),
            "preparation_manifest_sha256": hashlib.sha256(args.preparation_manifest.read_bytes()).hexdigest(),
        },
        "model": {
            "version": "member-a-v1.0.1",
            "architecture": "d16/s8/m1/c16 FSRCNN with native dense 5x5 subpixel head",
            "checkpoint_sha256": checkpoint_sha,
            "quant_params_sha256": hashlib.sha256((quant_path / "quant_params.json").read_bytes()).hexdigest(),
            "device_for_fp32": str(device),
            "integer_reference": "formal artifacts/quant; no recalibration or weight changes",
        },
        "protocol": {
            "input": "960x540 full-range 8-bit Y; synthetic FFmpeg bicubic downsample from native 8K HHI SDR Y",
            "staged_path": "FSRCNN x2 to 1080p, Keys cubic x2 to 4K, then Keys cubic x2 to 8K",
            "direct_baseline": "Keys cubic x8 directly from 540p to 8K",
            "keys": "a=-0.5; half-pixel centers; edge replication; float64 separable; ties away from zero; uint8 saturation",
            "metrics": "Y PSNR/SSIM; peak 255; report full frame and shave-16 separately; SSIM 11x11 Gaussian sigma 1.5",
            "outputs": "No candidate image is written; output hashes are provided to support local reproducibility.",
        },
        "scores": scores,
        "output_sha256": {name: sha256_bytes(image) for name, image in candidates.items()},
        "stage_times_ms": timings,
        "limitations": [
            "Single selected native 8K frame; not a multi-frame, temporal-stability, or video-throughput evaluation.",
            "Synthetic 540p input uses one fixed FFmpeg bicubic downsample; results characterize this degradation only.",
            "The HHI source is CC BY-NC-ND; only aggregated metrics and hashes are reported, not source or derived images.",
            "Software reference only; no claim about FPGA resources, timing, bitstream, board output, or 8K real-time capability.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
