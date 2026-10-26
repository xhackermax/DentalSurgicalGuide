"""Full shaft safety envelope for editable and confirmed static microscrews."""
import json
import bpy
from mathutils import Vector

from . import safety_volume as implant_safety


def screws():
    return [o for o in bpy.data.objects if o.type == 'MESH' and o.get('DSG_static_microscrew')
            and not o.get('DSG_obsolete_hidden')]


def sync(context, screw):
    from .. import guide_module as g
    margin = max(g.INTERIMPLANT_SAFETY_MARGIN_PER_IMPLANT_MM,float(context.scene.dsg_props.implant_tooth_clearance))
    scale = screw.matrix_world.to_scale()
    diameter = float(screw.get('DSG_microscrew_diameter_mm',g.MICROSCREW_DIAMETER_DEFAULT_MM))
    radius = diameter*.5*max(abs(scale.x),abs(scale.y)) + margin
    contact = float(screw.get('DSG_microscrew_contact_local_z_mm',g.MICROSCREW_TEMPLATE_CONTACT_Z_MM))
    tip = min(v.co.z for v in screw.data.vertices)
    if tip >= contact:
        raise ValueError('No se pudo determinar la punta del microtornillo.')
    height = (contact-tip)*abs(scale.z) + 2*margin
    axis = (screw.matrix_world.to_3x3() @ Vector((0,0,1))).normalized()
    center = screw.matrix_world @ Vector((0,0,(contact+tip)*.5))
    platform = screw.matrix_world @ Vector((0,0,contact))
    objects = []
    for prefix,length,location,hidden in [('DSG_MicroSafety_',2.,platform,False),
                                          ('DSG_HiddenMicroSafety_',height,center,True)]:
        name = prefix+screw.name
        obj = bpy.data.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name,g.make_cylinder_mesh(name+'_Mesh',radius,length,verts=64))
            g.link_object(context,obj)
        elif abs(obj.get('radius_mm',-1)-radius) > 1e-5 or abs(obj.get('height_mm',-1)-length) > 1e-5:
            g._replace_mesh_data_preserve_object(obj,g.make_cylinder_mesh(name+'_Mesh',radius,length,verts=64))
        obj.parent = screw
        obj.matrix_parent_inverse = screw.matrix_world.inverted_safe()
        obj.matrix_world = g._matrix_along_local_z(location,axis)
        obj.hide_render = True
        obj.hide_select = True
        obj.hide_viewport = hidden
        obj.hide_set(hidden)
        obj.show_in_front = not hidden
        obj.display_type = 'WIRE'
        obj.color = (.95,.55,.12,1.)
        obj['DSG_microscrew_safety'] = True
        obj['DSG_microscrew_visual_name'] = screw.name
        obj['radius_mm'],obj['height_mm'] = radius,length
        objects.append(obj)
    return objects[1]


def contacts(context,screw):
    volume = sync(context,screw)
    obstacles = implant_safety.obstacles(context.scene,screw,include_canals=False)+[s for s in screws() if s != screw]
    failures = implant_safety.mesh_contacts(context,volume,obstacles)
    from .nerve_safety import failures as nerve_failures
    failures += nerve_failures(context,screw)
    from .upper_cavity_safety import failures as upper_failures
    failures += upper_failures(context,screw)
    screw['DSG_safety_volume_contacts'] = json.dumps(failures)
    return failures


def validate(context,screw,fresh=True):
    if fresh:
        from . import nerve_safety
        implant_safety._GEOMETRY.clear()
        nerve_safety.clear()
    try:
        failures = contacts(context,screw)
    except (ValueError,RuntimeError) as exc:
        return 'No se pudo verificar la seguridad del microtornillo: '+str(exc)
    from .nerve_safety import description
    from .upper_cavity_safety import description as upper_description
    return 'Seguridad del microtornillo: '+'; '.join(upper_description(screw,name) if upper_description(screw,name)!=name else description(screw,name) for name in failures) if failures else None


def gate(context,operator):
    from . import nerve_safety
    implant_safety._GEOMETRY.clear()
    nerve_safety.clear()
    for screw in screws():
        error = validate(context,screw,fresh=False)
        if error:
            operator.report({'ERROR'},error)
            return False
    return True


def needs_refresh():
    names = {s.name for s in screws()}
    present = set()
    for obj in bpy.data.objects:
        if obj.get('DSG_microscrew_safety'):
            owner = obj.get('DSG_microscrew_visual_name')
            if owner not in names:
                return True
            present.add(obj.name)
    return any(('DSG_MicroSafety_'+n) not in present or ('DSG_HiddenMicroSafety_'+n) not in present for n in names)


def request_refresh(context):
    """Safe from Panel.draw: rebuilds missing/orphan safety cylinders later."""
    if needs_refresh():
        from .deferred import run_later
        run_later('microscrew_safety', refresh)


def remove_orphans():
    """Delete safety cylinders whose microscrew no longer exists."""
    names = {o.name for o in bpy.data.objects if o.type == 'MESH' and o.get('DSG_static_microscrew')}
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.get('DSG_microscrew_safety') and (obj.get('DSG_microscrew_visual_name') not in names
                                                 or bpy.data.objects.get(str(obj.get('DSG_microscrew_visual_name'))) is None):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            removed += 1
    return removed


def refresh(context):
    names = {s.name for s in screws()}
    for obj in list(bpy.data.objects):
        if obj.get('DSG_microscrew_safety') and obj.get('DSG_microscrew_visual_name') not in names:
            bpy.data.objects.remove(obj,do_unlink=True)
    for screw in screws():
        sync(context,screw)
