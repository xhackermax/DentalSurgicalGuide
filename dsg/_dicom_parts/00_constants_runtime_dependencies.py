"""DICOM Wizard Pro 5.x v1.13.0 - in-process CBCT AI, UniversalLab tooth instances/FDI and optimized surfaces.

Generated from the modular DICOM Wizard Pro package so it can be installed
directly as one .py file in Blender 5.1.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
import re
import sys
import tempfile
import threading
import subprocess
import pickle
import shutil
from . import lifecycle
from . import core
from . import icon_manager
from . import ui_style
from . import tooth_analysis

# =============================================================================
# MODULE: constants.py
# =============================================================================

ADDON_NAME = "Dental DICOM · Bilingual Workflow"
ADDON_VERSION = (1, 13, 0)
ADDON_VERSION_STR = ".".join(str(part) for part in ADDON_VERSION)
BLENDER_MIN_VERSION = (5, 0, 0)
TAB_NAME = "DSG"

# Shared workflow protocol has one source of truth in core.py. Local aliases
# preserve the long-standing module API without duplicating values.
SUITE_PROTOCOL_VERSION = core.SUITE_PROTOCOL_VERSION
SUITE_LANGUAGE_KEY = core.SUITE_LANGUAGE_KEY
SUITE_STAGE_KEY = core.SUITE_STAGE_KEY
SUITE_ROLE_KEY = core.SUITE_ROLE_KEY
LEGACY_ROLE_KEY = core.LEGACY_ROLE_KEY
ROLE_DICOM_TEETH = core.ROLE_DICOM_TEETH
ROLE_DICOM_BONE = core.ROLE_DICOM_BONE
ROLE_DICOM_MANDIBULAR_CANAL = core.ROLE_DICOM_MANDIBULAR_CANAL
ROLE_DICOM_ALIGNMENT_COMPOSITE = core.ROLE_DICOM_ALIGNMENT_COMPOSITE
ROLE_IOS_SCAN = core.ROLE_IOS_SCAN
ROLE_IOS_ALIGNED = core.ROLE_IOS_ALIGNED
ROLE_DSG_MODEL = core.ROLE_DSG_MODEL
ROLE_DSG_GUIDE = core.ROLE_DSG_GUIDE
NAME_DICOM_TEETH = "Dental_DICOM_Teeth"
NAME_DICOM_BONE = "Dental_DICOM_Bone"
NAME_DICOM_MAXILLA = "Dental_DICOM_Maxilla"
NAME_DICOM_MANDIBLE = "Dental_DICOM_Mandible"
NAME_DICOM_MANDIBULAR_CANAL = "Dental_DICOM_MandibularCanal"
NAME_DICOM_COMBINED = "Dental_DICOM_BoneTeeth"
TOOTH_ANALYSIS_COMPLETED_KEY = core.TOOTH_ANALYSIS_COMPLETED_KEY

# DICOM / medical values. CBCT intensity is not always calibrated to true HU,
# therefore the UI calls these values "densidad" rather than promising HU.
TYPICAL_AIR_VALUE = -1000.0
TYPICAL_CT_MIN = -1024.0
TYPICAL_CT_MAX = 3071.0

PYDICOM_VERSION = "3.0.2"

COLLECTION_NAME = "DICOM_WIZARD_PRO"
ROOT_NAME = "DICOM_WIZARD_ROOT"
BOUNDING_BOX_NAME = "DICOM_VOLUME_BOX"
VOLUME_OBJECT_NAME = "DICOM_VOLUME"
VOLUME_DATA_NAME = "DICOM_VOLUME_DATA"
VOLUME_MATERIAL_NAME = "DICOM_VOLUME_MATERIAL"
VOLUME_GRID_NAME = "density"
HEADER_TEXT_NAME = "DICOM_HEADER"

# Ephemeral, low-resolution solid isosurface used only to choose the threshold.
# It never replaces the final STL and is rebuilt only after the slider is idle.
SURFACE_PREVIEW_OBJECT_NAME = "DICOM_STL_PREVIEW_SURFACE"
SURFACE_PREVIEW_MESH_NAME = "DICOM_STL_PREVIEW_MESH"
SURFACE_PREVIEW_MATERIAL_NAME = "DICOM_STL_PREVIEW_MATERIAL"
SURFACE_PREVIEW_IDLE_SECONDS = 0.60
SURFACE_PREVIEW_DEFAULT_MAX_AXIS = 192

# Dedicated flat display panels used only by the 2x2 radiographic layout.
# They are placed far away from the clinical scene so every quad region can
# frame one image independently even though Blender quad view shares object
# visibility across all four sub-regions.
RADIOGRAPHIC_COLLECTION_NAME = "DICOM_RADIOGRAPHIC_DISPLAYS"
RADIOGRAPHIC_PROXY_PREFIX = "DICOM_RADIO_PROXY_"
RADIOGRAPHIC_PROXY_MESH_PREFIX = "DICOM_RADIO_PROXY_MESH_"

PLANE_SPECS = {
    "AXIAL": {
        "label": "Axial",
        "object": "DICOM_PLANE_AXIAL",
        "mesh": "DICOM_MESH_AXIAL",
        "image": "DICOM_IMAGE_AXIAL",
        "material": "DICOM_MATERIAL_AXIAL",
    },
    "CORONAL": {
        "label": "Coronal",
        "object": "DICOM_PLANE_CORONAL",
        "mesh": "DICOM_MESH_CORONAL",
        "image": "DICOM_IMAGE_CORONAL",
        "material": "DICOM_MATERIAL_CORONAL",
    },
    "SAGITTAL": {
        "label": "Sagital",
        "object": "DICOM_PLANE_SAGITTAL",
        "mesh": "DICOM_MESH_SAGITTAL",
        "image": "DICOM_IMAGE_SAGITTAL",
        "material": "DICOM_MATERIAL_SAGITTAL",
    },
}

# One normal-axis navigation control for each true MPR image editor.  These are
# deliberately mapped to the existing anatomical plane controls so no duplicate
# slice state can drift out of sync with the 3D cutting planes.
MPR_SLIDER_SPECS = {
    "AXIAL": {
        "property": "axial_move_z",
        "count_axis": 0,
        "spacing_axis": 0,
        "axis": "Z",
        "short_label": "AXIAL",
    },
    "CORONAL": {
        "property": "coronal_move_y",
        "count_axis": 1,
        "spacing_axis": 1,
        "axis": "Y",
        "short_label": "CORONAL",
    },
    "SAGITTAL": {
        "property": "sagittal_move_x",
        "count_axis": 2,
        "spacing_axis": 2,
        "axis": "X",
        "short_label": "SAGITAL",
    },
}

MPR_ROTATION_SPECS = {
    "AXIAL": {
        "horizontal_property": "axial_rotate_y",
        "vertical_property": "axial_rotate_x",
        "horizontal_axis": "Y",
        "vertical_axis": "X",
        "plane_axis": "Z",
        "label": "PLANO Z",
    },
    "SAGITTAL": {
        "horizontal_property": "sagittal_rotate_z",
        "vertical_property": "sagittal_rotate_y",
        "horizontal_axis": "Z",
        "vertical_axis": "Y",
        "plane_axis": "X",
        "label": "PLANO X",
    },
}


# Exact Blender orthographic views used by Numpad 7, 1 and 3.  The MPR
# layout calls bpy.ops.view3d.view_axis in each independent 3D editor instead
# of approximating the angles with custom quaternions or image editors.
MPR_VIEW_AXIS_TYPES = {
    "AXIAL": "TOP",       # Numpad 7 · view along global Z
    "CORONAL": "FRONT",  # Numpad 1 · view along global Y
    "SAGITTAL": "RIGHT", # Numpad 3 · view along global X
}

# Exact RegionView3D quaternions used internally by Blender for axis views
# (roll 0).  Assigning these directly avoids context/smooth-view races after
# asynchronous area splitting.  Order is Blender/mathutils W, X, Y, Z.
MPR_VIEW_QUATERNIONS = {
    "AXIAL": (1.0, 0.0, 0.0, 0.0),
    "CORONAL": (0.7071067811865476, -0.7071067811865476, 0.0, 0.0),
    "SAGITTAL": (0.5, -0.5, -0.5, -0.5),
}

# Full-resolution MPR remains available. Only the OpenVDB preview is adaptively
# decimated to keep a 501^3 dental CBCT usable in the viewport.
DEFAULT_VDB_MAX_AXIS = 256
MAX_VDB_AXIS = 384
MIN_VDB_AXIS = 96

# Avoid creating huge image planes if a future dataset is much larger than a
# normal dental CBCT. The sampling code preserves physical aspect ratio.
MAX_MPR_AXIS = 768

# Debounce property updates while the user drags sidebar sliders.
UI_REFRESH_DELAY_SECONDS = 0.08

# Object transforms are sampled continuously through depsgraph_update_post.
# A low-resolution preview is generated while the gizmo is moving, followed by
# a native-resolution reconstruction shortly after the user stops.
REALTIME_PREVIEW_MAX_AXIS = 256
REALTIME_PREVIEW_INTERVAL_SECONDS = 0.025
REALTIME_FINAL_DELAY_SECONDS = 0.18

# Review textures are immutable once assigned to a visible material. Blender
# may acquire image buffers from EEVEE/Workbench worker threads, so mutating an
# already displayed image can cause a native image_acquire_ibuf crash.
SAFE_REVIEW_IMAGE_PREFIX = "DICOM_REVIEW_SAFE_"
SAFE_REVIEW_REFRESH_DELAY_SECONDS = 0.12
SAFE_REVIEW_MAX_AXIS = 512
_SAFE_REVIEW_REFRESH_GENERATION = {
    "AXIAL": 0,
    "SAGITTAL": 0,
}
_SAFE_REVIEW_LAST_CHANGE_TIME = {
    "AXIAL": 0.0,
    "SAGITTAL": 0.0,
}
_SAFE_REVIEW_LAST_PREVIEW_TIME = {
    "AXIAL": 0.0,
    "SAGITTAL": 0.0,
}
_SAFE_REVIEW_PREVIEW_GENERATION = {
    "AXIAL": -1,
    "SAGITTAL": -1,
}
_SAFE_REVIEW_FINAL_GENERATION = {
    "AXIAL": -1,
    "SAGITTAL": -1,
}
_SAFE_REVIEW_TIMER_RUNNING = {
    "AXIAL": False,
    "SAGITTAL": False,
}

# Safe interactive preview: around 8-10 fps, then full quality after idle.
SAFE_REVIEW_PREVIEW_MAX_AXIS = 224
SAFE_REVIEW_PREVIEW_INTERVAL_SECONDS = 0.10
SAFE_REVIEW_FINAL_IDLE_SECONDS = 0.24

# Semi-automatic segmentation structures. The colors are used only for the
# viewport overlay and generated Blender materials.
SEGMENTATION_STRUCTURES = {
    "BONE": {
        "label": "Hueso + dientes",
        "object": "SEG_Hueso_Dientes",
        "material": "SEG_MAT_Hueso_Dientes",
        "color": (0.95, 0.58, 0.18),
    },
    "TEETH": {
        "label": "Dientes",
        "object": "SEG_Dientes",
        "material": "SEG_MAT_Dientes",
        "color": (0.20, 0.70, 1.00),
    },
    "BONE_ONLY": {
        "label": "Hueso",
        "object": "SEG_Hueso",
        "material": "SEG_MAT_Hueso",
        "color": (0.78, 0.68, 0.50),
    },
    "MANDIBULAR_CANAL": {
        "label": "Canal mandibular",
        "object": "SEG_Canal_Mandibular",
        "material": "SEG_MAT_Canal_Mandibular",
        "color": (1.00, 0.22, 0.08),
    },
    "SOFT_TISSUE": {
        "label": "Tejido blando",
        "object": "SEG_Tejido_Blando",
        "material": "SEG_MAT_Tejido_Blando",
        "color": (0.35, 0.85, 0.48),
    },
}
SEGMENTATION_EXCLUDE_COLOR = (1.0, 0.08, 0.12)
SEGMENTATION_SURFACE_PREFIX = "SEG_"

# Guardrails for automatic DICOM masks. These are deliberately permissive: the
# goal is to catch catastrophic threshold failures (nearly the whole FOV) rather
# than reject unusual but legitimate anatomy.
SEGMENTATION_MAX_COVERAGE = {
    "BONE": 0.82,
    "TEETH": 0.30,
    "BONE_ONLY": 0.72,
    "SOFT_TISSUE": 0.90,
}
SEGMENTATION_MIN_COVERAGE = {
    "TEETH": 0.00015,
}
SEGMENTATION_PREVIEW_MAX_AXIS = 512

# =============================================================================
# MODULE: runtime.py
# =============================================================================

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VolumeRuntime:
    """Large data that should not be stored in Blender RNA properties."""

    source_path: str = ""
    source_kind: str = ""
    source_files: list[str] = field(default_factory=list)
    header: Any = None
    datasets: list[Any] = field(default_factory=list)

    # Raw pixels are stored as [z, y, x]. Keeping them in their native dtype
    # avoids creating a second 250+ MB float copy for a 501^3 CBCT.
    volume: Any = None
    dims_zyx: tuple[int, int, int] = (0, 0, 0)
    spacing_zyx_mm: tuple[float, float, float] = (1.0, 1.0, 1.0)

    # Direction matrix columns represent local +X, +Y, +Z in DICOM patient
    # coordinates. The viewer centers the volume at Blender world origin.
    orientation_xyz: Any = None
    image_origin_patient: tuple[float, float, float] = (0.0, 0.0, 0.0)

    slopes: Any = None
    intercepts: Any = None
    density_min: float = 0.0
    density_max: float = 1.0
    auto_low: float = 0.0
    auto_high: float = 1.0
    estimated_memory_mb: float = 0.0

    # DSG 9.3 external-pipeline mmap cache. Created while DICOM is already
    # decoding off the UI path, so IMPLANTE INMEDIATO never copies hundreds of
    # megabytes before starting its worker process.
    pipeline_cache_dir: str = ""
    pipeline_volume_path: str = ""
    pipeline_slopes_path: str = ""
    pipeline_intercepts_path: str = ""
    pipeline_result_dir: str = ""

    vdb_path: str = ""
    vdb_stride: int = 1
    vdb_dims_xyz: tuple[int, int, int] = (0, 0, 0)

    # UI refresh scheduling state.
    update_lock: bool = False
    undo_in_progress: bool = False
    undo_repair_pending: bool = False
    timer_registered: bool = False
    refresh_generation: int = 0
    last_refresh_request_time: float = 0.0
    requested_plane_geometry_refresh: bool = False
    requested_plane_image_refresh: bool = False
    requested_visibility_refresh: bool = False
    requested_volume_material_refresh: bool = False

    # Hybrid STL threshold preview. The volume updates immediately in the GPU;
    # a cached low-resolution solid isosurface is rebuilt only after UI idle.
    surface_preview_timer_registered: bool = False
    surface_preview_generation: int = 0
    surface_preview_last_change_time: float = 0.0
    surface_preview_building: bool = False
    surface_preview_ready_threshold: float | None = None
    surface_preview_ready_structure: str = ""
    surface_preview_ready_quality: int = 0
    surface_preview_sample_cache: dict[int, Any] = field(default_factory=dict)

    # v9.2.64 native-threshold accelerator. This is deliberately a full-resolution
    # calibrated scalar cache, not a preview. The block hierarchy contains exact
    # min/max values and never changes the clinical voxel grid.
    native_density_fullres: Any = None
    native_density_cache_key: str = ""
    native_threshold_index: Any = None
    native_threshold_index_key: str = ""
    native_threshold_warmup_running: bool = False
    native_threshold_warmup_error: str = ""
    native_threshold_warmup_s: float = 0.0

    clinical_view_state: dict[int, dict[str, Any]] = field(default_factory=dict)

    # Real-time object-transform monitoring. Plane matrices are compared in
    # root-local space so rotating the whole DICOM volume does not trigger a
    # needless MPR reconstruction.
    transform_handler_lock: bool = False
    transform_timer_registered: bool = False
    pending_transform_orientations: set[str] = field(default_factory=set)
    final_transform_orientations: set[str] = field(default_factory=set)
    plane_matrix_cache: dict[str, tuple[float, ...]] = field(default_factory=dict)
    last_transform_event_time: float = 0.0

    # Sparse user drawings and cropped segmentation masks, one state per structure.
    segmentations: dict[str, Any] = field(default_factory=dict)

    # Semantic CBCT state: exactly one active full-size labelmap. Keeping one
    # complete array per model silently doubles/triples RAM on large CBCTs and
    # creates contradictory cache state. Model switching may re-run inference;
    # the active result is the single source of truth.
    semantic_labels: Any = None
    semantic_status_path: str = ""
    semantic_source_signature: str = ""
    semantic_model_kind: str = ""
    semantic_model_metadata: dict[str, Any] = field(default_factory=dict)
    semantic_crop_info: dict[str, Any] = field(default_factory=dict)

    def is_loaded(self) -> bool:
        return self.volume is not None and all(value > 0 for value in self.dims_zyx)

    def source_exists(self) -> bool:
        return bool(self.source_path) and Path(self.source_path).exists()

    def reset(self) -> None:
        """Release the volume and all metadata references."""
        old_pipeline_cache_dir = str(self.pipeline_cache_dir or "")
        old_pipeline_result_dir = str(self.pipeline_result_dir or "")
        self.source_path = ""
        self.source_kind = ""
        self.source_files.clear()
        self.header = None
        self.datasets.clear()
        self.volume = None
        self.dims_zyx = (0, 0, 0)
        self.spacing_zyx_mm = (1.0, 1.0, 1.0)
        self.orientation_xyz = None
        self.image_origin_patient = (0.0, 0.0, 0.0)
        self.slopes = None
        self.intercepts = None
        self.density_min = 0.0
        self.density_max = 1.0
        self.auto_low = 0.0
        self.auto_high = 1.0
        self.estimated_memory_mb = 0.0
        self.pipeline_cache_dir = ""
        self.pipeline_volume_path = ""
        self.pipeline_slopes_path = ""
        self.pipeline_intercepts_path = ""
        self.pipeline_result_dir = ""
        self.vdb_path = ""
        self.vdb_stride = 1
        self.vdb_dims_xyz = (0, 0, 0)
        self.update_lock = False
        self.undo_in_progress = False
        self.undo_repair_pending = False
        self.timer_registered = False
        self.refresh_generation += 1
        self.last_refresh_request_time = 0.0
        self.requested_plane_geometry_refresh = False
        self.requested_plane_image_refresh = False
        self.requested_visibility_refresh = False
        self.requested_volume_material_refresh = False
        self.surface_preview_timer_registered = False
        self.surface_preview_generation += 1
        self.surface_preview_last_change_time = 0.0
        self.surface_preview_building = False
        self.surface_preview_ready_threshold = None
        self.surface_preview_ready_structure = ""
        self.surface_preview_ready_quality = 0
        self.surface_preview_sample_cache.clear()
        self.native_density_fullres = None
        self.native_density_cache_key = ""
        self.native_threshold_index = None
        self.native_threshold_index_key = ""
        self.native_threshold_warmup_running = False
        self.native_threshold_warmup_error = ""
        self.native_threshold_warmup_s = 0.0
        self.clinical_view_state.clear()
        self.transform_handler_lock = False
        self.transform_timer_registered = False
        self.pending_transform_orientations.clear()
        self.final_transform_orientations.clear()
        self.plane_matrix_cache.clear()
        self.last_transform_event_time = 0.0
        self.segmentations.clear()
        self.semantic_labels = None
        self.semantic_status_path = ""
        self.semantic_source_signature = ""
        self.semantic_model_kind = ""
        self.semantic_model_metadata.clear()
        self.semantic_crop_info.clear()
        try:
            gc.collect()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        for _path in {old_pipeline_cache_dir, old_pipeline_result_dir}:
            if _path:
                try:
                    shutil.rmtree(_path, ignore_errors=True)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)


RUNTIME = VolumeRuntime()

# =============================================================================
# MODULE: dependencies.py
# =============================================================================

import importlib
import os
import sys
from pathlib import Path

import bpy


_language_get = core.language_get
_language_set = core.language_set


def _dw_spanish(props=None):
    scene = getattr(props, "id_data", None) if props is not None else getattr(bpy.context, "scene", None)
    return core.is_spanish(scene)


def _dw_t(props, english, spanish):
    scene = getattr(props, "id_data", None) if props is not None else getattr(bpy.context, "scene", None)
    return core.translate_ui(scene, english, spanish)


def _dw_status(props, text):
    if _dw_spanish(props) or not text:
        return text
    translations = (
        ("Selecciona un archivo DICOM", "Select a DICOM file"),
        ("Leyendo cabecera y buscando la serie", "Reading header and locating the series"),
        ("Comprobando DICOM", "Checking DICOM"),
        ("Cargando todos los cortes", "Loading all slices"),
        ("Creando volumen completo", "Building the full volume"),
        ("Visor listo", "Viewer ready"),
        ("Densidades analizadas", "Densities analyzed"),
        ("Creando STL alineado", "Creating aligned STL"),
        ("Convirtiendo DICOM a malla", "Converting DICOM to mesh"),
        ("STL creado", "STL created"),
        ("Revisión terminada", "Review completed"),
        ("No se pudo", "Could not"),
        ("No se encontró", "Not found"),
        ("Error", "Error"),
        ("listo para exportar", "ready to export"),
        ("abre MPR para revisar", "open MPR to review"),
    )
    result = str(text)
    for spanish, english in translations:
        result = result.replace(spanish, english)
    return result


def _dw_report(operator, levels, props, english, spanish=None):
    operator.report(levels, _dw_t(props, english, spanish if spanish is not None else english))


def _set_suite_role(obj, role, component="DICOM"):
    if obj is None:
        return
    core.set_role(obj, role)
    obj["dental_suite_component"] = component


def _suite_role(obj):
    return core.role_of(obj)


DICOM_RUNTIME_NAMESPACE = f"modules/dicom_wizard_pro_926_py{sys.version_info.major}{sys.version_info.minor}"


def _dicom_vendor_dir() -> Path:
    """Return a writable DICOM runtime directory without assuming its path is free.

    A previous/manual installation can leave a regular file at the namespace
    where Blender normally creates the directory.  ``user_resource(...,
    create=True)`` then prints a FileExistsError during add-on registration.
    Keep an existing runtime directory, but move safely to a sibling namespace
    when that collision is present.
    """
    scripts_root = Path(bpy.utils.user_resource("SCRIPTS"))
    config_root = Path(bpy.utils.user_resource("CONFIG"))
    candidates = (
        scripts_root / DICOM_RUNTIME_NAMESPACE,
        scripts_root / f"{DICOM_RUNTIME_NAMESPACE}_runtime",
        config_root / "dsg" / "runtimes" / DICOM_RUNTIME_NAMESPACE.rsplit("/", 1)[-1],
        Path(tempfile.gettempdir()) / "dsg" / DICOM_RUNTIME_NAMESPACE.rsplit("/", 1)[-1],
    )
    for target in candidates:
        try:
            target.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                return target
        except OSError:
            # A previous install can leave either a locked location or a file
            # in this slot.  Try the next isolated runtime location.
            continue
    raise RuntimeError("DSG no pudo crear un directorio de runtime DICOM utilizable.")


VENDOR_DIR = _dicom_vendor_dir()
# v9.2.7 reuses the v9.2.6 DICOM codec namespace and selects at most one runtime.  It may recover a legacy
# runtime only when its wheel metadata matches the current embedded Python ABI.
ADDON_RUNTIME_ROOT = Path(__file__).resolve().parent / "offline_runtime"
DICOM_OFFLINE_WHEELHOUSE = ADDON_RUNTIME_ROOT / f"win_py{sys.version_info.major}{sys.version_info.minor}" / "dicom_wheels"
ACTIVE_DICOM_VENDOR_DIR = VENDOR_DIR


def _dicom_wheel_tags(path: Path) -> tuple[str, ...]:
    tags = []
    try:
        for wheel_file in path.glob("*.dist-info/WHEEL"):
            text = wheel_file.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.startswith("Tag:"):
                    tags.append(line.split(":", 1)[1].strip())
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return tuple(tags)


def _dicom_runtime_abi_compatible(path: Path) -> bool:
    if not path.is_dir() or not (path / "pydicom").exists():
        return False
    tags = _dicom_wheel_tags(path)
    if os.name != "nt":
        return True
    py = f"cp{sys.version_info.major}{sys.version_info.minor}"
    binary_tags = [t.lower() for t in tags if "win_" in t.lower()]
    if not binary_tags:
        return False
    return all((py in t or "abi3" in t) for t in binary_tags)


def _legacy_dicom_candidates() -> list[Path]:
    result = []
    try:
        scripts = Path(bpy.utils.user_resource("SCRIPTS")).resolve()
        modules = scripts / "modules"
        if modules.is_dir():
            for child in modules.iterdir():
                name = child.name.lower()
                if child.is_dir() and (name.startswith("dicom_wizard_pro_") or name.startswith("dicom_reader_blender")):
                    if child.resolve() != VENDOR_DIR.resolve():
                        result.append(child.resolve())
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return result


def _activate_dicom_vendor(path: Path) -> None:
    global ACTIVE_DICOM_VENDOR_DIR
    selected = os.path.normcase(os.path.abspath(str(path)))
    for old in list(sys.path):
        try:
            norm = os.path.normcase(os.path.abspath(str(old)))
        except Exception:
            continue
        if ("dicom_wizard_pro_" in norm.lower() or "dicom_reader_blender" in norm.lower()) and norm != selected:
            try:
                sys.path.remove(old)
            except ValueError:
                pass
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
    sys.path.append(text)
    ACTIVE_DICOM_VENDOR_DIR = path
    importlib.invalidate_caches()


if _dicom_runtime_abi_compatible(VENDOR_DIR):
    _activate_dicom_vendor(VENDOR_DIR)
else:
    recovered = next((p for p in _legacy_dicom_candidates() if _dicom_runtime_abi_compatible(p)), None)
    if recovered is not None:
        _activate_dicom_vendor(recovered)
    else:
        _activate_dicom_vendor(VENDOR_DIR)



DEPENDENCY_IMPORT_ERRORS: dict[str, str] = {}


def load_module(module_name: str):
    try:
        module = importlib.import_module(module_name)
        DEPENDENCY_IMPORT_ERRORS.pop(module_name, None)
        return module
    except Exception as exc:
        # Binary wheels can fail with DLL/ABI errors rather than a plain
        # ImportError. Keep the add-on alive and expose the real diagnostic.
        DEPENDENCY_IMPORT_ERRORS[module_name] = f"{type(exc).__name__}: {exc}"
        return None


DICOM_RUNTIME_REQUIREMENTS = (
    f"pydicom=={PYDICOM_VERSION}",
    "pylibjpeg==2.1.0",
    "pylibjpeg-libjpeg==2.4.0",
    "pylibjpeg-openjpeg==2.5.0",
    "pylibjpeg-rle==2.2.0",
)

_DICOM_RUNTIME_LOCK = threading.Lock()
_DICOM_RUNTIME_STATE = {
    "running": False,
    "progress": 0.0,
    "message": "",
    "error": "",
    "restart_required": False,
}


def load_full_pydicom():
    """Return the real third-party pydicom package, never DSG's mini fallback."""
    return load_module("pydicom")


