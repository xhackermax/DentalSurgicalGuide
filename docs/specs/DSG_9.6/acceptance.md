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

## Release import 9.10.11 (2026-10-08)

The source ZIP is authoritative for this version. Current acceptance commands
are documented in `docs/VERIFICACION_9_10_11.md`: `tools/run_checks.py --no-smoke`
checks original-package/source identity, compilation, the 20 current pure tests,
metrics and codemap freshness. `--blender PATH --vtk-site-packages PATH` adds real
Blender 5.2 model-free ZIP/registration/geometry/history/diagnostic checks.

The former `tests/` suite is preserved as historical 9.7 coverage, with five
collection errors caused by removed modules. Migrating its applicable behavior
checks is pending; these are not counted as passing. The old `bpy==5.2.2` CI
installation is superseded by portable gates because that wheel is unavailable
in the consulted index. Real-model inference and a full clinical walkthrough
remain separate acceptance evidence and are not claimed for this import.
