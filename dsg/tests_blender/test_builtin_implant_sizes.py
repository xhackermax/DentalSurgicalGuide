"""Nominal preselection from user matrix, constrained separately by bone and hazards."""
import sys,tempfile
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt,safety_volume as safety
from dsg.implant_catalogues import nominal_body_mesh,rows
from dsg.implant_optimizer_worker import run

folder=Path(tempfile.mkdtemp(prefix='DSG_TEST_NOMINAL_'))
def mesh(name,vertices,faces,matrix=None):
    vp=folder/(name+'_v.npy');fp=folder/(name+'_f.npy');np.save(vp,vertices);np.save(fp,faces)
    return dict(name=name,vertices_path=str(vp),faces_path=str(fp),matrix=np.eye(4).tolist() if matrix is None else matrix)
def cube(name,extent,center=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=2)
    o=bpy.context.object
    from dsg.blender.safety_volume import _mesh_arrays
    v,f,_=_mesh_arrays(o.data);bpy.data.objects.remove(o,do_unlink=True)
    return mesh(name,v*np.asarray(extent)+np.asarray(center),f)
try:
    assert g.deferred_post_register();safety.unregister()
    for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
    catalogue=[]
    for r in rows('BTI_COREX'):
        v,f=nominal_body_mesh(r['diameter_mm'],r['length_mm']);catalogue.append(dict(r,**mesh(r['id'],v,f)))
    # Bone width +/-2.8 with 0.5 wall reserve permits diameter <=4.5, never5/5.5.
    # Nasal floor at z=-10 and 2mm margin permits nominal length<=8 (platformz0).
    pose=np.eye(4);pose[2,3]=-4
    req=dict(mode='SIZE',implant=mesh('implant',*nominal_body_mesh(4,8),pose.tolist()),
        bone=cube('native_bone',(2.8,8,10),(0,0,-10)),obstacles=[dict(cube('sinus',(20,20,4),(0,0,-14)),margin_mm=2.,kind='Sinus')],
        platform=[0,0,0],family='BTI CORE-X',catalogue=catalogue,current_id=None,
        settings={'min_coverage':.8,'boundary_reserve_mm':.5})
    result=run(req)
    assert result['status']=='NOMINAL_PROPOSAL',result
    best=result['best']['asset']
    assert best['diameter_mm']==4.5 and best['length_mm']==7.5,best
    assert np.allclose(np.asarray(result['best']['matrix'])@np.r_[best['platform_local_mm'],1],[0,0,0,1])
    req['obstacles'][0]['kind']='Nervio dentario inferior'
    assert run(req)['best']['asset']['length_mm']==7.5,'Neural buffer did not limit length'
    req['obstacles'].append(dict(cube('neighbor_tooth',(.5,20,20),(3.6,0,-5)),margin_mm=1.,kind='Raíz vecina'))
    neighbor_result=run(req)
    assert neighbor_result['best']['asset']['diameter_mm']==4.0,neighbor_result
    assert neighbor_result['best']['asset']['length_mm']==7.5,neighbor_result
    # 9.22.6: a nominal size is revalidated with its envelope before DSG resizes its own implant.
    req['obstacles']=req['obstacles'][:1];req.update(mode='VALIDATE',candidate=result['best'])
    assert run(req)['status']=='VALIDATED','Nominal envelope did not revalidate'
    longer=next(r for r in catalogue if r['diameter_mm']==4.5 and r['length_mm']==10.)
    m=np.eye(4);m[2,3]=-5.;req['candidate']={'matrix':m.tolist(),'asset':longer}
    assert run(req)['status']=='REJECTED','Too-long nominal size accepted on revalidation'
    scene=bpy.context.scene
    scene.dsg_opt_library='STRAUMANN_SP';assert scene.dsg_opt_family=='Straumann Standard Plus'
    assert len(opt._catalogue(scene))==12
    print('BUILTIN_IMPLANT_SIZES_PASS:60COREX/12SP,largest_admissible4.5x7.5,bone_width,sinus_length,fixed_platform,nominal_revalidation',flush=True)
finally:dsg.unregister()
