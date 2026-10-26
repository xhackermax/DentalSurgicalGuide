"""MPR centering must request Update before using a changed pending screw."""
import sys,math,unittest
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g

class UpdateNoticeTests(unittest.TestCase):
 def setUp(self):
  bpy.ops.mesh.primitive_cube_add(size=2,location=(10,20,30))
  self.obj=bpy.context.object
  self.obj['DSG_microscrew_preview']=True
  self.obj['DSG_microscrew_visual_preview']=True
  self.obj['DSG_microscrew_axis']=(0,0,1)
  self.obj['DSG_microscrew_contact_local_z_mm']=.5
  self.obj['DSG_microscrew_sleeve_top']=(10,20,30.5)
  bpy.context.scene.dsg_props.microscrew_preview_obj=self.obj
 def tearDown(self):
  bpy.context.scene.dsg_props.microscrew_preview_obj=None
  bpy.data.objects.remove(self.obj,do_unlink=True)
 def center(self):return bpy.ops.dsg.center_selected_microscrew_mpr()
 def assert_notice(self):
  with patch.object(g,'_open_compact_microscrew_mpr',return_value=(True,'OK')) as center,patch.object(g,'_dsg_report') as report:
   self.assertEqual(self.center(),{'CANCELLED'})
   center.assert_not_called()
   self.assertEqual(report.call_args.args[1],{'WARNING'})
   self.assertIn('Actualizar',report.call_args.args[3])
 def test_translation_requires_update_and_does_not_center(self):
  self.obj.location.x+=2;bpy.context.view_layer.update()
  self.assert_notice()
 def test_tilt_requires_update_and_does_not_center(self):
  self.obj.rotation_euler.y=math.radians(10);bpy.context.view_layer.update()
  self.assert_notice()
 def test_clean_pose_allows_center_and_respects_contact_offset(self):
  with patch.object(g,'_open_compact_microscrew_mpr',return_value=(True,'OK')) as center:
   self.assertEqual(self.center(),{'FINISHED'});center.assert_called_once()
 def test_updated_trajectory_clears_notice(self):
  self.obj.location.x+=2;self.obj.rotation_euler.y=math.radians(10);bpy.context.view_layer.update()
  axis=(self.obj.matrix_world.to_3x3()@Vector((0,0,1))).normalized()
  self.obj['DSG_microscrew_axis']=list(axis)
  self.obj['DSG_microscrew_sleeve_top']=list(self.obj.matrix_world.translation+axis*.5)
  with patch.object(g,'_open_compact_microscrew_mpr',return_value=(True,'OK')) as center:
   self.assertEqual(self.center(),{'FINISHED'});center.assert_called_once()

r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UpdateNoticeTests))
if not r.wasSuccessful():raise SystemExit(1)
print('MICROSCREW_UPDATE_NOTICE_PASS')
