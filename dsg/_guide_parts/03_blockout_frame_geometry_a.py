def irrigation_sleeve_guard_enabled(props):
    """Protect exact sleeve shells from C-shaped irrigation Booleans."""
    try:
        return bool(getattr(props, 'irr_protect_sleeve_boolean', True))
    except Exception:
        return True

def apply_sleeve_face_clearance_to_components(
        context, components, cutters, props, implants):
    """Clear only the flat annular drill-stop seating surface while preserving sleeve components."""
    valid_components = [obj for obj in components if _valid_obj(obj) and obj.type == 'MESH']
    valid_cutters = [obj for obj in cutters if _valid_obj(obj) and obj.type == 'MESH']
    valid_implants = [obj for obj in implants if is_valid_implant_obj(obj)]
    if not valid_components or not valid_cutters or not valid_implants:
        return True, 'No sleeve-face cleanup was required', 0

    implant_by_name = {
        (_safe_object_name(implant) or ''): implant for implant in valid_implants
    }
    cutter_aabbs = [object_world_aabb(cutter) for cutter in valid_cutters]
    operations = 0

    for component_index, component in enumerate(valid_components):
        component_aabb = object_world_aabb(component)
        for cutter_index, (cutter, cutter_aabb) in enumerate(zip(valid_cutters, cutter_aabbs)):
            implant_name = str(cutter.get('DSG_implant_name', ''))
            implant = implant_by_name.get(implant_name)
            if implant is None and cutter_index < len(valid_implants):
                implant = valid_implants[cutter_index]

            # The exact sleeve shell is the protected support surface.  Every
            # other overlapping component is cut, including frame, connectors,
            # irrigation and accidental geometry over the sleeve face.
            if implant is not None and _component_is_sleeve_shell_for_implant(
                    component, props, implant):
                try:
                    component['DSG_sleeve_flat_face_preserved'] = True
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                continue

            if not aabb_overlap(component_aabb, cutter_aabb, margin=0.02):
                continue

            ok, message = apply_difference_exact_checked(
                context,
                component,
                cutter,
                f'DSG_SleeveFaceClearance_{component_index:02d}_{cutter_index:02d}',
                robust_retry=True,
                allow_manifold_fallback=True,
                retry_offsets=(0.01, 0.02, 0.04, 0.08),
            )
            if not ok:
                return (
                    False,
                    f'component {component_index + 1}, sleeve {cutter_index + 1}: {message}',
                    operations,
                )
            operations += 1
            component_aabb = object_world_aabb(component)

    return True, f'{operations} sleeve seating-face clearance cut(s) applied', operations



