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
from bpy.props import FloatProperty, FloatVectorProperty, IntProperty
from mathutils import Matrix, Vector

from . import guide_module
from . import frame_structural_core as core
from . import frame_fem_core as fem
from . import frame_geodesic_paths as geodesic_paths
from . import frame_geodesic_fem as geodesic_fem
from . import frame_contact_core as contact_core
from . import frame_geodesic_groups as geodesic_groups
from . import frame_boolean_section_core as boolean_sections
from . import frame_swept_clearance_core as swept_clearance
from . import frame_sleeve_junction_core as sleeve_junction
from . import frame_perimeter_fem as perimeter_fem
from . import frame_boolean_path_core as boolean_paths
from . import frame_weak_points as weak_points

FRAME_STRUCTURAL_SCHEMA = core.SCHEMA
SUPPORT_KEY = "DSG_frame_support_nodes_json"
SUPPORT_SOURCE_KEY = "DSG_frame_support_identity_source"
SLEEVE_TRANSITION_INSIDE_TOLERANCE_MM = 0.3
# Widest FEM branch radius (2.2 mm) + 0.3 mm: attachments stay this far from
# either sleeve end so the drill access above/below the sleeve stays free.
SLEEVE_ATTACHMENT_END_CLEARANCE_MM = 2.5


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
    if found:
        return found[0]
    frame = bpy.data.objects.get(guide_module.FRAME_NAME)
    if frame is not None:
        return frame
    # After the sleeves are applied the frame is kept, renamed and hidden, as
    # the source of DSG_Guide.  The FEM step (after irrigation) analyses that
    # frame; without this fallback it always failed with "DSG_Frame not found".
    source = bpy.data.objects.get(guide_module.SLEEVE_SOURCE_FRAME_NAME)
    if source is not None and source.type == 'MESH' and len(source.data.polygons):
        return source
    return None


def _passive_obj(context):
    found = guide_module.find_dsg_objects(role=guide_module.ROLE_PASSIVE, obj_type='MESH')
    if found:
        return found[0]
    return bpy.data.objects.get(guide_module.COMBINED_NAME)


# The frame is a closed ring through the clicked support points.  Most cases
# use four (P1..P4); 3–8 points are handled the same way (ring P1..Pn).
MIN_SUPPORTS = 3
MAX_SUPPORTS = 8


def _support_count_ok(points) -> bool:
    return MIN_SUPPORTS <= len(points) <= MAX_SUPPORTS


def _contour_support_points() -> list[Vector]:
    """The four clicked frame points from the contour curve.

    Older frames lost their source points when microscrews were merged into
    them; the contour curve (live, or the latest workflow checkpoint copy)
    still holds the same clicks.  A closing duplicate point is ignored.
    """
    curves = []
    live = bpy.data.objects.get(getattr(guide_module, "CONTOUR_CURVE_NAME", "DSG_ContourCurve"))
    if live is not None:
        curves.append(live)
    suffix = "__" + str(getattr(guide_module, "CONTOUR_CURVE_NAME", "DSG_ContourCurve"))
    saved = [o for o in bpy.data.objects if o.name.startswith("__DSG_Checkpoint_") and o.name.endswith(suffix)]
    curves += sorted(saved, key=lambda o: o.name, reverse=True)
    for curve in curves:
        if curve.type != 'CURVE' or not curve.data.splines:
            continue
        spline = curve.data.splines[0]
        raw = spline.bezier_points if spline.type == 'BEZIER' else spline.points
        points = [curve.matrix_world @ Vector(tuple(p.co)[:3]) for p in raw]
        unique = []
        for p in points:
            if all((p - q).length > 0.05 for q in unique):
                unique.append(p)
        if MIN_SUPPORTS <= len(unique) <= MAX_SUPPORTS:
            return unique
    return []


def _support_nodes(frame_obj) -> tuple[list[dict], str]:
    explicit = _json_points(frame_obj.get(SUPPORT_KEY, "")) if frame_obj is not None else []
    source = "EXPLICIT_SEMANTIC_P1_P4"
    pts = explicit
    if not _support_count_ok(pts):
        pts = _json_points(frame_obj.get("DSG_frame_source_points_json", "")) if frame_obj is not None else []
        source = "FRAME_SOURCE_POINTS_LEGACY_ORDER"
    if not _support_count_ok(pts):
        pts = _contour_support_points()
        source = "CONTOUR_CURVE_POINTS"
    if not _support_count_ok(pts):
        raise RuntimeError(f"El frame necesita entre {MIN_SUPPORTS} y {MAX_SUPPORTS} puntos de apoyo (no se encontraron)")
    rows = []
    for idx, p in enumerate(pts, start=1):
        rows.append({"id": f"P{idx}", "xyz": [float(p.x), float(p.y), float(p.z)]})
    return rows, source


