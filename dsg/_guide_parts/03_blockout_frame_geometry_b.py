def get_interimplant_spacing_results(props):
    implants = get_all_implant_objects(props)
    results = []
    for index, implant_a in enumerate(implants):
        for implant_b in implants[index + 1:]:
            result = measure_interimplant_platform_clearance(props, implant_a, implant_b)
            if result is not None:
                results.append(result)
    return sorted(results, key=lambda item: item['clearance_mm'])


def get_interimplant_spacing_violations(props):
    threshold = INTERIMPLANT_MIN_CLEARANCE_MM - INTERIMPLANT_NUMERIC_TOLERANCE_MM
    return [
        result for result in get_interimplant_spacing_results(props)
        if float(result['clearance_mm']) < threshold
    ]


def get_implant_safety_halos():
    return [
        obj for obj in bpy.data.objects
        if _valid_obj(obj)
        and not bool(obj.get('DSG_obsolete_hidden', False))
        and (obj.name.startswith(IMPLANT_SAFETY_PREFIX)
             or bool(obj.get('DSG_implant_safety_halo', False)))
    ]


def clear_implant_safety_halos(implant_obj=None):
    """Retires halos without deleting their Object IDs during the workflow."""
    implant_name = _safe_object_name(implant_obj) if implant_obj is not None else None
    removed = 0
    for halo in list(get_implant_safety_halos()):
        linked_name = str(halo.get('DSG_implant_name', '') or '')
        if implant_name and linked_name != implant_name:
            continue
        try:
            halo['DSG_implant_safety_halo'] = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        removed += int(_archive_transient_dsg_object(
            halo, reason='implant_safety_halo_retired', prefix='DSG_ArchivedHalo_'))
    return removed


def _implant_safety_halo_name(implant_obj):
    return f'{IMPLANT_SAFETY_PREFIX}{_safe_object_name(implant_obj) or "Implant"}'


