# Reuse the package metadata instead of maintaining a second add-on version.
# Blender only installs dsg/__init__.py as the add-on; guide_module is a child.
from .version import DSG_VERSION, DSG_VERSION_STR

# Module metadata derived from version.py (SSOT). Not imported from the
# package: Blender removes ``bl_info`` from packages installed as Extensions.
bl_info = {
    "name": "DSG Dental Surgical Guide",
    "version": DSG_VERSION,
    "description": "Guide design module (implants, sleeves, frame, irrigation, export)",
}

# ─────────────────────────────────────────────────────────────────────────────
# Dental Surgical Guide v8.0.12 — corrected two-plane MPR pivot and duplicate IOS import
#
# Núcleo: modelo retentivo/eje → implantes → contorno → estructura → cilindros → irrigación
#         → refuerzos Catmull-Rom → fresado → corte final → STL.
#
# · Boolean UNION/DIFFERENCE EXACT para operaciones clínicas críticas.
# · Irrigation basada en eje interno: parámetros persistentes por conducto y corte transaccional por componentes.
# · Preflight manifold, diagnóstico y rollback transaccional.
# · Preview independiente de sleeves e irrigación antes de modificar la guía.
# · Paso 8 visible: cadenas segmentadas de 2 o más puntos; cada punto intermedio es final y origen. Cada contacto incorpora una transición volumétrica Coons de cuatro bordes hacia el frame o refuerzo previo, Ø2,5 mm.
# · Panel sin botones vacíos, iconos incompatibles ni escrituras sobre Scene/Object durante draw().
# · Protección axial: cilindro coaxial del diámetro del implante limpia irrigación y otros shells dentro del sleeve.
# · DSG_ContourCurve es temporal y se elimina, junto con sus datos, después de generar correctamente DSG_Frame.
# · Drill transaccional por componentes: nunca aplica DIFFERENCE sobre una guía multishell completa.
# · El visor radiológico se delega por completo en DICOM Wizard.
# ─────────────────────────────────────────────────────────────────────────────

import bpy
import bpy.utils.previews

