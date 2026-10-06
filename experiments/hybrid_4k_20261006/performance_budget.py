from __future__ import annotations

import argparse
import json
from pathlib import Path


WIDTHS = {
    "input_540p_y8": (960, 540, 1),
    "intermediate_1080p_y8": (1920, 1080, 1),
    "output_4k_y8": (3840, 2160, 1),
    "output_4k_yuv420_8bit": (3840, 2160, 1.5),
    "output_4k_rgb24": (3840, 2160, 3),
}


def calculate_budget(frame_rates: tuple[int, ...] = (30, 60)) -> dict[str, object]:
    if not frame_rates or any(rate <= 0 for rate in frame_rates):
        raise ValueError("At least one positive frame rate is required")
    streams: dict[str, dict[str, float | int]] = {}
    for name, (width, height, bytes_per_pixel) in WIDTHS.items():
        frame_bytes = int(width * height * bytes_per_pixel)
        streams[name] = {
            "width": width,
            "height": height,
            "bytes_per_frame": frame_bytes,
            "one_frame_buffer_MiB": frame_bytes / (1024**2),
            "double_buffer_MiB": 2 * frame_bytes / (1024**2),
        }

    traffic: dict[str, dict[str, float | int]] = {}
    input_bytes = int(WIDTHS["input_540p_y8"][0] * WIDTHS["input_540p_y8"][1])
    intermediate_bytes = int(WIDTHS["intermediate_1080p_y8"][0] * WIDTHS["intermediate_1080p_y8"][1])
    for fps in frame_rates:
        entry: dict[str, float | int] = {"fps": fps}
        for output_name in ("output_4k_y8", "output_4k_yuv420_8bit", "output_4k_rgb24"):
            output_bytes = streams[output_name]["bytes_per_frame"]
            endpoint = (input_bytes + output_bytes) * fps
            spill = (input_bytes + output_bytes + 2 * intermediate_bytes) * fps
            entry[f"endpoint_input_y_plus_{output_name}_MB_s"] = endpoint / 1_000_000
            entry[f"if_1080p_intermediate_spills_to_ddr_MB_s_{output_name}"] = spill / 1_000_000
        traffic[str(fps)] = entry

    return {
        "schema": "member-a-hybrid-video-bandwidth-budget-v1",
        "status": "ARITHMETIC_ESTIMATE_NOT_MEASURED_BOARD_DDR_TRAFFIC",
        "pipeline": "960x540 Y8 -> FSRCNN x2 -> 1920x1080 Y8 -> Keys bicubic x2 -> 3840x2160 output",
        "units": {"throughput": "decimal MB/s", "buffer": "MiB"},
        "assumptions": [
            "8-bit luma is 1 byte per pixel; 8-bit YUV 4:2:0 is 1.5 bytes per pixel; RGB24 is 3 bytes per pixel.",
            "Endpoint traffic counts one input read and one selected output write per frame.",
            "The spill case additionally counts one full 1080p Y write and one full 1080p Y read per frame.",
            "No protocol headers, burst inefficiency, refresh overhead, weight traffic, or display blanking are included.",
            "This is not a measurement of C RTL buffering, DDR transactions, or board throughput.",
        ],
        "streams": streams,
        "traffic_by_fps": traffic,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute ideal frame-buffer and endpoint bandwidth estimates")
    parser.add_argument("--fps", type=int, action="append", default=None, help="Frame rate to report; may be repeated")
    parser.add_argument("--output", type=Path, required=True, help="JSON output path under the ignored .data directory")
    args = parser.parse_args()

    output = args.output.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Budget output must stay under ignored .data/: {output}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    result = calculate_budget(tuple(args.fps or (30, 60)))
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
