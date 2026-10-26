"""Alt+H reveals current clinical references, never other-stage machinery."""
import sys,unittest,json
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core,guide_module as g
from dsg.blender import workflow_visibility as w,mpr_view

class WorkflowRevealTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for name in ('IOS','PassiveBackup','DSG_AxisMPR_Test','Guide','Implant'):
   bpy.ops.mesh.primitive_cube_add()
   obj=bpy.context.object;obj.name=name;self.objects.append(obj)
  self.model,self.passive,self.plane,self.guide,self.implant=self.objects
  self.passive.hide_set(True);self.passive.hide_select=True
  self.plane.hide_set(True);self.plane.hide_select=True
  self.implant.hide_select=True
  bpy.context.scene.dsg_props['current_step']=g.STEP_IRRIGATION
  w.capture(bpy.context)
  self.before=[(o.data.as_pointer(),len(o.data.vertices),o.matrix_world.copy()) for o in self.objects]
 def tearDown(self):
  for obj,before in zip(self.objects,self.before):
   self.assertEqual((obj.data.as_pointer(),len(obj.data.vertices),obj.matrix_world),before)
   bpy.data.objects.remove(obj,do_unlink=True)
  bpy.context.scene.pop(mpr_view.ACTIVE_KEY,None)
 def reveal(self):
  w.reveal(bpy.context)
 def test_h_reveal_keeps_other_stage_objects_hidden_and_evaluated(self):
  self.model.hide_set(True)
  self.reveal()
  self.assertFalse(self.model.hide_get())
  self.assertFalse(self.model.hide_select)
  self.assertTrue(self.passive.hide_get());self.assertTrue(self.plane.hide_get())
  self.assertFalse(self.passive.hide_viewport)
  evaluated=self.passive.evaluated_get(bpy.context.evaluated_depsgraph_get())
  self.assertEqual(len(evaluated.data.vertices),8)
 def test_existing_toggle_disabled_model_can_be_recovered(self):
  self.model.hide_viewport=True;self.model.hide_select=True;self.model.hide_set(True)
  self.reveal()
  self.assertFalse(self.model.hide_viewport);self.assertFalse(self.model.hide_get())
  self.assertFalse(self.model.hide_select)
 def test_readonly_current_reference_can_be_revealed(self):
  self.implant.hide_set(True);self.reveal()
  self.assertFalse(self.implant.hide_get());self.assertTrue(self.implant.hide_select)
 def test_hidden_new_technical_preview_is_protected(self):
  bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object
  try:
   obj.hide_select=True;obj.hide_set(True);self.reveal();self.assertTrue(obj.hide_get())
  finally:bpy.data.objects.remove(obj,do_unlink=True)
 def test_reference_rename_does_not_break_reveal(self):
  self.model.name='Renamed IOS';self.model.hide_set(True);self.reveal()
  self.assertFalse(self.model.hide_get())
 def test_mpr_hidden_ios_stays_hidden(self):
  bpy.context.scene[mpr_view.ACTIVE_KEY]=True
  self.model.hide_set(True);self.reveal();self.assertTrue(self.model.hide_get())
 def test_source_reused_as_current_frame_can_be_revealed(self):
  self.model['DSG_hidden_source']=True
  self.model.hide_set(True);self.reveal()
  self.assertFalse(self.model.hide_get())
 def test_direct_implant_return_refreshes_stage_allowlist(self):
  scene=bpy.context.scene
  scene.dsg_props['current_step']=g.STEP_CONTOUR
  w.capture(bpy.context)
  scene.dsg_props['current_step']=g.STEP_IMPLANT
  scene.dsg_props.model_obj=self.model
  try:
   with patch.object(g,'get_all_implant_objects',return_value=[]):
    self.assertTrue(g._restore_implant_planning_state(bpy.context,scene,{}))
   self.assertEqual(self.model.get(w.CONTEXT),w.stage_key(bpy.context))
   self.model.hide_set(True);self.reveal();self.assertFalse(self.model.hide_get())
  finally:scene.dsg_props.model_obj=None
 def test_capture_during_mpr_preserves_reference_for_after_close(self):
  scene=bpy.context.scene
  scene[mpr_view.ACTIVE_KEY]=True
  scene[mpr_view.HIDDEN_KEY]=json.dumps([self.model.name])
  self.model.hide_set(True)
  w.capture(bpy.context)
  self.reveal();self.assertTrue(self.model.hide_get())
  mpr_view.leave(bpy.context)
  self.model.hide_set(True);self.reveal()
  self.assertFalse(self.model.hide_get())
 def test_scope_and_keymap(self):
  ctx=SimpleNamespace(mode='OBJECT',area=SimpleNamespace(type='VIEW_3D'),scene=bpy.context.scene)
  with patch.object(core,'infer_stage',return_value=core.STAGE_ALIGNMENT):self.assertFalse(w.DSG_OT_RevealCurrentStage.poll(ctx))
  with patch.object(core,'infer_stage',return_value=core.STAGE_GUIDE):self.assertTrue(w.DSG_OT_RevealCurrentStage.poll(ctx))
  if bpy.context.window_manager.keyconfigs.addon:
   self.assertEqual(len(w.KEYMAPS),1)
   keymap,item=w.KEYMAPS[0]
   self.assertEqual(keymap.name,'Object Mode');self.assertTrue(item.alt);self.assertEqual(item.type,'H')

if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowRevealTests)).wasSuccessful():raise SystemExit(1)
print('WORKFLOW_REVEAL_PASS')
