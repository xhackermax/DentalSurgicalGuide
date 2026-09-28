"""Landmark projection from canonical template coordinates to the patient ghost."""
from __future__ import annotations

from typing import Any

from mathutils import Matrix, Vector

from .. import dental_assets
from .library import FamilyReferenceSnapshot


def _matrix(values) -> Matrix:
    if not isinstance(values, (list, tuple)) or len(values) != 16:
        raise ValueError("Expected flattened 4x4 matrix")
    return Matrix(tuple(tuple(float(values[r*4+c]) for c in range(4)) for r in range(4)))


def transfer_landmarks(
    reference: FamilyReferenceSnapshot,
    ghost_matrix_world: Matrix,
) -> dict[str, dict[str, Any]]:
    """Project canonical library landmarks through the registered ghost transform."""
    fdi = dental_assets.normalize_fdi(reference.fdi, include_primary=False)
    out: dict[str, dict[str, Any]] = {}
    for name in (*dental_assets.required_landmarks(fdi), *dental_assets.optional_landmarks(fdi)):
        obj_name = dental_assets.object_name(fdi, "LANDMARK", landmark=name)
        snap = reference.objects.get(obj_name)
        if snap is None:
            if name in dental_assets.required_landmarks(fdi):
                raise dental_assets.DentalAssetContractError(
                    f"Library reference missing required landmark {name} for FDI {fdi}"
                )
            continue
        p = ghost_matrix_world @ Vector(snap.location_relative_to_anchor)
        out[name] = {
            "name": name,
            "xyz": [float(p.x), float(p.y), float(p.z)],
            "template_xyz": [float(v) for v in snap.location_relative_to_anchor],
            "origin": "TEMPLATE_TRANSFER",
        }
    return out