def persist_support_nodes(context, points: list[list[float]], authority: str = "USER") -> dict:
    """Persist explicit P1..P4 semantics without changing frame geometry."""
    frame = _frame_obj(context)
    if frame is None:
        raise RuntimeError("DSG_Frame not found")
    if not _support_count_ok(points):
        raise ValueError(f"Between {MIN_SUPPORTS} and {MAX_SUPPORTS} support points are required")
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
        "single_sleeve_topology": (core.single_sleeve_primary_topology() if len(supports)==4 else __import__(__package__+'.frame_generator',fromlist=['perimeter_sleeve_topology']).perimeter_sleeve_topology([row['id'] for row in supports],sleeves[0]['id'])) if len(sleeves)==1 else None,
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

    ids = [row["id"] for row in ctx["support_nodes"]]
    pairs = [(ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
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
    # Every support keeps its own primary branch to a single sleeve.
    max_candidates = max(int(max_candidates), len(supports) if len(sleeves) == 1 else 1)
    candidates = []

    # Primary invariant branches.  For a single sleeve this exactly represents
    # P1→S←P3 and P2→S←P4, each as an independent support→sleeve branch.
    if len(sleeves) == 1:
        sleeve = sleeves[0]
        ids = list(supports)
        order = (["P1","P3","P2","P4"] if ids == ["P1","P2","P3","P4"] else ids)
        for p_id in order:
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
        if len(candidates) >= max_candidates:
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


def _fem_point_inside_surface(tree, point: Vector, tolerance: float = 0.05) -> bool:
    if tree is None:
        return False
    try:
        hit = tree.find_nearest(point)
    except Exception:
        return False
    if not hit or hit[0] is None or hit[1] is None:
        return False
    return (point - Vector(hit[0])).dot(_fem_safe_unit(hit[1])) < -tolerance


def _fem_sleeve_cardinal_points(sleeve: dict, passive_tree=None) -> tuple[Vector, list[Vector], Matrix]:
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
    # 9.24.10: in a narrow gap the sleeve ring lies inside the neighbouring
    # crowns of the passive model.  An attachment that is inside is moved to
    # the nearest free spot of the sleeve wall: first around the ring (up to
    # 60° away), then along the wall, but never so close to a sleeve end that
    # the widest branch would enter the drill access.
    if passive_tree is None:
        return center, [mx @ p for p in local], mx
    height = float(sleeve.get("height_mm", 6.0))
    max_dz = max(0.0, height * 0.5 - SLEEVE_ATTACHMENT_END_CLEARANCE_MM)
    heights = [0.0] + [s * k * 0.25 for k in range(1, int(max_dz / 0.25) + 1) for s in (1, -1)]
    offsets = [0.0] + [s * d for d in (15.0, 30.0, 45.0, 60.0) for s in (1, -1)]
    points = []
    used = []
    for p in local:
        base = math.degrees(math.atan2(p.y, p.x))
        chosen = None
        for dz in heights:
            for offset in offsets:
                angle = math.radians(base + offset)
                if any(abs((math.degrees(angle) - u + 180.0) % 360.0 - 180.0) < 10.0 for u in used):
                    continue
                candidate = mx @ Vector((r * math.cos(angle), r * math.sin(angle), dz))
                if not _fem_point_inside_surface(passive_tree, candidate, tolerance=0.0):
                    chosen = (candidate, math.degrees(angle))
                    break
            if chosen is not None:
                break
        if chosen is None:
            chosen = (mx @ p, base)
        points.append(chosen[0])
        used.append(chosen[1])
    return center, points, mx


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


def _fem_build_model(context=None, *, geodesic_candidates=False):
    context = context or bpy.context
    props = context.scene.dsg_props
    frame_ctx = get_frame_context(context)
    supports = [Vector(row["xyz"]) for row in frame_ctx["support_nodes"]]
    sleeves = list(frame_ctx.get("sleeves") or [])
    if not _support_count_ok(supports):
        raise RuntimeError(f"GenerativeFrame FEM requiere entre {MIN_SUPPORTS} y {MAX_SUPPORTS} puntos de apoyo")
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
    attachment_tree = None
    if True:  # both the clinical and the geodesic models
        passive = _passive_obj(context)
        if passive is not None:
            try:
                attachment_tree = guide_module._build_world_surface_bvh(context, passive)
            except Exception:
                attachment_tree = None

    for sleeve_index, sleeve in enumerate(sleeves):
        center, attachment_points, mx = _fem_sleeve_cardinal_points(sleeve, attachment_tree)
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
                # Experimental geodesic model builds curved surface paths later.
                # A rejected straight chord must not exclude a valid geodesic.
                if not geodesic_candidates and keep_out(a, b):
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



def _fem_build_geodesic_model(context=None) -> dict:
    """Read-only experimental FEM model with true surface-following beam chains.

    This does not mutate Blender geometry and is not the clinical STEP 6
    replacement. Exact triangular anchors are routed on the evaluated passive
    surface using the same graph as the native DSG frame.
    """
    context = context or bpy.context
    model = _fem_build_model(context, geodesic_candidates=True)
    passive = _passive_obj(context)
    if not guide_module._valid_obj(passive):
        raise RuntimeError("GEODESIC_NO_PASSIVE_SURFACE: el modelo pasivo no está disponible")
    cache, _reused, error = guide_module._build_frame_surface_graph_cache(context, passive)
    if cache is None:
        raise RuntimeError(f"GEODESIC_GRAPH_UNAVAILABLE: {error}")
    tree, _mx, _inv, reason = guide_module._frame_width_surface_bvh(context, passive, cache)
    if tree is None:
        raise RuntimeError(f"GEODESIC_SURFACE_BVH_UNAVAILABLE: {reason}")

    original = list(model["elements"])
    virtual = [e for e in original if e.virtual]
    candidate_beams = [e for e in original if e.render and not e.virtual]
    nodes = model["nodes"]
    new_elements = list(virtual)
    # The existing P1-P4 frame must be represented in the *same* experimental
    # stiffness/volume network. All four frame paths use the identical
    # triangle-face geodesic routing primitive as the reinforcement routes.
    support_count = len(model.get("frame_context", {}).get("support_nodes", []))
    if not 3 <= support_count <= 8:  # same range as MIN_SUPPORTS..MAX_SUPPORTS
        raise RuntimeError("PERIMETER_SUPPORT_IDENTITIES_MISSING")
    perimeter_paths = []
    for start_id, end_id in ((i, (i + 1) % support_count) for i in range(support_count)):
        start = Vector(tuple(float(v) for v in nodes[start_id].xyz))
        finish = Vector(tuple(float(v) for v in nodes[end_id].xyz))
        p0 = guide_module._frame_surface_projection(
            cache, start, max_distance_mm=1.0)
        p1 = guide_module._frame_surface_projection(
            cache, finish, max_distance_mm=1.0)
        if (p0 is None or p1 is None or not p0.get("triangle_vertices")
                or not p1.get("triangle_vertices")):
            raise RuntimeError(
                f"NO_VALID_PERIMETER_SURFACE_ANCHOR: P{start_id+1}/P{end_id+1}"
            )
        route = geodesic_paths.route_surface_face_anchors(
            cache["coords"], cache["csr_offsets"], cache["csr_dst"],
            cache["csr_weights"], p0["triangle_vertices"], tuple(p0["point"]),
            p1["triangle_vertices"], tuple(p1["point"]),
        )
        coords = [np.array(nodes[start_id].xyz, dtype=float)]
        coords.extend(np.asarray(p, dtype=float) for p in route.points_mm)
        coords.append(np.array(nodes[end_id].xyz, dtype=float))
        samples = [coords[0]]
        for a, b in zip(coords, coords[1:]):
            distance = float(np.linalg.norm(b-a))
            if distance <= 1e-7:
                continue
            for k in range(1, max(1, int(math.ceil(distance/1.5)))+1):
                count = max(1, int(math.ceil(distance/1.5)))
                samples.append(a+(b-a)*k/count)
        if len(samples)>1 and np.linalg.norm(samples[0]-samples[-1]) <= 1e-8:
            raise RuntimeError("PERIMETER_DEGENERATE_EDGE")
        perimeter_paths.append(samples)
    frame_radius = float(model["frame_context"]["frame_radius_mm"])
    frame_template = _fem_material_element(
        0, 1, frame_radius, tag="FRAME_PERIMETER",
        render=True, locked_radius=True, prunable=False, virtual=False,
    )
    frame_loop = perimeter_fem.append_perimeter_loop(
        nodes, new_elements, tuple(range(support_count)), perimeter_paths,
        radius_mm=frame_radius, template=frame_template,
        max_segment_mm=1.51,
    )
    if len(nodes)>2200:
        raise RuntimeError("PERIMETER_FEM_MODEL_TOO_LARGE")
    model["perimeter_routes"] = list(frame_loop.edges)
    model["perimeter_length_mm"] = float(frame_loop.length_mm)
    model["perimeter_included_in_nominal_volume"] = True
    model["perimeter_support_contact_calibrated"] = False
    accepted = []
    rejected = []
    sleeve_list = list(model.get("frame_context", {}).get("sleeves", []))
    sleeve_by_attachment = {}
    for record in model.get("sleeve_records", []):
        sleeve_id = str(record["id"])
        for node_id in record["attachment_nodes"]:
            if int(node_id) in sleeve_by_attachment:
                raise RuntimeError("DUPLICATE_SLEEVE_ATTACHMENT_OWNER")
            sleeve_by_attachment[int(node_id)] = sleeve_id
    if not sleeve_list or not sleeve_by_attachment:
        raise RuntimeError("GEODESIC_LUMEN_GEOMETRY_MISSING: sleeve mapping required")
    # 9.24.11: reinforcements start at the frame's weak points (found from
    # the frame and its own FEM response, without the IOS) and are then
    # routed over the IOS surface to the sleeve.  The support-based branches
    # stay as secondary candidates: the FEM keeps them only if the
    # weak-point branches alone cannot hold the sleeve within its limits.
    weak_candidates, weak_rows = _weak_point_candidates(model, nodes, new_elements, frame_loop, candidate_beams)
    model["weak_points"] = weak_rows
    candidate_beams = list(weak_candidates) + list(candidate_beams)
    served = set()
    # The nominal tubular FEM remains a design aid; no post-Boolean sections
    # or contact retention claims are made by this analysis.
    for candidate in candidate_beams:
        owner = candidate.tag.split("_")[0] if candidate.tag.startswith("WEAK") else None
        if owner is not None and owner in served:
            continue
        label = f"{candidate.tag}_ATT{int(candidate.j)}"
        support = Vector(tuple(float(v) for v in nodes[candidate.i].xyz))
        attachment = Vector(tuple(float(v) for v in nodes[candidate.j].xyz))
        source = guide_module._frame_surface_projection(cache, support, max_distance_mm=1.0)
        target = guide_module._frame_surface_projection(cache, attachment)
        if source is None or target is None or not source.get("triangle_vertices") or not target.get("triangle_vertices"):
            rejected.append({"candidate": label, "reason": "NO_SURFACE_FACE_ANCHOR"})
            continue
        # Sleeve transitions must depart towards the outer surface, not through
        # the passive model. A longer transition is allowed only after a future
        # explicit multi-surface clearance validator is implemented.
        terminal_offset = attachment - Vector(target["point"])
        normal = Vector(target["normal"])
        # 9.24.10: sleeve-ring attachments are sampled points; one lying a few
        # tenths of a millimetre under the tessellated surface is on it.
        if terminal_offset.length > 12.0 or terminal_offset.dot(normal) < -SLEEVE_TRANSITION_INSIDE_TOLERANCE_MM:
            rejected.append({"candidate": label, "reason": "UNSAFE_SLEEVE_TRANSITION"})
            continue
        # keep_out rejects any segment shorter than 0.2 mm, so only a real
        # transition (not a sub-0.2 mm touch to the surface) is tested.
        if terminal_offset.length > 0.20 and model["keep_out"](
            np.asarray(tuple(target["point"]), dtype=float),
            np.asarray(tuple(attachment), dtype=float),
        ):
            rejected.append({"candidate": label, "reason": "TRANSITION_CROSSES_PROTECTED_VOLUME"})
            continue
        try:
            route = geodesic_paths.route_surface_face_anchors(
                cache["coords"], cache["csr_offsets"], cache["csr_dst"], cache["csr_weights"],
                source["triangle_vertices"], tuple(source["point"]),
                target["triangle_vertices"], tuple(target["point"]),
            )
        except (ValueError, geodesic_paths.NoValidSurfaceRoute) as exc:
            rejected.append({"candidate": label, "reason": str(exc)})
            continue

        anchors = [np.asarray(tuple(support), dtype=float)]
        # Preserve every intrinsic bend. Splitting single surface edges is
        # permitted; joining nonadjacent vertices with a chord is not.
        anchors.extend(np.asarray(point, dtype=float) for point in route.points_mm)
        anchors.append(np.asarray(tuple(attachment), dtype=float))
        fine = [anchors[0]]
        for a, b in zip(anchors, anchors[1:]):
            length = float(np.linalg.norm(b - a))
            if length < 0.02:
                continue
            divisions = max(1, int(math.ceil(length / 1.5)))
            for k in range(1, divisions + 1):
                fine.append(a + (b - a) * (k / divisions))
        # Ensure exact FEM node poses even when coincident samples were removed.
        fine[0] = np.array(nodes[candidate.i].xyz, dtype=float)
        fine[-1] = np.array(nodes[candidate.j].xyz, dtype=float)
        if len(fine) < 2 or len(nodes) + len(fine) > 2200:
            raise RuntimeError(
                "GEODESIC_FEM_MODEL_TOO_LARGE: refine/condense the route before solving"
            )
        target_sleeve_id = sleeve_by_attachment.get(int(candidate.j))
        if target_sleeve_id is None:
            rejected.append({"candidate": label, "reason": "UNMAPPED_SLEEVE_ATTACHMENT"})
            continue
        try:
            sweep = sleeve_junction.preflight_sleeve_junction(
                fine, [float(candidate.radius_mm)] * len(fine), sleeve_list,
                target_sleeve_id=target_sleeve_id,
                maximum_deferred_tip_mm=2.0,
            )
        except (sleeve_junction.InvalidSleeveJunction,
                swept_clearance.InvalidClearanceGeometry) as exc:
            rejected.append({"candidate": label,
                             "reason": f"JUNCTION_PRECHECK_INVALID: {exc}"})
            continue
        if not sweep.candidate_admissible:
            rejected.append({
                "candidate": label,
                "reason": sweep.status,
                "target_sleeve": target_sleeve_id,
            })
            continue
        # 9.24.10: the drill must pass the sleeve ends freely even at the
        # largest radius the optimizer may give this branch.
        widest = float(getattr(model.get("config"), "radius_max_mm", candidate.radius_mm) or candidate.radius_mm)
        drill = swept_clearance.check_swept_tube_clearance(
            fine, [widest] * len(fine), _drill_access_zones(sleeve_list), sample_spacing_mm=0.2)
        if not drill.clear:
            rejected.append({"candidate": label, "reason": f"DRILL_ACCESS_{drill.status}"})
            continue
        ids = geodesic_fem.append_geodesic_beams(
            nodes, new_elements, fine,
            start_node=int(candidate.i), end_node=int(candidate.j),
            beam_template=candidate, label=label, max_segment_mm=1.51,
        )
        accepted.append({
            "candidate": label,
            "beam_elements": len(ids),
            "beam_indices": list(ids),
            "curve_points_mm": [list(map(float, point)) for point in fine],
            "surface_length_mm": float(route.surface_length_mm),
            "terminal_transition_mm": float(terminal_offset.length),
            "geodesic_backend": str(route.backend),
            "sleeve_junction_preflight": sweep.status,
            "target_sleeve": sweep.target_sleeve,
            "deferred_weld_tip_mm": float(sweep.deferred_tip_mm),
            "swept_lumen_zone_count": int(sweep.declared_lumens),
            "post_boolean_lumen_validation_required": True,
            "final_lumen_clear": False,
            "whole_anatomy_sweep_validated": False,
        })
        if owner is not None:
            served.add(owner)

    if len(accepted) < 2:
        raise RuntimeError(
            "NO_VALID_GEODESIC_FEM_MODEL: se requieren al menos dos ramas válidas. "
            f"Descartadas: {rejected[:6]}"
        )
    model["elements"] = new_elements
    model["config"].enable_topology_growth = False
    model["config"].max_growth_rounds = 0
    model["route_mode"] = "SURFACE_GEODESIC_EXPERIMENTAL_READ_ONLY"
    model["geodesic_routes"] = accepted
    model["rejected_geodesic_routes"] = rejected
    return model


def _frame_loop_chain(new_elements, frame_loop) -> list:
    """Ordered node indices along the closed frame loop (last repeat dropped)."""
    chain = []
    for record in frame_loop.edges:
        for beam_id in record["beam_indices"]:
            beam = new_elements[int(beam_id)]
            if not chain:
                chain.append(int(beam.i))
            chain.append(int(beam.j))
    if len(chain) > 1 and chain[0] == chain[-1]:
        chain.pop()
    return chain


def _frame_mechanics(model, nodes, new_elements, chain):
    """Frame-only FEM: per loop node, deflection and bending utilization.

    The sleeve is tied to the two nearest frame nodes by a resin link that
    stands for the guide body around it; supports stay clamped.  Solving
    K u = F for the sleeve load cases gives the frame's elastic curve, and
    the beam results give its bending (sigma = M*y/I) along the loop.
    """
    from dataclasses import replace
    elements = list(new_elements)
    frame_radius = float(model["frame_context"]["frame_radius_mm"])
    for record in model.get("sleeve_records", []):
        center = int(record["center_node"])
        c = np.asarray(nodes[center].xyz, float)
        nearest = sorted(chain, key=lambda k: float(np.linalg.norm(np.asarray(nodes[k].xyz, float) - c)))[:2]
        for k in nearest:
            elements.append(_fem_material_element(
                center, int(k), frame_radius, tag="GUIDE_BODY_LINK",
                render=False, locked_radius=True, prunable=False, virtual=True))
    bundle = fem.solve_load_cases(nodes, elements, model["load_cases"], monitor_nodes=model["monitor_nodes"])
    displacement = np.zeros(len(chain))
    for u in bundle.displacements:
        for pos, k in enumerate(chain):
            displacement[pos] = max(displacement[pos], float(np.linalg.norm(u[k * 6:k * 6 + 3])))
    bending = np.zeros(len(chain))
    position = {k: pos for pos, k in enumerate(chain)}
    for e_index, e in enumerate(elements):
        row = bundle.worst_results[e_index] if e_index < len(bundle.worst_results) else None
        if row is None or e.virtual:
            continue
        for k in (int(e.i), int(e.j)):
            if k in position:
                bending[position[k]] = max(bending[position[k]], float(row.get("bending_ratio", 0.0)))
    return displacement, bending


def _weak_points_by_stiffening(model, nodes, new_elements, chain, coords, sleeves, supports, radius, count):
    """Weak points from the frame-only FEM (no IOS).

    Every frame point outside the sleeve and support zones is tried as the
    end of a straight resin link to the sleeve; the point whose link lowers
    the sleeve displacement most is the frame's weakest spot for that load
    (it closes the most effective triangle).  Chosen greedily, one per round.
    """
    base = list(new_elements)
    frame_radius = float(model["frame_context"]["frame_radius_mm"])
    centers = [int(r["center_node"]) for r in model.get("sleeve_records", [])]
    for center in centers:
        c = np.asarray(nodes[center].xyz, float)
        for k in sorted(chain, key=lambda k: float(np.linalg.norm(np.asarray(nodes[k].xyz, float) - c)))[:2]:
            base.append(_fem_material_element(center, int(k), frame_radius, tag="GUIDE_BODY_LINK",
                                              render=False, locked_radius=True, prunable=False, virtual=True))
    candidates = []
    # Probe every ~6 mm of frame plus every corner / straight-run midpoint;
    # each probe is a full solve, so the set is kept small (< ~60).
    # (the chain is sampled very unevenly, so probes are spaced by arc length)
    arc = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(coords, axis=0), axis=1))))
    marks = np.arange(0.0, float(arc[-1]), 3.0)
    by_arc = {int(np.searchsorted(arc, m)) for m in marks}
    probe = sorted({min(i, len(chain) - 1) for i in by_arc}
                   | {i for i, _k, _s in weak_points.candidates(coords, closed=True)})
    for pos in probe:
        p = coords[pos]
        if min(float(np.linalg.norm(p - c)) - r for c, r in sleeves) < weak_points.SLEEVE_EXCLUSION_MM:
            continue
        if any(float(np.linalg.norm(p - q)) < weak_points.SUPPORT_EXCLUSION_MM for q in supports):
            continue
        candidates.append(pos)
    if not candidates:
        return []
    bonus = {i: s for i, _k, s in weak_points.candidates(coords, closed=True)}

    def sleeve_displacement(chosen):
        elements = list(base)
        for pos in chosen:
            k = int(chain[pos])
            center = min(centers, key=lambda c: float(np.linalg.norm(np.asarray(nodes[c].xyz, float) - coords[pos])))
            elements.append(_fem_material_element(center, k, radius, tag="WEAK_PROBE",
                                                  render=False, locked_radius=True, prunable=False, virtual=False))
        bundle = fem.solve_load_cases(nodes, elements, model["load_cases"], monitor_nodes=model["monitor_nodes"])
        return bundle.max_monitor_displacement_mm

    picks = weak_points.greedy_by_stiffening(coords, candidates, sleeve_displacement, count=count, bonus=bonus)
    rows = []
    for pos, displacement, gain in picks:
        kind = next((k for i, k, _s in weak_points.candidates(coords, closed=True) if i == pos), "MECHANICAL")
        rows.append({"index": int(pos), "point": coords[pos].copy(), "kind": kind, "score": float(gain),
                     "distance_mm": min(float(np.linalg.norm(coords[pos] - c)) for c, _r in sleeves),
                     "sleeve_displacement_after_mm": float(displacement)})
    return rows


