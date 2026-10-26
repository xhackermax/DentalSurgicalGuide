"""Use the user's manual Coons-Hermite union builder on every support endpoint."""
import numpy as np
import bpy,bmesh
from mathutils import Vector
from .axial_web_surface import mesh_tree
from .axial_design_sheet import outward_tree
from .axial_web_mesh import load_mesh

def add_manual_unions(context,body,web,request):
 from .. import guide_module as g
 from .generative_frame import _export_mesh
 from ..guide_export.mesh_checks import signed_volume_mm3,manifold_report
 objects=[];collars=[];supports={};trees={};receipts={};combined=None
 def support(kind,target):
  label='FRAME'if kind=='FRAME'else target
  if label in supports:return supports[label],trees[label]
  path=request['frame_support_file']if kind=='FRAME'else request['sleeve_surface_files'][target];v,f=load_mesh(path);tri=v[f];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
  if signed_volume_mm3(v,f)<0:f=f[:,::-1];normal=-normal
  if kind=='FRAME':
   axis=np.array(request['reinforcement_envelope']['frame_entry_axis']);selected=(normal@axis)>.1*np.linalg.norm(normal,axis=1)
  else:
   sleeve=next(s for s in request['sleeves']if s['id']==target);axis=np.array(sleeve['axis']);delta=tri.mean(axis=1)-np.array(sleeve['center']);radial=delta-(delta@axis)[:,None]*axis
   selected=(np.abs(normal@axis)<.05*np.linalg.norm(normal,axis=1))&(np.sum(normal*radial,axis=1)>0)&(np.linalg.norm(radial,axis=1)>sleeve['outer_radius_mm']-.1)
  if not np.any(selected):raise ValueError('MISSING_ADMISSIBLE_MANUAL_SUPPORT:'+label)
  mesh=bpy.data.meshes.new('DSG_ManualSupport_'+label);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update();obj=bpy.data.objects.new(mesh.name,mesh);context.scene.collection.objects.link(obj);objects.append(obj);supports[label]=obj;trees[label]=mesh_tree(v,f[selected]);return obj,trees[label]
 try:
  for key,attachment in web['attachments'].items():
   obj,tree=support(attachment['kind'],attachment['target']);routes=[r for r in web['radials']if r['nodes'][0]==key or r['nodes'][-1]==key]
   if not routes:raise ValueError('MISSING_MANUAL_TERMINAL_ROUTE:'+key)
   route=max(routes,key=lambda r:r['length_mm']);chain=route['nodes']if route['nodes'][0]==key else list(reversed(route['nodes']));points=[Vector(web['nodes'][k])for k in chain];near=tree.find_nearest(points[0])
   if not near or near[0]is None:raise ValueError('NO_MANUAL_CONTACT:'+key)
   contact,normal=near[0],near[1];full=[contact]+points if(contact-points[0]).length>1e-5 else points
   full,arc=g._polyline_cumulative_lengths(full);length=arc[-1];radius=float(attachment['radius_mm']);neck=g._reinforcement_extended_neck_length(radius,length);index=min(len(arc)-2,int(np.searchsorted(arc,neck,side='right')-1));fraction=(neck-arc[index])/max(arc[index+1]-arc[index],1e-9);center=full[index].lerp(full[index+1],fraction);tangent=(full[index+1]-full[index]).normalized()
   flat=bool(web.get('style',{}).get('support_fairing'))
   if flat:
    # A bent graph route can turn its end ring back across the support.
    # Place the fair neck beyond the bounded footprint and orient its plane
    # away from that footprint; never disable the halfspace guard.
    candidates=[p for p in points if(p-contact).length>=2.7*radius]
    if not candidates:raise ValueError('SUPPORT_FAIRING_NECK_TOO_SHORT:'+key)
    center=candidates[0];tangent=(center-contact).normalized()
   ratios=[1.35,1.2,1.05,1.]if flat and attachment['kind']=='FRAME'else[1.35]
   settings=[(r,h)for r in ratios for h in ([1.,.6,.3,.1]if flat and attachment['kind']=='FRAME'else[1.])]
   for ratio,handle_scale in settings:
    options=dict(footprint_radius_ratio=ratio,fullness_scale=0.,tangent_handle_scale=handle_scale,bound_tube_halfspace=True,support_embed_depth_override=.06)if flat else{}
    collar=g._build_reinforcement_coons_blend_object(context,'DSG_AxialManual_'+key.replace(':','_'),contact,normal,tangent,obj,radius,length,surface_tree=tree,tube_center_override=center,tube_tangent_override=tangent,cap_tube=True,**options)
    if collar is None:break
    if flat and attachment['kind']=='FRAME':
     from .reinforcement_envelope import validate_upper_frame_contact
     cv,cf=_export_mesh(context,collar);fv,ff=load_mesh(request['frame_support_file'])
     try:validate_upper_frame_contact(cv,cf,fv,ff,request['reinforcement_envelope']['frame_entry_axis'])
     except ValueError as exc:
      if str(exc)!='REINFORCEMENT_TOUCHES_LOWER_FRAME_SURFACE':raise
      g.safe_remove_object_with_data(collar);collar=None;continue
    break
   if collar is None:raise ValueError('MANUAL_COONS_BUILD_FAILED:'+key)
   collars.append(collar);v,f=_export_mesh(context,collar)
   if manifold_report(v,f).blocking:raise ValueError('MANUAL_COONS_NOT_CLOSED:'+key)
   if signed_volume_mm3(v,f)<0:
    bm=bmesh.new();bm.from_mesh(collar.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(collar.data);bm.free();collar.data.update()
   receipts[key]=dict(method=str(collar.get('DSG_reinforcement_blend_method')),shared_manual_builder=True,footprint_radius_ratio=ratio if flat else None,fullness_scale=0. if flat else 1.,tangent_handle_scale=handle_scale,contact_point_mm=list(contact),normal=list(normal),neck_length_mm=float(collar['DSG_reinforcement_blend_neck_length']),connector_radius_mm=radius)
  combined=g.build_combined_mesh_object_world(context,[body]+collars,'DSG_AxialWeb_ManualUnions')
  if combined is None:raise ValueError('MANUAL_UNION_COMBINE_FAILED')
  modifier=combined.modifiers.new('DSG_ManualWeb_Weld','REMESH');modifier.mode='VOXEL';modifier.voxel_size=.06;modifier.adaptivity=0.;modifier.use_smooth_shade=True;context.view_layer.update();deps=context.evaluated_depsgraph_get();mesh=bpy.data.meshes.new_from_object(combined.evaluated_get(deps),depsgraph=deps);old=combined.data;combined.modifiers.remove(modifier);combined.data=mesh
  if old.users==0:bpy.data.meshes.remove(old)
  from .axial_implicit_web import clean_volume_mesh
  clean_volume_mesh(combined.data,.06)
  combined['DSG_manual_union_receipts_json']=__import__('json').dumps(receipts);combined['DSG_manual_coons_count']=len(collars);combined['DSG_manual_coons_shared_builder']=True;return combined
 except Exception:
  if combined is not None:g.safe_remove_object_with_data(combined)
  raise
 finally:
  for obj in [body]+collars+objects:
   if obj.name in bpy.data.objects:g.safe_remove_object_with_data(obj)
