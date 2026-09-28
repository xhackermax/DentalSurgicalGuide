def _smooth_boundary_to_plane(bm, boundary_verts, direction, plane_projection,
                              iterations=10, factor=0.35):
    boundary_set = set(boundary_verts)
    direction = Vector(direction).normalized()
    for vert in boundary_set:
        vert.co += direction * (float(plane_projection) - float(vert.co.dot(direction)))
    for _ in range(max(0, int(iterations))):
        updates = {}
        for vert in boundary_set:
            neighbours = [edge.other_vert(vert) for edge in vert.link_edges
                          if edge.other_vert(vert) in boundary_set]
            if not neighbours:
                continue
            average = sum((other.co for other in neighbours), Vector()) / len(neighbours)
            candidate = vert.co.lerp(average, float(factor))
            candidate += direction * (float(plane_projection) - float(candidate.dot(direction)))
            updates[vert] = candidate
        for vert, coordinate in updates.items():
            vert.co = coordinate


def _close_open_model_flatten_remesh(context, source_obj):
    """Last-resort Easy-Dental-style closure: flatten open vertices then remesh.

    The supplied Easy Dental CAD code moves the non-manifold rim to a common
    plane and reconstructs the object with a smooth remesh. DSG keeps that core
    strategy, but uses the estimated dental base direction rather than global Z,
    performs a local boundary relaxation, preserves a hidden source copy and
    verifies the final topology transactionally.
    """
    closed = duplicate_object_with_data(context, source_obj, CLOSED_MODEL_NAME)
    closed.matrix_world = source_obj.matrix_world.copy()
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(closed.data)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        try:
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
            bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1.0e-7)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        wire = [edge for edge in bm.edges if len(edge.link_faces) == 0]
        if wire:
            try:
                bmesh.ops.delete(bm, geom=wire, context='EDGES')
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        boundary_verts = {vert for edge in boundary_edges for vert in edge.verts}
        if not boundary_verts:
            raise RuntimeError('No open border vertices were found for flattening')
        direction, diagnostics = _automatic_base_direction(
            bm, list(boundary_verts), source_obj=source_obj, return_diagnostics=True)
        projections = [float(vert.co.dot(direction)) for vert in bm.verts]
        boundary_projection = [float(vert.co.dot(direction)) for vert in boundary_verts]
        coords = [vert.co for vert in bm.verts]
        mins = Vector((min(value[index] for value in coords) for index in range(3)))
        maxs = Vector((max(value[index] for value in coords) for index in range(3)))
        diagonal = float((maxs - mins).length)
        diagonal_mm = diagonal * _object_average_world_scale(source_obj)
        base_depth_mm = max(AUTO_BASE_MIN_DEPTH_MM,
                            min(AUTO_BASE_MAX_DEPTH_MM, diagonal_mm * AUTO_BASE_DEPTH_FRACTION))
        plane_projection = max(
            _safe_percentile(boundary_projection, 88),
            _safe_percentile(projections, 94)) + _mm_to_object_units(source_obj, base_depth_mm * 0.35)
        _smooth_boundary_to_plane(
            bm, boundary_verts, direction, plane_projection,
            iterations=12, factor=0.32)
        bm.edges.ensure_lookup_table()
        for component in _boundary_edge_components(
                [edge for edge in bm.edges if len(edge.link_faces) == 1]):
            try:
                bmesh.ops.holes_fill(bm, edges=component, sides=0)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.normal_update(); bm.to_mesh(closed.data); closed.data.update()
    except Exception:
        if bm is not None:
            bm.free(); bm = None
        safe_remove_object_with_data(closed)
        raise
    finally:
        if bm is not None:
            bm.free()

    voxel_mm = max(0.16, min(0.24, diagonal_mm / 420.0))
    voxel = _mm_to_object_units(source_obj, voxel_mm)
    if not _run_voxel_remesh_operator(context, closed, voxel):
        safe_remove_object_with_data(closed)
        raise RuntimeError('Flatten-and-remesh fallback could not reconstruct the model')
    try:
        remove_disconnected_islands_keep_largest(
            closed, reason='flattened dental model base closure', max_vertices=3000000)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _clear_model_topology_cache()
    report = get_model_topology_report_cached(closed)
    if report.get('checked') and not report.get('solid'):
        safe_remove_object_with_data(closed)
        raise RuntimeError(
            'Flatten-and-remesh closure remained non-manifold '
            f"(boundary edges: {report.get('boundary_edges')}, branch edges: {report.get('branch_edges')})")
    closed['DSG_base_closure_status'] = 'flatten_relax_voxel_fallback'
    closed['DSG_base_closed_manifold'] = bool(report.get('solid', False))
    closed['DSG_base_depth_mm'] = float(base_depth_mm)
    closed['DSG_base_voxel_mm'] = float(voxel_mm)
    closed['DSG_base_direction_local'] = tuple(float(value) for value in direction)
    closed['DSG_base_direction_confidence'] = float(diagnostics.get('confidence', 0.0))
    closed['DSG_base_direction_method'] = str(diagnostics.get('method', 'unknown'))
    closed['DSG_source_open_model_name'] = str(source_obj.name)
    return closed, report


def close_open_dental_model_base(context, source_obj, perimeter_obj=None):
    """Close an open dental model without reconstructing its anatomy.

    Base closure is now topology-only. Volumetric and flatten/remesh fallbacks
    are intentionally disabled because they can modify tooth surfaces. Failure
    is preferable to silently changing clinically relevant geometry.
    """
    if not _valid_obj(source_obj) or source_obj.type != 'MESH':
        raise RuntimeError('No valid dental mesh was found')

    report = get_model_topology_report_cached(source_obj)
    if _workflow_closed_boundary_passes(report):
        source_obj['DSG_base_closure_status'] = 'already_solid'
        source_obj['DSG_base_closed_manifold'] = True
        source_obj['DSG_remesh_used_for_base_closure'] = False
        source_obj[CLOSED_MODEL_ACCEPTED_FLAG] = True
        return source_obj, report

    if not bool(source_obj.get(SCAN_HOLES_PROCESSED_FLAG, False)):
        raise RuntimeError(
            'Close/review secondary scan holes first. This intermediate step '
            'preserves the basal opening and does not use remesh')

    existing = bpy.data.objects.get(CLOSED_MODEL_NAME)
    if _valid_obj(existing) and existing is not source_obj:
        safe_remove_object_with_data(existing)

    # No hidden fallback is allowed here. The direct routine either adds only
    # basal faces or aborts and preserves the original scan exactly.
    closed, final_report = _close_open_model_direct(
        context, source_obj, perimeter_obj=perimeter_obj)

    source_obj[OPEN_MODEL_BACKUP_FLAG] = True
    source_obj['DSG_closed_model_name'] = CLOSED_MODEL_NAME
    closed[CLOSED_MODEL_ACCEPTED_FLAG] = True
    closed[EXTERNAL_CLOSED_MODEL_FLAG] = False
    register_dsg_object(closed, ROLE_MODEL, CLOSED_MODEL_NAME)
    _set_obj_hidden(source_obj, True, selectable_when_visible=False)
    _set_obj_hidden(closed, False, selectable_when_visible=True)
    if _valid_obj(perimeter_obj):
        _set_obj_hidden(perimeter_obj, True, selectable_when_visible=False)
    set_active(context, closed)
    return closed, final_report


class DSG_OT_AcceptClosedIOSModel(Operator):
    bl_idname = 'dsg.accept_closed_ios_model'
    bl_label = 'Use Closed IOS Model and Continue'
    bl_description = (
        'Accepts an IOS model that was already closed in another program after '
        'verifying that it is a manifold solid; no geometry is modified')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(model) or model.type != 'MESH':
            _dsg_report(
                self, {'ERROR'},
                'No aligned dental mesh was found',
                'No se encontró un modelo dental alineado')
            return {'CANCELLED'}

        _clear_model_topology_cache()
        report = get_model_topology_report_cached(model)
        if not report.get('checked'):
            _dsg_report(
                self, {'ERROR'},
                'The model topology could not be verified',
                'No se pudo verificar la topología del modelo')
            return {'CANCELLED'}
        if not _workflow_closed_boundary_passes(report):
            _dsg_report(
                self, {'ERROR'},
                'The selected model still has open boundary edges',
                'El modelo seleccionado todavía tiene aristas de borde abiertas')
            return {'CANCELLED'}

        model[SCAN_HOLES_PROCESSED_FLAG] = True
        model[CLOSED_MODEL_ACCEPTED_FLAG] = True
        model[EXTERNAL_CLOSED_MODEL_FLAG] = True
        model['DSG_base_closure_status'] = 'external_closed_model_accepted'
        model['DSG_base_closed_manifold'] = True
        model['DSG_remesh_used_for_base_closure'] = False
        model['DSG_external_model_topology_report'] = json.dumps({
            'boundary_edges': int(report.get('boundary_edges') or 0),
            'branch_edges': int(report.get('branch_edges') or 0),
            'wire_edges': int(report.get('wire_edges') or 0),
            'solid': bool(report.get('solid', False)),
        }, ensure_ascii=False)

        props.model_obj = register_dsg_object(model, ROLE_MODEL, model.name)
        _remove_retention_previews()
        _clear_retention_geometry_cache()
        _remove_retention_boundary()
        safe_remove_by_name(BLOCKOUT_NAME)
        safe_remove_by_name(COMBINED_NAME)
        context.scene[SUITE_STAGE_KEY] = 'DSG'
        props.current_step = STEP_MODEL
        _isolate_ios_for_guide(context, model)
        _set_obj_hidden(model, False, selectable_when_visible=True)
        set_active(context, model)

        _dsg_report(
            self, {'INFO'},
            'Closed manifold IOS accepted; continue with insertion direction and blockout',
            'IOS cerrado y manifold aceptado; continúa con la dirección de inserción y el blockout')
        return {'FINISHED'}


class DSG_OT_CloseModelBase(Operator):
    bl_idname = 'dsg.close_model_base'
    bl_label = 'Close Model Base Automatically'
    bl_description = (
        'After the scan-hole review, duplicates the scan and adds only basal '
        'walls and a cap. Tooth vertices are locked; no remesh is used')
    bl_options = {'REGISTER', 'UNDO'}

    use_drawn_perimeter: BoolProperty(
        name='Use Visible Perimeter',
        default=False,
        description='Uses the visible perimeter to select the nearest real closed boundary loop; it does not remesh the model')

    def execute(self, context):
        props = context.scene.dsg_props
        model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(model):
            _dsg_report(self, {'ERROR'}, 'No aligned dental model was found', 'No se encontró un modelo dental alineado')
            return {'CANCELLED'}
        perimeter = None
        if self.use_drawn_perimeter:
            perimeter = _base_perimeter_curve()
            if perimeter is None or len(_base_perimeter_world_points(perimeter)) < BASE_PERIMETER_MIN_POINTS:
                _dsg_report(
                    self, {'ERROR'},
                    'No valid visible perimeter is available',
                    'No hay un perímetro visible válido')
                return {'CANCELLED'}
        try:
            closed, report = close_open_dental_model_base(
                context, model, perimeter_obj=perimeter)
        except Exception as exc:
            _dsg_report(
                self, {'ERROR'},
                f'Anatomy-safe base closure failed: {exc}',
                f'No se pudo cerrar la base sin modificar la anatomía: {exc}')
            return {'CANCELLED'}

        closed[CLOSED_MODEL_ACCEPTED_FLAG] = True
        closed[EXTERNAL_CLOSED_MODEL_FLAG] = False
        props.model_obj = closed
        _remove_retention_previews()
        _clear_retention_geometry_cache()
        _clear_model_topology_cache()
        context.scene[SUITE_STAGE_KEY] = 'DSG'
        if report.get('solid'):
            depth = float(closed.get('DSG_base_depth_mm', 0.0))
            confidence = float(closed.get('DSG_base_direction_confidence', 0.0))
            severity = {'WARNING'} if confidence < AUTO_BASE_LOW_CONFIDENCE else {'INFO'}
            _dsg_report(
                self, severity,
                f'Model base closed and manifold ({depth:.1f} mm; direction confidence {confidence:.0%})',
                f'Base cerrada y modelo manifold ({depth:.1f} mm; confianza de dirección {confidence:.0%})')
        else:
            _dsg_report(
                self, {'WARNING'},
                'The model was processed, but solidity could not be verified',
                'El modelo fue procesado, pero no se pudo verificar que sea sólido')
        return {'FINISHED'}


