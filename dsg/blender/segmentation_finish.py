"""One optional, one-shot anatomy-finishing action in segmentation review."""
import json

import bmesh
import bpy

DONE = 'DSG_segmentation_finish_done'
SUMMARY = 'DSG_segmentation_finish_summary'
METHOD = 'DSG_segmentation_finish_method'
STATE = {}
REVIEW_STEPS = {'IMMEDIATE_FDI_REVIEW', 'SIMPLE_REVIEW'}


def targets(context):
    from .. import cbct_dental_module as dental
    teeth = dental.dentition_objects(context)
    if teeth:
        return [obj for obj in teeth if len(obj.data.polygons) > 0]
    scene = context.scene
    return [obj for key in ('DSG_simple_upper_object', 'DSG_simple_lower_object')
            if (obj := scene.objects.get(str(scene.get(key, '')))) is not None
            and obj.type == 'MESH' and len(obj.data.polygons) > 0]


def in_scope(context):
    from .. import core, dicom_module
    return (core.stage_is(context, core.STAGE_DICOM)
            and str(context.scene.get(core.ROUTE_STEP_KEY, '')) in REVIEW_STEPS
            and not dicom_module.semantic_workflow_busy() and bool(targets(context)))


def done(context):
    if not context.scene.get(DONE):
        return False
    # An older visual-only finish must remain upgradeable after installing this fix.
    arches = targets(context)
    if arches and all(bool(obj.get('DSG_simple_route')) for obj in arches):
        return context.scene.get(METHOD) == 'ORGANIC_ARCHES'
    return True


def reset(scene):
    scene[DONE] = False
    scene.pop(SUMMARY, None)
    scene.pop(METHOD, None)


