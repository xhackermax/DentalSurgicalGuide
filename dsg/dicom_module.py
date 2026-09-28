"""DICOM Wizard Pro 5.x v1.13.0 - in-process CBCT AI, UniversalLab tooth instances/FDI and optimized surfaces.

Generated from the modular DICOM Wizard Pro package; DSG 9.5.8 now loads the
source in ordered fragments while preserving the historical module namespace.
"""
# DSG 9.5.8 transitional namespace-preserving source split.
# Public API remains identical to the historical monolith.
from .source_parts import exec_source_parts as _exec_source_parts

_PARTS = (
    '00_constants_runtime_dependencies.py',
    '01_utils_dicom_io.py',
    '02_volume_mpr_scene.py',
    '03_updates_segmentation.py',
    '04_hybrid_surface_preview.py',
    '05_realtime_mpr.py',
    '06_operators_a.py',
    '06_operators_b.py',
    '07_panels_registration.py',
)
_exec_source_parts(
    globals(), __file__, '_dicom_parts', _PARTS, future_annotations=True
)
del _exec_source_parts, _PARTS
