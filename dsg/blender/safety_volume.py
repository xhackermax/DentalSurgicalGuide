"""Hidden full-height safety cylinders and planning collision guards."""
import json
import time

import bpy
import numpy as np
from bpy.app.handlers import persistent
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .cylinder_contact import intersects

STATE = {'busy': False, 'poses': {}, 'checked': {}, 'pending': {}, 'pending_since': 0.}
QUIET_SECONDS = .15
_GEOMETRY = {}  # obstacle name -> (mesh session uid, local vertices, triangles, local BVH)
PREFIX = 'DSG_HiddenSafety_'


def visible(context, props, implant):
    from .. import guide_module as g
    if not g.is_valid_implant_obj(implant):
        return None
    volume = sync(context, props, implant)
    name = g._implant_safety_halo_name(implant)
    halo = bpy.data.objects.get(name)
    radius = float(volume['radius_mm'])
    if halo is None:
        halo = bpy.data.objects.new(name, g.make_cylinder_mesh(name+'_Mesh', radius, 2.0, verts=64))
        g.link_object(context, halo)
    elif abs(halo.get('DSG_safety_envelope_height_mm', -1)-2.0) > 1e-5 or abs(halo.get('DSG_safety_envelope_radius_mm', -1)-radius) > 1e-5:
        g._replace_mesh_data_preserve_object(halo, g.make_cylinder_mesh(name+'_Mesh', radius, 2.0, verts=64))
    matrix = g._matrix_along_local_z(g.get_implant_platform_center_world(props, implant), g.get_implant_axis_world(props, implant))
    halo.parent = implant
    halo.matrix_parent_inverse = implant.matrix_world.inverted_safe()
    halo.matrix_world = matrix
    halo.hide_render, halo.hide_select = True, True
    halo.hide_viewport = False
    halo.hide_set(False)
    halo.display_type = 'WIRE'
    halo.show_in_front = True
    halo.color = (.10,.55,1.,1.)
    g.register_dsg_object(halo, g.ROLE_IMPLANT, halo.name, {
        'DSG_implant_safety_halo': True, 'DSG_implant_name': implant.name,
        'DSG_safety_margin_mm': max(g.INTERIMPLANT_SAFETY_MARGIN_PER_IMPLANT_MM, float(props.implant_tooth_clearance)),
        'DSG_tooth_clearance_margin_mm': float(props.implant_tooth_clearance),
        'DSG_min_interimplant_clearance_mm': g.INTERIMPLANT_MIN_CLEARANCE_MM,
        'DSG_safety_envelope_radius_mm': radius, 'DSG_safety_envelope_height_mm': 2.0,
        'DSG_safety_envelope_longitudinal': False, 'DSG_safety_visual_only': True,
        'DSG_hidden_safety_volume_name': volume.name})
    return halo


def sync(context, props, implant):
    from .. import guide_module as g
    margin = max(g.INTERIMPLANT_SAFETY_MARGIN_PER_IMPLANT_MM, float(props.implant_tooth_clearance))
    radius = g.get_implant_nominal_diameter_world(props, implant)*.5 + margin
    height = g.get_implant_length_world(props, implant) + 2*margin
    name = PREFIX+implant.name
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, g.make_cylinder_mesh(name+'_Mesh', radius, height, verts=64))
        g.link_object(context, obj)
    elif abs(obj.get('radius_mm', -1)-radius) > 1e-5 or abs(obj.get('height_mm', -1)-height) > 1e-5:
        g._replace_mesh_data_preserve_object(obj, g.make_cylinder_mesh(name+'_Mesh', radius, height, verts=64))
    matrix = g._matrix_along_local_z(g.get_implant_center_world(props, implant), g.get_implant_axis_world(props, implant))
    obj.parent = implant
    obj.matrix_parent_inverse = implant.matrix_world.inverted_safe()
    obj.matrix_world = matrix
    obj.hide_render = True
    obj.hide_select = True
    obj.hide_viewport = True
    obj.hide_set(True)
    obj['DSG_implant_safety_volume'] = True
    obj['DSG_implant_name'] = implant.name
    obj['radius_mm'], obj['height_mm'] = radius, height
    return obj


def obstacles(scene, implant,include_canals=True):
    from .. import core, cbct_dental_module as dental, dicom_module, guide_module as g
    excluded = set(core._immediate_extraction_fdis(scene)) if core.clinical_route(scene) == core.ROUTE_IMMEDIATE else set()
    teeth = [o for o in dental.dentition_objects() if int(o.get('DSG_fdi_number', 0)) not in excluded]
    others = [o for o in g.get_all_implant_objects(scene.dsg_props) if o != implant]
    from .protected_neighbors import canals, lower
    # The mandibular canal only matters for lower-arch implants.
    return teeth+others+(canals() if include_canals and lower(scene) else [])


