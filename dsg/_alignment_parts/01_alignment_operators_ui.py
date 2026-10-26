



def _apply_points(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
    homogeneous = np.ones((len(points), 4), dtype=np.float64)
    homogeneous[:, :3] = points
    return (transform @ homogeneous.T).T[:, :3]


def _apply_normals(normals: np.ndarray, transform: np.ndarray) -> np.ndarray:
    rotation = transform[:3, :3].copy()
    scale = max(float(np.linalg.norm(rotation, axis=0).mean()), 1.0e-12)
    rotation /= scale
    transformed = normals @ rotation.T
    return transformed / np.maximum(np.linalg.norm(transformed, axis=1, keepdims=True), 1.0e-12)


def _rotation_degrees(transform: np.ndarray) -> float:
    rotation = transform[:3, :3].copy()
    rotation /= max(float(np.linalg.norm(rotation, axis=0).mean()), 1.0e-12)
    value = np.clip((np.trace(rotation) - 1.0) * 0.5, -1.0, 1.0)
    return float(np.degrees(np.arccos(value)))


def _trimmed_correspondences(distances, valid_mask, keep_ratio: float):
    valid_indices = np.flatnonzero(valid_mask)
    if len(valid_indices) < PATCH_MIN_CORRESPONDENCES:
        return None
    keep_count = max(PATCH_MIN_CORRESPONDENCES, int(len(valid_indices) * keep_ratio))
    valid_distances = distances[valid_indices]
    if keep_count < len(valid_indices):
        local = np.argpartition(valid_distances, keep_count - 1)[:keep_count]
        return valid_indices[local]
    return valid_indices




# =============================================================================
# LANDMARK VALIDATION
# =============================================================================


def _triangle_metrics(points: np.ndarray) -> tuple[float, float]:
    distances = [
        float(np.linalg.norm(points[0] - points[1])),
        float(np.linalg.norm(points[1] - points[2])),
        float(np.linalg.norm(points[0] - points[2])),
    ]
    maximum_edge = max(distances)
    area = 0.5 * float(np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0])))
    normalized_area = area / max(maximum_edge * maximum_edge, 1.0e-12)
    return maximum_edge, normalized_area


def _validate_single_landmark_triangle(points: np.ndarray, props=None, label: str = "") -> tuple[bool, str]:
    span, normalized_area = _triangle_metrics(points)
    if span < MIN_LANDMARK_SPAN_MM:
        return False, _t(
            props,
            f"The {label or 'three zones'} are too close. Use anterior, right posterior and left posterior surfaces.",
            f"Las {label or 'tres zonas'} estÃƒÂ¡n demasiado juntas. Usa anterior, posterior derecha y posterior izquierda.",
        )
    if normalized_area < MIN_NORMALIZED_TRIANGLE_AREA:
        return False, _t(
            props,
            f"The {label or 'three zones'} are almost aligned. Move one zone laterally.",
            f"Las {label or 'tres zonas'} estÃƒÂ¡n casi alineadas. Desplaza lateralmente una zona.",
        )
    return True, ""


def _validate_landmark_geometry(source_points: np.ndarray, target_points: np.ndarray, props=None) -> tuple[bool, str]:
    labels = ((_t(props, "scan", "escaneado"), source_points), ("DICOM", target_points))
    for label, points in labels:
        span, normalized_area = _triangle_metrics(points)
        if span < MIN_LANDMARK_SPAN_MM:
            return False, _t(props, f"The {label} points are too close. Spread them across the arch.", f"Los puntos del {label} estÃƒÂ¡n demasiado juntos. DistribÃƒÂºyelos por la arcada.")
        if normalized_area < MIN_NORMALIZED_TRIANGLE_AREA:
            return False, _t(props, f"The {label} points are almost collinear. Move one laterally.", f"Los puntos del {label} estÃƒÂ¡n casi alineados. Separa lateralmente uno de ellos.")

    source_lengths = np.asarray([
        np.linalg.norm(source_points[0] - source_points[1]),
        np.linalg.norm(source_points[1] - source_points[2]),
        np.linalg.norm(source_points[0] - source_points[2]),
    ])
    target_lengths = np.asarray([
        np.linalg.norm(target_points[0] - target_points[1]),
        np.linalg.norm(target_points[1] - target_points[2]),
        np.linalg.norm(target_points[0] - target_points[2]),
    ])

    absolute_difference = np.abs(source_lengths - target_lengths)
    relative_difference = absolute_difference / np.maximum(np.maximum(source_lengths, target_lengths), 1.0e-6)
    if np.any(
        (absolute_difference > MAX_PAIR_DISTANCE_ABSOLUTE_ERROR_MM)
        & (relative_difference > MAX_PAIR_DISTANCE_RELATIVE_ERROR)
    ):
        # The point pairs are now hints rather than a rigid registration gate.
        # Whole-mesh multi-hypothesis analysis can recover a safe pose even when
        # one point is inaccurate or the pair order is imperfect.  Degenerate
        # triangles are still rejected above because they contain no usable 3D
        # orientation information at all.
        return True, _t(
            props,
            "Point pairs are approximate; whole-mesh refinement will resolve them.",
            "Los pares son aproximados; el refinado global de mallas los corregirÃƒÂ¡.",
        )

    return True, ""


# =============================================================================
# PROPERTIES
# =============================================================================


class DICP_Props(PropertyGroup):
    current_step: IntProperty(default=STEP_MODELS, min=STEP_MODELS, max=STEP_DONE)
    ui_language: EnumProperty(
        name="Idioma",
        items=core.LANGUAGE_ITEMS,
        get=_language_get,
        set=_language_set,
    )
    show_reset_flow: BoolProperty(
        name="Back",
        default=False,
        description="Shows or hides the action that returns alignment to its initial state while preserving its input models",
    )

    icp_source_obj: PointerProperty(name="IOS / Escaneado", type=bpy.types.Object)
    icp_target_obj: PointerProperty(name="Fixed reference", type=bpy.types.Object)

    source_point_1: FloatVectorProperty(size=3, subtype='XYZ')
    source_point_2: FloatVectorProperty(size=3, subtype='XYZ')
    source_point_3: FloatVectorProperty(size=3, subtype='XYZ')
    target_point_1: FloatVectorProperty(size=3, subtype='XYZ')
    target_point_2: FloatVectorProperty(size=3, subtype='XYZ')
    target_point_3: FloatVectorProperty(size=3, subtype='XYZ')

    source_point_count: IntProperty(default=0, min=0, max=3)
    target_point_count: IntProperty(default=0, min=0, max=3)

    original_source_matrix: StringProperty(default="")
    original_source_name: StringProperty(default="")
    ios_source_filepath: StringProperty(default="")
    landmark_rmse: FloatProperty(default=0.0, precision=3)
    icp_error: FloatProperty(default=0.0, precision=3)
    icp_overlap: FloatProperty(default=0.0, precision=1)
    icp_p95: FloatProperty(default=0.0, precision=3, options={'HIDDEN'})
    icp_valid_pairs: IntProperty(default=0, min=0, max=3, options={'HIDDEN'})
    icp_max_patch_error: FloatProperty(default=0.0, precision=3, options={'HIDDEN'})
    icp_min_patch_coverage: FloatProperty(default=0.0, precision=1, options={'HIDDEN'})
    icp_max_patch_normal_angle: FloatProperty(default=0.0, precision=1, options={'HIDDEN'})
    icp_zone_summary: StringProperty(default="", options={'HIDDEN'})
    alignment_quality_approved: BoolProperty(default=False, options={'HIDDEN'})
    mesh_refinement_used: BoolProperty(default=False, options={'HIDDEN'})
    mesh_refinement_score_before: FloatProperty(default=0.0, precision=3, options={'HIDDEN'})
    mesh_refinement_score_after: FloatProperty(default=0.0, precision=3, options={'HIDDEN'})
    mesh_refinement_coverage_before: FloatProperty(default=0.0, precision=1, options={'HIDDEN'})
    mesh_refinement_coverage_after: FloatProperty(default=0.0, precision=1, options={'HIDDEN'})
    mesh_reanchored_zones: IntProperty(default=0, min=0, max=3, options={'HIDDEN'})
    status_message: StringProperty(default="")
    aligned: BoolProperty(default=False)
    alignment_running: BoolProperty(default=False)
    alignment_progress: FloatProperty(default=0.0, min=0.0, max=1.0, subtype='FACTOR')
    source_patch_vertices: IntProperty(default=0, min=0)
    target_patch_vertices: IntProperty(default=0, min=0)