def closed(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return bool(bm.faces) and all(edge.is_manifold for edge in bm.edges)
    finally:
        bm.free()


def rollback(job=None):
    from .. import cbct_post_smoothing as post
    state = STATE.copy()
    STATE.clear()
    for row in state.get('objects', []):
        obj = row['object']
        try:
            # Discard our staged result without overwriting a later manual edit.
            expected = row.get('staged', obj.data)
            if obj.data != expected:
                if row['reference'] != obj.data:
                    obj[post.ORIGINAL_MESH] = row['reference']
                continue
            if row.get('staged_hash') and post.mesh_hash(obj.data) != row['staged_hash']:
                if row['reference'] != obj.data:
                    obj[post.ORIGINAL_MESH] = row['reference']
                continue
            obj.data = row['data']
            for key in list(obj.keys()):
                if key not in row['properties']:
                    del obj[key]
            for key, value in row['properties'].items():
                obj[key] = value
        except (ReferenceError, RuntimeError):
            continue
    scene = state.get('scene')
    if scene is not None:
        try:
            scene[DONE] = False
            scene[SUMMARY] = 'Mejora no aplicada · se conservan las mallas anteriores'
        except ReferenceError:
            pass


def sync_simple_composite(scene):
    """Refresh the visible alignment surface while retaining its raw ICP reference."""
    import numpy as np
    from .. import cbct_post_smoothing as post
    arches = [scene.objects.get(str(scene.get(key, ''))) for key in
              ('DSG_simple_upper_object', 'DSG_simple_lower_object')]
    composite = scene.objects.get(str(scene.get('DSG_simple_alignment_object', '')))
    if composite is None or any(obj is None for obj in arches):
        return False
    signature = json.dumps([(post.mesh_hash(obj.data),
                             [list(row) for row in composite.matrix_world.inverted() @ obj.matrix_world])
                            for obj in arches])
    if (composite.get('DSG_simple_finish_sources') == signature
            and composite.get(post.CACHED_MESH) == composite.data):
        return False
    vertices, faces = [], []
    offset = 0
    for obj in arches:
        v, f = post.mesh_arrays(obj.data)
        transform = np.asarray(composite.matrix_world.inverted() @ obj.matrix_world)
        vertices.append(v @ transform[:3, :3].T + transform[:3, 3])
        faces.append(f + offset)
        offset += len(v)
    v = np.concatenate(vertices).astype(np.float32)
    f = np.concatenate(faces).astype(np.int32)
    mesh = bpy.data.meshes.new(composite.name + '_Finished')
    try:
        mesh.vertices.add(len(v)); mesh.vertices.foreach_set('co', v.ravel())
        mesh.loops.add(f.size); mesh.loops.foreach_set('vertex_index', f.ravel())
        mesh.polygons.add(len(f))
        mesh.polygons.foreach_set('loop_start', np.arange(0, f.size, 3, dtype=np.int32))
        mesh.polygons.foreach_set('loop_total', np.full(len(f), 3, dtype=np.int32))
        mesh.polygons.foreach_set('use_smooth', np.ones(len(f), dtype=np.bool_))
        for material in composite.data.materials:
            mesh.materials.append(material)
        mesh.update(calc_edges=True)
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    original = post.source_mesh(composite)
    original.use_fake_user = True
    composite[post.ORIGINAL_MESH] = original
    composite[post.CACHED_MESH] = mesh
    composite[post.SOURCE_HASH] = post.mesh_hash(original)
    composite['DSG_simple_finish_sources'] = signature
    composite.data = mesh
    return True


def complete(job, result):
    from .. import cbct_post_smoothing as post
    scene = STATE['scene']
    accepted = sum(row.get('status') == 'READY' for row in result.get('teeth', []))
    if not accepted:
        reasons = [str(row.get('fallback_reason', 'Sin cambios')) for row in result.get('teeth', [])]
        raise RuntimeError('No se pudo mejorar ninguna superficie: ' + '; '.join(reasons)[:220])
    hashes = {}
    for index, row in enumerate(STATE['objects']):
        obj = row['object']
        raw = row['reference']
        raw.use_fake_user = True
        obj[post.ORIGINAL_MESH] = raw
        obj[post.SOURCE_HASH] = post.mesh_hash(raw)
        hashes[str(int(obj.get('DSG_universal_label', 0)) or index + 1)] = post.mesh_hash(raw)
    scene['DSG_post_smooth_cache_sources'] = json.dumps(hashes)
    sync_simple_composite(scene)
    scene[DONE] = True
    scene[METHOD] = str(result.get('mode', 'VISUAL'))
    scene[SUMMARY] = f'Mejora terminada · {accepted} superficies acabadas · originales conservados'
    STATE.clear()


def start(context):
    from .. import cbct_dental_module as dental, cbct_post_smoothing as post, dicom_module
    objects = targets(context)
    if not in_scope(context) or done(context) or post.busy():
        raise RuntimeError('La mejora solo se aplica una vez en la revisión de segmentación.')
    if any(obj.mode != 'OBJECT' for obj in objects):
        raise RuntimeError('Sal del modo Edición antes de mejorar los dientes.')
    previous_active = context.view_layer.objects.active
    STATE.update(scene=context.scene, objects=[])
    try:
        for obj in objects:
            obj.data.use_fake_user = True
            STATE['objects'].append({'object': obj, 'data': obj.data,
                                     'reference': post.source_mesh(obj),
                                     'properties': {key: obj[key] for key in obj.keys()}})
        labels = (dicom_module.get_cached_semantic_cbct_labels(model_kind='universal', require_current_source=True)
                  if dicom_module.RUNTIME.is_loaded() else None)
        # With the model's label map every tooth is rebuilt from it (organic surface,
        # shared contacts); refine + remesh + visual smoothing remain the fallback.
        # Universal tooth IDs are meaningful only for individual segmented teeth.
        # Simple arches are composite bone/teeth surfaces, never labels 1 and 2.
        organic = labels is not None and all(
            bool(obj.get('DSG_tooth_instance')) and int(obj.get('DSG_universal_label', 0)) > 0
            for obj in objects)
        simple_arches = all(
            bool(obj.get('DSG_simple_route')) and obj.get('DSG_simple_arch') in ('UPPER', 'LOWER')
            for obj in objects)
        if simple_arches and labels is None:
            raise RuntimeError('Falta la máscara original de las arcadas. Vuelve a segmentar el CBCT para aplicar la reconstrucción ITK.')
        organic_arches = simple_arches and labels is not None
        for row in STATE['objects']:
            obj = row['object']
            context.view_layer.objects.active = obj
            if organic or organic_arches:
                if organic_arches:
                    # Upgrade from the immutable CBCT surface, never from a prior finish.
                    obj.data = row['reference']
                dental._forget_smoothing_cache(obj)
                row['staged'] = obj.data
                row['staged_hash'] = post.mesh_hash(obj.data)
                continue
            if labels is not None and bool(obj.get('DSG_tooth_instance')):
                preview = str(obj.get('DSG_geometry_resolution', '')) == 'FDI_PREVIEW'
                try:
                    bpy.ops.dsg.cbct_improve_geometry()
                except RuntimeError:
                    pass  # Rejected refinements retain their preceding geometry.
                if preview and str(obj.get('DSG_geometry_resolution', '')) != 'FDI_PREVIEW':
                    row['reference'] = obj.data
            if not closed(obj):
                spacing = obj.get('DSG_cbct_spacing_zyx_mm', (.2, .2, .2))
                voxel = max(.05, min(.2, min(float(value) for value in spacing) * .5))
                dental.voxel_remesh_object(context, obj, voxel)
                if not closed(obj):
                    raise RuntimeError('La reparación de malla no produjo una superficie cerrada.')
            dental._forget_smoothing_cache(obj)
            row['staged'] = obj.data
            row['staged_hash'] = post.mesh_hash(obj.data)
        post.start(context, 'ORGANIC' if organic else 'ORGANIC_ARCHES' if organic_arches else 'VISUAL', objects_override=objects)
        post._JOB.update(on_complete=complete, on_cancel=rollback, on_failure=rollback,
                         scope_valid=lambda: in_scope(bpy.context), history_label='Mejorar dientes')
    except (ValueError, RuntimeError, OSError):
        rollback()
        raise
    finally:
        context.view_layer.objects.active = previous_active


def cancel_before_alignment():
    from .. import cbct_post_smoothing as post
    if STATE:
        post.cancel()


class DSG_OT_FinishSegmentedTeeth(bpy.types.Operator):
    bl_idname = 'dsg.finish_segmented_teeth'
    bl_label = 'Mejorar dientes'
    bl_description = 'Refinado disponible, reparación si hace falta y acabado automático; conserva la referencia CBCT original'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .. import cbct_post_smoothing as post
        return (context.mode == 'OBJECT' and in_scope(context)
                and not done(context) and (bool(STATE) or not post.busy()))

    def execute(self, context):
        from .. import cbct_post_smoothing as post
        if STATE:
            post.cancel()
            return {'FINISHED'}
        try:
            start(context)
        except (ValueError, RuntimeError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout, context):
    if not in_scope(context):
        return
    if done(context):
        layout.label(text=str(context.scene.get(SUMMARY, 'Mejora aplicada')), icon='CHECKMARK')
        return
    if context.scene.get(SUMMARY):
        layout.label(text=str(context.scene[SUMMARY]), icon='INFO')
    from .. import cbct_post_smoothing as post
    if str(context.scene.get(post.STATUS, '')).startswith('Suavizado no aplicado:'):
        layout.label(text=str(context.scene[post.STATUS])[:180], icon='ERROR')
    layout.operator('dsg.finish_segmented_teeth',
                    text='CANCELAR MEJORA' if STATE else 'MEJORAR DIENTES', icon='MOD_SMOOTH')


CLASSES = (DSG_OT_FinishSegmentedTeeth,)
