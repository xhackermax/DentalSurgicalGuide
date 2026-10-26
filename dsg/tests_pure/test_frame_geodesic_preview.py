"""Blender-free transactional tests for viewport-only geodesic FEM previews."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


class FakeCurve(dict):
    def __init__(self, name, npoints, old=False):
        super().__init__(DSG_geodesic_preview_only=old)
        self.name = name
        self.hide_render = False
        self._hidden = False
        self.data = SimpleNamespace(splines=[
            SimpleNamespace(points=[SimpleNamespace(radius=0.0) for _ in range(npoints)])
        ])

    def hide_set(self, hidden):
        self._hidden = bool(hidden)

    def hide_get(self):
        return self._hidden


class Registry(list):
    def get(self, name):
        return next((obj for obj in self if obj.name == name), None)


class FakePreview:
    def __init__(self, fail=None):
        self.objects = Registry([FakeCurve("DSG_GeodesicFEM_Preview_000", 2, old=True)])
        self.old = self.objects[0]
        self.fail = fail
        self.count = 0
        self.elements = [SimpleNamespace(radius_mm=1.0), SimpleNamespace(radius_mm=1.25)]
        self.routes = [
            {"candidate": "A", "curve_points_mm": [[0, 0, 0], [0, 1, 0], [0, 2, 0]],
             "beam_indices": [0, 1]},
            {"candidate": "B", "curve_points_mm": [[1, 0, 0], [1, 1, 0], [1, 2, 0]],
             "beam_indices": [0, 1]},
        ]
        self.model = {
            "nodes": [], "elements": self.elements, "load_cases": [],
            "monitor_nodes": [], "config": None, "keep_out": lambda *_a: False,
            "geodesic_routes": self.routes, "rejected_geodesic_routes": [],
        }

    def make_curve(self, context, name, points, **kwargs):
        self.count += 1
        if self.fail == "curve" and self.count == 2:
            raise RuntimeError("mock curve creation failure")
        obj = FakeCurve(name, len(points))
        self.objects.append(obj)
        return obj

    def run(self):
        source = Path(__file__).resolve().parents[1] / "frame_structural.py"
        tree = ast.parse(source.read_text("utf-8"))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "preview_geodesic_fem_paths")
        mod = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(mod)
        guide = SimpleNamespace(
            create_poly_curve_object=self.make_curve,
            _valid_obj=lambda obj: obj in self.objects,
            safe_remove_object=lambda obj: self.objects.remove(obj),
        )
        globals_ = {
            "bpy": SimpleNamespace(context="fake", data=SimpleNamespace(objects=self.objects)),
            "_fem_build_geodesic_model": lambda context: self.model,
            "fem": SimpleNamespace(optimize_reinforcement=lambda *_a, **_k: "fake"),
            "_fem_summary": lambda model, result: {"active_reinforcements": 2},
            "guide_module": guide,
            "Vector": tuple,
            "_DSG_LOG": SimpleNamespace(warning=lambda *_a, **_kw: None),
        }
        exec(compile(mod, str(source), "exec"), globals_)
        return globals_["preview_geodesic_fem_paths"]()


class PreviewSafetyTests(unittest.TestCase):
    def test_success_replaces_only_old_preview_and_marks_as_nonexportable(self):
        f = FakePreview()
        summary = f.run()
        self.assertEqual(len(f.objects), 2)
        self.assertNotIn(f.old, f.objects)
        self.assertEqual({obj.name for obj in f.objects},
                         {"DSG_GeodesicFEM_Preview_000", "DSG_GeodesicFEM_Preview_001"})
        self.assertTrue(all(obj.hide_render for obj in f.objects))
        self.assertTrue(all(obj["DSG_geodesic_preview_only"] for obj in f.objects))
        self.assertTrue(all(not obj["DSG_geodesic_post_boolean_validated"] for obj in f.objects))
        self.assertFalse(summary["guide_geometry_mutated"])
        self.assertTrue(summary["preview_only"])

    def test_second_curve_failure_preserves_previous_preview(self):
        f = FakePreview(fail="curve")
        with self.assertRaisesRegex(RuntimeError, "mock curve"):
            f.run()
        self.assertEqual(f.objects, [f.old])
        self.assertEqual(f.old.name, "DSG_GeodesicFEM_Preview_000")
        self.assertFalse(f.old.hide_get())

    def test_mismatched_model_refuses_to_create_preview(self):
        f = FakePreview()
        f.routes[0]["beam_indices"] = [0]
        with self.assertRaisesRegex(RuntimeError, "GEODESIC_PREVIEW_FEM_MISMATCH"):
            f.run()
        self.assertEqual(f.objects, [f.old])


if __name__ == "__main__":
    unittest.main()
