from __future__ import annotations

import numpy as np

from member_a.artifacts import MEMBER_A_ACCEPTANCE_VECTOR_CASES, _vector_inputs


def test_a03_boundary_extreme_vectors_cover_edges_and_pixel_extremes():
    vectors = _vector_inputs()
    assert tuple(vectors) == MEMBER_A_ACCEPTANCE_VECTOR_CASES

    edge = vectors["edge_impulses"]
    assert edge.shape == (54, 96)
    assert set(np.unique(edge)) == {0, 255}
    expected_points = {
        (0, 0), (0, 95), (53, 0), (53, 95),
        (0, 48), (53, 48), (27, 0), (27, 95),
    }
    actual_points = set(zip(*np.where(edge == 255)))
    assert actual_points == expected_points

    checker = vectors["checkerboard_extremes"]
    assert checker.shape == (54, 96)
    assert set(np.unique(checker)) == {0, 255}
    yy, xx = np.indices(checker.shape)
    np.testing.assert_array_equal(checker, (((xx + yy) & 1) * 255).astype(np.uint8))
    assert {int(checker[0, 0]), int(checker[0, -1]), int(checker[-1, 0]), int(checker[-1, -1])} == {0, 255}
