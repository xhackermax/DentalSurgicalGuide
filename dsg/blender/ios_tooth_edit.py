"""Guided IOS tooth selection, conservative rim smoothing and concave closure."""
import heapq
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SESSION = 'DSG_ios_tooth_edit_active'
BACKUP = 'DSG_ios_tooth_edit_backup'


def socket_depth_property():
    return bpy.props.FloatProperty(
        name='Profundidad del hueco', default=2.0, min=0.05, max=20.0,
        description='Profundidad hacia el interior del cierre con Grid Fill, en mm')


def model(context):
    from .. import guide_module as guide
    obj = context.scene.dsg_props.model_obj
    if obj is not None:
        return guide._closed_counterpart(obj) or obj
    return None


def editing(context):
    obj = context.active_object
    return obj is not None and obj.type == 'MESH' and bool(obj.get(SESSION))


def immediate_ready(context):
    """IOS ready for the retentive model: tooth removed and hole closed inward.

    The CBCT-tooth Boolean (socket) is done later, after the retentive model,
    in the virtual-extraction step with the occlusal-extension bar.
    """
    from .. import core
    from .ios_socket_boolean import prepared
    if core.clinical_route(context.scene) != core.ROUTE_IMMEDIATE:
        return True
    obj = model(context)
    return obj is not None and prepared(obj)


def rim_loop(bm):
    edges = [edge for edge in bm.edges if edge.is_boundary]
    if not edges:
        raise ValueError('La selección guardada no genera un hueco válido.')
    if any(edge.is_wire or len(edge.link_faces) > 2 for edge in bm.edges):
        raise ValueError('La selección deja aristas sueltas o no manifold; vuelve a marcar el diente.')
    adjacent = {}
    for edge in edges:
        for vertex in edge.verts:
            adjacent.setdefault(vertex, []).append(edge)
    if any(len(links) != 2 for links in adjacent.values()):
        raise ValueError('El borde no forma un bucle cerrado; revisa la selección del diente.')
    # Reverse the adjacent face winding to get the outward normal of the missing cap.
    first = edges[0].link_loops[0]
    start, current = first.link_loop_next.vert, first.vert
    ordered = [start]
    visited = {start}
    previous = start
    while current != start:
        if current in visited:
            raise ValueError('El borde se cruza o contiene más de un hueco.')
        ordered.append(current)
        visited.add(current)
        neighbors = [edge.other_vert(current) for edge in adjacent[current]]
        following = next(vertex for vertex in neighbors if vertex != previous)
        previous, current = current, following
    if len(ordered) != len(adjacent):
        raise ValueError('Hay varios huecos: elimina y cierra un diente cada vez.')
    return ordered, edges


