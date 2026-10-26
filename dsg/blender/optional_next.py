"""Skip only optional work; preserve confirmed geometry and existing gates."""
import bpy


def call(identifier):
    namespace, name = identifier.split('.')
    return getattr(getattr(bpy.ops, namespace), name)() == {'FINISHED'}


def advance(context, operator):
    from .. import guide_module as g
    props = context.scene.dsg_props
    step = int(props.current_step)
    if step not in {g.STEP_FRAME, g.STEP_IRRIGATION, g.STEP_REINFORCEMENT}:
        operator.report({'ERROR'}, 'Este paso es obligatorio y no se puede omitir.')
        return {'CANCELLED'}
    if not g._require_workflow_stage(operator, context, step,
                                    action_en='Cannot advance', action_es='No se puede avanzar'):
        return {'CANCELLED'}
    if step == g.STEP_FRAME:
        # A placed microscrew is kept: the pending one is confirmed and both are
        # incorporated into the frame (it used to be silently discarded here,
        # leaving only its orange safety cylinder).  If it cannot be confirmed
        # (safety), the step does not advance and the error is reported.
        if g.get_pending_microscrew_preview(props) is not None or g.get_confirmed_microscrew_objects():
            if not call('dsg.apply_microscrews_to_frame'):
                operator.report({'ERROR'}, 'El microtornillo colocado no se pudo incorporar; revísalo o descártalo antes de seguir.')
                return {'CANCELLED'}
        from . import microscrew_safety
        microscrew_safety.remove_orphans()
        return {'FINISHED'} if call('dsg.confirm_tube_frame') else {'CANCELLED'}
    if step == g.STEP_IRRIGATION:
        guide = g.get_active_guide_obj(props)
        resolution = str(guide.get('DSG_irrigation_resolution', '')).upper() if guide else ''
        if g.get_pending_irrigation_preview(props) is not None:
            if not call('dsg.remove_last_irrigation'):
                return {'CANCELLED'}
        if resolution not in {'APPLIED', 'SKIPPED'}:
            action = 'dsg.confirm_irrigation' if g.get_confirmed_irrigation_walls() else 'dsg.skip_irrigation'
            if not call(action):
                return {'CANCELLED'}
        return {'FINISHED'} if call('dsg.continue_after_irrigation') else {'CANCELLED'}
    if g.get_pending_reinforcement_preview(props) is not None:
        if not call('dsg.cancel_reinforcement_preview'):
            return {'CANCELLED'}
    guide = g.get_active_guide_obj(props)
    if guide is not None and guide.get('DSG_reinforcement_resolution') == 'APPLIED' and not g.get_confirmed_reinforcement_curves():
        if not g._require_workflow_stage(operator, context, g.STEP_DRILL,
                                        action_en='Cannot advance', action_es='No se puede avanzar'):
            return {'CANCELLED'}
        props.current_step = g.STEP_DRILL
        return {'FINISHED'} if props.current_step == g.STEP_DRILL else {'CANCELLED'}
    action = 'dsg.apply_reinforcements' if g.get_confirmed_reinforcement_curves() else 'dsg.skip_reinforcement'
    return {'FINISHED'} if call(action) else {'CANCELLED'}


class DSG_OT_OptionalNext(bpy.types.Operator):
    bl_idname = 'dsg.optional_next'
    bl_label = 'SIGUIENTE'
    bl_description = 'Conserva lo confirmado (también el microtornillo colocado), descarta las demás vistas previas pendientes y omite las mejoras opcionales restantes'
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        try:
            return advance(context, self)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (DSG_OT_OptionalNext,)
