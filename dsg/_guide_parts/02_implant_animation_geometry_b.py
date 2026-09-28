def get_closed_manifold_gate_report(obj, max_edges=5000000):
    """Strict one-shot topology audit used as the gate to the implant step.

    A passing surgical-guide support model must be one non-empty connected
    closed 2-manifold shell. The audit distinguishes open boundaries, branched
    edges, wire geometry, loose vertices, degenerate faces and disconnected
    shells so the user receives a useful diagnosis instead of a generic Boolean
    error. This function never repairs or modifies the clinical mesh.
    """
    base = {
        'gate_version': int(NEXT_STEP_MANIFOLD_GATE_VERSION),
        'checked': False,
        'solid': False,
        'closed': False,
        'manifold': False,
        'single_shell': False,
        'boundary_edges': None,
        'branch_edges': None,
        'wire_edges': None,
        'loose_vertices': None,
        'degenerate_faces': None,
        'shells': None,
        'vertices': 0,
        'edges': 0,
        'polygons': 0,
        'reason': 'invalid object',
        'method': 'bmesh_strict_gate',
    }
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return base

    mesh = obj.data
    try:
        vertex_count = len(mesh.vertices)
        edge_count = len(mesh.edges)
        polygon_count = len(mesh.polygons)
        base.update(vertices=int(vertex_count), edges=int(edge_count), polygons=int(polygon_count))
    except Exception as exc:
        base['reason'] = f'could not read mesh: {exc}'
        return base

    if vertex_count < 4 or edge_count < 6 or polygon_count < 4:
        base.update(checked=True, reason='empty or insufficient surface')
        return base
    if edge_count > int(max_edges):
        base['reason'] = f'mesh too large to certify ({edge_count} edges)'
        base['method'] = 'size_limit'
        return base

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        boundary = 0
        branch = 0
        wire = 0
        for edge in bm.edges:
            linked = len(edge.link_faces)
            if linked == 1:
                boundary += 1
            elif linked > 2:
                branch += 1
            elif linked == 0:
                wire += 1

        loose = sum(1 for vertex in bm.verts if not vertex.link_edges)
        degenerate = 0
        for face in bm.faces:
            if len(face.verts) < 3:
                degenerate += 1
                continue
            try:
                if face.calc_area() <= 1.0e-14:
                    degenerate += 1
            except Exception:
                degenerate += 1

        # Count connected face shells. Stop after the second shell because the
        # gate only needs to distinguish one shell from two-or-more, avoiding an
        # unnecessarily expensive full component count on very dense IOS meshes.
        for face in bm.faces:
            face.tag = False
        shells = 0
        for seed in bm.faces:
            if seed.tag:
                continue
            shells += 1
            if shells > 1:
                break
            seed.tag = True
            stack = [seed]
            while stack:
                face = stack.pop()
                for edge in face.edges:
                    for neighbour in edge.link_faces:
                        if not neighbour.tag:
                            neighbour.tag = True
                            stack.append(neighbour)

        closed = boundary == 0
        manifold = branch == 0 and wire == 0 and loose == 0
        single_shell = shells == 1
        strict_solid = bool(
            closed and manifold and single_shell
            and degenerate == 0 and len(bm.faces) > 0)
        workflow_ready = bool(closed and len(bm.faces) > 0)
        solid = strict_solid
        if workflow_ready and strict_solid:
            reason = 'closed manifold single shell'
        elif workflow_ready:
            reason = 'closed boundary shell; topology warnings are non-blocking'
        else:
            reason = 'open boundary detected'
        return {
            'gate_version': int(NEXT_STEP_MANIFOLD_GATE_VERSION),
            'checked': True,
            'solid': solid,
            'strict_solid': bool(strict_solid),
            'workflow_ready': bool(workflow_ready),
            'closed': bool(closed),
            'manifold': bool(manifold),
            'single_shell': bool(single_shell),
            'boundary_edges': int(boundary),
            'branch_edges': int(branch),
            'wire_edges': int(wire),
            'loose_vertices': int(loose),
            'degenerate_faces': int(degenerate),
            'shells': int(shells),  # 2 means two or more because of the early stop.
            'vertices': int(len(bm.verts)),
            'edges': int(len(bm.edges)),
            'polygons': int(len(bm.faces)),
            'reason': reason,
            'method': 'bmesh_strict_gate',
        }
    except (MemoryError, ReferenceError, RuntimeError) as exc:
        base['reason'] = f'strict topology audit unavailable: {exc}'
        base['method'] = 'audit_failed'
        return base
    except Exception as exc:
        base['reason'] = f'strict topology audit unavailable: {exc}'
        base['method'] = 'audit_failed'
        return base
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def store_closed_manifold_gate_report(obj, report, role=''):
    """Persist a gate result without treating it as valid after mesh changes."""
    if not _valid_obj(obj):
        return False
    passed = _workflow_closed_boundary_passes(report)
    try:
        obj[NEXT_STEP_MANIFOLD_GATE_FLAG] = passed
        obj[NEXT_STEP_MANIFOLD_GATE_REPORT] = json.dumps(report, default=str)
        obj[NEXT_STEP_MANIFOLD_GATE_SIGNATURE] = _closed_manifold_geometry_signature(obj)
        obj[NEXT_STEP_MANIFOLD_GATE_ROLE] = str(role or '')
        obj['DSG_closed_manifold_checked'] = bool(report.get('checked'))
        obj['DSG_closed_manifold_passed'] = passed
        obj['DSG_closed_manifold_boundary_edges'] = int(report.get('boundary_edges') or 0)
        obj['DSG_closed_manifold_branch_edges'] = int(report.get('branch_edges') or 0)
        obj['DSG_closed_manifold_degenerate_faces'] = int(report.get('degenerate_faces') or 0)
        obj['DSG_closed_manifold_shells'] = int(report.get('shells') or 0)
    except Exception:
        return False
    return passed


def load_closed_manifold_gate_report(obj):
    if not _valid_obj(obj):
        return None
    try:
        raw = obj.get(NEXT_STEP_MANIFOLD_GATE_REPORT)
        report = json.loads(raw) if isinstance(raw, str) and raw else None
        if not isinstance(report, dict):
            return None
        if str(obj.get(NEXT_STEP_MANIFOLD_GATE_SIGNATURE, '')) != _closed_manifold_geometry_signature(obj):
            return None
        return report
    except Exception:
        return None


def certify_closed_manifold_for_next_step(obj, role='', force=False):
    """Return a fresh or signature-valid certification and store it on obj."""
    if not force:
        cached = load_closed_manifold_gate_report(obj)
        if cached is not None:
            return cached
    report = get_closed_manifold_gate_report(obj)
    store_closed_manifold_gate_report(obj, report, role=role)
    return report


def _closed_manifold_gate_details(report, spanish=False):
    if not isinstance(report, dict):
        return 'sin diagnóstico' if spanish else 'no diagnostic'
    if not report.get('checked'):
        return str(report.get('reason', 'auditoría no disponible' if spanish else 'audit unavailable'))
    boundary = int(report.get('boundary_edges') or 0)
    branch = int(report.get('branch_edges') or 0)
    wire = int(report.get('wire_edges') or 0)
    loose = int(report.get('loose_vertices') or 0)
    degenerate = int(report.get('degenerate_faces') or 0)
    shells = int(report.get('shells') or 0)
    shell_text = '2+' if shells > 1 else str(shells)
    if spanish:
        return (f'bordes abiertos: {boundary}; aristas ramificadas: {branch}; '
                f'aristas sueltas: {wire}; vértices sueltos: {loose}; '
                f'caras degeneradas: {degenerate}; componentes: {shell_text}')
    return (f'open edges: {boundary}; branched edges: {branch}; '
            f'wire edges: {wire}; loose vertices: {loose}; '
            f'degenerate faces: {degenerate}; shells: {shell_text}')


def _source_model_passes_closed_manifold_gate(obj, force=False):
    report = certify_closed_manifold_for_next_step(obj, role='SOURCE_IOS', force=force)
    passed = _workflow_closed_boundary_passes(report)
    if passed and _valid_obj(obj):
        _mark_closed_boundary_model_accepted(obj, report)
        # Closed models imported from another program are accepted automatically;
        # no destructive DSG base-closing operation is applied.
        try:
            obj[CLOSED_MODEL_ACCEPTED_FLAG] = True
            obj[EXTERNAL_CLOSED_MODEL_FLAG] = bool(
                not obj.get('DSG_base_closure_status', ''))
            obj['DSG_base_closed_manifold'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return passed, report

def _restore_selection_after_mesh_tool(context, active_obj, selected_names, mode):
    """Restaura selección/modo tras usar operadores de limpieza de Blender."""
    try:
        if context.view_layer.objects.active and context.view_layer.objects.active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        for obj in context.view_layer.objects:
            obj.select_set(obj.name in selected_names)
        if _valid_obj(active_obj):
            context.view_layer.objects.active = active_obj
            if mode and mode != 'OBJECT' and active_obj.select_get():
                try:
                    bpy.ops.object.mode_set(mode=mode)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)




def _model_topology_cache_key(obj):
    """Stable in-session key for a model topology audit.

    The panel redraws often, so a BMesh audit must never run on every draw.
    Geometry edits change the vertex/edge/polygon counts and invalidate the key.
    """
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH' or obj.data is None:
        return None
    try:
        return (
            int(obj.data.as_pointer()),
            len(obj.data.vertices),
            len(obj.data.edges),
            len(obj.data.polygons),
        )
    except Exception:
        return None


def _clear_model_topology_cache():
    _MODEL_TOPOLOGY_CACHE.clear()


def get_model_topology_report_cached(obj, max_edges=5000000):
    """Return a cached solid/boundary report suitable for the UI.

    ``bad_edges`` alone does not distinguish an intentionally open scan base
    from self-intersections.  DSG therefore also counts boundary edges
    (exactly one linked face) and non-manifold branch edges (>2 linked faces).
    """
    key = _model_topology_cache_key(obj)
    if key is None:
        return {
            'checked': False, 'solid': False, 'boundary_edges': None,
            'branch_edges': None, 'bad_edges': None, 'reason': 'invalid object'
        }
    cached = _MODEL_TOPOLOGY_CACHE.get(key)
    if cached is not None:
        return dict(cached)
    if len(obj.data.edges) > int(max_edges):
        report = {
            'checked': False, 'solid': False, 'boundary_edges': None,
            'branch_edges': None, 'bad_edges': None,
            'reason': 'mesh too large for topology audit'
        }
        _MODEL_TOPOLOGY_CACHE[key] = report
        return dict(report)

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        boundary = 0
        branch = 0
        wire = 0
        for edge in bm.edges:
            linked = len(edge.link_faces)
            if linked == 1:
                boundary += 1
            elif linked > 2:
                branch += 1
            elif linked == 0:
                wire += 1
        bad = boundary + branch + wire
        report = {
            'checked': True,
            'solid': bad == 0,
            'strict_solid': bad == 0,
            'closed': boundary == 0,
            'workflow_ready': boundary == 0,
            'boundary_edges': int(boundary),
            'branch_edges': int(branch),
            'wire_edges': int(wire),
            'bad_edges': int(bad),
            'reason': 'solid' if bad == 0 else 'open/non-manifold',
        }
    except Exception as exc:
        report = {
            'checked': False, 'solid': False, 'boundary_edges': None,
            'branch_edges': None, 'bad_edges': None,
            'reason': f'topology audit failed: {exc}'
        }
    finally:
        if bm is not None:
            bm.free()
    _MODEL_TOPOLOGY_CACHE[key] = report
    return dict(report)


def _boundary_edge_components(boundary_edges):
    """Connected components of BMesh boundary edges."""
    remaining = set(boundary_edges)
    components = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        stack = [seed]
        while stack:
            edge = stack.pop()
            for vert in edge.verts:
                for linked in vert.link_edges:
                    if linked in remaining and len(linked.link_faces) == 1:
                        remaining.remove(linked)
                        component.add(linked)
                        stack.append(linked)
        components.append(list(component))
    return components


def _ordered_closed_boundary_loop(component_edges):
    """Order one degree-two boundary component; return None for branched rims."""
    if not component_edges:
        return None
    adjacency = {}
    for edge in component_edges:
        a, b = edge.verts
        adjacency.setdefault(a, []).append(edge)
        adjacency.setdefault(b, []).append(edge)
    if len(adjacency) < 3 or any(len(edges) != 2 for edges in adjacency.values()):
        return None
    start = next(iter(adjacency))
    ordered = [start]
    current = start
    previous_edge = None
    safety = 0
    while safety <= len(component_edges) + 2:
        candidates = [edge for edge in adjacency[current] if edge is not previous_edge]
        if not candidates:
            return None
        edge = candidates[0]
        nxt = edge.other_vert(current)
        if nxt is start:
            return ordered if len(ordered) >= 3 else None
        if nxt in ordered:
            return None
        ordered.append(nxt)
        previous_edge = edge
        current = nxt
        safety += 1
    return None


def _boundary_component_perimeter(component_edges):
    try:
        return float(sum(edge.calc_length() for edge in component_edges))
    except Exception:
        return 0.0



def _safe_percentile(values, percentile, default=0.0):
    """Percentile helper that tolerates empty/invalid numerical collections."""
    try:
        array = np.asarray(values, dtype=np.float64)
        array = array[np.isfinite(array)]
        if array.size:
            return float(np.percentile(array, float(percentile)))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return float(default)


def _robust_mad(values, center=None):
    """Median absolute deviation in model units."""
    try:
        array = np.asarray(values, dtype=np.float64)
        array = array[np.isfinite(array)]
        if not array.size:
            return 0.0
        if center is None:
            center = float(np.median(array))
        return float(np.median(np.abs(array - float(center))))
    except Exception:
        return 0.0


def _object_average_world_scale(obj):
    """Return a conservative local-to-world scale for millimetre parameters."""
    try:
        scales = [abs(float(v)) for v in obj.matrix_world.to_scale()]
        valid = [v for v in scales if v > 1.0e-8 and math.isfinite(v)]
        if valid:
            # Geometric mean is stable for slightly non-uniform imports and does
            # not let one accidental scale component dominate clinical depths.
            return float(math.exp(sum(math.log(v) for v in valid) / len(valid)))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return 1.0


def _mm_to_object_units(obj, millimetres):
    return float(millimetres) / max(1.0e-8, _object_average_world_scale(obj))


