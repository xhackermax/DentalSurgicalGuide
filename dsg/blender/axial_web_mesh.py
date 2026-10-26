"""Closed shared-junction volume and independent final geometry checks."""
import json
import numpy as np
import bpy,bmesh
from mathutils import Vector
from .axial_design_sheet import outward_tree,free_floor
from ..axial_extrados import height_bounds

def load_mesh(path):
 with np.load(path)as a:return np.array(a['vertices'],float),np.array(a['triangles'],int)

def fair_graph(web,request):
 keys=list(web['nodes']);index={k:i for i,k in enumerate(keys)};q=np.array([web['nodes'][k]for k in keys]);original=q.copy();adj=[set()for k in keys]
 for piece in web['pieces']:
  for a,b in zip(piece['node_chain'],piece['node_chain'][1:]):i,j=index[a],index[b];adj[i].add(j);adj[j].add(i)
 fixed=set(web['attachments']);n=np.array(request['reinforcement_envelope']['frame_entry_axis'],float);n/=np.linalg.norm(n);ios=outward_tree(*load_mesh(request['surface_file']));radius=float(request['radius_mm'])*.55*float((request.get('axial_web_style')or{}).get('size_scale',1.));frame=outward_tree(*load_mesh(request['frame_support_file']));reach=100.
 from .axial_web_surface import ray_height,exterior_floor
 from .axial_web_surface import mesh_tree
 lower=mesh_tree(*load_mesh(request['frame_lower_surface_file']))
 for _ in range(8):
  nxt=q.copy()
  for j,key in enumerate(keys):
   if key in fixed or not adj[j]:continue
   p=q[j]+.35*(q[list(adj[j])].mean(axis=0)-q[j]);delta=p-original[j];length=np.linalg.norm(delta)
   if length>.55:p=original[j]+delta*.55/length
   _,hi=height_bounds(p[None,:],np.array([radius+.12]),n,request['sleeves']);barrier=exterior_floor(lower,p,n,-.5,radius+.12,float(hi[0]));floor=None if barrier is None else free_floor(ios,p,n,max(-.5,barrier),float(hi[0]),radius+.04)
   if floor is not None:
    displacement=max(0.,floor);hit=ray_height(frame,p,n,reach)
    if hit is not None:displacement=max(displacement,float((hit-p)@n)+radius+.1)
    if displacement<=float(hi[0]):nxt[j]=p+n*displacement
  q=nxt
 web['nodes']={k:q[j].tolist()for j,k in enumerate(keys)}
 for piece in web['pieces']:piece['points_mm']=[web['nodes'][k]for k in piece['node_chain']]
 if web.get('style',{}).get('frame_smoothing'):
  from .axial_frame_smoothing import smooth_like_frame
  smooth_like_frame(web,request)
 return web

def build_volume(context,web,name='DSG_AxialWeb_Candidate',request=None):
 from .axial_implicit_web import build_implicit_volume
 obj=build_implicit_volume(context,web,name)
 if web.get('style',{}).get('manual_union')or web.get('style',{}).get('support_fairing'):
  from .axial_manual_unions import add_manual_unions
  if request is None:raise ValueError('MISSING_MANUAL_UNION_REFERENCE')
  obj=add_manual_unions(context,obj,web,request)
 return obj

def validate_centerline_skin(web,v,f,tolerance=.12):
 """Lipschitz bounds certify an inscribed variable-radius sweep along every segment."""
 from .sleeve_attachment import _winding
 tree=outward_tree(v,f);checks=0;minimum=float('inf');parent={};roots=[]
 def root(key):
  parent.setdefault(key,key)
  while parent[key]!=key:parent[key]=parent[parent[key]];key=parent[key]
  return key
 for index,piece in enumerate(web['pieces']):
  chain=piece.get('node_chain',[str(index)+':a',str(index)+':b']);roots.append(chain[0])
  for a,b in zip(chain,chain[1:]):parent[root(a)]=root(b)
 checked=set()
 for index,piece in enumerate(web['pieces']):
  points=np.asarray(piece['points_mm'],float);radii=np.asarray(piece['point_radii_mm'],float)
  component=root(roots[index])
  if np.min(radii)<=tolerance:raise ValueError('AXIAL_SECTION_TOO_SMALL_FOR_BOUND')
  if component not in checked:
   if abs(abs(_winding(points[0],v[f]))-1.)>1.e-4:raise ValueError('AXIAL_CENTERLINE_OUTSIDE')
   checked.add(component)
  pending=[(a,b,float(ra),float(rb),0)for a,b,ra,rb in zip(points,points[1:],radii,radii[1:])]
  while pending:
   a,b,ra,rb,depth=pending.pop();mid=(a+b)*.5;r=(ra+rb)*.5;near=tree.find_nearest(Vector(mid));distance=float(near[3]);checks+=1
   margin=distance-r;minimum=min(minimum,margin);bound=margin-.5*(np.linalg.norm(b-a)+abs(rb-ra))
   if bound>=-tolerance:continue
   if margin < -tolerance or depth>=16:raise ValueError('AXIAL_SECTION_ERODED:'+str(margin))
   pending.extend([(a,mid,ra,r,depth+1),(mid,b,r,rb,depth+1)])
 return dict(valid=True,method='CONTINUOUS_LIPSCHITZ_INSCRIBED_SWEEP',maximum_radius_loss_mm=tolerance,stations_checked=checks,minimum_sampled_radius_margin_mm=minimum)

