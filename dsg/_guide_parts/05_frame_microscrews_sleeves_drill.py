class DSG_OT_BuildTubeFrame(Operator):
    bl_idname = "dsg.build_tube_frame"
    bl_label  = "Generate Tubular Frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_FRAME,
                action_en='Cannot generate the frame',
                action_es='No se puede generar la estructura'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        ensure_object_mode(context)
        points = get_contour_curve_points()
        if len(points) < 4:
            points = [Vector(p.co) for p in props.contour_points]
        if len(points) < 4:
            _dsg_report(self, {'ERROR'}, "The outline requires at least 4 points", "El contorno necesita al menos 4 puntos")
            return {'CANCELLED'}

        # Un frame regenerado invalida todos los anclajes de microtornillos previos.
        safe_remove_by_prefix(MICROSCREW_PREFIX)
        safe_remove_by_prefix(MICROSCREW_VISUAL_PREFIX)
        remove_pending_microscrew_geometry_previews()
        remove_pending_microscrew_visuals()
        safe_remove_by_name(MICROSCREW_MARKER_NAME)
        safe_remove_by_name(MICROSCREW_FRAME_COMBINED_TMP_NAME)
        props.microscrew_count = 0
        props.microscrew_preview_obj = None
        props.microscrew_records_json = '[]'
        remove_animated_microscrews()
        safe_remove_by_name(FRAME_NAME)
        # Preserve the clinician's click order exactly.
        contour_pts = _remove_near_duplicate_points(points, epsilon=0.02, closed=True)
        build_started = time.perf_counter()
        surface_obj = get_confirmed_passive_model_obj()
        frame_path = None
        frame_stats = {
            'engine': FRAME_SURFACE_ENGINE_ID,
            'reason': 'confirmed passive model unavailable',
            'cache_reused': False,
        }
        if _valid_obj(surface_obj):
            frame_path, frame_stats = build_surface_intrinsic_frame_path(
                context,
                surface_obj,
                contour_pts,
                get_insertion_axis(),
                max_spacing=FRAME_SURFACE_TARGET_SPACING_MM,
                frame_radius_mm=float(props.tube_radius),
            )

        used_fallback = False
        if not frame_path:
            reason = str(frame_stats.get('reason', '') or 'surface corridor routing unavailable')
            _dsg_report(
                self, {'ERROR'},
                f'Surface shortest-path frame failed: {reason}. No free-space fallback was used.',
                f'Falló la ruta más corta sobre superficie: {reason}. No se usó ningún trazado por el aire.')
            return {'CANCELLED'}

        bevel_resolution = max(8, int(getattr(props, 'irr_bevel_resolution', 10)))
        # The centreline is already a continuous surface polyline inside the semantic
        # corridor. POLY preserves that route and avoids Bézier overshoot.
        frame_obj = build_surface_poly_tube_mesh(
            context, frame_path, props.tube_radius,
            name=FRAME_NAME,
            bevel_resolution=bevel_resolution,
            cyclic=True,
        )
        if not frame_obj:
            _dsg_report(
                self, {'ERROR'},
                "Could not generate the surface frame",
                "No se pudo generar la estructura sobre la superficie")
            return {'CANCELLED'}

        # A cyclic POLY sweep is normally a single closed solid and does not
        # need voxelisation. Remesh is retained only as a defensive repair path,
        # which removes a major frame-generation bottleneck on healthy cases.
        remesh_applied = False
        solid_report = get_mesh_solid_report(frame_obj, max_polygons=600000)
        needs_repair = bool(solid_report.get('checked') and not solid_report.get('solid'))
        if not solid_report.get('checked'):
            scalable_report = get_mesh_solid_report_scalable(frame_obj)
            needs_repair = bool(
                scalable_report.get('checked') and not scalable_report.get('solid'))
            solid_report = scalable_report if scalable_report.get('checked') else solid_report
        if needs_repair:
            remesh = frame_obj.modifiers.new('DSG_FrameRemeshFallback', 'REMESH')
            remesh.mode = 'VOXEL'
            remesh.voxel_size = max(0.12, props.tube_radius * 0.28)
            remesh.use_smooth_shade = True
            if not apply_modifier_direct(context, frame_obj, remesh.name):
                safe_remove_object(frame_obj)
                _dsg_report(
                    self, {'ERROR'},
                    "Could not repair the generated frame",
                    "No se pudo reparar la estructura generada")
                return {'CANCELLED'}
            remesh_applied = True

        elapsed = time.perf_counter() - build_started
        metadata = {
            'DSG_frame_radius_mm': float(props.tube_radius),
            'DSG_frame_diameter_mm': float(props.tube_radius) * 2.0,
            'DSG_frame_path_engine': str(frame_stats.get('engine', FRAME_SURFACE_ENGINE_ID)),
            'DSG_frame_surface_object': str(frame_stats.get('surface_name', _safe_object_name(surface_obj) or '')),
            'DSG_frame_surface_cache_reused': bool(frame_stats.get('cache_reused', False)),
            'DSG_frame_surface_vertices': int(frame_stats.get('surface_vertices', 0)),
            'DSG_frame_geodesic_expanded': int(frame_stats.get('expanded', 0)),
            'DSG_frame_geodesic_length_mm': float(frame_stats.get('geodesic_length_mm', 0.0)),
            'DSG_frame_geodesic_no_euclidean_fallback': True,
            'DSG_frame_geodesic_backend': str(frame_stats.get('backend', 'UNKNOWN')),
            'DSG_frame_distance_backend': str(frame_stats.get('distance_backend', 'UNKNOWN')),
            'DSG_frame_continuous_backend': str(frame_stats.get('continuous_backend', 'UNKNOWN')),
            'DSG_frame_semantic_corridor': bool(frame_stats.get('semantic_corridor', False)),
            'DSG_frame_route_objective': str(frame_stats.get('route_objective', '')),
            'DSG_frame_weighted_route_cost': float(frame_stats.get('weighted_route_cost', 0.0)),
            'DSG_frame_clearance_evaluations': int(frame_stats.get('clearance_evaluations', 0)),
            'DSG_frame_resolved_anchor_surface_coordinates_json': json.dumps(frame_stats.get('resolved_anchor_surface_coordinates', []), separators=(',', ':')),
            'DSG_frame_width_policy': str(frame_stats.get('width_policy', 'NONE_FINAL_BOOLEAN_ADAPTS_TUBE_TO_MODEL')),
            'DSG_frame_width_validated': bool(frame_stats.get('width_validated', False)),
            'DSG_frame_width_required_mm': float(frame_stats.get('width_required_mm', props.tube_radius * 2.0)),
            'DSG_frame_width_min_mm': float(frame_stats.get('width_min_mm', 0.0)),
            'DSG_frame_width_min_retained_ratio': float(frame_stats.get('width_min_retained_ratio', 1.0)),
            'DSG_frame_width_allowed_outer_embed_ratio': float(frame_stats.get('width_allowed_outer_embed_ratio', FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO)),
            'DSG_frame_width_tolerated_samples': int(frame_stats.get('width_tolerated_samples', 0)),
            'DSG_frame_width_reroutes': int(frame_stats.get('width_reroutes', 0)),
            'DSG_frame_width_blocked_vertices': int(frame_stats.get('width_blocked_vertices', 0)),
            'DSG_frame_width_samples': int(frame_stats.get('width_samples', 0)),
            'DSG_frame_width_worst_surface_rise_mm': float(frame_stats.get('width_worst_surface_rise_mm', 0.0)),
            'DSG_frame_width_surface_rise_tolerance_mm': float(frame_stats.get('width_surface_rise_tolerance_mm', 0.0)),
            'DSG_frame_max_anchor_snap_mm': float(frame_stats.get('max_anchor_snap_mm', 0.0)),
            'DSG_frame_anchor_auto_relocated_count': int(frame_stats.get('anchor_auto_relocated_count', 0)),
            'DSG_frame_anchor_auto_relocated_max_surface_mm': float(frame_stats.get('anchor_auto_relocated_max_surface_mm', 0.0)),
            'DSG_frame_anchor_auto_relocated_max_euclidean_mm': float(frame_stats.get('anchor_auto_relocated_max_euclidean_mm', 0.0)),
            'DSG_frame_anchor_resolution_json': json.dumps(frame_stats.get('anchor_resolution', []), separators=(',', ':')),
            'DSG_frame_resolved_anchor_points_json': json.dumps(frame_stats.get('resolved_anchor_points', []), separators=(',', ':')),
            'DSG_frame_raw_path_vertices': int(frame_stats.get('raw_path_vertices', 0)),
            'DSG_frame_catmull_control_points': int(frame_stats.get('catmull_control_points', 0)),
            'DSG_frame_catmull_control_spacing_mm': float(frame_stats.get('catmull_control_spacing_mm', FRAME_CATMULL_CONTROL_SPACING_MM_FIXED)),
            'DSG_frame_catmull_sample_spacing_mm': float(frame_stats.get('catmull_sample_spacing_mm', FRAME_CATMULL_SAMPLE_SPACING_MM_FIXED)),
            'DSG_frame_clean_spline_length_mm': float(frame_stats.get('clean_spline_length_mm', 0.0)),
            'DSG_frame_final_path_points': int(len(frame_path)),
            'DSG_frame_axial_segments': int(frame_stats.get('axial_segments', 0)),
            'DSG_frame_segment_count': int(frame_stats.get('segment_count', len(contour_pts))),
            'DSG_frame_fallback_used': bool(used_fallback),
            'DSG_frame_fallback_reason': str(frame_stats.get('fallback_reason', '')),
            'DSG_frame_remesh_fallback_applied': bool(remesh_applied),
            'DSG_frame_elapsed_seconds': float(elapsed),
            'DSG_frame_target_spacing_mm': float(FRAME_SURFACE_TARGET_SPACING_MM),
            'DSG_frame_source_points_json': json.dumps([[float(v.x), float(v.y), float(v.z)] for v in contour_pts]),
        }
        props.frame_obj = register_dsg_object(
            frame_obj, ROLE_FRAME, FRAME_NAME, metadata)

        # El contorno es una herramienta temporal. Solo se consume después de que
        # el frame se haya creado, consolidado y registrado correctamente.
        consume_contour_after_frame(props)

        engine_label = str(frame_stats.get('engine', FRAME_SURFACE_ENGINE_ID))
        remesh_note_en = ' · repair remesh used' if remesh_applied else ''
        remesh_note_es = ' · se usó remesh de reparación' if remesh_applied else ''
        relocated_count = int(frame_stats.get('anchor_auto_relocated_count', 0))
        relocated_max = float(frame_stats.get('anchor_auto_relocated_max_surface_mm', 0.0))
        anchor_note_en = (
            f' · {relocated_count} anchor(s) safely relocated ≤{relocated_max:.2f} mm on-surface'
            if relocated_count else '')
        anchor_note_es = (
            f' · {relocated_count} punto(s) reajustado(s) automáticamente ≤{relocated_max:.2f} mm sobre superficie'
            if relocated_count else '')
        _dsg_report(
            self, {'INFO'},
            f"Frame generated with {engine_label}; shortest on-surface route through {len(contour_pts)} user anchors in click order; cylindrical tube intersects the support model for final boolean adaptation; {elapsed:.2f} s{remesh_note_en}; contour deleted",
            f"Estructura generada con {engine_label}; ruta más corta sobre superficie pasando por {len(contour_pts)} puntos en el orden marcado; el tubo cilíndrico intersecta el modelo para adaptarse en la booleana final; {elapsed:.2f} s{remesh_note_es}; contorno eliminado")
        return {'FINISHED'}



# ─────────────────────────────────────────────────────────────
# Microtornillos: tubo desde el frame + sleeve terminal
# ─────────────────────────────────────────────────────────────

def get_pending_microscrew_preview(props):
    obj = getattr(props, 'microscrew_preview_obj', None)
    if _valid_obj(obj) and bool(obj.get('DSG_microscrew_preview', False)):
        return obj
    candidate = bpy.data.objects.get(MICROSCREW_PREVIEW_NAME)
    if _valid_obj(candidate) and bool(candidate.get('DSG_microscrew_preview', False)):
        return candidate
    candidates = []
    for item in list(bpy.data.objects):
        try:
            if (_valid_obj(item)
                    and bool(item.get('DSG_microscrew_preview', False))):
                candidates.append(item)
        except (ReferenceError, RuntimeError):
            continue
    if candidates:
        candidates.sort(key=lambda item: item.name)
        return candidates[0]
    return None


def get_confirmed_microscrew_objects():
    out = []
    for obj in list(bpy.data.objects):
        try:
            if (obj.type == 'MESH'
                    and obj.name.startswith(MICROSCREW_PREFIX)
                    and obj.name != MICROSCREW_PREVIEW_NAME
                    and bool(obj.get('DSG_microscrew_confirmed', False))
                    and _valid_obj(obj)):
                out.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    return sorted(out, key=lambda item: int(item.get('DSG_microscrew_index', 0)))



def get_microscrew_records(props):
    try:
        records = json.loads(getattr(props, 'microscrew_records_json', '[]') or '[]')
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return []


def set_microscrew_records(props, records):
    props.microscrew_records_json = json.dumps(records, separators=(',', ':'))


def _record_from_microscrew_object(obj, index=None):
    if not _valid_obj(obj):
        return None
    axis = list(obj.get('DSG_microscrew_axis', (0.0, 0.0, 1.0)))
    target = Vector(obj.get('DSG_microscrew_point_target', (0.0, 0.0, 0.0)))
    sleeve_top = obj.get('DSG_microscrew_sleeve_top')
    if sleeve_top is None:
        sleeve_top = list(target + Vector(axis).normalized() * MICROSCREW_SLEEVE_HEIGHT_MM)
    point_frame_a = obj.get('DSG_microscrew_point_frame_a', obj.get('DSG_microscrew_point_frame'))
    point_frame_b = obj.get('DSG_microscrew_point_frame_b')
    diameter, length = _normalized_microscrew_dimensions(
        obj.get('DSG_microscrew_diameter_mm', obj.get('DSG_microscrew_guided_diameter_mm', MICROSCREW_DIAMETER_DEFAULT_MM)),
        obj.get('DSG_microscrew_length_mm', MICROSCREW_LENGTH_DEFAULT_MM))
    return {
        'index': int(index if index is not None else obj.get('DSG_microscrew_index', 0)),
        'axis': [float(v) for v in axis],
        'sleeve_top': [float(v) for v in sleeve_top],
        'x_hint': [float(v) for v in obj.get('DSG_microscrew_x_hint', (1.0, 0.0, 0.0))],
        'point_target': [float(v) for v in target],
        'point_frame_a': [float(v) for v in point_frame_a] if point_frame_a is not None else None,
        'point_frame_b': [float(v) for v in point_frame_b] if point_frame_b is not None else None,
        'support_count': int(obj.get('DSG_microscrew_support_count', 1)),
        'sleeve_height': MICROSCREW_SLEEVE_HEIGHT_MM,
        'guided_diameter': diameter,
        'diameter': diameter,
        'length': length,
    }


def _matrix_along_local_z(center, axis):
    direction = Vector(axis)
    if direction.length < 1e-8:
        direction = Vector((0.0, 0.0, 1.0))
    direction.normalize()
    rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(direction).to_matrix().to_4x4()
    return Matrix.Translation(Vector(center)) @ rotation


def _create_cylinder_between(context, name, point_a, point_b, radius, segments=32):
    start = Vector(point_a)
    end = Vector(point_b)
    chord = end - start
    length = chord.length
    if length < 0.10:
        return None
    mesh = make_cylinder_mesh(
        name + '_Mesh', max(0.05, float(radius)), length,
        verts=max(12, min(96, int(segments))))
    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = _matrix_along_local_z(start.lerp(end, 0.5), chord)
    link_object(context, obj)
    return obj