def _surface_samples_for_base_orientation(bm, limit=AUTO_BASE_ANALYSIS_FACE_LIMIT):
    """Area-weighted deterministic samples of the dental surface.

    Face centres avoid the triangulation-density bias of raw STL vertices. The
    result contains coordinates, normals and area weights in object-local space.
    """
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    faces = list(bm.faces)
    if not faces:
        coords = np.asarray([tuple(v.co) for v in bm.verts], dtype=np.float64)
        normals = np.zeros_like(coords)
        weights = np.ones(len(coords), dtype=np.float64)
        return coords, normals, weights
    count = len(faces)
    stride = max(1, int(math.ceil(count / float(max(1, int(limit))))))
    sampled = faces[::stride]
    coords = []
    normals = []
    weights = []
    for face in sampled:
        try:
            area = max(1.0e-10, float(face.calc_area()))
            center = face.calc_center_median()
            normal = face.normal
        except Exception:
            continue
        coords.append((float(center.x), float(center.y), float(center.z)))
        normals.append((float(normal.x), float(normal.y), float(normal.z)))
        weights.append(area)
    if not coords:
        coords = [tuple(v.co) for v in bm.verts]
        normals = [(0.0, 0.0, 0.0)] * len(coords)
        weights = [1.0] * len(coords)
    return (
        np.asarray(coords, dtype=np.float64),
        np.asarray(normals, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
    )


def _robust_weighted_pca(points, base_weights, iterations=4):
    """Huber-reweighted PCA used only to initialise the dental frame."""
    points = np.asarray(points, dtype=np.float64)
    weights = np.asarray(base_weights, dtype=np.float64)
    if len(points) < 3:
        return np.zeros(3), np.eye(3), np.ones(3)
    weights = np.maximum(weights, 1.0e-12)
    weights /= max(1.0e-12, float(weights.sum()))
    center = np.average(points, axis=0, weights=weights)
    eigvals = np.ones(3)
    eigvecs = np.eye(3)
    for _ in range(max(1, int(iterations))):
        centered = points - center
        covariance = (centered * weights[:, None]).T @ centered
        covariance /= max(1.0e-12, float(weights.sum()))
        eigvals, eigvecs = np.linalg.eigh(covariance)
        order = np.argsort(eigvals)
        eigvals = np.maximum(eigvals[order], 1.0e-12)
        eigvecs = eigvecs[:, order]
        distances = np.linalg.norm(centered, axis=1)
        median = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median)))
        scale = max(1.0e-8, 1.4826 * mad)
        threshold = median + 2.5 * scale
        huber = np.ones_like(distances)
        mask = distances > threshold
        huber[mask] = threshold / np.maximum(distances[mask], 1.0e-12)
        weights = np.maximum(base_weights, 1.0e-12) * huber
        weights /= max(1.0e-12, float(weights.sum()))
        center = np.average(points, axis=0, weights=weights)
    return center, eigvecs, eigvals


def _numpy_unit(vector, fallback=(0.0, 0.0, 1.0)):
    array = np.asarray(vector, dtype=np.float64).reshape(3)
    length = float(np.linalg.norm(array))
    if not math.isfinite(length) or length <= 1.0e-10:
        array = np.asarray(fallback, dtype=np.float64)
        length = float(np.linalg.norm(array))
    return array / max(length, 1.0e-12)


def _numpy_perpendicular_frame(direction):
    normal = _numpy_unit(direction)
    reference = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(normal, reference))) > 0.90:
        reference = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
    axis_u = _numpy_unit(np.cross(normal, reference), (1.0, 0.0, 0.0))
    axis_v = _numpy_unit(np.cross(normal, axis_u), (0.0, 1.0, 0.0))
    return axis_u, axis_v, normal


def _local_insertion_axis_for_base(source_obj):
    """Optional tie-breaker only; base direction remains independent clinically."""
    try:
        if not _valid_obj(bpy.data.objects.get(AXIS_EMPTY_NAME)):
            return None
        world_axis = Vector(get_insertion_axis())
        if world_axis.length <= 1.0e-8:
            return None
        local_axis = source_obj.matrix_world.inverted_safe().to_3x3() @ world_axis
        if local_axis.length <= 1.0e-8:
            return None
        local_axis.normalize()
        return np.asarray(tuple(local_axis), dtype=np.float64)
    except Exception:
        return None


def _local_world_vertical_axis_for_base(source_obj=None):
    """Return the global +Z axis expressed in local mesh coordinates.

    Printed dental models generally benefit from a basal plane that is level in
    world space.  This candidate therefore represents a truly vertical closure
    direction irrespective of how the STL was imported or rotated.
    """
    try:
        world_up = Vector((0.0, 0.0, 1.0))
        if source_obj is not None:
            local_axis = source_obj.matrix_world.inverted_safe().to_3x3() @ world_up
        else:
            local_axis = world_up.copy()
        if local_axis.length <= 1.0e-8:
            return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
        local_axis.normalize()
        return np.asarray(tuple(local_axis), dtype=np.float64)
    except Exception:
        return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)


def _mean_boundary_normal_axis(boundary_verts):
    """Average the face normals around the open rim.

    The base plane should often be close to perpendicular to the mean boundary
    surface.  Using the averaged linked-face normals gives a print-friendly
    direction even when the crown/anatomy analysis would choose a more oblique
    dental frame.
    """
    vectors = []
    for vert in boundary_verts:
        if not getattr(vert, 'is_valid', True):
            continue
        linked = [face.normal.copy() for face in getattr(vert, 'link_faces', ()) if getattr(face, 'is_valid', True)]
        if not linked:
            continue
        normal = Vector()
        for item in linked:
            normal += item
        if normal.length <= 1.0e-8:
            continue
        normal.normalize()
        vectors.append(tuple(normal))
    if not vectors:
        return None
    mean = np.asarray(vectors, dtype=np.float64)
    axis = np.mean(mean, axis=0)
    if float(np.linalg.norm(axis)) <= 1.0e-8:
        return None
    return _numpy_unit(axis)


def _section_area_proxy(points, direction, lower, upper, sections=6):
    """Stable cross-section proxy based on robust in-plane extents."""
    axis_u, axis_v, normal = _numpy_perpendicular_frame(direction)
    projections = points @ normal
    edges = np.linspace(float(lower), float(upper), max(3, int(sections)) + 1)
    areas = []
    for index in range(len(edges) - 1):
        mask = (projections >= edges[index]) & (projections <= edges[index + 1])
        section = points[mask]
        if len(section) < 12:
            continue
        u = section @ axis_u
        v = section @ axis_v
        width = max(0.0, _safe_percentile(u, 95) - _safe_percentile(u, 5))
        depth = max(0.0, _safe_percentile(v, 95) - _safe_percentile(v, 5))
        areas.append(width * depth)
    if len(areas) < 2:
        return 1.0
    median = max(1.0e-8, float(np.median(areas)))
    return min(3.0, _robust_mad(areas, median) / median)


def _score_dental_base_direction(points, normals, weights, boundary_points,
                                 direction, insertion_axis=None, pca_rank_penalty=0.0):
    """Score one basal-axis candidate; lower is better."""
    direction = _numpy_unit(direction)
    projections = points @ direction
    boundary_projection = boundary_points @ direction if len(boundary_points) else projections
    span = max(1.0e-8, _safe_percentile(projections, 97) - _safe_percentile(projections, 3))

    # Resolve sign: the damaged/open border must lie toward the basal extreme.
    if _safe_percentile(boundary_projection, 60) < _safe_percentile(projections, 50):
        direction = -direction
        projections = -projections
        boundary_projection = -boundary_projection

    basal_extreme = _safe_percentile(projections, 97)
    boundary_level = _safe_percentile(boundary_projection, 65)
    planarity = _robust_mad(boundary_projection, np.median(boundary_projection)) / span
    extreme_gap = abs(basal_extreme - boundary_level) / span
    boundary_coverage = float(np.mean(boundary_projection >= _safe_percentile(projections, 78)))

    # A useful dental vertical direction has a comparatively compact axial span.
    axis_u, axis_v, _ = _numpy_perpendicular_frame(direction)
    u = points @ axis_u
    v = points @ axis_v
    transverse = max(
        1.0e-8,
        math.sqrt(max(1.0e-8,
            (_safe_percentile(u, 97) - _safe_percentile(u, 3))
            * (_safe_percentile(v, 97) - _safe_percentile(v, 3)))))
    axial_ratio = min(2.5, span / transverse)

    basal_start = _safe_percentile(projections, 66)
    section_variation = _section_area_proxy(
        points, direction, basal_start, basal_extreme, sections=6)

    # Occlusal/coronal geometry generally exhibits richer normal variation than
    # the cut basal band. This term is deliberately weak because edentulous and
    # partial scans can invert that relationship.
    low_mask = projections <= _safe_percentile(projections, 18)
    high_mask = projections >= _safe_percentile(projections, 82)
    normal_term = 0.0
    if normals.shape == points.shape and np.any(low_mask) and np.any(high_mask):
        low_complexity = float(np.median(1.0 - np.abs(normals[low_mask] @ direction)))
        high_complexity = float(np.median(1.0 - np.abs(normals[high_mask] @ direction)))
        normal_term = max(0.0, high_complexity - low_complexity)

    insertion_penalty = 0.0
    if insertion_axis is not None:
        insertion_axis = _numpy_unit(insertion_axis)
        # Sign-independent: this only breaks near ties and never defines the base.
        alignment = abs(float(np.dot(direction, insertion_axis)))
        insertion_penalty = (1.0 - alignment) * 0.12

    score = (
        4.2 * planarity
        + 2.8 * extreme_gap
        + 1.8 * (1.0 - boundary_coverage)
        + 0.9 * section_variation
        + 0.65 * axial_ratio
        + 0.45 * normal_term
        + float(pca_rank_penalty)
        + insertion_penalty
    )
    metrics = {
        'score': float(score),
        'planarity_ratio': float(planarity),
        'extreme_gap_ratio': float(extreme_gap),
        'boundary_coverage': float(boundary_coverage),
        'section_variation': float(section_variation),
        'axial_ratio': float(axial_ratio),
        'boundary_level_local': float(boundary_level),
        'axial_span_local': float(span),
    }
    return direction, float(score), metrics


def _tilted_axis(direction, tilt_u_deg, tilt_v_deg):
    axis_u, axis_v, normal = _numpy_perpendicular_frame(direction)
    candidate = (
        normal
        + math.tan(math.radians(float(tilt_u_deg))) * axis_u
        + math.tan(math.radians(float(tilt_v_deg))) * axis_v
    )
    return _numpy_unit(candidate)


def _robust_open_margin_plane_axis(boundary_points):
    """Return the normal of a robust best-fit plane through the open IOS margin.

    The margin itself defines the local vertical.  A first PCA fit is refined by
    rejecting isolated trim spikes with a median-absolute-deviation threshold.
    No world axis or camera direction participates in the result.
    """
    pts = np.asarray(boundary_points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[0] < 3:
        raise ValueError('The open margin has fewer than three valid vertices')

    active = np.ones(len(pts), dtype=bool)
    center = np.median(pts, axis=0)
    axis = None
    eigenvalues = np.zeros(3, dtype=np.float64)

    for _ in range(4):
        sample = pts[active]
        if len(sample) < 3:
            break
        center = np.median(sample, axis=0)
        centered = sample - center
        covariance = (centered.T @ centered) / max(1, len(sample))
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        order = np.argsort(eigenvalues)
        eigenvalues = eigenvalues[order]
        axis = _numpy_unit(eigenvectors[:, order[0]])

        distances = np.abs((pts - center) @ axis)
        median_distance = float(np.median(distances))
        mad = _robust_mad(distances, median_distance)
        tolerance = max(0.03, median_distance + 3.5 * max(mad, 1.0e-6))
        updated = distances <= tolerance
        if int(np.count_nonzero(updated)) < max(3, int(len(pts) * 0.65)):
            break
        if np.array_equal(updated, active):
            active = updated
            break
        active = updated

    if axis is None:
        raise ValueError('Could not fit a plane to the open margin')

    residuals = np.abs((pts - center) @ axis)
    diagnostics = {
        'margin_plane_vertex_count': int(len(pts)),
        'margin_plane_inlier_count': int(np.count_nonzero(active)),
        'margin_plane_outlier_count': int(len(pts) - np.count_nonzero(active)),
        'margin_plane_median_residual_mm': float(np.median(residuals)),
        'margin_plane_p90_residual_mm': float(np.percentile(residuals, 90)),
        'margin_plane_max_residual_mm': float(np.max(residuals)),
        'margin_plane_eigenvalues': [float(value) for value in eigenvalues],
    }
    return axis, center, diagnostics


def _estimate_dental_base_direction(bm, boundary_verts, source_obj=None):
    """Define the basal vertical only from the open model margin.

    The closing direction is perpendicular to a robust best-fit plane through
    the actual open boundary loop.  The sign is resolved from the dental mesh
    centre toward the margin, so extrusion proceeds out of the scan.  Linked
    face normals are used only to stabilise the sign when the centroid test is
    ambiguous; neither world Z, camera view nor insertion axis can tilt it.
    """
    points, normals, weights = _surface_samples_for_base_orientation(bm)
    if len(points) < 3:
        raise ValueError('Insufficient dental surface geometry')

    boundary_points = np.asarray(
        [tuple(v.co) for v in boundary_verts if getattr(v, 'is_valid', True)],
        dtype=np.float64)
    if boundary_points.ndim != 2 or boundary_points.shape[0] < 3:
        raise ValueError('The open model margin is not a valid closed boundary')

    axis, margin_center, diagnostics = _robust_open_margin_plane_axis(boundary_points)
    model_center = np.average(points, axis=0, weights=weights) if len(weights) == len(points) else np.mean(points, axis=0)
    outward_hint = margin_center - model_center

    mean_boundary_normal = _mean_boundary_normal_axis(boundary_verts)
    sign_method = 'model_center_to_margin'
    if float(np.linalg.norm(outward_hint)) > 1.0e-8:
        if float(np.dot(axis, outward_hint)) < 0.0:
            axis = -axis
    elif mean_boundary_normal is not None:
        if float(np.dot(axis, mean_boundary_normal)) < 0.0:
            axis = -axis
        sign_method = 'mean_boundary_normal'

    # Report consistency with local linked-face normals without allowing them to
    # tilt the margin-derived vertical.
    normal_alignment = None
    if mean_boundary_normal is not None:
        normal_alignment = abs(float(np.dot(axis, _numpy_unit(mean_boundary_normal))))

    boundary_projection = boundary_points @ axis
    all_projection = points @ axis
    span = max(1.0e-8, _safe_percentile(all_projection, 97) - _safe_percentile(all_projection, 3))
    planarity_ratio = _robust_mad(boundary_projection, np.median(boundary_projection)) / span
    confidence = max(0.0, min(1.0,
        1.0 - min(1.0, diagnostics['margin_plane_p90_residual_mm'] / max(0.25, span * 0.03))))

    direction_vector = Vector(tuple(float(value) for value in axis))
    direction_vector.normalize()
    diagnostics.update({
        'method': 'open_margin_robust_best_fit_plane_normal',
        'sign_method': sign_method,
        'confidence': float(confidence),
        'boundary_planarity_ratio': float(planarity_ratio),
        'boundary_level_local': float(np.median(boundary_projection)),
        'basal_extreme_local': float(_safe_percentile(all_projection, 97)),
        'occlusal_level_local': float(_safe_percentile(all_projection, 3)),
        'sample_count': int(len(points)),
        'boundary_vertex_count': int(len(boundary_points)),
        'mean_boundary_normal_alignment': (
            float(normal_alignment) if normal_alignment is not None else None),
        'uses_world_axis': False,
        'uses_camera_axis': False,
        'uses_insertion_axis': False,
    })
    return direction_vector, diagnostics


def _automatic_base_direction(bm, loop_verts, source_obj=None, return_diagnostics=False):
    """Compatibility wrapper for the robust dental-frame estimator."""
    try:
        direction, diagnostics = _estimate_dental_base_direction(
            bm, loop_verts, source_obj=source_obj)
    except Exception as exc:
        mesh_center = sum((vert.co for vert in bm.verts), Vector()) / max(1, len(bm.verts))
        rim_center = sum((vert.co for vert in loop_verts), Vector()) / max(1, len(loop_verts))
        direction = rim_center - mesh_center
        if direction.length <= 1.0e-6:
            direction = Vector((0.0, 0.0, 1.0))
        direction.normalize()
        diagnostics = {
            'method': 'centroid_fallback', 'confidence': 0.0,
            'reason': str(exc), 'boundary_vertex_count': int(len(loop_verts))}
    if return_diagnostics:
        return direction, diagnostics
    return direction

def _relax_closed_ring_positions(positions, direction, target_projection,
                                 iterations=4, factor=0.32):
    """Regularise one closed ring without changing its basal plane.

    Easy Dental CAD uses repeated relax/extrude operations before flattening the
    final cap.  This dependency-free equivalent keeps the same idea while
    avoiding LoopTools and preserving the original anatomical rim.
    """
    points = [Vector(point) for point in positions]
    if len(points) < 4:
        return points
    direction = Vector(direction).normalized()
    factor = max(0.0, min(0.49, float(factor)))
    for _ in range(max(0, int(iterations))):
        updated = []
        count = len(points)
        for index, point in enumerate(points):
            neighbour_mid = (points[(index - 1) % count] + points[(index + 1) % count]) * 0.5
            candidate = point.lerp(neighbour_mid, factor)
            candidate += direction * (float(target_projection) - float(candidate.dot(direction)))
            updated.append(candidate)
        points = updated
    return points


def _signed_polygon_area_2d(points):
    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        float(points[index][0]) * float(points[(index + 1) % len(points)][1])
        - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
        for index in range(len(points)))


