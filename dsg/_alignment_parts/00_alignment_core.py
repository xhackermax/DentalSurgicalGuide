import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
bl_info = {
    "name": "DSG Â· Alignment Module",
    "author": "Max Tiburcio",
    "version": (2, 16, 0),
    "blender": (5, 2, 0),
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

# Automatic area limits. These reproduce the useful idea behind Edit Mode >
# Select More (+): the clicked landmark is only a seed, then the surrounding
# connected dental surface is expanded before ICP. The Euclidean cap prevents
# the expansion from jumping to an antagonist or an opposite thin wall.
PATCH_CANDIDATE_LIMIT = 36000
PATCH_MIN_CORRESPONDENCES = 14
FALLBACK_PATCH_SAMPLE_LIMIT = 1100

MIN_LANDMARK_SPAN_MM = 10.0
MIN_NORMALIZED_TRIANGLE_AREA = 0.0025
MAX_PAIR_DISTANCE_RELATIVE_ERROR = 0.45
MAX_PAIR_DISTANCE_ABSOLUTE_ERROR_MM = 8.0
MAX_ACCEPTABLE_ALIGNMENT_ERROR_MM = 0.50

# Conservative hidden refinement. The three proven ICP scales remain unchanged.
# This pass only uses reciprocal correspondences inside the three areas selected
# by the user, solves a robust point-to-plane step and rejects any update that
# makes the common-surface error worse.
ROBUST_HUBER_DELTA_MM = 0.25
ROBUST_MAX_TRANSLATION_MM = 0.20
ROBUST_MAX_ROTATION_DEG = 0.30


# The user marks three broad, easy-to-recognise dental zones. The labels are
# deliberately clinical; Kabsch/ICP details remain completely hidden.
ROBUST_ZONE_KEYS = ("ANTERIOR", "POSTERIOR_RIGHT", "POSTERIOR_LEFT")
ROBUST_ZONE_LABELS_EN = ("Anterior facial", "Right posterior facial", "Left posterior facial")
ROBUST_ZONE_LABELS_ES = ("Anterior vestibular", "Posterior derecha", "Posterior izquierda")

# Pair-confidence weighting. A click is only a seed: the surrounding connected
# patch supplies the actual geometric information and determines its weight.

# Conservative global reciprocal refinement. It samples the whole available
# surfaces, but accepts only reciprocal, close and normal-compatible matches.
# Correspondences are balanced across the three clinical sectors, so a single
# dense molar or blurred occlusal region cannot dominate the solution.

# Automatic whole-mesh rescue.  The six clicks remain useful clinical hints,
# but they no longer have to place both meshes close enough for local ICP by
# themselves.  DSG evaluates the current landmark pose plus proper PCA axis
# hypotheses, refines only the best candidates, and accepts a correction only
# when reciprocal surface agreement improves materially.
# max distance, retained ratio, normal angle, Huber delta
# The whole-mesh pass runs *after* the clinician has paired three dental
# zones.  A large PCA hypothesis can otherwise exchange the two ends of a
# nearly symmetric arch (an apparently excellent RMS fit, but upside down / in
# reverse clinically).  It is a local refinement, never a second coarse
# registration, so it must remain close to the landmark pose.

# Plan A automatic registration.  DSG 9.6.4 adds a connected coronal crown
# shell, target-driven PCA recentering, sector-balanced scoring and a guarded
# point-to-plane finish.  Unlike the conservative whole-mesh rescue
# above, this stage starts from an arbitrary IOS pose.  It uses proper PCA
# hypotheses followed by target-driven trimmed ICP so extra gingiva in the IOS
# does not dominate the dental CBCT target.  Ambiguous near-symmetric solutions
# are rejected and sent to the three-zone Plan B instead of being guessed.
# When two whole-arch poses are globally similar, use three automatically
# distributed dental zones as a tie-breaker before falling back to manual clicks.
# This retains the safety logic of the 3-zone protocol but automates it.
# Additional tooth-landmark evidence.  The three clinical sectors remain the
# safety minimum, but Plan A now evaluates every available occlusal/incisal
# landmark so a locally convincing molar match cannot win against the whole arch.
# Coarse target-driven recentering compensates for IOS gingiva/scan-border bias
# before ICP.  Translation only: PCA still owns the coarse orientation.
# Three automatic dental sectors must all participate in the score.  This makes
# a locally excellent molar overlap lose against a slightly noisier whole-arch
# pose that explains anterior + both posterior regions.
# Final point-to-plane polishing is intentionally tiny and score guarded.
# If the raw mesh-score winner fails distributed anatomy, Plan A may promote a
# nearby candidate that passes all three sectors and the available crown
# landmarks.  The window is deliberately bounded so anatomy cannot rescue a
# geometrically poor pose.

# Final hidden validation gates. The familiar 0.50 mm robust mean remains the
# principal gate, while these checks prevent a good average from hiding one bad
# sector or poorly oriented correspondence set.
MAX_ACCEPTABLE_P95_MM = 0.95
MIN_ACCEPTABLE_PATCH_COVERAGE_PERCENT = 8.0


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
    """Give the IOS its fixed clinical colour; marking stays opaque."""
    if obj is None or getattr(obj, "type", "") != "MESH" or getattr(obj, "data", None) is None:
        return False
    from .blender.clinical_materials import apply
    apply(obj, 'IOS', thin=bool(obj.get('DSG_alignment_thin_review', False)))
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
            from . import cbct_dental_module
            if cbct_dental_module.VISUAL_SMOOTHING_CHOICE_KEY in context.scene:
                cbct_dental_module.set_dentition_alignment_visual_smoothing(
                    context, bool(context.scene[cbct_dental_module.VISUAL_SMOOTHING_CHOICE_KEY])
                )
            return [], [], []
        from . import cbct_dental_module
        teeth = list(cbct_dental_module.set_dentition_alignment_visual_smoothing(
            context, bool(context.scene.get(cbct_dental_module.VISUAL_SMOOTHING_CHOICE_KEY, True))
        ))
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
        cbct_dental_module.set_dentition_alignment_visual_smoothing(
            context, bool(context.scene.get(cbct_dental_module.VISUAL_SMOOTHING_CHOICE_KEY, False))
        )
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
        source['DSG_alignment_thin_review'] = True
        ensure_ios_gray_material(source)
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
                space.shading.type = 'MATERIAL'
                space.shading.color_type = 'OBJECT'
                space.shading.light = 'STUDIO'
                if hasattr(space.shading, 'show_xray'):
                    space.shading.show_xray = False
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
        return False, _t(props, "Select any fixed reference mesh and the moving scan.", "Selecciona cualquier malla de referencia fija y el escaneado mÃ³vil.")
    if source is None or source == target:
        props.icp_target_obj = target
        return False, _t(props, "Select the moving scan and press Detect models.", "Selecciona el escaneado mÃ³vil y pulsa Detectar modelos.")

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
        return False, _t(props, "One mesh has no valid geometry.", "Una de las mallas no contiene geometrÃ­a vÃ¡lida.")
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
                _DSG_LOG.debug("suppressed exception", exc_info=True)
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


def _registration_mesh_source(obj, depsgraph):
    """A DSG display modifier must never change the clinical ICP reference."""
    from . import cbct_dental_module
    original = obj.get('DSG_post_smooth_original_mesh')
    if isinstance(original, bpy.types.Mesh):
        return obj, original, False
    if obj.modifiers.get(cbct_dental_module.ALIGNMENT_VISUAL_SMOOTH_MODIFIER) is not None:
        return obj, obj.data, False
    evaluated = obj.evaluated_get(depsgraph)
    return evaluated, evaluated.to_mesh(), True


def _mesh_graph_from_objects(objects) -> _MeshGraph | None:
    """Concatenate several mesh objects into one in-memory world-space graph."""
    point_blocks, normal_blocks, edge_blocks = [], [], []
    offset = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj is None or obj.type != 'MESH':
            continue
        evaluated, mesh, temporary = _registration_mesh_source(obj, depsgraph)
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
            if temporary:
                evaluated.to_mesh_clear()
    if not point_blocks:
        return None
    points = np.concatenate(point_blocks, axis=0)
    normals = np.concatenate(normal_blocks, axis=0)
    edges = np.concatenate(edge_blocks, axis=0) if edge_blocks else np.empty((0, 2), dtype=np.int32)
    return _MeshGraph(points, normals, edges)

















def _extract_world_mesh_graph(obj) -> _MeshGraph | None:
    """Read evaluated vertices, normals and edge topology with foreach_get."""
    # Immediate review composites contain bone.  Registration must still use
    # only the segmented teeth that remain after virtual extraction selection.
    if obj is not None and bool(obj.get("DSG_immediate_arch_composite", False)):
        dental_graph = _mesh_graph_from_objects(_immediate_alignment_teeth(bpy.context, obj))
        if dental_graph is not None:
            return dental_graph
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated, mesh, temporary = _registration_mesh_source(obj, depsgraph)
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
        if temporary:
            evaluated.to_mesh_clear()






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


