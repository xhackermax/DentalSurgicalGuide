"""The existing model action and Blender selection target the irrigation IOS."""
import sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import clinical_materials

class IrrigationIOSHideTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for name in ('TestIrrIOS','TestIrrPassive','TestIrrGuide','TestIrrImplant'):
   bpy.ops.mesh.primitive_cube_add()
   obj=bpy.context.object;obj.name=name;self.objects.append(obj)
  self.model,self.passive,self.guide,self.implant=self.objects
  self.passive.hide_set(True)
  bpy.context.scene.dsg_props['current_step']=g.STEP_IRRIGATION
  self.poses=[o.matrix_world.copy() for o in self.objects]
 def tearDown(self):
  for o,pose in zip(self.objects,self.poses):
   self.assertEqual(o.matrix_world,pose)
   bpy.data.objects.remove(o,do_unlink=True)
 def toggle(self):
  with patch.object(g,'_workflow_model_candidate',return_value=self.model),patch.object(g,'get_blockout_visibility_objects',return_value=[self.passive]),patch.object(g,'get_passive_model_obj',return_value=self.passive),patch.object(g,'_dsg_report'):
   self.assertEqual(g.DSG_OT_ToggleBlockoutVisibility.execute(SimpleNamespace(as_pointer=lambda:123456789),bpy.context),{'FINISHED'})
 def test_reference_can_be_selected_for_normal_blender_hiding(self):
  g._show_irrigation_references(bpy.context,self.model,[self.implant],self.guide)
  self.assertFalse(self.model.hide_select)
  self.assertTrue(self.implant.hide_select)
 def test_existing_toggle_hides_visible_ios_without_showing_passive(self):
  self.toggle()
  self.assertTrue(self.model.hide_get())
  self.assertTrue(self.passive.hide_get())
  self.assertFalse(self.guide.hide_get())
  self.assertFalse(self.implant.hide_get())
 def test_existing_toggle_restores_ios_independently(self):
  self.model.hide_set(True)
  self.toggle()
  self.assertFalse(self.model.hide_get())
  self.assertTrue(self.passive.hide_get())
 def test_material_sync_respects_manual_hide(self):
  self.model.hide_set(True)
  with patch.object(g,'_workflow_model_candidate',return_value=self.model),patch.object(g,'get_confirmed_passive_model_obj',return_value=self.passive),patch.object(g,'_workflow_guide_candidate',return_value=self.guide),patch.object(g,'get_all_implant_objects',return_value=[self.implant]),patch('dsg.core.infer_stage',return_value='DSG'):
   clinical_materials.sync(bpy.context)
  self.assertTrue(self.model.hide_get())

if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IrrigationIOSHideTests)).wasSuccessful():raise SystemExit(1)
print('IRRIGATION_IOS_HIDE_PASS')
