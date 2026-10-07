from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zlib

import numpy as np

from .candidate_bundle_paths import resolve_candidate_bundle_root
from member_a.fixed_reference import FixedReference


def _verify_model_contract(spec: dict[str, object]) -> None:
    expected_layers = [
        ("feature", [5, 5], [2, 2], [16, 1, 5, 5], "int16", True),
        ("shrink", [1, 1], [0, 0], [8, 16, 1, 1], "int16", True),
        ("mapping0", [3, 3], [1, 1], [8, 8, 3, 3], "int16", True),
        ("expand", [1, 1], [0, 0], [16, 8, 1, 1], "int16", True),
        ("subpixel", [5, 5], [2, 2], [4, 16, 5, 5], "uint8", False),
    ]
    if spec.get("model") != "FSRCNNSubpixel-d16-s8-m1-c16-x2":
        raise AssertionError(f"Unexpected candidate model: {spec.get('model')!r}")
    if spec.get("input") != {
        "dtype": "uint8",
        "shape_hwc": [540, 960, 1],
        "scale": 1.0 / 255.0,
        "zero_point": 0,
        "layout": "HWC_row_major",
    }:
        raise AssertionError("Candidate input contract differs from 960x540 uint8 Y")
    if spec.get("hidden_activation") != {
        "dtype": "int16",
        "quantization": "symmetric_per_tensor",
        "zero_point": 0,
    }:
        raise AssertionError("Candidate hidden-activation contract is not symmetric INT16")
    weight = spec.get("weight")
    if (
        not isinstance(weight, dict)
        or weight.get("dtype") != "int8"
        or weight.get("layout") != "OIHW"
    ):
        raise AssertionError("Candidate weights must be INT8 OIHW")
    if spec.get("bias_accumulator") != {"dtype": "int32", "overflow": "saturate"}:
        raise AssertionError("Candidate bias/accumulator contract is not saturating INT32")
    if spec.get("rounding") != "nearest_ties_away_from_zero":
        raise AssertionError("Candidate rounding contract is unexpected")
    if spec.get("prelu") != "per_channel_Q1.15_before_requantization":
        raise AssertionError("Candidate PReLU contract is unexpected")
    if spec.get("pixel_shuffle") != {
        "scale": 2,
        "channel_order": ["top_left", "top_right", "bottom_left", "bottom_right"],
    }:
        raise AssertionError("Candidate PixelShuffle phase contract is unexpected")
    if spec.get("output") != {
        "dtype": "uint8",
        "shape_hwc": [1080, 1920, 1],
        "scale": 1.0 / 255.0,
        "zero_point": 0,
    }:
        raise AssertionError("Candidate output contract differs from 1920x1080 uint8 Y")

    layers = spec.get("layers")
    if not isinstance(layers, list) or len(layers) != len(expected_layers):
        raise AssertionError(f"Candidate must have exactly {len(expected_layers)} layers")
    for layer, (name, kernel, padding, weight_shape, output_dtype, has_prelu) in zip(
        layers, expected_layers
    ):
        if not isinstance(layer, dict):
            raise AssertionError(f"Candidate layer entry is not an object: {layer!r}")
        actual = (
            layer.get("name"),
            layer.get("type"),
            layer.get("kernel"),
            layer.get("padding"),
            layer.get("weight_shape_oihw"),
            layer.get("output_dtype"),
        )
        if actual != (name, "conv2d", kernel, padding, weight_shape, output_dtype):
            raise AssertionError(f"Candidate layer contract mismatch for {name}: {actual}")
        files = layer.get("files")
        tensor_names = ("weight", "bias", "prelu") if has_prelu else ("weight", "bias")
        expected_file_keys = {
            f"{tensor_name}_{view}"
            for tensor_name in tensor_names
            for view in ("npy", "bin", "mem", "coe")
        }
        if not isinstance(files, dict) or set(files) != expected_file_keys:
            raise AssertionError(f"Candidate tensor file set mismatch for {name}")


def _digest(path: Path) -> dict[str, str | int]:
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _verify_manifest_coverage(bundle_root: Path, manifest: dict[str, object]) -> None:
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        raise AssertionError("Bundle manifest 'files' must be an object")
    actual = {
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file() and path.name != "bundle_manifest.json"
    }
    declared_paths = set(declared)
    if actual != declared_paths:
        unlisted = sorted(actual - declared_paths)
        missing = sorted(declared_paths - actual)
        raise AssertionError(
            f"Bundle manifest coverage mismatch: unlisted={unlisted}, missing={missing}"
        )


