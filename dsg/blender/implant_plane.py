"""Radiographic plane of an implant (MPR through its long axis).

Like the Z and Inclination planes of the DICOM review, the plane shows the
CBCT resliced on it, but it always contains the implant's long axis and
follows the implant while it is moved or tilted, so the whole surroundings
of the implant (bone, canal, sinus, neighbouring roots) are seen along it.

* Follows the implant through a CHILD_OF constraint (not a real child, so
  implant-children logic such as safety halos or export never sees it).
* Orientation around the axis: mesio-distal (tangent to the arch) or
  vestibulo-lingual (towards the arch centre).
* Coloured frame (blue / red / green) to tell the planes apart.
* Shown or hidden with one toggle; while shown, the MPR view hides the IOS.
"""
import json
import math

import bpy
from mathutils import Matrix, Vector

# Must NOT start with 'DSG_Implant' (that prefix identifies real implants).
PREFIX = 'DSG_AxisMPR_'
LEGACY_PREFIXES = ('DSG_InclinationPlane_', 'DSG_ImplantMPR_')
ROLE = 'DSG_implant_inclination_plane'
ORIENTATION = 'DSG_inclination_plane_orientation'   # 'MD' | 'VL'
BASE_ANGLE = 'DSG_implant_mpr_base_angle'
COLOR_KEY = 'DSG_inclination_plane_color'
HIDDEN_MODELS = 'DSG_inclination_hidden_models'
VISIBLE_KEY = 'DSG_inclination_planes_visible'
SIZE_MM = 40.0          # square field around the implant centre
FRAME_MM = 0.6
MAX_AXIS = 320
COLORS = {
    'BLUE': ('Azul', (0.15, 0.45, 1.0)),
    'RED': ('Rojo', (1.0, 0.18, 0.15)),
    'GREEN': ('Verde', (0.15, 0.85, 0.3)),
}
ORDER = ('BLUE', 'RED', 'GREEN')
STATE = {'poses': {}, 'pending': set()}


# ── selection / lookup ──────────────────────────────────────────────

def selected_implant(context):
    from .. import guide_module as g
    props = context.scene.dsg_props
    active = context.view_layer.objects.active
    if active is not None and g.is_valid_implant_obj(active):
        return active
    if active is not None:  # emergence control selected: its implant
        for child in active.children:
            if g.is_valid_implant_obj(child):
                return child
    implant = getattr(props, 'implant_obj', None)
    return implant if g.is_valid_implant_obj(implant) else None


def plane_for(implant):
    if implant is None:
        return None
    return bpy.data.objects.get(PREFIX + implant.name)


def planes(scene):
    return [obj for obj in scene.objects if obj.get(ROLE)]


def visible(scene):
    return bool(scene.get(VISIBLE_KEY, True))


