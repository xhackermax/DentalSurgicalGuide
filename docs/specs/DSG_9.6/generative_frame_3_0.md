# GenerativeFrame 3.0 — roadmap audit and implementation contract

**Audit:** 2026-10-11 · PR #1 `feature/generative-frame-3-geodesic-h0` · live branch CI; clinical main unchanged

**Status:** EXPERIMENTAL, not ready for clinical use or merger. This document is the project's **single roadmap/status contract**. The original goal remains unchanged: optimize **perimeter frame + reinforcement network together**, on anatomical geodesics, allowing controlled contact/penetration and using post-Boolean structural evidence.

Branch CI now contains a **real Blender 5.2.2 LTS** workflow with verified official download/SHA256, addon registration/unregistration, UI operator resolution and evaluated-mesh cross-section tests, **plus** portable Python tests/ZIP build. This does not prove real geodesic candidate generation, patient fitting, full Boolean/Undo/export or clinical suitability. No H0-H7 stage is declared complete until all its acceptance gates pass.

## Nonnegotiable invariants

1. Frame and reinforcements follow the **same authorized anatomical surface corridor**, through user anchors in order. Reuse `frame_surface_corridor.weighted_route`; no free-space Euclidean shortcut and no second independent routing engine.
2. Contact is intentional: a *controlled* portion of tubes intersects the passive/blockout model to provide seating/contact after Boolean subtraction. Both insufficient contact and excessive loss of retained structure are invalid.
3. A measured guide after Boolean is the geometric authority. Pre-Boolean circular tube inertia `I=πr⁴/4` and polar inertia `J=πr⁴/2` are not automatically properties of trimmed or merged solids.
4. Hard keep-outs cover **SLEEVE_LUMEN, DRILL_PATH, IRRIGATION_CHANNEL, LATERAL_OPENING, FRANGIBLE_WALL**, plus insertion-path constraints and minimum fabricated wall requirements. Check the entire swept tube volume, not centerline only. Valid connections into the sleeve's *solid outer wall* are not equivalent to forbidden lumen penetration.
5. Patient/clinical guide objects are never replaced by unvalidated experimental candidate or viewport preview geometry. Every potentially destructive transition is atomic with rollback, Undo and repeated-run tests.
6. Print material, build orientation, processing, loads and contact support assumptions remain uncalibrated until measured. Engineering metrics are **research aids**, not patient safety approval.

## H0-H7 verified status at audit

| Stage | Status | Existing implementation | Missing acceptance gate |
|---|---|---|---|
| H0 — reproducibility/transaction | Partial; Blender smoke passing | Transactional candidate replacement and simulated rollback tests; real Blender 5.2.2 addon registration/unregistration/UI RNA and evaluated-mesh diagnostic smoke now on CI | Real Blender generation/Undo/redo/failure recovery, metadata idempotence and unchanged clinical export |
| H1 — unified surface geodesics | Partial | Shared underlying graph kernel; exact-face anchors in `frame_geodesic_paths`; original frame routes through its own Blender adapter | One *authoritative* route/smoothing/anchor/forbidden-mask contract for both frame and reinforcements. Test complex folds, occlusal/interproximal contours and sleeve exits |
| H2 — adaptive contact/penetration | Analytical prototype | `frame_contact_core`: local planar chord/contact, retained area, bending second moments, policy feasibility | Actually generate radius/depth-controlled tubes; validate inserted depth, residual geometry, fit and attachment transitions using final mesh; demonstrate nontrivial contact |
| H3 — post-Boolean section/clearance | Diagnostic prototype | `frame_boolean_section_core`, `frame_boolean_path_core`, `frame_swept_clearance_core`; single/multistation read-only final-mesh inspection | Automatically obtain **inside-solid** tracing paths for every generated member, sample actual post-Boolean sections, add all forbidden meshes and insertion clearance |
| H4 — structural FEM | Partial, perimeter now modeled | `frame_fem_core`, curved beam-chain discretization, **four-edge nonprunable geodesic perimeter** in experimental network and nominal volume/group-pruning candidates | P1-P4 are still fully clamped, so the loop cannot yet add realistic contact-supported stiffness; measured post-Boolean sections, junctions and bench-model calibration remain missing |
| H5 — joint topology/material objective | Partial prototype | `frame_geodesic_groups`: balanced whole-route deletion on nominal FEM; radii resizing separately | Real joint search across perimeter frame, path connectivity, reinforcement groups, beam diameter, embedding depth and manufacturability, with Pareto/baseline comparison |
| H6 — Blender application, UX and export | Pending | Experimental viewport/report tools, isolated from applied clinical guide | Transactional end-to-end generation → preview → validation → apply → Boolean → verify → STL/PDF/report/Undo; real Blender 5.2 automated/manual smoke |
| H7 — physical/clinical qualification | Pending | None claimed | Repeatable printed-guide fit, path of insertion, seating, dimensional control, fatigue/deflection, sleeve precision, retentive force and material-process evidence |

