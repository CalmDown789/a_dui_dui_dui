from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest
import torch

from experiments.hybrid_4k_20261006.bicubic_reference import resize_keys, resize_keys_u8
from experiments.hybrid_4k_20261006.candidate_models import HybridFSRCNN, PRESETS, mac_breakdown
from experiments.hybrid_4k_20261006.compare_color_video_runs import compare_summaries
from experiments.hybrid_4k_20261006.compare_integer_evaluations import compare_integer_evaluations
from experiments.hybrid_4k_20261006.compare_quant_bundles import compare_quant_bundles
from experiments.hybrid_4k_20261006.color_video_prototype import (
    pack_yuv420_frame,
    run_hybrid_integer_u8,
    selected_raw_source_indices,
    unpack_yuv420_frame,
    yuv420_frame_bytes,
)
from experiments.hybrid_4k_20261006.evaluate_hybrid import _ssim_y_tiled
from experiments.hybrid_4k_20261006.extract_uvg_hevc_frames import selected_source_indices
from experiments.hybrid_4k_20261006.hybrid_reference import run_hybrid_float_u8
from experiments.hybrid_4k_20261006.manifest_color_video_output import build_manifest, verify_manifest
from experiments.hybrid_4k_20261006.quantize_candidate_eval import _metrics_border, export_candidate_quantized_bundle
from member_a.fixed_reference import FixedReference
from member_a.quantization import calibrate_activation_scales
from experiments.hybrid_4k_20261006.performance_budget import calculate_budget
from experiments.hybrid_4k_20261006.summarize_video_matrix import collect_video_matrix
from experiments.hybrid_4k_20261006.train_candidate import (
    FramePatchDataset,
    _adapt_state_dict,
    _adapt_selected_shrink_channels,
    _fake_u8,
    _select_shrink_channels_by_l1,
    _set_trainable_scope,
    _torch_resize_keys2,
)
from member_a.model import FSRCNNSubpixel
from member_a.metrics import ssim_y


@pytest.mark.parametrize(
    ("name", "mac_per_pixel"),
    [("R0", 2832), ("R1", 1808), ("R2", 1968), ("R3", 1456), ("R4", 928), ("R5", 696)],
)
def test_candidate_shapes_and_mac(name: str, mac_per_pixel: int) -> None:
    config = PRESETS[name]
    model = HybridFSRCNN(config).eval()
    with torch.no_grad():
        stages = model.forward_with_intermediates(torch.zeros(1, 1, 18, 32))
    assert stages["feature"].shape == (1, config.d, 18, 32)
    assert stages["shrink"].shape == (1, config.s, 18, 32)
    assert stages["mapping0"].shape == (1, config.s, 18, 32)
    assert stages["expand"].shape == (1, config.c, 18, 32)
    assert stages["subpixel_phases"].shape == (1, 4, 18, 32)
    assert stages["output"].shape == (1, 1, 36, 64)
    breakdown = mac_breakdown(config)
    assert breakdown["mac_per_input_pixel"] == mac_per_pixel
    assert breakdown["output_width"] == 1920
    assert breakdown["output_height"] == 1080


def test_r3_full_frame_math_matches_plan() -> None:
    breakdown = mac_breakdown(PRESETS["R3"])
    assert breakdown["mac_per_frame"] == 754_790_400
    assert breakdown["gmac_per_second_60fps"] == pytest.approx(45.287424)
    assert breakdown["mac_per_frame"] / mac_breakdown(PRESETS["R0"])["mac_per_frame"] == pytest.approx(1456 / 2832)


def test_interleaved_frame_sampling_is_disjoint_and_ordered() -> None:
    original = selected_source_indices(frame_stride=10, frame_offset=0, count=4)
    interleaved = selected_source_indices(frame_stride=10, frame_offset=5, count=4)
    assert original == [0, 10, 20, 30]
    assert interleaved == [5, 15, 25, 35]
    assert set(original).isdisjoint(interleaved)
    with pytest.raises(ValueError):
        selected_source_indices(frame_stride=10, frame_offset=10, count=1)


