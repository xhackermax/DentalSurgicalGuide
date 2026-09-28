# ─────────────────────────────────────────────────────────────
# Frangible irrigation walls and perforation marks (DSG 9.7.2)
#
# Before 9.7.2 the "seal" was a Ø1.08 mm disk placed 0.03–0.13 mm INSIDE the
# drill bore, in front of the radial port. It never touched the sleeve wall
# (it exported as a loose island inside the drill path), it did not close the
# two C-mode outlets at all, and its Ø2.5 mm target ring fell outside the disk.
#
# Now, for every outlet through which water enters the drill bore (1 in DIRECT
# mode, 2 in C mode):
#   * a membrane (0.10 mm centre / 0.25 mm rim) fills the outlet channel
#     0.30 mm behind the bore surface and overlaps the wall so the union seals;
#   * a 0.20 mm conical countersink is cut around the outlet on the bore wall
#     (material removed only: the drill path is never obstructed);
#   * the opening order digit is engraved on the guide exterior next to the
#     sleeve.
# Pure geometry: ``frangible_seal``. This fragment adapts it to Blender.
# ─────────────────────────────────────────────────────────────
from . import frangible_seal as _fseal

FRANGIBLE_PREVIEW_PREFIX = 'DSG_FrangiblePreview_'
FRANGIBLE_MARK_CUTTER_PREFIX = 'DSG_FrangibleMarkCut_'
FRANGIBLE_MARKER_SHAPE = 'COUNTERSINK_POCKET_ORDER_DIGIT'


def frangible_seal_design():
    return _fseal.SealDesign(
        membrane_center_mm=float(IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED),
        membrane_rim_mm=float(IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED),
        label_size_mm=2.4,   # 5×7 glyph cells of ~0.34 mm: printable
    )


def frangible_outlets(props, implant_obj):
    """Where water enters the drill bore for this sleeve.

    Returns ``([{'point', 'normal', 'axis', 'lumen_r', 'mode'}], error)``;
    ``point`` lies on the bore surface and ``normal`` points into the wall.
    """
    if not is_valid_implant_obj(implant_obj):
        return [], 'invalid implant'
    entry = _irrigation_entry_for_implant(props, implant_obj)
    if not entry:
        return [], 'irrigation path not found'
    points = entry.get('points') or []
    if len(points) < 2:
        return [], 'irrigation path has no sleeve port'
    entry_props, _parameters = _irrigation_entry_effective_props(props, entry)
    anchor = Vector(points[1])

    ring = get_irrigation_internal_ring_geometry(anchor, entry_props, implant_obj)
    if ring:
        center = Vector(ring['center'])
        tangent = Vector(ring['tangent']).normalized()
        axis = Vector(ring['axis']).normalized()
        inner_r = float(ring['inner_r'])
        branch_r = max(0.14, float(ring['branch_tube_r']))
        # C cutter = tube(branch_r) + outlet sphere(1.08·branch_r) + 0.045 mm margin.
        hole_r = branch_r * 1.08 + 0.045
        return [{
            'point': center + tangent * (sign * inner_r),
            'normal': tangent * sign,
            'axis': axis,
            'lumen_r': hole_r,
            'mark_r': branch_r,
            'mode': 'C',
        } for sign in (1.0, -1.0)], ''

    port = get_sleeve_lateral_port_geometry(anchor, entry_props, implant_obj)
    if not port:
        return [], 'could not resolve lateral sleeve port'
    radial = Vector(port['radial']).normalized()
    axis = Vector(port['axis']).normalized()
    center = Vector(port['center'])
    overlap = Vector(port['internal_overlap_point'])
    rel = overlap - center
    axial = axis * rel.dot(axis)
    point = center + axial + radial * float(port['inner_r'])
    lumen_r = max(0.15, float(getattr(entry_props, 'irr_funnel_outer_diameter', 1.0)) * 0.5)
    return [{
        'point': point, 'normal': radial, 'axis': axis,
        'lumen_r': lumen_r + 0.045, 'mark_r': lumen_r, 'mode': 'DIRECT',
    }], ''


