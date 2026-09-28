"""Blender adapter for DSG frame structural precheck and MCP context.

Reuses the existing DSG geodesic graph, sleeve geometry and local-thickness
probes.  It does not implement a second frame engine and it is not an FEA
solver.  All results that rank weakness are explicitly labelled geometric
proxies unless user-supplied thresholds are provided.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
import math
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import guide_module
from . import frame_structural_core as core
from . import frame_fem_core as fem

FRAME_STRUCTURAL_SCHEMA = core.SCHEMA
SUPPORT_KEY = "DSG_frame_support_nodes_json"
SUPPORT_SOURCE_KEY = "DSG_frame_support_identity_source"


def _json_points(raw: Any) -> list[Vector]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    out = []
    for item in data or []:
        try:
            if isinstance(item, dict):
                item = item.get("xyz") or item.get("co")
            if item is not None and len(item) == 3:
                out.append(Vector((float(item[0]), float(item[1]), float(item[2]))))
        except Exception:
            continue
    return out


def _frame_obj(context):
    props = context.scene.dsg_props
    obj = getattr(props, "frame_obj", None)
    if obj is not None and obj.name in bpy.data.objects:
        return obj
    found = guide_module.find_dsg_objects(role=guide_module.ROLE_FRAME, obj_type='MESH')
    return found[0] if found else bpy.data.objects.get(guide_module.FRAME_NAME)


def _passive_obj(context):
    found = guide_module.find_dsg_objects(role=guide_module.ROLE_PASSIVE, obj_type='MESH')
    if found:
        return found[0]
    return bpy.data.objects.get(guide_module.COMBINED_NAME)


def _support_nodes(frame_obj) -> tuple[list[dict], str]:
    explicit = _json_points(frame_obj.get(SUPPORT_KEY, "")) if frame_obj is not None else []
    source = "EXPLICIT_SEMANTIC_P1_P4"
    pts = explicit
    if len(pts) != 4:
        pts = _json_points(frame_obj.get("DSG_frame_source_points_json", "")) if frame_obj is not None else []
        source = "FRAME_SOURCE_POINTS_LEGACY_ORDER"
    if len(pts) != 4:
        raise RuntimeError("GenerativeFrame requires exactly four support points P1..P4")
    rows = []
    for idx, p in enumerate(pts, start=1):
        rows.append({"id": f"P{idx}", "xyz": [float(p.x), float(p.y), float(p.z)]})
    return rows, source


def persist_support_nodes(context, points: list[list[float]], authority: str = "USER") -> dict:
    """Persist explicit P1..P4 semantics without changing frame geometry."""
    frame = _frame_obj(context)
    if frame is None:
        raise RuntimeError("DSG_Frame not found")
    if len(points) != 4:
        raise ValueError("Exactly four support points are required")
    rows = []
    for i, p in enumerate(points, start=1):
        v = Vector((float(p[0]), float(p[1]), float(p[2])))
        rows.append({"id": f"P{i}", "xyz": [float(v.x), float(v.y), float(v.z)], "authority": str(authority)})
    frame[SUPPORT_KEY] = json.dumps(rows, sort_keys=True)
    frame[SUPPORT_SOURCE_KEY] = "EXPLICIT_SEMANTIC_P1_P4"
    return {"support_nodes": rows, "support_identity_source": "EXPLICIT_SEMANTIC_P1_P4"}


def _sleeve_context(context) -> list[dict]:
    props = context.scene.dsg_props
    inner_r, outer_r, wall = guide_module._sleeve_radii_from_props(props)
    height = max(0.1, float(getattr(props, "sleeve_height", 7.0)))
    rows = []
    for index, implant in enumerate(guide_module.get_all_implant_objects(props), start=1):
        mx = guide_module.get_sleeve_matrix_world(props, implant)
        center = mx.to_translation()
        axis = guide_module.get_sleeve_axis_world(props, implant)
        rows.append({
            "id": f"S{index}",
            "implant_name": str(implant.name),
            "target_fdi": int(implant.get("DSG_target_fdi", 0) or 0),
            "center": [float(v) for v in center],
            "axis": [float(v) for v in axis],
            "inner_radius_mm": float(inner_r),
            "outer_radius_mm": float(outer_r),
            "wall_mm": float(wall),
            "height_mm": float(height),
            "matrix_world": [[float(value) for value in row] for row in mx],
            "lumen_keep_out": True,
        })
    return rows


def _nearest_sleeve_attachment(point: Vector, sleeves: list[dict]) -> tuple[dict | None, Vector | None, float | None]:
    best = None
    best_point = None
    best_distance = None
    for sleeve in sleeves:
        try:
            from mathutils import Matrix
            mx = Matrix(sleeve["matrix_world"])
            local = mx.inverted_safe() @ point
            radial = Vector((local.x, local.y, 0.0))
            if radial.length < 1e-8:
                radial = Vector((1.0, 0.0, 0.0))
            radial.normalize()
            half_h = float(sleeve["height_mm"]) * 0.5
            # Keep a small axial margin away from sleeve top/bottom faces.
            local_z = max(-half_h * 0.82, min(half_h * 0.82, float(local.z)))
            attach_local = radial * float(sleeve["outer_radius_mm"])
            attach_local.z = local_z
            attach_world = mx @ attach_local
            d = (point - attach_world).length
        except Exception:
            continue
        if best_distance is None or d < best_distance:
            best = sleeve; best_point = attach_world; best_distance = float(d)
    return best, best_point, best_distance


def _segment_intersects_sleeve_lumen(a: Vector, b: Vector, sleeve: dict, samples: int = 48) -> bool:
    """Conservative sampled test against the finite cylindrical lumen keep-out."""
    try:
        from mathutils import Matrix
        inv = Matrix(sleeve["matrix_world"]).inverted_safe()
        inner = float(sleeve["inner_radius_mm"])
        half_h = float(sleeve["height_mm"]) * 0.5
        for i in range(max(2, int(samples)) + 1):
            t = i / float(max(2, int(samples)))
            p = a.lerp(b, t)
            q = inv @ p
            if math.hypot(q.x, q.y) < inner - 1e-4 and abs(float(q.z)) <= half_h + 1e-4:
                return True
    except Exception:
        return True  # fail-safe: unknown geometry is not accepted as lumen-safe
    return False


def _polyline_midpoint(points: list[Vector]) -> Vector:
    xyz = core.point_at_fraction([[p.x, p.y, p.z] for p in points], 0.5)
    return Vector(xyz)


def _sample_local_thickness(context, frame_obj, points: list[Vector]) -> tuple[float | None, list[float]]:
    """Reuse DSG's own BVH/raycast wall-thickness probe on the current frame mesh."""
    if frame_obj is None or frame_obj.type != 'MESH':
        return None, []
    try:
        tree = guide_module._build_world_surface_bvh(context, frame_obj)
    except Exception:
        tree = None
    if tree is None:
        return None, []
    values = []
    for fraction in (0.25, 0.50, 0.75):
        xyz = core.point_at_fraction([[p.x, p.y, p.z] for p in points], fraction)
        p = Vector(xyz)
        try:
            hit = tree.find_nearest(p)
        except Exception:
            hit = None
        if not hit or hit[0] is None or hit[1] is None:
            continue
        surface, normal = Vector(hit[0]), Vector(hit[1])
        try:
            thickness = guide_module._smart_anchor_single_wall_thickness(tree, surface, normal)
        except Exception:
            thickness = None
        if thickness is not None and math.isfinite(float(thickness)):
            values.append(float(thickness))
    return (min(values) if values else None), values


