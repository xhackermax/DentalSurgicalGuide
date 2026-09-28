def _evaluate_common_patch_pairs_detailed(
    source_patches,
    source_normals,
    target_patches,
    target_normals,
):
    """Evaluate the three selected clinical zones independently and together."""
    patch_errors = []
    patch_coverages = []
    all_distances = []
    details = []
    valid_pairs = 0
    for patch_index in range(min(len(source_patches), len(target_patches), 3)):
        result = _reciprocal_correspondences(
            source_patches[patch_index],
            source_normals[patch_index] if source_normals is not None else None,
            target_patches[patch_index],
            target_normals[patch_index] if target_normals is not None else None,
            max_distance_mm=EVALUATION_MAX_DISTANCE_MM,
            normal_angle_deg=EVALUATION_NORMAL_ANGLE_DEG,
            reciprocal_tolerance_mm=EVALUATION_RECIPROCAL_TOLERANCE_MM,
            keep_ratio=EVALUATION_KEEP_RATIO,
        )
        if result is None:
            details.append({
                "index": patch_index,
                "valid": False,
                "error": 0.0,
                "coverage": 0.0,
                "p95": 0.0,
                "normal_median": 90.0,
                "count": 0,
            })
            continue
        _matched, target_indices, distances, selected = result
        selected_distances = np.asarray(distances[selected], dtype=np.float64)
        if len(selected_distances) < PATCH_MIN_CORRESPONDENCES:
            details.append({
                "index": patch_index,
                "valid": False,
                "error": 0.0,
                "coverage": 0.0,
                "p95": 0.0,
                "normal_median": 90.0,
                "count": int(len(selected_distances)),
            })
            continue

        error = float(np.sqrt(np.mean(np.square(selected_distances))))
        coverage = float(
            len(selected_distances)
            / max(min(len(source_patches[patch_index]), len(target_patches[patch_index])), 1)
            * 100.0
        )
        p95 = float(np.percentile(selected_distances, 95.0))
        normal_median = 0.0
        if (
            source_normals is not None
            and target_normals is not None
            and source_normals[patch_index] is not None
            and target_normals[patch_index] is not None
        ):
            source_selected_normals = np.asarray(source_normals[patch_index], dtype=np.float64)[selected]
            target_selected_normals = np.asarray(target_normals[patch_index], dtype=np.float64)[target_indices[selected]]
            dots = np.clip(np.abs(np.sum(source_selected_normals * target_selected_normals, axis=1)), 0.0, 1.0)
            angles = np.degrees(np.arccos(dots))
            normal_median = float(np.median(angles)) if len(angles) else 0.0

        valid_pairs += 1
        patch_errors.append(error)
        patch_coverages.append(coverage)
        all_distances.append(selected_distances)
        details.append({
            "index": patch_index,
            "valid": True,
            "error": error,
            "coverage": coverage,
            "p95": p95,
            "normal_median": normal_median,
            "count": int(len(selected_distances)),
        })

    while len(details) < 3:
        details.append({
            "index": len(details),
            "valid": False,
            "error": 0.0,
            "coverage": 0.0,
            "p95": 0.0,
            "normal_median": 90.0,
            "count": 0,
        })
    if valid_pairs == 0 or not patch_errors:
        return 0.0, 0.0, 0.0, 0, details
    combined = np.concatenate(all_distances) if all_distances else np.empty(0, dtype=np.float64)
    p95 = float(np.percentile(combined, 95.0)) if len(combined) else 0.0
    return float(np.mean(patch_errors)), float(np.mean(patch_coverages)), p95, int(valid_pairs), details


def _evaluate_common_patch_pairs(
    source_patches,
    source_normals,
    target_patches,
    target_normals,
) -> tuple[float, float, float, int]:
    error, coverage, p95, valid_pairs, _details = _evaluate_common_patch_pairs_detailed(
        source_patches,
        source_normals,
        target_patches,
        target_normals,
    )
    return error, coverage, p95, valid_pairs


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


def _evaluate_patch_pairs(source_patches, target_patches) -> tuple[float, float]:
    """Legacy compatibility wrapper; new alignment uses reciprocal evaluation."""
    empty_source_normals = [None for _ in source_patches]
    empty_target_normals = [None for _ in target_patches]
    error, overlap, _p95, _pairs = _evaluate_common_patch_pairs(
        source_patches, empty_source_normals, target_patches, empty_target_normals
    )
    return error, overlap


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
            f"Las {label or 'tres zonas'} están demasiado juntas. Usa anterior, posterior derecha y posterior izquierda.",
        )
    if normalized_area < MIN_NORMALIZED_TRIANGLE_AREA:
        return False, _t(
            props,
            f"The {label or 'three zones'} are almost aligned. Move one zone laterally.",
            f"Las {label or 'tres zonas'} están casi alineadas. Desplaza lateralmente una zona.",
        )
    return True, ""


def _validate_landmark_geometry(source_points: np.ndarray, target_points: np.ndarray, props=None) -> tuple[bool, str]:
    labels = ((_t(props, "scan", "escaneado"), source_points), ("DICOM", target_points))
    for label, points in labels:
        span, normalized_area = _triangle_metrics(points)
        if span < MIN_LANDMARK_SPAN_MM:
            return False, _t(props, f"The {label} points are too close. Spread them across the arch.", f"Los puntos del {label} están demasiado juntos. Distribúyelos por la arcada.")
        if normalized_area < MIN_NORMALIZED_TRIANGLE_AREA:
            return False, _t(props, f"The {label} points are almost collinear. Move one laterally.", f"Los puntos del {label} están casi alineados. Separa lateralmente uno de ellos.")

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
            "Los pares son aproximados; el refinado global de mallas los corregirá.",
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
                f"Se importó {source.name}. Selecciona cualquier malla de referencia fija antes de alinear.",
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
                f"Móvil: {props.icp_source_obj.name} | Referencia: {props.icp_target_obj.name}")
        return {'FINISHED'}


