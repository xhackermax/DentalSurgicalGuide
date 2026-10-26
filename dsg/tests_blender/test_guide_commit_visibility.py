"""Guide replacements inherit clinical metadata, never archive/display state."""
import sys,unittest
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import workflow_visibility as w

class GuideCommitVisibilityTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for name in (g.GUIDE_NAME,'NewIrrigatedGuide',g.CLOSED_MODEL_NAME):
   bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name=name;self.objects.append(obj)
  self.original,self.new,self.model=self.objects
  self.original['DSG_sleeves_applied']=True
  self.original['DSG_sleeve_inner_diameter']=2.8
  self.original[w.CONTEXT]=w.stage_key(bpy.context)
  self.original[w.ALLOWED]=False
  self.original[w.SELECTABLE]=False
  bpy.context.scene.dsg_props.guide_obj=self.original
  bpy.context.scene.dsg_props['current_step']=g.STEP_IRRIGATION
 def tearDown(self):
  bpy.context.scene.dsg_props.guide_obj=None
  for obj in self.objects:bpy.data.objects.remove(obj,do_unlink=True)
 def commit(self):
  g._archive_current_guide_for_sleeve_rebuild(bpy.context.scene.dsg_props,reason='irrigation_commit')
  self.new.name=g.GUIDE_NAME
  g._inherit_dsg_custom_properties(self.original,self.new)
  g.register_dsg_object(self.new,g.ROLE_GUIDE,g.GUIDE_NAME)
  bpy.context.scene.dsg_props.guide_obj=self.new
 def test_clinical_metadata_survives_without_inheriting_archive_state(self):
  self.commit()
  self.assertTrue(self.new['DSG_sleeves_applied'])
  self.assertAlmostEqual(self.new['DSG_sleeve_inner_diameter'],2.8)
  for key in ('DSG_obsolete_hidden','DSG_archive_reason',w.CONTEXT,w.ALLOWED,w.SELECTABLE):self.assertNotIn(key,self.new)
  self.assertTrue(self.original['DSG_obsolete_hidden'])
 def test_replacement_is_shown_when_irrigation_view_is_restored(self):
  self.commit()
  self.new['DSG_irrigation_resolution']='APPLIED'
  with patch.object(g,'_workflow_model_candidate',return_value=self.model),patch.object(g,'get_all_implant_objects',return_value=[]):
   self.assertTrue(g._restore_workflow_stage(bpy.context,bpy.context.scene,g.STEP_IRRIGATION))
  self.assertTrue(self.new.visible_get())
  self.assertTrue(self.new.get(w.ALLOWED))
  self.assertFalse(self.original.visible_get())
  self.new.hide_set(True);w.reveal(bpy.context)
  self.assertTrue(self.new.visible_get());self.assertFalse(self.original.visible_get())
 def test_explicit_excludes_still_preserve_source(self):
  self.original['DSG_clinical_keep']=17
  g._inherit_dsg_custom_properties(self.original,self.new,exclude_keys={'DSG_clinical_keep'})
  self.assertNotIn('DSG_clinical_keep',self.new)
  self.assertEqual(self.original['DSG_clinical_keep'],17)

if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuideCommitVisibilityTests)).wasSuccessful():raise SystemExit(1)
print('GUIDE_COMMIT_VISIBILITY_PASS')
