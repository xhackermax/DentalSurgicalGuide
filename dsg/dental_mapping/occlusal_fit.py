"""Final antagonist adjustment for CrownTarget.

OcclusalFit is intentionally last in the prosthetic pipeline. The operation is
transactional: the original mesh remains available until the evaluated Boolean
passes topology checks and affected semantic landmarks are reprojected.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Any

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

from .. import dental_assets, dental_asset_blender


@dataclass(frozen=True, slots=True)
class OcclusalFitPolicy:
    solver: str = "EXACT"
    max_landmark_reproject_mm: float = 2.0


def _mesh_topology(mesh: bpy.types.Mesh) -> dict[str, Any]:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        nonmanifold_gt2 = sum(1 for edge in bm.edges if len(edge.link_faces) > 2)
        boundary = sum(1 for edge in bm.edges if len(edge.link_faces) == 1)
        isolated = sum(1 for edge in bm.edges if len(edge.link_faces) == 0)
        degenerate_faces = sum(1 for face in bm.faces if face.calc_area() <= 1.0e-10)
        return {
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "edges_more_than_2_faces": nonmanifold_gt2,
            "boundary_edges": boundary,
            "isolated_edges": isolated,
            "degenerate_faces": degenerate_faces,
            "closed_manifold": bool(bm.edges) and all(len(edge.link_faces) == 2 for edge in bm.edges),
        }
    finally:
        bm.free()


def _functional_landmark_objects(fdi: int) -> list[bpy.types.Object]:
    result = []
    for name in (*dental_assets.required_landmarks(fdi), *dental_assets.optional_landmarks(fdi)):
        if "CERVICAL" in name or "EQUATOR" in name:
            continue
        obj = bpy.data.objects.get(dental_assets.object_name(fdi, "LANDMARK", landmark=name))
        if obj is not None:
            result.append(obj)
    return result


def _reproject_landmarks(
    crown: bpy.types.Object,
    landmarks: list[bpy.types.Object],
    *,
    max_distance_mm: float,
) -> dict[str, Any]:
    tree = BVHTree.FromObject(crown, bpy.context.evaluated_depsgraph_get(), deform=True, cage=False)
    if tree is None:
        raise RuntimeError("Could not build post-occlusion crown BVH")
    changes = {}
    unresolved = []
    for obj in landmarks:
        before = obj.matrix_world.translation.copy()
        hit = tree.find_nearest(before, max_distance_mm)
        if hit is None or hit[0] is None:
            unresolved.append(obj.name)
            continue
        after = hit[0]
        distance = float((after - before).length)
        obj.matrix_world.translation = after
        changes[obj.name] = {
            "before": [float(v) for v in before],
            "after": [float(v) for v in after],
            "reprojection_mm": distance,
        }
    return {"changes": changes, "unresolved": unresolved}


def fit_occlusion(
    crown: bpy.types.Object,
    antagonist: bpy.types.Object,
    *,
    fdi: int,
    policy: OcclusalFitPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or OcclusalFitPolicy()
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dental_asset_blender.validate_object_contract(
        crown, expected_fdi=fdi, expected_role="CROWN_TARGET"
    )
    if antagonist is None or antagonist.type != "MESH":
        raise ValueError("Antagonist must be a mesh")
    if crown.type != "MESH" or crown.data is None:
        raise ValueError("CrownTarget must be a mesh")

    original_topology = _mesh_topology(crown.data)
    original_mesh = crown.data
    modifier = crown.modifiers.new(name="DSG_OcclusalFit_TMP", type="BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = policy.solver
    modifier.object = antagonist
    depsgraph = bpy.context.evaluated_depsgraph_get()

    try:
        depsgraph.update()
        evaluated = crown.evaluated_get(depsgraph)
        new_mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
    finally:
        if crown.modifiers.get(modifier.name) is not None:
            crown.modifiers.remove(modifier)

    if new_mesh is None or len(new_mesh.vertices) == 0 or len(new_mesh.polygons) == 0:
        if new_mesh is not None:
            bpy.data.meshes.remove(new_mesh)
        raise RuntimeError("Occlusal Boolean produced an empty crown")

    new_topology = _mesh_topology(new_mesh)
    invalid = (
        new_topology["edges_more_than_2_faces"] > 0
        or new_topology["isolated_edges"] > 0
        or new_topology["degenerate_faces"] > 0
        or (original_topology["closed_manifold"] and not new_topology["closed_manifold"])
    )
    if invalid:
        bpy.data.meshes.remove(new_mesh)
        raise RuntimeError(
            "Occlusal Boolean rejected: topology would become invalid "
            f"({new_topology})"
        )

    landmarks = _functional_landmark_objects(fdi)
    crown.data = new_mesh
    new_mesh.name = f"{crown.name}_DATA"
    reproject = _reproject_landmarks(
        crown, landmarks, max_distance_mm=policy.max_landmark_reproject_mm
    )
    if reproject["unresolved"]:
        # Transaction rollback. Do not leave a semantically incomplete CrownTarget.
        crown.data = original_mesh
        bpy.data.meshes.remove(new_mesh)
        raise RuntimeError(
            "OcclusalFit could not preserve functional landmarks: "
            + ", ".join(reproject["unresolved"])
        )

    if original_mesh.users == 0:
        bpy.data.meshes.remove(original_mesh)

    report = {
        "schema": "dsg.occlusal_fit.v1",
        "fdi": fdi,
        "antagonist": antagonist.name,
        "phase": "FINAL",
        "topology_before": original_topology,
        "topology_after": new_topology,
        "landmark_reprojection": reproject,
        "policy": asdict(policy),
    }
    crown["DSG_occlusal_fit_json"] = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return report
