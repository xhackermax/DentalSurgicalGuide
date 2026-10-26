"""Immediate route, step 4: show the tooth, extract it virtually, then SIGUIENTE.

Order shown in the panel (only for the immediate route):
1. The CBCT tooth to extract is visible (protected_neighbors keeps it shown).
2. REALIZAR EXTRACCIÓN VIRTUAL: the tooth is subtracted from the CBCT bone,
   leaving the socket, and hidden.  The IOS socket Boolean is completed too if
   it was still pending.
3. SIGUIENTE: opens the neighbour selection and implant planning.
RESTAURAR DIENTE undoes it (bone mesh restored from its backup).
"""
import json
import time

import bpy

DONE = 'DSG_virtual_extraction_done_fdis'
CONFIRMED = 'DSG_virtual_extraction_confirmed'
BONE_BACKUP = 'DSG_virtual_extraction_bone_backup'
BONE_NAMES = 'DSG_virtual_extraction_bones_json'


def required(scene):
    from .. import core
    return core.clinical_route(scene) == core.ROUTE_IMMEDIATE


def targets(scene):
    from .ios_socket_boolean import targets as socket_targets
    return sorted({int(fdi) for fdi in socket_targets(scene) if int(fdi) > 0})


def done(scene):
    try:
        return {int(value) for value in json.loads(str(scene.get(DONE, '[]') or '[]'))}
    except (TypeError, ValueError):
        return set()


def performed(scene):
    return (not required(scene)) or (bool(targets(scene)) and set(targets(scene)) <= done(scene))


def confirmed(scene):
    return (not required(scene)) or (performed(scene) and bool(scene.get(CONFIRMED, False)))


def teeth(context, fdis):
    from .. import core
    return core._immediate_cbct_teeth(context, list(fdis))


def bones_for(scene, fdis):
    """Bone meshes that should receive the socket (plain bone and composite)."""
    groups = []
    if any(fdi < 30 for fdi in fdis):
        groups.append(([scene.get('DSG_immediate_upper_composite', ''), scene.get('DSG_maxilla_object', '')], 'Dental_DICOM_Maxilla'))
    if any(fdi >= 30 for fdi in fdis):
        groups.append(([scene.get('DSG_immediate_lower_composite', ''), scene.get('DSG_mandible_object', '')], 'Dental_DICOM_Mandible'))
    result = []
    for names, fallback in groups:
        found = [bpy.data.objects.get(str(name or '')) for name in names]
        found = [obj for obj in found if obj is not None and obj.type == 'MESH' and len(obj.data.polygons)]
        if not found:  # older scenes without the stored names
            obj = bpy.data.objects.get(fallback)
            found = [obj] if obj is not None and obj.type == 'MESH' and len(obj.data.polygons) else []
        result += [obj for obj in found if obj not in result]
    return result


def _closed(mesh):
    """Every edge shared by exactly two faces (vectorised; bone meshes are big)."""
    import numpy as np
    if not len(mesh.loops):
        return False
    edges = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get('edge_index', edges)
    return bool(np.all(np.bincount(edges, minlength=len(mesh.edges)) == 2))