# =============================================================================
# OPERATORS
# =============================================================================



class DICP_OT_ImportIOSSTL(Operator, ImportHelper):
    bl_idname = "dicp.import_ios_stl"
    bl_label = "Import intraoral STL"
    bl_description = "Import the intraoral scan STL and prepare it as the moving alignment model"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={'HIDDEN'})

    def execute(self, context):
        props = context.scene.dicp_props
        _set_dicom_collections_hidden(context, False)
        try:
            source, imported_objects = _import_stl_file(context, self.filepath)
        except Exception as exc:
            _report(
                self,
                {'ERROR'},
                props,
                f"Could not import the intraoral STL: {exc}",
                f"No se pudo importar el STL intraoral: {exc}",
            )
            return {'CANCELLED'}

        # The largest imported mesh is the clinical IOS. Any additional mesh
        # created by the importer remains untouched but does not enter alignment.
        _set_role(source, ROLE_IOS_SCAN)
        source.name = "Dental_IOS"
        source["dental_suite_source_path"] = str(self.filepath)
        source["dental_suite_component"] = "ALIGNMENT"
        source["dental_suite_protocol"] = SUITE_PROTOCOL_VERSION
        source.pop('DSG_alignment_thin_review', None)
        ensure_ios_gray_material(source, context=context)
        # FDI is established from the CBCT before alignment in DSG 8.8.
        # Importing a new IOS must never erase the reviewed CBCT dentition.
        source["DSG_dental_identity_source"] = "CBCT"

        target = _latest_alignment_reference(context, props, exclude=source)

        props.icp_source_obj = source
        props.icp_target_obj = target
        props.ios_source_filepath = str(self.filepath)
        props.original_source_matrix = _matrix_to_text(source.matrix_world)
        props.original_source_name = source.name
        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_MODELS
        props.alignment_running = False
        props.alignment_progress = 0.0
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        _set_active_only(context, source)

        if target is None:
            _report(
                self,
                {'WARNING'},
                props,
                f"Imported {source.name}. Select any fixed reference mesh before alignment.",
                f"Se importÃƒÂ³ {source.name}. Selecciona cualquier malla de referencia fija antes de alinear.",
            )
        else:
            target["dental_suite_alignment_reference"] = True
            _report(
                self,
                {'INFO'},
                props,
                f"IOS imported: {source.name} | Reference: {target.name}",
                f"IOS importado: {source.name} | Referencia: {target.name}",
            )
        return {'FINISHED'}

class DICP_OT_AutoDetect(Operator):
    bl_idname = "dicp.auto_detect"
    bl_label = "Detect models"
    bl_description = "Use any selected fixed mesh as reference and the other mesh as the moving scan"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        ok, message = _auto_detect_models(context, props)
        if not ok:
            _report(self, {'ERROR'}, props, message, message)
            return {'CANCELLED'}
        _set_role(props.icp_source_obj, ROLE_IOS_SCAN)
        ensure_ios_gray_material(props.icp_source_obj, context=context)
        props.icp_target_obj["dental_suite_alignment_reference"] = True
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        props.original_source_matrix = _matrix_to_text(props.icp_source_obj.matrix_world)
        props.original_source_name = props.icp_source_obj.name
        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_MODELS
        _report(self, {'INFO'}, props,
                f"Moving: {props.icp_source_obj.name} | Reference: {props.icp_target_obj.name}",
                f"MÃƒÂ³vil: {props.icp_source_obj.name} | Referencia: {props.icp_target_obj.name}")
        return {'FINISHED'}


class DICP_OT_UseSelection(Operator):
    bl_idname = "dicp.use_selection"
    bl_label = "Usar 2 seleccionados"
    bl_description = "El objeto activo serÃƒÂ¡ la referencia fija; el otro serÃƒÂ¡ el objeto mÃƒÂ³vil"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        if not _assign_from_selection(context, props):
            _report(self, {'ERROR'}, props, "Select exactly two meshes and keep the fixed reference active.", "Selecciona exactamente dos mallas; deja activa la referencia fija.")
            return {'CANCELLED'}

        valid, message = _validate_models(props.icp_source_obj, props.icp_target_obj, props)
        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        props.icp_target_obj["dental_suite_alignment_reference"] = True
        _set_role(props.icp_source_obj, ROLE_IOS_SCAN)
        ensure_ios_gray_material(props.icp_source_obj, context=context)
        props.original_source_matrix = _matrix_to_text(props.icp_source_obj.matrix_world)
        props.original_source_name = props.icp_source_obj.name
        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_MODELS
        _report(self, {'INFO'}, props, f"Scan: {props.icp_source_obj.name} | DICOM: {props.icp_target_obj.name}", f"Escaneado: {props.icp_source_obj.name} | DICOM: {props.icp_target_obj.name}")
        return {'FINISHED'}


def _landmark_event_in_viewport(area, region, event):
    """Exclude overlapping UI regions; WINDOW bounds also include Blender's sidebar."""
    x, y = event.mouse_x, event.mouse_y
    def inside(part):
        return (part.x <= x < part.x + part.width
                and part.y <= y < part.y + part.height)
    return inside(region) and not any(
        part.type != 'WINDOW' and inside(part) for part in area.regions)


