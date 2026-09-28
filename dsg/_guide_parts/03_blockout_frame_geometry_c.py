def _frame_width_nearest_surface(cache, point_world):
    tree = cache.get('width_bvh')
    matrix = cache.get('width_bvh_matrix')
    inverse = cache.get('width_bvh_inverse')
    if tree is None or matrix is None or inverse is None:
        return None, None, float('inf')
    try:
        result = tree.find_nearest(inverse @ Vector(point_world))
        if not result or result[0] is None:
            return None, None, float('inf')
        loc_local, normal_local, _index, _distance = result
        loc_world = matrix @ loc_local
        normal_world = matrix.to_3x3() @ normal_local
        if normal_world.length > 1.0e-10:
            normal_world.normalize()
        return loc_world, normal_world, (loc_world - Vector(point_world)).length
    except Exception:
        return None, None, float('inf')


def _frame_width_tangent_and_lateral(cache, route_indices, position, frame_radius_mm=None):
    """Stable local frame for width validation on a graph-geodesic route.

    The raw Dijkstra path follows triangulation edges and can zig-zag even when
    the underlying clinical route is smooth.  Using the immediately adjacent
    graph vertices rotates the lateral probe with that triangulation and can
    manufacture false 75% bottlenecks.  Estimate the tangent over an intrinsic
    arc-length window instead.  This changes only the validation orientation;
    the accepted centreline remains the original surface-constrained graph path.
    """
    coords = cache['coords']
    position = int(position)
    current_index = int(route_indices[position])
    center = Vector(coords[current_index])
    normal = _normalized_or_fallback(Vector(cache['normals'][current_index]), (0.0, 0.0, 1.0))

    if len(route_indices) <= 1:
        tangent = Vector((1.0, 0.0, 0.0))
    else:
        radius = max(0.5, float(frame_radius_mm or 1.5))
        tangent_window = max(0.80, min(2.00, radius * 0.50))

        left = position
        walked = 0.0
        while left > 0 and walked < tangent_window:
            a = coords[int(route_indices[left])]
            b = coords[int(route_indices[left - 1])]
            walked += _frame_np_distance(a, b)
            left -= 1

        right = position
        walked = 0.0
        last = len(route_indices) - 1
        while right < last and walked < tangent_window:
            a = coords[int(route_indices[right])]
            b = coords[int(route_indices[right + 1])]
            walked += _frame_np_distance(a, b)
            right += 1

        if left < position and right > position:
            tangent = Vector(coords[int(route_indices[right])]) - Vector(coords[int(route_indices[left])])
        elif right > position:
            tangent = Vector(coords[int(route_indices[right])]) - center
        elif left < position:
            tangent = center - Vector(coords[int(route_indices[left])])
        else:
            tangent = Vector((1.0, 0.0, 0.0))

    tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        tangent = Vector((1.0, 0.0, 0.0))
        if abs(tangent.dot(normal)) > 0.85:
            tangent = Vector((0.0, 1.0, 0.0))
        tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        return center, normal, tangent, None
    tangent.normalize()
    lateral = normal.cross(tangent)
    if lateral.length < 1.0e-8:
        return center, normal, tangent, None
    lateral.normalize()
    return center, normal, tangent, lateral


def _frame_width_retained_ratio(side_available_mm, radius_mm):
    radius = max(0.05, float(radius_mm))
    return max(0.0, min(1.0, float(side_available_mm) / radius))


def _frame_width_sample_is_hard_failure(fraction):
    mandatory_fraction = 1.0 - float(FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO)
    return float(fraction) <= mandatory_fraction + 1.0e-9


def _frame_route_full_width_profile(cache, route_indices, frame_radius_mm,
                                    start_tangent_hint=None, end_tangent_hint=None):
    """Validate a geodesic while allowing only the outer 25% to embed.

    Endpoint samples use the semantic closed-loop contour tangent when one is
    supplied.  A per-segment one-sided Dijkstra tangent is not the true tangent
    of a closed frame at an anchor and can create a false 75% support failure.
    Interior samples remain validated against the intrinsic route tangent.
    """
    if not route_indices:
        return {'ok': False, 'reason': 'empty route', 'failed_positions': [],
                'min_width_mm': 0.0, 'required_width_mm': 0.0, 'samples': 0,
                'min_retained_ratio': 0.0}
    radius = max(0.05, float(frame_radius_mm))
    required_width = radius * 2.0
    rise_tol = max(
        FRAME_WIDTH_SURFACE_RISE_MIN_TOL_MM,
        min(FRAME_WIDTH_SURFACE_RISE_MAX_TOL_MM,
            radius * FRAME_WIDTH_SURFACE_RISE_RADIUS_FACTOR),
    )
    coords = cache['coords']
    positions = [0]
    accumulated = 0.0
    step = max(0.20, float(FRAME_WIDTH_SAMPLE_STEP_MM))
    for pos in range(1, len(route_indices) - 1):
        a = coords[int(route_indices[pos - 1])]
        b = coords[int(route_indices[pos])]
        accumulated += _frame_np_distance(a, b)
        if accumulated >= step:
            positions.append(pos)
            accumulated = 0.0
    if len(route_indices) > 1:
        positions.append(len(route_indices) - 1)
    positions = sorted(set(int(p) for p in positions))

    failed_positions = []
    tolerated_positions = []
    min_half_width = radius
    min_retained_ratio = 1.0
    checked = 0
    worst_rise = 0.0
    last_pos = len(route_indices) - 1
    for pos in positions:
        # At a closed-loop anchor the true contour tangent depends on BOTH
        # neighbouring segments.  Reusing the semantic tangent that already
        # passed SAFE SURFACE SNAP keeps endpoint validation geometrically
        # consistent.  Only the exact endpoints use this policy; the departure
        # corridor and all interior samples still use the intrinsic route.
        endpoint_hint = None
        if pos == 0 and start_tangent_hint is not None:
            endpoint_hint = start_tangent_hint
        elif pos == last_pos and end_tangent_hint is not None:
            endpoint_hint = end_tangent_hint

        if endpoint_hint is not None:
            endpoint_profile = _frame_anchor_width_profile(
                cache, int(route_indices[pos]), endpoint_hint, radius)
            checked += int(endpoint_profile.get('samples', 0))
            worst_rise = max(
                worst_rise, float(endpoint_profile.get('worst_surface_rise_mm', 0.0)))
            local_half = max(0.0, float(endpoint_profile.get('min_width_mm', 0.0)) * 0.5)
            local_ratio = float(endpoint_profile.get(
                'min_retained_ratio', _frame_width_retained_ratio(local_half, radius)))
            min_half_width = min(min_half_width, local_half)
            min_retained_ratio = min(min_retained_ratio, local_ratio)
            if not bool(endpoint_profile.get('ok')):
                failed_positions.append(pos)
            elif bool(endpoint_profile.get('tolerated_outer_embedding', False)):
                tolerated_positions.append(pos)
            continue

        center, normal, tangent, lateral = _frame_width_tangent_and_lateral(
            cache, route_indices, pos, frame_radius_mm=radius)
        if lateral is None:
            failed_positions.append(pos)
            min_half_width = 0.0
            min_retained_ratio = 0.0
            continue
        local_half = radius
        local_hard = False
        local_tolerated = False
        for side in (-1.0, 1.0):
            side_available = radius
            for fraction in FRAME_WIDTH_SAMPLE_FRACTIONS:
                requested = radius * float(fraction)
                query = center + lateral * (side * requested)
                surface_point, _surface_normal, _distance = _frame_width_nearest_surface(cache, query)
                checked += 1
                failed_here = surface_point is None
                if surface_point is not None:
                    delta = surface_point - query
                    rise = float(delta.dot(normal))
                    axial_slip = abs(float((surface_point - center).dot(tangent)))
                    worst_rise = max(worst_rise, rise)
                    if rise > rise_tol and axial_slip <= max(0.65, radius * 0.60):
                        failed_here = True
                if failed_here:
                    side_available = min(
                        side_available,
                        max(0.0, requested - radius * FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO),
                    )
                    if _frame_width_sample_is_hard_failure(fraction):
                        local_hard = True
                    else:
                        local_tolerated = True
                    break
            local_half = min(local_half, side_available)
        local_ratio = _frame_width_retained_ratio(local_half, radius)
        min_half_width = min(min_half_width, local_half)
        min_retained_ratio = min(min_retained_ratio, local_ratio)
        if local_ratio + 1.0e-9 < FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO:
            local_hard = True
        if local_hard:
            failed_positions.append(pos)
        elif local_tolerated:
            tolerated_positions.append(pos)

    ok = not bool(failed_positions)
    return {
        'ok': ok,
        'reason': '' if ok else 'central 75% frame support band would narrow',
        'failed_positions': failed_positions,
        'tolerated_positions': tolerated_positions,
        'min_width_mm': float(min_half_width * 2.0),
        'required_width_mm': float(required_width),
        'min_retained_ratio': float(min_retained_ratio),
        'allowed_outer_embed_ratio': float(FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO),
        'surface_rise_tolerance_mm': float(rise_tol),
        'worst_surface_rise_mm': float(worst_rise),
        'samples': int(checked),
        'tolerated_samples': int(len(tolerated_positions)),
    }


def _frame_forbid_width_bottlenecks(cache, clinical_allowed, route_indices,
                                     failed_positions, frame_radius_mm,
                                     start_index, goal_index,
                                     forbid_radius_scale=1.0):
    """Dilate rejected bottlenecks so Dijkstra must go around/above them.

    Endpoint width failures are special: the semantic anchor itself must remain
    fixed on the surface, but the *first/last departure vertex* is allowed to
    change.  Therefore an endpoint failure blocks the adjacent route vertex
    rather than aborting immediately.  This forces Dijkstra to try another
    intrinsic departure direction while preserving the anchor and the strict
    no-Euclidean-fallback contract.
    """
    if clinical_allowed is None:
        clinical_allowed = np.ones(int(cache.get('vertex_count', 0)), dtype=bool)
    base_radius = max(
        FRAME_WIDTH_FORBID_RADIUS_MIN_MM,
        min(FRAME_WIDTH_FORBID_RADIUS_MAX_MM,
            float(frame_radius_mm) * FRAME_WIDTH_FORBID_RADIUS_FACTOR),
    )
    # This radius steers the next intrinsic search; it is not the clinical width
    # requirement. When accumulated exclusions disconnect a detailed dental
    # mesh, retry with a more local exclusion while preserving the exact same
    # final 75% width validation.
    radius = max(0.12, float(base_radius) * max(0.15, float(forbid_radius_scale)))
    blocked = 0
    route_count = len(route_indices)
    protected = {int(start_index), int(goal_index)}
    for raw_pos in failed_positions:
        pos = int(raw_pos)
        if route_count < 3:
            continue

        # A failure at/inside the endpoint guard does not prove the anchor is
        # impossible.  Redirect the forbidden region to the adjacent departure
        # vertex so the next intrinsic search can leave the anchor differently.
        endpoint_escape = False
        if pos <= FRAME_WIDTH_ANCHOR_GUARD_POINTS:
            pos = 1
            endpoint_escape = True
        elif pos >= route_count - 1 - FRAME_WIDTH_ANCHOR_GUARD_POINTS:
            pos = route_count - 2
            endpoint_escape = True

        vertex_index = int(route_indices[pos])

        # At an endpoint, block only the currently chosen departure vertex.
        # Dilating a radius here can accidentally remove every neighbour of the
        # anchor and make the graph look disconnected even though another safe
        # departure exists.  Repeated reroutes naturally enumerate alternatives.
        if endpoint_escape:
            if vertex_index not in protected and clinical_allowed[vertex_index]:
                clinical_allowed[vertex_index] = False
                blocked += 1
            continue

        # IMPORTANT: dilate the exclusion intrinsically on the mesh graph.
        # Euclidean KD radius search can jump across a thin tooth, embrasure or
        # opposite surface sheet and erase a perfectly valid alternative corridor.
        # That was the cause of artificial graph disconnections after rerouting.
        nearby_intrinsic = _frame_vertices_within_surface_radius(
            cache, vertex_index, radius,
            max_candidates=max(256, min(FRAME_ANCHOR_SAFE_SNAP_MAX_CANDIDATES, 1200)),
        )
        if nearby_intrinsic:
            for index, _surface_distance in nearby_intrinsic:
                index = int(index)
                if index in protected:
                    continue
                if clinical_allowed[index]:
                    clinical_allowed[index] = False
                    blocked += 1
        elif vertex_index not in protected and clinical_allowed[vertex_index]:
            clinical_allowed[vertex_index] = False
            blocked += 1
    clinical_allowed[int(start_index)] = True
    clinical_allowed[int(goal_index)] = True
    return clinical_allowed, int(blocked), float(radius)


