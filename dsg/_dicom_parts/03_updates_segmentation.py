import time

import bpy



def _request(
    *,
    plane_geometry: bool = False,
    plane_images: bool = False,
    visibility: bool = False,
    material: bool = False,
) -> None:
    if RUNTIME.update_lock or RUNTIME.undo_in_progress:
        return
    RUNTIME.requested_plane_geometry_refresh |= plane_geometry
    RUNTIME.requested_plane_image_refresh |= plane_images
    RUNTIME.requested_visibility_refresh |= visibility
    RUNTIME.requested_volume_material_refresh |= material
    RUNTIME.refresh_generation += 1
    RUNTIME.last_refresh_request_time = time.monotonic()

    if RUNTIME.timer_registered:
        return
    RUNTIME.timer_registered = True
    try:
        lifecycle.register_timer(_run_pending_refresh, first_interval=UI_REFRESH_DELAY_SECONDS)
    except Exception:
        RUNTIME.timer_registered = False


def _run_pending_refresh():
    if RUNTIME.undo_in_progress:
        RUNTIME.timer_registered = False
        return None
    elapsed = time.monotonic() - RUNTIME.last_refresh_request_time
    if elapsed < UI_REFRESH_DELAY_SECONDS:
        return max(0.02, UI_REFRESH_DELAY_SECONDS - elapsed)

    RUNTIME.timer_registered = False
    geometry = RUNTIME.requested_plane_geometry_refresh
    images = RUNTIME.requested_plane_image_refresh
    visibility = RUNTIME.requested_visibility_refresh
    material = RUNTIME.requested_volume_material_refresh
    RUNTIME.requested_plane_geometry_refresh = False
    RUNTIME.requested_plane_image_refresh = False
    RUNTIME.requested_visibility_refresh = False
    RUNTIME.requested_volume_material_refresh = False

    try:
        scene = bpy.context.scene
        props = getattr(scene, "dicom_wizard_pro", None)
        if props is None or not props.volume_loaded or not RUNTIME.is_loaded():
            return None

        update_density_labels(props)
        if material:
            refresh_volume_material(bpy.context)
        if geometry:
            refresh_planes(bpy.context)
        elif images:
            refresh_plane_images_from_objects(bpy.context)
        elif visibility:
            update_visibility(bpy.context)
        force_ui_redraw()
    except Exception as exc:
        try:
            bpy.context.scene.dicom_wizard_pro.status = f"Error al actualizar: {exc}"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        print("DICOM Wizard Pro refresh error:", repr(exc))
    return None


def on_threshold_change(self, context) -> None:
    """Update the GPU shader immediately; defer expensive MPR pixel rebuilding."""
    if RUNTIME.update_lock or RUNTIME.undo_in_progress:
        return
    try:
        if RUNTIME.is_loaded() and bool(getattr(self, "volume_loaded", False)):
            update_density_labels(self)
            refresh_volume_material(context)
            force_ui_redraw()
            # MPR images are secondary. They refresh only after the slider has
            # stopped, while the 3D OpenVDB preview remains fully interactive.
            if bool(getattr(self, "show_planes", False)):
                _request(plane_images=True)
            # SIMPLE route intentionally stays volume-only while the slider
            # moves. Native full-resolution STL extraction starts only on the
            # explicit confirmation action, keeping Blender responsive.
    except Exception as exc:
        print("DICOM instant threshold preview warning:", repr(exc))


def on_segmentation_threshold_preview_change(self, context) -> None:
    """Drive the STL preview with one cheap shader value and mark masks stale."""
    if RUNTIME.update_lock or RUNTIME.undo_in_progress:
        return
    try:
        state = get_segmentation_state(str(getattr(self, "segmentation_structure", "TEETH")))
        state["stale"] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if RUNTIME.is_loaded() and bool(getattr(self, "volume_loaded", False)):
            refresh_volume_material(context)
            if int(getattr(self, "step", 1)) == 3 and _auto_solid_preview_enabled(self):
                schedule_surface_preview(context)
            force_ui_redraw()
    except Exception as exc:
        print("DICOM STL preview threshold warning:", repr(exc))


def on_plane_change(self, context) -> None:
    # Sidebar position/angle controls intentionally rebuild the selected plane.
    _request(plane_geometry=True)


def on_active_plane_change(self, context) -> None:
    _request(visibility=True)
    if getattr(self, "step", 1) >= 3:
        _request(plane_images=True)
        try:
            sync_segmentation_properties(self)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def on_visibility_change(self, context) -> None:
    _request(visibility=True)


def on_opacity_change(self, context) -> None:
    if RUNTIME.update_lock or RUNTIME.undo_in_progress:
        return
    try:
        if RUNTIME.is_loaded() and bool(getattr(self, "volume_loaded", False)):
            refresh_volume_material(context)
            force_ui_redraw()
    except Exception as exc:
        print("DICOM instant opacity preview warning:", repr(exc))


def on_preview_appearance_change(self, context) -> None:
    """Adjust edge width/contrast through scalar sockets only."""
    if RUNTIME.update_lock or RUNTIME.undo_in_progress:
        return
    try:
        if RUNTIME.is_loaded() and bool(getattr(self, "volume_loaded", False)):
            refresh_volume_material(context)
            force_ui_redraw()
    except Exception as exc:
        print("DICOM preview appearance warning:", repr(exc))


def on_orientation_display_change(self, context) -> None:
    """Reapply the DICOM root orientation after changing display correction."""
    root = bpy.data.objects.get(ROOT_NAME)
    if root is not None:
        apply_patient_orientation(root)
        force_ui_redraw()


def _axis_control_names(orientation: str) -> tuple[str, str, str, str, str, str]:
    """Return the six RNA property names for one MPR plane."""
    prefix = orientation.lower()
    return (
        f"{prefix}_move_x",
        f"{prefix}_move_y",
        f"{prefix}_move_z",
        f"{prefix}_rotate_x",
        f"{prefix}_rotate_y",
        f"{prefix}_rotate_z",
    )


def _axis_control_values(props, orientation: str) -> tuple[float, float, float, float, float, float]:
    names = _axis_control_names(orientation)
    return tuple(float(getattr(props, name)) for name in names)


def _volume_extents_xyz_mm() -> tuple[float, float, float]:
    """Return physical DICOM extents in root-local X/Y/Z millimetres."""
    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    return (
        max(0.0, (x_count - 1) * x_spacing),
        max(0.0, (y_count - 1) * y_spacing),
        max(0.0, (z_count - 1) * z_spacing),
    )


def _orthonormal_rotation_matrix(matrix):
    """Return the nearest proper 3x3 rotation matrix."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    candidate = np.asarray(matrix, dtype=np.float64).reshape((3, 3))
    u, _singular_values, vh = np.linalg.svd(candidate)
    rotation = u @ vh
    if float(np.linalg.det(rotation)) < 0.0:
        u[:, -1] *= -1.0
        rotation = u @ vh
    return rotation


def _mpr_alignment_matrix(props):
    """Read the shared anatomical MPR frame stored in the scene."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    raw = props.get("mpr_alignment_matrix", None)
    try:
        if raw is not None and len(raw) == 9:
            return _orthonormal_rotation_matrix(list(raw))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    identity = np.eye(3, dtype=np.float64)
    props["mpr_alignment_matrix"] = [float(value) for value in identity.ravel()]
    return identity


def _store_mpr_alignment_matrix(props, matrix) -> None:
    rotation = _orthonormal_rotation_matrix(matrix)
    props["mpr_alignment_matrix"] = [float(value) for value in rotation.ravel()]