def _route_between(context, passive, cache, a: Vector, b: Vector, frame_radius: float):
    ia, da = guide_module._frame_nearest_vertex(cache, a)
    ib, db = guide_module._frame_nearest_vertex(cache, b)
    if ia < 0 or ib < 0:
        return None, {"reason": "support snap failed"}
    route, stats = guide_module._frame_width_preserving_surface_route(
        context, passive, cache, ia, ib, frame_radius_mm=frame_radius)
    if not route:
        return None, stats
    points, normals = guide_module._frame_intrinsic_resample(
        cache, route, max_spacing=guide_module.FRAME_SURFACE_TARGET_SPACING_MM)
    if points:
        points[0] = a.copy(); points[-1] = b.copy()
    return (points, normals), stats


def get_frame_context(context=None) -> dict:
    context = context or bpy.context
    frame = _frame_obj(context)
    passive = _passive_obj(context)
    if frame is None:
        raise RuntimeError("DSG_Frame not found")
    supports, source = _support_nodes(frame)
    sleeves = _sleeve_context(context)
    return {
        "schema": "dsg.generative_frame_context.v1",
        "frame_name": str(frame.name),
        "passive_surface": str(passive.name) if passive is not None else None,
        "support_nodes": supports,
        "support_identity_source": source,
        "support_identity_warning": (None if source == "EXPLICIT_SEMANTIC_P1_P4" else
                                     "P1..P4 were recovered from legacy frame source-point order; persist explicit semantics before autonomous regeneration."),
        "frame_radius_mm": float(frame.get("DSG_frame_radius_mm", getattr(context.scene.dsg_props, "tube_radius", guide_module.FRAME_RADIUS_DEFAULT_MM))),
        "frame_diameter_mm": float(frame.get("DSG_frame_diameter_mm", 2.0 * float(getattr(context.scene.dsg_props, "tube_radius", guide_module.FRAME_RADIUS_DEFAULT_MM)))),
        "sleeves": sleeves,
        "keep_out_regions": ["SLEEVE_LUMEN", "DRILL_PATH", "IRRIGATION_CHANNEL", "LATERAL_OPENING", "FRANGIBLE_WALL"],
        "single_sleeve_topology": core.single_sleeve_primary_topology() if len(sleeves) == 1 else None,
        "analysis_mode": "FEM_V2_AVAILABLE_PLUS_GEOMETRIC_PRECHECK",
    }


