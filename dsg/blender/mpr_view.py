"""Radiographic (MPR) viewing mode of the implant step.

While the DICOM review is open or an implant plane is shown:
* every IOS-derived model (closed model, passive/socketed IOS, blockout,
  antagonists...) is hidden;
* only the segmented neighbour teeth chosen by the clinician are shown;
* a "ghost" of the CBCT is shown: the segmented bone of the implant's arch,
  very translucent, drawn from a linked copy so the bone keeps its material.
Everything that was hidden is restored when the mode ends.
"""
import json

import bpy

HIDDEN_KEY = 'DSG_mpr_view_hidden_models'
ACTIVE_KEY = 'DSG_mpr_view_active'
GHOST_PREFIX = 'DSG_CBCT_Ghost_'
GHOST_MATERIAL = 'DSG_CBCT_Ghost'
GHOST_COLOR = (0.85, 0.88, 0.95, 0.12)


def active(scene):
    return bool(scene.get(ACTIVE_KEY, False))


def wanted(context):
    from .. import guide_module as g
    from . import implant_plane
    scene = context.scene
    # 9.24.9: the radiographic view belongs to the implant step only.
    props = getattr(scene, 'dsg_props', None)
    step = int(getattr(props, 'current_step', -1)) if props is not None else -1
    if step in {g.STEP_FRAME, g.STEP_SLEEVE} and any(
            plane.get('DSG_microscrew_mpr') and not plane.hide_get()
            for plane in implant_plane.planes(scene)):
        return True
    if step != int(g.STEP_IMPLANT):
        return False
    planes_shown = implant_plane.visible(scene) and any(not p.hide_get() for p in implant_plane.planes(scene))
    return bool(g._dicom_review_is_active(context) or planes_shown)


def _keep(obj, g):
    """Objects that stay as they are in MPR view."""
    if obj.type != 'MESH':
        return True
    name = obj.name
    if name.startswith((GHOST_PREFIX, 'DSG_AxisMPR_', 'DSG_OptimizationPreview')):
        return True
    role = str(obj.get('dental_suite_dsg_role', '') or obj.get('dsg_role', '') or '')
    if role == 'implant' or g.is_valid_implant_obj(obj) or g._is_valid_mpr_microscrew(obj):
        return True
    if name.startswith(('DSG_Implant', 'DSG_SafetyHalo', 'DSG_EmergenceTube', 'DSG_HiddenSafety',
                        'DSG_Sleeve', 'DSG_Microscrew', 'DSG_Measure', 'DICP_', 'DICOM_')):
        return True
    return g._is_dicom_related_object(obj)


def _ghost_material():
    material = bpy.data.materials.get(GHOST_MATERIAL) or bpy.data.materials.new(GHOST_MATERIAL)
    from .clinical_materials import configure
    configure(material, GHOST_COLOR)
    return material


def _bones(scene):
    """Bone of the implant's arch, whichever route built it.

    Full route: Dental_DICOM_Maxilla / Mandible.  Simple route (9.24.3): the
    two coloured CBCT arches (DSG_simple_upper/lower_object).  Immediate
    route: the arch composites.  Before, only the full-route names were
    looked up, so the simple route showed no CBCT ghost at all."""
    from . import protected_neighbors
    lower = bool(protected_neighbors.lower(scene))
    side = 'lower' if lower else 'upper'
    names = ['Dental_DICOM_Mandible' if lower else 'Dental_DICOM_Maxilla',
             str(scene.get(f'DSG_simple_{side}_object', '') or ''),
             str(scene.get(f'DSG_immediate_{side}_composite', '') or '')]
    for name in names:
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None and obj.type == 'MESH' and len(obj.data.polygons):
            return [obj]
    return []


def _show_ghost(context):
    material = _ghost_material()
    wanted_names = set()
    for bone in _bones(context.scene):
        name = GHOST_PREFIX + bone.name
        wanted_names.add(name)
        ghost = bpy.data.objects.get(name)
        if ghost is None or ghost.data != bone.data:
            if ghost is not None:
                bpy.data.objects.remove(ghost, do_unlink=True)
            ghost = bpy.data.objects.new(name, bone.data)   # linked: no mesh copy
            context.scene.collection.objects.link(ghost)
        ghost.matrix_world = bone.matrix_world.copy()
        for slot in ghost.material_slots:
            slot.link = 'OBJECT'
            slot.material = material
        ghost.hide_select = True
        ghost.hide_render = True
        ghost.show_transparent = True
        ghost['DSG_preview_only'] = True
        ghost.hide_viewport = False
        ghost.hide_set(False)
    for obj in list(bpy.data.objects):
        if obj.name.startswith(GHOST_PREFIX) and obj.name not in wanted_names:
            bpy.data.objects.remove(obj, do_unlink=True)


