"""Regression tests for shared intrinsic routing, without Blender."""
import unittest

import numpy as np

from dsg.frame_geodesic_paths import NoValidSurfaceRoute, route_surface_vertices


def folded_surface_graph():
    # Nearly coincident endpoints in 3D are distant along the folded surface.
    xyz = np.array([[0, 0, 0], [0, 0, 3], [3, 0, 3], [3, 0, 0], [0.2, 0, 0]], float)
    connections = [(0, 1), (1, 2), (2, 3), (3, 4)]
    adjacency = [[] for _ in xyz]
    for a, b in connections:
        length = float(np.linalg.norm(xyz[a] - xyz[b]))
        adjacency[a].append((b, length))
        adjacency[b].append((a, length))
    offsets, targets, weights = [0], [], []
    for row in adjacency:
        targets.extend(v for v, _ in row)
        weights.extend(w for _, w in row)
        offsets.append(len(targets))
    return xyz, offsets, targets, weights


class GeodesicPathsTests(unittest.TestCase):
    def test_no_euclidean_shortcut_across_fold(self):
        args = folded_surface_graph()
        path = route_surface_vertices(*args, 0, 4)
        self.assertEqual(path.vertex_indices, (0, 1, 2, 3, 4))
        self.assertGreater(path.surface_length_mm, 10.0)
        self.assertLess(np.linalg.norm(path.points_mm[0] - path.points_mm[-1]), 0.3)

    def test_blocked_corridor_has_no_straight_fallback(self):
        args = folded_surface_graph()
        with self.assertRaisesRegex(NoValidSurfaceRoute, "NO_VALID_SURFACE_ROUTE"):
            route_surface_vertices(*args, 0, 4, allowed_mask=[True, True, False, True, True])

    def test_protected_endpoints_remain_protected(self):
        args = folded_surface_graph()
        with self.assertRaises(NoValidSurfaceRoute):
            route_surface_vertices(*args, 0, 4, allowed_mask=[False, True, True, True, True])

    def test_deterministic_for_same_graph(self):
        args = folded_surface_graph()
        left = route_surface_vertices(*args, 0, 4)
        right = route_surface_vertices(*args, 0, 4)
        self.assertEqual(left.vertex_indices, right.vertex_indices)
        self.assertEqual(left.weighted_cost, right.weighted_cost)

    def test_bad_edge_weight_is_rejected(self):
        xyz, offsets, dst, weights = folded_surface_graph()
        weights[0] = 0.02
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            route_surface_vertices(xyz, offsets, dst, weights, 0, 4)

    def test_same_vertex_has_zero_length(self):
        path = route_surface_vertices(*folded_surface_graph(), 2, 2)
        self.assertEqual(path.vertex_indices, (2,))
        self.assertEqual(path.surface_length_mm, 0.0)

    def test_same_vertex_cannot_bypass_blocked_endpoint(self):
        with self.assertRaises(NoValidSurfaceRoute):
            route_surface_vertices(*folded_surface_graph(), 2, 2, allowed_mask=[True, True, False, True, True])


if __name__ == "__main__":
    unittest.main()