def _outlet_matrix(outlet):
    z_axis = Vector(outlet['normal']).normalized()
    x_axis = Vector(outlet['axis']).cross(z_axis)
    if x_axis.length < 1e-8:
        x_axis = Vector((1.0, 0.0, 0.0)).cross(z_axis)
    x_axis.normalize()
    y_axis = z_axis.cross(x_axis).normalized()
    mx = Matrix((x_axis, y_axis, z_axis)).transposed().to_4x4()
    mx.translation = Vector(outlet['point'])
    return mx


def _revolved_parts_object(context, name, parts):
    """One mesh object from several (profile, matrix) solids of revolution."""
    verts, faces = [], []
    for profile, matrix in parts:
        v_local, f_local = _fseal.revolve(profile, segments=int(IRRIGATION_FRANGIBLE_SEAL_SEGMENTS_FIXED))
        base = len(verts)
        verts.extend(tuple(matrix @ Vector(v)) for v in v_local)
        faces.extend(tuple(base + i for i in face) for face in f_local)
    safe_remove_by_name(name)
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    return obj


def build_frangible_irrigation_seal_object(context, props, implant_obj, name=None):
    """Membranes for every outlet of this sleeve, as one object to union."""
    outlets, error = frangible_outlets(props, implant_obj)
    if not outlets:
        return None, error
    design = frangible_seal_design()
    problems = [p for o in outlets for p in design.validate_outlet(float(o['mark_r']))]
    if problems:
        return None, '; '.join(problems)
    obj_name = name or (IRRIGATION_FRANGIBLE_SEAL_PREFIX + implant_obj.name)
    seal_obj = _revolved_parts_object(context, obj_name, [
        (_fseal.membrane_profile(float(o['lumen_r']), design), _outlet_matrix(o)) for o in outlets])
    seal_obj.display_type = 'WIRE'
    seal_obj.show_in_front = True
    order = int(implant_obj.get('DSG_irrigation_open_order', 0) or 0)
    try:
        seal_obj['DSG_frangible_irrigation_seal'] = True
        seal_obj['DSG_implant_name'] = implant_obj.name
        seal_obj['DSG_seal_mode'] = 'OUTLET_CHANNEL_FRANGIBLE_MEMBRANE'
        seal_obj['DSG_seal_outlet_mode'] = str(outlets[0]['mode'])
        seal_obj['DSG_seal_outlet_count'] = len(outlets)
        seal_obj['DSG_axial_sleeve_lumen_preserved'] = True
        seal_obj['DSG_seal_outlets_world'] = json.dumps([
            {'point': [float(v) for v in o['point']], 'normal': [float(v) for v in o['normal']],
             'lumen_r_mm': float(o['lumen_r'])} for o in outlets])
        # Backwards-compatible keys (first outlet).
        seal_obj['DSG_lateral_port_center_world'] = json.dumps([float(v) for v in outlets[0]['point']])
        seal_obj['DSG_lateral_port_radial_world'] = json.dumps([float(v) for v in outlets[0]['normal']])
        seal_obj['DSG_seal_center_thickness_mm'] = float(design.membrane_center_mm)
        seal_obj['DSG_seal_rim_thickness_mm'] = float(design.membrane_rim_mm)
        seal_obj['DSG_seal_depth_from_bore_mm'] = float(design.pocket_depth_mm)
        seal_obj['DSG_internal_marker_shape'] = FRANGIBLE_MARKER_SHAPE
        seal_obj['DSG_countersink_depth_mm'] = float(design.countersink_depth_mm)
        seal_obj['DSG_irrigation_open_order'] = order
        seal_obj['DSG_export_temporary'] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    register_dsg_object(seal_obj, ROLE_IRRIGATION, obj_name)
    return seal_obj, 'ok'


# ── Order label on the guide exterior ───────────────────────────────────────
def _occlusal_direction(props, implant_obj):
    center = get_sleeve_center_world(props, implant_obj)
    away = center - implant_obj.matrix_world.translation
    axis = get_sleeve_axis_world(props, implant_obj)
    if away.length < 1e-6:
        return axis
    return axis if axis.dot(away) >= 0.0 else -axis