def _remove(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def cleanup(scene):
    """Remove planes whose implant no longer exists, and the old flat ones."""
    for obj in list(planes(scene)):
        implant = bpy.data.objects.get(str(obj.get('DSG_inclination_plane_implant', '')))
        if implant is None or obj.name.startswith(LEGACY_PREFIXES):
            image = bpy.data.images.get(obj.name)
            _remove(obj)
            if image is not None and image.users == 0:
                bpy.data.images.remove(image)


# ── geometry ────────────────────────────────────────────────────────

def _mesh(name):
    """Image quad (material 0) inside a coloured frame (material 1), XY plane."""
    h = SIZE_MM / 2.0
    o = h + FRAME_MM
    verts = [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0),
             (-o, -o, 0), (o, -o, 0), (o, o, 0), (-o, o, 0)]
    faces = [(0, 1, 2, 3), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    uv = mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            x, y, _z = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv.data[loop_index].uv = ((x + h) / SIZE_MM, (y + h) / SIZE_MM)
    for index, polygon in enumerate(mesh.polygons):
        polygon.material_index = 0 if index == 0 else 1
    mesh.update()
    return mesh


def _frame_material(color_name=None):
    # Anatomical colours belong to structures, never to the radiographic frame.
    name = 'DSG_AxisMPR_Frame_Neutral'
    rgb = (0.32, 0.32, 0.32)
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*rgb, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    emission = nodes.get('FRAME_EMISSION')
    if emission is None:
        nodes.clear()
        output = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
        emission.name = 'FRAME_EMISSION'
        material.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    emission.inputs['Color'].default_value = (*rgb, 1.0)
    return material


def _arch_centre(context):
    model = getattr(context.scene.dsg_props, 'model_obj', None)
    if model is not None and model.type == 'MESH':
        corners = [model.matrix_world @ Vector(c) for c in model.bound_box]
        return sum(corners, Vector()) / 8.0
    return None


def _angle_about_axis(context, implant, orientation):
    """Rotation about the implant's local Z that makes the plane mesio-distal
    (tangent to the arch) or vestibulo-lingual (radial)."""
    centre = _arch_centre(context)
    if centre is None:
        return 0.0
    world = implant.matrix_world
    axis = (world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    radial = world.translation - centre
    radial -= axis * radial.dot(axis)
    if radial.length < 1e-6:
        return 0.0
    radial.normalize()
    direction = radial if orientation == 'VL' else axis.cross(radial).normalized()
    local = world.to_3x3().inverted() @ direction
    return math.atan2(local.y, local.x)


def _default_color(scene, implant):
    used = [p.get(COLOR_KEY) for p in planes(scene) if p.get('DSG_inclination_plane_implant') != implant.name]
    for name in ORDER:
        if name not in used:
            return name
    return ORDER[len(used) % len(ORDER)]


def _microscrew_basis(context, target, angle=0.0):
    """Rigid local plane whose Y axis contains the screw's persisted trajectory."""
    from .. import guide_module as g
    axis = g._microscrew_axis_world(target)
    centre = g._microscrew_center_world(target)
    x_axis = g._microscrew_x_hint_world(target, axis)
    x_axis = Matrix.Rotation(float(angle), 3, axis) @ x_axis
    normal = x_axis.cross(axis).normalized()
    world = Matrix((x_axis, axis, normal)).transposed().to_4x4()
    world.translation = centre
    # The CHILD_OF constraint follows translation/rotation, with scale disabled.
    rigid = target.matrix_world.to_quaternion().to_matrix().to_4x4()
    rigid.translation = target.matrix_world.translation
    return rigid.inverted_safe() @ world


def follow_target(scene, implant):
    """Keep the stable original identity while displaying its pending proposal."""
    if implant is None:
        return None
    for candidate in scene.objects:
        if (candidate.get('DSG_optimizer_preview')
                and str(candidate.get('DSG_optimizer_original', '')) == implant.name):
            return candidate
    return implant


def create(context, implant, orientation=None, color=None):
    legacy = [bpy.data.objects.get(prefix + implant.name) for prefix in LEGACY_PREFIXES]
    previous = plane_for(implant) or next((obj for obj in legacy if obj is not None), None)
    orientation = orientation or (previous.get(ORIENTATION) if previous else None) or 'MD'
    angle = float(previous.dsg_implant_mpr_angle) if previous is not None and orientation == previous.get(ORIENTATION, 'MD') else 0.0
    color = 'NEUTRAL'
    for old in [plane_for(implant), *legacy]:
        if old is not None:
            _remove(old)
    name = PREFIX + implant.name
    obj = bpy.data.objects.new(name, _mesh(name))
    collection = implant.users_collection[0] if implant.users_collection else context.scene.collection
    collection.objects.link(obj)
    obj.data.materials.append(bpy.data.materials.get(name) or bpy.data.materials.new(name))
    obj.data.materials.append(_frame_material(color))
    obj[ROLE] = True
    obj['DSG_preview_only'] = True
    obj['DSG_inclination_plane_implant'] = implant.name
    obj[ORIENTATION] = orientation
    obj[COLOR_KEY] = color
    obj.hide_render = True
    obj.hide_select = True
    constraint = obj.constraints.new('CHILD_OF')
    constraint.name = 'DSG_FollowImplant'
    constraint.target = follow_target(context.scene, implant)
    constraint.inverse_matrix = Matrix.Identity(4)
    constraint.set_inverse_pending = False
    constraint.use_scale_x = constraint.use_scale_y = constraint.use_scale_z = False
    # Plane local Y = implant long axis; local X = mesio-distal / bucco-lingual.
    from .. import guide_module as g
    microscrew = g._is_valid_mpr_microscrew(implant)
    obj['DSG_microscrew_mpr'] = microscrew
    base_angle = 0.0 if microscrew else _angle_about_axis(context, implant, orientation)
    obj[BASE_ANGLE] = base_angle
    obj.dsg_implant_mpr_angle = angle
    obj.matrix_basis = (_microscrew_basis(context, implant, angle) if microscrew else
                        Matrix.Rotation(base_angle + angle, 4, 'Z')
                        @ Matrix.Rotation(math.radians(90.0), 4, 'X'))
    context.view_layer.update()
    refresh(context, obj)
    return obj


def _angle_changed(obj, context):
    """Rotate only this section around the implant axis and queue its reslice."""
    if not obj.get(ROLE):
        return
    if BASE_ANGLE not in obj:
        obj[BASE_ANGLE] = math.atan2(obj.matrix_basis[1][0], obj.matrix_basis[0][0])
    angle = float(obj[BASE_ANGLE]) + float(obj.dsg_implant_mpr_angle)
    if obj.get('DSG_microscrew_mpr'):
        target = bpy.data.objects.get(str(obj.get('DSG_inclination_plane_implant', '')))
        if target is None:
            return
        obj.matrix_basis = _microscrew_basis(context, target, angle)
    else:
        obj.matrix_basis = (Matrix.Rotation(angle, 4, 'Z')
                            @ Matrix.Rotation(math.radians(90.0), 4, 'X'))
    STATE['pending'].add(obj.name)
    if not bpy.app.timers.is_registered(_refresh_pending):
        bpy.app.timers.register(_refresh_pending, first_interval=0.12)


def register_angle():
    if 'dsg_implant_mpr_angle' not in bpy.types.Object.bl_rna.properties:
        bpy.types.Object.dsg_implant_mpr_angle = bpy.props.FloatProperty(
            name='Inclinación MPR',subtype='ANGLE',unit='ROTATION',
            default=0.0,min=-math.pi,max=math.pi,precision=1,update=_angle_changed,
            description='Gira el corte alrededor del eje del implante seleccionado, sin mover el implante')
    for obj in planes(bpy.context.scene):
        if BASE_ANGLE not in obj:
            obj[BASE_ANGLE] = math.atan2(obj.matrix_basis[1][0], obj.matrix_basis[0][0])


def set_color(obj, color):
    obj.data.materials[1] = _frame_material()
    obj[COLOR_KEY] = 'NEUTRAL'


# ── radiographic image ──────────────────────────────────────────────

def _ensure_voxels(context):
    from .. import dicom_module as dicom
    if dicom.RUNTIME.is_loaded():
        return True
    from .. import guide_module as g
    ensure = getattr(g, '_ensure_dicom_voxels', None)
    if callable(ensure):
        try:
            ensure(context)
        except Exception:
            pass
    return dicom.RUNTIME.is_loaded()


def refresh(context, obj, max_axis=MAX_AXIS):
    """Reslice the CBCT on the plane (same sampling as the DICOM MPR planes)."""
    from .. import dicom_module as dicom
    import numpy as np
    if not _ensure_voxels(context):
        obj['DSG_implant_mpr_status'] = 'CBCT no cargado'
        return False
    root = bpy.data.objects.get(dicom.ROOT_NAME)
    if root is None:
        return False
    local = root.matrix_world.inverted_safe() @ obj.matrix_world
    axis_u = np.asarray((local[0][0], local[1][0], local[2][0]), dtype=np.float64)
    axis_v = np.asarray((local[0][1], local[1][1], local[2][1]), dtype=np.float64)
    scale_u = max(float(np.linalg.norm(axis_u)), 1e-8)
    scale_v = max(float(np.linalg.norm(axis_v)), 1e-8)
    axis_u /= scale_u
    axis_v = axis_v - axis_u * float(np.dot(axis_v, axis_u))
    axis_v /= max(float(np.linalg.norm(axis_v)), 1e-8)
    centre = np.asarray((local[0][3], local[1][3], local[2][3]), dtype=np.float64)
    width, height = SIZE_MM * scale_u, SIZE_MM * scale_v
    out_w, out_h = dicom._pose_output_shape(width, height, max_axis)
    values = dicom._oblique_slice(centre, axis_u, axis_v, width, height, out_w, out_h)
    props = context.scene.dicom_wizard_pro
    pixels = dicom.normalize_for_display(values, props.threshold_min_percent, props.threshold_max_percent)
    image = dicom._get_image(obj.name, out_w, out_h)
    dicom._set_image_pixels(image, pixels)
    material = dicom._get_plane_material(obj.name, image)
    if obj.data.materials[0] != material:
        obj.data.materials[0] = material
    STATE['poses'][obj.name] = _pose_key(obj)
    obj['DSG_implant_mpr_status'] = 'OK'
    return True


def _pose_key(obj):
    return tuple(round(value, 4) for row in obj.matrix_world for value in row)


def _refresh_pending():
    names, STATE['pending'] = set(STATE['pending']), set()
    context = bpy.context
    for name in names:
        obj = context.scene.objects.get(name)
        if obj is not None and obj.visible_get():
            try:
                refresh(context, obj)
            except Exception:
                pass
    return None


@bpy.app.handlers.persistent
def _follow(scene, _depsgraph=None):
    """Reslice when an implant moves (debounced)."""
    try:
        for obj in planes(scene):
            if not obj.get('DSG_microscrew_mpr'):
                source = scene.objects.get(str(obj.get('DSG_inclination_plane_implant', '')))
                target = follow_target(scene, source)
                constraint = obj.constraints.get('DSG_FollowImplant')
                if target is not None and constraint is not None and constraint.target != target:
                    constraint.target = target
                    STATE['poses'].pop(obj.name, None)
            if obj.get('DSG_microscrew_mpr') and not obj.hide_get():
                target = bpy.data.objects.get(str(obj.get('DSG_inclination_plane_implant', '')))
                from .. import guide_module as g
                if g._is_valid_mpr_microscrew(target):
                    # Updating a preview replaces its Object datablock. Blender clears
                    # CHILD_OF.target on deletion even when its name is reused.
                    constraint = obj.constraints.get('DSG_FollowImplant')
                    if constraint is not None and constraint.target != target:
                        constraint.target = target
                        STATE['poses'].pop(obj.name, None)
                    basis = _microscrew_basis(bpy.context, target, obj.dsg_implant_mpr_angle)
                    if any(abs(basis[r][c] - obj.matrix_basis[r][c]) > 1e-6
                           for r in range(4) for c in range(4)):
                        obj.matrix_basis = basis
            if obj.hide_get() or STATE['poses'].get(obj.name) == _pose_key(obj):
                continue
            STATE['pending'].add(obj.name)
        if STATE['pending'] and not bpy.app.timers.is_registered(_refresh_pending):
            bpy.app.timers.register(_refresh_pending, first_interval=0.12)
    except Exception:
        pass


# ── visibility ──────────────────────────────────────────────────────

def set_visible(context, show):
    """Show/hide the planes.  While a plane (or the DICOM review) is shown the
    MPR view hides the IOS models and shows neighbours + a CBCT ghost."""
    scene = context.scene
    scene[VISIBLE_KEY] = bool(show)
    for obj in planes(scene):
        obj.hide_set(not show)
        if show:
            STATE['pending'].add(obj.name)
    if show and not bpy.app.timers.is_registered(_refresh_pending):
        bpy.app.timers.register(_refresh_pending, first_interval=0.01)
    # 9.21.10/11 hid the closed model directly: give it back to the MPR view.
    for name in json.loads(str(scene.get(HIDDEN_MODELS, '[]'))):
        model = scene.objects.get(name)
        if model is not None:
            model.hide_set(False)
    scene[HIDDEN_MODELS] = '[]'
    from . import mpr_view
    mpr_view.sync(context)


# ── operators ───────────────────────────────────────────────────────

class DSG_OT_CreateInclinationPlane(bpy.types.Operator):
    bl_idname = 'dsg.create_implant_inclination_plane'
    bl_label = 'Plano radiográfico del implante'
    bl_description = ('Crea un plano con el CBCT que contiene el eje longitudinal del implante '
                      'seleccionado y lo sigue al moverlo o inclinarlo')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        implant = selected_implant(context)
        if implant is None:
            self.report({'ERROR'}, 'Selecciona un implante.')
            return {'CANCELLED'}
        cleanup(context.scene)
        obj = create(context, implant)
        set_visible(context, True)
        if obj.get('DSG_implant_mpr_status') != 'OK':
            self.report({'WARNING'}, 'Plano creado, pero el CBCT no está cargado: abre la revisión DICOM.')
        return {'FINISHED'}


class DSG_OT_RotateInclinationPlane(bpy.types.Operator):
    bl_idname = 'dsg.rotate_implant_inclination_plane'
    bl_label = 'Orientación del plano'
    bl_description = 'Alterna el plano entre mesio-distal y vestíbulo-lingual (siempre contiene el eje del implante)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        implant = selected_implant(context)
        plane = plane_for(implant)
        if plane is None:
            self.report({'ERROR'}, 'Crea primero el plano del implante.')
            return {'CANCELLED'}
        create(context, implant, 'VL' if plane.get(ORIENTATION, 'MD') == 'MD' else 'MD')
        set_visible(context, True)
        return {'FINISHED'}


class DSG_OT_ColorInclinationPlane(bpy.types.Operator):
    bl_idname = 'dsg.color_implant_inclination_plane'
    bl_label = 'Color del marco'
    bl_description = 'Cambia el color del marco del plano: azul, rojo o verde'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        plane = plane_for(selected_implant(context))
        if plane is None:
            self.report({'ERROR'}, 'Crea primero el plano del implante.')
            return {'CANCELLED'}
        current = plane.get(COLOR_KEY, 'BLUE')
        set_color(plane, ORDER[(ORDER.index(current) + 1) % len(ORDER)] if current in ORDER else 'BLUE')
        return {'FINISHED'}


class DSG_OT_ToggleInclinationPlanes(bpy.types.Operator):
    bl_idname = 'dsg.toggle_implant_inclination_planes'
    bl_label = 'Mostrar/ocultar planos del implante'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        set_visible(context, not visible(context.scene))
        return {'FINISHED'}


CLASSES = (DSG_OT_CreateInclinationPlane, DSG_OT_RotateInclinationPlane, DSG_OT_ToggleInclinationPlanes,
           DSG_OT_ColorInclinationPlane)


def draw(layout, context):
    scene = context.scene
    implant = selected_implant(context)
    plane = plane_for(implant)
    box = layout.box()
    row = box.row(align=True)
    row.enabled = implant is not None
    if plane is None:
        row.operator('dsg.create_implant_inclination_plane',
                     text='PLANO DEL IMPLANTE (CBCT)',icon='IMAGE_PLANE')
    if planes(scene):
        shown = visible(scene)
        row.operator('dsg.toggle_implant_inclination_planes', text='',
                     icon='HIDE_OFF' if shown else 'HIDE_ON', depress=shown)
    if plane is not None:
        row = box.row(align=True)
        label = 'Mesio-distal' if plane.get(ORIENTATION, 'MD') == 'MD' else 'Vestíbulo-lingual'
        row.operator('dsg.rotate_implant_inclination_plane', text=label, icon='FILE_REFRESH')
        box.prop(plane,'dsg_implant_mpr_angle',text='Inclinación MPR',slider=True)
        if plane.get('DSG_implant_mpr_status') not in (None, 'OK'):
            box.label(text=str(plane['DSG_implant_mpr_status']), icon='ERROR')
    elif implant is None:
        box.label(text='Selecciona un implante', icon='INFO')


def register():
    register_angle()
    if _follow not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_follow)


def unregister():
    if _follow in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_follow)
    if bpy.app.timers.is_registered(_refresh_pending):
        bpy.app.timers.unregister(_refresh_pending)
    if 'dsg_implant_mpr_angle' in bpy.types.Object.bl_rna.properties:
        del bpy.types.Object.dsg_implant_mpr_angle