def _frame_width_preserving_surface_route(context, surface_obj, cache,
                                          start_index, goal_index,
                                          frame_radius_mm,
                                          max_expansions=FRAME_SURFACE_MAX_EXPANSIONS,
                                          start_tangent_hint=None,
                                          end_tangent_hint=None):
    """Shortest intrinsic route preserving the mandatory central 75% band."""
    tree, _matrix, _inverse, error = _frame_width_surface_bvh(context, surface_obj, cache)
    if tree is None:
        return None, {'reason': error or 'frame-width BVH unavailable', 'expanded': 0,
                      'backend': 'NONE', 'width_validated': False}

    clinical_allowed = np.ones(int(cache.get('vertex_count', 0)), dtype=bool)
    total_expanded = 0
    total_blocked = 0
    last_profile = None
    backends = set()
    last_stats = {}
    corridor_resets = 0
    forbid_radius_scale = 1.0
    for reroute in range(max(1, int(FRAME_WIDTH_REROUTE_ATTEMPTS))):
        route, stats = _frame_geodesic_surface_route(
            cache, start_index, goal_index,
            max_expansions=max_expansions,
            hard_allowed_mask=clinical_allowed,
        )
        last_stats = dict(stats or {})
        total_expanded += int(last_stats.get('expanded', 0))
        if last_stats.get('backend'):
            backends.add(str(last_stats.get('backend')))
        if not route:
            # Hard exclusions are cumulative. On high-resolution dental meshes a
            # valid corridor can be cut accidentally by the dilation itself.
            # Restart from the complete intrinsic graph with smaller, localized
            # blockers. No failed route is accepted: every candidate must still
            # pass _frame_route_full_width_profile unchanged.
            if total_blocked > 0 and corridor_resets < 2:
                corridor_resets += 1
                forbid_radius_scale *= 0.50
                clinical_allowed = np.ones(int(cache.get('vertex_count', 0)), dtype=bool)
                clinical_allowed[int(start_index)] = True
                clinical_allowed[int(goal_index)] = True
                continue
            return None, {
                **last_stats,
                'reason': 'no connected intrinsic geodesic corridor remains after central 75% support-band rerouting',
                'expanded': int(total_expanded),
                'width_validated': False,
                'width_reroutes': int(reroute),
                'width_blocked_vertices': int(total_blocked),
                'width_corridor_resets': int(corridor_resets),
                'backend': '+'.join(sorted(backends)) if backends else str(last_stats.get('backend', 'NONE')),
            }

        profile = _frame_route_full_width_profile(
            cache, route, frame_radius_mm,
            start_tangent_hint=start_tangent_hint,
            end_tangent_hint=end_tangent_hint,
        )
        last_profile = profile
        if bool(profile.get('ok')):
            return route, {
                **last_stats,
                'expanded': int(total_expanded),
                'width_validated': True,
                'width_policy': 'GEODESIC_SURFACE_EMBED_25_PERCENT',
                'width_required_mm': float(profile.get('required_width_mm', frame_radius_mm * 2.0)),
                'width_min_mm': float(profile.get('min_width_mm', frame_radius_mm * 2.0)),
                'width_min_retained_ratio': float(profile.get('min_retained_ratio', 1.0)),
                'width_allowed_outer_embed_ratio': float(profile.get('allowed_outer_embed_ratio', FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO)),
                'width_tolerated_samples': int(profile.get('tolerated_samples', 0)),
                'width_surface_rise_tolerance_mm': float(profile.get('surface_rise_tolerance_mm', 0.0)),
                'width_worst_surface_rise_mm': float(profile.get('worst_surface_rise_mm', 0.0)),
                'width_samples': int(profile.get('samples', 0)),
                'width_reroutes': int(reroute),
                'width_blocked_vertices': int(total_blocked),
                'backend': '+'.join(sorted(backends)) if backends else str(last_stats.get('backend', 'UNKNOWN')),
            }

        failed = list(profile.get('failed_positions', []) or [])
        # Do not abort merely because the first route departure makes the
        # endpoint look too narrow.  The anchor passed SAFE SURFACE SNAP using
        # the semantic contour tangent; the actual Dijkstra departure may have
        # a different tangent.  Force an intrinsic endpoint escape reroute first.
        clinical_allowed, blocked, _forbid_radius = _frame_forbid_width_bottlenecks(
            cache, clinical_allowed, route, failed, frame_radius_mm,
            start_index, goal_index,
            forbid_radius_scale=forbid_radius_scale)
        total_blocked += int(blocked)
        if blocked <= 0:
            break

    final_failed = list((last_profile or {}).get('failed_positions', []) or [])
    final_endpoint_corridor_failure = bool(final_failed) and bool(route) and any(
        int(p) <= FRAME_WIDTH_ANCHOR_GUARD_POINTS
        or int(p) >= len(route) - 1 - FRAME_WIDTH_ANCHOR_GUARD_POINTS
        for p in final_failed
    )
    # Exact endpoints were already validated with the semantic closed-loop
    # tangent.  A remaining near-end failure therefore describes the intrinsic
    # departure corridor, not a contradiction in the resolved anchor itself.
    final_reason = (
        'intrinsic endpoint corridor cannot preserve the central 75% support band after rerouting'
        if final_endpoint_corridor_failure
        else 'no route preserved the central 75% support band after bottleneck rerouting'
    )
    return None, {
        **last_stats,
        'reason': final_reason,
        'expanded': int(total_expanded),
        'width_validated': False,
        'width_policy': 'GEODESIC_SURFACE_EMBED_25_PERCENT',
        'width_required_mm': float(frame_radius_mm) * 2.0,
        'width_min_mm': float((last_profile or {}).get('min_width_mm', 0.0)),
        'width_reroutes': int(FRAME_WIDTH_REROUTE_ATTEMPTS),
        'width_blocked_vertices': int(total_blocked),
        'width_corridor_resets': int(corridor_resets),
        'backend': '+'.join(sorted(backends)) if backends else str(last_stats.get('backend', 'UNKNOWN')),
    }

def _frame_intrinsic_resample(cache, route_indices, max_spacing):
    """Resample along the mesh-edge polyline; never project through free space."""
    if not route_indices:
        return [], []
    coords = cache['coords']
    normals = cache['normals']
    raw_points = [Vector(coords[int(index)]) for index in route_indices]
    raw_normals = [Vector(normals[int(index)]) for index in route_indices]
    if len(raw_points) <= 2:
        return raw_points, raw_normals

    target = max(0.08, float(max_spacing))
    out_points = [raw_points[0].copy()]
    out_normals = [_normalized_or_fallback(raw_normals[0], (0.0, 0.0, 1.0))]
    distance_since_keep = 0.0
    for index in range(1, len(raw_points) - 1):
        edge_length = (raw_points[index] - raw_points[index - 1]).length
        distance_since_keep += edge_length
        turn = _angle_between_segments(
            raw_points[index - 1], raw_points[index], raw_points[index + 1])
        ndot = max(-1.0, min(1.0, abs(raw_normals[index - 1].dot(raw_normals[index + 1]))))
        normal_change = math.acos(ndot)
        if (distance_since_keep >= target
                or turn >= math.radians(9.0)
                or normal_change >= math.radians(10.0)):
            out_points.append(raw_points[index].copy())
            out_normals.append(_normalized_or_fallback(raw_normals[index], out_normals[-1]))
            distance_since_keep = 0.0
    if (raw_points[-1] - out_points[-1]).length > 1.0e-6:
        out_points.append(raw_points[-1].copy())
        out_normals.append(_normalized_or_fallback(raw_normals[-1], out_normals[-1]))
    return out_points, out_normals


def _frame_virtual_anchor_shortest_route(cache, start_anchor, end_anchor):
    """Shortest surface route between exact face/barycentric endpoints."""
    start_vertices = sorted({int(v) for v in (start_anchor.get('triangle_vertices') or ()) if int(v) >= 0})
    end_vertices = sorted({int(v) for v in (end_anchor.get('triangle_vertices') or ()) if int(v) >= 0})
    if not start_vertices:
        v, _ = _frame_nearest_vertex(cache, start_anchor['point'])
        if v >= 0:
            start_vertices = [int(v)]
    if not end_vertices:
        v, _ = _frame_nearest_vertex(cache, end_anchor['point'])
        if v >= 0:
            end_vertices = [int(v)]
    if not start_vertices or not end_vertices:
        return None, {'reason': 'surface anchor has no graph representation', 'backend': 'NONE'}

    if (int(start_anchor.get('triangle_index', -1)) >= 0
            and int(start_anchor.get('triangle_index', -1)) == int(end_anchor.get('triangle_index', -2))):
        return [], {
            'reason': '', 'backend': 'SAME_TRIANGLE_DIRECT',
            'cost': float((Vector(end_anchor['point']) - Vector(start_anchor['point'])).length),
            'expanded': 0, 'direct_surface_segment': True,
        }

    coords = cache['coords']
    start_offsets = np.asarray([_frame_np_distance(coords[v], start_anchor['point']) for v in start_vertices], dtype=np.float64)
    end_offsets = np.asarray([_frame_np_distance(coords[v], end_anchor['point']) for v in end_vertices], dtype=np.float64)

    scipy_error = ''
    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra as scipy_dijkstra
        graph = cache.get('scipy_csr_graph')
        if graph is None:
            graph = csr_matrix(
                (cache['csr_weights'], cache['csr_dst'], cache['csr_offsets']),
                shape=(int(cache['vertex_count']), int(cache['vertex_count'])), copy=False)
            cache['scipy_csr_graph'] = graph
        distances, predecessors = scipy_dijkstra(
            graph, directed=True, indices=np.asarray(start_vertices, dtype=np.int32),
            return_predecessors=True)
        distances = np.atleast_2d(distances)
        predecessors = np.atleast_2d(predecessors)
        best = None
        for si, _sv in enumerate(start_vertices):
            for ei, ev in enumerate(end_vertices):
                d = float(distances[si, int(ev)])
                if not np.isfinite(d):
                    continue
                total = float(start_offsets[si] + d + end_offsets[ei])
                if best is None or total < best[0]:
                    best = (total, si, ei)
        if best is not None:
            total, si, ei = best
            start_vertex = int(start_vertices[si])
            current = int(end_vertices[ei])
            route = [current]
            guard = 0
            while current != start_vertex and guard <= int(cache['vertex_count']) + 1:
                previous = int(predecessors[si, current])
                if previous < 0 or previous == current:
                    route = None
                    break
                route.append(previous)
                current = previous
                guard += 1
            if route:
                route.reverse()
                return route, {
                    'reason': '', 'backend': 'SCIPY_VIRTUAL_ANCHOR_DIJKSTRA',
                    'cost': float(total),
                    'expanded': int(np.count_nonzero(np.isfinite(distances[si]))),
                    'direct_surface_segment': False,
                }
    except Exception as exc:
        scipy_error = str(exc)

    best = None
    for si, sv in enumerate(start_vertices):
        for ei, ev in enumerate(end_vertices):
            route, stats = _frame_geodesic_surface_route(cache, sv, ev)
            if not route:
                continue
            total = float(start_offsets[si] + float(stats.get('cost', 0.0)) + end_offsets[ei])
            if best is None or total < best[0]:
                best = (total, route, stats)
    if best is None:
        return None, {
            'reason': 'anchors lie on disconnected surface components',
            'backend': 'NONE', 'scipy_error': scipy_error,
        }
    total, route, stats = best
    out = dict(stats or {})
    out.update({'reason': '', 'cost': float(total), 'direct_surface_segment': False})
    return route, out


