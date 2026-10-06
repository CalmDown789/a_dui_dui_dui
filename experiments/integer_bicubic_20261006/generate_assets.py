from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from .assets import contract_payload, file_record, sha256_file, write_coefficients
from .integer_bicubic import COEFFICIENTS_Q14, resize_chunked, resize_float64, resize_scalar


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _save_raw(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.ascontiguousarray(values).tobytes(order="C"))


def _make_vectors(output_dir: Path) -> dict:
    vectors_dir = output_dir / "vectors"
    cases: dict[str, np.ndarray] = {
        "zero": np.zeros((6, 8), dtype=np.uint8),
        "constant_1x1": np.full((1, 1), 137, dtype=np.uint8),
        "impulse": np.pad(np.asarray([[255]], dtype=np.uint8), ((3, 3), (4, 4))),
        "ramp": np.arange(7 * 9, dtype=np.uint8).reshape(7, 9),
        "checkerboard": ((np.indices((8, 10)).sum(axis=0) & 1) * 255).astype(np.uint8),
        "random_seed_20261006": np.random.default_rng(20261006).integers(0, 256, (9, 11), dtype=np.uint8),
    }
    corners = np.zeros((9, 11), dtype=np.uint8)
    corners[0, 0], corners[0, -1], corners[-1, 0], corners[-1, -1] = 255, 17, 93, 255
    corners[1:-1, 1:-1] = np.arange(7 * 9, dtype=np.uint8).reshape(7, 9)
    cases["high_contrast_corners"] = corners

    manifest: dict[str, object] = {
        "schema": "member-a-bicubic-stage-vectors-v1",
        "status": "A_SIDE_SOFTWARE_REFERENCE_VECTORS",
        "arithmetic": "horizontal Q14 signed integer; vertical Q28 signed integer; final ties-away round and uint8 saturation",
        "vectors": [],
    }
    for name, source in cases.items():
        vector_dir = vectors_dir / name
        vector_dir.mkdir(parents=True, exist_ok=True)
        scalar_output, scalar_horizontal, scalar_accumulator = resize_scalar(source)
        output, horizontal, accumulator = resize_chunked(source, row_chunk=3)
        if horizontal is None or accumulator is None:
            raise AssertionError("stage arrays must be included in vectors")
        np.testing.assert_array_equal(output, scalar_output)
        np.testing.assert_array_equal(horizontal, scalar_horizontal)
        np.testing.assert_array_equal(accumulator, scalar_accumulator)
        np.testing.assert_array_equal(output, resize_float64(source, row_chunk=2))
        file_paths = {
            "input_y_u8.bin": source,
            "horizontal_q14_int32.bin": horizontal.astype("<i4", copy=False),
            "vertical_accum_q28_int64.bin": accumulator.astype("<i8", copy=False),
            "output_y_u8.bin": output,
        }
        for filename, array in file_paths.items():
            _save_raw(vector_dir / filename, array)
        manifest["vectors"].append(
            {
                "name": name,
                "input_shape_hw": list(source.shape),
                "output_shape_hw": list(output.shape),
                "input_min_max": [int(source.min()), int(source.max())],
                "horizontal_q14_min_max": [int(horizontal.min()), int(horizontal.max())],
                "vertical_q28_min_max": [int(accumulator.min()), int(accumulator.max())],
                "files": {filename: file_record(vector_dir / filename) for filename in file_paths},
            }
        )
    _write_json(vectors_dir / "manifest.json", manifest)
    return manifest


def _difference(reference: np.ndarray, candidate: np.ndarray) -> dict:
    delta = candidate.astype(np.int16).astype(np.int32) - reference.astype(np.int16).astype(np.int32)

    def region_record(difference: np.ndarray) -> dict:
        mse = float(np.mean(difference.astype(np.float64) ** 2))
        rmse = math.sqrt(mse)
        return {
            "pixels": int(difference.size),
            "mismatch_pixels": int(np.count_nonzero(difference)),
            "max_absolute_difference": int(np.max(np.abs(difference))) if difference.size else 0,
            "rmse": rmse,
            "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
        }

    return {
        "full_frame": region_record(delta),
        "shave_8": region_record(delta[8:-8, 8:-8]),
    }


def _load_y8(path: Path, shape: tuple[int, int]) -> np.ndarray:
    expected_bytes = shape[0] * shape[1]
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"{path} has {path.stat().st_size} bytes, expected {expected_bytes}")
    return np.fromfile(path, dtype=np.uint8).reshape(shape)


