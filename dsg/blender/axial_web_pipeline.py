"""Scoped V2 worker/review dispatch; legacy lattice generation remains intact."""
import json
from pathlib import Path
import numpy as np
import bpy
from ..axial_web_contract import TOPOLOGY,seal_files,verify_files,input_paths,verify_payload,verify_geometry_report

def augment_snapshot(context,request,folder):
 from .generative_frame import _export_mesh
 from .. import guide_module as g
 folder=Path(folder);request['guide_surface_file']=str(folder/'guide.npz');v,f=_export_mesh(context,bpy.data.objects[request['guide_name']]);np.savez(request['guide_surface_file'],vertices=v,triangles=f)
 request['sleeve_surface_files']={}
 for s in request['sleeves']:
  obj=bpy.data.objects.get(g.SLEEVE_SOURCE_PREFIX+f"{int(s['id'][1:]):02d}")
  if obj is None:raise ValueError('MISSING_SLEEVE_SOURCE:'+s['id'])
  path=str(folder/('sleeve_'+s['id']+'.npz'));v,f=_export_mesh(context,obj);np.savez(path,vertices=v,triangles=f);request['sleeve_surface_files'][s['id']]=path
 request['reinforcement_topology']=TOPOLOGY
 from .axial_design_sheet import generate_sheet_trace
 baseline=generate_sheet_trace(request,lambda _:None);count=baseline['report']['frame_origin_count'];minimum=2*len(request['sleeves']);target=max(minimum,(count+1)//2)
 request['axial_web_style']=dict(size_scale=2.,reference_frame_origins=count,target_frame_origins=target,reference_piece_count=len(baseline['pieces']),manual_union=False,frame_smoothing=True,surface_fairing=True,support_fairing=True)
 request['axial_input_manifest']=seal_files(input_paths(request))
 return request

def build_candidate(request,progress=print):
 if not bpy.app.background:raise ValueError('AXIAL_VOLUME_REQUIRES_ISOLATED_WORKER')
 verify_files(request['axial_input_manifest'])
 from .axial_design_sheet import generate_sheet_trace
 from .axial_web_mesh import fair_graph,build_volume,validate_volume
 from .generative_frame import _export_mesh
 web=fair_graph(generate_sheet_trace(request,progress),request);obj=None
 try:
  progress('Uniendo la red exterior y suavizando sus nodos');obj=build_volume(bpy.context,web,request=request)
  native=validate_volume(bpy.context,obj,web,request,progress);verify_geometry_report(web,native,request['sleeves']);verify_files(request['axial_input_manifest'])
  folder=Path(request['job_dir']);web_file=str(folder/'axial_web.json');volume_file=str(folder/'axial_volume.npz');Path(web_file).write_text(json.dumps(web),encoding='utf-8');v,f=_export_mesh(bpy.context,obj);np.savez(volume_file,vertices=v,triangles=f)
  report=dict(web['report'],native_geometry=native,lattice_complete=True,mechanics_evaluated=False)
  return dict(status='CANDIDATE',topology=TOPOLOGY,run_id=request['run_id'],case_fingerprint=request['case_fingerprint'],web_file=web_file,volume_file=volume_file,artifact_manifest=seal_files([web_file,volume_file]),report=report,pieces=[dict(route_id='AXIAL_VOLUME',member_role='NETWORK',radius_mm=float(request['radius_mm']))])
 finally:
  if obj is not None:
   mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
   if mesh.users==0:bpy.data.meshes.remove(mesh)

def _verify_context(context,request):
 from .generative_frame import case_fingerprint
 from .reinforcement_envelope import verify_context_envelope
 if case_fingerprint(context)!=request['case_fingerprint']:raise ValueError('STALE_INPUT: el caso cambio; vuelve a calcular la telarana.')
 verify_context_envelope(context,request)

def _materials(obj,web):
 from scipy.spatial import cKDTree
 roles=['PRIMARY','SECONDARY'];samples={k:[]for k in roles};radii={k:[]for k in roles}
 for piece in web['pieces']:
  role=piece['member_role'];points=np.asarray(piece['points_mm']);rr=piece['point_radii_mm']
  for a,b,ra,rb in zip(points,points[1:],rr,rr[1:]):
   t=np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(b-a)/.2))+1));samples[role].extend(a[None,:]+t[:,None]*(b-a));radii[role].extend(ra+t*(rb-ra))
 centers=np.array([p.center[:]for p in obj.data.polygons]);scores=[]
 for role,color in zip(roles,[(1.,.28,.05,1.),(.04,.8,.9,1.)]):
  name='DSG_Lattice_'+role;mat=bpy.data.materials.get(name)
  if mat is None:
   mat=bpy.data.materials.new(name);mat.diffuse_color=color;mat.use_nodes=True;shader=mat.node_tree.nodes.get('Principled BSDF')
   if shader:shader.inputs['Base Color'].default_value=color;shader.inputs['Roughness'].default_value=.45
  obj.data.materials.append(mat)
  tree=cKDTree(np.array(samples[role]));d,i=tree.query(centers,k=min(4,len(samples[role])));d=np.atleast_2d(d)if d.ndim==1 else d;i=np.atleast_2d(i)if i.ndim==1 else i;scores.append(np.min(d-np.asarray(radii[role])[i],axis=1))
 material_indices=np.argmin(np.array(scores),axis=0).astype(np.int32);obj.data.polygons.foreach_set('material_index',material_indices)
 for polygon in obj.data.polygons:polygon.use_smooth=True
 obj.color=(1.,.28,.05,1.);obj.show_in_front=False