def test_raw_video_segment_indices_allow_absolute_frame_start() -> None:
    assert selected_raw_source_indices(frame_start=300, frame_stride=2, count=4) == [300, 302, 304, 306]
    with pytest.raises(ValueError):
        selected_raw_source_indices(frame_start=-1, frame_stride=2, count=4)


def test_output_head_only_scope_freezes_shared_trunk() -> None:
    model = HybridFSRCNN(PRESETS["R1"])
    _set_trainable_scope(model, output_head_only=True)
    trainable = {name for name, parameter in model.named_parameters() if parameter.requires_grad}
    assert trainable == {"subpixel.weight", "subpixel.bias"}


def test_importance_pruning_transfers_matching_channel_paths() -> None:
    torch.manual_seed(41)
    source = HybridFSRCNN(PRESETS["R3"]).state_dict()
    selected = _select_shrink_channels_by_l1(source, 4)
    assert len(selected) == 4 and len(set(selected)) == 4
    model = HybridFSRCNN(PRESETS["R4"])
    adapted = _adapt_selected_shrink_channels(model, source, selected)
    indices = torch.tensor(selected)
    torch.testing.assert_close(adapted["shrink.weight"], source["shrink.weight"].index_select(0, indices))
    torch.testing.assert_close(
        adapted["mapping.0.weight"],
        source["mapping.0.weight"].index_select(0, indices).index_select(1, indices),
    )
    torch.testing.assert_close(adapted["expand.weight"], source["expand.weight"].index_select(1, indices))
    model.load_state_dict(adapted, strict=True)


def test_bandwidth_budget_matches_frame_geometry() -> None:
    budget = calculate_budget((30,))
    traffic = budget["traffic_by_fps"]["30"]
    assert traffic["endpoint_input_y_plus_output_4k_y8_MB_s"] == pytest.approx(264.384)
    assert traffic["endpoint_input_y_plus_output_4k_yuv420_8bit_MB_s"] == pytest.approx(388.8)
    assert traffic["if_1080p_intermediate_spills_to_ddr_MB_s_output_4k_y8"] == pytest.approx(388.8)
    assert budget["streams"]["output_4k_yuv420_8bit"]["bytes_per_frame"] == 12_441_600


def test_yuv420_pack_unpack_plane_order_and_sizes() -> None:
    y = np.arange(8, dtype=np.uint8).reshape(2, 4)
    cb = np.array([[100, 101]], dtype=np.uint8)
    cr = np.array([[150, 151]], dtype=np.uint8)
    packed = pack_yuv420_frame(y, cb, cr)
    assert len(packed) == yuv420_frame_bytes(4, 2) == 12
    actual_y, actual_cb, actual_cr = unpack_yuv420_frame(packed, 4, 2)
    np.testing.assert_array_equal(actual_y, y)
    np.testing.assert_array_equal(actual_cb, cb)
    np.testing.assert_array_equal(actual_cr, cr)
    with pytest.raises(ValueError):
        yuv420_frame_bytes(3, 2)


def test_r0_candidate_is_state_dict_compatible_with_frozen_model() -> None:
    torch.manual_seed(9)
    frozen = FSRCNNSubpixel().eval()
    candidate = HybridFSRCNN(PRESETS["R0"]).eval()
    candidate.load_state_dict(frozen.state_dict(), strict=True)
    input_tensor = torch.rand(1, 1, 11, 19)
    with torch.no_grad():
        expected = frozen(input_tensor)
        actual = candidate(input_tensor)
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)


@pytest.mark.parametrize("a", [-0.5, -0.75])
def test_keys_upscale_preserves_constant_and_exact_shape(a: float) -> None:
    image = np.full((7, 11), 73, dtype=np.uint8)
    result = resize_keys(image, scale=2, a=a)
    assert result.shape == (14, 22)
    np.testing.assert_allclose(result, 73.0, atol=1e-10)
    assert resize_keys_u8(image, scale=4, a=a).shape == (28, 44)