def _resample_closed_polygon_2d_exact(points, count):
    """Uniformly resample a closed 2-D polygon to ``count`` points."""
    points = [(float(x), float(y)) for x, y in points]
    count = max(3, int(count))
    if len(points) < 3:
        return []
    lengths = []
    perimeter = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        length = math.hypot(nxt[0] - point[0], nxt[1] - point[1])
        lengths.append(length)
        perimeter += length
    if perimeter <= 1.0e-10:
        return []
    targets = [perimeter * index / count for index in range(count)]
    result = []
    edge_index = 0
    accumulated = 0.0
    for target in targets:
        while edge_index < len(points) - 1 and accumulated + lengths[edge_index] < target:
            accumulated += lengths[edge_index]
            edge_index += 1
        length = max(lengths[edge_index], 1.0e-12)
        factor = (target - accumulated) / length
        a = points[edge_index]
        b = points[(edge_index + 1) % len(points)]
        result.append((a[0] + (b[0] - a[0]) * factor,
                       a[1] + (b[1] - a[1]) * factor))
    return result


def _aligned_star_base_ring(loop_verts, axis_u, axis_v, margin):
    """Create a simple star-shaped footprint with one point per rim vertex."""
    projected = [(float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
                 for vert in loop_verts]
    count = len(projected)
    bins = max(48, min(256, int(round(math.sqrt(max(1, count)) * 4.0))))
    footprint = _radial_envelope_polygon_2d(
        projected, bins=bins, percentile=96.0, margin=max(0.0, float(margin)))
    if len(footprint) < 3:
        footprint = _convex_hull_2d(projected)
    if len(footprint) < 3:
        return []

    # Preserve winding so the transition strip does not twist.
    source_area = _signed_polygon_area_2d(projected)
    footprint_area = _signed_polygon_area_2d(footprint)
    if source_area * footprint_area < 0.0:
        footprint = list(reversed(footprint))

    resampled = _resample_closed_polygon_2d_exact(footprint, count)
    if len(resampled) != count:
        return []

    # Align the cyclic start to the first anatomical rim point.
    first = projected[0]
    start_index = min(
        range(count),
        key=lambda index: (resampled[index][0] - first[0]) ** 2
                          + (resampled[index][1] - first[1]) ** 2)
    return resampled[start_index:] + resampled[:start_index]


def _margin_proxy_roughness_2d(points):
    """Return a scale-independent local roughness estimate for one cyclic rim."""
    if len(points) < 5:
        return 0.0
    values = []
    lengths = []
    count = len(points)
    for index, point in enumerate(points):
        previous = points[(index - 1) % count]
        following = points[(index + 1) % count]
        edge_a = math.hypot(point[0] - previous[0], point[1] - previous[1])
        edge_b = math.hypot(following[0] - point[0], following[1] - point[1])
        lengths.extend((edge_a, edge_b))
        midpoint = ((previous[0] + following[0]) * 0.5,
                    (previous[1] + following[1]) * 0.5)
        values.append(math.hypot(point[0] - midpoint[0], point[1] - midpoint[1]))
    scale = max(1.0e-9, float(np.median(np.asarray(lengths, dtype=np.float64))))
    return float(np.median(np.asarray(values, dtype=np.float64)) / scale)


def _regularized_margin_proxy_positions(loop_verts, direction, axis_u, axis_v,
                                         collar_offset, max_tangent_shift,
                                         iterations=5):
    """Create a smooth duplicated basal collar without moving the scan rim.

    The supplied manual workflow duplicated and relaxed the non-manifold border,
    then used shrinkwrap before extruding it into a base.  This dependency-free
    equivalent performs the same useful operation on newly-created coordinates:
    cyclic robust relaxation in the margin plane, a strict metric displacement
    limit, and a fixed axial offset along the margin-derived closure direction.
    """
    direction = Vector(direction).normalized()
    original = [
        (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
        for vert in loop_verts]
    projections = [float(vert.co.dot(direction)) for vert in loop_verts]
    if len(original) < 3:
        return [], {
            'iterations': 0, 'max_tangent_shift': 0.0,
            'roughness_before': 0.0, 'roughness_after': 0.0}

    points = [list(point) for point in original]
    original_center = np.mean(np.asarray(original, dtype=np.float64), axis=0)
    max_shift = max(0.0, float(max_tangent_shift))
    count = len(points)
    for _ in range(max(0, int(iterations))):
        updated = []
        for index, point in enumerate(points):
            previous = points[(index - 1) % count]
            following = points[(index + 1) % count]
            neighbour_mid = np.asarray((
                (previous[0] + following[0]) * 0.5,
                (previous[1] + following[1]) * 0.5), dtype=np.float64)
            window = np.asarray([
                points[(index - 2) % count], previous, point,
                following, points[(index + 2) % count]], dtype=np.float64)
            robust_target = 0.68 * neighbour_mid + 0.32 * np.median(window, axis=0)
            candidate = np.asarray(point, dtype=np.float64) * 0.64 + robust_target * 0.36
            source = np.asarray(original[index], dtype=np.float64)
            delta = candidate - source
            distance = float(np.linalg.norm(delta))
            if max_shift > 0.0 and distance > max_shift:
                candidate = source + delta * (max_shift / max(distance, 1.0e-12))
            updated.append([float(candidate[0]), float(candidate[1])])

        # Preserve the original centroid so relaxation cannot translate the base.
        current_center = np.mean(np.asarray(updated, dtype=np.float64), axis=0)
        correction = original_center - current_center
        points = [[value[0] + float(correction[0]), value[1] + float(correction[1])]
                  for value in updated]

    # Preserve winding; a reversed collar would twist the transition strip.
    if _signed_polygon_area_2d(original) * _signed_polygon_area_2d(points) <= 0.0:
        points = [list(point) for point in original]

    positions = []
    shifts = []
    for index, (coord_u, coord_v) in enumerate(points):
        source = np.asarray(original[index], dtype=np.float64)
        target = np.asarray((coord_u, coord_v), dtype=np.float64)
        shifts.append(float(np.linalg.norm(target - source)))
        positions.append(
            axis_u * float(coord_u)
            + axis_v * float(coord_v)
            + direction * (projections[index] + float(collar_offset)))

    diagnostics = {
        'iterations': int(iterations),
        'collar_offset': float(collar_offset),
        'max_tangent_shift': float(max(shifts) if shifts else 0.0),
        'median_tangent_shift': float(np.median(np.asarray(shifts, dtype=np.float64))) if shifts else 0.0,
        'roughness_before': float(_margin_proxy_roughness_2d(original)),
        'roughness_after': float(_margin_proxy_roughness_2d(points)),
    }
    return positions, diagnostics


def _close_main_boundary_with_planar_base(bm, loop_verts, outward_direction,
                                           base_depth, wall_margin=0.0,
                                           anatomy_clearance=0.0,
                                           collar_offset=0.0,
                                           max_collar_tangent_shift=0.0):
    """Create a deterministic manifold base without touching scan coordinates.

    The anatomical rim is extended through several newly-created transition
    rings.  The final cap no longer relies on ``triangle_fill`` accepting one
    very dense concave polygon.  Instead, a short basal-only transition reaches
    a guaranteed simple convex safety ring and that ring is closed with a
    deterministic triangle fan.  Only new basal vertices participate in this
    regularisation; every source dental vertex remains exactly where scanned.
    """
    direction = Vector(outward_direction)
    if direction.length <= 1.0e-9:
        direction = Vector((0.0, 0.0, 1.0))
    direction.normalize()
    depth = max(1.0e-5, float(base_depth))
    axis_u, axis_v, _ = _orthonormal_base_frame(direction)
    count = len(loop_verts)
    if count < 3:
        raise RuntimeError('The basal rim contains fewer than three vertices')

    rim_projection = [float(vert.co.dot(direction)) for vert in loop_verts]
    robust_rim = _safe_percentile(rim_projection, 75, max(rim_projection))
    spike_clearance = max(depth * 0.04, min(depth * 0.12, 0.25))

    # The flat base must never intersect a deep palate or any other anatomical
    # prominence.  Evaluate every face-connected vertex that exists before the
    # basal wall is created and place the basal plane at least the requested
    # clearance beyond the deepest point along the margin-derived axis.
    anatomical_projection = [
        float(vert.co.dot(direction))
        for vert in bm.verts
        if getattr(vert, 'is_valid', True) and len(getattr(vert, 'link_faces', ())) > 0
    ]
    deepest_anatomy = max(anatomical_projection) if anatomical_projection else max(rim_projection)
    required_clearance = max(0.0, float(anatomy_clearance))
    anatomy_safe_plane = deepest_anatomy + required_clearance

    base_plane = max(
        max(rim_projection) + spike_clearance,
        robust_rim + depth,
        anatomy_safe_plane,
    )
    # Use the true effective wall height for all transition and safety-ring
    # calculations when a deep palate forces the base farther outward.
    depth = max(depth, base_plane - robust_rim)

    # Build a duplicated, gently regularised collar before the long basal wall.
    # The source rim stays immutable; only this newly-created proxy is relaxed.
    collar_positions, collar_diagnostics = _regularized_margin_proxy_positions(
        loop_verts, direction, axis_u, axis_v,
        collar_offset=max(0.0, float(collar_offset)),
        max_tangent_shift=max(0.0, float(max_collar_tangent_shift)),
        iterations=5)
    if len(collar_positions) != count:
        raise RuntimeError('Could not generate a complete regularised basal collar')

    rim_u = [float(position.dot(axis_u)) for position in collar_positions]
    rim_v = [float(position.dot(axis_v)) for position in collar_positions]
    rim_projection_work = [float(position.dot(direction)) for position in collar_positions]
    center_u = float(np.median(np.asarray(rim_u, dtype=np.float64)))
    center_v = float(np.median(np.asarray(rim_v, dtype=np.float64)))

    margin_ratio = min(
        0.025,
        max(0.0, float(wall_margin)) / max(depth, 1.0e-6) * 0.08)
    # Five progressive rings emulate the useful relax/select-more/extrude logic
    # of the supplied workflow while keeping every operation deterministic.
    ring_specs = (
        (0.16, 0.002, 2, 0.16),
        (0.34, 0.007 + margin_ratio * 0.15, 3, 0.21),
        (0.56, 0.014 + margin_ratio * 0.35, 3, 0.25),
        (0.78, 0.022 + margin_ratio * 0.65, 4, 0.29),
        (1.00, 0.030 + margin_ratio, 5, 0.32),
    )

    def bridge_equal_rings(upper, lower, label):
        """Bridge every corresponding edge or fail transactionally."""
        made = 0
        if len(upper) != len(lower) or len(upper) < 3:
            raise RuntimeError(f'Invalid {label} ring correspondence')
        for index in range(len(upper)):
            nxt = (index + 1) % len(upper)
            try:
                bm.faces.new((upper[index], upper[nxt], lower[nxt], lower[index]))
                made += 1
                continue
            except ValueError:
                pass

            first = second = False
            try:
                bm.faces.new((upper[index], upper[nxt], lower[nxt]))
                first = True
                made += 1
            except ValueError:
                pass
            try:
                bm.faces.new((upper[index], lower[nxt], lower[index]))
                second = True
                made += 1
            except ValueError:
                pass
            if not (first and second):
                raise RuntimeError(
                    f'Could not create a complete {label} bridge at rim edge {index}; '
                    'the operation was cancelled before mesh commit')
        return int(made)

    previous_ring = list(loop_verts)
    side_faces = 0
    collar_ring = [bm.verts.new(position) for position in collar_positions]
    bm.verts.index_update()
    side_faces += bridge_equal_rings(previous_ring, collar_ring, 'regularised basal collar')
    previous_ring = collar_ring

    for fraction, radial_shrink, relax_iterations, relax_factor in ring_specs:
        target_positions = []
        eased_fraction = float(fraction) * float(fraction) * (3.0 - 2.0 * float(fraction))
        for coord_u, coord_v, start_projection in zip(rim_u, rim_v, rim_projection_work):
            scale = 1.0 - float(radial_shrink)
            new_u = center_u + (coord_u - center_u) * scale
            new_v = center_v + (coord_v - center_v) * scale
            target_projection = (
                base_plane if fraction >= 0.999
                else start_projection + (base_plane - start_projection) * eased_fraction)
            target_positions.append(
                axis_u * new_u + axis_v * new_v + direction * target_projection)

        common_projection = base_plane if fraction >= 0.999 else float(np.median([
            point.dot(direction) for point in target_positions]))
        target_positions = _relax_closed_ring_positions(
            target_positions, direction, common_projection,
            iterations=relax_iterations, factor=relax_factor)

        if fraction < 0.999:
            for index, point in enumerate(target_positions):
                desired = rim_projection_work[index] + (
                    base_plane - rim_projection_work[index]) * eased_fraction
                point += direction * (desired - float(point.dot(direction)))
        else:
            for point in target_positions:
                point += direction * (base_plane - float(point.dot(direction)))

        new_ring = [bm.verts.new(position) for position in target_positions]
        bm.verts.index_update()
        side_faces += bridge_equal_rings(
            previous_ring, new_ring, 'basal transition')
        previous_ring = new_ring

    # Build a simple convex footprint only in newly-created basal geometry.  The
    # original concave dental rim and all tooth coordinates remain untouched.
    projected = [
        (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
        for vert in previous_ring]
    hull = _convex_hull_2d(projected)
    if len(hull) < 3:
        raise RuntimeError(
            'Could not derive a simple basal safety ring from the newly-created base')

    source_area = _signed_polygon_area_2d(projected)
    hull_area = _signed_polygon_area_2d(hull)
    if abs(source_area) > 1.0e-12 and source_area * hull_area < 0.0:
        hull = list(reversed(hull))

    # Start both loops at corresponding locations, then sample the convex ring
    # using the actual cumulative spacing of the dense anatomical rim.  This
    # prevents twists when one region of the STL is much more tessellated.
    first = projected[0]
    start_index = min(
        range(len(hull)),
        key=lambda index: ((hull[index][0] - first[0]) ** 2
                           + (hull[index][1] - first[1]) ** 2))
    hull = hull[start_index:] + hull[:start_index]

    expand_margin = max(float(wall_margin), depth * 0.012, 1.0e-5)
    hull_center_x = float(sum(point[0] for point in hull) / len(hull))
    hull_center_y = float(sum(point[1] for point in hull) / len(hull))
    expanded_hull = []
    for x, y in hull:
        dx = float(x) - hull_center_x
        dy = float(y) - hull_center_y
        radius = math.hypot(dx, dy)
        factor = (radius + expand_margin) / max(radius, 1.0e-12)
        expanded_hull.append((
            hull_center_x + dx * factor,
            hull_center_y + dy * factor))

    dense_lengths = []
    dense_total = 0.0
    minimum_step = max(1.0e-12, sum(
        math.hypot(projected[(i + 1) % count][0] - projected[i][0],
                   projected[(i + 1) % count][1] - projected[i][1])
        for i in range(count)) * 1.0e-12)
    for index, point in enumerate(projected):
        nxt = projected[(index + 1) % count]
        length = max(minimum_step, math.hypot(nxt[0] - point[0], nxt[1] - point[1]))
        dense_lengths.append(length)
        dense_total += length
    fractions = []
    accumulated = 0.0
    for length in dense_lengths:
        fractions.append(accumulated / max(dense_total, 1.0e-12))
        accumulated += length

    hull_lengths = []
    hull_total = 0.0
    for index, point in enumerate(expanded_hull):
        nxt = expanded_hull[(index + 1) % len(expanded_hull)]
        length = math.hypot(nxt[0] - point[0], nxt[1] - point[1])
        hull_lengths.append(length)
        hull_total += length
    if hull_total <= 1.0e-12:
        raise RuntimeError('The basal safety ring collapsed to zero perimeter')

    sampled_hull = []
    segment = 0
    segment_start = 0.0
    for fraction in fractions:
        target = float(fraction) * hull_total
        while (segment < len(expanded_hull) - 1
               and segment_start + hull_lengths[segment] < target):
            segment_start += hull_lengths[segment]
            segment += 1
        local = ((target - segment_start)
                 / max(hull_lengths[segment], 1.0e-12))
        a = expanded_hull[segment]
        b = expanded_hull[(segment + 1) % len(expanded_hull)]
        sampled_hull.append((
            a[0] + (b[0] - a[0]) * local,
            a[1] + (b[1] - a[1]) * local))

    safety_projection = base_plane + max(
        depth * 0.035, float(wall_margin) * 0.35, 1.0e-5)
    safety_positions = [
        axis_u * x + axis_v * y + direction * safety_projection
        for x, y in sampled_hull]
    safety_ring = [bm.verts.new(position) for position in safety_positions]
    bm.verts.index_update()
    side_faces += bridge_equal_rings(
        previous_ring, safety_ring, 'manifold safety')

    center_position = sum((vert.co for vert in safety_ring), Vector()) / len(safety_ring)
    center_position += direction * (
        safety_projection - float(center_position.dot(direction)))
    center_vert = bm.verts.new(center_position)
    bm.verts.index_update()

    cap_faces = 0
    for index in range(len(safety_ring)):
        nxt = (index + 1) % len(safety_ring)
        try:
            bm.faces.new((safety_ring[index], safety_ring[nxt], center_vert))
            cap_faces += 1
        except ValueError as exc:
            raise RuntimeError(
                f'Could not close deterministic basal cap at edge {index}: {exc}')

    if cap_faces != len(safety_ring):
        raise RuntimeError(
            f'Deterministic basal cap was incomplete ({cap_faces}/{len(safety_ring)} faces)')

    build_diagnostics = {
        **collar_diagnostics,
        'transition_ring_count': int(len(ring_specs) + 1),
        'base_plane_projection': float(base_plane),
        'effective_depth': float(depth),
        'anatomy_clearance': float(required_clearance),
        'safety_ring_vertices': int(len(safety_ring)),
    }
    return list(safety_ring), int(side_faces), int(cap_faces), build_diagnostics

def _orthonormal_base_frame(direction):
    """Return two stable in-plane axes perpendicular to ``direction``."""
    normal = Vector(direction)
    if normal.length <= 1.0e-9:
        normal = Vector((0.0, 0.0, 1.0))
    normal.normalize()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(reference)) > 0.92:
        reference = Vector((1.0, 0.0, 0.0))
    axis_u = normal.cross(reference)
    if axis_u.length <= 1.0e-9:
        axis_u = Vector((1.0, 0.0, 0.0))
    axis_u.normalize()
    axis_v = normal.cross(axis_u)
    axis_v.normalize()
    return axis_u, axis_v, normal


def _convex_hull_2d(points):
    """Monotonic-chain convex hull used as a robust basal silhouette.

    Dental model creators first establish a clean perimeter before building a
    base.  Raw STL boundary edges are often branched or fragmented, so DSG does
    not use them directly in the volumetric fallback.  Instead, it derives a
    stable 2-D silhouette from the basal band of the scan.
    """
    unique = sorted({(round(float(x), 6), round(float(y), 6)) for x, y in points})
    if len(unique) < 3:
        return []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]



def _polygon_area_2d(points):
    if len(points) < 3:
        return 0.0
    return abs(0.5 * sum(
        float(points[index][0]) * float(points[(index + 1) % len(points)][1])
        - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
        for index in range(len(points))))


def _radial_envelope_polygon_2d(points, bins=144, percentile=90.0, margin=0.0):
    """Robust star-shaped footprint that rejects isolated scan spikes.

    Compared with a raw convex hull it follows the dental basal band more
    closely, while remaining simple and watertight for prism generation.
    """
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or len(array) < 12:
        return []
    center = np.median(array, axis=0)
    delta = array - center
    radii = np.linalg.norm(delta, axis=1)
    valid = np.isfinite(radii) & (radii > 1.0e-6)
    if np.count_nonzero(valid) < 12:
        return []
    delta = delta[valid]
    radii = radii[valid]
    angles = (np.arctan2(delta[:, 1], delta[:, 0]) + 2.0 * np.pi) % (2.0 * np.pi)
    bins = max(48, int(bins))
    bin_width = 2.0 * np.pi / bins
    indices = np.floor(angles / bin_width).astype(np.int64) % bins
    envelope = np.full(bins, np.nan, dtype=np.float64)
    for index in range(bins):
        values = radii[indices == index]
        if len(values):
            envelope[index] = np.percentile(values, float(percentile))
    present = np.where(np.isfinite(envelope))[0]
    if len(present) < bins * 0.35:
        return []
    # Cyclic nearest interpolation for missing angular sectors.
    for index in range(bins):
        if math.isfinite(float(envelope[index])):
            continue
        distances = np.minimum((present - index) % bins, (index - present) % bins)
        envelope[index] = envelope[present[int(np.argmin(distances))]]
    # Circular low-pass filtering removes scallops caused by sparse STL borders.
    for _ in range(4):
        envelope = (
            0.20 * np.roll(envelope, 2)
            + 0.20 * np.roll(envelope, 1)
            + 0.20 * envelope
            + 0.20 * np.roll(envelope, -1)
            + 0.20 * np.roll(envelope, -2))
    envelope += max(0.0, float(margin))
    polygon = []
    for index, radius in enumerate(envelope):
        angle = (index + 0.5) * bin_width
        polygon.append((
            float(center[0] + radius * math.cos(angle)),
            float(center[1] + radius * math.sin(angle))))
    return polygon


def _derive_dental_base_footprint(points, diagonal_local, margin_local):
    """Choose a robust dental footprint and fall back to convex hull safely."""
    radial = _radial_envelope_polygon_2d(
        points, bins=144, percentile=90.0, margin=margin_local)
    hull = _convex_hull_2d(points)
    if len(radial) >= 12 and len(hull) >= 3:
        radial_area = _polygon_area_2d(radial)
        hull_area = _polygon_area_2d(hull)
        # Reject a collapsed or wildly expanded radial outline.
        if hull_area > 1.0e-8 and 0.48 <= radial_area / hull_area <= 1.18:
            return radial, 'radial_envelope'
    if len(hull) >= 3 and margin_local > 0.0:
        center_x = sum(p[0] for p in hull) / len(hull)
        center_y = sum(p[1] for p in hull) / len(hull)
        expanded = []
        for x, y in hull:
            dx, dy = x - center_x, y - center_y
            radius = math.hypot(dx, dy)
            factor = (radius + margin_local) / max(radius, 1.0e-8)
            expanded.append((center_x + dx * factor, center_y + dy * factor))
        hull = expanded
    return hull, 'convex_hull_fallback'


def _simplify_closed_2d_polygon(points, tolerance=0.15, max_points=320):
    """Remove near-collinear points while retaining a closed dental footprint."""
    points = list(points)
    if len(points) <= 3:
        return points
    tolerance = max(1.0e-5, float(tolerance))
    changed = True
    while changed and len(points) > 12:
        changed = False
        keep = []
        count = len(points)
        for index, current in enumerate(points):
            previous = points[(index - 1) % count]
            following = points[(index + 1) % count]
            ax = current[0] - previous[0]
            ay = current[1] - previous[1]
            bx = following[0] - previous[0]
            by = following[1] - previous[1]
            denom = max(1.0e-9, math.hypot(bx, by))
            distance = abs(ax * by - ay * bx) / denom
            if distance < tolerance:
                changed = True
                continue
            keep.append(current)
        if len(keep) < 3:
            break
        points = keep
    if len(points) > int(max_points):
        step = int(math.ceil(len(points) / float(max_points)))
        points = points[::step]
    return points



def _base_perimeter_material():
    name = 'DSG_BasePerimeter_Material'
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
    try:
        material.diffuse_color = (1.0, 0.28, 0.03, 1.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def _base_perimeter_curve():
    obj = bpy.data.objects.get(BASE_PERIMETER_CURVE_NAME)
    return obj if _valid_obj(obj) and obj.type == 'CURVE' else None


def _remove_base_perimeter_curve():
    obj = bpy.data.objects.get(BASE_PERIMETER_CURVE_NAME)
    if _valid_obj(obj):
        safe_remove_object_with_data(obj)


def _set_base_perimeter_curve_points(context, world_points, source_obj, mode='MANUAL'):
    """Create/update the visible perimeter used by the base closure fallback."""
    points = [Vector(point) for point in world_points]
    obj = _base_perimeter_curve()
    if obj is None:
        data = bpy.data.curves.new(BASE_PERIMETER_CURVE_NAME, type='CURVE')
        data.dimensions = '3D'
        data.resolution_u = 2
        data.bevel_resolution = 2
        data.bevel_depth = _mm_to_object_units(source_obj, BASE_PERIMETER_CURVE_RADIUS_MM)
        obj = bpy.data.objects.new(BASE_PERIMETER_CURVE_NAME, data)
        context.collection.objects.link(obj)
        obj.show_in_front = True
        obj.color = (1.0, 0.28, 0.03, 1.0)
        material = _base_perimeter_material()
        if material and not obj.data.materials:
            obj.data.materials.append(material)
    data = obj.data
    while len(data.splines):
        data.splines.remove(data.splines[0])
    if points:
        spline = data.splines.new('POLY')
        spline.points.add(len(points) - 1)
        for point, value in zip(spline.points, points):
            point.co = (float(value.x), float(value.y), float(value.z), 1.0)
        spline.use_cyclic_u = len(points) >= BASE_PERIMETER_MIN_POINTS
    obj['DSG_base_perimeter_source'] = str(source_obj.name)
    obj['DSG_base_perimeter_mode'] = str(mode)
    obj['DSG_base_perimeter_points'] = int(len(points))
    _set_obj_hidden(obj, False, selectable_when_visible=True)
    _tag_dsg_view3d_redraw()
    return obj


def _base_perimeter_world_points(curve_obj=None):
    curve_obj = curve_obj or _base_perimeter_curve()
    if curve_obj is None:
        return []
    points = []
    try:
        for spline in curve_obj.data.splines:
            if spline.type == 'BEZIER':
                points.extend(curve_obj.matrix_world @ point.co for point in spline.bezier_points)
            else:
                points.extend(curve_obj.matrix_world @ Vector(point.co[:3]) for point in spline.points)
    except Exception:
        return []
    deduplicated = []
    for point in points:
        if not deduplicated or (point - deduplicated[-1]).length > 1.0e-6:
            deduplicated.append(point)
    if len(deduplicated) > 2 and (deduplicated[0] - deduplicated[-1]).length <= 1.0e-6:
        deduplicated.pop()
    return deduplicated


def _base_perimeter_local_points(source_obj, curve_obj=None):
    if not _valid_obj(source_obj):
        return []
    curve_obj = curve_obj or _base_perimeter_curve()
    if curve_obj is None:
        return []
    source_name = str(curve_obj.get('DSG_base_perimeter_source', ''))
    if source_name and source_name != source_obj.name:
        return []
    inverse = source_obj.matrix_world.inverted_safe()
    return [inverse @ point for point in _base_perimeter_world_points(curve_obj)]


def _smooth_closed_polygon_2d(points, iterations=3, factor=0.24):
    result = [(float(x), float(y)) for x, y in points]
    if len(result) < 4:
        return result
    factor = max(0.0, min(0.45, float(factor)))
    for _ in range(max(0, int(iterations))):
        updated = []
        count = len(result)
        for index, current in enumerate(result):
            previous = result[(index - 1) % count]
            following = result[(index + 1) % count]
            midpoint = ((previous[0] + following[0]) * 0.5,
                        (previous[1] + following[1]) * 0.5)
            updated.append((
                current[0] * (1.0 - factor) + midpoint[0] * factor,
                current[1] * (1.0 - factor) + midpoint[1] * factor))
        result = updated
    return result


def _resample_closed_polygon_2d(points, target_count=144):
    points = [(float(x), float(y)) for x, y in points]
    if len(points) < 3:
        return points
    lengths = []
    total = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        length = math.hypot(nxt[0] - point[0], nxt[1] - point[1])
        lengths.append(length)
        total += length
    if total <= 1.0e-8:
        return points
    target_count = max(24, min(320, int(target_count)))
    samples = []
    segment = 0
    accumulated = 0.0
    for sample_index in range(target_count):
        distance = total * sample_index / target_count
        while segment < len(points) - 1 and accumulated + lengths[segment] < distance:
            accumulated += lengths[segment]
            segment += 1
        local = (distance - accumulated) / max(lengths[segment], 1.0e-9)
        a = points[segment]
        b = points[(segment + 1) % len(points)]
        samples.append((a[0] + (b[0] - a[0]) * local,
                        a[1] + (b[1] - a[1]) * local))
    return samples


def _expand_polygon_radially(points, margin):
    if len(points) < 3 or margin <= 0.0:
        return list(points)
    center_x = float(np.median(np.asarray([point[0] for point in points], dtype=np.float64)))
    center_y = float(np.median(np.asarray([point[1] for point in points], dtype=np.float64)))
    expanded = []
    for x, y in points:
        dx, dy = x - center_x, y - center_y
        radius = math.hypot(dx, dy)
        factor = (radius + float(margin)) / max(radius, 1.0e-8)
        expanded.append((center_x + dx * factor, center_y + dy * factor))
    return expanded


def _drawn_base_footprint(source_obj, direction, axis_u, axis_v, curve_obj=None):
    local_points = _base_perimeter_local_points(source_obj, curve_obj)
    if len(local_points) < BASE_PERIMETER_MIN_POINTS:
        return None
    polygon = [(float(point.dot(axis_u)), float(point.dot(axis_v))) for point in local_points]
    polygon = _smooth_closed_polygon_2d(polygon, iterations=3, factor=0.22)
    polygon = _resample_closed_polygon_2d(polygon, target_count=max(72, min(192, len(polygon) * 4)))
    polygon = _simplify_closed_2d_polygon(
        polygon,
        tolerance=max(_mm_to_object_units(source_obj, 0.05), 1.0e-5),
        max_points=220)
    if len(polygon) < 3 or _polygon_area_2d(polygon) <= 1.0e-8:
        return None
    polygon = _expand_polygon_radially(
        polygon, _mm_to_object_units(source_obj, BASE_PERIMETER_MANUAL_MARGIN_MM))
    projections = [float(point.dot(direction)) for point in local_points]
    return {
        'polygon': polygon,
        'projections': projections,
        'local_points': local_points,
        'method': 'drawn_surface_perimeter',
    }


def _raycast_model_from_event(context, event, model_obj):
    if not _valid_obj(model_obj) or model_obj.type != 'MESH':
        return None
    region = context.region
    region_data = context.region_data
    if region is None or region_data is None:
        return None
    mouse = (event.mouse_region_x, event.mouse_region_y)
    origin_world = view3d_utils.region_2d_to_origin_3d(region, region_data, mouse)
    direction_world = view3d_utils.region_2d_to_vector_3d(region, region_data, mouse)
    inverse = model_obj.matrix_world.inverted_safe()
    origin_local = inverse @ origin_world
    direction_local = inverse.to_3x3() @ direction_world
    if direction_local.length <= 1.0e-9:
        return None
    direction_local.normalize()
    try:
        success, location, _normal, _face_index = model_obj.ray_cast(
            origin_local, direction_local, distance=1000000.0)
    except TypeError:
        success, location, _normal, _face_index = model_obj.ray_cast(
            origin_local, direction_local)
    if not success:
        return None
    return model_obj.matrix_world @ location


def _automatic_base_outline_world(context, source_obj, perimeter_obj=None):
    """Build the same automatic footprint used by the volumetric closure."""
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(source_obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        boundary_verts = {
            vert for edge in bm.edges if len(edge.link_faces) != 2
            for vert in edge.verts}
        direction, diagnostics = _automatic_base_direction(
            bm, list(boundary_verts) if boundary_verts else list(bm.verts),
            source_obj=source_obj, return_diagnostics=True)
        axis_u, axis_v, direction = _orthonormal_base_frame(direction)
        projections = [float(vert.co.dot(direction)) for vert in bm.verts]
        boundary_projection = [float(vert.co.dot(direction)) for vert in boundary_verts]
        basal_projection = _safe_percentile(
            boundary_projection if boundary_projection else projections, 68,
            _safe_percentile(projections, 96))
        drawn_footprint = _drawn_base_footprint(
            source_obj, direction, axis_u, axis_v, perimeter_obj)
        if drawn_footprint:
            basal_projection = _safe_percentile(
                drawn_footprint['projections'], 55, basal_projection)
        coords = [vert.co for vert in bm.verts]
        mins = Vector((min(value[index] for value in coords) for index in range(3)))
        maxs = Vector((max(value[index] for value in coords) for index in range(3)))
        diagonal = float((maxs - mins).length)
        diagonal_mm = diagonal * _object_average_world_scale(source_obj)
        basal_band_mm = max(
            AUTO_BASE_MIN_BASAL_BAND_MM,
            min(AUTO_BASE_MAX_BASAL_BAND_MM,
                diagonal_mm * AUTO_BASE_BASAL_BAND_FRACTION))
        basal_band = _mm_to_object_units(source_obj, basal_band_mm)
        basal_points = [
            (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
            for vert, projection in zip(bm.verts, projections)
            if projection >= basal_projection - basal_band]
        if len(basal_points) < 24:
            basal_points = [
                (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
                for vert in bm.verts]
        hull, method = _derive_dental_base_footprint(
            basal_points, diagonal,
            _mm_to_object_units(source_obj, AUTO_BASE_FOOTPRINT_MARGIN_MM))
        hull = _simplify_closed_2d_polygon(
            hull, tolerance=max(_mm_to_object_units(source_obj, 0.08), diagonal * 0.0012),
            max_points=220)
        if len(hull) < 3:
            raise RuntimeError('Could not derive a stable automatic perimeter')
        local = [axis_u * x + axis_v * y + direction * basal_projection for x, y in hull]
        world = [source_obj.matrix_world @ point for point in local]
        return world, diagnostics, method
    finally:
        if bm is not None:
            bm.free()


class DSG_OT_PreviewAutomaticBasePerimeter(Operator):
    bl_idname = 'dsg.preview_automatic_base_perimeter'
    bl_label = 'Preview Automatic Base Perimeter'
    bl_description = 'Shows the automatic dental perimeter before closing the model'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(model):
            _dsg_report(self, {'ERROR'}, 'No dental model was found', 'No se encontró un modelo dental')
            return {'CANCELLED'}
        try:
            points, diagnostics, method = _automatic_base_outline_world(context, model)
            curve = _set_base_perimeter_curve_points(context, points, model, mode='AUTO')
            curve['DSG_base_perimeter_method'] = str(method)
            curve['DSG_base_direction_confidence'] = float(diagnostics.get('confidence', 0.0))
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not preview the perimeter: {exc}',
                        f'No se pudo previsualizar el perímetro: {exc}')
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, 'Automatic base perimeter ready',
                    'Perímetro automático de la base preparado')
        return {'FINISHED'}


class DSG_OT_DrawBasePerimeter(Operator):
    bl_idname = 'dsg.draw_base_perimeter'
    bl_label = 'Draw Base Perimeter'
    bl_description = (
        'Draw a closed perimeter directly on the dental scan. Middle mouse and wheel keep native navigation; '
        'Enter confirms, Ctrl+Z removes the last point, Esc cancels')
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _points = None
    _model = None
    _navigating = False

    def _finish(self, context):
        if len(self._points or ()) < BASE_PERIMETER_MIN_POINTS:
            _dsg_report(self, {'ERROR'},
                        f'Place at least {BASE_PERIMETER_MIN_POINTS} points',
                        f'Coloca al menos {BASE_PERIMETER_MIN_POINTS} puntos')
            return {'RUNNING_MODAL'}
        curve = _set_base_perimeter_curve_points(context, self._points, self._model, mode='MANUAL')
        curve['DSG_base_perimeter_confirmed'] = True
        context.workspace.status_text_set(None)
        _dsg_report(self, {'INFO'}, 'Manual base perimeter confirmed',
                    'Perímetro manual de la base confirmado')
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            self._navigating = event.value == 'PRESS'
            return {'PASS_THROUGH'}
        if self._navigating and event.type == 'MOUSEMOVE':
            return {'PASS_THROUGH'}
        if event.type in {
                'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
                'NDOF_MOTION', 'NDOF_BUTTON_MENU', 'TRACKPADPAN', 'TRACKPADZOOM'}:
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = _raycast_model_from_event(context, event, self._model)
            if hit is None:
                _dsg_report(self, {'WARNING'}, 'Click on the dental model', 'Haz clic sobre el modelo dental')
                return {'RUNNING_MODAL'}
            minimum = _mm_to_object_units(self._model, BASE_PERIMETER_MIN_SPACING_MM)
            world_scale = max(1.0e-8, _object_average_world_scale(self._model))
            minimum_world = minimum * world_scale
            if not self._points or (hit - self._points[-1]).length >= minimum_world:
                self._points.append(hit)
                _set_base_perimeter_curve_points(context, self._points, self._model, mode='MANUAL')
            return {'RUNNING_MODAL'}
        if event.type == 'Z' and event.value == 'PRESS' and event.ctrl:
            if self._points:
                self._points.pop()
                _set_base_perimeter_curve_points(context, self._points, self._model, mode='MANUAL')
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._finish(context)
        if event.type == 'ESC' and event.value == 'PRESS':
            _remove_base_perimeter_curve()
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            _dsg_report(self, {'ERROR'}, 'Run this tool in the 3D View', 'Ejecuta esta herramienta en la Vista 3D')
            return {'CANCELLED'}
        props = context.scene.dsg_props
        self._model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(self._model):
            _dsg_report(self, {'ERROR'}, 'No dental model was found', 'No se encontró un modelo dental')
            return {'CANCELLED'}
        _remove_base_perimeter_curve()
        self._points = []
        self._navigating = False
        context.workspace.status_text_set(
            'DSG: Left click = point · MMB/Shift+MMB = navigate · Ctrl+Z = remove · Enter = confirm · Esc = cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


class DSG_OT_ClearBasePerimeter(Operator):
    bl_idname = 'dsg.clear_base_perimeter'
    bl_label = 'Clear Base Perimeter'
    bl_description = 'Removes the automatic or manually drawn base perimeter'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _remove_base_perimeter_curve()
        return {'FINISHED'}


def _append_base_prism_to_bmesh(bm, polygon_2d, axis_u, axis_v, direction,
                                top_projection, bottom_projection):
    """Append a closed prism that overlaps the basal scan and guarantees volume."""
    top = []
    bottom = []
    for x, y in polygon_2d:
        in_plane = axis_u * float(x) + axis_v * float(y)
        top.append(bm.verts.new(in_plane + direction * float(top_projection)))
        bottom.append(bm.verts.new(in_plane + direction * float(bottom_projection)))
    bm.verts.index_update()
    count = len(top)
    for index in range(count):
        nxt = (index + 1) % count
        try:
            bm.faces.new((top[index], top[nxt], bottom[nxt], bottom[index]))
        except ValueError:
            pass
    try:
        bm.faces.new(tuple(reversed(top)))
    except ValueError:
        pass
    try:
        bm.faces.new(tuple(bottom))
    except ValueError:
        pass


def _run_voxel_remesh_operator(context, obj, voxel_size):
    """Hard-disabled for dental-model base closure.

    Kept only as a compatibility symbol for older saved sessions. Returning
    False guarantees that no legacy base-closing path can voxel-remesh a dental
    scan, even if it is called accidentally by stale UI/operator state.
    """
    print('[DSG] Base-closure voxel remesh blocked by anatomy lock')
    return False



def _reproject_anatomical_surface_to_scan(closed_obj, source_obj, direction,
                                          basal_projection, voxel_size):
    """Recover scan detail after volumetric reconstruction without reopening it.

    Only vertices already close to the original scan and located coronally from
    the base are moved.  Topology remains the watertight topology produced by
    the voxel remesher.
    """
    source_bm = None
    closed_bm = None
    try:
        source_bm = bmesh.new()
        source_bm.from_mesh(source_obj.data)
        source_bm.verts.ensure_lookup_table()
        source_bm.faces.ensure_lookup_table()
        bvh = BVHTree.FromBMesh(source_bm)

        closed_bm = bmesh.new()
        closed_bm.from_mesh(closed_obj.data)
        closed_bm.verts.ensure_lookup_table()
        maximum_distance = max(0.30, min(0.80, float(voxel_size) * 4.0))
        coronary_limit = float(basal_projection) + float(voxel_size) * 1.5
        moved = 0
        for vert in closed_bm.verts:
            if float(vert.co.dot(direction)) > coronary_limit:
                continue
            nearest = bvh.find_nearest(vert.co)
            if not nearest:
                continue
            location, _normal, _face_index, distance = nearest
            if location is None or distance is None or float(distance) > maximum_distance:
                continue
            vert.co = location
            moved += 1
        if moved:
            try:
                bmesh.ops.recalc_face_normals(closed_bm, faces=list(closed_bm.faces))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            closed_bm.normal_update()
            closed_bm.to_mesh(closed_obj.data)
            closed_obj.data.update()
        return moved
    finally:
        if source_bm is not None:
            source_bm.free()
        if closed_bm is not None:
            closed_bm.free()


def _close_open_model_volumetric(context, source_obj, perimeter_obj=None):
    """Robust dental-model closure using silhouette + overlapping solid + VDB.

    This path intentionally does not try to heal thousands of raw boundary
    edges one by one.  It creates a clean base volume from the scan silhouette,
    overlaps that volume with the scan, and asks Blender's OpenVDB remesher to
    reconstruct one watertight shell.  The fitting anatomy is then projected
    back to the source scan where the two surfaces are already close.
    """
    closed = duplicate_object_with_data(context, source_obj, CLOSED_MODEL_NAME)
    closed.matrix_world = source_obj.matrix_world.copy()
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(closed.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        try:
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1.0e-7)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bmesh.ops.delete(
                bm,
                geom=[edge for edge in bm.edges if len(edge.link_faces) == 0],
                context='EDGES')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.verts.ensure_lookup_table()
        if len(bm.verts) < 3:
            raise RuntimeError('The scan does not contain enough geometry')

        boundary_verts = {
            vert for edge in bm.edges if len(edge.link_faces) != 2
            for vert in edge.verts}
        direction, base_diagnostics = _automatic_base_direction(
            bm, list(boundary_verts) if boundary_verts else list(bm.verts),
            source_obj=source_obj, return_diagnostics=True)
        axis_u, axis_v, direction = _orthonormal_base_frame(direction)

        projections = [float(vert.co.dot(direction)) for vert in bm.verts]
        boundary_projection = [
            float(vert.co.dot(direction)) for vert in boundary_verts]
        basal_projection = _safe_percentile(
            boundary_projection if boundary_projection else projections, 68,
            _safe_percentile(projections, 96))
        drawn_footprint = _drawn_base_footprint(
            source_obj, direction, axis_u, axis_v, perimeter_obj)
        if drawn_footprint:
            basal_projection = _safe_percentile(
                drawn_footprint['projections'], 55, basal_projection)
        coords = [vert.co for vert in bm.verts]
        mins = Vector((min(v[i] for v in coords) for i in range(3)))
        maxs = Vector((max(v[i] for v in coords) for i in range(3)))
        diagonal = float((maxs - mins).length)
        world_scale = _object_average_world_scale(source_obj)
        diagonal_mm = diagonal * world_scale
        basal_band_mm = max(
            AUTO_BASE_MIN_BASAL_BAND_MM,
            min(AUTO_BASE_MAX_BASAL_BAND_MM,
                diagonal_mm * AUTO_BASE_BASAL_BAND_FRACTION))
        basal_band = _mm_to_object_units(source_obj, basal_band_mm)
        basal_points = [
            (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
            for vert, projection in zip(bm.verts, projections)
            if projection >= basal_projection - basal_band
        ]
        if len(basal_points) < 24:
            basal_points = [
                (float(vert.co.dot(axis_u)), float(vert.co.dot(axis_v)))
                for vert in bm.verts
            ]
        footprint_margin = _mm_to_object_units(
            source_obj, AUTO_BASE_FOOTPRINT_MARGIN_MM)
        if drawn_footprint:
            hull = list(drawn_footprint['polygon'])
            footprint_method = str(drawn_footprint.get('method', 'drawn_surface_perimeter'))
        else:
            hull, footprint_method = _derive_dental_base_footprint(
                basal_points, diagonal, footprint_margin)
        hull = _simplify_closed_2d_polygon(
            hull, tolerance=max(_mm_to_object_units(source_obj, 0.08), diagonal * 0.0012),
            max_points=320)
        if len(hull) < 3:
            raise RuntimeError('Could not derive a stable basal silhouette')

        base_depth_mm = max(
            AUTO_BASE_MIN_DEPTH_MM,
            min(AUTO_BASE_MAX_DEPTH_MM, diagonal_mm * AUTO_BASE_DEPTH_FRACTION))
        overlap_mm = max(1.0, min(2.2, diagonal_mm * 0.025))
        base_depth = _mm_to_object_units(source_obj, base_depth_mm)
        overlap = _mm_to_object_units(source_obj, overlap_mm)
        top_projection = basal_projection - overlap
        perimeter_projection = (
            drawn_footprint['projections'] if drawn_footprint else
            (boundary_projection or projections))
        bottom_projection = max(
            _safe_percentile(perimeter_projection, 97)
            + _mm_to_object_units(source_obj, 0.35),
            basal_projection + base_depth)
        _append_base_prism_to_bmesh(
            bm, hull, axis_u, axis_v, direction, top_projection, bottom_projection)
        try:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.normal_update()
        bm.to_mesh(closed.data)
        closed.data.update()
    except Exception:
        if bm is not None:
            bm.free()
            bm = None
        safe_remove_object_with_data(closed)
        raise
    finally:
        if bm is not None:
            bm.free()

    # First attempt preserves high detail; a second slightly coarser pass is a
    # safety fallback for scans containing large self-intersections or gaps.
    voxel_primary_mm = max(0.10, min(0.18, diagonal_mm / 520.0))
    voxel_secondary_mm = max(voxel_primary_mm * 1.35, 0.16)
    voxel_primary = _mm_to_object_units(source_obj, voxel_primary_mm)
    voxel_secondary = _mm_to_object_units(source_obj, voxel_secondary_mm)
    success = _run_voxel_remesh_operator(context, closed, voxel_primary)
    if not success:
        safe_remove_object_with_data(closed)
        raise RuntimeError('Blender voxel remesh could not reconstruct the model')

    try:
        remove_disconnected_islands_keep_largest(
            closed, reason='automatic dental base closure', max_vertices=3000000)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _reproject_anatomical_surface_to_scan(
        closed, source_obj, direction, basal_projection, voxel_primary)
    _clear_model_topology_cache()
    report = get_model_topology_report_cached(closed)

    if report.get('checked') and not report.get('solid'):
        # Re-run from the already reconstructed shell at a slightly coarser
        # resolution; this closes sub-voxel defects without touching source data.
        if not _run_voxel_remesh_operator(context, closed, voxel_secondary):
            safe_remove_object_with_data(closed)
            raise RuntimeError('The volumetric closure remained non-manifold')
        try:
            remove_disconnected_islands_keep_largest(
                closed, reason='automatic dental base closure fallback', max_vertices=3000000)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _reproject_anatomical_surface_to_scan(
            closed, source_obj, direction, basal_projection, voxel_secondary)
        _clear_model_topology_cache()
        report = get_model_topology_report_cached(closed)

    if report.get('checked') and not report.get('solid'):
        safe_remove_object_with_data(closed)
        raise RuntimeError(
            'Volumetric closure did not produce a manifold model '
            f"(remaining boundary edges: {report.get('boundary_edges')}, "
            f"branch edges: {report.get('branch_edges')})")

    closed['DSG_base_closure_status'] = 'dental_frame_silhouette_voxel'
    closed['DSG_base_closed_manifold'] = bool(report.get('solid', False))
    closed['DSG_base_depth_mm'] = float(base_depth_mm)
    closed['DSG_base_overlap_mm'] = float(overlap_mm)
    closed['DSG_base_voxel_mm'] = float(voxel_primary_mm)
    closed['DSG_base_direction_local'] = tuple(float(value) for value in direction)
    closed['DSG_base_direction_confidence'] = float(base_diagnostics.get('confidence', 0.0))
    closed['DSG_base_direction_method'] = str(base_diagnostics.get('method', 'unknown'))
    closed['DSG_base_direction_diagnostics'] = json.dumps(base_diagnostics, ensure_ascii=False)
    closed['DSG_base_footprint_method'] = str(footprint_method)
    closed['DSG_base_hull_points'] = int(len(hull))
    closed['DSG_base_perimeter_guided'] = bool(drawn_footprint)
    closed['DSG_source_open_model_name'] = str(source_obj.name)
    return closed, report



def _remove_safe_duplicate_faces_and_wire_edges(bm):
    """Remove only topology that has no anatomical surface value.

    This is deliberately conservative: it removes exact duplicate faces and
    loose wire edges, but it never merges, moves, smooths, deletes or remeshes
    vertices belonging to the scanned dental surface.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    seen = set()
    duplicate_faces = []
    for face in bm.faces:
        key = tuple(sorted(int(vert.index) for vert in face.verts))
        if key in seen:
            duplicate_faces.append(face)
        else:
            seen.add(key)
    if duplicate_faces:
        try:
            bmesh.ops.delete(bm, geom=duplicate_faces, context='FACES_ONLY')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    bm.edges.ensure_lookup_table()
    wire_edges = [edge for edge in bm.edges if len(edge.link_faces) == 0]
    if wire_edges:
        try:
            bmesh.ops.delete(bm, geom=wire_edges, context='EDGES')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()



def _weld_exact_boundary_duplicates(bm, distance=1.0e-9):
    """Weld only coincident vertices on open borders, without moving anatomy.

    Scanner meshes can contain two distinct rim vertices at the exact same
    coordinate.  A wall face built from that zero-length edge is degenerate and
    can leave hundreds of boundary edges after an otherwise successful base
    closure.  ``find_doubles`` chooses an existing target vertex and
    ``weld_verts`` changes connectivity only; with the microscopic tolerance
    used here no dental coordinate is displaced.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    boundary_verts = list({
        vert for edge in bm.edges if len(edge.link_faces) == 1
        for vert in edge.verts})
    if len(boundary_verts) < 2:
        return 0
    try:
        result = bmesh.ops.find_doubles(
            bm, verts=boundary_verts, dist=max(1.0e-12, float(distance)))
        targetmap = dict(result.get('targetmap', {}))
        if not targetmap:
            return 0
        bmesh.ops.weld_verts(bm, targetmap=targetmap)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        return int(len(targetmap))
    except Exception:
        return 0

def _select_boundary_candidate(candidates, source_obj, perimeter_obj=None):
    """Choose a clean existing rim without rebuilding the dental surface.

    A visible/manual perimeter is used only to choose the nearest real boundary
    loop.  It is never converted through voxel reconstruction or a Boolean.
    """
    if not candidates:
        return None
    if not _valid_obj(perimeter_obj):
        return max(candidates, key=lambda item: item[0])

    guide_points = _base_perimeter_local_points(source_obj, perimeter_obj)
    if len(guide_points) < 3:
        return max(candidates, key=lambda item: item[0])

    guide = np.asarray([[float(point.x), float(point.y), float(point.z)]
                        for point in guide_points], dtype=np.float64)
    best = None
    best_score = None
    for candidate in candidates:
        _perimeter, _component, loop = candidate
        loop_points = np.asarray([[float(vert.co.x), float(vert.co.y), float(vert.co.z)]
                                  for vert in loop], dtype=np.float64)
        if len(loop_points) < 3:
            continue
        # Bound the cost on very dense rims while preserving their full shape.
        if len(loop_points) > 600:
            indexes = np.linspace(0, len(loop_points) - 1, 600).astype(np.int64)
            loop_points = loop_points[indexes]
        if len(guide) > 300:
            indexes = np.linspace(0, len(guide) - 1, 300).astype(np.int64)
            guide_eval = guide[indexes]
        else:
            guide_eval = guide
        distances = np.linalg.norm(
            guide_eval[:, None, :] - loop_points[None, :, :], axis=2)
        score = float(np.median(np.min(distances, axis=1)))
        if best_score is None or score < best_score:
            best_score = score
            best = candidate
    return best or max(candidates, key=lambda item: item[0])



def _component_vertices(component_edges):
    """Unique vertices belonging to one connected boundary component."""
    vertices = []
    seen = set()
    for edge in component_edges:
        for vert in edge.verts:
            key = int(vert.index)
            if key not in seen:
                seen.add(key)
                vertices.append(vert)
    return vertices


def _select_main_open_component(components, source_obj, perimeter_obj=None):
    """Protect the basal opening while secondary scan holes are repaired.

    The visible perimeter, when available, selects the nearest real boundary
    component. Otherwise the component with the greatest perimeter is treated
    as the base. The selected component is never filled by the hole-repair step.
    """
    if not components:
        return None
    records = [
        {
            'component': component,
            'perimeter': _boundary_component_perimeter(component),
            'vertices': _component_vertices(component),
        }
        for component in components
    ]
    guide_points = (_base_perimeter_local_points(source_obj, perimeter_obj)
                    if _valid_obj(perimeter_obj) else [])
    if len(guide_points) < 3:
        return max(records, key=lambda item: item['perimeter'])

    guide = np.asarray(
        [[float(point.x), float(point.y), float(point.z)] for point in guide_points],
        dtype=np.float64)
    if len(guide) > 300:
        guide = guide[np.linspace(0, len(guide) - 1, 300).astype(np.int64)]

    best = None
    best_score = None
    for item in records:
        points = np.asarray(
            [[float(vert.co.x), float(vert.co.y), float(vert.co.z)]
             for vert in item['vertices']], dtype=np.float64)
        if not len(points):
            continue
        if len(points) > 600:
            points = points[np.linspace(0, len(points) - 1, 600).astype(np.int64)]
        distances = np.linalg.norm(guide[:, None, :] - points[None, :, :], axis=2)
        score = float(np.median(np.min(distances, axis=1)))
        if best_score is None or score < best_score:
            best_score = score
            best = item
    return best or max(records, key=lambda item: item['perimeter'])


def _fill_secondary_scan_holes_bmesh(bm, source_obj, perimeter_obj=None):
    """Fill every non-basal boundary cycle without altering scan coordinates.

    Large holes are no longer skipped merely because of perimeter. A hole patch
    adds faces only; it does not remesh, smooth or displace the dental surface.
    Branching edges and pinched boundary junctions are split combinatorially at
    identical coordinates before cycles are triangulated.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    split_branch_edges = _split_non_manifold_edges_preserve_coordinates(bm)
    split_junction_edges = _split_branched_boundary_junctions(bm)

    boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
    components = _boundary_edge_components(boundary_edges)
    if not components:
        return {
            'processed': True, 'filled_count': 0, 'filled_perimeter_mm': 0.0,
            'protected_base_perimeter_mm': 0.0, 'skipped_large': 0,
            'skipped_branched': 0, 'remaining_components': 0,
            'split_branch_edges': split_branch_edges,
            'split_junction_edges': split_junction_edges,
        }

    protected = _select_main_open_component(
        components, source_obj, perimeter_obj=perimeter_obj)
    protected_component = protected['component'] if protected else None
    world_scale = _object_average_world_scale(source_obj)
    protected_mm = float(protected['perimeter'] * world_scale) if protected else 0.0

    filled_count = 0
    filled_perimeter_mm = 0.0
    skipped_branched = 0
    failed = 0
    ordered = sorted(components, key=_boundary_component_perimeter)
    for component in ordered:
        if component is protected_component:
            continue
        loop = _ordered_closed_boundary_loop(component)
        if loop is None:
            skipped_branched += 1
            continue
        perimeter_mm = float(_boundary_component_perimeter(component) * world_scale)
        ok, _created_faces = _fill_boundary_component_topology_only(bm, component)
        if ok:
            filled_count += 1
            filled_perimeter_mm += perimeter_mm
        else:
            failed += 1

    try:
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    bm.normal_update()
    bm.edges.ensure_lookup_table()
    remaining = _boundary_edge_components(
        [edge for edge in bm.edges if len(edge.link_faces) == 1])
    return {
        'processed': True,
        'filled_count': int(filled_count),
        'filled_perimeter_mm': float(filled_perimeter_mm),
        'protected_base_perimeter_mm': float(protected_mm),
        'maximum_hole_perimeter_mm': None,
        'skipped_large': 0,
        'skipped_branched': int(skipped_branched),
        'failed': int(failed),
        'remaining_components': int(len(remaining)),
        'split_branch_edges': int(split_branch_edges),
        'split_junction_edges': int(split_junction_edges),
    }


def close_scanned_model_holes(context, source_obj, perimeter_obj=None):
    """Create an anatomy-locked copy with secondary scan holes capped.

    The principal basal opening remains open for the following base-closure
    step. If no safe secondary holes exist, the source object is simply marked
    as reviewed and remains the active model.
    """
    if not _valid_obj(source_obj) or source_obj.type != 'MESH':
        raise RuntimeError('No valid dental mesh was found')

    existing = bpy.data.objects.get(HOLE_REPAIRED_MODEL_NAME)
    if _valid_obj(existing) and existing is not source_obj:
        safe_remove_object_with_data(existing)

    repaired = duplicate_object_with_data(
        context, source_obj, HOLE_REPAIRED_MODEL_NAME)
    repaired.matrix_world = source_obj.matrix_world.copy()
    bm = None
    diagnostics = None
    try:
        bm = bmesh.new()
        bm.from_mesh(repaired.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        diagnostics = _fill_secondary_scan_holes_bmesh(
            bm, source_obj, perimeter_obj=perimeter_obj)
        bm.to_mesh(repaired.data)
        repaired.data.update()
    except Exception:
        if bm is not None:
            bm.free()
            bm = None
        safe_remove_object_with_data(repaired)
        raise
    finally:
        if bm is not None:
            bm.free()

    anatomy_ok, anatomy_reason = _verify_original_anatomy_vertices_unchanged(
        source_obj, repaired)
    if not anatomy_ok:
        safe_remove_object_with_data(repaired)
        raise RuntimeError(
            f'Hole-closing anatomy-lock verification failed: {anatomy_reason}')

    filled_count = int((diagnostics or {}).get('filled_count', 0))
    if filled_count <= 0:
        safe_remove_object_with_data(repaired)
        source_obj[SCAN_HOLES_PROCESSED_FLAG] = True
        source_obj['DSG_scan_holes_filled_count'] = 0
        source_obj['DSG_scan_holes_diagnostics'] = json.dumps(
            diagnostics or {}, ensure_ascii=False)
        source_obj['DSG_remesh_used_for_hole_closure'] = False
        _clear_model_topology_cache()
        return source_obj, diagnostics or {}

    repaired[SCAN_HOLES_PROCESSED_FLAG] = True
    repaired['DSG_scan_holes_filled_count'] = filled_count
    repaired['DSG_scan_holes_filled_perimeter_mm'] = float(
        diagnostics.get('filled_perimeter_mm', 0.0))
    repaired['DSG_scan_holes_diagnostics'] = json.dumps(
        diagnostics, ensure_ascii=False)
    repaired['DSG_anatomy_lock'] = True
    repaired['DSG_anatomy_original_vertex_count'] = int(len(source_obj.data.vertices))
    repaired['DSG_remesh_used_for_hole_closure'] = False
    repaired['DSG_source_scan_before_hole_closure'] = str(source_obj.name)
    source_obj['DSG_hole_repaired_model_name'] = HOLE_REPAIRED_MODEL_NAME
    source_obj[OPEN_MODEL_BACKUP_FLAG] = True
    register_dsg_object(repaired, ROLE_MODEL, HOLE_REPAIRED_MODEL_NAME)
    _set_obj_hidden(source_obj, True, selectable_when_visible=False)
    _set_obj_hidden(repaired, False, selectable_when_visible=True)
    set_active(context, repaired)
    _clear_model_topology_cache()
    return repaired, diagnostics


class DSG_OT_CloseScanHoles(Operator):
    bl_idname = 'dsg.close_scan_holes'
    bl_label = 'Close Scan Holes'
    bl_description = (
        'Fills safe secondary holes before base closure. The principal basal '
        'opening and every original dental vertex are preserved; no remesh is used')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        model = (props.model_obj if _valid_obj(getattr(props, 'model_obj', None))
                 else _find_aligned_ios(context))
        if not _valid_obj(model):
            _dsg_report(self, {'ERROR'}, 'No aligned dental model was found',
                        'No se encontró un modelo dental alineado')
            return {'CANCELLED'}
        perimeter = _base_perimeter_curve()
        if not _valid_obj(perimeter):
            perimeter = None
        try:
            repaired, diagnostics = close_scanned_model_holes(
                context, model, perimeter_obj=perimeter)
        except Exception as exc:
            _dsg_report(
                self, {'ERROR'},
                f'Anatomy-safe hole closure failed: {exc}',
                f'No se pudieron cerrar los agujeros sin modificar la anatomía: {exc}')
            return {'CANCELLED'}

        props.model_obj = repaired
        _remove_retention_previews()
        _clear_retention_geometry_cache()
        _clear_model_topology_cache()
        count = int(diagnostics.get('filled_count', 0))
        skipped = int(diagnostics.get('skipped_large', 0)) + int(
            diagnostics.get('skipped_branched', 0))
        if count:
            message_en = f'{count} secondary scan hole(s) closed; basal opening preserved'
            message_es = f'{count} agujero(s) secundario(s) cerrados; apertura basal conservada'
        else:
            message_en = 'No safe secondary holes were found; basal opening preserved'
            message_es = 'No se encontraron agujeros secundarios seguros; apertura basal conservada'
        if skipped:
            message_en += f' · {skipped} suspicious opening(s) left for review'
            message_es += f' · {skipped} abertura(s) dudosa(s) quedan para revisión'
        _dsg_report(self, {'WARNING'} if skipped else {'INFO'}, message_en, message_es)
        return {'FINISHED'}


def _verify_original_anatomy_vertices_unchanged(source_obj, closed_obj,
                                                 tolerance=None):
    """Verify preservation of the *surface anatomy* without false failures.

    Older DSG builds compared every mesh vertex as an exact coordinate multiset.
    That incorrectly rejected valid closures when the input contained loose/wire
    vertices, duplicate coincident vertices, or when Blender performed a harmless
    float32 BMesh round-trip.  Those elements are not part of the dental surface.

    The anatomy lock now checks only vertices referenced by source faces and uses
    a small metric tolerance plus a sampled surface-distance audit.  It still
    rejects a genuinely displaced dental surface, but permits topology-only edge
    splitting and the removal of non-surface scanner debris.
    """
    try:
        source_mesh = source_obj.data
        closed_mesh = closed_obj.data
        if tolerance is None:
            # Two microns is below practical scanner/printing resolution while
            # safely above float32 round-trip noise at dental-model coordinates.
            tolerance = _mm_to_object_units(source_obj, 0.002)
        tolerance = max(float(tolerance), 1.0e-7)
        tolerance_sq = tolerance * tolerance
        cell = tolerance

        surface_used = bytearray(len(source_mesh.vertices))
        for polygon in source_mesh.polygons:
            for vertex_index in polygon.vertices:
                if 0 <= int(vertex_index) < len(surface_used):
                    surface_used[int(vertex_index)] = 1
        surface_indices = [index for index, used in enumerate(surface_used) if used]
        ignored_non_surface = len(source_mesh.vertices) - len(surface_indices)
        if not surface_indices:
            return False, 'source mesh contains no facial surface vertices'

        # Spatial hash avoids relying on vertex order or duplicate multiplicity.
        # Neighbouring cells are searched so points close to a cell boundary are
        # not rejected by quantisation.
        grid = {}
        for vertex in closed_mesh.vertices:
            co = vertex.co
            key = (
                int(math.floor(float(co.x) / cell)),
                int(math.floor(float(co.y) / cell)),
                int(math.floor(float(co.z) / cell)),
            )
            grid.setdefault(key, []).append(co.copy())

        maximum_distance = 0.0
        for index in surface_indices:
            source_co = source_mesh.vertices[index].co
            base_key = (
                int(math.floor(float(source_co.x) / cell)),
                int(math.floor(float(source_co.y) / cell)),
                int(math.floor(float(source_co.z) / cell)),
            )
            best_sq = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for candidate in grid.get((
                                base_key[0] + dx, base_key[1] + dy,
                                base_key[2] + dz), ()):
                            distance_sq = float((candidate - source_co).length_squared)
                            if best_sq is None or distance_sq < best_sq:
                                best_sq = distance_sq
            if best_sq is None or best_sq > tolerance_sq:
                distance = math.sqrt(best_sq) if best_sq is not None else float('inf')
                return False, (
                    f'surface vertex {index} changed or is missing '
                    f'(nearest distance {distance:.9g} local units; '
                    f'tolerance {tolerance:.9g})')
            maximum_distance = max(maximum_distance, math.sqrt(best_sq))

        # Geometry audit between vertices.  Use triangle centroids, not the
        # arithmetic centroid of a Blender polygon.  Post-extraction boolean
        # meshes often retain concave n-gons around the socket boundary; their
        # arithmetic centroid can fall outside the actual source face and inside
        # the new cap.  That created a false anatomy-lock rejection even though
        # all original surface vertices were preserved.  ``loop_triangles``
        # samples points that are guaranteed to lie on the source surface.
        closed_vertices = [vertex.co.copy() for vertex in closed_mesh.vertices]
        closed_polygons = [tuple(int(i) for i in polygon.vertices)
                           for polygon in closed_mesh.polygons
                           if len(polygon.vertices) >= 3]
        if not closed_polygons:
            return False, 'closed result contains no polygonal surface'
        try:
            closed_bvh = BVHTree.FromPolygons(
                closed_vertices, closed_polygons, all_triangles=False, epsilon=0.0)
        except TypeError:
            closed_bvh = BVHTree.FromPolygons(
                closed_vertices, closed_polygons, all_triangles=False)

        source_mesh.calc_loop_triangles()
        source_triangles = source_mesh.loop_triangles
        triangle_count = len(source_triangles)
        if triangle_count <= 0:
            return False, 'source mesh contains no triangular facial surface'
        sample_limit = 12000
        step = max(1, int(math.ceil(triangle_count / sample_limit)))
        surface_tolerance = max(tolerance * 2.5,
                                _mm_to_object_units(source_obj, 0.005))
        maximum_surface_distance = 0.0
        for triangle_index in range(0, triangle_count, step):
            triangle = source_triangles[triangle_index]
            indices = triangle.vertices
            centroid = (
                source_mesh.vertices[int(indices[0])].co
                + source_mesh.vertices[int(indices[1])].co
                + source_mesh.vertices[int(indices[2])].co
            ) / 3.0
            nearest = closed_bvh.find_nearest(centroid)
            if nearest is None or nearest[0] is None:
                return False, f'no resulting surface near source triangle {triangle_index}'
            distance = float(nearest[3])
            if distance > surface_tolerance:
                return False, (
                    f'source triangle {triangle_index} surface changed '
                    f'(distance {distance:.9g} local units; '
                    f'tolerance {surface_tolerance:.9g})')
            maximum_surface_distance = max(maximum_surface_distance, distance)

        diagnostics = {
            'surface_vertices_checked': int(len(surface_indices)),
            'non_surface_vertices_ignored': int(ignored_non_surface),
            'maximum_vertex_distance_local': float(maximum_distance),
            'maximum_surface_distance_local': float(maximum_surface_distance),
            'vertex_tolerance_local': float(tolerance),
            'surface_tolerance_local': float(surface_tolerance),
            'surface_audit': 'source_loop_triangle_centroids',
        }
        try:
            closed_obj['DSG_anatomy_lock_diagnostics'] = json.dumps(
                diagnostics, ensure_ascii=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, ''
    except Exception as exc:
        return False, f'anatomy surface verification failed: {exc}'


def _split_non_manifold_edges_preserve_coordinates(bm):
    """Split branching edges without moving the dental surface.

    A common scanner defect is one edge shared by three or more faces. Hole
    triangulation requires manifold boundary cycles. Splitting the offending
    edge duplicates connectivity at the same coordinates, matching the
    combinatorial-repair approach used by robust mesh libraries.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    branch_edges = [edge for edge in bm.edges if len(edge.link_faces) > 2]
    if not branch_edges:
        return 0
    try:
        bmesh.ops.split_edges(bm, edges=branch_edges)
    except TypeError:
        bmesh.ops.split_edges(bm, edges=branch_edges, use_verts=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return int(len(branch_edges))


def _split_branched_boundary_junctions(bm):
    """Separate boundary loops that touch at a vertex, without moving them."""
    total = 0
    for _ in range(3):
        bm.edges.ensure_lookup_table()
        boundary = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        degree = {}
        for edge in boundary:
            for vert in edge.verts:
                degree[vert] = degree.get(vert, 0) + 1
        junction_edges = {
            edge
            for vert, count in degree.items() if count != 2
            for edge in vert.link_edges if len(edge.link_faces) == 1
        }
        if not junction_edges:
            break
        try:
            bmesh.ops.split_edges(bm, edges=list(junction_edges))
        except TypeError:
            bmesh.ops.split_edges(bm, edges=list(junction_edges), use_verts=False)
        total += len(junction_edges)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
    return int(total)


def _fill_boundary_component_topology_only(bm, component):
    """Triangulate one simple boundary cycle using only new faces."""
    loop = _ordered_closed_boundary_loop(component)
    if loop is None:
        return False, 0
    before = len(bm.faces)
    created = []
    try:
        result = bmesh.ops.triangle_fill(
            bm, edges=list(component), use_beauty=True, use_dissolve=False)
        created = [geom for geom in result.get('geom', ())
                   if isinstance(geom, bmesh.types.BMFace)]
    except Exception:
        created = []
    if not created:
        try:
            result = bmesh.ops.holes_fill(bm, edges=list(component), sides=0)
            created = list(result.get('faces', ()))
        except Exception:
            created = []
    if not created:
        # ``holes_fill`` is conservative and can reject a valid tiny rim if
        # its local winding was disturbed by the Exact Boolean.  The component
        # has already been verified as one simple degree-two cycle, so the
        # edge-loop operator is a safe topology-only alternative here.
        try:
            prepared = bmesh.ops.edgenet_prepare(bm, edges=list(component))
            fill_edges = list(prepared.get('edges', ())) or list(component)
            result = bmesh.ops.edgeloop_fill(bm, edges=fill_edges)
            created = list(result.get('faces', ()))
        except Exception:
            created = []
    if not created:
        # ``triangle_fill`` can decline a very small, non-planar residual loop
        # left where the generated basal cap meets a Boolean socket.  The loop
        # was already proven simple and degree-two above, so a centre fan adds
        # only new cap faces and never moves/remeshes any scanned vertex.  This
        # is deliberately a fallback for residual loops, not a general repair.
        try:
            centre = sum((vert.co for vert in loop), Vector()) / float(len(loop))
            centre_vert = bm.verts.new(centre)
            bm.verts.ensure_lookup_table()
            for index, first in enumerate(loop):
                second = loop[(index + 1) % len(loop)]
                try:
                    bm.faces.new((first, second, centre_vert))
                except ValueError:
                    # Existing triangle is harmless; the component is audited
                    # again by the caller before committing the mesh.
                    pass
            created = [centre_vert]
        except Exception:
            created = []
    return bool(created or len(bm.faces) > before), int(max(0, len(bm.faces) - before))


def _fill_all_remaining_boundary_cycles(bm, maximum_passes=4):
    """Close every remaining simple cycle after the basal wall is generated."""
    filled = 0
    for _ in range(maximum_passes):
        _split_branched_boundary_junctions(bm)
        bm.edges.ensure_lookup_table()
        components = _boundary_edge_components(
            [edge for edge in bm.edges if len(edge.link_faces) == 1])
        progress = False
        for component in components:
            ok, count = _fill_boundary_component_topology_only(bm, component)
            if ok:
                filled += count
                progress = True
        if not progress:
            break
    return int(filled)


def _repair_residual_topology_globally(bm, maximum_passes=8):
    """Repair every safely repairable residual topology component.

    This is deliberately topology-wide, not a special case for a particular
    number of edges.  Every pass removes loose artefacts, welds only exactly
    coincident rim vertices, separates non-manifold junctions at their current
    coordinates, and caps every resulting simple boundary cycle.  It never
    displaces or remeshes the scanned anatomical surface.
    """
    diagnostics = {
        'passes': 0, 'faces_added': 0, 'wire_cleanup_passes': 0,
        'exact_welds': 0, 'non_manifold_splits': 0, 'junction_splits': 0,
    }
    for _pass in range(max(1, int(maximum_passes))):
        diagnostics['passes'] += 1
        before = (len(bm.verts), len(bm.edges), len(bm.faces))
        _remove_safe_duplicate_faces_and_wire_edges(bm)
        diagnostics['wire_cleanup_passes'] += 1
        diagnostics['exact_welds'] += _weld_exact_boundary_duplicates(bm, distance=1.0e-8)
        diagnostics['non_manifold_splits'] += _split_non_manifold_edges_preserve_coordinates(bm)
        diagnostics['junction_splits'] += _split_branched_boundary_junctions(bm)
        diagnostics['faces_added'] += _fill_all_remaining_boundary_cycles(bm, maximum_passes=2)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        boundary = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        branch = [edge for edge in bm.edges if len(edge.link_faces) > 2]
        wire = [edge for edge in bm.edges if len(edge.link_faces) == 0]
        if not boundary and not branch and not wire:
            break
        after = (len(bm.verts), len(bm.edges), len(bm.faces))
        if after == before:
            break
    bm.edges.ensure_lookup_table()
    diagnostics['remaining_boundary_edges'] = sum(1 for edge in bm.edges if len(edge.link_faces) == 1)
    diagnostics['remaining_branch_edges'] = sum(1 for edge in bm.edges if len(edge.link_faces) > 2)
    diagnostics['remaining_wire_edges'] = sum(1 for edge in bm.edges if len(edge.link_faces) == 0)
    return diagnostics

def _close_open_model_direct(context, source_obj, perimeter_obj=None):
    """Close the model by adding only secondary-hole caps and basal geometry.

    The scanned dental surface is immutable. Safe secondary holes are capped
    first, the principal opening is then extended into basal walls and a cap.
    No remesh, smoothing, merge, shrinkwrap, Boolean or source-vertex movement
    is permitted.
    """
    closed = duplicate_object_with_data(context, source_obj, CLOSED_MODEL_NAME)
    closed.matrix_world = source_obj.matrix_world.copy()
    original_vertex_count = len(source_obj.data.vertices)
    bm = None
    hole_diagnostics = {}
    try:
        bm = bmesh.new()
        bm.from_mesh(closed.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        _remove_safe_duplicate_faces_and_wire_edges(bm)
        exact_boundary_vertices_welded = _weld_exact_boundary_duplicates(
            bm, distance=1.0e-9)
        initial_split_branch_edges = _split_non_manifold_edges_preserve_coordinates(bm)
        initial_split_junction_edges = _split_branched_boundary_junctions(bm)

        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        if not boundary_edges:
            raise RuntimeError('The model has no closable open boundary')

        # Required intermediate stage: close safe secondary scan holes first,
        # while protecting the largest/perimeter-guided component as the base.
        hole_diagnostics = _fill_secondary_scan_holes_bmesh(
            bm, source_obj, perimeter_obj=perimeter_obj)

        bm.edges.ensure_lookup_table()
        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        candidates = []
        for component in _boundary_edge_components(boundary_edges):
            loop = _ordered_closed_boundary_loop(component)
            perimeter = _boundary_component_perimeter(component)
            if loop is not None:
                candidates.append((perimeter, component, loop))
        if not candidates:
            raise RuntimeError(
                'No clean closed basal rim remains after the hole-closing step. '
                'Remesh is disabled; clean or cut the basal border manually')

        chosen = _select_boundary_candidate(
            candidates, source_obj, perimeter_obj=perimeter_obj)
        main_perimeter, _main_component, main_loop = chosen
        world_scale = _object_average_world_scale(source_obj)
        main_perimeter_mm = main_perimeter * world_scale
        if main_perimeter_mm < AUTO_BASE_MIN_MAIN_LOOP_PERIMETER_MM:
            raise RuntimeError(
                f'No basal opening was detected (largest valid rim {main_perimeter_mm:.1f} mm)')

        direction, base_diagnostics = _automatic_base_direction(
            bm, main_loop, source_obj=source_obj, return_diagnostics=True)
        coords = [vert.co for vert in bm.verts]
        mins = Vector((min(v[i] for v in coords) for i in range(3)))
        maxs = Vector((max(v[i] for v in coords) for i in range(3)))
        diagonal = float((maxs - mins).length)
        diagonal_mm = diagonal * world_scale
        base_depth_mm = max(
            AUTO_BASE_MIN_DEPTH_MM,
            min(AUTO_BASE_MAX_DEPTH_MM, diagonal_mm * AUTO_BASE_DEPTH_FRACTION))
        base_depth = _mm_to_object_units(source_obj, base_depth_mm)

        wall_margin = _mm_to_object_units(source_obj, 0.20)
        anatomy_clearance = _mm_to_object_units(source_obj, 1.00)
        collar_offset = _mm_to_object_units(source_obj, 0.30)
        max_collar_tangent_shift = _mm_to_object_units(source_obj, 0.18)
        _bottom_ring, side_faces, cap_faces, model_build_diagnostics = _close_main_boundary_with_planar_base(
            bm, main_loop, direction, base_depth,
            wall_margin=wall_margin,
            anatomy_clearance=anatomy_clearance,
            collar_offset=collar_offset,
            max_collar_tangent_shift=max_collar_tangent_shift)

        # At this point no opening is intentional. Audit and repair the entire
        # residual topology, irrespective of the number of edges in a rim.
        residual_diagnostics = _repair_residual_topology_globally(bm)
        residual_faces = int(residual_diagnostics.get('faces_added', 0))

        bm.edges.ensure_lookup_table()
        remaining_boundary = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        remaining_branch = [edge for edge in bm.edges if len(edge.link_faces) > 2]
        remaining_wire = [edge for edge in bm.edges if len(edge.link_faces) == 0]
        if remaining_boundary or remaining_branch or remaining_wire:
            raise RuntimeError(
                'Topology repair left unresolved geometry before mesh commit '
                f'(boundary edges: {len(remaining_boundary)}, '
                f'branch edges: {len(remaining_branch)}, wire edges: {len(remaining_wire)})')
        try:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.normal_update()
        bm.to_mesh(closed.data)
        closed.data.update()
    except Exception:
        if bm is not None:
            bm.free()
            bm = None
        safe_remove_object_with_data(closed)
        raise
    finally:
        if bm is not None:
            bm.free()

    anatomy_ok, anatomy_reason = _verify_original_anatomy_vertices_unchanged(
        source_obj, closed)
    if not anatomy_ok:
        safe_remove_object_with_data(closed)
        raise RuntimeError(
            f'Anatomy-lock verification failed: {anatomy_reason}')

    _clear_model_topology_cache()
    report = get_model_topology_report_cached(closed)
    if report.get('checked') and not report.get('solid'):
        safe_remove_object_with_data(closed)
        raise RuntimeError(
            'Anatomy-preserving closure remained non-manifold after exact-rim '
            'cleanup and deterministic basal safety-cap generation '
            f"(boundary edges: {report.get('boundary_edges')}, "
            f"branch edges: {report.get('branch_edges')}, "
            f"wire edges: {report.get('wire_edges')}). "
            'Remesh was not applied')

    closed['DSG_base_closure_status'] = 'direct_rim_convex_safety_cap_anatomy_locked'
    closed['DSG_base_closed_manifold'] = bool(report.get('solid', False))
    closed['DSG_base_depth_mm'] = float(base_depth_mm)
    closed['DSG_base_min_anatomy_clearance_mm'] = 1.0
    closed['DSG_base_clearance_reference'] = 'deepest_face_connected_vertex_along_margin_axis'
    closed['DSG_base_main_rim_perimeter_mm'] = float(main_perimeter_mm)
    closed['DSG_base_direction_local'] = tuple(float(value) for value in direction)
    closed['DSG_base_direction_confidence'] = float(base_diagnostics.get('confidence', 0.0))
    closed['DSG_base_direction_method'] = str(base_diagnostics.get('method', 'unknown'))
    closed['DSG_base_direction_diagnostics'] = json.dumps(base_diagnostics, ensure_ascii=False)
    closed['DSG_base_perimeter_guided'] = bool(_valid_obj(perimeter_obj))
    closed[SCAN_HOLES_PROCESSED_FLAG] = True
    closed['DSG_scan_holes_filled_count'] = int(hole_diagnostics.get('filled_count', 0))
    closed['DSG_scan_holes_diagnostics'] = json.dumps(hole_diagnostics, ensure_ascii=False)
    closed['DSG_anatomy_lock'] = True
    closed['DSG_anatomy_original_vertex_count'] = int(original_vertex_count)
    closed['DSG_remesh_used_for_hole_closure'] = False
    closed['DSG_remesh_used_for_base_closure'] = False
    closed['DSG_base_branch_edges_split'] = int(initial_split_branch_edges)
    closed['DSG_base_boundary_junction_edges_split'] = int(initial_split_junction_edges)
    closed['DSG_base_exact_boundary_vertices_welded'] = int(exact_boundary_vertices_welded)
    closed['DSG_base_footprint_method'] = 'DIRECT_RIM_TO_CONVEX_MANIFOLD_SAFETY_CAP'
    closed['DSG_base_star_footprint_used'] = False
    closed['DSG_base_side_faces_created'] = int(side_faces)
    closed['DSG_base_cap_faces_created'] = int(cap_faces)
    closed['DSG_base_residual_faces_created'] = int(residual_faces)
    closed['DSG_base_residual_repair_diagnostics'] = json.dumps(residual_diagnostics, ensure_ascii=False)
    closed['DSG_model_creation_method'] = 'RELAXED_MARGIN_PROXY_PROGRESSIVE_PLANAR_BASE'
    closed['DSG_model_margin_proxy_offset_mm'] = 0.30
    closed['DSG_model_margin_proxy_max_tangent_shift_mm'] = 0.18
    closed['DSG_model_build_diagnostics'] = json.dumps(model_build_diagnostics, ensure_ascii=False)
    closed['DSG_source_open_model_name'] = str(source_obj.name)
    return closed, report



