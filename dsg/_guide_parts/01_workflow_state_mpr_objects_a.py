STEP_MODEL         = 0
STEP_AXIS          = 0
STEP_BLOCKOUT      = 0
STEP_IMPLANT       = 1
STEP_CONTOUR       = 2
STEP_FRAME         = 3
STEP_SLEEVE        = 4
STEP_IRRIGATION    = 5
STEP_REINFORCEMENT = 6
STEP_DRILL         = 7
STEP_FINAL_CUT     = 8
STEP_NAME          = 9
STEP_DONE          = 9
TOTAL_STEPS        = 10

# Global clinical numbering includes the two stages that precede this module:
# 1 DICOM import, 2 IOS–DICOM alignment, then the ten guide stages 3–12.
GLOBAL_CLINICAL_STEP_OFFSET = 2
GLOBAL_TOTAL_CLINICAL_STEPS = TOTAL_STEPS + GLOBAL_CLINICAL_STEP_OFFSET

GUIDE_FLOW_ORDER_KEY = "DSG_guide_flow_order"
GUIDE_FLOW_ORDER_MODEL_IMPLANT = "MODEL_IMPLANT_CONTOUR_V1"
GUIDE_FLOW_ORDER_IMPLANT_FIRST_LEGACY = "IMPLANT_FIRST_V1"

STEP_LABELS = [
    "Retentive Model",
    "Implant Planning",
    "Outline",
    "Microscrew",
    "Sleeves",
    "Irrigation",
    "Reinforcements",
    "Drill Channels",
    "Final Boolean",
    "Name and Export",
]

STEP_LABELS_ES = [
    "Modelo retentivo",
    "Planificación de implantes",
    "Contorno",
    "Microtornillo",
    "Cilindros",
    "Irrigación",
    "Refuerzos",
    "Canales de fresado",
    "Corte final",
    "Nombre y exportación",
]

def _migrate_model_implant_guide_flow(scene):
    """Migrate earlier scenes to model → implants → contour.

    Only the first three visible stages are remapped. Frame and every later
    stage retain their historical numeric indices, preserving downstream
    geometry and the established animation sequence.
    """
    if scene is None:
        return False
    current_order = str(scene.get(GUIDE_FLOW_ORDER_KEY, '') or '')
    if current_order == GUIDE_FLOW_ORDER_MODEL_IMPLANT:
        return False
    props = getattr(scene, 'dsg_props', None)
    if props is None:
        return False
    try:
        raw_step = int(getattr(props, 'current_step', STEP_MODEL))
    except Exception:
        raw_step = STEP_MODEL

    # Downstream stages keep exactly the same numbers.
    new_step = raw_step
    if raw_step < STEP_FRAME:
        blockout = _selected_retention_preview(props)
        combined = bpy.data.objects.get(COMBINED_NAME)
        retention_ready = bool(_valid_obj(blockout) and blockout.get('DSG_retention_analysis_ready', False))
        passive_ready = _valid_obj(combined)
        has_implants = any(
            _valid_obj(obj) and (str(obj.name).startswith(IMPLANT_PREFIX)
                                 or bool(obj.get('DSG_role', '') == ROLE_IMPLANT))
            for obj in bpy.data.objects)
        contour_ready = False
        try:
            contour_ready = len(get_contour_curve_points()) >= 4 or len(props.contour_points) >= 4
        except Exception:
            contour_ready = False

        if current_order == GUIDE_FLOW_ORDER_IMPLANT_FIRST_LEGACY:
            # v8.0.5/v8.0.6: 0 implants, 1 model, 2 contour.
            if raw_step == 2:
                new_step = STEP_CONTOUR
            elif passive_ready:
                new_step = STEP_IMPLANT
            else:
                new_step = STEP_MODEL
        else:
            # Older/unknown scenes are inferred from actual generated data.
            if contour_ready and passive_ready and has_implants:
                new_step = STEP_CONTOUR
            elif passive_ready or retention_ready:
                new_step = STEP_IMPLANT
            else:
                new_step = STEP_MODEL

    try:
        props.current_step = max(0, min(TOTAL_STEPS - 1, int(new_step)))
        scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        return True
    except Exception:
        return False


# Precisión visual: DSG guarda la proyección que tenía cada View3D al entrar
# en el flujo y usa una proyección ortográfica durante las operaciones de
# medida, paralelismo, contorno y posicionamiento. La orientación, el punto de
# vista y el zoom permanecen libres; solamente se elimina la distorsión focal.
PRECISION_VIEW_BACKUP_KEY = "_dsg_precision_projection_backup_v1"
PRECISION_VIEW_ACTIVE_KEY = "_dsg_precision_projection_active_v1"


def _safe_mpr_owner_area_pointer(scene):
    """Return the active DICOM quad-view area pointer so DSG never rewrites it."""
    try:
        props = getattr(scene, "dicom_wizard_pro", None)
        if props is None or not bool(props.get("safe_mpr_active", False)):
            return 0
        return int(props.get("safe_mpr_area_pointer", 0))
    except Exception:
        return 0


def _iter_precision_region_views(context=None, scene=None):
    """Yield stable keys and RegionView3D objects outside the DICOM MPR area."""
    context = context or bpy.context
    scene = scene or getattr(context, "scene", None)
    if scene is None:
        return
    mpr_pointer = _safe_mpr_owner_area_pointer(scene)
    current_window = getattr(context, "window", None)
    if current_window is not None:
        windows = [current_window]
    else:
        try:
            windows = list(context.window_manager.windows)
        except Exception:
            windows = []
    seen = set()
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", ()):
            if getattr(area, "type", None) != "VIEW_3D":
                continue
            try:
                area_pointer = int(area.as_pointer())
            except Exception:
                area_pointer = id(area)
            if mpr_pointer and area_pointer == mpr_pointer:
                continue
            space = getattr(getattr(area, "spaces", None), "active", None)
            if space is None:
                continue
            candidates = []
            rv3d = getattr(space, "region_3d", None)
            if rv3d is not None:
                candidates.append(("main", rv3d))
            try:
                candidates.extend((f"quad{index}", item)
                                  for index, item in enumerate(space.region_quadviews))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            for suffix, region_view in candidates:
                if region_view is None:
                    continue
                marker = id(region_view)
                if marker in seen:
                    continue
                seen.add(marker)
                yield f"{area_pointer}:{suffix}", area, region_view


