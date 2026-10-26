# Blender 5.2 compatibility

DSG 9.10.1 targets Blender 5.2 exclusively.

- `bl_info["blender"]` is 5.2.0.
- Runtime creation is scoped to Blender 5.2's current user scripts directory.
- No runtime, Python environment, model directory or add-on installation is adopted from older Blender versions.
- Heavy neural inference runs in an external worker instead of Blender's UI thread.
