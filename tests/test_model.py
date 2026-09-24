import pytest
import torch

from member_a.model import FSRCNNSubpixel, mac_breakdown


def test_model_shape_and_intermediates():
    model = FSRCNNSubpixel().eval()
    with torch.no_grad():
        stages = model.forward_with_intermediates(torch.zeros(1, 1, 54, 96))
    assert stages["feature"].shape == (1, 16, 54, 96)
    assert stages["shrink"].shape == (1, 8, 54, 96)
    assert stages["mapping0"].shape == (1, 8, 54, 96)
    assert stages["expand"].shape == (1, 16, 54, 96)
    assert stages["subpixel_phases"].shape == (1, 4, 54, 96)
    assert stages["output"].shape == (1, 1, 108, 192)


def test_frozen_mac_count():
    values = mac_breakdown()
    assert values["feature"] == 207_360_000
    assert values["shrink"] == 66_355_200
    assert values["mapping"] == 298_598_400
    assert values["expand"] == 66_355_200
    assert values["subpixel"] == 829_440_000
    assert values["total"] == 1_468_108_800
    assert values["gmac_per_second_30fps"] == pytest.approx(44.043264)
    assert values["margin_vs_133_2_gmac_s"] == pytest.approx(3.0242992376)
