def _safe_mpr_schedule_native_refresh(orientation):
    """Schedule only the final full-resolution image after interactive preview."""
    orientation = str(orientation).upper()
    RUNTIME.final_transform_orientations.add(orientation)
    RUNTIME.last_transform_event_time = time.monotonic()
    if RUNTIME.transform_timer_registered:
        return
    RUNTIME.transform_timer_registered = True
    try:
        lifecycle.register_timer(
            _run_realtime_transform_refresh,
            first_interval=REALTIME_FINAL_DELAY_SECONDS,
        )
    except Exception:
        RUNTIME.transform_timer_registered = False


def _safe_mpr_set_axis_percent(context, props, role, percent, *, final=False):
    """Move exactly one diagnostic cut along its anatomical normal axis.

    AXIAL    -> axial_move_z
    CORONAL  -> coronal_move_y
    SAGITTAL -> sagittal_move_x

    Property callbacks are intentionally suppressed here. The plane matrix and
    the displayed MPR image are refreshed explicitly, which avoids depending on
    a delayed callback context belonging to a Quad View sub-region.
    """
    role = str(role).upper()
    spec = MPR_SLIDER_SPECS.get(role)
    if spec is None or not RUNTIME.is_loaded():
        return False

    percent = clamp(float(percent), 0.0, 100.0)
    property_name = spec["property"]

    RUNTIME.update_lock = True
    try:
        setattr(props, property_name, percent)
    finally:
        RUNTIME.update_lock = False

    try:
        _apply_axis_controls_to_plane(
            context,
            role,
            schedule_refresh=False,
        )
        if final:
            _safe_review_schedule_image_refresh(
                role,
                final_axis=SAFE_REVIEW_MAX_AXIS,
            )
        else:
            _safe_review_request_realtime_refresh(role)
        props.status = (
            f"{spec['short_label']} · eje {spec['axis']} · "
            f"{percent:.1f}%"
        )
        force_ui_redraw()
        return True
    except Exception as exc:
        props.status = f"No se pudo mover {spec['short_label']}: {exc}"
        print("DICOM safe MPR axis movement error:", repr(exc))
        return False


def _safe_mpr_set_plane_rotation(
    context,
    props,
    role,
    horizontal_degrees,
    vertical_degrees,
    *,
    final=False,
):
    """Rotate one plane around its two in-plane DICOM-local axes."""
    role = str(role).upper()
    spec = MPR_ROTATION_SPECS.get(role)
    if spec is None or not RUNTIME.is_loaded():
        return False

    horizontal_degrees = clamp(float(horizontal_degrees), -180.0, 180.0)
    vertical_degrees = clamp(float(vertical_degrees), -180.0, 180.0)

    RUNTIME.update_lock = True
    try:
        setattr(
            props,
            spec["horizontal_property"],
            horizontal_degrees,
        )
        setattr(
            props,
            spec["vertical_property"],
            vertical_degrees,
        )
    finally:
        RUNTIME.update_lock = False

    try:
        _apply_axis_controls_to_plane(
            context,
            role,
            schedule_refresh=False,
        )
        if final:
            _safe_review_schedule_image_refresh(
                role,
                final_axis=SAFE_REVIEW_MAX_AXIS,
            )
        else:
            _safe_review_request_realtime_refresh(role)

        props.status = (
            f"{spec['label']} · "
            f"{spec['horizontal_axis']} {horizontal_degrees:+.1f}° · "
            f"{spec['vertical_axis']} {vertical_degrees:+.1f}°"
        )
        force_ui_redraw()
        return True
    except Exception as exc:
        props.status = f"No se pudo rotar {spec['label']}: {exc}"
        print("DICOM review-plane rotation error:", repr(exc))
        return False


def _safe_mpr_set_slider_from_mouse(context, props, role, region, mouse_x, *, final=False):
    if role not in MPR_SLIDER_SPECS or region is None:
        return False
    x0 = float(region.x + 22)
    x1 = float(region.x + max(23, region.width - 22))
    percent = 100.0 * (float(mouse_x) - x0) / max(1.0, x1 - x0)
    return _safe_mpr_set_axis_percent(
        context,
        props,
        role,
        percent,
        final=final,
    )