class DICP_OT_PickLandmarks(Operator):
    bl_idname = "dicp.pick_landmarks"
    bl_label = "Marcar zonas"
    bl_description = "Marca anterior, posterior derecha y posterior izquierda en el IOS y en la referencia DICOM"
    bl_options = {'REGISTER', 'UNDO'}

    _phase = "source"
    _area = None
    _region = None
    _rv3d = None
    _space = None
    _source = None
    _target = None
    _source_state = None
    _target_state = None
    _selected_names = None
    _active_name = ""
    _clinical_overlay_states = None
    _target_dental_bvh = None

    def _save_object_state(self, obj):
        return {
            "hide_viewport": bool(obj.hide_viewport),
            "hide_get": bool(obj.hide_get()) if obj.name in bpy.context.view_layer.objects else bool(obj.hide_viewport),
            "selected": bool(obj.select_get()) if obj.name in bpy.context.view_layer.objects else False,
        }

    def _ensure_in_view_layer(self, context, obj) -> bool:
        """Make an ICP participant addressable by hide_set/select/raycast.

        Immediate arch composites may remain linked only to an excluded DICOM
        collection. Blender keeps the Object datablock valid, but all per-view-
        layer APIs then raise RuntimeError. A second link to the scene master
        collection is non-destructive and preserves the original collection.
        """
        if obj is None:
            return False
        if obj.name in context.view_layer.objects:
            return True
        try:
            if obj.name not in context.scene.collection.objects:
                context.scene.collection.objects.link(obj)
            obj["DSG_alignment_view_layer_link"] = True
            context.view_layer.update()
        except Exception as exc:
            print(f"[DSG Alignment] ViewLayer link failed for {getattr(obj, 'name', '?')}: {exc}")
        return obj.name in context.view_layer.objects

    def _restore_scene_state(self, context):
        for obj, state in ((self._source, self._source_state), (self._target, self._target_state)):
            if obj and state:
                obj.hide_viewport = state["hide_viewport"]
                obj.hide_set(state["hide_get"])

        for obj, state in self._clinical_overlay_states or []:
            try:
                obj.hide_viewport = state["hide_viewport"]
                obj.hide_set(state["hide_get"])
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        bpy.ops.object.select_all(action='DESELECT')
        for name in self._selected_names or []:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)
        active = bpy.data.objects.get(self._active_name) if self._active_name else None
        if active:
            context.view_layer.objects.active = active

        context.workspace.status_text_set(None)

    def _focus(self, context, obj, other):
        # The displayed DICOM surface during landmark picking must be exactly the
        # ray-cast/ICP target. Hide the smoothed duplicate clinical teeth/labels
        # until the picker ends, preventing a visual-vs-mathematical mismatch.
        for overlay, _state in self._clinical_overlay_states or []:
            try:
                overlay.hide_viewport = True
                overlay.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        obj.hide_viewport = False
        if obj.name in context.view_layer.objects:
            obj.hide_set(False)
        other.hide_viewport = False
        if other.name in context.view_layer.objects:
            other.hide_set(True)

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        try:
            with context.temp_override(area=self._area, region=self._region, space_data=self._space):
                bpy.ops.view3d.view_selected(use_all_regions=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    def _set_status(self, context):
        props = context.scene.dicp_props
        if self._phase == "source":
            index = min(props.source_point_count, 2)
            zone = _zone_label(props, index)
            context.workspace.status_text_set(_t(
                props,
                f"IOS Ã‚Â· {zone} Ã‚Â· click the facial/lingual wall Ã‚Â· Backspace undo Ã‚Â· Esc cancel",
                f"IOS Ã‚Â· {zone} Ã‚Â· pulsa sobre la pared vestibular/lingual Ã‚Â· Retroceso deshacer Ã‚Â· Esc cancelar",
            ))
        else:
            index = min(props.target_point_count, 2)
            zone = _zone_label(props, index)
            context.workspace.status_text_set(_t(
                props,
                f"CBCT COMPOSITE Ã‚Â· same {zone} zone Ã‚Â· click a tooth Ã‚Â· Backspace undo Ã‚Â· Esc cancel",
                f"CBCT COMPUESTO Ã‚Â· misma zona {zone} Ã‚Â· pulsa sobre un diente Ã‚Â· Retroceso deshacer Ã‚Â· Esc cancelar",
            ))

    def _raycast(self, context, event, obj):
        x = event.mouse_x - self._region.x
        y = event.mouse_y - self._region.y
        if x < 0 or y < 0 or x >= self._region.width or y >= self._region.height:
            return None

        coordinate = (x, y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(self._region, self._rv3d, coordinate)
        ray_direction = view3d_utils.region_2d_to_vector_3d(self._region, self._rv3d, coordinate)

        depsgraph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        inverse = evaluated.matrix_world.inverted_safe()
        local_origin = inverse @ ray_origin
        local_direction = inverse.to_3x3() @ ray_direction
        if local_direction.length < 1.0e-12:
            return None
        local_direction.normalize()

        if obj == self._target and self._target_dental_bvh is not None:
            location, _normal, _index, _distance = self._target_dental_bvh.ray_cast(
                local_origin, local_direction, 1.0e7
            )
            return Vector(location) if location is not None else None

        hit, location, _normal, _face_index = evaluated.ray_cast(
            local_origin,
            local_direction,
            distance=1.0e7,
        )
        return Vector(location) if hit else None

    def _cancel(self, context):
        props = context.scene.dicp_props
        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_MODELS
        self._restore_scene_state(context)
        return {'CANCELLED'}

    def invoke(self, context, event):
        props = context.scene.dicp_props
        _set_dicom_collections_hidden(context, False)
        _ensure_object_mode(context)

        if props.icp_source_obj is None or props.icp_target_obj is None:
            _assign_from_selection(context, props)

        valid, message = _validate_models(props.icp_source_obj, props.icp_target_obj, props)
        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        if context.area is None or context.area.type != 'VIEW_3D':
            _report(self, {'ERROR'}, props, "Run this tool from a 3D View.", "Ejecuta esta herramienta desde una vista 3D.")
            return {'CANCELLED'}

        if any(op.bl_idname == self.bl_idname and op != self
               for op in context.window.modal_operators):
            self.report({'INFO'}, 'El marcado de puntos ya estÃƒÂ¡ activo.')
            return {'CANCELLED'}

        self._area = context.area
        self._space = context.space_data
        self._region = next((region for region in context.area.regions if region.type == 'WINDOW'), None)
        self._rv3d = self._space.region_3d
        if self._region is None or self._rv3d is None:
            _report(self, {'ERROR'}, props, "No valid 3D region was found.", "No se encontrÃƒÂ³ una regiÃƒÂ³n 3D vÃƒÂ¡lida.")
            return {'CANCELLED'}

        # Selecting the other intraoral scan in the viewport chooses it as
        # the IOS to align (the previous one becomes the antagonist).
        try:
            chosen = context.view_layer.objects.active
            if (chosen is not None and chosen != props.icp_source_obj and chosen.select_get()
                    and chosen in core.alignment_ios_candidates(props.icp_source_obj)):
                core.set_alignment_ios(context, chosen)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        self._source = props.icp_source_obj
        self._source.pop('DSG_alignment_thin_review', None)
        ensure_ios_gray_material(self._source)
        self._target = props.icp_target_obj
        if not self._ensure_in_view_layer(context, self._source):
            self.report({'ERROR'}, "El escaneado IOS no pertenece al View Layer activo")
            return {'CANCELLED'}
        if not self._ensure_in_view_layer(context, self._target):
            self.report({'ERROR'}, "El compuesto DICOM no pertenece al View Layer activo")
            return {'CANCELLED'}
        self._source_state = self._save_object_state(self._source)
        self._target_state = self._save_object_state(self._target)

        self._clinical_overlay_states = []
        self._target_dental_bvh = None
        try:
            from . import cbct_dental_module
            overlays = list(
                cbct_dental_module.segmented_alignment_source_objects(context)
            )
            overlays.extend([
                item for item in context.scene.objects
                if str(getattr(item, "name", "")).startswith(
                    cbct_dental_module.LABEL_OBJECT_PREFIX)
            ])
            for overlay in overlays:
                if overlay not in {self._source, self._target}:
                    self._clinical_overlay_states.append(
                        (overlay, self._save_object_state(overlay)))
            self._target_dental_bvh = _alignment_composite_dental_bvh(self._target)
        except Exception:
            self._clinical_overlay_states = []
            self._target_dental_bvh = None
        # While picking, only the model of the current phase may be visible
        # (IOS, then the CBCT composite).  Every other visible object
        # (segmented jaws, sinus/nasal cavities, the other arch, CBCT volume
        # and slices) is hidden here and restored when the picker ends.
        listed = {overlay.name for overlay, _state in self._clinical_overlay_states}
        for item in list(context.view_layer.objects):
            try:
                if item in {self._source, self._target} or item.name in listed:
                    continue
                if item.type not in {'MESH', 'CURVE', 'FONT', 'VOLUME', 'POINTCLOUD', 'EMPTY'}:
                    continue
                if item.hide_get() or item.hide_viewport:
                    continue
                self._clinical_overlay_states.append((item, self._save_object_state(item)))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        self._selected_names = [obj.name for obj in context.selected_objects]
        active = context.view_layer.objects.active
        self._active_name = active.name if active else ""

        original = _matrix_from_text(props.original_source_matrix)
        # The aligned IOS is renamed to Dental_IOS_Aligned.  Do not interpret
        # that canonical rename as a new source and overwrite the true initial
        # matrix when the user falls back to three zones.
        if original is None:
            props.original_source_matrix = _matrix_to_text(self._source.matrix_world)
            if not props.original_source_name:
                props.original_source_name = self._source.name
            original = self._source.matrix_world.copy()
        elif props.aligned:
            self._source.matrix_world = original
            context.view_layer.update()

        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_LANDMARKS
        self._phase = "source"
        self._focus(context, self._source, self._target)
        self._set_status(context)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dicp_props

        # A sidebar action can replace the IOS while this modal handler is alive.
        # Restore its temporary visibility, then show the newly selected models.
        if props.icp_source_obj != self._source or props.icp_target_obj != self._target:
            self._restore_scene_state(context)
            core._show_only_alignment_ios(context, props)
            return {'CANCELLED'}

        if not _landmark_event_in_viewport(self._area, self._region, event):
            return {'PASS_THROUGH'}

        if event.type == 'ESC' and event.value == 'PRESS':
            return self._cancel(context)

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}

        if (event.type in {'BACK_SPACE', 'DEL', 'RIGHTMOUSE'} or (event.type == 'Z' and event.ctrl)) and event.value == 'PRESS':
            if self._phase == "target" and props.target_point_count > 0:
                props.target_point_count -= 1
            elif self._phase == "target" and props.target_point_count == 0:
                self._phase = "source"
                props.source_point_count = max(0, props.source_point_count - 1)
                self._focus(context, self._source, self._target)
            elif props.source_point_count > 0:
                props.source_point_count -= 1

            _rebuild_markers(props)
            self._set_status(context)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            active_object = self._source if self._phase == "source" else self._target
            point = self._raycast(context, event, active_object)
            if point is None:
                _report(self, {'WARNING'}, props, "Click directly on the model surface.", "Haz clic directamente sobre la superficie del modelo.")
                return {'RUNNING_MODAL'}

            if self._phase == "source":
                index = props.source_point_count
                if index >= 3:
                    return {'RUNNING_MODAL'}
                _set_local_landmark(props, "source", index, point)
                props.source_point_count += 1
                _create_marker(self._source, point, "IOS", index)

                if props.source_point_count == 3:
                    source_world = _world_landmarks(self._source, _get_local_landmarks(props, "source"))
                    valid_triangle, triangle_message = _validate_single_landmark_triangle(
                        source_world,
                        props,
                        _t(props, "IOS zones", "zonas IOS"),
                    )
                    if not valid_triangle:
                        self.report({'ERROR'}, triangle_message)
                        props.source_point_count = 2
                        marker = next(
                            (obj for obj in bpy.data.objects if obj.name.startswith(f"{LANDMARK_PREFIX}IOS_3_")),
                            None,
                        )
                        if marker is not None:
                            bpy.data.objects.remove(marker, do_unlink=True)
                        self._set_status(context)
                        return {'RUNNING_MODAL'}
                    self._phase = "target"
                    self._focus(context, self._target, self._source)

            else:
                index = props.target_point_count
                if index >= 3:
                    return {'RUNNING_MODAL'}
                _set_local_landmark(props, "target", index, point)
                props.target_point_count += 1
                _create_marker(self._target, point, "DICOM", index)

                if props.target_point_count == 3:
                    source_world = _world_landmarks(self._source, _get_local_landmarks(props, "source"))
                    target_world = _world_landmarks(self._target, _get_local_landmarks(props, "target"))
                    valid, message = _validate_landmark_geometry(source_world, target_world, props)
                    if not valid:
                        self.report({'ERROR'}, message)
                        props.target_point_count = 0
                        for obj in list(bpy.data.objects):
                            if obj.name.startswith(f"{LANDMARK_PREFIX}DICOM_"):
                                bpy.data.objects.remove(obj, do_unlink=True)
                        self._set_status(context)
                        return {'RUNNING_MODAL'}

                    landmark_transform = _best_fit(source_world, target_world)
                    aligned_landmarks = _apply_points(source_world, landmark_transform)
                    props.landmark_rmse = float(
                        np.sqrt(np.mean(np.sum((aligned_landmarks - target_world) ** 2, axis=1)))
                    )
                    props.current_step = STEP_READY
                    props.status_message = _t(props, "Three robust zones ready", "Tres zonas robustas preparadas")
                    self._restore_scene_state(context)
                    _report(self, {'INFO'}, props, "Zones ready. Press Align models.", "Zonas preparadas. Pulsa Alinear modelos.")
                    return {'FINISHED'}

            self._set_status(context)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}


