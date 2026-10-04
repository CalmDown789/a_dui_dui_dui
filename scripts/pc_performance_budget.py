"""Calculate editable video/link budgets and optionally time a saved PC session."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_board_sequence import load_manifest  # noqa: E402
from received_frames import compare_received  # noqa: E402


PIXEL_FORMATS = {
    "Y8": (1, 1, "grayscale Y; current FPGA data contract"),
    "YUV420P": (3, 2, "hypothetical packed video transport format"),
    "RGB24": (3, 1, "hypothetical color/display format"),
}


def frame_bytes(width: int, height: int, fmt: str) -> int:
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError("Frame dimensions must be positive integers")
    if fmt not in PIXEL_FORMATS:
        raise ValueError(f"Unsupported pixel format: {fmt}")
    if fmt == "YUV420P" and (width % 2 or height % 2):
        raise ValueError("YUV420P requires even width and height")
    numerator, denominator, _ = PIXEL_FORMATS[fmt]
    size = width * height * numerator
    if size % denominator:
        raise ValueError("Pixel format does not produce an integral frame byte count")
    return size // denominator


def calculate_case(width: int, height: int, scale: int, fps: float, fmt: str,
                   baud: int, uart_bits_per_byte: int, ethernet_mbps: float) -> dict:
    if type(scale) is not int or scale <= 0:
        raise ValueError("Scale must be a positive integer")
    if not math.isfinite(fps) or fps <= 0 or baud <= 0 or uart_bits_per_byte <= 0:
        raise ValueError("FPS, baud and UART bits/byte must be positive")
    if not math.isfinite(ethernet_mbps) or ethernet_mbps <= 0:
        raise ValueError("Ethernet line rate must be positive")
    out_w, out_h = width * scale, height * scale
    in_frame = frame_bytes(width, height, fmt)
    out_frame = frame_bytes(out_w, out_h, fmt)
    in_bps, out_bps = in_frame * fps, out_frame * fps
    in_uart_s = (in_frame + 20) * uart_bits_per_byte / baud
    out_uart_s = out_frame * uart_bits_per_byte / baud
    stop_wait_s = in_uart_s + out_uart_s
    eth_bps = ethernet_mbps * 1_000_000
    # Conservative full-frame-buffer model: each frame is written once and read
    # once for both input and output. A streaming/line-buffer architecture can
    # require less external DDR traffic; this is not a measured MIG bandwidth.
    ddr_framebuffer_bps = 2 * (in_bps + out_bps)
    stream_output_bps = 2 * out_bps
    return {
        "input_width": width, "input_height": height,
        "output_width": out_w, "output_height": out_h,
        "scale": scale, "fps": fps, "pixel_format": fmt,
        "format_scope": PIXEL_FORMATS[fmt][2],
        "input_bytes_per_frame": in_frame,
        "output_bytes_per_frame": out_frame,
        "input_payload_MB_s": in_bps / 1_000_000,
        "output_payload_MB_s": out_bps / 1_000_000,
        "aggregate_payload_MB_s": (in_bps + out_bps) / 1_000_000,
        "aggregate_payload_Mbps": (in_bps + out_bps) * 8 / 1_000_000,
        "input_uart_wire_Mbps_8n1": in_bps * uart_bits_per_byte / 1_000_000,
        "output_uart_wire_Mbps_8n1": out_bps * uart_bits_per_byte / 1_000_000,
        "uart_input_seconds_per_frame_including_20B_header": in_uart_s,
        "uart_output_seconds_per_frame": out_uart_s,
        "uart_stop_and_wait_seconds_per_exchange": stop_wait_s,
        "uart_stop_and_wait_max_fps_ideal": 1 / stop_wait_s,
        "ethernet_rx_utilization_percent_raw_payload": 100 * in_bps * 8 / eth_bps,
        "ethernet_tx_utilization_percent_raw_payload": 100 * out_bps * 8 / eth_bps,
        "ethernet_bidirectional_ideal_input_frame_seconds": in_frame * 8 / eth_bps,
        "ethernet_bidirectional_ideal_output_frame_seconds": out_frame * 8 / eth_bps,
        "ddr_framebuffer_traffic_MB_s_write_and_read_input_and_output": ddr_framebuffer_bps / 1_000_000,
        "ddr_output_buffer_write_plus_display_read_MB_s": stream_output_bps / 1_000_000,
        "input_one_frame_buffer_MB": in_frame / 1_000_000,
        "output_one_frame_buffer_MB": out_frame / 1_000_000,
        "combined_one_pair_buffers_MB": (in_frame + out_frame) / 1_000_000,
        "combined_two_pair_buffers_MB": 2 * (in_frame + out_frame) / 1_000_000,
        "combined_three_pair_buffers_MB": 3 * (in_frame + out_frame) / 1_000_000,
        "display_active_rgb24_payload_Gbps": out_w * out_h * fps * 24 / 1_000_000_000,
        "assumptions": [
            "Decimal MB and Mbps; raw active pixels only.",
            "UART uses 8N1 (10 serial bits per byte) and a 20-byte prototype input header; no output header.",
            "UART exchange is sequential stop-and-wait; no computation, host scheduling, protocol gaps or retries included.",
            "Ethernet percentages are payload-only lower bounds against nominal line rate, not measured application throughput.",
            "DDR figures are traffic/storage estimates, not MIG or board measurements; burst, refresh, arbitration and intermediate tensors are excluded.",
            "RGB24 display rate excludes blanking, TMDS coding and link overhead.",
        ],
    }


def parse_stage_timings(session_dir: Path, playback_observed_seconds: float | None,
                        fps: float, comparison_manifest: Path | None = None) -> dict:
    received_path = session_dir / "received_manifest.json"
    received = json.loads(received_path.read_text(encoding="utf-8"))
    sends = [t.get("elapsed_seconds") for t in received.get("transmissions", [])
             if isinstance(t.get("elapsed_seconds"), (int, float))]
    waits, returns = [], []
    for frame in received.get("frames", []):
        first, last = frame.get("first_payload_read_offset_seconds"), frame.get("last_payload_read_offset_seconds")
        if isinstance(first, (int, float)) and isinstance(last, (int, float)) and last >= first:
            waits.append(float(first))
            returns.append(float(last - first))
    compare_seconds = None
    compare_status = None
    reference_path = comparison_manifest or (session_dir / "reference/manifest.json")
    if reference_path.is_file():
        start = time.perf_counter()
        report = compare_received(reference_path, received_path)
        compare_seconds = time.perf_counter() - start
        compare_status = report.get("status")
    fps_value = float(fps)
    received_count = int(received.get("frame_count", 0))
    nominal_playback = received_count / fps_value if received_count else None
    return {
        "source": str(received_path),
        "evidence_source": received.get("evidence_source"),
        "protocol_status": received.get("protocol_status", "NOT_RECORDED"),
        "capture_status": received.get("capture_status"),
        "frame_count": received_count,
        "host_send_seconds": sum(sends) if sends else None,
        "host_wait_to_first_payload_seconds_sum": sum(waits) if waits else None,
        "host_return_read_span_seconds_sum": sum(returns) if returns else None,
        "host_session_seconds": received.get("session_elapsed_seconds"),
        "local_byte_compare_seconds": compare_seconds,
        "local_byte_compare_status": compare_status,
        "playback_observed_seconds": playback_observed_seconds,
        "playback_nominal_seconds": nominal_playback,
        "playback_timing_basis": "operator_observed" if playback_observed_seconds is not None else "nominal_frames_divided_by_fps_only",
        "timing_caveat": "Wait/return use PC read-return timestamps; they do not isolate FPGA compute or UART pin timing. Simulation-session values are virtual/software values, not board measurements.",
    }


def render_markdown(cases: list[dict], stages: dict | None, args: argparse.Namespace) -> str:
    fps_label = ", ".join(f"{float(raw):g}" for raw in args.fps.split(","))
    lines = [
        "# PC 链路与存储带宽预算",
        "",
        f"参数：输入 {args.width}×{args.height}、×{args.scale} 输出、{fps_label} fps；UART {args.baud} bit/s，8N1。",
        "",
        "表中 MB/Mbps 均为十进制。Y8 是当前 A/B 数据合同；YUV420P/RGB24 是彩色视频链路的容量情景，不代表当前 FPGA 接口已支持。",
        "",
        "| 格式 | fps | 输入 MB/s | 输出 MB/s | 双向合计 Mbps | UART 输入 s/帧 | UART 输出 s/帧 | stop-wait s/帧 | 理想上限 fps | DDR 全帧读写 MB/s | 一对帧缓冲 MB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in cases:
        lines.append(
            f"| {item['pixel_format']} | {item['fps']:g} | {item['input_payload_MB_s']:.3f} | {item['output_payload_MB_s']:.3f} | {item['aggregate_payload_Mbps']:.3f} | {item['uart_input_seconds_per_frame_including_20B_header']:.3f} | {item['uart_output_seconds_per_frame']:.3f} | {item['uart_stop_and_wait_seconds_per_exchange']:.3f} | {item['uart_stop_and_wait_max_fps_ideal']:.4f} | {item['ddr_framebuffer_traffic_MB_s_write_and_read_input_and_output']:.3f} | {item['combined_one_pair_buffers_MB']:.3f} |"
        )
    lines += [
        "",
        "## 分段计时",
        "",
    ]
    if stages is None:
        lines += [
            "当前未给出已保存的 PC 收发会话，故发送、等待、回传和对拍的实测值留空；不要用理论带宽替代实测。",
            "播放时长按帧数/fps 计算，仅为名义媒体时长。",
        ]
    else:
        for label, key in (
            ("主机发送", "host_send_seconds"),
            ("等到首个回传字节（主机读返回）", "host_wait_to_first_payload_seconds_sum"),
            ("回传读返回跨度", "host_return_read_span_seconds_sum"),
            ("本机逐字节对拍", "local_byte_compare_seconds"),
            ("会话总耗时", "host_session_seconds"),
            ("用户实测播放", "playback_observed_seconds"),
            ("名义播放时长", "playback_nominal_seconds"),
        ):
            value = stages.get(key)
            lines.append(f"- {label}：{value:.6f} s" if isinstance(value, (int, float)) else f"- {label}：未提供/不可测")
        lines += ["", stages["timing_caveat"]]
    lines += [
        "",
        "## 解释边界",
        "",
        "- 921600 baud、8N1 下，仅传一个 1080p Y 输出帧约 22.5 s；540p 输入加 20 字节实验头约 5.625 s。当前 stop-and-wait 往返至少约 28.125 s/帧，不可能承载 30 fps。",
        "- 30 fps 灰度 Y8 的输入、输出、合计有效负载分别为 15.552、62.208、77.760 MB/s。千兆以太网在理想裸包下每方向所需约 124.416/497.664 Mb/s；应用效率和 UDP 协议仍需实测/冻结。",
        "- DDR 表是假设输入帧和输出帧各写入并读出一次的带宽上界式预算。流式行缓存可以降低输入帧外存流量；最终要依据 C 的真实读写调度与帧缓存策略核算。",
        "- RGB24 显示数值是活动像素量，不是 HDMI TMDS 时钟、布线速率或接口通过结论。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--fps", default="15,30,60", help="Comma-separated frame rates")
    parser.add_argument("--formats", default="Y8,YUV420P,RGB24", help="Comma-separated pixel formats")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--uart-bits-per-byte", type=int, default=10)
    parser.add_argument("--ethernet-mbps", type=float, default=1000)
    parser.add_argument("--session-dir", type=Path, help="Saved PC receive session to split send/wait/return timing")
    parser.add_argument("--reference-manifest", type=Path, help="Optional Golden manifest; defaults to session_dir/reference/manifest.json")
    parser.add_argument("--playback-observed-seconds", type=float,
                        help="Optional manual stopwatch value; otherwise only nominal duration is reported")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="New output directory; use a D: path and do not overwrite existing results")
    args = parser.parse_args()
    try:
        fps_values = [float(raw) for raw in args.fps.split(",")]
        formats = [raw.strip().upper() for raw in args.formats.split(",")]
        if not fps_values or not formats:
            raise ValueError("At least one FPS and format are required")
        if args.playback_observed_seconds is not None and args.playback_observed_seconds < 0:
            raise ValueError("Observed playback duration must be nonnegative")
        cases = [calculate_case(args.width, args.height, args.scale, fps, fmt, args.baud,
                                args.uart_bits_per_byte, args.ethernet_mbps)
                 for fmt in formats for fps in fps_values]
        stages = parse_stage_timings(args.session_dir, args.playback_observed_seconds,
                                     fps_values[0], args.reference_manifest) if args.session_dir else None
        output = args.out_dir.resolve()
        if not output.is_relative_to(Path("D:/Codex File/dialogue file").resolve()):
            raise ValueError("Generated budget artifacts must remain under D:/Codex File/dialogue file")
        if output.exists():
            raise ValueError(f"Refusing to overwrite existing output directory: {output}")
        output.mkdir(parents=True, exist_ok=False)
        report = {
            "schema": "member-a-pc-performance-budget-v1",
            "status": "ESTIMATE_ONLY" if stages is None else "BUDGET_PLUS_HOST_SESSION_ANALYSIS",
            "input_parameters": {"width": args.width, "height": args.height, "scale": args.scale,
                                 "fps": fps_values, "formats": formats, "baud": args.baud,
                                 "uart_bits_per_byte": args.uart_bits_per_byte,
                                 "ethernet_mbps": args.ethernet_mbps},
            "cases": cases,
            "stage_timings": stages,
            "board_throughput_verified": False,
            "ethernet_protocol_frozen": False,
            "ddr_bandwidth_measured": False,
        }
        (output / "pc_performance_budget.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        with (output / "pc_bandwidth_budget.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "pixel_format", "fps", "input_bytes_per_frame", "output_bytes_per_frame",
                "input_payload_MB_s", "output_payload_MB_s", "aggregate_payload_Mbps",
                "uart_input_seconds_per_frame_including_20B_header", "uart_output_seconds_per_frame",
                "uart_stop_and_wait_seconds_per_exchange", "uart_stop_and_wait_max_fps_ideal",
                "ethernet_rx_utilization_percent_raw_payload", "ethernet_tx_utilization_percent_raw_payload",
                "ddr_framebuffer_traffic_MB_s_write_and_read_input_and_output",
                "input_one_frame_buffer_MB", "output_one_frame_buffer_MB",
                "combined_one_pair_buffers_MB", "combined_two_pair_buffers_MB", "combined_three_pair_buffers_MB",
                "display_active_rgb24_payload_Gbps",
            ])
            writer.writeheader()
            for case in cases:
                writer.writerow({key: case[key] for key in writer.fieldnames})
        (output / "pc_performance_budget.md").write_text(render_markdown(cases, stages, args), encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": report["status"], "cases": len(cases), "output_dir": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
