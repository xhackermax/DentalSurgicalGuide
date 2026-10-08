import bpy
from bpy.types import Panel


def _ui_error(layout, section: str, exc: Exception) -> None:
    """Keep the rest of the panel visible if one UI section fails."""
    box = layout.box()
    box.label(text=f"No se pudo dibujar: {section}")
    box.label(text=str(exc)[:120])
    print(f"[DICOM Wizard Pro UI] {section}: {exc!r}")


def _draw_guarded(layout, section: str, callback) -> None:
    try:
        callback()
    except Exception as exc:
        _ui_error(layout, section, exc)


def _draw_axis_controls(layout, props) -> None:
    """Draw the six requested sliders for the active plane."""
    prefix = props.active_plane.lower()

    move = layout.box()
    move.label(text="MOVIMIENTO DEL PLANO")
    for axis in ("x", "y", "z"):
        item = move.box()
        item.label(text=f"Mover {axis.upper()}  ·  principio ↔ final")
        item.prop(props, f"{prefix}_move_{axis}", text="", slider=True)

    rotate = layout.box()
    rotate.label(text="ROTACIÓN DEL PLANO")
    for axis in ("x", "y", "z"):
        item = rotate.box()
        item.label(text=f"Girar {axis.upper()}  ·  izquierda ↔ derecha")
        item.prop(props, f"{prefix}_rotate_{axis}", text="", slider=True)


def _draw_visibility(layout, props) -> None:
    box = layout.box()
    box.label(text="VISIBILIDAD")
    row = box.row(align=True)
    row.prop(props, "show_volume", text="Volumen", toggle=True)
    row.prop(props, "show_planes", text="Plano", toggle=True)
    row.prop(props, "show_box", text="Marco", toggle=True)
    row = box.row(align=True)
    row.prop(props, "show_all_planes", text="Mostrar 3 planos", toggle=True)
    row.prop(props, "realtime_mpr", text="Tiempo real", toggle=True)
    box.prop(props, "correct_inplane_180", text="Corregir giro 180° del DICOM", toggle=True)


def _draw_density(layout, props, *, compact: bool = False) -> None:
    box = layout.box()
    box.label(text="THRESHOLD / DENSIDAD")
    box.prop(props, "threshold_min_percent", text="Densidad mínima", slider=True)
    box.prop(props, "threshold_max_percent", text="Densidad máxima", slider=True)
    box.label(text=f"Rango actual: {props.current_density_min:.0f} – {props.current_density_max:.0f}")
    if not compact:
        box.prop(props, "volume_opacity", text="Opacidad del volumen", slider=True)
    row = box.row()
    row.operator(DICOMWIZARDPRO_OT_auto_threshold.bl_idname, text="Threshold automático")


def _draw_plane_selector_and_actions(layout, props) -> None:
    box = layout.box()
    box.label(text="PLANO DE TRABAJO")
    box.prop(props, "active_plane", expand=True)

    row = box.row(align=True)
    plane_op = row.operator(DICOMWIZARDPRO_OT_select_target.bl_idname, text="Editar plano con G / R / S")
    plane_op.target = "PLANE"
    volume_op = row.operator(DICOMWIZARDPRO_OT_select_target.bl_idname, text="Rotar volumen")
    volume_op.target = "VOLUME"

    _draw_axis_controls(box, props)

    row = box.row(align=True)
    row.operator(DICOMWIZARDPRO_OT_center_plane.bl_idname, text="Centrar plano")
    row.operator(DICOMWIZARDPRO_OT_reset_plane.bl_idname, text="Enderezar plano")

    alignment = box.box()
    alignment.label(text="ORIENTACIÓN ANATÓMICA DE LOS 3 CORTES")
    alignment.label(text="Gira un plano hasta verlo recto y úsalo como referencia")
    alignment.operator(
        DICOMWIZARDPRO_OT_align_mpr_from_active_plane.bl_idname,
        text="ALINEAR LOS 3 CORTES DESDE ESTE PLANO",
    )
    alignment.operator(
        DICOMWIZARDPRO_OT_reset_mpr_orientation.bl_idname,
        text="Restablecer orientación original",
    )