## Confirmed implementation gaps (prioritized)

### P0-1 — real Blender 5.2 integration and lifecycle tests
**Updated evidence:** `.github/workflows/blender-5.2-smoke.yml` now runs official SHA256-verified Blender 5.2.2 registration/unregistration, UI RNA resolution and evaluated mesh section profiles. The full guide generation, external SciPy backend and Undo/rollback paths are **still not tested in actual Blender**.

**Remedy:** add a headless Blender 5.2 job (registration, route/preview, finalize, export, undo, reset, repeated runs, cleanup) on synthetic arches and real anonymized IOS fixtures. Ensure production SciPy and NumPy fallback match analytical reference cases.

**Acceptance:** zero failed operators; unchanged established clinical outputs; rollback restores original objects; deterministic output across repeated runs; no dangling previews or orphan meshes.

### P0-2 — protect sleeve lumen without forbidding every legitimate sleeve connection
**Updated evidence:** `frame_sleeve_junction_core.preflight_sleeve_junction` now checks all non-target sleeve lumens along the full swept tube and the target lumen upstream, allowing only a **bounded outer-wall terminal weld** (at most 2.5 mm) as a provisional candidate. Accepted candidates explicitly retain `final_lumen_clear=False` and require final Boolean lumen validation. Full residual lumen/wall/drill tests have **not** yet been built.

**Remedy:** distinguish valid connector-to-outer-sleeve union (including smoothly tapered ends) from the **actual lumen void**. Validate the lumen on the final union/Boolean mesh; reject solid obstruction and insufficient sleeve wall, not every temporary pre-Boolean volume intersection. Add clinical sleeve-radius cases and all four cardinal attachments, including multi-sleeve cases.

**Acceptance:** bona fide exterior welds survive, no residual lumen obstruction; final real wall thickness and drill access measured; illegal through-lumen paths fail.

### P0-3 — perimeter frame absent from the experimental FEM network
**Updated evidence:** `_fem_build_geodesic_model` now adds all four geodesic perimeter paths through the same face-anchor router and keeps them fixed in each experimental group-pruning solve; perimeter material is counted in nominal beam volume. **P1–P4 remain fixed in all 6 DOF**: support assumptions do not reproduce actual retention/compliance, and perimeter contribution to actual deflection is uncalibrated.

**Remedy:** discretize the existing frame loop with shared geodesic station IDs and junction continuity, model contacts as physically justified (not four blanket clamped points), retain cross-member attachment identity. Validate against reference assembled meshes.

**Acceptance:** frame alone and frame+reinforcements yield distinct, defensible stiffness and total volume. A reinforcement removal may never eliminate the last viable connectivity branch.

### P0-4 — post-Boolean measurements not attached to the experimental candidate
**Evidence:** `dsg.inspect_final_boolean_path` requires the user to select a separate **inside-solid POLY curve** on a previously finalized clinical guide. The experimental geodesic candidate is not merged with that guide. Thus these measurements do not currently validate the very candidate being optimized.

**Remedy:** perform candidate assembly and Boolean on a disposable work copy; derive/prove an interior trace automatically for each member, identify branch vs merged junction sections, sample true section and contact area, and map measurements back to stable candidate/beam identifiers.

**Acceptance:** every accepted candidate has traceable pre- and post-Boolean sections and contact metrics; a missing/inaccessible interior trace makes that candidate fail closed.

### P1-5 — complete forbidden swept volumes, surface masks and insertion
Existing swept checker only knows explicitly supplied spheres/cylinders; the Blender adapter passes sleeve-lumen cylinders. Add canal/drill shafts, irrigation channels, lateral windows, frangible walls and calibrated minimal distances using real mesh/BVH clearance. Keep intentional resting-surface overlap separate from forbidden through-model tunnels. Verify insertion-axis collisions and undercuts; demonstrate the guide can be placed/removed.

