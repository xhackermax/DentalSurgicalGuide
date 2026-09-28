# DSG 9.1.8 – Mixar/Blender _RestrictData install hotfix

## Fixed
- `cbct_dental_module.register()` no longer calls `migrate_existing_asset_metadata()` while Blender is enabling the add-on.
- The metadata migration now runs from `cbct_dental_module.deferred_post_register()` only after `bpy.data.objects` and `bpy.data.scenes` are available.
- Top-level DSG deferred initialization waits for CBCT, DICOM, and Guide deferred initialization before completing.

## Why
Mixar 3.3 / Blender 5.0 can expose `bpy.data` as `_RestrictData` during `addon_enable`. Accessing `bpy.data.objects` from `register()` raises:
`'_RestrictData' object has no attribute 'objects'`.

The migration remains enabled and idempotent for existing scenes; only its timing changed.
