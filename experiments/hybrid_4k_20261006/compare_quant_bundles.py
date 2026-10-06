from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


PACKAGE_CONTRACT_KEYS = (
    "schema_version",
    "model",
    "input",
    "hidden_activation",
    "weight",
    "bias_accumulator",
    "rounding",
    "prelu",
    "pixel_shuffle",
    "output",
)
LAYER_CONTRACT_KEYS = ("name", "type", "kernel", "padding", "weight_shape_oihw", "output_dtype")
NUMERIC_PARAMETER_KEYS = (
    "weight_scale_per_output",
    "input_scale",
    "output_scale",
    "bias_scale_per_output",
    "requant_multiplier_real",
    "requant_multiplier_q31",
    "prelu_q15",
)
BINARY_KEYS = (("weight_bin", np.dtype(np.int8)), ("bias_bin", np.dtype("<i4")), ("prelu_bin", np.dtype("<i2")))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _delta_summary(a: Any, b: Any) -> dict[str, Any]:
    if a is None or b is None:
        same_presence = a is None and b is None
        return {
            "same_shape": same_presence,
            "count": 0,
            "changed_count": 0 if same_presence else 1,
            "max_abs_delta": 0.0 if same_presence else None,
        }
    left = np.asarray(a, dtype=np.float64).reshape(-1)
    right = np.asarray(b, dtype=np.float64).reshape(-1)
    if left.shape != right.shape:
        return {"same_shape": False, "left_count": int(left.size), "right_count": int(right.size)}
    diff = np.abs(left - right)
    return {
        "same_shape": True,
        "count": int(left.size),
        "changed_count": int(np.count_nonzero(diff)),
        "max_abs_delta": float(diff.max(initial=0.0)),
    }


def compare_quant_bundles(baseline_dir: Path, candidate_dir: Path) -> dict[str, Any]:
    base_root = Path(baseline_dir)
    candidate_root = Path(candidate_dir)
    base_spec = json.loads((base_root / "quant_params.json").read_text(encoding="utf-8"))
    candidate_spec = json.loads((candidate_root / "quant_params.json").read_text(encoding="utf-8"))
    package_contract = {key: base_spec.get(key) == candidate_spec.get(key) for key in PACKAGE_CONTRACT_KEYS}
    base_layers = base_spec.get("layers", [])
    candidate_layers = candidate_spec.get("layers", [])
    if len(base_layers) != len(candidate_layers):
        raise ValueError(f"Layer count differs: {len(base_layers)} vs {len(candidate_layers)}")

    layers = []
    for base_layer, candidate_layer in zip(base_layers, candidate_layers, strict=True):
        name = base_layer.get("name", "unnamed")
        static_contract = {key: base_layer.get(key) == candidate_layer.get(key) for key in LAYER_CONTRACT_KEYS}
        numeric = {
            key: _delta_summary(base_layer.get(key), candidate_layer.get(key))
            for key in NUMERIC_PARAMETER_KEYS
        }
        binaries = {}
        for file_key, dtype in BINARY_KEYS:
            base_rel = base_layer.get("files", {}).get(file_key)
            candidate_rel = candidate_layer.get("files", {}).get(file_key)
            if base_rel is None and candidate_rel is None:
                continue
            if base_rel is None or candidate_rel is None:
                binaries[file_key] = {"same_file_presence": False}
                continue
            base_path = base_root / base_rel
            candidate_path = candidate_root / candidate_rel
            left = np.fromfile(base_path, dtype=dtype)
            right = np.fromfile(candidate_path, dtype=dtype)
            binaries[file_key] = {
                **_delta_summary(left, right),
                "baseline_sha256": _sha256(base_path),
                "candidate_sha256": _sha256(candidate_path),
            }
        layers.append({"name": name, "static_contract": static_contract, "numeric_parameter_deltas": numeric, "binary_tensor_deltas": binaries})

    layer_shapes_compatible = all(
        all(layer["static_contract"].values())
        and all(item.get("same_shape", True) and item.get("same_file_presence", True) for item in layer["numeric_parameter_deltas"].values())
        and all(item.get("same_shape", True) and item.get("same_file_presence", True) for item in layer["binary_tensor_deltas"].values())
        for layer in layers
    )
    shape_compatible = all(package_contract.values()) and layer_shapes_compatible
    return {
        "schema": "member-a-quant-candidate-compatibility-v1",
        "status": "SHAPE_CONTRACT_COMPATIBLE_NUMERIC_PARAMETERS_DIFFER" if shape_compatible else "INCOMPATIBLE_CONTRACT",
        "baseline_quant_dir": str(base_root.resolve()),
        "candidate_quant_dir": str(candidate_root.resolve()),
        "package_contract_equal": package_contract,
        "layer_array_shapes_compatible": layer_shapes_compatible,
        "shape_and_layer_contract_compatible": shape_compatible,
        "layers": layers,
        "integration_note": (
            "Matching shape/layout and quantization conventions do not make the candidate ROMs interchangeable. "
            "Use the candidate's complete weights, biases, PReLU coefficients, requantization multipliers, "
            "activation scales, test vectors, and integer Golden as one versioned set; do not mix with baseline ROMs."
            if shape_compatible
            else "Do not integrate until the package/layer contract mismatch is resolved."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a quantized candidate package against frozen A quantization assets")
    parser.add_argument("--baseline-quant-dir", type=Path, required=True)
    parser.add_argument("--candidate-quant-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="JSON output under ignored .data/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    try:
        output.relative_to(repo_root / ".data")
    except ValueError as exc:
        raise ValueError(f"Compatibility report must stay under ignored .data/: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing report: {output}")
    report = compare_quant_bundles(args.baseline_quant_dir, args.candidate_quant_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"], "shape_contract_compatible": report["shape_and_layer_contract_compatible"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
