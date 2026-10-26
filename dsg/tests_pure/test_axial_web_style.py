import unittest,numpy as np
class SparseOriginsTests(unittest.TestCase):
 def test_half_density_keeps_distal_routes_and_full_perimeter_coverage(self):
  from dsg.axial_web_style import sparse_origins
  rows=[dict(point=np.array([10*np.cos(i*2*np.pi/27),10*np.sin(i*2*np.pi/27),0]),distance=float(i+10),target='S1',vertex=i)for i in range(27)]
  selected=sparse_origins(rows,14);self.assertEqual(len(selected),14);self.assertIn(26,[r['vertex']for r in selected]);self.assertGreater(np.ptp(np.array([r['point']for r in selected]),axis=0)[:2].min(),19.)
 def test_two_independent_origins_per_sleeve_are_preserved(self):
  from dsg.axial_web_style import sparse_origins
  rows=[dict(point=np.array([float(i),float(i%3),0]),distance=float(10+i),target='S1'if i<6 else'S2',vertex=i)for i in range(12)]
  selected=sparse_origins(rows,6)
  for sid in ['S1','S2']:self.assertGreaterEqual(sum(r['target']==sid for r in selected),2)