def _base_plane_frame(orientation: str):
    """Return columns [U, V, normal] for an unrotated MPR plane."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    axis_u, axis_v, normal = plane_basis(orientation, 0.0, 0.0)
    return np.column_stack((axis_u, axis_v, normal))


def _refresh_all_aligned_planes(context: bpy.types.Context) -> None:
    """Apply the shared frame and reconstruct all three orthogonal cuts."""
    for orientation in PLANE_SPECS:
        _apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
    for orientation in PLANE_SPECS:
        refresh_plane_image_from_object(context, orientation, max_axis=MAX_MPR_AXIS)
    update_visibility(context)

    area = getattr(context, "area", None)
    if area is not None and area.type == "VIEW_3D":
        try:
            if getattr(area.spaces.active, "region_quadviews", None):
                configure_radiographic_quad_view(context, area)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    force_ui_redraw()


def _apply_axis_controls_to_plane(
    context: bpy.types.Context,
    orientation: str,
    *,
    schedule_refresh: bool = True,
) -> None:
    """Apply six sliders to the selected plane in DICOM-local coordinates.

    Move X/Y/Z are percentages across the complete physical volume. Rotation
    X/Y/Z are degrees around the DICOM-local axes. The plane image is then
    resampled from the 3D voxel array, rather than merely rotating a texture.
    """
    if RUNTIME.update_lock or not RUNTIME.is_loaded():
        return

    orientation = orientation.upper()
    spec = PLANE_SPECS.get(orientation)
    if spec is None:
        return
    obj = bpy.data.objects.get(spec["object"])
    if obj is None:
        return

    props = context.scene.dicom_wizard_pro
    move_x, move_y, move_z, rotate_x, rotate_y, rotate_z = _axis_control_values(
        props, orientation
    )

    extent_x, extent_y, extent_z = _volume_extents_xyz_mm()

    np = load_numpy()
    if np is None:
        return

    # The three cuts share one anatomical frame. Per-plane Euler controls are
    # applied inside that frame, rather than independently redefining what
    # axial/coronal/sagittal mean.
    alignment = _mpr_alignment_matrix(props)
    center_unaligned = np.asarray((
        -0.5 * extent_x + clamp(move_x, 0.0, 100.0) * 0.01 * extent_x,
        -0.5 * extent_y + clamp(move_y, 0.0, 100.0) * 0.01 * extent_y,
        -0.5 * extent_z + clamp(move_z, 0.0, 100.0) * 0.01 * extent_z,
    ), dtype=np.float64)
    center = alignment @ center_unaligned

    base_u, base_v, base_normal = plane_basis(orientation, 0.0, 0.0)
    local_rotation = (
        _rotation_matrix((0.0, 0.0, 1.0), rotate_z)
        @ _rotation_matrix((0.0, 1.0, 0.0), rotate_y)
        @ _rotation_matrix((1.0, 0.0, 0.0), rotate_x)
    )
    rotate_matrix = alignment @ local_rotation
    axis_u = _normalize(rotate_matrix @ base_u, alignment @ base_u)
    axis_v = rotate_matrix @ base_v
    axis_v = _normalize(axis_v - axis_u * float(np.dot(axis_v, axis_u)), alignment @ base_v)
    normal = _normalize(np.cross(axis_u, axis_v), rotate_matrix @ base_normal)

    matrix = Matrix((
        (float(axis_u[0]), float(axis_v[0]), float(normal[0]), float(center[0])),
        (float(axis_u[1]), float(axis_v[1]), float(normal[1]), float(center[1])),
        (float(axis_u[2]), float(axis_v[2]), float(normal[2]), float(center[2])),
        (0.0, 0.0, 0.0, 1.0),
    ))

    RUNTIME.transform_handler_lock = True
    try:
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_local = matrix
        RUNTIME.plane_matrix_cache[orientation] = _matrix_basis_signature(obj)
    finally:
        RUNTIME.transform_handler_lock = False

    if not schedule_refresh:
        return

    if bool(props.get("safe_mpr_active", False)):
        if orientation in {"AXIAL", "SAGITTAL"}:
            _safe_review_request_realtime_refresh(orientation)
        return

    if getattr(props, "realtime_mpr", True):
        _queue_realtime_transform(orientation)
    else:
        _request(plane_images=True)


def on_axial_axis_control_change(self, context) -> None:
    _apply_axis_controls_to_plane(context, "AXIAL")


def on_coronal_axis_control_change(self, context) -> None:
    _apply_axis_controls_to_plane(context, "CORONAL")


def on_sagittal_axis_control_change(self, context) -> None:
    _apply_axis_controls_to_plane(context, "SAGITTAL")


def _prepare_minimal_orthogonal_mpr(context: bpy.types.Context) -> None:
    """Initialise the review planes in one shared anatomical frame.

    The Z and X planes start orthogonal and centred. During review the user may
    translate each plane along its normal and tilt it around its two in-plane
    axes. The radiographic image is resampled after every transform.
    """
    if not RUNTIME.is_loaded():
        return
    props = context.scene.dicom_wizard_pro
    RUNTIME.update_lock = True
    try:
        # Keep only the clinically meaningful normal-axis value for each cut.
        props.axial_move_x = 50.0
        props.axial_move_y = 50.0
        props.coronal_move_x = 50.0
        props.coronal_move_z = 50.0
        props.sagittal_move_y = 50.0
        props.sagittal_move_z = 50.0
        for orientation in ("axial", "coronal", "sagittal"):
            setattr(props, f"{orientation}_rotate_x", 0.0)
            setattr(props, f"{orientation}_rotate_y", 0.0)
            setattr(props, f"{orientation}_rotate_z", 0.0)
    finally:
        RUNTIME.update_lock = False

    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        _apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
    for orientation in ("AXIAL", "CORONAL", "SAGITTAL"):
        refresh_plane_image_from_object(context, orientation, max_axis=MAX_MPR_AXIS)
    update_visibility(context)
    force_ui_redraw()


# =============================================================================
# MODULE: segmentation.py
# =============================================================================

import time

import bpy
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils


def _new_segmentation_state() -> dict:
    return {
        "positive": set(),
        "negative": set(),
        "mask": None,
        "origin_zyx": (0, 0, 0),
        "learned_low": 0.0,
        "learned_high": 0.0,
        "stale": True,
        "surface_name": "",
    }


def get_segmentation_state(structure: str) -> dict:
    structure = str(structure).upper()
    if structure not in SEGMENTATION_STRUCTURES:
        structure = "BONE"
    state = RUNTIME.segmentations.get(structure)
    if state is None:
        state = _new_segmentation_state()
        RUNTIME.segmentations[structure] = state
    return state


def _linear_indices_from_zyx(z, y, x):
    np = load_numpy()
    _z_count, y_count, x_count = RUNTIME.dims_zyx
    return ((np.asarray(z, dtype=np.int64) * y_count + np.asarray(y, dtype=np.int64)) * x_count + np.asarray(x, dtype=np.int64))


def _zyx_from_linear(indices):
    np = load_numpy()
    _z_count, y_count, x_count = RUNTIME.dims_zyx
    indices = np.asarray(indices, dtype=np.int64)
    z = indices // (y_count * x_count)
    remainder = indices % (y_count * x_count)
    y = remainder // x_count
    x = remainder % x_count
    return z, y, x


def _seed_array(values):
    """Return segmentation seed indices as a flat int64 NumPy array.

    Segmentation state stores positive/negative seeds as Python sets.  The MPR
    overlay uses ``numpy.isin`` and therefore needs an ndarray.  Older DSG
    builds referenced this helper after it had been accidentally removed,
    producing ``NameError: _seed_array is not defined`` during UI/update
    refresh.  Keep the conversion local, allocation-light and deterministic.
    """
    np = load_numpy()
    if np is None:
        return None
    if values is None:
        return np.empty((0,), dtype=np.int64)
    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=np.int64).reshape(-1)
    try:
        count = len(values)
    except TypeError:
        values = tuple(values)
        count = len(values)
    if count == 0:
        return np.empty((0,), dtype=np.int64)
    return np.fromiter(values, dtype=np.int64, count=count)


def _plane_sampling_points(center, axis_u, axis_v, width_mm, height_mm, output_width, output_height):
    np = load_numpy()
    u_coords = np.linspace(-0.5 * width_mm, 0.5 * width_mm, output_width, dtype=np.float32)
    v_coords = np.linspace(-0.5 * height_mm, 0.5 * height_mm, output_height, dtype=np.float32)
    uu, vv = np.meshgrid(u_coords, v_coords, indexing="xy")
    return (
        np.asarray(center, dtype=np.float32)[None, None, :]
        + uu[..., None] * np.asarray(axis_u, dtype=np.float32)[None, None, :]
        + vv[..., None] * np.asarray(axis_v, dtype=np.float32)[None, None, :]
    )


def _nearest_voxel_indices(points_xyz_mm):
    np = load_numpy()
    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    x_float = points_xyz_mm[..., 0] / x_spacing + 0.5 * (x_count - 1)
    y_float = points_xyz_mm[..., 1] / y_spacing + 0.5 * (y_count - 1)
    z_float = points_xyz_mm[..., 2] / z_spacing + 0.5 * (z_count - 1)
    valid = (
        (x_float >= 0.0) & (x_float <= x_count - 1)
        & (y_float >= 0.0) & (y_float <= y_count - 1)
        & (z_float >= 0.0) & (z_float <= z_count - 1)
    )
    x = np.rint(np.clip(x_float, 0, x_count - 1)).astype(np.int32)
    y = np.rint(np.clip(y_float, 0, y_count - 1)).astype(np.int32)
    z = np.rint(np.clip(z_float, 0, z_count - 1)).astype(np.int32)
    return z, y, x, valid


def _sample_cropped_mask(state: dict, z, y, x, valid):
    np = load_numpy()
    result = np.zeros(z.shape, dtype=bool)
    mask = state.get("mask")
    if mask is None or mask.size == 0:
        return result
    z0, y0, x0 = state.get("origin_zyx", (0, 0, 0))
    lz, ly, lx = z - z0, y - y0, x - x0
    inside = (
        valid
        & (lz >= 0) & (lz < mask.shape[0])
        & (ly >= 0) & (ly < mask.shape[1])
        & (lx >= 0) & (lx < mask.shape[2])
    )
    if inside.any():
        result[inside] = mask[lz[inside], ly[inside], lx[inside]]
    return result


def compose_segmentation_overlay(normalized, center, axis_u, axis_v, width_mm, height_mm, output_width, output_height, props):
    """Blend segmentation, positive seeds, and exclusion seeds over an MPR."""
    np = load_numpy()
    if (
        np is None
        or not getattr(props, "show_segmentation_overlay", False)
        or getattr(props, "step", 1) < 3
        or not RUNTIME.is_loaded()
    ):
        return normalized

    state = get_segmentation_state(props.segmentation_structure)
    if not state["positive"] and not state["negative"] and state.get("mask") is None:
        return normalized

    points = _plane_sampling_points(center, axis_u, axis_v, width_mm, height_mm, output_width, output_height)
    z, y, x, valid = _nearest_voxel_indices(points)
    linear = _linear_indices_from_zyx(z, y, x)

    positive_values = _seed_array(state["positive"])
    negative_values = _seed_array(state["negative"])
    positive = np.isin(linear, positive_values, assume_unique=False) & valid if positive_values.size else np.zeros(valid.shape, bool)
    negative = np.isin(linear, negative_values, assume_unique=False) & valid if negative_values.size else np.zeros(valid.shape, bool)
    segmented = _sample_cropped_mask(state, z, y, x, valid)

    rgb = np.repeat(np.asarray(normalized, dtype=np.float32)[..., None], 3, axis=2)
    color = np.asarray(SEGMENTATION_STRUCTURES[props.segmentation_structure]["color"], dtype=np.float32)
    exclude_color = np.asarray(SEGMENTATION_EXCLUDE_COLOR, dtype=np.float32)
    if segmented.any():
        rgb[segmented] = 0.55 * rgb[segmented] + 0.45 * color
    if positive.any():
        rgb[positive] = 0.15 * rgb[positive] + 0.85 * color
    if negative.any():
        rgb[negative] = 0.10 * rgb[negative] + 0.90 * exclude_color
    return np.clip(rgb, 0.0, 1.0)


def sync_segmentation_properties(props) -> None:
    state = get_segmentation_state(props.segmentation_structure)
    props.positive_seed_count = len(state["positive"])
    props.negative_seed_count = len(state["negative"])
    props.learned_density_low = float(state.get("learned_low", 0.0))
    props.learned_density_high = float(state.get("learned_high", 0.0))
    mask = state.get("mask")
    count = int(mask.sum()) if mask is not None else 0
    voxel_volume = float(RUNTIME.spacing_zyx_mm[0] * RUNTIME.spacing_zyx_mm[1] * RUNTIME.spacing_zyx_mm[2]) if RUNTIME.is_loaded() else 0.0
    props.segmented_voxel_count = count
    props.segmented_volume_mm3 = count * voxel_volume
    props.segmentation_ready = bool(mask is not None and count > 0 and not state.get("stale", False))
    props.generated_surface_name = str(state.get("surface_name", ""))
    props.surface_ready = bool(props.generated_surface_name and bpy.data.objects.get(props.generated_surface_name))


def _segmentation_refreshes_all_mpr_planes(props) -> bool:
    """Refresh the radiographic buffers required by the active review mode."""
    return bool(
        getattr(props, "show_all_planes", False)
        or props.get("safe_mpr_active", False)
    )


def _refresh_segmentation_views(
    context,
    *,
    max_axis: int = SEGMENTATION_PREVIEW_MAX_AXIS,
) -> None:
    props = context.scene.dicom_wizard_pro
    refresh_plane_images_from_objects(
        context,
        all_planes=_segmentation_refreshes_all_mpr_planes(props),
        max_axis=max_axis,
    )
    force_ui_redraw()


def on_segmentation_view_change(self, context) -> None:
    props = getattr(context.scene, "dicom_wizard_pro", None)
    if props is None or not props.volume_loaded:
        return
    sync_segmentation_properties(props)
    try:
        refresh_volume_material(context)
        # The default STL workflow is volume-only. Avoid rebuilding three MPR
        # textures when no slice is visible; the user can request the advanced
        # mask workflow explicitly when those images are needed.
        if not bool(getattr(props, "show_planes", False)):
            force_ui_redraw()
            return
        _refresh_segmentation_views(context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS)
    except Exception as exc:
        props.status = f"No se pudo actualizar la superposición: {exc}"




def _mouse_hit_active_plane(context, event, orientation: str):
    obj = bpy.data.objects.get(PLANE_SPECS[orientation]["object"])
    root = bpy.data.objects.get(ROOT_NAME)
    if obj is None or root is None or context.region is None or context.space_data is None:
        return None
    if context.area.type != "VIEW_3D":
        return None

    coord = (event.mouse_region_x, event.mouse_region_y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(context.region, context.space_data.region_3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(context.region, context.space_data.region_3d, coord)
    plane_point = obj.matrix_world.translation
    plane_normal = (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    denominator = plane_normal.dot(ray_direction)
    if abs(denominator) < 1e-8:
        return None
    distance = plane_normal.dot(plane_point - ray_origin) / denominator
    if distance < 0.0:
        return None
    hit_world = ray_origin + ray_direction * distance
    hit_plane = obj.matrix_world.inverted_safe() @ hit_world
    width = float(obj.get("dicom_plane_width_mm", max(obj.dimensions.x, 1.0)))
    height = float(obj.get("dicom_plane_height_mm", max(obj.dimensions.y, 1.0)))
    if abs(hit_plane.x) > width * 0.5 or abs(hit_plane.y) > height * 0.5:
        return None
    return root.matrix_world.inverted_safe() @ hit_world


def clear_segmentation_drawings(props, structure: str, *, clear_mask: bool = True) -> None:
    state = get_segmentation_state(structure)
    state["positive"].clear()
    state["negative"].clear()
    if clear_mask:
        state["mask"] = None
        state["origin_zyx"] = (0, 0, 0)
        state["learned_low"] = 0.0
        state["learned_high"] = 0.0
    state["stale"] = True
    sync_segmentation_properties(props)




def _scaled_roi(bounds_zyx):
    np = load_numpy()
    z0, z1, y0, y1, x0, x1 = bounds_zyx
    raw = RUNTIME.volume[z0:z1, y0:y1, x0:x1].astype(np.float32, copy=False)
    slopes = RUNTIME.slopes[z0:z1, None, None]
    intercepts = RUNTIME.intercepts[z0:z1, None, None]
    return raw * slopes + intercepts






def _occupied_bbox_3d(mask, *, margin: int = 0):
    """Return an exact ``(min_zyx, max_zyx_exclusive)`` occupied bounding box.

    The implementation deliberately avoids ``np.argwhere(mask)``: storing one
    int64 XYZ triplet per occupied voxel can consume more RAM than the mask
    itself. Axis occupancy projections are exact and require only O(Z+Y+X)
    temporary storage.
    """
    np = load_numpy()
    array = np.asarray(mask)
    if array.ndim != 3:
        raise ValueError(f"La máscara debe ser 3D, no {array.ndim}D")
    z = np.flatnonzero(array.any(axis=(1, 2)))
    if z.size == 0:
        return None
    y = np.flatnonzero(array.any(axis=(0, 2)))
    x = np.flatnonzero(array.any(axis=(0, 1)))
    pad = max(0, int(margin))
    minimum = np.asarray((z[0], y[0], x[0]), dtype=np.int64)
    maximum = np.asarray((z[-1] + 1, y[-1] + 1, x[-1] + 1), dtype=np.int64)
    if pad:
        minimum = np.maximum(minimum - pad, 0)
        maximum = np.minimum(maximum + pad, np.asarray(array.shape, dtype=np.int64))
    return minimum, maximum


def _compact_mask(mask, origin_zyx):
    """Crop a 3D mask to its occupied bounding box without coordinate spikes."""
    np = load_numpy()
    if mask is None:
        return None, (0, 0, 0)
    array = np.asarray(mask)
    bbox = _occupied_bbox_3d(array)
    if bbox is None:
        return None, (0, 0, 0)
    minimum, maximum = bbox
    cropped = np.ascontiguousarray(
        array[
            int(minimum[0]):int(maximum[0]),
            int(minimum[1]):int(maximum[1]),
            int(minimum[2]):int(maximum[2]),
        ]
    )
    origin = tuple(int(origin_zyx[i] + minimum[i]) for i in range(3))
    return cropped, origin





def _sample_density_for_automatic_analysis(max_samples: int = 2_000_000):
    """Return a robust, decimated sample of the complete CBCT density volume.

    The raw volume remains in its native dtype. Only the sampled voxels are
    converted to float32, which avoids duplicating a 501³ scan in memory.
    """
    np = load_numpy()
    if np is None or not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")

    z_count, y_count, x_count = RUNTIME.dims_zyx
    total = max(1, z_count * y_count * x_count)
    stride = max(1, int(np.ceil((total / max(1, max_samples)) ** (1.0 / 3.0))))
    z_indices = np.arange(0, z_count, stride, dtype=np.int32)
    raw = RUNTIME.volume[::stride, ::stride, ::stride].astype(np.float32, copy=False)
    sample = raw * RUNTIME.slopes[z_indices, None, None] + RUNTIME.intercepts[z_indices, None, None]
    sample = sample.ravel()
    sample = sample[np.isfinite(sample)]
    if sample.size > max_samples:
        sample = sample[::max(1, sample.size // max_samples)][:max_samples]
    if sample.size < 1024:
        raise RuntimeError("El DICOM no contiene suficientes valores válidos para analizar")
    return sample.astype(np.float32, copy=False)


def _weighted_histogram_kmeans_thresholds(sample, classes: int = 4):
    """Dependency-free 1D histogram clustering used if Multi-Otsu is unavailable."""
    np = load_numpy()
    robust_low, robust_high = np.percentile(sample, (0.2, 99.8))
    if not np.isfinite(robust_low) or not np.isfinite(robust_high) or robust_high <= robust_low:
        robust_low = float(np.min(sample))
        robust_high = float(np.max(sample))
    clipped = np.clip(sample, robust_low, robust_high)
    hist, edges = np.histogram(clipped, bins=512, range=(robust_low, robust_high))
    centers = 0.5 * (edges[:-1] + edges[1:])
    weights = hist.astype(np.float64)
    nonzero = weights > 0
    if nonzero.sum() < classes:
        return np.quantile(clipped, (0.20, 0.58, 0.84)).astype(np.float64)

    cumulative = np.cumsum(weights)
    total = cumulative[-1]
    initial_quantiles = np.linspace(0.08, 0.92, classes)
    centroids = np.asarray(
        [centers[min(len(centers) - 1, int(np.searchsorted(cumulative, q * total)))] for q in initial_quantiles],
        dtype=np.float64,
    )
    for _ in range(64):
        distances = np.abs(centers[:, None] - centroids[None, :])
        labels = np.argmin(distances, axis=1)
        new_centroids = centroids.copy()
        for index in range(classes):
            selected = labels == index
            selected_weight = weights[selected].sum()
            if selected_weight > 0:
                new_centroids[index] = np.sum(centers[selected] * weights[selected]) / selected_weight
        new_centroids.sort()
        if np.allclose(new_centroids, centroids, rtol=0.0, atol=max((robust_high - robust_low) * 1e-6, 1e-5)):
            centroids = new_centroids
            break
        centroids = new_centroids
    return 0.5 * (centroids[:-1] + centroids[1:])


def _weighted_otsu_threshold(values, bins: int = 512) -> float:
    """Dependency-free one-dimensional Otsu threshold on a robust histogram."""
    np = load_numpy()
    data = np.asarray(values, dtype=np.float32)
    data = data[np.isfinite(data)]
    if data.size < 32:
        return float(np.median(data)) if data.size else 0.0
    low, high = (float(v) for v in np.percentile(data, (0.2, 99.8)))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return float(np.median(data))
    hist, edges = np.histogram(np.clip(data, low, high), bins=max(64, int(bins)), range=(low, high))
    centers = 0.5 * (edges[:-1] + edges[1:])
    weights = hist.astype(np.float64)
    total_weight = float(weights.sum())
    if total_weight <= 0.0:
        return float(np.median(data))
    cumulative_weight = np.cumsum(weights)
    cumulative_mean = np.cumsum(weights * centers)
    total_mean = float(cumulative_mean[-1])
    denominator = cumulative_weight * (total_weight - cumulative_weight)
    score = np.full_like(denominator, -np.inf, dtype=np.float64)
    valid = denominator > 0.0
    numerator = (total_mean * cumulative_weight - cumulative_mean * total_weight) ** 2
    score[valid] = numerator[valid] / denominator[valid]
    index = int(np.argmax(score[:-1])) if score.size > 1 else 0
    return float(centers[index])


def _otsu_split_quality(values, threshold: float) -> tuple[float, float]:
    """Return minority fraction and normalized mean separation for an Otsu split."""
    np = load_numpy()
    data = np.asarray(values, dtype=np.float32)
    data = data[np.isfinite(data)]
    lower = data[data <= float(threshold)]
    upper = data[data > float(threshold)]
    if lower.size < 64 or upper.size < 64 or data.size == 0:
        return 0.0, 0.0
    minority_fraction = float(min(lower.size, upper.size) / data.size)
    pooled = float(np.sqrt(float(np.var(lower)) + float(np.var(upper))))
    separation = abs(float(np.mean(upper)) - float(np.mean(lower))) / max(pooled, 1e-6)
    return minority_fraction, separation


def _estimate_metal_cutoff(sample, soft_bone_threshold: float, robust_high: float) -> float:
    """Detect a separated extreme radiopaque tail without clipping normal enamel."""
    np = load_numpy()
    dense = sample[(sample > float(soft_bone_threshold)) & np.isfinite(sample)]
    if dense.size < 4096:
        return float(robust_high)
    quantile_levels = np.linspace(0.90, 0.9995, 180, dtype=np.float64)
    quantiles = np.quantile(dense, quantile_levels)
    gaps = np.diff(quantiles)
    if gaps.size < 8:
        return float(robust_high)
    baseline = float(np.median(gaps[: max(8, int(0.80 * gaps.size))]))
    baseline = max(
        baseline,
        max(float(robust_high) - float(soft_bone_threshold), 1.0) * 1e-4,
    )
    candidates = np.flatnonzero(
        (quantile_levels[1:] >= 0.985) & (gaps >= 6.0 * baseline)
    )
    if candidates.size == 0:
        return float(robust_high)
    index = int(candidates[0])
    cutoff = float(0.5 * (quantiles[index] + quantiles[index + 1]))
    return min(
        float(robust_high),
        max(float(soft_bone_threshold) + 1.0, cutoff),
    )


def _dense_tissue_valley_threshold(sample, soft_bone_threshold: float, robust_high: float):
    """Estimate the scan-specific valley separating bone from dental tissue."""
    np = load_numpy()
    dense = sample[
        (sample > float(soft_bone_threshold))
        & (sample <= float(robust_high))
        & np.isfinite(sample)
    ]
    if dense.size < 2048:
        return None

    dense_low = float(np.percentile(dense, 1.0))
    dense_high = float(np.percentile(dense, 99.2))
    if (
        not np.isfinite(dense_low)
        or not np.isfinite(dense_high)
        or dense_high <= dense_low
    ):
        return None

    hist, edges = np.histogram(
        np.clip(dense, dense_low, dense_high),
        bins=512,
        range=(dense_low, dense_high),
    )
    smooth = np.convolve(
        hist.astype(np.float64),
        np.ones(11, dtype=np.float64) / 11.0,
        mode="same",
    )
    if float(smooth.max()) <= 0.0:
        return None

    peak_indices = np.flatnonzero(
        (smooth[1:-1] >= smooth[:-2]) & (smooth[1:-1] >= smooth[2:])
    ) + 1
    peak_indices = peak_indices[
        (peak_indices > 12) & (peak_indices < len(smooth) - 12)
    ]
    if peak_indices.size < 2:
        return None

    order = peak_indices[np.argsort(smooth[peak_indices])[::-1]]
    candidates = order[: min(12, order.size)]
    best = None
    minimum_separation = max(18, int(0.07 * len(smooth)))
    for first in candidates:
        for second in candidates:
            low_peak, high_peak = sorted((int(first), int(second)))
            if high_peak - low_peak < minimum_separation:
                continue
            valley_local = (
                int(np.argmin(smooth[low_peak : high_peak + 1])) + low_peak
            )
            valley_height = float(smooth[valley_local])
            peak_height = min(
                float(smooth[low_peak]), float(smooth[high_peak])
            )
            if peak_height <= 0.0:
                continue
            depth = 1.0 - valley_height / peak_height
            separation = (high_peak - low_peak) / float(len(smooth))
            score = depth + 0.35 * separation
            if depth >= 0.12 and (best is None or score > best[0]):
                best = (score, valley_local)

    if best is None:
        return None
    valley_index = best[1]
    return float(0.5 * (edges[valley_index] + edges[valley_index + 1]))


def _automatic_range_for_structure(props, structure: str) -> tuple[float, float]:
    """Return the adaptive density interval for the selected DICOM anatomy.

    BONE is intentionally the classic combined mineralized surface (bone +
    teeth). TEETH and BONE_ONLY use the learned dense-tissue split so they are
    not just three names for the same isosurface.
    """
    structure = str(structure).upper()
    air_soft = float(props.auto_air_soft_threshold)
    soft_bone = float(props.auto_soft_bone_threshold)
    bone_teeth = float(props.auto_bone_teeth_threshold)
    robust_high = float(props.auto_robust_high)
    metal_cutoff = float(getattr(props, "auto_metal_cutoff", robust_high))
    overlap = clamp(
        float(props.auto_class_overlap_percent), 0.0, 40.0
    ) / 100.0

    if structure == "SOFT_TISSUE":
        span = max(soft_bone - air_soft, 1.0)
        return (
            air_soft - span * overlap * 0.25,
            soft_bone + span * overlap,
        )

    dense_gap = max(bone_teeth - soft_bone, 1.0)
    if structure == "TEETH":
        # This is the low/support threshold for 3D hysteresis, not a hard dental
        # boundary. A tiny overlap improves root continuity; only components
        # connected to the separate high-density seed are finally accepted.
        lower = bone_teeth - dense_gap * overlap * 0.10
        upper = max(lower + 1.0, metal_cutoff)
        return lower, upper

    if structure == "BONE_ONLY":
        lower_span = max(soft_bone - air_soft, 1.0)
        lower = soft_bone - lower_span * overlap * 0.20
        # Display the learned dental separator for review. The final bone-only
        # mask is mineralised tissue MINUS the 3D dental mask, so dense cortex is
        # preserved instead of being clipped by this upper value.
        upper = bone_teeth
        return lower, max(lower + 1.0, upper)

    # Classic combined mode: everything mineralized above the bone threshold.
    lower_span = max(soft_bone - air_soft, 1.0)
    lower = soft_bone - lower_span * overlap * 0.20
    return lower, robust_high


def sync_automatic_range_from_structure(props) -> None:
    if not getattr(props, "auto_thresholds_ready", False):
        return
    low, high = _automatic_range_for_structure(
        props, props.segmentation_structure
    )
    props.auto_range_low = float(min(low, high))
    props.auto_range_high = float(max(low, high))


def on_automatic_structure_change(self, context) -> None:
    if getattr(self, "auto_thresholds_ready", False):
        sync_automatic_range_from_structure(self)
    try:
        state = get_segmentation_state(
            str(getattr(self, "segmentation_structure", "BONE"))
        )
        state["stale"] = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    on_segmentation_view_change(self, context)
    if int(getattr(self, "step", 1)) == 3:
        # The shader gives immediate threshold feedback and the solid preview
        # is rebuilt by DSG's bundled NumPy voxel-surface engine.
        schedule_surface_preview(context, immediate=True)


def analyze_automatic_tissue_thresholds(context) -> tuple[float, float, float]:
    """Learn scanner-adaptive mineral, tooth-support and tooth-seed thresholds.

    DSG deliberately does not assume Hounsfield Units for CBCT.  The first
    stage separates air/soft/mineralised tissue.  Inside the mineralised tail a
    three-class split finds low-density bone, dense bone/dentin, and the
    high-density enamel/restoration band.  The lower dental threshold is used
    as a *support* threshold and the upper one as a high-confidence tooth seed;
    final TEETH segmentation is connectivity-based (3D hysteresis), not a
    simple intensity interval.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    props = context.scene.dicom_wizard_pro
    sample = _sample_density_for_automatic_analysis()

    robust_low, robust_high = (
        float(v) for v in np.percentile(sample, (0.2, 99.8))
    )
    clipped = sample[(sample >= robust_low) & (sample <= robust_high)]
    if clipped.size < 1024:
        clipped = sample

    method = "Otsu jerárquico + histéresis dental 3D"
    minimum_gap = max((robust_high - robust_low) * 0.002, 1.0)

    # Stage 1: robust air / patient / mineral split.
    global_split = _weighted_otsu_threshold(clipped)
    lower_values = clipped[clipped <= global_split]
    upper_values = clipped[clipped > global_split]
    lower_split = (
        _weighted_otsu_threshold(lower_values)
        if lower_values.size >= 256 else global_split
    )
    lower_fraction, lower_separation = _otsu_split_quality(
        lower_values, lower_split
    )
    if lower_fraction >= 0.08 and lower_separation >= 2.6:
        air_soft = max(robust_low, float(lower_split))
        soft_bone = max(air_soft + minimum_gap, float(global_split))
        method += " · escala positiva"
    else:
        air_soft = max(robust_low, float(global_split))
        patient_values = upper_values if upper_values.size >= 1024 else clipped
        soft_bone = max(
            air_soft + minimum_gap,
            _weighted_otsu_threshold(patient_values),
        )
        method += " · aire dominante"

    patient_tail = clipped[clipped > air_soft]
    if patient_tail.size >= 1024:
        mineral_split = float(_weighted_otsu_threshold(patient_tail))
        if np.isfinite(mineral_split):
            soft_bone = max(soft_bone, mineral_split)

    metal_cutoff = _estimate_metal_cutoff(clipped, soft_bone, robust_high)
    mineral_tail = clipped[
        (clipped > soft_bone) & (clipped <= metal_cutoff)
    ]
    if mineral_tail.size < 512:
        span = max(metal_cutoff - soft_bone, minimum_gap * 4.0)
        tooth_support = soft_bone + span * 0.35
        tooth_seed = soft_bone + span * 0.62
        method += " · fallback mineral"
    else:
        thresholds = None
        filters = load_skimage_filters()
        if filters is not None:
            try:
                thresholds = np.asarray(
                    filters.threshold_multiotsu(
                        mineral_tail.astype(np.float32, copy=False),
                        classes=3,
                        nbins=512,
                    ), dtype=np.float64,
                ).ravel()
                if thresholds.size >= 2:
                    method += " · Multi-Otsu"
            except Exception:
                thresholds = None
        if thresholds is None or thresholds.size < 2:
            thresholds = np.asarray(
                _weighted_histogram_kmeans_thresholds(
                    mineral_tail, classes=3
                ), dtype=np.float64,
            ).ravel()
            method += " · histograma 3 clases"

        if thresholds.size >= 2:
            tooth_support = float(thresholds[0])
            tooth_seed = float(thresholds[1])
        else:
            tooth_support = float(np.percentile(mineral_tail, 42.0))
            tooth_seed = float(np.percentile(mineral_tail, 72.0))

        valley = _dense_tissue_valley_threshold(
            clipped, soft_bone, metal_cutoff
        )
        if valley is not None and np.isfinite(valley):
            # The valley is useful, but never let it dominate the much more
            # stable three-class mineral split.
            tooth_support = 0.72 * tooth_support + 0.28 * float(valley)
            method += " · valle denso"

        p74 = float(np.percentile(mineral_tail, 74.0))
        tooth_seed = 0.78 * tooth_seed + 0.22 * p74

    tooth_support = max(
        soft_bone + minimum_gap,
        min(float(tooth_support), metal_cutoff - minimum_gap * 2.0),
    )
    tooth_seed = max(
        tooth_support + minimum_gap,
        min(float(tooth_seed), metal_cutoff - minimum_gap),
    )
    # Ensure that support and seed are genuinely distinct. A collapsed pair
    # degenerates hysteresis into a plain threshold and recreates the old bug.
    dense_span = max(metal_cutoff - soft_bone, minimum_gap * 4.0)
    seed_gap = max(minimum_gap, dense_span * 0.045)
    if tooth_seed < tooth_support + seed_gap:
        tooth_seed = min(metal_cutoff - minimum_gap, tooth_support + seed_gap)

    props.auto_air_soft_threshold = float(air_soft)
    props.auto_soft_bone_threshold = float(soft_bone)
    props.auto_bone_teeth_threshold = float(tooth_support)
    props.auto_tooth_seed_threshold = float(tooth_seed)
    props.auto_metal_cutoff = float(
        max(metal_cutoff, tooth_seed + minimum_gap)
    )
    props.auto_robust_low = robust_low
    props.auto_robust_high = robust_high
    props.auto_analysis_method = method
    props.auto_analysis_samples = int(sample.size)
    props.auto_thresholds_ready = True
    sync_automatic_range_from_structure(props)

    for state in RUNTIME.segmentations.values():
        state["stale"] = True
    props.status = (
        f"Densidades separadas · soporte dental {tooth_support:.0f} · "
        f"semilla {tooth_seed:.0f}"
    )
    return float(soft_bone), float(tooth_support), float(tooth_seed)


