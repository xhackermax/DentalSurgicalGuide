"""Use the frame's centripetal Catmull path with shared, fixed web junctions."""
import numpy as np

def frame_curve(points):
 from .. import guide_module as g
 from mathutils import Vector
 q=np.asarray(points,float).copy()
 if len(q)<3:return q.tolist()
 # Suppress mesh-grid chatter before choosing the frame's 5 mm controls.
 original=q.copy()
 for _ in range(12):q[1:-1]=.88*(q[1:-1]+.45*((q[:-2]+q[2:])*.5-q[1:-1]))+.12*original[1:-1]
 controls=g._frame_sparse_catmull_controls([Vector(p)for p in q],target_spacing=5.,keep_turn_deg=80.)
 if len(controls)<4:controls=[Vector(p)for p in q[np.unique(np.linspace(0,len(q)-1,min(4,len(q))).astype(int))]]
 curve=g.build_catmull_rom_frame_path(controls,closed=False,alpha=.5,max_spacing=.3,min_samples_per_segment=3,max_samples_per_segment=24)
 out=np.asarray([list(p)for p in curve],float);out[0]=original[0];out[-1]=original[-1]
 return out.tolist()

def smooth_like_frame(web,request):
 from .axial_web_mesh import load_mesh
 from .axial_design_sheet import outward_tree,free_floor
 from ..axial_extrados import height_bounds
 from .axial_web_surface import mesh_tree,exterior_floor
 n=np.asarray(request['reinforcement_envelope']['frame_entry_axis'],float);n/=np.linalg.norm(n)
 ios=outward_tree(*load_mesh(request['surface_file']));lower=mesh_tree(*load_mesh(request['frame_lower_surface_file']))
 # Junctions stay exactly shared. Radius stays uniform along each member,
 # including its ends; there are no enlarged balls or volcano collars.
 for piece in web['pieces']:
  points=np.asarray(frame_curve(piece['points_mm']),float);r=float(piece['radius_mm'])
  for i in range(1,len(points)-1):
   p=points[i];_,hi=height_bounds(p[None,:],np.array([r+.12]),n,request['sleeves'])
   barrier=exterior_floor(lower,p,n,0.,r+.12,float(hi[0]))
   floor=None if barrier is None else free_floor(ios,p,n,max(0.,barrier),float(hi[0]),r+.04)
   if floor is None:raise ValueError('FRAME_CURVE_HAS_NO_EXTERIOR_CLEARANCE')
   points[i]=p+n*floor
  piece['points_mm']=points.tolist()
  piece['point_radii_mm']=[piece['radius_mm']]*len(piece['points_mm'])
 web['report'].update(frame_smoothing=True,frame_curve_method='SHARED_FRAME_CENTRIPETAL_CATMULL_ROM',frame_catmull_alpha=.5,frame_control_spacing_mm=5.,frame_sample_spacing_mm=.3,terminal_enlargement=False)
