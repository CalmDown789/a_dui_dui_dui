from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics

import torch

from .candidate_models import HybridFSRCNN, PRESETS, mac_breakdown


def _parse_candidate(value: str) -> tuple[str, Path]:
    try:
        name, path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected VARIANT=CHECKPOINT") from exc
    if name not in PRESETS:
        raise argparse.ArgumentTypeError(f"Unsupported variant {name}")
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure isolated PyTorch CNN latency on the local GPU")
    parser.add_argument("--candidate", type=_parse_candidate, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    if args.warmup < 1 or args.iterations < 10:
        raise ValueError("Use at least one warmup and ten measured iterations")
    if not torch.cuda.is_available():
        raise RuntimeError("This benchmark requires CUDA; it is intended only for local relative comparison")

    repo_root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Benchmark results must be written under ignored .data/: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite benchmark result: {output}")

    torch.manual_seed(123)
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False
    device = torch.device("cuda:0")
    input_tensor = torch.rand(1, 1, 540, 960, device=device)
    rows: list[dict[str, object]] = []
    for variant, checkpoint_path in args.candidate:
        model = HybridFSRCNN(PRESETS[variant])
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
        model.load_state_dict(state, strict=True)
        model.to(device).eval()
        with torch.inference_mode():
            for _ in range(args.warmup):
                model(input_tensor)
            torch.cuda.synchronize()
            starts = [torch.cuda.Event(enable_timing=True) for _ in range(args.iterations)]
            ends = [torch.cuda.Event(enable_timing=True) for _ in range(args.iterations)]
            for start, end in zip(starts, ends, strict=True):
                start.record()
                model(input_tensor)
                end.record()
            torch.cuda.synchronize()
        timings = sorted(start.elapsed_time(end) for start, end in zip(starts, ends, strict=True))
        macs = mac_breakdown(PRESETS[variant])
        rows.append(
            {
                "variant": variant,
                "checkpoint": str(checkpoint_path.resolve()),
                "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
                "mac_per_frame": macs["mac_per_frame"],
                "mac_reduction_vs_r0_percent": (1 - macs["mac_per_frame"] / mac_breakdown(PRESETS["R0"])["mac_per_frame"]) * 100,
                "gpu_latency_ms_p50": statistics.median(timings),
                "gpu_latency_ms_p90": timings[min(len(timings) - 1, int(len(timings) * 0.9))],
                "gpu_latency_ms_mean": statistics.fmean(timings),
                "iterations": args.iterations,
            }
        )
        del model
        torch.cuda.empty_cache()

    report = {
        "schema": "member-a-local-cuda-cnn-benchmark-v1",
        "status": "LOCAL_PYTORCH_RELATIVE_LATENCY_ONLY_NOT_FPGA_THROUGHPUT",
        "device": torch.cuda.get_device_name(0),
        "input_shape_nchw": [1, 1, 540, 960],
        "warmup": args.warmup,
        "iterations": args.iterations,
        "notes": [
            "Measures the CNN only; excludes input transfer, bicubic post-processing, video IO, and host overhead.",
            "GPU time is not an estimate of ACX750 FPGA timing, DSP mapping, or sustained frame rate.",
            "cuDNN benchmark is enabled; use the same software/driver/GPU for comparisons.",
        ],
        "candidates": rows,
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
