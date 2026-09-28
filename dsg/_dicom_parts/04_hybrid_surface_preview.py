def _surface_preview_material(structure: str = "TEETH") -> bpy.types.Material:
    """Return one stable opaque material for the disposable solid preview."""
    material = bpy.data.materials.get(SURFACE_PREVIEW_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(SURFACE_PREVIEW_MATERIAL_NAME)
    structure = str(structure).upper()
    rgb = SEGMENTATION_STRUCTURES.get(structure, SEGMENTATION_STRUCTURES["TEETH"])["color"]
    color = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
    try:
        material.diffuse_color = color
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    material.use_nodes = True
    tree = getattr(material, "node_tree", None)
    if tree is not None:
        bsdf = tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            socket = bsdf.inputs.get("Base Color")
            if socket is not None:
                socket.default_value = color
            socket = bsdf.inputs.get("Roughness")
            if socket is not None:
                socket.default_value = 0.68
            socket = bsdf.inputs.get("Metallic")
            if socket is not None:
                socket.default_value = 0.0
            socket = bsdf.inputs.get("Alpha")
            if socket is not None:
                socket.default_value = 1.0
    for attr, value in (
        ("surface_render_method", "DITHERED"),
        ("blend_method", "OPAQUE"),
        ("show_transparent_back", True),
    ):
        try:
            setattr(material, attr, value)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    material["dsg_surface_preview_material"] = True
    return material


def _ensure_surface_preview_object(context: bpy.types.Context) -> bpy.types.Object:
    """Create a persistent object/mesh pair so rebuilding never swaps materials."""
    obj = bpy.data.objects.get(SURFACE_PREVIEW_OBJECT_NAME)
    if obj is not None and obj.type != "MESH":
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = None

    mesh = bpy.data.meshes.get(SURFACE_PREVIEW_MESH_NAME)
    if mesh is None:
        mesh = bpy.data.meshes.new(SURFACE_PREVIEW_MESH_NAME)

    collection = get_collection()
    if obj is None:
        obj = bpy.data.objects.new(SURFACE_PREVIEW_OBJECT_NAME, mesh)
        collection.objects.link(obj)
    else:
        if obj.data is not mesh:
            old_mesh = obj.data
            obj.data = mesh
            if old_mesh is not None and old_mesh.users == 0 and old_mesh.name.startswith(SURFACE_PREVIEW_MESH_NAME):
                try:
                    bpy.data.meshes.remove(old_mesh)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)

    root = get_root(collection)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    obj.hide_render = True
    obj.hide_select = True
    obj.show_in_front = False
    try:
        obj.display_type = "TEXTURED"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj["dicom_surface_preview"] = True
    obj["dicom_alignment_frame"] = "shared DICOM_WIZARD_ROOT local frame"

    material = _surface_preview_material(
        getattr(context.scene.dicom_wizard_pro, "segmentation_structure", "TEETH")
    )
    slots = mesh.materials
    if len(slots) == 0:
        slots.append(material)
    elif slots[0] != material:
        slots[0] = material
    return obj


def _clear_surface_preview_geometry(*, hide: bool = True) -> None:
    obj = bpy.data.objects.get(SURFACE_PREVIEW_OBJECT_NAME)
    if obj is None or obj.type != "MESH":
        return
    if hide:
        try:
            obj.hide_set(True)
            obj.hide_viewport = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    mesh = obj.data
    try:
        if hasattr(mesh, "clear_geometry"):
            mesh.clear_geometry()
        else:
            empty = bpy.data.meshes.new(SURFACE_PREVIEW_MESH_NAME + "_EMPTY")
            obj.data = empty
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            empty.name = SURFACE_PREVIEW_MESH_NAME
        mesh.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    RUNTIME.surface_preview_ready_threshold = None
    RUNTIME.surface_preview_ready_structure = ""
    RUNTIME.surface_preview_ready_quality = 0


def _surface_preview_matches(props) -> bool:
    obj = bpy.data.objects.get(SURFACE_PREVIEW_OBJECT_NAME)
    if obj is None or obj.type != "MESH" or obj.data is None or len(obj.data.vertices) == 0:
        return False
    low = obj.get("dicom_density_low", obj.get("dicom_density_threshold"))
    high = obj.get("dicom_density_high", low)
    if low is None or high is None:
        return False
    low_tol = max(1e-4, abs(float(props.auto_range_low)) * 1e-6)
    high_tol = max(1e-4, abs(float(props.auto_range_high)) * 1e-6)
    return (
        abs(float(low) - float(props.auto_range_low)) <= low_tol
        and abs(float(high) - float(props.auto_range_high)) <= high_tol
        and RUNTIME.surface_preview_ready_structure == str(props.segmentation_structure)
        and RUNTIME.surface_preview_ready_quality == int(props.surface_preview_quality)
    )


def _cached_surface_preview_sample(max_axis: int):
    max_axis = int(max_axis)
    cached = RUNTIME.surface_preview_sample_cache.get(max_axis)
    if cached is not None:
        return cached
    sampled = _sample_density_for_surface(max_axis)
    RUNTIME.surface_preview_sample_cache[max_axis] = sampled
    return sampled


def _set_surface_preview_mesh(
    context: bpy.types.Context,
    vertices_xyz,
    faces,
    *,
    threshold: float,
    threshold_high: float,
    structure: str,
    quality: int,
) -> bpy.types.Object:
    """Replace geometry in one persistent mesh datablock on Blender's main thread."""
    obj = _ensure_surface_preview_object(context)
    mesh = obj.data
    try:
        obj.hide_set(True)
        obj.hide_viewport = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if hasattr(mesh, "clear_geometry"):
        mesh.clear_geometry()
    else:
        old_mesh = mesh
        mesh = bpy.data.meshes.new(SURFACE_PREVIEW_MESH_NAME + "_BUILD")
        obj.data = mesh
        if old_mesh.users == 0:
            try:
                bpy.data.meshes.remove(old_mesh)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        mesh.name = SURFACE_PREVIEW_MESH_NAME

    mesh.from_pydata(vertices_xyz.tolist(), [], faces.tolist())
    mesh.update(calc_edges=True)
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    material = _surface_preview_material(structure)
    if len(mesh.materials) == 0:
        mesh.materials.append(material)
    elif mesh.materials[0] != material:
        mesh.materials[0] = material

    obj["dicom_density_threshold"] = float(threshold)
    obj["dicom_density_low"] = float(threshold)
    obj["dicom_density_high"] = float(threshold_high)
    obj["dicom_surface_preview_quality"] = int(quality)
    obj["dental_suite_structure"] = str(structure)
    RUNTIME.surface_preview_ready_threshold = float(threshold)
    RUNTIME.surface_preview_ready_structure = str(structure)
    RUNTIME.surface_preview_ready_quality = int(quality)
    return obj


def _sampled_hysteresis_mask(sampled_values, finite, support_low: float,
                             seed_high: float, upper: float):
    """Connectivity-only hysteresis for the bounded DICOM preview grid."""
    np = load_numpy()
    support = finite & (sampled_values >= float(support_low)) & (sampled_values <= float(upper))
    seeds = finite & (sampled_values >= float(seed_high)) & (sampled_values <= float(upper))
    if not seeds.any() or not support.any():
        return np.zeros_like(support, dtype=bool)
    ndi = load_scipy_ndimage()
    if ndi is not None:
        return ndi.binary_propagation(
            seeds, mask=support, structure=ndi.generate_binary_structure(3, 2)
        ).astype(bool, copy=False)
    runs, parent, _sizes, _boundary = _rle_component_analysis(support, adjacency=1)
    keep = _roots_overlapping_mask(runs, parent, seeds)
    return _mask_from_component_roots(support.shape, runs, parent, keep)


