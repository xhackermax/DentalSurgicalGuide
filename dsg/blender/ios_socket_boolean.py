"""Apply the immediate CBCT-tooth difference only after a concave IOS closure."""
import json

import bpy

APPLIED = 'DSG_ios_socket_boolean_fdis_json'
PENDING = 'DSG_ios_socket_boolean_pending'
GENERATION = 'DSG_ios_socket_boolean_generation'
REVISION = 'DSG_ios_socket_extension_revision'
CURRENT_REVISION = 3
BASE_MESH = 'DSG_ios_extension_base_mesh'
BASE_GENERATION = 'DSG_ios_extension_base_generation'


def prepared(obj):
    from .ios_skip_removal import SKIPPED
    return bool(obj.get('DSG_ios_socket_count') or obj.get(SKIPPED))


def targets(scene):
    from .. import core
    return core._immediate_extraction_fdis(scene) or [core.target_fdi(scene)]


def applied(obj):
    if obj.get(REVISION,0) != CURRENT_REVISION:
        return set()
    if obj.get(GENERATION, -1) != obj.get('DSG_ios_socket_count', 0):
        return set()
    try:
        return {int(value) for value in json.loads(str(obj.get(APPLIED, '[]')))}
    except (ValueError, TypeError):
        return set()


def ready(context, obj=None):
    from .. import core
    from .ios_tooth_edit import model
    if core.clinical_route(context.scene) != core.ROUTE_IMMEDIATE:
        return True
    obj = obj if obj is not None else model(context)
    return (obj is not None and prepared(obj)
            and not bool(obj.get(PENDING)) and set(targets(context.scene)).issubset(applied(obj)))


def apply(context, obj):
    from .. import core
    from . import socket_reach
    if core.clinical_route(context.scene) != core.ROUTE_IMMEDIATE:
        return []
    if context.mode != 'OBJECT' or not prepared(obj):
        raise RuntimeError('Cierra primero el hueco del IOS hacia dentro antes de la booleana.')
    pending = [fdi for fdi in targets(context.scene) if fdi not in applied(obj)]
    if not pending:
        obj[PENDING] = False
        context.scene['DSG_ios_postextraction_confirmed'] = True
        return []
    teeth = core._immediate_cbct_teeth(context, pending)
    found = {int(tooth.get('DSG_fdi_number', 0)) for tooth in teeth}
    if found != set(pending):
        missing = ', '.join(str(fdi) for fdi in pending if fdi not in found)
        raise RuntimeError('Falta el diente CBCT FDI ' + missing + ' para la booleana del IOS.')
    topology = core._mesh_topology_counts(obj.data)
    if topology['boundary_edges'] or topology['non_manifold_edges']:
        raise RuntimeError('El hueco debe estar cerrado y manifold antes de la booleana.')
    context.view_layer.update()
    work = obj.copy()
    generation = int(obj.get('DSG_ios_socket_count',0))
    baseline = bpy.data.meshes.get(str(obj.get(BASE_MESH,''))) if obj.get(BASE_GENERATION,-1)==generation else None
    # Recompute from the closed IOS so reducing the slider also reduces the cut.
    work.data = (baseline if baseline is not None else obj.data).copy()
    work.name = '__DSG_IOS_SocketBoolean'
    context.scene.collection.objects.link(work)
    report = []
    trees = []
    try:
        for tooth in teeth:
            cutter = None
            try:
                cutter, inner_shells = core._prepare_alveolar_cutter(context, tooth)
                # A CBCT tooth that ends below the IOS surface would leave a
                # closed cavity (removed later as an island): open it.
                required = socket_reach.requirement(cutter,tooth,work)[0]
                selected = float(context.scene.dsg_props.extraction_extension_mm) if context.scene.get('DSG_extraction_extension_initialized') else min(10.,required)
                if not context.scene.get('DSG_extraction_extension_initialized'):
                    context.scene.dsg_props.extraction_extension_mm = selected
                if selected+.001 < required:
                    raise RuntimeError(f'Extensión insuficiente: {selected:.2f} mm; necesaria {required:.2f} mm. Ajusta la barra antes de aplicar.')
                extension = socket_reach.extend(cutter, tooth, work,extension_mm=selected)
                trees.append(socket_reach.cutter_tree(cutter))
                result = core._apply_alveolar_boolean(context, work, cutter)
            finally:
                core._remove_cutter(cutter)
            fdi = int(tooth.get('DSG_fdi_number', 0))
            report.append({'fdi': fdi, 'inner_shells_removed': inner_shells,
                           'socket_extension_mm': round(float(extension), 2),
                           'socket_extension_method': 'ROOT_CROSS_SECTION_EXTRUSION' if extension else 'SOURCE_ALREADY_REACHES_SURFACE', **result})
            if not result['ok']:
                raise RuntimeError(f'La booleana FDI {fdi} no produjo un sólido limpio; reintenta.')
        cleaned, cleanup = core._clean_postextraction_boolean_debris(work)
        topology = core._mesh_topology_counts(work.data)
        if not cleaned or topology['boundary_edges'] or topology['non_manifold_edges']:
            raise RuntimeError('La booleana no dejó un IOS manifold; se conserva el cierre cóncavo.')
        for tooth, item, tree in zip(teeth, report, trees):
            item['socket_opening'] = socket_reach.verify_opening(work, tooth, tree)
        if baseline is None:
            baseline = obj.data.copy()
            baseline.use_fake_user = True
            obj[BASE_MESH] = baseline.name
            obj[BASE_GENERATION] = generation
        previous = obj.data
        obj.data = work.data
        work.data = previous
        obj[APPLIED] = json.dumps(sorted(applied(obj) | found))
        obj[GENERATION] = int(obj.get('DSG_ios_socket_count',0))
        obj[REVISION] = CURRENT_REVISION
        obj['DSG_ios_socket_boolean_report'] = json.dumps(report, ensure_ascii=False)
        obj['DSG_postextraction_boolean_cleanup'] = json.dumps(cleanup, ensure_ascii=False)
        obj['DSG_ios_postextraction_state'] = 'BOOLEAN_APPLIED_AFTER_SOCKET' if obj.get('DSG_ios_socket_count') else 'BOOLEAN_APPLIED_MANUAL_REMOVAL_SKIPPED'
        obj[PENDING] = False
        context.scene['DSG_ios_postextraction_confirmed'] = True
        context.scene.dicp_props.icp_source_obj = obj
        obj.data.update()
        # The retentive model was built before the extraction: carve it too.
        try:
            carve_passive(context, sorted(found))
        except Exception as exc:  # the IOS result stays valid; surface the problem
            obj['DSG_passive_socket_error'] = str(exc)
            print(f'[DSG] Socket on the retentive model failed: {exc}')
    finally:
        core._remove_cutter(work)
    return report