def _draw_reset_flow_panel(layout, props) -> None:
    """Navigation is centralized in DSG > Control del flujo (v9.2.5)."""
    return


class DICOMWIZARDPRO_PT_main(Panel):
    """Minimal DICOM exception/actions panel; normal route lives in DSG shell."""

    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB_NAME
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        try:
            return core.infer_stage(context.scene) == core.STAGE_DICOM
        except Exception:
            return True

    def draw(self, context):
        layout = self.layout
        layout.operator('dsg.copy_pipeline_diagnostic',text='Copiar diagnóstico',icon='COPYDOWN')
        props = context.scene.dicom_wizard_pro
        layout.use_property_split = False
        layout.use_property_decorate = False
        try:
            from . import runtime_bootstrap
            components = runtime_bootstrap.component_status()
        except Exception as exc:
            components = {"base_required_ready": False, "error": str(exc)}

        if not bool(components.get("base_required_ready", False)):
            # This is strictly a DICOM-base problem. Do not launch the AI installer here.
            state = dicom_install_state()
            detail = str(state.get("error") or state.get("message") or components.get("error") or "Motor DICOM pendiente")
            try:
                core.set_status_bar(context, detail)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            box = layout.box()
            box.label(text="Motor DICOM básico pendiente", icon='ERROR')
            box.label(text=detail[:120])
            if not bool(state.get("running", False)):
                row = ui_style.primary_action(box)
                row.operator("dsg.install_dicom_runtime", text="REPARAR MOTOR DICOM", icon="IMPORT")
            return

        area = getattr(context, "area", None)
        mpr_active = bool(props.get("safe_mpr_active", False))
        if not mpr_active and area is not None and area.type == "VIEW_3D":
            mpr_active = _safe_mpr_native_quad_active(area)
        if mpr_active:
            row = ui_style.secondary_action(layout)
            row.operator(DICOMWIZARDPRO_OT_close_safe_mpr.bl_idname, text=_dw_t(props, "EXIT MPR", "SALIR MPR"), icon_value=icon_manager.icon_id("close"))


class _DICOMChildPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB_NAME
    bl_parent_id = "DICOMWIZARDPRO_PT_main"
    step = 0

    @classmethod
    def poll(cls, context):
        # DSG 9.2.1: the top-level DSG panel owns the complete patient-first
        # SIMPLE / IMMEDIATE route selection.  These legacy child panels stay
        # registered for operator compatibility but are intentionally hidden so
        # users never see a second, conflicting button flow.
        return False


class DICOMWIZARDPRO_PT_import(_DICOMChildPanel, Panel):
    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_import"
    bl_options = {"HIDE_HEADER"}
    bl_order = 1
    step = 1

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicom_wizard_pro
        from . import runtime_bootstrap
        bootstrap_status = runtime_bootstrap.component_status()
        if not bool(bootstrap_status.get("base_required_ready", False)):
            # DICOM and the SIMPLE route must remain available even when the
            # immediate-implant AI stack is not yet recoverable.
            return

        dependencies = dependency_summary()
        if not dependencies["pydicom"]:
            layout.label(
                text=_dw_t(props, "Bundled DICOM reader unavailable", "Lector DICOM incluido no disponible"),
                icon_value=icon_manager.icon_id('status_error'))
            return
        if not dependencies["openvdb"]:
            layout.label(
                text=_dw_t(props, "OpenVDB is unavailable", "OpenVDB no disponible"),
                icon_value=icon_manager.icon_id('status_error'))
            return

        layout.label(
            text=f"Motores DSG ✓ · DICOM {dependencies.get('pydicom_version', '')}",
            icon_value=icon_manager.icon_id('status_ok'))

        open_row = ui_style.primary_action(layout)
        open_row.operator(
            DICOMWIZARDPRO_OT_select_file.bl_idname,
            text=_dw_t(props, "OPEN DICOM", "ABRIR DICOM"),
            icon_value=icon_manager.icon_id('open_folder'))
        if props.header_valid:
            info = layout.box()
            info.label(text=props.filename[:48])
            info.label(text=f"{props.dimensions_summary} · {props.spacing_summary}")
            load_row = ui_style.primary_action(layout)
            load_row.operator(
                DICOMWIZARDPRO_OT_next.bl_idname,
                text=_dw_t(props, "LOAD", "CARGAR"),
                icon_value=icon_manager.icon_id('import_stl'))


