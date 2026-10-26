# Simple arch finishing parity

SIMPLE review reconstructs the two existing arch masks with the same
`ITK_ANTIALIAS_MODEL_GRID_1` implementation used by immediate-route teeth:
verified model grid, ITK binary antialiasing, half-model-voxel surface extraction,
volume adjustment and distance/closed-mesh acceptance gates.

Arch policy retains internal cavity shells and small surface components. It
never fills bone cavities or creates individual FDI objects or tooth workers.
Existing normalized prediction classes are merged into two binary masks, with
no new inference. Missing source masks produce an actionable error.

Original meshes and alignment references are retained. Earlier VISUAL-only
finishes remain upgradeable. Source/current-case signatures and transform gates
continue to invalidate stale results. DICOM import retains the current prediction
for finishing and persists it for later use.

Validation: synthetic hollow multi-component arch, unchanged immediate tooth
geometry, Blender 5.2 route/operator/rollback tests, and real two-arch CBCT worker
validation. Geometric acceptance does not constitute clinical validation.