def _load_precision_view_backup(scene):
    try:
        payload = json.loads(str(scene.get(PRECISION_VIEW_BACKUP_KEY, "{}")))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _store_precision_view_backup(scene, backup):
    try:
        scene[PRECISION_VIEW_BACKUP_KEY] = json.dumps(backup, sort_keys=True)
        scene[PRECISION_VIEW_ACTIVE_KEY] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def activate_precision_orthographic(context=None, *, force=False):
    """Switch DSG View3D regions to ORTHO while preserving their prior mode."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return 0
    props = getattr(scene, "dsg_props", None)
    if not force and props is not None and not bool(getattr(props, "precision_ortho_lock", True)):
        return 0
    backup = _load_precision_view_backup(scene)
    changed = 0
    for key, area, rv3d in _iter_precision_region_views(context, scene):
        try:
            projection = str(rv3d.view_perspective)
            if key not in backup:
                backup[key] = projection if projection in {"PERSP", "ORTHO", "CAMERA"} else "PERSP"
            if projection != "ORTHO":
                rv3d.view_perspective = "ORTHO"
                changed += 1
            area.tag_redraw()
        except Exception:
            continue
    if backup:
        _store_precision_view_backup(scene, backup)
    return changed


def restore_precision_projection(context=None, *, scene=None):
    """Restore projection modes saved before DSG enabled precision orthographic."""
    context = context or bpy.context
    scene = scene or getattr(context, "scene", None)
    if scene is None:
        return 0
    backup = _load_precision_view_backup(scene)
    restored = 0
    if backup:
        for key, area, rv3d in _iter_precision_region_views(context, scene):
            projection = str(backup.get(key, ""))
            if projection not in {"PERSP", "ORTHO", "CAMERA"}:
                continue
            try:
                rv3d.view_perspective = projection
                area.tag_redraw()
                restored += 1
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    for key in (PRECISION_VIEW_BACKUP_KEY, PRECISION_VIEW_ACTIVE_KEY):
        try:
            del scene[key]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return restored


def _context_projection_is_orthographic(context):
    try:
        rv3d = getattr(context, "region_data", None)
        if rv3d is None and getattr(context, "area", None) is not None:
            rv3d = context.area.spaces.active.region_3d
        return rv3d is not None and str(rv3d.view_perspective) == "ORTHO"
    except Exception:
        return False


def _workflow_closed_boundary_passes(report):
    """Return True when the audited mesh has no open boundary edges.

    For this surgical-guide workflow, the transition to implant planning must
    not be blocked by diagnostics unrelated to an actual opening. Branched or
    degenerate topology remains available in the report for repair/quality
    review, but ``boundary_edges == 0`` is the closure criterion requested by
    the clinical workflow.
    """
    if not isinstance(report, dict) or not bool(report.get('checked')):
        return False
    boundary = report.get('boundary_edges')
    if boundary is None:
        return False
    try:
        return int(boundary) == 0
    except Exception:
        return False


def _mark_closed_boundary_model_accepted(obj, report=None):
    """Persist non-destructive acceptance of a zero-boundary dental model."""
    if not _valid_obj(obj):
        return False
    if report is None:
        report = get_model_topology_report_cached(obj)
    if not _workflow_closed_boundary_passes(report):
        return False
    try:
        obj[SCAN_HOLES_PROCESSED_FLAG] = True
        obj[CLOSED_MODEL_ACCEPTED_FLAG] = True
        obj[EXTERNAL_CLOSED_MODEL_FLAG] = bool(
            not obj.get('DSG_base_closure_status', ''))
        obj['DSG_base_closed_manifold'] = True
        obj['DSG_zero_boundary_closed'] = True
        obj['DSG_open_boundary_edges'] = 0
        obj['DSG_topology_warnings_nonblocking'] = bool(
            int(report.get('branch_edges') or 0)
            or int(report.get('wire_edges') or 0)
            or int(report.get('degenerate_faces') or 0)
            or int(report.get('shells') or 1) > 1)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _schedule_zero_boundary_auto_advance(scene, model):
    """Advance safely outside Panel.draw when a closed model is detected.

    Blender panel drawing should not mutate RNA directly. A one-shot timer
    performs the transition, re-audits the object, and lets the normal update
    callback validate the same zero-boundary rule.
    """
    if scene is None or not _valid_obj(model):
        return False
    key = (str(scene.name), str(model.name))
    if key in _AUTO_CLOSED_MODEL_ADVANCE_PENDING:
        return True
    _AUTO_CLOSED_MODEL_ADVANCE_PENDING.add(key)
    scene_name, model_name = key

    def _advance():
        try:
            target_scene = bpy.data.scenes.get(scene_name)
            target_model = bpy.data.objects.get(model_name)
            if target_scene is None or not _valid_obj(target_model):
                return None
            props = getattr(target_scene, 'dsg_props', None)
            if props is None or int(getattr(props, 'current_step', STEP_MODEL)) != STEP_MODEL:
                return None
            _clear_model_topology_cache()
            report = get_model_topology_report_cached(target_model)
            if not _workflow_closed_boundary_passes(report):
                return None
            _mark_closed_boundary_model_accepted(target_model, report)
            props.model_obj = register_dsg_object(target_model, ROLE_MODEL, target_model.name)
            target_scene['DSG_next_step_gate_blocked'] = False
            target_scene['DSG_zero_boundary_auto_advanced'] = True
            try:
                del target_scene['DSG_next_step_gate_message']
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            props.current_step = STEP_IMPLANT
            target_scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
            _set_obj_hidden(target_model, False, selectable_when_visible=True)
            _tag_dsg_view3d_redraw()
        except Exception as exc:
            print(f'[DSG] Zero-boundary auto-advance warning: {exc}')
        finally:
            _AUTO_CLOSED_MODEL_ADVANCE_PENDING.discard(key)
        return None

    try:
        bpy.app.timers.register(_advance, first_interval=0.01)
        return True
    except Exception:
        _AUTO_CLOSED_MODEL_ADVANCE_PENDING.discard(key)
        return False



def _workflow_model_candidate(props, context=None):
    model = getattr(props, 'model_obj', None) if props is not None else None
    if _valid_obj(model) and getattr(model, 'type', None) == 'MESH':
        return model
    try:
        return _find_aligned_ios(context or bpy.context)
    except Exception:
        return None


def _workflow_frame_candidate(props):
    candidates = [
        getattr(props, 'frame_obj', None) if props is not None else None,
        bpy.data.objects.get(FRAME_NAME),
        bpy.data.objects.get(SLEEVE_SOURCE_FRAME_NAME),
    ]
    for obj in candidates:
        if _valid_obj(obj) and getattr(obj, 'type', None) == 'MESH':
            return obj
    return None


def _workflow_guide_candidate(props):
    try:
        guide = get_active_guide_obj(props)
    except Exception:
        guide = getattr(props, 'guide_obj', None) if props is not None else None
    return guide if _valid_obj(guide) and getattr(guide, 'type', None) == 'MESH' else None



def _workflow_matrix_signature(obj):
    if not _valid_obj(obj):
        return ''
    try:
        values = [round(float(v), 6) for row in obj.matrix_world for v in row]
        return ','.join(f'{v:.6f}' for v in values)
    except Exception:
        return ''


def _workflow_object_signature(obj):
    if not _valid_obj(obj):
        return ''
    mesh_sig = _closed_manifold_geometry_signature(obj) if getattr(obj, 'type', None) == 'MESH' else ''
    payload = f'{getattr(obj, "type", "")}|{mesh_sig}|{_workflow_matrix_signature(obj)}'
    return f'{zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF:08x}'


def _workflow_implant_clinical_record(implant, props):
    """Return a clinically stable implant pose record.

    The previous workflow hashed all 16 values of ``matrix_world`` at six
    decimals.  Detaching an implant from its temporary emergence controller can
    introduce harmless floating-point changes in the matrix even when the
    implant has not moved clinically.  The contour gate then reported a false
    movement.  The clinical plan only depends on the implant centre, its apical
    axis, dimensions and effective scale; roll around the implant's own axis is
    irrelevant for the rotationally symmetric implant/sleeve geometry.
    """
    matrix = implant.matrix_world.copy()
    location = matrix.to_translation()
    basis = matrix.to_3x3()

    apical = basis @ Vector((0.0, 0.0, -1.0))
    if apical.length > 1.0e-12:
        apical.normalize()
    else:
        apical = Vector((0.0, 0.0, -1.0))

    # Quantisation is deliberately much tighter than any clinically meaningful
    # edit, but loose enough to ignore matrix decomposition/re-parenting noise.
    position = [round(float(value), 4) for value in location]
    axis = [round(float(value), 5) for value in apical]
    try:
        scale = [round(abs(float(value)), 5) for value in matrix.to_scale()]
    except Exception:
        scale = [1.0, 1.0, 1.0]

    return {
        'name': str(implant.name),
        'position': position,
        'apical_axis': axis,
        'scale': scale,
        'diameter': round(float(implant.get(
            'DSG_implant_diameter', getattr(props, 'implant_diameter', 0.0))), 4),
        'length': round(float(implant.get(
            'DSG_implant_length', getattr(props, 'implant_length', 0.0))), 4),
    }


def _workflow_implants_signature(props):
    """Hash the clinically relevant implant plan without numerical false positives."""
    try:
        implants = get_all_implant_objects(props)
    except Exception:
        implants = []
    records = []
    for implant in implants:
        try:
            records.append(_workflow_implant_clinical_record(implant, props))
        except Exception:
            records.append({'name': str(getattr(implant, 'name', ''))})
    payload = json.dumps(sorted(records, key=lambda item: item.get('name', '')), sort_keys=True)
    return f'{zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF:08x}'


def _workflow_contour_signature(props):
    try:
        points = get_contour_curve_points()
    except Exception:
        points = []
    if len(points) < 4 and props is not None:
        try:
            points = [Vector(item.co) for item in props.contour_points]
        except Exception:
            points = []
    payload = json.dumps([
        [round(float(point.x), 5), round(float(point.y), 5), round(float(point.z), 5)]
        for point in points
    ])
    return f'{zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF:08x}' if points else ''




def _workflow_checkpoint_collection_name(step):
    return f'{WORKFLOW_CHECKPOINT_COLLECTION_PREFIX}{int(step):02d}'


def _workflow_checkpoint_state_key(step):
    return f'{WORKFLOW_CHECKPOINT_STATE_PREFIX}{int(step):02d}'


def _workflow_checkpoint_managed_object(obj):
    """Return True for DSG-derived geometry that must participate in Back.

    The aligned IOS and DICOM/alignment objects are deliberately excluded. They
    are inputs shared by all DSG steps and must not be duplicated or replaced.
    """
    if not _valid_obj(obj):
        return False
    try:
        if bool(obj.get(WORKFLOW_CHECKPOINT_OBJECT_FLAG, False)):
            return False
        role = str(obj.get('dental_suite_dsg_role', '') or '')
        suite_role = str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, '')) or '')
        if role == ROLE_MODEL or suite_role in {ROLE_IOS_ALIGNED_SUITE, ROLE_IOS_SCAN_SUITE, ROLE_DSG_MODEL_SUITE}:
            return False
        managed_roles = {
            ROLE_BLOCKOUT, ROLE_BLOCKOUT_VISUAL, ROLE_RETENTION_BOUNDARY, ROLE_PASSIVE,
            ROLE_IMPLANT, ROLE_SLEEVE, ROLE_FRAME, ROLE_GUIDE, ROLE_IRRIGATION,
            ROLE_REINFORCEMENT, ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL,
            ROLE_CUTTER, ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
            ROLE_MEASUREMENT,
        }
        if role in managed_roles:
            return True
        name = str(obj.name)
        exact = {
            AXIS_EMPTY_NAME, BLOCKOUT_NAME, BLOCKOUT_VISUAL_NAME, COMBINED_NAME,
            RETENTION_BOUNDARY_NAME, CONTOUR_CURVE_NAME, FRAME_NAME, GUIDE_NAME,
            SLEEVE_SOURCE_FRAME_NAME, ENGRAVE_ANCHOR_NAME, ENGRAVE_PREVIEW_NAME,
            ENGRAVE_CUTTER_NAME, REINFORCEMENT_PREVIEW_NAME,
            REINFORCEMENT_MARKER_NAME, REINFORCEMENT_COMBINED_TMP_NAME,
            MICROSCREW_PREVIEW_NAME, MICROSCREW_VISUAL_PREVIEW_NAME,
            MICROSCREW_MARKER_NAME, MICROSCREW_FRAME_COMBINED_TMP_NAME,
        }
        prefixes = (
            'DSG_Blockout', 'DSG_Retention', IMPLANT_PREFIX, IMPLANT_SAFETY_PREFIX,
            SLEEVE_PREFIX, DRILL_PREFIX, ANIMATED_DRILL_PREFIX,
            ANIMATED_MICROSCREW_PREFIX, MICROSCREW_PREFIX,
            MICROSCREW_VISUAL_PREFIX, IRR_PREVIEW_PREFIX,
            IRR_PREVIEW_PATH_PREFIX, IRR_WALL_PREFIX, 'DSG_Irr_', 'DSG_IrrCut_',
            REINFORCEMENT_PREFIX, REINFORCEMENT_MARKER_PREFIX,
            DRILL_PROTECTION_PREFIX, 'DSG_SleeveApplyTmp_',
            'DSG_FinalSolidCutter', 'DSG_FinalCut_', 'DSG_FinalGuide_Work',
            'DSG_Contour', 'DSG_Frame', 'DSG_Guide', 'DSG_Engrave',
        )
        return name in exact or any(name.startswith(prefix) for prefix in prefixes)
    except Exception:
        return False


def _workflow_checkpoint_serializable_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _workflow_checkpoint_prop_state(props):
    scalar_names = (
        'irr_chain_count', 'irr_paths_json', 'reinforcement_count',
        'microscrew_count', 'microscrew_records_json', 'engrave_has_position',
        'drawing_active', 'irr_drawing_active', 'show_parallel_tools',
        'show_sleeve_window_options', 'show_irrigation_channel_options',
        'show_reinforcement_options', 'show_sequence_panel', 'show_name_tools',
        'show_final_visibility',
        'blockout_confirmed', 'axis_confirmed', 'model_prepared',
        'blockout_relief', 'retention_preset', 'implant_diameter', 'implant_length',
        'tube_radius', 'connector_diameter', 'microscrew_diameter',
        'microscrew_length', 'sleeve_inner_diameter', 'sleeve_wall',
        'sleeve_height', 'sleeve_lateral_opening',
        'sleeve_lateral_opening_width', 'sleeve_lateral_opening_rotation',
        'sleeve_lateral_opening_last_mode', 'irr_inner_diameter',
        'irr_wall_thickness', 'irr_sleeve_channel_mode', 'irrigation_mode',
        'engrave_patient_text', 'engrave_text_size',
    )
    pointer_names = (
        'model_obj', 'implant_obj', 'parallel_master_implant', 'frame_obj',
        'guide_obj', 'dct_object_being_cut', 'dct_object_making_cut',
        'irr_preview_obj', 'reinforcement_preview_obj', 'microscrew_preview_obj',
    )
    scalars = {}
    for name in scalar_names:
        try:
            value = _workflow_checkpoint_serializable_value(getattr(props, name))
            if value is not None:
                scalars[name] = value
        except Exception:
            continue
    pointers = {}
    for name in pointer_names:
        try:
            obj = getattr(props, name)
            pointers[name] = str(obj.name) if _valid_obj(obj) else ''
        except Exception:
            pointers[name] = ''
    contour = []
    try:
        contour = [[float(item.co[0]), float(item.co[1]), float(item.co[2])]
                   for item in props.contour_points]
    except Exception:
        contour = []
    return {'scalars': scalars, 'pointers': pointers, 'contour_points': contour}


def _workflow_checkpoint_scene_state(scene):
    state = {}
    try:
        for key in scene.keys():
            key = str(key)
            if key.startswith(WORKFLOW_CHECKPOINT_STATE_PREFIX):
                continue
            if not (key.startswith('DSG_workflow_') or key.startswith('DSG_next_step_')):
                continue
            value = _workflow_checkpoint_serializable_value(scene.get(key))
            if value is not None:
                state[key] = value
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return state


def _clear_workflow_checkpoint(scene, step):
    name = _workflow_checkpoint_collection_name(step)
    collection = bpy.data.collections.get(name)
    if collection is not None:
        for obj in list(collection.objects):
            try:
                data = getattr(obj, 'data', None)
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and getattr(data, 'users', 1) == 0:
                    try:
                        bpy.data.batch_remove(ids=(data,))
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bpy.data.collections.remove(collection)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if scene is not None:
        try:
            del scene[_workflow_checkpoint_state_key(step)]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _clear_workflow_checkpoints_after(scene, step):
    for candidate in range(int(step) + 1, TOTAL_STEPS):
        _clear_workflow_checkpoint(scene, candidate)


def _clear_all_workflow_checkpoints(scene):
    for candidate in range(TOTAL_STEPS):
        _clear_workflow_checkpoint(scene, candidate)


def _capture_workflow_checkpoint(context, step):
    """Store the completed stage before advancing to the next one."""
    global _WORKFLOW_CHECKPOINT_ACTIVE
    scene = getattr(context, 'scene', None)
    props = getattr(scene, 'dsg_props', None) if scene is not None else None
    if scene is None or props is None or _WORKFLOW_CHECKPOINT_ACTIVE:
        return False
    step = max(STEP_MODEL, min(STEP_NAME, int(step)))
    _WORKFLOW_CHECKPOINT_ACTIVE = True
    try:
        _clear_workflow_checkpoint(scene, step)
        name = _workflow_checkpoint_collection_name(step)
        collection = bpy.data.collections.new(name)
        ensure_dsg_root_collection().children.link(collection)
        collection.hide_viewport = True
        collection.hide_render = True

        originals = [obj for obj in list(scene.objects)
                     if _workflow_checkpoint_managed_object(obj)]
        original_to_copy = {}
        for index, obj in enumerate(originals):
            clone = obj.copy()
            source_name = str(obj.name)
            source_role = str(obj.get('dental_suite_dsg_role', '') or '')
            # Only meshes that are modified in place by later stages need an
            # independent datablock. Additive/reference objects can safely share
            # their data with the hidden checkpoint, reducing memory and pauses.
            deep_copy_data = bool(
                source_role in {ROLE_FRAME, ROLE_GUIDE}
                or source_name == GUIDE_NAME
                or source_name.startswith(('DSG_FinalGuide', 'DSG_FinalCut_')))
            if getattr(obj, 'data', None) is not None and deep_copy_data:
                try:
                    clone.data = obj.data.copy()
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            source_suite_role = str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, '')) or '')
            source_collections = [str(item.name) for item in getattr(obj, 'users_collection', ())
                                  if not str(item.name).startswith(WORKFLOW_CHECKPOINT_COLLECTION_PREFIX)]
            source_parent = str(obj.parent.name) if _valid_obj(getattr(obj, 'parent', None)) else ''
            clone.name = f'{name}__{index:04d}__{source_name}'
            clone[WORKFLOW_CHECKPOINT_OBJECT_FLAG] = True
            clone[WORKFLOW_CHECKPOINT_SOURCE_NAME] = source_name
            clone[WORKFLOW_CHECKPOINT_SOURCE_ROLE] = source_role
            clone[WORKFLOW_CHECKPOINT_SOURCE_SUITE_ROLE] = source_suite_role
            clone[WORKFLOW_CHECKPOINT_SOURCE_COLLECTIONS] = json.dumps(source_collections)
            clone[WORKFLOW_CHECKPOINT_SOURCE_PARENT] = source_parent
            clone[WORKFLOW_CHECKPOINT_SOURCE_HIDE_VIEWPORT] = bool(obj.hide_viewport)
            clone[WORKFLOW_CHECKPOINT_SOURCE_HIDE_RENDER] = bool(obj.hide_render)
            clone[WORKFLOW_CHECKPOINT_SOURCE_HIDE_SELECT] = bool(obj.hide_select)
            clone[WORKFLOW_CHECKPOINT_SOURCE_DISPLAY_TYPE] = str(getattr(obj, 'display_type', 'TEXTURED'))
            clone[WORKFLOW_CHECKPOINT_SOURCE_SHOW_IN_FRONT] = bool(getattr(obj, 'show_in_front', False))
            clone[WORKFLOW_CHECKPOINT_SOURCE_MATRIX_WORLD] = [
                float(value) for row in obj.matrix_world for value in row]
            masked_values = {}
            for masked_key in WORKFLOW_CHECKPOINT_BOOLEAN_MASK_KEYS:
                try:
                    if masked_key in clone:
                        masked_values[masked_key] = bool(clone.get(masked_key, False))
                        clone[masked_key] = False
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            clone[WORKFLOW_CHECKPOINT_MASKED_VALUES] = json.dumps(masked_values, separators=(',', ':'))
            clone['dental_suite_dsg_role'] = '__CHECKPOINT__'
            clone[SUITE_ROLE_KEY] = '__CHECKPOINT__'
            clone[LEGACY_ROLE_KEY] = '__CHECKPOINT__'
            source_world = obj.matrix_world.copy()
            clone.parent = None
            clone.matrix_world = source_world
            collection.objects.link(clone)
            clone.hide_viewport = True
            clone.hide_render = True
            clone.hide_select = True
            original_to_copy[obj] = clone

        # Point object references inside modifiers/constraints to the checkpoint
        # copies, so deleting live geometry later cannot damage the snapshot.
        for original, clone in original_to_copy.items():
            for modifier in getattr(clone, 'modifiers', ()):
                try:
                    target = getattr(modifier, 'object', None)
                    if target in original_to_copy:
                        modifier.object = original_to_copy[target]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            for constraint in getattr(clone, 'constraints', ()):
                try:
                    target = getattr(constraint, 'target', None)
                    if target in original_to_copy:
                        constraint.target = original_to_copy[target]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

        active = getattr(context.view_layer.objects, 'active', None)
        payload = {
            'version': WORKFLOW_CHECKPOINT_VERSION,
            'step': step,
            'props': _workflow_checkpoint_prop_state(props),
            'scene': _workflow_checkpoint_scene_state(scene),
            'active_object': str(active.name) if _valid_obj(active) else '',
        }
        scene[_workflow_checkpoint_state_key(step)] = json.dumps(payload, separators=(',', ':'))
        return True
    except Exception as exc:
        print(f'[DSG] Workflow checkpoint capture warning at step {step}: {exc}')
        _clear_workflow_checkpoint(scene, step)
        return False
    finally:
        _WORKFLOW_CHECKPOINT_ACTIVE = False


def _restore_workflow_checkpoint(context, step):
    """Restore exact geometry saved after completing ``step``."""
    global _WORKFLOW_CHECKPOINT_ACTIVE
    scene = getattr(context, 'scene', None)
    props = getattr(scene, 'dsg_props', None) if scene is not None else None
    if scene is None or props is None or _WORKFLOW_CHECKPOINT_ACTIVE:
        return False
    step = max(STEP_MODEL, min(STEP_NAME, int(step)))
    collection = bpy.data.collections.get(_workflow_checkpoint_collection_name(step))
    raw_state = str(scene.get(_workflow_checkpoint_state_key(step), '') or '')
    if collection is None or not raw_state:
        return False
    try:
        payload = json.loads(raw_state)
    except Exception:
        return False

    _WORKFLOW_CHECKPOINT_ACTIVE = True
    try:
        props.drawing_active = False
        props.irr_drawing_active = False
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []
        for obj in list(scene.objects):
            if _workflow_checkpoint_managed_object(obj):
                safe_remove_object(obj)

        checkpoint_objects = list(collection.objects)
        checkpoint_to_live = {}
        source_to_live = {}
        for checkpoint in checkpoint_objects:
            source_name = str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_NAME, '') or '')
            if not source_name:
                continue
            clone = checkpoint.copy()
            if getattr(checkpoint, 'data', None) is not None:
                try:
                    clone.data = checkpoint.data.copy()
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            clone.name = source_name
            try:
                clone.data.name = source_name + '_Mesh'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            source_role = str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_ROLE, '') or '')
            source_suite_role = str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_SUITE_ROLE, '') or '')
            try:
                masked_values = json.loads(str(checkpoint.get(WORKFLOW_CHECKPOINT_MASKED_VALUES, '{}') or '{}'))
                for masked_key, masked_value in masked_values.items():
                    clone[str(masked_key)] = bool(masked_value)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            for key in (
                WORKFLOW_CHECKPOINT_OBJECT_FLAG, WORKFLOW_CHECKPOINT_SOURCE_NAME,
                WORKFLOW_CHECKPOINT_SOURCE_ROLE, WORKFLOW_CHECKPOINT_SOURCE_SUITE_ROLE,
                WORKFLOW_CHECKPOINT_SOURCE_COLLECTIONS, WORKFLOW_CHECKPOINT_SOURCE_PARENT,
                WORKFLOW_CHECKPOINT_SOURCE_HIDE_VIEWPORT, WORKFLOW_CHECKPOINT_SOURCE_HIDE_RENDER,
                WORKFLOW_CHECKPOINT_SOURCE_HIDE_SELECT, WORKFLOW_CHECKPOINT_SOURCE_DISPLAY_TYPE,
                WORKFLOW_CHECKPOINT_SOURCE_SHOW_IN_FRONT, WORKFLOW_CHECKPOINT_SOURCE_MATRIX_WORLD,
                WORKFLOW_CHECKPOINT_MASKED_VALUES,
            ):
                try:
                    del clone[key]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            clone['dental_suite_dsg_role'] = source_role
            if source_suite_role:
                clone[SUITE_ROLE_KEY] = source_suite_role
                clone[LEGACY_ROLE_KEY] = source_suite_role
            else:
                for role_key in (SUITE_ROLE_KEY, LEGACY_ROLE_KEY):
                    try:
                        del clone[role_key]
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
            clone.parent = None
            clone.hide_viewport = bool(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_HIDE_VIEWPORT, False))
            clone.hide_render = bool(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_HIDE_RENDER, False))
            clone.hide_select = bool(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_HIDE_SELECT, False))
            try:
                clone.display_type = str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_DISPLAY_TYPE, 'TEXTURED'))
                clone.show_in_front = bool(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_SHOW_IN_FRONT, False))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

            linked = False
            try:
                collection_names = json.loads(str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_COLLECTIONS, '[]') or '[]'))
            except Exception:
                collection_names = []
            for collection_name in collection_names:
                target_collection = bpy.data.collections.get(str(collection_name))
                if target_collection is None:
                    target_collection = ensure_dsg_collection(str(collection_name))
                try:
                    target_collection.objects.link(clone)
                    linked = True
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            if not linked:
                link_object(context, clone)
            checkpoint_to_live[checkpoint] = clone
            source_to_live[source_name] = clone

        for checkpoint, clone in checkpoint_to_live.items():
            parent_name = str(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_PARENT, '') or '')
            if parent_name:
                try:
                    clone.parent = source_to_live.get(parent_name) or bpy.data.objects.get(parent_name)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                flat_matrix = list(checkpoint.get(WORKFLOW_CHECKPOINT_SOURCE_MATRIX_WORLD, ()))
                if len(flat_matrix) == 16:
                    clone.matrix_world = Matrix((
                        flat_matrix[0:4], flat_matrix[4:8],
                        flat_matrix[8:12], flat_matrix[12:16]))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            for modifier in getattr(clone, 'modifiers', ()):
                try:
                    target = getattr(modifier, 'object', None)
                    if target in checkpoint_to_live:
                        modifier.object = checkpoint_to_live[target]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            for constraint in getattr(clone, 'constraints', ()):
                try:
                    target = getattr(constraint, 'target', None)
                    if target in checkpoint_to_live:
                        constraint.target = checkpoint_to_live[target]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

        prop_state = payload.get('props', {}) if isinstance(payload, dict) else {}
        for name, value in prop_state.get('scalars', {}).items():
            try:
                setattr(props, name, value)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            props.contour_points.clear()
            for coordinates in prop_state.get('contour_points', []):
                item = props.contour_points.add()
                item.co = coordinates
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        for name, object_name in prop_state.get('pointers', {}).items():
            try:
                setattr(props, name, bpy.data.objects.get(str(object_name)) if object_name else None)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        for key in list(scene.keys()):
            key = str(key)
            if key.startswith('DSG_workflow_') or key.startswith('DSG_next_step_'):
                if not key.startswith(WORKFLOW_CHECKPOINT_STATE_PREFIX):
                    try:
                        del scene[key]
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
        for key, value in payload.get('scene', {}).items():
            try:
                scene[str(key)] = value
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        active_name = str(payload.get('active_object', '') or '')
        active = source_to_live.get(active_name) or bpy.data.objects.get(active_name)
        if _valid_obj(active):
            set_active(context, active)
        _clear_workflow_checkpoints_after(scene, step)
        return True
    except Exception as exc:
        print(f'[DSG] Workflow checkpoint restore warning at step {step}: {exc}')
        return False
    finally:
        _WORKFLOW_CHECKPOINT_ACTIVE = False


def _workflow_stage_signature(scene, props, stage):
    passive = get_confirmed_passive_model_obj()
    frame = _workflow_frame_candidate(props)
    guide = _workflow_guide_candidate(props)
    if stage == STEP_MODEL:
        return _workflow_object_signature(passive)
    if stage == STEP_IMPLANT:
        return _workflow_implants_signature(props)
    if stage == STEP_CONTOUR:
        return _workflow_contour_signature(props)
    if stage == STEP_FRAME:
        return _workflow_object_signature(frame)
    if stage in {STEP_SLEEVE, STEP_IRRIGATION, STEP_REINFORCEMENT, STEP_DRILL, STEP_FINAL_CUT, STEP_NAME}:
        return _workflow_object_signature(guide)
    return ''


def _workflow_store_signature(scene, key, value):
    if scene is None:
        return
    try:
        scene[key] = str(value or '')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _workflow_signature_changed(scene, key, current_value):
    if scene is None:
        return False
    previous = str(scene.get(key, '') or '')
    current = str(current_value or '')
    return bool(previous and current and previous != current)



def _clear_guide_outputs_for_model_change(context, keep_model=None):
    """Clear only guide-dependent data after choosing a different IOS.

    DICOM data and the Alignment state are preserved. Every DSG object derived
    from the previous IOS is removed because retaining implants, contours or a
    final guide against a different master model would be clinically unsafe.
    """
    scene = getattr(context, 'scene', None)
    props = getattr(scene, 'dsg_props', None) if scene is not None else None
    if scene is not None:
        _clear_all_workflow_checkpoints(scene)

    if props is not None:
        try:
            props.drawing_active = False
            props.irr_drawing_active = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    removable_roles = {
        ROLE_BLOCKOUT, ROLE_BLOCKOUT_VISUAL, ROLE_RETENTION_BOUNDARY, ROLE_PASSIVE, ROLE_IMPLANT,
        ROLE_SLEEVE, ROLE_FRAME, ROLE_GUIDE, ROLE_IRRIGATION,
        ROLE_REINFORCEMENT, ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL,
        ROLE_CUTTER, ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
        ROLE_MEASUREMENT,
    }
    exact_names = {
        BLOCKOUT_NAME, BLOCKOUT_VISUAL_NAME, COMBINED_NAME, RETENTION_BOUNDARY_NAME,
        CONTOUR_CURVE_NAME, FRAME_NAME, GUIDE_NAME, SLEEVE_SOURCE_FRAME_NAME,
        ENGRAVE_ANCHOR_NAME, ENGRAVE_PREVIEW_NAME, ENGRAVE_CUTTER_NAME,
        REINFORCEMENT_PREVIEW_NAME, REINFORCEMENT_MARKER_NAME,
        REINFORCEMENT_COMBINED_TMP_NAME, MICROSCREW_PREVIEW_NAME,
        MICROSCREW_MARKER_NAME, MICROSCREW_FRAME_COMBINED_TMP_NAME,
        'DSG_Orig_Copy', 'DSG_Blockout_Copy',
    }
    exact_names.update(RETENTION_PREVIEW_NAMES.values())
    prefixes = (
        IMPLANT_PREFIX, IMPLANT_SAFETY_PREFIX, SLEEVE_PREFIX, DRILL_PREFIX,
        ANIMATED_DRILL_PREFIX, ANIMATED_MICROSCREW_PREFIX,
        IRR_PREVIEW_PREFIX, IRR_PREVIEW_PATH_PREFIX, IRR_WALL_PREFIX,
        'DSG_Irr_', 'DSG_IrrCut_', REINFORCEMENT_PREFIX,
        REINFORCEMENT_MARKER_PREFIX, MICROSCREW_PREFIX,
        DRILL_PROTECTION_PREFIX, 'DSG_SleeveApplyTmp_',
        'DSG_FinalSolidCutter', 'DSG_FinalCut_', 'DSG_FinalGuide_Work',
        'DSG_Retention_', 'DSG_Blockout',
    )

    for obj in list(bpy.data.objects):
        if obj == keep_model:
            continue
        try:
            role = str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, '')) or '')
            matches = (
                role in removable_roles
                or obj.name in exact_names
                or any(obj.name.startswith(prefix) for prefix in prefixes)
            )
        except Exception:
            matches = False
        if matches:
            safe_remove_object(obj)

    _IMPLANT_STEP_RETURN_STATE.pop(str(getattr(scene, 'name', '')), None)
    _IMPLANT_STEP_RESTORE_PENDING.discard(str(getattr(scene, 'name', '')))
    try:
        _clear_retention_geometry_cache()
        _clear_model_topology_cache()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if props is not None:
        try:
            props.contour_points.clear()
            props.implant_obj = None
            props.parallel_master_implant = None
            props.frame_obj = None
            props.guide_obj = None
            props.dct_object_being_cut = None
            props.dct_object_making_cut = None
            props.irr_preview_obj = None
            props.reinforcement_preview_obj = None
            props.microscrew_preview_obj = None
            props.irr_chain_count = 0
            props.irr_paths_json = '[]'
            props.reinforcement_count = 0
            props.microscrew_count = 0
            props.microscrew_records_json = '[]'
            props.engrave_has_position = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    if scene is not None:
        for key in (
            WORKFLOW_PASSIVE_SIGNATURE_KEY, WORKFLOW_IMPLANT_SIGNATURE_KEY,
            WORKFLOW_IMPLANT_SIGNATURE_SCHEMA_KEY,
            WORKFLOW_CONTOUR_SIGNATURE_KEY, WORKFLOW_FRAME_SIGNATURE_KEY,
            WORKFLOW_SLEEVE_SIGNATURE_KEY, WORKFLOW_IRRIGATION_SIGNATURE_KEY,
            WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, WORKFLOW_DRILL_SIGNATURE_KEY,
            WORKFLOW_IRRIGATION_RESOLVED_KEY, WORKFLOW_REINFORCEMENT_RESOLVED_KEY,
            WORKFLOW_IMPLANTS_CONFIRMED_KEY, WORKFLOW_GATE_MESSAGE_KEY,
            WORKFLOW_GATE_TARGET_KEY, WORKFLOW_GATE_FALLBACK_KEY,
            'DSG_workflow_contour_confirmed', 'DSG_workflow_contour_point_count',
            'DSG_next_step_gate_message',
        ):
            try:
                del scene[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        scene['DSG_next_step_gate_blocked'] = False
        scene['DSG_workflow_last_invalidation'] = 'source_model_changed'
        scene['DSG_workflow_last_invalidation_step'] = int(STEP_MODEL)
    return True


def _invalidate_workflow_after(context, changed_step, *, reason='upstream_changed'):
    """Remove only outputs that depend on a changed upstream stage.

    Back navigation itself never calls this function.  It is called only when
    the user reconfirms a stage with a different geometry/transform signature.
    """
    scene = getattr(context, 'scene', None)
    props = getattr(scene, 'dsg_props', None) if scene is not None else None
    changed_step = int(changed_step)

    roles = set()
    exact_names = set()
    prefixes = set()
    if changed_step <= STEP_IMPLANT:
        roles.update({
            ROLE_FRAME, ROLE_GUIDE, ROLE_SLEEVE, ROLE_IRRIGATION,
            ROLE_REINFORCEMENT, ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL,
            ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
        })
        exact_names.add(CONTOUR_CURVE_NAME)
    elif changed_step == STEP_CONTOUR:
        roles.update({
            ROLE_FRAME, ROLE_GUIDE, ROLE_SLEEVE, ROLE_IRRIGATION,
            ROLE_REINFORCEMENT, ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL,
            ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
        })
    elif changed_step == STEP_FRAME:
        roles.update({
            ROLE_GUIDE, ROLE_SLEEVE, ROLE_IRRIGATION, ROLE_REINFORCEMENT,
            ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
        })
    elif changed_step == STEP_SLEEVE:
        roles.update({ROLE_IRRIGATION, ROLE_REINFORCEMENT, ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE})
    elif changed_step == STEP_IRRIGATION:
        roles.update({ROLE_REINFORCEMENT, ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE})
    elif changed_step == STEP_REINFORCEMENT:
        roles.update({ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE})
    elif changed_step == STEP_DRILL:
        roles.update({ROLE_ENGRAVE})

    for obj in list(bpy.data.objects):
        try:
            role = str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, '')) or '')
            matches = role in roles or obj.name in exact_names or any(obj.name.startswith(prefix) for prefix in prefixes)
        except Exception:
            matches = False
        if matches:
            safe_remove_object(obj)

    if props is not None:
        try:
            if changed_step <= STEP_IMPLANT:
                props.contour_points.clear()
                props.frame_obj = None
                props.guide_obj = None
                props.dct_object_being_cut = None
            elif changed_step == STEP_CONTOUR:
                props.frame_obj = None
                props.guide_obj = None
                props.dct_object_being_cut = None
            elif changed_step == STEP_FRAME:
                props.guide_obj = None
                props.dct_object_being_cut = None
            props.irr_preview_obj = None
            props.reinforcement_preview_obj = None
            props.microscrew_preview_obj = None
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    if scene is not None:
        clear_keys = []
        if changed_step <= STEP_IMPLANT:
            clear_keys += [WORKFLOW_CONTOUR_SIGNATURE_KEY, WORKFLOW_FRAME_SIGNATURE_KEY,
                           WORKFLOW_SLEEVE_SIGNATURE_KEY, WORKFLOW_IRRIGATION_SIGNATURE_KEY,
                           WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, WORKFLOW_DRILL_SIGNATURE_KEY,
                           WORKFLOW_IRRIGATION_RESOLVED_KEY, WORKFLOW_REINFORCEMENT_RESOLVED_KEY,
                           'DSG_workflow_contour_confirmed', 'DSG_workflow_contour_point_count']
        elif changed_step == STEP_CONTOUR:
            clear_keys += [WORKFLOW_FRAME_SIGNATURE_KEY, WORKFLOW_SLEEVE_SIGNATURE_KEY,
                           WORKFLOW_IRRIGATION_SIGNATURE_KEY, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY,
                           WORKFLOW_DRILL_SIGNATURE_KEY, WORKFLOW_IRRIGATION_RESOLVED_KEY,
                           WORKFLOW_REINFORCEMENT_RESOLVED_KEY]
        elif changed_step == STEP_FRAME:
            clear_keys += [WORKFLOW_SLEEVE_SIGNATURE_KEY, WORKFLOW_IRRIGATION_SIGNATURE_KEY,
                           WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, WORKFLOW_DRILL_SIGNATURE_KEY,
                           WORKFLOW_IRRIGATION_RESOLVED_KEY, WORKFLOW_REINFORCEMENT_RESOLVED_KEY]
        elif changed_step == STEP_SLEEVE:
            clear_keys += [WORKFLOW_IRRIGATION_SIGNATURE_KEY, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY,
                           WORKFLOW_DRILL_SIGNATURE_KEY, WORKFLOW_IRRIGATION_RESOLVED_KEY,
                           WORKFLOW_REINFORCEMENT_RESOLVED_KEY]
        elif changed_step == STEP_IRRIGATION:
            clear_keys += [WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, WORKFLOW_DRILL_SIGNATURE_KEY,
                           WORKFLOW_REINFORCEMENT_RESOLVED_KEY]
        elif changed_step == STEP_REINFORCEMENT:
            clear_keys += [WORKFLOW_DRILL_SIGNATURE_KEY]
        for key in clear_keys:
            try:
                del scene[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            scene['DSG_workflow_last_invalidation'] = str(reason)
            scene['DSG_workflow_last_invalidation_step'] = int(changed_step)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _workflow_contour_count(props):
    try:
        count = len(get_contour_curve_points())
    except Exception:
        count = 0
    if count < 4 and props is not None:
        try:
            count = max(count, len(props.contour_points))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return int(count)


def _workflow_irrigation_resolved(scene, guide, requested_step):
    if bool(scene.get(WORKFLOW_IRRIGATION_RESOLVED_KEY, False)):
        return True
    if _valid_obj(guide):
        if bool(guide.get('DSG_irrigation_skipped', False)):
            return True
        if str(guide.get('DSG_irrigation_mode', '') or ''):
            return True
        if int(guide.get('DSG_irrigation_cut_count', 0) or 0) > 0:
            return True
        # A later tangible result proves the optional irrigation decision was
        # already resolved in older files that predate the explicit marker.
        if (int(guide.get('DSG_reinforcement_count', 0) or 0) > 0
                or int(guide.get('DSG_drill_channel_count', 0) or 0) > 0
                or str(guide.get('DSG_final_pipeline', '') or '')):
            return True
    return False


def _workflow_reinforcement_resolved(scene, guide, requested_step):
    if bool(scene.get(WORKFLOW_REINFORCEMENT_RESOLVED_KEY, False)):
        return True
    if _valid_obj(guide):
        if bool(guide.get('DSG_reinforcement_skipped', False)):
            return True
        if int(guide.get('DSG_reinforcement_count', 0) or 0) > 0:
            return True
        if (int(guide.get('DSG_drill_channel_count', 0) or 0) > 0
                or str(guide.get('DSG_final_pipeline', '') or '')):
            return True
    return False


def _workflow_requirement_report(context, target_step, *, scene=None):
    """Audit every prerequisite needed to enter ``target_step``.

    The report always points to the earliest clinical stage that can repair the
    missing dependency.  Optional stages are considered resolved only after an
    explicit Apply/Skip action or when a later tangible guide result proves the
    decision was already completed in an older file.
    """
    scene = scene or getattr(context, 'scene', None)
    target_step = max(STEP_MODEL, min(STEP_NAME, int(target_step)))
    if scene is None:
        return {'ok': False, 'target': target_step, 'fallback': STEP_MODEL,
                'message_en': 'No active DSG scene', 'message_es': 'No hay una escena DSG activa'}
    props = getattr(scene, 'dsg_props', None)
    if props is None:
        return {'ok': False, 'target': target_step, 'fallback': STEP_MODEL,
                'message_en': 'DSG properties are unavailable', 'message_es': 'Las propiedades DSG no están disponibles'}

    model = _workflow_model_candidate(props, context)
    if not _valid_obj(model):
        return {'ok': False, 'target': target_step, 'fallback': STEP_MODEL,
                'message_en': 'Complete IOS/DICOM alignment before continuing',
                'message_es': 'Completa el alineamiento IOS/DICOM antes de continuar'}

    passive = None
    implants = []
    guide = _workflow_guide_candidate(props)
    frame = _workflow_frame_candidate(props)

    if target_step >= STEP_CONTOUR:
        passive = get_confirmed_passive_model_obj()
        if not _valid_obj(passive):
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'Confirm the retentive model before continuing',
                    'message_es': 'Confirma el modelo retentivo antes de continuar'}
        confirmed_state = bool(
            passive.get('DSG_retentive_model_confirmed', False)
            or str(passive.get('DSG_confirmation_state', '')).upper() == 'CONFIRMED')
        if not confirmed_state:
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'Confirm the retentive model before continuing',
                    'message_es': 'Confirma el modelo retentivo antes de continuar'}
        stored_passive_sig = str(scene.get(WORKFLOW_PASSIVE_SIGNATURE_KEY, '') or '')
        if stored_passive_sig and stored_passive_sig != _workflow_object_signature(passive):
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'The retentive model changed after confirmation; confirm it again',
                    'message_es': 'El modelo retentivo cambió después de confirmarlo; confírmalo de nuevo'}
        try:
            implants = get_all_implant_objects(props)
        except Exception:
            implants = []
        if not implants:
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'Create and confirm at least one implant before continuing',
                    'message_es': 'Crea y confirma al menos un implante antes de continuar'}
        try:
            violations = get_interimplant_spacing_violations(props)
        except Exception:
            violations = []
        if violations:
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'Correct the interimplant spacing before continuing',
                    'message_es': 'Corrige la separación entre implantes antes de continuar'}
        stored_implant_sig = str(scene.get(WORKFLOW_IMPLANT_SIGNATURE_KEY, '') or '')
        current_implant_sig = _workflow_implants_signature(props)
        stored_implant_schema = int(scene.get(WORKFLOW_IMPLANT_SIGNATURE_SCHEMA_KEY, 0) or 0)
        if stored_implant_sig and stored_implant_schema != WORKFLOW_IMPLANT_SIGNATURE_SCHEMA:
            # One-time migration from the old full-matrix hash.  Existing scenes
            # confirmed in v8.2.7 must not be blocked merely because v8.2.8 uses
            # a clinically tolerant pose signature.
            all_confirmed = all(bool(implant.get('DSG_implant_confirmed', False))
                                for implant in implants)
            if all_confirmed:
                scene[WORKFLOW_IMPLANT_SIGNATURE_KEY] = current_implant_sig
                scene[WORKFLOW_IMPLANT_SIGNATURE_SCHEMA_KEY] = WORKFLOW_IMPLANT_SIGNATURE_SCHEMA
                stored_implant_sig = current_implant_sig
                stored_implant_schema = WORKFLOW_IMPLANT_SIGNATURE_SCHEMA
        if stored_implant_sig and stored_implant_sig != current_implant_sig:
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'An implant was moved after confirmation; confirm the implant plan again',
                    'message_es': 'Se movió un implante después de confirmarlo; confirma de nuevo la planificación'}

    if target_step >= STEP_FRAME:
        contour_count = _workflow_contour_count(props)
        # Once a frame/guide exists, the contour has already been consumed and
        # may have been removed by a legacy file cleanup.
        if contour_count < 4 and not _valid_obj(frame) and not _valid_obj(guide):
            return {'ok': False, 'target': target_step, 'fallback': STEP_CONTOUR,
                    'message_en': 'Draw and confirm a closed outline with at least four points',
                    'message_es': 'Dibuja y confirma un contorno cerrado con al menos cuatro puntos'}
        stored_contour_sig = str(scene.get(WORKFLOW_CONTOUR_SIGNATURE_KEY, '') or '')
        current_contour_sig = _workflow_contour_signature(props)
        if stored_contour_sig and current_contour_sig and stored_contour_sig != current_contour_sig:
            return {'ok': False, 'target': target_step, 'fallback': STEP_CONTOUR,
                    'message_en': 'The outline changed after confirmation; confirm it again',
                    'message_es': 'El contorno cambió después de confirmarlo; confírmalo de nuevo'}

    if target_step >= STEP_SLEEVE:
        if not _valid_obj(frame) and not (_valid_obj(guide) and bool(guide.get('DSG_sleeves_applied', False))):
            return {'ok': False, 'target': target_step, 'fallback': STEP_FRAME,
                    'message_en': 'Create and confirm the frame before continuing',
                    'message_es': 'Crea y confirma la estructura antes de continuar'}
        try:
            pending_micro = get_pending_microscrew_preview(props)
            unapplied_micro = get_confirmed_microscrew_objects()
        except Exception:
            pending_micro, unapplied_micro = None, []
        if _valid_obj(pending_micro) or unapplied_micro:
            return {'ok': False, 'target': target_step, 'fallback': STEP_FRAME,
                    'message_en': 'Apply or discard all pending microscrews before continuing',
                    'message_es': 'Aplica o descarta todos los microtornillos pendientes antes de continuar'}
        stored_frame_sig = str(scene.get(WORKFLOW_FRAME_SIGNATURE_KEY, '') or '')
        current_frame_sig = _workflow_object_signature(frame)
        if stored_frame_sig and current_frame_sig and stored_frame_sig != current_frame_sig:
            return {'ok': False, 'target': target_step, 'fallback': STEP_FRAME,
                    'message_en': 'The frame changed after confirmation; confirm it again',
                    'message_es': 'La estructura cambió después de confirmarla; confírmala de nuevo'}

    if target_step >= STEP_IRRIGATION:
        guide = _workflow_guide_candidate(props)
        _restore_sleeve_metadata_if_derivable(props, guide)
        if not (_valid_obj(guide) and bool(guide.get('DSG_sleeves_applied', False))):
            return {'ok': False, 'target': target_step, 'fallback': STEP_SLEEVE,
                    'message_en': 'Create and apply the sleeves before continuing',
                    'message_es': 'Crea y aplica los cilindros antes de continuar'}
        stored_sleeve_sig = str(scene.get(WORKFLOW_SLEEVE_SIGNATURE_KEY, '') or '')
        current_guide_sig = _workflow_object_signature(guide)
        if stored_sleeve_sig and current_guide_sig and stored_sleeve_sig != current_guide_sig and not _workflow_irrigation_resolved(scene, guide, target_step):
            return {'ok': False, 'target': target_step, 'fallback': STEP_SLEEVE,
                    'message_en': 'The sleeve guide changed before irrigation was resolved; rebuild or confirm the sleeves',
                    'message_es': 'La guía con cilindros cambió antes de resolver la irrigación; reconstruye o confirma los cilindros'}

    if target_step >= STEP_REINFORCEMENT:
        if not _workflow_irrigation_resolved(scene, guide, target_step):
            return {'ok': False, 'target': target_step, 'fallback': STEP_IRRIGATION,
                    'message_en': 'Apply irrigation or explicitly continue without it',
                    'message_es': 'Aplica la irrigación o continúa explícitamente sin ella'}
        stored_irrigation_sig = str(scene.get(WORKFLOW_IRRIGATION_SIGNATURE_KEY, '') or '')
        current_irrigation_sig = _workflow_object_signature(guide)
        if stored_irrigation_sig and current_irrigation_sig and stored_irrigation_sig != current_irrigation_sig and not _workflow_reinforcement_resolved(scene, guide, target_step):
            return {'ok': False, 'target': target_step, 'fallback': STEP_IRRIGATION,
                    'message_en': 'The guide changed after irrigation; resolve irrigation again',
                    'message_es': 'La guía cambió después de la irrigación; resuelve de nuevo la irrigación'}

    if target_step >= STEP_DRILL:
        if not _workflow_reinforcement_resolved(scene, guide, target_step):
            return {'ok': False, 'target': target_step, 'fallback': STEP_REINFORCEMENT,
                    'message_en': 'Apply the reinforcements or explicitly continue without them',
                    'message_es': 'Aplica los refuerzos o continúa explícitamente sin ellos'}
        stored_reinforcement_sig = str(scene.get(WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, '') or '')
        current_reinforcement_sig = _workflow_object_signature(guide)
        if (stored_reinforcement_sig and current_reinforcement_sig
                and stored_reinforcement_sig != current_reinforcement_sig
                and int(guide.get('DSG_drill_channel_count', 0) or 0) <= 0
                and not bool(guide.get('DSG_drill_insertion_protected', False))):
            return {'ok': False, 'target': target_step, 'fallback': STEP_REINFORCEMENT,
                    'message_en': 'The guide changed after reinforcement; resolve that step again',
                    'message_es': 'La guía cambió después de los refuerzos; resuelve de nuevo ese paso'}

    if target_step >= STEP_FINAL_CUT:
        guide = _workflow_guide_candidate(props)
        if not _valid_obj(guide):
            return {'ok': False, 'target': target_step, 'fallback': STEP_DRILL,
                    'message_en': 'The guide is unavailable; rebuild the previous stage',
                    'message_es': 'La guía no está disponible; reconstruye el paso anterior'}
        if int(guide.get('DSG_drill_channel_count', 0) or 0) <= 0:
            return {'ok': False, 'target': target_step, 'fallback': STEP_DRILL,
                    'message_en': 'Create the drill channels before the final Boolean',
                    'message_es': 'Crea los canales de fresado antes de la booleana final'}
        stored_drill_sig = str(scene.get(WORKFLOW_DRILL_SIGNATURE_KEY, '') or '')
        if (stored_drill_sig
                and stored_drill_sig != _workflow_object_signature(guide)
                and not str(guide.get('DSG_final_pipeline', '') or '')
                and not bool(guide.get('DSG_final_cut_completed', False))):
            return {'ok': False, 'target': target_step, 'fallback': STEP_DRILL,
                    'message_en': 'The drill-channel guide changed after confirmation; confirm the channels again',
                    'message_es': 'La guía con canales cambió después de confirmarla; confirma de nuevo los canales'}
        if not _valid_obj(get_confirmed_passive_model_obj()):
            return {'ok': False, 'target': target_step, 'fallback': STEP_IMPLANT,
                    'message_en': 'The confirmed retentive model is missing; return to implant planning',
                    'message_es': 'Falta el modelo retentivo confirmado; vuelve a planificación de implantes'}

    if target_step >= STEP_NAME:
        guide = _workflow_guide_candidate(props)
        final_ready = bool(
            _valid_obj(guide)
            and (str(guide.get('DSG_final_pipeline', '') or '')
                 or str(guide.get('DSG_final_solver', '') or '')
                 or bool(guide.get('DSG_final_cut_completed', False))))
        if not final_ready:
            return {'ok': False, 'target': target_step, 'fallback': STEP_FINAL_CUT,
                    'message_en': 'Complete and validate the final guide Boolean before export',
                    'message_es': 'Completa y valida la booleana final de la guía antes de exportar'}

    return {'ok': True, 'target': target_step, 'fallback': target_step,
            'message_en': 'Workflow stage ready', 'message_es': 'Paso del flujo preparado'}


def _workflow_highest_valid_step(context, *, scene=None):
    scene = scene or getattr(context, 'scene', None)
    highest = STEP_MODEL
    for step in range(STEP_MODEL, STEP_NAME + 1):
        report = _workflow_requirement_report(context, step, scene=scene)
        if not bool(report.get('ok')):
            break
        highest = step
    return highest


def _workflow_hide_known_stage_objects():
    roles = {
        ROLE_BLOCKOUT, ROLE_BLOCKOUT_VISUAL, ROLE_RETENTION_BOUNDARY, ROLE_PASSIVE, ROLE_FRAME,
        ROLE_GUIDE, ROLE_IMPLANT, ROLE_SLEEVE, ROLE_IRRIGATION,
        ROLE_REINFORCEMENT, ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL,
        ROLE_DRILL_CUTTER, ROLE_DRILL_VISUAL, ROLE_ENGRAVE,
    }
    for obj in list(bpy.data.objects):
        try:
            role = str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, '')) or '')
        except Exception:
            role = ''
        if role in roles:
            _set_obj_hidden(obj, True, selectable_when_visible=False)


def _workflow_show_objects(objects, *, selectable=True):
    shown = []
    for obj in objects:
        if _valid_obj(obj) and obj not in shown:
            _set_obj_hidden(obj, False, selectable_when_visible=selectable)
            shown.append(obj)
    return shown


def _ensure_clinical_model_material():
    """Neutral gray IOS/model material for Material Preview.

    The IOS stays gray throughout planning so cyan FDI labels and blue blockout
    remain immediately distinguishable. This is display-only and never changes
    exported geometry.
    """
    name = 'DSG_IOS_NeutralGray'
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        material.use_nodes = True
        material.diffuse_color = (0.52, 0.55, 0.58, 1.0)
        material.metallic = 0.0
        material.roughness = 0.48
        nodes = material.node_tree.nodes if material.node_tree else None
        bsdf = nodes.get('Principled BSDF') if nodes else None
        _set_principled_input(bsdf, ('Base Color',), (0.52, 0.55, 0.58, 1.0))
        _set_principled_input(bsdf, ('Roughness',), 0.48)
        _set_principled_input(bsdf, ('Metallic',), 0.0)
        _set_principled_input(bsdf, ('Coat Weight', 'Clearcoat'), 0.06)
        _set_principled_input(bsdf, ('Coat Roughness', 'Clearcoat Roughness'), 0.34)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def _apply_clinical_model_material(obj):
    """Assign the model display material without touching blockout materials."""
    if not _valid_obj(obj) or obj.type != 'MESH' or getattr(obj, 'data', None) is None:
        return False
    # Never recolour generated blockout/overlay objects.
    if (_is_generated_blockout_mesh(obj)
            or bool(obj.get('DSG_blockout_visual_only', False))
            or str(obj.name).startswith(('DSG_Blockout', 'DSG_Retention'))):
        return False
    material = _ensure_clinical_model_material()
    try:
        if len(obj.material_slots) == 0:
            obj.data.materials.append(material)
        for slot in obj.material_slots:
            try:
                slot.link = 'OBJECT'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            slot.material = material
        obj['DSG_material_preview_role'] = 'IOS_NEUTRAL_GRAY'
        return True
    except Exception:
        return False


def _restore_workflow_stage(context, scene, step):
    """Reconstruct visibility, material preview and controllers for one stage."""
    global _WORKFLOW_RESTORE_ACTIVE
    if _WORKFLOW_RESTORE_ACTIVE or scene is None or getattr(context, 'scene', None) != scene:
        return False
    props = getattr(scene, 'dsg_props', None)
    if props is None:
        return False
    _WORKFLOW_RESTORE_ACTIVE = True
    try:
        step = max(STEP_MODEL, min(STEP_NAME, int(step)))
        props.drawing_active = False
        props.irr_drawing_active = False
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []

        if step == STEP_IMPLANT:
            return _restore_implant_planning_state(
                context, scene, _IMPLANT_STEP_RETURN_STATE.get(str(scene.name), {}))

        if _dicom_review_is_active(context):
            _close_dicom_review_for_guide(context)
        else:
            _hide_dicom_objects(context)
            _set_dicom_measurements_visibility(False)
        _set_material_preview_guide_view(context)
        _workflow_hide_known_stage_objects()

        model = _workflow_model_candidate(props, context)
        _apply_clinical_model_material(model)
        passive = get_confirmed_passive_model_obj()
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        implants = get_all_implant_objects(props)
        frame = _workflow_frame_candidate(props)
        guide = _workflow_guide_candidate(props)
        contour = bpy.data.objects.get(CONTOUR_CURVE_NAME) if 'CONTOUR_CURVE_NAME' in globals() else bpy.data.objects.get('DSG_ContourCurve')

        active = None
        if step == STEP_MODEL:
            shown = _workflow_show_objects([model, blockout, passive])
            active = blockout if _valid_obj(blockout) else (passive if _valid_obj(passive) else model)
            _set_retention_boundary_visible(bool(_valid_obj(blockout)))
        elif step == STEP_CONTOUR:
            if not _valid_obj(contour):
                try:
                    saved_points = [Vector(item.co) for item in props.contour_points]
                    if len(saved_points) >= 4:
                        set_contour_curve_points(context, saved_points, cyclic=True)
                        contour = bpy.data.objects.get(CONTOUR_CURVE_NAME)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            visual = bpy.data.objects.get(BLOCKOUT_VISUAL_NAME)
            if not _valid_obj(visual):
                try:
                    visual = _ensure_blockout_zone_visual(
                        context, model, blockout, force_rebuild=False)
                except Exception as exc:
                    print(f'[DSG] Blockout visual warning: {exc}')
                    visual = None
            _workflow_show_objects([passive] + implants + [contour])
            if _valid_obj(visual):
                _set_obj_hidden(visual, False, selectable_when_visible=False)
            _set_retention_boundary_visible(True)
            active = contour if _valid_obj(contour) else (implants[-1] if implants else passive)
        elif step == STEP_FRAME:
            micros = []
            try:
                micros = get_confirmed_microscrew_objects()
                pending = get_pending_microscrew_preview(props)
                if _valid_obj(pending):
                    micros.append(pending)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _workflow_show_objects([frame, passive] + implants + micros)
            active = frame if _valid_obj(frame) else (micros[-1] if micros else passive)
        elif step == STEP_SLEEVE:
            sleeve_sources = []
            try:
                sleeve_sources = get_sleeve_preview_objects()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _workflow_show_objects([guide, frame] + implants + sleeve_sources)
            active = guide if _valid_obj(guide) else (frame if _valid_obj(frame) else (implants[-1] if implants else None))
        elif step in {STEP_IRRIGATION, STEP_REINFORCEMENT, STEP_DRILL}:
            extras = []
            role = {STEP_IRRIGATION: ROLE_IRRIGATION,
                    STEP_REINFORCEMENT: ROLE_REINFORCEMENT,
                    STEP_DRILL: ROLE_DRILL_VISUAL}[step]
            try:
                extras = find_dsg_objects(role=role)
            except Exception:
                extras = []
            _workflow_show_objects([guide] + extras)
            active = guide
        elif step == STEP_FINAL_CUT:
            _workflow_show_objects([guide, passive])
            active = guide
        else:
            _workflow_show_objects([guide])
            active = guide

        if _valid_obj(active):
            set_active(context, active)
        _tag_dsg_view3d_redraw()
        return True
    except Exception as exc:
        print(f'[DSG] Workflow stage restore warning: {exc}')
        return False
    finally:
        _WORKFLOW_RESTORE_ACTIVE = False


def _schedule_workflow_stage_restore(scene, step, delay=0.03):
    if scene is None:
        return False
    key = (str(scene.name), int(step))
    if key in WORKFLOW_RESTORE_PENDING:
        return True
    WORKFLOW_RESTORE_PENDING.add(key)

    def _restore_timer():
        try:
            target_scene = bpy.data.scenes.get(key[0])
            if target_scene is None:
                return None
            props = getattr(target_scene, 'dsg_props', None)
            if props is None or int(getattr(props, 'current_step', STEP_MODEL)) != key[1]:
                return None
            _restore_workflow_stage(bpy.context, target_scene, key[1])
        except Exception as exc:
            print(f'[DSG] Workflow restore timer warning: {exc}')
        finally:
            WORKFLOW_RESTORE_PENDING.discard(key)
        return None

    try:
        lifecycle.register_timer(_restore_timer, first_interval=max(0.01, float(delay)))
        return True
    except Exception:
        WORKFLOW_RESTORE_PENDING.discard(key)
        return False


def _set_workflow_gate(scene, report):
    if scene is None:
        return
    if bool(report.get('ok')):
        for key in (WORKFLOW_GATE_MESSAGE_KEY, WORKFLOW_GATE_TARGET_KEY, WORKFLOW_GATE_FALLBACK_KEY):
            try:
                del scene[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return
    spanish = _dsg_spanish(getattr(scene, 'dsg_props', None))
    scene[WORKFLOW_GATE_MESSAGE_KEY] = str(
        report.get('message_es' if spanish else 'message_en', 'Workflow blocked'))
    scene[WORKFLOW_GATE_TARGET_KEY] = int(report.get('target', STEP_MODEL))
    scene[WORKFLOW_GATE_FALLBACK_KEY] = int(report.get('fallback', STEP_MODEL))


def _require_workflow_stage(operator, context, required_step, *, action_en='', action_es=''):
    operator_id = str(getattr(operator, 'bl_idname', '') or '')
    if operator_id in AGENT_USER_ONLY_OPERATOR_IDS and core.reject_external_agent_for_user_gate(
            operator, action=operator_id):
        return False
    """Block direct/manual operator calls when their clinical prerequisites are missing.

    The UI normally reaches operators through ``current_step`` and therefore
    through ``_on_current_step_update``.  Blender search, shortcuts and Python
    calls can invoke an operator directly, so every destructive/advancing action
    also uses this second line of defence.
    """
    scene = getattr(context, 'scene', None)
    props = getattr(scene, 'dsg_props', None) if scene is not None else None
    current_step = int(getattr(props, 'current_step', STEP_MODEL)) if props is not None else STEP_MODEL
    if current_step > int(required_step):
        message_en = (
            f'This action belongs to step {int(required_step) + 1}. Use Back to return there; '
            'DSG will not modify an earlier clinical stage from a later panel.')
        message_es = (
            f'Esta acción pertenece al paso {int(required_step) + 1}. Usa Atrás para volver; '
            'DSG no modificará un paso clínico anterior desde un panel posterior.')
        _dsg_report(operator, {'ERROR'}, message_en, message_es)
        _schedule_workflow_stage_restore(scene, current_step, delay=0.02)
        return False

    report = _workflow_requirement_report(context, required_step, scene=scene)
    if bool(report.get('ok')):
        return True

    _set_workflow_gate(scene, report)
    fallback = max(STEP_MODEL, min(int(required_step), int(report.get('fallback', STEP_MODEL))))
    if props is not None:
        global _STEP_GATE_ROLLBACK_ACTIVE
        _STEP_GATE_ROLLBACK_ACTIVE = True
        try:
            props.current_step = fallback
        finally:
            _STEP_GATE_ROLLBACK_ACTIVE = False
    if scene is not None:
        scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(fallback)
        _schedule_workflow_stage_restore(scene, fallback, delay=0.02)

    spanish = _dsg_spanish(props)
    dependency = str(report.get('message_es' if spanish else 'message_en', 'Workflow dependency missing'))
    prefix = action_es if spanish else action_en
    message = f'{prefix}: {dependency}' if prefix else dependency
    _dsg_report(operator, {'ERROR'}, message if not spanish else str(report.get('message_en', message)),
                message if spanish else str(report.get('message_es', message)))
    return False


def _reconcile_workflow_after_undo(scene):
    if scene is None:
        return False
    props = getattr(scene, 'dsg_props', None)
    if props is None:
        return False
    current = int(getattr(props, 'current_step', STEP_MODEL))
    report = _workflow_requirement_report(bpy.context, current, scene=scene)
    target = current if bool(report.get('ok')) else int(report.get('fallback', STEP_MODEL))
    target = max(STEP_MODEL, min(current, target))
    if target != current:
        global _STEP_GATE_ROLLBACK_ACTIVE
        _STEP_GATE_ROLLBACK_ACTIVE = True
        try:
            props.current_step = target
        finally:
            _STEP_GATE_ROLLBACK_ACTIVE = False
    scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(target)
    _set_workflow_gate(scene, report if target != current else {'ok': True})
    _schedule_workflow_stage_restore(scene, target, delay=0.04)
    return True

def _on_current_step_update(self, context):
    """Single gate for every forward/backward workflow transition."""
    global _STEP_GATE_ROLLBACK_ACTIVE
    try:
        scene = getattr(context, 'scene', None)
        if scene is None:
            return
        requested_step = max(STEP_MODEL, min(STEP_NAME, int(getattr(self, 'current_step', STEP_MODEL))))
        previous_step = int(scene.get(
            WORKFLOW_LAST_VALID_STEP_KEY, max(STEP_MODEL, requested_step - 1)))
        previous_step = max(STEP_MODEL, min(STEP_NAME, previous_step))

        # Internal rollback assignments already carry a validated destination.
        if _STEP_GATE_ROLLBACK_ACTIVE:
            scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(requested_step)
            _schedule_workflow_stage_restore(scene, requested_step, delay=0.03)
            return

        report = _workflow_requirement_report(context, requested_step, scene=scene)
        if not bool(report.get('ok')):
            fallback = max(STEP_MODEL, min(requested_step, int(report.get('fallback', STEP_MODEL))))
            _set_workflow_gate(scene, report)
            scene['DSG_next_step_gate_blocked'] = True
            scene['DSG_next_step_gate_message'] = str(
                report.get('message_es' if _dsg_spanish(self) else 'message_en', 'Workflow blocked'))
            _STEP_GATE_ROLLBACK_ACTIVE = True
            try:
                self.current_step = fallback
            finally:
                _STEP_GATE_ROLLBACK_ACTIVE = False
            scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(fallback)
            _schedule_workflow_stage_restore(scene, fallback, delay=0.03)
            _tag_dsg_view3d_redraw()
            return

        # Save the completed previous stage before any later operation can
        # destructively remesh or Boolean the same guide object.
        if requested_step > previous_step:
            _capture_workflow_checkpoint(context, previous_step)

        _set_workflow_gate(scene, {'ok': True})
        scene['DSG_next_step_gate_blocked'] = False
        try:
            del scene['DSG_next_step_gate_message']
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(requested_step)

        # Every stage receives a deterministic viewport/object reconstruction.
        # Step 2 uses its richer implant-controller restore routine.
        if requested_step == STEP_IMPLANT:
            _schedule_implant_planning_state_restore(
                scene, require_armed=False, delay=0.03)
        else:
            _schedule_workflow_stage_restore(scene, requested_step, delay=0.03)

        if str(scene.get(SUITE_STAGE_KEY, 'DSG')).upper() == 'DSG':
            activate_precision_orthographic(context)
    except Exception as exc:
        print(f'[DSG] Workflow transition audit warning: {exc}')
        try:
            scene = getattr(context, 'scene', None)
            if scene is not None:
                current = int(getattr(self, 'current_step', STEP_MODEL))
                fallback = min(current, _workflow_highest_valid_step(context, scene=scene))
                _STEP_GATE_ROLLBACK_ACTIVE = True
                try:
                    self.current_step = fallback
                finally:
                    _STEP_GATE_ROLLBACK_ACTIVE = False
                scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(fallback)
                _schedule_workflow_stage_restore(scene, fallback, delay=0.03)
        except Exception:
            _STEP_GATE_ROLLBACK_ACTIVE = False

def _on_precision_ortho_lock_update(self, context):
    try:
        if bool(getattr(self, "precision_ortho_lock", True)):
            activate_precision_orthographic(context, force=True)
        else:
            restore_precision_projection(context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

_language_get = core.language_get
_language_set = core.language_set

def _dsg_spanish(props=None):
    scene = getattr(props, 'id_data', None) if props is not None else getattr(bpy.context, 'scene', None)
    return core.is_spanish(scene)

def _ui_text(props, english, spanish):
    scene = getattr(props, 'id_data', None) if props is not None else getattr(bpy.context, 'scene', None)
    return core.translate_ui(scene, english, spanish)

def _step_text(props, step):
    try:
        scene = getattr(props, 'id_data', None) if props is not None else getattr(bpy.context, 'scene', None)
        return core.translate_ui(scene, STEP_LABELS[int(step)], STEP_LABELS_ES[int(step)])
    except Exception:
        return core.translate_ui(getattr(bpy.context, 'scene', None), STEP_LABELS[0], STEP_LABELS_ES[0])

def _dsg_report(operator, levels, english_message, spanish_message=None):
    message = core.translate_ui(getattr(bpy.context, 'scene', None), english_message, spanish_message)
    operator.report(levels, message)


# Estado GPU — módulo global
_CONTOUR_DRAW_HANDLER = None
_IRR_DRAW_HANDLER  = None
_PREFLIGHT_UI_CACHE = {}
_DICOM_MEASURE_UPDATE_LOCK = False
_DICOM_MEASURE_UPDATE_PENDING = False


# ─────────────────────────────────────────────────────────────
# Registro / recuperación robusta de objetos DSG
# ─────────────────────────────────────────────────────────────

def _suite_role(obj):
    return core.role_of(obj) if _valid_obj(obj) else ''

def _set_suite_role(obj, role):
    if not _valid_obj(obj):
        return
    core.set_role(obj, role)
    obj['dental_suite_component'] = 'DSG'

def _find_suite_object(role):
    return core.find_role(role)

def _is_generated_blockout_mesh(obj):
    """Return True for any DSG mesh that must never be reused as source anatomy."""
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH':
        return False
    dsg_role = str(obj.get('dental_suite_dsg_role', '')).lower()
    name = str(getattr(obj, 'name', ''))
    return bool(
        dsg_role in {ROLE_BLOCKOUT, ROLE_PASSIVE, ROLE_GUIDE, ROLE_FRAME, ROLE_CUTTER}
        or bool(obj.get('DSG_retention_preview', False))
        or bool(obj.get('DSG_contains_blockout', False))
        or name == BLOCKOUT_NAME
        or name == COMBINED_NAME
        or name in set(RETENTION_PREVIEW_NAMES.values())
        or name.startswith('DSG_Retention_')
        or name.startswith('DSG_Blockout')
    )


def _looks_like_dicom_mesh(obj):
    """Fast name/role guard available before the full DICOM helper is defined."""
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH':
        return False
    role = _suite_role(obj)
    name = str(getattr(obj, 'name', '') or '').upper()
    return bool(
        role in {ROLE_DICOM_TEETH_SUITE, ROLE_DICOM_BONE_SUITE}
        or name.startswith(('DICOM_', 'SEG_', 'STL_DIENTES', 'STL_HUESO', 'DENTAL_DICOM_'))
        or 'DICOM' in name
        or bool(obj.get('dental_suite_dicom_reference', False))
    )


def _is_strict_ios_blockout_source(obj):
    """Accept only an IOS scan/aligned IOS as source anatomy for blockout.

    An arbitrary active mesh is never accepted. This prevents a DICOM teeth or
    bone segmentation, a previous cutter, or a full two-jaw model from becoming
    ``DSG_Blockout`` after an undo/reload pointer change.
    """
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH':
        return False
    if _is_generated_blockout_mesh(obj) or _looks_like_dicom_mesh(obj):
        return False
    role = _suite_role(obj)
    dental_role = str(obj.get('dental_role', '') or '').upper()
    canonical = str(obj.get('dental_suite_canonical_name', '') or '').upper()
    name = str(getattr(obj, 'name', '') or '').upper()
    explicitly_ios = bool(
        role in {ROLE_IOS_ALIGNED_SUITE, ROLE_IOS_SCAN_SUITE}
        or dental_role in {ROLE_IOS_ALIGNED_SUITE, ROLE_IOS_SCAN_SUITE}
        or bool(obj.get('dental_suite_aligned', False))
        or canonical.startswith('DENTAL_IOS')
        or name.startswith('DENTAL_IOS')
    )
    return explicitly_ios


def _find_aligned_ios(context=None):
    obj = _find_suite_object(ROLE_IOS_ALIGNED_SUITE)
    if _is_strict_ios_blockout_source(obj):
        return obj
    # Compatibility fallback for older Alignment builds, but still require an
    # explicit IOS identity. Never fall back to an arbitrary active mesh.
    candidates = [
        o for o in bpy.data.objects
        if _is_strict_ios_blockout_source(o)
        and (
            _suite_role(o) == ROLE_IOS_ALIGNED_SUITE
            or bool(o.get('dental_suite_aligned', False))
            or str(o.get('dental_role', '')).upper() == ROLE_IOS_ALIGNED_SUITE
        )
    ]
    if candidates:
        visible = [o for o in candidates if not o.hide_get() and not o.hide_viewport]
        return (visible or candidates)[-1]
    return None


def _resolve_blockout_source_model(context, source_obj):
    """Resolve the IOS explicitly chosen in DSG, with a safe alignment fallback.

    A valid ``props.model_obj`` is now authoritative so the user can return to
    step 1 and correct a wrong IOS without restarting the whole workflow. DICOM
    surfaces and DSG-generated geometry are still rejected. If the explicit
    pointer is stale or invalid, the most recent aligned IOS remains the fallback.
    """
    if _is_strict_ios_blockout_source(source_obj):
        return source_obj
    aligned = _find_aligned_ios(context)
    if _is_strict_ios_blockout_source(aligned):
        return aligned
    supplied = str(getattr(source_obj, 'name', '') or '<none>')
    raise RuntimeError(
        f'Blockout source is not an aligned IOS ({supplied}). '
        'Select the correct aligned IOS in step 1 or return to Alignment')


DICOM_OBJECT_PREFIXES = (
    'DICOM_', 'SEG_', 'STL_Dientes', 'STL_Hueso', 'Dental_DICOM_',
)


def _is_dicom_related_object(obj):
    if not _valid_obj(obj):
        return False
    if _suite_role(obj) in {ROLE_DICOM_TEETH_SUITE, ROLE_DICOM_BONE_SUITE}:
        return True
    name = str(getattr(obj, 'name', ''))
    if name.startswith(DICOM_OBJECT_PREFIXES):
        return True
    for collection in getattr(obj, 'users_collection', ()):
        if str(collection.name).startswith('DICOM'):
            return True
    return False


def _set_solid_view_original_colors(context):
    """Return every visible 3D editor to normal Solid material colors."""
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            try:
                space = area.spaces.active
                space.shading.type = 'SOLID'
                space.shading.color_type = 'MATERIAL'
                space.shading.light = 'STUDIO'
                space.shading.show_shadows = True
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


DICOM_COLLECTION_PREFIXES = (
    'DICOM_WIZARD_PRO',
    'DICOM_RADIOGRAPHIC_DISPLAYS',
)


def _set_dicom_collections_hidden(context, hidden):
    core.set_dicom_collections_hidden(context, hidden)


def _show_dicom_objects(context):
    _set_dicom_collections_hidden(context, False)
    for obj in list(context.scene.objects):
        if not _is_dicom_related_object(obj):
            continue
        try:
            obj.hide_viewport = False
            obj.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _hide_dicom_objects(context):
    _set_dicom_collections_hidden(context, True)
    for obj in list(context.scene.objects):
        if not _is_dicom_related_object(obj):
            continue
        try:
            obj.hide_viewport = True
            obj.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)



def _hide_ios_antagonists_for_insertion_axis(context, ios):
    """Hide every registered antagonist while the insertion axis is chosen.

    The antagonist remains parented to the selected IOS and can be shown again
    later through the existing antagonist toggle.  We only change visibility.
    """
    if not _valid_obj(ios):
        return []
    hidden = []
    try:
        antagonists = core.antagonist_objects(ios)
    except Exception:
        antagonists = []
    for antagonist in antagonists:
        if not _valid_obj(antagonist):
            continue
        try:
            antagonist["DSG_hidden_for_insertion_axis"] = True
            antagonist.hide_viewport = True
            antagonist.hide_render = True
            antagonist.hide_set(True)
            hidden.append(str(antagonist.name))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        context.scene["DSG_axis_hidden_antagonists_json"] = json.dumps(hidden)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return hidden


def _show_simple_active_cbct_jaw(context, ios):
    """For SIMPLE cases show only the large CBCT jaw island matching the IOS."""
    scene = getattr(context, "scene", None)
    if scene is None or core.clinical_route(scene) != core.ROUTE_SIMPLE:
        return None
    arch = str(getattr(ios, "get", lambda *_: "")("DSG_ios_arch_hint", "") or scene.get("DSG_active_arch", "") or "").upper()
    upper_name = str(scene.get("DSG_simple_maxilla_object", "") or "")
    lower_name = str(scene.get("DSG_simple_mandible_object", "") or "")
    upper = bpy.data.objects.get(upper_name) if upper_name else None
    lower = bpy.data.objects.get(lower_name) if lower_name else None
    if arch not in {"MAXILLA", "MANDIBLE"}:
        return None
    active = upper if arch == "MAXILLA" else lower
    other = lower if arch == "MAXILLA" else upper
    for obj, show in ((active, True), (other, False)):
        if not _valid_obj(obj):
            continue
        try:
            obj.hide_viewport = not show
            obj.hide_render = not show
            obj.hide_set(not show)
            obj.hide_select = not show
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return active


def _isolate_ios_for_guide(context, ios):
    if not _valid_obj(ios):
        return
    _apply_clinical_model_material(ios)
    _hide_dicom_objects(context)
    try:
        ios.hide_viewport = False
        ios.hide_set(False)
        ios.hide_select = False
        ios.display_type = 'SOLID'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        ios.select_set(True)
        context.view_layer.objects.active = ios
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _set_solid_view_original_colors(context)


def _implant_geometry_center_world(implant):
    """Return the vertex centroid of an implant in world coordinates."""
    if not is_valid_implant_obj(implant):
        return None
    try:
        vertices = implant.data.vertices
        if vertices:
            center_local = Vector((0.0, 0.0, 0.0))
            for vertex in vertices:
                center_local += vertex.co
            center_local /= float(len(vertices))
            return implant.matrix_world @ center_local
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        corners = [implant.matrix_world @ Vector(corner) for corner in implant.bound_box]
        return sum(corners, Vector((0.0, 0.0, 0.0))) / float(len(corners))
    except Exception:
        return implant.matrix_world.translation.copy()

def _is_valid_mpr_microscrew(obj):
    """Return True for a DSG microscrew trajectory or visual object.

    The DICOM review accepts the actual visual screw, the sleeve/support object,
    and the pending preview.  The shared requirement is a persisted microscrew
    axis, which is more reliable than names after users rename objects.
    """
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH':
        return False
    try:
        axis = obj.get('DSG_microscrew_axis', None)
        if axis is None or len(axis) != 3:
            return False
        if Vector(axis).length <= 1.0e-8:
            return False
    except Exception:
        return False
    try:
        role = str(obj.get('dental_suite_dsg_role', '') or '')
        return bool(
            role in {ROLE_MICROSCREW, ROLE_MICROSCREW_VISUAL}
            or obj.get('DSG_static_microscrew', False)
            or obj.get('DSG_animated_microscrew', False)
            or obj.get('DSG_microscrew_preview', False)
            or obj.get('DSG_microscrew_visual_preview', False)
            or obj.name.startswith(MICROSCREW_PREFIX)
            or obj.name.startswith(MICROSCREW_VISUAL_PREFIX)
            or obj.name.startswith(ANIMATED_MICROSCREW_PREFIX)
        )
    except Exception:
        return True


def _selected_mpr_microscrew(context):
    """Resolve the microscrew the user intends to review.

    Selection wins.  If the active object is not a microscrew, use a pending
    screw, then the most recently confirmed static visual.  This keeps the
    workflow usable while the frame or DICOM plane temporarily owns selection.
    """
    active = getattr(getattr(context, 'view_layer', None), 'objects', None)
    active = getattr(active, 'active', None) if active is not None else None
    if _is_valid_mpr_microscrew(active):
        return active

    candidates = []
    for obj in bpy.data.objects:
        if not _is_valid_mpr_microscrew(obj):
            continue
        priority = 0
        try:
            if obj.get('DSG_microscrew_visual_preview', False):
                priority = 40
            elif obj.get('DSG_microscrew_preview', False):
                priority = 35
            elif obj.get('DSG_static_microscrew', False):
                priority = 30
            elif obj.get('DSG_microscrew_confirmed', False):
                priority = 25
            elif obj.get('DSG_animated_microscrew', False):
                priority = 10
            index = int(obj.get('DSG_microscrew_index', 0))
        except Exception:
            index = 0
        candidates.append((priority, index, obj))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].name))
    return candidates[-1][2]


def _microscrew_axis_world(obj):
    if not _is_valid_mpr_microscrew(obj):
        return None
    try:
        axis = Vector(obj.get('DSG_microscrew_axis', (0.0, 0.0, 1.0)))
        if axis.length > 1.0e-8:
            axis.normalize()
            return axis
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        axis = obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
        if axis.length > 1.0e-8:
            axis.normalize()
            return axis
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return None


def _microscrew_center_world(obj):
    """Clinical centre of the screw trajectory, not of its frame supports."""
    if not _is_valid_mpr_microscrew(obj):
        return None
    try:
        stop = obj.get('DSG_stop_contact_world', None)
        tip = obj.get('DSG_tip_final_world', None)
        if stop is not None and tip is not None and len(stop) == 3 and len(tip) == 3:
            return (Vector(stop) + Vector(tip)) * 0.5
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        sleeve_top = obj.get('DSG_microscrew_sleeve_top', None)
        target = obj.get('DSG_microscrew_point_target', None)
        if sleeve_top is not None and target is not None and len(sleeve_top) == 3 and len(target) == 3:
            return (Vector(sleeve_top) + Vector(target)) * 0.5
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        sleeve_top = obj.get('DSG_microscrew_sleeve_top', None)
        axis = _microscrew_axis_world(obj)
        if sleeve_top is not None and len(sleeve_top) == 3 and axis is not None:
            stop = Vector(sleeve_top)
            tip = stop + axis * MICROSCREW_TEMPLATE_TIP_Z_MM
            return (stop + tip) * 0.5
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        vertices = obj.data.vertices
        if vertices:
            center_local = sum((vertex.co for vertex in vertices), Vector()) / float(len(vertices))
            return obj.matrix_world @ center_local
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj.matrix_world.translation.copy()


def _microscrew_x_hint_world(obj, axis_world):
    try:
        hint = obj.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
        hint -= axis_world * hint.dot(axis_world)
        if hint.length > 1.0e-8:
            hint.normalize()
            return hint
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    fallback = Vector((1.0, 0.0, 0.0))
    if abs(float(fallback.dot(axis_world))) > 0.92:
        fallback = Vector((0.0, 1.0, 0.0))
    hint = fallback - axis_world * fallback.dot(axis_world)
    hint.normalize()
    return hint


def _ensure_mpr_target_visible(context, obj):
    """Keep an implant/microscrew visible over the MPR image planes."""
    if not _valid_obj(obj):
        return False

    def _unhide_object(candidate):
        if not _valid_obj(candidate):
            return
        try:
            candidate.hide_viewport = False
            candidate.hide_render = False
            candidate.hide_set(False)
            candidate.show_in_front = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    current = obj
    guard = 0
    while _valid_obj(current) and guard < 12:
        _unhide_object(current)
        current = getattr(current, 'parent', None)
        guard += 1

    collection_names = set()
    try:
        for collection in obj.users_collection:
            collection_names.add(collection.name)
            collection.hide_viewport = False
            collection.hide_render = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    def _walk(layer_collection):
        try:
            collection = layer_collection.collection
            if collection is not None and collection.name in collection_names:
                layer_collection.exclude = False
                layer_collection.hide_viewport = False
            for child in layer_collection.children:
                _walk(child)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        _walk(context.view_layer.layer_collection)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _unhide_object(obj)
    try:
        obj.display_type = 'SOLID'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _center_two_plane_mpr_on_microscrew(context, microscrew):
    """Centre the two-plane DICOM review on a selected microscrew.

    The shared MPR Z axis is aligned to the persisted local Z/trajectory of the
    screw.  Consequently the axial image is perpendicular to the screw and the
    sagittal image contains its full long axis.  Both planes pivot through the
    clinical midpoint of the selected screw rather than the DICOM volume centre.
    """
    if not _is_valid_mpr_microscrew(microscrew):
        return False, 'No valid microscrew selected'
    _ensure_mpr_target_visible(context, microscrew)
    dicom_props = getattr(context.scene, 'dicom_wizard_pro', None)
    if dicom_props is None:
        return False, 'DICOM module is unavailable'
    center_world = _microscrew_center_world(microscrew)
    axis_world = _microscrew_axis_world(microscrew)
    if center_world is None or axis_world is None:
        return False, 'Microscrew centre or axis could not be calculated'

    try:
        from . import dicom_module as _dicom
        np = _dicom.load_numpy()
        if np is None or not _dicom.RUNTIME.is_loaded():
            return False, 'DICOM volume is not loaded'
        root = bpy.data.objects.get(_dicom.ROOT_NAME)
        if root is None:
            return False, 'DICOM root is unavailable'

        root_inverse = root.matrix_world.inverted_safe()
        center_root = root_inverse @ center_world
        axis_root = root_inverse.to_3x3() @ axis_world
        if axis_root.length <= 1.0e-8:
            return False, 'Microscrew axis is invalid in DICOM coordinates'
        axis_root.normalize()

        x_hint_world = _microscrew_x_hint_world(microscrew, axis_world)
        x_axis = root_inverse.to_3x3() @ x_hint_world
        x_axis -= axis_root * x_axis.dot(axis_root)
        if x_axis.length <= 1.0e-8:
            fallback = Vector((1.0, 0.0, 0.0))
            if abs(float(fallback.dot(axis_root))) > 0.92:
                fallback = Vector((0.0, 1.0, 0.0))
            x_axis = fallback - axis_root * fallback.dot(axis_root)
        x_axis.normalize()
        y_axis = axis_root.cross(x_axis)
        if y_axis.length <= 1.0e-8:
            return False, 'Could not construct the microscrew MPR frame'
        y_axis.normalize()
        x_axis = y_axis.cross(axis_root).normalized()

        alignment = np.column_stack((
            np.asarray(tuple(x_axis), dtype=np.float64),
            np.asarray(tuple(y_axis), dtype=np.float64),
            np.asarray(tuple(axis_root), dtype=np.float64),
        ))
        _dicom._store_mpr_alignment_matrix(dicom_props, alignment)

        center_root_np = np.asarray(tuple(float(v) for v in center_root), dtype=np.float64)
        center_aligned = alignment.T @ center_root_np
        extent_x, extent_y, extent_z = _dicom._volume_extents_xyz_mm()

        def percent(value, extent):
            if float(extent) <= 1.0e-9:
                return 50.0
            return max(0.0, min(100.0,
                100.0 * (float(value) + 0.5 * float(extent)) / float(extent)))

        px = percent(center_aligned[0], extent_x)
        py = percent(center_aligned[1], extent_y)
        pz = percent(center_aligned[2], extent_z)

        _dicom.RUNTIME.update_lock = True
        try:
            for prefix in ('axial', 'sagittal'):
                setattr(dicom_props, f'{prefix}_move_x', px)
                setattr(dicom_props, f'{prefix}_move_y', py)
                setattr(dicom_props, f'{prefix}_move_z', pz)
                setattr(dicom_props, f'{prefix}_rotate_x', 0.0)
                setattr(dicom_props, f'{prefix}_rotate_y', 0.0)
                setattr(dicom_props, f'{prefix}_rotate_z', 0.0)
        finally:
            _dicom.RUNTIME.update_lock = False

        for orientation in ('AXIAL', 'SAGITTAL'):
            _dicom._apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
            if bool(dicom_props.get('safe_mpr_active', False)):
                _dicom._safe_review_request_realtime_refresh(orientation)
                _dicom._safe_review_schedule_image_refresh(orientation)
            else:
                _dicom.refresh_plane_image_from_object(
                    context, orientation, max_axis=_dicom.MAX_MPR_AXIS)

        dicom_props['dsg_mpr_target_microscrew'] = str(microscrew.name)
        dicom_props['dsg_mpr_target_center_world'] = [float(v) for v in center_world]
        dicom_props['dsg_mpr_target_axis_world'] = [float(v) for v in axis_world]
        dicom_props['dsg_mpr_pivot'] = 'SELECTED_MICROSCREW_CENTER'
        return True, f'MPR centred and aligned to {microscrew.name}'
    except Exception as exc:
        print(f'[DSG] Could not orient MPR through microscrew: {exc}')
        return False, str(exc)

def _resolve_mpr_target_implant(context, props):
    name = str(getattr(props, 'mpr_target_implant', '') or '')
    implant = bpy.data.objects.get(name) if name else None
    if is_valid_implant_obj(implant):
        return implant
    active = getattr(getattr(context, 'view_layer', None), 'objects', None)
    active = getattr(active, 'active', None) if active is not None else None
    if is_valid_implant_obj(active):
        return active
    if _valid_obj(active):
        linked = str(active.get('DSG_implant_name', '') or '')
        implant = bpy.data.objects.get(linked) if linked else None
        if is_valid_implant_obj(implant):
            return implant
    implants = get_all_implant_objects(props)
    return implants[0] if implants else None

def _center_two_plane_mpr_on_implant(context, implant):
    """Orient DSG's two-plane MPR toward the selected implant.

    This function deliberately preserves the original two-control clinical
    model:

    * ``axial_move_z`` moves the horizontal cut to the implant height.
    * ``sagittal_rotate_z`` rotates the vertical cut around the geometric
      centre of the COMPLETE DICOM volume until that plane intersects the
      implant.

    The vertical plane is never translated to the implant and its pivot is
    never changed to the implant.  All hidden translation controls remain at
    50 %, so inclination in Z always uses the DICOM centre as its pivot.
    """
    if not is_valid_implant_obj(implant):
        return False, 'No valid implant selected'
    _ensure_mpr_target_visible(context, implant)
    dicom_props = getattr(context.scene, 'dicom_wizard_pro', None)
    if dicom_props is None:
        return False, 'DICOM module is unavailable'
    center_world = _implant_geometry_center_world(implant)
    if center_world is None:
        return False, 'Implant center could not be calculated'
    try:
        from . import dicom_module as _dicom
        np = _dicom.load_numpy()
        if np is None or not _dicom.RUNTIME.is_loaded():
            return False, 'DICOM volume is not loaded'

        root = bpy.data.objects.get(_dicom.ROOT_NAME)
        if root is None:
            return False, 'DICOM root is unavailable'

        # Convert world coordinates into the root-local millimetric system used
        # by the MPR planes, then remove the shared anatomical alignment frame.
        center_root = root.matrix_world.inverted_safe() @ center_world
        alignment = _dicom._mpr_alignment_matrix(dicom_props)
        root_local = np.asarray(tuple(float(v) for v in center_root), dtype=np.float64)
        dicom_local = alignment.T @ root_local

        _extent_x, _extent_y, extent_z = _dicom._volume_extents_xyz_mm()

        def percent(value, extent):
            if float(extent) <= 1.0e-9:
                return 50.0
            return max(0.0, min(100.0, 100.0 * (float(value) + 0.5 * float(extent)) / float(extent)))

        axial_z_percent = percent(dicom_local[2], extent_z)

        # The base sagittal plane is YZ. Rotating it around DICOM-local Z by
        # (azimuth - 90 degrees) makes its horizontal in-plane direction point
        # from the volume centre toward the selected implant.
        radial_x = float(dicom_local[0])
        radial_y = float(dicom_local[1])
        if math.hypot(radial_x, radial_y) <= 1.0e-6:
            sagittal_z_degrees = 0.0
        else:
            sagittal_z_degrees = math.degrees(math.atan2(radial_y, radial_x)) - 90.0
            sagittal_z_degrees = ((sagittal_z_degrees + 180.0) % 360.0) - 180.0

        _dicom.RUNTIME.update_lock = True
        try:
            # Horizontal cut: centred in X/Y, moved only in Z.
            dicom_props.axial_move_x = 50.0
            dicom_props.axial_move_y = 50.0
            dicom_props.axial_move_z = axial_z_percent
            dicom_props.axial_rotate_x = 0.0
            dicom_props.axial_rotate_y = 0.0
            dicom_props.axial_rotate_z = 0.0

            # Vertical cut: its object origin stays at the complete DICOM centre.
            # Only Z inclination changes, so the plane sweeps radially through
            # the implant without changing its pivot.
            dicom_props.sagittal_move_x = 50.0
            dicom_props.sagittal_move_y = 50.0
            dicom_props.sagittal_move_z = 50.0
            dicom_props.sagittal_rotate_x = 0.0
            dicom_props.sagittal_rotate_y = 0.0
            dicom_props.sagittal_rotate_z = sagittal_z_degrees
        finally:
            _dicom.RUNTIME.update_lock = False

        for orientation in ('AXIAL', 'SAGITTAL'):
            _dicom._apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
            if bool(dicom_props.get('safe_mpr_active', False)):
                _dicom._safe_review_request_realtime_refresh(orientation)
                _dicom._safe_review_schedule_image_refresh(orientation)
            else:
                _dicom.refresh_plane_image_from_object(context, orientation, max_axis=_dicom.MAX_MPR_AXIS)

        dicom_props['dsg_mpr_target_implant'] = str(implant.name)
        dicom_props['dsg_mpr_target_center_world'] = [float(v) for v in center_world]
        dicom_props['dsg_mpr_axial_z_percent'] = float(axial_z_percent)
        dicom_props['dsg_mpr_sagittal_z_degrees'] = float(sagittal_z_degrees)
        dicom_props['dsg_mpr_pivot'] = 'DICOM_VOLUME_CENTER'
        return True, f'MPR oriented through {implant.name}'
    except Exception as exc:
        print(f'[DSG] Could not orient MPR through implant: {exc}')
        return False, str(exc)

def _mpr_implant_items(self, context):
    items = []
    try:
        implants = get_all_implant_objects(self)
    except Exception:
        implants = []
    for index, implant in enumerate(implants):
        name = _safe_object_name(implant) or f'Implant {index + 1}'
        items.append((name, name, f'Orient DICOM review through {name}', 'MESH_CYLINDER', index))
    if not items:
        items.append(('__NONE__', 'No implants', 'Add an implant first', 'INFO', 0))
    return items

def _on_mpr_target_implant_change(self, context):
    try:
        if context is None or not _dicom_review_is_active(context):
            return
        implant = bpy.data.objects.get(str(getattr(self, 'mpr_target_implant', '') or ''))
        if is_valid_implant_obj(implant):
            _center_two_plane_mpr_on_implant(context, implant)
    except Exception as exc:
        print(f'[DSG] MPR implant change warning: {exc}')



def _iter_view3d_areas(context=None):
    """Yield (window, screen, area, space) for every live 3D viewport."""
    context = context or bpy.context
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in getattr(screen, 'areas', ()):
            if getattr(area, 'type', None) != 'VIEW_3D':
                continue
            space = getattr(getattr(area, 'spaces', None), 'active', None)
            if space is None:
                continue
            yield window, screen, area, space


def _set_material_preview_guide_view(context=None):
    """Restore the clean implant-planning viewport used on entering step 2.

    This deliberately uses Blender Material Preview rather than Solid mode.  It
    also restores the sidebar, overlays and gizmos so the implant/emergence
    controllers are immediately available after exiting DICOM or undoing from
    the contour step.
    """
    changed = 0
    for _window, _screen, area, space in _iter_view3d_areas(context):
        try:
            shading = space.shading
            shading.type = 'MATERIAL'
            shading.color_type = 'MATERIAL'
            shading.show_shadows = True
            shading.show_cavity = True
            space.show_gizmo = True
            space.show_region_ui = True
            try:
                space.overlay.show_overlays = True
                space.overlay.show_floor = True
                space.overlay.show_cursor = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            area.tag_redraw()
            changed += 1
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return changed


def _capture_active_view3d_state(context):
    """Capture orientation/zoom without serialising Blender RNA objects."""
    area = getattr(context, 'area', None)
    if area is None or getattr(area, 'type', None) != 'VIEW_3D':
        return {}
    space = getattr(getattr(area, 'spaces', None), 'active', None)
    rv3d = getattr(space, 'region_3d', None) if space is not None else None
    if space is None:
        return {}
    state = {
        'area_pointer': int(area.as_pointer()),
        'show_region_ui': bool(getattr(space, 'show_region_ui', True)),
        'show_region_toolbar': bool(getattr(space, 'show_region_toolbar', True)),
    }
    if rv3d is not None:
        try:
            state.update({
                'view_location': tuple(float(v) for v in rv3d.view_location),
                'view_rotation': tuple(float(v) for v in rv3d.view_rotation),
                'view_distance': float(rv3d.view_distance),
                'view_perspective': str(rv3d.view_perspective),
            })
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return state


def _restore_active_view3d_state(context, state):
    if not isinstance(state, dict):
        return False
    wanted_pointer = int(state.get('area_pointer', 0) or 0)
    candidates = list(_iter_view3d_areas(context))
    if not candidates:
        return False
    selected = None
    for item in candidates:
        try:
            if wanted_pointer and int(item[2].as_pointer()) == wanted_pointer:
                selected = item
                break
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if selected is None:
        selected = candidates[0]
    _window, _screen, area, space = selected
    rv3d = getattr(space, 'region_3d', None)
    try:
        space.show_region_ui = True
        space.show_region_toolbar = bool(state.get('show_region_toolbar', True))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if rv3d is not None:
        try:
            location = state.get('view_location')
            rotation = state.get('view_rotation')
            if location and len(location) == 3:
                rv3d.view_location = Vector(location)
            if rotation and len(rotation) == 4:
                rv3d.view_rotation = Quaternion(rotation)
            if 'view_distance' in state:
                rv3d.view_distance = max(0.001, float(state['view_distance']))
            perspective = str(state.get('view_perspective', 'ORTHO'))
            if perspective in {'PERSP', 'ORTHO', 'CAMERA'}:
                rv3d.view_perspective = perspective
            rv3d.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