def _hide_ghost():
    for obj in list(bpy.data.objects):
        if obj.name.startswith(GHOST_PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)


def _show_neighbours(context):
    from . import protected_neighbors
    keep = protected_neighbors.kept(context.scene)
    cut = protected_neighbors.extraction(context.scene)
    for tooth in protected_neighbors.teeth(context.scene):
        fdi = int(tooth.get('DSG_fdi_number', 0))
        show = fdi in keep and fdi not in cut
        tooth.hide_viewport = not show
        try:
            tooth.hide_set(not show)
        except RuntimeError:
            pass


def enter(context):
    from .. import guide_module as g
    scene = context.scene
    hidden = json.loads(str(scene.get(HIDDEN_KEY, '[]')))
    for obj in list(scene.objects):
        if _keep(obj, g) or not obj.visible_get():
            continue
        # 9.24.5: a model already listed but shown again by something else
        # (stage restore, reload) is hidden again instead of being skipped.
        obj.hide_set(True)
        if obj.name not in hidden:
            hidden.append(obj.name)
    scene[HIDDEN_KEY] = json.dumps(hidden)
    scene[ACTIVE_KEY] = True
    _show_neighbours(context)
    _show_ghost(context)


def leave(context):
    scene = context.scene
    for name in json.loads(str(scene.get(HIDDEN_KEY, '[]'))):
        obj = scene.objects.get(name)
        if obj is not None:
            try:
                obj.hide_set(False)
            except RuntimeError:
                pass
    scene[HIDDEN_KEY] = '[]'
    scene[ACTIVE_KEY] = False
    _hide_ghost()


def sync(context):
    """Enter or leave the MPR view to match the review / implant planes."""
    try:
        if wanted(context):
            enter(context)
        elif active(context.scene):
            leave(context)
            from . import protected_neighbors
            protected_neighbors.sync(context)
    except Exception as exc:
        print(f'[DSG] MPR view: {exc}')


# â”€â”€ MPR plane visibility (list in the implant step) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PLANE_OBJECTS = {'AXIAL': 'DICOM_PLANE_AXIAL', 'SAGITTAL': 'DICOM_PLANE_SAGITTAL'}


def plane_object(kind):
    return bpy.data.objects.get(PLANE_OBJECTS.get(kind, ''))


def plane_shown(kind):
    obj = plane_object(kind)
    return obj is not None and obj.visible_get()


def any_shown(context):
    from . import implant_plane
    scene = context.scene
    implants = implant_plane.visible(scene) and bool(implant_plane.planes(scene))
    return implants or any(plane_shown(kind) for kind in PLANE_OBJECTS)


def _set_plane(kind, show):
    obj = plane_object(kind)
    if obj is None:
        return
    obj.hide_viewport = False
    try:
        obj.hide_set(not show)
    except RuntimeError:
        pass


class DSG_OT_ToggleMPRPlane(bpy.types.Operator):
    bl_idname = 'dsg.toggle_mpr_plane'
    bl_label = 'Mostrar/ocultar MPR'
    bl_description = 'Muestra u oculta el plano radiogrÃ¡fico (ALL: todos los planos MPR)'
    bl_options = {'REGISTER'}

    kind: bpy.props.EnumProperty(items=[('AXIAL', 'Plano Z', ''), ('SAGITTAL', 'InclinaciÃ³n', ''),
                                        ('IMPLANT', 'Plano del implante', ''), ('ALL', 'Todos', '')])

    def execute(self, context):
        from . import implant_plane
        if self.kind == 'IMPLANT':
            implant_plane.set_visible(context, not implant_plane.visible(context.scene))
        elif self.kind == 'ALL':
            show = not any_shown(context)
            for kind in PLANE_OBJECTS:
                _set_plane(kind, show)
            if implant_plane.planes(context.scene):
                implant_plane.set_visible(context, show)
        else:
            _set_plane(self.kind, not plane_shown(self.kind))
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


CLASSES = (DSG_OT_ToggleMPRPlane,)