def _weak_point_candidates(model, nodes, new_elements, frame_loop, candidate_beams):
    chain = _frame_loop_chain(new_elements, frame_loop)
    if len(chain) < 8:
        return [], []
    coords = np.asarray([nodes[k].xyz for k in chain], float)
    sleeves = [(np.asarray(s["center"], float), float(s["outer_radius_mm"]))
               for s in model.get("frame_context", {}).get("sleeves", [])]
    # Support nodes are the first nodes of the model (P1..Pn, clamped).
    supports = [np.asarray(nodes[i].xyz, float)
                for i in range(len(model.get("frame_context", {}).get("support_nodes", [])))]
    radius = float(candidate_beams[0].radius_mm) if candidate_beams else 1.0
    count = min(5, 3 + len(sleeves))
    rows = None
    try:
        rows = _weak_points_by_stiffening(model, nodes, new_elements, chain, coords, sleeves, supports, radius, count)
    except Exception as exc:
        _DSG_LOG.warning("Frame-only FEM for weak points failed: %s", exc)
    if not rows:
        rows = weak_points.select(coords, sleeves, supports=supports, closed=True, count=count)
    attachments = [int(n) for record in model.get("sleeve_records", []) for n in record["attachment_nodes"]]
    out, info = [], []
    for rank, row in enumerate(rows, start=1):
        node = int(chain[row["index"]])
        p = np.asarray(nodes[node].xyz, float)
        info.append({"rank": rank, "node": node, "kind": row["kind"], "score": float(row["score"]),
                     "distance_mm": float(row["distance_mm"]), "point": [float(v) for v in p]})
        for att in sorted(attachments, key=lambda a: float(np.linalg.norm(np.asarray(nodes[a].xyz, float) - p))):
            out.append(_fem_material_element(
                node, att, radius, tag=f"WEAK{rank}_{row['kind']}",
                render=True, locked_radius=False, prunable=True, virtual=False))
    return out, info


def analyze_geodesic_frame_fem(context=None) -> dict:
    """Compare stiffness/volume of curved routes without replacing clinical guides."""
    model = _fem_build_geodesic_model(context)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"], config=model["config"],
        keep_out_check=model["keep_out"],
    )
    summary = _fem_summary(model, result)
    summary.update(
        routing_mode=model["route_mode"],
        geodesic_routes=model["geodesic_routes"],
        rejected_geodesic_routes=model["rejected_geodesic_routes"],
        perimeter_length_mm=float(model.get("perimeter_length_mm", 0.0)),
        perimeter_beam_elements=sum(len(e["beam_indices"]) for e in model.get("perimeter_routes", [])),
        perimeter_included_in_nominal_volume=bool(model.get("perimeter_included_in_nominal_volume")),
        perimeter_support_contact_calibrated=False,
        post_boolean_lumen_validated=False,
        experimental=True,
        post_boolean_section_validated=False,
        geometry_mutated=False,
    )
    return summary