def build_surface_intrinsic_frame_path(context, surface_obj, anchors, insertion_axis,
                                       max_spacing=FRAME_SURFACE_TARGET_SPACING_MM,
                                       frame_radius_mm=FRAME_RADIUS_DEFAULT_MM):
    """Shortest on-surface closed frame through user anchors in click order.

    The centreline only has to remain on the passive-model surface. The
    cylindrical frame may overlap anatomy; final DSG boolean adaptation is
    intentionally responsible for trimming that overlap. No 75% width gate,
    clearance field, semantic corridor, or free-space fallback is used.
    """
    cache, cache_reused, cache_error = _build_frame_surface_graph_cache(context, surface_obj)
    if cache is None:
        return None, {'engine': FRAME_SURFACE_ENGINE_ID, 'reason': cache_error, 'cache_reused': False}

    tree, _matrix, _inverse, bvh_error = _frame_width_surface_bvh(context, surface_obj, cache)
    if tree is None:
        return None, {
            'engine': FRAME_SURFACE_ENGINE_ID,
            'reason': bvh_error or 'surface BVH unavailable',
            'cache_reused': bool(cache_reused),
        }

    source_anchors = _remove_near_duplicate_points(anchors, epsilon=0.02, closed=True)
    if len(source_anchors) < 4:
        return None, {'engine': FRAME_SURFACE_ENGINE_ID, 'reason': 'not enough anchors'}

    resolved_anchors = []
    snap_distances = []
    for anchor_index, source in enumerate(source_anchors):
        projection = _frame_surface_projection(cache, source, max_distance_mm=3.0)
        if projection is None:
            projection = _frame_surface_projection(cache, source)
        if projection is None:
            return None, {
                'engine': FRAME_SURFACE_ENGINE_ID,
                'reason': f'anchor {anchor_index + 1} could not be projected to the passive model',
                'cache_reused': bool(cache_reused), 'anchor_index': int(anchor_index + 1),
                'euclidean_fallback': False,
            }
        resolved_anchors.append(projection)
        snap_distances.append(float(projection.get('distance_mm', 0.0)))

    combined_points = []
    catmull_controls = []
    total_length = 0.0
    total_graph_cost = 0.0
    route_backends = set()
    continuous_backends = set()
    raw_path_vertices = 0
    count = len(resolved_anchors)

    for segment_index in range(count):
        next_index = (segment_index + 1) % count
        start_anchor = resolved_anchors[segment_index]
        end_anchor = resolved_anchors[next_index]
        route_indices, stats = _frame_virtual_anchor_shortest_route(cache, start_anchor, end_anchor)
        if route_indices is None:
            return None, {
                'engine': FRAME_SURFACE_ENGINE_ID,
                'reason': f'segment {segment_index + 1}: {stats.get("reason", "surface route failed")}',
                'cache_reused': bool(cache_reused),
                'segment_index': int(segment_index + 1),
                'route_stats': dict(stats or {}),
                'euclidean_fallback': False,
            }

        route_backends.add(str(stats.get('backend', 'UNKNOWN')))
        total_graph_cost += float(stats.get('cost', 0.0))

        if bool(stats.get('direct_surface_segment', False)):
            continuous = np.asarray([tuple(start_anchor['point']), tuple(end_anchor['point'])], dtype=np.float64)
            continuous = frame_surface_corridor.resample_polyline(continuous, max(0.20, float(max_spacing)))
            continuous_backend = 'SAME_TRIANGLE_DIRECT'
        else:
            raw_path_vertices += len(route_indices)
            continuous, continuous_backend = _frame_continuous_project_and_smooth(
                cache, route_indices, start_anchor, end_anchor, allowed_mask=None,
                frame_radius_mm=max(0.10, float(frame_radius_mm)))
            if continuous is None or len(continuous) < 2:
                raw = np.asarray([
                    tuple(start_anchor['point']),
                    *[tuple(cache['coords'][int(v)]) for v in route_indices],
                    tuple(end_anchor['point']),
                ], dtype=np.float64)
                continuous = frame_surface_corridor.resample_polyline(raw, max(0.20, float(max_spacing)))
                continuous_backend = 'DENSE_SURFACE_EDGE_PATH'

        continuous = np.asarray(continuous, dtype=np.float64)
        continuous_backends.add(str(continuous_backend))
        if len(continuous) < 2:
            return None, {
                'engine': FRAME_SURFACE_ENGINE_ID,
                'reason': f'segment {segment_index + 1}: continuous surface path is empty',
                'cache_reused': bool(cache_reused), 'euclidean_fallback': False,
            }

        # The geodesic/continuous solver is intentionally dense.  Do NOT feed
        # all of those samples into Catmull-Rom: they encode tiny zig-zags from
        # the IOS triangulation.  Build a much sparser control polygon first.
        segment_controls = _frame_sparse_catmull_controls(
            continuous, target_spacing=FRAME_CATMULL_CONTROL_SPACING_MM_FIXED)
        for control in segment_controls[:-1]:
            control = Vector(control)
            if catmull_controls and (control - catmull_controls[-1]).length <= 0.010:
                continue
            catmull_controls.append(control.copy())

        for a, b in zip(continuous[:-1], continuous[1:]):
            total_length += float(np.linalg.norm(np.asarray(b) - np.asarray(a)))
        for point in continuous[:-1]:
            point = Vector(point)
            if combined_points and (point - combined_points[-1]).length <= 0.010:
                continue
            combined_points.append(point.copy())

    if len(combined_points) < 4:
        return None, {
            'engine': FRAME_SURFACE_ENGINE_ID, 'reason': 'surface shortest path is too short',
            'cache_reused': bool(cache_reused), 'euclidean_fallback': False,
        }
    if len(combined_points) > 2 and (combined_points[0] - combined_points[-1]).length <= 0.010:
        combined_points.pop()
    if len(catmull_controls) > 2 and (catmull_controls[0] - catmull_controls[-1]).length <= 0.010:
        catmull_controls.pop()

    # v9.2.68: route finding remains exact/shortest on the surface, but the
    # tube is evaluated from a sparse centripetal Catmull control polygon.
    # This removes the saw-tooth appearance caused by using every geodesic
    # sample as a visible bend.  Evaluated spline samples are projected back
    # onto the passive model and tethered to the original route.
    clean_points, final_controls = _frame_clean_catmull_surface_loop(
        cache, combined_points, catmull_controls)
    if len(clean_points) >= 4:
        combined_points = clean_points

    clean_length = 0.0
    if len(combined_points) > 1:
        closed_seq = combined_points + [combined_points[0]]
        for a, b in zip(closed_seq[:-1], closed_seq[1:]):
            clean_length += float((Vector(b) - Vector(a)).length)

    return combined_points, {
        'engine': FRAME_SURFACE_ENGINE_ID, 'reason': '', 'cache_reused': bool(cache_reused),
        'surface_name': str(cache.get('surface_name', '')),
        'surface_vertices': int(cache.get('vertex_count', 0)),
        'surface_triangles': int(len(cache.get('triangles', ()))),
        'expanded': 0, 'raw_path_vertices': int(raw_path_vertices),
        'final_points': int(len(combined_points)), 'segment_count': int(count),
        'catmull_control_points': int(len(final_controls)),
        'catmull_control_spacing_mm': float(FRAME_CATMULL_CONTROL_SPACING_MM_FIXED),
        'catmull_sample_spacing_mm': float(FRAME_CATMULL_SAMPLE_SPACING_MM_FIXED),
        'geodesic_length_mm': float(total_length),
        'clean_spline_length_mm': float(clean_length),
        'weighted_route_cost': float(total_graph_cost),
        'max_anchor_snap_mm': float(max(snap_distances) if snap_distances else 0.0),
        'anchor_auto_relocated_count': 0,
        'anchor_auto_relocated_max_surface_mm': 0.0,
        'anchor_auto_relocated_max_euclidean_mm': 0.0,
        'anchor_resolution': [
            {
                'relocated': False, 'requested': [float(v) for v in source],
                'resolved': [float(v) for v in resolved['point']],
                'initial_snap_mm': float(resolved.get('distance_mm', 0.0)),
                'triangle_index': int(resolved.get('triangle_index', -1)),
                'barycentric': list(resolved.get('barycentric', [])),
            }
            for source, resolved in zip(source_anchors, resolved_anchors)
        ],
        'resolved_anchor_points': [[float(v) for v in item['point']] for item in resolved_anchors],
        'resolved_anchor_surface_coordinates': [
            {'triangle_index': int(item.get('triangle_index', -1)),
             'barycentric': list(item.get('barycentric', []))}
            for item in resolved_anchors
        ],
        'max_local_vertices': int(cache.get('vertex_count', 0)),
        'full_surface_attempts': int(count), 'euclidean_fallback': False,
        'backend': '+'.join(sorted(route_backends)) if route_backends else 'UNKNOWN',
        'distance_backend': 'EXACT_MESH_EDGE_LENGTH',
        'continuous_backend': '+'.join(sorted(continuous_backends)) if continuous_backends else 'DENSE_SURFACE_EDGE_PATH',
        'width_validated': False,
        'width_policy': 'NONE_FINAL_BOOLEAN_ADAPTS_TUBE_TO_MODEL',
        'width_required_mm': 0.0, 'width_min_mm': 0.0, 'width_min_retained_ratio': 0.0,
        'width_allowed_outer_embed_ratio': 1.0, 'width_tolerated_samples': 0,
        'width_reroutes': 0, 'width_blocked_vertices': 0, 'width_samples': 0,
        'width_worst_surface_rise_mm': 0.0, 'width_surface_rise_tolerance_mm': 0.0,
        'width_endpoint_tangent_policy': 'NOT_USED', 'semantic_corridor': False,
        'clearance_evaluations': 0,
        'route_objective': 'SHORTEST_SURFACE_DISTANCE_THROUGH_USER_ANCHORS_IN_CLICK_ORDER',
    }