def _full_density_mask(low: float, high: float | None = None):
    """Build one full-resolution mask without materialising a float volume."""
    np = load_numpy()
    z_count, y_count, x_count = RUNTIME.dims_zyx
    mask = np.zeros((z_count, y_count, x_count), dtype=bool)
    chunk_depth = max(1, min(16, z_count))
    for z0 in range(0, z_count, chunk_depth):
        z1 = min(z_count, z0 + chunk_depth)
        raw = RUNTIME.volume[z0:z1].astype(np.float32, copy=False)
        values = (
            raw * RUNTIME.slopes[z0:z1, None, None]
            + RUNTIME.intercepts[z0:z1, None, None]
        )
        block = np.isfinite(values) & (values >= float(low))
        if high is not None:
            block &= values <= float(high)
        mask[z0:z1] = block
    return mask


def _filter_dental_seed_mask(seeds):
    """Reject high-density seed components that look like cortex/FOV artefact.

    Enamel/restoration seeds are usually compact and local. Dense cortical
    sheets and reconstruction borders tend to be very large, elongated, or
    touch the volume boundary. Filtering only the *markers* is conservative:
    roots can still grow through the lower support mask afterwards.
    """
    np = load_numpy()
    seeds = np.ascontiguousarray(seeds, dtype=bool)
    if not seeds.any():
        return seeds, "EMPTY"
    voxel_mm3 = max(float(
        RUNTIME.spacing_zyx_mm[0] * RUNTIME.spacing_zyx_mm[1]
        * RUNTIME.spacing_zyx_mm[2]), 1e-9)
    ndi = load_scipy_ndimage()
    if ndi is not None:
        labels, count = ndi.label(seeds, structure=ndi.generate_binary_structure(3, 2))
        if int(count) <= 0:
            return np.zeros_like(seeds), "SCIPY_SEED_FILTER"
        sizes = np.bincount(labels.ravel(), minlength=int(count)+1)
        objects = ndi.find_objects(labels)
        boundary_labels = set(np.unique(np.concatenate((
            labels[0].ravel(), labels[-1].ravel(), labels[:,0,:].ravel(),
            labels[:,-1,:].ravel(), labels[:,:,0].ravel(), labels[:,:,-1].ravel(),
        ))).tolist())
        keep = np.zeros(int(count)+1, dtype=bool)
        spacing = tuple(float(v) for v in RUNTIME.spacing_zyx_mm)
        for lab in range(1, int(count)+1):
            vox = int(sizes[lab]); vol = vox * voxel_mm3
            if vol < 0.20 or vol > 18000.0:
                continue
            if lab in boundary_labels and vol > 650.0:
                continue
            sl = objects[lab-1] if lab-1 < len(objects) else None
            if sl is not None:
                dims = [max(1, s.stop-s.start) * spacing[i] for i,s in enumerate(sl)]
                dims_sorted = sorted(float(v) for v in dims)
                if max(dims) > 48.0 and min(dims) < 4.0:
                    continue
                # Thin, broad high-density sheets are much more likely cortex
                # or reconstruction borders than enamel/crown markers.
                if dims_sorted[0] < 1.6 and dims_sorted[1] > 9.0:
                    continue
                if dims_sorted[0] < 2.5 and dims_sorted[1] > 12.0 and dims_sorted[2] > 20.0:
                    continue
            keep[lab] = True
        filtered = keep[labels]
        return filtered, "SCIPY_SEED_FILTER"

    runs, parent, sizes, boundary = _rle_component_analysis(seeds, adjacency=1)
    stats = _component_statistics(seeds.shape, runs, parent, sizes, boundary)
    spacing = tuple(float(v) for v in RUNTIME.spacing_zyx_mm)
    keep_roots = []
    for root, item in stats.items():
        vol = float(item["size"]) * voxel_mm3
        if vol < 0.20 or vol > 18000.0:
            continue
        if bool(item["boundary"]) and vol > 650.0:
            continue
        dims = (
            (item["z1"]-item["z0"]+1)*spacing[0],
            (item["y1"]-item["y0"]+1)*spacing[1],
            (item["x1"]-item["x0"]+1)*spacing[2],
        )
        dims_sorted = sorted(float(v) for v in dims)
        if max(dims) > 48.0 and min(dims) < 4.0:
            continue
        if dims_sorted[0] < 1.6 and dims_sorted[1] > 9.0:
            continue
        if dims_sorted[0] < 2.5 and dims_sorted[1] > 12.0 and dims_sorted[2] > 20.0:
            continue
        keep_roots.append(root)
    return _mask_from_component_roots(seeds.shape, runs, parent, keep_roots), "NUMPY_SEED_FILTER"