def test_hybrid_pipeline_shapes_and_u8_range() -> None:
    torch.manual_seed(4)
    model = HybridFSRCNN(PRESETS["R0"]).eval()
    source = np.arange(18 * 32, dtype=np.uint8).reshape(18, 32)
    mid, final = run_hybrid_float_u8(model, source, keys_a=-0.5)
    assert mid.shape == (36, 64)
    assert final.shape == (72, 128)
    assert mid.dtype == np.uint8 and final.dtype == np.uint8


def test_integer_hybrid_video_stage_uses_u8_and_doubles_each_axis() -> None:
    class StubFixedReference:
        def run(self, image: np.ndarray) -> dict[str, np.ndarray]:
            output = np.repeat(np.repeat(image[:, :, None], 2, axis=0), 2, axis=1)
            return {"output": output.astype(np.uint8, copy=False)}

    source = np.arange(18 * 32, dtype=np.uint8).reshape(18, 32)
    mid, final = run_hybrid_integer_u8(StubFixedReference(), source, keys_a=-0.5)  # type: ignore[arg-type]
    assert mid.shape == (36, 64)
    assert final.shape == (72, 128)
    assert mid.dtype == np.uint8 and final.dtype == np.uint8


def test_integer_hybrid_video_stage_rejects_bad_quantized_output() -> None:
    class BadFixedReference:
        def run(self, image: np.ndarray) -> dict[str, np.ndarray]:
            return {"output": np.zeros((image.shape[0], image.shape[1], 1), dtype=np.uint8)}

    with pytest.raises(ValueError, match="Integer CNN output"):
        run_hybrid_integer_u8(BadFixedReference(), np.zeros((18, 32), dtype=np.uint8), keys_a=-0.5)  # type: ignore[arg-type]


def test_color_video_run_comparison_requires_matching_source_and_reports_deltas() -> None:
    def summary(model_mode: str, model_psnr: float, model_ssim: float) -> dict[str, object]:
        return {
            "sequence": "test",
            "source_video_sha256": "same-source",
            "source_frame_indices": [0],
            "source_fps_metadata": 120.0,
            "output_fps_for_selected_frames": 12.0,
            "input_format": "same-input",
            "keys_a": -0.5,
            "model_mode": model_mode,
            "model_artifact": model_mode,
            "metrics": {
                "per_frame": [
                    {
                        "frame_index": 0,
                        "bicubic_y_psnr_db": 40.0,
                        "bicubic_y_ssim": 0.95,
                        "hybrid_y_psnr_db": model_psnr,
                        "hybrid_y_ssim": model_ssim,
                    }
                ]
            },
        }

    baseline = summary("base", 41.0, 0.96)
    candidate = summary("qat", 41.25, 0.97)
    result = compare_summaries(baseline, candidate)
    assert result["comparison"]["mean_candidate_minus_baseline_y_psnr_db"] == pytest.approx(0.25)
    assert result["comparison"]["mean_candidate_minus_baseline_y_ssim"] == pytest.approx(0.01)
    candidate["source_video_sha256"] = "different-source"
    with pytest.raises(ValueError, match="source_video_sha256 differs"):
        compare_summaries(baseline, candidate)