def analyze_frame_structure(context=None, thresholds: dict | None = None) -> dict:
    context = context or bpy.context
    frame = _frame_obj(context)
    passive = _passive_obj(context)
    if frame is None or passive is None:
        raise RuntimeError("DSG frame and passive/blockout surface are required")
    ctx = get_frame_context(context)
    supports = {row["id"]: Vector(row["xyz"]) for row in ctx["support_nodes"]}
    sleeves = ctx["sleeves"]
    radius = float(ctx["frame_radius_mm"])
    diameter = float(ctx["frame_diameter_mm"])

    cache, reused, error = guide_module._build_frame_surface_graph_cache(context, passive)
    if cache is None:
        raise RuntimeError(error or "could not build frame surface graph")

    pairs = [("P1","P2"),("P2","P3"),("P3","P4"),("P4","P1")]
    segments = []
    for idx, (a_id, b_id) in enumerate(pairs, start=1):
        routed, stats = _route_between(context, passive, cache, supports[a_id], supports[b_id], radius)
        if routed is None:
            segments.append({"id": f"E{idx}", "from": a_id, "to": b_id,
                             "route_valid": False, "reason": str((stats or {}).get("reason", "route failed"))})
            continue
        points, _normals = routed
        span = core.polyline_length([[p.x,p.y,p.z] for p in points])
        midpoint = _polyline_midpoint(points)
        sleeve, attach, sleeve_distance = _nearest_sleeve_attachment(midpoint, sleeves)
        min_thickness, thickness_samples = _sample_local_thickness(context, frame, points)
        proxy = core.structural_need_proxy(span, diameter, sleeve_distance or 0.0, min_thickness)
        segments.append({
            "id": f"E{idx}", "from": a_id, "to": b_id, "route_valid": True,
            "geodesic_span_mm": float(span),
            "midpoint": [float(v) for v in midpoint],
            "nearest_sleeve_id": sleeve.get("id") if sleeve else None,
            "nearest_sleeve_implant": sleeve.get("implant_name") if sleeve else None,
            "sleeve_attachment": [float(v) for v in attach] if attach is not None else None,
            "distance_to_nearest_sleeve_envelope_mm": sleeve_distance,
            "min_local_thickness_mm": min_thickness,
            "local_thickness_samples_mm": thickness_samples,
            "route_backend": str((stats or {}).get("backend", "UNKNOWN")),
            **proxy,
        })

    valid = [row for row in segments if row.get("route_valid")]
    valid = core.normalize_scores(valid)
    by_id = {row["id"]: row for row in valid}
    segments = [by_id.get(row["id"], row) for row in segments]
    ranked = sorted(valid, key=lambda row: float(row.get("relative_need_0_1", 0.0)), reverse=True)
    metrics = {
        "max_unsupported_span_mm": max((float(r["geodesic_span_mm"]) for r in valid), default=None),
        "min_local_thickness_mm": min((float(r["min_local_thickness_mm"]) for r in valid if r.get("min_local_thickness_mm") is not None), default=None),
        "max_relative_need_0_1": max((float(r.get("relative_need_0_1", 0.0)) for r in valid), default=None),
        "segment_count": len(valid),
    }
    threshold_result = core.validate_thresholds(metrics, thresholds)
    result = {
        "schema": FRAME_STRUCTURAL_SCHEMA,
        "analysis_mode": "GEOMETRIC_STRUCTURAL_PRECHECK_NOT_FEA",
        "frame": {"name": str(frame.name), "diameter_mm": diameter, "surface_graph_cache_reused": bool(reused)},
        "support_identity_source": ctx["support_identity_source"],
        "sleeves": sleeves,
        "segments": segments,
        "structural_need_ranking": [r["id"] for r in ranked],
        "metrics": metrics,
        "threshold_evaluation": threshold_result,
        "warnings": [
            "Geometric need is a relative proxy, not stress/displacement or factor of safety.",
            "No engineering/clinical threshold is applied unless explicitly supplied.",
        ],
    }
    return result


