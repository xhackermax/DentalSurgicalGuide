import sys, unittest
from unittest.mock import patch
import bpy
sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g, core, alignment_module as alignment
from dsg.blender import clinical_materials as cm, mpr_view, virtual_extraction

class ClinicalDisplayTests(unittest.TestCase):
 def setUp(self):
  self.objs=[]
  for name in ('TestIOS','TestPassive','TestGuide','TestImplant','TestBone','TestFill'):
   bpy.ops.mesh.primitive_cube_add()
   obj=bpy.context.object;obj.name=name;self.objs.append(obj)
  self.model,self.passive,self.guide,self.implant,self.bone,self.fill=self.objs
  self.geometry=[(o.data.as_pointer(),len(o.data.vertices),o.matrix_world.copy()) for o in self.objs]
 def tearDown(self):
  for o,before in zip(self.objs,self.geometry):
   self.assertEqual((o.data.as_pointer(),len(o.data.vertices),o.matrix_world),before)
  for o in self.objs:bpy.data.objects.remove(o,do_unlink=True)
 def sync(self,step,route=core.ROUTE_SIMPLE):
  bpy.context.scene.dsg_props['current_step']=step
  for obj in self.objs:
   obj.hide_viewport=False;obj.hide_set(False)
  bpy.context.view_layer.update()
  with patch.object(core,'infer_stage',return_value=core.STAGE_GUIDE),patch.object(g,'_workflow_model_candidate',return_value=self.model),patch.object(g,'get_confirmed_passive_model_obj',return_value=self.passive),patch.object(g,'_workflow_guide_candidate',return_value=self.guide),patch.object(g,'get_all_implant_objects',return_value=[self.implant]),patch.object(mpr_view,'_bones',return_value=[self.bone]),patch.object(virtual_extraction,'required',return_value=(route==core.ROUTE_IMMEDIATE)),patch.object(virtual_extraction,'targets',return_value=[11]),patch.object(virtual_extraction,'bones_for',return_value=[self.bone]):
   cm.sync(bpy.context)
 def alpha(self,obj):return obj.material_slots[0].material.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value
 def test_both_routes_reference_and_hardware_policy(self):
  for route in (core.ROUTE_SIMPLE,core.ROUTE_IMMEDIATE):
   for step in (g.STEP_IMPLANT,g.STEP_CONTOUR,g.STEP_FRAME,g.STEP_SLEEVE,g.STEP_IRRIGATION):
    self.sync(step,route)
    self.assertAlmostEqual(self.alpha(self.model),.35)
    self.assertAlmostEqual(self.alpha(self.implant),1)
    self.assertAlmostEqual(self.alpha(self.guide),.35 if step in {g.STEP_IRRIGATION,g.STEP_REINFORCEMENT} else 1)
   self.assertAlmostEqual(self.alpha(self.bone),.35)
 def test_drill_and_final_seating_then_drawing(self):
  for step in (g.STEP_IRRIGATION,g.STEP_REINFORCEMENT,g.STEP_DRILL,g.STEP_FINAL_CUT):
   self.sync(step)
   self.assertAlmostEqual(self.alpha(self.guide),.35)
   self.assertAlmostEqual(self.alpha(self.model),.35 if step in {g.STEP_IRRIGATION,g.STEP_REINFORCEMENT} else 1)
  for step in (g.STEP_NAME,):
   self.sync(step)
   self.assertAlmostEqual(self.alpha(self.guide),1)
   self.assertAlmostEqual(self.alpha(self.model),1)
 def test_retention_reference_only_fill_stays_opaque(self):
  with patch.object(g,'BLOCKOUT_NAME',self.fill.name):
   self.sync(g.STEP_MODEL)
  self.assertAlmostEqual(self.alpha(self.model),.35)
  self.assertEqual(len(self.fill.material_slots),0)
 def test_no_noise_no_physical_transmission_and_palette(self):
  self.sync(g.STEP_IRRIGATION)
  for obj,kind in ((self.model,'IOS'),(self.implant,'IMPLANT'),(self.guide,'GUIDE')):
   mat=obj.material_slots[0].material;bsdf=mat.node_tree.nodes.get('Principled BSDF')
   self.assertEqual(mat.surface_render_method,'BLENDED')
   self.assertTrue(bsdf.inputs['Thin Wall'].default_value)
   self.assertEqual(bsdf.inputs['Transmission Weight'].default_value,0)
   self.assertEqual(bsdf.inputs['Subsurface Weight'].default_value,0)
   for a,b in zip(mat.diffuse_color[:3],cm.PALETTE[kind]):self.assertAlmostEqual(a,b)
 def test_anatomy_preserves_rgb_original_material_and_linked_mesh(self):
  original=bpy.data.materials.new('OriginalLabels');original.diffuse_color=(.7,.2,.1,1)
  self.bone.data.materials.append(original)
  original_color=tuple(original.diffuse_color)
  linked=self.bone.copy();bpy.context.collection.objects.link(linked)
  try:
   cm.anatomy(self.bone)
   self.assertEqual(linked.material_slots[0].material,original)
   self.assertEqual(tuple(original.diffuse_color),original_color)
   self.assertAlmostEqual(self.bone.material_slots[0].material.diffuse_color[0],.7)
   mat=self.bone.material_slots[0].material;cm.anatomy(self.bone)
   self.assertEqual(self.bone.material_slots[0].material,mat)
  finally:bpy.data.objects.remove(linked,do_unlink=True)
 def test_ghost_uses_same_thinwall_method(self):
  mat=mpr_view._ghost_material();node=mat.node_tree.nodes.get('Principled BSDF')
  self.assertEqual(mat.surface_render_method,'BLENDED')
  self.assertAlmostEqual(node.inputs['Alpha'].default_value,mpr_view.GHOST_COLOR[3])
  self.assertTrue(node.inputs['Thin Wall'].default_value)
 def test_alignment_review_and_marking_materials(self):
  self.model['DSG_alignment_thin_review']=True
  alignment.ensure_ios_gray_material(self.model)
  self.assertAlmostEqual(self.alpha(self.model),.35)
  self.model.pop('DSG_alignment_thin_review')
  alignment.ensure_ios_gray_material(self.model)
  self.assertAlmostEqual(self.alpha(self.model),1)

suite=unittest.defaultTestLoader.loadTestsFromTestCase(ClinicalDisplayTests)
if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
print('CLINICAL_THINWALL_PASS')