def close_socket(bm, matrix, depth_mm):
    """Native Grid Fill on the edit mesh; caller restores it if validation fails."""
    ordered, boundary = rim_loop(bm)
    if depth_mm <= 0:
        raise ValueError('La profundidad debe ser mayor que cero.')
    from .ios_guided_selection import smooth_rim
    smoothing = smooth_rim(bm, matrix)
    ordered, boundary = rim_loop(bm)
    world_rim = [matrix @ vertex.co for vertex in ordered]
    normal = sum((point.cross(world_rim[(index + 1) % len(world_rim)])
                  for index, point in enumerate(world_rim)), Vector())
    if normal.length < 1e-10:
        raise ValueError('El borde es degenerado y no permite definir el interior.')
    inward = -normal.normalized()
    inverse = matrix.inverted()
    local_direction = inverse.to_3x3() @ inward
    surface = BVHTree.FromBMesh(bm)
    material = boundary[0].link_faces[0].material_index
    marker = max(face.material_index for face in bm.faces) + 1
    if len(boundary) % 2:
        longest = max(boundary, key=lambda edge: (matrix.to_3x3() @ (edge.verts[0].co - edge.verts[1].co)).length)
        bmesh.ops.subdivide_edges(bm, edges=[longest], cuts=1)
        ordered, boundary = rim_loop(bm)
    fixed = set(ordered)
    original_faces = set(bm.faces)
    for face in bm.faces:
        face.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for vertex in bm.verts:
        vertex.select_set(False)
    for edge in boundary:
        edge.select_set(True)
    bmesh.update_edit_mesh(bpy.context.active_object.data, loop_triangles=False, destructive=True)
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.fill_grid(use_interp_simple=True)
    cap = [face for face in bm.faces if face not in original_faces]
    for face in cap:
        face.material_index = marker
    if not cap:
        raise ValueError('Grid Fill no pudo cerrar el borde; deshaz y revisa la selección.')
    interior = {vertex for face in cap for vertex in face.verts} - fixed
    if not interior:
        # A four-edge rim has no center vertex until its grid is subdivided.
        cap_edges = list({edge for face in cap for edge in face.edges})
        bmesh.ops.subdivide_edges(bm, edges=cap_edges, cuts=1, use_grid_fill=True)
        cap = [face for face in bm.faces if face.material_index == marker]
        fixed = {vertex for face in cap for vertex in face.verts
                 if any(other.material_index != marker for other in vertex.link_faces)}
        interior = {vertex for face in cap for vertex in face.verts} - fixed
    if not interior:
        raise ValueError('Grid Fill no generó una zona central para hundir el hueco.')
    cap_edges = {edge for face in cap for edge in face.edges}
    distances = {vertex: 0.0 for vertex in fixed}
    queue = [(0.0, index, vertex) for index, vertex in enumerate(fixed)]
    heapq.heapify(queue)
    serial = len(queue)
    while queue:
        distance, _, vertex = heapq.heappop(queue)
        if distance != distances[vertex]:
            continue
        for edge in vertex.link_edges:
            if edge not in cap_edges:
                continue
            other = edge.other_vert(vertex)
            candidate = distance + (matrix.to_3x3() @ (other.co - vertex.co)).length
            if candidate < distances.get(other, math.inf):
                distances[other] = candidate
                serial += 1
                heapq.heappush(queue, (candidate, serial, other))
    maximum = max(distances[vertex] for vertex in interior)
    if maximum < 1e-10:
        raise ValueError('El hueco es demasiado pequeño para generar una concavidad.')
    for vertex in interior:
        weight = math.sin(math.pi * .5 * distances[vertex] / maximum) ** 2
        depth = float(depth_mm) * weight
        hit, _, _, _ = surface.ray_cast(vertex.co + local_direction * 1e-5,
                                       local_direction.normalized())
        if hit is None:
            raise ValueError('No se encuentra la pared interior bajo el hueco; revisa el borde.')
        clearance = (matrix.to_3x3() @ (hit - vertex.co)).dot(inward)
        if depth >= clearance * .9:
            raise ValueError('La profundidad atraviesa el modelo; reduce Profundidad mm.')
        vertex.co += local_direction * depth
    for face in cap:
        face.material_index = material
        face.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if not all(edge.is_manifold for edge in bm.edges):
        raise ValueError('El cierre no quedó manifold; se conserva el hueco anterior.')
    obj = bpy.context.active_object
    obj['DSG_ios_rim_smoothing_vertices'] = smoothing['vertices']
    obj['DSG_ios_rim_smoothing_iterations'] = smoothing['iterations']
    obj['DSG_ios_rim_smoothing_max_mm'] = smoothing['max_mm']
    return len(cap)


class DSG_OT_IOSBeginToothRemoval(bpy.types.Operator):
    bl_idname = 'dsg.ios_begin_tooth_removal'
    bl_label = 'Seleccionar diente del IOS'
    bl_description = 'Inicia la selección guiada: Edición, selección circular C y guardar con P'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT','EDIT_MESH'} and not editing(context) and model(context) is not None

    def execute(self, context):
        from .. import guide_module as guide
        obj = model(context)
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        guide._clear_model_topology_cache()
        report = guide.get_model_topology_report_cached(obj)
        if not guide._workflow_closed_boundary_passes(report):
            self.report({'ERROR'}, 'Cierra primero el modelo IOS antes de eliminar un diente.')
            return {'CANCELLED'}
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        old = obj.get(BACKUP)
        if old is not None:
            del obj[BACKUP]
            if old.users == 0:
                bpy.data.meshes.remove(old)
        obj[BACKUP] = obj.data.copy()
        obj[SESSION] = True
        from .ios_skip_removal import SKIPPED
        obj['DSG_ios_edit_previous_skip'] = bool(obj.get(SKIPPED))
        obj[SKIPPED] = False
        from .ios_guided_selection import SAVED
        obj[SAVED] = False
        context.scene.dsg_props.model_obj = obj
        guide.set_active(context, obj)
        from .. import core
        for antagonist in core.antagonist_objects(obj):
            if (context.scene.objects.get(antagonist.name) == antagonist
                    and not antagonist.get('DSG_checkpoint_source_name')
                    and not antagonist.get('DSG_workflow_checkpoint_source_name')
                    and not antagonist.get('DSG_obsolete_hidden')):
                antagonist.hide_set(True)
                antagonist.hide_viewport = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        from .ios_guided_selection import activate_circle
        activate_circle(context)
        self.report({'INFO'}, 'Paso 1: marca el diente con la selección circular. Paso 2: pulsa P para guardar.')
        return {'FINISHED'}


