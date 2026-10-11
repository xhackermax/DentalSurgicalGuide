"""Guard against Blender operator registration regressions in postponed-annotation files."""
import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExperimentalOperatorContracts(unittest.TestCase):
    def test_contact_props_are_real_blender_property_objects(self):
        path = ROOT / "frame_structural.py"
        parsed = ast.parse(path.read_text("utf-8"))
        operator = next(
            node for node in parsed.body
            if isinstance(node, ast.ClassDef) and node.name == "DSG_OT_EstimateGeodesicContact"
        )
        definitions = [
            node for node in operator.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__annotations__"
                    for target in node.targets)
        ]
        self.assertEqual(len(definitions), 1)
        mapping = definitions[0].value
        self.assertIsInstance(mapping, ast.Dict)
        self.assertEqual(len(mapping.keys), 5)
        self.assertTrue(all(isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                            and value.func.id == "FloatProperty" for value in mapping.values))

    def test_registered_operator_is_invoked_by_visible_workflow(self):
        src = (ROOT / "frame_structural.py").read_text("utf-8")
        ui = (ROOT / "_guide_parts/08_export_final_ui_registration.py").read_text("utf-8")
        self.assertIn("DSG_OT_EstimateGeodesicContact)", src)
        self.assertIn("'dsg.estimate_geodesic_contact'", ui)
        self.assertIn("'dsg.analyze_geodesic_groups'", ui)


if __name__ == "__main__":
    unittest.main()
