"""Implants remain visible as fixed references during irrigation editing."""
import sys,unittest
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g

class IrrigationImplantVisibilityTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for name,role in [(g.IMPLANT_PREFIX+'IrrigationTest',g.ROLE_IMPLANT),(g.GUIDE_NAME,g.ROLE_GUIDE),(g.CLOSED_MODEL_NAME,g.ROLE_MODEL)]:
   bpy.ops.mesh.primitive_cube_add(size=2)
   obj=bpy.context.object;obj.name=name;obj['dental_suite_dsg_role']=role;self.objects.append(obj)
  self.implant,self.guide,self.model=self.objects
  self.implant.location=(10,20,30);bpy.context.view_layer.update()
  self.pose=self.implant.matrix_world.copy()
  bpy.context.scene.dsg_props.guide_obj=self.guide
 def tearDown(self):
  bpy.context.scene.dsg_props.guide_obj=None
  for obj in self.objects:bpy.data.objects.remove(obj,do_unlink=True)
 def restore(self,step):
  with patch.object(g,'get_all_implant_objects',return_value=[self.implant]),patch.object(g,'_workflow_guide_candidate',return_value=self.guide),patch.object(g,'_hide_retained_guide_sources'),patch.object(g,'_workflow_model_candidate',return_value=self.model):
   self.assertTrue(g._restore_workflow_stage(bpy.context,bpy.context.scene,step))
 def test_irrigation_restores_implant_as_fixed_visual_reference(self):
  self.implant.hide_set(True)
  self.restore(g.STEP_IRRIGATION)
  self.assertTrue(self.implant.visible_get())
  self.assertTrue(self.implant.hide_select)
  self.assertEqual(self.implant.matrix_world,self.pose)
  self.assertTrue(self.guide.visible_get())
 def test_irrigation_visibility_survives_repeated_stage_restore(self):
  self.restore(g.STEP_IRRIGATION)
  self.implant.hide_set(True)
  self.restore(g.STEP_IRRIGATION)
  self.assertTrue(self.implant.visible_get())
  self.assertEqual(self.implant.matrix_world,self.pose)
 def test_ios_is_visible_and_the_three_objects_have_distinct_colors(self):
  self.model.hide_set(True)
  poses={obj.name:obj.matrix_world.copy() for obj in self.objects}
  self.restore(g.STEP_IRRIGATION)
  self.assertTrue(self.model.visible_get())
  self.assertFalse(self.model.hide_select)
  colors=[]
  for obj in self.objects:
   self.assertTrue(obj.material_slots and obj.material_slots[0].material)
   colors.append(tuple(obj.material_slots[0].material.diffuse_color))
   self.assertEqual(obj.matrix_world,poses[obj.name])
  self.assertEqual(len(set(colors)),3)
 def test_ios_stays_visible_for_reinforcement_review(self):
  self.restore(g.STEP_IRRIGATION)
  self.restore(g.STEP_REINFORCEMENT)
  self.assertTrue(self.model.visible_get())
  self.assertFalse(self.model.hide_select)
  self.restore(g.STEP_DRILL)
  self.assertFalse(self.model.visible_get())
 def test_reinforcement_keeps_its_existing_visibility_policy(self):
  self.restore(g.STEP_REINFORCEMENT)
  self.assertFalse(self.implant.visible_get())

 def test_irrigation_helpers_follow_their_step_in_both_directions(self):
  helpers=[]
  for name in (g.IRR_PREVIEW_PATH_PREFIX+'UnitTest',g.IRR_LUMEN_DIAGNOSTIC_NAME):
   bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name=name
   if name==g.IRR_LUMEN_DIAGNOSTIC_NAME:obj['DSG_irrigation_lumen_diagnostic']=True
   helpers.append(obj)
  try:
   for step in (g.STEP_IRRIGATION,g.STEP_REINFORCEMENT,g.STEP_DRILL,g.STEP_FINAL_CUT,g.STEP_NAME,g.STEP_IRRIGATION,g.STEP_CONTOUR,g.STEP_MODEL):
    self.restore(step)
    for helper in helpers:
     self.assertEqual(helper.visible_get(),step==g.STEP_IRRIGATION,(step,helper.name))
  finally:
   for obj in helpers:bpy.data.objects.remove(obj,do_unlink=True)

r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IrrigationImplantVisibilityTests))
if not r.wasSuccessful():raise SystemExit(1)
print('IRRIGATION_IMPLANT_VISIBILITY_PASS')