# =============================================================================
# DSG v9 Ã‚Â· alineaciÃƒÂ³n solo con 3 puntos
# Kabsch con los 3 pares de puntos + un ICP punto-a-plano recortado sobre los
# dientes alrededor de esos puntos. Un ÃƒÂºnico execute(), sin modal ni modo
# automÃƒÂ¡tico.
# =============================================================================
THREE_POINT_CROP_RADIUS_MM = 10.0
THREE_POINT_SOURCE_VOXEL_MM = 0.25
THREE_POINT_TARGET_VOXEL_MM = 0.20
THREE_POINT_MAX_SOURCE = 9000
THREE_POINT_MAX_TARGET = 16000
THREE_POINT_ICP_ITERATIONS = 50
THREE_POINT_SCHEDULE_ITERATIONS = 20
THREE_POINT_START_DISTANCE_MM = 2.0
THREE_POINT_END_DISTANCE_MM = 0.6
THREE_POINT_NORMAL_ANGLE_DEG = 60.0
THREE_POINT_KEEP_RATIO = 0.85
THREE_POINT_MIN_PAIRS = 60
THREE_POINT_MIN_ZONE_PAIRS = 30
THREE_POINT_MAX_ICP_TRANSLATION_MM = 5.0
THREE_POINT_MAX_ICP_ROTATION_DEG = 10.0
THREE_POINT_EVAL_DISTANCE_MM = 1.0


def _ensure_scipy_kdtree() -> bool:
    """Load SciPy from DSG's private runtime if the module import missed it."""
    namespace = globals()
    if namespace.get("_SciPyKDTree") is not None:
        return True
    try:
        spatial = dicom_module.load_scipy_spatial()
        if spatial is not None:
            namespace["_SciPyKDTree"] = spatial.cKDTree
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return namespace.get("_SciPyKDTree") is not None


def _crop_near_seeds(points, normals, seeds, radius):
    seeds = np.asarray(seeds, dtype=np.float64)
    distance_sq = np.min(
        np.sum((points[:, None, :] - seeds[None, :, :]) ** 2, axis=2), axis=1
    ) if len(points) <= 400000 else None
    if distance_sq is None:
        keep = np.zeros(len(points), dtype=bool)
        for seed in seeds:
            keep |= np.sum((points - seed) ** 2, axis=1) <= radius * radius
    else:
        keep = distance_sq <= radius * radius
    return points[keep], normals[keep]


