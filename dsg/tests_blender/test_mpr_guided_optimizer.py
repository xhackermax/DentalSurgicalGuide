"""MPR-style measurements must influence a proposal, not only its final report."""
import sys
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.implant_optimizer_geometry import Solid,Evaluator
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_optimization import search_position
bpy.ops.mesh.primitive_cube_add(size=10)
v,f,_=_mesh_arrays(bpy.context.object.data);bone=Solid(v,f,'Native bone')
bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=1,depth=4)
v,f,_=_mesh_arrays(bpy.context.object.data)
e=Evaluator((v,f),bone,[],dict(boundary_reserve_mm=.1,min_coverage=.8,mpr_guided_selection=True),source_platform_local=[0,0,2])
base=np.eye(4);base[0,3]=3
original=e(base);centred=e(np.eye(4))
assert original['admissible'] and centred['admissible']
assert centred['score']>original['score']+.03, 'MPR wall measurements do not influence scoring'
assert centred['mpr_checks']['minimum_wall_mm']>original['mpr_checks']['minimum_wall_mm']
result=search_position(e,base,[3,0,2],max_shift_mm=3,max_tilt_deg=0,budget=60)
assert result['status']=='PROPOSAL',result
assert abs(result['best']['matrix'][0][3])<3
# Unsafe geometry never becomes admissible through the additional score.
bad=base.copy();bad[0,3]=5
assert not e(bad)['admissible']
print('MPR_GUIDED_POSITION_SELECTION_AND_HARD_GUARDS_PASS')
# The catalogue route also uses native cross-sectional wall reserve as a tie-break.
from pathlib import Path
sys.path.append(str(Path.home()/'AppData/Roaming/Blender Foundation/Blender/5.2/scripts/dsg_runtime/dsg_v910_blender52_py313/site-packages'))
from dsg.section_optimizer import SectionField,search_sections
from dsg.implant_catalogues import nominal_body_mesh
from dsg.optimizer_reference import candidate_rank
bv=bone.vertices.copy();bv[:,0]+=1.;bv[:,2]-=4.
section_bone=Solid(bv,bone.faces,'Offset native ridge')
a=dict(id='T2x4',family='T',diameter_mm=2.,length_mm=4.,platform_local_mm=[0,0,2],reference='SYNTHETIC',vertices_path='v',faces_path='f',dimension_only=True)
pose=np.eye(4);pose[2,3]=-2
settings=dict(max_shift_mm=2.,max_depth_mm=1.5,cervical_free_mm=1.,min_apical_mm=3.,mpr_guided_selection=True)
req=dict(implant={'matrix':pose.tolist()},platform=[0,0,0],catalogue=[a],family='T',sockets=[],settings=settings)
load=lambda a:nominal_body_mesh(a['diameter_mm'],a['length_mm'])
ev=Evaluator(load(a),section_bone,[],settings,asset_loader=load,source_platform_local=[0,0,2])
field=SectionField(req,section_bone,[],[])
result=search_sections(req,field,ev)
assert result['best'] and result['best']['evaluation']['mpr_checks']['status']=='MEASURED',result
assert result['best']['parameters'][0]>.0,result['best']['parameters']
assert result['best']['evaluation']['mpr_wall_reserve_mm']>field.assess(2,4,[0,0,1,0,0])['mpr_wall_reserve_mm']
print('MPR_GUIDED_SECTION_CATALOGUE_SELECTION_PASS',result['best']['parameters'])
# The worker applies the same measurements again before accepting a candidate.
import tempfile
from dsg.implant_optimizer_worker import run
folder=Path(tempfile.mkdtemp(prefix='DSG_TEST_MPR_OPT_'))
def export(name,vertices,faces,matrix):
 vp=folder/(name+'_v.npy');fp=folder/(name+'_f.npy')
 np.save(vp,vertices);np.save(fp,faces)
 return dict(name=name,vertices_path=str(vp),faces_path=str(fp),matrix=matrix.tolist())
request=dict(mode='POSITION',implant=export('implant',v,f,base),bone=export('bone',bone.vertices,bone.faces,np.eye(4)),obstacles=[],platform=[3,0,2],
 settings=dict(max_shift_mm=3.,max_tilt_deg=0.,boundary_reserve_mm=.1,min_coverage=.8,mpr_guided_selection=True,budget=60))
answer=run(request)
assert answer['best']['evaluation']['mpr_checks']['status']=='MEASURED'
request.update(mode='VALIDATE',candidate=answer['best'])
assert run(request)['status']=='VALIDATED'
request['obstacles']=[dict(export('obstruction',bone.vertices,bone.faces,np.eye(4)),margin_mm=2.,kind='Protected structure')]
assert run(request)['status']=='REJECTED'
print('MPR_GUIDED_WORKER_SEARCH_FRESH_VALIDATION_AND_OBSTRUCTION_PASS')
