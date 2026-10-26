"""The immediate tooth Boolean must run after the concave socket closure."""
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import bmesh
import bpy

sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import dsg
dsg.register()
from dsg import core, cbct_dental_module as dental


def volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    result = abs(bm.calc_volume())
    bm.free()
    return result


def make_ios():
    count = 8
    vertices = [(5*math.cos(i*math.tau/count), 5*math.sin(i*math.tau/count), z)
                for z in (0, 4) for i in range(count)] + [(0,0,6)]
    faces = [tuple(reversed(range(count)))]
    faces += [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
    faces += [(16,i+count,(i+1)%count+count) for i in range(count)]
    mesh = bpy.data.meshes.new('IOS source')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('IOS source', mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj['DSG_base_closed_manifold'] = True
    obj['dental_suite_aligned'] = True
    bpy.context.scene.dsg_props.model_obj = obj
    return obj


try:
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'IMMEDIATE'
    scene.dsg_suite_settings.target_fdi = '11'
    scene[core.IMMEDIATE_FDIS_KEY] = '[11]'
    obj = make_ios()
    original = [tuple(vertex.co) for vertex in obj.data.vertices]
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,3))
    tooth = bpy.context.object
    tooth.name = dental.TOOTH_OBJECT_PREFIX + '11'
    tooth.scale.z = 2
    tooth['DSG_tooth_instance'] = True
    tooth['DSG_fdi_number'] = 11
    scene['DSG_ios_postextraction_preview_name'] = obj.name
    obj['DSG_ios_postextraction_state'] = 'SOLID_CLOSED'
    with patch.object(core, '_apply_alveolar_boolean', side_effect=AssertionError('Early Boolean')) as early:
        try:
            bpy.ops.dsg_suite.confirm_ios_postextraction()
            raise AssertionError('Legacy action allowed a Boolean before the inward closure')
        except RuntimeError as error:
            assert 'hueco' in str(error).lower()
        assert not early.called
    scene['DSG_ios_postextraction_preview_name'] = ''
    from dsg.blender import ios_tooth_edit
    assert not ios_tooth_edit.immediate_ready(bpy.context)
    try:
        bpy.ops.dsg.prepare_aligned_model()
        raise AssertionError('Retentive preparation bypassed the socket Boolean')
    except RuntimeError as error:
        assert 'hueco' in str(error).lower()
    bpy.ops.ed.undo_push(message='IOS before socket and immediate Boolean')
    actual = core._apply_alveolar_boolean
    calls = []

    def ordered_boolean(context, target, cutter):
        assert target.get('DSG_ios_socket_count', 0) == 1, 'Boolean ran before socket closure'
        assert not core._mesh_topology_counts(target.data)['boundary_edges']
        assert any(.1 < vertex.co.z < 3 for vertex in target.data.vertices), 'Socket center is not inward'
        calls.append(volume(target))
        return actual(context, target, cutter)

    assert bpy.ops.dsg.ios_begin_tooth_removal() == {'FINISHED'}
    assert not calls, 'Entering Edit started the Boolean'
    bm = bmesh.from_edit_mesh(obj.data)
    for vertex in bm.verts:
        vertex.select_set(vertex.co.z > 5)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.dsg.ios_save_tooth_selection() == {'FINISHED'}
    assert not calls, 'Deleting the crown started the Boolean before closure'
    scene.dsg_props.ios_socket_depth_mm = 2
    # Closing the hole no longer subtracts: the Boolean comes after the
    # retentive model, in the virtual-extraction step.
    with patch.object(core, '_apply_alveolar_boolean', side_effect=AssertionError('Boolean on close')):
        assert bpy.ops.dsg.ios_close_tooth_socket() == {'FINISHED'}
    from dsg.blender import ios_tooth_edit, ios_socket_boolean as socket_boolean
    assert ios_tooth_edit.immediate_ready(bpy.context), 'A closed hole must allow the retentive model'
    assert obj[socket_boolean.PENDING] and not socket_boolean.ready(bpy.context, obj)
    with patch.object(core, '_apply_alveolar_boolean', side_effect=ordered_boolean):
        assert bpy.ops.dsg.ios_retry_socket_boolean() == {'FINISHED'}
    assert len(calls) == 1, 'The deferred tooth Boolean did not run'
    assert volume(obj) < calls[0] - .01, 'The Boolean did not modify the closed IOS'
    assert obj.get('DSG_ios_socket_boolean_fdis_json') == '[11]'
    assert scene.dsg_props.model_obj == obj, 'Planning no longer points to the modified IOS'
    assert all(value == 0 for key, value in core._mesh_topology_counts(obj.data).items() if key != 'faces')
    from dsg.blender import ios_tooth_edit
    assert ios_tooth_edit.immediate_ready(bpy.context)
    with patch.object(core, '_apply_alveolar_boolean', side_effect=AssertionError('Duplicate Boolean')):
        assert bpy.ops.dsg.ios_retry_socket_boolean() == {'FINISHED'}
    assert [tuple(vertex.co) for vertex in obj.get(ios_tooth_edit.BACKUP).vertices] == original
    scene[core.IMMEDIATE_FDIS_KEY] = '[12]'
    previous = obj.data
    coordinates = [tuple(vertex.co) for vertex in obj.data.vertices]
    try:
        bpy.ops.dsg.ios_retry_socket_boolean()
        raise AssertionError('A missing CBCT tooth was accepted')
    except RuntimeError as error:
        assert 'FDI 12' in str(error)
    assert obj.data == previous and [tuple(vertex.co) for vertex in obj.data.vertices] == coordinates
    assert not socket_boolean.ready(bpy.context, obj)
    scene[core.IMMEDIATE_FDIS_KEY] = '[11]'
    assert bpy.ops.dsg.ios_retry_socket_boolean() == {'FINISHED'}
    bpy.ops.ed.undo_push(message='IOS after socket and immediate Boolean')
    bpy.ops.ed.undo()
    restored = bpy.data.objects.get('IOS source')
    assert restored is not None
    if restored.mode == 'EDIT':
        restored.update_from_editmode()
    assert [tuple(vertex.co) for vertex in restored.data.vertices] == original
    print('IOS_BOOLEAN_AFTER_SOCKET_PASS: order, early/blockout guards, real difference, manifold, idempotence, rollback, native undo', flush=True)
finally:
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    dsg.unregister()
