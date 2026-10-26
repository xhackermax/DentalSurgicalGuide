"""Capability-based local agent facade for DSG.

The facade is the only supported in-process entry point for generic 3D agents
such as Mixar.  It deliberately exposes a closed set of planning/query tools
and omits clinical confirmations, final destructive operations and export.

Security note: Blender Python is not a hostile-code sandbox.  A process with
arbitrary bpy execution can ultimately mutate Blender data.  This facade is a
capability boundary for cooperative agents and auditability; clinical safety
continues to be enforced by DSG's own confirmation gates and exact geometry
validators.
"""
from __future__ import annotations

from datetime import datetime, timezone
import copy
import hashlib
import json
import threading
import uuid
from typing import Any

import bpy

from . import agent_core, agent_scene_graph

FACADE_SCHEMA = "dsg.agent_facade.v1"
RESULT_SCHEMA = "dsg.agent_tool_result.v1"
JOURNAL_KEY = "DSG_agent_operation_journal_json"
JOURNAL_MAX_ENTRIES = 128
JOURNAL_RESULT_MAX_BYTES = 120_000
_RUNTIME_INSTANCE_ID = uuid.uuid4().hex

# Bridge operations that deliberately require an explicit write capability.
_INJECT_FLAGS = {
    "map_patient_tooth": {"allow_mapping_write": True},
    "fit_crown_to_neighbors": {"allow_geometry_write": True},
    "fit_occlusion": {"allow_geometry_write": True},
    "prepare_implant_axis_from_prosthetic_context": {"allow_geometry_write": True},
    "apply_implant_bone_support_heatmap": {"allow_visualization_write": True},
    "clear_implant_bone_support_heatmap": {"allow_visualization_write": True},
    "set_frame_support_nodes": {"allow_geometry_write": True},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _require_main_thread() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            "DSG Agent Facade must run on Blender's main thread. Queue the request "
            "through Mixar main_thread_executor or the DSG MCP bridge."
        )


def _scene(scene=None):
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        raise RuntimeError("No active Blender scene")
    return scene


