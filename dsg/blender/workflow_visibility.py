"""Keep native Alt+H from revealing hidden workflow machinery in DSG."""
import json
import bpy

CONTEXT = 'DSG_visibility_stage'
ALLOWED = 'DSG_visibility_stage_reference'
SELECTABLE = 'DSG_visibility_stage_selectable'
KEYMAPS = []


def stage_key(context):
    return context.scene.name + ':' + str(context.scene.dsg_props.current_step)


def capture(context):
    """Called after stage reconstruction, before the user can hide references."""
    from . import emergence_reference
    emergence_reference.sync(context)
    key = stage_key(context)
    from . import mpr_view
    radiographic_references = set()
    if mpr_view.active(context.scene):
        try:
            radiographic_references = set(json.loads(str(context.scene.get(mpr_view.HIDDEN_KEY, '[]'))))
        except (ValueError, TypeError):
            pass
    for obj in context.scene.objects:
        obj[CONTEXT] = key
        obj[ALLOWED] = (not (obj.hide_viewport or obj.hide_get())
                        or obj.name in radiographic_references)
        obj[SELECTABLE] = not obj.hide_select


def protected(context, obj):
    if not (obj.hide_get() or obj.hide_viewport):
        return False
    from . import mpr_view
    from .. import guide_module as g
    if mpr_view.active(context.scene) and not mpr_view._keep(obj, g):
        return True
    if obj.name.startswith(('DSG_AxisMPR_', 'DSG_CBCT_Ghost_', 'DICP_', 'DICOM_')):
        return True
    if obj.get('DSG_obsolete_hidden') or obj.get('DSG_workflow_checkpoint_source_name') or obj.get('DSG_checkpoint_source_name'):
        return True
    if obj.get(CONTEXT) == stage_key(context):
        return not bool(obj.get(ALLOWED, False))
    if obj.get('DSG_hidden_source'):
        return True
    # Newly generated hidden technical previews were not present at stage entry.
    return bool(obj.hide_select)


def reveal(context):
    key = stage_key(context)
    for obj in context.view_layer.objects:
        if not (obj.hide_get() or obj.hide_viewport) or protected(context, obj):
            continue
        # Preserve the current-step layer's original selection policy. Readonly
        # implants remain readonly; an IOS hidden by a layer toggle stays usable.
        if obj.get(CONTEXT) == key and obj.get(ALLOWED):
            obj.hide_viewport = False
            obj.hide_select = not bool(obj.get(SELECTABLE, True))
        obj.hide_set(False)
    return {'FINISHED'}


class DSG_OT_RevealCurrentStage(bpy.types.Operator):
    bl_idname = 'dsg.reveal_current_stage'
    bl_label = 'Mostrar objetos ocultados en el paso actual'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .. import core
        return (context.mode == 'OBJECT' and context.area is not None
                and context.area.type == 'VIEW_3D'
                and core.infer_stage(context.scene) == core.STAGE_GUIDE)

    def execute(self, context):
        return reveal(context)


def register():
    bpy.utils.register_class(DSG_OT_RevealCurrentStage)
    config = bpy.context.window_manager.keyconfigs.addon
    if config is not None:
        keymap = config.keymaps.new(name='Object Mode', space_type='EMPTY')
        item = keymap.keymap_items.new(DSG_OT_RevealCurrentStage.bl_idname,
                                      'H', 'PRESS', alt=True, head=True)
        KEYMAPS.append((keymap, item))


def unregister():
    for keymap, item in KEYMAPS:
        keymap.keymap_items.remove(item)
    KEYMAPS.clear()
    bpy.utils.unregister_class(DSG_OT_RevealCurrentStage)
