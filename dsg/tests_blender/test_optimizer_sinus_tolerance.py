"""9.22.8: maxillary sinus tolerated as in manual planning; nasal cavity keeps its margin."""
import sys,tempfile
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.implant_catalogues import nominal_body_mesh
from dsg.implant_optimizer_worker import run
folder=Path(tempfile.mkdtemp(prefix='DSG_TEST_SINUS_'))
def save(name,v,f,matrix=None):
    vp=folder/(name+'_v.npy');fp=folder/(name+'_f.npy');np.save(vp,v);np.save(fp,f)
    return dict(name=name,vertices_path=str(vp),faces_path=str(fp),matrix=np.eye(4).tolist() if matrix is None else matrix)
def box(name,lo,hi):
    bpy.ops.mesh.primitive_cube_add(size=2);o=bpy.context.object
    from dsg.blender.safety_volume import _mesh_arrays
    v,f,_=_mesh_arrays(o.data);bpy.data.objects.remove(o,do_unlink=True)
    lo=np.asarray(lo,float);hi=np.asarray(hi,float)
    return save(name,(v+1)/2*(hi-lo)+lo,f)
v,f=nominal_body_mesh(4.,8.)
pose=np.eye(4);pose[2,3]=-4.  # platform z=0, apex z=-10 (z up = coronal)
implant=save('implant',v,f,pose.tolist())
bone=box('bone',(-6,-6,-30),(6,6,.5))
def request(zone_top,kind,limit):
    zone=box('zone',(-8,-8,-40),(8,8,zone_top));zone.update(margin_mm=0.,kind=kind)
    if limit:zone['max_invasion_mm']=limit
    return dict(mode='VALIDATE',implant=implant,bone=bone,obstacles=[zone],platform=[0,0,0],
        settings={'min_coverage':.8,'boundary_reserve_mm':.5,'cervical_free_mm':1.},candidate={'matrix':pose.tolist()})
# Sinus floor 1 mm above the apex -> 1 mm invasion, allowed with alert.
r=run(request(-7.0,'Seno maxilar derecho',2.))
assert r['status']=='VALIDATED',r
alert=r['evaluation']['alerts'][0];assert abs(alert['depth_mm']-1.)<.1,alert
# At 2 mm, keep the alert; above 2 mm, reject.
r=run(request(-6.0,'Seno maxilar derecho',2.));assert r['status']=='VALIDATED' and r['evaluation']['alerts'],r
r=run(request(-5.99,'Seno maxilar derecho',2.));assert r['status']=='REJECTED',r
# 3 mm invasion exceeds the limit.
r=run(request(-5.0,'Seno maxilar derecho',2.));assert r['status']=='REJECTED' and 'invasión' in r['evaluation']['reason'],r
# Clear of the sinus: no alert.
r=run(request(-9.0,'Seno maxilar derecho',2.));assert r['status']=='VALIDATED' and not r['evaluation']['alerts'],r
# Nasal cavity: no added buffer, but any penetration still rejected.
r=run(request(-7.0,'Cavidad nasal derecha',0.));assert r['status']=='REJECTED',r
r=run(request(-8.01,'Cavidad nasal derecha',0.));assert r['status']=='VALIDATED',r
r=run(request(-11.0,'Cavidad nasal derecha',0.));assert r['status']=='VALIDATED',r
print('SINUS_TOLERANCE_PASS:2mm_alert,above2mm_reject,nasal_zero_buffer_no_penetration',flush=True)

# At exactly 10 mm the previous 2 mm allowance must not apply.
v,f=nominal_body_mesh(4.,10.);pose[2,3]=-5.;implant=save('long_implant',v,f,pose.tolist())
r=run(request(-9.,'Seno maxilar derecho',2.));assert r['status']=='REJECTED',r
r=run(request(-10.01,'Seno maxilar derecho',2.));assert r['status']=='VALIDATED',r
print('LENGTH_DEPENDENT_SINUS_3D_PASS:8mm_up_to2,10mm_zero_entry,nasal_unchanged')

# Scaled local 8 mm bodies must use physical length in both search and validation.
v,f=nominal_body_mesh(4.,8.);pose=np.eye(4);pose[2,2]=1.5;pose[2,3]=-6.
implant=save('scaled_implant',v,f,pose.tolist())
r=run(request(-11.,'Seno maxilar derecho',2.));assert r['status']=='REJECTED',r
print('SCALED_LENGTH_RULE_PASS:physical12mm_cannot_use_short_implant_allowance')

# Custom-library source nominal length must survive independently of current ID.
v,f=nominal_body_mesh(4.,9.95);pose=np.eye(4);pose[2,3]=-4.975
implant=save('custom_source',v,f,pose.tolist())
q=request(-9.,'Seno maxilar derecho',2.);q['current']=None;q['source_nominal_length_mm']=10.
r=run(q);assert r['status']=='REJECTED',r
print('CUSTOM_NOMINAL_LENGTH_PASS:nominal10_physical9_95_no_entry')
