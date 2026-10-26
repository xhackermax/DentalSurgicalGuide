"""Coronal cross-section extrusion, unchanged root and actual hidden IOS cut."""
import sys,math
import bpy,bmesh
import numpy as np

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core
from dsg.blender import socket_reach as reach,ios_socket_boolean as boolean

try:
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    n=24
    rings=[(-8,.8),(-4,2.),(-2,2.),(0,.3)]
    vertices=[(r*math.cos(i*math.tau/n),r*math.sin(i*math.tau/n),z) for z,r in rings for i in range(n)]
    faces=[tuple(reversed(range(n))),tuple(range(3*n,4*n))]
    for j in range(3):faces.extend([(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for i in range(n)])
    mesh=bpy.data.meshes.new('Root');mesh.from_pydata(vertices,[],faces);mesh.update()
    tooth=bpy.data.objects.new('DSG_Tooth_FDI_15',mesh);bpy.context.scene.collection.objects.link(tooth)
    tooth['DSG_tooth_instance']=True;tooth['DSG_fdi_number']=15;tooth['DSG_tooth_axis_apical_world']=[0,0,-1]
    original=[tuple(v.co) for v in tooth.data.vertices]
    bpy.ops.mesh.primitive_cube_add(size=16,location=(0,0,-6))
    ios=bpy.context.object;ios.hide_set(True)
    cutter,_=core._prepare_alveolar_cutter(bpy.context,tooth)
    before=reach._world(cutter);top=before[:,2].max();level=top-reach.BAND_MM
    need=reach.extend(cutter,tooth,ios)
    assert need>0 and cutter['DSG_occlusal_extension_method']=='ROOT_CROSS_SECTION_EXTRUSION'
    after=reach._world(cutter)
    rounded={tuple(np.round(p,5)) for p in after}
    assert all(tuple(np.round(p,5)) in rounded for p in before if p[2]<level-1e-4)
    top_ring=after[abs(after[:,2]-(top+need))<1e-4]
    base_ring=after[abs(after[:,2]-level)<1e-4]
    assert len(top_ring)==len(base_ring)>12
    assert {tuple(np.round(p[:2],5)) for p in top_ring}=={tuple(np.round(p[:2],5)) for p in base_ring}
    assert not core._mesh_topology_counts(cutter.data)['non_manifold_edges']
    bm=bmesh.new();bm.from_mesh(ios.data);v0=abs(bm.calc_volume());bm.free()
    tree=reach.cutter_tree(cutter)
    result=core._apply_alveolar_boolean(bpy.context,ios,cutter)
    assert result['ok'] and ios.hide_get()
    cleaned,_=core._clean_postextraction_boolean_debris(ios)
    assert cleaned and reach.verify_opening(ios,tooth,tree)['verified']
    bm=bmesh.new();bm.from_mesh(ios.data);v1=abs(bm.calc_volume());bm.free()
    assert v0-v1>1 and original==[tuple(v.co) for v in tooth.data.vertices]
    assert not boolean.applied(ios), 'Old markers accepted without an opening verification revision'
    print('OCCLUSAL_ROOT_EXTENSION_PASS: constant section, unchanged apical root, manifold cutter, hidden IOS volume reduction, open socket',flush=True)
finally:
    dsg.unregister()
