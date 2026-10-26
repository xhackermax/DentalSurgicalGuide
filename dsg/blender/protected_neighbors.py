"""Persist visualization of CBCT neighbours, independently of extraction FDI."""
import json

import bpy

KEPT = 'DSG_protected_neighbor_fdis'
EDITOR = 'DSG_protected_neighbors_editor'
CONFIRMED = 'DSG_protected_neighbors_confirmed'


def extraction(scene):
    from .. import core
    return set(core._immediate_extraction_fdis(scene)) if core.clinical_route(scene) == core.ROUTE_IMMEDIATE else set()


def teeth(scene):
    from .. import cbct_dental_module as dental
    return dental.dentition_objects()


def kept(scene):
    """Neighbours the clinician chose to SEE.  None by default: showing every
    segmented tooth at once was slow and looked like unrequested imports.
    Hidden teeth are still checked by the implant safety volume."""
    available = {int(o.get('DSG_fdi_number',0)) for o in teeth(scene)}-extraction(scene)
    if KEPT not in scene:
        return set()
    return set(json.loads(str(scene[KEPT]))) & available


def canals():
    from .. import core, dicom_module as dicom
    result = [o for o in bpy.data.objects if o.type == 'MESH' and (
        o.name.startswith(dicom.NAME_DICOM_MANDIBULAR_CANAL)
        or o.get(core.SUITE_ROLE_KEY) == core.ROLE_DICOM_MANDIBULAR_CANAL
        or o.get(core.LEGACY_ROLE_KEY) == core.ROLE_DICOM_MANDIBULAR_CANAL)]
    return result


def lower(scene):
    from .. import core, guide_module as g
    # The displayed anatomy follows the selected implant, including its controller.
    # Another implant in the opposite arch must not switch this panel.
    if bpy.context.scene == scene:
        from .implant_plane import selected_implant
        implant=selected_implant(bpy.context)
        if g.is_valid_implant_obj(implant):
            fdi=int(implant.get('DSG_target_fdi',0))
            if fdi:return 30 <= fdi <= 48
            arch=str(implant.get('DSG_nerve_arch','')).upper()
            if arch in {'MAXILLA','MANDIBLE'}:return arch=='MANDIBLE'
    return (str(scene.get('DSG_active_arch','')).upper() == 'MANDIBLE'
            or any(30 <= int(o.get('DSG_target_fdi',0)) <= 48 for o in g.get_all_implant_objects(scene.dsg_props))
            or 30 <= core.target_fdi(scene) <= 48)


def _desired(context):
    """Visibility plan for the guide steps, or None when it does not apply.

    Retentive-model step: the root remnant (tooth to extract) stays hidden.
    Implant step: it is shown until the Boolean is done; after it, the IOS
    with its new socket replaces the passive model on screen.
    """
    from .. import core, guide_module as g
    from . import virtual_extraction
    scene = context.scene
    step = scene.dsg_props.current_step
    if core.infer_stage(scene) != core.STAGE_GUIDE or step not in {g.STEP_MODEL, g.STEP_IMPLANT, g.STEP_FRAME}:
        return None
    if g._dicom_review_is_active(context):
        return None
    from . import mpr_view
    if mpr_view.active(scene):   # radiographic view owns the visibility
        return None
    cut = extraction(scene)
    if step == g.STEP_MODEL:
        return [(obj, False, 'BOOLEAN_EXTRACTION') for obj in teeth(scene)
                if int(obj.get('DSG_fdi_number', 0)) in cut]
    visible = kept(scene)
    performed = virtual_extraction.performed(scene)
    show_cut = step == g.STEP_IMPLANT and not performed
    plan = []
    for obj in teeth(scene):
        fdi = int(obj.get('DSG_fdi_number',0))
        show = (fdi in cut and show_cut) or (fdi in visible and fdi not in cut)
        plan.append((obj, show, 'BOOLEAN_EXTRACTION' if fdi in cut else 'PROTECTED_NEIGHBOR'))
    return plan


def _models(context):
    """(object, shown) pairs for the socket view and the extension preview."""
    from .. import core, guide_module as g
    from . import virtual_extraction
    from .extraction_extension import NAME as PREVIEW
    scene = context.scene
    step = scene.dsg_props.current_step
    pairs = []
    preview = bpy.data.objects.get(PREVIEW)
    performed = virtual_extraction.performed(scene)
    if preview is not None:
        pairs.append((preview, step == g.STEP_IMPLANT and not performed))
    if step == g.STEP_IMPLANT and performed and core.clinical_route(scene) == core.ROUTE_IMMEDIATE:
        from .ios_tooth_edit import model
        ios = model(context)
        passive = g.get_passive_model_obj()
        if ios is not None and passive is not None and ios != passive:
            pairs += [(ios, True), (passive, False)]
    return pairs


