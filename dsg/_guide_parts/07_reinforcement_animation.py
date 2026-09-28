def get_pending_reinforcement_preview(props):
    obj = getattr(props, 'reinforcement_preview_obj', None)
    if _valid_obj(obj) and bool(obj.get('DSG_reinforcement_preview', False)):
        return obj
    candidate = bpy.data.objects.get(REINFORCEMENT_PREVIEW_NAME)
    if _valid_obj(candidate) and bool(candidate.get('DSG_reinforcement_preview', False)):
        return candidate
    return None


def get_confirmed_reinforcement_curves():
    out = []
    for obj in list(bpy.data.objects):
        try:
            if (obj.name.startswith(REINFORCEMENT_PREFIX)
                    and obj.name != REINFORCEMENT_PREVIEW_NAME
                    and obj.type in {'CURVE', 'MESH'}
                    and bool(obj.get('DSG_reinforcement_confirmed', False))
                    and _valid_obj(obj)):
                out.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    return sorted(out, key=lambda item: int(item.get('DSG_reinforcement_index', 0)))


def _orient_surface_normal_to_view(context, event, normal):
    n = Vector(normal) if normal is not None else Vector((0.0, 0.0, 1.0))
    if n.length < 1e-8:
        n = Vector((0.0, 0.0, 1.0))
    n.normalize()
    _origin, ray_dir = get_view_ray(context, event)
    if ray_dir is not None and n.dot(ray_dir) > 0.0:
        n.negate()
    return n


def _build_guide_bvh(context, guide_obj):
    if not _valid_obj(guide_obj) or guide_obj.type != 'MESH':
        return None, None, None
    try:
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = guide_obj.evaluated_get(depsgraph)
        matrix = evaluated.matrix_world.copy()
        tree = BVHTree.FromObject(evaluated, depsgraph)
        return tree, matrix, matrix.inverted()
    except Exception as exc:
        print(f'[DSG] Reinforcement BVH unavailable: {exc}')
        return None, None, None


def _nearest_guide_surface(tree, matrix, inverse, point_world, normal_hint=None):
    if tree is None:
        return Vector(point_world), (Vector(normal_hint) if normal_hint is not None else Vector((0.0, 0.0, 1.0))).normalized()
    try:
        result = tree.find_nearest(inverse @ Vector(point_world))
        if not result or result[0] is None:
            raise RuntimeError('no nearby point')
        loc_local, normal_local, _index, _distance = result
        location = matrix @ loc_local
        normal = (matrix.to_3x3() @ normal_local).normalized()
        if normal_hint is not None and normal.dot(Vector(normal_hint)) < 0.0:
            normal.negate()
        return location, normal
    except Exception:
        fallback = Vector(normal_hint) if normal_hint is not None else Vector((0.0, 0.0, 1.0))
        if fallback.length < 1e-8:
            fallback = Vector((0.0, 0.0, 1.0))
        return Vector(point_world), fallback.normalized()




def _catmull_rom_knot(t, point_a, point_b, alpha=0.5):
    distance = max((Vector(point_b) - Vector(point_a)).length, 1e-6)
    return float(t) + distance ** float(alpha)


def _catmull_rom_centripetal_segment(p0, p1, p2, p3, samples=12, alpha=0.5):
    """Muestrea el tramo P1→P2 con parametrización centrípeta.

    La implementación evita handles Bézier libres y no proyecta cada control
    sobre superficies cercanas, dos causas de los bucles observados alrededor
    del sleeve.
    """
    p0, p1, p2, p3 = map(Vector, (p0, p1, p2, p3))
    t0 = 0.0
    t1 = _catmull_rom_knot(t0, p0, p1, alpha)
    t2 = _catmull_rom_knot(t1, p1, p2, alpha)
    t3 = _catmull_rom_knot(t2, p2, p3, alpha)

    def blend(a, b, ta, tb, t):
        denom = tb - ta
        if abs(denom) < 1e-9:
            return a.copy()
        return a * ((tb - t) / denom) + b * ((t - ta) / denom)

    out = []
    count = max(4, int(samples))
    for index in range(count):
        u = index / float(count)
        t = t1 + (t2 - t1) * u
        a1 = blend(p0, p1, t0, t1, t)
        a2 = blend(p1, p2, t1, t2, t)
        a3 = blend(p2, p3, t2, t3, t)
        b1 = blend(a1, a2, t0, t2, t)
        b2 = blend(a2, a3, t1, t3, t)
        out.append(blend(b1, b2, t1, t2, t))
    return out


def _sample_centripetal_catmull_rom(control_points, samples_per_segment=12):
    controls = []
    for point in control_points:
        p = Vector(point)
        if not controls or (p - controls[-1]).length > 1e-4:
            controls.append(p)
    if len(controls) < 2:
        return controls
    if len(controls) == 2:
        return [controls[0].lerp(controls[1], i / 15.0) for i in range(16)]

    phantom_start = controls[0] + (controls[0] - controls[1])
    phantom_end = controls[-1] + (controls[-1] - controls[-2])
    padded = [phantom_start] + controls + [phantom_end]
    sampled = []
    for index in range(len(controls) - 1):
        segment = _catmull_rom_centripetal_segment(
            padded[index], padded[index + 1], padded[index + 2], padded[index + 3],
            samples=samples_per_segment, alpha=0.5)
        sampled.extend(segment)
    sampled.append(controls[-1].copy())
    return sampled


def _reinforcement_outward_direction(chord_direction, normal_a, normal_b):
    chord = _normalized_or_fallback(chord_direction, (1.0, 0.0, 0.0))
    combined = Vector(normal_a) + Vector(normal_b)
    if combined.length < 1e-8:
        combined = Vector(normal_a)
    outward = combined - chord * combined.dot(chord)
    if outward.length < 1e-8:
        outward = Vector(normal_a) - chord * Vector(normal_a).dot(chord)
    if outward.length < 1e-8:
        reference = Vector((0.0, 0.0, 1.0))
        if abs(chord.dot(reference)) > 0.90:
            reference = Vector((1.0, 0.0, 0.0))
        outward = chord.cross(reference).cross(chord)
    return _normalized_or_fallback(outward, (0.0, 0.0, 1.0))


def _raycast_evaluated_reinforcement_target(context, event, obj):
    """Raycast individual sobre MESH o CURVE evaluada.

    Los refuerzos confirmados permanecen como CURVE hasta aplicar el paso 8 visible.
    Para poder colocar un nuevo apoyo directamente sobre ellos se convierte solo
    su geometría evaluada a una malla temporal en memoria; no se modifica el objeto.
    """
    if not _valid_obj(obj):
        return None, None, None, None

    ray_origin_world, ray_dir_world = get_view_ray(context, event)
    if ray_origin_world is None or ray_dir_world is None:
        return None, None, None, None

    if obj.type == 'MESH':
        location, normal, face_index = do_raycast_detailed(context, event, obj)
        if location is None:
            return None, None, None, None
        return location, normal, face_index, (Vector(location) - ray_origin_world).length

    depsgraph = context.evaluated_depsgraph_get()
    evaluated = None
    temp_mesh = None
    try:
        evaluated = obj.evaluated_get(depsgraph)
        try:
            temp_mesh = evaluated.to_mesh(
                preserve_all_data_layers=False, depsgraph=depsgraph)
        except TypeError:
            temp_mesh = evaluated.to_mesh()
        if temp_mesh is None or len(temp_mesh.vertices) == 0 or len(temp_mesh.polygons) == 0:
            return None, None, None, None

        matrix = evaluated.matrix_world.copy()
        inverse = matrix.inverted_safe()
        origin_local = inverse @ ray_origin_world
        target_local = inverse @ (ray_origin_world + ray_dir_world * 10000.0)
        direction_local = target_local - origin_local
        if direction_local.length < 1e-8:
            return None, None, None, None
        direction_local.normalize()

        vertices = [vertex.co.copy() for vertex in temp_mesh.vertices]
        polygons = [tuple(poly.vertices) for poly in temp_mesh.polygons if len(poly.vertices) >= 3]
        if not polygons:
            return None, None, None, None
        tree = BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
        hit = tree.ray_cast(origin_local, direction_local, 10000.0)
        if not hit or hit[0] is None:
            return None, None, None, None
        location_local, normal_local, face_index, _distance = hit
        location_world = matrix @ location_local
        normal_world = matrix.to_3x3() @ normal_local
        if normal_world.length < 1e-8:
            normal_world = Vector((0.0, 0.0, 1.0))
        else:
            normal_world.normalize()
        return location_world, normal_world, face_index, (location_world - ray_origin_world).length
    except Exception as exc:
        print(f'[DSG] Reinforcement support raycast skipped ({_safe_object_name(obj)}): {exc}')
        return None, None, None, None
    finally:
        if evaluated is not None and temp_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def raycast_reinforcement_support(context, event, guide_obj):
    """Devuelve el apoyo visible más cercano entre guía y refuerzos confirmados."""
    candidates = []
    if _valid_obj(guide_obj):
        candidates.append(guide_obj)
    candidates.extend(get_confirmed_reinforcement_curves())

    best = None
    for candidate in candidates:
        location, normal, face_index, distance = _raycast_evaluated_reinforcement_target(
            context, event, candidate)
        if location is None or normal is None or distance is None:
            continue
        if best is None or distance < best[3]:
            best = (Vector(location), Vector(normal), candidate, float(distance), face_index)

    if best is None:
        return None, None, None
    location, normal, candidate, _distance, _face_index = best
    normal = _orient_surface_normal_to_view(context, event, normal)
    return location, normal, candidate


def remove_reinforcement_markers():
    for obj in list(bpy.data.objects):
        try:
            matches = (obj.name == REINFORCEMENT_MARKER_NAME
                       or obj.name.startswith(REINFORCEMENT_MARKER_PREFIX))
        except Exception:
            matches = False
        if matches:
            safe_remove_object(obj)


def refresh_reinforcement_markers(context, points, support_names=None):
    remove_reinforcement_markers()
    support_names = list(support_names or [])
    marker_radius = max(0.50, float(getattr(context.scene.dsg_props, 'connector_diameter', REINFORCEMENT_DIAMETER_MM)) * 0.22)
    for index, coordinate in enumerate(points):
        name = (REINFORCEMENT_MARKER_NAME if index == 0
                else f'{REINFORCEMENT_MARKER_PREFIX}{index + 1:02d}')
        marker_mesh = make_uv_sphere_mesh(name + '_Mesh', marker_radius, 16, 8)
        marker = bpy.data.objects.new(name, marker_mesh)
        marker.location = Vector(coordinate)
        link_object(context, marker)
        register_dsg_object(marker, ROLE_REINFORCEMENT, name, {
            'DSG_reinforcement_marker': True,
            'DSG_reinforcement_marker_index': index,
            'DSG_reinforcement_support': support_names[index] if index < len(support_names) else '',
        })
        marker.display_type = 'WIRE'
        marker.show_in_front = True
        marker.hide_render = True


def _clean_reinforcement_chain(points, normals, support_objects=None):
    clean_points = []
    clean_normals = []
    clean_supports = []
    support_objects = list(support_objects or [])
    for index, point in enumerate(points):
        coordinate = Vector(point)
        if clean_points and (coordinate - clean_points[-1]).length <= 1e-4:
            continue
        normal = Vector(normals[index]) if index < len(normals) else Vector((0.0, 0.0, 1.0))
        normal = _normalized_or_fallback(normal, (0.0, 0.0, 1.0))
        clean_points.append(coordinate)
        clean_normals.append(normal)
        clean_supports.append(support_objects[index] if index < len(support_objects) else None)
    return clean_points, clean_normals, clean_supports



def _build_world_surface_bvh(context, obj):
    """Construye un BVH en coordenadas World para MESH o CURVE evaluada."""
    if not _valid_obj(obj):
        return None
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = None
    temp_mesh = None
    try:
        evaluated = obj.evaluated_get(depsgraph)
        try:
            temp_mesh = evaluated.to_mesh(
                preserve_all_data_layers=False, depsgraph=depsgraph)
        except TypeError:
            temp_mesh = evaluated.to_mesh()
        if temp_mesh is None or len(temp_mesh.vertices) == 0 or len(temp_mesh.polygons) == 0:
            return None
        matrix = evaluated.matrix_world.copy()
        vertices = [matrix @ vertex.co for vertex in temp_mesh.vertices]
        polygons = [tuple(poly.vertices) for poly in temp_mesh.polygons if len(poly.vertices) >= 3]
        if not polygons:
            return None
        return BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
    except Exception as exc:
        print(f'[DSG] Coons support BVH unavailable ({_safe_object_name(obj)}): {exc}')
        return None
    finally:
        if evaluated is not None and temp_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _nearest_support_surface_world(tree, candidate, normal_hint, max_distance):
    candidate = Vector(candidate)
    hint = _normalized_or_fallback(normal_hint, (0.0, 0.0, 1.0))
    if tree is None:
        return candidate, hint
    try:
        result = tree.find_nearest(candidate)
        if not result or result[0] is None:
            return candidate, hint
        location, normal, _index, distance = result
        if distance is None or float(distance) > max(0.25, float(max_distance)):
            return candidate, hint
        normal = _normalized_or_fallback(normal, hint)
        if normal.dot(hint) < 0.0:
            normal.negate()
        return Vector(location), normal
    except Exception:
        return candidate, hint


def _bvh_world_ray_distance(tree, origin, direction, max_distance):
    if tree is None:
        return None
    origin = Vector(origin)
    direction = _normalized_or_fallback(direction, (1.0, 0.0, 0.0))
    distance_limit = max(0.20, float(max_distance))
    try:
        result = tree.ray_cast(origin, direction, distance_limit)
        if not result or result[0] is None:
            return None
        _location, _normal, _index, distance = result
        if distance is None:
            return None
        return max(0.0, float(distance))
    except Exception:
        return None


