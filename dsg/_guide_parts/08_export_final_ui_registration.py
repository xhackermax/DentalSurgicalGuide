class DSG_OT_PlaceEngraveAnchor(Operator):
    bl_idname = "dsg.place_engrave_anchor"
    bl_label = "Place Name on Surface"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot place the patient name',
                action_es='No se puede colocar el nombre del paciente'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        activate_precision_orthographic(context)
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, "DSG_Guide was not found for engraving placement", "No se encontró DSG_Guide para colocar el grabado")
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        _dsg_report(self, {'INFO'}, "Click the outer guide surface where the name will be placed", "Haz clic sobre la cara externa de la guía donde irá el nombre")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            _dsg_report(self, {'INFO'}, "Engraving placement canceled", "Colocación de grabado cancelada")
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            props = context.scene.dsg_props
            guide = get_active_guide_obj(props)
            loc, normal, _ = do_raycast_detailed(context, event, guide)
            if loc is None or normal is None:
                _dsg_report(self, {'WARNING'}, "Guide surface not detected. Click DSG_Guide", "No se detectó la superficie de la guía. Haz clic sobre DSG_Guide")
                return {'RUNNING_MODAL'}
            props.engrave_location = (float(loc.x), float(loc.y), float(loc.z))
            props.engrave_normal = (float(normal.x), float(normal.y), float(normal.z))
            x_axis = get_engrave_x_axis_perpendicular_to_sleeve_base(context, props, loc, normal)
            props.engrave_x_axis = (float(x_axis.x), float(x_axis.y), float(x_axis.z))
            props.engrave_has_position = True
            try:
                props.engrave_preview_dirty = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            create_or_update_engrave_anchor(context, props)
            create_or_update_engrave_preview(context, props)
            _dsg_report(self, {'INFO'}, "Name position saved. Enter the text and click Engrave", "Posición del nombre guardada. Escribe el texto y pulsa Grabar")
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class DSG_OT_UpdateEngravePreview(Operator):
    bl_idname = "dsg.update_engrave_preview"
    bl_label = "Update Preview"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot update the name preview',
                action_es='No se puede actualizar la vista previa del nombre'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if not getattr(props, 'engrave_has_position', False):
            _dsg_report(self, {'ERROR'}, "Place the name on the guide first", "Primero coloca el nombre sobre la guía")
            return {'CANCELLED'}
        create_or_update_engrave_anchor(context, props)
        preview = create_or_update_engrave_preview(context, props)
        if preview is None:
            _dsg_report(self, {'ERROR'}, "Could not create the preview", "No se pudo crear la vista previa")
            return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_ClearEngravePreview(Operator):
    bl_idname = "dsg.clear_engrave_preview"
    bl_label = "Clear Preview"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        safe_remove_engrave_object(ENGRAVE_PREVIEW_NAME)
        safe_remove_by_name(ENGRAVE_ANCHOR_NAME)
        props = context.scene.dsg_props
        props.engrave_has_position = False
        try:
            props.engrave_preview_dirty = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return {'FINISHED'}


class DSG_OT_ApplyPatientEngrave(Operator):
    bl_idname = "dsg.apply_patient_engrave"
    bl_label = "Engrave Name on Guide"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot engrave the patient name',
                action_es='No se puede grabar el nombre del paciente'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, "DSG_Guide not found", "No se encontró DSG_Guide")
            return {'CANCELLED'}
        if not getattr(props, 'engrave_has_position', False):
            _dsg_report(self, {'ERROR'}, "Place the name on the guide surface first", "Primero coloca el nombre sobre la superficie de la guía")
            return {'CANCELLED'}
        if not (props.engrave_patient_text or '').strip():
            _dsg_report(self, {'ERROR'}, "Enter the patient name or code", "Escribe el nombre o código del paciente")
            return {'CANCELLED'}

        cutter = create_engrave_text_cutter(context, props)
        if not _valid_obj(cutter):
            _dsg_report(self, {'ERROR'}, "Could not create the text cutter", "No se pudo crear el cutter de texto")
            return {'CANCELLED'}

        ok, solver, boolean_msg, elapsed = apply_patient_engrave_transactional(
            context, guide, cutter)
        if not ok:
            _dsg_report(
                self, {'ERROR'},
                f"Text engraving failed: {boolean_msg}",
                f"Falló el grabado del texto: {boolean_msg}")
            return {'CANCELLED'}

        # A complete union-find scan of a dense guide was the second major
        # bottleneck. For a shallow local subtraction it is only necessary on
        # moderate meshes; large guides have already passed the Boolean solid
        # audit and skip this presentation cleanup.
        islands_ok, islands_msg, _removed_faces, removed_components = (
            remove_disconnected_islands_keep_largest(
                guide, reason='patient_name_engrave', max_vertices=180000))
        if not islands_ok:
            _dsg_report(self, {'ERROR'}, islands_msg, islands_msg)
            return {'CANCELLED'}

        props.guide_obj = register_dsg_object(guide, ROLE_GUIDE, GUIDE_NAME)
        safe_remove_engrave_object(ENGRAVE_CUTTER_NAME)
        safe_remove_engrave_object(ENGRAVE_PREVIEW_NAME)
        anchor = bpy.data.objects.get(ENGRAVE_ANCHOR_NAME)
        if anchor:
            _set_obj_hidden(anchor, True)
        props.current_step = STEP_DONE
        cleanup_suffix = f' · {islands_msg}' if removed_components else ''
        elapsed_text = f'{float(elapsed):.2f} s'
        _dsg_report(
            self, {'INFO'},
            f"Name engraved using {solver or 'EXACT'} in {elapsed_text}{cleanup_suffix}. Ready to export",
            f"Nombre grabado con {solver or 'EXACT'} en {elapsed_text}{cleanup_suffix}. Lista para exportar")
        return {'FINISHED'}


class DSG_OT_SkipPatientName(Operator):
    bl_idname = 'dsg.skip_patient_name'
    bl_label = 'Continue Without Name'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot finish the guide',
                action_es='No se puede finalizar la guía'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        safe_remove_engrave_object(ENGRAVE_PREVIEW_NAME)
        safe_remove_engrave_object(ENGRAVE_CUTTER_NAME)
        safe_remove_by_name(ENGRAVE_ANCHOR_NAME)
        props.engrave_has_position = False
        props.current_step = STEP_DONE
        _dsg_report(self, {'INFO'}, 'Name skipped. The guide is ready to export.', 'Nombre omitido. La guía está lista para exportar.')
        return {'FINISHED'}


class DSG_OT_CleanGuideIslands(Operator):
    bl_idname = 'dsg.clean_guide_islands'
    bl_label = 'Remove Separate Fragments'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot clean the final guide',
                action_es='No se puede limpiar la guía final'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'DSG_Guide not found', 'No se encontró DSG_Guide')
            return {'CANCELLED'}
        ok, message, _faces, components = remove_disconnected_islands_keep_largest(
            guide, reason='manual_cleanup')
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, message if components else 'The guide already contains a single connected piece', message if components else 'La guía ya contiene una sola pieza conectada')
        return {'FINISHED'}


class DSG_OT_ExportGuideSTL(Operator, ExportHelper):
    bl_idname    = "dsg.export_guide_stl"
    bl_label     = "Export Guide STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={'HIDDEN'})

    # ── Quality gate (DSG 9.7.0, see guide_export/) ───────────────────────
    confirm_island_removal: BoolProperty(
        name="Confirm removal of detached pieces",
        description=("Allow deleting disconnected pieces larger than debris "
                     "(e.g. a sleeve that lost its connector). Off = cancel and review"),
        default=False, options={'SKIP_SAVE'})
    allow_non_manifold: BoolProperty(
        name="Allow non-closed mesh",
        description="Export even if the guide is not a closed solid (not recommended)",
        default=False, options={'SKIP_SAVE'})
    check_wall_thickness: BoolProperty(
        name="Check wall thickness", default=True)
    min_wall_thickness_mm: FloatProperty(
        name="Minimum wall (mm)", default=1.0, min=0.0, max=10.0, precision=2,
        description="Walls thinner than this are reported (depends on resin and printer)")
    min_canal_distance_mm: FloatProperty(
        name="Implant–canal margin (mm)", default=2.0, min=0.0, max=10.0, precision=2,
        description="Implants closer than this to the segmented mandibular canal are reported")
    write_report: BoolProperty(
        name="Write traceability report", default=True,
        description="Write <file>.dsg-report.json with inputs, plan, versions and quality checks")

    def invoke(self, context, event):
        # Patient-first workflow: exports open directly in the case folder.
        # The user can still change the filename/location in Blender's selector.
        folder = core.patient_folder(context.scene) if hasattr(core, "patient_folder") else ""
        if folder:
            case = str(getattr(context.scene.dsg_suite_settings, "case_name", "") or "patient").strip()
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in case).strip("_") or "patient"
            self.filepath = os.path.join(folder, f"DSG_Guide_{safe}.stl")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_NAME,
                action_en='Cannot export the guide',
                action_es='No se puede exportar la guía'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, "There is no guide to export", "No hay ferula para exportar")
            return {'CANCELLED'}
        ensure_object_mode(context)
        from .guide_export import service as export_service
        from .guide_export.policy import ExportPolicy
        gate = export_service.ExportGate(
            ExportPolicy(min_wall_thickness_mm=float(self.min_wall_thickness_mm),
                         min_canal_distance_mm=float(self.min_canal_distance_mm)),
            export_service.ExportOptions(
                allow_non_manifold=bool(self.allow_non_manifold),
                confirm_island_removal=bool(self.confirm_island_removal),
                check_wall_thickness=bool(self.check_wall_thickness),
                write_report=bool(self.write_report)))
        gate_checks = []
        export_obj = None
        export_work = None
        seal_objects = []
        islands_msg = ''
        removed_components = 0
        sealed_implants = get_sealed_irrigation_implants(
            props, require_confirmed_path=True)
        try:
            # Export is always transactional. Cleanup and seal fusion happen on a
            # temporary copy, so pressing Export repeatedly never changes the
            # clinical guide stored in the Blender scene.
            safe_remove_temp_by_name('DSG_ExportGuide_Work')
            safe_remove_temp_by_name('DSG_ExportGuide_WithSeals')
            export_work = duplicate_object_with_data(
                context, guide, 'DSG_ExportGuide_Work')
            if not _valid_obj(export_work):
                raise RuntimeError('Could not create the export working copy')
            export_work.display_type = 'SOLID'
            _set_obj_hidden(export_work, False, selectable_when_visible=True)

            island_check = gate.check_islands(export_work)
            gate_checks.append(island_check)
            if island_check.blocking:
                raise RuntimeError(
                    f'{island_check.message}. Tick "Confirm removal of detached pieces" '
                    'in the export options to proceed')
            islands_ok, islands_msg, _removed_faces, removed_components = (
                remove_disconnected_islands_keep_largest(
                    export_work, reason='pre_export_safety'))
            if not islands_ok:
                raise RuntimeError(islands_msg)

            if sealed_implants:
                export_work.name = 'DSG_ExportGuide_WithSeals'
                if export_work.data is not None:
                    export_work.data.name = 'DSG_ExportGuide_WithSeals_Mesh'

                seal_objects, seal_message = build_export_frangible_irrigation_seals(
                    context, props)
                if len(seal_objects) != len(sealed_implants):
                    raise RuntimeError(
                        f'Could not build all selective-irrigation seals: {seal_message}')

                for index, seal in enumerate(list(seal_objects)):
                    ok, _solver = apply_boolean_union_exact(
                        context, export_work, seal,
                        mod_name=f'DSG_ExportSealUnion_{index:02d}',
                        robust=True, cleanup_cutter=True)
                    if not ok:
                        raise RuntimeError(
                            f'Could not fuse the seal for {seal.get("DSG_implant_name", index + 1)}')
                    safe_remove_object_with_data(seal)
                seal_objects = []

                # Perforation marks: countersink around every sealed outlet and the
                # engraved opening-order digit. Material is only removed.
                mark_cutters, mark_notes = build_export_frangible_mark_cutters(
                    context, props, export_work)
                seal_objects = list(mark_cutters)
                for index, cutter in enumerate(list(mark_cutters)):
                    ok, message = apply_difference_exact_checked(
                        context, export_work, cutter, f'DSG_ExportMark_{index:02d}',
                        robust_retry=True)
                    if not ok:
                        raise RuntimeError(
                            f'Could not cut the perforation mark {cutter.name}: {message}')
                    safe_remove_object_with_data(cutter)
                seal_objects = []
                if mark_notes:
                    _DSG_LOG.warning('frangible marks: %s', '; '.join(mark_notes))
                    islands_msg = (islands_msg + ' · ' if islands_msg else '') + '; '.join(mark_notes)

                report = get_mesh_solid_report(export_work, max_polygons=1200000)
                if report.get('checked') and not report.get('solid'):
                    raise RuntimeError(
                        f'Sealed export is not solid: edges={report.get("bad_edges", 0)}, '
                        f'degenerate={report.get("degenerate_faces", 0)}')
                try:
                    export_work['DSG_export_frangible_seal_count'] = int(len(sealed_implants))
                    export_work['DSG_export_frangible_seal_center_thickness_mm'] = float(
                        IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED)
                    export_work['DSG_export_frangible_seal_rim_thickness_mm'] = float(
                        IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED)
                    export_work['DSG_export_frangible_seal_mode'] = IRRIGATION_FRANGIBLE_SEAL_MODE
                    export_work['DSG_export_frangible_marker_shape'] = FRANGIBLE_MARKER_SHAPE
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                export_obj = export_work

            if export_obj is None:
                export_obj = export_work

            try:
                export_obj.hide_viewport = False
                export_obj.hide_set(False)
                export_obj.hide_select = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            from .guide_export import blender_adapter as export_adapter
            export_adapter.triangulate_for_stl(export_obj)
            gate_checks.extend(gate.check_solid(export_obj))
            blocking = [c for c in gate_checks if c.blocking]
            if blocking:
                raise RuntimeError(
                    '; '.join(c.message for c in blocking)
                    + '. Repair the guide or tick "Allow non-closed mesh"')
            try:
                from .guide_export import blender_adapter as export_adapter
                gate_checks.extend(gate.check_anatomy(
                    get_all_implant_objects(props), export_adapter.find_mandibular_canal()))
            except Exception as exc:
                _DSG_LOG.warning('anatomy clearance skipped: %s', exc, exc_info=True)

            deselect_all_objects()
            export_obj.select_set(True)
            context.view_layer.objects.active = export_obj
            new_export_error = None
            try:
                # Exactly one transactional object is exported.
                bpy.ops.wm.stl_export(
                    filepath=self.filepath,
                    export_selected_objects=True,
                    # use_batch=True makes Blender append the object name to
                    # the file name (…DSG_ExportGuide_Work.stl). Exactly one
                    # transactional object is exported, so write it verbatim.
                    use_batch=False,
                    apply_modifiers=True,
                )
            except Exception as exc:
                new_export_error = exc
                try:
                    bpy.ops.export_mesh.stl(
                        filepath=self.filepath,
                        use_selection=True,
                        batch_mode='OFF',
                        use_mesh_modifiers=True,
                        check_existing=True,
                    )
                except Exception as legacy_exc:
                    raise RuntimeError(
                        f'Export error: {new_export_error} | fallback: {legacy_exc}')
        except Exception as exc:
            _dsg_report(
                self, {'ERROR'},
                f'Export canceled: {exc}. The original guide was preserved.',
                f'Exportación cancelada: {exc}. La guía original se conservó.')
            return {'CANCELLED'}
        finally:
            for seal in list(seal_objects):
                if _valid_obj(seal):
                    safe_remove_object_with_data(seal)
            if _valid_obj(export_work):
                safe_remove_object_with_data(export_work)

        report_note = ''
        if self.write_report:
            try:
                from .guide_export import blender_adapter as export_adapter
                from .guide_export import report as export_report
                ctx = export_adapter.read_export_context(
                    context, sys.modules[__name__],
                    operator_options={k: getattr(self, k) for k in (
                        'confirm_island_removal', 'allow_non_manifold', 'check_wall_thickness',
                        'min_wall_thickness_mm', 'min_canal_distance_mm')})
                geometry = next((c for c in gate_checks if c.name == 'geometry'), None)
                ctx.geometry = dict(geometry.metrics) if geometry else {}
                written = export_report.write_report(
                    export_report.build_report(
                        ctx, [c for c in gate_checks if c.name != 'geometry'], self.filepath,
                        stl_sha256=export_report.sha256_file(self.filepath)),
                    self.filepath)
                report_note = f' · report: {os.path.basename(str(written))}'
            except Exception as exc:
                _DSG_LOG.error('traceability report failed: %s', exc, exc_info=True)
                report_note = f' · REPORT NOT WRITTEN: {exc}'
        gate_note = ' · ' + export_service.summarize(
            [c for c in gate_checks if c.name != 'geometry'])
        suffix = (f' · {islands_msg}' if removed_components else '') + gate_note + report_note
        seal_suffix_en = (
            f' · {len(sealed_implants)} experimental export seal(s), '
            f'{IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED:.2f}/{IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED:.2f} mm center/rim'
            if sealed_implants else '')
        seal_suffix_es = (
            f' · {len(sealed_implants)} sello(s) experimental(es) de exportación, '
            f'{IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED:.2f}/{IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED:.2f} mm centro/borde'
            if sealed_implants else '')
        level = {'WARNING'} if any(c.status in ('WARN', 'FAIL') for c in gate_checks) else {'INFO'}
        _dsg_report(
            self, level,
            f'Exported: {self.filepath}{suffix}{seal_suffix_en}',
            f'Exportada: {self.filepath}{suffix}{seal_suffix_es}')
        restore_precision_projection(context)
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Controles de visibilidad para revisión final
# ─────────────────────────────────────────────────────────────

class DSG_OT_ToggleBlockoutVisibility(Operator):
    bl_idname = "dsg.toggle_blockout_visibility"
    bl_label  = "Show/Hide Model"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        targets = get_blockout_visibility_objects(props)
        shown, valid = _toggle_visibility_for_objects(targets)
        if shown is None:
            _dsg_report(self, {'ERROR'}, "DSG_PassiveCombined was not found", "No se encontró el modelo final DSG_PassiveCombined")
            return {'CANCELLED'}
        passive = get_passive_model_obj()
        if _valid_obj(passive):
            props.dct_object_making_cut = passive
        state = "shown" if shown else "hidden"
        _dsg_report(self, {'INFO'}, f"Model {state}: {', '.join(o.name for o in valid)}", f"Modelo {state}: {', '.join(o.name for o in valid)}")
        return {'FINISHED'}



class DSG_OT_ToggleGuideVisibility(Operator):
    bl_idname = "dsg.toggle_guide_visibility"
    bl_label  = "Show/Hide Guide"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        targets = get_guide_visibility_objects(props)
        shown, valid = _toggle_visibility_for_objects(targets)
        if shown is None:
            _dsg_report(self, {'ERROR'}, "DSG_Guide not found", "No se encontró DSG_Guide")
            return {'CANCELLED'}
        props.guide_obj = valid[0]
        props.dct_object_being_cut = valid[0]
        state = "shown" if shown else "hidden"
        _dsg_report(self, {'INFO'}, f"Guide {state}: {', '.join(o.name for o in valid)}", f"Guía {state}: {', '.join(o.name for o in valid)}")
        return {'FINISHED'}


