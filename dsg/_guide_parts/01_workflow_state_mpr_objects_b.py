def _capture_implant_step_return_state(context, props):
    """Arm restoration before leaving implant planning for the contour step."""
    scene = getattr(context, 'scene', None)
    if scene is None:
        return None
    active = getattr(getattr(context, 'view_layer', None), 'objects', None)
    active = getattr(active, 'active', None) if active is not None else None
    active_name = _safe_object_name(active) or ''
    active_implant_name = ''
    if is_valid_implant_obj(active):
        active_implant_name = active_name
    elif _valid_obj(active):
        try:
            active_implant_name = str(active.get('DSG_implant_name', '') or '')
        except Exception:
            active_implant_name = ''
    if not active_implant_name and is_valid_implant_obj(getattr(props, 'implant_obj', None)):
        active_implant_name = str(props.implant_obj.name)

    try:
        selected_names = [obj.name for obj in context.selected_objects if _valid_obj(obj)]
    except Exception:
        selected_names = []
    state = {
        'scene_name': str(scene.name),
        'armed': True,
        'captured_at': float(time.monotonic()),
        'active_object_name': active_name,
        'active_implant_name': active_implant_name,
        'selected_names': selected_names,
        'had_emergence_controls': bool(get_implant_emergence_tubes()),
        'view_state': _capture_active_view3d_state(context),
        'mpr_target_implant': str(getattr(props, 'mpr_target_implant', '') or ''),
    }
    _IMPLANT_STEP_RETURN_STATE[str(scene.name)] = state
    return state


def _restore_implant_planning_state(context, scene, state=None):
    """Rebuild the visible step-2 state after Back/Ctrl+Z or DICOM exit."""
    if scene is None or getattr(context, 'scene', None) != scene:
        return False
    props = getattr(scene, 'dsg_props', None)
    if props is None or int(getattr(props, 'current_step', STEP_MODEL)) != STEP_IMPLANT:
        return False
    state = state if isinstance(state, dict) else _IMPLANT_STEP_RETURN_STATE.get(str(scene.name), {})

    # Step 2 is always the normal material-planning view. DICOM can be reopened
    # explicitly, but returning from step 3 must not leave the user trapped in
    # radiographic mode or in Solid shading.
    if _dicom_review_is_active(context):
        _close_dicom_review_for_guide(context)
    else:
        _hide_dicom_objects(context)
        _set_dicom_measurements_visibility(False)
    _set_material_preview_guide_view(context)
    _restore_active_view3d_state(context, state.get('view_state', {}))
    _set_material_preview_guide_view(context)
    _workflow_hide_known_stage_objects()
    _set_retention_boundary_visible(False)

    passive = get_passive_model_obj()
    source = getattr(props, 'model_obj', None)
    if _valid_obj(passive):
        _set_obj_hidden(passive, False, selectable_when_visible=True)
        if _valid_obj(source) and source != passive:
            _set_obj_hidden(source, True)
    elif _valid_obj(source):
        _set_obj_hidden(source, False, selectable_when_visible=True)

    implants = get_all_implant_objects(props)
    controllers = []
    for index, implant in enumerate(implants, start=1):
        try:
            implant.hide_viewport = False
            implant.hide_render = False
            implant.hide_set(False)
            implant.show_in_front = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        controller = create_implant_emergence_tube(
            context, props, implant, index=index)
        if _valid_obj(controller):
            controllers.append(controller)
    if implants:
        rebuild_implant_safety_halos(context, props)

    target = None
    active_implant_name = str(state.get('active_implant_name', '') or '')
    if active_implant_name:
        target_implant = bpy.data.objects.get(active_implant_name)
        if is_valid_implant_obj(target_implant):
            target = _get_emergence_controller_for_implant(target_implant) or target_implant
            props.implant_obj = target_implant
    if not _valid_obj(target):
        active_name = str(state.get('active_object_name', '') or '')
        candidate = bpy.data.objects.get(active_name) if active_name else None
        target = candidate if _valid_obj(candidate) else (controllers[0] if controllers else (implants[-1] if implants else passive))
    if _valid_obj(target):
        set_active(context, target)

    props.drawing_active = False
    props.irr_drawing_active = False
    _tag_dsg_view3d_redraw()
    return True


def _schedule_implant_planning_state_restore(scene, *, require_armed=False, delay=0.04):
    if scene is None:
        return False
    scene_name = str(scene.name)
    if scene_name in _IMPLANT_STEP_RESTORE_PENDING:
        return True
    _IMPLANT_STEP_RESTORE_PENDING.add(scene_name)

    def _restore_timer():
        try:
            target_scene = bpy.data.scenes.get(scene_name)
            state = _IMPLANT_STEP_RETURN_STATE.get(scene_name, {})
            if target_scene is None:
                return None
            props = getattr(target_scene, 'dsg_props', None)
            if props is None or int(getattr(props, 'current_step', STEP_MODEL)) != STEP_IMPLANT:
                return None
            if require_armed and not bool(state.get('armed', False)):
                return None
            restored = _restore_implant_planning_state(bpy.context, target_scene, state)
            if restored and isinstance(state, dict):
                state['armed'] = False
                state['restored_at'] = float(time.monotonic())
        except Exception as exc:
            print(f'[DSG] Implant-step restoration warning: {exc}')
        finally:
            _IMPLANT_STEP_RESTORE_PENDING.discard(scene_name)
        return None

    try:
        lifecycle.register_timer(_restore_timer, first_interval=max(0.01, float(delay)))
        return True
    except Exception:
        _IMPLANT_STEP_RESTORE_PENDING.discard(scene_name)
        return False


@persistent
def _dsg_restore_implant_step_after_undo(_dummy=None):
    """Undo-post bridge for the complete DSG state machine.

    Blender restores datablocks but not every viewport/controller state.  After
    Ctrl+Z, clamp the visible step to the highest stage whose tangible
    prerequisites still exist, then rebuild that stage deterministically.
    """
    try:
        for scene in list(bpy.data.scenes):
            props = getattr(scene, 'dsg_props', None)
            if props is None:
                continue
            _reconcile_workflow_after_undo(scene)
    except Exception as exc:
        print(f'[DSG] Undo workflow reconciliation warning: {exc}')


def _remove_implant_navigation_restore_handler():
    try:
        for handler in list(bpy.app.handlers.undo_post):
            if getattr(handler, '__name__', '') == '_dsg_restore_implant_step_after_undo':
                bpy.app.handlers.undo_post.remove(handler)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _register_implant_navigation_restore_handler():
    _remove_implant_navigation_restore_handler()
    try:
        bpy.app.handlers.undo_post.append(_dsg_restore_implant_step_after_undo)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

def _dicom_review_is_active(context):
    props = getattr(context.scene, 'dicom_wizard_pro', None)
    return props is not None and bool(props.get('safe_mpr_active', False))


def _close_dicom_review_for_guide(context):
    if _dicom_review_is_active(context):
        try:
            bpy.ops.dicom_wizard_pro.close_safe_mpr()
        except Exception as exc:
            print(f'[DSG] Could not close DICOM review: {exc}')
    _hide_dicom_objects(context)
    _set_dicom_measurements_visibility(False)
    _set_material_preview_guide_view(context)


class DSG_OT_SelectMPRImplant(Operator):
    bl_idname = 'dsg.select_mpr_implant'
    bl_label = 'Select Implant for MPR'
    bl_description = 'Uses the implant selected in the 3D scene as the DICOM review target'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        active = getattr(getattr(context, 'view_layer', None), 'objects', None)
        active = getattr(active, 'active', None) if active is not None else None
        implant = active if is_valid_implant_obj(active) else None
        if implant is None and _valid_obj(active):
            linked = str(active.get('DSG_implant_name', '') or '')
            linked_obj = bpy.data.objects.get(linked) if linked else None
            implant = linked_obj if is_valid_implant_obj(linked_obj) else None
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'WARNING'}, 'Select an implant first', 'Selecciona primero un implante')
            return {'CANCELLED'}
        props.mpr_target_implant = str(implant.name)
        try:
            bpy.ops.object.select_all(action='DESELECT')
            implant.hide_set(False)
            implant.select_set(True)
            context.view_layer.objects.active = implant
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if _dicom_review_is_active(context):
            ok, message = _center_two_plane_mpr_on_implant(context, implant)
            if not ok:
                _dsg_report(self, {'ERROR'}, message, message)
                return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, f'Selected for MPR: {implant.name}', f'Seleccionado para MPR: {implant.name}')
        return {'FINISHED'}


class DSG_OT_OpenOrCenterImplantMPR(Operator):
    bl_idname = 'dsg.open_or_center_implant_mpr'
    bl_label = 'Implant MPR'
    bl_description = 'Moves the horizontal cut to the implant and rotates the vertical cut around the DICOM centre'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        implant = _resolve_mpr_target_implant(context, props)
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'WARNING'}, 'Select an implant first', 'Selecciona primero un implante')
            return {'CANCELLED'}
        props.mpr_target_implant = str(implant.name)
        _ensure_mpr_target_visible(context, implant)
        if not _dicom_review_is_active(context):
            result = bpy.ops.dsg.open_dicom_review()
            if 'CANCELLED' in result:
                return {'CANCELLED'}
        _ensure_mpr_target_visible(context, implant)
        ok, message = _center_two_plane_mpr_on_implant(context, implant)
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, f'MPR oriented through {implant.name}', f'MPR orientado hacia {implant.name}')
        return {'FINISHED'}


class DSG_OT_CenterSelectedMicroscrewMPR(Operator):
    bl_idname = 'dsg.center_selected_microscrew_mpr'
    bl_label = 'Center Microscrew MPR'
    bl_description = 'Centers DICOM review on the selected microscrew and aligns MPR Z with its local Z axis'
    bl_options = {'REGISTER'}

    def execute(self, context):
        microscrew = _selected_mpr_microscrew(context)
        if not _is_valid_mpr_microscrew(microscrew):
            _dsg_report(self, {'WARNING'}, 'Select a microscrew first', 'Selecciona primero un microtornillo')
            return {'CANCELLED'}
        ok, message = _center_two_plane_mpr_on_microscrew(context, microscrew)
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
            return {'CANCELLED'}
        _dsg_report(
            self, {'INFO'},
            f'MPR centred on {microscrew.name}',
            f'MPR centrado en {microscrew.name}')
        return {'FINISHED'}


class DSG_OT_OpenOrCenterMicroscrewMPR(Operator):
    bl_idname = 'dsg.open_or_center_microscrew_mpr'
    bl_label = 'Microscrew MPR'
    bl_description = 'Opens DICOM review centred on the selected microscrew and aligned to its local Z axis'
    bl_options = {'REGISTER'}

    def execute(self, context):
        microscrew = _selected_mpr_microscrew(context)
        if not _is_valid_mpr_microscrew(microscrew):
            _dsg_report(self, {'WARNING'}, 'Select a microscrew first', 'Selecciona primero un microtornillo')
            return {'CANCELLED'}
        _ensure_mpr_target_visible(context, microscrew)
        if not _dicom_review_is_active(context):
            result = bpy.ops.dsg.open_dicom_review()
            if 'CANCELLED' in result:
                return {'CANCELLED'}
        _ensure_mpr_target_visible(context, microscrew)
        ok, message = _center_two_plane_mpr_on_microscrew(context, microscrew)
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
            return {'CANCELLED'}
        _dsg_report(
            self, {'INFO'},
            f'MPR centred and aligned to {microscrew.name}',
            f'MPR centrado y alineado con {microscrew.name}')
        return {'FINISHED'}