def test_video_output_manifest_detects_changed_file(tmp_path) -> None:
    (tmp_path / "demo.mp4").write_bytes(b"small test video")
    (tmp_path / "summary.json").write_text("{}", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    (tmp_path / "delivery_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(tmp_path)["files_checked"] == 2
    (tmp_path / "demo.mp4").write_bytes(b"changed")
    with pytest.raises(AssertionError, match="demo.mp4"):
        verify_manifest(tmp_path)


def test_video_matrix_requires_ten_distinct_nonoverlapping_clips(tmp_path) -> None:
    metric = {
        "bicubic_y_psnr_db": 40.0,
        "bicubic_y_ssim": 0.95,
        "hybrid_y_psnr_db": 41.0,
        "hybrid_y_ssim": 0.96,
        "hybrid_y_delta_vs_bicubic_db": 1.0,
    }
    clip_names = [f"clip_{index:02d}" for index in range(10)]
    for index, clip_name in enumerate(clip_names):
        clip_dir = tmp_path / clip_name
        clip_dir.mkdir()
        (clip_dir / "hybrid_4k_color_demo.mp4").write_bytes(b"mp4")
        (clip_dir / "color_video_contact_sheet.png").write_bytes(b"png")
        source_path = tmp_path / f"source_{index}.raw"
        source_path.write_bytes(f"source_{index}".encode())
        indices = list(range(index * 125, index * 125 + 125))
        summary = {
            "status": "SOFTWARE_DEMO_ONLY_NOT_BOARD_PROTOCOL_OR_REALTIME_ACCEPTANCE",
            "sequence": f"sequence_{index}",
            "source_video": str(source_path),
            "source_video_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "source_frame_indices": indices,
            "frames": 125,
            "output_fps_for_selected_frames": 25,
            "metrics": {"per_frame": [metric] * 125},
        }
        (clip_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    report = collect_video_matrix(tmp_path, clip_names, verify_media=False)
    assert report["clip_count"] == 10
    assert report["total_evaluated_frames"] == 1250
    with pytest.raises(ValueError, match="At least 10"):
        collect_video_matrix(tmp_path, clip_names[:9])
    overlapping_path = tmp_path / clip_names[1] / "summary.json"
    overlapping = json.loads(overlapping_path.read_text(encoding="utf-8"))
    clip_zero = json.loads((tmp_path / clip_names[0] / "summary.json").read_text(encoding="utf-8"))
    overlapping["source_video"] = clip_zero["source_video"]
    overlapping["source_video_sha256"] = clip_zero["source_video_sha256"]
    overlapping["source_frame_indices"] = list(range(125))
    overlapping_path.write_text(json.dumps(overlapping), encoding="utf-8")
    with pytest.raises(ValueError, match="Source frames overlap"):
        collect_video_matrix(tmp_path, clip_names, verify_media=False)


def test_quant_bundle_comparison_separates_shape_compatibility_from_numeric_diff(tmp_path) -> None:
    contract = {
        "schema_version": 1,
        "model": "test-model",
        "input": {"dtype": "uint8"},
        "hidden_activation": {"dtype": "int16"},
        "weight": {"dtype": "int8", "layout": "OIHW"},
        "bias_accumulator": {"dtype": "int32"},
        "rounding": "nearest_ties_away_from_zero",
        "prelu": "Q1.15",
        "pixel_shuffle": {"order": [0, 1, 2, 3]},
        "output": {"dtype": "uint8"},
    }
    roots = [tmp_path / "baseline", tmp_path / "candidate"]
    for index, root in enumerate(roots):
        root.mkdir()
        (root / "w.bin").write_bytes(np.array([2 + index, 3], dtype=np.int8).tobytes())
        (root / "b.bin").write_bytes(np.array([7], dtype="<i4").tobytes())
        (root / "p.bin").write_bytes(np.array([100 + index], dtype="<i2").tobytes())
        layer = {
            "name": "feature",
            "type": "conv",
            "kernel": [1, 2],
            "padding": [0, 0],
            "weight_shape_oihw": [1, 1, 1, 2],
            "output_dtype": "int16",
            "weight_scale_per_output": [0.1],
            "input_scale": 1.0,
            "output_scale": 0.01,
            "bias_scale_per_output": [0.1],
            "requant_multiplier_real": [0.01 + index * 0.001],
            "requant_multiplier_q31": [21474836 + index],
            "prelu_q15": [100 + index],
            "files": {"weight_bin": "w.bin", "bias_bin": "b.bin", "prelu_bin": "p.bin"},
        }
        (root / "quant_params.json").write_text(json.dumps({**contract, "layers": [layer]}), encoding="utf-8")

    result = compare_quant_bundles(*roots)
    assert result["shape_and_layer_contract_compatible"] is True
    assert result["status"] == "SHAPE_CONTRACT_COMPATIBLE_NUMERIC_PARAMETERS_DIFFER"
    assert result["layers"][0]["binary_tensor_deltas"]["weight_bin"]["changed_count"] == 1
    candidate_spec_path = roots[1] / "quant_params.json"
    candidate_spec = json.loads(candidate_spec_path.read_text(encoding="utf-8"))
    candidate_spec["layers"][0]["padding"] = [1, 1]
    candidate_spec_path.write_text(json.dumps(candidate_spec), encoding="utf-8")
    assert compare_quant_bundles(*roots)["shape_and_layer_contract_compatible"] is False


def test_r1_three_by_three_head_quantizes_and_runs_with_candidate_metadata(tmp_path) -> None:
    torch.manual_seed(101)
    model = HybridFSRCNN(PRESETS["R1"]).eval()
    calibration = [torch.rand(1, 1, 16, 20)]
    scales = calibrate_activation_scales(model, calibration, torch.device("cpu"))
    quant_dir = tmp_path / "r1_quant"
    bundle = export_candidate_quantized_bundle(model, "R1", scales, quant_dir)
    assert bundle["model"].startswith("HybridFSRCNN-R1-")
    assert bundle["layers"][-1]["kernel"] == [3, 3]
    assert bundle["layers"][-1]["padding"] == [1, 1]
    fixed_output = FixedReference(quant_dir).run(np.zeros((16, 20), dtype=np.uint8))["output"]
    assert fixed_output.shape == (32, 40, 1)
    assert fixed_output.dtype == np.uint8


def test_integer_evaluation_comparison_pairs_rows_and_checks_bicubic_identity(tmp_path) -> None:
    header = "sequence,image,integer_psnr_db,integer_ssim,bicubic_psnr_db,bicubic_ssim\n"
    baseline_path = tmp_path / "baseline.csv"
    candidate_path = tmp_path / "candidate.csv"
    baseline_path.write_text(header + "ffmpeg_Bosphorus,frame_000.png,40.0,0.95,39.0,0.94\n", encoding="utf-8")
    candidate_path.write_text(header + "ffmpeg_Bosphorus,frame_000.png,40.25,0.96,39.0,0.94\n", encoding="utf-8")
    result = compare_integer_evaluations(
        baseline_path,
        candidate_path,
        sequence_prefix="ffmpeg_",
        baseline_name="R0",
        candidate_name="R1",
    )
    assert result["frames"] == 1
    assert result["mean_candidate_minus_baseline_psnr_db"] == pytest.approx(0.25)
    candidate_path.write_text(header + "ffmpeg_Bosphorus,frame_000.png,40.25,0.96,38.9,0.94\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bicubic_psnr_db differs"):
        compare_integer_evaluations(
            baseline_path,
            candidate_path,
            sequence_prefix="ffmpeg_",
            baseline_name="R0",
            candidate_name="R1",
        )


def test_tiled_ssim_matches_project_ssim() -> None:
    rng = np.random.default_rng(53)
    reference = rng.integers(0, 256, size=(43, 67), dtype=np.uint8)
    candidate = rng.integers(0, 256, size=(43, 67), dtype=np.uint8)
    expected = ssim_y(
        torch.from_numpy(reference.copy()).double()[None, None] / 255.0,
        torch.from_numpy(candidate.copy()).double()[None, None] / 255.0,
        border=8,
    )
    actual = _ssim_y_tiled(reference, candidate, border=8, tile_rows=7)
    assert actual == pytest.approx(expected, abs=1e-12)


def test_candidate_metric_reports_full_frame_and_shaved_border_separately() -> None:
    reference = np.zeros((32, 32), dtype=np.uint8)
    candidate = reference.copy()
    candidate[0, 0] = 255
    full_psnr, full_ssim = _metrics_border(reference, candidate, border=0)
    shaved_psnr, shaved_ssim = _metrics_border(reference, candidate, border=8)
    assert np.isfinite(full_psnr)
    assert full_ssim < 1.0
    assert shaved_psnr == float("inf")
    assert shaved_ssim == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("a", [-0.5, -0.75])
def test_torch_keys_matches_numpy_reference_and_has_gradient(a: float) -> None:
    rng = np.random.default_rng(123)
    values = rng.normal(size=(1, 1, 7, 9)).astype(np.float32)
    tensor = torch.tensor(values, requires_grad=True)
    actual = _torch_resize_keys2(tensor, a=a)
    expected = resize_keys(values[0, 0], scale=2, a=a)
    np.testing.assert_allclose(actual.detach().numpy()[0, 0], expected, atol=2e-6, rtol=1e-6)
    actual.square().mean().backward()
    assert tensor.grad is not None and torch.isfinite(tensor.grad).all()


def test_fake_u8_uses_straight_through_gradient_and_saturates() -> None:
    values = torch.tensor([-0.2, 0.5, 1.2], requires_grad=True)
    quantized = _fake_u8(values)
    torch.testing.assert_close(quantized.detach(), torch.tensor([0.0, 128.0 / 255.0, 1.0]))
    quantized.sum().backward()
    torch.testing.assert_close(values.grad, torch.tensor([0.0, 1.0, 0.0]))


@pytest.mark.parametrize("variant", ["R0", "R1", "R2", "R3", "R4", "R5"])
def test_candidate_transfer_initialization_crops_frozen_model(variant: str) -> None:
    source = FSRCNNSubpixel().state_dict()
    model = HybridFSRCNN(PRESETS[variant])
    adapted = _adapt_state_dict(model, source)
    assert set(adapted) == set(model.state_dict())
    model.load_state_dict(adapted, strict=True)
    if PRESETS[variant].c < 16:
        torch.testing.assert_close(adapted["expand_act.weight"], source["expand_act.weight"][: PRESETS[variant].c])
        torch.testing.assert_close(
            adapted["expand.weight"],
            source["expand.weight"][: PRESETS[variant].c, : PRESETS[variant].s],
        )
    if PRESETS[variant].d < 16:
        torch.testing.assert_close(adapted["feature.weight"], source["feature.weight"][: PRESETS[variant].d])
        torch.testing.assert_close(adapted["feature_act.weight"], source["feature_act.weight"][: PRESETS[variant].d])
    if PRESETS[variant].s < 8:
        torch.testing.assert_close(adapted["shrink.weight"], source["shrink.weight"][: PRESETS[variant].s, : PRESETS[variant].d])
        torch.testing.assert_close(adapted["shrink_act.weight"], source["shrink_act.weight"][: PRESETS[variant].s])
        torch.testing.assert_close(adapted["mapping.0.weight"], source["mapping.0.weight"][: PRESETS[variant].s, : PRESETS[variant].s])


def test_training_patch_alignment_uses_matching_4x_hr_crop(tmp_path) -> None:
    lr = np.arange(6 * 8, dtype=np.uint8).reshape(6, 8)
    hr = np.repeat(np.repeat(lr, 4, axis=0), 4, axis=1)
    path = tmp_path / "pair.npz"
    np.savez(path, lr_y=lr, hr_y=hr)
    dataset = FramePatchDataset([(path, "synthetic")], patches_per_frame=1, patch_size=4, seed=3, training=False)
    lr_patch, hr_patch = dataset[0]
    np.testing.assert_allclose(lr_patch.numpy()[0] * 255, lr[1:5, 2:6], atol=1e-5)
    np.testing.assert_allclose(hr_patch.numpy()[0] * 255, hr[4:20, 8:24], atol=1e-5)
