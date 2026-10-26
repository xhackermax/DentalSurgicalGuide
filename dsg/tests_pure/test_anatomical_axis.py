import unittest,numpy as np
class AnatomicalAxisTests(unittest.TestCase):
 def test_anatomical_basis_rotates_with_the_case(self):
  from dsg.axial_radial_web import axis_basis
  n=np.array([.2,-.1,1.]);n/=np.linalg.norm(n);x=np.array([1.,.2,.1]);angle=.9
  r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
  first=axis_basis(n,preferred=x);second=axis_basis(r@n,preferred=r@x)
  np.testing.assert_allclose(second,r@first,atol=1e-12)
