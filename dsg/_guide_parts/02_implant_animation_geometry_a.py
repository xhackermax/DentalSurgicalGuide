def orient_empty_to_vector(empty, axis_vec):
    q = Vector((0, 0, 1)).rotation_difference(Vector(axis_vec).normalized())
    empty.rotation_euler = q.to_euler()


def get_insertion_axis():
    empty = get_axis_empty()
    if empty:
        axis = empty.matrix_world.to_3x3() @ Vector((0, 0, 1))
        if axis.length > 1.0e-8:
            return axis.normalized()
    return Vector((0, 0, 1))


def _read_stored_world_axis(owner, key=BLOCKOUT_AXIS_WORLD_KEY):
    if owner is None:
        return None
    try:
        raw = owner.get(key)
    except Exception:
        raw = None
    if raw is None:
        return None
    try:
        axis = Vector(tuple(float(value) for value in raw[:3]))
    except Exception:
        return None
    if axis.length <= 1.0e-8:
        return None
    return axis.normalized()


def store_blockout_axis(context, model, axis_vec, source='CURRENT_VIEW_V7_0_47'):
    """Persist the exact world-space vector used to survey the model.

    The arrow remains an editable visual control, but the generated previews
    and the final confirmed model can now prove which vector they actually used.
    """
    axis = Vector(axis_vec)
    if axis.length <= 1.0e-8:
        raise ValueError('Invalid insertion axis')
    axis.normalize()
    packed = tuple(round(float(value), 9) for value in axis)
    owners = [get_axis_empty(), model, getattr(context, 'scene', None)]
    for owner in owners:
        if owner is None:
            continue
        try:
            owner[BLOCKOUT_AXIS_WORLD_KEY] = packed
            owner[BLOCKOUT_AXIS_SOURCE_KEY] = str(source)
            owner[BLOCKOUT_AXIS_CONVENTION_KEY] = BLOCKOUT_AXIS_CONVENTION_V7
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return axis


def current_blockout_axis(context, model=None, source='AXIS_ARROW_V7_0_47'):
    """Read the currently visible arrow and freeze that exact vector.

    This is used when the clinician rotates the arrow manually and explicitly
    asks DSG to rebuild the blockout.
    """
    axis = get_insertion_axis()
    return store_blockout_axis(context, model, axis, source=source)


def preview_blockout_axis(props, fallback_context=None, fallback_model=None):
    """Return the vector used by the selected preview.

    Confirming a preset must reproduce the preview exactly, even if the arrow
    was moved afterwards.  If no preview metadata exists, fall back safely to
    the current arrow and persist it.
    """
    preview = _selected_retention_preview(props) if props is not None else None
    axis = _read_stored_world_axis(preview, 'DSG_insertion_axis_world')
    if axis is not None:
        return axis
    axis = _read_stored_world_axis(preview, BLOCKOUT_AXIS_WORLD_KEY)
    if axis is not None:
        return axis
    model = fallback_model
    if model is None and props is not None:
        model = getattr(props, 'model_obj', None)
    if fallback_context is not None:
        return current_blockout_axis(
            fallback_context, model, source='FINAL_FALLBACK_AXIS_ARROW_V7_0_47')
    return get_insertion_axis()


def object_bbox_diagonal(obj):
    bb    = obj.bound_box
    scale = obj.matrix_world.to_scale()
    lmin  = Vector((min(v[i] for v in bb) for i in range(3)))
    lmax  = Vector((max(v[i] for v in bb) for i in range(3)))
    d     = lmax - lmin
    return math.sqrt((d.x * scale.x)**2 + (d.y * scale.y)**2 + (d.z * scale.z)**2)


def build_axis_basis(axis):
    axis = Vector(axis).normalized()
    ref  = Vector((1, 0, 0)) if abs(axis.dot(Vector((0, 0, 1)))) > 0.9 else Vector((0, 0, 1))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    return u, v, axis


def sort_contour_points(points_world, axis):
    pts    = [Vector(p) for p in points_world]
    center = sum(pts, Vector()) / len(pts)
    u, v, _ = build_axis_basis(axis)
    def ang(p):
        r = p - center
        return math.atan2(r.dot(v), r.dot(u))
    return sorted(pts, key=ang)


def make_cylinder_mesh(name, radius, depth, verts=24):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                          segments=verts, radius1=radius, radius2=radius, depth=depth)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def make_torus_mesh(name, major_radius, minor_radius, major_segments=48, minor_segments=16):
    """Torus analítico local alineado con Z para manifolds internos de irrigación."""
    major_radius = max(0.10, float(major_radius))
    minor_radius = max(0.05, float(minor_radius))
    major_segments = max(12, min(128, int(major_segments)))
    minor_segments = max(8, min(64, int(minor_segments)))

    vertices = []
    faces = []
    for i in range(major_segments):
        phi = 2.0 * math.pi * i / major_segments
        cphi = math.cos(phi)
        sphi = math.sin(phi)
        for j in range(minor_segments):
            theta = 2.0 * math.pi * j / minor_segments
            ctheta = math.cos(theta)
            stheta = math.sin(theta)
            radius = major_radius + minor_radius * ctheta
            vertices.append((radius * cphi, radius * sphi, minor_radius * stheta))

    for i in range(major_segments):
        ni = (i + 1) % major_segments
        for j in range(minor_segments):
            nj = (j + 1) % minor_segments
            a = i * minor_segments + j
            b = i * minor_segments + nj
            c = ni * minor_segments + nj
            d = ni * minor_segments + j
            faces.append((a, b, c, d))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    return mesh


def _decode_implant_template():
    """Decodifica una sola vez la plantilla STL optimizada integrada en el addon."""
    global _IMPLANT_TEMPLATE_CACHE
    if _IMPLANT_TEMPLATE_CACHE is not None:
        return _IMPLANT_TEMPLATE_CACHE

    compressed = base64.b85decode(_IMPLANT_TEMPLATE_B85.encode('ascii'))
    raw = zlib.decompress(compressed)
    if len(raw) < 8:
        raise RuntimeError('Empty implant template')
    vertex_count, face_count = struct.unpack_from('<II', raw, 0)
    vertex_bytes = int(vertex_count) * 12
    face_bytes = int(face_count) * 12
    expected = 8 + vertex_bytes + face_bytes
    if len(raw) != expected:
        raise RuntimeError(
            f'Damaged implant template: {len(raw)} bytes, esperados {expected}')

    vertices = tuple(struct.iter_unpack('<3f', raw[8:8 + vertex_bytes]))
    faces = tuple(struct.iter_unpack('<3I', raw[8 + vertex_bytes:]))
    if len(vertices) != vertex_count or len(faces) != face_count:
        raise RuntimeError('Implant template does not match its header')
    _IMPLANT_TEMPLATE_CACHE = (vertices, faces)
    return _IMPLANT_TEMPLATE_CACHE


