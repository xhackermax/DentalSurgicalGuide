"""Change the diameter/length of the implant being planned, in place.

Editing Diámetro or Longitud in step 4 resizes the active implant (or the
last one created) instead of requiring delete + add.  The platform stays on
the same point and the axis is unchanged; only the apex moves with length.
"""
import bpy
from mathutils import Vector

_BUSY = {'active': False}


def target_implant(context):
    from .. import guide_module as g
    props = context.scene.dsg_props
    active = context.active_object
    if g.is_valid_implant_obj(active):
        return active
    if active is not None:
        owner = bpy.data.objects.get(str(active.get('DSG_implant_name', '') or ''))
        if g.is_valid_implant_obj(owner):
            return owner
    if g.is_valid_implant_obj(props.implant_obj):
        return props.implant_obj
    implants = g.get_all_implant_objects(props)
    return implants[-1] if implants else None


def resize(context, implant, diameter, length):
    """Rebuild the implant mesh at the new size; returns True if it changed."""
    from .. import guide_module as g
    from . import safety_volume
    props = context.scene.dsg_props
    old_diameter = float(implant.get('DSG_implant_diameter', diameter))
    old_length = float(implant.get('DSG_implant_length', length))
    if abs(old_diameter - diameter) < 1.0e-6 and abs(old_length - length) < 1.0e-6:
        return False
    platform = g.get_implant_platform_center_world(props, implant)
    apical = (implant.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    try:
        mesh = g.make_embedded_implant_mesh(implant.data.name, diameter, length)
    except (ValueError, RuntimeError):
        mesh = g.make_cylinder_mesh(implant.data.name, diameter * 0.5, length, verts=32)
    for material in implant.data.materials:
        mesh.materials.append(material)
    name = implant.data.name
    g._replace_mesh_data_preserve_object(implant, mesh)
    mesh.name = name
    matrix = implant.matrix_world.copy()
    matrix.translation = platform + apical * (length * 0.5)
    implant.matrix_world = matrix
    for key in ('DSG_catalogue_asset_id','DSG_catalogue_platform_local_mm','DSG_optimizer_family'):
        if key in implant:del implant[key]
    implant['DSG_implant_diameter'] = float(diameter)
    implant['DSG_implant_length'] = float(length)
    if bpy.data.objects.get(safety_volume.PREFIX + implant.name) is not None:
        safety_volume.sync(context, props, implant)
    if bpy.data.objects.get(g._implant_safety_halo_name(implant)) is not None:
        safety_volume.visible(context, props, implant)
    return True


def on_diameter_changed(props, context):
    on_size_changed(props, context, 'DIAMETER')


def on_length_changed(props, context):
    on_size_changed(props, context, 'LENGTH')


def on_size_changed(props, context, which='BOTH'):
    """FloatProperty update callback; each field changes only its own size."""
    from .. import guide_module as g
    if _BUSY['active'] or context is None or context.scene is None:
        return
    if int(props.current_step) != int(g.STEP_IMPLANT):
        return
    implant = target_implant(context)
    if implant is None:
        return
    _BUSY['active'] = True
    try:
        diameter = float(implant.get('DSG_implant_diameter', props.implant_diameter))
        length = float(implant.get('DSG_implant_length', props.implant_length))
        if which in {'DIAMETER', 'BOTH'}:
            diameter = float(props.implant_diameter)
        if which in {'LENGTH', 'BOTH'}:
            length = float(props.implant_length)
        resize(context, implant, diameter, length)
    except (ValueError, RuntimeError, ReferenceError) as exc:
        print(f'[DSG] implant resize: {exc}')
    finally:
        _BUSY['active'] = False
