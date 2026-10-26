"""Compact screw MPR shares implant sampling, follows the trajectory and restores view."""
import sys,unittest,math
from types import SimpleNamespace
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_plane as m,mpr_view
m.register()

class MicroscrewMPRTests(unittest.TestCase):
 def setUp(self):
  bpy.ops.mesh.primitive_cube_add(size=2)
  self.screw=bpy.context.object;self.screw['DSG_microscrew_preview']=True
  self.screw['DSG_microscrew_axis']=(.6,0,.8)
  self.screw['DSG_stop_contact_world']=(3,5,1)
  self.screw['DSG_tip_final_world']=(9,5,9)
  self.pose=self.screw.matrix_world.copy()
  bpy.context.scene.dsg_props.current_step=g.STEP_FRAME
 def tearDown(self):
  for p in list(m.planes(bpy.context.scene)):m._remove(p)
  mpr_view.leave(bpy.context)
  bpy.data.objects.remove(self.screw,do_unlink=True)
 def test_plane_uses_implant_size_and_actual_screw_axis(self):
  with patch.object(m,'refresh',return_value=True):plane=m.create(bpy.context,self.screw)
  bpy.context.view_layer.update()
  self.assertLess(max(plane.dimensions),m.SIZE_MM+2*m.FRAME_MM+.001)
  self.assertLess((plane.matrix_world.translation-g._microscrew_center_world(self.screw)).length,1e-5)
  axis=(plane.matrix_world.to_3x3()@Vector((0,1,0))).normalized()
  self.assertGreater(abs(axis.dot(g._microscrew_axis_world(self.screw))),.99999)
  for degrees in (0,37,90):
   plane.dsg_implant_mpr_angle=math.radians(degrees);bpy.context.view_layer.update()
   axis=(plane.matrix_world.to_3x3()@Vector((0,1,0))).normalized()
   self.assertGreater(abs(axis.dot(g._microscrew_axis_world(self.screw))),.99999)
  self.assertEqual(self.screw.matrix_world,self.pose)
 def test_ghost_requested_in_frame_only_while_compact_plane_shown(self):
  with patch.object(m,'refresh',return_value=True):plane=m.create(bpy.context,self.screw)
  plane.hide_set(False)
  # Isolate view policy from the empty test case's workflow prerequisite clamp.
  context=SimpleNamespace(scene=SimpleNamespace(dsg_props=SimpleNamespace(current_step=g.STEP_FRAME),objects=bpy.context.scene.objects))
  self.assertTrue(mpr_view.wanted(context))
  self.assertTrue(mpr_view._keep(self.screw,g))
  plane.hide_set(True)
  self.assertFalse(mpr_view.wanted(context))
 def test_open_operator_reuses_compact_view_without_large_review(self):
  with patch.object(g,'_open_compact_microscrew_mpr',return_value=(True,'OK')) as compact:
   self.assertEqual(bpy.ops.dsg.open_or_center_microscrew_mpr(),{'FINISHED'})
   compact.assert_called_once()
 def test_rebuilt_screw_is_reattached_automatically(self):
  with patch.object(m,'refresh',return_value=True):plane=m.create(bpy.context,self.screw)
  plane.dsg_implant_mpr_angle=math.radians(37)
  name=self.screw.name;mesh=self.screw.data.copy();props=dict(self.screw.items())
  bpy.data.objects.remove(self.screw,do_unlink=True)
  self.screw=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(self.screw)
  for key,value in props.items():self.screw[key]=value
  self.screw.location=(20,30,40)
  self.screw['DSG_stop_contact_world']=(23,35,41)
  self.screw['DSG_tip_final_world']=(29,35,49)
  m._follow(bpy.context.scene)
  bpy.context.view_layer.update()
  constraint=next(c for c in plane.constraints if c.type=='CHILD_OF')
  self.assertEqual(constraint.target,self.screw)
  self.assertLess((plane.matrix_world.translation-g._microscrew_center_world(self.screw)).length,.001)
  self.assertAlmostEqual(plane.dsg_implant_mpr_angle,math.radians(37),places=5)
  self.assertIn(plane.name,m.STATE['pending'])
  self.assertFalse(plane.hide_get())
 def test_close_hides_compact_plane_and_ends_ghost(self):
  with patch.object(m,'refresh',return_value=True):plane=m.create(bpy.context,self.screw)
  mpr_view.enter(bpy.context)
  self.assertTrue(mpr_view.active(bpy.context.scene))
  g._close_dicom_review_for_guide(bpy.context)
  self.assertTrue(plane.hide_get())
  self.assertFalse(mpr_view.active(bpy.context.scene))

r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MicroscrewMPRTests))
if not r.wasSuccessful():raise SystemExit(1)
print('COMPACT_MICROSCREW_MPR_PASS')