def full_pydicom_available() -> bool:
    return load_full_pydicom() is not None


def _dataset_transfer_syntax_uid(dataset) -> str:
    value = getattr(dataset, "TransferSyntaxUID", None)
    if value is None:
        meta = getattr(dataset, "file_meta", None)
        value = getattr(meta, "TransferSyntaxUID", None) if meta is not None else None
    return str(value or "").strip()


def _transfer_syntax_requires_decoder(uid: str) -> bool:
    uid = str(uid or "").strip()
    # Encapsulated JPEG/JPEG-LS/JPEG2000/MPEG syntaxes use the 1.2.840.10008.1.2.4.*
    # family. RLE Lossless is 1.2.840.10008.1.2.5.
    return uid.startswith("1.2.840.10008.1.2.4.") or uid == "1.2.840.10008.1.2.5"


def dicom_runtime_status() -> dict:
    full = load_full_pydicom()
    return {
        "full_pydicom": full is not None,
        "pydicom_version": str(getattr(full, "__version__", "") or "") if full else "",
        "pylibjpeg": load_module("pylibjpeg") is not None if full else False,
        "libjpeg": load_module("libjpeg") is not None if full else False,
        "openjpeg": load_module("openjpeg") is not None if full else False,
        "jpeg_ls": load_module("jpeg_ls") is not None if full else False,
        "gdcm": load_module("gdcm") is not None if full else False,
        "vendor_dir": str(ACTIVE_DICOM_VENDOR_DIR),
        "runtime_recovered": bool(ACTIVE_DICOM_VENDOR_DIR.resolve() != VENDOR_DIR.resolve()),
        "offline_wheelhouse_ready": bool(DICOM_OFFLINE_WHEELHOUSE.is_dir() and any(DICOM_OFFLINE_WHEELHOUSE.glob("*.whl"))),
    }


