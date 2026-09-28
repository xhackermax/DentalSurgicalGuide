# DSG 9.5.8 transitional namespace-preserving source split.
# Public API remains identical to the historical monolith.
from .source_parts import exec_source_parts as _exec_source_parts

_PARTS = (
    '00_bootstrap_constants_assets_a.py',
    '00_bootstrap_constants_assets_b.py',
    '01_workflow_state_mpr_objects_a.py',
    '01_workflow_state_mpr_objects_b.py',
    '02_implant_animation_geometry_a.py',
    '02_implant_animation_geometry_b.py',
    '02_implant_animation_geometry_c.py',
    '03_blockout_frame_geometry_a.py',
    '03_blockout_frame_geometry_b.py',
    '03_blockout_frame_geometry_c.py',
    '04_properties_clinical_operators.py',
    '05_frame_microscrews_sleeves_drill.py',
    '06_irrigation_a.py',
    '06_irrigation_b.py',
    '06_irrigation_c_sequential.py',
    '06_irrigation_d_frangible.py',
    '07_reinforcement_animation.py',
    '08_export_final_ui_registration.py',
)
_exec_source_parts(globals(), __file__, '_guide_parts', _PARTS)
del _exec_source_parts, _PARTS