def _three_point_matches(src, src_n, index, tgt, tgt_n, max_distance):
    matched, idx, dist = index.query(src)
    valid = np.isfinite(dist) & (dist <= max_distance)
    dots = np.abs(np.sum(src_n * tgt_n[idx], axis=1))
    valid &= dots >= math.cos(math.radians(THREE_POINT_NORMAL_ANGLE_DEG))
    selected = _trimmed_correspondences(dist, valid, THREE_POINT_KEEP_RATIO)
    return matched, idx, dist, selected


def three_point_icp(source_points, source_normals, target_points, target_normals):
    """Return (transform 4x4, iterations) aligning source onto target."""
    index = _NearestIndex(target_points)
    src = np.asarray(source_points, dtype=np.float64).copy()
    src_n = np.asarray(source_normals, dtype=np.float64).copy()
    total = np.eye(4, dtype=np.float64)
    iterations = 0
    for iteration in range(THREE_POINT_ICP_ITERATIONS):
        ratio = min(1.0, iteration / max(THREE_POINT_SCHEDULE_ITERATIONS - 1, 1))
        max_distance = THREE_POINT_START_DISTANCE_MM + ratio * (THREE_POINT_END_DISTANCE_MM - THREE_POINT_START_DISTANCE_MM)
        _matched, idx, _dist, selected = _three_point_matches(src, src_n, index, target_points, target_normals, max_distance)
        if selected is None or len(selected) < THREE_POINT_MIN_PAIRS:
            break
        step = _point_to_plane_huber_transform(
            src[selected], target_points[idx[selected]], target_normals[idx[selected]],
            huber_delta_mm=0.25, max_translation_mm=1.0, max_rotation_deg=2.0,
        )
        src = _apply_points(src, step)
        src_n = _apply_normals(src_n, step)
        total = step @ total
        iterations = iteration + 1
        moved = float(np.linalg.norm(step[:3, 3]))
        if iteration >= THREE_POINT_SCHEDULE_ITERATIONS and moved < 5.0e-4 and _rotation_degrees(step) < 5.0e-3:
            break
    return total, iterations


def three_point_metrics(source_points, source_normals, target_points, target_normals, source_seeds):
    """RMS, p95, overlap and per-zone details after alignment."""
    index = _NearestIndex(target_points)
    _matched, _idx, dist, selected = _three_point_matches(
        source_points, source_normals, index, target_points, target_normals, THREE_POINT_EVAL_DISTANCE_MM
    )
    zone_of = np.argmin(
        np.sum((source_points[:, None, :] - np.asarray(source_seeds)[None, :, :]) ** 2, axis=2), axis=1
    )
    selected = np.asarray(selected if selected is not None else [], dtype=np.int64)
    details = []
    for zone in range(3):
        in_zone = int(np.count_nonzero(zone_of == zone))
        chosen = selected[zone_of[selected] == zone] if len(selected) else selected
        error = float(np.sqrt(np.mean(np.square(dist[chosen])))) if len(chosen) else 0.0
        coverage = 100.0 * len(chosen) / max(in_zone, 1)
        details.append({"index": zone, "zone": ROBUST_ZONE_KEYS[zone], "valid": bool(len(chosen) >= THREE_POINT_MIN_ZONE_PAIRS),
                        "error": error, "coverage": coverage, "pairs": int(len(chosen))})
    if len(selected) == 0:
        return 0.0, 0.0, 0.0, 0, details
    rms = float(np.sqrt(np.mean(np.square(dist[selected]))))
    p95 = float(np.percentile(dist[selected], 95.0))
    overlap = 100.0 * len(selected) / max(len(source_points), 1)
    valid_zones = sum(1 for detail in details if detail["valid"])
    return rms, overlap, p95, valid_zones, details


class DICP_OT_RunAlignment(Operator):
    bl_idname = "dicp.run_alignment"
    bl_label = "Alinear modelos"
    bl_description = "Ajuste con los 3 pares de puntos y un ICP sobre los dientes cercanos"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        target = props.icp_target_obj
        valid, message = _validate_models(source, target, props)
        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        if props.source_point_count != 3 or props.target_point_count != 3:
            _report(self, {'ERROR'}, props, "Mark the three points first.", "Marca primero los tres puntos en el IOS y en el CBCT.")
            return {'CANCELLED'}
        if not _ensure_scipy_kdtree():
            _DSG_LOG.warning("SciPy no disponible: el ICP usarÃƒÂ¡ el KDTree de Blender (mÃƒÂ¡s lento)")
        _ensure_object_mode(context)

        original = _matrix_from_text(props.original_source_matrix)
        if original is None:
            original = source.matrix_world.copy()
            props.original_source_matrix = _matrix_to_text(original)
        matrix_before = source.matrix_world.copy()
        started = __import__("time").perf_counter()
        try:
            source.matrix_world = original
            context.view_layer.update()
            source_landmarks = _world_landmarks(source, _get_local_landmarks(props, "source"))
            target_landmarks = _world_landmarks(target, _get_local_landmarks(props, "target"))
            ok, message = _validate_landmark_geometry(source_landmarks, target_landmarks, props)
            if not ok:
                raise ValueError(message)
            landmark_transform = _best_fit(source_landmarks, target_landmarks)
            aligned_landmarks = _apply_points(source_landmarks, landmark_transform)
            props.landmark_rmse = float(np.sqrt(np.mean(np.sum((aligned_landmarks - target_landmarks) ** 2, axis=1))))
            source.matrix_world = Matrix(landmark_transform.tolist()) @ source.matrix_world
            context.view_layer.update()

            source_graph = _extract_world_mesh_graph(source)
            target_graph = _extract_world_mesh_graph(target)
            if source_graph is None or target_graph is None:
                raise RuntimeError(_t(props, "The meshes could not be read.", "No se pudieron leer las mallas."))
            src_pts, src_nrm = _crop_near_seeds(source_graph.points, source_graph.normals, target_landmarks, THREE_POINT_CROP_RADIUS_MM)
            tgt_pts, tgt_nrm = _crop_near_seeds(target_graph.points, target_graph.normals, target_landmarks, THREE_POINT_CROP_RADIUS_MM + 2.0)
            src_pts, src_nrm = _voxel_downsample(src_pts, src_nrm, THREE_POINT_SOURCE_VOXEL_MM, THREE_POINT_MAX_SOURCE, 7101)
            tgt_pts, tgt_nrm = _voxel_downsample(tgt_pts, tgt_nrm, THREE_POINT_TARGET_VOXEL_MM, THREE_POINT_MAX_TARGET, 7201)
            if src_pts is None or tgt_pts is None or len(src_pts) < THREE_POINT_MIN_PAIRS or len(tgt_pts) < THREE_POINT_MIN_PAIRS:
                raise RuntimeError(_t(props, "Too little surface around the points. Place them on teeth.",
                                      "Hay poca superficie alrededor de los puntos. ColÃƒÂ³calos sobre dientes."))

            icp, iterations = three_point_icp(src_pts, src_nrm, tgt_pts, tgt_nrm)
            centre = src_pts.mean(axis=0)
            drift = float(np.linalg.norm(_apply_points(centre.reshape(1, 3), icp)[0] - centre))
            if drift > THREE_POINT_MAX_ICP_TRANSLATION_MM or _rotation_degrees(icp) > THREE_POINT_MAX_ICP_ROTATION_DEG:
                raise RuntimeError(_t(props, "ICP moved too far from the points; mark them again.",
                                      "El ICP se alejÃƒÂ³ demasiado de los puntos; mÃƒÂ¡rcalos de nuevo."))
            source.matrix_world = Matrix(icp.tolist()) @ source.matrix_world
            context.view_layer.update()

            final_src = _apply_points(src_pts, icp)
            final_nrm = _apply_normals(src_nrm, icp)
            rms, overlap, p95, valid_zones, details = three_point_metrics(final_src, final_nrm, tgt_pts, tgt_nrm, target_landmarks)
        except Exception as exc:
            source.matrix_world = matrix_before
            context.view_layer.update()
            props.alignment_running = False
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        props.icp_error = rms
        props.icp_overlap = overlap
        props.icp_p95 = p95
        props.icp_valid_pairs = int(valid_zones)
        valid_details = [d for d in details if d["valid"]]
        props.icp_max_patch_error = max((d["error"] for d in valid_details), default=0.0)
        props.icp_min_patch_coverage = min((d["coverage"] for d in valid_details), default=0.0)
        props.icp_max_patch_normal_angle = 0.0
        props.icp_zone_summary = json.dumps(details, separators=(",", ":"))
        props.mesh_refinement_used = False
        props.source_patch_vertices = int(len(src_pts))
        props.target_patch_vertices = int(len(tgt_pts))
        approved = (
            valid_zones == 3
            and 0.0 < rms <= MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM
            and 0.0 < p95 <= MAX_ACCEPTABLE_P95_MM
            and props.icp_min_patch_coverage >= MIN_ACCEPTABLE_PATCH_COVERAGE_PERCENT
        )
        props.alignment_quality_approved = bool(approved)
        props.aligned = True
        props.current_step = STEP_DONE
        props.alignment_running = False
        props.alignment_progress = 1.0

        _set_role(source, ROLE_IOS_ALIGNED)
        source["dental_suite_aligned"] = True
        source["dental_suite_canonical_name"] = "Dental_IOS_Aligned"
        source.name = "Dental_IOS_Aligned"
        source["dicp_alignment_method"] = "THREE_POINT_KABSCH_TRIMMED_POINT_TO_PLANE_ICP"
        source["dicp_alignment_mode"] = "THREE_ZONE"
        source["dicp_icp_iterations"] = int(iterations)
        source["dicp_alignment_seconds"] = float(__import__("time").perf_counter() - started)
        target["dental_suite_alignment_reference"] = True
        source["dicp_target_name"] = target.name
        source["dicp_error_mm"] = float(rms)
        source["dicp_overlap_percent"] = float(overlap)
        source["dicp_p95_mm"] = float(p95)
        source["dicp_valid_common_areas"] = int(valid_zones)
        source["dicp_max_patch_error_mm"] = float(props.icp_max_patch_error)
        source["dicp_min_patch_coverage_percent"] = float(props.icp_min_patch_coverage)
        source["dicp_zone_validation_json"] = str(props.icp_zone_summary)
        source["dicp_alignment_approved"] = bool(approved)
        source["dicp_max_acceptable_error_mm"] = float(MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM)

        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        _set_markers_hidden(True)
        _prepare_alignment_review_view(context, source, target)
        props.status_message = _t(
            props,
            "Review the superposition, then continue." if approved else "Validation blocked. Mark the three points again.",
            "Revisa la superposiciÃƒÂ³n y continÃƒÂºa." if approved else "ValidaciÃƒÂ³n no superada. Marca de nuevo los tres puntos.",
        )
        _report(
            self, {'INFO'}, props,
            f"Alignment done Ã‚Â· error {rms:.3f} mm Ã‚Â· p95 {p95:.3f} mm",
            f"AlineaciÃƒÂ³n hecha Ã‚Â· error {rms:.3f} mm Ã‚Â· p95 {p95:.3f} mm",
        )
        return {'FINISHED'}


