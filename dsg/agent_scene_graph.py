"""Lazy semantic scene graph for the DSG local agent runtime.

Inspired by the *pattern* of Mixar's per-scene lazy graph, but implemented
independently for DSG's dental semantics.  The graph is deliberately compact:
it is a structured index, not a replacement for exact geometry queries.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

from dataclasses import dataclass
from typing import Any

import bpy

GRAPH_SCHEMA = "dsg.scene_graph.v1"
_RELEVANT_PREFIXES = ("DSG_", "DICOM_", "IOS_")
_RELEVANT_KEYS = (
    "DSG_role", "DSG_target_fdi", "DSG_fdi", "DSG_implant_name",
    "DSG_asset_role", "DSG_family", "DSG_mapping_quality",
    "DSG_irrigation_sealed", "DSG_irrigation_gate_mode",
)


@dataclass
class _GraphCache:
    dirty: bool = True
    revision: int = 0
    graph: dict[str, Any] | None = None


_CACHE: dict[int, _GraphCache] = {}
_HANDLER_REGISTERED = False


def _scene_key(scene) -> int:
    try:
        return int(scene.as_pointer())
    except Exception:
        return id(scene)


def _cache(scene) -> _GraphCache:
    key = _scene_key(scene)
    row = _CACHE.get(key)
    if row is None:
        row = _GraphCache()
        _CACHE[key] = row
    return row


def current_revision(scene) -> int:
    return int(_cache(scene).revision)


def mark_dirty(scene) -> None:
    row = _cache(scene)
    row.dirty = True
    row.revision += 1


def _is_relevant(obj) -> bool:
    name = str(getattr(obj, "name", "") or "")
    if name.startswith(_RELEVANT_PREFIXES):
        return True
    try:
        return any(key in obj for key in _RELEVANT_KEYS)
    except Exception:
        return False


def _safe_prop(obj, key: str):
    try:
        value = obj.get(key)
    except Exception:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Blender ID properties may be array-like; keep the graph JSON-safe.
    try:
        return list(value)
    except Exception:
        return str(value)


def _vec3(value) -> list[float]:
    try:
        return [round(float(value[0]), 6), round(float(value[1]), 6), round(float(value[2]), 6)]
    except Exception:
        return [0.0, 0.0, 0.0]


def _object_uid(obj) -> str:
    uid = getattr(obj, "session_uid", None)
    if uid is not None:
        return f"obj:{int(uid)}"
    try:
        return f"objptr:{int(obj.as_pointer())}"
    except Exception:
        return f"name:{getattr(obj, 'name', '')}"


def _node(obj) -> dict[str, Any]:
    world = getattr(obj, "matrix_world", None)
    loc = getattr(world, "translation", getattr(obj, "location", (0, 0, 0)))
    collections = [str(c.name) for c in getattr(obj, "users_collection", ())]
    props = {key: _safe_prop(obj, key) for key in _RELEVANT_KEYS if _safe_prop(obj, key) is not None}
    return {
        "id": _object_uid(obj),
        "name": str(getattr(obj, "name", "") or ""),
        "type": str(getattr(obj, "type", "") or ""),
        "role": str(props.get("DSG_role") or props.get("DSG_asset_role") or ""),
        "fdi": props.get("DSG_target_fdi", props.get("DSG_fdi")),
        "parent": _object_uid(obj.parent) if getattr(obj, "parent", None) is not None else None,
        "collections": collections,
        "world_location_mm": _vec3(loc),
        "dimensions_mm": _vec3(getattr(obj, "dimensions", (0, 0, 0))),
        "visible": not bool(getattr(obj, "hide_viewport", False)),
        "selected": bool(obj.select_get()) if hasattr(obj, "select_get") else False,
        "properties": props,
    }


def _relations(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in nodes}
    by_name = {row["name"]: row for row in nodes}
    out: list[dict[str, Any]] = []
    for row in nodes:
        if row.get("parent") in by_id:
            out.append({"type": "PARENTED_TO", "source": row["id"], "target": row["parent"]})
        implant_name = row.get("properties", {}).get("DSG_implant_name")
        if implant_name and str(implant_name) in by_name:
            out.append({"type": "REFERENCES_IMPLANT", "source": row["id"], "target": by_name[str(implant_name)]["id"]})
    # Same-FDI relations are useful to the agent without pretending they are
    # geometric constraints.
    by_fdi: dict[str, list[str]] = {}
    for row in nodes:
        fdi = row.get("fdi")
        if fdi not in (None, "", 0, "0"):
            by_fdi.setdefault(str(fdi), []).append(row["id"])
    for fdi, ids in by_fdi.items():
        if len(ids) > 1:
            out.append({"type": "FDI_GROUP", "fdi": fdi, "members": ids})
    return out


def _build(scene) -> dict[str, Any]:
    nodes = [_node(obj) for obj in scene.objects if _is_relevant(obj)]
    nodes.sort(key=lambda row: (str(row.get("role", "")), str(row.get("name", ""))))
    role_counts: dict[str, int] = {}
    for row in nodes:
        role = row.get("role") or "UNCLASSIFIED"
        role_counts[role] = role_counts.get(role, 0) + 1
    return {
        "schema": GRAPH_SCHEMA,
        "scene": str(getattr(scene, "name", "") or ""),
        "revision": current_revision(scene),
        "node_count": len(nodes),
        "role_counts": role_counts,
        "nodes": nodes,
        "relations": _relations(nodes),
        "authority_note": "Semantic index only. Exact clinical measurements must use DSG geometry services, never scene-graph coordinates alone.",
    }


def get_scene_graph(scene) -> dict[str, Any]:
    row = _cache(scene)
    if row.graph is None or row.dirty:
        row.graph = _build(scene)
        row.dirty = False
        # Ensure the materialized graph exposes the revision after rebuild.
        row.graph["revision"] = int(row.revision)
    return row.graph


def get_scene_graph_summary(scene) -> dict[str, Any]:
    graph = get_scene_graph(scene)
    return {
        "schema": GRAPH_SCHEMA,
        "scene": graph["scene"],
        "revision": graph["revision"],
        "node_count": graph["node_count"],
        "role_counts": dict(graph["role_counts"]),
        "relation_count": len(graph["relations"]),
    }


def _depsgraph_handler(scene, depsgraph):
    # Keep handlers tiny and side-effect free: mark cache dirty only.  This is
    # intentionally conservative.  Rebuild happens lazily on the next query.
    try:
        for update in depsgraph.updates:
            ident = getattr(update, "id", None)
            if isinstance(ident, bpy.types.Object):
                if _is_relevant(ident):
                    mark_dirty(scene)
                    return
            elif isinstance(ident, (bpy.types.Mesh, bpy.types.Curve)):
                mark_dirty(scene)
                return
    except Exception:
        # A stale depsgraph callback must never break Blender interaction.
        return


def register():
    global _HANDLER_REGISTERED
    if _HANDLER_REGISTERED:
        return
    if _depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_handler)
    _HANDLER_REGISTERED = True


def unregister():
    global _HANDLER_REGISTERED
    try:
        while _depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handler)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _CACHE.clear()
    _HANDLER_REGISTERED = False