class DSG_OT_OpenDICOMReview(Operator):
    bl_idname = 'dsg.open_dicom_review'
    bl_label = 'Review DICOM'
    bl_description = 'Opens the final DICOM plane review without leaving the implant step'
    bl_options = {'REGISTER'}

    def execute(self, context):
        dicom_props = getattr(context.scene, 'dicom_wizard_pro', None)
        if dicom_props is None:
            _dsg_report(self, {'ERROR'}, 'DICOM module is unavailable', 'El módulo DICOM no está disponible')
            return {'CANCELLED'}
        if not bool(getattr(dicom_props, 'volume_loaded', False)):
            _dsg_report(self, {'ERROR'}, 'Load the DICOM first', 'Carga primero el DICOM')
            return {'CANCELLED'}
        # MPR is resampled directly from the loaded DICOM voxels. An STL is
        # optional 3D context and must never gate implant/microscrew review.
        try:
            from . import dicom_module as _dicom
            _dicom._resolve_or_recover_mpr_surface(context, mutate_state=True)
        except Exception as exc:
            print('[DSG MPR] optional surface recovery warning:', repr(exc))
        _show_dicom_objects(context)
        _set_dicom_measurements_visibility(True)
        dicom_props.step = 4
        try:
            result = bpy.ops.dicom_wizard_pro.radiographic_quad_view('INVOKE_DEFAULT')
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not open DICOM review: {exc}', f'No se pudo abrir la revisión DICOM: {exc}')
            return {'CANCELLED'}
        if 'CANCELLED' in result:
            _dsg_report(self, {'ERROR'}, 'DICOM review could not be opened', 'No se pudo abrir la revisión DICOM')
            return {'CANCELLED'}

        # Keep planned hardware visible even if an earlier workflow step hid
        # its object, parent or collection.
        try:
            active = getattr(context.view_layer.objects, 'active', None)
            target = active if (is_valid_implant_obj(active) or _is_valid_mpr_microscrew(active)) else None
            if target is None:
                target = _resolve_mpr_target_implant(context, context.scene.dsg_props)
            if target is None:
                target = _selected_mpr_microscrew(context)
            if target is not None:
                _ensure_mpr_target_visible(context, target)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        # DICOM's safe review normally hides the N sidebar to maximize image
        # space.  When review is launched from the implant step, keep that
        # sidebar open so the DSG controls (Z position, Z inclination, implants
        # and Next) remain visible and usable.
        try:
            area = getattr(context, 'area', None)
            if area is not None and area.type == 'VIEW_3D':
                area.spaces.active.show_region_ui = True
                area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            dicom_props['safe_mpr_keep_sidebar_for_dsg'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return {'FINISHED'}


class DSG_OT_CloseDICOMReview(Operator):
    bl_idname = 'dsg.close_dicom_review'
    bl_label = 'Close DICOM Review'
    bl_options = {'REGISTER'}

    def execute(self, context):
        _close_dicom_review_for_guide(context)
        props = getattr(context.scene, 'dsg_props', None)
        if props is not None and int(getattr(props, 'current_step', STEP_MODEL)) == STEP_IMPLANT:
            _schedule_implant_planning_state_restore(
                context.scene, require_armed=False, delay=0.02)
        return {'FINISHED'}


def ensure_dsg_root_collection():
    """Crea/recupera la colección raíz DSG sin tocar colecciones del usuario."""
    root = bpy.data.collections.get(DSG_ROOT_COLLECTION_NAME)
    if root is None:
        root = bpy.data.collections.new(DSG_ROOT_COLLECTION_NAME)
        try:
            bpy.context.scene.collection.children.link(root)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return root


def ensure_dsg_collection(collection_name):
    """Crea/recupera una subcolección DSG para ordenar la escena automáticamente."""
    root = ensure_dsg_root_collection()
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        coll = bpy.data.collections.new(collection_name)
    try:
        if coll.name not in root.children:
            root.children.link(coll)
    except Exception:
        # En algunos casos Blender no permite comparar por nombre de forma directa.
        try:
            if coll.name not in [c.name for c in root.children]:
                root.children.link(coll)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return coll


def unlink_object_from_dsg_collections(obj):
    """Desenlaza un objeto conservado por el usuario de las colecciones internas DSG."""
    if not _valid_obj(obj):
        return
    root = bpy.data.collections.get(DSG_ROOT_COLLECTION_NAME)
    if root is None:
        return
    for child in list(root.children):
        try:
            if obj.name in child.objects:
                child.objects.unlink(obj)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def cleanup_empty_dsg_collections(remove_root_if_empty=True):
    """Elimina subcolecciones DSG vacías y, opcionalmente, la raíz si queda vacía."""
    root = bpy.data.collections.get(DSG_ROOT_COLLECTION_NAME)
    if root is None:
        return 0
    removed = 0
    for child in list(root.children):
        try:
            is_empty = len(child.objects) == 0 and len(child.children) == 0
        except Exception:
            is_empty = False
        if not is_empty:
            continue
        try:
            root.children.unlink(child)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bpy.data.collections.remove(child)
            removed += 1
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if remove_root_if_empty:
        try:
            root_empty = len(root.objects) == 0 and len(root.children) == 0
        except Exception:
            root_empty = False
        if root_empty:
            try:
                for parent in list(root.users_scene):
                    parent.collection.children.unlink(root)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                bpy.data.collections.remove(root)
                removed += 1
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed


def get_dsg_collection_name_for_role(role):
    return ROLE_TO_COLLECTION.get(role, DSG_COLLECTION_GUIDE)


def link_object_to_dsg_collection(obj, role):
    """Enlaza el objeto a su colección DSG sin deshacer colecciones del usuario.

    Solo se elimina de otras subcolecciones DSG para evitar duplicados internos.
    Si el objeto ya estaba en una colección propia del usuario, se conserva.
    """
    if not _valid_obj(obj):
        return obj
    coll_name = get_dsg_collection_name_for_role(role)
    target = ensure_dsg_collection(coll_name)
    try:
        if obj.name not in target.objects:
            target.objects.link(obj)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    root = bpy.data.collections.get(DSG_ROOT_COLLECTION_NAME)
    if root:
        try:
            for child in root.children:
                if child == target:
                    continue
                if obj.name in child.objects:
                    child.objects.unlink(obj)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj



def register_dsg_object(obj, role, locked_name=None, extra=None):
    """Registra un objeto sin depender de PointerProperty persistente ni roles.

    La identidad se basa en nombres canónicos, prefijos y colecciones DSG. Solo
    se conservan metadatos clínicos explícitos de ``extra`` (por ejemplo, el
    implante asociado a una irrigación), no una capa paralela de roles.
    """
    if not _valid_obj(obj):
        return obj
    if locked_name:
        try:
            obj.name = str(locked_name)
            if getattr(obj, 'data', None) is not None and role != ROLE_MODEL:
                obj.data.name = str(locked_name) + '_Mesh'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if extra:
        try:
            for key, value in extra.items():
                obj[str(key)] = value
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        obj['dental_suite_dsg_role'] = str(role)
        obj['dental_suite_component'] = 'DSG'
        data_block = getattr(obj, 'data', None)
        if data_block is not None and role != ROLE_MODEL:
            try:
                data_block['DSG_owned_data'] = True
                data_block['DSG_owner_object'] = str(obj.name)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if role == ROLE_GUIDE:
            _set_suite_role(obj, ROLE_DSG_GUIDE_SUITE)
            store_guide_home_matrix(obj, force=False)
        elif role == ROLE_MODEL and _suite_role(obj) not in {ROLE_IOS_ALIGNED_SUITE, ROLE_IOS_SCAN_SUITE}:
            _set_suite_role(obj, ROLE_DSG_MODEL_SUITE)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    link_object_to_dsg_collection(obj, role)
    return obj




# ─────────────────────────────────────────────────────────────
# Protección transversal contra botones repetidos y duplicados
# ─────────────────────────────────────────────────────────────

_DSG_ACTION_RUNTIME = {}
_DSG_ACTION_GUARDS_INSTALLED = False
_DSG_OWNED_DATA_CLEANUP_PENDING = False

# Solo acciones que escriben o reconstruyen geometría. Las herramientas de
# navegación, reproducción y visibilidad siguen respondiendo sin retardo.
_DSG_WRITE_ACTION_COOLDOWNS = {
    'dsg.prepare_aligned_model': 1.25,
    'dsg.generate_blockout': 1.25,
    'dsg.confirm_blockout': 0.80,
    'dsg.confirm_contour': 0.80,
    'dsg.create_implant': 0.70,
    'dsg.create_implant_emergence_tubes': 1.00,
    'dsg.confirm_implant': 0.80,
    'dsg.build_tube_frame': 1.50,
    'dsg.confirm_microscrew_preview': 0.80,
    'dsg.apply_microscrews_to_frame': 1.50,
    'dsg.create_animated_microscrews': 1.00,
    'dsg.add_sleeve': 1.50,
    'dsg.apply_sleeves': 1.75,
    'dsg.create_apply_sleeves': 2.00,
    'dsg.protect_drill_insertion': 1.75,
    'dsg.add_drill_channel': 2.00,
    'dsg.prepare_and_create_drill_channels': 2.00,
    'dsg.confirm_irrigation_preview': 0.80,
    'dsg.update_confirm_irrigation': 1.00,
    'dsg.link_irrigation': 1.00,
    'dsg.confirm_irrigation': 1.50,
    'dsg.start_reinforcement': 0.70,
    'dsg.confirm_reinforcement_preview': 0.80,
    'dsg.apply_reinforcements': 1.50,
    'dsg.create_animated_drills': 1.00,
    'dsg.create_sequential_insertion_animation': 1.00,
    'dsg.update_final_animation': 1.00,
    'dsg.clean_guide_islands': 1.50,
}

_DSG_SINGLETON_OBJECT_NAMES = (
    AXIS_EMPTY_NAME, BLOCKOUT_NAME, BLOCKOUT_CANDIDATE_NAME, BLOCKOUT_VISUAL_NAME, COMBINED_NAME, COMBINED_CANDIDATE_NAME, FRAME_NAME, GUIDE_NAME,
    GUIDE_BUILD_TMP_NAME, MICROSCREW_PREVIEW_NAME, MICROSCREW_MARKER_NAME,
    MICROSCREW_FRAME_COMBINED_TMP_NAME, REINFORCEMENT_PREVIEW_NAME,
    REINFORCEMENT_MARKER_NAME, REINFORCEMENT_COMBINED_TMP_NAME,
    REINFORCEMENT_TUBE_TMP_NAME, REINFORCEMENT_CENTERLINE_TMP_NAME,
    ENGRAVE_ANCHOR_NAME, ENGRAVE_PREVIEW_NAME, ENGRAVE_CUTTER_NAME,
    DRILL_BATCH_CUTTER_NAME, DRILL_PROTECTION_RESULT_NAME,
    IRR_COMBINED_TMP_NAME, IRR_LUMEN_DIAGNOSTIC_NAME,
)


def _dsg_action_begin(operator_id):
    """Reject re-entrant and accidental rapid repeats of a write action."""
    now = time.monotonic()
    state = _DSG_ACTION_RUNTIME.setdefault(str(operator_id), {
        'busy': False, 'last_finish': -1.0e9,
    })
    cooldown = float(_DSG_WRITE_ACTION_COOLDOWNS.get(str(operator_id), 0.0))
    if bool(state.get('busy', False)):
        return False, 'busy'
    if cooldown > 0.0 and now - float(state.get('last_finish', -1.0e9)) < cooldown:
        return False, 'cooldown'
    state['busy'] = True
    state['started'] = now
    return True, ''


def _dsg_action_end(operator_id, result):
    state = _DSG_ACTION_RUNTIME.setdefault(str(operator_id), {})
    state['busy'] = False
    state['last_finish'] = time.monotonic()
    try:
        finished = result is not None and 'FINISHED' in result
    except Exception:
        finished = False
    if finished:
        _schedule_dsg_owned_data_cleanup()


def _make_dsg_guarded_execute(original_execute, operator_id):
    """Return a Blender-compatible execute callback with exactly two arguments.

    Blender validates operator callbacks from the Python function code object.
    Capturing values as default parameters would expose four positional arguments
    and prevent the addon from being enabled. A closure factory keeps the public
    callback signature strictly ``execute(self, context)``.
    """
    def guarded_execute(self, context):
        allowed, reason = _dsg_action_begin(operator_id)
        if not allowed:
            if reason == 'busy':
                _dsg_report(
                    self, {'WARNING'},
                    'This DSG action is already running',
                    'Esta acción DSG ya se está ejecutando')
            else:
                _dsg_report(
                    self, {'INFO'},
                    'Repeated click ignored; the previous action was already accepted',
                    'Clic repetido ignorado; la acción anterior ya fue aceptada')
            return {'CANCELLED'}
        result = {'CANCELLED'}
        try:
            result = original_execute(self, context)
            return result
        finally:
            _dsg_action_end(operator_id, result)

    guarded_execute.__name__ = getattr(original_execute, '__name__', 'execute')
    guarded_execute.__qualname__ = getattr(original_execute, '__qualname__', guarded_execute.__name__)
    guarded_execute.__doc__ = getattr(original_execute, '__doc__', None)
    guarded_execute._dsg_repeat_guard = True
    guarded_execute._dsg_original_execute = original_execute
    return guarded_execute


def _dsg_guard_operator_class(cls):
    """Wrap one operator once, without changing its clinical implementation."""
    operator_id = str(getattr(cls, 'bl_idname', '') or '')
    if operator_id not in _DSG_WRITE_ACTION_COOLDOWNS:
        return
    execute = getattr(cls, 'execute', None)
    if not callable(execute) or bool(getattr(execute, '_dsg_repeat_guard', False)):
        return
    cls.execute = _make_dsg_guarded_execute(execute, operator_id)


def _install_dsg_action_guards():
    global _DSG_ACTION_GUARDS_INSTALLED
    if _DSG_ACTION_GUARDS_INSTALLED:
        return
    for cls in CLASSES:
        _dsg_guard_operator_class(cls)
    _DSG_ACTION_GUARDS_INSTALLED = True


def _is_numeric_duplicate_name(name, base):
    if not str(name).startswith(str(base) + '.'):
        return False
    suffix = str(name)[len(str(base)) + 1:]
    return len(suffix) == 3 and suffix.isdigit()


def _cleanup_dsg_singleton_duplicates():
    """Remove only accidental .001 copies of objects that must be singletons."""
    if not _dsg_data_access_ready():
        return 0
    removed = 0
    _prepare_outliner_for_dsg_id_changes(bpy.context)
    for base in _DSG_SINGLETON_OBJECT_NAMES:
        exact = bpy.data.objects.get(base)
        copies = [
            obj for obj in list(bpy.data.objects)
            if _valid_obj(obj) and _is_numeric_duplicate_name(obj.name, base)
        ]
        # If no exact object exists, preserve the first live copy by restoring the
        # canonical name, then remove only the remaining accidental copies.
        if exact is None and copies:
            copies.sort(key=lambda obj: obj.name)
            exact = copies.pop(0)
            try:
                exact.name = base
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        for duplicate in copies:
            try:
                if duplicate is exact:
                    continue
                removed += int(safe_remove_object_with_data(duplicate))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed


def _cleanup_dsg_owned_orphan_data():
    """Purge only zero-user datablocks explicitly marked as DSG-owned."""
    if not _dsg_data_access_ready():
        return 0
    removed = 0
    data_groups = (
        getattr(bpy.data, 'meshes', ()),
        getattr(bpy.data, 'curves', ()),
        getattr(bpy.data, 'materials', ()),
        getattr(bpy.data, 'actions', ()),
    )
    for group in data_groups:
        for data_block in list(group):
            try:
                if int(getattr(data_block, 'users', 1)) != 0:
                    continue
                marked = bool(data_block.get('DSG_owned_data', False))
                by_name = str(getattr(data_block, 'name', '')).startswith('DSG_')
                if not (marked or by_name):
                    continue
                group.remove(data_block)
                removed += 1
            except (ReferenceError, RuntimeError):
                continue
            except Exception:
                continue
    try:
        cleanup_empty_dsg_collections(remove_root_if_empty=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed


def _dsg_owned_data_cleanup_timer():
    global _DSG_OWNED_DATA_CLEANUP_PENDING
    if any(bool(state.get('busy', False)) for state in _DSG_ACTION_RUNTIME.values()):
        return 0.50
    _DSG_OWNED_DATA_CLEANUP_PENDING = False
    try:
        _cleanup_dsg_singleton_duplicates()
        _cleanup_dsg_owned_orphan_data()
    except Exception as exc:
        print('[DSG] Deferred duplicate cleanup warning:', repr(exc))
    return None


def _schedule_dsg_owned_data_cleanup():
    global _DSG_OWNED_DATA_CLEANUP_PENDING
    if _DSG_OWNED_DATA_CLEANUP_PENDING or not lifecycle.is_active():
        return
    _DSG_OWNED_DATA_CLEANUP_PENDING = True
    try:
        lifecycle.unregister_timer(_dsg_owned_data_cleanup_timer)
        lifecycle.register_timer(_dsg_owned_data_cleanup_timer, first_interval=0.75)
    except Exception:
        _DSG_OWNED_DATA_CLEANUP_PENDING = False


def _rounded_matrix_signature(matrix, digits=5):
    try:
        return tuple(round(float(value), digits) for row in matrix for value in row)
    except Exception:
        return ()


def _current_sleeve_build_signature(props, implants=None, frame=None):
    implants = implants if implants is not None else get_all_implant_objects(props)
    frame = frame if frame is not None else _recover_frame_source_for_sleeve_rebuild(props)
    payload = {
        'frame': _safe_object_name(frame) or '',
        'frame_matrix': _rounded_matrix_signature(frame.matrix_world) if _valid_obj(frame) else (),
        'inner_radius': round(float(_sleeve_inner_radius_from_props(props)), 5),
        'wall': round(float(props.sleeve_wall), 5),
        'height': round(float(props.sleeve_height), 5),
        'segments': int(getattr(props, 'sleeve_segments', 32)),
        # Lateral access is a POST-IRRIGATION Boolean in v8.4.3 and therefore
        # must never invalidate/rebuild the closed sleeve source geometry.
        'lateral_opening_stage': 'POST_IRRIGATION',
        'implants': [
            (_safe_object_name(implant) or '', _rounded_matrix_signature(implant.matrix_world))
            for implant in implants if is_valid_implant_obj(implant)
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _sleeve_dimensions_from_props(props):
    """Return the three user-configurable sleeve dimensions in millimetres."""
    return (
        round(float(getattr(props, 'sleeve_inner_diameter', 4.7)), 5),
        round(float(getattr(props, 'sleeve_wall', 1.5)), 5),
        round(float(getattr(props, 'sleeve_height', 7.0)), 5),
    )


def _sleeve_dimensions_from_guide(guide):
    """Read dimensions stored on a generated guide, including migrated scenes."""
    if not _valid_obj(guide):
        return None
    try:
        explicit = (
            guide.get('DSG_sleeve_inner_diameter_mm', None),
            guide.get('DSG_sleeve_wall_mm', None),
            guide.get('DSG_sleeve_height_mm', None),
        )
        if all(value is not None for value in explicit):
            return tuple(round(float(value), 5) for value in explicit)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        raw = str(guide.get('DSG_sleeve_build_signature', '') or '')
        payload = json.loads(raw) if raw else {}
        if all(key in payload for key in ('inner_radius', 'wall', 'height')):
            return (
                round(float(payload['inner_radius']) * 2.0, 5),
                round(float(payload['wall']), 5),
                round(float(payload['height']), 5),
            )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return None


def _sleeve_dimensions_match_guide(props, guide, tolerance=1e-4):
    stored = _sleeve_dimensions_from_guide(guide)
    if stored is None:
        return False
    current = _sleeve_dimensions_from_props(props)
    return all(
        abs(float(a) - float(b)) <= float(tolerance)
        for a, b in zip(current, stored)
    )


def _safe_object_name(obj):
    """Devuelve el nombre solo cuando el StructRNA sigue vivo."""
    if obj is None:
        return None
    try:
        # as_pointer() falla de forma fiable cuando Blender ya invalidó el RNA.
        if not obj.as_pointer():
            return None
        return str(obj.name)
    except (ReferenceError, RuntimeError, AttributeError):
        return None
    except Exception:
        return None


def _valid_obj(obj):
    """Comprueba un Object de Blender sin tocar propiedades de un RNA eliminado."""
    name = _safe_object_name(obj)
    if not name:
        return False
    try:
        live = bpy.data.objects.get(name)
        if live is None:
            return False
        return live.as_pointer() == obj.as_pointer()
    except (ReferenceError, RuntimeError, AttributeError):
        return False
    except Exception:
        return False



def _inherit_dsg_custom_properties(source_obj, target_obj, exclude_keys=None):
    """Copy DSG custom properties when a guide object is rebuilt.

    Several clinical stages replace ``DSG_Guide`` with a newly assembled mesh.
    Blender custom properties do not follow that geometry automatically. Losing
    ``DSG_sleeves_applied`` or the stored sleeve dimensions makes later workflow
    validation incorrectly send the user back to the sleeve step. This helper
    copies only DSG-owned metadata and never touches transforms or mesh data.
    """
    if not (_valid_obj(source_obj) and _valid_obj(target_obj)):
        return 0
    excluded = {str(key) for key in (exclude_keys or ())}
    copied = 0
    try:
        keys = list(source_obj.keys())
    except Exception:
        keys = []
    for raw_key in keys:
        key = str(raw_key)
        if key in excluded or not key.startswith('DSG_'):
            continue
        try:
            target_obj[key] = source_obj[key]
            copied += 1
        except Exception:
            # A malformed legacy IDProperty must not abort a geometric commit.
            continue
    return copied


def _guide_has_downstream_sleeve_evidence(guide):
    """Return True when a guide can only have originated after sleeve creation."""
    if not _valid_obj(guide):
        return False
    evidence_keys = (
        'DSG_irrigation_mode',
        'DSG_irrigation_resolution',
        'DSG_irrigation_skipped',
        'DSG_irrigation_cut_count',
        'DSG_reinforcement_resolution',
        'DSG_reinforcement_skipped',
        'DSG_reinforcement_count',
        'DSG_drill_insertion_protected',
        'DSG_drill_channel_count',
        'DSG_final_cut_completed',
        'DSG_final_pipeline',
    )
    for key in evidence_keys:
        try:
            value = guide.get(key, None)
            if isinstance(value, str):
                if value:
                    return True
            elif bool(value):
                return True
        except Exception:
            continue
    try:
        return any(
            _valid_obj(obj) and str(obj.name).startswith(SLEEVE_SOURCE_PREFIX)
            for obj in bpy.data.objects
        )
    except Exception:
        return False


def _restore_sleeve_metadata_if_derivable(props, guide):
    """Repair scenes whose rebuilt guide lost sleeve metadata.

    Metadata is restored only when downstream irrigation/reinforcement/drill data
    or retained hidden sleeve sources prove that sleeves had already been made.
    """
    if not _valid_obj(guide):
        return False
    try:
        if bool(guide.get('DSG_sleeves_applied', False)):
            return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if not _guide_has_downstream_sleeve_evidence(guide):
        return False

    stored_dimensions = None
    try:
        for obj in bpy.data.objects:
            if not (_valid_obj(obj) and str(obj.name).startswith(SLEEVE_SOURCE_PREFIX)):
                continue
            stored_dimensions = _sleeve_dimensions_from_guide(obj)
            if stored_dimensions is not None:
                break
    except Exception:
        stored_dimensions = None
    if stored_dimensions is None:
        stored_dimensions = _sleeve_dimensions_from_props(props)

    try:
        guide['DSG_sleeves_applied'] = True
        guide['DSG_sleeve_inner_diameter_mm'] = float(stored_dimensions[0])
        guide['DSG_sleeve_wall_mm'] = float(stored_dimensions[1])
        guide['DSG_sleeve_height_mm'] = float(stored_dimensions[2])
        guide['DSG_sleeve_metadata_recovered'] = True
        return True
    except Exception:
        return False


def find_dsg_objects(role=None, exact_name=None, prefix=None, obj_type=None):
    """Busca por nombre, prefijo o colección; no usa propiedades DSG_role."""
    out = []

    def add(obj):
        if not _valid_obj(obj):
            return
        if obj_type and obj.type != obj_type:
            return
        if obj not in out:
            out.append(obj)

    if exact_name:
        add(bpy.data.objects.get(exact_name))

    role_exact = {
        ROLE_BLOCKOUT: BLOCKOUT_NAME,
        ROLE_BLOCKOUT_VISUAL: BLOCKOUT_VISUAL_NAME,
        ROLE_PASSIVE: COMBINED_NAME,
        ROLE_FRAME: FRAME_NAME,
        ROLE_GUIDE: GUIDE_NAME,
        ROLE_ENGRAVE: ENGRAVE_PREVIEW_NAME,
    }
    role_prefix = {
        ROLE_IMPLANT: IMPLANT_PREFIX + '_',
        ROLE_SLEEVE: SLEEVE_PREFIX + '_',
        ROLE_IRRIGATION: 'DSG_Irr_',
        ROLE_DRILL_CUTTER: DRILL_PREFIX,
        ROLE_DRILL_VISUAL: ANIMATED_DRILL_PREFIX,
        ROLE_MICROSCREW_VISUAL: ANIMATED_MICROSCREW_PREFIX,
    }

    if role and not exact_name and role in role_exact:
        add(bpy.data.objects.get(role_exact[role]))
    effective_prefix = prefix or (role_prefix.get(role) if role else None)
    if effective_prefix:
        for obj in bpy.data.objects:
            if obj.name.startswith(effective_prefix):
                add(obj)

    # Para roles sin nombre inequívoco, la colección DSG es la fuente de verdad.
    if role and role not in role_exact and role not in role_prefix and role != ROLE_MODEL:
        coll = bpy.data.collections.get(get_dsg_collection_name_for_role(role))
        if coll:
            for obj in coll.objects:
                add(obj)

    return out


def get_primary_dsg_object(props, prop_name=None, role=None, exact_name=None, prefix=None, obj_type=None):
    """Resuelve primero el nombre fijo y después el puntero actual como fallback."""
    if exact_name:
        obj = bpy.data.objects.get(exact_name)
        if _valid_obj(obj) and (obj_type is None or obj.type == obj_type):
            return obj
    if prefix:
        matches = find_dsg_objects(prefix=prefix, obj_type=obj_type)
        if matches:
            return matches[0]
    if props is not None and prop_name:
        obj = getattr(props, prop_name, None)
        if _valid_obj(obj) and (obj_type is None or obj.type == obj_type):
            return obj
    matches = find_dsg_objects(role=role, obj_type=obj_type) if role else []
    return matches[0] if matches else None


def repair_core_object_pointers(props):
    """Sincroniza solo los objetos únicos mediante sus nombres canónicos."""
    if props is None:
        return
    frame = bpy.data.objects.get(FRAME_NAME)
    guide = bpy.data.objects.get(GUIDE_NAME)
    passive = bpy.data.objects.get(COMBINED_NAME)
    if _valid_obj(frame) and frame.type == 'MESH':
        props.frame_obj = frame
    if _valid_obj(guide) and guide.type == 'MESH':
        props.guide_obj = guide
        props.dct_object_being_cut = guide
    if _valid_obj(passive) and passive.type == 'MESH':
        props.dct_object_making_cut = passive



# ─────────────────────────────────────────────────────────────
# Helpers generales
# ─────────────────────────────────────────────────────────────

def _clear_scene_object_pointers(obj):
    """Borra PointerProperty que apunten a ``obj`` antes de eliminarlo.

    Blender 5.1 puede dejar un enlace inválido dentro del memfile de Undo cuando
    se elimina un Object que todavía está referenciado por un PropertyGroup de
    Scene. El fallo no siempre aparece al eliminarlo: suele manifestarse después
    al pulsar Ctrl+Z durante ``BKE_memfile_undo_decode``.
    """
    if not _valid_obj(obj):
        return
    pointer_names = (
        'model_obj', 'implant_obj', 'parallel_master_implant',
        'frame_obj', 'guide_obj', 'reinforcement_preview_obj',
        'microscrew_preview_obj', 'irr_preview_obj',
        'dct_object_being_cut', 'dct_object_making_cut',
    )
    for scene in list(getattr(bpy.data, 'scenes', ())):
        props = getattr(scene, 'dsg_props', None)
        if props is None:
            continue
        for attr in pointer_names:
            try:
                if getattr(props, attr, None) is obj:
                    setattr(props, attr, None)
            except (ReferenceError, RuntimeError, TypeError):
                pass
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _clear_id_animation_data(id_data):
    """Detach Actions, NLA tracks and drivers before a DSG ID is retired.

    Blender 5.0 can crash in the Outliner while expanding AnimData from an
    object that has just been replaced. Clearing the AnimData through the RNA
    API leaves the Action datablock alive and removes only the unsafe link.
    """
    if id_data is None:
        return False
    try:
        animation_data = getattr(id_data, 'animation_data', None)
    except (ReferenceError, RuntimeError):
        return False
    except Exception:
        animation_data = None
    if animation_data is None:
        return False
    try:
        clear_fn = getattr(id_data, 'animation_data_clear', None)
        if callable(clear_fn):
            clear_fn()
            return True
    except (ReferenceError, RuntimeError):
        return False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False


def _sanitize_dsg_object_for_id_change(obj):
    """Prepare a generated object before delete, archive, rename or replacement."""
    if not _valid_obj(obj):
        return False
    try:
        _clear_id_animation_data(obj)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        _clear_id_animation_data(getattr(obj, 'data', None))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        obj.select_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        view_layer = getattr(bpy.context, 'view_layer', None)
        if view_layer is not None and view_layer.objects.active is obj:
            view_layer.objects.active = None
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _prepare_outliner_for_dsg_id_changes(context):
    """Avoid Blender 5.0 expanding stale Object AnimData during DSG rebuilds.

    The Object Contents filter is not clinically useful in DSG and disabling it
    prevents the Outliner from traversing Actions/Drivers while generated IDs
    are being renamed or archived. The property is guarded for compatibility.
    """
    changed = 0
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in getattr(screen, 'areas', ()):
            if getattr(area, 'type', '') != 'OUTLINER':
                continue
            try:
                space = area.spaces.active
                if hasattr(space, 'use_filter_object_content'):
                    if bool(space.use_filter_object_content):
                        space.use_filter_object_content = False
                        changed += 1
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return changed


def _archive_transient_dsg_object(obj, reason='temporary_cleanup', prefix='DSG_Archived_'):
    """Hide a temporary object without invalidating its Blender ID.

    This is used for frequently rebuilt helpers such as emergence controllers
    and safety halos. Keeping the ID alive until Reset avoids stale Outliner and
    Undo references in Blender 5.0.
    """
    if not _valid_obj(obj):
        return False
    _sanitize_dsg_object_for_id_change(obj)
    try:
        obj['DSG_obsolete_hidden'] = True
        obj['DSG_archive_reason'] = str(reason)
        obj['DSG_archived_at'] = float(time.time())
        obj.hide_render = True
        obj.hide_select = True
        obj.hide_viewport = True
        obj.hide_set(True)
        safe_name = _safe_object_name(obj) or 'Object'
        obj.name = f'{prefix}{int(time.time() * 1000)}_{safe_name}'
        return True
    except Exception:
        return False


def _sanitize_static_dsg_geometry_animdata():
    """Remove obsolete animation links before static clinical geometry stages."""
    for obj in list(getattr(bpy.data, 'objects', ())):
        try:
            is_dsg = str(obj.get('dental_suite_component', '')) == 'DSG'
            by_name = str(obj.name).startswith('DSG_')
            is_animation_output = str(obj.name).startswith((
                ANIMATED_DRILL_PREFIX, ANIMATED_MICROSCREW_PREFIX,
            ))
        except Exception:
            continue
        if (is_dsg or by_name) and not is_animation_output:
            _sanitize_dsg_object_for_id_change(obj)


def safe_remove_object(obj):
    """Elimina un objeto vivo después de sanear referencias y AnimData."""
    name = _safe_object_name(obj)
    if not name:
        return False
    try:
        live_obj = bpy.data.objects.get(name)
        if live_obj is not None:
            _clear_scene_object_pointers(live_obj)
            _sanitize_dsg_object_for_id_change(live_obj)
            # Preserve child world transforms before retiring a parent helper.
            for child in list(getattr(live_obj, 'children', ())):
                try:
                    child_world = child.matrix_world.copy()
                    child.parent = None
                    child.matrix_world = child_world
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            bpy.data.objects.remove(live_obj, do_unlink=True)
            return True
    except (ReferenceError, RuntimeError):
        return False
    except Exception:
        return False
    return False


def safe_remove_by_name(name):
    obj = bpy.data.objects.get(name)
    if obj:
        return safe_remove_object(obj)
    return False


def safe_remove_engrave_object(name):
    """Retira un helper de grabado junto con su datablock temporal.

    A diferencia de la eliminación genérica, la vista previa y el cutter del
    nombre siempre son propiedad exclusiva de DSG. Eliminarlos con sus datos
    evita acumular ``DSG_EngravePreview_Mesh.001`` tras editar varias veces el
    texto. También limpia curvas FONT huérfanas dejadas por versiones antiguas.
    """
    obj = bpy.data.objects.get(str(name))
    removed = False
    if obj is not None:
        if getattr(obj, 'data', None) is not None:
            removed = safe_remove_object_with_data(obj)
        else:
            removed = safe_remove_object(obj)

    legacy_names = {
        str(name) + '_Curve',
        str(name) + '_Mesh',
    }
    for datablocks in (getattr(bpy.data, 'curves', ()), getattr(bpy.data, 'meshes', ())):
        for datablock in list(datablocks):
            try:
                data_name = str(datablock.name)
                is_legacy = data_name in legacy_names or any(
                    data_name.startswith(prefix + '.') for prefix in legacy_names)
                if is_legacy and int(getattr(datablock, 'users', 1)) == 0:
                    datablocks.remove(datablock)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed


def safe_remove_object_with_data(obj):
    """Elimina un objeto temporal y su datablock huérfano cuando es seguro.

    ``bpy.data.objects.remove`` no elimina automáticamente la malla asociada.
    Para objetos de trabajo creados por DSG eso deja ``Mesh.001`` con
    ``users == 0`` y rompe el test de Frankenstein. Esta función solo elimina
    el datablock cuando ya no tiene ningún usuario, por lo que nunca borra una
    malla compartida por otro objeto.
    """
    if not _valid_obj(obj):
        return False
    try:
        data = getattr(obj, 'data', None)
    except Exception:
        data = None
    removed = safe_remove_object(obj)
    if removed and data is not None:
        try:
            if getattr(data, 'users', 1) == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
            return True
        except (ReferenceError, RuntimeError):
            return True
        except Exception:
            return True
    return removed


def safe_remove_temp_by_name(name):
    obj = bpy.data.objects.get(name)
    if obj:
        return safe_remove_object_with_data(obj)
    return False


def safe_remove_by_prefix(prefix):
    for obj in list(bpy.data.objects):
        if obj.name.startswith(prefix):
            safe_remove_object(obj)


def deselect_all_objects():
    # The view-layer collection can briefly yield ``None`` right after objects
    # were removed in the same operator (seen in Blender 5.2); skip them.
    for o in list(bpy.context.view_layer.objects):
        if o is not None:
            o.select_set(False)


def set_active(context, obj):
    if not _valid_obj(obj):
        return
    deselect_all_objects()
    obj.select_set(True)
    context.view_layer.objects.active = obj


def link_object(context, obj):
    if not _valid_obj(obj):
        return
    # Si register_dsg_object ya lo enlazó a una colección DSG, no duplicamos enlaces.
    if getattr(obj, 'users_collection', None):
        return
    if obj.name not in context.collection.objects:
        context.collection.objects.link(obj)


def ensure_object_mode(context):
    obj = context.view_layer.objects.active
    if obj and obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def apply_modifier_direct(context, obj, mod_name):
    mod = obj.modifiers.get(mod_name)
    if not mod:
        return False
    mod.show_viewport = True
    mod.show_render   = True
    prev_active = context.view_layer.objects.active
    ensure_object_mode(context)
    set_active(context, obj)
    try:
        with context.temp_override(object=obj, active_object=obj,
                                   selected_objects=[obj],
                                   selected_editable_objects=[obj]):
            bpy.ops.object.modifier_apply(modifier=mod_name)
        if _valid_obj(prev_active):
            set_active(context, prev_active)
        return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        bpy.ops.object.modifier_apply(modifier=mod_name)
        if _valid_obj(prev_active):
            set_active(context, prev_active)
        return True
    except Exception as e:
        print(f"[DSG] Error aplicando {mod_name}: {e}")
        if _valid_obj(prev_active):
            set_active(context, prev_active)
        return False


def should_keep_sleeve_flat_faces(props):
    """Protege la geometría precisa del sleeve después de generarlo.

    El voxel remesh global fusiona visualmente las uniones, pero también
    redondea/deforma las caras planas del cilindro del sleeve. Cuando esta
    opción está activa, los pasos posteriores solo hacen join/boolean y evitan
    remesh sobre DSG_Guide hasta que el usuario lo decida al final.
    """
    try:
        return bool(getattr(props, 'sleeve_keep_flat_faces', True))
    except Exception:
        return True


def mark_sleeve_flat_protected(obj, skipped_step=None):
    if _valid_obj(obj):
        try:
            obj['DSG_sleeve_flat_faces_protected'] = True
            if skipped_step:
                obj['DSG_sleeve_remesh_skipped'] = str(skipped_step)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def continuous_fusion_remesh_enabled(props):
    """Devuelve True cuando se prioriza una guía soldada y manifold.

    Las versiones que funcionaban de forma más estable aplicaban voxel remesh
    después de cada unión. El modo continuo recupera ese comportamiento y usa
    un voxel fino para limitar la deformación del sleeve.
    """
    try:
        return bool(getattr(props, 'continuous_fusion_remesh', True))
    except Exception:
        return True


def get_continuous_fusion_voxel(props, requested_voxel):
    requested = max(0.02, float(requested_voxel))
    try:
        cap = float(getattr(props, 'continuous_fusion_voxel', 0.12))
    except Exception:
        cap = 0.12
    return max(0.04, min(requested, max(0.04, cap)))


def add_and_apply_voxel_remesh_if_allowed(context, props, obj, mod_name, voxel_size, smooth=True, skipped_step=None):
    """Aplica voxel remesh solo cuando no puede alterar un sleeve protegido.

    Con ``sleeve_keep_flat_faces`` activo, DSG_Guide nunca vuelve a voxelizarse.
    Las fusiones posteriores se resuelven con Boolean EXACT y cutters sólidos.
    Así las dos caras anulares planas del sleeve quedan geométricamente invulnerables.
    """
    if not _valid_obj(obj):
        return False
    if should_keep_sleeve_flat_faces(props) and obj.name.startswith(GUIDE_NAME):
        mark_sleeve_flat_protected(obj, skipped_step or mod_name)
        return False
    remesh = obj.modifiers.new(mod_name, 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = get_continuous_fusion_voxel(props, voxel_size)
    remesh.use_smooth_shade = bool(smooth)
    return apply_modifier_direct(context, obj, remesh.name)

def join_objects(context, objects, out_name):
    valid = [o for o in objects if _valid_obj(o) and o.type == 'MESH']
    if not valid:
        return None
    ensure_object_mode(context)
    deselect_all_objects()
    for o in valid:
        o.select_set(True)
    context.view_layer.objects.active = valid[0]
    try:
        bpy.ops.object.join()
        joined = context.view_layer.objects.active
        joined.name = out_name
        return joined
    except Exception as e:
        print(f"[DSG] Error join: {e}")
        return None


def duplicate_object_with_data(context, src_obj, new_name):
    if not _valid_obj(src_obj):
        return None
    new_mesh = src_obj.data.copy()
    new_obj  = bpy.data.objects.new(new_name, new_mesh)
    new_obj.matrix_world = src_obj.matrix_world.copy()
    link_object(context, new_obj)
    return new_obj

def duplicate_evaluated_object_with_data(context, src_obj, new_name):
    """Duplica la geometría evaluada para que modificadores visibles y blockout coincidan."""
    if not _valid_obj(src_obj):
        return None
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = src_obj.evaluated_get(depsgraph)
    try:
        new_mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=False, depsgraph=depsgraph)
    except TypeError:
        new_mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
    if new_mesh is None:
        return None
    new_mesh.name = new_name + "_Mesh"
    new_obj = bpy.data.objects.new(new_name, new_mesh)
    new_obj.matrix_world = evaluated.matrix_world.copy()
    link_object(context, new_obj)
    return new_obj



def _world_vertex_normal(obj, vertex):
    """Return a normalized world-space vertex normal without modifying the mesh."""
    try:
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        normal = normal_matrix @ vertex.normal
        if normal.length > 1.0e-10:
            return normal.normalized()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return Vector((0.0, 0.0, 1.0))


def _ensure_temporary_blockout_proxy_manifold(proxy):
    """Verify and, only on the temporary proxy, repair topology without remesh.

    The clinical source and the visible blockout are never edited.  The proxy has
    the same closed topology as the base model, so moving its vertices cannot
    create boundary edges.  This fallback only removes loose/degenerate topology
    or fills a pre-existing small opening in the disposable Boolean proxy.
    """
    report = get_mesh_solid_report_scalable(proxy, max_edges=5000000)
    if report.get('checked') and report.get('solid'):
        return report

    make_mesh_manifold_bmesh(
        proxy,
        merge_dist=0.00005,
        fill_holes=True,
        max_vertices=1200000,
    )
    return get_mesh_solid_report_scalable(proxy, max_edges=5000000)


def _build_blockout_addition_volume(context, original_obj, blockout_obj,
                                     overlap_mm=RETENTION_BOOLEAN_OVERLAP_MM):
    """Create a disposable, closed proxy for surgical-guide blockout UNION.

    This is *not* a crown/cement-space offset.  The visible blockout and the IOS
    remain untouched.  Only a temporary Boolean proxy is moved microscopically
    into the source model so Blender sees a real volumetric intersection instead
    of tangent/coplanar faces.

    Behaviour:
      * unchanged anatomy is placed inside the IOS by ``overlap_mm``;
      * the true blockout exterior remains geometrically exact;
      * only the transition and two inner rings taper from overlap to zero;
      * direction blends insertion axis with the local inward surface normal;
      * the proxy keeps the complete closed source topology (no open skirt).
    """
    if not _valid_obj(original_obj) or not _valid_obj(blockout_obj):
        return None
    if original_obj.type != 'MESH' or blockout_obj.type != 'MESH':
        return None
    if len(original_obj.data.vertices) != len(blockout_obj.data.vertices):
        raise RuntimeError('Blockout topology no longer matches the source model')
    if len(original_obj.data.polygons) != len(blockout_obj.data.polygons):
        raise RuntimeError('Blockout face topology no longer matches the source model')

    source_report = get_mesh_solid_report_scalable(original_obj, max_edges=5000000)
    if source_report.get('checked') and not source_report.get('solid'):
        raise RuntimeError(
            'The base model must be manifold before blockout union '
            f'(bad edges: {source_report.get("bad_edges")})')

    axis = _read_stored_world_axis(blockout_obj, 'DSG_insertion_axis_world')
    if axis is None:
        axis = _read_stored_world_axis(blockout_obj, BLOCKOUT_AXIS_WORLD_KEY)
    if axis is None:
        axis = get_insertion_axis()
    axis = Vector(axis)
    if axis.length <= 1.0e-10:
        raise RuntimeError('Invalid blockout insertion axis')
    axis.normalize()

    overlap = min(
        float(RETENTION_BOOLEAN_OVERLAP_MAX_MM),
        max(0.005, float(overlap_mm)),
    )
    original_world = [original_obj.matrix_world @ v.co for v in original_obj.data.vertices]
    blockout_world = [blockout_obj.matrix_world @ v.co for v in blockout_obj.data.vertices]
    axial_displacement = [
        max(0.0, float((blockout_world[i] - original_world[i]).dot(axis)))
        for i in range(len(original_world))
    ]
    if not axial_displacement or max(axial_displacement) <= RETENTION_BOUNDARY_ISO_MM:
        return None

    changed = {i for i, depth in enumerate(axial_displacement)
               if depth > RETENTION_BOUNDARY_ISO_MM}
    neighbours = [set() for _ in original_obj.data.vertices]
    for edge in original_obj.data.edges:
        a, b = edge.vertices
        neighbours[a].add(b)
        neighbours[b].add(a)

    # Changed vertices touching unchanged anatomy are the true transition rim.
    boundary = {
        i for i in changed
        if any(j not in changed for j in neighbours[i])
    }
    ring_distance = {i: 0 for i in boundary}
    frontier = set(boundary)
    for ring in range(1, max(0, int(RETENTION_BOOLEAN_OVERLAP_RINGS)) + 1):
        nxt = set()
        for i in frontier:
            for j in neighbours[i]:
                if j in changed and j not in ring_distance:
                    ring_distance[j] = ring
                    nxt.add(j)
        frontier = nxt
        if not frontier:
            break

    # Copy the complete closed topology. Unchanged vertices are inset fully;
    # transition rings taper smoothly; the functional exterior stays exact.
    proxy_mesh = blockout_obj.data.copy()
    proxy_mesh.name = 'DSG_BlockoutAddition_Mesh'
    addition = bpy.data.objects.new('DSG_BlockoutAddition', proxy_mesh)
    addition.matrix_world = blockout_obj.matrix_world.copy()
    link_object(context, addition)
    inverse_world = addition.matrix_world.inverted()

    max_ring = max(1, int(RETENTION_BOOLEAN_OVERLAP_RINGS))
    moved = 0
    exact_exterior = 0
    for index, proxy_vertex in enumerate(proxy_mesh.vertices):
        if index not in changed:
            weight = 1.0
        elif index in ring_distance:
            # Boundary = full overlap; last protected ring approaches zero.
            t = min(1.0, float(ring_distance[index]) / float(max_ring + 1))
            weight = 1.0 - (t * t * (3.0 - 2.0 * t))  # inverse smoothstep
        else:
            weight = 0.0

        if weight <= 1.0e-8:
            proxy_vertex.co = inverse_world @ blockout_world[index]
            exact_exterior += 1
            continue

        outward = _world_vertex_normal(original_obj, original_obj.data.vertices[index])
        # Keep the direction coherent with insertion. Opposing normals are
        # flipped before blending, avoiding lateral folds around steep teeth.
        if outward.dot(axis) < 0.0:
            outward.negate()
        penetration_dir = axis * 0.70 + outward * 0.30
        if penetration_dir.length <= 1.0e-10:
            penetration_dir = axis.copy()
        penetration_dir.normalize()
        target_world = blockout_world[index] - penetration_dir * (overlap * weight)
        proxy_vertex.co = inverse_world @ target_world
        moved += 1

    proxy_mesh.validate(clean_customdata=False)
    proxy_mesh.update(calc_edges=True)
    try:
        bm = bmesh.new()
        bm.from_mesh(proxy_mesh)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(proxy_mesh)
        bm.free()
        proxy_mesh.update(calc_edges=True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    proxy_report = _ensure_temporary_blockout_proxy_manifold(addition)
    addition['DSG_blockout_addition_only'] = True
    addition['DSG_blockout_proxy_method'] = 'SURGICAL_GUIDE_LOCAL_TAPERED_OVERLAP'
    addition['DSG_boolean_overlap_mm'] = float(overlap)
    addition['DSG_boolean_overlap_max_mm'] = float(RETENTION_BOOLEAN_OVERLAP_MAX_MM)
    addition['DSG_boolean_overlap_rings'] = int(RETENTION_BOOLEAN_OVERLAP_RINGS)
    addition['DSG_boolean_overlap_vertices'] = int(moved)
    addition['DSG_boolean_exact_exterior_vertices'] = int(exact_exterior)
    addition['DSG_boolean_offset_is_clinical_relief'] = False
    addition['DSG_boolean_use_case'] = 'SURGICAL_GUIDE_BLOCKOUT_UNION'
    addition['DSG_maximum_axial_addition_mm'] = float(max(axial_displacement))
    addition['DSG_proxy_manifold_checked'] = bool(proxy_report.get('checked'))
    addition['DSG_proxy_manifold_solid'] = bool(proxy_report.get('solid'))
    addition.display_type = 'SOLID'
    return addition

def _passive_blockout_material(name, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = False
    material.diffuse_color = tuple(color)
    return material


def _assign_blockout_union_band_material(passive, original_obj,
                                          band_width_mm=RETENTION_JOIN_BAND_WIDTH_MM):
    """Paint a narrow surgical-teal band where the blockout joins the source model.

    The classification is geometric and independent of Boolean face provenance:
    faces coincident with the original anatomy remain ivory; faces outside the
    original BVH are considered blockout-generated.  The first added faces next
    to the transition, plus their immediate base neighbours, form the surgical-teal band.
    Colors are visual metadata only and do not alter/export the STL geometry.
    """
    if not _valid_obj(passive) or not _valid_obj(original_obj):
        return 0
    if passive.type != 'MESH' or original_obj.type != 'MESH':
        return 0

    source_bm = bmesh.new()
    result_bm = bmesh.new()
    try:
        source_bm.from_mesh(original_obj.data)
        source_bm.transform(original_obj.matrix_world)
        source_bm.faces.ensure_lookup_table()
        source_bm.normal_update()
        source_tree = BVHTree.FromBMesh(source_bm, epsilon=0.0)

        result_bm.from_mesh(passive.data)
        result_bm.faces.ensure_lookup_table()
        result_bm.edges.ensure_lookup_table()
        world = passive.matrix_world
        distance_eps = max(0.003, float(RETENTION_JOIN_DISTANCE_EPS_MM))
        band_width = max(distance_eps * 2.0, float(band_width_mm))

        blockout_only = str(passive.get('DSG_combination_method', '')).startswith(
            ('BLOCKOUT_ONLY_', 'CLOSED_BLOCKOUT_ONLY_'))
        if blockout_only:
            # The passive cutter is now a single offset blockout shell. Distance
            # to the IOS therefore classifies almost every face as outside and
            # would paint the whole model teal. Preserve the pre-protocol face
            # classes instead: material 2 = blockout addition; the accent is only
            # the interface with passive/retentive faces.
            added = {face: bool(int(face.material_index) == 2)
                     for face in result_bm.faces}
            seam = set()
            for face in result_bm.faces:
                for edge in face.edges:
                    neighbours = [linked for linked in edge.link_faces if linked is not face]
                    if any(added.get(linked, False) != added.get(face, False)
                           for linked in neighbours):
                        seam.add(face)
                        seam.update(neighbours)
        else:
            # Query every result vertex once. Dense dental scans commonly contain
            # two faces per vertex, so caching vertex distances roughly halves the
            # BVH work compared with querying every face sample independently.
            vertex_distance = {}
            for vert in result_bm.verts:
                nearest = source_tree.find_nearest(world @ vert.co)
                vertex_distance[vert] = (
                    float(nearest[3])
                    if nearest and nearest[3] is not None
                    else 1.0e9
                )

            added = {}
            near_transition = {}
            for face in result_bm.faces:
                distances = [vertex_distance[vert] for vert in face.verts]
                maximum = max(distances) if distances else 0.0
                mean = sum(distances) / max(1, len(distances))
                minimum = min(distances) if distances else 0.0
                is_added = maximum > distance_eps and mean > distance_eps * 0.35
                added[face] = bool(is_added)
                near_transition[face] = bool(is_added and minimum <= band_width)

            seam = {face for face, value in near_transition.items() if value}
            for face in result_bm.faces:
                for edge in face.edges:
                    neighbours = [linked for linked in edge.link_faces if linked is not face]
                    if any(added.get(linked, False) != added.get(face, False) for linked in neighbours):
                        seam.add(face)
                        seam.update(neighbours)

        # One extra ring keeps the line readable in Solid/Material Preview even
        # on very dense intraoral scans, without colouring the whole blockout.
        expanded = set(seam)
        for face in list(seam):
            for edge in face.edges:
                expanded.update(edge.link_faces)
        seam = expanded

        base_mat = _passive_blockout_material(
            'DSG_PassiveBaseCoolPorcelain', (0.82, 0.86, 0.88, 1.0))
        teal_mat = _passive_blockout_material(
            'DSG_BlockoutJoinSurgicalTeal', (0.025, 0.46, 0.50, 1.0))
        passive.data.materials.clear()
        passive.data.materials.append(base_mat)
        passive.data.materials.append(teal_mat)

        for face in result_bm.faces:
            face.material_index = 1 if face in seam else 0
        result_bm.to_mesh(passive.data)
        passive.data.update(calc_edges=True)

        count = len(seam)
        passive['DSG_blockout_join_material'] = 'DSG_BlockoutJoinSurgicalTeal'
        passive['DSG_blockout_join_band_width_mm'] = float(band_width)
        passive['DSG_blockout_join_accent_faces'] = int(count)
        # Legacy key retained so older diagnostic tools can still read the count.
        passive['DSG_blockout_join_gold_faces'] = int(count)
        return int(count)
    finally:
        source_bm.free()
        result_bm.free()

def _quiesce_blockout_boolean_modifiers():
    """Disable and remove legacy blockout Boolean modifiers without evaluation.

    Blender 5.0.1 can crash natively inside ``meshintersect::boolean_trimesh``
    while the dependency graph evaluates an old blockout UNION modifier.  The
    current blockout is homologous to the closed source model and no longer
    needs a Boolean modifier, so stale modifiers are disabled before any object
    selection, deletion or viewport update can trigger them.
    """
    target_names = {
        COMBINED_NAME,
        BLOCKOUT_NAME,
        'DSG_Orig_Copy',
        'DSG_Blockout_Copy',
        'DSG_BlockoutAddition',
        'DSG_Blockout_PreviewBackup',
    }
    removed = 0
    for obj in list(getattr(bpy.data, 'objects', ())):
        try:
            relevant = (
                obj.name in target_names
                or obj.name.startswith('DSG_Blockout')
                or obj.name.startswith('DSG_Passive')
            )
        except Exception:
            relevant = False
        if not relevant:
            continue
        for modifier in list(getattr(obj, 'modifiers', ())):
            try:
                is_boolean = modifier.type == 'BOOLEAN'
                is_blockout = (
                    'blockout' in str(modifier.name).lower()
                    or obj.name in target_names
                    or obj.name.startswith('DSG_Blockout')
                    or obj.name.startswith('DSG_Passive')
                )
            except Exception:
                continue
            if not (is_boolean and is_blockout):
                continue
            try:
                modifier.show_viewport = False
                modifier.show_render = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                obj.modifiers.remove(modifier)
                removed += 1
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return int(removed)


def _blockout_class_values(obj):
    """Read the point-domain retention classes written by build_blockout_bvh.

    0 = passive/support anatomy, 1 = deliberately retained undercut,
    2 = directional blockout addition. Material indices are a robust fallback
    for older .blend files where the point attribute was not preserved.
    """
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return []
    mesh = obj.data
    values = []
    try:
        attribute = mesh.attributes.get('DSG_retention_class')
        if attribute and attribute.domain == 'POINT' and len(attribute.data) == len(mesh.vertices):
            values = [max(0, min(2, int(item.value))) for item in attribute.data]
    except Exception:
        values = []
    if len(values) == len(mesh.vertices):
        return values

    values = [0] * len(mesh.vertices)
    try:
        for polygon in mesh.polygons:
            value = max(0, min(2, int(polygon.material_index)))
            for index in polygon.vertices:
                if value > values[index]:
                    values[index] = value
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return values


def _replace_vertex_group_indices(obj, name, indices, weight=1.0):
    """Create one deterministic vertex group without per-vertex Python calls."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return 0
    previous = obj.vertex_groups.get(name)
    if previous is not None:
        try:
            obj.vertex_groups.remove(previous)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    group = obj.vertex_groups.new(name=name)
    clean = sorted({int(index) for index in indices
                    if 0 <= int(index) < len(obj.data.vertices)})
    chunk_size = 100000
    for offset in range(0, len(clean), chunk_size):
        group.add(clean[offset:offset + chunk_size], float(weight), 'REPLACE')
    return len(clean)


def _prepare_blockout_modifier_groups(obj):
    """Create passive, retentive, blockout and transition groups.

    The transition is topology-based rather than non-manifold based. This keeps
    the operation local even on a perfectly closed IOS and reproduces the useful
    part of Select Non-Manifold + Relax without touching the complete arch.
    """
    classes = _blockout_class_values(obj)
    if not classes:
        return {}, []
    neighbours = [set() for _ in classes]
    for edge in obj.data.edges:
        a, b = (int(edge.vertices[0]), int(edge.vertices[1]))
        neighbours[a].add(b)
        neighbours[b].add(a)

    passive = {index for index, value in enumerate(classes) if value == 0}
    retained = {index for index, value in enumerate(classes) if value == 1}
    blocked = {index for index, value in enumerate(classes) if value == 2}
    transition = set()
    for index, linked in enumerate(neighbours):
        if any(classes[other] != classes[index] for other in linked):
            transition.add(index)
            transition.update(linked)

    frontier = set(transition)
    for _ in range(max(0, int(RETENTION_PROTOCOL_TRANSITION_RINGS) - 1)):
        expanded = set(frontier)
        for index in frontier:
            expanded.update(neighbours[index])
        frontier = expanded - transition
        transition.update(expanded)
        if not frontier:
            break

    counts = {
        'passive': _replace_vertex_group_indices(obj, 'DSG_PassiveSupport', passive),
        'retained': _replace_vertex_group_indices(obj, 'DSG_RetentiveZone', retained),
        'blocked': _replace_vertex_group_indices(obj, 'DSG_BlockoutZone', blocked),
        'transition': _replace_vertex_group_indices(obj, 'DSG_BlockoutTransition', transition),
    }
    return counts, classes


def _add_apply_passive_shrinkwrap(context, obj, target, modifier_name):
    """Project only passive support vertices to the IOS plus guide clearance."""
    if not RETENTION_PROTOCOL_PASSIVE_SHRINKWRAP:
        return True
    group = obj.vertex_groups.get('DSG_PassiveSupport')
    if group is None or not _valid_obj(target):
        return True
    clearance = max(0.0, float(obj.get(
        'DSG_passive_clearance_mm', RETENTION_PASSIVE_CLEARANCE_MM)))
    modifier = obj.modifiers.new(modifier_name, 'SHRINKWRAP')
    modifier.target = target
    modifier.vertex_group = group.name
    try:
        modifier.wrap_method = 'NEAREST_SURFACEPOINT'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    # OUTSIDE_SURFACE prevents a correctly oriented closed IOS from pulling the
    # seating surface through the tooth. Blender versions expose slightly
    # different enums, so unsupported values fall back to ON_SURFACE + offset.
    for mode in ('OUTSIDE_SURFACE', 'ABOVE_SURFACE', 'ON_SURFACE'):
        try:
            modifier.wrap_mode = mode
            break
        except Exception:
            continue
    modifier.offset = float(clearance)
    try:
        modifier.use_invert_vertex_group = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return apply_modifier_direct(context, obj, modifier.name)


def _add_apply_transition_relax(context, obj):
    """Apply a real Blender Laplacian modifier only to the blockout frontier."""
    group = obj.vertex_groups.get('DSG_BlockoutTransition')
    if group is None:
        return True, 'NO_TRANSITION'
    modifier = obj.modifiers.new('DSG_BlockoutTransitionRelax', 'LAPLACIANSMOOTH')
    modifier.vertex_group = group.name
    for attr, value in (
        ('iterations', int(RETENTION_PROTOCOL_RELAX_ITERATIONS)),
        ('lambda_factor', float(RETENTION_PROTOCOL_RELAX_FACTOR)),
        ('lambda_border', float(RETENTION_PROTOCOL_RELAX_BORDER_FACTOR)),
        ('use_volume_preserve', True),
        ('use_normalized', True),
        ('use_x', True), ('use_y', True), ('use_z', True),
    ):
        try:
            setattr(modifier, attr, value)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if apply_modifier_direct(context, obj, modifier.name):
        return True, 'LAPLACIANSMOOTH'

    # Compatibility fallback for Blender builds where Laplacian modifier RNA
    # differs. It remains limited to the same transition group.
    try:
        if obj.modifiers.get('DSG_BlockoutTransitionRelax'):
            obj.modifiers.remove(obj.modifiers.get('DSG_BlockoutTransitionRelax'))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    smooth = obj.modifiers.new('DSG_BlockoutTransitionRelaxFallback', 'SMOOTH')
    smooth.vertex_group = group.name
    smooth.factor = float(RETENTION_PROTOCOL_RELAX_FACTOR)
    smooth.iterations = max(1, int(RETENTION_PROTOCOL_RELAX_ITERATIONS))
    return apply_modifier_direct(context, obj, smooth.name), 'SMOOTH_FALLBACK'


def _clamp_blockout_modifier_result(obj, baseline_world, classes, axis):
    """Prevent modifiers from weakening retention or over-rounding the frontier."""
    if not _valid_obj(obj) or len(obj.data.vertices) != len(baseline_world):
        return {'clamped': 0, 'axial_restored': 0}
    axis = Vector(axis)
    if axis.length <= 1.0e-10:
        axis = Vector((0.0, 0.0, 1.0))
    axis.normalize()
    world = obj.matrix_world
    inverse = world.inverted()
    maximum_delta = max(0.005, float(RETENTION_PROTOCOL_MAX_SMOOTH_DELTA_MM))
    clamped = 0
    axial_restored = 0
    for index, vertex in enumerate(obj.data.vertices):
        baseline = baseline_world[index]
        current = world @ vertex.co
        delta = current - baseline
        if delta.length > maximum_delta:
            current = baseline + delta.normalized() * maximum_delta
            clamped += 1
        cls = classes[index] if index < len(classes) else 0
        if cls in (1, 2):
            axial = float((current - baseline).dot(axis))
            if axial < 0.0:
                current += axis * (-axial)
                axial_restored += 1
        vertex.co = inverse @ current
    obj.data.update(calc_edges=True)
    return {'clamped': int(clamped), 'axial_restored': int(axial_restored)}


def _boundary_edge_components_with_verts(boundary_edges):
    pending = set(boundary_edges)
    components = []
    while pending:
        seed = pending.pop()
        component = {seed}
        verts = set(seed.verts)
        changed = True
        while changed:
            changed = False
            linked = {edge for vert in tuple(verts) for edge in vert.link_edges
                      if edge in pending and len(edge.link_faces) == 1}
            if linked:
                pending.difference_update(linked)
                component.update(linked)
                for edge in linked:
                    verts.update(edge.verts)
                changed = True
        components.append((component, verts))
    return components


def _cleanup_blockout_protocol_mesh(obj):
    """BMesh equivalent of the supplied cleanup protocol, applied safely.

    It removes loose/duplicate/degenerate geometry, relaxes only true open
    boundaries, performs limited dissolve there, and fills only simple holes
    with at most RETENTION_PROTOCOL_MAX_HOLE_SIDES edges. It deliberately does
    not delete every non-manifold face, which could remove valid dental anatomy.
    """
    report = {
        'loose_edges': 0, 'loose_vertices': 0, 'boundary_vertices': 0,
        'holes_filled': 0, 'merge_distance_mm': float(RETENTION_PROTOCOL_MERGE_DISTANCE_MM),
    }
    if not _valid_obj(obj) or obj.type != 'MESH':
        return report
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        loose_edges = [edge for edge in bm.edges if not edge.link_faces]
        report['loose_edges'] = len(loose_edges)
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
        loose_vertices = [vert for vert in bm.verts if not vert.link_edges]
        report['loose_vertices'] = len(loose_vertices)
        if loose_vertices:
            bmesh.ops.delete(bm, geom=loose_vertices, context='VERTS')

        if bm.verts:
            bmesh.ops.remove_doubles(
                bm, verts=bm.verts[:],
                dist=max(0.0, float(RETENTION_PROTOCOL_MERGE_DISTANCE_MM)))
        if bm.edges:
            try:
                bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1.0e-7)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        boundary_vertices = {vert for edge in boundary_edges for vert in edge.verts}
        report['boundary_vertices'] = len(boundary_vertices)

        if boundary_vertices:
            # Three conservative relax passes, matching the supplied LoopTools
            # protocol but without requiring the optional add-on.
            for _ in range(3):
                updates = {}
                for vert in boundary_vertices:
                    linked = [edge.other_vert(vert) for edge in vert.link_edges
                              if len(edge.link_faces) == 1]
                    if len(linked) < 2:
                        continue
                    average = sum((other.co for other in linked), Vector()) / float(len(linked))
                    updates[vert] = vert.co.lerp(average, 0.35)
                for vert, coordinate in updates.items():
                    vert.co = coordinate

            try:
                bmesh.ops.dissolve_limit(
                    bm,
                    angle_limit=math.radians(float(RETENTION_PROTOCOL_DISSOLVE_ANGLE_DEG)),
                    use_dissolve_boundaries=True,
                    verts=list(boundary_vertices),
                    edges=boundary_edges,
                    delimit={'NORMAL'},
                )
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

            bm.edges.ensure_lookup_table()
            boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
            for component, verts in _boundary_edge_components_with_verts(boundary_edges):
                maximum = int(RETENTION_PROTOCOL_MAX_HOLE_SIDES)
                # Fill only a simple loop, never a branched non-manifold defect.
                degrees = {vert: sum(1 for edge in vert.link_edges if edge in component)
                           for vert in verts}
                if not component or len(component) > maximum:
                    continue
                if any(degree != 2 for degree in degrees.values()):
                    continue
                try:
                    result = bmesh.ops.holes_fill(bm, edges=list(component), sides=maximum)
                    if result.get('faces'):
                        report['holes_filled'] += 1
                except Exception:
                    continue

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(obj.data)
        obj.data.validate(clean_customdata=False)
        obj.data.update(calc_edges=True)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
        return report
    finally:
        bm.free()


def _apply_surgical_guide_blockout_modifier_protocol(context, original_obj, passive):
    """Apply the clinical passive-seat stack transactionally to one copy."""
    if not _valid_obj(original_obj) or not _valid_obj(passive):
        return False, {'reason': 'invalid objects'}
    backup = passive.data.copy()
    backup.name = passive.data.name + '_ProtocolBackup'
    baseline_world = [passive.matrix_world @ vertex.co.copy()
                      for vertex in passive.data.vertices]
    counts, classes = _prepare_blockout_modifier_groups(passive)
    axis = _read_stored_world_axis(passive, BLOCKOUT_AXIS_WORLD_KEY)
    if axis is None:
        axis = _read_stored_world_axis(passive, 'DSG_insertion_axis_world')
    if axis is None:
        axis = get_insertion_axis()

    shrink_first = True
    relax_ok = True
    shrink_lock = True
    relax_method = 'NO_TRANSITION'
    try:
        if counts.get('passive', 0):
            shrink_first = _add_apply_passive_shrinkwrap(
                context, passive, original_obj, 'DSG_PassiveSeatShrinkwrap')
        if counts.get('transition', 0):
            relax_ok, relax_method = _add_apply_transition_relax(context, passive)
        if counts.get('passive', 0):
            shrink_lock = _add_apply_passive_shrinkwrap(
                context, passive, original_obj, 'DSG_PassiveSeatLock')
        clamp = _clamp_blockout_modifier_result(passive, baseline_world, classes, axis)
        cleanup = _cleanup_blockout_protocol_mesh(passive)
        solid = get_mesh_solid_report_scalable(passive, max_edges=5000000)
        success = bool(shrink_first and relax_ok and shrink_lock
                       and (not solid.get('checked') or solid.get('solid')))
        report = {
            'success': success,
            'groups': counts,
            'shrinkwrap_first': bool(shrink_first),
            'transition_relax': bool(relax_ok),
            'relax_method': str(relax_method),
            'shrinkwrap_lock': bool(shrink_lock),
            'clamp': clamp,
            'cleanup': cleanup,
            'solid': solid,
        }
        if success:
            old_backup = backup
            try:
                if old_backup.users == 0:
                    bpy.data.meshes.remove(old_backup)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return True, report
    except Exception as exc:
        report = {'success': False, 'reason': str(exc), 'groups': counts}

    # Roll back all geometric modifier effects if any stage failed.
    old_mesh = passive.data
    passive.data = backup
    try:
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for modifier in list(passive.modifiers):
        try:
            passive.modifiers.remove(modifier)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False, report


def _boolean_rescue_passive_model(context, original_obj, blockout_obj):
    """Last-resort Boolean with a 0.01-0.03 mm disposable local overlap."""
    boolean_error = ''
    attempts = 0
    for overlap in RETENTION_BOOLEAN_OVERLAP_RETRIES_MM:
        attempts += 1
        safe_remove_by_name('DSG_Orig_Copy')
        safe_remove_by_name('DSG_BlockoutAddition')
        orig_copy = duplicate_object_with_data(context, original_obj, 'DSG_Orig_Copy')
        if not _valid_obj(orig_copy):
            boolean_error = 'could not duplicate source IOS'
            break
        try:
            addition = _build_blockout_addition_volume(
                context, original_obj, blockout_obj, overlap_mm=overlap)
        except Exception as exc:
            addition = None
            boolean_error = str(exc)
        if not _valid_obj(addition):
            safe_remove_object(orig_copy)
            if not boolean_error:
                boolean_error = 'could not build rescue overlap proxy'
            continue
        result, ok, message = fuse_additions_into_base_exact(
            context, orig_copy, [addition], COMBINED_NAME,
            mod_name=f'DSG_BlockoutRescue_{int(round(overlap * 1000.0)):03d}um',
            require_solid=True, robust=True, cleanup_cutter=False,
            prevalidated=False,
        )
        if ok and _valid_obj(result):
            return result, float(overlap), int(attempts), ''
        boolean_error = str(message)
        safe_remove_object(orig_copy)
        safe_remove_by_name('DSG_BlockoutAddition')
    return None, 0.0, int(attempts), boolean_error


def build_joined_passive_model(context, original_obj, blockout_obj,
                               output_name=COMBINED_NAME):
    """Create the v7-compatible passive cutter from evaluated IOS + blockout.

    The two surfaces are joined into one Blender object but are intentionally not
    forced manifold here. The existing v8 final-cut stage voxelizes the cutter at
    the configured resolution before the Boolean, exactly where solidification
    belongs in the proven workflow.
    """
    if not _valid_obj(original_obj) or not _valid_obj(blockout_obj):
        return None
    if original_obj.type != 'MESH' or blockout_obj.type != 'MESH':
        return None

    orig_name = output_name + '_Orig_Copy'
    block_name = output_name + '_Blockout_Copy'
    for name in (output_name, orig_name, block_name):
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            safe_remove_object(obj)

    orig_copy = duplicate_evaluated_object_with_data(context, original_obj, orig_name)
    block_copy = duplicate_object_with_data(context, blockout_obj, block_name)
    if not _valid_obj(orig_copy) or not _valid_obj(block_copy):
        if _valid_obj(orig_copy):
            safe_remove_object(orig_copy)
        if _valid_obj(block_copy):
            safe_remove_object(block_copy)
        return None

    orig_copy.display_type = 'SOLID'
    block_copy.display_type = 'SOLID'
    _set_obj_hidden(orig_copy, False, selectable_when_visible=True)
    _set_obj_hidden(block_copy, False, selectable_when_visible=True)

    passive = join_objects(context, [orig_copy, block_copy], output_name)
    if not _valid_obj(passive):
        if _valid_obj(orig_copy):
            safe_remove_object(orig_copy)
        if _valid_obj(block_copy):
            safe_remove_object(block_copy)
        return None
    passive.name = output_name
    passive.data.name = output_name + '_Mesh'
    passive.display_type = 'SOLID'
    _set_obj_hidden(passive, False, selectable_when_visible=True)
    passive['DSG_contains_original'] = True
    passive['DSG_contains_original_envelope'] = True
    passive['DSG_contains_blockout'] = True
    passive['DSG_final_cut_cutter'] = 'original_plus_view_raycast_blockout'
    passive['DSG_combination_method'] = 'V7_JOINED_SURFACES__SOLIDIFY_AT_FINAL_VOXEL_CUTTER'
    passive['DSG_overlapping_shells_intentional'] = True

    mat = (bpy.data.materials.get('DSG_PassiveCombinedMat')
           or bpy.data.materials.new('DSG_PassiveCombinedMat'))
    mat.use_nodes = False
    mat.diffuse_color = (0.86, 0.86, 0.78, 1.0)
    passive.data.materials.clear()
    passive.data.materials.append(mat)
    register_dsg_object(passive, ROLE_PASSIVE, output_name)
    return passive

def get_confirmed_passive_model_obj():
    """Return only the explicitly confirmed passive/retentive cutter.

    A calculated ``DSG_Blockout`` is a preview and must never be interpreted as
    a confirmed passive model.  The previous fallback caused step 2 to report
    "confirmed", allowed implant confirmation, and then left step 3 without the
    required ``DSG_PassiveCombined`` object.
    """
    passive = get_primary_dsg_object(
        None, None, role=ROLE_PASSIVE,
        exact_name=COMBINED_NAME, obj_type='MESH')
    if not _valid_obj(passive) or passive.type != 'MESH':
        return None
    confirmed = bool(
        passive.get('DSG_retentive_model_confirmed', False)
        or passive.get('DSG_next_step_gate_passed', False)
        or str(passive.get('DSG_confirmation_state', '')).upper() == 'CONFIRMED')
    return passive if confirmed else None


def get_passive_model_obj():
    """Return the best passive-model reference for non-gating geometry tools.

    Clinical workflow gates must call :func:`get_confirmed_passive_model_obj`.
    The blockout fallback is retained only for legacy previews and diagnostic
    operations that can safely work before explicit confirmation.
    """
    passive = get_confirmed_passive_model_obj()
    if _valid_obj(passive):
        return passive
    blockout = get_primary_dsg_object(
        None, None, role=ROLE_BLOCKOUT,
        exact_name=BLOCKOUT_NAME, obj_type='MESH')
    if _valid_obj(blockout) and blockout.type == 'MESH':
        return blockout
    return None


def _set_obj_hidden(obj, hidden=True, selectable_when_visible=True):
    if not _valid_obj(obj):
        return
    obj.hide_viewport = bool(hidden)
    obj.hide_select = False if (not hidden and selectable_when_visible) else True
    try:
        obj.hide_set(bool(hidden))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def prepare_final_cut_references(context, props, show_passive=True):
    """Prepara las referencias del corte final sin esconder objetos auxiliares.

    El objetivo es que en el paso final el usuario pueda decidir manualmente
    qué ve y qué oculta. Por eso esta función solo asigna:
      · DSG_Guide como objeto a cortar.
      · DSG_PassiveCombined como cutter/modelo con blockout.

    No oculta el blockout ni la guía.
    """
    repair_core_object_pointers(props)
    passive = get_confirmed_passive_model_obj()

    if _valid_obj(passive):
        props.dct_object_making_cut = passive
        if show_passive:
            _set_obj_hidden(passive, False, selectable_when_visible=True)

    if _valid_obj(props.guide_obj):
        props.dct_object_being_cut = props.guide_obj

    return passive


def _object_is_hidden(obj):
    if not _valid_obj(obj):
        return True
    try:
        return bool(obj.hide_viewport or obj.hide_get())
    except Exception:
        return bool(obj.hide_viewport)


def _toggle_visibility_for_objects(objects, show=None):
    valid = [o for o in objects if _valid_obj(o)]
    if not valid:
        return None, []

    # Si alguno está oculto, el botón los muestra todos.
    # Si todos están visibles, el botón los oculta todos.
    if show is None:
        show = any(_object_is_hidden(o) for o in valid)

    for obj in valid:
        _set_obj_hidden(obj, not show, selectable_when_visible=True)
    return bool(show), valid


def get_blockout_visibility_objects(props=None):
    """Devuelve únicamente el modelo pasivo final para la revisión clínica.

    El blockout crudo es un objeto técnico intermedio y no debe mostrarse como
    un segundo modelo en el último paso.
    """
    if props is not None:
        repair_core_object_pointers(props)
    objs = []
    candidates = []
    if props is not None:
        candidates.append(getattr(props, 'dct_object_making_cut', None))
    candidates.extend(
        find_dsg_objects(
            role=ROLE_PASSIVE,
            exact_name=COMBINED_NAME,
            obj_type='MESH'))

    for obj in candidates:
        if (_valid_obj(obj)
                and obj.type == 'MESH'
                and obj.name == COMBINED_NAME
                and obj not in objs):
            objs.append(obj)

    # Limpiar escenas antiguas: el blockout crudo ya está integrado en el
    # modelo pasivo y no debe conservarse como un segundo modelo.
    for blockout in list(find_dsg_objects(
            role=ROLE_BLOCKOUT,
            exact_name=BLOCKOUT_NAME,
            obj_type='MESH')):
        safe_remove_object(blockout)
    return objs



def get_guide_visibility_objects(props=None):
    if props is not None:
        repair_core_object_pointers(props)
    candidates = []
    if props is not None:
        candidates.append(getattr(props, 'guide_obj', None))
    candidates.extend(find_dsg_objects(role=ROLE_GUIDE, exact_name=GUIDE_NAME, obj_type='MESH'))
    out = []
    for obj in candidates:
        if _valid_obj(obj) and obj not in out:
            out.append(obj)
    return out


# ─────────────────────────────────────────────────────────────
# Helpers geométricos
# ─────────────────────────────────────────────────────────────

def get_axis_empty():
    return bpy.data.objects.get(AXIS_EMPTY_NAME)


def get_pending_implant_axis_empty():
    """One-shot implant axis proposed from FDI without altering guide insertion."""
    empty = bpy.data.objects.get(IMPLANT_AXIS_EMPTY_NAME)
    if not _valid_obj(empty):
        return None
    try:
        if not bool(empty.get('DSG_pending_implant_axis', False)):
            return None
    except Exception:
        return None
    return empty


def consume_pending_implant_axis_empty():
    empty = bpy.data.objects.get(IMPLANT_AXIS_EMPTY_NAME)
    if not _valid_obj(empty):
        return
    try:
        empty['DSG_pending_implant_axis'] = False
        empty.hide_set(True)
        empty.hide_render = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def invalidate_pending_implant_axis_empty():
    """Invalidate an advisory FDI axis so stale geometry cannot be consumed.

    A failed re-proposal must never leave a previously valid DSG_ImplantAxis
    armed for dsg.create_implant.  The object itself is retained to avoid ID
    churn, but its capability flag and target metadata are cleared and it is
    hidden until a new successful proposal rewrites it.
    """
    empty = bpy.data.objects.get(IMPLANT_AXIS_EMPTY_NAME)
    if not _valid_obj(empty):
        return False
    try:
        empty['DSG_pending_implant_axis'] = False
        empty['DSG_target_fdi'] = 0
        empty['DSG_axis_confidence'] = 0.0
        empty['DSG_axis_method'] = ''
        empty['DSG_axis_source_tooth'] = ''
        empty['DSG_axis_clinical_review_required'] = True
        empty.hide_set(True)
        empty.hide_render = True
        empty.hide_viewport = False
    except Exception:
        return False
    return True


def hide_axis_empty():
    """Oculta DSG_Axis sin eliminarlo para conservar su orientación interna."""
    empty = get_axis_empty()
    if empty is None:
        return False
    try:
        empty.hide_set(True)
    except Exception:
        try:
            empty.hide_viewport = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        empty.hide_render = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


VIEW_REFERENCE_VERSION = 2
VIEW_REFERENCE_LOCATION_KEY = "DSG_view_reference_location_world"
VIEW_REFERENCE_PIVOT_KEY = "DSG_view_pivot_world"
VIEW_REFERENCE_DISTANCE_KEY = "DSG_view_distance"
VIEW_REFERENCE_PERSPECTIVE_KEY = "DSG_view_perspective"
VIEW_REFERENCE_MATRIX_KEY = "DSG_view_matrix_world_to_view"
VIEW_REFERENCE_VERSION_KEY = "DSG_view_reference_version"

# The blockout axis is stored explicitly as a world-space vector.  v7.0.47
# generated the blockout immediately from the exact current-view vector.  Later
# workflows reconstructed it from the arrow object, which allowed the preview
# and the final blockout to use subtly different directions after undo, reload
# or manual object changes.  These keys preserve the clinically approved vector.
BLOCKOUT_AXIS_WORLD_KEY = "DSG_blockout_axis_world"
BLOCKOUT_AXIS_SOURCE_KEY = "DSG_blockout_axis_source"
BLOCKOUT_AXIS_CONVENTION_KEY = "DSG_blockout_axis_convention"
BLOCKOUT_AXIS_CONVENTION_V7 = "V7_NEGATIVE_VIEW_MATRIX_ROW_2_WORLD"


def ensure_axis_empty(context):
    empty = bpy.data.objects.get(AXIS_EMPTY_NAME)
    if empty is None:
        empty = bpy.data.objects.new(AXIS_EMPTY_NAME, None)
        empty.empty_display_type = 'SINGLE_ARROW'
        empty.empty_display_size = 10.0
        context.collection.objects.link(empty)
        props = context.scene.dsg_props
        if props.model_obj:
            empty.location = props.model_obj.matrix_world.translation.copy()
    return empty


def _view3d_window_region(area):
    """Return the actual viewport WINDOW region, even when invoked from the N-panel."""
    if area is None or getattr(area, 'type', None) != 'VIEW_3D':
        return None
    for region in getattr(area, 'regions', ()):
        if getattr(region, 'type', None) == 'WINDOW':
            return region
    return None


def _world_bbox_center(obj):
    if not _valid_obj(obj):
        return Vector((0.0, 0.0, 0.0))
    try:
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return sum(corners, Vector()) / max(1, len(corners))
    except Exception:
        return obj.matrix_world.translation.copy()


def _view_reference_target(context, model, region, rv3d):
    """Find the surface point at the centre of the user's current viewport.

    Rotation changes the insertion direction. Panning changes the centre ray and
    therefore this reference point. When the centre ray misses the IOS, the
    RegionView3D orbit pivot is preserved so a deliberate pan is never ignored.
    """
    pivot = Vector(getattr(rv3d, 'view_location', _world_bbox_center(model)))
    if region is None:
        return pivot, False
    coord = (float(region.width) * 0.5, float(region.height) * 0.5)
    try:
        origin = Vector(view3d_utils.region_2d_to_origin_3d(region, rv3d, coord))
        direction = Vector(view3d_utils.region_2d_to_vector_3d(region, rv3d, coord))
    except Exception:
        return pivot, False
    if direction.length < 1.0e-8:
        return pivot, False
    direction.normalize()
    hit, _normal, _face_index = _raycast_object_from_world_ray(
        context, model, origin, direction)
    if hit is not None:
        return Vector(hit), True
    return pivot, False


def capture_insertion_view_reference(context, model):
    """Capture the complete user view used to define guide insertion.

    The old implementation stored only view rotation. Consequently orbiting
    changed the arrow while panning left its origin frozen at the IOS object
    origin. DSG now stores both components independently:
      * orientation -> insertion axis;
      * viewport centre/pivot -> axis origin and visible reference point.

    Zoom and projection are stored as metadata so later workflows (and a future
    conversational/MCP controller) can reconstruct exactly what the clinician
    approved without making zoom influence the clinical axis.
    """
    area = getattr(context, 'area', None)
    if area is None or getattr(area, 'type', None) != 'VIEW_3D':
        raise RuntimeError('Run this action from a 3D View')
    space = getattr(getattr(area, 'spaces', None), 'active', None)
    rv3d = getattr(space, 'region_3d', None)
    if rv3d is None:
        raise RuntimeError('No active RegionView3D was found')
    region = _view3d_window_region(area)

    # Preserve the exact established direction convention used by DSG.
    vm = rv3d.view_matrix.copy()
    axis = Vector((-vm[2][0], -vm[2][1], -vm[2][2]))
    if axis.length < 1.0e-8:
        axis = Vector((0.0, 0.0, 1.0))
    else:
        axis.normalize()

    target, surface_hit = _view_reference_target(context, model, region, rv3d)
    empty = ensure_axis_empty(context)
    orient_empty_to_vector(empty, axis)
    empty.location = target
    # Preserve the exact v7.0.47 world vector before any later UI operation can
    # reinterpret the arrow transform.
    store_blockout_axis(context, model, axis, source='CURRENT_VIEW_V7_0_47')

    # Keep the arrow readable without letting a large scan create a huge gizmo.
    try:
        diagonal = float(object_bbox_diagonal(model))
        empty.empty_display_size = max(3.0, min(12.0, diagonal * 0.12))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        empty[VIEW_REFERENCE_VERSION_KEY] = int(VIEW_REFERENCE_VERSION)
        empty[VIEW_REFERENCE_LOCATION_KEY] = tuple(float(v) for v in target)
        empty[VIEW_REFERENCE_PIVOT_KEY] = tuple(float(v) for v in rv3d.view_location)
        empty[VIEW_REFERENCE_DISTANCE_KEY] = float(rv3d.view_distance)
        empty[VIEW_REFERENCE_PERSPECTIVE_KEY] = str(rv3d.view_perspective)
        empty[VIEW_REFERENCE_MATRIX_KEY] = _matrix_to_flat_16(vm)
        empty['DSG_view_reference_surface_hit'] = bool(surface_hit)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return empty, axis, target, surface_hit


