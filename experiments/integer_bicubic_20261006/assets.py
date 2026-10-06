from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zlib

import numpy as np

from .integer_bicubic import COEFFICIENTS_Q14, Q14, Q28


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, int | str]:
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def contract_payload() -> dict:
    coefficients = COEFFICIENTS_Q14.astype(int).tolist()
    return {
        "schema": "member-a-keys-bicubic-fixed-x2-v1",
        "status": "A_SIDE_DRAFT_FOR_B_REVIEW",
        "purpose": "FSRCNN integer 1080p Y8 output to 4K Y8 by separable Keys bicubic x2",
        "source": {"width": 1920, "height": 1080, "channels": 1, "dtype": "uint8", "layout": "HWC_row_major"},
        "target": {"width": 3840, "height": 2160, "channels": 1, "dtype": "uint8", "layout": "HWC_row_major"},
        "scale": 2,
        "filter": {"family": "Keys cubic convolution", "a": "-1/2", "support": "|x| < 2", "separable": True},
        "coordinate": {
            "formula": "source_coordinate = (output_index + 0.5) / 2 - 0.5",
            "phase": "even output index samples at k-1/4; odd output index at k+1/4",
            "axis_order": ["horizontal", "vertical"],
        },
        "boundary": {"mode": "edge replication", "definition": "clamp each of four source tap indices to [0, source_size-1]"},
        "coefficients": {
            "format": "signed INT16 Q2.14",
            "fractional_bits": 14,
            "phase_order": ["even", "odd"],
            "tap_order": "increasing source index, four taps",
            "values": coefficients,
            "sum_per_phase": [Q14, Q14],
            "derived_from_exact_rational_keys_weights": True,
        },
        "arithmetic": {
            "horizontal": {
                "input": "unsigned Y8 [0,255]",
                "multiply": "unsigned Y8 times signed Q2.14 coefficient",
                "accumulator": "signed integer; no rounding, requantization or saturation",
                "retained_scale": "Q14",
                "minimum_safe_accumulator_bits_from_bound": 24,
                "maximum_absolute_bound": 4961280,
            },
            "vertical": {
                "input": "signed horizontal Q14",
                "accumulator": "signed integer; no intermediate rounding or saturation",
                "retained_scale": "Q28",
                "minimum_safe_accumulator_bits_from_bound": 38,
                "maximum_absolute_bound": 96526663680,
            },
            "final": {
                "operation": "round Q28 accumulator once by 2^28, then saturate to uint8 [0,255]",
                "rounding": "nearest, midpoint ties away from zero",
                "saturation": "clip to [0,255]",
            },
            "reference_accumulator": "signed INT64",
        },
        "range_proof": {
            "absolute_coefficient_sum_q14": 19456,
            "horizontal": "255 * 19456 = 4961280; signed 23-bit is insufficient and signed 24-bit is sufficient",
            "vertical": "255 * 19456 * 19456 = 96526663680; signed 37-bit is insufficient and signed 38-bit is sufficient",
            "boundary_tap_clamping_cannot_increase_the_sum_of_absolute_coefficients": True,
        },
        "interfaces": {
            "input": "contiguous row-major single-channel uint8 array",
            "horizontal_intermediate": "row-major signed int32 container holding exact Q14 integers; mathematical range needs 24 signed bits",
            "vertical_accumulator": "row-major signed int64 reference values at Q28; mathematical range needs 38 signed bits",
            "output": "contiguous row-major single-channel uint8 array",
        },
        "acceptance_boundary": "A-side software contract draft only. B must review the intermediate precision and rounding placement before RTL freezes this interface.",
    }


def write_coefficients(directory: Path) -> dict[str, dict[str, int | str]]:
    directory.mkdir(parents=True, exist_ok=True)
    q14 = COEFFICIENTS_Q14.astype("<i2", copy=False)
    np.save(directory / "coefficients_q14_int16.npy", q14, allow_pickle=False)
    (directory / "coefficients_q14_int16.bin").write_bytes(q14.tobytes(order="C"))
    values = COEFFICIENTS_Q14.astype(int).tolist()
    (directory / "coefficients_q14.json").write_text(
        json.dumps(
            {
                "schema": "member-a-bicubic-coefficients-q14-v1",
                "dtype": "signed_int16_little_endian",
                "shape": [2, 4],
                "phase_order": ["even", "odd"],
                "tap_order": "increasing source index",
                "values": values,
                "sum_per_phase": [Q14, Q14],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    hex_lines = [f"{int(value) & 0xFFFF:04x}" for value in COEFFICIENTS_Q14.reshape(-1)]
    (directory / "coefficients_q14.mem").write_text("\n".join(hex_lines) + "\n", encoding="ascii", newline="\n")
    (directory / "coefficients_q14.coe").write_text(
        "memory_initialization_radix=16;\n"
        "memory_initialization_vector=\n"
        + ",\n".join(hex_lines)
        + ";\n",
        encoding="ascii",
        newline="\n",
    )
    return {
        path.name: file_record(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }
