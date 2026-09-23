from __future__ import annotations

from pathlib import Path
import csv
import hashlib
import json
import zlib

import numpy as np
from PIL import Image
import torch

from .data import procedural_u8
from .fixed_reference import FixedReference
from .model import FSRCNNSubpixel, mac_breakdown
from .quantization import quantized_forward_float


TEXT_SUFFIXES = {".coe", ".csv", ".json", ".md", ".mem", ".py", ".toml", ".txt"}


def _digest(path: Path, normalize_text: bool = False) -> dict[str, str | int]:
    data = path.read_bytes()
    normalized = normalize_text and (path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitattributes", ".gitignore"})
    if normalized:
        data = data.replace(b"\r\n", b"\n")
    result: dict[str, str | int] = {
        "bytes": len(data),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if normalized:
        result["normalization"] = "lf"
    return result


def write_model_contract(model: FSRCNNSubpixel, output_dir: Path) -> None:
    contract = {
        "name": "FSRCNNSubpixel-d16-s8-m1-c16-x2",
        "architecture_note": "FSRCNN trunk with a native dense 5x5 16-to-4 subpixel head; not a weight-equivalent 9x9 transposed convolution",
        "config": model.config.to_dict(),
        "input": {"shape_nchw": [1, 1, 540, 960], "dtype": "uint8_Y", "normalized_range": [0.0, 1.0]},
        "output": {"shape_nchw": [1, 1, 1080, 1920], "dtype": "uint8_Y", "normalized_range": [0.0, 1.0]},
        "pixel_shuffle_channel_order": ["top_left", "top_right", "bottom_left", "bottom_right"],
        "macs": mac_breakdown(model.config),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model_contract.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")


def _vector_inputs(width: int = 96, height: int = 54) -> dict[str, np.ndarray]:
    zero = np.zeros((height, width), dtype=np.uint8)
    impulse = zero.copy()
    impulse[height // 2, width // 2] = 255
    ramp = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    random = np.random.default_rng(123).integers(0, 256, size=(height, width), dtype=np.uint8)
    return {"zero": zero, "impulse": impulse, "ramp": ramp, "random": random}


def generate_fixed_vectors(quant_dir: Path, vectors_dir: Path) -> None:
    reference = FixedReference(quant_dir)
    for case, image in _vector_inputs().items():
        case_dir = vectors_dir / case
        case_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(image, mode="L").save(case_dir / "input.png")
        image.tofile(case_dir / "input_y_u8.bin")
        outputs = reference.run(image)
        files: dict[str, dict] = {}
        for name, values in outputs.items():
            path = case_dir / f"{name}_hwc_{values.dtype.name}.bin"
            np.ascontiguousarray(values).tofile(path)
            files[path.name] = {"shape": list(values.shape), "dtype": values.dtype.name, **_digest(path)}
        Image.fromarray(outputs["output"][:, :, 0], mode="L").save(case_dir / "output.png")
        for extra in [case_dir / "input.png", case_dir / "input_y_u8.bin", case_dir / "output.png"]:
            files[extra.name] = _digest(extra)
        (case_dir / "manifest.json").write_text(
            json.dumps({"case": case, "layout": "HWC_row_major", "files": files}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


@torch.no_grad()
def generate_full_reference(
    model: FSRCNNSubpixel,
    activation_scales: dict[str, float],
    output_dir: Path,
    device: torch.device,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_u8 = procedural_u8(960, 540, seed=123)
    tensor = torch.from_numpy(input_u8.astype(np.float32) / 255.0)[None, None].to(device)
    output = model(tensor).clamp(0.0, 1.0)[0, 0].cpu().numpy().astype(np.float32)
    quant_output = quantized_forward_float(model, tensor, activation_scales)[0, 0].cpu().numpy().astype(np.float32)
    output_u8 = np.clip(np.rint(output * 255.0), 0, 255).astype(np.uint8)
    quant_output_u8 = np.clip(np.rint(quant_output * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(input_u8, mode="L").save(output_dir / "input_960x540.png")
    Image.fromarray(output_u8, mode="L").save(output_dir / "output_1920x1080.png")
    Image.fromarray(quant_output_u8, mode="L").save(output_dir / "output_quant_1920x1080.png")
    np.save(output_dir / "ref_out_fp32.npy", output)
    np.save(output_dir / "ref_out_quant.npy", quant_output)
    input_u8.tofile(output_dir / "input_960x540_y_u8.bin")
    output_u8.tofile(output_dir / "output_1920x1080_y_u8.bin")
    quant_output_u8.tofile(output_dir / "output_quant_1920x1080_y_u8.bin")
    manifest = {
        path.name: _digest(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _array_metadata(values: np.ndarray) -> dict[str, object]:
    contiguous = np.ascontiguousarray(values)
    raw = contiguous.tobytes(order="C")
    return {
        "shape_hwc": list(contiguous.shape),
        "dtype": contiguous.dtype.name,
        "layout": "HWC_row_major",
        "minimum": int(contiguous.min()),
        "maximum": int(contiguous.max()),
        "bytes": len(raw),
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _write_u8_mem(values: np.ndarray, path: Path) -> None:
    flat = np.asarray(values, dtype=np.uint8).reshape(-1)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("".join(f"{int(value):02x}\n" for value in flat))


def generate_full_integer_golden(
    quant_dir: Path,
    input_bin: Path,
    output_dir: Path,
    *,
    width: int = 960,
    height: int = 540,
    rom_depth: int = 1 << 19,
) -> dict[str, object]:
    """Generate the authoritative 960x540 exact-integer acceptance vector.

    Unlike ``generate_full_reference``, this path never calls the floating-point
    model or QDQ simulator. Every stage uses the exported INT8/INT32/Q1.15/Q31
    parameters through :class:`FixedReference`.
    """
    quant_dir = Path(quant_dir)
    input_bin = Path(input_bin)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_bytes = input_bin.read_bytes()
    expected_bytes = width * height
    if len(input_bytes) != expected_bytes:
        raise ValueError(f"Expected {expected_bytes} input bytes, got {len(input_bytes)}")
    if rom_depth < expected_bytes:
        raise ValueError("ROM depth cannot be smaller than the input image")

    input_u8 = np.frombuffer(input_bytes, dtype=np.uint8).reshape(height, width)
    input_copy = output_dir / "input_960x540_y_u8.bin"
    input_copy.write_bytes(input_bytes)
    Image.fromarray(input_u8, mode="L").save(output_dir / "input_960x540_y_u8.png")

    padded = np.zeros(rom_depth, dtype=np.uint8)
    padded[:expected_bytes] = input_u8.reshape(-1)
    padded.tofile(output_dir / "input_rom_2p19_u8.bin")
    _write_u8_mem(padded, output_dir / "input_rom_2p19_u8.mem")

    reference = FixedReference(quant_dir)
    stage_digests: dict[str, dict[str, object]] = {}
    phases: np.ndarray | None = None
    output: np.ndarray | None = None
    for name, values in reference.iter_outputs(input_u8):
        stage_digests[name] = _array_metadata(values)
        if name == "subpixel_phases":
            phases = np.ascontiguousarray(values)
        elif name == "output":
            output = np.ascontiguousarray(values)

    if phases is None or output is None:
        raise RuntimeError("Fixed reference did not produce subpixel phases and output")

    phases.tofile(output_dir / "subpixel_phases_540x960x4_hwc_u8.bin")
    output.tofile(output_dir / "output_1920x1080_y_u8.bin")
    np.save(output_dir / "output_1920x1080_y_u8.npy", output[:, :, 0])
    Image.fromarray(output[:, :, 0], mode="L").save(output_dir / "output_1920x1080_y_u8.png")

    files = {
        path.name: _digest(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "A_CONFIRMED_INTEGER_GOLDEN",
        "golden_class": "full_frame_integer_bit_exact",
        "model": reference.spec["model"],
        "input": {
            "shape_hwc": [height, width, 1],
            "dtype": "uint8",
            "layout": "HWC_row_major",
            "rom_depth": rom_depth,
            "padding_bytes": rom_depth - expected_bytes,
            "padding_value": 0,
        },
        "integer_semantics": {
            "weight": "signed_int8_per_output_channel",
            "activation": "signed_int16_per_tensor",
            "bias_accumulator": "signed_int32_saturating",
            "prelu": "signed_Q1.15_before_requantization",
            "requantization": "signed_Q31",
            "rounding": "nearest_ties_away_from_zero",
            "output": "uint8_saturating",
        },
        "convolution_padding": {
            "feature_5x5": 2,
            "shrink_1x1": 0,
            "mapping0_3x3": 1,
            "expand_1x1": 0,
            "subpixel_5x5": 2,
            "value": 0,
        },
        "pixel_shuffle": {
            "scale": 2,
            "channel_order": ["top_left", "top_right", "bottom_left", "bottom_right"],
        },
        "authoritative_output": "output_1920x1080_y_u8.bin",
        "diagnostic_phase_output": "subpixel_phases_540x960x4_hwc_u8.bin",
        "quant_params": {
            "path": "../quant/quant_params.json",
            **_digest(quant_dir / "quant_params.json"),
        },
        "stage_digests": stage_digests,
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def write_metrics(path: Path, rows: list[dict], summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow({"image": "AVERAGE", **{key: summary[key] for key in fields if key != "image"}})


def write_delivery_manifest(root: Path) -> None:
    files: dict[str, dict[str, str | int]] = {}
    for path in sorted(root.rglob("*")):
        excluded_parts = {".git", ".venv", ".data", ".pytest_cache", "__pycache__"}
        if not path.is_file() or excluded_parts.intersection(path.parts):
            continue
        if path.name == "delivery_manifest.json":
            continue
        files[path.relative_to(root).as_posix()] = _digest(path, normalize_text=True)
    (root / "delivery_manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": files}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
