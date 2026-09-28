# DSG 9.5.8 refactor architecture

## Why the split is namespace-preserving first

`guide_module.py` had reached 50,403 lines. Moving thousands of Blender classes,
callbacks and helpers directly into independent modules would change import
order, `__module__`, circular dependencies and registration behavior at the same
time. That is too many variables for a clinical Blender addon with little bpy
integration coverage.

9.5.8 therefore separates **physical source ownership** from **runtime namespace
ownership**. `source_parts.exec_source_parts()` executes ordered files using the
facade module's globals. A function stored in `_guide_parts/06_irrigation_a.py`
still belongs at runtime to `dsg.guide_module`.

This gives immediate editing/review benefits while keeping the compatibility
surface narrow. Once Blender integration tests exist, individual domains can be
promoted from source fragments to real Python modules one by one.

## Guide source map

- `00_bootstrap_constants_assets_*`: imports, constants, embedded/template assets.
- `01_workflow_state_mpr_objects_*`: workflow state, checkpoints, MPR/object helpers.
- `02_implant_animation_geometry_*`: implant/drill/animation and related geometry.
- `03_blockout_frame_geometry_*`: blockout/frame/clearance and shared geometry.
- `04_properties_clinical_operators`: scene properties and clinical operators.
- `05_frame_microscrews_sleeves_drill`: frame, microscrew, sleeve and drill stage.
- `06_irrigation_*`: irrigation geometry, interaction and final application.
- `07_reinforcement_animation`: reinforcement and sequential animation.
- `08_export_final_ui_registration`: export, final-cut UI and registration lifecycle.

## DICOM source map

The DICOM monolith was itself generated from named modules, so 9.5.8 restores
those editing boundaries as ordered fragments: constants/runtime/dependencies,
utils+I/O, volume/MPR/scene, updates+segmentation, hybrid surfaces, realtime MPR,
operators and panels/registration.

## TotalSegmentator single-source cleanup

The compatibility labelmap now carries every active 9.5.x class needed by CPU
postprocessing. A second semantic volume and three support crops were artifacts
of the previous multi-model architecture and had no active consumer.

The mandibular-canal 0.65 mm closing remains because it changes useful geometry.
Only the fictitious cross-model verification semantics were removed.