# Standard volumetric CBCT/CT transfer syntaxes that DSG explicitly validates.
_DICOM_NATIVE_LE = {
    "1.2.840.10008.1.2",      # Implicit VR Little Endian
    "1.2.840.10008.1.2.1",    # Explicit VR Little Endian
}
_DICOM_NATIVE_FULL_ONLY = {
    "1.2.840.10008.1.2.2",    # Explicit VR Big Endian
    "1.2.840.10008.1.2.1.99", # Deflated Explicit VR Little Endian
}
_DICOM_JPEG_LIBJPEG = {
    "1.2.840.10008.1.2.4.50", "1.2.840.10008.1.2.4.51",
    "1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70",
    "1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81",
}
_DICOM_JPEG2000 = {
    "1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.4.91",
    "1.2.840.10008.1.2.4.201", "1.2.840.10008.1.2.4.202",
    "1.2.840.10008.1.2.4.203",
}
_DICOM_RLE = "1.2.840.10008.1.2.5"


def dicom_transfer_syntax_support(uid: str) -> tuple[bool, str]:
    """Return exact decoder readiness for a selected DICOM Transfer Syntax.

    This is intentionally stricter than checking whether ``pydicom`` imports.
    A package existing on disk is not proof that JPEG/JPEG-LS/JPEG2000 DLLs
    actually load in the embedded Blender/Mixar Python process.
    """
    uid = str(uid or "").strip()
    status = dicom_runtime_status()
    base_reader = load_pydicom() is not None
    full = bool(status.get("full_pydicom"))
    gdcm = bool(status.get("gdcm"))
    libjpeg = bool(status.get("libjpeg"))
    openjpeg = bool(status.get("openjpeg"))
    jpeg_ls = bool(status.get("jpeg_ls"))

    if not uid:
        return bool(base_reader), "lector DICOM disponible" if base_reader else "falta lector DICOM"
    if uid in _DICOM_NATIVE_LE:
        return bool(base_reader), "DICOM sin compresión compatible" if base_reader else "falta lector DICOM"
    if uid in _DICOM_NATIVE_FULL_ONLY:
        return full, "pydicom completo disponible" if full else "requiere pydicom completo"
    if uid == _DICOM_RLE:
        return full, "RLE soportado por pydicom" if full else "RLE requiere pydicom completo"
    if uid in _DICOM_JPEG_LIBJPEG:
        ok = full and (libjpeg or gdcm or (uid.endswith((".80", ".81")) and jpeg_ls))
        return ok, (
            "JPEG/JPEG-LS decoder listo" if ok else
            "requiere pydicom + pylibjpeg-libjpeg (o GDCM/pyjpegls para JPEG-LS)"
        )
    if uid in _DICOM_JPEG2000:
        ok = full and (openjpeg or gdcm)
        return ok, "JPEG2000/HTJ2K decoder listo" if ok else "requiere pydicom + pylibjpeg-openjpeg (o GDCM)"
    if uid.startswith("1.2.840.10008.1.2.4."):
        return False, f"Transfer Syntax encapsulada no validada para volumen CBCT: {uid}"
    return full, "Transfer Syntax legible con pydicom completo" if full else f"Transfer Syntax {uid} requiere pydicom completo"


