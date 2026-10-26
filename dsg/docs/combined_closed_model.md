# Crear modelo cerrado

The model preparation panel exposes one `dsg.close_model_base` action. It first
runs the existing `dsg.close_scan_holes` operator when the model is open and has
not been reviewed. On success it obtains `props.model_obj` again, because hole
repair may have produced a new anatomy-locked copy, then performs every existing
base creation, acceptance, cache invalidation and workflow update.

Failed hole review stops base creation. Previously reviewed holes and already
closed inputs skip unnecessary repair. Both existing geometry implementations,
original IOS preservation, native undo and phase progress remain in use. The
standalone repair operator remains registered for compatibility.

Verification: six Blender 5.2 regression cases (order with real geometry,
skip reviewed input, failure short circuit, single UI action, registered panel dispatch and assistant phase), the existing scan
hole preservation/progress test, and a real 142326-vertex IOS copy. The clinical
copy produced a 216790-vertex manifold model with zero boundary/branch/wire edges
and an unchanged source. Low automatic direction confidence remains the existing
operator warning, and this change does not alter the geometry algorithms.

The unrelated existing tooth socket test fails at ios_save_tooth_selection with
"Selecciona solo el diente; no todo el IOS" on both the installed baseline and
the patched source. This is not an introduced regression.
