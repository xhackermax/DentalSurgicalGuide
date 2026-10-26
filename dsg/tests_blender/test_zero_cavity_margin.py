"""Zero cavity buffer removes distance exclusion, never collision exclusion."""
import sys,numpy as np,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.implant_optimizer_geometry import Solid,Evaluator,clearance
from dsg.blender.safety_volume import _mesh_arrays
def box(size,location,name):
 bpy.ops.mesh.primitive_cube_add(size=size,location=location)
 obj=bpy.context.object;v,f,_=_mesh_arrays(obj.data)
 return Solid(v+np.asarray(location),f,name)
source=box(2,(0,0,0),'Implant')
bone=box(80,(0,0,0),'Native bone')
settings=dict(boundary_reserve_mm=.1,min_coverage=.8,cervical_free_mm=0.,explain_rejections=True)
for label in ('Seno maxilar izquierdo','Cavidad nasal izquierda'):
 for x,expected in ((2.0001,True),(1.999,False),(0.,False)):
  cavity=box(2,(x,0,0),label)
  measured=clearance(source,cavity,0.)
  assert (measured['status']=='SAFE')==expected,(label,x,measured)
  evaluation=Evaluator((source.vertices,source.faces),bone,[(cavity,0.,label,0.)],settings,source_platform_local=[0,0,1])(np.eye(4))
  assert evaluation['admissible']==expected,(label,x,evaluation)
  if not expected:assert any(v['code']=='STRUCTURE' for v in evaluation['violations'])
try:clearance(source,bone,-.1);raise AssertionError('Negative margin accepted')
except ValueError:pass
print('ZERO_CAVITY_MARGIN_PASS:sinus_nasal_close_allowed,intersection_containment_blocked,diagnostics_consistent',flush=True)