def _component_filter_from_seeds(support, seeds, *, min_mm3=8.0,
                                 max_mm3=60000.0,
                                 boundary_reject_mm3=9000.0):
    """3D hysteresis: keep support components connected to dense tooth seeds.

    Uses SciPy's C implementation when available.  The dependency-free RLE
    implementation is mathematically the same connectivity criterion and keeps
    Blender 5.1 functional even without binary wheels.
    """
    np = load_numpy()
    support = np.ascontiguousarray(support, dtype=bool)
    seeds = np.ascontiguousarray(seeds & support, dtype=bool)
    if not seeds.any():
        return np.zeros_like(support), "SIN_SEMILLAS"
    voxel_mm3 = max(float(
        RUNTIME.spacing_zyx_mm[0] * RUNTIME.spacing_zyx_mm[1]
        * RUNTIME.spacing_zyx_mm[2]), 1e-9)
    min_vox = max(1, int(np.ceil(float(min_mm3) / voxel_mm3)))
    max_vox = max(min_vox + 1, int(np.ceil(float(max_mm3) / voxel_mm3)))
    boundary_vox = max(min_vox + 1, int(np.ceil(float(boundary_reject_mm3) / voxel_mm3)))
    min_seed_vox = max(1, int(np.ceil(0.35 / voxel_mm3)))

    ndi = load_scipy_ndimage()
    if ndi is not None:
        structure = ndi.generate_binary_structure(3, 2)
        labels, count = ndi.label(support, structure=structure)
        if int(count) <= 0:
            return np.zeros_like(support), "SCIPY_CCL"
        sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
        seed_counts = np.bincount(labels[seeds].ravel(), minlength=int(count) + 1)
        boundary_labels = np.unique(np.concatenate((
            labels[0].ravel(), labels[-1].ravel(),
            labels[:, 0, :].ravel(), labels[:, -1, :].ravel(),
            labels[:, :, 0].ravel(), labels[:, :, -1].ravel(),
        )))
        boundary = np.zeros(int(count) + 1, dtype=bool)
        boundary[boundary_labels] = True
        keep = (
            (sizes >= min_vox) & (sizes <= max_vox)
            & (seed_counts >= min_seed_vox)
        )
        keep &= ~(boundary & (sizes >= boundary_vox))
        keep[0] = False
        out = keep[labels]
        return out, "SCIPY_CCL_HYSTERESIS"

    runs, parent, sizes, boundary = _rle_component_analysis(support, adjacency=1)
    seed_counts = _root_overlap_voxel_counts(runs, parent, seeds)
    keep_roots = []
    for root, size in sizes.items():
        if int(size) < min_vox or int(size) > max_vox:
            continue
        if int(seed_counts.get(root, 0)) < min_seed_vox:
            continue
        if bool(boundary.get(root, False)) and int(size) >= boundary_vox:
            continue
        keep_roots.append(root)
    return (
        _mask_from_component_roots(support.shape, runs, parent, keep_roots),
        "NUMPY_RLE_HYSTERESIS",
    )


