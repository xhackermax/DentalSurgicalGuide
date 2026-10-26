"""Live retention and live local relief on the retentive model (blockout).

Retention
    The blockout is the IOS with every blocked vertex pushed along the
    insertion axis by ``hit - retention`` (``hit`` = axial distance to the
    surface that blocks it, stored per vertex when the model is calculated),
    filled continuously (see ``blockout_shift``) so no pits or holes appear.
    Moving the retention slider therefore only re-evaluates that field with
    NumPy: the viewport updates while dragging, no new rays are cast, and
    local relief edits (added on top) are preserved.

Local relief
    In Edit Mode on the blockout, the current selection is shown already
    relieved by the slider amount, always outward (never into the model) and
    with a smooth three-ring fade, so it deforms the surface without holes.
    Changing the selection or the slider updates it live; the preview is
    non-cumulative.
    PREPARAR MODELO RETENTIVO, or leaving Edit Mode, fixes it.

In both cases the seating audit (a few seconds) runs once, shortly after the
user stops changing things, instead of after every step.
"""
import bpy
import bmesh
import numpy as np
from mathutils import Vector

from .blockout_field import blockout_shift

POLL_SECONDS = 0.2
AUDIT_DELAY_SECONDS = 1.0
RELIEF_RINGS = (1.0, 0.75, 0.40, 0.12)  # selection, then 3 fading rings
FACING_FULL = 0.30  # |normal . axis| from which the full relief applies

STATE = {
    'object': '',          # blockout name owning the preview
    'base': {},            # vertex index -> committed coordinate
    'expected': {},        # vertex index -> previewed coordinate
    'signature': None,     # (selected count, amount)
    'retention_pending': False,
    'editing': False,
}


def _guide():
    from .. import guide_module
    return guide_module


def blockout():
    obj = bpy.data.objects.get(_guide().BLOCKOUT_NAME)
    return obj if obj is not None and obj.type == 'MESH' else None


def axis_local(obj):
    g = _guide()
    values = obj.get(g.BLOCKOUT_AXIS_WORLD_KEY, obj.get('DSG_axis'))
    if values is None:
        return None
    axis = Vector(tuple(values))
    if axis.length <= 1e-10:
        return None
    axis = obj.matrix_world.inverted().to_3x3() @ axis.normalized()
    return axis.normalized() if axis.length > 1e-10 else None


def editing(context, obj=None):
    obj = obj or blockout()
    return obj is not None and context.mode == 'EDIT_MESH' and context.edit_object == obj


# ---------------------------------------------------------------- retention
def supports_live_retention(obj):
    return obj is not None and obj.data.attributes.get(_guide().BLOCKOUT_HIT_ATTRIBUTE) is not None


def apply_retention(context, retention):
    """Re-evaluate the blockout for a new retention value; False if not possible."""
    obj = blockout()
    if not supports_live_retention(obj):
        return False
    if editing(context, obj):
        STATE['retention_pending'] = True  # applied when Edit Mode ends
        return True
    axis = axis_local(obj)
    if axis is None:
        return False
    mesh = obj.data
    count = len(mesh.vertices)
    hits = np.empty(count, dtype=np.float32)
    mesh.attributes[_guide().BLOCKOUT_HIT_ATTRIBUTE].data.foreach_get('value', hits)
    old = float(obj.get('DSG_relief_mm', 0.0))
    new = max(0.0, float(retention))
    if abs(new - old) < 1e-7:
        return True
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get('vertices', edges)
    limits = dict(min_hit=float(obj.get('DSG_min_hit_mm', 0.0)), max_hit=float(obj.get('DSG_max_hit_mm', 0.0)))
    shift = blockout_shift(hits, new, edges, **limits) - blockout_shift(hits, old, edges, **limits)
    co = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3) + shift[:, None].astype(np.float32) * np.array(axis, dtype=np.float32)
    mesh.vertices.foreach_set('co', co.ravel())
    mesh.update()
    obj['DSG_relief_mm'] = new
    obj['DSG_seating_validation_status'] = 'PENDING'
    schedule_audit()
    return True


def on_retention_changed(props, context):
    apply_retention(context, props.blockout_relief)


# ------------------------------------------------------------- local relief
def _restore(bm):
    """Put back the committed coordinates of the previous preview.

    A vertex that is no longer where the preview left it (undo, manual edit)
    keeps its current position: the preview never overrides another change.
    """
    for index, co in STATE['base'].items():
        if index < len(bm.verts):
            vert = bm.verts[index]
            expected = STATE['expected'].get(index)
            if expected is not None and (vert.co - expected).length < 1e-6:
                vert.co = co
    STATE['base'], STATE['expected'] = {}, {}


