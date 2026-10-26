"""Manual removal is optional; immediate Boolean remains a real prerequisite."""
import sys
import bpy
from mathutils import Vector

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core, cbct_dental_module as dental
from dsg.blender import ios_tooth_edit as edit, ios_skip_removal as skip, ios_socket_boolean as boolean

try:
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'SIMPLE'
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,radius=5)
    ios = bpy.context.object
    ios.name = 'IOS skip fixture'
    ios['DSG_base_closed_manifold'] = True
    scene.dsg_props.model_obj = ios
    original = [tuple(v.co) for v in ios.data.vertices]
    assert bpy.ops.dsg.ios_skip_tooth_removal() == {'FINISHED'}
    assert ios[skip.SKIPPED] and not ios.get('DSG_ios_socket_count')
    assert original == [tuple(v.co) for v in ios.data.vertices]
    # Skip from a guided Edit session restores its backup before proceeding.
    assert bpy.ops.dsg.ios_begin_tooth_removal() == {'FINISHED'}
    assert not ios[skip.SKIPPED]
    assert bpy.ops.dsg.ios_skip_tooth_removal() == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and not edit.editing(bpy.context)
    assert original == [tuple(v.co) for v in ios.data.vertices]
    scene.dsg_suite_settings.workflow_route = 'IMMEDIATE'
    scene[core.IMMEDIATE_FDIS_KEY] = '[11]'
    assert not boolean.ready(bpy.context,ios), 'Skip alone falsely certifies an immediate IOS'
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,4))
    tooth = bpy.context.object
    tooth.name = dental.TOOTH_OBJECT_PREFIX+'11'
    tooth['DSG_tooth_instance'] = True
    tooth['DSG_fdi_number'] = 11
    bpy.context.view_layer.update()
    assert bpy.ops.dsg.ios_skip_tooth_removal() == {'FINISHED'}
    assert ios[boolean.PENDING] and not boolean.ready(bpy.context,ios), 'Skip must leave the Boolean for after the retentive model'
    assert edit.immediate_ready(bpy.context), 'Skip must allow the retentive model'
    assert bpy.ops.dsg.ios_retry_socket_boolean() == {'FINISHED'}
    assert boolean.ready(bpy.context,ios)
    assert ios[boolean.APPLIED] == '[11]'
    assert not ios.get('DSG_ios_socket_count'), 'Skip invented a concave closure'
    assert ios['DSG_ios_postextraction_state'] == 'BOOLEAN_APPLIED_MANUAL_REMOVAL_SKIPPED'
    topology = core._mesh_topology_counts(ios.data)
    assert not topology['boundary_edges'] and not topology['non_manifold_edges']
    assert original != [tuple(v.co) for v in ios.data.vertices], 'Immediate skip did not prepare the actual IOS'
    scene[core.IMMEDIATE_FDIS_KEY] = '[11,12]'
    previous = ios.data
    assert bpy.ops.dsg.ios_skip_tooth_removal() == {'FINISHED'}
    assert ios.data == previous and ios[boolean.PENDING]
    assert not boolean.ready(bpy.context,ios), 'Missing CBCT tooth did not block preparation'
    assert edit.DSG_OT_IOSRetrySocketBoolean.poll(bpy.context)
    print('IOS_SKIP_REMOVAL_PASS: simple unchanged, edit restored, real immediate Boolean, no fake socket, missing-FDI gate',flush=True)
finally:
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    dsg.unregister()