def propose_frame_reinforcements(context=None, max_candidates: int = 4,
                                 thresholds: dict | None = None) -> dict:
    """Propose topology only; does not modify geometry or apply booleans."""
    context = context or bpy.context
    analysis = analyze_frame_structure(context, thresholds=thresholds)
    frame_ctx = get_frame_context(context)
    supports = {row["id"]: Vector(row["xyz"]) for row in frame_ctx["support_nodes"]}
    sleeves = frame_ctx["sleeves"]
    candidates = []

    # Primary invariant branches.  For a single sleeve this exactly represents
    # P1→S←P3 and P2→S←P4, each as an independent support→sleeve branch.
    if len(sleeves) == 1:
        sleeve = sleeves[0]
        for p_id in ("P1","P3","P2","P4"):
            support = supports[p_id]
            _s, attach, dist = _nearest_sleeve_attachment(support, [sleeve])
            lumen_hit = True if attach is None else _segment_intersects_sleeve_lumen(support, attach, sleeve)
            candidates.append({
                "kind": "PRIMARY_SUPPORT_TO_SLEEVE",
                "from_node": p_id,
                "to_node": sleeve["id"],
                "direction": "SUPPORT_TO_SLEEVE",
                "from_xyz": [float(v) for v in support],
                "to_sleeve_envelope_xyz": [float(v) for v in attach] if attach is not None else None,
                "direct_length_mm": dist,
                "lumen_intersection": bool(lumen_hit),
                "status": "REJECTED_LUMEN_INTERSECTION" if lumen_hit else "PROPOSED_NOT_APPLIED",
            })

    # Additional candidates originate from the midpoint of the structurally
    # highest-ranked peripheral spans and terminate on the nearest sleeve shell.
    segment_by_id = {row["id"]: row for row in analysis["segments"]}
    for seg_id in analysis["structural_need_ranking"]:
        if len(candidates) >= max(4, int(max_candidates)) + (4 if len(sleeves) == 1 else 0):
            break
        row = segment_by_id[seg_id]
        if not row.get("midpoint") or not row.get("sleeve_attachment"):
            continue
        target_sleeve = next((sl for sl in sleeves if sl.get("id") == row.get("nearest_sleeve_id")), None)
        a = Vector(row["midpoint"]); b = Vector(row["sleeve_attachment"])
        lumen_hit = True if target_sleeve is None else _segment_intersects_sleeve_lumen(a, b, target_sleeve)
        candidates.append({
            "kind": "ADAPTIVE_SPAN_TO_SLEEVE",
            "from_region": seg_id,
            "from_xyz": list(row["midpoint"]),
            "to_node": row.get("nearest_sleeve_id"),
            "to_sleeve_envelope_xyz": list(row["sleeve_attachment"]),
            "direction": "FRAME_REGION_TO_SLEEVE",
            "relative_need_0_1": row.get("relative_need_0_1"),
            "direct_length_mm": row.get("distance_to_nearest_sleeve_envelope_mm"),
            "lumen_intersection": bool(lumen_hit),
            "status": "REJECTED_LUMEN_INTERSECTION" if lumen_hit else "PROPOSED_NOT_APPLIED",
        })

    proposal = {
        "schema": "dsg.frame_reinforcement_proposal.v1",
        "analysis_schema": FRAME_STRUCTURAL_SCHEMA,
        "applies_geometry": False,
        "single_sleeve_topology": frame_ctx.get("single_sleeve_topology"),
        "candidates": candidates,
        "keep_out_regions": frame_ctx["keep_out_regions"],
        "catmull_rom_policy": "CENTRIPETAL_ALPHA_0_5_FOR_GEOMETRIC_SMOOTHING_ONLY_TOPOLOGY_IS_DECIDED_FIRST",
        "multi_sleeve_note": ("Multiple sleeves are reported as separate load nodes. Figure-eight/chained topology remains a candidate to be compared by MCP; this version does not silently choose one." if len(sleeves) > 1 else None),
        "requires_clinician_review_before_boolean": True,
    }
    return proposal


def get_contract() -> dict:
    path = Path(__file__).resolve().parent / "resources" / "frame" / "frame_structural_contract_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


# =============================================================================
# GENERATIVEFRAME FEM V2 · integración Blender
# =============================================================================