def _clean_automatic_mask(mask, structure: str):
    """Small, spacing-aware cleanup without changing anatomical boundaries."""
    np = load_numpy()
    mask = np.ascontiguousarray(mask, dtype=bool)
    if not mask.any():
        return mask, "NONE"
    voxel_mm3 = max(float(
        RUNTIME.spacing_zyx_mm[0] * RUNTIME.spacing_zyx_mm[1]
        * RUNTIME.spacing_zyx_mm[2]), 1e-9)
    min_mm3 = 7.0 if structure == "TEETH" else 4.0
    min_vox = max(1, int(np.ceil(min_mm3 / voxel_mm3)))
    ndi = load_scipy_ndimage()
    if ndi is not None:
        labels, count = ndi.label(mask, structure=ndi.generate_binary_structure(3, 1))
        if int(count) > 0:
            sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
            keep = sizes >= min_vox; keep[0] = False
            mask = keep[labels]
        # One sub-millimetric close heals threshold pinholes but does not bridge
        # the periodontal gap aggressively.
        radii = tuple(max(0, int(round(0.25 / max(s, 1e-6)))) for s in RUNTIME.spacing_zyx_mm)
        if max(radii) > 0:
            footprint = np.ones(tuple(2*r+1 for r in radii), dtype=bool)
            mask = ndi.binary_closing(mask, structure=footprint, iterations=1)
        if structure == "TEETH":
            mask = ndi.binary_fill_holes(mask)
        return np.ascontiguousarray(mask, dtype=bool), "SCIPY_MORPHOLOGY"

    # Dependency-free component cleanup.  Do not auto-fill all holes here: the
    # RLE exterior fill is reliable but unnecessarily expensive on very large
    # volumes, and the generated surface already receives mild smoothing.
    runs, parent, sizes, _boundary = _rle_component_analysis(mask, adjacency=1)
    keep = [root for root, size in sizes.items() if int(size) >= min_vox]
    mask = _mask_from_component_roots(mask.shape, runs, parent, keep)
    return mask, "NUMPY_RLE_CLEANUP"


def _automatic_teeth_mask(props, *, support_low=None, upper=None):
    """Return a connectivity-constrained dental mask and backend diagnostics."""
    np = load_numpy()
    if support_low is None:
        support_low = float(props.auto_range_low)
    else:
        support_low = float(support_low)
    seed_high = float(getattr(props, "auto_tooth_seed_threshold", support_low))
    if upper is None:
        upper = float(props.auto_range_high)
    upper = float(max(upper, seed_high + 1.0))
    support = _full_density_mask(support_low, upper)
    seeds = _full_density_mask(seed_high, upper)
    filtered_seeds, seed_backend = _filter_dental_seed_mask(seeds)
    if filtered_seeds.any():
        seeds = filtered_seeds
    seed_count = max(1, int(seeds.sum()))
    teeth, backend = _component_filter_from_seeds(support, seeds)
    backend = f"{seed_backend}+{backend}"
    del support, seeds, filtered_seeds

    # If the support threshold still touches the jaw in a pathological scan,
    # progressively tighten it toward the seed.  This is scanner-adaptive and
    # prevents one accidental bridge from turning the whole maxilla/mandible
    # into a tooth mask.
    total_vox = max(1, int(np.prod(RUNTIME.dims_zyx)))
    for fraction in (0.18, 0.32, 0.48):
        tooth_voxels = int(teeth.sum())
        coverage = float(tooth_voxels) / total_vox
        growth_ratio = float(tooth_voxels) / max(seed_count, 1)
        if (
            teeth.any()
            and coverage <= SEGMENTATION_MAX_COVERAGE["TEETH"]
            and growth_ratio <= 18.0
        ):
            break
        tightened = support_low + (seed_high - support_low) * fraction
        support = _full_density_mask(tightened, upper)
        seeds = _full_density_mask(seed_high, upper)
        filtered_seeds, seed_backend = _filter_dental_seed_mask(seeds)
        if filtered_seeds.any():
            seeds = filtered_seeds
        seed_count = max(1, int(seeds.sum()))
        teeth, grow_backend = _component_filter_from_seeds(support, seeds)
        backend = f"{seed_backend}+{grow_backend}"
        del support, seeds, filtered_seeds

    if not teeth.any():
        # Safe last resort: high-confidence dental band only.  It is better to
        # return crowns that need manual expansion than to leak the whole jaw.
        fallback = max(support_low, seed_high - (seed_high-support_low) * 0.22)
        teeth = _full_density_mask(fallback, upper)
        backend += "+HIGH_BAND_FALLBACK"
    teeth, cleanup = _clean_automatic_mask(teeth, "TEETH")
    return teeth, f"{backend}+{cleanup}"




# =============================================================================
# DSG 8.7 · SEMANTIC CBCT DENTALSEGMENTATOR
# =============================================================================

SEMANTIC_CLASS_LABELS = {
    0: "background",
    1: "upper_skull_maxilla",
    2: "mandible",
    3: "upper_teeth",
    4: "lower_teeth",
    5: "mandibular_canal",
}
SEMANTIC_MODE_CLASSES = {
    "BONE": (1, 2, 3, 4),
    "TEETH": (3, 4),
    "BONE_ONLY": (1, 2),
    "SOFT_TISSUE": (),
}

def _semantic_engine_root() -> Path:
    return Path(__file__).resolve().parent / "cbct_semantic_engine"


def _semantic_source_signature() -> str:
    pieces = [str(RUNTIME.dims_zyx), str(RUNTIME.spacing_zyx_mm)]
    files = RUNTIME.source_files or ([RUNTIME.source_path] if RUNTIME.source_path else [])
    for name in files[:16]:
        try:
            fp = Path(name)
            st = fp.stat()
            pieces.append(f"{fp.resolve()}|{st.st_size}|{st.st_mtime_ns}")
        except Exception:
            pieces.append(str(name))
    return str(hash("||".join(pieces)))


def _semantic_model_kind_for_structure(structure: str) -> str:
    """Return the primary engine for a requested segmentation structure.

    DSG HYBRID restores the proven 8.7 responsibility split instead of routing
    every mineralized structure through UniversalLab:

    * BONE / BONE_ONLY -> DentalSegmentator (Dataset112, classes 1..5).
    * TEETH -> UniversalLab is the identity/FDI authority, but the interactive
      TEETH workflow first runs DentalSegmentator as anatomical continuity
      support and then UniversalLab.
    * MANDIBULAR_CANAL -> UniversalLab class 55 is the identity source and the
      full workflow additionally verifies continuity with DentalSegmentator 5.

    This function returns only the *primary* labelmap kind. Multi-model routing
    is orchestrated explicitly by the asynchronous clinical workflow.
    """
    structure = str(structure).upper()
    if structure in {"BONE", "BONE_ONLY"}:
        return "semantic"
    if structure in {"TEETH", "MANDIBULAR_CANAL"}:
        return "universal"
    return "semantic"


def _load_semantic_labels_cached(model_kind: str | None = None):
    """Query the one active semantic labelmap without triggering inference."""
    labels = getattr(RUNTIME, "semantic_labels", None)
    if labels is None or tuple(getattr(labels, "shape", ())) != tuple(RUNTIME.dims_zyx):
        return None
    kind = str(model_kind or "").lower()
    if kind and str(RUNTIME.semantic_model_kind or "").lower() != kind:
        return None
    return labels


def get_cached_semantic_cbct_labels(*, model_kind: str | None = None, require_current_source: bool = True):
    """Return cached labels only; never starts a neural inference (CQS query)."""
    labels = _load_semantic_labels_cached(model_kind)
    if labels is None:
        return None
    if require_current_source and str(RUNTIME.semantic_source_signature or "") != _semantic_source_signature():
        return None
    return labels


