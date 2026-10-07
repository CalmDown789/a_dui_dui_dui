import numpy as np
import pytest

from experiments.r0_4k_quality_20261006.evaluate_fusion import (
    blend_y,
    candidate_specs,
    edge_tile_weight_map,
    tile_activity,
)


def test_global_blend_endpoints_and_half_up_rounding():
    base = np.array([[0, 10, 255]], dtype=np.uint8)
    r0 = np.array([[255, 11, 0]], dtype=np.uint8)
    assert np.array_equal(blend_y(base, r0, 0.0), base)
    assert np.array_equal(blend_y(base, r0, 1.0), r0)
    assert np.array_equal(blend_y(np.array([[0]], dtype=np.uint8), np.array([[1]], dtype=np.uint8), 0.5),
                          np.array([[1]], dtype=np.uint8))


@pytest.mark.parametrize("alpha", [-0.01, 1.01, float("nan")])
def test_blend_rejects_invalid_alpha(alpha):
    frame = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(ValueError):
        blend_y(frame, frame, alpha)


def test_tile_activity_and_weight_map_are_deterministic_and_bounded():
    lr = np.zeros((540, 960), dtype=np.uint8)
    lr[:, 480:] = 255
    activity = tile_activity(lr)
    weights = edge_tile_weight_map(lr, 50, 0.0, 0.75)
    assert activity.shape == (9, 16)
    assert weights.shape == (2160, 3840)
    assert np.all((weights >= 0) & (weights <= 1))
    assert np.std(activity) > 0
    assert np.array_equal(weights, edge_tile_weight_map(lr, 50, 0.0, 0.75))


def test_candidate_grid_has_five_global_and_eight_tiled_recipes():
    specs = candidate_specs()
    assert len(specs) == 13
    assert sum(spec["kind"] == "global" for spec in specs) == 5
    assert sum(spec["kind"] == "edge_tile" for spec in specs) == 8
    assert len({spec["candidate_id"] for spec in specs}) == len(specs)