def contacts(context, implant,nerve_margin_mm=None):
    props = context.scene.dsg_props
    volume = sync(context, props, implant)
    from .microscrew_safety import screws
    failures = mesh_contacts(context,volume,obstacles(context.scene,implant,include_canals=False)+screws())
    from . import nerve_safety
    failures += nerve_safety.failures(context,implant,nerve_margin_mm)
    from . import upper_cavity_safety
    failures += upper_cavity_safety.failures(context,implant)
    implant['DSG_safety_volume_contacts'] = json.dumps(failures)
    return failures


def _mesh_arrays(mesh):
    vertices = np.empty(len(mesh.vertices)*3, dtype=np.float64)
    mesh.vertices.foreach_get('co', vertices)
    vertices = vertices.reshape(-1, 3)
    mesh.calc_loop_triangles()
    triangles = np.empty(len(mesh.loop_triangles)*3, dtype=np.int64)
    mesh.loop_triangles.foreach_get('vertices', triangles)
    triangles = triangles.reshape(-1, 3)
    tree = BVHTree.FromPolygons(vertices.tolist(), triangles.tolist(), all_triangles=True)
    return vertices, triangles, tree


def _local_geometry(obj, depsgraph):
    """Obstacle geometry in its own local space, cached while the mesh is unchanged.

    Teeth, canals and other implants do not change between two checks; only
    the cylinder moves.  Converting every vertex with Python on each check
    (and rebuilding a BVH) cost ~1.4 s per implant movement.
    """
    if obj.modifiers:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            return _mesh_arrays(mesh)
        finally:
            evaluated.to_mesh_clear()
    key = obj.data.session_uid
    cached = _GEOMETRY.get(obj.name)
    if cached is not None and cached[0] == key:
        return cached[1:]
    vertices, triangles, tree = _mesh_arrays(obj.data)
    _GEOMETRY[obj.name] = (key, vertices, triangles, tree)
    return vertices, triangles, tree


def _inside(tree, origin, direction):
    """Ray parity: is ``origin`` inside the closed surface held by ``tree``?"""
    count = 0
    for _ in range(256):
        hit, _normal, _index, _distance = tree.ray_cast(origin, direction)
        if hit is None:
            return bool(count % 2)
        origin = hit+direction*1e-5
        count += 1
    raise ValueError('No se pudo verificar la contención del cilindro de seguridad.')


def mesh_contacts(context,volume,objects):
    inverse = volume.matrix_world.inverted_safe()
    radius, half_height = float(volume['radius_mm']), float(volume['height_mm'])/2
    centre = volume.matrix_world.translation.copy()
    direction = Vector((1,.371,.219)).normalized()
    failures = []
    depsgraph = context.evaluated_depsgraph_get()
    for obj in objects:
        to_volume = inverse @ obj.matrix_world
        bounds = np.asarray([tuple(to_volume @ Vector(c)) for c in obj.bound_box])
        lo, hi = bounds.min(axis=0), bounds.max(axis=0)
        if np.any(lo > [radius, radius, half_height]) or np.any(hi < [-radius,-radius,-half_height]):
            continue
        local, triangles, tree = _local_geometry(obj, depsgraph)
        if not len(triangles):
            continue
        matrix = np.array(to_volume, dtype=np.float64)
        vertices = local @ matrix[:3, :3].T + matrix[:3, 3]
        if intersects(vertices, triangles, radius, half_height):
            failures.append(obj.name)
            continue
        # Whole cylinder inside a closed obstacle: no triangle crosses it.
        to_local = obj.matrix_world.inverted_safe()
        if _inside(tree, to_local @ centre, (to_local.to_3x3() @ direction).normalized()):
            failures.append(obj.name)
    return failures


def gate(context, operator,nerve_margin_mm=None):
    from .. import guide_module as g
    # Commit/export must not trust live caches after edits in another step.
    from . import nerve_safety
    _GEOMETRY.clear()
    nerve_safety.clear()
    for implant in g.get_all_implant_objects(context.scene.dsg_props):
        try:
            collisions = contacts(context, implant,nerve_margin_mm)
        except (ValueError, RuntimeError) as exc:
            operator.report({'ERROR'}, 'No se pudo verificar el volumen de seguridad: '+str(exc))
            return False
        if collisions:
            from .nerve_safety import description
            from .upper_cavity_safety import description as upper_description
            operator.report({'ERROR'}, implant.name+': '+ '; '.join(upper_description(implant,name) if upper_description(implant,name)!=name else description(implant,name) for name in collisions))
            return False
    return True