def _bvh_world_ray_hit_count(tree, origin, direction, max_distance, max_hits=96):
    """Count BVH ray hits while stepping past each intersection."""
    if tree is None:
        return 0
    direction = _normalized_or_fallback(direction, (1.0, 0.0, 0.0))
    current = Vector(origin)
    remaining = max(0.20, float(max_distance))
    hits = 0
    step = 0.002
    try:
        for _i in range(max(1, int(max_hits))):
            result = tree.ray_cast(current, direction, remaining)
            if not result or result[0] is None:
                break
            location, _normal, _index, distance = result
            if distance is None:
                break
            distance = max(0.0, float(distance))
            hits += 1
            advance = distance + step
            remaining -= advance
            if remaining <= 0.0:
                break
            current = Vector(location) + direction * step
    except Exception:
        return hits
    return hits


def _bvh_point_inside_solid(tree, point, tolerance=0.02, max_distance=10000.0):
    """Best-effort inside test for closed model cutters.

    The lumen/model preflight must catch the case where the water centreline is
    already inside a tooth/model.  A nearest-surface distance alone misses that
    situation because the nearest model surface can be farther away than the
    water radius.  This helper combines the nearest normal sign with ray-parity
    votes in several directions.
    """
    if tree is None:
        return False
    point = Vector(point)
    tol = max(0.001, float(tolerance))
    normal_inside = False
    try:
        nearest = tree.find_nearest(point)
        if nearest and nearest[0] is not None:
            location, normal, _index, distance = nearest
            if distance is not None and float(distance) <= tol:
                return True
            normal = _normalized_or_fallback(normal, (1.0, 0.0, 0.0))
            # With outward normals, points inside lie behind the nearest face.
            normal_inside = (point - Vector(location)).dot(normal) < -tol
    except Exception:
        normal_inside = False

    directions = (
        Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)),
        Vector((0.0, 0.0, 1.0)), Vector((0.577, 0.577, 0.577)),
        Vector((-0.577, 0.577, 0.577)),
    )
    votes = 0
    usable = 0
    for direction in directions:
        try:
            start = point + direction * (tol * 0.25)
            count = _bvh_world_ray_hit_count(
                tree, start, direction, max_distance=max_distance, max_hits=96)
            if count <= 0:
                continue
            usable += 1
            if count % 2 == 1:
                votes += 1
        except Exception:
            continue
    if usable >= 2 and votes >= max(2, (usable // 2) + 1):
        return True
    return bool(normal_inside and votes >= 1)


def _estimate_support_axis_half_span(tree, contact_point, surface_normal, axis_direction, search_distance):
    """Estimación conservadora de cuánto cabe una huella centrada en el contacto.

    Se desplaza ligeramente el origen hacia el interior del soporte y se lanza un
    rayo en ambos sentidos del eje tangente. El menor recorrido de salida fija el
    semieje máximo permitido para que la conexión no sobresalga de la geometría.
    """
    if tree is None:
        return None
    contact = Vector(contact_point)
    normal = _normalized_or_fallback(surface_normal, (0.0, 0.0, 1.0))
    axis = _normalized_or_fallback(axis_direction, (1.0, 0.0, 0.0))
    axis -= normal * axis.dot(normal)
    axis = _normalized_or_fallback(axis, (1.0, 0.0, 0.0))

    max_distance = max(0.50, float(search_distance))
    inside_depth = min(max(0.08, float(REINFORCEMENT_BLEND_SUPPORT_FIT_INSIDE_DEPTH_MM)), max_distance * 0.20)
    safety_margin = min(max(0.05, float(REINFORCEMENT_BLEND_SUPPORT_FIT_MARGIN_MM)), max_distance * 0.35)
    origin = contact - normal * inside_depth

    plus = _bvh_world_ray_distance(tree, origin, axis, max_distance)
    minus = _bvh_world_ray_distance(tree, origin, -axis, max_distance)
    valid = []
    for distance in (plus, minus):
        if distance is None:
            continue
        usable = distance - safety_margin
        if usable > 0.04:
            valid.append(usable)
    if not valid:
        return None
    if len(valid) == 1:
        return max(0.04, valid[0])
    return max(0.04, min(valid))


def _cubic_bezier_point(p0, p1, p2, p3, t):
    t = max(0.0, min(1.0, float(t)))
    omt = 1.0 - t
    return (Vector(p0) * (omt ** 3)
            + Vector(p1) * (3.0 * omt * omt * t)
            + Vector(p2) * (3.0 * omt * t * t)
            + Vector(p3) * (t ** 3))


def _ring_centroid(points):
    if not points:
        return Vector((0.0, 0.0, 0.0))
    centroid = Vector((0.0, 0.0, 0.0))
    for point in points:
        centroid += Vector(point)
    return centroid / float(len(points))


def _smooth_circular_ring(points, weight=0.16, passes=1):
    ring = [Vector(point) for point in points]
    count = len(ring)
    if count < 4:
        return ring
    w = max(0.0, min(0.33, float(weight)))
    iterations = max(0, int(passes))
    for _ in range(iterations):
        current = ring
        updated = []
        for index in range(count):
            prev_pt = current[(index - 1) % count]
            cur_pt = current[index]
            next_pt = current[(index + 1) % count]
            updated.append(cur_pt * (1.0 - 2.0 * w) + prev_pt * w + next_pt * w)
        ring = updated
    return ring


def _equalize_ring_radii(points, centroid, blend_weight=0.5):
    ring = [Vector(point) for point in points]
    if not ring:
        return ring
    weight = max(0.0, min(1.0, float(blend_weight)))
    if weight <= 1.0e-8:
        return ring

    radii = []
    directions = []
    fallback = None
    for point in ring:
        offset = Vector(point) - centroid
        radius = offset.length
        if radius > 1.0e-8:
            direction = offset / radius
            fallback = direction.copy()
        else:
            direction = None
        directions.append(direction)
        radii.append(radius)

    valid = [radius for radius in radii if radius > 1.0e-8]
    if not valid:
        return ring
    mean_radius = sum(valid) / float(len(valid))
    if fallback is None:
        fallback = Vector((1.0, 0.0, 0.0))

    equalized = []
    for point, direction, radius in zip(ring, directions, radii):
        if direction is None:
            direction = fallback.copy()
            radius = mean_radius
        target_radius = radius * (1.0 - weight) + mean_radius * weight
        equalized.append(centroid + direction * target_radius)
    return equalized


def _regularize_and_fullen_ring(points, longitudinal_factor):
    ring = [Vector(point) for point in points]
    if len(ring) < 4:
        return ring

    bell = max(0.0, min(1.0, float(longitudinal_factor)))
    if bell <= 1.0e-8:
        return ring

    smoothed = _smooth_circular_ring(
        ring,
        weight=float(REINFORCEMENT_BLEND_RING_SMOOTH_WEIGHT),
        passes=int(REINFORCEMENT_BLEND_RING_SMOOTH_PASSES),
    )
    centroid = _ring_centroid(smoothed)
    regularized = _equalize_ring_radii(
        smoothed, centroid,
        blend_weight=float(REINFORCEMENT_BLEND_RADIUS_EQUALIZE_WEIGHT) * bell,
    )

    fullness = 1.0 + float(REINFORCEMENT_BLEND_MID_FULLNESS_GAIN) * bell
    result = []
    for point in regularized:
        offset = point - centroid
        if offset.length <= 1.0e-8:
            result.append(Vector(point))
        else:
            result.append(centroid + offset * fullness)
    return result


def _polyline_cumulative_lengths(points):
    pts = [Vector(point) for point in points]
    if not pts:
        return [], []
    cumulative = [0.0]
    for index in range(1, len(pts)):
        cumulative.append(cumulative[-1] + (pts[index] - pts[index - 1]).length)
    return pts, cumulative


def _polyline_point_at_distance(points, cumulative, distance):
    if not points:
        return Vector((0.0, 0.0, 0.0))
    if len(points) == 1 or not cumulative:
        return Vector(points[0])
    target = max(0.0, min(float(distance), float(cumulative[-1])))
    for index in range(1, len(points)):
        if cumulative[index] + 1e-9 < target:
            continue
        span = cumulative[index] - cumulative[index - 1]
        if span < 1e-9:
            return Vector(points[index])
        factor = (target - cumulative[index - 1]) / span
        return Vector(points[index - 1]).lerp(Vector(points[index]), factor)
    return Vector(points[-1])


def _trim_polyline_by_distances(points, start_distance, end_distance):
    """Recorta una polilínea por longitud de arco sin cambiar su trayectoria."""
    pts, cumulative = _polyline_cumulative_lengths(points)
    if len(pts) < 2 or not cumulative or cumulative[-1] < 1e-6:
        return pts

    total = cumulative[-1]
    start = max(0.0, min(float(start_distance), total))
    end = max(start, min(total - max(0.0, float(end_distance)), total))
    if end - start < 0.08:
        midpoint = 0.5 * (start + end)
        start = max(0.0, midpoint - 0.04)
        end = min(total, midpoint + 0.04)

    result = [_polyline_point_at_distance(pts, cumulative, start)]
    for point, distance in zip(pts[1:-1], cumulative[1:-1]):
        if start + 1e-6 < distance < end - 1e-6:
            result.append(Vector(point))
    result.append(_polyline_point_at_distance(pts, cumulative, end))

    cleaned = []
    for point in result:
        if not cleaned or (point - cleaned[-1]).length > 1e-5:
            cleaned.append(Vector(point))
    return cleaned


def _polyline_vertex_tangents(points):
    pts = [Vector(point) for point in points]
    if len(pts) < 2:
        return []
    tangents = []
    for index in range(len(pts)):
        if index == 0:
            tangent = pts[1] - pts[0]
        elif index == len(pts) - 1:
            tangent = pts[-1] - pts[-2]
        else:
            before = pts[index] - pts[index - 1]
            after = pts[index + 1] - pts[index]
            before = _normalized_or_fallback(before, after)
            after = _normalized_or_fallback(after, before)
            tangent = before + after
            if tangent.length < 1e-7:
                tangent = after
        tangents.append(_normalized_or_fallback(tangent, (1.0, 0.0, 0.0)))
    return tangents


def _signed_angle_around_axis(vector_a, vector_b, axis):
    axis = _normalized_or_fallback(axis, (1.0, 0.0, 0.0))
    a = Vector(vector_a) - axis * Vector(vector_a).dot(axis)
    b = Vector(vector_b) - axis * Vector(vector_b).dot(axis)
    a = _normalized_or_fallback(a, (0.0, 1.0, 0.0))
    b = _normalized_or_fallback(b, a)
    return math.atan2(axis.dot(a.cross(b)), max(-1.0, min(1.0, a.dot(b))))


def _preferred_reinforcement_tube_u(surface_normal, outgoing_direction):
    """Eje transversal estable: evita el giro de Frenet cerca de tramos rectos."""
    normal = _normalized_or_fallback(surface_normal, (0.0, 0.0, 1.0))
    tangent = _normalized_or_fallback(outgoing_direction, (1.0, 0.0, 0.0))
    tangent_on_surface = tangent - normal * tangent.dot(normal)
    if tangent_on_surface.length < 1e-7:
        reference = Vector((1.0, 0.0, 0.0))
        if abs(reference.dot(normal)) > 0.88:
            reference = Vector((0.0, 1.0, 0.0))
        tangent_on_surface = reference - normal * reference.dot(normal)
    tangent_on_surface.normalize()
    side = normal.cross(tangent_on_surface)
    side = side - tangent * side.dot(tangent)
    return _normalized_or_fallback(side, (0.0, 1.0, 0.0))


def _create_open_rotation_minimizing_tube(context, name, points, radius,
                                            ring_segments, initial_u,
                                            desired_end_u=None):
    """Tubo abierto barrido por transporte paralelo con corrección de giro final.

    No tiene tapas. Sus aros extremos se reutilizan exactamente por los collars,
    de modo que tras remove_doubles el empalme es topológico, no una intersección
    visual entre un cilindro completo y una transición superpuesta.
    """
    pts = [Vector(point) for point in points]
    if len(pts) < 2:
        return None, None
    tangents = _polyline_vertex_tangents(pts)
    if len(tangents) != len(pts):
        return None, None

    first_tangent = tangents[0]
    u0 = Vector(initial_u) - first_tangent * Vector(initial_u).dot(first_tangent)
    if u0.length < 1e-7:
        reference = Vector((0.0, 0.0, 1.0))
        if abs(reference.dot(first_tangent)) > 0.88:
            reference = Vector((0.0, 1.0, 0.0))
        u0 = reference - first_tangent * reference.dot(first_tangent)
    u0.normalize()

    raw_u = [u0]
    for index in range(1, len(pts)):
        previous_tangent = tangents[index - 1]
        current_tangent = tangents[index]
        transported = raw_u[-1].copy()
        try:
            rotation = previous_tangent.rotation_difference(current_tangent)
            transported = rotation @ transported
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        transported -= current_tangent * transported.dot(current_tangent)
        transported = _normalized_or_fallback(transported, raw_u[-1])
        raw_u.append(transported)

    pts_for_length, cumulative = _polyline_cumulative_lengths(pts)
    total_length = cumulative[-1] if cumulative else 0.0
    end_twist = 0.0
    if desired_end_u is not None:
        desired = Vector(desired_end_u)
        desired -= tangents[-1] * desired.dot(tangents[-1])
        if desired.length > 1e-7:
            desired.normalize()
            end_twist = _signed_angle_around_axis(raw_u[-1], desired, tangents[-1])

    u_axes = []
    v_axes = []
    for index, (tangent, axis_u) in enumerate(zip(tangents, raw_u)):
        fraction = (cumulative[index] / total_length) if total_length > 1e-8 else 0.0
        corrected_u = axis_u.copy()
        if abs(end_twist) > 1e-8:
            try:
                corrected_u = Quaternion(tangent, end_twist * fraction) @ corrected_u
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        corrected_u -= tangent * corrected_u.dot(tangent)
        corrected_u = _normalized_or_fallback(corrected_u, axis_u)
        corrected_v = tangent.cross(corrected_u)
        corrected_v = _normalized_or_fallback(corrected_v, (0.0, 0.0, 1.0))
        u_axes.append(corrected_u)
        v_axes.append(corrected_v)

    segments = max(16, int(ring_segments))
    segments += (-segments) % 4
    tube_radius = max(0.20, float(radius))
    vertices = []
    for center, axis_u, axis_v in zip(pts, u_axes, v_axes):
        for circum_index in range(segments):
            angle = math.tau * circum_index / float(segments)
            vertices.append(tuple(
                center
                + axis_u * (math.cos(angle) * tube_radius)
                + axis_v * (math.sin(angle) * tube_radius)))

    faces = []
    for row_index in range(len(pts) - 1):
        row0 = row_index * segments
        row1 = (row_index + 1) * segments
        for circum_index in range(segments):
            next_index = (circum_index + 1) % segments
            faces.append((
                row0 + circum_index,
                row0 + next_index,
                row1 + next_index,
                row1 + circum_index,
            ))

    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = Matrix.Identity(4)
    link_object(context, obj)
    register_dsg_object(obj, ROLE_REINFORCEMENT, name, {
        'DSG_reinforcement_open_tube': True,
        'DSG_reinforcement_rotation_minimizing_frame': True,
        'DSG_reinforcement_diameter': tube_radius * 2.0,
    })
    frame_data = {
        'points': pts_for_length,
        'tangents': tangents,
        'u_axes': u_axes,
        'v_axes': v_axes,
        'segments': segments,
    }
    return obj, frame_data


def _reinforcement_extended_neck_length(connector_radius, path_length):
    radius = max(0.20, float(connector_radius))
    length = max(0.20, float(path_length))
    target = max(0.72, radius * REINFORCEMENT_BLEND_NECK_RADIUS_SCALE)
    minimum_body = max(
        float(REINFORCEMENT_BLEND_MIN_BODY_MM),
        radius * float(REINFORCEMENT_BLEND_MIN_BODY_RADIUS_SCALE))
    maximum_each = max(0.34, (length - minimum_body) * 0.5)
    return max(0.34, min(target, maximum_each))


def _reinforcement_consistent_endpoint_frames(surface_normal, contact_to_tube,
                                               body_u=None, body_v=None,
                                               ring_segments=48):
    """Construye la misma parametrización geométrica en ambos extremos.

    El error de las versiones anteriores era mezclar dos orientaciones:
    - el cuerpo siempre está parametrizado en A→B;
    - el collar final se recorre desde B hacia el interior, es decir B→A.

    Para un círculo, conservar U y V sin corregir la orientación produce una
    parametrización reflejada en el extremo final. Aquí se crea primero un frame
    dextrógiro respecto a contacto→tubo, se alinea a la fase discreta del aro del
    cuerpo y después se transporta por rotación mínima al plano del soporte.
    """
    normal = _normalized_or_fallback(surface_normal, (0.0, 0.0, 1.0))
    tangent = _normalized_or_fallback(contact_to_tube, (1.0, 0.0, 0.0))
    segments = max(16, int(ring_segments))
    segments += (-segments) % 4

    surface_forward = tangent - normal * tangent.dot(normal)
    if surface_forward.length < 1e-7:
        reference = Vector((1.0, 0.0, 0.0))
        if abs(reference.dot(normal)) > 0.88:
            reference = Vector((0.0, 1.0, 0.0))
        surface_forward = reference - normal * reference.dot(normal)
    surface_forward.normalize()
    surface_side = normal.cross(surface_forward)
    surface_side = _normalized_or_fallback(surface_side, (0.0, 1.0, 0.0))

    try:
        support_to_tube_rotation = normal.rotation_difference(tangent)
        desired_tube_major = support_to_tube_rotation @ surface_forward
        desired_tube_minor = support_to_tube_rotation @ surface_side
    except Exception:
        support_to_tube_rotation = Quaternion()
        desired_tube_major = surface_forward - tangent * surface_forward.dot(tangent)
        desired_tube_major = _normalized_or_fallback(desired_tube_major, surface_side)
        desired_tube_minor = tangent.cross(desired_tube_major)

    desired_tube_major -= tangent * desired_tube_major.dot(tangent)
    desired_tube_major = _normalized_or_fallback(desired_tube_major, surface_side)
    desired_tube_minor = tangent.cross(desired_tube_major)
    desired_tube_minor = _normalized_or_fallback(desired_tube_minor, surface_forward)

    phase_index = 0
    orientation_sign = 1.0
    if body_u is not None and body_v is not None:
        ring_u = Vector(body_u)
        ring_u -= tangent * ring_u.dot(tangent)
        ring_u = _normalized_or_fallback(ring_u, desired_tube_major)

        supplied_v = Vector(body_v)
        supplied_v -= tangent * supplied_v.dot(tangent)
        supplied_v -= ring_u * supplied_v.dot(ring_u)
        supplied_v = _normalized_or_fallback(supplied_v, tangent.cross(ring_u))

        body_axis = ring_u.cross(supplied_v)
        body_axis = _normalized_or_fallback(body_axis, tangent)
        orientation_sign = 1.0 if body_axis.dot(tangent) >= 0.0 else -1.0

        # La V local debe cumplir tangent × U = V. En el extremo final esto
        # equivale a -V_cuerpo; así deja de ser una parametrización reflejada.
        ring_v = tangent.cross(ring_u)
        ring_v = _normalized_or_fallback(ring_v, desired_tube_minor)

        phase_angle = _signed_angle_around_axis(
            ring_u, desired_tube_major, tangent)
        phase_step = math.tau / float(segments)
        phase_index = int(round(phase_angle / phase_step))
        snapped_angle = phase_index * phase_step

        tube_major = (
            ring_u * math.cos(snapped_angle)
            + ring_v * math.sin(snapped_angle))
        tube_major = _normalized_or_fallback(tube_major, desired_tube_major)
        tube_minor = tangent.cross(tube_major)
        tube_minor = _normalized_or_fallback(tube_minor, desired_tube_minor)
    else:
        tube_major = desired_tube_major
        tube_minor = desired_tube_minor

    # Invertir la misma rotación mínima devuelve una elipse del soporte cuya
    # fase corresponde exactamente al aro tubular, sin cruzar generatrices.
    try:
        inverse_rotation = support_to_tube_rotation.inverted()
        support_major = inverse_rotation @ tube_major
    except Exception:
        support_major = surface_forward.copy()
    support_major -= normal * support_major.dot(normal)
    support_major = _normalized_or_fallback(support_major, surface_forward)
    if support_major.dot(surface_forward) < 0.0:
        # Un giro de pi no cambia el conjunto de puntos del aro, pero mantiene
        # la dirección mayor de la huella orientada hacia el interior del tubo.
        support_major.negate()
        tube_major.negate()
        tube_minor.negate()
        phase_index += segments // 2

    support_minor = normal.cross(support_major)
    support_minor = _normalized_or_fallback(support_minor, surface_side)

    return (
        support_major, support_minor,
        tube_major, tube_minor,
        phase_index % segments, orientation_sign,
    )


def _build_reinforcement_coons_blend_object(context, name, contact_point,
                                              surface_normal, tube_direction,
                                              support_obj, connector_radius,
                                              segment_length, surface_tree=None,
                                              tube_center_override=None,
                                              tube_tangent_override=None,
                                              tube_u_override=None,
                                              tube_v_override=None,
                                              support_embed_depth_override=None,
                                              cap_tube=True):
    """Collar Coons-Hermite extendido desde el apoyo hasta el tubo recortado.

    Mantiene la huella y la proyección sobre soporte de v6.12.21. La diferencia
    decisiva es que cada generatriz longitudinal tiene derivadas explícitas:
    sale dentro del plano tangente local del soporte y llega paralela al eje del
    tubo. El cuerpo cilíndrico ya no ocupa esta zona, por lo que no reaparece el
    codo por debajo del collar.
    """
    contact = Vector(contact_point)
    normal = _normalized_or_fallback(surface_normal, (0.0, 0.0, 1.0))
    tangent = _normalized_or_fallback(
        tube_tangent_override if tube_tangent_override is not None else tube_direction,
        (1.0, 0.0, 0.0))
    radius = max(0.20, float(connector_radius))
    length = max(0.80, float(segment_length))

    segments = max(16, int(REINFORCEMENT_BLEND_RING_SEGMENTS))
    segments += (-segments) % 4
    (support_major_axis, support_minor_axis,
     tube_major_axis, tube_minor_axis,
     endpoint_phase_index, endpoint_orientation_sign) = (
        _reinforcement_consistent_endpoint_frames(
            normal,
            tangent,
            body_u=tube_u_override,
            body_v=tube_v_override,
            ring_segments=segments,
        )
    )
    base_forward = support_major_axis.copy()

    normal_alignment = abs(max(-1.0, min(1.0, tangent.dot(normal))))
    incidence = 1.0 - normal_alignment
    volcano_factor = _smootherstep01(
        max(0.0, min(1.0,
            (normal_alignment - float(REINFORCEMENT_BLEND_NORMAL_ENTRY_THRESHOLD))
            / max(1.0e-6, 1.0 - float(REINFORCEMENT_BLEND_NORMAL_ENTRY_THRESHOLD)))))

    # La zona de unión debe ser visual y estructuralmente más ancha que el
    # conector. Se parte del escalado previo, pero se garantiza además un radio
    # base objetivo superior al del tubo y ligeramente mayor aún en entradas
    # tipo volcán.
    target_union_radius = radius * float(REINFORCEMENT_BLEND_UNION_TARGET_RADIUS_RATIO) * (
        1.0 + 0.12 * volcano_factor)
    nominal_foot_minor = max(
        radius * REINFORCEMENT_BLEND_FOOT_SCALE * (
            1.0 + float(REINFORCEMENT_BLEND_NORMAL_ENTRY_FOOT_GAIN) * volcano_factor),
        target_union_radius)
    ellipse_factor = max(
        float(REINFORCEMENT_BLEND_UNION_MAJOR_RATIO),
        1.0 + REINFORCEMENT_BLEND_TANGENTIAL_STRETCH * incidence * (
            1.0 - float(REINFORCEMENT_BLEND_NORMAL_ENTRY_ELLIPSE_DAMP) * volcano_factor))
    nominal_foot_major = nominal_foot_minor * ellipse_factor

    # Conservamos la base volcánica nominal grande. No imponemos un mínimo
    # después de medir el soporte, porque ese mínimo era precisamente lo que
    # hacía reaparecer sectores fuera del frame. El recorte radial por dirección
    # se aplica más abajo sobre adaptive_foot_offsets.
    foot_minor = max(
        radius * float(REINFORCEMENT_BLEND_UNION_MIN_RADIUS_RATIO),
        nominal_foot_minor)
    foot_major = max(
        foot_minor * float(REINFORCEMENT_BLEND_UNION_MAJOR_RATIO),
        nominal_foot_major)
    if support_embed_depth_override is None:
        overlap = max(0.05, float(REINFORCEMENT_BLEND_OVERLAP_MM))
    else:
        overlap = max(
            0.05,
            min(float(REINFORCEMENT_STRUCTURAL_BURIAL_MAX_MM),
                float(support_embed_depth_override)))

    if tube_center_override is not None:
        tube_center = Vector(tube_center_override)
        neck_length = max(0.30, (tube_center - contact).length)
    else:
        neck_length = _reinforcement_extended_neck_length(radius, length)
        tube_center = contact + tangent * neck_length

    v_steps = max(5, int(REINFORCEMENT_BLEND_LONGITUDINAL_STEPS))

    support_ring = []
    support_normals = []
    tube_ring = []
    max_projection = max(1.20, foot_major * 1.35)
    adaptive_foot_offsets = _adaptive_volcano_footprint_offsets(
        surface_tree, contact, normal,
        support_major_axis, support_minor_axis,
        foot_major, foot_minor, segments, volcano_factor, radius)
    for index in range(segments):
        angle = math.tau * index / float(segments)
        ca, sa = math.cos(angle), math.sin(angle)
        # La huella deja de ser una elipse rígida. Cada dirección se limita por
        # el volumen real disponible del soporte y después se suaviza alrededor
        # del perímetro, produciendo una base volcánica variable y orgánica.
        candidate = contact + adaptive_foot_offsets[index]
        projected, projected_normal = _nearest_support_surface_world(
            surface_tree, candidate, normal, max_projection)

        # BVH.find_nearest puede saltar lateralmente hacia otra cara o hacia el
        # borde opuesto de una malla cercana. Conservamos la adaptación normal,
        # pero rechazamos desplazamientos tangenciales capaces de formar alas.
        delta = Vector(projected) - candidate
        normal_delta = normal * delta.dot(normal)
        tangent_delta = delta - normal_delta
        max_tangent = max(
            0.18,
            foot_minor * float(REINFORCEMENT_BLEND_MAX_TANGENTIAL_PROJECTION_SCALE))
        max_normal = max(
            0.30,
            foot_minor * float(REINFORCEMENT_BLEND_MAX_NORMAL_PROJECTION_SCALE))
        if tangent_delta.length > max_tangent:
            tangent_delta = Vector((0.0, 0.0, 0.0))
            projected_normal = normal.copy()
        if normal_delta.length > max_normal:
            normal_delta.normalize()
            normal_delta *= max_normal
        projected = candidate + normal_delta + tangent_delta
        projected = projected - Vector(projected_normal) * overlap
        support_ring.append(Vector(projected))
        support_normals.append(Vector(projected_normal))
        tube_ring.append(
            tube_center
            + tube_major_axis * (ca * radius)
            + tube_minor_axis * (sa * radius))

    # Filtrado circular muy leve: elimina saltos de triángulo sin redondear la
    # huella que hizo útil a v6.12.21. Después se vuelve a proyectar.
    if surface_tree is not None and len(support_ring) >= 8:
        smooth_passes = 1 + int(round(
            volcano_factor * max(0, int(REINFORCEMENT_BLEND_VOLCANO_SUPPORT_RING_SMOOTH_PASSES) - 1)))
        for _smooth_pass in range(max(1, smooth_passes)):
            filtered_ring = []
            filtered_normals = []
            for index in range(segments):
                candidate = (
                    support_ring[(index - 1) % segments] * 0.12
                    + support_ring[index] * 0.76
                    + support_ring[(index + 1) % segments] * 0.12)
                averaged_normal = (
                    support_normals[(index - 1) % segments] * 0.12
                    + support_normals[index] * 0.76
                    + support_normals[(index + 1) % segments] * 0.12)
                averaged_normal = _normalized_or_fallback(averaged_normal, normal)
                filtered_ring.append(Vector(candidate))
                filtered_normals.append(averaged_normal)
            support_ring = filtered_ring
            support_normals = filtered_normals

    rail_data = []
    support_handles = []
    tube_handles = []
    for index in range(segments):
        start = support_ring[index]
        end = tube_ring[index]
        local_normal = _normalized_or_fallback(support_normals[index], normal)
        span_vector = end - start
        span = max(0.20, span_vector.length)

        forward = tangent - local_normal * tangent.dot(local_normal)
        forward = _normalized_or_fallback(forward, base_forward)
        direct = span_vector - local_normal * span_vector.dot(local_normal)
        direct = _normalized_or_fallback(direct, forward)
        if forward.dot(span_vector) < 0.0:
            forward.negate()
        if direct.dot(span_vector) < 0.0:
            direct.negate()

        direct_weight = 0.22 + (
            float(REINFORCEMENT_BLEND_NORMAL_ENTRY_DIRECT_WEIGHT) - 0.22) * volcano_factor
        support_direction = _normalized_or_fallback(
            forward * (1.0 - direct_weight) + direct * direct_weight, direct)

        local_foot_radius = max(0.05, (start - contact).length)
        support_handle = min(
            span * (0.80 + 0.10 * volcano_factor),
            max(radius * 0.72,
                local_foot_radius * (0.48 + 0.18 * volcano_factor),
                neck_length * (0.62 + 0.10 * volcano_factor)))
        support_handle *= float(REINFORCEMENT_BLEND_SUPPORT_HANDLE_SCALE)
        tube_handle = min(
            span * (0.86 - 0.08 * volcano_factor),
            max(radius * 0.72, neck_length * (0.72 - 0.08 * volcano_factor)))
        tube_handle *= float(REINFORCEMENT_BLEND_TUBE_HANDLE_SCALE)

        rail_data.append((start, end, support_direction))
        support_handles.append(support_handle)
        tube_handles.append(tube_handle)

    if volcano_factor > 1.0e-6:
        support_handles = _smooth_circular_scalars(
            support_handles,
            passes=int(REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_PASSES),
            weight=float(REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_WEIGHT))
        tube_handles = _smooth_circular_scalars(
            tube_handles,
            passes=int(REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_PASSES),
            weight=float(REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_WEIGHT))

    rails = []
    for index, (start, end, support_direction) in enumerate(rail_data):
        rails.append((
            start,
            start + support_direction * support_handles[index],
            end - tangent * tube_handles[index],
            end,
        ))

    vertices = []
    for longitudinal_index in range(v_steps + 1):
        v = longitudinal_index / float(v_steps)
        ring = [_cubic_bezier_point(*rail, v) for rail in rails]

        # En lugar de inflar desde el centroide bruto (lo que amplifica picos
        # locales del perímetro), primero regularizamos el aro en dirección
        # circunferencial y luego añadimos el volumen de forma homogénea. Los
        # extremos v=0 y v=1 permanecen exactos.
        if 0 < longitudinal_index < v_steps and ring:
            bell = math.sin(math.pi * v) ** 2
            # En entradas casi perpendiculares evitamos el bulto central y
            # favorecemos un perfil de embudo: base amplia y cierre progresivo.
            bell *= max(0.0, 1.0 - volcano_factor)
            if bell > 1.0e-6:
                ring = _regularize_and_fullen_ring(ring, bell)
            elif volcano_factor > 1.0e-6:
                ring = _smooth_circular_ring(
                    ring,
                    weight=float(REINFORCEMENT_BLEND_RING_SMOOTH_WEIGHT),
                    passes=int(REINFORCEMENT_BLEND_RING_SMOOTH_PASSES))

        vertices.extend(tuple(point) for point in ring)

    faces = []
    for longitudinal_index in range(v_steps):
        row0 = longitudinal_index * segments
        row1 = (longitudinal_index + 1) * segments
        for circum_index in range(segments):
            next_index = (circum_index + 1) % segments
            faces.append((
                row0 + circum_index,
                row0 + next_index,
                row1 + next_index,
                row1 + circum_index,
            ))

    support_center_index = len(vertices)
    support_center = contact - normal * (overlap + 0.14)
    vertices.append(tuple(support_center))
    for circum_index in range(segments):
        next_index = (circum_index + 1) % segments
        faces.append((support_center_index, next_index, circum_index))

    if bool(cap_tube):
        tube_center_index = len(vertices)
        vertices.append(tuple(tube_center))
        last_row = v_steps * segments
        for circum_index in range(segments):
            next_index = (circum_index + 1) % segments
            faces.append((
                tube_center_index,
                last_row + circum_index,
                last_row + next_index))

    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = Matrix.Identity(4)
    link_object(context, obj)
    register_dsg_object(obj, ROLE_REINFORCEMENT, name, {
        'DSG_reinforcement_coons_blend': True,
        'DSG_reinforcement_blend_support': _safe_object_name(support_obj),
        'DSG_reinforcement_blend_radius': radius,
        'DSG_reinforcement_blend_method': 'large_round_volcano_uniformly_fitted_to_frame',
        'DSG_reinforcement_blend_neck_length': neck_length,
        'DSG_reinforcement_support_embed_depth': overlap,
        'DSG_reinforcement_preboolean_overlap': bool(REINFORCEMENT_STRUCTURAL_PREBOOLEAN_OVERLAP),
        'DSG_reinforcement_tube_trimmed': tube_center_override is not None,
        'DSG_reinforcement_mid_fullness_gain': float(REINFORCEMENT_BLEND_MID_FULLNESS_GAIN),
        'DSG_reinforcement_ring_smooth_weight': float(REINFORCEMENT_BLEND_RING_SMOOTH_WEIGHT),
        'DSG_reinforcement_ring_smooth_passes': int(REINFORCEMENT_BLEND_RING_SMOOTH_PASSES),
        'DSG_reinforcement_radius_equalize_weight': float(REINFORCEMENT_BLEND_RADIUS_EQUALIZE_WEIGHT),
        'DSG_reinforcement_no_endpoint_flanges': True,
        'DSG_reinforcement_endpoint_phase_index': int(endpoint_phase_index),
        'DSG_reinforcement_endpoint_orientation_sign': float(endpoint_orientation_sign),
        'DSG_reinforcement_normal_alignment': float(normal_alignment),
        'DSG_reinforcement_volcano_factor': float(volcano_factor),
        'DSG_reinforcement_union_target_radius_ratio': float(REINFORCEMENT_BLEND_UNION_TARGET_RADIUS_RATIO),
        'DSG_reinforcement_union_min_radius_ratio': float(REINFORCEMENT_BLEND_UNION_MIN_RADIUS_RATIO),
        'DSG_reinforcement_edge_clip_enabled': bool(REINFORCEMENT_BLEND_EDGE_CLIP_ENABLED),
        'DSG_reinforcement_edge_clip_safety_scale': float(REINFORCEMENT_BLEND_EDGE_CLIP_SAFETY_SCALE),
        'DSG_reinforcement_round_fit_enabled': bool(REINFORCEMENT_BLEND_ROUND_FIT_ENABLED),
        'DSG_reinforcement_round_fit_safety_scale': float(REINFORCEMENT_BLEND_ROUND_FIT_SAFETY_SCALE),
    })
    clean_boolean_cutter_mesh(obj, merge_dist=0.0001, max_vertices=180000)
    return obj


def _sample_reinforcement_two_point_segment(point_a, normal_a, point_b, normal_b,
                                            start_embed=0.0, end_embed=0.0,
                                            samples_per_segment=16):
    """Genera UN tramo entre dos puntos consecutivos.

    Esta función se usa en el paso 8 para que la cadena ya no sea una spline que
    atraviesa todos los puntos de una sola vez. En su lugar, cada tramo se crea
    por separado: 1→2, 2→3, 3→4... Así, después del primer punto, cada punto
    actúa literalmente como final del tramo anterior y origen del siguiente.
    """
    p0 = Vector(point_a)
    p1 = Vector(point_b)
    n0 = _normalized_or_fallback(normal_a, (0.0, 0.0, 1.0))
    n1 = _normalized_or_fallback(normal_b, (0.0, 0.0, 1.0))
    chord = p1 - p0
    distance = chord.length
    if distance < 1e-5:
        return []

    chord_dir = chord.normalized()
    outward = _reinforcement_outward_direction(chord_dir, n0, n1)
    shoulder = max(0.70, min(distance * 0.20, 3.50))

    controls = []
    start_embed = max(0.0, float(start_embed))
    end_embed = max(0.0, float(end_embed))
    if start_embed > 1e-5:
        controls.append(p0 - n0 * start_embed)
    controls.extend([
        p0,
        p0 + chord_dir * shoulder + outward * 0.0,
        p0.lerp(p1, 0.50),
        p1 - chord_dir * shoulder + outward * 0.0,
        p1,
    ])
    if end_embed > 1e-5:
        controls.append(p1 - n1 * end_embed)

    return [Vector(point) for point in _sample_centripetal_catmull_rom(
        controls, max(5, int(samples_per_segment)))]


def _build_reinforcement_segmented_chain(chain_points, chain_normals, endpoint_embed, samples_per_segment):
    """Crea la cadena completa como suma de tramos consecutivos independientes."""
    pts = [Vector(point) for point in chain_points]
    nrm = [_normalized_or_fallback(normal, (0.0, 0.0, 1.0)) for normal in chain_normals]
    if len(pts) < 2:
        return []

    sampled = []
    segment_count = len(pts) - 1
    for index in range(segment_count):
        start_embed = endpoint_embed if index == 0 else 0.0
        end_embed = endpoint_embed if index == segment_count - 1 else 0.0
        segment = _sample_reinforcement_two_point_segment(
            pts[index], nrm[index], pts[index + 1], nrm[index + 1],
            start_embed=start_embed, end_embed=end_embed,
            samples_per_segment=samples_per_segment,
        )
        if not segment:
            continue
        if sampled and (segment[0] - sampled[-1]).length <= 0.01:
            sampled.extend(segment[1:])
        else:
            sampled.extend(segment)

    cleaned = []
    for point in sampled:
        point = Vector(point)
        if not cleaned or (point - cleaned[-1]).length > 0.01:
            cleaned.append(point)
        else:
            cleaned[-1] = point
    return cleaned


def build_reinforcement_chain_preview(context, props, guide_obj,
                                      points, normals, support_objects=None):
    """Cadena segmentada con cuerpo recortado y collars Coons-Hermite largos.

    Cada tramo conserva la trayectoria centrípeta de v6.12.21, pero se divide en
    tres regiones reales: collar inicial, cuerpo tubular y collar final. El tubo
    no continúa oculto hasta el punto de apoyo y, por tanto, no puede reaparecer
    como un codo debajo de la transición.
    """
    if not _valid_obj(guide_obj):
        return None

    chain_points, chain_normals, chain_supports = _clean_reinforcement_chain(
        points, normals, support_objects)
    if len(chain_points) < 2:
        return None

    user_chain_points = [Vector(point) for point in chain_points]
    user_chain_normals = [Vector(normal) for normal in chain_normals]
    surface_cache = {}
    connector_diameter = max(1.0, float(getattr(props, 'connector_diameter', REINFORCEMENT_DIAMETER_MM)))
    connector_radius = connector_diameter * 0.5
    chain_points, chain_normals, chain_burial_depths = (
        _fixed_reinforcement_anchor_burials(
            context, chain_points, chain_normals, chain_supports,
            connector_radius, surface_cache=surface_cache)
    )

    total_length = sum(
        (chain_points[index] - chain_points[index - 1]).length
        for index in range(1, len(chain_points)))
    if total_length < 2.0:
        return None

    endpoint_embed = float(getattr(props, 'reinforcement_endpoint_embed', 0.35))
    arch_height = 0.0
    samples_per_segment = max(
        12, min(36, int(getattr(props, 'reinforcement_curve_resolution', 16)) + 6))

    safe_remove_by_name(REINFORCEMENT_PREVIEW_NAME)
    safe_remove_by_name(REINFORCEMENT_TUBE_TMP_NAME)
    safe_remove_by_name(REINFORCEMENT_CENTERLINE_TMP_NAME)
    safe_remove_by_prefix(REINFORCEMENT_BLEND_TMP_PREFIX)

    body_objects = []
    blend_objects = []
    combined = None
    try:
        ring_segments = max(16, int(REINFORCEMENT_BLEND_RING_SEGMENTS))
        ring_segments += (-ring_segments) % 4
        body_index = 0
        blend_index = 0

        for segment_index in range(len(chain_points) - 1):
            point_a = Vector(chain_points[segment_index])
            point_b = Vector(chain_points[segment_index + 1])
            normal_a = _normalized_or_fallback(
                chain_normals[segment_index], (0.0, 0.0, 1.0))
            normal_b = _normalized_or_fallback(
                chain_normals[segment_index + 1], normal_a)
            support_a = chain_supports[segment_index]
            support_b = chain_supports[segment_index + 1]

            full_path = _sample_reinforcement_two_point_segment(
                point_a, normal_a, point_b, normal_b,
                start_embed=0.0, end_embed=0.0,
                samples_per_segment=samples_per_segment)
            full_path, cumulative = _polyline_cumulative_lengths(full_path)
            if len(full_path) < 2 or not cumulative or cumulative[-1] < 0.25:
                continue

            path_length = cumulative[-1]
            neck_length = _reinforcement_extended_neck_length(
                connector_radius, path_length)
            body_points = _trim_polyline_by_distances(
                full_path, neck_length, neck_length)
            if len(body_points) < 2 or (body_points[-1] - body_points[0]).length < 0.05:
                continue

            body_tangents = _polyline_vertex_tangents(body_points)
            if len(body_tangents) != len(body_points):
                continue
            start_inward = body_tangents[0]
            body_end_axis = body_tangents[-1]
            end_inward = -body_end_axis
            start_u = _preferred_reinforcement_tube_u(normal_a, start_inward)
            # El cuerpo mantiene su RMF en A→B. El collar final, sin embargo,
            # siempre se parametriza desde el apoyo hacia el interior del tubo.
            end_u = _preferred_reinforcement_tube_u(normal_b, body_end_axis)

            body, frame_data = _create_open_rotation_minimizing_tube(
                context,
                f'{REINFORCEMENT_TUBE_TMP_NAME}_{body_index:03d}',
                body_points,
                connector_radius,
                ring_segments,
                start_u,
                desired_end_u=end_u,
            )
            if not _valid_obj(body) or not frame_data:
                if _valid_obj(body):
                    safe_remove_object(body)
                continue
            body_objects.append(body)
            body_index += 1

            burial_a = (
                float(chain_burial_depths[segment_index])
                if segment_index < len(chain_burial_depths)
                else float(REINFORCEMENT_BLEND_OVERLAP_MM))
            burial_b = (
                float(chain_burial_depths[segment_index + 1])
                if segment_index + 1 < len(chain_burial_depths)
                else float(REINFORCEMENT_BLEND_OVERLAP_MM))
            endpoint_specs = (
                (
                    point_a, normal_a, start_inward, support_a,
                    body_points[0], frame_data['u_axes'][0], frame_data['v_axes'][0],
                    burial_a,
                ),
                (
                    point_b, normal_b, end_inward, support_b,
                    body_points[-1], frame_data['u_axes'][-1], frame_data['v_axes'][-1],
                    burial_b,
                ),
            )

            for (contact, support_normal, outgoing, support_obj,
                 tube_center, tube_u, tube_v, support_embed_depth) in endpoint_specs:
                if not _valid_obj(support_obj):
                    continue
                cache_key = _safe_object_name(support_obj)
                if cache_key not in surface_cache:
                    surface_cache[cache_key] = _build_world_surface_bvh(
                        context, support_obj)
                blend = _build_reinforcement_coons_blend_object(
                    context,
                    f'{REINFORCEMENT_BLEND_TMP_PREFIX}{blend_index:03d}',
                    contact,
                    support_normal,
                    outgoing,
                    support_obj,
                    connector_radius,
                    path_length,
                    surface_tree=surface_cache[cache_key],
                    tube_center_override=tube_center,
                    tube_tangent_override=outgoing,
                    tube_u_override=tube_u,
                    tube_v_override=tube_v,
                    support_embed_depth_override=support_embed_depth,
                    cap_tube=False,
                )
                if _valid_obj(blend):
                    blend_objects.append(blend)
                    blend_index += 1

        parts = body_objects + blend_objects
        if not parts:
            return None
        combined = build_combined_mesh_object_world(
            context, parts, REINFORCEMENT_PREVIEW_NAME)
        if not _valid_obj(combined):
            raise RuntimeError(
                'No se pudo construir la previsualización Coons tangente extendida')

        # Los aros del cuerpo y del collar son geométricamente idénticos. Esta
        # soldadura microscópica crea una única piel sin remesh ni voxelización.
        clean_boolean_cutter_mesh(
            combined, merge_dist=0.00035, max_vertices=700000)
        for polygon in combined.data.polygons:
            polygon.use_smooth = True
        combined.data.update(calc_edges=True)

        support_names = [
            _safe_object_name(obj) if _valid_obj(obj) else ''
            for obj in chain_supports
        ]
        points_json = json.dumps([
            [float(v.x), float(v.y), float(v.z)] for v in chain_points])
        normals_json = json.dumps([
            [float(v.x), float(v.y), float(v.z)] for v in chain_normals])
        user_points_json = json.dumps([
            [float(v.x), float(v.y), float(v.z)] for v in user_chain_points])
        user_normals_json = json.dumps([
            [float(v.x), float(v.y), float(v.z)] for v in user_chain_normals])
        supports_json = json.dumps(support_names)
        smart_anchor_displacements = [
            (Vector(optimized) - Vector(user)).length
            for optimized, user in zip(chain_points, user_chain_points)]
        register_dsg_object(combined, ROLE_REINFORCEMENT, REINFORCEMENT_PREVIEW_NAME, {
            'DSG_reinforcement_preview': True,
            'DSG_reinforcement_confirmed': False,
            'DSG_reinforcement_diameter': connector_diameter,
            'DSG_reinforcement_point_count': len(chain_points),
            'DSG_reinforcement_points_json': points_json,
            'DSG_reinforcement_normals_json': normals_json,
            'DSG_reinforcement_user_points_json': user_points_json,
            'DSG_reinforcement_user_normals_json': user_normals_json,
            'DSG_reinforcement_supports_json': supports_json,
            'DSG_reinforcement_smart_anchors': False,
            'DSG_reinforcement_anchor_positions_fixed': True,
            'DSG_reinforcement_structural_weakness_search': bool(REINFORCEMENT_STRUCTURAL_WEAKNESS_ENABLED),
            'DSG_reinforcement_preboolean_structural_overlap': bool(REINFORCEMENT_STRUCTURAL_PREBOOLEAN_OVERLAP),
            'DSG_reinforcement_burial_depths_json': json.dumps([float(value) for value in chain_burial_depths]),
            'DSG_reinforcement_max_burial_depth': max(chain_burial_depths) if chain_burial_depths else 0.0,
            'DSG_reinforcement_min_burial_depth': min(chain_burial_depths) if chain_burial_depths else 0.0,
            'DSG_reinforcement_smart_anchor_max_displacement': max(smart_anchor_displacements) if smart_anchor_displacements else 0.0,
            'DSG_reinforcement_smart_anchor_mean_displacement': (sum(smart_anchor_displacements) / float(len(smart_anchor_displacements))) if smart_anchor_displacements else 0.0,
            'DSG_reinforcement_spline': 'open_segmented_two_point_chain',
            'DSG_reinforcement_blend': 'extended_tangent_coons_hermite',
            'DSG_reinforcement_blend_count': len(blend_objects),
            'DSG_reinforcement_body_count': len(body_objects),
            'DSG_reinforcement_arch_height': arch_height,
            'DSG_reinforcement_tube_trimmed_at_blends': True,
            'DSG_reinforcement_rotation_minimizing_frame': True,
            'DSG_reinforcement_preview_remesh': False,
        })
        combined.show_in_front = True
        combined.display_type = 'SOLID'
        props.reinforcement_preview_obj = combined
        set_active(context, combined)
        return combined
    except Exception as exc:
        print(f'[DSG] Extended tangent Coons preview failed: {exc}')
        if _valid_obj(combined):
            safe_remove_object(combined)
        return None
    finally:
        for body in body_objects:
            if _valid_obj(body):
                safe_remove_object(body)
        for blend in blend_objects:
            if _valid_obj(blend):
                safe_remove_object(blend)


def build_reinforcement_bezier_preview(context, props, guide_obj,
                                        point_a, normal_a, point_b, normal_b):
    """Compatibilidad con llamadas antiguas: crea una cadena simple de dos puntos."""
    return build_reinforcement_chain_preview(
        context, props, guide_obj,
        [point_a, point_b], [normal_a, normal_b], [guide_obj, guide_obj])


def reinforcement_curve_to_mesh(context, curve_obj, name):
    """Devuelve una copia MESH tanto si el refuerzo fuente es CURVE como MESH."""
    if not _valid_obj(curve_obj) or curve_obj.type not in {'CURVE', 'MESH'}:
        return None

    if curve_obj.type == 'MESH':
        try:
            mesh = curve_obj.data.copy()
            obj = bpy.data.objects.new(name, mesh)
            obj.matrix_world = curve_obj.matrix_world.copy()
            link_object(context, obj)
        except Exception as exc:
            print(f'[DSG] Reinforcement mesh duplication failed: {exc}')
            return None
    else:
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = curve_obj.evaluated_get(depsgraph)
        mesh = None
        try:
            mesh = bpy.data.meshes.new_from_object(
                evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
        except TypeError:
            try:
                mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
            except TypeError:
                mesh = bpy.data.meshes.new_from_object(evaluated)
        except Exception as exc:
            print(f'[DSG] Reinforcement mesh conversion failed: {exc}')
            return None
        if mesh is None or len(mesh.vertices) == 0:
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            return None
        obj = bpy.data.objects.new(name, mesh)
        obj.matrix_world = curve_obj.matrix_world.copy()
        link_object(context, obj)

    # The preview stores the exact clinical diameter as object metadata.
    # During final conversion this helper has no local ``connector_diameter``
    # variable, so recover it from the source object and fall back to the
    # current scene setting for legacy files.
    scene_props = getattr(getattr(context, 'scene', None), 'dsg_props', None)
    fallback_diameter = float(
        getattr(scene_props, 'connector_diameter', REINFORCEMENT_DIAMETER_MM)
    ) if scene_props is not None else float(REINFORCEMENT_DIAMETER_MM)
    resolved_connector_diameter = max(
        1.0,
        float(curve_obj.get('DSG_reinforcement_diameter', fallback_diameter)),
    )

    register_dsg_object(obj, ROLE_REINFORCEMENT, name, {
        'DSG_reinforcement_mesh_temp': True,
        'DSG_reinforcement_diameter': resolved_connector_diameter,
        'DSG_reinforcement_contains_coons_blends': bool(
            curve_obj.get('DSG_reinforcement_blend', '') in {
                'four_boundary_coons_patch', 'extended_tangent_coons_hermite'}),
    })
    clean_boolean_cutter_mesh(obj, merge_dist=0.0001, max_vertices=500000)
    return obj



class DSG_OT_CreateAnimatedDrills(Operator):
    bl_idname = 'dsg.create_animated_drills'
    bl_label = 'Create Animated Drills'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        implants = get_all_implant_objects(props)
        if not implants:
            _dsg_report(self, {'ERROR'}, 'No implants were found for drill placement', 'No se encontraron implantes para colocar la fresa')
            return {'CANCELLED'}

        remove_animated_drills()
        created = []
        try:
            base_start = int(props.drill_animation_start_frame)
            duration = max(1, int(props.drill_animation_end_frame) - base_start)
            item_gap = ANIMATION_ITEM_STAGGER_FRAMES_FIXED
            item_stride = duration + item_gap
            for index, implant in enumerate(implants):
                item_start = base_start + index * item_stride
                item_end = item_start + duration
                obj = build_animated_drill_for_implant(
                    context, props, implant, index,
                    start_frame_override=item_start,
                    end_frame_override=item_end)
                if not _valid_obj(obj):
                    raise RuntimeError(
                        f'Could not create the drill for implant {index + 1}')
                created.append(obj)

            start_frame = base_start
            active_end_frame = (base_start + len(implants) * duration
                                + max(0, len(implants) - 1) * item_gap)
            active_motion_frames = max(1, len(implants) * duration)
            reveal_frame = active_end_frame + 1
            final_end_frame = active_end_frame + active_motion_frames
            animate_implants_hidden_until(implants, start_frame, reveal_frame)
            context.scene['DSG_sequence_start_frame'] = int(start_frame)
            context.scene['DSG_sequence_active_end_frame'] = int(active_end_frame)
            context.scene['DSG_sequence_implant_reveal_frame'] = int(reveal_frame)
            context.scene['DSG_sequence_final_hold_frames'] = int(active_motion_frames)
            context.scene['DSG_sequence_end_frame'] = int(final_end_frame)
            context.scene.frame_start = start_frame
            context.scene.frame_end = final_end_frame
            context.scene.frame_set(start_frame)
            if created:
                set_active(context, created[0])
            _dsg_report(self, {'INFO'}, f'{len(created)} drill(s) created. The implants appear together at frame {reveal_frame} and remain visible for {active_motion_frames} stationary frames, until frame {final_end_frame}.', f'{len(created)} fresa(s) creada(s). Los implantes aparecen juntos en el fotograma {reveal_frame} y permanecen visibles durante {active_motion_frames} fotogramas sin movimiento, hasta el fotograma {final_end_frame}.')
            return {'FINISHED'}
        except Exception as exc:
            remove_animated_drills()
            _dsg_report(self, {'ERROR'}, f'Could not prepare the animation: {exc}', f'No se pudo preparar la animación: {exc}')
            return {'CANCELLED'}


class DSG_OT_PlayAnimatedDrills(Operator):
    bl_idname = 'dsg.play_animated_drills'
    bl_label = 'Play Drill Insertion'

    def execute(self, context):
        props = context.scene.dsg_props
        drills = get_animated_drill_objects()
        if not drills:
            _dsg_report(self, {'WARNING'}, 'Create the animated drill first', 'Primero crea la fresa animada')
            return {'CANCELLED'}
        for drill in drills:
            drill.hide_viewport = False
            drill.hide_set(False)
        start_frame = int(props.drill_animation_start_frame)
        end_frame = max(start_frame + 1, int(props.drill_animation_end_frame))
        context.scene.frame_start = start_frame
        context.scene.frame_end = end_frame
        context.scene.frame_set(start_frame)
        try:
            bpy.ops.screen.animation_play()
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not play the animation: {exc}', f'No se pudo reproducir la animación: {exc}')
            return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_StopAnimatedDrills(Operator):
    bl_idname = 'dsg.stop_animated_drills'
    bl_label = 'Stop Drill Animation'

    def execute(self, context):
        props = context.scene.dsg_props
        drills = get_animated_drill_objects()
        if not drills:
            _dsg_report(self, {'WARNING'}, 'Create the animated drill first', 'Primero crea la fresa animada')
            return {'CANCELLED'}
        try:
            if context.screen and context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
        except Exception:
            try:
                bpy.ops.screen.animation_cancel()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.scene.frame_set(int(props.drill_animation_start_frame))
        _dsg_report(self, {'INFO'}, 'Animation stopped and drill returned to the start position', 'Animación detenida y fresa devuelta a la posición inicial')
        return {'FINISHED'}


class DSG_OT_ToggleAnimatedDrillsVisibility(Operator):
    bl_idname = 'dsg.toggle_animated_drills_visibility'
    bl_label = 'Show or Hide Animated Drills'

    def execute(self, context):
        drills = get_animated_drill_objects()
        if not drills:
            _dsg_report(self, {'WARNING'}, 'Create the animated drill first', 'Primero crea la fresa animada')
            return {'CANCELLED'}

        any_visible = any(not _object_is_hidden(obj) for obj in drills)
        hide = bool(any_visible)
        if hide:
            try:
                if context.screen and context.screen.is_animation_playing:
                    bpy.ops.screen.animation_cancel(restore_frame=False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        for obj in drills:
            obj.hide_viewport = hide
            obj.hide_select = hide
            try:
                obj.hide_set(hide)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        _dsg_report(self, {'INFO'}, 'Drills hidden' if hide else 'Drills shown', 'Fresas ocultadas' if hide else 'Fresas mostradas')
        return {'FINISHED'}


class DSG_OT_ShowAnimatedDrillStart(Operator):
    bl_idname = 'dsg.show_animated_drill_start'
    bl_label = 'Show Start Position'

    def execute(self, context):
        props = context.scene.dsg_props
        if not get_animated_drill_objects():
            _dsg_report(self, {'WARNING'}, 'Create the animated drill first', 'Primero crea la fresa animada')
            return {'CANCELLED'}
        context.scene.frame_set(int(props.drill_animation_start_frame))
        return {'FINISHED'}


class DSG_OT_ShowAnimatedDrillStop(Operator):
    bl_idname = 'dsg.show_animated_drill_stop'
    bl_label = 'Show Maximum Insertion'

    def execute(self, context):
        props = context.scene.dsg_props
        drills = get_animated_drill_objects()
        if not drills:
            _dsg_report(self, {'WARNING'}, 'Create the animated drill first', 'Primero crea la fresa animada')
            return {'CANCELLED'}
        contact_frame = drills[0].get('DSG_animation_contact_frame')
        if contact_frame is None:
            start_frame = int(props.drill_animation_start_frame)
            end_frame = max(start_frame + 1, int(props.drill_animation_end_frame))
            contact_frame = start_frame + max(1, int(math.ceil((end_frame - start_frame) * 0.5)))
        context.scene.frame_set(int(contact_frame))
        return {'FINISHED'}



def _microscrew_records_for_animation(props):
    """Use live confirmed geometry when available; JSON is the post-fusion fallback."""
    confirmed = get_confirmed_microscrew_objects()
    if confirmed:
        records = []
        for index, obj in enumerate(confirmed):
            record = _record_from_microscrew_object(obj, index=index)
            if record is not None:
                records.append(record)
        if records:
            set_microscrew_records(props, records)
            return records
    return get_microscrew_records(props)


def configure_sequential_insertion_frames(props, screw_count=0, drill_count=0, extraction_count=0):
    """Orders extraction first (immediate route), then guide seating, screws,
    alternating drill/implant pairs, screw removal, and guide retraction/hide."""
    screw_count = max(0, int(screw_count))
    drill_count = max(0, int(drill_count))
    extraction_count = max(0, int(extraction_count))
    screw_duration = max(
        1,
        int(props.microscrew_animation_end_frame)
        - int(props.microscrew_animation_start_frame))
    drill_duration = max(
        1,
        int(props.drill_animation_end_frame)
        - int(props.drill_animation_start_frame))
    implant_duration = max(12, int(ANIMATION_IMPLANT_DURATION_FRAMES_FIXED))
    guide_seat_duration = max(8, int(ANIMATION_GUIDE_SEATING_DURATION_FRAMES_FIXED))
    guide_return_duration = max(8, int(ANIMATION_GUIDE_RETURN_DURATION_FRAMES_FIXED))
    group_gap = ANIMATION_SEQUENCE_GAP_FRAMES_FIXED
    item_gap = ANIMATION_ITEM_STAGGER_FRAMES_FIXED
    sequence_start = max(1, int(props.microscrew_animation_start_frame))

    extraction_duration = max(10, int(ANIMATION_EXTRACTION_DURATION_FRAMES_FIXED))
    extraction_stride = extraction_duration + int(ANIMATION_EXTRACTION_STRIDE_GAP_FRAMES_FIXED)
    extraction_start = sequence_start if extraction_count else 0
    if extraction_count:
        extraction_end = (
            extraction_start
            + extraction_count * extraction_duration
            + max(0, extraction_count - 1) * int(ANIMATION_EXTRACTION_STRIDE_GAP_FRAMES_FIXED)
        )
        guide_seat_start = extraction_end + 1 + group_gap
    else:
        extraction_end = sequence_start - 1
        guide_seat_start = sequence_start
    guide_seat_end = guide_seat_start + guide_seat_duration

    # Do not start the microscrews until the guide is fully seated.
    surgery_start = guide_seat_end + 1 + group_gap
    screw_start = surgery_start
    screw_stride = screw_duration + item_gap
    if screw_count:
        screw_end = (screw_start
                     + screw_count * screw_duration
                     + max(0, screw_count - 1) * item_gap)
    else:
        screw_end = surgery_start

    drill_start = (screw_end + group_gap) if screw_count else surgery_start
    pair_stride = drill_duration + 1 + implant_duration + item_gap
    if drill_count:
        final_pair_start = drill_start + (drill_count - 1) * pair_stride
        drill_end = final_pair_start + drill_duration
        implant_start = final_pair_start + drill_duration + 1
        implant_end = implant_start + implant_duration
        active_end = implant_end
    else:
        drill_end = screw_end
        implant_start = screw_end
        implant_end = screw_end
        active_end = screw_end

    active_motion_frames = max(
        1,
        guide_seat_duration
        + screw_count * screw_duration
        + drill_count * (drill_duration + implant_duration))

    unscrew_start = active_end + group_gap if screw_count else active_end + group_gap
    unscrew_stride = screw_duration + item_gap
    if screw_count:
        unscrew_end = (
            unscrew_start
            + screw_count * screw_duration
            + max(0, screw_count - 1) * item_gap)
    else:
        unscrew_end = active_end

    # The guide must remain fully seated until the screws have finished
    # unscrewing and disappeared from view (their visibility switches on
    # unscrew_end + 1).
    guide_return_start = unscrew_end + 1 + group_gap
    guide_return_end = guide_return_start + guide_return_duration
    guide_hide_frame = guide_return_end + 1
    final_hold_frames = max(1, int(ANIMATION_FINAL_GUIDE_HOLD_FRAMES_FIXED))
    sequence_end = guide_hide_frame + final_hold_frames

    if screw_count:
        props.microscrew_animation_start_frame = screw_start
        props.microscrew_animation_end_frame = screw_start + screw_duration
    if drill_count:
        props.drill_animation_start_frame = drill_start
        props.drill_animation_end_frame = drill_start + drill_duration

    return {
        'sequence_start': extraction_start if extraction_count else guide_seat_start,
        'extraction_start': extraction_start,
        'extraction_end': extraction_end,
        'extraction_duration': extraction_duration,
        'extraction_stride': extraction_stride,
        'guide_seat_start': guide_seat_start,
        'guide_seat_end': guide_seat_end,
        'surgery_start': surgery_start,
        'screw_start': screw_start,
        'screw_end': screw_end,
        'screw_duration': screw_duration,
        'screw_stride': screw_stride,
        'drill_start': drill_start,
        'drill_end': drill_end,
        'drill_duration': drill_duration,
        'drill_stride': pair_stride,
        'pair_stride': pair_stride,
        'implant_duration': implant_duration,
        'implant_start': implant_start,
        'implant_end': implant_end,
        'active_end': active_end,
        'active_motion_frames': active_motion_frames,
        'implant_reveal_frame': implant_start,
        'unscrew_start': unscrew_start,
        'unscrew_end': unscrew_end,
        'unscrew_duration': screw_duration,
        'unscrew_stride': unscrew_stride,
        'guide_return_start': guide_return_start,
        'guide_return_end': guide_return_end,
        'guide_hide_frame': guide_hide_frame,
        'final_hold_frames': final_hold_frames,
        'sequence_end': sequence_end,
        'gap': group_gap,
        'item_gap': item_gap,
    }


def get_sequential_insertion_bounds(props):
    objects = (get_animated_extraction_tooth_objects()
               + get_animated_microscrew_objects() + get_animated_drill_objects()
               + get_animated_implant_objects())
    stored_start = int(bpy.context.scene.get('DSG_sequence_start_frame', 1))
    stored_end = int(bpy.context.scene.get('DSG_sequence_end_frame', 0))
    if objects:
        starts = [int(obj.get('DSG_animation_start_frame', stored_start)) for obj in objects]
        ends = [int(obj.get('DSG_animation_end_frame', 2)) for obj in objects]
        start = min(min(starts), stored_start)
        active_end = max(ends)
        end = max(active_end, stored_end)
        return max(1, start), max(start + 1, end)
    start = min(
        stored_start,
        int(props.microscrew_animation_start_frame),
        int(props.drill_animation_start_frame))
    end = max(
        int(props.microscrew_animation_end_frame),
        int(props.drill_animation_end_frame),
        stored_end)
    return max(1, start), max(start + 1, end)


class DSG_OT_CreateSequentialInsertionAnimation(Operator):
    bl_idname = 'dsg.create_sequential_insertion_animation'
    bl_label = 'Create Screw, Drill and Implant Sequence'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        records = _microscrew_records_for_animation(props)
        implants = get_all_implant_objects(props)
        guide = get_active_guide_obj(props)
        clear_final_guide_visibility_animation(guide)
        has_screws = bool(records)
        has_drills = bool(implants)
        if not has_screws and not has_drills:
            _dsg_report(self, {'ERROR'}, 'No microscrews or implants are registered', 'No hay microtornillos ni implantes registrados')
            return {'CANCELLED'}

        extraction_sources = _immediate_extraction_animation_sources(context.scene)
        timeline = configure_sequential_insertion_frames(
            props, screw_count=len(records), drill_count=len(implants),
            extraction_count=len(extraction_sources))
        clear_animated_extraction_teeth()
        remove_animated_microscrews(restore_static=True)
        remove_animated_drills()
        for implant in implants:
            clear_implant_insertion_animation(implant, restore_final=True)
            _store_implant_final_transform(implant)
        extraction_created = []
        screws_created = []
        drills_created = []
        implants_animated = []
        try:
            if extraction_sources:
                for index, tooth_obj in enumerate(extraction_sources):
                    item_start = timeline['extraction_start'] + index * timeline['extraction_stride']
                    item_end = item_start + timeline['extraction_duration']
                    obj = build_animated_extraction_tooth(
                        context, tooth_obj, index,
                        start_frame_override=item_start,
                        end_frame_override=item_end)
                    if not _valid_obj(obj):
                        raise RuntimeError(
                            f'Could not animate the extracted tooth {index + 1}')
                    extraction_created.append(obj)

            if has_screws:
                for index, record in enumerate(records):
                    record['index'] = index
                    item_start = timeline['screw_start'] + index * timeline['screw_stride']
                    item_end = item_start + timeline['screw_duration']
                    obj = build_animated_microscrew(
                        context, props, record, index,
                        start_frame_override=item_start,
                        end_frame_override=item_end)
                    if not _valid_obj(obj):
                        raise RuntimeError(
                            f'Could not create screw {index + 1}')
                    screws_created.append(obj)
                set_microscrew_records(props, records)
                set_static_microscrew_visuals_hidden(True)

            if has_drills:
                for index, implant in enumerate(implants):
                    drill_start = timeline['drill_start'] + index * timeline['pair_stride']
                    drill_end = drill_start + timeline['drill_duration']
                    obj = build_animated_drill_for_implant(
                        context, props, implant, index,
                        start_frame_override=drill_start,
                        end_frame_override=drill_end)
                    if not _valid_obj(obj):
                        raise RuntimeError(
                            f'Could not create the drill for implant {index + 1}')
                    drills_created.append(obj)

                    implant_start = drill_end + 1
                    implant_end = implant_start + timeline['implant_duration']
                    if not animate_implant_screw_in_after_drill(
                            props, implant, timeline['sequence_start'],
                            implant_start, implant_end):
                        raise RuntimeError(
                            f'Could not animate implant {index + 1}')
                    implants_animated.append(implant)

            if has_screws:
                for reverse_index, screw_obj in enumerate(reversed(screws_created)):
                    record_index = len(records) - 1 - reverse_index
                    unscrew_start = (
                        timeline['unscrew_start']
                        + reverse_index * timeline['unscrew_stride'])
                    unscrew_end = unscrew_start + timeline['unscrew_duration']
                    if not append_microscrew_unscrew_animation(
                            screw_obj, props, records[record_index],
                            unscrew_start, unscrew_end):
                        raise RuntimeError(
                            f'Could not animate screw removal {record_index + 1}')

            animate_guide_seating_and_return(
                guide,
                timeline['guide_seat_start'], timeline['guide_seat_end'],
                timeline['guide_return_start'], timeline['guide_return_end'],
                timeline['guide_hide_frame'])

            context.scene['DSG_sequence_start_frame'] = int(timeline['sequence_start'])
            context.scene['DSG_sequence_extraction_start_frame'] = int(timeline.get('extraction_start', 0) or 0)
            context.scene['DSG_sequence_extraction_end_frame'] = int(timeline.get('extraction_end', 0) or 0)
            context.scene['DSG_sequence_active_end_frame'] = int(timeline['active_end'])
            context.scene['DSG_sequence_implant_reveal_frame'] = int(timeline['implant_reveal_frame'])
            context.scene['DSG_sequence_implant_duration_frames'] = int(timeline['implant_duration'])
            context.scene['DSG_sequence_guide_seat_start_frame'] = int(timeline['guide_seat_start'])
            context.scene['DSG_sequence_guide_seat_end_frame'] = int(timeline['guide_seat_end'])
            context.scene['DSG_sequence_unscrew_start_frame'] = int(timeline['unscrew_start'])
            context.scene['DSG_sequence_unscrew_end_frame'] = int(timeline['unscrew_end'])
            context.scene['DSG_sequence_guide_return_start_frame'] = int(timeline['guide_return_start'])
            context.scene['DSG_sequence_guide_return_end_frame'] = int(timeline['guide_return_end'])
            context.scene['DSG_sequence_guide_hide_frame'] = int(timeline['guide_hide_frame'])
            context.scene['DSG_sequence_final_hold_frames'] = int(timeline['final_hold_frames'])
            context.scene['DSG_sequence_end_frame'] = int(timeline['sequence_end'])
            context.scene.frame_start = int(timeline['sequence_start'])
            context.scene.frame_end = int(timeline['sequence_end'])
            # Leave the viewport at the keyed seated frame. Play still restarts
            # from sequence_start, but Create/Update never leave the guide apart.
            context.scene.frame_set(int(timeline['guide_seat_end']))
            restore_guide_home_transform(guide, scene=context.scene, make_visible=True)
            active = screws_created[0] if screws_created else drills_created[0]
            set_active(context, active)

            extraction_intro = (
                f' La secuencia se abre con {len(extraction_created)} diente(s) extraído(s) que salen '
                'siguiendo un eje coronario de extracción y luego desaparecen antes del protocolo estándar.'
                if extraction_created else '')
            if has_screws and has_drills:
                message = (
                    f'Secuencia creada: {len(screws_created)} tornillo(s); '
                    f'{len(drills_created)} pareja(s) fresa–implante.'
                    + extraction_intro + ' '
                    'Después de regresar cada fresa, su implante aparece justo encima '
                    f'del sleeve y se enrosca durante {timeline["implant_duration"]} frames. '
                    'La férula primero entra siguiendo la dirección correcta del eje de inserción y se asienta por completo sobre el modelo antes de empezar los tornillos. '
                    'Después del último implante, los tornillos se desatornillan '
                    'en orden inverso; solo cuando terminan de salir, la férula se retira devolviéndose por el mismo eje y luego se oculta automáticamente. '
                    f'Pausa entre parejas: {timeline["item_gap"]} frames.')
            elif has_screws:
                message = (
                    (f'{len(extraction_created)} extracción(es) animada(s) al inicio; ' if extraction_created else '')
                    + f'{len(screws_created)} tornillo(s) animado(s); la férula se asienta al inicio y se retira al final. '
                    'No se encontraron implantes para crear fresas.')
            else:
                message = (
                    (f'{len(extraction_created)} extracción(es) animada(s) al inicio; ' if extraction_created else '')
                    + f'{len(drills_created)} pareja(s) fresa–implante animada(s); la férula se asienta al inicio y se retira al final. '
                    'No se encontraron sleeves de microtornillo.')
            _dsg_report(self, {'INFO'}, message, message)
            return {'FINISHED'}
        except Exception as exc:
            clear_animated_extraction_teeth()
            remove_animated_microscrews(restore_static=True)
            remove_animated_drills()
            for implant in implants:
                clear_implant_insertion_animation(implant, restore_final=True)
            clear_final_guide_visibility_animation(guide)
            _dsg_report(self, {'ERROR'}, f'Could not create the sequence: {exc}', f'No se pudo crear la secuencia: {exc}')
            return {'CANCELLED'}


class DSG_OT_UpdateFinalAnimation(Operator):
    bl_idname = 'dsg.update_final_animation'
    bl_label = 'Update Final Animation'
    bl_description = (
        'Rebuilds the complete screw, drill and implant sequence and then '
        'recreates the synchronized solid water flow automatically')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        guide = get_active_guide_obj(context.scene.dsg_props)
        restore_guide_home_transform(guide, scene=context.scene, make_visible=True)
        try:
            try:
                sequence_result = bpy.ops.dsg.create_sequential_insertion_animation('EXEC_DEFAULT')
            except Exception as exc:
                _dsg_report(
                    self, {'ERROR'},
                    f'Could not update the final animation sequence: {exc}',
                    f'No se pudo actualizar la secuencia de animación final: {exc}')
                return {'CANCELLED'}

            if 'FINISHED' not in sequence_result:
                _dsg_report(
                    self, {'ERROR'},
                    'The final animation sequence could not be created',
                    'No se pudo crear la secuencia de animación final')
                return {'CANCELLED'}

            try:
                water_result = bpy.ops.dsg.simulate_irrigation_flow('EXEC_DEFAULT')
            except Exception as exc:
                _dsg_report(
                    self, {'WARNING'},
                    f'The animation was updated, but the water flow could not be recreated: {exc}',
                    f'La animación se actualizó, pero no se pudo recrear el flujo de agua: {exc}')
                return {'FINISHED'}

            if 'FINISHED' not in water_result:
                _dsg_report(
                    self, {'WARNING'},
                    'The animation was updated, but the water flow was not created',
                    'La animación se actualizó, pero no se creó el flujo de agua')
                return {'FINISHED'}

            _dsg_report(
                self, {'INFO'},
                'Final animation and solid water flow updated',
                'Animación final y flujo de agua en Solid actualizados')
            return {'FINISHED'}
        finally:
            # Update is never allowed to leave the guide displaced or hidden.
            try:
                seated_frame = int(context.scene.get(
                    'DSG_sequence_guide_seat_end_frame', context.scene.frame_current))
                context.scene.frame_set(seated_frame)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            restore_guide_home_transform(
                guide, scene=context.scene, make_visible=True)


class DSG_OT_PlaySequentialInsertionAnimation(Operator):
    bl_idname = 'dsg.play_sequential_insertion_animation'
    bl_label = 'Play Screw, Drill and Implant Sequence'

    def execute(self, context):
        props = context.scene.dsg_props
        objects = (get_animated_microscrew_objects() + get_animated_drill_objects()
                   + get_animated_implant_objects())
        if not objects:
            _dsg_report(self, {'WARNING'}, 'Create the animated sequence first', 'Primero crea la secuencia animada')
            return {'CANCELLED'}
        set_static_microscrew_visuals_hidden(True)
        for obj in objects:
            # Microscrew visibility is keyed so later screws do not wait in the
            # viewport as frozen duplicates. Other animated tools may still be
            # explicitly restored here.
            if not bool(obj.get('DSG_animated_microscrew', False)):
                obj.hide_viewport = False
            obj.hide_select = False
            try:
                obj.hide_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        start, end = get_sequential_insertion_bounds(props)
        context.scene.frame_start = start
        context.scene.frame_end = end
        context.scene.frame_set(start)
        try:
            bpy.ops.screen.animation_play()
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not play the sequence: {exc}', f'No se pudo reproducir la secuencia: {exc}')
            return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_StopSequentialInsertionAnimation(Operator):
    bl_idname = 'dsg.stop_sequential_insertion_animation'
    bl_label = 'Stop Insertion Sequence'

    def execute(self, context):
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        has_animation = bool(
            get_animated_microscrew_objects()
            or get_animated_drill_objects()
            or get_animated_implant_objects()
            or (_valid_obj(guide) and guide.get('DSG_final_sequence_visibility_animation')))
        if not has_animation:
            restore_guide_home_transform(guide, scene=context.scene, make_visible=True)
            _dsg_report(self, {'WARNING'}, 'Create the animated sequence first', 'Primero crea la secuencia animada')
            return {'CANCELLED'}
        try:
            if context.screen and context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
        except Exception:
            try:
                bpy.ops.screen.animation_cancel()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        seated_frame = int(context.scene.get(
            'DSG_sequence_guide_seat_end_frame', context.scene.frame_current))
        context.scene.frame_set(seated_frame)
        restore_guide_home_transform(guide, scene=context.scene, make_visible=True)
        _dsg_report(
            self, {'INFO'},
            'Sequence stopped; the guide returned to its original seated position',
            'Secuencia detenida; la guía volvió a su posición original sobre el modelo')
        return {'FINISHED'}


class DSG_OT_ToggleSequentialInsertionVisibility(Operator):
    bl_idname = 'dsg.toggle_sequential_insertion_visibility'
    bl_label = 'Show or Hide Screws, Drills and Implants'

    def execute(self, context):
        objects = (get_animated_microscrew_objects() + get_animated_drill_objects()
                   + get_animated_implant_objects())
        if not objects:
            _dsg_report(self, {'WARNING'}, 'Create the animated sequence first', 'Primero crea la secuencia animada')
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
        _dsg_report(self, {'INFO'}, 'Screws, drills and implants hidden' if hide
            else 'Screws, drills and implants shown', 'Tornillos, fresas e implantes ocultados' if hide
            else 'Tornillos, fresas e implantes mostrados')
        return {'FINISHED'}


class DSG_OT_StartReinforcement(Operator):
    bl_idname = 'dsg.start_reinforcement'
    bl_label = 'Draw Reinforcement Chain'
    bl_options = {'REGISTER', 'UNDO'}

    def _remove_markers(self):
        remove_reinforcement_markers()

    def _remove_working_preview(self, props):
        preview = get_pending_reinforcement_preview(props)
        if _valid_obj(preview):
            safe_remove_object(preview)
        props.reinforcement_preview_obj = None

    def _refresh_markers(self, context):
        display_points = self._optimized_points if len(self._optimized_points) == len(self._points) else self._points
        refresh_reinforcement_markers(context, display_points, self._support_names)

    def _rebuild_preview(self, context, props, guide):
        self._remove_working_preview(props)
        if len(self._points) < 2:
            self._optimized_points = [Vector(point) for point in self._points]
            return None
        preview = build_reinforcement_chain_preview(
            context, props, guide,
            self._points, self._normals, self._support_objects)
        self._optimized_points = [Vector(point) for point in self._points]
        if _valid_obj(preview):
            try:
                optimized_data = json.loads(str(preview.get('DSG_reinforcement_points_json', '[]')))
                if len(optimized_data) == len(self._points):
                    self._optimized_points = [Vector(value) for value in optimized_data]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return preview

    def _finish_modal(self, context):
        self._remove_markers()
        if context.area:
            context.area.tag_redraw()

    def _cancel_modal(self, context, props):
        self._remove_working_preview(props)
        self._finish_modal(context)

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)

        if event.type == 'ESC' and event.value == 'PRESS':
            self._cancel_modal(context, props)
            _dsg_report(self, {'INFO'}, 'Reinforcement chain canceled', 'Cadena de refuerzo cancelada')
            return {'CANCELLED'}

        # Paso 8: el clic derecho termina la captura de puntos. Se elimina la
        # dependencia del teclado (Enter/Espacio) y se conserva Esc para cancelar.
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if len(self._points) < 2:
                _dsg_report(self, {'WARNING'},
                            'Add at least two points before ending the chain',
                            'Añade al menos dos puntos antes de terminar la cadena')
                return {'RUNNING_MODAL'}
            preview = get_pending_reinforcement_preview(props)
            if not _valid_obj(preview):
                preview = self._rebuild_preview(context, props, guide)
            if not _valid_obj(preview):
                _dsg_report(self, {'ERROR'},
                            'The reinforcement chain could not be generated',
                            'No se pudo generar la cadena de refuerzo')
                return {'RUNNING_MODAL'}
            point_count = len(self._points)
            self._finish_modal(context)
            _dsg_report(
                self, {'INFO'},
                f'Open reinforcement chain ready with {point_count} points and Ø{float(getattr(props, "connector_diameter", REINFORCEMENT_DIAMETER_MM)):.1f} mm. Confirm or discard it.',
                f'Cadena abierta de refuerzo preparada con {point_count} puntos y Ø{float(getattr(props, "connector_diameter", REINFORCEMENT_DIAMETER_MM)):.1f} mm. Confírmala o descártala.')
            return {'FINISHED'}

        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            if not self._points:
                _dsg_report(self, {'WARNING'}, 'There are no points to undo', 'No hay puntos para deshacer')
                return {'RUNNING_MODAL'}
            self._points.pop()
            self._normals.pop()
            self._support_objects.pop()
            self._support_names.pop()
            self._optimized_points = [Vector(point) for point in self._points]
            self._rebuild_preview(context, props, guide)
            self._refresh_markers(context)
            _dsg_report(
                self, {'INFO'},
                f'Last point removed. {len(self._points)} point(s) remain.',
                f'Último punto eliminado. Quedan {len(self._points)} punto(s).')
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            location, normal, support_obj = raycast_reinforcement_support(
                context, event, guide)
            if location is None or normal is None or not _valid_obj(support_obj):
                _dsg_report(
                    self, {'WARNING'},
                    'Place the point on the guide or on a previously confirmed reinforcement',
                    'Coloca el punto sobre la guía o sobre un refuerzo confirmado previamente')
                return {'RUNNING_MODAL'}

            location = Vector(location)
            normal = Vector(normal)
            if self._points and (location - self._points[-1]).length < 0.80:
                _dsg_report(
                    self, {'WARNING'},
                    'The new point is too close to the previous point',
                    'El nuevo punto está demasiado cerca del punto anterior')
                return {'RUNNING_MODAL'}

            self._points.append(location)
            self._normals.append(normal)
            self._support_objects.append(support_obj)
            support_name = _safe_object_name(support_obj)
            self._support_names.append(support_name)

            preview = None
            if len(self._points) >= 2:
                preview = self._rebuild_preview(context, props, guide)
                if not _valid_obj(preview):
                    self._points.pop()
                    self._normals.pop()
                    self._support_objects.pop()
                    self._support_names.pop()
                    self._optimized_points = [Vector(point) for point in self._points]
                    self._rebuild_preview(context, props, guide)
                    self._refresh_markers(context)
                    _dsg_report(
                        self, {'ERROR'},
                        'That point produced an invalid segment; choose another position',
                        'Ese punto produjo un segmento no válido; elige otra posición')
                    return {'RUNNING_MODAL'}

            self._refresh_markers(context)
            point_count = len(self._points)
            is_previous_reinforcement = bool(
                support_obj != guide
                and support_obj.get('DSG_reinforcement_confirmed', False))
            support_es = 'un refuerzo previo' if is_previous_reinforcement else 'la guía'
            support_en = 'a previous reinforcement' if is_previous_reinforcement else 'the guide'

            if point_count == 1:
                _dsg_report(
                    self, {'INFO'},
                    f'First point recorded on {support_en}. Add a second point.',
                    f'Primer punto registrado sobre {support_es}. Añade un segundo punto.')
            else:
                _dsg_report(
                    self, {'INFO'},
                    f'Point {point_count} recorded on {support_en}. Add more points or right-click to end the chain.',
                    f'Punto {point_count} registrado sobre {support_es}. Añade más puntos o haz clic derecho para terminar la cadena.')
            return {'RUNNING_MODAL'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                          'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
                          'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
                          'NUMPAD_8', 'NUMPAD_9'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not _require_workflow_stage(
                self, context, STEP_REINFORCEMENT,
                action_en='Cannot draw a reinforcement connector',
                action_es='No se puede dibujar un conector de refuerzo'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        activate_precision_orthographic(context)
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'DSG_Guide not found', 'No se encontró DSG_Guide')
            return {'CANCELLED'}
        if get_pending_reinforcement_preview(props):
            _dsg_report(self, {'WARNING'},
                        'Confirm or discard the pending reinforcement chain',
                        'Confirma o descarta la cadena de refuerzo pendiente')
            return {'CANCELLED'}
        self._points = []
        self._normals = []
        self._support_objects = []
        self._support_names = []
        self._optimized_points = []
        self._remove_markers()
        context.window_manager.modal_handler_add(self)
        _dsg_report(
            self, {'INFO'},
            'Click 2 or more points on the guide or previous reinforcements. Right-click ends; Backspace removes the last point; Esc cancels.',
            'Haz clic en 2 o más zonas. Clic derecho termina; Retroceso elimina el último punto; Esc cancela.')
        return {'RUNNING_MODAL'}


class DSG_OT_ConfirmReinforcementPreview(Operator):
    bl_idname = 'dsg.confirm_reinforcement_preview'
    bl_label = 'Confirm Reinforcement Connector'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_REINFORCEMENT,
                action_en='Cannot confirm the reinforcement connector',
                action_es='No se puede confirmar el conector de refuerzo'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        preview = get_pending_reinforcement_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'WARNING'}, 'There is no pending connector', 'No hay un conector pendiente')
            return {'CANCELLED'}
        index = int(getattr(props, 'reinforcement_count', 0))
        name = f'{REINFORCEMENT_PREFIX}{index:02d}'
        safe_remove_by_name(name)
        preview.name = name
        try:
            preview.data.name = name + ('_Mesh' if preview.type == 'MESH' else '_Curve')
            preview['DSG_reinforcement_preview'] = False
            preview['DSG_reinforcement_confirmed'] = True
            preview['DSG_reinforcement_index'] = index
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        link_object_to_dsg_collection(preview, ROLE_REINFORCEMENT)
        preview.show_in_front = False
        props.reinforcement_preview_obj = None
        props.reinforcement_count = index + 1
        remove_reinforcement_markers()
        set_active(context, preview)
        _dsg_report(self, {'INFO'}, f'Connector {index + 1} confirmed. You can create another.', f'Conector {index + 1} confirmado. Puedes crear otro.')
        return {'FINISHED'}


class DSG_OT_CancelReinforcementPreview(Operator):
    bl_idname = 'dsg.cancel_reinforcement_preview'
    bl_label = 'Discard Pending Connector'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        preview = get_pending_reinforcement_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'WARNING'}, 'There is no pending connector', 'No hay un conector pendiente')
            return {'CANCELLED'}
        safe_remove_object(preview)
        props.reinforcement_preview_obj = None
        remove_reinforcement_markers()
        _dsg_report(self, {'INFO'}, 'Pending connector discarded', 'Conector pendiente descartado')
        return {'FINISHED'}