def create_poly_curve_object(context, name, points, bevel_radius=1.0,
                             bevel_resolution=8, cyclic=False):
    """Lightweight POLY sweep: no Bézier handles and therefore no overshoot."""
    pts = [Vector(point) for point in points]
    if len(pts) < 2:
        return None
    if cyclic and len(pts) > 2 and (pts[0] - pts[-1]).length < 0.01:
        pts.pop()
    curve_data = bpy.data.curves.new(name + '_Curve', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 1
    curve_data.render_resolution_u = 1
    curve_data.fill_mode = 'FULL'
    curve_data.bevel_depth = float(bevel_radius)
    curve_data.bevel_resolution = max(3, int(bevel_resolution))
    curve_data.use_fill_caps = not bool(cyclic)
    spline = curve_data.splines.new('POLY')
    spline.points.add(len(pts) - 1)
    for point_data, point in zip(spline.points, pts):
        point_data.co = (float(point.x), float(point.y), float(point.z), 1.0)
    spline.use_cyclic_u = bool(cyclic)
    # POLY splines default to flat-shaded conversion. The Bezier sibling of
    # this function already sets this; the frame/tube path was the one
    # surface that still converted to a faceted mesh (found during the
    # 8.2.16 UI/aesthetics audit).
    spline.use_smooth = True
    obj = bpy.data.objects.new(name, curve_data)
    link_object(context, obj)
    return obj


def _frame_organic_bezier_controls(points, radius, cyclic=True):
    """Return a clean control polygon for the visible frame tube.

    The geodesic solver intentionally emits a very dense, surface-projected
    polyline.  Sweeping that polyline directly preserves tiny changes inherited
    from IOS triangles and the result can look segmented or "machined".  For
    the final *visible* tube we keep the geodesic route as the clinical source,
    but resample it to a compact control polygon before the continuous Bezier
    sweep.  The control spacing is deliberately conservative so the frame stays
    close to the solved surface corridor while gaining C1-continuous tangency.
    """
    pts = _remove_near_duplicate_points(points, epsilon=0.015, closed=bool(cyclic))
    if len(pts) < 4:
        return pts

    r = max(0.25, float(radius))
    # About one control every 0.8-1.45 mm for normal guide-frame radii.  This is
    # much denser than the 5 mm routing controls, so AUTO Bezier handles cannot
    # wander far from the surface, but sparse enough to remove mesh chatter.
    min_dist = max(0.80, min(1.45, r * 0.42))

    if not cyclic:
        return simplify_points_by_distance(pts, min_dist=min_dist)

    # Closed-loop distance simplification.  Unlike the generic open helper, this
    # does not give the arbitrary first/last seam special treatment.
    controls = [pts[0].copy()]
    for point in pts[1:]:
        if (point - controls[-1]).length >= min_dist:
            controls.append(point.copy())

    if len(controls) >= 4 and (controls[-1] - controls[0]).length < min_dist * 0.45:
        # A tiny seam edge creates a visible kink even with smooth shading.
        controls.pop()
    if len(controls) < 4:
        return pts
    return controls


def build_surface_poly_tube_mesh(context, points, radius, name=FRAME_NAME,
                                 bevel_resolution=8, cyclic=True):
    """Build the clinical surface frame with a continuous organic sweep.

    Historical versions used a POLY curve for the final sweep.  The centreline
    was correct, but every tiny geodesic direction change became a geometric
    bend.  DSG 9.6.3 keeps the solved path, reduces only redundant display
    controls and uses AUTO Bezier tangents.  This makes the frame read as one
    anatomical ribbon/tube instead of a chain of short straight cylinders.
    """
    controls = _frame_organic_bezier_controls(points, radius, cyclic=cyclic)
    if len(controls) < 2:
        return None

    curve_obj = create_bezier_curve_object(
        context, name, controls,
        bevel_radius=radius,
        bevel_resolution=max(12, int(bevel_resolution)),
        cyclic=cyclic)
    if not _valid_obj(curve_obj):
        return None
    try:
        for spline in curve_obj.data.splines:
            if getattr(spline, 'type', '') != 'BEZIER':
                continue
            for bp in spline.bezier_points:
                # AUTO_CLAMPED keeps tangent continuity while suppressing the
                # hook/overshoot risk of unrestricted AUTO handles near sharp
                # embrasure turns.
                bp.handle_left_type = 'AUTO_CLAMPED'
                bp.handle_right_type = 'AUTO_CLAMPED'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Bezier continuity gives the smoothness; we do not need the historical
    # 24 evaluations per control segment. Eight keeps the mesh light enough for
    # the later sleeve/guide Booleans while remaining visually continuous.
    try:
        curve_obj.data.resolution_u = 8
        curve_obj.data.render_resolution_u = 10
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    obj = convert_curve_to_mesh(context, curve_obj, name)
    if _valid_obj(obj):
        try:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            obj['DSG_frame_visible_sweep'] = 'ORGANIC_AUTO_BEZIER_V1'
            obj['DSG_frame_visible_control_count'] = int(len(controls))
            obj['DSG_frame_visible_source_point_count'] = int(len(points))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def _clamp_vector_length(vec, max_length):
    """Limita una tangente sin cambiar su dirección."""
    v = Vector(vec)
    limit = max(0.0, float(max_length))
    if limit <= 1e-8 or v.length <= limit:
        return v.copy()
    return v.normalized() * limit


def _tcb_value(props, attr, default=0.0):
    """Lee TCB dentro de rangos estables para trayectorias clínicas.

    Bias/continuidad extremos (±1) anulan uno de los segmentos vecinos y crean
    ganchos o U exageradas en la raíz. Se conservan controles útiles, pero se
    limitan automáticamente antes de construir la geometría.
    """
    try:
        value = float(getattr(props, attr, default))
    except Exception:
        value = float(default)
    if attr == 'organic_tcb_bias':
        limit = 0.35
    elif attr == 'organic_tcb_continuity':
        limit = 0.40
    elif attr == 'organic_tcb_tension':
        limit = 0.60
    else:
        limit = 1.0
    return max(-limit, min(limit, value))


def _kochanek_bartels_tangent_pairs(points, tension=0.0, bias=0.0, continuity=0.0,
                                     contact_scale=0.70,
                                     incoming_directions=None,
                                     outgoing_directions=None):
    """Tangentes entrantes/salientes TCB para una ruta abierta.

    Kochanek-Bartels permite controlar la curva sin mover los anchors:
      · Tension: aprieta o relaja el recorrido.
      · Bias: favorece el segmento anterior o el siguiente.
      · Continuity: separa suavemente la tangente de entrada y salida.

    incoming_directions/outgoing_directions son overrides de DIRECCIÓN para los
    puntos de contacto. Su longitud se calcula con el segmento vecino y
    contact_scale, evitando handles enormes y overshoot contra sleeve/frame.
    """
    pts = [Vector(p) for p in points]
    n = len(pts)
    if n < 2:
        return [], []

    t = max(-1.0, min(1.0, float(tension)))
    b = max(-1.0, min(1.0, float(bias)))
    c = max(-1.0, min(1.0, float(continuity)))
    contact_scale = max(0.10, min(1.80, float(contact_scale)))
    incoming_directions = incoming_directions or {}
    outgoing_directions = outgoing_directions or {}

    incoming = [Vector((0.0, 0.0, 0.0)) for _ in range(n)]
    outgoing = [Vector((0.0, 0.0, 0.0)) for _ in range(n)]

    first = pts[1] - pts[0]
    last = pts[-1] - pts[-2]
    incoming[0] = first.copy()
    outgoing[0] = first.copy()
    incoming[-1] = last.copy()
    outgoing[-1] = last.copy()

    one_minus_t = 1.0 - t
    for i in range(1, n - 1):
        d_prev = pts[i] - pts[i - 1]
        d_next = pts[i + 1] - pts[i]

        # Fórmulas originales de Kochanek-Bartels para tangentes independientes.
        outgoing_i = (
            d_prev * (one_minus_t * (1.0 + c) * (1.0 + b) * 0.5) +
            d_next * (one_minus_t * (1.0 - c) * (1.0 - b) * 0.5)
        )
        incoming_i = (
            d_prev * (one_minus_t * (1.0 - c) * (1.0 + b) * 0.5) +
            d_next * (one_minus_t * (1.0 + c) * (1.0 - b) * 0.5)
        )

        # Límite geométrico: previene loops en puntos muy juntos o cambios cerrados.
        min_len = max(0.01, min(d_prev.length, d_next.length))
        max_tangent = min_len * 2.35
        outgoing[i] = _clamp_vector_length(outgoing_i, max_tangent)
        incoming[i] = _clamp_vector_length(incoming_i, max_tangent)

    for idx, direction in incoming_directions.items():
        i = int(idx)
        if i < 0 or i >= n:
            continue
        d = Vector(direction)
        if d.length < 1e-8:
            continue
        neighbour_len = (pts[i] - pts[i - 1]).length if i > 0 else first.length
        incoming[i] = d.normalized() * max(0.02, neighbour_len * contact_scale)

    for idx, direction in outgoing_directions.items():
        i = int(idx)
        if i < 0 or i >= n:
            continue
        d = Vector(direction)
        if d.length < 1e-8:
            continue
        neighbour_len = (pts[i + 1] - pts[i]).length if i < n - 1 else last.length
        outgoing[i] = d.normalized() * max(0.02, neighbour_len * contact_scale)

    return incoming, outgoing


def _hermite_tcb_point(p0, p1, tangent_out, tangent_in, u):
    """Evalúa un segmento Hermite equivalente a un segmento Bezier TCB."""
    u = max(0.0, min(1.0, float(u)))
    u2 = u * u
    u3 = u2 * u
    h00 = 2.0 * u3 - 3.0 * u2 + 1.0
    h10 = u3 - 2.0 * u2 + u
    h01 = -2.0 * u3 + 3.0 * u2
    h11 = u3 - u2
    return Vector(p0) * h00 + Vector(tangent_out) * h10 + Vector(p1) * h01 + Vector(tangent_in) * h11


def build_kochanek_bartels_path(points, props=None, max_spacing=0.35,
                                 min_samples_per_segment=5, max_samples_per_segment=48,
                                 incoming_directions=None, outgoing_directions=None):
    """Ruta abierta densa que atraviesa todos los anchors usando TCB."""
    pts = _remove_near_duplicate_points(points, epsilon=0.01, closed=False)
    if len(pts) < 3:
        return pts

    tension = _tcb_value(props, 'organic_tcb_tension', -0.10) if props else -0.10
    bias = _tcb_value(props, 'organic_tcb_bias', 0.0) if props else 0.0
    continuity = _tcb_value(props, 'organic_tcb_continuity', 0.0) if props else 0.0
    contact_scale = float(getattr(props, 'organic_tcb_contact_scale', 0.70)) if props else 0.70

    incoming, outgoing = _kochanek_bartels_tangent_pairs(
        pts,
        tension=tension,
        bias=bias,
        continuity=continuity,
        contact_scale=contact_scale,
        incoming_directions=incoming_directions,
        outgoing_directions=outgoing_directions,
    )

    spacing = max(0.08, float(max_spacing))
    min_s = max(3, int(min_samples_per_segment))
    max_s = max(min_s, int(max_samples_per_segment))
    out = []
    for i in range(len(pts) - 1):
        chord = (pts[i + 1] - pts[i]).length
        samples = max(min_s, int(math.ceil(chord / spacing)))
        samples = min(max_s, samples)
        for j in range(samples):
            u = j / float(samples)
            p = _hermite_tcb_point(pts[i], pts[i + 1], outgoing[i], incoming[i + 1], u)
            if not out or (p - out[-1]).length > 0.005:
                out.append(p)
    if not out or (pts[-1] - out[-1]).length > 0.005:
        out.append(pts[-1].copy())
    return out


def _ordered_points_from_evaluated_curve(context, curve_obj):
    """Extrae la polilínea evaluada de un Curve Path abierto en orden topológico."""
    if not _valid_obj(curve_obj):
        return []
    eval_obj = None
    mesh = None
    try:
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = curve_obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if mesh is None or len(mesh.vertices) < 2:
            return []

        world = eval_obj.matrix_world
        vertices = [world @ v.co for v in mesh.vertices]
        adjacency = {i: [] for i in range(len(vertices))}
        for edge in mesh.edges:
            a, b = int(edge.vertices[0]), int(edge.vertices[1])
            adjacency[a].append(b)
            adjacency[b].append(a)

        endpoints = [i for i, neighbours in adjacency.items() if len(neighbours) == 1]
        start = endpoints[0] if endpoints else 0
        ordered = []
        previous = None
        current = start
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            ordered.append(vertices[current].copy())
            candidates = [idx for idx in adjacency.get(current, []) if idx != previous and idx not in visited]
            if not candidates:
                break
            # En una spline abierta normal solo hay un candidato. Si Blender
            # crea una bifurcación inesperada elegimos el vecino más próximo.
            nxt = min(candidates, key=lambda idx: (vertices[idx] - vertices[current]).length)
            previous, current = current, nxt
        return _remove_near_duplicate_points(ordered, epsilon=0.005, closed=False)
    except Exception as exc:
        print(f"[DSG] No se pudo evaluar Bezier Path con Hooks: {exc}")
        return []
    finally:
        if eval_obj is not None and mesh is not None:
            try:
                eval_obj.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def build_hooked_tcb_path(context, name, points, props, contact_indices=None,
                          incoming_directions=None, outgoing_directions=None,
                          max_spacing=0.35):
    """Construye un Bezier Path real, fija contactos con Hook y devuelve su eje.

    El objeto Curve y sus empties son temporales: se evalúan para obtener la
    trayectoria y se eliminan antes de construir el tubo sólido. Así la guía no
    acumula controladores, pero el eje usado por el barrido procede realmente de
    un Path Bezier con handles TCB y puntos de contacto anclados por Hook.
    """
    pts = _remove_near_duplicate_points(points, epsilon=0.01, closed=False)
    if len(pts) < 3:
        return pts

    fallback = build_kochanek_bartels_path(
        pts, props=props, max_spacing=max_spacing,
        incoming_directions=incoming_directions,
        outgoing_directions=outgoing_directions,
    )
    if not bool(getattr(props, 'organic_use_path_hooks', True)):
        return fallback

    incoming, outgoing = _kochanek_bartels_tangent_pairs(
        pts,
        tension=_tcb_value(props, 'organic_tcb_tension', -0.10),
        bias=_tcb_value(props, 'organic_tcb_bias', 0.0),
        continuity=_tcb_value(props, 'organic_tcb_continuity', 0.0),
        contact_scale=float(getattr(props, 'organic_tcb_contact_scale', 0.70)),
        incoming_directions=incoming_directions,
        outgoing_directions=outgoing_directions,
    )

    curve_obj = None
    curve_data = None
    hook_objects = []
    try:
        curve_data = bpy.data.curves.new(name + '_PathCurve', type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = max(4, min(32, int(getattr(props, 'organic_path_resolution', 12))))
        curve_data.render_resolution_u = curve_data.resolution_u
        curve_data.fill_mode = 'FULL'
        curve_data.bevel_depth = 0.0
        curve_data.use_fill_caps = False
        try:
            curve_data.twist_smooth = 12
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            bp = spline.bezier_points[i]
            bp.co = p
            bp.handle_left_type = 'FREE'
            bp.handle_right_type = 'FREE'
            bp.handle_left = p - incoming[i] / 3.0
            bp.handle_right = p + outgoing[i] / 3.0
        spline.use_smooth = True
        spline.use_cyclic_u = False

        curve_obj = bpy.data.objects.new(name + '_Path', curve_data)
        link_object(context, curve_obj)

        valid_contacts = sorted(set(int(i) for i in (contact_indices or []) if 0 <= int(i) < len(pts)))
        for order, idx in enumerate(valid_contacts):
            empty = bpy.data.objects.new(f'{name}_Hook_{order:02d}', None)
            empty.empty_display_type = 'SPHERE'
            empty.empty_display_size = 0.22
            empty.location = pts[idx]
            empty.hide_render = True
            empty.hide_select = True
            link_object(context, empty)
            hook_objects.append(empty)

            hook = curve_obj.modifiers.new(f'DSG_PathHook_{order:02d}', 'HOOK')
            hook.object = empty
            # En curvas Bezier cada anchor ocupa tres índices: handle izq., co y handle der.
            hook.vertex_indices_set([idx * 3, idx * 3 + 1, idx * 3 + 2])
            try:
                hook.center = pts[idx]
                hook.matrix_inverse = empty.matrix_world.inverted() @ curve_obj.matrix_world
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        try:
            context.view_layer.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        evaluated = _ordered_points_from_evaluated_curve(context, curve_obj)
        if len(evaluated) >= 3:
            # Blender puede enumerar la malla evaluada desde cualquiera de los
            # extremos. Conservamos siempre el sentido clínico original.
            if (evaluated[-1] - pts[0]).length < (evaluated[0] - pts[0]).length:
                evaluated.reverse()

            endpoint_tol = max(0.05, float(max_spacing) * 0.55)
            endpoints_ok = (
                (evaluated[0] - pts[0]).length <= endpoint_tol and
                (evaluated[-1] - pts[-1]).length <= endpoint_tol
            )
            contacts_ok = all(
                min((p - pts[idx]).length for p in evaluated) <= endpoint_tol
                for idx in valid_contacts
            )
            if endpoints_ok and contacts_ok:
                return evaluated
            print('[DSG] Evaluated Path did not preserve its Hooks; safe mathematical TCB is used')
        return fallback
    except Exception as exc:
        print(f"[DSG] Path + Hook TCB skipped; mathematical TCB is used: {exc}")
        return fallback
    finally:
        if curve_obj is not None:
            safe_remove_object(curve_obj)
        if curve_data is not None:
            try:
                if curve_data.users == 0:
                    bpy.data.curves.remove(curve_data)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        for empty in hook_objects:
            safe_remove_object(empty)

def simplify_points_by_distance(points, min_dist=0.35):
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for p in pts[1:-1]:
        if (p - out[-1]).length >= min_dist:
            out.append(p)
    out.append(pts[-1])
    return out


def project_point_to_line(point, line_origin, line_dir):
    line_dir = Vector(line_dir)
    if line_dir.length < 1e-8:
        return Vector(line_origin)
    line_dir = line_dir.normalized()
    return Vector(line_origin) + line_dir * (Vector(point) - Vector(line_origin)).dot(line_dir)


def get_sleeve_entry_data(anchor_point, props, implant_obj=None):
    center = get_sleeve_center_world(props, implant_obj)
    axis = get_sleeve_axis_world(props, implant_obj)
    if center is None:
        return None, None, None, None
    anchor = Vector(anchor_point)

    # Keep the radial orientation selected by the user, but place the actual
    # channel centre in the superior/coronal third of the sleeve.
    clicked_axis_point = project_point_to_line(anchor, center, axis)
    radial = anchor - clicked_axis_point
    if radial.length < 1e-6:
        fallback = axis.cross(Vector((1, 0, 0)))
        if fallback.length < 1e-6:
            fallback = axis.cross(Vector((0, 1, 0)))
        radial = fallback.normalized()
    else:
        radial = radial.normalized()

    half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    local_z = get_irrigation_coronal_sleeve_z_local(
        props, implant_obj=implant_obj, half_h=half_h)
    axis_point = Vector(center) + Vector(axis).normalized() * float(local_z)
    return anchor, radial, axis_point, axis


def get_irrigation_taper_length(props):
    """Length de la reducción progresiva del canal interno.

    0 = automático: se usa la altura del sleeve. La reducción se mide siguiendo
    la curva real del tubo de irrigación, no como un cono recto independiente.
    """
    try:
        raw = float(getattr(props, 'irr_taper_length', 0.0))
    except Exception:
        raw = 0.0
    if raw > 0.01:
        return max(0.25, raw)
    sleeve_h = float(getattr(props, 'sleeve_height', 8.0))
    return max(0.25, sleeve_h)


def get_sleeve_wall_geometry(anchor_point, props, implant_obj=None, exit_overshoot=None):
    """Geometría radial real de la pared del sleeve para irrigación.

    El fallo de la versión con sleeve protegido era que el tubo exterior usaba
    `irr_sleeve_overlap` como distancia fija. Con pared de 1.5 mm y solape 1.2 mm,
    el tubo podía quedarse dentro de la pared sin llegar al lumen interno del
    sleeve. Esta función calcula el radio interno/externo real y fuerza que el
    tubo y el cutter lleguen hasta el lumen central, con una micro-sobresalida
    controlada para no crear un conducto axial hacia el implante.
    """
    anchor, radial, axis_entry, axis = get_sleeve_entry_data(anchor_point, props, implant_obj)
    if anchor is None or radial is None or axis_entry is None:
        return None

    radial = Vector(radial)
    if radial.length < 1e-8:
        return None
    radial.normalize()

    anchor = Vector(anchor)
    axis_entry = Vector(axis_entry)
    current_r = max(0.0, (anchor - axis_entry).dot(radial))

    inner_r = max(
        0.05,
        float(getattr(props, 'implant_diameter', 4.0)) * 0.5 +
        float(getattr(props, 'fresa_offset', 0.10))
    )
    outer_r = inner_r + max(0.05, float(getattr(props, 'sleeve_wall', 1.5)))

    # Si el clic quedó algo metido por remesh/raycast, usamos el radio teórico
    # exterior para garantizar pared completa. Si quedó fuera, respetamos el clic.
    surface_r = max(current_r, outer_r)
    surface_point = axis_entry + radial * surface_r
    inner_wall_point = axis_entry + radial * inner_r

    if exit_overshoot is None:
        exit_overshoot = float(getattr(props, 'irr_wall_exit_overshoot', 0.18))
    exit_overshoot = max(0.04, min(float(exit_overshoot), 0.60, inner_r * 0.45))
    lumen_stop_point = axis_entry + radial * max(0.0, inner_r - exit_overshoot)

    wall_depth = max(0.0, surface_r - inner_r)
    required_penetration = max(0.0, surface_r - (inner_r - exit_overshoot))

    return {
        'anchor': anchor,
        'radial': radial,
        'axis': axis,
        'axis_entry': axis_entry,
        'inner_r': inner_r,
        'outer_r': outer_r,
        'surface_r': surface_r,
        'surface_point': surface_point,
        'inner_wall_point': inner_wall_point,
        'lumen_stop_point': lumen_stop_point,
        'wall_depth': wall_depth,
        'required_penetration': required_penetration,
    }


def build_irrigation_outer_path(points, props, implant_obj=None, entry_mode='full'):
    """Trayectoria exterior imperativa del tubo de irrigación.

    La entrada no se detiene en la pared del sleeve. El primer tramo atraviesa
    radialmente toda la pared y termina dentro del lumen axial. Las caras planas
    no limitan esta construcción; se restauran después de fusionar el tubo.
    """
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return pts

    tube_r = (
        max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5) +
        max(0.05, float(getattr(props, 'irr_wall_thickness', 1.5)))
    )
    port = get_sleeve_lateral_port_geometry(
        pts[0], props, implant_obj=implant_obj, outer_tube_radius=tube_r)
    if not port:
        geo = get_sleeve_wall_geometry(pts[0], props, implant_obj)
        if not geo:
            return pts
        radial = Vector(geo['radial']).normalized()
        axis_entry = Vector(geo['axis_entry'])
        inner_r = float(geo['inner_r'])
        surface_point = Vector(geo['surface_point'])
        if _irrigation_is_direct_channel_mode(props):
            direct_tip = get_direct_irrigation_lumen_tip(surface_point, props, implant_obj=implant_obj)
            deep_point = direct_tip if direct_tip is not None else axis_entry + radial * max(0.0, inner_r - _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r))
        else:
            penetration = max(0.70, min(inner_r * 0.72, tube_r * 0.58))
            deep_point = axis_entry + radial * max(0.0, inner_r - penetration)
        launch_point = surface_point + radial * max(
            0.35, float(getattr(props, 'irr_entry_length', 1.2)))
        out = [deep_point, surface_point, launch_point]
    else:
        radial = Vector(port['radial']).normalized()
        axis = Vector(port['axis']).normalized()
        axis_entry = Vector(port['center']) + axis * float(port['safe_z'])
        inner_r = float(port['inner_r'])
        if _irrigation_is_direct_channel_mode(props):
            direct_tip = get_direct_irrigation_lumen_tip(Vector(port['face_point']), props, implant_obj=implant_obj)
            deep_point = direct_tip if direct_tip is not None else axis_entry + radial * max(0.0, inner_r - _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r))
        else:
            penetration = max(0.70, min(inner_r * 0.72, tube_r * 0.58))
            deep_r = max(0.0, inner_r - penetration)
            deep_point = axis_entry + radial * deep_r

        mode = str(entry_mode or 'full').lower()
        if mode == 'external':
            out = [Vector(port['external_anchor']), Vector(port['launch_point'])]
        else:
            # La secuencia radial garantiza una intersección volumétrica real:
            # lumen profundo -> pared interna -> cara lateral -> exterior.
            out = [
                deep_point,
                Vector(port['internal_overlap_point']),
                Vector(port['face_point']),
                Vector(port['external_anchor']),
                Vector(port['launch_point']),
            ]

    for p in pts[1:]:
        p = Vector(p)
        if (p - out[-1]).length > 0.02:
            out.append(p.copy())
    return _remove_near_duplicate_points(out, epsilon=0.02, closed=False)


