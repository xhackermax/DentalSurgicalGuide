"""Derived dental geometry from canonical landmarks.

Landmarks remain the semantic interface. Frames, loops and envelopes are derived
deterministically and persisted only when another component genuinely needs a
Blender object.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping

import bpy
from mathutils import Matrix, Vector

from .. import dental_assets, dental_asset_blender


DERIVED_METADATA_KEY = "DSG_derived_geometry_json"


def _items(landmarks: Iterable[Mapping[str, Any]]) -> dict[str, Vector]:
    out = {}
    for item in landmarks:
        name = dental_assets.normalize_landmark_name(item.get("name"))
        xyz = tuple(float(v) for v in item.get("xyz", ()))
        if len(xyz) != 3 or any(not math.isfinite(v) for v in xyz):
            raise ValueError(f"{name}: invalid xyz")
        out[name] = Vector(xyz)
    return out


def _normalized(vector: Vector, label: str) -> Vector:
    if vector.length <= 1.0e-6:
        raise dental_assets.DentalAssetContractError(f"Cannot derive ToothFrame: degenerate {label}")
    return vector.normalized()


def derive_tooth_frame_matrix(landmarks: Iterable[Mapping[str, Any]]) -> Matrix:
    pts = _items(landmarks)
    required = (
        "MESIAL_CONTACT", "DISTAL_CONTACT",
        "FACIAL_EQUATOR", "LINGUAL_EQUATOR",
        "FACIAL_CERVICAL", "LINGUAL_CERVICAL", "MESIAL_CERVICAL", "DISTAL_CERVICAL",
    )
    missing = [name for name in required if name not in pts]
    if missing:
        raise dental_assets.DentalAssetContractError(
            "Cannot derive ToothFrame; missing: " + ", ".join(missing)
        )

    origin = sum((pts[name] for name in (
        "FACIAL_CERVICAL", "LINGUAL_CERVICAL", "MESIAL_CERVICAL", "DISTAL_CERVICAL"
    )), Vector((0.0, 0.0, 0.0))) / 4.0
    x = _normalized(pts["MESIAL_CONTACT"] - pts["DISTAL_CONTACT"], "mesial-distal axis")
    y_raw = _normalized(pts["FACIAL_EQUATOR"] - pts["LINGUAL_EQUATOR"], "facial-lingual axis")
    y = y_raw - x * y_raw.dot(x)
    y = _normalized(y, "orthogonal facial axis")
    z = _normalized(x.cross(y), "coronal axis")

    # The semantic X/Y definitions fix the handedness. If their cross-product
    # points apically, the input mapping is inconsistent and must be reviewed,
    # not silently mirrored.
    coronal_candidates = [
        pts[name] for name in (
            "MESIOINCISAL", "DISTOINCISAL", "CUSP_TIP", "BUCCAL_CUSP_TIP",
            "LINGUAL_PALATAL_CUSP_TIP", "CENTRAL_FOSSA", "MB_CUSP", "DB_CUSP",
            "MP_CUSP", "DP_CUSP", "ML_CUSP", "DL_CUSP"
        ) if name in pts
    ]
    if coronal_candidates:
        coronal_center = sum(coronal_candidates, Vector((0.0, 0.0, 0.0))) / len(coronal_candidates)
        if (coronal_center - origin).dot(z) <= 0.0:
            raise dental_assets.DentalAssetContractError(
                "Mapped landmarks violate DSG_TOOTH_LOCAL_V1 handedness: +Z points away from coronal anatomy"
            )

    return Matrix((
        (x.x, y.x, z.x, origin.x),
        (x.y, y.y, z.y, origin.y),
        (x.z, y.z, z.z, origin.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


def materialize_tooth_frame(
    fdi: int,
    landmarks: Iterable[Mapping[str, Any]],
    *,
    coordinate_space: str = "WORLD",
) -> bpy.types.Object:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    matrix = derive_tooth_frame_matrix(landmarks)
    name = dental_assets.object_name(fdi, "TOOTH_FRAME")
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = 2.5
    obj.matrix_world = matrix
    dental_asset_blender.stamp_object(
        obj, fdi=fdi, role="TOOTH_FRAME", source="DERIVED",
        coordinate_space=coordinate_space, rename=True,
    )
    dental_asset_blender.validate_tooth_frame_object(obj, fdi=fdi)
    return obj


def _project_local(frame: Matrix, pts: dict[str, Vector], names: Iterable[str]):
    inv = frame.inverted_safe()
    return [
        tuple(float(v) for v in (inv @ pts[name]))
        for name in names if name in pts
    ]


def derive_geometry(
    fdi: int,
    landmarks: Iterable[Mapping[str, Any]],
    *,
    frame_matrix: Matrix | None = None,
) -> dict[str, Any]:
    """Compute compact loops/envelopes as data, not duplicate SSOT objects."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    pts = _items(landmarks)
    frame = frame_matrix or derive_tooth_frame_matrix(landmarks)

    cervical_order = ("MESIAL_CERVICAL", "FACIAL_CERVICAL", "DISTAL_CERVICAL", "LINGUAL_CERVICAL")
    cervical = _project_local(frame, pts, cervical_order)

    cls = dental_assets.tooth_class_from_fdi(fdi)
    if cls == "INCISOR":
        occ_names = ("MESIOINCISAL", "DISTOINCISAL")
    elif cls == "CANINE":
        occ_names = ("MESIAL_CUSP_RIDGE_END", "CUSP_TIP", "DISTAL_CUSP_RIDGE_END")
    else:
        occ_names = ("OCC_MESIOBUCCAL", "OCC_DISTOBUCCAL", "OCC_DISTOLINGUAL", "OCC_MESIOLINGUAL")
    occlusal = _project_local(frame, pts, occ_names)

    all_local = [frame.inverted_safe() @ p for p in pts.values()]
    if all_local:
        mins = [min(float(p[i]) for p in all_local) for i in range(3)]
        maxs = [max(float(p[i]) for p in all_local) for i in range(3)]
    else:
        mins = maxs = [0.0, 0.0, 0.0]
    result = {
        "schema": "dsg.dental_derived_geometry.v1",
        "fdi": fdi,
        "frame": [float(frame[r][c]) for r in range(4) for c in range(4)],
        "cervical_loop_local": cervical,
        "occlusal_envelope_local": occlusal,
        "crown_envelope_local_aabb": {"min": mins, "max": maxs},
    }
    return result


def store_derived_geometry(obj: bpy.types.Object, data: Mapping[str, Any]) -> None:
    obj[DERIVED_METADATA_KEY] = json.dumps(dict(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