class DICOMWIZARDPRO_PT_view(_DICOMChildPanel, Panel):
    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_view"
    bl_options = {"HIDE_HEADER"}
    bl_order = 10
    step = 2

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicom_wizard_pro
        toggles = ui_style.tertiary_action(layout)
        toggles.prop(props, "show_volume", text="3D", toggle=True)
        toggles.prop(props, "show_planes", text=_dw_t(props, "Slice", "Corte"), toggle=True)
        actions = ui_style.primary_action(layout)
        actions.operator(
            DICOMWIZARDPRO_OT_to_segmentation.bl_idname,
            text=_dw_t(props, "CONTINUE", "CONTINUAR"),
            icon_value=icon_manager.icon_id('continue'))


class DICOMWIZARDPRO_PT_view_advanced(_DICOMChildPanel, Panel):
    """Legacy registration shell; the DICOM Advanced menu was removed."""

    bl_label = "Advanced / Avanzado"
    bl_idname = "DICOMWIZARDPRO_PT_view_advanced"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 11
    step = 2

    @classmethod
    def poll(cls, context):
        return False

    def draw(self, context):
        pass


class DICOMWIZARDPRO_PT_segment(_DICOMChildPanel, Panel):
    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_segment"
    bl_options = {"HIDE_HEADER"}
    bl_order = 20
    step = 3

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicom_wizard_pro
        from . import segmentation_engines
        from . import runtime_bootstrap

        selected_id = str(getattr(props, "ai_segmentation_engine", "TOTALSEG") or "TOTALSEG").upper()
        statuses = segmentation_engines.verify_all(force=False)
        selected = statuses.get(selected_id) or statuses[segmentation_engines.ENGINE_TOTALSEG]
        install = segmentation_engines.install_state()
        engine = layout.box()
        engine.label(
            text=_dw_t(props, "CBCT Dental AI · 3-engine benchmark", "IA dental CBCT · benchmark 3 motores"),
            icon_value=icon_manager.icon_id('cbct'))
        engine.prop(props, "ai_segmentation_engine", text=_dw_t(props, "Engine", "Motor"))

        for engine_id in segmentation_engines.ENGINE_IDS:
            st = statuses[engine_id]
            unsupported = engine_id == "UMAMBA2" and os.name == "nt"
            icon = 'CHECKMARK' if st.ready else ('ERROR' if st.experimental else 'INFO')
            suffix = "NO COMPATIBLE CON WINDOWS" if unsupported else "READY" if st.ready else "PENDIENTE"
            row = engine.row(align=True)
            row.label(text=f"{st.label}: {suffix}", icon=icon)
            if not st.ready and not unsupported:
                op = row.operator(runtime_bootstrap.INSTALL_OPERATOR_ID, text="INSTALAR" if engine_id != "UMAMBA2" else "PREPARAR")
                op.engine = engine_id

        if install.get("running"):
            engine.label(text=str(install.get("message") or "Instalando motor IA…")[:140], icon_value=icon_manager.icon_id('status_pending'))
            try:
                percent = max(0, min(100, round(float(install.get("progress", 0.0)) * 100)))
                engine.progress(factor=float(install.get("progress", 0.0)), type='BAR', text=f"{percent}% · {str(install.get('phase') or 'PREPARANDO')}")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        elif install.get("error"):
            # Installation of ALL is intentionally partial-tolerant. Show the
            # error but keep already verified engines usable.
            engine.label(text=str(install.get("error"))[:140], icon='ERROR')

        selected_row = engine.row()
        selected_row.alert = not selected.ready
        selected_row.label(
            text=(f"Seleccionado: {selected.label} ✓" if selected.ready else f"Seleccionado pendiente: {selected.label}"),
            icon='CHECKMARK' if selected.ready else 'ERROR')
        if selected.error and not selected.ready:
            engine.label(text=selected.error[:140])
        if selected.engine == "TOOTHSEG":
            engine.label(text="ToothSeg: dientes/FDI únicamente; no crea maxila, mandíbula ni canal", icon='INFO')
        if selected.engine == "UMAMBA2" and not selected.model_ready:
            engine.label(text="Requiere Linux/CUDA y checkpoint final ToothFairy3; no se instala en Windows", icon='INFO')

        install_all = engine.row(align=True)
        op_all = install_all.operator(runtime_bootstrap.INSTALL_OPERATOR_ID, text="INSTALAR / REPARAR MOTORES", icon='IMPORT')
        op_all.engine = "ALL"
        install_all.operator("dsg.runtime_preflight", text="REVISAR", icon='FILE_REFRESH')

        compute = engine.row(align=True)
        compute.prop(props, "ai_device_preference", text=_dw_t(props, "AI compute", "Cálculo IA"))
        compute.prop(props, "ai_manage_blender_resources", text="Blender AUTO", toggle=True)
        diagnostics = engine.row(align=True)
        diagnostics.operator("dsg.run_safety_failtests", text="FAILTEST DSG", icon='CHECKMARK')

        ai_busy = semantic_workflow_busy()
        route = core.clinical_route(context.scene)
        target_fdi = core.target_fdi(context.scene)
        semantic_ready = bool(selected.ready)
        dual_ready = bool(selected.ready and (selected.engine != "TOOTHSEG" or route != core.ROUTE_IMMEDIATE))
        idle = not bool(install.get("running")) and not ai_busy

        route_box = layout.box()
        route_box.label(
            text=(_dw_t(props, "SIMPLE IMPLANT", "IMPLANTE SIMPLE")
                  if route == core.ROUTE_SIMPLE else
                  _dw_t(props, "IMMEDIATE IMPLANT", "IMPLANTE INMEDIATO")),
            icon='MODIFIER')
        if route == core.ROUTE_IMMEDIATE:
            route_box.label(text=f"FDI {target_fdi}")

        if route == core.ROUTE_IMMEDIATE:
            route_box.label(
                text=_dw_t(props,
                    "Mandatory: individual tooth + FDI + bone + canal",
                    "Obligatorio: diente individual + FDI + hueso + canal"),
                icon_value=icon_manager.icon_id('status_info'))
            immediate = ui_style.primary_action(route_box)
            immediate.enabled = bool(dual_ready and idle)
            immediate.operator(
                DICOMWIZARDPRO_OT_segment_all.bl_idname,
                text=_dw_t(props,
                    f"SEGMENT FOR IMMEDIATE IMPLANT · {selected.label}",
                    f"SEGMENTAR PARA IMPLANTE INMEDIATO · {selected.label}"),
                icon_value=icon_manager.icon_id('model'))
            route_box.label(
                text=("Motor compatible con FDI + maxilares + canal" if selected.engine != "TOOTHSEG" else "ToothSeg no es compatible con esta ruta"))
        else:
            route_box.label(text=_dw_t(props, "Exactly two colored arches", "Exactamente dos arcadas por color"), icon_value=icon_manager.icon_id('status_info'))
            simple = ui_style.primary_action(route_box)
            simple.enabled = bool(selected.ready and selected.engine != "TOOTHSEG" and idle)
            op = simple.operator(DICOMWIZARDPRO_OT_segment_all.bl_idname, text=_dw_t(props, "SEGMENT 2 ARCHES", "SEGMENTAR 2 ARCADAS"), icon_value=icon_manager.icon_id('model'))
            op.route_mode = "SIMPLE_ARCHES"

        if ai_busy:
            snapshot = segmentation_progress_snapshot(context)
            factor = float(snapshot.get("factor", 0.0) or 0.0)
            phase_text = str(snapshot.get("phase") or "Segmentación CBCT en curso")
            detail_text = str(snapshot.get("detail") or props.status or "")
            elapsed_s = float(snapshot.get("elapsed_s", 0.0) or 0.0)

            progress_box = layout.box()
            loading_engine = factor <= 0.20 and any(
                token in phase_text.lower()
                for token in ("engine", "motor", "peso", "runtime", "totalsegmentator", "toothseg", "mamba")
            )
            progress_box.label(
                text=_dw_t(
                    props,
                    "LOADING ENGINES AND WEIGHTS" if loading_engine else "SEGMENTATION IN PROGRESS",
                    "CARGANDO MOTORES Y PESOS" if loading_engine else "SEGMENTACIÓN EN CURSO",
                ),
                icon_value=icon_manager.icon_id('model'),
            )
            try:
                progress_box.progress(
                    factor=max(0.0, min(1.0, factor)),
                    text=f"{factor * 100.0:.0f}% · {phase_text}",
                )
            except Exception:
                progress_box.label(text=f"{factor * 100.0:.0f}% · {phase_text}")

            if detail_text:
                progress_box.label(text=detail_text[:110])
            progress_box.label(
                text=_dw_t(
                    props,
                    f"Working · {elapsed_s:.0f} s elapsed · Blender remains interactive",
                    f"Trabajando · {elapsed_s:.0f} s transcurridos · Blender sigue operativo",
                ),
                icon_value=icon_manager.icon_id('status_info'),
            )
            progress_box.label(
                text=_dw_t(
                    props,
                    "The bar shows completed workflow phases, not a fabricated neural-network percentage.",
                    "La barra muestra fases reales completadas, no un porcentaje inventado de la red neuronal.",
                )[:115]
            )

        info = layout.box()
        info.label(
            text=_dw_t(props, "CBCT semantic classes", "Clases semánticas CBCT"),
            icon_value=icon_manager.icon_id('status_info'))
        if selected.model_ready:
            info.label(text=f"{selected.label}: FDI individual" + (" + maxila/mandíbula/canal" if "JAW" in set(selected.capabilities) else ""))
            info.label(text="Salida normalizada · mismo pipeline de mallas DSG")
            info.label(text="Benchmark comparable: motor, tiempo y geometría quedan registrados")
        else:
            info.label(text=_dw_t(props,
                "Install the selected segmentation engine to segment CBCT",
                "Instala el motor de segmentación seleccionado para segmentar CBCT"))

        back = ui_style.tertiary_action(layout)
        back.operator(
            DICOMWIZARDPRO_OT_back_to_viewer.bl_idname,
            text=_dw_t(props, "Back", "Volver"),
            icon_value=icon_manager.icon_id('back'))


