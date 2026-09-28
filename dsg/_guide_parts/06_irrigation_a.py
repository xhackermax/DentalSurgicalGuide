def get_confirmed_irrigation_walls():
    """Wall Thicknesses externas confirmadas que aún no se han combinado con DSG_Guide."""
    out = []
    for obj in bpy.data.objects:
        try:
            if (obj.name.startswith(IRR_WALL_PREFIX)
                    and bool(obj.get('DSG_irrigation_wall_confirmed', False))
                    and _valid_obj(obj)
                    and obj.type == 'MESH'):
                out.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    return sorted(out, key=lambda item: item.name)



def _sample_irrigation_c_arc_points(center, radial, tangent, radius,
                                     angle_start_deg, angle_end_deg, steps=14):
    """Samples a planar circular arc around the sleeve axis.

    Angle 0° lies on the positive radial direction; +90° lies on the positive
    tangential direction.  The helper keeps the geometry deterministic and makes
    the later C manifold easy to inspect and modify.
    """
    center = Vector(center)
    radial = Vector(radial)
    tangent = Vector(tangent)
    if radial.length < 1e-8 or tangent.length < 1e-8 or radius <= 0.0:
        return []
    radial.normalize()
    tangent.normalize()
    steps = max(3, int(steps))
    points = []
    for index in range(steps):
        t = index / max(1, steps - 1)
        angle_deg = angle_start_deg + (angle_end_deg - angle_start_deg) * t
        angle = math.radians(angle_deg)
        point = center + radial * (math.cos(angle) * radius) + tangent * (math.sin(angle) * radius)
        points.append(point)
    return points



def _sample_plumbing_elbow_curve(start_point, end_point, start_direction,
                                  end_direction, min_turn_radius=0.35,
                                  max_step=0.08):
    """Returns a rounded plumbing-style elbow between two points.

    The outlet no longer uses a straight cylinder.  Instead, a cubic Bezier is
    shaped from the arc tangent to the sleeve-facing exit direction, producing a
    smooth codo-like bend similar to plumbing fittings.
    """
    start_point = Vector(start_point)
    end_point = Vector(end_point)
    start_direction = Vector(start_direction)
    end_direction = Vector(end_direction)
    chord = end_point - start_point
    distance = chord.length
    if distance < 1e-6:
        return [start_point.copy(), end_point.copy()]

    if start_direction.length < 1e-8:
        start_direction = chord.copy()
    if end_direction.length < 1e-8:
        end_direction = chord.copy()
    start_direction.normalize()
    end_direction.normalize()

    min_turn_radius = max(0.12, float(min_turn_radius))
    handle = max(distance * 0.34, min_turn_radius * 1.20)
    handle = min(handle, distance * 0.58)

    p1 = start_point + start_direction * handle
    p2 = end_point - end_direction * handle
    return _sample_cubic_bezier_segment(start_point, p1, p2, end_point, max_step=max_step)


def _continuous_irrigation_c_path(ring):
    """Return one uninterrupted centreline for the complete C manifold.

    The previous implementation built two arcs and two elbows as separate
    closed meshes.  Even with a voxel fuse, tiny non-overlapping junctions could
    survive and the sleeve Boolean could leave short blocked segments.  This
    path runs continuously from the lower sleeve outlet, through the lower arc
    and inlet split, to the upper outlet.
    """
    if not ring:
        return []
    upper_arc = [Vector(point) for point in ring.get('upper_arc', [])]
    lower_arc = [Vector(point) for point in ring.get('lower_arc', [])]
    if len(upper_arc) < 2 or len(lower_arc) < 2:
        return []

    branch_radius = max(0.14, float(ring.get('branch_tube_r', 0.25)))
    outlet_radius = min(
        max(float(ring.get('side_hole_r', branch_radius)), branch_radius * 0.82),
        branch_radius * 0.98,
    )

    def elbow(arc_path, start, end):
        start = Vector(start)
        end = Vector(end)
        start_direction = Vector(arc_path[-1]) - Vector(arc_path[-2])
        end_direction = Vector(ring['center']) - end
        return _sample_plumbing_elbow_curve(
            start,
            end,
            start_direction,
            end_direction,
            min_turn_radius=max(outlet_radius * 1.35, branch_radius * 1.10),
            max_step=0.055,
        )

    lower_elbow = elbow(
        lower_arc, ring['lower_attach_point'], ring['lower_lumen_point'])
    upper_elbow = elbow(
        upper_arc, ring['upper_attach_point'], ring['upper_lumen_point'])
    if len(lower_elbow) < 2 or len(upper_elbow) < 2:
        return []

    path = []

    def extend(points):
        for point in points:
            point = Vector(point)
            if not path or (point - path[-1]).length > 0.004:
                path.append(point)

    # One continuous route: lower lumen -> lower arc -> split -> upper arc ->
    # upper lumen.  Reversing the lower pieces preserves tangent continuity at
    # the split point (angle 0 degrees).
    extend(reversed(lower_elbow))
    extend(reversed(lower_arc))
    extend(upper_arc)
    extend(upper_elbow)
    return _remove_near_duplicate_points(path, epsilon=0.003, closed=False)


def _irrigation_c_continuity_samples(control_points, props, implant_obj=None,
                                     max_step=0.16):
    """Samples the intended C lumen centreline for post-Boolean auditing."""
    if len(control_points or []) < 2:
        return [], 0.0
    ring = get_irrigation_internal_ring_geometry(
        control_points[1], props, implant_obj)
    path = _continuous_irrigation_c_path(ring)
    if len(path) < 2:
        return [], 0.0
    raw = _resample_polyline_with_distances(
        path, max_step=max(0.06, float(max_step)))
    samples = [Vector(point) for point, _distance in raw]
    radius = max(0.12, float(ring.get('branch_tube_r', 0.25)))
    return samples, radius


