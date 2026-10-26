"""Surface-based proximal fit metrics and bounded mesiodistal placement."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree



@dataclass(frozen=True, slots=True)
class ProximalFitPolicy:
    search_mm: float = 1.2
    step_mm: float = 0.10
    region_radius_mm: float = 2.8
    near_contact_mm: float = 0.20
    penetration_tolerance_mm: float = 0.03
    penetration_penalty: float = 1000.0


def _tree(obj: bpy.types.Object) -> BVHTree:
    if obj is None or obj.type != "MESH":
        raise ValueError("Proximal neighbor must be a mesh")
    tree = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get(), deform=True, cage=False)
    if tree is None:
        raise RuntimeError(f"Could not build BVH for {obj.name}")
    return tree


def _region_points(
    crown: bpy.types.Object,
    contact_world: Vector,
    *,
    radius_mm: float,
) -> list[tuple[Vector, float]]:
    if crown.type != "MESH":
        raise ValueError("CrownTarget must be a mesh")
    world = crown.matrix_world
    mesh = crown.data
    # Approximate vertex-associated area by distributing polygon area.
    area = [0.0] * len(mesh.vertices)
    for poly in mesh.polygons:
        share = float(poly.area) / max(1, len(poly.vertices))
        for index in poly.vertices:
            area[index] += share
    points = []
    for vertex in mesh.vertices:
        p = world @ vertex.co
        if (p - contact_world).length <= radius_mm:
            # Matrix scale can make local polygon area imperfect; this remains a
            # comparative metric and is recorded explicitly as an approximation.
            points.append((p, max(area[vertex.index], 1.0e-6)))
    return points


def measure_side(
    crown: bpy.types.Object,
    neighbor: bpy.types.Object | None,
    *,
    contact_world: Vector,
    policy: ProximalFitPolicy,
) -> dict[str, Any]:
    if neighbor is None:
        return {
            "present": False, "mean_gap_mm": None, "max_gap_mm": None,
            "penetration_mm": 0.0, "near_contact_area_mm2": 0.0, "sample_count": 0,
        }
    tree = _tree(neighbor)
    samples = _region_points(crown, contact_world, radius_mm=policy.region_radius_mm)
    gaps = []
    weighted_area = 0.0
    near_area = 0.0
    penetration = 0.0
    for point, area in samples:
        hit = tree.find_nearest(point)
        if hit is None or hit[0] is None:
            continue
        nearest, normal, _index, distance = hit
        distance = float(distance)
        # Approximate signed surface distance from the neighbor's outward normal.
        sign = 1.0
        if normal is not None and (point - nearest).dot(normal) < 0.0:
            sign = -1.0
        signed = sign * distance
        if signed < 0.0:
            penetration = max(penetration, -signed)
            gap = 0.0
        else:
            gap = signed
        gaps.append((gap, area))
        weighted_area += area
        if signed <= policy.near_contact_mm and signed >= -policy.penetration_tolerance_mm:
            near_area += area
    if not gaps or weighted_area <= 0:
        return {
            "present": True, "mean_gap_mm": None, "max_gap_mm": None,
            "penetration_mm": float(penetration), "near_contact_area_mm2": 0.0,
            "sample_count": len(gaps),
        }
    mean_gap = sum(gap * area for gap, area in gaps) / weighted_area
    max_gap = max(gap for gap, _area in gaps)
    return {
        "present": True,
        "mean_gap_mm": float(mean_gap),
        "max_gap_mm": float(max_gap),
        "penetration_mm": float(penetration),
        "near_contact_area_mm2": float(near_area),
        "sample_count": len(gaps),
    }


def _score(metrics: dict[str, Any], policy: ProximalFitPolicy) -> float:
    score = 0.0
    for side in ("mesial", "distal"):
        m = metrics[side]
        if not m["present"]:
            continue
        penetration = float(m["penetration_mm"] or 0.0)
        if penetration > policy.penetration_tolerance_mm:
            score += policy.penetration_penalty * penetration
        gap = m["mean_gap_mm"]
        if gap is not None:
            score += float(gap)
        score -= 0.02 * float(m["near_contact_area_mm2"] or 0.0)
    return float(score)


def fit_translation(
    crown: bpy.types.Object,
    *,
    frame_x_world: Vector,
    mesial_neighbor: bpy.types.Object | None,
    distal_neighbor: bpy.types.Object | None,
    mesial_contact_world: Vector,
    distal_contact_world: Vector,
    policy: ProximalFitPolicy | None = None,
) -> dict[str, Any]:
    """Search one symmetric MD translation; never deform one proximal face alone."""
    policy = policy or ProximalFitPolicy()
    axis = frame_x_world.normalized()
    original = crown.matrix_world.copy()
    best = None
    steps = int(round((2.0 * policy.search_mm) / policy.step_mm))
    for i in range(steps + 1):
        offset = -policy.search_mm + i * policy.step_mm
        crown.matrix_world = original.copy()
        crown.matrix_world.translation += axis * offset
        shifted_mesial = mesial_contact_world + axis * offset
        shifted_distal = distal_contact_world + axis * offset
        metrics = {
            "mesial": measure_side(
                crown, mesial_neighbor, contact_world=shifted_mesial, policy=policy
            ),
            "distal": measure_side(
                crown, distal_neighbor, contact_world=shifted_distal, policy=policy
            ),
        }
        score = _score(metrics, policy)
        if best is None or score < best["score"]:
            best = {"offset_mm": float(offset), "score": score, "metrics": metrics}
    crown.matrix_world = original.copy()
    if best is None:
        raise RuntimeError("ProximalFit produced no candidate")
    crown.matrix_world.translation += axis * float(best["offset_mm"])
    report = {
        "schema": "dsg.proximal_fit.v1",
        "symmetric": True,
        "translation_mm": float(best["offset_mm"]),
        "score": float(best["score"]),
        "mesial": best["metrics"]["mesial"],
        "distal": best["metrics"]["distal"],
        "policy": asdict(policy),
    }
    return report
