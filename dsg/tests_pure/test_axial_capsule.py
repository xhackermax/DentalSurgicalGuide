import unittest,numpy as np
class CapsuleTests(unittest.TestCase):
 def test_taper_contains_every_intermediate_ball(self):
  from dsg.axial_capsule import capsule_sdf
  a=np.array([0.,0.,0.]);b=np.array([1.,.3,.1]);directions=np.random.default_rng(3).normal(size=(150,3));directions/=np.linalg.norm(directions,axis=1)[:,None]
  for t in np.linspace(0,1,15):
   r=.8*(1-t)+.3*t;points=a*(1-t)+b*t+directions*r
   self.assertLessEqual(capsule_sdf(points,a,b,.8,.3).max(),1e-10)
 def test_nested_sweep_is_the_larger_endpoint_ball(self):
  from dsg.axial_capsule import capsule_sdf
  p=np.array([[1.,0,0],[0,2.,0],[0,0,0]]);a=np.zeros(3);b=np.array([.1,0,0])
  np.testing.assert_allclose(capsule_sdf(p,a,b,.2,1.),np.linalg.norm(p-b,axis=1)-1.,atol=1e-12)
 def test_straight_capsule_retains_end_caps_and_outside(self):
  from dsg.axial_capsule import capsule_sdf
  p=np.array([[0,1,0],[-1,0,0],[3,0,0],[1,0,0]])
  np.testing.assert_allclose(capsule_sdf(p,np.zeros(3),np.array([2.,0,0]),1.,1.),[0,0,0,-1],atol=1e-12)
