import numpy as np
import torch

from member_b.golden import pixel_shuffle_hwc_x2
from member_b.model import TinySR
from member_b.quantization import round_away_from_zero


def main() -> None:
    model = TinySR().eval()
    with torch.inference_mode():
        output = model(torch.zeros(1, 1, 16, 24))
    assert tuple(output.shape) == (1, 1, 32, 48)

    source = np.asarray([-2.5, -1.5, -0.5, 0.5, 1.5, 2.5])
    expected = np.asarray([-3, -2, -1, 1, 2, 3])
    np.testing.assert_array_equal(round_away_from_zero(source), expected)

    x = np.asarray([[[10, 20, 30, 40]]], dtype=np.int8)
    y = pixel_shuffle_hwc_x2(x)[:, :, 0]
    np.testing.assert_array_equal(y, np.asarray([[10, 20], [30, 40]], dtype=np.int8))
    print("SELF_TEST_PASS")


if __name__ == "__main__":
    main()