def draw_rows(layout, context):
    """Implant plane entry for the MPR list (eye + create + options)."""
    scene = context.scene
    implant = selected_implant(context)
    plane = plane_for(implant)
    row = layout.row(align=True)
    if planes(scene):
        shown = visible(scene)
        eye = row.operator('dsg.toggle_mpr_plane', text='', icon='HIDE_OFF' if shown else 'HIDE_ON',
                           depress=shown)
        eye.kind = 'IMPLANT'
    else:
        getattr(row, '_layout', row).label(text='', icon='BLANK1')
    if plane is None:
        create = row.row(align=True)
        create.enabled = implant is not None
        create.operator('dsg.create_implant_inclination_plane',
                        text='Plano del implante (eje)',icon='IMAGE_PLANE')
    if plane is not None:
        options = layout.row(align=True)
        options.separator(factor=2.0)
        label = 'Mesio-distal' if plane.get(ORIENTATION, 'MD') == 'MD' else 'Vestíbulo-lingual'
        options.operator('dsg.rotate_implant_inclination_plane', text=label, icon='FILE_REFRESH')
        layout.prop(plane,'dsg_implant_mpr_angle',text='Inclinación MPR',slider=True)
        if plane.get('DSG_implant_mpr_status') not in (None, 'OK'):
            layout.label(text=str(plane['DSG_implant_mpr_status']), icon='ERROR')
