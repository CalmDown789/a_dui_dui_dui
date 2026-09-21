from __future__ import annotations

import numpy as np

from data_layout import (
    FrameGeometry,
    decode_int8_to_y8,
    encode_y8_to_int8,
    network_output_geometry,
    pack_hwc_int8,
    unpack_hwc_int8,
)


def test_hwc_byte_order_round_trip() -> None:
    geometry = FrameGeometry(2, 2, 2)
    source = np.array(
        [[[1, -1], [2, -2]], [[3, -3], [4, -4]]], dtype=np.int8
    )
    packed = pack_hwc_int8(source, geometry)
    expected = np.array([1, 255, 2, 254, 3, 253, 4, 252], dtype=np.uint8)
    np.testing.assert_array_equal(packed, expected)
    np.testing.assert_array_equal(unpack_hwc_int8(packed, geometry), source)


def test_payload_length_rejected() -> None:
    try:
        unpack_hwc_int8(bytes(7), FrameGeometry(2, 2, 2))
    except ValueError as error:
        assert "expected 8 bytes" in str(error)
    else:
        raise AssertionError("short payload was accepted")


def test_explicit_y8_zero_point_round_trip() -> None:
    source = np.array([[0, 127, 128, 255]], dtype=np.uint8)
    encoded = encode_y8_to_int8(source, zero_point=128)
    np.testing.assert_array_equal(encoded, [[-128, -1, 0, 127]])
    np.testing.assert_array_equal(
        decode_int8_to_y8(encoded, zero_point=128), source
    )


def test_padding_dependent_geometry() -> None:
    source = FrameGeometry(360, 640, 1)
    assert network_output_geometry(source, padding="same") == FrameGeometry(
        720, 1280, 1
    )
    assert network_output_geometry(source, padding="valid") == FrameGeometry(
        708, 1268, 1
    )


def main() -> None:
    test_hwc_byte_order_round_trip()
    test_payload_length_rejected()
    test_explicit_y8_zero_point_round_trip()
    test_padding_dependent_geometry()
    print("DRIVER_LAYOUT_TEST_PASS tests=4")


if __name__ == "__main__":
    main()