def estimate_geodesic_frame_contact(context=None, *, policy: contact_core.ContactPolicy) -> dict:
    """Read-only local planar contact estimate using the actual optimized FEM radii.

    The estimated contact and remaining section are based on normals of the
    passive model. They are NOT post-Boolean measurements, and do not assert
    adequate clinical retention or mechanical strength.
    """
    context = context or bpy.context
    model = _fem_build_geodesic_model(context)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"], config=model["config"],
        keep_out_check=model["keep_out"],
    )
    passive = _passive_obj(context)
    cache, _reused, error = guide_module._build_frame_surface_graph_cache(context, passive)
    if cache is None:
        raise RuntimeError(f"CONTACT_NO_SURFACE: {error}")

    route_results = []
    skipped_routes = []
    for route in model["geodesic_routes"]:
        try:
            route_results.append(_contact_route_result(route, model, cache, policy))
        except (contact_core.NoFeasibleContact, RuntimeError) as exc:
            # 9.24.10: one route over a folded/degenerate patch of the passive
            # surface no longer cancels the estimate for the other routes.
            skipped_routes.append({"label": str(route["candidate"]), "reason": str(exc)})
    if not route_results:
        reasons = "; ".join(f"{r['label']}: {r['reason']}" for r in skipped_routes)
        raise RuntimeError(f"CONTACT_NO_FEASIBLE_ROUTE: {reasons}")
    return _contact_report(route_results, skipped_routes, result, model)


def _contact_route_result(route, model, cache, policy):
    points = np.asarray(route["curve_points_mm"], dtype=float)
    beams = [model["elements"][int(i)] for i in route["beam_indices"]]
    if len(points) != len(beams) + 1:
        raise RuntimeError("CONTACT_FEM_ROUTE_MISMATCH")
    radii = [
        float(beams[0].radius_mm),
        *[(float(a.radius_mm) + float(b.radius_mm)) * 0.5
          for a, b in zip(beams, beams[1:])],
        float(beams[-1].radius_mm),
    ]
    surf_positions, normals, sample_indices = [], [], []
    for index, point in enumerate(points):
        projection = guide_module._frame_surface_projection(
            cache, Vector(tuple(float(v) for v in point)), max_distance_mm=0.03
        )
        if projection is None:
            continue
        if float(projection["distance_mm"]) > 0.03:
            continue
        surf_positions.append(tuple(float(v) for v in projection["point"]))
        normals.append(tuple(float(v) for v in projection["normal"]))
        sample_indices.append(index)
    if (len(sample_indices) < 2 or
            sample_indices[-1] - sample_indices[0] + 1 != len(sample_indices)):
        raise RuntimeError(
            "CONTACT_SURFACE_ROUTE_INCOMPLETE: model path has unverified surface samples"
        )
    estimate = contact_core.estimate_contact_route(
        surf_positions, normals,
        [radii[i] for i in sample_indices], policy
    )
    return {
        "label": str(route["candidate"]),
        "surface_samples": len(sample_indices),
        "contact_area_planar_estimate_mm2": float(estimate.estimated_contact_area_mm2),
        "retained_volume_planar_estimate_mm3": float(estimate.estimated_retained_volume_mm3),
        "nominal_volume_planar_estimate_mm3": float(estimate.nominal_volume_mm3),
        "min_retained_area_ratio": float(estimate.min_retained_area_ratio),
        "min_bending_inertia_ratio": float(estimate.min_bending_inertia_ratio),
        "min_penetration_mm": min(float(x.penetration_mm) for x in estimate.sections),
        "max_penetration_mm": max(float(x.penetration_mm) for x in estimate.sections),
        "max_center_offset_mm": max(float(x.center_offset_mm) for x in estimate.sections),
    }


def _contact_report(route_results, skipped_routes, result, model):
    return {
        "schema": "dsg.generative_frame_contact_estimate.v1",
        "skipped_routes": skipped_routes,
        "mode": "READ_ONLY_LOCAL_PLANAR_APPROXIMATION",
        "experimental": True,
        "post_boolean_validated": False,
        "retention_validated": False,
        "torsion_after_boolean_validated": False,
        "material_calibrated": False,
        "feasible_routes": len(route_results),
        "routes": route_results,
        "contact_area_planar_estimate_mm2": float(sum(
            x["contact_area_planar_estimate_mm2"] for x in route_results)),
        "retained_volume_planar_estimate_mm3": float(sum(
            x["retained_volume_planar_estimate_mm3"] for x in route_results)),
        "hard_safe_nominal_fem": bool(result.hard_safe),
        "perimeter_included_in_nominal_volume": bool(model.get("perimeter_included_in_nominal_volume")),
        "perimeter_support_contact_calibrated": False,
        "post_boolean_lumen_validated": False,
        "warning": ("This is an uncalibrated local tangent-plane diagnostic; "
                    "no actual Boolean, retention measurement or validated "
                    "post-Boolean FEM was performed."),
    }




def analyze_geodesic_group_topology(context=None) -> dict:
    """Balanced, read-only group pruning after the nominal curved-beam FEM run.

    Entire routes are removed or retained. This is not the clinical apply path.
    """
    context = context or bpy.context
    model = _fem_build_geodesic_model(context)
    solved = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"], config=model["config"],
        keep_out_check=model["keep_out"],
    )
    if not solved.hard_safe:
        raise RuntimeError("BASELINE_FEM_UNSAFE: geodesic candidate network is not structurally feasible")
    groups = {str(route["candidate"]): tuple(int(i) for i in route["beam_indices"])
              for route in model["geodesic_routes"]}
    if len(groups) != len(model["geodesic_routes"]):
        raise RuntimeError("DUPLICATED_GEODESIC_GROUP_LABEL")
    result = geodesic_groups.prune_geodesic_groups(
        model["nodes"], model["elements"], model["load_cases"], model["monitor_nodes"],
        groups, config=model["config"], stiffness_weight=0.5,
        min_remaining_groups=2,
    )
    return {
        "schema": "dsg.geodesic_group_pruning.v1",
        "objective": "BALANCED_NOMINAL_VOLUME_AND_COMPLIANCE",
        "perimeter_length_mm": float(model.get("perimeter_length_mm", 0.0)),
        "perimeter_included_in_nominal_volume": bool(model.get("perimeter_included_in_nominal_volume")),
        "perimeter_support_contact_calibrated": False,
        "post_boolean_lumen_validated": False,
        "active_groups": list(result.active_groups),
        "removed_groups": list(result.removed_groups),
        "material_volume_mm3": float(result.material_volume_mm3),
        "compliance_Nmm": float(result.compliance_Nmm),
        "balanced_objective": float(result.balanced_objective),
        "max_utilization": float(result.max_utilization),
        "max_displacement_mm": float(result.max_displacement_mm),
        "history": list(result.iterations),
        "experimental": True,
        "geometry_mutated": False,
        "post_boolean_validated": False,
        "contact_retention_validated": False,
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


def _validate_fem_candidate_sweep(context, model: dict, result) -> dict:
    """Hard preBoolean sweep before replacing any previously confirmed curves.

    A bounded outer-sleeve terminal weld is provisional. It still requires
    the actual final Boolean lumen/wall and manufacturer drill-access gates.
    """
    frame_ctx = model.get("frame_context") or {}
    sleeves = list(frame_ctx.get("sleeves") or [])
    sleeve_records = list(model.get("sleeve_records") or [])
    if not sleeves or len(sleeves) != len(sleeve_records):
        raise RuntimeError("FEM_SWEEP_MISSING_SLEEVE_RECORDS")
    attachments = {}
    for record in sleeve_records:
        for idx in record.get("attachment_nodes", ()):
            if int(idx) in attachments:
                raise RuntimeError("FEM_SWEEP_AMBIGUOUS_SLEEVE_ATTACHMENT")
            attachments[int(idx)] = str(record["id"])
    if not attachments:
        raise RuntimeError("FEM_SWEEP_NO_VALID_SLEEVE_ATTACHMENTS")

    lumens, drill_extensions = [], []
    for sleeve in sleeves:
        center = np.asarray(sleeve["center"], dtype=float)
        axis = np.asarray(sleeve["axis"], dtype=float)
        length = float(np.linalg.norm(axis))
        radius = float(sleeve["inner_radius_mm"])
        height = float(sleeve["height_mm"])
        if (center.shape != (3,) or not np.isfinite(center).all()
                or axis.shape != (3,) or not np.isfinite(axis).all()
                or length < 1e-9 or not np.isfinite([radius,height]).all()
                or radius <= 0 or height <= 0):
            raise RuntimeError("FEM_SWEEP_INVALID_SLEEVE")
        axis /= length
        lumens.append(swept_clearance.CylinderKeepOut(
            f"{sleeve['id']}:LUMEN", tuple(center), tuple(axis),radius,height*0.5))
        # Deliberately conservative 20mm uncalibrated access on BOTH ends.
        # This is a precheck, not verified patient/tool drilling clearance.
        extension=20.0
        for sign in (-1,1):
            shifted = center + axis * sign * (height*0.5 + extension*0.5)
            drill_extensions.append(swept_clearance.CylinderKeepOut(
                f"{sleeve['id']}:DRILL_{sign:+d}", tuple(shifted),
                tuple(axis),radius,extension*0.5))

    protected = []
    for obj in bpy.data.objects:
        if not (bool(obj.get("DSG_irrigation_wall_confirmed",False))
                or bool(obj.get("DSG_microscrew_confirmed",False))):
            continue
        if getattr(obj,"type",None) != 'MESH':
            raise RuntimeError(f"FEM_SWEEP_UNSUPPORTED_PROTECTED_OBJECT: {obj.name}")
        bvh = guide_module._build_world_surface_bvh(context,obj)
        if bvh is None:
            raise RuntimeError(f"FEM_SWEEP_PROTECTED_BVH_UNAVAILABLE: {obj.name}")
        protected.append((str(obj.name), bvh))

    checked=0
    for idx in result.active_elements:
        beam=model["elements"][idx]
        if not beam.active or not beam.render or beam.virtual:
            continue
        a=np.asarray(model["nodes"][beam.i].xyz,dtype=float)
        b=np.asarray(model["nodes"][beam.j].xyz,dtype=float)
        radius=float(beam.radius_mm)
        if not np.isfinite([*a,*b,radius]).all() or radius<=0:
            raise RuntimeError("FEM_SWEEP_NONFINITE_BEAM")
        length=float(np.linalg.norm(b-a))
        if length<=0.1:
            raise RuntimeError("FEM_SWEEP_DEGENERATE_BEAM")
        path=[a,b]
        radii=[radius,radius]
        target_id=attachments.get(int(beam.j))
        if target_id:
            pre=sleeve_junction.preflight_sleeve_junction(
                path,radii,sleeves,target_sleeve_id=target_id,
                maximum_deferred_tip_mm=min(2.5,max(0.25,length*0.25)))
            if not pre.candidate_admissible:
                raise RuntimeError(
                    f"FEM_SWEEP_TARGET_LUMEN_{pre.status}: {beam.tag}")
        else:
            full=swept_clearance.check_swept_tube_clearance(
                path,radii,lumens,sample_spacing_mm=0.2)
            if not full.clear:
                raise RuntimeError(f"FEM_SWEEP_LUMEN_{full.status}: {beam.tag}")

        drill=swept_clearance.check_swept_tube_clearance(
            path,radii,drill_extensions,sample_spacing_mm=0.2)
        if not drill.clear:
            raise RuntimeError(f"FEM_SWEEP_DRILL_{drill.status}: {beam.tag}")
        if protected:
            intervals=max(1,int(math.ceil(length/0.5)))
            for step in range(intervals+1):
                point=Vector(tuple(float(x) for x in
                    (a+(b-a)*(step/intervals))))
                for name,tree in protected:
                    hit=tree.find_nearest(point)
                    if not hit or hit[0] is None or hit[1] is None:
                        raise RuntimeError(f"FEM_SWEEP_NO_SURFACE: {name}")
                    surface,normal=Vector(hit[0]),Vector(hit[1])
                    if (point-surface).length<=radius+0.2 or (point-surface).dot(normal)<0:
                        raise RuntimeError(f"FEM_SWEEP_PROTECTED_OBJECT: {name}")
        checked+=1
    if checked==0:
        raise RuntimeError("FEM_SWEEP_NO_RENDERABLE_BEAMS")
    return {
        "candidate_tubes":checked,
        "sleeve_lumens":len(lumens),
        "drill_extension_zones":len(drill_extensions),
        "protected_meshes":len(protected),
        "post_boolean_lumen_validated":False,
        "clinical_acceptance":False,
    }


def _fem_straight_reinforcement_pieces(model, result) -> list:
    pieces = []
    for element_index in result.active_elements:
        e = model["elements"][element_index]
        if not e.active or not e.render or e.virtual:
            continue
        p0 = Vector(tuple(float(v) for v in model["nodes"][e.i].xyz))
        p1 = Vector(tuple(float(v) for v in model["nodes"][e.j].xyz))
        if (p1 - p0).length < 0.5:
            continue
        pieces.append({"element_index": int(element_index), "points": [p0, p1],
                       "radius_mm": float(e.radius_mm), "tag": str(e.tag), "mode": "STRAIGHT"})
    return pieces


def _fem_geodesic_reinforcement_pieces(context):
    """Optimized surface-routed branches as reinforcement pieces (one per route).

    A route is kept when its FEM chain survived pruning; it is drawn with the
    largest optimized radius of its chain (conservative, one bevel per curve).
    The perimeter loop is the existing frame and is never re-created.
    """
    model = _fem_build_geodesic_model(context)
    _keep_minimal_route_set(model)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"], config=model["config"],
        keep_out_check=model["keep_out"],
    )
    if not result.hard_safe:
        summary = _fem_summary(model, result)
        raise RuntimeError(f"U={summary['max_utilization']:.2f}, "
                           f"desplazamiento={summary['sleeve_displacement_mm']:.3f} mm")
    active = set(int(i) for i in result.active_elements)
    pieces = []
    for route in model["geodesic_routes"]:
        indices = [int(i) for i in route["beam_indices"]]
        beams = [model["elements"][i] for i in indices]
        if not indices or not all(i in active and model["elements"][i].active for i in indices):
            continue
        points = [Vector(tuple(float(v) for v in p)) for p in route["curve_points_mm"]]
        radius = max(float(b.radius_mm) for b in beams)
        worst = max(indices, key=lambda i: float(model["elements"][i].radius_mm))
        pieces.append({"element_index": worst, "points": points, "radius_mm": radius,
                       "tag": str(route["candidate"]), "mode": "GEODESIC_SURFACE",
                       "length_mm": float(sum((b - a).length for a, b in zip(points, points[1:]))),
                       "target_sleeve": route.get("target_sleeve")})
    if len(pieces) < 2:
        raise RuntimeError("menos de dos rutas sobre la superficie sobreviven a la optimización")
    return model, result, pieces