FRAME_FEM_SCHEMA = "dsg.generative_frame_fem.v1"
FRAME_FEM_PROFILE = "BALANCED"
FRAME_FEM_AXIAL_N = 40.0
FRAME_FEM_LATERAL_N = 15.0
FRAME_FEM_TORQUE_NMM = 20.0
FRAME_FEM_DESIGN_UTIL = 0.75
FRAME_FEM_DISP_TARGET_MM = 0.15
FRAME_FEM_DISP_LIMIT_MM = 0.20


def _fem_vec(v) -> np.ndarray:
    return np.asarray((float(v[0]), float(v[1]), float(v[2])), dtype=float)


def _fem_safe_unit(v, fallback=(0.0, 0.0, 1.0)) -> Vector:
    out = Vector(v)
    if out.length < 1e-9:
        out = Vector(fallback)
    if out.length < 1e-9:
        out = Vector((0.0, 0.0, 1.0))
    out.normalize()
    return out


def _fem_profile_config(props) -> fem.OptimizationConfig:
    # Perfil único visible: KISS. Los parámetros finos quedan centralizados aquí,
    # no dispersos por la UI. connector_diameter solo influye en el radio inicial.
    return fem.OptimizationConfig(
        iterations=18,
        radius_min_mm=0.55,
        radius_max_mm=2.20,
        prune_below_mm=0.65,
        relaxation=0.60,
        design_utilization_target=FRAME_FEM_DESIGN_UTIL,
        displacement_limit_mm=FRAME_FEM_DISP_LIMIT_MM,
        displacement_design_target_mm=FRAME_FEM_DISP_TARGET_MM,
        prune_utilization_threshold=0.15,
        max_prune_tests_per_iteration=8,
        prune_requires_recommended=True,
        enable_topology_growth=True,
        growth_trigger_utilization=0.95,
        growth_trigger_displacement_ratio=1.05,
        growth_every_n_iterations=2,
        max_growth_elements_per_round=3,
        max_growth_rounds=3,
        triangle_height_factor=0.22,
        triangle_height_min_mm=1.5,
        triangle_height_max_mm=5.0,
        growth_radius_mm=max(0.60, min(1.10, float(getattr(props, 'connector_diameter', 2.5)) * 0.30)),
        node_merge_distance_mm=0.50,
        numerical_tol=5.0e-4,
    )


def _fem_material_element(i: int, j: int, radius_mm: float, **kwargs) -> fem.BeamElement:
    params = dict(
        E=2500.0, G=900.0,
        material_strength_mpa=80.0,
        material_safety_factor=1.25,
        process_safety_factor=1.15,
        buckling_safety=2.0,
        effective_length_factor=1.0,
    )
    params.update(kwargs)
    return fem.BeamElement(i=i, j=j, radius_mm=float(radius_mm), **params)


def _fem_sleeve_cardinal_points(sleeve: dict) -> tuple[Vector, list[Vector], Matrix]:
    mx = Matrix(sleeve["matrix_world"])
    center = mx.to_translation()
    radius = max(0.5, float(sleeve["outer_radius_mm"]))
    # 1 % fuera de la envolvente para que la rama termine sobre la pared externa,
    # no dentro del lumen. z=0 utiliza el tercio medio más resistente del sleeve.
    r = radius * 1.01
    local = (
        Vector(( r, 0.0, 0.0)),
        Vector((0.0,  r, 0.0)),
        Vector((-r, 0.0, 0.0)),
        Vector((0.0, -r, 0.0)),
    )
    return center, [mx @ p for p in local], mx


def _fem_build_keep_out(context, sleeves: list[dict]):
    passive = _passive_obj(context)
    passive_tree = None
    if passive is not None:
        try:
            passive_tree = guide_module._build_world_surface_bvh(context, passive)
        except Exception:
            passive_tree = None

    def check(a_np: np.ndarray, b_np: np.ndarray) -> bool:
        a = Vector(tuple(float(v) for v in a_np))
        b = Vector(tuple(float(v) for v in b_np))
        if (b - a).length < 0.20:
            return True

        # Hard keep-out: lumen de cualquier sleeve.
        for sleeve in sleeves:
            if _segment_intersects_sleeve_lumen(a, b, sleeve, samples=28):
                return True

        # Evita cuerdas que atraviesen el modelo pasivo. Se ignoran los extremos,
        # que legítimamente pueden estar apoyados/embebidos en la guía.
        if passive_tree is not None:
            for k in range(1, 10):
                t = k / 10.0
                p = a.lerp(b, t)
                try:
                    hit = passive_tree.find_nearest(p)
                except Exception:
                    hit = None
                if not hit or hit[0] is None or hit[1] is None:
                    continue
                surface = Vector(hit[0])
                normal = _fem_safe_unit(hit[1])
                signed = (p - surface).dot(normal)
                # Solo rechazamos penetración inequívoca; una cercanía exterior
                # pequeña es normal para un refuerzo apoyado sobre la férula.
                if signed < -0.20:
                    return True
        return False

    return check


