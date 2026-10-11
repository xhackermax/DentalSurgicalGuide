# DSG GenerativeFrame 3.0: development contract (H0-H1)

Status: EXPERIMENTAL. No clinical approval or material/load calibration is implied.
Applies to Blender 5.2; baseline main commit 1bf193b (DSG 9.10.11).

## Product objective
Optimize the **frame and reinforcement network together**, balancing normalized
post-Boolean volume and mechanical compliance. No weighted score may override
clinical, fabrication, geometric, or structural hard constraints.

## Surface routing invariant
1. Frame and reinforcement candidates use the same intrinsic surface graph and
   existing `frame_surface_corridor` engine. The pure vertex-route contract is
   implemented in `dsg/frame_geodesic_paths.py`.
2. Paths may use only real mesh-surface adjacency. Euclidean proximity does not
   establish connectivity; never traverse through the passive/blockout solid.
3. Excluded vertices, including endpoints, must remain excluded.
4. No silent straight-line fallback when a surface corridor is disconnected.
   Emit `NO_VALID_SURFACE_ROUTE` and leave existing geometry untouched.
5. Smooth paths must remain surface-constrained. Transitions to sleeve envelopes
   are distinct 3D entities requiring volume-clearance verification.
6. Face/barycentric anchors, complete swept-volume collision checks, and the
   FEM beam-polyline discretization are follow-up milestones, **not delivered
   by the H1 pure vertex-route primitive**.

## Contact and structure (future H2-H5)
Penetration is optimized for verified support/contact area *and* adequate
post-Boolean resistant cross-sections. Never assume that maximizing overlap
alone establishes retention, or that nominal circular beam properties remain
valid after material is removed by Boolean operations.

## H0 transactional invariant
For `create_fem_reinforcements`, solve and build every replacement candidate
before retiring prior confirmed FEM objects. On candidate failure, remove only
temporary geometry and preserve the previous confirmed set and guide metadata.
Confirmed manual reinforcements cannot be overwritten.

## Acceptance to advance
- Pure tests exercise disconnected folds, excluded endpoints, determinism and
  invalid graph edges.
- Blender regression: solver failure and staging failure preserve prior geometry;
  successful reruns leave only the new confirmed set.
- Blender 5.2 install/register, operator audit, export validation and Ctrl+Z
  must pass before claiming completion.
- Legacy clinical workflows and STEP_FRAME behavior remain unchanged until
  the curved paths have separate post-Boolean and structural validation.
