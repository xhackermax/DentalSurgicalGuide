"""Guided Circle Select → P snapshot → transactional IOS tooth removal."""
import bmesh
import bpy
from mathutils import Vector

SAVED = 'DSG_ios_tooth_selection_saved'
LAYER = 'DSG_ios_saved_tooth'
KEYMAPS = []


def activate_circle(context):
    if bpy.app.background:
        return
    if context.area is None or context.area.type != 'VIEW_3D':
        raise ValueError('Inicia la selección desde la vista 3D.')
    # Persistent circle-selection tool: unlike the modal C operator, it lets
    # P reach the guided save action as soon as the brush stroke is released.
    bpy.ops.wm.tool_set_by_id(name='builtin.select_circle', space_type='VIEW_3D')
    set_circle_mode(context, 'ADD')


def set_circle_mode(context, mode):
    """ADD keeps every brush stroke (several passes); SUB erases mistakes."""
    tool = context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=True)
    tool.operator_properties('view3d.select_circle').mode = mode
    context.scene['DSG_ios_circle_mode'] = mode


def circle_mode(context):
    return str(context.scene.get('DSG_ios_circle_mode', 'ADD'))


def _components(faces):
    faces = set(faces)
    parts = []
    while faces:
        seed = faces.pop()
        part, stack = {seed}, [seed]
        while stack:
            for edge in stack.pop().edges:
                for other in edge.link_faces:
                    if other in faces:
                        faces.discard(other)
                        part.add(other)
                        stack.append(other)
        parts.append(part)
    return parts


def _ring(faces):
    return {other for face in faces for vertex in face.verts for other in vertex.link_faces}


def _fill_holes(region):
    """Add unselected pockets fully enclosed by the region (bounded flood)."""
    limit = max(5000, 4 * len(region))
    outside = set()
    for face in list(_ring(region) - region):
        if face in region or face in outside:
            continue
        pocket, stack, escaped = {face}, [face], False
        while stack and not escaped:
            for edge in stack.pop().edges:
                for other in edge.link_faces:
                    if other in region or other in pocket:
                        continue
                    if other in outside or len(pocket) >= limit:
                        escaped = True
                        break
                    pocket.add(other)
                    stack.append(other)
                if escaped:
                    break
        if escaped:
            outside |= pocket
        else:
            region |= pocket
    return region


def _bowties(region):
    """Rim vertices touched by the region more than once (rim would cross)."""
    result = set()
    for face in region:
        for vertex in face.verts:
            rim_edges = sum(1 for edge in vertex.link_edges
                            if sum(1 for f in edge.link_faces if f in region) == 1)
            if rim_edges > 2:
                result.add(vertex)
    return result


def clean_region(bm):
    """Turn the brushed selection into one clean disc of faces.

    Keeps the largest connected part, closes 1-ring notches of the brush edge
    (dilate + erode), fills unselected pockets and removes rim crossings, so
    several passes, overlaps or small misses still give a single closed rim.
    """
    selected = [face for face in bm.faces if face.select]
    if not selected:  # only loose vertices brushed: take the faces they touch
        selected = list({face for v in bm.verts if v.select for face in v.link_faces})
    if not selected:
        raise ValueError('Selecciona el diente con el círculo antes de guardar.')
    region = max(_components(selected), key=len)
    closed = _ring(region)
    closed = {face for face in closed if all(other in closed for v in face.verts for other in v.link_faces)}
    region = max(_components(closed | region), key=len)
    region = _fill_holes(region)
    for _ in range(8):
        crossing = _bowties(region)
        if not crossing:
            break
        region |= {face for vertex in crossing for face in vertex.link_faces}
        region = _fill_holes(region)
    if len(region) >= len(bm.faces):
        raise ValueError('Selecciona solo el diente; no todo el IOS.')
    return region


def _saved_faces(bm):
    layer = bm.faces.layers.int.get(LAYER)
    if layer is not None:
        return [face for face in bm.faces if face[layer]]
    legacy = bm.verts.layers.int.get(LAYER)  # selections saved by 9.15/9.16
    if legacy is not None:
        return [face for face in bm.faces if all(v[legacy] for v in face.verts)]
    return []


def store_region(bm, region):
    """Mark the region in a face layer; returns the region re-fetched.

    Adding or removing a layer reallocates the BMesh elements, so face
    references collected before are stale: work with indices around it.
    """
    bm.faces.index_update()
    indices = {face.index for face in region}
    layer = bm.faces.layers.int.get(LAYER) or bm.faces.layers.int.new(LAYER)
    legacy = bm.verts.layers.int.get(LAYER)
    if legacy is not None:
        bm.verts.layers.int.remove(legacy)
    layer = bm.faces.layers.int.get(LAYER)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face[layer] = int(face.index in indices)
    return [bm.faces[index] for index in sorted(indices)]


def selected_copy(bm):
    copy = bm.copy()
    faces = _saved_faces(copy)
    if not faces or len(faces) == len(copy.faces):
        copy.free()
        raise ValueError('Selecciona solo el diente; no una región vacía ni todo el IOS.')
    bmesh.ops.delete(copy, geom=faces, context='FACES')
    return copy


def remove_saved(bm):
    faces = _saved_faces(bm)
    if not faces:
        raise ValueError('Guarda primero la selección del diente con P.')
    bmesh.ops.delete(bm, geom=faces, context='FACES')
    for layers in (bm.faces.layers.int, bm.verts.layers.int):
        layer = layers.get(LAYER)
        if layer is not None:
            layers.remove(layer)


def show_region(bm, region):
    for face in bm.faces:
        face.select_set(False)
    for face in region:
        face.select_set(True)
    bm.select_flush_mode()


