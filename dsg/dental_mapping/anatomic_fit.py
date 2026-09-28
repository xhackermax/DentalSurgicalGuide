"""Bounded symmetric CrownTemplate → CrownTarget adaptation.

The immutable CrownTemplate is never modified. Adaptation uses a smooth,
symmetric envelope warp in DSG_TOOTH_LOCAL_V1, not arbitrary free-form vertex
editing. Generic limits are engineering guardrails; until FDI-specific limits
are clinically authored the result remains REVIEW-required.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math
from typing import Any, Mapping

import bpy
from mathutils import Matrix, Vector

from .. import dental_assets, dental_asset_blender
from . import library


@dataclass(frozen=True, slots=True)
class AnatomicFitPolicy:
    md_min_ratio: float = 0.85
    md_max_ratio: float = 1.15
    vl_min_ratio: float = 0.85
    vl_max_ratio: float = 1.15
    oa_min_ratio: float = 0.88
    oa_max_ratio: float = 1.12


def _matrix(values) -> Matrix:
    return Matrix(tuple(tuple(float(values[r*4+c]) for c in range(4)) for r in range(4)))


def _frame_relative_to_crown(fdi: int) -> Matrix:
    snapshot = library.read_family_reference_snapshot(fdi, anchor_role="CROWN_TEMPLATE")
    name = dental_assets.object_name(fdi, "TOOTH_FRAME")
    frame = snapshot.objects.get(name)
    if frame is None:
        raise dental_assets.DentalAssetContractError(f"FDI {fdi}: crown template has no ToothFrame")
    return _matrix(frame.matrix_relative_to_anchor)


def _bounds_in_frame(obj: bpy.types.Object, frame_world: Matrix) -> dict[str, list[float]]:
    if obj is None or obj.type != "MESH" or obj.data is None:
        raise ValueError("Crown dimensions require a mesh object")
    inv = frame_world.inverted_safe()
    points = [inv @ (obj.matrix_world @ vertex.co) for vertex in obj.data.vertices]
    if not points:
        raise ValueError("Crown mesh is empty")
    mins = [min(float(p[i]) for p in points) for i in range(3)]
    maxs = [max(float(p[i]) for p in points) for i in range(3)]
    return {"min": mins, "max": maxs}


def dimensions_in_frame(obj: bpy.types.Object, frame_world: Matrix) -> dict[str, float]:
    bounds = _bounds_in_frame(obj, frame_world)
    mins, maxs = bounds["min"], bounds["max"]
    return {"md_mm": maxs[0]-mins[0], "vl_mm": maxs[1]-mins[1], "oa_mm": maxs[2]-mins[2]}


def _ratio(name: str, target: float | None, reference: float, lo: float, hi: float) -> float:
    if target is None:
        return 1.0
    value = float(target)
    if not math.isfinite(value) or value <= 0 or reference <= 0:
        raise ValueError(f"Invalid {name} dimension")
    ratio = value / reference
    if ratio < lo or ratio > hi:
        raise dental_assets.DentalAssetContractError(
            f"{name} adaptation ratio {ratio:.3f} exceeds allowed [{lo:.3f}, {hi:.3f}]"
        )
    return ratio


def _smoothstep01(value: float) -> float:
    u = max(0.0, min(1.0, float(value)))
    return u*u*(3.0 - 2.0*u)


def _warp_axis(value: float, negative_extent: float, positive_extent: float, ratio: float) -> float:
    """Symmetric side-aware displacement: zero near center, full at envelope."""
    if abs(ratio - 1.0) <= 1.0e-12:
        return float(value)
    if value >= 0.0:
        extent = max(positive_extent, 1.0e-9)
        u = abs(value) / extent
        delta = (ratio - 1.0) * extent * _smoothstep01(u)
        return float(value + delta)
    extent = max(negative_extent, 1.0e-9)
    u = abs(value) / extent
    delta = (ratio - 1.0) * extent * _smoothstep01(u)
    return float(value - delta)


def warp_frame_point(point: Vector, *, bounds: Mapping[str, Any], ratios: Mapping[str, float]) -> Vector:
    mins = [float(v) for v in bounds["min"]]
    maxs = [float(v) for v in bounds["max"]]
    return Vector((
        _warp_axis(float(point.x), abs(mins[0]), abs(maxs[0]), float(ratios["MD"])),
        _warp_axis(float(point.y), abs(mins[1]), abs(maxs[1]), float(ratios["VL"])),
        _warp_axis(float(point.z), abs(mins[2]), abs(maxs[2]), float(ratios["OA"])),
    ))


def warp_crown_local_point(crown_target: bpy.types.Object, crown_local_point: Vector) -> Vector:
    """Apply exactly the stored CrownTarget deformation to a semantic reference point."""
    raw = str(crown_target.get("DSG_anatomic_fit_json", "") or "")
    if not raw:
        return crown_local_point.copy()
    data = json.loads(raw)
    frame_rel_values = data.get("frame_relative_to_crown")
    if not isinstance(frame_rel_values, list) or len(frame_rel_values) != 16:
        return crown_local_point.copy()
    F = _matrix(frame_rel_values)
    frame_point = F.inverted_safe() @ crown_local_point
    warped = warp_frame_point(
        frame_point,
        bounds=data["reference_bounds_frame"],
        ratios=data["ratios"],
    )
    return F @ warped


def create_crown_target(
    fdi: int,
    crown_template: bpy.types.Object,
    *,
    target_frame_world: Matrix,
    desired_dimensions: Mapping[str, float] | None = None,
    policy: AnatomicFitPolicy | None = None,
    replace_existing: bool = True,
) -> tuple[bpy.types.Object, dict[str, Any]]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    policy = policy or AnatomicFitPolicy()
    dental_asset_blender.validate_object_contract(
        crown_template, expected_fdi=fdi, expected_role="CROWN_TEMPLATE"
    )
    frame_rel = _frame_relative_to_crown(fdi)
    target_world = target_frame_world @ frame_rel.inverted_safe()

    name = dental_assets.object_name(fdi, "CROWN_TARGET")
    existing = bpy.data.objects.get(name)
    if existing is not None:
        if not replace_existing:
            return existing, json.loads(str(existing.get("DSG_anatomic_fit_json", "{}") or "{}"))
        old_data = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if old_data is not None and old_data.users == 0:
            bpy.data.meshes.remove(old_data)

    target = crown_template.copy()
    target.data = crown_template.data.copy()
    target.matrix_world = target_world
    bpy.context.scene.collection.objects.link(target)
    dental_asset_blender.stamp_object(
        target, fdi=fdi, role="CROWN_TARGET", source="DERIVED",
        coordinate_space="WORLD", rename=True,
    )

    target_frame = target.matrix_world @ frame_rel
    bounds = _bounds_in_frame(target, target_frame)
    ref_dims = dimensions_in_frame(target, target_frame)
    desired = dict(desired_dimensions or {})
    ratios = {
        "MD": _ratio("MD", desired.get("md_mm"), ref_dims["md_mm"], policy.md_min_ratio, policy.md_max_ratio),
        "VL": _ratio("VL", desired.get("vl_mm"), ref_dims["vl_mm"], policy.vl_min_ratio, policy.vl_max_ratio),
        "OA": _ratio("OA", desired.get("oa_mm"), ref_dims["oa_mm"], policy.oa_min_ratio, policy.oa_max_ratio),
    }

    inv_frame = frame_rel.inverted_safe()
    for vertex in target.data.vertices:
        frame_point = inv_frame @ vertex.co
        vertex.co = frame_rel @ warp_frame_point(frame_point, bounds=bounds, ratios=ratios)
    target.data.update()

    authored_limits = bool(crown_template.get("DSG_deformation_limits_validated", False))
    report = {
        "schema": "dsg.anatomic_fit.v1",
        "fdi": fdi,
        "status": "BOUNDED_SYMMETRIC_ENVELOPE_WARP",
        "mechanism": "BOUNDED_SYMMETRIC_ENVELOPE_WARP_V1",
        "symmetric": True,
        "reference_immutable": True,
        "reference_dimensions_mm": ref_dims,
        "reference_bounds_frame": bounds,
        "ratios": ratios,
        "frame_relative_to_crown": [float(frame_rel[r][c]) for r in range(4) for c in range(4)],
        "policy": asdict(policy),
        "limits_source": "AUTHORED_VALIDATED" if authored_limits else "GENERIC_ENGINEERING_GUARDRAIL",
        "requires_review": not authored_limits,
    }
    target["DSG_anatomic_fit_json"] = json.dumps(report, sort_keys=True, separators=(",", ":"))
    target["DSG_reference_crown_template"] = crown_template.name
    target["DSG_fit_status"] = report["status"]
    return target, report