class DSG_OT_IOSCloseToothSocket(bpy.types.Operator):
    bl_idname = 'dsg.ios_close_tooth_socket'
    bl_label = 'Cerrar hueco hacia dentro'
    bl_description = 'Elimina la selección guardada, suaviza todo el borde y genera Grid Fill con centro hundido'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .ios_guided_selection import SAVED
        obj = context.active_object
        return (context.mode == 'EDIT_MESH' and editing(context)
                and (bool(obj.get(SAVED)) or obj.data.total_vert_sel > 0))

    def execute(self, context):
        from .. import guide_module as guide
        from .ios_guided_selection import save_current_selection
        obj = context.active_object
        if obj.data.total_vert_sel > 0:
            # Always close what is selected now, after the last correction.
            try:
                save_current_selection(obj)
            except (ValueError, RuntimeError) as exc:
                self.report({'ERROR'}, str(exc) + ' Corrige con AÑADIR/QUITAR y vuelve a intentarlo.')
                return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        backup = bm.copy()
        depth = context.scene.dsg_props.ios_socket_depth_mm
        try:
            from .ios_guided_selection import remove_saved
            remove_saved(bm)
            close_socket(bm, obj.matrix_world, depth)
        except (ValueError, RuntimeError) as exc:
            bpy.ops.object.mode_set(mode='OBJECT')
            backup.to_mesh(obj.data)
            obj.data.update()
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        else:
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.data.update()
        finally:
            backup.free()
        obj[SESSION] = False
        from .ios_guided_selection import SAVED
        obj[SAVED] = False
        obj['DSG_ios_socket_count'] = int(obj.get('DSG_ios_socket_count', 0)) + 1
        obj['DSG_ios_socket_last_depth_mm'] = depth
        # The socket Boolean is done after the retentive model (virtual
        # extraction step), so the root remnant is not shown before that.
        from . import ios_socket_boolean
        obj[ios_socket_boolean.PENDING] = True
        context.scene['DSG_ios_postextraction_confirmed'] = False
        guide._clear_model_topology_cache()
        guide._clear_retention_geometry_cache()
        guide._remove_retention_previews()
        guide._remove_retention_boundary()
        guide.safe_remove_by_name(guide.BLOCKOUT_NAME)
        guide.safe_remove_by_name(guide.COMBINED_NAME)
        self.report({'INFO'}, 'Diente eliminado y hueco cerrado hacia dentro. Continúa con el modelo retentivo.')
        return {'FINISHED'}


class DSG_OT_IOSCancelToothRemoval(bpy.types.Operator):
    bl_idname = 'dsg.ios_cancel_tooth_removal'
    bl_label = 'Cancelar edición del diente'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return editing(context)

    def execute(self, context):
        from .. import guide_module as guide
        obj = context.active_object
        backup = obj.get(BACKUP)
        if backup is None:
            self.report({'ERROR'}, 'No existe una copia previa de esta edición.')
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        discarded = obj.data
        obj.data = backup
        del obj[BACKUP]
        if discarded.users == 0:
            bpy.data.meshes.remove(discarded)
        obj[SESSION] = False
        from .ios_guided_selection import SAVED
        obj[SAVED] = False
        guide._clear_model_topology_cache()
        from .ios_skip_removal import SKIPPED
        obj[SKIPPED] = bool(obj.get('DSG_ios_edit_previous_skip'))
        return {'FINISHED'}


