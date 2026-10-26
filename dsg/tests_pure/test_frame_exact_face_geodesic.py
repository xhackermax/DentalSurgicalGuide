"""Exact-face geodesic tests against folded triangulated surfaces."""
import unittest

import numpy as np

from dsg.frame_geodesic_paths import NoValidSurfaceRoute, route_surface_face_anchors


def folded_sheet():
    # The end triangles are close in 3D but only connected around the fold.
    xyz = np.asarray([
        [0, 0, 0],   # 0 first face
        [0, 0, 3],   # 1 first face
        [3, 0, 3],   # 2 bend
        [3, 0, 0],   # 3 final face
        [0.2, 0, 0], # 4 end near start in Euclidean space
        [0, 1, 0],   # 5 first face
        [3, 1, 0],   # 6 final face
    ], dtype=float)
    edges = [(0, 1), (1, 2), (2, 3), (3, 4),
             (0, 5), (1, 5), (3, 6), (4, 6)]
    graph = [[] for _ in xyz]
    for i, j in edges:
        length = float(np.linalg.norm(xyz[i] - xyz[j]))
        graph[i].append((j, length))
        graph[j].append((i, length))
    offsets, dst, weights = [0], [], []
    for adj in graph:
        dst.extend(j for j, length in adj)
        weights.extend(length for j, length in adj)
        offsets.append(len(dst))
    return xyz, offsets, dst, weights


class ExactFaceGeodesicTests(unittest.TestCase):
    def route(self, **kwargs):
        return route_surface_face_anchors(
            *folded_sheet(), [0, 1, 5], [0, 0.10, 0.10],
            [3, 4, 6], [0.48, 0.10, 0], **kwargs)

    def test_exact_anchors_preserved_without_euclidean_shortcut(self):
        result = self.route()
        np.testing.assert_allclose(result.points_mm[0], [0, 0.1, 0.1])
        np.testing.assert_allclose(result.points_mm[-1], [0.48, 0.1, 0])
        self.assertGreater(result.surface_length_mm, 6.0)
        self.assertLess(np.linalg.norm(result.points_mm[0] - result.points_mm[-1]), 0.6)

    def test_protected_corridor_fail_closed(self):
        with self.assertRaisesRegex(NoValidSurfaceRoute, "NO_VALID_SURFACE_ROUTE"):
            self.route(allowed_mask=[True, True, False, True, True, True, True])

    def test_protected_anchor_face_fails(self):
        with self.assertRaisesRegex(NoValidSurfaceRoute, "protected face"):
            self.route(allowed_mask=[False, True, True, True, True, True, True])

    def test_anchor_must_be_on_triangle(self):
        with self.assertRaisesRegex(NoValidSurfaceRoute, "surface triangle"):
            route_surface_face_anchors(
                *folded_sheet(), [0, 1, 5], [0.3, 0, 0],
                [3, 4, 6], [0.48, 0.10, 0])

    def test_same_triangle_direct_is_surface_valid(self):
        a, o, d, w = folded_sheet()
        p = route_surface_face_anchors(
            a, o, d, w, [0, 1, 5], [0, 0.2, 0.2],
            [5, 0, 1], [0, 0.3, 0.25])
        self.assertEqual(p.backend, "SAME_TRIANGLE")
        self.assertEqual(len(p.points_mm), 2)

    def test_malformed_edge_length_rejected(self):
        xyz, offsets, dst, weights = folded_sheet()
        weights[0] *= 0.5
        with self.assertRaisesRegex(ValueError, "edge length"):
            route_surface_face_anchors(
                xyz, offsets, dst, weights, [0, 1, 5], [0, 0.10, 0.10],
                [3, 4, 6], [0.48, 0.10, 0])

    def test_determinism(self):
        a, b = self.route(), self.route()
        self.assertEqual(a.vertex_indices, b.vertex_indices)
        self.assertEqual(a.weighted_cost, b.weighted_cost)


if __name__ == "__main__":
    unittest.main()
