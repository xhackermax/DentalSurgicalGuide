import sys,unittest,tempfile,json,numpy as np
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);sys.path.extend([r'C:\Users\isaac pc masterrace\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\dsg_runtime\dsg_v910_blender52_py313\site-packages'])
import bpy
class DesignSheetTests(unittest.TestCase):
 def test_ring_frame_produces_distributed_cells_over_its_opening(self):
  from dsg.blender.axial_design_sheet import generate_sheet_trace
  from dsg.blender.generative_frame import _export_mesh
  with tempfile.TemporaryDirectory()as folder:
   folder=Path(folder);bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,-1));ios=bpy.context.object;ios.scale=(18,18,1);bpy.context.view_layer.update()
   v,f=_export_mesh(bpy.context,ios);np.savez(folder/'ios.npz',vertices=v,triangles=f)
   bpy.ops.mesh.primitive_torus_add(major_radius=12,minor_radius=1,location=(0,0,2));frame=bpy.context.object;v,f=_export_mesh(bpy.context,frame);np.savez(folder/'frame.npz',vertices=v,triangles=f)
   r=dict(surface_file=str(folder/'ios.npz'),frame_support_file=str(folder/'frame.npz'),radius_mm=1.,surface_matrix=np.eye(4).tolist(),reinforcement_envelope=dict(frame_entry_axis=[0,0,1]),sleeves=[dict(id='S1',center=[0,0,0],axis=[0,0,1],entry_axis=[0,0,1],height_mm=12.,outer_radius_mm=2.5,inner_radius_mm=1.5)])
   web=generate_sheet_trace(r,lambda _:None)
   self.assertGreaterEqual(web['report']['cycle_count'],15);self.assertGreaterEqual(web['report']['frame_origin_count'],10)
   self.assertTrue(all(p[2]>.5 for p in web['nodes'].values()));self.assertEqual(web['report']['used_sleeves'],['S1'])
   points=np.asarray(list(web['nodes'].values()));self.assertGreater(np.ptp(points,axis=0)[:2].min(),18.)
 def test_rotated_two_sleeves_receive_distal_upper_frame_routes(self):
  from dsg.blender.axial_design_sheet import generate_sheet_trace
  from dsg.blender.generative_frame import _export_mesh
  from mathutils import Quaternion,Vector
  rotation=np.array(Quaternion(Vector((.2,.8,.4)).normalized(),1.1).to_matrix());axis=rotation@np.array([0.,0.,1.]);matrix=np.eye(4);matrix[:3,:3]=rotation
  with tempfile.TemporaryDirectory()as directory:
   folder=Path(directory);bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,-1));ios=bpy.context.object;ios.scale=(18,18,1);bpy.context.view_layer.update();v,f=_export_mesh(bpy.context,ios);np.savez(folder/'ios.npz',vertices=v@rotation.T,triangles=f)
   bpy.ops.mesh.primitive_torus_add(major_radius=12,minor_radius=1,location=(0,0,2));v,f=_export_mesh(bpy.context,bpy.context.object);np.savez(folder/'frame.npz',vertices=v@rotation.T,triangles=f)
   sleeves=[dict(id=sid,center=(rotation@np.array([x,0.,0.])).tolist(),axis=axis.tolist(),entry_axis=axis.tolist(),height_mm=12.,outer_radius_mm=2.5,inner_radius_mm=1.5)for sid,x in [('S1',-5.),('S2',5.)]]
   request=dict(surface_file=str(folder/'ios.npz'),frame_support_file=str(folder/'frame.npz'),radius_mm=1.,surface_matrix=matrix.tolist(),reinforcement_envelope=dict(frame_entry_axis=axis.tolist()),sleeves=sleeves)
   web=generate_sheet_trace(request,lambda _:None);self.assertEqual(web['report']['used_sleeves'],['S1','S2'])
   self.assertGreaterEqual(web['report']['cycle_count'],15)
   for sid in ['S1','S2']:self.assertGreaterEqual(sum(s==sid for s in web['source_nodes'].values()),2)
   self.assertGreater((np.asarray(list(web['nodes'].values()))@axis).min(),.5)
   reference=web['report']['frame_origin_count'];target=max(4,(reference+1)//2)
   request['axial_web_style']=dict(size_scale=2.,reference_frame_origins=reference,target_frame_origins=target,frame_smoothing=True)
   thick=generate_sheet_trace(request,lambda _:None)
   self.assertEqual(thick['report']['frame_origin_count'],target)
   self.assertEqual(thick['report']['used_sleeves'],['S1','S2'])
   self.assertTrue(all(abs(p['radius_mm']-(.8 if p['member_role']=='PRIMARY'else .5))<1.e-8 for p in thick['pieces']))
   for sid in ['S1','S2']:self.assertGreaterEqual(sum(s==sid for s in thick['source_nodes'].values()),2)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DesignSheetTests)).wasSuccessful():raise SystemExit(1)