class DICOMWIZARDPRO_PT_segment_advanced(_DICOMChildPanel, Panel):
    bl_label = "Advanced / Avanzado"
    bl_idname = "DICOMWIZARDPRO_PT_segment_advanced"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 21
    step = 99

    @classmethod
    def poll(cls, context):
        return False

    def draw(self, context):
        pass


class DICOMWIZARDPRO_PT_mpr_review(_DICOMChildPanel, Panel):
    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_mpr_review"
    bl_options = {"HIDE_HEADER"}
    bl_order = 30
    step = 4

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicom_wizard_pro
        surface = bpy.data.objects.get(props.generated_surface_name)
        if surface is None or surface.type != "MESH":
            layout.label(
                text=_dw_t(props, "STL not found", "No se encontró el STL"),
                icon_value=icon_manager.icon_id('status_error'))
            back = ui_style.tertiary_action(layout)
            back.operator(
                DICOMWIZARDPRO_OT_back_to_segmentation.bl_idname,
                text=_dw_t(props, "Back", "Volver"),
                icon_value=icon_manager.icon_id('back'))
            return

        from . import cbct_dental_module
        cbct_dental_module.draw_review(layout, context)
        has_cbct_fdi = bool(cbct_dental_module.dentition_objects())
        fdi_ok = bool(context.scene.get(cbct_dental_module.SCENE_ACCEPTED_KEY, False))

        mpr_active = bool(props.get("safe_mpr_active", False))
        if not mpr_active:
            continue_row = ui_style.primary_action(layout)
            continue_row.enabled = (not has_cbct_fdi) or fdi_ok
            continue_row.operator(
                DICOMWIZARDPRO_OT_prepare_alignment.bl_idname,
                text=_dw_t(props, "CONTINUE TO ALIGNMENT", "CONTINUAR A ALINEAMIENTO"),
                icon_value=icon_manager.icon_id('continue'))

            review_box = layout.box()
            review_box.label(
                text=_dw_t(props, "Optional · radiographic review", "Opcional · revisión radiográfica"),
                icon_value=icon_manager.icon_id('mpr'))
            open_row = ui_style.secondary_action(review_box)
            open_row.operator_context = "INVOKE_DEFAULT"
            open_row.operator(
                DICOMWIZARDPRO_OT_radiographic_quad_view.bl_idname,
                text=_dw_t(props, "Review with planes", "Revisar con planos"),
                icon_value=icon_manager.icon_id('mpr'))
            tools = ui_style.tertiary_action(review_box)
            tools.operator(
                DICOMWIZARDPRO_OT_select_surface.bl_idname,
                text=_dw_t(props, "Select reference", "Seleccionar referencia"))
            tools.operator(
                DICOMWIZARDPRO_OT_back_to_segmentation.bl_idname,
                text=_dw_t(props, "Back", "Volver"),
                icon_value=icon_manager.icon_id('back'))
            return

        z_box = layout.box()
        z_box.label(text=_dw_t(props, "HORIZONTAL PLANE", "PLANO HORIZONTAL"))
        z_box.prop(props, "axial_move_z", text=_dw_t(props, "Z Position", "Posición Z"), slider=True)
        rotation_box = layout.box()
        rotation_box.label(text=_dw_t(props, "VERTICAL PLANE", "PLANO VERTICAL"))
        rotation_box.prop(
            props, "sagittal_rotate_z",
            text=_dw_t(props, "Z Inclination", "Inclinación Z"), slider=True)
        layout.label(
            text=_dw_t(
                props,
                "Fixed radiographic visibility · Real-time update",
                "Visibilidad radiográfica fija · Actualización en tiempo real"),
            icon_value=icon_manager.icon_id('cbct'))
        exit_row = ui_style.primary_action(layout)
        exit_row.operator(
            DICOMWIZARDPRO_OT_close_safe_mpr.bl_idname,
            text=_dw_t(props, "EXIT REVIEW", "SALIR DE REVISIÓN"),
            icon_value=icon_manager.icon_id('continue'))