def dicom_standard_cbct_ready() -> bool:
    """True when the runtime covers the normal CT/CBCT pixel syntax families."""
    status = dicom_runtime_status()
    return bool(
        status.get("full_pydicom")
        and (status.get("libjpeg") or status.get("gdcm"))
        and (status.get("openjpeg") or status.get("gdcm"))
    )


def dicom_preflight_report() -> dict[str, Any]:
    status = dicom_runtime_status()
    coverage = {
        "native_little_endian": bool(load_pydicom() is not None),
        "big_endian_deflated": bool(status.get("full_pydicom")),
        "jpeg": bool(status.get("full_pydicom") and (status.get("libjpeg") or status.get("gdcm"))),
        "jpeg_ls": bool(status.get("full_pydicom") and (status.get("libjpeg") or status.get("jpeg_ls") or status.get("gdcm"))),
        "jpeg2000_htj2k": bool(status.get("full_pydicom") and (status.get("openjpeg") or status.get("gdcm"))),
        "rle": bool(status.get("full_pydicom")),
    }
    return {
        **status,
        "coverage": coverage,
        "standard_cbct_ready": all(coverage.values()),
        "import_errors": dict(DEPENDENCY_IMPORT_ERRORS),
    }


def dicom_install_state() -> dict:
    with _DICOM_RUNTIME_LOCK:
        return dict(_DICOM_RUNTIME_STATE)


