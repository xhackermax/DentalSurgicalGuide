import unittest
import numpy as np

class SurfaceFairingTests(unittest.TestCase):
 def test_concave_strut_junction_becomes_a_continuous_patch(self):
  from dsg.axial_surface_fairing import fair_union_field
  x=np.arange(-2.5,2.51,.025);xx,yy=np.meshgrid(x,x,indexing='ij');field=np.minimum(np.abs(xx)-1.,np.abs(yy)-1.).astype(np.float32)
  smooth=fair_union_field(field,.025,.625)
  i=int(np.argmin(abs(x-1.1)));self.assertLess(smooth[i,i],0.)
  # The hard diagonal crease has a gradient jump; the fair patch removes it.
  grad=np.gradient(smooth,.025);jump=np.linalg.norm([grad[0][i,i+1]-grad[0][i+1,i],grad[1][i,i+1]-grad[1][i+1,i]])
  self.assertLess(jump,.2)
 def test_straight_strut_keeps_its_original_diameter(self):
  from dsg.axial_surface_fairing import fair_union_field
  x=np.arange(-2.,2.01,.025);xx,yy=np.meshgrid(x,x,indexing='ij');field=(np.sqrt(xx*xx+yy*yy)-1.).astype(np.float32)
  smooth=fair_union_field(field,.025,.625);band=np.abs(field)<.2;np.testing.assert_allclose(smooth[band],field[band],atol=1.e-6)
 def test_no_erosion_of_the_original_struts(self):
  from dsg.axial_surface_fairing import fair_union_field
  x=np.arange(-2.,2.01,.05);xx,yy=np.meshgrid(x,x,indexing='ij');field=np.minimum(np.abs(xx)-1.,np.abs(yy)-.625).astype(np.float32)
  smooth=fair_union_field(field,.05,.625);self.assertTrue(np.all(smooth<=field+1.e-7))
