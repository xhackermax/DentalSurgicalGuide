# DSG 9.1.7 · Mixar Agent Runtime

## Goal

Make Mixar a fast in-process planning/orchestration client for DSG without
turning arbitrary generated Python into the clinical authority of the addon.
MCP remains supported as an external protocol; both paths reuse the same DSG
operation implementation.

## Implemented

- `agent_core.py`: closed, testable capability registry. Unknown operations deny
  by default. Clinical confirmation, generic `execute_step`, final Boolean and
  export are absent.
- `agent_facade.py`: direct main-thread in-process dispatcher for Mixar; no local
  TCP round-trip. Mutation calls require stable `operation_id` values and are
  journaled in the scene before geometry work.
- `agent_scene_graph.py`: lazy semantic DSG object graph with depsgraph-driven
  invalidation. It is context, never the authority for exact distances.
- Local operation journal: committed replay, conflict detection, stale-running
  detection after Blender restart, and failure records that warn about possible
  partial mutation.
- Mixar agent-origin deny gate: current clinical/final UI operators reject while
  Mixar's official `agent_execution_context` is active.
- Implant-tooth confirmation: replaced approximate hard gating with a
  triangle-triangle exact verifier that fails closed when incomplete.
- Catalog-diameter evaluation: FAST/FULL_VERTEX/EXACT modes; removed the legacy
  permissive `+0.02 mm` clearance tolerance.
- `roadmap_module._dispatch_operation`: one internal operation owner reused by
  localhost MCP and the local Agent Facade.
- DSG version metadata consolidated to 9.1.7 in active bootstrap/guide module.

## Deliberately not implemented / not falsely claimed

- `propose_frame_reinforcements()` still proposes only. It does not create,
  validate, Boolean-union or re-analyze reinforcement geometry.
- No generic rollback engine exists for arbitrary Blender mutations.
- No claim that Blender Python is a secure hostile-code sandbox.
- No claim that a missing Mixar agent marker proves a human clicked a button.
- No Blender runtime test was possible in this build environment.
