"""Insertion controls retain their saved direction while excluded by Blender."""
import ast,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from mathutils import Matrix,Vector
args=sys.argv[sys.argv.index('--')+1:]
class HiddenAxisTests(unittest.TestCase):
 def test_unparented_hidden_control_uses_its_saved_basis(self):
  for root in args:
   path=Path(root)/'_guide_parts/02_implant_animation_geometry_a.py'
   node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='get_insertion_axis')
   expected=Vector((.24,.32,.915)).normalized();basis=expected.to_track_quat('Z','Y').to_matrix().to_4x4()
   control=SimpleNamespace(parent=None,constraints=[],matrix_basis=basis,matrix_world=Matrix.Identity(4))
   scope={'Vector':Vector,'get_axis_empty':lambda:control};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
   self.assertGreater(scope['get_insertion_axis']().dot(expected),.999999)
 def test_parented_and_constrained_controls_keep_world_transform(self):
  for root in args:
   path=Path(root)/'_guide_parts/02_implant_animation_geometry_a.py'
   node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='get_insertion_axis')
   for parent,constraints in [(object(),[]),(None,[object()])]:
    control=SimpleNamespace(parent=parent,constraints=constraints,matrix_basis=Matrix.Rotation(1.,4,'X'),matrix_world=Matrix.Identity(4))
    scope={'Vector':Vector,'get_axis_empty':lambda:control};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    self.assertGreater(scope['get_insertion_axis']().dot(Vector((0,0,1))),.999999)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HiddenAxisTests)).wasSuccessful():raise SystemExit(1)