class DICP_OT_UseSelection(Operator):
    bl_idname = "dicp.use_selection"
    bl_label = "Usar 2 seleccionados"
    bl_description = "El objeto activo será la referencia fija; el otro será el objeto móvil"
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
                f"IOS · {zone} · click the facial/lingual wall · Backspace undo · Esc cancel",
                f"IOS · {zone} · pulsa sobre la pared vestibular/lingual · Retroceso deshacer · Esc cancelar",
            ))
        else:
            index = min(props.target_point_count, 2)
            zone = _zone_label(props, index)
            context.workspace.status_text_set(_t(
                props,
                f"CBCT COMPOSITE · same {zone} zone · click a tooth · Backspace undo · Esc cancel",
                f"CBCT COMPUESTO · misma zona {zone} · pulsa sobre un diente · Retroceso deshacer · Esc cancelar",
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

        self._area = context.area
        self._space = context.space_data
        self._region = next((region for region in context.area.regions if region.type == 'WINDOW'), None)
        self._rv3d = self._space.region_3d
        if self._region is None or self._rv3d is None:
            _report(self, {'ERROR'}, props, "No valid 3D region was found.", "No se encontró una región 3D válida.")
            return {'CANCELLED'}

        self._source = props.icp_source_obj
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

        if event.type == 'ESC' and event.value == 'PRESS':
            return self._cancel(context)

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}

        if event.type in {'BACK_SPACE', 'DEL', 'RIGHTMOUSE'} and event.value == 'PRESS':
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


class DICP_OT_RunAlignment(Operator):
    bl_idname = "dicp.run_alignment"
    bl_label = "Alinear modelos"
    bl_description = "Occlusal/incisal dental auto-registration with a three-zone fallback"
    bl_options = {'REGISTER', 'UNDO'}

    automatic: BoolProperty(
        name="Automatic", default=False, options={'SKIP_SAVE'},
        description="Plan A: global dental registration without manual landmarks",
    )

    _timer = None
    _source = None
    _target = None
    _props = None
    _matrix_before = None
    _source_patches_full = None
    _source_patch_normals_full = None
    _target_patches_full = None
    _target_patch_normals_full = None
    _total_icp = None
    _stage_index = 0
    _iteration = 0
    _stage_source_patches = None
    _stage_source_normals = None
    _stage_target_patches = None
    _stage_target_normals = None
    _nearest_indices = None
    _previous_error = None
    _last_error = None
    _stage_transform = None
    _completed_iterations = 0
    _total_iterations = sum(scale[4] for scale in ICP_SCALES)
    _preparing = False
    _prep_step = 0
    _source_graph = None
    _target_graph = None
    _aligned_source_seeds = None
    _target_seeds = None
    _source_vertex_total = 0
    _target_vertex_total = 0
    _robust_active = False
    _robust_iteration = 0
    _robust_source_patches = None
    _robust_source_normals = None
    _robust_target_patches = None
    _robust_target_normals = None
    _robust_transform = None
    _robust_previous_error = None
    _patch_weights = None
    _patch_quality = None
    _global_source_base = None
    _global_source_normals_base = None
    _global_target_points = None
    _global_target_normals = None
    _global_source_points = None
    _global_source_normals = None
    _global_transform = None
    _global_previous_error = None
    _global_local_guard_error = None
    _global_iteration = 0
    _global_active = False
    _automatic_mode = False
    _auto_global_stats = None

    def _status(self, context, english: str, spanish: str):
        self._props.status_message = _t(self._props, english, spanish)
        context.workspace.status_text_set(self._props.status_message)
        try:
            context.window_manager.progress_update(int(self._props.alignment_progress * 100.0))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _remove_timer(self, context):
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            self._timer = None
        try:
            context.window_manager.progress_end()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.workspace.status_text_set(None)

    def _rollback(self, context, message: str):
        if self._source is not None and self._matrix_before is not None:
            self._source.matrix_world = self._matrix_before
            context.view_layer.update()
        self._source_graph = None
        self._target_graph = None
        self._preparing = False
        self._robust_active = False
        self._global_active = False
        self._global_source_base = None
        self._global_source_normals_base = None
        self._global_target_points = None
        self._global_target_normals = None
        if self._props is not None:
            self._props.alignment_running = False
            self._props.alignment_progress = 0.0
            self._props.status_message = _t(self._props, "Alignment cancelled", "Alineación cancelada")
        self._remove_timer(context)
        if message:
            self.report({'ERROR'}, message)
        return {'CANCELLED'}

    def _preparation_tick(self, context):
        if self._prep_step == 0:
            self._status(context, "Reading scan topology", "Leyendo topología del escaneado")
            self._source_graph = _extract_world_mesh_graph(self._source)
            if self._source_graph is None:
                raise RuntimeError(_t(self._props, "The scan topology could not be read.", "No se pudo leer la topología del escaneado."))
            self._global_source_base, self._global_source_normals_base = _bounded_surface_sample(
                self._source_graph.points,
                self._source_graph.normals,
                voxel_mm=GLOBAL_VOXEL_MM,
                candidate_limit=GLOBAL_SAMPLE_CANDIDATES,
                max_points=GLOBAL_MAX_SOURCE_POINTS,
                seed=8101,
            )
            self._props.alignment_progress = 0.03
            self._prep_step = 1
            return

        if self._prep_step == 1:
            self._status(context, "Reading DICOM topology", "Leyendo topología DICOM")
            if self._automatic_mode:
                # Plan A compares the IOS only with root-safe CBCT crown shells.
                # DSG 9.6.4 includes the connected axial crown walls as well as
                # occlusal/incisal caps; roots and bone remain excluded.
                target_teeth = _alignment_target_tooth_objects(context, self._target)
                self._target_graph = _mesh_graph_from_registration_crowns(
                    target_teeth, relaxed=False)
                if self._target_graph is None:
                    # A relaxed crown band is still root-safe and is preferable
                    # to silently reintroducing complete tooth roots.
                    self._target_graph = _mesh_graph_from_registration_crowns(
                        target_teeth, relaxed=True)
                if self._target_graph is None:
                    raise RuntimeError(_t(
                        self._props,
                        "Root-safe CBCT crown references could not be built. Use the 3-zone fallback.",
                        "No se pudieron construir referencias coronales seguras del CBCT. Usa el plan B de 3 zonas.",
                    ))
            else:
                self._target_graph = _extract_world_mesh_graph(self._target)
            if self._target_graph is None:
                raise RuntimeError(_t(self._props, "The DICOM topology could not be read.", "No se pudo leer la topología DICOM."))
            self._global_target_points, self._global_target_normals = _bounded_surface_sample(
                self._target_graph.points,
                self._target_graph.normals,
                voxel_mm=GLOBAL_VOXEL_MM,
                candidate_limit=GLOBAL_SAMPLE_CANDIDATES,
                max_points=GLOBAL_MAX_TARGET_POINTS,
                seed=8201,
            )
            self._props.alignment_progress = 0.05
            self._prep_step = 2
            return

        if self._prep_step == 2:
            if self._automatic_mode:
                self._status(
                    context,
                    "Automatic dental registration · crown-shell matching",
                    "Alineación dental automática · ajustando coronas",
                )
                target_seeds, seed_method = _automatic_target_zone_seeds(
                    context, self._target, self._target_graph)
                graph_meta = dict(getattr(self._target_graph, "meta", {}) or {})
                landmark_map = dict(graph_meta.get("landmarks_by_fdi", {}) or {})
                dental_landmarks = (
                    np.asarray(list(landmark_map.values()), dtype=np.float64)
                    if len(landmark_map) >= 3 else None
                )
                correction, stats = _automatic_global_registration(
                    self._global_source_base,
                    self._global_source_normals_base,
                    self._global_target_points,
                    self._global_target_normals,
                    validation_seeds=target_seeds,
                    dental_landmarks=dental_landmarks,
                )
                self._auto_global_stats = dict(stats or {})
                if not bool(stats.get('accepted', False)):
                    reason = str(stats.get('reason', 'low_confidence'))
                    if reason == 'ambiguous':
                        raise RuntimeError(_t(
                            self._props,
                            "Automatic alignment found more than one plausible arch pose. Use the 3-zone fallback.",
                            "La alineación automática encontró más de una posición plausible. Usa el plan B de 3 zonas.",
                        ))
                    raise RuntimeError(_t(
                        self._props,
                        "Automatic alignment was not reliable enough. Use the 3-zone fallback.",
                        "La alineación automática no alcanzó confianza suficiente. Usa el plan B de 3 zonas.",
                    ))
                self._source.matrix_world = Matrix(correction.tolist()) @ self._source.matrix_world
                context.view_layer.update()
                _transform_mesh_graph_in_place(self._source_graph, correction)
                self._global_source_base = _apply_points(self._global_source_base, correction)
                self._global_source_normals_base = _apply_normals(self._global_source_normals_base, correction)
                if target_seeds is None:
                    raise RuntimeError(_t(self._props, "Could not create three automatic dental validation zones.", "No se pudieron crear tres zonas dentales automáticas de validación."))
                valid_spread, spread_message = _validate_point_spread(target_seeds, self._props)
                if not valid_spread:
                    raise RuntimeError(spread_message or _t(self._props, "Automatic dental zones are not sufficiently distributed.", "Las zonas dentales automáticas no están suficientemente distribuidas."))
                self._target_seeds = np.asarray(target_seeds, dtype=np.float64)
                projected, distances, accepted = _reanchor_source_zones_to_target(self._source_graph, self._target_seeds)
                if sum(bool(value) for value in accepted) < 3:
                    raise RuntimeError(_t(self._props, "Automatic pose found, but three distributed IOS correspondences could not be confirmed. Use 3 zones.", "Se encontró una posición automática, pero no se confirmaron tres correspondencias IOS distribuidas. Usa 3 zonas."))
                self._aligned_source_seeds = np.asarray(projected, dtype=np.float64)
                self._props.mesh_refinement_used = True
                self._props.mesh_refinement_score_before = 0.0
                self._props.mesh_refinement_score_after = float(stats.get('score', 0.0))
                self._props.mesh_refinement_coverage_before = 0.0
                self._props.mesh_refinement_coverage_after = float(stats.get('coverage', 0.0))
                self._props.mesh_reanchored_zones = 3
                self._source["dicp_auto_zone_method"] = str(seed_method)
                self._source["dicp_auto_reference_surface"] = str(graph_meta.get("reference_surface", "CORONAL_CROWN_SHELL"))
                try:
                    axis_diag = dict(graph_meta.get("axis_diagnostics", {}) or {})
                    self._source["dicp_auto_occlusal_axis_json"] = json.dumps(
                        [float(v) for v in np.asarray(graph_meta.get("occlusal_axis"), dtype=np.float64)],
                        separators=(",", ":"),
                    )
                    self._source["dicp_auto_occlusal_axis_method"] = str(axis_diag.get("method", ""))
                    self._source["dicp_auto_occlusal_axis_confidence"] = float(axis_diag.get("confidence", 0.0))
                    self._source["dicp_auto_dental_landmarks"] = int(len(landmark_map))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                self._source["dicp_auto_global_stats_json"] = json.dumps(stats, separators=(",", ":"))
            else:
                self._status(
                    context,
                    "Analysing complete mesh overlap",
                    "Analizando la superposición completa de las mallas",
                )
                correction, stats = _automatic_whole_mesh_refinement(
                    self._global_source_base,
                    self._global_source_normals_base,
                    self._global_target_points,
                    self._global_target_normals,
                )
                self._props.mesh_refinement_used = bool(stats.get('accepted', False))
                self._props.mesh_refinement_score_before = float(stats.get('score_before', 0.0))
                self._props.mesh_refinement_score_after = float(stats.get('score_after', 0.0))
                self._props.mesh_refinement_coverage_before = float(stats.get('coverage_before', 0.0))
                self._props.mesh_refinement_coverage_after = float(stats.get('coverage_after', 0.0))
                if bool(stats.get('accepted', False)):
                    self._source.matrix_world = Matrix(correction.tolist()) @ self._source.matrix_world
                    context.view_layer.update()
                    _transform_mesh_graph_in_place(self._source_graph, correction)
                    self._global_source_base = _apply_points(self._global_source_base, correction)
                    self._global_source_normals_base = _apply_normals(self._global_source_normals_base, correction)
                    self._aligned_source_seeds = _apply_points(self._aligned_source_seeds, correction)

                projected, distances, accepted = _reanchor_source_zones_to_target(
                    self._source_graph, self._target_seeds
                )
                reanchored = 0
                for zone_index, use_projected in enumerate(accepted):
                    if use_projected:
                        self._aligned_source_seeds[zone_index] = projected[zone_index]
                        reanchored += 1
                self._props.mesh_reanchored_zones = int(reanchored)
            self._props.alignment_progress = 0.09
            self._prep_step = 3
            return

        if 3 <= self._prep_step <= 5:
            patch_index = self._prep_step - 3
            self._status(
                context,
                f"Creating automatic area {patch_index + 1}/3",
                f"Creando área automática {patch_index + 1}/3",
            )
            source_patch, source_normals, _ = _extract_geodesic_patch(
                self._source_graph, self._aligned_source_seeds[patch_index]
            )
            target_patch, target_normals, _ = _extract_geodesic_patch(
                self._target_graph, self._target_seeds[patch_index]
            )
            if len(source_patch) < PATCH_MIN_VERTICES or len(target_patch) < PATCH_MIN_VERTICES:
                raise RuntimeError(_t(
                    self._props,
                    f"Area {patch_index + 1} could not grow safely. Move the pair away from an edge or artefact.",
                    f"El área {patch_index + 1} no pudo crecer de forma segura. Aleja el par de un borde o artefacto.",
                ))
            source_confidence, source_quality = _surface_patch_quality(
                source_patch, source_normals, self._aligned_source_seeds[patch_index]
            )
            target_confidence, target_quality = _surface_patch_quality(
                target_patch, target_normals, self._target_seeds[patch_index]
            )
            pair_confidence = math.sqrt(max(source_confidence, 0.0) * max(target_confidence, 0.0))
            if pair_confidence < PATCH_MIN_CONFIDENCE:
                zone = _zone_label(self._props, patch_index)
                if self._automatic_mode:
                    raise RuntimeError(_t(
                        self._props,
                        f"Automatic {zone} validation is not reliable enough. Use the 3-zone fallback.",
                        f"La validación automática de {zone} no es suficientemente fiable. Usa el plan B de 3 zonas.",
                    ))
                raise RuntimeError(_t(
                    self._props,
                    f"The {zone} zone has insufficient reliable surface. Move the click onto a broader facial/lingual wall.",
                    f"La zona {zone} no tiene superficie fiable suficiente. Mueve el clic a una pared vestibular/lingual más amplia.",
                ))
            pair_weight = float(np.clip(
                PATCH_WEIGHT_MIN + pair_confidence * (PATCH_WEIGHT_MAX - PATCH_WEIGHT_MIN),
                PATCH_WEIGHT_MIN,
                PATCH_WEIGHT_MAX,
            ))
            self._patch_weights.append(pair_weight)
            self._patch_quality.append({
                "source": source_quality,
                "target": target_quality,
                "confidence": float(pair_confidence),
                "weight": pair_weight,
            })

            self._source_patches_full.append(source_patch)
            self._source_patch_normals_full.append(source_normals)
            self._target_patches_full.append(target_patch)
            self._target_patch_normals_full.append(target_normals)
            self._source_vertex_total += len(source_patch)
            self._target_vertex_total += len(target_patch)
            self._props.alignment_progress = 0.10 + 0.015 * (patch_index + 1)
            self._prep_step += 1
            return

        self._props.source_patch_vertices = int(self._source_vertex_total)
        self._props.target_patch_vertices = int(self._target_vertex_total)

        # The user's clicks only initialise the alignment. Patch centroids and
        # patch confidence provide a second weighted Kabsch correction before
        # any ICP iteration, reducing sensitivity to where inside a broad wall
        # the user clicked.
        source_centres = np.asarray([patch.mean(axis=0) for patch in self._source_patches_full], dtype=np.float64)
        target_centres = np.asarray([patch.mean(axis=0) for patch in self._target_patches_full], dtype=np.float64)
        patch_weights = np.asarray(self._patch_weights, dtype=np.float64)
        patch_correction = _weighted_best_fit_huber(
            source_centres, target_centres, patch_weights,
            delta_mm=0.75, irls_iterations=3,
        )
        source_centre = source_centres.mean(axis=0)
        moved_centre = _apply_points(source_centre.reshape(1, 3), patch_correction)[0]
        correction_translation = float(np.linalg.norm(moved_centre - source_centre))
        correction_rotation = _rotation_degrees(patch_correction)
        if (
            correction_translation <= PATCH_COARSE_MAX_TRANSLATION_MM
            and correction_rotation <= PATCH_COARSE_MAX_ROTATION_DEG
        ):
            for patch_index in range(3):
                self._source_patches_full[patch_index] = _apply_points(
                    self._source_patches_full[patch_index], patch_correction
                )
                self._source_patch_normals_full[patch_index] = _apply_normals(
                    self._source_patch_normals_full[patch_index], patch_correction
                )
            self._total_icp = patch_correction @ self._total_icp

        self._source_graph = None
        self._target_graph = None
        self._preparing = False
        self._prepare_stage(context)

    def _prepare_stage(self, context):
        if self._stage_index >= len(ICP_SCALES):
            return False
        label, voxel, max_source, max_target, iterations, max_distance, keep_ratio, normal_angle, use_normals, tolerance = ICP_SCALES[self._stage_index]

        self._stage_source_patches = []
        self._stage_source_normals = []
        self._stage_target_patches = []
        self._stage_target_normals = []
        self._nearest_indices = []

        for patch_index in range(3):
            source_points, source_normals = _voxel_downsample(
                self._source_patches_full[patch_index],
                self._source_patch_normals_full[patch_index],
                voxel,
                max_source,
                1000 + self._stage_index * 10 + patch_index,
            )
            target_points, target_normals = _voxel_downsample(
                self._target_patches_full[patch_index],
                self._target_patch_normals_full[patch_index],
                voxel,
                max_target,
                2000 + self._stage_index * 10 + patch_index,
            )
            if source_points is None or target_points is None or len(source_points) < PATCH_MIN_CORRESPONDENCES or len(target_points) < PATCH_MIN_CORRESPONDENCES:
                raise RuntimeError(_t(
                    self._props,
                    f"Automatic area {patch_index + 1} is too small. Place that point on a broader dental surface.",
                    f"El área automática {patch_index + 1} es demasiado pequeña. Coloca ese punto sobre una superficie dental más amplia.",
                ))
            self._stage_source_patches.append(source_points)
            self._stage_source_normals.append(source_normals)
            self._stage_target_patches.append(target_points)
            self._stage_target_normals.append(target_normals)
            self._nearest_indices.append(_NearestIndex(target_points))

        self._iteration = 0
        self._previous_error = None
        self._last_error = None
        self._stage_transform = np.eye(4, dtype=np.float64)
        self._status(
            context,
            f"Refining 3 automatic areas · {label.lower()} scale",
            f"Refinando 3 áreas automáticas · escala {('gruesa' if label == 'Coarse' else 'media' if label == 'Medium' else 'fina')}",
        )
        return True

    def _match_patch_pair(
        self,
        patch_index: int,
        source_points: np.ndarray,
        source_normals: np.ndarray,
        target_normals: np.ndarray,
        max_distance: float,
        normal_angle: float,
        use_normals: bool,
        keep_ratio: float,
    ):
        matched, target_indices, distances = self._nearest_indices[patch_index].query(source_points)

        # Coarse landmarks are only approximate. Try the clinical distance first,
        # then relax it before declaring the expanded area unusable.
        distance_factors = (1.0, 1.75, 2.75)
        normal_angles = (normal_angle, min(90.0, normal_angle + 14.0), 90.0)
        for factor, angle_limit in zip(distance_factors, normal_angles):
            valid = distances <= (max_distance * factor)
            if use_normals and source_normals is not None and target_normals is not None and angle_limit < 90.0:
                dots = np.clip(
                    np.sum(source_normals * target_normals[target_indices], axis=1),
                    -1.0,
                    1.0,
                )
                valid &= np.degrees(np.arccos(np.abs(dots))) <= angle_limit

            selected = _trimmed_correspondences(distances, valid, keep_ratio)
            if selected is not None and len(selected) >= PATCH_MIN_CORRESPONDENCES:
                return matched, distances, selected
        return None

    def _one_iteration(self):
        label, voxel, max_source, max_target, iterations, max_distance, keep_ratio, normal_angle, use_normals, tolerance = ICP_SCALES[self._stage_index]
        pair_results = []

        for patch_index in range(3):
            source_points = self._stage_source_patches[patch_index]
            source_normals = self._stage_source_normals[patch_index]
            target_normals = self._stage_target_normals[patch_index]
            result = self._match_patch_pair(
                patch_index,
                source_points,
                source_normals,
                target_normals,
                max_distance,
                normal_angle,
                use_normals,
                keep_ratio,
            )
            if result is None:
                continue
            matched, distances, selected = result
            pair_results.append((patch_index, source_points, matched, distances, selected))

        # A single local area can fit but may rotate around its own surface. Two
        # expanded common areas are enough because the three rough landmarks have
        # already established the global orientation.
        if len(pair_results) < PATCH_MIN_ACTIVE_PAIRS:
            return "NO_MATCH"

        # Every active patch contributes the same correspondence count. This
        # prevents one dense molar area from dominating the other dental areas.
        balanced_count = min(len(result[4]) for result in pair_results)
        if balanced_count < PATCH_MIN_CORRESPONDENCES:
            return "NO_MATCH"

        source_blocks = []
        target_blocks = []
        weight_blocks = []
        selected_distances = []
        for patch_index, source_points, matched, distances, selected in pair_results:
            if len(selected) > balanced_count:
                local = np.argpartition(distances[selected], balanced_count - 1)[:balanced_count]
                selected = selected[local]
            source_blocks.append(source_points[selected])
            target_blocks.append(matched[selected])
            pair_weight = float(self._patch_weights[patch_index]) if self._patch_weights else 1.0
            weight_blocks.append(np.full(len(selected), pair_weight, dtype=np.float64))
            selected_distances.append(distances[selected])

        source_combined = np.concatenate(source_blocks, axis=0)
        target_combined = np.concatenate(target_blocks, axis=0)
        correspondence_weights = np.concatenate(weight_blocks, axis=0)
        incremental = _weighted_best_fit_huber(
            source_combined, target_combined, correspondence_weights,
            delta_mm=0.30, irls_iterations=3,
        )

        for patch_index in range(3):
            self._stage_source_patches[patch_index] = _apply_points(
                self._stage_source_patches[patch_index], incremental
            )
            if self._stage_source_normals[patch_index] is not None:
                self._stage_source_normals[patch_index] = _apply_normals(
                    self._stage_source_normals[patch_index], incremental
                )
        self._stage_transform = incremental @ self._stage_transform

        error = float(np.mean(np.concatenate(selected_distances)))
        translation = float(np.linalg.norm(incremental[:3, 3]))
        rotation = _rotation_degrees(incremental)
        converged = (
            (self._previous_error is not None and abs(self._previous_error - error) < tolerance)
            or (translation < tolerance and rotation < tolerance * 10.0)
        )
        self._previous_error = error
        self._last_error = error
        self._iteration += 1
        self._completed_iterations += 1
        self._props.alignment_progress = min(
            0.98,
            0.12 + 0.86 * self._completed_iterations / max(self._total_iterations, 1),
        )
        if converged or self._iteration >= iterations:
            return "STAGE_DONE"
        return "CONTINUE"

    def _commit_stage(self):
        if self._stage_transform is None:
            return
        for patch_index in range(3):
            self._source_patches_full[patch_index] = _apply_points(
                self._source_patches_full[patch_index], self._stage_transform
            )
            if self._source_patch_normals_full[patch_index] is not None:
                self._source_patch_normals_full[patch_index] = _apply_normals(
                    self._source_patch_normals_full[patch_index], self._stage_transform
                )
        self._total_icp = self._stage_transform @ self._total_icp
        self._stage_transform = np.eye(4, dtype=np.float64)

    def _prepare_robust_refinement(self, context) -> bool:
        """Prepare a hidden, conservative refinement around the three areas."""
        self._robust_source_patches = []
        self._robust_source_normals = []
        self._robust_target_patches = []
        self._robust_target_normals = []
        for patch_index in range(3):
            source_points, source_normals = _voxel_downsample(
                self._source_patches_full[patch_index],
                self._source_patch_normals_full[patch_index],
                ROBUST_VOXEL_MM,
                ROBUST_MAX_SOURCE_PER_PATCH,
                7100 + patch_index,
            )
            target_points, target_normals = _voxel_downsample(
                self._target_patches_full[patch_index],
                self._target_patch_normals_full[patch_index],
                ROBUST_VOXEL_MM,
                ROBUST_MAX_TARGET_PER_PATCH,
                7200 + patch_index,
            )
            self._robust_source_patches.append(source_points)
            self._robust_source_normals.append(source_normals)
            self._robust_target_patches.append(target_points)
            self._robust_target_normals.append(target_normals)

        error, _coverage, _p95, valid_pairs = _evaluate_common_patch_pairs(
            self._robust_source_patches,
            self._robust_source_normals,
            self._robust_target_patches,
            self._robust_target_normals,
        )
        if valid_pairs < 3 or error <= 0.0:
            self._robust_active = False
            return False
        self._robust_previous_error = float(error)
        self._robust_transform = np.eye(4, dtype=np.float64)
        self._robust_iteration = 0
        self._robust_active = True
        self._status(
            context,
            "Final robust refinement on common areas",
            "Refinado robusto final en áreas comunes",
        )
        return True

    def _robust_one_iteration(self):
        if not self._robust_active:
            return "ROBUST_DONE"
        progress_ratio = self._robust_iteration / max(ROBUST_REFINEMENT_ITERATIONS - 1, 1)
        maximum_distance = ROBUST_START_DISTANCE_MM + (ROBUST_END_DISTANCE_MM - ROBUST_START_DISTANCE_MM) * progress_ratio
        pair_results = []
        for patch_index in range(3):
            result = _reciprocal_correspondences(
                self._robust_source_patches[patch_index],
                self._robust_source_normals[patch_index],
                self._robust_target_patches[patch_index],
                self._robust_target_normals[patch_index],
                max_distance_mm=maximum_distance,
                normal_angle_deg=ROBUST_NORMAL_ANGLE_DEG,
                reciprocal_tolerance_mm=ROBUST_RECIPROCAL_TOLERANCE_MM,
                keep_ratio=0.90,
            )
            if result is None:
                return "ROBUST_DONE"
            matched, target_indices, distances, selected = result
            pair_results.append((patch_index, matched, target_indices, distances, selected))

        if len(pair_results) != 3:
            return "ROBUST_DONE"
        balanced_count = min(len(result[4]) for result in pair_results)
        if balanced_count < PATCH_MIN_CORRESPONDENCES:
            return "ROBUST_DONE"

        source_blocks = []
        target_blocks = []
        normal_blocks = []
        weight_blocks = []
        for patch_index, matched, target_indices, distances, selected in pair_results:
            if len(selected) > balanced_count:
                local = np.argpartition(distances[selected], balanced_count - 1)[:balanced_count]
                selected = selected[local]
            source_blocks.append(self._robust_source_patches[patch_index][selected])
            target_blocks.append(matched[selected])
            normal_blocks.append(self._robust_target_normals[patch_index][target_indices[selected]])
            pair_weight = float(self._patch_weights[patch_index]) if self._patch_weights else 1.0
            weight_blocks.append(np.full(len(selected), pair_weight, dtype=np.float64))

        source_combined = np.concatenate(source_blocks, axis=0)
        target_combined = np.concatenate(target_blocks, axis=0)
        target_normals = np.concatenate(normal_blocks, axis=0)
        base_weights = np.concatenate(weight_blocks, axis=0)
        incremental = _point_to_plane_huber_transform(
            source_combined,
            target_combined,
            target_normals,
            base_weights=base_weights,
        )
        translation = float(np.linalg.norm(incremental[:3, 3]))
        rotation = _rotation_degrees(incremental)
        if translation <= 1.0e-8 and rotation <= 1.0e-8:
            return "ROBUST_DONE"

        candidate_patches = [_apply_points(points, incremental) for points in self._robust_source_patches]
        candidate_normals = [
            None if normals is None else _apply_normals(normals, incremental)
            for normals in self._robust_source_normals
        ]
        candidate_error, _coverage, _p95, valid_pairs = _evaluate_common_patch_pairs(
            candidate_patches,
            candidate_normals,
            self._robust_target_patches,
            self._robust_target_normals,
        )
        if valid_pairs < 3 or candidate_error <= 0.0:
            return "ROBUST_DONE"

        improvement = float(self._robust_previous_error - candidate_error)
        if improvement < ROBUST_MIN_IMPROVEMENT_MM:
            return "ROBUST_DONE"

        self._robust_source_patches = candidate_patches
        self._robust_source_normals = candidate_normals
        self._robust_transform = incremental @ self._robust_transform
        self._robust_previous_error = float(candidate_error)
        self._robust_iteration += 1
        self._completed_iterations += 1
        self._props.alignment_progress = min(
            0.99,
            0.12 + 0.86 * self._completed_iterations / max(self._total_iterations, 1),
        )
        if self._robust_iteration >= ROBUST_REFINEMENT_ITERATIONS or improvement < ROBUST_STOP_IMPROVEMENT_MM:
            return "ROBUST_DONE"
        return "CONTINUE"

    def _commit_robust_refinement(self):
        if self._robust_transform is None:
            self._robust_active = False
            return
        if not np.allclose(self._robust_transform, np.eye(4), atol=1.0e-12):
            for patch_index in range(3):
                self._source_patches_full[patch_index] = _apply_points(
                    self._source_patches_full[patch_index], self._robust_transform
                )
                if self._source_patch_normals_full[patch_index] is not None:
                    self._source_patch_normals_full[patch_index] = _apply_normals(
                        self._source_patch_normals_full[patch_index], self._robust_transform
                    )
            self._total_icp = self._robust_transform @ self._total_icp
        self._robust_active = False

    def _global_balanced_selection(self, matched, distances, selected):
        """Balance reciprocal matches around anterior/right/left sectors."""
        if selected is None or len(selected) == 0 or self._target_seeds is None:
            return None
        selected = np.asarray(selected, dtype=np.int64)
        matched_selected = np.asarray(matched, dtype=np.float64)[selected]
        seeds = np.asarray(self._target_seeds, dtype=np.float64)
        if len(seeds) != 3:
            return None
        squared = np.sum((matched_selected[:, None, :] - seeds[None, :, :]) ** 2, axis=2)
        zone_ids = np.argmin(squared, axis=1)
        zone_local_indices = [np.flatnonzero(zone_ids == zone) for zone in range(3)]
        if any(len(indices) < GLOBAL_MIN_PER_ZONE for indices in zone_local_indices):
            return None
        balanced_count = min(GLOBAL_MAX_PER_ZONE, min(len(indices) for indices in zone_local_indices))
        balanced = []
        for local_indices in zone_local_indices:
            original_indices = selected[local_indices]
            local_distances = distances[original_indices]
            if len(original_indices) > balanced_count:
                keep = np.argpartition(local_distances, balanced_count - 1)[:balanced_count]
                original_indices = original_indices[keep]
            balanced.append(original_indices)
        return np.concatenate(balanced, axis=0)

    def _global_correspondence_state(self, source_points, source_normals, maximum_distance):
        result = _reciprocal_correspondences(
            source_points,
            source_normals,
            self._global_target_points,
            self._global_target_normals,
            max_distance_mm=maximum_distance,
            normal_angle_deg=GLOBAL_NORMAL_ANGLE_DEG,
            reciprocal_tolerance_mm=GLOBAL_RECIPROCAL_TOLERANCE_MM,
            keep_ratio=GLOBAL_KEEP_RATIO,
        )
        if result is None:
            return None
        matched, target_indices, distances, selected = result
        selected = self._global_balanced_selection(matched, distances, selected)
        if selected is None or len(selected) < GLOBAL_MIN_PER_ZONE * 3:
            return None
        return matched, target_indices, distances, selected

    def _prepare_global_refinement(self, context) -> bool:
        """Prepare the final full-surface reciprocal pass with local-zone guard."""
        if (
            self._global_source_base is None
            or self._global_target_points is None
            or self._global_source_normals_base is None
            or self._global_target_normals is None
            or len(self._global_source_base) < GLOBAL_MIN_PER_ZONE * 3
            or len(self._global_target_points) < GLOBAL_MIN_PER_ZONE * 3
        ):
            self._global_active = False
            return False
        self._global_source_points = _apply_points(self._global_source_base, self._total_icp)
        self._global_source_normals = _apply_normals(self._global_source_normals_base, self._total_icp)
        self._global_transform = np.eye(4, dtype=np.float64)
        self._global_iteration = 0
        initial = self._global_correspondence_state(
            self._global_source_points,
            self._global_source_normals,
            GLOBAL_START_DISTANCE_MM,
        )
        if initial is None:
            self._global_active = False
            return False
        _matched, _target_indices, distances, selected = initial
        self._global_previous_error = float(np.sqrt(np.mean(np.square(distances[selected]))))
        local_error, _coverage, _p95, valid_pairs = _evaluate_common_patch_pairs(
            self._source_patches_full,
            self._source_patch_normals_full,
            self._target_patches_full,
            self._target_patch_normals_full,
        )
        if valid_pairs < 3 or local_error <= 0.0:
            self._global_active = False
            return False
        self._global_local_guard_error = float(local_error)
        self._global_active = True
        self._status(
            context,
            "Final reciprocal surface check",
            "Comprobación recíproca final de superficies",
        )
        return True

    def _global_one_iteration(self):
        if not self._global_active:
            return "GLOBAL_DONE"
        progress_ratio = self._global_iteration / max(GLOBAL_REFINEMENT_ITERATIONS - 1, 1)
        maximum_distance = GLOBAL_START_DISTANCE_MM + (
            GLOBAL_END_DISTANCE_MM - GLOBAL_START_DISTANCE_MM
        ) * progress_ratio
        state = self._global_correspondence_state(
            self._global_source_points,
            self._global_source_normals,
            maximum_distance,
        )
        if state is None:
            return "GLOBAL_DONE"
        matched, target_indices, distances, selected = state
        target_normals = self._global_target_normals[target_indices[selected]]
        incremental = _point_to_plane_huber_transform(
            self._global_source_points[selected],
            matched[selected],
            target_normals,
            huber_delta_mm=GLOBAL_HUBER_DELTA_MM,
            max_translation_mm=GLOBAL_MAX_TRANSLATION_MM,
            max_rotation_deg=GLOBAL_MAX_ROTATION_DEG,
        )
        translation = float(np.linalg.norm(incremental[:3, 3]))
        rotation = _rotation_degrees(incremental)
        if translation <= 1.0e-8 and rotation <= 1.0e-8:
            return "GLOBAL_DONE"

        candidate_points = _apply_points(self._global_source_points, incremental)
        candidate_normals = _apply_normals(self._global_source_normals, incremental)
        candidate_state = self._global_correspondence_state(
            candidate_points,
            candidate_normals,
            maximum_distance,
        )
        if candidate_state is None:
            return "GLOBAL_DONE"
        _candidate_matched, _candidate_target_indices, candidate_distances, candidate_selected = candidate_state
        candidate_error = float(np.sqrt(np.mean(np.square(candidate_distances[candidate_selected]))))
        improvement = float(self._global_previous_error - candidate_error)
        if improvement < GLOBAL_MIN_IMPROVEMENT_MM:
            return "GLOBAL_DONE"

        candidate_patches = [_apply_points(points, incremental) for points in self._source_patches_full]
        candidate_patch_normals = [
            _apply_normals(normals, incremental) if normals is not None else None
            for normals in self._source_patch_normals_full
        ]
        local_error, _coverage, _p95, valid_pairs = _evaluate_common_patch_pairs(
            candidate_patches,
            candidate_patch_normals,
            self._target_patches_full,
            self._target_patch_normals_full,
        )
        if (
            valid_pairs < 3
            or local_error <= 0.0
            or local_error > self._global_local_guard_error + GLOBAL_LOCAL_GUARD_TOLERANCE_MM
        ):
            return "GLOBAL_DONE"

        self._global_source_points = candidate_points
        self._global_source_normals = candidate_normals
        self._source_patches_full = candidate_patches
        self._source_patch_normals_full = candidate_patch_normals
        self._global_transform = incremental @ self._global_transform
        self._global_previous_error = candidate_error
        self._global_local_guard_error = float(local_error)
        self._global_iteration += 1
        self._completed_iterations += 1
        self._props.alignment_progress = min(
            0.995,
            0.12 + 0.86 * self._completed_iterations / max(self._total_iterations, 1),
        )
        if self._global_iteration >= GLOBAL_REFINEMENT_ITERATIONS:
            return "GLOBAL_DONE"
        return "CONTINUE"

    def _commit_global_refinement(self):
        if self._global_transform is not None and not np.allclose(
            self._global_transform, np.eye(4), atol=1.0e-12
        ):
            self._total_icp = self._global_transform @ self._total_icp
        self._global_active = False

    def _finish_success(self, context):
        self._source.matrix_world = Matrix(self._total_icp.tolist()) @ self._source.matrix_world
        context.view_layer.update()

        evaluation_source = []
        evaluation_source_normals = []
        evaluation_target = []
        evaluation_target_normals = []
        for patch_index in range(3):
            source_points, source_normals = _voxel_downsample(
                self._source_patches_full[patch_index],
                self._source_patch_normals_full[patch_index],
                0.20,
                800,
                5000 + patch_index,
            )
            target_points, target_normals = _voxel_downsample(
                self._target_patches_full[patch_index],
                self._target_patch_normals_full[patch_index],
                0.20,
                1000,
                6000 + patch_index,
            )
            evaluation_source.append(source_points)
            evaluation_source_normals.append(source_normals)
            evaluation_target.append(target_points)
            evaluation_target_normals.append(target_normals)

        (
            self._props.icp_error,
            self._props.icp_overlap,
            self._props.icp_p95,
            self._props.icp_valid_pairs,
            zone_details,
        ) = _evaluate_common_patch_pairs_detailed(
            evaluation_source,
            evaluation_source_normals,
            evaluation_target,
            evaluation_target_normals,
        )
        valid_zone_details = [detail for detail in zone_details if detail.get("valid")]
        self._props.icp_max_patch_error = max(
            (float(detail["error"]) for detail in valid_zone_details),
            default=0.0,
        )
        self._props.icp_min_patch_coverage = min(
            (float(detail["coverage"]) for detail in valid_zone_details),
            default=0.0,
        )
        self._props.icp_max_patch_normal_angle = max(
            (float(detail["normal_median"]) for detail in valid_zone_details),
            default=90.0,
        )
        serializable_details = []
        for detail in zone_details:
            item = dict(detail)
            item["zone"] = ROBUST_ZONE_KEYS[int(detail.get("index", 0))]
            serializable_details.append(item)
        self._props.icp_zone_summary = json.dumps(serializable_details, separators=(",", ":"))

        approved = (
            self._props.icp_valid_pairs == 3
            and 0.0 < float(self._props.icp_error) <= MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM
            and 0.0 < float(self._props.icp_p95) <= MAX_ACCEPTABLE_P95_MM
            and 0.0 < float(self._props.icp_max_patch_error) <= MAX_ACCEPTABLE_PATCH_ERROR_MM
            and float(self._props.icp_min_patch_coverage) >= MIN_ACCEPTABLE_PATCH_COVERAGE_PERCENT
            and float(self._props.icp_max_patch_normal_angle) <= MAX_ACCEPTABLE_PATCH_NORMAL_MEDIAN_DEG
        )
        self._props.alignment_quality_approved = bool(approved)
        self._props.aligned = True
        self._props.current_step = STEP_DONE
        self._props.alignment_running = False
        self._props.alignment_progress = 1.0
        self._props.status_message = _t(
            self._props,
            "Alignment accepted" if approved else "Repeat alignment: robust error above 0.50 mm or insufficient common areas",
            "Alineación aceptada" if approved else "Repite el alineamiento: error robusto superior a 0,50 mm o áreas comunes insuficientes",
        )

        _set_role(self._source, ROLE_IOS_ALIGNED)
        self._source["dental_suite_aligned"] = True
        self._source["dental_suite_canonical_name"] = "Dental_IOS_Aligned"
        self._source.name = "Dental_IOS_Aligned"
        self._source["dicp_alignment_method"] = (
            "AUTO_OCCLUSAL_INCISAL_DENTAL_LANDMARKS_TRIMMED_ICP_GEOMATCH_VALIDATED"
            if self._automatic_mode else
            "WHOLE_MESH_MULTI_HYPOTHESIS_3_DENTAL_ZONES_LOCAL_ICP_GLOBAL_RECIPROCAL_HUBER"
        )
        self._source["dicp_alignment_mode"] = "AUTO" if self._automatic_mode else "THREE_ZONE"
        self._source["dicp_mesh_refinement_used"] = bool(self._props.mesh_refinement_used)
        self._source["dicp_mesh_refinement_score_before"] = float(self._props.mesh_refinement_score_before)
        self._source["dicp_mesh_refinement_score_after"] = float(self._props.mesh_refinement_score_after)
        self._source["dicp_mesh_refinement_coverage_before"] = float(self._props.mesh_refinement_coverage_before)
        self._source["dicp_mesh_refinement_coverage_after"] = float(self._props.mesh_refinement_coverage_after)
        self._source["dicp_mesh_reanchored_zones"] = int(self._props.mesh_reanchored_zones)
        self._source["dicp_patch_radius_mm"] = float(PATCH_GEODESIC_RADIUS_MM)
        self._source["dicp_patch_select_more_rings"] = int(PATCH_SELECT_MORE_RINGS)
        self._source["dicp_patch_euclidean_cap_mm"] = float(PATCH_EUCLIDEAN_RADIUS_MM)
        self._target["dental_suite_alignment_reference"] = True
        self._source["dicp_target_name"] = self._target.name
        self._source["dicp_error_mm"] = float(self._props.icp_error)
        self._source["dicp_overlap_percent"] = float(self._props.icp_overlap)
        self._source["dicp_p95_mm"] = float(self._props.icp_p95)
        self._source["dicp_valid_common_areas"] = int(self._props.icp_valid_pairs)
        self._source["dicp_max_patch_error_mm"] = float(self._props.icp_max_patch_error)
        self._source["dicp_min_patch_coverage_percent"] = float(self._props.icp_min_patch_coverage)
        self._source["dicp_max_patch_normal_median_deg"] = float(self._props.icp_max_patch_normal_angle)
        self._source["dicp_zone_validation_json"] = str(self._props.icp_zone_summary)
        self._source["dicp_patch_weights"] = [float(value) for value in (self._patch_weights or [])]
        self._source["dicp_alignment_approved"] = bool(self._props.alignment_quality_approved)
        self._source["dicp_max_acceptable_error_mm"] = float(MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM)

        # Stay in Alignment for manual validation.  Do not enter DSG or hide
        # the DICOM until the user presses Siguiente / Next.
        context.scene[SUITE_STAGE_KEY] = "ALIGNMENT"
        _set_markers_hidden(True)
        _prepare_alignment_review_view(context, self._source, self._target)

        self._props.status_message = _t(
            self._props,
            "Review the superposition, then continue." if approved else ("Automatic validation was not sufficient. Use the 3-zone fallback." if self._automatic_mode else "Validation blocked. Mark the three zones again."),
            "Revisa la superposición y continúa." if approved else ("La validación automática no fue suficiente. Usa el plan B de 3 zonas." if self._automatic_mode else "Validación bloqueada. Marca de nuevo las tres zonas."),
        )
        self._remove_timer(context)
        _report(
            self, {'INFO'}, self._props,
            f"Stable alignment completed · robust error {self._props.icp_error:.3f} mm",
            f"Alineamiento estable completado · error robusto {self._props.icp_error:.3f} mm",
        )
        return {'FINISHED'}

    def _start(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        target = props.icp_target_obj
        valid, message = _validate_models(source, target, props)
        if valid:
            try:
                from . import cbct_dental_module
                if cbct_dental_module.dentition_objects(context):
                    quality = str(target.get("dental_suite_alignment_reference_quality", "") or "")
                    immediate_target = False
                    if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
                        arch = str(context.scene.get("DSG_active_arch", "MAXILLA") or "MAXILLA").upper()
                        target_key = (
                            "DSG_immediate_upper_composite"
                            if arch == "MAXILLA" else "DSG_immediate_lower_composite"
                        )
                        registered_name = str(context.scene.get(target_key, "") or "")
                        immediate_target = bool(
                            registered_name
                            and target.name == registered_name
                            and bool(target.get("DSG_immediate_arch_composite", False))
                            and str(target.get("DSG_bone_arch", "") or "").upper() == arch
                            and bool(target.get("dental_suite_alignment_reference", False))
                        )
                        if immediate_target:
                            target["dental_suite_alignment_reference_quality"] = "IMMEDIATE_ARCH_COMPOSITE"
                            target["DSG_immediate_alignment_target"] = True
                    if quality != "ALL_SEGMENTED_DUPLICATE_COMPOSITE" and not immediate_target:
                        valid = False
                        message = _t(
                            props,
                            "Segmented CBCT data exist, but the target is not the all-segmented duplicate composite.",
                            "Hay datos CBCT segmentados, pero el target no es el compuesto duplicado de todas las segmentaciones.",
                        )
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        if props.alignment_running:
            _report(self, {'WARNING'}, props, "Alignment is already running.", "El alineamiento ya está en ejecución.")
            return {'CANCELLED'}
        self._automatic_mode = bool(self.automatic)
        self._auto_global_stats = None
        if (not self._automatic_mode) and (props.source_point_count != 3 or props.target_point_count != 3):
            _report(self, {'ERROR'}, props, "Mark the three robust zones first.", "Marca primero las tres zonas robustas.")
            return {'CANCELLED'}

        original = _matrix_from_text(props.original_source_matrix)
        if original is None:
            original = source.matrix_world.copy()
            props.original_source_matrix = _matrix_to_text(original)

        self._source = source
        self._target = target
        self._props = props
        self._matrix_before = source.matrix_world.copy()
        self._total_icp = np.eye(4, dtype=np.float64)
        self._stage_index = 0
        self._completed_iterations = 0
        self._total_iterations = (
            sum(scale[4] for scale in ICP_SCALES)
            + ROBUST_REFINEMENT_ITERATIONS
            + GLOBAL_REFINEMENT_ITERATIONS
        )
        self._robust_active = False
        self._robust_iteration = 0
        self._robust_transform = np.eye(4, dtype=np.float64)
        self._robust_previous_error = None
        self._global_active = False
        self._global_iteration = 0
        self._global_transform = np.eye(4, dtype=np.float64)
        self._global_previous_error = None
        self._global_local_guard_error = None
        self._global_source_base = None
        self._global_source_normals_base = None
        self._global_target_points = None
        self._global_target_normals = None
        self._patch_weights = []
        self._patch_quality = []
        _ensure_object_mode(context)

        try:
            source.matrix_world = original
            context.view_layer.update()
            if self._automatic_mode:
                props.landmark_rmse = 0.0
                self._status(context, "Preparing automatic dental registration", "Preparando alineación dental automática")
                self._aligned_source_seeds = None
                self._target_seeds = None
            else:
                source_landmarks = _world_landmarks(source, _get_local_landmarks(props, "source"))
                target_landmarks = _world_landmarks(target, _get_local_landmarks(props, "target"))
                valid, message = _validate_landmark_geometry(source_landmarks, target_landmarks, props)
                if not valid:
                    raise ValueError(message)

                landmark_transform = _best_fit(source_landmarks, target_landmarks)
                aligned_landmarks = _apply_points(source_landmarks, landmark_transform)
                props.landmark_rmse = float(np.sqrt(np.mean(np.sum((aligned_landmarks - target_landmarks) ** 2, axis=1))))
                source.matrix_world = Matrix(landmark_transform.tolist()) @ source.matrix_world
                context.view_layer.update()
                self._status(context, "Preparing automatic areas", "Preparando áreas automáticas")
                self._aligned_source_seeds = _world_landmarks(source, _get_local_landmarks(props, "source"))
                self._target_seeds = _world_landmarks(target, _get_local_landmarks(props, "target"))
            self._source_patches_full = []
            self._source_patch_normals_full = []
            self._target_patches_full = []
            self._target_patch_normals_full = []
            self._source_vertex_total = 0
            self._target_vertex_total = 0
            self._source_graph = None
            self._target_graph = None
            self._prep_step = 0
            self._preparing = True
        except Exception as exc:
            return self._rollback(context, str(exc))

        props.alignment_running = True
        props.alignment_progress = 0.01
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
        props.mesh_refinement_used = False
        props.mesh_refinement_score_before = 0.0
        props.mesh_refinement_score_after = 0.0
        props.mesh_refinement_coverage_before = 0.0
        props.mesh_refinement_coverage_after = 0.0
        props.mesh_reanchored_zones = 0
        context.window_manager.progress_begin(0, 100)
        self._timer = context.window_manager.event_timer_add(ALIGNMENT_TIMER_SECONDS, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        # Ctrl+Z while the ICP modal owns the event loop means “revert this
        # clinical step”, not “queue a global undo behind a running timer”.
        if event.type == 'Z' and bool(getattr(event, 'ctrl', False)):
            try:
                context.scene["DSG_alignment_cancel_requested"] = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return self._rollback(context, "")
        if event.type == 'ESC':
            try:
                context.scene["DSG_alignment_cancel_requested"] = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return self._rollback(context, "")
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if bool(context.scene.get("DSG_alignment_cancel_requested", False)):
            context.scene["DSG_alignment_cancel_requested"] = False
            return self._rollback(context, "")

        try:
            if self._preparing:
                self._preparation_tick(context)
                return {'RUNNING_MODAL'}

            if self._robust_active:
                result = self._robust_one_iteration()
                self._status(
                    context,
                    f"Robust common-area refinement · {int(self._props.alignment_progress * 100)}%",
                    f"Refinado robusto de áreas comunes · {int(self._props.alignment_progress * 100)}%",
                )
                if result == "ROBUST_DONE":
                    self._commit_robust_refinement()
                    if self._prepare_global_refinement(context):
                        return {'RUNNING_MODAL'}
                    return self._finish_success(context)
                return {'RUNNING_MODAL'}

            if self._global_active:
                result = self._global_one_iteration()
                self._status(
                    context,
                    f"Reciprocal surface check · {int(self._props.alignment_progress * 100)}%",
                    f"Comprobación recíproca · {int(self._props.alignment_progress * 100)}%",
                )
                if result == "GLOBAL_DONE":
                    self._commit_global_refinement()
                    return self._finish_success(context)
                return {'RUNNING_MODAL'}

            result = self._one_iteration()
            if result == "NO_MATCH":
                if self._stage_index == 0:
                    raise RuntimeError(_t(
                        self._props,
                        "ICP could not find two usable expanded surface areas. Use the three points only to approximate the same broad dental zones, then run again.",
                        "El ICP no encontró dos áreas ampliadas utilizables. Usa los tres puntos solo para aproximar las mismas zonas dentales amplias y vuelve a ejecutar.",
                    ))
                result = "STAGE_DONE"

            label = ICP_SCALES[self._stage_index][0]
            self._status(
                context,
                f"Refining 3 areas · {label.lower()} · {int(self._props.alignment_progress * 100)}%",
                f"Refinando 3 áreas · {('grueso' if label == 'Coarse' else 'medio' if label == 'Medium' else 'fino')} · {int(self._props.alignment_progress * 100)}%",
            )

            if result == "STAGE_DONE":
                self._commit_stage()
                self._stage_index += 1
                if self._stage_index >= len(ICP_SCALES):
                    if self._prepare_robust_refinement(context):
                        return {'RUNNING_MODAL'}
                    if self._prepare_global_refinement(context):
                        return {'RUNNING_MODAL'}
                    return self._finish_success(context)
                self._prepare_stage(context)
        except Exception as exc:
            return self._rollback(context, str(exc))
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._rollback(context, "")


class DICP_OT_ReviewAlignment(Operator):
    bl_idname = "dicp.review_alignment"
    bl_label = "Revisar"
    bl_description = "Muestra juntos el IOS alineado y la referencia fija para comprobar la superposición"
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
        _report(self, {'INFO'}, props, "Alignment review ready.", "Revisión del alineamiento preparada.")
        return {'FINISHED'}


class DICP_OT_SendToDSG(Operator):
    bl_idname = "dicp.send_to_dsg"
    bl_label = "Siguiente"
    bl_description = "Accept the visual superposition review and continue to the Surgical Guide workflow"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        if source is None or not props.aligned:
            _report(self, {'ERROR'}, props, "Align the models first.", "Alinea primero los modelos.")
            return {'CANCELLED'}
        # In the immediate route, the guide must use the reviewed virtual
        # post-extraction IOS—not the pre-extraction crown scan.  The mesh
        # change remains clinician-confirmed in the core workflow.
        try:
            immediate = core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE
            selected = json.loads(str(context.scene.get("DSG_immediate_extraction_fdis_json", "[]") or "[]"))
            if immediate and selected and not bool(context.scene.get("DSG_ios_postextraction_confirmed", False)):
                retry = bool(context.scene.get("DSG_ios_postextraction_closure_retry_available", False))
                boolean_retry = bool(context.scene.get("DSG_ios_postextraction_boolean_retry_available", False))
                _report(
                    self, {'ERROR'}, props,
                    (
                        "The virtual IOS Boolean is ready, but its closure needs retrying. "
                        "Return to IOS post-extraction and confirm it again."
                        if retry else
                        "The local IOS opening is prepared, but the extraction Boolean needs retrying."
                        if boolean_retry else
                        "Create and review the virtual post-extraction IOS before continuing."
                    ),
                    (
                        "La booleana del IOS virtual está lista, pero falta reintentar su cierre. "
                        "Vuelve a IOS postextracción y confirma de nuevo."
                        if retry else
                        "El hueco local del IOS está preparado, pero falta reintentar la booleana de extracción."
                        if boolean_retry else
                        "Crea y revisa el IOS postextracción virtual antes de continuar."
                    ),
                )
                return {'CANCELLED'}
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not bool(getattr(props, "alignment_quality_approved", False)):
            _report(
                self,
                {'ERROR'},
                props,
                "The three-zone validation was not passed. Mark the zones again and repeat the alignment.",
                "No se superó la validación de las tres zonas. Márcalas de nuevo y repite el alineamiento.",
            )
            return {'CANCELLED'}
        _set_role(source, ROLE_IOS_ALIGNED)
        _disable_clinical_cbct_review_smoothing(context)
        try:
            from . import cbct_dental_module
            cbct_dental_module.clear_alignment_working_composite(
                context, restore_sources=False
            )
        except Exception as exc:
            print(f"[DSG Alignment] Composite cleanup warning: {exc}")
        context.scene[SUITE_STAGE_KEY] = "DSG"
        _isolate_aligned_ios_for_guide(context, source)
        dsg_props = getattr(context.scene, "dsg_props", None)
        if dsg_props is not None and hasattr(dsg_props, "model_obj"):
            dsg_props.model_obj = source
            if hasattr(dsg_props, "current_step"):
                dsg_props.current_step = 0
        _report(self, {'INFO'}, props, "Aligned scan prepared for DSG.", "Escaneado alineado preparado para DSG.")
        return {'FINISHED'}


class DICP_OT_RestoreSource(Operator):
    bl_idname = "dicp.restore_source"
    bl_label = "Restaurar posición"
    bl_description = "Devuelve el escaneado a la posición que tenía antes de iniciar el alineamiento"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dicp_props
        source = props.icp_source_obj
        original = _matrix_from_text(props.original_source_matrix)
        if source is None or original is None:
            _report(self, {'ERROR'}, props, "No saved initial position exists.", "No existe una posición inicial guardada.")
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
        props.status_message = _t(props, "Initial position restored", "Posición inicial restaurada")
        _set_markers_hidden(False)
        _report(self, {'INFO'}, props, "Initial position restored", "Posición inicial restaurada")
        return {'FINISHED'}


class DICP_OT_ClearLandmarks(Operator):
    bl_idname = "dicp.clear_landmarks"
    bl_label = "Redibujar puntos"
    bl_description = "Borra los seis puntos y prepara una nueva selección"
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
    bl_label = "Deshacer última acción"
    bl_description = "Deshace exactamente la última operación, igual que Ctrl+Z"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        props = context.scene.dicp_props
        if props.alignment_running:
            _report(
                self,
                {'WARNING'},
                props,
                "Cancel the running alignment with Esc before undoing.",
                "Cancela con Esc el alineamiento en curso antes de deshacer.",
            )
            return {'CANCELLED'}
        try:
            result = bpy.ops.ed.undo()
        except RuntimeError as exc:
            _report(self, {'WARNING'}, props, f"Undo is not available: {exc}", f"No hay una acción disponible para deshacer: {exc}")
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            _report(self, {'INFO'}, props, "Nothing to undo.", "No hay ninguna acción para deshacer.")
            return {'CANCELLED'}
        _report(self, {'INFO'}, props, "Last action undone.", "Última acción deshecha.")
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
        if props.alignment_running:
            _report(
                self,
                {'WARNING'},
                props,
                "Cancel the running alignment with Esc, then press Reset again.",
                "Cancela el alineamiento en curso con Esc y después pulsa Reiniciar de nuevo.",
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
                row = ui_style.primary_action(layout, enabled=not bool(getattr(props, "alignment_running", False)))
                row.operator("dicp.import_ios_stl", text=_t(props, "IMPORT IOS", "IMPORTAR IOS"), icon_value=icon_manager.icon_id("import_stl"))
            tools = ui_style.secondary_action(layout, align=True)
            tools.operator("dsg_suite.use_selected_ios", text=_t(props, "USE SELECTED IOS", "USAR IOS SELECCIONADO"), icon="MESH_DATA")
            tools.operator("dicp.auto_detect", text=_t(props, "DETECT", "DETECTAR"), icon_value=icon_manager.icon_id("auto_align"))
            return

        ensure_ios_gray_material(props.icp_source_obj, context=context)
        points_ready = props.source_point_count == 3 and props.target_point_count == 3

        if props.alignment_running:
            percentage = int(float(props.alignment_progress) * 100.0)
            core.set_status_bar(context, _t(props, f"Aligning {percentage}% · Esc cancels", f"Alineando {percentage}% · Esc cancela"))
            busy = ui_style.primary_action(layout, enabled=False)
            busy.operator("dicp.run_alignment", text=_t(props, "ALIGNING…", "ALINEANDO…"), icon_value=icon_manager.icon_id("status_pending"))
            return

        if not props.aligned:
            if points_ready:
                core.set_status_bar(context, _t(props, "Plan B · 3 zones ready", "Plan B · 3 zonas listas"))
                align = ui_style.primary_action(layout)
                op = align.operator("dicp.run_alignment", text=_t(props, "ALIGN WITH 3 ZONES", "ALINEAR CON 3 ZONAS"), icon_value=icon_manager.icon_id("manual_align"))
                op.automatic = False
                auto = ui_style.tertiary_action(layout)
                op = auto.operator("dicp.run_alignment", text=_t(props, "TRY AUTOMATIC", "PROBAR AUTOMÁTICO"), icon_value=icon_manager.icon_id("auto_align"))
                op.automatic = True
            else:
                core.set_status_bar(context, _t(props, "Plan A · occlusal/incisal dental alignment", "Plan A · alineación dental oclusal/incisal"))
                align = ui_style.primary_action(layout)
                op = align.operator("dicp.run_alignment", text=_t(props, "ALIGN AUTOMATICALLY", "ALINEAR AUTOMÁTICAMENTE"), icon_value=icon_manager.icon_id("auto_align"))
                op.automatic = True
                fallback = ui_style.tertiary_action(layout)
                fallback.operator("dicp.pick_landmarks", text=_t(props, "3-ZONE FALLBACK", "PLAN B · 3 ZONAS"), icon_value=icon_manager.icon_id("manual_align"))
                replace = ui_style.tertiary_action(layout)
                replace.operator("dicp.import_ios_stl", text=_t(props, "CHANGE IOS", "CAMBIAR IOS"), icon_value=icon_manager.icon_id("import_stl"))
            return

        if bool(props.alignment_quality_approved):
            immediate = core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE
            try:
                extraction_fdis = json.loads(str(context.scene.get("DSG_immediate_extraction_fdis_json", "[]") or "[]"))
            except Exception:
                extraction_fdis = []
            postex_confirmed = bool(context.scene.get("DSG_ios_postextraction_confirmed", False))
            postex_boolean_retry = bool(context.scene.get("DSG_ios_postextraction_boolean_retry_available", False))
            postex_retry = bool(context.scene.get("DSG_ios_postextraction_closure_retry_available", False))
            route_step = str(context.scene.get(core.ROUTE_STEP_KEY, "") or "")

            if immediate and extraction_fdis and not postex_confirmed:
                # DSG's main workflow panel owns the immediate post-extraction
                # controls. Keeping a second copy here made the same primary
                # action appear twice in the N-panel.
                core.set_status_bar(
                    context,
                    _t(props, "Use the DSG panel for the next IOS step.",
                       "Usa el panel DSG para el siguiente paso del IOS."),
                )
                layout.label(text=_t(props, "Next step in DSG", "Siguiente en DSG"), icon="INFO")
            else:
                core.set_status_bar(context, _t(props, f"Robust error {props.icp_error:.3f} mm", f"Error robusto {props.icp_error:.3f} mm"))
                go = ui_style.primary_action(layout)
                go.operator("dicp.send_to_dsg", text=_t(props, "CONTINUE", "CONTINUAR"), icon_value=icon_manager.icon_id("continue"))
                review = ui_style.tertiary_action(layout)
                review.operator("dicp.back_to_alignment", text=_t(props, "REVIEW", "REVISAR"), icon_value=icon_manager.icon_id("back"))
        else:
            core.set_status_bar(context, _t(props, f"Validation failed · robust error {props.icp_error:.3f} mm", f"Validación no superada · error robusto {props.icp_error:.3f} mm"))
            repeat = ui_style.primary_action(layout)
            if str(props.icp_source_obj.get("dicp_alignment_mode", "") or "") == "AUTO":
                repeat.operator("dicp.pick_landmarks", text=_t(props, "USE 3-ZONE FALLBACK", "USAR PLAN B · 3 ZONAS"), icon_value=icon_manager.icon_id("manual_align"))
            else:
                repeat.operator("dicp.back_to_alignment", text=_t(props, "MARK ZONES AGAIN", "MARCAR ZONAS DE NUEVO"), icon_value=icon_manager.icon_id("back"))


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
