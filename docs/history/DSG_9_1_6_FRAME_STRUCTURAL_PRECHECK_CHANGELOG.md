# DSG 9.1.6 · Frame Structural Precheck + historical integration audit

This revision reconciles the historical requirements supplied by the architect with the current DSG 9.1.5 / Mapper 0.4.1 / CaseEngine 2.4 line.

## Confirmed already present (not duplicated)
- Mapper BVH vectorization and cache reuse.
- depsgraph geometry invalidation + `session_uid` cache identities.
- DSG-installed dental asset contract is authoritative; previous hashes/legacy landmark aliases remain migration-only.
- `CROWN_TEMPLATE → CROWN_GHOST → TOOTH` coronal mapping; `TOOTH_TEMPLATE` remains optional/full-tooth CBCT reference.
- CBCT density sampling and implant Bone Support/heatmap are native DSG services, not the old standalone `dsg_ext` duplicate sampler.
- CaseEngine server-side gates/versioning/idempotency/jobs/channel/permissions and later hardening remain intact.
- Clinical context, country-aware guidance requests, offline Evidence Engine and implant-tooth safety/diameter analysis remain intact.

## New in 9.1.6
- `frame_structural_core.py`: pure Python geometric structural proxy, unit-testable outside Blender.
- `frame_structural.py`: Blender adapter reusing DSG's existing geodesic graph, width-preserving Dijkstra routing, sleeve geometry and local wall-thickness probes.
- `dsg.generative_frame.v1` contract resource.
- Semantic support-node persistence for exactly P1/P2/P3/P4.
- Structural context with sleeve load nodes and hard keep-out vocabulary.
- Geodesic span analysis for P1-P2, P2-P3, P3-P4, P4-P1.
- Relative structural-need ranking combining span/diameter, distance to sleeve envelope and measured local thickness.
- No invented pass/fail limits. User/MCP thresholds are applied only when explicitly supplied.
- Single-sleeve primary topology invariant: `P1→S←P3` and `P2→S←P4`; direct P1→P3 and P2→P4 diagonals are forbidden.
- Every proposed branch terminates on the sleeve structural envelope and is explicitly checked against the finite sleeve lumen. Intersections are rejected.
- Adaptive candidates can originate from the highest-ranked long/remote peripheral spans and terminate at the nearest sleeve envelope.
- Catmull-Rom is documented as a smoothing/interpolation mechanism only; it never decides structural topology.
- Multi-sleeve figure-eight/chained solutions are exposed as a future/candidate topology and are deliberately not silently selected in this revision.

## Deliberate non-claim
This is **not finite-element analysis**. No stress, strain, displacement or factor of safety is claimed. It is a deterministic geometric precheck intended to tell MCP where to investigate/reinforce first and to provide structured inputs for future FEA/topology optimization.

## Runtime validation limitation
No Blender/bpy executable is available in the build sandbox. Blender-dependent code is syntax-checked only. `frame_structural_core.py` is executed with real unit tests.
