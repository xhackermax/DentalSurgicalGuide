"""Immediate step 4: tooth visible → REALIZAR EXTRACCIÓN VIRTUAL → SIGUIENTE; undo restores."""
import sys
import bmesh
import bpy

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core,cbct_dental_module as dental
from dsg.blender import virtual_extraction as ve, protected_neighbors as n

try:
    scene = bpy.context.scene
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    scene.dsg_suite_settings.workflow_route = 'IMMEDIATE'
    scene[core.IMMEDIATE_FDIS_KEY] = '[16]'
    mesh = bpy.data.meshes.new('Bone')
    b = bmesh.new(); bmesh.ops.create_icosphere(b,subdivisions=4,radius=10.0); b.to_mesh(mesh); b.free()
    bone = bpy.data.objects.new('Dental_DICOM_Maxilla',mesh); scene.collection.objects.link(bone)
    scene['DSG_maxilla_object'] = bone.name
    mesh = bpy.data.meshes.new('Tooth')
    b = bmesh.new(); bmesh.ops.create_cube(b,size=4.0); b.to_mesh(mesh); b.free()
    tooth = bpy.data.objects.new(dental.TOOTH_OBJECT_PREFIX+'16',mesh); scene.collection.objects.link(tooth)
    tooth.location = (0,0,10)
    tooth['DSG_tooth_instance'] = True
    tooth['DSG_fdi_number'] = 16
    faces = len(bone.data.polygons)
    assert not ve.performed(scene) and not ve.confirmed(scene)
    assert bpy.ops.dsg.perform_virtual_extraction() == {'FINISHED'}
    assert ve.performed(scene) and not ve.confirmed(scene)
    assert len(bone.data.polygons) != faces and ve._closed(bone.data), 'socket not carved as a closed solid'
    assert tooth.hide_viewport, 'extracted tooth must be hidden'
    assert bpy.ops.dsg.confirm_virtual_extraction() == {'FINISHED'}
    assert ve.confirmed(scene) and scene.get(n.EDITOR), 'SIGUIENTE must open neighbour selection'
    assert not n.confirmed(scene), 'Neighbours must be confirmed before the implant is placed'
    assert bpy.ops.dsg.confirm_protected_neighbors() == {'FINISHED'} and n.confirmed(scene)
    assert bpy.ops.dsg.undo_virtual_extraction() == {'FINISHED'}
    assert len(bone.data.polygons) == faces and not tooth.hide_viewport and not ve.performed(scene)
    print('VIRTUAL_EXTRACTION_PASS: visible tooth, closed socket, SIGUIENTE, reversible',flush=True)
finally:
    dsg.unregister()
