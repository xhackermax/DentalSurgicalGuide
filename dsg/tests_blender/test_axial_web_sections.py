import sys,unittest,numpy as np,bpy
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);sys.path.append(r'C:\Users\isaac pc masterrace\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\dsg_runtime\dsg_v910_blender52_py313\site-packages')
class SkinTests(unittest.TestCase):
 def test_thin_or_detached_geometry_cannot_certify_requested_sections(self):
  from dsg.blender.axial_web_mesh import validate_centerline_skin
  from dsg.blender.generative_frame import _export_mesh
  bpy.ops.mesh.primitive_cube_add(size=2);v,f=_export_mesh(bpy.context,bpy.context.object)
  def web(radius):return dict(pieces=[dict(points_mm=[[-.2,0,0],[.2,0,0]],point_radii_mm=[radius,radius])])
  self.assertTrue(validate_centerline_skin(web(.7),v,f)['valid'])
  with self.assertRaisesRegex(ValueError,'AXIAL_SECTION'):validate_centerline_skin(web(1.4),v,f)
  shifted=v+10
  with self.assertRaisesRegex(ValueError,'AXIAL_CENTERLINE_OUTSIDE'):validate_centerline_skin(web(.7),shifted,f)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SkinTests)).wasSuccessful():raise SystemExit(1)
