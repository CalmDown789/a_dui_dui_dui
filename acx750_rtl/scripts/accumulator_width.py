#!/usr/bin/env python3
"""Conservative signed accumulator-width audit for convolution layers."""

from __future__ import annotations

import argparse


def required_signed_bits(
    act_width: int,
    weight_width: int,
    taps: int,
    channels: int,
    bias_width: int | None,
) -> tuple[int, int]:
    values = (act_width, weight_width, taps, channels)
    if any(value < 1 for value in values):
        raise ValueError("widths, taps, and channels must be positive")
    if bias_width is not None and bias_width < 1:
        raise ValueError("bias width must be positive when supplied")

    # Signed two's-complement extrema are asymmetric. abs(min) is the largest
    # magnitude, so this deliberately computes a safe bound rather than a
    # distribution-dependent estimate.
    max_product_magnitude = (1 << (act_width - 1)) * (1 << (weight_width - 1))
    max_sum_magnitude = max_product_magnitude * taps * channels
    if bias_width is not None:
        max_sum_magnitude += 1 << (bias_width - 1)

    return max_sum_magnitude, max_sum_magnitude.bit_length() + 1


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--act-width", type=int, required=True)
    parser.add_argument("--weight-width", type=int, required=True)
    parser.add_argument("--taps", type=int, required=True)
    parser.add_argument("--channels", type=int, required=True)
    parser.add_argument("--bias-width", type=int)
    parser.add_argument("--acc-width", type=int, default=32)
    return parser


def main() -> None:
    args = make_parser().parse_args()
    magnitude, required = required_signed_bits(
        args.act_width,
        args.weight_width,
        args.taps,
        args.channels,
        args.bias_width,
    )
    status = "SAFE_BY_BOUND" if args.acc_width >= required else "OVERFLOW_POSSIBLE"
    print(f"MAX_ABS_BOUND={magnitude}")
    print(f"REQUIRED_SIGNED_BITS={required}")
    print(f"CANDIDATE_ACC_WIDTH={args.acc_width}")
    print(f"STATUS={status}")


if __name__ == "__main__":
    main()