class DICOMWIZARDPRO_PT_result(_DICOMChildPanel, Panel):
    bl_label = "DICOM"
    bl_idname = "DICOMWIZARDPRO_PT_result"
    bl_options = {"HIDE_HEADER"}
    bl_order = 40
    step = 5

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicom_wizard_pro
        if props.generated_surface_name:
            layout.label(
                text=props.generated_surface_name[:48],
                icon_value=icon_manager.icon_id('status_ok'))

        continue_row = ui_style.primary_action(layout)
        continue_row.operator(
            DICOMWIZARDPRO_OT_prepare_alignment.bl_idname,
            text=_dw_t(props, "CONTINUE TO ALIGNMENT", "CONTINUAR A ALINEAMIENTO"),
            icon_value=icon_manager.icon_id('continue'))

        export = ui_style.secondary_action(layout)
        export.operator(
            DICOMWIZARDPRO_OT_export_surface_stl.bl_idname,
            text=_dw_t(props, "Export STL", "Exportar STL"),
            icon_value=icon_manager.icon_id('export_stl'))

        row = ui_style.tertiary_action(layout)
        row.operator(
            DICOMWIZARDPRO_OT_select_surface.bl_idname,
            text=_dw_t(props, "Select", "Seleccionar"))
        row.operator(
            DICOMWIZARDPRO_OT_back_to_segmentation.bl_idname,
            text=_dw_t(props, "Back", "Volver"),
            icon_value=icon_manager.icon_id('back'))