def repair_manifold_difference_boundary(obj, max_boundary_edges=256, merge_dist=0.0005):
    """Close small accidental rims left by Blender MANIFOLD Boolean.

    This is used only by the drill insertion protection pre-cleanup. The final
    drill lumen is cut later by the dedicated drill-channel operator.
    """
    report = {
        'changed': False,
        'boundary_edges': 0,
        'components': 0,
        'filled_components': 0,
        'max_boundary_edges': int(max_boundary_edges),
    }
    if not _valid_obj(obj) or obj.type != 'MESH':
        return report
    bm = None
    try:
        mesh = obj.data
        mesh.validate(clean_customdata=False)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        if bm.verts:
            bmesh.ops.remove_doubles(
                bm, verts=bm.verts[:], dist=max(0.0, float(merge_dist)))
        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) != 2]
        report['boundary_edges'] = int(len(boundary_edges))
        if not boundary_edges or len(boundary_edges) > int(max_boundary_edges):
            return report
        remaining = set(boundary_edges)
        components = []
        while remaining:
            start = remaining.pop()
            stack = [start]
            component = [start]
            while stack:
                edge = stack.pop()
                for vert in edge.verts:
                    for linked in vert.link_edges:
                        if linked in remaining and len(linked.link_faces) != 2:
                            remaining.remove(linked)
                            stack.append(linked)
                            component.append(linked)
            components.append(component)
        report['components'] = int(len(components))
        for component in components:
            try:
                result = bmesh.ops.holes_fill(bm, edges=list(component), sides=0)
                if result.get('faces'):
                    report['filled_components'] += 1
            except Exception as exc:
                report.setdefault('errors', []).append(str(exc))
        if report['filled_components']:
            if bm.faces:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            bm.to_mesh(mesh)
            mesh.validate(clean_customdata=False)
            mesh.update(calc_edges=True)
            report['changed'] = True
        return report
    except Exception as exc:
        report['error'] = str(exc)
        return report
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def apply_difference_manifold_checked(context, base_obj, cutter_obj, modifier_name):
    """Apply one transactional MANIFOLD difference without invoking EXACT.

    This path is reserved for clean analytic drill-protection cutters. Blender
    5.1 can crash natively inside meshintersect when several EXACT Boolean
    modifiers are evaluated consecutively on recently rebuilt multi-shell
    guide parts. MANIFOLD is sufficient here because both operands are closed
    by construction. A failed result is rolled back and reported instead of
    retrying with EXACT.
    """
    if not _valid_obj(base_obj) or not _valid_obj(cutter_obj):
        return False, 'invalid objects'
    original_mesh = base_obj.data.copy()
    mod = None
    try:
        clean_boolean_cutter_mesh(cutter_obj)
        mod = base_obj.modifiers.new(modifier_name, 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = cutter_obj
        supported = get_supported_boolean_solvers(mod)
        if 'MANIFOLD' not in supported:
            base_obj.modifiers.remove(mod)
            _restore_object_mesh_copy(base_obj, original_mesh)
            return False, 'MANIFOLD Boolean is not supported by this Blender build'
        mod.solver = 'MANIFOLD'
        if not apply_modifier_direct(context, base_obj, mod.name):
            leftover = base_obj.modifiers.get(modifier_name)
            if leftover is not None:
                base_obj.modifiers.remove(leftover)
            _restore_object_mesh_copy(base_obj, original_mesh)
            return False, 'Boolean DIFFERENCE MANIFOLD could not be applied'

        if not base_obj.data or not base_obj.data.vertices or not base_obj.data.polygons:
            _restore_object_mesh_copy(base_obj, original_mesh)
            return False, 'the Boolean completely removed the component'

        cleanup_boolean_result_minimal(base_obj)
        report = get_mesh_solid_report(base_obj, max_polygons=900000)
        if report.get('checked') and not report.get('solid'):
            repair = repair_manifold_difference_boundary(base_obj)
            if repair.get('changed'):
                cleanup_boolean_result_minimal(base_obj)
                report = get_mesh_solid_report(base_obj, max_polygons=900000)
                try:
                    base_obj['DSG_manifold_repair_report'] = json.dumps(
                        repair, ensure_ascii=False, default=str)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        if report.get('checked') and not report.get('solid'):
            bad = report.get('bad_edges', 0)
            deg = report.get('degenerate_faces', 0)
            _restore_object_mesh_copy(base_obj, original_mesh)
            return False, f'non-solid MANIFOLD result: edges={bad}, degenerate faces={deg}'

        try:
            base_obj['DSG_boolean_solver'] = 'MANIFOLD'
            base_obj['DSG_boolean_combined_drill_protection'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if original_mesh.users == 0:
                bpy.data.meshes.remove(original_mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, 'DIFFERENCE MANIFOLD OK'
    except Exception as exc:
        try:
            if mod is not None and base_obj.modifiers.get(mod.name) is not None:
                base_obj.modifiers.remove(mod)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _restore_object_mesh_copy(base_obj, original_mesh)
        return False, f'MANIFOLD Boolean error: {exc}'

def apply_drill_insertion_protection_to_components(context, components, cutters):
    """Apply axial protection with one combined MANIFOLD cut per component.

    Combining all implant cylinders avoids the previous chain of repeated EXACT
    modifiers (component × implant), which could crash Blender 5.1 inside the
    native mesh-intersection code.
    """
    valid_components = [obj for obj in components if _valid_obj(obj) and obj.type == 'MESH']
    valid_cutters = [obj for obj in cutters if _valid_obj(obj) and obj.type == 'MESH']
    if not valid_components or not valid_cutters:
        return False, 'components or protection cutters are missing', 0

    combined = build_combined_mesh_object_world(
        context, valid_cutters, 'DSG_DrillProtection_Combined')
    if not _valid_obj(combined):
        return False, 'could not build the combined drill-protection cutter', 0
    combined.display_type = 'WIRE'
    combined.show_in_front = True
    try:
        combined['DSG_cut_type'] = 'combined_drill_insertion_protection'
        combined['DSG_analytic_solid'] = True
        combined['DSG_cutter_count'] = len(valid_cutters)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    combined_aabb = object_world_aabb(combined)
    operations = 0
    try:
        for component_index, component in enumerate(valid_components):
            if not aabb_overlap(object_world_aabb(component), combined_aabb, margin=0.02):
                continue
            component_kind = (
                'irrigation wall'
                if bool(component.get('DSG_irrigation_wall_confirmed', False))
                else 'guide shell')
            ok, message = apply_difference_manifold_checked(
                context, component, combined,
                f'DSG_DrillProtectionCombined_{component_index:02d}')
            if not ok:
                return False, f'{component_kind} {component_index + 1}: {message}', operations
            operations += 1
        return True, f'{operations} combined axial MANIFOLD cut(s) applied', operations
    finally:
        safe_remove_object(combined)


def protect_guide_drill_insertion_transactional(context, props):
    """Limpia el eje sobre la guía y las paredes de irrigación por Boolean.

    En el paso 7 las paredes confirmadas todavía son objetos independientes de
    DSG_Guide. La versión anterior cortaba únicamente la guía y por eso el botón
    parecía no hacer nada sobre el tubo. Esta operación trabaja con copias,
    aplica DIFFERENCE EXACT a cada shell que intersecte el cutter y solo hace
    commit cuando todos los resultados siguen siendo sólidos y no vacíos.
    """
    guide = get_active_guide_obj(props)
    implants = get_all_implant_objects(props)
    irrigation_walls = get_confirmed_irrigation_walls()
    if not _valid_obj(guide):
        return False, 'DSG_Guide not found', 0
    if not implants:
        return False, 'No se encontraron implantes DSG', 0

    temp_objects = []
    parts = []
    cutters = []
    face_cutters = []
    wall_pairs = []
    result = None
    committed = False
    operations = 0
    face_operations = 0

    try:
        # 1) La guía se procesa por shells para evitar booleanas sobre una malla
        # multishell completa.
        parts = split_mesh_object_loose_parts(
            context, guide, prefix='DSG_DrillProtectPart')
        temp_objects.extend(parts)
        if not parts:
            return False, 'Could not split the guide into closed shells', 0

        # 2) Las paredes de irrigación se duplican para que el original sobreviva
        # a cualquier fallo de la booleana.
        for index, wall in enumerate(irrigation_walls):
            wall_name = _safe_object_name(wall)
            wall_copy = duplicate_object_with_data(
                context, wall, f'DSG_DrillProtectWallCopy_{index:02d}')
            if not _valid_obj(wall_copy):
                return False, f'Could not copy irrigation wall {index + 1}', operations
            register_dsg_object(wall_copy, ROLE_IRRIGATION)
            temp_objects.append(wall_copy)
            wall_pairs.append((wall, wall_copy, wall_name))

        cutters = build_drill_insertion_protection_cutters(
            context, props, implants, reference_obj=guide)
        temp_objects.extend(cutters)
        if not cutters:
            return False, 'Could not create the Boolean cylinders', 0

        targets = list(parts) + [copy for _original, copy, _name in wall_pairs]
        ok, message, operations = apply_drill_insertion_protection_to_components(
            context, targets, cutters)
        if not ok:
            return False, message, operations

        # Clear every non-sleeve component only over the flat annular drill-stop support surface.
        # The exact cylindrical sleeve shell is detected and skipped, preserving
        # its flat annular top face while removing connectors or any other body
        # that invades that flat surface.
        face_cutters = build_sleeve_face_clearance_cutters(
            context, props, implants)
        temp_objects.extend(face_cutters)
        if not face_cutters:
            return False, 'Could not create the flat sleeve-face cutters', operations
        face_ok, face_message, face_operations = (
            apply_sleeve_face_clearance_to_components(
                context, targets, face_cutters, props, implants))
        if not face_ok:
            return False, face_message, operations + face_operations

        if operations <= 0:
            _clinical_radius, boolean_radius, _anti, _extra = (
                get_drill_protection_radii(props))
            diameter = boolean_radius * 2.0
            return False, (
                f'Los cilindros Ø {diameter:.2f} mm no intersectaron la guía ni las paredes. '
                'Revisa la posición y orientación del implante.'), 0

        # 3) Reconstruye únicamente la guía. Las paredes permanecen separadas para
        # que el flujo de irrigación pueda seguir confirmándolas normalmente.
        safe_remove_by_name(DRILL_PROTECTION_RESULT_NAME)
        result = build_combined_mesh_object_world(
            context, parts, DRILL_PROTECTION_RESULT_NAME)
        if not _valid_obj(result):
            return False, 'Could not rebuild the protected guide', operations
        temp_objects.append(result)

        report = get_mesh_solid_report(result, max_polygons=1200000)
        if report.get('checked') and not report.get('solid'):
            return (
                False,
                f'Non-solid protection result: edges={report.get("bad_edges", 0)}, '
                f'caras degeneradas={report.get("degenerate_faces", 0)}',
                operations,
            )

        # 4) Commit transaccional.
        old_guide_name = _safe_object_name(guide)
        if old_guide_name:
            _archive_current_guide_for_sleeve_rebuild(
                props, reason='drill_insertion_protection_commit')

        for original, wall_copy, original_name in wall_pairs:
            if _valid_obj(original):
                safe_remove_object(original)
            if _valid_obj(wall_copy):
                wall_copy.name = original_name or wall_copy.name
                try:
                    wall_copy.data.name = wall_copy.name + '_Mesh'
                    wall_copy['DSG_irrigation_wall_confirmed'] = True
                    wall_copy['DSG_drill_axis_cleaned'] = True
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                register_dsg_object(wall_copy, ROLE_IRRIGATION)

        # Quitar todos los temporales salvo el resultado y las paredes ya
        # comprometidas.
        committed_wall_ids = {
            wall_copy.as_pointer() for _original, wall_copy, _name in wall_pairs
            if _valid_obj(wall_copy)
        }
        for obj in list(temp_objects):
            if obj is result:
                continue
            try:
                if _valid_obj(obj) and obj.as_pointer() in committed_wall_ids:
                    continue
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            safe_remove_object(obj)

        result.name = GUIDE_NAME
        result.data.name = GUIDE_NAME + '_Mesh'
        _inherit_dsg_custom_properties(guide, result)
        clinical_radius, boolean_radius, anti_coplanar, protection_extra = (
            get_drill_protection_radii(props))
        diameter = boolean_radius * 2.0
        try:
            result['DSG_drill_insertion_protected'] = True
            result['DSG_drill_protection_operations'] = int(operations)
            result['DSG_sleeve_face_clearance_operations'] = int(face_operations)
            result['DSG_sleeve_occlusal_faces_preserved'] = True
            result['DSG_drill_protection_clinical_diameter'] = float(clinical_radius * 2.0)
            result['DSG_drill_protection_anticoplanar_radial'] = float(anti_coplanar)
            result['DSG_drill_protection_extra_radial'] = float(protection_extra)
            result['DSG_drill_protection_diameter'] = float(diameter)
            result['DSG_drill_protection_clearance_source'] = 'fresa_offset_dynamic_plus_anticoplanar'
            result['DSG_drill_protected_irrigation_walls'] = int(len(wall_pairs))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        props.guide_obj = register_dsg_object(result, ROLE_GUIDE, GUIDE_NAME)
        set_active(context, result)
        committed = True
        total_operations = int(operations) + int(face_operations)
        return (
            True,
            f'{operations} cortes axiales y {face_operations} limpiezas de cara plana '
            f'aplicados sobre guía y {len(wall_pairs)} irrigation wall(s)',
            total_operations,
        )
    finally:
        if not committed:
            for obj in list(temp_objects):
                safe_remove_object(obj)


def cleanup_drill_boolean_result(obj, merge_dist=0.0005):
    """Limpieza topológica mínima tras el boolean del canal.

    Elimina caras duplicadas exactas, vértices microscópicamente coincidentes y
    edges degeneradas. No rellena huecos ni hace remesh, por lo que no cierra
    el canal ni redondea las caras planas del sleeve.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False

    bm = None
    try:
        mesh = obj.data
        mesh.validate(clean_customdata=False)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Quitar caras duplicadas que pueden dejar una sola arista con 3/4 caras.
        seen = set()
        duplicates = []
        for face in bm.faces:
            key = tuple(sorted(v.index for v in face.verts))
            if key in seen:
                duplicates.append(face)
            else:
                seen.add(key)
        if duplicates:
            bmesh.ops.delete(bm, geom=duplicates, context='FACES')

        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        if bm.verts:
            bmesh.ops.remove_doubles(
                bm,
                verts=bm.verts[:],
                dist=max(0.0, float(merge_dist)),
            )
        if bm.edges:
            try:
                bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-7)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        bm.to_mesh(mesh)
        bm.free()
        bm = None
        mesh.validate(clean_customdata=False)
        mesh.update()
        return True
    except Exception as exc:
        print(f"[DSG] Post-Boolean channel cleanup skipped: {exc}")
        return False
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def restore_guide_mesh_from_backup(guide_obj, backup_mesh):
    """Restaura la guía si un boolean produce bordes abiertos/no manifold."""
    if not guide_obj or not backup_mesh:
        return False
    result_mesh = guide_obj.data
    guide_obj.data = backup_mesh
    try:
        guide_obj.data.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if result_mesh and result_mesh != backup_mesh and result_mesh.users == 0:
            bpy.data.meshes.remove(result_mesh)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


# ─────────────────────────────────────────────────────────────
# Blockout BVH
# ─────────────────────────────────────────────────────────────



def _read_render_depth_pass(width, height):
    """Read the one-channel Z pass produced by Blender's Render Result."""
    image = bpy.data.images.get('Render Result')
    if image is None:
        raise RuntimeError('Blender did not create a Render Result')
    candidates = []
    try:
        for layer in image.view_layers:
            for render_pass in layer.passes:
                name = str(getattr(render_pass, 'name', '')).lower()
                if name in {'depth', 'z'} or 'depth' in name:
                    candidates.append(render_pass)
    except Exception:
        candidates = []
    if not candidates:
        raise RuntimeError('The orthographic render did not expose a Depth pass')
    last_error = None
    for render_pass in candidates:
        try:
            channels = max(1, int(getattr(render_pass, 'channels', 1)))
            raw = np.asarray(render_pass.rect[:], dtype=np.float32)
            expected = int(width) * int(height) * channels
            if raw.size != expected:
                continue
            array = raw.reshape((int(height), int(width), channels))[:, :, 0]
            return np.ascontiguousarray(array, dtype=np.float32)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f'Could not read the Depth pass: {last_error or "unexpected pass size"}')


def _render_orthographic_ios_depth(source_obj, axis, world, u, v, axial):
    """Rasterize the aligned IOS triangles from the insertion direction.

    A temporary Eevee scene contains only a modifier-free copy of the IOS and an
    orthographic camera.  The renderer's Z buffer is the exact frontmost triangle
    envelope at image resolution, so interdental voids remain voids and no Python
    ray loop is required.
    """
    axis = Vector(axis).normalized()
    basis_u, basis_v, _ = build_axis_basis(axis)
    u_min_raw, u_max_raw = float(np.min(u)), float(np.max(u))
    v_min_raw, v_max_raw = float(np.min(v)), float(np.max(v))
    span_u = max(1.0e-4, u_max_raw - u_min_raw)
    span_v = max(1.0e-4, v_max_raw - v_min_raw)
    margin = float(RETENTION_RASTER_MARGIN_MM)
    desired_u = span_u + 2.0 * margin
    desired_v = span_v + 2.0 * margin
    pixel_mm = max(0.05, float(RETENTION_RASTER_PIXEL_MM))
    width = max(RETENTION_RASTER_MIN_PIXELS, int(math.ceil(desired_u / pixel_mm)))
    height = max(RETENTION_RASTER_MIN_PIXELS, int(math.ceil(desired_v / pixel_mm)))
    maximum = max(width, height)
    if maximum > int(RETENTION_RASTER_MAX_PIXELS):
        scale = float(maximum) / float(RETENTION_RASTER_MAX_PIXELS)
        pixel_mm *= scale
        width = max(64, int(math.ceil(desired_u / pixel_mm)))
        height = max(64, int(math.ceil(desired_v / pixel_mm)))
    width = int(max(64, min(int(RETENTION_RASTER_MAX_PIXELS), width)))
    height = int(max(64, min(int(RETENTION_RASTER_MAX_PIXELS), height)))
    center_u = 0.5 * (u_min_raw + u_max_raw)
    center_v = 0.5 * (v_min_raw + v_max_raw)
    actual_u = float(width) * pixel_mm
    actual_v = float(height) * pixel_mm
    u_min = center_u - 0.5 * actual_u
    v_min = center_v - 0.5 * actual_v

    axial_min = float(np.min(axial))
    axial_max = float(np.max(axial))
    camera_axial = axial_max + max(float(RETENTION_RASTER_CAMERA_MARGIN_MM),
                                   0.12 * max(1.0, axial_max - axial_min))
    clip_end = max(20.0, camera_axial - axial_min + 10.0)
    camera_position = (basis_u * center_u + basis_v * center_v + axis * camera_axial)

    token = f'{int(time.time() * 1000000) % 1000000000:09d}'
    scene = None
    proxy = None
    camera_obj = None
    camera_data = None
    override_material = None
    started = time.perf_counter()
    try:
        scene = bpy.data.scenes.new(f'DSG_BlockoutRaster_{token}')
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.pixel_aspect_x = 1.0
        scene.render.pixel_aspect_y = 1.0
        scene.render.film_transparent = True
        scene.render.use_file_extension = False
        scene.render.use_compositing = False
        scene.render.use_sequencer = False
        try:
            scene.render.image_settings.file_format = 'OPEN_EXR'
            scene.render.image_settings.color_depth = '32'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        view_layer = scene.view_layers[0]
        view_layer.use_pass_z = True

        proxy = source_obj.copy()
        proxy.name = f'DSG_RasterIOS_{token}'
        proxy.data = source_obj.data
        proxy.matrix_world = source_obj.matrix_world.copy()
        proxy.hide_render = False
        proxy.hide_viewport = False
        try:
            proxy.animation_data_clear()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            for modifier in list(proxy.modifiers):
                proxy.modifiers.remove(modifier)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        scene.collection.objects.link(proxy)

        override_material = bpy.data.materials.new(f'DSG_RasterDepthMaterial_{token}')
        override_material.use_nodes = False
        override_material.diffuse_color = (0.5, 0.5, 0.5, 1.0)
        view_layer.material_override = override_material

        camera_data = bpy.data.cameras.new(f'DSG_RasterCameraData_{token}')
        camera_obj = bpy.data.objects.new(f'DSG_RasterCamera_{token}', camera_data)
        scene.collection.objects.link(camera_obj)
        camera_data.type = 'ORTHO'
        camera_data.ortho_scale = actual_v
        camera_data.clip_start = 0.01
        camera_data.clip_end = clip_end
        orientation = Matrix((basis_u, basis_v, axis)).transposed().to_4x4()
        orientation.translation = camera_position
        camera_obj.matrix_world = orientation
        scene.camera = camera_obj

        bpy.ops.render.render(scene=scene.name, write_still=False)
        depth = _read_render_depth_pass(width, height)
        valid = (np.isfinite(depth)
                 & (depth > 0.001)
                 & (depth < float(camera_data.clip_end) * 0.999))
        if int(np.count_nonzero(valid)) < 32:
            raise RuntimeError('The triangle depth image is empty')
        return {
            'depth_image': depth,
            'valid_image': valid,
            'width': width,
            'height': height,
            'pixel_mm': float(pixel_mm),
            'u_min': float(u_min),
            'v_min': float(v_min),
            'camera_axial': float(camera_axial),
            'clip_end': float(clip_end),
            'render_seconds': float(time.perf_counter() - started),
            'valid_pixels': int(np.count_nonzero(valid)),
        }
    finally:
        try:
            if scene is not None:
                bpy.data.scenes.remove(scene)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if proxy is not None and proxy.name in bpy.data.objects:
                bpy.data.objects.remove(proxy, do_unlink=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if camera_obj is not None and camera_obj.name in bpy.data.objects:
                bpy.data.objects.remove(camera_obj, do_unlink=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if camera_data is not None and camera_data.users == 0:
                bpy.data.cameras.remove(camera_data)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            if override_material is not None and override_material.users == 0:
                bpy.data.materials.remove(override_material)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _sample_raster_depth(depth, valid, px, py, radius=1):
    """Sample direct pixels, then a one-pixel nearest-envelope fallback."""
    height, width = depth.shape
    px = np.asarray(px, dtype=np.int32)
    py = np.asarray(py, dtype=np.int32)
    inside = (px >= 0) & (px < width) & (py >= 0) & (py < height)
    values = np.full(px.shape, np.inf, dtype=np.float64)
    direct = np.zeros(px.shape, dtype=bool)
    indices = np.flatnonzero(inside)
    if indices.size:
        good = valid[py[indices], px[indices]]
        good_indices = indices[good]
        if good_indices.size:
            values[good_indices] = depth[py[good_indices], px[good_indices]]
            direct[good_indices] = True
    fallback = np.zeros(px.shape, dtype=bool)
    if radius > 0 and np.any(inside & ~direct):
        missing = inside & ~direct
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                qx = px + dx
                qy = py + dy
                ok = missing & (qx >= 0) & (qx < width) & (qy >= 0) & (qy < height)
                idx = np.flatnonzero(ok)
                if not idx.size:
                    continue
                good = valid[qy[idx], qx[idx]]
                idx = idx[good]
                if not idx.size:
                    continue
                candidate = depth[qy[idx], qx[idx]].astype(np.float64)
                better = candidate < values[idx]
                chosen = idx[better]
                values[chosen] = candidate[better]
                fallback[chosen] = True
    return values, direct, fallback


def _simple_axis_blockout_analysis(source_obj, axis):
    """Accurate blockout survey from a cached orthographic triangle Z buffer.

    Unlike the previous vertex-cell method, every rendered pixel comes from a
    real IOS triangle.  The frontmost triangle along the insertion axis is the
    physical insertion envelope; the axial distance from each IOS vertex to that
    envelope is its undercut depth.  Preset changes reuse the same cached image.
    """
    axis = Vector(axis)
    if axis.length <= 1.0e-8:
        raise ValueError('Invalid insertion axis')
    axis.normalize()
    key = ('TRIANGLE_RASTER_DEPTH_V1', int(RETENTION_RASTER_ENGINE_VERSION),
           round(float(RETENTION_RASTER_PIXEL_MM), 4)) + tuple(_retention_cache_key(source_obj, axis))
    cached = _RETENTION_BVH_CACHE.get(key)
    if cached is not None:
        return cached

    mesh = source_obj.data
    count = len(mesh.vertices)
    if count < 3:
        raise ValueError('The IOS does not contain enough vertices')
    try:
        mesh.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    local = np.empty(count * 3, dtype=np.float64)
    normals_local = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', local)
    mesh.vertices.foreach_get('normal', normals_local)
    local = local.reshape((-1, 3))
    normals_local = normals_local.reshape((-1, 3))
    matrix = np.asarray([[float(source_obj.matrix_world[r][c]) for c in range(4)]
                         for r in range(4)], dtype=np.float64)
    linear = matrix[:3, :3]
    translation = matrix[:3, 3]
    inverse_linear = np.linalg.inv(linear)
    world = local @ linear.T + translation
    normals_world = normals_local @ inverse_linear
    lengths = np.linalg.norm(normals_world, axis=1)
    good_normals = lengths > 1.0e-12
    normals_world[good_normals] /= lengths[good_normals, None]
    normals_world[~good_normals] = np.asarray((0.0, 0.0, 1.0))

    basis_u, basis_v, _ = build_axis_basis(axis)
    axis_np = np.asarray(tuple(axis), dtype=np.float64)
    u_np = np.asarray(tuple(basis_u), dtype=np.float64)
    v_np = np.asarray(tuple(basis_v), dtype=np.float64)
    u = world @ u_np
    v = world @ v_np
    axial = world @ axis_np

    try:
        raster = _render_orthographic_ios_depth(source_obj, axis, world, u, v, axial)
        pixel_mm = float(raster['pixel_mm'])
        px = np.rint((u - float(raster['u_min'])) / pixel_mm - 0.5).astype(np.int32)
        py = np.rint((v - float(raster['v_min'])) / pixel_mm - 0.5).astype(np.int32)
        depth_image = raster['depth_image']
        valid_image = raster['valid_image']
        z_a, direct_a, fallback_a = _sample_raster_depth(
            depth_image, valid_image, px, py,
            radius=int(RETENTION_RASTER_FALLBACK_RADIUS_PIXELS))
        z_b, direct_b, fallback_b = _sample_raster_depth(
            depth_image, valid_image, px, (int(raster['height']) - 1) - py,
            radius=int(RETENTION_RASTER_FALLBACK_RADIUS_PIXELS))
        facing = normals_world @ axis_np

        def orientation_score(z_values):
            valid_values = np.isfinite(z_values)
            front = float(raster['camera_axial']) - z_values
            residual = front - axial
            visible = valid_values & (facing > 0.35)
            sample = np.abs(residual[visible])
            if sample.size < 16:
                sample = np.abs(residual[valid_values])
            return float(np.median(sample)) if sample.size else float('inf')

        if orientation_score(z_b) + 1.0e-6 < orientation_score(z_a):
            sampled_z, direct, fallback = z_b, direct_b, fallback_b
            y_flipped = True
        else:
            sampled_z, direct, fallback = z_a, direct_a, fallback_a
            y_flipped = False
        sampled_valid = np.isfinite(sampled_z)
        front_axial = np.full(count, -np.inf, dtype=np.float64)
        front_axial[sampled_valid] = float(raster['camera_axial']) - sampled_z[sampled_valid]
        raw_depth = np.maximum(0.0, front_axial - axial - float(RETENTION_RASTER_DEPTH_BIAS_MM))
        facing = normals_world @ axis_np
        candidate = (
            sampled_valid
            & (raw_depth > float(RETENTION_MIN_UNDERCUT_MM))
            & (raw_depth <= float(RETENTION_RASTER_MAX_CLINICAL_DEPTH_MM))
        )
        # A tiny apparent depth on a strongly front-facing facet is normally a
        # raster sampling error on a steep slope, not a clinically useful undercut.
        candidate &= ~(
            (raw_depth < float(RETENTION_RASTER_SHALLOW_VISIBLE_LIMIT_MM))
            & (facing > float(RETENTION_RASTER_SHALLOW_VISIBLE_NORMAL_DOT))
        )
        clinical = sampled_valid & (raw_depth <= float(RETENTION_RASTER_MAX_CLINICAL_DEPTH_MM))
        valid_depths = raw_depth[candidate]
        analysis = {
            'coords_local': local.astype(np.float32),
            'coords_world': world.astype(np.float32),
            'normals_world': normals_world.astype(np.float32),
            'depths_np': raw_depth.astype(np.float32),
            'depths': raw_depth.astype(np.float32),
            'usable_mask_np': candidate,
            'usable_mask': candidate,
            'clinical_mask_np': clinical,
            'candidate_count': int(np.count_nonzero(candidate)),
            'maximum_undercut_depth_mm': float(np.max(valid_depths) if valid_depths.size else 0.0),
            'anatomy_vertex_limit': int(count),
            'grid_width': int(raster['width']),
            'grid_height': int(raster['height']),
            'grid_cell_mm': float(pixel_mm),
            'occupied_cells': int(raster['valid_pixels']),
            'axis_np': axis_np.astype(np.float64),
            'linear': linear,
            'translation': translation,
            'inverse_linear': inverse_linear,
            'method': 'ORTHOGRAPHIC_TRIANGLE_ZBUFFER_DEPTHMAP',
            'render_seconds': float(raster['render_seconds']),
            'direct_samples': int(np.count_nonzero(direct)),
            'fallback_samples': int(np.count_nonzero(fallback & ~direct)),
            'y_flipped': bool(y_flipped),
        }
    except Exception as exc:
        # Reliable fallback for systems where a render-depth pass is unavailable.
        analysis = _vertex_grid_blockout_analysis_legacy(source_obj, axis)
        analysis = dict(analysis)
        analysis['method'] = 'VERTEX_GRID_FALLBACK_AFTER_RASTER_ERROR'
        analysis['raster_error'] = str(exc)
        analysis['render_seconds'] = 0.0
        analysis['direct_samples'] = 0
        analysis['fallback_samples'] = 0

    if len(_RETENTION_BVH_CACHE) >= int(RETENTION_CACHE_MAX_ENTRIES):
        _RETENTION_BVH_CACHE.pop(next(iter(_RETENTION_BVH_CACHE)))
    _RETENTION_BVH_CACHE[key] = analysis
    return analysis


def _vertex_grid_blockout_analysis_legacy(source_obj, axis):
    """Return a fast, single-valued insertion envelope for the aligned IOS.

    This deliberately avoids BVH trees, per-vertex ray casts and BMesh.  Each
    vertex is projected to a small cell in the plane perpendicular to the exact
    insertion axis.  The most coronal point in that cell is the local insertion
    envelope.  A vertex is a blockout candidate only when:

    * it lies behind that envelope by a measurable amount;
    * its normal faces away from the insertion direction;
    * its cell contains real IOS samples; and
    * the candidate belongs to a small coherent group of neighbouring cells.

    No dilation is used, so an empty interdental cell cannot bridge two teeth.
    """
    axis = Vector(axis)
    if axis.length <= 1.0e-8:
        raise ValueError('Invalid insertion axis')
    axis.normalize()
    key = ('SIMPLE_AXIS_V1',) + tuple(_retention_cache_key(source_obj, axis))
    cached = _RETENTION_BVH_CACHE.get(key)
    if cached is not None:
        return cached

    mesh = source_obj.data
    count = len(mesh.vertices)
    if count < 3:
        raise ValueError('The IOS does not contain enough vertices')
    try:
        mesh.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    local = np.empty(count * 3, dtype=np.float64)
    normals_local = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', local)
    mesh.vertices.foreach_get('normal', normals_local)
    local = local.reshape((-1, 3))
    normals_local = normals_local.reshape((-1, 3))

    matrix = np.asarray([[float(source_obj.matrix_world[r][c]) for c in range(4)]
                         for r in range(4)], dtype=np.float64)
    linear = matrix[:3, :3]
    translation = matrix[:3, 3]
    inverse_linear = np.linalg.inv(linear)
    world = local @ linear.T + translation
    # Column-vector normal transform is inverse-transpose; for row vectors this
    # is multiplication by inverse(linear).
    normals_world = normals_local @ inverse_linear
    lengths = np.linalg.norm(normals_world, axis=1)
    valid_lengths = lengths > 1.0e-12
    normals_world[valid_lengths] /= lengths[valid_lengths, None]
    normals_world[~valid_lengths] = np.asarray((0.0, 0.0, 1.0))

    basis_u, basis_v, _ = build_axis_basis(axis)
    axis_np = np.asarray(tuple(axis), dtype=np.float64)
    u_np = np.asarray(tuple(basis_u), dtype=np.float64)
    v_np = np.asarray(tuple(basis_v), dtype=np.float64)
    u = world @ u_np
    v = world @ v_np
    axial = world @ axis_np

    span_u = max(1.0e-6, float(np.max(u) - np.min(u)))
    span_v = max(1.0e-6, float(np.max(v) - np.min(v)))
    cell_size = max(float(RETENTION_SIMPLE_GRID_MIN_MM),
                    min(float(RETENTION_SIMPLE_GRID_MAX_MM),
                        float(RETENTION_SIMPLE_GRID_TARGET_MM)))
    maximum_cells = max(64, int(RETENTION_SIMPLE_GRID_MAX_CELLS))
    cell_size = max(cell_size, max(span_u, span_v) / float(maximum_cells - 2))
    width = max(4, min(maximum_cells, int(math.ceil(span_u / cell_size)) + 2))
    height = max(4, min(maximum_cells, int(math.ceil(span_v / cell_size)) + 2))
    origin_u = float(np.min(u)) - cell_size
    origin_v = float(np.min(v)) - cell_size
    iu = np.clip(np.floor((u - origin_u) / cell_size).astype(np.int32), 0, width - 1)
    iv = np.clip(np.floor((v - origin_v) / cell_size).astype(np.int32), 0, height - 1)
    cell_ids = iv.astype(np.int64) * int(width) + iu.astype(np.int64)
    cell_count = int(width * height)

    envelope = np.full(cell_count, -np.inf, dtype=np.float64)
    occupancy = np.zeros(cell_count, dtype=np.int32)
    np.maximum.at(envelope, cell_ids, axial)
    np.add.at(occupancy, cell_ids, 1)
    sampled_envelope = envelope[cell_ids]
    depth = np.maximum(0.0, sampled_envelope - axial)
    facing = normals_world @ axis_np

    candidate = (
        np.isfinite(sampled_envelope)
        & (occupancy[cell_ids] >= int(RETENTION_SIMPLE_MIN_CELL_VERTICES))
        & (depth > float(RETENTION_MIN_UNDERCUT_MM))
        & (depth <= float(RETENTION_SIMPLE_MAX_DEPTH_MM))
        & (facing < float(RETENTION_SIMPLE_NORMAL_DOT_LIMIT))
    )

    # Cell-level coherence is much cheaper than building full vertex adjacency
    # and prevents an isolated noisy sample from pulling one triangle into a
    # vertical spike.  It validates candidates but never expands the envelope.
    candidate_counts = np.zeros(cell_count, dtype=np.int32)
    np.add.at(candidate_counts, cell_ids[candidate], 1)
    candidate_cells = (candidate_counts > 0).reshape((height, width))
    support = candidate_cells.astype(np.int16)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.zeros_like(candidate_cells, dtype=np.int16)
        src_y0 = max(0, -dy)
        src_y1 = height - max(0, dy)
        src_x0 = max(0, -dx)
        src_x1 = width - max(0, dx)
        dst_y0 = max(0, dy)
        dst_x0 = max(0, dx)
        if src_y1 > src_y0 and src_x1 > src_x0:
            shifted[dst_y0:dst_y0 + (src_y1 - src_y0),
                    dst_x0:dst_x0 + (src_x1 - src_x0)] = \
                candidate_cells[src_y0:src_y1, src_x0:src_x1]
        support += shifted
    support_flat = support.reshape(-1)
    coherent = ((candidate_counts[cell_ids] >= 3)
                | (support_flat[cell_ids] >= int(RETENTION_SIMPLE_MIN_PATCH_CELL_SUPPORT)))
    candidate &= coherent

    clinical = (
        np.isfinite(sampled_envelope)
        & (depth <= float(RETENTION_SIMPLE_FULL_CLEARANCE_DEPTH_MM))
    )
    valid_depths = depth[candidate]
    analysis = {
        'coords_local': local.astype(np.float32),
        'coords_world': world.astype(np.float32),
        'normals_world': normals_world.astype(np.float32),
        'depths_np': depth.astype(np.float32),
        'depths': depth.astype(np.float32),
        'usable_mask_np': candidate,
        'usable_mask': candidate,
        'clinical_mask_np': clinical,
        'candidate_count': int(np.count_nonzero(candidate)),
        'maximum_undercut_depth_mm': float(np.max(valid_depths) if valid_depths.size else 0.0),
        'anatomy_vertex_limit': int(count),
        'grid_width': int(width),
        'grid_height': int(height),
        'grid_cell_mm': float(cell_size),
        'occupied_cells': int(np.count_nonzero(occupancy)),
        'axis_np': axis_np.astype(np.float64),
        'linear': linear,
        'translation': translation,
        'inverse_linear': inverse_linear,
        'method': 'SIMPLE_AXIS_HEIGHTFIELD_NO_DILATION',
    }
    if len(_RETENTION_BVH_CACHE) >= int(RETENTION_CACHE_MAX_ENTRIES):
        _RETENTION_BVH_CACHE.pop(next(iter(_RETENTION_BVH_CACHE)))
    _RETENTION_BVH_CACHE[key] = analysis
    return analysis


def _write_mesh_point_attribute(mesh, name, data_type, values):
    """Write one point-domain attribute with foreach_set when available."""
    try:
        existing = mesh.attributes.get(name)
        if existing is not None and (existing.domain != 'POINT' or existing.data_type != data_type):
            mesh.attributes.remove(existing)
            existing = None
        attribute = existing or mesh.attributes.new(name=name, type=data_type, domain='POINT')
        attribute.data.foreach_set('value', values)
        return True
    except Exception:
        return False


# Removed dead legacy implementation: build_blockout_depthmap_legacy (no production references in DSG 8.9 audit).


def _retention_material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = False
    mat.diffuse_color = tuple(color)
    try:
        mat.blend_method = 'BLEND'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return mat


def _retention_level(props) -> str:
    value = str(getattr(props, 'retention_level', 'AUTO') or 'AUTO').upper()
    # MEDIUM is migrated silently from older .blend files.
    if value == 'MEDIUM':
        value = 'AUTO'
    return value if value in RETENTION_LEVEL_ENGAGEMENT_MM else 'AUTO'


def _retention_engagement_mm(props) -> float:
    return float(RETENTION_LEVEL_ENGAGEMENT_MM[_retention_level(props)])


def _retention_clearance_mm(props) -> float:
    return float(RETENTION_LEVEL_CLEARANCE_MM[_retention_level(props)])


def _retention_draft_angle_deg(props) -> float:
    return float(RETENTION_LEVEL_DRAFT_ANGLE_DEG[_retention_level(props)])


def _retention_fraction(props) -> float:
    """Backward-compatible fraction stored in older DSG files."""
    return float(RETENTION_LEVEL_MAXIMUM_FRACTION[_retention_level(props)])


def _blockout_matches_retention_settings(blockout, props) -> bool:
    if not _valid_obj(blockout) or getattr(blockout, 'type', None) != 'MESH':
        return False
    return (
        str(blockout.get('DSG_retention_level', '')).upper() == _retention_level(props)
        and abs(float(blockout.get('DSG_retention_engagement_mm', -1.0)) - _retention_engagement_mm(props)) <= 1.0e-4
        and abs(
            float(blockout.get('DSG_passive_clearance_mm', -1.0))
            - float(RETENTION_LEVEL_CLEARANCE_MM.get(_retention_level(props), RETENTION_PASSIVE_CLEARANCE_MM))
        ) <= 1.0e-6
        and bool(blockout.get('DSG_retention_analysis_ready', False))
    )


def _retention_preview_object(level=None):
    level = str(level or 'MEDIUM').upper()
    if level not in RETENTION_PREVIEW_NAMES:
        level = 'MEDIUM'
    return bpy.data.objects.get(RETENTION_PREVIEW_NAMES[level])


def _selected_retention_preview(props):
    return _retention_preview_object(_retention_level(props))


def _retention_previews_ready():
    return all(
        _valid_obj(_retention_preview_object(level))
        and _retention_preview_object(level).type == 'MESH'
        and bool(_retention_preview_object(level).get('DSG_retention_analysis_ready', False))
        for level in ('LOW', 'MEDIUM', 'HIGH')
    )


def _remove_retention_previews(remove_blockout=True):
    for name in set(RETENTION_PREVIEW_NAMES.values()):
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            safe_remove_object_with_data(obj)
    for name in set(RETENTION_BOUNDARY_PREVIEW_NAMES.values()):
        obj = bpy.data.objects.get(name)
        if _valid_obj(obj):
            safe_remove_object_with_data(obj)
    if remove_blockout:
        legacy = bpy.data.objects.get(BLOCKOUT_NAME)
        if _valid_obj(legacy):
            safe_remove_object_with_data(legacy)
        manifold_proxy = bpy.data.objects.get('DSG_BlockoutManifoldProxy')
        if _valid_obj(manifold_proxy):
            safe_remove_object_with_data(manifold_proxy)


def _show_selected_retention_preview(props):
    selected = str(getattr(props, 'retention_level', 'MEDIUM') or 'MEDIUM').upper()
    active = None
    for level, name in RETENTION_PREVIEW_NAMES.items():
        obj = bpy.data.objects.get(name)
        if not _valid_obj(obj):
            continue
        visible = level == selected
        _set_obj_hidden(obj, not visible, selectable_when_visible=visible)
        if visible:
            active = obj
    if _valid_obj(active):
        # The opaque IOS masks sub-millimetric differences. During comparison,
        # show only the selected prepared duplicate so LOW/MEDIUM/HIGH are clear.
        props_model = getattr(props, 'model_obj', None)
        if _valid_obj(props_model):
            _set_obj_hidden(props_model, True)
        set_active(bpy.context, active)
        try:
            active.display_type = 'SOLID'
            active.show_transparent = False
            active.color = {
                'LOW': (0.20, 0.62, 0.95, 1.0),
                'MEDIUM': (0.18, 0.82, 0.58, 1.0),
                'HIGH': (0.95, 0.58, 0.16, 1.0),
            }.get(selected, (0.18, 0.82, 0.58, 1.0))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _tag_dsg_view3d_redraw()
    return active


def _build_all_retention_previews(context, model, axis):
    """Build LOW/MEDIUM/HIGH from one immutable model and insertion view.

    The three proposals use the same surveyed maximum coronary perimeter. LOW
    shifts the working line 1 mm occlusally, MEDIUM uses the anatomical maximum,
    and HIGH shifts it 1 mm apically. No remesh is used.
    """
    props = context.scene.dsg_props
    _remove_retention_previews()
    _remove_retention_boundary()
    safe_remove_by_name(COMBINED_NAME)
    created = []
    axis = Vector(axis)
    if axis.length < 1.0e-8:
        raise ValueError('Invalid insertion axis')
    axis.normalize()
    selected = _retention_level(props)
    try:
        for level in ('LOW', 'MEDIUM', 'HIGH'):
            blockout = build_blockout_bvh(
                context, model, axis.copy(),
                passive_clearance_mm=RETENTION_PASSIVE_CLEARANCE_MM,
                retention_engagement_mm=float(RETENTION_LEVEL_ENGAGEMENT_MM[level]),
                selective_retention=True,
                retention_level=level,
                final_quality=False,
            )
            target_name = RETENTION_PREVIEW_NAMES[level]
            blockout.name = target_name
            if blockout.data:
                blockout.data.name = target_name + '_Mesh'
            blockout['DSG_retention_preview'] = True
            blockout['DSG_retention_source_model'] = model.name
            blockout['DSG_retention_shared_axis'] = True
            blockout['DSG_retention_selected'] = bool(level == selected)
            blockout[BLOCKOUT_AXIS_WORLD_KEY] = tuple(round(float(value), 9) for value in axis)
            blockout[BLOCKOUT_AXIS_SOURCE_KEY] = 'MAX_CORONARY_PERIMETER_VIEW_SURVEY'
            blockout[BLOCKOUT_AXIS_CONVENTION_KEY] = BLOCKOUT_AXIS_CONVENTION_V7

            boundary = bpy.data.objects.get(RETENTION_BOUNDARY_NAME)
            if _valid_obj(boundary):
                boundary.name = RETENTION_BOUNDARY_PREVIEW_NAMES[level]
                boundary['DSG_retention_level'] = level
                boundary['DSG_retention_preview'] = True
                boundary[BLOCKOUT_AXIS_WORLD_KEY] = tuple(round(float(value), 9) for value in axis)
            created.append(blockout)
        _show_selected_retention_preview(props)
        return created
    except Exception:
        _remove_retention_previews()
        raise


def _create_max_retention_marker(context, blockout):
    """Mark the exact deepest safe undercut selected for frame drawing."""
    _remove_retention_boundary()
    if not _valid_obj(blockout):
        return None
    try:
        exact_point = json.loads(blockout.get('DSG_maximum_retention_point_world', '[]'))
        exact_normal = json.loads(blockout.get('DSG_maximum_retention_normal_world', '[]'))
        centers = json.loads(blockout.get('DSG_retention_zone_centers_world', '[]'))
        normals = json.loads(blockout.get('DSG_retention_zone_normals_world', '[]'))
    except Exception:
        return None
    if exact_point:
        center = Vector(exact_point)
        normal = Vector(exact_normal) if exact_normal else Vector((0, 0, 1))
    elif centers:
        center = Vector(centers[0])
        normal = Vector(normals[0]) if normals else Vector((0, 0, 1))
    else:
        return None
    if normal.length < 1e-8:
        normal = Vector((0, 0, 1))
    normal.normalize()
    ref = Vector((1, 0, 0)) if abs(normal.x) < 0.85 else Vector((0, 1, 0))
    tangent = normal.cross(ref).normalized()
    bitangent = normal.cross(tangent).normalized()
    radius = max(2.4, RETENTION_ZONE_RADIUS_MM * 0.85)
    offset_center = center + normal * (RETENTION_BOUNDARY_SURFACE_OFFSET_MM + 0.08)
    ring = []
    for i in range(49):
        a = (2.0 * math.pi * i) / 48.0
        ring.append(offset_center + tangent * (math.cos(a) * radius) + bitangent * (math.sin(a) * radius))
    # Crosshair makes the exact opening/maximum point unambiguous.
    cross_a = [offset_center - tangent * radius * 0.55, offset_center + tangent * radius * 0.55]
    cross_b = [offset_center - bitangent * radius * 0.55, offset_center + bitangent * radius * 0.55]
    obj = _create_retention_boundary_object(context, [ring, cross_a, cross_b])
    if _valid_obj(obj):
        obj['DSG_maximum_retention_only'] = True
        obj['DSG_retention_level'] = str(blockout.get('DSG_retention_level', 'MEDIUM'))
        obj['DSG_exact_maximum_depth_mm'] = float(blockout.get('DSG_maximum_retention_sample_depth_mm', 0.0))
        _set_retention_boundary_visible(True)
    return obj

def _survey_retention_zones(bm_src, tree, axis, engagement_mm, axial_offset_mm=0.0):
    """Locate the real maximum usable undercut and define one retention zone.

    LOW, MEDIUM and HIGH must all be derived from the same anatomical maximum,
    not from three unrelated distributed regions.  The returned zone is centred
    on the deepest clinically acceptable sample; the selected level later keeps
    a fraction of that maximum depth.
    """
    verts = bm_src.verts
    if len(verts) < 12:
        return [], {'candidate_count': 0, 'sample_stride': 1}

    stride = max(1, int(math.ceil(len(verts) / float(RETENTION_SAMPLE_LIMIT))))
    ray_offset = 0.002
    candidates = []
    axial_values = [float(verts[index].co.dot(axis)) for index in range(0, len(verts), stride)]
    axial_min = min(axial_values)
    axial_max = max(axial_values)
    crown_floor = axial_min + (axial_max - axial_min) * 0.35

    for index in range(0, len(verts), stride):
        vert = verts[index]
        origin = vert.co + axis * ray_offset
        hit_loc, _, _, _ = tree.ray_cast(origin, axis)
        if hit_loc is None:
            continue
        depth = float((hit_loc - vert.co).dot(axis))
        if not (RETENTION_MIN_UNDERCUT_MM <= depth <= RETENTION_MAX_UNDERCUT_MM):
            continue
        if float(vert.co.dot(axis)) < crown_floor:
            continue
        normal = vert.normal.normalized() if vert.normal.length > 1e-8 else Vector((0.0, 0.0, 0.0))
        facing = float(normal.dot(axis))
        if facing >= -0.025 or facing <= -0.88:
            continue
        angle_score = max(0.0, min(1.0, (-facing) / 0.45))
        candidates.append((vert.co.copy(), normal.copy(), depth, facing, angle_score))

    info = {'candidate_count': len(candidates), 'sample_stride': stride}
    if not candidates:
        return [], info

    # Highest depth wins; angle is only a tie-breaker.
    deepest = max(candidates, key=lambda item: (item[2], item[4]))
    max_point, max_normal, max_depth = deepest[0], deepest[1], float(deepest[2])

    # Refine the local normal without moving the anatomical maximum point.
    local = [item for item in candidates if (item[0] - max_point).length <= RETENTION_ZONE_RADIUS_MM]
    if local:
        weighted_normal = sum((item[1] * (0.25 + item[4]) for item in local), Vector())
        if weighted_normal.length > 1e-8:
            max_normal = weighted_normal.normalized()

    # LOW/MEDIUM/HIGH use the same anatomical maximum but move the working
    # retention line by an explicit, visible distance along the insertion axis.
    axial_offset_mm = float(axial_offset_mm)
    shifted_point = max_point + axis * axial_offset_mm

    info.update({
        'zone_count': 1,
        'maximum_retention_depth_mm': max_depth,
        'maximum_retention_point_world': [float(v) for v in shifted_point],
        'maximum_retention_normal_world': [float(v) for v in max_normal],
        'maximum_retention_sample_depth_mm': max_depth,
        'retention_line_axial_offset_mm': axial_offset_mm,
        'anatomical_maximum_retention_point_world': [float(v) for v in max_point],
    })
    return [(shifted_point.copy(), max_normal.copy())], info


def _blockout_retention_class(point, normal, depth, zones):
    if not zones:
        return 2 if depth > RETENTION_MAX_UNDERCUT_MM else 0
    for center, zone_normal in zones:
        if (point - center).length > RETENTION_ZONE_RADIUS_MM:
            continue
        # Prevent a spherical zone on a thin tooth from engaging the opposite
        # vestibular/lingual surface or a neighbouring interproximal wall.
        if normal.length > 1e-8 and float(normal.normalized().dot(zone_normal)) < 0.48:
            continue
        if RETENTION_MIN_UNDERCUT_MM <= depth <= RETENTION_MAX_UNDERCUT_MM:
            return 1
    return 2 if depth > RETENTION_MAX_UNDERCUT_MM else 0



def _remove_retention_boundary():
    obj = bpy.data.objects.get(RETENTION_BOUNDARY_NAME)
    if _valid_obj(obj):
        safe_remove_object_with_data(obj)


def _set_retention_boundary_visible(visible: bool):
    obj = bpy.data.objects.get(RETENTION_BOUNDARY_NAME)
    if not _valid_obj(obj):
        return
    try:
        obj.hide_set(not bool(visible))
        obj.hide_viewport = not bool(visible)
        obj.hide_render = True
        obj.hide_select = True
        obj.show_in_front = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _retention_boundary_material():
    mat = bpy.data.materials.get(RETENTION_BOUNDARY_MATERIAL_NAME)
    if mat is None:
        mat = bpy.data.materials.new(RETENTION_BOUNDARY_MATERIAL_NAME)
    mat.use_nodes = False
    mat.diffuse_color = (0.08, 0.78, 0.84, 1.0)
    return mat


def _retention_boundary_polylines(bm_src, bm_out, axis):
    """Extract the height-of-contour line where blockout displacement begins.

    ``bm_src`` and ``bm_out`` share topology.  The scalar field is the axial
    displacement introduced by the blockout.  An iso-contour at 0.015 mm gives
    a stable, visible boundary between untouched anatomy and blocked undercut.
    """
    bm_src.verts.ensure_lookup_table()
    bm_out.verts.ensure_lookup_table()
    if len(bm_src.verts) != len(bm_out.verts):
        return []

    axis = Vector(axis).normalized()
    displacement = [
        max(0.0, float((bm_out.verts[index].co - bm_src.verts[index].co).dot(axis)))
        for index in range(len(bm_src.verts))
    ]
    iso = float(RETENTION_BOUNDARY_ISO_MM)
    segments = []

    for face in bm_out.faces:
        if len(face.verts) < 3:
            continue
        face_values = [displacement[vert.index] for vert in face.verts]
        if max(face_values) < iso or min(face_values) > iso:
            continue

        crossings = []
        for edge in face.edges:
            a_out, b_out = edge.verts
            ia, ib = int(a_out.index), int(b_out.index)
            va, vb = displacement[ia], displacement[ib]
            da, db = va - iso, vb - iso
            if abs(da) <= 1e-9 and abs(db) <= 1e-9:
                continue
            if da * db > 0.0:
                continue
            denominator = vb - va
            factor = 0.5 if abs(denominator) <= 1e-12 else (iso - va) / denominator
            factor = max(0.0, min(1.0, float(factor)))
            a_src = bm_src.verts[ia]
            b_src = bm_src.verts[ib]
            point = a_src.co.lerp(b_src.co, factor)
            normal = a_src.normal.lerp(b_src.normal, factor)
            if normal.length > 1e-8:
                normal.normalize()
                point += normal * RETENTION_BOUNDARY_SURFACE_OFFSET_MM
            crossings.append(point.copy())

        unique = []
        for point in crossings:
            if not any((point - other).length <= 1e-5 for other in unique):
                unique.append(point)
        if len(unique) == 2:
            if (unique[0] - unique[1]).length > 1e-5:
                segments.append((unique[0], unique[1]))
        elif len(unique) > 2:
            # Triangulated IOS meshes normally produce two points.  For an
            # occasional n-gon, retain the longest pair instead of branching.
            best = None
            best_distance = 0.0
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    distance = (unique[i] - unique[j]).length
                    if distance > best_distance:
                        best = (unique[i], unique[j])
                        best_distance = distance
            if best is not None and best_distance > 1e-5:
                segments.append(best)

    if not segments:
        return []

    tolerance = max(1e-4, float(RETENTION_BOUNDARY_NODE_TOLERANCE_MM))
    node_sums = {}
    node_counts = {}
    adjacency = {}
    edges = set()

    def node_key(point):
        return tuple(int(round(float(value) / tolerance)) for value in point)

    for point_a, point_b in segments:
        key_a, key_b = node_key(point_a), node_key(point_b)
        if key_a == key_b:
            continue
        for key, point in ((key_a, point_a), (key_b, point_b)):
            node_sums[key] = node_sums.get(key, Vector()) + point
            node_counts[key] = node_counts.get(key, 0) + 1
            adjacency.setdefault(key, set())
        edge_key = tuple(sorted((key_a, key_b)))
        if edge_key in edges:
            continue
        edges.add(edge_key)
        adjacency[key_a].add(key_b)
        adjacency[key_b].add(key_a)

    node_points = {
        key: node_sums[key] / max(1, node_counts[key]) for key in node_sums
    }
    unused = set(edges)
    polylines = []

    def consume_chain(start, next_key):
        chain = [start]
        previous, current = start, next_key
        while True:
            edge_key = tuple(sorted((previous, current)))
            if edge_key not in unused:
                break
            unused.remove(edge_key)
            chain.append(current)
            candidates = [
                item for item in adjacency.get(current, ())
                if item != previous and tuple(sorted((current, item))) in unused
            ]
            if len(candidates) != 1:
                break
            previous, current = current, candidates[0]
        return chain

    # Open chains and junctions first.
    for start in list(adjacency):
        if len(adjacency[start]) == 2:
            continue
        for neighbour in list(adjacency[start]):
            if tuple(sorted((start, neighbour))) in unused:
                chain = consume_chain(start, neighbour)
                if len(chain) >= 2:
                    polylines.append([node_points[key] for key in chain])

    # Remaining degree-two components are closed loops.
    while unused:
        key_a, key_b = next(iter(unused))
        chain = consume_chain(key_a, key_b)
        if len(chain) >= 2:
            if chain[-1] != chain[0] and chain[0] in adjacency.get(chain[-1], set()):
                closing = tuple(sorted((chain[-1], chain[0])))
                if closing in unused:
                    unused.remove(closing)
                    chain.append(chain[0])
            polylines.append([node_points[key] for key in chain])

    filtered = []
    for polyline in polylines:
        length = sum((polyline[index] - polyline[index - 1]).length for index in range(1, len(polyline)))
        if length >= RETENTION_BOUNDARY_MIN_LENGTH_MM:
            filtered.append(polyline)
    return filtered


def _retention_boundary_metrics_fast(bm_src, displacement):
    """Return inexpensive perimeter metrics directly from crossing mesh edges.

    The detailed surgical-cyan polyline is a presentation aid, not part of blockout
    geometry. During the interactive preview we therefore count connected
    crossing-edge components and estimate perimeter length without constructing
    thousands of interpolated points and dictionary nodes.
    """
    iso = float(RETENTION_BOUNDARY_ISO_MM)
    parent = {}
    rank = {}
    crossing_length = 0.0
    crossing_edges = 0

    def find(item):
        root = parent.setdefault(item, item)
        while parent[root] != root:
            parent[root] = parent[parent[root]]
            root = parent[root]
        while parent[item] != item:
            nxt = parent[item]
            parent[item] = root
            item = nxt
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        rank_a, rank_b = rank.get(ra, 0), rank.get(rb, 0)
        if rank_a < rank_b:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank_a == rank_b:
            rank[ra] = rank_a + 1

    for edge in bm_src.edges:
        a = int(edge.verts[0].index)
        b = int(edge.verts[1].index)
        if a >= len(displacement) or b >= len(displacement):
            continue
        da = float(displacement[a]) - iso
        db = float(displacement[b]) - iso
        if da == 0.0 and db == 0.0:
            continue
        if da * db > 0.0:
            continue
        crossing_edges += 1
        crossing_length += float((edge.verts[0].co - edge.verts[1].co).length) * 0.5
        union(a, b)

    roots = {find(item) for item in parent} if parent else set()
    return {
        'loop_count': int(len(roots)),
        'length_mm': float(crossing_length),
        'crossing_edge_count': int(crossing_edges),
    }


def _create_retention_boundary_object(context, polylines):
    _remove_retention_boundary()
    if not polylines:
        return None
    curve = bpy.data.curves.new(RETENTION_BOUNDARY_NAME + '_Data', type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    curve.bevel_depth = 0.085
    curve.bevel_resolution = 2
    curve.fill_mode = 'FULL'
    for points in polylines:
        if len(points) < 2:
            continue
        closed = len(points) > 2 and (points[0] - points[-1]).length <= RETENTION_BOUNDARY_NODE_TOLERANCE_MM * 1.5
        payload = points[:-1] if closed else points
        if len(payload) < 2:
            continue
        spline = curve.splines.new(type='POLY')
        spline.points.add(len(payload) - 1)
        for item, point in zip(spline.points, payload):
            item.co = (float(point.x), float(point.y), float(point.z), 1.0)
        spline.use_cyclic_u = bool(closed)
    if len(curve.splines) == 0:
        bpy.data.curves.remove(curve)
        return None
    obj = bpy.data.objects.new(RETENTION_BOUNDARY_NAME, curve)
    link_object(context, obj)
    obj.data.materials.append(_retention_boundary_material())
    obj.show_in_front = True
    obj.hide_select = True
    obj.hide_render = True
    obj.display_type = 'SOLID'
    register_dsg_object(obj, ROLE_RETENTION_BOUNDARY, RETENTION_BOUNDARY_NAME)
    _set_retention_boundary_visible(False)
    return obj


def _directional_survey_proxy_analysis(bm_src, axis, anatomy_limit):
    """Build a dense insertion-envelope proxy perpendicular to ``axis``.

    This is the deterministic equivalent of the supplied manual workflow that
    subdivides a plane, shrinkwraps it from the selected view and then uses
    proximity weights to identify undercuts.  No Blender modifier is created:
    the proxy exists only as a compact NumPy height field.

    For each transverse grid cell the most coronal/frontmost axial coordinate is
    stored.  A small max-neighbourhood bridges scan tessellation gaps, and every
    source vertex receives a proxy depth plus a local support score.  The source
    mesh is never edited.
    """
    bm_src.verts.ensure_lookup_table()
    count = len(bm_src.verts)
    anatomy_limit = max(0, min(int(anatomy_limit), count))
    if anatomy_limit < 3:
        return [0.0] * count, [0] * count, [0.0] * count, {
            'grid_width': 0, 'grid_height': 0, 'cell_size_mm': 0.0,
            'occupied_cells': 0, 'method': 'insufficient_geometry'}

    axis = Vector(axis)
    if axis.length <= 1.0e-8:
        axis = Vector((0.0, 0.0, 1.0))
    axis.normalize()
    basis_u, basis_v, _ = build_axis_basis(axis)
    u_vec = np.asarray(tuple(basis_u), dtype=np.float64)
    v_vec = np.asarray(tuple(basis_v), dtype=np.float64)
    a_vec = np.asarray(tuple(axis), dtype=np.float64)

    points = np.asarray(
        [tuple(bm_src.verts[index].co) for index in range(anatomy_limit)],
        dtype=np.float64)
    transverse_u = points @ u_vec
    transverse_v = points @ v_vec
    axial = points @ a_vec

    u_min = float(np.min(transverse_u))
    u_max = float(np.max(transverse_u))
    v_min = float(np.min(transverse_v))
    v_max = float(np.max(transverse_v))
    span_u = max(1.0e-6, u_max - u_min)
    span_v = max(1.0e-6, v_max - v_min)

    cell_size = max(
        float(RETENTION_SURVEY_GRID_MIN_MM),
        min(float(RETENTION_SURVEY_GRID_MAX_MM), float(RETENTION_SURVEY_GRID_TARGET_MM)))
    max_cells = max(64, int(RETENTION_SURVEY_GRID_MAX_CELLS))
    required = max(span_u, span_v) / max(1.0, float(max_cells - 5))
    cell_size = max(cell_size, required)
    margin_cells = 2
    width = min(max_cells, max(8, int(math.ceil(span_u / cell_size)) + margin_cells * 2 + 1))
    height_count = min(max_cells, max(8, int(math.ceil(span_v / cell_size)) + margin_cells * 2 + 1))

    origin_u = u_min - margin_cells * cell_size
    origin_v = v_min - margin_cells * cell_size
    indices_u = np.clip(
        np.floor((transverse_u - origin_u) / cell_size).astype(np.int32),
        0, width - 1)
    indices_v = np.clip(
        np.floor((transverse_v - origin_v) / cell_size).astype(np.int32),
        0, height_count - 1)

    heights = np.full((height_count, width), -np.inf, dtype=np.float64)
    occupancy = np.zeros((height_count, width), dtype=np.int32)
    np.maximum.at(heights, (indices_v, indices_u), axial)
    np.add.at(occupancy, (indices_v, indices_u), 1)
    occupied = occupancy > 0

    def shifted(array, dy, dx, fill):
        result = np.full_like(array, fill)
        src_y0 = max(0, -dy)
        src_y1 = array.shape[0] - max(0, dy)
        src_x0 = max(0, -dx)
        src_x1 = array.shape[1] - max(0, dx)
        dst_y0 = max(0, dy)
        dst_y1 = dst_y0 + max(0, src_y1 - src_y0)
        dst_x0 = max(0, dx)
        dst_x1 = dst_x0 + max(0, src_x1 - src_x0)
        if src_y1 > src_y0 and src_x1 > src_x0:
            result[dst_y0:dst_y1, dst_x0:dst_x1] = array[src_y0:src_y1, src_x0:src_x1]
        return result

    envelope = heights.copy()
    support_grid = occupied.astype(np.int16)
    radius = max(0, int(RETENTION_SURVEY_DILATION_CELLS))
    if radius:
        expanded = np.full_like(heights, -np.inf)
        support_sum = np.zeros_like(support_grid)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                expanded = np.maximum(expanded, shifted(heights, dy, dx, -np.inf))
                support_sum += shifted(occupied.astype(np.int16), dy, dx, 0)
        envelope = expanded
        support_grid = support_sum

    sampled_envelope = envelope[indices_v, indices_u]
    sampled_support = support_grid[indices_v, indices_u]
    valid = np.isfinite(sampled_envelope)
    proxy_depth = np.zeros(anatomy_limit, dtype=np.float64)
    proxy_depth[valid] = np.maximum(0.0, sampled_envelope[valid] - axial[valid])

    depths = [0.0] * count
    support = [0] * count
    clinical_weights = [0.0] * count
    full_depth = float(RETENTION_CLINICAL_SURFACE_FULL_DEPTH_MM)
    maximum_depth = max(full_depth + 1.0e-6, float(RETENTION_CLINICAL_SURFACE_MAX_DEPTH_MM))
    fade_span = maximum_depth - full_depth
    for index in range(anatomy_limit):
        depth = float(proxy_depth[index])
        depths[index] = depth
        support[index] = int(sampled_support[index])
        if depth <= full_depth:
            weight = 1.0
        elif depth >= maximum_depth:
            weight = 0.0
        else:
            t = max(0.0, min(1.0, (maximum_depth - depth) / fade_span))
            weight = t * t * (3.0 - 2.0 * t)
        clinical_weights[index] = float(weight)

    cell_ids = [-1] * count
    linear_ids = indices_v.astype(np.int64) * int(width) + indices_u.astype(np.int64)
    for index in range(anatomy_limit):
        cell_ids[index] = int(linear_ids[index])

    return depths, support, clinical_weights, {
        'grid_width': int(width),
        'grid_height': int(height_count),
        'cell_size_mm': float(cell_size),
        'occupied_cells': int(np.count_nonzero(occupied)),
        'dilation_cells': int(radius),
        'maximum_support_cells': int(np.max(sampled_support) if len(sampled_support) else 0),
        '_cell_ids': cell_ids,
        'method': 'DIRECTIONAL_SUBDIVIDED_PLANE_SHRINKWRAP_PROXIMITY_EQUIVALENT',
    }


def _get_cached_blockout_analysis(source_obj, bm_src, axis, selective_retention=True,
                                  retention_engagement_mm=RETENTION_TARGET_ENGAGEMENT_MM,
                                  retention_level='AUTO'):
    """Survey one model + insertion axis and reject non-clinical ray artefacts.

    The old implementation accepted every first BVH hit.  On an open/noisy
    intraoral STL a ray could cross a hole, an interdental space or the complete
    thickness of a crown.  Adjacent vertices then received radically different
    displacements and the original topology was stretched into vertical
    curtains.  This survey keeps only coherent local insertion shadows:

    * vertices close to open/non-manifold borders are excluded;
    * the opposite hit normal must be compatible with the insertion envelope;
    * very deep rays are clamped to a coronal analysis band;
    * isolated depth spikes are removed with a one-ring median test;
    * the resulting field is lightly regularised before the three presets use it.
    """
    key = _retention_cache_key(source_obj, axis)
    cached = _RETENTION_BVH_CACHE.get(key)
    if cached is not None:
        return cached

    bm_src.verts.ensure_lookup_table()
    bm_src.edges.ensure_lookup_table()
    bm_src.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm_src)
    ray_offset = 0.003
    count = len(bm_src.verts)
    try:
        anatomy_limit = int(source_obj.get('DSG_anatomy_original_vertex_count', count))
    except Exception:
        anatomy_limit = count
    anatomy_limit = max(0, min(count, anatomy_limit))

    # Dense integer adjacency is substantially faster than repeatedly walking
    # BMesh link_edges during filtering, regularisation and profile changes.
    adjacency_lists = [[] for _ in range(count)]
    for edge in bm_src.edges:
        a = int(edge.verts[0].index)
        b = int(edge.verts[1].index)
        adjacency_lists[a].append(b)
        adjacency_lists[b].append(a)
    adjacency = [tuple(items) for items in adjacency_lists]
    del adjacency_lists

    # The user view supplies the direction and an optional surface reference.
    # The reference is used only to reject deep basal geometry; it never changes
    # the insertion axis and zoom has no mathematical effect.
    view_reference = None
    axis_owner = get_axis_empty()
    if axis_owner is not None:
        try:
            raw = axis_owner.get(VIEW_REFERENCE_LOCATION_KEY)
            surface_hit = bool(axis_owner.get('DSG_view_reference_surface_hit', False))
            if raw is not None and surface_hit:
                view_reference = Vector(tuple(float(value) for value in raw[:3]))
        except Exception:
            view_reference = None
    try:
        diagonal = float(object_bbox_diagonal(source_obj))
    except Exception:
        diagonal = 40.0
    coronary_depth_limit = max(8.0, min(14.0, diagonal * 0.30))
    coronary_front_limit = max(3.0, min(6.0, diagonal * 0.12))

    # Open scan rims and scan holes are the main source of false long rays.
    border = set()
    for edge in bm_src.edges:
        if len(edge.link_faces) != 2:
            border.update(int(v.index) for v in edge.verts)
    expanded = set(border)
    frontier = set(border)
    for _ in range(max(0, int(RETENTION_BOUNDARY_EXCLUDE_RINGS))):
        nxt = set()
        for index in frontier:
            nxt.update(adjacency[index])
        nxt.difference_update(expanded)
        expanded.update(nxt)
        frontier = nxt
        if not frontier:
            break
    boundary_mask = [False] * count
    for index in expanded:
        if 0 <= index < count:
            boundary_mask[index] = True

    # Reproduce the supplied subdivided-plane/shrinkwrap/proximity survey as a
    # directional height field.  It provides a continuous frontmost insertion
    # envelope; BVH rays below validate the field and prevent bridges across
    # genuine large spaces.
    proxy_depths, proxy_support, clinical_surface_weights, proxy_metadata = _directional_survey_proxy_analysis(
        bm_src, axis, anatomy_limit)
    proxy_metadata = dict(proxy_metadata or {})
    proxy_cell_ids = proxy_metadata.pop('_cell_ids', [-1] * count)

    raw_depths = [0.0] * count
    depths = [0.0] * count
    hit_locations = [None] * count
    hit_normals = [None] * count
    facing_values = [0.0] * count
    usable_mask = [False] * count
    rejected_boundary = 0
    rejected_normal = 0
    rejected_proxy_support = 0
    rejected_nonclinical_surface = 0
    proxy_only_count = 0
    proxy_ray_count = 0
    fast_proxy_count = 0
    bounded_proxy_fallback_count = 0
    direct_ray_cast_count = 0
    ray_cell_cache = {}
    clamped_deep = 0

    for vert in bm_src.verts:
        index = int(vert.index)
        if index >= anatomy_limit:
            continue
        if view_reference is not None:
            axial_from_reference = float((vert.co - view_reference).dot(axis))
            if axial_from_reference < -coronary_front_limit or axial_from_reference > coronary_depth_limit:
                continue
        normal = vert.normal.normalized() if vert.normal.length > 1e-8 else Vector((0.0, 0.0, 1.0))
        facing = float(normal.dot(axis))
        facing_values[index] = facing
        if boundary_mask[index]:
            rejected_boundary += 1
            continue
        # Only the flank hidden from the insertion direction can be retentive.
        if not (-0.96 < facing < -0.015):
            continue

        proxy_depth = float(proxy_depths[index]) if index < len(proxy_depths) else 0.0
        support = int(proxy_support[index]) if index < len(proxy_support) else 0
        clinical_weight = (float(clinical_surface_weights[index])
                           if index < len(clinical_surface_weights) else 0.0)
        if clinical_weight <= 1.0e-6 or proxy_depth > float(RETENTION_CLINICAL_SURFACE_MAX_DEPTH_MM):
            rejected_nonclinical_surface += 1
            continue
        if proxy_depth <= RETENTION_MIN_UNDERCUT_MM:
            continue
        if support < int(RETENTION_SURVEY_MIN_SUPPORT_CELLS):
            rejected_proxy_support += 1
            continue

        # Fast hybrid validation. Shallow, well-supported columns are already
        # stable enough for preview. Deeper/ambiguous columns share one BVH ray
        # per transverse grid cell instead of one ray per dense IOS vertex.
        # If a ray is unavailable, a small bounded proxy value is accepted only
        # when neighbourhood support is strong; later component/median filters
        # still have to confirm topological coherence.
        raw_depth = 0.0
        hit_normal = Vector((0.0, 0.0, 0.0))
        strong_support = support >= int(RETENTION_SURVEY_MIN_SUPPORT_CELLS) + 1
        if (strong_support
                and proxy_depth <= float(RETENTION_SURVEY_FAST_PROXY_DEPTH_MM)):
            raw_depth = min(
                proxy_depth, float(RETENTION_SURVEY_PROXY_ONLY_MAX_DEPTH_MM))
            proxy_only_count += 1
            fast_proxy_count += 1
        else:
            cell_id = (int(proxy_cell_ids[index])
                       if index < len(proxy_cell_ids) else -1)
            ray_record = ray_cell_cache.get(cell_id) if cell_id >= 0 else None
            if ray_record is None:
                hit_loc, first_normal, _, _ = tree.ray_cast(
                    vert.co + axis * ray_offset, axis)
                direct_ray_cast_count += 1
                valid = False
                hit_axial = 0.0
                stored_normal = Vector((0.0, 0.0, 0.0))
                if hit_loc is not None:
                    first_depth = float((hit_loc - vert.co).dot(axis))
                    normal_dot = 1.0
                    if first_normal is not None and first_normal.length > 1e-8:
                        stored_normal = first_normal.normalized()
                        normal_dot = float(stored_normal.dot(axis))
                    maximum_reasonable = max(
                        float(RETENTION_MAX_ANALYSIS_DEPTH_MM)
                        + float(RETENTION_SURVEY_RAY_MAX_EXTRA_MM),
                        proxy_depth + float(RETENTION_SURVEY_RAY_MAX_EXTRA_MM))
                    valid = bool(
                        first_depth > RETENTION_MIN_UNDERCUT_MM
                        and first_depth <= maximum_reasonable
                        and normal_dot >= float(RETENTION_SURVEY_RAY_NORMAL_MIN_DOT))
                    if valid:
                        hit_axial = float(hit_loc.dot(axis))
                    else:
                        rejected_normal += 1
                ray_record = (bool(valid), float(hit_axial), stored_normal.copy())
                if cell_id >= 0:
                    ray_cell_cache[cell_id] = ray_record

            ray_valid, hit_axial, cached_normal = ray_record
            ray_depth = float(hit_axial - vert.co.dot(axis)) if ray_valid else 0.0
            if ray_valid and ray_depth > RETENTION_MIN_UNDERCUT_MM:
                hit_normal = cached_normal.copy()
                if abs(proxy_depth - ray_depth) <= float(RETENTION_SURVEY_RAY_TOLERANCE_MM):
                    blend = max(0.0, min(0.75, float(RETENTION_SURVEY_RAY_BLEND)))
                    raw_depth = proxy_depth * (1.0 - blend) + ray_depth * blend
                else:
                    raw_depth = min(
                        proxy_depth,
                        ray_depth + float(RETENTION_SURVEY_RAY_TOLERANCE_MM))
                proxy_ray_count += 1
            elif (strong_support
                  and proxy_depth <= float(RETENTION_SURVEY_PROXY_ONLY_MAX_DEPTH_MM)):
                raw_depth = proxy_depth
                proxy_only_count += 1
                bounded_proxy_fallback_count += 1
            elif RETENTION_SURVEY_REQUIRE_DIRECT_RAY:
                continue

        if raw_depth <= RETENTION_MIN_UNDERCUT_MM:
            continue
        raw_depths[index] = raw_depth
        depth = min(raw_depth, float(RETENTION_MAX_ANALYSIS_DEPTH_MM))
        if raw_depth > RETENTION_MAX_ANALYSIS_DEPTH_MM:
            clamped_deep += 1
        depths[index] = depth
        hit_locations[index] = vert.co + axis * depth
        hit_normals[index] = hit_normal.copy()
        usable_mask[index] = True

    # Remove small disconnected candidate islands before any smoothing. A true
    # retentive flank is a coherent patch; tiny isolated sets are scan noise and
    # can create long stretched faces when a single vertex is displaced.
    component_removed = 0
    visited = set()
    minimum_component = max(3, int(RETENTION_MIN_CANDIDATE_COMPONENT_VERTICES))
    for seed in range(anatomy_limit):
        if not usable_mask[seed] or seed in visited:
            continue
        stack = [seed]
        visited.add(seed)
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for other in adjacency[current]:
                if other < anatomy_limit and usable_mask[other] and other not in visited:
                    visited.add(other)
                    stack.append(other)
        if len(component) < minimum_component:
            for index in component:
                usable_mask[index] = False
                raw_depths[index] = 0.0
                depths[index] = 0.0
                hit_locations[index] = None
            component_removed += len(component)

    # Remove isolated spikes and cap abrupt one-ring depth jumps.  This is a
    # robust median filter on the scalar undercut field, not a smoothing of the
    # original dental anatomy.
    filtered = list(depths)
    for vert in bm_src.verts:
        index = int(vert.index)
        if not usable_mask[index]:
            continue
        neighbour_depths = [
            depths[other]
            for other in adjacency[index]
            if usable_mask[other]
            and depths[other] > RETENTION_MIN_UNDERCUT_MM
        ]
        if len(neighbour_depths) < int(RETENTION_MIN_COHERENT_NEIGHBOURS):
            usable_mask[index] = False
            filtered[index] = 0.0
            hit_locations[index] = None
            continue
        ordered = sorted(neighbour_depths)
        median = ordered[len(ordered) // 2]
        filtered[index] = min(
            depths[index],
            median + float(RETENTION_DEPTH_NEIGHBOUR_TOLERANCE_MM),
            float(RETENTION_MAX_ANALYSIS_DEPTH_MM),
        )

    # Two conservative regularisation passes reduce scan-frequency striping.
    for _ in range(2):
        updated = list(filtered)
        for vert in bm_src.verts:
            index = int(vert.index)
            if not usable_mask[index]:
                continue
            values = [filtered[index]]
            for other in adjacency[index]:
                if usable_mask[other] and filtered[other] > RETENTION_MIN_UNDERCUT_MM:
                    values.append(filtered[other])
            if len(values) >= 3:
                values.sort()
                median = values[len(values) // 2]
                updated[index] = 0.65 * filtered[index] + 0.35 * median
        filtered = updated

    maximum_depth = 0.0
    maximum_point = None
    maximum_normal = None
    for vert in bm_src.verts:
        index = int(vert.index)
        if not usable_mask[index]:
            continue
        depth = max(0.0, float(filtered[index]))
        depths[index] = depth
        if depth <= RETENTION_MIN_UNDERCUT_MM:
            usable_mask[index] = False
            hit_locations[index] = None
            continue
        hit_locations[index] = vert.co + axis * depth
        if depth > maximum_depth:
            maximum_depth = depth
            maximum_point = vert.co.copy()
            maximum_normal = vert.normal.normalized() if vert.normal.length > 1e-8 else Vector((0.0, 0.0, 1.0))

    cached = {
        'hit_locations': hit_locations,
        'hit_normals': hit_normals,
        'depths': depths,
        'raw_depths': raw_depths,
        'facing_values': facing_values,
        'usable_mask': usable_mask,
        'boundary_mask': boundary_mask,
        'maximum_undercut_depth_mm': float(maximum_depth),
        'maximum_undercut_point_world': [float(v) for v in maximum_point] if maximum_point is not None else [],
        'maximum_undercut_normal_world': [float(v) for v in maximum_normal] if maximum_normal is not None else [],
        'candidate_count': int(sum(1 for value in usable_mask if value)),
        'rejected_boundary_count': int(rejected_boundary),
        'rejected_normal_count': int(rejected_normal),
        'rejected_proxy_support_count': int(rejected_proxy_support),
        'rejected_nonclinical_surface_count': int(rejected_nonclinical_surface),
        'removed_small_component_vertices': int(component_removed),
        'proxy_only_candidate_count': int(proxy_only_count),
        'proxy_ray_candidate_count': int(proxy_ray_count),
        'fast_proxy_candidate_count': int(fast_proxy_count),
        'bounded_proxy_fallback_count': int(bounded_proxy_fallback_count),
        'direct_ray_cast_count': int(direct_ray_cast_count),
        'unique_ray_cell_count': int(len(ray_cell_cache)),
        'proxy_metadata': proxy_metadata,
        'survey_engine_version': int(RETENTION_SURVEY_ENGINE_VERSION),
        'clamped_deep_count': int(clamped_deep),
        'anatomy_vertex_limit': int(anatomy_limit),
        'clinical_surface_weights': clinical_surface_weights,
        'coronary_reference_used': bool(view_reference is not None),
        'coronary_depth_limit_mm': float(coronary_depth_limit),
        'adjacency': adjacency,
    }
    if len(_RETENTION_BVH_CACHE) >= int(RETENTION_CACHE_MAX_ENTRIES):
        _RETENTION_BVH_CACHE.pop(next(iter(_RETENTION_BVH_CACHE)))
    _RETENTION_BVH_CACHE[key] = cached
    return cached


def _smooth_blockout_displacement(bm, displacement, maximum_displacement, iterations, factor,
                                  adjacency=None):
    """Smooth only the scalar blockout field, never the original anatomy.

    ``adjacency`` is cached with the BVH survey. Reusing integer neighbour lists
    avoids repeatedly traversing Python BMesh edge wrappers on dense IOS scans.
    """
    if iterations <= 0 or factor <= 0.0:
        return displacement
    bm.verts.ensure_lookup_table()
    if adjacency is None or len(adjacency) != len(bm.verts):
        adjacency = [tuple(int(edge.other_vert(vert).index) for edge in vert.link_edges)
                     for vert in bm.verts]
    current = list(displacement)
    factor = max(0.0, min(0.65, float(factor)))
    for _ in range(int(iterations)):
        updated = list(current)
        for index, neighbours in enumerate(adjacency):
            if not neighbours:
                continue
            if current[index] <= 1e-9 and not any(current[item] > 1e-9 for item in neighbours):
                continue
            average = sum(current[item] for item in neighbours) / float(len(neighbours))
            value = current[index] * (1.0 - factor) + average * factor
            updated[index] = max(0.0, min(float(maximum_displacement[index]), value))
        current = updated
    return current


def _limit_blockout_displacement_gradient(bm, displacement, maximum_displacement,
                                          iterations=4):
    """Limit impossible per-edge jumps in the axial displacement field.

    This preserves a visible blockout transition while preventing one scan
    vertex from travelling several millimetres farther than its neighbour.
    """
    if iterations <= 0:
        return displacement
    current = list(displacement)
    for _ in range(int(iterations)):
        updated = list(current)
        for edge in bm.edges:
            a = int(edge.verts[0].index)
            b = int(edge.verts[1].index)
            edge_length = max(1e-6, float((edge.verts[0].co - edge.verts[1].co).length))
            allowed = float(RETENTION_DISPLACEMENT_EDGE_BASE_MM) + edge_length * float(RETENTION_DISPLACEMENT_EDGE_SLOPE)
            da, db = current[a], current[b]
            if da > db + allowed:
                updated[a] = min(updated[a], db + allowed, float(maximum_displacement[a]))
            elif db > da + allowed:
                updated[b] = min(updated[b], da + allowed, float(maximum_displacement[b]))
        current = updated
    return current


def _shrinkwrap_proxy_relax_displacement(bm, displacement,
                                           maximum_displacement,
                                           adjacency=None,
                                           final_quality=True):
    """Regularise only the true blockout frontier and keep anatomy anchored.

    This implements the useful geometric principle of the former manual
    non-manifold/relax/fill workflow without context-sensitive operators or
    LoopTools.  The transition is detected from the scalar displacement field,
    expanded by a small number of topological rings and relaxed there only.

    Important invariants:
    * vertices outside the local band remain exactly unchanged (zero);
    * the moved core is never allowed to collapse below its clinically required
      displacement;
    * values are always clamped to the ray-derived insertion envelope;
    * no source vertex, face or triangulation is deleted or globally smoothed.
    """
    bm.verts.ensure_lookup_table()
    count = len(bm.verts)
    if count == 0 or len(displacement) != count:
        return list(displacement), {
            'transition_vertices': 0, 'band_vertices': 0, 'iterations': 0,
            'anchored_vertices': 0, 'method': 'LOCAL_FRONTIER_RELAX_V2'}

    if adjacency is None or len(adjacency) != count:
        adjacency = [tuple(int(edge.other_vert(vert).index) for edge in vert.link_edges)
                     for vert in bm.verts]

    iso = float(RETENTION_BOUNDARY_ISO_MM)
    original = [max(0.0, min(float(maximum_displacement[i]), float(displacement[i])))
                for i in range(count)]
    moved = [value > iso for value in original]

    transition = set()
    for index, neighbours in enumerate(adjacency):
        if neighbours and any(moved[other] != moved[index] for other in neighbours):
            transition.add(index)
    if not transition:
        return original, {
            'transition_vertices': 0, 'band_vertices': 0, 'iterations': 0,
            'anchored_vertices': count, 'method': 'LOCAL_FRONTIER_RELAX_V2'}

    # Build ring distance from the exact frontier.  Only this narrow strip may
    # change; the rest of the duplicate retains bit-for-bit source coordinates.
    ring_distance = {index: 0 for index in transition}
    frontier = set(transition)
    rings = max(1, int(RETENTION_PROXY_RELAX_RINGS))
    for distance in range(1, rings + 1):
        expanded = set()
        for index in frontier:
            expanded.update(adjacency[index])
        expanded.difference_update(ring_distance)
        if not expanded:
            break
        for index in expanded:
            ring_distance[index] = distance
        frontier = expanded
    band = set(ring_distance)

    # Preserve the clinically required moved core.  Relaxation may round a jagged
    # frontier, but it must not reduce vertices well inside the blocked region.
    core_floor = list(original)
    for index in range(count):
        if moved[index] and index not in band:
            core_floor[index] = original[index]
        elif moved[index]:
            core_floor[index] = original[index] * 0.72
        else:
            core_floor[index] = 0.0

    iterations = (int(RETENTION_PROXY_RELAX_FINAL_ITERATIONS)
                  if final_quality else int(RETENTION_PROXY_RELAX_PREVIEW_ITERATIONS))
    factor = max(0.0, min(0.58, float(RETENTION_PROXY_RELAX_FACTOR)))
    median_factor = max(0.0, min(0.35, float(RETENTION_PROXY_MEDIAN_FACTOR)))
    current = list(original)

    for _ in range(max(0, iterations)):
        updated = list(current)
        for index in band:
            neighbours = adjacency[index]
            if not neighbours:
                continue
            values = [current[other] for other in neighbours]
            average = sum(values) / float(len(values))
            ordered = sorted(values + [current[index]])
            median = ordered[len(ordered) // 2]
            blended = (average * (1.0 - median_factor) + median * median_factor)

            # Fade the relaxation towards the outer band.  Outside vertices stay
            # strict zero; this prevents a microscopic offset spreading over the
            # complete arch and preserves the old Ctrl+J behaviour.
            distance = ring_distance.get(index, rings)
            fade = max(0.18, 1.0 - (float(distance) / float(rings + 1)))
            local_factor = factor * fade
            candidate = current[index] * (1.0 - local_factor) + blended * local_factor

            if not moved[index]:
                # An unmoved vertex may only form a short transition ramp when it
                # directly touches moved geometry.  Outer rings remain zero.
                touches_moved = any(moved[other] for other in neighbours)
                if distance >= 2 and not touches_moved:
                    candidate = 0.0
            updated[index] = max(
                float(core_floor[index]),
                min(float(maximum_displacement[index]), float(candidate)))
        current = updated

    current = _limit_blockout_displacement_gradient(
        bm, current, maximum_displacement,
        iterations=2 if final_quality else 1)

    # Re-anchor everything outside the local band after the gradient pass.
    for index in range(count):
        if index not in band:
            current[index] = original[index] if moved[index] else 0.0
        current[index] = max(
            float(core_floor[index]),
            min(float(maximum_displacement[index]), float(current[index])))

    return current, {
        'transition_vertices': int(len(transition)),
        'band_vertices': int(len(band)),
        'iterations': int(iterations),
        'anchored_vertices': int(count - len(band)),
        'method': 'LOCAL_FRONTIER_RELAX_V2',
    }


def _scientific_blockout_profile(level, analysis):
    """Resolve hidden clearance/engagement values from whole-arch geometry.

    Published offset studies support a moderate internal clearance rather than
    a zero-gap fit.  The exact retained undercut is less well standardised, so
    AUTO derives it from robust percentiles of this patient's valid coronary
    undercut field and clamps it to conservative limits.
    """
    level = str(level or 'AUTO').upper()
    if level == 'MEDIUM':
        level = 'AUTO'
    if level not in RETENTION_LEVEL_ENGAGEMENT_MM:
        level = 'AUTO'
    clearance = float(RETENTION_LEVEL_CLEARANCE_MM[level])
    draft = float(RETENTION_LEVEL_DRAFT_ANGLE_DEG[level])
    usable = analysis.get('usable_mask', ())
    depths = analysis.get('depths', ())
    valid_depths = [
        float(depth) for index, depth in enumerate(depths)
        if float(depth) > RETENTION_MIN_UNDERCUT_MM
        and (index >= len(usable) or bool(usable[index]))
    ]
    p50 = _safe_percentile(valid_depths, 50, 0.0)
    p75 = _safe_percentile(valid_depths, 75, p50)
    p90 = _safe_percentile(valid_depths, 90, p75)
    p95 = _safe_percentile(valid_depths, 95, p90)
    maximum = max(valid_depths) if valid_depths else 0.0

    if level == 'AUTO':
        # Robust blend: the median represents the common perimeter, while the
        # upper quartiles keep the fit from being dictated by one isolated tooth.
        adaptive = 0.52 * p50 + 0.33 * p75 + 0.15 * p90
        adaptive -= clearance * 0.10
        engagement = max(
            RETENTION_AUTO_MIN_ENGAGEMENT_MM,
            min(RETENTION_AUTO_MAX_ENGAGEMENT_MM, adaptive),
        )
    else:
        engagement = float(RETENTION_LEVEL_ENGAGEMENT_MM[level])

    return {
        'level': level,
        'clearance_mm': float(clearance),
        'engagement_mm': float(engagement),
        'draft_angle_deg': float(draft),
        'p50_depth_mm': float(p50),
        'p75_depth_mm': float(p75),
        'p90_depth_mm': float(p90),
        'p95_depth_mm': float(p95),
        'maximum_depth_mm': float(maximum),
        'valid_depth_count': int(len(valid_depths)),
    }


def _blockout_insertion_metrics(depths, usable_mask, displacement, clearance_mm):
    """Measure the axial undercut remaining after the current blockout field."""
    remaining = []
    indexed = []
    for index, depth in enumerate(depths):
        depth = float(depth)
        if depth <= RETENTION_MIN_UNDERCUT_MM:
            continue
        if index < len(usable_mask) and not bool(usable_mask[index]):
            continue
        move = float(displacement[index]) if index < len(displacement) else 0.0
        value = max(0.0, depth - move - float(clearance_mm))
        remaining.append(value)
        indexed.append((index, value))
    return {
        'remaining': remaining,
        'indexed': indexed,
        'p50_mm': float(_safe_percentile(remaining, 50, 0.0)),
        'p90_mm': float(_safe_percentile(remaining, 90, 0.0)),
        'p95_mm': float(_safe_percentile(remaining, 95, 0.0)),
        'maximum_mm': float(max(remaining) if remaining else 0.0),
        'candidate_count': int(len(remaining)),
    }


def _raise_neighbours_for_blockout_gradient(bm, displacement, maximum_displacement,
                                             iterations=2):
    """Propagate required correction outward without reducing a validated point.

    A conventional smoothing pass can lower a locally required displacement and
    recreate an insertion interference.  This projection does the opposite: when
    an edge jump is too steep it raises the lower endpoint only.  The source mesh
    is untouched and every value remains bounded by its ray-derived maximum.
    """
    current = list(displacement)
    for _ in range(max(0, int(iterations))):
        updated = list(current)
        changed = False
        for edge in bm.edges:
            a = int(edge.verts[0].index)
            b = int(edge.verts[1].index)
            edge_length = max(1e-6, float((edge.verts[0].co - edge.verts[1].co).length))
            allowed = (float(RETENTION_DISPLACEMENT_EDGE_BASE_MM)
                       + edge_length * float(RETENTION_DISPLACEMENT_EDGE_SLOPE))
            da, db = current[a], current[b]
            if da > db + allowed:
                value = min(float(maximum_displacement[b]), da - allowed)
                if value > updated[b] + 1e-9:
                    updated[b] = value
                    changed = True
            elif db > da + allowed:
                value = min(float(maximum_displacement[a]), db - allowed)
                if value > updated[a] + 1e-9:
                    updated[a] = value
                    changed = True
        current = updated
        if not changed:
            break
    return current


def _smooth_blockout_correction_upward(displacement, maximum_displacement, adjacency,
                                        iterations=2, factor=0.32):
    """Blend the automatic correction while never decreasing blockout."""
    if not adjacency:
        return displacement
    current = list(displacement)
    factor = max(0.0, min(0.60, float(factor)))
    for _ in range(max(0, int(iterations))):
        updated = list(current)
        for index, neighbours in enumerate(adjacency):
            if not neighbours:
                continue
            average = sum(current[other] for other in neighbours) / float(len(neighbours))
            if average <= current[index] + 1e-9:
                continue
            value = current[index] + (average - current[index]) * factor
            updated[index] = min(float(maximum_displacement[index]), max(current[index], value))
        current = updated
    return current


def _auto_correct_blockout_insertion(bm, depths, usable_mask, displacement,
                                     maximum_displacement, clearance_mm,
                                     retention_level, engagement_mm,
                                     adjacency=None, final_quality=True):
    """Automatically project the blockout into a valid axial insertion envelope.

    The initial evidence-informed profile still defines the desired retention.
    This second stage measures the residual axial lock, corrects only values above
    the profile-specific P90/maximum envelope, spreads the correction into a
    manufacturable transition, and rechecks the result.  It replaces the former
    warning/override dialog with an actionable geometric result.
    """
    level = str(retention_level or 'AUTO').upper()
    if level == 'MEDIUM':
        level = 'AUTO'
    if level not in RETENTION_INSERTION_P90_LIMIT_MM:
        level = 'AUTO'

    p90_limit = min(float(engagement_mm), float(RETENTION_INSERTION_P90_LIMIT_MM[level]))
    max_limit = max(p90_limit, min(
        float(engagement_mm) + 0.08,
        float(RETENTION_INSERTION_MAX_LIMIT_MM[level])))
    tolerance = float(RETENTION_INSERTION_VALIDATION_TOLERANCE_MM)
    iterations_limit = (int(RETENTION_INSERTION_FINAL_ITERATIONS)
                        if final_quality else int(RETENTION_INSERTION_PREVIEW_ITERATIONS))
    current = list(displacement)
    initial = list(displacement)
    before = _blockout_insertion_metrics(depths, usable_mask, current, clearance_mm)
    performed = 0

    for iteration in range(iterations_limit):
        metrics = _blockout_insertion_metrics(depths, usable_mask, current, clearance_mm)
        need_p90_projection = metrics['p90_mm'] > p90_limit + tolerance
        changed = False

        # Correct hard local maxima first. If the upper distribution still exceeds
        # P90, project that complete upper tail to the P90 target in the same pass.
        for index, remaining in metrics['indexed']:
            target = max_limit
            if need_p90_projection and remaining > p90_limit:
                target = p90_limit
            if remaining <= target + tolerance:
                continue
            extra = remaining - target
            new_value = min(float(maximum_displacement[index]), current[index] + extra)
            if new_value > current[index] + 1e-9:
                current[index] = new_value
                changed = True

        if not changed:
            performed = iteration
            break

        current = _raise_neighbours_for_blockout_gradient(
            bm, current, maximum_displacement, iterations=2)
        current = _smooth_blockout_correction_upward(
            current, maximum_displacement, adjacency,
            iterations=RETENTION_INSERTION_UPWARD_SMOOTH_ITERATIONS,
            factor=RETENTION_INSERTION_UPWARD_SMOOTH_FACTOR)
        performed = iteration + 1

    # Final hard projection: presentation smoothing must never reintroduce a
    # value outside the validated envelope.
    metrics = _blockout_insertion_metrics(depths, usable_mask, current, clearance_mm)
    need_p90_projection = metrics['p90_mm'] > p90_limit + tolerance
    for index, remaining in metrics['indexed']:
        target = p90_limit if (need_p90_projection and remaining > p90_limit) else max_limit
        if remaining > target + tolerance:
            current[index] = min(
                float(maximum_displacement[index]),
                current[index] + (remaining - target))
    after = _blockout_insertion_metrics(depths, usable_mask, current, clearance_mm)

    corrected_indices = [
        index for index, (old, new) in enumerate(zip(initial, current))
        if new > old + 1e-6
    ]
    additions = [current[index] - initial[index] for index in corrected_indices]
    p90_excess = max(0.0, after['p90_mm'] - p90_limit)
    max_excess = max(0.0, after['maximum_mm'] - max_limit)
    unresolved = bool(p90_excess > tolerance or max_excess > tolerance)

    return current, {
        'status': 'AXIS_CONFLICT' if unresolved else 'OPTIMIZED',
        'unresolved': bool(unresolved),
        'iterations': int(performed),
        'corrected_vertices': int(len(corrected_indices)),
        'corrected_ratio': (float(len(corrected_indices)) / float(max(1, after['candidate_count']))),
        'maximum_added_correction_mm': float(max(additions) if additions else 0.0),
        'mean_added_correction_mm': float(sum(additions) / len(additions) if additions else 0.0),
        'before_p90_mm': float(before['p90_mm']),
        'before_maximum_mm': float(before['maximum_mm']),
        'after_p90_mm': float(after['p90_mm']),
        'after_maximum_mm': float(after['maximum_mm']),
        'p90_limit_mm': float(p90_limit),
        'maximum_limit_mm': float(max_limit),
        'p90_excess_mm': float(p90_excess),
        'maximum_excess_mm': float(max_excess),
        'candidate_count': int(after['candidate_count']),
    }


def _evaluated_mesh_for_blockout(context, source_obj):
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = source_obj.evaluated_get(depsgraph)
    try:
        mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    except TypeError:
        mesh = evaluated.to_mesh()
    if mesh is None:
        raise RuntimeError("No se pudo obtener la malla evaluada del IOS")
    return evaluated, mesh

def build_blockout_bvh(
        context,
        source_obj,
        axis_vec,
        relief_mm=0.10,
        min_hit_mm=BLOCKOUT_MIN_HIT_DEFAULT_MM,
        max_hit_mm=BLOCKOUT_MAX_HIT_DEFAULT_MM,
        output_name=BLOCKOUT_NAME):
    """Blockout v8: el raycast sencillo de v7, con evaluación, filtros y estadísticas."""
    started = time.perf_counter()
    axis = Vector(axis_vec)
    if axis.length <= 1.0e-9:
        raise ValueError("El eje de inserción es nulo")
    axis.normalize()

    relief_mm = max(0.0, float(relief_mm))
    min_hit_mm = max(float(BLOCKOUT_RAY_OFFSET_MM), float(min_hit_mm))
    max_hit_mm = max(0.0, float(max_hit_mm))
    if max_hit_mm > 0.0 and max_hit_mm <= min_hit_mm:
        raise ValueError("El alcance máximo del raycast debe superar la distancia mínima")

    evaluated = None
    evaluated_mesh = None
    bm_src = None
    bm_out = None
    created_mesh = None
    created_object = None
    completed = False
    try:
        evaluated, evaluated_mesh = _evaluated_mesh_for_blockout(context, source_obj)
        if len(evaluated_mesh.vertices) == 0 or len(evaluated_mesh.polygons) == 0:
            raise ValueError("El IOS evaluado no contiene geometría utilizable")

        bm_src = bmesh.new()
        bm_src.from_mesh(evaluated_mesh)
        bm_src.transform(evaluated.matrix_world)
        bm_src.verts.ensure_lookup_table()
        bm_src.faces.ensure_lookup_table()
        tree = BVHTree.FromBMesh(bm_src)
        if tree is None:
            raise RuntimeError("No se pudo construir el BVH del IOS")

        bm_out = bmesh.new()
        bm_out.from_mesh(evaluated_mesh)
        bm_out.transform(evaluated.matrix_world)
        bm_out.verts.ensure_lookup_table()

        moved = 0
        no_hit = 0
        too_near = 0
        too_far = 0
        hidden_by_relief = 0
        move_sum = 0.0
        move_max = 0.0
        hit_sum = 0.0
        hit_max = 0.0

        for vert in bm_out.verts:
            origin = vert.co + axis * float(BLOCKOUT_RAY_OFFSET_MM)
            hit_loc, _hit_normal, _hit_index, _hit_distance = tree.ray_cast(origin, axis)
            if hit_loc is None:
                no_hit += 1
                continue

            hit_delta = float((hit_loc - vert.co).dot(axis))
            if hit_delta <= min_hit_mm:
                too_near += 1
                continue
            if max_hit_mm > 0.0 and hit_delta > max_hit_mm:
                too_far += 1
                continue

            effective_move = hit_delta - relief_mm
            # Evita el fallo de v7 por el que una colisión menor que el alivio
            # desplazaba el vértice en dirección contraria al raycast.
            if effective_move <= 0.0:
                hidden_by_relief += 1
                continue

            vert.co += axis * effective_move
            moved += 1
            move_sum += effective_move
            move_max = max(move_max, effective_move)
            hit_sum += hit_delta
            hit_max = max(hit_max, hit_delta)

        if bm_out.faces:
            bmesh.ops.recalc_face_normals(bm_out, faces=bm_out.faces[:])

        created_mesh = bpy.data.meshes.new(output_name + "_Mesh")
        bm_out.to_mesh(created_mesh)
        created_mesh.validate(clean_customdata=False)
        created_mesh.update(calc_edges=True)
        if len(created_mesh.vertices) == 0 or len(created_mesh.polygons) == 0:
            raise RuntimeError("El blockout resultante quedó vacío")

        created_object = bpy.data.objects.new(output_name, created_mesh)
        context.collection.objects.link(created_object)
        blockout = created_object

        material = (bpy.data.materials.get("DSG_BlockoutMat")
                    or bpy.data.materials.new("DSG_BlockoutMat"))
        material.use_nodes = False
        material.diffuse_color = (0.2, 0.6, 1.0, 0.35)
        try:
            material.blend_method = 'BLEND'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        blockout.data.materials.clear()
        blockout.data.materials.append(material)
        try:
            blockout.show_transparent = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        elapsed = max(0.0, time.perf_counter() - started)
        total = len(created_mesh.vertices)
        blockout["DSG_blockout_engine"] = BLOCKOUT_ENGINE_ID
        blockout["DSG_source_object"] = source_obj.name
        blockout["DSG_used_evaluated_mesh"] = True
        blockout["DSG_axis"] = [float(axis.x), float(axis.y), float(axis.z)]
        blockout["DSG_relief_mm"] = relief_mm
        blockout["DSG_ray_offset_mm"] = float(BLOCKOUT_RAY_OFFSET_MM)
        blockout["DSG_min_hit_mm"] = min_hit_mm
        blockout["DSG_max_hit_mm"] = max_hit_mm
        blockout["DSG_vertices_total"] = total
        blockout["DSG_vertices_moved"] = moved
        blockout["DSG_rays_without_hit"] = no_hit
        blockout["DSG_hits_too_near"] = too_near
        blockout["DSG_hits_too_far"] = too_far
        blockout["DSG_hits_below_relief"] = hidden_by_relief
        blockout["DSG_mean_move_mm"] = (move_sum / moved) if moved else 0.0
        blockout["DSG_max_move_mm"] = move_max
        blockout["DSG_mean_hit_mm"] = (hit_sum / moved) if moved else 0.0
        blockout["DSG_max_hit_found_mm"] = hit_max
        blockout["DSG_elapsed_seconds"] = elapsed
        completed = True
        return blockout
    finally:
        if bm_src is not None:
            bm_src.free()
        if bm_out is not None:
            bm_out.free()
        if evaluated is not None and evaluated_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if not completed:
            if created_object is not None and _valid_obj(created_object):
                try:
                    safe_remove_object(created_object)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            elif created_mesh is not None:
                try:
                    if created_mesh.users == 0:
                        bpy.data.meshes.remove(created_mesh)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)



def _set_principled_input(bsdf, names, value):
    """Assign a Principled input across Blender 4/5 naming differences."""
    if bsdf is None:
        return False
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is None:
            continue
        try:
            socket.default_value = value
            return True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False


def _blockout_zone_visual_material():
    """Clinical teal material used only to review the added blockout surface."""
    material = (bpy.data.materials.get('DSG_BlockoutZoneVisualMat')
                or bpy.data.materials.new('DSG_BlockoutZoneVisualMat'))
    material.use_nodes = True
    material.diffuse_color = (0.02, 0.46, 0.54, 1.0)
    try:
        nodes = material.node_tree.nodes
        bsdf = nodes.get('Principled BSDF')
        _set_principled_input(bsdf, ('Base Color',), (0.015, 0.34, 0.42, 1.0))
        _set_principled_input(bsdf, ('Roughness',), 0.22)
        _set_principled_input(bsdf, ('Metallic',), 0.04)
        _set_principled_input(bsdf, ('Coat Weight', 'Clearcoat'), 0.30)
        _set_principled_input(bsdf, ('Coat Roughness', 'Clearcoat Roughness'), 0.12)
        _set_principled_input(
            bsdf, ('Emission Color', 'Emission'), (0.01, 0.18, 0.22, 1.0))
        _set_principled_input(bsdf, ('Emission Strength',), 0.35)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def _ensure_blockout_zone_visual(context, original_obj=None, blockout_obj=None,
                                  force_rebuild=False):
    """Create a non-exportable overlay containing only blockout-added faces.

    The original IOS and the raycast blockout share evaluated topology. Faces
    whose vertices moved along the insertion axis are copied into a separate
    mesh, offset 0.015 mm along their normals and shown with a mild teal
    emission. This is visual metadata only; it never enters Boolean or STL data.
    """
    existing = bpy.data.objects.get(BLOCKOUT_VISUAL_NAME)
    if _valid_obj(existing) and not force_rebuild:
        return existing
    if _valid_obj(existing):
        safe_remove_object(existing)

    blockout_obj = blockout_obj if _valid_obj(blockout_obj) else bpy.data.objects.get(BLOCKOUT_NAME)
    if not _valid_obj(blockout_obj) or blockout_obj.type != 'MESH':
        return None

    if not _valid_obj(original_obj):
        source_name = str(blockout_obj.get('DSG_source_object', '') or '')
        original_obj = bpy.data.objects.get(source_name)
    if not _valid_obj(original_obj) or original_obj.type != 'MESH':
        return None

    evaluated = None
    evaluated_mesh = None
    try:
        evaluated, evaluated_mesh = _evaluated_mesh_for_blockout(context, original_obj)
        if len(evaluated_mesh.vertices) != len(blockout_obj.data.vertices):
            return None
        if len(evaluated_mesh.polygons) != len(blockout_obj.data.polygons):
            return None

        source_world = [evaluated.matrix_world @ vertex.co
                        for vertex in evaluated_mesh.vertices]
        blockout_world = [blockout_obj.matrix_world @ vertex.co
                          for vertex in blockout_obj.data.vertices]

        axis_values = blockout_obj.get(BLOCKOUT_AXIS_WORLD_KEY, blockout_obj.get('DSG_axis'))
        try:
            axis = Vector(axis_values)
        except Exception:
            axis = Vector((0.0, 0.0, 1.0))
        if axis.length <= 1.0e-10:
            axis = Vector((0.0, 0.0, 1.0))
        axis.normalize()

        moved = []
        epsilon = float(BLOCKOUT_VISUAL_CHANGE_EPS_MM)
        for source_co, blockout_co in zip(source_world, blockout_world):
            delta = blockout_co - source_co
            moved.append(bool(delta.dot(axis) > epsilon or delta.length > epsilon * 1.5))

        selected_polygons = [
            polygon for polygon in blockout_obj.data.polygons
            if any(moved[index] for index in polygon.vertices)
        ]
        if not selected_polygons:
            return None

        used_indices = sorted({
            int(index)
            for polygon in selected_polygons
            for index in polygon.vertices
        })
        remap = {source_index: new_index
                 for new_index, source_index in enumerate(used_indices)}

        try:
            normal_matrix = blockout_obj.matrix_world.to_3x3().inverted().transposed()
        except Exception:
            normal_matrix = blockout_obj.matrix_world.to_3x3()
        offset = float(BLOCKOUT_VISUAL_SURFACE_OFFSET_MM)
        vertices = []
        for source_index in used_indices:
            normal = normal_matrix @ blockout_obj.data.vertices[source_index].normal
            if normal.length > 1.0e-10:
                normal.normalize()
            else:
                normal = axis.copy()
            vertices.append(tuple(blockout_world[source_index] + normal * offset))
        faces = [tuple(remap[int(index)] for index in polygon.vertices)
                 for polygon in selected_polygons]

        mesh = bpy.data.meshes.new(BLOCKOUT_VISUAL_NAME + '_Mesh')
        mesh.from_pydata(vertices, [], faces)
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        if len(mesh.polygons) == 0:
            bpy.data.meshes.remove(mesh)
            return None

        visual = bpy.data.objects.new(BLOCKOUT_VISUAL_NAME, mesh)
        link_object(context, visual)
        visual.matrix_world = Matrix.Identity(4)
        visual.data.materials.clear()
        visual.data.materials.append(_blockout_zone_visual_material())
        visual.display_type = 'SOLID'
        visual.hide_render = True
        visual.hide_select = True
        try:
            visual.show_in_front = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        visual['DSG_visual_only'] = True
        visual['DSG_exclude_from_export'] = True
        visual['DSG_blockout_visual_faces'] = int(len(mesh.polygons))
        visual['DSG_blockout_visual_offset_mm'] = float(offset)
        visual['DSG_blockout_visual_source'] = str(blockout_obj.name)
        register_dsg_object(visual, ROLE_BLOCKOUT_VISUAL, BLOCKOUT_VISUAL_NAME)
        _set_obj_hidden(visual, True, selectable_when_visible=False)
        return visual
    finally:
        if evaluated is not None and evaluated_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def is_valid_implant_obj(obj):
    return (obj is not None
            and _valid_obj(obj)
            and obj.type == 'MESH'
            and obj.name.startswith(IMPLANT_PREFIX)
            and not obj.name.startswith(IMPLANT_EMERGENCE_LEGACY_PREFIX)
            and not bool(obj.get('DSG_implant_emergence_tube', False)))


def get_all_implant_objects(props=None):
    """Devuelve todos los implantes DSG presentes en escena, sin duplicados."""
    implants = []
    seen = set()

    if props and is_valid_implant_obj(getattr(props, 'implant_obj', None)):
        implants.append(props.implant_obj)
        seen.add(props.implant_obj.name)

    for obj in bpy.data.objects:
        if is_valid_implant_obj(obj) and obj.name not in seen:
            implants.append(obj)
            seen.add(obj.name)

    return sorted(implants, key=lambda o: o.name)


def count_implants(props=None):
    return len(get_all_implant_objects(props))


def irrigation_implant_is_sealed(implant_obj):
    """Return the persisted selective-irrigation state for one implant.

    OPEN is the conservative default.  The state lives on the implant object so
    repeated panel redraws and Blender file saves do not create auxiliary
    collections or records.
    """
    if not is_valid_implant_obj(implant_obj):
        return False
    try:
        return bool(implant_obj.get('DSG_irrigation_sealed', False))
    except Exception:
        return False


def set_irrigation_implant_sealed(implant_obj, sealed):
    if not is_valid_implant_obj(implant_obj):
        return False
    try:
        implant_obj['DSG_irrigation_sealed'] = bool(sealed)
        implant_obj['DSG_irrigation_gate_mode'] = (
            IRRIGATION_FRANGIBLE_SEAL_MODE if sealed else 'OPEN')
        return True
    except Exception:
        return False


def auto_assign_irrigation_gate_defaults(props):
    """Keep the first irrigated implant open and seal every later outlet.

    The order is the order in which implants first appear in the saved irrigation
    paths. This makes the behaviour deterministic for direct channels and linked
    branches, and preserves a manual OPEN override only until the path list changes.
    """
    ordered_names = []
    try:
        for entry in load_irrigation_path_entries(props):
            name = str(entry.get('implant_name') or '')
            if name and name not in ordered_names:
                ordered_names.append(name)
    except Exception:
        ordered_names = []

    # Before irrigation exists, use implant creation order so Implant 2+ already
    # carries the intended default when the user reaches the irrigation step.
    if not ordered_names:
        ordered_names = [obj.name for obj in get_all_implant_objects(props)]

    changed = []
    for index, name in enumerate(ordered_names):
        implant = bpy.data.objects.get(name)
        if not is_valid_implant_obj(implant):
            continue
        sealed = index > 0
        previous = irrigation_implant_is_sealed(implant)
        set_irrigation_implant_sealed(implant, sealed)
        try:
            implant['DSG_irrigation_gate_auto_index'] = int(index + 1)
            implant['DSG_irrigation_gate_auto_default'] = True
            implant['DSG_irrigation_internal_marker'] = bool(sealed)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if previous != sealed:
            changed.append(implant.name)
    # Linked networks: the order of opening follows the trunk geometry (from
    # the initial sleeve towards the inlet), not the order of creation.
    try:
        changed.extend(refresh_irrigation_network_roles(props))
    except Exception as exc:
        _DSG_LOG.warning('irrigation network roles not refreshed: %s', exc, exc_info=True)
    return changed


def irrigation_path_implant_names(props):
    """Names of implants that actually have a confirmed irrigation branch."""
    names = set()
    try:
        for entry in load_irrigation_path_entries(props):
            name = entry.get('implant_name')
            if name:
                names.add(str(name))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return names


def get_sealed_irrigation_implants(props, require_confirmed_path=True):
    path_names = irrigation_path_implant_names(props) if require_confirmed_path else None
    result = []
    for implant in get_all_implant_objects(props):
        if not irrigation_implant_is_sealed(implant):
            continue
        if path_names is not None and implant.name not in path_names:
            continue
        result.append(implant)
    return result


def sync_irrigation_gate_metadata(guide_obj, props):
    """Store a portable summary on the guide without creating geometry."""
    if not _valid_obj(guide_obj):
        return []
    names = [obj.name for obj in get_sealed_irrigation_implants(
        props, require_confirmed_path=True)]
    try:
        guide_obj['DSG_irrigation_sealed_implants'] = json.dumps(names)
        guide_obj['DSG_irrigation_frangible_seal_count'] = int(len(names))
        guide_obj['DSG_irrigation_frangible_seal_center_thickness_mm'] = float(
            IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED)
        guide_obj['DSG_irrigation_frangible_seal_rim_thickness_mm'] = float(
            IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED)
        guide_obj['DSG_irrigation_frangible_seal_mode'] = (
            IRRIGATION_FRANGIBLE_SEAL_MODE if names else 'NONE')
        guide_obj['DSG_irrigation_frangible_marker_shape'] = FRANGIBLE_MARKER_SHAPE
        guide_obj['DSG_irrigation_frangible_marker_depth_mm'] = float(
            frangible_seal_design().countersink_depth_mm)
        guide_obj['DSG_irrigation_frangible_seal_export_only'] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return names


def get_implant_nominal_diameter_world(props, implant_obj):
    """Diámetro clínico del implante, incluyendo una posible escala XY del objeto."""
    fallback = max(0.10, float(getattr(props, 'implant_diameter', 4.0)))
    if not is_valid_implant_obj(implant_obj):
        return fallback
    try:
        nominal = max(0.10, float(implant_obj.get('DSG_implant_diameter', fallback)))
    except Exception:
        nominal = fallback
    try:
        scale = implant_obj.matrix_world.to_scale()
        radial_scale = max(abs(float(scale.x)), abs(float(scale.y)), 1e-6)
    except Exception:
        radial_scale = 1.0
    return nominal * radial_scale


def get_implant_platform_center_world(props, implant_obj):
    """Centro world-space de la plataforma coronal (extremo +Z local)."""
    if not is_valid_implant_obj(implant_obj):
        return None
    try:
        platform_local_z = max(float(corner[2]) for corner in implant_obj.bound_box)
        return implant_obj.matrix_world @ Vector((0.0, 0.0, platform_local_z))
    except Exception:
        return implant_obj.matrix_world.translation.copy()


def measure_interimplant_platform_clearance(props, implant_a, implant_b):
    """Mide la distancia libre horizontal entre plataformas adyacentes.

    La diferencia de centros se proyecta sobre el plano perpendicular al eje
    medio de ambos implantes. De este modo, una diferencia corono-apical no
    puede falsear como segura una separación mesiodistal insuficiente.
    """
    center_a = get_implant_platform_center_world(props, implant_a)
    center_b = get_implant_platform_center_world(props, implant_b)
    if center_a is None or center_b is None:
        return None

    axis_a = get_implant_axis_world(props, implant_a)
    axis_b = get_implant_axis_world(props, implant_b)
    if axis_a.length < 1e-8:
        axis_a = Vector((0.0, 0.0, 1.0))
    if axis_b.length < 1e-8:
        axis_b = axis_a.copy()
    axis_a.normalize()
    axis_b.normalize()
    if axis_a.dot(axis_b) < 0.0:
        axis_b.negate()
    plane_normal = axis_a + axis_b
    if plane_normal.length < 1e-8:
        plane_normal = axis_a.copy()
    plane_normal.normalize()

    delta = center_b - center_a
    horizontal = delta - plane_normal * delta.dot(plane_normal)
    center_distance = float(horizontal.length)
    diameter_a = get_implant_nominal_diameter_world(props, implant_a)
    diameter_b = get_implant_nominal_diameter_world(props, implant_b)
    required_center_distance = (
        diameter_a * 0.5 + diameter_b * 0.5 + INTERIMPLANT_MIN_CLEARANCE_MM)
    clearance = center_distance - diameter_a * 0.5 - diameter_b * 0.5
    return {
        'implant_a': implant_a,
        'implant_b': implant_b,
        'center_distance_mm': center_distance,
        'required_center_distance_mm': required_center_distance,
        'clearance_mm': clearance,
        'deficit_mm': max(0.0, INTERIMPLANT_MIN_CLEARANCE_MM - clearance),
    }
