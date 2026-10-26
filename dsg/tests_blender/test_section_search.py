"""Section configuration space + final full-surface protected-zone checks."""
import sys,tempfile,json,numpy as np,bpy
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
runtime=Path.home()/'AppData/Roaming/Blender Foundation/Blender/5.2/scripts/dsg_runtime/dsg_v910_blender52_py313/site-packages'
sys.path.append(str(runtime))
from dsg.section_optimizer import SectionField,search_sections,exact_section_evaluation
from dsg.blender.implant_optimizer_geometry import Solid,Evaluator
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_catalogues import nominal_body_mesh

def solid_box(lo,hi,name):
 bpy.ops.mesh.primitive_cube_add(size=2);obj=bpy.context.object
 v,f,_=_mesh_arrays(obj.data);bpy.data.objects.remove(obj,do_unlink=True)
 v=(v+1)/2*(np.asarray(hi)-lo)+lo
 return Solid(v,f,name)
def asset(d,l):return dict(id=f'{d}x{l}',family='T',diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],reference='Synthetic',vertices_path='synthetic_v',faces_path='synthetic_f',availability='LISTED',dimension_only=True)
def request(catalogue):
 pose=np.eye(4);pose[2,3]=-5
 return dict(implant={'matrix':pose.tolist()},platform=[0,0,0],catalogue=catalogue,family='T',sockets=[],
  settings=dict(max_shift_mm=0.,max_depth_mm=1.5,cervical_free_mm=1.,min_apical_mm=3.))
large=solid_box((-40,-40,-40),(40,40,40),'Scale parity fixture')
points=np.random.default_rng(12).uniform(-5,5,(500,3))
assert np.all(large.signed_distances(points)>0),'Ray parity falsely put an interior point outside'
assert not large.contains([50,0,0])
bone=solid_box((-2.2,-2.2,-12),(2.2,2.2,1),'Native')
req=request([asset(3,6),asset(4,10),asset(5,10)])
def load(a):return nominal_body_mesh(a['diameter_mm'],a['length_mm'])
ev=Evaluator(load(asset(4,10)),bone,[],req['settings'],asset_loader=load,source_platform_local=[0,0,5])
field=SectionField(req,bone,[],[])
result=search_sections(req,field,ev)
assert result['best']['asset']['diameter_mm']==4 and result['best']['asset']['length_mm']==10,result
assert result['verified_3d']>=1 and result['best']['evaluation']['exact_structure_check']
assert result['best']['evaluation']['native_bone_volume_mm3']>100
# Filled contour pixels cannot silently become support.
inner=solid_box((-.5,-.5,-11),(.5,.5,1),'Unknown inner void')
hollow=Solid(np.vstack((bone.vertices,inner.vertices)),np.vstack((bone.faces,inner.faces+len(bone.vertices))),'Hollow bone')
unknown_field=SectionField(req,hollow,[],[])
unknown=unknown_field.assess(3,10,[0,0,0,0,0])
assert not unknown['admissible'] and any(v['code']=='UNVERIFIABLE' for v in unknown['violations'])
try:field.assess(4,50,[0,0,0,0,0]);raise AssertionError('Unmapped length accepted')
except ValueError:pass
# A large socket is available geometric space, never native bone.
socket=solid_box((-1.5,-1.5,-8),(1.5,1.5,1),'Socket')
socket_field=SectionField(req,bone,[],[socket])
measured=socket_field.assess(3,10,[0,0,0,0,0])
assert measured['socket_space_volume_mm3']>0 and measured['native_bone_volume_mm3']<70
assert not measured['admissible'],'A large empty socket became native anchorage'
# Thin obstruction entirely between the planes: the final 3D check must catch it.
z=float(field.z[np.argmin(abs(field.z+5))]+field.pitch*.5)
thin=solid_box((-.2,-.2,z-.01),(.2,.2,z+.01),'Between slices')
hazards=[(thin,0.,'Cavidad nasal',0.)]
thin_field=SectionField(req,bone,hazards,[])
ev=Evaluator(load(asset(4,10)),bone,hazards,req['settings'],asset_loader=load,source_platform_local=[0,0,5])
pose=np.eye(4);pose[2,3]=-5
value=exact_section_evaluation(thin_field,ev,pose,asset(4,10))
assert not value['admissible'] and value['violations'][0]['code']=='STRUCTURE',value
# Native bone stops at sinus floor; air in the allowed tip is reported separately.
large_bone=solid_box((-6,-6,-7),(6,6,1),'Bone to sinus floor')
sinus=solid_box((-8,-8,-30),(8,8,-7),'Sinus')
hazards=[(sinus,0.,'Seno maxilar',2.)]
req=request([asset(4,9),asset(4,10)])
field=SectionField(req,large_bone,hazards,[])
ev=Evaluator(load(asset(4,9)),large_bone,hazards,req['settings'],asset_loader=load,source_platform_local=[0,0,4.5])
pose[2,3]=-4.5
value=exact_section_evaluation(field,ev,pose,asset(4,9))
assert value['admissible'] and value['alerts'] and value['sinus_space_volume_mm3']>0,value
assert value['native_bone_volume_mm3']<value['implant_volume_mm3']
pose[2,3]=-5.
value=exact_section_evaluation(field,ev,pose,asset(4,10))
assert not value['admissible'],value
# The worker must use the section path and revalidate it, not silently return
# to the old 1.6 mm expanded hull during APPLY.
from dsg.implant_optimizer_worker import run
folder=Path(tempfile.mkdtemp(prefix='DSG_SECTION_WORKER_TEST_'))
def saved(solid,key):
 vp=folder/(key+'_v.npy');fp=folder/(key+'_f.npy');np.save(vp,solid.vertices);np.save(fp,solid.faces)
 return dict(name=key,vertices_path=str(vp),faces_path=str(fp),matrix=np.eye(4).tolist())