class DSG_OT_RemoveLastReinforcement(Operator):
    bl_idname = 'dsg.remove_last_reinforcement'
    bl_label = 'Delete Last Connector'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        curves = get_confirmed_reinforcement_curves()
        if not curves:
            _dsg_report(self, {'WARNING'}, 'There are no confirmed connectors', 'No hay conectores confirmados')
            return {'CANCELLED'}
        last = curves[-1]
        safe_remove_object(last)
        remaining = get_confirmed_reinforcement_curves()
        props.reinforcement_count = len(remaining)
        _dsg_report(self, {'INFO'}, 'Last connector deleted', 'Último conector eliminado')
        return {'FINISHED'}


class DSG_OT_SkipReinforcement(Operator):
    bl_idname = 'dsg.skip_reinforcement'
    bl_label = 'Skip Reinforcement Connectors'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_REINFORCEMENT,
                action_en='Cannot resolve reinforcement',
                action_es='No se pueden resolver los refuerzos'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        pending = get_pending_reinforcement_preview(props)
        if _valid_obj(pending):
            safe_remove_object(pending)
        for curve in get_confirmed_reinforcement_curves():
            safe_remove_object(curve)
        remove_reinforcement_markers()
        props.reinforcement_preview_obj = None
        props.reinforcement_count = 0
        context.scene[WORKFLOW_REINFORCEMENT_RESOLVED_KEY] = True
        guide = _workflow_guide_candidate(props)
        reinforcement_signature = _workflow_object_signature(guide)
        if _workflow_signature_changed(context.scene, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, reinforcement_signature):
            _invalidate_workflow_after(context, STEP_REINFORCEMENT, reason='reinforcement_decision_changed')
        _workflow_store_signature(context.scene, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, reinforcement_signature)
        if _valid_obj(guide):
            guide['DSG_reinforcement_skipped'] = True
            guide['DSG_reinforcement_resolution'] = 'SKIPPED'
        props.current_step = STEP_DRILL
        _dsg_report(self, {'INFO'}, 'Connectors skipped. Continue to the drill step.', 'Conectores omitidos. Continúa con el drill.')
        return {'FINISHED'}


