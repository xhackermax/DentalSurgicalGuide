import gc
from pathlib import Path

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper


_LAST_PROBE: SourceProbe | None = None


def _fill_probe_properties(props, probe: SourceProbe) -> None:
    props.filepath = probe.filepath
    props.filename = probe.filename
    props.source_kind = probe.source_kind
    props.dimensions_summary = probe.dimensions_text
    props.spacing_summary = probe.spacing_text
    props.equipment_summary = " · ".join(
        value for value in (probe.manufacturer, probe.model) if value and value != "—"
    ) or "Equipo no indicado"
    props.estimated_memory_mb = probe.estimated_memory_mb
    props.spacing_inferred = probe.spacing_inferred
    props.header_valid = True
    props.volume_loaded = False
    props.status = (
        "DICOM preparado · serie recuperada automáticamente"
        if probe.recovered_from_non_image
        else "DICOM preparado"
    )


def _clear_properties(props) -> None:
    RUNTIME.update_lock = True
    try:
        props.step = 1
        props.filepath = ""
        props.status = "Selecciona DICOM (.dcm, .dicom, DICOMDIR o sin extensión)"
        props.header_valid = False
        props.volume_loaded = False
        props.filename = ""
        props.source_kind = ""
        props.dimensions_summary = ""
        props.spacing_summary = ""
        props.equipment_summary = ""
        props.estimated_memory_mb = 0.0
        props.spacing_inferred = False
        props.show_volume = True
        props.show_planes = True
        props.show_all_planes = False
        props.show_box = False
        props.realtime_mpr = True
        props.correct_inplane_180 = True
        # Shared orthonormal frame used by axial/coronal/sagittal MPR.
        # It is separate from the DICOM root transform: rotating the root only
        # moves the scene, while this matrix changes the actual reconstructed
        # anatomical cuts.
        props["mpr_alignment_matrix"] = [
            1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0,
        ]
        props.active_plane = "AXIAL"
        props.axial_position = 50.0
        props.coronal_position = 50.0
        props.sagittal_position = 50.0
        props.axial_rotation_u = 0.0
        props.axial_rotation_v = 0.0
        props.coronal_rotation_u = 0.0
        props.coronal_rotation_v = 0.0
        props.sagittal_rotation_u = 0.0
        props.sagittal_rotation_v = 0.0
        for orientation in ("axial", "coronal", "sagittal"):
            setattr(props, f"{orientation}_move_x", 50.0)
            setattr(props, f"{orientation}_move_y", 50.0)
            setattr(props, f"{orientation}_move_z", 50.0)
            setattr(props, f"{orientation}_rotate_x", 0.0)
            setattr(props, f"{orientation}_rotate_y", 0.0)
            setattr(props, f"{orientation}_rotate_z", 0.0)
        props.threshold_min_percent = 10.0
        props.threshold_max_percent = 90.0
        props.current_density_min = 0.0
        props.current_density_max = 1.0
        props.volume_opacity = 0.16
        props.preview_volume_opacity = 0.08
        props.preview_display_mode = "SURFACE"
        props.auto_solid_preview = True
        props.surface_preview_quality = "128"
        props.surface_preview_ready = False
        props.surface_preview_status = "Sólido automático"
        props.preview_shell_width_percent = 0.35
        props.preview_surface_emphasis = 2.0
        props.segmentation_structure = "BONE"
        props.auto_thresholds_ready = False
        props.auto_analysis_method = "Sin analizar"
        props.auto_analysis_samples = 0
        props.auto_air_soft_threshold = 0.0
        props.auto_soft_bone_threshold = 0.0
        props.auto_bone_teeth_threshold = 0.0
        props.auto_tooth_seed_threshold = 0.0
        props.auto_metal_cutoff = 1.0
        props.auto_robust_low = 0.0
        props.auto_robust_high = 1.0
        props.auto_class_overlap_percent = 8.0
        props.auto_range_low = 0.0
        props.auto_range_high = 1.0
        props.paint_mode = "ADD"
        props.brush_radius_mm = 2.0
        props.brush_depth_mm = 1.0
        props.show_segmentation_overlay = True
        props.seg_density_tolerance = 38.0
        props.seg_edge_respect = 55.0
        props.seg_roi_margin_mm = 18.0
        props.island_min_mm3 = 5.0
        props.close_radius_mm = 0.6
        props.correct_stl_x_180 = False
        props.correct_stl_z_180 = False
        props.direct_stl_quality = "640"
        props.surface_smoothing_iterations = 0
        props.surface_reduction_percent = 0.0
        props.positive_seed_count = 0
        props.negative_seed_count = 0
        props.learned_density_low = 0.0
        props.learned_density_high = 0.0
        props.segmented_voxel_count = 0
        props.segmented_volume_mm3 = 0.0
        props.segmentation_ready = False
        props.generated_surface_name = ""
        props.surface_ready = False
        props.segmentation_progress = 0.0
        props.segmentation_progress_phase = ""
        props.segmentation_progress_detail = ""
    finally:
        RUNTIME.update_lock = False