### P1-6 — optimized contact on real geometry
`frame_contact_core` selects an ideal shallowest planar penetration, but the Blender preview currently uses nominal surface centerlines and FEM radii; the chosen embedding depth is **not** applied to its actual geometry. Add bounded depth fields and smooth tapering, contact-patch estimation and Boolean feedback. Use no universal assumed clinical depth.

### P1-7 — post-Boolean FEM + beam-group continuity
The FEM still uses full circular sections for axial, bending and torsion. Do not simply replace `I` or `J` from a measured 2D cross-section while leaving merged junction kinematics unchanged. Introduce validated equivalent beam sections where slender-beam assumptions hold, and a higher-fidelity solid FEM fallback for junctions. Couple radius changes along whole curved members and ensure rendered taper matches solved geometry.

### P1-8 — joint optimization, reproducibility and runtime
Current geodesic mode disables topology growth and prunes only candidate reinforcements; the full objective `J=0.5 V/V0 + 0.5 C/C0` applies to nominal reinforcement elements, not the whole guide. Optimize discrete perimeter/connectivity choices plus continuous path, radius and penetration variables. Add constrained Pareto front, fallback to last feasible design, deterministic seeds, cap graph/FEM size, cache route/mesh features, compare real execution time and peak RAM with baseline.

### P2-9 — workflow/observability/spec synchronization
Keep one canonical planning file (this document). Separate labels `experimental`, `geometry measured`, `FEM validated`, `manufacturing qualified`. Reports must identify exact mesh checksum, Blender/DSG version, loads, material calibration, candidate ID, limits and all skipped/failed checks. No optional missing-region mask should be silently interpreted as "clear".

### P2-10 — physical and clinical design validation
Bench-test printed guides using the intended resin/printer/postcure; compare predicted and measured contact, deflection, fracture, fatigue, seating, removal force and sleeve position. Establish acceptance thresholds from device design inputs and risk analysis. No production clinical automation before this evidence and professional review.

## Practical PR sequence / dependencies

1. **PR-A · repair and prove P0-1/P0-2:** real Blender integration fixtures, correct allowable sleeve junction while forbidding actual lumen obstruction. **Gate:** real Blender passes, plus a valid one-sleeve and a valid multi-sleeve guide both route successfully.
2. **PR-B · P0-3:** include actual geodesic perimeter frame and non-ideal support conditions in coupled FEM. **Gate:** frame+reinforcement mechanical/volume measurements reconciled against reference assembly.
3. **PR-C · P0-4/P1-6:** transactional candidate Boolean, auto interior tracing, adaptively embedded geometry and post-Boolean sections. **Gate:** no ideal-circle phantom stiffness; valid contact and residual structure for all members.
4. **PR-D · P1-5/P1-7:** full swept clearance, insertion feasibility and calibrated effective beams or solid FEM near junctions. **Gate:** zero forbidden cut-path obstruction and stress/deflection benchmark within documented tolerance.
5. **PR-E · P1-8:** joint Pareto search of frame + reinforcement + contact + thickness. **Gate:** no worse than manually selected baseline across all hard constraints; measured volume/compliance objective improves if a feasible candidate exists, otherwise report no improvement.
6. **PR-F · H6/H7:** apply/undo/export workflow, measured prototyping and manufacturing evidence. **Gate:** Blender 5.2 clinical workflow and independent physical design-validation checklist pass.

## October 12 audit corrections

- `OPTIMIZAR FRAME` uses a **mandatory pre-staging swept-volume gate** for
  every rendered FEM candidate: mapped target-sleeve outer-wall provisional
  weld, complete non-target sleeve lumens, +/-20 mm **uncalibrated** drill
  approach corridors and all identifiable confirmed irrigation/microscrew
  Blender mesh BVHs at no more than 0.5 mm sampling. A missing BVH fails closed.
  The previous clinical scene remains unchanged on any preflight rejection.
- This gate is strictly **preBoolean**. It never labels a final lumen or
  physical fit clinically cleared. Missing other hard regions (lateral ports,
  frangible walls) or an uncalibrated drill depth means H3/H6 remain PENDING.
- Curved FEM members carry total route length for Euler buckling even when
  discretized to 1.5 mm; dense FEM refuses oversized matrices without SciPy.
  Contact boundary conditions at P1..P4 are still uncalibrated.
- Edentulous SIMPLE mode requires jaws 53/54 but no teeth; the worker/manifest
  separately preserve FULL dentition requirements. Immediate two-jaw composites
  rollback partially staged geometry.
- Build artifact now has an explicit GF3 experimental filename, a Blender
  warning and generated SHA-256 manifest of exact packaged files, retaining
  the original 9.10.11 provenance manifest independently.