class DICP_OT_ReviewAlignment(Operator):
    bl_idname = "dicp.review_alignment"
    bl_label = "Revisar"
    bl_description = "Muestra juntos el IOS alineado y la referencia fija para comprobar la superposiciÃƒÂ³n"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        target = props.icp_target_obj
        if source is None or target is None or not props.aligned:
            _report(self, {'ERROR'}, props, "Align the models first.", "Alinea primero los modelos.")
            return {'CANCELLED'}
        _prepare_alignment_review_view(context, source, target)
        _set_markers_hidden(True)
        _report(self, {'INFO'}, props, "Alignment review ready.", "RevisiÃƒÂ³n del alineamiento preparada.")
        return {'FINISHED'}


class DICP_OT_SendToDSG(Operator):
    bl_idname = "dicp.send_to_dsg"
    bl_label = "Siguiente"
    bl_description = "Salta cualquier paso pendiente del alineamiento y pasa a la guÃƒÂ­a DSG"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.dicp_props
        if props.icp_source_obj is None or not props.aligned:
            _report(self, {'ERROR'}, props, "Align the models first.", "Alinea primero los modelos.")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        warnings = []
        # DSG v9: SIGUIENTE never blocks.  An unfinished virtual
        # post-extraction IOS is discarded so the guide never receives a
        # half-built mesh; a confirmed one is kept.
        pending_preview = str(scene.get("DSG_ios_postextraction_preview_name", "") or "")
        if pending_preview and not bool(scene.get("DSG_ios_postextraction_confirmed", False)):
            bpy.ops.dsg_suite.restore_ios_preextraction()
            warnings.append(_t(props, "unfinished post-extraction IOS discarded", "IOS postextracciÃƒÂ³n sin terminar descartado"))
        elif (core.clinical_route(scene) == core.ROUTE_IMMEDIATE
              and str(scene.get("DSG_immediate_extraction_fdis_json", "[]") or "[]") not in {"", "[]"}
              and not bool(scene.get("DSG_ios_postextraction_confirmed", False))):
            warnings.append(_t(props, "IOS extraction deferred until inward socket closure", "extracciÃƒÂ³n IOS despuÃƒÂ©s del cierre del hueco hacia dentro"))
        if not bool(props.alignment_quality_approved):
            warnings.append(_t(props, "three-zone validation not passed", "validaciÃƒÂ³n de tres zonas no superada"))
        source = props.icp_source_obj
        _set_role(source, ROLE_IOS_ALIGNED)
        _disable_clinical_cbct_review_smoothing(context)
        try:
            from . import cbct_dental_module
            cbct_dental_module.clear_alignment_working_composite(context, restore_sources=False)
        except Exception as exc:
            print(f"[DSG Alignment] Composite cleanup warning: {exc}")
        scene[core.ROUTE_STEP_KEY] = "DSG"
        core.set_stage(scene, core.STAGE_GUIDE)
        _isolate_aligned_ios_for_guide(context, source)
        dsg_props = getattr(scene, "dsg_props", None)
        if dsg_props is not None and hasattr(dsg_props, "model_obj"):
            dsg_props.model_obj = source
            if hasattr(dsg_props, "current_step"):
                dsg_props.current_step = 0
        if warnings:
            _report(self, {'WARNING'}, props, "DSG opened Ã‚Â· " + "; ".join(warnings), "DSG abierto Ã‚Â· " + "; ".join(warnings))
        else:
            _report(self, {'INFO'}, props, "Aligned scan prepared for DSG.", "Escaneado alineado preparado para DSG.")
        return {'FINISHED'}


