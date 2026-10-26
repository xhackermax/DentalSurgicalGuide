import unittest,numpy as np
from dsg.section_geometry import raster_sections

def box(lo,hi):
 v=np.array([[x,y,z] for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])],float)
 f=np.array([[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]])
 return v,f

class Sections(unittest.TestCase):
 def test_true_sections_not_a_projection(self):
  v,f=box((-1,-1,-1),(1,1,1));grid=np.arange(-1.5,1.6,.5)
  mask=raster_sections(v,f,grid,grid,np.array([-.75,.25,1.25]))
  self.assertTrue(mask[0,3,3]);self.assertTrue(mask[1,3,3]);self.assertFalse(mask[2].any())
  self.assertFalse(mask[0,0,0])
 def test_inner_hole_is_not_filled_by_rasterizer(self):
  a,fa=box((-2,-2,-1),(2,2,1));b,fb=box((-.6,-.6,-1),(.6,.6,1))
  grid=np.arange(-2.5,2.6,.25)
  mask=raster_sections(np.vstack((a,b)),np.vstack((fa,fb+8)),grid,grid,[0.])[0]
  self.assertFalse(mask[10,10]);self.assertTrue(mask[10,15])
 def test_disconnected_parts_are_preserved(self):
  a,fa=box((-2,-1,-1),(-1,1,1));b,fb=box((1,-1,-1),(2,1,1));grid=np.arange(-3,3.1,.25)
  mask=raster_sections(np.vstack((a,b)),np.vstack((fa,fb+8)),grid,grid,[0.])[0]
  self.assertFalse(mask[12,12]);self.assertTrue(mask[12,6]);self.assertTrue(mask[12,18])
if __name__=='__main__':unittest.main()
