"""DSG v9 · Ctrl+Z ligero.

Ctrl+Z is Blender's native undo, nothing else: no checkpoint copies of the
scene, no CBCT hashing, no files written to disk. Going back to the start of a
clinical stage is done with the deterministic stage buttons (↻ DICOM,
↻ ALINEAR, ↻ DSG and ATRÁS), which clear the later work instead of replaying
history.

What this module still does, because native undo needs it to be safe:
- before an undo, cancel the CBCT segmentation worker, the tooth-smoothing
  worker, DSG timers and any running DSG modal tool (they hold references
  that undo invalidates) and clear geometry caches;
- after an undo, block automatic stage advances until the user acts again;
- give every workflow operator the UNDO flag so Blender records a step.

The public names (begin, commit, has_checkpoint, restore_runtime,
undo_previous, automation_suspended) are kept so existing callers work.
"""
from __future__ import annotations
import functools
import bpy
from bpy.app.handlers import persistent

STATE_KEY = 'DSG_history_state'
PROJECT_KEY = 'DSG_history_project'
_ACTIVE_MODALS = {}
_UNDO_EPOCH = 0
_SUSPENDED = {'automation': False}


# --- compatibility API ------------------------------------------------------
def begin(context, label):
    """No checkpoint: native undo records the step when the operator ends."""
    _SUSPENDED['automation'] = False


def commit(context, label):
    """Finish delayed guide presentation so the undo step is complete."""
    from . import guide_module as guide, lifecycle
    scene = context.scene
    pending = any(key[0] == scene.name for key in guide.WORKFLOW_RESTORE_PENDING)
    pending = pending or scene.name in guide._IMPLANT_STEP_RESTORE_PENDING
    if pending:
        lifecycle.cancel_named_timers(guide.__name__, {'_restore_timer'})
        guide.WORKFLOW_RESTORE_PENDING.clear()
        guide._IMPLANT_STEP_RESTORE_PENDING.clear()
        guide._restore_workflow_stage(context, scene, scene.dsg_props.current_step)
    return ''


def has_checkpoint(scene):
    """There are no archived checkpoints; the legacy undo repairs always run."""
    return False


def automation_suspended():
    return bool(_SUSPENDED['automation'])


def restore_runtime(scene, force=False):
    return False


def undo_previous(context):
    if bpy.ops.ed.undo.poll():
        return bpy.ops.ed.undo()
    return {'CANCELLED'}


# --- undo safety ------------------------------------------------------------
@persistent
def _before_undo(*_):
    from .blender import generative_frame
    generative_frame.freeze_for_undo()
    global _UNDO_EPOCH
    _UNDO_EPOCH += 1
    _SUSPENDED['automation'] = True
    from .blender import implant_optimizer
    implant_optimizer.freeze_for_undo()
    # Modal operators retain RNA and mesh references. Release them before
    # native undo invalidates those references.
    for operator, context in list(_ACTIVE_MODALS.values()):
        _cancel_modal(operator, context)
    _ACTIVE_MODALS.clear()
    from . import cbct_post_smoothing as post, dicom_module as dicom, cbct_pipeline_client as pipeline, guide_module as guide, lifecycle, core
    lifecycle.cancel_module_timers(dicom.__name__)
    lifecycle.cancel_module_timers(core.__name__)
    core._IMMEDIATE_ROUTE_EXECUTING = False
    dicom._clear_pending_refresh_state()
    dicom.RUNTIME.undo_in_progress = True
    dicom.RUNTIME.update_lock = True
    lifecycle.cancel_module_timers(guide.__name__)
    guide.WORKFLOW_RESTORE_PENDING.clear()
    guide._IMPLANT_STEP_RESTORE_PENDING.clear()
    guide._AUTO_CLOSED_MODEL_ADVANCE_PENDING.clear()
    for name in ('_MODEL_TOPOLOGY_CACHE', '_FRAME_SURFACE_GRAPH_CACHE', '_RETENTION_BVH_CACHE',
                 '_ENGRAVE_PROJECTION_CACHE', '_PREFLIGHT_UI_CACHE', '_DSG_ACTION_RUNTIME'):
        getattr(guide, name, {}).clear()
    for name in ('_RETENTION_PREVIEW_REFRESH_PENDING', '_ENGRAVE_PREVIEW_REFRESH_PENDING',
                 '_DICOM_MEASURE_UPDATE_PENDING', '_DSG_OWNED_DATA_CLEANUP_PENDING'):
        setattr(guide, name, False)
    guide.unregister_contour_draw_handler()
    guide.unregister_irr_draw_handler()
    guide._draw_callback_irrigation._current_chain = []
    post.cancel(update_status=False)
    if dicom.semantic_workflow_busy():
        pipeline.cancel()
        dicom._ASYNC_SEGMENTATION.update(active=False, builder=None, prepared_surfaces=None, phase='')
        dicom._restore_ai_performance_session(bpy.context)


@persistent
def _after_undo(*_):
    from . import dicom_module as dicom
    dicom.RUNTIME.undo_in_progress = False
    dicom.RUNTIME.update_lock = False
    from .blender import implant_optimizer
    implant_optimizer.resume_after_undo()


@persistent
def _after_load(*_):
    _SUSPENDED['automation'] = False
    _after_undo()


def _cancel_modal(operator, context):
    for name in ('cancel', '_cancel', '_finish', '_cleanup', '_finish_modal', '_finish_cursor', '_remove_timer'):
        method = getattr(operator, name, None)
        if callable(method):
            try:
                if self_module(operator) == 'guide_module' and name == '_finish_modal' and operator.bl_idname == 'dsg.start_irrigation':
                    method(context.scene.dsg_props)
                else:
                    method(context)
            except (ReferenceError, RuntimeError, TypeError, AttributeError):
                continue
            break
    timer = getattr(operator, '_timer', None)
    if timer is not None:
        try:
            context.window_manager.event_timer_remove(timer)
            operator._timer = None
        except (ReferenceError, RuntimeError):
            pass


