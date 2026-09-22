#!/usr/bin/env python3
"""Generate deterministic signed test vectors for conv3x3_backend.

The widths and channel count here are regression settings only. They do not
describe or freeze the deployed network.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stimulus", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--groups", type=int, default=96)
    parser.add_argument("--channels", type=int, default=3)
    parser.add_argument("--seed", type=int, default=750200)
    return parser


def edge_vectors() -> list[tuple[list[int], list[int]]]:
    return [
        ([127] * 9, [127] * 9),
        ([-128] * 9, [127] * 9),
        ([-128] * 9, [-128] * 9),
        ([127, -128, 0, 1, -1, 64, -64, 126, -127],
         [-128, 127, 1, -1, 0, -64, 64, -127, 126]),
    ]


def main() -> None:
    args = make_parser().parse_args()
    if args.groups < 1 or args.channels < 1:
        raise ValueError("groups and channels must both be positive")

    rng = random.Random(args.seed)
    edges = edge_vectors()
    stimulus_lines: list[str] = []
    expected_lines: list[str] = []

    for group in range(args.groups):
        first_bias = rng.randint(-100_000, 100_000)
        accumulator = first_bias

        for channel in range(args.channels):
            if group < len(edges):
                x_values, k_values = edges[(group + channel) % len(edges)]
            else:
                x_values = [rng.randint(-128, 127) for _ in range(9)]
                k_values = [rng.randint(-128, 127) for _ in range(9)]

            # Later-channel bias values are deliberately unrelated. The RTL
            # contract is to sample bias only on the first channel of a group.
            bias = first_bias if channel == 0 else rng.randint(-100_000, 100_000)
            gap_cycles = rng.randint(0, 3)
            accumulator += sum(x * k for x, k in zip(x_values, k_values))
            fields = [gap_cycles, bias, *x_values, *k_values]
            stimulus_lines.append(" ".join(str(value) for value in fields))

        expected_lines.append(str(accumulator))

    args.stimulus.parent.mkdir(parents=True, exist_ok=True)
    args.expected.parent.mkdir(parents=True, exist_ok=True)
    args.stimulus.write_text("\n".join(stimulus_lines) + "\n", encoding="ascii")
    args.expected.write_text("\n".join(expected_lines) + "\n", encoding="ascii")
    print(
        f"generated groups={args.groups} channels={args.channels} "
        f"seed={args.seed} samples={len(stimulus_lines)}"
    )


if __name__ == "__main__":
    main()