def _store_semantic_result(labels, *, kind: str, signature: str, metadata=None, crop_info=None):
    """Commit one validated full-size labelmap as the semantic SSOT."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un CBCT activo para almacenar la segmentación")
    array = np.ascontiguousarray(labels)
    if tuple(array.shape) != tuple(RUNTIME.dims_zyx):
        raise RuntimeError(
            f"Resultado IA incompatible: {tuple(array.shape)} != CBCT {tuple(RUNTIME.dims_zyx)}"
        )
    if array.dtype.kind not in {"u", "i"}:
        raise RuntimeError(f"Resultado IA inválido: dtype {array.dtype}; se esperaban etiquetas enteras")
    RUNTIME.semantic_labels = array
    RUNTIME.semantic_status_path = ""
    RUNTIME.semantic_source_signature = str(signature)
    RUNTIME.semantic_model_kind = str(kind).lower()
    RUNTIME.semantic_model_metadata = dict(metadata or {})
    RUNTIME.semantic_crop_info = dict(crop_info or {})
    return array


def predict_semantic_cbct_labels_sync(context, *, force: bool = False, model_kind: str | None = None):
    """Explicit synchronous compatibility path for scripts, never called by DSG UI.

    The interactive workflow uses :func:`start_prediction_job`; keeping the word
    ``sync`` in this API makes a potentially blocking operation impossible to
    mistake for a cache query.

    DSG 8.8 removes the 8.7 chain ``NPY -> external Python -> SimpleITK ->
    NIfTI -> nnUNetv2_predict -> NIfTI -> NPY``. The raw CBCT is calibrated,
    optionally cropped without interpolation, inferred and restored in memory.
    """
    np = load_numpy()
    if np is None or not RUNTIME.is_loaded():
        raise RuntimeError("Carga primero un CBCT")
    props = context.scene.dicom_wizard_pro
    kind = str(model_kind or _semantic_model_kind_for_structure(props.segmentation_structure)).lower()
    signature = _semantic_source_signature()
    cached = get_cached_semantic_cbct_labels(model_kind=kind, require_current_source=True)
    if not force and cached is not None:
        return cached

    from . import cbct_ai_runtime
    status = cbct_ai_runtime.runtime_status()
    if not status.dependencies_ready:
        raise RuntimeError(
            "Motor IA interno no instalado. Pulsa «INSTALAR MOTORES»; "
            "DSG lo instala dentro de Blender sin Python/Slicer externos."
        )
    if kind == "universal" and not status.universal_model_ready:
        raise RuntimeError(
            "Falta UniversalLab (dientes individuales + FDI). "
            "Pulsa «INSTALAR MOTORES»."
        )
    if kind == "semantic" and not status.semantic_model_ready:
        raise RuntimeError("Falta el checkpoint DentalSegmentator incluido con DSG")

    def status_cb(message: str):
        props.status = str(message)
        force_ui_redraw()

    status_cb("Preparando CBCT en memoria…")
    # UniversalLab benefits strongly from the conservative no-interpolation crop
    # used by BATCHDENTALSEG. The proven DSG 8.7 semantic model keeps full FOV
    # for strict clinical equivalence during migration.
    calibrated, crop_slices, crop_info = cbct_ai_runtime.calibrate_and_autocrop(
        RUNTIME.volume,
        RUNTIME.slopes,
        RUNTIME.intercepts,
        RUNTIME.spacing_zyx_mm,
        enable_crop=(kind == "universal"),
        margin_mm=15.0,
        min_reduction_fraction=0.15,
    )
    if crop_info.get("cropped"):
        retained = 100.0 * float(crop_info.get("retained_fraction", 1.0))
        status_cb(f"ROI dentomaxilar · {retained:.0f}% del volumen · iniciando IA…")

    metadata = cbct_ai_runtime.model_metadata(kind)
    perf_plan = cbct_ai_runtime.build_inference_plan(
        crop_info.get("crop_shape_zyx", calibrated.shape), RUNTIME.spacing_zyx_mm,
        kind=kind, device_preference=str(getattr(props, "ai_device_preference", "AUTO")),
        metadata=metadata,
    )
    perf_plan, ok_ram, available_ram, safe_budget = cbct_ai_runtime._enable_disk_accumulator_if_needed(
        perf_plan, calibrated.shape, RUNTIME.spacing_zyx_mm, metadata
    )
    estimated_peak = float(perf_plan.get("estimated_ram_gb", 0.0))
    crop_info["performance_plan"] = dict(perf_plan)
    crop_info["estimated_additional_ram_gb"] = float(estimated_peak)
    crop_info["available_ram_gb"] = float(available_ram) if available_ram is not None else None
    crop_info["safe_budget_ram_gb"] = float(safe_budget) if safe_budget is not None else None
    if not ok_ram:
        del calibrated
        raise RuntimeError(
            f"Memoria insuficiente incluso con respaldo en disco: hacen falta ~{estimated_peak:.1f} GB de RAM; "
            f"hay ~{available_ram:.1f} GB libres y DSG puede usar de forma segura ~{safe_budget:.1f} GB."
        )
    if bool(perf_plan.get("disk_accumulator")):
        status_cb(
            f"RAM baja · acumulador nnU-Net temporal en disco "
            f"(~{float(perf_plan.get('estimated_swap_file_gb', 0.0)):.1f} GB)…"
        )

    labels_crop = cbct_ai_runtime.predict_volume(
        calibrated,
        RUNTIME.spacing_zyx_mm,
        kind=kind,
        device_preference=str(getattr(props, "ai_device_preference", "AUTO")),
        use_tta=False,  # matches DSG 8.7 --disable_tta and avoids doubling inference time
        low_memory_export=True,
        status_cb=status_cb,
        performance_plan=perf_plan,
    )
    crop_info["performance_plan_actual"] = cbct_ai_runtime.last_performance_plan()
    del calibrated
    labels = cbct_ai_runtime.restore_crop(labels_crop, RUNTIME.dims_zyx, crop_slices)
    del labels_crop

    if kind == "universal":
        # Preserve UniversalLab's learned instances and only resolve the known
        # left/right mirroring failure mode in the original DICOM coordinate system.
        try:
            from . import cbct_dental_module
            mirror = cbct_dental_module.correct_universal_mirroring(labels)
            crop_info["mirroring"] = mirror
        except Exception as exc:
            crop_info["mirroring"] = {"checked": False, "error": str(exc)}

    active_labels = _store_semantic_result(
        labels, kind=kind, signature=signature, metadata=metadata, crop_info=crop_info
    )
    props.status = (
        "UniversalLab · dientes individualizados + FDI listos"
        if kind == "universal"
        else "DentalSegmentator · segmentación CBCT lista"
    )
    return RUNTIME.semantic_labels


# Legacy API name retained for third-party scripts. DSG itself never calls it.
ensure_semantic_cbct_labels = predict_semantic_cbct_labels_sync


def _semantic_classes_for_structure(structure: str, model_kind: str | None = None) -> tuple[int, ...]:
    structure = str(structure).upper()
    kind = str(model_kind or RUNTIME.semantic_model_kind or "semantic").lower()
    if kind == "universal":
        if structure == "TEETH":
            return tuple(range(1, 53))
        if structure == "BONE_ONLY":
            return (53, 54)
        if structure == "MANDIBULAR_CANAL":
            return (55,)
        if structure == "BONE":
            return tuple(range(1, 55))
        return ()
    return tuple(SEMANTIC_MODE_CLASSES.get(structure, ()))


def _semantic_mask_for_structure(labels, structure: str):
    np = load_numpy()
    classes = _semantic_classes_for_structure(structure, RUNTIME.semantic_model_kind)
    if not classes:
        raise RuntimeError(f"El modo {structure} no tiene clases semánticas configuradas")
    # UniversalLab labels are compact uint8. np.isin is acceptable only for the
    # already-cropped clinical state; the full label map itself remains one byte/voxel.
    return np.isin(labels, np.asarray(classes, dtype=np.uint8))


def _semantic_compact_mask_for_structure(labels, structure: str):
    """Return only the occupied semantic ROI, avoiding a full-FOV boolean copy."""
    np = load_numpy()
    classes = tuple(int(v) for v in _semantic_classes_for_structure(structure, RUNTIME.semantic_model_kind))
    if not classes:
        raise RuntimeError(f"El modo {structure} no tiene clases semánticas configuradas")
    try:
        from scipy import ndimage
    except ImportError:
        # Dependency-degraded fallback remains mathematically identical, only
        # less memory efficient. AI installation normally provides SciPy.
        full = _semantic_mask_for_structure(labels, structure)
        try:
            return _compact_mask(full, (0, 0, 0))
        finally:
            del full

    boxes = ndimage.find_objects(labels, max_label=max(classes))
    selected = [
        boxes[value - 1]
        for value in classes
        if 0 < value <= len(boxes) and boxes[value - 1] is not None
    ]
    if not selected:
        return None, (0, 0, 0)
    starts = tuple(min(int(box[axis].start) for box in selected) for axis in range(3))
    stops = tuple(max(int(box[axis].stop) for box in selected) for axis in range(3))
    roi = labels[starts[0]:stops[0], starts[1]:stops[1], starts[2]:stops[2]]
    ordered = sorted(set(classes))
    contiguous = ordered == list(range(ordered[0], ordered[-1] + 1))
    if contiguous:
        compact = (roi >= ordered[0]) & (roi <= ordered[-1])
    else:
        compact = np.isin(roi, np.asarray(ordered, dtype=np.uint8))
    return np.ascontiguousarray(compact), starts



def _compact_mask_for_classes(labels, classes):
    """Return a compact native-resolution bool mask for explicit integer classes."""
    np = load_numpy()
    classes = tuple(sorted({int(v) for v in classes}))
    if not classes:
        return None, (0, 0, 0)
    arr = np.asarray(labels)
    try:
        from scipy import ndimage
        boxes = ndimage.find_objects(arr, max_label=max(classes))
        selected = [
            boxes[value - 1]
            for value in classes
            if 0 < value <= len(boxes) and boxes[value - 1] is not None
        ]
    except Exception:
        selected = []
    if not selected:
        coords = np.argwhere(np.isin(arr, np.asarray(classes, dtype=arr.dtype)))
        if coords.size == 0:
            return None, (0, 0, 0)
        starts = tuple(int(v) for v in coords.min(axis=0))
        stops = tuple(int(v) + 1 for v in coords.max(axis=0))
    else:
        starts = tuple(min(int(box[axis].start) for box in selected) for axis in range(3))
        stops = tuple(max(int(box[axis].stop) for box in selected) for axis in range(3))
    roi = arr[starts[0]:stops[0], starts[1]:stops[1], starts[2]:stops[2]]
    mask = np.isin(roi, np.asarray(classes, dtype=arr.dtype))
    return np.ascontiguousarray(mask, dtype=np.bool_), starts


def _embed_compact_mask(mask, origin, union_origin, union_shape):
    np = load_numpy()
    out = np.zeros(tuple(int(v) for v in union_shape), dtype=np.bool_)
    if mask is None:
        return out
    oz, oy, ox = (int(v) for v in origin)
    uz, uy, ux = (int(v) for v in union_origin)
    z0, y0, x0 = oz - uz, oy - uy, ox - ux
    z1, y1, x1 = z0 + mask.shape[0], y0 + mask.shape[1], x0 + mask.shape[2]
    out[z0:z1, y0:y1, x0:x1] = mask
    return out


def _ellipsoid_structure(radius_mm: float):
    """Anisotropic structuring element expressed in physical millimetres."""
    np = load_numpy()
    sz, sy, sx = (float(v) for v in RUNTIME.spacing_zyx_mm)
    rz = max(1, int(math.ceil(float(radius_mm) / max(sz, 1.0e-6))))
    ry = max(1, int(math.ceil(float(radius_mm) / max(sy, 1.0e-6))))
    rx = max(1, int(math.ceil(float(radius_mm) / max(sx, 1.0e-6))))
    zz, yy, xx = np.ogrid[-rz:rz + 1, -ry:ry + 1, -rx:rx + 1]
    dist2 = (zz * sz) ** 2 + (yy * sy) ** 2 + (xx * sx) ** 2
    return np.asarray(dist2 <= float(radius_mm) ** 2, dtype=np.bool_)


def _fuse_mandibular_canal_masks(universal_mask, universal_origin,
                                  verifier_mask=None, verifier_origin=None):
    """Conservative ensemble of UniversalLab-55 and DentalSegmentator-5.

    Rules:
    * UniversalLab remains accepted evidence.
    * Full connected components from the dedicated DentalSegmentator canal class
      are kept when they overlap/approach UniversalLab, plus up to the two largest
      substantial components so an entirely missed contralateral canal can be
      recovered.
    * No long synthetic path is drawn.
    * Only sub-millimetric binary closing (<=0.65 mm) is allowed to heal tiny
      voxel interruptions after model-backed fusion.
    """
    np = load_numpy()
    if universal_mask is None and verifier_mask is None:
        return None, (0, 0, 0), {
            "source": "NONE", "universal_voxels": 0, "verifier_voxels": 0,
            "verifier_added_voxels": 0, "final_voxels": 0,
        }
    if universal_mask is None:
        u_origin = tuple(int(v) for v in verifier_origin)
        u_shape = tuple(int(v) for v in verifier_mask.shape)
    else:
        u_origin = tuple(int(v) for v in universal_origin)
        u_shape = tuple(int(v) for v in universal_mask.shape)
    if verifier_mask is None:
        v_origin = u_origin
        v_shape = u_shape
    else:
        v_origin = tuple(int(v) for v in verifier_origin)
        v_shape = tuple(int(v) for v in verifier_mask.shape)

    starts = tuple(min(u_origin[i], v_origin[i]) for i in range(3))
    u_stop = tuple(u_origin[i] + u_shape[i] for i in range(3))
    v_stop = tuple(v_origin[i] + v_shape[i] for i in range(3))
    stops = tuple(max(u_stop[i], v_stop[i]) for i in range(3))
    shape = tuple(stops[i] - starts[i] for i in range(3))

    U = _embed_compact_mask(universal_mask, u_origin, starts, shape) if universal_mask is not None else np.zeros(shape, dtype=np.bool_)
    V = _embed_compact_mask(verifier_mask, v_origin, starts, shape) if verifier_mask is not None else np.zeros(shape, dtype=np.bool_)

    universal_voxels = int(U.sum())
    verifier_voxels = int(V.sum())
    accepted_v = np.zeros(shape, dtype=np.bool_)

    if verifier_voxels:
        try:
            from scipy import ndimage
            cc, count = ndimage.label(V)
            sizes = np.bincount(cc.ravel())
            if sizes.size:
                sizes[0] = 0
            order = [int(i) for i in np.argsort(sizes)[::-1] if int(i) != 0 and int(sizes[int(i)]) >= 8]
            if universal_voxels:
                near = ndimage.binary_dilation(U, structure=_ellipsoid_structure(1.5))
            else:
                near = np.zeros_like(U)

            kept = []
            largest = int(sizes[order[0]]) if order else 0
            for rank, comp_id in enumerate(order):
                comp = (cc == comp_id)
                touches = bool(np.any(comp & near)) if universal_voxels else False
                substantial = int(sizes[comp_id]) >= max(12, int(round(largest * 0.12))) if largest else False
                # Preserve model-backed bilateral canals even if UniversalLab
                # missed one whole side. Do not accept an unlimited zoo of blobs.
                bilateral_recovery = rank < 2 and substantial
                if touches or bilateral_recovery:
                    accepted_v |= comp
                    kept.append(comp_id)
            kept_components = len(kept)
        except Exception:
            accepted_v = V.copy()
            kept_components = -1
    else:
        kept_components = 0

    fused = U | accepted_v
    before_close = int(fused.sum())

    # Heal only tiny sampling/classification interruptions. 0.65 mm is
    # deliberately too small to fabricate a missing multi-millimetre trajectory.
    try:
        from scipy import ndimage
        fused = ndimage.binary_closing(
            fused,
            structure=_ellipsoid_structure(0.65),
            iterations=1,
            border_value=0,
        )
        # Preserve every model-backed voxel even if closing erodes at a boundary.
        fused |= U
        fused |= accepted_v
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    final_voxels = int(fused.sum())
    added = int((fused & ~U).sum())
    return np.ascontiguousarray(fused, dtype=np.bool_), starts, {
        "source": (
            "ENSEMBLE_UNIVERSALLAB55_DENTALSEGMENTATOR5"
            if verifier_voxels else "UNIVERSALLAB55_NATIVE"
        ),
        "universal_voxels": universal_voxels,
        "verifier_voxels": verifier_voxels,
        "verifier_kept_components": int(kept_components),
        "verifier_added_voxels": added,
        "preclose_voxels": before_close,
        "final_voxels": final_voxels,
        "closing_radius_mm": 0.65,
    }



def _mandibular_canal_material():
    """High-visibility clinical material for the learned IAN canal mask."""
    spec = SEGMENTATION_STRUCTURES["MANDIBULAR_CANAL"]
    material = bpy.data.materials.get(spec["material"])
    if material is None:
        material = bpy.data.materials.new(spec["material"])
    color = spec["color"]
    alpha = 0.82
    material.diffuse_color = (*color, alpha)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        base_color = bsdf.inputs.get("Base Color")
        if base_color is not None:
            base_color.default_value = (*color, alpha)
        alpha_input = bsdf.inputs.get("Alpha")
        if alpha_input is not None:
            alpha_input.default_value = alpha
        roughness = bsdf.inputs.get("Roughness")
        if roughness is not None:
            roughness.default_value = 0.34
    _configure_transparent_material(material, alpha)
    return material


def _filter_mandibular_canal_components(mask):
    """Remove only tiny isolated class-55 speckles; retain anatomical variants.

    We deliberately do not force exactly two connected components because
    accessory/bifid canals and small segmentation discontinuities are possible.
    """
    np = load_numpy()
    array = np.ascontiguousarray(mask, dtype=np.bool_)
    voxel_count = int(array.sum())
    if voxel_count < 8:
        return array, {
            "input_voxels": voxel_count,
            "kept_voxels": voxel_count,
            "components": 0,
            "kept_components": 0,
        }
    try:
        from scipy import ndimage
        labels_cc, count = ndimage.label(array)
        if count <= 1:
            return array, {
                "input_voxels": voxel_count,
                "kept_voxels": voxel_count,
                "components": int(count),
                "kept_components": int(count),
            }
        sizes = np.bincount(labels_cc.ravel())
        sizes[0] = 0
        largest = int(sizes.max()) if sizes.size else 0
        # Conservative: remove only obvious speckles.
        minimum = max(8, min(48, int(round(largest * 0.01))))
        keep_ids = np.flatnonzero(sizes >= minimum)
        filtered = np.isin(labels_cc, keep_ids)
        return np.ascontiguousarray(filtered), {
            "input_voxels": voxel_count,
            "kept_voxels": int(filtered.sum()),
            "components": int(count),
            "kept_components": int(len(keep_ids)),
            "minimum_component_voxels": int(minimum),
        }
    except Exception:
        return array, {
            "input_voxels": voxel_count,
            "kept_voxels": voxel_count,
            "components": -1,
            "kept_components": -1,
        }


def build_mandibular_canal_surface(context, labels, *,
                                     verifier_mask=None, verifier_origin=None,
                                     verifier_stats=None, prepared=None):
    """Materialise the IAN canal at native mask resolution.

    UniversalLab class 55 is fused conservatively with the dedicated
    DentalSegmentator class 5 when the verifier is available. The label mask is
    never stride-downsampled before marching cubes.
    """
    np = load_numpy()
    if isinstance(prepared, dict):
        status = str(prepared.get("status", "UNKNOWN"))
        fusion = dict(prepared.get("fusion") or {})
        voxels = int(prepared.get("voxels", 0) or 0)
        if status == "NOT_FOUND":
            summary = {"status": "NOT_FOUND", "voxels": 0, "faces": 0, "semantic_class": 55, **fusion}
            if verifier_stats:
                summary["verifier"] = dict(verifier_stats)
            context.scene["DSG_mandibular_canal_status"] = "NOT_FOUND"
            context.scene["DSG_mandibular_canal_semantic_class"] = 55
            return None, summary
        if prepared.get("vertices_path"):
            vertices_xyz = np.load(str(prepared.get("vertices_path")), mmap_mode="r")
        else:
            vertices_xyz = np.asarray(prepared.get("vertices"), dtype=np.float32)
        if prepared.get("faces_array_path"):
            faces = np.load(str(prepared.get("faces_array_path")), mmap_mode="r")
        else:
            faces = np.asarray(prepared.get("faces_array"), dtype=np.int32)
        if len(faces) < 4:
            context.scene["DSG_mandibular_canal_status"] = "SURFACE_EMPTY"
            return None, {"status": "SURFACE_EMPTY", "voxels": voxels, "faces": int(len(faces)), "semantic_class": 55, **fusion}
    else:
        prepared = _prepare_canal_surface_arrays(
            labels, verifier_mask=verifier_mask, verifier_origin=verifier_origin, verifier_stats=verifier_stats
        )
        fusion = dict(prepared.get("fusion") or {})
        voxels = int(prepared.get("voxels", 0) or 0)
        if str(prepared.get("status")) == "NOT_FOUND":
            summary = {"status": "NOT_FOUND", "voxels": 0, "faces": 0, "semantic_class": 55, **fusion}
            if verifier_stats:
                summary["verifier"] = dict(verifier_stats)
            context.scene["DSG_mandibular_canal_status"] = "NOT_FOUND"
            context.scene["DSG_mandibular_canal_semantic_class"] = 55
            return None, summary
        vertices_xyz = np.asarray(prepared.get("vertices"), dtype=np.float32)
        faces = np.asarray(prepared.get("faces_array"), dtype=np.int32)
        if len(faces) < 4:
            context.scene["DSG_mandibular_canal_status"] = "SURFACE_EMPTY"
            return None, {"status": "SURFACE_EMPTY", "voxels": voxels, "faces": int(len(faces)), "semantic_class": 55, **fusion}

    root = get_root(get_collection())
    old = bpy.data.objects.get(NAME_DICOM_MANDIBULAR_CANAL)
    if old is not None:
        old_mesh = old.data if old.type == "MESH" else None
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    obj = _new_surface_from_arrays(
        context,
        object_name=NAME_DICOM_MANDIBULAR_CANAL,
        vertices_xyz=vertices_xyz,
        faces=faces,
        root=root,
    )
    material = _mandibular_canal_material()
    if len(obj.data.materials) == 0:
        obj.data.materials.append(material)
    else:
        obj.data.materials[0] = material

    try:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    obj.show_in_front = True
    obj.hide_render = False
    obj.hide_select = False
    obj["DSG_semantic_class"] = 55
    obj["DSG_verifier_semantic_class"] = 5
    obj["DSG_structure"] = "MANDIBULAR_CANAL"
    obj["DSG_safety_structure"] = True
    obj["DSG_source"] = str(fusion.get("source", "UNIVERSALLAB55_NATIVE"))
    obj["DSG_segmentation_status"] = "SEGMENTED"
    obj["DSG_voxel_count"] = voxels
    obj["DSG_surface_faces"] = int(len(faces))
    obj["DSG_sampling_stride"] = 1
    obj["DSG_native_resolution"] = True
    obj["DSG_universal_voxels"] = int(fusion.get("universal_voxels", 0))
    obj["DSG_verifier_voxels"] = int(fusion.get("verifier_voxels", 0))
    obj["DSG_verifier_added_voxels"] = int(fusion.get("verifier_added_voxels", 0))
    obj["DSG_verifier_kept_components"] = int(fusion.get("verifier_kept_components", 0))
    obj["DSG_gap_close_radius_mm"] = float(fusion.get("closing_radius_mm", 0.0))
    obj["dental_suite_structure"] = "MANDIBULAR_CANAL"
    obj["dental_suite_component"] = "DICOM"
    _set_suite_role(obj, ROLE_DICOM_MANDIBULAR_CANAL, component="DICOM")

    context.scene["DSG_mandibular_canal_status"] = "SEGMENTED"
    context.scene["DSG_mandibular_canal_object"] = obj.name
    context.scene["DSG_mandibular_canal_semantic_class"] = 55
    context.scene["DSG_mandibular_canal_verifier_class"] = 5
    context.scene["DSG_mandibular_canal_source"] = str(fusion.get("source", ""))

    summary = {
        "status": "SEGMENTED",
        "voxels": voxels,
        "faces": int(len(faces)),
        "semantic_class": 55,
        "verifier_class": 5,
        "stride": 1,
        "native_resolution": True,
        **fusion,
    }
    if verifier_stats:
        summary["verifier"] = dict(verifier_stats)
    return obj, summary



def segment_tissue_semantically(context, structure: str | None = None) -> dict:
    np = load_numpy()
    props = context.scene.dicom_wizard_pro
    if structure and structure in SEGMENTATION_STRUCTURES:
        props.segmentation_structure = structure
    structure = str(props.segmentation_structure).upper()
    if structure == "SOFT_TISSUE":
        return segment_tissue_automatically(context, structure)
    kind = _semantic_model_kind_for_structure(structure)
    labels = get_cached_semantic_cbct_labels(model_kind=kind, require_current_source=True)
    if labels is None:
        raise RuntimeError(
            "No hay una segmentación IA compatible en memoria. Usa el botón de segmentación; "
            "DSG no inicia inferencias pesadas de forma implícita en el hilo de Blender."
        )
    compact, origin = _semantic_compact_mask_for_structure(labels, structure)
    if compact is None:
        raise RuntimeError("La clase semántica seleccionada quedó vacía")
    count = int(compact.sum())
    total = int(labels.size)
    if count < 64:
        raise RuntimeError("La IA no encontró suficiente anatomía para este modo")
    coverage = count / max(total, 1)
    if coverage > 0.72:
        raise RuntimeError("La máscara semántica ocupa demasiado FOV; se rechaza por seguridad")
    if not compact.any():
        raise RuntimeError("La clase semántica seleccionada quedó vacía")
    state = get_segmentation_state(structure)
    state["positive"].clear(); state["negative"].clear()
    state["mask"] = compact
    state["origin_zyx"] = origin
    state["learned_low"] = 0.0
    state["learned_high"] = 55.0 if kind == "universal" else 5.0
    state["semantic_classes"] = _semantic_classes_for_structure(structure, kind)
    state["semantic"] = True
    state["semantic_model_kind"] = kind
    state["stale"] = False
    sync_segmentation_properties(props)
    if kind == "universal" and structure == "TEETH":
        tooth_count = sum(1 for value in np.unique(labels) if 1 <= int(value) <= 52)
        props.status = f"UniversalLab · {tooth_count} dientes individualizados · {count:,} voxels"
    else:
        props.status = f"Máscara IA · {SEGMENTATION_STRUCTURES[structure]['label']} · {count:,} voxels"
    return state


def segment_tissue_automatically(context, structure: str | None = None) -> dict:
    """Create a full-resolution mask with tissue-specific 3D logic.

    * BONE: one-sided mineralised mask (bone + teeth).
    * TEETH: two-threshold 3D hysteresis; only support components connected to
      high-confidence dental seeds survive.
    * BONE_ONLY: mineralised mask minus the connectivity-derived dental mask.
    """
    np = load_numpy()
    if np is None or not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")
    props = context.scene.dicom_wizard_pro
    if structure and structure in SEGMENTATION_STRUCTURES:
        props.segmentation_structure = structure
    structure = str(props.segmentation_structure).upper()
    if not props.auto_thresholds_ready:
        analyze_automatic_tissue_thresholds(context)
        sync_automatic_range_from_structure(props)

    if (
        core.clinical_route(scene) == core.ROUTE_SIMPLE
        and str(scene.get(core.ROUTE_STEP_KEY, "") or "") == "SIMPLE_DENSITY"
    ):
        update_density_labels(props)
        low = float(props.current_density_min)
        high = float(props.current_density_max)
    else:
        low = float(min(props.auto_range_low, props.auto_range_high))
        high = float(max(props.auto_range_low, props.auto_range_high))
    if high <= low:
        raise RuntimeError("El rango automático no es válido")

    progress_begin(context, 4)
    backend = "DSG_NATIVE"
    try:
        if structure == "TEETH":
            progress_update(context, 1)
            mask, backend = _automatic_teeth_mask(props)
            progress_update(context, 3)
        elif structure == "BONE_ONLY":
            # Do NOT discard dense cortical bone with an arbitrary upper
            # threshold. Build all mineralised tissue and subtract only the
            # connectivity-defined dental mask.
            bone_floor = float(low)
            mineral = _full_density_mask(bone_floor, None)
            progress_update(context, 1)
            # Reuse the automatically learned dental support regardless of the
            # BONE_ONLY display range.
            teeth, tooth_backend = _automatic_teeth_mask(
                props,
                support_low=float(props.auto_bone_teeth_threshold),
                upper=float(props.auto_metal_cutoff),
            )
            progress_update(context, 2)
            mask = mineral & ~teeth
            del mineral, teeth
            mask, cleanup = _clean_automatic_mask(mask, "BONE_ONLY")
            backend = f"MINERAL_MINUS_TEETH[{tooth_backend}]+{cleanup}"
            progress_update(context, 3)
        else:
            # Combined mode: preserve the classic one-sided mineralised anatomy.
            mask = _full_density_mask(low, None)
            progress_update(context, 2)
            mask, cleanup = _clean_automatic_mask(mask, structure)
            backend = f"MINERAL_ONE_SIDED+{cleanup}"
            progress_update(context, 3)
    finally:
        progress_end(context)

    coverage = float(mask.mean())
    max_cov = float(SEGMENTATION_MAX_COVERAGE.get(structure, 0.90))
    min_cov = float(SEGMENTATION_MIN_COVERAGE.get(structure, 0.0))
    if coverage > max_cov:
        raise RuntimeError(
            f"La máscara de {SEGMENTATION_STRUCTURES[structure]['label']} ocupa "
            f"{coverage*100:.0f}% del volumen. DSG la rechaza para evitar una "
            "segmentación catastrófica; pulsa REANALIZAR o ajusta el umbral."
        )
    if coverage < min_cov:
        raise RuntimeError(
            "La máscara dental es demasiado pequeña. Pulsa REANALIZAR; si el "
            "CBCT tiene mucho metal, baja ligeramente el umbral de soporte."
        )

    compact, origin = _compact_mask(mask, (0, 0, 0))
    del mask
    if compact is None or not compact.any():
        raise RuntimeError(
            "La segmentación no produjo una región válida; ajusta los límites"
        )

    state = get_segmentation_state(structure)
    state["positive"].clear(); state["negative"].clear()
    state["mask"] = compact
    state["origin_zyx"] = origin
    state["learned_low"] = low
    state["learned_high"] = high
    state["segmentation_backend"] = backend
    state["stale"] = False
    sync_segmentation_properties(props)
    _refresh_segmentation_views(
        context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS
    )
    props.status = (
        f"{SEGMENTATION_STRUCTURES[structure]['label']} · "
        f"{int(compact.sum()):,} voxels · {backend}"
    )
    return state

def _require_mask(props):
    state = get_segmentation_state(props.segmentation_structure)
    mask = state.get("mask")
    if mask is None or not mask.any():
        raise RuntimeError("Calcula primero la segmentación")
    return state, mask


def _rle_component_analysis(mask, adjacency: int = 1):
    """Label 3D binary components with run-length encoding and union-find.

    This dependency-free implementation avoids SciPy and is efficient for the
    large, mostly coherent masks produced by dental thresholding. Components
    are connected through X runs and overlapping runs in adjacent Y/Z rows.
    ``adjacency=1`` also accepts one-voxel diagonal contact in those rows.
    """
    np = load_numpy()
    data = np.asarray(mask, dtype=bool)
    if data.ndim != 3:
        raise RuntimeError("La máscara debe ser tridimensional")
    z_count, y_count, x_count = data.shape

    parent: list[int] = []
    rank: list[int] = []
    run_length: list[int] = []
    run_boundary: list[bool] = []
    runs: list[tuple[int, int, int, int, int]] = []

    def make_set(length: int, boundary: bool) -> int:
        index = len(parent)
        parent.append(index); rank.append(0); run_length.append(int(length)); run_boundary.append(bool(boundary))
        return index

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    def row_runs(row, z: int, y: int):
        padded = np.empty(x_count + 2, dtype=np.int8)
        padded[0] = 0; padded[-1] = 0; padded[1:-1] = row.astype(np.int8, copy=False)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1) - 1
        current = []
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            boundary = z in (0, z_count - 1) or y in (0, y_count - 1) or x0 == 0 or x1 == x_count - 1
            run_id = make_set(x1 - x0 + 1, boundary)
            item = (int(x0), int(x1), run_id)
            current.append(item)
            runs.append((z, y, int(x0), int(x1), run_id))
        return current

    def union_rows(current, previous) -> None:
        if not current or not previous:
            return
        i = j = 0
        margin = max(0, int(adjacency))
        while i < len(current) and j < len(previous):
            c0, c1, cid = current[i]
            p0, p1, pid = previous[j]
            if c1 + margin < p0:
                i += 1
            elif p1 + margin < c0:
                j += 1
            else:
                union(cid, pid)
                if c1 <= p1:
                    i += 1
                else:
                    j += 1

    previous_slice_rows = [None] * y_count
    for z in range(z_count):
        current_slice_rows = [None] * y_count
        previous_y = None
        for y in range(y_count):
            current = row_runs(data[z, y], z, y)
            union_rows(current, previous_y)
            union_rows(current, previous_slice_rows[y])
            current_slice_rows[y] = current
            previous_y = current
        previous_slice_rows = current_slice_rows

    component_sizes: dict[int, int] = {}
    component_boundary: dict[int, bool] = {}
    for run_id, length in enumerate(run_length):
        root = find(run_id)
        component_sizes[root] = component_sizes.get(root, 0) + int(length)
        component_boundary[root] = component_boundary.get(root, False) or bool(run_boundary[run_id])
    return runs, parent, component_sizes, component_boundary


def _mask_from_component_roots(shape, runs, parent, keep_roots):
    np = load_numpy()
    keep = set(int(value) for value in keep_roots)

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    output = np.zeros(shape, dtype=bool)
    for z, y, x0, x1, run_id in runs:
        if find(run_id) in keep:
            output[z, y, x0:x1 + 1] = True
    return output



def _component_statistics(shape, runs, parent, component_sizes, component_boundary):
    """Return physical-shape statistics for run-length connected components."""
    stats = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for z, y, x0, x1, run_id in runs:
        root = find(run_id)
        item = stats.get(root)
        if item is None:
            item = {
                "size": int(component_sizes.get(root, 0)),
                "boundary": bool(component_boundary.get(root, False)),
                "z0": int(z), "z1": int(z),
                "y0": int(y), "y1": int(y),
                "x0": int(x0), "x1": int(x1),
            }
            stats[root] = item
        else:
            item["z0"] = min(item["z0"], int(z))
            item["z1"] = max(item["z1"], int(z))
            item["y0"] = min(item["y0"], int(y))
            item["y1"] = max(item["y1"], int(y))
            item["x0"] = min(item["x0"], int(x0))
            item["x1"] = max(item["x1"], int(x1))
    return stats


def _roots_overlapping_mask(runs, parent, overlap_mask):
    """Return component roots whose runs overlap at least one True voxel."""
    roots = set()

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for z, y, x0, x1, run_id in runs:
        if overlap_mask[z, y, x0:x1 + 1].any():
            roots.add(find(run_id))
    return roots



def _root_overlap_voxel_counts(runs, parent, overlap_mask):
    """Count overlap voxels for each connected-component root."""
    counts = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for z, y, x0, x1, run_id in runs:
        count = int(overlap_mask[z, y, x0:x1 + 1].sum())
        if count:
            root = find(run_id)
            counts[root] = counts.get(root, 0) + count
    return counts



def remove_small_islands(context, *, keep_largest: bool = False) -> int:
    """Remove small 3D components with SciPy when present, RLE otherwise."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    ndi = load_scipy_ndimage()
    props = context.scene.dicom_wizard_pro
    state, mask = _require_mask(props)
    mask = np.ascontiguousarray(mask, dtype=bool)
    voxel_volume = float(
        RUNTIME.spacing_zyx_mm[0] * RUNTIME.spacing_zyx_mm[1]
        * RUNTIME.spacing_zyx_mm[2])
    minimum_voxels = max(
        1, int(np.ceil(float(props.island_min_mm3) / max(voxel_volume, 1e-9))))

    if ndi is not None:
        labels, count = ndi.label(mask, structure=ndi.generate_binary_structure(3, 1))
        count = int(count)
        if count <= 0:
            return 0
        sizes = np.bincount(labels.ravel(), minlength=count + 1)
        keep = np.zeros(count + 1, dtype=bool)
        if keep_largest:
            keep[int(np.argmax(sizes[1:]) + 1)] = True
        else:
            keep = sizes >= minimum_voxels
            keep[0] = False
        cleaned = keep[labels]
        backend = "SCIPY_CCL"
    else:
        runs, parent, sizes, _boundary = _rle_component_analysis(mask, adjacency=1)
        if not sizes:
            return 0
        if keep_largest:
            roots = [max(sizes, key=sizes.get)]
        else:
            roots = [root for root, size in sizes.items() if int(size) >= minimum_voxels]
        cleaned = _mask_from_component_roots(mask.shape, runs, parent, roots)
        backend = "NUMPY_RLE_CCL"

    removed = int(np.count_nonzero(mask) - np.count_nonzero(cleaned))
    compact, origin = _compact_mask(cleaned, state["origin_zyx"])
    state["mask"] = compact
    state["origin_zyx"] = origin
    state["stale"] = False
    state["island_cleanup_backend"] = backend
    sync_segmentation_properties(props)
    _refresh_segmentation_views(context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS)
    return removed


