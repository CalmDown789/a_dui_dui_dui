"""Collect committed Vitis HLS estimates into one reproducible Markdown table."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HlsEstimate:
    name: str
    top: str
    estimated_period_ns: float
    bram: int
    dsp: int
    ff: int
    lut: int

    @property
    def estimated_fmax_mhz(self) -> float:
        return 1000.0 / self.estimated_period_ns


def parse_report(path: Path) -> HlsEstimate:
    text = path.read_text(encoding="utf-8", errors="replace")

    top_match = re.search(r"Vitis HLS Report for '([^']+)'", text)
    timing_match = re.search(
        r"\|ap_clk\s*\|\s*[0-9.]+ ns\|\s*([0-9.]+) ns\|", text
    )
    total_match = re.search(
        r"\|Total\s*\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|\s*(\d+)\|",
        text,
    )
    if top_match is None or timing_match is None or total_match is None:
        raise ValueError(f"unsupported or incomplete HLS report: {path}")

    bram, dsp, ff, lut = (int(value) for value in total_match.groups())
    return HlsEstimate(
        name=path.parent.name.removeprefix("hls_"),
        top=top_match.group(1),
        estimated_period_ns=float(timing_match.group(1)),
        bram=bram,
        dsp=dsp,
        ff=ff,
        lut=lut,
    )


def render_markdown(estimates: list[HlsEstimate]) -> str:
    lines = [
        "# HLS 阶段资源汇总",
        "",
        "目标器件均为 PYNQ-Z2 对应的 `xc7z020-clg400-1`，综合时钟约束均为 10 ns。",
        "",
        "| 阶段 | HLS 顶层 | 估算 Fmax (MHz) | BRAM_18K | DSP | FF | LUT |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for estimate in estimates:
        lines.append(
            f"| {estimate.name} | `{estimate.top}` | "
            f"{estimate.estimated_fmax_mhz:.2f} | {estimate.bram} | "
            f"{estimate.dsp} | {estimate.ff} | {estimate.lut} |"
        )

    lines.extend(
        [
            "",
            "注意：各行是不同功能边界的独立综合，不可相加为完整网络资源。",
            "`stage3` 是目前最接近可交付子系统的一行，包含末层卷积、后处理和 Pixel Shuffle；",
            "所有数据仍是 HLS 估算，不等于 Vivado 实现后的资源、WNS 或板上帧率。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = sorted(args.results.glob("hls_*/*_csynth.rpt"))
    if not reports:
        raise SystemExit(f"no HLS reports found under {args.results}")

    estimates = [parse_report(report) for report in reports]
    args.output.write_text(render_markdown(estimates), encoding="utf-8")
    print(f"HLS_SUMMARY_PASS reports={len(estimates)} output={args.output}")


if __name__ == "__main__":
    main()