PANEL_CLASSES = (
    DICOMWIZARDPRO_PT_main,
    DICOMWIZARDPRO_PT_import,
    DICOMWIZARDPRO_PT_view,
    DICOMWIZARDPRO_PT_view_advanced,
    DICOMWIZARDPRO_PT_segment,
    DICOMWIZARDPRO_PT_mpr_review,
    DICOMWIZARDPRO_PT_result,
)


# =============================================================================
# MODULE: __init__.py
# =============================================================================

import bpy
from bpy.props import PointerProperty


bl_info = {
    "name": "DSG · DICOM Module",
    "author": "Max Tiburcio",
    "version": ADDON_VERSION,
    "blender": BLENDER_MIN_VERSION,
    "location": "3D View > Sidebar > DSG",
    "description": "Bilingual DICOM/CBCT to STL workflow with automatic handoff to Dental Alignment",
    "warning": "Clinical visualization prototype; not a certified diagnostic device",
    "category": "3D View",
}

CLASSES = (
    DICOMWizardProProperties,
    *OPERATOR_CLASSES,
    *PANEL_CLASSES,
)


def menu_import(self, context) -> None:
    self.layout.operator(
        "dicom_wizard_pro.select_file",
        text="DICOM Wizard Pro",
    )


def _dicom_data_access_ready() -> bool:
    """True only after Blender has released its activation-time _RestrictData."""
    try:
        return (
            getattr(bpy.data, "objects", None) is not None
            and getattr(bpy.data, "scenes", None) is not None
        )
    except Exception:
        return False