def _window_morphology_axis(mask, radius: int, axis: int, *, dilate: bool):
    np = load_numpy()
    radius = max(0, int(radius))
    if radius <= 0:
        return mask
    pad = [(0, 0)] * mask.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(mask, pad, mode="constant", constant_values=(False if dilate else True))
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * radius + 1, axis=axis)
    return windows.any(axis=-1) if dilate else windows.all(axis=-1)


def _binary_box_morphology(mask, radii_zyx, *, dilate: bool):
    result = mask.astype(bool, copy=True)
    for axis, radius in enumerate(radii_zyx):
        result = _window_morphology_axis(result, int(radius), axis, dilate=dilate)
    return result


def close_segmentation_gaps(context) -> None:
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    props = context.scene.dicom_wizard_pro
    state, mask = _require_mask(props)
    radius_mm = max(float(props.close_radius_mm), min(RUNTIME.spacing_zyx_mm))
    radii = tuple(max(1, int(round(radius_mm / max(spacing, 1e-6)))) for spacing in RUNTIME.spacing_zyx_mm)
    # A separable box closing is fast, anisotropy-aware and dependency-free.
    dilated = _binary_box_morphology(mask, radii, dilate=True)
    closed = _binary_box_morphology(dilated, radii, dilate=False)
    compact, origin = _compact_mask(closed, state["origin_zyx"])
    state["mask"] = compact; state["origin_zyx"] = origin; state["stale"] = False
    sync_segmentation_properties(props)
    _refresh_segmentation_views(context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS)


