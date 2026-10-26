"""Synthetic geometry only: bounded search, full-face exclusions, real asset poses."""
import sys,tempfile,json
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.implant_optimizer_geometry import Solid,clearance
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_optimizer_worker import run

def cube(size=2,center=(0,0,0),scale=(1,1,1)):
    bpy.ops.mesh.primitive_cube_add(size=size)
    obj=bpy.context.object;v,f,_=_mesh_arrays(obj.data)
    bpy.data.objects.remove(obj,do_unlink=True)
    return v*np.asarray(scale)+np.asarray(center),f

a=Solid(*cube(),'implant')
slab=Solid(*cube(scale=(.1,2,2)),'thin nasal slab')
assert clearance(a,slab,2)['status']=='CONTACT','Crossing faces without inside vertices passed'
contained=Solid(*cube(size=.1),'contained canal')
assert clearance(a,contained,2)['status']=='CONTACT'
assert clearance(a,Solid(*cube(center=(4.5,0,0)),'canal'),2)['status']=='SAFE'
assert clearance(a,Solid(*cube(center=(3.8,0,0)),'canal'),2)['status']!='SAFE'
v,f=cube()
try:Solid(v,f[:-1],'open bone');raise AssertionError('Open bone accepted')
except ValueError:pass

folder=Path(tempfile.mkdtemp(prefix='DSG_TEST_OPT_'))
def asset(name,mesh):
    v,f=mesh;vp=folder/(name+'_v.npy');fp=folder/(name+'_f.npy')
    np.save(vp,v);np.save(fp,f)
    return {'name':name,'vertices_path':str(vp),'faces_path':str(fp),'matrix':np.eye(4).tolist()}

req={'mode':'POSITION','implant':asset('implant',cube()),'bone':asset('bone',cube(size=3,center=(.8,0,0))),
     'obstacles':[],'platform':[0,0,1],'settings':{'max_shift_mm':1.,'max_tilt_deg':0.,'min_coverage':.2,'boundary_reserve_mm':.1,'budget':60}}
result=run(req)
assert result['status']=='PROPOSAL',result
assert result['best']['evaluation']['support_fraction']>result['baseline']['evaluation'].get('support_fraction',0.)
assert not result['baseline']['evaluation']['admissible'],'Baseline protrudes from bone and must fail the wall reserve'
assert np.allclose(np.asarray(result['best']['matrix'])[:3,:3],np.eye(3))
assert req['implant']['matrix']==np.eye(4).tolist(),'Input pose mutated'
req.update(mode='VALIDATE',candidate=result['best'])
assert run(req)['status']=='VALIDATED'
req['obstacles']=[dict(asset('canal',cube(size=6)),margin_mm=2,kind='nerve')]
assert run(req)['status']=='REJECTED','Fresh obstruction ignored on apply'
req.update(mode='SIZE',obstacles=[],bone=asset('large_bone',cube(size=20)),family='SYNTHETIC',current_id=None)
catalogue=[]
for name,size in [('small',1),('large',2)]:
    row=asset(name,cube(size=size));row.update(id=name,family='SYNTHETIC',diameter_mm=size,length_mm=size,
        platform_local_mm=[0,0,size/2],reference='SYNTHETIC TEST ONLY')
    catalogue.append(row)
req['catalogue']=catalogue
result=run(req);assert result['status']=='COMPARISON' and result['best']['asset']['id']=='large'
matrix=np.asarray(result['best']['matrix']);assert np.allclose(matrix[:3,:3],np.eye(3))
assert np.allclose(matrix@np.r_[result['best']['asset']['platform_local_mm'],1],[0,0,1,1])
print('IMPLANT_OPTIMIZER_GEOMETRY_PASS',flush=True)