class DICOMWIZARDPRO_OT_radiographic_quad_view(Operator):
    """Compatibility operator that opens the new single-view plane review."""

    bl_idname = "dicom_wizard_pro.radiographic_quad_view"
    bl_label = "Revisión 3D con planos"
    bl_description = (
        "Muestra el STL en una sola vista 3D con un plano móvil Z "
        "y otro plano móvil X"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return (
            props is not None
            and props.step == 4
            and props.volume_loaded
            and RUNTIME.is_loaded()
            and context.area is not None
            and context.area.type == "VIEW_3D"
        )

    def invoke(self, context, event):
        ok, message = _safe_mpr_open(context)
        self.report({"INFO"} if ok else {"ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}

    def execute(self, context):
        ok, message = _safe_mpr_open(context)
        self.report({"INFO"} if ok else {"ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class DICOMWIZARDPRO_OT_move_review_plane(Operator):
    """Move one review plane by horizontal mouse motion."""

    bl_idname = "dicom_wizard_pro.move_review_plane"
    bl_label = "Mover plano"
    bl_description = (
        "Pulsa, mueve el ratón horizontalmente y vuelve a pulsar para fijar"
    )
    bl_options = {"REGISTER", "BLOCKING"}

    role: bpy.props.EnumProperty(
        name="Plano",
        items=[
            ("AXIAL", "Plano Z", "Mueve el plano horizontal sobre el eje Z"),
            ("SAGITTAL", "Plano X", "Mueve el plano vertical sobre el eje X"),
        ],
        default="AXIAL",
    )

    _start_mouse_x = 0
    _start_percent = 50.0
    _token = 0

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return (
            props is not None
            and bool(props.get("safe_mpr_active", False))
            and context.area is not None
            and context.area.type == "VIEW_3D"
        )

    def invoke(self, context, event):
        props = context.scene.dicom_wizard_pro
        role = str(self.role).upper()
        if role not in {"AXIAL", "SAGITTAL"}:
            return {"CANCELLED"}

        spec = MPR_SLIDER_SPECS[role]
        self._start_mouse_x = int(event.mouse_x)
        self._start_percent = float(getattr(props, spec["property"]))
        self._token = int(props.get("safe_mpr_token", 0))
        props["mpr_rotate_role"] = ""
        props["mpr_move_role"] = role
        props.status = (
            f"{spec['short_label']} · mueve · clic para recalcular"
        )

        try:
            context.window.cursor_modal_set("SCROLL_X")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        context.window_manager.modal_handler_add(self)
        force_ui_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = _safe_mpr_props(context)
        role = str(self.role).upper()

        if (
            props is None
            or not bool(props.get("safe_mpr_active", False))
            or int(props.get("safe_mpr_token", -1)) != int(self._token)
        ):
            self._finish_cursor(context)
            return {"CANCELLED"}

        spec = MPR_SLIDER_SPECS[role]

        if event.type == "MOUSEMOVE":
            area = _safe_mpr_find_owner_area(context)
            region = _area_window_region(area) if area is not None else None
            width = max(320.0, float(region.width if region is not None else 800))
            delta = float(event.mouse_x - self._start_mouse_x)
            percent = self._start_percent + 100.0 * delta / (width * 0.72)
            _safe_mpr_set_axis_percent(
                context,
                props,
                role,
                percent,
                final=False,
            )
            return {"RUNNING_MODAL"}

        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"}:
            if event.value == "PRESS":
                current = float(getattr(props, spec["property"]))
                _safe_mpr_set_axis_percent(
                    context,
                    props,
                    role,
                    current,
                    final=True,
                )
                props["mpr_move_role"] = ""
                props["mpr_rotate_role"] = ""
                props.status = (
                    f"Plano {spec['axis']} fijado en {current:.1f}%"
                )
                self._finish_cursor(context)
                force_ui_redraw()
                return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            _safe_mpr_set_axis_percent(
                context,
                props,
                role,
                self._start_percent,
                final=True,
            )
            props["mpr_move_role"] = ""
            props["mpr_rotate_role"] = ""
            props.status = "Movimiento cancelado"
            self._finish_cursor(context)
            force_ui_redraw()
            return {"CANCELLED"}

        # The wheel remains native viewport zoom.
        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "MIDDLEMOUSE",
        }:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    @staticmethod
    def _finish_cursor(context):
        try:
            context.window.cursor_modal_restore()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


class DICOMWIZARDPRO_OT_rotate_review_plane(Operator):
    """Tilt one review plane with two-dimensional mouse movement."""

    bl_idname = "dicom_wizard_pro.rotate_review_plane"
    bl_label = "Rotar plano"
    bl_description = (
        "Mueve el ratón horizontal y verticalmente para inclinar el plano; "
        "Shift permite ajuste fino"
    )
    bl_options = {"REGISTER", "BLOCKING"}

    role: bpy.props.EnumProperty(
        name="Plano",
        items=[
            (
                "AXIAL",
                "Plano Z",
                "Inclina el plano Z alrededor de X e Y",
            ),
            (
                "SAGITTAL",
                "Plano X",
                "Inclina el plano X alrededor de Y y Z",
            ),
        ],
        default="AXIAL",
    )

    _start_mouse_x = 0
    _start_mouse_y = 0
    _start_horizontal = 0.0
    _start_vertical = 0.0
    _token = 0

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return (
            props is not None
            and bool(props.get("safe_mpr_active", False))
            and context.area is not None
            and context.area.type == "VIEW_3D"
        )

    def invoke(self, context, event):
        props = context.scene.dicom_wizard_pro
        role = str(self.role).upper()
        spec = MPR_ROTATION_SPECS.get(role)
        if spec is None:
            return {"CANCELLED"}

        self._start_mouse_x = int(event.mouse_x)
        self._start_mouse_y = int(event.mouse_y)
        self._start_horizontal = float(
            getattr(props, spec["horizontal_property"])
        )
        self._start_vertical = float(
            getattr(props, spec["vertical_property"])
        )
        self._token = int(props.get("safe_mpr_token", 0))

        props["mpr_move_role"] = ""
        props["mpr_rotate_role"] = role
        props.status = (
            f"{spec['label']} · mueve · clic para recalcular · Shift=fino"
        )

        try:
            context.window.cursor_modal_set("SCROLL_XY")
        except Exception:
            try:
                context.window.cursor_modal_set("CROSSHAIR")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        context.window_manager.modal_handler_add(self)
        force_ui_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = _safe_mpr_props(context)
        role = str(self.role).upper()
        spec = MPR_ROTATION_SPECS.get(role)

        if (
            props is None
            or spec is None
            or not bool(props.get("safe_mpr_active", False))
            or int(props.get("safe_mpr_token", -1)) != int(self._token)
        ):
            self._finish_cursor(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            area = _safe_mpr_find_owner_area(context)
            region = _area_window_region(area) if area is not None else None
            width = max(
                320.0,
                float(region.width if region is not None else 800),
            )
            height = max(
                240.0,
                float(region.height if region is not None else 600),
            )

            delta_x = float(event.mouse_x - self._start_mouse_x)
            delta_y = float(event.mouse_y - self._start_mouse_y)

            # Across most of the viewport the normal range is about 120°.
            # Holding Shift reduces sensitivity to one fifth.
            fine_factor = 0.20 if bool(event.shift) else 1.0
            horizontal = (
                self._start_horizontal
                + fine_factor * 120.0 * delta_x / (width * 0.72)
            )
            vertical = (
                self._start_vertical
                + fine_factor * 120.0 * delta_y / (height * 0.72)
            )

            _safe_mpr_set_plane_rotation(
                context,
                props,
                role,
                horizontal,
                vertical,
                final=False,
            )
            return {"RUNNING_MODAL"}

        if event.type in {
            "LEFTMOUSE",
            "RET",
            "NUMPAD_ENTER",
            "SPACE",
        } and event.value == "PRESS":
            horizontal = float(
                getattr(props, spec["horizontal_property"])
            )
            vertical = float(
                getattr(props, spec["vertical_property"])
            )
            _safe_mpr_set_plane_rotation(
                context,
                props,
                role,
                horizontal,
                vertical,
                final=True,
            )
            props["mpr_rotate_role"] = ""
            props["mpr_move_role"] = ""
            props.status = (
                f"{spec['label']} fijado · "
                f"{spec['horizontal_axis']} {horizontal:+.1f}° · "
                f"{spec['vertical_axis']} {vertical:+.1f}°"
            )
            self._finish_cursor(context)
            force_ui_redraw()
            return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            _safe_mpr_set_plane_rotation(
                context,
                props,
                role,
                self._start_horizontal,
                self._start_vertical,
                final=True,
            )
            props["mpr_rotate_role"] = ""
            props["mpr_move_role"] = ""
            props.status = "Rotación cancelada"
            self._finish_cursor(context)
            force_ui_redraw()
            return {"CANCELLED"}

        # Preserve native viewport navigation while the tool is active.
        if event.type in {
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "MIDDLEMOUSE",
        }:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    @staticmethod
    def _finish_cursor(context):
        try:
            context.window.cursor_modal_restore()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


class DICOMWIZARDPRO_OT_close_safe_mpr(Operator):
    bl_idname = "dicom_wizard_pro.close_safe_mpr"
    bl_label = "Salir de revisión"
    bl_description = "Oculta los dos planos y continúa al paso Exportar"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        area = getattr(context, "area", None)
        return (
            props is not None
            and area is not None
            and area.type == "VIEW_3D"
            and bool(props.get("safe_mpr_active", False))
        )

    def execute(self, context):
        ok, message = _safe_mpr_close(context)
        self.report({"INFO"} if ok else {"ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


def _close_mpr_before_workflow_action(context) -> tuple[bool, str]:
    """Collapse native Quad View before destructive or final workflow actions."""
    props = getattr(context.scene, "dicom_wizard_pro", None)
    if props is None:
        return True, ""
    area = getattr(context, "area", None)
    active = bool(props.get("safe_mpr_active", False))
    if not active and area is not None and area.type == "VIEW_3D":
        active = _safe_mpr_native_quad_active(area)
    if not active:
        return True, ""
    return _safe_mpr_close(context)




class DICOMWIZARDPRO_OT_fit_view(Operator):
    bl_idname = "dicom_wizard_pro.fit_view"
    bl_label = "Centrar vista"
    bl_description = "Encuadra el volumen DICOM en la vista 3D"
    bl_options = {"REGISTER"}

    def execute(self, context):
        frame_viewer(context)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_fit_clinical_preview(Operator):
    bl_idname = "dicom_wizard_pro.fit_clinical_preview"
    bl_label = "Centrar CBCT"
    bl_description = "Centra y amplía el CBCT en la vista clínica limpia"
    bl_options = {"REGISTER"}

    def execute(self, context):
        configure_clinical_preview_view(context, frame=True)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_refresh(Operator):
    bl_idname = "dicom_wizard_pro.refresh"
    bl_label = "Actualizar"
    bl_description = "Actualiza manualmente el volumen, los planos y su visibilidad"
    bl_options = {"REGISTER"}

    def execute(self, context):
        update_density_labels(context.scene.dicom_wizard_pro)
        refresh_volume_material(context)
        refresh_plane_images_from_objects(context)
        update_visibility(context)
        return {"FINISHED"}







class DICOMWIZARDPRO_OT_to_segmentation(Operator):
    bl_idname = "dicom_wizard_pro.to_segmentation"
    bl_label = "Siguiente: segmentar"
    bl_description = "Analiza automáticamente la densidad y abre la segmentación por tejidos"

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded and RUNTIME.is_loaded()

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        props.step = 3
        props.show_volume = True
        props.show_planes = False
        props.show_all_planes = False
        props.show_box = False
        props.show_segmentation_overlay = False
        props.surface_preview_ready = False
        props.preview_display_mode = "SURFACE"
        props.preview_volume_opacity = 0.10
        props.surface_preview_quality = "128"
        props.auto_solid_preview = True
        try:
            if not props.auto_thresholds_ready:
                analyze_automatic_tissue_thresholds(context)
            sync_automatic_range_from_structure(props)
            props.status = (
                f"{SEGMENTATION_STRUCTURES[props.segmentation_structure]['label']} · "
                "umbrales automáticos listos"
            )
        except Exception as exc:
            props.status = f"No se pudieron analizar las densidades: {exc}"
        sync_segmentation_properties(props)
        refresh_volume_material(context)
        update_visibility(context)
        set_viewport_material_mode(context)
        configure_clinical_preview_view(context, frame=True)
        if _auto_solid_preview_enabled(props):
            schedule_surface_preview(context, immediate=True)
        else:
            props.surface_preview_status = "Motor DICOM integrado · vista por densidad"
        # Keep the framing result, then remove the giant orange cube/selection
        # that obscures the clinical threshold preview. The root remains usable
        # from the Outliner and is restored to a cube when returning to viewer.
        root = bpy.data.objects.get(ROOT_NAME)
        if root is not None:
            try:
                root.empty_display_type = "PLAIN_AXES"
                root.empty_display_size = 12.0
                root.show_in_front = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        for selected in list(context.selected_objects):
            try:
                selected.select_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            context.view_layer.objects.active = None
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        force_ui_redraw()
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_undo_last(Operator):
    bl_idname = "dicom_wizard_pro.undo_last"
    bl_label = "Deshacer última acción"
    bl_description = "Deshace exactamente la última operación, igual que Ctrl+Z"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if RUNTIME.undo_in_progress:
            self.report({'WARNING'}, "Ya hay una operación de deshacer en curso")
            return {'CANCELLED'}
        try:
            result = bpy.ops.ed.undo()
        except RuntimeError as exc:
            self.report({'WARNING'}, f"No hay una acción disponible para deshacer: {exc}")
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            self.report({'INFO'}, "No hay ninguna acción para deshacer")
            return {'CANCELLED'}
        props.status = "Última acción deshecha"
        return {'FINISHED'}


class DICOMWIZARDPRO_OT_back_to_viewer(Operator):
    bl_idname = "dicom_wizard_pro.back_to_viewer"
    bl_label = "Volver a visualización"
    bl_description = "Vuelve al paso de visualización sin perder la segmentación"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        restore_clinical_preview_view(context)
        props.step = 2
        props.show_volume = True
        props.show_planes = True
        props.show_all_planes = False
        try:
            get_root(get_collection())
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        refresh_volume_material(context)
        update_visibility(context)
        refresh_plane_images_from_objects(context, all_planes=False)
        props.status = "Visor listo"
        return {"FINISHED"}








class DICOMWIZARDPRO_OT_clear_drawings(Operator):
    bl_idname = "dicom_wizard_pro.clear_drawings"
    bl_label = "Borrar máscara"
    bl_description = "Borra la máscara automática de la estructura activa"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        clear_segmentation_drawings(props, props.segmentation_structure, clear_mask=True)
        _refresh_segmentation_views(context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS)
        props.status = "Máscara automática eliminada"
        return {"FINISHED"}



class DICOMWIZARDPRO_OT_analyze_tissues(Operator):
    bl_idname = "dicom_wizard_pro.analyze_tissues"
    bl_label = "Analizar densidades"
    bl_description = "Detecta automáticamente aire/tejido, tejido/hueso y hueso/diente en este CBCT"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        try:
            props.status = "Analizando densidades del CBCT…"
            analyze_automatic_tissue_thresholds(context)
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Hueso y dentición diferenciados por densidad adaptativa")
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_adjust_tissue_sensitivity(Operator):
    bl_idname = "dicom_wizard_pro.adjust_tissue_sensitivity"
    bl_label = "Ajustar segmentación"
    bl_description = "Ajuste simple del umbral sin cambiar parámetros técnicos"

    direction: bpy.props.EnumProperty(
        items=[("MORE", "Más", "Incluye más anatomía"),
               ("LESS", "Menos", "Hace la segmentación más selectiva")],
        default="MORE",
    )

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        try:
            if not props.auto_thresholds_ready:
                analyze_automatic_tissue_thresholds(context)
                sync_automatic_range_from_structure(props)
            structure = str(props.segmentation_structure).upper()
            sign = -1.0 if self.direction == "MORE" else 1.0
            if structure == "TEETH":
                seed = float(props.auto_tooth_seed_threshold)
                floor = float(props.auto_soft_bone_threshold)
                current = float(props.auto_range_low)
                span = max(seed - float(props.auto_bone_teeth_threshold),
                           (float(props.auto_robust_high)-floor) * 0.04, 1.0)
                step = span * 0.10
                current += sign * step
                current = max(floor + 1.0, min(seed - 1.0, current))
                props.auto_range_low = current
            else:
                current = float(props.auto_range_low)
                span = max(float(props.auto_robust_high)-float(props.auto_soft_bone_threshold), 1.0)
                step = span * 0.025
                current += sign * step
                low_bound = float(props.auto_air_soft_threshold) + 1.0
                high_bound = float(props.auto_bone_teeth_threshold) - 1.0
                if structure == "BONE":
                    high_bound = float(props.auto_robust_high) - 1.0
                props.auto_range_low = max(low_bound, min(high_bound, current))
            state = get_segmentation_state(structure)
            state["stale"] = True
            schedule_surface_preview(context, immediate=True)
            props.status = "Segmentación ajustada · revisa la vista previa"
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_reset_tissue_range(Operator):
    bl_idname = "dicom_wizard_pro.reset_tissue_range"
    bl_label = "Restaurar umbrales automáticos"
    bl_description = "Restaura los límites calculados para el modo de segmentación seleccionado"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if not props.auto_thresholds_ready:
            try:
                analyze_automatic_tissue_thresholds(context)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        sync_automatic_range_from_structure(props)
        refresh_volume_material(context)
        props.status = "Umbrales automáticos restaurados"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_calculate_segmentation(Operator):
    bl_idname = "dicom_wizard_pro.calculate_segmentation"
    bl_label = "Segmentar automáticamente"
    bl_description = "Genera una máscara 3D completa usando el rango adaptativo del tejido"

    target: bpy.props.StringProperty(default="")

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        started = time.perf_counter()
        try:
            if self.target in SEGMENTATION_STRUCTURES:
                props.segmentation_structure = self.target
                sync_automatic_range_from_structure(props)
            props.status = f"Segmentando {SEGMENTATION_STRUCTURES[props.segmentation_structure]['label']}…"
            segment_tissue_automatically(context)
            # Optional component cleanup is applied equally to all three
            # adaptive density modes. The mask itself is produced by DSG.
            if bool(getattr(props, "auto_clean_small_islands", True)):
                try:
                    remove_small_islands(context, keep_largest=False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        props.show_volume = True
        props.show_planes = True
        props.show_all_planes = False
        props.show_segmentation_overlay = True
        refresh_volume_material(context)
        update_visibility(context)
        elapsed = time.perf_counter() - started
        props.status = (
            f"{SEGMENTATION_STRUCTURES[props.segmentation_structure]['label']} segmentado "
            f"automáticamente · {elapsed:.2f} s")
        self.report({"INFO"}, props.status)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_remove_small_islands(Operator):
    bl_idname = "dicom_wizard_pro.remove_small_islands"
    bl_label = "Eliminar islas pequeñas"
    bl_description = "Elimina componentes cuyo volumen sea menor que el límite en mm³"

    def execute(self, context):
        try:
            removed = remove_small_islands(context, keep_largest=False)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.scene.dicom_wizard_pro.status = f"Se eliminaron {removed:,} vóxeles de islas pequeñas"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_keep_largest_island(Operator):
    bl_idname = "dicom_wizard_pro.keep_largest_island"
    bl_label = "Conservar isla mayor"
    bl_description = "Conserva solamente el componente conectado de mayor tamaño"

    def execute(self, context):
        try:
            removed = remove_small_islands(context, keep_largest=True)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.scene.dicom_wizard_pro.status = f"Isla principal conservada; {removed:,} vóxeles eliminados"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_close_gaps(Operator):
    bl_idname = "dicom_wizard_pro.close_gaps"
    bl_label = "Cerrar discontinuidades"
    bl_description = "Cierra pequeñas interrupciones sin rellenar todas las cavidades"

    def execute(self, context):
        try:
            close_segmentation_gaps(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.scene.dicom_wizard_pro.status = "Discontinuidades cerradas"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_fill_holes(Operator):
    bl_idname = "dicom_wizard_pro.fill_holes"
    bl_label = "Rellenar huecos internos"
    bl_description = "Rellena cavidades cerradas; úsalo con cuidado en anatomía real"

    def execute(self, context):
        try:
            fill_segmentation_holes(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.scene.dicom_wizard_pro.status = "Huecos internos rellenados"
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# DSG 8.8.6 non-blocking CUDA-aware CBCT workflow
# -----------------------------------------------------------------------------
# Neural work happens in cbct_ai_runtime's worker thread. Blender data is never
# touched there. This timer commits the result and creates at most one tooth mesh
# per tick, keeping Blender's event loop alive throughout the operation.
# This state is intentionally module-owned and always initialized before an
# immediate route can arm its asynchronous workers.  The 9.2.79 helper-restore
# merge kept the performance-session functions but accidentally omitted this
# backing object, so every immediate segmentation aborted before launching AI.
_AI_PERFORMANCE_SESSION = {
    "active": False,
    "viewport_shading": [],
    "changed_viewports": 0,
}

_ASYNC_SEGMENTATION = {
    "active": False,
    "phase": "",
    "structure": "",
    "kind": "",
    "source_signature": "",
    "started": 0.0,
    "builder": None,
    "tooth_summary": None,
    "postprocess_started": False,
    "postprocess_result": None,
    "prepared_surfaces": None,
    "canal_verifier_mask": None,
    "canal_verifier_origin": None,
    "canal_verifier_stats": None,
    "bone_semantic_mask": None,
    "bone_semantic_origin": None,
    "maxilla_semantic_mask": None,
    "maxilla_semantic_origin": None,
    "mandible_semantic_mask": None,
    "mandible_semantic_origin": None,
    "tooth_verifier_upper_mask": None,
    "tooth_verifier_upper_origin": None,
    "tooth_verifier_lower_mask": None,
    "tooth_verifier_lower_origin": None,
    "tooth_path_stats": None,
    "bone_build_step": "",
    "bone_obj_name": "",
    "maxilla_obj_name": "",
    "mandible_obj_name": "",
    "canal_obj_name": "",
    "canal_summary": None,
    "progress": 0.0,
    "progress_phase": "",
    "progress_detail": "",
    "last_message": "",
}



_POSTPROCESS_JOB_LOCK = threading.Lock()
_POSTPROCESS_JOB = {
    "running": False,
    "done": False,
    "error": "",
    "message": "",
    "result": None,
    "started": 0.0,
    "job_dir": "",
    "processes": {},
    "base_result": None,
    "task_messages": {},
}


def _postprocess_job_state() -> dict:
    with _POSTPROCESS_JOB_LOCK:
        return {
            "running": bool(_POSTPROCESS_JOB.get("running")),
            "done": bool(_POSTPROCESS_JOB.get("done")),
            "error": str(_POSTPROCESS_JOB.get("error") or ""),
            "message": str(_POSTPROCESS_JOB.get("message") or ""),
            "started": float(_POSTPROCESS_JOB.get("started") or 0.0),
            "task_messages": dict(_POSTPROCESS_JOB.get("task_messages") or {}),
        }


def _clear_postprocess_job_dir():
    with _POSTPROCESS_JOB_LOCK:
        job_dir = str(_POSTPROCESS_JOB.get("job_dir") or "")
        _POSTPROCESS_JOB["job_dir"] = ""
        _POSTPROCESS_JOB["processes"] = {}
    if job_dir:
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _cancel_postprocess_workers():
    with _POSTPROCESS_JOB_LOCK:
        processes = dict(_POSTPROCESS_JOB.get("processes") or {})
        _POSTPROCESS_JOB.update(
            running=False, done=False, error="Cancelado",
            message="Postproceso cancelado", processes={}, task_messages={}
        )
    for proc in processes.values():
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _clear_postprocess_job_dir()


def _postprocess_write_optional_array(base_dir, name, arr):
    np = load_numpy()
    if arr is None:
        return ""
    path = Path(base_dir) / f"{name}.npy"
    np.save(str(path), np.asarray(arr), allow_pickle=False)
    return str(path)


def _launch_postprocess_worker(blender_binary: Path, request_path: Path, log_path: Path):
    log_handle = log_path.open("w", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    command = [
        str(blender_binary), "--background", "--factory-startup",
        "--python", str(Path(__file__).resolve().parent / "cbct_postprocess_worker.py"),
        "--", str(request_path),
    ]
    process = subprocess.Popen(
        command, stdout=log_handle, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=env,
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
    )
    return process, log_handle


def _start_universal_postprocess_job(result: dict) -> bool:
    """Run pure numerical dental reconciliation + mesh preparation off the UI path.

    No bpy datablock is touched here. The existing DSG AI architecture already
    separates numerical inference from main-thread Blender commits; 9.2.15 extends
    that same boundary to the previously blocking 70-72% dental post-processing.
    """
    with _POSTPROCESS_JOB_LOCK:
        if bool(_POSTPROCESS_JOB.get("running")):
            return False
        _POSTPROCESS_JOB.update(
            running=True, done=False, error="", message="Preparando reconciliación dental…",
            result=None, started=time.perf_counter(),
        )

    upper_mask = _ASYNC_SEGMENTATION.get("tooth_verifier_upper_mask")
    upper_origin = _ASYNC_SEGMENTATION.get("tooth_verifier_upper_origin") or (0, 0, 0)
    lower_mask = _ASYNC_SEGMENTATION.get("tooth_verifier_lower_mask")
    lower_origin = _ASYNC_SEGMENTATION.get("tooth_verifier_lower_origin") or (0, 0, 0)
    bone_semantic_mask = _ASYNC_SEGMENTATION.get("bone_semantic_mask")
    bone_semantic_origin = _ASYNC_SEGMENTATION.get("bone_semantic_origin") or (0, 0, 0)
    maxilla_semantic_mask = _ASYNC_SEGMENTATION.get("maxilla_semantic_mask")
    maxilla_semantic_origin = _ASYNC_SEGMENTATION.get("maxilla_semantic_origin") or (0, 0, 0)
    mandible_semantic_mask = _ASYNC_SEGMENTATION.get("mandible_semantic_mask")
    mandible_semantic_origin = _ASYNC_SEGMENTATION.get("mandible_semantic_origin") or (0, 0, 0)
    canal_verifier_mask = _ASYNC_SEGMENTATION.get("canal_verifier_mask")
    canal_verifier_origin = _ASYNC_SEGMENTATION.get("canal_verifier_origin") or (0, 0, 0)
    canal_verifier_stats = dict(_ASYNC_SEGMENTATION.get("canal_verifier_stats") or {})

    def _worker():
        try:
            from . import cbct_dental_module
            np = load_numpy()
            labels = result.get("labels")
            with _POSTPROCESS_JOB_LOCK:
                _POSTPROCESS_JOB["message"] = "Reconciliando continuidad corona-raíz en ROI compactos…"
            path_started = time.perf_counter()
            path_stats = tooth_analysis.reconcile_universal_dentition_paths(
                np, labels, RUNTIME.spacing_zyx_mm,
                upper_support_mask=upper_mask, upper_support_origin=upper_origin,
                lower_support_mask=lower_mask, lower_support_origin=lower_origin,
            )
            path_s = time.perf_counter() - path_started
            with _POSTPROCESS_JOB_LOCK:
                _POSTPROCESS_JOB["message"] = "Preparando mallas dentales y refinado CBCT fuera del hilo de Blender…"
            mesh_payload = cbct_dental_module.prepare_universal_dentition_meshes(labels)
            with _POSTPROCESS_JOB_LOCK:
                _POSTPROCESS_JOB["message"] = "Preparando maxila, mandíbula y canal fuera del hilo de Blender…"
            # Prefer UniversalLab jaw classes 54/53; retain DentalSegmentator
            # anatomy as fallback exactly as the clinical route already does.
            u_max, u_max_origin = _compact_mask_for_classes(labels, (54,))
            max_mask = u_max if u_max is not None and bool(u_max.any()) else maxilla_semantic_mask
            max_origin = u_max_origin if u_max is not None and bool(u_max.any()) else maxilla_semantic_origin
            max_class = 54 if u_max is not None and bool(u_max.any()) else 1
            max_source = "UNIVERSALLAB" if max_class == 54 else "DENTALSEGMENTATOR_8_7"
            u_man, u_man_origin = _compact_mask_for_classes(labels, (53,))
            man_mask = u_man if u_man is not None and bool(u_man.any()) else mandible_semantic_mask
            man_origin = u_man_origin if u_man is not None and bool(u_man.any()) else mandible_semantic_origin
            man_class = 53 if u_man is not None and bool(u_man.any()) else 2
            man_source = "UNIVERSALLAB" if man_class == 53 else "DENTALSEGMENTATOR_8_7"
            surfaces_started = time.perf_counter()
            surfaces = {
                "maxilla": _prepare_mask_surface_arrays(
                    max_mask, max_origin, kind="JAW", label=max_class, max_axis=384, refine=True
                ),
                "mandible": _prepare_mask_surface_arrays(
                    man_mask, man_origin, kind="JAW", label=man_class, max_axis=384, refine=True
                ),
                "canal": _prepare_canal_surface_arrays(
                    labels, verifier_mask=canal_verifier_mask, verifier_origin=canal_verifier_origin,
                    verifier_stats=canal_verifier_stats,
                ),
                "maxilla_class": int(max_class), "maxilla_source": str(max_source),
                "mandible_class": int(man_class), "mandible_source": str(man_source),
                "surface_prepare_s": 0.0,
            }
            surfaces["surface_prepare_s"] = float(time.perf_counter() - surfaces_started)
            crop_info = result.setdefault("crop_info", {})
            crop_info["tooth_path_reconciliation"] = dict(path_stats or {})
            crop_info["tooth_postprocess_times"] = {
                "path_reconciliation_s": float(path_s),
                "mesh_prepare_s": float(mesh_payload.get("prepare_s", 0.0) or 0.0),
                "surface_extract_s": float(mesh_payload.get("surface_extract_s", 0.0) or 0.0),
            }
            crop_info["tooth_surface_meshing"] = {
                "engine_counts": dict(mesh_payload.get("engine_counts") or {}),
                "vtk_available": bool(mesh_payload.get("vtk_available", False)),
                "fallback_count": int(mesh_payload.get("mesher_fallback_count", 0) or 0),
                "native_preview_count": int(mesh_payload.get("native_preview_count", 0) or 0),
                "roi_total_voxels": int(mesh_payload.get("roi_total_voxels", 0) or 0),
                "roi_vs_naive_fraction": float(mesh_payload.get("roi_vs_naive_fraction", 0.0) or 0.0),
                "bbox_cache": bool(mesh_payload.get("bbox_cache", False)),
                "roi_worker_count": int(mesh_payload.get("roi_worker_count", 1) or 1),
                "native_fullres_count": int(mesh_payload.get("native_fullres_count", 0) or 0),
                "single_pass": bool(mesh_payload.get("single_pass", False)),
                "per_tooth_binary_masks": bool(mesh_payload.get("per_tooth_binary_masks", False)),
                "component_cleanup_stage": str(mesh_payload.get("component_cleanup_stage", "")),
                "native_resolution": bool(mesh_payload.get("native_resolution", False)),
            }
            payload = {
                "result": result,
                "path_stats": dict(path_stats or {}),
                "prepared_meshes": mesh_payload,
                "prepared_surfaces": surfaces,
                "elapsed_s": float(time.perf_counter() - float(_POSTPROCESS_JOB.get("started") or time.perf_counter())),
            }
            with _POSTPROCESS_JOB_LOCK:
                _POSTPROCESS_JOB.update(running=False, done=True, error="", message="Listo", result=payload)
        except Exception as exc:
            with _POSTPROCESS_JOB_LOCK:
                _POSTPROCESS_JOB.update(
                    running=False, done=True,
                    error=f"{type(exc).__name__}: {exc}", message="Error en postproceso dental", result=None,
                )

    thread = threading.Thread(target=_worker, name="DSG-ToothPostprocess", daemon=True)
    thread.start()
    return True


def _consume_universal_postprocess_result():
    with _POSTPROCESS_JOB_LOCK:
        if not bool(_POSTPROCESS_JOB.get("done")):
            return None
        payload = _POSTPROCESS_JOB.get("result")
        error = str(_POSTPROCESS_JOB.get("error") or "")
        _POSTPROCESS_JOB.update(running=False, done=False, error="", message="", result=None, started=0.0)
    if error:
        raise RuntimeError(error)
    return payload


_AI_PERFORMANCE_SESSION = {
    "active": False,
    "viewport_shading": [],
    "changed_viewports": 0,
}


def _begin_ai_performance_session(context) -> dict:
    """Reduce only measured/reversible graphics pressure during neural inference.

    DSG deliberately does not rewrite global Undo preferences. Neural inference
    itself does not create Blender undo states, changing user-wide history limits
    does not reliably free existing undo memory, and doing so violates least
    astonishment. Material/Rendered viewports do consume graphics resources, so
    those are temporarily switched to Solid and restored exactly afterwards.
    Cycles CUDA/OptiX settings are never changed; PyTorch CUDA is independent.
    """
    if bool(_AI_PERFORMANCE_SESSION.get("active")):
        return dict(_AI_PERFORMANCE_SESSION)
    props = getattr(getattr(context, "scene", None), "dicom_wizard_pro", None)
    if props is not None and not bool(getattr(props, "ai_manage_blender_resources", True)):
        return dict(_AI_PERFORMANCE_SESSION)

    session = {"active": True, "viewport_shading": [], "changed_viewports": 0}
    try:
        wm = context.window_manager
        for window in list(getattr(wm, "windows", ())):
            screen = getattr(window, "screen", None)
            if screen is None:
                continue
            for area in list(getattr(screen, "areas", ())):
                if getattr(area, "type", "") != "VIEW_3D":
                    continue
                shading = getattr(getattr(area.spaces, "active", None), "shading", None)
                old_type = str(getattr(shading, "type", "SOLID")) if shading is not None else "SOLID"
                if old_type not in {"MATERIAL", "RENDERED"}:
                    continue
                session["viewport_shading"].append(
                    (int(window.as_pointer()), int(area.as_pointer()), old_type)
                )
                try:
                    shading.type = "SOLID"
                    session["changed_viewports"] += 1
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
    except Exception as exc:
        print("[DSG Performance] Viewport profile warning:", repr(exc))

    _AI_PERFORMANCE_SESSION.clear()
    _AI_PERFORMANCE_SESSION.update(session)
    force_ui_redraw()
    return dict(session)


def _restore_ai_performance_session(context=None) -> None:
    if not bool(_AI_PERFORMANCE_SESSION.get("active")):
        return
    saved = dict(_AI_PERFORMANCE_SESSION)
    _AI_PERFORMANCE_SESSION.clear()
    _AI_PERFORMANCE_SESSION.update(active=False, viewport_shading=[], changed_viewports=0)
    context = context or bpy.context
    wanted = {(int(w), int(a)): str(t) for w, a, t in saved.get("viewport_shading", [])}
    if wanted:
        try:
            for window in list(getattr(context.window_manager, "windows", ())):
                screen = getattr(window, "screen", None)
                if screen is None:
                    continue
                wp = int(window.as_pointer())
                for area in list(getattr(screen, "areas", ())):
                    key = (wp, int(area.as_pointer()))
                    old_type = wanted.get(key)
                    if old_type is None or getattr(area, "type", "") != "VIEW_3D":
                        continue
                    shading = getattr(getattr(area.spaces, "active", None), "shading", None)
                    if shading is not None:
                        try:
                            shading.type = old_type
                        except Exception:
                            _DSG_LOG.debug("suppressed exception", exc_info=True)
        except Exception as exc:
            print("[DSG Performance] Viewport restore warning:", repr(exc))
    force_ui_redraw()


def ai_performance_session_state() -> dict:
    return dict(_AI_PERFORMANCE_SESSION)


def _segmentation_progress_from_ai_message(message: str, *, verifier: bool = False) -> tuple[float, str]:
    """Map real nnU-Net pipeline messages to a stable phase progress value.

    The network's internal sliding-window percentage is not exposed by nnU-Net in
    this integration, so DSG deliberately does NOT fabricate one. The progress
    bar represents completed workflow phases; during the long neural-network
    phase the percentage remains stable while elapsed time continues to update.
    """
    text = str(message or "").strip().lower()

    if verifier:
        base = 0.04
        mapping = (
            ("recortando", 0.05, "Preparando verificador anatómico"),
            ("cargando", 0.07, "Cargando DentalSegmentator"),
            ("preprocesando", 0.09, "Preprocesando verificador"),
            ("segmentando", 0.12, "Verificando canal y continuidad dental"),
            ("reconstruyendo", 0.15, "Reconstruyendo soporte anatómico"),
            ("restaurando", 0.17, "Finalizando verificador"),
            ("terminada", 0.18, "Verificador anatómico listo"),
        )
    else:
        base = 0.20
        mapping = (
            ("recortando", 0.21, "Preparando CBCT"),
            ("localizando arcadas", 0.24, "Localizando arcadas"),
            ("roi dental", 0.27, "Preparando ROI dental"),
            ("universalLab directo".lower(), 0.27, "Preparando UniversalLab"),
            ("cargando", 0.31, "Cargando UniversalLab"),
            ("reutilizado", 0.33, "UniversalLab cargado"),
            ("preprocesando", 0.37, "Preprocesando CBCT"),
            ("segmentando cbct", 0.45, "Segmentando dientes con IA"),
            ("cuda híbrido", 0.49, "Segmentando con CUDA híbrido"),
            ("reconstruyendo etiquetas", 0.62, "Reconstruyendo etiquetas"),
            ("exportando por clases", 0.64, "Reconstruyendo etiquetas por clases"),
            ("restaurando etiquetas", 0.67, "Restaurando resolución CBCT"),
            ("comprobando maxila", 0.69, "Verificando FDI y arcadas"),
            ("terminada", 0.70, "Inferencia dental terminada"),
        )

    factor = base
    phase = "Procesando IA"
    for token, candidate, label in mapping:
        if token in text:
            factor = float(candidate)
            phase = str(label)
    return factor, phase


def _set_segmentation_progress(context, factor: float, phase: str, detail: str = "") -> None:
    factor = max(0.0, min(1.0, float(factor)))
    _ASYNC_SEGMENTATION["progress"] = factor
    _ASYNC_SEGMENTATION["progress_phase"] = str(phase or "")
    _ASYNC_SEGMENTATION["progress_detail"] = str(detail or "")

    scene = getattr(context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
    if props is not None:
        try:
            props.segmentation_progress = factor
            props.segmentation_progress_phase = str(phase or "")
            props.segmentation_progress_detail = str(detail or "")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Blender's own status-bar progress complements the explicit DSG panel bar.
    try:
        progress_update(context, int(round(factor * 100.0)))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        core.set_status_bar(
            context,
            f"{factor * 100.0:.0f}% · {phase}" + (f" · {detail}" if detail else ""),
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    force_ui_redraw()


def _begin_segmentation_progress(context, phase: str) -> None:
    try:
        progress_begin(context, 100)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _set_segmentation_progress(context, 0.01, phase)


def _end_segmentation_progress(context, *, success: bool) -> None:
    if success:
        _set_segmentation_progress(context, 1.0, "Segmentación terminada")
    try:
        progress_end(context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Keep 100% only for the current redraw; reset telemetry after completion so
    # stale progress never appears on a new case.
    scene = getattr(context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
    if props is not None and not success:
        try:
            props.segmentation_progress = 0.0
            props.segmentation_progress_phase = ""
            props.segmentation_progress_detail = ""
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def segmentation_progress_snapshot(context=None) -> dict[str, object]:
    context = context or bpy.context
    active = bool(_ASYNC_SEGMENTATION.get("active"))
    factor = float(_ASYNC_SEGMENTATION.get("progress", 0.0) or 0.0)
    phase = str(_ASYNC_SEGMENTATION.get("progress_phase", "") or "")
    detail = str(_ASYNC_SEGMENTATION.get("progress_detail", "") or "")
    started = float(_ASYNC_SEGMENTATION.get("started", 0.0) or 0.0)
    elapsed = max(0.0, time.perf_counter() - started) if active and started > 0.0 else 0.0
    return {
        "active": active,
        "factor": max(0.0, min(1.0, factor)),
        "phase": phase,
        "detail": detail,
        "elapsed_s": elapsed,
    }



def semantic_workflow_busy() -> bool:
    """Return whether a clinical segmentation transaction is active."""
    if bool(_ASYNC_SEGMENTATION.get("active")):
        return True
    try:
        from . import cbct_pipeline_client
        if bool(cbct_pipeline_client.state().get("running")):
            return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        from . import cbct_ai_runtime
        return bool(cbct_ai_runtime.prediction_job_state().get("running"))
    except Exception:
        return False



def _cache_async_semantic_result(result: dict) -> object:
    """Commit a worker-produced labelmap to DSG runtime on Blender's main thread."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    signature = str(result.get("source_signature", ""))
    if signature != _semantic_source_signature():
        raise RuntimeError("El CBCT cambió durante la segmentación; el resultado se descartó por seguridad")
    kind = str(result.get("kind", "")).lower()
    labels = np.ascontiguousarray(result["labels"])
    metadata = dict(result.get("metadata") or {})
    crop_info = dict(result.get("crop_info") or {})
    crop_info["stage_times"] = dict(result.get("stage_times") or {})

    if kind == "universal" and ("arch" not in crop_info or "laterality" not in crop_info):
        # Legacy-job fallback: use the same semantic SSOT as the current worker.
        try:
            from . import cbct_dental_module
            semantic_check = cbct_dental_module.correct_universal_semantics(labels)
            crop_info["arch"] = dict(semantic_check.get("arch") or {})
            crop_info["laterality"] = dict(semantic_check.get("laterality") or {})
            crop_info["mirroring"] = dict(semantic_check.get("laterality") or {})
        except Exception as exc:
            crop_info["arch"] = {"checked": False, "error": str(exc)}
            crop_info["laterality"] = {"checked": False, "error": str(exc)}
            crop_info["mirroring"] = dict(crop_info["laterality"])

    return _store_semantic_result(
        labels, kind=kind, signature=signature, metadata=metadata, crop_info=crop_info
    )


def _finish_async_segmentation(context, obj, *, detail: str, elapsed: float) -> None:
    props = context.scene.dicom_wizard_pro
    context.scene["DSG_last_segmentation_elapsed_s"] = float(elapsed)
    context.scene["DSG_last_segmentation_finished_at"] = float(time.time())
    context.scene["DSG_last_segmentation_success"] = True
    restore_clinical_preview_view(context)
    props.step = 4
    # 9.2.16: the OpenVDB DICOM object is a FOG_VOLUME. Once segmentation is
    # complete it only obscures the clinical meshes; keep the data loaded but
    # hide every radiographic display proxy until the user explicitly reopens it.
    props.show_volume = False
    props.show_planes = False
    props.show_all_planes = False
    props.show_box = False
    update_visibility(context)
    props.surface_preview_status = str(detail)
    if str(_ASYNC_SEGMENTATION.get("structure", "")).upper() == "ALL":
        props.status = f"Segmentación completa · {detail} · {elapsed:.1f} s · Blender no bloqueado"
    else:
        props.status = (
            f"{SEGMENTATION_STRUCTURES[props.segmentation_structure]['label']} · "
            f"{detail} · {elapsed:.1f} s · Blender no bloqueado"
        )
    _set_segmentation_progress(context, 1.0, "Segmentación terminada", props.status)
    if str(_ASYNC_SEGMENTATION.get("structure", "")).upper() == "ALL":
        try:
            route = core.clinical_route(context.scene)
            route_mode = str(_ASYNC_SEGMENTATION.get("route_mode") or "FULL").upper()
            if route == core.ROUTE_IMMEDIATE:
                context.scene["DSG_route_step"] = "IMMEDIATE_FDI_REVIEW"
            elif route == core.ROUTE_SIMPLE and route_mode == "SIMPLE_ARCHES":
                context.scene["DSG_route_step"] = "SIMPLE_REVIEW"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    # Async timers live outside the initiating operator. Push the completed
    # transaction explicitly so Ctrl+Z returns to the checkpoint before AI.
    try:
        bpy.ops.ed.undo_push(message="DSG · Segmentación CBCT terminada")
    except Exception as exc:
        print(f"[DSG Workflow] undo push warning: {exc}")
    _ASYNC_SEGMENTATION.update(
        active=False, phase="", builder=None, tooth_summary=None,
        postprocess_started=False, postprocess_result=None, prepared_surfaces=None,
        canal_verifier_mask=None, canal_verifier_origin=None,
        canal_verifier_stats=None,
        bone_semantic_mask=None, bone_semantic_origin=None,
        maxilla_semantic_mask=None, maxilla_semantic_origin=None,
        mandible_semantic_mask=None, mandible_semantic_origin=None,
        tooth_verifier_upper_mask=None, tooth_verifier_upper_origin=None,
        tooth_verifier_lower_mask=None, tooth_verifier_lower_origin=None,
        tooth_path_stats=None, universal_roi_slices_full=None, universal_roi_info=None,
        bone_build_step="", bone_obj_name="", maxilla_obj_name="", mandible_obj_name="",
        canal_obj_name="", canal_summary=None, progress=1.0,
        progress_phase="Segmentación terminada",
        progress_detail=props.status,
        last_message=props.status,
    )
    _end_segmentation_progress(context, success=True)
    _restore_ai_performance_session(context)
    try:
        from . import cbct_pipeline_client
        cbct_pipeline_client.release_process_keep_artifacts()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _abort_async_segmentation(context, message: str) -> None:
    """Abort one transaction and remove only artifacts created by that phase."""
    phase = str(_ASYNC_SEGMENTATION.get("phase", ""))
    try:
        from . import cbct_pipeline_client
        cbct_pipeline_client.cleanup_artifacts()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        from . import cbct_ai_runtime
        cbct_ai_runtime.cancel_parallel_dual_jobs()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        _cancel_postprocess_workers()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if phase in {"BUILD_TEETH", "BUILD_BONE"} or str(_ASYNC_SEGMENTATION.get("structure", "")).upper() == "ALL":
        # One-click full segmentation is transactional. Never leave a plausible
        # half-built dentition/bone result in the clinical scene.
        try:
            from . import cbct_dental_module
            cbct_dental_module.clear_dentition(keep_alignment_reference=False)
            cbct_dental_module.reset_scene_state(getattr(context, "scene", None))
            for name in (
                NAME_DICOM_BONE,
                NAME_DICOM_MAXILLA,
                NAME_DICOM_MANDIBLE,
                NAME_DICOM_MANDIBULAR_CANAL,
                NAME_DICOM_COMBINED,
                "Dental_DICOM_AlignmentRef",
            ):
                old_obj = bpy.data.objects.get(name)
                if old_obj is not None:
                    old_mesh = old_obj.data if old_obj.type == "MESH" else None
                    bpy.data.objects.remove(old_obj, do_unlink=True)
                    if old_mesh is not None and old_mesh.users == 0:
                        bpy.data.meshes.remove(old_mesh)
        except Exception as cleanup_exc:
            print(f"[DSG CBCT AI] Rollback warning: {cleanup_exc}")
    try:
        context.scene.dicom_wizard_pro.status = f"Error: {message}"
        context.scene["DSG_last_segmentation_error"] = str(message)
        context.scene["DSG_last_segmentation_error_phase"] = str(phase)
        started = float(_ASYNC_SEGMENTATION.get("started", 0.0) or 0.0)
        context.scene["DSG_last_segmentation_elapsed_s"] = max(
            0.0, time.perf_counter() - started
        ) if started > 0.0 else 0.0
        context.scene["DSG_last_segmentation_finished_at"] = float(time.time())
        context.scene["DSG_last_segmentation_success"] = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _ASYNC_SEGMENTATION.update(
        active=False, phase="", builder=None,
        postprocess_started=False, postprocess_result=None, prepared_surfaces=None,
        canal_verifier_mask=None, canal_verifier_origin=None,
        canal_verifier_stats=None,
        bone_semantic_mask=None, bone_semantic_origin=None,
        maxilla_semantic_mask=None, maxilla_semantic_origin=None,
        mandible_semantic_mask=None, mandible_semantic_origin=None,
        tooth_verifier_upper_mask=None, tooth_verifier_upper_origin=None,
        tooth_verifier_lower_mask=None, tooth_verifier_lower_origin=None,
        tooth_path_stats=None, universal_roi_slices_full=None, universal_roi_info=None,
        bone_build_step="", bone_obj_name="", maxilla_obj_name="", mandible_obj_name="",
        canal_obj_name="", canal_summary=None,
        progress=0.0, progress_phase="", progress_detail="",
        last_message=str(message),
    )
    _end_segmentation_progress(context, success=False)

    # A DICOM AI transaction is allowed to fail at any timer phase. Restore the
    # checkpoint captured before launching it so a failure never strands the
    # workflow on a half-created scene or on a dead SEGMENTING screen.
    restored = False
    try:
        restored = bool(core.restore_dicom_route_checkpoint(context))
    except Exception as rollback_exc:
        print(f"[DSG CBCT AI] checkpoint rollback warning: {rollback_exc}")
    if restored:
        try:
            context.scene.dicom_wizard_pro.status = f"Error: {message}"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    _restore_ai_performance_session(context)
    print(f"[DSG CBCT AI] {message}")


def cancel_semantic_workflow(context, message: str = "Segmentación cancelada") -> bool:
    """Cancel the active asynchronous CBCT transaction and roll it back safely."""
    if not bool(_ASYNC_SEGMENTATION.get("active")):
        return False
    _abort_async_segmentation(context, str(message or "Segmentación cancelada"))
    try:
        context.scene.dicom_wizard_pro.status = "Segmentación cancelada · estado anterior restaurado"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _start_universal_full_job_after_verifier(props) -> bool:
    """Start UniversalLab on the proven in-process background worker.

    This bypasses persistent servers, second Blender processes and dual-worker
    orchestration until segmentation is clinically stable again.
    """
    from . import cbct_ai_runtime
    started = cbct_ai_runtime._start_prediction_job_inprocess(
        RUNTIME.volume, RUNTIME.slopes, RUNTIME.intercepts,
        RUNTIME.spacing_zyx_mm, RUNTIME.dims_zyx,
        kind="universal",
        source_signature=_semantic_source_signature(),
        device_preference=str(getattr(props, "ai_device_preference", "AUTO")),
        orientation_xyz=RUNTIME.orientation_xyz,
        image_origin_patient=RUNTIME.image_origin_patient,
        preferred_roi_slices_full=_ASYNC_SEGMENTATION.get("universal_roi_slices_full"),
    )
    if started:
        _ASYNC_SEGMENTATION["phase"] = "AI"
        _ASYNC_SEGMENTATION["kind"] = "universal"
        _ASYNC_SEGMENTATION["last_message"] = ""
        props.status = "UniversalLab · segmentando dientes, huesos y canal…"
    return bool(started)



def _poll_async_segmentation():
    if not bool(_ASYNC_SEGMENTATION.get("active")):
        return None
    context = bpy.context
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "dicom_wizard_pro"):
        _ASYNC_SEGMENTATION.update(
            active=False, phase="", builder=None,
            progress=0.0, progress_phase="", progress_detail="",
        )
        _end_segmentation_progress(context, success=False)
        _restore_ai_performance_session(context)
        return None
    props = scene.dicom_wizard_pro
    phase = str(_ASYNC_SEGMENTATION.get("phase", "AI"))

    try:
        if phase == "PIPELINE_EXTERNAL":
            from . import cbct_pipeline_client
            state = cbct_pipeline_client.state()
            factor = max(0.02, min(0.94, float(state.get("factor", 0.02) or 0.02)))
            message = str(state.get("message") or "Pipeline externo…")
            props.status = message
            _set_segmentation_progress(context, factor, str(state.get("phase") or "Pipeline externo"), message)
            if bool(state.get("running")):
                return 0.10
            error = str(state.get("error") or "")
            if error:
                raise RuntimeError(error)
            manifest = cbct_pipeline_client.consume_manifest()
            if manifest is None:
                return 0.10
            if str(manifest.get("source_signature") or "") != _semantic_source_signature():
                raise RuntimeError("El CBCT cambió durante el pipeline externo")
            route_mode = str(manifest.get("route_mode") or _ASYNC_SEGMENTATION.get("route_mode") or "FULL").upper()
            if route_mode == "SIMPLE_ARCHES":
                prepared = dict(manifest.get("prepared_surfaces") or {})
                upper, lower, composite = build_simple_arch_pair(context, prepared)
                RUNTIME.pipeline_result_dir = str(cbct_pipeline_client.artifact_dir() or "")
                scene["DSG_pipeline_timings_json"] = json.dumps(manifest.get("timings") or {}, ensure_ascii=False, default=str)
                scene["DSG_pipeline_execution"] = "TOTALSEGMENTATOR_SIMPLE_ARCHES"
                scene["DSG_cbct_segmentation_engine"] = "TotalSegmentator"
                scene["DSG_cbct_segmentation_mode"] = "SIMPLE_TWO_ARCHES"
                scene["DSG_simple_upper_object"] = upper.name
                scene["DSG_simple_lower_object"] = lower.name
                scene["DSG_simple_alignment_object"] = composite.name
                props.generated_surface_name = upper.name
                props.surface_ready = True
                props.segmentation_ready = True
                detail = f"2 arcadas · {len(upper.data.polygons)+len(lower.data.polygons):,} caras"
                _finish_async_segmentation(context, upper, detail=detail, elapsed=time.perf_counter()-float(_ASYNC_SEGMENTATION.get("started", time.perf_counter())))
                return None

            np = load_numpy()
            labels_path = str(manifest.get("universal_labels_path") or "")
            labels = np.load(labels_path, mmap_mode="r")
            if tuple(labels.shape) != tuple(RUNTIME.dims_zyx):
                raise RuntimeError("TotalSegmentator devolvió dimensiones incompatibles")
            # Keep the TotalSegmentator compatibility labelmap memory-mapped. No full-volume
            # copy is made on Blender's main thread.
            RUNTIME.semantic_labels = labels
            RUNTIME.pipeline_result_dir = str(cbct_pipeline_client.artifact_dir() or "")
            RUNTIME.semantic_source_signature = str(manifest.get("source_signature") or "")
            RUNTIME.semantic_model_kind = "universal"
            RUNTIME.semantic_model_metadata = dict(manifest.get("universal_metadata") or {})
            RUNTIME.semantic_crop_info = dict(manifest.get("universal_crop_info") or {})
            path_stats = dict(manifest.get("path_stats") or {})
            scene["DSG_tooth_path_reconciliation_json"] = json.dumps(path_stats, ensure_ascii=False)
            scene["DSG_tooth_path_reconciliation_corrected"] = bool(path_stats.get("corrected", False))
            scene["DSG_pipeline_timings_json"] = json.dumps(manifest.get("timings") or {}, ensure_ascii=False, default=str)
            scene["DSG_pipeline_worker_failures_json"] = json.dumps(manifest.get("worker_failures_recovered") or {}, ensure_ascii=False)
            scene["DSG_pipeline_execution"] = "TOTALSEGMENTATOR_EXTERNAL_GPU_PLUS_CPU_MESH_WORKERS"
            scene["DSG_cbct_segmentation_engine"] = "TotalSegmentator"
            scene["DSG_cbct_totalseg_task"] = str(manifest.get("totalseg_task") or "teeth")
            prepared_meshes = dict(manifest.get("prepared_meshes") or {})
            _ASYNC_SEGMENTATION["prepared_surfaces"] = dict(manifest.get("prepared_surfaces") or {})
            _ASYNC_SEGMENTATION["tooth_path_stats"] = path_stats
            from . import totalseg_runtime
            totalseg_runtime._prepend_paths()
            from . import cbct_dental_module
            _ASYNC_SEGMENTATION["builder"] = cbct_dental_module.iter_build_universal_dentition(
                context, labels, run_mirroring_check=False, prepared_meshes=prepared_meshes
            )
            _ASYNC_SEGMENTATION["phase"] = "BUILD_TEETH"
            props.status = "TotalSegmentator listo · importando dientes FDI…"
            _set_segmentation_progress(context, 0.945, "Importando geometría", props.status)
            return 0.01

        if phase == "AI_CANAL_VERIFIER":
            from . import cbct_ai_runtime
            job = cbct_ai_runtime.prediction_job_state()
            message = str(job.get("message") or "Verificando canal y soporte dental…")
            factor, phase_label = _segmentation_progress_from_ai_message(
                message, verifier=True
            )
            _set_segmentation_progress(
                context, factor, phase_label,
                "Anatomía · DentalSegmentator · " + message,
            )
            if message != _ASYNC_SEGMENTATION.get("last_message"):
                props.status = "Anatomía · DentalSegmentator · " + message
                _ASYNC_SEGMENTATION["last_message"] = message
            if bool(job.get("running")):
                return 0.10
            error = str(job.get("error") or "")
            if error:
                # HYBRID policy: TEETH/ALL are genuinely two-engine routes.
                # Never silently degrade to UniversalLab-only, because that
                # would break the user's explicit clinical routing contract.
                _abort_async_segmentation(
                    context,
                    "DentalSegmentator falló en una ruta que exige los dos motores: " + error,
                )
                return None
            result = cbct_ai_runtime.consume_prediction_result()
            if result is None:
                return 0.10
            signature = str(result.get("source_signature", ""))
            if signature != _semantic_source_signature():
                raise RuntimeError("El CBCT cambió durante la verificación del canal")
            if str(result.get("kind", "")).lower() != "semantic":
                raise RuntimeError("El verificador del canal devolvió un modelo inesperado")

            labels_sem = result.get("labels")
            try:
                roi_slices, roi_info = cbct_ai_runtime._dental_roi_from_semantic(
                    labels_sem, RUNTIME.spacing_zyx_mm, margin_mm=28.0
                )
                _ASYNC_SEGMENTATION["universal_roi_slices_full"] = roi_slices
                _ASYNC_SEGMENTATION["universal_roi_info"] = dict(roi_info or {})
            except Exception as roi_exc:
                _ASYNC_SEGMENTATION["universal_roi_slices_full"] = None
                _ASYNC_SEGMENTATION["universal_roi_info"] = {"valid": False, "error": str(roi_exc)}
            verifier_mask, verifier_origin = _compact_mask_for_classes(labels_sem, (5,))
            bone_semantic_mask, bone_semantic_origin = _compact_mask_for_classes(labels_sem, (1, 2))
            maxilla_semantic_mask, maxilla_semantic_origin = _compact_mask_for_classes(labels_sem, (1,))
            mandible_semantic_mask, mandible_semantic_origin = _compact_mask_for_classes(labels_sem, (2,))
            upper_teeth_mask, upper_teeth_origin = _compact_mask_for_classes(labels_sem, (3,))
            lower_teeth_mask, lower_teeth_origin = _compact_mask_for_classes(labels_sem, (4,))
            _ASYNC_SEGMENTATION["canal_verifier_mask"] = verifier_mask
            _ASYNC_SEGMENTATION["bone_semantic_mask"] = bone_semantic_mask
            _ASYNC_SEGMENTATION["bone_semantic_origin"] = tuple(int(v) for v in bone_semantic_origin)
            _ASYNC_SEGMENTATION["maxilla_semantic_mask"] = maxilla_semantic_mask
            _ASYNC_SEGMENTATION["maxilla_semantic_origin"] = tuple(int(v) for v in maxilla_semantic_origin)
            _ASYNC_SEGMENTATION["mandible_semantic_mask"] = mandible_semantic_mask
            _ASYNC_SEGMENTATION["mandible_semantic_origin"] = tuple(int(v) for v in mandible_semantic_origin)
            _ASYNC_SEGMENTATION["canal_verifier_origin"] = tuple(int(v) for v in verifier_origin)
            _ASYNC_SEGMENTATION["tooth_verifier_upper_mask"] = upper_teeth_mask
            _ASYNC_SEGMENTATION["tooth_verifier_upper_origin"] = tuple(int(v) for v in upper_teeth_origin)
            _ASYNC_SEGMENTATION["tooth_verifier_lower_mask"] = lower_teeth_mask
            _ASYNC_SEGMENTATION["tooth_verifier_lower_origin"] = tuple(int(v) for v in lower_teeth_origin)
            _ASYNC_SEGMENTATION["canal_verifier_stats"] = {
                "model": "DentalSegmentator",
                "semantic_class": 5,
                "voxels": int(verifier_mask.sum()) if verifier_mask is not None else 0,
                "bone_voxels": int(bone_semantic_mask.sum()) if bone_semantic_mask is not None else 0,
                "maxilla_voxels": int(maxilla_semantic_mask.sum()) if maxilla_semantic_mask is not None else 0,
                "mandible_voxels": int(mandible_semantic_mask.sum()) if mandible_semantic_mask is not None else 0,
                "upper_teeth_voxels": int(upper_teeth_mask.sum()) if upper_teeth_mask is not None else 0,
                "lower_teeth_voxels": int(lower_teeth_mask.sum()) if lower_teeth_mask is not None else 0,
                "source_signature": signature,
            }
            # Release the full verifier labelmap before UniversalLab inference.
            del labels_sem
            del result

            props.status = "Soporte dental y canal verificados · iniciando UniversalLab…"
            _set_segmentation_progress(
                context, 0.20, "Preparando UniversalLab", props.status
            )
            if not _start_universal_full_job_after_verifier(props):
                raise RuntimeError("No se pudo iniciar UniversalLab después del verificador del canal")
            return 0.10

        if phase == "AI":
            from . import cbct_ai_runtime
            job = cbct_ai_runtime.prediction_job_state()
            message = str(job.get("message") or "Segmentando CBCT en segundo plano…")
            factor, phase_label = _segmentation_progress_from_ai_message(
                message, verifier=False
            )
            _set_segmentation_progress(context, factor, phase_label, message)
            if message != _ASYNC_SEGMENTATION.get("last_message"):
                props.status = message
                _ASYNC_SEGMENTATION["last_message"] = message
            if bool(job.get("running")):
                return 0.10
            error = str(job.get("error") or "")
            if error:
                _abort_async_segmentation(context, error)
                return None
            result = cbct_ai_runtime.consume_prediction_result()
            if result is None:
                return 0.10

            kind = str(result.get("kind", "")).lower()
            structure = str(_ASYNC_SEGMENTATION.get("structure", "")).upper()

            # 9.2.15: the 70-72% freeze was here. Competitive Tooth Path ran
            # many 3-D EDT/watershed operations directly inside this Blender timer.
            # Start pure numerical reconciliation + tooth mesh preparation outside
            # the datablock commit path, then keep this timer limited to UI polling.
            if kind == "universal" and structure in {"TEETH", "ALL"}:
                if not _start_universal_postprocess_job(result):
                    raise RuntimeError("Ya hay un postproceso dental en curso")
                _ASYNC_SEGMENTATION["phase"] = "POSTPROCESS_TEETH"
                _ASYNC_SEGMENTATION["postprocess_started"] = True
                props.status = "IA terminada · reconciliando dientes sin bloquear Blender…"
                _set_segmentation_progress(context, 0.705, "Postprocesando dientes", props.status)
                return 0.08

            labels = _cache_async_semantic_result(result)

            # UniversalLab dentition is built directly from its integer labelmap.
            # Do NOT route the new ALL workflow through the legacy BONE/TEETH mask
            # state before tooth creation. BUILD_BONE prepares its own 53/54 mask.
            if kind == "universal" and structure in {"TEETH", "ALL"}:
                from . import cbct_dental_module
                _ASYNC_SEGMENTATION["builder"] = cbct_dental_module.iter_build_universal_dentition(
                    context, labels, run_mirroring_check=True
                )
                _ASYNC_SEGMENTATION["phase"] = "BUILD_TEETH"
                props.status = (
                    "IA terminada · creando dientes + FDI 1 a 1…"
                    if structure == "ALL"
                    else "IA terminada · creando dientes 1 a 1…"
                )
                _set_segmentation_progress(
                    context, 0.72, "Reconstruyendo dientes", props.status
                )
                return 0.01

            # Other semantic surfaces still use the legacy active-mask state.
            segment_tissue_semantically(
                context,
                str(_ASYNC_SEGMENTATION.get("structure") or props.segmentation_structure),
            )
            props.status = "IA terminada · creando superficie…"
            obj = generate_segmentation_surface(context)
            detail = f"{len(obj.data.polygons):,} caras"
            _finish_async_segmentation(
                context, obj, detail=detail,
                elapsed=time.perf_counter() - float(_ASYNC_SEGMENTATION.get("started", time.perf_counter())),
            )
            return None

        if phase == "POSTPROCESS_TEETH":
            state = _postprocess_job_state()
            message = str(state.get("message") or "Reconciliando dientes…")
            props.status = message
            _set_segmentation_progress(context, 0.71, "Workers múltiples · postproceso", message)
            if bool(state.get("running")):
                return 0.08
            error = str(state.get("error") or "")
            if error:
                # Preserve the trained UniversalLab result if optional reconciliation
                # fails, but do not hide the reason. Mesh preparation then falls back
                # to the existing incremental builder on the main thread.
                payload = _consume_universal_postprocess_result()  # raises with exact error
                return 0.08
            payload = _consume_universal_postprocess_result()
            if payload is None:
                return 0.08
            result = payload.get("result") or {}
            path_stats = dict(payload.get("path_stats") or {})
            prepared_meshes = payload.get("prepared_meshes") or {}
            _ASYNC_SEGMENTATION["prepared_surfaces"] = payload.get("prepared_surfaces") or {}
            _ASYNC_SEGMENTATION["tooth_path_stats"] = path_stats
            scene["DSG_tooth_path_reconciliation_json"] = json.dumps(path_stats, ensure_ascii=False)
            scene["DSG_tooth_path_reconciliation_corrected"] = bool(path_stats.get("corrected", False))
            scene["DSG_tooth_postprocess_worker_s"] = float(payload.get("elapsed_s", 0.0) or 0.0)
            labels = _cache_async_semantic_result(result)
            from . import cbct_dental_module
            _ASYNC_SEGMENTATION["builder"] = cbct_dental_module.iter_build_universal_dentition(
                context, labels, run_mirroring_check=True, prepared_meshes=prepared_meshes
            )
            _ASYNC_SEGMENTATION["phase"] = "BUILD_TEETH"
            props.status = "Postproceso listo · insertando dientes preparados…"
            _set_segmentation_progress(context, 0.72, "Insertando dientes", props.status)
            return 0.01

        if phase == "BUILD_TEETH":
            builder = _ASYNC_SEGMENTATION.get("builder")
            if builder is None:
                raise RuntimeError("Se perdió el generador incremental de dientes")
            try:
                update = next(builder)
                index = int(update.get("index", 0)); total = int(update.get("total", 0))
                fdi = update.get("fdi")
                if fdi:
                    props.status = f"Insertando diente preparado · {index}/{total} · FDI {int(fdi)}"
                else:
                    props.status = f"Insertando diente preparado · {index}/{total}"
                fraction = float(index) / float(max(total, 1))
                _set_segmentation_progress(
                    context,
                    0.72 + 0.18 * max(0.0, min(1.0, fraction)),
                    "Reconstruyendo dientes",
                    props.status,
                )
                return 0.02
            except StopIteration as finished:
                summary = finished.value or {}
                tooth_count = int(summary.get("tooth_count", 0))
                faces = int(summary.get("total_faces", 0))
                mesh_s = float(summary.get("mesh_build_s", 0.0) or 0.0)
                detail = f"{tooth_count} dientes · {faces:,} caras"
                if mesh_s > 0.0:
                    detail += f" · mallas {mesh_s:.1f}s"

                if str(_ASYNC_SEGMENTATION.get("structure", "")).upper() == "ALL":
                    _ASYNC_SEGMENTATION["tooth_summary"] = dict(summary)
                    _ASYNC_SEGMENTATION["phase"] = "BUILD_BONE"
                    _ASYNC_SEGMENTATION["bone_build_step"] = "MAXILLA"
                    _ASYNC_SEGMENTATION["builder"] = None
                    props.status = "Dientes + FDI listos · creando maxila/mandíbula…"
                    _set_segmentation_progress(
                        context, 0.92, "Creando maxila y mandíbula", props.status
                    )
                    return 0.01

                # Legacy/internal TEETH-only route still needs a target because
                # it terminates directly on dental geometry.
                from . import cbct_dental_module
                obj = cbct_dental_module.ensure_segmented_alignment_composite(context)
                _finish_async_segmentation(
                    context, obj, detail=detail,
                    elapsed=time.perf_counter() - float(_ASYNC_SEGMENTATION.get("started", time.perf_counter())),
                )
                return None

        if phase == "BUILD_BONE":
            # 9.2.16: materialise maxilla/mandible/canal over separate timer ticks; no duplicate combined jaw.
            # 9.2.13 built combined bone + maxilla + mandible + canal in one
            # callback, and its new anatomy refinement made that callback long
            # enough to starve Blender's event loop. Each tick now owns exactly
            # one heavyweight mesh operation and returns control immediately.
            labels = get_cached_semantic_cbct_labels(
                model_kind="universal", require_current_source=True
            )
            if labels is None:
                raise RuntimeError("Se perdió el labelmap UniversalLab antes de crear el canal")

            build_step = str(_ASYNC_SEGMENTATION.get("bone_build_step") or "MAXILLA")

            if build_step == "BONE_MAIN":
                # 9.2.16: immediate segmentation has exactly TWO jaw meshes.
                # Maxilla and mandible already carry ROLE_DICOM_BONE, so the old
                # combined Dental_DICOM_Bone duplicated both jaws visually and
                # consumed memory/mesh-build time without adding clinical data.
                old = bpy.data.objects.get(NAME_DICOM_BONE)
                if old is not None:
                    old_mesh = old.data if old.type == "MESH" else None
                    bpy.data.objects.remove(old, do_unlink=True)
                    if old_mesh is not None and old_mesh.users == 0:
                        bpy.data.meshes.remove(old_mesh)
                _ASYNC_SEGMENTATION["bone_obj_name"] = ""
                _ASYNC_SEGMENTATION["bone_build_step"] = "MAXILLA"
                props.status = "Creando maxila…"
                _set_segmentation_progress(context, 0.93, "Creando maxila", props.status)
                return 0.01

            if build_step == "MAXILLA":
                stale_bone = bpy.data.objects.get(NAME_DICOM_BONE)
                if stale_bone is not None:
                    stale_mesh = stale_bone.data if stale_bone.type == "MESH" else None
                    bpy.data.objects.remove(stale_bone, do_unlink=True)
                    if stale_mesh is not None and stale_mesh.users == 0:
                        bpy.data.meshes.remove(stale_mesh)
                ul_mask, ul_origin = _compact_mask_for_classes(labels, (54,))
                maxilla_mask = ul_mask
                maxilla_origin = ul_origin
                maxilla_class = 54
                maxilla_source = "TOTALSEGMENTATOR"
                if maxilla_mask is None or not bool(getattr(maxilla_mask, "any", lambda: False)()):
                    maxilla_mask = _ASYNC_SEGMENTATION.get("maxilla_semantic_mask")
                    maxilla_origin = _ASYNC_SEGMENTATION.get("maxilla_semantic_origin")
                    maxilla_class = 1
                    maxilla_source = "TOTALSEGMENTATOR"
                prepared_surfaces = _ASYNC_SEGMENTATION.get("prepared_surfaces") or {}
                max_prepared = prepared_surfaces.pop("maxilla", None)
                if isinstance(prepared_surfaces, dict) and prepared_surfaces.get("maxilla_class") is not None:
                    maxilla_class = int(prepared_surfaces.get("maxilla_class"))
                    maxilla_source = str(prepared_surfaces.get("maxilla_source") or maxilla_source)
                maxilla_obj = build_semantic_arch_surface(
                    context, maxilla_mask, maxilla_origin,
                    object_name=NAME_DICOM_MAXILLA, arch="MAXILLA",
                    semantic_class=maxilla_class, source_engine=maxilla_source, prepared=max_prepared,
                )
                scene["DSG_maxilla_object"] = maxilla_obj.name
                scene["DSG_maxilla_engine"] = maxilla_source
                scene["DSG_cbct_segmentation_mode"] = "TOTALSEGMENTATOR_TEETH"
                scene["DSG_cbct_segmentation_skipped"] = False
                scene["DSG_cbct_bone_engine"] = "TotalSegmentator_teeth_jawbones"
                scene["DSG_cbct_tooth_engine"] = "TotalSegmentator_ToothFairy3_FDI"
                scene["DSG_alignment_reference_pending"] = True
                scene["DSG_alignment_reference_status"] = "NOT_BUILT_YET"
                _ASYNC_SEGMENTATION["maxilla_obj_name"] = maxilla_obj.name
                _ASYNC_SEGMENTATION["bone_build_step"] = "MANDIBLE"
                props.status = "Maxila lista · creando mandíbula…"
                _set_segmentation_progress(context, 0.945, "Creando mandíbula", props.status)
                return 0.02

            if build_step == "MANDIBLE":
                ul_mask, ul_origin = _compact_mask_for_classes(labels, (53,))
                mandible_mask = ul_mask
                mandible_origin = ul_origin
                mandible_class = 53
                mandible_source = "TOTALSEGMENTATOR"
                if mandible_mask is None or not bool(getattr(mandible_mask, "any", lambda: False)()):
                    mandible_mask = _ASYNC_SEGMENTATION.get("mandible_semantic_mask")
                    mandible_origin = _ASYNC_SEGMENTATION.get("mandible_semantic_origin")
                    mandible_class = 2
                    mandible_source = "TOTALSEGMENTATOR"
                prepared_surfaces = _ASYNC_SEGMENTATION.get("prepared_surfaces") or {}
                man_prepared = prepared_surfaces.pop("mandible", None)
                if isinstance(prepared_surfaces, dict) and prepared_surfaces.get("mandible_class") is not None:
                    mandible_class = int(prepared_surfaces.get("mandible_class"))
                    mandible_source = str(prepared_surfaces.get("mandible_source") or mandible_source)
                mandible_obj = build_semantic_arch_surface(
                    context, mandible_mask, mandible_origin,
                    object_name=NAME_DICOM_MANDIBLE, arch="MANDIBLE",
                    semantic_class=mandible_class, source_engine=mandible_source, prepared=man_prepared,
                )
                scene["DSG_mandible_object"] = mandible_obj.name
                scene["DSG_mandible_engine"] = mandible_source
                _ASYNC_SEGMENTATION["mandible_obj_name"] = mandible_obj.name
                _ASYNC_SEGMENTATION["bone_build_step"] = "CANAL"
                props.status = "Maxila/mandíbula listas · creando canal mandibular…"
                _set_segmentation_progress(context, 0.965, "Creando canal mandibular", props.status)
                return 0.02

            if build_step == "CANAL":
                try:
                    prepared_surfaces = _ASYNC_SEGMENTATION.get("prepared_surfaces") or {}
                    canal_obj, canal_summary = build_mandibular_canal_surface(
                        context,
                        labels,
                        verifier_mask=_ASYNC_SEGMENTATION.get("canal_verifier_mask"),
                        verifier_origin=_ASYNC_SEGMENTATION.get("canal_verifier_origin"),
                        verifier_stats=_ASYNC_SEGMENTATION.get("canal_verifier_stats"),
                        prepared=prepared_surfaces.pop("canal", None),
                    )
                except Exception as canal_exc:
                    canal_obj = None
                    canal_summary = {
                        "status": "ERROR",
                        "error": f"{type(canal_exc).__name__}: {canal_exc}",
                        "faces": 0,
                    }
                    scene["DSG_mandibular_canal_status"] = "ERROR"
                    scene["DSG_mandibular_canal_error"] = str(canal_summary["error"])
                    print("[DSG CANAL] " + str(canal_summary["error"]))
                mandible_obj = bpy.data.objects.get(str(_ASYNC_SEGMENTATION.get("mandible_obj_name") or ""))
                if mandible_obj is None:
                    raise RuntimeError("Se perdió la mandíbula durante la construcción escalonada")
                mandible_obj["DSG_mandibular_canal_status"] = str(canal_summary.get("status", "UNKNOWN"))
                if canal_obj is not None:
                    mandible_obj["DSG_mandibular_canal_object"] = canal_obj.name
                    _ASYNC_SEGMENTATION["canal_obj_name"] = canal_obj.name
                _ASYNC_SEGMENTATION["canal_summary"] = dict(canal_summary)
                _ASYNC_SEGMENTATION["bone_build_step"] = "FINALIZE"
                props.status = "Canal listo · finalizando segmentación…"
                _set_segmentation_progress(context, 0.985, "Finalizando segmentación", props.status)
                return 0.02

            if build_step == "FINALIZE":
                maxilla_obj = bpy.data.objects.get(str(_ASYNC_SEGMENTATION.get("maxilla_obj_name") or ""))
                mandible_obj = bpy.data.objects.get(str(_ASYNC_SEGMENTATION.get("mandible_obj_name") or ""))
                if maxilla_obj is None or mandible_obj is None:
                    raise RuntimeError("Faltan maxila o mandíbula al finalizar la segmentación")
                canal_summary = dict(_ASYNC_SEGMENTATION.get("canal_summary") or {"status": "UNKNOWN"})

                props.segmentation_structure = "BONE_ONLY"
                props.generated_surface_name = maxilla_obj.name
                props.surface_ready = True

                summary = dict(_ASYNC_SEGMENTATION.get("tooth_summary") or {})
                tooth_count = int(summary.get("tooth_count", 0))
                dental_faces = int(summary.get("total_faces", 0))
                detail = (
                    f"{tooth_count} dientes + FDI · maxila/mandíbula · "
                    f"{len(maxilla_obj.data.polygons) + len(mandible_obj.data.polygons):,} caras hueso"
                )
                canal_status = str(canal_summary.get("status", "UNKNOWN"))
                if canal_status == "SEGMENTED":
                    detail += f" · canal mandibular {int(canal_summary.get('faces', 0)):,} caras"
                else:
                    detail += f" · canal mandibular {canal_status}"
                if dental_faces:
                    detail += f" · {dental_faces:,} caras dentales"
                refined_objects = [
                    obj for obj in (maxilla_obj, mandible_obj)
                    if str(obj.get("DSG_anatomy_refine_status", "")) == "OK"
                ]
                if refined_objects:
                    detail += " · anatomía CBCT refinada"
                    scene["DSG_anatomy_refinement"] = "CBCT_CONSTRAINED_FAST_V2"
                    scene["DSG_anatomy_refinement_objects"] = int(len(refined_objects))
                _set_segmentation_progress(context, 0.995, "Finalizando segmentación", detail)
                _finish_async_segmentation(
                    context, maxilla_obj, detail=detail,
                    elapsed=time.perf_counter() - float(_ASYNC_SEGMENTATION.get("started", time.perf_counter())),
                )
                return None

            raise RuntimeError(f"Paso de construcción ósea desconocido: {build_step}")

    except Exception as exc:
        _abort_async_segmentation(context, f"{type(exc).__name__}: {exc}")
        return None
    return 0.10


def _start_async_full_segmentation(context, structure: str = "ALL", route_mode: str = "FULL") -> bool:
    """DSG 9.5: one TotalSegmentator task=teeth inference in an isolated worker."""
    from . import totalseg_runtime, cbct_pipeline_client
    props = context.scene.dicom_wizard_pro
    structure = str(structure or "ALL").upper()
    route_mode = str(route_mode or "FULL").upper()
    if route_mode not in {"FULL", "SIMPLE_ARCHES"}:
        raise ValueError(f"Modo de segmentación desconocido: {route_mode}")
    if structure not in {"ALL", "TEETH"}:
        raise ValueError("El flujo TotalSegmentator sólo admite ALL o TEETH")
    if semantic_workflow_busy():
        return False
    status = totalseg_runtime.quick_status()
    if not status.dependencies_ready:
        raise RuntimeError("TotalSegmentator no está instalado. Pulsa «INSTALAR MOTORES».")
    if not status.model_ready:
        raise RuntimeError("Faltan los modelos TotalSegmentator task=teeth (Tasks 115/113). Pulsa «INSTALAR MOTORES».")
    totalseg_runtime._prepend_paths()
    required = [RUNTIME.pipeline_volume_path, RUNTIME.pipeline_slopes_path, RUNTIME.pipeline_intercepts_path]
    if not all(value and Path(value).is_file() for value in required):
        raise RuntimeError("Falta la memoria compartida del CBCT. Recarga el paciente con DSG 9.5.")
    signature = _semantic_source_signature()
    RUNTIME.semantic_labels = None
    try: gc.collect()
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    try: cbct_pipeline_client.cleanup_artifacts()
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    _begin_ai_performance_session(context)
    _begin_segmentation_progress(context, "Arrancando TotalSegmentator")
    started = cbct_pipeline_client.start_full_pipeline(
        volume_path=RUNTIME.pipeline_volume_path,
        slopes_path=RUNTIME.pipeline_slopes_path,
        intercepts_path=RUNTIME.pipeline_intercepts_path,
        dims_zyx=RUNTIME.dims_zyx,
        spacing_zyx=RUNTIME.spacing_zyx_mm,
        source_signature=signature,
        orientation_xyz=RUNTIME.orientation_xyz,
        image_origin_patient=RUNTIME.image_origin_patient,
        device_preference=str(getattr(props, "ai_device_preference", "AUTO")),
        totalseg_site_paths=totalseg_runtime.active_site_paths(),
        totalseg_home_dir=totalseg_runtime.totalseg_home(),
        totalseg_version=totalseg_runtime.TOTALSEG_VERSION,
        dicom_vendor_dir=VENDOR_DIR,
        route_mode=route_mode,
    )
    if not started:
        _end_segmentation_progress(context, success=False); _restore_ai_performance_session(context); return False
    _ASYNC_SEGMENTATION.update(
        active=True, phase="PIPELINE_EXTERNAL", structure=structure, kind="external", route_mode=route_mode,
        source_signature=signature, started=time.perf_counter(), builder=None,
        tooth_summary=None, prepared_surfaces=None, tooth_path_stats=None,
        bone_build_step="", bone_obj_name="", maxilla_obj_name="", mandible_obj_name="",
        canal_obj_name="", canal_summary=None, last_message="",
    )
    props.show_volume=False; props.show_planes=False; props.show_all_planes=False; props.show_box=False
    update_visibility(context)
    lifecycle.unregister_timer(_poll_async_segmentation)
    lifecycle.register_timer(_poll_async_segmentation, first_interval=0.05)
    props.status = ("TotalSegmentator · ruta simple · dos arcadas" if route_mode == "SIMPLE_ARCHES" else "TotalSegmentator · task=teeth · inferencia dental única")
    context.scene["DSG_cbct_requested_engine_route"] = ("TOTALSEGMENTATOR_SIMPLE_ARCHES" if route_mode == "SIMPLE_ARCHES" else "TOTALSEGMENTATOR_TEETH")
    _set_segmentation_progress(context,0.02,"TotalSegmentator",props.status)
    return True



def _start_async_semantic_segmentation(context) -> bool:
    from . import cbct_ai_runtime
    props = context.scene.dicom_wizard_pro
    if semantic_workflow_busy():
        return False
    kind = _semantic_model_kind_for_structure(props.segmentation_structure)
    signature = _semantic_source_signature()
    status = cbct_ai_runtime.quick_status()
    if not status.dependencies_ready:
        raise RuntimeError("Motor IA interno no instalado. Pulsa «INSTALAR MOTORES»")
    if kind == "universal" and not status.universal_model_ready:
        raise RuntimeError("Falta UniversalLab. Pulsa «INSTALAR MOTORES»")
    if kind == "semantic" and not status.semantic_model_ready:
        raise RuntimeError("Falta el checkpoint DentalSegmentator incluido con DSG")

    _begin_ai_performance_session(context)
    try:
        started = cbct_ai_runtime._start_prediction_job_inprocess(
            RUNTIME.volume, RUNTIME.slopes, RUNTIME.intercepts,
            RUNTIME.spacing_zyx_mm, RUNTIME.dims_zyx,
            kind=kind, source_signature=signature,
            device_preference=str(getattr(props, "ai_device_preference", "AUTO")),
            orientation_xyz=RUNTIME.orientation_xyz,
            image_origin_patient=RUNTIME.image_origin_patient,
        )
    except Exception:
        _restore_ai_performance_session(context)
        raise
    if not started:
        _restore_ai_performance_session(context)
        return False
    _ASYNC_SEGMENTATION.update(
        active=True, phase="AI", structure=str(props.segmentation_structure).upper(),
        kind=kind, source_signature=signature, started=time.perf_counter(),
        builder=None, last_message="",
    )
    lifecycle.unregister_timer(_poll_async_segmentation)
    lifecycle.register_timer(_poll_async_segmentation, first_interval=0.05)
    props.status = "Segmentación iniciada en segundo plano · puedes seguir usando Blender"
    force_ui_redraw()
    return True


class DICOMWIZARDPRO_OT_segment_semantic_structure(Operator):
    bl_idname = "dicom_wizard_pro.segment_semantic_structure"
    bl_label = "Segmentar estructura"
    bl_description = "Usa TotalSegmentator task=teeth para dientes FDI, maxila, mandíbula y canal"
    bl_options = {"REGISTER", "UNDO"}

    target: bpy.props.StringProperty(default="BONE")

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        target = str(self.target or "BONE").upper()
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
            self.report({"ERROR"}, "Implante inmediato usa SEGMENTAR PARA IMPLANTE INMEDIATO con TotalSegmentator")
            return {"CANCELLED"}
        if target not in {"BONE", "BONE_ONLY", "TEETH"}:
            self.report({"ERROR"}, f"Segmentación no soportada: {target}")
            return {"CANCELLED"}
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        try:
            props.segmentation_structure = target
            # TotalSegmentator is the only segmentation engine in DSG 9.5.
            # BONE/BONE_ONLY requests still use task=teeth because that model
            # supplies the jawbones and canal together with dental FDI.
            started = _start_async_full_segmentation(context, structure="TEETH" if target == "TEETH" else "ALL")
            context.scene["DSG_cbct_requested_engine_route"] = "TOTALSEGMENTATOR_TEETH"
            if not started:
                self.report({"WARNING"}, "Ya hay una segmentación CBCT en curso")
                return {"CANCELLED"}
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_segment_all(Operator):
    bl_idname = "dicom_wizard_pro.segment_all"
    bl_label = "Segmentar todo"
    bl_description = "TotalSegmentator task=teeth: ruta completa o dos arcadas simples"
    bl_options = {"REGISTER", "UNDO"}

    route_mode: bpy.props.StringProperty(default="FULL")

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        try:
            mode = str(self.route_mode or "FULL").upper()
            if not _start_async_full_segmentation(context, structure="ALL", route_mode=mode):
                self.report({"WARNING"}, "Ya hay una segmentación CBCT en curso")
                return {"CANCELLED"}
            context.scene["DSG_cbct_requested_engine_route"] = (
                "TOTALSEGMENTATOR_SIMPLE_ARCHES" if mode == "SIMPLE_ARCHES"
                else "TOTALSEGMENTATOR_TEETH"
            )
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_direct_dicom_to_surface(Operator):
    bl_idname = "dicom_wizard_pro.direct_dicom_to_surface"
    bl_label = "Segmentar DICOM"
    bl_options = {"REGISTER"}
    bl_description = (
        "Genera la máscara adaptativa del modo elegido y crea su malla con el motor DICOM integrado"
    )

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
            self.report({"ERROR"}, "Implante inmediato usa TotalSegmentator task=teeth")
            return {"CANCELLED"}
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        try:
            if not _start_async_full_segmentation(context, structure="ALL"):
                self.report({"WARNING"}, "Ya hay una segmentación CBCT en curso")
                return {"CANCELLED"}
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        # Crucial: return immediately. All heavy neural work runs on a worker
        # thread; bpy.app.timers commits results incrementally on the main thread.
        return {"FINISHED"}



def generate_native_alignment_reference(
    context,
    max_axis: int = 176,
    *,
    set_generated_surface: bool = False,
    labels_override=None,
) -> bpy.types.Object:
    """Return the best available IOS↔CBCT dental reference.

    Segmented tooth objects always use their exact native composite. The sampled
    labelmap shell below is retained only for legacy/degraded scenes without
    individual teeth.
    """
    try:
        from . import cbct_dental_module
        teeth = cbct_dental_module.dentition_objects(context)
    except Exception:
        teeth = []
    if teeth:
        try:
            return cbct_dental_module.ensure_segmented_alignment_composite(context)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo construir el target dental nativo: {exc}"
            ) from exc

    np = load_numpy()
    if np is None:
        raise RuntimeError("Esta versión de Blender no incluye NumPy")
    if not RUNTIME.is_loaded():
        raise RuntimeError("Carga primero un CBCT")
    props = context.scene.dicom_wizard_pro
    labels = labels_override if labels_override is not None else get_cached_semantic_cbct_labels(
        model_kind=RUNTIME.semantic_model_kind or None, require_current_source=True
    )
    if labels is None:
        raise RuntimeError("No hay etiquetas CBCT en memoria. Segmenta primero el CBCT.")
    kind = str(RUNTIME.semantic_model_kind or "semantic").lower()
    compact, origin_zyx = _semantic_compact_mask_for_structure(labels, "TEETH")
    if compact is None or int(compact.sum()) < 64:
        raise RuntimeError("La IA no encontró suficientes dientes para alinear")

    # Downsample only the occupied dental ROI. The previous full-FOV np.isin
    # allocated another boolean array the size of the CBCT merely to build a
    # lightweight ICP target. Original voxel coordinates are restored through
    # the compact-mask origin before mesh conversion.
    max_axis = max(96, int(max_axis))
    stride = max(1, int(math.ceil(max(compact.shape) / float(max_axis))))
    zlocal = _preview_axis_indices(compact.shape[0], stride)
    ylocal = _preview_axis_indices(compact.shape[1], stride)
    xlocal = _preview_axis_indices(compact.shape[2], stride)
    mask = np.ascontiguousarray(compact[np.ix_(zlocal, ylocal, xlocal)], dtype=bool)
    del compact
    zidx = zlocal.astype(np.float64) + float(origin_zyx[0])
    yidx = ylocal.astype(np.float64) + float(origin_zyx[1])
    xidx = xlocal.astype(np.float64) + float(origin_zyx[2])
    vertices_xyz, triangles, stats = _voxel_shell_from_sampled_mask(mask, zidx, yidx, xidx)
    if len(triangles) < 50:
        raise RuntimeError("La referencia dental CBCT quedó demasiado pequeña")

    root = get_root(get_collection())
    old = bpy.data.objects.get("Dental_DICOM_AlignmentRef")
    if old is not None:
        old_mesh = old.data if old.type == 'MESH' else None
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    obj = _new_surface_from_arrays(
        context, object_name="Dental_DICOM_AlignmentRef",
        vertices_xyz=vertices_xyz, faces=triangles, root=root,
    )
    if len(obj.data.materials) == 0:
        obj.data.materials.append(_surface_material("TEETH"))
    _set_suite_role(obj, ROLE_DICOM_TEETH, component="DICOM")
    obj["dental_suite_structure"] = "TEETH"
    obj["dental_suite_alignment_reference"] = True
    obj["dicom_semantic_classes"] = "1-52" if kind == "universal" else "3,4"
    obj["dicom_semantic_model_kind"] = kind
    obj["dicom_reference_stride"] = int(stride)
    obj["dicom_surface_method"] = "AI semantic teeth + lightweight DSG alignment shell"
    obj["dicom_reference_occupied_voxels"] = int(stats.get("occupied", int(mask.sum())))
    if set_generated_surface:
        props.generated_surface_name = obj.name
        props.surface_ready = True
        state = get_segmentation_state("TEETH")
        state["surface_name"] = obj.name
    props.surface_preview_status = f"Referencia dental IA · {len(triangles):,} caras"
    return obj


def generate_unsegmented_dicom_stl(context) -> bpy.types.Object:
    """Build a native DICOM threshold STL with no neural segmentation."""
    props = context.scene.dicom_wizard_pro
    if not RUNTIME.is_loaded():
        raise RuntimeError("Carga primero un CBCT")
    if not props.auto_thresholds_ready:
        analyze_automatic_tissue_thresholds(context)
    # SIMPLE route: the automatic tissue threshold is only the starting point.
    # The clinician-adjustable DENSITY/HU slider is the final SSOT used to
    # generate the native STL when the user presses CONFIRMAR.
    update_density_labels(props)
    threshold = float(getattr(props, "current_density_min", 0.0))
    if not math.isfinite(threshold):
        threshold = float(getattr(props, "auto_soft_bone_threshold", 0.0))
    if not math.isfinite(threshold):
        raise RuntimeError("El umbral DICOM/densidad no es válido")
    props.status = "Creando STL nativo full-resolution · motor acelerado…"
    force_ui_redraw()

    # v9.2.64: the threshold route never downsamples and never converts the
    # scalar CBCT into a binary preview mask. An exact min/max block hierarchy
    # prunes cells that cannot cross the threshold; CUDA Marching Cubes is used
    # when the installed DSG runtime exposes a suitable GPU, otherwise continuous
    # vtkFlyingEdges3D runs on active hierarchy chunks. Both interpolate directly
    # on the original calibrated scalar field.
    projection = {"projected": 0}
    new_engine_error = ""
    try:
        from . import cbct_native_threshold
        density = _native_density_fullres_cached()
        index = _native_threshold_index_cached(prefer_cuda=True)
        surface = cbct_native_threshold.extract_threshold_surface(
            density, threshold, index,
            vtk_module=load_vtk(),
            skimage_measure=load_skimage_measure(),
            prefer_gpu=True,
        )
        vertices_xyz = _global_voxel_to_centered_xyz(surface.vertices_zyx)
        faces = surface.faces
        stats = dict(surface.diagnostics or {})
        stats["backend"] = str(surface.engine)
        stats["native_resolution"] = True
        stats["surface_extract_s"] = float(surface.elapsed_s)
        stats["warmup_s"] = float(getattr(RUNTIME, "native_threshold_warmup_s", 0.0) or 0.0)
    except Exception as exc:
        new_engine_error = f"{type(exc).__name__}: {exc}"
        # Deterministic legacy recovery. Even an unsupported VTK/Torch runtime
        # must never prevent SIMPLE from producing a native-resolution STL.
        if load_skimage_measure() is not None:
            vertices_xyz, faces, stats = _marching_cubes_native_chunked(context, threshold, "BONE")
            try:
                vertices_xyz, projection = _project_vertices_to_native_threshold(
                    vertices_xyz, threshold, iterations=1
                )
            except Exception:
                projection = {"projected": 0}
        else:
            vertices_xyz, faces, stats = _native_threshold_voxel_shell_chunked(
                context, threshold, "BONE"
            )
            projection = {"projected": 0}
        stats = dict(stats or {})
        stats["native_turbo_fallback_reason"] = new_engine_error
    root = get_root(get_collection())
    obj = _new_surface_from_arrays(
        context, object_name=NAME_DICOM_COMBINED,
        vertices_xyz=vertices_xyz, faces=faces, root=root,
    )
    if len(obj.data.materials) == 0:
        obj.data.materials.append(_surface_material("BONE"))
    obj["dicom_parented_to_root"] = True
    obj["dicom_root_name"] = root.name
    obj["dicom_surface_engine"] = str(stats.get("backend", "DSG_NATIVE_DICOM_HD_THRESHOLD_NO_AI"))
    obj["dicom_density_low"] = threshold
    obj["dicom_native_resolution"] = bool(stats.get("native_resolution", False))
    obj["dicom_hd_slabs"] = int(stats.get("slabs", stats.get("processed_chunks", 0)) or 0)
    obj["dicom_threshold_projection_vertices"] = int(projection.get("projected", 0))
    obj["DSG_native_threshold_fullres"] = True
    obj["DSG_native_threshold_surface_extract_s"] = float(stats.get("surface_extract_s", 0.0) or 0.0)
    obj["DSG_native_threshold_active_blocks"] = int(stats.get("active_leaf_blocks", stats.get("active_parent_blocks", 0)) or 0)
    obj["DSG_native_threshold_gpu"] = bool("CUDA" in str(stats.get("backend", "")).upper())
    obj["DSG_native_threshold_fallback_reason"] = str(stats.get("native_turbo_fallback_reason", "") or "")
    obj["dental_suite_structure"] = "DICOM_STL_NO_AI"
    obj["dental_suite_alignment_reference"] = True
    obj["dental_suite_source_path"] = str(RUNTIME.source_path or "")
    obj["DSG_segmentation_skipped"] = True
    _set_suite_role(obj, ROLE_DICOM_BONE, component="DICOM")
    props.generated_surface_name = obj.name
    props.surface_ready = True
    props.surface_preview_status = f"STL DICOM sin IA · {len(faces):,} caras"
    context.scene["DSG_cbct_segmentation_mode"] = "DICOM_STL_NO_AI"
    context.scene["DSG_cbct_segmentation_skipped"] = True
    context.scene[SUITE_STAGE_KEY] = "DICOM"
    _apply_dicom_surface_transparency(context, props)
    return obj


class DICOMWIZARDPRO_OT_continue_with_dicom_stl(Operator):
    bl_idname = "dicom_wizard_pro.continue_with_dicom_stl"
    bl_label = "Continuar con STL DICOM"
    bl_description = "Omite IA, crea el STL radiográfico del CBCT y pasa a alineamiento"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
            self.report({"ERROR"}, "La ruta de implante inmediato no permite omitir la segmentación IA")
            return {"CANCELLED"}
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        if semantic_workflow_busy():
            self.report({"WARNING"}, "Hay una segmentación CBCT en curso")
            return {"CANCELLED"}
        try:
            previous_active = context.view_layer.objects.active
            surface = generate_unsegmented_dicom_stl(context)
            context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
            bpy.ops.object.select_all(action="DESELECT")
            surface.hide_set(False); surface.select_set(True); context.view_layer.objects.active = surface
            align_props = getattr(context.scene, "dicp_props", None)
            if align_props is not None:
                align_props.icp_target_obj = surface
                if previous_active is not None and previous_active != surface and previous_active.type == "MESH":
                    role = _suite_role(previous_active)
                    if role not in {ROLE_DICOM_TEETH, ROLE_DICOM_BONE, ROLE_DSG_GUIDE}:
                        align_props.icp_source_obj = previous_active
                        _set_suite_role(previous_active, ROLE_IOS_SCAN, component="ALIGNMENT")
            props.step = 5
            props.status = f"STL DICOM listo · {len(surface.data.polygons):,} caras · segmentación omitida"
            self.report({"INFO"}, props.status)
            return {"FINISHED"}
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class DICOMWIZARDPRO_OT_prepare_ai_alignment(Operator):
    bl_idname = "dicom_wizard_pro.prepare_ai_alignment"
    bl_label = "Crear referencia dental CBCT y continuar"
    bl_description = "Crea una referencia de dientes para el alineamiento DICOM↔IOS con el motor incluido"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if not RUNTIME.is_loaded():
            _dw_report(self, {"ERROR"}, props, "Load a CBCT first.", "Carga primero un CBCT.")
            return {"CANCELLED"}
        try:
            from . import cbct_dental_module
            if cbct_dental_module.dentition_objects(context):
                try:
                    preflight = cbct_dental_module.native_alignment_code_preflight()
                    if not bool(preflight.get("json_available", False)):
                        raise RuntimeError("preflight: json no disponible")
                    obj = cbct_dental_module.ensure_segmented_alignment_composite(context)
                    context.scene["DSG_alignment_reference_pending"] = False
                    context.scene["DSG_alignment_reference_status"] = "ALL_SEGMENTED_COMPOSITE_READY"
                    cbct_dental_module.set_segmented_sources_alignment_visibility(
                        context, False
                    )
                except Exception as exc:
                    context.scene["DSG_alignment_reference_pending"] = True
                    context.scene["DSG_alignment_reference_status"] = "ERROR"
                    raise RuntimeError(
                        "Los dientes segmentados se han conservado; falló solo "
                        f"la preparación del alineamiento nativo: {exc}"
                    ) from exc
            else:
                obj = generate_native_alignment_reference(
                    context, set_generated_surface=not bool(props.generated_surface_name)
                )
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        align_props = getattr(context.scene, "dicp_props", None)
        if align_props is not None:
            align_props.icp_target_obj = obj
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        props.status = f"Referencia dental CBCT lista · {len(obj.data.polygons):,} caras"
        self.report({"INFO"}, props.status)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_prepare_alignment(Operator):
    bl_idname = "dicom_wizard_pro.prepare_alignment"
    bl_label = "Continue to Alignment"
    bl_description = "Prepara una referencia dental común al CBCT y al IOS para el alineamiento"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        try:
            from . import cbct_dental_module
            dentition = cbct_dental_module.dentition_objects()
            if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
                if not dentition:
                    _dw_report(
                        self, {"ERROR"}, props,
                        "Immediate implant requires individual CBCT teeth + FDI.",
                        "Implante inmediato exige dientes CBCT individuales + FDI.")
                    return {"CANCELLED"}
                target_fdi = int(core.target_fdi(context.scene))
                target_found = False
                for tooth in dentition:
                    try:
                        if int(tooth.get("DSG_fdi_number", 0) or 0) == target_fdi:
                            target_found = True
                            break
                    except Exception:
                        continue
                if not target_found:
                    _dw_report(
                        self, {"ERROR"}, props,
                        f"Target FDI {target_fdi} is missing from the CBCT dentition.",
                        f"El FDI objetivo {target_fdi} no existe en la dentición CBCT.")
                    return {"CANCELLED"}
            if dentition and not bool(context.scene.get(cbct_dental_module.SCENE_ACCEPTED_KEY, False)):
                _dw_report(self, {"ERROR"}, props, "Confirm CBCT FDI before alignment.", "Confirma la dentición FDI del CBCT antes del alineamiento.")
                return {"CANCELLED"}
        except Exception as exc:
            if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
                _dw_report(self, {"ERROR"}, props, str(exc), f"No se pudo validar la ruta inmediata: {exc}")
                return {"CANCELLED"}
        surface = bpy.data.objects.get(props.generated_surface_name)
        if surface is None or surface.type != 'MESH':
            _dw_report(self, {"ERROR"}, props, "Create a segmentation first.", "Crea primero una segmentación.")
            return {"CANCELLED"}

        previous_active = context.view_layer.objects.active
        structure = str(surface.get("dental_suite_structure", "")).upper()
        try:
            from . import cbct_dental_module
            if cbct_dental_module.dentition_objects(context):
                try:
                    preflight = cbct_dental_module.native_alignment_code_preflight()
                    if not bool(preflight.get("json_available", False)):
                        raise RuntimeError("preflight: json no disponible")
                    target = cbct_dental_module.ensure_segmented_alignment_composite(context)
                    context.scene["DSG_alignment_reference_pending"] = False
                    context.scene["DSG_alignment_reference_status"] = "ALL_SEGMENTED_COMPOSITE_READY"
                    cbct_dental_module.set_segmented_sources_alignment_visibility(
                        context, False
                    )
                except Exception as exc:
                    context.scene["DSG_alignment_reference_pending"] = True
                    context.scene["DSG_alignment_reference_status"] = "ERROR"
                    raise RuntimeError(
                        "La segmentación está conservada. Falló únicamente la "
                        f"preparación del target nativo de alineamiento: {exc}"
                    ) from exc
            else:
                target = (
                    surface
                    if structure in {"TEETH", "DICOM_STL_NO_AI"}
                    else generate_native_alignment_reference(context)
                )
        except Exception as exc:
            props.status = f"Error preparando referencia dental: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        target["dental_suite_alignment_reference"] = True
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        bpy.ops.object.select_all(action='DESELECT')
        target.hide_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target

        align_props = getattr(context.scene, "dicp_props", None)
        if align_props is not None:
            align_props.icp_target_obj = target
            if previous_active is not None and previous_active != target and previous_active.type == 'MESH':
                role = _suite_role(previous_active)
                if role not in {ROLE_DICOM_TEETH, ROLE_DICOM_BONE, ROLE_DSG_GUIDE}:
                    align_props.icp_source_obj = previous_active
                    _set_suite_role(previous_active, ROLE_IOS_SCAN, component="ALIGNMENT")

        if target is surface:
            message_en = f"Reference prepared: {target.name}"
            message_es = f"Referencia preparada: {target.name}"
        else:
            quality = str(target.get("dental_suite_alignment_reference_quality", "") or "")
            if quality == "ALL_SEGMENTED_DUPLICATE_COMPOSITE":
                tri_count = int(target.get("DSG_alignment_total_face_count", len(target.data.polygons)))
                source_count = int(target.get("DSG_alignment_source_count", 0))
                message_en = f"Two-object alignment · CBCT composite {source_count} segments · {tri_count:,} triangles"
                message_es = f"Alineamiento de 2 objetos · compuesto CBCT {source_count} segmentos · {tri_count:,} triángulos"
            else:
                message_en = f"Dental alignment reference prepared; {surface.name} preserved"
                message_es = f"Referencia dental preparada; se conserva {surface.name}"
        _dw_report(self, {"INFO"}, props, message_en, message_es)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_export_surface_stl(Operator, ExportHelper):
    bl_idname = "dicom_wizard_pro.export_surface_stl"
    bl_label = "Exportar STL"
    bl_description = "Guarda la superficie seleccionada como archivo STL"

    filename_ext = ".stl"
    filter_glob: bpy.props.StringProperty(
        default="*.stl",
        options={"HIDDEN"},
    )

    def invoke(self, context, event):
        props = context.scene.dicom_wizard_pro
        state = get_segmentation_state(props.segmentation_structure)
        obj = bpy.data.objects.get(state.get("surface_name", ""))
        if obj is None:
            obj = bpy.data.objects.get(props.generated_surface_name)
        if obj is not None and not self.filepath:
            safe_name = "".join(
                character if character.isalnum() or character in "-_" else "_"
                for character in obj.name
            )
            self.filepath = safe_name + ".stl"
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        state = get_segmentation_state(props.segmentation_structure)
        obj = bpy.data.objects.get(state.get("surface_name", ""))
        if obj is None:
            obj = bpy.data.objects.get(props.generated_surface_name)
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "No existe una superficie para exportar")
            return {"CANCELLED"}

        previous_active = context.view_layer.objects.active
        previous_selection = list(context.selected_objects)
        try:
            for selected in list(context.selected_objects):
                selected.select_set(False)
            obj.hide_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.wm.stl_export(
                filepath=self.filepath,
                export_selected_objects=True,
                apply_modifiers=True,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo exportar STL: {exc}")
            return {"CANCELLED"}
        finally:
            try:
                obj.select_set(False)
                for selected in previous_selection:
                    if selected.name in bpy.data.objects:
                        selected.select_set(True)
                if previous_active is not None and previous_active.name in bpy.data.objects:
                    context.view_layer.objects.active = previous_active
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        props.status = f"STL exportado: {self.filepath}"
        self.report({"INFO"}, props.status)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_generate_surface(Operator):
    bl_idname = "dicom_wizard_pro.generate_surface"
    bl_label = "Generar superficie"
    bl_description = "Convierte la máscara 3D en una malla con el motor DICOM integrado"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        try:
            props.status = "Generando superficie…"
            obj = generate_segmentation_surface(context)
        except Exception as exc:
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        props.step = 4
        props.show_volume = True
        props.show_planes = False
        props.show_all_planes = False
        update_visibility(context)
        props.status = f"STL creado: {obj.name} · abre MPR para revisar"
        self.report({"INFO"}, props.status)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_select_surface(Operator):
    bl_idname = "dicom_wizard_pro.select_surface"
    bl_label = "Seleccionar superficie"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        state = get_segmentation_state(props.segmentation_structure)
        obj = bpy.data.objects.get(state.get("surface_name", ""))
        if obj is None:
            self.report({"ERROR"}, "No se encontró la superficie")
            return {"CANCELLED"}
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.hide_set(False); obj.select_set(True); context.view_layer.objects.active = obj
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_back_to_segmentation(Operator):
    bl_idname = "dicom_wizard_pro.back_to_segmentation"
    bl_label = "Volver a segmentación"

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        props.step = 3
        props.show_volume = True
        props.show_planes = False
        props.show_segmentation_overlay = False
        sync_segmentation_properties(props)
        refresh_volume_material(context)
        configure_clinical_preview_view(context, frame=True)
        schedule_surface_preview(context, immediate=True)
        update_visibility(context)
        props.status = "Elige SEGMENTAR TODO o CONTINUAR CON STL DICOM"
        return {"FINISHED"}

CLASSES = (
    DSG_OT_install_dicom_runtime,
    DICOMWIZARDPRO_OT_select_file,
    DICOMWIZARDPRO_OT_next,
    DICOMWIZARDPRO_OT_new_file,
    DICOMWIZARDPRO_OT_auto_threshold,
    DICOMWIZARDPRO_OT_reset_plane,
    DICOMWIZARDPRO_OT_align_mpr_from_active_plane,
    DICOMWIZARDPRO_OT_reset_mpr_orientation,
    DICOMWIZARDPRO_OT_center_plane,
    DICOMWIZARDPRO_OT_select_target,
    DICOMWIZARDPRO_OT_radiographic_quad_view,
    DICOMWIZARDPRO_OT_move_review_plane,
    DICOMWIZARDPRO_OT_rotate_review_plane,
    DICOMWIZARDPRO_OT_close_safe_mpr,
    DICOMWIZARDPRO_OT_fit_view,
    DICOMWIZARDPRO_OT_fit_clinical_preview,
    DICOMWIZARDPRO_OT_refresh,
    DICOMWIZARDPRO_OT_to_segmentation,
    DICOMWIZARDPRO_OT_undo_last,
    DICOMWIZARDPRO_OT_back_to_viewer,
    DICOMWIZARDPRO_OT_clear_drawings,
    DICOMWIZARDPRO_OT_analyze_tissues,
    DICOMWIZARDPRO_OT_adjust_tissue_sensitivity,
    DICOMWIZARDPRO_OT_reset_tissue_range,
    DICOMWIZARDPRO_OT_calculate_segmentation,
    DICOMWIZARDPRO_OT_remove_small_islands,
    DICOMWIZARDPRO_OT_keep_largest_island,
    DICOMWIZARDPRO_OT_close_gaps,
    DICOMWIZARDPRO_OT_fill_holes,
    DICOMWIZARDPRO_OT_segment_semantic_structure,
    DICOMWIZARDPRO_OT_segment_all,
    DICOMWIZARDPRO_OT_direct_dicom_to_surface,
    DICOMWIZARDPRO_OT_continue_with_dicom_stl,
    DICOMWIZARDPRO_OT_prepare_ai_alignment,
    DICOMWIZARDPRO_OT_prepare_alignment,
    DICOMWIZARDPRO_OT_export_surface_stl,
    DICOMWIZARDPRO_OT_generate_surface,
    DICOMWIZARDPRO_OT_select_surface,
    DICOMWIZARDPRO_OT_back_to_segmentation,
)

# Preserve the operator class tuple before panels.py reuses CLASSES.
OPERATOR_CLASSES = CLASSES

# =============================================================================
# MODULE: panels.py
# =============================================================================

