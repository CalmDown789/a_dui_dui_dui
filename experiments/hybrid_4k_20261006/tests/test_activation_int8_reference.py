from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from member_a.fixed_reference import FixedReference
from member_a.quantization import export_quantized_bundle
from experiments.hybrid_4k_20261006.activation_int8_reference import (
    HIDDEN_LAYERS,
    MixedActivationFixedReference,
    _ste_fake_quant,
    export_mixed_activation_bundle,
    validate_activation_bits,
)
from experiments.hybrid_4k_20261006.candidate_models import HybridFSRCNN, PRESETS


class ActivationInt8ReferenceTests(unittest.TestCase):
    def test_signed_int8_contract_is_explicit(self) -> None:
        validate_activation_bits({name: 8 for name in HIDDEN_LAYERS})
        validate_activation_bits({name: 16 for name in HIDDEN_LAYERS})
        with self.assertRaises(ValueError):
            validate_activation_bits({name: 4 for name in HIDDEN_LAYERS})
        with self.assertRaises(ValueError):
            validate_activation_bits({"feature": 8})

    def test_ste_rounds_ties_away_from_zero_and_preserves_gradient(self) -> None:
        values = torch.tensor([0.5, -0.5, 2.0, -2.0], requires_grad=True)
        result = _ste_fake_quant(values, 1.0, -1, 1)
        self.assertTrue(torch.equal(result.detach(), torch.tensor([1.0, -1.0, 1.0, -1.0])))
        result.sum().backward()
        self.assertTrue(torch.equal(values.grad, torch.ones_like(values)))

    def test_int16_experiment_reference_matches_formal_reference(self) -> None:
        torch.manual_seed(7)
        model = HybridFSRCNN(PRESETS["R0"]).eval()
        sample = torch.linspace(0.0, 1.0, 1 * 1 * 16 * 16).reshape(1, 1, 16, 16)
        scales = {name: 1.0e-4 for name in HIDDEN_LAYERS}
        all_int16 = {name: 16 for name in HIDDEN_LAYERS}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            formal = root / "formal"
            mixed = root / "mixed"
            export_quantized_bundle(model, scales, formal)
            export_mixed_activation_bundle(model, scales, all_int16, mixed)
            input_u8 = np.arange(16 * 16, dtype=np.uint8).reshape(16, 16)
            reference = FixedReference(formal).run(input_u8)
            experimental = MixedActivationFixedReference(mixed).run(input_u8)
            self.assertEqual(reference.keys(), experimental.keys())
            for key in reference:
                self.assertTrue(np.array_equal(reference[key], experimental[key]), key)

    def test_int8_outputs_are_signed_and_shape_preserving(self) -> None:
        torch.manual_seed(9)
        model = HybridFSRCNN(PRESETS["R0"]).eval()
        bits = {name: 16 for name in HIDDEN_LAYERS}
        bits["mapping0"] = 8
        scales = {name: 1.0e-4 for name in HIDDEN_LAYERS}
        with tempfile.TemporaryDirectory() as temp:
            quant_dir = Path(temp) / "quant"
            spec = export_mixed_activation_bundle(model, scales, bits, quant_dir)
            self.assertEqual(spec["weight"]["layout"], "OIHW")
            self.assertEqual(spec["hidden_activation"]["bits_by_layer"], bits)
            for layer in spec["layers"]:
                shape = tuple(layer["weight_shape_oihw"])
                files = layer["files"]
                raw_weight = np.fromfile(quant_dir / files["weight_bin"], dtype=np.int8)
                self.assertEqual(raw_weight.size, int(np.prod(shape)))
                self.assertEqual(np.load(quant_dir / files["weight_npy"]).shape, shape)
                for suffix in ("weight_mem", "weight_coe", "bias_bin", "bias_mem", "bias_coe"):
                    self.assertTrue((quant_dir / files[suffix]).is_file(), suffix)
            input_u8 = np.full((16, 16), 127, dtype=np.uint8)
            outputs = MixedActivationFixedReference(quant_dir).run(input_u8)
            self.assertEqual(outputs["mapping0"].dtype, np.int8)
            self.assertTrue(np.all(outputs["mapping0"] >= -127))
            self.assertTrue(np.all(outputs["mapping0"] <= 127))
            for name in ("feature", "shrink", "expand"):
                self.assertEqual(outputs[name].dtype, np.int16)
            self.assertEqual(outputs["output"].dtype, np.uint8)
            self.assertEqual(outputs["output"].shape, (32, 32, 1))


if __name__ == "__main__":
    unittest.main()
