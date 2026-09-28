import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
bl_info = {
    "name": "DSG · Alignment Module",
    "author": "Max Tiburcio",
    "version": (2, 16, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > DSG",
    "description": "Occlusal/incisal dental auto-registration with ambiguity-safe three-zone fallback",
    "category": "3D View",
}


import heapq
import itertools
import json
import math

import bpy

from . import lifecycle
from . import core
from . import icon_manager
from . import ui_style
from . import dicom_module
from . import dental_surface_geometry
import numpy as np
from bpy.props import (
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    EnumProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree

try:
    from scipy.spatial import cKDTree as _SciPyKDTree
except Exception:
    _SciPyKDTree = None


# =============================================================================
# CONFIGURATION
# v2.2: no mesh triangulation, no heavyweight undo snapshots and modal ICP.
# =============================================================================

TAB_NAME = "DSG"
LANDMARK_COLLECTION = "DICP_Landmarks"
LANDMARK_PREFIX = "DICP_LM_"

# Shared workflow protocol: core.py is the single source of truth.
SUITE_PROTOCOL_VERSION = core.SUITE_PROTOCOL_VERSION
SUITE_LANGUAGE_KEY = core.SUITE_LANGUAGE_KEY
SUITE_STAGE_KEY = core.SUITE_STAGE_KEY
SUITE_ROLE_KEY = core.SUITE_ROLE_KEY
LEGACY_ROLE_KEY = core.LEGACY_ROLE_KEY
ROLE_DICOM_TEETH = core.ROLE_DICOM_TEETH
ROLE_DICOM_BONE = core.ROLE_DICOM_BONE
ROLE_DICOM_ALIGNMENT_COMPOSITE = core.ROLE_DICOM_ALIGNMENT_COMPOSITE
ROLE_IOS_SCAN = core.ROLE_IOS_SCAN
ROLE_IOS_ALIGNED = core.ROLE_IOS_ALIGNED
ROLE_DSG_MODEL = core.ROLE_DSG_MODEL
ROLE_DSG_GUIDE = core.ROLE_DSG_GUIDE


STEP_MODELS = 0
STEP_LANDMARKS = 1
STEP_READY = 2
STEP_DONE = 3

# Internal clinical defaults. They remain hidden from the user.
# Each landmark is also the centre of a bounded geodesic patch. ICP only
# compares the three corresponding patch pairs, never the complete arches.
# Each scale tuple contains: label, voxel, max source points PER PATCH,
# max target points PER PATCH, iterations, max distance, retained ratio,
# normal angle, use normals, tolerance.
ICP_SCALES = (
    # Coarse is intentionally forgiving: the three landmarks only bring both
    # meshes close enough for the surface ICP to take over.
    ("Coarse", 1.10, 650, 850, 14, 7.00, 0.82, 90.0, False, 9.0e-4),
    ("Medium", 0.60, 850, 1050, 12, 3.25, 0.84, 78.0, True, 3.5e-4),
    ("Fine",   0.32, 1100, 1300, 14, 1.35, 0.86, 62.0, True, 1.0e-4),
)

# Automatic area limits. These reproduce the useful idea behind Edit Mode >
# Select More (+): the clicked landmark is only a seed, then the surrounding
# connected dental surface is expanded before ICP. The Euclidean cap prevents
# the expansion from jumping to an antagonist or an opposite thin wall.
PATCH_GEODESIC_RADIUS_MM = 8.50
PATCH_EUCLIDEAN_RADIUS_MM = 12.00
PATCH_MAX_VERTICES = 5200
PATCH_SELECT_MORE_RINGS = 6
PATCH_MIN_VERTICES = 30
PATCH_CANDIDATE_LIMIT = 36000
PATCH_MIN_CORRESPONDENCES = 14
PATCH_MIN_ACTIVE_PAIRS = 2
PATCH_EDGE_MEDIAN_MULTIPLIER = 7.0
PATCH_EDGE_MIN_LIMIT_MM = 1.10
PATCH_EDGE_MAX_LIMIT_MM = 4.25
PATCH_MAX_NORMAL_CHANGE_DEG = 88.0
PATCH_FALLBACK_RADIUS_MM = 9.50
FALLBACK_PATCH_SAMPLE_LIMIT = 1100
ALIGNMENT_TIMER_SECONDS = 0.02

MIN_LANDMARK_SPAN_MM = 10.0
MIN_NORMALIZED_TRIANGLE_AREA = 0.0025
MAX_PAIR_DISTANCE_RELATIVE_ERROR = 0.45
MAX_PAIR_DISTANCE_ABSOLUTE_ERROR_MM = 8.0
MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM = 0.50

# Conservative hidden refinement. The three proven ICP scales remain unchanged.
# This pass only uses reciprocal correspondences inside the three areas selected
# by the user, solves a robust point-to-plane step and rejects any update that
# makes the common-surface error worse.
ROBUST_REFINEMENT_ITERATIONS = 8
ROBUST_VOXEL_MM = 0.22
ROBUST_MAX_SOURCE_PER_PATCH = 1200
ROBUST_MAX_TARGET_PER_PATCH = 1400
ROBUST_START_DISTANCE_MM = 1.20
ROBUST_END_DISTANCE_MM = 0.75
ROBUST_NORMAL_ANGLE_DEG = 65.0
ROBUST_RECIPROCAL_TOLERANCE_MM = 0.45
ROBUST_HUBER_DELTA_MM = 0.25
ROBUST_MAX_TRANSLATION_MM = 0.20
ROBUST_MAX_ROTATION_DEG = 0.30
ROBUST_MIN_IMPROVEMENT_MM = 0.0005
ROBUST_STOP_IMPROVEMENT_MM = 0.0015

EVALUATION_MAX_DISTANCE_MM = 1.20
EVALUATION_NORMAL_ANGLE_DEG = 70.0
EVALUATION_RECIPROCAL_TOLERANCE_MM = 0.50
EVALUATION_KEEP_RATIO = 0.85

# The user marks three broad, easy-to-recognise dental zones. The labels are
# deliberately clinical; Kabsch/ICP details remain completely hidden.
ROBUST_ZONE_KEYS = ("ANTERIOR", "POSTERIOR_RIGHT", "POSTERIOR_LEFT")
ROBUST_ZONE_LABELS_EN = ("Anterior facial", "Right posterior facial", "Left posterior facial")
ROBUST_ZONE_LABELS_ES = ("Anterior vestibular", "Posterior derecha", "Posterior izquierda")

# Pair-confidence weighting. A click is only a seed: the surrounding connected
# patch supplies the actual geometric information and determines its weight.
PATCH_MIN_CONFIDENCE = 0.18
PATCH_WEIGHT_MIN = 0.65
PATCH_WEIGHT_MAX = 1.35
PATCH_COARSE_MAX_TRANSLATION_MM = 4.0
PATCH_COARSE_MAX_ROTATION_DEG = 8.0

# Conservative global reciprocal refinement. It samples the whole available
# surfaces, but accepts only reciprocal, close and normal-compatible matches.
# Correspondences are balanced across the three clinical sectors, so a single
# dense molar or blurred occlusal region cannot dominate the solution.
GLOBAL_REFINEMENT_ITERATIONS = 5
GLOBAL_SAMPLE_CANDIDATES = 90000
GLOBAL_MAX_SOURCE_POINTS = 15000
GLOBAL_MAX_TARGET_POINTS = 18000
GLOBAL_VOXEL_MM = 0.45
GLOBAL_START_DISTANCE_MM = 0.90
GLOBAL_END_DISTANCE_MM = 0.55
GLOBAL_NORMAL_ANGLE_DEG = 55.0
GLOBAL_RECIPROCAL_TOLERANCE_MM = 0.40
GLOBAL_KEEP_RATIO = 0.76
GLOBAL_HUBER_DELTA_MM = 0.20
GLOBAL_MAX_TRANSLATION_MM = 0.12
GLOBAL_MAX_ROTATION_DEG = 0.18
GLOBAL_MIN_PER_ZONE = 24
GLOBAL_MAX_PER_ZONE = 480
GLOBAL_MIN_IMPROVEMENT_MM = 0.0005
GLOBAL_LOCAL_GUARD_TOLERANCE_MM = 0.003

# Automatic whole-mesh rescue.  The six clicks remain useful clinical hints,
# but they no longer have to place both meshes close enough for local ICP by
# themselves.  DSG evaluates the current landmark pose plus proper PCA axis
# hypotheses, refines only the best candidates, and accepts a correction only
# when reciprocal surface agreement improves materially.
AUTO_MESH_MAX_SOURCE_POINTS = 15000
AUTO_MESH_MAX_TARGET_POINTS = 18000
AUTO_MESH_PCA_VOXEL_MM = 1.50
AUTO_MESH_EVALUATION_POINTS = 2000
AUTO_MESH_REFINED_CANDIDATES = 8
# max distance, retained ratio, normal angle, Huber delta
AUTO_MESH_ICP_STAGES = (
    (8.0, 0.68, 82.0, 0.80),
    (4.5, 0.74, 72.0, 0.60),
    (2.4, 0.80, 62.0, 0.42),
    (1.2, 0.84, 55.0, 0.30),
    (0.65, 0.88, 48.0, 0.25),
)
AUTO_MESH_SCORE_DISTANCE_MM = 2.50
AUTO_MESH_SCORE_MAX_DISTANCE_MM = 6.00
AUTO_MESH_RECIPROCAL_DISTANCE_MM = 1.25
AUTO_MESH_PCA_AMBIGUITY_GAP = 0.16
AUTO_MESH_AMBIGUOUS_ROTATION_PRIOR_MM_PER_DEG = 0.0035
AUTO_MESH_MIN_CORRESPONDENCES = 90
AUTO_MESH_MIN_COVERAGE_PERCENT = 12.0
AUTO_MESH_ACCEPT_SCORE_RATIO = 0.92
AUTO_MESH_ACCEPT_COVERAGE_GAIN_PERCENT = 8.0
AUTO_MESH_MAX_INCREMENT_TRANSLATION_MM = 15.0
AUTO_MESH_MAX_INCREMENT_ROTATION_DEG = 28.0
# The whole-mesh pass runs *after* the clinician has paired three dental
# zones.  A large PCA hypothesis can otherwise exchange the two ends of a
# nearly symmetric arch (an apparently excellent RMS fit, but upside down / in
# reverse clinically).  It is a local refinement, never a second coarse
# registration, so it must remain close to the landmark pose.
AUTO_MESH_MAX_LANDMARK_POSE_ROTATION_DEG = 18.0
AUTO_MESH_MAX_LANDMARK_POSE_TRANSLATION_MM = 18.0
AUTO_MESH_REANCHOR_MAX_DISTANCE_MM = 4.50

# Plan A automatic registration.  DSG 9.6.4 adds a connected coronal crown
# shell, target-driven PCA recentering, sector-balanced scoring and a guarded
# point-to-plane finish.  Unlike the conservative whole-mesh rescue
# above, this stage starts from an arbitrary IOS pose.  It uses proper PCA
# hypotheses followed by target-driven trimmed ICP so extra gingiva in the IOS
# does not dominate the dental CBCT target.  Ambiguous near-symmetric solutions
# are rejected and sent to the three-zone Plan B instead of being guessed.
AUTO_GLOBAL_REFINED_CANDIDATES = 14
AUTO_GLOBAL_MIN_COVERAGE_PERCENT = 28.0
AUTO_GLOBAL_MAX_SCORE_MM = 1.80
AUTO_GLOBAL_MAX_NORMAL_MEDIAN_DEG = 68.0
AUTO_GLOBAL_MIN_RELATIVE_MARGIN = 0.055
AUTO_GLOBAL_MIN_ABSOLUTE_MARGIN_MM = 0.055
# When two whole-arch poses are globally similar, use three automatically
# distributed dental zones as a tie-breaker before falling back to manual clicks.
# This retains the safety logic of the 3-zone protocol but automates it.
AUTO_GLOBAL_ZONE_MAX_MEDIAN_MM = 2.60
AUTO_GLOBAL_ZONE_MAX_WORST_MM = 4.50
AUTO_GLOBAL_ZONE_MIN_MEDIAN_MARGIN_MM = 0.30
AUTO_GLOBAL_ZONE_MIN_WORST_MARGIN_MM = 0.50
AUTO_GLOBAL_ZONE_CANDIDATE_SCORE_WINDOW_MM = 0.24
# Additional tooth-landmark evidence.  The three clinical sectors remain the
# safety minimum, but Plan A now evaluates every available occlusal/incisal
# landmark so a locally convincing molar match cannot win against the whole arch.
AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MM = 3.20
AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MEDIAN_MM = 2.20
AUTO_GLOBAL_DENTAL_MIN_SUPPORT_RATIO = 0.50
AUTO_GLOBAL_DENTAL_MIN_SECTORS = 3
AUTO_GLOBAL_DENTAL_MIN_MARGIN_MM = 0.22
AUTO_GLOBAL_MAX_INCREMENT_TRANSLATION_MM = 22.0
AUTO_GLOBAL_MAX_INCREMENT_ROTATION_DEG = 42.0
# Coarse target-driven recentering compensates for IOS gingiva/scan-border bias
# before ICP.  Translation only: PCA still owns the coarse orientation.
AUTO_GLOBAL_RECENTER_ITERATIONS = 2
AUTO_GLOBAL_RECENTER_MAX_DISTANCE_MM = 22.0
AUTO_GLOBAL_RECENTER_KEEP_RATIO = 0.62
AUTO_GLOBAL_RECENTER_MAX_STEP_MM = 9.0
AUTO_GLOBAL_RECENTER_MAX_POINTS = 3500
# Three automatic dental sectors must all participate in the score.  This makes
# a locally excellent molar overlap lose against a slightly noisier whole-arch
# pose that explains anterior + both posterior regions.
AUTO_GLOBAL_SECTOR_DISTANCE_MM = 2.75
AUTO_GLOBAL_SECTOR_TARGET_COVERAGE_PERCENT = 22.0
AUTO_GLOBAL_SECTOR_PENALTY_PER_PERCENT = 0.022
AUTO_GLOBAL_SECTOR_RMS_PENALTY = 0.10
# Final point-to-plane polishing is intentionally tiny and score guarded.
AUTO_GLOBAL_PLANE_ITERATIONS = 3
AUTO_GLOBAL_PLANE_MAX_DISTANCE_MM = 1.25
AUTO_GLOBAL_PLANE_NORMAL_ANGLE_DEG = 62.0
AUTO_GLOBAL_PLANE_KEEP_RATIO = 0.82
AUTO_GLOBAL_PLANE_HUBER_DELTA_MM = 0.22
AUTO_GLOBAL_PLANE_MAX_TRANSLATION_MM = 0.40
AUTO_GLOBAL_PLANE_MAX_ROTATION_DEG = 0.65
# If the raw mesh-score winner fails distributed anatomy, Plan A may promote a
# nearby candidate that passes all three sectors and the available crown
# landmarks.  The window is deliberately bounded so anatomy cannot rescue a
# geometrically poor pose.
AUTO_GLOBAL_ANATOMY_RECOVERY_WINDOW_MM = 0.70
AUTO_GLOBAL_ICP_STAGES = (
    # max distance, retained target fraction, normal angle, Huber delta
    (10.0, 0.58, 90.0, 0.90),
    (6.0,  0.64, 82.0, 0.70),
    (3.5,  0.70, 72.0, 0.50),
    (1.8,  0.76, 62.0, 0.34),
    (0.95, 0.82, 56.0, 0.25),
)

# Final hidden validation gates. The familiar 0.50 mm robust mean remains the
# principal gate, while these checks prevent a good average from hiding one bad
# sector or poorly oriented correspondence set.
MAX_ACCEPTABLE_P95_MM = 0.95
MAX_ACCEPTABLE_PATCH_ERROR_MM = 0.65
MIN_ACCEPTABLE_PATCH_COVERAGE_PERCENT = 8.0
MAX_ACCEPTABLE_PATCH_NORMAL_MEDIAN_DEG = 50.0


# =============================================================================
# GENERAL HELPERS
# =============================================================================


_language_get = core.language_get
_language_set = core.language_set


def _is_spanish(props=None) -> bool:
    scene = getattr(props, "id_data", None) if props is not None else getattr(bpy.context, "scene", None)
    return core.is_spanish(scene)


def _t(props, english: str, spanish: str) -> str:
    scene = getattr(props, "id_data", None) if props is not None else getattr(bpy.context, "scene", None)
    return core.translate_ui(scene, english, spanish)


def _zone_label(props, index: int) -> str:
    safe_index = max(0, min(int(index), len(ROBUST_ZONE_LABELS_EN) - 1))
    scene = getattr(props, "id_data", None) if props is not None else getattr(bpy.context, "scene", None)
    return core.translate_ui(scene, ROBUST_ZONE_LABELS_EN[safe_index], ROBUST_ZONE_LABELS_ES[safe_index])


def _report(operator, levels, props, english: str, spanish: str | None = None) -> None:
    operator.report(levels, _t(props, english, spanish if spanish is not None else english))


def _set_role(obj, role: str) -> None:
    if obj is None:
        return
    core.set_role(obj, role)
    obj["dental_suite_component"] = "ALIGNMENT"


def _object_role(obj) -> str:
    return core.role_of(obj)


def _latest_role_object(role: str):
    return core.find_role(role)


def _is_dicom_or_alignment_helper(obj) -> bool:
    if obj is None:
        return False
    role = _object_role(obj)
    name = str(getattr(obj, "name", ""))
    if role in {ROLE_DICOM_TEETH, ROLE_DICOM_BONE}:
        return True
    if name.startswith((
        "DICOM_", "SEG_", "STL_Dientes", "STL_Hueso",
        "Dental_DICOM_", LANDMARK_PREFIX,
    )):
        return True
    for collection in getattr(obj, "users_collection", ()):
        if str(collection.name).startswith(("DICOM", "DICP_Landmarks")):
            return True
    return False


def _set_guide_entry_solid_view(context) -> None:
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            try:
                space = area.spaces.active
                space.shading.type = 'SOLID'
                space.shading.color_type = 'MATERIAL'
                space.shading.light = 'STUDIO'
                if hasattr(space.shading, 'show_xray'):
                    space.shading.show_xray = False
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)



IOS_GRAY_MATERIAL_NAME = "DSG_IOS_NeutralGray"
IOS_GRAY_RGBA = (0.52, 0.55, 0.58, 1.0)


def _set_principled_value(bsdf, names, value):
    if bsdf is None:
        return
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is not None:
            try:
                socket.default_value = value
                return
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _set_alignment_material_preview(context) -> None:
    """Use Material Preview while reviewing the IOS and FDI overlays."""
    if context is None:
        context = bpy.context
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            try:
                shading = area.spaces.active.shading
                shading.type = 'MATERIAL'
                if hasattr(shading, 'show_xray'):
                    shading.show_xray = False
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def ensure_ios_gray_material(obj, context=None) -> bool:
    """Give the IOS one stable neutral-gray Material Preview appearance."""
    if obj is None or getattr(obj, "type", "") != "MESH" or getattr(obj, "data", None) is None:
        return False
    mat = bpy.data.materials.get(IOS_GRAY_MATERIAL_NAME) or bpy.data.materials.new(IOS_GRAY_MATERIAL_NAME)
    try:
        mat.use_nodes = True
        mat.diffuse_color = IOS_GRAY_RGBA
        mat.metallic = 0.0
        mat.roughness = 0.48
        nodes = mat.node_tree.nodes if mat.node_tree else None
        bsdf = nodes.get("Principled BSDF") if nodes else None
        _set_principled_value(bsdf, ("Base Color",), IOS_GRAY_RGBA)
        _set_principled_value(bsdf, ("Roughness",), 0.48)
        _set_principled_value(bsdf, ("Metallic",), 0.0)
        _set_principled_value(bsdf, ("Coat Weight", "Clearcoat"), 0.06)
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            for i in range(len(obj.data.materials)):
                obj.data.materials[i] = mat
        obj.color = IOS_GRAY_RGBA
        obj["DSG_material_preview_role"] = "IOS_NEUTRAL_GRAY"
    except Exception:
        return False
    if context is not None:
        _set_alignment_material_preview(context)
    return True


DICOM_COLLECTION_PREFIXES = (
    "DICOM_WIZARD_PRO",
    "DICOM_RADIOGRAPHIC_DISPLAYS",
)


def _set_dicom_collections_hidden(context, hidden: bool) -> None:
    core.set_dicom_collections_hidden(context, hidden)


def _hide_dicom_scene_objects_except(context, keep_objects) -> None:
    """Hide DICOM volume/MPR helpers while keeping only the generated STL review meshes.

    The DICOM collections must be unhidden so the CBCT-derived STL object can be
    displayed, but the user requested not to see the full volume in the alignment
    review.  Therefore every DICOM collection object is hidden except the DICOM
    teeth STL selected as target and the aligned IOS STL.
    """
    keep = {obj for obj in keep_objects if obj is not None}
    for obj in list(context.scene.objects):
        if obj in keep:
            continue
        name = str(getattr(obj, "name", ""))
        in_dicom_collection = any(
            any(str(collection.name).startswith(prefix) for prefix in DICOM_COLLECTION_PREFIXES)
            for collection in getattr(obj, "users_collection", ())
        )
        is_dicom_named_object = name.startswith((
            "DICOM_",
            "SEG_",
            "STL_Dientes",
            "STL_Hueso",
            "Dental_DICOM_",
        ))
        if in_dicom_collection or is_dicom_named_object or _is_dicom_or_alignment_helper(obj):
            try:
                obj.hide_viewport = True
                obj.hide_render = True
                obj.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _clinical_cbct_review_objects(context, target):
    """Legacy visual overlays only.

    The v9.1.26 segmented composite intentionally returns no overlays: the
    complete Alignment stage must contain exactly IOS + CBCT composite.
    """
    try:
        if target is None or not bool(target.get("dental_suite_alignment_reference", False)):
            return [], [], []
        if str(target.get("dental_suite_alignment_reference_quality", "") or "") in {
            "ALL_SEGMENTED_DUPLICATE_COMPOSITE", "IMMEDIATE_ARCH_COMPOSITE"
        }:
            return [], [], []
        from . import cbct_dental_module
        teeth = list(cbct_dental_module.set_dentition_alignment_visual_smoothing(context, True))
        if not teeth:
            return [], [], []
        labels = [
            obj for obj in context.scene.objects
            if str(getattr(obj, "name", "")).startswith(cbct_dental_module.LABEL_OBJECT_PREFIX)
        ]
        safety = []
        canal = core.find_role(getattr(core, "ROLE_DICOM_MANDIBULAR_CANAL", "DICOM_MANDIBULAR_CANAL"))
        if canal is not None:
            safety.append(canal)
        return teeth, labels, safety
    except Exception as exc:
        print(f"[DSG Alignment] Clinical CBCT review fallback: {type(exc).__name__}: {exc}")
        return [], [], []


def _disable_clinical_cbct_review_smoothing(context) -> None:
    try:
        from . import cbct_dental_module
        cbct_dental_module.set_dentition_alignment_visual_smoothing(context, False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _prepare_alignment_review_view(context, source, target) -> None:
    """Review IOS against the high-resolution segmented CBCT teeth.

    ICP uses the exact native-resolution tooth composite. Final review hides that
    numerical composite and shows the equivalent individual tooth meshes with
    temporary non-destructive Laplacian display smoothing.  If individual teeth are
    unavailable (for example the no-AI DICOM-STL route), the numerical target is
    shown exactly as before.
    """
    if source is None or target is None:
        return

    clinical_teeth, fdi_labels, safety_objects = _clinical_cbct_review_objects(context, target)
    visual_refs = clinical_teeth if clinical_teeth else [target]
    keep = set([source, *visual_refs, *fdi_labels, *safety_objects])

    _set_dicom_collections_hidden(context, False)
    _hide_dicom_scene_objects_except(context, keep)

    # The exact native numerical target is hidden only for final visual review,
    # where the equivalent individual clinical teeth are easier to inspect.
    if clinical_teeth:
        try:
            target.hide_viewport = True
            target.hide_render = True
            target.hide_set(True)
            target.hide_select = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    for obj in [source, *visual_refs, *fdi_labels, *safety_objects]:
        try:
            obj.hide_viewport = False
            obj.hide_render = False if obj != target else obj.hide_render
            obj.hide_set(False)
            if obj in fdi_labels:
                obj.hide_select = True
            else:
                obj.hide_select = False
            if obj in safety_objects:
                obj.show_in_front = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        if hasattr(source, 'display_type'):
            source.display_type = 'SOLID'
        source.show_in_front = False
        source.color = IOS_GRAY_RGBA
        for ref in visual_refs:
            if hasattr(ref, 'display_type'):
                ref.display_type = 'SOLID'
            ref.show_in_front = True
            ref.color = (1.0, 0.55, 0.20, 0.70)
        for label in fdi_labels:
            label.show_in_front = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        # Select high-res clinical teeth and IOS for a useful frame-all view, but
        # keep the IOS active so the review remains consistent with prior DSG.
        for ref in visual_refs:
            if not getattr(ref, 'hide_select', False):
                ref.select_set(True)
        source.select_set(True)
        context.view_layer.objects.active = source
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            try:
                space = area.spaces.active
                space.shading.type = 'SOLID'
                space.shading.color_type = 'OBJECT'
                space.shading.light = 'STUDIO'
                if hasattr(space.shading, 'show_xray'):
                    space.shading.show_xray = True
                if hasattr(space.shading, 'xray_alpha'):
                    space.shading.xray_alpha = 0.45
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is not None:
                    with context.temp_override(area=area, region=region, space_data=space):
                        try:
                            bpy.ops.view3d.view_selected(use_all_regions=False)
                        except Exception:
                            _DSG_LOG.debug("suppressed exception", exc_info=True)
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _isolate_aligned_ios_for_guide(context, source) -> None:
    if source is None:
        return
    _set_dicom_collections_hidden(context, True)
    for obj in list(context.scene.objects):
        try:
            if obj == source:
                obj.hide_viewport = False
                obj.hide_set(False)
                obj.hide_select = False
                if hasattr(obj, 'display_type'):
                    obj.display_type = 'SOLID'
            elif _is_dicom_or_alignment_helper(obj):
                obj.hide_viewport = True
                obj.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        source.select_set(True)
        context.view_layer.objects.active = source
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _set_guide_entry_solid_view(context)


def _is_alignment_candidate(obj) -> bool:
    """Any real mesh may be the moving object; roles never restrict alignment."""
    if obj is None or obj.type != 'MESH':
        return False
    if _object_role(obj) == ROLE_DSG_GUIDE:
        return False
    if obj.name.startswith((LANDMARK_PREFIX, "DSG_", "DICOM_PLANE_", "DICOM_VOLUME")):
        return False
    return len(obj.data.vertices) >= 3


def _is_valid_reference_mesh(obj) -> bool:
    return bool(
        obj is not None
        and getattr(obj, "type", None) == "MESH"
        and getattr(obj, "data", None) is not None
        and len(obj.data.vertices) >= 3
        and not obj.name.startswith((LANDMARK_PREFIX, "DSG_", "DICOM_PLANE_", "DICOM_VOLUME"))
    )


def _latest_alignment_reference(context=None, props=None, *, exclude=None):
    """Find any usable fixed mesh, without forcing a dental-teeth role."""
    current = getattr(props, "icp_target_obj", None) if props is not None else None
    if _is_valid_reference_mesh(current) and current != exclude:
        return current
    active = getattr(getattr(context, "view_layer", None), "objects", None)
    active = getattr(active, "active", None) if active is not None else None
    if _is_valid_reference_mesh(active) and active != exclude and _object_role(active) != ROLE_IOS_SCAN:
        return active
    explicit = [
        obj for obj in bpy.data.objects
        if _is_valid_reference_mesh(obj)
        and obj != exclude
        and bool(obj.get("dental_suite_alignment_reference", False))
    ]
    if explicit:
        return explicit[-1]
    for role in (ROLE_DICOM_TEETH, ROLE_DICOM_BONE):
        candidate = _latest_role_object(role)
        if _is_valid_reference_mesh(candidate) and candidate != exclude:
            return candidate
    return None


def _auto_detect_models(context, props) -> tuple[bool, str]:
    selected_meshes = [obj for obj in context.selected_objects if _is_valid_reference_mesh(obj)]
    active = context.view_layer.objects.active
    if len(selected_meshes) == 2 and active in selected_meshes:
        props.icp_target_obj = active
        props.icp_source_obj = selected_meshes[0] if selected_meshes[1] == active else selected_meshes[1]
        return True, ""

    source = getattr(props, "icp_source_obj", None)
    if not _is_alignment_candidate(source):
        source = _latest_role_object(ROLE_IOS_SCAN)
    if source is None:
        selected_sources = [obj for obj in context.selected_objects if _is_alignment_candidate(obj)]
        source = active if active in selected_sources else (selected_sources[-1] if selected_sources else None)
    if source is None:
        source = next((o for o in reversed(list(bpy.data.objects)) if _is_alignment_candidate(o)), None)

    target = _latest_alignment_reference(context, props, exclude=source)
    if target is None:
        return False, _t(props, "Select any fixed reference mesh and the moving scan.", "Selecciona cualquier malla de referencia fija y el escaneado móvil.")
    if source is None or source == target:
        props.icp_target_obj = target
        return False, _t(props, "Select the moving scan and press Detect models.", "Selecciona el escaneado móvil y pulsa Detectar modelos.")

    props.icp_source_obj = source
    props.icp_target_obj = target
    target["dental_suite_alignment_reference"] = True
    _set_role(source, ROLE_IOS_SCAN)
    return True, ""



def _set_active_only(context, obj) -> None:
    """Make one object visible, selected and active without touching geometry."""
    if obj is None:
        return
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        for item in context.selected_objects:
            try:
                item.select_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.hide_select = False
        obj.select_set(True)
        context.view_layer.objects.active = obj
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _import_stl_file(context, filepath: str):
    """Import one STL with Blender 5.x and retain compatibility with older builds."""
    before_names = set(bpy.data.objects.keys())
    _ensure_object_mode(context)

    result = None
    primary_error = None
    try:
        result = bpy.ops.wm.stl_import(filepath=filepath)
    except Exception as exc:
        primary_error = exc
        try:
            # Legacy fallback for Blender versions that still expose import_mesh.stl.
            result = bpy.ops.import_mesh.stl(filepath=filepath)
        except Exception as legacy_exc:
            raise RuntimeError(
                f"STL import failed: {type(primary_error).__name__}: {primary_error}; "
                f"fallback: {type(legacy_exc).__name__}: {legacy_exc}"
            ) from legacy_exc

    if result is not None and 'FINISHED' not in result:
        raise RuntimeError(f"STL importer returned {result}")

    imported = [
        obj for obj in bpy.data.objects
        if obj.name not in before_names and getattr(obj, 'type', None) == 'MESH'
    ]
    selected_new = [
        obj for obj in context.selected_objects
        if getattr(obj, 'type', None) == 'MESH' and obj.name not in before_names
    ]
    if selected_new:
        imported = selected_new
    if not imported:
        active = context.view_layer.objects.active
        if active is not None and active.type == 'MESH' and active.name not in before_names:
            imported = [active]
    if not imported:
        raise RuntimeError("The STL importer did not create a mesh object")

    active = context.view_layer.objects.active
    source = active if active in imported else max(imported, key=lambda obj: len(obj.data.vertices))
    return source, imported

def _matrix_to_text(matrix: Matrix) -> str:
    return json.dumps([float(v) for row in matrix for v in row])


def _matrix_from_text(text: str) -> Matrix | None:
    if not text:
        return None
    try:
        values = json.loads(text)
        if not isinstance(values, list) or len(values) != 16:
            return None
        return Matrix((values[0:4], values[4:8], values[8:12], values[12:16]))
    except Exception:
        return None


def _ensure_object_mode(context) -> None:
    active = context.view_layer.objects.active
    if active and active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _alignment_composite_dental_bvh(obj):
    """Build an in-memory dental BVH without creating a third Blender object."""
    if obj is None or obj.type != "MESH":
        return None
    quality = str(obj.get("dental_suite_alignment_reference_quality", "") or "")
    if bool(obj.get("DSG_immediate_arch_composite", False)):
        teeth = _immediate_alignment_teeth(bpy.context, obj)
        if not teeth:
            return None
        inverse = obj.matrix_world.inverted_safe()
        vertices, polygons = [], []
        for tooth in teeth:
            offset = len(vertices)
            local_transform = inverse @ tooth.matrix_world
            vertices.extend(local_transform @ vertex.co for vertex in tooth.data.vertices)
            polygons.extend(
                tuple(offset + int(v) for v in polygon.vertices)
                for polygon in tooth.data.polygons if len(polygon.vertices) >= 3
            )
        return BVHTree.FromPolygons(vertices, polygons, all_triangles=False) if vertices and polygons else None
    if quality != "ALL_SEGMENTED_DUPLICATE_COMPOSITE":
        return None

    face_limit = int(obj.get("DSG_alignment_dental_face_count", 0) or 0)
    vertex_limit = int(obj.get("DSG_alignment_dental_vertex_count", 0) or 0)
    if face_limit < 1 or vertex_limit < 3:
        return None

    mesh = obj.data
    vertex_limit = min(vertex_limit, len(mesh.vertices))
    face_limit = min(face_limit, len(mesh.polygons))
    vertices = [mesh.vertices[index].co.copy() for index in range(vertex_limit)]
    polygons = []
    for polygon in mesh.polygons[:face_limit]:
        indices = tuple(int(v) for v in polygon.vertices)
        if len(indices) >= 3 and max(indices) < vertex_limit:
            polygons.append(indices)
    if not polygons:
        return None
    return BVHTree.FromPolygons(vertices, polygons, all_triangles=True)



def _validate_models(source, target, props=None) -> tuple[bool, str]:
    if source is None or target is None:
        return False, _t(props, "Select the intraoral scan and DICOM reference.", "Selecciona el escaneado y la referencia DICOM.")
    if source == target:
        return False, _t(props, "The scan and reference cannot be the same object.", "El escaneado y la referencia no pueden ser el mismo objeto.")
    if source.type != 'MESH' or target.type != 'MESH':
        return False, _t(props, "Both objects must be meshes.", "Ambos objetos deben ser mallas.")
    if len(source.data.vertices) < 3 or len(target.data.vertices) < 3:
        return False, _t(props, "One mesh has no valid geometry.", "Una de las mallas no contiene geometría válida.")
    return True, ""


def _assign_from_selection(context, props) -> bool:
    selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
    active = context.view_layer.objects.active
    if len(selected) != 2 or active not in selected:
        return False

    props.icp_target_obj = active
    props.icp_source_obj = selected[0] if selected[1] == active else selected[1]
    return True


def _landmark_attr(prefix: str, index: int) -> str:
    return f"{prefix}_point_{index + 1}"


def _get_local_landmarks(props, prefix: str) -> list[Vector]:
    count = props.source_point_count if prefix == "source" else props.target_point_count
    return [Vector(getattr(props, _landmark_attr(prefix, i))) for i in range(count)]


def _set_local_landmark(props, prefix: str, index: int, point: Vector) -> None:
    setattr(props, _landmark_attr(prefix, index), tuple(float(v) for v in point))


def _clear_landmark_values(props) -> None:
    props.source_point_count = 0
    props.target_point_count = 0
    for prefix in ("source", "target"):
        for index in range(3):
            setattr(props, _landmark_attr(prefix, index), (0.0, 0.0, 0.0))
    props.landmark_rmse = 0.0
    props.icp_error = 0.0
    props.icp_overlap = 0.0
    if hasattr(props, "icp_p95"):
        props.icp_p95 = 0.0
        props.icp_valid_pairs = 0
        if hasattr(props, "icp_max_patch_error"):
            props.icp_max_patch_error = 0.0
            props.icp_min_patch_coverage = 0.0
            props.icp_max_patch_normal_angle = 0.0
            props.icp_zone_summary = ""
        props.alignment_quality_approved = False
    props.status_message = ""
    props.aligned = False
    if hasattr(props, "source_patch_vertices"):
        props.source_patch_vertices = 0
        props.target_patch_vertices = 0


def _world_landmarks(obj, local_points: list[Vector]) -> np.ndarray:
    return np.asarray([tuple(obj.matrix_world @ point) for point in local_points], dtype=np.float64)


def _landmark_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.get(LANDMARK_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(LANDMARK_COLLECTION)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _clear_markers() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith(LANDMARK_PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)

    collection = bpy.data.collections.get(LANDMARK_COLLECTION)
    if collection and not collection.objects:
        for scene in bpy.data.scenes:
            try:
                scene.collection.children.unlink(collection)
            except RuntimeError:
                pass
        bpy.data.collections.remove(collection)


def _set_markers_hidden(hidden: bool) -> None:
    for obj in bpy.data.objects:
        if obj.name.startswith(LANDMARK_PREFIX):
            obj.hide_set(hidden)
            obj.hide_viewport = hidden
            obj.hide_render = True


def _marker_size(obj) -> float:
    dimensions = [abs(float(v)) for v in obj.dimensions if abs(float(v)) > 1.0e-6]
    if not dimensions:
        return 0.7
    return max(0.4, min(1.2, sum(dimensions) / len(dimensions) * 0.012))


def _create_marker(parent_obj, local_point: Vector, prefix: str, index: int) -> None:
    collection = _landmark_collection()
    props = getattr(getattr(bpy.context, "scene", None), "dicp_props", None)
    zone = _zone_label(props, index).replace(" ", "_")
    marker = bpy.data.objects.new(f"{LANDMARK_PREFIX}{prefix}_{index + 1}_{zone}", None)
    marker.empty_display_type = 'SPHERE'
    marker.empty_display_size = _marker_size(parent_obj)
    marker.show_in_front = True
    marker.show_name = True
    marker.hide_render = True
    marker.parent = parent_obj
    marker.matrix_parent_inverse = Matrix.Identity(4)
    marker.location = local_point
    marker["dicp_landmark_role"] = prefix
    marker["dicp_landmark_index"] = index
    collection.objects.link(marker)


def _rebuild_markers(props) -> None:
    _clear_markers()
    if props.icp_source_obj:
        for i, point in enumerate(_get_local_landmarks(props, "source")):
            _create_marker(props.icp_source_obj, point, "IOS", i)
    if props.icp_target_obj:
        for i, point in enumerate(_get_local_landmarks(props, "target")):
            _create_marker(props.icp_target_obj, point, "DICOM", i)


# =============================================================================
# AUTOMATIC GEODESIC AREAS AND RESPONSIVE ICP
# =============================================================================


def _to_world(points: np.ndarray, matrix_world: np.ndarray) -> np.ndarray:
    homogeneous = np.ones((len(points), 4), dtype=np.float64)
    homogeneous[:, :3] = points
    return (matrix_world @ homogeneous.T).T[:, :3]


def _to_world_normals(normals: np.ndarray, matrix_world: np.ndarray) -> np.ndarray:
    normal_matrix = np.array(Matrix(matrix_world).to_3x3().inverted().transposed(), dtype=np.float64)
    transformed = normals @ normal_matrix.T
    lengths = np.linalg.norm(transformed, axis=1, keepdims=True)
    return transformed / np.maximum(lengths, 1.0e-12)


class _MeshGraph:
    """Evaluated mesh data read once and reused by all three automatic areas."""

    __slots__ = ("points", "normals", "edges", "spatial_index", "meta")

    def __init__(self, points, normals, edges, meta=None):
        self.points = points
        self.normals = normals
        self.edges = edges
        self.meta = dict(meta or {})
        self.spatial_index = _SciPyKDTree(points) if _SciPyKDTree is not None else None

    def nearest_vertex(self, point: np.ndarray) -> int:
        if self.spatial_index is not None:
            _distance, index = self.spatial_index.query(point, k=1)
            return int(index)
        distances_sq = np.sum((self.points - point) ** 2, axis=1)
        return int(np.argmin(distances_sq))

    def vertices_inside_radius(self, point: np.ndarray, radius: float) -> np.ndarray:
        if self.spatial_index is not None:
            indices = np.asarray(self.spatial_index.query_ball_point(point, r=radius), dtype=np.int32)
        else:
            distances_sq = np.sum((self.points - point) ** 2, axis=1)
            indices = np.flatnonzero(distances_sq <= radius * radius).astype(np.int32)

        if len(indices) == 0:
            return indices
        if len(indices) > PATCH_CANDIDATE_LIMIT:
            distances_sq = np.sum((self.points[indices] - point) ** 2, axis=1)
            keep = np.argpartition(distances_sq, PATCH_CANDIDATE_LIMIT - 1)[:PATCH_CANDIDATE_LIMIT]
            indices = indices[keep]
        return np.unique(indices)


def _immediate_alignment_teeth(context, target):
    """Return the original segmented teeth represented by an immediate target.

    Immediate review composites contain bone + teeth, but IOS registration is
    dental-only.  The original segmented teeth remain in the scene, so use them
    as the mathematical target without creating a third visible Blender object.
    """
    if target is None or not bool(target.get("DSG_immediate_arch_composite", False)):
        return []
    try:
        from . import cbct_dental_module, tooth_analysis
        arch = str(target.get("DSG_bone_arch", "") or "").upper()
        excluded = set()
        raw = str(target.get("DSG_excluded_fdis", "") or "")
        for token in raw.split(','):
            token = token.strip()
            if token:
                try:
                    excluded.add(int(token))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        teeth = []
        for tooth in cbct_dental_module.dentition_objects(context):
            fdi = int(tooth.get("DSG_fdi_number", 0) or 0)
            if fdi <= 0 or fdi in excluded:
                continue
            if str(tooth_analysis.arch_from_fdi(fdi) or "").upper() != arch:
                continue
            if tooth.type == 'MESH' and tooth.data is not None and len(tooth.data.vertices) >= 3:
                teeth.append(tooth)
        return teeth
    except Exception:
        return []


def _mesh_graph_from_objects(objects) -> _MeshGraph | None:
    """Concatenate several mesh objects into one in-memory world-space graph."""
    point_blocks, normal_blocks, edge_blocks = [], [], []
    offset = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj is None or obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if mesh is None or len(mesh.vertices) < 3:
                continue
            mesh.update()
            nv = len(mesh.vertices)
            ne = len(mesh.edges)
            coordinates = np.empty(nv * 3, dtype=np.float64)
            normals = np.empty(nv * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", coordinates)
            mesh.vertices.foreach_get("normal", normals)
            local_points = coordinates.reshape((-1, 3))
            local_normals = normals.reshape((-1, 3))
            matrix_world = np.asarray(evaluated.matrix_world, dtype=np.float64)
            point_blocks.append(_to_world(local_points, matrix_world))
            normal_blocks.append(_to_world_normals(local_normals, matrix_world))
            if ne:
                edge_vertices = np.empty(ne * 2, dtype=np.int32)
                mesh.edges.foreach_get("vertices", edge_vertices)
                edge_blocks.append(edge_vertices.reshape((-1, 2)) + int(offset))
            offset += nv
        finally:
            evaluated.to_mesh_clear()
    if not point_blocks:
        return None
    points = np.concatenate(point_blocks, axis=0)
    normals = np.concatenate(normal_blocks, axis=0)
    edges = np.concatenate(edge_blocks, axis=0) if edge_blocks else np.empty((0, 2), dtype=np.int32)
    return _MeshGraph(points, normals, edges)


def _mesh_graph_from_registration_crowns(objects, *, relaxed=False):
    """Dental-only graph of connected coronal CBCT crown shells.

    DSG 9.6.4 keeps the old occlusal/incisal patch as the landmark source, but
    adds the connected axial crown walls for global registration.  This gives
    PCA/ICP substantially more asymmetric geometry while remaining root/bone
    safe.
    """
    data = dental_surface_geometry.build_registration_crown_graph_data(objects, relaxed=relaxed)
    if not data:
        return None
    points = np.asarray(data.get("points", []), dtype=np.float64)
    normals = np.asarray(data.get("normals", []), dtype=np.float64)
    edges = np.asarray(data.get("edges", []), dtype=np.int32)
    if len(points) < AUTO_MESH_MIN_CORRESPONDENCES:
        return None
    meta = {
        "reference_surface": str(data.get("reference_surface", "CORONAL_CROWN_SHELL")),
        "occlusal_axis": np.asarray(data.get("occlusal_axis"), dtype=np.float64),
        "landmarks_by_fdi": dict(data.get("landmarks_by_fdi", {})),
        "patches_by_fdi": dict(data.get("patches_by_fdi", {})),
        "axis_diagnostics": dict(data.get("axis_diagnostics", {})),
        "relaxed": bool(data.get("relaxed", relaxed)),
    }
    return _MeshGraph(points, normals, edges, meta=meta)


def _mesh_graph_from_occlusal_patches(objects, *, relaxed=False):
    """Compatibility wrapper retained for older scripts/tests."""
    return _mesh_graph_from_registration_crowns(objects, relaxed=relaxed)


def _alignment_target_tooth_objects(context, target):
    """Dental source objects for automatic registration/zone placement."""
    immediate = _immediate_alignment_teeth(context, target)
    if immediate:
        return immediate
    try:
        from . import cbct_dental_module, tooth_analysis
        teeth = [o for o in cbct_dental_module.dentition_objects(context) if o and o.type == 'MESH']
        active_arch = str(context.scene.get("DSG_active_arch", "") or "").upper()
        if active_arch in {"MAXILLA", "MANDIBLE"}:
            filtered = [
                tooth for tooth in teeth
                if str(tooth_analysis.arch_from_fdi(int(tooth.get("DSG_fdi_number", 0) or 0)) or "").upper() == active_arch
            ]
            if len(filtered) >= 3:
                return filtered
        return teeth
    except Exception:
        return []


def _tooth_world_centroid(obj):
    try:
        n = len(obj.data.vertices)
        if n < 1:
            return None
        co = np.empty(n * 3, dtype=np.float64)
        obj.data.vertices.foreach_get('co', co)
        local = co.reshape((-1, 3))
        centre = local.mean(axis=0)
        mw = np.asarray(obj.matrix_world, dtype=np.float64)
        return centre @ mw[:3, :3].T + mw[:3, 3]
    except Exception:
        return None



def _tooth_crown_surface_seed(obj, arch: str):
    """Return an IOS-visible crown-biased surface point for one segmented tooth.

    The previous zone seed used the full tooth centroid, which can lie near the
    root.  That is a poor landmark for IOS registration because the IOS has no
    root surface.  In DSG's LPS-oriented dental space, maxillary crowns are on
    the inferior side of each tooth and mandibular crowns on the superior side.
    Select a robust occlusal/incisal band and choose a central surface point.
    """
    try:
        n = len(obj.data.vertices)
        if n < 8:
            return None
        co = np.empty(n * 3, dtype=np.float64)
        obj.data.vertices.foreach_get('co', co)
        local = co.reshape((-1, 3))
        mw = np.asarray(obj.matrix_world, dtype=np.float64)
        world = local @ mw[:3, :3].T + mw[:3, 3]
        z = world[:, 2]
        arch = str(arch or '').upper()
        if arch == 'MAXILLA':
            limit = float(np.percentile(z, 22.0))
            candidates = world[z <= limit]
        elif arch == 'MANDIBLE':
            limit = float(np.percentile(z, 78.0))
            candidates = world[z >= limit]
        else:
            return None
        if len(candidates) < 3:
            return None
        centre_xy = np.median(candidates[:, :2], axis=0)
        xy_distance = np.linalg.norm(candidates[:, :2] - centre_xy[None, :], axis=1)
        # Prefer a central point within the crown band rather than the most
        # extreme cusp/outlier.  It is both surface-based and reproducible.
        return candidates[int(np.argmin(xy_distance))].copy()
    except Exception:
        return None


def _automatic_target_zone_seeds(context, target_obj, target_graph):
    """Create three well-distributed dental seeds without user clicks.

    Prefer FDI semantics (anterior, right posterior, left posterior).  If FDI is
    incomplete, fall back to a geometric U-arch construction: two extremes of
    the major PCA axis plus the point furthest from the line joining them.
    """
    teeth = _alignment_target_tooth_objects(context, target_obj)
    fdi_map = {int(o.get('DSG_fdi_number', 0) or 0): o for o in teeth}
    arch = str(target_obj.get("DSG_bone_arch", "") or "").upper()
    if not arch:
        available = [fdi for fdi in fdi_map if fdi > 0]
        arch = "MAXILLA" if any(10 <= fdi < 30 for fdi in available) else "MANDIBLE"
    if arch == "MAXILLA":
        groups = (
            (11, 21, 12, 22, 13, 23),
            (16, 15, 14, 17, 18, 13),
            (26, 25, 24, 27, 28, 23),
        )
    else:
        groups = (
            (31, 41, 32, 42, 33, 43),
            (46, 45, 44, 47, 48, 43),
            (36, 35, 34, 37, 38, 33),
        )
    seeds = []
    used = set()
    for group in groups:
        chosen = next((fdi_map.get(fdi) for fdi in group if fdi_map.get(fdi) is not None and fdi not in used), None)
        if chosen is None:
            break
        fdi = int(chosen.get('DSG_fdi_number', 0) or 0)
        used.add(fdi)
        crown_seed = None
        try:
            graph_landmarks = dict(getattr(target_graph, "meta", {}).get("landmarks_by_fdi", {}))
            if fdi in graph_landmarks:
                crown_seed = np.asarray(graph_landmarks[fdi], dtype=np.float64)
        except Exception:
            crown_seed = None
        if crown_seed is None:
            # Compatibility fallback for Plan B / legacy targets.  Plan A uses
            # the occlusal graph and normally never reaches this branch.
            crown_seed = _tooth_crown_surface_seed(chosen, arch)
        if crown_seed is None:
            centre = _tooth_world_centroid(chosen)
            if centre is None:
                break
            crown_seed = np.asarray(centre, dtype=np.float64)
        index = target_graph.nearest_vertex(np.asarray(crown_seed, dtype=np.float64))
        seeds.append(target_graph.points[index].copy())
    if len(seeds) == 3:
        ok, _message = _validate_point_spread(np.asarray(seeds, dtype=np.float64), None)
        if ok:
            return np.asarray(seeds, dtype=np.float64), "FDI"

    points = np.asarray(target_graph.points, dtype=np.float64)
    if len(points) < 3:
        return None, "NONE"
    centre, basis = _principal_frame(points)
    axis = basis[:, 0]
    projection = (points - centre) @ axis
    left_idx = int(np.argmin(projection))
    right_idx = int(np.argmax(projection))
    a, b = points[left_idx], points[right_idx]
    ab = b - a
    denom = max(float(np.dot(ab, ab)), 1.0e-12)
    t = np.clip(((points - a) @ ab) / denom, 0.0, 1.0)
    closest = a[None, :] + t[:, None] * ab[None, :]
    perpendicular = np.linalg.norm(points - closest, axis=1)
    anterior_idx = int(np.argmax(perpendicular))
    fallback = np.asarray([points[anterior_idx], a, b], dtype=np.float64)
    return fallback, "PCA"


def _validate_point_spread(points, props=None):
    points = np.asarray(points, dtype=np.float64)
    if len(points) != 3:
        return False, ""
    distances = [float(np.linalg.norm(points[i] - points[j])) for i in range(3) for j in range(i + 1, 3)]
    if min(distances) < MIN_LANDMARK_SPAN_MM:
        return False, _t(props, "Automatic dental zones are too close.", "Las zonas dentales automáticas están demasiado juntas.")
    a, b, c = points
    area2 = float(np.linalg.norm(np.cross(b - a, c - a)))
    scale = max(max(distances) ** 2, 1.0e-12)
    if area2 / scale < MIN_NORMALIZED_TRIANGLE_AREA:
        return False, _t(props, "Automatic dental zones are nearly collinear.", "Las zonas dentales automáticas están casi alineadas.")
    return True, ""


def _extract_world_mesh_graph(obj) -> _MeshGraph | None:
    """Read evaluated vertices, normals and edge topology with foreach_get."""
    # Immediate review composites contain bone.  Registration must still use
    # only the segmented teeth that remain after virtual extraction selection.
    if obj is not None and bool(obj.get("DSG_immediate_arch_composite", False)):
        dental_graph = _mesh_graph_from_objects(_immediate_alignment_teeth(bpy.context, obj))
        if dental_graph is not None:
            return dental_graph
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if mesh is None or len(mesh.vertices) < 3 or len(mesh.edges) < 2:
            return None
        mesh.update()
        vertex_count = len(mesh.vertices)
        edge_count = len(mesh.edges)

        coordinates = np.empty(vertex_count * 3, dtype=np.float64)
        normals = np.empty(vertex_count * 3, dtype=np.float64)
        edge_vertices = np.empty(edge_count * 2, dtype=np.int32)
        mesh.vertices.foreach_get("co", coordinates)
        mesh.vertices.foreach_get("normal", normals)
        mesh.edges.foreach_get("vertices", edge_vertices)

        local_points = coordinates.reshape((-1, 3))
        local_normals = normals.reshape((-1, 3))
        edges = edge_vertices.reshape((-1, 2))

        # The Blender target contains ALL duplicated segmentation components,
        # but IOS alignment is dental. Teeth were written first into the
        # composite, so restrict graph/whole-mesh refinement/geodesic ICP to
        # that exact connected/disconnected dental prefix.
        quality = str(obj.get("dental_suite_alignment_reference_quality", "") or "")
        if quality == "ALL_SEGMENTED_DUPLICATE_COMPOSITE":
            dental_limit = int(obj.get("DSG_alignment_dental_vertex_count", 0) or 0)
            if 3 <= dental_limit <= len(local_points):
                local_points = local_points[:dental_limit]
                local_normals = local_normals[:dental_limit]
                if len(edges):
                    edge_mask = (
                        (edges[:, 0] < dental_limit)
                        & (edges[:, 1] < dental_limit)
                    )
                    edges = edges[edge_mask]

        matrix_world = np.asarray(evaluated.matrix_world, dtype=np.float64)
        world_points = _to_world(local_points, matrix_world)
        world_normals = _to_world_normals(local_normals, matrix_world)
        return _MeshGraph(world_points, world_normals, edges)
    finally:
        evaluated.to_mesh_clear()


def _fallback_local_patch(graph: _MeshGraph, seed_world: np.ndarray):
    candidate = graph.vertices_inside_radius(seed_world, PATCH_FALLBACK_RADIUS_MM)
    if len(candidate) == 0:
        nearest = graph.nearest_vertex(seed_world)
        candidate = np.asarray([nearest], dtype=np.int32)
    distances_sq = np.sum((graph.points[candidate] - seed_world) ** 2, axis=1)
    if len(candidate) > PATCH_MAX_VERTICES:
        keep = np.argpartition(distances_sq, PATCH_MAX_VERTICES - 1)[:PATCH_MAX_VERTICES]
        candidate = candidate[keep]
    return graph.points[candidate].copy(), graph.normals[candidate].copy(), candidate


def _extract_geodesic_patch(graph: _MeshGraph, seed_world: np.ndarray):
    """Expand a landmark into a connected Select More-style dental patch.

    The landmark is not treated as the ICP data. It is only the seed used to
    find a nearby vertex; from there we grow a bounded connected area, similar
    to selecting one vertex in Edit Mode and pressing Select More (+) several
    times. A softer geodesic pass keeps the centre coherent, while the final
    ring expansion gives ICP enough real surface to converge.
    """
    seed_world = np.asarray(seed_world, dtype=np.float64)
    seed_global = graph.nearest_vertex(seed_world)
    candidate = graph.vertices_inside_radius(seed_world, PATCH_EUCLIDEAN_RADIUS_MM)
    if len(candidate) < PATCH_MIN_VERTICES:
        return _fallback_local_patch(graph, seed_world)

    if seed_global not in candidate:
        candidate = np.unique(np.append(candidate, seed_global).astype(np.int32))
    else:
        candidate = np.sort(candidate)

    membership = np.zeros(len(graph.points), dtype=np.bool_)
    membership[candidate] = True
    edge_mask = membership[graph.edges[:, 0]] & membership[graph.edges[:, 1]]
    local_edges_global = graph.edges[edge_mask]
    if len(local_edges_global) < 3:
        return _fallback_local_patch(graph, seed_world)

    edge_vectors = graph.points[local_edges_global[:, 0]] - graph.points[local_edges_global[:, 1]]
    edge_lengths = np.linalg.norm(edge_vectors, axis=1)
    positive = edge_lengths[edge_lengths > 1.0e-9]
    if len(positive) == 0:
        return _fallback_local_patch(graph, seed_world)

    median_edge = float(np.median(positive))
    edge_limit = max(
        PATCH_EDGE_MIN_LIMIT_MM,
        min(PATCH_EDGE_MAX_LIMIT_MM, median_edge * PATCH_EDGE_MEDIAN_MULTIPLIER),
    )

    # Select More (+) should follow mesh connectivity. We therefore build the
    # broad adjacency from length-limited edges only; normal filtering is used
    # only for the initial coherent geodesic core, not for the final expansion.
    broad_mask = edge_lengths <= edge_limit
    broad_edges_global = local_edges_global[broad_mask]
    broad_lengths = edge_lengths[broad_mask]
    if len(broad_edges_global) < 3:
        return _fallback_local_patch(graph, seed_world)

    local_u = np.searchsorted(candidate, broad_edges_global[:, 0])
    local_v = np.searchsorted(candidate, broad_edges_global[:, 1])
    broad_adjacency = [[] for _ in range(len(candidate))]
    for u, v, weight in zip(local_u.tolist(), local_v.tolist(), broad_lengths.tolist()):
        broad_adjacency[u].append((v, weight))
        broad_adjacency[v].append((u, weight))

    normal_dots = np.abs(np.sum(
        graph.normals[broad_edges_global[:, 0]] * graph.normals[broad_edges_global[:, 1]],
        axis=1,
    ))
    normal_limit = math.cos(math.radians(PATCH_MAX_NORMAL_CHANGE_DEG))
    safe_mask = normal_dots >= normal_limit
    safe_edges_global = broad_edges_global[safe_mask]
    safe_lengths = broad_lengths[safe_mask]

    seed_local = int(np.searchsorted(candidate, seed_global))
    if len(safe_edges_global) >= 3:
        safe_u = np.searchsorted(candidate, safe_edges_global[:, 0])
        safe_v = np.searchsorted(candidate, safe_edges_global[:, 1])
        safe_adjacency = [[] for _ in range(len(candidate))]
        for u, v, weight in zip(safe_u.tolist(), safe_v.tolist(), safe_lengths.tolist()):
            safe_adjacency[u].append((v, weight))
            safe_adjacency[v].append((u, weight))
    else:
        safe_adjacency = broad_adjacency

    distances = np.full(len(candidate), np.inf, dtype=np.float64)
    distances[seed_local] = 0.0
    queue = [(0.0, seed_local)]
    visited = []
    closed = np.zeros(len(candidate), dtype=np.bool_)

    while queue and len(visited) < PATCH_MAX_VERTICES:
        distance, vertex = heapq.heappop(queue)
        if closed[vertex]:
            continue
        if distance > PATCH_GEODESIC_RADIUS_MM:
            break
        closed[vertex] = True
        visited.append(vertex)
        for neighbour, weight in safe_adjacency[vertex]:
            if closed[neighbour]:
                continue
            next_distance = distance + weight
            if next_distance < distances[neighbour] and next_distance <= PATCH_GEODESIC_RADIUS_MM:
                distances[neighbour] = next_distance
                heapq.heappush(queue, (next_distance, neighbour))

    # If the coherent geodesic core is too small because the STL topology is
    # irregular, start from the seed and let the Select More rings build a patch.
    selected_local = set(int(index) for index in visited) if visited else {seed_local}
    frontier = set(selected_local)

    for _ring in range(PATCH_SELECT_MORE_RINGS):
        if not frontier or len(selected_local) >= PATCH_MAX_VERTICES:
            break
        next_frontier = set()
        for vertex in frontier:
            for neighbour, _weight in broad_adjacency[vertex]:
                if neighbour in selected_local:
                    continue
                global_index = int(candidate[neighbour])
                if np.linalg.norm(graph.points[global_index] - seed_world) > PATCH_EUCLIDEAN_RADIUS_MM:
                    continue
                selected_local.add(neighbour)
                next_frontier.add(neighbour)
                if len(selected_local) >= PATCH_MAX_VERTICES:
                    break
            if len(selected_local) >= PATCH_MAX_VERTICES:
                break
        frontier = next_frontier

    if len(selected_local) < PATCH_MIN_VERTICES:
        return _fallback_local_patch(graph, seed_world)

    selected_array = np.fromiter(selected_local, dtype=np.int32, count=len(selected_local))
    selected_global = candidate[selected_array]
    return graph.points[selected_global].copy(), graph.normals[selected_global].copy(), selected_global


def _voxel_downsample(points, normals, voxel_size: float, max_points: int, seed: int):
    if points is None or len(points) == 0:
        return None, None
    if _SciPyKDTree is None:
        max_points = min(max_points, FALLBACK_PATCH_SAMPLE_LIMIT)

    keys = np.floor(points / max(voxel_size, 1.0e-6)).astype(np.int64)
    _, first_indices = np.unique(keys, axis=0, return_index=True)
    sampled_points = points[first_indices]
    sampled_normals = None if normals is None else normals[first_indices]

    if len(sampled_points) > max_points:
        rng = np.random.default_rng(seed)
        selected = rng.choice(len(sampled_points), size=max_points, replace=False)
        sampled_points = sampled_points[selected]
        if sampled_normals is not None:
            sampled_normals = sampled_normals[selected]
    return sampled_points, sampled_normals


class _NearestIndex:
    """Vectorized SciPy queries when available, compact Blender fallback otherwise."""

    def __init__(self, target_points: np.ndarray):
        self.target = target_points
        self.scipy_tree = _SciPyKDTree(target_points) if _SciPyKDTree is not None else None
        self.blender_tree = None
        if self.scipy_tree is None:
            tree = KDTree(len(target_points))
            for index, point in enumerate(target_points):
                tree.insert(Vector((float(point[0]), float(point[1]), float(point[2]))), index)
            tree.balance()
            self.blender_tree = tree

    def query(self, source_points: np.ndarray):
        if self.scipy_tree is not None:
            try:
                distances, indices = self.scipy_tree.query(source_points, k=1, workers=-1)
            except TypeError:
                distances, indices = self.scipy_tree.query(source_points, k=1)
            indices = np.asarray(indices, dtype=np.int32)
            return self.target[indices], indices, np.asarray(distances, dtype=np.float64)

        matched = np.empty_like(source_points)
        indices = np.empty(len(source_points), dtype=np.int32)
        distances = np.empty(len(source_points), dtype=np.float64)
        for i, point in enumerate(source_points):
            _, target_index, distance = self.blender_tree.find(
                Vector((float(point[0]), float(point[1]), float(point[2])))
            )
            matched[i] = self.target[target_index]
            indices[i] = target_index
            distances[i] = distance
        return matched, indices, distances


def _best_fit(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    if len(source) < 3:
        return np.eye(4, dtype=np.float64)
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[2, :] *= -1
        rotation = vt.T @ u.T
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = target_center - rotation @ source_center
    return transform



def _limited_alignment_sample(points, normals, max_points: int, seed: int):
    """Return a deterministic point/normal subset for whole-mesh hypotheses."""
    points = np.asarray(points, dtype=np.float64)
    normals = None if normals is None else np.asarray(normals, dtype=np.float64)
    if len(points) <= int(max_points):
        return points.copy(), None if normals is None else normals.copy()
    rng = np.random.default_rng(int(seed))
    chosen = np.sort(rng.choice(len(points), size=int(max_points), replace=False))
    return points[chosen], None if normals is None else normals[chosen]


def _principal_frame_diagnostics(points):
    """Return centroid, right-handed PCA basis, eigenvalues and ambiguity.

    PCA axes become unreliable when two eigenvalues are similar.  The ambiguity
    value is 0 for a strongly anisotropic partial arch and approaches 1 when the
    principal in-plane axes cannot be distinguished safely.
    """
    points = np.asarray(points, dtype=np.float64)
    centre = points.mean(axis=0)
    centred = points - centre
    covariance = centred.T @ centred / max(len(points) - 1, 1)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    values = np.maximum(values[order], 0.0)
    basis = vectors[:, order]
    if float(np.linalg.det(basis)) < 0.0:
        basis[:, -1] *= -1.0
    major = max(float(values[0]), 1.0e-12)
    first_gap = max(0.0, float(values[0] - values[1])) / major
    ambiguity = float(np.clip(1.0 - first_gap / max(AUTO_MESH_PCA_AMBIGUITY_GAP, 1.0e-6), 0.0, 1.0))
    return centre, basis, values, ambiguity


def _principal_frame(points):
    centre, basis, _values, _ambiguity = _principal_frame_diagnostics(points)
    return centre, basis


def _proper_axis_hypotheses(source_points, target_points):
    """Generate the 24 proper signed PCA-axis mappings plus identity."""
    source_centre, source_basis = _principal_frame(source_points)
    target_centre, target_basis = _principal_frame(target_points)
    candidates = [np.eye(4, dtype=np.float64)]
    seen = set()
    for permutation in itertools.permutations(range(3)):
        permutation_matrix = np.zeros((3, 3), dtype=np.float64)
        for column, source_axis in enumerate(permutation):
            permutation_matrix[source_axis, column] = 1.0
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            signed = permutation_matrix @ np.diag(signs)
            if float(np.linalg.det(signed)) < 0.0:
                continue
            rotation = target_basis @ signed.T @ source_basis.T
            if float(np.linalg.det(rotation)) < 0.0:
                continue
            key = tuple(np.rint(rotation.ravel() * 1.0e6).astype(np.int64))
            if key in seen:
                continue
            seen.add(key)
            transform = np.eye(4, dtype=np.float64)
            transform[:3, :3] = rotation
            transform[:3, 3] = target_centre - rotation @ source_centre
            candidates.append(transform)
    return candidates


def _mesh_candidate_score(
    transformed_source,
    transformed_normals,
    target_points,
    target_normals,
    target_index=None,
):
    """Score partial dental surfaces bidirectionally and deterministically.

    A low score requires a compact forward distance, a reasonable reverse fit,
    reciprocal nearest-neighbour support, useful coverage and compatible normals.
    This prevents a small accidental overlap from defeating the correct arch pose.
    """
    transformed_source = np.asarray(transformed_source, dtype=np.float64)
    target_points = np.asarray(target_points, dtype=np.float64)
    transformed_normals = None if transformed_normals is None else np.asarray(transformed_normals, dtype=np.float64)
    target_normals = None if target_normals is None else np.asarray(target_normals, dtype=np.float64)

    if len(transformed_source) > AUTO_MESH_EVALUATION_POINTS:
        # Deterministic uniform sample: repeated runs produce the same winner.
        chosen = np.linspace(0, len(transformed_source) - 1, AUTO_MESH_EVALUATION_POINTS).round().astype(np.int64)
        source_eval = transformed_source[chosen]
        source_normals_eval = None if transformed_normals is None else transformed_normals[chosen]
    else:
        source_eval = transformed_source
        source_normals_eval = transformed_normals

    if target_index is None:
        target_index = _NearestIndex(target_points)
    matched, target_indices, distances = target_index.query(source_eval)
    finite = np.isfinite(distances)
    if int(finite.sum()) < AUTO_MESH_MIN_CORRESPONDENCES:
        return float('inf'), 0.0, 90.0

    valid_indices = np.flatnonzero(finite & (distances <= AUTO_MESH_SCORE_MAX_DISTANCE_MM))
    if len(valid_indices) < AUTO_MESH_MIN_CORRESPONDENCES:
        valid_indices = np.flatnonzero(finite)
    ordered = valid_indices[np.argsort(distances[valid_indices])]
    keep_count = max(
        min(AUTO_MESH_MIN_CORRESPONDENCES, len(ordered)),
        int(round(len(ordered) * 0.62)),
    )
    selected = ordered[:keep_count]
    selected_distances = distances[selected]
    rms = float(np.sqrt(np.mean(np.square(selected_distances))))
    p95 = float(np.percentile(selected_distances, 95.0))
    coverage = 100.0 * float(np.count_nonzero(finite & (distances <= AUTO_MESH_SCORE_DISTANCE_MM))) / max(len(distances), 1)

    normal_median = 90.0
    if source_normals_eval is not None and target_normals is not None and len(selected):
        dots = np.einsum('ij,ij->i', source_normals_eval[selected], target_normals[target_indices[selected]])
        dots = np.clip(np.abs(dots), 0.0, 1.0)
        normal_median = float(np.degrees(np.arccos(np.median(dots))))

    # Reverse and reciprocal checks are evaluated against the complete candidate
    # source set so partial target coverage cannot win through a tiny local patch.
    source_index = _NearestIndex(transformed_source)
    back_matched, _reverse_indices, reverse_distances = source_index.query(target_points)
    reverse_finite = reverse_distances[np.isfinite(reverse_distances)]
    if len(reverse_finite):
        reverse_sorted = np.sort(reverse_finite)
        reverse_keep = max(1, int(round(len(reverse_sorted) * 0.36)))
        reverse_rms = float(np.sqrt(np.mean(np.square(reverse_sorted[:reverse_keep]))))
    else:
        reverse_rms = AUTO_MESH_SCORE_MAX_DISTANCE_MM

    reciprocal_distance = np.linalg.norm(source_eval - back_matched[target_indices], axis=1)
    reciprocal_valid = finite & np.isfinite(reciprocal_distance)
    reciprocal_coverage = 100.0 * float(np.count_nonzero(
        reciprocal_valid & (reciprocal_distance <= AUTO_MESH_RECIPROCAL_DISTANCE_MM)
    )) / max(len(source_eval), 1)

    coverage_penalty = max(0.0, AUTO_MESH_MIN_COVERAGE_PERCENT - coverage) * 0.08
    reciprocal_penalty = max(0.0, 18.0 - reciprocal_coverage) * 0.025
    score = (
        0.55 * rms
        + 0.18 * p95
        + 0.22 * reverse_rms
        + 0.010 * normal_median
        + coverage_penalty
        + reciprocal_penalty
    )
    return float(score), float(coverage), float(normal_median)

def _refine_mesh_hypothesis(
    source_points,
    source_normals,
    target_points,
    target_normals,
    initial_transform,
    target_index,
):
    """Run a bounded broad-to-fine ICP on one rigid whole-mesh hypothesis."""
    total = np.asarray(initial_transform, dtype=np.float64).copy()
    moving = _apply_points(source_points, total)
    moving_normals = None if source_normals is None else _apply_normals(source_normals, total)

    for maximum_distance, keep_ratio, normal_angle, huber_delta in AUTO_MESH_ICP_STAGES:
        matched, target_indices, distances = target_index.query(moving)
        source_index = _NearestIndex(moving)
        back_matched, _back_indices, _back_distances = source_index.query(target_points)
        reciprocal_distance = np.linalg.norm(moving - back_matched[target_indices], axis=1)
        reciprocal_tolerance = max(AUTO_MESH_RECIPROCAL_DISTANCE_MM, 0.28 * float(maximum_distance))
        valid = np.isfinite(distances) & (distances <= float(maximum_distance))
        valid &= np.isfinite(reciprocal_distance) & (reciprocal_distance <= reciprocal_tolerance)
        if moving_normals is not None and target_normals is not None:
            dots = np.einsum('ij,ij->i', moving_normals, target_normals[target_indices])
            valid &= np.abs(dots) >= math.cos(math.radians(float(normal_angle)))
        selected = np.flatnonzero(valid)
        if len(selected) < AUTO_MESH_MIN_CORRESPONDENCES:
            break
        selected = selected[np.argsort(distances[selected])]
        keep_count = max(
            AUTO_MESH_MIN_CORRESPONDENCES,
            min(len(selected), int(round(len(selected) * float(keep_ratio)))),
        )
        selected = selected[:keep_count]
        incremental = _weighted_best_fit_huber(
            moving[selected], matched[selected], None,
            delta_mm=float(huber_delta), irls_iterations=3,
        )
        if (
            float(np.linalg.norm(incremental[:3, 3])) > AUTO_MESH_MAX_INCREMENT_TRANSLATION_MM
            or _rotation_degrees(incremental) > AUTO_MESH_MAX_INCREMENT_ROTATION_DEG
        ):
            break
        moving = _apply_points(moving, incremental)
        if moving_normals is not None:
            moving_normals = _apply_normals(moving_normals, incremental)
        total = incremental @ total

    score, coverage, normal_median = _mesh_candidate_score(
        moving,
        moving_normals,
        target_points,
        target_normals,
        target_index=target_index,
    )
    return total, score, coverage, normal_median


def _automatic_whole_mesh_refinement(
    source_points,
    source_normals,
    target_points,
    target_normals,
):
    """Find a safer initial pose when landmark placement is inaccurate.

    The returned transform is a correction in the CURRENT world frame of the
    source mesh.  No reflection or non-uniform scale is ever considered.
    """
    source_points, source_normals = _voxel_downsample(
        np.asarray(source_points, dtype=np.float64), source_normals,
        AUTO_MESH_PCA_VOXEL_MM, AUTO_MESH_MAX_SOURCE_POINTS, 9101,
    )
    target_points, target_normals = _voxel_downsample(
        np.asarray(target_points, dtype=np.float64), target_normals,
        AUTO_MESH_PCA_VOXEL_MM, AUTO_MESH_MAX_TARGET_POINTS, 9201,
    )
    if (
        len(source_points) < AUTO_MESH_MIN_CORRESPONDENCES
        or len(target_points) < AUTO_MESH_MIN_CORRESPONDENCES
    ):
        return np.eye(4, dtype=np.float64), {
            'accepted': False, 'score_before': float('inf'), 'score_after': float('inf'),
            'coverage_before': 0.0, 'coverage_after': 0.0, 'normal_median': 90.0,
        }

    target_index = _NearestIndex(target_points)
    score_before, coverage_before, _normal_before = _mesh_candidate_score(
        source_points, source_normals, target_points, target_normals, target_index
    )

    _sc, _sb, _sv, source_ambiguity = _principal_frame_diagnostics(source_points)
    _tc, _tb, _tv, target_ambiguity = _principal_frame_diagnostics(target_points)
    pca_ambiguity = max(float(source_ambiguity), float(target_ambiguity))

    hypotheses = _proper_axis_hypotheses(source_points, target_points)
    ranked = []
    for index, transform in enumerate(hypotheses):
        transformed = _apply_points(source_points, transform)
        transformed_normals = None if source_normals is None else _apply_normals(source_normals, transform)
        score, coverage, normal_median = _mesh_candidate_score(
            transformed, transformed_normals, target_points, target_normals, target_index
        )
        # In a symmetric complete arch PCA may swap the two in-plane axes.  The
        # current landmark/Kabsch pose is identity in this frame, so a soft prior
        # preserves it unless whole-surface evidence is materially better.
        rotation_prior = (
            pca_ambiguity
            * AUTO_MESH_AMBIGUOUS_ROTATION_PRIOR_MM_PER_DEG
            * _rotation_degrees(transform)
        )
        adjusted_score = float(score + rotation_prior)
        ranked.append((adjusted_score, -coverage, index, transform, normal_median, score))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))

    # Always include the current landmark pose, then refine only the best PCA
    # candidates to keep Blender responsive.
    safe_ranked = [
        item for item in ranked
        if _rotation_degrees(item[3]) <= AUTO_MESH_MAX_LANDMARK_POSE_ROTATION_DEG
        and float(np.linalg.norm(item[3][:3, 3])) <= AUTO_MESH_MAX_LANDMARK_POSE_TRANSLATION_MM
    ]
    selected = safe_ranked[:AUTO_MESH_REFINED_CANDIDATES]
    identity_entry = next((item for item in ranked if item[2] == 0), None)
    if identity_entry is not None and all(item[2] != 0 for item in selected):
        selected.append(identity_entry)

    best = (float('inf'), 0.0, 90.0, np.eye(4, dtype=np.float64))
    for _adjusted_score, _neg_coverage, _index, hypothesis, _raw_normal, _raw_score in selected:
        refined, score, coverage, normal_median = _refine_mesh_hypothesis(
            source_points,
            source_normals,
            target_points,
            target_normals,
            hypothesis,
            target_index,
        )
        if (score, -coverage) < (best[0], -best[1]):
            best = (score, coverage, normal_median, refined)

    score_after, coverage_after, normal_after, correction = best
    materially_better = (
        score_after <= score_before * AUTO_MESH_ACCEPT_SCORE_RATIO
        or coverage_after >= coverage_before + AUTO_MESH_ACCEPT_COVERAGE_GAIN_PERCENT
        or (
            coverage_before < AUTO_MESH_MIN_COVERAGE_PERCENT
            and coverage_after >= AUTO_MESH_MIN_COVERAGE_PERCENT + 4.0
        )
    )
    orientation_safe = bool(
        _rotation_degrees(correction) <= AUTO_MESH_MAX_LANDMARK_POSE_ROTATION_DEG
        and float(np.linalg.norm(correction[:3, 3])) <= AUTO_MESH_MAX_LANDMARK_POSE_TRANSLATION_MM
    )
    accepted = bool(
        np.isfinite(score_after)
        and coverage_after >= AUTO_MESH_MIN_COVERAGE_PERCENT
        and materially_better
        and orientation_safe
    )
    if not accepted:
        correction = np.eye(4, dtype=np.float64)
        score_after = score_before
        coverage_after = coverage_before
        normal_after = _normal_before

    return correction, {
        'accepted': accepted,
        'score_before': float(score_before),
        'score_after': float(score_after),
        'coverage_before': float(coverage_before),
        'coverage_after': float(coverage_after),
        'normal_median': float(normal_after),
        'translation_mm': float(np.linalg.norm(correction[:3, 3])),
        'rotation_deg': float(_rotation_degrees(correction)),
        'pca_ambiguity': float(pca_ambiguity),
        'hypotheses_tested': int(len(hypotheses)),
        'orientation_guard_passed': bool(orientation_safe),
    }



def _target_zone_labels(target_points, validation_seeds):
    """Assign each target sample to the nearest automatic dental validation zone."""
    if validation_seeds is None:
        return None
    points = np.asarray(target_points, dtype=np.float64)
    seeds = np.asarray(validation_seeds, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or seeds.shape != (3, 3):
        return None
    delta = points[:, None, :] - seeds[None, :, :]
    labels = np.argmin(np.einsum('nzi,nzi->nz', delta, delta), axis=1).astype(np.int8)
    counts = np.bincount(labels, minlength=3)
    if int(np.min(counts)) < max(12, AUTO_MESH_MIN_CORRESPONDENCES // 4):
        return None
    return labels


def _target_driven_recenter(source_points, target_points, initial_transform):
    """Correct PCA centroid bias caused by gingiva and uneven IOS scan borders.

    PCA decides orientation.  This stage only translates that hypothesis using
    a trimmed median of target->IOS nearest-neighbour residuals.  The bounded
    steps make it safe for arbitrary-pose Plan A while greatly enlarging the
    basin of attraction of the first ICP stage.
    """
    total = np.asarray(initial_transform, dtype=np.float64).copy()
    source_sample, _unused = _limited_alignment_sample(
        np.asarray(source_points, dtype=np.float64), None, AUTO_GLOBAL_RECENTER_MAX_POINTS, 9511)
    target_sample, _unused = _limited_alignment_sample(
        np.asarray(target_points, dtype=np.float64), None, AUTO_GLOBAL_RECENTER_MAX_POINTS, 9521)
    moving = _apply_points(source_sample, total)
    target = target_sample
    for _ in range(AUTO_GLOBAL_RECENTER_ITERATIONS):
        index = _NearestIndex(moving)
        matched, _indices, distances = index.query(target)
        valid = np.flatnonzero(
            np.isfinite(distances) & (distances <= AUTO_GLOBAL_RECENTER_MAX_DISTANCE_MM)
        )
        if len(valid) < AUTO_MESH_MIN_CORRESPONDENCES:
            break
        ordered = valid[np.argsort(distances[valid])]
        keep = max(
            AUTO_MESH_MIN_CORRESPONDENCES,
            int(round(len(ordered) * AUTO_GLOBAL_RECENTER_KEEP_RATIO)),
        )
        selected = ordered[:min(len(ordered), keep)]
        delta = np.median(target[selected] - matched[selected], axis=0)
        if not np.isfinite(delta).all():
            break
        size = float(np.linalg.norm(delta))
        if size <= 0.02:
            break
        if size > AUTO_GLOBAL_RECENTER_MAX_STEP_MM:
            delta *= AUTO_GLOBAL_RECENTER_MAX_STEP_MM / size
        shift = np.eye(4, dtype=np.float64)
        shift[:3, 3] = delta
        moving = moving + delta[None, :]
        total = shift @ total
    return total


def _sector_fit_metrics(distances, zone_labels):
    """Return worst-sector coverage/RMS for arch-balanced candidate scoring."""
    if zone_labels is None:
        return None
    distances = np.asarray(distances, dtype=np.float64)
    labels = np.asarray(zone_labels, dtype=np.int8)
    if len(distances) != len(labels):
        return None
    coverages = []
    rms_values = []
    for zone in range(3):
        mask = labels == zone
        values = distances[mask]
        values = values[np.isfinite(values)]
        if len(values) < 8:
            return None
        coverages.append(
            100.0 * float(np.count_nonzero(values <= AUTO_GLOBAL_SECTOR_DISTANCE_MM)) / len(values)
        )
        ordered = np.sort(values)
        keep = max(6, int(round(len(ordered) * 0.82)))
        kept = ordered[:min(len(ordered), keep)]
        rms_values.append(float(np.sqrt(np.mean(np.square(kept)))))
    return {
        'coverage_min': float(min(coverages)),
        'coverage_median': float(np.median(coverages)),
        'rms_worst': float(max(rms_values)),
        'rms_median': float(np.median(rms_values)),
    }


def _candidate_anatomy_diagnostics(entry, source_points, validation_seeds, dental_landmarks):
    transform = entry[-1]
    moving = _apply_points(source_points, transform)
    zone_median, zone_worst, zone_supported = _distributed_zone_pose_residual(
        moving, validation_seeds)
    dental = _distributed_dental_landmark_residual(moving, dental_landmarks)
    dental_available = int(dental.get('count', 0)) >= 4
    zone_available = validation_seeds is not None
    zone_good = bool(
        (not zone_available)
        or (
            int(zone_supported) >= 3
            and float(zone_median) <= AUTO_GLOBAL_ZONE_MAX_MEDIAN_MM
            and float(zone_worst) <= AUTO_GLOBAL_ZONE_MAX_WORST_MM
        )
    )
    dental_good = bool(
        (not dental_available)
        or (
            int(dental.get('sectors', 0)) >= AUTO_GLOBAL_DENTAL_MIN_SECTORS
            and float(dental.get('support_ratio', 0.0)) >= AUTO_GLOBAL_DENTAL_MIN_SUPPORT_RATIO
            and float(dental.get('median_mm', float('inf'))) <= AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MEDIAN_MM
        )
    )
    return bool(zone_good and dental_good), {
        'zone_supported': int(zone_supported),
        'zone_median_mm': float(zone_median),
        'zone_worst_mm': float(zone_worst),
        'dental_landmarks': int(dental.get('count', 0)),
        'dental_landmarks_supported': int(dental.get('supported', 0)),
        'dental_landmark_support_ratio': float(dental.get('support_ratio', 0.0)),
        'dental_landmark_sectors': int(dental.get('sectors', 0)),
        'dental_landmark_median_mm': float(dental.get('median_mm', float('inf'))),
        'dental_landmark_p90_mm': float(dental.get('p90_mm', float('inf'))),
    }


def _anatomically_valid_candidate_pool(refined, source_points, validation_seeds, dental_landmarks):
    """Filter near-best mesh candidates through distributed dental anatomy."""
    if not refined:
        return [], {}
    if validation_seeds is None and dental_landmarks is None:
        return list(refined), {}
    raw_best_score = float(refined[0][0])
    pool = []
    diagnostics = {}
    for entry in refined:
        if float(entry[0]) > raw_best_score + AUTO_GLOBAL_ANATOMY_RECOVERY_WINDOW_MM:
            continue
        good, diag = _candidate_anatomy_diagnostics(
            entry, source_points, validation_seeds, dental_landmarks)
        diagnostics[int(entry[3])] = diag
        if good:
            pool.append(entry)
    pool.sort(key=lambda item: (item[0], item[1], item[3]))
    return pool, diagnostics

def _partial_overlap_candidate_score(transformed_source, transformed_normals, target_points, target_normals, target_zone_labels=None):
    """Score a dental target against a larger IOS surface.

    Target->source error dominates because the IOS legitimately contains gingiva
    and other surfaces absent from the segmented CBCT teeth.  A small reverse
    term still rejects tiny accidental overlaps.
    """
    transformed_source = np.asarray(transformed_source, dtype=np.float64)
    target_points = np.asarray(target_points, dtype=np.float64)
    if len(transformed_source) < AUTO_MESH_MIN_CORRESPONDENCES or len(target_points) < AUTO_MESH_MIN_CORRESPONDENCES:
        return float('inf'), 0.0, 90.0
    source_index = _NearestIndex(transformed_source)
    matched_source, source_indices, distances = source_index.query(target_points)
    finite = np.isfinite(distances)
    valid = np.flatnonzero(finite & (distances <= AUTO_MESH_SCORE_MAX_DISTANCE_MM))
    if len(valid) < AUTO_MESH_MIN_CORRESPONDENCES:
        valid = np.flatnonzero(finite)
    if len(valid) < AUTO_MESH_MIN_CORRESPONDENCES:
        return float('inf'), 0.0, 90.0
    ordered = valid[np.argsort(distances[valid])]
    keep = max(AUTO_MESH_MIN_CORRESPONDENCES, int(round(len(ordered) * 0.82)))
    selected = ordered[:min(len(ordered), keep)]
    d = distances[selected]
    rms = float(np.sqrt(np.mean(np.square(d))))
    p95 = float(np.percentile(d, 95.0))
    coverage = 100.0 * float(np.count_nonzero(finite & (distances <= AUTO_MESH_SCORE_DISTANCE_MM))) / max(len(distances), 1)

    normal_median = 90.0
    if transformed_normals is not None and target_normals is not None and len(selected):
        src_norm = np.asarray(transformed_normals, dtype=np.float64)[source_indices[selected]]
        tgt_norm = np.asarray(target_normals, dtype=np.float64)[selected]
        dots = np.clip(np.abs(np.einsum('ij,ij->i', src_norm, tgt_norm)), 0.0, 1.0)
        normal_median = float(np.degrees(np.arccos(np.median(dots))))

    # Reverse support is sampled and heavily trimmed: it is only a guard against
    # a tiny CBCT patch coinciding somewhere inside a much larger IOS.
    if len(transformed_source) > AUTO_MESH_EVALUATION_POINTS:
        chosen = np.linspace(0, len(transformed_source) - 1, AUTO_MESH_EVALUATION_POINTS).round().astype(np.int64)
        source_eval = transformed_source[chosen]
    else:
        source_eval = transformed_source
    target_index = _NearestIndex(target_points)
    _match, _idx, reverse = target_index.query(source_eval)
    reverse = reverse[np.isfinite(reverse)]
    if len(reverse):
        reverse = np.sort(reverse)
        reverse_keep = max(1, int(round(len(reverse) * 0.28)))
        reverse_rms = float(np.sqrt(np.mean(np.square(reverse[:reverse_keep]))))
    else:
        reverse_rms = AUTO_MESH_SCORE_MAX_DISTANCE_MM

    coverage_penalty = max(0.0, AUTO_GLOBAL_MIN_COVERAGE_PERCENT - coverage) * 0.035
    sector_penalty = 0.0
    sector = _sector_fit_metrics(distances, target_zone_labels)
    if sector is not None:
        sector_penalty += max(
            0.0,
            AUTO_GLOBAL_SECTOR_TARGET_COVERAGE_PERCENT - float(sector['coverage_min']),
        ) * AUTO_GLOBAL_SECTOR_PENALTY_PER_PERCENT
        sector_penalty += max(0.0, float(sector['rms_worst']) - rms) * AUTO_GLOBAL_SECTOR_RMS_PENALTY
    score = 0.60 * rms + 0.20 * p95 + 0.10 * reverse_rms + 0.008 * normal_median + coverage_penalty + sector_penalty
    return float(score), float(coverage), float(normal_median)


def _refine_partial_overlap_hypothesis(source_points, source_normals, target_points, target_normals, initial_transform, target_zone_labels=None):
    total = np.asarray(initial_transform, dtype=np.float64).copy()
    moving = _apply_points(source_points, total)
    moving_normals = None if source_normals is None else _apply_normals(source_normals, total)
    target_points = np.asarray(target_points, dtype=np.float64)
    target_normals = None if target_normals is None else np.asarray(target_normals, dtype=np.float64)

    for maximum_distance, keep_ratio, normal_angle, huber_delta in AUTO_GLOBAL_ICP_STAGES:
        source_index = _NearestIndex(moving)
        matched_source, source_indices, distances = source_index.query(target_points)
        valid = np.isfinite(distances) & (distances <= float(maximum_distance))
        if moving_normals is not None and target_normals is not None:
            dots = np.einsum('ij,ij->i', moving_normals[source_indices], target_normals)
            valid &= np.abs(dots) >= math.cos(math.radians(float(normal_angle)))
        selected = np.flatnonzero(valid)
        if len(selected) < AUTO_MESH_MIN_CORRESPONDENCES:
            break
        selected = selected[np.argsort(distances[selected])]
        keep_count = max(AUTO_MESH_MIN_CORRESPONDENCES, int(round(len(selected) * float(keep_ratio))))
        selected = selected[:min(len(selected), keep_count)]
        incremental = _weighted_best_fit_huber(
            matched_source[selected], target_points[selected], None,
            delta_mm=float(huber_delta), irls_iterations=3,
        )
        if (
            float(np.linalg.norm(incremental[:3, 3])) > AUTO_GLOBAL_MAX_INCREMENT_TRANSLATION_MM
            or _rotation_degrees(incremental) > AUTO_GLOBAL_MAX_INCREMENT_ROTATION_DEG
        ):
            break
        moving = _apply_points(moving, incremental)
        if moving_normals is not None:
            moving_normals = _apply_normals(moving_normals, incremental)
        total = incremental @ total

    # Tiny point-to-plane finish.  It is accepted only when the same global,
    # sector-balanced score does not worsen, so CBCT surface noise cannot pull a
    # good point-to-point solution away from the clinically supported pose.
    for _ in range(AUTO_GLOBAL_PLANE_ITERATIONS):
        if target_normals is None:
            break
        before_score, before_coverage, _before_normal = _partial_overlap_candidate_score(
            moving, moving_normals, target_points, target_normals, target_zone_labels)
        source_index = _NearestIndex(moving)
        matched_source, source_indices, distances = source_index.query(target_points)
        valid = np.isfinite(distances) & (distances <= AUTO_GLOBAL_PLANE_MAX_DISTANCE_MM)
        if moving_normals is not None:
            dots = np.einsum('ij,ij->i', moving_normals[source_indices], target_normals)
            valid &= np.abs(dots) >= math.cos(math.radians(AUTO_GLOBAL_PLANE_NORMAL_ANGLE_DEG))
        selected = np.flatnonzero(valid)
        if len(selected) < AUTO_MESH_MIN_CORRESPONDENCES:
            break
        selected = selected[np.argsort(distances[selected])]
        keep_count = max(
            AUTO_MESH_MIN_CORRESPONDENCES,
            int(round(len(selected) * AUTO_GLOBAL_PLANE_KEEP_RATIO)),
        )
        selected = selected[:min(len(selected), keep_count)]
        incremental = _point_to_plane_huber_transform(
            matched_source[selected],
            target_points[selected],
            target_normals[selected],
            huber_delta_mm=AUTO_GLOBAL_PLANE_HUBER_DELTA_MM,
            max_translation_mm=AUTO_GLOBAL_PLANE_MAX_TRANSLATION_MM,
            max_rotation_deg=AUTO_GLOBAL_PLANE_MAX_ROTATION_DEG,
        )
        candidate_points = _apply_points(moving, incremental)
        candidate_normals = None if moving_normals is None else _apply_normals(moving_normals, incremental)
        after_score, after_coverage, _after_normal = _partial_overlap_candidate_score(
            candidate_points, candidate_normals, target_points, target_normals, target_zone_labels)
        if not np.isfinite(after_score):
            break
        if after_score > before_score + 0.002 and after_coverage < before_coverage + 0.5:
            break
        moving = candidate_points
        moving_normals = candidate_normals
        total = incremental @ total

    score, coverage, normal_median = _partial_overlap_candidate_score(
        moving, moving_normals, target_points, target_normals, target_zone_labels)
    return total, score, coverage, normal_median



def _distributed_zone_pose_residual(transformed_source, validation_seeds):
    """Measure whether one candidate explains three separated dental zones."""
    if validation_seeds is None:
        return float('inf'), float('inf'), 0
    seeds = np.asarray(validation_seeds, dtype=np.float64)
    if seeds.ndim != 2 or seeds.shape[0] < 3 or seeds.shape[1] != 3:
        return float('inf'), float('inf'), 0
    moving = np.asarray(transformed_source, dtype=np.float64)
    if len(moving) < 3:
        return float('inf'), float('inf'), 0
    index = _NearestIndex(moving)
    _matched, _indices, distances = index.query(seeds[:3])
    distances = np.asarray(distances, dtype=np.float64)
    finite = distances[np.isfinite(distances)]
    if len(finite) < 3:
        return float('inf'), float('inf'), int(len(finite))
    median = float(np.median(finite))
    worst = float(np.max(finite))
    supported = int(np.count_nonzero(finite <= AUTO_GLOBAL_ZONE_MAX_WORST_MM))
    return median, worst, supported


def _distributed_dental_landmark_residual(transformed_source, dental_landmarks):
    """Evaluate every available crown landmark and its arch distribution.

    The IOS is not segmented, so each target landmark is compared with the
    closest aligned IOS surface.  A correct pose should support landmarks in
    anterior and both posterior sectors, not only one locally similar tooth.
    """
    if dental_landmarks is None:
        return {
            'count': 0, 'supported': 0, 'support_ratio': 0.0, 'sectors': 0,
            'median_mm': float('inf'), 'p90_mm': float('inf'),
        }
    points = np.asarray(dental_landmarks, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        return {
            'count': int(len(points)) if points.ndim else 0, 'supported': 0,
            'support_ratio': 0.0, 'sectors': 0, 'median_mm': float('inf'),
            'p90_mm': float('inf'),
        }
    moving = np.asarray(transformed_source, dtype=np.float64)
    if len(moving) < 3:
        return {
            'count': int(len(points)), 'supported': 0, 'support_ratio': 0.0,
            'sectors': 0, 'median_mm': float('inf'), 'p90_mm': float('inf'),
        }
    index = _NearestIndex(moving)
    _matched, _indices, distances = index.query(points)
    distances = np.asarray(distances, dtype=np.float64)
    finite = np.isfinite(distances)
    supported_mask = finite & (distances <= AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MM)
    supported = int(np.count_nonzero(supported_mask))
    finite_values = distances[finite]
    median = float(np.median(finite_values)) if len(finite_values) else float('inf')
    p90 = float(np.percentile(finite_values, 90.0)) if len(finite_values) else float('inf')

    # Split landmarks into thirds along the arch's dominant in-plane axis.
    # This does not need FDI labels and therefore also works with partial maps.
    centre = points.mean(axis=0)
    centred = points - centre
    covariance = centred.T @ centred / max(len(points) - 1, 1)
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    projection = centred @ axis
    order = np.argsort(projection)
    sectors = 0
    for group in np.array_split(order, 3):
        if len(group) and np.any(supported_mask[group]):
            sectors += 1
    return {
        'count': int(len(points)),
        'supported': int(supported),
        'support_ratio': float(supported / max(len(points), 1)),
        'sectors': int(sectors),
        'median_mm': float(median),
        'p90_mm': float(p90),
    }


def _resolve_global_pose_ambiguity(refined, source_points, validation_seeds, dental_landmarks=None):
    """Resolve near-symmetric arch poses with distributed dental evidence.

    Three separated validation zones remain the hard clinical minimum.  When
    more segmented teeth are available, every occlusal/incisal landmark also
    votes.  This breaks ties that look convincing around one molar but fail to
    explain the rest of the arch.
    """
    if len(refined) < 2:
        return refined[0], False, {}
    best_score = float(refined[0][0])
    window = [
        entry for entry in refined
        if float(entry[0]) <= best_score + AUTO_GLOBAL_ZONE_CANDIDATE_SCORE_WINDOW_MM
    ]
    if len(window) < 2:
        return refined[0], False, {}

    ranked = []
    for entry in window:
        transform = entry[-1]
        moving = _apply_points(source_points, transform)
        zone_median, zone_worst, zone_supported = _distributed_zone_pose_residual(
            moving, validation_seeds)
        dental = _distributed_dental_landmark_residual(moving, dental_landmarks)
        # Sort first by anatomical distribution, then amount of supported tooth
        # evidence, then local residuals and finally the generic mesh score.
        ranked.append((
            -int(dental.get('sectors', 0)),
            -float(dental.get('support_ratio', 0.0)),
            -int(zone_supported),
            float(dental.get('median_mm', float('inf'))),
            float(zone_median),
            float(zone_worst),
            float(entry[0]),
            entry,
            dental,
        ))
    ranked.sort(key=lambda item: item[:7])
    first = ranked[0]
    second = ranked[1]
    first_entry = first[7]
    first_dental = first[8]
    second_dental = second[8]
    first_zone_supported = -int(first[2])
    second_zone_supported = -int(second[2])
    zone_median_margin = float(second[4] - first[4])
    zone_worst_margin = float(second[5] - first[5])
    dental_median_margin = float(
        second_dental.get('median_mm', float('inf'))
        - first_dental.get('median_mm', float('inf'))
    )
    dental_available = int(first_dental.get('count', 0)) >= 4
    dental_good = bool(
        (not dental_available)
        or (
            int(first_dental.get('sectors', 0)) >= AUTO_GLOBAL_DENTAL_MIN_SECTORS
            and float(first_dental.get('support_ratio', 0.0)) >= AUTO_GLOBAL_DENTAL_MIN_SUPPORT_RATIO
            and float(first_dental.get('median_mm', float('inf'))) <= AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MEDIAN_MM
        )
    )
    dental_margin_good = bool(
        (not dental_available)
        or int(second_dental.get('sectors', 0)) < int(first_dental.get('sectors', 0))
        or float(second_dental.get('support_ratio', 0.0)) + 0.12 < float(first_dental.get('support_ratio', 0.0))
        or dental_median_margin >= AUTO_GLOBAL_DENTAL_MIN_MARGIN_MM
    )
    zone_good = bool(
        validation_seeds is None
        or (
            first_zone_supported >= 3
            and first[4] <= AUTO_GLOBAL_ZONE_MAX_MEDIAN_MM
            and first[5] <= AUTO_GLOBAL_ZONE_MAX_WORST_MM
        )
    )
    zone_margin_good = bool(
        validation_seeds is None
        or second_zone_supported < 3
        or zone_median_margin >= AUTO_GLOBAL_ZONE_MIN_MEDIAN_MARGIN_MM
        or zone_worst_margin >= AUTO_GLOBAL_ZONE_MIN_WORST_MARGIN_MM
    )
    resolved = bool(zone_good and dental_good and (zone_margin_good or dental_margin_good))
    diagnostics = {
        'zone_disambiguation_used': bool(resolved),
        'zone_supported': int(first_zone_supported),
        'zone_median_mm': float(first[4]),
        'zone_worst_mm': float(first[5]),
        'zone_median_margin_mm': float(zone_median_margin),
        'zone_worst_margin_mm': float(zone_worst_margin),
        'zone_candidates_considered': int(len(ranked)),
        'dental_landmarks': int(first_dental.get('count', 0)),
        'dental_landmarks_supported': int(first_dental.get('supported', 0)),
        'dental_landmark_support_ratio': float(first_dental.get('support_ratio', 0.0)),
        'dental_landmark_sectors': int(first_dental.get('sectors', 0)),
        'dental_landmark_median_mm': float(first_dental.get('median_mm', float('inf'))),
        'dental_landmark_p90_mm': float(first_dental.get('p90_mm', float('inf'))),
        'dental_landmark_median_margin_mm': float(dental_median_margin),
    }
    return (first_entry if resolved else refined[0]), resolved, diagnostics


def _automatic_global_registration(source_points, source_normals, target_points, target_normals, validation_seeds=None, dental_landmarks=None):
    """Plan A: arbitrary-pose rigid dental registration with anatomy guards.

    DSG 9.6.4 broadens the basin of attraction without becoming permissive:
    PCA hypotheses are target-recentered, scored across three arch sectors,
    refined against root-safe coronal crown shells, polished with a tiny
    point-to-plane pass, then filtered through distributed dental landmarks.
    """
    source_points, source_normals = _voxel_downsample(
        np.asarray(source_points, dtype=np.float64), source_normals,
        AUTO_MESH_PCA_VOXEL_MM, AUTO_MESH_MAX_SOURCE_POINTS, 9301,
    )
    target_points, target_normals = _voxel_downsample(
        np.asarray(target_points, dtype=np.float64), target_normals,
        AUTO_MESH_PCA_VOXEL_MM, AUTO_MESH_MAX_TARGET_POINTS, 9401,
    )
    if source_points is None or target_points is None or len(source_points) < AUTO_MESH_MIN_CORRESPONDENCES or len(target_points) < AUTO_MESH_MIN_CORRESPONDENCES:
        return np.eye(4, dtype=np.float64), {'accepted': False, 'reason': 'insufficient_geometry'}

    target_zone_labels = _target_zone_labels(target_points, validation_seeds)
    hypotheses = _proper_axis_hypotheses(source_points, target_points)
    coarse = []
    for index, hypothesis in enumerate(hypotheses):
        recentered = _target_driven_recenter(source_points, target_points, hypothesis)
        moving = _apply_points(source_points, recentered)
        moving_normals = None if source_normals is None else _apply_normals(source_normals, recentered)
        score, coverage, normal_median = _partial_overlap_candidate_score(
            moving, moving_normals, target_points, target_normals, target_zone_labels)
        coarse.append((score, -coverage, normal_median, index, recentered))
    coarse.sort(key=lambda item: (item[0], item[1], item[3]))

    refined = []
    for _score, _neg_cov, _normal, index, hypothesis in coarse[:AUTO_GLOBAL_REFINED_CANDIDATES]:
        transform, score, coverage, normal_median = _refine_partial_overlap_hypothesis(
            source_points, source_normals, target_points, target_normals, hypothesis,
            target_zone_labels=target_zone_labels,
        )
        if np.isfinite(score):
            refined.append((float(score), -float(coverage), float(normal_median), int(index), transform))
    if not refined:
        return np.eye(4, dtype=np.float64), {'accepted': False, 'reason': 'no_candidate'}
    refined.sort(key=lambda item: (item[0], item[1], item[3]))

    # A generic mesh-score winner can be a locally excellent but anatomically
    # wrong molar/anterior coincidence.  If distributed evidence is available,
    # discard near-best candidates that do not explain all three arch sectors.
    anatomy_pool, anatomy_by_index = _anatomically_valid_candidate_pool(
        refined, source_points, validation_seeds, dental_landmarks)
    candidate_pool = anatomy_pool if anatomy_pool else refined
    anatomy_filter_used = bool(anatomy_pool)
    best = candidate_pool[0]
    second = candidate_pool[1] if len(candidate_pool) > 1 else None
    best_score, neg_cov, best_normal, best_index, best_transform = best
    best_coverage = -neg_cov
    if second is None:
        absolute_margin = relative_margin = float('inf')
        coverage_margin = float('inf')
    else:
        absolute_margin = float(second[0] - best_score)
        relative_margin = absolute_margin / max(abs(float(best_score)), 0.05)
        coverage_margin = float(best_coverage - (-second[1]))
    ambiguity_safe = bool(
        second is None
        or absolute_margin >= AUTO_GLOBAL_MIN_ABSOLUTE_MARGIN_MM
        or relative_margin >= AUTO_GLOBAL_MIN_RELATIVE_MARGIN
        or coverage_margin >= 9.0
    )
    zone_diag = dict(anatomy_by_index.get(int(best_index), {}) or {})
    zone_diag.update({
        'anatomy_filter_used': bool(anatomy_filter_used),
        'anatomy_valid_candidates': int(len(anatomy_pool)),
        'raw_winner_index': int(refined[0][3]),
        'anatomy_promoted_candidate': bool(int(best_index) != int(refined[0][3])),
        'sector_balanced_scoring': bool(target_zone_labels is not None),
    })

    if not ambiguity_safe and validation_seeds is not None:
        # Resolve only among anatomy-valid candidates when possible.  Invalid
        # local overlaps must not force a correct distributed pose into Plan B.
        ambiguity_source = candidate_pool
        resolved_best, zone_resolved, resolved_diag = _resolve_global_pose_ambiguity(
            ambiguity_source, source_points, validation_seeds, dental_landmarks=dental_landmarks)
        zone_diag.update(resolved_diag)
        if zone_resolved:
            best = resolved_best
            best_score, neg_cov, best_normal, best_index, best_transform = best
            best_coverage = -neg_cov
            competitors = [entry for entry in ambiguity_source if entry is not best]
            second = competitors[0] if competitors else None
            if second is None:
                absolute_margin = relative_margin = coverage_margin = float('inf')
            else:
                absolute_margin = float(second[0] - best_score)
                relative_margin = absolute_margin / max(abs(float(best_score)), 0.05)
                coverage_margin = float(best_coverage - (-second[1]))
            ambiguity_safe = True

    dental_diag = _distributed_dental_landmark_residual(
        _apply_points(source_points, best_transform), dental_landmarks)
    dental_available = int(dental_diag.get('count', 0)) >= 4
    dental_gate = bool(
        (not dental_available)
        or (
            int(dental_diag.get('sectors', 0)) >= AUTO_GLOBAL_DENTAL_MIN_SECTORS
            and float(dental_diag.get('support_ratio', 0.0)) >= AUTO_GLOBAL_DENTAL_MIN_SUPPORT_RATIO
            and float(dental_diag.get('median_mm', float('inf'))) <= AUTO_GLOBAL_DENTAL_LANDMARK_MAX_MEDIAN_MM
        )
    )
    zone_diag.update({
        'dental_landmarks': int(dental_diag.get('count', 0)),
        'dental_landmarks_supported': int(dental_diag.get('supported', 0)),
        'dental_landmark_support_ratio': float(dental_diag.get('support_ratio', 0.0)),
        'dental_landmark_sectors': int(dental_diag.get('sectors', 0)),
        'dental_landmark_median_mm': float(dental_diag.get('median_mm', float('inf'))),
        'dental_landmark_p90_mm': float(dental_diag.get('p90_mm', float('inf'))),
    })

    sector_diag = None
    if target_zone_labels is not None:
        transformed = _apply_points(source_points, best_transform)
        source_index = _NearestIndex(transformed)
        _matched, _indices, distances = source_index.query(target_points)
        sector_diag = _sector_fit_metrics(distances, target_zone_labels)
        if sector_diag is not None:
            zone_diag.update({
                'sector_min_coverage_percent': float(sector_diag['coverage_min']),
                'sector_median_coverage_percent': float(sector_diag['coverage_median']),
                'sector_worst_rms_mm': float(sector_diag['rms_worst']),
                'sector_median_rms_mm': float(sector_diag['rms_median']),
            })

    accepted = bool(
        np.isfinite(best_score)
        and best_score <= AUTO_GLOBAL_MAX_SCORE_MM
        and best_coverage >= AUTO_GLOBAL_MIN_COVERAGE_PERCENT
        and best_normal <= AUTO_GLOBAL_MAX_NORMAL_MEDIAN_DEG
        and ambiguity_safe
        and dental_gate
        and float(np.linalg.det(best_transform[:3, :3])) > 0.0
    )
    if not accepted:
        return np.eye(4, dtype=np.float64), {
            'accepted': False,
            'reason': 'ambiguous' if not ambiguity_safe else 'low_confidence',
            'score': float(best_score), 'coverage': float(best_coverage),
            'normal_median': float(best_normal), 'relative_margin': float(relative_margin),
            'absolute_margin': float(absolute_margin), 'coverage_margin': float(coverage_margin),
            'hypotheses_tested': int(len(hypotheses)), 'refined_candidates': int(len(refined)),
            **zone_diag,
        }
    return best_transform, {
        'accepted': True, 'reason': 'ok', 'score': float(best_score),
        'coverage': float(best_coverage), 'normal_median': float(best_normal),
        'relative_margin': float(relative_margin), 'absolute_margin': float(absolute_margin),
        'coverage_margin': float(coverage_margin), 'hypotheses_tested': int(len(hypotheses)),
        'refined_candidates': int(len(refined)), 'winner_index': int(best_index),
        **zone_diag,
        'translation_mm': float(np.linalg.norm(best_transform[:3, 3])),
        'rotation_deg': float(_rotation_degrees(best_transform)),
    }


def _transform_mesh_graph_in_place(graph, transform):
    if graph is None:
        return
    graph.points = _apply_points(graph.points, transform)
    graph.normals = _apply_normals(graph.normals, transform)
    graph.spatial_index = _SciPyKDTree(graph.points) if _SciPyKDTree is not None else None


def _reanchor_source_zones_to_target(source_graph, target_seeds):
    """Project each fixed-reference zone onto the already coarsely aligned IOS."""
    anchors = []
    distances = []
    for target_seed in np.asarray(target_seeds, dtype=np.float64):
        index = source_graph.nearest_vertex(target_seed)
        point = source_graph.points[index].copy()
        distance = float(np.linalg.norm(point - target_seed))
        anchors.append(point)
        distances.append(distance)
    accepted = [distance <= AUTO_MESH_REANCHOR_MAX_DISTANCE_MM for distance in distances]
    return np.asarray(anchors, dtype=np.float64), distances, accepted


def _weighted_best_fit(source: np.ndarray, target: np.ndarray, weights: np.ndarray | None) -> np.ndarray:
    """Weighted Kabsch rigid transform with bounded, finite weights."""
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if len(source) < 3 or len(source) != len(target):
        return np.eye(4, dtype=np.float64)
    if weights is None:
        return _best_fit(source, target)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    if len(weights) != len(source):
        return _best_fit(source, target)
    valid = np.isfinite(source).all(axis=1) & np.isfinite(target).all(axis=1) & np.isfinite(weights)
    valid &= weights > 1.0e-8
    if np.count_nonzero(valid) < 3:
        return _best_fit(source, target)
    source = source[valid]
    target = target[valid]
    weights = np.clip(weights[valid], 1.0e-6, None)
    weights /= max(float(weights.sum()), 1.0e-12)
    source_center = np.sum(source * weights[:, None], axis=0)
    target_center = np.sum(target * weights[:, None], axis=0)
    source_centered = source - source_center
    target_centered = target - target_center
    covariance = (source_centered * weights[:, None]).T @ target_centered
    try:
        u, _singular, vt = np.linalg.svd(covariance)
    except np.linalg.LinAlgError:
        return _best_fit(source, target)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = target_center - rotation @ source_center
    return transform


def _weighted_best_fit_huber(
    source: np.ndarray,
    target: np.ndarray,
    base_weights: np.ndarray | None = None,
    *,
    delta_mm: float = 0.30,
    irls_iterations: int = 3,
) -> np.ndarray:
    """Rigid weighted Kabsch solved with Huber IRLS.

    The transform is always rotation + translation.  Reflection is explicitly
    rejected by forcing det(R)=+1; no scale or deformation term exists.
    """
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if len(source) < 3 or len(source) != len(target):
        return np.eye(4, dtype=np.float64)
    valid = np.isfinite(source).all(axis=1) & np.isfinite(target).all(axis=1)
    if base_weights is None:
        base = np.ones(len(source), dtype=np.float64)
    else:
        candidate = np.asarray(base_weights, dtype=np.float64).reshape(-1)
        if len(candidate) != len(source):
            base = np.ones(len(source), dtype=np.float64)
        else:
            valid &= np.isfinite(candidate) & (candidate > 1.0e-8)
            base = np.clip(candidate, 1.0e-6, None)
    if np.count_nonzero(valid) < 3:
        return np.eye(4, dtype=np.float64)
    source = source[valid]
    target = target[valid]
    base = base[valid]
    base /= max(float(np.mean(base)), 1.0e-12)
    robust = np.ones(len(source), dtype=np.float64)
    transform = np.eye(4, dtype=np.float64)
    delta = max(float(delta_mm), 1.0e-4)
    for _ in range(max(1, int(irls_iterations))):
        transform = _weighted_best_fit(source, target, base * robust)
        moved = _apply_points(source, transform)
        errors = np.linalg.norm(moved - target, axis=1)
        robust = np.ones(len(errors), dtype=np.float64)
        outside = errors > delta
        robust[outside] = delta / np.maximum(errors[outside], 1.0e-12)
        robust = np.clip(robust, 0.05, 1.0)
    return transform


def _surface_patch_quality(points: np.ndarray, normals: np.ndarray | None, seed: np.ndarray) -> tuple[float, dict]:
    """Return a conservative confidence score for one clicked surface patch.

    The score rewards a broad two-dimensional surface and coherent normals. It
    does not reward raw vertex density, so a dense noisy CBCT patch cannot win
    simply by containing more triangles.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < PATCH_MIN_VERTICES:
        return 0.0, {"coherence": 0.0, "spread": 0.0, "radius": 0.0}
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    if len(points) < PATCH_MIN_VERTICES:
        return 0.0, {"coherence": 0.0, "spread": 0.0, "radius": 0.0}

    centred = points - points.mean(axis=0)
    covariance = centred.T @ centred / max(len(points) - 1, 1)
    try:
        eigenvalues = np.sort(np.maximum(np.linalg.eigvalsh(covariance), 0.0))[::-1]
    except np.linalg.LinAlgError:
        eigenvalues = np.zeros(3, dtype=np.float64)
    major = math.sqrt(float(eigenvalues[0])) if len(eigenvalues) else 0.0
    secondary = math.sqrt(float(eigenvalues[1])) if len(eigenvalues) > 1 else 0.0
    spread_score = min(1.0, max(0.0, secondary / 2.25))
    radius = float(np.percentile(np.linalg.norm(points - np.asarray(seed, dtype=np.float64), axis=1), 80.0))
    radius_score = min(1.0, max(0.0, radius / 4.0))

    coherence = 0.5
    if normals is not None:
        normals = np.asarray(normals, dtype=np.float64)
        normals = normals[finite]
        lengths = np.linalg.norm(normals, axis=1)
        valid_normals = np.isfinite(normals).all(axis=1) & (lengths > 1.0e-8)
        normals = normals[valid_normals]
        if len(normals) >= 6:
            normals = normals / np.linalg.norm(normals, axis=1, keepdims=True)
            reference = normals[0]
            signs = np.where((normals @ reference) < 0.0, -1.0, 1.0)
            aligned = normals * signs[:, None]
            coherence = float(np.linalg.norm(aligned.mean(axis=0)))
            coherence = min(1.0, max(0.0, coherence))

    confidence = 0.50 * coherence + 0.35 * spread_score + 0.15 * radius_score
    # Avoid zeroing a clinically useful but nearly planar vestibular wall.
    confidence = min(1.0, max(0.0, confidence))
    return confidence, {
        "coherence": float(coherence),
        "spread": float(spread_score),
        "radius": float(radius),
        "major": float(major),
        "secondary": float(secondary),
    }


def _bounded_surface_sample(
    points: np.ndarray,
    normals: np.ndarray | None,
    *,
    voxel_mm: float,
    candidate_limit: int,
    max_points: int,
    seed: int,
):
    """Create a deterministic bounded sample without voxelising millions of points."""
    if points is None or len(points) == 0:
        return None, None
    points = np.asarray(points, dtype=np.float64)
    normals_array = None if normals is None else np.asarray(normals, dtype=np.float64)
    count = len(points)
    if count > candidate_limit:
        # Evenly distributed deterministic candidates with a seed-dependent
        # phase; this avoids allocating a multi-million-element choice array.
        step = count / float(candidate_limit)
        phase = int(seed) % max(int(step), 1)
        indices = np.floor(phase + np.arange(candidate_limit, dtype=np.float64) * step).astype(np.int64)
        indices = np.clip(indices, 0, count - 1)
        points = points[indices]
        if normals_array is not None:
            normals_array = normals_array[indices]
    return _voxel_downsample(points, normals_array, voxel_mm, max_points, seed)


def _rotation_matrix_from_vector(rotation_vector: np.ndarray) -> np.ndarray:
    """Rodrigues rotation from a small axis-angle vector in radians."""
    vector = np.asarray(rotation_vector, dtype=np.float64).reshape(3)
    angle = float(np.linalg.norm(vector))
    if angle <= 1.0e-12:
        return np.eye(3, dtype=np.float64)
    axis = vector / angle
    x, y, z = axis
    skew = np.array(((0.0, -z, y), (z, 0.0, -x), (-y, x, 0.0)), dtype=np.float64)
    return np.eye(3, dtype=np.float64) + math.sin(angle) * skew + (1.0 - math.cos(angle)) * (skew @ skew)


def _point_to_plane_huber_transform(
    source: np.ndarray,
    target: np.ndarray,
    target_normals: np.ndarray,
    *,
    base_weights: np.ndarray | None = None,
    huber_delta_mm: float = ROBUST_HUBER_DELTA_MM,
    max_translation_mm: float = ROBUST_MAX_TRANSLATION_MM,
    max_rotation_deg: float = ROBUST_MAX_ROTATION_DEG,
) -> np.ndarray:
    """Return one small robust point-to-plane rigid increment.

    The system is centred around the current patch centroid. Three short IRLS
    steps use a Huber kernel. The increment is capped so the hidden refinement
    cannot undo a good landmark + ICP solution.
    """
    if source is None or target is None or target_normals is None or len(source) < 6:
        return np.eye(4, dtype=np.float64)
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    normals = np.asarray(target_normals, dtype=np.float64)
    normal_length = np.linalg.norm(normals, axis=1, keepdims=True)
    valid = np.isfinite(source).all(axis=1) & np.isfinite(target).all(axis=1) & np.isfinite(normals).all(axis=1)
    valid &= normal_length[:, 0] > 1.0e-8
    if np.count_nonzero(valid) < 6:
        return np.eye(4, dtype=np.float64)
    source = source[valid]
    target = target[valid]
    normals = normals[valid] / normal_length[valid]
    if base_weights is None:
        base = np.ones(len(source), dtype=np.float64)
    else:
        base_array = np.asarray(base_weights, dtype=np.float64).reshape(-1)
        if len(base_array) != len(valid):
            base = np.ones(len(source), dtype=np.float64)
        else:
            base = np.clip(base_array[valid], 1.0e-4, None)
            base /= max(float(np.mean(base)), 1.0e-12)

    pivot = np.average(source, axis=0, weights=base)
    centred = source - pivot
    matrix = np.concatenate((np.cross(centred, normals), normals), axis=1)
    right = np.sum(normals * (target - source), axis=1)
    if np.linalg.matrix_rank(matrix) < 6:
        return np.eye(4, dtype=np.float64)

    solution = np.zeros(6, dtype=np.float64)
    delta = max(float(huber_delta_mm), 1.0e-4)
    for _ in range(3):
        residual = matrix @ solution - right
        absolute = np.abs(residual)
        robust_weights = np.ones_like(absolute)
        outside = absolute > delta
        robust_weights[outside] = delta / np.maximum(absolute[outside], 1.0e-12)
        weights = robust_weights * base
        sqrt_weights = np.sqrt(np.clip(weights, 1.0e-6, None))
        weighted_matrix = matrix * sqrt_weights[:, None]
        weighted_right = right * sqrt_weights
        try:
            solution, _residuals, rank, _singular = np.linalg.lstsq(weighted_matrix, weighted_right, rcond=1.0e-7)
        except np.linalg.LinAlgError:
            return np.eye(4, dtype=np.float64)
        if rank < 6 or not np.isfinite(solution).all():
            return np.eye(4, dtype=np.float64)

    rotation_vector = solution[:3]
    translation_local = solution[3:]
    rotation_limit = math.radians(max(float(max_rotation_deg), 0.0))
    rotation_size = float(np.linalg.norm(rotation_vector))
    if rotation_limit > 0.0 and rotation_size > rotation_limit:
        rotation_vector *= rotation_limit / rotation_size
    translation_limit = max(float(max_translation_mm), 0.0)
    translation_size = float(np.linalg.norm(translation_local))
    if translation_limit > 0.0 and translation_size > translation_limit:
        translation_local *= translation_limit / translation_size

    rotation = _rotation_matrix_from_vector(rotation_vector)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = pivot + translation_local - rotation @ pivot
    return transform


def _reciprocal_correspondences(
    source_points: np.ndarray,
    source_normals: np.ndarray | None,
    target_points: np.ndarray,
    target_normals: np.ndarray | None,
    *,
    max_distance_mm: float,
    normal_angle_deg: float,
    reciprocal_tolerance_mm: float,
    keep_ratio: float,
):
    """Find epsilon-reciprocal common-surface correspondences."""
    if source_points is None or target_points is None:
        return None
    if len(source_points) < PATCH_MIN_CORRESPONDENCES or len(target_points) < PATCH_MIN_CORRESPONDENCES:
        return None
    target_index = _NearestIndex(target_points)
    matched, target_indices, distances = target_index.query(source_points)
    source_index = _NearestIndex(source_points)
    back_matched, _back_indices, _back_distances = source_index.query(target_points)
    reciprocal_distance = np.linalg.norm(source_points - back_matched[target_indices], axis=1)

    valid = np.isfinite(distances) & (distances <= float(max_distance_mm))
    valid &= np.isfinite(reciprocal_distance) & (reciprocal_distance <= float(reciprocal_tolerance_mm))
    if source_normals is not None and target_normals is not None and normal_angle_deg < 90.0:
        dots = np.clip(
            np.abs(np.sum(source_normals * target_normals[target_indices], axis=1)),
            0.0,
            1.0,
        )
        valid &= np.degrees(np.arccos(dots)) <= float(normal_angle_deg)

    selected = _trimmed_correspondences(distances, valid, float(keep_ratio))
    if selected is None or len(selected) < PATCH_MIN_CORRESPONDENCES:
        return None
    return matched, target_indices, distances, selected