def pre_register_quiesce() -> None:
    """Stop old DICOM callbacks without reading any scene/object datablocks."""
    try:
        lifecycle.cancel_module_timers(__name__)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    unregister_realtime_handler()
    unregister_undo_handlers()
    RUNTIME.update_lock = True
    RUNTIME.undo_in_progress = True
    RUNTIME.undo_repair_pending = False
    RUNTIME.transform_handler_lock = True


_DICOM_REGISTERED_CLASSES = []
_DICOM_SCENE_POINTER_OWNED = False
_DICOM_MENU_OWNED = False
_DICOM_HEADERS_OWNED = False
_DICOM_HANDLER_OWNED = False
_DICOM_UNDO_HANDLERS_OWNED = False


def _dicom_unregister_class_object(class_object):
    if class_object is None:
        return False
    try:
        bpy.utils.unregister_class(class_object)
        return True
    except Exception:
        return False


def _dicom_unregister_stale_classes():
    """Remove RNA classes left by a previous DSG/DICOM installation."""
    removed = 0
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None and _dicom_unregister_class_object(existing):
            removed += 1
            continue
        if _dicom_unregister_class_object(cls):
            removed += 1
    if removed:
        print(f"[DSG] Removed {removed} stale DICOM class(es) from an older version")
    return removed


def _dicom_remove_stale_scene_pointer():
    if not hasattr(bpy.types.Scene, "dicom_wizard_pro"):
        return False
    try:
        del bpy.types.Scene.dicom_wizard_pro
        print("[DSG] Removed stale Scene.dicom_wizard_pro from older DSG/DICOM version")
        return True
    except Exception as exc:
        raise RuntimeError(
            f"Could not replace stale Scene.dicom_wizard_pro from a previous DSG/DICOM add-on: {exc}"
        )


