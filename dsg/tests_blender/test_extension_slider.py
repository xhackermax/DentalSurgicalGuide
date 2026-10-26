"""Slider preview, short-cut rollback and recomputation from a retained IOS."""
import sys
import bpy,bmesh
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core
from dsg.blender import extraction_extension as ext,ios_socket_boolean as boolean

def volume(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    try:return abs(bm.calc_volume())
    finally:bm.free()

try:
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene
    scene.dsg_suite_settings.workflow_route='IMMEDIATE'
    scene.dsg_suite_settings.target_fdi='15'
    scene[core.IMMEDIATE_FDIS_KEY]='[15]'
    bpy.ops.mesh.primitive_cube_add(size=16,location=(0,0,-6))
    ios=bpy.context.object
    ios['DSG_base_closed_manifold']=True
    ios['DSG_ios_socket_count']=1
    scene.dsg_props.model_obj=ios
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,radius=1,location=(0,0,-4))
    tooth=bpy.context.object;tooth.name='DSG_Tooth_FDI_15'
    tooth.scale.z=4
    tooth['DSG_tooth_instance']=True;tooth['DSG_fdi_number']=15
    tooth['DSG_tooth_axis_apical_world']=[0,0,-1]
    original=volume(ios)
    scene.dsg_props.extraction_extension_mm=0
    visual=bpy.data.objects[ext.NAME]
    assert visual['DSG_required_extension_mm']>2
    assert not visual['DSG_extension_sufficient']
    before=ios.data
    try:
        boolean.apply(bpy.context,ios)
        raise AssertionError('Insufficient length was applied')
    except RuntimeError as exc:assert 'insuficiente' in str(exc).lower()
    assert ios.data==before and volume(ios)==original
    scene.dsg_props.extraction_extension_mm=12
    assert scene.dsg_props.extraction_extension_mm==10
    assert visual['DSG_extension_sufficient']
    report=boolean.apply(bpy.context,ios)
    assert report[0]['socket_opening']['verified']
    assert boolean.ready(bpy.context,ios) and volume(ios)<original-1
    base=bpy.data.meshes[ ios[boolean.BASE_MESH] ]
    probe=ios.copy();probe.data=base
    assert abs(volume(probe)-original)<1e-5
    bpy.data.objects.remove(probe)
    scene.dsg_props.extraction_extension_mm=visual['DSG_required_extension_mm']+.01
    assert not boolean.ready(bpy.context,ios)
    report=boolean.apply(bpy.context,ios)
    assert report[0]['socket_opening']['verified'] and boolean.ready(bpy.context,ios)
    assert bpy.data.meshes[ios[boolean.BASE_MESH]]==base
    assert bpy.types.Scene.bl_rna.properties['dsg_props']
    print('EXTENSION_SLIDER_PASS: 0..10 clamp, live preview, short Boolean rollback, actual opening, retained baseline and recomputation',flush=True)
finally:
    dsg.unregister()
