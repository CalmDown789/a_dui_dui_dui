#!/usr/bin/env python3
"""Arithmetic-only throughput budget for the frozen d16/s8/m1/c16 model."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Layer:
    name: str
    in_channels: int
    out_channels: int
    kernel: int

    def macs(self, width: int, height: int) -> int:
        return (
            width
            * height
            * self.in_channels
            * self.out_channels
            * self.kernel
            * self.kernel
        )


LAYERS = (
    Layer("feature", 1, 16, 5),
    Layer("shrinking", 16, 8, 1),
    Layer("mapping0", 8, 8, 3),
    Layer("expanding", 8, 16, 1),
    Layer("subpixel", 16, 4, 5),
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--width", type=int, default=960)
    result.add_argument("--height", type=int, default=540)
    result.add_argument("--fps", type=float, default=30.0)
    result.add_argument("--clock-mhz", type=float, required=True)
    result.add_argument("--dsps", type=int, default=740)
    result.add_argument("--macs-per-dsp-cycle", type=float, default=1.0)
    result.add_argument(
        "--assumed-efficiency",
        type=float,
        default=1.0,
        help="fraction in (0,1], used only for a sensitivity calculation",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    if args.width < 1 or args.height < 1 or args.fps <= 0:
        raise ValueError("frame dimensions and fps must be positive")
    if args.clock_mhz <= 0 or args.dsps < 1 or args.macs_per_dsp_cycle <= 0:
        raise ValueError("clock, DSP count, and MAC rate must be positive")
    if not 0 < args.assumed_efficiency <= 1:
        raise ValueError("assumed efficiency must be in (0,1]")

    layer_macs = [(layer.name, layer.macs(args.width, args.height)) for layer in LAYERS]
    total_macs = sum(value for _, value in layer_macs)
    clock_hz = args.clock_mhz * 1e6
    required_macs_per_second = total_macs * args.fps
    peak_macs_per_second = args.dsps * clock_hz * args.macs_per_dsp_cycle
    effective_supply = peak_macs_per_second * args.assumed_efficiency
    required_peak_fraction = required_macs_per_second / peak_macs_per_second
    required_average_dsps = required_macs_per_second / (
        clock_hz * args.macs_per_dsp_cycle
    )
    ideal_cycles_per_frame = total_macs / (
        args.dsps * args.macs_per_dsp_cycle
    )
    deadline_cycles = clock_hz / args.fps

    for name, value in layer_macs:
        print(f"LAYER_{name.upper()}_MACS={value}")
    print(f"TOTAL_MACS_PER_FRAME={total_macs}")
    print(f"REQUIRED_GMAC_PER_SECOND={required_macs_per_second / 1e9:.6f}")
    print(f"RAW_PEAK_GMAC_PER_SECOND={peak_macs_per_second / 1e9:.6f}")
    print(f"ASSUMED_EFFECTIVE_GMAC_PER_SECOND={effective_supply / 1e9:.6f}")
    print(f"REQUIRED_RAW_PEAK_FRACTION={required_peak_fraction:.6f}")
    print(f"REQUIRED_AVERAGE_DSPS={required_average_dsps:.3f}")
    print(f"IDEAL_CYCLES_PER_FRAME={ideal_cycles_per_frame:.3f}")
    print(f"DEADLINE_CYCLES_PER_FRAME={deadline_cycles:.3f}")
    print(
        "ARITHMETIC_BUDGET_STATUS="
        + ("PASS" if effective_supply >= required_macs_per_second else "FAIL")
    )
    print("NOTE=Arithmetic-only upper bound; memory, bubbles, padding, and control are excluded")


if __name__ == "__main__":
    main()