- Additional failure/rollback/contract TDD; Blender 5.2.2 smoke now also
  constructs **one- and two-sleeve synthetic fused guides**, applies real
  Blender EXACT UNION and DIFFERENCE booleans, tests lumen/annular section
  topology and independent radial ray checks, verifies repeated deterministic
  runs and rejects an undrilled control model. Successful synthetic mesh tests
  **do not** substitute for complete DSG operator generation/Undo/export,
  anatomical drilling envelopes, fitting or clinical qualification.

## Next immediate development action

**Next:** the *isolated* one-/two-sleeve real Boolean and lumen checks now pass. Extend these fixtures to execute the **actual DSG** full flow (support P1–P4, frame build, sleeves, reinforcement preparation, drilling, final-cut operator, export and Ctrl+Z/rollback), first using synthetic dental arches and then independent anonymized data. Require a postBoolean lumen/wall check on the disposable candidate before a clinical transition and calibrated non-clamped contact boundary conditions. Do not claim mechanical improvement solely from adding frame volume.

## Notes

- Numeric defaults in FEM and contact dialogs are software fixtures, not evidence-based clinical limits.
- Source evidence: `dsg/frame_structural.py` (`_fem_build_model`, `_fem_build_geodesic_model`, preview/apply); `dsg/frame_fem_core.py`; `dsg/frame_contact_core.py`; `dsg/frame_geodesic_groups.py`; `dsg/frame_boolean_path_core.py`; `dsg/frame_swept_clearance_core.py`; `.github/workflows/ci.yml`; `AGENTS.md`.

## 2026-10-11 implementation evidence and strict limitations
- **Blender real CI:** `.github/workflows/blender-5.2-smoke.yml` downloads
  official **Blender 5.2.2 LTS** and checks the upstream SHA256.
  `tools/blender_smoke.py` covers addon registration/unregistration (twice)
  and the entire UI-operator reference surface. `tools/generative_frame_blender_smoke.py`
  inspects actual registered experimental operator RNA properties and a
  real evaluated Blender cube's geometric sections, without scene mutation.
- **Sleeve preflight:** `frame_sleeve_junction_core.py` replaces the
  blanket "tube must not touch even its target sleeve" preBoolean rejection:
  non-target lumens remain forbidden on the whole tube; target lumen remains
  protected outside the explicit terminal outer-wall weld segment.
  No result ever reports final lumen clear without a postBoolean geometry test.
- **Perimeter network:** `frame_perimeter_fem.py` appends all four frame edges
  atomically as locked/nonprunable geodesic FEM chains. The whole nominal
  perimeter volume stays in the group's balanced comparison. Group removal
  can never delete only a portion of the perimeter.
- **Not yet structural validation:** support P1–P4 remain artificially fixed.
  The loop adds real *accounting* of nominal frame material, but not a
  clinically meaningful change in measured stiffness until contact boundary
  conditions are calibrated. Nominal tube radii are not the final solid's
  postBoolean properties.
- **Next build gate:** real one- and two-sleeve end-to-end Blender assemblies,
  final clear lumen + wall + drilling path checks, Undo/rollback and variable
  contact-supported FEM comparison to reference deflections.

## 2026-10-12 synthetic Blender Boolean evidence

- **Actual Blender 5.2.2 test CI (not mock):** `tools/generative_frame_boolean_junction_smoke.py`
  builds one/two sleeve shell unions and reinforcement attachments, performs
  the actual final cylindrical bore Boolean, and checks multi-station retained
  cross-section topology. Expected void probes fail as void, while annular
  material points remain inside the measured solid.
- A second fixture `tools/generative_frame_boolean_blender_smoke.py`
  uses independent 24-angle radial probes at five axial stations per sleeve,
  repeats each one/two sleeve construction and rejects an undrilled negative
  control. Ray positions must be transformed to Blender object-local space;
  numerical rays lying exactly on tessellation seams require robust sampling.
- **Passing baseline:** commit `8f2bbfc72f327b47aceb7d21fa25b5edb8ac2c18`,
  GitHub Actions `38248992840` (Blender) and `38248993025` (portable/ZIP).
- This is a **synthetic research-gate milestone, not H6/H7 completion**.
  Remaining blockers include actual DSG operator-to-operator run, final
  Boolean on the actual candidate, rollback/Undo of patient-scene transitions,
  verified drilling and lateral/irrigation keep-outs, calibrated limits,
  non-clamped FEM support/contact and physical validation.
