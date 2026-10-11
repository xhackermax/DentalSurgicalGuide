"""Test DSG's Blender adapter geodesic model in a Blender-free harness."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dsg import frame_fem_core as fem, frame_geodesic_fem
from dsg import frame_swept_clearance_core as swept_clearance
from dsg import frame_sleeve_junction_core as sleeve_junction


class Vec(tuple):
    def __new__(cls, values):
        return tuple.__new__(cls, (float(x) for x in values))

    def __sub__(self, other):
        return Vec(a - b for a, b in zip(self, other))

    @property
    def length(self):
        return float(np.linalg.norm(self))

    def dot(self, other):
        return sum(a * b for a, b in zip(self, other))


class ExperimentalAdapterTests(unittest.TestCase):
    def create(self, fail_routes=False):
        nodes = [
            fem.Node([0, 0, 0], [True] * 6, "KEEP_IN_SUPPORT"),
            fem.Node([0, 2, 0], [True] * 6, "KEEP_IN_SUPPORT"),
            fem.Node([2, 0, 0], [False] * 6, "LOAD"),
        ]
        base = {
            "nodes": nodes,
            "elements": [fem.BeamElement(0, 2, 1.0, tag="CAND_A"),
                         fem.BeamElement(1, 2, 1.0, tag="CAND_B")],
            "load_cases": [fem.LoadCase("FAKE")],
            "monitor_nodes": [2],
            "keep_out": lambda *_a: False,
            "config": fem.OptimizationConfig(),
            "frame_context": {"sleeves": [{
                "id": "S1", "center": [5, 0, 0], "axis": [0, 0, 1],
                "inner_radius_mm": 2.1, "outer_radius_mm": 3.0,
                "height_mm": 7.0, "lumen_keep_out": True,
            }]},
            "sleeve_records": [{"id": "S1", "attachment_nodes": [2]}],
        }
        cache = {"coords": [], "csr_offsets": [], "csr_dst": [], "csr_weights": []}
        guide = SimpleNamespace(
            _valid_obj=lambda obj: True,
            _build_frame_surface_graph_cache=lambda *_a: (cache, False, ""),
            _frame_width_surface_bvh=lambda *_a: (object(), None, None, ""),
            _frame_surface_projection=lambda _cache, point, **_kw: {
                "point": Vec(point),
                "normal": Vec([0, 0, 1]),
                "triangle_vertices": (0, 1, 2),
            },
        )
        seen = []

        def route(_coords, _off, _dst, _length, _ids0, p0, _ids1, p1):
            seen.append((tuple(p0), tuple(p1)))
            if fail_routes:
                raise ValueError("NO_VALID_SURFACE_ROUTE: intentionally blocked")
            mid = (np.asarray(p0) + np.asarray(p1)) / 2
            mid[2] += 0.4
            return SimpleNamespace(points_mm=np.asarray([p0, mid, p1], float),
                                   surface_length_mm=3.5, backend="FAKE_SURFACE_GRAPH")
        source = Path(__file__).resolve().parents[1] / "frame_structural.py"
        tree = ast.parse(source.read_text("utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_fem_build_geodesic_model")
        module = ast.Module(body=[function], type_ignores=[])
        ast.fix_missing_locations(module)
        env = {
            "bpy": SimpleNamespace(context="mock"),
            "_fem_build_model": lambda context, geodesic_candidates: base,
            "_passive_obj": lambda context: object(),
            "guide_module": guide,
            "geodesic_paths": SimpleNamespace(
                route_surface_face_anchors=route,
                NoValidSurfaceRoute=ValueError,
            ),
            "geodesic_fem": frame_geodesic_fem,
            "swept_clearance": swept_clearance,
            "sleeve_junction": sleeve_junction,
            "fem": fem,
            "np": np,
            "math": __import__("math"),
            "Vector": Vec,
        }
        exec(compile(module, str(source), "exec"), env)
        return env["_fem_build_geodesic_model"], base, seen

    def test_replaces_straight_candidates_with_fem_beam_paths(self):
        fn, base, seen = self.create()
        model = fn("mock")
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(model["geodesic_routes"]), 2)
        self.assertGreater(len(model["elements"]), 2)
        self.assertTrue(all(element.tag.startswith("CAND_") and ":SEG" in element.tag
                            for element in model["elements"]))
        self.assertTrue(all(not element.prunable for element in model["elements"]))
        self.assertFalse(model["config"].enable_topology_growth)
        self.assertEqual(model["route_mode"], "SURFACE_GEODESIC_EXPERIMENTAL_READ_ONLY")
        self.assertGreater(len(model["nodes"]), 3)


    def test_swept_lumen_blocks_a_colliding_tube_not_just_centerline(self):
        fn, base, seen = self.create()
        base["frame_context"] = {"sleeves": [{
            "id": "S1", "lumen_keep_out": True,
            "center": [0, 0, 0], "axis": [0, 0, 1],
            "inner_radius_mm": 1.4, "outer_radius_mm": 2.0,
            "height_mm": 6.0
        }]}
        with self.assertRaisesRegex(RuntimeError, "NO_VALID_GEODESIC_FEM_MODEL"):
            fn("mock")
        self.assertEqual(len(seen), 2)

    def test_swept_clearance_reports_which_explicit_zones_are_checked(self):
        fn, base, seen = self.create()
        base["frame_context"] = {"sleeves": [{
            "id": "S1", "lumen_keep_out": True,
            "center": [5, 0, 0], "axis": [0, 0, 1],
            "inner_radius_mm": 0.4, "outer_radius_mm": 3.0,
            "height_mm": 6.0
        }]}
        model=fn("mock")
        self.assertTrue(all(route["post_boolean_lumen_validation_required"]
                            and not route["final_lumen_clear"]
                            for route in model["geodesic_routes"]))
        self.assertTrue(all(route["swept_lumen_zone_count"] == 1
                            for route in model["geodesic_routes"]))
        self.assertTrue(all(not route["whole_anatomy_sweep_validated"]
                            for route in model["geodesic_routes"]))

    def test_invalid_intrinsic_routes_fail_instead_of_using_chords(self):
        fn, base, seen = self.create(fail_routes=True)
        with self.assertRaisesRegex(RuntimeError, "NO_VALID_GEODESIC_FEM_MODEL"):
            fn("mock")
        self.assertEqual(len(seen), 2)


if __name__ == "__main__":
    unittest.main()