def _fem_build_model(context=None):
    context = context or bpy.context
    props = context.scene.dsg_props
    frame_ctx = get_frame_context(context)
    supports = [Vector(row["xyz"]) for row in frame_ctx["support_nodes"]]
    sleeves = list(frame_ctx.get("sleeves") or [])
    if len(supports) != 4:
        raise RuntimeError("GenerativeFrame FEM requiere exactamente P1..P4")
    if not sleeves:
        raise RuntimeError("GenerativeFrame FEM requiere al menos un sleeve aplicado")

    nodes: list[fem.Node] = [
        fem.Node(_fem_vec(p), np.array([True] * 6), role="KEEP_IN_SUPPORT")
        for p in supports
    ]
    elements: list[fem.BeamElement] = []
    monitor_nodes: list[int] = []
    load_cases: list[fem.LoadCase] = []
    sleeve_records: list[dict] = []

    connector_radius = max(
        0.60,
        min(1.25, float(getattr(props, 'connector_diameter', guide_module.REINFORCEMENT_DIAMETER_MM)) * 0.5),
    )
    keep_out = _fem_build_keep_out(context, sleeves)

    for sleeve_index, sleeve in enumerate(sleeves):
        center, attachment_points, mx = _fem_sleeve_cardinal_points(sleeve)
        center_idx = len(nodes)
        nodes.append(fem.Node(_fem_vec(center), np.array([False] * 6), role="LOAD"))
        monitor_nodes.append(center_idx)

        attach_indices = []
        for point in attachment_points:
            idx = len(nodes)
            nodes.append(fem.Node(_fem_vec(point), np.array([False] * 6), role="SLEEVE_ATTACH"))
            attach_indices.append(idx)

            # Sleeve idealizado como unión rígida. Participa en K pero no se
            # optimiza, no se poda y no genera geometría visible.
            elements.append(_fem_material_element(
                center_idx, idx,
                radius_mm=max(1.50, float(sleeve["outer_radius_mm"]) * 0.70),
                E=25000.0, G=9000.0,
                allow_stress_mpa=1.0e9,
                tag=f"VIRTUAL_SLEEVE_{sleeve_index}",
                render=False, locked_radius=True, prunable=False, virtual=True,
            ))

        # Para cada apoyo, solo las dos posiciones de sleeve más cercanas. Esto
        # conserva suficientes caminos alternativos sin crear una telaraña.
        for support_idx, support in enumerate(supports):
            ranked = sorted(
                attach_indices,
                key=lambda idx: float(np.linalg.norm(nodes[idx].xyz - nodes[support_idx].xyz)),
            )
            accepted = 0
            for attach_idx in ranked:
                if accepted >= 2:
                    break
                a = nodes[support_idx].xyz
                b = nodes[attach_idx].xyz
                L = float(np.linalg.norm(b - a))
                if L < 1.5 or L > 65.0:
                    continue
                if keep_out(a, b):
                    continue
                elements.append(_fem_material_element(
                    support_idx, attach_idx, connector_radius,
                    tag=f"CAND_S{sleeve_index+1}_P{support_idx+1}",
                    render=True, locked_radius=False, prunable=True, virtual=False,
                ))
                accepted += 1

        axis = -_fem_safe_unit(sleeve.get("axis", (0.0, 0.0, 1.0)))
        x_axis = _fem_safe_unit(mx.to_3x3() @ Vector((1.0, 0.0, 0.0)), (1.0, 0.0, 0.0))
        y_axis = _fem_safe_unit(mx.to_3x3() @ Vector((0.0, 1.0, 0.0)), (0.0, 1.0, 0.0))
        cases = fem.make_sleeve_load_cases(
            center_idx,
            axial_N=FRAME_FEM_AXIAL_N,
            lateral_N=FRAME_FEM_LATERAL_N,
            torque_Nmm=FRAME_FEM_TORQUE_NMM,
            axial_axis=tuple(axis),
            lateral_x_axis=tuple(x_axis),
            lateral_y_axis=tuple(y_axis),
            torque_axis=tuple(-axis),
        )
        for case in cases:
            case.name = f"{sleeve.get('id', f'S{sleeve_index+1}')}:{case.name}"
        load_cases.extend(cases)
        sleeve_records.append({
            "id": str(sleeve.get("id", f"S{sleeve_index+1}")),
            "center_node": center_idx,
            "attachment_nodes": attach_indices,
        })

    renderable = [e for e in elements if e.render and not e.virtual]
    if len(renderable) < 2:
        raise RuntimeError(
            "No hay suficientes trayectorias FEM seguras entre P1..P4 y el sleeve. "
            "Revisa el contorno/posición del sleeve o los keep-out."
        )

    return {
        "nodes": nodes,
        "elements": elements,
        "load_cases": load_cases,
        "monitor_nodes": monitor_nodes,
        "keep_out": keep_out,
        "frame_context": frame_ctx,
        "sleeve_records": sleeve_records,
        "config": _fem_profile_config(props),
    }