def run_3d_print_make_manifold(context, obj):
    """Intenta ejecutar el Make Manifold real de Blender/3D Print Toolbox."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False

    active_prev = context.view_layer.objects.active
    mode_prev = active_prev.mode if active_prev and hasattr(active_prev, 'mode') else 'OBJECT'
    selected_prev = {o.name for o in context.view_layer.objects if o.select_get()}

    try:
        # No se activa ningún add-on ni se modifican Preferencias desde una
        # operación clínica. Si 3D Print Toolbox ya está disponible se usa;
        # en caso contrario se continúa con el fallback BMesh interno.
        op = getattr(bpy.ops.mesh, 'print3d_clean_non_manifold', None)
        if op is None:
            return False

        ensure_object_mode(context)
        set_active(context, obj)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='SELECT')

        if hasattr(op, 'poll') and not op.poll():
            return False

        op()
        try:
            bpy.ops.mesh.normals_make_consistent(inside=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        obj.data.update()
        return True
    except Exception as e:
        print(f"[DSG] 3D Print Make Manifold skipped: {e}")
        return False
    finally:
        _restore_selection_after_mesh_tool(context, active_prev, selected_prev, mode_prev)


def make_mesh_manifold_bmesh(obj, merge_dist=0.001, fill_holes=True, max_vertices=450000):
    """Fallback interno: limpia la malla y rellena bordes abiertos pequeños/medios.

    No sustituye al Make Manifold de 3D Print cuando está disponible, pero mejora
    mucho los booleanos: elimina geometría suelta, vértices dobles, degenerados y
    recalcula normales.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False
    mesh = obj.data
    if mesh is None or len(mesh.vertices) == 0:
        return False
    if len(mesh.vertices) > int(max_vertices):
        print(f"[DSG] Fallback Make Manifold skipped: mesh too large ({len(mesh.vertices)} vertices)")
        return False

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        loose_edges = [e for e in bm.edges if not e.link_faces]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')

        loose_verts = [v for v in bm.verts if not v.link_edges]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')

        if bm.verts:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=max(0.0, float(merge_dist)))

        try:
            if bm.edges:
                bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-6)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        if fill_holes:
            boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
            if boundary_edges:
                try:
                    bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
                except Exception as e:
                    print(f"[DSG] holes_fill skipped: {e}")

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        return True
    except Exception as e:
        try:
            if bm:
                bm.free()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        print(f"[DSG] Fallback Make Manifold failed: {e}")
        return False


def verify_solid_and_make_manifold_before_drill(context, guide_obj):
    """Preflight del paso 9 antes de generar canales centrales.

    1) Verifica Solid/no-manifold.
    2) Si no es sólido, ejecuta Make Manifold.
    3) Re-verifica y devuelve si conviene seguir con boolean rápido o robusto.
    """
    if not _valid_obj(guide_obj) or guide_obj.type != 'MESH':
        return False, 'Invalid guide for solid verification'

    ensure_object_mode(context)
    before = get_mesh_solid_report(guide_obj)

    if before.get('checked') and before.get('solid'):
        try:
            guide_obj['DSG_solid_precheck_step10'] = 'solid_ok'
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, 'Solid OK'

    ran_print3d = run_3d_print_make_manifold(context, guide_obj)
    ran_bmesh = make_mesh_manifold_bmesh(guide_obj, merge_dist=0.001, fill_holes=True)

    after = get_mesh_solid_report(guide_obj)
    try:
        guide_obj['DSG_solid_precheck_step10'] = json.dumps({
            'before': before,
            'after': after,
            'ran_3d_print_make_manifold': bool(ran_print3d),
            'ran_bmesh_fallback': bool(ran_bmesh),
        })
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if after.get('checked') and after.get('solid'):
        return True, 'Make Manifold aplicado: Solid OK'

    if after.get('checked'):
        bad = after.get('bad_edges')
        deg = after.get('degenerate_faces')
        return False, f'Make Manifold applied, but non-manifold edges remain={bad}, degenerate faces={deg}; robust Boolean will be used'

    return False, 'Make Manifold applied, but Solid could not be verified because of mesh size; robust Boolean will be used'


def _mesh_preflight_fingerprint(obj):
    if not _valid_obj(obj) or obj.type != 'MESH' or obj.data is None:
        return None
    mesh = obj.data
    return {
        'mesh': mesh.name,
        'vertices': len(mesh.vertices),
        'edges': len(mesh.edges),
        'polygons': len(mesh.polygons),
    }


def _preflight_storage_key(key):
    safe = ''.join(ch if ch.isalnum() or ch == '_' else '_' for ch in str(key))
    return f'DSG_boolean_preflight_{safe}'


def store_boolean_preflight(obj, key, data):
    if not _valid_obj(obj):
        return data
    payload = dict(data or {})
    payload['fingerprint'] = _mesh_preflight_fingerprint(obj)
    try:
        obj[_preflight_storage_key(key)] = json.dumps(payload, ensure_ascii=False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        _PREFLIGHT_UI_CACHE[(obj.name, str(key), json.dumps(payload.get('fingerprint'), sort_keys=True))] = payload
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return payload


def load_boolean_preflight(obj, key):
    if not _valid_obj(obj):
        return None
    raw = obj.get(_preflight_storage_key(key))
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return None
    return data if data.get('fingerprint') == _mesh_preflight_fingerprint(obj) else None


def _preflight_from_report(report, repaired=False, repair_methods=None, message=''):
    repair_methods = list(repair_methods or [])
    checked = bool(report.get('checked'))
    solid = bool(report.get('solid')) if checked else False
    if not checked:
        # Una malla grande no verificada no equivale a una malla defectuosa.
        # Se permite continuar porque las operaciones críticas son transaccionales.
        status = 'orange'
    elif solid:
        status = 'orange' if repaired else 'green'
    else:
        status = 'red'
    if not message:
        if checked and solid and repaired:
            message = 'Automatic repair applied; mesh is solid'
        elif checked and solid:
            message = 'Mesh is closed and ready for EXACT Boolean'
        elif checked:
            message = (
                f"Non-manifold mesh: edges={report.get('bad_edges', '?')}, "
                f"degeneradas={report.get('degenerate_faces', '?')}"
            )
        else:
            message = 'Large mesh: lightweight verification skipped; continuing with EXACT Boolean and rollback'
    return {
        'status': status,
        'checked': checked,
        'solid': solid,
        'repaired': bool(repaired),
        'repair_methods': repair_methods,
        'bad_edges': report.get('bad_edges'),
        'degenerate_faces': report.get('degenerate_faces'),
        'polygons': report.get('polygons'),
        'solver': 'EXACT',
        'message': message,
    }


def evaluate_boolean_preflight(obj, key, max_polygons=800000):
    """Chequeo no destructivo cacheado en memoria para el semáforo del panel."""
    cached = load_boolean_preflight(obj, key)
    if cached is not None:
        return cached
    fingerprint = _mesh_preflight_fingerprint(obj)
    cache_key = (obj.name if obj else '', str(key), json.dumps(fingerprint, sort_keys=True))
    if cache_key in _PREFLIGHT_UI_CACHE:
        return _PREFLIGHT_UI_CACHE[cache_key]
    report = get_mesh_solid_report(obj, max_polygons=max_polygons)
    data = _preflight_from_report(report)
    _PREFLIGHT_UI_CACHE[cache_key] = data
    return data


def run_boolean_preflight(context, obj, key, try_repair=True, max_polygons=800000,
                          merge_dist=0.001, fill_holes=True):
    """Comprueba una malla y, si hace falta, intenta una reparación limitada.

    Verde: ya estaba solid. Naranja: se reparó automáticamente. Rojo: sigue
    abierta/no verificable y el Critical Boolean se cancela antes de tocar la guía.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return store_boolean_preflight(obj, key, {
            'status': 'red', 'checked': False, 'solid': False, 'repaired': False,
            'repair_methods': [], 'bad_edges': None, 'degenerate_faces': None,
            'polygons': 0, 'solver': 'EXACT', 'message': 'Invalid Mesh object',
        }) if obj else {
            'status': 'red', 'checked': False, 'solid': False, 'repaired': False,
            'repair_methods': [], 'bad_edges': None, 'degenerate_faces': None,
            'polygons': 0, 'solver': 'EXACT', 'message': 'Invalid Mesh object',
        }

    ensure_object_mode(context)
    before = get_mesh_solid_report(obj, max_polygons=max_polygons)
    if before.get('checked') and before.get('solid'):
        data = _preflight_from_report(before, repaired=False)
        data['before'] = before
        data['after'] = before
        return store_boolean_preflight(obj, key, data)

    repaired = False
    methods = []
    if try_repair and before.get('checked') and not before.get('solid'):
        if run_3d_print_make_manifold(context, obj):
            repaired = True
            methods.append('3D Print Make Manifold')
        if make_mesh_manifold_bmesh(obj, merge_dist=merge_dist, fill_holes=fill_holes):
            repaired = True
            methods.append('BMesh cleanup/fill')

    after = get_mesh_solid_report(obj, max_polygons=max_polygons)
    data = _preflight_from_report(after, repaired=repaired, repair_methods=methods)
    data['before'] = before
    data['after'] = after
    return store_boolean_preflight(obj, key, data)


def combine_boolean_preflights(obj, key, results, label='Critical Boolean'):
    results = [r for r in results if r]
    any_red = any(r.get('status') == 'red' for r in results)
    any_orange = any(r.get('status') == 'orange' for r in results)
    any_unchecked = any(not bool(r.get('checked')) for r in results)
    any_repaired = any(bool(r.get('repaired')) for r in results)
    status = 'red' if any_red else ('orange' if any_orange else 'green')
    bad_edges = sum(int(r.get('bad_edges') or 0) for r in results)
    degenerate = sum(int(r.get('degenerate_faces') or 0) for r in results)

    if status == 'green':
        message = f'{label}: all meshes are verified and ready'
    elif status == 'orange':
        details = []
        if any_repaired:
            details.append('automatic repair applied')
        if any_unchecked:
            details.append('large mesh not verified by the lightweight check')
        suffix = '; '.join(details) or 'non-blocking warning'
        message = f'{label}: {suffix}; continuing transactionally'
    else:
        failed = [r.get('message', 'invalid mesh') for r in results if r.get('status') == 'red']
        message = f"{label}: " + '; '.join(failed[:3])

    all_checked = bool(results) and all(bool(r.get('checked')) for r in results)
    all_solid = all_checked and all(bool(r.get('solid')) for r in results)
    return store_boolean_preflight(obj, key, {
        'status': status,
        'checked': all_checked,
        'solid': all_solid,
        'repaired': any_repaired,
        'unverified_large_mesh': any_unchecked,
        'repair_methods': [m for r in results for m in r.get('repair_methods', [])],
        'bad_edges': bad_edges,
        'degenerate_faces': degenerate,
        'polygons': sum(int(r.get('polygons') or 0) for r in results),
        'solver': 'EXACT',
        'message': message,
        'components': results,
    })


def clean_boolean_cutter_mesh(obj, merge_dist=0.0005, max_vertices=160000):
    """Limpieza ligera para cutters generados por el addon.

    No intenta convertir una malla mala en perfecta, pero sí elimina vértices
    sueltos, dobles microscópicos y recalcula normales. Esto ayuda mucho con
    cutters de tubos orgánicos o de radio variable antes del boolean.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False
    mesh = obj.data
    bm = None
    try:
        if len(mesh.vertices) == 0 or len(mesh.vertices) > int(max_vertices):
            return False
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        loose = [v for v in bm.verts if not v.link_edges]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')

        if bm.verts:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=max(0.0, float(merge_dist)))
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        return True
    except Exception as e:
        try:
            bm.free()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        print(f"[DSG] Limpieza cutter boolean omitida: {e}")
        return False