def _drill_access_zones(sleeves, extension=20.0):
    """Uncalibrated drill-access cylinders beyond both ends of every sleeve."""
    zones = []
    for sleeve in sleeves:
        center = np.asarray(sleeve["center"], dtype=float)
        axis = np.asarray(sleeve["axis"], dtype=float)
        axis = axis / max(1e-9, float(np.linalg.norm(axis)))
        radius = float(sleeve["inner_radius_mm"]); height = float(sleeve["height_mm"])
        for sign in (-1, 1):
            shifted = center + axis * sign * (height * 0.5 + extension * 0.5)
            zones.append(swept_clearance.CylinderKeepOut(
                f"{sleeve['id']}:DRILL_{sign:+d}", tuple(shifted), tuple(axis), radius, extension * 0.5))
    return zones


def _keep_minimal_route_set(model):
    """Keep the weak-point branches, adding support branches only if needed.

    Every branch is evaluated at the widest allowed radius (one linear solve
    each): support branches are added one by one, the most effective first,
    until the sleeve displacement reaches the design target.  The others are
    switched off (their beams inactive, their inner nodes fixed so K stays
    regular) before the FEM sizes the radii.
    """
    routes = list(model.get("geodesic_routes") or [])
    if not routes:
        return
    nodes, elements = model["nodes"], model["elements"]
    config = model["config"]
    r_max = float(getattr(config, "radius_max_mm", 2.2))
    target = float(getattr(config, "displacement_design_target_mm", 0.15))
    saved = {}

    def route_nodes(route):
        ids = [int(i) for i in route["beam_indices"]]
        ends = {int(elements[ids[0]].i), int(elements[ids[-1]].j)}
        inner = {int(elements[i].i) for i in ids} | {int(elements[i].j) for i in ids}
        return ids, inner - ends

    def apply(subset):
        for route in routes:
            ids, inner = route_nodes(route)
            on = route in subset
            for i in ids:
                saved.setdefault(("e", i), (elements[i].active, elements[i].radius_mm))
                elements[i].active = on
                if on:
                    elements[i].radius_mm = r_max
            for n in inner:
                saved.setdefault(("n", n), np.array(nodes[n].fixed, dtype=bool))
                nodes[n].fixed = saved[("n", n)].copy() if on else np.ones(6, dtype=bool)

    def restore():
        for key, value in saved.items():
            if key[0] == "e":
                elements[key[1]].active, elements[key[1]].radius_mm = value
            else:
                nodes[key[1]].fixed = value.copy()

    def displacement(subset):
        apply(subset)
        bundle = fem.solve_load_cases(nodes, elements, model["load_cases"], monitor_nodes=model["monitor_nodes"])
        return bundle.max_monitor_displacement_mm

    weak = [r for r in routes if str(r["candidate"]).startswith("WEAK")]
    others = [r for r in routes if r not in weak]
    chosen = list(weak)
    try:
        while others and (len(chosen) < 2 or displacement(chosen) > target):
            best = min(others, key=lambda r: displacement(chosen + [r]))
            chosen.append(best)
            others.remove(best)
    finally:
        restore()
    apply(chosen)
    # Radii back to their optimizer start value for the kept branches.
    for route in chosen:
        ids, _inner = route_nodes(route)
        for i in ids:
            elements[i].radius_mm = saved[("e", i)][1]
    model["geodesic_routes"] = chosen
    model["dropped_geodesic_routes"] = [str(r["candidate"]) for r in routes if r not in chosen]


def _validate_geodesic_pieces_sweep(context, model: dict, pieces: list) -> dict:
    """Drill-access and protected-object precheck for surface-routed pieces.

    The sleeve-junction (target lumen) preflight already ran for each route
    when the geodesic model was built.
    """
    sleeves = list((model.get("frame_context") or {}).get("sleeves") or [])
    drill_extensions = _drill_access_zones(sleeves)
    for piece in pieces:
        path = [np.asarray(tuple(p), dtype=float) for p in piece["points"]]
        radii = [float(piece["radius_mm"])] * len(path)
        drill = swept_clearance.check_swept_tube_clearance(
            path, radii, drill_extensions, sample_spacing_mm=0.2)
        if not drill.clear:
            raise RuntimeError(f"FEM_SWEEP_DRILL_{drill.status}: {piece['tag']}")
    return {"candidate_tubes": len(pieces), "drill_extension_zones": len(drill_extensions),
            "route_mode": "GEODESIC_SURFACE", "post_boolean_lumen_validated": False,
            "clinical_acceptance": False}