def _fem_summary(model: dict, result: fem.OptimizationResult) -> dict:
    bundle = result.final_bundle
    rows = []
    for idx in result.active_elements:
        e = model["elements"][idx]
        r = bundle.worst_results[idx]
        if r is None:
            continue
        rows.append({
            "element_index": int(idx),
            "from_node": int(e.i),
            "to_node": int(e.j),
            "radius_mm": float(e.radius_mm),
            "diameter_mm": float(e.radius_mm * 2.0),
            "length_mm": float(r["length_mm"]),
            "utilization": float(r["utilization"]),
            "governing": str(r["governing"]),
            "tag": str(e.tag),
        })
    last = result.history[-1] if result.history else {}
    return {
        "schema": FRAME_FEM_SCHEMA,
        "profile": FRAME_FEM_PROFILE,
        "hard_safe": bool(result.hard_safe),
        "recommended": bool(result.recommended),
        "volume_mm3": float(result.total_volume_mm3),
        "active_reinforcements": len(rows),
        "max_utilization": float(last.get("max_utilization", 0.0)),
        "max_stress_ratio": float(last.get("max_stress_ratio", 0.0)),
        "max_buckling_ratio": float(last.get("max_buckling_ratio", 0.0)),
        "sleeve_displacement_mm": float(last.get("sleeve_displacement_mm", 0.0)),
        "design_utilization_target": float(model["config"].design_utilization_target),
        "displacement_design_target_mm": float(model["config"].displacement_design_target_mm),
        "displacement_limit_mm": float(model["config"].displacement_limit_mm),
        "iterations": len(result.history),
        "scipy_sparse": bool(getattr(fem, "_HAVE_SCIPY", False)),
        "elements": rows,
        "history": result.history,
        "warning": (
            "FEM design aid: material/load defaults require validation for the actual resin, manufacturing process and clinical use."
        ),
    }


def analyze_frame_fem(context=None) -> dict:
    """Run FEM without touching Blender geometry."""
    context = context or bpy.context
    model = _fem_build_model(context)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"],
        config=model["config"],
        keep_out_check=model["keep_out"],
    )
    return _fem_summary(model, result)


def _remove_existing_fem_reinforcements():
    removed = 0
    for obj in list(guide_module.get_confirmed_reinforcement_curves()):
        try:
            if bool(obj.get("DSG_reinforcement_fem_generated", False)):
                guide_module.safe_remove_object(obj)
                removed += 1
        except Exception:
            continue
    return removed