def _replace_mesh_data_preserve_object(obj, new_mesh):
    if not _valid_obj(obj) or new_mesh is None:
        return False
    old_mesh = getattr(obj, 'data', None)
    obj.data = new_mesh
    try:
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def create_implant_safety_halo(context, props, implant_obj):
    """Create/reuse a longitudinal implant safety envelope.

    The former short platform ring is intentionally upgraded to span the full
    implant body. Geometry is only a visual envelope; clinical clearance is
    always measured from the real implant mesh to segmented teeth/BVH.
    """
    if not is_valid_implant_obj(implant_obj):
        return None
    implant_name = _safe_object_name(implant_obj) or ''
    tooth_margin = max(0.0, float(getattr(
        props, 'implant_tooth_clearance', IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM)))
    visual_margin = max(INTERIMPLANT_SAFETY_MARGIN_PER_IMPLANT_MM, tooth_margin)
    implant_radius = get_implant_nominal_diameter_world(props, implant_obj) * 0.5
    halo_radius = implant_radius + visual_margin
    halo_height = max(
        IMPLANT_SAFETY_ENVELOPE_MIN_HEIGHT_MM,
        float(get_implant_length_world(props, implant_obj)))
    center = get_implant_center_world(props, implant_obj)
    axis = get_implant_axis_world(props, implant_obj)
    if center is None or axis.length < 1e-8:
        return None

    existing = next((
        halo for halo in get_implant_safety_halos()
        if str(halo.get('DSG_implant_name', '') or '') == implant_name
    ), None)

    if _valid_obj(existing):
        current_radius = float(existing.get('DSG_safety_envelope_radius_mm', -1.0) or -1.0)
        current_height = float(existing.get('DSG_safety_envelope_height_mm', -1.0) or -1.0)
        if abs(current_radius - halo_radius) > 1.0e-4 or abs(current_height - halo_height) > 1.0e-4:
            mesh = make_cylinder_mesh(
                _implant_safety_halo_name(implant_obj) + '_Mesh',
                halo_radius, halo_height, verts=64)
            _replace_mesh_data_preserve_object(existing, mesh)
        existing.matrix_world = _matrix_along_local_z(center, axis)
        world_matrix = existing.matrix_world.copy()
        existing.parent = implant_obj
        try:
            existing.matrix_parent_inverse = implant_obj.matrix_world.inverted_safe()
        except Exception:
            existing.matrix_parent_inverse = implant_obj.matrix_world.inverted()
        existing.matrix_world = world_matrix
        try:
            existing.hide_viewport = False
            existing.hide_render = True
            existing.hide_select = True
            existing.hide_set(False)
            existing.show_in_front = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        existing['DSG_safety_margin_mm'] = float(visual_margin)
        existing['DSG_tooth_clearance_margin_mm'] = float(tooth_margin)
        existing['DSG_safety_envelope_radius_mm'] = float(halo_radius)
        existing['DSG_safety_envelope_height_mm'] = float(halo_height)
        existing['DSG_safety_envelope_longitudinal'] = True
        return existing

    mesh = make_cylinder_mesh(
        _implant_safety_halo_name(implant_obj) + '_Mesh',
        halo_radius, halo_height, verts=64)
    halo = bpy.data.objects.new(_implant_safety_halo_name(implant_obj), mesh)
    link_object(context, halo)
    halo.matrix_world = _matrix_along_local_z(center, axis)
    world_matrix = halo.matrix_world.copy()
    halo.parent = implant_obj
    try:
        halo.matrix_parent_inverse = implant_obj.matrix_world.inverted_safe()
    except Exception:
        halo.matrix_parent_inverse = implant_obj.matrix_world.inverted()
    halo.matrix_world = world_matrix
    halo.display_type = 'WIRE'
    halo.show_in_front = True
    halo.hide_render = True
    halo.hide_select = True
    try:
        halo.color = (0.10, 0.55, 1.0, 1.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    register_dsg_object(halo, ROLE_IMPLANT, halo.name, {
        'DSG_implant_safety_halo': True,
        'DSG_implant_name': str(implant_obj.name),
        'DSG_safety_margin_mm': float(visual_margin),
        'DSG_tooth_clearance_margin_mm': float(tooth_margin),
        'DSG_min_interimplant_clearance_mm': float(INTERIMPLANT_MIN_CLEARANCE_MM),
        'DSG_safety_envelope_radius_mm': float(halo_radius),
        'DSG_safety_envelope_height_mm': float(halo_height),
        'DSG_safety_envelope_longitudinal': True,
        'DSG_safety_visual_only': True,
    })
    return halo

def rebuild_implant_safety_halos(context, props):
    """Reuse one stable halo Object per implant instead of delete/recreate loops."""
    implants = get_all_implant_objects(props)
    implant_names = {_safe_object_name(implant) for implant in implants}
    for halo in list(get_implant_safety_halos()):
        linked_name = str(halo.get('DSG_implant_name', '') or '')
        if linked_name not in implant_names:
            try:
                halo['DSG_implant_safety_halo'] = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _archive_transient_dsg_object(
                halo, reason='orphan_implant_safety_halo', prefix='DSG_ArchivedHalo_')
    halos = []
    for implant in implants:
        halo = create_implant_safety_halo(context, props, implant)
        if _valid_obj(halo):
            halos.append(halo)
    return halos


def mark_implant_safety_halos(violations, additional_implant_names=None):
    violating_names = set(str(name) for name in (additional_implant_names or []) if name)
    for result in violations:
        if isinstance(result, dict):
            for key in ('implant_a', 'implant_b'):
                value = result.get(key)
                if value is not None:
                    violating_names.add(_safe_object_name(value))
            name = str(result.get('implant', '') or '')
            if name:
                violating_names.add(name)
    for halo in get_implant_safety_halos():
        linked_name = str(halo.get('DSG_implant_name', '') or '')
        try:
            # Blue = clear, amber = requires review. We avoid making the visual
            # envelope itself the source of truth; BVH measurements decide.
            halo.color = ((1.0, 0.42, 0.03, 1.0)
                          if linked_name in violating_names
                          else (0.10, 0.55, 1.0, 1.0))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def get_implant_tooth_safety_results(props, verification_mode='FAST'):
    """Return implant↔tooth clearance results for implants with a valid target FDI.

    FAST is intended for viewport feedback. EXACT is reserved for the clinical
    confirmation gate and fails closed if the triangle verifier cannot finish.
    """
    mode = str(verification_mode or 'FAST').upper()
    try:
        from .dental_mapping import surgical_context
    except Exception as exc:
        if mode == 'EXACT':
            # Confirmation must fail closed when the exact verifier itself is
            # unavailable.  Only implants that explicitly target an FDI are in
            # scope; legacy/manual implants without FDI remain outside this gate.
            failed = []
            for implant in get_all_implant_objects(props):
                fdi = int(implant.get('DSG_target_fdi', 0) or 0)
                if dental_assets.valid_fdi(fdi, include_primary=False):
                    failed.append({
                        'schema': 'dsg.implant_neighbor_clearance.v3',
                        'fdi': fdi, 'implant': implant.name,
                        'error': f'Exact dental safety engine unavailable: {exc}',
                        'verification_mode': mode, 'hard_gate_eligible': False,
                        'required_clearance_mm': max(0.0, float(getattr(
                            props, 'implant_tooth_clearance', IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM))),
                        'safe': None,
                    })
            return failed
        return []
    required = max(0.0, float(getattr(
        props, 'implant_tooth_clearance', IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM)))
    results = []
    for implant in get_all_implant_objects(props):
        fdi = int(implant.get('DSG_target_fdi', 0) or 0)
        if not dental_assets.valid_fdi(fdi, include_primary=False):
            continue
        try:
            result = surgical_context.analyze_implant_neighbor_clearance(
                fdi=fdi, implant_name=implant.name, required_clearance_mm=required,
                verification_mode=mode)
            results.append(result)
        except Exception as exc:
            results.append({
                'schema': 'dsg.implant_neighbor_clearance.v3',
                'fdi': fdi, 'implant': implant.name, 'error': str(exc),
                'verification_mode': mode, 'hard_gate_eligible': False,
                'required_clearance_mm': required, 'safe': None})
    return results


def get_implant_tooth_safety_violations(props, verification_mode='FAST'):
    return [r for r in get_implant_tooth_safety_results(props, verification_mode=verification_mode) if r.get('safe') is False]


class DSG_OT_AnalyzeImplantSafety(Operator):
    bl_idname = 'dsg.analyze_implant_safety'
    bl_label = 'Analyze Implant Safety'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        rebuild_implant_safety_halos(context, props)
        inter = get_interimplant_spacing_violations(props)
        tooth_results = get_implant_tooth_safety_results(props)
        tooth_viol = [r for r in tooth_results if r.get('safe') is False]
        mark_implant_safety_halos(
            inter, additional_implant_names=[r.get('implant') for r in tooth_viol])
        measured = [r for r in tooth_results if r.get('minimum_neighbor_clearance_mm') is not None]
        if tooth_viol:
            worst = min(tooth_viol, key=lambda r: float(r.get('minimum_neighbor_clearance_mm', 1e9)))
            _dsg_report(
                self, {'WARNING'},
                f"Tooth safety review: {worst['implant']} has {worst['minimum_neighbor_clearance_mm']:.2f} mm; required {worst['required_clearance_mm']:.2f} mm.",
                f"Revisión de seguridad dental: {worst['implant']} tiene {worst['minimum_neighbor_clearance_mm']:.2f} mm; requerido {worst['required_clearance_mm']:.2f} mm.")
        elif measured:
            worst = min(measured, key=lambda r: float(r.get('minimum_neighbor_clearance_mm', 1e9)))
            _dsg_report(
                self, {'INFO'},
                f"Implant-tooth safety OK. Minimum measured clearance: {worst['minimum_neighbor_clearance_mm']:.2f} mm.",
                f"Seguridad implante-diente correcta. Distancia mínima medida: {worst['minimum_neighbor_clearance_mm']:.2f} mm.")
        else:
            _dsg_report(
                self, {'INFO'},
                'Safety envelope updated. Implant-tooth analysis requires implants linked to a target FDI.',
                'Envolvente de seguridad actualizada. El análisis implante-diente requiere implantes vinculados a un FDI objetivo.')
        return {'FINISHED'}


def _get_emergence_controller_for_implant(implant_obj):
    implant_name = _safe_object_name(implant_obj) or ''
    for tube in get_implant_emergence_tubes():
        if str(tube.get('DSG_implant_name', '') or '') == implant_name:
            return tube
    return None


def select_interimplant_violation(context, props, result):
    """Selecciona los dos controles implicados para que el usuario pueda separarlos."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    selected = []
    for implant in (result['implant_a'], result['implant_b']):
        target = _get_emergence_controller_for_implant(implant) or implant
        if not _valid_obj(target):
            continue
        try:
            target.hide_select = False
            target.select_set(True)
            selected.append(target)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if selected:
        props.implant_obj = result['implant_b']
        try:
            context.view_layer.objects.active = selected[-1]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def get_implant_emergence_tubes():
    tubes = []
    for obj in bpy.data.objects:
        if not _valid_obj(obj) or bool(obj.get('DSG_obsolete_hidden', False)):
            continue
        name = str(obj.name)
        if (name.startswith(IMPLANT_EMERGENCE_PREFIX)
                or name.startswith(IMPLANT_EMERGENCE_LEGACY_PREFIX)
                or bool(obj.get('DSG_implant_emergence_tube', False))):
            tubes.append(obj)
    return tubes



def _detach_implant_from_emergence_tube(tube):
    """Preserves the edited implant pose before removing its temporary controller."""
    if not _valid_obj(tube):
        return None
    implant_name = str(tube.get('DSG_implant_name', '') or '')
    implant = bpy.data.objects.get(implant_name) if implant_name else None
    if not is_valid_implant_obj(implant):
        return None

    try:
        world_matrix = implant.matrix_world.copy()
    except Exception:
        world_matrix = None

    if implant.parent == tube:
        original_parent_name = str(tube.get('DSG_original_implant_parent_name', '') or '')
        original_parent = bpy.data.objects.get(original_parent_name) if original_parent_name else None
        if original_parent is not None and not _valid_obj(original_parent):
            original_parent = None
        implant.parent = original_parent
        if world_matrix is not None:
            implant.matrix_world = world_matrix

    try:
        implant.hide_select = bool(tube.get('DSG_original_implant_hide_select', False))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return implant



def clear_implant_emergence_tubes():
    """Detach and archive controllers; do not delete IDs during clinical flow."""
    removed = 0
    for obj in list(get_implant_emergence_tubes()):
        _detach_implant_from_emergence_tube(obj)
        try:
            obj['DSG_implant_emergence_tube'] = False
            obj['DSG_implant_emergence_controller'] = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        removed += int(_archive_transient_dsg_object(
            obj, reason='implant_emergence_confirmed', prefix='DSG_ArchivedEmergence_'))
    return removed


def remove_implant_emergence_tubes_for_implant(implant_obj):
    """Removes only the temporary emergence controller linked to one implant."""
    if not _valid_obj(implant_obj):
        return 0

    implant_name = _safe_object_name(implant_obj) or ''
    removed = 0
    for tube in list(get_implant_emergence_tubes()):
        linked_name = str(tube.get('DSG_implant_name', '') or '')
        is_parent = False
        try:
            is_parent = implant_obj.parent == tube
        except Exception:
            is_parent = False

        if linked_name != implant_name and not is_parent:
            continue

        # Detach first so the implant keeps the position/orientation edited
        # through the emergence controller. The implant is deleted immediately
        # afterwards by the caller, but detaching avoids leaving broken parents.
        _detach_implant_from_emergence_tube(tube)
        try:
            tube['DSG_implant_emergence_tube'] = False
            tube['DSG_implant_emergence_controller'] = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        removed += int(_archive_transient_dsg_object(
            tube, reason='implant_deleted', prefix='DSG_ArchivedEmergence_'))

    try:
        if 'DSG_temporarily_controlled_by_emergence' in implant_obj:
            del implant_obj['DSG_temporarily_controlled_by_emergence']
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return removed



def _emergence_coronal_direction_world(implant_obj):
    """Return the coronal/platform direction of the embedded implant.

    The internal implant template is normalized with its platform at local +Z
    and its apex at local -Z.  The emergency controller must therefore always
    extend along local +Z.  Re-evaluating the side from the blockout axis can
    invert the controller after manual rotations or workflow migrations.
    """
    if not is_valid_implant_obj(implant_obj):
        return Vector((0.0, 0.0, 1.0))
    try:
        direction = implant_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
        if direction.length > 1e-8:
            return direction.normalized()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return Vector((0.0, 0.0, 1.0))


def _rebuild_emergence_controller_geometry(context, obj, implant_obj, index=0):
    """Rebuild one controller as the clean v7.0.53 cylinder, preserving pose.

    The Object ID is reused to avoid Outliner/AnimData instability, while the
    mesh datablock is replaced transactionally so malformed or legacy geometry
    cannot be reused.
    """
    if not _valid_obj(obj) or not is_valid_implant_obj(implant_obj):
        return None

    length = float(IMPLANT_EMERGENCE_LENGTH_MM)
    radius = float(IMPLANT_EMERGENCE_DIAMETER_MM) * 0.5
    implant_world = implant_obj.matrix_world.copy()
    original_parent_name = str(obj.get('DSG_original_implant_parent_name', '') or '')
    original_parent = bpy.data.objects.get(original_parent_name) if original_parent_name else None
    if original_parent is not None and not _valid_obj(original_parent):
        original_parent = None

    # Temporarily detach the implant so changing the controller matrix cannot
    # move or scale the clinical implant.
    if implant_obj.parent == obj:
        implant_obj.parent = original_parent
        implant_obj.matrix_world = implant_world

    old_mesh = obj.data if obj.type == 'MESH' else None
    mesh = make_cylinder_mesh(
        f'{IMPLANT_EMERGENCE_PREFIX}_{index:02d}_Mesh',
        radius,
        length,
        verts=24,
    )
    # make_cylinder_mesh is centred on local Z. Move its geometry so the object
    # origin is at the implant centre and the tube occupies local Z = 0..15 mm.
    mesh.transform(Matrix.Translation((0.0, 0.0, length * 0.5)))
    mesh.update()
    obj.data = mesh
    if old_mesh is not None and old_mesh is not mesh and old_mesh.users == 0:
        try:
            bpy.data.meshes.remove(old_mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    center = get_implant_center_world(context.scene.dsg_props, implant_obj)
    direction = _emergence_coronal_direction_world(implant_obj)
    obj.matrix_world = _matrix_along_local_z(Vector(center), direction)
    obj.name = f'{IMPLANT_EMERGENCE_PREFIX}_{index:02d}'
    try:
        obj.data.name = obj.name + '_Mesh'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    original_hide_select = bool(obj.get(
        'DSG_original_implant_hide_select',
        getattr(implant_obj, 'hide_select', False),
    ))
    obj.display_type = 'SOLID'
    obj.show_in_front = True
    obj.hide_render = True
    obj.hide_viewport = False
    obj.hide_select = False
    obj.hide_set(False)
    obj.lock_scale = (True, True, True)
    try:
        obj.color = (0.42, 0.72, 0.58, 1.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    register_dsg_object(obj, ROLE_IMPLANT, obj.name, {
        'DSG_implant_emergence_tube': True,
        'DSG_implant_emergence_controller': True,
        'DSG_implant_name': str(implant_obj.name),
        'DSG_original_implant_parent_name': (
            original_parent.name if _valid_obj(original_parent) else ''),
        'DSG_original_implant_hide_select': original_hide_select,
        'DSG_emergence_length_mm': float(length),
        'DSG_emergence_diameter_mm': float(IMPLANT_EMERGENCE_DIAMETER_MM),
        'DSG_emergence_schema': 2,
        'DSG_emergence_direction': 'implant_local_positive_z_coronal',
        'DSG_emergence_clean_cylinder': True,
        'DSG_target_fdi': int(implant_obj.get('DSG_target_fdi', 0) or 0),
        'DSG_target_family_id': str(implant_obj.get('DSG_target_family_id', '') or ''),
        'DSG_asset_contract_sha256': str(implant_obj.get('DSG_asset_contract_sha256', '') or ''),
    })

    # Reattach while preserving the exact implant matrix.
    implant_obj.parent = obj
    try:
        implant_obj.matrix_parent_inverse = obj.matrix_world.inverted_safe()
    except Exception:
        implant_obj.matrix_parent_inverse = obj.matrix_world.inverted()
    implant_obj.matrix_world = implant_world
    implant_obj.hide_select = True
    implant_obj['DSG_temporarily_controlled_by_emergence'] = True
    return obj


def create_implant_emergence_tube(context, props, implant_obj, index=0):
    if not is_valid_implant_obj(implant_obj):
        return None

    existing = _get_emergence_controller_for_implant(implant_obj)
    if _valid_obj(existing):
        schema = int(existing.get('DSG_emergence_schema', 0) or 0)
        clean = bool(existing.get('DSG_emergence_clean_cylinder', False))
        if schema >= 2 and clean and existing.type == 'MESH':
            try:
                existing.hide_viewport = False
                existing.hide_render = True
                existing.hide_select = False
                existing.hide_set(False)
                existing.show_in_front = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return existing
        # One-time migration of legacy/malformed controllers. The implant pose
        # is preserved and the same Object ID is reused.
        return _rebuild_emergence_controller_geometry(
            context, existing, implant_obj, index=index)

    mesh = make_cylinder_mesh(
        f'{IMPLANT_EMERGENCE_PREFIX}_{index:02d}_Mesh',
        float(IMPLANT_EMERGENCE_DIAMETER_MM) * 0.5,
        float(IMPLANT_EMERGENCE_LENGTH_MM),
        verts=24,
    )
    obj = bpy.data.objects.new(f'{IMPLANT_EMERGENCE_PREFIX}_{index:02d}', mesh)
    link_object(context, obj)
    return _rebuild_emergence_controller_geometry(
        context, obj, implant_obj, index=index)



def get_nearest_implant_to_point(props, point):
    """Devuelve el implante DSG cuyo sleeve queda más cerca de un punto world.

    En multiimplante no conviene depender solo de props.implant_obj: durante la
    irrigación el usuario puede clicar sobre cualquier sleeve. Este helper mide
    la cercanía al cilindro teórico del sleeve de cada implante y elige el mejor.
    """
    implants = get_all_implant_objects(props)
    if not implants:
        return None

    p = Vector(point)
    inner_r = _sleeve_inner_radius_from_props(props)
    outer_r = inner_r + props.sleeve_wall
    half_h = props.sleeve_height * 0.5

    best_obj = None
    best_score = float('inf')
    for implant in implants:
        try:
            sleeve_mx = get_sleeve_matrix_world(props, implant)
            local = sleeve_mx.inverted() @ p
        except Exception:
            continue

        radial = math.hypot(local.x, local.y)
        radial_error = abs(radial - outer_r)
        z_error = max(0.0, abs(local.z) - half_h)
        center_bias = (sleeve_mx.to_translation() - p).length * 0.01
        score = radial_error + z_error * 0.35 + center_bias

        if score < best_score:
            best_score = score
            best_obj = implant

    return best_obj


def ensure_implant_divergence_property(implant_obj):
    if not is_valid_implant_obj(implant_obj):
        return 0.0
    if 'DSG_divergence_deg' not in implant_obj:
        implant_obj['DSG_divergence_deg'] = 0.0
    try:
        implant_obj.id_properties_ui('DSG_divergence_deg').update(
            min=-20.0, max=20.0, soft_min=-10.0, soft_max=10.0,
            description='Individual angular offset relative to the master implant')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        return float(implant_obj.get('DSG_divergence_deg', 0.0))
    except Exception:
        return 0.0


def copy_implant_world_rotation_keep_position(target_obj, master_obj, divergence_deg=0.0):
    """Copia el eje del maestro y aplica una divergencia individual controlada.

    El giro se realiza en el plano definido por el maestro y la posición del
    implante destino, de modo que un offset positivo abre el implante hacia fuera
    y uno negativo lo inclina hacia el maestro. El centro y la escala no cambian.
    """
    if not is_valid_implant_obj(target_obj) or not is_valid_implant_obj(master_obj):
        return False

    loc = target_obj.matrix_world.to_translation()
    master_loc = master_obj.matrix_world.to_translation()
    scale = target_obj.matrix_world.to_scale()
    master_rot = master_obj.matrix_world.to_quaternion()
    master_axis = (master_rot @ Vector((0.0, 0.0, 1.0))).normalized()

    lateral = loc - master_loc
    lateral -= master_axis * lateral.dot(master_axis)
    if lateral.length < 1e-7:
        lateral = master_rot @ Vector((1.0, 0.0, 0.0))
    lateral.normalize()

    rotation_axis = master_axis.cross(lateral)
    if rotation_axis.length < 1e-7:
        rotation_axis = master_rot @ Vector((0.0, 1.0, 0.0))
    rotation_axis.normalize()

    offset_q = Quaternion(rotation_axis, math.radians(float(divergence_deg)))
    target_rot = offset_q @ master_rot
    target_obj.matrix_world = Matrix.LocRotScale(loc, target_rot, scale)
    target_obj['DSG_divergence_applied_deg'] = float(divergence_deg)
    return True


def is_implant_parallel_locked(implant_obj):
    """True when an implant must keep its current pose during parallelization.

    This lock is intentionally limited to DSG parallelization. It does not use
    Blender's transform locks, so the clinician can still unlock and reposition
    the implant manually without hidden constraints or broken downstream tools.
    """
    if not is_valid_implant_obj(implant_obj):
        return False
    try:
        return bool(implant_obj.get('DSG_parallel_locked', False))
    except Exception:
        return False


def set_implant_parallel_locked(implant_obj, locked):
    if not is_valid_implant_obj(implant_obj):
        return False
    implant_obj['DSG_parallel_locked'] = bool(locked)
    try:
        implant_obj.id_properties_ui('DSG_parallel_locked').update(
            description='Preserves this implant position and angulation when other implants are parallelized')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def get_implant_for_parallel_lock(context, props):
    """Resolve the implant the lock button should affect.

    The active scene selection has priority, matching the visible object the user
    is working on. The stored active implant is only a safe fallback.
    """
    active = context.view_layer.objects.active if context and context.view_layer else None
    if is_valid_implant_obj(active):
        return active
    candidate = getattr(props, 'implant_obj', None)
    return candidate if is_valid_implant_obj(candidate) else None


def get_parallel_master_implant(context, props):
    """Devuelve el implante maestro elegido en UI o el activo/seleccionado."""
    active = context.view_layer.objects.active if context and context.view_layer else None

    if is_valid_implant_obj(getattr(props, 'parallel_master_implant', None)):
        return props.parallel_master_implant
    if is_valid_implant_obj(active):
        return active
    if is_valid_implant_obj(getattr(props, 'implant_obj', None)):
        return props.implant_obj

    implants = get_all_implant_objects(props)
    return implants[-1] if implants else None


def get_next_implant_name():
    max_idx = 0
    for obj in bpy.data.objects:
        if not obj.name.startswith(IMPLANT_PREFIX):
            continue
        suffix = obj.name[len(IMPLANT_PREFIX):].strip('_.- ')
        if suffix.isdigit():
            max_idx = max(max_idx, int(suffix))
        else:
            max_idx = max(max_idx, 1)
    return f"{IMPLANT_PREFIX}_{max_idx + 1:02d}"


def get_implant_center_world(props, implant_obj=None):
    implant = implant_obj if implant_obj is not None else props.implant_obj
    if not _valid_obj(implant):
        return None
    return implant.matrix_world.translation.copy()


def get_implant_axis_world(props, implant_obj=None):
    implant = implant_obj if implant_obj is not None else props.implant_obj
    if not _valid_obj(implant):
        return Vector((0, 0, 1))
    return (implant.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()


def get_implant_length_world(props, implant_obj=None):
    """Length real aproximada del implante en world-space.

    Se usa para colocar el sleeve por encima/oclusal al implante sin depender
    solo del valor del panel si el usuario escaló el cilindro manualmente.
    """
    implant = implant_obj if implant_obj is not None else props.implant_obj
    fallback = max(0.1, float(getattr(props, 'implant_length', 10.0)))
    if not is_valid_implant_obj(implant):
        return fallback
    try:
        bb = implant.bound_box
        local_z = max(v[2] for v in bb) - min(v[2] for v in bb)
        scale_z = abs(implant.matrix_world.to_scale().z)
        length = local_z * scale_z
        return length if length > 0.1 else fallback
    except Exception:
        return fallback


def get_sleeve_occlusal_sign(props, implant_obj=None):
    """Devuelve el lado del eje del implante donde debe ir el sleeve.

    NUEVA LOGICA v5.0.2:
    El usuario ya eligio el sentido clinico de entrada al capturar el eje desde
    la vista para generar el blockout. Por tanto, el sleeve debe quedar en el
    lado contrario a ese eje de insercion, es decir, hacia el lado abierto/oclusal
    desde el que se asienta la guia.

    Como el sleeve debe seguir siendo coaxial al implante, solo elegimos entre
    +Z o -Z LOCAL del implante. Calculamos cual de los dos sentidos es mas
    opuesto al eje de blockout y desplazamos el sleeve hacia ese lado.
    """
    implant = implant_obj if implant_obj is not None else getattr(props, 'implant_obj', None)
    if not is_valid_implant_obj(implant):
        return 1.0

    implant_axis = (implant.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    try:
        blockout_axis = get_insertion_axis().normalized()
    except Exception:
        blockout_axis = Vector((0, 0, 1))

    if blockout_axis.length < 1e-6:
        return 1.0

    # Queremos que (sign * implant_axis) apunte en sentido contrario al eje de
    # blockout. Si implant_axis ya mira contra el blockout, sign = +1; si mira
    # en el mismo sentido, sign = -1.
    return -1.0 if implant_axis.dot(blockout_axis) >= 0.0 else 1.0


def get_sleeve_matrix_world(props, implant_obj=None):
    """Matriz clínica real del sleeve asociado a un implante.

    Si el usuario movió o rotó el preview del sleeve antes de aplicarlo, se usa
    la matriz guardada en el implante. Si no existe, se calcula coaxialmente como
    en el flujo clásico.
    """
    implant = implant_obj if implant_obj is not None else props.implant_obj
    if not is_valid_implant_obj(implant):
        return Matrix.Identity(4)

    try:
        raw = implant.get('DSG_sleeve_matrix_world', '')
        if raw:
            values = json.loads(raw) if isinstance(raw, str) else raw
            if len(values) == 4 and all(len(row) == 4 for row in values):
                return Matrix(values)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    mx = implant.matrix_world.copy()
    axis = (implant.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    implant_len = get_implant_length_world(props, implant)
    sleeve_h = max(0.1, float(getattr(props, 'sleeve_height', 8.0)))
    gap = max(0.0, float(getattr(props, 'sleeve_implant_gap', 0.0)))
    shift = get_sleeve_occlusal_sign(props, implant) * (implant_len * 0.5 + gap + sleeve_h * 0.5)
    mx.translation = implant.matrix_world.to_translation() + axis * shift
    return mx


def get_sleeve_center_world(props, implant_obj=None):
    return get_sleeve_matrix_world(props, implant_obj).to_translation()


def get_sleeve_axis_world(props, implant_obj=None):
    implant = implant_obj if implant_obj is not None else props.implant_obj
    if not is_valid_implant_obj(implant):
        return Vector((0, 0, 1))
    mx = get_sleeve_matrix_world(props, implant)
    return (mx.to_3x3() @ Vector((0, 0, 1))).normalized()


def _irrigation_entry_for_implant(props, implant_obj):
    name = implant_obj.name if is_valid_implant_obj(implant_obj) else ''
    for entry in load_irrigation_path_entries(props):
        if str(entry.get('implant_name') or entry.get('implant') or '') == name:
            return entry
    return None


# build_frangible_irrigation_seal_object() moved to 06_irrigation_d_frangible.py
# (DSG 9.7.2): the membrane now sits inside every outlet channel instead of
# floating in the drill bore, and the marks are printable.


def build_export_frangible_irrigation_seals(context, props):
    seals = []
    for implant in get_sealed_irrigation_implants(props, require_confirmed_path=True):
        name = IRRIGATION_FRANGIBLE_SEAL_PREFIX + implant.name + '_Export'
        safe_remove_temp_by_name(name)
        seal, message = build_frangible_irrigation_seal_object(
            context, props, implant, name=name)
        if not _valid_obj(seal):
            for item in seals:
                safe_remove_object_with_data(item)
            return [], f'{implant.name}: {message}'
        seals.append(seal)
    return seals, 'ok'


IRRIGATION_PARAMETER_KEYS = (
    'irr_inner_diameter',
    'irr_wall_thickness',
    'irr_bevel_resolution',
    'irr_funnel_depth',
    'irr_cut_overshoot',
    'irr_wall_exit_overshoot',
    'irr_direct_sleeve_lumen_overlap',
    'irr_curve_smooth_iters',
    'irr_terminal_depth',
    'irr_entry_length',
    'irr_sleeve_overlap',
    'irr_junction_blend',
    'irr_funnel_enabled',
    'irr_sleeve_channel_mode',
    'irr_funnel_outer_diameter',
    'irr_taper_length',
    'irr_lumen_subdivision',
    'organic_tcb_tension',
    'organic_tcb_bias',
    'organic_tcb_continuity',
    'organic_tcb_contact_scale',
    'frame_catmull_alpha',
)


class _IrrigationPropsOverlay:
    """Vista de propiedades que conserva los valores propios de un conducto."""
    def __init__(self, base_props, values=None):
        self._base_props = base_props
        self._values = dict(values or {})

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        return getattr(self._base_props, name)


def capture_irrigation_parameters(props):
    values = {}
    for key in IRRIGATION_PARAMETER_KEYS:
        try:
            value = getattr(props, key)
            if isinstance(value, bool):
                values[key] = bool(value)
            elif isinstance(value, int):
                values[key] = int(value)
            elif isinstance(value, str):
                values[key] = str(value)
            else:
                values[key] = float(value)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    # The reduced outlet/nozzle is now a permanent clinical rule.
    values['irr_funnel_enabled'] = True
    values['irr_lumen_sample_step'] = float(IRR_LUMEN_SAMPLE_STEP_MM_FIXED)
    return values


def irrigation_props_overlay(props, values=None):
    fixed_values = dict(values or {})
    # Always keep the sleeve outlet reduction active, including older scenes
    # that may have stored the former checkbox as disabled.
    fixed_values['irr_funnel_enabled'] = True
    fixed_values['irr_lumen_sample_step'] = float(IRR_LUMEN_SAMPLE_STEP_MM_FIXED)
    return _IrrigationPropsOverlay(props, fixed_values)


def irrigation_parameters_from_object(obj, props):
    if _valid_obj(obj):
        try:
            raw = obj.get('DSG_irrigation_params', '')
            if raw:
                values = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if isinstance(values, dict):
                    return values
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return capture_irrigation_parameters(props)


def store_irrigation_path(props, points, implant_obj=None, parameters=None):
    try:
        data = json.loads(props.irr_paths_json or "[]")
    except Exception:
        data = []

    implant_name = None
    if _valid_obj(implant_obj):
        implant_name = implant_obj.name
    elif _valid_obj(props.implant_obj):
        implant_name = props.implant_obj.name

    entry = {
        "implant": implant_name,
        "points": [[float(p.x), float(p.y), float(p.z)] for p in points],
        "parameters": dict(parameters or capture_irrigation_parameters(props)),
        "index": len(data),
    }
    data.append(entry)
    props.irr_paths_json = json.dumps(data)
    auto_assign_irrigation_gate_defaults(props)


def load_irrigation_path_entries(props):
    try:
        data = json.loads(props.irr_paths_json or "[]")
    except Exception:
        data = []

    out = []
    for index, entry in enumerate(data):
        implant_name = None
        parameters = {}
        chain = entry
        if isinstance(entry, dict):
            implant_name = entry.get("implant")
            chain = entry.get("points", [])
            raw_params = entry.get("parameters", {})
            parameters = raw_params if isinstance(raw_params, dict) else {}

        pts = []
        for p in chain:
            if len(p) == 3:
                pts.append(Vector((p[0], p[1], p[2])))

        implant_obj = bpy.data.objects.get(implant_name) if implant_name else None
        if len(pts) >= 2:
            out.append({
                "points": pts,
                "implant": implant_obj,
                "implant_name": implant_name,
                "parameters": parameters,
                "index": int(entry.get('index', index)) if isinstance(entry, dict) else index,
                "link": bool(entry.get('link', False)) if isinstance(entry, dict) else False,
                "source_index": int(entry.get('source_index', -1)) if isinstance(entry, dict) else -1,
                "link_split_point": entry.get('link_split_point') if isinstance(entry, dict) else None,
                "link_trunk_point": entry.get('link_trunk_point') if isinstance(entry, dict) else None,
                "link_source_shoulder": entry.get('link_source_shoulder') if isinstance(entry, dict) else None,
                "link_source_rejoin": entry.get('link_source_rejoin') if isinstance(entry, dict) else None,
                "link_manifold_center": entry.get('link_manifold_center') if isinstance(entry, dict) else None,
                "link_source_tangent": entry.get('link_source_tangent') if isinstance(entry, dict) else None,
                "link_channel_point": entry.get('link_channel_point') if isinstance(entry, dict) else None,
                "link_lateral": entry.get('link_lateral') if isinstance(entry, dict) else None,
                "link_side_chamber_center": entry.get('link_side_chamber_center') if isinstance(entry, dict) else None,
                "link_split_center": entry.get('link_split_center') if isinstance(entry, dict) else None,
                "link_trunk_direction": entry.get('link_trunk_direction') if isinstance(entry, dict) else None,
                "link_branch_angle_deg": entry.get('link_branch_angle_deg') if isinstance(entry, dict) else None,
                "link_geometry_mode": entry.get('link_geometry_mode') if isinstance(entry, dict) else None,
                "link_common_anchor": entry.get('link_common_anchor') if isinstance(entry, dict) else None,
                "link_main_rejoin": entry.get('link_main_rejoin') if isinstance(entry, dict) else None,
                "link_main_shoulder": entry.get('link_main_shoulder') if isinstance(entry, dict) else None,
                "link_link_shoulder": entry.get('link_link_shoulder') if isinstance(entry, dict) else None,
                "link_link_rejoin": entry.get('link_link_rejoin') if isinstance(entry, dict) else None,
                "link_branch_midpoint": entry.get('link_branch_midpoint') if isinstance(entry, dict) else None,
                "link_plenum_radius": entry.get('link_plenum_radius') if isinstance(entry, dict) else None,
            })
    return out


def sort_irrigation_entries_for_boolean(entries):
    """Links first, then regular channels, preserving relative order.

    The link branches must cut first so the main channels can open the final
    communication afterwards when Apply Irrigation is executed.
    """
    ordered = list(entries or [])
    return sorted(
        ordered,
        key=lambda entry: (0 if bool(entry.get('link', False)) else 1,
                           int(entry.get('index', 0)))
    )


def extend_polyline_ends(points, extra_start=0.0, extra_end=0.0):
    """
    Extiende una polilínea por sus extremos siguiendo la dirección del
    primer y último segmento. Esto ayuda a que el cutter sobresalga del
    tubo orgánico y el boolean recorte completamente la luz interna.
    """
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return pts

    if extra_start > 0.0:
        first_dir = pts[0] - pts[1]
        if first_dir.length > 1e-6:
            pts[0] = pts[0] + first_dir.normalized() * extra_start

    if extra_end > 0.0:
        last_dir = pts[-1] - pts[-2]
        if last_dir.length > 1e-6:
            pts[-1] = pts[-1] + last_dir.normalized() * extra_end

    return pts


def smooth_polyline_chaikin(points, iterations=2):
    pts = [Vector(p) for p in points]
    if len(pts) < 3 or iterations <= 0:
        return pts
    for _ in range(iterations):
        new_pts = [pts[0].copy()]
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            q = p0 * 0.75 + p1 * 0.25
            r = p0 * 0.25 + p1 * 0.75
            new_pts.extend([q, r])
        new_pts.append(pts[-1].copy())
        pts = new_pts
    return pts


def _remove_near_duplicate_points(points, epsilon=0.01, closed=False):
    """Elimina duplicados consecutivos sin cambiar la intención clínica del usuario.

    Es importante antes de Catmull-Rom porque dos puntos iguales generan
    intervalos t de longitud cero y pueden crear artefactos o loops.
    """
    pts = [Vector(p) for p in points]
    if not pts:
        return []

    out = []
    eps = max(0.0, float(epsilon))
    for p in pts:
        if not out or (p - out[-1]).length > eps:
            out.append(p.copy())

    if closed and len(out) > 2 and (out[0] - out[-1]).length <= eps:
        out.pop()
    return out


def _angle_between_segments(a, b, c):
    """Ángulo en b entre a-b-c. Devuelve 0 si los segmentos son inválidos."""
    v1 = Vector(b) - Vector(a)
    v2 = Vector(c) - Vector(b)
    if v1.length < 1e-8 or v2.length < 1e-8:
        return 0.0
    try:
        return v1.normalized().angle(v2.normalized(), 0.0)
    except Exception:
        return 0.0


def _centripetal_t(t_prev, p_prev, p_next, alpha=0.5):
    """Parámetro t para Catmull-Rom centrípeto.

    alpha=0.5 reduce overshoot y loops frente a Catmull-Rom uniforme.
    """
    dist = max((Vector(p_next) - Vector(p_prev)).length, 1e-6)
    return float(t_prev) + (dist ** max(0.0, min(1.0, float(alpha))))


def _lerp_by_t(pa, pb, ta, tb, t):
    denom = float(tb - ta)
    if abs(denom) < 1e-8:
        return Vector(pa).copy()
    return Vector(pa) * ((tb - t) / denom) + Vector(pb) * ((t - ta) / denom)


def catmull_rom_centripetal_point(p0, p1, p2, p3, u, alpha=0.5):
    """Punto Catmull-Rom centrípeto entre p1 y p2.

    u está normalizado entre 0 y 1. La curva pasa por p1 y p2, por eso es
    adecuada para un contorno clínico donde los puntos del usuario son anchors.
    """
    p0, p1, p2, p3 = Vector(p0), Vector(p1), Vector(p2), Vector(p3)
    t0 = 0.0
    t1 = _centripetal_t(t0, p0, p1, alpha)
    t2 = _centripetal_t(t1, p1, p2, alpha)
    t3 = _centripetal_t(t2, p2, p3, alpha)

    t = t1 + (t2 - t1) * max(0.0, min(1.0, float(u)))

    a1 = _lerp_by_t(p0, p1, t0, t1, t)
    a2 = _lerp_by_t(p1, p2, t1, t2, t)
    a3 = _lerp_by_t(p2, p3, t2, t3, t)
    b1 = _lerp_by_t(a1, a2, t0, t2, t)
    b2 = _lerp_by_t(a2, a3, t1, t3, t)
    c  = _lerp_by_t(b1, b2, t1, t2, t)
    return c


def build_catmull_rom_frame_path(points, closed=True, alpha=0.5, max_spacing=0.6,
                                  min_samples_per_segment=6, max_samples_per_segment=64):
    """Convierte los puntos manuales del contorno en una ruta densa y orgánica.

    Uso previsto: Paso 6 / frame tubular.
    - Respeta los puntos del usuario: la curva pasa por ellos.
    - Usa Catmull-Rom centrípeto para evitar barrigas/loops innecesarios.
    - Subdivide adaptativamente por distancia y por cambio angular.
    - Si closed=True devuelve una ruta sin duplicar el primer punto; debe usarse
      con una curva cíclica para evitar un segmento cero en la unión.
    """
    pts = _remove_near_duplicate_points(points, epsilon=0.01, closed=closed)
    n = len(pts)
    if n < 2:
        return pts
    if closed and n < 4:
        return pts
    if (not closed) and n < 4:
        return pts

    spacing = max(0.15, float(max_spacing))
    min_s = max(2, int(min_samples_per_segment))
    max_s = max(min_s, int(max_samples_per_segment))
    alpha = max(0.0, min(1.0, float(alpha)))

    out = []

    if closed:
        segment_count = n
        for i in range(segment_count):
            p0 = pts[(i - 1) % n]
            p1 = pts[i % n]
            p2 = pts[(i + 1) % n]
            p3 = pts[(i + 2) % n]

            chord = (p2 - p1).length
            by_distance = int(math.ceil(chord / spacing)) if chord > 1e-8 else min_s

            # Más muestras si hay cambio fuerte de dirección en los anchors vecinos.
            a1 = _angle_between_segments(p0, p1, p2)
            a2 = _angle_between_segments(p1, p2, p3)
            by_angle = int(math.ceil((a1 + a2) / math.pi * 8.0))

            samples = max(min_s, by_distance, by_angle)
            samples = min(max_s, samples)

            for j in range(samples):
                # j=0 incluye p1; j=samples no se incluye porque será p2 del siguiente segmento.
                u = j / float(samples)
                p = catmull_rom_centripetal_point(p0, p1, p2, p3, u, alpha=alpha)
                if not out or (p - out[-1]).length > 0.01:
                    out.append(p)

        # Para curva cíclica no duplicamos el primer punto al final.
        if len(out) > 2 and (out[0] - out[-1]).length <= 0.01:
            out.pop()
        return out

    # Ruta abierta: duplicamos extremos virtuales para que la curva arranque y termine estable.
    padded = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        chord = (p2 - p1).length
        samples = max(min_s, int(math.ceil(chord / spacing)))
        samples = min(max_s, samples)
        for j in range(samples):
            u = j / float(samples)
            p = catmull_rom_centripetal_point(p0, p1, p2, p3, u, alpha=alpha)
            if not out or (p - out[-1]).length > 0.01:
                out.append(p)
    if not out or (pts[-1] - out[-1]).length > 0.01:
        out.append(pts[-1].copy())
    return out





def _frame_sparse_catmull_controls(points, target_spacing=FRAME_CATMULL_CONTROL_SPACING_MM_FIXED,
                                    keep_turn_deg=FRAME_CATMULL_KEEP_TURN_DEG):
    """Reduce a dense geodesic polyline to a clean Catmull control polygon.

    The raw surface shortest path is intentionally dense and inherits small
    direction changes from the IOS triangulation.  Those samples are excellent
    for finding the route, but poor as spline controls.  This helper keeps
    endpoints exactly, spaces ordinary controls by arc length, and only inserts
    an early control when the route contains a clinically meaningful turn.
    """
    pts = _remove_near_duplicate_points(points, epsilon=0.01, closed=False)
    if len(pts) <= 2:
        return pts

    spacing = max(0.60, float(target_spacing))
    min_sep = spacing * max(0.20, min(0.80, float(FRAME_CATMULL_MIN_CONTROL_SEPARATION_FACTOR)))
    keep_turn = math.radians(max(5.0, float(keep_turn_deg)))

    out = [pts[0].copy()]
    accumulated = 0.0
    for i in range(1, len(pts) - 1):
        accumulated += float((pts[i] - pts[i - 1]).length)
        turn = _angle_between_segments(pts[i - 1], pts[i], pts[i + 1])
        separated = (pts[i] - out[-1]).length >= min_sep
        if separated and (accumulated >= spacing or turn >= keep_turn):
            out.append(pts[i].copy())
            accumulated = 0.0

    if (pts[-1] - out[-1]).length > 0.01:
        out.append(pts[-1].copy())
    else:
        out[-1] = pts[-1].copy()
    return out


def _frame_project_smoothed_catmull_to_surface(cache, smoothed_points, reference_points):
    """Project Catmull samples back to the passive surface without large jumps.

    The sparse control polygon removes triangulation chatter, while Catmull-Rom
    can naturally bow a few tenths of a millimetre away from the mesh between
    controls.  Every evaluated sample is therefore returned to the IOS surface.
    A tether to the original shortest path prevents a nearest-surface query from
    hopping to another close sheet in an embrasure/contact region.
    """
    smooth = [Vector(p) for p in smoothed_points]
    refs = [Vector(p) for p in reference_points]
    if not smooth or not refs:
        return smooth

    ref_np = np.asarray([tuple(p) for p in refs], dtype=np.float64)
    tether = max(0.20, float(FRAME_CATMULL_ROUTE_TETHER_MM))
    max_proj = max(0.20, float(FRAME_CATMULL_MAX_SURFACE_PROJECTION_MM))
    out = []

    for p in smooth:
        q = np.asarray(tuple(p), dtype=np.float64)
        delta = ref_np - q[None, :]
        nearest_ref_index = int(np.argmin(np.einsum('ij,ij->i', delta, delta)))
        nearest_ref = refs[nearest_ref_index]

        projection = _frame_surface_projection(cache, p, max_distance_mm=max_proj)
        if projection is not None:
            candidate = Vector(projection['point'])
            # Keep the smoothing inside a narrow tube around the true geodesic.
            if (candidate - nearest_ref).length <= tether:
                chosen = candidate
            else:
                chosen = nearest_ref.copy()
        else:
            chosen = nearest_ref.copy()

        if not out or (chosen - out[-1]).length > 0.01:
            out.append(chosen)

    if len(out) > 2 and (out[0] - out[-1]).length <= 0.01:
        out.pop()
    return out


def _frame_clean_catmull_surface_loop(cache, dense_surface_points, sparse_controls):
    """Create the final clean surface-following loop from sparse Catmull controls."""
    controls = _remove_near_duplicate_points(sparse_controls, epsilon=0.02, closed=True)
    if len(controls) < 4:
        return [Vector(p) for p in dense_surface_points], controls

    spline = build_catmull_rom_frame_path(
        controls,
        closed=True,
        alpha=FRAME_CATMULL_ALPHA_FIXED,
        max_spacing=FRAME_CATMULL_SAMPLE_SPACING_MM_FIXED,
        min_samples_per_segment=3,
        max_samples_per_segment=24,
    )
    if len(spline) < 4:
        return [Vector(p) for p in dense_surface_points], controls

    projected = _frame_project_smoothed_catmull_to_surface(
        cache, spline, dense_surface_points)
    if len(projected) < 4:
        return [Vector(p) for p in dense_surface_points], controls
    return projected, controls


def _frame_surface_cache_key(obj):
    if not _valid_obj(obj) or getattr(obj, 'type', None) != 'MESH':
        return ''
    try:
        return f'{obj.name}|{_workflow_object_signature(obj)}'
    except Exception:
        data = getattr(obj, 'data', None)
        return f'{getattr(obj, "name", "")}|{len(getattr(data, "vertices", []))}|{len(getattr(data, "edges", []))}|{_workflow_matrix_signature(obj)}'


def _build_frame_surface_graph_cache(context, surface_obj):
    """Build a compact mesh-edge graph for true geodesic routing.

    v8.4.3 deliberately does not build a Python list-of-lists adjacency graph
    and does not build a BVH for every frame.  Both were large bottlenecks on
    dense IOS meshes.  Directed edge arrays are sorted once into CSR form and
    reused by every segment of the contour.
    """
    if not _valid_obj(surface_obj) or surface_obj.type != 'MESH':
        return None, False, 'invalid surface'
    key = _frame_surface_cache_key(surface_obj)
    cached = _FRAME_SURFACE_GRAPH_CACHE.get(key)
    if cached is not None:
        return cached, True, ''

    depsgraph = context.evaluated_depsgraph_get()
    evaluated = None
    temp_mesh = None
    try:
        evaluated = surface_obj.evaluated_get(depsgraph)
        try:
            temp_mesh = evaluated.to_mesh(
                preserve_all_data_layers=False, depsgraph=depsgraph)
        except TypeError:
            temp_mesh = evaluated.to_mesh()
        if temp_mesh is None or len(temp_mesh.vertices) < 4 or len(temp_mesh.edges) < 3:
            return None, False, 'surface mesh is empty'

        vertex_count = len(temp_mesh.vertices)
        coords = np.empty(vertex_count * 3, dtype=np.float64)
        normals = np.empty(vertex_count * 3, dtype=np.float64)
        temp_mesh.vertices.foreach_get('co', coords)
        temp_mesh.vertices.foreach_get('normal', normals)
        coords = coords.reshape((-1, 3))
        normals = normals.reshape((-1, 3))

        world_matrix = evaluated.matrix_world.copy()
        basis = np.array(
            [[float(world_matrix[r][c]) for c in range(3)] for r in range(3)],
            dtype=np.float64)
        translation = np.array(
            [float(world_matrix.translation[i]) for i in range(3)],
            dtype=np.float64)
        world_coords = coords @ basis.T + translation

        try:
            normal_matrix_bl = world_matrix.to_3x3().inverted().transposed()
        except Exception:
            normal_matrix_bl = world_matrix.to_3x3()
        normal_matrix = np.array(
            [[float(normal_matrix_bl[r][c]) for c in range(3)] for r in range(3)],
            dtype=np.float64)
        world_normals = normals @ normal_matrix.T
        normal_lengths = np.linalg.norm(world_normals, axis=1)
        normal_lengths[normal_lengths < 1.0e-12] = 1.0
        world_normals /= normal_lengths[:, None]

        # Triangles are required by the continuous corridor engine. Keep them
        # in evaluated-mesh vertex indexing so they share the same world_coords.
        try:
            temp_mesh.calc_loop_triangles()
            triangle_count = len(temp_mesh.loop_triangles)
            triangle_indices = np.empty(triangle_count * 3, dtype=np.int32)
            triangle_polygons = np.empty(triangle_count, dtype=np.int32)
            try:
                temp_mesh.loop_triangles.foreach_get('vertices', triangle_indices)
                temp_mesh.loop_triangles.foreach_get('polygon_index', triangle_polygons)
                triangle_indices = triangle_indices.reshape((-1, 3))
            except Exception:
                triangle_indices = np.asarray(
                    [tuple(int(v) for v in tri.vertices) for tri in temp_mesh.loop_triangles],
                    dtype=np.int32)
                triangle_polygons = np.asarray(
                    [int(tri.polygon_index) for tri in temp_mesh.loop_triangles],
                    dtype=np.int32)
        except Exception:
            triangle_indices = np.empty((0, 3), dtype=np.int32)
            triangle_polygons = np.empty((0,), dtype=np.int32)

        poly_to_triangles = {}
        for tri_index, polygon_index in enumerate(triangle_polygons):
            poly_to_triangles.setdefault(int(polygon_index), []).append(int(tri_index))

        edge_indices = np.empty(len(temp_mesh.edges) * 2, dtype=np.int32)
        temp_mesh.edges.foreach_get('vertices', edge_indices)
        edge_indices = edge_indices.reshape((-1, 2))
        valid = edge_indices[:, 0] != edge_indices[:, 1]
        edge_indices = edge_indices[valid]
        if len(edge_indices) < 3:
            return None, False, 'surface has no usable edges'
        delta = world_coords[edge_indices[:, 1]] - world_coords[edge_indices[:, 0]]
        edge_lengths = np.linalg.norm(delta, axis=1)
        valid_length = edge_lengths > 1.0e-8
        edge_indices = edge_indices[valid_length]
        edge_lengths = edge_lengths[valid_length]

        # CSR directed graph: two directed records per undirected mesh edge.
        src = np.concatenate((edge_indices[:, 0], edge_indices[:, 1])).astype(np.int32, copy=False)
        dst = np.concatenate((edge_indices[:, 1], edge_indices[:, 0])).astype(np.int32, copy=False)
        weights = np.concatenate((edge_lengths, edge_lengths)).astype(np.float64, copy=False)
        order = np.argsort(src, kind='stable')
        src = src[order]
        dst = dst[order]
        weights = weights[order]
        offsets = np.searchsorted(
            src, np.arange(vertex_count + 1, dtype=np.int32), side='left').astype(np.int64)

        kd = KDTree(vertex_count)
        for index, coordinate in enumerate(world_coords):
            kd.insert(
                (float(coordinate[0]), float(coordinate[1]), float(coordinate[2])),
                index)
        kd.balance()

        cache = {
            'key': key,
            'surface_name': surface_obj.name,
            'coords': world_coords,
            'normals': world_normals,
            'csr_src': src,
            'csr_dst': dst,
            'csr_weights': weights,
            'csr_offsets': offsets,
            'kd': kd,
            'vertex_count': int(vertex_count),
            'edge_count': int(len(edge_indices)),
            'triangles': triangle_indices,
            'triangle_polygons': triangle_polygons,
            'poly_to_triangles': poly_to_triangles,
            'heat_solver': None,
            'heat_solver_failed': False,
        }
        _FRAME_SURFACE_GRAPH_CACHE[key] = cache
        while len(_FRAME_SURFACE_GRAPH_CACHE) > FRAME_SURFACE_MAX_CACHE_ENTRIES:
            oldest_key = next(iter(_FRAME_SURFACE_GRAPH_CACHE))
            if oldest_key == key and len(_FRAME_SURFACE_GRAPH_CACHE) == 1:
                break
            _FRAME_SURFACE_GRAPH_CACHE.pop(oldest_key, None)
        return cache, False, ''
    except Exception as exc:
        return None, False, f'could not build geodesic graph: {exc}'
    finally:
        if evaluated is not None and temp_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _frame_nearest_vertex(cache, point):
    try:
        _co, index, distance = cache['kd'].find(Vector(point))
        return int(index), float(distance)
    except Exception:
        return -1, float('inf')


def _frame_vertices_within_surface_radius(cache, start_index, radius_mm,
                                          max_candidates=FRAME_ANCHOR_SAFE_SNAP_MAX_CANDIDATES):
    """Return nearby graph vertices ordered by geodesic edge distance.

    This deliberately walks the mesh CSR graph. KD/Euclidean range search could
    jump across a thin tooth, embrasure or concavity to a physically different
    surface patch.
    """
    start_index = int(start_index)
    radius = max(0.0, float(radius_mm))
    if start_index < 0 or radius <= 0.0:
        return []
    offsets = cache['csr_offsets']
    dst = cache['csr_dst']
    weights = cache['csr_weights']
    best = {start_index: 0.0}
    heap = [(0.0, start_index)]
    out = []
    limit = max(32, int(max_candidates))
    while heap and len(out) < limit:
        distance, current = heapq.heappop(heap)
        if distance != best.get(current):
            continue
        if distance > radius + 1.0e-9:
            break
        out.append((int(current), float(distance)))
        begin = int(offsets[current])
        end = int(offsets[current + 1])
        for pos in range(begin, end):
            neighbour = int(dst[pos])
            candidate = float(distance) + float(weights[pos])
            if candidate > radius + 1.0e-9:
                continue
            if candidate + 1.0e-12 < best.get(neighbour, float('inf')):
                best[neighbour] = candidate
                heapq.heappush(heap, (candidate, neighbour))
    return out


def _frame_anchor_width_profile(cache, vertex_index, tangent_hint, frame_radius_mm):
    """Endpoint width test using the same 75/25 support policy."""
    vertex_index = int(vertex_index)
    radius = max(0.05, float(frame_radius_mm))
    required_width = radius * 2.0
    center = Vector(cache['coords'][vertex_index])
    normal = _normalized_or_fallback(Vector(cache['normals'][vertex_index]), (0.0, 0.0, 1.0))
    tangent = Vector(tangent_hint)
    tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        tangent = Vector((1.0, 0.0, 0.0))
        if abs(tangent.dot(normal)) > 0.85:
            tangent = Vector((0.0, 1.0, 0.0))
        tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        return {'ok': False, 'min_width_mm': 0.0, 'required_width_mm': required_width,
                'min_retained_ratio': 0.0, 'reason': 'degenerate anchor tangent'}
    tangent.normalize()
    lateral = normal.cross(tangent)
    if lateral.length < 1.0e-8:
        return {'ok': False, 'min_width_mm': 0.0, 'required_width_mm': required_width,
                'min_retained_ratio': 0.0, 'reason': 'degenerate anchor lateral'}
    lateral.normalize()
    rise_tol = max(
        FRAME_WIDTH_SURFACE_RISE_MIN_TOL_MM,
        min(FRAME_WIDTH_SURFACE_RISE_MAX_TOL_MM,
            radius * FRAME_WIDTH_SURFACE_RISE_RADIUS_FACTOR),
    )
    local_half = radius
    checked = 0
    worst_rise = 0.0
    hard_failure = False
    tolerated_outer = False
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
                    hard_failure = True
                else:
                    tolerated_outer = True
                break
        local_half = min(local_half, side_available)
    retained = _frame_width_retained_ratio(local_half, radius)
    ok = (not hard_failure and retained + 1.0e-9 >= FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO)
    return {
        'ok': bool(ok),
        'min_width_mm': float(local_half * 2.0),
        'required_width_mm': float(required_width),
        'min_retained_ratio': float(retained),
        'allowed_outer_embed_ratio': float(FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO),
        'surface_rise_tolerance_mm': float(rise_tol),
        'worst_surface_rise_mm': float(worst_rise),
        'samples': int(checked),
        'tolerated_outer_embedding': bool(tolerated_outer and ok),
        'reason': '' if ok else 'anchor central 75% support band is too narrow',
    }


def _frame_resolve_safe_anchor(cache, source_point, previous_point, next_point,
                               frame_radius_mm, used_indices=None):
    """Resolve a semantic contour click to the closest width-valid surface vertex."""
    source = Vector(source_point)
    previous = Vector(previous_point)
    next_point = Vector(next_point)
    used_indices = set(int(v) for v in (used_indices or ()))

    nearest_index, nearest_euclidean = _frame_nearest_vertex(cache, source)
    if nearest_index < 0:
        return None, {
            'reason': 'anchor could not be snapped to the surface graph',
            'requested': [float(v) for v in source],
        }

    tangent_hint = next_point - previous
    nearest_profile = _frame_anchor_width_profile(
        cache, nearest_index, tangent_hint, frame_radius_mm)
    if nearest_index not in used_indices and bool(nearest_profile.get('ok')):
        resolved = Vector(cache['coords'][nearest_index])
        return int(nearest_index), {
            'reason': '',
            'relocated': False,
            'surface_geodesic_shift_mm': 0.0,
            'euclidean_shift_mm': float((resolved - source).length),
            'initial_snap_mm': float(nearest_euclidean),
            'requested': [float(v) for v in source],
            'resolved': [float(v) for v in resolved],
            'width_min_mm': float(nearest_profile.get('min_width_mm', 0.0)),
            'width_required_mm': float(nearest_profile.get('required_width_mm', frame_radius_mm * 2.0)),
        }

    search_radius = max(
        FRAME_ANCHOR_SAFE_SNAP_MIN_MM,
        min(
            FRAME_ANCHOR_SAFE_SNAP_MAX_MM,
            float(frame_radius_mm) * FRAME_ANCHOR_SAFE_SNAP_RADIUS_FACTOR + 1.0,
        ),
    )
    candidates = _frame_vertices_within_surface_radius(
        cache, nearest_index, search_radius)
    best = None
    for candidate_index, surface_distance in candidates:
        candidate_index = int(candidate_index)
        if candidate_index in used_indices:
            continue
        profile = _frame_anchor_width_profile(
            cache, candidate_index, tangent_hint, frame_radius_mm)
        if not bool(profile.get('ok')):
            continue
        resolved = Vector(cache['coords'][candidate_index])
        euclidean_shift = float((resolved - source).length)
        score = (
            float(surface_distance),
            euclidean_shift,
            -float(profile.get('min_width_mm', 0.0)),
        )
        if best is None or score < best[0]:
            best = (score, candidate_index, resolved, profile, surface_distance)

    if best is None:
        return None, {
            'reason': (
                f'no full-diameter surface position was found within '
                f'{search_radius:.2f} mm geodesically from this contour anchor'
            ),
            'relocated': False,
            'search_radius_mm': float(search_radius),
            'initial_snap_mm': float(nearest_euclidean),
            'requested': [float(v) for v in source],
            'initial_width_min_mm': float(nearest_profile.get('min_width_mm', 0.0)),
            'width_required_mm': float(nearest_profile.get(
                'required_width_mm', frame_radius_mm * 2.0)),
        }

    _score, candidate_index, resolved, profile, surface_distance = best
    return int(candidate_index), {
        'reason': '',
        'relocated': True,
        'search_radius_mm': float(search_radius),
        'surface_geodesic_shift_mm': float(surface_distance),
        'euclidean_shift_mm': float((resolved - source).length),
        'initial_snap_mm': float(nearest_euclidean),
        'requested': [float(v) for v in source],
        'resolved': [float(v) for v in resolved],
        'width_min_mm': float(profile.get('min_width_mm', 0.0)),
        'width_required_mm': float(profile.get(
            'required_width_mm', frame_radius_mm * 2.0)),
    }


def _frame_np_distance(a, b):
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    dz = float(a[2]) - float(b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _frame_local_vertex_mask(cache, start_index, goal_index, padding_mm):
    """Bounding corridor used only to limit work, never as route cost."""
    coords = cache['coords']
    a = coords[int(start_index)]
    b = coords[int(goal_index)]
    padding = max(0.0, float(padding_mm))
    minimum = np.minimum(a, b) - padding
    maximum = np.maximum(a, b) + padding
    mask = np.all((coords >= minimum) & (coords <= maximum), axis=1)
    mask[int(start_index)] = True
    mask[int(goal_index)] = True
    return mask


def _frame_bidirectional_dijkstra(cache, start_index, goal_index,
                                  allowed_mask=None,
                                  max_expansions=FRAME_SURFACE_MAX_EXPANSIONS):
    """Shortest path by accumulated physical mesh-edge length only.

    This is the graph-geodesic approximation on the evaluated IOS/passive
    surface.  There is deliberately no Euclidean A* heuristic and no normal
    penalty that can bias the clinical path away from the shortest surface
    route.
    """
    start_index = int(start_index)
    goal_index = int(goal_index)
    if start_index < 0 or goal_index < 0:
        return None, {'reason': 'invalid endpoints', 'expanded': 0}
    if start_index == goal_index:
        return [start_index], {'reason': '', 'expanded': 0, 'cost': 0.0}

    offsets = cache['csr_offsets']
    dst = cache['csr_dst']
    weights = cache['csr_weights']
    if allowed_mask is not None:
        if not bool(allowed_mask[start_index]) or not bool(allowed_mask[goal_index]):
            return None, {'reason': 'endpoints outside local corridor', 'expanded': 0}

    dist_f = {start_index: 0.0}
    dist_b = {goal_index: 0.0}
    parent_f = {}
    parent_b = {}
    heap_f = [(0.0, start_index)]
    heap_b = [(0.0, goal_index)]
    settled_f = set()
    settled_b = set()
    best = float('inf')
    meeting = None
    expanded = 0

    def relax_one(heap, distances, parents, settled, other_distances, forward=True):
        nonlocal best, meeting, expanded
        while heap:
            current_dist, current = heapq.heappop(heap)
            if current in settled:
                continue
            if current_dist != distances.get(current):
                continue
            settled.add(current)
            expanded += 1
            other = other_distances.get(current)
            if other is not None and current_dist + other < best:
                best = current_dist + other
                meeting = current
            begin = int(offsets[current])
            end = int(offsets[current + 1])
            for edge_pos in range(begin, end):
                neighbour = int(dst[edge_pos])
                if allowed_mask is not None and not bool(allowed_mask[neighbour]):
                    continue
                candidate = current_dist + float(weights[edge_pos])
                if candidate + 1.0e-12 < distances.get(neighbour, float('inf')):
                    distances[neighbour] = candidate
                    # parent_f: predecessor from start; parent_b: next node toward goal.
                    parents[neighbour] = current
                    heapq.heappush(heap, (candidate, neighbour))
                other_neighbour = other_distances.get(neighbour)
                if other_neighbour is not None and candidate + other_neighbour < best:
                    best = candidate + other_neighbour
                    meeting = neighbour
            return current_dist
        return float('inf')

    while heap_f and heap_b and expanded < int(max_expansions):
        min_f = heap_f[0][0]
        min_b = heap_b[0][0]
        if meeting is not None and min_f + min_b >= best - 1.0e-10:
            break
        if min_f <= min_b:
            relax_one(heap_f, dist_f, parent_f, settled_f, dist_b, True)
        else:
            relax_one(heap_b, dist_b, parent_b, settled_b, dist_f, False)

    if meeting is None:
        return None, {
            'reason': 'geodesic route not found within search limit',
            'expanded': int(expanded),
        }

    left = [meeting]
    current = meeting
    while current != start_index:
        current = parent_f.get(current)
        if current is None:
            return None, {'reason': 'forward geodesic reconstruction failed', 'expanded': int(expanded)}
        left.append(current)
    left.reverse()

    right = []
    current = meeting
    while current != goal_index:
        current = parent_b.get(current)
        if current is None:
            return None, {'reason': 'backward geodesic reconstruction failed', 'expanded': int(expanded)}
        right.append(current)
    route = left + right
    return route, {
        'reason': '',
        'expanded': int(expanded),
        'cost': float(best),
    }


def _frame_scipy_dijkstra(cache, start_index, goal_index, allowed_mask=None):
    """Exact shortest path on the mesh-edge CSR graph using SciPy C code.

    Euclidean coordinates are never used as path cost or heuristic here.  The
    only weights are physical lengths of actual evaluated mesh edges.  SciPy is
    an acceleration backend, not a different geometric model.
    """
    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra as scipy_dijkstra
    except Exception as exc:
        return None, {
            'reason': f'scipy unavailable: {exc}',
            'expanded': 0,
            'backend': 'PYTHON_FALLBACK_REQUIRED',
        }

    start_index = int(start_index)
    goal_index = int(goal_index)
    vertex_count = int(cache.get('vertex_count', 0))
    if start_index < 0 or goal_index < 0 or vertex_count <= 0:
        return None, {'reason': 'invalid endpoints', 'expanded': 0, 'backend': 'SCIPY_CSR'}
    if start_index == goal_index:
        return [start_index], {
            'reason': '', 'expanded': 1, 'cost': 0.0, 'backend': 'SCIPY_CSR'}

    graph = cache.get('scipy_csr_graph')
    if graph is None:
        graph = csr_matrix(
            (cache['csr_weights'], cache['csr_dst'], cache['csr_offsets']),
            shape=(vertex_count, vertex_count),
            copy=False,
        )
        cache['scipy_csr_graph'] = graph

    global_indices = None
    start_local = start_index
    goal_local = goal_index
    local_graph = graph
    if allowed_mask is not None:
        if not bool(allowed_mask[start_index]) or not bool(allowed_mask[goal_index]):
            return None, {
                'reason': 'endpoints outside local corridor',
                'expanded': 0,
                'backend': 'SCIPY_CSR',
            }
        global_indices = np.flatnonzero(allowed_mask).astype(np.int32, copy=False)
        if global_indices.size <= 1:
            return None, {
                'reason': 'local corridor is empty',
                'expanded': int(global_indices.size),
                'backend': 'SCIPY_CSR',
            }
        start_pos = np.searchsorted(global_indices, start_index)
        goal_pos = np.searchsorted(global_indices, goal_index)
        if (start_pos >= global_indices.size or goal_pos >= global_indices.size
                or int(global_indices[start_pos]) != start_index
                or int(global_indices[goal_pos]) != goal_index):
            return None, {
                'reason': 'local endpoint remap failed',
                'expanded': 0,
                'backend': 'SCIPY_CSR',
            }
        start_local = int(start_pos)
        goal_local = int(goal_pos)
        # CSR slicing is compiled and dramatically cheaper than constructing
        # Python adjacency lists for every contour segment.
        local_graph = graph[global_indices][:, global_indices].tocsr()

    try:
        distances, predecessors = scipy_dijkstra(
            local_graph,
            directed=True,
            indices=int(start_local),
            return_predecessors=True,
        )
    except Exception as exc:
        return None, {
            'reason': f'scipy dijkstra failed: {exc}',
            'expanded': 0,
            'backend': 'SCIPY_CSR',
        }

    goal_distance = float(distances[int(goal_local)])
    finite_count = int(np.count_nonzero(np.isfinite(distances)))
    if not np.isfinite(goal_distance):
        return None, {
            'reason': 'no connected geodesic route inside corridor',
            'expanded': finite_count,
            'backend': 'SCIPY_CSR',
        }

    route_local = [int(goal_local)]
    current = int(goal_local)
    guard = 0
    max_guard = int(local_graph.shape[0]) + 2
    while current != int(start_local):
        previous = int(predecessors[current])
        if previous < 0 or previous == current:
            return None, {
                'reason': 'scipy geodesic reconstruction failed',
                'expanded': finite_count,
                'backend': 'SCIPY_CSR',
            }
        route_local.append(previous)
        current = previous
        guard += 1
        if guard > max_guard:
            return None, {
                'reason': 'scipy geodesic predecessor loop',
                'expanded': finite_count,
                'backend': 'SCIPY_CSR',
            }
    route_local.reverse()
    if global_indices is None:
        route = route_local
    else:
        route = [int(global_indices[index]) for index in route_local]
    return route, {
        'reason': '',
        'expanded': finite_count,
        'cost': goal_distance,
        'backend': 'SCIPY_CSR',
    }


def _frame_exact_dijkstra(cache, start_index, goal_index, allowed_mask=None,
                          max_expansions=FRAME_SURFACE_MAX_EXPANSIONS):
    """Use compiled CSR Dijkstra first; retain an exact Python fallback."""
    route, stats = _frame_scipy_dijkstra(
        cache, start_index, goal_index, allowed_mask=allowed_mask)
    if route:
        return route, stats
    scipy_reason = str(stats.get('reason', '') or '')
    # A disconnected local corridor is a valid search result: do not spend time
    # repeating the same corridor in Python. The caller will expand it.
    if scipy_reason in {
            'no connected geodesic route inside corridor',
            'endpoints outside local corridor',
            'local corridor is empty'}:
        return None, stats
    route, fallback_stats = _frame_bidirectional_dijkstra(
        cache, start_index, goal_index,
        allowed_mask=allowed_mask,
        max_expansions=max_expansions,
    )
    fallback_stats['backend'] = 'PYTHON_BIDIRECTIONAL_DIJKSTRA'
    if scipy_reason:
        fallback_stats['scipy_reason'] = scipy_reason
    return route, fallback_stats


def _frame_geodesic_surface_route(cache, start_index, goal_index,
                                  max_expansions=FRAME_SURFACE_MAX_EXPANSIONS,
                                  hard_allowed_mask=None):
    """Adaptive exact Dijkstra constrained to the dental surface.

    ``hard_allowed_mask`` is reserved for clinical exclusions such as a frame
    width bottleneck. It changes which vertices are legal, never the edge cost:
    every accepted route is still a true graph geodesic measured only in mm.
    """
    coords = cache['coords']
    chord = _frame_np_distance(coords[int(start_index)], coords[int(goal_index)])
    paddings = []
    for padding in (
        max(FRAME_SURFACE_LOCAL_PADDING_MIN_MM,
            chord * FRAME_SURFACE_LOCAL_PADDING_FACTOR),
        max(FRAME_SURFACE_LOCAL_PADDING_MIN_MM * 1.8, chord * 1.35),
        max(FRAME_SURFACE_LOCAL_PADDING_MIN_MM * 3.0, chord * 2.25),
    ):
        if not paddings or abs(padding - paddings[-1]) > 0.25:
            paddings.append(float(padding))

    clinical_mask = None
    if hard_allowed_mask is not None:
        clinical_mask = np.asarray(hard_allowed_mask, dtype=bool)
        if clinical_mask.shape[0] != int(cache.get('vertex_count', 0)):
            return None, {'reason': 'invalid clinical width mask', 'expanded': 0, 'backend': 'NONE'}

    total_expanded = 0
    for attempt, padding in enumerate(paddings, start=1):
        allowed = _frame_local_vertex_mask(cache, start_index, goal_index, padding)
        if clinical_mask is not None:
            allowed &= clinical_mask
            allowed[int(start_index)] = True
            allowed[int(goal_index)] = True
        route, stats = _frame_exact_dijkstra(
            cache, start_index, goal_index,
            allowed_mask=allowed,
            max_expansions=max(12000, int(max_expansions // 2)),
        )
        total_expanded += int(stats.get('expanded', 0))
        if route:
            stats.update({
                'expanded': int(total_expanded),
                'local_padding_mm': float(padding),
                'local_vertices': int(np.count_nonzero(allowed)),
                'attempt': int(attempt),
            })
            return route, stats

    # Never switch to a Euclidean spline. The last chance is still Dijkstra,
    # now on the complete surface graph while preserving clinical exclusions.
    allowed = clinical_mask.copy() if clinical_mask is not None else None
    if allowed is not None:
        allowed[int(start_index)] = True
        allowed[int(goal_index)] = True
    route, stats = _frame_exact_dijkstra(
        cache, start_index, goal_index,
        allowed_mask=allowed,
        max_expansions=max_expansions,
    )
    total_expanded += int(stats.get('expanded', 0))
    stats.update({
        'expanded': int(total_expanded),
        'local_padding_mm': -1.0,
        'local_vertices': int(np.count_nonzero(allowed)) if allowed is not None else int(cache.get('vertex_count', 0)),
        'attempt': int(len(paddings) + 1),
    })
    return route, stats



def _frame_width_surface_bvh(context, surface_obj, cache):
    """Lazy BVH used only by the hard full-width gate."""
    tree = cache.get('width_bvh')
    matrix = cache.get('width_bvh_matrix')
    inverse = cache.get('width_bvh_inverse')
    if tree is not None and matrix is not None and inverse is not None:
        return tree, matrix, inverse, ''
    if not _valid_obj(surface_obj) or surface_obj.type != 'MESH':
        return None, None, None, 'invalid width-validation surface'
    try:
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = surface_obj.evaluated_get(depsgraph)
        matrix = evaluated.matrix_world.copy()
        inverse = matrix.inverted()
        tree = BVHTree.FromObject(evaluated, depsgraph)
        if tree is None:
            return None, None, None, 'could not build width-validation BVH'
        cache['width_bvh'] = tree
        cache['width_bvh_matrix'] = matrix
        cache['width_bvh_inverse'] = inverse
        return tree, matrix, inverse, ''
    except Exception as exc:
        return None, None, None, f'could not build width-validation BVH: {exc}'



def _frame_barycentric(point, a, b, c):
    p = np.asarray(point, dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    c = np.asarray(c, dtype=np.float64)
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = float(np.dot(v0, v0))
    d01 = float(np.dot(v0, v1))
    d11 = float(np.dot(v1, v1))
    d20 = float(np.dot(v2, v0))
    d21 = float(np.dot(v2, v1))
    den = d00 * d11 - d01 * d01
    if abs(den) < 1.0e-16:
        return np.array([1.0, 0.0, 0.0], dtype=np.float64)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    u = 1.0 - v - w
    return np.array([u, v, w], dtype=np.float64)


def _frame_surface_projection(cache, point_world, max_distance_mm=None):
    """Project a point to the evaluated surface without snapping it to a vertex.

    Returns an exact face/barycentric anchor whenever triangle data are available.
    The routing graph later connects this virtual anchor to all vertices of that
    triangle, so a contour click is no longer forced through one triangulation
    vertex.
    """
    tree = cache.get('width_bvh')
    matrix = cache.get('width_bvh_matrix')
    inverse = cache.get('width_bvh_inverse')
    if tree is None or matrix is None or inverse is None:
        return None
    try:
        local_query = inverse @ Vector(point_world)
        if max_distance_mm is None:
            result = tree.find_nearest(local_query)
        else:
            try:
                result = tree.find_nearest(local_query, float(max_distance_mm) * 2.5)
            except TypeError:
                result = tree.find_nearest(local_query)
        if not result or result[0] is None:
            return None
        loc_local, normal_local, polygon_index, _distance = result
        loc_world = matrix @ loc_local
        normal_world = matrix.to_3x3() @ normal_local
        if normal_world.length < 1.0e-10:
            normal_world = Vector((0.0, 0.0, 1.0))
        else:
            normal_world.normalize()
        distance_world = float((loc_world - Vector(point_world)).length)
        if max_distance_mm is not None and distance_world > float(max_distance_mm):
            return None

        triangles = cache.get('triangles')
        poly_map = cache.get('poly_to_triangles') or {}
        tri_index = -1
        bary = None
        tri_vertices = ()
        candidates = poly_map.get(int(polygon_index), []) if polygon_index is not None else []
        if triangles is not None and len(triangles) and candidates:
            best = None
            p = np.asarray(tuple(loc_world), dtype=np.float64)
            coords = cache['coords']
            for candidate in candidates:
                tv = np.asarray(triangles[int(candidate)], dtype=np.int32)
                bc = _frame_barycentric(p, coords[tv[0]], coords[tv[1]], coords[tv[2]])
                violation = float(np.sum(np.maximum(-bc, 0.0)) + np.sum(np.maximum(bc - 1.0, 0.0)))
                if best is None or violation < best[0]:
                    best = (violation, int(candidate), bc, tuple(int(v) for v in tv))
            if best is not None:
                _violation, tri_index, bary, tri_vertices = best

        if not tri_vertices:
            nearest, _snap = _frame_nearest_vertex(cache, loc_world)
            if nearest >= 0:
                tri_vertices = (int(nearest),)
                bary = np.array([1.0], dtype=np.float64)

        return {
            'point': loc_world.copy(),
            'normal': normal_world.copy(),
            'polygon_index': int(polygon_index) if polygon_index is not None else -1,
            'triangle_index': int(tri_index),
            'triangle_vertices': tuple(tri_vertices),
            'barycentric': [float(v) for v in np.asarray(bary).ravel()] if bary is not None else [],
            'distance_mm': float(distance_world),
        }
    except Exception:
        return None


def _frame_ray_surface_height(cache, query_world, center_world, normal_world, tangent_world,
                              max_scan_mm):
    """Height of the same surface sheet along the local normal line.

    Unlike nearest-point queries, a normal-line ray cannot jump laterally across
    an interproximal contact. No hit means free tube space, not a failure.
    """
    tree = cache.get('width_bvh')
    matrix = cache.get('width_bvh_matrix')
    inverse = cache.get('width_bvh_inverse')
    if tree is None or matrix is None or inverse is None:
        return None
    normal = _normalized_or_fallback(Vector(normal_world), (0.0, 0.0, 1.0))
    tangent = _normalized_or_fallback(Vector(tangent_world), (1.0, 0.0, 0.0))
    scan = max(0.5, float(max_scan_mm))
    candidates = []
    for side in (1.0, -1.0):
        origin_world = Vector(query_world) + normal * (side * scan)
        direction_world = normal * (-side)
        origin_local = inverse @ origin_world
        direction_local = inverse.to_3x3() @ direction_world
        if direction_local.length < 1.0e-10:
            continue
        direction_local.normalize()
        try:
            hit = tree.ray_cast(origin_local, direction_local, scan * 6.0)
        except TypeError:
            hit = tree.ray_cast(origin_local, direction_local)
        if not hit or hit[0] is None:
            continue
        loc_local, hit_normal_local, _poly, _dist = hit
        loc_world = matrix @ loc_local
        hit_normal_world = matrix.to_3x3() @ hit_normal_local
        if hit_normal_world.length > 1.0e-10:
            hit_normal_world.normalize()
        # Reject an obviously different surface sheet with opposing orientation.
        if hit_normal_world.length > 1.0e-10 and abs(float(hit_normal_world.dot(normal))) < 0.20:
            continue
        axial_slip = abs(float((loc_world - Vector(query_world)).dot(tangent)))
        if axial_slip > 0.40:
            continue
        rise = float((loc_world - Vector(center_world)).dot(normal))
        offset_from_query = abs(float((loc_world - Vector(query_world)).dot(normal)))
        candidates.append((offset_from_query, rise))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return float(candidates[0][1])


def _frame_point_support_profile(cache, point_world, normal_world, tangent_hint, frame_radius_mm):
    """Cross-section retention of the tube at one continuous surface point."""
    radius = max(0.05, float(frame_radius_mm))
    center = Vector(point_world)
    normal = _normalized_or_fallback(Vector(normal_world), (0.0, 0.0, 1.0))
    tangent = Vector(tangent_hint)
    tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        tangent = Vector((1.0, 0.0, 0.0))
        if abs(tangent.dot(normal)) > 0.85:
            tangent = Vector((0.0, 1.0, 0.0))
        tangent -= normal * tangent.dot(normal)
    if tangent.length < 1.0e-8:
        return {'ok': False, 'min_retained_ratio': 0.0, 'min_width_mm': 0.0,
                'required_width_mm': radius * 2.0, 'samples': 0,
                'reason': 'degenerate tangent'}
    tangent.normalize()
    lateral = normal.cross(tangent)
    if lateral.length < 1.0e-8:
        return {'ok': False, 'min_retained_ratio': 0.0, 'min_width_mm': 0.0,
                'required_width_mm': radius * 2.0, 'samples': 0,
                'reason': 'degenerate lateral'}
    lateral.normalize()

    rise_tol = max(
        FRAME_WIDTH_SURFACE_RISE_MIN_TOL_MM,
        min(FRAME_WIDTH_SURFACE_RISE_MAX_TOL_MM,
            radius * FRAME_WIDTH_SURFACE_RISE_RADIUS_FACTOR),
    )
    scan = max(FRAME_SURFACE_RAY_SCAN_MIN_MM, radius * FRAME_SURFACE_RAY_SCAN_FACTOR)
    side_ratios = []
    checked = 0
    worst_rise = 0.0
    tolerated_outer = False
    for side in (-1.0, 1.0):
        previous_safe = 0.0
        side_ratio = 1.0
        for fraction in FRAME_SWEEP_SAMPLE_FRACTIONS:
            requested = radius * float(fraction)
            query = center + lateral * (side * requested)
            rise = _frame_ray_surface_height(
                cache, query, center, normal, tangent, scan)
            checked += 1
            if rise is not None:
                worst_rise = max(worst_rise, float(rise))
            obstructed = rise is not None and float(rise) > rise_tol
            if obstructed:
                side_ratio = float(previous_safe)
                if float(fraction) > FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO:
                    tolerated_outer = True
                    side_ratio = max(side_ratio, FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO)
                break
            previous_safe = float(fraction)
        side_ratios.append(float(side_ratio))

    retained = min(side_ratios) if side_ratios else 0.0
    ok = retained + 1.0e-9 >= FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO
    return {
        'ok': bool(ok),
        'min_retained_ratio': float(retained),
        'min_width_mm': float(retained * radius * 2.0),
        'required_width_mm': float(radius * 2.0),
        'surface_rise_tolerance_mm': float(rise_tol),
        'worst_surface_rise_mm': float(worst_rise),
        'samples': int(checked),
        'tolerated_outer_embedding': bool(tolerated_outer and ok),
        'reason': '' if ok else 'tube cross-section loses the central 75% support band',
    }


def _frame_resolve_continuous_anchor(cache, source_point, previous_point, next_point,
                                     frame_radius_mm, used_indices=None):
    """Resolve a semantic contour click to an exact face/barycentric anchor."""
    used_indices = set(used_indices or ())
    source = Vector(source_point)
    tangent = Vector(next_point) - Vector(previous_point)
    projection = _frame_surface_projection(cache, source)
    if projection is None:
        return None, {'reason': 'contour anchor could not be projected to IOS'}
    profile = _frame_point_support_profile(
        cache, projection['point'], projection['normal'], tangent, frame_radius_mm)
    nearest_index, nearest_dist = _frame_nearest_vertex(cache, projection['point'])
    if profile.get('ok'):
        return projection, {
            'relocated': False,
            'surface_geodesic_shift_mm': 0.0,
            'euclidean_shift_mm': float((projection['point'] - source).length),
            'initial_snap_mm': float(projection.get('distance_mm', nearest_dist)),
            'requested': [float(v) for v in source],
            'resolved': [float(v) for v in projection['point']],
            'triangle_index': int(projection.get('triangle_index', -1)),
            'barycentric': list(projection.get('barycentric', [])),
            'width_min_mm': float(profile.get('min_width_mm', 0.0)),
            'width_required_mm': float(profile.get('required_width_mm', frame_radius_mm * 2.0)),
        }

    search_radius = max(
        FRAME_ANCHOR_SAFE_SNAP_MIN_MM,
        min(FRAME_ANCHOR_SAFE_SNAP_MAX_MM,
            float(frame_radius_mm) * FRAME_ANCHOR_SAFE_SNAP_RADIUS_FACTOR),
    )
    nearby = _frame_vertices_within_surface_radius(
        cache, nearest_index, search_radius,
        max_candidates=FRAME_ANCHOR_SAFE_SNAP_MAX_CANDIDATES)
    best = None
    for vertex_index, surface_distance in nearby:
        point = Vector(cache['coords'][int(vertex_index)])
        normal = Vector(cache['normals'][int(vertex_index)])
        candidate_profile = _frame_point_support_profile(
            cache, point, normal, tangent, frame_radius_mm)
        if not candidate_profile.get('ok'):
            continue
        euclidean_shift = float((point - source).length)
        score = float(surface_distance) + 0.20 * euclidean_shift
        if best is None or score < best[0]:
            best = (score, int(vertex_index), float(surface_distance),
                    euclidean_shift, candidate_profile)
    if best is None:
        return None, {
            'reason': (
                f'no surface point within {search_radius:.2f} mm can preserve '
                f'the central {FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO * 100:.0f}% tube band'
            ),
            'initial_snap_mm': float(projection.get('distance_mm', nearest_dist)),
        }
    _score, vertex_index, surface_distance, euclidean_shift, candidate_profile = best
    resolved_point = Vector(cache['coords'][vertex_index])
    resolved = _frame_surface_projection(cache, resolved_point)
    if resolved is None:
        resolved = {
            'point': resolved_point,
            'normal': Vector(cache['normals'][vertex_index]),
            'triangle_index': -1,
            'triangle_vertices': (int(vertex_index),),
            'barycentric': [1.0],
            'distance_mm': 0.0,
        }
    return resolved, {
        'relocated': True,
        'surface_geodesic_shift_mm': float(surface_distance),
        'euclidean_shift_mm': float(euclidean_shift),
        'initial_snap_mm': float(projection.get('distance_mm', nearest_dist)),
        'requested': [float(v) for v in source],
        'resolved': [float(v) for v in resolved['point']],
        'triangle_index': int(resolved.get('triangle_index', -1)),
        'barycentric': list(resolved.get('barycentric', [])),
        'width_min_mm': float(candidate_profile.get('min_width_mm', 0.0)),
        'width_required_mm': float(candidate_profile.get('required_width_mm', frame_radius_mm * 2.0)),
    }


def _frame_semantic_segment_seeds(cache, start_point, end_point):
    a = Vector(start_point)
    b = Vector(end_point)
    length = float((b - a).length)
    count = max(2, int(math.ceil(length / max(0.20, FRAME_CORRIDOR_SEED_SPACING_MM))) + 1)
    seeds = []
    projected_points = []
    for i in range(count):
        t = i / float(max(1, count - 1))
        raw = a.lerp(b, t)
        projection = _frame_surface_projection(
            cache, raw,
            max_distance_mm=max(3.0, FRAME_CORRIDOR_RADIUS_MIN_MM * 1.5))
        if projection is None:
            continue
        projected_points.append(projection['point'].copy())
        vertex_index, _distance = _frame_nearest_vertex(cache, projection['point'])
        if vertex_index >= 0 and (not seeds or int(vertex_index) != seeds[-1]):
            seeds.append(int(vertex_index))
    return seeds, projected_points


def _frame_intrinsic_distance_field(cache, seeds):
    triangles = np.asarray(cache.get('triangles') if cache.get('triangles') is not None else [], dtype=np.int32)
    if (len(triangles) and int(cache.get('vertex_count', 0)) <= FRAME_HEAT_MAX_VERTICES
            and not bool(cache.get('heat_solver_failed', False))):
        dist, solver, backend, error = frame_surface_corridor.try_potpourri_heat_distance(
            cache['coords'], triangles, seeds, solver=cache.get('heat_solver'))
        if dist is not None:
            cache['heat_solver'] = solver
            cache['heat_backend'] = backend
            return dist, backend
        # Missing optional module should not be retried for every contour segment.
        if 'unavailable' in str(error).lower():
            cache['heat_solver_failed'] = True
    dist = frame_surface_corridor.multisource_intrinsic_distance(
        cache['csr_offsets'], cache['csr_dst'], cache['csr_weights'], seeds,
        int(cache.get('vertex_count', 0)))
    return dist, 'CSR_INTRINSIC_DISTANCE'


def _frame_corridor_clearance_field(cache, allowed_mask, semantic_distance,
                                    tangent_hint, frame_radius_mm):
    n = int(cache.get('vertex_count', 0))
    ratios = np.ones(n, dtype=np.float64)
    penalties = np.zeros(n, dtype=np.float64)
    hard_allowed = np.asarray(allowed_mask, dtype=bool).copy()
    indices = np.flatnonzero(hard_allowed)
    if indices.size == 0:
        return ratios, penalties, hard_allowed, 0

    # Exact cross-section queries are expensive. Evaluate the clinically likely
    # center of the semantic corridor first; failed final sweep samples trigger
    # targeted refinement around the actual candidate route.
    central_limit = max(2.5, float(frame_radius_mm) * 1.55)
    central = indices[np.asarray(semantic_distance[indices] <= central_limit)]
    if central.size == 0:
        central = indices
    if central.size > FRAME_CORRIDOR_CLEARANCE_EVAL_LIMIT:
        order = np.argsort(semantic_distance[central], kind='stable')
        central = central[order[:FRAME_CORRIDOR_CLEARANCE_EVAL_LIMIT]]

    evaluated = 0
    for vertex_index in central:
        point = Vector(cache['coords'][int(vertex_index)])
        normal = Vector(cache['normals'][int(vertex_index)])
        profile = _frame_point_support_profile(
            cache, point, normal, tangent_hint, frame_radius_mm)
        ratio = float(profile.get('min_retained_ratio', 0.0))
        ratios[int(vertex_index)] = ratio
        evaluated += 1
        if ratio < FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO:
            hard_allowed[int(vertex_index)] = False
        deficit = max(0.0, 1.0 - ratio)
        penalties[int(vertex_index)] = FRAME_CORRIDOR_CLEARANCE_WEIGHT * (deficit / 0.25) ** 2
    return ratios, penalties, hard_allowed, int(evaluated)


def _frame_continuous_project_and_smooth(cache, route_indices, start_anchor, end_anchor,
                                         allowed_mask, frame_radius_mm):
    coords = cache['coords']
    raw = np.asarray([coords[int(i)] for i in route_indices], dtype=np.float64)
    if len(raw) < 2:
        return None, 'NONE'

    # Narrow intrinsic band fixes the route's homotopy class before an optional
    # geometry-central edge-flip straightening crosses triangle interiors.
    band_radius = max(1.25, float(frame_radius_mm) * FRAME_CONTINUOUS_EDGEFLIP_BAND_FACTOR)
    route_band = frame_surface_corridor.multisource_intrinsic_distance(
        cache['csr_offsets'], cache['csr_dst'], cache['csr_weights'], route_indices,
        int(cache.get('vertex_count', 0)), limit_mm=band_radius)
    band_mask = np.isfinite(route_band)
    if allowed_mask is not None:
        band_mask &= np.asarray(allowed_mask, dtype=bool)
    for v in route_indices:
        band_mask[int(v)] = True
    effective_allowed = band_mask

    triangles = np.asarray(cache.get('triangles') if cache.get('triangles') is not None else [], dtype=np.int32)
    continuous = None
    backend = 'PROJECTED_CURVE_SHORTENING'
    if len(triangles):
        continuous, edge_backend = frame_surface_corridor.try_potpourri_edgeflip(
            cache['coords'], triangles, route_indices, band_mask)
        if continuous is not None:
            backend = edge_backend

    if continuous is None:
        continuous = frame_surface_corridor.resample_polyline(
            raw, max(0.20, FRAME_SURFACE_TARGET_SPACING_MM))
        if len(continuous) >= 2:
            continuous[0] = np.asarray(tuple(start_anchor['point']), dtype=np.float64)
            continuous[-1] = np.asarray(tuple(end_anchor['point']), dtype=np.float64)
        original = continuous.copy()
        for _iteration in range(max(0, int(FRAME_CONTINUOUS_SMOOTH_ITERATIONS))):
            updated = continuous.copy()
            for i in range(1, len(continuous) - 1):
                midpoint = 0.5 * (continuous[i - 1] + continuous[i + 1])
                target = continuous[i] + FRAME_CONTINUOUS_SMOOTH_BLEND * (midpoint - continuous[i])
                # Small tether to the chosen weighted corridor prevents a shortcut
                # from crossing a contact merely because it is Euclidean-close.
                target = 0.88 * target + 0.12 * original[i]
                projection = _frame_surface_projection(
                    cache, target, max_distance_mm=FRAME_CONTINUOUS_MAX_PROJECTION_MM)
                if projection is None:
                    continue
                nearest, _dist = _frame_nearest_vertex(cache, projection['point'])
                if nearest < 0 or not bool(effective_allowed[int(nearest)]):
                    continue
                updated[i] = np.asarray(tuple(projection['point']), dtype=np.float64)
            continuous = updated

    continuous = np.asarray(continuous, dtype=np.float64)
    if len(continuous) < 2:
        return None, backend
    continuous = frame_surface_corridor.resample_polyline(
        continuous, max(0.20, FRAME_SURFACE_TARGET_SPACING_MM))
    continuous[0] = np.asarray(tuple(start_anchor['point']), dtype=np.float64)
    continuous[-1] = np.asarray(tuple(end_anchor['point']), dtype=np.float64)
    return continuous, backend


def _frame_continuous_sweep_profile(cache, points, frame_radius_mm,
                                    start_tangent_hint=None, end_tangent_hint=None):
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return {'ok': False, 'reason': 'continuous route is empty', 'failed_positions': [],
                'min_retained_ratio': 0.0, 'min_width_mm': 0.0, 'samples': 0}
    failed = []
    tolerated = 0
    min_ratio = 1.0
    min_width = float(frame_radius_mm) * 2.0
    worst_rise = 0.0
    checked = 0
    for i in range(len(pts)):
        projection = _frame_surface_projection(cache, pts[i], max_distance_mm=1.0)
        if projection is None:
            failed.append(i)
            min_ratio = 0.0
            continue
        if i == 0 and start_tangent_hint is not None:
            tangent = Vector(start_tangent_hint)
        elif i == len(pts) - 1 and end_tangent_hint is not None:
            tangent = Vector(end_tangent_hint)
        elif i == 0:
            tangent = Vector(pts[1] - pts[0])
        elif i == len(pts) - 1:
            tangent = Vector(pts[-1] - pts[-2])
        else:
            tangent = Vector(pts[i + 1] - pts[i - 1])
        profile = _frame_point_support_profile(
            cache, projection['point'], projection['normal'], tangent, frame_radius_mm)
        checked += int(profile.get('samples', 0))
        ratio = float(profile.get('min_retained_ratio', 0.0))
        min_ratio = min(min_ratio, ratio)
        min_width = min(min_width, float(profile.get('min_width_mm', 0.0)))
        worst_rise = max(worst_rise, float(profile.get('worst_surface_rise_mm', 0.0)))
        if not profile.get('ok'):
            failed.append(i)
        elif profile.get('tolerated_outer_embedding'):
            tolerated += 1
    return {
        'ok': not bool(failed),
        'reason': '' if not failed else 'continuous tube sweep cannot retain the central 75% band',
        'failed_positions': failed,
        'min_retained_ratio': float(min_ratio),
        'min_width_mm': float(min_width),
        'required_width_mm': float(frame_radius_mm) * 2.0,
        'samples': int(checked),
        'tolerated_samples': int(tolerated),
        'worst_surface_rise_mm': float(worst_rise),
    }


def _frame_semantic_clearance_surface_route(cache, start_anchor, end_anchor,
                                            frame_radius_mm, start_tangent_hint,
                                            end_tangent_hint):
    """Plan one frame segment entirely on the IOS surface.

    v9.2.65 changes the semantic corridor from a brittle *hard tunnel* into an
    adaptive intrinsic intent band:

    1. project the user's intended segment to the IOS;
    2. compute one intrinsic distance field to that intent;
    3. try increasingly wider intrinsic bands if the narrow band is disconnected;
    4. treat predicted width/clearance as a strong *soft cost* on the first pass;
    5. only hard-ban regions proven bad by the actual continuous tube sweep;
    6. preserve a small intrinsic launch neighbourhood around exact barycentric
       endpoints so an otherwise valid anchor cannot be isolated by one bad
       triangulation ring.

    No Euclidean replacement path is ever accepted.
    """
    start_point = start_anchor['point']
    end_point = end_anchor['point']
    seeds, semantic_projection = _frame_semantic_segment_seeds(
        cache, start_point, end_point)
    if len(seeds) < 2:
        return None, {
            'reason': 'semantic contour corridor could not be projected',
            'backend': 'NONE',
            'euclidean_fallback': False,
        }

    semantic_distance, distance_backend = _frame_intrinsic_distance_field(cache, seeds)

    start_candidates = list(start_anchor.get('triangle_vertices') or ())
    end_candidates = list(end_anchor.get('triangle_vertices') or ())
    if not start_candidates:
        nearest, _ = _frame_nearest_vertex(cache, start_point)
        start_candidates = [nearest]
    if not end_candidates:
        nearest, _ = _frame_nearest_vertex(cache, end_point)
        end_candidates = [nearest]
    start_candidates = sorted({int(v) for v in start_candidates if int(v) >= 0})
    end_candidates = sorted({int(v) for v in end_candidates if int(v) >= 0})
    if not start_candidates or not end_candidates:
        return None, {
            'reason': 'surface endpoint could not be represented on the IOS mesh',
            'backend': 'NONE',
            'euclidean_fallback': False,
        }

    semantic_tangent = Vector(end_point) - Vector(start_point)
    if semantic_tangent.length < 1.0e-8:
        semantic_tangent = Vector(start_tangent_hint or (1.0, 0.0, 0.0))

    curvature = cache.get('frame_curvature_proxy')
    if curvature is None:
        curvature = frame_surface_corridor.curvature_proxy(
            cache['normals'], cache['csr_offsets'], cache['csr_dst'],
            src_indices=cache.get('csr_src'))
        cache['frame_curvature_proxy'] = curvature
    curvature = np.asarray(curvature, dtype=np.float64)

    start_offsets = [float((Vector(cache['coords'][v]) - Vector(start_point)).length)
                     for v in start_candidates]
    end_offsets = [float((Vector(cache['coords'][v]) - Vector(end_point)).length)
                   for v in end_candidates]

    base_radius = max(
        FRAME_CORRIDOR_RADIUS_MIN_MM,
        float(frame_radius_mm) * FRAME_CORRIDOR_RADIUS_FACTOR)
    radius_candidates = []
    for factor in FRAME_CORRIDOR_EXPANSION_FACTORS:
        radius = min(FRAME_CORRIDOR_RADIUS_MAX_MM, base_radius * float(factor))
        if not radius_candidates or radius > radius_candidates[-1] + 1.0e-6:
            radius_candidates.append(float(radius))
    if radius_candidates[-1] < FRAME_CORRIDOR_RADIUS_MAX_MM - 1.0e-6:
        radius_candidates.append(float(FRAME_CORRIDOR_RADIUS_MAX_MM))

    # Exact anchors may sit at a narrow contact where the local width predictor
    # is pessimistic. Keep a small *intrinsic* launch disk soft-routable; the
    # final continuous sweep still decides whether the tube is acceptable.
    launch_radius = max(
        FRAME_CORRIDOR_ENDPOINT_LAUNCH_MIN_MM,
        float(frame_radius_mm) * FRAME_CORRIDOR_ENDPOINT_LAUNCH_RADIUS_FACTOR)
    endpoint_launch = set(start_candidates + end_candidates)
    for seed_vertex in start_candidates + end_candidates:
        for vertex_index, _distance in _frame_vertices_within_surface_radius(
                cache, int(seed_vertex), launch_radius, max_candidates=1200):
            endpoint_launch.add(int(vertex_index))

    total_clearance_evals = 0
    total_route_attempts = 0
    continuous_backend = ''
    route_backend = ''
    last_profile = None
    last_failure = 'no connected intrinsic route exists on the IOS surface'
    widest_allowed_count = 0

    for expansion_index, corridor_radius in enumerate(radius_candidates):
        allowed = np.isfinite(semantic_distance) & (semantic_distance <= corridor_radius)
        for v in endpoint_launch:
            if 0 <= int(v) < len(allowed):
                allowed[int(v)] = True
        widest_allowed_count = max(widest_allowed_count, int(np.count_nonzero(allowed)))

        # Clearance is sampled up front, but in v9.2.65 it is a soft planning
        # field first. The old code immediately removed every vertex below 45%,
        # which could cut the corridor into two components before a path had ever
        # been tested with the true continuous tube sweep.
        ratios, clearance_penalty, predicted_hard_allowed, clearance_evals = (
            _frame_corridor_clearance_field(
                cache, allowed, semantic_distance, semantic_tangent, frame_radius_mm))
        total_clearance_evals += int(clearance_evals)

        normalized_intent = np.zeros_like(semantic_distance, dtype=np.float64)
        finite = np.isfinite(semantic_distance)
        normalized_intent[finite] = np.minimum(
            3.0, semantic_distance[finite] / max(corridor_radius, 1.0e-9))
        base_penalty = (
            FRAME_CORRIDOR_INTENT_WEIGHT * normalized_intent ** 2
            + clearance_penalty
            + FRAME_CORRIDOR_CURVATURE_WEIGHT * curvature
        )

        # Low predicted clearance remains traversable but very expensive. This
        # preserves connectivity without rewarding anatomically poor routes.
        low_pred = allowed & (ratios < FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO)
        if np.any(low_pred):
            deficit = np.maximum(0.0, FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO - ratios[low_pred])
            base_penalty[low_pred] += (
                FRAME_CORRIDOR_CLEARANCE_WEIGHT * 6.0
                * (1.0 + deficit / max(FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO, 1.0e-9)) ** 2
            )

        penalty = base_penalty.copy()
        working_allowed = allowed.copy()  # soft-first: do NOT start from predicted_hard_allowed
        for v in endpoint_launch:
            if 0 <= int(v) < len(working_allowed):
                working_allowed[int(v)] = True

        for attempt in range(max(1, int(FRAME_CORRIDOR_RETRY_COUNT))):
            total_route_attempts += 1
            result = frame_surface_corridor.weighted_route(
                cache['csr_offsets'], cache['csr_dst'], cache['csr_weights'],
                start_candidates, end_candidates,
                start_offsets=start_offsets, goal_offsets=end_offsets,
                allowed_mask=working_allowed, vertex_penalty=penalty,
                src_indices=cache.get('csr_src'))

            if result is None or not result.vertex_indices:
                last_failure = (
                    'semantic corridor is disconnected at this intrinsic radius')
                # Do not fail here. Widen the intrinsic corridor and try again.
                break

            route = list(result.vertex_indices)
            route_backend = str(result.backend)
            continuous, continuous_backend = _frame_continuous_project_and_smooth(
                cache, route, start_anchor, end_anchor, working_allowed, frame_radius_mm)
            if continuous is None:
                last_failure = 'continuous surface refinement failed inside the selected corridor'
                continue

            profile = _frame_continuous_sweep_profile(
                cache, continuous, frame_radius_mm,
                start_tangent_hint=start_tangent_hint,
                end_tangent_hint=end_tangent_hint)
            last_profile = profile
            if profile.get('ok'):
                path_length = float(np.sum(np.linalg.norm(np.diff(continuous, axis=0), axis=1)))
                return [Vector(tuple(p)) for p in continuous], {
                    'reason': '',
                    'backend': route_backend,
                    'distance_backend': distance_backend,
                    'continuous_backend': continuous_backend,
                    'cost': float(result.cost),
                    'path_length_mm': float(path_length),
                    'local_vertices': int(result.allowed_vertices),
                    'corridor_radius_mm': float(corridor_radius),
                    'corridor_expansion_index': int(expansion_index),
                    'semantic_seed_count': int(len(seeds)),
                    'clearance_evaluations': int(total_clearance_evals),
                    'width_validated': True,
                    'width_policy': 'CONTINUOUS_TUBE_CROSS_SECTION_75_PERCENT',
                    'width_required_mm': float(profile.get('required_width_mm', frame_radius_mm * 2.0)),
                    'width_min_mm': float(profile.get('min_width_mm', frame_radius_mm * 2.0)),
                    'width_min_retained_ratio': float(profile.get('min_retained_ratio', 1.0)),
                    'width_tolerated_samples': int(profile.get('tolerated_samples', 0)),
                    'width_worst_surface_rise_mm': float(profile.get('worst_surface_rise_mm', 0.0)),
                    'width_samples': int(profile.get('samples', 0)),
                    'corridor_retries': int(attempt),
                    'route_attempts_total': int(total_route_attempts),
                    'euclidean_fallback': False,
                }

            last_failure = str(profile.get(
                'reason', 'continuous tube sweep failed width validation'))

            # Only after a *real continuous sweep* fails do we hard-ban severely
            # unsupported local regions. Endpoint launch disks stay routable so
            # the exact anchor cannot be isolated by a single vertex ring.
            failed = list(profile.get('failed_positions', []) or [])
            for pos in failed:
                pos = int(pos)
                if pos < 0 or pos >= len(continuous):
                    continue
                nearest, _distance = _frame_nearest_vertex(cache, continuous[pos])
                if nearest < 0:
                    continue
                nearby = _frame_vertices_within_surface_radius(
                    cache, nearest, FRAME_CORRIDOR_RETRY_RADIUS_MM,
                    max_candidates=1100)
                for vertex_index, _surface_distance in nearby:
                    vertex_index = int(vertex_index)
                    point = Vector(cache['coords'][vertex_index])
                    normal = Vector(cache['normals'][vertex_index])
                    local_profile = _frame_point_support_profile(
                        cache, point, normal, semantic_tangent, frame_radius_mm)
                    total_clearance_evals += 1
                    ratio = float(local_profile.get('min_retained_ratio', 0.0))
                    deficit = max(0.0, 1.0 - ratio)
                    penalty[vertex_index] = max(
                        penalty[vertex_index],
                        FRAME_CORRIDOR_CLEARANCE_WEIGHT * 1.75 * (deficit / 0.25) ** 2)
                    if (ratio < FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO
                            and vertex_index not in endpoint_launch):
                        working_allowed[vertex_index] = False
            for v in endpoint_launch:
                if 0 <= int(v) < len(working_allowed):
                    working_allowed[int(v)] = True

        # This radius did not produce a validated route. Expand intrinsically.

    return None, {
        'reason': (
            (last_profile or {}).get('reason')
            or last_failure
            or 'no validated intrinsic surface route was found'),
        'backend': route_backend or 'ADAPTIVE_SEMANTIC_CORRIDOR',
        'distance_backend': distance_backend,
        'continuous_backend': continuous_backend,
        'corridor_radius_mm': float(radius_candidates[-1]),
        'corridor_expansions': int(len(radius_candidates) - 1),
        'allowed_vertices_max': int(widest_allowed_count),
        'clearance_evaluations': int(total_clearance_evals),
        'width_validated': False,
        'width_min_mm': float((last_profile or {}).get('min_width_mm', 0.0)),
        'width_min_retained_ratio': float((last_profile or {}).get('min_retained_ratio', 0.0)),
        'corridor_retries': int(FRAME_CORRIDOR_RETRY_COUNT),
        'route_attempts_total': int(total_route_attempts),
        'euclidean_fallback': False,
    }

