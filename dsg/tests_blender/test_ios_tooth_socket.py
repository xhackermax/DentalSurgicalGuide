"""Native edit/delete workflow, concave closure, rim preservation and cancel."""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import dsg
dsg.register()


class Layout:
    def __init__(self):
        self.operators = []

    def operator(self, identifier, **kwargs):
        self.operators.append(identifier)
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


def model(name, count=8, scale=(1, 1, 1), rotation=0):
    vertices = [(5 * math.cos(i * math.tau/count), 5 * math.sin(i * math.tau/count), z)
                for z in (0, 4) for i in range(count)]
    vertices.append((0, 0, 6))
    faces = [tuple(reversed(range(count)))]
    faces += [(i, (i+1)%count, (i+1)%count+count, i+count) for i in range(count)]
    faces += [(2*count, i+count, (i+1)%count+count) for i in range(count)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = Matrix.Rotation(rotation, 4, 'Y') @ Matrix.Diagonal((*scale, 1))
    obj['DSG_base_closed_manifold'] = True
    obj['dental_suite_aligned'] = True
    bpy.context.scene.dsg_props.model_obj = obj
    bpy.context.scene.dsg_props.current_step = 0
    return obj


def delete_tooth(obj, count):
    assert bpy.ops.dsg.ios_begin_tooth_removal() == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    bm = bmesh.from_edit_mesh(obj.data)
    for vertex in bm.verts:
        vertex.select_set(vertex.co.z > 5)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.dsg.ios_save_tooth_selection() == {'FINISHED'}


try:
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.dsg.ios_begin_tooth_removal.get_rna_type()
    obj = model('Depth rejection')
    layout = Layout()
    dsg.guide_module._draw_step_model_axis(layout, layout, bpy.context, bpy.context.scene.dsg_props)
    assert 'dsg.ios_begin_tooth_removal' in layout.operators, 'Closed-model stage hides the new tool'
    delete_tooth(obj, 8)
    layout = Layout()
    dsg.guide_module._draw_step_model_axis(layout, layout, bpy.context, bpy.context.scene.dsg_props)
    assert 'dsg.ios_close_tooth_socket' in layout.operators, 'Hole-edit stage hides its closure action'
    assert 'dsg.close_model_base' not in layout.operators, 'Tooth hole was mistaken for an open base'
    before = bmesh.from_edit_mesh(obj.data)
    coordinates = sorted(tuple(vertex.co) for vertex in before.verts)
    face_count = len(before.faces)
    bpy.context.scene.dsg_props.ios_socket_depth_mm = 10
    try:
        bpy.ops.dsg.ios_close_tooth_socket()
        raise AssertionError('An excessive cavity depth was accepted')
    except RuntimeError as error:
        assert 'profundidad' in str(error).lower()
    restored = bmesh.from_edit_mesh(obj.data)
    assert sorted(tuple(vertex.co) for vertex in restored.verts) == coordinates
    assert len(restored.faces) == face_count, 'Rejected closure modified the original hole'
    assert bpy.ops.dsg.ios_cancel_tooth_removal() == {'FINISHED'}
    assert len(obj.data.vertices) == 17, 'Cancel did not recover the deleted tooth'
    bpy.data.objects.remove(obj, do_unlink=True)
    for count, scale, rotation in [(8, (1,1,1), 0), (7, (1.5,.8,1.2), .8), (4, (1,1,1), .4)]:
        obj = model('Socket test', count, scale, rotation)
        original = [tuple(vertex.co) for vertex in obj.data.vertices]
        delete_tooth(obj, count)
        before = bmesh.from_edit_mesh(obj.data)
        border = [tuple(vertex.co) for vertex in before.verts if abs(vertex.co.z-4) < 1e-5]
        bpy.context.scene.dsg_props.ios_socket_depth_mm = 2
        assert bpy.ops.dsg.ios_close_tooth_socket() == {'FINISHED'}
        assert bpy.context.mode == 'OBJECT'
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        assert all(edge.is_manifold for edge in bm.edges), 'Closure is not manifold'
        points = {tuple(vertex.co) for vertex in bm.verts}
        assert obj['DSG_ios_rim_smoothing_vertices'] == count
        assert obj['DSG_ios_rim_smoothing_max_mm'] <= .201
        assert set(original[:count]).issubset(points), 'Smoothing moved vertices outside the rim'
        interior = [vertex for vertex in bm.verts if vertex.co.z < 4 - 1e-5 and vertex.co.z > 0]
        assert interior, 'Grid Fill stayed flat instead of creating an inward cavity'
        axis = (obj.matrix_world.to_3x3().inverted().transposed() @ Vector((0,0,1))).normalized()
        plane = obj.matrix_world @ Vector((0,0,4))
        depths = [-(obj.matrix_world @ vertex.co - plane).dot(axis) for vertex in interior]
        assert abs(max(depths) - 2) < 1e-4, ('Incorrect physical depth', depths)
        assert obj.get('DSG_ios_socket_count', 0) == 1
        bm.free()
        assert bpy.ops.dsg.ios_begin_tooth_removal() == {'FINISHED'}
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete(type='VERT')
        assert bpy.ops.dsg.ios_cancel_tooth_removal() == {'FINISHED'}
        assert len(obj.data.vertices) > 0, 'Cancel did not restore geometry'
        bpy.data.objects.remove(obj, do_unlink=True)
    obj = model('Native undo test')
    original = sorted(tuple(vertex.co) for vertex in obj.data.vertices)
    bpy.ops.ed.undo_push(message='IOS before removing the tooth')
    delete_tooth(obj, 8)
    bpy.context.scene.dsg_props.ios_socket_depth_mm = 2
    assert bpy.ops.dsg.ios_close_tooth_socket() == {'FINISHED'}
    bpy.ops.ed.undo_push(message='IOS after socket closure')
    bpy.ops.ed.undo()
    restored = bpy.data.objects.get('Native undo test')
    assert restored is not None
    if restored.mode == 'EDIT':
        restored.update_from_editmode()
    assert sorted(tuple(vertex.co) for vertex in restored.data.vertices) == original, 'Native undo did not restore the IOS'
    print('IOS_TOOTH_SOCKET_PASS: even/odd/quad rims, rotation, scale, depth, manifold, cancel, native undo', flush=True)
finally:
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    dsg.unregister()