from . import lifecycle
from . import core
from . import icon_manager
from . import ui_style
from . import glyph_library
from . import dental_assets
from . import frame_surface_corridor
import bmesh
import gpu
import math
import json
import time
import base64
import zlib
import struct
import os
import sys
import logging
import tempfile
import random
import heapq
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from bpy.props import (
    PointerProperty, FloatProperty, BoolProperty,
    CollectionProperty, FloatVectorProperty, IntProperty, StringProperty, EnumProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ExportHelper
from gpu_extras.batch import batch_for_shader

_DSG_LOG = logging.getLogger("dsg.guide")

from .guide_assets import load_text as _load_guide_asset


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

AXIS_EMPTY_NAME = "DSG_Axis"
IMPLANT_AXIS_EMPTY_NAME = "DSG_ImplantAxis"
BLOCKOUT_NAME   = "DSG_Blockout"
BLOCKOUT_CANDIDATE_NAME = "DSG_Blockout_Candidate"
BLOCKOUT_VISUAL_NAME = "DSG_BlockoutZoneVisual"
BLOCKOUT_VISUAL_CHANGE_EPS_MM = 0.005
BLOCKOUT_VISUAL_SURFACE_OFFSET_MM = 0.015
BLOCKOUT_RAY_OFFSET_MM = 0.002
BLOCKOUT_MIN_HIT_DEFAULT_MM = 0.01
BLOCKOUT_MAX_HIT_DEFAULT_MM = 25.0
BLOCKOUT_ENGINE_ID = "V8_VIEW_PARALLEL_RAYCAST"
# The seating check is deliberately an *algorithmic* quality check, rather than
# a claim of clinical accuracy.  It verifies that the view-parallel envelope is
# free of material axial locks beyond the requested relief, that it remained an
# axial construction, and that the source/candidate topology is still matched.
# Printing, sleeve tolerances, scan quality and the clinical trial fit remain
# independent responsibilities of the clinician.
BLOCKOUT_SEATING_SAMPLE_LIMIT = 60000
BLOCKOUT_SEATING_RESIDUAL_TOLERANCE_MM = 0.060
BLOCKOUT_SEATING_MAX_RESIDUAL_EXTRA_MM = 0.120
BLOCKOUT_SEATING_LATERAL_LIMIT_MM = 0.035
CLOSED_MODEL_NAME = "DSG_Model_Closed"
HOLE_REPAIRED_MODEL_NAME = "DSG_Model_HolesClosed"
OPEN_MODEL_BACKUP_FLAG = "DSG_open_model_backup"
SCAN_HOLES_PROCESSED_FLAG = "DSG_scan_holes_processed"
CLOSED_MODEL_ACCEPTED_FLAG = "DSG_closed_model_accepted"
EXTERNAL_CLOSED_MODEL_FLAG = "DSG_external_closed_model"
BASE_PERIMETER_CURVE_NAME = "DSG_BasePerimeter"
BASE_PERIMETER_MIN_POINTS = 8
BASE_PERIMETER_MIN_SPACING_MM = 0.35
BASE_PERIMETER_CURVE_RADIUS_MM = 0.18
BASE_PERIMETER_MANUAL_MARGIN_MM = 0.20
AUTO_BASE_MIN_DEPTH_MM = 3.0
AUTO_BASE_MAX_DEPTH_MM = 8.0
AUTO_BASE_DEPTH_FRACTION = 0.075
AUTO_BASE_SMALL_HOLE_MAX_PERIMETER_MM = 10.0
AUTO_SCAN_HOLE_MAX_PERIMETER_MM = 25.0
AUTO_SCAN_HOLE_MAX_BASE_RATIO = 0.30
AUTO_SCAN_HOLE_MIN_PERIMETER_MM = 0.25
AUTO_BASE_MIN_MAIN_LOOP_PERIMETER_MM = 15.0
# Dental-base orientation analysis. Raw PCA is only an initialization: DSG
# evaluates the open rim, surface sections and a small cone of nearby axes before
# accepting a basal direction. Values are intentionally conservative and remain
# independent of viewport zoom/pan.
AUTO_BASE_ANALYSIS_FACE_LIMIT = 18000
AUTO_BASE_DIRECTION_SEARCH_DEG = 10.0
AUTO_BASE_DIRECTION_COARSE_STEP_DEG = 5.0
AUTO_BASE_DIRECTION_FINE_STEP_DEG = 1.5
AUTO_BASE_BASAL_BAND_FRACTION = 0.22
AUTO_BASE_MIN_BASAL_BAND_MM = 2.0
AUTO_BASE_MAX_BASAL_BAND_MM = 6.0
AUTO_BASE_FOOTPRINT_MARGIN_MM = 0.55
AUTO_BASE_LOW_CONFIDENCE = 0.42
_MODEL_TOPOLOGY_CACHE = {}
# Workflow closure is determined by the clinically relevant open-boundary count.
# Zero boundary edges means the shell is closed and DSG may advance. Additional
# topology diagnostics (branched/wire edges, degenerate faces or extra shells)
# are retained as warnings but are not misreported as open scan holes. A geometry
# edit invalidates the stored certification through the object signature.
NEXT_STEP_MANIFOLD_GATE_VERSION = 2
_AUTO_CLOSED_MODEL_ADVANCE_PENDING = set()
NEXT_STEP_MANIFOLD_GATE_FLAG = 'DSG_next_step_manifold_passed'
NEXT_STEP_MANIFOLD_GATE_REPORT = 'DSG_next_step_manifold_report'
NEXT_STEP_MANIFOLD_GATE_SIGNATURE = 'DSG_next_step_manifold_signature'
NEXT_STEP_MANIFOLD_GATE_ROLE = 'DSG_next_step_manifold_role'
_STEP_GATE_ROLLBACK_ACTIVE = False
_DSG_UNDO_OPERATOR_ACTIVE = False
_DSG_LAST_UNDO_TIME = 0.0

# v8.0.84 — Central workflow state machine.  A clinical step is never entered
# merely because an operator assigned ``current_step``.  Every transition is
# audited against the tangible objects produced by all earlier stages. Back
# restores a DSG-owned geometric checkpoint rather than using Blender's global
# memfile undo. Ctrl+Z remains a separate local Blender undo operation.
WORKFLOW_STATE_VERSION = 1
WORKFLOW_LAST_VALID_STEP_KEY = 'DSG_workflow_last_valid_step'
WORKFLOW_GATE_MESSAGE_KEY = 'DSG_workflow_gate_message'
WORKFLOW_GATE_TARGET_KEY = 'DSG_workflow_gate_target'
WORKFLOW_GATE_FALLBACK_KEY = 'DSG_workflow_gate_fallback'
WORKFLOW_IRRIGATION_RESOLVED_KEY = 'DSG_workflow_irrigation_resolved'
WORKFLOW_REINFORCEMENT_RESOLVED_KEY = 'DSG_workflow_reinforcement_resolved'
WORKFLOW_IMPLANTS_CONFIRMED_KEY = 'DSG_workflow_implants_confirmed'

# Operations that must stay outside Mixar's agent execution context.  This list
# protects confirmation/final/destructive gates even if an agent-generated
# script bypasses the normal DSG Agent Facade.  Absence of Mixar context is not
# treated as proof of human presence; this is a one-way deny rule only.
AGENT_USER_ONLY_OPERATOR_IDS = frozenset({
    'dsg.clinical_confirm_review',
    'dsg.confirm_model',
    'dsg.confirm_axis',
    'dsg.confirm_blockout',
    'dsg.confirm_contour',
    'dsg.confirm_implant',
    'dsg.confirm_microscrew_preview',
    'dsg.confirm_tube_frame',
    'dsg.confirm_sleeve',
    'dsg.confirm_drill',
    'dsg.confirm_irrigation_preview',
    'dsg.update_confirm_irrigation',
    'dsg.confirm_irrigation',
    'dsg.confirm_reinforcement_preview',
    'dsg.apply_reinforcements',
    'dsg.apply_patient_engrave',
    'dsg.export_guide_stl',
    'dct.apply_cut',
})
WORKFLOW_PASSIVE_SIGNATURE_KEY = 'DSG_workflow_passive_signature'
WORKFLOW_IMPLANT_SIGNATURE_KEY = 'DSG_workflow_implant_signature'
WORKFLOW_IMPLANT_SIGNATURE_SCHEMA_KEY = 'DSG_workflow_implant_signature_schema'
WORKFLOW_IMPLANT_SIGNATURE_SCHEMA = 2
WORKFLOW_CONTOUR_SIGNATURE_KEY = 'DSG_workflow_contour_signature'
WORKFLOW_FRAME_SIGNATURE_KEY = 'DSG_workflow_frame_signature'
WORKFLOW_SLEEVE_SIGNATURE_KEY = 'DSG_workflow_sleeve_signature'
WORKFLOW_IRRIGATION_SIGNATURE_KEY = 'DSG_workflow_irrigation_signature'
WORKFLOW_REINFORCEMENT_SIGNATURE_KEY = 'DSG_workflow_reinforcement_signature'
WORKFLOW_DRILL_SIGNATURE_KEY = 'DSG_workflow_drill_signature'
WORKFLOW_RESTORE_PENDING = set()
_WORKFLOW_RESTORE_ACTIVE = False

# v8.2.7 — Geometric checkpoints for real Back navigation. Each forward
# transition stores the completed stage in a hidden collection. Back restores
# that exact stage, including meshes changed by later Boolean/remesh operations,
# instead of only changing the menu and object visibility.
WORKFLOW_CHECKPOINT_VERSION = 1
WORKFLOW_CHECKPOINT_COLLECTION_PREFIX = '__DSG_Checkpoint_Step_'
WORKFLOW_CHECKPOINT_STATE_PREFIX = 'DSG_workflow_checkpoint_state_'
WORKFLOW_CHECKPOINT_OBJECT_FLAG = 'DSG_workflow_checkpoint_object'
WORKFLOW_CHECKPOINT_SOURCE_NAME = 'DSG_workflow_checkpoint_source_name'
WORKFLOW_CHECKPOINT_SOURCE_ROLE = 'DSG_workflow_checkpoint_source_role'
WORKFLOW_CHECKPOINT_SOURCE_SUITE_ROLE = 'DSG_workflow_checkpoint_source_suite_role'
WORKFLOW_CHECKPOINT_SOURCE_COLLECTIONS = 'DSG_workflow_checkpoint_source_collections'
WORKFLOW_CHECKPOINT_SOURCE_PARENT = 'DSG_workflow_checkpoint_source_parent'
WORKFLOW_CHECKPOINT_SOURCE_HIDE_VIEWPORT = 'DSG_workflow_checkpoint_source_hide_viewport'
WORKFLOW_CHECKPOINT_SOURCE_HIDE_RENDER = 'DSG_workflow_checkpoint_source_hide_render'
WORKFLOW_CHECKPOINT_SOURCE_HIDE_SELECT = 'DSG_workflow_checkpoint_source_hide_select'
WORKFLOW_CHECKPOINT_SOURCE_DISPLAY_TYPE = 'DSG_workflow_checkpoint_source_display_type'
WORKFLOW_CHECKPOINT_SOURCE_SHOW_IN_FRONT = 'DSG_workflow_checkpoint_source_show_in_front'
WORKFLOW_CHECKPOINT_SOURCE_MATRIX_WORLD = 'DSG_workflow_checkpoint_source_matrix_world'
WORKFLOW_CHECKPOINT_MASKED_VALUES = 'DSG_workflow_checkpoint_masked_values'
WORKFLOW_CHECKPOINT_BOOLEAN_MASK_KEYS = (
    'DSG_animated_implant', 'DSG_animated_drill', 'DSG_animated_microscrew',
    'DSG_static_microscrew', 'DSG_microscrew_preview',
    'DSG_microscrew_visual_preview', 'DSG_microscrew_confirmed',
    'DSG_sleeve_preview', 'DSG_irrigation_preview',
    'DSG_irrigation_wall_confirmed', 'DSG_reinforcement_preview',
    'DSG_reinforcement_confirmed', 'DSG_retention_preview',
)
_WORKFLOW_CHECKPOINT_ACTIVE = False

# Runtime-only navigation snapshot.  Blender's geometry/RNA undo restores the
# implant objects, but it does not reliably restore View3D shading, the DICOM
# review UI or transient emergence controllers.  Keeping this outside Scene
# data lets it survive Ctrl+Z and allows the implant step to be reconstructed
# exactly after returning from the contour step.
_IMPLANT_STEP_RETURN_STATE = {}
_IMPLANT_STEP_RESTORE_PENDING = set()

RETENTION_PREVIEW_NAMES = {
    'LOW': 'DSG_Retention_LOW',
    'MEDIUM': 'DSG_Retention_MEDIUM',
    'HIGH': 'DSG_Retention_HIGH',
}
RETENTION_BOUNDARY_PREVIEW_NAMES = {
    'LOW': 'DSG_RetentionBoundary_LOW',
    'MEDIUM': 'DSG_RetentionBoundary_MEDIUM',
    'HIGH': 'DSG_RetentionBoundary_HIGH',
}
RETENTION_MIN_UNDERCUT_MM = 0.06
RETENTION_MAX_UNDERCUT_MM = 0.42
# Professional three-preset workflow.  The principal clinical parameter is the
# axial undercut depth that remains engaged after blockout.  Exocad exposes
# undercut depth and draft angle separately; DSG presents safe, understandable
# presets while keeping the exact values centralized for future validation.
# Evidence-informed, deliberately conservative presets.  The interface stays
# simple, while the algorithm treats internal clearance, retained undercut and
# draft allowance as separate quantities. AUTO is the central reproducible
# preset; LOW and HIGH provide predictable limits.
RETENTION_PASSIVE_CLEARANCE_MM = 0.12
RETENTION_LEVEL_CLEARANCE_MM = {
    'LOW': 0.18,
    'AUTO': 0.12,
    'MEDIUM': 0.12,  # legacy alias
    'HIGH': 0.08,
}
RETENTION_LEVEL_ENGAGEMENT_MM = {
    'LOW': 0.10,
    'AUTO': 0.22,  # central reproducible profile
    'MEDIUM': 0.22,  # legacy alias
    'HIGH': 0.35,
}
RETENTION_LEVEL_DRAFT_ANGLE_DEG = {
    'LOW': 3.0,
    'AUTO': 2.0,
    'MEDIUM': 2.0,  # legacy alias
    'HIGH': 1.0,
}
RETENTION_AUTO_MIN_ENGAGEMENT_MM = 0.12
RETENTION_AUTO_MAX_ENGAGEMENT_MM = 0.28
# Surgical-guide passive-seat protocol. The clinical fit is created in the
# blockout itself; the final Boolean must not invent crown-like cement space.
# A local Boolean overlap is retained only as a transactional rescue when the
# already-prepared closed blockout cannot be used directly.
RETENTION_BOOLEAN_OVERLAP_MM = 0.010
RETENTION_BOOLEAN_OVERLAP_RETRIES_MM = (0.010, 0.020, 0.030)
RETENTION_BOOLEAN_OVERLAP_MAX_MM = 0.030
RETENTION_BOOLEAN_OVERLAP_RINGS = 2
RETENTION_BOOLEAN_PROXY_INSET_MM = 0.010
RETENTION_JOIN_BAND_WIDTH_MM = 0.18
RETENTION_JOIN_DISTANCE_EPS_MM = 0.008

# Blender modifier protocol derived from the supplied manual workflow:
# passive Shrinkwrap -> local boundary relaxation -> passive Shrinkwrap lock ->
# controlled BMesh cleanup. All modifiers are applied transactionally to a copy.
RETENTION_PROTOCOL_PASSIVE_SHRINKWRAP = True
RETENTION_PROTOCOL_TRANSITION_RINGS = 3
RETENTION_PROTOCOL_RELAX_ITERATIONS = 3
RETENTION_PROTOCOL_RELAX_FACTOR = 0.16
RETENTION_PROTOCOL_RELAX_BORDER_FACTOR = 0.05
RETENTION_PROTOCOL_MAX_SMOOTH_DELTA_MM = 0.040
RETENTION_PROTOCOL_MERGE_DISTANCE_MM = 0.0001
RETENTION_PROTOCOL_DISSOLVE_ANGLE_DEG = 2.0
RETENTION_PROTOCOL_MAX_HOLE_SIDES = 80
# Performance controls. Preview generation stays clinically faithful but
# defers expensive presentation-only contour reconstruction and one final
# scalar smoothing pass until confirmation. The BVH survey is cached by
# model geometry + insertion view, so changing retention presets does not
# repeat tens of thousands of ray casts.
RETENTION_PREVIEW_SMOOTH_MAX_ITERATIONS = 2
# Shrinkwrap-proxy inspired transition regularisation.  The legacy/manual
# workflow duplicated the border, relaxed several surrounding rings and then
# shrinkwrapped the proxy back to the dental model.  DSG reproduces the useful
# geometry principle directly on the axial displacement field, avoiding
# context-sensitive operators and the optional LoopTools dependency.
RETENTION_PROXY_RELAX_RINGS = 3
RETENTION_PROXY_RELAX_PREVIEW_ITERATIONS = 1
RETENTION_PROXY_RELAX_FINAL_ITERATIONS = 5
RETENTION_PROXY_RELAX_FACTOR = 0.46
RETENTION_PROXY_MEDIAN_FACTOR = 0.22
# Directional survey proxy.  This reproduces the useful geometry behind the
# supplied plane -> subdivide -> shrinkwrap -> proximity workflow without
# destructive modifiers.  A dense 2-D height field is built perpendicular to
# the exact user-view insertion axis.  It represents the frontmost insertion
# envelope, while BVH rays validate and refine the measured undercut depth.
RETENTION_SURVEY_ENGINE_VERSION = 7
# v8.0.87 simple blockout engine.  The preview is a single NumPy pass over the
# original IOS: one transverse height cell per vertex, no BVH, no ray casting,
# no BMesh relaxation and no iterative insertion correction.  The topology is
# copied unchanged, so a closed/manifold IOS remains closed/manifold.
RETENTION_SIMPLE_GRID_TARGET_MM = 0.42
RETENTION_SIMPLE_GRID_MIN_MM = 0.30
RETENTION_SIMPLE_GRID_MAX_MM = 0.70
RETENTION_SIMPLE_GRID_MAX_CELLS = 320
RETENTION_SIMPLE_MAX_DEPTH_MM = 3.00
RETENTION_SIMPLE_FULL_CLEARANCE_DEPTH_MM = 4.50
RETENTION_SIMPLE_NORMAL_DOT_LIMIT = -0.02
RETENTION_SIMPLE_MIN_CELL_VERTICES = 2
RETENTION_SIMPLE_MIN_PATCH_CELL_SUPPORT = 2
RETENTION_SIMPLE_MOVE_EPS_MM = 0.012
# v8.0.88: orthographic triangle-raster survey. Blender's renderer performs
# the expensive hidden-surface test on triangles; Python only samples the cached
# depth image and writes the prepared IOS coordinates once.  This avoids both the
# weak vertex-cell envelope and the old per-vertex BVH bottleneck.
RETENTION_RASTER_PIXEL_MM = 0.16
RETENTION_RASTER_MIN_PIXELS = 192
RETENTION_RASTER_MAX_PIXELS = 640
RETENTION_RASTER_MARGIN_MM = 1.25
RETENTION_RASTER_CAMERA_MARGIN_MM = 6.0
RETENTION_RASTER_DEPTH_BIAS_MM = 0.035
RETENTION_RASTER_SHALLOW_VISIBLE_LIMIT_MM = 0.18
RETENTION_RASTER_SHALLOW_VISIBLE_NORMAL_DOT = 0.40
RETENTION_RASTER_MAX_CLINICAL_DEPTH_MM = 5.50
RETENTION_RASTER_FALLBACK_RADIUS_PIXELS = 1
RETENTION_RASTER_ENGINE_VERSION = 1
RETENTION_SURVEY_GRID_TARGET_MM = 0.28
RETENTION_SURVEY_GRID_MIN_MM = 0.18
RETENTION_SURVEY_GRID_MAX_MM = 0.48
RETENTION_SURVEY_GRID_MAX_CELLS = 360
# One cell is enough to bridge tessellation gaps. Larger dilation can jump an
# interdental space and create a false insertion curtain.
RETENTION_SURVEY_DILATION_CELLS = 1
RETENTION_SURVEY_MIN_SUPPORT_CELLS = 2
RETENTION_SURVEY_RAY_BLEND = 0.22
RETENTION_SURVEY_RAY_TOLERANCE_MM = 0.25
# A clinical blockout candidate must have a real same-component BVH impact.
# Height-field-only candidates are never allowed to deform the IOS.
RETENTION_SURVEY_REQUIRE_DIRECT_RAY = False
# Preview-safe hybrid survey. Shallow, well-supported proxy columns are accepted
# immediately; deeper/ambiguous columns share one BVH ray per transverse cell.
# A bounded coherent proxy fallback prevents an empty preview without allowing
# the multi-millimetre jumps that produced the former vertical curtains.
RETENTION_SURVEY_FAST_PROXY_DEPTH_MM = 0.55
RETENTION_SURVEY_PROXY_ONLY_MAX_DEPTH_MM = 1.35
RETENTION_SURVEY_RAY_NORMAL_MIN_DOT = -0.70
RETENTION_SURVEY_RAY_MAX_EXTRA_MM = 0.75
# Only the coronal/support shell close to the frontmost insertion envelope may
# receive blockout or passive clearance. Closed scan bases and remote DICOM-like
# surfaces remain exactly unchanged.
RETENTION_CLINICAL_SURFACE_FULL_DEPTH_MM = 4.50
RETENTION_CLINICAL_SURFACE_MAX_DEPTH_MM = 6.50
RETENTION_MIN_CANDIDATE_COMPONENT_VERTICES = 5
RETENTION_MAX_CANDIDATE_RATIO = 0.55
RETENTION_DETAILED_BOUNDARY_FACE_LIMIT = 90000
RETENTION_CACHE_MAX_ENTRIES = 3
# Automatic insertion-envelope validation.  These limits are not a warning
# system: they are hidden targets used to add only the extra blockout required
# after the selected LOW/AUTO/HIGH profile has been calculated.  The correction
# runs on the scalar displacement field, never on the source anatomy.
RETENTION_INSERTION_WARNING_SCORE = 0.52  # legacy compatibility only
RETENTION_INSERTION_WARNING_P90_MM = 0.30  # legacy compatibility only
RETENTION_INSERTION_WARNING_MAX_MM = 0.48  # legacy compatibility only
RETENTION_INSERTION_P90_LIMIT_MM = {
    'LOW': 0.10,
    'AUTO': 0.20,
    'MEDIUM': 0.20,
    'HIGH': 0.28,
}
RETENTION_INSERTION_MAX_LIMIT_MM = {
    'LOW': 0.16,
    'AUTO': 0.28,
    'MEDIUM': 0.28,
    'HIGH': 0.40,
}
RETENTION_INSERTION_PREVIEW_ITERATIONS = 1
RETENTION_INSERTION_FINAL_ITERATIONS = 6
RETENTION_INSERTION_VALIDATION_TOLERANCE_MM = 0.012
RETENTION_INSERTION_UPWARD_SMOOTH_FACTOR = 0.32
RETENTION_INSERTION_UPWARD_SMOOTH_ITERATIONS = 2
RETENTION_LEVEL_TRANSITION_SMOOTH = {
    # Preview and final generation use the same stable displacement field. The
    # final model adds extra iterations below, but previews must also be smooth;
    # otherwise dense/noisy intraoral scans show vertical 'curtains'.
    'LOW': (5, 0.42),
    'AUTO': (4, 0.38),
    'MEDIUM': (4, 0.38),
    'HIGH': (4, 0.34),
}
# Compatibility constants retained for older .blend files; the restored
# maximum-coronary-perimeter blockout does not use these filters.
RETENTION_BOUNDARY_EXCLUDE_RINGS = 2
RETENTION_MAX_ANALYSIS_DEPTH_MM = 3.00
RETENTION_DEPTH_NEIGHBOUR_TOLERANCE_MM = 0.65
RETENTION_MIN_COHERENT_NEIGHBOURS = 2
RETENTION_DISPLACEMENT_EDGE_BASE_MM = 0.06
RETENTION_DISPLACEMENT_EDGE_SLOPE = 0.90
RETENTION_TARGET_ENGAGEMENT_MM = RETENTION_LEVEL_ENGAGEMENT_MM['AUTO']
RETENTION_ZONE_RADIUS_MM = 3.4
RETENTION_SAMPLE_LIMIT = 24000
RETENTION_REQUIRED_ZONES = 1
# Retained only for backward compatibility with scenes created by v8.0.29-35.
RETENTION_LEVEL_MAXIMUM_FRACTION = {'LOW': 0.55, 'AUTO': 0.55, 'MEDIUM': 0.55, 'HIGH': 0.55}
RETENTION_LEVEL_AXIAL_OFFSET_MM = {'LOW': -1.0, 'AUTO': 0.0, 'MEDIUM': 0.0, 'HIGH': 1.0}
COMBINED_NAME   = "DSG_PassiveCombined"
COMBINED_CANDIDATE_NAME = "DSG_PassiveCombined_Candidate"
FRAME_NAME      = "DSG_Frame"
GUIDE_NAME      = "DSG_Guide"
SLEEVE_SOURCE_FRAME_NAME = "DSG_SourceFrame_Hidden"
SLEEVE_SOURCE_PREFIX = "DSG_SourceSleeve_Hidden_"
GUIDE_BUILD_TMP_NAME = "DSG_Guide_BuildTmp"
SLEEVE_NAME     = "DSG_Sleeve"

_DSG_CUSTOM_PREVIEWS = None

def _register_dsg_custom_icons():
    global _DSG_CUSTOM_PREVIEWS
    if _DSG_CUSTOM_PREVIEWS is not None:
        return
    try:
        previews = bpy.utils.previews.new()
        icon_dir = os.path.join(os.path.dirname(__file__), 'icons')
        previews.load('mpr_orange', os.path.join(icon_dir, 'mpr_orange.png'), 'IMAGE')
        previews.load('implant_tea', os.path.join(icon_dir, 'implant_tea.png'), 'IMAGE')
        _DSG_CUSTOM_PREVIEWS = previews
    except Exception as exc:
        _DSG_CUSTOM_PREVIEWS = None
        print(f'[DSG] Could not load custom clinical icons: {exc}')

def _unregister_dsg_custom_icons():
    global _DSG_CUSTOM_PREVIEWS
    if _DSG_CUSTOM_PREVIEWS is None:
        return
    try:
        bpy.utils.previews.remove(_DSG_CUSTOM_PREVIEWS)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _DSG_CUSTOM_PREVIEWS = None

def _dsg_custom_icon_id(name):
    try:
        return int(_DSG_CUSTOM_PREVIEWS[name].icon_id) if _DSG_CUSTOM_PREVIEWS is not None else 0
    except Exception:
        return 0
DRILL_NAME      = "DSG_Drill"
IMPLANT_PREFIX  = "DSG_Implant"
DICOM_MEASURE_PREFIX = "DSG_DICOM_Measure_"
DICOM_MEASURE_POINT_A_PREFIX = "DSG_DICOM_MeasurePointA_"
DICOM_MEASURE_POINT_B_PREFIX = "DSG_DICOM_MeasurePointB_"
DICOM_MEASURE_LINE_MATERIAL = "DSG_DICOM_Measure_Turquoise"
DICOM_MEASURE_POINT_A_MATERIAL = "DSG_DICOM_Measure_ImplantPoint"
DICOM_MEASURE_POINT_B_MATERIAL = "DSG_DICOM_Measure_AnatomyPoint"
DICOM_MEASURE_PLANE_NAMES = (
    "DICOM_PLANE_AXIAL",
    "DICOM_PLANE_CORONAL",
    "DICOM_PLANE_SAGITTAL",
)
IMPLANT_EMERGENCE_PREFIX = "DSG_EmergenceTube"
IMPLANT_EMERGENCE_LEGACY_PREFIX = "DSG_ImplantEmergence"
IMPLANT_EMERGENCE_LENGTH_MM = 15.0
IMPLANT_EMERGENCE_DIAMETER_MM = 2.0
# Seguridad mesiodistal: la recomendación clínica clásica reserva 1,5 mm
# alrededor de cada implante, lo que equivale a 3,0 mm libres entre dos
# plataformas adyacentes. El addon visualiza ambos halos y no permite avanzar
# al frame mientras exista una pareja por debajo de esa separación.
IMPLANT_SAFETY_PREFIX = "DSG_SafetyHalo_"
# One longitudinal safety envelope is reused for both interimplant and
# implant-to-segmented-tooth review. Interimplant clearance remains 3.0 mm
# total (1.5 mm per implant). The tooth margin is configurable because it is
# evidence/context driven and must not be frozen forever in geometry code.
INTERIMPLANT_SAFETY_MARGIN_PER_IMPLANT_MM = 1.50
INTERIMPLANT_MIN_CLEARANCE_MM = 3.00
IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM = 1.50
IMPLANT_SAFETY_ENVELOPE_MIN_HEIGHT_MM = 0.80
INTERIMPLANT_NUMERIC_TOLERANCE_MM = 0.02
IMPLANT_TOOTH_NUMERIC_TOLERANCE_MM = 0.02
SLEEVE_PREFIX   = "DSG_Sleeve"
DRILL_PREFIX    = "DSG_Drill"
DRILL_BATCH_CUTTER_NAME = "DSG_Drill_AllCutter"
DRILL_PROTECTION_PREFIX = "DSG_DrillProtection_"
DRILL_PROTECTION_RESULT_NAME = "DSG_Guide_DrillProtected"
ENGRAVE_ANCHOR_NAME = "DSG_EngraveAnchor"
ENGRAVE_PREVIEW_NAME = "DSG_EngravePreview"
ENGRAVE_CUTTER_NAME = "DSG_EngraveCutter"
CONTOUR_CURVE_NAME = "DSG_ContourCurve"
RETENTION_BOUNDARY_NAME = "DSG_RetentionBoundary"
RETENTION_BOUNDARY_MATERIAL_NAME = "DSG_RetentionBoundary_Mat"
RETENTION_BOUNDARY_ISO_MM = 0.015
RETENTION_BOUNDARY_SURFACE_OFFSET_MM = 0.055
RETENTION_BOUNDARY_NODE_TOLERANCE_MM = 0.10
RETENTION_BOUNDARY_MIN_LENGTH_MM = 1.25
IRR_PREVIEW_PREFIX = "DSG_Irr_Preview_"
IRR_PREVIEW_PATH_PREFIX = "DSG_Irr_PathPreview_"
IRR_WALL_PREFIX = "DSG_Irr_Wall_"
IRR_LINK_MARKER_PREFIX = "DSG_Irr_LinkPoint_"
IRR_COMBINED_TMP_NAME = "DSG_IrrigationCombinedTmp"
IRR_FLOW_SIM_PREFIX = "DSG_IrrFlowSim_"
IRR_FLOW_SIM_MATERIAL = "DSG_IrrFlowWater_Mat"
IRR_LUMEN_DIAGNOSTIC_NAME = "Lumen real comprobado"
IRR_LUMEN_DIAGNOSTIC_MATERIAL = "DSG_LumenRealComprobado_Mat"
IRR_FLOW_VIEWPORT_PARTICLE_MATERIAL = "DSG_IrrFlowViewportParticles_Mat"
IRR_FLOW_CFD_MOD_PREFIX = "DSG_IrrFlowCFD_"
REINFORCEMENT_PREFIX = "DSG_Reinforcement_"
REINFORCEMENT_PREVIEW_NAME = "DSG_Reinforcement_Preview"
REINFORCEMENT_MARKER_NAME = "DSG_Reinforcement_PointA"
REINFORCEMENT_MARKER_PREFIX = "DSG_Reinforcement_Point_"
REINFORCEMENT_COMBINED_TMP_NAME = "DSG_ReinforcementCombinedTmp"
REINFORCEMENT_BLEND_TMP_PREFIX = "DSG_ReinforcementCoonsBlendTmp_"
REINFORCEMENT_TUBE_TMP_NAME = "DSG_ReinforcementTubeTmp"
REINFORCEMENT_CENTERLINE_TMP_NAME = "DSG_ReinforcementCenterlineTmp"
# Paso 8 visible (Refuerzos): diámetro aumentado un 25 % respecto al valor histórico de 2,0 mm.
REINFORCEMENT_DIAMETER_MM = 2.5
# Transición con el soporte: conserva la huella Coons de v6.12.21, pero el tubo
# se recorta y el collar ocupa realmente la zona de empalme. Las secciones
# circulares se transportan con un marco de rotación mínima.
REINFORCEMENT_BLEND_FOOT_SCALE = 1.72
REINFORCEMENT_BLEND_TANGENTIAL_STRETCH = 0.38
REINFORCEMENT_BLEND_OVERLAP_MM = 0.22
REINFORCEMENT_BLEND_RING_SEGMENTS = 48
REINFORCEMENT_BLEND_LONGITUDINAL_STEPS = 14
REINFORCEMENT_BLEND_NECK_RADIUS_SCALE = 2.15
REINFORCEMENT_BLEND_MIN_BODY_RADIUS_SCALE = 0.85
REINFORCEMENT_BLEND_MIN_BODY_MM = 0.65
REINFORCEMENT_BLEND_SUPPORT_HANDLE_SCALE = 0.82
REINFORCEMENT_BLEND_TUBE_HANDLE_SCALE = 0.94
# Volumen exclusivamente en la zona media del collar: no modifica ni la huella
# sobre el soporte ni el aro que comparte con el tubo.
REINFORCEMENT_BLEND_MID_FULLNESS_GAIN = 0.22
REINFORCEMENT_BLEND_RING_SMOOTH_WEIGHT = 0.16
REINFORCEMENT_BLEND_RING_SMOOTH_PASSES = 2
REINFORCEMENT_BLEND_RADIUS_EQUALIZE_WEIGHT = 0.58
REINFORCEMENT_BLEND_NORMAL_ENTRY_THRESHOLD = 0.62
REINFORCEMENT_BLEND_NORMAL_ENTRY_FOOT_GAIN = 0.36
REINFORCEMENT_BLEND_NORMAL_ENTRY_ELLIPSE_DAMP = 0.75
REINFORCEMENT_BLEND_NORMAL_ENTRY_DIRECT_WEIGHT = 0.82
REINFORCEMENT_BLEND_NORMAL_ENTRY_SUPPORT_HANDLE_GAIN = 1.26
REINFORCEMENT_BLEND_NORMAL_ENTRY_TUBE_HANDLE_GAIN = 0.84
REINFORCEMENT_BLEND_NORMAL_ENTRY_FULLNESS_DAMP = 0.18
REINFORCEMENT_BLEND_VOLCANO_ADAPTIVE_FOOTPRINT = True
REINFORCEMENT_BLEND_VOLCANO_SCALE_SMOOTH_PASSES = 4
REINFORCEMENT_BLEND_VOLCANO_SCALE_SMOOTH_WEIGHT = 0.20
REINFORCEMENT_BLEND_VOLCANO_SUPPORT_RING_SMOOTH_PASSES = 3
REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_PASSES = 3
REINFORCEMENT_BLEND_VOLCANO_HANDLE_SMOOTH_WEIGHT = 0.18
# Protección frente a saltos del nearest-point hacia caras vecinas del STL.
REINFORCEMENT_BLEND_MAX_TANGENTIAL_PROJECTION_SCALE = 0.34
REINFORCEMENT_BLEND_MAX_NORMAL_PROJECTION_SCALE = 0.72
REINFORCEMENT_BLEND_SUPPORT_FIT_MARGIN_MM = 0.18
REINFORCEMENT_BLEND_SUPPORT_FIT_INSIDE_DEPTH_MM = 0.18
REINFORCEMENT_BLEND_SUPPORT_FIT_SCALE = 0.90
REINFORCEMENT_BLEND_UNION_TARGET_RADIUS_RATIO = 2.95
REINFORCEMENT_BLEND_UNION_MIN_RADIUS_RATIO = 1.72
REINFORCEMENT_BLEND_UNION_MAJOR_RATIO = 1.22
REINFORCEMENT_BLEND_EDGE_CLIP_ENABLED = True
REINFORCEMENT_BLEND_EDGE_CLIP_BINARY_STEPS = 11
REINFORCEMENT_BLEND_EDGE_CLIP_SAFETY_SCALE = 0.91
REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_MIN_MM = 1.60
REINFORCEMENT_BLEND_EDGE_CLIP_PROBE_RADIUS_SCALE = 2.80
REINFORCEMENT_BLEND_ROUND_FIT_ENABLED = True
REINFORCEMENT_BLEND_ROUND_FIT_BINARY_STEPS = 13
REINFORCEMENT_BLEND_ROUND_FIT_SAFETY_SCALE = 0.93
REINFORCEMENT_BLEND_ROUND_FIT_MIN_SCALE = 0.12
# Anclajes inteligentes: el clic del usuario define una zona de intención, no
# una posición rígida. El optimizador busca cerca un apoyo con más espacio,
# mejor tangencia y menor irregularidad superficial.
REINFORCEMENT_SMART_ANCHORS_ENABLED = False
REINFORCEMENT_SMART_ANCHOR_SEARCH_RADIUS_MM = 2.80
REINFORCEMENT_SMART_ANCHOR_RING_FRACTIONS = (0.45, 0.90)
REINFORCEMENT_SMART_ANCHOR_SAMPLES_PER_RING = 8
REINFORCEMENT_SMART_ANCHOR_SHORTLIST = 6
REINFORCEMENT_SMART_ANCHOR_REFINEMENT_RADIUS_MM = 0.55
REINFORCEMENT_SMART_ANCHOR_MAX_MOVE_MM = 3.20
REINFORCEMENT_SMART_ANCHOR_MIN_NORMAL_DOT = 0.35
REINFORCEMENT_SMART_ANCHOR_MAX_PROJECTION_MM = 1.10
REINFORCEMENT_SMART_ANCHOR_MOVE_WEIGHT = 0.85
REINFORCEMENT_SMART_ANCHOR_TANGENCY_WEIGHT = 3.20
REINFORCEMENT_SMART_ANCHOR_FIT_WEIGHT = 8.50
REINFORCEMENT_SMART_ANCHOR_ROUGHNESS_WEIGHT = 1.40
REINFORCEMENT_SMART_ANCHOR_PAIR_TANGENCY_WEIGHT = 3.50
REINFORCEMENT_SMART_ANCHOR_TWIST_WEIGHT = 0.35
REINFORCEMENT_SMART_ANCHOR_COORDINATE_PASSES = 2
REINFORCEMENT_STRUCTURAL_WEAKNESS_ENABLED = True
REINFORCEMENT_STRUCTURAL_THICKNESS_MAX_MM = 12.0
REINFORCEMENT_STRUCTURAL_THICKNESS_EPSILON_MM = 0.055
REINFORCEMENT_STRUCTURAL_THICKNESS_SAMPLE_RADIUS_SCALE = 0.42
REINFORCEMENT_STRUCTURAL_MIN_VALID_THICKNESS_MM = 0.22
REINFORCEMENT_STRUCTURAL_WEAKNESS_TOLERANCE_MM = 0.38
REINFORCEMENT_STRUCTURAL_WEAKNESS_WEIGHT = 18.0
REINFORCEMENT_STRUCTURAL_INVALID_THICKNESS_PENALTY = 20.0
REINFORCEMENT_STRUCTURAL_BURIAL_WEIGHT = 2.8
REINFORCEMENT_STRUCTURAL_BURIAL_FRACTION = 0.44
REINFORCEMENT_STRUCTURAL_PREBOOLEAN_OVERLAP = True
REINFORCEMENT_STRUCTURAL_INTERIOR_HIT_DOT_MIN = -0.20
REINFORCEMENT_STRUCTURAL_INTERIOR_ORIGIN_EPS_MM = 0.045
REINFORCEMENT_STRUCTURAL_MIN_SOLID_OVERLAP_MM = 0.20
REINFORCEMENT_STRUCTURAL_BURIAL_MIN_MM = 0.12
REINFORCEMENT_STRUCTURAL_BURIAL_MAX_MM = 1.15
# Frame: radio predeterminado aumentado un 25 % (2,0 -> 2,5 mm).
FRAME_RADIUS_DEFAULT_MM = 3.0

# Parámetros clínicos internos predefinidos. Se mantienen funcionales, pero no
# se muestran en la interfaz para evitar ajustes accidentales y simplificar el flujo.
FRAME_CATMULL_ALPHA_FIXED = 0.5
# v9.2.69 — sparse Catmull control polygon for the surface frame.
# The geodesic solver may return hundreds of tightly spaced samples which
# faithfully follow mesh triangulation but also preserve high-frequency
# zig-zag.  We intentionally keep Catmull CONTROL points much farther apart
# and then evaluate a dense smooth spline for the cylindrical sweep.
FRAME_CATMULL_SPACING_MM_FIXED = 5.00  # legacy/public name: now control spacing
FRAME_CATMULL_CONTROL_SPACING_MM_FIXED = 5.00
FRAME_CATMULL_SAMPLE_SPACING_MM_FIXED = 0.30
FRAME_CATMULL_KEEP_TURN_DEG = 22.0
FRAME_CATMULL_MIN_CONTROL_SEPARATION_FACTOR = 0.42
FRAME_CATMULL_MAX_SURFACE_PROJECTION_MM = 1.20
FRAME_CATMULL_ROUTE_TETHER_MM = 0.95
# v9.2.66 — Simple surface shortest-path frame engine.
# The clinician places only the anchors that describe the frame. DSG preserves
# click order and connects consecutive anchors by the shortest route on the
# evaluated passive-model surface. The cylindrical tube is intentionally
# allowed to intersect the model because the final DSG boolean adapts it to
# anatomy. Width/clearance heuristics no longer veto a valid centreline.
# No free-space Euclidean fallback is accepted.
FRAME_SURFACE_ENGINE_ID = 'SURFACE_SHORTEST_PATH_V1_CONTINUOUS'
FRAME_SURFACE_TARGET_SPACING_MM = 0.30
FRAME_SURFACE_SIMPLIFY_SPACING_MM = 0.20
FRAME_SURFACE_SMOOTH_ITERATIONS = 0
FRAME_SURFACE_NORMAL_WEIGHT = 0.0
FRAME_SURFACE_EQUATOR_WEIGHT = 0.0
FRAME_SURFACE_MAX_PROJECTION_MM = 0.0
FRAME_SURFACE_MAX_CACHE_ENTRIES = 2
FRAME_SURFACE_LOCAL_PADDING_MIN_MM = 5.0
FRAME_SURFACE_LOCAL_PADDING_FACTOR = 0.75
FRAME_SURFACE_MAX_EXPANSIONS = 180000
# Hard frame-width gate. The tube radius is sampled laterally on both sides of
# the geodesic centreline against the real evaluated passive surface. A local
# surface that rises into the tube by more than this tolerance would physically
# narrow the post-boolean frame and is therefore rejected.
FRAME_WIDTH_SURFACE_RISE_MIN_TOL_MM = 0.18
FRAME_WIDTH_SURFACE_RISE_RADIUS_FACTOR = 0.08
FRAME_WIDTH_SURFACE_RISE_MAX_TOL_MM = 0.35
FRAME_WIDTH_SAMPLE_FRACTIONS = (0.50, 0.75, 1.00)
# Geodesic centreline remains on the passive model. The outer 25 % of the
# lateral radius may overlap/embed in the support surface; the central 75 % is
# mandatory. Thus only a failure at the 1.00-radius sample is tolerated.
FRAME_WIDTH_ALLOWED_OUTER_EMBED_RATIO = 0.25
FRAME_WIDTH_MIN_RETAINED_DIAMETER_RATIO = 0.75
FRAME_WIDTH_SAMPLE_STEP_MM = 0.45
FRAME_WIDTH_REROUTE_ATTEMPTS = 12
FRAME_WIDTH_FORBID_RADIUS_FACTOR = 0.30
FRAME_WIDTH_FORBID_RADIUS_MIN_MM = 0.45
FRAME_WIDTH_FORBID_RADIUS_MAX_MM = 1.25
FRAME_WIDTH_ANCHOR_GUARD_POINTS = 1

# v9.2.63 — semantic corridor planner. The clinician's contour is the intent;
# global shortest-edge distance is no longer the objective. A weighted intrinsic
# corridor is selected first, then the route is straightened continuously across
# triangle interiors and validated using a real local tube cross-section probe.
FRAME_CORRIDOR_RADIUS_MIN_MM = 4.0
FRAME_CORRIDOR_RADIUS_FACTOR = 2.20
# v9.2.65: the semantic contour is an intent corridor, not a hard tunnel.
# If anatomy/triangulation makes the first narrow band disconnected, expand it
# intrinsically while remaining on the same IOS surface. No Euclidean fallback.
FRAME_CORRIDOR_RADIUS_MAX_MM = 18.0
FRAME_CORRIDOR_EXPANSION_FACTORS = (1.0, 1.50, 2.25, 3.25, 4.50)
FRAME_CORRIDOR_ENDPOINT_LAUNCH_MIN_MM = 1.35
FRAME_CORRIDOR_ENDPOINT_LAUNCH_RADIUS_FACTOR = 0.90
FRAME_CORRIDOR_SEED_SPACING_MM = 0.60
FRAME_CORRIDOR_INTENT_WEIGHT = 1.60
FRAME_CORRIDOR_CLEARANCE_WEIGHT = 5.00
FRAME_CORRIDOR_CURVATURE_WEIGHT = 0.65
FRAME_CORRIDOR_HARD_MIN_RETAINED_RATIO = 0.45
FRAME_CORRIDOR_CLEARANCE_EVAL_LIMIT = 2600
FRAME_CORRIDOR_RETRY_COUNT = 4
FRAME_CORRIDOR_RETRY_RADIUS_MM = 1.10
FRAME_CONTINUOUS_SMOOTH_ITERATIONS = 10
FRAME_CONTINUOUS_SMOOTH_BLEND = 0.42
FRAME_CONTINUOUS_MAX_PROJECTION_MM = 1.60
FRAME_CONTINUOUS_EDGEFLIP_BAND_FACTOR = 0.90
FRAME_HEAT_MAX_VERTICES = 350000
FRAME_SWEEP_SAMPLE_FRACTIONS = (0.25, 0.50, 0.75, 1.00)
FRAME_SWEEP_STEP_MM = 0.35
FRAME_SURFACE_RAY_SCAN_MIN_MM = 1.50
FRAME_SURFACE_RAY_SCAN_FACTOR = 1.30

# A contour click is the clinician's semantic intent, not necessarily the exact
# millimetric centreline endpoint. If that precise surface zone cannot preserve
# the requested frame diameter, DSG may move the endpoint a short distance ALONG
# THE SAME MESH SURFACE. No Euclidean/free-space relocation is permitted.
FRAME_ANCHOR_SAFE_SNAP_MIN_MM = 1.50
FRAME_ANCHOR_SAFE_SNAP_RADIUS_FACTOR = 2.00
FRAME_ANCHOR_SAFE_SNAP_MAX_MM = 4.50
FRAME_ANCHOR_SAFE_SNAP_MAX_CANDIDATES = 2400
_FRAME_SURFACE_GRAPH_CACHE = {}
MICROSCREW_SUPPORT_DIAMETER_MM_FIXED = 3.5
MICROSCREW_CIRCULAR_SEGMENTS_FIXED = 40
MICROSCREW_FRAME_EMBED_MM_FIXED = 0.70
MICROSCREW_SLEEVE_OVERLAP_MM_FIXED = 0.65
# El cuerpo de cada conector es Ø3,5 mm, pero se estrecha solamente en la
# llegada al sleeve para mantener libre el lumen guiado de Ø2 mm.
MICROSCREW_SUPPORT_SLEEVE_NECK_DIAMETER_MM_FIXED = 2.2
MICROSCREW_SUPPORT_FRAME_FLARE_SCALE_FIXED = 1.18
MICROSCREW_SUPPORT_SLEEVE_TAPER_START_FIXED = 0.68
IRR_LUMEN_SAMPLE_STEP_MM_FIXED = 0.55
IRR_BOOLEAN_RETRY_OFFSETS_MM = (0.02, 0.05)
# Sobrecorte radial mínimo para la protección axial. Evita que el cutter
# coincida exactamente con el lumen ya creado en el sleeve, una situación
# que puede producir cientos de edges abiertas en Boolean EXACT.
DRILL_PROTECTION_ANTICOPLANAR_MM_FIXED = 0.02
# Step 9: preserve only the occlusal flat seating surface of every sleeve.
# The cleanup cutter is an annular prism matching the real sleeve support face:
# it does not create a lateral safety halo around the sleeve wall.  A tiny
# 0.02 mm radial overlap is purely numerical, preventing coplanar Boolean
# failures without creating clinically relevant clearance.
SLEEVE_FACE_CLEARANCE_ABOVE_MM_FIXED = 1.20
SLEEVE_FACE_CLEARANCE_BELOW_MM_FIXED = 0.08
SLEEVE_FACE_NUMERIC_EPS_MM_FIXED = 0.02
SLEEVE_FACE_CLEARANCE_SEGMENTS_FIXED = 48
SLEEVE_FACE_CUTTER_PREFIX = "DSG_SleeveFaceClearance_"

# Microtornillos integrados en el paso del frame.
MICROSCREW_PREFIX = "DSG_MicroScrew_"
MICROSCREW_PREVIEW_NAME = "DSG_MicroScrew_Preview"
MICROSCREW_VISUAL_PREVIEW_NAME = "DSG_MicroScrewVisual_Preview"
MICROSCREW_VISUAL_PREFIX = "DSG_MicroScrewVisual_"
MICROSCREW_MARKER_NAME = "DSG_MicroScrew_PointA"
MICROSCREW_FRAME_COMBINED_TMP_NAME = "DSG_MicroScrewFrameCombinedTmp"
MICROSCREW_SLEEVE_HEIGHT_MM = 3.0
MICROSCREW_INNER_DIAMETER_MM = 2.0
MICROSCREW_WALL_THICKNESS_MM = 1.5

# El STL aportado se integra en el addon para que la simulación no dependa de
# rutas externas. Esta versión usa una geometría refinada derivada del archivo
# Hitem3d-1782326566213.stl, reprocesada, recentrada y alineada sobre Z local
# (punta hacia -Z y cabeza hacia +Z). El plano de contacto del tope con el
# sleeve se fijó en Z local = 0.
MICROSCREW_TEMPLATE_SOURCE = "Hitem3d-1782326566213.stl"
MICROSCREW_TEMPLATE_VERTS = 12242
MICROSCREW_TEMPLATE_FACES = 24480
MICROSCREW_TEMPLATE_CONTACT_Z_MM = 0.0
MICROSCREW_TEMPLATE_TIP_Z_MM = -8.65707185
MICROSCREW_TEMPLATE_TOP_Z_MM = 0.75980717
MICROSCREW_GUIDED_DIAMETER_MM = 2.0
MICROSCREW_DIAMETER_DEFAULT_MM = 2.0
MICROSCREW_LENGTH_DEFAULT_MM = 8.0
MICROSCREW_DIAMETER_MIN_MM = 1.2
MICROSCREW_DIAMETER_MAX_MM = 3.5
MICROSCREW_LENGTH_MIN_MM = 4.0
MICROSCREW_LENGTH_MAX_MM = 20.0
MICROSCREW_TEMPLATE_ACTIVE_LENGTH_MM = abs(MICROSCREW_TEMPLATE_CONTACT_Z_MM - MICROSCREW_TEMPLATE_TIP_Z_MM)
MICROSCREW_SEAT_DEPTH_MM = 0.75
MICROSCREW_STOP_RADIUS_MM = 1.57
MICROSCREW_STOP_CLEARANCE_MM = 0.025
# Depth medida desde la cara superior del sleeve y radio interno. Este
# perfil reproduce el cono inferior del tope real del microtornillo de forma
# más fiel y compacta, manteniendo la cabeza principal por encima del sleeve.
MICROSCREW_SEAT_PROFILE_MM = (
    (0.75, 1.00000000),
    (0.70, 1.02000000),
    (0.65, 1.06000000),
    (0.60, 1.11000000),
    (0.55, 1.15000000),
    (0.50, 1.18000000),
    (0.45, 1.20000000),
    (0.40, 1.22000000),
    (0.35, 1.25000000),
    (0.30, 1.29000000),
    (0.25, 1.33000000),
    (0.20, 1.38000000),
    (0.15, 1.43000000),
    (0.10, 1.49000000),
    (0.05, 1.54000000),
    (0.00, 1.57000000),
)
ANIMATED_MICROSCREW_PREFIX = "DSG_AnimatedMicroScrew_"
ANIMATED_MICROSCREW_MATERIAL = "DSG_AnimatedMicroScrew_Mat"
ANIMATED_DRILL_TURNS_PER_MM = 0.35
ANIMATED_DRILL_MIN_TURNS = 4.0
ANIMATED_MICROSCREW_TURNS_PER_MM = 0.25
ANIMATED_MICROSCREW_MIN_TURNS = 2.5
# Separaciones internas de la secuencia. No se exponen al usuario.
ANIMATION_ITEM_STAGGER_FRAMES_FIXED = 5
ANIMATION_SEQUENCE_GAP_FRAMES_FIXED = 20
ANIMATION_IMPLANT_DURATION_FRAMES_FIXED = 45
ANIMATION_IMPLANT_START_CLEARANCE_MM_FIXED = 0.20
ANIMATION_FINAL_GUIDE_HOLD_FRAMES_FIXED = 15
ANIMATION_GUIDE_SEATING_DURATION_FRAMES_FIXED = 24
ANIMATION_GUIDE_RETURN_DURATION_FRAMES_FIXED = 24

# v9.2.72 — immediate extraction animation before the established final protocol.
ANIMATED_EXTRACTION_TOOTH_PREFIX = "DSG_AnimatedExtractionTooth_"
ANIMATION_EXTRACTION_DURATION_FRAMES_FIXED = 28
ANIMATION_EXTRACTION_STRIDE_GAP_FRAMES_FIXED = 6
ANIMATION_EXTRACTION_CLEARANCE_MIN_MM_FIXED = 8.0
ANIMATION_EXTRACTION_CLEARANCE_MAX_MM_FIXED = 18.0
ANIMATION_EXTRACTION_CLEARANCE_EXTRA_MM_FIXED = 2.0
ANIMATION_GUIDE_AXIS_OFFSET_MM_FIXED = 15.0

# Immutable seated transform of the final guide. Animation and Update may never
# redefine this position from the guide's current viewport transform.
GUIDE_HOME_MATRIX_KEY = "DSG_guide_home_matrix_world_v1"
GUIDE_HOME_SCENE_KEY = "DSG_guide_home_matrix_world_v1"
GUIDE_HOME_ROTATION_MODE_KEY = "DSG_guide_home_rotation_mode_v1"

# Irrigation sleeve port placement. The centre offset is calculated from the
# real external radius of the tapered wall at the sleeve. A tiny clearance keeps
# the wall tangent/almost flush without intersecting the coronal flat face.
IRRIGATION_SLEEVE_CORONAL_FACE_CLEARANCE_MM_FIXED = 0.03
IRRIGATION_SLEEVE_OPPOSITE_FACE_MIN_CLEARANCE_MM_FIXED = 0.25
# Unión volcánica entre el conducto exterior y la pared lateral del sleeve.
# Solo aumenta la masa exterior; el lumen hidráulico se corta después con su
# diámetro original y el lumen axial del sleeve se restaura tras la UNION.
IRRIGATION_SLEEVE_VOLCANO_RADIUS_RATIO_FIXED = 2.20
IRRIGATION_SLEEVE_VOLCANO_MIN_EXTRA_MM_FIXED = 0.95
IRRIGATION_SLEEVE_VOLCANO_OUTER_TAPER_SCALE_FIXED = 1.75
IRRIGATION_SLEEVE_VOLCANO_OUTER_TAPER_MIN_MM_FIXED = 2.60
IRRIGATION_SLEEVE_VOLCANO_INNER_FOOT_WEIGHT_FIXED = 0.72
IRRIGATION_SLEEVE_VOLCANO_SHOULDER_MIN_MM_FIXED = 0.42
IRRIGATION_SLEEVE_VOLCANO_SHOULDER_RATIO_FIXED = 0.28
IRRIGATION_SLEEVE_VOLCANO_INNER_TAPER_RATIO_FIXED = 0.62
IRRIGATION_SLEEVE_VOLCANO_BURIED_PEAK_RATIO_FIXED = 0.84
IRRIGATION_SLEEVE_VOLCANO_SURFACE_WEIGHT_FIXED = 0.22
IRRIGATION_SLEEVE_VOLCANO_VISIBLE_SHOULDER_MIN_MM_FIXED = 0.00
IRRIGATION_SLEEVE_VOLCANO_VISIBLE_SHOULDER_RATIO_FIXED = 0.000
IRRIGATION_SLEEVE_VOLCANO_VISIBLE_SHOULDER_END_WEIGHT_FIXED = 0.06
IRRIGATION_SLEEVE_VOLCANO_NECK_WEIGHT_FIXED = 0.00
IRRIGATION_SLEEVE_VOLCANO_NECK_TAPER_RATIO_FIXED = 0.55
IRRIGATION_SLEEVE_EXIT_BLEND_MIN_MM_FIXED = 1.20
IRRIGATION_SLEEVE_EXIT_BLEND_RADIUS_SCALE_FIXED = 1.65
IRRIGATION_SLEEVE_VISIBLE_EXTRA_WEIGHT_FIXED = 0.16
IRRIGATION_SLEEVE_VISIBLE_FADE_MIN_MM_FIXED = 0.90
IRRIGATION_SLEEVE_VISIBLE_FADE_RADIUS_SCALE_FIXED = 0.72
IRRIGATION_SLIM_WALL_THICKNESS_DEFAULT_MM = 0.75

# Selective multi-implant irrigation gates.  These are intentionally generated
# only on a temporary export copy, after every drill/final-cut operation has
# finished.  Creating them earlier would let the axial drill Boolean erase the
# membrane or let the final voxel remesh change its calibrated thickness.
IRRIGATION_FRANGIBLE_SEAL_PREFIX = "DSG_FrangibleSeal_"
IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED = 0.10   # 100 µm frangible wall (9.7.1)
IRRIGATION_FRANGIBLE_SEAL_RIM_THICKNESS_MM_FIXED = 0.25      # thicker rim: breaks in the centre (9.7.2)
IRRIGATION_FRANGIBLE_SEAL_SEGMENTS_FIXED = 48
IRRIGATION_FRANGIBLE_SEAL_MODE = "FRANGIBLE_INTERNAL_MARKED_DIAPHRAGM"
# Membrane/mark geometry (pocket, countersink, digit): see frangible_seal.SealDesign.
# Lateral access window safety. These are internal guardrails, not user-facing
# clinical presets; the actual window is always clamped to the available arc.
SLEEVE_WINDOW_ANGULAR_BINS = 720
SLEEVE_WINDOW_IRRIGATION_CLEARANCE_MM_FIXED = 0.60
SLEEVE_WINDOW_MIN_SIDE_WALL_MM_FIXED = 0.80
SLEEVE_WINDOW_MIN_FREE_ARC_DEG_FIXED = 40.0
SLEEVE_WINDOW_MIN_RETAINED_ARC_DEG_FIXED = 180.0
SLEEVE_WINDOW_DEFAULT_CROSSCHECK_RADIUS_MM = 1.25
ANIMATED_IMPLANT_TURNS_PER_MM = 0.65
ANIMATED_IMPLANT_MIN_TURNS = 4.0

_MICROSCREW_VISUAL_TEMPLATE_CACHE = None
_LAST_MICROSCREW_PREVIEW_ERROR = ""
_MICROSCREW_VISUAL_TEMPLATE_B85 = _load_guide_asset("microscrew_visual_template.b85")

# Fresa visual animada del paso 8.