def _set_dicom_install_state(**updates) -> None:
    with _DICOM_RUNTIME_LOCK:
        _DICOM_RUNTIME_STATE.update(updates)


def _install_dicom_runtime_worker() -> None:
    """Prepare the full DICOM reader from a compatible runtime or local wheelhouse only."""
    _set_dicom_install_state(
        running=True, progress=0.02, message="Comprobando Motor DICOM offline…",
        error="", restart_required=False,
    )
    try:
        status = dicom_runtime_status()
        if dicom_standard_cbct_ready():
            _set_dicom_install_state(running=False, progress=1.0, message="Motor DICOM disponible ✓", error="", restart_required=False)
            return

        # Retry legacy discovery now, in case an older runtime was created after
        # module import but before the repair button was pressed.
        for candidate in _legacy_dicom_candidates():
            if not _dicom_runtime_abi_compatible(candidate):
                continue
            _activate_dicom_vendor(candidate)
            status = dicom_runtime_status()
            if dicom_standard_cbct_ready():
                _set_dicom_install_state(running=False, progress=1.0, message=f"Motor DICOM recuperado · {candidate}", error="", restart_required=False)
                return

        if not (DICOM_OFFLINE_WHEELHOUSE.is_dir() and any(DICOM_OFFLINE_WHEELHOUSE.glob("*.whl"))):
            raise RuntimeError(
                f"No hay runtime DICOM compatible y el ZIP no contiene dicom_wheels para Python "
                f"{sys.version_info.major}.{sys.version_info.minor}"
            )

        try:
            from pip._internal.cli.main import main as pip_main
        except Exception:
            import ensurepip
            ensurepip.bootstrap(user=True)
            from pip._internal.cli.main import main as pip_main

        VENDOR_DIR.mkdir(parents=True, exist_ok=True)
        _set_dicom_install_state(progress=0.12, message="Instalando DICOM desde wheelhouse local…")
        args = [
            "install", "--disable-pip-version-check", "--no-index", "--only-binary=:all:", "--no-deps",
            "--find-links", str(DICOM_OFFLINE_WHEELHOUSE), "--upgrade", "--target", str(VENDOR_DIR),
            *DICOM_RUNTIME_REQUIREMENTS,
        ]
        code = int(pip_main(args) or 0)
        if code != 0:
            raise RuntimeError(f"pip offline terminó con código {code}")
        _activate_dicom_vendor(VENDOR_DIR)
        _set_dicom_install_state(running=False, progress=1.0, message="Motor DICOM offline instalado · reinicia Blender una vez", error="", restart_required=True)
    except Exception as exc:
        _set_dicom_install_state(
            running=False, progress=0.0, message="Motor DICOM offline incompleto",
            error=f"{type(exc).__name__}: {exc}", restart_required=False,
        )