def preview(context, force=False):
    """Show the selected relief live; returns the number of vertices moved."""
    obj = blockout()
    if not editing(context, obj):
        return 0
    amount = float(context.scene.dsg_props.blockout_local_relief_mm)
    signature = (int(obj.data.total_vert_sel), round(amount, 6))
    if not force and STATE['object'] == obj.name and signature == STATE['signature']:
        return len(STATE['base'])
    axis = axis_local(obj)
    if axis is None:
        return 0
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    if STATE['object'] == obj.name:
        _restore(bm)
    selected = [vert for vert in bm.verts if vert.select]
    weights = {vert.index: RELIEF_RINGS[0] for vert in selected}
    frontier = selected
    for weight in RELIEF_RINGS[1:]:
        nxt = []
        for vert in frontier:
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other.index not in weights:
                    weights[other.index] = weight
                    nxt.append(other)
        frontier = nxt
    for index, weight in weights.items():
        vert = bm.verts[index]
        # Always outward: along +axis where the surface faces the axis,
        # along -axis where it faces away, fading to zero on side walls.
        facing = max(-1.0, min(1.0, vert.normal.dot(axis) / FACING_FULL))
        STATE['base'][index] = vert.co.copy()
        vert.co = vert.co + axis * (amount * weight * facing)
        STATE['expected'][index] = vert.co.copy()
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    STATE.update(object=obj.name, signature=signature)
    return len(weights)


def commit(context, audit=True):
    """Keep the previewed relief as part of the blockout; returns vertices fixed."""
    obj = blockout()
    count = len(STATE['base'])
    amount = float(context.scene.dsg_props.blockout_local_relief_mm)
    STATE.update(base={}, expected={}, signature=None)
    if obj is not None and count:
        obj['DSG_local_relief_last_mm'] = amount
        obj['DSG_local_relief_last_vertices'] = int(count)
        obj['DSG_local_relief_edits'] = int(obj.get('DSG_local_relief_edits', 0)) + 1
        obj['DSG_seating_validation_status'] = 'PENDING'
        if audit:
            run_audit(context)
    return count


def on_local_relief_changed(props, context):
    preview(context, force=True)


# -------------------------------------------------------------- seating audit
def run_audit(context=None):
    context = context or bpy.context
    g = _guide()
    obj = blockout()
    if obj is None:
        return None
    if editing(context, obj):
        obj.update_from_editmode()
    props = context.scene.dsg_props
    requested = props.model_obj if g._valid_obj(getattr(props, 'model_obj', None)) else None
    try:
        model = g._resolve_blockout_source_model(context, requested)
    except Exception:
        return None
    if not g._valid_obj(model):
        return None
    report = g._validate_blockout_seating(context, model, obj)
    g._store_blockout_seating_report(props, obj, report)
    try:
        visual = g._ensure_blockout_zone_visual(context, model, obj, force_rebuild=True)
        if g._valid_obj(visual):
            g._set_obj_hidden(visual, False, selectable_when_visible=False)
    except Exception as exc:
        print(f'[DSG] Could not refresh blockout review overlay: {exc}')
    return report


def _audit_timer():
    if not editing(bpy.context):
        run_audit(bpy.context)
    return None


def schedule_audit():
    """(Re)start the countdown: the audit runs once the user stops changing."""
    if bpy.app.timers.is_registered(_audit_timer):
        bpy.app.timers.unregister(_audit_timer)
    bpy.app.timers.register(_audit_timer, first_interval=AUDIT_DELAY_SECONDS)


# ------------------------------------------------------------------- polling
def _poll():
    try:
        _step()
    except Exception as exc:  # the timer must survive a bad frame
        print(f'[DSG] live relief: {exc}')
    return POLL_SECONDS


def _step():
    context = bpy.context
    if getattr(context, 'scene', None) is None or not hasattr(context.scene, 'dsg_props'):
        return
    obj = blockout()
    now_editing = editing(context, obj)
    if now_editing:
        preview(context)
    elif STATE['editing']:
        # Edit Mode ended: what the user saw is what stays.
        pending = STATE['retention_pending']
        STATE['retention_pending'] = False
        fixed = commit(context, audit=False)
        if pending:
            apply_retention(context, context.scene.dsg_props.blockout_relief)
        elif fixed:
            schedule_audit()
    STATE['editing'] = now_editing


def status_text():
    count = len(STATE['base'])
    return f'Alivio en vivo: {count} vértices' if count else ''


def register():
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=POLL_SECONDS, persistent=True)


def unregister():
    for timer in (_poll, _audit_timer):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