def _apply(context, plan):
    from .deferred import assign, assign_key, set_hidden
    from .. import guide_module as g
    changed = False
    for obj, show, role in plan:
        changed |= set_hidden(obj, not show)
        changed |= assign(obj, 'hide_render', True)
        changed |= assign(obj, 'show_in_front', show)
        changed |= assign_key(obj, 'DSG_neighbor_visualized', show)
        changed |= assign_key(obj, 'DSG_neighbor_role', role)
    for obj, show in _models(context):
        changed |= set_hidden(obj, not show)
    if context.scene.dsg_props.current_step == g.STEP_MODEL:
        return changed
    if lower(context.scene):
        for obj in canals():
            changed |= set_hidden(obj, False)
            changed |= assign(obj, 'hide_render', True)
            changed |= assign(obj, 'hide_select', True)
            changed |= assign(obj, 'show_in_front', True)
            changed |= assign_key(obj, 'DSG_protected_nerve', True)
    return changed


def sync(context):
    """Apply neighbour/nerve visibility. Never call it from Panel.draw."""
    plan = _desired(context)
    if plan is not None:
        _apply(context, plan)


def needs_sync(context):
    plan = _desired(context)
    if plan is None:
        return False
    for obj, show, _role in plan:
        if obj.hide_viewport == show or bool(obj.get('DSG_neighbor_visualized')) != show:
            return True
    if any(obj.hide_viewport == show for obj, show in _models(context)):
        return True
    from .. import guide_module as g
    if context.scene.dsg_props.current_step == g.STEP_MODEL:
        return False
    return lower(context.scene) and any(obj.hide_viewport for obj in canals())


def request_sync(context):
    """Safe from Panel.draw: schedules sync only when something differs."""
    if needs_sync(context):
        from .deferred import run_later
        run_later('protected_neighbors', sync)


class DSG_OT_ToggleProtectedNeighbor(bpy.types.Operator):
    bl_idname = 'dsg.toggle_protected_neighbor'
    bl_label = 'Conservar diente vecino'
    bl_description = 'Muestra u oculta la raíz CBCT vecina; ocultarla no desactiva su comprobación de seguridad'
    bl_options = {'REGISTER','UNDO'}
    fdi: bpy.props.IntProperty(default=0)

    def execute(self,context):
        scene = context.scene
        if self.fdi in extraction(scene):
            self.report({'ERROR'},'Este FDI está fijado para extracción y pertenece a la booleana.')
            return {'CANCELLED'}
        values = kept(scene)
        if self.fdi in values:
            values.remove(self.fdi)
        else:
            values.add(self.fdi)
        scene[KEPT] = json.dumps(sorted(values))
        sync(context)
        return {'FINISHED'}


class DSG_OT_EditProtectedNeighbors(bpy.types.Operator):
    bl_idname = 'dsg.edit_protected_neighbors'
    bl_label = 'ELEGIR DIENTES VECINOS'

    def execute(self,context):
        context.scene[EDITOR] = not bool(context.scene.get(EDITOR))
        return {'FINISHED'}


class DSG_OT_ResetProtectedNeighbors(bpy.types.Operator):
    bl_idname = 'dsg.all_protected_neighbors'
    bl_label = 'MOSTRAR TODOS LOS VECINOS'
    bl_options = {'REGISTER','UNDO'}

    def execute(self,context):
        scene = context.scene
        available = {int(o.get('DSG_fdi_number',0)) for o in teeth(scene)}-extraction(scene)
        scene[KEPT] = json.dumps(sorted(available))
        sync(context)
        return {'FINISHED'}


class DSG_OT_ClearProtectedNeighbors(bpy.types.Operator):
    bl_idname = 'dsg.clear_protected_neighbors'
    bl_label = 'QUITAR DIENTES VECINOS'
    bl_description = 'Oculta todos los dientes vecinos segmentados; su comprobación de seguridad sigue activa'
    bl_options = {'REGISTER','UNDO'}

    def execute(self,context):
        context.scene[KEPT] = '[]'
        sync(context)
        return {'FINISHED'}


class DSG_OT_ConfirmProtectedNeighbors(bpy.types.Operator):
    bl_idname = 'dsg.confirm_protected_neighbors'
    bl_label = 'CONFIRMAR SELECCIÓN'
    bl_description = 'Fija los dientes vecinos visibles y pasa a la colocación del implante'
    bl_options = {'REGISTER','UNDO'}

    def execute(self,context):
        context.scene[CONFIRMED] = True
        context.scene[EDITOR] = False
        sync(context)
        return {'FINISHED'}