def start_dicom_runtime_install() -> bool:
    """Compatibility entry point: install on Blender's main Python thread.

    Pip is deliberately never launched from a secondary Python thread in the
    hybrid build because that was a recurrent source of partial installs and
    signal/DLL errors on Windows.
    """
    state = dicom_install_state()
    if state.get("running"):
        return False
    _install_dicom_runtime_worker()
    return True


def load_numpy():
    return load_module("numpy")


def load_pydicom():
    """Return full pydicom when already bundled by Blender, else DSG's reader.

    The fallback is shipped with the add-on and requires no installation.
    """
    module = load_module("pydicom")
    if module is not None:
        return module
    try:
        from . import minidicom
        DEPENDENCY_IMPORT_ERRORS.pop("pydicom", None)
        return minidicom
    except Exception as exc:
        DEPENDENCY_IMPORT_ERRORS["pydicom"] = f"{type(exc).__name__}: {exc}"
        return None


def load_openvdb():
    """Return Blender's OpenVDB Python module when available."""
    return load_module("openvdb") or load_module("pyopenvdb")


def _load_scientific_module(module_name: str):
    """Load an optional scientific module, including DSG's private AI runtime.

    The SIMPLE route must not require the AI stack, but the IMMEDIATE route
    legitimately installs scipy/scikit-image inside ``dsg_ai_runtime_*``.
    v9.2.1 only searched Blender + the DICOM codec folder, so an already
    installed scikit-image could be invisible to dicom_module.  Retry after
    exposing the current DSG AI runtime, without installing anything here.
    """
    module = load_module(module_name)
    if module is not None:
        return module
    try:
        from . import cbct_ai_runtime
        cbct_ai_runtime._prepend_runtime_paths()
        importlib.invalidate_caches()
    except Exception:
        return None
    return load_module(module_name)