class DICP_OT_RestoreSource(Operator):
    bl_idname = "dicp.restore_source"
    bl_label = "Restaurar posiciÃƒÂ³n"
    bl_description = "Devuelve el escaneado a la posiciÃƒÂ³n que tenÃƒÂ­a antes de iniciar el alineamiento"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        original = _matrix_from_text(props.original_source_matrix)
        if source is None or original is None:
            _report(self, {'ERROR'}, props, "No saved initial position exists.", "No existe una posiciÃƒÂ³n inicial guardada.")
            return {'CANCELLED'}

        source.matrix_world = original
        context.view_layer.update()
        props.aligned = False
        props.icp_error = 0.0
        props.icp_overlap = 0.0
        props.icp_p95 = 0.0
        props.icp_valid_pairs = 0
        props.icp_max_patch_error = 0.0
        props.icp_min_patch_coverage = 0.0
        props.icp_max_patch_normal_angle = 0.0
        props.icp_zone_summary = ""
        props.alignment_quality_approved = False
        props.current_step = STEP_READY if props.source_point_count == 3 and props.target_point_count == 3 else STEP_MODELS
        props.status_message = _t(props, "Initial position restored", "PosiciÃƒÂ³n inicial restaurada")
        _set_markers_hidden(False)
        _report(self, {'INFO'}, props, "Initial position restored", "PosiciÃƒÂ³n inicial restaurada")
        return {'FINISHED'}


class DICP_OT_ClearLandmarks(Operator):
    bl_idname = "dicp.clear_landmarks"
    bl_label = "Redibujar puntos"
    bl_description = "Borra los seis puntos y prepara una nueva selecciÃƒÂ³n"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        original = _matrix_from_text(props.original_source_matrix)
        if source and original and props.aligned:
            source.matrix_world = original
            context.view_layer.update()

        _clear_landmark_values(props)
        _clear_markers()
        props.current_step = STEP_MODELS
        _report(self, {'INFO'}, props, "Points cleared", "Puntos eliminados")
        return {'FINISHED'}


class DICP_OT_BackToAlignment(Operator):
    bl_idname = "dicp.back_to_alignment"
    bl_label = "Deshacer ÃƒÂºltima acciÃƒÂ³n"
    bl_description = "Deshace exactamente la ÃƒÂºltima operaciÃƒÂ³n, igual que Ctrl+Z"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        props = context.scene.dicp_props
        if False:  # DSG v9: la alineaciÃƒÂ³n ya no es modal
            _report(
                self,
                {'WARNING'},
                props,
                "Cancel the running alignment with Esc before undoing.",
                "Cancela con Esc el alineamiento en curso antes de deshacer.",
            )
            return {'CANCELLED'}
        try:
            from . import workflow_history
            result = workflow_history.undo_previous(context)
        except RuntimeError as exc:
            _report(self, {'WARNING'}, props, f"Undo is not available: {exc}", f"No hay una acciÃƒÂ³n disponible para deshacer: {exc}")
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            _report(self, {'INFO'}, props, "Nothing to undo.", "No hay ninguna acciÃƒÂ³n para deshacer.")
            return {'CANCELLED'}
        _report(self, {'INFO'}, props, "Last action undone.", "ÃƒÅ¡ltima acciÃƒÂ³n deshecha.")
        return {'FINISHED'}


class DICP_OT_Reset(Operator):
    bl_idname = "dicp.reset"
    bl_label = "Back to Alignment Start"
    bl_description = "Clears alignment-generated state, restores the IOS initial position and preserves both input models"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.dicp_props

        # A second operator cannot safely remove another running modal timer.
        # Ask the modal alignment to finish its own rollback first.
        if False:  # DSG v9: la alineaciÃƒÂ³n ya no es modal
            _report(
                self,
                {'WARNING'},
                props,
                "Cancel the running alignment with Esc, then press Reset again.",
                "Cancela el alineamiento en curso con Esc y despuÃƒÂ©s pulsa Reiniciar de nuevo.",
            )
            return {'CANCELLED'}

        source = props.icp_source_obj if _is_alignment_candidate(props.icp_source_obj) else None
        target_candidate = props.icp_target_obj
        target = (
            target_candidate
            if target_candidate is not None
            and target_candidate.name in bpy.data.objects
            and target_candidate.type == 'MESH'
            else None
        )
        original = _matrix_from_text(props.original_source_matrix)

        # Match Surgical Guide semantics: preserve the initial clinical inputs,
        # but delete every result/state generated by this module.
        if source is not None and original is not None:
            try:
                source.matrix_world = original
                context.view_layer.update()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        if source is not None:
            _set_role(source, ROLE_IOS_SCAN)
            source.pop('DSG_alignment_thin_review', None)
            ensure_ios_gray_material(source, context=context)
            for key in (
                "dental_suite_aligned",
                "dental_suite_canonical_name",
                "dicp_alignment_method",
                "dicp_alignment_mode",
                "dicp_auto_zone_method",
                "dicp_auto_global_stats_json",
                "dicp_mesh_refinement_used",
                "dicp_mesh_refinement_score_before",
                "dicp_mesh_refinement_score_after",
                "dicp_mesh_refinement_coverage_before",
                "dicp_mesh_refinement_coverage_after",
                "dicp_mesh_reanchored_zones",
                "dicp_patch_radius_mm",
                "dicp_patch_select_more_rings",
                "dicp_patch_euclidean_cap_mm",
                "dicp_target_name",
                "dicp_error_mm",
                "dicp_overlap_percent",
                "dicp_p95_mm",
                "dicp_valid_common_areas",
                "dicp_max_patch_error_mm",
                "dicp_min_patch_coverage_percent",
                "dicp_max_patch_normal_median_deg",
                "dicp_zone_validation_json",
                "dicp_patch_weights",
                "dicp_alignment_approved",
                "dicp_max_acceptable_error_mm",
            ):
                try:
                    if key in source:
                        del source[key]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                if props.original_source_name:
                    source.name = props.original_source_name
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        if target is not None:
            _set_role(target, ROLE_DICOM_TEETH)

        _clear_markers()
        _clear_landmark_values(props)
        props.icp_source_obj = source
        props.icp_target_obj = target
        props.current_step = STEP_MODELS
        props.aligned = False
        props.alignment_running = False
        props.alignment_progress = 0.0
        props.landmark_rmse = 0.0
        props.icp_error = 0.0
        props.icp_overlap = 0.0
        props.icp_p95 = 0.0
        props.icp_valid_pairs = 0
        props.icp_max_patch_error = 0.0
        props.icp_min_patch_coverage = 0.0
        props.icp_max_patch_normal_angle = 0.0
        props.icp_zone_summary = ""
        props.alignment_quality_approved = False
        props.mesh_refinement_used = False
        props.mesh_refinement_score_before = 0.0
        props.mesh_refinement_score_after = 0.0
        props.mesh_refinement_coverage_before = 0.0
        props.mesh_refinement_coverage_after = 0.0
        props.mesh_reanchored_zones = 0
        props.source_patch_vertices = 0
        props.target_patch_vertices = 0
        props.show_reset_flow = False
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        _set_dicom_collections_hidden(context, False)

        if source is not None:
            try:
                source.hide_viewport = False
                source.hide_render = False
                source.hide_select = False
                _set_active_only(context, source)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if target is not None:
            try:
                target.hide_viewport = False
                target.hide_render = False
                target.hide_select = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        _report(
            self,
            {'INFO'},
            props,
            "Alignment workflow reset; input models preserved",
            "Flujo de alineamiento reiniciado; modelos de entrada conservados",
        )
        return {'FINISHED'}

# =============================================================================
# PANEL
# =============================================================================


def _draw_reset_flow_panel(layout, props) -> None:
    """Navigation/restart controls live in the shared DSG control panel."""
    return


