DSG — optional offline engine payload
=====================================

Normal installs do NOT need anything here: DSG downloads the prebuilt engine
listed in engines/manifest-v2.json (GitHub Release + Google Drive mirrors), or
builds it with uv as a last resort. See docs/INSTALACION_MOTORES_9_7_3.md.

For machines without Internet you may ship a "full offline" add-on ZIP. Put the
three archives below (see OFFLINE_PAYLOAD_MANIFEST.json) and fill the manifest
with tools/build_offline_bundle.py:

- payload/runtime/runtime_win64_py313_cuda_totalseg218.zip  (site-packages)
- payload/weights/Dataset113_ToothFairy3.zip
- payload/weights/Dataset115_mandible.zip

The installer verifies every SHA-256 and extracts them once into the user's
runtime folder (outside the add-on), so later add-on updates reuse it.

DSG RUNTIME GOVERNANCE NOTICE: default installation is DENTAL/MAXILLOFACIAL
only (AGENTS.md, docs/specs/DSG_9.6/runtime_scope.md).
