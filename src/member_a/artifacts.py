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