def _carve_bone(context, bone, cutter):
    """MANIFOLD-only difference: fast, and skipped when the bone is not solid."""
    if not _closed(bone.data):
        return {'ok': False, 'reason': 'hueso no cerrado; se conserva el alvéolo de la segmentación'}
    modifier = bone.modifiers.new('DSG_VirtualExtraction', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.solver = 'MANIFOLD'
    modifier.object = cutter
    try:
        from .evaluated_visible import visible
        with visible(bone):  # hidden bones are not evaluated (no cut at all)
            context.view_layer.update()
            mesh = bpy.data.meshes.new_from_object(bone.evaluated_get(context.evaluated_depsgraph_get()))
    finally:
        bone.modifiers.remove(modifier)
    if not len(mesh.polygons) or not _closed(mesh):
        bpy.data.meshes.remove(mesh)
        return {'ok': False, 'reason': 'la booleana no dejó un hueso cerrado; se conserva el original'}
    if len(mesh.polygons) == len(bone.data.polygons) and len(mesh.vertices) == len(bone.data.vertices):
        # The segmentation already left the socket empty; keep the original.
        bpy.data.meshes.remove(mesh)
        return {'ok': True, 'unchanged': True}
    if bone.get(BONE_BACKUP) is None:
        bone[BONE_BACKUP] = bone.data.copy()
    previous = bone.data
    mesh.name = previous.name
    bone.data = mesh
    if previous.users == 0:
        bpy.data.meshes.remove(previous)
    return {'ok': True}


def _hide_tooth(tooth, fdi):
    previous = {'hide_viewport': tooth.hide_viewport, 'hide_render': tooth.hide_render, 'hide_select': tooth.hide_select}
    for attribute, value in previous.items():
        key = 'DSG_virtual_extraction_prev_' + attribute
        if key not in tooth:
            tooth[key] = bool(value)
    tooth['DSG_virtual_extraction'] = True
    tooth['DSG_virtual_extraction_fdi'] = int(fdi)
    tooth.hide_viewport = True
    tooth.hide_render = True
    tooth.hide_select = True
    try:
        tooth.hide_set(True)
    except RuntimeError:
        pass


def _show_tooth(tooth):
    tooth['DSG_virtual_extraction'] = False
    for attribute in ('hide_viewport', 'hide_render', 'hide_select'):
        tooth.pop('DSG_virtual_extraction_prev_' + attribute, None)
    tooth.hide_viewport = False
    tooth.hide_select = False
    try:
        tooth.hide_set(False)
    except RuntimeError:
        pass


class DSG_OT_PerformVirtualExtraction(bpy.types.Operator):
    bl_idname = 'dsg.perform_virtual_extraction'
    bl_label = 'REALIZAR OPERACIÓN BOOLEANA'
    bl_description = ('Resta el resto radicular (con la extensión coronal elegida) del IOS y del hueso: '
                      'crea el hueco donde irá el implante; reversible con Restaurar diente')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .. import core
        from . import ios_socket_boolean
        from .ios_tooth_edit import model
        scene = context.scene
        if not required(scene):
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        fdis = targets(scene)
        found = teeth(context, fdis)
        found_fdis = {int(obj.get('DSG_fdi_number', 0)) for obj in found}
        missing = [fdi for fdi in fdis if fdi not in found_fdis]
        if missing:
            self.report({'ERROR'}, 'Falta el diente CBCT FDI ' + ', '.join(map(str, missing)) + '.')
            return {'CANCELLED'}
        started = time.perf_counter()
        notes = []
        ios = model(context)
        if ios is not None and not ios_socket_boolean.ready(context, ios):
            try:
                ios_socket_boolean.apply(context, ios)
            except (ValueError, RuntimeError) as exc:
                # Without the IOS socket the step is not done: nothing is
                # hidden or marked, so the user can adjust the bar and retry.
                self.report({'ERROR'}, 'Booleana del IOS: ' + str(exc))
                return {'CANCELLED'}
        from .extraction_extension import NAME as PREVIEW
        preview = bpy.data.objects.get(PREVIEW)
        if preview is not None:
            mesh = preview.data
            bpy.data.objects.remove(preview, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bones = bones_for(scene, fdis)
        carved = []
        for tooth in found:
            cutter = None
            try:
                cutter, _inner = core._prepare_alveolar_cutter(context, tooth)
                for bone in bones:
                    result = _carve_bone(context, bone, cutter)
                    if result['ok']:
                        if not result.get('unchanged'):
                            carved.append(bone.name)
                    else:
                        notes.append(f"{bone.name}: {result['reason']}")
            except (ValueError, RuntimeError) as exc:
                notes.append(f"FDI {int(tooth.get('DSG_fdi_number', 0))}: {exc}")
            finally:
                core._remove_cutter(cutter)
            _hide_tooth(tooth, int(tooth.get('DSG_fdi_number', 0)))
        for bone in bones:
            bone.hide_viewport = False
            try:
                bone.hide_set(False)
            except RuntimeError:
                pass
        scene[DONE] = json.dumps(sorted(done(scene) | found_fdis))
        scene[BONE_NAMES] = json.dumps(sorted(set(carved)))
        scene[CONFIRMED] = False
        scene['DSG_immediate_extraction_prepared'] = True
        scene['DSG_immediate_extraction_tooth'] = found[0].name
        scene['DSG_immediate_extraction_fdi'] = int(fdis[0])
        scene['DSG_restoration_scenario'] = 'IMMEDIATE_EXTRACTION'
        elapsed = time.perf_counter() - started
        message = f"Extracción virtual FDI {', '.join(map(str, fdis))} realizada en {elapsed:.1f} s"
        if notes:
            self.report({'WARNING'}, message + ' · ' + ' · '.join(notes))
        else:
            self.report({'INFO'}, message + ' · alvéolo creado en el hueso')
        return {'FINISHED'}


class DSG_OT_ConfirmVirtualExtraction(bpy.types.Operator):
    bl_idname = 'dsg.confirm_virtual_extraction'
    bl_label = 'SIGUIENTE'
    bl_description = 'Pasa a elegir los dientes vecinos y planificar el implante'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if not performed(scene):
            self.report({'ERROR'}, 'Realiza primero la extracción virtual.')
            return {'CANCELLED'}
        scene[CONFIRMED] = True
        from .protected_neighbors import CONFIRMED as NEIGHBORS_CONFIRMED, EDITOR, sync
        scene[EDITOR] = True
        scene[NEIGHBORS_CONFIRMED] = False  # next: choose the neighbours
        sync(context)
        return {'FINISHED'}


class DSG_OT_UndoVirtualExtraction(bpy.types.Operator):
    bl_idname = 'dsg.undo_virtual_extraction'
    bl_label = 'Restaurar diente'
    bl_description = 'Devuelve el diente y el hueso al estado anterior a la extracción virtual'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for bone in bpy.data.objects:
            backup = bone.get(BONE_BACKUP) if bone.type == 'MESH' else None
            if backup is None:
                continue
            carved = bone.data
            bone.data = backup
            del bone[BONE_BACKUP]
            if carved.users == 0:
                bpy.data.meshes.remove(carved)
        for tooth in teeth(context, targets(scene)):
            _show_tooth(tooth)
        for key in (DONE, CONFIRMED, BONE_NAMES):
            scene.pop(key, None)
        scene['DSG_immediate_extraction_prepared'] = False
        scene['DSG_immediate_extraction_tooth'] = ''
        scene['DSG_immediate_extraction_fdi'] = 0
        self.report({'INFO'}, 'Diente restaurado')
        return {'FINISHED'}


def draw(layout, context):
    """Draw the sub-step; returns True once SIGUIENTE was pressed."""
    scene = context.scene
    if not required(scene):
        return True
    fdis = targets(scene)
    label = ', '.join(map(str, fdis)) or '-'
    if confirmed(scene):
        row = layout.row(align=True)
        row.label(text=f'Extracción virtual FDI {label} ✓', icon='CHECKMARK')
        return True
    from .. import core, ui_style
    from .ios_socket_boolean import ready as ios_ready
    box = layout.box()
    box.label(text=f'EXTRACCIÓN VIRTUAL · FDI {label}', icon='MOD_BOOLEAN')
    if not performed(scene):
        core.set_status_bar(context, f'Resto radicular FDI {label}: elige la extensión coronal y pulsa REALIZAR OPERACIÓN BOOLEANA.')
        box.label(text='El resto radicular se muestra en la vista 3D.', icon='HIDE_OFF')
        if not ios_ready(context):
            from .extraction_extension import draw as draw_extension
            draw_extension(box, context)
        action = ui_style.primary_action(box)
        action.operator('dsg.perform_virtual_extraction', text='REALIZAR OPERACIÓN BOOLEANA', icon='MOD_BOOLEAN')
        return False
    core.set_status_bar(context, 'Hueco del implante creado. Pulsa SIGUIENTE para elegir los dientes vecinos.')
    box.label(text='Hueco del implante creado · resto radicular oculto', icon='CHECKMARK')
    action = ui_style.primary_action(box)
    action.operator('dsg.confirm_virtual_extraction', text='SIGUIENTE', icon='FORWARD')
    return False


CLASSES = (DSG_OT_PerformVirtualExtraction, DSG_OT_ConfirmVirtualExtraction, DSG_OT_UndoVirtualExtraction)