class DSG_OT_IOSRetrySocketBoolean(bpy.types.Operator):
    bl_idname = 'dsg.ios_retry_socket_boolean'
    bl_label = 'Reintentar booleana después del cierre'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .. import core
        obj = model(context)
        return (context.mode == 'OBJECT' and core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE
                and obj is not None and ios_boolean_prepared(obj))

    def execute(self, context):
        from . import ios_socket_boolean
        from .. import guide_module as guide
        obj = model(context)
        try:
            ios_socket_boolean.apply(context, obj)
        except (ValueError, RuntimeError) as exc:
            obj[ios_socket_boolean.PENDING] = True
            context.scene['DSG_ios_postextraction_confirmed'] = False
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        guide._clear_model_topology_cache()
        guide._clear_retention_geometry_cache()
        return {'FINISHED'}


def draw(layout, context):
    box = layout.box()
    box.label(text='Eliminar diente del IOS', icon='EDITMODE_HLT')
    from .ios_skip_removal import SKIPPED
    obj = model(context)
    if obj is not None and obj.get(SKIPPED) and not editing(context):
        box.label(text='Eliminación manual omitida', icon='CHECKMARK')
        return
    if editing(context):
        from .ios_guided_selection import SAVED
        from .. import core
        saved = bool(context.active_object.get(SAVED))
        if context.mode != 'EDIT_MESH':
            box.operator('dsg.ios_circle_selection', text='VOLVER A EDICIÓN (C)', icon='EDITMODE_HLT')
            box.operator('dsg.ios_cancel_tooth_removal', text='CANCELAR Y RESTAURAR', icon='LOOP_BACK')
            box.operator('dsg.ios_skip_tooth_removal', text='SIGUIENTE', icon='FORWARD')
            core.set_status_bar(context, 'Selección pausada. Vuelve a Edición para guardar o cerrar el hueco.')
            return
        from .ios_guided_selection import circle_mode
        count = context.active_object.data.total_vert_sel
        core.set_status_bar(context, 'Pasa el círculo las veces que necesites (AÑADIR suma, QUITAR corrige). P revisa el borde.')
        mode = circle_mode(context)
        row = box.row(align=True)
        add = row.operator('dsg.ios_selection_mode', text='AÑADIR', icon='ADD', depress=mode == 'ADD')
        add.mode = 'ADD'
        sub = row.operator('dsg.ios_selection_mode', text='QUITAR', icon='REMOVE', depress=mode == 'SUB')
        sub.mode = 'SUB'
        box.label(text=f'{count} vértices seleccionados' if count else 'Nada seleccionado todavía', icon='VERTEXSEL')
        if saved or count:
            box.prop(context.scene.dsg_props, 'ios_socket_depth_mm', text='Profundidad mm')
            box.operator('dsg.ios_close_tooth_socket', text='2 · CERRAR HUECO HACIA DENTRO', icon='MESH_GRID')
        box.operator('dsg.ios_clear_selection', text='Empezar selección de nuevo', icon='X')
        box.operator('dsg.ios_cancel_tooth_removal', text='CANCELAR Y RESTAURAR', icon='LOOP_BACK')
        box.operator('dsg.ios_skip_tooth_removal', text='SIGUIENTE', icon='FORWARD')
    else:
        box.operator('dsg.ios_begin_tooth_removal', text='1 · SELECCIONAR DIENTE (C)', icon='EDITMODE_HLT')
        box.operator('dsg.ios_skip_tooth_removal', text='SIGUIENTE', icon='FORWARD')


from .ios_guided_selection import CLASSES as _GUIDED_CLASSES
from .ios_skip_removal import CLASSES as _SKIP_CLASSES
from .ios_socket_boolean import prepared as ios_boolean_prepared

CLASSES = [*_GUIDED_CLASSES, *_SKIP_CLASSES, DSG_OT_IOSBeginToothRemoval, DSG_OT_IOSCloseToothSocket, DSG_OT_IOSCancelToothRemoval, DSG_OT_IOSRetrySocketBoolean]