def remember(implant):
    STATE['poses'][implant.name] = (implant.matrix_world.copy(),
                                   implant.parent.matrix_world.copy() if implant.parent else None)


@persistent
def update(scene, depsgraph):
    from .. import core, guide_module as g
    if STATE['busy'] or core.infer_stage(scene) != core.STAGE_GUIDE:
        return
    if scene.dsg_props.current_step != g.STEP_IMPLANT:
        return
    changed_geometry = False
    for item in depsgraph.updates:
        if item.is_updated_geometry:
            changed_geometry = True
            _GEOMETRY.pop(item.id.name, None)
            if isinstance(item.id, bpy.types.Mesh):
                for name, cached in tuple(_GEOMETRY.items()):
                    if cached[0] == item.id.session_uid:_GEOMETRY.pop(name,None)
    for implant in g.get_all_implant_objects(scene.dsg_props):
        signature = (tuple(map(tuple, implant.matrix_world)), implant.data.session_uid)
        if not changed_geometry and STATE['checked'].get(implant.name) == signature:
            continue
        STATE['checked'][implant.name] = signature
        STATE['pending'][implant.name] = scene.name
        STATE['pending_since'] = time.monotonic()
    if STATE['pending'] and not bpy.app.timers.is_registered(_audit_timer):
        bpy.app.timers.register(_audit_timer,first_interval=QUIET_SECONDS)


def _audit_timer():
    """Warn on a settled editing pose; never overwrite Blender's native R/G."""
    from .. import core, guide_module as g
    if STATE['busy']:
        return QUIET_SECONDS
    remaining = QUIET_SECONDS-(time.monotonic()-STATE['pending_since'])
    if remaining > 0:
        return remaining
    pending = dict(STATE['pending'])
    STATE['pending'].clear()
    STATE['busy'] = True
    try:
        context = bpy.context
        for name, scene_name in pending.items():
            implant = bpy.data.objects.get(name)
            if implant is None or context.scene.name != scene_name:
                continue
            if core.infer_stage(context.scene) != core.STAGE_GUIDE or context.scene.dsg_props.current_step != g.STEP_IMPLANT:
                continue
            try:
                collisions = contacts(context,implant)
            except (ValueError,RuntimeError) as exc:
                implant['DSG_safety_volume_contacts'] = json.dumps(['verificación pendiente'])
                core.set_status_bar(context,'Seguridad pendiente: '+str(exc))
                continue
            from . import safety_alerts
            safety_alerts.observe(context,implant,collisions)
            from .upper_cavity_safety import alerts as anatomical_alerts
            warnings=anatomical_alerts(implant)
            if collisions:
                core.set_status_bar(context,'Contacto de seguridad: '+', '.join(collisions)+'. Ajusta antes de confirmar.')
            elif warnings:
                core.set_status_bar(context,'Alerta anatómica: '+'; '.join(safety_alerts.contact_label(row['name'],implant.name) for row in warnings))
            else:
                remember(implant)
                core.set_status_bar(context,'Posición comprobada: sin contactos con el cilindro de seguridad.')
    finally:
        STATE['busy'] = False
    return QUIET_SECONDS if STATE['pending'] else None


@persistent
def load(_filepath):
    from . import nerve_safety
    nerve_safety.clear()
    from . import safety_alerts
    safety_alerts.clear()
    if bpy.app.timers.is_registered(_audit_timer):bpy.app.timers.unregister(_audit_timer)
    STATE['pending'].clear()
    STATE['poses'].clear()
    STATE['checked'].clear()
    _GEOMETRY.clear()
    STATE['busy'] = False


def register():
    from . import upper_cavity_safety
    upper_cavity_safety.register()
    from . import nerve_safety
    nerve_safety.register()
    from . import safety_alerts
    safety_alerts.register()
    if update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(update)
    if load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load)


def unregister():
    from . import upper_cavity_safety
    upper_cavity_safety.unregister()
    from . import nerve_safety
    nerve_safety.unregister()
    from . import safety_alerts
    safety_alerts.unregister()
    if bpy.app.timers.is_registered(_audit_timer):bpy.app.timers.unregister(_audit_timer)
    STATE['pending'].clear()
    while update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(update)
    while load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load)
    STATE['poses'].clear()
    STATE['checked'].clear()
    _GEOMETRY.clear()
