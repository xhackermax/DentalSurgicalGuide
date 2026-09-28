# DSG 9.6 — Acceptance gates

A build is not stable until applicable gates pass.

- Python `compileall`: PASS
- Unit tests: PASS
- Manifest/contract tests: PASS
- Route tests: PASS
- UI operator audit: `DEAD_BUTTONS = 0`
- Runtime scope audit: default profile contains no unrelated whole-body model assets
- ZIP integrity: PASS
- Blender 5.2 real smoke test: PASS
- Long operations expose progress/activity and actionable failure
- SIMPLE_ARCHES remains materially lighter than FDI
- Runtime/model assets are not redownloaded unnecessarily across addon-only updates

## Automation (9.7.0)

`python tools/run_checks.py` executes compileall, ruff correctness rules, the
pytest suite (including `DEAD_BUTTONS = 0`, version SSOT and regression tests),
the Blender smoke test and the ZIP install test (legacy add-on + Extension).
CI runs the same command with `bpy==5.2.2`. The manual Blender 5.2 clinical
walkthrough (DICOM → alignment → guide → export) is still required.