def self_module(operator):
    return type(operator).__module__.rsplit('.', 1)[-1]


# --- operator wrapping: modal tracking only, no snapshots ------------------
def _track_modal(self, context, result):
    key = self.as_pointer()
    if 'RUNNING_MODAL' in result:
        _ACTIVE_MODALS[key] = (self, context)
        self._dsg_undo_epoch = _UNDO_EPOCH
    elif result in ({'FINISHED'}, {'CANCELLED'}):
        _ACTIVE_MODALS.pop(key, None)


def _wrap_execute(execute):
    @functools.wraps(execute)
    def wrapped(self, context):
        _SUSPENDED['automation'] = False
        result = execute(self, context)
        _track_modal(self, context, result)
        return result
    return wrapped


def _wrap_invoke(invoke):
    @functools.wraps(invoke)
    def wrapped(self, context, event):
        _SUSPENDED['automation'] = False
        result = invoke(self, context, event)
        _track_modal(self, context, result)
        return result
    return wrapped


def _wrap_modal(modal):
    @functools.wraps(modal)
    def wrapped(self, context, event):
        if getattr(self, '_dsg_undo_epoch', _UNDO_EPOCH) != _UNDO_EPOCH:
            return {'CANCELLED'}
        result = modal(self, context, event)
        if result in ({'FINISHED'}, {'CANCELLED'}):
            _ACTIVE_MODALS.pop(self.as_pointer(), None)
        return result
    return wrapped


# Operations that edit Blender data but historically omitted native undo.
_EXTRA_UNDO = {'dicom_wizard_pro.clear_drawings', 'dicom_wizard_pro.calculate_segmentation',
 'dicom_wizard_pro.remove_small_islands', 'dicom_wizard_pro.keep_largest_island',
 'dicom_wizard_pro.close_gaps', 'dicom_wizard_pro.fill_holes', 'dicom_wizard_pro.to_segmentation',
 'dicom_wizard_pro.back_to_viewer', 'dicom_wizard_pro.adjust_tissue_sensitivity',
 'dicom_wizard_pro.reset_tissue_range', 'dicom_wizard_pro.direct_dicom_to_surface',
 'dicom_wizard_pro.next', 'dicom_wizard_pro.new_file', 'dicom_wizard_pro.auto_threshold',
 'dicom_wizard_pro.reset_plane', 'dicom_wizard_pro.center_plane', 'dicom_wizard_pro.analyze_tissues',
 'dicom_wizard_pro.generate_surface', 'dicom_wizard_pro.back_to_segmentation',
 'dicom_wizard_pro.move_review_plane', 'dicom_wizard_pro.rotate_review_plane',
 'dsg.cbct_toggle_fdi', 'dsg.cbct_post_smooth_teeth'}
_WORKFLOW_MODULES = {'core', 'dicom_module', 'cbct_dental_module', 'alignment_module', 'guide_module', 'frame_structural'}
_READ_ONLY_OPERATORS = {
    'dsg.analyze_geodesic_frame_fem',
    'dsg.estimate_geodesic_contact',
    'dsg.analyze_geodesic_groups',
    'dsg.inspect_final_boolean_section',
    'dsg.inspect_final_boolean_path',
}
_EXTERNAL_OPERATORS = {'dsg_suite.install_engines_core', 'dsg.install_dicom_runtime',
 'dsg.copy_pipeline_diagnostic',
 'dsg.install_ai_runtime', 'dsg.ai_status_refresh', 'dicp.back_to_alignment',
 'dicom_wizard_pro.undo_last', 'dicom_wizard_pro.export_surface_stl', 'dsg.export_guide_stl'}


def prepare_operators(modules):
    for module in modules:
        classes = getattr(module, 'CLASSES', None)
        if classes is None:
            classes = getattr(module,'_CLASSES',())
        for cls in classes:
            if not isinstance(cls, type) or not issubclass(cls, bpy.types.Operator):
                continue
            options = set(getattr(cls, 'bl_options', ()))
            workflow = module.__name__.rsplit('.', 1)[-1] in _WORKFLOW_MODULES
            if cls.bl_idname in _EXTERNAL_OPERATORS or cls.bl_idname in _READ_ONLY_OPERATORS:
                continue
            if workflow or cls.bl_idname in _EXTRA_UNDO:
                options.add('UNDO')
                cls.bl_options = options
            if 'UNDO' not in options or cls.__dict__.get('_dsg_history_wrapped', False):
                continue
            execute = cls.__dict__.get('execute')
            invoke = cls.__dict__.get('invoke')
            modal = cls.__dict__.get('modal')
            if execute is not None:
                cls.execute = _wrap_execute(execute)
            if invoke is not None:
                cls.invoke = _wrap_invoke(invoke)
            if modal is not None:
                cls.modal = _wrap_modal(modal)
            cls._dsg_history_wrapped = True


_HANDLERS = (('undo_pre', _before_undo), ('undo_post', _after_undo), ('redo_pre', _before_undo),
             ('redo_post', _after_undo), ('load_pre', _before_undo), ('load_post', _after_load))


def register():
    for name, handler in _HANDLERS:
        group = getattr(bpy.app.handlers, name)
        if handler not in group:
            group.insert(0, handler)


def unregister():
    for name, handler in _HANDLERS:
        group = getattr(bpy.app.handlers, name)
        if handler in group:
            group.remove(handler)
    _ACTIVE_MODALS.clear()