def register() -> None:
    # Do not read scene/object data here. Registration is transactional so a
    # failure cannot leave half-registered operators or duplicated header hooks.
    global _DICOM_REGISTERED_CLASSES, _DICOM_SCENE_POINTER_OWNED
    global _DICOM_MENU_OWNED, _DICOM_HEADERS_OWNED, _DICOM_HANDLER_OWNED
    global _DICOM_UNDO_HANDLERS_OWNED
    if _DICOM_REGISTERED_CLASSES:
        return
    _dicom_remove_stale_scene_pointer()
    _dicom_unregister_stale_classes()
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.dicom_wizard_pro = PointerProperty(type=DICOMWizardProProperties)
        _DICOM_SCENE_POINTER_OWNED = True

        bpy.types.TOPBAR_MT_file_import.append(menu_import)
        _DICOM_MENU_OWNED = True
        bpy.types.VIEW3D_HT_header.prepend(draw_mpr_slice_header)
        bpy.types.VIEW3D_HT_header.prepend(draw_mpr_global_header)
        _DICOM_HEADERS_OWNED = True
        # Depsgraph/undo handlers are intentionally NOT installed here.
        # Blender 5.2 still exposes _RestrictData during this function and may
        # invoke a newly appended handler immediately. deferred_post_register()
        # installs them after normal bpy.data access is confirmed.
        _DICOM_HANDLER_OWNED = False
        _DICOM_UNDO_HANDLERS_OWNED = False
        _DICOM_REGISTERED_CLASSES = registered
    except Exception:
        unregister_undo_handlers()
        _DICOM_UNDO_HANDLERS_OWNED = False
        unregister_realtime_handler()
        if _DICOM_HEADERS_OWNED:
            for callback in (draw_mpr_slice_header, draw_mpr_global_header):
                try:
                    bpy.types.VIEW3D_HT_header.remove(callback)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        if _DICOM_MENU_OWNED:
            try:
                bpy.types.TOPBAR_MT_file_import.remove(menu_import)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if _DICOM_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dicom_wizard_pro"):
            del bpy.types.Scene.dicom_wizard_pro
        for cls in reversed(registered):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _DICOM_REGISTERED_CLASSES = []
        _DICOM_SCENE_POINTER_OWNED = False
        _DICOM_MENU_OWNED = False
        _DICOM_HEADERS_OWNED = False
        _DICOM_HANDLER_OWNED = False
        _DICOM_UNDO_HANDLERS_OWNED = False
        raise


def deferred_post_register() -> bool:
    """Install data-sensitive handlers after Blender releases _RestrictData."""
    global _DICOM_HANDLER_OWNED, _DICOM_UNDO_HANDLERS_OWNED
    if not _dicom_data_access_ready():
        return False
    if not _DICOM_HANDLER_OWNED:
        register_realtime_handler()
        _DICOM_HANDLER_OWNED = True
    if not _DICOM_UNDO_HANDLERS_OWNED:
        register_undo_handlers()
        _DICOM_UNDO_HANDLERS_OWNED = True
    RUNTIME.update_lock = False
    RUNTIME.undo_in_progress = False
    RUNTIME.transform_handler_lock = False
    return True


def unregister() -> None:
    global _DICOM_REGISTERED_CLASSES, _DICOM_SCENE_POINTER_OWNED
    global _DICOM_MENU_OWNED, _DICOM_HEADERS_OWNED, _DICOM_HANDLER_OWNED
    global _DICOM_UNDO_HANDLERS_OWNED
    lifecycle.cancel_module_timers(__name__)
    _safe_mpr_remove_draw_handler()
    if _DICOM_UNDO_HANDLERS_OWNED:
        unregister_undo_handlers()
    _DICOM_UNDO_HANDLERS_OWNED = False
    if _DICOM_HANDLER_OWNED:
        unregister_realtime_handler()
    _DICOM_HANDLER_OWNED = False
    if _DICOM_HEADERS_OWNED:
        for callback in (draw_mpr_slice_header, draw_mpr_global_header):
            try:
                bpy.types.VIEW3D_HT_header.remove(callback)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    _DICOM_HEADERS_OWNED = False
    if _DICOM_MENU_OWNED:
        try:
            bpy.types.TOPBAR_MT_file_import.remove(menu_import)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _DICOM_MENU_OWNED = False

    # Restore any temporary AI performance profile before disabling the add-on.
    try:
        _restore_ai_performance_session(bpy.context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Restore viewport overlays/gizmos if the add-on is disabled while the
    # clinical threshold preview is active. Patient objects remain untouched.
    try:
        restore_clinical_preview_view(bpy.context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Do not call cleanup_scene() here. Disabling an add-on must never delete
    # a patient's imported/generated objects. Only volatile RAM/temp cache dies.
    try:
        remove_cached_vdb()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    RUNTIME.reset()

    if _DICOM_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dicom_wizard_pro"):
        del bpy.types.Scene.dicom_wizard_pro
    _DICOM_SCENE_POINTER_OWNED = False
    for cls in reversed(list(_DICOM_REGISTERED_CLASSES)):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _DICOM_REGISTERED_CLASSES = []


if __name__ == "__main__":
    register()