class DSG_OT_ApplyReinforcements(Operator):
    bl_idname = 'dsg.apply_reinforcements'
    bl_label = 'Add Connectors and Continue'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_REINFORCEMENT,
                action_en='Cannot apply the reinforcement connectors',
                action_es='No se pueden aplicar los conectores de refuerzo'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if get_pending_reinforcement_preview(props):
            _dsg_report(self, {'ERROR'}, 'Confirm or discard the pending connector', 'Confirma o descarta el conector pendiente')
            return {'CANCELLED'}
        guide = get_active_guide_obj(props)
        curves = get_confirmed_reinforcement_curves()
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'DSG_Guide not found', 'No se encontró DSG_Guide')
            return {'CANCELLED'}
        if not curves:
            _dsg_report(self, {'ERROR'}, 'There are no confirmed connectors; use Skip to continue without them', 'No hay conectores confirmados; usa Saltar para continuar sin ellos')
            return {'CANCELLED'}

        mesh_objects = []
        combined = None
        try:
            for index, curve in enumerate(curves):
                mesh_obj = reinforcement_curve_to_mesh(
                    context, curve, f'DSG_ReinforcementMeshTmp_{index:02d}')
                if not _valid_obj(mesh_obj):
                    raise RuntimeError(f'No se pudo convertir el conector {index + 1} to mesh')
                report = get_mesh_solid_report(mesh_obj, max_polygons=500000)
                if report.get('checked') and not report.get('solid'):
                    raise RuntimeError(
                        f'Connector {index + 1} no sólido: edges={report.get("bad_edges", 0)}')
                mesh_objects.append(mesh_obj)

            safe_remove_by_name(REINFORCEMENT_COMBINED_TMP_NAME)
            combined = build_combined_mesh_object_world(
                context, [guide] + mesh_objects, REINFORCEMENT_COMBINED_TMP_NAME)
            if not _valid_obj(combined):
                raise RuntimeError('Could not add connector geometry')

            report = get_mesh_solid_report(combined, max_polygons=1200000)
            if report.get('checked') and not report.get('solid'):
                raise RuntimeError(
                    f'Non-solid result: edges={report.get("bad_edges", 0)}, '
                    f'degeneradas={report.get("degenerate_faces", 0)}')

            old_name = _safe_object_name(guide)
            if old_name:
                _archive_current_guide_for_sleeve_rebuild(
                    props, reason='reinforcement_commit')
            for curve in curves:
                safe_remove_object(curve)
            for mesh_obj in mesh_objects:
                safe_remove_object(mesh_obj)
            mesh_objects.clear()

            combined.name = GUIDE_NAME
            combined.data.name = GUIDE_NAME + '_Mesh'
            _inherit_dsg_custom_properties(guide, combined)
            try:
                fem_curves = [curve for curve in curves if bool(curve.get('DSG_reinforcement_fem_generated', False))]
                fem_diameters = [
                    float(curve.get('DSG_reinforcement_diameter', getattr(props, 'connector_diameter', REINFORCEMENT_DIAMETER_MM)))
                    for curve in fem_curves
                ]
                combined['DSG_reinforcement_count'] = len(curves)
                combined['DSG_reinforcement_diameter'] = float(getattr(props, 'connector_diameter', REINFORCEMENT_DIAMETER_MM))
                combined['DSG_reinforcement_fusion'] = 'pending_final_voxel_remesh'
                combined['DSG_reinforcement_fem_generated'] = bool(fem_curves)
                if fem_diameters:
                    combined['DSG_reinforcement_variable_diameter'] = True
                    combined['DSG_reinforcement_diameter_min_mm'] = min(fem_diameters)
                    combined['DSG_reinforcement_diameter_max_mm'] = max(fem_diameters)
                    combined['DSG_reinforcement_fem_count'] = len(fem_curves)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            props.guide_obj = register_dsg_object(combined, ROLE_GUIDE, GUIDE_NAME)
            props.reinforcement_preview_obj = None
            props.reinforcement_count = 0
            context.scene[WORKFLOW_REINFORCEMENT_RESOLVED_KEY] = True
            reinforcement_signature = _workflow_object_signature(props.guide_obj)
            if _workflow_signature_changed(context.scene, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, reinforcement_signature):
                _invalidate_workflow_after(context, STEP_REINFORCEMENT, reason='reinforcement_geometry_changed')
            _workflow_store_signature(context.scene, WORKFLOW_REINFORCEMENT_SIGNATURE_KEY, reinforcement_signature)
            try:
                props.guide_obj['DSG_reinforcement_resolution'] = 'APPLIED'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            set_active(context, props.guide_obj)
            props.current_step = STEP_DRILL
            _dsg_report(self, {'INFO'}, f'{len(curves)} connector(s) added. The final remesh will fuse them permanently.', f'{len(curves)} conector(es) incorporado(s). El remesh final los fusionará definitivamente.')
            return {'FINISHED'}

        except Exception as exc:
            for mesh_obj in mesh_objects:
                safe_remove_object(mesh_obj)
            if _valid_obj(combined):
                safe_remove_object(combined)
            _dsg_report(self, {'ERROR'}, f'Conectores cancelados: {exc}. The original guide was preserved.', f'Conectores cancelados: {exc}. La guía original se conservó.')
            return {'CANCELLED'}


# ─────────────────────────────────────────────────────────────
# Exportación STL
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Grabado final de nombre de paciente
# ─────────────────────────────────────────────────────────────

