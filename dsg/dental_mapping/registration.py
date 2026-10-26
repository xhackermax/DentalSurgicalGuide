"""Template → ghost → patient surface registration.

Registration produces geometry/mapping evidence only. It never changes FDI.
The canonical FDI identity comes from the segmented TOOTH object/contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .. import dental_assets, dental_asset_blender


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    max_samples_coarse: int = 450
    max_samples_icp: int = 2500
    max_iterations: int = 18
    trim_fraction: float = 0.82
    convergence_mm: float = 0.015
    valid_rms_mm: float = 0.75
    review_rms_mm: float = 1.25
    invalid_rms_mm: float = 2.0
    min_uniform_scale: float = 0.75
    max_uniform_scale: float = 1.35


def _np():
    import numpy as np
    return np


def _matrix_tuple(matrix: Matrix) -> list[float]:
    return [float(matrix[r][c]) for r in range(4) for c in range(4)]


def _world_points(obj: bpy.types.Object, max_points: int) -> Any:
    np = _np()
    if obj is None or obj.type != "MESH" or obj.data is None:
        raise ValueError("Registration requires mesh objects")
    count = len(obj.data.vertices)
    if count < 16:
        raise ValueError(f"{obj.name}: insufficient vertices for registration")
    stride = max(1, int(math.ceil(count / max(16, int(max_points)))))
    matrix = obj.matrix_world
    points = [matrix @ obj.data.vertices[i].co for i in range(0, count, stride)]
    arr = np.asarray([(p.x, p.y, p.z) for p in points], dtype=np.float64)
    if arr.shape[0] < 16:
        raise ValueError(f"{obj.name}: insufficient sampled vertices")
    return arr


def _pca(points):
    np = _np()
    center = points.mean(axis=0)
    centered = points - center[None, :]
    covariance = centered.T @ centered / max(1, points.shape[0] - 1)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    values = values[order]
    basis = vectors[:, order]
    # eigh returns an orthonormal basis but sign is arbitrary. Force a proper basis.
    if np.linalg.det(basis) < 0:
        basis[:, -1] *= -1.0
    radius = math.sqrt(max(1.0e-12, float((centered * centered).sum(axis=1).mean())))
    return center, basis, values, radius


def _proper_signed_permutations():
    np = _np()
    import itertools
    out = []
    eye = np.eye(3)
    for perm in itertools.permutations(range(3)):
        p = eye[:, perm]
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            s = np.diag(signs)
            m = p @ s
            if np.linalg.det(m) > 0.5:
                out.append(m)
    return out


def _bvh_for_object(obj: bpy.types.Object) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(obj, depsgraph, deform=True, cage=False)
    if tree is None:
        raise RuntimeError(f"Could not build BVH for {obj.name}")
    return tree


def _nearest_rms(tree: BVHTree, points, *, max_points: int = 500) -> float:
    np = _np()
    if points.shape[0] > max_points:
        stride = max(1, int(math.ceil(points.shape[0] / max_points)))
        points = points[::stride]
    distances = []
    for xyz in points:
        hit = tree.find_nearest(Vector((float(xyz[0]), float(xyz[1]), float(xyz[2]))))
        if hit is None or hit[0] is None:
            continue
        distances.append(float(hit[3]))
    if len(distances) < 12:
        return float("inf")
    arr = np.asarray(distances, dtype=np.float64)
    return float(math.sqrt(float((arr * arr).mean())))


def _coarse_transform(template: bpy.types.Object, patient: bpy.types.Object, policy: RegistrationPolicy):
    np = _np()
    src = _world_points(template, policy.max_samples_coarse)
    dst = _world_points(patient, policy.max_samples_coarse)
    src_center, src_basis, _sv, src_radius = _pca(src)
    dst_center, dst_basis, _dv, dst_radius = _pca(dst)
    uniform_scale = dst_radius / max(src_radius, 1.0e-9)
    uniform_scale = max(policy.min_uniform_scale, min(policy.max_uniform_scale, uniform_scale))
    tree = _bvh_for_object(patient)

    best = None
    for signed_perm in _proper_signed_permutations():
        rotation = dst_basis @ signed_perm @ src_basis.T
        if np.linalg.det(rotation) < 0.0:
            continue
        transformed = (uniform_scale * (rotation @ (src - src_center).T)).T + dst_center[None, :]
        rms = _nearest_rms(tree, transformed, max_points=policy.max_samples_coarse)
        if best is None or rms < best["rms"]:
            best = {"rms": rms, "rotation": rotation, "scale": uniform_scale}
    if best is None or not math.isfinite(float(best["rms"])):
        raise RuntimeError("Could not determine a stable coarse tooth registration")

    r = best["rotation"]
    s = float(best["scale"])
    A = Matrix((
        (s*r[0,0], s*r[0,1], s*r[0,2], float(dst_center[0] - s*(r[0] @ src_center))),
        (s*r[1,0], s*r[1,1], s*r[1,2], float(dst_center[1] - s*(r[1] @ src_center))),
        (s*r[2,0], s*r[2,1], s*r[2,2], float(dst_center[2] - s*(r[2] @ src_center))),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return A, float(best["rms"]), s


def _rigid_kabsch(src, dst) -> Matrix:
    np = _np()
    if src.shape != dst.shape or src.shape[0] < 6:
        raise ValueError("Kabsch requires paired point arrays")
    cs = src.mean(axis=0)
    cd = dst.mean(axis=0)
    x = src - cs
    y = dst - cd
    H = x.T @ y
    U, _S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T
    t = cd - R @ cs
    return Matrix((
        (float(R[0,0]), float(R[0,1]), float(R[0,2]), float(t[0])),
        (float(R[1,0]), float(R[1,1]), float(R[1,2]), float(t[1])),
        (float(R[2,0]), float(R[2,1]), float(R[2,2]), float(t[2])),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _icp_refine(ghost: bpy.types.Object, patient: bpy.types.Object, policy: RegistrationPolicy):
    np = _np()
    tree = _bvh_for_object(patient)
    history = []
    previous = float("inf")
    for iteration in range(policy.max_iterations):
        src = _world_points(ghost, policy.max_samples_icp)
        pairs_src = []
        pairs_dst = []
        distances = []
        for xyz in src:
            hit = tree.find_nearest(Vector((float(xyz[0]), float(xyz[1]), float(xyz[2]))))
            if hit is None or hit[0] is None:
                continue
            p = hit[0]
            pairs_src.append(xyz)
            pairs_dst.append((p.x, p.y, p.z))
            distances.append(float(hit[3]))
        if len(distances) < 24:
            raise RuntimeError("ICP could not find enough surface correspondences")
        dist = np.asarray(distances, dtype=np.float64)
        cutoff = float(np.quantile(dist, max(0.50, min(0.98, policy.trim_fraction))))
        keep = dist <= cutoff
        src_keep = np.asarray(pairs_src, dtype=np.float64)[keep]
        dst_keep = np.asarray(pairs_dst, dtype=np.float64)[keep]
        if src_keep.shape[0] < 12:
            raise RuntimeError("ICP trimming rejected too many correspondences")
        delta = _rigid_kabsch(src_keep, dst_keep)
        ghost.matrix_world = delta @ ghost.matrix_world

        post_src = _world_points(ghost, policy.max_samples_icp)
        rms = _nearest_rms(tree, post_src, max_points=policy.max_samples_icp)
        history.append(float(rms))
        if not math.isfinite(rms):
            raise RuntimeError("ICP produced non-finite RMS")
        if previous - rms < policy.convergence_mm:
            break
        previous = rms
    return (history[-1] if history else float("inf")), history


def _mapping_state(rms_mm: float, policy: RegistrationPolicy) -> tuple[str, float]:
    if not math.isfinite(rms_mm) or rms_mm > policy.invalid_rms_mm:
        return "INVALID", 0.0
    sigma = max(0.1, policy.valid_rms_mm)
    confidence = math.exp(-0.5 * (rms_mm / sigma) ** 2)
    confidence = max(0.0, min(1.0, confidence))
    if rms_mm <= policy.valid_rms_mm:
        return "VALID", confidence
    if rms_mm <= policy.review_rms_mm:
        return "REVIEW", confidence
    return "LOW_CONFIDENCE", confidence


def create_ghost(
    template: bpy.types.Object,
    *,
    fdi: int,
    coordinate_space: str,
    replace_existing: bool = True,
) -> bpy.types.Object:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    canonical = dental_assets.object_name(fdi, "TOOTH_GHOST")
    existing = bpy.data.objects.get(canonical)
    if existing is not None:
        if not replace_existing:
            return existing
        data = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)

    ghost = template.copy()
    ghost.data = template.data.copy() if template.data is not None else None
    ghost.matrix_world = template.matrix_world.copy()
    collection = bpy.data.collections.get("DSG_Dental_Ghosts")
    if collection is None:
        collection = bpy.data.collections.new("DSG_Dental_Ghosts")
        bpy.context.scene.collection.children.link(collection)
    collection.objects.link(ghost)
    dental_asset_blender.stamp_object(
        ghost,
        fdi=fdi,
        role="TOOTH_GHOST",
        source="DERIVED",
        coordinate_space=coordinate_space,
        rename=True,
    )
    ghost.display_type = "WIRE"
    ghost.show_in_front = True
    return ghost


def register_template_to_patient(
    template: bpy.types.Object,
    patient: bpy.types.Object,
    *,
    fdi: int,
    policy: RegistrationPolicy | None = None,
    keep_ghost: bool = True,
) -> dict[str, Any]:
    """Coarse PCA registration followed by trimmed surface ICP."""
    policy = policy or RegistrationPolicy()
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    if dental_asset_blender.object_fdi(patient) not in {0, fdi}:
        raise dental_assets.DentalAssetContractError(
            f"Patient tooth FDI {dental_asset_blender.object_fdi(patient)} != requested FDI {fdi}"
        )
    dental_asset_blender.validate_object_contract(
        template, expected_fdi=fdi, expected_role="TOOTH_TEMPLATE"
    )
    if patient.type != "MESH":
        raise ValueError("Patient tooth must be a mesh")
    coordinate_space = dental_asset_blender.object_coordinate_space(patient) or "WORLD"
    ghost = create_ghost(template, fdi=fdi, coordinate_space=coordinate_space)

    coarse_delta, coarse_rms, scale = _coarse_transform(template, patient, policy)
    ghost.matrix_world = coarse_delta @ template.matrix_world
    final_rms, history = _icp_refine(ghost, patient, policy)
    state, confidence = _mapping_state(final_rms, policy)

    transform = ghost.matrix_world @ template.matrix_world.inverted_safe()
    result = {
        "schema": "dsg.dental_registration.v1",
        "method": "PCA_COARSE+TRIMMED_SURFACE_ICP",
        "fdi": fdi,
        "ghost_object": ghost.name,
        "coarse_rms_mm": float(coarse_rms),
        "rms_mm": float(final_rms),
        "iterations": len(history),
        "history_rms_mm": [float(v) for v in history],
        "uniform_scale": float(scale),
        "transform_template_to_target": _matrix_tuple(transform),
        "state": state,
        "confidence": float(confidence),
    }
    ghost["DSG_registration_json"] = __import__("json").dumps(result, separators=(",", ":"), sort_keys=True)
    if not keep_ghost:
        data = ghost.data
        bpy.data.objects.remove(ghost, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
        result["ghost_object"] = ""
    return result


# ---------------------------------------------------------------------------
# Mapper extension: CROWN_TEMPLATE -> CROWN_GHOST -> patient TOOTH
# Kept outside the immutable shared dental-assets contract v1. The base hash is
# intentionally unchanged; the extension role is stamped with the same family
# metadata plus DSG_mapper_extension_role=CROWN_GHOST.
CROWN_GHOST_ROLE = "CROWN_GHOST"
CROWN_GHOST_NAME_PATTERN = "DSG_CrownGhost_FDI_{fdi:02d}"


def _stamp_crown_ghost(obj: bpy.types.Object, *, fdi: int, coordinate_space: str) -> bpy.types.Object:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    keys = dental_assets.property_keys()
    values = {
        keys["schema"]: dental_assets.schema(),
        keys["contract_version"]: dental_assets.contract_version(),
        keys["contract_hash"]: dental_assets.contract_sha256(),
        keys["family_id"]: dental_assets.family_id(fdi),
        keys["asset_id"]: f"FDI.{fdi:02d}.CROWN_GHOST",
        keys["asset_role"]: CROWN_GHOST_ROLE,
        keys["asset_source"]: "DERIVED",
        keys["asset_revision"]: "1",
        keys["fdi"]: fdi,
        keys["tooth_class"]: dental_assets.tooth_class_from_fdi(fdi),
        keys["arch"]: dental_assets.arch_from_fdi(fdi),
        keys["side"]: dental_assets.side_from_fdi(fdi),
        keys["coordinate_space"]: str(coordinate_space).upper(),
    }
    for key, value in values.items():
        obj[str(key)] = value
    obj["DSG_mapper_extension_role"] = CROWN_GHOST_ROLE
    obj["DSG_mapper_schema"] = "dsg.dental_mapper.v2"
    obj["DSG_authority"] = "DERIVED_FROM_GOLD_STANDARD"
    obj["DSG_inference_source"] = "ARCHITECT_GOLD_STANDARD"
    obj["DSG_approval_state"] = "TEMPORARY"
    canonical = CROWN_GHOST_NAME_PATTERN.format(fdi=fdi)
    existing = bpy.data.objects.get(canonical)
    if existing is not None and existing is not obj:
        data = getattr(existing, "data", None)
        bpy.data.objects.remove(existing, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    obj.name = canonical
    if obj.data is not None:
        obj.data.name = canonical + "_DATA"
    return obj


def create_crown_ghost(
    crown_template: bpy.types.Object,
    *,
    fdi: int,
    coordinate_space: str,
    replace_existing: bool = True,
) -> bpy.types.Object:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dental_asset_blender.validate_object_contract(
        crown_template, expected_fdi=fdi, expected_role="CROWN_TEMPLATE"
    )
    canonical = CROWN_GHOST_NAME_PATTERN.format(fdi=fdi)
    existing = bpy.data.objects.get(canonical)
    if existing is not None:
        if not replace_existing:
            return existing
        data = getattr(existing, "data", None)
        bpy.data.objects.remove(existing, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    ghost = crown_template.copy()
    ghost.data = crown_template.data.copy() if crown_template.data is not None else None
    ghost.matrix_world = crown_template.matrix_world.copy()
    collection = bpy.data.collections.get("DSG_Dental_Ghosts")
    if collection is None:
        collection = bpy.data.collections.new("DSG_Dental_Ghosts")
        bpy.context.scene.collection.children.link(collection)
    collection.objects.link(ghost)
    _stamp_crown_ghost(ghost, fdi=fdi, coordinate_space=coordinate_space)
    ghost.display_type = "WIRE"
    ghost.show_in_front = True
    ghost["DSG_ghost_source_role"] = "CROWN_TEMPLATE"
    ghost["DSG_ghost_target_role"] = "TOOTH"
    return ghost


def register_crown_template_to_patient(
    crown_template: bpy.types.Object,
    patient: bpy.types.Object,
    *,
    fdi: int,
    policy: RegistrationPolicy | None = None,
    keep_ghost: bool = True,
) -> dict[str, Any]:
    """Gold Standard coronal registration: CROWN_TEMPLATE -> CROWN_GHOST -> TOOTH."""
    policy = policy or RegistrationPolicy()
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dental_asset_blender.validate_object_contract(
        crown_template, expected_fdi=fdi, expected_role="CROWN_TEMPLATE"
    )
    if dental_asset_blender.object_fdi(patient) not in {0, fdi}:
        raise dental_assets.DentalAssetContractError(
            f"Patient tooth FDI {dental_asset_blender.object_fdi(patient)} != requested FDI {fdi}"
        )
    if patient.type != "MESH":
        raise ValueError("Patient tooth must be a mesh")
    coordinate_space = dental_asset_blender.object_coordinate_space(patient) or "WORLD"
    ghost = create_crown_ghost(
        crown_template, fdi=fdi, coordinate_space=coordinate_space, replace_existing=True
    )
    coarse_delta, coarse_rms, scale = _coarse_transform(crown_template, patient, policy)
    ghost.matrix_world = coarse_delta @ crown_template.matrix_world
    final_rms, history = _icp_refine(ghost, patient, policy)
    state, confidence = _mapping_state(final_rms, policy)
    transform = ghost.matrix_world @ crown_template.matrix_world.inverted_safe()
    result = {
        "schema": "dsg.dental_registration.v2",
        "method": "CROWN_GHOST_PCA_COARSE+TRIMMED_SURFACE_ICP",
        "mapping_scope": "CORONAL_GOLD_STANDARD",
        "fdi": fdi,
        "template_role": "CROWN_TEMPLATE",
        "ghost_role": "CROWN_GHOST",
        "ghost_object": ghost.name,
        "coarse_rms_mm": float(coarse_rms),
        "rms_mm": float(final_rms),
        "iterations": len(history),
        "history_rms_mm": [float(v) for v in history],
        "uniform_scale": float(scale),
        "transform_template_to_target": _matrix_tuple(transform),
        "state": state,
        "confidence": float(confidence),
    }
    ghost["DSG_registration_json"] = __import__("json").dumps(result, separators=(",", ":"), sort_keys=True)
    if not keep_ghost:
        data = ghost.data
        bpy.data.objects.remove(ghost, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        result["ghost_object"] = ""
    return result