class DICP_PT_Main(Panel):
    bl_label = "Alignment"
    bl_idname = "DICP_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = TAB_NAME
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        try:
            return core.infer_stage(context.scene) == core.STAGE_ALIGNMENT
        except Exception:
            return True

    def draw(self, context):
        layout = self.layout
        props = context.scene.dicp_props
        layout.use_property_split = False
        layout.use_property_decorate = False
        valid_models, message = _validate_models(props.icp_source_obj, props.icp_target_obj, props)

        if not valid_models:
            source = getattr(props, "icp_source_obj", None)
            source_ready = source is not None and getattr(source, "type", "") == "MESH"
            core.set_status_bar(context, str(message or _t(props, "Import/detect IOS and CBCT reference.", "Importa/detecta IOS y referencia CBCT.")))
            if not source_ready:
                row = ui_style.primary_action(layout, enabled=True)
                row.operator("dicp.import_ios_stl", text=_t(props, "IMPORT IOS", "IMPORTAR IOS"), icon_value=icon_manager.icon_id("import_stl"))
            tools = ui_style.secondary_action(layout, align=True)
            tools.operator("dsg_suite.use_selected_ios", text=_t(props, "USE SELECTED IOS", "USAR IOS SELECCIONADO"), icon="MESH_DATA")
            return

        ensure_ios_gray_material(props.icp_source_obj, context=context)
        points_ready = props.source_point_count == 3 and props.target_point_count == 3

        if not props.aligned:
            if points_ready:
                core.set_status_bar(context, _t(props, "3 points ready", "3 puntos listos"))
                align = ui_style.primary_action(layout)
                align.operator("dicp.run_alignment", text=_t(props, "ALIGN", "ALINEAR"), icon_value=icon_manager.icon_id("manual_align"))
                redo = ui_style.tertiary_action(layout)
                redo.operator("dicp.clear_landmarks", text=_t(props, "REDRAW POINTS", "REDIBUJAR PUNTOS"), icon_value=icon_manager.icon_id("back"))
            else:
                core.set_status_bar(context, _t(props, "Mark 3 points on the IOS and the same 3 on the CBCT", "Marca 3 puntos en el IOS y los mismos 3 en el CBCT"))
                candidates = core.alignment_ios_candidates(props.icp_source_obj)
                if len(candidates) > 1 and props.source_point_count == 0:
                    layout.label(text=_t(props, "IOS to align", "IOS a alinear"))
                    choose = layout.row(align=True)
                    for candidate in candidates:
                        op = choose.operator(
                            "dsg_suite.choose_alignment_ios",
                            text=core._ios_arch_label(context.scene, candidate),
                            depress=bool(candidate == props.icp_source_obj),
                        )
                        op.object_name = candidate.name
                pick = ui_style.primary_action(layout)
                pick.operator("dicp.pick_landmarks", text=_t(props, "MARK 3 POINTS", "MARCAR 3 PUNTOS"), icon_value=icon_manager.icon_id("manual_align"))
                replace = ui_style.tertiary_action(layout)
                replace.operator("dicp.import_ios_stl", text=_t(props, "CHANGE IOS", "CAMBIAR IOS"), icon_value=icon_manager.icon_id("import_stl"))
            return

        # DSG v9: once the models are aligned SIGUIENTE is always available.
        # It skips validation review and the immediate post-extraction step.
        if bool(props.alignment_quality_approved):
            core.set_status_bar(context, _t(props, f"Robust error {props.icp_error:.3f} mm", f"Error robusto {props.icp_error:.3f} mm"))
        else:
            core.set_status_bar(context, _t(props, f"Validation failed Ã‚Â· robust error {props.icp_error:.3f} mm", f"ValidaciÃƒÂ³n no superada Ã‚Â· error robusto {props.icp_error:.3f} mm"))
        go = ui_style.primary_action(layout)
        go.operator("dicp.send_to_dsg", text=_t(props, "NEXT", "SIGUIENTE"), icon_value=icon_manager.icon_id("continue"))
        review = ui_style.tertiary_action(layout)
        review.operator("dicp.back_to_alignment", text=_t(props, "MARK POINTS AGAIN", "MARCAR PUNTOS DE NUEVO"), icon_value=icon_manager.icon_id("back"))


def _draw_tooth_analyzer_section(layout, context, props):
    """Show the CBCT dentition handoff; IOS is no longer re-segmented for FDI."""
    try:
        from . import cbct_dental_module
        cbct_dental_module.draw_alignment_handoff(layout, context)
    except Exception as exc:
        print("DSG CBCT dentition handoff UI:", repr(exc))


# =============================================================================
# REGISTRATION
# =============================================================================


CLASSES = (
    DICP_Props,
    DICP_OT_ImportIOSSTL,
    DICP_OT_AutoDetect,
    DICP_OT_UseSelection,
    DICP_OT_PickLandmarks,
    DICP_OT_RunAlignment,
    DICP_OT_ReviewAlignment,
    DICP_OT_SendToDSG,
    DICP_OT_RestoreSource,
    DICP_OT_ClearLandmarks,
    DICP_OT_BackToAlignment,
    DICP_OT_Reset,
    DICP_PT_Main,
)


_ALIGNMENT_REGISTERED_CLASSES = []
_ALIGNMENT_SCENE_POINTER_OWNED = False


def _alignment_unregister_class_object(class_object):
    if class_object is None:
        return False
    try:
        bpy.utils.unregister_class(class_object)
        return True
    except Exception:
        return False


def _alignment_unregister_stale_classes():
    """Remove RNA classes left by a previous DSG/alignment installation.

    Blender can keep Scene.dicp_props/classes alive when a zip is installed
    over another DSG version.  This makes upgrades fail unless the user first
    disables the old add-on.  The cleanup is intentionally non-destructive for
    scene objects; it only releases the old Python/RNA registration.
    """
    removed = 0
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None and _alignment_unregister_class_object(existing):
            removed += 1
            continue
        if _alignment_unregister_class_object(cls):
            removed += 1
    if removed:
        print(f"[DSG] Removed {removed} stale alignment class(es) from an older version")
    return removed


def _alignment_remove_stale_scene_pointer():
    if not hasattr(bpy.types.Scene, "dicp_props"):
        return False
    try:
        del bpy.types.Scene.dicp_props
        print("[DSG] Removed stale Scene.dicp_props from older DSG/alignment version")
        return True
    except Exception as exc:
        raise RuntimeError(
            f"Could not replace stale Scene.dicp_props from a previous DSG/alignment add-on: {exc}"
        )


def register():
    global _ALIGNMENT_REGISTERED_CLASSES, _ALIGNMENT_SCENE_POINTER_OWNED
    if _ALIGNMENT_REGISTERED_CLASSES:
        return
    _alignment_remove_stale_scene_pointer()
    _alignment_unregister_stale_classes()
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.dicp_props = PointerProperty(type=DICP_Props)
        _ALIGNMENT_SCENE_POINTER_OWNED = True
        _ALIGNMENT_REGISTERED_CLASSES = registered
    except Exception:
        if _ALIGNMENT_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dicp_props"):
            del bpy.types.Scene.dicp_props
        _ALIGNMENT_SCENE_POINTER_OWNED = False
        for cls in reversed(registered):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _ALIGNMENT_REGISTERED_CLASSES = []
        raise


def unregister():
    global _ALIGNMENT_REGISTERED_CLASSES, _ALIGNMENT_SCENE_POINTER_OWNED
    lifecycle.cancel_module_timers(__name__)
    # Scene meshes/landmarks are deliberately preserved when the add-on is
    # disabled. Unregister must release code, not destructively edit the case.
    if _ALIGNMENT_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dicp_props"):
        del bpy.types.Scene.dicp_props
    _ALIGNMENT_SCENE_POINTER_OWNED = False
    for cls in reversed(list(_ALIGNMENT_REGISTERED_CLASSES)):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _ALIGNMENT_REGISTERED_CLASSES = []


if __name__ == "__main__":
    register()