def _process_frame(
    *,
    name: str,
    cnn_output_path: Path,
    cnn_shape: tuple[int, int],
    original_input_path: Path,
    original_input_shape: tuple[int, int],
    output_directory: Path,
    row_chunk: int,
) -> tuple[dict, dict]:
    cnn_output = _load_y8(cnn_output_path, cnn_shape)
    original_input = _load_y8(original_input_path, original_input_shape)
    result, horizontal, accumulator = resize_chunked(cnn_output, row_chunk=row_chunk)
    if horizontal is None or accumulator is None:
        raise AssertionError("full golden stage data was not returned")
    floating = resize_float64(cnn_output, row_chunk=row_chunk)
    np.testing.assert_array_equal(result, floating)
    output_path = output_directory / f"{name}_3840x2160_y_u8.bin"
    _save_raw(output_path, result)
    frame_record = {
        "id": name,
        "pipeline_stage_input": {
            "path_from_repository_root": cnn_output_path.relative_to(output_directory.parents[2]).as_posix(),
            "shape_hw": list(cnn_shape),
            "dtype": "uint8",
            "layout": "row_major_Y",
            **file_record(cnn_output_path),
        },
        "original_540p_input": {
            "path_from_repository_root": original_input_path.relative_to(output_directory.parents[2]).as_posix(),
            "shape_hw": list(original_input_shape),
            "dtype": "uint8",
            "layout": "row_major_Y",
            **file_record(original_input_path),
        },
        "output_4k": {
            "path_from_repository_root": output_path.relative_to(output_directory.parents[2]).as_posix(),
            "shape_hwc": [result.shape[0], result.shape[1], 1],
            "dtype": "uint8",
            "layout": "HWC_row_major",
            **file_record(output_path),
        },
    }
    error_record = {
        "id": name,
        "float64_vs_integer_final_y8": _difference(floating, result),
        "integer_stage_ranges": {
            "horizontal_q14_min": int(horizontal.min()),
            "horizontal_q14_max": int(horizontal.max()),
            "vertical_q28_min": int(accumulator.min()),
            "vertical_q28_max": int(accumulator.max()),
        },
    }
    return frame_record, error_record