def load_scipy_ndimage():
    return _load_scientific_module("scipy.ndimage")


def load_scipy_spatial():
    return _load_scientific_module("scipy.spatial")


def load_skimage_measure():
    return _load_scientific_module("skimage.measure")


def load_skimage_filters():
    return _load_scientific_module("skimage.filters")


def load_skimage_segmentation():
    return _load_scientific_module("skimage.segmentation")


def load_vtk():
    """Optional VTK accelerator used for compact CBCT Flying Edges meshing.

    VTK is deliberately not a hard clinical dependency: if its wheel is absent
    or fails to import, tooth meshing falls back to scikit-image Lewiner.
    """
    return _load_scientific_module("vtk")


def load_simpleitk():
    """Optional ITK-backed dental segmentation engine."""
    return _load_scientific_module("SimpleITK")












def dependency_summary() -> dict[str, str | bool]:
    pydicom = load_pydicom()
    full_pydicom = load_full_pydicom()
    numpy = load_numpy()
    openvdb = load_openvdb()
    return {
        "pydicom": pydicom is not None,
        "pydicom_full": full_pydicom is not None,
        "pydicom_version": getattr(full_pydicom, "__version__", "") if full_pydicom else "DSG_MINI",
        "dicom_reader_mode": "FULL_PYDICOM" if full_pydicom is not None else "BUNDLED_MINIDICOM",
        "numpy": numpy is not None,
        "numpy_version": getattr(numpy, "__version__", "") if numpy else "",
        "openvdb": openvdb is not None,
        "scipy": load_scipy_ndimage() is not None,
        "skimage": load_skimage_measure() is not None,
        "vtk": load_vtk() is not None,
        "vtk_version": (
            getattr(getattr(load_vtk(), "vtkVersion", None), "GetVTKVersion", lambda: "")()
            if load_vtk() is not None else ""
        ),
        "simpleitk": load_simpleitk() is not None,
        "simpleitk_error": DEPENDENCY_IMPORT_ERRORS.get("SimpleITK", ""),
        "scipy_error": DEPENDENCY_IMPORT_ERRORS.get("scipy.ndimage", ""),
        "skimage_error": DEPENDENCY_IMPORT_ERRORS.get("skimage.measure", ""),
        "vtk_error": DEPENDENCY_IMPORT_ERRORS.get("vtk", ""),
    }

# =============================================================================
# MODULE: utils.py
# =============================================================================