def stage(context,request,outcome):
 from . import generative_frame as gf
 from .. import guide_module as g
 import sys
 for site in request.get('section_site_paths',[]):
  if site not in sys.path:sys.path.append(site)
 _verify_context(context,request);web=verify_payload(request,outcome);obj=None
 try:
  with np.load(outcome['volume_file'])as a:v=np.array(a['vertices']);f=np.array(a['triangles'])
  mesh=bpy.data.meshes.new('DSG_AxialWeb_'+request['run_id']);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update();obj=bpy.data.objects.new(mesh.name,mesh);context.scene.collection.objects.link(obj)
  _materials(obj,web);obj[gf.OWNER]=True;obj['DSG_generative_run_id']=request['run_id'];obj['DSG_generative_radius_mm']=max(max(p['point_radii_mm'])for p in web['pieces']);obj['DSG_variable_radius_min_mm']=min(min(p['point_radii_mm'])for p in web['pieces']);obj['DSG_generative_route_id']='AXIAL_VOLUME';obj['DSG_lattice_member_role']='NETWORK';obj['DSG_reinforcement_confirmed']=False;obj['DSG_axial_web_topology']=TOPOLOGY;obj['DSG_axial_native_geometry_json']=json.dumps(outcome['report']['native_geometry'])
  _verify_context(context,request)
 except Exception:
  if obj is not None:g.safe_remove_object_with_data(obj)
  raise
 for previous in gf.preview_objects():
  if previous!=obj:g.safe_remove_object_with_data(previous)
 visibility=dict(gf.STATE.get('visibility',{}))
 for previous in g.get_confirmed_reinforcement_curves():visibility.setdefault(previous.name,bool(previous.hide_get()));previous.hide_set(True)
 gf.STATE.update(request=request,result=outcome,scene_name=context.scene.name,visibility=visibility,building_candidate=False,message='Telarana exterior propuesta; malla y anclajes comprobados.',preview_hashes={obj.name:gf.case_geometry_fingerprint(obj)})
 context.scene[gf.SAVED]=json.dumps({k:gf.STATE[k]for k in ('request','result','scene_name','visibility','preview_hashes')})
 return [obj]

def accept(context):
 from . import generative_frame as gf
 from .. import guide_module as g,frame_structural as structural
 request=gf.STATE.get('request');outcome=gf.STATE.get('result')
 if not request or not outcome:raise ValueError('MISSING_AXIAL_WEB_PROPOSAL')
 _verify_context(context,request);verify_payload(request,outcome);objects=gf.preview_objects();hashes=gf.STATE.get('preview_hashes',{})
 if len(objects)!=1 or set(hashes)!={o.name for o in objects}or any(hashes[o.name]!=gf.case_geometry_fingerprint(o)or o.get('DSG_axial_web_topology')!=TOPOLOGY for o in objects):raise ValueError('STALE_PREVIEW: la propuesta ha cambiado.')
 guide=bpy.data.objects[request['guide_name']];frame=structural._frame_obj(context)
 if gf.case_geometry_fingerprint(frame)!=request['frame_digest']:raise ValueError('FRAME_CHANGED')
 obj=objects[0];old=g.get_confirmed_reinforcement_curves();saved=[];props=context.scene.dsg_props;count=int(props.reinforcement_count);name=obj.name
 keys=('DSG_frame_fem_hard_safe','DSG_frame_fem_recommended','DSG_generative_report_json','DSG_frame_fem_design_aid_not_validation');previous={k:(k in guide,guide.get(k))for k in keys}
 try:
  import uuid
  for item in old:
   saved.append((item,item.name,bool(item.hide_get()),bool(item.get('DSG_reinforcement_confirmed'))));item.name='DSG_GenerativeArchive_'+uuid.uuid4().hex[:8]+'_'+item.name;item['DSG_reinforcement_confirmed']=False;item.hide_set(True)
  obj.name=g.REINFORCEMENT_PREFIX+'00';obj[gf.OWNER]=False;obj['DSG_reinforcement_confirmed']=True;obj['DSG_reinforcement_index']=0;obj['DSG_reinforcement_generative_generated']=True;obj['DSG_reinforcement_diameter']=2.*float(obj['DSG_generative_radius_mm']);g.register_dsg_object(obj,g.ROLE_REINFORCEMENT,obj.name,{})
  props.reinforcement_count=1;guide['DSG_frame_fem_hard_safe']=False;guide['DSG_frame_fem_recommended']=False;guide['DSG_generative_report_json']=json.dumps(outcome['report']);guide['DSG_frame_fem_design_aid_not_validation']=True;gf.STATE['accepted_frame_digest']=gf.case_geometry_fingerprint(frame)
 except Exception:
  obj.name=name;obj[gf.OWNER]=True;obj['DSG_reinforcement_confirmed']=False
  for item,item_name,hidden,confirmed in saved:item.name=item_name;item.hide_set(hidden);item['DSG_reinforcement_confirmed']=confirmed
  for k,(present,value)in previous.items():
   if present:guide[k]=value
   elif k in guide:del guide[k]
  props.reinforcement_count=count;raise
 if gf.SAVED in context.scene:del context.scene[gf.SAVED]
 gf.STATE.update(request=None,result=None,visibility={},building_candidate=False,message='Telarana aplicada; mecanica pendiente de validar.')