def get_irrigation_funnel_geometry(points, props, implant_obj=None):
    """Geometría del lumen con penetración radial imperativa.

    El extremo interno queda claramente dentro del lumen axial del sleeve. No se
    recorta contra las caras planas; esas caras se reconstruyen tras la unión.
    """
    pts = [Vector(p) for p in points]
    if not pts:
        return None

    port = get_sleeve_lateral_port_geometry(pts[0], props, implant_obj)
    if port:
        radial = Vector(port['radial']).normalized()
        axis = Vector(port['axis']).normalized()
        axis_entry = Vector(port['center']) + axis * float(port['safe_z'])
        inner_r = float(port['inner_r'])
        ring = get_irrigation_internal_ring_geometry(pts[0], props, implant_obj)
        if ring:
            inner_tip = Vector(ring['inlet_point'])
        elif _irrigation_is_direct_channel_mode(props):
            direct_tip = get_direct_irrigation_lumen_tip(Vector(port['face_point']), props, implant_obj=implant_obj)
            inner_tip = direct_tip if direct_tip is not None else axis_entry + radial * max(0.0, inner_r - _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r))
        else:
            requested = float(getattr(props, 'irr_funnel_depth', 0.0))
            penetration = requested if requested > 0.0 else max(0.70, inner_r * 0.72)
            penetration = min(max(0.25, penetration), max(0.30, inner_r * 0.92))
            inner_tip = axis_entry + radial * max(0.0, inner_r - penetration)
        face_point = Vector(port['face_point'])
        return {
            'anchor': face_point.copy(),
            'radial': radial,
            'entry_direction': radial.copy(),
            'outlet_center': face_point.copy(),
            'inner_tip': inner_tip,
            'through_depth': (face_point - inner_tip).length,
            'taper_len': get_irrigation_taper_length(props),
            'wall_geometry': port,
            'apical_port': False,
            'imperative_entry': True,
        }

    geo = get_sleeve_wall_geometry(pts[0], props, implant_obj)
    if not geo:
        return None
    radial = Vector(geo['radial']).normalized()
    inner_r = float(geo['inner_r'])
    ring = get_irrigation_internal_ring_geometry(pts[0], props, implant_obj)
    if ring:
        inner_tip = Vector(ring['inlet_point'])
    elif _irrigation_is_direct_channel_mode(props):
        direct_tip = get_direct_irrigation_lumen_tip(Vector(geo['surface_point']), props, implant_obj=implant_obj)
        inner_tip = direct_tip if direct_tip is not None else Vector(geo['axis_entry']) + radial * max(0.0, inner_r - _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r))
    else:
        requested = float(getattr(props, 'irr_funnel_depth', 0.0))
        penetration = requested if requested > 0.0 else max(0.70, inner_r * 0.72)
        penetration = min(max(0.25, penetration), max(0.30, inner_r * 0.92))
        inner_tip = Vector(geo['axis_entry']) + radial * max(0.0, inner_r - penetration)
    anchor = Vector(geo['surface_point'])
    return {
        'anchor': anchor,
        'radial': radial,
        'outlet_center': anchor.copy(),
        'inner_tip': inner_tip,
        'through_depth': (anchor - inner_tip).length,
        'taper_len': get_irrigation_taper_length(props),
        'wall_geometry': geo,
        'imperative_entry': True,
    }


def _irrigation_outward_centerline(points, props, implant_obj=None, smooth=True):
    """Devuelve la línea central externa desde el sleeve hacia fuera.

    Siempre empieza exactamente en el anchor del sleeve y después usa el mismo
    recorrido que el tubo exterior. Es la clave para que el lumen quede centrado
    dentro del tubo visible, incluso si el usuario dibuja curvas o ángulos.
    """
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return pts

    geom = get_irrigation_funnel_geometry(pts, props, implant_obj)
    if geom is None:
        return pts

    anchor = geom['anchor']
    outer_path = build_irrigation_outer_path(pts, props, implant_obj)

    out = [anchor.copy()]
    found_anchor = False
    for p in outer_path:
        p = Vector(p)
        if not found_anchor:
            if (p - anchor).length <= 0.05:
                found_anchor = True
            continue
        if (p - out[-1]).length > 0.02:
            out.append(p.copy())

    if len(out) < 2:
        entry_dir = Vector(geom.get('entry_direction', geom['radial'])).normalized()
        out.append(anchor + entry_dir * max(0.8, float(getattr(props, 'irr_entry_length', 1.2))))
        for p in pts[1:]:
            p = Vector(p)
            if (p - out[-1]).length > 0.02:
                out.append(p.copy())

    if smooth and len(out) >= 3:
        out = simplify_points_by_distance(out, min_dist=0.12)
        radial_dir = Vector(geom.get('entry_direction', geom['radial'])).normalized()
        out = build_kochanek_bartels_path(
            out,
            props=props,
            max_spacing=max(0.14, min(IRR_LUMEN_SAMPLE_STEP_MM_FIXED * 0.70, 0.45)),
            incoming_directions={0: radial_dir},
            outgoing_directions={0: radial_dir},
        )
        # El anchor clínico nunca se desplaza aunque cambien T/B/C.
        out[0] = anchor.copy()

    return out


def build_irrigation_lumen_path(points, props, implant_obj=None):
    """Trayectoria del canal interno centrada en el tubo exterior."""
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return pts
    return _irrigation_outward_centerline(pts, props, implant_obj, smooth=True)


def _smootherstep01(t):
    """Interpolación aún más orgánica para cambios de diámetro."""
    t = max(0.0, min(1.0, float(t)))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _append_sample(samples, point, radius, min_dist=0.01):
    """Añade una muestra de barrido evitando duplicados exactos."""
    p = Vector(point)
    r = max(0.01, float(radius))
    if samples:
        lp, lr = samples[-1]
        if (p - lp).length < min_dist:
            # Si el punto es prácticamente el mismo, conservamos el radio mayor
            # para evitar anillos degenerados.
            samples[-1] = (lp, max(lr, r))
            return
    samples.append((p, r))


