import sys,unittest,numpy as np
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);import dsg;dsg.register();import bpy
from dsg.blender.organic_reinforcement import certify_generated_contacts
from dsg.blender.sleeve_attachment import certify_sleeve_attachment
from dsg.blender.generative_frame import _export_mesh
class GrowthPhysicalContactTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for x in [0.,.6]:
   bpy.ops.mesh.primitive_cube_add(size=2,location=(x,0,0));o=bpy.context.object;self.objects.append(o)
   modifier=o.modifiers.new('triangles','TRIANGULATE');bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=modifier.name)
 def tearDown(self):
  from dsg import guide_module as g
  for o in self.objects:g.safe_remove_object_with_data(o)
 def test_contact_is_allowed_only_at_declared_local_joint(self):
  new=dict(route_id='new',origin='J',port='N',points_mm=[[0,0,0],[0,3,0]],radius_mm=1.)
  old=dict(route_id='old',origin='F',port='P',nodes={'J':[0,0,0]},radius_mm=1.)
  certify_generated_contacts(bpy.context,new,self.objects[1],[old],[self.objects[0]])
  new['origin']='undeclared'
  with self.assertRaisesRegex(ValueError,'UNDECLARED_CONTACT'):certify_generated_contacts(bpy.context,new,self.objects[1],[old],[self.objects[0]])
 def test_remote_contact_cannot_use_an_unrelated_joint_label(self):
  new=dict(route_id='new',origin='J',port='N',points_mm=[[20,0,0],[20,3,0]],radius_mm=.5)
  old=dict(route_id='old',origin='F',port='P',nodes={'J':[20,0,0]},radius_mm=.5)
  with self.assertRaisesRegex(ValueError,'UNDECLARED_CONTACT'):certify_generated_contacts(bpy.context,new,self.objects[1],[old],[self.objects[0]])
 def test_positive_overlap_witness_is_local_to_requested_endpoint(self):
  a,b=(_export_mesh(bpy.context,o)for o in self.objects)
  self.assertTrue(certify_sleeve_attachment(*a,*b)['positive_volume_overlap'])
  with self.assertRaises(ValueError):certify_sleeve_attachment(*a,*b,near_point_mm=[20,0,0],maximum_witness_distance_mm=1.)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GrowthPhysicalContactTests)).wasSuccessful():raise SystemExit(1)