def _stage_metadata(values: np.ndarray) -> dict[str, object]:
    array = np.ascontiguousarray(values)
    raw = array.tobytes(order="C")
    return {
        "shape_hwc": list(array.shape),
        "dtype": array.dtype.name,
        "layout": "HWC_row_major",
        "minimum": int(array.min()),
        "maximum": int(array.max()),
        "bytes": len(raw),
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _hex_words(values: np.ndarray, bits: int) -> list[str]:
    mask = (1 << bits) - 1
    width = bits // 4
    return [f"{int(value) & mask:0{width}X}" for value in np.asarray(values).reshape(-1)]


def _coe_words(path: Path) -> list[str]:
    text = path.read_text(encoding="ascii")
    marker = "memory_initialization_vector="
    if marker not in text:
        raise AssertionError(f"Missing COE initialization vector: {path}")
    header, body = text.split(marker, 1)
    if "memory_initialization_radix=16;" not in header.lower():
        raise AssertionError(f"COE radix is not 16: {path}")
    body = body.strip()
    if not body.endswith(";"):
        raise AssertionError(f"COE vector is missing its terminator: {path}")
    return [word.strip().upper() for word in body[:-1].split(",")]


def _verify_quant_export_views(bundle_root: Path) -> tuple[int, int]:
    quant_root = bundle_root / "quant"
    spec = json.loads((quant_root / "quant_params.json").read_text(encoding="utf-8"))
    _verify_model_contract(spec)
    dtype_by_tensor = {
        "weight": (8, np.dtype(np.int8)),
        "bias": (32, np.dtype("<i4")),
        "prelu": (16, np.dtype("<i2")),
    }
    tensor_count = 0
    file_view_count = 0
    for layer in spec["layers"]:
        files = layer["files"]
        output_channels = layer["weight_shape_oihw"][0]
        for metadata_key in (
            "weight_scale_per_output",
            "bias_scale_per_output",
            "requant_multiplier_real",
            "requant_multiplier_q31",
        ):
            if len(layer.get(metadata_key, [])) != output_channels:
                raise AssertionError(
                    f"{layer['name']} {metadata_key} length differs from output channels"
                )
        if layer["output_dtype"] == "int16" and len(layer.get("prelu_q15", [])) != output_channels:
            raise AssertionError(
                f"{layer['name']} PReLU metadata length differs from output channels"
            )
        for tensor_name, (bits, expected_dtype) in dtype_by_tensor.items():
            npy_key = f"{tensor_name}_npy"
            if npy_key not in files:
                if tensor_name == "prelu" and layer["output_dtype"] == "uint8":
                    continue
                raise AssertionError(f"{layer['name']} is missing required {tensor_name} tensor")
            array = np.load(quant_root / files[npy_key], allow_pickle=False)
            if array.dtype != expected_dtype:
                raise AssertionError(
                    f"{layer['name']} {tensor_name}: expected {expected_dtype}, got {array.dtype}"
                )
            expected_shape = (
                layer["weight_shape_oihw"]
                if tensor_name == "weight"
                else [output_channels]
            )
            if list(array.shape) != expected_shape:
                raise AssertionError(
                    f"{layer['name']} {tensor_name}: expected shape {expected_shape}, got {list(array.shape)}"
                )
            if tensor_name == "prelu" and array.tolist() != layer.get("prelu_q15"):
                raise AssertionError(f"{layer['name']} PReLU array differs from quant_params.json")
            contiguous = np.ascontiguousarray(array)
            raw_path = quant_root / files[f"{tensor_name}_bin"]
            if raw_path.read_bytes() != contiguous.tobytes(order="C"):
                raise AssertionError(f"{layer['name']} {tensor_name}: .bin differs from .npy")
            expected_words = _hex_words(contiguous, bits)
            mem_words = [
                line.strip().upper()
                for line in (quant_root / files[f"{tensor_name}_mem"])
                .read_text(encoding="ascii")
                .splitlines()
                if line.strip()
            ]
            if mem_words != expected_words:
                raise AssertionError(f"{layer['name']} {tensor_name}: .mem differs from .npy")
            coe_words = _coe_words(quant_root / files[f"{tensor_name}_coe"])
            if coe_words != expected_words:
                raise AssertionError(f"{layer['name']} {tensor_name}: .coe differs from .npy")
            tensor_count += 1
            file_view_count += 4
    return tensor_count, file_view_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify candidate file digests and exact integer vectors/Golden")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-published",
        action="store_true",
        help="allow bundles under experiments/hybrid_4k_20261006/candidate_delivery",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    root = resolve_candidate_bundle_root(
        args.bundle_dir, repo_root, allow_published=args.allow_published
    )

    bundle_manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    _verify_manifest_coverage(root, bundle_manifest)
    checked_files = 0
    for relative, expected in bundle_manifest["files"].items():
        actual = _digest(root / relative)
        if actual != expected:
            raise AssertionError(f"Bundle digest mismatch: {relative}")
        checked_files += 1

    checked_export_tensors, checked_export_files = _verify_quant_export_views(root)
    reference = FixedReference(root / "quant")
    vectors_root = root / "test_vectors"
    vector_count = 0
    for case_dir in sorted(path for path in vectors_root.iterdir() if path.is_dir()):
        input_bytes = (case_dir / "input_y_u8.bin").read_bytes()
        input_image = np.frombuffer(input_bytes, dtype=np.uint8).reshape(54, 96)
        for name, values in reference.iter_outputs(input_image):
            output_path = case_dir / f"{name}_hwc_{values.dtype.name}.bin"
            if output_path.read_bytes() != np.ascontiguousarray(values).tobytes(order="C"):
                raise AssertionError(f"Integer vector mismatch: {case_dir.name}/{output_path.name}")
            vector_count += 1

    golden_root = root / "full_integer_candidate_gold" / "full_integer_golden"
    golden_manifest = json.loads((golden_root / "manifest.json").read_text(encoding="utf-8"))
    full_input = np.fromfile(golden_root / "input_960x540_y_u8.bin", dtype=np.uint8).reshape(540, 960)
    stage_count = 0
    for name, values in reference.iter_outputs(full_input):
        if _stage_metadata(values) != golden_manifest["stage_digests"][name]:
            raise AssertionError(f"Full-frame stage mismatch: {name}")
        stage_count += 1

    print(json.dumps({
        "status": "PASS_EXPERIMENTAL_CANDIDATE_BUNDLE_INTEGRITY_AND_INTEGER_REFERENCE",
        "checked_package_files": checked_files,
        "checked_quant_tensors": checked_export_tensors,
        "checked_quant_export_views": checked_export_files,
        "checked_vector_stages": vector_count,
        "checked_full_frame_stages": stage_count,
        "limitations": "This validates A-side files and Python integer reference only; not B RTL, synthesis, FPGA, or board.",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