def create_fem_reinforcements(context=None, *, replace_existing=True) -> dict:
    """Stage a complete FEM candidate before replacing previously confirmed geometry.

    A solver failure or temporary curve error leaves the previous frame and
    reinforcements untouched.  No old object is destroyed before the new
    objects and report are ready.  The commit is reversible until cleanup.
    """
    context = context or bpy.context
    props = context.scene.dsg_props
    # The MCP/service entrypoint must enforce the same gates as the UI
    # operator; direct callers cannot bypass the clinical workflow step.
    if int(getattr(props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
        raise RuntimeError("La optimización FEM solo se permite en el paso de refuerzos")
    if guide_module.get_pending_reinforcement_preview(props):
        raise RuntimeError("Confirma o descarta el refuerzo manual pendiente")
    guide = guide_module.get_active_guide_obj(props)
    if not guide_module._valid_obj(guide):
        raise RuntimeError("DSG_Guide no está disponible")

    existing = guide_module.get_confirmed_reinforcement_curves()
    manual = [obj for obj in existing if not bool(obj.get("DSG_reinforcement_fem_generated", False))]
    if manual:
        raise RuntimeError(
            "Hay refuerzos manuales confirmados. Aplícalos o elimínalos antes de optimizar automáticamente."
        )
    previous = [obj for obj in existing if bool(obj.get("DSG_reinforcement_fem_generated", False))]
    if previous and not replace_existing:
        raise RuntimeError("Ya existen refuerzos FEM. Confirma su sustitución antes de continuar.")

    # This calculation is pure in-memory and must precede any scene mutation.
    # 9.24.11: the frame's weak points are found without the IOS (frame-only
    # FEM: deflection and bending, plus corners and long straight runs); the
    # reinforcements leave from them and are routed over the IOS surface to
    # the sleeve; the FEM then sizes their radii.
    try:
        model, result, pieces = _fem_geodesic_reinforcement_pieces(context)
    except RuntimeError as exc:
        raise RuntimeError(
            f"No se encontraron refuerzos válidos desde los puntos débiles del frame: {exc}. "
            "DSG conserva los refuerzos originales."
        ) from exc
    summary = _fem_summary(model, result)
    summary["route_mode"] = "WEAK_POINTS_GEODESIC_SURFACE"
    summary["weak_points"] = list(model.get("weak_points") or [])
    summary["active_reinforcements"] = len(pieces)
    # Numerical FEM safety never substitutes for geometric swept clearance.
    # Fail BEFORE staging if a proposed tube intersects protected volumes.
    summary["sweep_preflight"] = _validate_geodesic_pieces_sweep(context, model, pieces)

    staged = []
    previous_state = []
    old_count = int(props.reinforcement_count)
    guide_updates = {
        "DSG_frame_fem_schema": FRAME_FEM_SCHEMA,
        "DSG_frame_fem_profile": FRAME_FEM_PROFILE,
        "DSG_frame_fem_hard_safe": bool(summary["hard_safe"]),
        "DSG_frame_fem_recommended": bool(summary["recommended"]),
        "DSG_frame_fem_volume_mm3": float(summary["volume_mm3"]),
        "DSG_frame_fem_max_utilization": float(summary["max_utilization"]),
        "DSG_frame_fem_sleeve_displacement_mm": float(summary["sleeve_displacement_mm"]),
        "DSG_frame_fem_history_json": json.dumps(summary["history"], separators=(",", ":")),
        "DSG_frame_fem_element_count": 0,
        "DSG_frame_fem_design_aid_not_validation": True,
        "DSG_frame_fem_lumen_post_boolean_validation_pending": True,
    }
    guide_state = {key: (key in guide, guide.get(key)) for key in guide_updates}
    bundle = result.final_bundle
    bevel_resolution = max(5, int(getattr(props, "reinforcement_bevel_resolution", 8)))

    try:
        for piece in pieces:
            element_index = int(piece["element_index"])
            e = model["elements"][element_index]
            r = bundle.worst_results[element_index]
            if r is None:
                continue
            serial = len(staged)
            name = f"{guide_module.REINFORCEMENT_PREFIX}FEM_STAGING_{serial:03d}"
            if bpy.data.objects.get(name) is not None:
                raise RuntimeError(f"Existe una geometría temporal sin resolver: {name}")
            obj = guide_module.create_poly_curve_object(
                context, name, piece["points"],
                bevel_radius=float(piece["radius_mm"]),
                bevel_resolution=bevel_resolution,
                cyclic=False,
            )
            if not guide_module._valid_obj(obj):
                raise RuntimeError(f"No se pudo construir el elemento FEM {element_index}")
            # Track the candidate *before* metadata calls that may fail.
            staged.append(obj)
            metadata = {
                "DSG_reinforcement_preview": False,
                "DSG_reinforcement_confirmed": False,
                "DSG_reinforcement_index": int(serial),
                "DSG_reinforcement_diameter": float(piece["radius_mm"] * 2.0),
                "DSG_reinforcement_fem_generated": True,
                "DSG_fem_schema": FRAME_FEM_SCHEMA,
                "DSG_fem_element_index": int(element_index),
                "DSG_fem_governing": str(r["governing"]),
                "DSG_fem_utilization": float(r["utilization"]),
                "DSG_fem_radius_mm": float(piece["radius_mm"]),
                "DSG_fem_length_mm": float(piece.get("length_mm", r["length_mm"])),
                "DSG_fem_tag": str(piece.get("tag", e.tag)),
                "DSG_fem_route_mode": str(piece.get("mode", "STRAIGHT")),
                "DSG_fem_pre_boolean_sweep_passed": True,
                "DSG_fem_post_boolean_lumen_validated": False,
            }
            obj = guide_module.register_dsg_object(
                obj, guide_module.ROLE_REINFORCEMENT, name, metadata
            )
            staged[-1] = obj
            obj.show_in_front = False

        if not staged:
            raise RuntimeError("El FEM no produjo barras renderizables")

        # Save and hide existing output only after staging completed.
        for obj in previous:
            previous_state.append((
                obj, str(obj.name),
                bool(obj.get("DSG_reinforcement_confirmed", True)),
                bool(obj.hide_get()), bool(obj.hide_render),
            ))
            obj.name = f"DSG_FEM_PREVIOUS_{obj.name}"
            obj["DSG_reinforcement_confirmed"] = False
            obj.hide_set(True)
            obj.hide_render = True

        for serial, obj in enumerate(staged):
            target_name = f"{guide_module.REINFORCEMENT_PREFIX}{serial:02d}"
            if bpy.data.objects.get(target_name) is not None:
                raise RuntimeError(f"Nombre de refuerzo ocupado: {target_name}")
            obj.name = target_name
            obj["DSG_reinforcement_confirmed"] = True

        props.reinforcement_count = len(staged)
        props.reinforcement_preview_obj = None
        guide_updates["DSG_frame_fem_element_count"] = len(staged)
        for key, value in guide_updates.items():
            guide[key] = value
        guide_module.set_active(context, staged[0])

    except Exception:
        # Roll back staged geometry *and* restored original object identities.
        for obj in staged:
            if guide_module._valid_obj(obj):
                guide_module.safe_remove_object(obj)
        for obj, original_name, confirmed, hidden, render_hidden in previous_state:
            if guide_module._valid_obj(obj):
                obj.name = original_name
                obj["DSG_reinforcement_confirmed"] = confirmed
                obj.hide_set(hidden)
                obj.hide_render = render_hidden
        props.reinforcement_count = old_count
        for key, (had_value, value) in guide_state.items():
            if had_value:
                guide[key] = value
            elif key in guide:
                del guide[key]
        raise

    # Cleanup after a successful commit: it must never invalidate the new result.
    for obj, _name, _confirmed, _hidden, _render_hidden in previous_state:
        try:
            if guide_module._valid_obj(obj):
                guide_module.safe_remove_object(obj)
        except Exception:
            _DSG_LOG.warning("Could not remove archived FEM geometry after commit", exc_info=True)
    return summary


class DSG_OT_OptimizeFrameFEM(Operator):
    bl_idname = "dsg.optimize_frame_fem"
    bl_label = "Optimize Frame"
    bl_description = "Propone refuerzos geodésicos conservando el contorno; revisión geométrica antes de aplicar"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .blender import generative_frame
        try:
            generative_frame.start(context)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Calculando rutas; el contorno y los refuerzos actuales se conservan hasta aceptar.')
        return {'FINISHED'}



def preview_geodesic_fem_paths(context=None) -> dict:
    """Create nonexported Blender previews from exactly the curved FEM chains.

    A preview is *not* an approved reinforcement or a final guide component.
    Existing previews are preserved if any construction/commit step fails.
    """
    context = context or bpy.context
    model = _fem_build_geodesic_model(context)
    result = fem.optimize_reinforcement(
        model["nodes"], model["elements"], model["load_cases"],
        monitor_nodes=model["monitor_nodes"], config=model["config"],
        keep_out_check=model["keep_out"],
    )
    summary = _fem_summary(model, result)
    prefix = "DSG_GeodesicFEM_Preview_"
    old = [obj for obj in list(bpy.data.objects)
           if obj.name.startswith(prefix) and bool(obj.get("DSG_geodesic_preview_only", False))]
    staged = []
    previous_state = []
    try:
        for serial, route in enumerate(model["geodesic_routes"]):
            points = [Vector(point) for point in route["curve_points_mm"]]
            edges = [model["elements"][int(i)] for i in route["beam_indices"]]
            if len(points) != len(edges) + 1:
                raise RuntimeError("GEODESIC_PREVIEW_FEM_MISMATCH: different geometry and FEM path")
            name = f"DSG_GeodesicFEM_Staging_{serial:03d}"
            if bpy.data.objects.get(name) is not None:
                raise RuntimeError(f"GEODESIC_PREVIEW_STAGING_CONFLICT: {name}")
            curve = guide_module.create_poly_curve_object(
                context, name, points, bevel_radius=1.0, bevel_resolution=8, cyclic=False
            )
            if not guide_module._valid_obj(curve):
                raise RuntimeError(f"GEODESIC_PREVIEW_BUILD_FAILED: {name}")
            staged.append(curve)
            # Blender POLY spline radii are multiplied by bevel_depth (1 mm).
            # Each vertex receives the mean radius of adjacent FEM elements.
            radii = [float(edges[0].radius_mm)]
            radii.extend((float(a.radius_mm) + float(b.radius_mm)) * 0.5
                         for a, b in zip(edges, edges[1:]))
            radii.append(float(edges[-1].radius_mm))
            spline = curve.data.splines[0]
            if len(spline.points) != len(radii):
                raise RuntimeError("GEODESIC_PREVIEW_SPLINE_MISMATCH")
            for point, radius in zip(spline.points, radii):
                point.radius = radius
            curve["DSG_geodesic_preview_only"] = True
            curve["DSG_geodesic_fem_label"] = str(route["candidate"])
            curve["DSG_geodesic_post_boolean_validated"] = False
            curve.hide_render = True

        if not staged:
            raise RuntimeError("GEODESIC_PREVIEW_EMPTY")
        # Commit: old previews are only archived after every replacement exists.
        for obj in old:
            previous_state.append((obj, str(obj.name), bool(obj.hide_get()), bool(obj.hide_render)))
            obj.name = f"DSG_GeodesicFEM_Archive_{obj.name}"
            obj.hide_set(True)
        for serial, obj in enumerate(staged):
            name = f"{prefix}{serial:03d}"
            if bpy.data.objects.get(name) is not None:
                raise RuntimeError(f"GEODESIC_PREVIEW_NAME_CONFLICT: {name}")
            obj.name = name
            obj.hide_set(False)
    except Exception:
        for obj in staged:
            if guide_module._valid_obj(obj):
                guide_module.safe_remove_object(obj)
        for obj, name, hidden, hide_render in previous_state:
            if guide_module._valid_obj(obj):
                obj.name = name
                obj.hide_set(hidden)
                obj.hide_render = hide_render
        raise

    for obj, _name, _hidden, _render in previous_state:
        try:
            if guide_module._valid_obj(obj):
                guide_module.safe_remove_object(obj)
        except Exception:
            _DSG_LOG.warning("Geodesic preview archive cleanup failed", exc_info=True)
    summary.update(
        geodesic_routes=model["geodesic_routes"],
        rejected_geodesic_routes=model["rejected_geodesic_routes"],
        experimental=True,
        geometry_mutated=True,
        guide_geometry_mutated=False,
        preview_only=True,
        post_boolean_section_validated=False,
    )
    return summary


class DSG_OT_PreviewGeodesicFrameFEM(Operator):
    bl_idname = "dsg.preview_geodesic_frame_fem"
    bl_label = "Preview Surface-Geodesic Reinforcements (Experimental)"
    bl_description = "Build viewport-only FEM-geodesic paths without altering the surgical guide"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            if int(getattr(context.scene.dsg_props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
                raise RuntimeError("La vista previa geodésica requiere el paso de refuerzos")
            result = preview_geodesic_fem_paths(context)
        except Exception as exc:
            guide_module._dsg_report(
                self, {'ERROR'}, f"Geodesic preview failed: {exc}",
                f"No se pudo generar la vista previa geodésica: {exc}",
            )
            return {'CANCELLED'}
        guide_module._dsg_report(
            self, {'INFO'},
            f"Experimental surface preview: {len(result['geodesic_routes'])} FEM-matched paths; "
            "not included in clinical guide/export.",
            f"Vista previa experimental: {len(result['geodesic_routes'])} rutas FEM geodésicas; "
            "no se aplican ni exportan con la guía.",
        )
        return {'FINISHED'}


class DSG_OT_EstimateGeodesicContact(Operator):
    bl_idname = "dsg.estimate_geodesic_contact"
    bl_label = "Evaluate Contact Profile (Experimental)"
    bl_description = "Local-planar contact estimate only; not a validated clinical retention test"
    bl_options = {'REGISTER'}

    # The module uses postponed annotations; Blender requires actual
    # deferred RNA property objects in __annotations__, not annotation strings.
    __annotations__ = {
        "min_contact_width_mm": FloatProperty(
            name="Minimum interface width (mm)", default=0.8,
            min=0.0, max=8.0, precision=3),
        "min_area_ratio": FloatProperty(
            name="Minimum retained area fraction", default=0.65,
            min=0.0, max=1.0, precision=3),
        "min_inertia_ratio": FloatProperty(
            name="Minimum bending inertia fraction", default=0.30,
            min=0.0, max=1.0, precision=3),
        "min_penetration_mm": FloatProperty(
            name="Minimum overlap (mm)", default=0.01,
            min=0.0, max=5.0, precision=3),
        "max_penetration_mm": FloatProperty(
            name="Maximum overlap (mm)", default=0.7,
            min=0.0, max=5.0, precision=3),
    }

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="RESEARCH ONLY: planar estimate, not clinical proof", icon='ERROR')
        for attr in ("min_contact_width_mm", "min_area_ratio", "min_inertia_ratio",
                     "min_penetration_mm", "max_penetration_mm"):
            col.prop(self, attr)

    def execute(self, context):
        try:
            if int(getattr(context.scene.dsg_props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
                raise RuntimeError("El diagnóstico de contacto requiere el paso de refuerzos")
            report = estimate_geodesic_frame_contact(context, policy=contact_core.ContactPolicy(
                min_contact_width_mm=float(self.min_contact_width_mm),
                min_retained_area_ratio=float(self.min_area_ratio),
                min_bending_inertia_ratio=float(self.min_inertia_ratio),
                min_penetration_mm=float(self.min_penetration_mm),
                max_penetration_mm=float(self.max_penetration_mm),
            ))
        except Exception as exc:
            guide_module._dsg_report(self, {'ERROR'},
                f"Contact research estimate failed: {exc}",
                f"Falló la estimación experimental de contacto: {exc}")
            return {'CANCELLED'}
        guide_module._dsg_report(self, {'INFO'},
            f"Experimental contact: {report['feasible_routes']} routes, interface "
            f"estimate {report['contact_area_planar_estimate_mm2']:.1f} mm². Not clinically validated.",
            f"Contacto experimental: {report['feasible_routes']} rutas, superficie "
            f"estimada {report['contact_area_planar_estimate_mm2']:.1f} mm². Sin validación clínica.")
        skipped = report.get('skipped_routes') or []
        if skipped:
            names = ", ".join(r['label'] for r in skipped)
            guide_module._dsg_report(self, {'WARNING'},
                f"Routes without a contact estimate (folded passive surface): {names}",
                f"Rutas sin estimación de contacto (superficie del pasivo plegada): {names}")
        return {'FINISHED'}


class DSG_OT_AnalyzeGeodesicGroups(Operator):
    bl_idname = "dsg.analyze_geodesic_groups"
    bl_label = "Optimize Geodesic Groups (Experimental, Read-only)"
    bl_description = (
        "Test removal of whole curved FEM routes under balanced volume/compliance; "
        "does not apply or export any optimized geometry"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            if int(getattr(context.scene.dsg_props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
                raise RuntimeError("El análisis de topología requiere el paso de refuerzos")
            report = analyze_geodesic_group_topology(context)
        except Exception as exc:
            guide_module._dsg_report(self, {'ERROR'},
                f"Geodesic group analysis failed: {exc}",
                f"Falló el análisis experimental de grupos: {exc}")
            return {'CANCELLED'}
        guide_module._dsg_report(
            self, {'INFO'},
            f"Balanced research FEM: {len(report['active_groups'])} active path groups, "
            f"{len(report['removed_groups'])} candidate removals. No geometry changed.",
            f"FEM experimental equilibrado: {len(report['active_groups'])} rutas activas, "
            f"{len(report['removed_groups'])} grupos eliminables. Geometría intacta.",
        )
        return {'FINISHED'}


def inspect_final_boolean_guide_section(context=None, *, point_mm, axis,
                                        nominal_radius_mm=None,
                                        mesh_arrays_fn=None) -> dict:
    """Measure one requested section of the *actual* final Boolean guide.

    Only a DSG guide explicitly marked as final-cut-completed is accepted.
    Explicit interior probe/section point prevents assigning unrelated
    implants, sleeves or neighbouring frame branches to this cross-section.
    A failure leaves all Blender objects untouched and does not affect export.
    """
    context = context or bpy.context
    guide = guide_module.get_active_guide_obj(context.scene.dsg_props)
    if (not guide_module._valid_obj(guide)
            or getattr(guide, 'type', None) != 'MESH'
            or not bool(guide.get("DSG_final_cut_completed", False))):
        raise RuntimeError(
            "BOOLEAN_SECTION_REQUIRES_FINAL_GUIDE: apply the validated final "
            "Boolean first; preview curves/pre-Boolean guides cannot be measured"
        )
    if mesh_arrays_fn is None:
        # Reuse the actual export adapter: evaluated mesh, world coordinates.
        from .guide_export.blender_adapter import mesh_arrays
        mesh_arrays_fn = mesh_arrays
    vertices, triangles = mesh_arrays_fn(guide)
    section = boolean_sections.measure_boolean_section(
        vertices, triangles, point_mm, axis, probe_point_mm=point_mm,
        require_closed=True,
    )
    comparison = (boolean_sections.compare_section_to_nominal_circle(
        section, nominal_radius_mm=float(nominal_radius_mm))
        if nominal_radius_mm is not None else None)
    return {
        "geometry_reference_area_ratio": (
            float(comparison.measured_area_ratio) if comparison else None),
        "geometry_reference_weak_inertia_ratio": (
            float(comparison.measured_weak_axis_bending_ratio) if comparison else None),
        "nominal_section_radius_mm": (
            float(comparison.nominal_radius_mm) if comparison else None),
        "section_may_include_merged_frame": True,
        "schema": "dsg.actual_boolean_section.v1",
        "guide_name": str(guide.name),
        "method": section.backend,
        "section_area_mm2": float(section.area_mm2),
        "principal_inertia_min_mm4": float(section.principal_inertia_min_mm4),
        "principal_inertia_max_mm4": float(section.principal_inertia_max_mm4),
        "boundary_count": int(section.boundary_count),
        "hole_count": int(section.hole_count),
        "component_count": int(section.global_component_count),
        "experimental": True,
        "mesh_is_post_boolean": True,
        "design_approved": False,
        "retention_validated": False,
        "full_frame_fem_validated": False,
        "geometry_mutated": False,
    }


def inspect_final_boolean_guide_path(
    context=None, *, interior_centerline_mm, nominal_radii_mm=None,
    sample_count=9, mesh_arrays_fn=None,
) -> dict:
    """Sample true mesh sections along an explicitly INSIDE-the-solid path.

    No silent projection of surface geodesics into the Boolean-cut volume:
    a path must be supplied through retained material. No guide mutations.
    """
    context = context or bpy.context
    guide = guide_module.get_active_guide_obj(context.scene.dsg_props)
    if (not guide_module._valid_obj(guide)
            or getattr(guide, 'type', None) != 'MESH'
            or not bool(guide.get("DSG_final_cut_completed", False))):
        raise RuntimeError("BOOLEAN_PATH_REQUIRES_FINAL_GUIDE")
    if mesh_arrays_fn is None:
        from .guide_export.blender_adapter import mesh_arrays
        mesh_arrays_fn = mesh_arrays
    vertices, triangles = mesh_arrays_fn(guide)
    profile = boolean_paths.profile_boolean_path(
        vertices, triangles, interior_centerline_mm,
        nominal_radii_mm=nominal_radii_mm, sample_count=int(sample_count),
    )
    return {
        "schema": "dsg.actual_boolean_path_profile.v1",
        "guide_name": str(guide.name),
        "method": "ACTUAL_EVALUATED_FINAL_GUIDE_MULTI_STATION",
        "total_path_length_mm": float(profile.arclength_mm),
        "station_count": int(profile.probe_count),
        "area_min_mm2": float(profile.area_min_mm2),
        "area_median_mm2": float(profile.area_median_mm2),
        "weak_inertia_min_mm4": float(profile.weak_inertia_min_mm4),
        "weak_inertia_median_mm4": float(profile.weak_inertia_median_mm4),
        "worst_station_by_area": int(profile.worst_station_index_by_area),
        "worst_station_by_inertia": int(profile.worst_station_index_by_inertia),
        "stations": [{
            "index": station.index,
            "arclength_mm": station.arclength_mm,
            "point_mm": list(station.point_mm),
            "area_mm2": station.area_mm2,
            "principal_inertia_min_mm4": station.principal_inertia_min_mm4,
            "hole_count": station.hole_count,
            "nominal_weak_inertia_ratio": station.nominal_weak_inertia_ratio,
        } for station in profile.stations],
        "experimental": True,
        "complete": True,
        "geometry_mutated": False,
        "retention_validated": False,
        "post_boolean_fem_validated": False,
    }


class DSG_OT_InspectFinalBooleanPath(Operator):
    bl_idname = "dsg.inspect_final_boolean_path"
    bl_label = "Profile Sections Along Final Guide (Experimental)"
    bl_description = (
        "Read several actual cross-sections along a selected POLY curve INSIDE "
        "the final guide material. Copies research JSON to clipboard only."
    )
    bl_options = {'REGISTER'}

    __annotations__ = {
        "station_count": IntProperty(
            name="Cross-section stations", default=9, min=2, max=25,
            description="All samples must be in retained solid, or the scan fails"),
        "nominal_diameter_mm": FloatProperty(
            name="Reference diameter (mm)", default=2.5, min=0.1, max=25,
            precision=3, description="Geometry comparison only, not a clinical limit"),
    }

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Select a NON-PREVIEW POLY curve inside the final solid",
                  icon='INFO')
        col.label(text="All samples must be inside guide material", icon='ERROR')
        col.prop(self, "station_count")
        col.prop(self, "nominal_diameter_mm")
        col.label(text="Results copied as research-only JSON", icon='INFO')

    def execute(self, context):
        try:
            curve = context.active_object
            if (curve is None or getattr(curve, "type", None) != 'CURVE'
                    or bool(curve.get("DSG_geodesic_preview_only", False))):
                raise RuntimeError(
                    "Selecciona una curva POLY independiente dentro del material, "
                    "no una vista previa geodésica superficial"
                )
            if len(curve.data.splines) != 1:
                raise RuntimeError("Se necesita exactamente una spline POLY no cíclica")
            spline = curve.data.splines[0]
            if spline.type != 'POLY' or spline.use_cyclic_u or len(spline.points) < 2:
                raise RuntimeError("Se necesita una curva abierta POLY de dos o más puntos")
            path = [
                tuple(float(v) for v in (curve.matrix_world @ Vector(
                    (float(p.co[0]), float(p.co[1]), float(p.co[2])))))
                for p in spline.points
            ]
            report = inspect_final_boolean_guide_path(
                context, interior_centerline_mm=path,
                nominal_radii_mm=[float(self.nominal_diameter_mm) * 0.5] * len(path),
                sample_count=int(self.station_count),
            )
            context.window_manager.clipboard = json.dumps(
                report, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False,
            )
        except Exception as exc:
            guide_module._dsg_report(
                self, {'ERROR'},
                f"Final Boolean path profile failed: {exc}",
                f"Falló el perfil de secciones finales: {exc}")
            return {'CANCELLED'}
        guide_module._dsg_report(
            self, {'INFO'},
            f"{report['station_count']} actual sections, minimum area "
            f"{report['area_min_mm2']:.2f} mm², min I "
            f"{report['weak_inertia_min_mm4']:.3f} mm⁴. JSON copied, no guide changes.",
            f"{report['station_count']} secciones reales, área mínima "
            f"{report['area_min_mm2']:.2f} mm², I mínima "
            f"{report['weak_inertia_min_mm4']:.3f} mm⁴. JSON copiado, guía intacta.",
        )
        return {'FINISHED'}


class DSG_OT_InspectFinalBooleanSection(Operator):
    bl_idname = "dsg.inspect_final_boolean_section"
    bl_label = "Inspect Final Guide Section (Experimental)"
    bl_description = (
        "Measure real cross-section at the 3D cursor inside the final Boolean guide; "
        "never modifies the guide or exports a mesh"
    )
    bl_options = {'REGISTER'}

    # Blender requires actual property descriptors with postponed annotations.
    __annotations__ = {
        "section_axis": FloatVectorProperty(
            name="Plane normal / beam tangent",
            description="Local beam direction of the requested section in world XYZ",
            subtype='DIRECTION', size=3, default=(1.0, 0.0, 0.0)),
        "nominal_diameter_mm": FloatProperty(
            name="Reference cylinder diameter (mm)",
            description="For geometric comparison only: not measured automatically and not a structural pass/fail limit",
            default=2.5, min=0.1, max=25.0, precision=3),
    }

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Place the 3D cursor INSIDE the final guide", icon='INFO')
        col.label(text="Not a retention / clinical acceptance test", icon='ERROR')
        col.prop(self, "section_axis")
        col.prop(self, "nominal_diameter_mm")
        col.label(text="Reference is only a comparison, not a safety threshold", icon='INFO')

    def execute(self, context):
        try:
            guide = guide_module.get_active_guide_obj(context.scene.dsg_props)
            if not guide_module._valid_obj(guide) or not bool(guide.get("DSG_final_cut_completed", False)):
                raise RuntimeError("Se necesita una guía con booleana final aplicada")
            point = tuple(float(v) for v in context.scene.cursor.location)
            report = inspect_final_boolean_guide_section(
                context, point_mm=point, axis=tuple(float(v) for v in self.section_axis),
                nominal_radius_mm=float(self.nominal_diameter_mm) * 0.5)
        except Exception as exc:
            guide_module._dsg_report(
                self, {'ERROR'},
                f"Final-guide section measurement failed: {exc}",
                f"No se pudo medir la sección final: {exc}")
            return {'CANCELLED'}
        guide_module._dsg_report(
            self, {'INFO'},
            f"Actual guide section: {report['section_area_mm2']:.2f} mm², "
            f"Imin={report['principal_inertia_min_mm4']:.3f} mm⁴, "
            f"holes={report['hole_count']}, I/Icircle={report['geometry_reference_weak_inertia_ratio']:.2f}. Research only.",
            f"Sección real: {report['section_area_mm2']:.2f} mm², "
            f"Imin={report['principal_inertia_min_mm4']:.3f} mm⁴, "
            f"huecos={report['hole_count']}, I/Icírculo={report['geometry_reference_weak_inertia_ratio']:.2f}. Solo investigación.")
        return {'FINISHED'}


class DSG_OT_AnalyzeGeodesicFrameFEM(Operator):
    bl_idname = "dsg.analyze_geodesic_frame_fem"
    bl_label = "Analyze Surface-Geodesic FEM (Experimental)"
    bl_description = (
        "Analyze FEM beam chains following the passive surface, without "
        "changing or applying any guide geometry"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            if int(getattr(context.scene.dsg_props, 'current_step', -1)) != int(guide_module.STEP_REINFORCEMENT):
                raise RuntimeError("El análisis geodésico requiere el paso de refuerzos")
            summary = analyze_geodesic_frame_fem(context)
        except Exception as exc:
            guide_module._dsg_report(
                self, {'ERROR'},
                f"Experimental geodesic FEM failed: {exc}",
                f"Análisis geodésico experimental fallido: {exc}",
            )
            return {'CANCELLED'}
        guide_module._dsg_report(
            self, {'INFO'},
            f"Geodesic FEM (design aid): {len(summary['geodesic_routes'])} surface routes, "
            f"{summary['active_reinforcements']} beam elements, "
            f"U={summary['max_utilization']:.2f}; no geometry changed.",
            f"FEM geodésico (experimental): {len(summary['geodesic_routes'])} rutas, "
            f"{summary['active_reinforcements']} elementos, "
            f"U={summary['max_utilization']:.2f}; geometría intacta.",
        )
        return {'FINISHED'}


from .blender import generative_frame
_CLASSES = (DSG_OT_OptimizeFrameFEM, DSG_OT_AnalyzeGeodesicFrameFEM, DSG_OT_PreviewGeodesicFrameFEM, DSG_OT_EstimateGeodesicContact, DSG_OT_AnalyzeGeodesicGroups, DSG_OT_InspectFinalBooleanSection, DSG_OT_InspectFinalBooleanPath)


def register():
    for cls in _CLASSES + generative_frame.CLASSES:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            bpy.utils.register_class(cls)


def unregister():
    generative_frame.freeze_for_undo()
    for cls in reversed(_CLASSES + generative_frame.CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