def set_boolean_exact_options(mod, robust=False):
    """Activa opciones de tolerancia si existen en el build de Blender."""
    for attr, value in (
        ('use_self', bool(robust)),
        ('use_hole_tolerant', bool(robust)),
    ):
        if hasattr(mod, attr):
            try:
                setattr(mod, attr, value)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def apply_boolean_modifier_smart(context, obj_cut, mod, obj_cutter=None,
                                 prefer_fast=True, force_robust=False,
                                 cleanup_cutter=True):
    """Aplica una booleana EXACT una sola vez.

    Se conserva el nombre para no romper llamadas existentes. La seguridad se
    basa en limpieza del cutter, copia/rollback en el nivel transaccional y
    validación manifold, no en probar varios solvers.
    """
    if not obj_cut or not mod:
        return False, None
    if obj_cutter is None:
        obj_cutter = getattr(mod, 'object', None)
    if cleanup_cutter and obj_cutter and obj_cutter.type == 'MESH':
        clean_boolean_cutter_mesh(obj_cutter)
    try:
        mod.solver = 'EXACT'
        set_boolean_exact_options(mod, robust=bool(force_robust))
    except Exception as exc:
        print(f"[DSG] No se pudo configurar EXACT: {exc}")
        return False, None
    ok = apply_modifier_direct(context, obj_cut, mod.name)
    if not ok:
        print(f"[DSG] EXACT Boolean failed: {mod.name}")
    return ok, 'EXACT'


