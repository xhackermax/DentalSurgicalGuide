import math
from typing import Iterable

import bpy


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def safe_float(value, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def as_tuple3(value: Iterable[float] | None, default=(0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    try:
        values = tuple(float(component) for component in value)
        if len(values) >= 3 and all(math.isfinite(component) for component in values[:3]):
            return values[:3]
    except (TypeError, ValueError):
        pass
    return tuple(float(component) for component in default)


def force_ui_redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def progress_begin(context: bpy.types.Context, maximum: int = 100) -> None:
    try:
        context.window_manager.progress_begin(0, maximum)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def progress_update(context: bpy.types.Context, value: int) -> None:
    try:
        context.window_manager.progress_update(value)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    force_ui_redraw()


def progress_end(context: bpy.types.Context) -> None:
    try:
        context.window_manager.progress_end()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

# =============================================================================
# MODULE: dicom_io.py
# =============================================================================

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


ProgressCallback = Callable[[int, int, str], None]

# v9.2.17: opening a CBCT must never perform the full decode/Torch/VDB work
# on Blender's UI thread. Header discovery is cached and pixel decoding runs
# in a pure I/O/NumPy worker; only scene commits happen in modal timer ticks.
_HEADER_CACHE_LOCK = threading.RLock()
_HEADER_CACHE: dict[tuple[str, bool], tuple[int, int, Any, bool]] = {}
_HEADER_CACHE_MAX = 4096


def _cached_header(
    filepath: str,
    *,
    force_fallback: bool = True,
    include_per_frame: bool = False,
):
    """Read/cache metadata without forcing enhanced per-frame sequences on the UI thread.

    Enhanced CBCT can contain hundreds/thousands of items in
    PerFrameFunctionalGroupsSequence. Parsing that sequence while the user merely
    chooses a patient was a hidden bottleneck. The fast cache deliberately omits
    it; a full geometry header is loaded later inside the DICOM decode worker only
    when an enhanced multi-frame study actually needs it.
    """
    path = Path(filepath)
    try:
        st = path.stat()
        resolved = str(path.resolve())
        stamp = (int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        resolved = str(path)
        stamp = (-1, -1)
    key = (resolved, bool(include_per_frame))
    with _HEADER_CACHE_LOCK:
        item = _HEADER_CACHE.get(key)
        if item is not None and item[:2] == stamp:
            return item[2], item[3]
    header, forced = read_header(
        str(path),
        force_fallback=force_fallback,
        include_per_frame=include_per_frame,
    )
    with _HEADER_CACHE_LOCK:
        if len(_HEADER_CACHE) >= _HEADER_CACHE_MAX:
            for old_key in tuple(_HEADER_CACHE.keys())[: max(1, _HEADER_CACHE_MAX // 8)]:
                _HEADER_CACHE.pop(old_key, None)
        _HEADER_CACHE[key] = (stamp[0], stamp[1], header, bool(forced))
    return header, forced


@dataclass
class SourceProbe:
    """Lightweight information shown before decoding the pixel volume."""

    filepath: str
    filename: str
    source_kind: str
    source_files: list[str]
    source_headers: list[Any]
    header: Any
    rows: int
    columns: int
    frames: int
    modality: str
    manufacturer: str
    model: str
    series_description: str
    patient_name: str
    patient_id: str
    spacing_zyx_mm: tuple[float, float, float]
    spacing_inferred: bool
    estimated_memory_mb: float
    selected_filepath: str = ""
    recovered_from_non_image: bool = False
    recovery_note: str = ""
    transfer_syntax_uid: str = ""
    compressed_pixel_data: bool = False

    @property
    def dimensions_text(self) -> str:
        return f"{self.columns} × {self.rows} × {self.frames}"

    @property
    def spacing_text(self) -> str:
        z, y, x = self.spacing_zyx_mm
        return f"{x:g} × {y:g} × {z:g} mm"


HEADER_TAGS_FAST = [
    "SOPClassUID",
    "SOPInstanceUID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "FrameOfReferenceUID",
    "PatientName",
    "PatientID",
    "Modality",
    "Manufacturer",
    "ManufacturerModelName",
    "SeriesDescription",
    "SeriesNumber",
    "InstanceNumber",
    "Rows",
    "Columns",
    "NumberOfFrames",
    "BitsAllocated",
    "BitsStored",
    "PixelRepresentation",
    "PhotometricInterpretation",
    "SamplesPerPixel",
    "PixelSpacing",
    "ImagerPixelSpacing",
    "SliceThickness",
    "SpacingBetweenSlices",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "SliceLocation",
    "RescaleSlope",
    "RescaleIntercept",
    "WindowCenter",
    "WindowWidth",
    "SharedFunctionalGroupsSequence",
]
HEADER_TAGS_FULL = HEADER_TAGS_FAST + ["PerFrameFunctionalGroupsSequence"]


def _first_item(dataset: Any, sequence_name: str):
    sequence = getattr(dataset, sequence_name, None)
    if not sequence:
        return None
    try:
        return sequence[0]
    except (IndexError, TypeError):
        return None


def _sequence_item(dataset: Any, sequence_name: str, index: int):
    sequence = getattr(dataset, sequence_name, None)
    if not sequence:
        return None
    try:
        return sequence[min(max(index, 0), len(sequence) - 1)]
    except (IndexError, TypeError):
        return None


def _nested_first(dataset: Any, *sequence_names: str):
    current = dataset
    for name in sequence_names:
        current = _first_item(current, name)
        if current is None:
            return None
    return current


def read_header(
    filepath: str,
    *,
    force_fallback: bool = True,
    include_per_frame: bool = False,
):
    """Read metadata without Pixel Data; enhanced per-frame data is opt-in."""
    pydicom = load_pydicom()
    if pydicom is None:
        raise RuntimeError("pydicom no está instalado")

    InvalidDicomError = getattr(pydicom, "InvalidDicomError", Exception)

    kwargs = {
        "stop_before_pixels": True,
        "specific_tags": HEADER_TAGS_FULL if include_per_frame else HEADER_TAGS_FAST,
    }
    try:
        return pydicom.dcmread(filepath, force=False, **kwargs), False
    except InvalidDicomError:
        if not force_fallback:
            raise
        dataset = pydicom.dcmread(filepath, force=True, **kwargs)
        identifying = ("Rows", "Columns", "Modality", "SeriesInstanceUID", "SOPClassUID")
        if not any(hasattr(dataset, keyword) for keyword in identifying):
            raise InvalidDicomError("El archivo no contiene una cabecera DICOM reconocible")
        return dataset, True


def _pixel_measures(dataset: Any, frame_index: int = 0):
    shared = _nested_first(dataset, "SharedFunctionalGroupsSequence", "PixelMeasuresSequence")
    if shared is not None:
        return shared

    frame_group = _sequence_item(dataset, "PerFrameFunctionalGroupsSequence", frame_index)
    if frame_group is not None:
        measures = _first_item(frame_group, "PixelMeasuresSequence")
        if measures is not None:
            return measures
    return None


def pixel_spacing(dataset: Any, frame_index: int = 0) -> tuple[float | None, float | None]:
    value = getattr(dataset, "PixelSpacing", None)
    if value is None:
        measures = _pixel_measures(dataset, frame_index)
        value = getattr(measures, "PixelSpacing", None) if measures is not None else None
    if value is None:
        value = getattr(dataset, "ImagerPixelSpacing", None)

    try:
        row_spacing = float(value[0])
        column_spacing = float(value[1])
        if row_spacing > 0.0 and column_spacing > 0.0:
            return row_spacing, column_spacing
    except (TypeError, ValueError, IndexError):
        pass
    return None, None


def slice_spacing(dataset: Any, frame_index: int = 0) -> float | None:
    for source in (dataset, _pixel_measures(dataset, frame_index)):
        if source is None:
            continue
        for keyword in ("SpacingBetweenSlices", "SliceThickness"):
            value = safe_float(getattr(source, keyword, None))
            if value is not None and value > 0.0:
                return value
    return None


def image_orientation(dataset: Any, frame_index: int = 0):
    value = getattr(dataset, "ImageOrientationPatient", None)
    if value is None:
        shared = _nested_first(
            dataset,
            "SharedFunctionalGroupsSequence",
            "PlaneOrientationSequence",
        )
        value = getattr(shared, "ImageOrientationPatient", None) if shared is not None else None
    if value is None:
        frame_group = _sequence_item(dataset, "PerFrameFunctionalGroupsSequence", frame_index)
        plane = _first_item(frame_group, "PlaneOrientationSequence") if frame_group is not None else None
        value = getattr(plane, "ImageOrientationPatient", None) if plane is not None else None

    try:
        values = tuple(float(component) for component in value)
        if len(values) >= 6:
            return values[:6]
    except (TypeError, ValueError):
        pass
    return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def image_position(dataset: Any, frame_index: int = 0) -> tuple[float, float, float] | None:
    value = getattr(dataset, "ImagePositionPatient", None)
    if value is None:
        frame_group = _sequence_item(dataset, "PerFrameFunctionalGroupsSequence", frame_index)
        plane = _first_item(frame_group, "PlanePositionSequence") if frame_group is not None else None
        value = getattr(plane, "ImagePositionPatient", None) if plane is not None else None
    if value is None:
        return None
    return as_tuple3(value, default=(0.0, 0.0, 0.0))


def rescale_values(dataset: Any, frame_index: int = 0) -> tuple[float, float]:
    slope = safe_float(getattr(dataset, "RescaleSlope", None), 1.0)
    intercept = safe_float(getattr(dataset, "RescaleIntercept", None), 0.0)

    shared = _nested_first(
        dataset,
        "SharedFunctionalGroupsSequence",
        "PixelValueTransformationSequence",
    )
    if shared is not None:
        slope = safe_float(getattr(shared, "RescaleSlope", None), slope)
        intercept = safe_float(getattr(shared, "RescaleIntercept", None), intercept)

    frame_group = _sequence_item(dataset, "PerFrameFunctionalGroupsSequence", frame_index)
    transform = _first_item(frame_group, "PixelValueTransformationSequence") if frame_group is not None else None
    if transform is not None:
        slope = safe_float(getattr(transform, "RescaleSlope", None), slope)
        intercept = safe_float(getattr(transform, "RescaleIntercept", None), intercept)

    return float(slope if slope is not None else 1.0), float(intercept if intercept is not None else 0.0)


def _orientation_matrix(dataset: Any):
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    values = image_orientation(dataset)
    axis_x = np.asarray(values[:3], dtype=np.float64)
    axis_y = np.asarray(values[3:6], dtype=np.float64)

    def normalized(vector, fallback):
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm > 1e-9 else np.asarray(fallback, dtype=np.float64)

    axis_x = normalized(axis_x, (1.0, 0.0, 0.0))
    axis_y = axis_y - axis_x * float(np.dot(axis_y, axis_x))
    axis_y = normalized(axis_y, (0.0, 1.0, 0.0))
    axis_z = normalized(np.cross(axis_x, axis_y), (0.0, 0.0, 1.0))
    return np.column_stack((axis_x, axis_y, axis_z))


def _position_projection(dataset: Any, normal, frame_index: int = 0) -> float | None:
    np = load_numpy()
    position = image_position(dataset, frame_index)
    if position is None or np is None:
        return None
    return float(np.dot(np.asarray(position, dtype=np.float64), normal))


def _discover_series(selected_path: str, selected_header: Any) -> list[tuple[str, Any]]:
    """Find sibling files belonging to the same classic DICOM series."""
    series_uid = str(getattr(selected_header, "SeriesInstanceUID", "") or "")
    if not series_uid:
        return [(selected_path, selected_header)]

    selected = Path(selected_path)
    candidates: list[tuple[str, Any]] = []
    selected_norm = os.path.normcase(os.path.abspath(str(selected)))
    for path in selected.parent.iterdir():
        if not path.is_file():
            continue
        try:
            path_norm = os.path.normcase(os.path.abspath(str(path)))
            if path_norm == selected_norm:
                header = selected_header
            else:
                header, _forced = _cached_header(str(path), force_fallback=True)
        except Exception:
            continue
        if str(getattr(header, "SeriesInstanceUID", "") or "") != series_uid:
            continue
        if safe_int(getattr(header, "Rows", 0), 0) <= 0 or safe_int(getattr(header, "Columns", 0), 0) <= 0:
            continue
        candidates.append((str(path), header))

    if not candidates:
        return [(selected_path, selected_header)]

    orientation = _orientation_matrix(selected_header)
    normal = orientation[:, 2]

    def sort_key(item: tuple[str, Any]):
        path, dataset = item
        projection = _position_projection(dataset, normal)
        if projection is not None:
            return (0, projection, path)
        location = safe_float(getattr(dataset, "SliceLocation", None))
        if location is not None:
            return (1, location, path)
        return (2, safe_int(getattr(dataset, "InstanceNumber", 0), 0), path)

    candidates.sort(key=sort_key)
    return candidates


def _infer_multiframe_z_spacing(dataset: Any, frame_count: int, normal) -> float | None:
    np = load_numpy()
    if np is None or frame_count < 2:
        return None

    # Sample all positions for ordinary dental CBCT sizes. This remains cheap
    # compared with pixel decoding and captures enhanced multi-frame geometry.
    projections: list[float] = []
    for index in range(frame_count):
        position = image_position(dataset, index)
        if position is None:
            continue
        projections.append(float(np.dot(np.asarray(position, dtype=np.float64), normal)))

    if len(projections) < 2:
        return None
    differences = np.abs(np.diff(np.asarray(projections, dtype=np.float64)))
    differences = differences[differences > 1e-6]
    if differences.size == 0:
        return None
    return float(np.median(differences))


def _infer_classic_z_spacing(items: list[tuple[str, Any]], normal) -> float | None:
    np = load_numpy()
    if np is None or len(items) < 2:
        return None
    projections = [
        _position_projection(dataset, normal)
        for _path, dataset in items
    ]
    projections = [value for value in projections if value is not None]
    if len(projections) < 2:
        return None
    differences = np.abs(np.diff(np.asarray(projections, dtype=np.float64)))
    differences = differences[differences > 1e-6]
    return float(np.median(differences)) if differences.size else None


def _estimate_memory_mb(rows: int, columns: int, frames: int, bits_allocated: int) -> float:
    bytes_per_voxel = max(1, int(math.ceil(max(bits_allocated, 8) / 8.0)))
    return rows * columns * frames * bytes_per_voxel / (1024.0 * 1024.0)


def _valid_image_dimensions(dataset: Any) -> tuple[int, int] | None:
    rows = safe_int(getattr(dataset, "Rows", 0), 0)
    columns = safe_int(getattr(dataset, "Columns", 0), 0)
    if rows > 0 and columns > 0:
        return rows, columns
    return None


def _sort_recovered_series_items(items: list[tuple[str, Any]], reference_header: Any) -> list[tuple[str, Any]]:
    """Sort recovered classic-series slices across arbitrary subdirectories."""
    if not items:
        return []
    orientation = _orientation_matrix(reference_header)
    normal = orientation[:, 2]

    def sort_key(item: tuple[str, Any]):
        path, dataset = item
        projection = _position_projection(dataset, normal)
        if projection is not None:
            return (0, projection, path)
        location = safe_float(getattr(dataset, "SliceLocation", None))
        if location is not None:
            return (1, location, path)
        return (2, safe_int(getattr(dataset, "InstanceNumber", 0), 0), path)

    return sorted(items, key=sort_key)


def _bounded_recursive_files(root: Path, *, max_depth: int, remaining: int) -> list[Path]:
    """Return files below *root* without trusting filename extensions.

    Dental CBCT exports frequently use extension-less files or opaque numeric
    names. Discovery therefore probes file contents with pydicom instead of
    filtering on ``.dcm``. Symlinked directories are not traversed so a vendor
    export cannot accidentally make recovery wander outside the study tree.
    """
    if remaining <= 0 or not root.exists() or not root.is_dir():
        return []

    found: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(found) < remaining:
        directory, depth = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if len(found) >= remaining:
                break
            try:
                if entry.is_file():
                    found.append(entry)
                elif depth < max_depth and entry.is_dir() and not entry.is_symlink():
                    stack.append((entry, depth + 1))
            except OSError:
                continue
    return found


def _recovery_search_roots(selected_path: Path) -> list[tuple[Path, int]]:
    """Choose bounded study-tree roots for recovery of a non-image DICOM.

    9.1.9 only recursed when the filename was literally ``DICOMDIR``. Real
    CBCT exports often place SR/PR/metadata objects in one child directory and
    the image series in a sibling directory, sometimes without a DICOMDIR
    filename. We therefore always recurse from the selected file's directory
    and, when safe, from up to two parent study directories.
    """
    roots: list[tuple[Path, int]] = []
    current = selected_path.parent
    if current.exists():
        roots.append((current, 6))

    # Parent/grandparent scans are deliberately shallower and never include a
    # filesystem/drive root. This catches sibling image folders without making
    # a bad click scan an entire disk.
    for depth in (4, 3):
        parent = current.parent
        if parent == current or parent.parent == parent:
            break
        roots.append((parent, depth))
        current = parent

    deduped: list[tuple[Path, int]] = []
    seen: set[str] = set()
    for root, depth in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((root, depth))
    return deduped


def _dicomdir_referenced_paths(selected_path: Path, selected_header: Any) -> list[Path]:
    """Resolve ReferencedFileID entries when the selected object is DICOMDIR.

    ``read_header`` intentionally loads a small tag subset, so Directory Record
    Sequence is fetched only on this recovery path. Failure is harmless because
    bounded content-based tree discovery remains available afterwards.
    """
    sop_class = str(getattr(selected_header, "SOPClassUID", "") or "")
    is_dicomdir = selected_path.name.upper() == "DICOMDIR" or sop_class == "1.2.840.10008.1.3.10"
    if not is_dicomdir:
        return []

    pydicom = load_pydicom()
    if pydicom is None:
        return []
    try:
        dataset = pydicom.dcmread(str(selected_path), force=True, stop_before_pixels=True)
    except Exception:
        return []

    results: list[Path] = []
    sequence = getattr(dataset, "DirectoryRecordSequence", None) or []
    for record in sequence:
        value = getattr(record, "ReferencedFileID", None)
        if not value:
            continue
        try:
            if isinstance(value, str):
                components = [part for part in value.replace("\\", "/").split("/") if part]
            else:
                components = [str(part) for part in value if str(part)]
            if not components:
                continue
            candidate = selected_path.parent.joinpath(*components)
            if candidate.is_file():
                results.append(candidate)
        except Exception:
            continue
    return results


def _candidate_series_near_selection(
    selected_path: Path,
    selected_header: Any | None = None,
    *,
    max_files: int = 20000,
):
    """Discover image-bearing DICOM series around a non-image selection.

    The search is extension-agnostic, recursively inspects the study tree, and
    groups a series by Study/Series UID rather than by physical directory. A
    diagnostic report is returned so failures tell us whether no DICOM files
    were present or whether DICOM objects were present but none carried images.
    """
    if selected_header is None:
        try:
            selected_header, _forced = read_header(str(selected_path), force_fallback=True)
        except Exception:
            selected_header = None

    selected_study_uid = str(getattr(selected_header, "StudyInstanceUID", "") or "") if selected_header is not None else ""

    ordered_paths: list[Path] = []
    seen_paths: set[str] = set()

    def add_path(path: Path) -> None:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if path == selected_path or key in seen_paths or not path.is_file():
            return
        seen_paths.add(key)
        ordered_paths.append(path)

    # DICOMDIR references are precise and therefore get first priority.
    if selected_header is not None:
        for path in _dicomdir_referenced_paths(selected_path, selected_header):
            add_path(path)
            if len(ordered_paths) >= max_files:
                break

    scanned_roots: list[str] = []
    for root, depth in _recovery_search_roots(selected_path):
        if len(ordered_paths) >= max_files:
            break
        scanned_roots.append(str(root))
        remaining = max_files - len(ordered_paths)
        for path in _bounded_recursive_files(root, max_depth=depth, remaining=remaining):
            add_path(path)
            if len(ordered_paths) >= max_files:
                break

    groups: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    readable_dicom = 0
    image_files = 0
    for item in ordered_paths:
        try:
            header, _forced = _cached_header(str(item), force_fallback=True)
        except Exception:
            continue
        readable_dicom += 1
        dims = _valid_image_dimensions(header)
        if dims is None:
            continue
        image_files += 1
        rows, columns = dims
        study_uid = str(getattr(header, "StudyInstanceUID", "") or "")
        series_uid = str(getattr(header, "SeriesInstanceUID", "") or "")
        # A real SeriesInstanceUID is authoritative across directories. For old
        # exports without UIDs, keep directory in the synthetic key to avoid
        # merging unrelated same-sized images.
        if not series_uid:
            series_uid = f"NO_UID:{item.parent}:{rows}x{columns}"
        key = (study_uid, series_uid, rows, columns)
        group = groups.setdefault(
            key,
            {
                "representative": str(item),
                "header": header,
                "items": [],
                "files": 0,
                "frames": 0,
                "rows": rows,
                "columns": columns,
                "modality": str(getattr(header, "Modality", "") or "").upper(),
                "description": str(getattr(header, "SeriesDescription", "") or ""),
                "series_uid": str(getattr(header, "SeriesInstanceUID", "") or ""),
                "study_uid": study_uid,
            },
        )
        group["items"].append((str(item), header))
        group["files"] += 1
        group["frames"] += max(1, safe_int(getattr(header, "NumberOfFrames", 1), 1))

    candidates = list(groups.values())
    modality_rank = {"CT": 5, "CBCT": 5, "DX": 2, "CR": 2}
    for candidate in candidates:
        candidate["source_items"] = _sort_recovered_series_items(candidate["items"], candidate["header"])
        if candidate["source_items"]:
            candidate["representative"], candidate["header"] = candidate["source_items"][0]
        candidate["voxel_proxy"] = int(candidate["rows"]) * int(candidate["columns"]) * int(candidate["frames"])
        candidate["modality_rank"] = modality_rank.get(candidate["modality"], 1)
        candidate["same_study"] = bool(selected_study_uid and candidate["study_uid"] == selected_study_uid)

    candidates.sort(
        key=lambda c: (
            int(c["same_study"]),
            c["modality_rank"],
            c["frames"],
            c["voxel_proxy"],
        ),
        reverse=True,
    )
    diagnostics = {
        "scanned_files": len(ordered_paths),
        "readable_dicom": readable_dicom,
        "image_files": image_files,
        "scanned_roots": scanned_roots,
        "selected_study_uid": selected_study_uid,
    }
    return candidates, diagnostics


def _recover_image_source(selected_path: Path, selected_header: Any | None = None):
    candidates, diagnostics = _candidate_series_near_selection(selected_path, selected_header)
    if not candidates:
        roots_text = " | ".join(diagnostics["scanned_roots"][:3]) or str(selected_path.parent)
        return None, (
            "El archivo seleccionado es DICOM pero no contiene píxeles de imagen (faltan Rows/Columns). "
            f"DSG examinó {diagnostics['scanned_files']} archivos en el árbol del estudio, reconoció "
            f"{diagnostics['readable_dicom']} objetos DICOM y encontró {diagnostics['image_files']} con imagen. "
            f"Raíces examinadas: {roots_text}. Si el CBCT está en otra carpeta, selecciona cualquier corte "
            "real de esa serie o coloca/selecciona el DICOMDIR de la raíz completa del estudio."
        )

    if len(candidates) == 1:
        candidate = candidates[0]
        return candidate, (
            f"Serie de imagen detectada automáticamente: {candidate['modality'] or 'DICOM'} "
            f"{candidate['columns']}×{candidate['rows']}×{candidate['frames']} "
            f"en {candidate['files']} archivo(s)."
        )

    best, second = candidates[0], candidates[1]
    # Auto-recover only when the best CT/CBCT series is strongly supported by
    # study identity and/or substantially more volumetric data. Otherwise fail
    # closed and let the clinician choose a real slice from the intended series.
    best_frames = int(best["frames"])
    second_frames = max(1, int(second["frames"]))
    dominant = (
        best["modality"] in {"CT", "CBCT"}
        and best_frames >= 8
        and (
            (best["same_study"] and not second["same_study"])
            or best_frames >= 3 * second_frames
        )
    )
    if dominant:
        return best, (
            f"Serie {best['modality'] or 'DICOM'} dominante detectada automáticamente "
            f"({best['columns']}×{best['rows']}×{best['frames']}, {best['files']} archivo(s))."
        )

    summaries = []
    for candidate in candidates[:6]:
        label = candidate["description"] or candidate["series_uid"] or "sin descripción"
        same = " · mismo estudio" if candidate["same_study"] else ""
        summaries.append(
            f"{candidate['modality'] or '—'} {candidate['columns']}×{candidate['rows']}×"
            f"{candidate['frames']} ({candidate['files']} archivos) · {label}{same}"
        )
    return None, (
        f"El archivo seleccionado no contiene imagen y se encontraron {len(candidates)} series de imagen. "
        "DSG no elegirá una reconstrucción médica de forma ambigua. Selecciona un corte de la serie CBCT "
        "que quieras usar. Candidatas: " + " | ".join(summaries)
    )


def probe_source(filepath: str) -> SourceProbe:
    """Inspect a selected DICOM file and determine whether it is multi-frame."""
    selected_path = Path(filepath)
    if not selected_path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {filepath}")

    path = selected_path
    header, _forced = _cached_header(str(path), force_fallback=True)
    recovered = False
    recovery_note = ""
    dims = _valid_image_dimensions(header)
    if dims is None:
        candidate, recovery_note = _recover_image_source(selected_path, header)
        if candidate is None:
            raise RuntimeError(recovery_note)
        path = Path(candidate["representative"])
        header = candidate["header"]
        recovered = True
        dims = _valid_image_dimensions(header)

    if dims is None:
        raise RuntimeError("No se pudieron determinar Rows/Columns de la serie DICOM recuperada")
    rows, columns = dims

    declared_frames = max(1, safe_int(getattr(header, "NumberOfFrames", 1), 1))
    if declared_frames > 1:
        source_kind = "MULTIFRAME"
        source_items = [(str(path), header)]
        frame_count = declared_frames
    else:
        if recovered and candidate is not None and candidate.get("source_items"):
            # Recovery from DICOMDIR/non-image metadata already performed an
            # explicit series selection, so keep its discovered items.
            source_items = list(candidate["source_items"])
            frame_count = len(source_items)
            source_kind = "SERIES" if frame_count > 1 else "SINGLE"
        else:
            # Do NOT scan/parse every sibling slice on Blender's UI thread.
            # Resolve the complete classic series inside the decode worker.
            source_items = [(str(path), header)]
            frame_count = 1
            source_kind = "SERIES_PENDING"

    orientation = _orientation_matrix(header)
    normal = orientation[:, 2]
    row_spacing, column_spacing = pixel_spacing(header)
    inferred = False
    if row_spacing is None:
        row_spacing = 1.0
        inferred = True
    if column_spacing is None:
        column_spacing = 1.0
        inferred = True

    if source_kind == "MULTIFRAME":
        # Fast probe deliberately omits PerFrameFunctionalGroupsSequence. Use
        # shared/top-level spacing now; if missing, the decode worker refines
        # geometry from the full enhanced header without blocking Blender UI.
        z_spacing = slice_spacing(header)
    elif source_kind == "SERIES":
        z_spacing = _infer_classic_z_spacing(source_items, normal)
    else:
        z_spacing = None

    if z_spacing is None:
        z_spacing = slice_spacing(header)
    if z_spacing is None or z_spacing <= 0.0:
        z_spacing = 1.0
        inferred = True

    bits = safe_int(getattr(header, "BitsAllocated", 16), 16)
    memory_mb = _estimate_memory_mb(rows, columns, frame_count, bits)

    return SourceProbe(
        filepath=str(path),
        filename=path.name,
        source_kind=source_kind,
        source_files=[item[0] for item in source_items],
        source_headers=[item[1] for item in source_items],
        header=header,
        rows=rows,
        columns=columns,
        frames=frame_count,
        modality=str(getattr(header, "Modality", "") or "—"),
        manufacturer=str(getattr(header, "Manufacturer", "") or "—"),
        model=str(getattr(header, "ManufacturerModelName", "") or "—"),
        series_description=str(getattr(header, "SeriesDescription", "") or "—"),
        patient_name=str(getattr(header, "PatientName", "") or "—"),
        patient_id=str(getattr(header, "PatientID", "") or "—"),
        spacing_zyx_mm=(float(z_spacing), float(row_spacing), float(column_spacing)),
        spacing_inferred=inferred,
        estimated_memory_mb=memory_mb,
        selected_filepath=str(selected_path),
        recovered_from_non_image=recovered,
        recovery_note=recovery_note,
        transfer_syntax_uid=_dataset_transfer_syntax_uid(header),
        compressed_pixel_data=_transfer_syntax_requires_decoder(
            _dataset_transfer_syntax_uid(header)
        ),
    )


def _decode_pixel_array(path: str, dataset: Any | None = None):
    """Decode one DICOM image without reparsing/storing a full Dataset when possible.

    pydicom 3's ``pixels.pixel_array(path)`` reads the minimal image metadata and
    pixel stream directly from disk.  For DSG's bundled minidicom, the cached
    stop-before-pixels header already contains the byte offset, so it can read
    PixelData without parsing the header a second time.
    """
    pydicom = load_pydicom()
    if pydicom is None:
        raise RuntimeError("pydicom no está instalado")

    try:
        if full_pydicom_available():
            from pydicom.pixels import pixel_array as pd_pixel_array
            return pd_pixel_array(path)
        bundled_pixel_array = getattr(pydicom, "pixel_array", None)
        if callable(bundled_pixel_array):
            return bundled_pixel_array(path, dataset=dataset)
        if dataset is None:
            dataset = pydicom.dcmread(path, force=True)
        return dataset.pixel_array
    except Exception as first_error:
        try:
            # Last-resort compatibility path for unusual full-pydicom builds.
            dataset = pydicom.dcmread(path, force=True)
            return dataset.pixel_array
        except Exception as second_error:
            uid = _dataset_transfer_syntax_uid(dataset) if dataset is not None else ""
            ready, detail = dicom_transfer_syntax_support(uid)
            raise RuntimeError(
                "No se pudieron decodificar los píxeles DICOM. "
                f"TransferSyntax={uid or 'desconocida'} · {detail}. "
                "DSG verifica el motor antes de abrir el volumen; prepara/repara el runtime DICOM offline. "
                f"Detalle: {second_error}"
            ) from first_error


def _grayscale_frame(array):
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")
    array = np.asarray(array)
    if array.ndim == 3 and array.shape[-1] in (3, 4):
        rgb = array[..., :3].astype(np.float32, copy=False)
        return (
            rgb[..., 0] * 0.2126
            + rgb[..., 1] * 0.7152
            + rgb[..., 2] * 0.0722
        )
    array = np.squeeze(array)
    if array.ndim != 2:
        raise RuntimeError(f"Frame DICOM no compatible: shape={array.shape}")
    return array


def _load_multiframe(probe: SourceProbe, callback: ProgressCallback | None):
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    # Enhanced multi-frame geometry may live in a very large
    # PerFrameFunctionalGroupsSequence. Parse it here in the background worker,
    # never while the user is choosing/opening the CBCT from Blender's UI thread.
    geometry_header = probe.header
    if int(getattr(probe, "frames", 1) or 1) > 1 and not hasattr(geometry_header, "PerFrameFunctionalGroupsSequence"):
        if callback:
            callback(0, 4, "Leyendo geometría DICOM mejorada")
        try:
            geometry_header, _forced = _cached_header(
                probe.filepath,
                force_fallback=True,
                include_per_frame=True,
            )
        except Exception:
            geometry_header = probe.header

    if callback:
        callback(1, 4, "Decodificando volumen multi-frame")
    array = np.asarray(_decode_pixel_array(probe.filepath, dataset=geometry_header))

    if array.ndim == 2:
        array = array[np.newaxis, :, :]
    elif array.ndim == 4 and array.shape[-1] in (3, 4):
        rgb = array[..., :3].astype(np.float32, copy=False)
        array = (
            rgb[..., 0] * 0.2126
            + rgb[..., 1] * 0.7152
            + rgb[..., 2] * 0.0722
        )
    else:
        array = np.squeeze(array)

    if array.ndim != 3:
        raise RuntimeError(f"Volumen DICOM no compatible: shape={array.shape}")
    if callback:
        callback(2, 4, "Leyendo transformaciones de densidad")

    frame_count = int(array.shape[0])
    slopes = np.empty(frame_count, dtype=np.float32)
    intercepts = np.empty(frame_count, dtype=np.float32)
    for index in range(frame_count):
        slopes[index], intercepts[index] = rescale_values(geometry_header, index)

    if callback:
        callback(4, 4, "Volumen decodificado")
    return array, slopes, intercepts, [geometry_header]


def _resolve_classic_series_in_worker(
    probe: SourceProbe,
    callback: ProgressCallback | None = None,
) -> None:
    """Resolve all slices/geometry for a classic DICOM series off the UI thread."""
    if probe.source_kind != "SERIES_PENDING":
        return
    if callback:
        callback(0, 4, "Localizando cortes de la serie DICOM")
    items = _discover_series(probe.filepath, probe.header)
    probe.source_files = [item[0] for item in items]
    probe.source_headers = [item[1] for item in items]
    probe.frames = max(1, len(items))
    probe.source_kind = "SERIES" if probe.frames > 1 else "SINGLE"

    try:
        orientation = _orientation_matrix(probe.header)
        normal = orientation[:, 2]
        z_spacing = _infer_classic_z_spacing(items, normal) if len(items) > 1 else None
        if z_spacing is None:
            z_spacing = slice_spacing(probe.header)
        if z_spacing is None or z_spacing <= 0.0:
            z_spacing = float(probe.spacing_zyx_mm[0] or 1.0)
        probe.spacing_zyx_mm = (
            float(z_spacing),
            float(probe.spacing_zyx_mm[1]),
            float(probe.spacing_zyx_mm[2]),
        )
        bits = safe_int(getattr(probe.header, "BitsAllocated", 16), 16)
        probe.estimated_memory_mb = _estimate_memory_mb(
            int(probe.rows), int(probe.columns), int(probe.frames), bits
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _load_classic_series(probe: SourceProbe, callback: ProgressCallback | None):
    pydicom = load_pydicom()
    np = load_numpy()
    if pydicom is None or np is None:
        raise RuntimeError("Faltan pydicom o NumPy")

    # v9.2.17 reuses the metadata headers obtained during series discovery.
    # Older builds reopened and parsed every DCM twice and retained full
    # PixelData-bearing Dataset objects, which was a major CBCT-open bottleneck.
    headers = list(getattr(probe, "source_headers", []) or [])
    if len(headers) != len(probe.source_files):
        headers = []
        for path in probe.source_files:
            header, _forced = _cached_header(path, force_fallback=True)
            headers.append(header)

    volume = None
    slopes = np.empty(probe.frames, dtype=np.float32)
    intercepts = np.empty(probe.frames, dtype=np.float32)

    for index, path in enumerate(probe.source_files):
        header = headers[index]
        frame = _grayscale_frame(_decode_pixel_array(path, dataset=header))
        if volume is None:
            volume = np.empty((probe.frames, frame.shape[0], frame.shape[1]), dtype=frame.dtype)
        if frame.shape != volume.shape[1:]:
            raise RuntimeError("La serie contiene cortes con dimensiones diferentes")
        volume[index] = frame
        slopes[index], intercepts[index] = rescale_values(header, 0)
        if callback:
            callback(index + 1, probe.frames, f"Decodificando corte {index + 1}/{probe.frames}")

    if volume is None:
        raise RuntimeError("No se encontraron píxeles en la serie DICOM")
    return volume, slopes, intercepts, headers


def _sample_density_statistics(volume, slopes, intercepts) -> tuple[float, float, float, float]:
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    z_count, y_count, x_count = volume.shape
    z_step = max(1, z_count // 48)
    y_step = max(1, y_count // 64)
    x_step = max(1, x_count // 64)

    z_indices = np.arange(0, z_count, z_step, dtype=np.int64)
    sample = volume[z_indices, ::y_step, ::x_step].astype(np.float32, copy=False)
    sample = sample * slopes[z_indices, None, None] + intercepts[z_indices, None, None]
    finite = sample[np.isfinite(sample)]
    if finite.size == 0:
        return 0.0, 1.0, 0.0, 1.0

    data_min = float(finite.min())
    data_max = float(finite.max())
    auto_low = float(np.percentile(finite, 1.0))
    auto_high = float(np.percentile(finite, 99.0))
    if not math.isfinite(auto_low) or not math.isfinite(auto_high) or auto_high <= auto_low:
        auto_low, auto_high = data_min, data_max
    if data_max <= data_min:
        data_max = data_min + 1.0
        auto_high = data_max
    return data_min, data_max, auto_low, auto_high



def _prepare_external_pipeline_cache(probe, volume, slopes, intercepts):
    """Write one mmap-friendly copy while DICOM is already decoding off UI."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no disponible para cache externo")
    root = Path(tempfile.gettempdir()) / "DSG_PIPELINE_INPUT"
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        (str(probe.filepath) + "|" + str(getattr(volume, "shape", "")) + "|" + str(time.time_ns())).encode("utf-8", errors="ignore")
    ).hexdigest()[:18]
    folder = root / digest
    folder.mkdir(parents=True, exist_ok=True)
    volume_path = folder / "volume.npy"; slopes_path = folder / "slopes.npy"; intercepts_path = folder / "intercepts.npy"
    np.save(str(volume_path), np.asarray(volume), allow_pickle=False)
    np.save(str(slopes_path), np.asarray(slopes), allow_pickle=False)
    np.save(str(intercepts_path), np.asarray(intercepts), allow_pickle=False)
    return {
        "pipeline_cache_dir": str(folder),
        "pipeline_volume_path": str(volume_path),
        "pipeline_slopes_path": str(slopes_path),
        "pipeline_intercepts_path": str(intercepts_path),
    }

def _decode_volume_payload(probe: SourceProbe, callback: ProgressCallback | None = None) -> dict[str, Any]:
    """Pure file/NumPy stage. Safe to run outside Blender's UI thread."""
    np = load_numpy()
    if np is None:
        raise RuntimeError("NumPy no está disponible")

    if probe.source_kind == "MULTIFRAME":
        volume, slopes, intercepts, datasets = _load_multiframe(probe, callback)
    else:
        _resolve_classic_series_in_worker(probe, callback)
        volume, slopes, intercepts, datasets = _load_classic_series(probe, callback)

    if volume.ndim != 3:
        raise RuntimeError(f"Se esperaba volumen [z,y,x], recibido {volume.shape}")

    z_count, y_count, x_count = (int(value) for value in volume.shape)
    if slopes.shape[0] != z_count:
        slopes = np.full(z_count, float(slopes[0] if slopes.size else 1.0), dtype=np.float32)
    if intercepts.shape[0] != z_count:
        intercepts = np.full(z_count, float(intercepts[0] if intercepts.size else 0.0), dtype=np.float32)

    geometry_header = datasets[0] if datasets else probe.header
    orientation = _orientation_matrix(geometry_header)
    origin = image_position(geometry_header, 0) or image_position(probe.header, 0) or (0.0, 0.0, 0.0)

    spacing_zyx = tuple(float(v) for v in probe.spacing_zyx_mm)
    if probe.source_kind == "MULTIFRAME":
        normal = orientation[:, 2]
        row_spacing, column_spacing = pixel_spacing(geometry_header)
        z_spacing = _infer_multiframe_z_spacing(geometry_header, z_count, normal)
        if z_spacing is None:
            z_spacing = slice_spacing(geometry_header)
        spacing_zyx = (
            float(z_spacing if z_spacing and z_spacing > 0 else spacing_zyx[0]),
            float(row_spacing if row_spacing and row_spacing > 0 else spacing_zyx[1]),
            float(column_spacing if column_spacing and column_spacing > 0 else spacing_zyx[2]),
        )

    data_min, data_max, auto_low, auto_high = _sample_density_statistics(volume, slopes, intercepts)
    if callback:
        callback(99, 100, "Preparando memoria compartida del pipeline…")
    pipeline_cache = _prepare_external_pipeline_cache(probe, volume, slopes, intercepts)
    return {
        "volume": volume, "slopes": slopes, "intercepts": intercepts,
        **pipeline_cache,
        "datasets": datasets, "header": geometry_header,
        "dims_zyx": (z_count, y_count, x_count),
        "spacing_zyx_mm": spacing_zyx,
        "orientation": orientation, "origin": tuple(float(v) for v in origin),
        "data_min": data_min, "data_max": data_max,
        "auto_low": auto_low, "auto_high": auto_high,
    }


def _commit_volume_payload(probe: SourceProbe, payload: dict[str, Any]) -> None:
    """Main-thread stage: publish a decoded payload to DSG's shared runtime."""
    try:
        from . import cbct_dental_module
        cbct_dental_module.clear_dentition(keep_alignment_reference=False)
        cbct_dental_module.reset_scene_state()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    RUNTIME.reset()
    RUNTIME.source_path = probe.filepath
    RUNTIME.source_kind = probe.source_kind
    RUNTIME.source_files = list(probe.source_files)
    RUNTIME.header = payload.get("header", probe.header)
    RUNTIME.datasets = payload["datasets"]
    RUNTIME.volume = payload["volume"]
    RUNTIME.dims_zyx = tuple(payload["dims_zyx"])
    RUNTIME.spacing_zyx_mm = tuple(payload.get("spacing_zyx_mm", probe.spacing_zyx_mm))
    RUNTIME.orientation_xyz = payload["orientation"]
    RUNTIME.image_origin_patient = tuple(payload["origin"])
    RUNTIME.slopes = payload["slopes"]
    RUNTIME.intercepts = payload["intercepts"]
    RUNTIME.density_min = float(payload["data_min"])
    RUNTIME.density_max = float(payload["data_max"])
    RUNTIME.auto_low = float(payload["auto_low"])
    RUNTIME.auto_high = float(payload["auto_high"])
    RUNTIME.estimated_memory_mb = RUNTIME.volume.nbytes / (1024.0 * 1024.0)
    RUNTIME.pipeline_cache_dir = str(payload.get("pipeline_cache_dir", "") or "")
    RUNTIME.pipeline_volume_path = str(payload.get("pipeline_volume_path", "") or "")
    RUNTIME.pipeline_slopes_path = str(payload.get("pipeline_slopes_path", "") or "")
    RUNTIME.pipeline_intercepts_path = str(payload.get("pipeline_intercepts_path", "") or "")
    # DSG 9.3: no threshold warmup at patient open. SIMPLE creates its threshold
    # accelerator only after that route is explicitly chosen.


def load_volume(probe: SourceProbe, callback: ProgressCallback | None = None) -> None:
    """Synchronous compatibility wrapper. Clinical UI uses the async modal path."""
    payload = _decode_volume_payload(probe, callback)
    _commit_volume_payload(probe, payload)


def write_header_text(probe: SourceProbe) -> None:
    """Write a bounded metadata summary without serializing huge frame sequences."""
    import bpy

    block = bpy.data.texts.get("DICOM_HEADER") or bpy.data.texts.new("DICOM_HEADER")
    block.clear()
    lines = [
        "DICOM WIZARD PRO - HEADER SUMMARY",
        "=" * 72,
        f"Selected file: {probe.filepath}",
        f"Source kind: {probe.source_kind}",
        f"Files/frames: {probe.frames}",
        f"Transfer Syntax: {probe.transfer_syntax_uid or '—'}",
        f"Estimated raw memory: {probe.estimated_memory_mb:.1f} MB",
        "",
    ]
    # Never call str(dataset) here. Enhanced multi-frame CBCT datasets can
    # contain thousands of PerFrameFunctionalGroupsSequence items; converting
    # the whole object to text used to freeze Blender before pixels were read.
    bounded_tags = (
        "SOPClassUID", "StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID",
        "PatientName", "PatientID", "Modality", "Manufacturer", "ManufacturerModelName",
        "SeriesDescription", "Rows", "Columns", "NumberOfFrames", "BitsAllocated",
        "BitsStored", "PixelRepresentation", "PhotometricInterpretation", "SamplesPerPixel",
        "PixelSpacing", "SliceThickness", "SpacingBetweenSlices", "ImagePositionPatient",
        "ImageOrientationPatient", "RescaleSlope", "RescaleIntercept", "WindowCenter", "WindowWidth",
    )
    for name in bounded_tags:
        value = getattr(probe.header, name, None)
        if value is not None:
            text = str(value)
            if len(text) > 300:
                text = text[:297] + "..."
            lines.append(f"{name}: {text}")
    for seq_name in ("SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence"):
        seq = getattr(probe.header, seq_name, None)
        if seq is not None:
            try:
                lines.append(f"{seq_name}: {len(seq)} item(s) [not expanded]")
            except Exception:
                lines.append(f"{seq_name}: present [not expanded]")
    block.write("\n".join(lines))

# =============================================================================
# MODULE: volume_preview.py
# =============================================================================