def make_microscrew_anatomic_sleeve_mesh(name, segments=32, screw_diameter_mm=None):
    """Closed sleeve whose lumen and anatomical seat follow screw diameter."""
    segments = max(16, min(96, int(segments)))
    diameter, _length = _normalized_microscrew_dimensions(screw_diameter_mm, None)
    radial_scale = diameter / max(1.0e-8, MICROSCREW_GUIDED_DIAMETER_MM)
    half_height = MICROSCREW_SLEEVE_HEIGHT_MM * 0.5
    inner_base = diameter * 0.5
    wall = MICROSCREW_WALL_THICKNESS_MM

    # Perfil local de abajo hacia arriba. El cuerpo inferior conserva Ø interno
    # 2 mm; el collar superior sigue el cono inferior del tope real.
    rings = [(-half_height, inner_base)]
    seat_start_z = half_height - MICROSCREW_SEAT_DEPTH_MM
    rings.append((seat_start_z, inner_base))
    for depth, radius in MICROSCREW_SEAT_PROFILE_MM:
        z = half_height - float(depth)
        radius = max(inner_base, float(radius) * radial_scale)
        if abs(z - rings[-1][0]) < 1e-7:
            rings[-1] = (z, max(rings[-1][1], radius))
        else:
            rings.append((z, radius))
    rings.sort(key=lambda item: item[0])

    vertices = []
    for z, inner_radius in rings:
        outer_radius = inner_radius + wall
        for ring_radius in (outer_radius, inner_radius):
            for index in range(segments):
                angle = 2.0 * math.pi * index / segments
                vertices.append((
                    ring_radius * math.cos(angle),
                    ring_radius * math.sin(angle),
                    z,
                ))

    faces = []
    stride = segments * 2
    for level in range(len(rings) - 1):
        base = level * stride
        nxt = (level + 1) * stride
        for index in range(segments):
            j = (index + 1) % segments
            faces.append((base + index, base + j, nxt + j, nxt + index))
            faces.append((base + segments + index,
                          nxt + segments + index,
                          nxt + segments + j,
                          base + segments + j))

    bottom = 0
    top = (len(rings) - 1) * stride
    for index in range(segments):
        j = (index + 1) % segments
        faces.append((bottom + index,
                      bottom + segments + index,
                      bottom + segments + j,
                      bottom + j))
        faces.append((top + index,
                      top + j,
                      top + segments + j,
                      top + segments + index))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    try:
        mesh.validate(clean_customdata=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh.update(calc_edges=True)
    try:
        for poly in mesh.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return mesh



def _smart_anchor_tangent_basis(normal, toward):
    normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    toward = Vector(toward)
    major = toward - normal * toward.dot(normal)
    if major.length < 1.0e-7:
        reference = Vector((1.0, 0.0, 0.0))
        if abs(reference.dot(normal)) > 0.86:
            reference = Vector((0.0, 1.0, 0.0))
        major = reference - normal * reference.dot(normal)
    major.normalize()
    minor = normal.cross(major)
    minor = _normalized_or_fallback(minor, (0.0, 1.0, 0.0))
    major = minor.cross(normal)
    major = _normalized_or_fallback(major, major)
    return major, minor


def _smart_anchor_project_candidate(tree, raw_candidate, seed_point, seed_normal,
                                    max_projection=None, max_move=None):
    raw_candidate = Vector(raw_candidate)
    seed_point = Vector(seed_point)
    seed_normal = _normalized_or_fallback(seed_normal, (0.0, 0.0, 1.0))
    if tree is None:
        return raw_candidate, seed_normal

    projection_limit = max(
        0.20,
        float(REINFORCEMENT_SMART_ANCHOR_MAX_PROJECTION_MM)
        if max_projection is None else float(max_projection))
    move_limit = max(
        0.25,
        float(REINFORCEMENT_SMART_ANCHOR_MAX_MOVE_MM)
        if max_move is None else float(max_move))
    try:
        result = tree.find_nearest(raw_candidate)
        if not result or result[0] is None:
            return None
        location, normal, _index, distance = result
        if distance is None or float(distance) > projection_limit:
            return None
        location = Vector(location)
        normal = _normalized_or_fallback(normal, seed_normal)

        # La normal de un STL puede estar invertida. La orientamos mediante el
        # volumen actual del frame: -normal debe señalar hacia el material en el
        # que se enterrará el collar antes de ejecutar la booleana.
        probe = _smart_anchor_probe_solid_interior(tree, location, normal)
        if probe is not None:
            normal = Vector(probe[0])

        alignment = abs(normal.dot(seed_normal))
        if alignment < float(REINFORCEMENT_SMART_ANCHOR_MIN_NORMAL_DOT):
            return None
        if (location - seed_point).length > move_limit:
            return None
        return location, normal
    except Exception:
        return None


def _smart_anchor_neighbor_direction(point, neighbor_points):
    point = Vector(point)
    vectors = []
    for neighbor in neighbor_points:
        vector = Vector(neighbor) - point
        if vector.length > 1.0e-7:
            vectors.append(vector.normalized())
    if not vectors:
        return Vector((1.0, 0.0, 0.0))
    direction = Vector((0.0, 0.0, 0.0))
    for vector in vectors:
        direction += vector
    if direction.length < 1.0e-7:
        direction = vectors[0]
    return direction.normalized()


def _smart_anchor_local_roughness(tree, point, normal, major, minor, sample_radius):
    if tree is None:
        return 0.0
    point = Vector(point)
    normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    sample_radius = max(0.18, float(sample_radius))
    penalties = []
    for axis in (major, -major, minor, -minor):
        raw = point + Vector(axis) * sample_radius
        try:
            result = tree.find_nearest(raw)
        except Exception:
            result = None
        if not result or result[0] is None:
            penalties.append(0.65)
            continue
        location, sample_normal, _index, distance = result
        if distance is None or float(distance) > sample_radius * 1.25:
            penalties.append(0.65)
            continue
        sample_normal = _normalized_or_fallback(sample_normal, normal)
        dot = sample_normal.dot(normal)
        if dot < 0.0:
            dot = -dot
        penalties.append((1.0 - max(0.0, min(1.0, dot))) ** 2)
    return sum(penalties) / float(max(1, len(penalties)))


def _smart_anchor_fit_metrics(tree, point, normal, toward, connector_radius):
    point = Vector(point)
    normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    toward = _normalized_or_fallback(toward, (1.0, 0.0, 0.0))
    major, minor = _smart_anchor_tangent_basis(normal, toward)

    incidence = 1.0 - abs(max(-1.0, min(1.0, toward.dot(normal))))
    desired_minor = max(0.20, float(connector_radius)) * float(REINFORCEMENT_BLEND_FOOT_SCALE)
    desired_major = desired_minor * (
        1.0 + float(REINFORCEMENT_BLEND_TANGENTIAL_STRETCH) * incidence)
    search_distance = max(connector_radius * 5.0, desired_major * 2.5)
    allowed_major = _estimate_support_axis_half_span(
        tree, point, normal, major, search_distance)
    allowed_minor = _estimate_support_axis_half_span(
        tree, point, normal, minor, search_distance)

    ratios = []
    if allowed_major is not None and desired_major > 1.0e-8:
        ratios.append(float(allowed_major) / desired_major)
    if allowed_minor is not None and desired_minor > 1.0e-8:
        ratios.append(float(allowed_minor) / desired_minor)
    fit_ratio = min(ratios) if ratios else 0.72
    fit_ratio = max(0.0, min(2.0, fit_ratio))
    return fit_ratio, major, minor, desired_major, desired_minor


def _smart_anchor_probe_solid_interior(tree, point, normal, max_distance=None):
    """Detecta qué lado de la superficie entra realmente en el sólido actual.

    El refuerzo se construye antes de la UNION booleana. Por eso necesitamos que
    la base del collar penetre en el volumen ya existente del frame, no en una
    geometría final todavía inexistente. Se prueban ambas direcciones normales y
    se elige la que atraviesa material y sale por otra cara coherente del sólido.

    Devuelve ``(outward_normal, inward_direction, thickness)`` o ``None``.
    """
    if tree is None:
        return None
    point = Vector(point)
    source_normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    epsilon = max(
        0.012,
        float(REINFORCEMENT_STRUCTURAL_INTERIOR_ORIGIN_EPS_MM))
    distance_limit = max(
        0.50,
        float(REINFORCEMENT_STRUCTURAL_THICKNESS_MAX_MM)
        if max_distance is None else float(max_distance))

    probes = []
    for sign in (-1.0, 1.0):
        direction = source_normal * sign
        origin = point + direction * epsilon
        try:
            result = tree.ray_cast(origin, direction, distance_limit)
        except Exception:
            result = None
        if not result or result[0] is None:
            continue
        _location, hit_normal, _index, distance = result
        if distance is None:
            continue
        thickness = float(distance) + epsilon
        if thickness <= epsilon * 2.0 or thickness > distance_limit + epsilon:
            continue
        hit_normal = _normalized_or_fallback(hit_normal, direction)
        exit_alignment = max(-1.0, min(1.0, hit_normal.dot(direction)))
        if exit_alignment < float(REINFORCEMENT_STRUCTURAL_INTERIOR_HIT_DOT_MIN):
            continue

        # Una salida por la pared opuesta suele tener normal aproximadamente en
        # el mismo sentido del rayo. Se prioriza esa coherencia y después el
        # recorrido de material más corto, evitando capturar otra pieza lejana.
        score = exit_alignment * 4.0 - thickness * 0.025
        probes.append((score, direction.copy(), thickness))

    if not probes:
        return None
    probes.sort(key=lambda item: item[0], reverse=True)
    _score, inward_direction, thickness = probes[0]
    inward_direction = _normalized_or_fallback(inward_direction, -source_normal)
    outward_normal = -inward_direction
    return outward_normal, inward_direction, float(thickness)


def _smart_anchor_single_wall_thickness(tree, point, normal, max_distance=None):
    """Mide el grosor del sólido prebooleana y orienta su lado interior real."""
    probe = _smart_anchor_probe_solid_interior(
        tree, point, normal, max_distance=max_distance)
    if probe is None:
        return None
    _outward_normal, _inward_direction, thickness = probe
    return float(thickness)


def _smart_anchor_structural_metrics(tree, point, normal, toward, connector_radius):
    """Devuelve grosor débil robusto y profundidad segura de enterramiento.

    El grosor se muestrea en el centro y alrededor de la futura huella. Se usa un
    percentil bajo para localizar la zona estructuralmente más débil sin dejar que
    un único triángulo defectuoso domine completamente la decisión.
    """
    if tree is None:
        return None, float(REINFORCEMENT_BLEND_OVERLAP_MM), 0.0
    point = Vector(point)
    normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    toward = _normalized_or_fallback(toward, (1.0, 0.0, 0.0))
    major, minor = _smart_anchor_tangent_basis(normal, toward)
    sample_radius = max(
        0.16,
        float(connector_radius)
        * float(REINFORCEMENT_STRUCTURAL_THICKNESS_SAMPLE_RADIUS_SCALE))
    sample_offsets = (
        Vector((0.0, 0.0, 0.0)),
        major * sample_radius,
        -major * sample_radius,
        minor * sample_radius,
        -minor * sample_radius,
    )
    thicknesses = []
    for offset in sample_offsets:
        raw = point + offset
        try:
            nearest = tree.find_nearest(raw)
        except Exception:
            nearest = None
        if not nearest or nearest[0] is None:
            continue
        location, local_normal, _index, distance = nearest
        if distance is None or float(distance) > sample_radius * 1.55:
            continue
        local_normal = _normalized_or_fallback(local_normal, normal)
        local_probe = _smart_anchor_probe_solid_interior(
            tree, Vector(location), local_normal)
        if local_probe is not None:
            local_normal = Vector(local_probe[0])
            thickness = float(local_probe[2])
        else:
            if local_normal.dot(normal) < 0.0:
                local_normal.negate()
            thickness = _smart_anchor_single_wall_thickness(
                tree, Vector(location), local_normal)
        if thickness is not None:
            thicknesses.append(float(thickness))

    coverage = len(thicknesses) / float(len(sample_offsets))
    if not thicknesses or coverage < 0.40:
        return None, float(REINFORCEMENT_BLEND_OVERLAP_MM), coverage

    thicknesses.sort()
    # Percentil bajo robusto: segundo valor cuando hay suficientes muestras.
    weak_index = 1 if len(thicknesses) >= 4 else 0
    weak_thickness = thicknesses[weak_index]
    safe_thickness = min(thicknesses)
    burial = safe_thickness * float(REINFORCEMENT_STRUCTURAL_BURIAL_FRACTION)
    burial = max(
        float(REINFORCEMENT_STRUCTURAL_BURIAL_MIN_MM),
        float(REINFORCEMENT_STRUCTURAL_MIN_SOLID_OVERLAP_MM),
        burial)
    burial = min(float(REINFORCEMENT_STRUCTURAL_BURIAL_MAX_MM), burial)
    # El solape es previo a la booleana y debe quedar dentro del sólido actual,
    # pero nunca atravesar más de aproximadamente la mitad de la pared medida.
    burial = min(burial, max(0.06, safe_thickness * 0.48))
    return float(weak_thickness), float(burial), float(coverage)


def _smart_anchor_candidate_score(tree, candidate_point, candidate_normal,
                                  seed_point, neighbor_points, connector_radius,
                                  search_radius):
    point = Vector(candidate_point)
    normal = _normalized_or_fallback(candidate_normal, (0.0, 0.0, 1.0))
    seed = Vector(seed_point)
    neighbors = [Vector(value) for value in neighbor_points]
    toward = _smart_anchor_neighbor_direction(point, neighbors)

    move = (point - seed).length / max(0.20, float(search_radius))
    move_cost = float(REINFORCEMENT_SMART_ANCHOR_MOVE_WEIGHT) * move * move

    tangent_cost = 0.0
    valid_neighbors = 0
    for neighbor in neighbors:
        vector = neighbor - point
        if vector.length < 1.0e-7:
            continue
        direction = vector.normalized()
        tangent_cost += abs(direction.dot(normal)) ** 2
        valid_neighbors += 1
    if valid_neighbors:
        tangent_cost /= float(valid_neighbors)
    tangent_cost *= float(REINFORCEMENT_SMART_ANCHOR_TANGENCY_WEIGHT)

    fit_ratio, major, minor, _desired_major, _desired_minor = _smart_anchor_fit_metrics(
        tree, point, normal, toward, connector_radius)
    if fit_ratio >= 1.0:
        fit_cost = -0.12 * min(1.0, fit_ratio - 1.0)
    else:
        deficit = 1.0 - fit_ratio
        fit_cost = float(REINFORCEMENT_SMART_ANCHOR_FIT_WEIGHT) * deficit * deficit

    roughness = _smart_anchor_local_roughness(
        tree, point, normal, major, minor,
        max(0.35, float(connector_radius) * 0.62))
    roughness_cost = float(REINFORCEMENT_SMART_ANCHOR_ROUGHNESS_WEIGHT) * roughness

    weak_thickness, burial_depth, thickness_coverage = (
        _smart_anchor_structural_metrics(
            tree, point, normal, toward, connector_radius)
        if REINFORCEMENT_STRUCTURAL_WEAKNESS_ENABLED
        else (None, float(REINFORCEMENT_BLEND_OVERLAP_MM), 0.0)
    )
    base_score = move_cost + tangent_cost + fit_cost + roughness_cost
    return (
        base_score, fit_ratio,
        weak_thickness, burial_depth, thickness_coverage,
    )


def _smart_anchor_generate_candidates(tree, seed_point, seed_normal,
                                      neighbor_points, connector_radius,
                                      search_radius=None, center_override=None,
                                      include_seed=True, score_radius=None):
    seed = Vector(seed_point)
    seed_normal = _normalized_or_fallback(seed_normal, (0.0, 0.0, 1.0))
    center = Vector(center_override) if center_override is not None else seed.copy()
    radius = max(
        0.20,
        float(REINFORCEMENT_SMART_ANCHOR_SEARCH_RADIUS_MM)
        if search_radius is None else float(search_radius))
    toward = _smart_anchor_neighbor_direction(center, neighbor_points)
    major, minor = _smart_anchor_tangent_basis(seed_normal, toward)

    raw_candidates = []
    if include_seed:
        raw_candidates.append(seed.copy())
    if (center - seed).length > 1.0e-5:
        raw_candidates.append(center.copy())
    fractions = REINFORCEMENT_SMART_ANCHOR_RING_FRACTIONS
    sample_count = max(4, int(REINFORCEMENT_SMART_ANCHOR_SAMPLES_PER_RING))
    for fraction in fractions:
        ring_radius = radius * max(0.05, float(fraction))
        for index in range(sample_count):
            angle = math.tau * index / float(sample_count)
            raw_candidates.append(
                center
                + major * (math.cos(angle) * ring_radius)
                + minor * (math.sin(angle) * ring_radius))

    candidates = []
    for raw in raw_candidates:
        projected = _smart_anchor_project_candidate(
            tree, raw, seed, seed_normal,
            max_projection=max(
                float(REINFORCEMENT_SMART_ANCHOR_MAX_PROJECTION_MM),
                radius * 0.55),
            max_move=float(REINFORCEMENT_SMART_ANCHOR_MAX_MOVE_MM))
        if projected is None:
            continue
        point, normal = projected
        duplicate = False
        for existing in candidates:
            if (point - existing['point']).length < 0.08:
                duplicate = True
                break
        if duplicate:
            continue
        (score, fit_ratio, weak_thickness,
         burial_depth, thickness_coverage) = _smart_anchor_candidate_score(
            tree, point, normal, seed, neighbor_points,
            connector_radius, max(float(score_radius) if score_radius is not None else radius, 0.20))
        candidates.append({
            'point': Vector(point),
            'normal': Vector(normal),
            'score': float(score),
            'base_score': float(score),
            'fit_ratio': float(fit_ratio),
            'weak_thickness': (None if weak_thickness is None else float(weak_thickness)),
            'burial_depth': float(burial_depth),
            'thickness_coverage': float(thickness_coverage),
        })

    if not candidates:
        candidates.append({
            'point': seed.copy(),
            'normal': seed_normal.copy(),
            'score': 1000.0,
            'base_score': 1000.0,
            'fit_ratio': 0.0,
            'weak_thickness': None,
            'burial_depth': float(REINFORCEMENT_BLEND_OVERLAP_MM),
            'thickness_coverage': 0.0,
        })

    # Prioridad estructural: localizar primero el grosor más débil cercano al clic.
    # Entre candidatos de debilidad comparable, se prefiere el que permite mayor
    # enterramiento seguro de la base del refuerzo.
    valid_thicknesses = [
        float(item['weak_thickness'])
        for item in candidates
        if item.get('weak_thickness') is not None
        and float(item['weak_thickness']) >= float(REINFORCEMENT_STRUCTURAL_MIN_VALID_THICKNESS_MM)
    ]
    if REINFORCEMENT_STRUCTURAL_WEAKNESS_ENABLED and valid_thicknesses:
        weakest = min(valid_thicknesses)
        reference = max(float(connector_radius) * 1.6, 1.0)
        tolerance = max(0.05, float(REINFORCEMENT_STRUCTURAL_WEAKNESS_TOLERANCE_MM))
        max_burial = max(0.10, float(REINFORCEMENT_STRUCTURAL_BURIAL_MAX_MM))
        for item in candidates:
            thickness = item.get('weak_thickness')
            if thickness is None or float(thickness) < float(REINFORCEMENT_STRUCTURAL_MIN_VALID_THICKNESS_MM):
                item['score'] = float(item['base_score']) + float(REINFORCEMENT_STRUCTURAL_INVALID_THICKNESS_PENALTY)
                continue
            thickness = float(thickness)
            weakness_delta = max(0.0, thickness - weakest)
            weakness_cost = float(REINFORCEMENT_STRUCTURAL_WEAKNESS_WEIGHT) * (weakness_delta / reference) ** 2
            burial_reward = 0.0
            if weakness_delta <= tolerance:
                burial_ratio = min(1.0, float(item.get('burial_depth', 0.0)) / max_burial)
                burial_reward = float(REINFORCEMENT_STRUCTURAL_BURIAL_WEIGHT) * burial_ratio
            item['score'] = float(item['base_score']) + weakness_cost - burial_reward
            item['weakest_reference'] = weakest
    candidates.sort(key=lambda item: item['score'])
    return candidates


def _smart_anchor_pair_score(candidate_a, candidate_b, seed_distance):
    point_a = Vector(candidate_a['point'])
    point_b = Vector(candidate_b['point'])
    normal_a = _normalized_or_fallback(candidate_a['normal'], (0.0, 0.0, 1.0))
    normal_b = _normalized_or_fallback(candidate_b['normal'], normal_a)
    chord = point_b - point_a
    distance = chord.length
    if distance < max(1.25, REINFORCEMENT_DIAMETER_MM * 0.72):
        return 1.0e6
    direction = chord.normalized()

    tangency = abs(direction.dot(normal_a)) ** 2 + abs(direction.dot(normal_b)) ** 2
    tangency *= float(REINFORCEMENT_SMART_ANCHOR_PAIR_TANGENCY_WEIGHT)

    u_a = _preferred_reinforcement_tube_u(normal_a, direction)
    u_b = _preferred_reinforcement_tube_u(normal_b, -direction)
    twist = abs(_signed_angle_around_axis(u_a, u_b, direction)) / math.pi
    twist_cost = float(REINFORCEMENT_SMART_ANCHOR_TWIST_WEIGHT) * twist * twist

    length_reference = max(1.0e-6, float(seed_distance))
    length_change = abs(distance - length_reference) / length_reference
    length_cost = 0.18 * length_change * length_change

    fit_balance = abs(float(candidate_a.get('fit_ratio', 0.0))
                      - float(candidate_b.get('fit_ratio', 0.0)))
    balance_cost = 0.10 * fit_balance * fit_balance
    return tangency + twist_cost + length_cost + balance_cost


def _smart_anchor_optimize_pair(tree_a, tree_b, seed_a, normal_a, seed_b, normal_b,
                                connector_radius):
    seed_a = Vector(seed_a)
    seed_b = Vector(seed_b)
    normal_a = _normalized_or_fallback(normal_a, (0.0, 0.0, 1.0))
    normal_b = _normalized_or_fallback(normal_b, normal_a)
    search_radius = float(REINFORCEMENT_SMART_ANCHOR_SEARCH_RADIUS_MM)

    candidates_a = _smart_anchor_generate_candidates(
        tree_a, seed_a, normal_a, [seed_b], connector_radius, search_radius)
    candidates_b = _smart_anchor_generate_candidates(
        tree_b, seed_b, normal_b, [seed_a], connector_radius, search_radius)
    shortlist = max(2, int(REINFORCEMENT_SMART_ANCHOR_SHORTLIST))
    candidates_a = candidates_a[:shortlist]
    candidates_b = candidates_b[:shortlist]

    seed_distance = (seed_b - seed_a).length
    best = None
    for candidate_a in candidates_a:
        for candidate_b in candidates_b:
            score = (
                float(candidate_a['score'])
                + float(candidate_b['score'])
                + _smart_anchor_pair_score(candidate_a, candidate_b, seed_distance))
            if best is None or score < best[0]:
                best = (score, candidate_a, candidate_b)
    if best is None:
        return (seed_a, normal_a, float(REINFORCEMENT_BLEND_OVERLAP_MM),
                seed_b, normal_b, float(REINFORCEMENT_BLEND_OVERLAP_MM))

    _, chosen_a, chosen_b = best
    # Refinamiento local pequeño alrededor del par elegido. Sigue respetando el
    # radio máximo medido desde el clic original.
    refine_radius = float(REINFORCEMENT_SMART_ANCHOR_REFINEMENT_RADIUS_MM)
    refined_a = _smart_anchor_generate_candidates(
        tree_a, seed_a, normal_a, [chosen_b['point']], connector_radius,
        search_radius=refine_radius, center_override=chosen_a['point'],
        score_radius=search_radius)
    refined_b = _smart_anchor_generate_candidates(
        tree_b, seed_b, normal_b, [chosen_a['point']], connector_radius,
        search_radius=refine_radius, center_override=chosen_b['point'],
        score_radius=search_radius)
    refined_a = refined_a[:shortlist]
    refined_b = refined_b[:shortlist]
    for candidate_a in refined_a:
        for candidate_b in refined_b:
            score = (
                float(candidate_a['score'])
                + float(candidate_b['score'])
                + _smart_anchor_pair_score(candidate_a, candidate_b, seed_distance))
            if score < best[0]:
                best = (score, candidate_a, candidate_b)

    _, chosen_a, chosen_b = best
    return (
        Vector(chosen_a['point']), Vector(chosen_a['normal']),
        float(chosen_a.get('burial_depth', REINFORCEMENT_BLEND_OVERLAP_MM)),
        Vector(chosen_b['point']), Vector(chosen_b['normal']),
        float(chosen_b.get('burial_depth', REINFORCEMENT_BLEND_OVERLAP_MM)),
    )


def _optimize_reinforcement_chain_anchors(context, points, normals, support_objects,
                                          connector_radius, surface_cache=None):
    points = [Vector(point) for point in points]
    normals = [
        _normalized_or_fallback(
            normals[index] if index < len(normals) else (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0))
        for index in range(len(points))]
    supports = list(support_objects or [])
    if (not REINFORCEMENT_SMART_ANCHORS_ENABLED
            or len(points) < 2
            or len(supports) < len(points)):
        return points, normals, [float(REINFORCEMENT_BLEND_OVERLAP_MM)] * len(points)

    cache = surface_cache if surface_cache is not None else {}
    trees = []
    for support in supports:
        if not _valid_obj(support):
            trees.append(None)
            continue
        key = _safe_object_name(support)
        if key not in cache:
            cache[key] = _build_world_surface_bvh(context, support)
        trees.append(cache.get(key))

    # Para un solo segmento se puede optimizar el par conjuntamente, que es la
    # situación más importante y produce la unión visualmente más coherente.
    if len(points) == 2:
        (point_a, normal_a, burial_a,
         point_b, normal_b, burial_b) = _smart_anchor_optimize_pair(
            trees[0], trees[1], points[0], normals[0], points[1], normals[1],
            connector_radius)
        return [point_a, point_b], [normal_a, normal_b], [burial_a, burial_b]

    optimized_points = [point.copy() for point in points]
    optimized_normals = [normal.copy() for normal in normals]
    optimized_burials = [float(REINFORCEMENT_BLEND_OVERLAP_MM)] * len(points)
    passes = max(1, int(REINFORCEMENT_SMART_ANCHOR_COORDINATE_PASSES))
    for _pass_index in range(passes):
        for index in range(len(optimized_points)):
            neighbor_points = []
            if index > 0:
                neighbor_points.append(optimized_points[index - 1])
            if index + 1 < len(optimized_points):
                neighbor_points.append(optimized_points[index + 1])
            candidates = _smart_anchor_generate_candidates(
                trees[index], points[index], normals[index], neighbor_points,
                connector_radius,
                search_radius=float(REINFORCEMENT_SMART_ANCHOR_SEARCH_RADIUS_MM),
                center_override=optimized_points[index])
            if candidates:
                optimized_points[index] = Vector(candidates[0]['point'])
                optimized_normals[index] = Vector(candidates[0]['normal'])
                optimized_burials[index] = float(
                    candidates[0].get('burial_depth', REINFORCEMENT_BLEND_OVERLAP_MM))
    return optimized_points, optimized_normals, optimized_burials


def _fixed_reinforcement_anchor_burials(context, points, normals, support_objects,
                                           connector_radius, surface_cache=None):
    """Mantiene exactamente los puntos elegidos y calcula solo su solape interno.

    No busca candidatos ni desplaza posiciones. La medición estructural se usa
    únicamente para decidir cuánto puede penetrar el collar antes de la UNION.
    """
    pts = [Vector(point) for point in points]
    nrms = [
        _normalized_or_fallback(
            normals[index] if index < len(normals) else (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0))
        for index in range(len(pts))]
    supports = list(support_objects or [])
    cache = surface_cache if surface_cache is not None else {}
    burials = []

    for index, point in enumerate(pts):
        default_burial = float(REINFORCEMENT_BLEND_OVERLAP_MM)
        support = supports[index] if index < len(supports) else None
        if not _valid_obj(support):
            burials.append(default_burial)
            continue
        key = _safe_object_name(support)
        if key not in cache:
            cache[key] = _build_world_surface_bvh(context, support)
        tree = cache.get(key)
        neighbors = []
        if index > 0:
            neighbors.append(pts[index - 1])
        if index + 1 < len(pts):
            neighbors.append(pts[index + 1])
        toward = _smart_anchor_neighbor_direction(point, neighbors)
        _thickness, burial, _coverage = _smart_anchor_structural_metrics(
            tree, point, nrms[index], toward, connector_radius)
        burials.append(max(0.05, float(burial)))

    return pts, nrms, burials


def _smooth_circular_scalars(values, passes=1, weight=0.20):
    result = [float(value) for value in values]
    count = len(result)
    if count < 3:
        return result
    w = max(0.0, min(0.33, float(weight)))
    for _ in range(max(0, int(passes))):
        current = result
        result = [
            current[index] * (1.0 - 2.0 * w)
            + current[(index - 1) % count] * w
            + current[(index + 1) % count] * w
            for index in range(count)
        ]
    return result


def _support_surface_under_candidate(tree, candidate, normal, probe_distance):
    """Comprueba si el candidato está situado sobre alguna cara del soporte.

    Se lanza un rayo en ambas direcciones de la normal desde lados opuestos del
    plano local. Si no aparece ninguna cara, el punto está fuera de la proyección
    del frame y la huella debe contraerse.
    """
    if tree is None:
        return True
    point = Vector(candidate)
    axis = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
    probe = max(0.50, float(probe_distance))
    try:
        hit_a = tree.ray_cast(point + axis * probe, -axis, probe * 2.0 + 0.05)
        if hit_a and hit_a[0] is not None:
            return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        hit_b = tree.ray_cast(point - axis * probe, axis, probe * 2.0 + 0.05)
        if hit_b and hit_b[0] is not None:
            return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False


def _maximum_supported_offset_scale(tree, contact, normal, offset, radius):
    """Mayor fracción del offset cuya proyección sigue dentro del frame."""
    if tree is None or not bool(REINFORCEMENT_BLEND_EDGE_CLIP_ENABLED):
        return 1.0
    vector = Vector(offset)
    if vector.length < 1.0e-8:
        return 1.0

    probe = max(
        float(REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_MIN_MM),
        float(radius) * float(REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_RADIUS_SCALE))
    origin = Vector(contact)
    if _support_surface_under_candidate(tree, origin + vector, normal, probe):
        return 1.0

    low = 0.0
    high = 1.0
    # El centro procede de un clic sobre el soporte; aun así se comprueba para
    # evitar resultados erráticos en mallas abiertas o degeneradas.
    if not _support_surface_under_candidate(tree, origin, normal, probe):
        return 0.0

    for _ in range(max(5, int(REINFORCEMENT_BLEND_EDGE_CLIP_BINARY_STEPS))):
        middle = 0.5 * (low + high)
        candidate = origin + vector * middle
        if _support_surface_under_candidate(tree, candidate, normal, probe):
            low = middle
        else:
            high = middle

    return max(0.0, min(1.0,
        low * float(REINFORCEMENT_BLEND_EDGE_CLIP_SAFETY_SCALE)))


def _all_footprint_points_supported(tree, contact, normal, offsets, scale, radius):
    """Comprueba el aro completo conservando exactamente su forma nominal."""
    if tree is None:
        return True
    probe = max(
        float(REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_MIN_MM),
        float(radius) * float(REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_RADIUS_SCALE))
    center = Vector(contact)
    factor = max(0.0, float(scale))
    for offset in offsets:
        candidate = center + Vector(offset) * factor
        if not _support_surface_under_candidate(tree, candidate, normal, probe):
            return False
    return True


def _maximum_round_footprint_scale(tree, contact, normal, offsets, radius):
    """Mayor escala uniforme que mantiene toda la huella dentro del soporte.

    A diferencia del recorte radial de v6.12.50, aquí todos los radios conservan
    la misma proporción. El volcán puede hacerse menor, pero nunca se deforma ni
    genera lóbulos o lados planos.
    """
    if (tree is None or not bool(REINFORCEMENT_BLEND_ROUND_FIT_ENABLED)
            or not offsets):
        return 1.0

    if _all_footprint_points_supported(
            tree, contact, normal, offsets, 1.0, radius):
        return 1.0

    minimum = max(0.01, min(1.0,
        float(REINFORCEMENT_BLEND_ROUND_FIT_MIN_SCALE)))
    if not _all_footprint_points_supported(
            tree, contact, normal, offsets, minimum, radius):
        # En mallas abiertas o degeneradas mantenemos una huella pequeña pero
        # redonda en vez de fabricar una forma irregular por sectores.
        return minimum

    low = minimum
    high = 1.0
    for _ in range(max(6, int(REINFORCEMENT_BLEND_ROUND_FIT_BINARY_STEPS))):
        middle = 0.5 * (low + high)
        if _all_footprint_points_supported(
                tree, contact, normal, offsets, middle, radius):
            low = middle
        else:
            high = middle

    return max(minimum, min(1.0,
        low * float(REINFORCEMENT_BLEND_ROUND_FIT_SAFETY_SCALE)))


def _adaptive_volcano_footprint_offsets(surface_tree, contact, normal,
                                         major_axis, minor_axis,
                                         foot_major, foot_minor,
                                         segments, volcano_factor, radius):
    """Huella volcánica grande, redonda y contenida mediante escala uniforme.

    Se construye primero la elipse volcánica ideal. Después se calcula una sola
    escala máxima para el aro entero. De esta manera la conexión mantiene su
    redondez y sus proporciones, aunque tenga que reducirse para no salir del
    frame.
    """
    count = max(8, int(segments))
    nominal_offsets = []
    for index in range(count):
        angle = math.tau * index / float(count)
        ca, sa = math.cos(angle), math.sin(angle)
        nominal_offsets.append(
            Vector(major_axis) * (ca * float(foot_major))
            + Vector(minor_axis) * (sa * float(foot_minor)))

    if (surface_tree is None
            or not bool(REINFORCEMENT_BLEND_VOLCANO_ADAPTIVE_FOOTPRINT)):
        return nominal_offsets

    uniform_scale = _maximum_round_footprint_scale(
        surface_tree, contact, normal, nominal_offsets, radius)
    return [offset * uniform_scale for offset in nominal_offsets]


# Removed dead legacy implementation: _legacy_cubic_bezier_point_v1 (no production references in DSG 8.9 audit).


def _cubic_bezier_tangent(p0, p1, p2, p3, t):
    u = 1.0 - float(t)
    tangent = ((p1 - p0) * (3.0 * u * u) +
               (p2 - p1) * (6.0 * u * t) +
               (p3 - p2) * (3.0 * t * t))
    return _normalized_or_fallback(tangent, p3 - p0)


def _microscrew_support_radius_at(t, body_radius, sleeve_neck_radius=None):
    """Conector grueso con apoyo amplio en frame y cuello seguro en el sleeve.

    El cuerpo mantiene el diámetro estructural grande. Solo el último tercio se
    estrecha mediante smootherstep hasta un cuello que no invade el lumen de
    Ø2 mm. En el frame existe una expansión corta para mejorar la futura unión.
    """
    t = max(0.0, min(1.0, float(t)))
    body_radius = max(0.20, float(body_radius))
    if sleeve_neck_radius is None:
        sleeve_neck_radius = body_radius
    sleeve_neck_radius = max(0.20, min(body_radius, float(sleeve_neck_radius)))

    frame_flare = body_radius * float(MICROSCREW_SUPPORT_FRAME_FLARE_SCALE_FIXED)
    if t <= 0.20:
        local = _smootherstep01(t / 0.20)
        return frame_flare + (body_radius - frame_flare) * local

    taper_start = max(0.45, min(0.90, float(MICROSCREW_SUPPORT_SLEEVE_TAPER_START_FIXED)))
    if t >= taper_start:
        local = _smootherstep01((t - taper_start) / max(1.0e-6, 1.0 - taper_start))
        return body_radius + (sleeve_neck_radius - body_radius) * local

    return body_radius


def make_microscrew_smooth_support_mesh(name, start, end, support_radius,
                                        outer_radius, start_tangent=None,
                                        end_tangent=None, segments=24,
                                        sleeve_neck_radius=None):
    """Connector Bézier curvo, cerrado y con tapas enterradas en los solapes."""
    p0 = Vector(start)
    p3 = Vector(end)
    chord = p3 - p0
    length = chord.length
    if length < 0.8:
        return None

    chord_axis = chord.normalized()
    t0 = _normalized_or_fallback(start_tangent, chord_axis)
    t3 = _normalized_or_fallback(end_tangent, chord_axis)

    # Limita la curvatura para evitar bucles cuando los puntos están próximos.
    handle = min(max(length * 0.30, 0.75), 4.0)
    p1 = p0 + t0 * handle
    p2 = p3 - t3 * handle

    segments = max(16, min(64, int(segments)))
    ring_count = max(9, min(18, int(math.ceil(length * 1.35)) + 5))

    centers = []
    tangents = []
    for ring_index in range(ring_count):
        t = ring_index / float(ring_count - 1)
        centers.append(_cubic_bezier_point(p0, p1, p2, p3, t))
        tangents.append(_cubic_bezier_tangent(p0, p1, p2, p3, t))

    # Transporte paralelo aproximado: evita giros repentinos de los anillos.
    x_axis, y_axis, _ = build_axis_basis(tangents[0])
    frames = [(x_axis, y_axis)]
    previous_x = x_axis
    for tangent in tangents[1:]:
        transported_x = previous_x - tangent * previous_x.dot(tangent)
        if transported_x.length < 1e-7:
            transported_x, _fallback_y, _ = build_axis_basis(tangent)
        transported_x.normalize()
        transported_y = tangent.cross(transported_x)
        if transported_y.length < 1e-7:
            transported_x, transported_y, _ = build_axis_basis(tangent)
        else:
            transported_y.normalize()
            transported_x = transported_y.cross(tangent).normalized()
        if transported_x.dot(previous_x) < 0.0:
            transported_x.negate()
            transported_y.negate()
        frames.append((transported_x, transported_y))
        previous_x = transported_x

    vertices = []
    for ring_index, (center, tangent) in enumerate(zip(centers, tangents)):
        t = ring_index / float(ring_count - 1)
        radius = _microscrew_support_radius_at(t, support_radius, sleeve_neck_radius)
        x_axis, y_axis = frames[ring_index]
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            radial = x_axis * math.cos(angle) + y_axis * math.sin(angle)
            point = center + radial * radius
            vertices.append((point.x, point.y, point.z))

    faces = []
    stride = segments
    for level in range(ring_count - 1):
        base = level * stride
        nxt = (level + 1) * stride
        for index in range(segments):
            j = (index + 1) % segments
            faces.append((base + index, base + j, nxt + j, nxt + index))

    # Cierra los dos extremos. Las tapas quedan enterradas dentro del frame y
    # de la pared del sleeve, por lo que no son visibles, pero convierten el
    # conector en un shell manifold antes de irrigación y otros booleanos.
    start_center_index = len(vertices)
    vertices.append((centers[0].x, centers[0].y, centers[0].z))
    end_center_index = len(vertices)
    vertices.append((centers[-1].x, centers[-1].y, centers[-1].z))
    last_ring = (ring_count - 1) * stride
    for index in range(segments):
        j = (index + 1) % segments
        # Tapa inicial: normal opuesta a la tangente de salida.
        faces.append((start_center_index, j, index))
        # Tapa final: normal en el sentido de la tangente de llegada.
        faces.append((end_center_index, last_ring + index, last_ring + j))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    try:
        mesh.validate(clean_customdata=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh.update(calc_edges=True)
    try:
        for poly in mesh.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return mesh


def _microscrew_target_candidates(props, include_frame=False):
    candidates = []
    for obj in (
        getattr(props, 'model_obj', None),
        bpy.data.objects.get(COMBINED_NAME),
        bpy.data.objects.get(BLOCKOUT_NAME),
        getattr(props, 'guide_obj', None),
        getattr(props, 'frame_obj', None) if include_frame else None,
        bpy.data.objects.get(FRAME_NAME) if include_frame else None,
    ):
        if not _valid_obj(obj) or obj.type != 'MESH' or obj in candidates:
            continue
        candidates.append(obj)
    return candidates


def raycast_microscrew_target(context, event, props):
    """Busca el segundo punto en modelo/blockout; usa el frame como fallback."""
    ray_origin, _ray_dir = get_view_ray(context, event)
    if ray_origin is None:
        return None, None, None

    def best_hit(candidates):
        best = None
        for obj in candidates:
            location, normal, _face = do_raycast_detailed(context, event, obj)
            if location is None or normal is None:
                continue
            distance = (Vector(location) - Vector(ray_origin)).length
            if best is None or distance < best[0]:
                best = (distance, Vector(location), Vector(normal), obj)
        return best

    primary = _microscrew_target_candidates(props, include_frame=False)
    hit = best_hit(primary)
    if hit is None:
        frame = getattr(props, 'frame_obj', None)
        if not _valid_obj(frame):
            frame = bpy.data.objects.get(FRAME_NAME)
        hit = best_hit([frame] if _valid_obj(frame) else [])
    if hit is None:
        return None, None, None
    return hit[1], hit[2], hit[3]


def build_microscrew_preview(context, props, point_frame, normal_frame,
                              point_target, normal_target,
                              point_frame_b=None, normal_frame_b=None):
    global _LAST_MICROSCREW_PREVIEW_ERROR
    _LAST_MICROSCREW_PREVIEW_ERROR = ""
    frame_point_a = Vector(point_frame)
    target_point = Vector(point_target)
    frame_normal_a = _normalized_or_fallback(normal_frame, (0.0, 0.0, 1.0))
    sleeve_axis = _normalized_or_fallback(normal_target, (0.0, 0.0, 1.0))

    frame_anchors = [(frame_point_a, frame_normal_a)]
    if point_frame_b is not None:
        frame_point_b = Vector(point_frame_b)
        frame_normal_b = _normalized_or_fallback(normal_frame_b, (0.0, 0.0, 1.0))
        frame_anchors.append((frame_point_b, frame_normal_b))
    else:
        frame_point_b = None

    screw_diameter, screw_length = _microscrew_dimensions_from_props(props)
    height = MICROSCREW_SLEEVE_HEIGHT_MM
    inner_radius = screw_diameter * 0.5
    outer_radius = inner_radius + MICROSCREW_WALL_THICKNESS_MM
    segments = MICROSCREW_CIRCULAR_SEGMENTS_FIXED
    support_radius = MICROSCREW_SUPPORT_DIAMETER_MM_FIXED * 0.5
    sleeve_neck_radius = MICROSCREW_SUPPORT_SLEEVE_NECK_DIAMETER_MM_FIXED * 0.5
    frame_embed = MICROSCREW_FRAME_EMBED_MM_FIXED

    sleeve_center = target_point + sleeve_axis * (height * 0.5)

    lumen_safety = 0.22
    # El cuerpo es grueso, pero la distancia al eje del sleeve se calcula con
    # el cuello final reducido para conservar intacto el lumen de Ø2 mm.
    minimum_center_radius = inner_radius + sleeve_neck_radius + lumen_safety
    attachment_radius = max(minimum_center_radius, outer_radius - 0.30)
    attachment_radius = min(outer_radius - 0.08, attachment_radius)

    support_specs = []
    radial_hints = []
    for frame_point, frame_normal in frame_anchors:
        toward_frame = frame_point - sleeve_center
        radial = toward_frame - sleeve_axis * toward_frame.dot(sleeve_axis)
        if radial.length < 1e-6:
            radial = build_axis_basis(sleeve_axis)[0]
        radial.normalize()
        support_end = sleeve_center + radial * attachment_radius
        support_start = frame_point - frame_normal * (frame_embed + support_radius * 0.55)
        if (support_end - support_start).length < 0.90:
            raise RuntimeError('uno de los conectores del microtornillo es demasiado corto')
        support_specs.append((support_start, support_end, frame_normal, -radial))
        radial_hints.append(radial)

    x_hint = radial_hints[0].copy()
    if len(radial_hints) > 1:
        combined = radial_hints[0] + radial_hints[1]
        if combined.length > 1e-6:
            x_hint = combined.normalized()

    remove_pending_microscrew_geometry_previews()
    remove_pending_microscrew_visuals()
    sleeve_tmp_name = 'DSG_MicroScrewSleeveTmp'
    support_tmp_prefix = 'DSG_MicroScrewSupportTmp'
    safe_remove_by_name(sleeve_tmp_name)
    for idx in range(4):
        safe_remove_by_name(f'{support_tmp_prefix}_{idx}')

    sleeve = None
    supports = []
    preview = None
    try:
        sleeve_mesh = make_microscrew_anatomic_sleeve_mesh(
            sleeve_tmp_name + '_Mesh', segments, screw_diameter)
        sleeve = bpy.data.objects.new(sleeve_tmp_name, sleeve_mesh)
        sleeve.matrix_world = _matrix_along_local_z(sleeve_center, sleeve_axis)
        link_object(context, sleeve)

        combine_objects = [sleeve]
        for idx, (support_start, support_end, support_start_tangent, support_end_tangent) in enumerate(support_specs):
            support_mesh = make_microscrew_smooth_support_mesh(
                f'{support_tmp_prefix}_{idx}_Mesh', support_start, support_end,
                support_radius, outer_radius,
                start_tangent=support_start_tangent,
                end_tangent=support_end_tangent,
                segments=segments,
                sleeve_neck_radius=sleeve_neck_radius)
            if support_mesh is None:
                raise RuntimeError('could not generate one of the microscrew connectors')
            support = bpy.data.objects.new(f'{support_tmp_prefix}_{idx}', support_mesh)
            link_object(context, support)
            supports.append(support)
            combine_objects.append(support)

        preview = build_combined_mesh_object_world(
            context, combine_objects, MICROSCREW_PREVIEW_NAME)
        if not _valid_obj(preview):
            raise RuntimeError('no se pudo combinar la estructura del microtornillo y el sleeve')

        preview = register_dsg_object(
            preview, ROLE_MICROSCREW, MICROSCREW_PREVIEW_NAME, {
                'DSG_microscrew_preview': True,
                'DSG_microscrew_confirmed': False,
                'DSG_microscrew_point_frame': list(frame_point_a),
                'DSG_microscrew_point_frame_a': list(frame_point_a),
                'DSG_microscrew_point_frame_b': list(frame_point_b) if frame_point_b is not None else None,
                'DSG_microscrew_normal_frame_a': list(frame_normal_a),
                'DSG_microscrew_normal_frame_b': list(frame_normal_b) if frame_point_b is not None else None,
                'DSG_microscrew_point_target': list(target_point),
                'DSG_microscrew_normal_target': list(sleeve_axis),
                'DSG_microscrew_axis': list(sleeve_axis),
                'DSG_microscrew_sleeve_height': MICROSCREW_SLEEVE_HEIGHT_MM,
                'DSG_microscrew_inner_diameter': screw_diameter,
                'DSG_microscrew_diameter_mm': screw_diameter,
                'DSG_microscrew_length_mm': screw_length,
                'DSG_microscrew_wall_thickness': MICROSCREW_WALL_THICKNESS_MM,
                'DSG_microscrew_support_diameter': support_radius * 2.0,
                'DSG_microscrew_support_sleeve_neck_diameter': sleeve_neck_radius * 2.0,
                'DSG_microscrew_support_frame_embed': frame_embed,
                'DSG_microscrew_support_count': len(support_specs),
                'DSG_microscrew_union_deferred': True,
                'DSG_microscrew_sleeve_center': list(sleeve_center),
                'DSG_microscrew_sleeve_top': list(target_point + sleeve_axis * height),
                'DSG_microscrew_x_hint': list(x_hint),
                'DSG_microscrew_anatomic_seat': True,
                'DSG_microscrew_seat_depth_mm': MICROSCREW_SEAT_DEPTH_MM,
                'DSG_microscrew_stop_radius_mm': MICROSCREW_STOP_RADIUS_MM * (screw_diameter / MICROSCREW_GUIDED_DIAMETER_MM),
                'DSG_microscrew_soft_transition': True,
                'DSG_microscrew_bezier_transition': True,
                'DSG_microscrew_three_point_support': len(support_specs) >= 2,
            })
        preview.display_type = 'SOLID'
        preview.show_in_front = False
        props.microscrew_preview_obj = preview

        preview_record = _record_from_microscrew_object(preview, 0)
        visual = None
        if preview_record is not None:
            try:
                visual = build_static_microscrew_visual(
                    context, preview_record, MICROSCREW_VISUAL_PREVIEW_NAME,
                    index=0, preview=True)
            except Exception as visual_exc:
                print(f'[DSG] Static microscrew visual warning: {visual_exc}')
        set_active(context, visual if _valid_obj(visual) else preview)
        return preview
    except Exception as exc:
        _LAST_MICROSCREW_PREVIEW_ERROR = str(exc)
        print(f'[DSG] Microscrew preview failed: {exc}')
        if _valid_obj(preview):
            safe_remove_object(preview)
        remove_pending_microscrew_visuals()
        return None
    finally:
        if _valid_obj(sleeve):
            safe_remove_object(sleeve)
        for support in supports:
            if _valid_obj(support):
                safe_remove_object(support)


class DSG_OT_StartMicroscrew(Operator):
    bl_idname = 'dsg.start_microscrew'
    bl_label = 'Select 3 Microscrew Points'
    bl_options = {'REGISTER', 'UNDO'}

    def _marker_name(self, index):
        return f'{MICROSCREW_MARKER_NAME}_{index}'

    def _add_marker(self, context, location, index):
        marker_mesh = make_uv_sphere_mesh(self._marker_name(index) + '_Mesh', 0.55, 16, 8)
        marker = bpy.data.objects.new(self._marker_name(index), marker_mesh)
        marker.location = Vector(location)
        link_object(context, marker)
        register_dsg_object(marker, ROLE_MICROSCREW, self._marker_name(index))
        marker.display_type = 'WIRE'
        marker.show_in_front = True

    def _remove_marker(self):
        safe_remove_by_name(MICROSCREW_MARKER_NAME)
        for index in range(4):
            safe_remove_by_name(self._marker_name(index))

    def _finish(self, context):
        self._remove_marker()
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dsg_props
        frame = _workflow_frame_candidate(props)

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._finish(context)
            _dsg_report(self, {'INFO'}, 'Microscrew placement canceled', 'Colocación del microtornillo cancelada')
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if len(self._points) == 0:
                location, normal, _face = do_raycast_detailed(context, event, frame)
                if location is None or normal is None:
                    _dsg_report(self, {'WARNING'}, 'The first point must be placed on the frame', 'El primer punto debe colocarse sobre la estructura')
                    return {'RUNNING_MODAL'}
                normal = _orient_surface_normal_to_view(context, event, normal)
                self._points.append(Vector(location))
                self._normals.append(Vector(normal))
                self._roles.append('frame')
                self._add_marker(context, self._points[0], 0)
                _dsg_report(self, {'INFO'}, 'First point recorded on the frame. Now select the sleeve base on the model.', 'Primer punto registrado en la estructura. Selecciona ahora la base del cilindro sobre el modelo.')
                return {'RUNNING_MODAL'}

            if len(self._points) == 1:
                location, normal, target_obj = raycast_microscrew_target(context, event, props)
                if location is None or normal is None:
                    _dsg_report(self, {'WARNING'}, 'The second point must be placed on the model, blockout, or frame', 'El segundo punto debe colocarse sobre el modelo, modelo retentivo o estructura')
                    return {'RUNNING_MODAL'}
                normal = _orient_surface_normal_to_view(context, event, normal)
                self._points.append(Vector(location))
                self._normals.append(Vector(normal))
                self._roles.append('target')
                self._target_obj_name = _safe_object_name(target_obj) or 'superficie'
                self._add_marker(context, self._points[1], 1)
                _dsg_report(self, {'INFO'}, 'Second point recorded on the model. Select the third point on the frame to create a second support.', 'Segundo punto registrado en el modelo. Selecciona el tercer punto sobre la estructura para crear un segundo soporte.')
                return {'RUNNING_MODAL'}

            location, normal, _face = do_raycast_detailed(context, event, frame)
            if location is None or normal is None:
                _dsg_report(self, {'WARNING'}, 'The third point must be placed on the frame', 'El tercer punto debe colocarse sobre la estructura')
                return {'RUNNING_MODAL'}
            normal = _orient_surface_normal_to_view(context, event, normal)
            self._points.append(Vector(location))
            self._normals.append(Vector(normal))
            self._roles.append('frame')
            self._add_marker(context, self._points[2], 2)
            preview = build_microscrew_preview(
                context, props,
                self._points[0], self._normals[0],
                self._points[1], self._normals[1],
                self._points[2], self._normals[2])
            self._finish(context)
            if not _valid_obj(preview):
                detail = _LAST_MICROSCREW_PREVIEW_ERROR or 'unknown geometry error'
                _dsg_report(self, {'ERROR'}, f'Could not create the microscrew structure: {detail}', f'No se pudo crear la estructura del microtornillo: {detail}')
                return {'CANCELLED'}
            target_name = self._target_obj_name or 'superficie'
            _dsg_report(self, {'INFO'}, f'Vista previa creada sobre {target_name}: microtornillo Ø{props.microscrew_diameter:.2f} × {props.microscrew_length:.1f} mm, cilindro de 3 mm y conectores Ø{MICROSCREW_SUPPORT_DIAMETER_MM_FIXED:.1f} mm.', f'Vista previa creada sobre {target_name}: microtornillo Ø{props.microscrew_diameter:.2f} × {props.microscrew_length:.1f} mm, cilindro de 3 mm y conectores Ø{MICROSCREW_SUPPORT_DIAMETER_MM_FIXED:.1f} mm.')
            return {'FINISHED'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                          'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
                          'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
                          'NUMPAD_8', 'NUMPAD_9'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not _require_workflow_stage(
                self, context, STEP_FRAME,
                action_en='Cannot place the microscrew',
                action_es='No se puede colocar el microtornillo'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        activate_precision_orthographic(context)
        frame = _workflow_frame_candidate(props)
        if not _valid_obj(frame):
            _dsg_report(self, {'ERROR'}, 'Generate the tubular frame first', 'Genera primero la estructura tubular')
            return {'CANCELLED'}
        if get_pending_microscrew_preview(props):
            _dsg_report(self, {'WARNING'}, 'Confirm or discard the pending microscrew', 'Confirma o descarta el microtornillo pendiente')
            return {'CANCELLED'}
        self._points = []
        self._normals = []
        self._roles = []
        self._target_obj_name = ''
        self._remove_marker()
        context.window_manager.modal_handler_add(self)
        _dsg_report(self, {'INFO'}, 'Select 3 points: frame, model, and frame. Esc cancels.', 'Selecciona 3 puntos: estructura, modelo y estructura. Esc cancela.')
        return {'RUNNING_MODAL'}



def _microscrew_preview_visual_object():
    """Devuelve el STL visual editable del microtornillo pendiente.

    Se prioriza el objeto activo. Si Blender conservó una copia con sufijo
    ``.001``, el usuario normalmente habrá movido esa copia visible; elegir por
    nombre antes que por selección hacía que Actualizar leyera la posición vieja.
    """
    active = bpy.context.view_layer.objects.active if bpy.context and bpy.context.view_layer else None
    if (_valid_obj(active)
            and bool(active.get('DSG_microscrew_visual_preview', False))):
        return active

    visual = bpy.data.objects.get(MICROSCREW_VISUAL_PREVIEW_NAME)
    if (_valid_obj(visual)
            and bool(visual.get('DSG_microscrew_visual_preview', False))):
        return visual

    candidates = []
    for obj in list(bpy.data.objects):
        try:
            if (_valid_obj(obj)
                    and bool(obj.get('DSG_microscrew_visual_preview', False))):
                candidates.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    if candidates:
        candidates.sort(key=lambda obj: (not _object_is_hidden(obj), obj.name), reverse=True)
        return candidates[0]
    return None


def _microscrew_axis_from_visual_or_preview(visual, preview):
    """Extrae el eje actual del microtornillo.

    Si el usuario además de moverlo lo rota, se respeta su eje local Z actual.
    Si no puede calcularse, se mantiene el eje original guardado en el preview.
    """
    if _valid_obj(visual):
        try:
            axis = visual.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
            if axis.length > 1e-8:
                return axis.normalized()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        axis = Vector(preview.get('DSG_microscrew_axis', (0.0, 0.0, 1.0)))
        if axis.length > 1e-8:
            return axis.normalized()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return Vector((0.0, 0.0, 1.0))


def update_pending_microscrew_from_visual(context, props):
    """Recrea el preview usando el microtornillo visual como nuevo punto 2.

    Conserva exactamente los puntos 1 y 3 marcados por el usuario sobre el frame.
    Solo cambia el punto 2: se recalcula desde la posición actual del
    microtornillo visual. Esto permite revisar con cortes DICOM, mover el
    microtornillo y actualizar la geometría del sleeve/conectores sin repetir los
    3 clics.
    """
    preview = get_pending_microscrew_preview(props)
    if not _valid_obj(preview):
        return None, 'No hay microtornillo pendiente para actualizar'

    visual = _microscrew_preview_visual_object()
    if not _valid_obj(visual):
        return None, 'No se encontró el microtornillo visual editable'

    try:
        point_frame_a = Vector(preview.get('DSG_microscrew_point_frame_a'))
        point_frame_b_raw = preview.get('DSG_microscrew_point_frame_b')
        if point_frame_b_raw is None:
            return None, 'Este microtornillo no tiene tercer punto guardado'
        point_frame_b = Vector(point_frame_b_raw)
    except Exception:
        return None, 'No se pudieron recuperar los puntos 1 y 3 originales'

    normal_frame_a = _normalized_or_fallback(
        preview.get('DSG_microscrew_normal_frame_a', (0.0, 0.0, 1.0)),
        (0.0, 0.0, 1.0))
    normal_frame_b = _normalized_or_fallback(
        preview.get('DSG_microscrew_normal_frame_b', normal_frame_a),
        normal_frame_a)

    axis = _microscrew_axis_from_visual_or_preview(visual, preview)

    # build_static_microscrew_visual coloca el origen del STL visual en
    # sleeve_top. Por tanto, el nuevo punto 2 clínico/base del sleeve es
    # sleeve_top - eje * altura_sleeve.
    try:
        sleeve_top = Vector(visual.matrix_world.translation)
    except Exception:
        sleeve_top = Vector(preview.get('DSG_microscrew_sleeve_top', (0.0, 0.0, 0.0)))
    sleeve_height = float(preview.get('DSG_microscrew_sleeve_height', MICROSCREW_SLEEVE_HEIGHT_MM))
    point_target = sleeve_top - axis * sleeve_height

    # Any previously generated animation now points to the old trajectory.
    # Remove it before rebuilding so no frozen copy can survive in the scene.
    invalidate_microscrew_animation(context)

    rebuilt = build_microscrew_preview(
        context, props,
        point_frame_a, normal_frame_a,
        point_target, axis,
        point_frame_b, normal_frame_b)
    if not _valid_obj(rebuilt):
        detail = _LAST_MICROSCREW_PREVIEW_ERROR or 'error geométrico desconocido'
        return None, detail
    return rebuilt, None


class DSG_OT_UpdateMicroscrewFromVisual(Operator):
    bl_idname = 'dsg.update_microscrew_from_visual'
    bl_label = 'Update Microscrew From Visual'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        rebuilt, error = update_pending_microscrew_from_visual(context, props)
        if error:
            _dsg_report(
                self, {'ERROR'},
                f'Could not update microscrew: {error}',
                f'No se pudo actualizar el microtornillo: {error}')
            return {'CANCELLED'}
        _dsg_report(
            self, {'INFO'},
            'Microscrew updated: point 2 was moved to the current visual screw position; points 1 and 3 were preserved.',
            'Microtornillo actualizado: el punto 2 se movió a la posición actual del tornillo visual; los puntos 1 y 3 se conservaron.')
        return {'FINISHED'}

def confirm_pending_microscrew_object(context, props):
    """Convierte el preview pendiente en microtornillo confirmado.

    Devuelve ``(objeto, índice, error)``. Se usa tanto por el operador histórico
    de confirmar como por la nueva acción única confirmar + incorporar al frame.
    """
    preview = get_pending_microscrew_preview(props)
    if not _valid_obj(preview):
        return None, -1, 'There is no pending microscrew'

    # Adding or confirming a placement changes the animation record set.
    invalidate_microscrew_animation(context)
    remove_pending_microscrew_geometry_previews(keep=preview)
    records = get_microscrew_records(props)
    index = len(records)
    name = f'{MICROSCREW_PREFIX}{index:02d}'
    safe_remove_by_name(name)
    preview.name = name
    if getattr(preview, 'data', None) is not None:
        preview.data.name = name + '_Mesh'
    preview['DSG_microscrew_preview'] = False
    preview['DSG_microscrew_confirmed'] = True
    preview['DSG_microscrew_index'] = index
    preview.display_type = 'SOLID'
    preview.show_in_front = False
    link_object_to_dsg_collection(preview, ROLE_MICROSCREW)
    props.microscrew_preview_obj = None

    record = _record_from_microscrew_object(preview, index)
    if record is None:
        return None, -1, 'Could not save the microscrew placement'
    records.append(record)
    set_microscrew_records(props, records)
    visual = bpy.data.objects.get(MICROSCREW_VISUAL_PREVIEW_NAME)
    if _valid_obj(visual):
        new_visual_name = f'{MICROSCREW_VISUAL_PREFIX}{index:02d}'
        safe_remove_by_name(new_visual_name)
        visual.name = new_visual_name
        if getattr(visual, 'data', None) is not None:
            visual.data.name = new_visual_name + '_Mesh'
        visual['DSG_microscrew_visual_preview'] = False
        visual['DSG_microscrew_index'] = index
        link_object_to_dsg_collection(visual, ROLE_MICROSCREW_VISUAL)
    else:
        try:
            record_for_visual = _record_from_microscrew_object(preview, index)
            if record_for_visual is not None:
                visual = build_static_microscrew_visual(
                    context, record_for_visual, f'{MICROSCREW_VISUAL_PREFIX}{index:02d}',
                    index=index, preview=False)
        except Exception as visual_exc:
            print(f'[DSG] Could not create confirmed microscrew visual: {visual_exc}')

    props.microscrew_count = len(get_confirmed_microscrew_objects())
    set_active(context, visual if _valid_obj(visual) else preview)
    return preview, index, None


class DSG_OT_ConfirmMicroscrewPreview(Operator):
    bl_idname = 'dsg.confirm_microscrew_preview'
    bl_label = 'Confirm Microscrew'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if core.reject_external_agent_for_user_gate(self, action=self.bl_idname):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        preview, index, error = confirm_pending_microscrew_object(context, props)
        if error:
            _dsg_report(self, {'WARNING'}, error, error)
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, f'Microtornillo {index + 1} confirmado. Puedes colocar otro.', f'Microtornillo {index + 1} confirmado. Puedes colocar otro.')
        return {'FINISHED'}


class DSG_OT_CancelMicroscrewPreview(Operator):
    bl_idname = 'dsg.cancel_microscrew_preview'
    bl_label = 'Discard Pending Microscrew'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        preview = get_pending_microscrew_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'WARNING'}, 'There is no pending microscrew', 'No hay un microtornillo pendiente')
            return {'CANCELLED'}
        safe_remove_object(preview)
        remove_pending_microscrew_geometry_previews()
        remove_pending_microscrew_visuals()
        props.microscrew_preview_obj = None
        _dsg_report(self, {'INFO'}, 'Pending microscrew discarded', 'Microtornillo pendiente descartado')
        return {'FINISHED'}


class DSG_OT_RemoveLastMicroscrew(Operator):
    bl_idname = 'dsg.remove_last_microscrew'
    bl_label = 'Delete Last Microscrew'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        objects = get_confirmed_microscrew_objects()
        if not objects:
            _dsg_report(self, {'WARNING'}, 'There are no confirmed microscrews', 'No hay microtornillos confirmados')
            return {'CANCELLED'}
        # Indexes and timing change after a deletion; discard the whole old
        # microscrew animation instead of leaving renamed/static remnants.
        invalidate_microscrew_animation(context)
        removed_index = int(objects[-1].get('DSG_microscrew_index', len(objects) - 1))
        safe_remove_object(objects[-1])
        records = get_microscrew_records(props)
        records = [item for item in records if int(item.get('index', -1)) != removed_index]
        for new_index, item in enumerate(records):
            item['index'] = new_index
        set_microscrew_records(props, records)
        safe_remove_by_name(f'{MICROSCREW_VISUAL_PREFIX}{removed_index:02d}')
        # Reindex the visible static microscrews so object names and record indexes stay aligned.
        for new_index, item in enumerate(records):
            old_index = int(item.get('index', new_index))
            old_name = f'{MICROSCREW_VISUAL_PREFIX}{old_index:02d}'
            visual = bpy.data.objects.get(old_name)
            if _valid_obj(visual):
                new_name = f'{MICROSCREW_VISUAL_PREFIX}{new_index:02d}'
                if old_name != new_name:
                    safe_remove_by_name(new_name)
                    visual.name = new_name
                    if getattr(visual, 'data', None) is not None:
                        visual.data.name = new_name + '_Mesh'
                visual['DSG_microscrew_index'] = new_index
        props.microscrew_count = len(get_confirmed_microscrew_objects())
        _dsg_report(self, {'INFO'}, 'Last microscrew deleted', 'Último microtornillo eliminado')
        return {'FINISHED'}


class DSG_OT_ApplyMicroscrewsToFrame(Operator):
    bl_idname = 'dsg.apply_microscrews_to_frame'
    bl_label = 'Add Microscrews to Frame'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        auto_confirmed = False
        pending = get_pending_microscrew_preview(props)
        if _valid_obj(pending):
            rebuilt, sync_error = update_pending_microscrew_from_visual(context, props)
            if sync_error:
                _dsg_report(
                    self, {'ERROR'},
                    f'Could not synchronize the moved microscrew: {sync_error}',
                    f'No se pudo sincronizar el microtornillo movido: {sync_error}')
                return {'CANCELLED'}
            pending = rebuilt
            _preview, _index, error = confirm_pending_microscrew_object(context, props)
            if error:
                _dsg_report(self, {'ERROR'}, error, error)
                return {'CANCELLED'}
            auto_confirmed = True

        frame = _workflow_frame_candidate(props)
        objects = get_confirmed_microscrew_objects()
        if not _valid_obj(frame):
            _dsg_report(self, {'ERROR'}, 'Frame not found', 'No se encontró la estructura')
            return {'CANCELLED'}
        if not objects:
            _dsg_report(self, {'ERROR'}, 'There are no confirmed microscrews', 'No hay microtornillos confirmados')
            return {'CANCELLED'}

        safe_remove_by_name(MICROSCREW_FRAME_COMBINED_TMP_NAME)
        combined = build_combined_mesh_object_world(
            context, [frame] + objects, MICROSCREW_FRAME_COMBINED_TMP_NAME)
        if not _valid_obj(combined):
            _dsg_report(self, {'ERROR'}, 'Could not add the geometry to the frame', 'No se pudo incorporar la geometría a la estructura')
            return {'CANCELLED'}

        count = len(objects)
        old_frame_name = _safe_object_name(frame)
        if old_frame_name:
            safe_remove_by_name(old_frame_name)
        for obj in objects:
            safe_remove_object(obj)

        combined.name = FRAME_NAME
        combined.data.name = FRAME_NAME + '_Mesh'
        combined['DSG_microscrew_count'] = len(get_microscrew_records(props))
        combined['DSG_microscrew_sleeve_height'] = MICROSCREW_SLEEVE_HEIGHT_MM
        dimension_records = get_microscrew_records(props)
        combined['DSG_microscrew_dimensions_json'] = json.dumps([
            {'diameter': float(item.get('diameter', item.get('guided_diameter', MICROSCREW_DIAMETER_DEFAULT_MM))),
             'length': float(item.get('length', MICROSCREW_LENGTH_DEFAULT_MM))}
            for item in dimension_records
        ], separators=(',', ':'))
        maximum_microscrew_diameter = max(
            [float(item.get('diameter', item.get('guided_diameter', MICROSCREW_DIAMETER_DEFAULT_MM)))
             for item in dimension_records] or [MICROSCREW_DIAMETER_DEFAULT_MM])
        combined['DSG_microscrew_inner_diameter'] = maximum_microscrew_diameter
        combined['DSG_microscrew_wall_thickness'] = MICROSCREW_WALL_THICKNESS_MM
        combined['DSG_microscrew_anatomic_seat'] = True
        combined['DSG_microscrew_seat_depth_mm'] = MICROSCREW_SEAT_DEPTH_MM
        combined['DSG_microscrew_stop_radius_mm'] = (
            MICROSCREW_STOP_RADIUS_MM
            * maximum_microscrew_diameter / MICROSCREW_GUIDED_DIAMETER_MM)
        combined['DSG_microscrew_union_deferred'] = True
        combined.display_type = 'SOLID'
        combined.show_in_front = False
        props.frame_obj = register_dsg_object(combined, ROLE_FRAME, FRAME_NAME)
        props.microscrew_count = 0
        props.microscrew_preview_obj = None
        set_active(context, combined)
        action_text = 'confirmado(s) e incorporado(s)' if auto_confirmed else 'incorporado(s)'
        _dsg_report(self, {'INFO'}, f'{count} microscrew(s) {action_text} to the frame with a smooth Bezier transition; final fusion will occur during the final remesh', f'{count} microtornillo(s) {action_text} a la estructura con transición Bézier suave; la fusión definitiva se hará en el remesh final')
        return {'FINISHED'}


class DSG_OT_CreateAnimatedMicroscrews(Operator):
    bl_idname = 'dsg.create_animated_microscrews'
    bl_label = 'Create Animated Screws'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        # Valores clínicos predefinidos: ya no se muestran en la interfaz.
        props.microscrew_animation_distance = 15.0
        props.microscrew_animation_start_frame = 1
        props.microscrew_animation_end_frame = 60
        records = get_microscrew_records(props)
        if not records:
            records = []
            for obj in get_confirmed_microscrew_objects():
                record = _record_from_microscrew_object(obj)
                if record is not None:
                    records.append(record)
            if records:
                set_microscrew_records(props, records)
        if not records:
            _dsg_report(self, {'ERROR'}, 'No microscrew sleeves are registered', 'No hay cilindros de microtornillo registrados')
            return {'CANCELLED'}

        remove_animated_microscrews(restore_static=True)
        created = []
        try:
            base_start = int(props.microscrew_animation_start_frame)
            duration = max(1, int(props.microscrew_animation_end_frame) - base_start)
            item_gap = ANIMATION_ITEM_STAGGER_FRAMES_FIXED
            item_stride = duration + item_gap
            for index, record in enumerate(records):
                record['index'] = index
                item_start = base_start + index * item_stride
                item_end = item_start + duration
                obj = build_animated_microscrew(
                    context, props, record, index,
                    start_frame_override=item_start,
                    end_frame_override=item_end)
                if not _valid_obj(obj):
                    raise RuntimeError(f'Could not create screw {index + 1}')
                created.append(obj)
            set_microscrew_records(props, records)
            # Planning STL screws are references only. Keeping them visible
            # creates apparently frozen duplicates beside the animated screws.
            set_static_microscrew_visuals_hidden(True)
            start_frame = base_start
            end_frame = base_start + len(records) * duration + max(0, len(records) - 1) * item_gap
            context.scene.frame_start = start_frame
            context.scene.frame_end = end_frame
            context.scene.frame_set(start_frame)
            if created:
                set_active(context, created[0])
            _dsg_report(self, {'INFO'}, f'{len(created)} STL screw(s) created with their saved diameter and length; axis matches the sleeve and conical stop seats at frame {end_frame}.', f'{len(created)} tornillo(s) STL creado(s) con su diámetro y longitud guardados; eje idéntico al cilindro y tope cónico en el fotograma {end_frame}.')
            return {'FINISHED'}
        except Exception as exc:
            remove_animated_microscrews(restore_static=True)
            _dsg_report(self, {'ERROR'}, f'Could not prepare the animation: {exc}', f'No se pudo preparar la animación: {exc}')
            return {'CANCELLED'}


class DSG_OT_PlayAnimatedMicroscrews(Operator):
    bl_idname = 'dsg.play_animated_microscrews'
    bl_label = 'Play Microscrew Insertion'

    def execute(self, context):
        props = context.scene.dsg_props
        objects = get_animated_microscrew_objects()
        if not objects:
            _dsg_report(self, {'WARNING'}, 'Create the animated screws first', 'Primero crea los tornillos animados')
            return {'CANCELLED'}
        set_static_microscrew_visuals_hidden(True)
        for obj in objects:
            # hide_viewport is animated per screw; do not force every staggered
            # item visible before its own reveal frame.
            obj.hide_select = False
            obj.hide_set(False)
        start_frame = min(
            int(obj.get('DSG_animation_start_frame',
                        props.microscrew_animation_start_frame))
            for obj in objects)
        end_frame = max(
            int(obj.get('DSG_animation_end_frame',
                        props.microscrew_animation_end_frame))
            for obj in objects)
        end_frame = max(start_frame + 1, end_frame)
        context.scene.frame_start = start_frame
        context.scene.frame_end = end_frame
        context.scene.frame_set(start_frame)
        try:
            bpy.ops.screen.animation_play()
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not play the animation: {exc}', f'No se pudo reproducir la animación: {exc}')
            return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_StopAnimatedMicroscrews(Operator):
    bl_idname = 'dsg.stop_animated_microscrews'
    bl_label = 'Stop Microscrew Animation'

    def execute(self, context):
        props = context.scene.dsg_props
        if not get_animated_microscrew_objects():
            _dsg_report(self, {'WARNING'}, 'Create the animated screws first', 'Primero crea los tornillos animados')
            return {'CANCELLED'}
        try:
            if context.screen and context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
        except Exception:
            try:
                bpy.ops.screen.animation_cancel()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        objects = get_animated_microscrew_objects()
        start_frame = min(
            int(obj.get('DSG_animation_start_frame',
                        props.microscrew_animation_start_frame))
            for obj in objects)
        context.scene.frame_set(start_frame)
        _dsg_report(self, {'INFO'}, 'Animation stopped and screws returned to the start', 'Animación detenida y tornillos devueltos al inicio')
        return {'FINISHED'}


class DSG_OT_ToggleAnimatedMicroscrewsVisibility(Operator):
    bl_idname = 'dsg.toggle_animated_microscrews_visibility'
    bl_label = 'Show or Hide Animated Microscrews'

    def execute(self, context):
        objects = get_animated_microscrew_objects()
        if not objects:
            _dsg_report(self, {'WARNING'}, 'Create the animated screws first', 'Primero crea los tornillos animados')
            return {'CANCELLED'}
        hide = any(not _object_is_hidden(obj) for obj in objects)
        if hide:
            try:
                if context.screen and context.screen.is_animation_playing:
                    bpy.ops.screen.animation_cancel(restore_frame=False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        for obj in objects:
            obj.hide_viewport = hide
            obj.hide_select = hide
            try:
                obj.hide_set(hide)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _dsg_report(self, {'INFO'}, 'Screws hidden' if hide else 'Screws shown', 'Tornillos ocultados' if hide else 'Tornillos mostrados')
        return {'FINISHED'}


class DSG_OT_ShowAnimatedMicroscrewStart(Operator):
    bl_idname = 'dsg.show_animated_microscrew_start'
    bl_label = 'Show Microscrew Start Position'

    def execute(self, context):
        props = context.scene.dsg_props
        if not get_animated_microscrew_objects():
            _dsg_report(self, {'WARNING'}, 'Create the animated screws first', 'Primero crea los tornillos animados')
            return {'CANCELLED'}
        objects = get_animated_microscrew_objects()
        start_frame = min(
            int(obj.get('DSG_animation_start_frame',
                        props.microscrew_animation_start_frame))
            for obj in objects)
        context.scene.frame_set(start_frame)
        return {'FINISHED'}


class DSG_OT_ShowAnimatedMicroscrewStop(Operator):
    bl_idname = 'dsg.show_animated_microscrew_stop'
    bl_label = 'Show Microscrew Final Seat'

    def execute(self, context):
        props = context.scene.dsg_props
        if not get_animated_microscrew_objects():
            _dsg_report(self, {'WARNING'}, 'Create the animated screws first', 'Primero crea los tornillos animados')
            return {'CANCELLED'}
        objects = get_animated_microscrew_objects()
        end_frame = max(
            int(obj.get('DSG_animation_end_frame',
                        props.microscrew_animation_end_frame))
            for obj in objects)
        context.scene.frame_set(max(
            int(props.microscrew_animation_start_frame) + 1,
            end_frame))
        return {'FINISHED'}


class DSG_OT_ConfirmTubeFrame(Operator):
    bl_idname = "dsg.confirm_tube_frame"
    bl_label  = "Confirm Frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_FRAME,
                action_en='Cannot confirm the frame',
                action_es='No se puede confirmar la estructura'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        frame = _workflow_frame_candidate(props)
        if not _valid_obj(frame):
            _dsg_report(self, {'ERROR'}, "Generate the frame first", "Genera primero la estructura")
            return {'CANCELLED'}
        props.frame_obj = frame
        if get_pending_microscrew_preview(props):
            _dsg_report(self, {'ERROR'}, "Confirm or discard the pending microscrew", "Confirma o descarta el microtornillo pendiente")
            return {'CANCELLED'}
        if get_confirmed_microscrew_objects():
            _dsg_report(self, {'ERROR'}, "Incorpora los microtornillos confirmados a la estructura antes de continuar", "Incorpora los microtornillos confirmados a la estructura antes de continuar")
            return {'CANCELLED'}

        frame_signature = _workflow_object_signature(props.frame_obj)
        if _workflow_signature_changed(context.scene, WORKFLOW_FRAME_SIGNATURE_KEY, frame_signature):
            _invalidate_workflow_after(context, STEP_FRAME, reason='frame_changed')
        _workflow_store_signature(context.scene, WORKFLOW_FRAME_SIGNATURE_KEY, frame_signature)

        # User-visible transition Step 4 (Microscrew) -> Step 5 (Sleeves):
        # close the temporary DICOM plane review and return to the normal solid
        # guide view before the next panel is shown.
        _close_dicom_review_for_guide(context)
        try:
            props.frame_obj['DSG_frame_confirmed'] = True
            props.frame_obj['DSG_frame_confirmed_version'] = '8.0.88'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        props.current_step = STEP_SLEEVE
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Paso 7 — Sleeve
# ─────────────────────────────────────────────────────────────

def get_sleeve_preview_objects():
    previews = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not obj.name.startswith(SLEEVE_PREFIX + '_'):
            continue
        if '_Inner_Tmp_' in obj.name or obj.name.startswith('DSG_SleeveApplyTmp_'):
            continue
        if bool(obj.get('DSG_sleeve_preview', False)):
            previews.append(obj)
    return sorted(previews, key=lambda item: item.name)


def _archive_current_guide_for_sleeve_rebuild(props, reason='sleeve_rebuild'):
    """Aparta la guía actual sin destruir IDs durante una regeneración.

    La guía puede estar referenciada por Scene.dsg_props y por el historial de
    Undo. Renombrarla y ocultarla mantiene válidos esos enlaces mientras se crea
    la nueva guía. Solo Reset elimina posteriormente estos objetos archivados.
    """
    guide = bpy.data.objects.get(GUIDE_NAME)
    if not _valid_obj(guide):
        return None
    _sanitize_dsg_object_for_id_change(guide)
    try:
        guide.name = f'DSG_ArchivedGuide_{int(time.time() * 1000)}'
        guide['DSG_obsolete_hidden'] = True
        guide['DSG_archive_reason'] = str(reason)
        guide.hide_render = True
        guide.hide_select = True
        guide.hide_viewport = True
        guide.hide_set(True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if getattr(props, 'guide_obj', None) is guide:
            props.guide_obj = None
        if getattr(props, 'dct_object_being_cut', None) is guide:
            props.dct_object_being_cut = None
        if getattr(props, 'dct_object_making_cut', None) is guide:
            props.dct_object_making_cut = None
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return guide


def _recover_frame_source_for_sleeve_rebuild(props):
    """Devuelve el frame clínico aunque ya se hubiera aplicado una guía."""
    candidates = (
        getattr(props, 'frame_obj', None),
        bpy.data.objects.get(FRAME_NAME),
        bpy.data.objects.get(SLEEVE_SOURCE_FRAME_NAME),
    )
    frame = next((obj for obj in candidates if _valid_obj(obj)), None)
    if not _valid_obj(frame):
        return None
    try:
        frame.name = FRAME_NAME
        frame['DSG_hidden_source'] = False
        frame.hide_render = False
        frame.hide_select = False
        frame.hide_viewport = False
        frame.hide_set(False)
        props.frame_obj = frame
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return frame


class DSG_OT_ToggleLateralOpening(Operator):
    """Legacy id kept so old .blend/keymaps do not break registration."""
    bl_idname = 'dsg.toggle_lateral_opening'
    bl_label = 'Lateral Opening (moved)'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        # v8.4.3: never let a legacy call mutate sleeve geometry/state before
        # irrigation. The dedicated post-irrigation operator is the only writer.
        if int(getattr(props, 'current_step', STEP_MODEL)) != STEP_IRRIGATION:
            _dsg_report(
                self, {'ERROR'},
                'Lateral opening moved after Irrigation',
                'La apertura lateral se realiza después de Irrigación')
            return {'CANCELLED'}
        guide = get_active_guide_obj(props)
        resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper() if _valid_obj(guide) else ''
        if resolution not in {'APPLIED', 'SKIPPED'}:
            _dsg_report(
                self, {'ERROR'},
                'Resolve irrigation first',
                'Resuelve primero la irrigación')
            return {'CANCELLED'}
        return bpy.ops.dsg.apply_post_irrigation_lateral_opening('EXEC_DEFAULT')


class DSG_OT_CaptureLateralOpeningView(Operator):
    """Legacy direction capture, allowed only in the post-irrigation sub-stage."""
    bl_idname = 'dsg.capture_lateral_opening_view'
    bl_label = 'Use Current View for Post-Irrigation Opening'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper() if _valid_obj(guide) else ''
        if (int(getattr(props, 'current_step', STEP_MODEL)) != STEP_IRRIGATION
                or resolution not in {'APPLIED', 'SKIPPED'}):
            _dsg_report(
                self, {'ERROR'},
                'Direction can only be captured after irrigation is resolved',
                'La dirección solo puede capturarse después de resolver la irrigación')
            return {'CANCELLED'}
        direction = -_current_view_forward_world(context)
        props.sleeve_lateral_opening_direction = (
            float(direction.x), float(direction.y), float(direction.z))
        props.sleeve_lateral_opening_last_mode = 'POST_IRRIGATION_VIEW'
        return {'FINISHED'}



LATERAL_WINDOW_PICK_MARKER_PREFIX = 'DSG_LateralWindowPick_'


def _lateral_window_manual_angle_map(props):
    """Return the per-implant manual window angles saved in Scene properties."""
    try:
        raw = json.loads(str(getattr(props, 'sleeve_lateral_opening_manual_json', '{}') or '{}'))
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        try:
            out[str(key)] = _normalize_angle_2pi(float(value))
        except Exception:
            continue
    return out


def _store_lateral_window_manual_angle_map(props, values):
    clean = {}
    for key, value in dict(values or {}).items():
        try:
            clean[str(key)] = float(_normalize_angle_2pi(float(value)))
        except Exception:
            continue
    props.sleeve_lateral_opening_manual_json = json.dumps(clean, separators=(',', ':'))
    return clean


def _remove_lateral_window_pick_markers(implant_name=None):
    wanted = str(implant_name or '')
    for obj in list(bpy.data.objects):
        try:
            if not bool(obj.get('DSG_lateral_window_pick', False)):
                continue
            if wanted and str(obj.get('DSG_implant', '')) != wanted:
                continue
        except Exception:
            continue
        safe_remove_object(obj)


def _clear_lateral_window_manual_picks(props, remove_markers=True):
    try:
        props.sleeve_lateral_opening_manual_json = '{}'
        props.sleeve_lateral_opening_last_mode = 'USER_PICK_REQUIRED'
        props.sleeve_lateral_opening_rotation = 0.0
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if remove_markers:
        _remove_lateral_window_pick_markers()


def _lateral_window_manual_selection_status(props):
    implants = get_all_implant_objects(props)
    names = [_safe_object_name(item) for item in implants if is_valid_implant_obj(item)]
    values = _lateral_window_manual_angle_map(props)
    selected = sum(1 for name in names if name and name in values)
    return int(selected), int(len(names))


def _create_lateral_window_pick_marker(context, props, implant_obj, center_angle):
    """Create a tiny non-destructive arrow showing the user's chosen drill-entry side."""
    if not is_valid_implant_obj(implant_obj):
        return None
    implant_name = _safe_object_name(implant_obj) or ''
    _remove_lateral_window_pick_markers(implant_name)
    try:
        sleeve_mx = get_sleeve_matrix_world(props, implant_obj)
        inner_r = _sleeve_inner_radius_from_props(props)
        outer_r = inner_r + float(getattr(props, 'sleeve_wall', 1.5))
        local_radial = Vector((math.cos(center_angle), math.sin(center_angle), 0.0))
        local_tangent = Vector((-math.sin(center_angle), math.cos(center_angle), 0.0))
        radial = _normalized_or_fallback(sleeve_mx.to_3x3() @ local_radial, (1.0, 0.0, 0.0))
        tangent = _normalized_or_fallback(sleeve_mx.to_3x3() @ local_tangent, (0.0, 1.0, 0.0))
        axis = _normalized_or_fallback(sleeve_mx.to_3x3() @ Vector((0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
        marker = bpy.data.objects.new(
            f'{LATERAL_WINDOW_PICK_MARKER_PREFIX}{implant_name or "Implant"}', None)
        marker.empty_display_type = 'ARROWS'
        marker.empty_display_size = max(1.4, float(inner_r) * 0.75)
        orientation = Matrix((radial, tangent, axis)).transposed().to_4x4()
        orientation.translation = sleeve_mx.translation + radial * (outer_r + 0.65)
        marker.matrix_world = orientation
        marker.show_in_front = True
        marker.hide_render = True
        marker['DSG_lateral_window_pick'] = True
        marker['DSG_implant'] = implant_name
        marker['DSG_lateral_window_angle_rad'] = float(center_angle)
        link_object(context, marker)
        return marker
    except Exception:
        return None


def _signed_angle_delta(a, b):
    return math.atan2(math.sin(float(a) - float(b)), math.cos(float(a) - float(b)))


def _resolve_user_lateral_window_for_implant(context, props, implant_obj,
                                               sleeve_matrix, outer_radius,
                                               inner_diameter):
    """Validate the exact user-picked side, keeping irrigation geometry protected.

    The user, not DSG, chooses the side that offers the best drill access in a
    restricted mouth opening.  DSG still acts as a guardrail: when an irrigation
    channel is present, the chosen exact-width slot must fit inside the largest
    free sector.  It is never silently rotated or narrowed.
    """
    name = _safe_object_name(implant_obj) or ''
    values = _lateral_window_manual_angle_map(props)
    if not name or name not in values:
        return {
            'valid': False,
            'mode': 'USER_PICK_REQUIRED',
            'message': f'mark the lateral drill-entry side on {name or "the sleeve"}',
        }

    rotation = math.radians(float(getattr(props, 'sleeve_lateral_opening_rotation', 0.0)))
    picked_center = float(values[name])
    center = _normalize_angle_2pi(picked_center + rotation)
    outer_radius = max(0.10, float(outer_radius))
    inner_diameter = max(0.40, float(inner_diameter))
    ratio = min(0.94, inner_diameter / max(2.0 * outer_radius, 1.0e-6))
    requested_half = max(math.radians(6.0), min(math.radians(75.0), math.asin(ratio)))
    entries = _sleeve_window_entries_for_implant(props, implant_obj)

    if entries:
        auto = _resolve_lateral_window_for_implant(
            context, props, implant_obj, sleeve_matrix, outer_radius)
        if not bool(auto.get('valid', False)):
            return {
                'valid': False,
                'mode': 'USER_PICK_IRRIGATION_CONFLICT',
                'message': str(auto.get('message', 'no safe irrigation-free sector remains')),
            }
        if bool(auto.get('width_reduced', False)):
            return {
                'valid': False,
                'mode': 'USER_PICK_IRRIGATION_CONFLICT',
                'message': (
                    f'the irrigation-free sector is narrower than the '
                    f'{inner_diameter:.2f} mm sleeve lumen'),
            }

        automatic_center = float(auto.get('automatic_center_angle', auto.get('center_angle', 0.0)))
        free_span = float(auto.get('free_span_rad', 0.0))
        side_margin = max(
            math.radians(4.0),
            float(SLEEVE_WINDOW_MIN_SIDE_WALL_MM_FIXED) / outer_radius)
        allowed_offset = max(0.0, free_span * 0.5 - requested_half - side_margin)
        delta = abs(_signed_angle_delta(center, automatic_center))
        if delta > allowed_offset + math.radians(0.75):
            return {
                'valid': False,
                'mode': 'USER_PICK_IRRIGATION_CONFLICT',
                'free_span_rad': float(free_span),
                'message': (
                    'the selected side intersects the protected irrigation sector; '
                    'click another side of the sleeve with more free space'),
            }
        free_span_deg = math.degrees(free_span)
        mode = 'USER_PICKED_IRRIGATION_SAFE'
    else:
        free_span_deg = 360.0
        mode = 'USER_PICKED_SIDE'

    return {
        'valid': True,
        'mode': mode,
        'center_angle': float(center),
        'picked_center_angle': float(picked_center),
        'half_angle': float(requested_half),
        'requested_width_mm': float(inner_diameter),
        'actual_width_mm': float(inner_diameter),
        'free_span_rad': math.radians(float(free_span_deg)),
        'manual_rotation_requested_deg': math.degrees(rotation),
        'manual_rotation_applied_deg': math.degrees(rotation),
        'width_reduced': False,
        'message': 'user-picked drill-entry side',
    }


class DSG_OT_PickLateralOpeningSide(Operator):
    """Let the clinician click the sleeve side with the best lateral drill access."""
    bl_idname = 'dsg.pick_lateral_opening_side'
    bl_label = 'Pick Lateral Opening Side'
    bl_options = {'REGISTER', 'UNDO'}

    def _restore_cursor(self, context):
        try:
            context.window.cursor_modal_restore()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    def invoke(self, context, event):
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper() if _valid_obj(guide) else ''
        if (int(getattr(props, 'current_step', STEP_MODEL)) != STEP_IRRIGATION
                or resolution not in {'APPLIED', 'SKIPPED'}):
            _dsg_report(
                self, {'ERROR'},
                'Resolve irrigation before positioning the lateral opening',
                'Resuelve la irrigación antes de colocar la apertura lateral')
            return {'CANCELLED'}
        if not get_all_implant_objects(props):
            _dsg_report(self, {'ERROR'}, 'No implants found', 'No se encontraron implantes')
            return {'CANCELLED'}
        try:
            context.window.cursor_modal_set('CROSSHAIR')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.window_manager.modal_handler_add(self)
        selected, total = _lateral_window_manual_selection_status(props)
        _dsg_report(
            self, {'INFO'},
            f'Click the cylindrical side of each sleeve where the drill has most access ({selected}/{total} already marked). Esc cancels.',
            f'Haz clic en el lateral de cada cilindro donde la fresa tenga más acceso ({selected}/{total} ya marcados). Esc cancela.')
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        props = context.scene.dsg_props
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._restore_cursor(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        location, radial = raycast_sleeve_lateral_on_guide(context, event, props)
        implant = getattr(props, 'implant_obj', None)
        if location is None or radial is None or not is_valid_implant_obj(implant):
            _dsg_report(
                self, {'WARNING'},
                'Click the curved lateral wall of a sleeve, not the top/bottom face',
                'Haz clic en la pared lateral curva del cilindro, no en la cara superior/inferior')
            return {'RUNNING_MODAL'}

        try:
            sleeve_mx = get_sleeve_matrix_world(props, implant)
            angle = _normalize_angle_2pi(
                _sleeve_lateral_opening_angle(context, sleeve_mx, radial))
        except Exception:
            _dsg_report(self, {'WARNING'}, 'Could not resolve that sleeve direction', 'No se pudo resolver esa dirección del cilindro')
            return {'RUNNING_MODAL'}

        values = _lateral_window_manual_angle_map(props)
        name = _safe_object_name(implant) or ''
        values[name] = float(angle)
        _store_lateral_window_manual_angle_map(props, values)
        props.sleeve_lateral_opening_direction = (
            float(radial.x), float(radial.y), float(radial.z))
        props.sleeve_lateral_opening_last_mode = 'USER_PICKED_PENDING'
        _create_lateral_window_pick_marker(context, props, implant, angle)
        try:
            if context.area is not None:
                context.area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        selected, total = _lateral_window_manual_selection_status(props)
        if total > 0 and selected >= total:
            self._restore_cursor(context)
            _dsg_report(
                self, {'INFO'},
                'Lateral drill-entry position ready. Apply the opening when satisfied.',
                'Posición de entrada lateral lista. Aplica la apertura cuando estés conforme.')
            return {'FINISHED'}

        _dsg_report(
            self, {'INFO'},
            f'Position saved for {name}. Mark the remaining sleeve(s): {selected}/{total}.',
            f'Posición guardada para {name}. Marca los cilindros restantes: {selected}/{total}.')
        return {'RUNNING_MODAL'}


class DSG_OT_AddSleeve(Operator):
    bl_idname = "dsg.add_sleeve"
    bl_label  = "Sleeve Preview"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_SLEEVE,
                action_en='Cannot generate the sleeve preview',
                action_es='No se puede generar la vista previa de cilindros'):
            return {'CANCELLED'}
        started = time.perf_counter()
        props = context.scene.dsg_props
        _prepare_outliner_for_dsg_id_changes(context)
        _sanitize_static_dsg_geometry_animdata()
        activate_precision_orthographic(context)
        # Resolution fija y no editable para mantener una geometría uniforme.
        props.sleeve_segments = 32
        implants = get_all_implant_objects(props)
        frame = _recover_frame_source_for_sleeve_rebuild(props)
        if not _valid_obj(frame) or not implants:
            _dsg_report(self, {'ERROR'}, "Frame or implants are missing", "Faltan estructura o implantes")
            return {'CANCELLED'}

        inner_r = _sleeve_inner_radius_from_props(props)
        outer_r = inner_r + props.sleeve_wall
        height = props.sleeve_height
        segments = max(16, min(64, int(getattr(props, 'sleeve_segments', 32))))
        # v8.4.3: sleeves are ALWAYS generated closed. Lateral access is
        # cut only after irrigation has been applied/skipped, so one Boolean can
        # open the sleeve and the underlying frame simultaneously.
        opening_enabled = False
        opening_solutions = {}
        props.sleeve_lateral_opening_last_mode = 'POST_IRRIGATION_PENDING'

        sleeve_signature = _current_sleeve_build_signature(props, implants, frame)
        existing_previews = get_sleeve_preview_objects()
        if (len(existing_previews) == len(implants)
                and existing_previews
                and all(str(obj.get('DSG_sleeve_build_signature', '')) == sleeve_signature
                        for obj in existing_previews)):
            for obj in existing_previews:
                try:
                    obj.hide_viewport = False
                    obj.hide_select = False
                    obj.hide_set(False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            set_active(context, existing_previews[0])
            _dsg_report(
                self, {'INFO'},
                'The sleeve preview already exists; the existing objects were reused',
                'La vista previa de cilindros ya existe; se reutilizaron los objetos existentes')
            return {'FINISHED'}

        # The sleeve geometry changed, so any previous manual lateral-window
        # direction is no longer guaranteed to land on the same physical wall.
        _clear_lateral_window_manual_picks(props, remove_markers=True)

        # Nunca eliminar DSG_Guide mientras Scene/Undo puedan referenciarla.
        # Se archiva de forma no destructiva y se genera una guía nueva.
        _archive_current_guide_for_sleeve_rebuild(props)
        for existing in list(bpy.data.objects):
            try:
                existing_name = str(existing.name)
                matches = (
                    existing_name.startswith(SLEEVE_PREFIX)
                    or existing_name.startswith('DSG_SleeveApplyTmp_')
                    or existing_name == 'DSG_SleeveBatchCutter'
                )
            except Exception:
                matches = False
            if matches and not bool(existing.get('DSG_obsolete_hidden', False)):
                try:
                    existing['DSG_sleeve_preview'] = False
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                _archive_transient_dsg_object(
                    existing, reason='sleeve_preview_rebuild',
                    prefix='DSG_ArchivedSleeve_')

        previews = []

        for idx, implant in enumerate(implants, start=1):
            sleeve_name = f"{SLEEVE_PREFIX}_{idx:02d}"
            sleeve_mx = get_sleeve_matrix_world(props, implant)

            # Sleeve hueco construido directamente: no cutter interior ni Boolean.
            solution = opening_solutions.get(implant.name, {}) if opening_enabled else {}
            opening_width = float(solution.get(
                'actual_width_mm', getattr(props, 'sleeve_lateral_opening_width', inner_r * 2.0)))
            opening_angle = float(solution.get('center_angle', 0.0)) if opening_enabled else 0.0
            opening_half_angle = float(solution.get('half_angle', 0.0)) if opening_enabled else None
            mesh = make_annular_cylinder_mesh(
                sleeve_name + '_Mesh', inner_r, outer_r, height, segments,
                lateral_opening=opening_enabled,
                opening_width_mm=opening_width,
                opening_center_angle=opening_angle,
                opening_half_angle=opening_half_angle)
            sleeve = bpy.data.objects.new(sleeve_name, mesh)
            sleeve.matrix_world = sleeve_mx
            link_object(context, sleeve)
            register_dsg_object(
                sleeve, ROLE_SLEEVE, sleeve_name,
                {
                    'DSG_implant': implant.name,
                    'DSG_sleeve_preview': True,
                    'DSG_analytic_solid': True,
                    'DSG_sleeve_segments': segments,
                    'DSG_sleeve_inner_diameter_mm': float(inner_r * 2.0),
                    'DSG_sleeve_wall_mm': float(props.sleeve_wall),
                    'DSG_sleeve_height_mm': float(height),
                    'DSG_sleeve_build_signature': sleeve_signature,
                    'DSG_sleeve_lateral_opening': bool(opening_enabled),
                    'DSG_sleeve_lateral_opening_width_mm': float(opening_width),
                    'DSG_sleeve_lateral_opening_requested_width_mm': float(getattr(props, 'sleeve_lateral_opening_width', opening_width)),
                    'DSG_sleeve_lateral_opening_angle_rad': float(opening_angle),
                    'DSG_sleeve_lateral_opening_half_angle_rad': float(opening_half_angle or 0.0),
                    'DSG_sleeve_lateral_opening_mode': str(solution.get('mode', 'CLOSED') if opening_enabled else 'CLOSED'),
                    'DSG_sleeve_lateral_opening_free_span_deg': float(math.degrees(float(solution.get('free_span_rad', 0.0)))),
                    'DSG_sleeve_lateral_opening_rotation_requested_deg': float(solution.get('manual_rotation_requested_deg', 0.0)),
                    'DSG_sleeve_lateral_opening_rotation_applied_deg': float(solution.get('manual_rotation_applied_deg', 0.0)),
                    'DSG_sleeve_lateral_opening_width_reduced': bool(solution.get('width_reduced', False)),
                    'DSG_sleeve_window_irrigation_signature': _sleeve_window_irrigation_signature(props, implants),
                },
            )
            store_analytic_solid_preflight(
                sleeve, f'sleeve_union_part_{idx}',
                message=f'Sleeve {idx} closed by construction; no preview Boolean')

            sleeve['DSG_sleeve_side'] = 'opposite_blockout_axis'
            sleeve['DSG_blockout_axis'] = tuple(float(v) for v in get_insertion_axis())
            sleeve.display_type = 'WIRE'
            sleeve.show_in_front = True
            sleeve.hide_select = False
            previews.append(sleeve)

        props.frame_obj = frame
        if previews:
            set_active(context, previews[0])
            hide_axis_empty()
        elapsed = time.perf_counter() - started
        try:
            props.sleeve_last_timing = f'Preview {elapsed:.3f} s · {len(previews)} sleeve(s) · {segments} segmentos'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _dsg_report(self, {'INFO'}, f"Direct preview ready in {elapsed:.2f} s: {len(previews)} sleeve(s). "
                    "No DIFFERENCE Boolean or sleeve repair was required.", f"Preview directo listo en {elapsed:.2f} s: {len(previews)} sleeve(s). "
                    "Sin Boolean DIFFERENCE ni reparación por sleeve.")
        return {'FINISHED'}


class DSG_OT_CreateApplySleeves(Operator):
    bl_idname = 'dsg.create_apply_sleeves'
    bl_label = 'Create and Apply Sleeves'
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_SLEEVE,
                action_en='Cannot create the sleeves',
                action_es='No se pueden crear los cilindros'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        _prepare_outliner_for_dsg_id_changes(context)
        _sanitize_static_dsg_geometry_animdata()
        props.sleeve_segments = 32

        existing_guide = get_active_guide_obj(props)
        if (_valid_obj(existing_guide)
                and bool(existing_guide.get('DSG_sleeves_applied', False))):
            if _sleeve_dimensions_match_guide(props, existing_guide):
                props.current_step = max(int(getattr(props, 'current_step', STEP_SLEEVE)), STEP_IRRIGATION)
                set_active(context, existing_guide)
                _dsg_report(
                    self, {'INFO'},
                    'Sleeves are already applied with these dimensions; the existing guide was reused',
                    'Los cilindros ya están aplicados con estas medidas; se reutilizó la guía existente')
                return {'FINISHED'}
            _invalidate_workflow_after(
                context, STEP_SLEEVE, reason='sleeve_dimensions_changed')

        result = bpy.ops.dsg.add_sleeve('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            _dsg_report(self, {'ERROR'}, 'Could not create the sleeves', 'No se pudieron generar los cilindros')
            return {'CANCELLED'}

        result = bpy.ops.dsg.apply_sleeves('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            _dsg_report(self, {'ERROR'}, 'Sleeves were created but could not be applied to the guide', 'Los cilindros se generaron, pero no pudieron aplicarse a la guía')
            return {'CANCELLED'}

        _dsg_report(self, {'INFO'}, 'Sleeves created and applied to the guide', 'Cilindros generados y aplicados a la guía')
        return {'FINISHED'}


class DSG_OT_RebuildLateralWindowFromIrrigation(Operator):
    """Deprecated legacy id: sleeve rebuilding is forbidden after irrigation."""
    bl_idname = 'dsg.rebuild_lateral_window_from_irrigation'
    bl_label = 'Legacy Lateral Window Rebuild (disabled)'
    bl_options = {'REGISTER'}

    def execute(self, context):
        _dsg_report(
            self, {'ERROR'},
            'Legacy sleeve rebuild disabled. Use the post-irrigation batch Boolean.',
            'Reconstrucción antigua desactivada. Usa la booleana post-irrigación sobre frame + cilindro.')
        return {'CANCELLED'}


def _build_post_irrigation_lateral_opening_cutter(context, props, guide):
    """One batch cutter for sleeve + frame, sized to the INNER sleeve diameter."""
    implants = get_all_implant_objects(props)
    if not implants:
        return None, [], 'no implants'
    try:
        inner_diameter = float(guide.get(
            'DSG_sleeve_inner_diameter_mm', getattr(props, 'sleeve_inner_diameter', 4.7)))
        wall = float(guide.get('DSG_sleeve_wall_mm', getattr(props, 'sleeve_wall', 1.5)))
        height = float(guide.get('DSG_sleeve_height_mm', getattr(props, 'sleeve_height', 7.0)))
        frame_radius = float(guide.get('DSG_frame_radius_mm', getattr(props, 'tube_radius', FRAME_RADIUS_DEFAULT_MM)))
    except Exception:
        return None, [], 'invalid sleeve dimensions'
    inner_diameter = max(0.50, inner_diameter)
    inner_radius = inner_diameter * 0.5
    outer_radius = inner_radius + max(0.20, wall)
    frame_radius = max(0.50, frame_radius)
    # The requested clinical rule is exact: the lateral window's tangential
    # width equals the distance between two opposite points of the inner wall.
    # 0.02 mm is Boolean overlap only; metadata records the nominal width.
    cutter_width = inner_diameter + 0.02
    radial_start = -0.10
    radial_end = outer_radius + 2.0 * frame_radius + 2.0
    radial_depth = radial_end - radial_start
    z_depth = height + 2.0 * frame_radius + 4.0

    # The property is synchronized to the physical design requirement. It is no
    # longer a free dimension in the UI.
    props.sleeve_lateral_opening_width = float(inner_diameter)
    records = []
    bm_total = bmesh.new()
    try:
        for implant in implants:
            sleeve_mx = get_sleeve_matrix_world(props, implant)
            # DSG 9.6.3: the clinician explicitly chooses the drill-entry side.
            # Automatic free-sector placement was technically safe but could point
            # the window toward a side that is awkward in a patient with limited
            # mouth opening. The exact click is now authoritative; irrigation is
            # retained only as a safety guardrail, never as an auto-rotator.
            solution = _resolve_user_lateral_window_for_implant(
                context, props, implant, sleeve_mx, outer_radius, inner_diameter)
            if not bool(solution.get('valid', False)):
                return None, records, (
                    f'cannot place lateral opening for {implant.name}: '
                    f'{solution.get("message", "unknown")}' )
            center_angle = float(solution.get('center_angle', 0.0))
            mode = str(solution.get('mode', 'USER_PICKED_SIDE'))
            free_span_deg = math.degrees(float(solution.get('free_span_rad', 2.0 * math.pi)))

            local_radial = Vector((math.cos(center_angle), math.sin(center_angle), 0.0))
            local_tangent = Vector((-math.sin(center_angle), math.cos(center_angle), 0.0))
            radial = _normalized_or_fallback(
                sleeve_mx.to_3x3() @ local_radial, (1.0, 0.0, 0.0))
            tangent = _normalized_or_fallback(
                sleeve_mx.to_3x3() @ local_tangent, (0.0, 1.0, 0.0))
            axis = _normalized_or_fallback(
                sleeve_mx.to_3x3() @ Vector((0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
            center = sleeve_mx.translation + radial * ((radial_start + radial_end) * 0.5)

            bm = bmesh.new()
            try:
                bmesh.ops.create_cube(bm, size=1.0)
                for vert in bm.verts:
                    vert.co.x *= radial_depth
                    vert.co.y *= cutter_width
                    vert.co.z *= z_depth
                orientation = Matrix((radial, tangent, axis)).transposed().to_4x4()
                orientation.translation = center
                bmesh.ops.transform(bm, matrix=orientation, verts=bm.verts[:])
                _transfer_bm(bm, bm_total)
            finally:
                bm.free()
            records.append({
                'implant': str(implant.name),
                'mode': mode,
                'angle_rad': float(center_angle),
                'picked_angle_rad': float(solution.get('picked_center_angle', center_angle)),
                'fine_rotation_deg': float(solution.get('manual_rotation_applied_deg', 0.0)),
                'width_mm': float(inner_diameter),
                'free_span_deg': float(free_span_deg),
            })

        if not bm_total.faces:
            return None, records, 'empty lateral opening cutter'
        bmesh.ops.recalc_face_normals(bm_total, faces=bm_total.faces[:])
        mesh = bpy.data.meshes.new('DSG_PostIrrigationLateralOpeningCutter_Mesh')
        bm_total.to_mesh(mesh)
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
    finally:
        bm_total.free()

    cutter = bpy.data.objects.new('DSG_PostIrrigationLateralOpeningCutter', mesh)
    cutter.matrix_world = Matrix.Identity(4)
    link_object(context, cutter)
    cutter.display_type = 'WIRE'
    cutter.show_in_front = True
    register_dsg_object(cutter, ROLE_CUTTER, cutter.name, {
        'DSG_cut_type': 'post_irrigation_lateral_opening_batch',
        'DSG_nominal_opening_width_mm': float(inner_diameter),
        'DSG_boolean_scope': 'FRAME_AND_SLEEVE_SIMULTANEOUS',
        'DSG_implant_count': int(len(records)),
    })
    return cutter, records, ''


class DSG_OT_ApplyPostIrrigationLateralOpening(Operator):
    bl_idname = 'dsg.apply_post_irrigation_lateral_opening'
    bl_label = 'Apply Post-Irrigation Lateral Opening'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot apply the lateral opening',
                action_es='No se puede aplicar la apertura lateral'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'DSG_Guide is missing', 'Falta DSG_Guide')
            return {'CANCELLED'}
        resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper()
        if resolution not in {'APPLIED', 'SKIPPED'}:
            _dsg_report(
                self, {'ERROR'},
                'Resolve irrigation before creating the lateral opening',
                'Resuelve primero la irrigación antes de crear la apertura lateral')
            return {'CANCELLED'}
        if bool(guide.get('DSG_sleeve_lateral_opening', False)):
            _dsg_report(self, {'INFO'}, 'Lateral opening is already applied', 'La apertura lateral ya está aplicada')
            return {'FINISHED'}

        cutter = None
        work = None
        try:
            cutter, records, error = _build_post_irrigation_lateral_opening_cutter(
                context, props, guide)
            if not _valid_obj(cutter):
                raise RuntimeError(error or 'could not build lateral opening cutter')

            mesh = guide.data.copy()
            work = bpy.data.objects.new('DSG_Guide_PostIrrigationOpening_WORK', mesh)
            work.matrix_world = guide.matrix_world.copy()
            link_object(context, work)
            _inherit_dsg_custom_properties(guide, work)
            before_polygons = len(work.data.polygons)

            modifier = work.modifiers.new('DSG_PostIrrigationLateralOpening', 'BOOLEAN')
            modifier.operation = 'DIFFERENCE'
            modifier.object = cutter
            try:
                modifier.solver = 'EXACT'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            set_boolean_exact_options(modifier, robust=True)
            if not apply_modifier_direct(context, work, modifier.name):
                raise RuntimeError('Boolean EXACT could not cut frame and sleeve together')
            if work.data is None or len(work.data.vertices) == 0 or len(work.data.polygons) == 0:
                raise RuntimeError('lateral opening Boolean produced empty geometry')
            after_polygons = len(work.data.polygons)

            nominal_width = float(guide.get(
                'DSG_sleeve_inner_diameter_mm', getattr(props, 'sleeve_inner_diameter', 4.7)))
            work['DSG_sleeve_lateral_opening'] = True
            work['DSG_sleeve_lateral_opening_width_mm'] = float(nominal_width)
            work['DSG_sleeve_lateral_opening_rotation_deg'] = float(
                getattr(props, 'sleeve_lateral_opening_rotation', 0.0))
            work['DSG_sleeve_lateral_opening_mode'] = 'POST_IRRIGATION_USER_PICKED_BOOLEAN'
            work['DSG_sleeve_lateral_opening_stage'] = 'POST_IRRIGATION'
            work['DSG_sleeve_lateral_opening_boolean_scope'] = 'FRAME_AND_SLEEVE_SIMULTANEOUS'
            work['DSG_sleeve_lateral_opening_records'] = json.dumps(records, separators=(',', ':'))
            work['DSG_sleeve_window_irrigation_signature'] = _sleeve_window_irrigation_signature(props)
            work['DSG_lateral_opening_pre_polygons'] = int(before_polygons)
            work['DSG_lateral_opening_post_polygons'] = int(after_polygons)

            _archive_current_guide_for_sleeve_rebuild(
                props, reason='post_irrigation_lateral_opening_commit')
            work.name = GUIDE_NAME
            work.data.name = GUIDE_NAME + '_Mesh'
            props.guide_obj = register_dsg_object(work, ROLE_GUIDE, GUIDE_NAME)
            work = None
            props.sleeve_lateral_opening = True
            props.sleeve_lateral_opening_width = float(nominal_width)
            props.sleeve_lateral_opening_last_mode = 'POST_IRRIGATION_USER_PICKED_BOOLEAN'
            context.scene[WORKFLOW_IRRIGATION_RESOLVED_KEY] = True
            _workflow_store_signature(
                context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY,
                _workflow_object_signature(props.guide_obj))
            prepare_final_cut_references(context, props, show_passive=False)
            _remove_lateral_window_pick_markers()
            _dsg_report(
                self, {'INFO'},
                f'Lateral opening applied after irrigation: {nominal_width:.2f} mm, frame + sleeve in one Boolean',
                f'Apertura lateral aplicada después de irrigación: {nominal_width:.2f} mm, frame + cilindro en una sola booleana')
            return {'FINISHED'}
        except Exception as exc:
            if _valid_obj(work):
                safe_remove_object(work)
            _dsg_report(
                self, {'ERROR'},
                f'Lateral opening canceled: {exc}',
                f'Apertura lateral cancelada: {exc}')
            return {'CANCELLED'}
        finally:
            if _valid_obj(cutter):
                safe_remove_object(cutter)


class DSG_OT_ContinueAfterIrrigation(Operator):
    bl_idname = 'dsg.continue_after_irrigation'
    bl_label = 'Continue After Irrigation'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot continue after irrigation',
                action_es='No se puede continuar después de irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        resolution = str(guide.get('DSG_irrigation_resolution', '') or '').upper() if _valid_obj(guide) else ''
        if resolution not in {'APPLIED', 'SKIPPED'}:
            _dsg_report(self, {'ERROR'}, 'Resolve irrigation first', 'Resuelve primero la irrigación')
            return {'CANCELLED'}
        context.scene[WORKFLOW_IRRIGATION_RESOLVED_KEY] = True
        _workflow_store_signature(
            context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY,
            _workflow_object_signature(guide))
        prepare_final_cut_references(context, props, show_passive=False)
        # If the clinician only previewed/marked a lateral access but chose not
        # to apply it, do not leave helper arrows in the final guide scene.
        if not bool(guide.get('DSG_sleeve_lateral_opening', False)):
            _remove_lateral_window_pick_markers()
        props.current_step = STEP_REINFORCEMENT
        return {'FINISHED'}


class DSG_OT_ApplySleeves(Operator):
    bl_idname = 'dsg.apply_sleeves'
    bl_label = 'Apply Sleeves'
    bl_options = {'REGISTER'}

    def execute(self, context):
        """Crea DSG_Guide sin borrar objetos durante la evaluación del depsgraph.

        Blender 5 puede cerrar de forma nativa si un objeto activo/original se
        elimina mientras BKE_object_sync_to_original está sincronizando la vista.
        Por eso el frame y los sleeves fuente se conservan ocultos hasta Reset.
        """
        if not _require_workflow_stage(
                self, context, STEP_SLEEVE,
                action_en='Cannot apply the sleeves',
                action_es='No se pueden aplicar los cilindros'):
            return {'CANCELLED'}
        started = time.perf_counter()
        props = context.scene.dsg_props
        _prepare_outliner_for_dsg_id_changes(context)
        _sanitize_static_dsg_geometry_animdata()
        existing_guide = get_active_guide_obj(props)
        if (_valid_obj(existing_guide)
                and bool(existing_guide.get('DSG_sleeves_applied', False))):
            props.current_step = max(int(getattr(props, 'current_step', STEP_SLEEVE)), STEP_IRRIGATION)
            set_active(context, existing_guide)
            _dsg_report(
                self, {'INFO'},
                'Sleeves are already applied; no new guide or hidden sources were created',
                'Los cilindros ya están aplicados; no se crearon otra guía ni fuentes ocultas')
            return {'FINISHED'}

        frame = _recover_frame_source_for_sleeve_rebuild(props)
        previews = get_sleeve_preview_objects()
        if not _valid_obj(frame) or not previews:
            _dsg_report(self, {'ERROR'}, 'Create the sleeve preview first', 'Genera primero la vista previa de cilindros')
            return {'CANCELLED'}

        # Guarda matrices clínicas antes de cambiar nombres o visibilidad.
        for sleeve in previews:
            implant_name = str(sleeve.get('DSG_implant', ''))
            implant = bpy.data.objects.get(implant_name) if implant_name else None
            if is_valid_implant_obj(implant):
                try:
                    implant['DSG_sleeve_matrix_world'] = json.dumps(
                        [list(row) for row in sleeve.matrix_world])
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Evita que el objeto activo sea uno de los objetos fuente que pasarán a
        # estado oculto durante este mismo operador.
        try:
            if context.object and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            for obj in list(context.selected_objects):
                obj.select_set(False)
            context.view_layer.objects.active = None
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Nunca se elimina una guía anterior durante el refresh. Se aparta y queda
        # disponible para que Reset la limpie de forma segura posteriormente.
        old_guide = _archive_current_guide_for_sleeve_rebuild(props)

        existing_tmp = bpy.data.objects.get(GUIDE_BUILD_TMP_NAME)
        if _valid_obj(existing_tmp):
            _archive_transient_dsg_object(
                existing_tmp, reason='guide_build_tmp_replaced',
                prefix='DSG_ArchivedGuideTmp_')
        guide = build_combined_mesh_object_world(
            context, [frame] + previews, GUIDE_BUILD_TMP_NAME)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'Could not build DSG_Guide from the frame and sleeves', 'No se pudo construir DSG_Guide a partir de la estructura y los cilindros')
            return {'CANCELLED'}

        preview_count = len(previews)

        # Las fuentes NO se eliminan. Se renombran y ocultan para impedir punteros
        # StructRNA inválidos durante el refresco multihilo del depsgraph.
        _sanitize_dsg_object_for_id_change(frame)
        try:
            frame.name = SLEEVE_SOURCE_FRAME_NAME
            frame['DSG_hidden_source'] = True
            frame['DSG_source_role'] = 'frame_before_sleeves'
            frame.hide_render = True
            frame.hide_select = True
            frame.hide_viewport = True
            frame.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        for index, sleeve in enumerate(previews, start=1):
            _sanitize_dsg_object_for_id_change(sleeve)
            try:
                sleeve.name = f'{SLEEVE_SOURCE_PREFIX}{index:02d}'
                sleeve['DSG_sleeve_preview'] = False
                sleeve['DSG_hidden_source'] = True
                sleeve['DSG_source_role'] = 'sleeve_before_guide'
                sleeve.hide_render = True
                sleeve.hide_select = True
                sleeve.hide_viewport = True
                sleeve.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        guide.name = GUIDE_NAME
        try:
            guide.data.name = GUIDE_NAME + '_Mesh'
            guide['DSG_sleeve_union_deferred'] = True
            guide['DSG_multishell_guide'] = True
            guide['DSG_closed_shell_count'] = int(preview_count + 1)
            guide['DSG_sleeve_apply_mode'] = 'DIRECT_MESH_COMBINE_SAFE_HIDDEN_SOURCES'
            guide['DSG_sleeve_exact_faces_preserved'] = True
            guide['DSG_source_objects_retained'] = True
            guide['DSG_sleeves_applied'] = True
            guide['DSG_sleeve_inner_diameter_mm'] = float(getattr(props, 'sleeve_inner_diameter', 4.7))
            guide['DSG_sleeve_wall_mm'] = float(getattr(props, 'sleeve_wall', 1.5))
            guide['DSG_sleeve_height_mm'] = float(getattr(props, 'sleeve_height', 7.0))
            guide['DSG_sleeve_lateral_opening'] = False
            guide['DSG_sleeve_lateral_opening_width_mm'] = 0.0
            guide['DSG_sleeve_lateral_opening_rotation_deg'] = 0.0
            guide['DSG_sleeve_lateral_opening_mode'] = 'POST_IRRIGATION_PENDING'
            guide['DSG_sleeve_lateral_opening_stage'] = 'POST_IRRIGATION'
            guide['DSG_sleeve_window_irrigation_signature'] = ''
            guide['DSG_sleeve_lateral_opening_records'] = '[]'
            guide['DSG_sleeve_build_signature'] = str(
                previews[0].get('DSG_sleeve_build_signature', '')) if previews else ''
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        guide.display_type = 'SOLID'
        guide.show_in_front = False
        guide.hide_viewport = False
        guide.hide_render = False
        guide.hide_select = False
        try:
            guide.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        props.guide_obj = register_dsg_object(guide, ROLE_GUIDE, GUIDE_NAME)
        props.frame_obj = None
        props.dct_object_being_cut = guide

        elapsed = time.perf_counter() - started
        status_data = {
            'status': 'orange',
            'checked': True,
            'solid': True,
            'repaired': False,
            'repair_methods': [],
            'bad_edges': 0,
            'degenerate_faces': 0,
            'polygons': len(guide.data.polygons) if guide.data else 0,
            'solver': 'NONE',
            'message': (
                f'Safe application in {elapsed:.3f} s: frame y {preview_count} sleeve(s) '
                'se conservaron ocultos para evitar invalidar el depsgraph.'
            ),
            'multishell': True,
            'boolean_deferred': True,
        }
        store_boolean_preflight(guide, 'sleeve_union', status_data)
        try:
            props.sleeve_last_timing = (
                f'Safe application {elapsed:.3f} s · {preview_count} sleeve(s) · fuentes ocultas')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        sleeve_signature = _workflow_object_signature(guide)
        if _workflow_signature_changed(context.scene, WORKFLOW_SLEEVE_SIGNATURE_KEY, sleeve_signature):
            _invalidate_workflow_after(context, STEP_SLEEVE, reason='sleeve_guide_changed')
        _workflow_store_signature(context.scene, WORKFLOW_SLEEVE_SIGNATURE_KEY, sleeve_signature)
        props.current_step = STEP_IRRIGATION
        hide_axis_empty()
        try:
            context.view_layer.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        set_active(context, guide)
        _dsg_report(self, {'INFO'}, f'{preview_count} sleeve(s) applied without deleting objects during refresh.', f'{preview_count} cilindro(s) aplicado(s) sin eliminar objetos durante la actualización.')
        return {'FINISHED'}


class DSG_OT_ConfirmSleeve(Operator):
    """Avance manual de compatibilidad para Blender 4.1.

    En Blender 5 el operador de generación suele refrescar el panel y avanza solo,
    pero en 4.1 algunos redraw del panel N pueden quedarse en el paso Sleeve. Este
    botón deja una salida explícita y segura si la guía ya existe.
    """
    bl_idname = "dsg.confirm_sleeve"
    bl_label = "Continue to Irrigation"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_SLEEVE,
                action_en='Cannot confirm the sleeves',
                action_es='No se pueden confirmar los cilindros'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not (_valid_obj(guide) and bool(guide.get('DSG_sleeves_applied', False))):
            _dsg_report(self, {'ERROR'}, "Create and apply the sleeves first", "Genera y aplica primero los cilindros")
            return {'CANCELLED'}
        if not _sleeve_dimensions_match_guide(props, guide):
            _dsg_report(
                self, {'ERROR'},
                'The sleeve dimensions changed; update the sleeves before continuing',
                'Las medidas del cilindro cambiaron; actualiza los cilindros antes de continuar')
            return {'CANCELLED'}
        props.guide_obj = register_dsg_object(guide, ROLE_GUIDE, GUIDE_NAME)
        sleeve_signature = _workflow_object_signature(guide)
        _workflow_store_signature(context.scene, WORKFLOW_SLEEVE_SIGNATURE_KEY, sleeve_signature)
        props.current_step = STEP_IRRIGATION
        try:
            for area in context.screen.areas:
                area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _dsg_report(self, {'INFO'}, "Sleeves confirmed. Continue to irrigation", "Cilindros confirmados. Continúa con irrigación")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Paso 9 — Canal de perforación final
# ─────────────────────────────────────────────────────────────

class DSG_OT_ProtectDrillInsertion(Operator):
    bl_idname = 'dsg.protect_drill_insertion'
    bl_label = 'Clear Drill Insertion Path'
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_DRILL,
                action_en='Cannot prepare the drill path',
                action_es='No se puede preparar el eje de fresado'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        ok, message, operations = protect_guide_drill_insertion_transactional(
            context, props)
        if not ok:
            _dsg_report(self, {'ERROR'}, f'Drill protection canceled: {message}', f'Protección de fresa cancelada: {message}')
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, f'Drill path cleared: {message}', f'Eje de fresado limpiado: {message}')
        return {'FINISHED'}


class DSG_OT_AddDrillChannel(Operator):
    bl_idname = 'dsg.add_drill_channel'
    bl_label = 'Create Drill Channels'
    bl_options = {'REGISTER'}

    def execute(self, context):
        """Perfora cada shell cerrado por separado y solo después reúne la guía.

        DSG_Guide puede contener frame, sleeves y paredes de irrigación como shells
        independientes. Apply un único Boolean sobre el objeto multishell podía
        producir edges en T y resultados no-manifold. Este operador mantiene la
        guía original intacta, separa copias por conectividad, corta únicamente los
        componentes que intersectan cada cutter y hace commit al final.
        """
        if not _require_workflow_stage(
                self, context, STEP_DRILL,
                action_en='Cannot create the drill channels',
                action_es='No se pueden crear los canales de fresado'):
            return {'CANCELLED'}
        activate_precision_orthographic(context)
        props = context.scene.dsg_props
        guide = props.guide_obj
        implants = get_all_implant_objects(props)
        if not _valid_obj(guide) or not implants:
            _dsg_report(self, {'ERROR'}, 'Guide or implants are missing', 'Faltan guía o implantes')
            return {'CANCELLED'}

        existing_channel_count = int(guide.get('DSG_drill_channel_count', 0))
        if existing_channel_count >= len(implants):
            set_active(context, guide)
            _dsg_report(
                self, {'INFO'},
                'Drill channels are already present; the existing guide was reused',
                'Los canales de fresado ya existen; se reutilizó la guía actual')
            return {'FINISHED'}

        # La limpieza automática se realiza aquí, después de aplicar o saltar
        # los conectores de refuerzo. Si el usuario ya la ejecutó manualmente,
        # el marcador de la guía evita repetir la booleana.
        already_clean = (
            bool(guide.get('DSG_drill_insertion_protected', False))
            and bool(guide.get('DSG_sleeve_occlusal_faces_preserved', False))
        )
        if bool(getattr(props, 'drill_protection_auto', True)) and not already_clean:
            ok, message, _operations = protect_guide_drill_insertion_transactional(
                context, props)
            if not ok:
                _dsg_report(self, {'ERROR'}, f'Automatic cleanup canceled: {message}', f'Limpieza automática cancelada: {message}')
                return {'CANCELLED'}
            guide = get_active_guide_obj(props)
            if not _valid_obj(guide):
                _dsg_report(self, {'ERROR'}, 'The guide is unavailable after cleanup', 'La guía no está disponible después de la limpieza')
                return {'CANCELLED'}
            props.guide_obj = guide

        ensure_object_mode(context)
        original_guide_name = _safe_object_name(guide)
        try:
            original_guide_metadata = {str(key): guide[key] for key in guide.keys()}
        except Exception:
            original_guide_metadata = {}

        # Elimina únicamente residuos temporales de intentos anteriores.
        safe_remove_by_prefix('DSG_DrillGuidePart')
        safe_remove_by_prefix('DSG_DrillCutterPart')
        safe_remove_by_name('DSG_Drill_Result_TMP')

        temp_objects = []
        guide_parts = []
        cutter_parts = []
        batch_cutter = None
        final_temp = None
        failure = None
        operations = 0
        unverified_parts = 0
        diagnostic = {
            'status': 'red',
            'phase': 'initializing',
            'solver': 'MANIFOLD',
            'bad_edges': None,
            'degenerate_faces': None,
            'component_operations': 0,
            'guide_components': 0,
            'cutter_components': 0,
        }

        def store_diagnostic(target_obj, status, phase, message, report=None):
            payload = dict(diagnostic)
            payload.update({
                'status': status,
                'phase': phase,
                'message': message,
                'component_operations': int(operations),
                'guide_components': int(len(guide_parts)),
                'cutter_components': int(len(cutter_parts)),
                'unverified_parts': int(unverified_parts),
            })
            if isinstance(report, dict):
                payload['bad_edges'] = report.get('bad_edges')
                payload['degenerate_faces'] = report.get('degenerate_faces')
                payload['polygons'] = report.get('polygons')
            if _valid_obj(target_obj):
                try:
                    target_obj['DSG_solid_precheck_step10'] = json.dumps(
                        payload, ensure_ascii=False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            return payload

        try:
            # 1) La guía original nunca se modifica durante el cálculo.
            guide_parts = split_mesh_object_loose_parts(
                context, guide, prefix='DSG_DrillGuidePart')
            temp_objects.extend(guide_parts)
            if not guide_parts:
                failure = 'No se pudo separar DSG_Guide en componentes cerrados'
                raise RuntimeError(failure)

            # Solo un component demostrado no-manifold bloquea el proceso.
            for index, part in enumerate(guide_parts):
                report = get_mesh_solid_report(part, max_polygons=900000)
                if report.get('checked') and not report.get('solid'):
                    failure = (
                        f'El component {index + 1} ya era no-manifold antes del drill: '
                        f'aristas={report.get("bad_edges", 0)}, '
                        f'degeneradas={report.get("degenerate_faces", 0)}')
                    store_diagnostic(guide, 'red', 'guide_component_preflight', failure, report)
                    raise RuntimeError(failure)
                if not report.get('checked'):
                    unverified_parts += 1

            # 2) Todos los ejes clínicos se conservan como un único cutter multi-shell.
            # Blender 5.1 puede cerrar dentro de meshintersect cuando encadena
            # DIFFERENCE EXACT (componente × implante). Los cutters son cilindros
            # analíticos cerrados, por lo que se aplica una sola MANIFOLD por
            # componente de guía y nunca se invoca EXACT en este paso.
            safe_remove_by_name(DRILL_NAME)
            safe_remove_by_name(DRILL_BATCH_CUTTER_NAME)
            safe_remove_by_prefix('DSG_DrillCutterPart')
            safe_remove_by_prefix(DRILL_PROTECTION_PREFIX)
            batch_cutter = build_safe_drill_cutter(
                context, props, implants, guide, name=DRILL_BATCH_CUTTER_NAME)
            if not _valid_obj(batch_cutter):
                failure = 'Could not create the combined drill cutter'
                raise RuntimeError(failure)
            temp_objects.append(batch_cutter)
            cutter_parts = [batch_cutter]

            cutter_report = get_mesh_solid_report(batch_cutter, max_polygons=900000)
            if cutter_report.get('checked') and not cutter_report.get('solid'):
                failure = (
                    f'El cutter combinado no es sólido: '
                    f'aristas={cutter_report.get("bad_edges", 0)}, '
                    f'degeneradas={cutter_report.get("degenerate_faces", 0)}')
                store_diagnostic(
                    guide, 'red', 'combined_cutter_preflight', failure, cutter_report)
                raise RuntimeError(failure)

            # Refresca referencias por nombre antes de modificar mallas.
            guide_part_names = [
                name for name in (_safe_object_name(obj) for obj in guide_parts) if name]
            cutter_name = _safe_object_name(batch_cutter)
            guide_parts = [bpy.data.objects.get(name) for name in guide_part_names]
            batch_cutter = bpy.data.objects.get(cutter_name) if cutter_name else None
            cutter_parts = [batch_cutter] if _valid_obj(batch_cutter) else []
            if (not guide_parts or not cutter_parts or
                    any(not _valid_obj(obj) for obj in guide_parts + cutter_parts)):
                failure = 'Temporary components became invalid before drilling'
                raise RuntimeError(failure)

            # 3) Una única DIFFERENCE MANIFOLD por componente intersectado.
            combined_aabb = object_world_aabb(batch_cutter)
            for part_index, part in enumerate(guide_parts):
                if not aabb_overlap(
                        object_world_aabb(part), combined_aabb, margin=0.02):
                    continue
                ok, message = apply_difference_manifold_checked(
                    context,
                    part,
                    batch_cutter,
                    f'DSG_DrillCombined_{part_index:02d}',
                )
                if not ok:
                    failure = (
                        f'Drill MANIFOLD falló en component {part_index + 1}: {message}')
                    report = get_mesh_solid_report(part, max_polygons=900000)
                    store_diagnostic(
                        guide, 'red', 'combined_component_difference', failure, report)
                    raise RuntimeError(failure)
                operations += 1

            if operations == 0:
                failure = (
                    'Los cutters no intersectaron ningún component de la guía. '
                    'Comprueba la posición de los implantes y la altura de los sleeves.')
                raise RuntimeError(failure)

            # 4) Reunión no destructiva de shells ya cortados y validados.
            safe_remove_by_name('DSG_Drill_Result_TMP')
            final_temp = build_combined_mesh_object_world(
                context, guide_parts, 'DSG_Drill_Result_TMP')
            if not _valid_obj(final_temp):
                failure = 'No se pudo reunir los componentes perforados'
                raise RuntimeError(failure)
            temp_objects.append(final_temp)

            final_report = get_mesh_solid_report(final_temp, max_polygons=1200000)
            if final_report.get('checked') and not final_report.get('solid'):
                failure = (
                    f'La reunión final del drill no es solid: '
                    f'aristas={final_report.get("bad_edges", 0)}, '
                    f'degeneradas={final_report.get("degenerate_faces", 0)}')
                store_diagnostic(guide, 'red', 'final_validation', failure, final_report)
                raise RuntimeError(failure)

            # 5) Commit atómico: la guía original se archiva y nunca se elimina durante el depsgraph.
            if original_guide_name:
                _archive_current_guide_for_sleeve_rebuild(
                    props, reason='drill_channel_commit')

            for obj in list(temp_objects):
                if obj is final_temp:
                    continue
                safe_remove_object(obj)

            final_temp.name = GUIDE_NAME
            final_temp.data.name = GUIDE_NAME + '_Mesh'
            try:
                for key, value in original_guide_metadata.items():
                    final_temp[key] = value
                final_temp['DSG_drill_channel_count'] = int(len(implants))
                final_temp['DSG_drill_component_operations'] = int(operations)
                final_temp['DSG_drill_component_mode'] = True
                final_temp['DSG_drill_combined_manifold'] = True
                final_temp['DSG_multishell_guide'] = True
                final_temp['DSG_needs_final_consolidation'] = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

            props.guide_obj = register_dsg_object(
                final_temp, ROLE_GUIDE, GUIDE_NAME)
            set_active(context, final_temp)
            prepare_final_cut_references(context, props, show_passive=False)

            status = 'orange' if (unverified_parts or not final_report.get('checked')) else 'green'
            message = (
                f'Drill completado: {len(implants)} canal(es) con cutter combinado, '
                f'{operations} corte(s) MANIFOLD. ')
            if status == 'orange':
                message += 'A component was too large for a complete audit.'
            else:
                message += 'Todos los componentes quedaron manifold.'

            payload = store_diagnostic(
                final_temp, status, 'completed', message, final_report)
            store_boolean_preflight(final_temp, 'drill', {
                'status': status,
                'checked': bool(final_report.get('checked')),
                'solid': True,
                'repaired': False,
                'repair_methods': [],
                'bad_edges': final_report.get('bad_edges', 0),
                'degenerate_faces': final_report.get('degenerate_faces', 0),
                'polygons': final_report.get('polygons'),
                'solver': 'MANIFOLD',
                'message': message,
                'component_operations': int(operations),
                'combined_cutter': True,
            })
            _dsg_report(self, {'INFO'}, message, message)
            return {'FINISHED'}

        except Exception as exc:
            # La guía original sigue intacta. Solo se eliminan copias y cutters.
            for obj in list(temp_objects):
                safe_remove_object(obj)
            if _valid_obj(batch_cutter):
                safe_remove_object(batch_cutter)
            if _valid_obj(guide):
                store_diagnostic(
                    guide, 'red', diagnostic.get('phase', 'cancelled'),
                    failure or str(exc))
            _dsg_report(self, {'ERROR'}, f'Drill canceled: {failure or str(exc)}. '
                'The original guide was preserved.', f'Drill cancelado: {failure or str(exc)}. '
                'La guía original se conservó.')
            return {'CANCELLED'}


class DSG_OT_PrepareAndCreateDrillChannels(Operator):
    bl_idname = 'dsg.prepare_and_create_drill_channels'
    bl_label = 'Prepare and Create Drill Channels'
    bl_description = (
        'Runs the drill preparation workflow as a single action: optional cleanup, '
        'guide check, and drill-channel creation')
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_DRILL,
                action_en='Cannot prepare the drill channels',
                action_es='No se pueden preparar los canales de fresado'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'No active guide found', 'No se encontró una guía activa')
            return {'CANCELLED'}
        if count_implants(props) <= 0:
            _dsg_report(self, {'ERROR'}, 'No implants available', 'No hay implantes disponibles')
            return {'CANCELLED'}

        if bool(getattr(props, 'drill_protection_auto', True)):
            result = bpy.ops.dsg.protect_drill_insertion('EXEC_DEFAULT')
            if 'CANCELLED' in result:
                _dsg_report(
                    self, {'ERROR'},
                    'Automatic drill cleanup failed before channel creation',
                    'La limpieza automática del fresado falló antes de crear los canales')
                return {'CANCELLED'}

        result = bpy.ops.dsg.run_boolean_preflight('EXEC_DEFAULT', target='drill')
        if 'CANCELLED' in result:
            _dsg_report(
                self, {'ERROR'},
                'Guide check failed before creating drill channels',
                'La comprobación de la guía falló antes de crear los canales de fresado')
            return {'CANCELLED'}

        result = bpy.ops.dsg.add_drill_channel('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            _dsg_report(
                self, {'ERROR'},
                'Drill channels could not be created',
                'No se pudieron crear los canales de fresado')
            return {'CANCELLED'}

        _dsg_report(
            self, {'INFO'},
            'Guide prepared and drill channels created',
            'Guía preparada y canales de fresado creados')
        return {'FINISHED'}


class DSG_OT_ConfirmDrill(Operator):
    bl_idname = "dsg.confirm_drill"
    bl_label  = "Confirm Channels → Final Boolean"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_DRILL,
                action_en='Cannot confirm the drill channels',
                action_es='No se pueden confirmar los canales de fresado'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if not _valid_obj(props.guide_obj):
            _dsg_report(self, {'ERROR'}, "Create the channel first", "Genera el canal primero")
            return {'CANCELLED'}
        if int(props.guide_obj.get('DSG_drill_channel_count', 0) or 0) <= 0:
            _dsg_report(self, {'ERROR'}, "Create the drill channels before confirming", "Genera los canales de fresado antes de confirmar")
            return {'CANCELLED'}

        passive = prepare_final_cut_references(context, props, show_passive=True)
        if not _valid_obj(passive):
            _dsg_report(
                self, {'ERROR'},
                'The confirmed retentive model is required before the final Boolean',
                'Se necesita el modelo retentivo confirmado antes de la booleana final')
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, "Channel confirmed: cut prepared as DSG_Guide - DSG_PassiveCombined", "Canal confirmado: corte preparado como DSG_Guide - DSG_PassiveCombined")
        try:
            props.guide_obj['DSG_drill_channels_confirmed'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        drill_signature = _workflow_object_signature(props.guide_obj)
        if _workflow_signature_changed(context.scene, WORKFLOW_DRILL_SIGNATURE_KEY, drill_signature):
            _invalidate_workflow_after(context, STEP_DRILL, reason='drill_channels_changed')
        _workflow_store_signature(context.scene, WORKFLOW_DRILL_SIGNATURE_KEY, drill_signature)
        props.current_step = STEP_FINAL_CUT
        return {'FINISHED'}



# ─────────────────────────────────────────────────────────────
# Irrigation v6.4 — eje interno primero
# ─────────────────────────────────────────────────────────────

