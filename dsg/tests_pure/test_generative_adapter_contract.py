"""Whole-operator registration/transport obligations without requiring bpy."""
import ast,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class AdapterContractTests(unittest.TestCase):
    def test_operator_delegates_to_background_generation(self):
        tree=ast.parse((ROOT/'frame_structural.py').read_text('utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DSG_OT_OptimizeFrameFEM')
        execute=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
        text=ast.unparse(execute)
        self.assertIn('generative_frame.start(context)',text)
        self.assertNotIn('create_fem_reinforcements(context',text)

    def test_undo_stops_generation_before_releasing_ids(self):
        text=(ROOT/'workflow_history.py').read_text('utf-8')
        self.assertIn('generative_frame.freeze_for_undo()',text)

    def test_review_controls_registered_with_structural_module(self):
        text=(ROOT/'frame_structural.py').read_text('utf-8')
        self.assertIn('generative_frame.CLASSES',text)
        panel=(ROOT/'_guide_parts/08_export_final_ui_registration.py').read_text('utf-8')
        self.assertIn('generative_frame.draw_review(b, context)',panel)

if __name__=='__main__':unittest.main()
