"""Blender-free regression for experimental group-wise geodesic topology interface."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


class GroupAnalysisAdapterTests(unittest.TestCase):
    def run_adapter(self, duplicate=False, hard_safe=True):
        routes = [
            {"candidate": "CAND_S1_P1_ATT5", "beam_indices": [0, 1]},
            {"candidate": "CAND_S1_P1_ATT6" if not duplicate else "CAND_S1_P1_ATT5",
             "beam_indices": [2, 3]},
        ]
        model = dict(
            nodes=[], elements=[object() for _ in range(4)],
            load_cases=[], monitor_nodes=[], config="CFG",
            keep_out=None, geodesic_routes=routes,
        )
        captured = {}
        def prune(nodes, elements, loads, monitors, groups, **kwargs):
            captured["groups"] = groups
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                active_groups=("CAND_S1_P1_ATT5",),
                removed_groups=("CAND_S1_P1_ATT6",),
                material_volume_mm3=10., compliance_Nmm=2.,
                balanced_objective=0.72, max_utilization=0.45,
                max_displacement_mm=0.11, iterations=({"removed_group":"CAND_S1_P1_ATT6"},),
            )
        source = Path(__file__).resolve().parents[1] / "frame_structural.py"
        tree = ast.parse(source.read_text("utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "analyze_geodesic_group_topology")
        module = ast.Module(body=[function], type_ignores=[])
        ast.fix_missing_locations(module)
        env = {
            "bpy": SimpleNamespace(context="fake"),
            "_fem_build_geodesic_model": lambda context: model,
            "fem": SimpleNamespace(optimize_reinforcement=lambda *_a, **_kw:
                                   SimpleNamespace(hard_safe=hard_safe)),
            "geodesic_groups": SimpleNamespace(prune_geodesic_groups=prune),
        }
        exec(compile(module, str(source), "exec"), env)
        result = env["analyze_geodesic_group_topology"]("fake")
        return result, captured

    def test_candidate_identity_is_preserved_per_attachment(self):
        r, captured = self.run_adapter()
        self.assertEqual(len(captured["groups"]), 2)
        self.assertEqual(captured["groups"]["CAND_S1_P1_ATT5"], (0,1))
        self.assertEqual(captured["kwargs"]["stiffness_weight"], 0.5)
        self.assertEqual(captured["kwargs"]["min_remaining_groups"], 2)
        self.assertEqual(len(r["removed_groups"]), 1)
        self.assertFalse(r["geometry_mutated"])
        self.assertFalse(r["post_boolean_validated"])

    def test_duplicate_route_group_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "DUPLICATED_GEODESIC_GROUP_LABEL"):
            self.run_adapter(duplicate=True)

    def test_failed_baseline_never_runs_pruning(self):
        with self.assertRaisesRegex(RuntimeError, "BASELINE_FEM_UNSAFE"):
            self.run_adapter(hard_safe=False)


if __name__ == "__main__":
    unittest.main()