def _final_cbct_stl_objects(context):
    """Return only the 3D STL meshes generated from the CBCT segmentation.

    MPR planes, radiographic display objects, volume helpers and measurements
    are deliberately excluded from the final visualization step.
    """
    result = []
    for obj in list(context.scene.objects):
        if not _valid_obj(obj) or obj.type != 'MESH':
            continue
        role = _suite_role(obj)
        name = str(getattr(obj, 'name', ''))
        is_cbct_mesh = (
            role in {ROLE_DICOM_TEETH_SUITE, ROLE_DICOM_BONE_SUITE}
            or name.startswith('STL_Dientes')
            or name.startswith('STL_Hueso')
            or name.startswith('Dental_DICOM_Teeth')
            or name.startswith('Dental_DICOM_Bone')
        )
        if is_cbct_mesh:
            result.append(obj)
    return result


def _prepare_final_overlay_view(context, props):
    """Prepare the final review without hiding the surgical guide.

    The guide is the principal object. Model and CBCT STL are independent
    reference layers that can be toggled while the guide remains visible.
    Previous MPR/radiographic review helpers and measurements are closed.
    """
    _close_dicom_review_for_guide(context)
    _set_dicom_measurements_visibility(False)

    # The guide must always remain visible during final inspection.
    guide_targets = get_guide_visibility_objects(props)
    for obj in guide_targets:
        _set_obj_hidden(obj, False, selectable_when_visible=True)
    if guide_targets:
        props.guide_obj = guide_targets[0]
        props.dct_object_being_cut = guide_targets[0]
    return guide_targets


def _toggle_final_reference_layer(targets):
    """Toggle one final reference layer without changing other visible layers."""
    valid = [obj for obj in targets if _valid_obj(obj)]
    if not valid:
        return None, []
    # If at least one object is hidden, show the complete layer; otherwise hide it.
    show_layer = any(obj.hide_get() for obj in valid)
    for obj in valid:
        _set_obj_hidden(obj, not show_layer, selectable_when_visible=True)
        if show_layer:
            try:
                for collection in obj.users_collection:
                    collection.hide_viewport = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return show_layer, valid


class DSG_OT_FinalViewModel(Operator):
    bl_idname = "dsg.final_view_model"
    bl_label = "Toggle Model Layer"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        targets = get_blockout_visibility_objects(props)
        if not targets:
            _dsg_report(self, {'ERROR'}, 'Final model not found', 'No se encontró el modelo final')
            return {'CANCELLED'}
        guide_targets = _prepare_final_overlay_view(context, props)
        shown, valid = _toggle_final_reference_layer(targets)
        if shown and valid:
            set_active(context, guide_targets[0] if guide_targets else valid[0])
        _set_solid_view_original_colors(context)
        state_en = 'shown with the guide' if shown else 'hidden; guide remains visible'
        state_es = 'visible junto con la férula' if shown else 'oculto; la férula permanece visible'
        _dsg_report(self, {'INFO'}, f'Model layer {state_en}', f'Capa Modelo {state_es}')
        return {'FINISHED'}


class DSG_OT_FinalViewCBCTSTL(Operator):
    bl_idname = "dsg.final_view_cbct_stl"
    bl_label = "Toggle CBCT STL Layer"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        targets = _final_cbct_stl_objects(context)
        if not targets:
            _dsg_report(
                self, {'ERROR'},
                'No CBCT STL segmentation was found',
                'No se encontró ningún STL generado desde el CBCT')
            return {'CANCELLED'}
        guide_targets = _prepare_final_overlay_view(context, props)
        shown, valid = _toggle_final_reference_layer(targets)
        if shown and valid:
            set_active(context, guide_targets[0] if guide_targets else valid[0])
        _set_solid_view_original_colors(context)
        state_en = 'shown with the guide and current layers' if shown else 'hidden; guide and other layers remain visible'
        state_es = 'visible junto con la férula y las capas actuales' if shown else 'oculto; la férula y las demás capas permanecen visibles'
        _dsg_report(self, {'INFO'}, f'CBCT STL layer {state_en}', f'Capa STL CBCT {state_es}')
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Edge loops + corte final preservando geometría contra modelo + blockout
# ─────────────────────────────────────────────────────────────

FINAL_CUT_SOLID_CUTTER_NAME = "DSG_FinalCut_SolidPassiveCutter"
FINAL_CUT_SHRINKWRAP_PROXY_NAME = "DSG_FinalCut_ShrinkwrapProxy"