class DSG_OT_install_dicom_runtime(Operator):
    bl_idname = "dsg.install_dicom_runtime"
    bl_label = "Preparar Motor DICOM offline"
    bl_description = (
        "Recupera o instala desde wheelhouse local pydicom y codecs para "
        "JPEG/JPEG-LS/JPEG2000/RLE en la carpeta privada de DSG"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        if full_pydicom_available():
            self.report({"INFO"}, "Motor DICOM completo ya disponible")
            return {"FINISHED"}
        # pip is intentionally executed from Blender's main thread in v9.2.
        # Previous worker-thread installs could fail inside pip/signal handling
        # and leave a half-written binary runtime. Installation is one-time;
        # clinical segmentation remains asynchronous afterwards.
        if dicom_install_state().get("running"):
            self.report({"INFO"}, "La preparación del Motor DICOM ya está en curso")
            return {"FINISHED"}
        _install_dicom_runtime_worker()
        state = dicom_install_state()
        error = str(state.get("error", "") or "")
        if error:
            self.report({"ERROR"}, error[:500])
            return {"CANCELLED"}
        if bool(state.get("restart_required", False)):
            self.report({"WARNING"}, "Motor DICOM preparado. Reinicia Mixar/Blender una vez.")
        else:
            self.report({"INFO"}, "Motor DICOM preparado")
        return {"FINISHED"}


def _auto_detect_ai_device_after_dicom(context) -> dict:
    """Cheap TotalSegmentator compute detection without importing Torch in Blender UI."""
    props = context.scene.dicom_wizard_pro
    result = {"device":"AUTO","cuda":False,"gpu_name":"","vram_free_gb":0.0,"vram_total_gb":0.0,"detail":""}
    try:
        from . import totalseg_runtime
        quick=totalseg_runtime.quick_status()
        if not quick.dependencies_ready:
            props.ai_device_preference="AUTO"; props.ai_cuda_available=False; props.ai_device_detected="TotalSegmentator pendiente"
            result["detail"]=props.ai_device_detected; return result
        cuda=bool(totalseg_runtime._nvidia_driver_present())
        props.ai_cuda_available=cuda; props.ai_gpu_name="NVIDIA GPU" if cuda else ""; props.ai_vram_free_gb=0.0; props.ai_vram_total_gb=0.0
        props.ai_device_preference="CUDA" if cuda else "CPU"
        detail="CUDA AUTO · TotalSegmentator" if cuda else "TotalSegmentator · CPU"
        props.ai_device_detected=detail
        result.update(device="CUDA" if cuda else "CPU",cuda=cuda,gpu_name=props.ai_gpu_name,detail=detail)
        context.scene["DSG_ai_device_auto_detected"]=result["device"]; context.scene["DSG_cuda_available"]=cuda
        return result
    except Exception as exc:
        props.ai_device_preference="AUTO"; props.ai_cuda_available=False; props.ai_device_detected=f"TotalSegmentator · detección pendiente: {exc}"[:120]
        result["detail"]=props.ai_device_detected; return result


class DICOMWIZARDPRO_OT_select_file(Operator, ImportHelper):
    bl_idname = "dicom_wizard_pro.select_file"
    bl_label = "Elegir DICOM / DCM"
    bl_description = (
        "Selecciona un archivo DICOM (.dcm, .dicom, DICOMDIR o sin extensión), "
        "multi-frame o un corte perteneciente a una serie"
    )
    bl_options = {"REGISTER"}

    # DICOM is a file format, not a filename extension. Dental CBCT exports may
    # use .dcm, .dicom, DICOMDIR, numeric/opaque names or no extension at all.
    # Never append or require .dcm: the reader validates the file by content.
    filename_ext = ""
    check_extension = False
    filter_glob: bpy.props.StringProperty(
        default="*.dcm;*.DCM;*.dicom;*.DICOM;DICOMDIR;dicomdir;*.*;*",
        options={"HIDDEN"},
    )

    def execute(self, context):
        global _LAST_PROBE
        props = context.scene.dicom_wizard_pro
        try:
            props.status = "Leyendo cabecera y buscando la serie…"
            probe = probe_source(self.filepath)
            _LAST_PROBE = probe
            _fill_probe_properties(props, probe)
            write_header_text(probe)
            # Opening/selecting a CBCT must remain lightweight. Never import
            # Torch/nnU-Net here; that was a hidden multi-second UI stall.
            compute = {"detail": ""}
            # Full DICOM/AI preflight already runs once at deferred add-on startup.
            # File selection performs only exact TransferSyntax validation below.
        except Exception as exc:
            _LAST_PROBE = None
            props.header_valid = False
            props.status = f"Error: {exc}"
            print("DICOM Wizard Pro probe error:", repr(exc))
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        support_ready, support_detail = dicom_transfer_syntax_support(probe.transfer_syntax_uid)
        if not support_ready:
            props.status = (
                f"Motor DICOM incompleto para {probe.transfer_syntax_uid or 'TransferSyntax desconocida'} · "
                f"{support_detail}"
            )
            self.report({"WARNING"}, props.status)
        elif probe.recovered_from_non_image:
            self.report(
                {"WARNING"},
                f"El archivo elegido no era una imagen. {probe.recovery_note} "
                f"Usando: {probe.filename}",
            )
        else:
            self.report({"INFO"}, f"DICOM preparado: {probe.dimensions_text}")

        compute_detail = str((compute or {}).get("detail", "") or "")
        if compute_detail:
            current = str(props.status or "")
            if current and compute_detail not in current:
                props.status = current + " · " + compute_detail
            elif not current:
                props.status = compute_detail
            if bool((compute or {}).get("cuda", False)):
                self.report({"INFO"}, compute_detail)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_next(Operator):
    bl_idname = "dicom_wizard_pro.next"
    bl_label = "Siguiente"
    bl_description = "Carga el CBCT sin bloquear la interfaz"
    bl_options = {"REGISTER"}

    _timer = None
    _thread = None
    _payload = None
    _error = ""
    _progress = 0.0
    _message = ""
    _done = False

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return (
            props is not None
            and props.header_valid
            and bool(props.filepath)
            and load_pydicom() is not None
            and load_numpy() is not None
            and (
                _LAST_PROBE is None
                or dicom_transfer_syntax_support(getattr(_LAST_PROBE, "transfer_syntax_uid", ""))[0]
            )
        )

    def _worker(self, probe):
        try:
            def cb(current: int, total: int, message: str) -> None:
                self._progress = max(0.0, min(1.0, float(current) / max(1.0, float(total))))
                self._message = str(message)
            self._payload = _decode_volume_payload(probe, cb)
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            self._done = True

    def _finish_modal(self, context):
        try:
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        self._timer = None
        progress_end(context)

    def execute(self, context):
        global _LAST_PROBE
        props = context.scene.dicom_wizard_pro
        try:
            if _LAST_PROBE is None or _LAST_PROBE.filepath != props.filepath:
                props.status = "Comprobando DICOM…"
                _LAST_PROBE = probe_source(props.filepath)
            probe = _LAST_PROBE
            ready, detail = dicom_transfer_syntax_support(probe.transfer_syntax_uid)
            if not ready:
                raise RuntimeError(detail)

            # Clear only Blender scene artefacts on the UI thread. The expensive
            # DICOM decode itself runs in a worker that never touches bpy.
            cleanup_scene()
            remove_cached_vdb()
            self._payload = None
            self._error = ""
            self._progress = 0.0
            self._message = "Preparando lectura…"
            self._done = False
            progress_begin(context, 100)
            props.status = "Abriendo CBCT…"
            self._thread = threading.Thread(target=self._worker, args=(probe,), daemon=True, name="DSG-DICOM-Decode")
            self._thread.start()
            self._timer = context.window_manager.event_timer_add(0.10, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self._finish_modal(context)
            props.volume_loaded = False
            props.status = f"Error: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        props = context.scene.dicom_wizard_pro
        progress_update(context, 5 + int(70 * self._progress))
        props.status = self._message or "Decodificando CBCT…"
        try:
            context.workspace.status_text_set(props.status)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not self._done:
            return {"RUNNING_MODAL"}

        if self._error:
            self._finish_modal(context)
            props.volume_loaded = False
            props.status = self._error
            try:
                context.scene["DSG_route_step"] = "PATIENT"
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, self._error)
            return {"CANCELLED"}

        try:
            probe = _LAST_PROBE
            _commit_volume_payload(probe, self._payload)
            # Classic-series discovery may have been completed by the worker, so
            # publish the final slice count/spacing/memory metadata now.
            _fill_probe_properties(props, probe)
            progress_update(context, 80)
            full_range = max(RUNTIME.density_max - RUNTIME.density_min, 1e-6)
            RUNTIME.update_lock = True
            try:
                props.threshold_min_percent = max(0.0, min(100.0, 100.0 * (RUNTIME.auto_low - RUNTIME.density_min) / full_range))
                props.threshold_max_percent = max(0.0, min(100.0, 100.0 * (RUNTIME.auto_high - RUNTIME.density_min) / full_range))
                props["mpr_alignment_matrix"] = [1.0,0.0,0.0, 0.0,1.0,0.0, 0.0,0.0,1.0]
                props.active_plane = "AXIAL"
                props.axial_position = props.coronal_position = props.sagittal_position = 50.0
                for orientation in ("axial", "coronal", "sagittal"):
                    setattr(props, f"{orientation}_move_x", 50.0)
                    setattr(props, f"{orientation}_move_y", 50.0)
                    setattr(props, f"{orientation}_move_z", 50.0)
                    setattr(props, f"{orientation}_rotate_x", 0.0)
                    setattr(props, f"{orientation}_rotate_y", 0.0)
                    setattr(props, f"{orientation}_rotate_z", 0.0)
                # MPR-first opening: the fog/OpenVDB preview is deliberately not
                # built here. It was both expensive and visually obstructive.
                props.show_volume = False
                props.show_planes = True
                props.show_all_planes = False
                props.show_box = False
                props.volume_loaded = True
                props.step = 2
            finally:
                RUNTIME.update_lock = False

            props.status = "Creando MPR…"
            create_viewer_scene(context, include_volume=False)
            update_density_labels(props)
            progress_update(context, 100)
            props.status = "CBCT listo"
            # Publish route readiness only after the asynchronous decode and MPR
            # creation actually succeeded. The calling suite operator may have
            # returned long before this modal reaches completion.
            try:
                context.scene["DSG_route_step"] = "CBCT_READY"
                context.scene["DSG_suite_stage"] = "DICOM"
                context.scene["DSG_patient_dicom_path"] = str(probe.filepath)
                # v9.2.71 hard gate. The route cannot use a deep-verification
                # result from addon startup or another patient.
                context.scene["DSG_immediate_gate_armed"] = False
                context.scene["DSG_immediate_gate_cbct_ready_at"] = float(time.time())
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                context.workspace.status_text_set("CBCT listo · MPR nativo · volumen 3D diferido")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            # v9.2.75: DO NOT import Torch, verify nnU-Net, launch CUDA, or warm
            # AI models merely because a patient was opened. Those operations
            # compete for RAM/CPU/GPU and made the SIMPLE route slower. The AI
            # process is now lazy and starts only when IMPLANTE INMEDIATO is
            # explicitly selected.
            try:
                from . import runtime_bootstrap
                runtime_bootstrap.invalidate_ui_component_status()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            self._finish_modal(context)
            return {"FINISHED"}
        except Exception as exc:
            self._finish_modal(context)
            cleanup_scene()
            props.volume_loaded = False
            props.status = f"Error: {exc}"
            try:
                context.scene["DSG_route_step"] = "PATIENT"
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class DICOMWIZARDPRO_OT_new_file(Operator):
    bl_idname = "dicom_wizard_pro.new_file"
    bl_label = "Back to DICOM Start"
    bl_description = "Deletes DICOM module work, closes the current volume and returns to the first step"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        global _LAST_PROBE
        ok, message = _close_mpr_before_workflow_action(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        restore_clinical_preview_view(context)
        cleanup_scene()
        remove_cached_vdb()
        RUNTIME.reset()
        _LAST_PROBE = None
        props = context.scene.dicom_wizard_pro
        _clear_properties(props)
        context.scene[TOOTH_ANALYSIS_COMPLETED_KEY] = False
        try:
            from . import cbct_dental_module
            cbct_dental_module.clear_dentition(keep_alignment_reference=False)
            cbct_dental_module.reset_scene_state(context.scene)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        # Roadmaps are case-specific clinical audit objects. An explicit new
        # DICOM case reset removes the active roadmap metadata but never tries
        # to undo already-created geometry.
        for key in ("DSG_roadmap_store_json", "DSG_roadmap_active_plan_id"):
            try:
                del context.scene[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.scene[SUITE_STAGE_KEY] = "DICOM"
        gc.collect()
        self.report({"INFO"}, _dw_t(props, "DICOM workflow reset", "Flujo DICOM reiniciado"))
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_auto_threshold(Operator):
    bl_idname = "dicom_wizard_pro.auto_threshold"
    bl_label = "Automático"
    bl_description = "Recupera el rango de densidad automático"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return RUNTIME.is_loaded()

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        full_range = max(RUNTIME.density_max - RUNTIME.density_min, 1e-6)
        RUNTIME.update_lock = True
        try:
            props.threshold_min_percent = max(
                0.0,
                min(100.0, 100.0 * (RUNTIME.auto_low - RUNTIME.density_min) / full_range),
            )
            props.threshold_max_percent = max(
                0.0,
                min(100.0, 100.0 * (RUNTIME.auto_high - RUNTIME.density_min) / full_range),
            )
        finally:
            RUNTIME.update_lock = False
        update_density_labels(props)
        refresh_volume_material(context)
        refresh_plane_images_from_objects(context)
        props.status = "Threshold automático"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_reset_plane(Operator):
    bl_idname = "dicom_wizard_pro.reset_plane"
    bl_label = "Enderezar"
    bl_description = "Restablece la rotación del plano seleccionado"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        orientation = props.active_plane
        prefix = orientation.lower()
        RUNTIME.update_lock = True
        try:
            setattr(props, f"{prefix}_rotate_x", 0.0)
            setattr(props, f"{prefix}_rotate_y", 0.0)
            setattr(props, f"{prefix}_rotate_z", 0.0)
            # Keep legacy angles neutral as well.
            setattr(props, f"{prefix}_rotation_u", 0.0)
            setattr(props, f"{prefix}_rotation_v", 0.0)
        finally:
            RUNTIME.update_lock = False
        _apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
        refresh_plane_image_from_object(context, orientation, max_axis=MAX_MPR_AXIS)
        update_visibility(context)
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_align_mpr_from_active_plane(Operator):
    bl_idname = "dicom_wizard_pro.align_mpr_from_active_plane"
    bl_label = "Alinear los 3 cortes desde este plano"
    bl_description = (
        "Convierte la orientación actual del plano seleccionado en la orientación "
        "anatómica común y reconstruye axial, coronal y sagital perpendiculares"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded and RUNTIME.is_loaded()

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        orientation = props.active_plane
        plane = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        root = bpy.data.objects.get(ROOT_NAME)
        if plane is None or root is None:
            self.report({"ERROR"}, "No se encontró el plano MPR activo")
            return {"CANCELLED"}

        np = load_numpy()
        if np is None:
            self.report({"ERROR"}, "NumPy no está disponible")
            return {"CANCELLED"}

        local_matrix = root.matrix_world.inverted_safe() @ plane.matrix_world
        current_frame = np.asarray((
            (local_matrix[0][0], local_matrix[0][1], local_matrix[0][2]),
            (local_matrix[1][0], local_matrix[1][1], local_matrix[1][2]),
            (local_matrix[2][0], local_matrix[2][1], local_matrix[2][2]),
        ), dtype=np.float64)
        current_frame = _orthonormal_rotation_matrix(current_frame)
        base_frame = _base_plane_frame(orientation)
        alignment = current_frame @ base_frame.T
        _store_mpr_alignment_matrix(props, alignment)

        # The selected plane orientation is now carried by the shared frame.
        # Neutralise all independent rotations so the other two cuts become
        # exactly perpendicular instead of inheriting unrelated oblique angles.
        RUNTIME.update_lock = True
        try:
            for prefix in ("axial", "coronal", "sagittal"):
                setattr(props, f"{prefix}_rotate_x", 0.0)
                setattr(props, f"{prefix}_rotate_y", 0.0)
                setattr(props, f"{prefix}_rotate_z", 0.0)
                setattr(props, f"{prefix}_rotation_u", 0.0)
                setattr(props, f"{prefix}_rotation_v", 0.0)
        finally:
            RUNTIME.update_lock = False

        _refresh_all_aligned_planes(context)
        props.status = (
            f"Orientación anatómica tomada del plano {PLANE_SPECS[orientation]['label']}; "
            "los tres cortes vuelven a ser perpendiculares"
        )
        self.report({"INFO"}, "Orientación anatómica aplicada a los tres cortes")
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_reset_mpr_orientation(Operator):
    bl_idname = "dicom_wizard_pro.reset_mpr_orientation"
    bl_label = "Restablecer orientación MPR"
    bl_description = (
        "Elimina la inclinación compartida, centra los tres cortes y recupera "
        "axial, coronal y sagital originales del volumen"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded and RUNTIME.is_loaded()

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        np = load_numpy()
        if np is None:
            self.report({"ERROR"}, "NumPy no está disponible")
            return {"CANCELLED"}

        _store_mpr_alignment_matrix(props, np.eye(3, dtype=np.float64))
        RUNTIME.update_lock = True
        try:
            props.axial_position = 50.0
            props.coronal_position = 50.0
            props.sagittal_position = 50.0
            for prefix in ("axial", "coronal", "sagittal"):
                setattr(props, f"{prefix}_move_x", 50.0)
                setattr(props, f"{prefix}_move_y", 50.0)
                setattr(props, f"{prefix}_move_z", 50.0)
                setattr(props, f"{prefix}_rotate_x", 0.0)
                setattr(props, f"{prefix}_rotate_y", 0.0)
                setattr(props, f"{prefix}_rotate_z", 0.0)
                setattr(props, f"{prefix}_rotation_u", 0.0)
                setattr(props, f"{prefix}_rotation_v", 0.0)
        finally:
            RUNTIME.update_lock = False

        _refresh_all_aligned_planes(context)
        props.status = "Orientación MPR restablecida: tres cortes centrados y perpendiculares"
        self.report({"INFO"}, "Orientación MPR restablecida")
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_center_plane(Operator):
    bl_idname = "dicom_wizard_pro.center_plane"
    bl_label = "Centrar plano"
    bl_description = "Coloca el plano activo en el centro X/Y/Z del volumen sin cambiar su rotación"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded and RUNTIME.is_loaded()

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        orientation = props.active_plane
        prefix = orientation.lower()
        RUNTIME.update_lock = True
        try:
            setattr(props, f"{prefix}_move_x", 50.0)
            setattr(props, f"{prefix}_move_y", 50.0)
            setattr(props, f"{prefix}_move_z", 50.0)
        finally:
            RUNTIME.update_lock = False
        _apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
        refresh_plane_image_from_object(context, orientation, max_axis=MAX_MPR_AXIS)
        update_visibility(context)
        props.status = f"Plano {PLANE_SPECS[orientation]['label']} centrado"
        return {"FINISHED"}


class DICOMWIZARDPRO_OT_select_target(Operator):
    bl_idname = "dicom_wizard_pro.select_target"
    bl_label = "Seleccionar control"
    bl_description = "Selecciona el plano activo o el control del volumen para usar G/R/S"
    bl_options = {"REGISTER"}

    target: bpy.props.EnumProperty(
        items=[
            ("PLANE", "Plano", "Seleccionar el plano activo"),
            ("VOLUME", "Volumen", "Seleccionar el control del volumen completo"),
        ],
        default="PLANE",
    )

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "dicom_wizard_pro", None)
        return props is not None and props.volume_loaded

    def execute(self, context):
        props = context.scene.dicom_wizard_pro
        if self.target == "VOLUME":
            obj = bpy.data.objects.get(ROOT_NAME)
        else:
            obj = bpy.data.objects.get(PLANE_SPECS[props.active_plane]["object"])
        if obj is None:
            self.report({"ERROR"}, "No se encontró el control solicitado")
            return {"CANCELLED"}

        for selected in context.selected_objects:
            selected.select_set(False)
        obj.hide_select = False
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        try:
            context.scene.transform_orientation_slots[0].type = "LOCAL"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        props.status = (
            "Usa G/R/S sobre el volumen completo"
            if self.target == "VOLUME"
            else "Usa G/R/S: el corte se recalcula en tiempo real"
        )
        return {"FINISHED"}



def _dicom_volume_extent_mm() -> float:
    """Return a safe physical size used to frame the radiographic viewports."""
    if not RUNTIME.is_loaded():
        return 100.0
    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    return max(
        max(1, x_count - 1) * x_spacing,
        max(1, y_count - 1) * y_spacing,
        max(1, z_count - 1) * z_spacing,
        1.0,
    )


def _radiographic_proxy_name(orientation: str) -> str:
    return RADIOGRAPHIC_PROXY_PREFIX + orientation.upper()


def _radiographic_proxy_mesh_name(orientation: str) -> str:
    return RADIOGRAPHIC_PROXY_MESH_PREFIX + orientation.upper()


def _radiographic_proxy_location(orientation: str) -> Vector:
    """Return an isolated world location for one flat MPR display.

    Blender's native quad view gives every sub-region its own camera but keeps
    one shared SpaceView3D, so object visibility cannot be different per
    quadrant. The three display panels are therefore spaced far apart. Each
    radiographic region frames only its own panel; the true DICOM scene stays
    around the origin for the 3D quadrant.
    """
    extent = _dicom_volume_extent_mm()
    spacing = max(extent * 12.0, 1200.0)
    index = {"AXIAL": 1.0, "CORONAL": 2.0, "SAGITTAL": 3.0}[orientation.upper()]
    return Vector((spacing * index, 0.0, 0.0))


def _get_radiographic_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.get(RADIOGRAPHIC_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(RADIOGRAPHIC_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _build_flat_proxy_mesh(
    obj: bpy.types.Object,
    width: float,
    height: float,
    material: bpy.types.Material | None,
) -> None:
    half_width = max(float(width), 1e-3) * 0.5
    half_height = max(float(height), 1e-3) * 0.5
    mesh = obj.data
    mesh.clear_geometry()
    mesh.from_pydata(
        [
            (-half_width, -half_height, 0.0),
            (half_width, -half_height, 0.0),
            (half_width, half_height, 0.0),
            (-half_width, half_height, 0.0),
        ],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()

    uv_layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    coordinates = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    polygon = mesh.polygons[0]
    for loop_index, uv in zip(polygon.loop_indices, coordinates):
        uv_layer.data[loop_index].uv = uv

    mesh.materials.clear()
    if material is not None:
        mesh.materials.append(material)
    obj["dicom_plane_width_mm"] = float(width)
    obj["dicom_plane_height_mm"] = float(height)


def _ensure_radiographic_proxy(orientation: str) -> bpy.types.Object | None:
    orientation = orientation.upper()
    source = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
    if source is None:
        return None

    collection = _get_radiographic_collection()
    object_name = _radiographic_proxy_name(orientation)
    mesh_name = _radiographic_proxy_mesh_name(orientation)
    obj = bpy.data.objects.get(object_name)
    if obj is None or obj.type != "MESH":
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        mesh = bpy.data.meshes.get(mesh_name) or bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(object_name, mesh)
        collection.objects.link(obj)
    elif collection.objects.get(obj.name) is None:
        collection.objects.link(obj)

    width = float(source.get("dicom_plane_width_mm", max(source.dimensions.x, 1.0)))
    height = float(source.get("dicom_plane_height_mm", max(source.dimensions.y, 1.0)))
    material = source.data.materials[0] if source.data and source.data.materials else None
    _build_flat_proxy_mesh(obj, width, height, material)

    obj.parent = None
    obj.matrix_world = Matrix.Translation(_radiographic_proxy_location(orientation))
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Matrix.Identity(4).to_quaternion()
    obj.scale = (1.0, 1.0, 1.0)
    obj.show_in_front = True
    obj.hide_render = True
    obj.hide_select = False
    obj.hide_viewport = False
    obj.hide_set(False)
    obj["dicom_radiographic_proxy"] = True
    obj["dicom_orientation"] = orientation
    return obj


def _sync_radiographic_proxy(orientation: str) -> None:
    """Update an existing display proxy without creating one unnecessarily."""
    if bpy.data.objects.get(_radiographic_proxy_name(orientation)) is None:
        return
    _ensure_radiographic_proxy(orientation)


def _create_radiographic_proxies() -> bool:
    success = True
    for orientation in PLANE_SPECS:
        success = (_ensure_radiographic_proxy(orientation) is not None) and success
    return success


def _remove_radiographic_proxies() -> None:
    collection = bpy.data.collections.get(RADIOGRAPHIC_COLLECTION_NAME)
    if collection is not None:
        for obj in list(collection.objects):
            mesh = obj.data if obj.type == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(collection)
    else:
        for orientation in PLANE_SPECS:
            obj = bpy.data.objects.get(_radiographic_proxy_name(orientation))
            if obj is not None:
                mesh = obj.data if obj.type == "MESH" else None
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)


def _region_view3d(region: bpy.types.Region):
    """Return the RegionView3D owned by a concrete quad sub-region."""
    rv3d = getattr(region, "data", None)
    if rv3d is None or not hasattr(rv3d, "view_rotation"):
        return None
    return rv3d


def _quad_window_regions(area: bpy.types.Area) -> list[bpy.types.Region]:
    """Return quad regions as top-left, top-right, bottom-left, bottom-right."""
    regions = [
        region
        for region in area.regions
        if region.type == "WINDOW" and _region_view3d(region) is not None
    ]
    if len(regions) != 4:
        return []

    entries = [
        (
            region,
            float(region.x) + 0.5 * float(region.width),
            float(region.y) + 0.5 * float(region.height),
        )
        for region in regions
    ]
    x_values = [entry[1] for entry in entries]
    y_values = [entry[2] for entry in entries]
    minimum_width = max(1.0, min(float(region.width) for region in regions))
    minimum_height = max(1.0, min(float(region.height) for region in regions))
    if (max(x_values) - min(x_values)) < 0.35 * minimum_width:
        return []
    if (max(y_values) - min(y_values)) < 0.35 * minimum_height:
        return []

    by_x = sorted(entries, key=lambda entry: entry[1])
    left = by_x[:2]
    right = by_x[2:]
    top_left = max(left, key=lambda entry: entry[2])[0]
    bottom_left = min(left, key=lambda entry: entry[2])[0]
    top_right = max(right, key=lambda entry: entry[2])[0]
    bottom_right = min(right, key=lambda entry: entry[2])[0]
    ordered = [top_left, top_right, bottom_left, bottom_right]
    return ordered if len({region.as_pointer() for region in ordered}) == 4 else []


def _prepare_independent_quad_region(rv3d) -> None:
    try:
        rv3d.lock_rotation = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        rv3d.show_sync_view = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        rv3d.use_box_clip = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _set_region_view_from_proxy(
    region: bpy.types.Region,
    orientation: str,
) -> bool:
    """Frame only the dedicated flat image panel for one MPR orientation."""
    proxy = bpy.data.objects.get(_radiographic_proxy_name(orientation))
    rv3d = _region_view3d(region)
    if proxy is None or rv3d is None:
        return False

    try:
        _prepare_independent_quad_region(rv3d)
        # The proxy is deliberately a flat XY panel. Its image already contains
        # the axial/coronal/sagittal reconstruction, so this viewport is a true
        # independent radiographic monitor rather than another angle of the 3D
        # scene.
        rv3d.view_rotation = proxy.matrix_world.to_quaternion().inverted()
        rv3d.view_location = proxy.matrix_world.translation.copy()
        rv3d.view_perspective = "ORTHO"

        width = float(proxy.get("dicom_plane_width_mm", 100.0))
        height = float(proxy.get("dicom_plane_height_mm", 100.0))
        aspect = max(float(region.width), 1.0) / max(float(region.height), 1.0)
        required_height = max(height, width / max(aspect, 1e-6))
        rv3d.view_distance = max(required_height * 0.56, 1.0)
        try:
            rv3d.view_camera_zoom = 0.0
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            rv3d.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            rv3d.lock_rotation = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True
    except Exception as exc:
        print(f"DICOM independent MPR view {orientation} error:", repr(exc))
        return False


def _set_region_view_3d(
    context: bpy.types.Context,
    area: bpy.types.Area,
    region: bpy.types.Region,
) -> bool:
    """Configure the bottom-right quadrant as the true clinical 3D scene."""
    rv3d = _region_view3d(region)
    if rv3d is None:
        return False
    target = bpy.data.objects.get(ROOT_NAME) or bpy.data.objects.get(BOUNDING_BOX_NAME)
    extent = _dicom_volume_extent_mm()
    try:
        _prepare_independent_quad_region(rv3d)
        rv3d.view_perspective = "PERSP"
        rv3d.view_location = (
            target.matrix_world.translation.copy()
            if target is not None
            else Vector((0.0, 0.0, 0.0))
        )
        camera_world = (
            Matrix.Rotation(math.radians(58.0), 4, "X")
            @ Matrix.Rotation(math.radians(-42.0), 4, "Z")
        )
        rv3d.view_rotation = camera_world.to_quaternion().inverted()
        rv3d.view_distance = max(extent * 1.15, 1.0)
        try:
            rv3d.view_camera_zoom = 0.0
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            rv3d.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True
    except Exception as exc:
        print("DICOM radiographic 3D view error:", repr(exc))
        return False


def configure_radiographic_quad_view(context: bpy.types.Context, area: bpy.types.Area) -> bool:
    """Configure three isolated MPR monitors plus one genuine 3D viewport."""
    if area is None or area.type != "VIEW_3D":
        return False
    space = area.spaces.active
    if not getattr(space, "region_quadviews", None):
        return False
    if not _create_radiographic_proxies():
        return False

    regions = _quad_window_regions(area)
    if len(regions) != 4:
        return False

    for region in regions:
        rv3d = _region_view3d(region)
        if rv3d is not None:
            _prepare_independent_quad_region(rv3d)

    try:
        space.shading.type = "MATERIAL"
        space.clip_start = 0.05
        # Proxies live far from the origin, so the shared clipping range must
        # include them while the 3D quadrant remains centred on the patient.
        farthest_proxy = max(
            abs(_radiographic_proxy_location(orientation).x)
            for orientation in PLANE_SPECS
        )
        space.clip_end = max(10000.0, farthest_proxy * 2.0)
        space.overlay.show_floor = False
        space.overlay.show_cursor = False
        space.overlay.show_text = True
        space.overlay.show_stats = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    top_left, top_right, bottom_left, bottom_right = regions
    success = _set_region_view_from_proxy(top_left, "AXIAL")
    success = _set_region_view_from_proxy(top_right, "CORONAL") and success
    success = _set_region_view_from_proxy(bottom_left, "SAGITTAL") and success
    success = _set_region_view_3d(context, area, bottom_right) and success
    area.tag_redraw()
    return success



def _area_window_region(area: bpy.types.Area):
    return next((region for region in area.regions if region.type == "WINDOW"), None)


def _area_center_xy(area: bpy.types.Area) -> tuple[int, int]:
    return (
        int(area.x + max(1, area.width) * 0.5),
        int(area.y + max(1, area.height) * 0.5),
    )


def _area_from_pointer(screen: bpy.types.Screen, pointer_value: int):
    return next(
        (area for area in screen.areas if area.as_pointer() == int(pointer_value)),
        None,
    )


def _area_rect(area: bpy.types.Area) -> tuple[int, int, int, int]:
    """Return an editor rectangle in window coordinates."""
    return (int(area.x), int(area.y), int(area.width), int(area.height))


def _rect_contains(
    parent: tuple[int, int, int, int],
    child: tuple[int, int, int, int],
    tolerance: int = 8,
) -> bool:
    px, py, pw, ph = parent
    cx, cy, cw, ch = child
    return (
        cx >= px - tolerance
        and cy >= py - tolerance
        and cx + cw <= px + pw + tolerance
        and cy + ch <= py + ph + tolerance
    )


def _areas_inside_rect(
    screen: bpy.types.Screen,
    rect: tuple[int, int, int, int],
) -> list[bpy.types.Area]:
    """Return real editors created inside one original editor rectangle."""
    return [
        area
        for area in screen.areas
        if _rect_contains(rect, _area_rect(area))
    ]


def _two_columns_in_rect(
    screen: bpy.types.Screen,
    rect: tuple[int, int, int, int],
) -> tuple[bpy.types.Area, bpy.types.Area] | None:
    """Identify a settled left/right split by geometry, not pointer timing."""
    areas = _areas_inside_rect(screen, rect)
    if len(areas) != 2:
        return None
    left, right = sorted(areas, key=lambda area: area.x + area.width * 0.5)
    tolerance = 12
    if abs(left.y - right.y) > tolerance or abs(left.height - right.height) > tolerance:
        return None
    if left.x + left.width > right.x + tolerance:
        return None
    return left, right


def _two_rows_in_rect(
    screen: bpy.types.Screen,
    rect: tuple[int, int, int, int],
) -> tuple[bpy.types.Area, bpy.types.Area] | None:
    """Identify a settled top/bottom split by geometry, not pointer timing."""
    areas = _areas_inside_rect(screen, rect)
    if len(areas) != 2:
        return None
    bottom, top = sorted(areas, key=lambda area: area.y + area.height * 0.5)
    tolerance = 12
    if abs(bottom.x - top.x) > tolerance or abs(bottom.width - top.width) > tolerance:
        return None
    if bottom.y + bottom.height > top.y + tolerance:
        return None
    return top, bottom


def _request_screen_area_split(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    area: bpy.types.Area,
    direction: str,
) -> bool:
    """Request one UI split without assuming that screen.areas updates now.

    Blender finishes rebuilding the Screen after the operator returns.  Trying
    to discover the new Area in the same Python call is the reason v1.4.0 often
    stopped after the first split with “No se pudo identificar el nuevo
    editor”.  The asynchronous builder below waits for the next UI ticks.
    """
    region = _area_window_region(area)
    if region is None:
        return False
    try:
        with bpy.context.temp_override(
            window=window,
            screen=screen,
            area=area,
            region=region,
        ):
            result = bpy.ops.screen.area_split(
                direction=direction,
                factor=0.5,
                cursor=_area_center_xy(area),
            )
        return "FINISHED" in result
    except Exception as exc:
        print("DICOM area split request error:", repr(exc))
        return False


def _configure_clean_view3d_area(area: bpy.types.Area, *, global_view: bool = False) -> None:
    """Make one real 3D editor visually minimal without changing the scene."""
    area.type = "VIEW_3D"
    space = area.spaces.active
    try:
        space.shading.type = "MATERIAL"
        space.clip_start = 0.05
        space.clip_end = max(10000.0, _dicom_volume_extent_mm() * 20.0)
        space.overlay.show_floor = False
        space.overlay.show_cursor = False
        space.overlay.show_stats = False
        space.overlay.show_text = True
        space.show_region_ui = True
        space.show_region_toolbar = False
        space.show_gizmo = bool(global_view)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    area.tag_redraw()


def _mpr_orientation_for_area(context: bpy.types.Context) -> str | None:
    """Return the diagnostic role assigned to the current 3D editor area."""
    area = getattr(context, "area", None)
    scene = getattr(context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
    if area is None or props is None or area.type != "VIEW_3D":
        return None
    if not bool(props.get("radiographic_split_active", False)):
        return None

    pointer = int(area.as_pointer())
    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        stored = int(props.get(f"radiographic_area_{orientation.lower()}", 0))
        if stored and stored == pointer:
            return orientation
    return None


def _mpr_slice_readout(orientation: str, percent: float) -> tuple[int, int, float]:
    """Convert a 0–100 slice position to index, total slices and centred mm."""
    spec = MPR_SLIDER_SPECS[orientation]
    count = max(1, int(RUNTIME.dims_zyx[spec["count_axis"]]))
    spacing = float(RUNTIME.spacing_zyx_mm[spec["spacing_axis"]])
    fraction = clamp(float(percent), 0.0, 100.0) / 100.0
    index_zero = int(round(fraction * max(0, count - 1)))
    position_mm = (index_zero - 0.5 * (count - 1)) * spacing
    return index_zero + 1, count, position_mm


def draw_mpr_slice_header(self, context: bpy.types.Context) -> None:
    # The three independent sliders are drawn inside their own Quad View regions.
    return


def _is_global_mpr_area(context: bpy.types.Context) -> bool:
    area = getattr(context, "area", None)
    scene = getattr(context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
    if area is None or props is None or area.type != "VIEW_3D":
        return False
    if not bool(props.get("radiographic_split_active", False)):
        return False
    return int(props.get("radiographic_area_view_3d", 0)) == int(area.as_pointer())


def draw_mpr_global_header(self, context: bpy.types.Context) -> None:
    """Review controls live exclusively in the add-on sidebar panel."""
    return


def _set_global_mpr_local_visibility(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    area: bpy.types.Area,
    *,
    enabled: bool,
) -> bool:
    """Hide axial/coronal only in the fourth viewport using Local View.

    Scene visibility remains unchanged, so the axial and coronal diagnostic
    viewports keep their own planes.  The fourth viewport retains the complete
    clinical scene but excludes only those two MPR meshes.
    """
    if area is None or area.type != "VIEW_3D":
        return False
    region = _area_window_region(area)
    space = area.spaces.active
    if region is None or space is None:
        return False

    try:
        with bpy.context.temp_override(
            window=window,
            screen=screen,
            area=area,
            region=region,
        ):
            local_view_active = getattr(space, "local_view", None) is not None
            if not enabled:
                if local_view_active:
                    result = bpy.ops.view3d.localview(frame_selected=False)
                    return "FINISHED" in result
                return True

            sagittal = bpy.data.objects.get(PLANE_SPECS["SAGITTAL"]["object"])
            if sagittal is None:
                return False

            if not local_view_active:
                # A single selected seed object creates the per-viewport local
                # view. Membership is then set explicitly for every object.
                for obj in window.view_layer.objects:
                    try:
                        obj.select_set(False)
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
                try:
                    sagittal.hide_set(False)
                    sagittal.select_set(True)
                    window.view_layer.objects.active = sagittal
                except Exception:
                    return False
                result = bpy.ops.view3d.localview(frame_selected=False)
                if "FINISHED" not in result:
                    return False

            excluded = {
                PLANE_SPECS["AXIAL"]["object"],
                PLANE_SPECS["CORONAL"]["object"],
            }
            for obj in window.view_layer.objects:
                try:
                    obj.local_view_set(space, obj.name not in excluded)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

            # Keep the sagittal plane active so Blender's rotation gizmo and
            # R, Z operate on the clinically relevant plane.
            for obj in window.view_layer.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            sagittal.select_set(True)
            window.view_layer.objects.active = sagittal
            area.tag_redraw()
            return True
    except Exception as exc:
        print("DICOM global MPR local-view error:", repr(exc))
        return False




def _set_diagnostic_mpr_local_visibility(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    area: bpy.types.Area,
    orientation: str,
    *,
    enabled: bool,
) -> bool:
    """Isolate exactly one MPR plane in one concrete 3D editor.

    The previous version used Local View as a prerequisite for setting the
    camera.  When Local View did not settle immediately after an area split,
    camera configuration was skipped and all three editors stayed in the
    inherited User Perspective.  This routine now resets inherited local-view
    state, enters it with a complete context override, and verifies membership.
    Camera orientation is handled independently by ``_configure_mpr_axis_view``.
    """
    if area is None or area.type != "VIEW_3D":
        return False
    orientation = orientation.upper()
    region = _area_window_region(area)
    space = area.spaces.active
    plane = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
    scene = getattr(window, "scene", None)
    view_layer = getattr(window, "view_layer", None)
    if region is None or space is None or plane is None or scene is None or view_layer is None:
        return False

    previous_selected = [obj for obj in view_layer.objects if obj.select_get()]
    previous_active = view_layer.objects.active

    def _override():
        return bpy.context.temp_override(
            window=window,
            screen=screen,
            area=area,
            region=region,
            scene=scene,
            view_layer=view_layer,
        )

    try:
        # Always clear an inherited/stale Local View first.  Areas created by a
        # split copy the source SpaceView3D and can otherwise inherit its state.
        if getattr(space, "local_view", None) is not None:
            with _override():
                result = bpy.ops.view3d.localview(frame_selected=False)
            if "FINISHED" not in result:
                return False

        if not enabled:
            area.tag_redraw()
            return getattr(space, "local_view", None) is None

        for obj in view_layer.objects:
            try:
                obj.select_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            plane.hide_set(False)
            plane.hide_viewport = False
            plane.select_set(True)
            view_layer.objects.active = plane
        except Exception:
            return False

        with _override():
            result = bpy.ops.view3d.localview(frame_selected=False)
        if "FINISHED" not in result or getattr(space, "local_view", None) is None:
            return False

        # Explicit membership makes the result deterministic even if the
        # original editor contained several selected objects before splitting.
        for obj in view_layer.objects:
            try:
                obj.local_view_set(space, obj == plane)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        try:
            isolated = bool(plane.local_view_get(space))
            if isolated:
                for other_orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
                    if other_orientation == orientation:
                        continue
                    other = bpy.data.objects.get(PLANE_SPECS[other_orientation]["object"])
                    if other is not None and other.local_view_get(space):
                        isolated = False
                        break
        except Exception:
            isolated = getattr(space, "local_view", None) is not None

        area.tag_redraw()
        return isolated
    except Exception as exc:
        print(f"DICOM diagnostic local-view {orientation} error:", repr(exc))
        return False
    finally:
        for obj in view_layer.objects:
            try:
                obj.select_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        for obj in previous_selected:
            try:
                obj.select_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            view_layer.objects.active = previous_active
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

def _frame_object_in_axis_view(
    area: bpy.types.Area,
    obj: bpy.types.Object,
    view_quaternion,
    margin: float = 1.08,
) -> bool:
    """Frame an object without invoking ``view_selected`` or smooth view.

    Running ``view_axis`` and ``view_selected`` back-to-back can start two
    smooth-view transitions.  Immediately after a screen split those
    transitions may overwrite one another, leaving the new editors in User
    Perspective.  This calculates the orthographic scale directly.
    """
    from mathutils import Quaternion, Vector

    if area is None or area.type != "VIEW_3D" or obj is None:
        return False
    region = _area_window_region(area)
    rv3d = getattr(area.spaces.active, "region_3d", None)
    if region is None or rv3d is None:
        return False
    try:
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        if not corners:
            return False
        center = sum(corners, Vector((0.0, 0.0, 0.0))) / float(len(corners))
        quat = Quaternion(view_quaternion)
        projected = [quat @ (corner - center) for corner in corners]
        half_x = max(abs(point.x) for point in projected)
        half_y = max(abs(point.y) for point in projected)

        width_px = max(1.0, float(region.width))
        height_px = max(1.0, float(region.height))
        if width_px >= height_px:
            distance = max(half_x, half_y * width_px / height_px)
        else:
            distance = max(half_y, half_x * height_px / width_px)

        rv3d.view_location = center
        rv3d.view_distance = max(distance * float(margin), 0.01)
        return True
    except Exception as exc:
        print("DICOM direct MPR framing error:", repr(exc))
        return False

def _configure_sagittal_z_editing(area: bpy.types.Area) -> None:
    """Expose only rotation editing and lock the sagittal plane to global Z."""
    plane = bpy.data.objects.get(PLANE_SPECS["SAGITTAL"]["object"])
    if plane is not None:
        try:
            plane.lock_rotation = (True, True, False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    if area is None or area.type != "VIEW_3D":
        return
    space = area.spaces.active
    try:
        space.show_gizmo = True
        space.show_gizmo_navigate = True
        space.show_gizmo_tool = False
        space.show_gizmo_object_translate = False
        space.show_gizmo_object_scale = False
        space.show_gizmo_object_rotate = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    area.tag_redraw()


def _restore_sagittal_rotation_locks(props) -> None:
    plane = bpy.data.objects.get(PLANE_SPECS["SAGITTAL"]["object"])
    if plane is None:
        return
    try:
        plane.lock_rotation = (
            bool(props.get("radiographic_sagittal_lock_x", False)),
            bool(props.get("radiographic_sagittal_lock_y", False)),
            bool(props.get("radiographic_sagittal_lock_z", False)),
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _configure_clinical_3d_editor(area: bpy.types.Area) -> None:
    _configure_clean_view3d_area(area, global_view=True)
    space = area.spaces.active
    rv3d = getattr(space, "region_3d", None)
    if rv3d is not None:
        target = bpy.data.objects.get(ROOT_NAME) or bpy.data.objects.get(BOUNDING_BOX_NAME)
        try:
            rv3d.lock_rotation = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        rv3d.view_perspective = "PERSP"
        rv3d.view_location = (
            target.matrix_world.translation.copy()
            if target is not None
            else Vector((0.0, 0.0, 0.0))
        )
        camera_world = (
            Matrix.Rotation(math.radians(58.0), 4, "X")
            @ Matrix.Rotation(math.radians(-42.0), 4, "Z")
        )
        rv3d.view_rotation = camera_world.to_quaternion().inverted()
        rv3d.view_distance = max(_dicom_volume_extent_mm() * 1.15, 1.0)
    _configure_sagittal_z_editing(area)
    area.tag_redraw()



def _configure_mpr_axis_view(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    area: bpy.types.Area,
    orientation: str,
) -> bool:
    """Configure one independent diagnostic viewport around its own plane.

    FRONT/RIGHT/TOP is requested exactly as with Numpad 1/3/7, then the final
    quaternion is taken from the actual MPR plane.  This preserves the same
    clinical axes even when the DICOM root contains patient-orientation data.
    Crucially, camera setup no longer depends on Local View succeeding first.
    """
    orientation = orientation.upper()
    view_type = MPR_VIEW_AXIS_TYPES[orientation]
    plane = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
    if plane is None or area is None:
        return False

    _configure_clean_view3d_area(area, global_view=False)
    region = _area_window_region(area)
    space = area.spaces.active
    rv3d = getattr(space, "region_3d", None)
    if region is None or rv3d is None:
        return False

    try:
        # First request Blender's native axis command so its internal axis-view
        # state behaves exactly like Numpad 7 / 1 / 3.
        view_preferences = getattr(bpy.context.preferences, "view", None)
        old_smooth = getattr(view_preferences, "smooth_view", None)
        try:
            if old_smooth is not None:
                view_preferences.smooth_view = 0
            with bpy.context.temp_override(
                window=window,
                screen=screen,
                area=area,
                region=region,
                scene=window.scene,
                view_layer=window.view_layer,
            ):
                bpy.ops.view3d.view_axis(
                    type=view_type,
                    align_active=False,
                    relative=False,
                )
        except Exception as exc:
            print(f"DICOM axis operator fallback {orientation}:", repr(exc))
        finally:
            if old_smooth is not None:
                try:
                    view_preferences.smooth_view = old_smooth
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

        # The plane matrix is authoritative.  It differs for axial, coronal and
        # sagittal and includes the DICOM patient's global orientation.
        expected_quaternion = plane.matrix_world.to_quaternion().normalized().inverted()
        rv3d.view_perspective = "ORTHO"
        rv3d.view_rotation = expected_quaternion
        if not _frame_object_in_axis_view(area, plane, expected_quaternion):
            return False
        try:
            rv3d.show_sync_view = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            rv3d.lock_rotation = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Isolation is attempted after the camera is already valid.  Therefore
        # a transient Local View failure can no longer leave every editor in the
        # same User Perspective.
        isolated = _set_diagnostic_mpr_local_visibility(
            window,
            screen,
            area,
            orientation,
            enabled=True,
        )
        if not isolated:
            print(f"DICOM warning: {orientation} camera configured; Local View pending")

        # Local View can alter the framing, so write the final values once more.
        rv3d.view_perspective = "ORTHO"
        rv3d.view_rotation = expected_quaternion
        _frame_object_in_axis_view(area, plane, expected_quaternion)
        try:
            rv3d.lock_rotation = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        area.tag_redraw()
        return (
            rv3d.view_perspective == "ORTHO"
            and abs(float(rv3d.view_rotation.dot(expected_quaternion))) > 0.9995
        )
    except Exception as exc:
        print(f"DICOM direct-axis MPR {orientation} error:", repr(exc))
        return False


def _schedule_mpr_viewport_configuration(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    role_pointers: dict[str, int],
    token: int,
) -> None:
    """Configure one viewport per UI tick, then verify the complete layout.

    View-axis and Local View operators modify global selection/context.  Running
    all four configurations in one timer callback allowed later operations to
    overwrite earlier editors.  A small state machine makes each area settle
    before the next one is touched.
    """
    phases = ["AXIAL", "CORONAL", "SAGITTAL", "VIEW_3D", "VERIFY"]
    state = {"phase_index": 0, "attempts": 10}

    def _next_step():
        props = getattr(getattr(window, "scene", None), "dicom_wizard_pro", None)
        if props is None or int(props.get("radiographic_layout_token", -1)) != token:
            return None
        if window.screen != screen:
            props["radiographic_building"] = False
            props.status = "La pantalla cambió mientras se orientaba el visor MPR"
            return None

        phase = phases[state["phase_index"]]
        try:
            if phase in ("AXIAL", "CORONAL", "SAGITTAL"):
                area = _area_from_pointer(screen, role_pointers[phase])
                ok = area is not None and _configure_mpr_axis_view(
                    window, screen, area, phase
                )
                if not ok:
                    state["attempts"] -= 1
                    if state["attempts"] > 0:
                        props.status = f"Ajustando vista {phase.lower()}…"
                        return 0.12
                    props["radiographic_building"] = False
                    props.status = f"No se pudo orientar la vista {phase.lower()}"
                    return None
                props.status = f"Vista {phase.lower()} fijada"
                state["phase_index"] += 1
                state["attempts"] = 10
                return 0.12

            if phase == "VIEW_3D":
                area = _area_from_pointer(screen, role_pointers["VIEW_3D"])
                ok = False
                if area is not None:
                    _configure_clinical_3d_editor(area)
                    ok = _set_global_mpr_local_visibility(
                        window, screen, area, enabled=True
                    )
                if not ok:
                    state["attempts"] -= 1
                    if state["attempts"] > 0:
                        props.status = "Ajustando vista 3D global…"
                        return 0.12
                    props["radiographic_building"] = False
                    props.status = "No se pudo aislar el plano sagital en la vista 3D"
                    return None
                state["phase_index"] += 1
                state["attempts"] = 10
                return 0.12

            global_area = _area_from_pointer(screen, role_pointers["VIEW_3D"])
            if global_area is None:
                raise RuntimeError("Se perdió la vista 3D global")
            region = _area_window_region(global_area)
            if region is None:
                raise RuntimeError("La vista 3D no tiene región WINDOW")
            with bpy.context.temp_override(
                window=window,
                screen=screen,
                area=global_area,
                region=region,
                scene=window.scene,
                view_layer=window.view_layer,
            ):
                verified, message = _verify_true_mpr_layout(
                    bpy.context, role_pointers
                )
            props["radiographic_building"] = False
            props.status = (
                f"Verificado: {message}"
                if verified
                else f"MPR creado; revisar aislamiento: {message}"
            )
            force_ui_redraw()
            return None
        except Exception as exc:
            print("DICOM sequential MPR configuration error:", repr(exc))
            state["attempts"] -= 1
            if state["attempts"] > 0:
                return 0.12
            props["radiographic_building"] = False
            props.status = f"Error orientando el visor MPR: {exc}"
            return None

    lifecycle.register_timer(_next_step, first_interval=0.12)

def _store_mpr_role_pointers(props, role_pointers: dict[str, int]) -> None:
    for role, pointer_value in role_pointers.items():
        props[f"radiographic_area_{role.lower()}"] = int(pointer_value)


def _schedule_true_mpr_layout_build(
    context: bpy.types.Context,
    token: int,
) -> bool:
    """Build the 2×2 editor grid one split per Blender UI tick.

    Screen layout operators rebuild ``screen.areas`` asynchronously.  The old
    implementation executed three splits in one operator call and immediately
    searched for the new Area, which is not reliable in Blender 5.1.  This
    state machine waits until each split is visible in the Screen RNA before
    requesting the next one.
    """
    window = context.window
    screen = context.screen
    source_area = context.area
    props = context.scene.dicom_wizard_pro
    if window is None or screen is None or source_area is None:
        return False

    source_rect = _area_rect(source_area)
    state = {
        "phase": "WAIT_COLUMNS",
        "source_rect": source_rect,
        "left_pointer": 0,
        "right_pointer": 0,
        "top_left_pointer": 0,
        "bottom_left_pointer": 0,
        "top_right_pointer": 0,
        "bottom_right_pointer": 0,
        "attempts": 50,
    }

    if not _request_screen_area_split(window, screen, source_area, "VERTICAL"):
        return False

    props["radiographic_building"] = True
    props.status = "Creando visor MPR: dividiendo en dos columnas…"

    def _retry_or_fail(message: str):
        state["attempts"] -= 1
        if state["attempts"] > 0:
            return 0.08
        props["radiographic_building"] = False
        props.status = f"No se pudo crear el visor MPR: {message}"
        print("DICOM MPR layout build error:", message)
        return None

    def _build_next_step():
        try:
            current_props = getattr(getattr(window, "scene", None), "dicom_wizard_pro", None)
            if current_props is None:
                return None
            if int(current_props.get("radiographic_layout_token", -1)) != token:
                return None
            if window.screen != screen:
                current_props["radiographic_building"] = False
                current_props.status = "La pantalla cambió mientras se creaba el visor MPR"
                return None

            phase = state["phase"]
            if phase == "WAIT_COLUMNS":
                columns = _two_columns_in_rect(screen, state["source_rect"])
                if columns is None:
                    return _retry_or_fail("la primera división no terminó")
                left, right = columns
                state["left_pointer"] = int(left.as_pointer())
                state["right_pointer"] = int(right.as_pointer())
                state["left_rect"] = _area_rect(left)
                state["right_rect"] = _area_rect(right)
                if not _request_screen_area_split(window, screen, left, "HORIZONTAL"):
                    return _retry_or_fail("Blender rechazó la división de la columna izquierda")
                state["phase"] = "WAIT_LEFT_ROWS"
                state["attempts"] = 50
                current_props.status = "Creando visor MPR: dividiendo la columna izquierda…"
                return 0.08

            if phase == "WAIT_LEFT_ROWS":
                rows = _two_rows_in_rect(screen, state["left_rect"])
                if rows is None:
                    return _retry_or_fail("la columna izquierda no terminó de dividirse")
                top_left, bottom_left = rows
                state["top_left_pointer"] = int(top_left.as_pointer())
                state["bottom_left_pointer"] = int(bottom_left.as_pointer())

                right = _area_from_pointer(screen, state["right_pointer"])
                if right is None:
                    columns = _two_columns_in_rect(screen, state["source_rect"])
                    right = columns[1] if columns is not None else None
                if right is None:
                    return _retry_or_fail("se perdió la columna derecha")
                state["right_pointer"] = int(right.as_pointer())
                state["right_rect"] = _area_rect(right)
                if not _request_screen_area_split(window, screen, right, "HORIZONTAL"):
                    return _retry_or_fail("Blender rechazó la división de la columna derecha")
                state["phase"] = "WAIT_RIGHT_ROWS"
                state["attempts"] = 50
                current_props.status = "Creando visor MPR: dividiendo la columna derecha…"
                return 0.08

            if phase == "WAIT_RIGHT_ROWS":
                rows = _two_rows_in_rect(screen, state["right_rect"])
                if rows is None:
                    return _retry_or_fail("la columna derecha no terminó de dividirse")
                top_right, bottom_right = rows
                state["top_right_pointer"] = int(top_right.as_pointer())
                state["bottom_right_pointer"] = int(bottom_right.as_pointer())

                top_left = _area_from_pointer(screen, state["top_left_pointer"])
                bottom_left = _area_from_pointer(screen, state["bottom_left_pointer"])
                if top_left is None or bottom_left is None:
                    left_rows = _two_rows_in_rect(screen, state["left_rect"])
                    if left_rows is None:
                        return _retry_or_fail("se perdieron las vistas de la columna izquierda")
                    top_left, bottom_left = left_rows

                four = (top_left, top_right, bottom_left, bottom_right)
                if len({int(area.as_pointer()) for area in four}) != 4:
                    return _retry_or_fail("Blender no expuso cuatro editores diferentes")

                for area in four:
                    _configure_clean_view3d_area(area, global_view=False)
                _configure_clinical_3d_editor(bottom_right)

                role_pointers = {
                    "AXIAL": int(top_left.as_pointer()),
                    "CORONAL": int(top_right.as_pointer()),
                    "SAGITTAL": int(bottom_left.as_pointer()),
                    "VIEW_3D": int(bottom_right.as_pointer()),
                }
                current_props["radiographic_split_active"] = True
                _store_mpr_role_pointers(current_props, role_pointers)
                current_props.status = "Cuatro viewports creados; orientando cada plano de forma independiente…"
                _schedule_mpr_viewport_configuration(
                    window,
                    screen,
                    role_pointers,
                    token,
                )
                return None

            return None
        except Exception as exc:
            current_props = getattr(getattr(window, "scene", None), "dicom_wizard_pro", None)
            if current_props is not None:
                current_props["radiographic_building"] = False
                current_props.status = f"Error creando visor MPR: {exc}"
            print("DICOM asynchronous MPR layout error:", repr(exc))
            return None

    lifecycle.register_timer(_build_next_step, first_interval=0.08)
    return True


def _verify_true_mpr_layout(
    context: bpy.types.Context,
    role_pointers: dict[str, int],
) -> tuple[bool, str]:
    """Verify four real viewports and the Z/Y/X MPR plane assignment."""
    screen = context.screen
    props = context.scene.dicom_wizard_pro
    if screen is None:
        return False, "No existe la pantalla activa"

    from mathutils import Quaternion

    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        area = _area_from_pointer(screen, role_pointers.get(orientation, 0))
        if area is None or area.type != "VIEW_3D":
            return False, f"La vista {orientation} no es un viewport 3D independiente"
        space = area.spaces.active
        rv3d = getattr(space, "region_3d", None)
        if rv3d is None:
            return False, f"La vista {orientation} no tiene RegionView3D"
        target = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if target is None:
            return False, f"No existe el plano {orientation}"
        expected = target.matrix_world.to_quaternion().normalized().inverted()
        if rv3d.view_perspective != "ORTHO":
            return False, f"La vista {orientation} no está en ortográfica"
        if abs(float(rv3d.view_rotation.dot(expected))) < 0.9995:
            return False, f"La cámara {orientation} no mira perpendicularmente a su plano"
        if getattr(space, "local_view", None) is None:
            return False, f"La vista {orientation} no pudo aislar su plano"
        target = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if target is None:
            return False, f"No existe el plano {orientation}"
        try:
            if not target.local_view_get(space):
                return False, f"El plano {orientation} no está visible en su viewport"
            for other in ("AXIAL", "CORONAL", "SAGITTAL"):
                if other == orientation:
                    continue
                other_obj = bpy.data.objects.get(PLANE_SPECS[other]["object"])
                if other_obj is not None and other_obj.local_view_get(space):
                    return False, f"El plano {other} invade la vista {orientation}"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    global_area = _area_from_pointer(screen, role_pointers.get("VIEW_3D", 0))
    if global_area is None or global_area.type != "VIEW_3D":
        return False, "La cuarta vista no es un viewport 3D global"
    global_space = global_area.spaces.active
    if getattr(global_space, "local_view", None) is None:
        return False, "La vista 3D no pudo aislar el plano sagital"
    axial_obj = bpy.data.objects.get(PLANE_SPECS["AXIAL"]["object"])
    coronal_obj = bpy.data.objects.get(PLANE_SPECS["CORONAL"]["object"])
    sagittal_obj = bpy.data.objects.get(PLANE_SPECS["SAGITTAL"]["object"])
    try:
        if axial_obj is not None and axial_obj.local_view_get(global_space):
            return False, "El plano axial sigue visible en la vista 3D"
        if coronal_obj is not None and coronal_obj.local_view_get(global_space):
            return False, "El plano coronal sigue visible en la vista 3D"
        if sagittal_obj is None or not sagittal_obj.local_view_get(global_space):
            return False, "El plano sagital no está visible en la vista 3D"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Check that the cutting planes themselves remain orthogonal and mapped to
    # the clinically intended source axes before the viewport commands run.
    alignment = _mpr_alignment_matrix(props)
    expected_normals = {
        "AXIAL": alignment @ _base_plane_frame("AXIAL")[:, 2],
        "CORONAL": alignment @ _base_plane_frame("CORONAL")[:, 2],
        "SAGITTAL": alignment @ _base_plane_frame("SAGITTAL")[:, 2],
    }
    for orientation, expected in expected_normals.items():
        _obj, _center, _u, _v, actual, _width, _height = _plane_pose_from_object(orientation)
        if abs(float(load_numpy().dot(actual, expected))) < 0.999:
            return False, f"El plano {orientation} no está bloqueado a su eje anatómico"

    return True, (
        "Axial=TOP/Num7 · Coronal=FRONT/Num1 · Sagital=RIGHT/Num3 · "
        "3D: solo sagital, giro Z"
    )



def _join_screen_areas(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    source: bpy.types.Area,
    target: bpy.types.Area,
) -> bool:
    """Join two adjacent areas while keeping ``source`` alive.

    Blender's current implementation deletes the area supplied as ``target_xy``
    and preserves ``source_xy``.  The previous helper assumed the opposite,
    which deleted the intended 3D editor and invalidated all following pointers.
    """
    if source is None or target is None or source == target:
        return False
    region = _area_window_region(source)
    try:
        override = dict(window=window, screen=screen, area=source)
        if region is not None:
            override["region"] = region
        with bpy.context.temp_override(**override):
            result = bpy.ops.screen.area_join(
                source_xy=_area_center_xy(source),
                target_xy=_area_center_xy(target),
            )
        return "FINISHED" in result
    except Exception as exc:
        print("DICOM area join error:", repr(exc))
        return False

def _close_area_fallback(
    window: bpy.types.Window,
    screen: bpy.types.Screen,
    area: bpy.types.Area,
) -> bool:
    region = _area_window_region(area)
    if region is None:
        return False
    try:
        with bpy.context.temp_override(
            window=window,
            screen=screen,
            area=area,
            region=region,
        ):
            result = bpy.ops.screen.area_close()
        return "FINISHED" in result
    except Exception as exc:
        print("DICOM area close fallback error:", repr(exc))
        return False



def _restore_true_mpr_layout(context: bpy.types.Context, props) -> bool:
    """Compatibility wrapper: schedule a reliable asynchronous close."""
    token = int(props.get("radiographic_layout_token", 0))
    return _schedule_true_mpr_layout_close(context, props, token)


def _area_containing_point(
    screen: bpy.types.Screen,
    point: tuple[int, int],
) -> bpy.types.Area | None:
    px, py = point
    for area in screen.areas:
        if area.x <= px < area.x + area.width and area.y <= py < area.y + area.height:
            return area
    return None


def _schedule_true_mpr_layout_close(
    context: bpy.types.Context,
    props,
    token: int,
) -> bool:
    """Collapse the 2×2 grid in reverse order, one join per UI tick.

    Screen joins rebuild ``screen.areas`` just like splits.  Performing three
    joins synchronously left stale Area pointers and therefore only the first
    join happened.  The global bottom-right editor is now always the source so
    it survives all the way back to one 3D viewport.
    """
    window = context.window
    screen = context.screen
    if window is None or screen is None:
        return False

    role_pointers = {
        role: int(props.get(f"radiographic_area_{role.lower()}", 0))
        for role in ("AXIAL", "CORONAL", "SAGITTAL", "VIEW_3D")
    }
    areas = {
        role: _area_from_pointer(screen, pointer)
        for role, pointer in role_pointers.items()
    }
    if any(area is None for area in areas.values()):
        return False

    global_area = areas["VIEW_3D"]
    global_seed = _area_center_xy(global_area)
    left_seed = _area_center_xy(areas["SAGITTAL"])
    all_rects = [_area_rect(area) for area in areas.values()]
    min_x = min(rect[0] for rect in all_rects)
    min_y = min(rect[1] for rect in all_rects)
    max_x = max(rect[0] + rect[2] for rect in all_rects)
    max_y = max(rect[1] + rect[3] for rect in all_rects)
    full_rect = (min_x, min_y, max_x - min_x, max_y - min_y)

    # The global editor must leave Local View before it becomes the survivor.
    _set_global_mpr_local_visibility(
        window, screen, global_area, enabled=False
    )
    props["radiographic_building"] = True
    props.status = "Cerrando MPR: restaurando la vista 3D…"

    state = {"phase": "JOIN_RIGHT", "attempts": 40}

    def _retry(message: str):
        state["attempts"] -= 1
        if state["attempts"] > 0:
            return 0.08
        props["radiographic_building"] = False
        props.status = f"No se pudo cerrar MPR: {message}"
        return None

    def _finish():
        previous_show_all = bool(props.get("radiographic_previous_show_all_planes", False))
        previous_show_planes = bool(props.get("radiographic_previous_show_planes", True))
        _restore_sagittal_rotation_locks(props)
        RUNTIME.update_lock = True
        try:
            props.show_all_planes = previous_show_all
            props.show_planes = previous_show_planes
        finally:
            RUNTIME.update_lock = False
        update_visibility(bpy.context)
        props["radiographic_split_active"] = False
        props["radiographic_building"] = False
        for role in ("axial", "coronal", "sagittal", "view_3d"):
            try:
                del props[f"radiographic_area_{role}"]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        props.status = "Visor MPR cerrado; vista 3D restaurada"
        force_ui_redraw()
        return None

    def _close_next_step():
        try:
            current_props = getattr(getattr(window, "scene", None), "dicom_wizard_pro", None)
            if current_props is None:
                return None
            if int(current_props.get("radiographic_layout_token", -1)) != token:
                return None
            if window.screen != screen:
                current_props["radiographic_building"] = False
                current_props.status = "La pantalla cambió mientras se cerraba MPR"
                return None

            phase = state["phase"]
            if phase == "JOIN_RIGHT":
                source = _area_containing_point(screen, global_seed)
                target = _area_from_pointer(screen, role_pointers["CORONAL"])
                if source is None or target is None:
                    return _retry("no se encontraron las vistas derechas")
                if not _join_screen_areas(window, screen, source, target):
                    return _retry("Blender rechazó la unión de la columna derecha")
                state["phase"] = "WAIT_RIGHT"
                state["attempts"] = 40
                return 0.08

            if phase == "WAIT_RIGHT":
                source = _area_containing_point(screen, global_seed)
                if source is None or source.height < full_rect[3] * 0.85:
                    return _retry("la columna derecha no terminó de unirse")
                # Join the left column, keeping sagittal as its temporary survivor.
                sagittal = _area_containing_point(screen, left_seed)
                axial = _area_from_pointer(screen, role_pointers["AXIAL"])
                if sagittal is None or axial is None:
                    return _retry("no se encontraron las vistas izquierdas")
                if not _join_screen_areas(window, screen, sagittal, axial):
                    return _retry("Blender rechazó la unión de la columna izquierda")
                state["phase"] = "WAIT_LEFT"
                state["attempts"] = 40
                return 0.08

            if phase == "WAIT_LEFT":
                global_survivor = _area_containing_point(screen, global_seed)
                left_survivor = _area_containing_point(screen, left_seed)
                if global_survivor is None or left_survivor is None:
                    return _retry("las columnas no se estabilizaron")
                if global_survivor == left_survivor:
                    return _finish()
                if global_survivor.height < full_rect[3] * 0.85 or left_survivor.height < full_rect[3] * 0.85:
                    return _retry("las columnas aún no ocupan toda la altura")
                if not _join_screen_areas(window, screen, global_survivor, left_survivor):
                    return _retry("Blender rechazó la unión final")
                state["phase"] = "WAIT_FINAL"
                state["attempts"] = 40
                return 0.08

            if phase == "WAIT_FINAL":
                survivor = _area_containing_point(screen, global_seed)
                if survivor is None:
                    return _retry("se perdió la vista 3D superviviente")
                rect = _area_rect(survivor)
                if not _rect_contains(full_rect, rect, tolerance=16) or rect[2] < full_rect[2] * 0.85:
                    return _retry("la unión final no terminó")
                _configure_clean_view3d_area(survivor, global_view=True)
                return _finish()
            return None
        except Exception as exc:
            print("DICOM asynchronous MPR close error:", repr(exc))
            return _retry(str(exc))

    lifecycle.register_timer(_close_next_step, first_interval=0.08)
    return True


# =============================================================================
# SAFE NATIVE QUAD-VIEW MPR (v1.4.4)
# =============================================================================
# Previous versions dynamically split and re-joined Screen.areas from timers.
# That is fragile because those UI topology changes can overlap Blender's
# memfile undo system.  This implementation never creates or destroys Areas.
# It uses Blender's native region_quadview inside one VIEW_3D area and draws
# the three MPR images directly in the three orthographic sub-regions.

_SAFE_MPR_DRAW_HANDLE = None
_SAFE_MPR_OWNER_AREA_POINTER = 0


def _safe_mpr_props(context=None):
    scene = None
    if context is not None:
        scene = getattr(context, "scene", None)
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "dicom_wizard_pro", None) if scene is not None else None


def _safe_mpr_window_regions(area):
    """Return the four quad-view WINDOW regions sorted by screen position."""
    if area is None or area.type != "VIEW_3D":
        return []
    regions = [
        region for region in area.regions
        if region.type == "WINDOW" and getattr(region, "data", None) is not None
    ]
    if len(regions) != 4:
        return []
    # Top row first, then left to right. Blender region y is bottom-origin.
    return sorted(regions, key=lambda r: (-int(r.y + r.height * 0.5), int(r.x + r.width * 0.5)))


def _safe_mpr_region_roles(area):
    regions = _safe_mpr_window_regions(area)
    if len(regions) != 4:
        return {}
    return {
        "AXIAL": regions[0],
        "CORONAL": regions[1],
        "SAGITTAL": regions[2],
        "VIEW_3D": regions[3],
    }


def _safe_mpr_store_region_roles(props, area):
    """Store process-sized UI pointers without overflowing Blender ID properties.

    ``as_pointer()`` returns a 64-bit address on 64-bit Blender builds, while an
    ID-property integer may be converted through a signed C int. Strings retain
    the complete address and remain safely convertible with ``int(...)``.
    """
    roles = _safe_mpr_region_roles(area)
    if len(roles) != 4:
        return False
    props["safe_mpr_area_pointer"] = str(int(area.as_pointer()))
    for role, region in roles.items():
        props[f"safe_mpr_region_{role.lower()}"] = str(int(region.as_pointer()))
    return True


def _safe_mpr_role_for_region(props, region):
    if props is None or region is None:
        return None
    pointer = int(region.as_pointer())
    for role in ("AXIAL", "CORONAL", "SAGITTAL", "VIEW_3D"):
        if int(props.get(f"safe_mpr_region_{role.lower()}", 0)) == pointer:
            return role
    return None


def _safe_mpr_find_owner_area(context=None):
    global _SAFE_MPR_OWNER_AREA_POINTER
    window = getattr(context, "window", None) if context is not None else None
    if window is None:
        window = getattr(bpy.context, "window", None)
    screen = getattr(window, "screen", None) if window is not None else None
    if screen is None:
        return None
    pointer = int(_SAFE_MPR_OWNER_AREA_POINTER)
    if not pointer:
        props = _safe_mpr_props(context)
        pointer = int(props.get("safe_mpr_area_pointer", 0)) if props is not None else 0
    return next((a for a in screen.areas if int(a.as_pointer()) == pointer), None)


def _safe_mpr_configure_regions(area):
    """Assign exact Numpad 7/1/3 views plus a free perspective region."""
    from mathutils import Quaternion, Vector

    roles = _safe_mpr_region_roles(area)
    if len(roles) != 4:
        return False
    extent = max(10.0, float(_dicom_volume_extent_mm()))
    rotations = {
        "AXIAL": Quaternion((1.0, 0.0, 0.0, 0.0)),
        "CORONAL": Quaternion((0.7071067811865476, -0.7071067811865476, 0.0, 0.0)),
        "SAGITTAL": Quaternion((0.5, -0.5, -0.5, -0.5)),
    }
    for role in ("AXIAL", "CORONAL", "SAGITTAL"):
        rv3d = roles[role].data
        rv3d.view_perspective = "ORTHO"
        rv3d.view_rotation = rotations[role]
        rv3d.view_location = Vector((0.0, 0.0, 0.0))
        rv3d.view_distance = extent * 0.72

    global_rv3d = roles["VIEW_3D"].data
    global_rv3d.view_perspective = "PERSP"
    global_rv3d.view_location = Vector((0.0, 0.0, 0.0))
    global_rv3d.view_distance = extent * 1.15

    space = area.spaces.active
    try:
        space.overlay.show_floor = False
        space.overlay.show_cursor = False
        space.overlay.show_stats = False
        space.overlay.show_text = True
        space.show_region_ui = False
        space.show_region_toolbar = False
        space.clip_start = 0.05
        space.clip_end = max(10000.0, extent * 20.0)
        space.shading.type = "MATERIAL"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    area.tag_redraw()
    return True


def _safe_mpr_save_object_visibility(props):
    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        obj = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if obj is None:
            continue
        key = orientation.lower()
        props[f"safe_mpr_{key}_hide_viewport"] = bool(obj.hide_viewport)
        props[f"safe_mpr_{key}_hide_select"] = bool(obj.hide_select)
        try:
            props[f"safe_mpr_{key}_hide_get"] = bool(obj.hide_get())
        except Exception:
            props[f"safe_mpr_{key}_hide_get"] = False

    surface = bpy.data.objects.get(str(props.generated_surface_name))
    if surface is not None:
        props["safe_mpr_surface_hide_select"] = bool(surface.hide_select)


def _safe_mpr_apply_global_visibility(props):
    """Global 3D shows volume + sagittal; 2D images are GPU overlays."""
    for orientation in ("AXIAL", "CORONAL"):
        obj = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if obj is not None:
            obj.hide_viewport = True
            try:
                obj.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    sagittal = bpy.data.objects.get(PLANE_SPECS["SAGITTAL"]["object"])
    if sagittal is not None:
        sagittal.hide_viewport = False
        try:
            sagittal.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        sagittal.lock_rotation[0] = True
        sagittal.lock_rotation[1] = True
        sagittal.lock_rotation[2] = False


def _safe_mpr_apply_two_plane_visibility(props) -> None:
    """Display axial-Z and sagittal-X image planes plus any optional mesh context."""
    volume = bpy.data.objects.get(VOLUME_OBJECT_NAME)
    if volume is not None:
        volume.hide_viewport = True
        volume.hide_render = True
        try:
            volume.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    for orientation in ("AXIAL", "SAGITTAL"):
        obj = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if obj is None:
            continue
        obj.hide_viewport = False
        obj.hide_render = False
        try:
            obj.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        obj.lock_rotation[0] = True
        obj.lock_rotation[1] = True
        obj.lock_rotation[2] = True
        obj.hide_select = True

    coronal = bpy.data.objects.get(PLANE_SPECS["CORONAL"]["object"])
    if coronal is not None:
        coronal.hide_viewport = True
        coronal.hide_render = True
        try:
            coronal.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    surface = bpy.data.objects.get(str(props.generated_surface_name))
    if surface is not None:
        surface.hide_viewport = False
        surface.hide_render = False
        surface.hide_select = True
        try:
            surface.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _apply_dicom_surface_transparency(bpy.context, props)


def _safe_mpr_restore_object_visibility(props):
    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        obj = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
        if obj is None:
            continue
        key = orientation.lower()
        obj.hide_viewport = bool(
            props.get(f"safe_mpr_{key}_hide_viewport", False)
        )
        obj.hide_select = bool(
            props.get(f"safe_mpr_{key}_hide_select", False)
        )
        try:
            obj.hide_set(
                bool(props.get(f"safe_mpr_{key}_hide_get", False))
            )
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    surface = bpy.data.objects.get(str(props.generated_surface_name))
    if surface is not None:
        surface.hide_select = bool(
            props.get("safe_mpr_surface_hide_select", False)
        )
    _restore_sagittal_rotation_locks(props)


def _safe_draw_uniform_rect(shader, batch_for_shader, x0, y0, x1, y1, color):
    batch = batch_for_shader(
        shader,
        "TRI_FAN",
        {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))},
    )
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _safe_mpr_draw_callback():
    """Draw one independent MPR image and one axis slider per quad region."""
    props = _safe_mpr_props()
    if props is None or not bool(props.get("safe_mpr_active", False)):
        return
    area = getattr(bpy.context, "area", None)
    region = getattr(bpy.context, "region", None)
    if area is None or region is None or area.type != "VIEW_3D":
        return
    if int(area.as_pointer()) != int(props.get("safe_mpr_area_pointer", 0)):
        return
    role = _safe_mpr_role_for_region(props, region)
    if role not in ("AXIAL", "CORONAL", "SAGITTAL"):
        return

    image = bpy.data.images.get(PLANE_SPECS[role]["image"])
    if image is None or image.size[0] <= 0 or image.size[1] <= 0:
        return

    try:
        import gpu
        import blf
        from gpu_extras.batch import batch_for_shader

        width = max(1, int(region.width))
        height = max(1, int(region.height))
        slider_h = 34.0
        content_h = max(1.0, height - slider_h)

        uniform = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")
        _safe_draw_uniform_rect(uniform, batch_for_shader, 0.0, 0.0, float(width), float(height), (0.015, 0.015, 0.015, 1.0))

        iw, ih = float(image.size[0]), float(image.size[1])
        scale = min(width / max(iw, 1.0), content_h / max(ih, 1.0))
        dw, dh = iw * scale, ih * scale
        x0 = (width - dw) * 0.5
        y0 = slider_h + (content_h - dh) * 0.5
        x1, y1 = x0 + dw, y0 + dh

        texture = gpu.texture.from_image(image)
        shader = gpu.shader.from_builtin("IMAGE")
        batch = batch_for_shader(
            shader,
            "TRI_FAN",
            {
                "pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                "texCoord": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            },
        )
        shader.bind()
        shader.uniform_sampler("image", texture)
        batch.draw(shader)

        spec = MPR_SLIDER_SPECS[role]
        percent = float(getattr(props, spec["property"]))
        slice_number, slice_total, position_mm = _mpr_slice_readout(role, percent)
        bar_x0, bar_x1 = 22.0, max(23.0, width - 22.0)
        bar_y = 14.0
        _safe_draw_uniform_rect(uniform, batch_for_shader, bar_x0, bar_y - 2.0, bar_x1, bar_y + 2.0, (0.55, 0.55, 0.55, 0.9))
        knob_x = bar_x0 + (bar_x1 - bar_x0) * clamp(percent, 0.0, 100.0) / 100.0
        _safe_draw_uniform_rect(uniform, batch_for_shader, knob_x - 5.0, bar_y - 7.0, knob_x + 5.0, bar_y + 7.0, (0.95, 0.95, 0.95, 1.0))

        font_id = 0
        blf.size(font_id, 13)
        blf.color(font_id, 1.0, 1.0, 1.0, 0.95)
        blf.position(font_id, 10.0, height - 20.0, 0.0)
        numpad = {"AXIAL": "7", "CORONAL": "1", "SAGITTAL": "3"}[role]
        blf.draw(font_id, f"{spec['short_label']} · EJE {spec['axis']} · NUM {numpad}")
        readout = f"{slice_number}/{slice_total}   {position_mm:+.1f} mm"
        text_w, _ = blf.dimensions(font_id, readout)
        blf.position(font_id, max(8.0, width - text_w - 10.0), 7.0, 0.0)
        blf.draw(font_id, readout)
    except Exception as exc:
        # Draw callbacks must never propagate exceptions into Blender's UI loop.
        print("DICOM safe MPR draw error:", repr(exc))
    finally:
        try:
            import gpu
            gpu.state.blend_set("NONE")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _safe_mpr_add_draw_handler():
    global _SAFE_MPR_DRAW_HANDLE
    if _SAFE_MPR_DRAW_HANDLE is None:
        _SAFE_MPR_DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _safe_mpr_draw_callback, (), "WINDOW", "POST_PIXEL"
        )


def _safe_mpr_remove_draw_handler():
    global _SAFE_MPR_DRAW_HANDLE
    if _SAFE_MPR_DRAW_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_SAFE_MPR_DRAW_HANDLE, "WINDOW")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _SAFE_MPR_DRAW_HANDLE = None


def _safe_mpr_native_quad_active(area):
    """Return True only when this VIEW_3D space owns four native quad regions."""
    if area is None or area.type != "VIEW_3D":
        return False
    try:
        return len(area.spaces.active.region_quadviews) == 4
    except Exception:
        return False


def _safe_mpr_pick_toggle_region(area, props, enable):
    """Pick the concrete WINDOW region required by SCREEN_OT_region_quadview.

    Blender enters Quad View only from the last normal WINDOW region. To leave
    Quad View, the operator must receive one of the actual QSPLIT regions, not
    an arbitrary WINDOW region from the area.
    """
    if area is None or area.type != "VIEW_3D":
        return None

    windows = [
        region for region in area.regions
        if region.type == "WINDOW" and getattr(region, "data", None) is not None
    ]
    if not windows:
        return None

    if enable:
        # Blender's C operator rejects entry unless the selected region is the
        # last region in the area's internal region list.
        return windows[-1]

    # Prefer the 3D quadrant stored when the MPR was opened. It is guaranteed
    # to be one of the native QSPLIT regions. Fall back to any exposed quad
    # region if the stored pointer became stale.
    preferred_pointer = int(props.get("safe_mpr_region_view_3d", 0)) if props is not None else 0
    if preferred_pointer:
        for region in windows:
            if int(region.as_pointer()) == preferred_pointer:
                return region

    quad_regions = _safe_mpr_window_regions(area)
    return quad_regions[-1] if quad_regions else windows[-1]


def _safe_mpr_toggle_native_quad(context, area, enable):
    """Toggle Blender's native Ctrl+Alt+Q Quad View in a verified context."""
    if area is None or area.type != "VIEW_3D":
        return False

    enable = bool(enable)
    current_quad = _safe_mpr_native_quad_active(area)
    if current_quad == enable:
        return True

    props = _safe_mpr_props(context)
    region = _safe_mpr_pick_toggle_region(area, props, enable)
    if region is None:
        return False

    window = getattr(context, "window", None) or getattr(bpy.context, "window", None)
    screen = getattr(window, "screen", None) if window is not None else None
    space = area.spaces.active
    region_data = getattr(region, "data", None)

    try:
        override = {
            "window": window,
            "screen": screen,
            "area": area,
            "region": region,
            "space_data": space,
        }
        if region_data is not None:
            override["region_data"] = region_data
        with context.temp_override(**override):
            result = bpy.ops.screen.region_quadview()

        # The operator changes regions synchronously. Verify the resulting
        # state instead of trusting FINISHED alone.
        changed = _safe_mpr_native_quad_active(area) == enable
        if not changed:
            print("DICOM native quad-view toggle returned", result, "but state did not change")
        return "FINISHED" in result and changed
    except Exception as exc:
        print("DICOM native quad-view toggle error:", repr(exc))
        return False


def _resolve_or_recover_mpr_surface(context, *, mutate_state=True):
    """Return an optional mesh used only as 3D context during MPR.

    v9.2.66 self-heals stale ``generated_surface_name`` / ``surface_ready``
    when a surface exists, but radiographic review no longer depends on one.
    The diagnostic planes are generated directly from the loaded DICOM volume.
    """
    props = getattr(context.scene, 'dicom_wizard_pro', None)
    if props is None:
        return None

    names = []
    current = str(getattr(props, 'generated_surface_name', '') or '')
    if current:
        names.append(current)

    scene = context.scene
    for key in ('DSG_maxilla_object', 'DSG_mandible_object'):
        value = str(scene.get(key, '') or '')
        if value:
            names.append(value)
    names.extend((NAME_DICOM_MAXILLA, NAME_DICOM_MANDIBLE))

    # Alignment composite is an acceptable visual/framing surface if a dual
    # segmentation path removed or renamed the old generated_surface object.
    try:
        from . import cbct_dental_module
        names.append(str(getattr(cbct_dental_module, 'ALIGNMENT_COMPOSITE_NAME', '') or ''))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    seen = set()
    for name in names:
        name = str(name or '')
        if not name or name in seen:
            continue
        seen.add(name)
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != 'MESH' or getattr(obj, 'data', None) is None:
            continue
        try:
            if len(obj.data.vertices) < 3:
                continue
        except Exception:
            continue
        if mutate_state:
            try:
                props.generated_surface_name = obj.name
                props.surface_ready = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return obj

    # Last-resort semantic recovery: if native dental objects exist, build the
    # already-defined alignment composite. This remains surface-only and does
    # not reload/resegment the DICOM.
    try:
        from . import cbct_dental_module
        teeth = cbct_dental_module.dentition_objects(context)
        if teeth:
            obj = cbct_dental_module.ensure_segmented_alignment_composite(context)
            if obj is not None and obj.type == 'MESH':
                if mutate_state:
                    props.generated_surface_name = obj.name
                    props.surface_ready = True
                return obj
    except Exception as exc:
        print('[DSG MPR] semantic surface recovery failed:', repr(exc))
    return None


def _safe_mpr_open(context):
    """Open DICOM MPR from voxel data, with optional mesh context and movable Z/X planes."""
    global _SAFE_MPR_OWNER_AREA_POINTER

    props = context.scene.dicom_wizard_pro
    area = getattr(context, "area", None)
    if area is None or area.type != "VIEW_3D":
        return False, "Abre la revisión desde un Viewport 3D"
    if bool(props.get("safe_mpr_active", False)):
        return True, "La revisión por planos ya está abierta"

    # The radiographic images are resampled from the loaded volume itself. A
    # polygonal surface is optional context, not a prerequisite for MPR.
    surface = _resolve_or_recover_mpr_surface(context, mutate_state=True)

    # Recover cleanly if a previous add-on build left native Quad View active.
    if _safe_mpr_native_quad_active(area):
        if not _safe_mpr_toggle_native_quad(context, area, False):
            return False, "No se pudo cerrar la antigua vista cuádruple"

    props["safe_mpr_previous_show_volume"] = bool(props.show_volume)
    props["safe_mpr_previous_show_planes"] = bool(props.show_planes)
    props["safe_mpr_previous_show_all_planes"] = bool(props.show_all_planes)
    props["safe_mpr_previous_show_box"] = bool(props.show_box)
    props["safe_mpr_previous_active_plane"] = str(props.active_plane)

    space = area.spaces.active
    props["safe_mpr_previous_region_ui"] = bool(space.show_region_ui)
    props["safe_mpr_previous_region_toolbar"] = bool(space.show_region_toolbar)
    props["safe_mpr_previous_shading_type"] = str(space.shading.type)
    props["safe_mpr_previous_color_type"] = str(space.shading.color_type)
    props["safe_mpr_previous_light"] = str(space.shading.light)

    _safe_mpr_save_object_visibility(props)
    _prepare_minimal_orthogonal_mpr(context)

    # Cancel any generic transform refresh left by an earlier interaction.
    RUNTIME.pending_transform_orientations.clear()
    RUNTIME.final_transform_orientations.clear()

    # Build new immutable images while the review planes are still hidden.
    for orientation in ("AXIAL", "SAGITTAL"):
        _SAFE_REVIEW_REFRESH_GENERATION[orientation] += 1
        _SAFE_REVIEW_TIMER_RUNNING[orientation] = False
        _SAFE_REVIEW_PREVIEW_GENERATION[orientation] = -1
        _SAFE_REVIEW_FINAL_GENERATION[orientation] = -1
        _safe_review_refresh_plane_image(
            context,
            orientation,
            max_axis=SAFE_REVIEW_MAX_AXIS,
        )

    RUNTIME.update_lock = True
    try:
        props.show_volume = False
        props.show_planes = True
        props.show_all_planes = False
        props.show_box = False
        props.active_plane = "AXIAL"

        # Removed controls are forced to their neutral values.
        props.axial_rotate_x = 0.0
        props.axial_rotate_y = 0.0
        props.sagittal_move_x = 50.0
        props.sagittal_rotate_y = 0.0
    finally:
        RUNTIME.update_lock = False

    # Apply the neutralized transforms before showing/rebuilding the planes.
    _apply_axis_controls_to_plane(
        context,
        "AXIAL",
        schedule_refresh=False,
    )
    _apply_axis_controls_to_plane(
        context,
        "SAGITTAL",
        schedule_refresh=False,
    )

    _safe_mpr_apply_two_plane_visibility(props)

    for selected in list(context.selected_objects):
        try:
            selected.select_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        context.view_layer.objects.active = None
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        # Workbench Texture avoids EEVEE's parallel material-image sync path.
        space.shading.type = "SOLID"
        space.shading.color_type = "TEXTURE"
        space.shading.light = "FLAT"
        space.shading.show_shadows = False
        space.shading.show_cavity = False
        space.overlay.show_floor = False
        space.overlay.show_cursor = False
        space.overlay.show_stats = False
        space.show_region_ui = False
        space.show_region_toolbar = False
        space.clip_start = 0.05
        space.clip_end = max(10000.0, _dicom_volume_extent_mm() * 20.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    props["safe_mpr_area_pointer"] = str(int(area.as_pointer()))
    props["safe_mpr_active"] = True
    props.realtime_mpr = True
    for orientation in ("AXIAL", "SAGITTAL"):
        _SAFE_REVIEW_LAST_CHANGE_TIME[orientation] = 0.0
        _SAFE_REVIEW_LAST_PREVIEW_TIME[orientation] = 0.0
        _SAFE_REVIEW_PREVIEW_GENERATION[orientation] = -1
        _SAFE_REVIEW_FINAL_GENERATION[orientation] = int(
            _SAFE_REVIEW_REFRESH_GENERATION.get(orientation, 0)
        )
        _SAFE_REVIEW_TIMER_RUNNING[orientation] = False
    props["safe_mpr_token"] = int(props.get("safe_mpr_token", 0)) + 1
    props["mpr_move_role"] = ""
    props["mpr_rotate_role"] = ""
    _SAFE_MPR_OWNER_AREA_POINTER = int(area.as_pointer())

    _safe_mpr_remove_draw_handler()
    props.status = "Revisión 3D · Posición Z e Inclinación Z"
    area.tag_redraw()
    force_ui_redraw()
    return True, props.status


def _safe_mpr_close(context):
    """Leave the single-view review and restore the previous viewer state."""
    global _SAFE_MPR_OWNER_AREA_POINTER

    props = context.scene.dicom_wizard_pro
    area = _safe_mpr_find_owner_area(context)
    if area is None:
        candidate = getattr(context, "area", None)
        if candidate is not None and candidate.type == "VIEW_3D":
            area = candidate

    if area is None or area.type != "VIEW_3D":
        message = "No se encontró el Viewport 3D de revisión"
        props.status = message
        return False, message

    props["safe_mpr_active"] = False
    props["mpr_move_role"] = ""
    props["mpr_rotate_role"] = ""
    for orientation in ("AXIAL", "SAGITTAL"):
        _SAFE_REVIEW_REFRESH_GENERATION[orientation] += 1
    RUNTIME.pending_transform_orientations.clear()
    RUNTIME.final_transform_orientations.clear()
    _safe_mpr_remove_draw_handler()
    _safe_mpr_restore_object_visibility(props)

    RUNTIME.update_lock = True
    try:
        props.show_volume = bool(
            props.get("safe_mpr_previous_show_volume", False)
        )
        props.show_planes = bool(
            props.get("safe_mpr_previous_show_planes", False)
        )
        props.show_all_planes = bool(
            props.get("safe_mpr_previous_show_all_planes", False)
        )
        props.show_box = bool(
            props.get("safe_mpr_previous_show_box", False)
        )
        previous_active = str(
            props.get("safe_mpr_previous_active_plane", "AXIAL")
        )
        if previous_active in PLANE_SPECS:
            props.active_plane = previous_active
    finally:
        RUNTIME.update_lock = False

    update_visibility(context)

    try:
        space = area.spaces.active
        space.show_region_ui = bool(
            props.get("safe_mpr_previous_region_ui", True)
        )
        space.show_region_toolbar = bool(
            props.get("safe_mpr_previous_region_toolbar", True)
        )
        previous_type = str(
            props.get("safe_mpr_previous_shading_type", "SOLID")
        )
        previous_color = str(
            props.get("safe_mpr_previous_color_type", "MATERIAL")
        )
        previous_light = str(
            props.get("safe_mpr_previous_light", "STUDIO")
        )
        if previous_type in {"WIREFRAME", "SOLID", "MATERIAL", "RENDERED"}:
            space.shading.type = previous_type
        if previous_color in {
            "MATERIAL",
            "OBJECT",
            "RANDOM",
            "VERTEX",
            "TEXTURE",
            "SINGLE",
        }:
            space.shading.color_type = previous_color
        if previous_light in {"STUDIO", "MATCAP", "FLAT"}:
            space.shading.light = previous_light
        area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    for key in (
        "safe_mpr_area_pointer",
        "safe_mpr_previous_region_ui",
        "safe_mpr_previous_region_toolbar",
        "safe_mpr_previous_shading_type",
        "safe_mpr_previous_color_type",
        "safe_mpr_previous_light",
        "safe_mpr_surface_hide_select",
    ):
        try:
            del props[key]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    _SAFE_MPR_OWNER_AREA_POINTER = 0

    if int(props.step) == 4 and bool(props.surface_ready):
        surface = bpy.data.objects.get(str(props.generated_surface_name))
        if surface is not None and surface.type == "MESH":
            props.step = 5
            message = "Revisión terminada · STL listo para exportar"
        else:
            message = "Revisión cerrada; no se encontró el STL"
    else:
        message = "Revisión por planos cerrada"

    props.status = message
    force_ui_redraw()
    return True, message


def _safe_mpr_region_at_mouse(area, mouse_x, mouse_y):
    for role, region in _safe_mpr_region_roles(area).items():
        if region.x <= mouse_x < region.x + region.width and region.y <= mouse_y < region.y + region.height:
            return role, region
    return None, None