def _load_journal(scene) -> list[dict[str, Any]]:
    raw = str(scene.get(JOURNAL_KEY, "") or "")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_journal(scene, entries: list[dict[str, Any]]) -> None:
    compact = entries[-JOURNAL_MAX_ENTRIES:]
    scene[JOURNAL_KEY] = json.dumps(compact, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _serializable_result(value: Any) -> tuple[Any | None, str, int]:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    size = len(raw.encode("utf-8"))
    if size <= JOURNAL_RESULT_MAX_BYTES:
        return json.loads(raw), digest, size
    return None, digest, size


def _bridge_module():
    # Lazy import avoids an import cycle during DSG bootstrap.
    from . import roadmap_module
    return roadmap_module


def get_capabilities(scene=None) -> dict[str, Any]:
    scene = _scene(scene)
    manifest = agent_core.capability_manifest()
    manifest.update({
        "facade_schema": FACADE_SCHEMA,
        "dsg_version": "9.1.7",
        "scene_graph": agent_scene_graph.get_scene_graph_summary(scene),
        "execution": {
            "in_process": "BLENDER_MAIN_THREAD_DIRECT",
            "external": "DSG_MCP_LOCALHOST_BRIDGE",
            "operation_journal": "SCENE_PERSISTENT_BOUNDED_JSON",
        },
        "safety": {
            "clinical_confirmations_exposed": False,
            "generic_execute_step_exposed": False,
            "arbitrary_dsg_operator_dispatch_exposed": False,
            "blender_python_is_not_security_sandbox": True,
        },
    })
    return manifest


def get_operation_history(scene=None, limit: int = 50) -> dict[str, Any]:
    scene = _scene(scene)
    entries = _load_journal(scene)
    limit = max(1, min(int(limit or 50), JOURNAL_MAX_ENTRIES))
    return {
        "schema": "dsg.agent_operation_history.v1",
        "count": len(entries),
        "entries": entries[-limit:],
    }


def get_operation_status(operation_id: str, scene=None) -> dict[str, Any]:
    scene = _scene(scene)
    row = agent_core.find_journal_entry(_load_journal(scene), str(operation_id or ""))
    stale_running = bool(
        row is not None
        and str(row.get("status", "")) == "RUNNING"
        and str(row.get("runtime_instance_id", "") or "") != _RUNTIME_INSTANCE_ID
    )
    return {
        "schema": "dsg.agent_operation_status.v1",
        "operation_id": str(operation_id or ""),
        "found": row is not None,
        "stale_running_from_previous_runtime": stale_running,
        "entry": row,
    }


def _prepare_args(spec: agent_core.AgentToolSpec, params: dict[str, Any]) -> dict[str, Any]:
    args = copy.deepcopy(params or {})
    # The facade, not the model, grants the narrow write flag implied by the
    # registered capability. A caller cannot turn an unlisted bridge op into a
    # write by inventing allow_* flags because it never chooses bridge_op.
    for key, value in _INJECT_FLAGS.get(spec.bridge_op, {}).items():
        args[key] = value
    # FAST is appropriate for interactive agent ranking; hard confirmation is
    # independently reverified EXACT by DSG_OT_ConfirmImplant.
    if spec.bridge_op in {"analyze_implant_neighbor_clearance", "analyze_implant_diameter_options"}:
        mode = str(args.get("verification_mode", "FAST") or "FAST").upper()
        if mode not in {"FAST", "FULL_VERTEX", "EXACT"}:
            raise ValueError("verification_mode must be FAST, FULL_VERTEX or EXACT")
        args["verification_mode"] = mode
    return args


def _dispatch(spec: agent_core.AgentToolSpec, params: dict[str, Any], scene) -> Any:
    roadmap = _bridge_module()
    args = _prepare_args(spec, params)
    response = roadmap._dispatch_operation(scene, spec.bridge_op, args)
    if not isinstance(response, dict):
        raise RuntimeError("DSG operation returned a non-object response")
    if not bool(response.get("ok", False)):
        raise RuntimeError(str(response.get("error") or "DSG operation failed"))
    return response.get("result")


def run_agent_tool(tool_name: str, params: dict[str, Any] | None = None, *,
                   operation_id: str | None = None, scene=None) -> dict[str, Any]:
    """Run one closed-capability agent tool on Blender's main thread.

    Mutations are idempotent by ``operation_id + canonical input hash``.  A
    committed operation is replayed from the scene journal rather than run a
    second time.  Queries do not require operation IDs.
    """
    _require_main_thread()
    scene = _scene(scene)
    name = str(tool_name or "")
    spec = agent_core.TOOLS.get(name)
    if spec is None or not spec.agent_callable:
        raise PermissionError(f"Agent capability is not exposed: {name or '<missing>'}")
    if not isinstance(params or {}, dict):
        raise ValueError("params must be an object")
    params = params or {}

    revision_before = agent_scene_graph.current_revision(scene)
    op_id = str(operation_id or "")
    journal = _load_journal(scene)
    row = None

    if spec.requires_operation_id:
        if not op_id:
            return {
                "schema": RESULT_SCHEMA, "ok": False, "status": "OPERATION_ID_REQUIRED",
                "tool": name, "error": "Mutation tools require a stable operation_id for idempotency.",
            }
        input_hash = agent_core.canonical_hash(name, params)
        state, row = agent_core.begin_journal(
            journal, operation_id=op_id, tool_name=name, input_hash=input_hash,
            started_at=_utc_now(), scene_revision=revision_before,
        )
        if state == "CONFLICT":
            return {"schema": RESULT_SCHEMA, "ok": False, "status": "OPERATION_ID_CONFLICT", "tool": name, "operation_id": op_id, "journal": row}
        if state == "IN_PROGRESS":
            same_runtime = str(row.get("runtime_instance_id", "") or "") == _RUNTIME_INSTANCE_ID
            if not same_runtime:
                return {
                    "schema": RESULT_SCHEMA, "ok": False,
                    "status": "STALE_RUNNING_REVIEW_REQUIRED",
                    "tool": name, "operation_id": op_id, "journal": row,
                    "error": "Operation was left RUNNING by a previous Blender runtime. Inspect scene state before creating a new operation_id.",
                }
            return {"schema": RESULT_SCHEMA, "ok": True, "status": "IN_PROGRESS", "tool": name, "operation_id": op_id, "journal": row}
        if state == "FAILED_PREVIOUSLY":
            return {"schema": RESULT_SCHEMA, "ok": False, "status": "FAILED_PREVIOUSLY_NEW_ID_REQUIRED", "tool": name, "operation_id": op_id, "journal": row}
        if state == "REPLAY":
            return {
                "schema": RESULT_SCHEMA, "ok": True, "status": "REPLAYED_COMMITTED",
                "tool": name, "operation_id": op_id,
                "result": row.get("result"), "result_sha256": row.get("result_sha256"),
                "result_omitted_from_journal": row.get("result") is None,
                "scene_revision_before": row.get("scene_revision_before"),
                "scene_revision_after": row.get("scene_revision_after"),
            }
        row["runtime_instance_id"] = _RUNTIME_INSTANCE_ID
        _save_journal(scene, journal)  # persist RUNNING before geometry work

    try:
        result = _dispatch(spec, params, scene)
        if spec.mutates_scene:
            agent_scene_graph.mark_dirty(scene)
        revision_after = agent_scene_graph.current_revision(scene)
        payload = {
            "schema": RESULT_SCHEMA,
            "ok": True,
            "status": "COMMITTED" if spec.mutates_scene else "SUCCESS",
            "tool": name,
            "operation_id": op_id or None,
            "scene_revision_before": revision_before,
            "scene_revision_after": revision_after,
            "result": result,
        }
        if row is not None:
            cached, digest, size = _serializable_result(result)
            row.update({
                "status": "COMMITTED", "finished_at": _utc_now(),
                "scene_revision_after": revision_after,
                "result": cached, "result_sha256": digest, "result_bytes": size,
            })
            _save_journal(scene, journal)
        return payload
    except Exception as exc:
        if row is not None:
            row.update({
                "status": "FAILED", "finished_at": _utc_now(),
                "scene_revision_after": agent_scene_graph.current_revision(scene),
                "error": f"{type(exc).__name__}: {exc}",
                "partial_scene_mutation_possible": bool(spec.mutates_scene),
                "retry_policy": "INSPECT_SCENE_THEN_USE_NEW_OPERATION_ID",
            })
            _save_journal(scene, journal)
        return {
            "schema": RESULT_SCHEMA,
            "ok": False,
            "status": "FAILED",
            "tool": name,
            "operation_id": op_id or None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def register():
    agent_scene_graph.register()


def unregister():
    agent_scene_graph.unregister()
