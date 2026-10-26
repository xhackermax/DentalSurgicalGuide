"""9.22.9: immediate implant - the extraction socket is not missing bone; apical anchorage required."""
import sys,tempfile
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.implant_catalogues import nominal_body_mesh
from dsg.implant_optimizer_worker import run
from dsg.blender.safety_volume import _mesh_arrays
folder=Path(tempfile.mkdtemp(prefix='DSG_TEST_SOCKET_'))
def save(name,v,f,matrix=None):
    vp=folder/(name+'_v.npy');fp=folder/(name+'_f.npy');np.save(vp,np.asarray(v,float));np.save(fp,np.asarray(f,np.int64))
    return dict(name=name,vertices_path=str(vp),faces_path=str(fp),matrix=np.eye(4).tolist() if matrix is None else matrix)
# Bone block z in [-20,0] with a 5 mm wide socket 6 mm deep (root removed from the bone label).
bpy.ops.mesh.primitive_cube_add(size=1);bone=bpy.context.object;bone.scale=(12,12,20);bone.location=(0,0,-10)
bpy.ops.mesh.primitive_cylinder_add(radius=2.5,depth=7,vertices=48,location=(0,0,-2.5));hole=bpy.context.object
mod=bone.modifiers.new('cut','BOOLEAN');mod.object=hole;mod.operation='DIFFERENCE';mod.solver='EXACT'
bpy.context.view_layer.objects.active=bone;bpy.ops.object.modifier_apply(modifier=mod.name)
for o in bpy.context.scene.objects:o.select_set(o==bone)
bpy.ops.object.transform_apply(location=True,scale=True)
bv,bf,_=_mesh_arrays(bone.data)
# Extracted root = the socket volume (reaching above the crest like a crown).
bpy.ops.mesh.primitive_cylinder_add(radius=2.4,depth=8,vertices=48,location=(0,0,-2));root=bpy.context.object
for o in bpy.context.scene.objects:o.select_set(o==root)
bpy.ops.object.transform_apply(location=True)
rv,rf,_=_mesh_arrays(root.data)
bone_item=save('bone',bv,bf);socket=save('root15',rv,rf)
def request(length,sockets):
    v,f=nominal_body_mesh(4.,length);pose=np.eye(4);pose[2,3]=-length/2
    return dict(mode='VALIDATE',implant=save(f'imp{length}',v,f,pose.tolist()),bone=bone_item,obstacles=[],platform=[0,0,0],sockets=sockets,
        settings={'min_coverage':.8,'boundary_reserve_mm':.5,'cervical_free_mm':1.,'min_apical_mm':3.},candidate={'matrix':pose.tolist()})
# Without socket handling an implant in a fresh socket can never be admissible.
r=run(request(11.5,[]));assert r['status']=='REJECTED',r
# With the socket: 11.5 mm -> 5.5 mm beyond the 6 mm socket: admissible.
r=run(request(11.5,[socket]));assert r['status']=='VALIDATED',r
e=r['evaluation'];assert 4.5<e['apical_engagement_mm']<6.,e;assert e['socket_fraction']>.3,e
# 8 mm -> ~2 mm beyond the socket: below the 3 mm apical anchorage.
r=run(request(8.,[socket]));assert r['status']=='REJECTED' and 'Anclaje apical' in r['evaluation']['reason'],r
print('IMMEDIATE_SOCKET_PASS:socket_not_missing_bone,apical_anchorage',flush=True)