def fill_segmentation_holes(context) -> None:
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    props = context.scene.dicom_wizard_pro
    state, mask = _require_mask(props)
    background = ~mask
    runs, parent, _sizes, boundary = _rle_component_analysis(background, adjacency=0)
    exterior_roots = {root for root, touches_boundary in boundary.items() if touches_boundary}
    exterior = _mask_from_component_roots(background.shape, runs, parent, exterior_roots)
    filled = ~exterior
    compact, origin = _compact_mask(filled, state["origin_zyx"])
    state["mask"] = compact; state["origin_zyx"] = origin; state["stale"] = False
    sync_segmentation_properties(props)
    _refresh_segmentation_views(context, max_axis=SEGMENTATION_PREVIEW_MAX_AXIS)

def _surface_material(structure: str):
    spec = SEGMENTATION_STRUCTURES[structure]
    material = bpy.data.materials.get(spec["material"])
    if material is None:
        material = bpy.data.materials.new(spec["material"])
    color = spec["color"]
    alpha = _dicom_surface_alpha_from_props()
    material.diffuse_color = (color[0], color[1], color[2], alpha)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        base_color = bsdf.inputs.get("Base Color")
        if base_color is not None:
            base_color.default_value = (*color, alpha)
        alpha_input = bsdf.inputs.get("Alpha")
        if alpha_input is not None:
            alpha_input.default_value = alpha
        roughness = bsdf.inputs.get("Roughness")
        if roughness is not None:
            roughness.default_value = 0.42
    _configure_transparent_material(material, alpha)
    return material


DICOM_SURFACE_TRANSPARENCY_DEFAULT = 82.0
DICOM_SURFACE_ALPHA_MIN = 0.03


def _dicom_surface_alpha_from_props(props=None) -> float:
    """Return the fixed radiographic alpha used by DSG for generated DICOM STL."""
    transparency = DICOM_SURFACE_TRANSPARENCY_DEFAULT
    return clamp(1.0 - transparency / 100.0, DICOM_SURFACE_ALPHA_MIN, 1.0)


def _configure_transparent_material(material, alpha: float) -> None:
    """Make a material really transparent in Blender Solid/Material previews."""
    if material is None:
        return
    alpha = clamp(float(alpha), DICOM_SURFACE_ALPHA_MIN, 1.0)
    try:
        r, g, b, _a = material.diffuse_color
    except Exception:
        r, g, b = (0.20, 0.70, 1.00)
    try:
        material.diffuse_color = (float(r), float(g), float(b), alpha)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for attr, value in (
        ("blend_method", "BLEND"),
        ("surface_render_method", "BLENDED"),
        ("show_transparent_back", False),
        ("use_screen_refraction", False),
    ):
        try:
            setattr(material, attr, value)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        material.alpha_threshold = 0.01
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            base_color = bsdf.inputs.get("Base Color")
            if base_color is not None:
                current = list(base_color.default_value)
                while len(current) < 4:
                    current.append(1.0)
                current[3] = alpha
                base_color.default_value = tuple(current[:4])
            alpha_input = bsdf.inputs.get("Alpha")
            if alpha_input is not None:
                alpha_input.default_value = alpha
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _iter_dicom_surface_objects(props=None):
    """Yield generated DICOM STL surfaces that may hide the radiographic slice."""
    names = []
    if props is not None:
        try:
            name = str(getattr(props, "generated_surface_name", ""))
            if name:
                names.append(name)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    names.extend((NAME_DICOM_TEETH, NAME_DICOM_BONE, NAME_DICOM_COMBINED))
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        obj = bpy.data.objects.get(name)
        if obj is not None and getattr(obj, "type", None) == "MESH":
            yield obj
    for obj in list(bpy.data.objects):
        try:
            if obj.name in seen or getattr(obj, "type", None) != "MESH":
                continue
            if bool(obj.get("dicom_direct_surface", False)) or bool(obj.get("dicom_parented_to_root", False)):
                yield obj
        except Exception:
            continue


def _apply_dicom_surface_transparency(context=None, props=None) -> None:
    """Apply the ghost transparency slider to the generated DICOM STL."""
    if props is None and context is not None:
        try:
            props = context.scene.dicom_wizard_pro
        except Exception:
            props = None
    alpha = _dicom_surface_alpha_from_props(props)
    for obj in _iter_dicom_surface_objects(props):
        try:
            r, g, b, _a = obj.color
        except Exception:
            r, g, b = (0.20, 0.70, 1.00)
        try:
            obj.color = (float(r), float(g), float(b), alpha)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            obj.show_transparent = alpha < 0.999
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            obj.display_type = "TEXTURED"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            obj.show_in_front = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        materials = list(getattr(obj.data, "materials", []))
        if not materials:
            material = bpy.data.materials.get("SEG_MAT_Dientes") or bpy.data.materials.new("SEG_MAT_Dientes")
            try:
                obj.data.materials.append(material)
                materials = [material]
            except Exception:
                materials = []
        for material in materials:
            _configure_transparent_material(material, alpha)
        try:
            obj.data.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if context is None:
        try:
            context = bpy.context
        except Exception:
            context = None
    if context is not None:
        try:
            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def on_dicom_surface_transparency_change(self, context):
    _apply_dicom_surface_transparency(context, self)


import time



# =============================================================================
# MODULE: hybrid_surface_preview.py
# =============================================================================