PASSIVE_CARVED = 'DSG_socket_carved_fdis'


def carve_passive(context, fdis=None):
    """Subtract the extraction socket from the retentive model (DSG_PassiveCombined).

    The retentive model is built from the closed IOS *before* the virtual
    extraction, so without this the guide is fitted onto the extracted tooth.
    Uses the same alveolar cutter (with the chosen coronal extension) as the
    IOS Boolean.  Returns the list of FDI carved now, or raises RuntimeError.
    """
    from .. import core, guide_module as g
    from . import socket_reach
    passive = bpy.data.objects.get(g.COMBINED_NAME)
    if passive is None or passive.type != 'MESH':
        return []
    scene = context.scene
    fdis = list(fdis or targets(scene))
    try:
        done = {int(v) for v in json.loads(str(passive.get(PASSIVE_CARVED, '[]')))}
    except (ValueError, TypeError):
        done = set()
    pending = [fdi for fdi in fdis if fdi not in done]
    if not pending:
        return []
    teeth = core._immediate_cbct_teeth(context, pending)
    if not teeth:
        return []
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    work = passive.copy()
    work.data = passive.data.copy()
    work.name = '__DSG_Passive_SocketBoolean'
    scene.collection.objects.link(work)
    carved = []
    try:
        extension = float(scene.dsg_props.extraction_extension_mm)
        for tooth in teeth:
            cutter = None
            try:
                cutter, _inner = core._prepare_alveolar_cutter(context, tooth)
                socket_reach.extend(cutter, tooth, work, extension_mm=extension)
                result = core._apply_alveolar_boolean(context, work, cutter)
            finally:
                core._remove_cutter(cutter)
            if not result.get('ok'):
                raise RuntimeError('la booleana del alvéolo en el modelo retentivo no dio un sólido limpio')
            carved.append(int(tooth.get('DSG_fdi_number', 0)))
        cleaned, _cleanup = core._clean_postextraction_boolean_debris(work)
        topology = core._mesh_topology_counts(work.data)
        if not cleaned or topology['boundary_edges'] or topology['non_manifold_edges']:
            raise RuntimeError('el modelo retentivo no quedó manifold tras el alvéolo')
        # Written into the same mesh datablock: the step checkpoints share it,
        # so going back (e.g. to redo the final cut) keeps the socket.
        import bmesh
        bm = bmesh.new()
        try:
            bm.from_mesh(work.data)
            bm.to_mesh(passive.data)
        finally:
            bm.free()
        for other in bpy.data.objects:
            if other.type == 'MESH' and other.data == passive.data and other != passive:
                other[PASSIVE_CARVED] = json.dumps(sorted(done | set(carved)))
        passive[PASSIVE_CARVED] = json.dumps(sorted(done | set(carved)))
        # The socket is an expected workflow change, not a user edit of the
        # confirmed model: refresh the confirmation signature.
        try:
            if str(scene.get(g.WORKFLOW_PASSIVE_SIGNATURE_KEY, '') or ''):
                scene[g.WORKFLOW_PASSIVE_SIGNATURE_KEY] = g._workflow_object_signature(passive)
        except Exception:
            pass
        passive['DSG_socket_carved'] = True
        passive.data.update()
        return carved
    finally:
        core._remove_cutter(work)


def draw_closure(layout, context, obj):
    """Model step: the IOS only needs the hole closed; the Boolean comes later."""
    from .. import core
    if core.clinical_route(context.scene) != core.ROUTE_IMMEDIATE:
        return True
    if prepared(obj):
        layout.label(text='Hueco del IOS cerrado · la booleana se hará tras el modelo retentivo', icon='CHECKMARK')
        return True
    layout.label(text='Elimina el diente del IOS y cierra el hueco hacia dentro, o pulsa SIGUIENTE.', icon='INFO')
    return False


def draw_status(layout, context, obj):
    from .. import core
    if core.clinical_route(context.scene) != core.ROUTE_IMMEDIATE:
        return True
    from .extraction_extension import draw as draw_extension
    draw_extension(layout,context)
    if ready(context, obj):
        layout.label(text='IOS preparado · booleana aplicada · FDI ' + ', '.join(map(str, targets(context.scene))), icon='CHECKMARK')
        return True
    if prepared(obj):
        layout.label(text='Booleana del diente CBCT pendiente', icon='ERROR')
        layout.operator('dsg.ios_retry_socket_boolean', text='REINTENTAR BOOLEANA', icon='MOD_BOOLEAN')
    else:
        layout.label(text='Elimina el diente IOS y cierra el hueco hacia dentro.', icon='INFO')
    layout.label(text='Después se aplica la booleana; luego continúa la planificación.')
    return False