def apply_boolean_difference_fast(context, obj_cut, obj_cutter, mod_name, prefer_fast=True, force_robust=False):
    """Alias histórico: actualmente siempre aplica DIFFERENCE con EXACT."""
    if not obj_cut or not obj_cutter:
        return False, None
    mod = obj_cut.modifiers.new(mod_name, 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = obj_cutter
    return apply_boolean_modifier_smart(
        context, obj_cut, mod, obj_cutter=obj_cutter,
        prefer_fast=False, force_robust=True, cleanup_cutter=True,
    )


def apply_boolean_union_exact(context, obj_base, obj_add, mod_name='DSG_UnionExact',
                              robust=True, cleanup_cutter=True):
    """Fusiona dos sólidos con un único Boolean UNION robusto.

    A diferencia de object.join(), elimina las superficies internas y produce una
    sola envolvente. Se fuerza EXACT porque estas uniones son pequeñas y críticas:
    sleeve-frame y tubo-guía.
    """
    if not obj_base or not obj_add:
        return False, None
    if not _valid_obj(obj_base) or not _valid_obj(obj_add):
        return False, None
    mod = obj_base.modifiers.new(mod_name, 'BOOLEAN')
    mod.operation = 'UNION'
    mod.object = obj_add
    return apply_boolean_modifier_smart(
        context,
        obj_base,
        mod,
        obj_cutter=obj_add,
        prefer_fast=False,
        force_robust=bool(robust),
        cleanup_cutter=bool(cleanup_cutter),
    )


def _restore_object_mesh_copy(obj, mesh_copy):
    """Restaura una copia de malla y elimina la malla descartada si queda huérfana."""
    if not obj or not mesh_copy:
        return False
    old = obj.data
    obj.data = mesh_copy
    try:
        obj.data.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if old and old != mesh_copy and old.users == 0:
            bpy.data.meshes.remove(old)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def fuse_additions_into_base_exact(context, base_obj, additions, out_name,
                                   mod_name='DSG_UnionExact', require_solid=True,
                                   robust=True, cleanup_cutter=True, prevalidated=False):
    """Fusiona adiciones con UNION EXACT y valida el resultado BRUTO.

    Regla crítica v6.1.3:
    - Después del UNION no se ejecuta Merge by Distance, dissolve ni limpieza
      genérica. Esas operaciones podían convertir una unión válida de Blender
      en cientos de edges no-manifold.
    - Se comprueba directamente la malla producida por EXACT.
    - Si el resultado no es sólido, se restaura el backup sin modificarlo.

    Los cutters temporales se identifican por nombre para no dereferenciar un
    StructRNA que Blender haya invalidado durante el join o el modifier_apply.
    """
    valid = [o for o in additions if _valid_obj(o) and o.type == 'MESH']
    if not _valid_obj(base_obj) or not valid:
        return None, False, 'invalid objects'

    before = ({'checked': True, 'solid': True, 'bad_edges': 0, 'degenerate_faces': 0}
              if prevalidated else get_mesh_solid_report(base_obj))
    if require_solid and before.get('checked') and not before.get('solid'):
        return None, False, (
            f'el sólido base ya era no manifold: '
            f'aristas={before.get("bad_edges")}, '
            f'caras degeneradas={before.get("degenerate_faces")}'
        )

    backup = base_obj.data.copy()
    cutter = valid[0]
    if len(valid) > 1:
        cutter = join_objects(context, valid, mod_name + '_Additions')
    if not _valid_obj(cutter):
        try:
            bpy.data.meshes.remove(backup)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return None, False, 'could not build the union cutter'

    cutter_name = _safe_object_name(cutter)
    cutter_report = ({'checked': True, 'solid': True, 'bad_edges': 0, 'degenerate_faces': 0}
                     if prevalidated else get_mesh_solid_report(cutter))
    if require_solid and cutter_report.get('checked') and not cutter_report.get('solid'):
        _restore_object_mesh_copy(base_obj, backup)
        if cutter_name:
            safe_remove_by_name(cutter_name)
        return None, False, (
            f'cutter no sólido antes del UNION: '
            f'aristas={cutter_report.get("bad_edges")}, '
            f'caras degeneradas={cutter_report.get("degenerate_faces")}'
        )

    ok, solver = apply_boolean_union_exact(
        context, base_obj, cutter, mod_name=mod_name,
        robust=robust, cleanup_cutter=cleanup_cutter)
    if not ok:
        _restore_object_mesh_copy(base_obj, backup)
        if cutter_name:
            safe_remove_by_name(cutter_name)
        return None, False, f'Boolean UNION EXACT no pudo aplicarse'

    # IMPORTANTE: validar exactamente la salida de Blender, sin remove_doubles.
    try:
        base_obj.data.update()
        context.view_layer.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    raw_after = get_mesh_solid_report(base_obj)
    if require_solid and raw_after.get('checked') and not raw_after.get('solid'):
        bad_edges = raw_after.get('bad_edges')
        degenerate = raw_after.get('degenerate_faces')
        _restore_object_mesh_copy(base_obj, backup)
        if cutter_name:
            safe_remove_by_name(cutter_name)
        return None, False, (
            f'raw EXACT union is non-solid: edges={bad_edges}, '
            f'caras degeneradas={degenerate}'
        )

    base_obj.name = out_name
    try:
        base_obj.data.name = out_name + '_Mesh'
        for poly in base_obj.data.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if cutter_name:
        safe_remove_by_name(cutter_name)
    try:
        if backup.users == 0:
            bpy.data.meshes.remove(backup)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if raw_after.get('checked'):
        return base_obj, True, (
            f'UNION {solver or "EXACT"}; SOLID bruto OK; '
            f'polígonos={raw_after.get("polygons", 0)}'
        )
    return base_obj, True, f'UNION {solver or "EXACT"}; large result not verified'


def sleeve_sidewall_guard_enabled(props):
    """Compatibilidad de nombre: activa la validación analítica de caras planas."""
    try:
        return bool(getattr(props, 'sleeve_sidewall_invulnerable', True))
    except Exception:
        return True



def _sleeve_inner_radius_from_props(props):
    """Single source of truth for the sleeve lumen, independent of implant size."""
    return max(0.05, float(getattr(props, 'sleeve_inner_diameter', 4.7)) * 0.5)


def _sleeve_radii_from_props(props):
    inner_r = _sleeve_inner_radius_from_props(props)
    wall = max(0.05, float(getattr(props, 'sleeve_wall', 1.5)))
    return inner_r, inner_r + wall, wall



def _sleeve_flat_face_guard_values(props):
    """Márgenes de validación analítica; ya no generan cutters anulares."""
    radial_margin = max(0.01, float(getattr(props, 'sleeve_sidewall_clearance', 0.12)))
    axial_tolerance = max(0.01, float(getattr(props, 'sleeve_sidewall_guard_depth', 0.20)) * 0.5)
    axial_margin = max(0.0, float(getattr(props, 'sleeve_sidewall_axial_margin', 0.08)))
    half_guard = axial_tolerance + axial_margin
    return radial_margin, axial_tolerance * 2.0, axial_margin, half_guard



def get_sleeve_sidewall_zone(point, props, padding=0.0, implant_obj=None):
    """Devuelve la cara plana anular del sleeve más cercana a ``point``.

    Aunque conserva el nombre histórico ``sidewall`` por compatibilidad, esta
    función ya no protege la pared curva. La zona protegida es una lámina anular
    alrededor de z=+altura/2 y z=-altura/2 en coordenadas locales del sleeve.
    """
    p = Vector(point)
    inner_r, outer_r, wall = _sleeve_radii_from_props(props)
    radial_margin, slab_depth, axial_margin, half_guard = _sleeve_flat_face_guard_values(props)
    half_h = max(0.1, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    pad = max(0.0, float(padding))

    implants = [implant_obj] if is_valid_implant_obj(implant_obj) else get_all_implant_objects(props)
    best = None
    best_error = float('inf')
    for implant in implants:
        if not is_valid_implant_obj(implant):
            continue
        try:
            mx = get_sleeve_matrix_world(props, implant)
            local = mx.inverted() @ p
        except Exception:
            continue

        radial = math.hypot(local.x, local.y)
        inner_guard_r = max(0.01, inner_r - radial_margin)
        outer_guard_r = outer_r + radial_margin
        face_sign = 1.0 if local.z >= 0.0 else -1.0
        nearest_face_z = face_sign * half_h
        face_distance = abs(local.z - nearest_face_z)

        if radial < inner_guard_r:
            radial_error = inner_guard_r - radial
        elif radial > outer_guard_r:
            radial_error = radial - outer_guard_r
        else:
            radial_error = 0.0
        axial_error = max(0.0, face_distance - half_guard)
        error = radial_error + axial_error

        in_zone = (
            radial >= inner_guard_r - pad
            and radial <= outer_guard_r + pad
            and face_distance <= half_guard + pad
        )
        if error < best_error:
            best_error = error
            best = {
                'implant': implant,
                'matrix': mx,
                'local': local,
                'radial': radial,
                'inner_r': inner_r,
                'outer_r': outer_r,
                'wall': wall,
                'inner_guard_r': inner_guard_r,
                'outer_guard_r': outer_guard_r,
                'half_h': half_h,
                'face_sign': face_sign,
                'face_z': nearest_face_z,
                'face_distance': face_distance,
                'half_guard': half_guard,
                'in_zone': bool(in_zone),
                'error': error,
            }
    return best


def is_point_near_protected_sleeve_sidewall(point, props, padding=0.0):
    """Compatibilidad: True si el punto está cerca de una cara plana protegida."""
    if not sleeve_sidewall_guard_enabled(props):
        return False
    info = get_sleeve_sidewall_zone(point, props, padding=padding)
    return bool(info and info.get('in_zone'))


def get_irrigation_base_outer_radius_at_sleeve(props):
    """Radio exterior normal del conducto en la salida estrecha del sleeve."""
    inner_channel_r = max(
        0.05,
        float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5,
    )
    outlet_d = max(
        0.05,
        float(getattr(props, 'irr_funnel_outer_diameter', 1.0)),
    )
    outlet_inner_r = min(max(0.025, outlet_d * 0.5), inner_channel_r)
    wall_t = max(0.0, float(getattr(props, 'irr_wall_thickness', 1.5)))
    local_blend = max(0.0, float(getattr(props, 'irr_junction_blend', 0.0)))
    return max(0.05, outlet_inner_r + wall_t + local_blend)


def get_irrigation_outer_radius_at_sleeve(props):
    """Radio real de la base volcánica donde el tubo se funde con el sleeve.

    La base es mayor que el conducto, pero queda limitada por la altura del
    sleeve para no invadir sus caras planas. Esta medida también se utiliza para
    recalcular automáticamente la cota coronal del puerto.
    """
    base_radius = get_irrigation_base_outer_radius_at_sleeve(props)
    target = max(
        base_radius + float(IRRIGATION_SLEEVE_VOLCANO_MIN_EXTRA_MM_FIXED),
        base_radius * float(IRRIGATION_SLEEVE_VOLCANO_RADIUS_RATIO_FIXED),
    )
    half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    maximum_by_height = max(
        base_radius,
        half_h - float(IRRIGATION_SLEEVE_CORONAL_FACE_CLEARANCE_MM_FIXED),
    )
    return max(base_radius, min(target, maximum_by_height))



def get_irrigation_coronal_port_offset_mm(props, half_h=None):
    """Exact centre offset needed to leave the outer wall flush to the face."""
    if half_h is None:
        half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    half_h = max(0.10, float(half_h))
    sleeve_height = half_h * 2.0
    desired_offset = (
        get_irrigation_outer_radius_at_sleeve(props)
        + float(IRRIGATION_SLEEVE_CORONAL_FACE_CLEARANCE_MM_FIXED)
    )
    max_offset = max(
        0.05,
        sleeve_height
        - IRRIGATION_SLEEVE_OPPOSITE_FACE_MIN_CLEARANCE_MM_FIXED,
    )
    return min(desired_offset, max_offset)



def get_irrigation_coronal_sleeve_z_local(props, implant_obj=None, half_h=None):
    """Places the port so its external wall is tangent to the coronal face.

    The user's click chooses only the circumferential direction. The vertical
    centre is derived from the real local outer radius instead of a guessed
    fixed distance, so diameter and wall-thickness changes remain flush.
    """
    if half_h is None:
        half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    half_h = max(0.10, float(half_h))
    offset_from_coronal = get_irrigation_coronal_port_offset_mm(
        props, half_h=half_h)
    sign = 1.0 if float(get_sleeve_occlusal_sign(props, implant_obj)) >= 0.0 else -1.0
    return sign * (half_h - offset_from_coronal)




def _irrigation_direct_sleeve_overlap_mm(props, inner_r=None):
    """Depth of a DIRECT irrigation port inside the axial sleeve lumen.

    DIRECT mode must create only a short hydraulic communication into the sleeve
    lumen.  It must not drive the channel centreline to the implant/drill axis,
    because that makes the diagnostic/cutter look as if the irrigation path ends
    in the implant centre instead of just opening into the sleeve lumen.
    """
    try:
        requested = float(getattr(props, 'irr_direct_sleeve_lumen_overlap', 1.0))
    except Exception:
        requested = 1.0
    requested = max(0.05, requested)
    if inner_r is not None:
        try:
            inner_r = max(0.05, float(inner_r))
            requested = min(requested, max(0.05, inner_r - 0.05))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return requested


def get_direct_irrigation_lumen_tip(anchor_point, props, implant_obj=None):
    """Return the clinical DIRECT-mode inner end point.

    The point is measured radially from the inner sleeve wall and stops 1 mm
    inside the sleeve lumen by default.  It is intentionally not the sleeve axis.
    """
    geo = get_sleeve_wall_geometry(anchor_point, props, implant_obj)
    if not geo:
        return None
    radial = Vector(geo.get('radial', (1.0, 0.0, 0.0)))
    if radial.length < 1.0e-8:
        return None
    radial.normalize()
    axis_entry = Vector(geo['axis_entry'])
    inner_r = max(0.05, float(geo['inner_r']))
    overlap = _irrigation_direct_sleeve_overlap_mm(props, inner_r=inner_r)
    return axis_entry + radial * max(0.0, inner_r - overlap)


def _irrigation_is_direct_channel_mode(props):
    try:
        return str(getattr(props, 'irr_sleeve_channel_mode', 'C') or 'C').upper() == 'DIRECT'
    except Exception:
        return False


def _normalize_direct_irrigation_controls(control_points, props, implant_obj=None):
    """Fix legacy DIRECT paths whose first point was saved at the sleeve axis.

    v7.0.28 could store the first control in DIRECT mode at the centre of the
    sleeve lumen.  This normalizer rebuilds only that first point from the real
    sleeve wall and leaves all user/external points untouched.
    """
    pts = [Vector(point) for point in list(control_points or [])]
    if len(pts) < 2 or not _irrigation_is_direct_channel_mode(props):
        return pts
    if not is_valid_implant_obj(implant_obj):
        # Callers (e.g. smooth_irrigation_centerline_controls) do not pass the
        # implant. Falling back to props.implant_obj moved the first point of
        # every *other* sleeve's channel (all Link branches) into the ACTIVE
        # sleeve, so linked DIRECT sleeves were never opened. The saved first
        # point lies inside its own sleeve: resolve the owner from it.
        implant_obj = get_nearest_implant_to_point(props, pts[0])
    anchor_for_wall = pts[1]
    tip = get_direct_irrigation_lumen_tip(anchor_for_wall, props, implant_obj=implant_obj)
    if tip is not None:
        pts[0] = Vector(tip)
    return pts

def get_sleeve_lateral_port_geometry(anchor_point, props, implant_obj=None, outer_tube_radius=None):
    """Puerto seguro sobre la superficie cilíndrica lateral del sleeve.

    Las caras superior e inferior permanecen intocables. El contacto se coloca
    sobre la pared curva, suficientemente alejado de ambos bordes planos para que
    el radio completo del tubo no alcance las caras anulares.
    """
    p = Vector(anchor_point)
    if not is_valid_implant_obj(implant_obj):
        implant_obj = get_nearest_implant_to_point(props, p)
    if not is_valid_implant_obj(implant_obj):
        return None

    mx = get_sleeve_matrix_world(props, implant_obj)
    inv = mx.inverted()
    local = inv @ p
    center = mx.to_translation()
    axis = (mx.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()

    radial_local = Vector((local.x, local.y, 0.0))
    if radial_local.length < 1e-7:
        radial_local = Vector((1.0, 0.0, 0.0))
    radial_local.normalize()
    radial = (mx.to_3x3() @ radial_local).normalized()

    inner_r, outer_r, wall = _sleeve_radii_from_props(props)
    half_h = max(0.1, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    radial_margin, slab_depth, axial_margin, half_guard = _sleeve_flat_face_guard_values(props)

    if outer_tube_radius is None:
        outer_tube_radius = (
            max(0.05, float(getattr(props, 'irr_inner_diameter', 4.0)) * 0.5) +
            max(0.05, float(getattr(props, 'irr_wall_thickness', 1.5)))
        )
    tube_r = max(0.05, float(outer_tube_radius))

    # The radial click chooses the circumferential direction only.  The channel
    # level is fixed in the coronal/superior sleeve zone.  Basing this on the
    # narrow outlet diameter avoids forcing the port back to the sleeve centre
    # merely because the external supply tube is wide.
    safe_z = get_irrigation_coronal_sleeve_z_local(
        props, implant_obj=implant_obj, half_h=half_h)

    exit_overshoot = max(0.04, min(
        float(getattr(props, 'irr_wall_exit_overshoot', 0.18)),
        0.60,
        inner_r * 0.45,
    ))
    inner_target_r = max(0.02, inner_r - exit_overshoot)
    outside_offset = max(0.18, min(tube_r * 0.42 + radial_margin, 1.60))
    launch_len = max(0.30, float(getattr(props, 'irr_entry_length', 1.2)))

    def world_at(radius, z_value=safe_z):
        return mx @ Vector((radial_local.x * radius, radial_local.y * radius, z_value))

    face_point = world_at(outer_r)
    internal_overlap_point = world_at(inner_target_r)
    external_anchor = world_at(outer_r + outside_offset)
    launch_point = world_at(outer_r + outside_offset + launch_len)
    lumen_tip = internal_overlap_point.copy()

    return {
        'implant': implant_obj,
        'center': center,
        'axis': axis,
        'occlusal': axis.copy(),
        # Clave heredada: ahora representa la dirección radial exterior.
        'apical': radial.copy(),
        'radial': radial,
        'inner_r': inner_r,
        'outer_r': outer_r,
        'wall': wall,
        'half_h': half_h,
        'safe_z': safe_z,
        'port_vertical_zone': 'CORONAL_SUPERIOR',
        'coronal_face_offset_mm': float(get_irrigation_coronal_port_offset_mm(props, half_h=half_h)),
        'coronal_face_clearance_mm': float(IRRIGATION_SLEEVE_CORONAL_FACE_CLEARANCE_MM_FIXED),
        'local_outer_radius_at_sleeve_mm': float(get_irrigation_outer_radius_at_sleeve(props)),
        'face_point': face_point,
        'external_anchor': external_anchor,
        'internal_overlap_point': internal_overlap_point,
        'lumen_tip': lumen_tip,
        'launch_point': launch_point,
    }


def get_sleeve_apical_port_geometry(anchor_point, props, implant_obj=None, outer_tube_radius=None):
    """Alias heredado de v24: ahora devuelve un puerto lateral seguro."""
    return get_sleeve_lateral_port_geometry(
        anchor_point, props, implant_obj=implant_obj, outer_tube_radius=outer_tube_radius
    )



def append_cylinder_to_bmesh(bm_dst, radius, depth, matrix_world, verts=12):
    """Añade un cilindro cutter directamente en coordenadas mundo."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=max(8, int(verts)),
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    bm.transform(matrix_world)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    _transfer_bm(bm, bm_dst)
    bm.free()


def build_multi_cylinder_cutter(context, name, transforms, radius, depth, verts=12):
    """Crea un único objeto cutter con todos los canales de implante.

    Antes se hacía un boolean por implante. Eso recalculaba toda la férula varias
    veces y podía congelar Blender. Con este cutter combinado se aplica un solo
    boolean para todos los implantes.
    """
    safe_remove_by_name(name)
    bm_total = bmesh.new()
    count = 0
    for mx in transforms:
        try:
            append_cylinder_to_bmesh(bm_total, radius, depth, mx, verts=verts)
            count += 1
        except Exception as e:
            print(f"[DSG] Could not add cutter cylinder: {e}")

    if count == 0 or len(bm_total.verts) == 0:
        bm_total.free()
        return None

    bmesh.ops.remove_doubles(bm_total, verts=bm_total.verts[:], dist=0.001)
    bmesh.ops.recalc_face_normals(bm_total, faces=bm_total.faces[:])
    mesh = bpy.data.meshes.new(name + '_Mesh')
    bm_total.to_mesh(mesh)
    bm_total.free()

    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.display_type = 'WIRE'
    return obj



def append_profiled_drill_cutter_to_bmesh(bm_dst, matrix_world, profile, verts=24):
    """Añade un cutter axial cerrado con radios variables.

    El perfil permite atravesar el lumen del sleeve con un radio unas centésimas
    menor y ensancharse solo al salir por su pared lateral. De este modo no hay una
    pared cilíndrica exactamente coplanar con el interior del sleeve, que era la
    principal causa de caras abiertas y resultados no manifold en el paso 9.
    """
    segments = max(8, int(verts))
    ordered = sorted([(float(z), max(0.001, float(r))) for z, r in profile], key=lambda item: item[0])
    if len(ordered) < 2:
        return False

    bm = bmesh.new()
    rings = []
    try:
        for z, radius in ordered:
            ring = []
            for i in range(segments):
                angle = (2.0 * math.pi * i) / segments
                ring.append(bm.verts.new((radius * math.cos(angle), radius * math.sin(angle), z)))
            rings.append(ring)

        bm.verts.ensure_lookup_table()
        # Tapas: la inferior se invierte para que la normal apunte hacia -Z.
        try:
            bm.faces.new(list(reversed(rings[0])))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            bm.faces.new(rings[-1])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        for ring_a, ring_b in zip(rings[:-1], rings[1:]):
            for i in range(segments):
                j = (i + 1) % segments
                try:
                    bm.faces.new((ring_a[i], ring_a[j], ring_b[j], ring_b[i]))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)

        bm.transform(matrix_world)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        _transfer_bm(bm, bm_dst)
        return True
    finally:
        bm.free()


def build_safe_drill_cutter(context, props, implants, guide_obj, name=DRILL_BATCH_CUTTER_NAME):
    """Crea el cutter seguro del paso 9 sin superficies coplanares con el sleeve.

    La parte que atraviesa el sleeve es ligeramente menor que su lumen. Al salir
    por la pared lateral, el cutter se abre de forma corta y controlada para limpiar
    por completo el frame situado debajo del sleeve.
    """
    safe_remove_by_name(name)
    if not implants or guide_obj is None:
        return None

    inner_r = _sleeve_inner_radius_from_props(props)
    # El cutter debe INTERSECTAR ligeramente la pared interna del sleeve. Si es
    # menor que el lumen, no corta el sleeve y puede terminar exactamente en la
    # unión sleeve/frame, creando una arista en T. Un sobrecorte de centésimas
    # evita superficies coincidentes sin alterar clínicamente el diámetro.
    clearance = max(0.005, min(float(getattr(props, 'drill_sleeve_clearance', 0.02)), inner_r * 0.10))
    sleeve_radius = inner_r + clearance
    lower_radius = sleeve_radius + max(0.02, clearance * 1.50)
    sleeve_h = max(0.1, float(props.sleeve_height))
    top_extension = 1.5
    transition_half = 0.15
    # La transición nunca debe cruzar la pared lateral del sleeve. Se coloca por
    # completo dentro del frame, separada de esa cara para evitar una unión en T.
    transition_offset = max(0.45, transition_half + 0.20)

    guide_diag = max(1.0, object_bbox_diagonal(guide_obj))
    depth = max(
        sleeve_h + float(props.implant_length) + float(props.drill_extra_depth) + top_extension,
        guide_diag * 1.05,
    )

    bm_total = bmesh.new()
    count = 0
    try:
        for implant in implants:
            axis = get_sleeve_axis_world(props, implant)
            sign = get_sleeve_occlusal_sign(props, implant)
            occlusal = (axis * sign).normalized()
            sleeve_center = get_sleeve_center_world(props, implant)

            # El extremo superior queda fuera del sleeve y el cutter avanza en
            # dirección apical. Así limpia todo el lumen sin acabar dentro de la guía.
            top_world = sleeve_center + occlusal * (sleeve_h * 0.5 + top_extension)
            center_world = top_world - occlusal * (depth * 0.5)
            rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(occlusal)
            mx = Matrix.LocRotScale(center_world, rotation, Vector((1.0, 1.0, 1.0)))

            z_top = depth * 0.5
            z_bottom = -depth * 0.5
            # Cara apical del sleeve medida en coordenadas locales del cutter.
            z_apical = z_top - (top_extension + sleeve_h)
            transition_center = z_apical - transition_offset
            profile = [
                (z_bottom, lower_radius),
                (transition_center - transition_half, lower_radius),
                (transition_center + transition_half, sleeve_radius),
                (z_top, sleeve_radius),
            ]
            if append_profiled_drill_cutter_to_bmesh(
                bm_total, mx, profile, verts=max(8, int(props.drill_cutter_segments))
            ):
                count += 1

        if count == 0 or len(bm_total.verts) == 0:
            return None

        bmesh.ops.remove_doubles(bm_total, verts=bm_total.verts[:], dist=0.0001)
        if bm_total.faces:
            bmesh.ops.recalc_face_normals(bm_total, faces=bm_total.faces[:])
        mesh = bpy.data.meshes.new(name + '_Mesh')
        bm_total.to_mesh(mesh)
    finally:
        bm_total.free()

    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj)
    obj.display_type = 'WIRE'
    obj.show_in_front = True
    return obj



def get_drill_protection_radii(props):
    """Devuelve radio clínico, radio booleano y sobrecorte anti-coplanar.

    El radio clínico sigue leyendo dinámicamente la holgura principal de la
    fresa. El cutter booleano añade solo unas centésimas para atravesar de forma
    inequívoca la pared interior del sleeve y evitar superficies coincidentes.
    """
    implant_diameter = max(0.10, float(getattr(props, 'implant_diameter', 4.0)))
    fresa_clearance = max(0.0, float(getattr(props, 'fresa_offset', 0.10)))
    clinical_radius = max(0.05, implant_diameter * 0.5 + fresa_clearance)

    configured_overcut = max(
        0.0, float(getattr(props, 'drill_sleeve_clearance',
                           DRILL_PROTECTION_ANTICOPLANAR_MM_FIXED)))
    protection_extra = max(
        0.0, float(getattr(props, 'drill_protection_clearance', 0.0)))
    anti_coplanar = max(
        DRILL_PROTECTION_ANTICOPLANAR_MM_FIXED,
        configured_overcut,
    )
    boolean_radius = clinical_radius + anti_coplanar + protection_extra
    return clinical_radius, boolean_radius, anti_coplanar, protection_extra


def build_drill_insertion_protection_cutters(context, props, implants, reference_obj=None):
    """Crea cilindros coaxiales para limpiar físicamente el eje de fresado.

    El radio clínico sigue siendo:

        radio clínico = diámetro_implante / 2 + holgura_fresa

    El cutter booleano añade un sobrecorte radial mínimo anti-coplanar. Esto
    impide que sus caras coincidan exactamente con el lumen del sleeve, que era
    la causa del resultado no sólido con muchas edges abiertas. La holgura
    principal continúa actualizándose automáticamente desde fresa_offset.
    """
    safe_remove_by_prefix(DRILL_PROTECTION_PREFIX)
    valid_implants = [implant for implant in implants if is_valid_implant_obj(implant)]
    if not valid_implants:
        return []

    implant_diameter = max(0.10, float(getattr(props, 'implant_diameter', 4.0)))
    fresa_clearance = max(0.0, float(getattr(props, 'fresa_offset', 0.10)))
    clinical_radius, radius, anti_coplanar, protection_extra = (
        get_drill_protection_radii(props))

    sleeve_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)))
    implant_len = max(1.0, float(getattr(props, 'implant_length', 10.0)))
    extra_depth = max(5.0, float(getattr(props, 'drill_extra_depth', 5.0)))
    reference_diag = object_bbox_diagonal(reference_obj) if _valid_obj(reference_obj) else 0.0

    # Simétrico respecto al centro del sleeve. Se sobredimensiona para garantizar
    # que el cilindro atraviese cualquier geometría visible en ambos sentidos.
    depth = max(
        (sleeve_h + implant_len + extra_depth) * 2.0,
        reference_diag * 2.25,
        40.0,
    )
    segments = max(16, min(64, int(getattr(props, 'drill_protection_segments', 32))))

    cutters = []
    for index, implant in enumerate(valid_implants):
        try:
            axis = get_sleeve_axis_world(props, implant)
            sign = get_sleeve_occlusal_sign(props, implant)
            occlusal = (axis * sign).normalized()
            sleeve_center = get_sleeve_center_world(props, implant)
            rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(occlusal)

            name = f'{DRILL_PROTECTION_PREFIX}{index + 1:02d}'
            mesh = make_cylinder_mesh(name + '_Mesh', radius, depth, verts=segments)
            cutter = bpy.data.objects.new(name, mesh)
            cutter.matrix_world = Matrix.LocRotScale(
                sleeve_center, rotation, Vector((1.0, 1.0, 1.0)))
            link_object(context, cutter)
            cutter.display_type = 'WIRE'
            cutter.show_in_front = True
            register_dsg_object(cutter, ROLE_DRILL_CUTTER, name, {
                'DSG_cut_type': 'drill_insertion_protection',
                'DSG_implant_diameter': implant_diameter,
                'DSG_fresa_clearance_radial': fresa_clearance,
                'DSG_protection_clinical_diameter': clinical_radius * 2.0,
                'DSG_protection_anticoplanar_radial': anti_coplanar,
                'DSG_protection_extra_radial': protection_extra,
                'DSG_protection_diameter': radius * 2.0,
                'DSG_protection_depth': depth,
            })
            cutters.append(cutter)
        except Exception as exc:
            print(f'[DSG] Could not create axial protection {index + 1}: {exc}')

    return cutters



def build_sleeve_face_clearance_cutters(context, props, implants):
    """Create annular cutters only over each sleeve's flat occlusal face.

    The cutter follows the true annular support surface between the sleeve's
    inner and outer radii.  It extends coronally and only 0.08 mm below the
    theoretical support plane.  There is no lateral clearance halo.  A 0.02 mm
    overlap at both radial borders is used solely to make Boolean EXACT robust.

    The original sleeve shell is detected separately and excluded from the
    Boolean, so its flat support face remains geometrically unchanged.
    """
    safe_remove_by_prefix(SLEEVE_FACE_CUTTER_PREFIX)
    valid_implants = [implant for implant in implants if is_valid_implant_obj(implant)]
    if not valid_implants:
        return []

    inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    eps = max(0.005, float(SLEEVE_FACE_NUMERIC_EPS_MM_FIXED))
    cutter_inner_r = max(0.01, inner_r - eps)
    cutter_outer_r = max(cutter_inner_r + 0.02, outer_r + eps)
    above = max(0.10, float(SLEEVE_FACE_CLEARANCE_ABOVE_MM_FIXED))
    below = max(0.01, float(SLEEVE_FACE_CLEARANCE_BELOW_MM_FIXED))
    depth = above + below
    sleeve_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)))
    segments = max(24, int(SLEEVE_FACE_CLEARANCE_SEGMENTS_FIXED))

    cutters = []
    for index, implant in enumerate(valid_implants):
        try:
            axis = get_sleeve_axis_world(props, implant)
            sign = get_sleeve_occlusal_sign(props, implant)
            occlusal = (axis * sign).normalized()
            sleeve_center = get_sleeve_center_world(props, implant)
            face_center = sleeve_center + occlusal * (sleeve_h * 0.5)
            cutter_center = face_center + occlusal * ((above - below) * 0.5)
            rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(occlusal)

            name = f'{SLEEVE_FACE_CUTTER_PREFIX}{index + 1:02d}'
            mesh = make_annular_cylinder_mesh(
                name + '_Mesh',
                cutter_inner_r,
                cutter_outer_r,
                depth,
                segments=segments,
            )
            cutter = bpy.data.objects.new(name, mesh)
            cutter.matrix_world = Matrix.LocRotScale(
                cutter_center, rotation, Vector((1.0, 1.0, 1.0)))
            link_object(context, cutter)
            cutter.display_type = 'WIRE'
            cutter.show_in_front = True
            register_dsg_object(cutter, ROLE_DRILL_CUTTER, name, {
                'DSG_cut_type': 'sleeve_flat_face_only_clearance',
                'DSG_implant_name': _safe_object_name(implant) or '',
                'DSG_sleeve_face_inner_radius': float(cutter_inner_r),
                'DSG_sleeve_face_outer_radius': float(cutter_outer_r),
                'DSG_sleeve_face_numeric_epsilon': float(eps),
                'DSG_sleeve_face_clearance_above': float(above),
                'DSG_sleeve_face_clearance_below': float(below),
                'DSG_sleeve_face_preserved': True,
                'DSG_no_lateral_clearance_halo': True,
            })
            cutters.append(cutter)
        except Exception as exc:
            print(f'[DSG] Could not create flat sleeve-face cutter {index + 1}: {exc}')
    return cutters


def _component_is_sleeve_shell_for_implant(component, props, implant):
    """Recognize the exact loose sleeve shell so the flat face is never cut."""
    if not _valid_obj(component) or component.type != 'MESH' or not _valid_obj(implant):
        return False
    mesh = getattr(component, 'data', None)
    if mesh is None or not mesh.vertices:
        return False

    inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    radial_tol = max(0.18, float(getattr(props, 'sleeve_sidewall_clearance', 0.12)) + 0.08)
    axial_tol = 0.22

    try:
        to_local = get_sleeve_matrix_world(props, implant).inverted() @ component.matrix_world
    except Exception:
        return False

    count = len(mesh.vertices)
    # Dense shells do not need every vertex for reliable cylindrical bounds.
    stride = max(1, count // 4096)
    min_r = float('inf')
    max_r = 0.0
    min_z = float('inf')
    max_z = float('-inf')
    sampled = 0
    outside = 0
    for index in range(0, count, stride):
        co = to_local @ mesh.vertices[index].co
        radial = math.hypot(float(co.x), float(co.y))
        z = float(co.z)
        min_r = min(min_r, radial)
        max_r = max(max_r, radial)
        min_z = min(min_z, z)
        max_z = max(max_z, z)
        sampled += 1
        if radial > outer_r + radial_tol or abs(z) > half_h + axial_tol:
            outside += 1
            if outside > max(2, int(sampled * 0.02)):
                return False

    if sampled < 8:
        return False
    z_span = max_z - min_z
    return (
        outside == 0
        and min_r >= max(0.0, inner_r - radial_tol)
        and max_r <= outer_r + radial_tol
        and min_z <= -half_h + axial_tol * 2.0
        and max_z >= half_h - axial_tol * 2.0
        and z_span >= max(0.20, half_h * 1.45)
    )




def find_sleeve_shell_implant(component, props, implants=None):
    """Return the implant whose exact sleeve shell matches this loose component."""
    if not _valid_obj(component) or component.type != 'MESH':
        return None
    candidates = list(implants or [])
    if not candidates:
        try:
            candidates = get_all_implant_objects(props)
        except Exception:
            candidates = []
    for implant in candidates:
        if is_valid_implant_obj(implant) and _component_is_sleeve_shell_for_implant(
                component, props, implant):
            return implant
    return None


def component_is_any_sleeve_shell(component, props, implants=None):
    """Return True when a loose guide component is the exact sleeve shell."""
    return find_sleeve_shell_implant(component, props, implants=implants) is not None


def _angle_degrees_from_xy(x_value, y_value):
    angle = math.degrees(math.atan2(float(y_value), float(x_value)))
    while angle < 0.0:
        angle += 360.0
    while angle >= 360.0:
        angle -= 360.0
    return angle


def _cluster_circular_angles_degrees(angles, gap_deg=28.0):
    """Cluster polar angles while handling the 0/360° seam."""
    values = sorted(float(a) % 360.0 for a in angles if math.isfinite(float(a)))
    if not values:
        return []
    if len(values) == 1:
        return [values]

    gaps = []
    for index in range(len(values)):
        current = values[index]
        nxt = values[(index + 1) % len(values)]
        if index == len(values) - 1:
            nxt += 360.0
        gaps.append((nxt - current, index))
    _largest_gap, break_index = max(gaps, key=lambda item: item[0])

    ordered = []
    cursor = (break_index + 1) % len(values)
    previous = None
    for _ in range(len(values)):
        value = values[cursor]
        if previous is not None and value < previous:
            value += 360.0
        ordered.append(value)
        previous = value
        cursor = (cursor + 1) % len(values)

    clusters = [[ordered[0]]]
    gap = max(5.0, float(gap_deg))
    for value in ordered[1:]:
        if value - clusters[-1][-1] > gap:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return clusters


def _cluster_span_degrees(cluster):
    if not cluster:
        return 0.0
    return max(cluster) - min(cluster)


def cutter_has_c_sleeve_manifold(cutter, props=None):
    """True when the cutter is intended to create the open-C sleeve manifold."""
    if not _valid_obj(cutter):
        return False
    try:
        params = cutter.get('DSG_irrigation_params', '')
        if params:
            values = json.loads(str(params))
            mode = str(values.get('irr_sleeve_channel_mode', getattr(props, 'irr_sleeve_channel_mode', 'C') if props is not None else 'C')).upper()
            return mode != 'DIRECT'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        mode = str(cutter.get('DSG_irrigation_channel_mode', '')).upper()
        if mode:
            return mode != 'DIRECT'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        return bool(cutter.get('DSG_irrigation_internal_c_manifold', False))
    except Exception:
        return True


def irrigation_sleeve_raycast_preflight(context, sleeve_part, cutter, props, implant):
    """Validate a C-irrigation cutter before it is allowed to touch a sleeve.

    v7.0.16 keeps the user's selected C-channel.  The previous v7.0.15 guard
    simply skipped sleeve Booleans, which preserved the sleeve but also removed
    the C manifold from the sleeve itself.  This preflight is intentionally more
    surgical: it lets the intended inlet cut pass, but rejects the operation if
    ray tracing detects a second premature opening through the sleeve wall.
    """
    if not _valid_obj(sleeve_part) or not _valid_obj(cutter) or not is_valid_implant_obj(implant):
        return False, 'invalid sleeve/cutter for raycast preflight', {}

    if not cutter_has_c_sleeve_manifold(cutter, props):
        return True, 'direct sleeve channel: C-leak preflight not required', {
            'mode': 'DIRECT',
            'outer_clusters': 0,
            'ray_clusters': 0,
        }

    try:
        sleeve_mx = get_sleeve_matrix_world(props, implant)
        sleeve_inv = sleeve_mx.inverted_safe()
        cutter_to_sleeve = sleeve_inv @ cutter.matrix_world
    except Exception as exc:
        return False, f'could not evaluate sleeve local coordinates: {exc}', {}

    inner_r, outer_r, wall_t = _sleeve_radii_from_props(props)
    half_h = max(0.10, float(getattr(props, 'sleeve_height', 7.0)) * 0.5)
    wall_t = max(0.05, float(wall_t))
    leak_band = max(0.035, min(0.12, wall_t * 0.08))
    flat_face_keepout = max(0.12, min(0.35, wall_t * 0.18))
    angular_gap = 30.0

    mesh = getattr(cutter, 'data', None)
    if mesh is None or not mesh.vertices:
        return False, 'empty irrigation cutter', {}

    sampled = 0
    near_sleeve = 0
    outer_angles = []
    z_values = []
    face_keepout_hits = 0
    vertex_count = len(mesh.vertices)
    stride = max(1, vertex_count // 12000)
    for index in range(0, vertex_count, stride):
        local = cutter_to_sleeve @ mesh.vertices[index].co
        radial = math.hypot(float(local.x), float(local.y))
        z = float(local.z)
        sampled += 1
        if abs(z) > half_h + flat_face_keepout:
            continue
        if radial < max(0.0, inner_r - 0.45) or radial > outer_r + max(1.20, wall_t * 1.50):
            continue
        near_sleeve += 1
        z_values.append(z)

        # Any irrigation cut reaching the flat seating faces is forbidden.
        if (inner_r - 0.08) <= radial <= (outer_r + 0.12) and abs(z) > half_h - flat_face_keepout:
            face_keepout_hits += 1

        # Vertices close to the external cylindrical wall indicate an external
        # opening.  One cluster is the intended inlet.  Two separated clusters
        # mean a premature side-wall breakout/leak.
        if radial >= outer_r - leak_band and abs(z) <= half_h - flat_face_keepout:
            outer_angles.append(_angle_degrees_from_xy(local.x, local.y))

    if near_sleeve == 0:
        return True, 'cutter does not intersect this sleeve shell', {
            'mode': 'C',
            'outer_clusters': 0,
            'ray_clusters': 0,
            'sampled_vertices': int(sampled),
        }

    if face_keepout_hits > max(3, near_sleeve * 0.01):
        return False, (
            f'C-channel rejected: {face_keepout_hits} sampled cutter vertices enter the sleeve flat-face keepout zone'
        ), {
            'mode': 'C',
            'face_keepout_hits': int(face_keepout_hits),
            'near_sleeve_vertices': int(near_sleeve),
        }

    vertex_clusters = _cluster_circular_angles_degrees(outer_angles, gap_deg=angular_gap)
    meaningful_vertex_clusters = [cluster for cluster in vertex_clusters if len(cluster) >= 2]
    if len(meaningful_vertex_clusters) > 1:
        spans = [_cluster_span_degrees(cluster) for cluster in meaningful_vertex_clusters]
        return False, (
            f'C-channel rejected: {len(meaningful_vertex_clusters)} separated external wall openings detected by vertex scan'
        ), {
            'mode': 'C',
            'outer_clusters': int(len(meaningful_vertex_clusters)),
            'outer_cluster_spans_deg': [float(v) for v in spans],
        }
    if meaningful_vertex_clusters and _cluster_span_degrees(meaningful_vertex_clusters[0]) > 115.0:
        return False, (
            'C-channel rejected: the intended sleeve inlet is too wide around the sleeve wall'
        ), {
            'mode': 'C',
            'outer_clusters': 1,
            'outer_cluster_span_deg': float(_cluster_span_degrees(meaningful_vertex_clusters[0])),
        }

    # Ray trace from just outside the sleeve towards the axis.  A hit very near
    # the external cylindrical wall is a wall opening.  Only one angular opening
    # is accepted; more than one means irrigation water can escape through the
    # sleeve side wall before reaching the planned outlets.
    z_values = sorted(z_values)
    if z_values:
        q1 = z_values[len(z_values) // 4]
        median = z_values[len(z_values) // 2]
        q3 = z_values[(len(z_values) * 3) // 4]
        z_scan_values = []
        for value in (q1, median, q3):
            value = max(-half_h + flat_face_keepout, min(half_h - flat_face_keepout, float(value)))
            if not any(abs(value - existing) < 0.05 for existing in z_scan_values):
                z_scan_values.append(value)
    else:
        z_scan_values = [0.0]

    ray_angles = []
    rot = sleeve_mx.to_3x3()
    ray_count = 72
    ray_start_margin = max(0.50, wall_t * 0.80)
    ray_distance = max(2.0, outer_r + ray_start_margin + 0.50)
    for z in z_scan_values:
        for ray_index in range(ray_count):
            angle = (2.0 * math.pi * ray_index) / float(ray_count)
            local_dir = Vector((math.cos(angle), math.sin(angle), 0.0))
            origin_world = sleeve_mx @ Vector((
                local_dir.x * (outer_r + ray_start_margin),
                local_dir.y * (outer_r + ray_start_margin),
                float(z),
            ))
            direction_world = -(rot @ local_dir)
            hit, _normal, _face_index = raycast_object_along_world(
                context, cutter, origin_world, direction_world, distance=ray_distance)
            if hit is None:
                continue
            hit_local = sleeve_inv @ hit
            hit_radial = math.hypot(float(hit_local.x), float(hit_local.y))
            if hit_radial >= outer_r - leak_band:
                ray_angles.append(_angle_degrees_from_xy(hit_local.x, hit_local.y))

    ray_clusters = _cluster_circular_angles_degrees(ray_angles, gap_deg=angular_gap)
    meaningful_ray_clusters = [cluster for cluster in ray_clusters if len(cluster) >= 2]
    if len(meaningful_ray_clusters) > 1:
        spans = [_cluster_span_degrees(cluster) for cluster in meaningful_ray_clusters]
        return False, (
            f'C-channel rejected: raycast found {len(meaningful_ray_clusters)} separated sleeve-wall outlets; reposition irrigation point or reduce outlet diameter'
        ), {
            'mode': 'C',
            'ray_clusters': int(len(meaningful_ray_clusters)),
            'ray_cluster_spans_deg': [float(v) for v in spans],
            'scan_z_count': int(len(z_scan_values)),
        }
    if meaningful_ray_clusters and _cluster_span_degrees(meaningful_ray_clusters[0]) > 125.0:
        return False, (
            'C-channel rejected: raycast shows an excessively wide sleeve-wall opening'
        ), {
            'mode': 'C',
            'ray_clusters': 1,
            'ray_cluster_span_deg': float(_cluster_span_degrees(meaningful_ray_clusters[0])),
        }

    return True, 'C-channel sleeve raycast preflight OK', {
        'mode': 'C',
        'outer_clusters': int(len(meaningful_vertex_clusters)),
        'ray_clusters': int(len(meaningful_ray_clusters)),
        'near_sleeve_vertices': int(near_sleeve),
        'sampled_vertices': int(sampled),
        'scan_z_count': int(len(z_scan_values)),
    }


def _irrigation_entry_channel_mode(entry, props):
    """Return the saved irrigation channel mode for an entry without touching UI state."""
    try:
        parameters = entry.get('parameters', {}) if isinstance(entry, dict) else {}
        if isinstance(parameters, dict):
            mode = parameters.get('irr_sleeve_channel_mode', None)
            if mode is not None:
                return str(mode or 'C').upper()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        return str(getattr(props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
    except Exception:
        return 'C'


def _deduplicate_irrigation_lumen_samples(samples, epsilon=0.02):
    """Clean water-lumen samples without ever expanding to the tube wall."""
    clean = []
    for item in list(samples or []):
        if not item or len(item) < 2:
            continue
        try:
            point = Vector(item[0])
            radius = max(0.02, float(item[1]))
        except Exception:
            continue
        if clean and (point - clean[-1][0]).length <= float(epsilon):
            clean[-1] = (clean[-1][0], max(clean[-1][1], radius))
        else:
            clean.append((point, radius))
    return clean


def _irrigation_resolve_implant_for_entry(entry, props, controls=None):
    """Resolve the implant used by the irrigation entry without guessing from UI state."""
    implant_obj = entry.get('implant') if isinstance(entry, dict) else None
    if is_valid_implant_obj(implant_obj):
        return implant_obj
    implant_name = ''
    try:
        implant_name = str(entry.get('implant_name', '') if isinstance(entry, dict) else '')
    except Exception:
        implant_name = ''
    if implant_name:
        implant_obj = bpy.data.objects.get(implant_name)
        if is_valid_implant_obj(implant_obj):
            return implant_obj
    pts = controls if controls is not None else (entry.get('points', []) if isinstance(entry, dict) else [])
    try:
        if len(pts) > 1:
            return get_nearest_implant_to_point(props, pts[1])
        if len(pts) > 0:
            return get_nearest_implant_to_point(props, pts[0])
    except Exception:
        return None
    return None


def _irrigation_internal_sleeve_manifold_sample_groups(control_points, props, implant_obj=None):
    """Return sample groups for the final water lumen that lives inside the sleeve.

    The visible/debug lumen must not stop at the lateral exit hole.  In C mode the
    final cutter also contains a split plenum, two C-arc branches and two rounded
    outlets into the sleeve lumen.  These samples mirror
    build_irrigation_internal_ring_parts() so the preflight and the diagnostic
    inspect the same hydraulic volume that the final Boolean cuts.
    """
    controls = [Vector(point) for point in list(control_points or [])]
    if len(controls) < 2:
        return []
    try:
        ring = get_irrigation_internal_ring_geometry(controls[1], props, implant_obj)
    except Exception:
        ring = None
    if not ring:
        return []

    groups = []
    try:
        radial = Vector(ring.get('radial', (1.0, 0.0, 0.0)))
        if radial.length < 1.0e-8:
            radial = Vector((1.0, 0.0, 0.0))
        radial.normalize()
        split = Vector(ring['split_point'])
        plenum_r = max(0.18, float(ring['split_plenum_r']))
        plenum_half = max(0.06, min(0.18, plenum_r * 0.35))
        groups.append([
            (split - radial * plenum_half, plenum_r, plenum_r),
            (split + radial * plenum_half, plenum_r, plenum_r),
        ])
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        branch_radius = max(0.14, float(ring['branch_tube_r']))
        for path_key in ('upper_arc', 'lower_arc'):
            path = [Vector(point) for point in list(ring.get(path_key, []) or [])]
            clean = _deduplicate_irrigation_lumen_samples(
                [(point, branch_radius) for point in path], epsilon=0.006)
            if len(clean) >= 2:
                groups.append([(Vector(point), float(radius), float(radius)) for point, radius in clean])
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        branch_radius = max(0.14, float(ring['branch_tube_r']))
        outlet_radius = min(max(float(ring['side_hole_r']), branch_radius * 0.82), branch_radius * 0.98)
        outlet_specs = (
            (ring.get('upper_arc', []), ring['upper_attach_point'], ring['upper_lumen_point']),
            (ring.get('lower_arc', []), ring['lower_attach_point'], ring['lower_lumen_point']),
        )
        for arc_path, start, end in outlet_specs:
            start = Vector(start)
            end = Vector(end)
            if len(arc_path) >= 2:
                start_direction = Vector(arc_path[-1]) - Vector(arc_path[-2])
            else:
                start_direction = end - start
            end_direction = Vector(ring['center']) - end
            elbow_points = _sample_plumbing_elbow_curve(
                start,
                end,
                start_direction,
                end_direction,
                min_turn_radius=max(outlet_radius * 1.35, branch_radius * 1.10),
                max_step=0.07,
            )
            clean = _deduplicate_irrigation_lumen_samples(
                [(Vector(point), outlet_radius) for point in elbow_points], epsilon=0.006)
            if len(clean) >= 2:
                groups.append([(Vector(point), float(radius), float(radius)) for point, radius in clean])
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    return groups


def _irrigation_model_preflight_sample_groups(entry, props, wye_specs=None, balances=None):
    """Build every final water-lumen segment checked by the preflight.

    v7.0.28 fixes the diagnostic shown by the user: the checked geometry no
    longer stops at the lateral sleeve hole.  It includes the external channel
    plus the same internal sleeve C-manifold/plenum/outlets that the final cutter
    adds in build_irrigation_single_lumen_cutter() and
    build_irrigation_y_network_lumen_cutter().
    """
    if not isinstance(entry, dict):
        return []
    points = [Vector(point) for point in entry.get('points', [])]
    if len(points) < 2:
        return []

    try:
        entry_props, _parameters = _irrigation_entry_effective_props(props, entry)
    except Exception:
        entry_props = irrigation_props_overlay(props, entry.get('parameters', {}))

    groups = []
    try:
        samples = build_irrigation_lumen_samples_from_controls(
            points, entry_props, include_overshoot=True)
        samples = apply_venturi_profile_to_samples(samples, None)
        samples = _apply_entry_midpoint_geometry(samples, entry, list(wye_specs or []))
        if balances is not None:
            samples = _apply_entry_balancing(samples, entry, list(wye_specs or []), balances)
    except Exception:
        samples = []

    clean = _deduplicate_irrigation_lumen_samples(samples, epsilon=0.006)
    if len(clean) >= 2:
        groups.append([(Vector(point), float(radius), float(radius))
                       for point, radius in clean])

    implant_obj = _irrigation_resolve_implant_for_entry(entry, props, points)
    try:
        groups.extend(_irrigation_internal_sleeve_manifold_sample_groups(
            points, entry_props, implant_obj=implant_obj))
    except Exception as exc:
        print(f'[DSG] Could not add sleeve manifold to preflight samples: {exc}')

    return [group for group in groups if len(group) >= 2]


def _irrigation_model_preflight_samples(entry, props):
    """Compatibility: flattened complete water-lumen sample list."""
    flat = []
    for group in _irrigation_model_preflight_sample_groups(entry, props):
        flat.extend(group)
    return flat


def _irrigation_sample_tangent(samples, index):
    if not samples:
        return Vector((1.0, 0.0, 0.0))
    if len(samples) == 1:
        return Vector((1.0, 0.0, 0.0))
    idx = max(0, min(int(index), len(samples) - 1))
    if idx == 0:
        tangent = samples[1][0] - samples[0][0]
    elif idx >= len(samples) - 1:
        tangent = samples[-1][0] - samples[-2][0]
    else:
        tangent = samples[idx + 1][0] - samples[idx - 1][0]
    if tangent.length < 1.0e-8:
        return Vector((1.0, 0.0, 0.0))
    tangent.normalize()
    return tangent


def irrigation_model_cut_preflight(context, entry, props, passive_model=None,
                                   label='irrigation'):
    """Preflight the exact irrigation water lumen against the passive model.

    The blocker is deliberately based on the water passage, not on the whole
    outside wall of the tube.  It rejects only when the passive model invades the
    lumen itself, when the lumen centre/ring is already inside the model, or when
    the final Boolean would leave virtually no material between the water lumen
    and the model.  This prevents the leak shown by the user while avoiding the
    old over-conservative "outside wall touched the model" rule.
    """
    mode = _irrigation_entry_channel_mode(entry, props)
    model = passive_model if _valid_obj(passive_model) else get_passive_model_obj()

    if not _valid_obj(model) or model.type != 'MESH':
        return True, 'passive model not available; water-lumen preflight skipped', {
            'status': 'skipped',
            'reason': 'missing_passive_model',
            'policy': 'EXACT_WATER_LUMEN_MODEL_PREFLIGHT',
            'mode': mode,
        }

    sample_groups = _irrigation_model_preflight_sample_groups(entry, props)
    total_sample_count = sum(len(group) for group in sample_groups)
    if total_sample_count < 2:
        return False, 'could not rebuild exact irrigation lumen samples for model preflight', {
            'status': 'red',
            'reason': 'invalid_irrigation_lumen_samples',
            'policy': 'EXACT_WATER_LUMEN_MODEL_PREFLIGHT',
            'mode': mode,
        }

    try:
        model_tree = _build_world_surface_bvh(context, model)
    except Exception:
        model_tree = None
    if model_tree is None:
        return True, 'model BVH unavailable; water-lumen preflight skipped', {
            'status': 'skipped',
            'reason': 'model_bvh_unavailable',
            'policy': 'EXACT_WATER_LUMEN_MODEL_PREFLIGHT',
            'mode': mode,
            'model': _safe_object_name(model),
        }

    try:
        final_voxel = float(getattr(props, 'dct_final_cutter_voxel_size', 0.18))
    except Exception:
        final_voxel = 0.18
    try:
        saved_parameters = entry.get('parameters', {}) if isinstance(entry, dict) else {}
        entry_props = irrigation_props_overlay(props, saved_parameters)
        wall_t = max(0.05, float(getattr(entry_props, 'irr_wall_thickness', 1.5)))
    except Exception:
        wall_t = 1.5

    # Numerical guard around the true water lumen.  The blocker is intentionally
    # narrow: final-lumen radius + Boolean/print tolerance.  The exterior wall
    # and its radial sleeve blend are NOT used as rejection geometry.
    lumen_guard = max(0.04, min(0.12, final_voxel * 0.55))
    retained_wall_guard = max(lumen_guard, min(0.18, final_voxel * 0.90))

    try:
        model_solid_report = get_mesh_solid_report(model, max_polygons=500000)
    except Exception:
        model_solid_report = {'checked': False, 'solid': False}
    inside_checks_enabled = bool(
        model_solid_report.get('checked') and model_solid_report.get('solid'))

    stride = max(1, total_sample_count // 320)
    radial_rays = 32
    ring_probe_count = 16
    near_lumen_count = 0
    lumen_conflicts = []
    inside_conflicts = []
    reserve_conflicts = []
    lumen_ray_conflicts = []
    ring_inside_conflicts = []
    min_lumen_clearance = None
    min_reserve_clearance = None

    global_sample_index = 0
    for group_index, samples in enumerate(sample_groups):
        group_stride = max(1, min(stride, max(1, len(samples))))
        for idx in range(0, len(samples), group_stride):
            sample_id = global_sample_index + idx
            center, lumen_r, _ignored_wall_r = samples[idx]
            center = Vector(center)
            lumen_r = max(0.02, float(lumen_r))
            test_r = lumen_r + lumen_guard
            reserve_r = lumen_r + retained_wall_guard

            try:
                nearest = model_tree.find_nearest(center)
            except Exception:
                nearest = None
            if nearest and nearest[0] is not None:
                _loc, _normal, _face_index, distance = nearest
                if distance is not None:
                    distance = float(distance)
                    lumen_clearance = distance - lumen_r
                    reserve_clearance = distance - reserve_r
                    min_lumen_clearance = lumen_clearance if min_lumen_clearance is None else min(min_lumen_clearance, lumen_clearance)
                    min_reserve_clearance = reserve_clearance if min_reserve_clearance is None else min(min_reserve_clearance, reserve_clearance)
                    if distance <= test_r:
                        lumen_conflicts.append((sample_id, distance, lumen_r, test_r))
                        near_lumen_count += 1
                    elif distance <= reserve_r:
                        reserve_conflicts.append((sample_id, distance, lumen_r, reserve_r))
                        near_lumen_count += 1

            # If the centreline is inside a CLOSED tooth/model, nearest-distance
            # checks can falsely pass because the nearest surface may be farther
            # away than the water radius.  The parity test is only trusted for a
            # verified solid; open/non-manifold STL models otherwise create false
            # positives.
            if inside_checks_enabled and _bvh_point_inside_solid(
                    model_tree, center, tolerance=max(0.01, lumen_guard * 0.25)):
                inside_conflicts.append((sample_id, lumen_r))
                near_lumen_count += 1

            tangent = _irrigation_sample_tangent(samples, idx)
            basis_u, basis_v, _axis = build_axis_basis(tangent)

            # Radial rays from the water centreline to the lumen/reserve boundary.
            # They do not use the external tube wall as a broad halo.
            for ray_index in range(radial_rays):
                angle = (2.0 * math.pi * ray_index) / float(radial_rays)
                direction = (basis_u * math.cos(angle) + basis_v * math.sin(angle))
                if direction.length < 1.0e-8:
                    continue
                direction.normalize()
                hit_distance = _bvh_world_ray_distance(
                    model_tree, center, direction, reserve_r)
                if hit_distance is None:
                    continue
                if hit_distance <= test_r:
                    lumen_ray_conflicts.append((sample_id, hit_distance, lumen_r, test_r))
                elif hit_distance <= reserve_r:
                    reserve_conflicts.append((sample_id, hit_distance, lumen_r, reserve_r))

            # Probe real points around the lumen wall/reserve.  This is what makes the
            # check robust when the water tube is already embedded in the model.
            for probe_index in range(ring_probe_count):
                angle = (2.0 * math.pi * probe_index) / float(ring_probe_count)
                direction = (basis_u * math.cos(angle) + basis_v * math.sin(angle))
                if direction.length < 1.0e-8:
                    continue
                direction.normalize()
                if not inside_checks_enabled:
                    continue
                lumen_probe = center + direction * min(test_r, reserve_r)
                if _bvh_point_inside_solid(
                        model_tree, lumen_probe, tolerance=max(0.01, lumen_guard * 0.20)):
                    ring_inside_conflicts.append((sample_id, lumen_r, 'lumen_ring'))
                    break
                reserve_probe = center + direction * reserve_r
                if _bvh_point_inside_solid(
                        model_tree, reserve_probe, tolerance=max(0.01, lumen_guard * 0.20)):
                    reserve_conflicts.append((sample_id, reserve_r, lumen_r, reserve_r))
                    break

        global_sample_index += len(samples)

    hard_lumen_conflicts = (
        len(lumen_conflicts) + len(lumen_ray_conflicts) +
        len(inside_conflicts) + len(ring_inside_conflicts)
    )
    reserve_conflict_count = len(reserve_conflicts)
    conflict_count = hard_lumen_conflicts + reserve_conflict_count
    common_data = {
        'status': 'green' if conflict_count == 0 else 'red',
        'policy': 'EXACT_FINAL_LUMEN_PLUS_SLEEVE_MANIFOLD_PREFLIGHT_V7_0_28',
        'mode': mode,
        'ray_policy': 'RADIAL_RAYS_FROM_ORDERED_FINAL_WATER_LUMEN_ONLY',
        'wall_policy': 'OUTER_WALL_AND_WALL_BLEND_IGNORED_FOR_REJECTION',
        'inside_policy': 'ONLY_IF_PASSIVE_MODEL_IS_VERIFIED_SOLID',
        'passive_model_solid_report': dict(model_solid_report or {}),
        'model': _safe_object_name(model),
        'label': str(label),
        'sample_count': int(total_sample_count),
        'sample_group_count': int(len(sample_groups)),
        'sample_stride': int(stride),
        'guard_mm': float(lumen_guard),
        'lumen_guard_mm': float(lumen_guard),
        'retained_wall_guard_mm': float(retained_wall_guard),
        'minimum_lumen_clearance_mm': float(min_lumen_clearance) if min_lumen_clearance is not None else None,
        'minimum_clearance_mm': float(min_lumen_clearance) if min_lumen_clearance is not None else None,
        'minimum_retained_wall_clearance_mm': float(min_reserve_clearance) if min_reserve_clearance is not None else None,
        'near_model_samples': int(near_lumen_count),
        'near_lumen_samples': int(near_lumen_count),
        'wall_conflicts': 0,
        'lumen_conflicts': int(len(lumen_conflicts)),
        'inside_lumen_conflicts': int(len(inside_conflicts)),
        'ring_inside_conflicts': int(len(ring_inside_conflicts)),
        'ray_conflicts': int(len(lumen_ray_conflicts)),
        'lumen_ray_conflicts': int(len(lumen_ray_conflicts)),
        'retained_wall_conflicts': int(reserve_conflict_count),
    }

    if hard_lumen_conflicts:
        return False, (
            f'{label}: el modelo/diente invade la luz real del canal de irrigación; '
            f'el agua quedaría comunicada con el modelo al hacer el corte final'), common_data
    if reserve_conflicts:
        common_data['status'] = 'orange'
        common_data['warning'] = (
            'El modelo está cerca de la luz del agua, pero no invade el lumen real; '
            'se permite continuar porque la pared exterior no es criterio de bloqueo.')

    return True, f'{label}: exact final water-lumen preflight OK', common_data