def validate_volume(context,obj,web,request,progress=print):
 from .generative_frame import _export_mesh
 from ..guide_export.mesh_checks import manifold_report,connected_components,signed_volume_mm3
 from .organic_reinforcement import mesh_self_intersections
 from ..reinforcement_envelope import validate_mesh_envelope
 from .reinforcement_envelope import validate_upper_frame_contact
 from ..organic_reinforcement import validate_mesh_keepouts
 from ..frame_swept_clearance_core import CylinderKeepOut
 from .sleeve_attachment import certify_sleeve_attachment,_winding
 v,f=_export_mesh(context,obj);report=manifold_report(v,f)
 if report.blocking or report.metrics['degenerate_triangles']:raise ValueError('AXIAL_NOT_CLOSED:'+str(report.metrics))
 if signed_volume_mm3(v,f)<0:
  bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free();v,f=_export_mesh(context,obj)
 component_labels=connected_components(len(v),f);components=len(np.unique(component_labels))
 if components!=web['report']['component_count']:raise ValueError('AXIAL_UNEXPECTED_VOLUME_COMPONENTS:'+str(components))
 if mesh_self_intersections(v,f):raise ValueError('AXIAL_SELF_INTERSECTION')
 progress('Comprobando secciones y limites de sleeve, cara inferior y anatomia original')
 sections=validate_centerline_skin(web,v,f)
 envelope=validate_mesh_envelope(v,f,request);fv,ff=load_mesh(request['frame_support_file']);upper=validate_upper_frame_contact(v,f,fv,ff,request['reinforcement_envelope']['frame_entry_axis'])
 iv,it=load_mesh(request['surface_file']);ios=outward_tree(iv,it);skin=outward_tree(v,f)
 # Exact triangle crossings plus both directions of containment.
 if skin.overlap(ios):raise ValueError('AXIAL_IOS_SURFACE_INTERSECTION')
 # Without boundary crossings, one winding witness per connected closed
 # component determines containment for its entire boundary. Nearest-normal
 # signs alone are ambiguous at concave dental edges.
 if manifold_report(iv,it).blocking:raise ValueError('AXIAL_IOS_NOT_CLOSED')
 for component in np.unique(component_labels):
  point=v[np.flatnonzero(component_labels==component)[0]]
  if abs(_winding(point,iv[it]))>1.e-4:raise ValueError('AXIAL_IOS_INTERIOR')
 ios_components=connected_components(len(iv),it)
 for component in np.unique(ios_components):
  point=iv[np.flatnonzero(ios_components==component)[0]]
  if abs(_winding(point,v[f]))>1.e-4:raise ValueError('AXIAL_ENCLOSES_IOS')
 zones=[CylinderKeepOut(s['id']+':FULL_DRILL',tuple(s['center']),tuple(s['axis']),s['inner_radius_mm'],s['height_mm']*.5+20.)for s in request['sleeves']]
 obstacles=[]
 for row in request.get('obstacles',[]):
  ov,of=load_mesh(row['file']);obstacles.append(dict(label=row['label'],vertices_mm=ov,triangles=of,closed=row['closed']))
 check=validate_mesh_keepouts(v,f,zones,obstacles)
 if not check['valid']:raise ValueError(check['reason'])
 receipts={};component_support={}
 for key,a in web['attachments'].items():
  if a['kind']=='FRAME':sv,sf=fv,ff
  else:sv,sf=load_mesh(request['sleeve_surface_files'][a['target']])
  progress('Comprobando union local '+a['kind']+':'+key)
  receipts[key]=certify_sleeve_attachment(v,f,sv,sf,near_point_mm=a['point_mm'],maximum_witness_distance_mm=2.*a['radius_mm']+.25)
  hit=skin.find_nearest(Vector(receipts[key]['witness_mm']));component=int(component_labels[f[int(hit[2]),0]]);component_support.setdefault(component,set()).add(a['kind'])
 if any(component_support.get(int(c),set())!={'FRAME','SLEEVE'}for c in np.unique(component_labels)):raise ValueError('AXIAL_UNSUPPORTED_VOLUME_COMPONENT')
 # Also prove attachment to the actual visible final guide, rather than
 # relying only on preserved hidden frame/sleeve source solids.
 if request.get('guide_surface_file'):
  gv,gf=load_mesh(request['guide_surface_file']);guide=outward_tree(gv,gf)
  for key,receipt in receipts.items():
   witness=np.array(receipt['witness_mm']);near=guide.find_nearest(Vector(witness))
   if near is not None and near[3]>.01 and abs(abs(_winding(witness,gv[gf]))-1.)<1.e-4:receipt['visible_guide_overlap_verified']=True
   else:
    a=web['attachments'][key];receipt['visible_guide_receipt']=certify_sleeve_attachment(v,f,gv,gf,near_point_mm=a['point_mm'],maximum_witness_distance_mm=2.*a['radius_mm']+.25);receipt['visible_guide_overlap_verified']=True
 # Euler genus measures actual surviving open cells after volume union.
 edges=np.unique(np.sort(np.vstack((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]])),axis=1),axis=0);genus=int(round((2*components-(len(v)-len(edges)+len(f)))/2))
 if genus<8:raise ValueError('AXIAL_CELLS_COLLAPSED:'+str(genus))
 return dict(valid=True,manual_union_receipts=json.loads(obj.get('DSG_manual_union_receipts_json','{}')),manual_union_count=int(obj.get('DSG_manual_coons_count',0)),sections=sections,manifold=report.as_dict(),component_count=components,physical_cell_count=genus,envelope=envelope,frame_contact=upper,keepouts=check,attachment_receipts=receipts,ios_original_clear=True,self_intersections=0,mechanics_evaluated=False)
