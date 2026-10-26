"""Explicit optional manual tooth removal, without inventing a socket closure."""
import bpy

SKIPPED = 'DSG_ios_manual_tooth_removal_skipped'


class DSG_OT_IOSSkipToothRemoval(bpy.types.Operator):
    bl_idname = 'dsg.ios_skip_tooth_removal'
    bl_label = 'SIGUIENTE'
    bl_description = 'Omite la eliminación manual; la booleana del diente se hace tras el modelo retentivo'
    bl_options = {'REGISTER','UNDO'}

    @classmethod
    def poll(cls, context):
        from .ios_tooth_edit import model
        return context.mode in {'OBJECT','EDIT_MESH'} and model(context) is not None

    def execute(self, context):
        from .. import core, guide_module as g
        from . import ios_tooth_edit as edit, ios_socket_boolean as boolean
        obj = edit.model(context)
        if edit.editing(context):
            if bpy.ops.dsg.ios_cancel_tooth_removal() != {'FINISHED'}:
                return {'CANCELLED'}
        elif context.mode != 'OBJECT':
            self.report({'ERROR'},'Termina la edición o inicia la selección guiada antes de omitirla.')
            return {'CANCELLED'}
        topology = core._mesh_topology_counts(obj.data)
        if topology['boundary_edges'] or topology['non_manifold_edges']:
            self.report({'ERROR'},'Cierra primero el modelo IOS; no se puede omitir sobre una malla abierta.')
            return {'CANCELLED'}
        obj[SKIPPED] = True
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
            # The tooth Boolean is done after the retentive model.
            obj[boolean.PENDING] = True
            context.scene['DSG_ios_postextraction_confirmed'] = False
            g._clear_model_topology_cache()
            g._clear_retention_geometry_cache()
            g._remove_retention_previews()
            g._remove_retention_boundary()
            g.safe_remove_by_name(g.BLOCKOUT_NAME)
            g.safe_remove_by_name(g.COMBINED_NAME)
        self.report({'INFO'},'Eliminación manual omitida. Continúa con el modelo retentivo.')
        return {'FINISHED'}


CLASSES = (DSG_OT_IOSSkipToothRemoval,)
