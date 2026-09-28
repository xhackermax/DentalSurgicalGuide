from bpy.app.handlers import persistent


def _queue_realtime_transform(orientation: str) -> None:
    props = getattr(getattr(bpy.context, "scene", None), "dicom_wizard_pro", None)
    if props is not None and bool(props.get("safe_mpr_active", False)):
        return
    RUNTIME.pending_transform_orientations.add(orientation)
    RUNTIME.final_transform_orientations.add(orientation)
    RUNTIME.last_transform_event_time = time.monotonic()
    if RUNTIME.transform_timer_registered:
        return
    RUNTIME.transform_timer_registered = True
    try:
        lifecycle.register_timer(
            _run_realtime_transform_refresh,
            first_interval=REALTIME_PREVIEW_INTERVAL_SECONDS,
        )
    except Exception:
        RUNTIME.transform_timer_registered = False


def _run_realtime_transform_refresh():
    try:
        scene = bpy.context.scene
        props = getattr(scene, "dicom_wizard_pro", None)
        if (
            props is None
            or not props.volume_loaded
            or not props.realtime_mpr
            or not RUNTIME.is_loaded()
            or bool(props.get("safe_mpr_active", False))
        ):
            RUNTIME.transform_timer_registered = False
            RUNTIME.pending_transform_orientations.clear()
            RUNTIME.final_transform_orientations.clear()
            return None

        elapsed = time.monotonic() - RUNTIME.last_transform_event_time

        # Fast feedback while Blender's transform modal operator is running.
        if RUNTIME.pending_transform_orientations:
            orientations = tuple(RUNTIME.pending_transform_orientations)
            RUNTIME.pending_transform_orientations.clear()
            RUNTIME.transform_handler_lock = True
            try:
                for orientation in orientations:
                    refresh_plane_image_from_object(
                        bpy.context,
                        orientation,
                        max_axis=REALTIME_PREVIEW_MAX_AXIS,
                    )
            finally:
                RUNTIME.transform_handler_lock = False
            force_ui_redraw()

        # Keep the timer alive until no transform has arrived for a short time.
        if elapsed < REALTIME_FINAL_DELAY_SECONDS:
            return REALTIME_PREVIEW_INTERVAL_SECONDS

        # Once the transform settles, replace the preview with native resolution.
        if RUNTIME.final_transform_orientations:
            orientations = tuple(RUNTIME.final_transform_orientations)
            RUNTIME.final_transform_orientations.clear()
            RUNTIME.transform_handler_lock = True
            try:
                for orientation in orientations:
                    refresh_plane_image_from_object(
                        bpy.context,
                        orientation,
                        max_axis=MAX_MPR_AXIS,
                    )
            finally:
                RUNTIME.transform_handler_lock = False
            props.status = "Plano actualizado en tiempo real"
            force_ui_redraw()

    except Exception as exc:
        try:
            bpy.context.scene.dicom_wizard_pro.status = f"Error MPR en tiempo real: {exc}"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        print("DICOM Wizard Pro real-time MPR error:", repr(exc))

    RUNTIME.transform_timer_registered = False
    return None


@persistent
def dicom_wizard_pro_depsgraph_update(scene, depsgraph) -> None:
    """Detect direct viewport transforms of the DICOM MPR planes."""
    # Blender 5.1 can emit depsgraph notifications while enabling an add-on,
    # when bpy.data is the temporary _RestrictData object. Never touch objects
    # until normal blend-data access has been restored.
    if not _dicom_data_access_ready():
        return
    if RUNTIME.transform_handler_lock or RUNTIME.update_lock or RUNTIME.undo_in_progress or not RUNTIME.is_loaded():
        return
    props = getattr(scene, "dicom_wizard_pro", None)
    if props is None or not props.volume_loaded or not props.realtime_mpr:
        return
    if bool(props.get("safe_mpr_active", False)):
        # Review planes are controlled only by the dedicated modal operators.
        # This prevents native G/R transforms from launching unsafe image writes.
        return

    # Comparing matrix_basis rather than matrix_world is essential: rotating the
    # root changes every child's world matrix, but not its pose relative to the
    # DICOM volume. Only a direct edit of a plane should resample the volume.
    for orientation, spec in PLANE_SPECS.items():
        obj = bpy.data.objects.get(spec["object"])
        if obj is None:
            continue
        signature = _matrix_basis_signature(obj)
        previous = RUNTIME.plane_matrix_cache.get(orientation)
        if previous is None:
            RUNTIME.plane_matrix_cache[orientation] = signature
            continue
        if signature != previous:
            RUNTIME.plane_matrix_cache[orientation] = signature
            _queue_realtime_transform(orientation)


