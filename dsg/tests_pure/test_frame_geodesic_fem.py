"""Surface-curved FEM member tests, without Blender."""
import unittest

import numpy as np

from dsg import frame_fem_core as fem
from dsg.frame_geodesic_fem import InvalidBeamPath, append_geodesic_beams


class GeodesicFEMTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [
            fem.Node([0, 0, 0], [True] * 6, "KEEP_IN_SUPPORT"),
            fem.Node([2, 0, 0], [False] * 6, "LOAD"),
        ]
        self.elements = []
        self.template = fem.BeamElement(i=0, j=1, radius_mm=1, tag="SOURCE")

    def test_curved_path_yields_consecutive_beams_not_a_chord(self):
        path = [[0, 0, 0], [0, 1, 0], [1, 1, 0], [2, 0, 0]]
        indices = append_geodesic_beams(
            self.nodes, self.elements, path, start_node=0, end_node=1,
            beam_template=self.template, label="GEO_1")
        self.assertEqual(len(indices), 3)
        self.assertEqual([(e.i, e.j) for e in self.elements], [(0, 2), (2, 3), (3, 1)])
        self.assertTrue(all(not e.prunable for e in self.elements))
        self.assertEqual(self.template.tag, "SOURCE")
        self.assertAlmostEqual(sum(np.linalg.norm(self.nodes[e.i].xyz - self.nodes[e.j].xyz)
                                   for e in self.elements), 2 + np.sqrt(2))

    def test_bad_endpoints_do_not_mutate_network(self):
        with self.assertRaisesRegex(InvalidBeamPath, "support differs"):
            append_geodesic_beams(self.nodes, self.elements, [[3, 0, 0], [2, 0, 0]],
                start_node=0, end_node=1, beam_template=self.template, label="GEO_1")
        self.assertEqual(len(self.nodes), 2)
        self.assertEqual(self.elements, [])

    def test_long_chord_is_rejected_not_silently_straightened(self):
        with self.assertRaisesRegex(InvalidBeamPath, "GEODESIC_SEGMENT_TOO_LONG"):
            append_geodesic_beams(self.nodes, self.elements, [[0, 0, 0], [2, 0, 0]],
                start_node=0, end_node=1, beam_template=self.template, label="GEO_1",
                max_segment_mm=0.7)
        self.assertEqual(len(self.nodes), 2)
        self.assertEqual(self.elements, [])

    def test_no_duplicate_nodes(self):
        with self.assertRaisesRegex(InvalidBeamPath, "duplicate"):
            append_geodesic_beams(self.nodes, self.elements,
                [[0, 0, 0], [0, 0, 0], [2, 0, 0]],
                start_node=0, end_node=1, beam_template=self.template, label="GEO_1")


if __name__ == "__main__":
    unittest.main()