def create_fem_reinforcements(context=None, *, replace_existing=True) -> dict:
    """Run FEM and create confirmed reinforcement CURVE objects for review.

    Geometry remains non-destructive until the existing APPLY AND CONTINUE step.
    """
    context = context or bpy.context
    props = context.scene.dsg_props
    guide = guide_module.get_active_guide_obj(props)
    if not guide_module._valid_obj(guide):
        raise RuntimeError("DSG_Guide no está disponible")

    existing = guide_module.get_confirmed_reinforcement_curves()
    manual = [obj for obj in existing if not bool(obj.get("DSG_reinforcement_fem_generated", False))]
    if manual:
        raise RuntimeError(
            "Hay refuerzos manuales confirmados. Aplícalos o elimínalos antes de optimizar automáticamente."
        )
    if replace_existing:
        _remove_existing_fem_reinforcements()
        props.reinforcement_count = 0

    model = _fem_build_model(context)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"],
        config=model["config"],
        keep_out_check=model["keep_out"],
    )
    summary = _fem_summary(model, result)

    if not result.hard_safe:
        raise RuntimeError(
            f"El FEM no alcanza los límites duros: U={summary['max_utilization']:.2f}, "
            f"desplazamiento={summary['sleeve_displacement_mm']:.3f} mm. "
            "DSG no genera refuerzos inseguros automáticamente."
        )

    created = []
    bundle = result.final_bundle
    bevel_resolution = max(5, int(getattr(props, 'reinforcement_bevel_resolution', 8)))
    try:
        for serial, element_index in enumerate(result.active_elements):
            e = model["elements"][element_index]
            if not e.active or not e.render or e.virtual:
                continue
            r = bundle.worst_results[element_index]
            if r is None:
                continue
            p0 = Vector(tuple(float(v) for v in model["nodes"][e.i].xyz))
            p1 = Vector(tuple(float(v) for v in model["nodes"][e.j].xyz))
            if (p1 - p0).length < 0.5:
                continue

            name = f"{guide_module.REINFORCEMENT_PREFIX}{serial:02d}"
            guide_module.safe_remove_by_name(name)
            obj = guide_module.create_poly_curve_object(
                context, name, [p0, p1],
                bevel_radius=float(e.radius_mm),
                bevel_resolution=bevel_resolution,
                cyclic=False,
            )
            if not guide_module._valid_obj(obj):
                raise RuntimeError(f"No se pudo crear el elemento FEM {element_index}")

            metadata = {
                "DSG_reinforcement_preview": False,
                "DSG_reinforcement_confirmed": True,
                "DSG_reinforcement_index": int(serial),
                "DSG_reinforcement_diameter": float(e.radius_mm * 2.0),
                "DSG_reinforcement_fem_generated": True,
                "DSG_fem_schema": FRAME_FEM_SCHEMA,
                "DSG_fem_element_index": int(element_index),
                "DSG_fem_governing": str(r["governing"]),
                "DSG_fem_utilization": float(r["utilization"]),
                "DSG_fem_radius_mm": float(e.radius_mm),
                "DSG_fem_length_mm": float(r["length_mm"]),
                "DSG_fem_tag": str(e.tag),
            }
            obj = guide_module.register_dsg_object(
                obj, guide_module.ROLE_REINFORCEMENT, name, metadata)
            obj.show_in_front = False
            created.append(obj)

        if not created:
            raise RuntimeError("El FEM no produjo barras renderizables")

        props.reinforcement_count = len(created)
        props.reinforcement_preview_obj = None
        guide["DSG_frame_fem_schema"] = FRAME_FEM_SCHEMA
        guide["DSG_frame_fem_profile"] = FRAME_FEM_PROFILE
        guide["DSG_frame_fem_hard_safe"] = bool(summary["hard_safe"])
        guide["DSG_frame_fem_recommended"] = bool(summary["recommended"])
        guide["DSG_frame_fem_volume_mm3"] = float(summary["volume_mm3"])
        guide["DSG_frame_fem_max_utilization"] = float(summary["max_utilization"])
        guide["DSG_frame_fem_sleeve_displacement_mm"] = float(summary["sleeve_displacement_mm"])
        guide["DSG_frame_fem_history_json"] = json.dumps(summary["history"], separators=(",", ":"))
        guide["DSG_frame_fem_element_count"] = int(len(created))
        guide["DSG_frame_fem_design_aid_not_validation"] = True
        if created:
            guide_module.set_active(context, created[0])
        return summary
    except Exception:
        for obj in created:
            if guide_module._valid_obj(obj):
                guide_module.safe_remove_object(obj)
        props.reinforcement_count = 0
        raise


class DSG_OT_OptimizeFrameFEM(Operator):
    bl_idname = "dsg.optimize_frame_fem"
    bl_label = "Optimize Frame"
    bl_description = "FEM multi-carga: genera refuerzos mínimos y los deja en revisión antes de aplicarlos"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        try:
            if int(getattr(props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
                raise RuntimeError("La optimización FEM se ejecuta en el paso de refuerzos")
            if guide_module.get_pending_reinforcement_preview(props):
                raise RuntimeError("Confirma o descarta primero el refuerzo manual pendiente")
            summary = create_fem_reinforcements(context, replace_existing=True)
        except Exception as exc:
            guide_module._dsg_report(
                self, {'ERROR'},
                f"Frame optimization failed: {exc}",
                f"No se pudo optimizar el frame: {exc}")
            return {'CANCELLED'}

        status = "RECOMMENDED" if summary["recommended"] else "SAFE / REVIEW"
        guide_module._dsg_report(
            self, {'INFO'},
            f"FEM {status}: {summary['active_reinforcements']} reinforcement(s), "
            f"U={summary['max_utilization']:.2f}, sleeve={summary['sleeve_displacement_mm']:.3f} mm. Review and Apply.",
            f"FEM {status}: {summary['active_reinforcements']} refuerzo(s), "
            f"U={summary['max_utilization']:.2f}, sleeve={summary['sleeve_displacement_mm']:.3f} mm. Revisa y aplica.")
        return {'FINISHED'}


_CLASSES = (DSG_OT_OptimizeFrameFEM,)


def register():
    for cls in _CLASSES:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
