import unittest,numpy as np
class ExtradosTests(unittest.TestCase):
 def test_rotating_axis_rotates_exterior_result(self):
  from dsg.axial_extrados import lift_offsets
  p=np.array([[1,2,0],[3,4,0]],float);h=np.array([2.,3.]);r=np.array([.5,.5]);rot=np.array([[1,0,0],[0,0,-1],[0,1,0]],float)
  a=lift_offsets(p,h,r,[0,0,1],[]);b=lift_offsets(p@rot.T,h,r,rot@[0,0,1],[])
  np.testing.assert_allclose(b,a@rot.T,atol=1e-10)
 def test_incompatible_sleeve_ceiling_fails_instead_of_using_contact_side(self):
  from dsg.axial_extrados import lift_offsets
  sleeve=dict(id='S1',center=[0,0,0],entry_axis=[0,0,1],height_mm=1.)
  with self.assertRaisesRegex(ValueError,'NO_EXTERIOR_SPACE'):lift_offsets(np.array([[0,0,0],[1,0,0]]),[2,2],[.6,.6],[0,0,1],[sleeve])
 def test_all_sleeves_constrain_full_radius(self):
  from dsg.axial_extrados import lift_offsets
  sleeves=[dict(id='S1',center=[0,0,0],entry_axis=[0,0,1],height_mm=10.),dict(id='S2',center=[0,0,0],entry_axis=[0,0,1],height_mm=6.)]
  result=lift_offsets(np.array([[0,0,0],[1,0,0]]),[8,8],[.5,.5],[0,0,1],sleeves)
  self.assertTrue(np.all(result[:,2]+.5<=2.95+1e-8));self.assertTrue(np.all(result[:,2]>.5))