def _build_transport_frames(points):
    """Frames de rotación mínima para barridos tubulares.

    El método anterior reproyectaba el eje transversal en cada muestra. En
    curvas cerradas o con cambios rápidos podía acumular un giro desigual. Aquí
    se transporta el frame mediante la rotación mínima entre tangentes
    consecutivas y se reortogonaliza solo para controlar el error numérico.
    """
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
            if before.length > 1.0e-8:
                before.normalize()
            if after.length > 1.0e-8:
                after.normalize()
            tangent = before + after
            if tangent.length < 1.0e-8:
                tangent = pts[index + 1] - pts[index - 1]
        if tangent.length < 1.0e-8:
            tangent = Vector((0.0, 0.0, 1.0))
        tangents.append(tangent.normalized())

    first_tangent = tangents[0]
    reference = Vector((0.0, 0.0, 1.0))
    if abs(first_tangent.dot(reference)) > 0.88:
        reference = Vector((0.0, 1.0, 0.0))
    axis_u = first_tangent.cross(reference)
    if axis_u.length < 1.0e-8:
        axis_u = Vector((1.0, 0.0, 0.0))
    axis_u.normalize()

    frames = []
    previous_tangent = first_tangent.copy()
    previous_u = axis_u.copy()
    for index, tangent in enumerate(tangents):
        if index == 0:
            transported_u = previous_u.copy()
        else:
            transported_u = previous_u.copy()
            try:
                rotation = previous_tangent.rotation_difference(tangent)
                transported_u = rotation @ transported_u
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        transported_u -= tangent * transported_u.dot(tangent)
        if transported_u.length < 1.0e-8:
            fallback = Vector((0.0, 0.0, 1.0))
            if abs(tangent.dot(fallback)) > 0.88:
                fallback = Vector((0.0, 1.0, 0.0))
            transported_u = tangent.cross(fallback)
        transported_u.normalize()

        # Evita una inversión numérica de 180 grados entre aros consecutivos.
        if index > 0 and transported_u.dot(previous_u) < 0.0:
            transported_u.negate()

        axis_v = tangent.cross(transported_u)
        if axis_v.length < 1.0e-8:
            axis_v = Vector((0.0, 1.0, 0.0))
        axis_v.normalize()
        frames.append((transported_u.copy(), axis_v.copy(), tangent.copy()))
        previous_tangent = tangent.copy()
        previous_u = transported_u.copy()
    return frames


def append_variable_radius_tube_to_bmesh(bm, samples, segments=32, cap_start=True, cap_end=True):
    """Añade un tubo continuo de radio variable en coordenadas mundo.

    A diferencia de varios conos/cilindros cerrados pegados entre sí, este crea
    una sola piel conectada. Es justo lo que necesitamos para que el canal y el
    cono del embudo formen una transición orgánica y no una junta dura.
    """
    clean = []
    for item in samples:
        if not item or len(item) != 2:
            continue
        p, r = item
        p = Vector(p)
        r = max(0.01, float(r))
        if clean and (p - clean[-1][0]).length < 0.01:
            clean[-1] = (clean[-1][0], max(clean[-1][1], r))
        else:
            clean.append((p, r))

    if len(clean) < 2:
        return False

    points = [p for p, _ in clean]
    radii = [r for _, r in clean]
    frames = _build_transport_frames(points)
    if len(frames) != len(points):
        return False

    seg = max(12, int(segments))
    rings = []
    for (p, r), (u, v, _t) in zip(clean, frames):
        ring = []
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            ring.append(bm.verts.new(p + u * math.cos(a) * r + v * math.sin(a) * r))
        rings.append(ring)

    bm.verts.ensure_lookup_table()
    for j in range(len(rings) - 1):
        r0 = rings[j]
        r1 = rings[j + 1]
        for i in range(seg):
            ni = (i + 1) % seg
            try:
                bm.faces.new([r0[i], r0[ni], r1[ni], r1[i]])
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    if cap_start:
        try:
            bm.faces.new(list(reversed(rings[0])))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if cap_end:
        try:
            bm.faces.new(rings[-1])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def _resample_polyline_with_distances(points, max_step=0.35):
    """Remuestrea una polilínea manteniendo distancia acumulada."""
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return [(pts[0], 0.0)] if pts else []

    max_step = max(0.05, float(max_step))
    out = [(pts[0].copy(), 0.0)]
    acc = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        seg = b - a
        length = seg.length
        if length < 1e-8:
            continue
        steps = max(1, int(math.ceil(length / max_step)))
        for i in range(1, steps + 1):
            t = i / steps
            p = a.lerp(b, t)
            out.append((p, acc + length * t))
        acc += length
    return out


def build_irrigation_funnel_samples(points, props, implant_obj=None, include_channel_tail=False):
    """Muestras del lumen de irrigación como UN SOLO tubo tapered.

    Esta es la lógica v5.0.8: no hay cono + cilindro. El cutter interno es un
    tubo continuo de radio variable que sigue la línea central real del tubo de
    irrigación. Cerca del sleeve tiene el Ø de salida; progresivamente se abre
    hasta el Ø del canal interno siguiendo curvas y ángulos del recorrido.
    """
    pts = [Vector(p) for p in points]
    geom = get_irrigation_funnel_geometry(pts, props, implant_obj)
    if geom is None:
        return []

    inner_r = max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5)
    outlet_d = max(0.05, float(getattr(props, 'irr_funnel_outer_diameter', 1.0)))
    outlet_r = max(0.025, outlet_d * 0.5)
    outlet_r = min(outlet_r, inner_r)
    taper_len = max(0.25, float(geom.get('taper_len', get_irrigation_taper_length(props))))

    # 1) Línea central exterior, centrada en el tubo real y extendida al final
    # para garantizar que el boolean atraviese completamente el extremo libre.
    outward = _irrigation_outward_centerline(pts, props, implant_obj, smooth=True)
    outward = extend_polyline_ends(
        outward,
        0.0,
        float(getattr(props, 'irr_cut_overshoot', 1.0)) if include_channel_tail else 0.0,
    )
    if len(outward) < 2:
        return []

    # 2) Boquilla fina hacia el interior del sleeve + anchor exacto + recorrido.
    centerline = [geom['inner_tip'].copy()]
    for p in outward:
        p = Vector(p)
        if (p - centerline[-1]).length > 0.02:
            centerline.append(p.copy())

    # 3) Remuestreo eficiente. Antes se usaba un paso muy denso fijo
    # (≈0.35 mm) y eso generaba demasiados anillos para el booleano. Ahora el
    # paso es configurable: más alto = cutter mucho más ligero.
    raw_step = IRR_LUMEN_SAMPLE_STEP_MM_FIXED
    if raw_step <= 0.0:
        raw_step = min(inner_r * 0.42, 0.55)
    step = max(0.15, min(raw_step, 1.50))
    raw_samples = _resample_polyline_with_distances(centerline, max_step=step)

    # Distancia acumulada del anchor dentro de la centerline: el primer segmento
    # es inner_tip → anchor. Como outward[0] se fuerza al anchor, lo podemos medir
    # directamente.
    anchor_offset = (geom['anchor'] - geom['inner_tip']).length

    samples = []
    for p, d in raw_samples:
        sdist = d - anchor_offset
        if sdist <= 0.0:
            r = outlet_r
        elif sdist >= taper_len:
            r = inner_r
        else:
            s = _smootherstep01(sdist / taper_len)
            r = outlet_r + (inner_r - outlet_r) * s
        _append_sample(samples, p, r, min_dist=0.005)

    return samples


def build_variable_radius_tube_object(context, name, samples, bevel_resolution=8, show_wire=True, subdiv_levels=0):
    """Crea un objeto mesh cerrado desde muestras de centro/radio.

    v5.0.7: opcionalmente aplica Subdivision Surface al cutter antes de usarlo
    para el booleano. Esto suaviza la unión boquilla→cono→canal sin separar
    las piezas ni crear booleanos independientes.
    """
    if not samples or len(samples) < 2:
        return None
    safe_remove_by_name(name)
    bm = bmesh.new()
    # Para cutters booleanos no hace falta una sección exageradamente densa.
    # 8 en UI => 16 lados reales, suficiente para un canal de irrigación y mucho
    # más ligero que los 24 lados anteriores.
    seg = max(12, int(bevel_resolution) * 2)
    ok = append_variable_radius_tube_to_bmesh(bm, samples, segments=seg, cap_start=True, cap_end=True)
    if (not ok) or len(bm.verts) == 0:
        bm.free()
        return None
    try:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name + '_Mesh')
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.display_type = 'WIRE' if show_wire else 'SOLID'
    obj.show_in_front = True
    try:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # v5.0.7 — Subdivision Surface real sobre el cutter del lumen.
    # Se aplica ANTES del booleano para que el hueco final de la guía quede
    # más orgánico, sobre todo en la transición cono/canal.
    levels = max(0, min(2, int(subdiv_levels or 0)))
    if levels > 0:
        try:
            sub = obj.modifiers.new('DSG_LumenOrganicSubdivide', 'SUBSURF')
            sub.levels = levels
            sub.render_levels = levels
            try:
                sub.subdivision_type = 'CATMULL_CLARK'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            apply_modifier_direct(context, obj, sub.name)
            for poly in obj.data.polygons:
                poly.use_smooth = True
        except Exception as e:
            print(f"[DSG] Could not apply subdivision to the irrigation lumen: {e}")

    return obj


def build_irrigation_complete_lumen_cutter(context, points, props, implant_obj=None, name='DSG_IrrSmoothCut'):
    """Cutter único tapered: salida fina → reducción progresiva → canal.

    El lumen sigue el centro del tubo de irrigación dibujado. No se construye
    como cono + cilindro, sino como una sola piel de radio variable.
    """
    samples = build_irrigation_funnel_samples(points, props, implant_obj, include_channel_tail=True)
    return build_variable_radius_tube_object(
        context,
        name,
        samples,
        bevel_resolution=getattr(props, 'irr_bevel_resolution', 8),
        show_wire=True,
        subdiv_levels=getattr(props, 'irr_lumen_subdivision', 1),
    )


def build_irrigation_constant_lumen_samples(points, props, implant_obj=None):
    """Muestras de lumen de radio constante para el modo sin embudo."""
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return []

    inner_r = max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5)
    lumen_pts = build_irrigation_lumen_path(pts, props, implant_obj)
    lumen_pts = extend_polyline_ends(
        lumen_pts,
        min(0.12, max(0.02, float(getattr(props, 'irr_cut_overshoot', 1.0)) * 0.08)),
        float(getattr(props, 'irr_cut_overshoot', 1.0)),
    )
    if len(lumen_pts) < 2:
        return []

    raw_step = IRR_LUMEN_SAMPLE_STEP_MM_FIXED
    if raw_step <= 0.0:
        raw_step = min(inner_r * 0.42, 0.55)
    step = max(0.15, min(raw_step, 1.50))
    return [(p, inner_r) for p, _d in _resample_polyline_with_distances(lumen_pts, max_step=step)]


# Removed dead legacy implementation: _legacy_build_irrigation_combined_lumen_cutter_v1 (no production references in DSG 8.9 audit).


def create_bezier_curve_object(context, name, points, bevel_radius=1.0, bevel_resolution=10, cyclic=False):
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return None

    # Si la curva es cíclica, no conviene duplicar el primer punto al final:
    # un segmento cero puede generar pinzamientos en el frame.
    if cyclic and len(pts) > 2 and (pts[0] - pts[-1]).length < 0.01:
        pts.pop()

    curve_data = bpy.data.curves.new(name + '_Curve', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 24
    curve_data.fill_mode = 'FULL'
    curve_data.bevel_depth = float(bevel_radius)
    curve_data.bevel_resolution = int(bevel_resolution)
    curve_data.use_fill_caps = True

    spline = curve_data.splines.new('BEZIER')
    spline.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = spline.bezier_points[i]
        bp.co = p
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
    spline.use_smooth = True
    try:
        spline.use_cyclic_u = bool(cyclic)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    obj = bpy.data.objects.new(name, curve_data)
    link_object(context, obj)
    return obj


def convert_curve_to_mesh(context, curve_obj, out_name):
    if not _valid_obj(curve_obj):
        return None

    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = curve_obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(obj_eval, preserve_all_data_layers=False, depsgraph=depsgraph)
    mesh.name = out_name + '_Mesh'
    obj = bpy.data.objects.new(out_name, mesh)
    obj.matrix_world = curve_obj.matrix_world.copy()
    link_object(context, obj)
    safe_remove_object(curve_obj)
    return obj

def _distance_along_polyline_to_nearest_point(path, target):
    """Distancia acumulada aproximada hasta el punto de la ruta más cercano."""
    pts = [Vector(p) for p in path]
    if not pts:
        return 0.0
    target = Vector(target)
    best_d = 0.0
    best_err = float('inf')
    acc = 0.0
    for i, p in enumerate(pts):
        err = (p - target).length
        if err < best_err:
            best_err = err
            best_d = acc
        if i < len(pts) - 1:
            acc += (pts[i + 1] - p).length
    return best_d


def build_organic_tube_mesh(context, points, radius, name='DSG_OrganicTube', bevel_resolution=10,
                            smooth_iters=2, simplify=True, cyclic=False):
    pts = [Vector(p) for p in points]
    if simplify:
        pts = simplify_points_by_distance(pts, min_dist=max(radius * 0.35, 0.2))
    pts = smooth_polyline_chaikin(pts, iterations=max(0, int(smooth_iters)))
    if len(pts) < 2:
        return None
    curve_obj = create_bezier_curve_object(
        context,
        name,
        pts,
        bevel_radius=radius,
        bevel_resolution=bevel_resolution,
        cyclic=cyclic,
    )
    if not curve_obj:
        return None
    return convert_curve_to_mesh(context, curve_obj, name)


def get_irrigation_junction_outer_radius(props, body_outer_radius):
    """Radio del cuello que realmente atraviesa la pared lateral del sleeve.

    El tubo principal puede tener Ø exterior grande (p. ej. 7 mm), pero no debe
    intersectar directamente las tapas del sleeve. En el contacto se usa el
    radio tapered de la boquilla y se limita por la altura lateral disponible.
    """
    body_r = max(0.05, float(body_outer_radius))
    wall_t = max(0.05, float(getattr(props, 'irr_wall_thickness', 1.5)))
    outlet_d = max(0.05, float(getattr(props, 'irr_funnel_outer_diameter', 1.0)))
    outlet_inner_r = min(
        max(0.025, outlet_d * 0.5),
        max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5),
    )
    tapered_r = min(body_r, max(0.10, outlet_inner_r + wall_t))

    half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    _radial_margin, _depth, _axial_margin, half_guard = _sleeve_flat_face_guard_values(props)
    max_lateral_r = max(0.20, half_h - half_guard - 0.18)

    # El collar debe ser ligeramente mayor que el primer tramo del tubo. Si los
    # dos radios son idénticos, aparecen caras cilíndricas coincidentes durante
    # el solape y EXACT puede producir bordes no-manifold. La diferencia crea
    # una intersección volumétrica real y determinista.
    collar_r = tapered_r + max(0.10, tapered_r * 0.07)
    return max(0.20, min(collar_r, max_lateral_r))