req=request([asset(4,9),asset(4,10)])
req['section_site_paths']=[str(runtime)];req['mode']='SIZE'
req['settings'].update(section_search=True,combine_size_position=True)
req['current']={'diameter_mm':3.,'length_mm':6.}
source=nominal_body_mesh(3.,6.);vp=folder/'source_v.npy';fp=folder/'source_f.npy';np.save(vp,source[0]);np.save(fp,source[1])
source_pose=np.eye(4);source_pose[2,3]=-3.
req['implant'].update(vertices_path=str(vp),faces_path=str(fp),matrix=source_pose.tolist())
req['bone']=saved(large_bone,'bone')
zone=saved(sinus,'sinus');zone.update(margin_mm=0.,kind='Seno maxilar',max_invasion_mm=2.)
req['obstacles']=[zone]
for a in req['catalogue']:
 v,f=nominal_body_mesh(a['diameter_mm'],a['length_mm']);vp=folder/(a['id']+'_v.npy');fp=folder/(a['id']+'_f.npy');np.save(vp,v);np.save(fp,f)
 a.update(vertices_path=str(vp),faces_path=str(fp))
out=run(req);assert out['section_search'] and out['best'] and out['best']['asset']['length_mm']==9,out
req.update(mode='VALIDATE',candidate=out['best'])
validated=run(req);assert validated['status']=='VALIDATED',validated
# A newly protected structure must invalidate exactly the same proposed pose.
new=saved(solid_box((-.4,-.4,-6),(.4,.4,-5),'New nasal zone'),'new_nasal');new.update(margin_mm=0.,kind='Cavidad nasal')
req['obstacles'].append(new)
assert run(req)['status']=='REJECTED'
print('SECTION_SEARCH_PASS:largest_fit,explicit_native_socket_air,between_plane_3d_guard,sinus2mm_bound',flush=True)