def smooth_rim(bm, matrix, iterations=3, maximum_mm=.20):
    """Tangential rim smoothing that never flips a face.

    Each rim vertex moves only if its own faces keep their orientation and no
    edge collapses; otherwise that vertex stays where it was.  Dense scans
    with sub-0.2 mm triangles used to abort the whole closure here.
    """
    from .ios_tooth_edit import rim_loop
    ordered, edges = rim_loop(bm)
    original = [matrix @ v.co for v in ordered]
    normal = sum((p.cross(original[(i+1)%len(original)]) for i,p in enumerate(original)),Vector())
    if normal.length < 1e-10:
        raise ValueError('El borde del hueco no permite un suavizado estable.')
    normal.normalize()
    bm.normal_update()
    reference = {face: face.normal.copy() for v in ordered for face in v.link_faces}
    linear = matrix.to_3x3()
    inverse = matrix.inverted()

    def acceptable(vertex):
        for face in vertex.link_faces:
            face.normal_update()
            if face.normal.dot(reference[face]) <= .2:
                return False
        return all((linear @ (e.verts[0].co-e.verts[1].co)).length >= .001 for e in vertex.link_edges)

    kept = set()
    for _ in range(iterations):
        positions = [matrix @ v.co for v in ordered]
        for i, vertex in enumerate(ordered):
            delta = ((positions[i-1]+positions[(i+1)%len(positions)])*.5-positions[i])*.20
            delta -= normal*delta.dot(normal)
            candidate = positions[i]+delta
            moved = candidate-original[i]
            if moved.length > maximum_mm:
                candidate = original[i]+moved.normalized()*maximum_mm
            previous = vertex.co.copy()
            vertex.co = inverse @ candidate
            if not acceptable(vertex):
                vertex.co = previous
                for face in vertex.link_faces:
                    face.normal_update()
                kept.add(vertex)
    bm.normal_update()
    maximum = max((matrix @ v.co-p).length for v,p in zip(ordered,original))
    return {'vertices':len(ordered), 'iterations':iterations, 'max_mm':maximum, 'kept_vertices':len(kept)}


class DSG_OT_IOSSaveToothSelection(bpy.types.Operator):
    bl_idname = 'dsg.ios_save_tooth_selection'
    bl_label = 'GUARDAR SELECCIÓN (P)'
    bl_description = 'Guarda la región dental marcada con C sin separar ni borrar todavía la malla'
    bl_options = {'REGISTER','UNDO'}

    @classmethod
    def poll(cls, context):
        from .ios_tooth_edit import editing
        return context.mode == 'EDIT_MESH' and editing(context)

    def execute(self, context):
        obj = context.active_object
        try:
            count = save_current_selection(obj)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Selección guardada ({count} caras, borde limpio). Corrige con AÑADIR/QUITAR y vuelve a pulsar P, o CERRAR HUECO.')
        return {'FINISHED'}


def save_current_selection(obj):
    """Clean the current brush selection, check its rim and store it."""
    from .ios_tooth_edit import rim_loop
    bm = bmesh.from_edit_mesh(obj.data)
    region = store_region(bm, clean_region(bm))
    show_region(bm, region)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    preview = selected_copy(bm)
    try:
        rim_loop(preview)
    except ValueError:
        obj[SAVED] = False
        raise
    finally:
        preview.free()
    obj[SAVED] = True
    obj['DSG_ios_tooth_saved_vertex_count'] = len({v for f in region for v in f.verts})
    obj['DSG_ios_tooth_saved_face_count'] = len(region)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return len(region)


class DSG_OT_IOSSelectionMode(bpy.types.Operator):
    bl_idname = 'dsg.ios_selection_mode'
    bl_label = 'Modo de selección'
    bl_description = 'AÑADIR suma cada pasada del círculo; QUITAR borra lo seleccionado de más'
    mode: bpy.props.EnumProperty(items=(('ADD', 'Añadir', ''), ('SUB', 'Quitar', '')), default='ADD')

    def execute(self, context):
        if context.mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(type='VERT')
        activate_circle(context)
        set_circle_mode(context, self.mode)
        return {'FINISHED'}


class DSG_OT_IOSClearSelection(bpy.types.Operator):
    bl_idname = 'dsg.ios_clear_selection'
    bl_label = 'Empezar selección de nuevo'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        bpy.ops.mesh.select_all(action='DESELECT')
        context.active_object[SAVED] = False
        set_circle_mode(context, 'ADD')
        return {'FINISHED'}


class DSG_OT_IOSCircleSelection(bpy.types.Operator):
    bl_idname = 'dsg.ios_circle_selection'
    bl_label = 'Seleccionar con círculo (C)'

    @classmethod
    def poll(cls, context):
        from .ios_tooth_edit import editing
        return context.mode in {'OBJECT','EDIT_MESH'} and editing(context)

    def execute(self, context):
        if context.mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(type='VERT')
        activate_circle(context)
        return {'FINISHED'}


def register():
    config = bpy.context.window_manager.keyconfigs.addon
    if config is not None and not KEYMAPS:
        keymap = config.keymaps.new(name='Mesh',space_type='EMPTY',region_type='WINDOW')
        item = keymap.keymap_items.new('dsg.ios_save_tooth_selection','P','PRESS',head=True)
        KEYMAPS.append((keymap,item))
        item = keymap.keymap_items.new('dsg.ios_circle_selection','C','PRESS',head=True)
        KEYMAPS.append((keymap,item))


def unregister():
    for keymap,item in KEYMAPS:
        keymap.keymap_items.remove(item)
    KEYMAPS.clear()


CLASSES = (DSG_OT_IOSSaveToothSelection, DSG_OT_IOSCircleSelection, DSG_OT_IOSSelectionMode, DSG_OT_IOSClearSelection)