def build_irrigation_radial_collar(context, anchor_point, props, implant_obj,
                                    body_outer_radius, name='DSG_IrrRadialCollar',
                                    variant=0):
    """Crea un collar cónico radial robusto entre el sleeve y el tubo.

    El antiguo cilindro tenía un disco interno del mismo diámetro que el cuello.
    Ese disco podía cortar la superficie facetada del sleeve de forma casi
    tangencial y dejar unos pocos bordes abiertos. Aquí el extremo interno es más
    estrecho, queda completamente enterrado en la pared y el extremo externo se
    ensancha de forma gradual.

    ``variant`` cambia discretamente profundidad, segmentos y desplazamiento
    axial. Las variantes se usan solo si EXACT rechaza la primera geometría.
    """
    variant = max(0, min(2, int(variant)))
    junction_r = get_irrigation_junction_outer_radius(props, body_outer_radius)
    port = get_sleeve_lateral_port_geometry(
        anchor_point, props, implant_obj=implant_obj,
        outer_tube_radius=junction_r,
    )
    if not port:
        return None, None

    radial = Vector(port['radial'])
    sleeve_axis = Vector(port['axis'])
    if radial.length < 1e-8 or sleeve_axis.length < 1e-8:
        return None, None
    radial.normalize()
    sleeve_axis.normalize()

    # Microdesalineación controlada: evita que los anillos del collar coincidan
    # exactamente con loops del sleeve, sin alterar clínicamente la posición.
    axial_jitter = (0.0, 0.035, -0.045)[variant]
    axis_entry = (
        Vector(port['center'])
        + sleeve_axis * (float(port['safe_z']) + axial_jitter)
    )

    inner_r = float(port['inner_r'])
    outer_r = float(port['outer_r'])
    wall = max(0.05, float(port['wall']))

    inner_scale = (0.66, 0.54, 0.46)[variant]
    inner_cap_r = max(0.18, min(junction_r * inner_scale, junction_r - 0.12))

    # El disco interno debe quedar íntegramente dentro del cilindro exterior del
    # sleeve. Esta cota considera también su extensión tangencial.
    outer_safe = max(inner_r + 0.08, outer_r - (0.08 + 0.02 * variant))
    square = max(0.0, outer_safe * outer_safe - inner_cap_r * inner_cap_r)
    max_start_for_full_cap = math.sqrt(square) if square > 0.0 else inner_r + 0.06

    desired_embed = (wall * 0.22, wall * 0.15, wall * 0.10)[variant]
    desired_start = inner_r + max(0.07, desired_embed)
    start_r = min(desired_start, max_start_for_full_cap)
    start_r = max(inner_r + 0.045, min(start_r, outer_r - 0.12))

    external_r = (Vector(port['external_anchor']) - axis_entry).dot(radial)
    launch_r = (Vector(port['launch_point']) - axis_entry).dot(radial)
    extra_overlap = (1.30, 1.48, 1.62)[variant]
    end_r = max(
        external_r + junction_r * extra_overlap,
        external_r + 0.55 + 0.10 * variant,
        (external_r + launch_r) * 0.5,
    )

    p0 = axis_entry + radial * start_r
    p1 = axis_entry + radial * end_r
    depth = (p1 - p0).length
    if depth <= 0.10:
        return None, None

    segments = (47, 43, 53)[variant]
    mesh = make_frustum_mesh(
        name + '_Mesh',
        radius_inner=inner_cap_r,
        radius_outer=junction_r,
        depth=depth,
        verts=segments,
    )
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.location = (p0 + p1) * 0.5

    # rotation_difference fija el eje Z. Un pequeño roll adicional rompe otra
    # posible coincidencia entre vértices del collar y edges del sleeve.
    q_align = Vector((0.0, 0.0, 1.0)).rotation_difference(radial)
    q_roll = Quaternion(radial, math.radians((3.7, 7.1, 11.3)[variant]))
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = q_roll @ q_align
    obj.display_type = 'SOLID'
    try:
        for poly in obj.data.polygons:
            poly.use_smooth = True
        obj['DSG_collar_variant'] = variant
        obj['DSG_collar_inner_radius'] = float(inner_cap_r)
        obj['DSG_collar_outer_radius'] = float(junction_r)
        obj['DSG_collar_segments'] = int(segments)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj, {
        'port': port,
        'junction_radius': junction_r,
        'inner_cap_radius': inner_cap_r,
        'start_point': p0,
        'end_point': p1,
        'variant': variant,
        'segments': segments,
    }