def _clear_pending_refresh_state() -> None:
    RUNTIME.timer_registered = False
    RUNTIME.transform_timer_registered = False
    RUNTIME.requested_plane_geometry_refresh = False
    RUNTIME.requested_plane_image_refresh = False
    RUNTIME.requested_visibility_refresh = False
    RUNTIME.requested_volume_material_refresh = False
    RUNTIME.surface_preview_timer_registered = False
    RUNTIME.surface_preview_generation += 1
    RUNTIME.surface_preview_building = False
    RUNTIME.pending_transform_orientations.clear()
    RUNTIME.final_transform_orientations.clear()


@persistent
def dicom_wizard_pro_undo_pre(*_args) -> None:
    """Freeze callbacks before Blender swaps the undo memfile/depsgraph."""
    RUNTIME.undo_in_progress = True
    RUNTIME.update_lock = True
    RUNTIME.undo_repair_pending = False
    lifecycle.cancel_module_timers(__name__)
    _clear_pending_refresh_state()


def _repair_after_undo():
    """Repair links after the new depsgraph is stable, never inside undo itself."""
    if not RUNTIME.undo_repair_pending:
        return None
    RUNTIME.undo_repair_pending = False
    if RUNTIME.undo_in_progress:
        return 0.10
    try:
        scene = getattr(bpy.context, "scene", None)
        props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
        if props is None or not RUNTIME.is_loaded() or not bool(getattr(props, "volume_loaded", False)):
            return None
        volume = bpy.data.objects.get(VOLUME_OBJECT_NAME)
        if volume is not None and volume.type == "VOLUME":
            material = bpy.data.materials.get(VOLUME_MATERIAL_NAME)
            if not _volume_material_is_valid(material):
                material = get_or_create_volume_material(force_rebuild=True)
            slots = volume.data.materials
            if len(slots) == 0:
                slots.append(material)
            elif slots[0] != material:
                slots[0] = material
            refresh_volume_material(bpy.context, allow_rebuild=False)
        update_visibility(bpy.context)
        if int(getattr(props, "step", 1)) == 3 and _auto_solid_preview_enabled(props):
            schedule_surface_preview(bpy.context, immediate=False)
        force_ui_redraw()
    except Exception as exc:
        print("DICOM safe undo repair warning:", repr(exc))
    return None


@persistent
def dicom_wizard_pro_undo_post(*_args) -> None:
    """Resume only after undo completed and defer all material access one tick."""
    RUNTIME.undo_in_progress = False
    RUNTIME.update_lock = False
    _clear_pending_refresh_state()
    RUNTIME.undo_repair_pending = True
    try:
        lifecycle.register_timer(_repair_after_undo, first_interval=0.18)
    except Exception:
        RUNTIME.undo_repair_pending = False


@persistent
def dicom_wizard_pro_redo_pre(*_args) -> None:
    dicom_wizard_pro_undo_pre(*_args)


@persistent
def dicom_wizard_pro_redo_post(*_args) -> None:
    dicom_wizard_pro_undo_post(*_args)


def register_undo_handlers() -> None:
    unregister_undo_handlers()
    bpy.app.handlers.undo_pre.append(dicom_wizard_pro_undo_pre)
    bpy.app.handlers.undo_post.append(dicom_wizard_pro_undo_post)
    bpy.app.handlers.redo_pre.append(dicom_wizard_pro_redo_pre)
    bpy.app.handlers.redo_post.append(dicom_wizard_pro_redo_post)


def unregister_undo_handlers() -> None:
    handler_groups = (
        (bpy.app.handlers.undo_pre, "dicom_wizard_pro_undo_pre"),
        (bpy.app.handlers.undo_post, "dicom_wizard_pro_undo_post"),
        (bpy.app.handlers.redo_pre, "dicom_wizard_pro_redo_pre"),
        (bpy.app.handlers.redo_post, "dicom_wizard_pro_redo_post"),
    )
    for handlers, wanted_name in handler_groups:
        for handler in list(handlers):
            if getattr(handler, "__name__", "") == wanted_name:
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass


def register_realtime_handler() -> None:
    unregister_realtime_handler()
    bpy.app.handlers.depsgraph_update_post.append(dicom_wizard_pro_depsgraph_update)


def unregister_realtime_handler() -> None:
    for handler in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(handler, "__name__", "") == "dicom_wizard_pro_depsgraph_update":
            try:
                bpy.app.handlers.depsgraph_update_post.remove(handler)
            except ValueError:
                pass


# =============================================================================
# MODULE: operators.py
# =============================================================================