def make_embedded_implant_mesh(name, diameter, length):
    """Crea la representación visual del implante desde el STL integrado.

    La plantilla está normalizada: diámetro transversal = 1 y longitud axial = 1.
    Por ello los controles existentes de diámetro y longitud siguen funcionando,
    y el eje local Z mantiene toda la lógica de sleeve, drill y paralelismo.
    """
    diameter = max(0.10, float(diameter))
    length = max(0.10, float(length))
    template_vertices, template_faces = _decode_implant_template()
    vertices = [
        (float(x) * diameter, float(y) * diameter, float(z) * length)
        for x, y, z in template_vertices
    ]
    faces = [tuple(int(index) for index in face) for face in template_faces]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    try:
        mesh.validate(clean_customdata=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh.update(calc_edges=True)
    return mesh


def _decode_drill_visual_template():
    """Decodifica una sola vez la fresa optimizada integrada en el addon."""
    global _DRILL_VISUAL_TEMPLATE_CACHE
    if _DRILL_VISUAL_TEMPLATE_CACHE is not None:
        return _DRILL_VISUAL_TEMPLATE_CACHE

    compressed = base64.b85decode(_DRILL_VISUAL_TEMPLATE_B85.encode('ascii'))
    raw = zlib.decompress(compressed)
    if len(raw) < 8:
        raise RuntimeError('Empty drill template')
    vertex_count, face_count = struct.unpack_from('<II', raw, 0)
    vertex_bytes = int(vertex_count) * 12
    face_bytes = int(face_count) * 12
    expected = 8 + vertex_bytes + face_bytes
    if len(raw) != expected:
        raise RuntimeError(
            f'Damaged drill template: {len(raw)} bytes, esperados {expected}')
    vertices = tuple(struct.iter_unpack('<3f', raw[8:8 + vertex_bytes]))
    faces = tuple(struct.iter_unpack('<3I', raw[8 + vertex_bytes:]))
    if len(vertices) != vertex_count or len(faces) != face_count:
        raise RuntimeError('Drill template does not match its header')
    _DRILL_VISUAL_TEMPLATE_CACHE = (vertices, faces)
    return _DRILL_VISUAL_TEMPLATE_CACHE


def _reduce_and_rectify_drill_mesh(mesh, guide_diameter_mm, stop_z_mm, guide_bottom_z_mm):
    """Reduce la triangulación y rectifica el cilindro/tope de la fresa.

    El cilindro comprendido entre ``guide_bottom_z_mm`` y ``stop_z_mm`` se
    regulariza para que tenga Ø 4,70 mm y paredes paralelas. La pequeña cara
    plana inmediatamente posterior se mantiene perpendicular al eje (90°).
    """
    if mesh is None:
        return False
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Taper ligera antes de modificar la geometría axial.
        if bm.verts:
            try:
                bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.004)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if bm.edges:
            try:
                bmesh.ops.dissolve_limit(
                    bm,
                    angle_limit=math.radians(1.5),
                    verts=bm.verts[:],
                    edges=bm.edges[:],
                    delimit={'NORMAL', 'MATERIAL', 'SHARP', 'SEAM', 'UV'})
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        bm.verts.ensure_lookup_table()
        guide_r = max(0.05, float(guide_diameter_mm) * 0.5)
        stop_z = float(stop_z_mm)
        bottom_z = float(guide_bottom_z_mm)
        if bottom_z >= stop_z:
            raise RuntimeError('invalid axial limits for the guide cylinder')

        # Rectifica todo el cilindro guía, no solo la zona próxima al tope.
        radial_floor = guide_r * 0.78
        radial_ceiling = guide_r * 1.18
        axial_tol = 0.03
        for v in bm.verts:
            z = float(v.co.z)
            r = math.hypot(v.co.x, v.co.y)
            if bottom_z - axial_tol <= z <= stop_z + axial_tol and radial_floor <= r <= radial_ceiling and r > 1e-8:
                scale_r = guide_r / r
                v.co.x *= scale_r
                v.co.y *= scale_r

        # Aplana exactamente la cara de contacto del tope.
        stop_face_tol = max(0.10, guide_r * 0.045)
        ring_candidates = []
        for v in bm.verts:
            r = math.hypot(v.co.x, v.co.y)
            if abs(v.co.z - stop_z) <= stop_face_tol and r >= guide_r + 0.02:
                ring_candidates.append(r)
                v.co.z = stop_z

        if ring_candidates:
            ring_candidates.sort()
            shoulder_r = ring_candidates[len(ring_candidates) // 2]
        else:
            shoulder_r = guide_r + max(0.45, guide_r * 0.18)

        # Wall Thickness vertical del hombro: encuentro a 90° con la cara plana.
        wall_tol = max(0.12, shoulder_r * 0.07)
        wall_band_high = stop_z + max(0.50, guide_r * 0.22)
        for v in bm.verts:
            r = math.hypot(v.co.x, v.co.y)
            z = float(v.co.z)
            if stop_z - 0.02 <= z <= wall_band_high and abs(r - shoulder_r) <= wall_tol and r > 1e-8:
                scale_r = shoulder_r / r
                v.co.x *= scale_r
                v.co.y *= scale_r

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        try:
            mesh.validate(clean_customdata=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        mesh.update(calc_edges=True)
        return True
    except Exception as exc:
        print(f'[DSG] Could not straighten the drill: {exc}')
        return False
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)



def _percentile_sorted(values, fraction):
    if not values:
        return 0.0
    values = sorted(float(value) for value in values)
    if len(values) == 1:
        return values[0]
    position = max(0.0, min(1.0, float(fraction))) * (len(values) - 1)
    low = int(math.floor(position))
    high = min(len(values) - 1, low + 1)
    blend = position - low
    return values[low] * (1.0 - blend) + values[high] * blend


def _interpolate_profile(samples, z_value, value_index):
    if not samples:
        return 0.0
    if z_value <= samples[0][0]:
        return samples[0][value_index]
    if z_value >= samples[-1][0]:
        return samples[-1][value_index]
    lo = 0
    hi = len(samples) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if samples[mid][0] <= z_value:
            lo = mid
        else:
            hi = mid
    z0 = samples[lo][0]
    z1 = samples[hi][0]
    if abs(z1 - z0) < 1e-9:
        return samples[lo][value_index]
    t = (z_value - z0) / (z1 - z0)
    return samples[lo][value_index] * (1.0 - t) + samples[hi][value_index] * t


def _straighten_drill_axis(vertices, bins_count=96):
    """Elimina la curvatura heredada del STL sin destruir las hélices.

    Para cada sección axial calcula un centro robusto usando los percentiles
    5–95 % de X/Y, suaviza la línea central y resta su desplazamiento. Así la
    punta, la parte activa, el cilindro, el tope y el vástago comparten Z.
    """
    if not vertices:
        return []
    z_min = min(float(vertex[2]) for vertex in vertices)
    z_max = max(float(vertex[2]) for vertex in vertices)
    span = max(1e-8, z_max - z_min)
    count = max(24, int(bins_count))
    bins = [[] for _ in range(count)]
    for vertex in vertices:
        index = int((float(vertex[2]) - z_min) / span * count)
        index = max(0, min(count - 1, index))
        bins[index].append(vertex)

    raw = []
    for index, section in enumerate(bins):
        if len(section) < 4:
            continue
        xs = [float(vertex[0]) for vertex in section]
        ys = [float(vertex[1]) for vertex in section]
        zs = [float(vertex[2]) for vertex in section]
        cx = 0.5 * (_percentile_sorted(xs, 0.05) + _percentile_sorted(xs, 0.95))
        cy = 0.5 * (_percentile_sorted(ys, 0.05) + _percentile_sorted(ys, 0.95))
        raw.append((sum(zs) / len(zs), cx, cy))

    if len(raw) < 3:
        return [tuple(vertex) for vertex in vertices]

    # Suavizado corto: elimina ruido de las hélices sin ocultar una desviación
    # real del centro del STL.
    smooth = []
    for index, sample in enumerate(raw):
        start = max(0, index - 2)
        end = min(len(raw), index + 3)
        window = raw[start:end]
        weights = []
        for neighbour_index in range(start, end):
            distance = abs(neighbour_index - index)
            weights.append(3.0 if distance == 0 else (2.0 if distance == 1 else 1.0))
        total = sum(weights)
        cx = sum(item[1] * weight for item, weight in zip(window, weights)) / total
        cy = sum(item[2] * weight for item, weight in zip(window, weights)) / total
        smooth.append((sample[0], cx, cy))

    straightened = []
    for x, y, z in vertices:
        cx = _interpolate_profile(smooth, float(z), 1)
        cy = _interpolate_profile(smooth, float(z), 2)
        straightened.append((float(x) - cx, float(y) - cy, float(z)))
    return straightened


def _rebuild_upper_cylindrical_body(vertices, stop_z_mm, guide_radius_mm):
    """Reconstruye la parte superior como cilindros lisos con ángulos rectos.

    A partir del plano del tope se descarta la silueta irregular del STL y se
    rehace una anatomía simple por escalones coaxiales:
      · hombro/tope ancho,
      · cuello corto,
      · vástago principal,
      · remate superior.

    Esto produce una geometría más limpia y predecible para la animación contra
    el sleeve.
    """
    if not vertices:
        return []

    stop_z = float(stop_z_mm)
    guide_r = max(0.10, float(guide_radius_mm))
    top_vertices = [v for v in vertices if float(v[2]) >= stop_z]
    if len(top_vertices) < 8:
        return [tuple(v) for v in vertices]

    z_max = max(float(v[2]) for v in top_vertices)
    total_h = max(2.50, z_max - stop_z)

    # Heights por tramos: cilindros y escalones netos.
    flange_h = min(0.95, total_h * 0.16)
    neck_h = min(0.55, total_h * 0.08)
    cap_h = min(0.95, total_h * 0.12)
    tip_h = min(0.50, total_h * 0.06)
    shank_h = max(0.80, total_h - flange_h - neck_h - cap_h - tip_h)

    z1 = stop_z + flange_h
    z2 = z1 + neck_h
    z3 = z2 + shank_h
    z4 = min(z_max, z3 + cap_h)

    # Radios cilíndricos lisos y coaxiales.
    flange_r = guide_r + 0.80
    neck_r = max(guide_r * 0.86, flange_r - 0.65)
    shank_r = max(1.10, guide_r * 0.58)
    cap_r = max(shank_r + 0.35, shank_r * 1.22)
    tip_r = max(0.65, shank_r * 0.72)

    rebuilt = []
    for x, y, z in vertices:
        x = float(x); y = float(y); z = float(z)
        if z >= stop_z:
            if z <= z1:
                target_r = flange_r
            elif z <= z2:
                target_r = neck_r
            elif z <= z3:
                target_r = shank_r
            elif z <= z4:
                target_r = cap_r
            else:
                target_r = tip_r
            current_r = math.hypot(x, y)
            if current_r > 1e-9:
                factor = target_r / current_r
                x *= factor
                y *= factor
            else:
                x = target_r
                y = 0.0
        rebuilt.append((x, y, z))
    return rebuilt


def _add_ring_vertices(bm, z_value, radius, segments=40):
    verts = []
    segments = max(12, int(segments))
    radius = max(0.01, float(radius))
    for i in range(segments):
        ang = (2.0 * math.pi * i) / segments
        verts.append(bm.verts.new((math.cos(ang) * radius, math.sin(ang) * radius, float(z_value))))
    return verts


def _connect_rings_quads(bm, ring_a, ring_b):
    count = min(len(ring_a), len(ring_b))
    if count < 3:
        return
    for i in range(count):
        a0 = ring_a[i]
        a1 = ring_a[(i + 1) % count]
        b1 = ring_b[(i + 1) % count]
        b0 = ring_b[i]
        try:
            bm.faces.new((a0, a1, b1, b0))
        except ValueError:
            pass


def _cap_ring_with_center(bm, ring, z_value, flip=False):
    center = bm.verts.new((0.0, 0.0, float(z_value)))
    count = len(ring)
    for i in range(count):
        v0 = ring[i]
        v1 = ring[(i + 1) % count]
        try:
            if flip:
                bm.faces.new((center, v1, v0))
            else:
                bm.faces.new((center, v0, v1))
        except ValueError:
            pass


def _overlay_simple_symmetric_upper_body(mesh, stop_z_mm, guide_radius_mm):
    """Superpone una anatomía superior simple, recta y totalmente simétrica.

    Para evitar irregularidades heredadas del STL, la parte superior existente
    se contrae hacia el eje y se cubre con una nueva geometría sencilla hecha
    con anillos circulares coaxiales.
    """
    if mesh is None:
        return False
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()

        stop_z = float(stop_z_mm)
        guide_r = max(0.10, float(guide_radius_mm))
        upper_verts = [v for v in bm.verts if float(v.co.z) >= stop_z]
        if len(upper_verts) < 8:
            return False

        z_max = max(float(v.co.z) for v in upper_verts)
        total_h = max(2.50, z_max - stop_z)

        # Contrae la geometría superior heredada del STL para que no se vea.
        hidden_r = max(0.20, guide_r * 0.35)
        for v in upper_verts:
            r = math.hypot(v.co.x, v.co.y)
            if r > hidden_r and r > 1e-8:
                factor = hidden_r / r
                v.co.x *= factor
                v.co.y *= factor

        # Perfil sencillo por tramos, totalmente recto y simétrico.
        flange_h = min(0.90, total_h * 0.16)
        neck_h = min(0.55, total_h * 0.08)
        shank_h = max(0.90, total_h * 0.48)
        head_h = max(0.55, total_h - flange_h - neck_h - shank_h)

        z0 = stop_z
        z1 = z0 + flange_h
        z2 = z1 + neck_h
        z3 = z2 + shank_h
        z4 = z_max

        flange_r = guide_r + 0.82
        neck_r = max(guide_r * 0.86, flange_r - 0.62)
        shank_r = max(1.05, guide_r * 0.56)
        head_r = max(shank_r + 0.22, shank_r * 1.18)

        segments = 40
        # Anillos para escalones rectos a 90°.
        ring_guide = _add_ring_vertices(bm, z0, guide_r, segments)
        ring_flange_base = _add_ring_vertices(bm, z0, flange_r, segments)
        ring_flange_top = _add_ring_vertices(bm, z1, flange_r, segments)
        ring_neck_base = _add_ring_vertices(bm, z1, neck_r, segments)
        ring_neck_top = _add_ring_vertices(bm, z2, neck_r, segments)
        ring_shank_base = _add_ring_vertices(bm, z2, shank_r, segments)
        ring_shank_top = _add_ring_vertices(bm, z3, shank_r, segments)
        ring_head_base = _add_ring_vertices(bm, z3, head_r, segments)
        ring_head_top = _add_ring_vertices(bm, z4, head_r, segments)

        _connect_rings_quads(bm, ring_guide, ring_flange_base)
        _connect_rings_quads(bm, ring_flange_base, ring_flange_top)
        _connect_rings_quads(bm, ring_flange_top, ring_neck_base)
        _connect_rings_quads(bm, ring_neck_base, ring_neck_top)
        _connect_rings_quads(bm, ring_neck_top, ring_shank_base)
        _connect_rings_quads(bm, ring_shank_base, ring_shank_top)
        _connect_rings_quads(bm, ring_shank_top, ring_head_base)
        _connect_rings_quads(bm, ring_head_base, ring_head_top)
        _cap_ring_with_center(bm, ring_head_top, z4, flip=False)

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        try:
            mesh.validate(clean_customdata=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        mesh.update(calc_edges=True)
        return True
    except Exception as exc:
        print(f'[DSG] Could not overlay the simplified upper drill body: {exc}')
        return False
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def make_embedded_drill_visual_mesh(
        name,
        guide_diameter_mm=DRILL_FIXED_GUIDE_DIAMETER_MM,
        guide_length_mm=7.0,
        active_length_mm=10.0):
    """Crea una fresa visual paramétrica a partir del STL integrado.

    Reglas geométricas:
      · cilindro guía: diámetro configurable y longitud igual a la altura del sleeve;
      · parte activa: longitud igual a la del implante asociado;
      · el tope y el vástago permanecen sin estirarse;
      · la punta nunca puede sobrepasar la profundidad del implante cuando el
        tope está en contacto con el sleeve.
    """
    diameter = max(0.50, float(guide_diameter_mm))
    guide_length = max(0.50, float(guide_length_mm))
    active_length = max(0.50, float(active_length_mm))
    radial_scale = diameter / max(1e-8, float(DRILL_TEMPLATE_GUIDE_DIAMETER))

    template_vertices, template_faces = _decode_drill_visual_template()
    stop_template_mm = float(DRILL_TEMPLATE_STOP_Z) * radial_scale
    bottom_template_mm = float(DRILL_TEMPLATE_GUIDE_BOTTOM_Z) * radial_scale
    # Usa el vértice apical real de la plantilla para que la punta termine
    # exactamente a la longitud seleccionada, sin exceso ni defecto acumulado.
    tip_template_mm = min(float(vertex[2]) for vertex in template_vertices) * radial_scale

    template_guide_span = max(1e-8, stop_template_mm - bottom_template_mm)
    template_active_span = max(1e-8, bottom_template_mm - tip_template_mm)
    desired_bottom_mm = stop_template_mm - guide_length
    desired_tip_mm = desired_bottom_mm - active_length

    vertices = []
    for x, y, z in template_vertices:
        px = float(x) * radial_scale
        py = float(y) * radial_scale
        pz = float(z) * radial_scale

        if pz <= bottom_template_mm:
            # Estira/contrae solamente la parte activa desde el inicio del
            # cilindro hasta la punta.
            t = (pz - tip_template_mm) / template_active_span
            t = max(0.0, min(1.0, t))
            pz = desired_tip_mm + t * active_length
        elif pz <= stop_template_mm:
            # Remapea el cilindro para que mida exactamente lo mismo que el sleeve.
            t = (pz - bottom_template_mm) / template_guide_span
            t = max(0.0, min(1.0, t))
            pz = desired_bottom_mm + t * guide_length
        # Por encima del plano de tope se conserva la longitud original del
        # hombro y del vástago.
        vertices.append((px, py, pz))

    # El STL de origen presenta una deriva lateral acumulada. Se corrige antes
    # de construir la malla para que todas las zonas compartan un eje Z único.
    vertices = _straighten_drill_axis(vertices, bins_count=112)

    # Reconstruye toda la parte superior como una secuencia de cilindros lisos
    # y escalonados, con ángulos rectos y sin irregularidades heredadas del STL.
    vertices = _rebuild_upper_cylindrical_body(
        vertices, stop_template_mm, diameter * 0.5)

    faces = [tuple(int(index) for index in face) for face in template_faces]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    try:
        mesh.validate(clean_customdata=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh.update(calc_edges=True)

    _reduce_and_rectify_drill_mesh(
        mesh, diameter, stop_template_mm, desired_bottom_mm)
    _overlay_simple_symmetric_upper_body(
        mesh, stop_template_mm, diameter * 0.5)
    return mesh, radial_scale, stop_template_mm, desired_bottom_mm, desired_tip_mm


def _set_fcurve_interpolation_linear(action, prefixes=('location', 'rotation_quaternion')):
    if action is None:
        return
    try:
        for fcurve in action.fcurves:
            if not any(fcurve.data_path.startswith(prefix) for prefix in prefixes):
                continue
            for key in fcurve.keyframe_points:
                key.interpolation = 'LINEAR'
                key.handle_left_type = 'VECTOR'
                key.handle_right_type = 'VECTOR'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _insert_helical_segment(obj, base_rotation, longitudinal, start_location,
                            final_location, start_frame, end_frame,
                            turns_from, turns_to, previous_quaternion=None):
    start_location = Vector(start_location)
    final_location = Vector(final_location)
    start_frame = float(start_frame)
    end_frame = float(end_frame)
    turns_delta = abs(float(turns_to) - float(turns_from))
    frame_span = max(1.0, end_frame - start_frame)
    steps = max(1, int(math.ceil(max(turns_delta * 8.0, frame_span / 6.0))))

    for step in range(steps + 1):
        factor = float(step) / float(steps)
        frame = start_frame + (end_frame - start_frame) * factor
        location = start_location.lerp(final_location, factor)
        turns = float(turns_from) + (float(turns_to) - float(turns_from)) * factor
        angle = -math.tau * turns

        twist = Quaternion(longitudinal, angle)
        rotation = twist @ base_rotation
        rotation.normalize()

        if previous_quaternion is not None and previous_quaternion.dot(rotation) < 0.0:
            rotation = Quaternion((-rotation.w, -rotation.x, -rotation.y, -rotation.z))

        obj.location = location
        obj.rotation_quaternion = rotation
        obj.keyframe_insert(data_path='location', frame=frame)
        obj.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        previous_quaternion = rotation.copy()

    return previous_quaternion


def apply_clockwise_helical_animation(obj, base_rotation, start_location, final_location,
                                      start_frame, end_frame, turns):
    """Avanza y gira sobre el eje longitudinal real de la inserción."""
    start_location = Vector(start_location)
    final_location = Vector(final_location)
    longitudinal = start_location - final_location
    if longitudinal.length < 1e-8:
        longitudinal = base_rotation @ Vector((0.0, 0.0, 1.0))
    longitudinal = _normalized_or_fallback(longitudinal, (0.0, 0.0, 1.0))

    turns = max(0.0, float(turns))
    start_frame = int(start_frame)
    end_frame = max(start_frame + 1, int(end_frame))
    obj.rotation_mode = 'QUATERNION'

    _insert_helical_segment(
        obj, base_rotation, longitudinal,
        start_location, final_location,
        start_frame, end_frame,
        0.0, turns, previous_quaternion=None)

    if obj.animation_data and obj.animation_data.action:
        _set_fcurve_interpolation_linear(obj.animation_data.action)

    obj['DSG_clockwise_helical_animation'] = True
    obj['DSG_helical_turns'] = float(turns)
    obj['DSG_longitudinal_rotation_axis_world'] = list(longitudinal)
    obj['DSG_rotation_axis_from_insertion_path'] = True
    return longitudinal


def apply_clockwise_helical_roundtrip_animation(obj, base_rotation, start_location,
                                                contact_location, start_frame,
                                                contact_frame, end_frame,
                                                turns_in, turns_out=None):
    """La fresa entra al sleeve y luego regresa a su posición inicial."""
    start_location = Vector(start_location)
    contact_location = Vector(contact_location)
    longitudinal = start_location - contact_location
    if longitudinal.length < 1e-8:
        longitudinal = base_rotation @ Vector((0.0, 0.0, 1.0))
    longitudinal = _normalized_or_fallback(longitudinal, (0.0, 0.0, 1.0))

    start_frame = int(start_frame)
    contact_frame = max(start_frame + 1, int(contact_frame))
    end_frame = max(contact_frame + 1, int(end_frame))
    turns_in = max(0.0, float(turns_in))
    turns_out = turns_in if turns_out is None else max(0.0, float(turns_out))

    obj.rotation_mode = 'QUATERNION'
    previous_quaternion = _insert_helical_segment(
        obj, base_rotation, longitudinal,
        start_location, contact_location,
        start_frame, contact_frame,
        0.0, turns_in, previous_quaternion=None)
    _insert_helical_segment(
        obj, base_rotation, longitudinal,
        contact_location, start_location,
        contact_frame, end_frame,
        turns_in, turns_in + turns_out, previous_quaternion=previous_quaternion)

    if obj.animation_data and obj.animation_data.action:
        _set_fcurve_interpolation_linear(obj.animation_data.action)

    obj['DSG_clockwise_helical_animation'] = True
    obj['DSG_helical_turns_in'] = float(turns_in)
    obj['DSG_helical_turns_out'] = float(turns_out)
    obj['DSG_helical_turns'] = float(turns_in + turns_out)
    obj['DSG_longitudinal_rotation_axis_world'] = list(longitudinal)
    obj['DSG_rotation_axis_from_insertion_path'] = True
    obj['DSG_roundtrip_animation'] = True
    return longitudinal


def ensure_animated_drill_material():
    material = bpy.data.materials.get(ANIMATED_DRILL_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(ANIMATED_DRILL_MATERIAL)
    try:
        material.use_nodes = False
        material.diffuse_color = (0.07, 0.09, 0.12, 1.0)
        material.metallic = 0.75
        material.roughness = 0.28
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def _set_constant_interpolation_for_data_paths(action, data_paths):
    if action is None:
        return
    wanted = set(data_paths)
    try:
        for fcurve in action.fcurves:
            if fcurve.data_path not in wanted:
                continue
            for key in fcurve.keyframe_points:
                key.interpolation = 'CONSTANT'
                key.handle_left_type = 'VECTOR'
                key.handle_right_type = 'VECTOR'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def clear_implant_drill_visibility_animation(implant_obj):
    if not _valid_obj(implant_obj):
        return
    try:
        if implant_obj.animation_data and implant_obj.animation_data.action:
            action = implant_obj.animation_data.action
            for fcurve in list(action.fcurves):
                if fcurve.data_path in {'hide_viewport', 'hide_render'}:
                    action.fcurves.remove(fcurve)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        implant_obj.hide_viewport = False
        implant_obj.hide_render = False
        implant_obj.hide_select = False
        implant_obj.hide_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def animate_implants_hidden_until(implant_objects, hide_start_frame, reveal_frame):
    """Oculta todos los implantes durante la secuencia y los revela juntos al final."""
    hide_start_frame = int(hide_start_frame)
    reveal_frame = max(hide_start_frame + 1, int(reveal_frame))
    for implant_obj in implant_objects:
        if not _valid_obj(implant_obj):
            continue
        clear_implant_drill_visibility_animation(implant_obj)
        keyframes = []
        if hide_start_frame > 1:
            keyframes.append((hide_start_frame - 1, False))
        keyframes.extend([
            (hide_start_frame, True),
            (reveal_frame - 1, True),
            (reveal_frame, False),
        ])
        for frame, hidden in keyframes:
            implant_obj.hide_viewport = bool(hidden)
            implant_obj.hide_render = bool(hidden)
            implant_obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
            implant_obj.keyframe_insert(data_path='hide_render', frame=int(frame))
        try:
            if implant_obj.animation_data and implant_obj.animation_data.action:
                _set_constant_interpolation_for_data_paths(
                    implant_obj.animation_data.action, ('hide_viewport', 'hide_render'))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        implant_obj['DSG_implant_hidden_for_full_sequence'] = True
        implant_obj['DSG_implant_sequence_hide_start_frame'] = int(hide_start_frame)
        implant_obj['DSG_implant_sequence_reveal_frame'] = int(reveal_frame)


def _matrix_to_flat_list(matrix):
    return [float(matrix[row][col]) for row in range(4) for col in range(4)]



def _matrix_from_flat_list(values):
    values = list(values or [])
    if len(values) != 16:
        return None
    try:
        return Matrix((
            values[0:4], values[4:8], values[8:12], values[12:16],
        ))
    except Exception:
        return None



def _store_implant_final_transform(implant_obj):
    if not _valid_obj(implant_obj):
        return None
    stored = _matrix_from_flat_list(
        implant_obj.get('DSG_implant_animation_final_matrix_world'))
    if stored is not None:
        return stored
    final_matrix = implant_obj.matrix_world.copy()
    implant_obj['DSG_implant_animation_final_matrix_world'] = _matrix_to_flat_list(final_matrix)
    implant_obj['DSG_implant_animation_original_rotation_mode'] = str(implant_obj.rotation_mode)
    return final_matrix



def clear_implant_insertion_animation(implant_obj, restore_final=True):
    """Remove only animation curves created by the final insertion sequence."""
    if not _valid_obj(implant_obj):
        return
    final_matrix = _matrix_from_flat_list(
        implant_obj.get('DSG_implant_animation_final_matrix_world'))
    try:
        if implant_obj.animation_data and implant_obj.animation_data.action:
            action = implant_obj.animation_data.action
            for fcurve in list(action.fcurves):
                if fcurve.data_path in {
                        'location', 'rotation_quaternion', 'rotation_euler',
                        'hide_viewport', 'hide_render'}:
                    action.fcurves.remove(fcurve)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if restore_final and final_matrix is not None:
        try:
            implant_obj.matrix_world = final_matrix
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        original_mode = implant_obj.get('DSG_implant_animation_original_rotation_mode')
        if original_mode in {'QUATERNION', 'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX', 'AXIS_ANGLE'}:
            implant_obj.rotation_mode = str(original_mode)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        implant_obj.hide_viewport = False
        implant_obj.hide_render = False
        implant_obj.hide_select = False
        implant_obj.hide_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for key in (
            'DSG_animated_implant', 'DSG_implant_animation_start_frame',
            'DSG_implant_animation_end_frame', 'DSG_implant_animation_turns',
            'DSG_implant_animation_start_location',
            'DSG_implant_animation_final_location',
            'DSG_animation_start_frame', 'DSG_animation_end_frame'):
        try:
            if key in implant_obj:
                del implant_obj[key]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)




def _find_tooth_object_for_fdi(fdi):
    try:
        name = dental_assets.object_name(int(fdi), "TOOTH")
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            return obj
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for obj in bpy.data.objects:
        try:
            if getattr(obj, "type", None) == "MESH" and int(obj.get("DSG_fdi_number", 0) or 0) == int(fdi):
                return obj
        except Exception:
            continue
    return None


def _immediate_extraction_animation_sources(scene):
    """Return hidden/registered teeth that should be animated out first.

    Supports the classic single-tooth route and the newer multi-FDI immediate
    route.  Returned order is stable and clinical (ascending FDI).
    """
    if scene is None or core.clinical_route(scene) != core.ROUTE_IMMEDIATE:
        return []
    seen = set()
    pairs = []
    name = str(scene.get("DSG_immediate_extraction_tooth", "") or "")
    if name:
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            fdi = int(obj.get("DSG_virtual_extraction_fdi", scene.get("DSG_immediate_extraction_fdi", 0)) or 0)
            key = str(obj.name_full)
            seen.add(key)
            pairs.append((fdi or 10_000, obj))
    raw = str(scene.get("DSG_immediate_extraction_fdis", "") or "").strip()
    if raw:
        values = []
        for token in raw.replace(";", ",").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                values.append(int(token))
            except Exception:
                continue
        for fdi in sorted(set(values)):
            obj = _find_tooth_object_for_fdi(fdi)
            if not _valid_obj(obj):
                continue
            key = str(obj.name_full)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((int(fdi), obj))
    pairs.sort(key=lambda item: int(item[0]) if item[0] else 10_000)
    return [obj for _, obj in pairs]


def _copy_object_material_slots(dst, src):
    try:
        dst.data.materials.clear()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        for material in src.data.materials:
            dst.data.materials.append(material)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _estimate_extraction_axis_and_travel(tooth_obj):
    """Estimate a crown-ward extraction vector from the tooth geometry itself.

    The direction is derived from the long axis of the tooth.  We detect which
    end is crown-like by comparing the radial cross-section near both extremes:
    the crown end is usually wider than the apical/root end.  Motion is then
    forced from root toward crown, never in the apical direction.
    """
    vertices = getattr(getattr(tooth_obj, "data", None), "vertices", None)
    if not vertices:
        return Vector((0.0, 0.0, 1.0)), 10.0
    count = len(vertices)
    if count < 8:
        return Vector((0.0, 0.0, 1.0)), 10.0
    step = max(1, count // 12000)
    coords = np.array(
        [(tooth_obj.matrix_world @ vertices[i].co)[:] for i in range(0, count, step)],
        dtype=np.float64,
    )
    if len(coords) < 8:
        return Vector((0.0, 0.0, 1.0)), 10.0

    center = coords.mean(axis=0)
    centered = coords - center
    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        axis = vh[0]
    except Exception:
        cov = np.cov(centered.T)
        evals, evecs = np.linalg.eigh(cov)
        axis = evecs[:, int(np.argmax(evals))]
    axis = np.asarray(axis, dtype=np.float64)
    axis_norm = np.linalg.norm(axis)
    if axis_norm < 1e-9:
        return Vector((0.0, 0.0, 1.0)), 10.0
    axis /= axis_norm

    projections = centered @ axis
    p_low = float(np.quantile(projections, 0.18))
    p_high = float(np.quantile(projections, 0.82))
    low_pts = coords[projections <= p_low]
    high_pts = coords[projections >= p_high]
    if len(low_pts) < 3 or len(high_pts) < 3:
        lo = int(np.argmin(projections))
        hi = int(np.argmax(projections))
        direction = coords[hi] - coords[lo]
        length = float(projections.max() - projections.min())
        if np.linalg.norm(direction) < 1e-9:
            direction = axis
        direction /= max(np.linalg.norm(direction), 1e-9)
        travel = float(np.clip(length * 0.90 + ANIMATION_EXTRACTION_CLEARANCE_EXTRA_MM_FIXED,
                               ANIMATION_EXTRACTION_CLEARANCE_MIN_MM_FIXED,
                               ANIMATION_EXTRACTION_CLEARANCE_MAX_MM_FIXED))
        return Vector(direction.tolist()), travel

    def _end_width(end_pts):
        rel = end_pts - center
        # radial distance to the long axis line through the global centroid
        proj = rel @ axis
        closest = np.outer(proj, axis)
        radial = rel - closest
        norms = np.linalg.norm(radial, axis=1)
        return float(np.mean(norms)) if len(norms) else 0.0

    low_width = _end_width(low_pts)
    high_width = _end_width(high_pts)
    if high_width >= low_width:
        crown = high_pts.mean(axis=0)
        root = low_pts.mean(axis=0)
    else:
        crown = low_pts.mean(axis=0)
        root = high_pts.mean(axis=0)

    direction = crown - root
    direction_norm = np.linalg.norm(direction)
    if direction_norm < 1e-9:
        direction = axis
        direction_norm = np.linalg.norm(direction)
    direction /= max(direction_norm, 1e-9)

    tooth_length = float(projections.max() - projections.min())
    travel = float(np.clip(
        tooth_length * 0.90 + ANIMATION_EXTRACTION_CLEARANCE_EXTRA_MM_FIXED,
        ANIMATION_EXTRACTION_CLEARANCE_MIN_MM_FIXED,
        ANIMATION_EXTRACTION_CLEARANCE_MAX_MM_FIXED,
    ))
    return Vector(direction.tolist()), travel


def clear_animated_extraction_teeth():
    removed = 0
    for obj in list(bpy.data.objects):
        if not _valid_obj(obj):
            continue
        if not (str(getattr(obj, "name", "")).startswith(ANIMATED_EXTRACTION_TOOTH_PREFIX)
                or bool(obj.get("DSG_animated_extraction_tooth", False))):
            continue
        mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed


def get_animated_extraction_tooth_objects():
    return sorted(
        [obj for obj in bpy.data.objects
         if _valid_obj(obj)
         and (bool(obj.get("DSG_animated_extraction_tooth", False))
              or str(obj.name).startswith(ANIMATED_EXTRACTION_TOOTH_PREFIX))],
        key=lambda obj: obj.name,
    )


def build_animated_extraction_tooth(context, tooth_obj, index=0,
                                    start_frame_override=None,
                                    end_frame_override=None):
    """Create a visible duplicate of the virtually extracted tooth and animate it out."""
    if not _valid_obj(tooth_obj):
        return None
    start_frame = max(1, int(start_frame_override if start_frame_override is not None else 1))
    end_frame = max(start_frame + 1, int(end_frame_override if end_frame_override is not None else
                                         (start_frame + ANIMATION_EXTRACTION_DURATION_FRAMES_FIXED)))
    disappear_frame = end_frame + 1

    duplicate = tooth_obj.copy()
    duplicate.data = tooth_obj.data.copy()
    duplicate.name = f"{ANIMATED_EXTRACTION_TOOTH_PREFIX}{index:02d}"
    try:
        context.scene.collection.objects.link(duplicate)
    except Exception:
        linked = False
        for collection in tooth_obj.users_collection:
            try:
                collection.objects.link(duplicate)
                linked = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not linked:
            bpy.context.scene.collection.objects.link(duplicate)

    duplicate.matrix_world = tooth_obj.matrix_world.copy()
    _copy_object_material_slots(duplicate, tooth_obj)
    duplicate.hide_viewport = False
    duplicate.hide_render = False
    duplicate.hide_select = False
    try:
        duplicate.hide_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    final_location = duplicate.matrix_world.translation.copy()
    final_rotation = duplicate.matrix_world.to_quaternion()
    direction, travel = _estimate_extraction_axis_and_travel(tooth_obj)
    if direction.length < 1e-8:
        direction = Vector((0.0, 0.0, 1.0))
    direction.normalize()
    start_location = final_location.copy()
    end_location = final_location + direction * float(travel)

    duplicate.rotation_mode = "QUATERNION"
    if start_frame > 1:
        duplicate.hide_viewport = True
        duplicate.hide_render = True
        duplicate.keyframe_insert(data_path="hide_viewport", frame=start_frame - 1)
        duplicate.keyframe_insert(data_path="hide_render", frame=start_frame - 1)

    # visible and seated at the extraction start
    duplicate.hide_viewport = False
    duplicate.hide_render = False
    duplicate.location = start_location
    duplicate.rotation_quaternion = final_rotation
    duplicate.keyframe_insert(data_path="hide_viewport", frame=start_frame)
    duplicate.keyframe_insert(data_path="hide_render", frame=start_frame)
    duplicate.keyframe_insert(data_path="location", frame=start_frame)
    duplicate.keyframe_insert(data_path="rotation_quaternion", frame=start_frame)

    # extracted along the crown-ward axis
    duplicate.location = end_location
    duplicate.rotation_quaternion = final_rotation
    duplicate.keyframe_insert(data_path="location", frame=end_frame)
    duplicate.keyframe_insert(data_path="rotation_quaternion", frame=end_frame)

    # then disappears before the normal guide/screw/drill/implant protocol starts
    duplicate.hide_viewport = False
    duplicate.hide_render = False
    duplicate.keyframe_insert(data_path="hide_viewport", frame=end_frame)
    duplicate.keyframe_insert(data_path="hide_render", frame=end_frame)
    duplicate.hide_viewport = True
    duplicate.hide_render = True
    duplicate.keyframe_insert(data_path="hide_viewport", frame=disappear_frame)
    duplicate.keyframe_insert(data_path="hide_render", frame=disappear_frame)

    try:
        if duplicate.animation_data and duplicate.animation_data.action:
            _set_fcurve_interpolation_linear(
                duplicate.animation_data.action,
                prefixes=("location", "rotation_quaternion"),
            )
            _set_constant_interpolation_for_data_paths(
                duplicate.animation_data.action, ("hide_viewport", "hide_render")
            )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    duplicate["DSG_animated_extraction_tooth"] = True
    duplicate["DSG_animation_start_frame"] = int(start_frame)
    duplicate["DSG_animation_end_frame"] = int(disappear_frame)
    duplicate["DSG_extraction_direction_world"] = [float(v) for v in direction]
    duplicate["DSG_extraction_travel_mm"] = float(travel)
    duplicate["DSG_source_tooth_name"] = str(tooth_obj.name)
    try:
        duplicate["DSG_virtual_extraction_fdi"] = int(tooth_obj.get("DSG_virtual_extraction_fdi", 0) or tooth_obj.get("DSG_fdi_number", 0) or 0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return duplicate


def get_animated_implant_objects():
    return sorted(
        [obj for obj in get_all_implant_objects(bpy.context.scene.dsg_props)
         if _valid_obj(obj) and bool(obj.get('DSG_animated_implant', False))],
        key=lambda obj: obj.name,
    )



def _implant_start_location_above_sleeve(props, implant_obj, final_matrix):
    """Places the complete implant immediately above the occlusal sleeve face."""
    _drill_rotation, occlusal_axis = _rotation_for_drill_on_sleeve(props, implant_obj)
    occlusal_axis = _normalized_or_fallback(occlusal_axis, (0.0, 0.0, 1.0))
    sleeve_height = max(0.50, float(getattr(props, 'sleeve_height', 7.0)))
    sleeve_center = get_sleeve_center_world(props, implant_obj)
    sleeve_face = sleeve_center + occlusal_axis * (sleeve_height * 0.5)
    final_location = final_matrix.translation.copy()

    # Find the most apical point of the implant relative to the occlusal axis.
    # That point is placed just outside the sleeve entrance, so the implant
    # starts completely above the sleeve rather than intersecting it.
    min_relative_projection = None
    try:
        linear = final_matrix.to_3x3()
        for corner in implant_obj.bound_box:
            relative_world = linear @ Vector(corner)
            projection = relative_world.dot(occlusal_axis)
            min_relative_projection = (
                projection if min_relative_projection is None
                else min(min_relative_projection, projection))
    except Exception:
        min_relative_projection = None
    if min_relative_projection is None:
        implant_length = max(0.5, float(get_implant_length_world(props, implant_obj)))
        min_relative_projection = -implant_length * 0.5

    current_apical_projection = (
        final_location.dot(occlusal_axis) + float(min_relative_projection))
    desired_apical_projection = (
        sleeve_face.dot(occlusal_axis)
        + ANIMATION_IMPLANT_START_CLEARANCE_MM_FIXED)
    travel = max(0.50, desired_apical_projection - current_apical_projection)
    return final_location + occlusal_axis * travel, occlusal_axis, travel



def animate_implant_screw_in_after_drill(props, implant_obj, sequence_start_frame,
                                         insertion_start_frame, insertion_end_frame):
    """Reveal the implant above its sleeve and screw it into its planned pose."""
    if not is_valid_implant_obj(implant_obj):
        return False
    clear_implant_insertion_animation(implant_obj, restore_final=True)
    final_matrix = _store_implant_final_transform(implant_obj)
    if final_matrix is None:
        return False

    final_location = final_matrix.translation.copy()
    final_rotation = final_matrix.to_quaternion()
    start_location, occlusal_axis, travel = _implant_start_location_above_sleeve(
        props, implant_obj, final_matrix)
    sequence_start_frame = max(1, int(sequence_start_frame))
    insertion_start_frame = max(sequence_start_frame + 1, int(insertion_start_frame))
    insertion_end_frame = max(insertion_start_frame + 1, int(insertion_end_frame))

    # Hidden throughout the drilling phase; visible exactly when insertion starts.
    visibility_keys = []
    if sequence_start_frame > 1:
        visibility_keys.append((sequence_start_frame - 1, False))
    visibility_keys.extend([
        (sequence_start_frame, True),
        (insertion_start_frame - 1, True),
        (insertion_start_frame, False),
    ])
    for frame, hidden in visibility_keys:
        implant_obj.hide_viewport = bool(hidden)
        implant_obj.hide_render = bool(hidden)
        implant_obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
        implant_obj.keyframe_insert(data_path='hide_render', frame=int(frame))

    implant_obj.rotation_mode = 'QUATERNION'
    turns = max(
        ANIMATED_IMPLANT_MIN_TURNS,
        float(travel) * ANIMATED_IMPLANT_TURNS_PER_MM)
    apply_clockwise_helical_animation(
        implant_obj, final_rotation,
        start_location, final_location,
        insertion_start_frame, insertion_end_frame, turns)

    try:
        if implant_obj.animation_data and implant_obj.animation_data.action:
            _set_constant_interpolation_for_data_paths(
                implant_obj.animation_data.action,
                ('hide_viewport', 'hide_render'))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    implant_obj['DSG_animated_implant'] = True
    implant_obj['DSG_implant_animation_start_frame'] = int(insertion_start_frame)
    implant_obj['DSG_implant_animation_end_frame'] = int(insertion_end_frame)
    implant_obj['DSG_animation_start_frame'] = int(insertion_start_frame)
    implant_obj['DSG_animation_end_frame'] = int(insertion_end_frame)
    implant_obj['DSG_implant_animation_turns'] = float(turns)
    implant_obj['DSG_implant_animation_start_location'] = list(start_location)
    implant_obj['DSG_implant_animation_final_location'] = list(final_location)
    implant_obj['DSG_implant_starts_above_sleeve'] = True
    implant_obj['DSG_implant_starts_after_drill_return'] = True
    implant_obj['DSG_implant_insertion_axis_world'] = list(-occlusal_axis)
    return True


def animate_implant_hidden_during_drill(implant_obj, start_frame, end_frame):
    # Compatibilidad con llamadas antiguas: ahora el implante se revela al final.
    animate_implants_hidden_until([implant_obj], start_frame, int(end_frame) + 1)


def get_animated_drill_objects():
    return sorted(
        [obj for obj in bpy.data.objects
         if _valid_obj(obj) and obj.name.startswith(ANIMATED_DRILL_PREFIX)],
        key=lambda obj: obj.name,
    )


def remove_animated_drills():
    removed = 0
    implant_names = set()
    for obj in list(bpy.data.objects):
        if obj.name.startswith(ANIMATED_DRILL_PREFIX):
            implant_name = obj.get('DSG_implant_name')
            if implant_name:
                implant_names.add(str(implant_name))
            if safe_remove_object(obj):
                removed += 1
    for implant_name in implant_names:
        implant_obj = bpy.data.objects.get(implant_name)
        clear_implant_insertion_animation(implant_obj, restore_final=True)
        clear_implant_drill_visibility_animation(implant_obj)
    return removed


def _rotation_for_drill_on_sleeve(props, implant_obj):
    """Orienta +Z local de la fresa hacia la entrada oclusal del sleeve."""
    sleeve_mx = get_sleeve_matrix_world(props, implant_obj)
    sleeve_axis = _normalized_or_fallback(
        sleeve_mx.to_3x3() @ Vector((0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
    sign = get_sleeve_occlusal_sign(props, implant_obj)
    z_axis = sleeve_axis * float(sign)

    x_hint = sleeve_mx.to_3x3() @ Vector((1.0, 0.0, 0.0))
    x_axis = x_hint - z_axis * x_hint.dot(z_axis)
    if x_axis.length < 1e-8:
        x_axis = z_axis.cross(Vector((0.0, 1.0, 0.0)))
    if x_axis.length < 1e-8:
        x_axis = Vector((1.0, 0.0, 0.0))
    x_axis.normalize()
    y_axis = z_axis.cross(x_axis)
    if y_axis.length < 1e-8:
        y_axis = Vector((0.0, 1.0, 0.0))
    y_axis.normalize()
    x_axis = y_axis.cross(z_axis).normalized()
    rotation_matrix = Matrix((x_axis, y_axis, z_axis)).transposed()
    return rotation_matrix.to_quaternion(), z_axis


def build_animated_drill_for_implant(context, props, implant_obj, index,
                                      start_frame_override=None, end_frame_override=None):
    """Crea y anima una fresa coaxial calibrada contra el lumen del sleeve."""
    if not is_valid_implant_obj(implant_obj):
        return None

    name = f'{ANIMATED_DRILL_PREFIX}{index:02d}'
    safe_remove_by_name(name)

    # El cilindro guía visual utiliza el diámetro de fresa elegido para el sleeve.
    guide_diameter_mm = max(
        0.50, float(getattr(props, 'sleeve_inner_diameter', DRILL_FIXED_GUIDE_DIAMETER_MM)))
    sleeve_height = max(0.50, float(getattr(props, 'sleeve_height', 7.0)))
    implant_length = max(0.50, float(get_implant_length_world(props, implant_obj)))
    mesh, template_scale, stop_local_mm, guide_bottom_local_mm, tip_local_mm = (
        make_embedded_drill_visual_mesh(
            name + '_Mesh',
            guide_diameter_mm=guide_diameter_mm,
            guide_length_mm=sleeve_height,
            active_length_mm=implant_length,
        )
    )
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    register_dsg_object(obj, ROLE_DRILL_VISUAL, name, {
        'DSG_visual_only': True,
        'DSG_animated_drill': True,
        'DSG_implant_name': implant_obj.name,
        'DSG_drill_guide_diameter_mm': guide_diameter_mm,
        'DSG_drill_guide_length_mm': float(sleeve_height),
        'DSG_drill_active_length_mm': float(implant_length),
        'DSG_drill_axis_straightened': True,
        'DSG_drill_shank_surface_of_revolution': True,
        'DSG_drill_stop_local_z_mm': float(stop_local_mm),
        'DSG_drill_guide_bottom_local_z_mm': float(guide_bottom_local_mm),
        'DSG_drill_tip_local_z_mm': float(tip_local_mm),
        'DSG_template_scale': float(template_scale),
    })

    material = ensure_animated_drill_material()
    try:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj.display_type = 'SOLID'
    obj.show_in_front = False
    obj.hide_render = True

    rotation, occlusal_axis = _rotation_for_drill_on_sleeve(props, implant_obj)
    sleeve_center = get_sleeve_center_world(props, implant_obj)
    sleeve_occlusal_face = sleeve_center + occlusal_axis * (sleeve_height * 0.5)

    # La pequeña cara plana situada justo después del cilindro guía debe
    # coincidir con la cara oclusal del sleeve. Así el cilindro grande queda
    # introducido dentro del sleeve y no flotando ni atravesándolo.
    contact_offset = float(DRILL_STOP_CONTACT_OFFSET_MM)
    # Coincidencia geométrica exacta: el inicio del hombro posterior al cilindro
    # queda sobre la cara oclusal del sleeve. Un offset positivo separaría la
    # fresa; cero representa contacto sin enterramiento.
    final_location = (sleeve_occlusal_face
                      - occlusal_axis * stop_local_mm
                      + occlusal_axis * contact_offset)
    start_offset = max(1.0, float(getattr(props, 'drill_animation_distance', 25.0)))
    start_location = final_location + occlusal_axis * start_offset

    start_frame = (int(start_frame_override) if start_frame_override is not None
                   else int(getattr(props, 'drill_animation_start_frame', 1)))
    end_frame = (int(end_frame_override) if end_frame_override is not None
                 else int(getattr(props, 'drill_animation_end_frame', 60)))
    if end_frame <= start_frame:
        end_frame = start_frame + 1

    total_duration = max(2, end_frame - start_frame)
    contact_frame = start_frame + max(1, int(math.ceil(total_duration * 0.5)))
    if contact_frame >= end_frame:
        contact_frame = end_frame - 1
    drill_turns = max(ANIMATED_DRILL_MIN_TURNS,
                      start_offset * ANIMATED_DRILL_TURNS_PER_MM)
    apply_clockwise_helical_roundtrip_animation(
        obj, rotation, start_location, final_location,
        start_frame, contact_frame, end_frame,
        drill_turns, turns_out=drill_turns)

    obj['DSG_animation_start_frame'] = start_frame
    obj['DSG_animation_contact_frame'] = int(contact_frame)
    obj['DSG_animation_end_frame'] = end_frame
    obj['DSG_animation_distance'] = start_offset
    obj['DSG_final_tip_depth_from_sleeve_top_mm'] = float(sleeve_height + implant_length)
    obj['DSG_tip_never_beyond_implant'] = True
    obj['DSG_stop_contact_world'] = list(sleeve_occlusal_face)
    obj['DSG_stop_plane_local_z'] = float(stop_local_mm)
    obj['DSG_stop_contact_offset_mm'] = float(contact_offset)
    obj['DSG_fixed_guide_diameter_mm'] = float(guide_diameter_mm)
    obj['DSG_clockwise_viewed_from_sleeve_entry'] = True
    obj['DSG_visibility_managed_by_sequence'] = True
    obj['DSG_drill_returns_to_start'] = True
    obj['DSG_hides_implant_while_moving'] = True

    # The drill is visible only during its own in-and-out movement. At the
    # first implant-insertion frame (end_frame + 1) it is already hidden.
    visibility_keys = []
    if start_frame > 1:
        visibility_keys.append((start_frame - 1, True))
    visibility_keys.extend([
        (start_frame, False),
        (end_frame, False),
        (end_frame + 1, True),
    ])
    for frame, hidden in visibility_keys:
        obj.hide_viewport = bool(hidden)
        obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
    try:
        if obj.animation_data and obj.animation_data.action:
            _set_constant_interpolation_for_data_paths(
                obj.animation_data.action, ('hide_viewport',))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj['DSG_hidden_during_implant_insertion'] = True
    return obj


def _decode_microscrew_visual_template():
    """Decodifica la malla compacta integrada del microtornillo."""
    global _MICROSCREW_VISUAL_TEMPLATE_CACHE
    if _MICROSCREW_VISUAL_TEMPLATE_CACHE is not None:
        return _MICROSCREW_VISUAL_TEMPLATE_CACHE
    try:
        raw = zlib.decompress(base64.b85decode(
            _MICROSCREW_VISUAL_TEMPLATE_B85.encode('ascii')))
    except Exception as exc:
        raise RuntimeError(f'No se pudo descomprimir la plantilla del microtornillo: {exc}') from exc
    if len(raw) < 8:
        raise RuntimeError('Empty or incomplete microscrew template')
    vertex_count, face_count = struct.unpack_from('<II', raw, 0)
    expected = 8 + vertex_count * 12 + face_count * 12
    if vertex_count <= 0 or face_count <= 0 or len(raw) != expected:
        raise RuntimeError(
            f'Invalid microscrew internal format: '
            f'{vertex_count} vertices, {face_count} faces, {len(raw)} bytes')
    if vertex_count != MICROSCREW_TEMPLATE_VERTS or face_count != MICROSCREW_TEMPLATE_FACES:
        raise RuntimeError(
            f'Plantilla del microtornillo no coincide con la versión del addon '
            f'({vertex_count}/{face_count} frente a '
            f'{MICROSCREW_TEMPLATE_VERTS}/{MICROSCREW_TEMPLATE_FACES})')
    offset = 8
    vertices = [
        struct.unpack_from('<fff', raw, offset + index * 12)
        for index in range(vertex_count)
    ]
    offset += vertex_count * 12
    faces = [
        struct.unpack_from('<III', raw, offset + index * 12)
        for index in range(face_count)
    ]
    _MICROSCREW_VISUAL_TEMPLATE_CACHE = (vertices, faces)
    return _MICROSCREW_VISUAL_TEMPLATE_CACHE


def _normalized_microscrew_dimensions(diameter_mm=None, length_mm=None):
    diameter = max(
        MICROSCREW_DIAMETER_MIN_MM,
        min(MICROSCREW_DIAMETER_MAX_MM,
            float(MICROSCREW_DIAMETER_DEFAULT_MM if diameter_mm is None else diameter_mm)))
    length = max(
        MICROSCREW_LENGTH_MIN_MM,
        min(MICROSCREW_LENGTH_MAX_MM,
            float(MICROSCREW_LENGTH_DEFAULT_MM if length_mm is None else length_mm)))
    return diameter, length


def _microscrew_dimensions_from_props(props):
    return _normalized_microscrew_dimensions(
        getattr(props, 'microscrew_diameter', MICROSCREW_DIAMETER_DEFAULT_MM),
        getattr(props, 'microscrew_length', MICROSCREW_LENGTH_DEFAULT_MM))


def _microscrew_dimensions_from_record(record):
    record = record if isinstance(record, dict) else {}
    return _normalized_microscrew_dimensions(
        record.get('diameter', record.get('guided_diameter', MICROSCREW_DIAMETER_DEFAULT_MM)),
        record.get('length', MICROSCREW_LENGTH_DEFAULT_MM))


def make_embedded_microscrew_visual_mesh(name, diameter_mm=None, length_mm=None):
    """Create the embedded screw STL at the selected clinical dimensions.

    The stop/contact plane remains at local Z=0.  Only the active portion below
    that plane is stretched to the selected length; the head height is preserved.
    Radial dimensions scale from the original Ø2 mm template.
    """
    diameter, length = _normalized_microscrew_dimensions(diameter_mm, length_mm)
    vertices, faces = _decode_microscrew_visual_template()
    radial_scale = diameter / max(1.0e-8, MICROSCREW_GUIDED_DIAMETER_MM)
    axial_scale = length / max(1.0e-8, MICROSCREW_TEMPLATE_ACTIVE_LENGTH_MM)
    contact_z = float(MICROSCREW_TEMPLATE_CONTACT_Z_MM)
    scaled_vertices = []
    for x, y, z in vertices:
        z = float(z)
        if z <= contact_z:
            z = contact_z - (contact_z - z) * axial_scale
        scaled_vertices.append((float(x) * radial_scale, float(y) * radial_scale, z))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(scaled_vertices, [], faces)
    try:
        mesh.validate(clean_customdata=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh.update(calc_edges=True)
    return mesh


def ensure_animated_microscrew_material():
    """Distinct metallic violet for every visual microscrew.

    Violet is intentionally separated from both the warm model and the existing
    blue blockout. The material is visual-only and never enters guide booleans.
    """
    material = bpy.data.materials.get(ANIMATED_MICROSCREW_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(ANIMATED_MICROSCREW_MATERIAL)
    try:
        material.use_nodes = True
        material.diffuse_color = (0.34, 0.10, 0.52, 1.0)
        material.metallic = 0.72
        material.roughness = 0.22
        nodes = material.node_tree.nodes if material.node_tree else None
        bsdf = nodes.get('Principled BSDF') if nodes else None
        _set_principled_input(bsdf, ('Base Color',), (0.24, 0.045, 0.42, 1.0))
        _set_principled_input(bsdf, ('Metallic',), 0.72)
        _set_principled_input(bsdf, ('Roughness',), 0.22)
        _set_principled_input(bsdf, ('Coat Weight', 'Clearcoat'), 0.25)
        _set_principled_input(bsdf, ('Coat Roughness', 'Clearcoat Roughness'), 0.12)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def get_animated_microscrew_objects():
    """Returns every DSG animated microscrew, including renamed stale copies."""
    objects = []
    for obj in list(bpy.data.objects):
        try:
            if not _valid_obj(obj):
                continue
            if (obj.name.startswith(ANIMATED_MICROSCREW_PREFIX)
                    or bool(obj.get('DSG_animated_microscrew', False))):
                objects.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    return sorted(
        objects,
        key=lambda obj: (
            int(obj.get('DSG_microscrew_index', 0)),
            obj.name),
    )


def get_static_microscrew_visual_objects(include_preview=False):
    """Returns planning-only screws that must not coexist with animation copies."""
    objects = []
    for obj in list(bpy.data.objects):
        try:
            if not _valid_obj(obj):
                continue
            is_preview = (
                bool(obj.get('DSG_microscrew_visual_preview', False))
                or obj.name == MICROSCREW_VISUAL_PREVIEW_NAME
                or obj.name.startswith(MICROSCREW_VISUAL_PREVIEW_NAME + '.'))
            is_static = (
                bool(obj.get('DSG_static_microscrew', False))
                or (obj.name.startswith(MICROSCREW_VISUAL_PREFIX)
                    and not bool(obj.get('DSG_animated_microscrew', False))))
            if not is_static or (is_preview and not include_preview):
                continue
            objects.append(obj)
        except (ReferenceError, RuntimeError):
            continue
    return sorted(
        objects,
        key=lambda obj: (
            int(obj.get('DSG_microscrew_index', 0)),
            obj.name),
    )


def set_static_microscrew_visuals_hidden(hidden, include_preview=False):
    """Hide planning screws while animated copies exist, preserving user state.

    Before v7.0.49 the static planning STL remained visible during the final
    sequence.  It could therefore look like a screw frozen at an old position
    while the rebuilt screw moved along the corrected trajectory.
    """
    hidden = bool(hidden)
    changed = 0
    state_key = 'DSG_hidden_by_microscrew_animation'
    for obj in get_static_microscrew_visual_objects(include_preview=include_preview):
        try:
            if hidden:
                if not bool(obj.get(state_key, False)):
                    obj['DSG_pre_animation_hide_viewport'] = bool(obj.hide_viewport)
                    obj['DSG_pre_animation_hide_select'] = bool(obj.hide_select)
                    try:
                        obj['DSG_pre_animation_hide_set'] = bool(obj.hide_get())
                    except Exception:
                        obj['DSG_pre_animation_hide_set'] = False
                    obj[state_key] = True
                obj.hide_viewport = True
                obj.hide_select = True
                obj.hide_render = True
                try:
                    obj.hide_set(True)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                changed += 1
            elif bool(obj.get(state_key, False)):
                obj.hide_viewport = bool(obj.get(
                    'DSG_pre_animation_hide_viewport', False))
                obj.hide_select = bool(obj.get(
                    'DSG_pre_animation_hide_select', False))
                obj.hide_render = True
                try:
                    obj.hide_set(bool(obj.get(
                        'DSG_pre_animation_hide_set', False)))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                for key in (
                        state_key,
                        'DSG_pre_animation_hide_viewport',
                        'DSG_pre_animation_hide_select',
                        'DSG_pre_animation_hide_set'):
                    try:
                        if key in obj:
                            del obj[key]
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
                changed += 1
        except (ReferenceError, RuntimeError):
            continue
    return changed


def remove_pending_microscrew_geometry_previews(keep=None):
    """Remove stale pending sleeve/support previews, including ``.001`` copies."""
    removed = 0
    keep_name = _safe_object_name(keep) if _valid_obj(keep) else None
    for obj in list(bpy.data.objects):
        try:
            if keep_name and obj.name == keep_name:
                continue
            is_pending = bool(obj.get('DSG_microscrew_preview', False))
            has_pending_name = (
                obj.name == MICROSCREW_PREVIEW_NAME
                or obj.name.startswith(MICROSCREW_PREVIEW_NAME + '.'))
            if (is_pending or has_pending_name) and safe_remove_object(obj):
                removed += 1
        except (ReferenceError, RuntimeError):
            continue
    return removed


def remove_pending_microscrew_visuals():
    """Remove every pending visual copy, not only the exact unsuffixed name."""
    removed = 0
    for obj in list(bpy.data.objects):
        try:
            is_pending = bool(obj.get('DSG_microscrew_visual_preview', False))
            has_pending_name = (
                obj.name == MICROSCREW_VISUAL_PREVIEW_NAME
                or obj.name.startswith(MICROSCREW_VISUAL_PREVIEW_NAME + '.'))
            if (is_pending or has_pending_name) and safe_remove_object(obj):
                removed += 1
        except (ReferenceError, RuntimeError):
            continue
    return removed


def remove_animated_microscrews(restore_static=True):
    removed = 0
    for obj in get_animated_microscrew_objects():
        if safe_remove_object(obj):
            removed += 1
    if restore_static:
        set_static_microscrew_visuals_hidden(False)
    return removed


def invalidate_microscrew_animation(context=None):
    """Discard animation copies after a placement changes.

    This prevents an old generated screw from surviving after the editable
    three-point preview has been moved and rebuilt.
    """
    try:
        screen = getattr(context, 'screen', None) if context is not None else None
        if screen and screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return remove_animated_microscrews(restore_static=True)


def _rotation_for_microscrew_axis(axis, x_hint=None):
    """Orienta +Z local hacia la entrada coronal del sleeve."""
    z_axis = _normalized_or_fallback(axis, (0.0, 0.0, 1.0))
    hint = Vector(x_hint) if x_hint is not None else Vector((1.0, 0.0, 0.0))
    x_axis = hint - z_axis * hint.dot(z_axis)
    if x_axis.length < 1e-8:
        x_axis = z_axis.cross(Vector((0.0, 1.0, 0.0)))
    if x_axis.length < 1e-8:
        x_axis = Vector((1.0, 0.0, 0.0))
    x_axis.normalize()
    y_axis = z_axis.cross(x_axis)
    if y_axis.length < 1e-8:
        y_axis = Vector((0.0, 1.0, 0.0))
    y_axis.normalize()
    x_axis = y_axis.cross(z_axis).normalized()
    return Matrix((x_axis, y_axis, z_axis)).transposed().to_quaternion(), z_axis




def build_static_microscrew_visual(context, record, name, index=0, preview=False):
    """Crea el STL visual del microtornillo ya asentado sobre el sleeve.

    Se usa en el paso de marcar 3 puntos para que el usuario no vea solo el
    tubo/sleeve de guía, sino también el microtornillo real que ocupará esa
    trayectoria.  Es visual-only: no entra en booleanas ni en remesh.
    """
    if preview:
        remove_pending_microscrew_visuals()
    else:
        safe_remove_by_name(name)
    diameter, length = _microscrew_dimensions_from_record(record)
    mesh = make_embedded_microscrew_visual_mesh(name + '_Mesh', diameter, length)
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)

    axis = _normalized_or_fallback(record.get('axis'), (0.0, 0.0, 1.0))
    sleeve_top = Vector(record.get('sleeve_top', (0.0, 0.0, 0.0)))
    x_hint = record.get('x_hint', (1.0, 0.0, 0.0))
    rotation, insertion_axis = _rotation_for_microscrew_axis(axis, x_hint)
    final_location = sleeve_top - insertion_axis * MICROSCREW_TEMPLATE_CONTACT_Z_MM

    obj.rotation_euler = rotation.to_euler()
    obj.location = final_location
    register_dsg_object(obj, ROLE_MICROSCREW_VISUAL, name, {
        'DSG_visual_only': True,
        'DSG_static_microscrew': True,
        'DSG_microscrew_visual_preview': bool(preview),
        'DSG_microscrew_index': int(index),
        'DSG_microscrew_axis': list(axis),
        'DSG_microscrew_sleeve_top': list(sleeve_top),
        'DSG_microscrew_guided_diameter_mm': diameter,
        'DSG_microscrew_diameter_mm': diameter,
        'DSG_microscrew_length_mm': length,
        'DSG_microscrew_stop_radius_mm': MICROSCREW_STOP_RADIUS_MM * (diameter / MICROSCREW_GUIDED_DIAMETER_MM),
        'DSG_microscrew_contact_local_z_mm': MICROSCREW_TEMPLATE_CONTACT_Z_MM,
        'DSG_tip_final_world': list(final_location - insertion_axis * length),
        'DSG_stop_contact_world': list(sleeve_top),
    })
    material = ensure_animated_microscrew_material()
    try:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj.display_type = 'SOLID'
    obj.show_in_front = True
    obj.hide_render = True
    return obj

def build_animated_microscrew(context, props, record, index,
                                start_frame_override=None, end_frame_override=None):
    """Crea el tornillo STL y anima su inserción coaxial hasta el asiento."""
    name = f'{ANIMATED_MICROSCREW_PREFIX}{index:02d}'
    safe_remove_by_name(name)
    diameter, length = _microscrew_dimensions_from_record(record)
    mesh = make_embedded_microscrew_visual_mesh(name + '_Mesh', diameter, length)
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)

    axis = _normalized_or_fallback(record.get('axis'), (0.0, 0.0, 1.0))
    sleeve_top = Vector(record.get('sleeve_top', (0.0, 0.0, 0.0)))
    x_hint = record.get('x_hint', (1.0, 0.0, 0.0))
    rotation, insertion_axis = _rotation_for_microscrew_axis(axis, x_hint)

    # La plantilla tiene el plano de contacto en Z local = 0. La sección cónica
    # inferior entra en el collar y la corona más ancha queda por encima,
    # deteniéndose exactamente en la cara superior del sleeve.
    final_location = sleeve_top - insertion_axis * MICROSCREW_TEMPLATE_CONTACT_Z_MM
    start_offset = max(
        2.0, float(getattr(props, 'microscrew_animation_distance', 15.0)))
    start_location = final_location + insertion_axis * start_offset
    start_frame = (int(start_frame_override) if start_frame_override is not None
                   else int(getattr(props, 'microscrew_animation_start_frame', 1)))
    end_frame = (int(end_frame_override) if end_frame_override is not None
                 else int(getattr(props, 'microscrew_animation_end_frame', 60)))
    if end_frame <= start_frame:
        end_frame = start_frame + 1

    register_dsg_object(obj, ROLE_MICROSCREW_VISUAL, name, {
        'DSG_visual_only': True,
        'DSG_animated_microscrew': True,
        'DSG_microscrew_index': int(index),
        'DSG_microscrew_axis': list(axis),
        'DSG_microscrew_sleeve_top': list(sleeve_top),
        'DSG_microscrew_guided_diameter_mm': diameter,
        'DSG_microscrew_diameter_mm': diameter,
        'DSG_microscrew_length_mm': length,
        'DSG_microscrew_stop_radius_mm': MICROSCREW_STOP_RADIUS_MM * (diameter / MICROSCREW_GUIDED_DIAMETER_MM),
        'DSG_microscrew_contact_local_z_mm': MICROSCREW_TEMPLATE_CONTACT_Z_MM,
    })
    material = ensure_animated_microscrew_material()
    try:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj.display_type = 'SOLID'
    obj.show_in_front = False
    obj.hide_render = True
    screw_turns = max(ANIMATED_MICROSCREW_MIN_TURNS,
                      start_offset * ANIMATED_MICROSCREW_TURNS_PER_MM)
    apply_clockwise_helical_animation(
        obj, rotation, start_location, final_location,
        start_frame, end_frame, screw_turns)

    # Every screw is invisible until its own insertion starts. Without these
    # keys, staggered screws remain frozen at their outside/start positions from
    # frame 1 and look like stale copies left by a previous update.
    reveal_frame = int(start_frame)
    hidden_frame = max(0, reveal_frame - 1)
    for frame, hidden in ((hidden_frame, True), (reveal_frame, False)):
        obj.hide_viewport = bool(hidden)
        obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
    if obj.animation_data and obj.animation_data.action:
        _set_constant_interpolation_for_data_paths(
            obj.animation_data.action, ('hide_viewport',))

    obj['DSG_microscrew_reveal_frame'] = reveal_frame
    obj['DSG_animation_start_frame'] = start_frame
    obj['DSG_animation_end_frame'] = end_frame
    obj['DSG_animation_distance'] = start_offset
    obj['DSG_stop_contact_world'] = list(sleeve_top)
    obj['DSG_tip_final_world'] = list(
        final_location + insertion_axis * MICROSCREW_TEMPLATE_TIP_Z_MM)
    obj['DSG_clockwise_viewed_from_sleeve_entry'] = True
    return obj


def append_microscrew_unscrew_animation(obj, props, record,
                                         start_frame, end_frame):
    """Appends a reverse helical motion that removes an inserted microscrew."""
    if not _valid_obj(obj):
        return False

    axis = _normalized_or_fallback(record.get('axis'), (0.0, 0.0, 1.0))
    sleeve_top = Vector(record.get('sleeve_top', (0.0, 0.0, 0.0)))
    x_hint = record.get('x_hint', (1.0, 0.0, 0.0))
    base_rotation, insertion_axis = _rotation_for_microscrew_axis(axis, x_hint)

    final_location = sleeve_top - insertion_axis * MICROSCREW_TEMPLATE_CONTACT_Z_MM
    start_offset = max(
        2.0,
        float(obj.get(
            'DSG_animation_distance',
            getattr(props, 'microscrew_animation_distance', 15.0))))
    outside_location = final_location + insertion_axis * start_offset
    longitudinal = _normalized_or_fallback(
        outside_location - final_location, insertion_axis)
    turns = max(
        ANIMATED_MICROSCREW_MIN_TURNS,
        float(obj.get(
            'DSG_helical_turns',
            start_offset * ANIMATED_MICROSCREW_TURNS_PER_MM)))

    start_frame = int(start_frame)
    end_frame = max(start_frame + 1, int(end_frame))
    obj.rotation_mode = 'QUATERNION'
    _insert_helical_segment(
        obj, base_rotation, longitudinal,
        final_location, outside_location,
        start_frame, end_frame,
        turns, 0.0, previous_quaternion=None)

    # Once completely removed, the screw disappears from the viewport.
    for frame, hidden in ((end_frame, False), (end_frame + 1, True)):
        obj.hide_viewport = bool(hidden)
        obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))

    if obj.animation_data and obj.animation_data.action:
        _set_fcurve_interpolation_linear(obj.animation_data.action)
        _set_constant_interpolation_for_data_paths(
            obj.animation_data.action, ('hide_viewport',))

    obj['DSG_microscrew_unscrew_start_frame'] = int(start_frame)
    obj['DSG_microscrew_unscrew_end_frame'] = int(end_frame)
    obj['DSG_animation_end_frame'] = int(end_frame + 1)
    obj['DSG_unscrews_after_implants'] = True
    return True



def _matrix_from_flat_16(raw):
    try:
        values = [float(value) for value in raw]
        if len(values) != 16:
            return None
        return Matrix((
            values[0:4], values[4:8], values[8:12], values[12:16],
        ))
    except Exception:
        return None


def _matrix_to_flat_16(matrix):
    matrix = Matrix(matrix)
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def store_guide_home_matrix(guide_obj, force=False, scene=None):
    """Stores the seated world transform once and shares it with replacement guides."""
    if not _valid_obj(guide_obj):
        return None
    scene = scene or getattr(bpy.context, 'scene', None)
    existing = None
    if not force:
        existing = _matrix_from_flat_16(guide_obj.get(GUIDE_HOME_MATRIX_KEY, []))
        if existing is None and scene is not None:
            existing = _matrix_from_flat_16(scene.get(GUIDE_HOME_SCENE_KEY, []))
        # Migration from v6.12.68: use the old stored seated transform rather
        # than the currently evaluated animation frame, which may be retracted.
        if existing is None:
            old_location = guide_obj.get('DSG_final_sequence_final_location')
            old_rotation = guide_obj.get('DSG_final_sequence_final_rotation_quaternion')
            try:
                if old_location is not None and old_rotation is not None:
                    existing = Matrix.LocRotScale(
                        Vector(old_location), Quaternion(old_rotation),
                        guide_obj.matrix_world.to_scale())
            except Exception:
                existing = None
    home = existing if existing is not None else guide_obj.matrix_world.copy()
    flat = _matrix_to_flat_16(home)
    guide_obj[GUIDE_HOME_MATRIX_KEY] = flat
    guide_obj[GUIDE_HOME_ROTATION_MODE_KEY] = str(guide_obj.rotation_mode)
    if scene is not None:
        scene[GUIDE_HOME_SCENE_KEY] = flat
    return home.copy()


def get_guide_home_matrix(guide_obj, scene=None):
    if not _valid_obj(guide_obj):
        return None
    scene = scene or getattr(bpy.context, 'scene', None)
    home = _matrix_from_flat_16(guide_obj.get(GUIDE_HOME_MATRIX_KEY, []))
    if home is None and scene is not None:
        home = _matrix_from_flat_16(scene.get(GUIDE_HOME_SCENE_KEY, []))
    if home is None:
        home = store_guide_home_matrix(guide_obj, force=True, scene=scene)
    return home.copy() if home is not None else None


def restore_guide_home_transform(guide_obj, scene=None, make_visible=True):
    """Returns the guide to its immutable seated position regardless of timeline state."""
    if not _valid_obj(guide_obj):
        return False
    home = get_guide_home_matrix(guide_obj, scene=scene)
    if home is None:
        return False
    try:
        guide_obj.matrix_world = home
        if make_visible:
            guide_obj.hide_viewport = False
            guide_obj.hide_render = False
            guide_obj.hide_set(False)
        try:
            guide_obj.update_tag(refresh={'OBJECT'})
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True
    except Exception:
        return False


def _keyframe_guide_world_matrix(guide_obj, world_matrix, frame):
    """Assigns a world matrix, then keys the resulting local transform safely."""
    guide_obj.rotation_mode = 'QUATERNION'
    guide_obj.matrix_world = Matrix(world_matrix)
    guide_obj.keyframe_insert(data_path='location', frame=int(frame))
    guide_obj.keyframe_insert(data_path='rotation_quaternion', frame=int(frame))
    guide_obj.keyframe_insert(data_path='scale', frame=int(frame))


def clear_final_guide_visibility_animation(guide_obj):
    """Removes only final-sequence keys and restores the immutable seated guide."""
    if not _valid_obj(guide_obj):
        return
    try:
        owns_keys = bool(guide_obj.get('DSG_final_sequence_visibility_animation'))
        if owns_keys and guide_obj.animation_data and guide_obj.animation_data.action:
            action = guide_obj.animation_data.action
            for fcurve in list(action.fcurves):
                if fcurve.data_path in {
                        'hide_viewport', 'hide_render', 'location',
                        'rotation_euler', 'rotation_quaternion', 'scale'}:
                    action.fcurves.remove(fcurve)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    restore_guide_home_transform(guide_obj, make_visible=True)
    try:
        for key in (
                'DSG_final_sequence_visibility_animation',
                'DSG_final_sequence_hide_frame',
                'DSG_final_sequence_seat_start_frame',
                'DSG_final_sequence_seat_end_frame',
                'DSG_final_sequence_return_start_frame',
                'DSG_final_sequence_return_end_frame',
                'DSG_final_sequence_axis_offset_mm',
                'DSG_final_sequence_final_location',
                'DSG_final_sequence_final_rotation_quaternion'):
            if key in guide_obj:
                del guide_obj[key]
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _guide_axis_animation_offset_mm(guide_obj):
    offset = float(ANIMATION_GUIDE_AXIS_OFFSET_MM_FIXED)
    try:
        if _valid_obj(guide_obj):
            diag = float(object_bbox_diagonal(guide_obj))
            offset = max(offset, min(30.0, diag * 0.35))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return float(offset)



def animate_guide_seating_and_return(guide_obj, seat_start_frame, seat_end_frame,
                                     return_start_frame, return_end_frame,
                                     hide_frame):
    """Animates around an immutable seated guide transform.

    Moving the guide in the viewport or pressing Update can never redefine the
    seated position. Stop and Update restore this same world matrix.
    """
    if not _valid_obj(guide_obj):
        return False
    home_matrix = get_guide_home_matrix(guide_obj)
    if home_matrix is None:
        return False
    clear_final_guide_visibility_animation(guide_obj)

    seat_start_frame = max(1, int(seat_start_frame))
    seat_end_frame = max(seat_start_frame + 1, int(seat_end_frame))
    return_start_frame = max(seat_end_frame + 1, int(return_start_frame))
    return_end_frame = max(return_start_frame + 1, int(return_end_frame))
    hide_frame = max(return_end_frame + 1, int(hide_frame))

    insertion_axis = Vector(get_insertion_axis())
    if insertion_axis.length < 1e-8:
        insertion_axis = Vector((0.0, 0.0, 1.0))
    insertion_axis.normalize()
    offset_mm = _guide_axis_animation_offset_mm(guide_obj)

    seated_matrix = home_matrix.copy()
    retracted_matrix = home_matrix.copy()
    retracted_matrix.translation = (
        seated_matrix.translation - insertion_axis * offset_mm)

    visibility_keys = (
        (seat_start_frame, False),
        (return_end_frame, False),
        (hide_frame, True),
    )
    for frame, hidden in visibility_keys:
        guide_obj.hide_viewport = bool(hidden)
        guide_obj.hide_render = bool(hidden)
        guide_obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
        guide_obj.keyframe_insert(data_path='hide_render', frame=int(frame))

    _keyframe_guide_world_matrix(guide_obj, retracted_matrix, seat_start_frame)
    _keyframe_guide_world_matrix(guide_obj, seated_matrix, seat_end_frame)
    _keyframe_guide_world_matrix(guide_obj, seated_matrix, return_start_frame)
    _keyframe_guide_world_matrix(guide_obj, retracted_matrix, return_end_frame)

    try:
        if guide_obj.animation_data and guide_obj.animation_data.action:
            _set_fcurve_interpolation_linear(guide_obj.animation_data.action)
            _set_constant_interpolation_for_data_paths(
                guide_obj.animation_data.action,
                ('hide_viewport', 'hide_render'))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    guide_obj['DSG_final_sequence_visibility_animation'] = True
    guide_obj['DSG_final_sequence_hide_frame'] = int(hide_frame)
    guide_obj['DSG_final_sequence_seat_start_frame'] = int(seat_start_frame)
    guide_obj['DSG_final_sequence_seat_end_frame'] = int(seat_end_frame)
    guide_obj['DSG_final_sequence_return_start_frame'] = int(return_start_frame)
    guide_obj['DSG_final_sequence_return_end_frame'] = int(return_end_frame)
    guide_obj['DSG_final_sequence_axis_offset_mm'] = float(offset_mm)

    # Building or updating the sequence must leave the guide seated on the model.
    restore_guide_home_transform(guide_obj, make_visible=True)
    return True


def make_frustum_mesh(name, radius_inner, radius_outer, depth, verts=47):
    """Crea un tronco de cono cerrado orientado sobre Z local.

    ``radius_inner`` corresponde al extremo -Z que se introduce en el sleeve y
    ``radius_outer`` al extremo +Z que conecta con el tubo externo. Usar radios
    distintos y un número de segmentos no múltiplo del sleeve evita círculos y
    edges coincidentes durante Boolean EXACT.
    """
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=max(17, int(verts)),
        radius1=max(0.03, float(radius_inner)),
        radius2=max(0.04, float(radius_outer)),
        depth=max(0.05, float(depth)),
    )
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh



def make_annular_cylinder_mesh(name, inner_radius, outer_radius, depth, segments=32,
                               lateral_opening=False, opening_width_mm=0.0,
                               opening_center_angle=0.0, opening_half_angle=None):
    """Create a closed annular sleeve, optionally with a manifold lateral opening.

    The opening is generated directly by omitting an angular sector and closing
    both cut faces. No Boolean is required, so preview and rebuild remain fast.
    ``opening_width_mm`` is the chord width measured at the outer sleeve radius.
    """
    seg = max(12, min(96, int(segments)))
    inner = max(0.01, float(inner_radius))
    outer = max(inner + 0.01, float(outer_radius))
    half = max(0.01, float(depth) * 0.5)
    lateral_opening = bool(lateral_opening)

    if not lateral_opening:
        verts = []
        for z, radius in ((-half, outer), (half, outer), (-half, inner), (half, inner)):
            for i in range(seg):
                angle = 2.0 * math.pi * i / seg
                verts.append((radius * math.cos(angle), radius * math.sin(angle), z))
        ob, ot, ib, it = 0, seg, seg * 2, seg * 3
        faces = []
        for i in range(seg):
            j = (i + 1) % seg
            faces.append((ob + i, ob + j, ot + j, ot + i))
            faces.append((ib + j, ib + i, it + i, it + j))
            faces.append((ot + i, ot + j, it + j, it + i))
            faces.append((ob + j, ob + i, ib + i, ib + j))
    else:
        # Keep at least 210° of circumferential guidance. The width is clamped
        # to avoid producing two weak pillars instead of a sleeve.
        if opening_half_angle is None:
            width = max(0.4, float(opening_width_mm))
            ratio = min(0.94, width / max(2.0 * outer, 1e-6))
            half_open = max(math.radians(6.0), min(math.radians(75.0), math.asin(ratio)))
        else:
            half_open = max(
                math.radians(6.0),
                min(math.radians(75.0), float(opening_half_angle)))
        retained_arc = 2.0 * math.pi - 2.0 * half_open
        retained_segments = max(8, int(round(seg * retained_arc / (2.0 * math.pi))))
        angles = [
            float(opening_center_angle) + half_open + retained_arc * i / retained_segments
            for i in range(retained_segments + 1)
        ]
        ring_count = len(angles)
        verts = []
        for z, radius in ((-half, outer), (half, outer), (-half, inner), (half, inner)):
            for angle in angles:
                verts.append((radius * math.cos(angle), radius * math.sin(angle), z))
        ob, ot, ib, it = 0, ring_count, ring_count * 2, ring_count * 3
        faces = []
        for i in range(ring_count - 1):
            j = i + 1
            faces.append((ob + i, ob + j, ot + j, ot + i))
            faces.append((ib + j, ib + i, it + i, it + j))
            faces.append((ot + i, ot + j, it + j, it + i))
            faces.append((ob + j, ob + i, ib + i, ib + j))
        # Close the two radial cut faces so the U-shaped sleeve is manifold.
        for i in (0, ring_count - 1):
            faces.append((ob + i, ot + i, it + i, ib + i))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    return mesh


def _current_view_forward_world(context):
    """Return the current viewport forward vector, or the insertion axis."""
    try:
        area = getattr(context, 'area', None)
        space = getattr(getattr(area, 'spaces', None), 'active', None)
        rv3d = getattr(space, 'region_3d', None)
        vm = rv3d.view_matrix
        vec = Vector((-vm[2][0], -vm[2][1], -vm[2][2]))
        if vec.length > 1e-8:
            return vec.normalized()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        return get_insertion_axis().normalized()
    except Exception:
        return Vector((0.0, 0.0, 1.0))


def _sleeve_lateral_opening_angle(context, sleeve_matrix, world_direction=None):
    """Angle of the lateral access facing the clinician's chosen view."""
    toward_user = Vector(world_direction) if world_direction is not None else -_current_view_forward_world(context)
    axis = (sleeve_matrix.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    projected = toward_user - axis * toward_user.dot(axis)
    if projected.length < 1e-8:
        projected = sleeve_matrix.to_3x3() @ Vector((1.0, 0.0, 0.0))
    projected.normalize()
    local = sleeve_matrix.to_3x3().inverted() @ projected
    return math.atan2(local.y, local.x)


def _normalize_angle_2pi(angle):
    return float(angle) % (2.0 * math.pi)


def _irrigation_entry_implant_name(entry):
    if not isinstance(entry, dict):
        return ''
    name = str(entry.get('implant_name') or '')
    if name:
        return name
    implant = entry.get('implant')
    return _safe_object_name(implant) or ''


def _sleeve_window_irrigation_signature(props, implants=None):
    """Stable signature of the geometry that can constrain a lateral window."""
    implant_names = {
        _safe_object_name(item) for item in (implants or get_all_implant_objects(props))
        if is_valid_implant_obj(item)
    }
    payload = []
    relevant_keys = (
        'irr_sleeve_channel_mode', 'irr_inner_diameter',
        'irr_wall_thickness', 'irr_funnel_outer_diameter',
        'irr_bevel_resolution', 'irr_direct_sleeve_lumen_overlap',
    )
    for entry in load_irrigation_path_entries(props):
        name = _irrigation_entry_implant_name(entry)
        if implant_names and name not in implant_names:
            continue
        params = dict(entry.get('parameters') or {})
        relevant = {}
        for key in relevant_keys:
            value = params.get(key, getattr(props, key, None))
            if isinstance(value, float):
                value = round(float(value), 5)
            relevant[key] = value
        points = [
            [round(float(point.x), 4), round(float(point.y), 4), round(float(point.z), 4)]
            for point in entry.get('points', [])
        ]
        payload.append({
            'implant': name,
            'index': int(entry.get('index', len(payload))),
            'link': bool(entry.get('link', False)),
            'points': points,
            'parameters': relevant,
        })
    payload.sort(key=lambda item: (item['implant'], item['index'], item['link']))
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _window_mark_occupied_bins(occupied, angle, half_angle):
    count = len(occupied)
    if count <= 0:
        return
    step = (2.0 * math.pi) / count
    center = int(round(_normalize_angle_2pi(angle) / step)) % count
    radius = max(0, int(math.ceil(max(0.0, float(half_angle)) / step)))
    for offset in range(-radius, radius + 1):
        occupied[(center + offset) % count] = True


def _window_largest_free_run(occupied):
    """Return start index and length of the largest circular free interval."""
    count = len(occupied)
    if count <= 0:
        return None
    if not any(occupied):
        return 0, count
    if all(occupied):
        return None
    best_start = 0
    best_len = 0
    current_start = 0
    current_len = 0
    doubled = occupied + occupied
    for index, blocked in enumerate(doubled):
        if not blocked:
            if current_len == 0:
                current_start = index
            current_len += 1
            if current_len > count:
                current_start += 1
                current_len = count
            if current_len > best_len and current_start < count:
                best_start = current_start
                best_len = current_len
        else:
            current_len = 0
    return best_start % count, min(best_len, count)


def _window_point_angle_and_radius(sleeve_matrix, point_world):
    try:
        local = sleeve_matrix.inverted_safe() @ Vector(point_world)
    except Exception:
        local = sleeve_matrix.inverted() @ Vector(point_world)
    radial = math.hypot(float(local.x), float(local.y))
    return math.atan2(float(local.y), float(local.x)), radial


def _window_mark_world_point(occupied, sleeve_matrix, point_world,
                             protected_radius_mm, max_half_deg=72.0):
    angle, radial = _window_point_angle_and_radius(sleeve_matrix, point_world)
    if radial <= 1.0e-5:
        return
    ratio = min(0.98, max(0.0, float(protected_radius_mm)) / radial)
    half_angle = min(math.radians(float(max_half_deg)), math.asin(ratio))
    _window_mark_occupied_bins(occupied, angle, half_angle)


def _sleeve_window_entries_for_implant(props, implant_obj):
    name = _safe_object_name(implant_obj) or ''
    return [
        entry for entry in load_irrigation_path_entries(props)
        if _irrigation_entry_implant_name(entry) == name
    ]


def _resolve_lateral_window_for_implant(context, props, implant_obj,
                                         sleeve_matrix, outer_radius):
    """Resolve a safe window from actual irrigation geometry or the saved view.

    With confirmed irrigation, the whole occupied C/direct geometry is sampled
    and the opening is centred in the largest remaining angular sector. Without
    irrigation, the user's captured viewport direction remains the reference.
    """
    outer_radius = max(0.10, float(outer_radius))
    requested_width = max(0.40, float(getattr(
        props, 'sleeve_lateral_opening_width', outer_radius)))
    requested_ratio = min(0.94, requested_width / max(2.0 * outer_radius, 1.0e-6))
    requested_half = max(
        math.radians(6.0),
        min(math.radians(75.0), math.asin(requested_ratio)))
    rotation = math.radians(float(getattr(
        props, 'sleeve_lateral_opening_rotation', 0.0)))
    entries = _sleeve_window_entries_for_implant(props, implant_obj)

    if not entries:
        direction = Vector(getattr(
            props, 'sleeve_lateral_opening_direction', (1.0, 0.0, 0.0)))
        center = _sleeve_lateral_opening_angle(
            context, sleeve_matrix, direction) + rotation
        return {
            'valid': True,
            'mode': 'VIEW',
            'center_angle': _normalize_angle_2pi(center),
            'half_angle': requested_half,
            'requested_width_mm': requested_width,
            'actual_width_mm': 2.0 * outer_radius * math.sin(requested_half),
            'free_span_rad': 2.0 * math.pi,
            'manual_rotation_requested_deg': math.degrees(rotation),
            'manual_rotation_applied_deg': math.degrees(rotation),
            'width_reduced': False,
            'message': 'view orientation',
        }

    bins = max(180, int(SLEEVE_WINDOW_ANGULAR_BINS))
    occupied = [False] * bins
    clearance = float(SLEEVE_WINDOW_IRRIGATION_CLEARANCE_MM_FIXED)
    diana_radius = float(SLEEVE_WINDOW_DEFAULT_CROSSCHECK_RADIUS_MM)
    marked_samples = 0

    for entry in entries:
        points = entry.get('points', [])
        if len(points) < 2:
            continue
        params = dict(entry.get('parameters') or {})
        entry_props = irrigation_props_overlay(props, params)
        mode = str(getattr(
            entry_props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
        if mode == 'DIRECT':
            port = get_sleeve_lateral_port_geometry(
                points[1], entry_props, implant_obj)
            candidates = []
            if port:
                for key in ('surface_point', 'internal_overlap_point', 'axis_entry'):
                    if key in port:
                        candidates.append(Vector(port[key]))
            if not candidates:
                candidates = [Vector(points[1])]
            lumen_radius = max(
                0.20,
                float(getattr(entry_props, 'irr_funnel_outer_diameter', 1.0)) * 0.5)
            protected = max(diana_radius, lumen_radius) + clearance
            for point in candidates:
                _window_mark_world_point(
                    occupied, sleeve_matrix, point, protected)
                marked_samples += 1
            continue

        ring = get_irrigation_internal_ring_geometry(
            points[1], entry_props, implant_obj)
        if not ring:
            _window_mark_world_point(
                occupied, sleeve_matrix, points[1], diana_radius + clearance)
            marked_samples += 1
            continue

        branch_radius = max(0.14, float(ring.get('branch_tube_r', 0.25)))
        arc_protected = branch_radius + clearance * 0.65
        arc_points = list(ring.get('upper_arc', [])) + list(ring.get('lower_arc', []))
        for point in arc_points:
            _window_mark_world_point(
                occupied, sleeve_matrix, point, arc_protected, max_half_deg=45.0)
            marked_samples += 1
        for key in ('split_point', 'upper_lumen_point', 'lower_lumen_point'):
            point = ring.get(key)
            if point is not None:
                _window_mark_world_point(
                    occupied, sleeve_matrix, point, diana_radius + clearance)
                marked_samples += 1

    if marked_samples <= 0:
        direction = Vector(getattr(
            props, 'sleeve_lateral_opening_direction', (1.0, 0.0, 0.0)))
        center = _sleeve_lateral_opening_angle(
            context, sleeve_matrix, direction) + rotation
        return {
            'valid': True,
            'mode': 'VIEW_FALLBACK',
            'center_angle': _normalize_angle_2pi(center),
            'half_angle': requested_half,
            'requested_width_mm': requested_width,
            'actual_width_mm': 2.0 * outer_radius * math.sin(requested_half),
            'free_span_rad': 2.0 * math.pi,
            'manual_rotation_requested_deg': math.degrees(rotation),
            'manual_rotation_applied_deg': math.degrees(rotation),
            'width_reduced': False,
            'message': 'irrigation geometry unavailable; view fallback',
        }

    free = _window_largest_free_run(occupied)
    if free is None:
        return {
            'valid': False,
            'mode': 'IRRIGATION_AUTO',
            'message': 'no free angular sector remains around the sleeve',
        }
    start_index, free_count = free
    step = (2.0 * math.pi) / bins
    free_start = start_index * step
    free_span = free_count * step
    minimum_free = math.radians(float(SLEEVE_WINDOW_MIN_FREE_ARC_DEG_FIXED))
    if free_span < minimum_free:
        return {
            'valid': False,
            'mode': 'IRRIGATION_AUTO',
            'free_span_rad': free_span,
            'message': 'the largest free sector is too narrow for a lateral opening',
        }

    automatic_center = free_start + free_span * 0.5
    side_margin = max(
        math.radians(4.0),
        float(SLEEVE_WINDOW_MIN_SIDE_WALL_MM_FIXED) / outer_radius)
    max_half = max(0.0, free_span * 0.5 - side_margin)
    retained_limit = math.radians(
        (360.0 - float(SLEEVE_WINDOW_MIN_RETAINED_ARC_DEG_FIXED)) * 0.5)
    max_half = min(max_half, retained_limit, math.radians(75.0))
    if max_half < math.radians(6.0):
        return {
            'valid': False,
            'mode': 'IRRIGATION_AUTO',
            'free_span_rad': free_span,
            'message': 'insufficient side wall remains beside the irrigation geometry',
        }

    half_angle = min(requested_half, max_half)
    allowed_offset = max(0.0, free_span * 0.5 - half_angle - side_margin)
    applied_rotation = max(-allowed_offset, min(allowed_offset, rotation))
    center = automatic_center + applied_rotation
    return {
        'valid': True,
        'mode': 'IRRIGATION_AUTO',
        'center_angle': _normalize_angle_2pi(center),
        'automatic_center_angle': _normalize_angle_2pi(automatic_center),
        'half_angle': half_angle,
        'requested_width_mm': requested_width,
        'actual_width_mm': 2.0 * outer_radius * math.sin(half_angle),
        'free_span_rad': free_span,
        'manual_rotation_requested_deg': math.degrees(rotation),
        'manual_rotation_applied_deg': math.degrees(applied_rotation),
        'width_reduced': half_angle + 1.0e-8 < requested_half,
        'rotation_clamped': abs(applied_rotation - rotation) > 1.0e-8,
        'message': 'largest free sector opposite actual irrigation geometry',
    }


def _sleeve_window_requires_irrigation_rebuild(props, guide):
    if not bool(getattr(props, 'sleeve_lateral_opening', False)):
        return False
    if not _valid_obj(guide):
        return False
    entries = load_irrigation_path_entries(props)
    if not entries:
        return False
    current = _sleeve_window_irrigation_signature(props)
    stored = str(guide.get('DSG_sleeve_window_irrigation_signature', '') or '')
    return current != stored


def build_combined_mesh_object_world(context, objects, name):
    """Combina copias geométricas en una sola malla sin ``bpy.ops.object.join``.

    Los vértices se transforman directamente a coordenadas World. Esto evita
    duplicar objetos, cambiar selección, invalidar StructRNA y ejecutar el
    operador Join antes del Boolean de sleeves.
    """
    valid = [obj for obj in objects if _valid_obj(obj) and obj.type == 'MESH']
    if not valid:
        return None

    verts = []
    faces = []
    offset = 0
    try:
        for obj in valid:
            matrix = obj.matrix_world
            mesh = obj.data
            verts.extend(tuple(matrix @ vertex.co) for vertex in mesh.vertices)
            for poly in mesh.polygons:
                faces.append(tuple(offset + int(index) for index in poly.vertices))
            offset += len(mesh.vertices)

        mesh_out = bpy.data.meshes.new(name + '_Mesh')
        mesh_out.from_pydata(verts, [], faces)
        mesh_out.validate(clean_customdata=False)
        mesh_out.update(calc_edges=True)
        obj_out = bpy.data.objects.new(name, mesh_out)
        obj_out.matrix_world = Matrix.Identity(4)
        link_object(context, obj_out)
        register_dsg_object(obj_out, ROLE_CUTTER, name, {
            'DSG_cut_type': 'combined_sleeves_fast',
            'DSG_analytic_solid': True,
        })
        return obj_out
    except Exception as exc:
        print(f'[DSG] Could not build the fast combined cutter: {exc}')
        try:
            if 'obj_out' in locals() and _valid_obj(obj_out):
                safe_remove_object(obj_out)
            elif 'mesh_out' in locals() and mesh_out.users == 0:
                bpy.data.meshes.remove(mesh_out)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return None


def store_analytic_solid_preflight(obj, key, message='Mesh closed by construction'):
    """Marca una primitiva generada por DSG como solid sin recorrer sus edges."""
    if not _valid_obj(obj):
        return None
    data = {
        'status': 'green',
        'checked': True,
        'solid': True,
        'repaired': False,
        'repair_methods': [],
        'bad_edges': 0,
        'degenerate_faces': 0,
        'polygons': len(obj.data.polygons) if obj.data else 0,
        'solver': 'EXACT',
        'message': message,
        'analytic': True,
    }
    return store_boolean_preflight(obj, key, data)


def make_uv_sphere_mesh(name, radius, u_segments=24, v_segments=12):
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=u_segments, v_segments=v_segments, radius=radius)
    except TypeError:
        bmesh.ops.create_uvsphere(bm, u_segments=u_segments, v_segments=v_segments, diameter=radius * 2.0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def choose_raycast_target(props):
    combined = bpy.data.objects.get(COMBINED_NAME)
    if combined:
        return combined
    blockout = bpy.data.objects.get(BLOCKOUT_NAME)
    if blockout:
        return blockout
    return props.model_obj


def _transfer_bm(bm_src, bm_dst):
    vmap = {}
    for v in bm_src.verts:
        vmap[v] = bm_dst.verts.new(v.co.copy())
    for f in bm_src.faces:
        try:
            bm_dst.faces.new([vmap[v] for v in f.verts])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _mesh_nonmanifold_info_from_mesh(mesh, max_polygons=120000):
    """Chequeo ligero de no-manifold sin entrar en Edit Mode.

    Cuenta cuántas caras usan cada arista. En una malla cerrada sana, una arista
    se usa exactamente por 2 caras. Si se usa por 1, 0 o más de 2, la malla puede
    dar problemas a las operaciones booleanas. Devuelve None si la malla es demasiado grande
    para no frenar el flujo.
    """
    if mesh is None:
        return None
    try:
        poly_count = len(mesh.polygons)
        if poly_count == 0 or poly_count > int(max_polygons):
            return None

        edge_use = {}
        degenerate_faces = 0
        for poly in mesh.polygons:
            verts = list(poly.vertices)
            n = len(verts)
            if n < 3:
                degenerate_faces += 1
                continue
            for i in range(n):
                a = int(verts[i])
                b = int(verts[(i + 1) % n])
                if a == b:
                    degenerate_faces += 1
                    continue
                key = (a, b) if a < b else (b, a)
                edge_use[key] = edge_use.get(key, 0) + 1

        bad_edges = sum(1 for count in edge_use.values() if count != 2)
        return {
            'checked': True,
            'nonmanifold': bool(bad_edges or degenerate_faces),
            'bad_edges': bad_edges,
            'degenerate_faces': degenerate_faces,
            'polygons': poly_count,
        }
    except Exception:
        return None


def get_mesh_solid_report(obj, max_polygons=350000):
    """Verifica si una malla se comporta como sólido cerrado para booleanos.

    Es el equivalente ligero al chequeo Solid: todas las edges deberían tener
    exactamente dos caras y no debería haber caras degeneradas. Si la malla es
    enorme, devuelve checked=False para no bloquear Blender; en ese caso el
    flujo seguirá con solver robusto.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return {
            'checked': False,
            'solid': False,
            'reason': 'invalid object',
            'bad_edges': None,
            'degenerate_faces': None,
            'polygons': 0,
        }

    info = _mesh_nonmanifold_info_from_mesh(obj.data, max_polygons=max_polygons)
    if info is None:
        return {
            'checked': False,
            'solid': False,
            'reason': 'mesh too large for a lightweight check',
            'bad_edges': None,
            'degenerate_faces': None,
            'polygons': len(obj.data.polygons) if obj.data else 0,
        }

    solid = not bool(info.get('nonmanifold'))
    return {
        'checked': True,
        'solid': solid,
        'reason': 'sólida' if solid else 'no manifold',
        'bad_edges': int(info.get('bad_edges', 0)),
        'degenerate_faces': int(info.get('degenerate_faces', 0)),
        'polygons': int(info.get('polygons', 0)),
    }


def get_mesh_solid_report_scalable(obj, max_edges=5000000):
    """Verificación manifold para resultados grandes, ejecutada solo bajo demanda.

    El chequeo ligero basado en polígonos se omite cuando la malla supera su
    límite para no bloquear el panel. En el corte final usamos BMesh una sola vez:
    Blender construye la conectividad en código nativo y Python recorre las
    edges ya enlazadas. Si la malla también supera este límite de seguridad,
    devuelve checked=False sin considerar la geometría defectuosa.
    """
    report = get_mesh_solid_report(obj, max_polygons=900000)
    if report.get('checked'):
        report['method'] = 'lightweight'
        return report

    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return report

    mesh = obj.data
    try:
        edge_count = len(mesh.edges)
        poly_count = len(mesh.polygons)
    except Exception:
        return report

    if edge_count > int(max_edges):
        return {
            'checked': False,
            'solid': False,
            'reason': f'mesh too large for scalable audit ({edge_count} edges)',
            'bad_edges': None,
            'degenerate_faces': None,
            'polygons': poly_count,
            'edges': edge_count,
            'method': 'size_limit',
        }

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        bad_edges = 0
        for edge in bm.edges:
            if len(edge.link_faces) != 2:
                bad_edges += 1

        degenerate_faces = 0
        for face in bm.faces:
            if len(face.verts) < 3:
                degenerate_faces += 1
                continue
            try:
                if face.calc_area() <= 1e-14:
                    degenerate_faces += 1
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        solid = not bool(bad_edges or degenerate_faces)
        return {
            'checked': True,
            'solid': solid,
            'reason': 'sólida' if solid else 'no manifold',
            'bad_edges': int(bad_edges),
            'degenerate_faces': int(degenerate_faces),
            'polygons': int(poly_count),
            'edges': int(edge_count),
            'method': 'bmesh_scalable',
        }
    except (MemoryError, ReferenceError, RuntimeError) as exc:
        return {
            'checked': False,
            'solid': False,
            'reason': f'scalable audit unavailable: {exc}',
            'bad_edges': None,
            'degenerate_faces': None,
            'polygons': poly_count,
            'edges': edge_count,
            'method': 'audit_failed',
        }
    except Exception as exc:
        return {
            'checked': False,
            'solid': False,
            'reason': f'scalable audit unavailable: {exc}',
            'bad_edges': None,
            'degenerate_faces': None,
            'polygons': poly_count,
            'edges': edge_count,
            'method': 'audit_failed',
        }
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)



def _closed_manifold_geometry_signature(obj):
    """CRC signature tying a successful audit to the complete mesh geometry.

    ``foreach_get`` copies coordinates in Blender's C layer, so checking whether
    the certification is still current remains much cheaper than rebuilding
    BMesh connectivity while still detecting edits anywhere on the model.
    """
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return ''
    mesh = obj.data
    try:
        vertex_count = int(len(mesh.vertices))
        coords = np.empty(vertex_count * 3, dtype=np.float32)
        if vertex_count:
            mesh.vertices.foreach_get('co', coords)
        crc = int(zlib.crc32(coords.tobytes()) & 0xFFFFFFFF)
        values = (
            vertex_count,
            int(len(mesh.edges)),
            int(len(mesh.polygons)),
            crc,
        )
        return '|'.join(str(value) for value in values)
    except Exception:
        return ''


