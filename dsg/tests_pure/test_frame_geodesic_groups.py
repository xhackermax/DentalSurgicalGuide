"""Pure FEM group pruning regression: atomic paths and no orphan-node failures."""
import unittest

import numpy as np

from dsg import frame_fem_core as fem
from dsg.frame_geodesic_groups import InvalidGeodesicGroups, prune_geodesic_groups


class GeodesicGroupPruningTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [
            fem.Node([0, 0, 0], [True]*6, "KEEP_IN_SUPPORT"),
            fem.Node([4, 0, 0], [False]*6, "LOAD"),
            fem.Node([0, 4, 0], [True]*6, "KEEP_IN_SUPPORT"),
            fem.Node([2, 0, 0], [False]*6, "GEODESIC_PATH"),
        ]
        self.e = [
            fem.BeamElement(0, 3, 1.2, tag="PRIMARY:SEG0", prunable=False),
            fem.BeamElement(3, 1, 1.2, tag="PRIMARY:SEG1", prunable=False),
            fem.BeamElement(0, 2, 1.2, tag="WASTE:SEG0", prunable=False),
        ]
        self.groups = {"PRIMARY": [0, 1], "WASTE": [2]}
        self.loads = [fem.LoadCase("LATERAL", forces={1:np.array([0,0,-0.1])})]
        self.cfg = fem.OptimizationConfig(
            displacement_limit_mm=1,
            displacement_design_target_mm=1,
        )

    def run_optimizer(self, **kwargs):
        return prune_geodesic_groups(
            self.nodes, self.e, self.loads, [1], self.groups,
            config=self.cfg, **kwargs)

    def test_deletes_waste_group_without_disconnecting_primary(self):
        report = self.run_optimizer()
        self.assertEqual(report.active_groups, ("PRIMARY",))
        self.assertEqual(report.removed_groups, ("WASTE",))
        self.assertLess(report.balanced_objective, 1)
        self.assertTrue(all(b.active for b in self.e))
        self.assertEqual(len(report.iterations), 1)

    def test_compacts_orphan_free_nodes_when_entire_chain_deleted(self):
        result = self.run_optimizer()
        self.assertEqual(result.removed_groups, ("WASTE",))
        self.assertGreater(result.compliance_Nmm, 0)

    def test_constrained_min_group_count_keeps_everything(self):
        result = self.run_optimizer(min_remaining_groups=2)
        self.assertEqual(result.removed_groups, ())
        self.assertEqual(result.active_groups, ("PRIMARY", "WASTE"))

    def test_group_overlap_rejected(self):
        self.groups["WASTE"] = [1, 2]
        with self.assertRaisesRegex(InvalidGeodesicGroups, "multiple"):
            self.run_optimizer()

    def test_a_group_cannot_be_only_a_piece_of_a_curve(self):
        self.groups["PRIMARY"] = [0]
        with self.assertRaisesRegex(InvalidGeodesicGroups, "unclassified"):
            self.run_optimizer()

    def test_non_finite_weight_rejected(self):
        with self.assertRaises(ValueError):
            self.run_optimizer(stiffness_weight=float("nan"))


if __name__ == "__main__":
    unittest.main()