def _build_surface_preview(context: bpy.types.Context, generation: int) -> bool:
    """Build a bounded solid preview with the same native engine as final output."""
    if (
        RUNTIME.undo_in_progress
        or RUNTIME.update_lock
        or generation != RUNTIME.surface_preview_generation
        or not RUNTIME.is_loaded()
    ):
        return False
    scene = getattr(context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
    if props is None or int(getattr(props, "step", 1)) != 3:
        return False

    if (
        core.clinical_route(scene) == core.ROUTE_SIMPLE
        and str(scene.get(core.ROUTE_STEP_KEY, "") or "") == "SIMPLE_DENSITY"
    ):
        # In the SIMPLE path the visible density slider is the SSOT. The same
        # threshold drives both this lightweight solid preview and the final STL.
        update_density_labels(props)
        low = float(getattr(props, "current_density_min", props.auto_range_low))
        high = float(getattr(props, "current_density_max", props.auto_range_high))
    else:
        low = float(min(props.auto_range_low, props.auto_range_high))
        high = float(max(props.auto_range_low, props.auto_range_high))
    quality = int(props.surface_preview_quality)
    structure = str(props.segmentation_structure).upper()
    RUNTIME.surface_preview_building = True
    props.surface_preview_ready = False
    props.surface_preview_status = "Calculando sólido…"
    force_ui_redraw()

    try:
        sampled_values, z_indices, y_indices, x_indices, _stride = _cached_surface_preview_sample(quality)
        np = load_numpy()
        finite = np.isfinite(sampled_values)
        if not finite.any():
            raise RuntimeError("El volumen no contiene densidades válidas")
        finite_values = sampled_values[finite]
        if low >= float(finite_values.max()):
            raise RuntimeError("El umbral inferior queda fuera del volumen útil")
        if structure == "BONE":
            sampled_mask = finite & (sampled_values >= low)
        elif structure == "TEETH":
            seed_high = float(getattr(props, "auto_tooth_seed_threshold", low))
            sampled_mask = _sampled_hysteresis_mask(
                sampled_values, finite, low, seed_high, high
            )
        elif structure == "BONE_ONLY":
            bone_floor = float(low)
            mineral = finite & (sampled_values >= bone_floor)
            seed_high = float(getattr(props, "auto_tooth_seed_threshold", props.auto_bone_teeth_threshold))
            teeth = _sampled_hysteresis_mask(
                sampled_values, finite,
                float(props.auto_bone_teeth_threshold),
                seed_high,
                float(props.auto_metal_cutoff),
            )
            sampled_mask = mineral & ~teeth
        else:
            if high <= low or high <= float(finite_values.min()):
                raise RuntimeError("El intervalo de densidad no es válido")
            sampled_mask = finite & (sampled_values >= low) & (sampled_values <= high)
        if int(sampled_mask.sum()) < 2:
            raise RuntimeError("El intervalo no contiene anatomía visible")

        vertices_xyz, faces, _stats = _voxel_shell_from_sampled_mask(
            sampled_mask, z_indices, y_indices, x_indices
        )
        if generation != RUNTIME.surface_preview_generation or RUNTIME.undo_in_progress:
            return False
        _set_surface_preview_mesh(
            context,
            vertices_xyz,
            faces,
            threshold=low,
            threshold_high=high,
            structure=structure,
            quality=quality,
        )
        props.surface_preview_ready = True
        props.surface_preview_status = f"{len(faces):,} caras · máscara 3D adaptativa"
        return True
    except Exception as exc:
        _clear_surface_preview_geometry(hide=True)
        props.surface_preview_ready = False
        props.surface_preview_status = f"Vista sólida no disponible: {exc}"
        print("DICOM native solid preview warning:", repr(exc))
        return False
    finally:
        RUNTIME.surface_preview_building = False
        try:
            update_visibility(context)
            force_ui_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _surface_preview_timer():
    if RUNTIME.undo_in_progress:
        RUNTIME.surface_preview_timer_registered = False
        return None
    generation = RUNTIME.surface_preview_generation
    elapsed = time.monotonic() - RUNTIME.surface_preview_last_change_time
    if elapsed < SURFACE_PREVIEW_IDLE_SECONDS:
        return max(0.03, SURFACE_PREVIEW_IDLE_SECONDS - elapsed)

    RUNTIME.surface_preview_timer_registered = False
    try:
        context = bpy.context
        scene = getattr(context, "scene", None)
        props = getattr(scene, "dicom_wizard_pro", None) if scene is not None else None
        if props is None or int(getattr(props, "step", 1)) != 3:
            return None
        _build_surface_preview(context, generation)
    except Exception as exc:
        print("DICOM surface preview timer warning:", repr(exc))
    return None


def _auto_solid_preview_enabled(props) -> bool:
    """The solid preview is bundled with DSG and has no external engine gate."""
    return bool(getattr(props, "auto_solid_preview", True))


def schedule_surface_preview(context: bpy.types.Context, *, immediate: bool = False) -> None:
    """Invalidate the old solid and schedule one low-resolution rebuild.

    SIMPLE_DENSITY is excluded in v9.2.75 because even the delayed preview runs
    on Blender's main thread and can grey/freeze the UI on large CBCTs.
    """
    if RUNTIME.undo_in_progress or RUNTIME.update_lock:
        return
    try:
        scene = context.scene
        if (
            core.clinical_route(scene) == core.ROUTE_SIMPLE
            and str(scene.get(core.ROUTE_STEP_KEY, "") or "") == "SIMPLE_DENSITY"
        ):
            return
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    props = getattr(getattr(context, "scene", None), "dicom_wizard_pro", None)
    if props is None or int(getattr(props, "step", 1)) != 3:
        return

    RUNTIME.surface_preview_generation += 1
    RUNTIME.surface_preview_last_change_time = time.monotonic() - (SURFACE_PREVIEW_IDLE_SECONDS if immediate else 0.0)
    props.surface_preview_ready = False
    # The solid preview is mandatory in DSG.  The GPU volume remains visible
    # only as immediate feedback until the delayed surface is ready.
    props.surface_preview_status = "Preparando sólido…"
    # Never show stale geometry. In SURFACE mode the volume temporarily becomes
    # visible, giving immediate feedback until the solid is ready.
    obj = bpy.data.objects.get(SURFACE_PREVIEW_OBJECT_NAME)
    if obj is not None:
        try:
            obj.hide_set(True)
            obj.hide_viewport = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    update_visibility(context)

    if RUNTIME.surface_preview_timer_registered:
        return
    RUNTIME.surface_preview_timer_registered = True
    first_interval = 0.03 if immediate else SURFACE_PREVIEW_IDLE_SECONDS
    try:
        lifecycle.register_timer(_surface_preview_timer, first_interval=first_interval)
    except Exception:
        RUNTIME.surface_preview_timer_registered = False


def on_auto_solid_preview_change(self, context) -> None:
    """Keep the automatic solid preview permanently enabled."""
    if RUNTIME.undo_in_progress or RUNTIME.update_lock:
        return
    try:
        # Retained as a hidden compatibility property for older .blend files.
        # Runtime behavior no longer permits the volume-only mode.
        self.preview_display_mode = "SURFACE"
        self.surface_preview_status = f"Espera {SURFACE_PREVIEW_IDLE_SECONDS:.1f}s para vista sólida"
        schedule_surface_preview(context, immediate=False)
        force_ui_redraw()
    except Exception as exc:
        print("DICOM automatic solid preview warning:", repr(exc))


def on_surface_preview_quality_change(self, context) -> None:
    if RUNTIME.undo_in_progress or RUNTIME.update_lock:
        return
    try:
        schedule_surface_preview(context, immediate=False)
    except Exception as exc:
        print("DICOM preview quality warning:", repr(exc))


def _save_clinical_view_state(area, space) -> None:
    pointer = int(area.as_pointer())
    if pointer in RUNTIME.clinical_view_state:
        return
    overlay = getattr(space, "overlay", None)
    shading = getattr(space, "shading", None)
    RUNTIME.clinical_view_state[pointer] = {
        "show_overlays": getattr(overlay, "show_overlays", True),
        "show_gizmo": getattr(space, "show_gizmo", True),
        "shading_type": getattr(shading, "type", "MATERIAL"),
        "background_type": getattr(shading, "background_type", "THEME"),
        "background_color": tuple(getattr(shading, "background_color", (0.05, 0.05, 0.05))),
        "show_cavity": getattr(shading, "show_cavity", False),
        "cavity_type": getattr(shading, "cavity_type", "SCREEN"),
    }


def configure_clinical_preview_view(context: bpy.types.Context, *, frame: bool = False) -> None:
    """Create a clean diagnostic-style viewport without changing user objects."""
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        _save_clinical_view_state(area, space)
        try:
            space.overlay.show_overlays = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            space.show_gizmo = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        shading = getattr(space, "shading", None)
        if shading is not None:
            for attr, value in (
                ("type", "MATERIAL"),
                ("background_type", "VIEWPORT"),
                ("background_color", (0.022, 0.024, 0.030)),
                ("show_cavity", True),
                ("cavity_type", "BOTH"),
                ("show_shadows", True),
                ("show_specular_highlight", True),
            ):
                try:
                    setattr(shading, attr, value)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            for attr, value in (
                ("curvature_ridge_factor", 1.4),
                ("curvature_valley_factor", 1.1),
            ):
                try:
                    setattr(shading, attr, value)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        if frame:
            rv3d = getattr(space, "region_3d", None)
            if rv3d is not None:
                target = bpy.data.objects.get(ROOT_NAME)
                try:
                    rv3d.view_location = (
                        target.matrix_world.translation.copy()
                        if target is not None
                        else Vector((0.0, 0.0, 0.0))
                    )
                    rv3d.view_perspective = "ORTHO"
                    rv3d.view_rotation = Quaternion((0.7071067811865476, -0.7071067811865476, 0.0, 0.0))
                    rv3d.view_distance = max(_dicom_volume_extent_mm() * 0.62, 1.0)
                    rv3d.update()
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        area.tag_redraw()


def restore_clinical_preview_view(context: bpy.types.Context) -> None:
    screen = getattr(context, "screen", None)
    if screen is None:
        RUNTIME.clinical_view_state.clear()
        return
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        state = RUNTIME.clinical_view_state.get(int(area.as_pointer()))
        if not state:
            continue
        space = area.spaces.active
        try:
            space.overlay.show_overlays = bool(state["show_overlays"])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            space.show_gizmo = bool(state["show_gizmo"])
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        shading = getattr(space, "shading", None)
        if shading is not None:
            for attr in ("type", "background_type", "background_color", "show_cavity", "cavity_type"):
                try:
                    setattr(shading, attr, state[attr if attr != "type" else "shading_type"])
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        area.tag_redraw()
    RUNTIME.clinical_view_state.clear()


def _segmentation_vdb_path(structure: str) -> Path:
    directory = Path(bpy.app.tempdir or tempfile.gettempdir()) / "dicom_wizard_pro_921"
    directory.mkdir(parents=True, exist_ok=True)
    digest_source = (
        f"{RUNTIME.source_path}|{structure}|{RUNTIME.dims_zyx}|"
        f"{RUNTIME.spacing_zyx_mm}|{time.time_ns()}"
    )
    digest = hashlib.sha1(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:18]
    return directory / f"segmentation_{structure.lower()}_{digest}.vdb"


def _write_binary_mask_vdb(mask, filepath: Path) -> None:
    np = load_numpy()
    vdb = load_openvdb()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if vdb is None:
        raise RuntimeError("Blender no expone OpenVDB; usa la versión oficial de Blender 5.1")

    # pydicom/NumPy masks are [z,y,x], while OpenVDB arrays are [x,y,z].
    values_xyz = np.ascontiguousarray(mask.transpose(2, 1, 0), dtype=np.float32)
    grid = vdb.FloatGrid()
    grid.name = "density"
    try:
        grid.gridClass = vdb.GridClass.FOG_VOLUME
    except Exception:
        try:
            grid.gridClass = "fog volume"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    grid.copyFromArray(values_xyz, tolerance=0.0)
    try:
        grid.prune(tolerance=0.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        grid.transform = vdb.createLinearTransform(voxelSize=1.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    vdb.write(str(filepath), grids=[grid])


def _evaluated_mesh_from_object(context, obj: bpy.types.Object) -> bpy.types.Mesh:
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    try:
        return bpy.data.meshes.new_from_object(
            evaluated,
            preserve_all_data_layers=False,
            depsgraph=depsgraph,
        )
    except TypeError:
        return bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)


def _normalized_density_threshold(value: float) -> float:
    denominator = max(float(RUNTIME.density_max - RUNTIME.density_min), 1e-6)
    return clamp(
        (float(value) - float(RUNTIME.density_min)) / denominator,
        0.0,
        1.0,
    )


def _sample_density_for_surface(max_axis: int, *, precise: bool = False):
    """Return density samples and their exact original voxel indices.

    ``precise=False`` keeps the fast regular sub-sampling used by the optional
    solid preview. ``precise=True`` performs an interpolated resample so the STL
    follows the radiographic threshold more faithfully, especially at 384 px.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")

    z_count, y_count, x_count = RUNTIME.dims_zyx
    max_axis = max(32, int(max_axis))

    if precise:
        ndimage = load_scipy_ndimage()
        if ndimage is not None:
            max_dim = max(z_count, y_count, x_count)
            scale = min(1.0, float(max_axis) / float(max_dim))
            target_shape = (
                max(32, int(round(z_count * scale))),
                max(32, int(round(y_count * scale))),
                max(32, int(round(x_count * scale))),
            )
            try:
                density = RUNTIME.volume.astype(np.float32, copy=False)
                density = density * RUNTIME.slopes[:, None, None] + RUNTIME.intercepts[:, None, None]
                if target_shape != (z_count, y_count, x_count):
                    zoom_factors = (
                        target_shape[0] / float(z_count),
                        target_shape[1] / float(y_count),
                        target_shape[2] / float(x_count),
                    )
                    values = ndimage.zoom(density, zoom_factors, order=1, mode="nearest", prefilter=False)
                else:
                    values = np.array(density, copy=False)
                z_indices = np.linspace(0.0, float(z_count - 1), int(values.shape[0]), dtype=np.float64)
                y_indices = np.linspace(0.0, float(y_count - 1), int(values.shape[1]), dtype=np.float64)
                x_indices = np.linspace(0.0, float(x_count - 1), int(values.shape[2]), dtype=np.float64)
                approx_stride = max(1, int(round(float(max_dim) / float(max(values.shape)))))
                return np.asarray(values, dtype=np.float32), z_indices, y_indices, x_indices, approx_stride
            except Exception as exc:
                print("DICOM precise resample fallback:", repr(exc))

    stride = max(
        1,
        int(math.ceil(max(z_count, y_count, x_count) / float(max_axis))),
    )
    z_indices = _preview_axis_indices(z_count, stride)
    y_indices = _preview_axis_indices(y_count, stride)
    x_indices = _preview_axis_indices(x_count, stride)
    raw = RUNTIME.volume[np.ix_(z_indices, y_indices, x_indices)]
    values = raw.astype(np.float32, copy=False)
    values = values * RUNTIME.slopes[z_indices.astype(np.int32), None, None] + RUNTIME.intercepts[z_indices.astype(np.int32), None, None]
    return values, z_indices, y_indices, x_indices, stride


def _refine_density_for_surface(values_zyx, threshold_density: float):
    """Reduce staircase artefacts without drifting far from the selected threshold."""
    np = load_numpy()
    ndimage = load_scipy_ndimage()
    values = np.asarray(values_zyx, dtype=np.float32) if np is not None else values_zyx
    if np is None or ndimage is None or values.size == 0:
        return values
    try:
        sigma = 0.45 if max(values.shape) >= 320 else 0.35
        blurred = ndimage.gaussian_filter(values, sigma=sigma, mode="nearest")
        # Blend only part of the blur so the STL stays faithful to the selected level.
        refined = values * 0.62 + blurred * 0.38
        # Preserve the global threshold neighbourhood to avoid visible drift.
        refined += (float(threshold_density) - float(np.median(refined))) * 0.0
        return np.asarray(refined, dtype=np.float32)
    except Exception as exc:
        print("DICOM surface refine fallback:", repr(exc))
        return values


def _extract_triplanar_contour_clouds(
    values_zyx,
    level: float,
    z_indices,
    y_indices,
    x_indices,
    structure: str,
):
    """Extract hidden subpixel contour constraints from all useful MPR slices.

    Marching squares runs only when the user confirms STL creation. Long noisy
    loops are sampled conservatively and capped so the operation remains usable
    on ordinary dental workstations.
    """
    np = load_numpy()
    measure = load_skimage_measure()
    if np is None or measure is None:
        return {}

    values = np.asarray(values_zyx, dtype=np.float32)
    finite = np.isfinite(values)
    inside = finite & (values >= float(level))
    if not bool(inside.any()):
        return {}

    bbox = _occupied_bbox_3d(inside, margin=1)
    if bbox is None:
        return {}
    minimum, maximum = bbox
    crop = values[
        int(minimum[0]):int(maximum[0]),
        int(minimum[1]):int(maximum[1]),
        int(minimum[2]):int(maximum[2]),
    ]
    finite_crop = crop[np.isfinite(crop)]
    if finite_crop.size == 0:
        return {}
    outside = min(float(finite_crop.min()), float(level) - 1e-3)
    clean = np.where(np.isfinite(crop), crop, outside).astype(np.float32, copy=False)

    structure = str(structure).upper()
    max_loops_per_slice = 24 if structure == "TEETH" else 12
    min_points_per_loop = 7 if structure == "TEETH" else 10
    max_points_per_loop = 384
    max_points_per_orientation = 280000 if structure == "TEETH" else 220000

    clouds_sample_zyx = {"AXIAL": [], "CORONAL": [], "SAGITTAL": []}

    def add_contours(orientation: str, fixed_index: int, image_2d) -> None:
        local_min = float(np.min(image_2d))
        local_max = float(np.max(image_2d))
        if not (local_min <= float(level) <= local_max):
            return
        try:
            contours = measure.find_contours(
                image_2d,
                level=float(level),
                fully_connected="high",
                positive_orientation="low",
            )
        except TypeError:
            contours = measure.find_contours(image_2d, level=float(level))
        if not contours:
            return
        contours = sorted(contours, key=lambda item: int(item.shape[0]), reverse=True)
        kept = 0
        for contour in contours:
            count = int(contour.shape[0])
            if count < min_points_per_loop:
                continue
            step = max(1, int(math.ceil(count / float(max_points_per_loop))))
            points = np.asarray(contour[::step], dtype=np.float64)
            if points.shape[0] < 2:
                continue
            fixed = float(fixed_index)
            if orientation == "AXIAL":
                z = np.full(points.shape[0], fixed, dtype=np.float64)
                y = points[:, 0]
                x = points[:, 1]
            elif orientation == "CORONAL":
                z = points[:, 0]
                y = np.full(points.shape[0], fixed, dtype=np.float64)
                x = points[:, 1]
            else:
                z = points[:, 0]
                y = points[:, 1]
                x = np.full(points.shape[0], fixed, dtype=np.float64)
            clouds_sample_zyx[orientation].append(np.column_stack((z, y, x)))
            kept += 1
            if kept >= max_loops_per_slice:
                break

    for z in range(clean.shape[0]):
        add_contours("AXIAL", z, clean[z, :, :])
    for y in range(clean.shape[1]):
        add_contours("CORONAL", y, clean[:, y, :])
    for x in range(clean.shape[2]):
        add_contours("SAGITTAL", x, clean[:, :, x])

    result = {}
    offset = minimum.astype(np.float64)
    for orientation, chunks in clouds_sample_zyx.items():
        if not chunks:
            continue
        points_zyx = np.concatenate(chunks, axis=0)
        if points_zyx.shape[0] > max_points_per_orientation:
            choose = np.linspace(
                0,
                points_zyx.shape[0] - 1,
                max_points_per_orientation,
                dtype=np.int64,
            )
            points_zyx = points_zyx[choose]
        points_zyx += offset[None, :]
        result[orientation] = _centered_xyz_from_sample_vertices(
            points_zyx,
            z_indices,
            y_indices,
            x_indices,
        ).astype(np.float32, copy=False)
    return result


def _mesh_vertex_normals_numpy(vertices_xyz, faces):
    np = load_numpy()
    vertices = np.asarray(vertices_xyz, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    normals = np.zeros_like(vertices, dtype=np.float64)
    chunk_size = 200000
    for start in range(0, triangles.shape[0], chunk_size):
        tri = triangles[start:start + chunk_size]
        a = vertices[tri[:, 0]]
        b = vertices[tri[:, 1]]
        c = vertices[tri[:, 2]]
        face_normals = np.cross(b - a, c - a)
        np.add.at(normals, tri[:, 0], face_normals)
        np.add.at(normals, tri[:, 1], face_normals)
        np.add.at(normals, tri[:, 2], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    return normals


def _sample_axis_spacing_mm(source_indices, physical_spacing_mm: float) -> float:
    np = load_numpy()
    indices = np.asarray(source_indices, dtype=np.float64)
    if indices.size <= 1:
        return float(physical_spacing_mm)
    differences = np.diff(indices)
    differences = differences[differences > 1e-9]
    if differences.size == 0:
        return float(physical_spacing_mm)
    return float(np.median(differences)) * float(physical_spacing_mm)


def _vertices_xyz_to_sample_coordinates(vertices_xyz, z_indices, y_indices, x_indices):
    """Convert root-local millimetres to fractional sampled-grid coordinates."""
    np = load_numpy()
    vertices = np.asarray(vertices_xyz, dtype=np.float64)
    full_z, full_y, full_x = RUNTIME.dims_zyx
    spacing_z, spacing_y, spacing_x = (float(v) for v in RUNTIME.spacing_zyx_mm)
    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    voxel_x = sign_x * vertices[:, 0] / max(spacing_x, 1e-9) + 0.5 * float(full_x - 1)
    voxel_y = sign_y * vertices[:, 1] / max(spacing_y, 1e-9) + 0.5 * float(full_y - 1)
    voxel_z = sign_z * vertices[:, 2] / max(spacing_z, 1e-9) + 0.5 * float(full_z - 1)
    sx = np.interp(voxel_x, np.asarray(x_indices, dtype=np.float64), np.arange(len(x_indices), dtype=np.float64))
    sy = np.interp(voxel_y, np.asarray(y_indices, dtype=np.float64), np.arange(len(y_indices), dtype=np.float64))
    sz = np.interp(voxel_z, np.asarray(z_indices, dtype=np.float64), np.arange(len(z_indices), dtype=np.float64))
    return np.column_stack((sz, sy, sx))


def _project_vertices_to_threshold_field(
    vertices_xyz,
    values_zyx,
    level: float,
    z_indices,
    y_indices,
    x_indices,
    *,
    iterations: int = 2,
):
    """Project vertices onto the trilinearly interpolated CBCT threshold field.

    Marching Cubes supplies only stable topology. Final vertex positions are
    corrected against the continuous scalar field, which is closer to the
    radiographic data than post-hoc mesh smoothing.
    """
    np = load_numpy()
    ndimage = load_scipy_ndimage()
    if np is None or ndimage is None:
        return vertices_xyz, {"projected": 0, "iterations": 0}
    values = np.asarray(values_zyx, dtype=np.float32)
    vertices = np.asarray(vertices_xyz, dtype=np.float64).copy()
    if vertices.size == 0 or values.size == 0:
        return vertices_xyz, {"projected": 0, "iterations": 0}

    spacing_z = _sample_axis_spacing_mm(z_indices, RUNTIME.spacing_zyx_mm[0])
    spacing_y = _sample_axis_spacing_mm(y_indices, RUNTIME.spacing_zyx_mm[1])
    spacing_x = _sample_axis_spacing_mm(x_indices, RUNTIME.spacing_zyx_mm[2])
    voxel_diag = math.sqrt(spacing_x ** 2 + spacing_y ** 2 + spacing_z ** 2)
    max_step = max(0.32 * voxel_diag, 0.05 * min(spacing_x, spacing_y, spacing_z))
    h = 0.50
    moved_total = 0
    chunk_size = 80000

    for _iteration in range(max(1, int(iterations))):
        moved_this_iteration = 0
        for start in range(0, len(vertices), chunk_size):
            end = min(len(vertices), start + chunk_size)
            local = vertices[start:end]
            coords = _vertices_xyz_to_sample_coordinates(local, z_indices, y_indices, x_indices)
            zc, yc, xc = coords[:, 0], coords[:, 1], coords[:, 2]
            valid = (
                (zc >= 0.5) & (zc <= values.shape[0] - 1.5)
                & (yc >= 0.5) & (yc <= values.shape[1] - 1.5)
                & (xc >= 0.5) & (xc <= values.shape[2] - 1.5)
            )
            if not bool(valid.any()):
                continue
            q = np.vstack((zc, yc, xc))
            intensity = ndimage.map_coordinates(values, q, order=1, mode="nearest", prefilter=False)
            qzp = q.copy(); qzp[0] += h
            qzm = q.copy(); qzm[0] -= h
            qyp = q.copy(); qyp[1] += h
            qym = q.copy(); qym[1] -= h
            qxp = q.copy(); qxp[2] += h
            qxm = q.copy(); qxm[2] -= h
            gz = (ndimage.map_coordinates(values, qzp, order=1, mode="nearest", prefilter=False)
                  - ndimage.map_coordinates(values, qzm, order=1, mode="nearest", prefilter=False)) / (2.0 * h * max(spacing_z, 1e-9))
            gy = (ndimage.map_coordinates(values, qyp, order=1, mode="nearest", prefilter=False)
                  - ndimage.map_coordinates(values, qym, order=1, mode="nearest", prefilter=False)) / (2.0 * h * max(spacing_y, 1e-9))
            gx = (ndimage.map_coordinates(values, qxp, order=1, mode="nearest", prefilter=False)
                  - ndimage.map_coordinates(values, qxm, order=1, mode="nearest", prefilter=False)) / (2.0 * h * max(spacing_x, 1e-9))
            gradient = np.column_stack((gx, gy, gz))
            norm_sq = np.einsum("ij,ij->i", gradient, gradient)
            reliable = valid & np.isfinite(intensity) & np.isfinite(norm_sq) & (norm_sq > 1e-8)
            if not bool(reliable.any()):
                continue
            step = np.zeros_like(gradient)
            scale = np.zeros(len(local), dtype=np.float64)
            scale[reliable] = -(intensity[reliable] - float(level)) / norm_sq[reliable]
            step[reliable] = gradient[reliable] * scale[reliable, None]
            lengths = np.linalg.norm(step, axis=1)
            too_far = lengths > max_step
            step[too_far] *= (max_step / np.maximum(lengths[too_far], 1e-12))[:, None]
            move = reliable & (np.linalg.norm(step, axis=1) > 1e-5)
            local[move] += step[move]
            vertices[start:end] = local
            moved_this_iteration += int(move.sum())
        moved_total += moved_this_iteration
        if moved_this_iteration == 0:
            break
    return vertices.astype(np.float32), {"projected": moved_total, "iterations": max(1, int(iterations))}


def _taubin_smooth_vertices(vertices_xyz, faces, *, lam: float = 0.10, mu: float = -0.105):
    """One low-shrinkage smoothing cycle used only before final reprojection."""
    np = load_numpy()
    if np is None:
        return vertices_xyz
    vertices = np.asarray(vertices_xyz, dtype=np.float64).copy()
    triangles = np.asarray(faces, dtype=np.int64)
    if len(vertices) == 0 or len(triangles) == 0:
        return vertices_xyz

    def laplacian(current):
        sums = np.zeros_like(current)
        counts = np.zeros(len(current), dtype=np.float64)
        chunk = 180000
        for start in range(0, len(triangles), chunk):
            tri = triangles[start:start + chunk]
            for a, b in ((0, 1), (1, 2), (2, 0), (1, 0), (2, 1), (0, 2)):
                np.add.at(sums, tri[:, a], current[tri[:, b]])
                np.add.at(counts, tri[:, a], 1.0)
        average = np.divide(sums, counts[:, None], out=current.copy(), where=counts[:, None] > 0.0)
        return average - current

    vertices += float(lam) * laplacian(vertices)
    vertices += float(mu) * laplacian(vertices)
    return vertices.astype(np.float32)


def _refine_vertices_with_triplanar_contours(
    vertices_xyz,
    faces,
    contour_clouds,
    z_indices,
    y_indices,
    x_indices,
):
    """Move vertices only along their normals toward agreeing MPR contours."""
    np = load_numpy()
    spatial = load_scipy_spatial()
    if np is None or spatial is None or not contour_clouds:
        return vertices_xyz, {"moved": 0, "constraints": 0}

    vertices = np.asarray(vertices_xyz, dtype=np.float64)
    if vertices.shape[0] == 0:
        return vertices_xyz, {"moved": 0, "constraints": 0}
    normals = _mesh_vertex_normals_numpy(vertices, faces)

    spacing_z = _sample_axis_spacing_mm(z_indices, RUNTIME.spacing_zyx_mm[0])
    spacing_y = _sample_axis_spacing_mm(y_indices, RUNTIME.spacing_zyx_mm[1])
    spacing_x = _sample_axis_spacing_mm(x_indices, RUNTIME.spacing_zyx_mm[2])
    voxel_diagonal = math.sqrt(spacing_z ** 2 + spacing_y ** 2 + spacing_x ** 2)
    minimum_spacing = max(min(spacing_z, spacing_y, spacing_x), 1e-6)
    max_distance = max(1.65 * voxel_diagonal, 1.5 * minimum_spacing)
    max_tangent = max(1.10 * voxel_diagonal, minimum_spacing)
    max_normal_shift = max(0.45 * voxel_diagonal, 0.35 * minimum_spacing)
    agreement_tolerance = max(0.65 * voxel_diagonal, 0.5 * minimum_spacing)

    trees = []
    point_sets = []
    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        points = contour_clouds.get(orientation)
        if points is None or len(points) < 3:
            continue
        points = np.asarray(points, dtype=np.float64)
        try:
            trees.append(spatial.cKDTree(points, compact_nodes=True, balanced_tree=True))
            point_sets.append(points)
        except Exception:
            continue
    if not trees:
        return vertices_xyz, {"moved": 0, "constraints": 0}

    refined = vertices.copy()
    moved_total = 0
    accepted_total = 0
    chunk_size = 75000
    epsilon = max(0.05 * minimum_spacing, 1e-6)

    for start in range(0, vertices.shape[0], chunk_size):
        end = min(vertices.shape[0], start + chunk_size)
        points = vertices[start:end]
        local_normals = normals[start:end]
        shifts = []
        weights = []
        valid_masks = []
        for tree, cloud in zip(trees, point_sets):
            try:
                distances, nearest = tree.query(points, k=1, workers=-1)
            except TypeError:
                distances, nearest = tree.query(points, k=1)
            target = cloud[np.asarray(nearest, dtype=np.int64)]
            delta = target - points
            normal_shift = np.einsum("ij,ij->i", delta, local_normals)
            tangent_sq = np.maximum(np.asarray(distances) ** 2 - normal_shift ** 2, 0.0)
            tangent = np.sqrt(tangent_sq)
            valid = (
                np.isfinite(distances)
                & (distances <= max_distance)
                & (tangent <= max_tangent)
                & (np.abs(normal_shift) <= max_normal_shift * 1.75)
            )
            shifts.append(normal_shift)
            weights.append(1.0 / (np.asarray(distances) + epsilon))
            valid_masks.append(valid)

        shift_matrix = np.vstack(shifts)
        weight_matrix = np.vstack(weights)
        valid_matrix = np.vstack(valid_masks)
        valid_count = valid_matrix.sum(axis=0)
        masked_weights = np.where(valid_matrix, weight_matrix, 0.0)
        weight_sum = masked_weights.sum(axis=0)
        weighted_shift = np.divide(
            (shift_matrix * masked_weights).sum(axis=0),
            weight_sum,
            out=np.zeros(end - start, dtype=np.float64),
            where=weight_sum > 0.0,
        )
        minimum_shift = np.min(np.where(valid_matrix, shift_matrix, np.inf), axis=0)
        maximum_shift = np.max(np.where(valid_matrix, shift_matrix, -np.inf), axis=0)
        spread = maximum_shift - minimum_shift

        strong = (valid_count >= 2) & (spread <= agreement_tolerance)
        weak = valid_count == 1
        final_shift = np.zeros(end - start, dtype=np.float64)
        final_shift[strong] = weighted_shift[strong]
        final_shift[weak] = 0.20 * weighted_shift[weak]
        final_shift = np.clip(final_shift, -max_normal_shift, max_normal_shift)
        move_mask = np.abs(final_shift) > max(0.01 * minimum_spacing, 1e-5)
        refined[start:end] += local_normals * final_shift[:, None]
        moved_total += int(move_mask.sum())
        accepted_total += int(valid_count.sum())

    return refined.astype(np.float32), {
        "moved": moved_total,
        "constraints": accepted_total,
        "contour_points": int(sum(len(points) for points in point_sets)),
    }


def _interpolate_sample_coordinates(sample_coordinates, source_indices):
    """Map fractional sampled-grid coordinates to original voxel indices."""
    np = load_numpy()
    source_indices = np.asarray(source_indices, dtype=np.float64)
    sample_coordinates = np.asarray(sample_coordinates, dtype=np.float64)

    if source_indices.size <= 1:
        return np.zeros_like(sample_coordinates, dtype=np.float64)

    return np.interp(
        sample_coordinates,
        np.arange(source_indices.size, dtype=np.float64),
        source_indices,
    )


def _centered_xyz_from_sample_vertices(
    vertices_zyx,
    z_indices,
    y_indices,
    x_indices,
):
    """Convert marching-cubes (z,y,x) vertices into MPR-local (x,y,z) mm."""
    np = load_numpy()
    vertices_zyx = np.asarray(vertices_zyx, dtype=np.float64)

    voxel_z = _interpolate_sample_coordinates(vertices_zyx[:, 0], z_indices)
    voxel_y = _interpolate_sample_coordinates(vertices_zyx[:, 1], y_indices)
    voxel_x = _interpolate_sample_coordinates(vertices_zyx[:, 2], x_indices)

    full_z, full_y, full_x = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = (
        float(value) for value in RUNTIME.spacing_zyx_mm
    )

    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    vertices_xyz = np.empty((vertices_zyx.shape[0], 3), dtype=np.float32)
    vertices_xyz[:, 0] = sign_x * (
        voxel_x - 0.5 * float(full_x - 1)
    ) * x_spacing
    vertices_xyz[:, 1] = sign_y * (
        voxel_y - 0.5 * float(full_y - 1)
    ) * y_spacing
    vertices_xyz[:, 2] = sign_z * (
        voxel_z - 0.5 * float(full_z - 1)
    ) * z_spacing
    return vertices_xyz


def _marching_cubes_cropped(
    values_zyx,
    level: float,
    z_indices,
    y_indices,
    x_indices,
):
    """Extract the occupied region and return centered XYZ vertices."""
    np = load_numpy()
    measure = load_skimage_measure()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if measure is None:
        raise RuntimeError(
            "Falta el motor STL. Pulsa «Instalar motor STL» y reinicia Blender."
        )

    values = np.asarray(values_zyx, dtype=np.float32)
    finite = np.isfinite(values)
    inside = finite & (values >= float(level))
    if not bool(inside.any()):
        raise RuntimeError("El umbral no contiene ningún voxel")

    bbox = _occupied_bbox_3d(inside, margin=1)
    if bbox is None:
        raise RuntimeError("El umbral no contiene ningún voxel")
    minimum, maximum = bbox
    crop_slices = tuple(
        slice(int(minimum[axis]), int(maximum[axis]))
        for axis in range(3)
    )
    crop = values[crop_slices]

    finite_crop = crop[np.isfinite(crop)]
    if finite_crop.size == 0:
        raise RuntimeError("La región seleccionada no contiene valores válidos")

    epsilon = max(
        1e-3,
        abs(float(level)) * 1e-5,
        float(np.ptp(finite_crop)) * 1e-5,
    )
    outside_value = min(float(finite_crop.min()), float(level) - epsilon)
    padded = np.pad(
        crop,
        1,
        mode="constant",
        constant_values=outside_value,
    )

    vertices, faces, _normals, _surface_values = measure.marching_cubes(
        padded,
        level=float(level),
        step_size=1,
        allow_degenerate=False,
        method="lewiner",
    )

    vertices[:, 0] += float(minimum[0]) - 1.0
    vertices[:, 1] += float(minimum[1]) - 1.0
    vertices[:, 2] += float(minimum[2]) - 1.0

    vertices_xyz = _centered_xyz_from_sample_vertices(
        vertices,
        z_indices,
        y_indices,
        x_indices,
    )
    return vertices_xyz, np.asarray(faces, dtype=np.int32)



# High-definition final DICOM surface engine. The preview remains lightweight,
# while the confirmed STL is extracted from the native voxel grid in overlapping
# slabs. This avoids the former 384 px bottleneck without allocating a complete
# float32 copy of a large CBCT volume.
DICOM_HD_BBOX_AXIS = 192
DICOM_HD_MARGIN_MM = 3.0
DICOM_HD_TARGET_SLAB_VOXELS = 22_000_000
DICOM_HD_MIN_SLAB_DEPTH = 24
DICOM_HD_MAX_SLAB_DEPTH = 96
DICOM_HD_OVERLAP_SLICES = 3
DICOM_HD_VERTEX_WELD_TOLERANCE_VOX = 1.0e-4


def _threshold_bbox_native(level: float, *, preview_axis: int = DICOM_HD_BBOX_AXIS):
    """Locate thresholded anatomy cheaply, then return native inclusive/exclusive bounds."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    sampled, z_indices, y_indices, x_indices, _stride = _sample_density_for_surface(
        int(preview_axis), precise=False
    )
    finite = np.isfinite(sampled)
    inside = finite & (sampled >= float(level))
    if not bool(inside.any()):
        raise RuntimeError("El umbral no contiene anatomía visible")

    z_used = np.flatnonzero(np.any(inside, axis=(1, 2)))
    y_used = np.flatnonzero(np.any(inside, axis=(0, 2)))
    x_used = np.flatnonzero(np.any(inside, axis=(0, 1)))
    if not (z_used.size and y_used.size and x_used.size):
        raise RuntimeError("No se pudo localizar la anatomía del STL")

    spacing_z, spacing_y, spacing_x = (float(v) for v in RUNTIME.spacing_zyx_mm)
    margins = (
        max(2, int(math.ceil(DICOM_HD_MARGIN_MM / max(spacing_z, 1e-6)))),
        max(2, int(math.ceil(DICOM_HD_MARGIN_MM / max(spacing_y, 1e-6)))),
        max(2, int(math.ceil(DICOM_HD_MARGIN_MM / max(spacing_x, 1e-6)))),
    )
    full_shape = tuple(int(v) for v in RUNTIME.dims_zyx)
    sampled_axes = (z_indices, y_indices, x_indices)
    used_axes = (z_used, y_used, x_used)
    bounds = []
    for axis, (indices, used, margin, full_count) in enumerate(
        zip(sampled_axes, used_axes, margins, full_shape)
    ):
        lo = int(math.floor(float(indices[int(used[0])]))) - int(margin)
        hi = int(math.ceil(float(indices[int(used[-1])]))) + int(margin) + 1
        bounds.append((max(0, lo), min(int(full_count), hi)))
    return tuple(bounds)


def _density_native_slab(z0: int, z1: int, y0: int, y1: int, x0: int, x1: int):
    """Read and rescale only one native CBCT slab into float32."""
    np = load_numpy()
    raw = RUNTIME.volume[int(z0):int(z1), int(y0):int(y1), int(x0):int(x1)]
    values = np.asarray(raw, dtype=np.float32)
    z_slice = slice(int(z0), int(z1))
    values = values * np.asarray(RUNTIME.slopes[z_slice], dtype=np.float32)[:, None, None]
    values += np.asarray(RUNTIME.intercepts[z_slice], dtype=np.float32)[:, None, None]
    return np.ascontiguousarray(values, dtype=np.float32)


# v9.2.64 — native full-resolution scalar cache + exact threshold hierarchy.
_NATIVE_THRESHOLD_CACHE_LOCK = threading.RLock()


def _native_threshold_cache_key() -> str:
    """Cheap identity for the currently loaded immutable DICOM volume."""
    try:
        ptr = int(RUNTIME.volume.__array_interface__["data"][0])
    except Exception:
        ptr = id(RUNTIME.volume)
    return "|".join((
        str(RUNTIME.source_path or ""),
        repr(tuple(int(v) for v in RUNTIME.dims_zyx)),
        str(getattr(RUNTIME.volume, "dtype", "")),
        str(ptr),
    ))


def _load_torch_for_surface_acceleration():
    """Reuse DSG's selected AI runtime without making Torch mandatory."""
    try:
        from . import cbct_ai_runtime
        cbct_ai_runtime._prepend_runtime_paths()
        import importlib
        importlib.invalidate_caches()
        import torch
        return torch
    except Exception:
        return None


def _native_density_fullres_cached():
    """Return one calibrated float32 native CBCT volume, cached by source.

    This intentionally spends RAM to save repeated per-slab rescale/copy work.
    No resampling, smoothing or quantisation is performed.
    """
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")
    key = _native_threshold_cache_key()
    with _NATIVE_THRESHOLD_CACHE_LOCK:
        cached = RUNTIME.native_density_fullres
        if (
            cached is not None
            and str(RUNTIME.native_density_cache_key or "") == key
            and tuple(int(v) for v in getattr(cached, "shape", ())) == tuple(int(v) for v in RUNTIME.dims_zyx)
        ):
            return cached

    z, y, x = (int(v) for v in RUNTIME.dims_zyx)
    values = _density_native_slab(0, z, 0, y, 0, x)
    with _NATIVE_THRESHOLD_CACHE_LOCK:
        if key == _native_threshold_cache_key():
            RUNTIME.native_density_fullres = values
            RUNTIME.native_density_cache_key = key
            RUNTIME.native_threshold_index = None
            RUNTIME.native_threshold_index_key = ""
    return values


def _native_threshold_index_cached(*, prefer_cuda: bool = True):
    """Build/reuse exact block min/max hierarchy on the native scalar grid."""
    from . import cbct_native_threshold
    values = _native_density_fullres_cached()
    key = _native_threshold_cache_key() + "|B16|P4"
    with _NATIVE_THRESHOLD_CACHE_LOCK:
        cached = RUNTIME.native_threshold_index
        cached_ok = (cached is not None and str(RUNTIME.native_threshold_index_key or "") == key)
    if cached_ok:
        if not prefer_cuda or bool(getattr(cached, "gpu_enabled", False)):
            return cached
        # Upgrade the already-warm CPU hierarchy to CUDA only when a CUDA Torch
        # runtime is genuinely available. This avoids importing Torch from the
        # DICOM-loader warmup thread and the DLL races that older DSG builds saw.
        torch_probe = _load_torch_for_surface_acceleration()
        try:
            if torch_probe is None or not bool(torch_probe.cuda.is_available()):
                return cached
        except Exception:
            return cached
    torch_module = _load_torch_for_surface_acceleration() if prefer_cuda else None
    index = cbct_native_threshold.build_threshold_index(
        values, block_size=16, parent_factor=4,
        torch_module=torch_module, prefer_cuda=bool(prefer_cuda),
    )
    with _NATIVE_THRESHOLD_CACHE_LOCK:
        if key.startswith(_native_threshold_cache_key()):
            RUNTIME.native_threshold_index = index
            RUNTIME.native_threshold_index_key = key
    return index


def _warm_native_threshold_engine_async() -> None:
    """Warm the native scalar/index cache while the clinician reviews the CBCT.

    The warmup never touches bpy datablocks and never changes geometry. If it
    fails, generation remains fully functional through the synchronous path.
    """
    if not RUNTIME.is_loaded():
        return
    with _NATIVE_THRESHOLD_CACHE_LOCK:
        if bool(RUNTIME.native_threshold_warmup_running):
            return
        key = _native_threshold_cache_key()
        if (
            RUNTIME.native_threshold_index is not None
            and str(RUNTIME.native_threshold_index_key or "").startswith(key)
        ):
            return
        RUNTIME.native_threshold_warmup_running = True
        RUNTIME.native_threshold_warmup_error = ""

    def _worker():
        started = time.perf_counter()
        error = ""
        try:
            _native_threshold_index_cached(prefer_cuda=False)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed = float(time.perf_counter() - started)
        with _NATIVE_THRESHOLD_CACHE_LOCK:
            # A new DICOM may have been loaded while the old cache was warming.
            if key == _native_threshold_cache_key():
                RUNTIME.native_threshold_warmup_s = elapsed
                RUNTIME.native_threshold_warmup_error = error
            RUNTIME.native_threshold_warmup_running = False

    threading.Thread(
        target=_worker, name="DSG-NativeThresholdWarmup", daemon=True
    ).start()


def _refine_native_slab(values, structure: str):
    """Apply a very small physical-space blur to suppress voxel stairs, not anatomy."""
    np = load_numpy()
    ndimage = load_scipy_ndimage()
    if np is None or ndimage is None or values.size == 0:
        return values
    sigma_mm = 0.12 if str(structure).upper() == "TEETH" else 0.16
    spacing = tuple(max(float(v), 1e-6) for v in RUNTIME.spacing_zyx_mm)
    sigma = tuple(min(0.80, max(0.25, sigma_mm / value)) for value in spacing)
    try:
        blurred = ndimage.gaussian_filter(
            values, sigma=sigma, mode="nearest", truncate=2.0
        )
        # Preserve radiographic edges while suppressing single-voxel terracing.
        values *= 0.72
        values += blurred * 0.28
        return np.asarray(values, dtype=np.float32)
    except Exception as exc:
        print("DICOM HD slab smoothing fallback:", repr(exc))
        return values


def _global_voxel_to_centered_xyz(vertices_zyx):
    """Convert native global voxel ZYX coordinates to root-local XYZ millimetres."""
    np = load_numpy()
    vertices = np.asarray(vertices_zyx, dtype=np.float64)
    full_z, full_y, full_x = (int(v) for v in RUNTIME.dims_zyx)
    spacing_z, spacing_y, spacing_x = (float(v) for v in RUNTIME.spacing_zyx_mm)
    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    result = np.empty((vertices.shape[0], 3), dtype=np.float32)
    result[:, 0] = sign_x * (vertices[:, 2] - 0.5 * float(full_x - 1)) * spacing_x
    result[:, 1] = sign_y * (vertices[:, 1] - 0.5 * float(full_y - 1)) * spacing_y
    result[:, 2] = sign_z * (vertices[:, 0] - 0.5 * float(full_z - 1)) * spacing_z
    return result


def _centered_xyz_to_global_voxel(vertices_xyz):
    np = load_numpy()
    vertices = np.asarray(vertices_xyz, dtype=np.float64)
    full_z, full_y, full_x = (int(v) for v in RUNTIME.dims_zyx)
    spacing_z, spacing_y, spacing_x = (float(v) for v in RUNTIME.spacing_zyx_mm)
    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    result = np.empty((vertices.shape[0], 3), dtype=np.float64)
    result[:, 2] = sign_x * vertices[:, 0] / max(spacing_x, 1e-9) + 0.5 * float(full_x - 1)
    result[:, 1] = sign_y * vertices[:, 1] / max(spacing_y, 1e-9) + 0.5 * float(full_y - 1)
    result[:, 0] = sign_z * vertices[:, 2] / max(spacing_z, 1e-9) + 0.5 * float(full_z - 1)
    return result


def _runtime_density_at_voxel_coordinates(coords_zyx):
    """Trilinearly sample calibrated DICOM density without copying the volume."""
    np = load_numpy()
    ndimage = load_scipy_ndimage()
    if np is None or ndimage is None:
        return None
    coords = np.asarray(coords_zyx, dtype=np.float64)
    q = np.vstack((coords[:, 0], coords[:, 1], coords[:, 2]))
    raw = ndimage.map_coordinates(
        RUNTIME.volume, q, order=1, mode="nearest", prefilter=False
    ).astype(np.float64, copy=False)
    z = np.clip(coords[:, 0], 0.0, float(len(RUNTIME.slopes) - 1))
    base = np.floor(z).astype(np.int64)
    upper = np.minimum(base + 1, len(RUNTIME.slopes) - 1)
    fraction = z - base
    slopes = (1.0 - fraction) * np.asarray(RUNTIME.slopes)[base] + fraction * np.asarray(RUNTIME.slopes)[upper]
    intercepts = (1.0 - fraction) * np.asarray(RUNTIME.intercepts)[base] + fraction * np.asarray(RUNTIME.intercepts)[upper]
    return raw * slopes + intercepts


def _project_vertices_to_native_threshold(vertices_xyz, level: float, *, iterations: int = 1):
    """Reproject a smoothed HD mesh to the original native DICOM threshold."""
    np = load_numpy()
    if np is None or load_scipy_ndimage() is None:
        return vertices_xyz, {"projected": 0, "iterations": 0}
    vertices = np.asarray(vertices_xyz, dtype=np.float64).copy()
    if vertices.size == 0:
        return vertices_xyz, {"projected": 0, "iterations": 0}
    spacing_z, spacing_y, spacing_x = (float(v) for v in RUNTIME.spacing_zyx_mm)
    voxel_diag = math.sqrt(spacing_x ** 2 + spacing_y ** 2 + spacing_z ** 2)
    max_step_mm = max(0.18 * voxel_diag, 0.025)
    moved_total = 0
    chunk_size = 60000
    h = 0.50
    for _ in range(max(1, int(iterations))):
        moved_iteration = 0
        for start in range(0, len(vertices), chunk_size):
            end = min(len(vertices), start + chunk_size)
            local = vertices[start:end]
            coords = _centered_xyz_to_global_voxel(local)
            intensity = _runtime_density_at_voxel_coordinates(coords)
            if intensity is None:
                continue
            gradients = []
            for axis, spacing_mm in ((0, spacing_z), (1, spacing_y), (2, spacing_x)):
                plus = coords.copy(); plus[:, axis] += h
                minus = coords.copy(); minus[:, axis] -= h
                fp = _runtime_density_at_voxel_coordinates(plus)
                fm = _runtime_density_at_voxel_coordinates(minus)
                gradients.append((fp - fm) / (2.0 * h * max(spacing_mm, 1e-9)))
            gradient_xyz = np.column_stack((gradients[2], gradients[1], gradients[0]))
            norm_sq = np.einsum("ij,ij->i", gradient_xyz, gradient_xyz)
            reliable = np.isfinite(intensity) & np.isfinite(norm_sq) & (norm_sq > 1e-8)
            scale = np.zeros(len(local), dtype=np.float64)
            scale[reliable] = -(intensity[reliable] - float(level)) / norm_sq[reliable]
            step = gradient_xyz * scale[:, None]
            lengths = np.linalg.norm(step, axis=1)
            limit = lengths > max_step_mm
            step[limit] *= (max_step_mm / np.maximum(lengths[limit], 1e-12))[:, None]
            move = reliable & (np.linalg.norm(step, axis=1) > 1e-5)
            local[move] += step[move]
            vertices[start:end] = local
            moved_iteration += int(move.sum())
        moved_total += moved_iteration
        if moved_iteration == 0:
            break
    return vertices.astype(np.float32), {"projected": moved_total, "iterations": max(1, int(iterations))}


def _weld_triangle_arrays(vertices_zyx, faces):
    """Merge coincident slab-boundary vertices and discard degenerate triangles."""
    np = load_numpy()
    vertices = np.asarray(vertices_zyx, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    if len(vertices) == 0 or len(triangles) == 0:
        return vertices.astype(np.float32), triangles.astype(np.int32)
    quantized = np.rint(vertices / DICOM_HD_VERTEX_WELD_TOLERANCE_VOX).astype(np.int64)
    _keys, first, inverse = np.unique(
        quantized, axis=0, return_index=True, return_inverse=True
    )
    welded_vertices = vertices[np.asarray(first, dtype=np.int64)]
    welded_faces = inverse[triangles]
    valid = (
        (welded_faces[:, 0] != welded_faces[:, 1])
        & (welded_faces[:, 1] != welded_faces[:, 2])
        & (welded_faces[:, 2] != welded_faces[:, 0])
    )
    return (
        np.asarray(welded_vertices, dtype=np.float32),
        np.asarray(welded_faces[valid], dtype=np.int32),
    )


def _native_threshold_voxel_shell_chunked(context, level: float, structure: str):
    """Dependency-free native threshold surface for the SIMPLE implant route.

    This is the fail-safe STL engine.  It uses only Blender's NumPy and the
    calibrated DICOM voxels already in memory, so SIMPLE never depends on
    scikit-image, Torch, nnU-Net or a second Python installation.

    The volume is processed in Z slabs with a one-voxel halo. Exposed faces are
    encoded with *global* DICOM grid-corner IDs and welded once at the end,
    therefore slab borders cannot create internal caps or duplicate seams.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible en Blender/Mixar")
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")

    (z_bounds, y_bounds, x_bounds) = _threshold_bbox_native(float(level))
    z0, z1 = (int(v) for v in z_bounds)
    y0, y1 = (int(v) for v in y_bounds)
    x0, x1 = (int(v) for v in x_bounds)
    full_z, full_y, full_x = (int(v) for v in RUNTIME.dims_zyx)
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    slab_depth = int(DICOM_HD_TARGET_SLAB_VOXELS // max(1, width * height))
    slab_depth = max(DICOM_HD_MIN_SLAB_DEPTH, min(DICOM_HD_MAX_SLAB_DEPTH, slab_depth))
    total_depth = max(1, z1 - z0)
    slab_count = max(1, int(math.ceil(total_depth / float(slab_depth))))

    gy = full_y + 1
    gx = full_x + 1
    quad_parts = []

    def grid_id(z, y, x):
        return (z.astype(np.int64) * gy + y.astype(np.int64)) * gx + x.astype(np.int64)

    def append_faces(exposed, global_origin, corners):
        pos = np.argwhere(exposed)
        if pos.size == 0:
            return
        pos = pos.astype(np.int64, copy=False)
        z = pos[:, 0] + int(global_origin[0])
        y = pos[:, 1] + int(global_origin[1])
        x = pos[:, 2] + int(global_origin[2])
        q = []
        for dz, dy, dx in corners:
            q.append(grid_id(z + dz, y + dy, x + dx))
        quad_parts.append(np.stack(q, axis=1))

    for slab_index, core_start in enumerate(range(z0, z1, slab_depth), start=1):
        core_end = min(z1, core_start + slab_depth)
        hz0 = max(0, core_start - 1)
        hz1 = min(full_z, core_end + 1)
        hy0 = max(0, y0 - 1)
        hy1 = min(full_y, y1 + 1)
        hx0 = max(0, x0 - 1)
        hx1 = min(full_x, x1 + 1)

        props = context.scene.dicom_wizard_pro
        props.status = f"STL SIMPLE integrado · bloque {slab_index}/{slab_count}"
        force_ui_redraw()

        values = _density_native_slab(hz0, hz1, hy0, hy1, hx0, hx1)
        occupied = np.isfinite(values) & (values >= float(level))

        cz0, cz1 = core_start - hz0, core_end - hz0
        cy0, cy1 = y0 - hy0, y1 - hy0
        cx0, cx1 = x0 - hx0, x1 - hx0
        core_mask = occupied[cz0:cz1, cy0:cy1, cx0:cx1]
        if not bool(core_mask.any()):
            continue

        # Six neighbour fields. Interior neighbours come directly from the
        # current core; only the outermost cell of each side needs the halo.
        left = np.zeros_like(core_mask, dtype=bool)
        right = np.zeros_like(core_mask, dtype=bool)
        down = np.zeros_like(core_mask, dtype=bool)
        up = np.zeros_like(core_mask, dtype=bool)
        back = np.zeros_like(core_mask, dtype=bool)
        front = np.zeros_like(core_mask, dtype=bool)

        left[:, :, 1:] = core_mask[:, :, :-1]
        if x0 > 0:
            left[:, :, 0] = occupied[cz0:cz1, cy0:cy1, cx0 - 1]
        right[:, :, :-1] = core_mask[:, :, 1:]
        if x1 < full_x:
            right[:, :, -1] = occupied[cz0:cz1, cy0:cy1, cx1]

        down[:, 1:, :] = core_mask[:, :-1, :]
        if y0 > 0:
            down[:, 0, :] = occupied[cz0:cz1, cy0 - 1, cx0:cx1]
        up[:, :-1, :] = core_mask[:, 1:, :]
        if y1 < full_y:
            up[:, -1, :] = occupied[cz0:cz1, cy1, cx0:cx1]

        back[1:, :, :] = core_mask[:-1, :, :]
        if core_start > 0:
            back[0, :, :] = occupied[cz0 - 1, cy0:cy1, cx0:cx1]
        front[:-1, :, :] = core_mask[1:, :, :]
        if core_end < full_z:
            front[-1, :, :] = occupied[cz1, cy0:cy1, cx0:cx1]

        origin = (core_start, y0, x0)
        append_faces(core_mask & ~left,  origin, ((0,0,0),(1,0,0),(1,1,0),(0,1,0)))
        append_faces(core_mask & ~right, origin, ((0,0,1),(0,1,1),(1,1,1),(1,0,1)))
        append_faces(core_mask & ~down,  origin, ((0,0,0),(0,0,1),(1,0,1),(1,0,0)))
        append_faces(core_mask & ~up,    origin, ((0,1,0),(1,1,0),(1,1,1),(0,1,1)))
        append_faces(core_mask & ~back,  origin, ((0,0,0),(0,1,0),(0,1,1),(0,0,1)))
        append_faces(core_mask & ~front, origin, ((1,0,0),(1,0,1),(1,1,1),(1,1,0)))

    if not quad_parts:
        raise RuntimeError("El umbral no produjo una superficie STL")

    quad_ids = np.concatenate(quad_parts, axis=0)
    unique_ids, inverse = np.unique(quad_ids.ravel(), return_inverse=True)
    quad_local = inverse.reshape((-1, 4)).astype(np.int32, copy=False)

    z_grid = unique_ids // (gy * gx)
    rem = unique_ids % (gy * gx)
    y_grid = rem // gx
    x_grid = rem % gx
    # Grid corners lie half a voxel away from the corresponding voxel centre.
    corners_zyx = np.column_stack((z_grid, y_grid, x_grid)).astype(np.float64, copy=False)
    corners_zyx -= 0.5
    vertices_xyz = _global_voxel_to_centered_xyz(corners_zyx)

    triangles = np.empty((len(quad_local) * 2, 3), dtype=np.int32)
    triangles[0::2] = quad_local[:, (0, 1, 2)]
    triangles[1::2] = quad_local[:, (0, 2, 3)]
    return (
        np.asarray(vertices_xyz, dtype=np.float32),
        triangles,
        {
            "backend": "DSG_NUMPY_NATIVE_THRESHOLD_SHELL",
            "native_resolution": True,
            "slabs": int(slab_count),
            "quads": int(len(quad_local)),
        },
    )


def _marching_cubes_native_chunked(context, level: float, structure: str):
    """Extract a native-resolution isosurface in overlapping Z slabs."""
    np = load_numpy()
    measure = load_skimage_measure()
    if np is None or measure is None:
        raise RuntimeError("El motor STL no está disponible")
    (z_bounds, y_bounds, x_bounds) = _threshold_bbox_native(float(level))
    z0, z1 = z_bounds; y0, y1 = y_bounds; x0, x1 = x_bounds
    width = max(1, int(x1 - x0)); height = max(1, int(y1 - y0))
    slab_depth = int(DICOM_HD_TARGET_SLAB_VOXELS // max(1, width * height))
    slab_depth = max(DICOM_HD_MIN_SLAB_DEPTH, min(DICOM_HD_MAX_SLAB_DEPTH, slab_depth))
    total_depth = int(z1 - z0)
    slab_count = max(1, int(math.ceil(total_depth / float(slab_depth))))

    vertex_parts = []
    face_parts = []
    vertex_offset = 0
    for slab_index, core_start in enumerate(range(z0, z1, slab_depth), start=1):
        core_end = min(z1, core_start + slab_depth)
        ext_start = max(z0, core_start - DICOM_HD_OVERLAP_SLICES)
        ext_end = min(z1, core_end + DICOM_HD_OVERLAP_SLICES)
        props = context.scene.dicom_wizard_pro
        props.status = f"STL HD · bloque {slab_index}/{slab_count}"
        force_ui_redraw()

        values = _density_native_slab(ext_start, ext_end, y0, y1, x0, x1)
        finite = values[np.isfinite(values)]
        if finite.size == 0 or float(finite.max()) < float(level):
            continue
        outside = min(float(finite.min()), float(level) - max(1e-3, abs(float(level)) * 1e-5))
        values = np.where(np.isfinite(values), values, outside).astype(np.float32, copy=False)
        values = _refine_native_slab(values, structure)
        padded = np.pad(values, 1, mode="constant", constant_values=outside)
        try:
            local_vertices, local_faces, _normals, _surface_values = measure.marching_cubes(
                padded,
                level=float(level),
                step_size=1,
                allow_degenerate=False,
                method="lewiner",
            )
        except (RuntimeError, ValueError):
            continue
        local_vertices -= 1.0
        global_vertices = local_vertices + np.asarray((ext_start, y0, x0), dtype=np.float64)
        centroids_z = global_vertices[np.asarray(local_faces, dtype=np.int64), 0].mean(axis=1)
        if core_end >= z1:
            keep = (centroids_z >= float(core_start) - 1e-6) & (centroids_z <= float(core_end) + 1e-6)
        else:
            keep = (centroids_z >= float(core_start) - 1e-6) & (centroids_z < float(core_end) - 1e-6)
        kept_faces = np.asarray(local_faces[keep], dtype=np.int64)
        if kept_faces.size == 0:
            continue
        used = np.unique(kept_faces.ravel())
        remap = np.full(len(global_vertices), -1, dtype=np.int64)
        remap[used] = np.arange(len(used), dtype=np.int64)
        compact_vertices = np.asarray(global_vertices[used], dtype=np.float32)
        compact_faces = np.asarray(remap[kept_faces], dtype=np.int32)
        vertex_parts.append(compact_vertices)
        face_parts.append(compact_faces + int(vertex_offset))
        vertex_offset += len(compact_vertices)

    if not vertex_parts or not face_parts:
        raise RuntimeError("El umbral no produjo una superficie válida")
    vertices = np.concatenate(vertex_parts, axis=0)
    faces = np.concatenate(face_parts, axis=0)
    vertices, faces = _weld_triangle_arrays(vertices, faces)
    return _global_voxel_to_centered_xyz(vertices), faces, {
        "bounds_zyx": ((z0, z1), (y0, y1), (x0, x1)),
        "slabs": slab_count,
        "slab_depth": slab_depth,
        "native_resolution": True,
    }

def _new_surface_from_arrays(
    context,
    *,
    object_name: str,
    vertices_xyz,
    faces,
    root,
) -> bpy.types.Object:
    """Create a large triangle mesh using Blender bulk collection writes."""
    np = load_numpy()
    old = bpy.data.objects.get(object_name)
    old_mesh = old.data if old is not None and old.type == "MESH" else None

    vertices = np.ascontiguousarray(vertices_xyz, dtype=np.float32)
    triangles = np.ascontiguousarray(faces, dtype=np.int32)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise RuntimeError("Vértices STL inválidos")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise RuntimeError("Caras STL inválidas")

    mesh = bpy.data.meshes.new(object_name + "_MESH_BUILD")
    mesh.vertices.add(int(vertices.shape[0]))
    mesh.vertices.foreach_set("co", vertices.ravel())

    loop_count = int(triangles.shape[0] * 3)
    mesh.loops.add(loop_count)
    mesh.loops.foreach_set("vertex_index", triangles.ravel())
    mesh.polygons.add(int(triangles.shape[0]))
    mesh.polygons.foreach_set(
        "loop_start", np.arange(0, loop_count, 3, dtype=np.int32)
    )
    mesh.polygons.foreach_set(
        "loop_total", np.full(triangles.shape[0], 3, dtype=np.int32)
    )
    try:
        mesh.polygons.foreach_set(
            "use_smooth", np.ones(triangles.shape[0], dtype=np.bool_)
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    # Marching-cubes/DSG arrays are preflighted numerically before commit. A full
    # mesh.validate() on every 3-D clinical surface duplicated an O(F) topology
    # walk on Blender's main thread. Edge calculation is retained for downstream
    # Blender operators, but the redundant validation pass is removed.
    mesh.update(calc_edges=True)

    obj = bpy.data.objects.new(object_name + "_BUILD", mesh)
    get_collection().objects.link(obj)
    # Transactional replacement: keep the previous clinical surface until the
    # complete HD mesh exists and has passed Blender validation.
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    obj.name = object_name
    mesh.name = object_name + "_MESH"
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    obj["dicom_alignment_frame"] = "centered voxel XYZ under DICOM_WIZARD_ROOT"
    obj["dicom_laterality_mapping"] = "DICOM_IOP_NATIVE_NO_SINGLE_AXIS_MIRROR"
    obj["dicom_surface_engine"] = "native chunked skimage marching_cubes"
    obj["dicom_stl_extra_rotation"] = False
    return obj

def _apply_stl_orientation_correction(
    obj: bpy.types.Object,
    props,
) -> None:
    """Keep the mesh in the exact same root-local frame as its source volume.

    This compatibility hook intentionally performs no rotation. Earlier builds
    baked independent 180-degree X/Z rotations into mesh vertices after the
    Volume-to-Mesh conversion, breaking alignment with the MPR planes.
    """
    if obj is None or obj.type != "MESH" or obj.data is None:
        return

    obj["dicom_alignment_frame"] = "shared DICOM_WIZARD_ROOT local frame"
    obj["dicom_stl_extra_rotation"] = False
    obj["dicom_stl_x_correction_degrees"] = 0.0
    obj["dicom_stl_z_correction_degrees"] = 0.0


def _sampled_voxel_volume_mm3(z_indices, y_indices, x_indices) -> float:
    np = load_numpy()
    if np is None:
        if RUNTIME.spacing_zyx_mm:
            sz, sy, sx = (float(v) for v in RUNTIME.spacing_zyx_mm)
            return max(sz * sy * sx, 1e-9)
        return 1.0
    def _axis_step_mm(indices, spacing_mm):
        if len(indices) <= 1:
            return float(spacing_mm)
        diffs = np.diff(np.asarray(indices, dtype=np.int32))
        diffs = diffs[diffs > 0]
        if diffs.size == 0:
            return float(spacing_mm)
        return float(np.median(diffs)) * float(spacing_mm)
    sz, sy, sx = (float(v) for v in RUNTIME.spacing_zyx_mm)
    return max(_axis_step_mm(z_indices, sz) * _axis_step_mm(y_indices, sy) * _axis_step_mm(x_indices, sx), 1e-9)


def _apply_small_island_cleanup_to_sampled_values(sampled_values, threshold_density, z_indices, y_indices, x_indices, props):
    np = load_numpy()
    if np is None or not bool(getattr(props, "auto_clean_small_islands", True)):
        return sampled_values, 0
    mask = np.asarray(sampled_values >= threshold_density, dtype=bool)
    if int(mask.sum()) < 8:
        return sampled_values, 0
    runs, parent, sizes, _boundary = _rle_component_analysis(mask, adjacency=1)
    voxel_volume = _sampled_voxel_volume_mm3(z_indices, y_indices, x_indices)
    minimum_voxels = max(1, int(np.ceil(float(getattr(props, "island_min_mm3", 5.0)) / max(voxel_volume, 1e-9))))
    keep_roots = {root for root, size in sizes.items() if int(size) >= minimum_voxels}
    if not keep_roots or len(keep_roots) == len(sizes):
        return sampled_values, 0
    cleaned_mask = _mask_from_component_roots(mask.shape, runs, parent, keep_roots)
    removed = int(mask.sum() - cleaned_mask.sum())
    if removed <= 0:
        return sampled_values, 0
    cleaned_values = np.array(sampled_values, copy=True)
    cleaned_values[~cleaned_mask] = float(threshold_density) - 1e-3
    return cleaned_values, removed


def generate_direct_density_surface(context) -> bpy.types.Object:
    """Compatibility entry point for the adaptive DSG DICOM segmentation engine."""
    props = context.scene.dicom_wizard_pro
    # DSG 8.7: the clinical segmentation is semantic. Density thresholds are
    # only a viewer aid and never decide whether a voxel is tooth or bone.
    segment_tissue_semantically(context)
    return generate_segmentation_surface(context)



def _axis_voxel_boundaries(indices):
    """Cell-boundary coordinates for sampled voxel-center indices."""
    np = load_numpy()
    values = np.asarray(indices, dtype=np.float64)
    out = np.empty(len(values) + 1, dtype=np.float64)
    if len(values) == 1:
        out[:] = (values[0] - 0.5, values[0] + 0.5)
        return out
    out[1:-1] = 0.5 * (values[:-1] + values[1:])
    out[0] = values[0] - 0.5 * (values[1] - values[0])
    out[-1] = values[-1] + 0.5 * (values[-1] - values[-2])
    return out


def _voxel_shell_from_sampled_mask(sampled_mask, z_centers, y_centers, x_centers):
    """Triangulate a sampled binary mask in the exact DICOM voxel frame.

    ``z_centers/y_centers/x_centers`` are positions in the original voxel grid,
    not local array coordinates.  This lets the same bundled engine serve both
    the low-resolution preview and the final full-resolution segmentation.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    sampled = np.ascontiguousarray(sampled_mask, dtype=bool)
    if sampled.ndim != 3 or min(sampled.shape) < 1 or int(sampled.sum()) < 2:
        raise RuntimeError("La máscara es demasiado pequeña para crear una malla")

    z_centers = np.asarray(z_centers, dtype=np.float64)
    y_centers = np.asarray(y_centers, dtype=np.float64)
    x_centers = np.asarray(x_centers, dtype=np.float64)
    if sampled.shape != (len(z_centers), len(y_centers), len(x_centers)):
        raise RuntimeError("La rejilla de segmentación no coincide con la máscara")

    nz, ny, nx = sampled.shape
    gz, gy, gx = nz + 1, ny + 1, nx + 1
    quads = []

    def grid_id(z, y, x):
        return (z.astype(np.int64) * gy + y.astype(np.int64)) * gx + x.astype(np.int64)

    def add_quads(sel, corners):
        pos = np.argwhere(sel)
        if pos.size == 0:
            return
        z = pos[:, 0].astype(np.int64)
        y = pos[:, 1].astype(np.int64)
        x = pos[:, 2].astype(np.int64)
        q = []
        for dz, dy, dx in corners:
            q.append(grid_id(z + dz, y + dy, x + dx))
        quads.append(np.stack(q, axis=1))

    # Six exposed sides per occupied voxel, welded through deterministic grid IDs.
    left = np.zeros_like(sampled); left[:, :, 1:] = sampled[:, :, :-1]
    right = np.zeros_like(sampled); right[:, :, :-1] = sampled[:, :, 1:]
    down = np.zeros_like(sampled); down[:, 1:, :] = sampled[:, :-1, :]
    up = np.zeros_like(sampled); up[:, :-1, :] = sampled[:, 1:, :]
    back = np.zeros_like(sampled); back[1:, :, :] = sampled[:-1, :, :]
    front = np.zeros_like(sampled); front[:-1, :, :] = sampled[1:, :, :]

    add_quads(sampled & ~left,  ((0,0,0),(1,0,0),(1,1,0),(0,1,0)))
    add_quads(sampled & ~right, ((0,0,1),(0,1,1),(1,1,1),(1,0,1)))
    add_quads(sampled & ~down,  ((0,0,0),(0,0,1),(1,0,1),(1,0,0)))
    add_quads(sampled & ~up,    ((0,1,0),(1,1,0),(1,1,1),(0,1,1)))
    add_quads(sampled & ~back,  ((0,0,0),(0,1,0),(0,1,1),(0,0,1)))
    add_quads(sampled & ~front, ((1,0,0),(1,0,1),(1,1,1),(1,1,0)))

    if not quads:
        raise RuntimeError("La máscara no produjo una superficie")
    quad_ids = np.concatenate(quads, axis=0)
    unique_ids, inverse = np.unique(quad_ids.ravel(), return_inverse=True)
    quad_local = inverse.reshape((-1, 4)).astype(np.int32, copy=False)

    z_grid = unique_ids // (gy * gx)
    rem = unique_ids % (gy * gx)
    y_grid = rem // gx
    x_grid = rem % gx

    zb = _axis_voxel_boundaries(z_centers)
    yb = _axis_voxel_boundaries(y_centers)
    xb = _axis_voxel_boundaries(x_centers)
    global_zyx = np.column_stack((zb[z_grid], yb[y_grid], xb[x_grid]))
    vertices_xyz = _global_voxel_to_centered_xyz(global_zyx)

    triangles = np.empty((len(quad_local) * 2, 3), dtype=np.int32)
    triangles[0::2] = quad_local[:, (0, 1, 2)]
    triangles[1::2] = quad_local[:, (0, 2, 3)]
    return (
        np.asarray(vertices_xyz, dtype=np.float32),
        triangles,
        {"quads": int(len(quad_local)), "occupied": int(sampled.sum())},
    )


def _native_voxel_shell_from_mask(mask, origin_zyx, *, max_axis: int = 384):
    """Triangulate the boundary of a binary mask using Blender + NumPy only."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3 or min(mask.shape) < 1 or int(mask.sum()) < 2:
        raise RuntimeError("La máscara es demasiado pequeña para crear una malla")

    max_axis = max(96, int(max_axis))
    stride = max(1, int(math.ceil(max(mask.shape) / float(max_axis))))
    iz = _preview_axis_indices(mask.shape[0], stride)
    iy = _preview_axis_indices(mask.shape[1], stride)
    ix = _preview_axis_indices(mask.shape[2], stride)
    sampled = np.ascontiguousarray(mask[np.ix_(iz, iy, ix)], dtype=bool)
    z0, y0, x0 = (int(v) for v in origin_zyx)
    vertices, triangles, stats = _voxel_shell_from_sampled_mask(
        sampled,
        iz.astype(np.float64) + float(z0),
        iy.astype(np.float64) + float(y0),
        ix.astype(np.float64) + float(x0),
    )
    stats["stride"] = int(stride)
    stats["backend"] = "DSG_NUMPY_VOXEL_SHELL"
    return vertices, triangles, stats


def generate_segmentation_surface(context) -> bpy.types.Object:
    """Convert the active AI mask to Blender-native surfaces.

    UniversalLab teeth are emitted as independent learned instances. Other
    masks use marching cubes instead of the old cubical voxel shell, removing
    the visible terracing and unnecessary polygon load from DSG 8.7.
    """
    props = context.scene.dicom_wizard_pro
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    structure = str(props.segmentation_structure).upper()
    state, mask = _require_mask(props)
    if min(mask.shape) < 1 or int(mask.sum()) < 2:
        raise RuntimeError("La segmentación es demasiado pequeña para crear una superficie")

    semantic_kind = str(state.get("semantic_model_kind", RUNTIME.semantic_model_kind or ""))
    universal_summary = None
    if structure in {"TEETH", "BONE"} and semantic_kind == "universal":
        labels = _load_semantic_labels_cached("universal")
        if labels is None:
            raise RuntimeError("Se perdió el labelmap UniversalLab; vuelve a segmentar")
        props.status = "Creando dientes independientes + FDI…"
        force_ui_redraw()
        from . import cbct_dental_module
        universal_summary = cbct_dental_module.build_universal_dentition(
            context, labels, run_mirroring_check=True
        )
        if structure == "TEETH":
            obj = universal_summary["alignment_reference"]
            state["surface_name"] = obj.name
            props.generated_surface_name = obj.name
            props.surface_ready = True
            props.surface_preview_status = (
                f"{universal_summary['tooth_count']} dientes · "
                f"{universal_summary['total_faces']:,} caras clínicas"
            )
            context.scene[SUITE_STAGE_KEY] = "DICOM"
            _apply_dicom_surface_transparency(context, props)
            teeth = cbct_dental_module.dentition_objects(context)
            if teeth:
                # Blender 5.x can keep a collection datablock alive while it is
                # no longer part of the active ViewLayer.  Never call
                # select_set directly on a freshly generated tooth.
                safe_select_object(context, teeth[0], make_active=True, deselect_others=True)
            return obj
        # BONE + TEETH: keep the learned teeth as independent objects and make
        # only maxilla/mandible (53+54) into the companion bone mesh. This is
        # both clearer and lighter than fusing all labels into one STL.
        bone_full = np.isin(labels, np.asarray((53, 54), dtype=np.uint8))
        bone_compact, bone_origin = _compact_mask(bone_full, (0, 0, 0))
        del bone_full
        if bone_compact is None or not bone_compact.any():
            raise RuntimeError("UniversalLab no devolvió maxila/mandíbula suficientes")
        mask = bone_compact
        surface_origin = bone_origin
    else:
        surface_origin = state["origin_zyx"]

    max_axis = 384
    try:
        quality = int(props.direct_stl_quality)
        max_axis = max(256, min(512, quality))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    props.status = f"Creando malla · {SEGMENTATION_STRUCTURES[structure]['label']}…"
    force_ui_redraw()
    z0, y0, x0 = (int(v) for v in surface_origin)
    stride = max(1, int(math.ceil(max(mask.shape) / float(max_axis))))
    iz = _preview_axis_indices(mask.shape[0], stride)
    iy = _preview_axis_indices(mask.shape[1], stride)
    ix = _preview_axis_indices(mask.shape[2], stride)
    sampled = np.ascontiguousarray(mask[np.ix_(iz, iy, ix)], dtype=np.float32)
    vertices_xyz, faces = _marching_cubes_cropped(
        sampled,
        0.5,
        iz.astype(np.float64) + float(z0),
        iy.astype(np.float64) + float(y0),
        ix.astype(np.float64) + float(x0),
    )
    stats = {"stride": int(stride), "backend": "DSG_MARCHING_CUBES"}
    anatomy_stats = {"status": "SKIPPED"}
    if bool(state.get("semantic", False)) and structure in {"BONE", "BONE_ONLY"} and not bool(state.get("skip_anatomy_refine", False)):
        try:
            from . import anatomy_refine
            vertices_xyz, faces, anatomy_stats = anatomy_refine.refine_segmented_surface(
                context, vertices_xyz, faces,
                mask=mask, origin_zyx=surface_origin, kind="BONE",
            )
        except Exception as refine_exc:
            anatomy_stats = {
                "status": "FALLBACK_SOURCE",
                "reason": f"{type(refine_exc).__name__}: {refine_exc}",
            }

    root = get_root(get_collection())
    if structure == "TEETH":
        canonical_name = NAME_DICOM_TEETH
    elif structure == "BONE_ONLY" or (structure == "BONE" and semantic_kind == "universal"):
        canonical_name = NAME_DICOM_BONE
    else:
        canonical_name = NAME_DICOM_COMBINED

    obj = _new_surface_from_arrays(
        context,
        object_name=canonical_name,
        vertices_xyz=vertices_xyz,
        faces=faces,
        root=root,
    )
    if len(obj.data.materials) == 0:
        material_structure = "BONE_ONLY" if (structure == "BONE" and semantic_kind == "universal") else structure
        obj.data.materials.append(_surface_material(material_structure))

    smoothing = int(props.surface_smoothing_iterations)
    # Learned CBCT anatomy already received the constrained 9.2.14 refinement.
    # Do not stack Blender's ordinary Smooth modifier on it: repeated Laplacian
    # smoothing is exactly the kind of unbounded contraction that made teeth and
    # cortical contours look smaller than the radiographic anatomy.
    if smoothing > 0 and not bool(state.get("semantic", False)):
        smooth = obj.modifiers.new("Suavizado", "SMOOTH")
        smooth.factor = 0.18
        smooth.iterations = min(3, smoothing)

    reduction = clamp(float(props.surface_reduction_percent) / 100.0, 0.0, 0.95)
    if reduction > 0.001:
        decimate = obj.modifiers.new("Reducción", "DECIMATE")
        decimate.decimate_type = "COLLAPSE"
        decimate.ratio = max(0.02, 1.0 - reduction)

    obj["dicom_parented_to_root"] = True
    obj["dicom_root_name"] = root.name
    obj["dicom_surface_sampling_stride"] = int(stats["stride"])
    if bool(state.get("semantic", False)) and structure in {"BONE", "BONE_ONLY"}:
        obj["DSG_anatomy_refine_status"] = str(anatomy_stats.get("status", "UNKNOWN"))
        obj["DSG_anatomy_refine_backend"] = str(anatomy_stats.get("backend", "SOURCE"))
        obj["DSG_anatomy_refine_volume_ratio"] = float(anatomy_stats.get("volume_ratio", 1.0) or 1.0)
        obj["DSG_anatomy_refine_cbct_snapped"] = int(anatomy_stats.get("cbct_snapped", 0) or 0)
        obj["DSG_anatomy_refine_json"] = json.dumps(anatomy_stats, ensure_ascii=False, default=str)
    if bool(state.get("semantic", False)):
        obj["dicom_surface_engine"] = f"DSG 8.8 in-process {semantic_kind or 'semantic'} + marching cubes"
        classes = state.get("semantic_classes", ())
        if len(classes) <= 12:
            obj["dicom_semantic_classes"] = ",".join(str(v) for v in classes)
        else:
            obj["dicom_semantic_classes"] = f"{min(classes)}-{max(classes)}"
    else:
        obj["dicom_surface_engine"] = "DSG adaptive density + marching cubes"
    obj["dicom_density_low"] = float(state.get("learned_low", props.auto_range_low))
    obj["dicom_density_high"] = float(state.get("learned_high", props.auto_range_high))
    role = ROLE_DICOM_TEETH if structure == "TEETH" else ROLE_DICOM_BONE
    _set_suite_role(obj, role, component="DICOM")
    obj["dental_suite_structure"] = structure
    obj["dental_suite_source_path"] = str(RUNTIME.source_path or "")
    context.scene[SUITE_STAGE_KEY] = "DICOM"

    state["surface_name"] = obj.name
    props.generated_surface_name = obj.name
    props.surface_ready = True
    props.surface_preview_status = f"{len(faces):,} caras · marching cubes"
    _apply_dicom_surface_transparency(context, props)

    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj



def _prepare_mask_surface_arrays(mask, origin_zyx, *, kind="JAW", label=None, max_axis=384, refine=True):
    """Pure numeric native-resolution mask surface for worker use.

    ``max_axis`` remains in the signature for compatibility but v9.2.64 never
    downsamples clinical semantic anatomy. VTK Discrete Flying Edges is used on
    the compact mask when available; Lewiner step=1 is the exact fallback.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if mask is None or not bool(getattr(mask, "any", lambda: False)()):
        return None
    from . import cbct_surface_meshing
    mask = np.ascontiguousarray(mask, dtype=np.uint8)
    z0, y0, x0 = (int(v) for v in (origin_zyx or (0, 0, 0)))
    extraction = cbct_surface_meshing.extract_binary_surface(
        mask,
        step_size=1,
        preferred_engine="AUTO",
        vtk_module=load_vtk(),
        skimage_measure=load_skimage_measure(),
    )
    vertices_zyx = np.asarray(extraction.vertices_zyx, dtype=np.float64)
    vertices_zyx += np.asarray((z0, y0, x0), dtype=np.float64)[None, :]
    vertices_xyz = _global_voxel_to_centered_xyz(vertices_zyx)
    faces = np.ascontiguousarray(extraction.faces, dtype=np.int32)
    refine_stats = {"status": "SKIPPED_NATIVE_SOURCE"}
    if bool(refine):
        try:
            from . import anatomy_refine
            vertices_xyz, faces, refine_stats = anatomy_refine.refine_segmented_surface(
                None, vertices_xyz, faces,
                mask=mask, origin_zyx=(z0, y0, x0), kind=str(kind), label=label,
            )
        except Exception as exc:
            refine_stats = {"status": "FALLBACK_SOURCE", "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "vertices": np.ascontiguousarray(vertices_xyz, dtype=np.float32),
        "faces": np.ascontiguousarray(faces, dtype=np.int32),
        "stride": 1,
        "origin": (z0, y0, x0),
        "kind": str(kind),
        "label": int(label) if label is not None else None,
        "refine_stats": dict(refine_stats),
        "mask_voxels": int(mask.sum()),
        "surface_mesher": str(extraction.engine),
        "surface_extract_s": float(extraction.elapsed_s),
        "native_resolution": True,
    }


def _prepare_canal_surface_arrays(labels, verifier_mask=None, verifier_origin=None, verifier_stats=None):
    """Pure numeric canal fusion + native marching cubes for worker use."""
    np = load_numpy()
    universal_mask, universal_origin = _compact_mask_for_classes(labels, (55,))
    fused, origin, fusion = _fuse_mandibular_canal_masks(
        universal_mask, universal_origin,
        verifier_mask=verifier_mask, verifier_origin=verifier_origin,
    )
    if fused is None or not fused.any():
        return {"status": "NOT_FOUND", "faces": 0, "voxels": 0, "fusion": dict(fusion)}
    voxels = int(fused.sum())
    z0, y0, x0 = (int(v) for v in origin)
    sampled = np.ascontiguousarray(fused, dtype=np.float32)
    iz = np.arange(sampled.shape[0], dtype=np.float64) + float(z0)
    iy = np.arange(sampled.shape[1], dtype=np.float64) + float(y0)
    ix = np.arange(sampled.shape[2], dtype=np.float64) + float(x0)
    vertices_xyz, faces = _marching_cubes_cropped(sampled, 0.5, iz, iy, ix)
    return {
        "status": "SEGMENTED" if len(faces) >= 4 else "SURFACE_EMPTY",
        "vertices": np.ascontiguousarray(vertices_xyz, dtype=np.float32),
        "faces_array": np.ascontiguousarray(faces, dtype=np.int32),
        "faces": int(len(faces)), "voxels": voxels,
        "origin": tuple(int(v) for v in origin), "fusion": dict(fusion),
        "verifier": dict(verifier_stats or {}),
    }


SIMPLE_UPPER_COLOR = (0.86, 0.70, 0.38, 1.0)  # amarillo arena
SIMPLE_LOWER_COLOR = (0.36, 0.70, 0.91, 1.0)  # azul celeste
SIMPLE_UPPER_OBJECT = "DSG_Simple_Arch_A"
SIMPLE_LOWER_OBJECT = "DSG_Simple_Arch_B"
SIMPLE_ALIGNMENT_OBJECT = "Dental_DICOM_AlignmentComposite"


def _simple_arch_material(name: str, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.diffuse_color = tuple(float(v) for v in color)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    if bsdf is not None:
        socket = bsdf.inputs.get("Base Color")
        if socket is not None: socket.default_value = tuple(float(v) for v in color)
        socket = bsdf.inputs.get("Roughness")
        if socket is not None: socket.default_value = 0.52
        socket = bsdf.inputs.get("Metallic")
        if socket is not None: socket.default_value = 0.0
    return material


def _load_prepared_surface_arrays(prepared):
    np = load_numpy()
    if np is None: raise RuntimeError("NumPy no está disponible")
    if not isinstance(prepared, dict): raise RuntimeError("Superficie simple preparada no disponible")
    vp = str(prepared.get("vertices_path") or "")
    fp = str(prepared.get("faces_path") or prepared.get("faces_array_path") or "")
    if not vp or not fp: raise RuntimeError("La superficie simple no contiene geometría preparada")
    return np.asarray(np.load(vp, mmap_mode="r"), dtype=np.float32), np.asarray(np.load(fp, mmap_mode="r"), dtype=np.int32)


def _remove_object_family(name: str):
    for old in list(bpy.data.objects):
        if str(old.name) == name or str(old.name).startswith(name + "."):
            data = old.data if getattr(old, "type", None) == "MESH" else None
            bpy.data.objects.remove(old, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)


def build_simple_arch_pair(context, prepared_surfaces):
    """Materialize exactly two visible SIMPLE meshes and one hidden alignment target."""
    prepared_surfaces = dict(prepared_surfaces or {})
    up_v, up_f = _load_prepared_surface_arrays(prepared_surfaces.get("upper_arch"))
    lo_v, lo_f = _load_prepared_surface_arrays(prepared_surfaces.get("lower_arch"))
    for name in (SIMPLE_UPPER_OBJECT, SIMPLE_LOWER_OBJECT, SIMPLE_ALIGNMENT_OBJECT):
        _remove_object_family(name)
    root = get_root(get_collection())
    upper = _new_surface_from_arrays(context, object_name=SIMPLE_UPPER_OBJECT, vertices_xyz=up_v, faces=up_f, root=root)
    lower = _new_surface_from_arrays(context, object_name=SIMPLE_LOWER_OBJECT, vertices_xyz=lo_v, faces=lo_f, root=root)
    upper.data.materials.clear(); upper.data.materials.append(_simple_arch_material("DSG_SIMPLE_SAND", SIMPLE_UPPER_COLOR))
    lower.data.materials.clear(); lower.data.materials.append(_simple_arch_material("DSG_SIMPLE_SKY", SIMPLE_LOWER_COLOR))
    for obj, arch in ((upper, "UPPER"), (lower, "LOWER")):
        obj["DSG_simple_arch"] = arch
        obj["DSG_simple_route"] = True
        obj["DSG_has_fdi_identity"] = False
        obj["DSG_contains_canal"] = False
        obj["dental_suite_structure"] = "SIMPLE_ARCH"
        obj["dental_suite_source_path"] = str(RUNTIME.source_path or "")
        _set_suite_role(obj, ROLE_DICOM_BONE, component="DICOM")
    # Hidden composite keeps IOS alignment robust while the clinician sees only
    # the two requested colored meshes.
    np = load_numpy()
    combined_v = np.concatenate((up_v, lo_v), axis=0)
    combined_f = np.concatenate((up_f, lo_f + int(len(up_v))), axis=0)
    composite = _new_surface_from_arrays(context, object_name=SIMPLE_ALIGNMENT_OBJECT, vertices_xyz=combined_v, faces=combined_f, root=root)
    composite["DSG_simple_alignment_composite"] = True
    composite["dental_suite_alignment_reference"] = True
    _set_suite_role(composite, ROLE_DICOM_ALIGNMENT_COMPOSITE, component="DICOM")
    composite.hide_viewport = True; composite.hide_render = True; composite.hide_select = True
    try: composite.hide_set(True)
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    return upper, lower, composite


def build_semantic_arch_surface(
    context, mask, origin_zyx, *, object_name: str, arch: str, semantic_class: int,
    source_engine: str = "DENTALSEGMENTATOR_8_7", prepared=None,
):
    """Materialize one jaw class as its own Blender mesh.

    For the immediate route DSG prefers UniversalLab 54=maxilla and 53=mandible
    because those are jaw-specific classes. DentalSegmentator 1/2 remains the
    semantic-anatomy owner/fallback, but 9.2.16 no longer materializes an extra
    combined jaw mesh. Exactly one maxilla and one mandible remain in the scene.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if mask is None or not bool(getattr(mask, "any", lambda: False)()):
        raise RuntimeError(f"La segmentación no devolvió geometría para {arch}")
    z0, y0, x0 = (int(v) for v in (origin_zyx or (0, 0, 0)))
    if isinstance(prepared, dict) and (prepared.get("vertices") is not None or prepared.get("vertices_path")):
        vertices_xyz = (np.load(str(prepared.get("vertices_path")), mmap_mode="r")
                        if prepared.get("vertices_path") else np.asarray(prepared.get("vertices"), dtype=np.float32))
        faces = (np.load(str(prepared.get("faces_path")), mmap_mode="r")
                 if prepared.get("faces_path") else np.asarray(prepared.get("faces"), dtype=np.int32))
        refine_stats = dict(prepared.get("refine_stats") or {"status": "SKIPPED"})
    else:
        max_axis = 384
        props = context.scene.dicom_wizard_pro
        try:
            max_axis = max(256, min(512, int(props.direct_stl_quality)))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        payload = _prepare_mask_surface_arrays(
            mask, (z0, y0, x0), kind="JAW", label=int(semantic_class),
            max_axis=max_axis, refine=True,
        )
        if payload is None:
            raise RuntimeError(f"La segmentación no devolvió geometría para {arch}")
        vertices_xyz = payload["vertices"]
        faces = payload["faces"]
        refine_stats = dict(payload.get("refine_stats") or {"status": "SKIPPED"})
    # Enforce one physical Blender jaw object per arch. This also removes
    # stale .001/.002 copies left by interrupted or older segmentation runs.
    arch_upper = str(arch).upper()
    for old in list(bpy.data.objects):
        same_name_family = str(old.name) == str(object_name) or str(old.name).startswith(str(object_name) + ".")
        same_arch_source = (
            str(old.get("DSG_bone_arch", "") or "").upper() == arch_upper
            and not bool(old.get("DSG_immediate_arch_composite", False))
        )
        if not (same_name_family or same_arch_source):
            continue
        old_mesh = old.data if old.type == "MESH" else None
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    root = get_root(get_collection())
    obj = _new_surface_from_arrays(
        context, object_name=object_name,
        vertices_xyz=vertices_xyz, faces=faces, root=root,
    )
    if len(obj.data.materials) == 0:
        obj.data.materials.append(_surface_material("BONE_ONLY"))
    obj["dicom_parented_to_root"] = True
    obj["dicom_root_name"] = root.name
    source_engine = str(source_engine or "DENTALSEGMENTATOR_8_7").upper()
    obj["dicom_surface_engine"] = (
        "UniversalLab_jaw_class" if source_engine == "UNIVERSALLAB"
        else "DentalSegmentator_8.7_arch_class"
    )
    obj["DSG_semantic_source"] = source_engine
    obj["DSG_semantic_class"] = int(semantic_class)
    obj["DSG_bone_arch"] = str(arch).upper()
    obj["DSG_full_segmentation"] = True
    obj["DSG_anatomy_refine_status"] = str(refine_stats.get("status", "UNKNOWN"))
    obj["DSG_anatomy_refine_backend"] = str(refine_stats.get("backend", "SOURCE"))
    obj["DSG_anatomy_refine_volume_ratio"] = float(refine_stats.get("volume_ratio", 1.0) or 1.0)
    obj["DSG_anatomy_refine_cbct_snapped"] = int(refine_stats.get("cbct_snapped", 0) or 0)
    obj["DSG_anatomy_refine_json"] = json.dumps(refine_stats, ensure_ascii=False, default=str)
    obj["dental_suite_structure"] = str(arch).upper()
    obj["dental_suite_source_path"] = str(RUNTIME.source_path or "")
    _set_suite_role(obj, ROLE_DICOM_BONE, component="DICOM")
    return obj


class DICOMWizardProProperties(bpy.types.PropertyGroup):
    """Small persistent UI state; the voxel array lives in ``runtime.py``."""

    step: bpy.props.IntProperty(default=1, min=1, max=5)
    filepath: bpy.props.StringProperty(name="Archivo", subtype="FILE_PATH")
    status: bpy.props.StringProperty(default="Selecciona un archivo DICOM")
    ui_language: bpy.props.EnumProperty(
        name="Idioma",
        items=core.LANGUAGE_ITEMS,
        get=_language_get,
        set=_language_set,
    )
    show_reset_flow: bpy.props.BoolProperty(
        name="Back",
        default=False,
        description="Shows or hides the action that returns the DICOM workflow to its initial state",
    )
    header_valid: bpy.props.BoolProperty(default=False)
    volume_loaded: bpy.props.BoolProperty(default=False)

    filename: bpy.props.StringProperty(default="")
    source_kind: bpy.props.StringProperty(default="")
    dimensions_summary: bpy.props.StringProperty(default="")
    spacing_summary: bpy.props.StringProperty(default="")
    equipment_summary: bpy.props.StringProperty(default="")
    estimated_memory_mb: bpy.props.FloatProperty(default=0.0)
    spacing_inferred: bpy.props.BoolProperty(default=False)

    show_volume: bpy.props.BoolProperty(
        name="Volumen",
        default=True,
        update=on_visibility_change,
    )
    show_planes: bpy.props.BoolProperty(
        name="Plano",
        default=True,
        update=on_visibility_change,
    )
    show_all_planes: bpy.props.BoolProperty(
        name="Mostrar los 3 planos",
        default=False,
        update=on_active_plane_change,
    )
    show_box: bpy.props.BoolProperty(
        name="Marco",
        default=True,
        update=on_visibility_change,
    )
    realtime_mpr: bpy.props.BoolProperty(
        name="Tiempo real",
        description="Recalcula el corte mientras mueves o rotas el plano con G/R/S",
        default=True,
    )
    correct_inplane_180: bpy.props.BoolProperty(
        name="Corregir giro 180°",
        description="Corrige automáticamente DICOM dentales con X/Y invertidos sin cambiar el eje de los cortes",
        default=True,
        update=on_orientation_display_change,
    )

    threshold_min_percent: bpy.props.FloatProperty(
        name="Mínimo",
        description="Límite inferior de densidad visible",
        default=10.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_threshold_change,
    )
    threshold_max_percent: bpy.props.FloatProperty(
        name="Máximo",
        description="Límite superior de densidad visible",
        default=90.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_threshold_change,
    )
    current_density_min: bpy.props.FloatProperty(default=0.0)
    current_density_max: bpy.props.FloatProperty(default=1.0)
    volume_opacity: bpy.props.FloatProperty(
        name="Opacidad",
        description="Valor interno fijo de la visualización volumétrica",
        default=0.16,
        min=0.001,
        max=2.0,
        soft_min=0.01,
        soft_max=0.5,
        precision=3,
        options={"HIDDEN"},
        update=on_opacity_change,
    )
    preview_volume_opacity: bpy.props.FloatProperty(
        name="Volumen auxiliar",
        description="Valor interno fijo mientras se prepara la superficie sólida",
        default=0.08,
        min=0.0,
        max=0.25,
        soft_max=0.12,
        precision=3,
        options={"HIDDEN"},
        update=on_opacity_change,
    )
    auto_solid_preview: bpy.props.BoolProperty(
        name="Sólido auto",
        description="Compatibilidad interna; DSG mantiene siempre activa la superficie sólida automática",
        default=True,
        options={"HIDDEN"},
        update=on_auto_solid_preview_change,
    )
    auto_clean_small_islands: bpy.props.BoolProperty(
        name="Auto limpiar islas",
        description="Elimina automáticamente islas pequeñas al segmentar y al crear el STL",
        default=True,
        options={"HIDDEN"},
    )
    preview_display_mode: bpy.props.EnumProperty(
        name="Vista previa",
        description="Modo interno fijo de superficie sólida automática",
        items=[
            ("SURFACE", "Superficie", "Superficie sólida automática", "MESH_DATA", 0),
        ],
        default="SURFACE",
        options={"HIDDEN"},
        update=lambda self, context: None,
    )
    surface_preview_quality: bpy.props.EnumProperty(
        name="Detalle previo",
        description="Resolución de la superficie provisional; no cambia la calidad del STL final",
        items=[
            ("128", "Rápida", "Menor espera durante el ajuste"),
            ("192", "Detallada", "Mejor lectura de raíces y corticales"),
        ],
        default="128",
        update=on_surface_preview_quality_change,
    )
    surface_preview_ready: bpy.props.BoolProperty(default=False)
    surface_preview_status: bpy.props.StringProperty(default="Mueve el umbral para actualizar")

    preview_shell_width_percent: bpy.props.FloatProperty(
        name="Zona del límite",
        description="Anchura de la zona sutil que ayuda a localizar el umbral exacto sin quemar la imagen",
        default=0.35,
        min=0.05,
        max=3.0,
        soft_min=0.10,
        soft_max=1.0,
        subtype="PERCENTAGE",
        precision=2,
        update=on_preview_appearance_change,
    )
    preview_surface_emphasis: bpy.props.FloatProperty(
        name="Definición del límite",
        description="Refuerzo suave y no luminoso del nivel exacto que se convertirá a STL",
        default=2.0,
        min=0.0,
        max=8.0,
        soft_max=5.0,
        precision=1,
        update=on_preview_appearance_change,
    )
    dicom_surface_transparency: bpy.props.FloatProperty(
        name="Transparencia STL",
        description="Valor radiográfico interno fijo",
        default=DICOM_SURFACE_TRANSPARENCY_DEFAULT,
        min=0.0,
        max=95.0,
        soft_min=0.0,
        soft_max=95.0,
        subtype="PERCENTAGE",
        precision=0,
        options={"HIDDEN"},
        update=on_dicom_surface_transparency_change,
    )

    active_plane: bpy.props.EnumProperty(
        name="Plano",
        items=[
            ("AXIAL", "Axial", "Plano axial"),
            ("CORONAL", "Coronal", "Plano coronal"),
            ("SAGITTAL", "Sagital", "Plano sagital"),
        ],
        default="AXIAL",
        update=on_active_plane_change,
    )

    # Six independent controls per plane. Movement uses 0–100 % of the complete
    # DICOM extent along each root-local axis. Rotation is expressed in degrees.
    axial_move_x: bpy.props.FloatProperty(name="Mover X", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_axial_axis_control_change)
    axial_move_y: bpy.props.FloatProperty(name="Mover Y", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_axial_axis_control_change)
    axial_move_z: bpy.props.FloatProperty(name="Mover Z", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_axial_axis_control_change)
    axial_rotate_x: bpy.props.FloatProperty(name="Girar X", default=0.0, min=-180.0, max=180.0, precision=1, update=on_axial_axis_control_change)
    axial_rotate_y: bpy.props.FloatProperty(name="Girar Y", default=0.0, min=-180.0, max=180.0, precision=1, update=on_axial_axis_control_change)
    axial_rotate_z: bpy.props.FloatProperty(name="Girar Z", default=0.0, min=-180.0, max=180.0, precision=1, update=on_axial_axis_control_change)

    coronal_move_x: bpy.props.FloatProperty(name="Mover X", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_coronal_axis_control_change)
    coronal_move_y: bpy.props.FloatProperty(name="Mover Y", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_coronal_axis_control_change)
    coronal_move_z: bpy.props.FloatProperty(name="Mover Z", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_coronal_axis_control_change)
    coronal_rotate_x: bpy.props.FloatProperty(name="Girar X", default=0.0, min=-180.0, max=180.0, precision=1, update=on_coronal_axis_control_change)
    coronal_rotate_y: bpy.props.FloatProperty(name="Girar Y", default=0.0, min=-180.0, max=180.0, precision=1, update=on_coronal_axis_control_change)
    coronal_rotate_z: bpy.props.FloatProperty(name="Girar Z", default=0.0, min=-180.0, max=180.0, precision=1, update=on_coronal_axis_control_change)

    sagittal_move_x: bpy.props.FloatProperty(name="Mover X", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_sagittal_axis_control_change)
    sagittal_move_y: bpy.props.FloatProperty(name="Mover Y", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_sagittal_axis_control_change)
    sagittal_move_z: bpy.props.FloatProperty(name="Mover Z", default=50.0, min=0.0, max=100.0, subtype="PERCENTAGE", update=on_sagittal_axis_control_change)
    sagittal_rotate_x: bpy.props.FloatProperty(name="Girar X", default=0.0, min=-180.0, max=180.0, precision=1, update=on_sagittal_axis_control_change)
    sagittal_rotate_y: bpy.props.FloatProperty(name="Girar Y", default=0.0, min=-180.0, max=180.0, precision=1, update=on_sagittal_axis_control_change)
    sagittal_rotate_z: bpy.props.FloatProperty(name="Girar Z", default=0.0, min=-180.0, max=180.0, precision=1, update=on_sagittal_axis_control_change)

    # AI compute/resource profile. Cycles CUDA/OptiX preferences affect rendering,
    # not PyTorch; DSG selects CUDA directly and manages Blender headroom only
    # while the CBCT job is active.
    ai_device_detected: bpy.props.StringProperty(
        name="Dispositivo IA detectado",
        default="Pendiente · selecciona un DICOM",
    )
    ai_cuda_available: bpy.props.BoolProperty(
        name="CUDA detectada",
        default=False,
    )
    ai_gpu_name: bpy.props.StringProperty(
        name="GPU",
        default="",
    )
    ai_vram_total_gb: bpy.props.FloatProperty(
        name="VRAM total",
        default=0.0,
        min=0.0,
    )
    ai_vram_free_gb: bpy.props.FloatProperty(
        name="VRAM libre",
        default=0.0,
        min=0.0,
    )
    ai_device_preference: bpy.props.EnumProperty(
        name="Cálculo IA",
        description="AUTO usa CUDA si PyTorch la detecta y cae a CPU sólo cuando es necesario",
        items=[
            ("AUTO", "AUTO", "DSG elige CUDA FULL/HYBRID según VRAM y RAM"),
            ("CUDA", "CUDA", "Exige una GPU NVIDIA disponible para PyTorch CUDA"),
            ("CPU", "CPU", "Fuerza inferencia por CPU; es más lenta pero útil como compatibilidad"),
        ],
        default="AUTO",
    )
    ai_manage_blender_resources: bpy.props.BoolProperty(
        name="Gestionar recursos de Blender",
        description="Durante la IA pasa temporalmente Material Preview/Rendered a Solid para liberar VRAM; restaura la vista al terminar",
        default=True,
    )

    # Segmentation workflow state.
    segmentation_progress: bpy.props.FloatProperty(
        name="Progreso de segmentación",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        options={"HIDDEN"},
    )
    segmentation_progress_phase: bpy.props.StringProperty(
        name="Fase de segmentación",
        default="",
        options={"HIDDEN"},
    )
    segmentation_progress_detail: bpy.props.StringProperty(
        name="Detalle de segmentación",
        default="",
        options={"HIDDEN"},
    )
    segmentation_structure: bpy.props.EnumProperty(
        name="Segmentación DICOM",
        items=[
            ("BONE", "Hueso + dientes", "Segmentación semántica CBCT con el modelo DentalSegmentator validado en DSG 8.7"),
            ("TEETH", "Dientes", "UniversalLab: instancias dentales individuales y numeración FDI desde CBCT"),
            ("BONE_ONLY", "Hueso", "Clases óseas semánticas del DentalSegmentator, sin la clase dental"),
        ],
        default="BONE",
        update=on_automatic_structure_change,
    )
    auto_thresholds_ready: bpy.props.BoolProperty(default=False)
    auto_analysis_method: bpy.props.StringProperty(default="Sin analizar")
    auto_analysis_samples: bpy.props.IntProperty(default=0)
    auto_air_soft_threshold: bpy.props.FloatProperty(name="Aire / tejido", default=0.0, min=-100000.0, max=100000.0, precision=1)
    auto_soft_bone_threshold: bpy.props.FloatProperty(name="Tejido / hueso", default=0.0, min=-100000.0, max=100000.0, precision=1)
    auto_bone_teeth_threshold: bpy.props.FloatProperty(name="Soporte dental", description="Umbral bajo usado para conservar raíces conectadas a semillas dentales", default=0.0, min=-100000.0, max=100000.0, precision=1)
    auto_tooth_seed_threshold: bpy.props.FloatProperty(name="Semilla dental", description="Umbral alto de confianza que inicia la segmentación dental 3D", default=0.0, min=-100000.0, max=100000.0, precision=1)
    auto_metal_cutoff: bpy.props.FloatProperty(name="Corte metal", default=1.0, min=-100000.0, max=100000.0, precision=1)
    auto_robust_low: bpy.props.FloatProperty(default=0.0)
    auto_robust_high: bpy.props.FloatProperty(default=1.0)
    auto_class_overlap_percent: bpy.props.FloatProperty(
        name="Solapamiento entre tejidos",
        description="Amplía ligeramente el rango óseo para evitar cortes por variación de densidad del CBCT",
        default=8.0,
        min=0.0,
        max=40.0,
        subtype="PERCENTAGE",
        update=on_segmentation_threshold_preview_change,
    )
    auto_range_low: bpy.props.FloatProperty(
        name="Límite inferior",
        description="Umbral mostrado en tiempo real por la GPU y usado sin cambios al crear el STL",
        default=0.0,
        min=-100000.0,
        max=100000.0,
        soft_min=-2048.0,
        soft_max=8192.0,
        step=10,
        precision=1,
        update=on_segmentation_threshold_preview_change,
    )
    auto_range_high: bpy.props.FloatProperty(
        name="Límite superior",
        description="Corte superior para Dientes/Hueso; se actualiza en tiempo real",
        default=1.0,
        min=-100000.0,
        max=100000.0,
        precision=1,
        update=on_segmentation_threshold_preview_change,
    )
    paint_mode: bpy.props.EnumProperty(
        name="Herramienta",
        items=[
            ("ADD", "Añadir", "Dibujo positivo: pertenece a la estructura", "ADD", 0),
            ("EXCLUDE", "Excluir", "Dibujo negativo: no pertenece a la estructura", "REMOVE", 1),
            ("ERASE", "Borrar", "Borra dibujos positivos y negativos", "BRUSH_DATA", 2),
        ],
        default="ADD",
    )
    brush_radius_mm: bpy.props.FloatProperty(
        name="Radio del pincel", default=2.0, min=0.2, max=15.0, soft_max=6.0, precision=2
    )
    brush_depth_mm: bpy.props.FloatProperty(
        name="Profundidad", default=1.0, min=0.1, max=10.0, soft_max=3.0, precision=2
    )
    show_segmentation_overlay: bpy.props.BoolProperty(
        name="Mostrar máscara", default=True, update=on_segmentation_view_change
    )
    seg_density_tolerance: bpy.props.FloatProperty(
        name="Tolerancia de densidad", default=38.0, min=0.0, max=100.0, subtype="PERCENTAGE"
    )
    seg_edge_respect: bpy.props.FloatProperty(
        name="Respeto de bordes", default=55.0, min=0.0, max=100.0, subtype="PERCENTAGE"
    )
    seg_roi_margin_mm: bpy.props.FloatProperty(
        name="Margen de región", default=18.0, min=2.0, max=80.0, soft_max=35.0, precision=1
    )
    island_min_mm3: bpy.props.FloatProperty(options={"HIDDEN"}, 
        name="Eliminar islas menores de", default=5.0, min=0.0, max=5000.0, soft_max=500.0, precision=2
    )
    close_radius_mm: bpy.props.FloatProperty(
        name="Cerrar discontinuidades", default=0.6, min=0.1, max=5.0, soft_max=2.0, precision=2
    )
    correct_stl_x_180: bpy.props.BoolProperty(
        name="Corrección STL X obsoleta",
        description="Propiedad heredada; la malla usa el mismo marco que el volumen",
        default=False,
        options={"HIDDEN"},
    )

    correct_stl_z_180: bpy.props.BoolProperty(
        name="Corrección STL Z obsoleta",
        description="Propiedad heredada; la malla usa el mismo marco que el volumen",
        default=False,
        options={"HIDDEN"},
    )

    direct_stl_quality: bpy.props.EnumProperty(
        name="Calidad STL",
        description="Estado interno de compatibilidad; el STL final usa resolución nativa adaptativa",
        items=[
            ("384", "Compatibilidad", "Valor heredado de versiones anteriores"),
            ("640", "Alta definición", "Mínimo interno para superficies de máscara"),
        ],
        default="640",
        options={"HIDDEN"},
    )
    surface_smoothing_iterations: bpy.props.IntProperty(
        name="Suavizado", default=0, min=0, max=20, options={"HIDDEN"}
    )
    surface_reduction_percent: bpy.props.FloatProperty(
        name="Reducir polígonos", default=0.0, min=0.0, max=95.0, subtype="PERCENTAGE", options={"HIDDEN"}
    )
    positive_seed_count: bpy.props.IntProperty(default=0)
    negative_seed_count: bpy.props.IntProperty(default=0)
    learned_density_low: bpy.props.FloatProperty(default=0.0)
    learned_density_high: bpy.props.FloatProperty(default=0.0)
    segmented_voxel_count: bpy.props.IntProperty(default=0)
    segmented_volume_mm3: bpy.props.FloatProperty(default=0.0)
    segmentation_ready: bpy.props.BoolProperty(default=False)
    generated_surface_name: bpy.props.StringProperty(default="")
    surface_ready: bpy.props.BoolProperty(default=False)

    # Legacy geometric controls are retained internally for initial plane creation.
    axial_position: bpy.props.FloatProperty(
        name="Posición",
        default=50.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_plane_change,
    )
    axial_rotation_u: bpy.props.FloatProperty(
        name="Rotación X",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )
    axial_rotation_v: bpy.props.FloatProperty(
        name="Rotación Y",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )

    coronal_position: bpy.props.FloatProperty(
        name="Posición",
        default=50.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_plane_change,
    )
    coronal_rotation_u: bpy.props.FloatProperty(
        name="Rotación X",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )
    coronal_rotation_v: bpy.props.FloatProperty(
        name="Rotación Y",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )

    sagittal_position: bpy.props.FloatProperty(
        name="Posición",
        default=50.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
        update=on_plane_change,
    )
    sagittal_rotation_u: bpy.props.FloatProperty(
        name="Rotación X",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )
    sagittal_rotation_v: bpy.props.FloatProperty(
        name="Rotación Y",
        default=0.0,
        min=-90.0,
        max=90.0,
        precision=1,
        update=on_plane_change,
    )

# =============================================================================
# MODULE: realtime_mpr.py
# =============================================================================

