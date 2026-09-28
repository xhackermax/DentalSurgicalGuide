import hashlib
import math
import tempfile
import threading
from pathlib import Path

import bpy



def _cache_path(source_path: str, max_axis: int, stride: int) -> Path:
    identities: list[str] = []
    source_files = RUNTIME.source_files or [source_path]
    for filename in source_files:
        source = Path(filename)
        try:
            identities.append(
                f"{source.resolve()}|{source.stat().st_size}|{source.stat().st_mtime_ns}"
            )
        except OSError:
            identities.append(str(filename))
    identity = "||".join(identities) + f"|{max_axis}|{stride}|single-frame-v1"
    digest = hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:20]
    directory = Path(bpy.app.tempdir or tempfile.gettempdir()) / "dicom_wizard_pro_921"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"volume_{digest}.vdb"


def _preview_axis_indices(count: int, stride: int):
    """Return regular preview indices that always include both endpoints."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    count = max(1, int(count))
    stride = max(1, int(stride))
    if count == 1:
        return np.asarray((0,), dtype=np.int64)
    target_count = max(2, int(math.floor((count - 1) / stride)) + 1)
    return np.unique(
        np.rint(
            np.linspace(0, count - 1, target_count, dtype=np.float64)
        ).astype(np.int64)
    )


def _preview_sampled_shape(stride: int) -> tuple[int, int, int]:
    z_count, y_count, x_count = RUNTIME.dims_zyx
    return (
        int(_preview_axis_indices(z_count, stride).size),
        int(_preview_axis_indices(y_count, stride).size),
        int(_preview_axis_indices(x_count, stride).size),
    )


def _density_sample(stride: int):
    """Sample the same full DICOM grid used by MPR, preserving its endpoints."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")

    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_indices = _preview_axis_indices(z_count, stride)
    y_indices = _preview_axis_indices(y_count, stride)
    x_indices = _preview_axis_indices(x_count, stride)

    raw = RUNTIME.volume[np.ix_(z_indices, y_indices, x_indices)]
    values = raw.astype(np.float32, copy=False)
    values = (
        values * RUNTIME.slopes[z_indices, None, None]
        + RUNTIME.intercepts[z_indices, None, None]
    )

    denominator = max(RUNTIME.density_max - RUNTIME.density_min, 1e-6)
    normalized = np.clip(
        (values - RUNTIME.density_min) / denominator,
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    normalized[normalized < 0.001] = 0.0
    return normalized


def build_vdb_preview(max_axis: int = 256, *, force_rebuild: bool = False) -> str:
    """Write an adaptively decimated full-volume VDB preview."""
    np = load_numpy()
    vdb = load_openvdb()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if vdb is None:
        raise RuntimeError(
            "Esta instalación de Blender no expone OpenVDB. "
            "Instala la versión oficial de Blender 5.1."
        )
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay volumen DICOM cargado")

    max_axis = int(clamp(float(max_axis), MIN_VDB_AXIS, MAX_VDB_AXIS))
    z_count, y_count, x_count = RUNTIME.dims_zyx
    stride = max(1, int(math.ceil(max(z_count, y_count, x_count) / max_axis)))
    output = _cache_path(RUNTIME.source_path, max_axis, stride)

    if output.is_file() and not force_rebuild:
        sampled_shape = _preview_sampled_shape(stride)
        RUNTIME.vdb_path = str(output)
        RUNTIME.vdb_stride = stride
        RUNTIME.vdb_dims_xyz = (
            int(sampled_shape[2]),
            int(sampled_shape[1]),
            int(sampled_shape[0]),
        )
        return str(output)

    normalized_zyx = _density_sample(stride)
    # DICOM/pydicom uses [z, y, x]. OpenVDB's array indices are [x, y, z].
    density_xyz = np.ascontiguousarray(normalized_zyx.transpose(2, 1, 0), dtype=np.float32)

    grid = vdb.FloatGrid()
    grid.name = VOLUME_GRID_NAME
    try:
        grid.gridClass = vdb.GridClass.FOG_VOLUME
    except Exception:
        try:
            grid.gridClass = "fog volume"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    grid.copyFromArray(density_xyz, tolerance=0.001)
    try:
        grid.prune(tolerance=0.001)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        grid.transform = vdb.createLinearTransform(voxelSize=1.0)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    vdb.write(str(output), grids=[grid])

    RUNTIME.vdb_path = str(output)
    RUNTIME.vdb_stride = stride
    RUNTIME.vdb_dims_xyz = tuple(int(value) for value in density_xyz.shape)
    return str(output)


def _socket(sockets, names: tuple[str, ...], fallback_index: int):
    for name in names:
        found = sockets.get(name)
        if found is not None:
            return found
    return sockets[fallback_index]


def _volume_material_is_valid(material: bpy.types.Material | None) -> bool:
    """Return True only for the current persistent clinical GPU preview schema."""
    if material is None or not bool(getattr(material, "use_nodes", False)):
        return False
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return False
    required = (
        "DICOM_OUTPUT",
        "DICOM_VOLUME_INFO",
        "DICOM_WINDOW_REMAP",
        "DICOM_UPPER_MASK",
        "DICOM_WINDOW_DENSITY",
        "DICOM_WINDOW_VOLUME",
        "DICOM_STL_THRESHOLD",
        "DICOM_STL_RAMP",
        "DICOM_STL_FILL_DENSITY",
        "DICOM_STL_SHELL_UPPER",
        "DICOM_STL_SHELL_MASK",
        "DICOM_STL_SHELL_DENSITY",
        "DICOM_STL_COMBINED_DENSITY",
        "DICOM_STL_COLOR_RAMP",
        "DICOM_STL_VOLUME",
        "DICOM_STL_PREVIEW_MODE",
        "DICOM_PREVIEW_MIX",
    )
    return all(tree.nodes.get(name) is not None for name in required)


def get_or_create_volume_material(*, force_rebuild: bool = False) -> bpy.types.Material:
    """Create one persistent, non-emissive clinical threshold preview shader.

    The previous luminous shell could wash out the complete VDB and make the
    volume bounding cube visually dominant. This schema uses one Principled
    Volume only. Densities above the STL threshold retain a graded radiographic
    response, while a very subtle non-emissive band marks the exact iso-level.
    Interactive changes still update scalar sockets only.
    """
    material = bpy.data.materials.get(VOLUME_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(VOLUME_MATERIAL_NAME)
        force_rebuild = True
    if _volume_material_is_valid(material) and not force_rebuild:
        return material

    material.use_nodes = True
    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    info = nodes.new("ShaderNodeVolumeInfo")

    # Normal radiographic window used in viewer step 2.
    remap = nodes.new("ShaderNodeMapRange")
    upper_mask = nodes.new("ShaderNodeMath")
    window_density = nodes.new("ShaderNodeMath")
    window_volume = nodes.new("ShaderNodeVolumePrincipled")

    # Clinical STL preview. The Map Range preserves density differences above
    # the threshold, so roots/cortical/dense structures remain distinguishable.
    # The shell is deliberately non-emissive and only adds a small density lift.
    stl_threshold = nodes.new("ShaderNodeMath")
    stl_ramp = nodes.new("ShaderNodeMapRange")
    stl_fill_density = nodes.new("ShaderNodeMath")
    stl_shell_upper = nodes.new("ShaderNodeMath")
    stl_shell_mask = nodes.new("ShaderNodeMath")
    stl_shell_density = nodes.new("ShaderNodeMath")
    stl_combined_density = nodes.new("ShaderNodeMath")
    stl_color_ramp = nodes.new("ShaderNodeValToRGB")
    stl_volume = nodes.new("ShaderNodeVolumePrincipled")

    preview_mode = nodes.new("ShaderNodeValue")
    preview_mix = nodes.new("ShaderNodeMixShader")

    output.name = "DICOM_OUTPUT"
    info.name = "DICOM_VOLUME_INFO"
    remap.name = "DICOM_WINDOW_REMAP"
    upper_mask.name = "DICOM_UPPER_MASK"
    window_density.name = "DICOM_WINDOW_DENSITY"
    window_volume.name = "DICOM_WINDOW_VOLUME"
    stl_threshold.name = "DICOM_STL_THRESHOLD"
    stl_ramp.name = "DICOM_STL_RAMP"
    stl_fill_density.name = "DICOM_STL_FILL_DENSITY"
    stl_shell_upper.name = "DICOM_STL_SHELL_UPPER"
    stl_shell_mask.name = "DICOM_STL_SHELL_MASK"
    stl_shell_density.name = "DICOM_STL_SHELL_DENSITY"
    stl_combined_density.name = "DICOM_STL_COMBINED_DENSITY"
    stl_color_ramp.name = "DICOM_STL_COLOR_RAMP"
    stl_volume.name = "DICOM_STL_VOLUME"
    preview_mode.name = "DICOM_STL_PREVIEW_MODE"
    preview_mix.name = "DICOM_PREVIEW_MIX"

    remap.data_type = "FLOAT"
    remap.clamp = True
    upper_mask.operation = "LESS_THAN"
    window_density.operation = "MULTIPLY"

    stl_threshold.operation = "GREATER_THAN"
    stl_ramp.data_type = "FLOAT"
    stl_ramp.clamp = True
    stl_fill_density.operation = "MULTIPLY"
    stl_shell_upper.operation = "LESS_THAN"
    stl_shell_mask.operation = "MULTIPLY"
    stl_shell_density.operation = "MULTIPLY"
    stl_combined_density.operation = "ADD"

    _socket(remap.inputs, ("From Min",), 1).default_value = 0.15
    _socket(remap.inputs, ("From Max",), 2).default_value = 0.85
    _socket(remap.inputs, ("To Min",), 3).default_value = 0.0
    _socket(remap.inputs, ("To Max",), 4).default_value = 0.15
    upper_mask.inputs[1].default_value = 0.85

    stl_threshold.inputs[1].default_value = 0.50
    _socket(stl_ramp.inputs, ("From Min",), 1).default_value = 0.50
    _socket(stl_ramp.inputs, ("From Max",), 2).default_value = 1.00
    _socket(stl_ramp.inputs, ("To Min",), 3).default_value = 0.0
    _socket(stl_ramp.inputs, ("To Max",), 4).default_value = 1.0
    stl_fill_density.inputs[1].default_value = 0.14
    stl_shell_upper.inputs[1].default_value = 0.504
    stl_shell_density.inputs[1].default_value = 0.035
    preview_mode.outputs[0].default_value = 0.0

    window_color = window_volume.inputs.get("Color")
    if window_color is not None:
        window_color.default_value = (0.72, 0.78, 0.86, 1.0)

    # Cool-grey at the threshold, progressively whiter for denser anatomy.
    ramp = stl_color_ramp.color_ramp
    ramp.interpolation = "EASE"
    ramp.elements[0].position = 0.0
    ramp.elements[0].color = (0.18, 0.32, 0.50, 1.0)
    ramp.elements[1].position = 1.0
    ramp.elements[1].color = (0.90, 0.94, 1.00, 1.0)
    middle = ramp.elements.new(0.32)
    middle.color = (0.48, 0.62, 0.78, 1.0)

    for volume_node in (window_volume, stl_volume):
        blackbody = volume_node.inputs.get("Blackbody Intensity")
        if blackbody is not None:
            blackbody.default_value = 0.0
        emission_strength = volume_node.inputs.get("Emission Strength")
        if emission_strength is not None:
            emission_strength.default_value = 0.0
        anisotropy = volume_node.inputs.get("Anisotropy")
        if anisotropy is not None:
            anisotropy.default_value = 0.10

    density_output = _socket(info.outputs, ("Density",), 1)

    # Radiographic branch.
    links.new(density_output, _socket(remap.inputs, ("Value",), 0))
    links.new(density_output, upper_mask.inputs[0])
    links.new(_socket(remap.outputs, ("Result",), 0), window_density.inputs[0])
    links.new(upper_mask.outputs[0], window_density.inputs[1])
    links.new(window_density.outputs[0], _socket(window_volume.inputs, ("Density",), 2))

    # STL branch. One graded volume shader, no additive emission.
    links.new(density_output, stl_threshold.inputs[0])
    links.new(density_output, _socket(stl_ramp.inputs, ("Value",), 0))
    links.new(_socket(stl_ramp.outputs, ("Result",), 0), stl_fill_density.inputs[0])
    links.new(density_output, stl_shell_upper.inputs[0])
    links.new(stl_threshold.outputs[0], stl_shell_mask.inputs[0])
    links.new(stl_shell_upper.outputs[0], stl_shell_mask.inputs[1])
    links.new(stl_shell_mask.outputs[0], stl_shell_density.inputs[0])
    links.new(stl_fill_density.outputs[0], stl_combined_density.inputs[0])
    links.new(stl_shell_density.outputs[0], stl_combined_density.inputs[1])
    links.new(_socket(stl_ramp.outputs, ("Result",), 0), stl_color_ramp.inputs[0])
    links.new(stl_combined_density.outputs[0], _socket(stl_volume.inputs, ("Density",), 2))
    links.new(stl_color_ramp.outputs.get("Color") or stl_color_ramp.outputs[0], stl_volume.inputs.get("Color") or stl_volume.inputs[0])

    # Persistent mode switch; threshold interaction changes values only.
    links.new(preview_mode.outputs[0], preview_mix.inputs[0])
    links.new(_socket(window_volume.outputs, ("Volume",), 0), preview_mix.inputs[1])
    links.new(_socket(stl_volume.outputs, ("Volume",), 0), preview_mix.inputs[2])
    links.new(preview_mix.outputs[0], _socket(output.inputs, ("Volume",), 1))

    info.location = (-1080, 80)
    remap.location = (-840, 280)
    upper_mask.location = (-840, 120)
    window_density.location = (-610, 230)
    window_volume.location = (-360, 260)
    stl_threshold.location = (-840, -80)
    stl_ramp.location = (-840, -250)
    stl_fill_density.location = (-560, -220)
    stl_shell_upper.location = (-840, -420)
    stl_shell_mask.location = (-560, -390)
    stl_shell_density.location = (-330, -390)
    stl_combined_density.location = (-100, -260)
    stl_color_ramp.location = (-330, -110)
    stl_volume.location = (150, -220)
    preview_mode.location = (170, 80)
    preview_mix.location = (430, 60)
    output.location = (700, 60)
    material["dsg_volume_shader_schema"] = 5
    return material

def _density_to_normalized(value: float) -> float:
    denominator = max(float(RUNTIME.density_max) - float(RUNTIME.density_min), 1e-6)
    return clamp((float(value) - float(RUNTIME.density_min)) / denominator, 0.0, 1.0)


def update_volume_material(
    threshold_min_percent: float,
    threshold_max_percent: float,
    opacity: float,
    *,
    segmentation_threshold_density: float | None = None,
    preview_shell_width_percent: float = 0.35,
    preview_surface_emphasis: float = 2.0,
    allow_rebuild: bool = False,
) -> bool:
    """Update only scalar sockets in the persistent clinical GPU shader."""
    if RUNTIME.undo_in_progress:
        return False
    material = bpy.data.materials.get(VOLUME_MATERIAL_NAME)
    if not _volume_material_is_valid(material):
        if not allow_rebuild:
            return False
        material = get_or_create_volume_material(force_rebuild=True)
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return False
    nodes = tree.nodes
    remap = nodes.get("DICOM_WINDOW_REMAP")
    upper_mask = nodes.get("DICOM_UPPER_MASK")
    stl_threshold = nodes.get("DICOM_STL_THRESHOLD")
    stl_ramp = nodes.get("DICOM_STL_RAMP")
    stl_fill_density = nodes.get("DICOM_STL_FILL_DENSITY")
    stl_shell_upper = nodes.get("DICOM_STL_SHELL_UPPER")
    stl_shell_density = nodes.get("DICOM_STL_SHELL_DENSITY")
    preview_mode = nodes.get("DICOM_STL_PREVIEW_MODE")
    if any(node is None for node in (
        remap, upper_mask, stl_threshold, stl_ramp, stl_fill_density,
        stl_shell_upper, stl_shell_density, preview_mode,
    )):
        return False

    low = clamp(float(threshold_min_percent), 0.0, 100.0) / 100.0
    high = clamp(float(threshold_max_percent), 0.0, 100.0) / 100.0
    if high < low:
        low, high = high, low
    if high <= low:
        high = min(1.0, low + 0.001)

    shader_opacity = max(0.001, float(opacity))
    _socket(remap.inputs, ("From Min",), 1).default_value = low
    _socket(remap.inputs, ("From Max",), 2).default_value = high
    _socket(remap.inputs, ("To Min",), 3).default_value = 0.0
    _socket(remap.inputs, ("To Max",), 4).default_value = shader_opacity
    upper_mask.inputs[1].default_value = high

    use_stl_preview = segmentation_threshold_density is not None
    preview_mode.outputs[0].default_value = 1.0 if use_stl_preview else 0.0
    if use_stl_preview:
        threshold_normalized = _density_to_normalized(float(segmentation_threshold_density))
        shell_width = clamp(float(preview_shell_width_percent), 0.05, 3.0) / 100.0
        shell_upper = min(1.0, threshold_normalized + shell_width)

        stl_threshold.inputs[1].default_value = threshold_normalized
        _socket(stl_ramp.inputs, ("From Min",), 1).default_value = threshold_normalized
        _socket(stl_ramp.inputs, ("From Max",), 2).default_value = 1.0
        _socket(stl_ramp.inputs, ("To Min",), 3).default_value = 0.0
        _socket(stl_ramp.inputs, ("To Max",), 4).default_value = 1.0
        stl_shell_upper.inputs[1].default_value = shell_upper

        # Graded interior preserves anatomy; the exact iso-level gets only a
        # modest, non-emissive density lift so it cannot burn out the viewport.
        emphasis = clamp(float(preview_surface_emphasis), 0.0, 8.0)
        stl_fill_density.inputs[1].default_value = shader_opacity
        stl_shell_density.inputs[1].default_value = shader_opacity * (0.08 + 0.06 * emphasis)
    return True


def create_volume_object(collection: bpy.types.Collection, root: bpy.types.Object) -> bpy.types.Object:
    if not RUNTIME.vdb_path or not Path(RUNTIME.vdb_path).is_file():
        raise RuntimeError("No se ha generado el archivo OpenVDB")

    obj = bpy.data.objects.get(VOLUME_OBJECT_NAME)
    if obj is not None and obj.type != "VOLUME":
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = None

    if obj is None:
        data = bpy.data.volumes.get(VOLUME_DATA_NAME)
        if data is None:
            data = bpy.data.volumes.new(VOLUME_DATA_NAME)
        obj = bpy.data.objects.new(VOLUME_OBJECT_NAME, data)
        collection.objects.link(obj)
    else:
        data = obj.data
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)

    data.filepath = RUNTIME.vdb_path
    data.is_sequence = False
    try:
        data.grids.load()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    material = get_or_create_volume_material(force_rebuild=False)
    data.materials.clear()
    data.materials.append(material)

    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    sampled_x, sampled_y, sampled_z = RUNTIME.vdb_dims_xyz
    full_z, full_y, full_x = RUNTIME.dims_zyx

    full_extent_x = max(0.0, (full_x - 1) * x_spacing)
    full_extent_y = max(0.0, (full_y - 1) * y_spacing)
    full_extent_z = max(0.0, (full_z - 1) * z_spacing)

    sx = (
        full_extent_x / float(sampled_x - 1)
        if sampled_x > 1
        else x_spacing
    )
    sy = (
        full_extent_y / float(sampled_y - 1)
        if sampled_y > 1
        else y_spacing
    )
    sz = (
        full_extent_z / float(sampled_z - 1)
        if sampled_z > 1
        else z_spacing
    )

    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.scale = (sx, sy, sz)
    obj.location = (
        -0.5 * full_extent_x,
        -0.5 * full_extent_y,
        -0.5 * full_extent_z,
    )
    obj["dicom_alignment_frame"] = "root-local full voxel extent"
    obj["dicom_preview_endpoint_aligned"] = True
    # Users manipulate the dataset through DICOM_WIZARD_ROOT. Selecting the
    # VDB object directly would disturb its internal voxel scale and offset.
    obj.hide_select = True
    obj.hide_render = False
    try:
        # Blender 5.1 VolumeDisplay uses LINEAR for the best speed/smoothness balance.
        data.display.interpolation_method = "LINEAR"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        data.display.density = 1.0
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def remove_cached_vdb() -> None:
    path = RUNTIME.vdb_path
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

# =============================================================================
# MODULE: mpr.py
# =============================================================================

import math
from dataclasses import dataclass



@dataclass
class SliceResult:
    orientation: str
    values: object
    normalized: object
    center_xyz_mm: object
    axis_u_xyz: object
    axis_v_xyz: object
    normal_xyz: object
    width_mm: float
    height_mm: float
    output_width: int
    output_height: int


def density_from_percent(percent: float) -> float:
    fraction = clamp(float(percent), 0.0, 100.0) / 100.0
    return RUNTIME.density_min + fraction * (RUNTIME.density_max - RUNTIME.density_min)


def threshold_values(min_percent: float, max_percent: float) -> tuple[float, float]:
    low = density_from_percent(min_percent)
    high = density_from_percent(max_percent)
    if high < low:
        low, high = high, low
    if high <= low:
        high = low + 1e-6
    return low, high


def _normalize(vector, fallback):
    np = load_numpy()
    vector = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-10:
        return np.asarray(fallback, dtype=np.float64)
    return vector / norm


def _rotation_matrix(axis, angle_degrees: float):
    np = load_numpy()
    axis = _normalize(axis, (1.0, 0.0, 0.0))
    angle = math.radians(float(angle_degrees))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    x, y, z = axis
    cross = np.asarray(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=np.float64,
    )
    identity = np.eye(3, dtype=np.float64)
    outer = np.outer(axis, axis)
    return cosine * identity + sine * cross + (1.0 - cosine) * outer


def plane_basis(orientation: str, rotation_u: float, rotation_v: float):
    np = load_numpy()
    orientation = orientation.upper()
    if orientation == "AXIAL":
        axis_u = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
        axis_v = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
        normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    elif orientation == "CORONAL":
        axis_u = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
        axis_v = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
        normal = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
    elif orientation == "SAGITTAL":
        axis_u = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
        axis_v = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
        normal = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
    else:
        raise ValueError(f"Orientación MPR desconocida: {orientation}")

    rotate_u = _rotation_matrix(axis_u, rotation_u)
    axis_v = rotate_u @ axis_v
    normal = rotate_u @ normal

    rotate_v = _rotation_matrix(axis_v, rotation_v)
    axis_u = rotate_v @ axis_u
    normal = rotate_v @ normal

    axis_u = _normalize(axis_u, (1.0, 0.0, 0.0))
    axis_v = _normalize(axis_v - axis_u * float(np.dot(axis_v, axis_u)), (0.0, 1.0, 0.0))
    normal = _normalize(np.cross(axis_u, axis_v), normal)
    return axis_u, axis_v, normal


def _base_geometry(orientation: str, position_percent: float):
    np = load_numpy()
    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm

    x_extent = max(0.0, (x_count - 1) * x_spacing)
    y_extent = max(0.0, (y_count - 1) * y_spacing)
    z_extent = max(0.0, (z_count - 1) * z_spacing)
    position = clamp(float(position_percent), 0.0, 100.0) / 100.0

    orientation = orientation.upper()
    if orientation == "AXIAL":
        center = np.asarray((0.0, 0.0, -0.5 * z_extent + position * z_extent))
        width, height = x_extent, y_extent
        output_width, output_height = x_count, y_count
    elif orientation == "CORONAL":
        center = np.asarray((0.0, -0.5 * y_extent + position * y_extent, 0.0))
        width, height = x_extent, z_extent
        output_width, output_height = x_count, z_count
    elif orientation == "SAGITTAL":
        center = np.asarray((-0.5 * x_extent + position * x_extent, 0.0, 0.0))
        width, height = y_extent, z_extent
        output_width, output_height = y_count, z_count
    else:
        raise ValueError(f"Orientación MPR desconocida: {orientation}")

    largest = max(output_width, output_height, 1)
    if largest > MAX_MPR_AXIS:
        scale = MAX_MPR_AXIS / float(largest)
        output_width = max(2, int(round(output_width * scale)))
        output_height = max(2, int(round(output_height * scale)))

    return center, float(width), float(height), int(output_width), int(output_height)


def _scaled_axial(index: int):
    np = load_numpy()
    index = max(0, min(int(index), RUNTIME.dims_zyx[0] - 1))
    return (
        RUNTIME.volume[index].astype(np.float32, copy=False) * RUNTIME.slopes[index]
        + RUNTIME.intercepts[index]
    )


def _scaled_coronal(index: int):
    np = load_numpy()
    index = max(0, min(int(index), RUNTIME.dims_zyx[1] - 1))
    values = RUNTIME.volume[:, index, :].astype(np.float32, copy=False)
    return values * RUNTIME.slopes[:, None] + RUNTIME.intercepts[:, None]


def _scaled_sagittal(index: int):
    np = load_numpy()
    index = max(0, min(int(index), RUNTIME.dims_zyx[2] - 1))
    values = RUNTIME.volume[:, :, index].astype(np.float32, copy=False)
    return values * RUNTIME.slopes[:, None] + RUNTIME.intercepts[:, None]


def _direct_slice(orientation: str, position_percent: float):
    orientation = orientation.upper()
    z_count, y_count, x_count = RUNTIME.dims_zyx
    fraction = clamp(float(position_percent), 0.0, 100.0) / 100.0
    if orientation == "AXIAL":
        index = int(round(fraction * max(0, z_count - 1)))
        # Keep DICOM column order intact.  Older builds reversed X here to
        # compensate for the now-removed one-axis mesh reflection.
        return _scaled_axial(index)
    if orientation == "CORONAL":
        index = int(round(fraction * max(0, y_count - 1)))
        return _scaled_coronal(index)
    if orientation == "SAGITTAL":
        index = int(round(fraction * max(0, x_count - 1)))
        return _scaled_sagittal(index)
    raise ValueError(f"Orientación MPR desconocida: {orientation}")


def _trilinear_sample(points_xyz_mm):
    """Sample the raw [z,y,x] volume at centered local physical points."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm

    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    x = sign_x * points_xyz_mm[..., 0] / x_spacing + 0.5 * (x_count - 1)
    y = sign_y * points_xyz_mm[..., 1] / y_spacing + 0.5 * (y_count - 1)
    z = sign_z * points_xyz_mm[..., 2] / z_spacing + 0.5 * (z_count - 1)

    valid = (
        (x >= 0.0)
        & (x <= x_count - 1)
        & (y >= 0.0)
        & (y <= y_count - 1)
        & (z >= 0.0)
        & (z <= z_count - 1)
    )

    x0 = np.floor(np.clip(x, 0.0, x_count - 1)).astype(np.int32)
    y0 = np.floor(np.clip(y, 0.0, y_count - 1)).astype(np.int32)
    z0 = np.floor(np.clip(z, 0.0, z_count - 1)).astype(np.int32)
    x1 = np.minimum(x0 + 1, x_count - 1)
    y1 = np.minimum(y0 + 1, y_count - 1)
    z1 = np.minimum(z0 + 1, z_count - 1)

    wx = (x - x0).astype(np.float32, copy=False)
    wy = (y - y0).astype(np.float32, copy=False)
    wz = (z - z0).astype(np.float32, copy=False)

    raw = RUNTIME.volume
    slopes = RUNTIME.slopes
    intercepts = RUNTIME.intercepts

    def voxel(zi, yi, xi):
        return (
            raw[zi, yi, xi].astype(np.float32, copy=False) * slopes[zi]
            + intercepts[zi]
        )

    c000 = voxel(z0, y0, x0)
    c001 = voxel(z0, y0, x1)
    c010 = voxel(z0, y1, x0)
    c011 = voxel(z0, y1, x1)
    c100 = voxel(z1, y0, x0)
    c101 = voxel(z1, y0, x1)
    c110 = voxel(z1, y1, x0)
    c111 = voxel(z1, y1, x1)

    c00 = c000 * (1.0 - wx) + c001 * wx
    c01 = c010 * (1.0 - wx) + c011 * wx
    c10 = c100 * (1.0 - wx) + c101 * wx
    c11 = c110 * (1.0 - wx) + c111 * wx
    c0 = c00 * (1.0 - wy) + c01 * wy
    c1 = c10 * (1.0 - wy) + c11 * wy
    result = c0 * (1.0 - wz) + c1 * wz
    return np.where(valid, result, RUNTIME.density_min).astype(np.float32, copy=False)




def get_cbct_density_info():
    """Public JSON-safe description of the currently loaded CBCT density runtime.

    Values are calibrated DICOM gray values after per-slice slope/intercept.
    They are not advertised as Hounsfield Units for CBCT.
    """
    loaded = RUNTIME.volume is not None and all(int(v) > 0 for v in RUNTIME.dims_zyx)
    root = bpy.data.objects.get(ROOT_NAME)
    return {
        "schema": "dsg.cbct_density_runtime.v1",
        "loaded": bool(loaded),
        "source_kind": str(RUNTIME.source_kind or ""),
        "dims_zyx": [int(v) for v in RUNTIME.dims_zyx],
        "spacing_zyx_mm": [float(v) for v in RUNTIME.spacing_zyx_mm],
        "density_min": float(RUNTIME.density_min),
        "density_max": float(RUNTIME.density_max),
        "auto_low": float(RUNTIME.auto_low),
        "auto_high": float(RUNTIME.auto_high),
        "interpretation": "RELATIVE_CBCT_GRAY_NOT_HU",
        "root_object": root.name if root else None,
    }


def sample_cbct_density_world(points_xyz_world, *, normalized: bool = False, return_valid: bool = False):
    """Sample the existing CBCT runtime at Blender world-space XYZ points.

    This is a public facade over DSG's native trilinear sampler. It does not
    create a new density engine and does not segment trabecular bone.
    When ``return_valid`` is true, returns ``(values, valid_mask)`` so callers
    never confuse points outside the CBCT field-of-view with low-density bone.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    if RUNTIME.volume is None:
        raise RuntimeError("No hay un volumen CBCT cargado")
    arr = np.asarray(points_xyz_world, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape((1, 3))
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError("points_xyz_world debe tener forma Nx3")
    root = bpy.data.objects.get(ROOT_NAME)
    if root is not None:
        inv = root.matrix_world.inverted_safe()
        local = np.empty_like(arr, dtype=np.float32)
        for i, xyz in enumerate(arr):
            p = inv @ Vector((float(xyz[0]), float(xyz[1]), float(xyz[2])))
            local[i] = (p.x, p.y, p.z)
    else:
        local = arr

    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    sign_x, sign_y, sign_z = _dicom_display_signs_xyz()
    x = sign_x * local[:, 0] / x_spacing + 0.5 * (x_count - 1)
    y = sign_y * local[:, 1] / y_spacing + 0.5 * (y_count - 1)
    z = sign_z * local[:, 2] / z_spacing + 0.5 * (z_count - 1)
    valid = (
        (x >= 0.0) & (x <= x_count - 1)
        & (y >= 0.0) & (y <= y_count - 1)
        & (z >= 0.0) & (z <= z_count - 1)
    )

    values = _trilinear_sample(local)
    if normalized:
        low = float(RUNTIME.auto_low)
        high = float(RUNTIME.auto_high)
        if high <= low + 1e-6:
            low = float(RUNTIME.density_min)
            high = float(RUNTIME.density_max)
        denominator = max(high - low, 1e-6)
        values = np.clip((values - low) / denominator, 0.0, 1.0).astype(np.float32, copy=False)
    return (values, valid.astype(bool, copy=False)) if return_valid else values

def _oblique_slice(
    center,
    axis_u,
    axis_v,
    width_mm: float,
    height_mm: float,
    output_width: int,
    output_height: int,
):
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    u_coordinates = np.linspace(
        -0.5 * width_mm,
        0.5 * width_mm,
        output_width,
        dtype=np.float32,
    )
    v_coordinates = np.linspace(
        -0.5 * height_mm,
        0.5 * height_mm,
        output_height,
        dtype=np.float32,
    )
    uu, vv = np.meshgrid(u_coordinates, v_coordinates, indexing="xy")
    points = (
        center[None, None, :]
        + uu[..., None] * axis_u[None, None, :]
        + vv[..., None] * axis_v[None, None, :]
    )
    return _trilinear_sample(points)


def normalize_for_display(values, threshold_min_percent: float, threshold_max_percent: float):
    np = load_numpy()
    low, high = threshold_values(threshold_min_percent, threshold_max_percent)
    normalized = np.clip((values - low) / max(high - low, 1e-6), 0.0, 1.0)
    return normalized.astype(np.float32, copy=False)


def reconstruct_slice(
    orientation: str,
    position_percent: float,
    rotation_u: float,
    rotation_v: float,
    threshold_min_percent: float,
    threshold_max_percent: float,
) -> SliceResult:
    """Return an orthogonal or oblique MPR slice and its plane geometry."""
    if not RUNTIME.is_loaded():
        raise RuntimeError("No hay un volumen DICOM cargado")

    center, width, height, output_width, output_height = _base_geometry(
        orientation,
        position_percent,
    )
    axis_u, axis_v, normal = plane_basis(orientation, rotation_u, rotation_v)

    if abs(rotation_u) < 1e-7 and abs(rotation_v) < 1e-7:
        values = _direct_slice(orientation, position_percent)
        # Direct slices retain native dimensions; resize only if a future volume
        # exceeds MAX_MPR_AXIS. Nearest-neighbour indexing avoids SciPy.
        if values.shape != (output_height, output_width):
            np = load_numpy()
            row_indices = np.linspace(0, values.shape[0] - 1, output_height).round().astype(int)
            col_indices = np.linspace(0, values.shape[1] - 1, output_width).round().astype(int)
            values = values[row_indices[:, None], col_indices[None, :]]
    else:
        values = _oblique_slice(
            center,
            axis_u,
            axis_v,
            width,
            height,
            output_width,
            output_height,
        )

    normalized = normalize_for_display(
        values,
        threshold_min_percent,
        threshold_max_percent,
    )
    return SliceResult(
        orientation=orientation.upper(),
        values=values,
        normalized=normalized,
        center_xyz_mm=center,
        axis_u_xyz=axis_u,
        axis_v_xyz=axis_v,
        normal_xyz=normal,
        width_mm=width,
        height_mm=height,
        output_width=output_width,
        output_height=output_height,
    )

# =============================================================================
# MODULE: scene.py
# =============================================================================

from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


def _dicom_display_signs_xyz() -> tuple[float, float, float]:
    """Return the root-local signs for DICOM voxel axes without reflections.

    DICOM ``ImageOrientationPatient`` is already the physical authority for
    patient laterality.  Older DSG builds additionally multiplied local X by
    ``-1``.  That second, one-axis reflection mirrored every generated CBCT
    surface (threshold STL, DentalSegmentator and UniversalLab meshes) even
    though the labelmap itself was correct.

    Keep the voxel-to-local transform right-handed and let
    :func:`apply_patient_orientation` apply the DICOM direction cosines.  A
    scanner-specific in-plane display normalization may flip X *and* Y together
    (a 180-degree rotation), but DSG must never introduce a single-axis mirror.
    """
    return (1.0, 1.0, 1.0)


def _collection_in_tree(root: bpy.types.Collection, target: bpy.types.Collection) -> bool:
    """Return True when *target* belongs to the current scene collection tree.

    Blender datablocks can survive after their collection was unlinked from a
    scene.  Reusing such a collection makes newly-created objects exist in
    ``bpy.data`` but not in the active ViewLayer, which then makes
    ``Object.select_set`` raise "cannot be selected because it is not in View
    Layer".
    """
    if root == target:
        return True
    for child in getattr(root, "children", ()):
        if _collection_in_tree(child, target):
            return True
    return False


def _layer_collection_path(layer_collection, target_collection):
    """Return the LayerCollection path leading to *target_collection*."""
    if getattr(layer_collection, "collection", None) == target_collection:
        return [layer_collection]
    for child in getattr(layer_collection, "children", ()):
        path = _layer_collection_path(child, target_collection)
        if path:
            return [layer_collection] + path
    return None


def ensure_collection_in_view_layer(context, collection: bpy.types.Collection) -> bool:
    """Make an existing collection usable from the active Blender ViewLayer.

    This is intentionally idempotent. It repairs stale/orphaned DSG collections
    left by Undo, add-on reloads or previous DSG versions and also unhides the
    LayerCollection path required to select newly-created clinical objects.
    """
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    view_layer = getattr(context, "view_layer", None)
    if scene is None or collection is None:
        return False

    if not _collection_in_tree(scene.collection, collection):
        try:
            scene.collection.children.link(collection)
        except RuntimeError:
            # It may have become linked between the test and the link call.
            pass

    try:
        collection.hide_viewport = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if view_layer is not None:
        # Force Blender to synchronize LayerCollection nodes after a new link.
        try:
            view_layer.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        path = _layer_collection_path(getattr(view_layer, "layer_collection", None), collection)
        if path:
            for layer_collection in path:
                try:
                    layer_collection.exclude = False
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                try:
                    layer_collection.hide_viewport = False
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                view_layer.update()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        return collection.name in {c.name for c in scene.collection.children_recursive}
    except Exception:
        return _collection_in_tree(scene.collection, collection)


def object_in_view_layer(context, obj: bpy.types.Object) -> bool:
    if obj is None:
        return False
    view_layer = getattr(context or bpy.context, "view_layer", None)
    if view_layer is None:
        return False
    try:
        return view_layer.objects.get(obj.name) is obj
    except Exception:
        try:
            return obj.name in view_layer.objects
        except Exception:
            return False


def ensure_object_in_view_layer(context, obj: bpy.types.Object) -> bool:
    """Repair collection linkage for *obj* before selection/activation.

    We first expose all of the object's existing collections.  If none of them
    belongs to the scene (possible after Undo/reload), the object is linked to
    DSG's canonical DICOM collection.  This avoids duplicating objects while
    guaranteeing that every generated tooth can be selected.
    """
    context = context or bpy.context
    if obj is None:
        return False
    scene = getattr(context, "scene", None)
    if scene is None:
        return False

    linked_here = False
    for collection in list(getattr(obj, "users_collection", ())):
        if _collection_in_tree(scene.collection, collection):
            linked_here = True
        ensure_collection_in_view_layer(context, collection)

    if not linked_here:
        collection = get_collection()
        ensure_collection_in_view_layer(context, collection)
        ensure_linked(collection, obj)

    try:
        context.view_layer.update()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return object_in_view_layer(context, obj)


def safe_select_object(context, obj: bpy.types.Object, *, make_active: bool = True, deselect_others: bool = False) -> bool:
    """Select an object only after guaranteeing active ViewLayer membership."""
    context = context or bpy.context
    if not ensure_object_in_view_layer(context, obj):
        return False
    if deselect_others:
        for selected in list(getattr(context, "selected_objects", ())):
            try:
                selected.select_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        obj.hide_viewport = False
        obj.hide_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        obj.select_set(True)
    except RuntimeError:
        # One more depsgraph/view-layer synchronization cures the short window
        # immediately after relinking a collection in Blender 5.x.
        try:
            context.view_layer.update()
            obj.select_set(True)
        except Exception:
            return False
    except Exception:
        return False
    if make_active:
        try:
            context.view_layer.objects.active = obj
        except Exception:
            return False
    return True


def get_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
    # IMPORTANT: an existing collection datablock is not necessarily linked to
    # the current scene (Undo/reload/old DSG versions can orphan it). Always
    # repair that relation before creating/selecting clinical objects.
    try:
        ensure_collection_in_view_layer(bpy.context, collection)
    except Exception:
        scene = getattr(bpy.context, "scene", None)
        if scene is not None and not _collection_in_tree(scene.collection, collection):
            scene.collection.children.link(collection)
    return collection


def ensure_linked(collection: bpy.types.Collection, obj: bpy.types.Object) -> None:
    if collection.objects.get(obj.name) is None:
        collection.objects.link(obj)


def get_root(collection: bpy.types.Collection) -> bpy.types.Object:
    root = bpy.data.objects.get(ROOT_NAME)
    if root is None:
        root = bpy.data.objects.new(ROOT_NAME, None)
        ensure_linked(collection, root)
    # The root is the user-facing transform control for the complete dataset.
    # Rotating it moves the volume, box, and all MPR planes together natively.
    root.empty_display_type = "CUBE"
    if RUNTIME.is_loaded():
        z_count, y_count, x_count = RUNTIME.dims_zyx
        z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
        root.empty_display_size = 0.5 * max(
            x_count * x_spacing,
            y_count * y_spacing,
            z_count * z_spacing,
            1.0,
        )
    else:
        root.empty_display_size = 10.0
    root.show_in_front = True
    root.hide_render = True
    root.hide_select = False
    return root


def apply_patient_orientation(root: bpy.types.Object) -> None:
    """Orient local voxel axes using DICOM direction cosines.

    Many dental scanners (including several Planmeca exports) encode the in-plane
    X and Y directions both reversed. That is a valid DICOM orientation, but in
    Blender it looks like an unwanted 180-degree rotation around Z. By default
    we choose the equivalent in-plane orientation whose X/Y axes point closest
    to Blender +X/+Y. Flipping both axes preserves the slice normal and the
    right-handed coordinate system. The user can disable this correction.

    IMPORTANT: this function may only preserve orientation or rotate both
    in-plane axes together.  A single-axis sign change would be a reflection
    and would invert patient laterality.
    """
    orientation = RUNTIME.orientation_xyz
    if orientation is None:
        root.matrix_world = Matrix.Identity(4)
        return

    try:
        np = load_numpy()
        display_orientation = np.asarray(orientation, dtype=np.float64).copy()
        props = getattr(getattr(bpy.context, "scene", None), "dicom_wizard_pro", None)
        correct_180 = True if props is None else bool(getattr(props, "correct_inplane_180", True))
        if correct_180:
            direct_score = float(display_orientation[0, 0] + display_orientation[1, 1])
            flipped_score = float(-display_orientation[0, 0] - display_orientation[1, 1])
            if flipped_score > direct_score + 1e-6:
                display_orientation[:, 0] *= -1.0
                display_orientation[:, 1] *= -1.0
        root.matrix_world = Matrix(display_orientation.tolist()).to_4x4()
    except Exception:
        root.matrix_world = Matrix.Identity(4)


def _new_or_replace_mesh_object(
    object_name: str,
    mesh_name: str,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
) -> bpy.types.Object:
    obj = bpy.data.objects.get(object_name)
    old_mesh = None
    if obj is None or obj.type != "MESH":
        mesh = bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(object_name, mesh)
        ensure_linked(collection, obj)
    else:
        old_mesh = obj.data
        mesh = bpy.data.meshes.new(mesh_name)
        obj.data = mesh
        ensure_linked(collection, obj)
    obj.parent = parent
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    return obj


def create_bounding_box(collection: bpy.types.Collection, root: bpy.types.Object) -> bpy.types.Object:
    z_count, y_count, x_count = RUNTIME.dims_zyx
    z_spacing, y_spacing, x_spacing = RUNTIME.spacing_zyx_mm
    width = max(x_spacing, x_count * x_spacing)
    height = max(y_spacing, y_count * y_spacing)
    depth = max(z_spacing, z_count * z_spacing)
    hx, hy, hz = width * 0.5, height * 0.5, depth * 0.5

    obj = _new_or_replace_mesh_object(
        BOUNDING_BOX_NAME,
        BOUNDING_BOX_NAME + "_MESH",
        collection,
        root,
    )
    vertices = [
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    obj.data.from_pydata(vertices, edges, [])
    obj.data.update()
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_render = True
    obj.hide_select = True
    return obj


def _get_image(name: str, width: int, height: int) -> bpy.types.Image:
    image = bpy.data.images.get(name)
    if image is not None and tuple(image.size) != (width, height):
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(
            name,
            width=width,
            height=height,
            alpha=True,
            float_buffer=False,
        )
    try:
        image.colorspace_settings.name = "Non-Color"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return image


def _set_image_pixels(image: bpy.types.Image, pixels) -> None:
    """Upload pixels without changing the DICOM row direction.

    DICOM row 0 and voxel y=0 remain on the same side of the plane. The viewing
    camera may change, but the underlying raster is never mirrored.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    pixels = np.asarray(pixels, dtype=np.float32)
    if pixels.ndim == 2:
        height, width = pixels.shape
        rgba = np.empty((height, width, 4), dtype=np.float32)
        rgba[..., 0] = pixels
        rgba[..., 1] = pixels
        rgba[..., 2] = pixels
        rgba[..., 3] = 1.0
    elif pixels.ndim == 3 and pixels.shape[-1] in (3, 4):
        height, width = pixels.shape[:2]
        rgba = np.ones((height, width, 4), dtype=np.float32)
        rgba[..., :pixels.shape[-1]] = pixels
    else:
        raise ValueError(f"Formato de imagen no compatible: {pixels.shape}")
    image.pixels.foreach_set(rgba.ravel())
    image.update()


def _get_plane_material(name: str, image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    texture = nodes.get("DICOM_IMAGE_TEXTURE")
    emission = nodes.get("DICOM_IMAGE_EMISSION")
    output = nodes.get("DICOM_IMAGE_OUTPUT")
    if texture is None or emission is None or output is None:
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        emission = nodes.new("ShaderNodeEmission")
        texture = nodes.new("ShaderNodeTexImage")
        output.name = "DICOM_IMAGE_OUTPUT"
        emission.name = "DICOM_IMAGE_EMISSION"
        texture.name = "DICOM_IMAGE_TEXTURE"
        links.new(texture.outputs["Color"], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], output.inputs["Surface"])
        texture.location = (-250, 0)
        emission.location = (0, 0)
        output.location = (230, 0)

    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    return material


def _build_plane_mesh(obj: bpy.types.Object, result, material: bpy.types.Material) -> None:
    """Build a plane around its own origin and place it with matrix_local.

    Keeping the mesh centred on the object origin makes Blender's native G/R/S
    gizmos intuitive. The object matrix is also the single source of truth used
    by the real-time MPR handler.
    """
    half_width = result.width_mm * 0.5
    half_height = result.height_mm * 0.5
    vertices = [
        (-half_width, -half_height, 0.0),
        (half_width, -half_height, 0.0),
        (half_width, half_height, 0.0),
        (-half_width, half_height, 0.0),
    ]
    obj.data.from_pydata(vertices, [], [(0, 1, 2, 3)])
    obj.data.update()

    uv_layer = obj.data.uv_layers.new(name="UVMap")
    uv_coordinates = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    polygon = obj.data.polygons[0]
    for loop_index, coordinates in zip(polygon.loop_indices, uv_coordinates):
        uv_layer.data[loop_index].uv = coordinates

    obj.data.materials.clear()
    obj.data.materials.append(material)

    center = result.center_xyz_mm
    axis_u = result.axis_u_xyz
    axis_v = result.axis_v_xyz
    normal = result.normal_xyz
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_local = Matrix((
        (float(axis_u[0]), float(axis_v[0]), float(normal[0]), float(center[0])),
        (float(axis_u[1]), float(axis_v[1]), float(normal[1]), float(center[1])),
        (float(axis_u[2]), float(axis_v[2]), float(normal[2]), float(center[2])),
        (0.0, 0.0, 0.0, 1.0),
    ))
    obj["dicom_plane_width_mm"] = float(result.width_mm)
    obj["dicom_plane_height_mm"] = float(result.height_mm)
    obj.show_in_front = True
    obj.hide_render = False
    obj.hide_select = False


def _plane_parameters(props, orientation: str) -> tuple[float, float, float]:
    orientation = orientation.upper()
    if orientation == "AXIAL":
        return props.axial_position, props.axial_rotation_u, props.axial_rotation_v
    if orientation == "CORONAL":
        return props.coronal_position, props.coronal_rotation_u, props.coronal_rotation_v
    return props.sagittal_position, props.sagittal_rotation_u, props.sagittal_rotation_v


def refresh_plane(context: bpy.types.Context, orientation: str) -> bpy.types.Object:
    props = context.scene.dicom_wizard_pro
    spec = PLANE_SPECS[orientation]
    position, rotation_u, rotation_v = _plane_parameters(props, orientation)
    result = reconstruct_slice(
        orientation,
        position,
        rotation_u,
        rotation_v,
        props.threshold_min_percent,
        props.threshold_max_percent,
    )

    collection = get_collection()
    root = get_root(collection)
    image = _get_image(spec["image"], result.output_width, result.output_height)
    display_pixels = compose_segmentation_overlay(
        result.normalized,
        result.center_xyz_mm, result.axis_u_xyz, result.axis_v_xyz,
        result.width_mm, result.height_mm,
        result.output_width, result.output_height, props,
    )
    _set_image_pixels(image, display_pixels)
    material = _get_plane_material(spec["material"], image)
    obj = _new_or_replace_mesh_object(
        spec["object"],
        spec["mesh"],
        collection,
        root,
    )
    RUNTIME.transform_handler_lock = True
    try:
        _build_plane_mesh(obj, result, material)
        RUNTIME.plane_matrix_cache[orientation] = _matrix_basis_signature(obj)
    finally:
        RUNTIME.transform_handler_lock = False
    return obj


def _matrix_basis_signature(obj: bpy.types.Object) -> tuple[float, ...]:
    """Return a stable signature for an object's user-editable transform."""
    matrix = obj.matrix_basis
    return tuple(round(float(matrix[row][column]), 7) for row in range(4) for column in range(4))


def _plane_pose_from_object(orientation: str):
    """Read the current plane pose in DICOM-root local millimetres."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    spec = PLANE_SPECS[orientation]
    obj = bpy.data.objects.get(spec["object"])
    root = bpy.data.objects.get(ROOT_NAME)
    if obj is None or root is None:
        raise RuntimeError(f"No existe el plano {orientation}")

    local_matrix = root.matrix_world.inverted_safe() @ obj.matrix_world
    axis_u_raw = np.asarray(
        (local_matrix[0][0], local_matrix[1][0], local_matrix[2][0]),
        dtype=np.float64,
    )
    axis_v_raw = np.asarray(
        (local_matrix[0][1], local_matrix[1][1], local_matrix[2][1]),
        dtype=np.float64,
    )
    scale_u = max(float(np.linalg.norm(axis_u_raw)), 1e-8)
    scale_v = max(float(np.linalg.norm(axis_v_raw)), 1e-8)
    axis_u = axis_u_raw / scale_u
    axis_v = axis_v_raw - axis_u * float(np.dot(axis_v_raw, axis_u))
    axis_v = _normalize(axis_v, (0.0, 1.0, 0.0))
    normal = _normalize(np.cross(axis_u, axis_v), (0.0, 0.0, 1.0))

    center = np.asarray(
        (local_matrix[0][3], local_matrix[1][3], local_matrix[2][3]),
        dtype=np.float64,
    )
    base_width = float(obj.get("dicom_plane_width_mm", max(obj.dimensions.x, 1.0)))
    base_height = float(obj.get("dicom_plane_height_mm", max(obj.dimensions.y, 1.0)))
    width = max(1e-4, base_width * scale_u)
    height = max(1e-4, base_height * scale_v)
    return obj, center, axis_u, axis_v, normal, width, height


def _pose_output_shape(width_mm: float, height_mm: float, max_axis: int) -> tuple[int, int]:
    """Choose an MPR resolution from physical size and source voxel spacing."""
    min_spacing = max(1e-6, min(RUNTIME.spacing_zyx_mm))
    output_width = max(2, int(round(width_mm / min_spacing)) + 1)
    output_height = max(2, int(round(height_mm / min_spacing)) + 1)
    largest = max(output_width, output_height)
    if largest > max_axis:
        factor = max_axis / float(largest)
        output_width = max(2, int(round(output_width * factor)))
        output_height = max(2, int(round(output_height * factor)))
    return output_width, output_height


def _safe_review_refresh_plane_image(
    context: bpy.types.Context,
    orientation: str,
    *,
    max_axis: int = SAFE_REVIEW_MAX_AXIS,
) -> bpy.types.Object:
    """Reconstruct into a new image datablock, then atomically swap texture.

    The currently displayed image is never resized, removed, or overwritten.
    This avoids racing Blender's material renderer while it acquires the image
    buffer on another worker thread.
    """
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    orientation = str(orientation).upper()
    spec = PLANE_SPECS[orientation]
    props = context.scene.dicom_wizard_pro

    obj, center, axis_u, axis_v, _normal, width, height = (
        _plane_pose_from_object(orientation)
    )
    output_width, output_height = _pose_output_shape(
        width,
        height,
        max_axis,
    )

    values = _oblique_slice(
        center,
        axis_u,
        axis_v,
        width,
        height,
        output_width,
        output_height,
    )
    normalized = normalize_for_display(
        values,
        props.threshold_min_percent,
        props.threshold_max_percent,
    )
    display_pixels = compose_segmentation_overlay(
        normalized,
        center,
        axis_u,
        axis_v,
        width,
        height,
        output_width,
        output_height,
        props,
    )

    generation = int(
        _SAFE_REVIEW_REFRESH_GENERATION.get(orientation, 0)
    )
    unique_name = (
        f"{SAFE_REVIEW_IMAGE_PREFIX}{orientation}_{generation:06d}_"
        f"{time.monotonic_ns()}"
    )
    image = bpy.data.images.new(
        unique_name,
        width=output_width,
        height=output_height,
        alpha=True,
        float_buffer=False,
    )
    try:
        image.colorspace_settings.name = "Non-Color"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Populate the new, unreferenced image completely before assigning it.
    _set_image_pixels(image, display_pixels)

    material = _get_plane_material(spec["material"], image)
    if obj.data is not None:
        if len(obj.data.materials) == 0:
            obj.data.materials.append(material)
        elif obj.data.materials[0] != material:
            obj.data.materials[0] = material

    obj["dicom_review_image"] = image.name
    obj["dicom_review_image_generation"] = generation
    return obj


def _safe_review_request_realtime_refresh(
    orientation: str,
) -> None:
    """Request a safe real-time preview without mutating visible image buffers.

    Property sliders may emit many updates per second. The plane geometry moves
    immediately, while this timer creates immutable low-resolution images at a
    bounded rate. Once interaction stops, one full-resolution image is built.
    """
    orientation = str(orientation).upper()
    if orientation not in _SAFE_REVIEW_REFRESH_GENERATION:
        return

    scene = getattr(bpy.context, "scene", None)
    props = getattr(scene, "dicom_wizard_pro", None)
    if (
        props is None
        or not bool(props.get("safe_mpr_active", False))
        or not RUNTIME.is_loaded()
    ):
        return

    now = time.monotonic()
    _SAFE_REVIEW_REFRESH_GENERATION[orientation] += 1
    _SAFE_REVIEW_LAST_CHANGE_TIME[orientation] = now

    if _SAFE_REVIEW_TIMER_RUNNING[orientation]:
        return

    _SAFE_REVIEW_TIMER_RUNNING[orientation] = True

    def _run():
        try:
            scene = getattr(bpy.context, "scene", None)
            props = getattr(scene, "dicom_wizard_pro", None)
            if (
                props is None
                or not bool(props.get("safe_mpr_active", False))
                or not RUNTIME.is_loaded()
            ):
                _SAFE_REVIEW_TIMER_RUNNING[orientation] = False
                return None

            now = time.monotonic()
            generation = int(
                _SAFE_REVIEW_REFRESH_GENERATION.get(orientation, 0)
            )
            changed_at = float(
                _SAFE_REVIEW_LAST_CHANGE_TIME.get(orientation, 0.0)
            )
            last_preview_at = float(
                _SAFE_REVIEW_LAST_PREVIEW_TIME.get(orientation, 0.0)
            )

            preview_needed = (
                generation
                != _SAFE_REVIEW_PREVIEW_GENERATION.get(orientation, -1)
                and now - last_preview_at
                >= SAFE_REVIEW_PREVIEW_INTERVAL_SECONDS
            )
            if preview_needed:
                _safe_review_refresh_plane_image(
                    bpy.context,
                    orientation,
                    max_axis=SAFE_REVIEW_PREVIEW_MAX_AXIS,
                )
                _SAFE_REVIEW_PREVIEW_GENERATION[orientation] = generation
                _SAFE_REVIEW_LAST_PREVIEW_TIME[orientation] = now
                props.status = (
                    f"Plano "
                    f"{MPR_ROTATION_SPECS[orientation]['plane_axis']} "
                    "· vista previa"
                )
                force_ui_redraw()

            interaction_finished = (
                now - changed_at >= SAFE_REVIEW_FINAL_IDLE_SECONDS
            )
            final_needed = (
                interaction_finished
                and generation
                != _SAFE_REVIEW_FINAL_GENERATION.get(orientation, -1)
            )
            if final_needed:
                _safe_review_refresh_plane_image(
                    bpy.context,
                    orientation,
                    max_axis=SAFE_REVIEW_MAX_AXIS,
                )
                _SAFE_REVIEW_PREVIEW_GENERATION[orientation] = generation
                _SAFE_REVIEW_FINAL_GENERATION[orientation] = generation
                props.status = (
                    f"Plano "
                    f"{MPR_ROTATION_SPECS[orientation]['plane_axis']} "
                    "actualizado"
                )
                force_ui_redraw()

            # Stop only when the latest generation has received full quality.
            if (
                interaction_finished
                and _SAFE_REVIEW_FINAL_GENERATION.get(orientation, -1)
                == _SAFE_REVIEW_REFRESH_GENERATION.get(orientation, 0)
            ):
                _SAFE_REVIEW_TIMER_RUNNING[orientation] = False
                return None

            return 0.035
        except Exception as exc:
            _SAFE_REVIEW_TIMER_RUNNING[orientation] = False
            try:
                bpy.context.scene.dicom_wizard_pro.status = (
                    f"No se pudo actualizar el plano: {exc}"
                )
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            print("DICOM safe realtime review refresh error:", repr(exc))
            return None

    try:
        lifecycle.register_timer(_run, first_interval=0.01)
    except Exception:
        _SAFE_REVIEW_TIMER_RUNNING[orientation] = False


def _safe_review_schedule_image_refresh(
    orientation: str,
    *,
    final_axis: int = SAFE_REVIEW_MAX_AXIS,
) -> None:
    """Debounce a safe immutable texture rebuild after modal interaction."""
    orientation = str(orientation).upper()
    if orientation not in _SAFE_REVIEW_REFRESH_GENERATION:
        return

    _SAFE_REVIEW_REFRESH_GENERATION[orientation] += 1
    generation = _SAFE_REVIEW_REFRESH_GENERATION[orientation]

    def _run():
        try:
            scene = getattr(bpy.context, "scene", None)
            props = getattr(scene, "dicom_wizard_pro", None)
            if (
                props is None
                or not bool(props.get("safe_mpr_active", False))
                or generation
                != _SAFE_REVIEW_REFRESH_GENERATION.get(orientation, -1)
            ):
                return None

            _safe_review_refresh_plane_image(
                bpy.context,
                orientation,
                max_axis=final_axis,
            )
            props.status = (
                f"Plano {MPR_ROTATION_SPECS[orientation]['plane_axis']} "
                "actualizado"
            )
            force_ui_redraw()
        except Exception as exc:
            try:
                bpy.context.scene.dicom_wizard_pro.status = (
                    f"No se pudo actualizar el plano: {exc}"
                )
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            print("DICOM safe review image refresh error:", repr(exc))
        return None

    try:
        lifecycle.register_timer(
            _run,
            first_interval=SAFE_REVIEW_REFRESH_DELAY_SECONDS,
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def refresh_plane_image_from_object(
    context: bpy.types.Context,
    orientation: str,
    *,
    max_axis: int = MAX_MPR_AXIS,
) -> bpy.types.Object:
    """Resample the volume using the plane's actual viewport transform."""
    props = context.scene.dicom_wizard_pro
    spec = PLANE_SPECS[orientation]
    obj, center, axis_u, axis_v, _normal, width, height = _plane_pose_from_object(orientation)
    output_width, output_height = _pose_output_shape(width, height, max_axis)
    values = _oblique_slice(
        center,
        axis_u,
        axis_v,
        width,
        height,
        output_width,
        output_height,
    )
    normalized = normalize_for_display(
        values,
        props.threshold_min_percent,
        props.threshold_max_percent,
    )
    display_pixels = compose_segmentation_overlay(
        normalized, center, axis_u, axis_v, width, height,
        output_width, output_height, props,
    )
    image = _get_image(spec["image"], output_width, output_height)
    _set_image_pixels(image, display_pixels)
    _get_plane_material(spec["material"], image)
    # The radiographic quad layout uses a flat display proxy for each MPR.
    # Keep its physical aspect ratio synchronized while the true cutting plane
    # moves or rotates inside the volume.
    sync_function = globals().get("_sync_radiographic_proxy")
    if callable(sync_function):
        try:
            sync_function(orientation)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return obj


def refresh_plane_images_from_objects(
    context: bpy.types.Context,
    *,
    all_planes: bool | None = None,
    max_axis: int = MAX_MPR_AXIS,
) -> None:
    props = context.scene.dicom_wizard_pro
    show_all = props.show_all_planes if all_planes is None else bool(all_planes)
    orientations = tuple(PLANE_SPECS) if show_all else (props.active_plane,)
    for orientation in orientations:
        if bpy.data.objects.get(PLANE_SPECS[orientation]["object"]) is not None:
            refresh_plane_image_from_object(context, orientation, max_axis=max_axis)
    update_visibility(context)


def update_visibility(context: bpy.types.Context) -> None:
    props = context.scene.dicom_wizard_pro
    segmentation_active = bool(_ASYNC_SEGMENTATION.get("active"))
    in_threshold_preview = int(getattr(props, "step", 1)) == 3
    solid_ready = _surface_preview_matches(props) if in_threshold_preview else False

    # Blender 5.1 production UI exposes a single preview mode: SURFACE.
    # While that low-resolution surface is rebuilding we keep the volume visible;
    # as soon as the surface is ready the volume is hidden automatically.
    if segmentation_active:
        # The OpenVDB DICOM volume and its MPR helpers are diagnostic proxies,
        # not semantic anatomy.  Keeping them visible while the dual-engine
        # workflow creates teeth, jaws and canal looks like an unwanted soft-
        # tissue segmentation and obscures the clinical meshes.
        volume_visible = False
    elif in_threshold_preview:
        volume_visible = bool(props.show_volume) and not solid_ready
    else:
        volume_visible = bool(props.show_volume)

    volume = bpy.data.objects.get(VOLUME_OBJECT_NAME)
    if volume is not None:
        volume.hide_set(not volume_visible)
        volume.hide_viewport = not volume_visible
        volume.hide_render = not volume_visible

    preview_surface = bpy.data.objects.get(SURFACE_PREVIEW_OBJECT_NAME)
    if preview_surface is not None:
        surface_visible = not segmentation_active and in_threshold_preview and solid_ready
        preview_surface.hide_set(not surface_visible)
        preview_surface.hide_viewport = not surface_visible
        preview_surface.hide_render = True

    active = props.active_plane
    for orientation, spec in PLANE_SPECS.items():
        obj = bpy.data.objects.get(spec["object"])
        if obj is None:
            continue
        visible = (
            not segmentation_active
            and props.show_planes
            and (props.show_all_planes or orientation == active)
        )
        obj.hide_set(not visible)
        obj.hide_viewport = not visible
        obj.hide_render = not visible

    box = bpy.data.objects.get(BOUNDING_BOX_NAME)
    if box is not None:
        box_visible = not segmentation_active and bool(props.show_box)
        box.hide_set(not box_visible)
        box.hide_viewport = not box_visible


def refresh_planes(context: bpy.types.Context, *, all_planes: bool | None = None) -> None:
    props = context.scene.dicom_wizard_pro
    if not RUNTIME.is_loaded():
        return
    show_all = props.show_all_planes if all_planes is None else bool(all_planes)
    orientations = tuple(PLANE_SPECS) if show_all else (props.active_plane,)
    for orientation in orientations:
        refresh_plane(context, orientation)
    update_visibility(context)


def refresh_volume_material(
    context: bpy.types.Context, *, allow_rebuild: bool = False
) -> bool:
    if RUNTIME.undo_in_progress:
        return False
    props = context.scene.dicom_wizard_pro
    step = int(getattr(props, "step", 1))
    segmentation_threshold = None
    display_min = float(props.threshold_min_percent)
    display_max = float(props.threshold_max_percent)
    if step >= 3 and bool(getattr(props, "auto_thresholds_ready", False)):
        structure = str(getattr(props, "segmentation_structure", "BONE")).upper()
        low_density = float(props.auto_range_low)
        high_density = float(props.auto_range_high)
        if structure == "BONE":
            # Combined bone+teeth is a one-sided mineralized class.
            segmentation_threshold = low_density
        else:
            # Teeth and bone-only are true bounded density bands. Use the
            # regular volume window so the preview matches both thresholds.
            denominator = max(float(RUNTIME.density_max - RUNTIME.density_min), 1e-6)
            display_min = 100.0 * (low_density - float(RUNTIME.density_min)) / denominator
            display_max = 100.0 * (high_density - float(RUNTIME.density_min)) / denominator
            display_min = clamp(display_min, 0.0, 100.0)
            display_max = clamp(display_max, 0.0, 100.0)
    preview_opacity = (
        float(getattr(props, "preview_volume_opacity", 0.10))
        if step >= 3
        else float(props.volume_opacity)
    )
    return update_volume_material(
        display_min,
        display_max,
        preview_opacity,
        segmentation_threshold_density=segmentation_threshold,
        preview_shell_width_percent=float(getattr(props, "preview_shell_width_percent", 0.8)),
        preview_surface_emphasis=float(getattr(props, "preview_surface_emphasis", 6.0)),
        allow_rebuild=allow_rebuild,
    )


def create_viewer_scene(context: bpy.types.Context, *, include_volume: bool = True) -> None:
    props = context.scene.dicom_wizard_pro
    collection = get_collection()
    root = get_root(collection)
    apply_patient_orientation(root)
    root["dicom_alignment_policy"] = "single shared parent transform"
    root["dicom_children_must_not_bake_orientation"] = True
    create_bounding_box(collection, root)
    if include_volume and RUNTIME.vdb_path:
        create_volume_object(collection, root)
        refresh_volume_material(context)
    refresh_planes(context, all_planes=True)
    # Build all three planes from one shared anatomical frame. This keeps them
    # mutually perpendicular even when the acquisition volume was tilted.
    for orientation in PLANE_SPECS:
        _apply_axis_controls_to_plane(context, orientation, schedule_refresh=False)
    refresh_plane_images_from_objects(context, all_planes=True, max_axis=MAX_MPR_AXIS)
    update_visibility(context)
    set_viewport_material_mode(context)
    frame_viewer(context)


def set_viewport_material_mode(context: bpy.types.Context) -> None:
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        try:
            area.spaces.active.shading.type = "MATERIAL"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def frame_viewer(context: bpy.types.Context) -> None:
    target = bpy.data.objects.get(ROOT_NAME) or bpy.data.objects.get(BOUNDING_BOX_NAME)
    if target is None:
        return
    for selected in context.selected_objects:
        selected.select_set(False)
    target.hide_select = False
    target.select_set(True)
    context.view_layer.objects.active = target

    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        region = next((region for region in area.regions if region.type == "WINDOW"), None)
        if region is None:
            continue
        try:
            with context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_selected(use_all_regions=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        break


def cleanup_scene() -> None:
    try:
        _remove_radiographic_proxies()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is not None:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)

    for image in list(bpy.data.images):
        if (
            image.name.startswith(SAFE_REVIEW_IMAGE_PREFIX)
            and image.users == 0
        ):
            try:
                bpy.data.images.remove(image)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    for spec in PLANE_SPECS.values():
        image = bpy.data.images.get(spec["image"])
        if image is not None and image.users == 0:
            bpy.data.images.remove(image)
        material = bpy.data.materials.get(spec["material"])
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)

    volume_data = bpy.data.volumes.get(VOLUME_DATA_NAME)
    if volume_data is not None and volume_data.users == 0:
        bpy.data.volumes.remove(volume_data)
    volume_material = bpy.data.materials.get(VOLUME_MATERIAL_NAME)
    if volume_material is not None and volume_material.users == 0:
        bpy.data.materials.remove(volume_material)
    preview_material = bpy.data.materials.get(SURFACE_PREVIEW_MATERIAL_NAME)
    if preview_material is not None and preview_material.users == 0:
        bpy.data.materials.remove(preview_material)

    mesh_prefixes = (
        SURFACE_PREVIEW_MESH_NAME,
        BOUNDING_BOX_NAME + "_MESH",
        RADIOGRAPHIC_PROXY_MESH_PREFIX,
        *(spec["mesh"] for spec in PLANE_SPECS.values()),
    )
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0 and any(mesh.name.startswith(prefix) for prefix in mesh_prefixes):
            bpy.data.meshes.remove(mesh)


def update_density_labels(props) -> None:
    low = RUNTIME.density_min + (
        max(0.0, min(100.0, props.threshold_min_percent)) / 100.0
    ) * (RUNTIME.density_max - RUNTIME.density_min)
    high = RUNTIME.density_min + (
        max(0.0, min(100.0, props.threshold_max_percent)) / 100.0
    ) * (RUNTIME.density_max - RUNTIME.density_min)
    props.current_density_min = min(low, high)
    props.current_density_max = max(low, high)

# =============================================================================
# MODULE: updates.py
# =============================================================================

