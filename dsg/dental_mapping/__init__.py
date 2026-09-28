"""DSG Dental Mapping package.

High-level consumers should import :mod:`service`. Low-level modules are kept
orthogonal so the external recognition engine and future MCP do not need to know
Blender object naming or registration internals.
"""
from .service import (
    get_dental_asset_contract, family_descriptor, required_landmarks,
    load_tooth_template, load_crown_template, map_patient_tooth, map_patient_crown,
    get_landmarks, get_tooth_frame, get_mapping_quality,
    select_crown_candidate, fit_crown_to_neighbors, fit_occlusion,
    get_emergence_region, get_prosthetic_axis, build_implant_planning_context,
    get_gold_standard, analyze_implant_bone_support, analyze_implant_neighbor_clearance, analyze_interdental_space, analyze_implant_diameter_options, build_full_implant_context,
    prepare_implant_axis_from_prosthetic_context, evaluate_implant_candidate,
    apply_implant_bone_support_heatmap, clear_implant_bone_support_heatmap,
)
from .migration import migrate_scene_compatibility

__all__ = [name for name in globals() if not name.startswith("_")]
