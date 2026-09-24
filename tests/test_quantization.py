import json

import numpy as np
import torch

from member_a.fixed_reference import FixedReference, pixel_shuffle_hwc_x2
from member_a.model import FSRCNNSubpixel
from member_a.quantization import (
    INT16_MAX,
    INT16_MIN,
    calibrate_activation_scales,
    export_quantized_bundle,
    round_away_from_zero,
)


def test_round_ties_away_from_zero():
    values = np.array([-2.5, -1.5, -0.5, 0.5, 1.5, 2.5])
    assert np.array_equal(round_away_from_zero(values), np.array([-3, -2, -1, 1, 2, 3]))


def test_pixel_shuffle_phase_order():
    phases = np.zeros((2, 3, 4), dtype=np.uint8)
    phases[:, :, 0] = 10
    phases[:, :, 1] = 20
    phases[:, :, 2] = 30
    phases[:, :, 3] = 40
    output = pixel_shuffle_hwc_x2(phases)[:, :, 0]
    assert np.all(output[0::2, 0::2] == 10)
    assert np.all(output[0::2, 1::2] == 20)
    assert np.all(output[1::2, 0::2] == 30)
    assert np.all(output[1::2, 1::2] == 40)


def test_export_layout_formats_and_fixed_reference(tmp_path):
    torch.manual_seed(123)
    model = FSRCNNSubpixel().eval()
    sample = torch.rand(1, 1, 8, 12)
    scales = calibrate_activation_scales(model, [sample], torch.device("cpu"))
    spec = export_quantized_bundle(model, scales, tmp_path)
    assert spec["weight"]["layout"] == "OIHW"
    assert spec["pixel_shuffle"]["channel_order"] == ["top_left", "top_right", "bottom_left", "bottom_right"]
    for layer in spec["layers"]:
        shape = tuple(layer["weight_shape_oihw"])
        loaded = np.fromfile(tmp_path / layer["files"]["weight_bin"], dtype=np.int8).reshape(shape)
        assert loaded.shape == shape
        assert (tmp_path / layer["files"]["weight_mem"]).is_file()
        assert (tmp_path / layer["files"]["weight_coe"]).is_file()
    reference = FixedReference(tmp_path)
    outputs = reference.run(np.arange(96, dtype=np.uint8).reshape(8, 12))
    assert outputs["feature"].dtype == np.int16
    assert outputs["feature"].min() >= INT16_MIN
    assert outputs["feature"].max() <= INT16_MAX
    assert outputs["output"].shape == (16, 24, 1)
    assert outputs["output"].dtype == np.uint8
    parsed = json.loads((tmp_path / "quant_params.json").read_text(encoding="utf-8"))
    assert parsed["model"] == "FSRCNNSubpixel-d16-s8-m1-c16-x2"
