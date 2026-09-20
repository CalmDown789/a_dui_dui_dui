from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from sr_reference import conv2d_int32


def format_nested(array: np.ndarray, indent: int = 0) -> str:
    if array.ndim == 1:
        return "{" + ", ".join(str(int(value)) for value in array) + "}"
    prefix = " " * indent
    children = [format_nested(child, indent + 4) for child in array]
    separator = ",\n" + " " * (indent + 4)
    return "{\n" + " " * (indent + 4) + separator.join(children) + "\n" + prefix + "}"


def write_header(
    path: Path,
    activations: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
    expected: np.ndarray,
) -> None:
    text = f"""#ifndef LAYER_VECTOR_HPP
#define LAYER_VECTOR_HPP

#include <cstdint>

namespace layer_vector {{

constexpr int ROWS = {activations.shape[0]};
constexpr int COLS = {activations.shape[1]};
constexpr int INPUT_CHANNELS = {activations.shape[2]};
constexpr int OUTPUT_CHANNELS = {weights.shape[0]};
constexpr int OUTPUT_ROWS = {expected.shape[0]};
constexpr int OUTPUT_COLS = {expected.shape[1]};

constexpr std::int8_t INPUT[ROWS][COLS][INPUT_CHANNELS] =
    {format_nested(activations, 4)};

constexpr std::int8_t WEIGHTS[OUTPUT_CHANNELS][INPUT_CHANNELS][3][3] =
    {format_nested(weights, 4)};

constexpr std::int32_t BIAS[OUTPUT_CHANNELS] =
    {format_nested(bias, 4)};

constexpr std::int32_t EXPECTED[OUTPUT_ROWS][OUTPUT_COLS][OUTPUT_CHANNELS] =
    {format_nested(expected, 4)};

}}  // namespace layer_vector

#endif
"""
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    activations = np.empty((4, 5, 2), dtype=np.int8)
    activations[:, :, 0] = np.arange(1, 21, dtype=np.int8).reshape(4, 5)
    activations[:, :, 1] = 2

    weights = np.zeros((3, 2, 3, 3), dtype=np.int8)
    weights[0, 0, :, :] = 1
    weights[0, 1, :, :] = -1
    weights[1, 0, :, :] = -1
    weights[1, 1, :, :] = 1
    bias = np.array([7, -3, 42], dtype=np.int32)
    expected = conv2d_int32(activations, weights, bias, padding="valid")

    activations.tofile(output_dir / "input_hwc_i8.bin")
    weights.tofile(output_dir / "weights_oihw_i8.bin")
    bias.astype("<i4").tofile(output_dir / "bias_i32_le.bin")
    expected.astype("<i4").tofile(output_dir / "expected_hwc_i32_le.bin")
    write_header(output_dir / "layer_vector.hpp", activations, weights, bias, expected)

    manifest = {
        "name": "layer_smoke_v1",
        "padding": "valid",
        "input": {
            "file": "input_hwc_i8.bin",
            "dtype": "int8",
            "layout": "HWC",
            "shape": list(activations.shape),
        },
        "weights": {
            "file": "weights_oihw_i8.bin",
            "dtype": "int8",
            "layout": "OIHW",
            "shape": list(weights.shape),
        },
        "bias": {
            "file": "bias_i32_le.bin",
            "dtype": "int32_le",
            "shape": list(bias.shape),
        },
        "expected": {
            "file": "expected_hwc_i32_le.bin",
            "dtype": "int32_le",
            "layout": "HWC",
            "shape": list(expected.shape),
        },
        "stream_order": {
            "input": "row,column,input_channel",
            "output": "row,column,output_channel",
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        "LAYER_VECTOR_GENERATED "
        f"input={activations.shape} weights={weights.shape} output={expected.shape}"
    )


if __name__ == "__main__":
    main()
