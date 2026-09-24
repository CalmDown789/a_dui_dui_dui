import numpy as np

from member_a.fixed_reference import _apply_prelu_q15, _requantize
from member_a.quantization import INT16_MAX, INT16_MIN, Q15, Q31


def test_prelu_q15_and_signed_rounding():
    accum = np.array([[[-7, 8]]], dtype=np.int32)
    alpha = np.array([Q15 // 2, Q15 // 4], dtype=np.int16)
    result = _apply_prelu_q15(accum, alpha)
    assert np.array_equal(result, np.array([[[-4, 8]]]))


def test_requantize_saturates_int16():
    accum = np.array([[[-100_000, 100_000]]], dtype=np.int32)
    multiplier = np.array([Q31, Q31], dtype=np.int64)
    result = _requantize(accum, multiplier, INT16_MIN, INT16_MAX)
    assert np.array_equal(result, np.array([[[INT16_MIN, INT16_MAX]]]))
