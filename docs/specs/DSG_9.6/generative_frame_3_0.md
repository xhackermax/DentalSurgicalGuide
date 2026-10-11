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
6. Exact triangle-face anchors are supported in the new shared geodesic
   wrapper. A curved route can be discretized into nonprunable FEM elements,
   with no automatic chord replacement.
7. The experimental `dsg.analyze_geodesic_frame_fem` command computes a
   read-only surface-constrained candidate FEM model. The separate
   `dsg.preview_geodesic_frame_fem` command renders viewport-only
   variable-radius preview curves directly from the same FEM beam chain.
8. Both features are deliberately **not** used by the clinical frame/refinement
   apply/export pipeline. No post-Boolean structural/contact validation exists.
9. Complete swept-volume collision checks, empirically defined penetration,
   contact/retention metrics, group-aware route pruning and load calibration
   remain subsequent milestones.

## Contact and structure (future H2-H5)
Penetration is optimized for verified support/contact area *and* adequate
post-Boolean resistant cross-sections. Never assume that maximizing overlap
alone establishes retention, or that nominal circular beam properties remain
valid after material is removed by Boolean operations.

## Limitations of the current experimental surface adapter
- It starts from existing support-to-sleeve candidate identities, without
  optimizing the perimeter frame or the global topological connectivity.
- Sleeve transitions are explicitly checked with current keep-out helpers;
  the geometry still needs an independent full swept-volume and insertion
  clearance validator.
- The FEM still treats nominal circular cross-sections, not post-Boolean
  material sections. Its ratings cannot be interpreted as clinical safety.
- Large graph paths are bounded; if the full geometric FEM is too large,
  fail with an actionable message rather than silently straightening.
- The experimental Blender preview is hidden from rendering and excluded
  from DSG's confirmed reinforcement role; the original clinical guide
  is never replaced by it.

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

## H2 local-planar contact estimates (research only)
- `dsg/frame_contact_core.py` computes interface chord width, residual area,
  centroid, and bending second moments after an ideal local plane section.
  It does not claim torsional stiffness of the cropped shape.
- `select_contact_section` minimizes penetration subject to **explicit**
  contact, remaining-section, and maximum-overlap requirements; impossible
  constraints fail closed.
- `frame_structural.estimate_geodesic_frame_contact` reports provisional
  results from surface-projected FEM samples and current optimized beam radii,
  without modifying Blender guide geometry.
- The optional `dsg.estimate_geodesic_contact` dialog is research-only.
  Numeric defaults are software fixtures, not clinically validated limits.
- **Pending H3:** real post-Boolean volume/section measurement, insertion
  clearance, undercuts, contact/retention tests, materials and loads calibration.