def apply_object_scale_for_final(context, obj):
    """Aplica únicamente la escala para que el voxel esté expresado en milímetros reales."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False
    ensure_object_mode(context)
    set_active(context, obj)
    try:
        with context.temp_override(object=obj, active_object=obj,
                                   selected_objects=[obj],
                                   selected_editable_objects=[obj]):
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return True
    except Exception:
        try:
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            return True
        except Exception as exc:
            print(f'[DSG] Could not apply scale before remesh: {exc}')
            return False


def apply_final_voxel_remesh(context, obj, voxel_size, modifier_name):
    """Convierte una malla o conjunto de shells en una única superficie voxelizada."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False, 'invalid object'

    apply_object_scale_for_final(context, obj)
    ensure_object_mode(context)
    set_active(context, obj)

    before = len(obj.data.polygons) if obj.data else 0
    mod = obj.modifiers.new(modifier_name, 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = max(0.04, float(voxel_size))
    try:
        mod.use_smooth_shade = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if not apply_modifier_direct(context, obj, mod.name):
        return False, 'Voxel Remesh failed'

    try:
        obj.data.validate(clean_customdata=False)
        obj.data.update()
        for poly in obj.data.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    after = len(obj.data.polygons) if obj.data else 0
    if after == 0:
        return False, 'Voxel Remesh produced an empty mesh'
    return True, f'voxel {float(voxel_size):.3f} mm · {before}→{after} caras'


def decimate_final_mesh(context, obj, target_faces, modifier_name):
    """Reduce polígonos con Collapse únicamente cuando supera el objetivo."""
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return False, 'invalid object for reduction'

    before = len(obj.data.polygons)
    target = max(1000, int(target_faces))
    if before <= target:
        return True, f'reduction skipped · {before} caras'

    ratio = max(0.03, min(1.0, float(target) / float(max(1, before))))
    ensure_object_mode(context)
    set_active(context, obj)
    mod = obj.modifiers.new(modifier_name, 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    try:
        mod.use_collapse_triangulate = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if not apply_modifier_direct(context, obj, mod.name):
        return False, 'polygon reduction failed'

    try:
        obj.data.validate(clean_customdata=False)
        obj.data.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    after = len(obj.data.polygons) if obj.data else 0
    return True, f'Decimate {before}→{after} caras'


def build_final_solid_cutter(context, passive_obj, voxel_size=0.18,
                             target_faces=260000):
    """Prepara modelo + blockout como cutter sólido y ligero.

    El Voxel Remesh y el Decimate se validan por separado. Si aparecen unas
    pocas edges abiertas, se intenta un cierre local. Si el Decimate es quien
    abre la malla, se recupera automáticamente la versión solid previa y se
    continúa con más polígonos en vez de cancelar el corte final.
    """
    if not _valid_obj(passive_obj) or passive_obj.type != 'MESH':
        return None, 'invalid passive model'

    safe_remove_temp_by_name(FINAL_CUT_SOLID_CUTTER_NAME)
    cutter = duplicate_object_with_data(context, passive_obj, FINAL_CUT_SOLID_CUTTER_NAME)
    if not _valid_obj(cutter):
        return None, 'could not duplicate the blockout model'

    cutter.name = FINAL_CUT_SOLID_CUTTER_NAME
    cutter.data.name = FINAL_CUT_SOLID_CUTTER_NAME + '_Mesh'
    cutter.display_type = 'WIRE'
    cutter.show_in_front = True
    cutter.hide_select = True
    _set_obj_hidden(cutter, False, selectable_when_visible=False)
    register_dsg_object(cutter, ROLE_CUTTER, FINAL_CUT_SOLID_CUTTER_NAME)

    ok, remesh_msg = apply_final_voxel_remesh(
        context, cutter, voxel_size, 'DSG_Final_BlockoutVoxel')
    if not ok:
        safe_remove_object_with_data(cutter)
        return None, remesh_msg

    stage_messages = [remesh_msg]

    # Validar inmediatamente tras el Voxel Remesh. Normalmente ya debería ser
    # sólido; cuando deja un orificio diminuto, lo cerramos localmente.
    remesh_report = get_mesh_solid_report(cutter, max_polygons=900000)
    if remesh_report.get('checked') and not remesh_report.get('solid'):
        repaired, repair_msg, repaired_report = repair_small_final_nonmanifold(
            cutter, max_bad_edges=48)
        if repaired:
            stage_messages.append(repair_msg + ' tras remesh')
            remesh_report = repaired_report or get_mesh_solid_report(cutter, max_polygons=900000)
        if remesh_report.get('checked') and not remesh_report.get('solid'):
            bad = remesh_report.get('bad_edges', '?')
            deg = remesh_report.get('degenerate_faces', '?')
            safe_remove_object_with_data(cutter)
            return None, (
                f'modelo blockout no sólido inmediatamente tras Voxel Remesh: '
                f'aristas={bad}, degeneradas={deg}; {repair_msg}')

    # El Decimate puede abrir pequeños triángulos. Conservamos una copia solid
    # previa para revertir solo esta reducción cuando sea necesario.
    pre_decimate_mesh = cutter.data.copy()
    ok, decimate_msg = decimate_final_mesh(
        context, cutter, target_faces, 'DSG_Final_BlockoutDecimate')
    if not ok:
        _restore_object_mesh_copy(cutter, pre_decimate_mesh)
        pre_decimate_mesh = None
        decimate_msg = 'Decimate skipped because it failed; preserving the solid voxelized blockout'
        stage_messages.append(decimate_msg)
    else:
        stage_messages.append(decimate_msg)
        decimated_report = get_mesh_solid_report(cutter, max_polygons=900000)
        if decimated_report.get('checked') and not decimated_report.get('solid'):
            repaired, repair_msg, repaired_report = repair_small_final_nonmanifold(
                cutter, max_bad_edges=48)
            if repaired:
                stage_messages.append(repair_msg + ' tras Decimate')
                decimated_report = repaired_report or get_mesh_solid_report(cutter, max_polygons=900000)

            if decimated_report.get('checked') and not decimated_report.get('solid'):
                # La reducción abrió la malla. Recuperamos la versión solid
                # previa, que suele tener más caras pero es segura para Boolean.
                _restore_object_mesh_copy(cutter, pre_decimate_mesh)
                pre_decimate_mesh = None
                restored_report = get_mesh_solid_report(cutter, max_polygons=900000)
                if restored_report.get('checked') and not restored_report.get('solid'):
                    repaired_backup, backup_msg, restored_report = repair_small_final_nonmanifold(
                        cutter, max_bad_edges=48)
                    if repaired_backup:
                        stage_messages.append(backup_msg + ' en backup previo al Decimate')
                if restored_report.get('checked') and not restored_report.get('solid'):
                    bad = restored_report.get('bad_edges', '?')
                    deg = restored_report.get('degenerate_faces', '?')
                    safe_remove_object_with_data(cutter)
                    return None, (
                        f'modelo blockout no sólido incluso tras revertir Decimate: '
                        f'aristas={bad}, degeneradas={deg}')
                stage_messages.append(
                    'Decimate reverted because it opened the mesh; preserving the solid cutter with more polygons')

        if pre_decimate_mesh is not None:
            try:
                if pre_decimate_mesh.users == 0:
                    bpy.data.meshes.remove(pre_decimate_mesh)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    final_report = get_mesh_solid_report(cutter, max_polygons=900000)
    if final_report.get('checked') and not final_report.get('solid'):
        repaired, repair_msg, final_report = repair_small_final_nonmanifold(
            cutter, max_bad_edges=48)
        if repaired:
            stage_messages.append(repair_msg + ' during final validation')
    if final_report.get('checked') and not final_report.get('solid'):
        bad = final_report.get('bad_edges', '?')
        deg = final_report.get('degenerate_faces', '?')
        safe_remove_object_with_data(cutter)
        return None, (
            f'modelo blockout no sólido tras preparación: '
            f'aristas={bad}, degeneradas={deg}')

    try:
        cutter['DSG_final_cutter_voxel'] = float(voxel_size)
        cutter['DSG_final_cutter_target_faces'] = int(target_faces)
        cutter['DSG_final_cutter_repair'] = ' | '.join(stage_messages)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return cutter, ' · '.join(stage_messages)



def _object_local_bounds(obj):
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None, None
    try:
        corners = [Vector(corner) for corner in obj.bound_box]
    except Exception:
        corners = []
    if not corners:
        return None, None
    minimum = Vector((
        min(v.x for v in corners),
        min(v.y for v in corners),
        min(v.z for v in corners),
    ))
    maximum = Vector((
        max(v.x for v in corners),
        max(v.y for v in corners),
        max(v.z for v in corners),
    ))
    return minimum, maximum


def _object_world_bounds_center(obj):
    if not _valid_obj(obj):
        return Vector((0.0, 0.0, 0.0))
    try:
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return sum(corners, Vector((0.0, 0.0, 0.0))) / float(len(corners))
    except Exception:
        try:
            return obj.matrix_world.translation.copy()
        except Exception:
            return Vector((0.0, 0.0, 0.0))


def _trim_unprojected_proxy_vertices(proxy, start_z, tolerance):
    """Elimina celdas del grid que Shrinkwrap no logró proyectar.

    En modo Project, los vértices sin intersección permanecen exactamente sobre
    el plano base. Al borrarlos desaparecen también las caras que atravesarían
    huecos externos del STL y queda únicamente la huella anatómica proyectada.
    """
    if not _valid_obj(proxy) or proxy.type != 'MESH' or proxy.data is None:
        return False, 0, 0
    bm = bmesh.new()
    try:
        bm.from_mesh(proxy.data)
        bm.verts.ensure_lookup_table()
        unprojected = [
            vert for vert in bm.verts
            if abs(float(vert.co.z) - float(start_z)) <= float(tolerance)
        ]
        projected_count = len(bm.verts) - len(unprojected)
        if unprojected:
            bmesh.ops.delete(bm, geom=unprojected, context='VERTS')
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(proxy.data)
        proxy.data.validate(clean_customdata=False)
        proxy.data.update(calc_edges=True)
        return projected_count > 0 and len(proxy.data.polygons) > 0, projected_count, len(proxy.data.polygons)
    except Exception as exc:
        print(f'[DSG] Could not trim Shrinkwrap proxy: {exc}')
        return False, 0, 0
    finally:
        bm.free()


def build_final_shrinkwrap_proxy_cutter(context, passive_obj, guide_obj,
                                         voxel_size=0.18,
                                         target_faces=260000):
    """Construye un cutter sólido de tipo height-field para STL intraoral abierto.

    1. Crea un grid regular con topología controlada.
    2. Lo proyecta en Z hacia la superficie dental mediante Shrinkwrap/Project.
    3. Elimina las celdas sin impacto.
    4. Solidify añade volumen únicamente en el lado opuesto a la guía.
    5. Voxel Remesh sella la proxy y Decimate limita su coste booleano.

    La malla intraoral original nunca se modifica. La proxy es temporal y se
    elimina, junto con su datablock, al terminar el corte final.
    """
    if not _valid_obj(passive_obj) or passive_obj.type != 'MESH':
        return None, 'invalid passive model for Shrinkwrap proxy'
    if not _valid_obj(guide_obj) or guide_obj.type != 'MESH':
        return None, 'invalid guide for Shrinkwrap proxy orientation'

    safe_remove_temp_by_name(FINAL_CUT_SHRINKWRAP_PROXY_NAME)

    local_min, local_max = _object_local_bounds(passive_obj)
    if local_min is None or local_max is None:
        return None, 'could not read the passive-model bounds'

    try:
        scale = passive_obj.matrix_world.to_scale()
        sx = max(abs(float(scale.x)), 1.0e-6)
        sy = max(abs(float(scale.y)), 1.0e-6)
        sz = max(abs(float(scale.z)), 1.0e-6)
    except Exception:
        sx = sy = sz = 1.0

    width_local = max(1.0e-5, float(local_max.x - local_min.x))
    depth_local_xy = max(1.0e-5, float(local_max.y - local_min.y))
    height_local = max(1.0e-5, float(local_max.z - local_min.z))
    width_mm = width_local * sx
    depth_mm_xy = depth_local_xy * sy
    height_mm = height_local * sz

    margin_mm = max(1.0, float(voxel_size) * 6.0)
    desired_step_mm = max(0.22, min(0.55, float(voxel_size) * 1.55))
    max_grid_vertices = 180000
    area_mm2 = max(1.0, (width_mm + 2.0 * margin_mm) * (depth_mm_xy + 2.0 * margin_mm))
    area_limited_step = math.sqrt(area_mm2 / float(max_grid_vertices))
    grid_step_mm = max(desired_step_mm, area_limited_step)

    x_min = float(local_min.x) - margin_mm / sx
    x_max = float(local_max.x) + margin_mm / sx
    y_min = float(local_min.y) - margin_mm / sy
    y_max = float(local_max.y) + margin_mm / sy
    nx = max(8, int(math.ceil(((x_max - x_min) * sx) / grid_step_mm)) + 1)
    ny = max(8, int(math.ceil(((y_max - y_min) * sy) / grid_step_mm)) + 1)
    nx = min(nx, 600)
    ny = min(ny, 600)

    # Decide qué lado contiene la férula. La superficie proyectada se conserva
    # y Solidify crece exclusivamente hacia el lado contrario.
    guide_center_world = _object_world_bounds_center(guide_obj)
    try:
        guide_center_local = passive_obj.matrix_world.inverted_safe() @ guide_center_world
    except Exception:
        guide_center_local = Vector((0.0, 0.0, (local_min.z + local_max.z) * 0.5))
    distance_top = abs(float(guide_center_local.z) - float(local_max.z))
    distance_bottom = abs(float(guide_center_local.z) - float(local_min.z))
    project_from_top = distance_top <= distance_bottom

    z_margin_local = margin_mm / sz
    if project_from_top:
        start_z = float(local_max.z) + z_margin_local
        use_positive = False
        use_negative = True
        solidify_offset = -1.0
        projection_side = 'TOP_TO_BOTTOM'
    else:
        start_z = float(local_min.z) - z_margin_local
        use_positive = True
        use_negative = False
        solidify_offset = 1.0
        projection_side = 'BOTTOM_TO_TOP'

    vertices = []
    for iy in range(ny):
        ty = float(iy) / float(max(1, ny - 1))
        y = y_min + (y_max - y_min) * ty
        for ix in range(nx):
            tx = float(ix) / float(max(1, nx - 1))
            x = x_min + (x_max - x_min) * tx
            vertices.append((x, y, start_z))

    faces = []
    for iy in range(ny - 1):
        row = iy * nx
        next_row = (iy + 1) * nx
        for ix in range(nx - 1):
            a = row + ix
            b = a + 1
            c = next_row + ix + 1
            d = next_row + ix
            faces.append((a, b, c, d))

    mesh = bpy.data.meshes.new(FINAL_CUT_SHRINKWRAP_PROXY_NAME + '_Mesh')
    proxy = bpy.data.objects.new(FINAL_CUT_SHRINKWRAP_PROXY_NAME, mesh)
    try:
        mesh.from_pydata(vertices, [], faces)
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        proxy.matrix_world = passive_obj.matrix_world.copy()
        link_object(context, proxy)
        proxy.display_type = 'WIRE'
        proxy.show_in_front = True
        proxy.hide_select = True
        _set_obj_hidden(proxy, False, selectable_when_visible=False)
        register_dsg_object(proxy, ROLE_CUTTER, FINAL_CUT_SHRINKWRAP_PROXY_NAME, {
            'DSG_final_proxy_method': 'SHRINKWRAP_PROJECT_SOLIDIFY',
            'DSG_final_proxy_projection_side': projection_side,
        })

        shrink = proxy.modifiers.new('DSG_Final_ShrinkwrapProject', 'SHRINKWRAP')
        shrink.target = passive_obj
        shrink.wrap_method = 'PROJECT'
        try:
            shrink.wrap_mode = 'ON_SURFACE'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        shrink.project_axis = 'Z'
        shrink.use_positive_direction = bool(use_positive)
        shrink.use_negative_direction = bool(use_negative)
        shrink.project_limit = max(
            1.0,
            (height_mm + margin_mm * 4.0) / sz,
        )
        try:
            shrink.cull_face = 'OFF'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            shrink.offset = 0.0
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        if not apply_modifier_direct(context, proxy, shrink.name):
            safe_remove_object_with_data(proxy)
            return None, 'Shrinkwrap Project modifier failed'

        trim_tolerance = max(1.0e-5, (margin_mm / sz) * 0.05)
        trimmed, projected_count, projected_faces = _trim_unprojected_proxy_vertices(
            proxy, start_z, trim_tolerance)
        if not trimmed or projected_count < 64 or projected_faces < 32:
            safe_remove_object_with_data(proxy)
            return None, (
                f'Shrinkwrap projected too little anatomy: '
                f'{projected_count} vertices / {projected_faces} faces')

        islands_ok, islands_msg, _removed_faces, _removed_components = (
            remove_disconnected_islands_keep_largest(
                proxy, reason='final_shrinkwrap_projection'))
        if not islands_ok:
            safe_remove_object_with_data(proxy)
            return None, f'could not isolate the projected dental surface: {islands_msg}'

        # Enough depth to extend beyond the whole dental scan, but always away
        # from the guide so the seating surface remains the Shrinkwrap result.
        solid_depth_mm = max(8.0, min(60.0, height_mm + margin_mm * 4.0))
        solid = proxy.modifiers.new('DSG_Final_ProxySolidify', 'SOLIDIFY')
        solid.thickness = solid_depth_mm / sz
        solid.offset = float(solidify_offset)
        try:
            solid.use_rim = True
            solid.use_rim_only = False
            solid.use_even_offset = True
            solid.use_quality_normals = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not apply_modifier_direct(context, proxy, solid.name):
            safe_remove_object_with_data(proxy)
            return None, 'Solidify failed on the Shrinkwrap proxy'

        ok, remesh_msg = apply_final_voxel_remesh(
            context, proxy, voxel_size, 'DSG_Final_ProxyVoxel')
        if not ok:
            safe_remove_object_with_data(proxy)
            return None, f'proxy voxel sealing failed: {remesh_msg}'

        islands_ok, islands_msg, _removed_faces, _removed_components = (
            remove_disconnected_islands_keep_largest(
                proxy, reason='final_shrinkwrap_proxy_voxel'))
        if not islands_ok:
            safe_remove_object_with_data(proxy)
            return None, f'proxy island cleanup failed: {islands_msg}'

        ok, decimate_msg = decimate_final_mesh(
            context, proxy, target_faces, 'DSG_Final_ProxyDecimate')
        if not ok:
            decimate_msg = 'proxy Decimate skipped because it failed'

        report = get_mesh_solid_report(proxy, max_polygons=900000)
        if report.get('checked') and not report.get('solid'):
            repaired, repair_msg, report = repair_small_final_nonmanifold(
                proxy, max_bad_edges=48)
            if not repaired:
                safe_remove_object_with_data(proxy)
                return None, (
                    f'Shrinkwrap proxy remained non-manifold: '
                    f'edges={report.get("bad_edges", "?")}; {repair_msg}')
        else:
            repair_msg = 'proxy solid without local repair'

        try:
            proxy['DSG_final_proxy_grid_mm'] = float(grid_step_mm)
            proxy['DSG_final_proxy_projected_vertices'] = int(projected_count)
            proxy['DSG_final_proxy_projected_faces'] = int(projected_faces)
            proxy['DSG_final_proxy_solid_depth_mm'] = float(solid_depth_mm)
            proxy['DSG_final_proxy_voxel_mm'] = float(voxel_size)
            proxy['DSG_final_proxy_target_faces'] = int(target_faces)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        return proxy, (
            f'Shrinkwrap proxy {projection_side.lower()} · grid {grid_step_mm:.3f} mm · '
            f'{projected_count} projected vertices · Solidify {solid_depth_mm:.1f} mm · '
            f'{remesh_msg} · {decimate_msg} · {repair_msg}')
    except Exception as exc:
        safe_remove_object_with_data(proxy)
        return None, f'Shrinkwrap proxy creation failed: {exc}'


def build_final_cutter_auto(context, passive_obj, guide_obj, voxel_size=0.18,
                            target_faces=260000, use_shrinkwrap_proxy=True):
    """Selecciona automáticamente cutter voxel normal o proxy Shrinkwrap."""
    report = get_mesh_solid_report(passive_obj, max_polygons=900000)
    source_is_open = bool(report.get('checked') and not report.get('solid'))
    attempts = []

    if use_shrinkwrap_proxy and source_is_open:
        cutter, message = build_final_shrinkwrap_proxy_cutter(
            context, passive_obj, guide_obj,
            voxel_size=voxel_size, target_faces=target_faces)
        attempts.append('open STL → ' + message)
        if _valid_obj(cutter):
            return cutter, ' · '.join(attempts), 'SHRINKWRAP_PROXY'

    cutter, message = build_final_solid_cutter(
        context, passive_obj, voxel_size=voxel_size,
        target_faces=target_faces)
    attempts.append('voxel cutter → ' + message)
    if _valid_obj(cutter):
        return cutter, ' · '.join(attempts), 'VOXEL_CUTTER'

    if use_shrinkwrap_proxy and not source_is_open:
        cutter, message = build_final_shrinkwrap_proxy_cutter(
            context, passive_obj, guide_obj,
            voxel_size=voxel_size, target_faces=target_faces)
        attempts.append('voxel failed → ' + message)
        if _valid_obj(cutter):
            return cutter, ' · '.join(attempts), 'SHRINKWRAP_PROXY'

    return None, ' · '.join(attempts), 'FAILED'

def get_supported_boolean_solvers(mod):
    try:
        prop = mod.bl_rna.properties.get('solver')
        return {item.identifier for item in prop.enum_items}
    except Exception:
        return {'EXACT'}


def apply_final_boolean_prepared(context, guide_obj, cutter_obj):
    """Applies the final DIFFERENCE transactionally and validates each solver.

    Blender may report that a MANIFOLD/EXACT modifier was applied successfully
    even when the resulting mesh contains open edges. The previous workflow
    accepted that result immediately. Here every attempt starts from the same
    untouched guide mesh and is accepted only when the output is actually solid.
    """
    if not _valid_obj(guide_obj) or not _valid_obj(cutter_obj):
        return False, None

    test_mod = guide_obj.modifiers.new('DSG_Final_BooleanSolverProbe', 'BOOLEAN')
    supported = get_supported_boolean_solvers(test_mod)
    try:
        guide_obj.modifiers.remove(test_mod)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    candidates = ['MANIFOLD', 'EXACT'] if 'MANIFOLD' in supported else ['EXACT']
    source_mesh = guide_obj.data.copy()
    last_solver = candidates[-1] if candidates else None
    last_report = None

    try:
        for attempt_index, solver in enumerate(candidates):
            if attempt_index > 0:
                _restore_object_mesh_copy(guide_obj, source_mesh.copy())

            mod = guide_obj.modifiers.new(f'DSG_Final_Difference_{solver}', 'BOOLEAN')
            mod.operation = 'DIFFERENCE'
            mod.object = cutter_obj
            try:
                mod.solver = solver
            except Exception:
                try:
                    guide_obj.modifiers.remove(mod)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                continue

            # EXACT is the robust fallback. MANIFOLD remains the fast first
            # attempt, but it is never accepted without a solid-mesh audit.
            set_boolean_exact_options(mod, robust=(solver == 'EXACT'))
            applied = apply_modifier_direct(context, guide_obj, mod.name)
            if not applied:
                try:
                    if mod.name in guide_obj.modifiers:
                        guide_obj.modifiers.remove(mod)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                continue

            report = get_mesh_solid_report(guide_obj, max_polygons=900000)
            last_report = report
            if not report.get('checked') or report.get('solid'):
                try:
                    guide_obj['DSG_final_boolean_validated_solver'] = str(solver)
                    guide_obj['DSG_final_boolean_transactional_validation'] = True
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                try:
                    if source_mesh.users == 0:
                        bpy.data.meshes.remove(source_mesh)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                return True, solver

            print(
                f'[DSG] Final Boolean {solver} rejected after validation: '
                f'edges={report.get("bad_edges", "?")}, '
                f'degenerate={report.get("degenerate_faces", "?")}')

        # Every solver failed or produced an invalid mesh. Restore the exact
        # pre-Boolean guide so the caller can cancel without leaving damage.
        _restore_object_mesh_copy(guide_obj, source_mesh)
        source_mesh = None
        if last_report:
            try:
                guide_obj['DSG_final_boolean_last_bad_edges'] = int(
                    last_report.get('bad_edges') or 0)
                guide_obj['DSG_final_boolean_last_degenerate_faces'] = int(
                    last_report.get('degenerate_faces') or 0)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return False, last_solver
    finally:
        if source_mesh is not None:
            try:
                if source_mesh.users == 0:
                    bpy.data.meshes.remove(source_mesh)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def repair_small_final_nonmanifold(obj, max_bad_edges=24):
    """Cierra únicamente aberturas finales pequeñas sin remallar toda la guía.

    Está pensado para el caso típico de 3 edges abiertas después del Boolean o
    del Decimate. Solo actúa cuando todas las edges defectuosas son bordes de
    contorno (una cara), forman bucles cerrados y el total no supera el límite.
    Nunca intenta reparar edges con más de dos caras ni agujeros grandes.
    """
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return False, 'invalid final object', None

    before = get_mesh_solid_report(obj, max_polygons=900000)
    if before.get('checked') and before.get('solid'):
        return True, 'the mesh was already solid', before
    if not before.get('checked'):
        return False, 'the mesh is too large for safe local repair', before

    bad_count = int(before.get('bad_edges') or 0)
    degenerate = int(before.get('degenerate_faces') or 0)
    if degenerate or bad_count <= 0 or bad_count > int(max_bad_edges):
        return False, (
            f'local repair not applicable: edges={bad_count}, '
            f'degeneradas={degenerate}'), before

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        bad_edges = [edge for edge in bm.edges if len(edge.link_faces) != 2]
        boundary = [edge for edge in bad_edges if len(edge.link_faces) == 1]
        unsafe = [edge for edge in bad_edges if len(edge.link_faces) != 1]
        if unsafe or len(boundary) != bad_count:
            return False, 'there are loose edges or edges with more than two faces; closure is not forced', before

        # Cada vértice de un contorno cerrable debe tener grado 2 dentro del
        # conjunto de bordes abiertos. Esto evita tapar grietas ramificadas.
        degree = {}
        for edge in boundary:
            for vert in edge.verts:
                degree[vert] = degree.get(vert, 0) + 1
        if not degree or any(value != 2 for value in degree.values()):
            return False, 'open boundaries do not form a small closed loop', before

        result = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
        new_faces = list(result.get('faces', [])) if isinstance(result, dict) else []
        if not new_faces:
            return False, 'Blender could not create the local cap', before

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(obj.data)
        obj.data.validate(clean_customdata=False)
        obj.data.update(calc_edges=True)
    except Exception as exc:
        return False, f'local closure failed: {exc}', before
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    after = get_mesh_solid_report(obj, max_polygons=900000)
    if after.get('checked') and after.get('solid'):
        try:
            obj['DSG_final_local_hole_repair'] = bad_count
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, f'cierre local aplicado sobre {bad_count} edges', after
    return False, (
        f'el cierre local no completó la reparación: '
        f'aristas={after.get("bad_edges", "?")}, '
        f'degeneradas={after.get("degenerate_faces", "?")}'), after


def validate_final_result_light(guide_obj):
    """Validación corta: nunca ejecuta la auditoría BMesh de millones de edges."""
    if not _valid_obj(guide_obj) or guide_obj.type != 'MESH':
        return False, 'invalid result', False
    report = get_mesh_solid_report(guide_obj, max_polygons=900000)
    if report.get('checked') and report.get('solid'):
        return True, 'SOLID verificado', True
    if report.get('checked'):
        return False, (
            f"non-manifold result: edges={report.get('bad_edges', '?')}, "
            f"degeneradas={report.get('degenerate_faces', '?')}") , True
    return True, 'large result: lightweight validation skipped', False


# DCT — Herramientas de acabado (Edge loops + Boolean Cut)
# ─────────────────────────────────────────────────────────────

class DCT_OT_VoxelRemesh(Operator):
    """Aplica Voxel Remesh al objeto activo"""
    bl_idname = "dct.voxel_remesh"
    bl_label  = "Apply Voxel Remesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        obj   = context.active_object
        if obj is None or obj.type != 'MESH':
            _dsg_report(self, {'ERROR'}, "Select a Mesh object", "Selecciona un objeto Mesh")
            return {'CANCELLED'}
        ensure_object_mode(context)
        mod                = obj.modifiers.new("VoxelRemesh_DCT", 'REMESH')
        mod.mode           = 'VOXEL'
        mod.voxel_size     = props.dct_voxel_size
        mod.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
        _dsg_report(self, {'INFO'}, f"Voxel Remesh aplicado (size={props.dct_voxel_size:.3f})", f"Voxel Remesh aplicado (size={props.dct_voxel_size:.3f})")
        return {'FINISHED'}


class DCT_OT_SelectBeingCut(Operator):
    bl_idname = "dct.select_being_cut"
    bl_label  = "Select Object Being Cut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            _dsg_report(self, {'ERROR'}, "There is no active object", "No hay objeto activo")
            return {'CANCELLED'}
        context.scene.dsg_props.dct_object_being_cut = obj
        _dsg_report(self, {'INFO'}, f"Objeto a cortar: {obj.name}", f"Objeto a cortar: {obj.name}")
        return {'FINISHED'}


class DCT_OT_SelectMakingCut(Operator):
    bl_idname = "dct.select_making_cut"
    bl_label  = "Select Object Making Cut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        obj = context.active_object
        if obj is None:
            _dsg_report(self, {'ERROR'}, "There is no active object", "No hay objeto activo")
            return {'CANCELLED'}

        passive = get_passive_model_obj()
        if passive and props.model_obj and obj == props.model_obj:
            obj = passive
            _set_obj_hidden(obj, False, selectable_when_visible=True)
            _dsg_report(self, {'INFO'}, "The original model was selected; the passive blockout model will be used automatically", "Has seleccionado el original; uso automáticamente el modelo pasivo con modelo retentivo")
        else:
            _dsg_report(self, {'INFO'}, f"Objeto cutter: {obj.name}", f"Objeto cutter: {obj.name}")

        props.dct_object_making_cut = obj
        return {'FINISHED'}


class DCT_OT_ApplyCut(Operator):
    bl_idname = "dct.apply_cut"
    bl_label  = "Apply Final Boolean"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_FINAL_CUT,
                action_en='Cannot apply the final Boolean',
                action_es='No se puede aplicar la booleana final'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        original_guide = props.dct_object_being_cut
        passive = get_confirmed_passive_model_obj()
        obj_cutter = props.dct_object_making_cut or passive

        if not _valid_obj(original_guide):
            original_guide = get_active_guide_obj(props)
        if passive and (not _valid_obj(obj_cutter) or obj_cutter == props.model_obj):
            obj_cutter = passive

        if not _valid_obj(original_guide) or original_guide.type != 'MESH':
            _dsg_report(self, {'ERROR'}, 'DSG_Guide was not found for the final cut', 'No se encontró DSG_Guide para el corte final')
            return {'CANCELLED'}
        if not _valid_obj(obj_cutter) or obj_cutter.type != 'MESH':
            _dsg_report(self, {'ERROR'}, 'DSG_PassiveCombined was not found', 'No se encontró DSG_PassiveCombined')
            return {'CANCELLED'}
        if original_guide == obj_cutter:
            _dsg_report(self, {'ERROR'}, 'The guide and blockout model cannot be the same object', 'La guía y el modelo retentivo no pueden ser el mismo objeto')
            return {'CANCELLED'}

        ensure_object_mode(context)
        _set_obj_hidden(original_guide, False, selectable_when_visible=True)
        _set_obj_hidden(obj_cutter, False, selectable_when_visible=True)

        # Transacción por copia: la guía original no se toca hasta terminar.
        # También se elimina el datablock del trabajo anterior si quedó huérfano.
        safe_remove_temp_by_name('DSG_FinalGuide_Work')
        safe_remove_temp_by_name(FINAL_CUT_SOLID_CUTTER_NAME)
        safe_remove_temp_by_name(FINAL_CUT_SHRINKWRAP_PROXY_NAME)
        work = duplicate_object_with_data(context, original_guide, 'DSG_FinalGuide_Work')
        temp_cutter = None
        if not _valid_obj(work):
            _dsg_report(self, {'ERROR'}, 'Could not create the guide working copy', 'No se pudo crear la copia de trabajo de la guía')
            return {'CANCELLED'}

        work.display_type = 'SOLID'
        _set_obj_hidden(work, False, selectable_when_visible=True)
        set_active(context, work)

        def cancel(message):
            if _valid_obj(temp_cutter):
                safe_remove_object_with_data(temp_cutter)
            if _valid_obj(work):
                safe_remove_object_with_data(work)
            _set_obj_hidden(original_guide, False, selectable_when_visible=True)
            set_active(context, original_guide)
            _dsg_report(self, {'ERROR'}, message + '. The original guide was preserved.', message + '. La guía original se conservó.')
            return {'CANCELLED'}

        guide_voxel = float(getattr(props, 'dct_final_remesh_voxel_size', 0.12))
        cutter_voxel = float(getattr(props, 'dct_final_cutter_voxel_size', 0.18))
        guide_target = int(getattr(props, 'dct_final_guide_target_faces', 220000))
        cutter_target = int(getattr(props, 'dct_final_cutter_target_faces', 260000))
        result_target = int(getattr(props, 'dct_final_result_target_faces', 180000))
        use_decimate = bool(getattr(props, 'dct_final_decimate', True))
        use_shrinkwrap_proxy = bool(
            getattr(props, 'dct_final_use_shrinkwrap_proxy', True))

        ok, guide_remesh_msg = apply_final_voxel_remesh(
            context, work, guide_voxel, 'DSG_Final_GuideVoxel')
        if not ok:
            return cancel(f'Guide remesh failed: {guide_remesh_msg}')

        if use_decimate:
            ok, guide_decimate_msg = decimate_final_mesh(
                context, work, guide_target, 'DSG_Final_GuideDecimate')
            if not ok:
                return cancel(f'Guide pre-reduction failed: {guide_decimate_msg}')
        else:
            guide_decimate_msg = 'pre-reduction disabled'

        guide_report = get_mesh_solid_report(work, max_polygons=900000)
        if guide_report.get('checked') and not guide_report.get('solid'):
            return cancel(
                f"The voxelized guide is not closed: edges={guide_report.get('bad_edges', '?')}")
        effective_cutter_target = cutter_target if use_decimate else 100000000
        temp_cutter, cutter_msg, cutter_strategy = build_final_cutter_auto(
            context, obj_cutter, work, voxel_size=cutter_voxel,
            target_faces=effective_cutter_target,
            use_shrinkwrap_proxy=use_shrinkwrap_proxy)
        if not _valid_obj(temp_cutter):
            return cancel(f'Blockout model preparation failed: {cutter_msg}')

        ok_cut, solver = apply_final_boolean_prepared(context, work, temp_cutter)
        retry_msg = ''
        if not ok_cut and use_shrinkwrap_proxy:
            # apply_final_boolean_prepared restaura exactamente la guía previa.
            # Probamos la estrategia alternativa sin acumular modificaciones.
            previous_strategy = cutter_strategy
            safe_remove_object_with_data(temp_cutter)
            temp_cutter = None
            if previous_strategy == 'SHRINKWRAP_PROXY':
                temp_cutter, alternate_msg = build_final_solid_cutter(
                    context, obj_cutter, voxel_size=cutter_voxel,
                    target_faces=effective_cutter_target)
                cutter_strategy = 'VOXEL_CUTTER_RETRY'
            else:
                temp_cutter, alternate_msg = build_final_shrinkwrap_proxy_cutter(
                    context, obj_cutter, work, voxel_size=cutter_voxel,
                    target_faces=effective_cutter_target)
                cutter_strategy = 'SHRINKWRAP_PROXY_RETRY'
            retry_msg = f' · Boolean retry after {previous_strategy}: {alternate_msg}'
            if _valid_obj(temp_cutter):
                ok_cut, solver = apply_final_boolean_prepared(context, work, temp_cutter)

        if not ok_cut:
            return cancel(
                'The final Boolean failed with both the normal cutter and the Shrinkwrap proxy' + retry_msg)

        cutter_msg += retry_msg
        safe_remove_object_with_data(temp_cutter)
        temp_cutter = None

        repair_messages = []
        islands_ok, islands_msg, _island_faces, _island_count = (
            remove_disconnected_islands_keep_largest(
                work, reason='final_boolean_result'))
        if not islands_ok:
            return cancel(islands_msg)
        if _island_count:
            repair_messages.append(islands_msg)

        # Primero se valida la salida directa del Boolean. Si solo quedan unos
        # pocos bordes abiertos, se cierran localmente sin repetir el remesh.
        solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
        if not solid_ok:
            repaired, repair_msg, _ = repair_small_final_nonmanifold(work, max_bad_edges=24)
            if not repaired:
                return cancel(f'{solid_msg}; {repair_msg}')
            repair_messages.append(repair_msg)
            solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
            if not solid_ok:
                return cancel(solid_msg)

        # Se guarda la malla solid anterior al Decimate. Si la reducción abre
        # un triángulo y la reparación local no funciona, se recupera esta copia
        # y el flujo continúa con algo más de polígonos, pero completamente sólido.
        pre_decimate_mesh = work.data.copy() if use_decimate else None
        if use_decimate:
            ok, result_decimate_msg = decimate_final_mesh(
                context, work, result_target, 'DSG_Final_ResultDecimate')
            if not ok:
                if pre_decimate_mesh is not None:
                    _restore_object_mesh_copy(work, pre_decimate_mesh)
                    pre_decimate_mesh = None
                result_decimate_msg = 'final reduction skipped because it failed; preserving the solid Boolean output'
            else:
                islands_ok, islands_msg, _island_faces, _island_count = (
                    remove_disconnected_islands_keep_largest(
                        work, reason='final_decimate_result'))
                if not islands_ok:
                    _restore_object_mesh_copy(work, pre_decimate_mesh)
                    pre_decimate_mesh = None
                    result_decimate_msg += ' · reduction reverted because island cleanup failed'
                elif _island_count:
                    repair_messages.append(islands_msg)

                solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
                if not solid_ok:
                    repaired, repair_msg, _ = repair_small_final_nonmanifold(work, max_bad_edges=24)
                    if repaired:
                        repair_messages.append(repair_msg)
                        solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
                    if not repaired or not solid_ok:
                        _restore_object_mesh_copy(work, pre_decimate_mesh)
                        pre_decimate_mesh = None
                        solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
                        if not solid_ok:
                            repaired_backup, backup_msg, _ = repair_small_final_nonmanifold(
                                work, max_bad_edges=24)
                            if repaired_backup:
                                repair_messages.append(backup_msg)
                                solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
                        if not solid_ok:
                            return cancel(solid_msg)
                        result_decimate_msg += ' · reduction reverted to preserve a solid guide'
                if pre_decimate_mesh is not None:
                    try:
                        if pre_decimate_mesh.users == 0:
                            bpy.data.meshes.remove(pre_decimate_mesh)
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
        else:
            result_decimate_msg = 'final reduction disabled'

        solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
        if not solid_ok:
            repaired, repair_msg, _ = repair_small_final_nonmanifold(work, max_bad_edges=24)
            if repaired:
                repair_messages.append(repair_msg)
                solid_ok, solid_msg, solid_verified = validate_final_result_light(work)
        if not solid_ok:
            return cancel(solid_msg)

        repair_summary = ' · '.join(repair_messages) if repair_messages else 'no local repair needed'

        original_name = _safe_object_name(original_guide)
        if original_name:
            _archive_current_guide_for_sleeve_rebuild(
                props, reason='final_cut_commit')

        work.name = GUIDE_NAME
        work.data.name = GUIDE_NAME + '_Mesh'
        _inherit_dsg_custom_properties(original_guide, work)
        try:
            work['DSG_final_pipeline'] = 'GUIDE_VOXEL_DECIMATE__AUTO_VOXEL_OR_SHRINKWRAP_PROXY__BOOLEAN_TRANSACTIONAL'
            work['DSG_final_guide_voxel'] = guide_voxel
            work['DSG_final_blockout_voxel'] = cutter_voxel
            work['DSG_final_cutter_strategy'] = str(cutter_strategy)
            work['DSG_final_shrinkwrap_proxy_enabled'] = bool(use_shrinkwrap_proxy)
            work['DSG_final_solver'] = solver or 'EXACT'
            work['DSG_final_faces'] = len(work.data.polygons)
            work['DSG_final_cut_completed'] = True
            work['DSG_workflow_state_version'] = int(WORKFLOW_STATE_VERSION)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        props.guide_obj = register_dsg_object(work, ROLE_GUIDE, GUIDE_NAME)
        props.dct_object_being_cut = props.guide_obj
        props.dct_object_making_cut = obj_cutter
        _set_obj_hidden(obj_cutter, True)
        if _valid_obj(props.model_obj):
            _set_obj_hidden(props.model_obj, True)
        _set_obj_hidden(props.guide_obj, False, selectable_when_visible=True)
        set_active(context, props.guide_obj)

        store_boolean_preflight(props.guide_obj, 'final_cut', {
            'status': 'green' if solid_verified else 'orange',
            'checked': bool(solid_verified),
            'solid': bool(solid_verified),
            'repaired': True,
            'repair_methods': [
                'Guide Voxel Remesh',
                'Shrinkwrap Proxy' if 'SHRINKWRAP' in cutter_strategy else 'Blockout Model Voxel Remesh',
                'Decimate', repair_summary],
            'cutter_strategy': cutter_strategy,
            'shrinkwrap_proxy_enabled': bool(use_shrinkwrap_proxy),
            'bad_edges': 0 if solid_verified else None,
            'degenerate_faces': 0 if solid_verified else None,
            'polygons': len(props.guide_obj.data.polygons),
            'solver': solver or 'EXACT',
            'message': (
                f'Simplified final cut completed · {guide_remesh_msg} · '
                f'{guide_decimate_msg} · {cutter_msg} · {result_decimate_msg} · {repair_summary} · {solid_msg}'
            ),
        })

        props.current_step = STEP_NAME
        strategy_label = ('Shrinkwrap proxy' if 'SHRINKWRAP' in cutter_strategy
                          else 'voxel cutter')
        _dsg_report(self, {'INFO'}, f'Final cut ready | {strategy_label} | solver={solver or "EXACT"} | '
            f'{len(props.guide_obj.data.polygons)} faces | {repair_summary}. Continue to step 11.', f'Corte final listo | {strategy_label} | solver={solver or "EXACT"} | '
            f'{len(props.guide_obj.data.polygons)} caras | {repair_summary}. Continúa al paso 11.')
        return {'FINISHED'}


class DSG_OT_ContinueToNameExport(Operator):
    bl_idname = 'dsg.continue_to_name_export'
    bl_label = 'Continue to Name and Export'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        guide = _workflow_guide_candidate(props)
        final_ready = bool(
            _valid_obj(guide)
            and (str(guide.get('DSG_final_pipeline', '') or '')
                 or bool(guide.get('DSG_final_cut_completed', False))))
        if not final_ready:
            _dsg_report(
                self, {'ERROR'},
                'The final guide has not been completed yet',
                'La guía final todavía no está terminada')
            return {'CANCELLED'}
        props.current_step = STEP_NAME
        _dsg_report(
            self, {'INFO'},
            'Final guide restored; continue with name and export',
            'Guía final restaurada; continúa con nombre y exportación')
        return {'FINISHED'}


class DCT_OT_ClearCutSelection(Operator):
    bl_idname = "dct.clear_cut_selection"
    bl_label  = "Clear Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        props.dct_object_being_cut  = None
        props.dct_object_making_cut = None
        _dsg_report(self, {'INFO'}, "Selection cleared", "Seleccion limpiada")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Panel
# ─────────────────────────────────────────────────────────────

def draw_preflight_semaphore(layout, obj, key, label, max_polygons=800000, data=None):
    box = layout.box()
    box.label(text=label)
    if data is None:
        if not _valid_obj(obj) or obj.type != 'MESH':
            row = box.row()
            row.alert = True
            row.label(text=_ui_text(getattr(bpy.context.scene, 'dsg_props', None), 'ERROR — object unavailable', 'ERROR — objeto no disponible'), icon_value=icon_manager.icon_id('status_error'))
            return {'status': 'red', 'message': _ui_text(getattr(bpy.context.scene, 'dsg_props', None), 'object unavailable', 'objeto no disponible')}
        data = evaluate_boolean_preflight(obj, key, max_polygons=max_polygons)
    status = str(data.get('status', 'red')).lower()
    if _dsg_spanish(getattr(bpy.context.scene, 'dsg_props', None)):
        visual = {'green': 'CORRECTO', 'orange': 'AVISO', 'red': 'ERROR'}
        prefix = visual.get(status, 'ERROR')
    else:
        visual = {'green': 'READY', 'orange': 'WARNING', 'red': 'ERROR'}
        prefix = visual.get(status, 'ERROR')
    status_icons = {
        'green': 'status_ok',
        'orange': 'status_warning',
        'red': 'status_error',
    }
    row = box.row()
    row.alert = status == 'red'
    row.label(
        text=f"{prefix} — {data.get('message', _ui_text(getattr(bpy.context.scene, 'dsg_props', None), 'no diagnostics', 'sin diagnóstico'))}",
        icon_value=icon_manager.icon_id(status_icons.get(status, 'status_error')))
    bad = data.get('bad_edges')
    deg = data.get('degenerate_faces')
    box.label(text=_ui_text(getattr(bpy.context.scene, 'dsg_props', None), f"Bad edges: {bad if bad is not None else '?'} · degenerate: {deg if deg is not None else '?'} · solver: EXACT", f"Aristas malas: {bad if bad is not None else '?'} · degeneradas: {deg if deg is not None else '?'} · solucionador: EXACT"))
    return data


def get_sleeve_preflight_summary(frame, previews):
    """Resumen ligero para UI; nunca recorre una malla dentro de ``Panel.draw``."""
    if not _valid_obj(frame):
        return {'status': 'red', 'message': 'DSG_Frame not found',
                'bad_edges': None, 'degenerate_faces': None, 'solver': 'EXACT'}
    if not previews:
        return {'status': 'red', 'message': 'Genera el preview para evaluar la UNION',
                'bad_edges': None, 'degenerate_faces': None, 'solver': 'EXACT'}

    frame_data = load_boolean_preflight(frame, 'sleeve_union_frame')
    if frame_data is None:
        return {
            'status': 'orange',
            'message': 'Frame pending verification. Click Check or Apply; the panel does not scan the mesh automatically.',
            'bad_edges': None,
            'degenerate_faces': None,
            'solver': 'EXACT',
        }

    if frame_data.get('status') == 'red':
        return {
            'status': 'red',
            'message': frame_data.get('message', 'Frame no manifold'),
            'bad_edges': frame_data.get('bad_edges'),
            'degenerate_faces': frame_data.get('degenerate_faces'),
            'solver': 'EXACT',
        }

    status = 'orange' if frame_data.get('status') == 'orange' else 'green'
    return {
        'status': status,
        'message': (
            'Frame repaired and sleeves closed by construction; ready for EXACT UNION'
            if status == 'orange'
            else 'Frame checked and sleeves closed by construction; ready for EXACT UNION'
        ),
        'bad_edges': int(frame_data.get('bad_edges') or 0),
        'degenerate_faces': int(frame_data.get('degenerate_faces') or 0),
        'solver': 'EXACT',
    }


def get_step10_diagnostic(guide):
    if not _valid_obj(guide):
        return None
    raw = guide.get('DSG_solid_precheck_step10')
    if not raw:
        return None
    if raw == 'solid_ok':
        return {'status': 'green', 'message': 'Solid OK', 'bad_edges': 0,
                'degenerate_faces': 0, 'solver': 'EXACT'}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {'status': 'red', 'message': str(raw), 'solver': 'EXACT'}


def _draw_reset_flow_panel(layout, props):
    """Navigation is centralized in DSG > Control del flujo (v9.2.5)."""
    return


def _draw_collapsible_sequence_panel(layout, context, props, create_text=None):
    """Optional final animation controls, closed by default."""
    if create_text is None:
        create_text = _ui_text(props, 'Create animation', 'Crear animación')
    header = layout.row(align=True)
    header.prop(
        props, 'show_sequence_panel',
        text=_ui_text(props, 'Animation', 'Animación'),
        icon='TRIA_DOWN' if props.show_sequence_panel else 'TRIA_RIGHT',
        emboss=False)
    if props.show_sequence_panel:
        content = layout.box()
        _draw_sequential_insertion_animation(
            content, context, props,
            allow_create=True,
            create_text=create_text)


def _primary_action(container, enabled=True):
    """Direct/mandatory route using the shared DSG hierarchy."""
    return ui_style.primary_action(container, enabled=enabled)


def _secondary_action(container, enabled=True):
    """Optional efficacy route using the shared DSG hierarchy."""
    return ui_style.secondary_action(container, enabled=enabled)


def _secondary_box(container, props, label_en, label_es):
    # Minimal UI: the box groups optional controls visually; explanatory copy
    # belongs in Blender's status bar, not as permanent panel text.
    return container.box()


def _tertiary_header(container, props, prop_name, label_en, label_es):
    row = container.row(align=True)
    expanded = bool(getattr(props, prop_name, False))
    row.prop(
        props, prop_name,
        text=_ui_text(props, label_en, label_es),
        icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT',
        emboss=False)
    return expanded


def _compact_tools(container):
    """Tertiary/accessory tools, compact and visually discreet."""
    return ui_style.compact_action(container)


def _step_progress_text(step):
    """Ten visual dots for DSG only: filled through the current stage."""
    current = max(STEP_MODEL, min(STEP_NAME, int(step)))
    return '  '.join(
        '●' if index <= current else '○'
        for index in range(TOTAL_STEPS)
    )


def _draw_step_model_axis(layout, b, context, props):
    """Clinical first step: orient, choose retention, calculate and confirm.

    Raycast tolerances, final cutter remesh settings and diagnostic statistics
    remain internal. They are deliberately not shown in the normal workflow.
    """
    model = getattr(props, 'model_obj', None)
    detected = model if _valid_obj(model) else _find_aligned_ios(context)
    blockout = bpy.data.objects.get(BLOCKOUT_NAME)
    blockout_ready = _valid_obj(blockout)

    if not _valid_obj(detected):
        warning = b.row()
        warning.label(
            text=_ui_text(props, 'Complete Alignment before continuing', 'Completa el alineamiento antes de continuar'),
            icon_value=icon_manager.icon_id('status_info'))
        return

    # Restore the explicit closed-model workflow from DSG 8.0.73. The geometry
    # engine below is the newer anatomy-locked 9.2 implementation; only its
    # accidentally omitted UI gate is restored here. Retention/blockout must use
    # a verified closed manifold duplicate, never silently continue from an open
    # IOS scan.
    topology = get_model_topology_report_cached(detected)
    if topology.get('checked') and not _workflow_closed_boundary_passes(topology):
        preparation = b.box()
        preparation.alert = True
        preparation.label(
            text=_ui_text(props, 'Open model detected', 'Modelo abierto detectado'),
            icon='ERROR')
        boundary = topology.get('boundary_edges')
        if boundary is not None:
            preparation.label(text=_ui_text(
                props, f'Open border edges: {int(boundary)}',
                f'Aristas de borde abiertas: {int(boundary)}'))
        if not bool(detected.get(SCAN_HOLES_PROCESSED_FLAG, False)):
            holes = preparation.box()
            holes.label(
                text=_ui_text(props, 'STEP 1 · CLOSE SCAN HOLES', 'PASO 1 · CERRAR AGUJEROS'),
                icon_value=icon_manager.icon_id('contour'))
            action = _primary_action(holes)
            action.operator(
                'dsg.close_scan_holes',
                text=_ui_text(props, 'CLOSE SAFE HOLES', 'CERRAR AGUJEROS SEGUROS'),
                icon_value=icon_manager.icon_id('validate'))
            holes.label(text=_ui_text(
                props, 'Original dental vertices remain locked.',
                'Los vértices dentarios originales permanecen bloqueados.'), icon='LOCKED')
            return
        base = preparation.box()
        base.label(
            text=_ui_text(props, 'STEP 2 · GENERATE CLOSED MODEL', 'PASO 2 · GENERAR MODELO CERRADO'),
            icon_value=icon_manager.icon_id('model'))
        action = _primary_action(base)
        action.operator(
            'dsg.close_model_base',
            text=_ui_text(props, 'GENERATE CLOSED MODEL', 'GENERAR MODELO CERRADO'),
            icon_value=icon_manager.icon_id('validate'))
        base.label(text=_ui_text(
            props, 'Creates DSG_Model_Closed; the original IOS is preserved.',
            'Crea DSG_Model_Closed; se conserva el IOS original.'), icon='DUPLICATE')
        return

    closed_model_accepted = bool(
        detected.get(CLOSED_MODEL_ACCEPTED_FLAG, False)
        or detected.get('DSG_base_closed_manifold', False)
        or str(detected.get('DSG_base_closure_status', '')).startswith(
            ('direct_', 'already_solid', 'external_'))
    )
    if topology.get('checked') and _workflow_closed_boundary_passes(topology) and not closed_model_accepted:
        closed = b.box()
        closed.label(
            text=_ui_text(props, 'Closed manifold model detected', 'Modelo cerrado y manifold detectado'),
            icon_value=icon_manager.icon_id('status_ok'))
        action = _primary_action(closed)
        action.operator(
            'dsg.accept_closed_ios_model',
            text=_ui_text(props, 'USE CLOSED MODEL AND CONTINUE', 'USAR MODELO CERRADO Y CONTINUAR'),
            icon_value=icon_manager.icon_id('continue'))
        return

    b.label(
        text=_ui_text(props, f'Model: {detected.name}', f'Modelo: {detected.name}'),
        icon_value=icon_manager.icon_id('status_ok'))

    active_ios = getattr(context, 'active_object', None)
    model_tools = ui_style.tertiary_action(b)
    model_tools.enabled = bool(_is_strict_ios_blockout_source(active_ios))
    model_tools.operator(
        'dsg.use_selected_ios_model',
        text=_ui_text(props, 'Use selected IOS', 'Usar IOS seleccionado'),
        icon='EYEDROPPER')
    if not _is_strict_ios_blockout_source(active_ios):
        hint = b.row()
        hint.label(
            text=_ui_text(
                props,
                'To change it, select another aligned IOS in the scene.',
                'Para cambiarlo, selecciona otro IOS alineado en la escena.'),
            icon='INFO')

    instructions = b.column(align=True)
    instructions.label(
        text=_ui_text(
            props,
            'Orient the model; the current view will be used when calculating.',
            'Orienta el modelo; al calcular se utilizará la vista actual.'),
        icon_value=icon_manager.icon_id('orient_view'))
    instructions.prop(
        props, 'blockout_relief',
        text=_ui_text(props, 'Retention', 'Retención'))

    choose = _primary_action(b)
    choose.operator(
        'dsg.prepare_aligned_model',
        text=_ui_text(
            props,
            'UPDATE RETENTIVE MODEL' if blockout_ready else 'CALCULATE RETENTIVE MODEL',
            'ACTUALIZAR MODELO RETENTIVO' if blockout_ready else 'CALCULAR MODELO RETENTIVO'),
        icon='ORIENTATION_VIEW')

    if blockout_ready:
        seating_status = str(blockout.get('DSG_seating_validation_status', 'PENDING')).upper()
        seating_summary = str(
            blockout.get('DSG_seating_validation_summary', '')
            or getattr(props, 'blockout_seating_summary', ''))
        review = b.box()
        if seating_status == 'PASSED':
            review.label(
                text=_ui_text(props, 'SEATING CHECK · PASSED', 'COMPROBACIÓN DE ASIENTO · SUPERADA'),
                icon_value=icon_manager.icon_id('status_ok'))
            review.label(
                text=_ui_text(props, 'Teal surface = local blockout added for the insertion path.', 'Superficie turquesa = blockout local añadido para la vía de inserción.'),
                icon='MATERIAL')
        else:
            review.alert = True
            review.label(
                text=_ui_text(props, 'SEATING REVIEW REQUIRED', 'REVISIÓN DE ASIENTO NECESARIA'),
                icon='ERROR')
            review.label(
                text=_ui_text(props, 'Change the view or relief, then calculate again.', 'Cambia la vista o el alivio y vuelve a calcular.'),
                icon='ORIENTATION_VIEW')
        if seating_summary:
            review.label(text=seating_summary, icon='INFO')
        recheck = _secondary_action(review)
        recheck.operator(
            'dsg.validate_blockout_seating',
            text=_ui_text(props, 'RECHECK SEATING', 'VOLVER A COMPROBAR ASIENTO'),
            icon='CHECKMARK')
        local = _secondary_box(
            review, props, 'Local contact relief', 'Alivio local de contacto')
        local.label(
            text=_ui_text(
                props,
                'Optional: select teal vertices in Edit Mode; only the blockout moves along the insertion axis.',
                'Opcional: selecciona vértices turquesa en Modo Edición; solo el blockout avanza según el eje de inserción.'),
            icon='EDITMODE_HLT')
        local.prop(
            props, 'blockout_local_relief_mm',
            text=_ui_text(props, 'Local relief', 'Alivio local'))
        local_action = _secondary_action(local)
        local_action.operator(
            'dsg.apply_selected_blockout_relief',
            text=_ui_text(props, 'APPLY SELECTED RELIEF', 'APLICAR ALIVIO SELECCIONADO'),
            icon='MOD_SHRINKWRAP')
        if seating_status == 'PASSED':
            confirm = _primary_action(b)
            confirm.operator(
                'dsg.confirm_blockout',
                text=_ui_text(props, 'CONFIRM RETENTIVE MODEL', 'CONFIRMAR MODELO RETENTIVO'),
                icon_value=icon_manager.icon_id('validate'))
        else:
            recovery = _secondary_action(b)
            recovery.operator(
                'dsg.force_confirm_blockout',
                text=_ui_text(props, 'CONTINUE AFTER REVIEW', 'CONTINUAR TRAS REVISIÓN'),
                icon='ERROR')

def _draw_step_blockout(layout, b, context, props):
    _draw_step_model_axis(layout, b, context, props)


def _draw_step_contour(layout, b, context, props):
    confirmed_passive = get_confirmed_passive_model_obj()
    if not _valid_obj(confirmed_passive):
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        optimized = bool(
            _valid_obj(blockout)
            and str(blockout.get('DSG_insertion_validation_status', 'UNKNOWN')) == 'OPTIMIZED')
        recovery = b.box()
        recovery.label(
            text=_ui_text(
                props,
                'Confirm the retentive model before marking the outline.',
                'Confirma el modelo retentivo antes de marcar el contorno.'),
            icon='LOCKED')
        action = ui_style.primary_action(recovery)
        action.enabled = optimized
        action.operator(
            'dsg.confirm_blockout',
            text=_ui_text(props, 'CONFIRM RETENTIVE MODEL', 'CONFIRMAR MODELO RETENTIVO'),
            icon_value=icon_manager.icon_id('validate'))
        if not _valid_obj(blockout):
            calculate = ui_style.primary_action(recovery)
            calculate.operator(
                'dsg.prepare_aligned_model',
                text=_ui_text(props, 'CALCULATE BLOCKOUT FROM VIEW', 'CALCULAR BLOCKOUT DESDE LA VISTA'),
                icon='ORIENTATION_VIEW')
        elif not optimized:
            recalculate = ui_style.primary_action(recovery)
            recalculate.operator(
                'dsg.prepare_aligned_model',
                text=_ui_text(props, 'RECALCULATE INSERTION FROM VIEW', 'RECALCULAR INSERCIÓN DESDE LA VISTA'),
                icon='ORIENTATION_VIEW')
        return

    n = len(get_contour_curve_points())
    drawing = bool(getattr(props, 'drawing_active', False))
    contour_obj = get_contour_curve()
    editing = bool(
        _valid_obj(contour_obj)
        and context.mode == 'EDIT_CURVE'
        and context.view_layer.objects.active == contour_obj)

    visual = bpy.data.objects.get(BLOCKOUT_VISUAL_NAME)
    if _valid_obj(visual):
        visual_note = b.row()
        visual_note.label(
            text=_ui_text(
                props,
                'Bright teal = surface created by blockout',
                'Turquesa brillante = superficie creada por el blockout'),
            icon='MATERIAL')

    boundary = bpy.data.objects.get(RETENTION_BOUNDARY_NAME)
    if _valid_obj(boundary):
        guide = b.row()
        guide.label(
            text=_ui_text(
                props,
                'Cyan ring = maximum retention zone for the frame',
                'Anillo cian = zona de máxima retención para el frame'),
            icon_value=icon_manager.icon_id('contour'))

    if editing:
        notice = b.row()
        notice.label(
            text=_ui_text(props, 'Select one point and press G to move it', 'Selecciona un punto y pulsa G para moverlo'),
            icon_value=icon_manager.icon_id('edit_points'))
        primary = _primary_action(b)
        primary.operator(
            'dsg.toggle_contour_point_edit',
            text=_ui_text(props, 'FINISH POINT EDITING', 'TERMINAR EDICIÓN DE PUNTOS'),
            icon_value=icon_manager.icon_id('validate'))
        return

    if drawing:
        notice = b.row()
        notice.label(
            text=_ui_text(props, 'Right-click when the contour is complete', 'Botón derecho cuando el contorno esté completo'),
            icon='MOUSE_RMB')
        return

    if n < 4:
        primary = _primary_action(b)
        primary.operator(
            'dsg.start_drawing',
            text=_ui_text(props, 'MARK CONTOUR', 'MARCAR CONTORNO'),
            icon_value=icon_manager.icon_id('contour'))
        if n:
            tools = _compact_tools(b)
            tools.operator('dsg.toggle_contour_point_edit', text=_ui_text(props, 'Edit points', 'Editar puntos'), icon_value=icon_manager.icon_id('edit_points'))
            destructive = ui_style.destructive_action(b, compact=True)
            destructive.operator('dsg.clear_contour', text=_ui_text(props, 'Restart contour', 'Reiniciar contorno'), icon_value=icon_manager.icon_id('delete'))
        return

    primary = _primary_action(b)
    primary.operator('dsg.confirm_contour', text=_ui_text(props, 'CONTINUE', 'CONTINUAR'), icon_value=icon_manager.icon_id('continue'))
    tools = _compact_tools(b)
    tools.operator('dsg.toggle_contour_point_edit', text=_ui_text(props, 'Edit points', 'Editar puntos'), icon_value=icon_manager.icon_id('edit_points'))
    tools.operator('dsg.start_drawing', text=_ui_text(props, 'Add points', 'Añadir puntos'), icon_value=icon_manager.icon_id('contour'))
    destructive = ui_style.destructive_action(b, compact=True)
    destructive.operator('dsg.clear_contour', text=_ui_text(props, 'Restart contour', 'Reiniciar contorno'), icon_value=icon_manager.icon_id('delete'))

def _draw_dicom_review_box_for_guide_step(box, context, props):
    """Contextual DICOM review, visually secondary unless already active."""
    dicom_props = getattr(context.scene, 'dicom_wizard_pro', None)
    if dicom_props is None or not bool(getattr(dicom_props, 'volume_loaded', False)):
        return
    microscrew = _selected_mpr_microscrew(context)
    active = _dicom_review_is_active(context)
    review = box.box()
    review.label(
        text=_ui_text(
            props,
            'Radiographic review' if active else 'Optional · radiographic review',
            'Revisión radiográfica' if active else 'Opcional · revisión radiográfica'),
        icon_value=icon_manager.icon_id('mpr'))
    if active:
        if _is_valid_mpr_microscrew(microscrew):
            centre = ui_style.secondary_action(review)
            centre.operator(
                'dsg.center_selected_microscrew_mpr',
                text=_ui_text(props, 'CENTER SELECTED MICROSCREW', 'CENTRAR MICROTORNILLO SELECCIONADO'),
                icon_value=icon_manager.icon_id('mpr'))
        row = review.row(align=True)
        row.prop(dicom_props, 'axial_move_z', text='Z', slider=True)
        row.prop(dicom_props, 'sagittal_rotate_z', text=_ui_text(props, 'Inclination', 'Inclinación'), slider=True)
        finish = ui_style.secondary_action(review)
        finish.operator(
            'dsg.close_dicom_review',
            text=_ui_text(props, 'Finish review', 'Terminar revisión'),
            icon_value=icon_manager.icon_id('close'))
    else:
        tools = ui_style.secondary_action(review)
        if _is_valid_mpr_microscrew(microscrew):
            tools.operator(
                'dsg.open_or_center_microscrew_mpr',
                text=_ui_text(props, 'Review selected microscrew', 'Revisar microtornillo seleccionado'),
                icon_value=icon_manager.icon_id('mpr'))
        else:
            tools.operator(
                'dsg.open_dicom_review',
                text=_ui_text(props, 'Review DICOM', 'Revisar DICOM'),
                icon_value=icon_manager.icon_id('mpr'))

def _draw_implant_passive_blockout_box(container, context, props):
    """Compact recovery card for an unconfirmed retentive model."""
    passive = get_confirmed_passive_model_obj()
    blockout = bpy.data.objects.get(BLOCKOUT_NAME)

    if _valid_obj(passive):
        return True

    fit = container.box()
    fit.label(
        text=_ui_text(
            props,
            'Confirm the retentive model before planning implants.',
            'Confirma el modelo retentivo antes de planificar implantes.'),
        icon='LOCKED')
    fit.prop(props, 'blockout_relief', text=_ui_text(props, 'Retention', 'Retención'))

    calculate = ui_style.primary_action(fit)
    calculate.operator(
        'dsg.prepare_aligned_model',
        text=_ui_text(
            props,
            'UPDATE RETENTIVE MODEL' if _valid_obj(blockout) else 'CALCULATE RETENTIVE MODEL',
            'ACTUALIZAR MODELO RETENTIVO' if _valid_obj(blockout) else 'CALCULAR MODELO RETENTIVO'),
        icon='ORIENTATION_VIEW')

    if _valid_obj(blockout):
        fit.label(
            text=_ui_text(props, 'Ready for visual review', 'Listo para revisión visual'),
            icon_value=icon_manager.icon_id('status_ok'))
        confirm = ui_style.primary_action(fit)
        confirm.operator(
            'dsg.confirm_blockout',
            text=_ui_text(props, 'CONFIRM RETENTIVE MODEL', 'CONFIRMAR MODELO RETENTIVO'),
            icon_value=icon_manager.icon_id('validate'))
    return False

def _draw_implant_dicom_review(box, context, props, dicom_props, review_active):
    if dicom_props is None or not bool(getattr(dicom_props, 'volume_loaded', False)):
        return
    review = box.box()
    review.label(
        text=_ui_text(
            props,
            'Radiographic review' if review_active else 'Optional · radiographic review',
            'Revisión radiográfica' if review_active else 'Opcional · revisión radiográfica'),
        icon_value=icon_manager.icon_id('mpr'))
    target = review.row(align=True)
    target.prop(props, 'mpr_target_implant', text=_ui_text(props, 'Implant', 'Implante'))
    target.operator(
        'dsg.select_mpr_implant', text='',
        icon_value=icon_manager.icon_id('select_implant'))
    if not review_active:
        mpr_row = ui_style.secondary_action(review)
        mpr_row.operator(
            'dsg.open_or_center_implant_mpr',
            text=_ui_text(props, 'Review selected implant', 'Revisar implante seleccionado'),
            icon_value=icon_manager.icon_id('mpr'))
        return
    exit_review = ui_style.secondary_action(review)
    exit_review.operator(
        'dsg.close_dicom_review',
        text=_ui_text(props, 'Exit DICOM view', 'Salir de vista DICOM'),
        icon_value=icon_manager.icon_id('close'))
    nav = review.row(align=True)
    nav.prop(dicom_props, 'axial_move_z', text='Z', slider=True)
    nav.prop(dicom_props, 'sagittal_rotate_z', text=_ui_text(props, 'Inclination', 'Inclinación'), slider=True)
    measure = _compact_tools(review)
    measure.operator(
        'dsg.measure_implant_to_dicom',
        text=_ui_text(props, 'Implant distance', 'Distancia implante'),
        icon_value=icon_manager.icon_id('measure_distance'))
    measure.operator(
        'dsg.measure_dicom_two_points',
        text=_ui_text(props, 'Free distance', 'Distancia libre'),
        icon_value=icon_manager.icon_id('measure_two_points'))


def _immediate_target_tooth(scene):
    """Return the TotalSegmentator tooth object selected as the extraction target."""
    fdi = core.target_fdi(scene)
    try:
        name = dental_assets.object_name(fdi, "TOOTH")
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            return obj
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for obj in bpy.data.objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        try:
            if int(obj.get("DSG_fdi_number", 0) or 0) == int(fdi):
                return obj
        except Exception:
            continue
    return None


def _immediate_extraction_ready(scene) -> bool:
    if core.clinical_route(scene) != core.ROUTE_IMMEDIATE:
        return True
    # DSG 9.2.1 prepares extraction sockets BEFORE alignment.  One or several
    # teeth are hidden with H, then maxilla+visible upper teeth and
    # mandible+visible lower teeth are Ctrl+J composites.  That pre-alignment
    # state supersedes the older single-tooth virtual-extraction gate.
    multi_fdis = str(scene.get("DSG_immediate_extraction_fdis", "") or "").strip()
    upper_name = str(scene.get("DSG_immediate_upper_composite", "") or "")
    lower_name = str(scene.get("DSG_immediate_lower_composite", "") or "")
    if multi_fdis and (bpy.data.objects.get(upper_name) is not None or bpy.data.objects.get(lower_name) is not None):
        return True
    target = _immediate_target_tooth(scene)
    if not _valid_obj(target):
        return False
    return bool(scene.get("DSG_immediate_extraction_prepared", False)) and str(
        scene.get("DSG_immediate_extraction_tooth", "") or ""
    ) == str(target.name)


def restore_immediate_extraction(scene) -> bool:
    """Restore a virtually extracted tooth and clear route-specific state.

    Uses the stored object name first so changing FDI or clinical route cannot
    strand the previously selected tooth hidden in the scene.
    """
    if scene is None:
        return False
    name = str(scene.get("DSG_immediate_extraction_tooth", "") or "")
    tooth = bpy.data.objects.get(name) if name else None
    if not _valid_obj(tooth):
        tooth = _immediate_target_tooth(scene)
    restored = False
    if _valid_obj(tooth):
        try:
            tooth.hide_viewport = bool(tooth.get("DSG_virtual_extraction_prev_hide_viewport", False))
            tooth.hide_render = bool(tooth.get("DSG_virtual_extraction_prev_hide_render", False))
            tooth.hide_select = bool(tooth.get("DSG_virtual_extraction_prev_hide_select", False))
            try:
                tooth.hide_set(bool(tooth.hide_viewport))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            tooth["DSG_virtual_extraction"] = False
            restored = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    scene["DSG_immediate_extraction_prepared"] = False
    scene["DSG_immediate_extraction_tooth"] = ""
    scene["DSG_immediate_extraction_fdi"] = 0
    return restored


class DSG_OT_PrepareImmediateExtraction(Operator):
    bl_idname = "dsg.prepare_immediate_extraction"
    bl_label = "Prepare Immediate Extraction"
    bl_description = "Oculta de forma no destructiva el diente FDI objetivo para planificar el implante en el alvéolo postextracción"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if core.clinical_route(scene) != core.ROUTE_IMMEDIATE:
            self.report({"ERROR"}, "Selecciona primero la ruta Implante inmediato")
            return {"CANCELLED"}
        tooth = _immediate_target_tooth(scene)
        fdi = core.target_fdi(scene)
        if not _valid_obj(tooth):
            self.report({"ERROR"}, f"No existe el diente FDI {fdi}. Ejecuta DIENTES + FDI con los dos motores y revisa la numeración.")
            return {"CANCELLED"}
        try:
            tooth["DSG_virtual_extraction_prev_hide_viewport"] = bool(tooth.hide_viewport)
            tooth["DSG_virtual_extraction_prev_hide_render"] = bool(tooth.hide_render)
            tooth["DSG_virtual_extraction_prev_hide_select"] = bool(tooth.hide_select)
            tooth["DSG_virtual_extraction"] = True
            tooth["DSG_virtual_extraction_fdi"] = int(fdi)
            tooth.hide_viewport = True
            tooth.hide_render = True
            tooth.hide_select = True
            try:
                tooth.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            scene["DSG_immediate_extraction_prepared"] = True
            scene["DSG_immediate_extraction_tooth"] = str(tooth.name)
            scene["DSG_immediate_extraction_fdi"] = int(fdi)
            scene["DSG_restoration_scenario"] = "IMMEDIATE_EXTRACTION"
            scene["DSG_route_review_required"] = True
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"FDI {fdi}: extracción virtual preparada")
        return {"FINISHED"}


class DSG_OT_RestoreImmediateTooth(Operator):
    bl_idname = "dsg.restore_immediate_tooth"
    bl_label = "Restore Immediate Tooth"
    bl_description = "Restaura la visibilidad del diente ocultado por la extracción virtual"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        restore_immediate_extraction(scene)
        scene["DSG_route_review_required"] = True
        return {"FINISHED"}


def _draw_immediate_implant_gate(container, context, props) -> bool:
    scene = context.scene
    if core.clinical_route(scene) != core.ROUTE_IMMEDIATE:
        return True

    multi_fdis = str(scene.get("DSG_immediate_extraction_fdis", "") or "").strip()
    upper_name = str(scene.get("DSG_immediate_upper_composite", "") or "")
    lower_name = str(scene.get("DSG_immediate_lower_composite", "") or "")
    if multi_fdis and (bpy.data.objects.get(upper_name) is not None or bpy.data.objects.get(lower_name) is not None):
        box = container.box()
        box.label(
            text=_ui_text(props, f'Immediate sockets · FDI {multi_fdis}', f'Alvéolos inmediatos · FDI {multi_fdis}'),
            icon='MOD_BOOLEAN')
        box.label(
            text=_ui_text(props, 'Prepared before IOS alignment · jaw composites confirmed',
                                  'Preparados antes del alineamiento IOS · modelos por arcada confirmados'),
            icon_value=icon_manager.icon_id('status_ok'))
        box.label(
            text=_ui_text(props, 'Mandibular nerve remains separate', 'El nervio mandibular permanece separado'),
            icon_value=icon_manager.icon_id('status_ok'))
        return True

    fdi = core.target_fdi(scene)
    tooth = _immediate_target_tooth(scene)
    prepared = _immediate_extraction_ready(scene)
    box = container.box()
    box.label(
        text=_ui_text(props, f'Immediate implant · FDI {fdi}', f'Implante inmediato · FDI {fdi}'),
        icon='MOD_BOOLEAN')
    if not _valid_obj(tooth):
        warning = box.row()
        warning.alert = True
        warning.label(
            text=_ui_text(
                props,
                f'FDI {fdi} is not segmented. Return to DICOM and run the 2-engine route.',
                f'FDI {fdi} no está segmentado. Vuelve a DICOM y ejecuta la ruta de 2 motores.'),
            icon='ERROR')
        return False

    box.label(
        text=_ui_text(props, 'Tooth identity from TotalSegmentator ✓', 'Identidad dental de TotalSegmentator ✓'),
        icon_value=icon_manager.icon_id('status_ok'))
    if prepared:
        box.label(
            text=_ui_text(props, 'Virtual extraction prepared · socket planning active',
                                  'Extracción virtual preparada · planificación alveolar activa'),
            icon_value=icon_manager.icon_id('status_ok'))
        restore = ui_style.tertiary_action(box)
        restore.operator(
            DSG_OT_RestoreImmediateTooth.bl_idname,
            text=_ui_text(props, 'Restore tooth', 'Restaurar diente'),
            icon_value=icon_manager.icon_id('back'))
        return True

    box.label(
        text=_ui_text(
            props,
            'This is non-destructive: CBCT and bone remain unchanged.',
            'Es no destructivo: el CBCT y el hueso no se modifican.'),
        icon='INFO')
    prepare = ui_style.primary_action(box)
    prepare.operator(
        DSG_OT_PrepareImmediateExtraction.bl_idname,
        text=_ui_text(props, f'PREPARE VIRTUAL EXTRACTION FDI {fdi}', f'PREPARAR EXTRACCIÓN VIRTUAL FDI {fdi}'),
        icon='MOD_BOOLEAN')
    return False


def _draw_step_implant(layout, b, context, props):
    immediate_ready = _draw_immediate_implant_gate(b, context, props)
    passive_ready = _draw_implant_passive_blockout_box(b, context, props)
    implant_count = count_implants(props)
    dicom_props = getattr(context.scene, 'dicom_wizard_pro', None)
    dicom_loaded = bool(dicom_props and getattr(dicom_props, 'volume_loaded', False))
    review_active = bool(dicom_loaded and _dicom_review_is_active(context))

    dimensions = b.row(align=True)
    dimensions.prop(props, 'implant_diameter', text=_ui_text(props, 'Diameter', 'Diámetro'))
    dimensions.prop(props, 'implant_length', text=_ui_text(props, 'Length', 'Longitud'))

    if implant_count == 0:
        primary = _primary_action(b, enabled=bool(passive_ready and immediate_ready))
        primary.operator('dsg.create_implant', text=_ui_text(props, 'ADD IMPLANT', 'AÑADIR IMPLANTE'), icon_value=icon_manager.icon_id('add_implant'))
        return

    # Secondary efficacy tools are drawn after the direct Continue action.
    emergence_active = len(get_implant_emergence_tubes()) >= implant_count

    if dicom_loaded and review_active:
        _draw_implant_dicom_review(b, context, props, dicom_props, True)

    spacing_results = get_interimplant_spacing_results(props) if implant_count >= 2 else []
    if spacing_results:
        worst = spacing_results[0]
        unsafe = float(worst['clearance_mm']) < (
            INTERIMPLANT_MIN_CLEARANCE_MM - INTERIMPLANT_NUMERIC_TOLERANCE_MM)
        if unsafe:
            warning = b.row()
            warning.alert = True
            warning.label(
                text=_ui_text(
                    props,
                    f'Implants too close: {worst["clearance_mm"]:.2f} mm',
                    f'Implantes demasiado próximos: {worst["clearance_mm"]:.2f} mm'),
                icon='ERROR')

    primary = _primary_action(b, enabled=bool(passive_ready and immediate_ready))
    primary.operator('dsg.confirm_implant', text=_ui_text(props, 'CONTINUE', 'CONTINUAR'), icon_value=icon_manager.icon_id('continue'))

    optional = _secondary_box(
        b, props, 'Optional · improve effectiveness',
        'Opcional · mejorar eficacia')
    tools = _secondary_action(optional)
    tools.operator('dsg.create_implant', text=_ui_text(props, 'Add another implant', 'Añadir otro implante'), icon_value=icon_manager.icon_id('add_implant'))
    tools.operator(
        'dsg.create_implant_emergence_tubes',
        text=_ui_text(
            props,
            'Select emergence controls' if emergence_active else 'Create emergence controls',
            'Seleccionar controles de emergencia' if emergence_active else 'Crear controles de emergencia'),
        icon_value=icon_manager.icon_id('edit_implant'))
    safety = optional.row(align=True)
    safety.prop(
        props, 'implant_tooth_clearance',
        text=_ui_text(props, 'Tooth safety', 'Seguridad diente'))
    safety.operator(
        'dsg.analyze_implant_safety',
        text=_ui_text(props, 'Analyze', 'Analizar'),
        icon_value=icon_manager.icon_id('measure_distance'))
    delete_row = ui_style.destructive_action(optional, compact=True)
    delete_row.operator('dsg.remove_last_implant', text=_ui_text(props, 'Delete last implant', 'Eliminar último implante'), icon_value=icon_manager.icon_id('delete_implant'))

    if dicom_loaded and not review_active:
        _draw_implant_dicom_review(b, context, props, dicom_props, False)

    if implant_count >= 2 and _tertiary_header(
            b, props, 'show_parallel_tools',
            'Accessory · parallelization', 'Accesorio · paralelización'):
        advanced = b.box()
        advanced.prop(
            props, 'parallel_master_implant',
            text=_ui_text(props, 'Master implant', 'Implante maestro'))
        advanced.prop(
            props, 'parallel_divergence_tolerance',
            text=_ui_text(props, 'Tolerance', 'Tolerancia'))
        row = _compact_tools(advanced)
        row.operator(
            'dsg.set_parallel_master',
            text=_ui_text(props, 'Use selected as master', 'Usar seleccionado como maestro'))
        row.operator(
            'dsg.parallelize_implants',
            text=_ui_text(props, 'Parallelize', 'Paralelizar'))
        lock = advanced.row()
        lock.operator(
            'dsg.toggle_implant_parallel_lock',
            text=_ui_text(props, 'Lock selected implant', 'Bloquear implante seleccionado'))

def _draw_sequential_insertion_animation(box, context, props,
                                         allow_create=False,
                                         create_text=None):
    if create_text is None:
        create_text = _ui_text(props, 'Update', 'Actualizar')
    records = get_microscrew_records(props)
    confirmed = get_confirmed_microscrew_objects()
    screws = get_animated_microscrew_objects()
    drills = get_animated_drill_objects()
    animated_implants = get_animated_implant_objects()
    all_objects = screws + drills + animated_implants

    if allow_create:
        create = ui_style.tertiary_action(box)
        create.enabled = bool(records or confirmed or count_implants(props) > 0)
        label = (_ui_text(props, 'Rebuild animation', 'Reconstruir animación')
                 if all_objects else create_text)
        create.operator('dsg.update_final_animation', text=label)

    controls = box.row(align=True)
    controls.enabled = bool(all_objects)
    controls.operator('dsg.play_sequential_insertion_animation', text=_ui_text(props, 'Play', 'Reproducir'))
    controls.operator('dsg.stop_sequential_insertion_animation', text=_ui_text(props, 'Stop', 'Detener'))

    visibility = box.row()
    visibility.enabled = bool(all_objects)
    hidden = bool(all_objects) and all(_object_is_hidden(obj) for obj in all_objects)
    visibility.operator(
        'dsg.toggle_sequential_insertion_visibility',
        text=_ui_text(props, 'Show' if hidden else 'Hide', 'Mostrar' if hidden else 'Ocultar'))



def _draw_step_frame(layout, b, context, props):
    frame = _workflow_frame_candidate(props)

    if not _valid_obj(frame):
        b.prop(props, 'tube_radius', text=_ui_text(props, 'Frame radius', 'Grosor del frame'))
        primary = _primary_action(b)
        primary.operator('dsg.build_tube_frame', text=_ui_text(props, 'CREATE STRUCTURE', 'CREAR ESTRUCTURA'), icon_value=icon_manager.icon_id('frame'))
        return

    review_active = _dicom_review_is_active(context)
    if review_active:
        _draw_dicom_review_box_for_guide_step(b, context, props)
    pending = get_pending_microscrew_preview(props)
    confirmed = get_confirmed_microscrew_objects()
    if pending is not None or confirmed:
        dimensions = b.row(align=True)
        dimensions.prop(props, 'microscrew_diameter', text=_ui_text(props, 'Diameter', 'Diámetro'))
        dimensions.prop(props, 'microscrew_length', text=_ui_text(props, 'Length', 'Longitud'))

    if pending is not None:
        primary = _primary_action(b)
        primary.operator('dsg.apply_microscrews_to_frame', text=_ui_text(props, 'USE MICROSCREW', 'USAR MICROTORNILLO'), icon_value=icon_manager.icon_id('validate'))
        tools = _compact_tools(b)
        tools.operator('dsg.update_microscrew_from_visual', text=_ui_text(props, 'Update', 'Actualizar'), icon_value=icon_manager.icon_id('edit_implant'))
        discard = ui_style.destructive_action(b, compact=True)
        discard.operator('dsg.cancel_microscrew_preview', text=_ui_text(props, 'Discard microscrew', 'Descartar microtornillo'), icon_value=icon_manager.icon_id('delete'))
        if not review_active:
            _draw_dicom_review_box_for_guide_step(b, context, props)
        return

    if confirmed:
        primary = _primary_action(b)
        primary.operator('dsg.apply_microscrews_to_frame', text=_ui_text(props, 'APPLY AND CONTINUE', 'APLICAR Y CONTINUAR'), icon_value=icon_manager.icon_id('validate'))
        tools = ui_style.destructive_action(b, compact=True)
        tools.operator('dsg.remove_last_microscrew', text=_ui_text(props, 'Delete last microscrew', 'Eliminar último microtornillo'), icon_value=icon_manager.icon_id('delete'))
        if not review_active:
            _draw_dicom_review_box_for_guide_step(b, context, props)
        return

    primary = _primary_action(b)
    primary.operator('dsg.confirm_tube_frame', text=_ui_text(props, 'CONTINUE', 'CONTINUAR'), icon_value=icon_manager.icon_id('continue'))
    optional = _secondary_box(
        b, props, 'Optional · improve fixation',
        'Opcional · mejorar fijación')
    tools = _secondary_action(optional)
    tools.operator('dsg.start_microscrew', text=_ui_text(props, 'Add microscrew', 'Añadir microtornillo'), icon_value=icon_manager.icon_id('microscrew'))
    if not review_active:
        _draw_dicom_review_box_for_guide_step(b, context, props)

def _draw_step_sleeve(layout, b, context, props):
    guide = _workflow_guide_candidate(props)
    sleeves_ready = bool(_valid_obj(guide) and guide.get('DSG_sleeves_applied', False))
    dimensions_match = bool(sleeves_ready and _sleeve_dimensions_match_guide(props, guide))

    dimensions = b.box()
    dimensions.label(
        text=_ui_text(props, 'Direct route · essential dimensions',
                      'Ruta directa · medidas esenciales'),
        icon='MOD_SOLIDIFY')
    first = dimensions.row(align=True)
    first.prop(
        props, 'sleeve_inner_diameter',
        text=_ui_text(props, 'Drill Ø', 'Fresa Ø'))
    first.prop(
        props, 'sleeve_wall',
        text=_ui_text(props, 'Wall', 'Pared'))
    second = dimensions.row()
    second.prop(
        props, 'sleeve_height',
        text=_ui_text(props, 'Height', 'Altura'))

    # Fast route first: create/update or continue with the current sleeves.
    if sleeves_ready and dimensions_match:
        primary = _primary_action(b)
        primary.operator(
            'dsg.confirm_sleeve',
            text=_ui_text(props, 'CONTINUE', 'CONTINUAR'),
            icon_value=icon_manager.icon_id('continue'))
    else:
        frame = _workflow_frame_candidate(props)
        can_build = count_implants(props) > 0 and (_valid_obj(frame) or sleeves_ready)
        primary = _primary_action(b, enabled=can_build)
        primary.operator(
            'dsg.create_apply_sleeves',
            text=_ui_text(
                props,
                'UPDATE SLEEVES' if sleeves_ready else 'CREATE SLEEVES',
                'ACTUALIZAR CILINDROS' if sleeves_ready else 'CREAR CILINDROS'),
            icon_value=icon_manager.icon_id('frame'))

    note = b.row()
    note.label(
        text=_ui_text(
            props,
            'Lateral access is created after irrigation',
            'La apertura lateral se crea después de irrigación'),
        icon='INFO')


def _draw_irrigation_implant_gates(box, props):
    implants = get_all_implant_objects(props)
    if len(implants) <= 1:
        return
    gate_box = box.box()
    gate_box.label(text=_ui_text(props, 'Irrigation outlets', 'Salidas de irrigación'), icon_value=icon_manager.icon_id('irrigation'))
    for index, implant in enumerate(implants, start=1):
        sealed = irrigation_implant_is_sealed(implant)
        op = gate_box.operator(
            'dsg.toggle_irrigation_implant_seal',
            text=(f'{_ui_text(props, "Implant", "Implante")} {index} · '
                  + (_ui_text(props, 'CLOSED · MARKED', 'TAPADA · MARCADA') if sealed else _ui_text(props, 'OPEN', 'ABIERTA'))),
            icon='LOCKED' if sealed else 'CHECKMARK',
            depress=sealed)
        op.implant_name = implant.name
    if any(irrigation_implant_is_sealed(item) for item in implants):
        warning = gate_box.row()
        warning.label(
            text=_ui_text(props, 'Perforate at the countersink inside the sleeve (order digit engraved)',
                          'Perforar en el avellanado del cilindro (nº de orden grabado)'),
            icon_value=icon_manager.icon_id('status_warning'))

def _draw_irrigation_sequential_network(box, props):
    """Main channel + Linked sleeves: selection, opening order and state."""
    if count_implants(props) <= 1:
        return
    net_box = box.box()
    net_box.label(
        text=_ui_text(props, 'Irrigation network · sequential opening',
                      'Red de irrigación · apertura secuencial'),
        icon_value=icon_manager.icon_id('irrigation'))
    net_box.prop(props, 'irr_sequential_opening',
                 text=_ui_text(props, 'Sequential opening', 'Apertura secuencial'))
    if irrigation_sequential_enabled(props):
        net_box.prop(props, 'irr_open_branch_share',
                     text=_ui_text(props, 'Water to opened sleeve', 'Agua al cilindro abierto'),
                     slider=True)

    # Current order (read-only: roles are computed when links change).
    members = []
    for implant in get_all_implant_objects(props):
        order = int(implant.get(IRR_OPEN_ORDER_KEY, 0) or 0)
        if order > 0:
            members.append((order, implant))
    for order, implant in sorted(members, key=lambda item: item[0]):
        row = net_box.row()
        if order == 1:
            row.label(text=_ui_text(
                props, f'1 · {implant.name} · OPEN (start)',
                f'1 · {implant.name} · ABIERTA (inicio)'), icon='CHECKMARK')
        else:
            share = float(implant.get('DSG_irrigation_predicted_share_at_opening', 0.0) or 0.0)
            extra = f' · {share:.0%}' if share > 0 else ''
            row.label(text=_ui_text(
                props, f'{order} · {implant.name} · 0.10 mm wall · perforate {order}th{extra}',
                f'{order} · {implant.name} · pared 0,10 mm · perforar {order}º{extra}'), icon='LOCKED')

    if any(order > 1 for order, _implant in members):
        preview = net_box.row(align=True)
        preview.operator(
            'dsg.preview_frangible_marks',
            text=_ui_text(props, 'Preview walls & marks', 'Ver paredes y marcas'),
            icon='HIDE_OFF')
        clear = preview.operator('dsg.preview_frangible_marks', text='', icon='X')
        clear.clear = True

    candidates = irrigation_link_candidates(props)
    if candidates:
        pick = net_box.column(align=True)
        pick.label(text=_ui_text(props, 'Link to the main channel:', 'Vincular al conducto principal:'))
        selected = 0
        for implant in candidates:
            chosen = bool(implant.get(IRR_LINK_CANDIDATE_KEY, False))
            selected += int(chosen)
            op = pick.operator(
                'dsg.toggle_irrigation_link_candidate',
                text=implant.name, icon='CHECKBOX_HLT' if chosen else 'CHECKBOX_DEHLT',
                depress=chosen)
            op.implant_name = implant.name
        action = _secondary_action(net_box)
        action.enabled = selected > 0
        action.operator(
            'dsg.link_selected_irrigation',
            text=_ui_text(props, f'LINK SELECTED ({selected})', f'VINCULAR SELECCIONADOS ({selected})'),
            icon_value=icon_manager.icon_id('link'))


def _draw_irrigation_mode_selector(box, props):
    selector = box.box()
    selector.label(
        text=_ui_text(props, 'Irrigation type', 'Tipo de irrigación'),
        icon_value=icon_manager.icon_id('irrigation'))
    mode_value = str(getattr(props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
    modes = ui_style.secondary_action(selector)
    op_c = modes.operator(
        'dsg.set_irrigation_cylinder_channel_mode',
        text=_ui_text(props, 'C CHANNEL', 'CANAL EN C'),
        icon_value=icon_manager.icon_id('irrigation_c'),
        depress=mode_value == 'C')
    op_c.mode = 'C'
    op_direct = modes.operator(
        'dsg.set_irrigation_cylinder_channel_mode',
        text=_ui_text(props, 'DIRECT', 'DIRECTA'),
        icon_value=icon_manager.icon_id('irrigation_direct'),
        depress=mode_value == 'DIRECT')
    op_direct.mode = 'DIRECT'


def _draw_step_irrigation(layout, b, context, props):
    pending = get_pending_irrigation_preview(props)
    walls = get_confirmed_irrigation_walls()
    guide = get_active_guide_obj(props)
    resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper() if _valid_obj(guide) else ''

    # After irrigation is resolved, remain on this same numbered step for the
    # lateral-opening decision. No new workflow number is introduced.
    if resolution in {'APPLIED', 'SKIPPED'}:
        done = b.box()
        done.label(
            text=_ui_text(props, 'POST-IRRIGATION', 'POST-IRRIGACIÓN'),
            icon_value=icon_manager.icon_id('status_ok'))
        if bool(guide.get('DSG_sleeve_lateral_opening', False)):
            width = float(guide.get('DSG_sleeve_lateral_opening_width_mm', 0.0))
            done.label(
                text=_ui_text(
                    props,
                    f'Lateral opening applied · {width:.2f} mm · frame + sleeve',
                    f'Apertura lateral aplicada · {width:.2f} mm · frame + cilindro'),
                icon_value=icon_manager.icon_id('validate'))
        else:
            inner_diameter = float(guide.get(
                'DSG_sleeve_inner_diameter_mm', getattr(props, 'sleeve_inner_diameter', 4.7)))
            optional = _secondary_box(
                done, props,
                'Optional · lateral drill entry',
                'Opcional · entrada lateral de la fresa')
            optional.label(
                text=_ui_text(
                    props,
                    f'Opening width fixed to inner sleeve Ø: {inner_diameter:.2f} mm',
                    f'Anchura fijada al Ø interior del cilindro: {inner_diameter:.2f} mm'))
            optional.label(
                text=_ui_text(
                    props,
                    'You choose the side with the best drill access',
                    'Tú eliges el lado con mejor acceso para la fresa'),
                icon='MOUSE_LMB')
            selected_picks, total_picks = _lateral_window_manual_selection_status(props)
            pick_row = _secondary_action(optional)
            pick_row.operator(
                'dsg.pick_lateral_opening_side',
                text=_ui_text(
                    props,
                    f'PICK WINDOW SIDE  {selected_picks}/{total_picks}',
                    f'MARCAR LADO DE VENTANA  {selected_picks}/{total_picks}'),
                icon='EYEDROPPER')

            apply_row = _secondary_action(optional)
            apply_row.enabled = bool(total_picks > 0 and selected_picks >= total_picks)
            apply_row.operator(
                'dsg.apply_post_irrigation_lateral_opening',
                text=_ui_text(props, 'APPLY LATERAL OPENING', 'APLICAR APERTURA LATERAL'),
                icon='MOD_BOOLEAN')
            if _tertiary_header(
                    optional, props, 'show_sleeve_window_options',
                    'Accessory · fine direction', 'Accesorio · dirección fina'):
                advanced = optional.box()
                advanced.prop(
                    props, 'sleeve_lateral_opening_rotation',
                    text=_ui_text(props, 'Fine rotation after pick', 'Rotación fina tras marcar'))
                advanced.label(
                    text=_ui_text(
                        props,
                        'DSG blocks positions that collide with irrigation',
                        'DSG bloquea posiciones que chocan con la irrigación'),
                    icon='INFO')

        primary = _primary_action(b)
        primary.operator(
            'dsg.continue_after_irrigation',
            text=_ui_text(props, 'CONTINUE', 'CONTINUAR'),
            icon_value=icon_manager.icon_id('continue'))
        return

    # C / Direct is intentionally visible, not buried in Accessory options.
    if pending is None:
        _draw_irrigation_mode_selector(b, props)
    _draw_irrigation_implant_gates(b, props)

    if pending is not None:
        primary = _primary_action(b)
        primary.operator(
            'dsg.update_confirm_irrigation',
            text=_ui_text(props, 'USE THIS CHANNEL', 'USAR ESTE CONDUCTO'),
            icon_value=icon_manager.icon_id('validate'))
        tools = ui_style.destructive_action(b, compact=True)
        tools.operator(
            'dsg.remove_last_irrigation',
            text=_ui_text(props, 'Discard channel', 'Descartar conducto'),
            icon_value=icon_manager.icon_id('delete'))
        return

    if not walls:
        primary = _primary_action(b)
        primary.operator(
            'dsg.skip_irrigation',
            text=_ui_text(props, 'CONTINUE WITHOUT IRRIGATION',
                          'CONTINUAR SIN IRRIGACIÓN'),
            icon_value=icon_manager.icon_id('continue'))

        optional = _secondary_box(
            b, props, 'Optional · improve cooling',
            'Opcional · mejorar refrigeración')
        if count_implants(props) > 1:
            optional.prop(props, 'implant_obj', text=_ui_text(props, 'Implant', 'Implante'))
        draw = _secondary_action(optional)
        draw.operator(
            'dsg.start_irrigation',
            text=_ui_text(props, 'Draw irrigation', 'Dibujar irrigación'),
            icon_value=icon_manager.icon_id('irrigation'))
        if _tertiary_header(
                optional, props, 'show_irrigation_channel_options',
                'Accessory · channel dimensions',
                'Accesorio · medidas del conducto'):
            advanced = optional.box()
            dimensions = advanced.row(align=True)
            dimensions.prop(props, 'irr_inner_diameter', text=_ui_text(props, 'Lumen', 'Lumen'))
            dimensions.prop(props, 'irr_wall_thickness', text=_ui_text(props, 'Thickness', 'Grosor'))
        return

    _draw_irrigation_sequential_network(b, props)

    primary = _primary_action(b)
    primary.operator(
        'dsg.confirm_irrigation',
        text=_ui_text(props, 'APPLY IRRIGATION', 'APLICAR IRRIGACIÓN'),
        icon_value=icon_manager.icon_id('continue'))

    optional = _secondary_box(
        b, props, 'Optional · additional channels',
        'Opcional · conductos adicionales')
    tools = _secondary_action(optional)
    tools.operator(
        'dsg.start_irrigation',
        text=_ui_text(props, 'Add another', 'Añadir otro'),
        icon_value=icon_manager.icon_id('irrigation'))
    if count_implants(props) > 1:
        tools.operator(
            'dsg.link_irrigation',
            text=_ui_text(props, 'Link', 'Vincular'),
            icon_value=icon_manager.icon_id('link'))
    delete_row = ui_style.destructive_action(optional, compact=True)
    delete_row.operator(
        'dsg.remove_last_irrigation',
        text=_ui_text(props, 'Delete last channel', 'Eliminar último conducto'),
        icon_value=icon_manager.icon_id('delete'))

    if _tertiary_header(
            optional, props, 'show_irrigation_channel_options',
            'Accessory · channel dimensions',
            'Accesorio · medidas del conducto'):
        advanced = optional.box()
        dimensions = advanced.row(align=True)
        dimensions.prop(props, 'irr_inner_diameter', text=_ui_text(props, 'Lumen', 'Lumen'))
        dimensions.prop(props, 'irr_wall_thickness', text=_ui_text(props, 'Thickness', 'Grosor'))


def _draw_step_reinforcement(layout, b, context, props):
    pending = get_pending_reinforcement_preview(props)
    confirmed = get_confirmed_reinforcement_curves()

    if pending is not None:
        primary = _primary_action(b)
        primary.operator(
            'dsg.confirm_reinforcement_preview',
            text=_ui_text(props, 'USE REINFORCEMENT', 'USAR REFUERZO'),
            icon_value=icon_manager.icon_id('validate'))
        tools = ui_style.destructive_action(b, compact=True)
        tools.operator(
            'dsg.cancel_reinforcement_preview',
            text=_ui_text(props, 'Discard reinforcement', 'Descartar refuerzo'),
            icon_value=icon_manager.icon_id('delete'))
        return

    if confirmed:
        primary = _primary_action(b)
        primary.operator(
            'dsg.apply_reinforcements',
            text=_ui_text(props, 'APPLY AND CONTINUE', 'APLICAR Y CONTINUAR'),
            icon_value=icon_manager.icon_id('continue'))
        optional = _secondary_box(
            b, props, 'Optional · additional reinforcements',
            'Opcional · refuerzos adicionales')
        tools = _secondary_action(optional)
        tools.operator(
            'dsg.start_reinforcement',
            text=_ui_text(props, 'Add another', 'Añadir otro'),
            icon_value=icon_manager.icon_id('reinforcement'))
        delete_row = ui_style.destructive_action(optional, compact=True)
        delete_row.operator(
            'dsg.remove_last_reinforcement',
            text=_ui_text(props, 'Delete last reinforcement', 'Eliminar último refuerzo'),
            icon_value=icon_manager.icon_id('delete'))
        return

    # KISS: una acción principal. FEM decide topología, radios, poda y rigidez;
    # el usuario solo revisa el resultado antes de la aplicación destructiva.
    primary = _primary_action(b)
    primary.operator(
        'dsg.optimize_frame_fem',
        text=_ui_text(props, 'OPTIMIZE FRAME', 'OPTIMIZAR FRAME'),
        icon_value=icon_manager.icon_id('reinforcement'))

    optional = _secondary_box(
        b, props, 'Optional · manual / skip',
        'Opcional · manual / omitir')
    tools = _secondary_action(optional)
    tools.operator(
        'dsg.start_reinforcement',
        text=_ui_text(props, 'Add manually', 'Añadir manualmente'),
        icon_value=icon_manager.icon_id('reinforcement'))
    tools.operator(
        'dsg.skip_reinforcement',
        text=_ui_text(props, 'Continue without', 'Continuar sin refuerzo'),
        icon_value=icon_manager.icon_id('continue'))
    if _tertiary_header(
            optional, props, 'show_reinforcement_options',
            'Accessory · manual dimensions', 'Accesorio · medidas manuales'):
        advanced = optional.box()
        advanced.prop(
            props, 'connector_diameter',
            text=_ui_text(props, 'Manual connector thickness', 'Grosor manual'))


def _draw_step_drill(layout, b, context, props):
    guide = get_active_guide_obj(props)
    channels_ready = bool(_valid_obj(guide) and int(guide.get('DSG_drill_channel_count', 0)) > 0)
    primary = _primary_action(b, enabled=_valid_obj(guide) and count_implants(props) > 0)
    if channels_ready:
        primary.operator('dsg.confirm_drill', text=_ui_text(props, 'CONTINUE', 'CONTINUAR'), icon_value=icon_manager.icon_id('continue'))
    else:
        primary.operator('dsg.prepare_and_create_drill_channels', text=_ui_text(props, 'CREATE DRILL CHANNELS', 'CREAR CANALES DE FRESADO'), icon_value=icon_manager.icon_id('drill_channel'))

def _draw_step_final_cut(layout, b, context, props):
    guide = _workflow_guide_candidate(props)
    final_ready = bool(
        _valid_obj(guide)
        and (str(guide.get('DSG_final_pipeline', '') or '')
             or bool(guide.get('DSG_final_cut_completed', False))))
    primary = _primary_action(b)
    if final_ready:
        primary.operator(
            'dsg.continue_to_name_export',
            text=_ui_text(props, 'CONTINUE', 'CONTINUAR'),
            icon_value=icon_manager.icon_id('continue'))
    else:
        primary.operator('dct.apply_cut', text=_ui_text(props, 'FINISH GUIDE', 'FINALIZAR GUÍA'), icon_value=icon_manager.icon_id('finalize_guide'))

def _draw_step_name_export(layout, b, context, props):
    guide = get_active_guide_obj(props)
    sealed = get_sealed_irrigation_implants(props, require_confirmed_path=True)
    if sealed:
        warning = b.row()
        warning.label(
            text=_ui_text(
                props,
                f'{len(sealed)} selective seal(s) require physical validation',
                f'{len(sealed)} sello(s) requieren validación física'),
            icon_value=icon_manager.icon_id('status_warning'))

    # Direct route: exporting does not depend on optional identification.
    primary = _primary_action(b, enabled=_valid_obj(guide))
    primary.operator(
        'dsg.export_guide_stl',
        text=_ui_text(props, 'EXPORT STL', 'EXPORTAR STL'),
        icon_value=icon_manager.icon_id('export_stl'))

    if _tertiary_header(
            b, props, 'show_name_tools',
            'Accessory · name engraving', 'Accesorio · grabado del nombre'):
        tools_box = b.box()
        tools_box.prop(
            props, 'engrave_patient_text',
            text=_ui_text(props, 'Patient', 'Paciente'))
        tools_box.prop(
            props, 'engrave_text_size',
            text=_ui_text(props, 'Letter size', 'Tamaño de letra'))
        text_ready = bool((props.engrave_patient_text or '').strip())
        if text_ready and not bool(getattr(props, 'engrave_has_position', False)):
            tools = _secondary_action(tools_box)
            tools.operator(
                'dsg.place_engrave_anchor',
                text=_ui_text(props, 'Place name', 'Colocar nombre'),
                icon_value=icon_manager.icon_id('engrave_name'))
        elif text_ready:
            if bool(getattr(props, 'engrave_preview_dirty', False)):
                tools_box.label(
                    text=_ui_text(props, 'Preview needs update', 'Actualiza la vista previa'),
                    icon_value=icon_manager.icon_id('status_warning'))
            tools = _secondary_action(tools_box)
            tools.operator(
                'dsg.update_engrave_preview',
                text=_ui_text(props, 'Preview', 'Vista previa'),
                icon_value=icon_manager.icon_id('view'))
            tools.operator(
                'dsg.apply_patient_engrave',
                text=_ui_text(props, 'Engrave name', 'Grabar nombre'),
                icon_value=icon_manager.icon_id('engrave_name'))

_DSG_STEP_DRAWERS = {
    STEP_MODEL: _draw_step_model_axis,
    STEP_IMPLANT: _draw_step_implant,
    STEP_CONTOUR: _draw_step_contour,
    STEP_FRAME: _draw_step_frame,
    STEP_SLEEVE: _draw_step_sleeve,
    STEP_IRRIGATION: _draw_step_irrigation,
    STEP_REINFORCEMENT: _draw_step_reinforcement,
    STEP_DRILL: _draw_step_drill,
    STEP_FINAL_CUT: _draw_step_final_cut,
    STEP_NAME: _draw_step_name_export,
}

class _DSGMinimalUILayout:
    """Proxy that removes passive panel copy while preserving interactive UI.

    Labels are intentionally not drawn. Critical/alert labels are redirected
    to Blender's bottom status bar. Buttons, properties, templates and layout
    state pass through unchanged.
    """
    __slots__ = ("_layout", "_context", "_alert")

    def __init__(self, layout, context, alert=False):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_alert", bool(alert))

    def __getattr__(self, name):
        return getattr(self._layout, name)

    def __setattr__(self, name, value):
        if name in {"_layout", "_context", "_alert"}:
            object.__setattr__(self, name, value)
            return
        if name == "alert":
            object.__setattr__(self, "_alert", bool(value))
        setattr(self._layout, name, value)

    def _wrap(self, child):
        return _DSGMinimalUILayout(child, self._context, alert=self._alert)

    def row(self, *args, **kwargs):
        return self._wrap(self._layout.row(*args, **kwargs))

    def column(self, *args, **kwargs):
        return self._wrap(self._layout.column(*args, **kwargs))

    def box(self, *args, **kwargs):
        return self._wrap(self._layout.box(*args, **kwargs))

    def split(self, *args, **kwargs):
        return self._wrap(self._layout.split(*args, **kwargs))

    def grid_flow(self, *args, **kwargs):
        return self._wrap(self._layout.grid_flow(*args, **kwargs))

    def label(self, text="", **kwargs):
        icon = str(kwargs.get("icon", "") or "").upper()
        critical = self._alert or icon in {"ERROR", "CANCEL", "WARNING", "LOCKED"}
        if critical and text:
            try:
                core.set_status_bar(self._context, str(text))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return None

class DSG_PT_Main(Panel):
    bl_label       = "DSG"
    bl_idname      = "DSG_PT_main"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "DSG"
    bl_options     = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        try:
            return core.infer_stage(context.scene) == core.STAGE_GUIDE
        except Exception:
            return True

    def draw(self, context):
        layout = self.layout
        try:
            props = context.scene.dsg_props
            layout.use_property_decorate = False
            raw_step = int(getattr(props, "current_step", STEP_MODEL))
            max_step = min(TOTAL_STEPS, len(STEP_LABELS)) - 1
            step = max(0, min(raw_step, max_step))
            gate_message = str(context.scene.get(WORKFLOW_GATE_MESSAGE_KEY, "") or "")
            status = _step_text(props, step)
            if gate_message:
                status += " · " + gate_message
            try:
                core.set_status_bar(context, status)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

            minimal_layout = _DSGMinimalUILayout(layout, context)
            box = minimal_layout.box()
            draw_func = _DSG_STEP_DRAWERS.get(step)
            if draw_func:
                draw_func(minimal_layout, box, context, props)

            if step == STEP_NAME:
                view = ui_style.tertiary_action(layout)
                view.operator("dsg.final_view_model", text=_ui_text(props, "MODEL", "MODELO"), icon_value=icon_manager.icon_id("model_visibility"))
                view.operator("dsg.final_view_cbct_stl", text=_ui_text(props, "CBCT", "CBCT"), icon_value=icon_manager.icon_id("cbct"))
                _draw_sequential_insertion_animation(minimal_layout.box(), context, props, allow_create=True, create_text=_ui_text(props, "CREATE ANIMATION", "CREAR ANIMACIÓN"))
        except Exception as exc:
            try:
                core.set_status_bar(context, f"DSG: {type(exc).__name__}: {exc}")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

# ─────────────────────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────────────────────

CLASSES = [
    DSG_ContourPoint,
    DSG_Props,
    DSG_OT_RunBooleanPreflight,
    DSG_OT_ForceOrthographicView,
    DSG_OT_PrepareImmediateExtraction,
    DSG_OT_RestoreImmediateTooth,
    DSG_OT_Reset,
    DSG_OT_ResetCurrentStep,
    DSG_OT_UseSelectedIOSModel,
    DSG_OT_PreviewAutomaticBasePerimeter,
    DSG_OT_DrawBasePerimeter,
    DSG_OT_ClearBasePerimeter,
    DSG_OT_CloseScanHoles,
    DSG_OT_AcceptClosedIOSModel,
    DSG_OT_CloseModelBase,
    DSG_OT_SelectMPRImplant,
    DSG_OT_OpenOrCenterImplantMPR,
    DSG_OT_CenterSelectedMicroscrewMPR,
    DSG_OT_OpenOrCenterMicroscrewMPR,
    DSG_OT_OpenDICOMReview,
    DSG_OT_CloseDICOMReview,
    DSG_OT_MeasureImplantToDICOM,
    DSG_OT_MeasureDICOMTwoPoints,
    DSG_OT_RemoveLastDICOMMeasurement,
    DSG_OT_ClearDICOMMeasurements,
    DSG_OT_PrepareAlignedModel,
    DSG_OT_ConfirmModel,
    DSG_OT_CaptureAxis,
    DSG_OT_SelectAxis,
    DSG_OT_ConfirmAxis,
    DSG_OT_SelectRetentionPreset,
    DSG_OT_GenerateBlockout,
    DSG_OT_AnalyzeRetention,
    DSG_OT_ValidateBlockoutSeating,
    DSG_OT_ApplySelectedBlockoutRelief,
    DSG_OT_AutoPrepareRetention,
    DSG_OT_ConfirmBlockout,
    DSG_OT_ForceConfirmBlockout,
    DSG_OT_StartDrawing,
    DSG_OT_ToggleContourPointEdit,
    DSG_OT_ClearContour,
    DSG_OT_ConfirmContour,
    DSG_OT_CreateImplant,
    DSG_OT_RemoveLastImplant,
    DSG_OT_ToggleImplantParallelLock,
    DSG_OT_SetParallelMaster,
    DSG_OT_ParallelizeImplants,
    DSG_OT_CreateImplantEmergenceTubes,
    DSG_OT_AnalyzeImplantSafety,
    DSG_OT_ConfirmImplant,
    DSG_OT_BuildTubeFrame,
    DSG_OT_StartMicroscrew,
    DSG_OT_UpdateMicroscrewFromVisual,
    DSG_OT_ConfirmMicroscrewPreview,
    DSG_OT_CancelMicroscrewPreview,
    DSG_OT_RemoveLastMicroscrew,
    DSG_OT_ApplyMicroscrewsToFrame,
    DSG_OT_CreateAnimatedMicroscrews,
    DSG_OT_PlayAnimatedMicroscrews,
    DSG_OT_StopAnimatedMicroscrews,
    DSG_OT_ToggleAnimatedMicroscrewsVisibility,
    DSG_OT_ShowAnimatedMicroscrewStart,
    DSG_OT_ShowAnimatedMicroscrewStop,
    DSG_OT_ConfirmTubeFrame,
    DSG_OT_ToggleLateralOpening,
    DSG_OT_CaptureLateralOpeningView,
    DSG_OT_PickLateralOpeningSide,
    DSG_OT_AddSleeve,
    DSG_OT_CreateApplySleeves,
    DSG_OT_RebuildLateralWindowFromIrrigation,
    DSG_OT_ApplyPostIrrigationLateralOpening,
    DSG_OT_ContinueAfterIrrigation,
    DSG_OT_ApplySleeves,
    DSG_OT_ConfirmSleeve,
    DSG_OT_ProtectDrillInsertion,
    DSG_OT_AddDrillChannel,
    DSG_OT_PrepareAndCreateDrillChannels,
    DSG_OT_ConfirmDrill,
    # ── Irrigation (NUEVO) ──────────────────────────────────
    DSG_OT_SetIrrigationCylinderChannelMode,
    DSG_OT_ToggleIrrigationImplantSeal,
    DSG_OT_StartIrrigationFromPoints,
    DSG_OT_StartIrrigation,
    DSG_OT_UpdateIrrigationPreview,
    DSG_OT_ShowExactIrrigationLumenDiagnostic,
    DSG_OT_ConfirmIrrigationPreview,
    DSG_OT_UpdateConfirmIrrigation,
    DSG_OT_LinkIrrigation,
    *SEQUENTIAL_IRRIGATION_CLASSES,
    *FRANGIBLE_CLASSES,
    DSG_OT_RemoveLastIrrigation,
    DSG_OT_CancelIrrigationPreview,
    DSG_OT_SkipIrrigation,
    DSG_OT_SimulateIrrigationFlow,
    DSG_OT_ClearIrrigationFlowSimulation,
    DSG_OT_ConfirmIrrigation,
    # ── Fresa visual animada del paso 8 ─────────────────
    DSG_OT_CreateAnimatedDrills,
    DSG_OT_PlayAnimatedDrills,
    DSG_OT_StopAnimatedDrills,
    DSG_OT_ToggleAnimatedDrillsVisibility,
    DSG_OT_ShowAnimatedDrillStart,
    DSG_OT_ShowAnimatedDrillStop,
    DSG_OT_CreateSequentialInsertionAnimation,
    DSG_OT_UpdateFinalAnimation,
    DSG_OT_PlaySequentialInsertionAnimation,
    DSG_OT_StopSequentialInsertionAnimation,
    DSG_OT_ToggleSequentialInsertionVisibility,
    # ── Conectores de refuerzo Catmull-Rom ─────────────
    DSG_OT_StartReinforcement,
    DSG_OT_ConfirmReinforcementPreview,
    DSG_OT_CancelReinforcementPreview,
    DSG_OT_RemoveLastReinforcement,
    DSG_OT_SkipReinforcement,
    DSG_OT_ApplyReinforcements,
    # ── Grabado paciente ────────────────────────────────────
    DSG_OT_PlaceEngraveAnchor,
    DSG_OT_UpdateEngravePreview,
    DSG_OT_ClearEngravePreview,
    DSG_OT_ApplyPatientEngrave,
    DSG_OT_SkipPatientName,
    DSG_OT_CleanGuideIslands,
    # ── Exportar ────────────────────────────────────────────
    DSG_OT_ExportGuideSTL,
    # ── Visibilidad final ─────────────────────────────────
    DSG_OT_ToggleBlockoutVisibility,
    DSG_OT_ToggleGuideVisibility,
    DSG_OT_FinalViewModel,
    DSG_OT_FinalViewCBCTSTL,
    # ── DCT ─────────────────────────────────────────────────
    DCT_OT_VoxelRemesh,
    DCT_OT_SelectBeingCut,
    DCT_OT_SelectMakingCut,
    DCT_OT_ApplyCut,
    DSG_OT_ContinueToNameExport,
    DCT_OT_ClearCutSelection,
    # ── Panel ────────────────────────────────────────────────
    DSG_PT_Main,
]


def _dsg_migrate_irrigation_outlet_to_1mm(_dummy=None):
    """Actualiza una sola vez el antiguo valor predeterminado de 0,80 a 1,00 mm.

    Se conserva cualquier valor personalizado distinto de 0,80 mm. El marcador por
    escena evita sobrescribir una elección posterior del usuario.
    """
    scenes = getattr(bpy.data, 'scenes', None)
    if scenes is None:
        # Blender calls add-on register() with restricted data access while enabling
        # from preferences.  The load_post handler below will run this migration
        # again once normal scene data is available.
        return
    outlet_marker = "_dsg_v6815_irrigation_outlet_migrated"
    ui_marker = "_dsg_v6924_final_water_defaults_applied"
    for scene in scenes:
        try:
            props = scene.dsg_props
            if not bool(scene.get(outlet_marker, False)):
                current = float(props.irr_funnel_outer_diameter)
                if abs(current - 0.8) <= 1.0e-6:
                    props.irr_funnel_outer_diameter = 1.0
                scene[outlet_marker] = True

            # Apply the requested final-step values once, including already-open scenes.
            if not bool(scene.get(ui_marker, False)):
                props.irr_spray_length = 10.0
                props.irr_spray_spread = 24.0
                props.irr_spray_streams = 8
                scene[ui_marker] = True

            # v6.12.18: increase only the historical untouched frame default by 25 %.
            # Any custom value different from 2.0 mm is preserved.
            frame_marker = "_dsg_v61218_frame_radius_25pct_applied"
            if not bool(scene.get(frame_marker, False)):
                current_radius = float(props.tube_radius)
                if abs(current_radius - 2.0) <= 1.0e-6:
                    props.tube_radius = FRAME_RADIUS_DEFAULT_MM
                scene[frame_marker] = True

            # v6.12.52: increase the untouched v6.12.18 default from Ø5.0 to Ø6.0 mm.
            # Custom frame radii are preserved.
            frame_6mm_marker = "_dsg_v61252_frame_radius_6mm_applied"
            if not bool(scene.get(frame_6mm_marker, False)):
                current_radius = float(props.tube_radius)
                if abs(current_radius - 2.5) <= 1.0e-6:
                    props.tube_radius = FRAME_RADIUS_DEFAULT_MM
                scene[frame_6mm_marker] = True

            # v6.12.58: slim the irrigation tube body while preserving the wide
            # volcanic sleeve junction. Only the untouched historical 1.5 mm
            # wall is migrated; custom wall thicknesses remain unchanged.
            irrigation_slim_marker = "_dsg_v61258_irrigation_slim_wall_applied"
            if not bool(scene.get(irrigation_slim_marker, False)):
                current_wall = float(props.irr_wall_thickness)
                if abs(current_wall - 1.5) <= 1.0e-6:
                    props.irr_wall_thickness = IRRIGATION_SLIM_WALL_THICKNESS_DEFAULT_MM
                scene[irrigation_slim_marker] = True

            # Reopen files on the highest stage whose tangible dependencies are
            # still present; never leave an old .blend stranded on a stale panel.
            if getattr(bpy.context, 'scene', None) == scene:
                _reconcile_workflow_after_undo(scene)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


_DSG_REGISTERED_CLASSES = []
_DSG_SCENE_POINTER_OWNED = False
_DSG_LOAD_HANDLER_OWNED = False
_DSG_MEASURE_HANDLER_OWNED = False


def _dsg_remove_load_handler():
    try:
        while _dsg_migrate_irrigation_outlet_to_1mm in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_dsg_migrate_irrigation_outlet_to_1mm)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def pre_register_quiesce():
    """Remove callbacks from older DSG builds without reading bpy.data."""
    try:
        lifecycle.cancel_module_timers(__name__)
        _unregister_dsg_custom_icons()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _remove_dicom_measure_handler()
    _remove_implant_navigation_restore_handler()
    _dsg_remove_load_handler()


def _dsg_remove_scene_pointer():
    global _DSG_SCENE_POINTER_OWNED
    if not _DSG_SCENE_POINTER_OWNED:
        return
    try:
        if hasattr(bpy.types.Scene, 'dsg_props'):
            del bpy.types.Scene.dsg_props
    except Exception as exc:
        print(f'[DSG] Could not remove Scene.dsg_props: {exc}')
    _DSG_SCENE_POINTER_OWNED = False


def _dsg_unregister_class_object(class_object):
    if class_object is None:
        return False
    try:
        bpy.utils.unregister_class(class_object)
        return True
    except Exception:
        return False


def _dsg_unregister_stale_classes():
    """Removes classes left registered by an older addon file.

    Installing several DSG versions under different filenames makes Blender
    treat them as different addons even though their classes have the same
    ``bl_idname``.  Registration then stops before the N-panel is reached.
    Looking up the currently registered bpy.types class by Python class name
    allows this version to cleanly replace the stale module.
    """
    removed = 0
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None and _dsg_unregister_class_object(existing):
            removed += 1
            continue
        if _dsg_unregister_class_object(cls):
            removed += 1
    if removed:
        print(f'[DSG] Removed {removed} stale registered class(es) from an older version')
    return removed


def _dsg_rollback_registration(classes):
    for cls in reversed(list(classes)):
        _dsg_unregister_class_object(cls)
    _dsg_remove_scene_pointer()


def _dsg_is_class_registered(cls):
    """Checks class registration without relying on bpy.types.<class name>."""
    try:
        checker = getattr(bpy.utils, 'is_registered_class', None)
        if checker is not None:
            return bool(checker(cls))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        return getattr(cls, 'bl_rna', None) is not None
    except Exception:
        return False


def register():
    # Registration is transactional and never unregisters classes owned by a
    # different add-on version. A duplicate installation now fails clearly.
    global _DSG_REGISTERED_CLASSES, _DSG_SCENE_POINTER_OWNED
    global _DSG_LOAD_HANDLER_OWNED, _DSG_MEASURE_HANDLER_OWNED
    if _DSG_REGISTERED_CLASSES:
        return
    version_text = '.'.join(str(part) for part in bl_info['version'])
    print(f"[DSG] Registering Dental Surgical Guide v{version_text} · {bl_info['description']}")
    _register_dsg_custom_icons()

    _dsg_remove_load_handler()
    if hasattr(bpy.types.Scene, 'dsg_props'):
        try:
            del bpy.types.Scene.dsg_props
            print('[DSG] Removed stale Scene.dsg_props from older DSG version')
        except Exception as exc:
            raise RuntimeError(
                f'Could not replace stale Scene.dsg_props from a previous DSG add-on: {exc}')
    _dsg_unregister_stale_classes()

    registered = []
    current_class = None
    try:
        _install_dsg_action_guards()
        for current_class in [cls for cls in CLASSES if cls is not DSG_PT_Main]:
            bpy.utils.register_class(current_class)
            registered.append(current_class)

        bpy.types.Scene.dsg_props = PointerProperty(type=DSG_Props)
        _DSG_SCENE_POINTER_OWNED = True

        current_class = DSG_PT_Main
        bpy.utils.register_class(DSG_PT_Main)
        registered.append(DSG_PT_Main)
        if not _dsg_is_class_registered(DSG_PT_Main):
            raise RuntimeError('Blender did not confirm DSG_PT_Main registration')

        if _dsg_migrate_irrigation_outlet_to_1mm not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(_dsg_migrate_irrigation_outlet_to_1mm)
            _DSG_LOAD_HANDLER_OWNED = True

        # Measurement handlers and scene/object scans are installed later by
        # deferred_post_register(), after Blender releases _RestrictData.
        _DSG_MEASURE_HANDLER_OWNED = False

        _DSG_REGISTERED_CLASSES = registered
        print('[DSG] Dental SG sidebar registered successfully: View3D > N > DSG')
    except Exception as exc:
        failed_name = getattr(current_class, '__name__', 'Scene.dsg_props')
        print(f'[DSG] Registration failed at {failed_name}: {type(exc).__name__}: {exc}')
        _dsg_rollback_registration(registered)
        _DSG_REGISTERED_CLASSES = []
        _DSG_LOAD_HANDLER_OWNED = False
        _remove_dicom_measure_handler()
        _DSG_MEASURE_HANDLER_OWNED = False
        raise

def deferred_post_register():
    """Recover existing DSG state after Blender restores normal data access."""
    global _DSG_MEASURE_HANDLER_OWNED
    if not _dsg_data_access_ready():
        return False
    objects = bpy.data.objects
    scenes = bpy.data.scenes

    if not _DSG_MEASURE_HANDLER_OWNED:
        _register_dicom_measure_handler()
        _DSG_MEASURE_HANDLER_OWNED = True
    _register_implant_navigation_restore_handler()

    _schedule_dsg_owned_data_cleanup()
    for existing_scene in scenes:
        _migrate_model_implant_guide_flow(existing_scene)
    scene = getattr(bpy.context, 'scene', None)
    if scene is not None:
        dsg_props = getattr(scene, 'dsg_props', None)
        if dsg_props is not None and not bool(getattr(dsg_props, 'precision_ortho_lock', True)):
            try:
                dsg_props.precision_ortho_lock = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    _update_all_dicom_measurements(scene)
    existing_guide = objects.get(GUIDE_NAME)
    if _valid_obj(existing_guide):
        store_guide_home_matrix(existing_guide, force=False, scene=scene)

    _dsg_migrate_irrigation_outlet_to_1mm()
    if scene is not None and str(scene.get(SUITE_STAGE_KEY, "")).upper() == "DSG":
        activate_precision_orthographic(bpy.context)
    return True


def unregister():
    global _DSG_REGISTERED_CLASSES, _DSG_LOAD_HANDLER_OWNED, _DSG_MEASURE_HANDLER_OWNED
    try:
        restore_precision_projection(bpy.context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    lifecycle.cancel_module_timers(__name__)
    _unregister_dsg_custom_icons()
    if _DSG_LOAD_HANDLER_OWNED:
        _dsg_remove_load_handler()
    _DSG_LOAD_HANDLER_OWNED = False
    _remove_dicom_measure_handler()
    _remove_implant_navigation_restore_handler()
    _DSG_MEASURE_HANDLER_OWNED = False
    _IMPLANT_STEP_RETURN_STATE.clear()
    _IMPLANT_STEP_RESTORE_PENDING.clear()
    unregister_contour_draw_handler()
    unregister_irr_draw_handler()
    _dsg_remove_scene_pointer()

    for cls in reversed(list(_DSG_REGISTERED_CLASSES)):
        _dsg_unregister_class_object(cls)
    _DSG_REGISTERED_CLASSES = []


if __name__ == "__main__":
    register()