def find_order_label_site(props, implant_obj, guide_bvh, avoid_directions=()):
    """A flat, thick-enough, occlusal-facing spot next to the sleeve (or None)."""
    design = frangible_seal_design()
    center = get_sleeve_center_world(props, implant_obj)
    occ = _occlusal_direction(props, implant_obj).normalized()
    _inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    half_h = max(0.1, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    u, v, _a = build_axis_basis(occ)
    half = design.label_size_mm * 0.5
    offset = outer_r + half + 1.0
    candidates = []
    for k in range(16):
        ang = 2.0 * math.pi * k / 16.0
        direction = (u * math.cos(ang) + v * math.sin(ang)).normalized()
        penalty = max([direction.dot(Vector(a).normalized()) for a in avoid_directions] or [-1.0])
        candidates.append((penalty, k, direction))
    for _penalty, _k, direction in sorted(candidates):
        origin = center + direction * offset + occ * (half_h + 6.0)
        loc, normal, _index, _dist = guide_bvh.ray_cast(origin, -occ, 20.0)
        if loc is None or normal is None:
            continue
        normal = Vector(normal).normalized()
        if normal.dot(occ) < 0.5:
            continue
        # Flat enough under the whole glyph?
        tx = direction.cross(normal).normalized()
        ty = normal.cross(tx).normalized()
        flat = True
        for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half)):
            probe = loc + tx * dx + ty * dy + normal * 2.0
            hit = guide_bvh.ray_cast(probe, -normal, 4.0)
            if hit[0] is None or abs((hit[0] - loc).dot(normal)) > 0.15:
                flat = False
                break
        if not flat:
            continue
        # Enough material behind the engraving?
        back = guide_bvh.ray_cast(loc - normal * 0.02, -normal, 10.0)
        if back[0] is None or (back[0] - loc).length < design.label_depth_mm + 0.8:
            continue
        return {'location': loc, 'normal': normal, 'x_axis': tx}
    return None


