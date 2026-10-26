"""Local surface refinement for transferred dental landmarks.

The initial implementation is deliberately conservative: it snaps each semantic
point to the nearest patient surface within a bounded radius. Feature-specific
curvature refiners can be added behind the same interface once validated.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import dental_assets


def _bvh(obj: bpy.types.Object) -> BVHTree:
    if obj is None or obj.type != "MESH":
        raise ValueError("Landmark refinement requires a mesh patient tooth")
    tree = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get(), deform=True, cage=False)
    if tree is None:
        raise RuntimeError(f"Could not build BVH for {obj.name}")
    return tree


def refine_landmarks(
    patient: bpy.types.Object,
    transferred: Mapping[str, Mapping[str, Any]],
    *,
    registration_rms_mm: float,
    max_snap_mm: float = 1.5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tree = _bvh(patient)
    final = []
    metrics: dict[str, Any] = {}
    registration_component = math.exp(-0.5 * (max(0.0, float(registration_rms_mm)) / 0.75) ** 2)
    for raw_name, item in transferred.items():
        name = dental_assets.normalize_landmark_name(raw_name)
        xyz = item.get("xyz")
        p = Vector(tuple(float(v) for v in xyz))
        hit = tree.find_nearest(p, max_snap_mm)
        if hit is None or hit[0] is None:
            refined = p
            surface_distance = float(max_snap_mm)
            surface_component = 0.0
            method = "UNRESOLVED_NO_SURFACE_HIT"
        else:
            refined = hit[0]
            surface_distance = float(hit[3])
            surface_component = math.exp(-0.5 * (surface_distance / 0.45) ** 2)
            method = "LOCAL_SURFACE_NEAREST"
        semantic_component = 1.0
        confidence = max(0.0, min(1.0, registration_component * surface_component * semantic_component))
        final.append({
            "name": name,
            "xyz": [float(refined.x), float(refined.y), float(refined.z)],
            "confidence": float(confidence),
        })
        metrics[name] = {
            "origin": "TEMPLATE_TRANSFER",
            "transfer_distance_mm": float((refined - p).length),
            "surface_distance_mm": float(surface_distance),
            "refinement_method": method,
            "registration_rms_mm": float(registration_rms_mm),
            "confidence_components": {
                "registration": float(registration_component),
                "surface": float(surface_component),
                "semantic": float(semantic_component),
            },
        }
    return final, metrics
