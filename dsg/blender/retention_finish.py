"""One user action for retention generation, local relief and seating review."""
import bpy


def run(context):
    from .. import guide_module as guide
    from .ios_tooth_edit import immediate_ready
    if not immediate_ready(context):
        return {'CANCELLED'}
    blockout = bpy.data.objects.get(guide.BLOCKOUT_NAME)
    if context.mode == 'EDIT_MESH' and context.edit_object == blockout:
        # This operation already repeats the seating audit. Rebuilding here
        # would discard the clinician's selected local correction.
        return bpy.ops.dsg.apply_selected_blockout_relief()
    if context.mode != 'OBJECT':
        return {'CANCELLED'}
    from . import live_relief
    live_relief.commit(context, audit=False)  # a rebuild starts from a clean preview
    if bpy.ops.dsg.prepare_aligned_model() != {'FINISHED'}:
        return {'CANCELLED'}
    # The seating audit already ran inside prepare_aligned_model; repeating
    # it here doubled the cost of every click.
    blockout = bpy.data.objects.get(guide.BLOCKOUT_NAME)
    status = str(blockout.get('DSG_seating_validation_status', '')).upper() if blockout is not None else ''
    return {'FINISHED'} if status == 'PASSED' else {'CANCELLED'}


class DSG_OT_PrepareRetentionUnified(bpy.types.Operator):
    bl_idname = 'dsg.prepare_retention_unified'
    bl_label = 'PREPARAR MODELO RETENTIVO'
    bl_description = 'Calcula o actualiza el modelo y comprueba el asiento; en edición aplica el alivio seleccionado'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = run(context)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if result != {'FINISHED'}:
            self.report({'WARNING'}, 'Revisa el modelo, el asiento y la selección antes de continuar.')
        return result


CLASSES = (DSG_OT_PrepareRetentionUnified,)
