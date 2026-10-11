"""Blender-free contract tests for provisional surface-contact FEM diagnostics."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dsg import frame_contact_core as core


class Vec(tuple):
    def __new__(cls, values):
        return super().__new__(cls, [float(x) for x in values])


class SurfaceContactAdapterTests(unittest.TestCase):
    def run_model(self, points=None, feasible=True):
        points = points or [[-1, 0, 1], [0, 0, 0], [1, 0, 0], [2, 0, 1]]
        elements = [SimpleNamespace(radius_mm=1.0) for _ in range(len(points) - 1)]
        model = {
            "elements": elements,
            "nodes": [],
            "load_cases": [],
            "monitor_nodes": [],
            "config": None,
            "keep_out": lambda *_a: False,
            "geodesic_routes": [{
                "candidate": "GEO_TEST",
                "beam_indices": list(range(len(elements))),
                "curve_points_mm": points,
            }],
        }
        original = [list(p) for p in points]
        def projection(cache, point, max_distance_mm):
            if abs(point[2]) > max_distance_mm:
                return None
            return {
                "point": Vec(point),
                "normal": Vec([0, 0, 1]),
                "distance_mm": 0,
            }
        guide = SimpleNamespace(
            _build_frame_surface_graph_cache=lambda context, passive: ({}, True, ""),
            _frame_surface_projection=projection,
        )
        source = Path(__file__).resolve().parents[1] / "frame_structural.py"
        tree = ast.parse(source.read_text("utf8"))
        fn = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                  and item.name == "estimate_geodesic_frame_contact")
        partial = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(partial)
        env = dict(
            bpy=SimpleNamespace(context="fake"),
            _fem_build_geodesic_model=lambda context: model,
            _passive_obj=lambda context: object(),
            guide_module=guide,
            fem=SimpleNamespace(optimize_reinforcement=lambda *_a, **_kw:
                                SimpleNamespace(hard_safe=feasible)),
            contact_core=core, Vector=Vec, np=np,
        )
        exec(compile(partial, str(source), "exec"), env)
        result = env["estimate_geodesic_frame_contact"](
            "fake",
            policy=core.ContactPolicy(0.8, 0.6, 0.3, 0.01, 0.7),
        )
        self.assertEqual(points, original)
        return result

    def test_only_on_surface_sections_are_counted(self):
        report = self.run_model()
        self.assertEqual(report["feasible_routes"], 1)
        self.assertEqual(report["routes"][0]["surface_samples"], 2)
        self.assertGreater(report["contact_area_planar_estimate_mm2"], 0)
        self.assertFalse(report["post_boolean_validated"])
        self.assertFalse(report["retention_validated"])
        self.assertFalse(report["torsion_after_boolean_validated"])

    def test_nominal_fem_failure_is_not_turned_into_safe_status(self):
        report = self.run_model(feasible=False)
        self.assertFalse(report["hard_safe_nominal_fem"])
        self.assertFalse(report["post_boolean_validated"])

    def test_disconnected_surface_samples_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "CONTACT_SURFACE_ROUTE_INCOMPLETE"):
            self.run_model(points=[[0, 0, 0], [1, 0, 1], [2, 0, 0]])


if __name__ == "__main__":
    unittest.main()
