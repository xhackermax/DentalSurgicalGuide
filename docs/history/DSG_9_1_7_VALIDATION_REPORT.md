# DSG 9.1.7 validation report

Validation in this environment is split explicitly by execution capability.

## Executed outside Blender

- Pure DSG/NumPy tests: exact mesh-distance kernel, agent policy/journal
  primitives, clinical core, evidence core and structural-precheck core.
- CaseEngine tests are executed separately in its package.
- Mixar AST-policy tests are executed separately in the Mixar overlay package.

The exact-distance tests include triangle intersection, coplanar containment,
an edge-edge closest-point case where vertex-only sampling is insufficient,
candidate-budget fail-closed behavior, and randomized comparison of the AABB
broadphase result against brute-force all triangle pairs.

## Syntax/static validation

Blender-dependent modules are compiled with CPython syntax checks. A static
operator audit verifies that every current `dsg.confirm_*` plus clinical review,
final Boolean, reinforcement commit, engraving commit and STL export is covered
by the Mixar-agent deny policy.

## Not executable here

No Blender 5.x / `bpy` / Mixar binary is installed in the sandbox. Therefore
scene mutation, depsgraph behavior, exact clearance on real CBCT meshes,
operator UI gates, WebSocket delivery and real Mixar bootstrap registration are
not claimed as runtime-tested.

Use `tests_blender/agent_runtime_smoke.py` inside Blender/Mixar before promoting
9.1.7 to a clinical workstation.

## Final build counts

- Pure DSG tests: **23/23 passed**.
- Mixar AST defence-in-depth tests: **6/6 passed**.
- MCP CaseEngine 2.6 tests: **16/16 passed**.
- Static Mixar-agent deny coverage: **18/18 current critical/final operators**.
- Changed runtime modules: CPython syntax check **PASS**.
- Mixar overlay installer: dry-run/install/reinstall idempotency smoke **PASS**.
