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

## H4/H5 prototype: balanced, whole-route FEM group pruning
- `frame_geodesic_groups.py` reruns FEM for each **complete curved route**
  proposed for deletion. It removes orphaned FEM nodes from each trial so that
  a removed chain cannot leave artificial singular 6-DOF systems.
- Accept only group deletions that pass all nominal FEM hard and recommended
  limits and lower `0.5*(V/V0)+0.5*(compliance/C0)`.
- Evaluate loads and monitoring points on the compact graph; invalid/
  disconnected loading fails closed. Do not mutate live FEM input or Blender.
- `dsg.analyze_geodesic_groups` is a read-only experimental operator; it
  reports topology recommendations but **never applies** an optimized guide.
- Results remain based on nominal circular beams, not the real Boolean solid.
  Full-frame topology and contact-calibrated FEM are still pending.

## H3: actual post-Boolean section measurement (experimental diagnostic)
- `dsg/frame_boolean_section_core.py` slices a closed triangular mesh at an
  arbitrary section plane and computes cross-sectional area, centroid, principal
  bending moments of inertia, distinct components and nested material voids.
- Fail closed on open/nonmanifold contour, ambiguous coplanar intersections,
  probe outside actual solid, probe in a hole or an unboundedly large mesh.
- `inspect_final_boolean_guide_section()` accepts **only** a DSG guide with
  `DSG_final_cut_completed`, and uses the existing `guide_export.blender_adapter.mesh_arrays`
  to inspect Blender's evaluated, world-coordinate geometry.
- The optional final-export-stage button measures a plane through the 3D cursor;
  the cursor must be **inside the material**, and the plane normal must match
  the direction of the region being evaluated.
- This is a **single human-requested section**, not sampled full-guide FEM,
  and never auto-approves exported STL or modifies the final guide.
- Physical retentive performance, insertion safety, anisotropic resin,
  torsional constants and globally connected-frame behavior remain unverified.

## H3 reference comparison
- The final-guide section inspector accepts an optional **user-specified**
  nominal circular beam diameter. It reports `A_actual/A_circle` and
  `I_min_actual/I_circle` as geometry-only diagnostic ratios.
- These ratios do **not** calibrate Saint-Venant torsion, local buckling,
  bonding to anatomy, placement fit, resin fatigue or true contact retention.
- The section may include multiple merged mesh features. Never treat the
  ratio as an isolated bar's beam stiffness or an automatic acceptance gate.
- To measure an anatomical region, put the Blender 3D cursor **inside**
  the final guide material, align the plane normal with the local tangent,
  and use the step-11 research section-inspection button. A cursor on the
  section boundary, inside a hole, or outside the mesh produces a failure.
