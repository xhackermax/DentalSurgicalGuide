import sys,unittest,numpy as np
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);sys.path.append(r'C:\Users\isaac pc masterrace\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\dsg_runtime\dsg_v910_blender52_py313\site-packages')
class FrameSmoothingTests(unittest.TestCase):
 def test_shared_frame_curve_removes_triangulation_chatter_and_preserves_endpoints(self):
  from dsg.blender.axial_frame_smoothing import frame_curve
  points=np.array([[i*.3,.12*(-1)**i,2.]for i in range(81)]);smooth=np.array(frame_curve(points));np.testing.assert_allclose(smooth[[0,-1]],points[[0,-1]],atol=1e-6)
  self.assertLess(np.max(np.abs(smooth[3:-3,1])),.12);self.assertGreater(len(smooth),10)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FrameSmoothingTests)).wasSuccessful():raise SystemExit(1)