class DSG_OT_ReopenProtectedNeighbors(bpy.types.Operator):
    bl_idname = 'dsg.reopen_protected_neighbors'
    bl_label = 'Cambiar dientes vecinos'
    bl_options = {'REGISTER','UNDO'}

    def execute(self,context):
        context.scene[CONFIRMED] = False
        context.scene[EDITOR] = True
        return {'FINISHED'}


def confirmed(scene):
    from .. import guide_module as g
    # Scenes that already have implants were planned before this step existed.
    if CONFIRMED in scene:
        return bool(scene[CONFIRMED])
    return g.count_implants(scene.dsg_props) > 0


def _toggles(box, scene):
    cut = extraction(scene)
    visible = kept(scene)
    grid = box.grid_flow(columns=4, even_columns=True, align=True)
    for obj in sorted(teeth(scene),key=lambda o:int(o.get('DSG_fdi_number',0))):
        fdi = int(obj.get('DSG_fdi_number',0))
        if fdi in cut:
            continue
        button = grid.operator('dsg.toggle_protected_neighbor',text=str(fdi),
                               icon='CHECKBOX_HLT' if fdi in visible else 'CHECKBOX_DEHLT',depress=fdi in visible)
        button.fdi = fdi
    row = box.row(align=True)
    row.operator('dsg.clear_protected_neighbors',text='QUITAR DIENTES VECINOS',icon='X')
    row.operator('dsg.all_protected_neighbors',text='MOSTRAR TODOS')


def _nerve(layout, scene):
    if lower(scene):
        count = len(canals())
        layout.label(text='Nervio mandibular conservado' if count else 'Falta segmentación del nervio mandibular',
                     icon='CHECKMARK' if count else 'ERROR')


def draw_step(layout, context):
    """Neighbour step before implant placement; True once the selection is confirmed."""
    from .. import ui_style
    scene = context.scene
    if confirmed(scene):
        visible = sorted(kept(scene))
        row = layout.row(align=True)
        row.label(text='Dientes vecinos: ' + (', '.join(map(str, visible)) or 'ninguno') + ' ✓', icon='CHECKMARK')
        row.operator('dsg.reopen_protected_neighbors', text='', icon='GREASEPENCIL')
        _nerve(layout, scene)
        request_sync(context)
        return True
    box = layout.box()
    box.label(text='DIENTES VECINOS', icon='RESTRICT_SELECT_OFF')
    box.label(text='Marca los dientes que quieres ver al colocar el implante.', icon='INFO')
    _toggles(box, scene)
    _nerve(box, scene)
    action = ui_style.primary_action(box)
    action.operator('dsg.confirm_protected_neighbors', text='CONFIRMAR SELECCIÓN', icon='CHECKMARK')
    request_sync(context)
    return False


def draw(layout,context):
    scene = context.scene
    box = layout.box()
    cut = extraction(scene)
    if cut:
        box.label(text='Booleana · FDI '+', '.join(map(str,sorted(cut))),icon='MOD_BOOLEAN')
    box.operator('dsg.edit_protected_neighbors',text='ELEGIR DIENTES VECINOS',icon='RESTRICT_SELECT_OFF')
    if scene.get(EDITOR):
        visible = kept(scene)
        for obj in sorted(teeth(scene),key=lambda o:int(o.get('DSG_fdi_number',0))):
            fdi = int(obj.get('DSG_fdi_number',0))
            if fdi in cut:
                continue
            button = box.operator('dsg.toggle_protected_neighbor',text='FDI '+str(fdi),
                                  icon='CHECKBOX_HLT' if fdi in visible else 'CHECKBOX_DEHLT',depress=fdi in visible)
            button.fdi = fdi
        row = box.row(align=True)
        row.operator('dsg.clear_protected_neighbors',text='QUITAR DIENTES VECINOS',icon='X')
        row.operator('dsg.all_protected_neighbors',text='MOSTRAR TODOS')
    if lower(scene):
        count = len(canals())
        box.label(text='Nervio mandibular conservado' if count else 'Falta segmentación del nervio mandibular',
                  icon='CHECKMARK' if count else 'ERROR')
    request_sync(context)


CLASSES = (DSG_OT_ToggleProtectedNeighbor,DSG_OT_EditProtectedNeighbors,DSG_OT_ResetProtectedNeighbors,
           DSG_OT_ClearProtectedNeighbors,DSG_OT_ConfirmProtectedNeighbors,DSG_OT_ReopenProtectedNeighbors)