def generate_assets(repo_root: Path, *, row_chunk: int = 16) -> dict:
    output_dir = repo_root / "artifacts" / "integer_bicubic_20261006"
    output_dir.mkdir(parents=True, exist_ok=True)
    coefficient_records = write_coefficients(output_dir / "coefficients")
    contract = contract_payload()
    _write_json(output_dir / "interp_contract.json", contract)
    vector_manifest = _make_vectors(output_dir)

    base_manifest_path = repo_root / "artifacts" / "full_integer_golden" / "manifest.json"
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    cnn_output_path = repo_root / "artifacts" / "full_integer_golden" / "output_1920x1080_y_u8.bin"
    input_540_path = repo_root / "artifacts" / "full_integer_golden" / "input_960x540_y_u8.bin"
    mixed_dir = output_dir / "mixed_golden"
    mixed_dir.mkdir(parents=True, exist_ok=True)

    single, single_error = _process_frame(
        name="frozen_full_integer_golden",
        cnn_output_path=cnn_output_path,
        cnn_shape=(1080, 1920),
        original_input_path=input_540_path,
        original_input_shape=(540, 960),
        output_directory=mixed_dir,
        row_chunk=row_chunk,
    )
    multiframe_dir = repo_root / "artifacts" / "multiframe"
    multiframe_manifest_path = multiframe_dir / "manifest.json"
    sequence_frames: list[dict] = []
    sequence_errors: list[dict] = []
    for frame_index in range(3):
        frame_id = f"frame_{frame_index:03d}"
        frame_record, error_record = _process_frame(
            name=f"sequence_{frame_id}",
            cnn_output_path=multiframe_dir / f"{frame_id}_output_y_u8.bin",
            cnn_shape=(1080, 1920),
            original_input_path=multiframe_dir / f"{frame_id}_input_y_u8.bin",
            original_input_shape=(540, 960),
            output_directory=mixed_dir,
            row_chunk=row_chunk,
        )
        frame_record["source_frame_id"] = frame_id
        sequence_frames.append(frame_record)
        sequence_errors.append(error_record)

    report = {
        "schema": "member-a-bicubic-integer-float-parity-v1",
        "status": "PASS" if all(
            row["float64_vs_integer_final_y8"]["full_frame"]["mismatch_pixels"] == 0
            and row["float64_vs_integer_final_y8"]["shave_8"]["mismatch_pixels"] == 0
            for row in [single_error, *sequence_errors]
        ) else "FAIL",
        "comparison": "same Keys a=-0.5, half-pixel coordinates, edge replication and final Y8 conversion; only float64 versus Q14 integer arithmetic differs",
        "meaning": "This measures arithmetic parity between two implementations, not 4K reconstruction quality against a true 4K reference.",
        "coefficient_quantization": "all four phase taps are exactly representable in Q14; no coefficient approximation error",
        "rounding": "fixed point retains horizontal Q14 and vertical Q28 exactly; rounds once at Q28 using nearest ties away from zero; float reference rounds final values by the same rule",
        "single_full_frame": single_error,
        "three_contiguous_frames": sequence_errors,
    }
    _write_json(output_dir / "interpolation_error_report.json", report)

    task_plan_path = repo_root / "docs" / "MEMBER_A_PARALLEL_INTEGER_BICUBIC_4K_2026-10-06.md"
    source_manifest = {
        "schema": "member-a-integer-bicubic-source-manifest-v1",
        "status": "SOURCE_HASHES_RECORDED",
        "repository_base_commit": "976776c7d7da6d848dfbba43f7e3c007afb41c6b",
        "frozen_a_model_source_commit": "98c82f394bdfba85bc2959bede9760edc4d6862f",
        "task_plan": {
            "path": task_plan_path.relative_to(repo_root).as_posix(),
            **file_record(task_plan_path),
        },
        "implementation": {
            path.name: {
                "path": path.relative_to(repo_root).as_posix(),
                **file_record(path),
            }
            for path in [
                Path(__file__),
                Path(__file__).with_name("integer_bicubic.py"),
                Path(__file__).with_name("assets.py"),
            ]
        },
        "frozen_full_integer_golden_manifest": {
            "path": base_manifest_path.relative_to(repo_root).as_posix(),
            **file_record(base_manifest_path),
        },
        "frozen_full_frame_input_540p": {
            "path": input_540_path.relative_to(repo_root).as_posix(),
            **file_record(input_540_path),
        },
        "frozen_full_frame_integer_cnn_output_1080p": {
            "path": cnn_output_path.relative_to(repo_root).as_posix(),
            **file_record(cnn_output_path),
        },
        "multi_frame_source_manifest": {
            "path": multiframe_manifest_path.relative_to(repo_root).as_posix(),
            **file_record(multiframe_manifest_path),
        },
        "quant_params": {
            "path": "artifacts/quant/quant_params.json",
            **file_record(repo_root / "artifacts" / "quant" / "quant_params.json"),
        },
        "interpolation_contract_sha256": sha256_file(output_dir / "interp_contract.json"),
        "coefficient_files": coefficient_records,
        "limitations": [
            "The source frames and frozen CNN outputs are inherited from the A-side member-a branch; no CNN or source-video data is modified.",
            "This manifest does not provide FPGA or board evidence.",
        ],
    }
    _write_json(output_dir / "source_manifest.json", source_manifest)

    package_manifest = {
        "schema": "member-a-integer-bicubic-golden-v1",
        "status": "A_SIDE_SOFTWARE_GOLDEN_FOR_B_REVIEW",
        "pipeline": "960x540 Y8 input -> frozen A integer FSRCNN x2 -> 1920x1080 Y8 -> fixed Keys bicubic x2 -> 3840x2160 Y8",
        "model": base_manifest["model"],
        "frozen_model_provenance": {
            "source_commit": "98c82f394bdfba85bc2959bede9760edc4d6862f",
            "frozen_full_integer_manifest_sha256": sha256_file(base_manifest_path),
            "quant_params_sha256": base_manifest["quant_params"]["sha256"],
            "network_output_sha256": file_record(cnn_output_path)["sha256"],
        },
        "interpolation_contract_sha256": sha256_file(output_dir / "interp_contract.json"),
        "coefficient_files": coefficient_records,
        "single_full_frame": single,
        "contiguous_three_frame_software_sequence": {
            "source_manifest_sha256": sha256_file(multiframe_manifest_path),
            "frame_count": len(sequence_frames),
            "frames": sequence_frames,
            "cross_frame_state": "Each call is stateless; input arrays are read-only and every output is independently hashed.",
        },
        "test_vectors_manifest_sha256": sha256_file(output_dir / "vectors" / "manifest.json"),
        "source_manifest_sha256": sha256_file(output_dir / "source_manifest.json"),
        "error_report_sha256": sha256_file(output_dir / "interpolation_error_report.json"),
        "data_scope": "The full-size input and three-frame sequence are existing CC-BY source-derived member-A Y8 assets; no new source video is copied.",
        "hardware_boundary": "No B RTL, synthesis, timing, board or sustained frame-rate claim is made by this software Golden.",
    }
    _write_json(output_dir / "golden_manifest.json", package_manifest)
    return {"output_dir": output_dir, "package_manifest": package_manifest, "error_report": report, "vectors": vector_manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fixed bicubic coefficients, vectors and full-size A-side Goldens")
    parser.add_argument("--row-chunk", type=int, default=16)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    result = generate_assets(repo_root, row_chunk=args.row_chunk)
    print(json.dumps({"output_dir": str(result["output_dir"]), "status": result["error_report"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