def _guide_world_bvh(guide_obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = guide_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mw = guide_obj.matrix_world
        verts = [mw @ vert.co for vert in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
    finally:
        eval_obj.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def build_frangible_mark_cutters(context, props, implant_obj, guide_obj, name_prefix=None):
    """Countersinks (one per outlet) + engraved order digit. Returns (cutters, notes)."""
    outlets, error = frangible_outlets(props, implant_obj)
    if not outlets:
        return [], [error]
    design = frangible_seal_design()
    prefix = name_prefix or (FRANGIBLE_MARK_CUTTER_PREFIX + implant_obj.name)
    cutters, notes = [], []
    sink = _revolved_parts_object(context, prefix + '_Countersink', [
        (_fseal.countersink_profile(float(o['mark_r']), design), _outlet_matrix(o)) for o in outlets])
    sink.display_type = 'WIRE'
    sink['DSG_frangible_mark'] = 'COUNTERSINK'
    cutters.append(sink)

    order = int(implant_obj.get('DSG_irrigation_open_order', 0) or 0)
    if order <= 0:
        notes.append('no opening order assigned: digit not engraved')
        return cutters, notes
    if not _valid_obj(guide_obj):
        notes.append('guide not available: digit not engraved')
        return cutters, notes
    site = find_order_label_site(
        props, implant_obj, _guide_world_bvh(guide_obj),
        avoid_directions=[Vector(o['normal']) for o in outlets])
    if site is None:
        notes.append(f'{implant_obj.name}: no flat area for the order digit')
        return cutters, notes
    depth = design.label_depth_mm
    matrix = build_engrave_orientation_matrix(
        site['location'] + site['normal'] * ((0.2 - depth) * 0.5), site['normal'], site['x_axis'])
    digit = create_engrave_text_mesh_object(
        context, prefix + '_OrderDigit', str(order), design.label_size_mm, depth + 0.2, matrix)
    if digit is None or not _voxel_solidify(digit, voxel_size=0.03):
        if digit is not None:
            safe_remove_object_with_data(digit)
        notes.append(f'{implant_obj.name}: could not build the order digit')
        return cutters, notes
    digit.display_type = 'WIRE'
    digit['DSG_frangible_mark'] = 'ORDER_DIGIT'
    digit['DSG_irrigation_open_order'] = order
    cutters.append(digit)
    return cutters, notes


def _voxel_solidify(obj, voxel_size=0.03):
    """Make a pixel-font cutter a closed 2-manifold.

    Glyph pixels that touch only along an edge (diagonal cells, e.g. in "3")
    create edges shared by four faces; an EXACT Boolean with such a cutter
    yields a non-solid guide. A fine voxel remesh fuses the cells (≤0.03 mm
    rounding on a 2.4 mm digit).
    """
    try:
        mod = obj.modifiers.new('DSG_DigitVoxel', 'REMESH')
        mod.mode = 'VOXEL'
        mod.voxel_size = float(voxel_size)
        mod.use_smooth_shade = False
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        new_mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        obj.modifiers.remove(mod)
        old = obj.data
        obj.data = new_mesh
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
        return bool(get_mesh_solid_report(obj).get('solid', False))
    except Exception as exc:
        _DSG_LOG.warning('digit cutter voxel fusion failed: %s', exc, exc_info=True)
        return False


def build_export_frangible_mark_cutters(context, props, guide_obj):
    cutters, notes = [], []
    for implant in get_sealed_irrigation_implants(props, require_confirmed_path=True):
        parts, part_notes = build_frangible_mark_cutters(context, props, implant, guide_obj)
        cutters.extend(parts)
        notes.extend(part_notes)
    return cutters, notes


# ── Viewport preview ────────────────────────────────────────────────────────
def clear_frangible_preview():
    for obj in list(bpy.data.objects):
        try:
            if obj.name.startswith(FRANGIBLE_PREVIEW_PREFIX):
                safe_remove_object_with_data(obj)
        except (ReferenceError, RuntimeError):
            continue


def build_frangible_preview(context, props):
    """Non-destructive display of walls (red) and marks (wire). Returns (count, notes)."""
    clear_frangible_preview()
    guide = get_active_guide_obj(props)
    count, notes = 0, []
    material = _ensure_frangible_preview_material()
    for implant in get_sealed_irrigation_implants(props, require_confirmed_path=True):
        seal, message = build_frangible_irrigation_seal_object(
            context, props, implant, name=f'{FRANGIBLE_PREVIEW_PREFIX}{implant.name}_Wall')
        if not _valid_obj(seal):
            notes.append(f'{implant.name}: {message}')
            continue
        seal.display_type = 'SOLID'
        if material is not None and seal.data is not None:
            seal.data.materials.append(material)
        count += 1
        marks, mark_notes = build_frangible_mark_cutters(
            context, props, implant, guide, name_prefix=f'{FRANGIBLE_PREVIEW_PREFIX}{implant.name}')
        notes.extend(mark_notes)
        for mark in marks:
            mark.show_in_front = True
            mark.hide_select = True
    return count, notes


def _ensure_frangible_preview_material():
    name = 'DSG_FrangiblePreview_Material'
    material = bpy.data.materials.get(name)
    if material is None:
        try:
            material = bpy.data.materials.new(name)
            material.diffuse_color = (0.95, 0.15, 0.10, 1.0)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
            return None
    return material


class DSG_OT_PreviewFrangibleMarks(Operator):
    bl_idname = 'dsg.preview_frangible_marks'
    bl_label = 'Preview Frangible Walls'
    bl_description = ('Show the 0.10 mm frangible walls, the countersink marks and the engraved '
                      'opening order before exporting (display only)')
    bl_options = {'REGISTER', 'UNDO'}

    clear: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        props = context.scene.dsg_props
        if self.clear:
            clear_frangible_preview()
            _dsg_report(self, {'INFO'}, 'Frangible preview removed', 'Vista previa de paredes frangibles eliminada')
            return {'FINISHED'}
        count, notes = build_frangible_preview(context, props)
        if count == 0:
            _dsg_report(self, {'WARNING'},
                        'No sealed sleeve to preview' + (f": {'; '.join(notes)}" if notes else ''),
                        'No hay cilindros sellados' + (f": {'; '.join(notes)}" if notes else ''))
            return {'CANCELLED'}
        message = f'{count} frangible wall(s) shown' + (f" · {'; '.join(notes)}" if notes else '')
        _dsg_report(self, {'WARNING'} if notes else {'INFO'}, message,
                    f'{count} pared(es) frangible(s) mostrada(s)' + (f" · {'; '.join(notes)}" if notes else ''))
        return {'FINISHED'}


FRANGIBLE_CLASSES = (DSG_OT_PreviewFrangibleMarks,)
