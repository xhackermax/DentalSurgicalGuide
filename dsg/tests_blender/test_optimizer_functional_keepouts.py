"""Missing saved functional cuts must fail closed and preserve the scene."""
import sys,tempfile,unittest,json
from pathlib import Path
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import functional_keepouts as k,generative_frame as gf
class FunctionalKeepoutTests(unittest.TestCase):
 def setUp(self):
  bpy.ops.mesh.primitive_cube_add();self.guide=bpy.context.object
  self.before=set(bpy.data.objects);self.width=bpy.context.scene.dsg_props.sleeve_lateral_opening_width
  self.paths=bpy.context.scene.dsg_props.irr_paths_json
  bpy.context.scene.dsg_props.irr_paths_json='[]'
 def tearDown(self):
  self.assertEqual(set(bpy.data.objects),self.before)
  self.assertEqual(bpy.context.scene.dsg_props.sleeve_lateral_opening_width,self.width)
  bpy.context.scene.dsg_props.irr_paths_json=self.paths
  bpy.data.objects.remove(self.guide,do_unlink=True)
 def run_export(self):
  with tempfile.TemporaryDirectory() as folder:return k.export_missing(bpy.context,self.guide,folder,gf._export_mesh)
 def test_no_applied_cuts_need_no_functional_volumes(self):self.assertEqual(self.run_export(),[])
 def test_missing_irrigation_paths_are_not_treated_as_clearance(self):
  self.guide['DSG_irrigation_resolution']='APPLIED';self.guide['DSG_irrigation_saved_path_count']=1
  with self.assertRaisesRegex(ValueError,'trayectos'):self.run_export()
 def test_missing_lateral_records_are_rejected(self):
  self.guide['DSG_sleeve_lateral_opening']=True
  with self.assertRaisesRegex(ValueError,'posición guardada'):self.run_export()
 def test_malformed_lateral_records_do_not_leave_temporary_objects(self):
  self.guide['DSG_sleeve_lateral_opening']=True;self.guide['DSG_sleeve_lateral_opening_records']='bad json'
  with self.assertRaises(ValueError):self.run_export()
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FunctionalKeepoutTests)).wasSuccessful():raise SystemExit(1)
print('OPTIMIZER_FUNCTIONAL_KEEPOUTS_PASS')