def apply_difference_exact_transactional(context, base_obj, cutter_obj,
                                         mod_name, require_solid=True):
    """Aplica DIFFERENCE EXACT con rollback local y diagnóstico manifold."""
    if not _valid_obj(base_obj) or not _valid_obj(cutter_obj):
        return base_obj, False, 'invalid objects'
    backup = base_obj.data.copy()
    cutter_name = _safe_object_name(cutter_obj)
    mod = base_obj.modifiers.new(mod_name, 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter_obj
    ok, solver = apply_boolean_modifier_smart(
        context, base_obj, mod, obj_cutter=cutter_obj,
        prefer_fast=False, force_robust=True, cleanup_cutter=True)
    if not ok:
        _restore_object_mesh_copy(base_obj, backup)
        if cutter_name:
            safe_remove_by_name(cutter_name)
        return base_obj, False, 'Boolean DIFFERENCE EXACT no pudo aplicarse'

    report = get_mesh_solid_report(base_obj)
    if require_solid and report.get('checked') and not report.get('solid'):
        _restore_object_mesh_copy(base_obj, backup)
        if cutter_name:
            safe_remove_by_name(cutter_name)
        return base_obj, False, (
            f'Non-solid DIFFERENCE: edges={report.get("bad_edges")}, '
            f'caras degeneradas={report.get("degenerate_faces")}')

    if cutter_name:
        safe_remove_by_name(cutter_name)
    try:
        if backup.users == 0:
            bpy.data.meshes.remove(backup)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return base_obj, True, f'DIFFERENCE {solver or "EXACT"} OK'


def force_voxel_union_imperative(context, guide_obj, addition_obj, props,
                                  out_name=GUIDE_NAME,
                                  mod_name='DSG_IrrigationImperativeVoxelUnion'):
    """Fusión forzada: Join de shells + Voxel Remesh fino.

    Solo se usa cuando UNION EXACT no entrega un sólido. La prioridad de esta
    ruta es que el tubo atraviese la guía y llegue al lumen. La geometría exacta
    del sleeve se reconstruye inmediatamente después.
    """
    if not _valid_obj(guide_obj) or not _valid_obj(addition_obj):
        return None, False, 'invalid objects for forced fusion'

    backup = guide_obj.data.copy()
    joined = join_objects(context, [guide_obj, addition_obj], out_name)
    if not _valid_obj(joined):
        _restore_object_mesh_copy(guide_obj, backup)
        return None, False, 'Object Join failed before Voxel Remesh'

    try:
        requested = float(getattr(props, 'continuous_fusion_voxel', 0.08))
    except Exception:
        requested = 0.08
    voxel = max(0.04, min(0.10, requested))

    remesh = joined.modifiers.new(mod_name, 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = voxel
    remesh.use_smooth_shade = True
    if not apply_modifier_direct(context, joined, remesh.name):
        _restore_object_mesh_copy(joined, backup)
        return None, False, f'Mandatory Voxel Remesh failed (voxel={voxel:.3f} mm)'

    report = get_mesh_solid_report(joined, max_polygons=800000)
    if report.get('checked') and not report.get('solid'):
        make_mesh_manifold_bmesh(joined, merge_dist=max(0.0005, voxel * 0.015), fill_holes=True)
        report = get_mesh_solid_report(joined, max_polygons=800000)
    if report.get('checked') and not report.get('solid'):
        _restore_object_mesh_copy(joined, backup)
        return None, False, (
            f'Non-solid Voxel Remesh: edges={report.get("bad_edges")}, '
            f'caras degeneradas={report.get("degenerate_faces")}')

    joined.name = out_name
    try:
        joined.data.name = out_name + '_Mesh'
        if backup.users == 0:
            bpy.data.meshes.remove(backup)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return joined, True, f'Join + Voxel Remesh imperativo ({voxel:.3f} mm)'


def build_pristine_sleeve_shell(context, props, implant_obj,
                                name='DSG_IrrigationSleeveRestore'):
    """Reconstruye el cilindro hueco exacto del sleeve asociado."""
    if not is_valid_implant_obj(implant_obj):
        return None
    inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    height = max(0.10, float(getattr(props, 'sleeve_height', 7.0)))
    mx = get_sleeve_matrix_world(props, implant_obj)

    outer = bpy.data.objects.new(
        name, make_cylinder_mesh(name + '_OuterMesh', outer_r, height, 32))
    outer.matrix_world = mx
    link_object(context, outer)
    inner_name = name + '_InnerCut'
    inner = bpy.data.objects.new(
        inner_name, make_cylinder_mesh(inner_name + '_Mesh', inner_r, height + 2.0, 32))
    inner.matrix_world = mx
    link_object(context, inner)

    mod = outer.modifiers.new(name + '_HollowExact', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = inner
    ok, _solver = apply_boolean_modifier_smart(
        context, outer, mod, obj_cutter=inner,
        prefer_fast=False, force_robust=True, cleanup_cutter=True)
    safe_remove_object(inner)
    if not ok:
        safe_remove_object(outer)
        return None
    return outer


def build_sleeve_plane_trim_cutter(context, props, implant_obj, body_outer_radius,
                                    positive=True, name='DSG_SleevePlaneTrim'):
    """Cilindro tipo semiespacio que vuelve a cortar una cara plana del sleeve."""
    mx = get_sleeve_matrix_world(props, implant_obj)
    center = mx.to_translation()
    axis = (mx.to_3x3() @ Vector((0, 0, 1))).normalized()
    _inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    height = max(0.10, float(getattr(props, 'sleeve_height', 7.0)))
    half_h = height * 0.5
    radius = outer_r + max(0.80, float(body_outer_radius) * 1.25)
    depth = max(8.0, height + float(body_outer_radius) * 5.0)
    sign = 1.0 if positive else -1.0
    # El cutter entra unas micras dentro del sleeve para evitar una booleana
    # coplanar exactamente sobre la tapa original. La pérdida axial es <0.01 mm.
    plane_inset = 0.006
    cutter_center = center + axis * sign * (half_h - plane_inset + depth * 0.5)

    cutter = bpy.data.objects.new(
        name, make_cylinder_mesh(name + '_Mesh', radius, depth, 48))
    link_object(context, cutter)
    cutter.location = cutter_center
    cutter.rotation_mode = 'QUATERNION'
    cutter.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis)
    return cutter


def build_sleeve_lumen_restore_cutter(context, props, implant_obj,
                                       name='DSG_SleeveLumenRestoreCut'):
    """Reabre el lumen axial exacto después de la fusión imperativa."""
    mx = get_sleeve_matrix_world(props, implant_obj)
    inner_r, _outer_r, _wall = _sleeve_radii_from_props(props)
    height = max(0.10, float(getattr(props, 'sleeve_height', 7.0)))
    radius = inner_r + max(0.015, min(0.05, inner_r * 0.02))
    cutter = bpy.data.objects.new(
        name, make_cylinder_mesh(name + '_Mesh', radius, height + 1.2, 48))
    cutter.matrix_world = mx
    link_object(context, cutter)
    return cutter


def restore_sleeve_after_imperative_irrigation(context, guide_obj, props,
                                                 implant_obj, body_outer_radius,
                                                 prefix='DSG_IrrRestore'):
    """Restaura shell, planos superior/inferior y lumen sin cancelar el tubo.

    La restauración es secundaria: si alguna booleana falla, se conserva siempre
    la unión imperativa ya realizada y se devuelve un aviso detallado.
    """
    messages = []
    current = guide_obj

    shell = build_pristine_sleeve_shell(
        context, props, implant_obj, name=prefix + '_PristineSleeve')
    if _valid_obj(shell):
        restored, ok, msg = fuse_additions_into_base_exact(
            context, current, [shell], GUIDE_NAME,
            mod_name=prefix + '_SleeveShellUnion', require_solid=True)
        if ok and restored is not None:
            current = restored
            messages.append('shell exacto restaurado')
        else:
            messages.append('aviso shell: ' + msg)
    else:
        messages.append('aviso: no se pudo reconstruir shell exacto')

    top = build_sleeve_plane_trim_cutter(
        context, props, implant_obj, body_outer_radius,
        positive=True, name=prefix + '_TopPlaneTrim')
    current, ok_top, msg_top = apply_difference_exact_transactional(
        context, current, top, prefix + '_TopPlaneDifference', require_solid=True)
    messages.append('cara superior plana' if ok_top else 'aviso superior: ' + msg_top)

    bottom = build_sleeve_plane_trim_cutter(
        context, props, implant_obj, body_outer_radius,
        positive=False, name=prefix + '_BottomPlaneTrim')
    current, ok_bottom, msg_bottom = apply_difference_exact_transactional(
        context, current, bottom, prefix + '_BottomPlaneDifference', require_solid=True)
    messages.append('cara inferior plana' if ok_bottom else 'aviso inferior: ' + msg_bottom)

    lumen = build_sleeve_lumen_restore_cutter(
        context, props, implant_obj, name=prefix + '_LumenCut')
    current, ok_lumen, msg_lumen = apply_difference_exact_transactional(
        context, current, lumen, prefix + '_LumenDifference', require_solid=True)
    messages.append('lumen axial reabierto' if ok_lumen else 'aviso lumen: ' + msg_lumen)

    return current, '; '.join(messages)


def fuse_irrigation_staged_exact(context, guide_obj, path_world, props, implant_obj,
                                  body_outer_radius, mod_prefix='DSG_Irr'):
    """Fusión imperativa del tubo hasta el interior del lumen.

    1) Construye el tubo completo desde dentro del lumen hacia el exterior.
    2) Intenta UNION EXACT directa sin guards ni validación de caras planas.
    3) Si EXACT no deja sólido, fuerza Join + Voxel Remesh fino.
    4) Reconstruye el sleeve y recorta de nuevo sus dos planos y su lumen.
    """
    if not _valid_obj(guide_obj) or len(path_world) < 2:
        return None, False, 'invalid guide or path', None

    overall_backup = guide_obj.data.copy()
    tube = build_blended_irrigation_outer_tube_mesh(
        context, path_world, body_outer_radius, props,
        implant_obj=implant_obj, name=mod_prefix + '_ImperativeTube',
        bevel_resolution=props.irr_bevel_resolution,
        smooth_iters=props.irr_curve_smooth_iters,
        entry_mode='full')
    if not _valid_obj(tube):
        try:
            bpy.data.meshes.remove(overall_backup)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return None, False, 'no se pudo construir el tubo imperativo', None

    # Primera opción: UNION EXACT directa. No se llama a ningún guard del sleeve.
    fused, ok_exact, exact_msg = fuse_additions_into_base_exact(
        context, guide_obj, [tube], GUIDE_NAME,
        mod_name=mod_prefix + '_ImperativeUnionExact', require_solid=True)
    fusion_msg = exact_msg

    if not ok_exact or fused is None:
        # fuse_additions... restaura la guía y elimina el cutter fallido.
        tube = build_blended_irrigation_outer_tube_mesh(
            context, path_world, body_outer_radius, props,
            implant_obj=implant_obj, name=mod_prefix + '_ImperativeTubeVoxel',
            bevel_resolution=props.irr_bevel_resolution,
            smooth_iters=props.irr_curve_smooth_iters,
            entry_mode='full')
        if not _valid_obj(tube):
            _restore_object_mesh_copy(guide_obj, overall_backup)
            return None, False, (
                'EXACT UNION failed and the tube could not be rebuilt for fallback: '
                + exact_msg), None
        fused, ok_voxel, voxel_msg = force_voxel_union_imperative(
            context, guide_obj, tube, props, out_name=GUIDE_NAME,
            mod_name=mod_prefix + '_ImperativeVoxelRemesh')
        if not ok_voxel or fused is None:
            _restore_object_mesh_copy(guide_obj, overall_backup)
            return None, False, (
                f'UNION EXACT: {exact_msg}; fallback imperativo: {voxel_msg}'), None
        fusion_msg = f'Non-solid EXACT result ({exact_msg}); {voxel_msg}'

    # La entrada ya está dentro del lumen. Ahora se recupera la geometría exacta
    # del sleeve sin permitir que un fallo de restauración elimine el tubo.
    fused, restore_msg = restore_sleeve_after_imperative_irrigation(
        context, fused, props, implant_obj, body_outer_radius,
        prefix=mod_prefix + '_Restore')

    try:
        if overall_backup.users == 0:
            bpy.data.meshes.remove(overall_backup)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return fused, True, fusion_msg + '; ' + restore_msg, {
        'imperative': True,
        'flat_faces_restored': restore_msg,
    }


# Removed dead legacy implementation: _legacy_build_blended_irrigation_outer_tube_mesh_v1 (no production references in DSG 8.9 audit).


# ─────────────────────────────────────────────────────────────
# Draw handlers GPU — contorno e irrigación
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Outline nativo de Blender
# ─────────────────────────────────────────────────────────────

def get_contour_curve():
    obj = bpy.data.objects.get(CONTOUR_CURVE_NAME)
    return obj if obj and obj.type == 'CURVE' else None


def ensure_contour_curve(context):
    obj = get_contour_curve()
    if obj is not None:
        return obj
    curve = bpy.data.curves.new(CONTOUR_CURVE_NAME + '_Data', type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    curve.bevel_depth = 0.08
    curve.bevel_resolution = 2
    curve.fill_mode = 'FULL'
    obj = bpy.data.objects.new(CONTOUR_CURVE_NAME, curve)
    link_object(context, obj)
    obj.show_in_front = True
    obj.display_type = 'WIRE'
    link_object_to_dsg_collection(obj, ROLE_FRAME)
    return obj


def set_contour_curve_points(context, points, cyclic=True):
    obj = ensure_contour_curve(context)
    curve = obj.data
    while len(curve.splines) > 0:
        curve.splines.remove(curve.splines[0])
    pts = [Vector(p) for p in points]
    if pts:
        spline = curve.splines.new(type='POLY')
        spline.points.add(len(pts) - 1)
        for item, point in zip(spline.points, pts):
            local = obj.matrix_world.inverted() @ point
            item.co = (local.x, local.y, local.z, 1.0)
        spline.use_cyclic_u = bool(cyclic and len(pts) >= 3)
    curve.update_tag()
    return obj


def get_contour_curve_points():
    obj = get_contour_curve()
    if obj is None or not obj.data.splines:
        return []
    spline = obj.data.splines[0]
    return [obj.matrix_world @ Vector(point.co[:3]) for point in spline.points]


def clear_contour_curve(remove_data=True):
    """Elimina el objeto temporal del contorno y, si queda huérfano, su datablock Curve.

    El contorno solo se necesita para construir DSG_Frame. Delete también el
    datablock evita que ``DSG_ContourCurve_Data`` quede como residuo en el .blend.
    """
    obj = bpy.data.objects.get(CONTOUR_CURVE_NAME)
    curve_data = None
    if obj is not None:
        try:
            if obj.type == 'CURVE':
                curve_data = obj.data
        except (ReferenceError, RuntimeError):
            curve_data = None
        safe_remove_object(obj)

    if remove_data and curve_data is not None:
        try:
            if curve_data.users == 0:
                bpy.data.curves.remove(curve_data)
        except (ReferenceError, RuntimeError, TypeError):
            pass


def consume_contour_after_frame(props):
    """Limpia todo el estado de contorno solo tras crear el frame con éxito.

    Si la creación del frame falla, esta función no se llama y la curva permanece
    disponible para corregirla.
    """
    unregister_contour_draw_handler()
    clear_contour_curve(remove_data=True)
    try:
        props.contour_points.clear()
        props.drawing_active = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def sync_legacy_contour_points(props, points):
    """Mantiene compatibilidad al abrir el archivo con versiones anteriores."""
    props.contour_points.clear()
    for point in points:
        item = props.contour_points.add()
        item.co = Vector(point)

def _mark_gpu_dirty():
    """Compatibilidad con operadores modales: el dibujo GPU ya no cachea batches."""
    pass


def _as_gpu_coords(points):
    return [tuple(Vector(p)) for p in points]


def draw_polyline_gpu(coords, point_color, line_color, point_size=10, close_loop=False):
    """Dibuja puntos y polilínea 3D con una sola rutina GPU.

    Se usa para el contorno y los trazados de irrigación con una rutina común.
    """
    if not coords:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.point_size_set(point_size)
    gpu.state.blend_set('ALPHA')
    shader.bind()

    batch_pts = batch_for_shader(shader, 'POINTS', {"pos": coords})
    shader.uniform_float("color", point_color)
    batch_pts.draw(shader)

    if len(coords) >= 2:
        line_coords = coords + [coords[0]] if close_loop else coords
        batch_ln = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_coords})
        shader.uniform_float("color", line_color)
        batch_ln.draw(shader)

    gpu.state.blend_set('NONE')


def _draw_callback_contour():
    current_chain = getattr(_draw_callback_contour, '_current_chain', [])
    if not current_chain:
        current_chain = get_contour_curve_points()
    if not current_chain:
        return
    try:
        draw_polyline_gpu(
            _as_gpu_coords(current_chain),
            point_color=(0.20, 1.0, 0.35, 1.0),
            line_color=(0.05, 0.95, 0.25, 0.95),
            point_size=12,
            close_loop=len(current_chain) >= 3,
        )
    except RuntimeError as exc:
        print(f'[DSG] Contour draw: {exc}')


_draw_callback_contour._current_chain = []


def register_contour_draw_handler():
    global _CONTOUR_DRAW_HANDLER
    if _CONTOUR_DRAW_HANDLER is None:
        _CONTOUR_DRAW_HANDLER = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback_contour, (), 'WINDOW', 'POST_VIEW')


def unregister_contour_draw_handler():
    global _CONTOUR_DRAW_HANDLER
    if _CONTOUR_DRAW_HANDLER is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_CONTOUR_DRAW_HANDLER, 'WINDOW')
        except RuntimeError:
            pass
        _CONTOUR_DRAW_HANDLER = None
    _draw_callback_contour._current_chain = []



# Irrigation drawing callback

def _draw_callback_irrigation():
    current_chain = getattr(_draw_callback_irrigation, '_current_chain', [])
    if not current_chain:
        return
    try:
        draw_polyline_gpu(
            _as_gpu_coords(current_chain),
            point_color=(0.0, 1.0, 0.9, 1.0),
            line_color=(0.0, 0.75, 1.0, 0.9),
            point_size=14,
            close_loop=False,
        )
    except RuntimeError as e:
        print(f"[DSG] Irr draw: {e}")


_draw_callback_irrigation._current_chain = []


def register_irr_draw_handler():
    global _IRR_DRAW_HANDLER
    if _IRR_DRAW_HANDLER is None:
        _IRR_DRAW_HANDLER = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback_irrigation, (), 'WINDOW', 'POST_VIEW')


def unregister_irr_draw_handler():
    global _IRR_DRAW_HANDLER
    if _IRR_DRAW_HANDLER is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_IRR_DRAW_HANDLER, 'WINDOW')
        except RuntimeError:
            pass
        _IRR_DRAW_HANDLER = None


_ENGRAVE_PREVIEW_REFRESH_PENDING = False
# One-entry surface projection cache shared by the live preview and the final
# cutter.  The expensive BVH projection should not be repeated when the user
# clicks Grabar immediately after approving the preview.
_ENGRAVE_PROJECTION_CACHE = {}
_ENGRAVE_PROJECTION_CACHE_MAX_ENTRIES = 2


def _engrave_preview_refresh_timer():
    global _ENGRAVE_PREVIEW_REFRESH_PENDING
    _ENGRAVE_PREVIEW_REFRESH_PENDING = False
    try:
        if not lifecycle.is_active():
            return None
        scene = getattr(bpy.context, 'scene', None)
        props = getattr(scene, 'dsg_props', None) if scene is not None else None
        if props is None or not bool(getattr(props, 'engrave_has_position', False)):
            return None
        if not _valid_obj(get_active_guide_obj(props)):
            return None
        create_or_update_engrave_preview(bpy.context, props)
        _tag_dicom_measurement_redraw()
    except Exception as exc:
        print(f'[DSG] Automatic engraving preview refresh skipped: {exc}')
    return None


def _on_engrave_setting_change(self, context):
    """Mark the engraving preview as stale without recomputing it live.

    Live BVH reprojection while typing was one of the main final-step
    bottlenecks. The preview is now refreshed only on explicit user request
    (or when the anchor is initially placed), and the final Boolean still runs
    only when the user clicks the engrave button.
    """
    global _ENGRAVE_PREVIEW_REFRESH_PENDING
    try:
        lifecycle.unregister_timer(_engrave_preview_refresh_timer)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _ENGRAVE_PREVIEW_REFRESH_PENDING = False
    try:
        self['DSG_engrave_preview_dirty'] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


# ─────────────────────────────────────────────────────────────
# Properties
# ─────────────────────────────────────────────────────────────