def _world_bvh_for_closed_mesh(obj):
    """Build a world-space BVH and a conservative ray length for one mesh."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None, 0.0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = None
    try:
        mesh = evaluated.to_mesh()
        vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
        polygons = [tuple(int(index) for index in polygon.vertices)
                    for polygon in mesh.polygons if len(polygon.vertices) >= 3]
        if not vertices or not polygons:
            return None, 0.0
        tree = BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
        minimum = Vector((
            min(point.x for point in vertices),
            min(point.y for point in vertices),
            min(point.z for point in vertices),
        ))
        maximum = Vector((
            max(point.x for point in vertices),
            max(point.y for point in vertices),
            max(point.z for point in vertices),
        ))
        return tree, max(10.0, (maximum - minimum).length * 2.5)
    except Exception:
        return None, 0.0
    finally:
        try:
            if mesh is not None:
                evaluated.to_mesh_clear()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _point_inside_closed_bvh(tree, point, ray_length):
    """Parity test with three non-axis-aligned rays to avoid edge ambiguity."""
    if tree is None:
        return False
    directions = (
        Vector((0.923, 0.271, 0.273)).normalized(),
        Vector((-0.337, 0.889, 0.309)).normalized(),
        Vector((0.211, -0.401, 0.891)).normalized(),
    )
    votes = 0
    for direction in directions:
        origin = Vector(point) + direction * 1.0e-5
        remaining = max(1.0, float(ray_length))
        intersections = 0
        for _iteration in range(128):
            location, _normal, _index, distance = tree.ray_cast(
                origin, direction, remaining)
            if location is None:
                break
            intersections += 1
            advance = max(1.0e-4, float(distance) + 1.0e-4)
            origin = origin + direction * advance
            remaining -= advance
            if remaining <= 1.0e-4:
                break
        if intersections % 2 == 1:
            votes += 1
    return votes >= 2


def _blocked_irrigation_c_samples(component, cutter):
    """Return C-centreline samples still occupied by solid after the cut."""
    if not _valid_obj(component) or not _valid_obj(cutter):
        return []
    raw = cutter.get('DSG_irrigation_c_continuity_samples', '')
    if not raw:
        return []
    try:
        samples = [Vector(value) for value in json.loads(str(raw))]
    except Exception:
        return []
    if not samples:
        return []
    tree, ray_length = _world_bvh_for_closed_mesh(component)
    if tree is None:
        return []
    blocked = []
    # Skip only the extreme end points, which can lie exactly on the open axial
    # lumen boundary. Every internal sample must be outside the sleeve solid.
    for point in samples[1:-1] if len(samples) > 2 else samples:
        if _point_inside_closed_bvh(tree, point, ray_length):
            blocked.append(point)
    return blocked


def get_irrigation_internal_ring_geometry(anchor_point, props, implant_obj=None):
    """Sleeve manifold geometry using an open C instead of a closed annulus.

    The previous toroidal ring could leave an air pocket inside the loop.  This
    geometry keeps the same radial entry into the sleeve wall, but it splits the
    flow into two daughter arcs that never reconnect, so every internal volume
    has a downstream escape route.

    In DIRECT mode no C manifold is produced.  Returning ``None`` intentionally
    makes the main radial centerline continue directly into the sleeve lumen.
    """
    mode = str(getattr(props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
    if mode == 'DIRECT':
        return None

    geo = get_sleeve_wall_geometry(anchor_point, props, implant_obj)
    if not geo:
        return None

    axis = Vector(geo['axis'])
    radial = Vector(geo['radial'])
    center = Vector(geo['axis_entry'])
    if axis.length < 1e-8 or radial.length < 1e-8:
        return None
    axis.normalize()
    radial.normalize()
    tangent = axis.cross(radial)
    if tangent.length < 1e-8:
        u, v, _ = build_axis_basis(axis)
        tangent = u if abs(u.dot(radial)) < 0.9 else v
    tangent.normalize()

    inner_r = max(0.05, float(geo['inner_r']))
    outer_r = max(inner_r + 0.10, float(geo['outer_r']))
    wall_t = max(0.25, outer_r - inner_r)

    outlet_r = max(0.15, float(getattr(props, 'irr_funnel_outer_diameter', 1.0)) * 0.5)
    branch_tube_r = min(max(0.18, outlet_r * 0.72), max(0.18, wall_t * 0.34))
    branch_tube_r = min(branch_tube_r, max(0.16, wall_t * 0.42))

    arc_center_r = inner_r + wall_t * 0.55
    arc_center_r = max(arc_center_r, inner_r + branch_tube_r + 0.08)
    arc_center_r = min(arc_center_r, outer_r - branch_tube_r - 0.08)
    if arc_center_r <= inner_r + 0.02:
        return None

    side_hole_r = min(max(0.18, outlet_r * 0.90), branch_tube_r + 0.04)
    split_point = center + radial * arc_center_r
    split_plenum_r = max(side_hole_r * 0.92, min(branch_tube_r * 1.08, branch_tube_r + 0.05))

    # The outlets remain approximately tangential so the jet enters the sleeve
    # lumen from two opposed directions.  A little extra sweep produces a real
    # C around the posterior side of the sleeve instead of a transverse T.
    outlet_angle_deg = 102.0
    arc_steps = max(6, int(getattr(props, 'irr_bevel_resolution', 8)) * 2)
    upper_arc = _sample_irrigation_c_arc_points(
        center, radial, tangent, arc_center_r, 0.0, outlet_angle_deg, steps=arc_steps)
    lower_arc = _sample_irrigation_c_arc_points(
        center, radial, tangent, arc_center_r, 0.0, -outlet_angle_deg, steps=arc_steps)
    if not upper_arc or not lower_arc:
        return None

    lumen_overshoot = max(0.10, side_hole_r * 0.70)
    upper_lumen_point = center + tangent * max(0.0, inner_r - lumen_overshoot)
    lower_lumen_point = center - tangent * max(0.0, inner_r - lumen_overshoot)

    return {
        'center': center,
        'axis': axis,
        'radial': radial,
        'tangent': tangent,
        'inner_r': inner_r,
        'outer_r': outer_r,
        'wall_t': wall_t,
        'ring_center_r': arc_center_r,  # kept for compatibility with old metadata/users
        'ring_tube_r': branch_tube_r,
        'side_hole_r': side_hole_r,
        'inlet_point': split_point,
        'split_point': split_point,
        'split_plenum_r': split_plenum_r,
        'branch_tube_r': branch_tube_r,
        'outlet_angle_deg': outlet_angle_deg,
        'upper_arc': upper_arc,
        'lower_arc': lower_arc,
        'upper_attach_point': Vector(upper_arc[-1]),
        'lower_attach_point': Vector(lower_arc[-1]),
        'upper_lumen_point': upper_lumen_point,
        'lower_lumen_point': lower_lumen_point,
        'geometry_mode': 'OPEN_C_SLEEVE_MANIFOLD',
    }



def build_irrigation_internal_ring_parts(context, control_points, props, implant_obj=None, name_prefix='DSG_IrrRing'):
    """Build one continuous open-C cutter inside the sleeve.

    Earlier builds represented the C as five independent solids (two arcs, two
    elbows and a split plenum).  Small Boolean/voxel junction errors could leave
    short solid bridges inside the sleeve.  The C is now a single capped tube
    from one axial-lumen outlet to the other, with only overlapping junction
    spheres added at the inlet and outlets.
    """
    if len(control_points) < 2:
        return []
    ring = get_irrigation_internal_ring_geometry(
        control_points[1], props, implant_obj)
    if not ring:
        return []

    path = _continuous_irrigation_c_path(ring)
    if len(path) < 2:
        return []

    branch_radius = max(0.14, float(ring['branch_tube_r']))
    samples = [(Vector(point), branch_radius) for point in path]
    parts = []

    continuous = build_variable_radius_tube_object(
        context,
        f'{name_prefix}_ContinuousC',
        samples,
        bevel_resolution=max(8, int(getattr(props, 'irr_bevel_resolution', 8))),
        show_wire=True,
        subdiv_levels=0,
    )
    if not _valid_obj(continuous):
        return []
    continuous.show_in_front = True
    parts.append(continuous)

    # Volumetric overlaps at every network junction. These are deliberately a
    # little larger than the lumen radius and are part of the cutter only; they
    # prevent a zero-area/tangent contact from becoming a blocked water path.
    junction_specs = (
        ('Split', ring['split_point'], max(
            float(ring['split_plenum_r']), branch_radius * 1.22)),
        ('UpperOutlet', ring['upper_lumen_point'], branch_radius * 1.08),
        ('LowerOutlet', ring['lower_lumen_point'], branch_radius * 1.08),
    )
    for suffix, location, radius in junction_specs:
        mesh = make_uv_sphere_mesh(
            f'{name_prefix}_{suffix}_Mesh',
            max(0.16, float(radius)),
            22,
            12,
        )
        obj = bpy.data.objects.new(f'{name_prefix}_{suffix}', mesh)
        obj.location = Vector(location)
        link_object(context, obj)
        obj.display_type = 'WIRE'
        obj.show_in_front = True
        parts.append(obj)

    return parts


def build_irrigation_c_only_cutter(context, control_points, props,
                                     implant_obj=None,
                                     name='DSG_IrrCOnlyCut',
                                     extra_radius=0.045):
    """Build a compact cutter containing only the continuous sleeve C lumen.

    This cutter is used to open the same C path through the irrigation wall
    shell.  Previously the sleeve was cut, but the overlapping external tube
    wall was assembled afterwards and could re-block parts of the C manifold.
    """
    if len(control_points or []) < 2:
        return None
    ring = get_irrigation_internal_ring_geometry(
        control_points[1], props, implant_obj)
    path = _continuous_irrigation_c_path(ring)
    if not ring or len(path) < 2:
        return None

    radius = max(
        0.14,
        float(ring.get('branch_tube_r', 0.25)) + max(0.0, float(extra_radius)),
    )
    parts = []
    tube = build_variable_radius_tube_object(
        context,
        name + '_Tube',
        [(Vector(point), radius) for point in path],
        bevel_resolution=max(8, int(getattr(props, 'irr_bevel_resolution', 8))),
        show_wire=True,
        subdiv_levels=0,
    )
    if not _valid_obj(tube):
        return None
    parts.append(tube)

    for suffix, location, node_radius in (
        ('Split', ring['split_point'], max(radius * 1.18, float(ring['split_plenum_r']) + extra_radius)),
        ('UpperOutlet', ring['upper_lumen_point'], radius * 1.06),
        ('LowerOutlet', ring['lower_lumen_point'], radius * 1.06),
    ):
        mesh = make_uv_sphere_mesh(
            f'{name}_{suffix}_Mesh', max(0.16, float(node_radius)), 22, 12)
        obj = bpy.data.objects.new(f'{name}_{suffix}', mesh)
        obj.location = Vector(location)
        link_object(context, obj)
        obj.display_type = 'WIRE'
        obj.show_in_front = True
        parts.append(obj)

    cutter = _fuse_irrigation_solids_with_voxel(
        context, parts, name, voxel_size=0.024)
    if not _valid_obj(cutter):
        return None
    samples, _sample_radius = _irrigation_c_continuity_samples(
        control_points, props, implant_obj=implant_obj, max_step=0.14)
    try:
        cutter['DSG_irrigation_c_continuity_samples'] = json.dumps([
            [float(point.x), float(point.y), float(point.z)] for point in samples
        ])
        cutter['DSG_irrigation_c_continuity_radius'] = float(radius)
        cutter['DSG_irrigation_c_only_cutter'] = True
        cutter['DSG_irrigation_internal_c_manifold'] = True
        cutter['DSG_irrigation_c_continuous_single_path'] = True
        cutter['DSG_cut_type'] = 'dedicated_per_sleeve_continuous_c'
        cutter['DSG_implant_name'] = _safe_object_name(implant_obj) or ''
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return cutter


def build_irrigation_initial_control_points(points, props, implant_obj=None):
    """Convierte los clics del usuario en controles del eje interno.

    El primer clic es el contacto con la pared lateral. Se añade automáticamente
    un punto anterior dentro del lumen axial del sleeve. Los demás clics se
    conservan como controles externos, igual que los anchors del frame.
    """
    raw = _remove_near_duplicate_points(points, epsilon=0.03, closed=False)
    if len(raw) < 2:
        return []

    geo = get_sleeve_wall_geometry(raw[0], props, implant_obj)
    if not geo:
        return []

    radial = Vector(geo['radial'])
    if radial.length < 1e-8:
        return []
    radial.normalize()
    axis_entry = Vector(geo['axis_entry'])
    inner_r = max(0.05, float(geo['inner_r']))
    channel_r = max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5)

    ring = get_irrigation_internal_ring_geometry(raw[0], props, implant_obj)
    if ring:
        deep_point = Vector(ring['inlet_point'])
    elif _irrigation_is_direct_channel_mode(props):
        direct_tip = get_direct_irrigation_lumen_tip(raw[0], props, implant_obj=implant_obj)
        deep_point = direct_tip if direct_tip is not None else axis_entry + radial * max(0.0, inner_r - _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r))
    else:
        requested = max(0.0, float(getattr(props, 'irr_funnel_depth', 0.0)))
        # 0 = automático: el eje llega hasta el centro del lumen del sleeve.
        # Así el cap del cutter queda completamente dentro de una cavidad existente
        # y no termina tangente a la pared interna, causa típica de un loop abierto.
        penetration = requested if requested > 0.01 else inner_r
        penetration = min(max(0.25, penetration), inner_r)
        deep_point = axis_entry + radial * max(0.0, inner_r - penetration)
    surface_point = Vector(geo['surface_point'])
    controls = [deep_point, surface_point]
    for point in raw[1:]:
        point = Vector(point)
        if (point - controls[-1]).length > 0.03:
            controls.append(point.copy())
    return controls


def smooth_irrigation_centerline_controls(control_points, props):
    """Suaviza solo la parte exterior y conserva el tramo radial del sleeve."""
    control_points = _normalize_direct_irrigation_controls(control_points, props)
    controls = _remove_near_duplicate_points(control_points, epsilon=0.02, closed=False)
    if len(controls) < 2:
        return controls

    deep = Vector(controls[0])
    surface = Vector(controls[1])
    external = [surface] + [Vector(point) for point in controls[2:]]

    if len(external) >= 4:
        external = build_catmull_rom_frame_path(
            external,
            closed=False,
            alpha=FRAME_CATMULL_ALPHA_FIXED,
            max_spacing=max(0.20, IRR_LUMEN_SAMPLE_STEP_MM_FIXED),
            min_samples_per_segment=4,
            max_samples_per_segment=40,
        )
    elif len(external) >= 3:
        external = build_kochanek_bartels_path(
            external,
            props=props,
            max_spacing=max(0.20, IRR_LUMEN_SAMPLE_STEP_MM_FIXED),
        )

    if not external:
        external = [surface]
    external[0] = surface.copy()
    return _remove_near_duplicate_points([deep] + external, epsilon=0.02, closed=False)


def _irrigation_polyline_sample(points, target_distance):
    pts = [Vector(point) for point in points]
    if not pts:
        return Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)), 0
    if len(pts) == 1:
        return pts[0].copy(), Vector((1.0, 0.0, 0.0)), 0

    target = max(0.0, float(target_distance))
    accumulated = 0.0
    for index in range(len(pts) - 1):
        segment = pts[index + 1] - pts[index]
        length = segment.length
        if length < 1.0e-8:
            continue
        if accumulated + length >= target:
            factor = (target - accumulated) / length
            point = pts[index].lerp(pts[index + 1], factor)
            return point, segment.normalized(), index
        accumulated += length
    tangent = pts[-1] - pts[-2]
    if tangent.length < 1.0e-8:
        tangent = Vector((1.0, 0.0, 0.0))
    else:
        tangent.normalize()
    return pts[-1].copy(), tangent, len(pts) - 2


def _quintic_zero_acceleration_point(p0, p1, derivative0, derivative1, t):
    """Quíntica con posición/tangente fijadas y aceleración cero en extremos."""
    t = max(0.0, min(1.0, float(t)))
    p0 = Vector(p0)
    p1 = Vector(p1)
    d0 = Vector(derivative0)
    d1 = Vector(derivative1)
    controls = (
        p0,
        p0 + d0 / 5.0,
        p0 + d0 * (2.0 / 5.0),
        p1 - d1 * (2.0 / 5.0),
        p1 - d1 / 5.0,
        p1,
    )
    u = 1.0 - t
    weights = (
        u ** 5,
        5.0 * u ** 4 * t,
        10.0 * u ** 3 * t ** 2,
        10.0 * u ** 2 * t ** 3,
        5.0 * u * t ** 4,
        t ** 5,
    )
    result = Vector((0.0, 0.0, 0.0))
    for control, weight in zip(controls, weights):
        result += control * weight
    return result


def _build_irrigation_radial_exit_blend(surface, radial, external_path,
                                          blend_length, sample_step=0.10):
    """Sustituye el primer codo por una salida radial G1/C2 estable.

    El giro hacia la trayectoria del usuario comienza después de una distancia
    suficiente para que la reducción de radio no coincida con una curvatura
    extrema del eje.
    """
    surface = Vector(surface)
    radial = Vector(radial)
    if radial.length < 1.0e-8:
        radial = Vector((1.0, 0.0, 0.0))
    radial.normalize()

    path = _remove_near_duplicate_points(external_path, epsilon=0.01, closed=False)
    if not path:
        path = [surface, surface + radial * max(0.80, float(blend_length))]
    if (path[0] - surface).length > 0.02:
        path.insert(0, surface.copy())
    else:
        path[0] = surface.copy()

    total_length = sum((path[index + 1] - path[index]).length
                       for index in range(len(path) - 1))
    target_distance = min(max(0.55, float(blend_length)), max(0.55, total_length))
    target, target_tangent, target_segment = _irrigation_polyline_sample(
        path, target_distance)
    chord = target - surface
    chord_length = max(0.20, chord.length)

    start_derivative = radial * min(chord_length * 1.15, max(0.70, blend_length))
    end_derivative = target_tangent * min(chord_length * 1.00, max(0.60, blend_length * 0.90))
    sample_count = max(10, int(math.ceil(chord_length / max(0.05, float(sample_step)))) + 1)
    blend = [
        _quintic_zero_acceleration_point(
            surface, target, start_derivative, end_derivative,
            index / float(sample_count - 1))
        for index in range(sample_count)
    ]

    # Conserva el resto de la trayectoria original después del punto de empalme.
    remainder = []
    accumulated = 0.0
    inserted_target = False
    for index in range(len(path) - 1):
        segment = path[index + 1] - path[index]
        length = segment.length
        if length < 1.0e-8:
            continue
        if not inserted_target and accumulated + length >= target_distance:
            remainder.append(target.copy())
            inserted_target = True
        if inserted_target:
            remainder.append(path[index + 1].copy())
        accumulated += length

    combined = blend
    for point in remainder[1:]:
        if (point - combined[-1]).length > 0.01:
            combined.append(point.copy())
    return _remove_near_duplicate_points(combined, epsilon=0.008, closed=False)


def build_irrigation_wall_path(control_points, props, implant_obj=None):
    """Ruta exterior con salida radial estable y giro separado del estrechamiento.

    La pared comienza dentro del sleeve para asegurar la UNION. Desde la
    superficie sale con tangente radial y una quíntica C2 la conecta con la
    trayectoria del usuario. Esto elimina el codo concentrado que producía el
    nudo en la cara interior del canal.
    """
    centerline = smooth_irrigation_centerline_controls(control_points, props)
    if len(centerline) < 2:
        return []

    surface = Vector(centerline[1])
    geo = get_sleeve_wall_geometry(surface, props, implant_obj)
    if geo:
        radial = Vector(geo['radial'])
        if radial.length > 1.0e-8:
            radial.normalize()
        else:
            radial = Vector(centerline[2] - surface) if len(centerline) > 2 else Vector((1.0, 0.0, 0.0))
            radial.normalize()
        inner_r = float(geo['inner_r'])
        requested_overlap = max(0.10, float(getattr(props, 'irr_sleeve_overlap', 1.2)))
        overlap = min(requested_overlap, max(0.20, inner_r * 0.78))
        wall_start = Vector(geo['axis_entry']) + radial * max(0.0, inner_r - overlap)
    else:
        radial = Vector(centerline[2] - surface) if len(centerline) > 2 else Vector(surface - centerline[0])
        if radial.length < 1.0e-8:
            radial = Vector((1.0, 0.0, 0.0))
        radial.normalize()
        wall_start = Vector(centerline[0]).lerp(surface, 0.55)

    external = [surface.copy()] + [Vector(point) for point in centerline[2:]]
    if len(external) < 2:
        external.append(surface + radial * 1.20)

    base_outer_radius = max(
        0.25,
        float(get_irrigation_base_outer_radius_at_sleeve(props)))
    blend_length = max(
        float(IRRIGATION_SLEEVE_EXIT_BLEND_MIN_MM_FIXED),
        base_outer_radius * float(IRRIGATION_SLEEVE_EXIT_BLEND_RADIUS_SCALE_FIXED))
    exterior_blend = _build_irrigation_radial_exit_blend(
        surface, radial, external, blend_length, sample_step=0.09)

    path = [wall_start]
    for point in exterior_blend:
        if not path or (Vector(point) - path[-1]).length > 0.008:
            path.append(Vector(point))
    return _remove_near_duplicate_points(path, epsilon=0.006, closed=False)


def build_irrigation_profile_samples(path_points, props, surface_point=None,
                                      include_overshoot=False, add_wall=False):
    """Builds the irrigation lumen profile.

    Regular irrigation channels use a fixed hydraulic profile:
    - the external water inlet is Ø4.00 mm for the first 4.00 mm;
    - the following 2.00 mm form a smooth reduction;
    - the remaining channel is Ø1.00 mm up to the sleeve.

    Link branches remain continuously Ø1.00 mm. ``add_wall`` only adds the
    selected wall thickness around that internal lumen.
    """
    original_path = _remove_near_duplicate_points(path_points, epsilon=0.02, closed=False)
    if len(original_path) < 2:
        return []

    path = [Vector(point) for point in original_path]
    extra_start = 0.0
    extra_end = 0.0
    if include_overshoot:
        overshoot = max(0.20, float(getattr(props, 'irr_cut_overshoot', 1.5)))
        extra_start = max(0.10, min(0.30, overshoot * 0.15))
        extra_end = overshoot
        path = extend_polyline_ends(path, extra_start=extra_start, extra_end=extra_end)

    is_link = bool(getattr(props, 'irr_link_continuous_1mm', False))
    narrow_radius = 0.50
    inlet_radius = 2.00
    inlet_length = 4.00
    transition_length = 2.00
    wall = max(0.0, float(getattr(props, 'irr_wall_thickness', 1.5))) if add_wall else 0.0
    step = max(0.12, min(IRR_LUMEN_SAMPLE_STEP_MM_FIXED, 1.20))
    if add_wall:
        step = min(step, 0.12)

    raw = _resample_polyline_with_distances(path, max_step=step)
    if not raw:
        return []

    total_extended_length = float(raw[-1][1])
    # The cutter overshoot lies outside the visible tube. Subtract it so the
    # physical tube still contains a complete 4 mm long Ø4 mm inlet.
    physical_end_distance = max(0.0, total_extended_length - extra_end)

    samples = []
    for point, distance in raw:
        if is_link:
            radius = narrow_radius
        else:
            distance_from_physical_inlet = max(0.0, physical_end_distance - float(distance))
            if distance_from_physical_inlet <= inlet_length:
                radius = inlet_radius
            elif distance_from_physical_inlet <= inlet_length + transition_length:
                t = ((distance_from_physical_inlet - inlet_length) / transition_length)
                t = _smootherstep01(t)
                radius = inlet_radius + (narrow_radius - inlet_radius) * t
            else:
                radius = narrow_radius
        samples.append((Vector(point), radius + wall))
    return samples


def build_irrigation_lumen_samples_from_controls(control_points, props, include_overshoot=True):
    centerline = smooth_irrigation_centerline_controls(control_points, props)
    if len(centerline) < 2:
        return []
    return build_irrigation_profile_samples(
        centerline, props, surface_point=centerline[1],
        include_overshoot=include_overshoot, add_wall=False)


def _smooth_monotonic_irrigation_radii(result, surface_index, base_radii, passes=2):
    if not result or surface_index < 0 or surface_index >= len(result):
        return result
    radii = [float(radius) for _point, radius in result]
    base = [float(value) for value in base_radii]
    end = len(radii)
    start = max(0, surface_index)

    # Suaviza la parte visible con un filtro más blando y algo más largo.
    for _ in range(max(2, int(passes))):
        prev = list(radii)
        for i in range(start + 1, end - 1):
            avg = (prev[i - 1] + prev[i] * 3.0 + prev[i + 1]) / 5.0
            radii[i] = max(base[i], avg)

    # El primer punto visible también se amortigua para eliminar el labio justo
    # bajo el sleeve, pero sin bajar del radio base ni romper la continuidad.
    if start + 1 < end:
        blended = radii[start] * 0.42 + radii[start + 1] * 0.58
        radii[start] = max(base[start], min(radii[start], blended))

    # Impone un descenso monótono hacia el canal fino, evitando pequeños hombros.
    for i in range(start + 1, end):
        radii[i] = min(radii[i], radii[i - 1])
        radii[i] = max(base[i], radii[i])

    return [(Vector(point), radii[idx]) for idx, (point, _r) in enumerate(result)]


def _monotone_cubic_scalar(y0, y1, slope0, slope1, x0, x1, x):
    span = max(1.0e-8, float(x1) - float(x0))
    t = max(0.0, min(1.0, (float(x) - float(x0)) / span))
    u = 1.0 - t
    return (
        (2.0 * t ** 3 - 3.0 * t ** 2 + 1.0) * float(y0)
        + (t ** 3 - 2.0 * t ** 2 + t) * span * float(slope0)
        + (-2.0 * t ** 3 + 3.0 * t ** 2) * float(y1)
        + (t ** 3 - t ** 2) * span * float(slope1)
    )


def _monotone_three_point_slopes(x0, y0, x1, y1, x2, y2):
    h0 = max(1.0e-8, float(x1) - float(x0))
    h1 = max(1.0e-8, float(x2) - float(x1))
    delta0 = (float(y1) - float(y0)) / h0
    delta1 = (float(y2) - float(y1)) / h1
    if delta0 * delta1 <= 0.0:
        middle = 0.0
    else:
        w0 = 2.0 * h1 + h0
        w1 = h1 + 2.0 * h0
        middle = (w0 + w1) / (w0 / delta0 + w1 / delta1)
    return 0.0, middle, 0.0


def apply_irrigation_sleeve_volcano_to_outer_samples(samples, surface_point, props):
    """Perfil exterior único, monótono y desacoplado de la curvatura del eje.

    El máximo volumen queda enterrado. La sección llega a la superficie con un
    exceso pequeño y luego recupera el radio normal mediante una interpolación
    cúbica monótona; no hay hombros, mesetas ni filtros posteriores capaces de
    crear un nudo local.
    """
    clean = []
    for item in list(samples or []):
        if not item or len(item) != 2:
            continue
        point, radius = item
        point = Vector(point)
        radius = max(0.02, float(radius))
        if clean and (point - clean[-1][0]).length < 1.0e-5:
            clean[-1] = (point, max(radius, clean[-1][1]))
        else:
            clean.append((point, radius))
    if len(clean) < 2:
        return clean

    surface = Vector(surface_point)
    surface_index = min(
        range(len(clean)),
        key=lambda index: (clean[index][0] - surface).length)
    volcano_radius = max(
        clean[surface_index][1],
        float(get_irrigation_outer_radius_at_sleeve(props)))
    if volcano_radius <= clean[surface_index][1] + 1.0e-6:
        return clean

    cumulative = [0.0]
    for index in range(1, len(clean)):
        cumulative.append(
            cumulative[-1] + (clean[index][0] - clean[index - 1][0]).length)

    surface_distance = cumulative[surface_index]
    inside_span = max(0.12, surface_distance - cumulative[0])
    peak_distance = surface_distance - inside_span * 0.78
    peak_distance = max(cumulative[0] + 0.04, min(surface_distance - 0.04, peak_distance))

    base_radius_surface = clean[surface_index][1]
    extra_amplitude = max(0.0, volcano_radius - base_radius_surface)
    surface_weight = max(0.04, min(0.30, float(IRRIGATION_SLEEVE_VISIBLE_EXTRA_WEIGHT_FIXED)))
    visible_fade = max(
        float(IRRIGATION_SLEEVE_VISIBLE_FADE_MIN_MM_FIXED),
        base_radius_surface * float(IRRIGATION_SLEEVE_VISIBLE_FADE_RADIUS_SCALE_FIXED))
    fade_end = surface_distance + visible_fade

    slope_peak, slope_surface, slope_end = _monotone_three_point_slopes(
        peak_distance, 1.0,
        surface_distance, surface_weight,
        fade_end, 0.0)

    result = []
    for index, (point, normal_radius) in enumerate(clean):
        distance = cumulative[index]
        if distance <= peak_distance:
            u = max(0.0, min(1.0,
                (distance - cumulative[0])
                / max(1.0e-8, peak_distance - cumulative[0])))
            weight = 0.72 + (1.0 - 0.72) * _smootherstep01(u)
        elif distance <= surface_distance:
            weight = _monotone_cubic_scalar(
                1.0, surface_weight,
                slope_peak, slope_surface,
                peak_distance, surface_distance, distance)
        elif distance <= fade_end:
            weight = _monotone_cubic_scalar(
                surface_weight, 0.0,
                slope_surface, slope_end,
                surface_distance, fade_end, distance)
        else:
            weight = 0.0

        weight = max(0.0, min(1.0, float(weight)))
        # El incremento se calcula contra el radio base local para que el perfil
        # hidráulico normal siga siendo el límite inferior en todo momento.
        desired = float(normal_radius) + extra_amplitude * weight
        result.append((Vector(point), max(float(normal_radius), desired)))
    return result


def build_irrigation_outer_wall_object(context, control_points, props, implant_obj=None,
                                        name='DSG_IrrWall', show_wire=True):
    path = build_irrigation_wall_path(control_points, props, implant_obj)
    if len(path) < 2:
        return None
    samples = build_irrigation_profile_samples(
        path, props, surface_point=path[1],
        include_overshoot=False, add_wall=True)
    samples = apply_irrigation_sleeve_volcano_to_outer_samples(
        samples, path[1], props)
    obj = build_variable_radius_tube_object(
        context,
        name,
        samples,
        bevel_resolution=max(24, int(getattr(props, 'irr_bevel_resolution', 8)) + 10),
        show_wire=show_wire,
        subdiv_levels=0,
    )
    if _valid_obj(obj):
        obj.show_in_front = bool(show_wire)
        try:
            obj['DSG_irrigation_wall'] = True
            obj['DSG_analytic_solid'] = True
            obj['DSG_irrigation_sleeve_volcano'] = True
            obj['DSG_irrigation_sleeve_fusion_style'] = 'separated_curvature_and_radius'
            obj['DSG_irrigation_sleeve_volcano_radius'] = float(
                get_irrigation_outer_radius_at_sleeve(props))
            obj['DSG_irrigation_sleeve_base_tube_radius'] = float(
                get_irrigation_base_outer_radius_at_sleeve(props))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def build_irrigation_lumen_preview_object(context, control_points, props,
                                            name='DSG_IrrLumenPreview'):
    samples = build_irrigation_lumen_samples_from_controls(
        control_points, props, include_overshoot=False)
    obj = build_variable_radius_tube_object(
        context,
        name,
        samples,
        bevel_resolution=max(3, int(getattr(props, 'irr_bevel_resolution', 8))),
        show_wire=True,
        subdiv_levels=0,
    )
    if _valid_obj(obj):
        obj.show_in_front = True
        try:
            obj['DSG_irrigation_lumen_preview'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def get_irrigation_lumen_preview(preview_obj):
    if not _valid_obj(preview_obj):
        return None
    try:
        name = str(preview_obj.get('DSG_lumen_preview', ''))
    except Exception:
        name = ''
    obj = bpy.data.objects.get(name) if name else None
    return obj if _valid_obj(obj) else None


def _ensure_irrigation_lumen_diagnostic_material(blocked=False):
    """Material transparente para ver exactamente el lumen interno comprobado."""
    mat_name = IRR_LUMEN_DIAGNOSTIC_MATERIAL + ('_Blocked' if blocked else '_OK')
    material = bpy.data.materials.get(mat_name)
    if material is None:
        material = bpy.data.materials.new(mat_name)
    rgba = (1.0, 0.05, 0.02, 0.46) if blocked else (1.0, 0.78, 0.0, 0.42)
    try:
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        for node in list(nodes):
            nodes.remove(node)
        output = nodes.new('ShaderNodeOutputMaterial')
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.inputs['Base Color'].default_value = rgba
        try:
            principled.inputs['Alpha'].default_value = rgba[3]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            principled.inputs['Roughness'].default_value = 0.34
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        links.new(principled.outputs[0], output.inputs[0])
    except Exception:
        try:
            material.use_nodes = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        material.diffuse_color = rgba
        material.blend_method = 'BLEND'
        material.shadow_method = 'NONE'
        material.use_backface_culling = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def get_irrigation_lumen_diagnostic_object(preview_obj=None):
    if _valid_obj(preview_obj):
        try:
            name = str(preview_obj.get('DSG_lumen_diagnostic', ''))
        except Exception:
            name = ''
        obj = bpy.data.objects.get(name) if name else None
        if _valid_obj(obj):
            return obj
    obj = bpy.data.objects.get(IRR_LUMEN_DIAGNOSTIC_NAME)
    if _valid_obj(obj):
        return obj
    for candidate in bpy.data.objects:
        try:
            if bool(candidate.get('DSG_irrigation_lumen_diagnostic', False)):
                return candidate
        except Exception:
            continue
    return None


def remove_irrigation_lumen_diagnostics(preview_obj=None):
    """Elimina solo los objetos de diagnóstico del lumen, no la pared ni el canal."""
    removed = 0
    names = set()
    if _valid_obj(preview_obj):
        try:
            linked_name = str(preview_obj.get('DSG_lumen_diagnostic', ''))
            if linked_name:
                names.add(linked_name)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    names.add(IRR_LUMEN_DIAGNOSTIC_NAME)
    for obj in list(bpy.data.objects):
        try:
            if obj.name in names or bool(obj.get('DSG_irrigation_lumen_diagnostic', False)):
                if safe_remove_object(obj):
                    removed += 1
        except Exception:
            continue
    return removed


def create_irrigation_lumen_diagnostic_object(context, entry, props, blocked=False, name=None):
    """Crea la geometría exacta que usa el preflight del lumen de agua.

    v7.0.28: el diagnóstico ya no es una sola polilínea que termina en el
    agujero lateral.  Se construye por grupos independientes: conducto externo,
    plenum interno del sleeve, ramas C y salidas redondeadas hacia el lumen del
    sleeve.  Así lo que ves en amarillo/rojo coincide con lo que se comprueba.
    """
    sample_groups = _irrigation_model_preflight_sample_groups(entry, props)
    if sum(len(group) for group in sample_groups) < 2:
        return None, 'No se pudo reconstruir el lumen real comprobado'
    diag_name = name or IRR_LUMEN_DIAGNOSTIC_NAME
    remove_irrigation_lumen_diagnostics(None)

    bm = bmesh.new()
    built_count = 0
    try:
        seg = max(12, int(getattr(props, 'irr_bevel_resolution', 8)) * 2)
        for group in sample_groups:
            samples = [(Vector(center), float(radius)) for center, radius, _outer in group]
            if append_variable_radius_tube_to_bmesh(
                    bm, samples, segments=seg, cap_start=True, cap_end=True):
                built_count += 1
        if built_count == 0 or not bm.verts:
            bm.free()
            return None, 'No se pudo crear la malla del lumen real comprobado'
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        mesh = bpy.data.meshes.new(diag_name + '_Mesh')
        bm.to_mesh(mesh)
        bm.free()
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(diag_name, mesh)
        link_object(context, obj)
    except Exception as exc:
        try:
            bm.free()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return None, f'No se pudo crear la malla del lumen real comprobado: {exc}'

    if not _valid_obj(obj):
        return None, 'No se pudo crear la malla del lumen real comprobado'
    material = _ensure_irrigation_lumen_diagnostic_material(blocked=blocked)
    try:
        obj.data.materials.clear()
        obj.data.materials.append(material)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    rgba = (1.0, 0.05, 0.02, 0.46) if blocked else (1.0, 0.78, 0.0, 0.42)
    try:
        obj.color = rgba
        obj.show_transparent = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj.display_type = 'SOLID'
    obj.show_in_front = True
    obj.hide_render = True
    try:
        obj['DSG_irrigation_lumen_diagnostic'] = True
        obj['DSG_irrigation_exact_preflight_lumen'] = True
        obj['DSG_irrigation_lumen_diagnostic_status'] = 'BLOCKED' if blocked else 'OK'
        obj['DSG_irrigation_lumen_sample_count'] = int(sum(len(group) for group in sample_groups))
        obj['DSG_irrigation_lumen_group_count'] = int(len(sample_groups))
        obj['DSG_irrigation_includes_sleeve_manifold'] = True
        if isinstance(entry, dict):
            obj['DSG_irrigation_lumen_entry_index'] = int(entry.get('index', -1))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        link_object_to_dsg_collection(obj, ROLE_IRRIGATION)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        _ensure_solid_material_coloring(context)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    set_active(context, obj)
    return obj, ''


def build_pending_irrigation_lumen_diagnostic(context, props, preview=None, blocked=False):
    preview = preview if _valid_obj(preview) else get_pending_irrigation_preview(props)
    if not _valid_obj(preview):
        return None, 'No hay vista previa pendiente de irrigación'
    controls = get_irrigation_preview_path_world(preview)
    if len(controls) < 3:
        return None, 'El eje interno no es válido'
    implant = bpy.data.objects.get(str(preview.get('DSG_implant', '')))
    if not is_valid_implant_obj(implant):
        implant = get_nearest_implant_to_point(props, controls[1])
    parameters = irrigation_parameters_from_object(preview, props)
    entry = {
        'points': [Vector(point) for point in controls],
        'implant': implant if is_valid_implant_obj(implant) else None,
        'implant_name': _safe_object_name(implant),
        'parameters': parameters,
        'index': int(getattr(props, 'irr_chain_count', 0)),
        'link': False,
    }
    obj, error = create_irrigation_lumen_diagnostic_object(
        context, entry, props, blocked=blocked, name=IRR_LUMEN_DIAGNOSTIC_NAME)
    if _valid_obj(obj):
        try:
            preview['DSG_lumen_diagnostic'] = obj.name
            obj['DSG_preview_source'] = preview.name
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj, error


def remove_irrigation_preview_bundle(preview_obj, remove_curve=True):
    curve_obj = get_irrigation_preview_curve(preview_obj) if _valid_obj(preview_obj) else None
    lumen_obj = get_irrigation_lumen_preview(preview_obj) if _valid_obj(preview_obj) else None
    remove_irrigation_lumen_diagnostics(preview_obj)
    safe_remove_object(preview_obj)
    safe_remove_object(lumen_obj)
    if remove_curve:
        safe_remove_object(curve_obj)


def build_blended_irrigation_outer_tube_mesh(context, points, outer_radius, props, implant_obj=None,
                                             name='DSG_IrrOuter', bevel_resolution=8, smooth_iters=2,
                                             entry_mode='full'):
    """Compatibilidad: ahora construye la pared desde los controles del eje interno."""
    return build_irrigation_outer_wall_object(
        context, points, props, implant_obj=implant_obj, name=name, show_wire=False)


def build_irrigation_combined_lumen_cutter(context, path_entries, props,
                                            report_prefix='', name='DSG_Irr_AllLumenCut'):
    """Un único cutter que atraviesa paredes externas y sleeves."""
    entries = list(path_entries or [])
    if not entries:
        return None, 0

    safe_remove_by_name(name)
    bm = bmesh.new()
    built_count = 0
    seg = max(12, int(getattr(props, 'irr_bevel_resolution', 8)) * 2)

    for index, entry in enumerate(entries):
        controls = entry.get('points', []) if isinstance(entry, dict) else []
        if len(controls) < 2:
            continue
        try:
            entry_props, _parameters = _irrigation_entry_effective_props(props, entry)
        except Exception:
            entry_props = props
        samples = build_irrigation_lumen_samples_from_controls(
            controls, entry_props, include_overshoot=True)
        try:
            samples = _apply_entry_midpoint_geometry(samples, entry, [])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if len(samples) < 2:
            continue
        try:
            if append_variable_radius_tube_to_bmesh(
                    bm, samples, segments=seg, cap_start=True, cap_end=True):
                built_count += 1
        except Exception as exc:
            print(f'[DSG] Could not add internal path {index}: {exc}')

    if built_count == 0 or not bm.verts:
        bm.free()
        return None, 0
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    mesh = bpy.data.meshes.new(name + '_Mesh')
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)

    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.display_type = 'WIRE'
    obj.show_in_front = True
    register_dsg_object(obj, ROLE_CUTTER, name, {
        'DSG_cut_type': 'irrigation_centerline_combined',
        'DSG_analytic_solid': True,
    })
    return obj, built_count



def append_hollow_variable_radius_tube_to_bmesh(bm, samples, wall_thickness,
                                                  segments=16, cap_start=True, cap_end=True):
    """Construye una pared hueca con radio exterior opcionalmente independiente.

    Formatos aceptados por muestra:
    ``(centro, radio_interior)``: exterior = interior + espesor constante.
    ``(centro, radio_interior, radio_exterior)``: permite una base volcánica
    exterior sin modificar en absoluto el lumen hidráulico.
    """
    clean = []
    thickness = max(0.02, float(wall_thickness))
    for item in samples:
        if not item or len(item) not in {2, 3}:
            continue
        point = Vector(item[0])
        inner_radius = max(0.02, float(item[1]))
        if len(item) == 3:
            outer_radius = max(inner_radius + 0.02, float(item[2]))
        else:
            outer_radius = inner_radius + thickness
        if clean and (point - clean[-1][0]).length < 0.01:
            previous = clean[-1]
            clean[-1] = (
                previous[0],
                max(previous[1], inner_radius),
                max(previous[2], outer_radius),
            )
        else:
            clean.append((point, inner_radius, outer_radius))
    if len(clean) < 2:
        return False

    points = [item[0] for item in clean]
    frames = _build_transport_frames(points)
    if len(frames) != len(points):
        return False

    seg = max(12, int(segments))
    outer_rings = []
    inner_rings = []
    for (point, inner_radius, outer_radius), (u, v, _tangent) in zip(clean, frames):
        outer_ring = []
        inner_ring = []
        for i in range(seg):
            angle = 2.0 * math.pi * i / seg
            direction = u * math.cos(angle) + v * math.sin(angle)
            outer_ring.append(bm.verts.new(point + direction * outer_radius))
            inner_ring.append(bm.verts.new(point + direction * inner_radius))
        outer_rings.append(outer_ring)
        inner_rings.append(inner_ring)

    for ring_index in range(len(outer_rings) - 1):
        outer_a = outer_rings[ring_index]
        outer_b = outer_rings[ring_index + 1]
        inner_a = inner_rings[ring_index]
        inner_b = inner_rings[ring_index + 1]
        for i in range(seg):
            j = (i + 1) % seg
            try:
                bm.faces.new((outer_a[i], outer_a[j], outer_b[j], outer_b[i]))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                # Orden inverso: la normal de la piel interior apunta al lumen.
                bm.faces.new((inner_a[j], inner_a[i], inner_b[i], inner_b[j]))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    if cap_start:
        for i in range(seg):
            j = (i + 1) % seg
            try:
                bm.faces.new((outer_rings[0][j], outer_rings[0][i],
                              inner_rings[0][i], inner_rings[0][j]))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    if cap_end:
        last = len(outer_rings) - 1
        for i in range(seg):
            j = (i + 1) % seg
            try:
                bm.faces.new((outer_rings[last][i], outer_rings[last][j],
                              inner_rings[last][j], inner_rings[last][i]))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def apply_venturi_profile_to_samples(samples, venturi_specs=None):
    """Compatibility no-op: the common-trunk Venturi is intentionally disabled.

    A Venturi increases local velocity but does not, by itself, guarantee equal
    flow distribution between two daughter branches. In this addon it also
    created an unwanted geometric waist near the Y junction. Flow balancing is
    now performed with identical calibrated restrictions in BOTH daughter
    branches after the split, which is the fixed-geometry equivalent of using
    balancing valves/orifices in plumbing systems.
    """
    return [(Vector(point), float(radius)) for point, radius in samples]



def apply_balancing_nozzle_after_split(samples, split_points,
                                         throat_diameter=0.80,
                                         inlet_transition=0.35,
                                         throat_length=0.90,
                                         outlet_transition=0.60,
                                         split_clearance=0.70):
    """Applies a smooth metering nozzle only inside a daughter branch.

    The common trunk and the central plenum are never restricted.  A diameter
    at or above the normal Ø1 mm lumen, or a zero throat length, is treated as
    an intentional no-op.  This permits minimum-loss balancing: only the easier
    daughter receives extra resistance.
    """
    clean = [(Vector(point), float(radius)) for point, radius in samples]
    if len(clean) < 3:
        return clean

    throat_diameter = float(throat_diameter)
    throat_length = float(throat_length)
    if throat_diameter >= 0.995 or throat_length <= 0.01:
        return clean

    points = [item[0] for item in clean]
    radii = [item[1] for item in clean]
    throat_radius = max(0.20, throat_diameter * 0.5)
    split_clearance = max(0.30, float(split_clearance))
    inlet_transition = max(0.15, float(inlet_transition))
    throat_length = max(0.20, throat_length)
    outlet_transition = max(0.15, float(outlet_transition))
    profile_end = split_clearance + inlet_transition + throat_length + outlet_transition

    unique_splits = []
    for raw in list(split_points or []):
        try:
            split = Vector(raw)
        except Exception:
            continue
        if all((split - existing).length > 0.20 for existing in unique_splits):
            unique_splits.append(split)

    def radius_for_distance(base_radius, distance_from_split):
        if distance_from_split <= split_clearance:
            return base_radius
        local = distance_from_split - split_clearance
        if local <= inlet_transition:
            t = _smootherstep01(local / inlet_transition)
            return base_radius + (throat_radius - base_radius) * t
        local -= inlet_transition
        if local <= throat_length:
            return throat_radius
        local -= throat_length
        if local <= outlet_transition:
            t = _smootherstep01(local / outlet_transition)
            return throat_radius + (base_radius - throat_radius) * t
        return base_radius

    for split in unique_splits:
        split_index = min(range(len(points)), key=lambda idx: (points[idx] - split).length)
        distance_from_split = 0.0
        # Saved irrigation paths run from the sleeve towards the inlet.  The
        # daughter side is therefore the decreasing-index side of the split.
        for idx in range(split_index, -1, -1):
            if idx < split_index:
                distance_from_split += (points[idx + 1] - points[idx]).length
            if distance_from_split > profile_end:
                break
            base_radius = radii[idx]
            if base_radius > 0.60:
                continue
            desired = radius_for_distance(base_radius, distance_from_split)
            radii[idx] = min(base_radius, max(throat_radius, desired))

    return [(point, radius) for point, radius in zip(points, radii)]


def build_irrigation_junction_cutter(context, entry, name='DSG_IrrLinkJunctionCut'):
    """Builds one fused cutter that opens a true Y junction in both closed walls.

    The cutter contains a common trunk and two angled daughter branches. This
    removes the orthogonal T-shape and opens the origins of both daughter
    channels so neither sleeve path remains partially blocked.
    """
    parts = build_irrigation_link_y_parts(context, entry, name_prefix=name + '_Part')
    if not parts:
        return None
    cutter = build_combined_mesh_object_world(context, parts, name)
    for obj in parts:
        safe_remove_object(obj)
    if not _valid_obj(cutter):
        return None

    cutter.display_type = 'WIRE'
    cutter.show_in_front = True
    try:
        remesh = cutter.modifiers.new(name + '_Fuse', 'REMESH')
        remesh.mode = 'VOXEL'
        remesh.voxel_size = 0.055
        remesh.use_smooth_shade = True
        if apply_modifier_direct(context, cutter, remesh.name):
            cleanup_boolean_result_minimal(cutter, merge_dist=0.0004)
    except Exception as exc:
        print(f'[DSG] Irrigation junction cutter fusion skipped: {exc}')

    try:
        cutter['DSG_irrigation_junction_cutter'] = True
        cutter['DSG_irrigation_balancing_nozzle_diameter'] = 0.80
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return cutter


def _merge_irrigation_inner_outer_profiles(inner_samples, outer_samples, wall_thickness):
    """Une perfiles coincidentes para construir lumen y exterior independientes."""
    inner = [(Vector(point), max(0.02, float(radius)))
             for point, radius in list(inner_samples or [])]
    outer = [(Vector(point), max(0.04, float(radius)))
             for point, radius in list(outer_samples or [])]
    if not inner:
        return []
    thickness = max(0.02, float(wall_thickness))
    if not outer:
        return [(point, radius, radius + thickness) for point, radius in inner]

    merged = []
    for point, inner_radius in inner:
        nearest_point, nearest_outer = min(
            outer, key=lambda item: (item[0] - point).length)
        if (nearest_point - point).length > 0.12:
            outer_radius = inner_radius + thickness
        else:
            outer_radius = max(inner_radius + 0.02, nearest_outer)
        merged.append((point, inner_radius, outer_radius))
    return merged


def build_irrigation_hollow_wall_object(context, control_points, props, implant_obj=None,
                                          name='DSG_IrrHollowWall', show_wire=False, cap_end=True,
                                          venturi_specs=None):
    """Builds a manifold hollow wall directly from the irrigation centerline.

    ``cap_end=True`` creates an annular end face between the outer and inner
    rings. It closes the wall shell but never plugs the central lumen.
    """
    path = build_irrigation_wall_path(control_points, props, implant_obj)
    if len(path) < 2:
        return None
    wall_thickness = max(0.05, float(getattr(props, 'irr_wall_thickness', 1.5)))
    inner_samples = build_irrigation_profile_samples(
        path, props, surface_point=path[1],
        include_overshoot=False, add_wall=False)
    inner_samples = apply_venturi_profile_to_samples(inner_samples, venturi_specs)
    if len(inner_samples) < 2:
        return None

    # La pared final se construye directamente hueca. Por eso el volcán debe
    # aplicarse al perfil EXTERIOR antes de generar sus aros; aplicarlo solo a la
    # preview no sobrevivía a esta reconstrucción.
    outer_samples = [
        (Vector(point), float(inner_radius) + wall_thickness)
        for point, inner_radius in inner_samples
    ]
    outer_samples = apply_irrigation_sleeve_volcano_to_outer_samples(
        outer_samples, path[1], props)
    hollow_samples = _merge_irrigation_inner_outer_profiles(
        inner_samples, outer_samples, wall_thickness)

    safe_remove_by_name(name)
    bm = bmesh.new()
    ok = append_hollow_variable_radius_tube_to_bmesh(
        bm, hollow_samples, wall_thickness,
        segments=max(48, int(getattr(props, 'irr_bevel_resolution', 8)) * 6),
        cap_start=True, cap_end=bool(cap_end),
    )
    if not ok or not bm.verts:
        bm.free()
        return None
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name + '_Mesh')
    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.display_type = 'WIRE' if show_wire else 'SOLID'
    obj.show_in_front = bool(show_wire)
    try:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj.data.update(calc_edges=True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    register_dsg_object(obj, ROLE_IRRIGATION, name, {
        'DSG_irrigation_hollow_wall': True,
        'DSG_analytic_solid': True,
        'DSG_irrigation_venturi': bool(venturi_specs),
        'DSG_irrigation_venturi_throat_diameter': 0.80 if venturi_specs else 0.0,
        'DSG_irrigation_sleeve_volcano': True,
        'DSG_irrigation_sleeve_volcano_final_wall': True,
        'DSG_irrigation_sleeve_fusion_style': 'separated_curvature_and_radius',
        'DSG_irrigation_body_wall_thickness': float(getattr(props, 'irr_wall_thickness', IRRIGATION_SLIM_WALL_THICKNESS_DEFAULT_MM)),
        'DSG_irrigation_sleeve_volcano_radius': float(get_irrigation_outer_radius_at_sleeve(props)),
    })
    return obj


def _irrigation_entry_effective_props(props, entry):
    parameters = dict(entry.get('parameters', {}) if isinstance(entry, dict) else {})
    parameters['irr_funnel_enabled'] = True
    if bool(entry.get('link', False)):
        parameters['irr_inner_diameter'] = 1.0
        parameters['irr_funnel_outer_diameter'] = 1.0
        parameters['irr_taper_length'] = 0.0
        parameters['irr_funnel_enabled'] = True
        parameters['irr_link_continuous_1mm'] = True
    return irrigation_props_overlay(props, parameters), parameters


def _fuse_irrigation_solids_with_voxel(context, objects, name, voxel_size):
    combined = build_combined_mesh_object_world(context, objects, name)
    for obj in list(objects):
        safe_remove_object(obj)
    if not _valid_obj(combined):
        return None
    try:
        remesh = combined.modifiers.new(name + '_Fuse', 'REMESH')
        remesh.mode = 'VOXEL'
        remesh.voxel_size = float(voxel_size)
        remesh.use_smooth_shade = True
        if not apply_modifier_direct(context, combined, remesh.name):
            safe_remove_object(combined)
            return None
        cleanup_boolean_result_minimal(combined, merge_dist=max(0.0003, float(voxel_size) * 0.01))
    except Exception as exc:
        print(f'[DSG] Irrigation network voxel fusion failed: {exc}')
        safe_remove_object(combined)
        return None
    return combined



def _entry_vector(entry, *keys):
    for key in keys:
        raw = entry.get(key) if isinstance(entry, dict) else None
        if raw is None:
            continue
        try:
            return Vector(raw)
        except Exception:
            continue
    return None


def _sample_cubic_bezier_segment(p0, p1, p2, p3, max_step=0.18):
    p0, p1, p2, p3 = map(Vector, (p0, p1, p2, p3))
    estimate = (p1 - p0).length + (p2 - p1).length + (p3 - p2).length
    count = max(6, min(64, int(math.ceil(estimate / max(0.05, float(max_step)))) + 1))
    points = []
    for index in range(count):
        t = index / max(1, count - 1)
        u = 1.0 - t
        points.append(
            p0 * (u ** 3)
            + p1 * (3.0 * u * u * t)
            + p2 * (3.0 * u * t * t)
            + p3 * (t ** 3)
        )
    return points


def _midpoint_wye_metadata(link_entry):
    """Returns the complete adaptive midpoint-manifold geometry.

    New links store every local anchor explicitly.  Older links are upgraded in
    memory to a compatible geometry so saved projects remain usable.
    """
    try:
        split = _entry_vector(
            link_entry, 'link_split_center', 'link_split_point',
            'link_manifold_center', 'link_channel_point')
        source = _entry_vector(link_entry, 'link_channel_point')
        trunk = _entry_vector(
            link_entry, 'link_trunk_direction', 'link_source_tangent')
        if split is None or trunk is None:
            return None
        if trunk.length < 1e-8:
            return None
        trunk.normalize()                         # sleeve -> external inlet
        flow_out = -trunk                         # inlet -> source sleeve

        lateral = _entry_vector(link_entry, 'link_lateral')
        if lateral is None:
            lateral = Vector((1.0, 0.0, 0.0))
        lateral = lateral - trunk * lateral.dot(trunk)
        if lateral.length < 1e-8:
            basis_u, _basis_v, _axis = build_axis_basis(trunk)
            lateral = basis_u
        lateral.normalize()

        common_anchor = _entry_vector(link_entry, 'link_common_anchor', 'link_trunk_point')
        main_rejoin = _entry_vector(link_entry, 'link_main_rejoin', 'link_source_rejoin')
        main_shoulder = _entry_vector(link_entry, 'link_main_shoulder', 'link_source_shoulder')
        link_shoulder = _entry_vector(link_entry, 'link_link_shoulder')
        link_rejoin = _entry_vector(link_entry, 'link_link_rejoin')
        branch_midpoint = _entry_vector(link_entry, 'link_branch_midpoint')

        if source is None:
            source = split - flow_out * 0.20
        angle_deg = max(18.0, min(42.0, float(
            link_entry.get('link_branch_angle_deg', 30.0) or 30.0)))
        angle = math.radians(angle_deg)
        main_dir = (flow_out * math.cos(angle) - lateral * math.sin(angle)).normalized()
        link_dir = (flow_out * math.cos(angle) + lateral * math.sin(angle)).normalized()

        if common_anchor is None:
            common_anchor = source + trunk * 1.10
        if main_rejoin is None:
            main_rejoin = source + flow_out * 2.10
        if main_shoulder is None:
            main_shoulder = split + main_dir * 1.10
        if link_shoulder is None:
            link_shoulder = split + link_dir * 1.10
        if link_rejoin is None:
            link_rejoin = link_shoulder.copy()
        if branch_midpoint is None:
            branch_midpoint = (main_shoulder + link_shoulder) * 0.5

        return {
            'split': split,
            'source': source,
            'trunk': trunk,
            'flow_out': flow_out,
            'lateral': lateral,
            'common_anchor': common_anchor,
            'main_rejoin': main_rejoin,
            'main_shoulder': main_shoulder,
            'link_shoulder': link_shoulder,
            'link_rejoin': link_rejoin,
            'branch_midpoint': branch_midpoint,
            'angle_deg': angle_deg,
            'plenum_radius': max(0.52, min(0.62, float(
                link_entry.get('link_plenum_radius', 0.55) or 0.55))),
        }
    except Exception:
        return None


def _forced_wye_metadata(link_entry):
    """Compatibility tuple used by older callers."""
    meta = _midpoint_wye_metadata(link_entry)
    if meta is None:
        return None
    return meta['split'], meta['trunk'], meta['lateral'], meta['angle_deg']


def _deduplicate_radius_samples(samples, epsilon=0.012):
    result = []
    for point, radius in samples:
        point = Vector(point)
        radius = float(radius)
        if result and (point - result[-1][0]).length < epsilon:
            result[-1] = (point, max(radius, result[-1][1]))
        else:
            result.append((point, radius))
    return result


def force_source_samples_into_balanced_wye(samples, link_entry):
    """Replaces the old straight source segment with a new midpoint Y.

    The source path is cut at two real samples: one towards its sleeve and one
    towards the external inlet.  Everything between them is discarded.  A new
    main daughter, central split and common entrance are then generated from the
    stored manifold anchors.  No obsolete straight-through lumen survives.
    """
    meta = _midpoint_wye_metadata(link_entry)
    clean = [(Vector(point), float(radius)) for point, radius in list(samples or [])]
    if meta is None or len(clean) < 6:
        return clean

    points = [item[0] for item in clean]
    source_index = min(range(len(points)), key=lambda i: (points[i] - meta['source']).length)
    main_index = min(range(len(points)), key=lambda i: (points[i] - meta['main_rejoin']).length)
    common_index = min(range(len(points)), key=lambda i: (points[i] - meta['common_anchor']).length)

    # Samples are sleeve -> inlet.  Recover deterministic anchors if nearest
    # projections happen to fall on the wrong side of a strongly curved path.
    if main_index >= source_index:
        main_index = source_index
        travelled = 0.0
        while main_index > 0 and travelled < 1.65:
            travelled += (points[main_index] - points[main_index - 1]).length
            main_index -= 1
    if common_index <= source_index:
        common_index = source_index
        travelled = 0.0
        while common_index < len(points) - 1 and travelled < 1.00:
            travelled += (points[common_index + 1] - points[common_index]).length
            common_index += 1
    if main_index >= common_index:
        return clean

    main_anchor, main_radius = clean[main_index]
    common_anchor, common_radius = clean[common_index]
    junction_radius = min(0.55, main_radius, common_radius)

    # Two controlled Bézier pieces meet at the calculated split.  The first
    # follows the main daughter shoulder; the second bends the inlet smoothly
    # from the original channel into the center of the Y.
    d_main = max(0.30, (meta['split'] - main_anchor).length)
    p1_main = main_anchor.lerp(meta['main_shoulder'], 0.62)
    p2_main = meta['main_shoulder']
    main_curve = _sample_cubic_bezier_segment(
        main_anchor, p1_main, p2_main, meta['split'], max_step=0.16)

    common_dir = common_anchor - meta['split']
    if common_dir.length < 1e-8:
        common_dir = meta['trunk']
    common_dir.normalize()
    d_common = max(0.30, (common_anchor - meta['split']).length)
    p1_common = meta['split'] + common_dir * min(d_common * 0.42, 0.65)
    local_tangent = points[min(len(points) - 1, common_index + 1)] - points[max(0, common_index - 1)]
    if local_tangent.length < 1e-8:
        local_tangent = meta['trunk']
    local_tangent.normalize()
    p2_common = common_anchor - local_tangent * min(d_common * 0.34, 0.55)
    common_curve = _sample_cubic_bezier_segment(
        meta['split'], p1_common, p2_common, common_anchor, max_step=0.16)

    local_points = main_curve + common_curve[1:]
    local_samples = []
    split_pos = max(1, len(main_curve) - 1)
    last = max(1, len(local_points) - 1)
    for idx, point in enumerate(local_points):
        if idx <= split_pos:
            t = idx / split_pos
            radius = main_radius + (junction_radius - main_radius) * t
        else:
            t = (idx - split_pos) / max(1, last - split_pos)
            radius = junction_radius + (common_radius - junction_radius) * t
        local_samples.append((Vector(point), float(radius)))

    return _deduplicate_radius_samples(
        clean[:main_index] + local_samples + clean[common_index + 1:])


def reshape_link_samples_into_midpoint_wye(samples, link_entry):
    """Rebuilds the linked daughter up to the same calculated split center."""
    meta = _midpoint_wye_metadata(link_entry)
    clean = [(Vector(point), float(radius)) for point, radius in list(samples or [])]
    if meta is None or len(clean) < 4:
        return clean

    points = [item[0] for item in clean]
    shoulder_index = min(
        range(len(points)), key=lambda i: (points[i] - meta['link_rejoin']).length)
    # Keep the complete sleeve-side path and discard every old terminal piece.
    shoulder_index = max(1, min(shoulder_index, len(clean) - 2))
    anchor, anchor_radius = clean[shoulder_index]
    distance = max(0.35, (meta['split'] - anchor).length)
    p1 = anchor.lerp(meta['link_shoulder'], 0.62)
    p2 = meta['link_shoulder']
    curve = _sample_cubic_bezier_segment(
        anchor, p1, p2, meta['split'], max_step=0.16)

    local = []
    last = max(1, len(curve) - 1)
    target_radius = min(0.55, anchor_radius)
    for idx, point in enumerate(curve):
        t = idx / last
        radius = anchor_radius + (target_radius - anchor_radius) * t
        local.append((Vector(point), float(radius)))
    return _deduplicate_radius_samples(clean[:shoulder_index] + local)


def irrigation_branch_length_to_split(samples, split_point):
    """Approximate sleeve-to-split centreline length for one daughter."""
    clean = [(Vector(point), float(radius)) for point, radius in samples]
    if len(clean) < 2:
        return 0.0
    split = Vector(split_point)
    split_index = min(range(len(clean)), key=lambda i: (clean[i][0] - split).length)
    length = 0.0
    for i in range(split_index):
        length += (clean[i + 1][0] - clean[i][0]).length
    length += (clean[split_index][0] - split).length
    return max(0.0, float(length))


def irrigation_branch_resistance_to_split(samples, split_point,
                                            minimum_diameter=0.20):
    """Numerically estimates relative Hagen-Poiseuille resistance to the Y.

    For laminar flow in a circular tube, resistance is proportional to
    ``integral(ds / D(s)^4)``.  Integrating the sampled diameter profile is more
    faithful than assuming every branch is a perfect Ø1 mm cylinder.
    The common viscosity and pi/128 factors cancel when the two branches are
    compared, so this function intentionally returns relative resistance units.
    """
    clean = [(Vector(point), float(radius)) for point, radius in samples]
    if len(clean) < 2:
        return 0.0

    split = Vector(split_point)
    split_index = min(range(len(clean)), key=lambda i: (clean[i][0] - split).length)
    resistance = 0.0

    for i in range(split_index):
        p0, r0 = clean[i]
        p1, r1 = clean[i + 1]
        ds = (p1 - p0).length
        diameter = max(float(minimum_diameter), float(r0 + r1))
        resistance += ds / (diameter ** 4)

    # Include the residual distance from the closest sample to the exact split.
    p_last, r_last = clean[split_index]
    ds_last = (p_last - split).length
    diameter_last = max(float(minimum_diameter), float(r_last) * 2.0)
    resistance += ds_last / (diameter_last ** 4)
    return max(0.0, float(resistance))



def calculate_length_compensated_nozzles(source_samples, link_samples, split_point,
                                           throat_length=0.90,
                                           min_diameter=0.72,
                                           max_diameter=0.94,
                                           lumen_diameter=1.00,
                                           split_clearance=0.70,
                                           inlet_transition=0.35,
                                           outlet_transition=0.50,
                                           end_clearance=0.25,
                                           activation_error=0.02):
    """Minimum-loss passive balance for two daughter branches.

    The naturally harder branch remains at the full Ø1 mm lumen.  Only the
    easier branch receives the exact additional Hagen-Poiseuille resistance
    required to match it.  Diameter is solved first; when Ø0.72 mm would be
    exceeded, throat length is increased instead.  This maximises delivered
    flow while retaining a passive near-50/50 split.
    """
    source_length = irrigation_branch_length_to_split(source_samples, split_point)
    link_length = irrigation_branch_length_to_split(link_samples, split_point)
    r_source = irrigation_branch_resistance_to_split(source_samples, split_point)
    r_link = irrigation_branch_resistance_to_split(link_samples, split_point)

    nominal_length = max(0.30, float(throat_length))
    d_min = max(0.20, float(min_diameter))
    d_max = max(d_min + 1e-6, min(float(max_diameter), float(lumen_diameter) - 0.01))
    d_lumen = max(d_max + 0.01, float(lumen_diameter))
    reserved = (max(0.30, float(split_clearance))
                + max(0.15, float(inlet_transition))
                + max(0.15, float(outlet_transition))
                + max(0.0, float(end_clearance)))
    available = {
        'source': max(0.0, source_length - reserved),
        'link': max(0.0, link_length - reserved),
    }
    base = {'source': r_source, 'link': r_link}
    harder = 'source' if r_source >= r_link else 'link'
    easier = 'link' if harder == 'source' else 'source'
    target = base[harder]
    mean_r = max(1e-9, 0.5 * (r_source + r_link))
    natural_error = abs(r_source - r_link) / mean_r

    result = {
        'source': {
            'diameter': d_lumen, 'throat_length': 0.0,
            'predicted': r_source, 'exact': True, 'limited_by': ''},
        'link': {
            'diameter': d_lumen, 'throat_length': 0.0,
            'predicted': r_link, 'exact': True, 'limited_by': ''},
    }

    if natural_error > max(0.0, float(activation_error)):
        delta = max(0.0, target - base[easier])
        room = available[easier]
        exact = True
        limited_by = ''
        diameter = d_lumen
        use_length = 0.0

        if room < 0.20:
            exact = False
            limited_by = 'NO_PRINTABLE_SPACE'
        else:
            use_length = min(nominal_length, room)
            inv_d4 = (delta / max(1e-9, use_length)) + (1.0 / d_lumen ** 4)
            diameter = inv_d4 ** (-0.25)

            if diameter > d_max:
                coefficient = (1.0 / d_max ** 4) - (1.0 / d_lumen ** 4)
                required_length = delta / max(1e-9, coefficient)
                if required_length < 0.20:
                    # Difference is too small to justify a printable nozzle.
                    diameter = d_lumen
                    use_length = 0.0
                    limited_by = 'BELOW_PRINTABLE_ACTIVATION'
                elif required_length <= room:
                    diameter = d_max
                    use_length = required_length
                else:
                    diameter = d_max
                    use_length = room
                    exact = False
                    limited_by = 'MAX_DIAMETER_AND_AVAILABLE_LENGTH'

            elif diameter < d_min:
                coefficient = (1.0 / d_min ** 4) - (1.0 / d_lumen ** 4)
                required_length = delta / max(1e-9, coefficient)
                diameter = d_min
                if required_length <= room:
                    use_length = max(0.20, required_length)
                    limited_by = 'THROAT_LENGTH_EXTENDED_AT_MIN_DIAMETER'
                else:
                    use_length = room
                    exact = False
                    limited_by = 'MIN_DIAMETER_AND_AVAILABLE_LENGTH'

        predicted = base[easier]
        if use_length > 0.0 and diameter < d_lumen:
            predicted += use_length * (
                (1.0 / diameter ** 4) - (1.0 / d_lumen ** 4))
        result[easier] = {
            'diameter': float(diameter),
            'throat_length': float(use_length),
            'predicted': float(predicted),
            'exact': bool(exact),
            'limited_by': limited_by,
        }

    predicted_source = float(result['source']['predicted'])
    predicted_link = float(result['link']['predicted'])
    denominator = max(1e-9, 0.5 * (predicted_source + predicted_link))
    relative_error = abs(predicted_source - predicted_link) / denominator
    conductance_source = 1.0 / max(1e-9, predicted_source)
    conductance_link = 1.0 / max(1e-9, predicted_link)
    conductance_sum = max(1e-9, conductance_source + conductance_link)

    return {
        'source_diameter': float(result['source']['diameter']),
        'link_diameter': float(result['link']['diameter']),
        'source_throat_length': float(result['source']['throat_length']),
        'link_throat_length': float(result['link']['throat_length']),
        'source_length': float(source_length),
        'link_length': float(link_length),
        'source_baseline_resistance': float(r_source),
        'link_baseline_resistance': float(r_link),
        'target_equivalent_resistance': float(target),
        'source_predicted_total_resistance': predicted_source,
        'link_predicted_total_resistance': predicted_link,
        'relative_resistance_error': float(relative_error),
        'predicted_source_flow_fraction': float(conductance_source / conductance_sum),
        'predicted_link_flow_fraction': float(conductance_link / conductance_sum),
        'exact_balance_possible': bool(
            result['source']['exact'] and result['link']['exact']
            and relative_error <= 0.01),
        'source_limit': result['source']['limited_by'],
        'link_limit': result['link']['limited_by'],
        'restricted_branch': easier if natural_error > activation_error else 'NONE',
        'natural_relative_resistance_error': float(natural_error),
        'split_clearance': float(split_clearance),
        'balancing_mode': 'MINIMUM_LOSS_POISEUILLE_SINGLE_BRANCH',
    }



def _add_forced_wye_plenum_part(context, parts, link_entry, radius, name):
    """Adds a compact overlap chamber at the calculated midpoint split."""
    meta = _midpoint_wye_metadata(link_entry)
    if meta is None:
        return None
    effective_radius = max(float(radius), float(meta['plenum_radius']))
    mesh = make_uv_sphere_mesh(name + '_Mesh', max(0.10, effective_radius), 24, 12)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = meta['split']
    link_object(context, obj)
    obj.display_type = 'WIRE'
    obj.show_in_front = True
    parts.append(obj)
    return obj



def _calculate_midpoint_wye_balances(source_entry, wye_specs, props):
    """Hydraulic design of a linked network.

    * Sequential opening (default, 9.7.1): see ``irrigation_network``. Each Y
      throttles the trunk towards the initial sleeve so that the sleeve
      perforated next receives most of the flow. Returns
      ``{'mode': 'SEQUENTIAL_OPENING', ...}``.
    * Legacy: nozzle-free, full Ø1 mm everywhere (returns ``{}``).
    """
    if wye_specs and irrigation_sequential_enabled(props):
        try:
            return sequential_wye_balances(source_entry, wye_specs, props)
        except Exception as exc:
            _DSG_LOG.warning('sequential irrigation design failed, using full lumen: %s', exc, exc_info=True)
    return {}


def _apply_entry_midpoint_geometry(samples, entry, wye_specs):
    if bool(entry.get('link', False)):
        return reshape_link_samples_into_midpoint_wye(samples, entry)
    shaped = list(samples)
    for spec in list(wye_specs or []):
        shaped = force_source_samples_into_balanced_wye(shaped, spec)
    return shaped


def _apply_entry_balancing(samples, entry, wye_specs, balances):
    """Sequential mode: metering throats on the trunk towards the initial sleeve.

    Linked daughters always keep the full lumen; in legacy mode nothing changes.
    """
    if (not isinstance(balances, dict) or balances.get('mode') != 'SEQUENTIAL_OPENING'
            or bool(entry.get('link', False))):
        return list(samples)
    return apply_sequential_trunk_throats(samples, balances)


def build_irrigation_y_network_hollow_wall(context, source_entry, link_entries, props,
                                             name='DSG_IrrYNetworkWall'):
    """Builds a new adaptive manifold instead of preserving the old junction.

    The selected source region is deleted locally.  A common entrance bends into
    the midpoint split, and two fresh daughters are generated.  The lumen and
    outer body are fused independently, then hollowed once.  Only the easier
    daughter is metered, maximising total water delivery.
    """
    link_entries = order_links_along_trunk(source_entry, link_entries, props)
    entries = [source_entry] + list(link_entries or [])
    if len(entries) < 2:
        return None
    wye_specs = list(link_entries or [])
    outer_parts, inner_parts = [], []
    balances = _calculate_midpoint_wye_balances(source_entry, wye_specs, props)

    try:
        for local_index, entry in enumerate(entries):
            entry_props, _parameters = _irrigation_entry_effective_props(props, entry)
            controls = entry.get('points', [])
            if len(controls) < 2:
                raise RuntimeError(f'entry {local_index + 1} has no valid path')
            implant = entry.get('implant')

            wall_path = build_irrigation_wall_path(controls, entry_props, implant)
            if len(wall_path) < 2:
                raise RuntimeError(f'entry {local_index + 1} has no wall path')
            outer_lumen = build_irrigation_profile_samples(
                wall_path, entry_props, surface_point=wall_path[1],
                include_overshoot=False, add_wall=False)
            outer_lumen = _apply_entry_midpoint_geometry(
                outer_lumen, entry, wye_specs)

            wall_thickness = max(
                0.05, float(getattr(entry_props, 'irr_wall_thickness', 1.5)))
            outer_samples = [
                (Vector(point), float(radius) + wall_thickness)
                for point, radius in outer_lumen]
            outer_samples = apply_irrigation_sleeve_volcano_to_outer_samples(
                outer_samples, wall_path[1], entry_props)
            outer_obj = build_variable_radius_tube_object(
                context, f'{name}_OuterPart_{local_index:02d}', outer_samples,
                bevel_resolution=max(3, int(getattr(entry_props, 'irr_bevel_resolution', 8))),
                show_wire=True, subdiv_levels=0)
            if not _valid_obj(outer_obj):
                raise RuntimeError(f'could not build outer part {local_index + 1}')
            outer_parts.append(outer_obj)

            inner_samples = build_irrigation_lumen_samples_from_controls(
                controls, entry_props, include_overshoot=True)
            inner_samples = _apply_entry_midpoint_geometry(
                inner_samples, entry, wye_specs)
            inner_samples = _apply_entry_balancing(
                inner_samples, entry, wye_specs, balances)
            inner_obj = build_variable_radius_tube_object(
                context, f'{name}_InnerPart_{local_index:02d}', inner_samples,
                bevel_resolution=max(3, int(getattr(entry_props, 'irr_bevel_resolution', 8))),
                show_wire=True, subdiv_levels=0)
            if not _valid_obj(inner_obj):
                raise RuntimeError(f'could not build inner part {local_index + 1}')
            inner_parts.append(inner_obj)

        source_props, _ = _irrigation_entry_effective_props(props, source_entry)
        source_wall = max(0.05, float(getattr(source_props, 'irr_wall_thickness', 1.5)))
        for spec_index, spec in enumerate(wye_specs):
            meta = _midpoint_wye_metadata(spec)
            if meta is None:
                continue
            plenum = float(meta['plenum_radius'])
            _add_forced_wye_plenum_part(
                context, inner_parts, spec, plenum,
                f'{name}_InnerPlenum_{spec_index:02d}')
            _add_forced_wye_plenum_part(
                context, outer_parts, spec, plenum + source_wall,
                f'{name}_OuterPlenum_{spec_index:02d}')

        outer = _fuse_irrigation_solids_with_voxel(
            context, outer_parts, name + '_Outer', voxel_size=0.060)
        outer_parts = []
        if not _valid_obj(outer):
            raise RuntimeError('could not fuse the adaptive outer manifold')
        inner = _fuse_irrigation_solids_with_voxel(
            context, inner_parts, name + '_Inner', voxel_size=0.035)
        inner_parts = []
        if not _valid_obj(inner):
            safe_remove_object(outer)
            raise RuntimeError('could not fuse the adaptive continuous lumen')

        ok, message = apply_difference_exact_checked(
            context, outer, inner, name + '_HollowDifference', robust_retry=True)
        safe_remove_object(inner)
        if not ok:
            safe_remove_object(outer)
            raise RuntimeError(f'could not hollow the adaptive manifold: {message}')

        outer.name = name
        if outer.data is not None:
            outer.data.name = name + '_Mesh'
        outer.display_type = 'SOLID'
        outer.show_in_front = False

        sequential = isinstance(balances, dict) and balances.get('mode') == 'SEQUENTIAL_OPENING'
        records = [] if sequential else [r for r in balances.values() if isinstance(r, dict)]
        exact_all = bool(records) and all(
            bool(record.get('exact_balance_possible', False)) for record in records)
        max_error = max([
            float(record.get('relative_resistance_error', 1.0))
            for record in records] or [1.0])
        angles = [
            float((_midpoint_wye_metadata(spec) or {}).get('angle_deg', 30.0))
            for spec in wye_specs]

        register_dsg_object(outer, ROLE_IRRIGATION, name, {
            'DSG_irrigation_hollow_wall': True,
            'DSG_irrigation_y_network': True,
            'DSG_irrigation_geometry_mode': 'ADAPTIVE_MIDPOINT_MANIFOLD',
            'DSG_irrigation_source_segment_replaced': True,
            'DSG_irrigation_common_trunk_venturi': False,
            'DSG_irrigation_equalization_plenum': True,
            'DSG_irrigation_sleeve_volcano': True,
            'DSG_irrigation_sleeve_volcano_final_wall': True,
            'DSG_irrigation_sleeve_fusion_style': 'elegant_shoulder_slim_channel',
            'DSG_irrigation_body_wall_thickness': float(getattr(props, 'irr_wall_thickness', IRRIGATION_SLIM_WALL_THICKNESS_DEFAULT_MM)),
            'DSG_irrigation_no_internal_caps': True,
            'DSG_irrigation_link_count': len(wye_specs),
            'DSG_irrigation_balancing_mode': (
                'SEQUENTIAL_OPENING_TRUNK_THROATS' if sequential
                else 'MINIMUM_LOSS_POISEUILLE_SINGLE_BRANCH'),
            'DSG_irrigation_only_easier_branch_restricted': not sequential,
            'DSG_irrigation_nozzle_min_diameter': 0.72,
            'DSG_irrigation_nozzle_max_diameter': 0.94,
            'DSG_irrigation_nozzle_after_split': True,
            'DSG_irrigation_balance_exact_all': exact_all,
            'DSG_irrigation_balance_max_relative_error': max_error,
            'DSG_irrigation_balance_data': json.dumps(balances),
            'DSG_irrigation_branch_angle_mean_deg': (
                sum(angles) / len(angles) if angles else 0.0),
        })
        report = get_mesh_solid_report(outer, max_polygons=900000)
        if report.get('checked') and not report.get('solid'):
            message = (
                f'adaptive manifold is not solid: edges={report.get("bad_edges", 0)}, '
                f'degenerate faces={report.get("degenerate_faces", 0)}')
            safe_remove_object(outer)
            raise RuntimeError(message)
        return outer

    except Exception as exc:
        print(f'[DSG] Adaptive midpoint irrigation manifold failed: {exc}')
        for obj in outer_parts + inner_parts:
            safe_remove_object(obj)
        return None


def build_irrigation_y_network_lumen_cutter(context, source_entry, link_entries, props,
                                              name='DSG_IrrYNetworkCut'):
    """Creates a cutter that exactly follows the rebuilt manifold lumen."""
    link_entries = order_links_along_trunk(source_entry, link_entries, props)
    entries = [source_entry] + list(link_entries or [])
    wye_specs = list(link_entries or [])
    if len(entries) < 2:
        return None
    parts = []
    balances = _calculate_midpoint_wye_balances(source_entry, wye_specs, props)
    try:
        for local_index, entry in enumerate(entries):
            entry_props, parameters = _irrigation_entry_effective_props(props, entry)
            controls = entry.get('points', [])
            if len(controls) < 2:
                raise RuntimeError('invalid manifold cutter path')
            samples = build_irrigation_lumen_samples_from_controls(
                controls, entry_props, include_overshoot=True)
            samples = _apply_entry_midpoint_geometry(samples, entry, wye_specs)
            samples = _apply_entry_balancing(samples, entry, wye_specs, balances)
            tube = build_variable_radius_tube_object(
                context, f'{name}_Tube_{local_index:02d}', samples,
                bevel_resolution=max(3, int(getattr(entry_props, 'irr_bevel_resolution', 8))),
                show_wire=True, subdiv_levels=0)
            if not _valid_obj(tube):
                raise RuntimeError('could not build manifold cutter tube')
            parts.append(tube)

            # Keep sleeve manifolds independent from the shared Y cutter.
            # A single voxel-fused Y containing several C manifolds can lose a
            # short branch during Boolean evaluation.  Dedicated C-only cutters
            # are built per implant below and audited against their own sleeve.

        for spec_index, spec in enumerate(wye_specs):
            meta = _midpoint_wye_metadata(spec)
            if meta is not None:
                _add_forced_wye_plenum_part(
                    context, parts, spec, meta['plenum_radius'],
                    f'{name}_Plenum_{spec_index:02d}')

        cutter = _fuse_irrigation_solids_with_voxel(
            context, parts, name, voxel_size=0.035)
        parts = []
        if not _valid_obj(cutter):
            return None
        cutter.display_type = 'WIRE'
        cutter.show_in_front = True
        register_dsg_object(cutter, ROLE_CUTTER, name, {
            'DSG_cut_type': 'adaptive_midpoint_manifold_lumen',
            'DSG_irrigation_y_network': True,
            'DSG_irrigation_geometry_mode': 'ADAPTIVE_MIDPOINT_MANIFOLD_EXTERNAL_ONLY',
            'DSG_irrigation_balancing_mode': (
                'SEQUENTIAL_OPENING_TRUNK_THROATS'
                if isinstance(balances, dict) and balances.get('mode') == 'SEQUENTIAL_OPENING'
                else 'FULL_1MM_LINK_DAUGHTERS'),
            'DSG_irrigation_balance_data': json.dumps(balances),
            'DSG_irrigation_contains_sleeve_c_manifolds': False,
        })
        return cutter
    except Exception as exc:
        print(f'[DSG] Adaptive midpoint manifold cutter failed: {exc}')
        for obj in parts:
            safe_remove_object(obj)
        return None


def remove_disconnected_islands_keep_largest(obj, reason='boolean', max_vertices=2500000):
    """Conserva el cuerpo principal y elimina shells desconectados.

    Una guía terminada y cada component booleano deben formar una sola pieza.
    Las pequeñas islas cerradas pueden ser manifold y aun así convertirse en
    fragmentos sueltos al imprimir. Se conserva el component con más caras.
    """
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return False, 'objeto Mesh no válido', 0, 0

    mesh = obj.data
    vertex_count = len(mesh.vertices)
    polygon_count = len(mesh.polygons)
    if vertex_count == 0 or polygon_count == 0:
        return False, 'empty mesh', 0, 0
    if vertex_count > int(max_vertices):
        return True, f'island cleanup skipped because of size ({vertex_count} vertices)', 0, 0

    parent = list(range(vertex_count))
    rank = [0] * vertex_count

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a, b):
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        if rank[root_a] < rank[root_b]:
            root_a, root_b = root_b, root_a
        parent[root_b] = root_a
        if rank[root_a] == rank[root_b]:
            rank[root_a] += 1

    try:
        for edge in mesh.edges:
            a, b = edge.vertices
            union(int(a), int(b))

        faces_by_root = {}
        area_by_root = {}
        for polygon in mesh.polygons:
            if not polygon.vertices:
                continue
            root = find(int(polygon.vertices[0]))
            faces_by_root[root] = faces_by_root.get(root, 0) + 1
            try:
                area_by_root[root] = area_by_root.get(root, 0.0) + float(polygon.area)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        if len(faces_by_root) <= 1:
            return True, 'sin islas desconectadas', 0, 0

        keep_root = max(
            faces_by_root,
            key=lambda root: (
                int(faces_by_root.get(root, 0)),
                float(area_by_root.get(root, 0.0)),
            ),
        )
        remove_roots = set(faces_by_root) - {keep_root}
        removed_faces = sum(int(faces_by_root.get(root, 0)) for root in remove_roots)
        removed_components = len(remove_roots)

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            remove_verts = [
                vert for vert in bm.verts
                if find(int(vert.index)) != keep_root
            ]
            if remove_verts:
                bmesh.ops.delete(bm, geom=remove_verts, context='VERTS')
            if bm.faces:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            bm.to_mesh(mesh)
        finally:
            bm.free()

        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        try:
            obj['DSG_island_cleanup_reason'] = str(reason)
            obj['DSG_island_cleanup_components_removed'] = int(removed_components)
            obj['DSG_island_cleanup_faces_removed'] = int(removed_faces)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
            return False, 'cleanup removed the entire mesh', removed_faces, removed_components
        return True, (
            f'{removed_components} isla(s) desconectada(s) eliminada(s), '
            f'{removed_faces} faces discarded'
        ), removed_faces, removed_components
    except Exception as exc:
        return False, f'island cleanup failed: {exc}', 0, 0


def split_mesh_object_loose_parts(context, source_obj, prefix='DSG_IrrGuidePart'):
    """Separa shells desconectados sin Edit Mode ni bpy.ops.mesh.separate."""
    if not _valid_obj(source_obj) or source_obj.type != 'MESH':
        return []
    mesh = source_obj.data
    vertex_count = len(mesh.vertices)
    if vertex_count == 0:
        return []

    parent = list(range(vertex_count))
    rank = [0] * vertex_count

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a, b):
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        if rank[root_a] < rank[root_b]:
            root_a, root_b = root_b, root_a
        parent[root_b] = root_a
        if rank[root_a] == rank[root_b]:
            rank[root_a] += 1

    for edge in mesh.edges:
        a, b = edge.vertices
        union(int(a), int(b))

    polygons_by_root = {}
    for polygon in mesh.polygons:
        if not polygon.vertices:
            continue
        root = find(int(polygon.vertices[0]))
        polygons_by_root.setdefault(root, []).append(polygon)

    parts = []
    for part_index, polygons in enumerate(polygons_by_root.values()):
        used_indices = sorted({int(index) for polygon in polygons for index in polygon.vertices})
        remap = {old: new for new, old in enumerate(used_indices)}
        vertices = [tuple(mesh.vertices[index].co) for index in used_indices]
        faces = [tuple(remap[int(index)] for index in polygon.vertices) for polygon in polygons]
        part_mesh = bpy.data.meshes.new(f'{prefix}_{part_index:02d}_Mesh')
        part_mesh.from_pydata(vertices, [], faces)
        part_mesh.validate(clean_customdata=False)
        part_mesh.update(calc_edges=True)
        part_obj = bpy.data.objects.new(f'{prefix}_{part_index:02d}', part_mesh)
        part_obj.matrix_world = source_obj.matrix_world.copy()
        link_object(context, part_obj)
        parts.append(part_obj)
    return parts


def object_world_aabb(obj):
    if not _valid_obj(obj):
        return None
    try:
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        minimum = Vector((min(p.x for p in corners), min(p.y for p in corners), min(p.z for p in corners)))
        maximum = Vector((max(p.x for p in corners), max(p.y for p in corners), max(p.z for p in corners)))
        return minimum, maximum
    except Exception:
        return None


def aabb_overlap(aabb_a, aabb_b, margin=0.02):
    if not aabb_a or not aabb_b:
        return True
    minimum_a, maximum_a = aabb_a
    minimum_b, maximum_b = aabb_b
    margin = max(0.0, float(margin))
    return not (
        maximum_a.x < minimum_b.x - margin or minimum_a.x > maximum_b.x + margin or
        maximum_a.y < minimum_b.y - margin or minimum_a.y > maximum_b.y + margin or
        maximum_a.z < minimum_b.z - margin or minimum_a.z > maximum_b.z + margin
    )


def build_irrigation_single_lumen_cutter(context, entry, props, name):
    parameters = dict(entry.get('parameters', {}) if isinstance(entry, dict) else {})
    if bool(entry.get('link', False)):
        parameters['irr_inner_diameter'] = 1.0
        parameters['irr_funnel_outer_diameter'] = 1.0
        parameters['irr_taper_length'] = 0.0
        parameters['irr_funnel_enabled'] = True
        parameters['irr_link_continuous_1mm'] = True
    entry_props = irrigation_props_overlay(props, parameters)
    controls = entry.get('points', []) if isinstance(entry, dict) else []
    if len(controls) < 2:
        return None

    implant_obj = entry.get('implant') if isinstance(entry, dict) else None
    if not is_valid_implant_obj(implant_obj):
        implant_obj = get_nearest_implant_to_point(
            props, controls[1] if len(controls) > 1 else controls[0])

    samples = build_irrigation_lumen_samples_from_controls(
        controls, entry_props, include_overshoot=True)
    if len(samples) < 2:
        return None

    main_name = name + '_MainTmp'
    main_cutter = build_variable_radius_tube_object(
        context, main_name, samples,
        bevel_resolution=max(4, int(getattr(entry_props, 'irr_bevel_resolution', 8))),
        show_wire=True, subdiv_levels=0,
    )
    if not _valid_obj(main_cutter):
        return None

    parts = [main_cutter]
    ring_parts = build_irrigation_internal_ring_parts(
        context, controls, entry_props, implant_obj=implant_obj,
        name_prefix=name + '_RingTmp')
    parts.extend(ring_parts)
    sleeve_channel_mode = str(
        getattr(entry_props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
    has_c_manifold = bool(ring_parts) and sleeve_channel_mode != 'DIRECT'

    if len(parts) == 1:
        cutter = main_cutter
        cutter.name = name
        if cutter.data is not None:
            cutter.data.name = name + '_Mesh'
    else:
        cutter = build_combined_mesh_object_world(context, parts, name)
        for obj in parts:
            safe_remove_object(obj)
        if not _valid_obj(cutter):
            return None
        cutter.display_type = 'WIRE'
        cutter.show_in_front = True

        # The hydraulic lumen is only 1 mm in its distal part. A fixed fine voxel
        # is used here instead of scaling the voxel from the 4 mm inlet; the old
        # 0.08 mm value could erase or pinch short C-manifold junctions.
        try:
            voxel = 0.028 if has_c_manifold else 0.040
            remesh = cutter.modifiers.new('DSG_IrrContinuousCFuse', 'REMESH')
            remesh.mode = 'VOXEL'
            remesh.voxel_size = voxel
            remesh.use_smooth_shade = True
            if not apply_modifier_direct(context, cutter, remesh.name):
                safe_remove_object(cutter)
                return None
            cleanup_boolean_result_minimal(
                cutter, merge_dist=max(0.00015, voxel * 0.008))
        except Exception as exc:
            print(f'[DSG] Continuous C irrigation fusion failed: {exc}')
            safe_remove_object(cutter)
            return None

    if _valid_obj(cutter):
        report = get_mesh_solid_report(cutter, max_polygons=900000)
        if report.get('checked') and not report.get('solid'):
            print(
                '[DSG] Irrigation cutter rejected before Boolean: '
                f'bad edges={report.get("bad_edges", 0)}, '
                f'degenerate faces={report.get("degenerate_faces", 0)}')
            safe_remove_object(cutter)
            return None

        continuity_samples, continuity_radius = _irrigation_c_continuity_samples(
            controls, entry_props, implant_obj=implant_obj, max_step=0.14)
        if continuity_samples:
            cutter_tree, cutter_ray_length = _world_bvh_for_closed_mesh(cutter)
            missing = [
                point for point in continuity_samples[1:-1]
                if not _point_inside_closed_bvh(
                    cutter_tree, point, cutter_ray_length)
            ]
            if missing:
                print(
                    '[DSG] Continuous C cutter rejected: '
                    f'{len(missing)} centreline sample(s) are outside the cutter solid')
                safe_remove_object(cutter)
                return None
        metadata = {
            'DSG_cut_type': 'irrigation_single_centerline_continuous_c_manifold',
            'DSG_irrigation_params': json.dumps(parameters),
            'DSG_irrigation_channel_mode': sleeve_channel_mode,
            'DSG_implant_name': _safe_object_name(implant_obj) or '',
            'DSG_irrigation_internal_ring': False,
            'DSG_irrigation_internal_c_manifold': bool(has_c_manifold),
            'DSG_irrigation_c_continuous_single_path': bool(has_c_manifold),
            'DSG_irrigation_outlet_count': 2 if has_c_manifold else 1,
            'DSG_irrigation_outlet_style': 'CONTINUOUS_C_WITH_OVERLAP_NODES',
            'DSG_irrigation_link_y': bool(entry.get('link', False)),
            'DSG_irrigation_inlet_diameter': 1.0 if bool(entry.get('link', False)) else 4.0,
            'DSG_irrigation_distal_diameter': 1.0,
            'DSG_irrigation_inlet_length': 0.0 if bool(entry.get('link', False)) else 4.0,
            'DSG_irrigation_c_continuity_radius': float(continuity_radius),
            'DSG_irrigation_c_continuity_samples': json.dumps([
                [float(point.x), float(point.y), float(point.z)]
                for point in continuity_samples
            ]),
        }
        register_dsg_object(cutter, ROLE_CUTTER, name, metadata)
    return cutter


def cleanup_boolean_result_minimal(obj, merge_dist=0.0002):
    """Limpieza topológica mínima después de una booleana.

    Solo suelda vértices prácticamente coincidentes y elimina edges
    degeneradas. No rellena huecos ni cambia la forma clínica del conducto.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if bm.verts:
            bmesh.ops.remove_doubles(
                bm, verts=bm.verts[:], dist=max(0.00001, float(merge_dist)))
        if bm.edges:
            bmesh.ops.dissolve_degenerate(
                bm, edges=bm.edges[:], dist=max(0.000001, float(merge_dist) * 0.5))
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(obj.data)
        obj.data.validate(clean_customdata=False)
        obj.data.update(calc_edges=True)
        return True
    except Exception as exc:
        print(f'[DSG] Minimal post-Boolean cleanup skipped: {exc}')
        return False
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def make_offset_boolean_cutter(context, source_obj, name, offset_mm):
    """Duplica y expande suavemente un cutter cerrado siguiendo sus normales.

    El pequeño offset evita contactos tangenciales/coplanares que pueden dejar
    un anillo abierto en EXACT. También desplaza ligeramente las tapas, por lo
    que aumenta el sobrecorte sin alterar el eje ni el diámetro clínico de forma
    apreciable.
    """
    if not _valid_obj(source_obj) or source_obj.type != 'MESH':
        return None
    safe_remove_by_name(name)
    mesh = source_obj.data.copy()
    cutter = bpy.data.objects.new(name, mesh)
    cutter.matrix_world = source_obj.matrix_world.copy()
    link_object(context, cutter)
    cutter.display_type = 'WIRE'
    cutter.show_in_front = True

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.normal_update()
        amount = max(0.0, float(offset_mm))
        if amount > 0.0:
            for vert in bm.verts:
                normal = vert.normal.copy()
                if normal.length > 1e-8:
                    vert.co += normal.normalized() * amount
        if bm.verts:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0002)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        return cutter
    except Exception as exc:
        print(f'[DSG] Could not create retry cutter: {exc}')
        safe_remove_object(cutter)
        return None
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def apply_difference_exact_checked(context, base_obj, cutter_obj, modifier_name,
                                   robust_retry=False,
                                   allow_manifold_fallback=False,
                                   retry_offsets=None):
    """DIFFERENCE transaccional sobre un shell cerrado.

    Para irrigación y protección axial puede activar reintentos robustos. Si
    EXACT deja una costura abierta por tangencia, restaura el componente original
    y repite con cutters ligeramente expandidos. Opcionalmente prueba MANIFOLD
    cuando Blender lo soporta. Nunca rellena la abertura del conducto ni confirma
    un resultado no manifold.
    """
    if not _valid_obj(base_obj) or not _valid_obj(cutter_obj):
        return False, 'invalid objects'

    original_mesh = base_obj.data.copy()
    last_message = 'Boolean DIFFERENCE EXACT no pudo aplicarse'

    def restore_fresh_original():
        fresh = original_mesh.copy()
        return _restore_object_mesh_copy(base_obj, fresh)

    def run_attempt(active_cutter, attempt_name, robust=False, solver='EXACT'):
        mod = base_obj.modifiers.new(attempt_name, 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = active_cutter
        selected_solver = str(solver or 'EXACT').upper()
        try:
            supported = get_supported_boolean_solvers(mod)
        except Exception:
            supported = {'EXACT'}
        if selected_solver not in supported:
            try:
                base_obj.modifiers.remove(mod)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return False, f'Boolean solver {selected_solver} is not supported'
        try:
            mod.solver = selected_solver
        except Exception:
            try:
                base_obj.modifiers.remove(mod)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return False, f'Boolean solver {selected_solver} could not be selected'
        set_boolean_exact_options(mod, robust=bool(robust))

        if not apply_modifier_direct(context, base_obj, mod.name):
            try:
                leftover = base_obj.modifiers.get(attempt_name)
                if leftover is not None:
                    base_obj.modifiers.remove(leftover)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return False, f'Boolean DIFFERENCE {selected_solver} could not be applied'

        try:
            vertex_count = len(base_obj.data.vertices) if base_obj.data else 0
            polygon_count = len(base_obj.data.polygons) if base_obj.data else 0
        except Exception:
            vertex_count = 0
            polygon_count = 0
        if vertex_count == 0 or polygon_count == 0:
            return False, 'the Boolean completely removed the component'

        islands_ok, islands_msg, _removed_faces, removed_components = (
            remove_disconnected_islands_keep_largest(
                base_obj, reason=f'boolean:{attempt_name}'))
        if not islands_ok:
            return False, islands_msg

        cleanup_boolean_result_minimal(base_obj)
        report = get_mesh_solid_report(base_obj, max_polygons=900000)
        if report.get('checked') and not report.get('solid'):
            bad = report.get('bad_edges', 0)
            deg = report.get('degenerate_faces', 0)
            return False, f'non-solid result: edges={bad}, degenerate faces={deg}'

        suffix = '' if removed_components == 0 else f' · {islands_msg}'
        return True, f'DIFFERENCE {selected_solver} OK' + suffix

    ok, message = run_attempt(
        cutter_obj, modifier_name, robust=False, solver='EXACT')
    if ok:
        try:
            if original_mesh.users == 0:
                bpy.data.meshes.remove(original_mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, message
    last_message = message

    # EXACT can leave a small open ring on otherwise valid closed shells. Blender
    # 5.x provides MANIFOLD for exactly this class of clean, manifold operands.
    # Every attempt starts from the untouched source mesh and is audited before
    # being accepted.
    if allow_manifold_fallback:
        restore_fresh_original()
        manifold_name = f'{modifier_name}_Manifold'
        ok, manifold_message = run_attempt(
            cutter_obj, manifold_name, robust=False, solver='MANIFOLD')
        if ok:
            try:
                base_obj['DSG_boolean_manifold_fallback'] = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                if original_mesh.users == 0:
                    bpy.data.meshes.remove(original_mesh)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return True, manifold_message + ' · fallback MANIFOLD validado'
        last_message = manifold_message

    if robust_retry:
        offsets = tuple(
            float(value) for value in
            (retry_offsets if retry_offsets is not None else IRR_BOOLEAN_RETRY_OFFSETS_MM)
            if float(value) > 0.0)
        for retry_index, offset_mm in enumerate(offsets, start=1):
            retry_name = f'{modifier_name}_Robust_{retry_index:02d}'
            retry_cutter = make_offset_boolean_cutter(
                context, cutter_obj, retry_name + '_Cutter', offset_mm)
            if not _valid_obj(retry_cutter):
                last_message = f'{last_message}; could not create retry {retry_index}'
                continue
            try:
                # Robust EXACT first.
                restore_fresh_original()
                ok, retry_message = run_attempt(
                    retry_cutter, retry_name, robust=True, solver='EXACT')
                if not ok and allow_manifold_fallback:
                    # Then MANIFOLD on the same expanded cutter.
                    restore_fresh_original()
                    ok, retry_message = run_attempt(
                        retry_cutter, retry_name + '_Manifold',
                        robust=False, solver='MANIFOLD')
            finally:
                safe_remove_object(retry_cutter)
            if ok:
                try:
                    base_obj['DSG_boolean_robust_retry'] = True
                    base_obj['DSG_boolean_retry_offset_mm'] = float(offset_mm)
                    base_obj['DSG_boolean_retry_solver'] = (
                        'MANIFOLD' if 'MANIFOLD' in retry_message else 'EXACT')
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                try:
                    if original_mesh.users == 0:
                        bpy.data.meshes.remove(original_mesh)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                return True, (
                    f'{retry_message} · reintento robusto con sobrecorte '
                    f'{offset_mm:.3f} mm')
            last_message = retry_message

    _restore_object_mesh_copy(base_obj, original_mesh)
    return False, last_message


# ─────────────────────────────────────────────────────────────
# Paso 8 — Irrigation por eje interno
# ─────────────────────────────────────────────────────────────
#
# 1. Los puntos representan el eje/lumen interno.
# 2. El primer clic toca el sleeve y se añade automáticamente un control profundo.
# 3. Al confirmar cada preview solo se guarda la pared externa como objeto separado.
# 4. Al finalizar, guía + todas las paredes se combinan sin Boolean.
# 5. Un único DIFFERENCE EXACT perfora simultáneamente walls and sleeves.
# ─────────────────────────────────────────────────────────────

def get_pending_irrigation_preview(props):
    """Busca el preview pendiente sin escribir en Scene durante Panel.draw()."""
    obj = getattr(props, 'irr_preview_obj', None)
    if _valid_obj(obj) and bool(obj.get('DSG_irrigation_preview', False)):
        return obj
    for candidate in bpy.data.objects:
        try:
            if (candidate.name.startswith(IRR_PREVIEW_PREFIX)
                    and bool(candidate.get('DSG_irrigation_preview', False))):
                # No rehidratar props.irr_preview_obj aquí: esta función se llama
                # desde draw() y Blender no permite escribir en ID data-blocks.
                return candidate
        except (ReferenceError, RuntimeError):
            continue
    return None


