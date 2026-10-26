"""C activation, contextual P mapping, saved-region stability and closure gates."""
import sys
import math
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bmesh
import bpy

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core
from dsg.blender import ios_guided_selection as guided, ios_tooth_edit as edit


class Layout:
    def __init__(self):
        self.ids = []
    def operator(self, name, **kwargs):
        self.ids.append(name)
        return self
    def __getattr__(self,name):
        return lambda *args,**kwargs:self


try:
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'SIMPLE'
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    n = 8
    vertices = [(5*math.cos(i*math.tau/n),5*math.sin(i*math.tau/n),z) for z in (0,4) for i in range(n)]+[(0,0,6)]
    faces = [tuple(reversed(range(n)))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]+[(16,i+n,(i+1)%n+n) for i in range(n)]
    mesh = bpy.data.meshes.new('Guided fixture')
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    obj = bpy.data.objects.new('Guided fixture',mesh)
    scene.collection.objects.link(obj)
    obj['DSG_base_closed_manifold'] = True
    scene.dsg_props.model_obj = obj
    assert bpy.ops.dsg.ios_begin_tooth_removal() == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    assert not edit.DSG_OT_IOSCloseToothSocket.poll(bpy.context)
    layout = Layout()
    edit.draw(layout,bpy.context)
    assert 'dsg.ios_save_tooth_selection' in layout.ids
    assert 'dsg.ios_close_tooth_socket' not in layout.ids
    # UI Circle Select is activated by code, not delegated to the user.
    tool = Mock()
    modes = Mock()
    with patch.object(guided,'bpy',SimpleNamespace(app=SimpleNamespace(background=False),ops=SimpleNamespace(wm=SimpleNamespace(tool_set_by_id=tool)))), \
            patch.object(guided,'set_circle_mode',modes):
        guided.activate_circle(SimpleNamespace(area=SimpleNamespace(type='VIEW_3D')))
    tool.assert_called_once_with(name='builtin.select_circle',space_type='VIEW_3D')
    assert modes.call_args[0][1] == 'ADD', 'Circle strokes must accumulate (several passes)'
    assert 'dsg.ios_selection_mode' in layout.ids and 'dsg.ios_clear_selection' in layout.ids
    try:
        bpy.ops.dsg.ios_save_tooth_selection()
        raise AssertionError('Empty selection was accepted')
    except RuntimeError:
        pass
    bm = bmesh.from_edit_mesh(mesh)
    for v in bm.verts:
        v.select_set(v.co.z > 5)
    bmesh.update_edit_mesh(mesh)
    original = sorted(tuple(v.co) for v in bm.verts)
    assert bpy.ops.dsg.ios_save_tooth_selection() == {'FINISHED'}
    assert sorted(tuple(v.co) for v in bm.verts) == original, 'Saving P deleted geometry early'
    assert obj[guided.SAVED] and edit.DSG_OT_IOSCloseToothSocket.poll(bpy.context)
    assert obj['DSG_ios_tooth_saved_face_count'] == 8, 'Brushed vertex must save the faces it touches'
    # P shows the cleaned region as the live selection; CERRAR uses it.
    assert sum(1 for f in bm.faces if f.select) == 8
    # A whole-IOS selection is rejected at CERRAR instead of deleting everything.
    bpy.ops.mesh.select_all(action='SELECT')
    try:
        bpy.ops.dsg.ios_close_tooth_socket()
        raise AssertionError('Whole-model selection was accepted')
    except RuntimeError:
        pass
    assert bpy.context.mode == 'EDIT_MESH' and len(bmesh.from_edit_mesh(mesh).faces) == 17
    bm = bmesh.from_edit_mesh(mesh)
    for f in bm.faces:
        f.select_set(False)
    for v in bm.verts:
        v.select_set(v.co.z > 5)
    bmesh.update_edit_mesh(mesh)
    scene.dsg_props.ios_socket_depth_mm = 2
    assert bpy.ops.dsg.ios_close_tooth_socket() == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and len(mesh.vertices) > 0
    assert obj['DSG_ios_rim_smoothing_vertices'] == 8
    assert 0 < obj['DSG_ios_rim_smoothing_max_mm'] <= .201
    assert not obj[guided.SAVED]
    assert not edit.editing(bpy.context)
    guided.register()
    for keymap,item in guided.KEYMAPS:
        assert keymap.name == 'Mesh'
        assert (item.type,item.idname) in {('P','dsg.ios_save_tooth_selection'),('C','dsg.ios_circle_selection')}
    assert not guided.DSG_OT_IOSSaveToothSelection.poll(bpy.context), 'P overrides native Blender outside the guided session'
    guided.unregister()
    assert not guided.KEYMAPS
    print('IOS_GUIDED_SELECTION_PASS: additive circle tool, correctable selection, P mapping, saved snapshot, closure gate, local rim smoothing',flush=True)
finally:
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    dsg.unregister()
